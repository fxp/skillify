#!/usr/bin/env python3
"""用智谱 Batch API 批量对 comments.txt 里的用户评论做情感分类。

流程：构造 jsonl 请求文件 -> 上传（purpose=batch）-> 创建 batch 任务 -> 打印任务 id。
不轮询、不等结果（结果文件保留 30 天，之后可用 GET /paas/v4/batches/{id} 查询）。

模型策略（重要）：
    Batch 有一份独立于平台整体的模型白名单，校验发生在**文件上传**这一步，
    白名单外的模型直接报业务错误码 1210「模型名称错误」。
    截至 2026-09 实测，旗舰 glm-5.3 不在白名单内；白名单内质量最强的是 glm-5.1。
    因此按 MODEL_PREFERENCE 依次试探：先按用户要求试 glm-5.3，
    若上传被 1210 拒绝则自动降级到下一个模型（白名单日后更新时本脚本无需改动）。

踩坑规避（来自实测，非官方文档）：
    - custom_id 有未文档化的 6 字符下限，这里用 request-0001 格式；
    - 不设 max_tokens：思考类模型的推理 token 计入 max_tokens，预算给小会得到
      finish_reason=length + 空 content，干脆不限制；
    - 不用 response_format/json_schema 约束输出（会被静默忽略），改为在
      prompt 里写死输出格式。
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
CHAT_ENDPOINT = "/v4/chat/completions"  # jsonl 每行的 url 须与 batch 的 endpoint 一致

# 按质量优先排序的候选模型；遇 1210（模型不在 Batch 白名单）时依次降级。
MODEL_PREFERENCE = ["glm-5.3", "glm-5.1", "glm-5-turbo", "glm-4-plus", "glm-4-air"]

SYSTEM_PROMPT = (
    "你是评论情感分类器。把给定的用户评论分为：正面、负面、中性 三类。"
    "只输出这三个词中的一个作为分类标签，不要输出任何解释或其他内容。"
)

SCRIPT_DIR = Path(__file__).resolve().parent
COMMENTS_FILE = SCRIPT_DIR / "comments.txt"
REQUESTS_FILE = SCRIPT_DIR / "batch_requests.jsonl"


class ApiError(Exception):
    """智谱业务错误（body 里带 code/msg，HTTP 状态码不一定能反映）。"""

    def __init__(self, code, message, http_status=None):
        self.code = str(code) if code is not None else None
        self.message = message
        self.http_status = http_status
        super().__init__(f"[{self.code}] {self.message}")


def parse_api_response(resp):
    """统一解析响应：HTTP 失败或 body 带错误码时抛 ApiError，否则返回 body dict。"""
    try:
        payload = resp.json()
    except ValueError:
        raise ApiError(None, f"HTTP {resp.status_code}，响应不是 JSON：{resp.text[:300]}", resp.status_code)
    # 兼容 {"error":{"code","message"}} 与 {"code","msg"} 两种错误体
    err = payload.get("error") or {}
    code = payload.get("code", err.get("code"))
    msg = payload.get("msg") or payload.get("message") or err.get("message")
    if code not in (None, 0, "0", 200, "200", "success"):
        raise ApiError(code, msg or json.dumps(payload, ensure_ascii=False)[:300], resp.status_code)
    if not resp.ok:
        raise ApiError(code, f"HTTP {resp.status_code}：{msg or resp.text[:300]}", resp.status_code)
    return payload


def read_comments(path):
    if not path.exists():
        sys.exit(f"错误：找不到评论文件 {path}")
    comments = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not comments:
        sys.exit(f"错误：{path} 里没有有效评论")
    return comments


def build_requests_file(comments, model):
    """把每条评论写成一个独立的 chat/completions 请求行。"""
    with REQUESTS_FILE.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, 1):
            request = {
                # custom_id 最短 6 字符，短了上传阶段就报 1214
                "custom_id": f"request-{i:04d}",
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
            f.write(json.dumps(request, ensure_ascii=False) + "\n")


def upload_requests_file(api_key):
    """上传 jsonl（purpose 必须是 batch），返回文件 id。

    模型白名单校验就发生在这一步。
    """
    with REQUESTS_FILE.open("rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (REQUESTS_FILE.name, f)},
            data={"purpose": "batch"},
            timeout=120,
        )
    payload = parse_api_response(resp)
    return payload["id"]


def create_batch(api_key, input_file_id, model):
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "input_file_id": input_file_id,
            "endpoint": CHAT_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"description": "用户评论情感分类", "model": model},
        },
        timeout=60,
    )
    return parse_api_response(resp)


def pick_model_and_upload(api_key, comments):
    """按偏好依次尝试模型：1210「模型名称错误」→ 降级；其他错误 → 立即终止。"""
    last_model_error = None
    for model in MODEL_PREFERENCE:
        build_requests_file(comments, model)
        try:
            file_id = upload_requests_file(api_key)
            return model, file_id
        except ApiError as e:
            if e.code == "1210" and "模型" in (e.message or ""):
                print(f"  模型 {model} 不在 Batch 白名单（1210 {e.message}），尝试降级……")
                last_model_error = e
                continue
            raise  # 鉴权/网络/文件等其他问题，降级救不了
    # 全部候选都被拒：报错信息里带有平台回传的完整白名单，原样转述给用户
    sys.exit(
        f"错误：候选模型 {MODEL_PREFERENCE} 全部被 Batch 拒绝。"
        f"最后一次报错：{last_model_error}。"
        "平台报错信息里包含当前完整的 Batch 模型白名单，请据此更换 MODEL_PREFERENCE。"
    )


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")

    comments = read_comments(COMMENTS_FILE)
    print(f"读取到 {len(comments)} 条评论：{COMMENTS_FILE}")

    model, file_id = pick_model_and_upload(api_key, comments)
    print(f"请求文件已上传：{REQUESTS_FILE.name} -> file id {file_id}（模型 {model}）")

    batch = create_batch(api_key, file_id, model)
    counts = batch.get("request_counts") or {}
    print()
    print(f"Batch 任务创建成功！")
    print(f"  batch id : {batch['id']}")
    print(f"  status   : {batch.get('status')}")
    print(f"  模型     : {model}（请求总数 {counts.get('total', len(comments))}）")
    print(f"  后续查询 : GET {BASE_URL}/paas/v4/batches/{batch['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
