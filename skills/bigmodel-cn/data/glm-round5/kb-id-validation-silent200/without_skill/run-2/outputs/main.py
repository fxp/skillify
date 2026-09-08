#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱托管知识库 ID 上线前校验(发布流水线卡点)。

环境变量:
    ZHIPU_KB_ID      必填, 待校验的知识库 ID
    ZHIPUAI_API_KEY  必填, 智谱开放平台 API Key
    ZHIPU_API_BASE   可选, 覆盖 API 根地址(默认 https://open.bigmodel.cn/api)

实现方式:
    只依赖 requests, 调用官方《知识库详情》接口:
        GET {BASE}/llm-application/open/knowledge/{id}
        Authorization: Bearer <ZHIPUAI_API_KEY>
    接口定义: https://docs.bigmodel.cn/api-reference/知识库-api/知识库详情

判定标准 —— fail-closed(宁可误报无效, 绝不把坏 ID 放上线):
    只有同时满足以下 4 点才判"有效", 其余一律判"无效"并以退出码 1 卡住流水线:
      1. HTTP 状态码 == 200;
      2. 响应体是合法的 JSON 对象;
      3. 业务响应码 body["code"] == 200。该接口业务失败时 HTTP 状态码可能
         仍是 200, 失败信息只在 body 的 code/message 里(所谓"静默 200"),
         因此绝不能只看 HTTP 200 就认定有效;
      4. body["data"] 为对象, 且 data["id"] 与 ZHIPU_KB_ID 完全一致, 防止
         接口忽略错误 ID、返回其他/默认知识库而造成误判。
    网络异常、超时、非 JSON、字段缺失、鉴权失败(401/403)等统统判"无效"。

退出码: 0 = 有效(放行); 1 = 无效(卡点)。
"""

import os
import sys
import time
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("[校验结论] ❌ 无效 —— 运行环境缺少 requests 库, 无法执行校验")
    sys.exit(1)

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api"
KB_DETAIL_PATH = "/llm-application/open/knowledge/{kb_id}"
SUCCESS_CODE = 200        # 官方文档: body 中 code == 200 才代表业务成功
TIMEOUT_SECONDS = 10      # 单次请求超时
MAX_ATTEMPTS = 3          # 瞬时故障重试次数, 耗尽仍失败 => 判无效
RETRY_BACKOFF_SECONDS = 1.0


class RetryExhausted(Exception):
    """重试耗尽仍拿不到可判定的接口响应。"""


def _one_line(text, limit=200):
    """把任意内容压成一行并截断, 便于打进流水线日志。"""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "...(截断)"


def _mask_key(api_key):
    if len(api_key) <= 8:
        return "****"
    return "{}****{}".format(api_key[:4], api_key[-2:])


def conclude_invalid(reason):
    print()
    print("[校验结论] ❌ 无效 —— {}".format(reason))
    print("卡点动作: 阻断上线(退出码 1)。本卡点为 fail-closed, 无法证明有效即视为无效。")
    return 1


def conclude_valid(kb_id):
    print()
    print("[校验结论] ✅ 有效 —— 知识库 {} 存在, 且当前 API Key 可访问".format(kb_id))
    print("卡点动作: 放行(退出码 0)")
    return 0


def fetch_detail(url, headers):
    """请求知识库详情接口。

    只有 5xx/429/网络异常这类瞬时故障才重试; 拿到任何明确响应
    (包括 401/403/404 或业务错误)都直接返回, 交给响应校验去判定。
    重试耗尽仍失败则抛 RetryExhausted, 由调用方判定为无效。
    """
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_error = "网络层失败({}): {}".format(type(exc).__name__, exc)
        else:
            if resp.status_code < 500 and resp.status_code != 429:
                return resp
            last_error = "服务端瞬时异常(HTTP {})".format(resp.status_code)
        if attempt < MAX_ATTEMPTS:
            print("  第 {}/{} 次尝试失败: {}; {}s 后重试".format(
                attempt, MAX_ATTEMPTS, last_error, RETRY_BACKOFF_SECONDS))
            time.sleep(RETRY_BACKOFF_SECONDS)
    raise RetryExhausted(last_error)


def validate_response(resp, kb_id):
    """严格校验接口响应。

    返回 (是否有效, 无效原因, 摘要信息列表, 警告列表)。
    任何一项校验不过都返回"无效" —— 宁可误报无效, 不放行坏 ID。
    """
    # 1) HTTP 层: 状态码必须是 200
    if resp.status_code != 200:
        return False, "HTTP 状态码为 {}, 不是 200; 响应体片段: {}".format(
            resp.status_code, _one_line(resp.text)), [], []

    # 2) JSON 层: 必须能解析出 JSON 对象
    try:
        body = resp.json()
    except ValueError:
        return False, ("HTTP 200 但响应体不是合法 JSON(疑似接口静默失败), "
                       "响应体片段: {}".format(_one_line(resp.text))), [], []
    if not isinstance(body, dict):
        return False, "HTTP 200 但响应体不是 JSON 对象: {}".format(_one_line(body)), [], []

    # 3) 业务层: body.code 必须是 200
    #    该接口业务失败时 HTTP 状态码可能仍是 200, 失败只体现在 body 的
    #    code/message 里 —— 这里是"静默 200"陷阱的关键防线。
    code = body.get("code")
    if code != SUCCESS_CODE and str(code) != str(SUCCESS_CODE):
        message = body.get("message", body.get("msg"))
        return False, ("HTTP 200 但业务响应码 code={!r}(应为 {}), message={!r} —— "
                       "接口明确返回了业务错误, 判定无效".format(code, SUCCESS_CODE, message)), [], []

    # 4) 数据层: 必须返回 data 对象, 且其中的 id 与待校验 ID 完全一致
    data = body.get("data")
    if not isinstance(data, dict):
        return False, ("响应中缺少 data 对象(body={}), 无法证明该知识库存在, "
                       "判定无效".format(_one_line(body))), [], []
    returned_id = data.get("id")
    if returned_id is None or str(returned_id).strip() != kb_id:
        return False, ("接口返回的知识库 id 为 {!r}, 与待校验的 ZHIPU_KB_ID={!r} 不一致 —— "
                       "不能证明目标知识库存在, 判定无效".format(returned_id, kb_id)), [], []

    summary = [
        "知识库名称: {!r}".format(data.get("name")),
        "描述: {!r}".format(data.get("description")),
        "文档数量: {!r}".format(data.get("document_size")),
        "总字数: {!r}".format(data.get("word_num")),
    ]
    warnings = []
    try:
        if int(data.get("document_size")) == 0:
            warnings.append("知识库存在但当前没有任何文档, 上线后检索将返回空结果, "
                            "请确认符合预期")
    except (TypeError, ValueError):
        pass
    return True, "", summary, warnings


def main():
    try:  # 兼容 GBK 等非 UTF-8 终端, 确保结论一定能打印出来而不是抛编码异常
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    print("=" * 64)
    print("智谱托管知识库 ID 上线前校验(发布流水线卡点)")
    print("=" * 64)

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if api_key.lower().startswith("bearer "):  # 容错: 有人会把整串 Bearer xxx 存进环境变量
        api_key = api_key[len("bearer "):].strip()
    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()

    if not api_key:
        return conclude_invalid("环境变量 ZHIPUAI_API_KEY 未设置或为空, 无法发起校验")
    if not kb_id:
        return conclude_invalid("环境变量 ZHIPU_KB_ID 未设置或为空, 无法发起校验")

    base_url = (os.environ.get("ZHIPU_API_BASE") or DEFAULT_BASE_URL).strip().rstrip("/")
    # quote(..., safe="") 防止 ID 里混入 "/" 等字符被错误拼进路径
    url = base_url + KB_DETAIL_PATH.format(kb_id=quote(kb_id, safe=""))

    print("待校验知识库 ID: {}".format(kb_id))
    print("API Key: {}".format(_mask_key(api_key)))
    print("请求接口: GET {}".format(url))
    print("判定标准: HTTP 200 且 body.code == 200 且 data.id 与待校验 ID 一致, "
          "否则一律判无效")

    try:
        resp = fetch_detail(url, {"Authorization": "Bearer {}".format(api_key)})
    except RetryExhausted as exc:
        return conclude_invalid(
            "连续 {} 次请求均失败({}), 无法确认知识库有效 —— 按宁可误报无效处理".format(
                MAX_ATTEMPTS, exc))

    ok, reason, summary, warnings = validate_response(resp, kb_id)
    if not ok:
        return conclude_invalid(reason)

    print()
    print("接口返回的知识库信息:")
    for line in summary:
        print("  {}".format(line))
    for warning in warnings:
        print("  ⚠️ {}".format(warning))
    return conclude_valid(kb_id)


if __name__ == "__main__":
    sys.exit(main())
