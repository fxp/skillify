#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用智谱开放平台 Batch API 对 comments.txt 中的用户评论做情感分类。

流程: 读取评论 -> 构造 jsonl 请求 -> 上传文件(purpose=batch) -> 创建 batch 任务 -> 打印任务 id(不等跑完)

关于模型的重要说明(为什么不是直接 glm-5.3):
    Batch 只支持一份独立的模型白名单, 不是平台上全部模型; 旗舰 glm-5.3 不在白名单里,
    且校验发生在文件上传这一步(POST /paas/v4/files), 业务码 1210"模型名称错误"。
    因此本脚本先用 glm-5.3 尝试上传(白名单会随平台更新, 以报错为准), 若被 1210 拒绝,
    则解析报错信息里给出的白名单, 自动降级到白名单内质量最强的文本模型(首选 glm-5.1)
    重新构造并上传, 同时打印调整说明。这样即使用户指定模型不可用, 任务也能跑成。

运行: python3 main.py  (需设置环境变量 ZHIPUAI_API_KEY, comments.txt 与本脚本同目录)
依赖: 仅 requests
"""

import io
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
COMMENTS_FILE = Path(__file__).resolve().parent / "comments.txt"
JSONL_FILENAME = "batch_requests.jsonl"
MAX_REQUESTS_PER_BATCH = 50000  # 单个 batch 文件的请求数上限

# 质量优先的候选顺序: 旗舰在前; 被 Batch 白名单拒绝后按此顺序自动降级
PREFERRED_MODELS = [
    "glm-5.3",  # 用户指定的旗舰, 预期不在 Batch 白名单, 会触发 1210 后自动降级
    "glm-5.1",  # 实测白名单内质量最强的文本模型
    "glm-4-plus",
    "glm-4-0520",
    "glm-4",
    "glm-4-long",
    "glm-4-air",
    "glm-4-air-250414",
    "glm-4-flash",
    "glm-4-flashx-250414",
]

SYSTEM_PROMPT = (
    "你是用户评论情感分类器。对输入的一条评论判断情感倾向，"
    "只输出以下三个标签之一：正面、负面、中性。不要输出任何解释或其他内容。"
)

# 常见业务错误码的排查提示(来自实测, 帮助定位问题而不是只抛原始报错)
ERROR_HINTS = {
    "1000": "鉴权失败, 请检查 ZHIPUAI_API_KEY 是否为有效的标准 API Key。",
    "1001": "请求头缺少 Authorization, 请检查 ZHIPUAI_API_KEY 环境变量。",
    "1003": "API Key 过期或无效。",
    "1113": "余额不足或无可用资源包。注意: GLM Coding Plan 套餐 Key 不能打标准端点, 请使用标准 API Key。",
    "1211": "模型不存在, 请核对模型名拼写。",
}


def fail(msg):
    sys.exit(f"错误: {msg}")


def load_comments(path):
    """读取同目录 comments.txt, 每行一条评论; 跳过空行。"""
    if not path.is_file():
        fail(f"找不到评论文件 {path}, 请把 comments.txt 放到与本脚本相同的目录。")
    comments = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    comments = [c for c in comments if c]
    if not comments:
        fail(f"{path} 中没有非空的评论行。")
    if len(comments) > MAX_REQUESTS_PER_BATCH:
        fail(
            f"共 {len(comments)} 条评论, 超过单个 batch 文件 {MAX_REQUESTS_PER_BATCH} 条上限, "
            f"请拆分成多份分批提交。"
        )
    return comments


def build_jsonl(comments, model):
    """按 Batch 输入格式构造 jsonl 字节流, 每行一个独立的 chat/completions 请求。"""
    lines = []
    for i, comment in enumerate(comments, 1):
        # custom_id 有未文档化的 6 字符下限, 短了上传阶段就报 1210, 用 request-000001 格式
        request = {
            "custom_id": f"request-{i:06d}",
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"评论：{comment}"},
                ],
                "temperature": 0.1,
                # 思考 token 也计入 max_tokens 预算, 给足余量避免 finish_reason=length、正文为空
                "max_tokens": 2048,
            },
        }
        lines.append(json.dumps(request, ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8")


def http_request(method, url, *, tries=3, **kwargs):
    """带瞬时网络错误重试的请求封装(业务错误不在此重试, 由调用方处理)。"""
    kwargs.setdefault("timeout", 60)
    last_exc = None
    for attempt in range(1, tries + 1):
        try:
            return requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < tries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"请求 {url} 连续 {tries} 次失败: {last_exc}") from last_exc


def extract_api_error(resp):
    """提取业务错误体 {"error":{"code":...,"message":...}}; 非该结构返回 None。"""
    try:
        body = resp.json()
    except ValueError:
        return None
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        if "code" in err:
            return str(err["code"]), str(err.get("message", ""))
    return None


def die_on_api_error(stage, code, message):
    hint = ERROR_HINTS.get(code, "")
    fail(f"{stage}失败: 业务错误码 {code}: {message}{os.linesep}提示: {hint}" if hint
         else f"{stage}失败: 业务错误码 {code}: {message}")


def is_vision_model(name):
    """识别视觉模型命名, 如 glm-4v / glm-4v-plus / glm-5v-turbo / glm-4.6v。"""
    return any(re.fullmatch(r"\d+(?:\.\d+)?v", seg) for seg in name.split("-"))


def parse_whitelist(message):
    """从 1210 报错信息中解析 Batch 支持的模型白名单, 只保留 GLM 系文本对话模型。"""
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9]*(?:-[0-9a-zA-Z.\-]+)+", message)
    chat_models = []
    for token in tokens:
        name = token.lower().rstrip(".")
        # 过滤非 GLM 与视觉模型(cogview/cogvideox/embedding/glm-4v/glm-5v-*)
        if not name.startswith("glm") or is_vision_model(name):
            continue
        if name not in chat_models:
            chat_models.append(name)
    return chat_models


def order_by_preference(models):
    """按 PREFERRED_MODELS 的质量优先级排序(不在偏好表里的保持解析到的原始顺序靠后)。"""
    def rank(name):
        return (0, PREFERRED_MODELS.index(name)) if name in PREFERRED_MODELS else (1, 0)

    return sorted(models, key=rank)


def upload_with_model_fallback(comments, headers):
    """依次尝试候选模型上传 jsonl; 撞上 1210 模型白名单拒绝时自动降级并返回调整记录。"""
    requested_model = PREFERRED_MODELS[0]
    candidates = list(PREFERRED_MODELS)
    tried = set()
    adjustments = []

    while True:
        model = next((m for m in candidates if m not in tried), None)
        if model is None:
            fail("所有候选模型都被 Batch 白名单拒绝, 请把上方报错信息反馈给维护者。")
        tried.add(model)

        print(f"  上传请求文件 (model={model}, {len(comments)} 条) ...")
        resp = http_request(
            "POST",
            f"{BASE_URL}/paas/v4/files",
            headers=headers,
            files={"file": (JSONL_FILENAME, io.BytesIO(build_jsonl(comments, model)), "application/json")},
            data={"purpose": "batch"},
        )

        err = extract_api_error(resp)
        if err is None:
            if not resp.ok:
                fail(f"上传失败: HTTP {resp.status_code}: {resp.text[:300]}")
            file_id = resp.json().get("id")
            if not file_id:
                fail(f"上传返回异常(缺少文件 id): {resp.text[:300]}")
            return model, file_id, adjustments

        code, message = err
        is_model_rejection = code == "1210" and ("模型" in message or "model" in message.lower())
        if not is_model_rejection:
            # 例如 custom_id 过短也会报 1210, 但那不是换模型能解决的, 直接报出
            die_on_api_error("上传", code, message)

        print(f"  ! 上传被拒: 1210 {message}")
        whitelist = parse_whitelist(message)
        if model == requested_model:
            reason = (
                f"指定模型 {model} 不在 Batch 白名单内(白名单独立于平台模型列表, "
                f"校验发生在上传阶段), 已自动降级"
            )
        else:
            reason = f"降级模型 {model} 同样被拒, 继续降级"
        if whitelist:
            print(f"    报错给出的可用模型: {', '.join(whitelist)}")
            candidates = order_by_preference(whitelist)
            adjustments.append(
                f"{reason}; 按报错白名单改用质量优先的下一候选。"
            )
        else:
            adjustments.append(f"{reason}; 报错未给出白名单, 按内置偏好顺序重试。")
        # 不要重试刚被拒的模型, 回到循环取下一个候选


def create_batch(file_id, headers):
    """基于已上传文件创建 batch 任务, 返回 Batch 对象。"""
    resp = http_request(
        "POST",
        f"{BASE_URL}/paas/v4/batches",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "input_file_id": file_id,
            "endpoint": "/v4/chat/completions",
            # 保留输入文件便于核对结果; 平台 30 天后也会自动清理
            "auto_delete_input_file": False,
            "metadata": {"description": "用户评论情感分类", "source": "comments.txt"},
        },
    )
    err = extract_api_error(resp)
    if err is None and resp.ok:
        return resp.json()
    if err:
        code, message = err
        die_on_api_error("创建 batch 任务", code, message)
    fail(f"创建 batch 任务失败: HTTP {resp.status_code}: {resp.text[:300]}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("未设置环境变量 ZHIPUAI_API_KEY (标准 API Key), 请先 export ZHIPUAI_API_KEY=... 再运行。")
    headers = {"Authorization": f"Bearer {api_key}"}

    print(f"[1/3] 读取评论: {COMMENTS_FILE}")
    comments = load_comments(COMMENTS_FILE)
    print(f"      共 {len(comments)} 条非空评论")

    print("[2/3] 构造并上传 batch 请求文件 (期望模型 glm-5.3)")
    model, file_id, adjustments = upload_with_model_fallback(comments, headers)
    for note in adjustments:
        print(f"  [调整] {note}")
    print(f"      上传成功: {file_id} (实际使用模型 {model})")

    print("[3/3] 创建 batch 任务 ...")
    batch = create_batch(file_id, headers)
    batch_id = batch.get("id")
    if not batch_id:
        fail(f"创建返回异常(缺少任务 id): {json.dumps(batch, ensure_ascii=False)[:300]}")

    # 注意: 计数字段是嵌套的 request_counts.{total,completed,failed}, 不是顶层字段
    request_counts = batch.get("request_counts") or {}
    print()
    print("=" * 60)
    print("Batch 任务创建成功!")
    print(f"  任务 id   : {batch_id}")
    print(f"  初始状态 : {batch.get('status')}")
    print(f"  使用模型 : {model} (原始请求 glm-5.3)")
    print(f"  请求数量 : {request_counts.get('total', len(comments))}")
    if adjustments:
        print("  模型调整 : " + " | ".join(adjustments))
    print(f"  查询进度 : GET {BASE_URL}/paas/v4/batches/{batch_id}")
    print("  结果下载 : 任务 completed 后, 读取该对象的 output_file_id,")
    print(f"             再 GET {BASE_URL}/paas/v4/files/<output_file_id>/content")
    print("=" * 60)


if __name__ == "__main__":
    main()
