#!/usr/bin/env python3
"""用智谱 Batch API 批量推理对 comments.txt 里的用户评论做情感分类。

流程：读取同目录 comments.txt -> 构造 .jsonl 请求文件 -> 上传（purpose=batch）
-> 创建 batch 任务 -> 打印 batch 任务 id（不等待任务跑完）。

模型策略（重要）：
    Batch API 有一份独立的模型白名单，旗舰 glm-5.3 不在其中，且校验发生在
    文件上传阶段（业务错误码 1210"模型名称错误"），不是创建 batch 时才报。
    因此脚本先按计划用 glm-5.3 上传；若报 1210 则自动降级到白名单内
    质量最强的 glm-5.1（其后依次 glm-5-turbo、glm-4-plus 兜底），
    并在输出里说明做了什么调整。

用法：
    export ZHIPUAI_API_KEY=...
    python3 main.py
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
COMMENTS_FILE = Path(__file__).resolve().parent / "comments.txt"
JSONL_FILENAME = "batch_requests.jsonl"
# Batch 任务内每个请求的端点，创建任务时 endpoint 参数须与之一致
CHAT_ENDPOINT = "/v4/chat/completions"

# 按质量排序的候选模型：首选用户指定的旗舰 glm-5.3；
# 其余是 Batch 白名单内（实测可用）的降级选项
MODEL_CANDIDATES = ["glm-5.3", "glm-5.1", "glm-5-turbo", "glm-4-plus"]

SYSTEM_PROMPT = (
    "你是情感分类器。对给出的用户评论进行情感分类，"
    "只输出以下三个标签之一：正面、负面、中性。不要输出任何解释或其他内容。"
)


def read_comments(path: Path) -> list:
    """读取评论文件，每行一条；去掉空行和首尾空白。"""
    if not path.is_file():
        sys.exit(f"找不到评论文件：{path}")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        sys.exit(f"{path} 不是 UTF-8 编码，请转存为 UTF-8 后重试")
    comments = [line.strip() for line in lines if line.strip()]
    if not comments:
        sys.exit(f"{path} 里没有有效评论（空文件或全是空行）")
    return comments


def build_jsonl_bytes(comments: list, model: str) -> bytes:
    """把评论列表构造成 Batch 输入文件的字节流，每行一个独立请求。

    custom_id 用 request-001 格式：Batch 要求最短 6 字符，短了上传就报 1214。
    """
    lines = []
    for i, comment in enumerate(comments, 1):
        request = {
            "custom_id": f"request-{i:03d}",
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


def http(method: str, url: str, *, tries: int = 3, **kwargs):
    """带简单重试的请求封装：网络异常 / 5xx 退避重试，其余原样返回。"""
    kwargs.setdefault("timeout", (10, 120))
    for attempt in range(1, tries + 1):
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            if attempt == tries:
                sys.exit(f"网络请求失败（已重试 {tries} 次）：{url}\n{exc}")
            time.sleep(2 * attempt)
            continue
        if resp.status_code >= 500 and attempt < tries:
            time.sleep(2 * attempt)
            continue
        return resp


def api_error(payload: dict):
    """从响应体里提取业务错误 (code, message)，没有错误则返回 None。

    智谱接口出错时通常是 {"error": {"code": "1210", "message": ...}}，
    部分接口把 code/message 放在顶层，两种都兼容。
    """
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("code", "")), str(err.get("message", ""))
    code = payload.get("code")
    if code not in (None, "", 0, 200):
        return str(code), str(payload.get("message", ""))
    return None


def upload_jsonl(payload: bytes, headers: dict) -> str:
    """上传 .jsonl 请求文件（purpose=batch），返回文件 id。"""
    resp = http(
        "POST",
        f"{BASE_URL}/paas/v4/files",
        headers=headers,
        files={"file": (JSONL_FILENAME, payload, "application/json")},
        data={"purpose": "batch"},
    )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    err = api_error(body)
    if err is None and body.get("id"):
        return body["id"]
    code, message = err or (f"HTTP_{resp.status_code}", resp.text[:300])
    if code == "1210":
        # 模型不在 Batch 白名单（或 custom_id 等参数名非法）。对模型名问题
        # 的正确处理是换白名单内模型重试，而不是重试同一个模型
        raise ModelNotAllowedError(message)
    sys.exit(f"上传 Batch 请求文件失败（{code}）：{message}")


class ModelNotAllowedError(Exception):
    """模型不在 Batch 白名单内（上传阶段 1210 模型名称错误）。"""


def create_batch(input_file_id: str, headers: dict) -> dict:
    """基于已上传文件创建 batch 任务，返回 Batch 对象。"""
    resp = http(
        "POST",
        f"{BASE_URL}/paas/v4/batches",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "input_file_id": input_file_id,
            "endpoint": CHAT_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"description": "comments.txt 用户评论情感分类"},
        },
    )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    err = api_error(body)
    if err is None and body.get("id"):
        return body
    code, message = err or (f"HTTP_{resp.status_code}", resp.text[:300])
    sys.exit(f"创建 Batch 任务失败（{code}）：{message}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）")

    comments = read_comments(COMMENTS_FILE)
    print(f"已读取 {len(comments)} 条评论（{COMMENTS_FILE.name}）")

    headers = {"Authorization": f"Bearer {api_key}"}

    # 依次尝试候选模型：撞上"模型不在 Batch 白名单"（1210）就降级到下一个
    used_model = None
    input_file_id = None
    for model in MODEL_CANDIDATES:
        if used_model is not None:
            print(f"\n[降级重试] 改用白名单内候选：{model} ...")
        payload = build_jsonl_bytes(comments, model)
        print(f"正在构造并上传请求文件（model={model}，{len(comments)} 个请求）...")
        try:
            input_file_id = upload_jsonl(payload, headers)
            used_model = model
            break
        except ModelNotAllowedError as exc:
            print(f"[警告] {model} 上传被拒（1210 模型名称错误）：{exc}")
            print(
                "       Batch API 只支持一份独立的模型白名单（校验发生在文件上传阶段），"
                "旗舰模型不在其中。上面报错信息里列出的即当前完整白名单。"
            )

    if used_model is None:
        sys.exit(
            "所有候选模型都不在 Batch 白名单内，任务未能创建。"
            "请把上面报错信息里的白名单发给维护者，更新 MODEL_CANDIDATES 后重试。"
        )

    if used_model != MODEL_CANDIDATES[0]:
        print(
            f"\n[调整说明] 计划用旗舰模型 {MODEL_CANDIDATES[0]}，但 Batch 白名单不接受它，"
            f"已自动改用 {used_model}（白名单内质量最强的选择）。\n"
            f"            若必须要 {MODEL_CANDIDATES[0]} 的分类质量，只能放弃 Batch 半价，"
            f"改走同步/异步 chat completions 接口逐条调用。"
        )

    print(f"上传成功：input_file_id = {input_file_id}")

    batch = create_batch(input_file_id, headers)
    # request_counts 是嵌套对象，不是顶层字段
    counts = batch.get("request_counts") or {}

    print("\n===== Batch 任务创建成功 =====")
    print(f"batch_id : {batch['id']}")
    print(f"status   : {batch.get('status')}")
    print(f"model    : {used_model}")
    print(f"请求数   : {counts.get('total')}")
    print(f"查询进度 : GET {BASE_URL}/paas/v4/batches/{batch['id']}")
    print("任务完成后用 output_file_id 下载结果（本次脚本不等待）")


if __name__ == "__main__":
    main()
