#!/usr/bin/env python3
"""用智谱（bigmodel.cn）Batch API 批量做评论情感分类。

流程：读同目录 comments.txt（每行一条评论）→ 构造 jsonl 请求文件 →
上传（purpose=batch）→ 创建 batch 任务 → 打印 batch 任务 id（不等待跑完）。

模型说明（重要）：
    Batch API 有一份独立的模型白名单，旗舰 glm-5.3 目前不在其中——
    校验发生在文件上传阶段，整份文件会被 1210「模型名称错误」拒绝。
    白名单会随平台更新变化，所以本脚本按质量从高到低依次尝试：
        glm-5.3（用户首选，若已进白名单则直接用）
        glm-5.1（白名单内质量最强的模型，实测 2026-09）
        glm-4-plus（再兜底）
    哪个模型被拒、最终用了哪个，运行时都会打印出来。

API Key 从环境变量 ZHIPUAI_API_KEY 读取。仅依赖 requests。
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
SCRIPT_DIR = Path(__file__).resolve().parent
COMMENTS_FILE = SCRIPT_DIR / "comments.txt"

# 按分类质量从高到低排列的候选链；上传/建任务阶段被"模型类"错误拒绝时自动降级。
MODEL_CANDIDATES = ["glm-5.3", "glm-5.1", "glm-4-plus"]

BATCH_ENDPOINT = "/v4/chat/completions"  # Batch 目前仅支持这一种 endpoint
TEMPERATURE = 0.1
# 思考模型的推理 token 也计入 max_tokens，预算不足会得到空内容（finish_reason=length），
# 分类任务给 2048 足够覆盖思考 + 一个 JSON 对象。
MAX_TOKENS = 2048

SYSTEM_PROMPT = (
    "你是一个情感分类器。判断用户评论的情感倾向，标签只能从「正面」「负面」「中性」"
    "三个词中选一个。输出必须只是一个 JSON 对象，形如 {\"sentiment\": \"<标签>\"}，"
    "不要输出任何解释或多余文字。"
)
USER_PROMPT_TEMPLATE = (
    "请对下面这条用户评论做情感分类，只输出一个 JSON 对象 "
    "{\"sentiment\": \"正面|负面|中性\"}，不要有任何其他文字。\n\n评论：{comment}"
)
# 注意：模板里含 JSON 字面量的花括号，不能用 str.format()（会把 {"sentiment"} 当占位符），
# 只能用 replace 填充。

# 可重试：限流/过载（1302/1305）与 5xx、网络抖动；重试无意义的 4xx 直接抛。
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3


class FatalApiError(Exception):
    """配置/鉴权/余额等重试与换模型都无法解决的问题。"""


class ModelRejectedError(Exception):
    """当前模型不在 Batch 白名单（或模型名非法），应尝试候选链中的下一个。"""

    def __init__(self, model, code, message):
        super().__init__(f"模型 {model} 被拒绝: [{code}] {message}")
        self.model = model
        self.code = code
        self.message = message


def extract_error(resp):
    """从响应里取业务错误码和消息（错误体形如 {"error":{"code":"1210","message":...}}）。

    返回 (code, message)；没有错误体时返回 (None, resp.text[:200])。
    """
    try:
        body = resp.json()
    except ValueError:
        return None, (resp.text or "")[:200]
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("code")), str(err.get("message", ""))
    # 部分接口把 code/message 平铺在顶层
    if "code" in body and "message" in body and str(body.get("code")) != "200":
        return str(body.get("code")), str(body.get("message", ""))
    return None, ""


def is_model_rejection(code, message):
    """判定是否"模型不被 Batch 接受"这类错误（换模型重试才有意义）。"""
    if code not in {"1210", "1211"}:  # 1210 参数有误(含模型名称错误) / 1211 模型不存在
        return False
    text = message.lower()
    return "模型" in message or "model" in text


def raise_for_fatal(resp, action):
    """把不可重试的 4xx 转成带上下文的 FatalApiError。"""
    code, message = extract_error(resp)
    if resp.status_code == 401:
        raise FatalApiError(
            f"{action} 鉴权失败（HTTP {resp.status_code}, [{code}] {message}）："
            "请检查环境变量 ZHIPUAI_API_KEY 是否为有效的标准 API Key。"
        )
    if resp.status_code == 429 and code == "1113":
        raise FatalApiError(
            f"{action} 余额不足（HTTP 429, [{code}] {message}）。注意：若手里是 "
            "GLM Coding Plan 套餐 Key，它不含 Batch 能力且不能打标准端点，"
            "需要用标准 API Key。"
        )
    raise FatalApiError(f"{action} 失败：HTTP {resp.status_code}, [{code}] {message}")


def request_with_retry(method, url, action, timeout=60, **kwargs):
    """带指数退避的请求：仅对限流/5xx/网络错误重试，4xx 直接返回响应。"""
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
        else:
            if resp.status_code not in RETRYABLE_STATUS:
                return resp
            last_exc = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if attempt < MAX_RETRIES:
            wait = 2 ** attempt
            print(f"  ! {action} 触发重试（{last_exc}），{wait}s 后重试 "
                  f"({attempt + 1}/{MAX_RETRIES})...")
            time.sleep(wait)
    raise FatalApiError(f"{action} 重试 {MAX_RETRIES} 次后仍失败：{last_exc}")


def read_comments(path):
    """读取评论文件，每行一条；跳过空行，返回 (行号, 评论原文) 列表。"""
    if not path.exists():
        raise FatalApiError(f"找不到评论文件：{path}（应与 main.py 放在同一目录）")
    comments = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if line:
                comments.append((lineno, line))
    if not comments:
        raise FatalApiError(f"评论文件是空的：{path}")
    return comments


def build_request_lines(model, comments):
    """构造 Batch 的 jsonl 请求行。

    注意两个实测坑：custom_id 有未文档化的 6 字符下限（用 request-0001 这种格式）；
    response_format 的 json_schema 会被静默忽略，所以用 json_object + prompt 写清结构。
    """
    lines = []
    for lineno, comment in comments:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",
                 "content": USER_PROMPT_TEMPLATE.replace("{comment}", comment)},
            ],
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "response_format": {"type": "json_object"},
        }
        lines.append({
            "custom_id": f"request-l{lineno:04d}",
            "method": "POST",
            "url": BATCH_ENDPOINT,
            "body": body,
        })
    return lines


def check_upload_response(resp):
    """上传接口的业务错误检查；模型被拒时抛 ModelRejectedError。"""
    code, message = extract_error(resp)
    if resp.status_code >= 400 or code:
        if is_model_rejection(code, message):
            raise ModelRejectedError("（上传阶段）", code, message)
        raise_for_fatal(resp, "上传请求文件")
    return resp.json()["id"]


def upload_batch_file(model, comments):
    """构造 jsonl 并上传（purpose 必须是 batch），返回 file_id。"""
    lines = build_request_lines(model, comments)
    payload = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    resp = request_with_retry(
        "POST",
        f"{BASE_URL}/paas/v4/files",
        "上传请求文件",
        headers={"Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}"},
        files={"file": ("batch_requests.jsonl", payload.encode("utf-8"),
                        "application/x-ndjson")},
        data={"purpose": "batch"},
    )
    return check_upload_response(resp)


def create_batch(file_id):
    """基于已上传的文件创建 batch 任务，返回 batch 对象。"""
    resp = request_with_retry(
        "POST",
        f"{BASE_URL}/paas/v4/batches",
        "创建 batch 任务",
        timeout=30,
        headers={
            "Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "input_file_id": file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"description": "comments.txt 情感分类"},
        },
    )
    code, message = extract_error(resp)
    if resp.status_code >= 400 or code:
        if is_model_rejection(code, message):
            raise ModelRejectedError("（创建任务阶段）", code, message)
        raise_for_fatal(resp, "创建 batch 任务")
    return resp.json()


def delete_file_quietly(file_id):
    """创建任务失败时清理刚上传的输入文件，尽力而为，不影响主流程。"""
    try:
        request_with_retry(
            "DELETE",
            f"{BASE_URL}/paas/v4/files/{file_id}",
            "清理输入文件",
            timeout=30,
            headers={"Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}"},
        )
    except Exception as exc:  # noqa: BLE001 - 清理失败只提示
        print(f"  ! 清理未使用的输入文件 {file_id} 失败（可忽略）：{exc}")


def run_with_model(model, comments):
    """用指定模型走完 上传→创建任务，成功返回 (file_id, batch)。"""
    file_id = upload_batch_file(model, comments)
    try:
        batch = create_batch(file_id)
    except ModelRejectedError:
        delete_file_quietly(file_id)
        raise
    except Exception:
        delete_file_quietly(file_id)
        raise
    return file_id, batch


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY（智谱标准 API Key）。", file=sys.stderr)
        sys.exit(1)

    comments = read_comments(COMMENTS_FILE)
    print(f"已读取 {len(comments)} 条评论（{COMMENTS_FILE}）")

    used_model = None
    batch = None
    for idx, model in enumerate(MODEL_CANDIDATES, start=1):
        print(f"\n[{idx}/{len(MODEL_CANDIDATES)}] 尝试模型 {model} ...")
        try:
            file_id, batch = run_with_model(model, comments)
        except ModelRejectedError as exc:
            print(f"  ✗ {model} 不可用 {exc.code} {exc.message}")
            print(f"    → 原因：Batch 有一份独立模型白名单，旗舰 glm-5.3 不在其中，"
                  f"且校验发生在文件上传阶段。自动降级到下一个候选。")
            continue
        used_model = model
        print(f"  ✓ 请求文件上传成功：{file_id}")
        break

    if batch is None:
        print("\n错误：候选模型全部被拒，无法创建 batch 任务。", file=sys.stderr)
        sys.exit(1)

    print("\n==================================================")
    print("Batch 任务创建成功（无需等待跑完）")
    print(f"  实际使用模型 : {used_model}")
    if used_model != MODEL_CANDIDATES[0]:
        print(f"  说明 : 首选 {MODEL_CANDIDATES[0]} 被 Batch 模型白名单拒绝，"
              f"已自动降级为白名单内质量最强的 {used_model}")
    print(f"  输入文件     : {batch.get('input_file_id')}")
    print(f"  请求条数     : {batch.get('request_counts', {}).get('total')}")
    print(f"  当前状态     : {batch.get('status')}")
    print(f"  batch 任务 id : {batch.get('id')}")
    print("==================================================")
    print(f"\nbatch_id={batch.get('id')}")


if __name__ == "__main__":
    try:
        main()
    except FatalApiError as exc:
        print(f"\n错误：{exc}", file=sys.stderr)
        sys.exit(1)
