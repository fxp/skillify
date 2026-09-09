#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱开放平台 Batch API 批量做评论情感分类。

流程:读同目录 comments.txt(每行一条评论)→ 构造 .jsonl 请求文件
→ 上传(purpose=batch)→ 创建 batch 任务 → 打印任务 ID(不等待执行完成)。

模型策略:首选旗舰 glm-5.3;若上传阶段报业务码 1210(模型名称错误,
即模型不在 Batch 白名单——白名单与平台全部模型不同,且只在报错信息里出现),
则从报错信息解析白名单,按质量优先级降级到名单内最强的模型(当前为 glm-5.1)。

用法:ZHIPUAI_API_KEY=xxx python3 main.py
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
TIMEOUT = 60

PRIMARY_MODEL = "glm-5.3"
# 质量优先的降级候选,从强到弱。前两位(5.3/5.2)目前都不在 Batch 白名单里;
# glm-5.1 是白名单内最强的(实测 2026-09),作为默认降级目标。
PREFERRED_MODELS = [
    "glm-5.3",
    "glm-5.2",
    "glm-5.1",
    "glm-5-turbo",
    "glm-4-plus",
    "glm-4",
    "glm-4-flash",
]

SYSTEM_PROMPT = (
    "你是评论情感分类器。对给出的用户评论判断情感倾向,"
    "只输出一个词:正面、负面 或 中性。不要输出任何其他内容。"
)


class ZhipuAPIError(RuntimeError):
    """平台返回的业务错误(HTTP 4xx + body.error.code)。"""

    def __init__(self, code, message, status_code=None):
        super().__init__(f"[{code}] {message}")
        self.code = str(code) if code is not None else "unknown"
        self.message = message or ""
        self.status_code = status_code


def request_with_retry(method, url, tries=3, **kwargs):
    """带简单重试的请求:仅对网络异常 / 429 / 5xx 重试,4xx 直接返回让上层判业务码。"""
    kwargs.setdefault("timeout", TIMEOUT)
    last_exc = None
    for attempt in range(1, tries + 1):
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
        else:
            if resp.status_code < 500 and resp.status_code != 429:
                return resp
            last_exc = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        if attempt < tries:
            time.sleep(2 * attempt)
    raise RuntimeError(f"请求 {url} 连续 {tries} 次失败: {last_exc}")


def parse_body(resp):
    """解析响应体;body.error 存在时抛 ZhipuAPIError,否则返回解析后的 JSON。"""
    try:
        body = resp.json()
    except ValueError:
        raise ZhipuAPIError(resp.status_code, f"非 JSON 响应: {resp.text[:300]}", resp.status_code)
    if isinstance(body, dict) and body.get("error"):
        err = body["error"]
        raise ZhipuAPIError(err.get("code"), err.get("message"), resp.status_code)
    if resp.status_code != 200:
        raise ZhipuAPIError(resp.status_code, f"HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code)
    return body


def upload_batch_file(jsonl_bytes, headers):
    """上传 .jsonl 请求文件(purpose=batch),返回 file_id。

    模型白名单校验发生在这一步:模型不在 Batch 白名单内时,
    这里就会收到 1210「模型名称错误」,报错信息里带完整白名单。
    """
    resp = request_with_retry(
        "POST",
        FILES_URL,
        headers=headers,
        files={"file": ("batch_requests.jsonl", jsonl_bytes)},
        data={"purpose": "batch"},
    )
    body = parse_body(resp)
    file_id = body.get("id")
    if not file_id:
        raise ZhipuAPIError("unexpected", f"上传响应里没有 id: {body}")
    return file_id


def create_batch(file_id, headers):
    """基于已上传文件创建 batch 任务,返回 Batch 对象。"""
    resp = request_with_retry(
        "POST",
        BATCHES_URL,
        headers={**headers, "Content-Type": "application/json"},
        json={
            "input_file_id": file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {"description": "comments.txt 情感分类"},
        },
    )
    return parse_body(resp)


def build_request_lines(comments, model):
    """把评论列表构造成 Batch 输入 jsonl 的字节内容(每行一个 chat/completions 请求)。

    custom_id 必须唯一且 ≥6 字符(短了上传阶段就报 1210),用 request-0001 格式。
    max_tokens 给 2048:思考型模型的推理 token 计入输出预算,给太小会拿到空正文。
    """
    lines = []
    for idx, comment in enumerate(comments, 1):
        lines.append(
            json.dumps(
                {
                    "custom_id": f"request-{idx:04d}",
                    "method": "POST",
                    "url": "/v4/chat/completions",
                    "body": {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": comment},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 2048,
                    },
                },
                ensure_ascii=False,
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def is_model_not_allowed(err):
    """是否为『模型不在 Batch 白名单』导致的 1210(区别于 custom_id 过短等同码错误)。"""
    return err.code == "1210" and ("模型" in err.message or "model" in err.message.lower())


def ranked_whitelisted_models(message):
    """从 1210 报错信息里解析白名单,按质量优先级返回名单内的候选。

    白名单会随平台更新、官方文档不登,报错信息本身就是最权威的来源,
    所以这里解析报错而不是写死一份列表。
    """
    # 版本段允许点号(glm-5.1 / cogview-4-250304),结尾的句点去掉避免脏匹配
    tokens = {t.rstrip(".") for t in re.findall(r"[a-z][a-z0-9]*(?:-[a-z0-9.]+)+", message.lower())}
    return [m for m in PREFERRED_MODELS if m in tokens]


def find_comments_file():
    script_dir = Path(__file__).resolve().parent
    for directory in (script_dir, Path.cwd()):
        candidate = directory / "comments.txt"
        if candidate.is_file():
            return candidate
    sys.exit(f"错误: 找不到 comments.txt(已查找 {script_dir} 与当前目录)")


def load_comments():
    path = find_comments_file()
    comments = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not comments:
        sys.exit(f"错误: {path} 里没有有效评论(每行一条,不能全为空)")
    return comments


def pick_model_and_upload(comments, headers):
    """依次尝试候选模型上传;撞上白名单 1210 时降级重传。返回 (model, file_id)。"""
    candidates = list(PREFERRED_MODELS)
    tried = []
    while candidates:
        model = candidates.pop(0)
        tried.append(model)
        payload = build_request_lines(comments, model)
        print(f"→ 尝试用 {model} 上传 Batch 请求文件({len(comments)} 条评论)…")
        try:
            file_id = upload_batch_file(payload, headers)
        except ZhipuAPIError as err:
            if not is_model_not_allowed(err):
                raise
            print(f"  ✗ {model} 被拒绝: {err}")
            ranked = ranked_whitelisted_models(err.message)
            if ranked:
                remaining = [m for m in ranked if m not in tried]
                note = "、".join(remaining) if remaining else "无(候选均已试过)"
                print(
                    f"  ↘ 调整: {model} 不在 Batch 白名单内(校验发生在文件上传阶段),"
                    f"按报错信息里的白名单降级,后续候选: {note}"
                )
                candidates = remaining + [m for m in candidates if m not in remaining]
            else:
                print(f"  ↘ 调整: 未能从报错解析出白名单,按既定优先级继续尝试下一个候选")
            continue
        print(f"  ✓ 上传成功,file_id={file_id}")
        return model, file_id
    raise ZhipuAPIError(
        "no_model",
        f"所有候选模型均被 Batch 拒绝(已试: {'、'.join(tried)})。"
        "Batch 只支持一份独立白名单,请以 1210 报错信息中列出的模型为准。",
    )


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误: 未设置环境变量 ZHIPUAI_API_KEY(标准 API Key,https://bigmodel.cn/usercenter/proj-mgmt/apikeys)")
    headers = {"Authorization": f"Bearer {api_key}"}

    comments = load_comments()
    model, file_id = pick_model_and_upload(comments, headers)

    # 落一份 jsonl 便于核对任务内容(失败不影响主流程)
    try:
        (Path(__file__).resolve().parent / "batch_requests.jsonl").write_bytes(
            build_request_lines(comments, model)
        )
    except OSError:
        pass

    batch = create_batch(file_id, headers)
    batch_id = batch.get("id")
    if not batch_id:
        sys.exit(f"错误: 创建 batch 的响应里没有 id: {json.dumps(batch, ensure_ascii=False)[:500]}")

    print()
    print("Batch 任务创建成功(按要求不等待执行完成)")
    print(f"  batch_id : {batch_id}")
    print(f"  status   : {batch.get('status')}")
    print(f"  model    : {model}" + ("(自 glm-5.3 降级,原因见上)" if model != PRIMARY_MODEL else ""))
    print(f"  file_id  : {file_id}")
    print(f"  请求数   : {(batch.get('request_counts') or {}).get('total', len(comments))}")
    print()
    print(f"后续: GET {BATCHES_URL}/{batch_id} 查询进度;status=completed 后")
    print(f"用 {FILES_URL}/<output_file_id>/content 下载结果(custom_id 与输入一一对应)。")


if __name__ == "__main__":
    main()
