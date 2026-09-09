#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱（bigmodel.cn）Batch API 批量做评论情感分类。

读取脚本同目录下的 comments.txt（每行一条评论），构造 batch 请求 jsonl，
上传（purpose=batch）后创建 batch 任务，打印创建成功的任务 id（不等待跑完）。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

模型策略（为什么不是直接写死 glm-5.3）：
    Batch API 有一份独立于平台整体的模型白名单，旗舰 glm-5.3 目前不在名单内——
    不是等到创建任务才失败，而是在上传 jsonl 文件这一步整份就被拒绝
    （业务错误码 1210：模型名称错误）。
    因此脚本按候选列表逐个尝试：先按需求用 glm-5.3；被 1210 拒绝时自动降级，
    默认会落到 glm-5.1（白名单内质量最强的模型，尽量保住分类质量）。
    若日后 glm-5.3 进入白名单，脚本无需改动即自动优先使用它。
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
FILES_ENDPOINT = f"{BASE_URL}/paas/v4/files"
BATCHES_ENDPOINT = f"{BASE_URL}/paas/v4/batches"
# jsonl 每行的 url 必须与创建 batch 时的 endpoint 完全一致，目前仅支持此值
BATCH_CHAT_ENDPOINT = "/v4/chat/completions"

# 按质量排序的候选模型：glm-5.3 是需求指定的首选；其余都在 Batch 实测白名单内，
# glm-5.1 是其中最强的，作为质量优先的降级目标。
MODEL_CANDIDATES = ["glm-5.3", "glm-5.1", "glm-5-turbo", "glm-4-plus"]

# 上传阶段"模型不在 Batch 白名单 / 模型名称错误"的业务错误码，触发降级重试
MODEL_REJECTED_CODE = "1210"

SYSTEM_PROMPT = (
    "你是评论情感分类器。对用户给出的每条评论，只输出一个分类标签："
    "正面、负面 或 中性。不要输出任何解释或其他内容。"
)

TIMEOUT = 60


class ZhipuApiError(RuntimeError):
    """智谱接口返回的业务错误（HTTP 非 2xx，或响应体里带错误信息）。"""

    def __init__(self, code, message, status_code=None):
        super().__init__(f"[{code}] {message}" if code else message)
        self.code = str(code or "")
        self.message = message
        self.status_code = status_code


def parse_response(resp):
    """统一解析响应：成功返回 JSON dict，失败抛 ZhipuApiError。

    兼容两种错误形状：{"error": {"code": ..., "message": ...}} 与顶层 {"code": ..., "message": ...}。
    """
    try:
        body = resp.json()
    except ValueError:
        body = None

    body_error = isinstance(body, dict) and isinstance(body.get("error"), dict)
    if resp.ok and not body_error:
        return body if isinstance(body, dict) else {}

    code, message = "", f"HTTP {resp.status_code}: {resp.text[:200]}"
    if body_error:
        code = body["error"].get("code", "")
        message = body["error"].get("message", "") or message
    elif isinstance(body, dict):
        code = body.get("code", "") or ""
        message = body.get("message", "") or message
    raise ZhipuApiError(code, message, resp.status_code)


def read_comments(path):
    if not path.is_file():
        sys.exit(f"错误：找不到评论文件：{path}")
    # utf-8-sig 兼容带 BOM 的文件
    comments = [ln.strip() for ln in path.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    if not comments:
        sys.exit(f"错误：{path} 中没有读到任何评论")
    return comments


def build_batch_jsonl(comments, model):
    """每条评论 -> 一行 batch 请求。

    custom_id 必须唯一且不少于 6 个字符（短的会在上传阶段直接被拒），这里用 request-00001 格式。
    """
    lines = []
    for seq, comment in enumerate(comments, start=1):
        lines.append(json.dumps({
            "custom_id": f"request-{seq:05d}",
            "method": "POST",
            "url": BATCH_CHAT_ENDPOINT,
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"评论：{comment}"},
                ],
                "temperature": 0.1,  # 分类任务要稳定，不要发散
            },
        }, ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8")


def upload_batch_file(api_key, content, filename):
    resp = requests.post(
        FILES_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": (filename, content, "application/json")},
        data={"purpose": "batch"},  # 给 Batch 用的文件 purpose 必须是 batch
        timeout=TIMEOUT,
    )
    file_obj = parse_response(resp)
    if not file_obj.get("id"):
        raise ZhipuApiError("", f"上传返回中缺少文件 id：{file_obj}")
    return file_obj


def create_batch(api_key, input_file_id, model, n_requests):
    resp = requests.post(
        BATCHES_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "input_file_id": input_file_id,
            "endpoint": BATCH_CHAT_ENDPOINT,
            "auto_delete_input_file": False,  # 保留输入文件，便于事后核对
            "metadata": {
                "description": "comments.txt 情感分类",
                "model": model,
                "requests": str(n_requests),
            },
        },
        timeout=TIMEOUT,
    )
    batch = parse_response(resp)
    if not batch.get("id"):
        raise ZhipuApiError("", f"创建 batch 返回中缺少任务 id：{batch}")
    return batch


def submit(api_key, comments):
    """按候选列表上传 batch 请求文件，返回 (使用的模型, 文件 id)。

    glm-5.3 被 Batch 白名单拒绝（1210）时自动降级到下一个候选，并把原因打印出来。
    """
    last_error = None
    for model in MODEL_CANDIDATES:
        content = build_batch_jsonl(comments, model)
        print(f"尝试模型 {model}：构造 jsonl（{len(comments)} 个请求）并上传 ...")
        try:
            file_obj = upload_batch_file(api_key, content, f"sentiment-{model}.jsonl")
        except ZhipuApiError as exc:
            last_error = exc
            if exc.code == MODEL_REJECTED_CODE:
                print(f"  被拒绝（{exc}）——该模型不在 Batch 白名单，按候选列表降级重试")
                continue
            raise  # 鉴权/网络/其他业务错误：换模型也解决不了，直接抛出
        return model, file_obj["id"]
    # 所有候选都被白名单拒绝：抛出最后一次的报错原文，便于排查
    raise last_error


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY（先 export ZHIPUAI_API_KEY=你的Key）")

    comments_path = Path(__file__).resolve().parent / "comments.txt"
    comments = read_comments(comments_path)
    print(f"已读取 {len(comments)} 条评论：{comments_path}")

    try:
        model, file_id = submit(api_key, comments)
    except ZhipuApiError as exc:
        sys.exit(f"错误：智谱接口返回失败：{exc}")

    print(f"上传成功：input_file_id = {file_id}")
    if model != MODEL_CANDIDATES[0]:
        print(f"注意：首选模型 {MODEL_CANDIDATES[0]} 不被 Batch 接受（不在白名单），"
              f"已改用 {model}（白名单内质量最强的候选）")

    print("创建 batch 任务 ...")
    try:
        batch = create_batch(api_key, file_id, model, len(comments))
    except ZhipuApiError as exc:
        sys.exit(f"错误：创建 batch 任务失败：{exc}")

    # request_counts 是嵌套对象（{"total": .., "completed": .., "failed": ..}），不是顶层字段
    total = (batch.get("request_counts") or {}).get("total")
    print("Batch 任务创建成功（不需要等它跑完）。")
    print(f"  batch 任务 id：{batch['id']}")
    print(f"  状态：{batch.get('status')}")
    print(f"  模型：{model}，共 {total if total is not None else len(comments)} 个请求")
    print(f"  之后可用该 id 轮询进度：GET {BATCHES_ENDPOINT}/{batch['id']}")


if __name__ == "__main__":
    main()
