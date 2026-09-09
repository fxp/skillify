#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱开放平台（bigmodel.cn）Batch API 批量做评论情感分类。

流程：读取同目录 comments.txt（每行一条评论） -> 构造 jsonl 请求文件
-> 上传（purpose=batch） -> 创建 batch 任务 -> 打印任务 id（不等待跑完）。

运行方式：
    ZHIPUAI_API_KEY=你的key python3 main.py
依赖：仅 requests。

关于模型的说明（重要）：
Batch 有一份独立于平台的模型白名单，且校验发生在**文件上传**阶段——不在白名单里的
模型会直接报业务码 1210「模型名称错误」，白名单本身只出现在这条报错信息里。
截至 2026-09 实测，旗舰 glm-5.3 不在白名单内，白名单中质量最强的是 glm-5.1。
因此本脚本按优先级依次尝试 ["glm-5.3", "glm-5.1"]：优先满足"用最好模型"的要求，
若 glm-5.3 在上传阶段被 1210 拒绝，则自动降级到 glm-5.1 把任务跑成，并明确告知。
若日后平台把 glm-5.3 放进白名单，脚本会直接用 glm-5.3，无需改动。
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
CHAT_ENDPOINT = "/v4/chat/completions"  # Batch 的 endpoint 字段目前唯一支持的取值
UPLOAD_TIMEOUT = 120   # 秒
CREATE_TIMEOUT = 30    # 秒

# 候选模型按质量优先排序；首个上传成功的生效
CANDIDATE_MODELS = ["glm-5.3", "glm-5.1"]

# 单个 batch 文件上限：50000 条请求、100MB（此处只校验条数）
MAX_REQUESTS_PER_BATCH = 50000

SYSTEM_PROMPT = (
    "你是评论情感分类器。判断给定评论的情感倾向，"
    "只输出以下三个标签之一：正面、负面、中性。不要输出任何其他内容。"
)


class ZhipuApiError(RuntimeError):
    """携带智谱业务错误码的 API 异常。"""

    def __init__(self, code, message, http_status):
        self.code = str(code) if code is not None else None
        self.message = message
        self.http_status = http_status
        super().__init__(f"HTTP {http_status} 业务码 {self.code}: {message}")


def extract_api_error(payload):
    """挖出业务错误码与消息；兼容 {"error":{code,message}} 和顶层 code/message 两种形态。"""
    if not isinstance(payload, dict):
        return None, ""
    err = payload.get("error")
    if isinstance(err, dict):
        return err.get("code"), err.get("message") or ""
    if "code" in payload or "message" in payload:
        return payload.get("code"), payload.get("message") or ""
    return None, ""


def check_response(resp):
    """校验响应：HTTP 非 2xx、或响应体带业务错误码（部分接口 200 也带错误码）时抛异常。"""
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    code, message = extract_api_error(payload)
    if resp.ok and (code is None or str(code) in {"0", "200"}):
        return payload
    detail = message or (json.dumps(payload, ensure_ascii=False) if payload else resp.text[:500])
    raise ZhipuApiError(code if code is not None else resp.status_code, detail, resp.status_code)


def load_comments():
    """读取脚本同目录的 comments.txt，每行一条，忽略空行。"""
    path = Path(__file__).resolve().parent / "comments.txt"
    if not path.is_file():
        sys.exit(f"错误：找不到评论文件 {path}（应与 main.py 放在同一目录，每行一条评论）")
    # utf-8-sig 兼容带 BOM 的文本
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    comments = [line.strip() for line in lines if line.strip()]
    if not comments:
        sys.exit(f"错误：{path} 里没有非空评论")
    if len(comments) > MAX_REQUESTS_PER_BATCH:
        sys.exit(
            f"错误：{len(comments)} 条评论超出单个 batch 文件 {MAX_REQUESTS_PER_BATCH} 条的上限，"
            f"请拆分成多个文件分批提交"
        )
    return comments


def build_jsonl(comments, model):
    """构造 Batch 请求 jsonl（bytes）。custom_id 用 request-NNNNNN，远超 6 字符下限。"""
    lines = []
    for i, comment in enumerate(comments, 1):
        request = {
            "custom_id": f"request-{i:06d}",  # Batch 要求 custom_id 最短 6 字符，短了上传即报错
            "method": "POST",
            "url": CHAT_ENDPOINT,
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": comment},
                ],
                "temperature": 0.1,
            },
        }
        lines.append(json.dumps(request, ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8")


def upload_batch_file(api_key, content):
    """上传 jsonl（purpose 必须是 batch），返回文件 id。模型白名单校验就发生在这一步。"""
    resp = requests.post(
        f"{BASE_URL}/paas/v4/files",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": ("batch_requests.jsonl", content, "application/json")},
        data={"purpose": "batch"},
        timeout=UPLOAD_TIMEOUT,
    )
    payload = check_response(resp)
    file_id = payload.get("id")
    if not file_id:
        raise ZhipuApiError(None, f"上传响应中没有文件 id: {payload}", resp.status_code)
    return file_id


def create_batch(api_key, input_file_id, model):
    """创建 batch 任务，返回 Batch 对象。"""
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "input_file_id": input_file_id,
            "endpoint": CHAT_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"description": "comments.txt 评论情感分类", "model": model},
        },
        timeout=CREATE_TIMEOUT,
    )
    payload = check_response(resp)
    if not payload.get("id"):
        raise ZhipuApiError(None, f"创建响应中没有任务 id: {payload}", resp.status_code)
    return payload


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）")

    comments = load_comments()
    print(f"已读取 {len(comments)} 条评论")

    # 依次尝试候选模型：glm-5.3 不在 Batch 白名单时，上传阶段即报 1210，自动降级
    file_id = None
    used_model = None
    for model in CANDIDATE_MODELS:
        content = build_jsonl(comments, model)
        try:
            file_id = upload_batch_file(api_key, content)
        except ZhipuApiError as exc:
            # custom_id 长度已保证合法，此处 1210 只会是模型不在 Batch 白名单
            if exc.code == "1210" and model != CANDIDATE_MODELS[-1]:
                print(f"[降级] {model} 不在 Batch 模型白名单内（{exc.message}），尝试下一候选…")
                continue
            raise
        used_model = model
        break

    if file_id is None:
        sys.exit("错误：所有候选模型都被 Batch 拒绝。请从上方报错信息里的白名单中选一个模型改 CANDIDATE_MODELS")

    print(f"请求文件上传成功：{file_id}（模型 {used_model}）")

    batch = create_batch(api_key, file_id, used_model)
    # 注意：计数字段是嵌套的 request_counts.{total,completed,failed}，不是顶层字段
    total = (batch.get("request_counts") or {}).get("total")
    print("Batch 任务创建成功：")
    print(f"  batch id : {batch['id']}")
    print(f"  status   : {batch.get('status')}")
    print(f"  模型     : {used_model}")
    print(f"  请求数   : {total if total is not None else len(comments)}")
    print("任务为异步执行（一般 24 小时内完成），稍后可用 GET /paas/v4/batches/{batch_id} 查询进度。")


if __name__ == "__main__":
    try:
        main()
    except ZhipuApiError as exc:
        sys.exit(f"API 调用失败：{exc}")
    except requests.RequestException as exc:
        sys.exit(f"网络请求失败：{exc}")
