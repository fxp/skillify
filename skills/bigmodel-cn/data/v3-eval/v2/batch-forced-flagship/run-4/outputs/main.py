#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱开放平台（bigmodel.cn）Batch API 批量做评论情感分类。

流程：读取同目录 comments.txt（每行一条评论）→ 构造 chat/completions 的 jsonl
请求文件 → 上传（purpose=batch）→ 创建 batch 任务 → 打印 batch 任务 id（不等待跑完）。

关于模型选择（重要）：
- 首选 glm-5.3（旗舰模型）。
- 但 Batch API 有一份独立于平台模型列表的白名单，校验发生在文件上传阶段：
  白名单外的模型报业务码 1210「模型名称错误」，报错信息里会附带当前白名单。
  截至 2026-09 实测，旗舰 glm-5.3 / glm-5.2 都不在白名单内（智谱官方文档的
  模型列表长期未更新，报错信息才是白名单的权威来源）。
- 因此脚本先按 glm-5.3 真实尝试上传；若被 1210 拒绝，则解析报错信息里的白名单，
  按「质量优先」的预设顺序选出白名单内最强的文本模型（目前是 glm-5.1）重试，
  并在输出里说明调整原因。若报错里解析不出白名单，则直接按预设顺序逐个降级。

依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import json
import os
import re
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api"
CHAT_ENDPOINT = "/v4/chat/completions"  # Batch 目前唯一支持的 endpoint，jsonl 的 url 与之保持一致
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMMENTS_FILE = os.path.join(SCRIPT_DIR, "comments.txt")

# 候选模型按质量从高到低排列；白名单外的会在上传阶段被拒（1210），自动往下降级。
PREFERRED_MODELS = [
    "glm-5.3",
    "glm-5.2",
    "glm-5.1",
    "glm-5-turbo",
    "glm-4-plus",
    "glm-4-0520",
    "glm-4",
    "glm-4-long",
    "glm-4-air-250414",
    "glm-4-air-0111",
    "glm-4-air",
    "glm-4-flashx-250414",
    "glm-4-flash",
]
MAX_MODEL_ATTEMPTS = 6  # 报错里解析不出白名单时最多盲试几个，避免无意义地连打接口

SYSTEM_PROMPT = (
    "你是评论情感分类器。对用户发送的一条评论判断情感倾向，"
    "只输出下面三个标签之一，不要输出任何多余内容：\n"
    "正面\n负面\n中性"
)

# 从报错信息里捞模型代码（如 glm-5.1、glm-4-air-250414、cogview-4-250304）
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)+")
# 视觉模型（glm-4v / glm-5v-turbo 等）不适合做纯文本分类的兜底候选
_VISION_RE = re.compile(r"^glm-\d+v")


def read_comments(path):
    """读取评论文件：每行一条，忽略空行。utf-8-sig 兼容带 BOM 的文件。"""
    if not os.path.isfile(path):
        sys.exit(f"[错误] 找不到评论文件：{path}（应与 main.py 同目录，每行一条评论）")
    with open(path, encoding="utf-8-sig") as f:
        comments = [line.strip() for line in f if line.strip()]
    if not comments:
        sys.exit(f"[错误] {path} 中没有有效评论。")
    return comments


def build_jsonl_bytes(model, comments):
    """构造 Batch 请求文件内容（每行一个独立的 chat/completions 请求）。"""
    lines = []
    for i, comment in enumerate(comments, 1):
        request = {
            # custom_id 有未文档化的 6 字符下限，过短在上传阶段就报错，用 request-000001 格式
            "custom_id": f"request-{i:06d}",
            "method": "POST",
            "url": CHAT_ENDPOINT,
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": comment},
                ],
                "temperature": 0.1,
                # 思考型模型的思考 token 也计入 max_tokens，预算给足，避免正文被截空
                "max_tokens": 2048,
            },
        }
        lines.append(json.dumps(request, ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8")


def extract_error(resp):
    """提取业务错误。智谱部分接口 HTTP 200 也带业务错误体，不能只看状态码。

    返回 {"code": ..., "message": ...} 或 None（响应看起来是成功的）。
    """
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return {
                "code": str(err.get("code", f"HTTP {resp.status_code}")),
                "message": str(err.get("message", "")),
            }
        if "code" in body and "message" in body and not body.get("id"):
            return {"code": str(body["code"]), "message": str(body["message"])}
        if resp.ok:
            return None
        return {"code": f"HTTP {resp.status_code}", "message": json.dumps(body, ensure_ascii=False)[:300]}
    if resp.ok:
        return None
    return {"code": f"HTTP {resp.status_code}", "message": (resp.text or "")[:300]}


def parse_whitelist(message):
    """从 1210 报错文本里提取模型白名单（报错信息是白名单最权威的来源）。"""
    return [t.lower() for t in _TOKEN_RE.findall(message or "")]


def is_model_rejection(err):
    """判断错误是否属于「模型不在 Batch 白名单」这类换模型就能救的错误。"""
    if not err:
        return False
    msg = err.get("message", "")
    return err.get("code") == "1210" and ("模型" in msg or "model" in msg.lower())


def http_request(method, url, tries=3, **kwargs):
    """带简单重试的请求（仅重试网络异常与 5xx，业务错误原样返回）。"""
    kwargs.setdefault("timeout", 60)
    for attempt in range(1, tries + 1):
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            if attempt == tries:
                raise RuntimeError(f"网络请求失败（{method} {url}）：{exc}") from exc
        else:
            if resp.status_code < 500 or attempt == tries:
                return resp
        time.sleep(2 * attempt)
    raise RuntimeError("不应执行到这里")


def upload_batch_file(api_key, model, comments):
    """上传 Batch 请求文件。成功返回 (file_id, None)，失败返回 (None, err)。"""
    resp = http_request(
        "POST",
        f"{BASE_URL}/paas/v4/files",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": ("sentiment_requests.jsonl", build_jsonl_bytes(model, comments), "application/x-ndjson")},
        data={"purpose": "batch"},
    )
    err = extract_error(resp)
    if err:
        return None, err
    try:
        file_id = resp.json().get("id")
    except (ValueError, AttributeError):
        file_id = None
    if not file_id:
        return None, {"code": f"HTTP {resp.status_code}", "message": f"上传响应中没有文件 id：{resp.text[:200]}"}
    return file_id, None


def create_batch(api_key, input_file_id, model, n_comments):
    """创建 batch 任务。成功返回 (batch对象, None)，失败返回 (None, err)。"""
    resp = http_request(
        "POST",
        f"{BASE_URL}/paas/v4/batches",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "input_file_id": input_file_id,
            "endpoint": CHAT_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"task": "sentiment-classification", "model": model, "rows": str(n_comments)},
        },
    )
    err = extract_error(resp)
    if err:
        return None, err
    try:
        batch = resp.json()
    except ValueError:
        batch = None
    if not isinstance(batch, dict) or not batch.get("id"):
        return None, {"code": f"HTTP {resp.status_code}", "message": f"响应中没有任务 id：{resp.text[:200]}"}
    return batch, None


def run(api_key, comments):
    """上传请求文件并创建 batch 任务。按质量优先选模型，被白名单拒绝时自动降级。

    返回 (实际使用的模型, batch 对象)。
    """
    candidates = list(PREFERRED_MODELS)
    whitelist_applied = False
    attempts = 0

    while candidates and attempts < MAX_MODEL_ATTEMPTS:
        model = candidates.pop(0)
        attempts += 1
        print(f"[{attempts}] 尝试模型 {model}：构造并上传 batch 请求文件 ...")

        file_id, err = upload_batch_file(api_key, model, comments)
        if file_id is None:
            if is_model_rejection(err):
                print(f"    被拒绝（{err['code']}）：{err['message'][:160]}")
                if not whitelist_applied:
                    whitelist_applied = True
                    wl = parse_whitelist(err["message"])
                    if wl:
                        print(f"    从报错信息解析到 Batch 白名单（{len(wl)} 个模型），按质量优先重排候选。")
                        rest = [m for m in candidates if m in wl]
                        extra = [
                            m for m in wl
                            if m not in PREFERRED_MODELS and m.startswith("glm-") and not _VISION_RE.match(m)
                        ]
                        candidates = rest + extra
                    else:
                        print("    报错信息里没有可解析的白名单，按预设的质量优先顺序继续降级。")
                continue
            raise RuntimeError(f"上传请求文件失败（{err['code']}）：{err['message']}")

        print(f"    上传成功，input_file_id = {file_id}")

        batch, err = create_batch(api_key, file_id, model, len(comments))
        if batch is not None:
            return model, batch
        if is_model_rejection(err):
            # 白名单校验在上传阶段，这里只是兜底
            print(f"    创建任务被拒（{err['code']}）：{err['message'][:160]}")
            continue
        raise RuntimeError(f"创建 batch 任务失败（{err['code']}）：{err['message']}")

    raise RuntimeError(
        "候选模型均被 Batch 拒绝，任务未能创建。请查看上方报错信息中的白名单，"
        "或到 docs.bigmodel.cn 确认 Batch 当前支持的模型。"
    )


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("[错误] 未设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key），请先设置后再运行。")

    comments = read_comments(COMMENTS_FILE)
    print(f"从 {COMMENTS_FILE} 读取到 {len(comments)} 条评论。")

    requested = PREFERRED_MODELS[0]
    model, batch = run(api_key, comments)

    print()
    if model != requested:
        print(f"[调整说明] 要求使用 {requested}，但 Batch API 有一份独立于平台模型列表的白名单，")
        print(f"           {requested} 目前不在白名单内（文件上传阶段即被拒，业务码 1210）。")
        print(f"           已自动改用白名单内质量最强的文本模型 {model}——这是 Batch 通道下最接近旗舰的选择。")

    print("=" * 60)
    print("Batch 任务创建成功（异步执行，预计 24 小时内完成，脚本不等待）")
    print(f"  batch 任务 id : {batch['id']}")
    print(f"  状态          : {batch.get('status')}")
    print(f"  模型          : {model}")
    request_counts = batch.get("request_counts") or {}
    if request_counts.get("total") is not None:
        print(f"  请求总数      : {request_counts['total']}")
    print("=" * 60)
    print(f"之后可用该 id 查询进度：GET {BASE_URL}/paas/v4/batches/{batch['id']}")


if __name__ == "__main__":
    main()
