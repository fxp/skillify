#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱开放平台 Batch API 对 comments.txt 里的用户评论做情感分类。

流程：读取评论 -> 构造 batch 请求 jsonl -> 上传文件(purpose=batch) -> 创建 batch 任务
-> 打印任务 id（不轮询、不等跑完）。

模型策略（重要）：
智谱 Batch 只支持一份独立于平台的模型白名单，官方文档不公开这份名单，完整名单只
出现在上传接口的 1210 报错信息里；且校验发生在【文件上传】阶段（POST /paas/v4/files），
还没到创建 batch 那步就会被拒。截至 2026-09 的实测，旗舰 glm-5.3 不在白名单内。
因此脚本的做法：
  1. 先按需求用 glm-5.3 尝试（白名单随平台更新，以实际报错为准，不硬编码"必败"）；
  2. 若上传报"模型名称错误"，从报错原文里解析出当前白名单，按「质量优先」选白名单内
     最强的文本模型（首选 glm-5.1）重建 jsonl 重新上传；
  3. 报错里解析不出名单时，退回内置的质量降级序列逐个尝试。
绝不重试刚被拒的同一个模型。

用法：
    export ZHIPUAI_API_KEY=...
    python3 main.py        # comments.txt 需与脚本同目录，每行一条评论

结果查询（另行执行，本脚本不等待）：
    GET https://open.bigmodel.cn/api/paas/v4/batches/{batch_id}
    完成后 GET .../paas/v4/files/{output_file_id}/content 下载结果 jsonl，
    每行的 custom_id（request-000001…）与输入行一一对应。
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
FILES_URL = f"{BASE_URL}/paas/v4/files"
BATCHES_URL = f"{BASE_URL}/paas/v4/batches"
# jsonl 每行的 url 必须与创建 batch 时传的 endpoint 完全一致，目前仅支持对话补全
BATCH_ENDPOINT = "/v4/chat/completions"

REQUESTED_MODEL = "glm-5.3"
# 质量优先的候选顺序（文本模型；glm-4v*/glm-5v* 是视觉系，cogview/cogvideox/embedding
# 分别是绘图/视频/向量，都不适用于本任务，故不列入）
QUALITY_ORDER = [
    "glm-5.3", "glm-5.2", "glm-5.1", "glm-5-turbo",
    "glm-4-plus", "glm-4-0520", "glm-4-plus-0111", "glm-4",
    "glm-4-long", "glm-4-air-0111", "glm-4-air", "glm-4-air-250414",
    "glm-4-flashx-250414", "glm-4-flash", "glm-3-turbo",
]
MAX_MODEL_ATTEMPTS = 5  # 最多换 5 次模型，防止异常报错导致死循环

SYSTEM_PROMPT = (
    "你是评论情感分类器。判断用户评论的情感倾向，"
    '只输出一个 JSON 对象：{"label": "正面" | "负面" | "中性"}，不要输出任何其他文字。'
)
USER_PROMPT_TEMPLATE = "评论：{text}"

# 5.x 系模型的思考 token 也计入 max_tokens，预算给小会出现 finish_reason=length、
# 正文为空的假成功，这里给足余量（计费按实际用量，调大上限本身不多花钱）
MAX_TOKENS = 2048


def die(msg):
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(1)


def extract_error(body):
    """提取业务错误码与信息。兼容 {error:{code,message}} 与顶层 {code,message} 两种形态，
    避免依赖 HTTP 状态码（部分错误 HTTP 200 也返回）。"""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("code", "")), str(err.get("message", ""))
        code = body.get("code")
        if code not in (None, "", 0, "0"):
            return str(code), str(body.get("message", ""))
    return "", ""


def parse_body(resp):
    try:
        return resp.json()
    except ValueError:
        return {}


def request_with_retry(method, url, key, *, timeout=60, tries=3, **kwargs):
    """带简单重试的请求：仅对网络异常 / 5xx / 429 重试；业务错误原样返回给调用方处理。"""
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            resp = requests.request(
                method, url,
                headers={"Authorization": f"Bearer {key}"},
                timeout=timeout, **kwargs,
            )
            if resp.status_code >= 500 or resp.status_code == 429:
                last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                if attempt < tries:
                    time.sleep(3 * attempt)
                    continue
            return resp
        except requests.RequestException as exc:
            last_err = exc
            if attempt < tries:
                time.sleep(3 * attempt)
                continue
    raise RuntimeError(f"请求 {url} 连续 {tries} 次失败：{last_err}")


def read_comments():
    path = Path(__file__).resolve().parent / "comments.txt"
    if not path.is_file():
        die(f"找不到评论文件：{path}（应与本脚本同目录，每行一条评论）")
    comments = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not comments:
        die(f"评论文件为空：{path}")
    if len(comments) > 50000:  # 单个 batch 文件的请求上限
        die(f"共 {len(comments)} 条，超过单个 batch 文件 50000 条的上限，请拆分后再跑")
    return path, comments


def build_payload(comments, model):
    """构造 batch 请求文件的字节内容（每行一个 JSON 请求）。

    注意两个实测坑：
    - custom_id 有未文档化的 6 字符下限，"r1"/"id-1" 这类会在上传阶段直接报错，
      这里用 request-000001 格式；
    - response_format 的 json_schema 会被静默忽略，可靠做法是 json_object
      并在 prompt 里写清字段结构（后续解析结果时仍需 json.loads 失败兜底）。
    """
    lines = []
    for idx, comment in enumerate((c for c in comments if c and c.strip()), 1):
        lines.append(json.dumps({
            "custom_id": f"request-{idx:06d}",
            "method": "POST",
            "url": BATCH_ENDPOINT,
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_PROMPT_TEMPLATE.format(text=comment)},
                ],
                "temperature": 0.1,
                "max_tokens": MAX_TOKENS,
                "response_format": {"type": "json_object"},
            },
        }, ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8")


def is_model_rejection(code, message):
    """判断上传失败是否为『模型不被 Batch 接受』。

    1210 业务码同时覆盖"模型名称错误"和"custom id 长度不足"两种情况，
    后者是构造问题（本脚本已规避），不能靠换模型解决，须区分开。
    """
    msg = message or ""
    if "模型名称" in msg or "模型不存在" in msg or "白名单" in msg:
        return True
    if "模型" in msg and "不支持" in msg:
        return True
    return code == "1210" and "custom" not in msg.lower()


def parse_whitelist_models(message):
    """从 1210 报错原文中解析 Batch 白名单里的 glm 文本模型。

    报错信息本身是白名单最权威的来源（官方文档不公开，且名单随平台更新）。
    排除视觉系（含 -4v / -5v 的型号）；cogview/cogvideox/embedding 不以 glm-
    开头，天然被排除。
    """
    tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9.\-]*", message or ""))
    return sorted(
        t for t in tokens
        if t.startswith("glm-") and "-4v" not in t and "-5v" not in t
    )


def choose_fallback(message, tried):
    """选出下一个要尝试的模型：白名单解析成功则按质量偏好取交集首选；
    解析失败则沿内置质量降级序列走。均无候选时返回 None。"""
    whitelist = parse_whitelist_models(message)
    candidates = whitelist if whitelist else QUALITY_ORDER
    source = "1210 报错里解析出的白名单" if whitelist else "内置质量降级序列"
    for m in QUALITY_ORDER:
        if m in candidates and m not in tried:
            return m, source
    # 白名单与内置偏好无交集（比如平台出了新一代命名）时，取剩余里"最大"的兜底
    rest = [m for m in candidates if m not in tried]
    if rest:
        return max(rest), source
    return None, source


def upload_requests_file(key, payload):
    """上传 batch 请求文件。返回 (file_id, http_status, error_code, error_message)，
    file_id 非空即成功。"""
    resp = request_with_retry(
        "POST", FILES_URL, key=key, timeout=(10, 300),
        files={"file": ("batch_requests.jsonl", payload)},
        data={"purpose": "batch"},  # 给 Batch 用的文件 purpose 必须是 batch
    )
    body = parse_body(resp)
    code, message = extract_error(body)
    if body.get("id") and not code:
        return body["id"], resp.status_code, "", ""
    return None, resp.status_code, code, message or resp.text[:500]


def create_batch(key, file_id, description):
    resp = request_with_retry(
        "POST", BATCHES_URL, key=key, timeout=60,
        json={
            "input_file_id": file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"description": description},
        },
    )
    body = parse_body(resp)
    code, message = extract_error(body)
    if body.get("id") and not code:
        return body
    die(f"创建 batch 失败：HTTP {resp.status_code} code={code} message={message or resp.text[:500]}")


def main():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        die("环境变量 ZHIPUAI_API_KEY 未设置（标准 API Key，可在 bigmodel.cn 控制台获取）")

    path, comments = read_comments()
    print(f"读取 {path.name}：共 {len(comments)} 条评论")

    # ---- 上传（含 glm-5.3 失败后的自动降级重试）----
    model = REQUESTED_MODEL
    tried = []
    file_id = None
    while file_id is None:
        tried.append(model)
        payload = build_payload(comments, model)
        print(f"以模型 {model} 构造请求文件（{len(comments)} 行，{len(payload)} 字节），上传中 …")
        file_id, status, code, message = upload_requests_file(key, payload)
        if file_id:
            break
        if is_model_rejection(code, message) and len(tried) < MAX_MODEL_ATTEMPTS:
            nxt, source = choose_fallback(message, tried)
            if nxt is None:
                die(f"模型 {model} 被 Batch 拒绝（{code} {message}），且找不到可降级的候选模型")
            print(f"  ⚠ 上传被拒：HTTP {status} code={code} {message}")
            print(f"  ⚠ 原因：Batch 只支持一份独立的模型白名单（官方文档不公开，完整名单只出现在")
            print(f"    该报错里），旗舰 {REQUESTED_MODEL} 不在其中，且校验就发生在文件上传阶段。")
            print(f"  → 按「白名单内质量最强」原则改用 {nxt}（来源：{source}），重建 jsonl 重新上传。")
            model = nxt
            continue
        # custom_id 长度、鉴权、余额等其他错误换模型也救不回来，直接报出
        die(f"上传请求文件失败：HTTP {status} code={code} message={message}")

    if model != REQUESTED_MODEL:
        print()
        print(f"【调整说明】请求的 {REQUESTED_MODEL} 走不通 Batch，已自动降级为 {model}。")
        print(f"理由：见上方报错——glm-5.3 不在 Batch 白名单内；{model} 是白名单内质量最强的")
        print("文本模型，在『把任务跑成』与『分类质量』之间取最优折中。")
        print()

    print(f"上传成功：input_file_id = {file_id}")

    # ---- 创建 batch 任务并打印任务 id ----
    batch = create_batch(key, file_id, f"评论情感分类（{len(comments)} 条，模型 {model}）")
    # request_counts 是嵌套对象，不是顶层字段（官方早期示例写错过）
    total = (batch.get("request_counts") or {}).get("total", len(comments))

    print()
    print("✅ Batch 任务创建成功（不等待完成）")
    print(f"   batch id      : {batch.get('id')}")
    print(f"   模型          : {model}")
    print(f"   状态          : {batch.get('status')}")
    print(f"   请求数        : {total}")
    print(f"   input_file_id : {batch.get('input_file_id', file_id)}")
    print()
    print(f"之后可用下面命令查询进度（建议间隔 20~30 秒轮询）：")
    print(f"  curl -H \"Authorization: Bearer $ZHIPUAI_API_KEY\" {BATCHES_URL}/{batch.get('id')}")
    print("状态到 completed 后，下载 output_file_id 对应文件即为分类结果；")
    print("结果按 custom_id（request-000001…）与输入行一一对应。")


if __name__ == "__main__":
    main()
