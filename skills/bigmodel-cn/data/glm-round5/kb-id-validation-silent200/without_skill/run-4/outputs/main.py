#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上线前校验智谱开放平台（bigmodel.cn）托管知识库的 ID 是否真实存在、当前 API Key 能否访问。

用法
----
发布流水线卡点脚本，直接运行：

    ZHIPUAI_API_KEY=xxxx ZHIPU_KB_ID=yyyy python3 main.py

- 知识库 ID 从环境变量 ZHIPU_KB_ID 读取；
- API Key 从环境变量 ZHIPUAI_API_KEY 读取（只使用 requests，不依赖 SDK）。

校验方式
--------
主检查：官方"知识库详情"接口
    GET https://open.bigmodel.cn/api/llm-application/open/knowledge/{id}
若详情接口在网关层不可用（404/405 且无业务错误体），则退回"知识库列表"接口分页扫描兜底：
    GET https://open.bigmodel.cn/api/llm-application/open/knowledge?page=&size=
文档：https://docs.bigmodel.cn/api-reference/知识库-api/知识库详情
      https://docs.bigmodel.cn/api-reference/知识库-api/知识库列表

卡点安全策略（重要）
--------------------
底线是【绝不把无效 ID 判成有效】，宁可误报无效。只有同时拿到以下正向证据才判通过：
  1) HTTP 状态码为 200；
  2) 响应体是 JSON 对象，且业务码 code == 200 ——
     智谱知识库接口出错时 HTTP 仍可能是 200（"静默 200"），错误只藏在 body 的
     code/message 里，所以绝不能只看 HTTP 状态码；
  3) 响应 data.id 与配置的 ZHIPU_KB_ID 完全一致。
以下情况一律判不通过（退出码 1）：环境变量缺失/值明显非法、网络错误、超时、
HTTP 非 200、body 不是 JSON、code != 200、data 缺失、id 不一致、列表扫描不完整等。

说明：document_size（文档数）等字段只作为信息打印，不作为卡点条件
（空知识库是否允许上线属于业务决策，不属于"ID 是否有效"的范畴）。

退出码：0 = 校验通过（有效）；1 = 校验不通过（无效或无法确认，均视为无效）。
"""

import json
import os
import sys
import time
from urllib.parse import quote

import requests

API_BASE = "https://open.bigmodel.cn"
KNOWLEDGE_DETAIL_URL = API_BASE + "/api/llm-application/open/knowledge/{knowledge_id}"
KNOWLEDGE_LIST_URL = API_BASE + "/api/llm-application/open/knowledge"

REQUEST_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3        # 网络/5xx 重试次数：只减少误报，不会把失败变成通过
RETRY_BACKOFF_SECONDS = 1.0
LIST_PAGE_SIZE = 50
LIST_MAX_PAGES = 200    # 分页护栏：扫描不完整时宁可判不通过，也不静默漏掉目标

EXIT_PASS = 0
EXIT_FAIL = 1


class ValidationError(Exception):
    """校验不通过。异常消息为面向流水线日志的人可读原因。"""


class EndpointUnavailable(Exception):
    """详情接口在网关层不可用（非业务错误），需退回列表接口兜底扫描。"""


def fail(reason: str) -> int:
    """打印最终结论（不通过）并返回失败退出码。"""
    print("-" * 62)
    print(f"校验结论: 无效（校验不通过）—— {reason}")
    print("按上线卡点策略拒绝发布：宁可误报无效，也不放行无法确认的 ID。")
    print("RESULT: FAIL")
    return EXIT_FAIL


def body_snippet(resp, limit: int = 200) -> str:
    """响应体文本片段，用于失败日志，便于排查。"""
    text = (resp.text or "").strip().replace("\n", " ")
    if not text:
        return "<空响应体>"
    return text[:limit] + ("…" if len(text) > limit else "")


def json_snippet(payload, limit: int = 200) -> str:
    """JSON 序列化片段，用于失败日志。"""
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(payload)
    return text[:limit] + ("…" if len(text) > limit else "")


def parse_json_object(resp, step: str) -> dict:
    """把响应体解析成 JSON 对象；解析失败按不通过处理（fail-safe）。"""
    try:
        payload = resp.json()
    except Exception:  # 任何解析失败（含编码错误）都无法确认有效，一律不通过
        raise ValidationError(
            f"{step}: HTTP {resp.status_code} 但响应体不是合法 JSON（片段: {body_snippet(resp)}）"
        )
    if not isinstance(payload, dict):
        raise ValidationError(
            f"{step}: HTTP {resp.status_code} 但响应体不是 JSON 对象（片段: {body_snippet(resp)}）"
        )
    return payload


def describe_error(payload: dict) -> str:
    """从错误响应体提取人可读信息，兼容 code/message 与 error.code/message 两种形状。"""
    code = payload.get("code")
    message = payload.get("message")
    err = payload.get("error")
    if message is None and isinstance(err, dict):
        code = err.get("code", code)
        message = err.get("message")
    if message is None:
        message = f"无错误信息（响应: {json_snippet(payload)}）"
    return f"code={code!r}, message={message!r}"


def ensure_business_success(payload: dict, step: str) -> None:
    """业务层校验：智谱知识库接口出错时 HTTP 仍可能是 200（"静默 200"），
    错误只体现在 body 的 code/message 上，因此必须检查业务码。"""
    code = payload.get("code")
    if str(code) != "200":  # 文档定义 code 为 integer 200；字符串 "200" 也接受
        raise ValidationError(
            f"{step}: 业务层返回失败（注意：HTTP 状态码可能仍是 200）: {describe_error(payload)}"
        )


def http_get(url: str, params, api_key: str, step: str):
    """带限次重试的 GET。仅对网络异常和 5xx 重试；最终仍失败则判不通过。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    last_error = "未知网络错误"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            last_error = f"网络错误 {type(exc).__name__}: {exc}"
        else:
            if resp.status_code < 500 or attempt == MAX_ATTEMPTS:
                return resp
            last_error = f"服务端错误 HTTP {resp.status_code}"
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise ValidationError(
        f"{step}: {last_error}（共尝试 {MAX_ATTEMPTS} 次仍失败，无法确认知识库有效）"
    )


def fetch_detail(api_key: str, kb_id: str) -> dict:
    """主检查：查询知识库详情，返回知识库记录 dict（仅在确认有效时返回）。"""
    step = "查询知识库详情 GET /api/llm-application/open/knowledge/{id}"
    url = KNOWLEDGE_DETAIL_URL.format(knowledge_id=quote(kb_id, safe=""))
    resp = http_get(url, None, api_key, step)

    if resp.status_code in (404, 405):
        # 区分两种 404：带 code/message 的是业务错误（知识库不存在/无权限等），直接不通过；
        # 不带业务错误体的是网关/路由层 404（接口本身不可用，多为 HTML），交列表接口兜底。
        try:
            payload = resp.json()
        except Exception:
            payload = None
        if isinstance(payload, dict) and ("code" in payload or "message" in payload):
            raise ValidationError(
                f"{step}: HTTP {resp.status_code}, 业务错误: {describe_error(payload)}"
            )
        raise EndpointUnavailable(f"HTTP {resp.status_code} 且无业务错误体")

    payload = parse_json_object(resp, step)
    if resp.status_code != 200:
        raise ValidationError(
            f"{step}: HTTP {resp.status_code}, {describe_error(payload)}"
        )
    ensure_business_success(payload, step)

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValidationError(
            f"{step}: code=200 但响应缺少 data 对象，无法确认知识库存在"
            f"（响应: {json_snippet(payload)}）"
        )
    returned_id = data.get("id")
    if returned_id != kb_id:
        raise ValidationError(
            f"{step}: 响应中的知识库 id 为 {returned_id!r}，"
            f"与配置的 ZHIPU_KB_ID {kb_id!r} 不一致，拒绝放行"
        )
    return data


def scan_list(api_key: str, kb_id: str) -> dict:
    """兜底检查：分页扫描账号知识库列表，精确匹配 id。
    只有完整扫描后命中才返回；扫描不完整或未命中一律抛 ValidationError。"""
    step = "扫描知识库列表 GET /api/llm-application/open/knowledge"
    scanned = 0
    total = None
    for page in range(1, LIST_MAX_PAGES + 1):
        resp = http_get(
            KNOWLEDGE_LIST_URL,
            {"page": page, "size": LIST_PAGE_SIZE},
            api_key,
            step,
        )
        payload = parse_json_object(resp, step)
        if resp.status_code != 200:
            raise ValidationError(
                f"{step}: 第 {page} 页 HTTP {resp.status_code}, {describe_error(payload)}"
            )
        ensure_business_success(payload, step)
        data = payload.get("data")
        items = data.get("list") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ValidationError(
                f"{step}: 第 {page} 页响应缺少 data.list 数组，扫描不完整"
                f"（响应: {json_snippet(payload)}）"
            )
        for item in items:
            if isinstance(item, dict) and item.get("id") == kb_id:
                return item
        scanned += len(items)
        total = data.get("total")
        if not items:
            break
        if isinstance(total, int) and scanned >= total:
            break
    else:
        raise ValidationError(
            f"{step}: 知识库数量超过 {LIST_MAX_PAGES} 页护栏，扫描不完整，无法确认 ID 有效"
        )
    total_desc = total if isinstance(total, int) else scanned
    raise ValidationError(
        f"{step}: 已完整扫描账号下共 {total_desc} 个知识库，"
        f"没有 id={kb_id!r} —— 该知识库不存在，或当前 API Key 无权访问"
    )


def check_config() -> tuple:
    """读取并做最基本的配置校验；任何配置问题直接判不通过。"""
    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()
    kb_id = (os.environ.get("ZHIPU_KB_ID") or "").strip()

    if not api_key:
        raise ValidationError("环境变量 ZHIPUAI_API_KEY 未设置或为空，无法调用 API 校验")
    if not kb_id:
        raise ValidationError("环境变量 ZHIPU_KB_ID 未设置或为空，没有可校验的知识库 ID")
    if any(ch.isspace() for ch in kb_id):
        raise ValidationError(
            f"ZHIPU_KB_ID 含空白字符（{kb_id!r}），疑似配置/复制粘贴出错"
        )
    if any(ch in kb_id for ch in "\"'`"):
        raise ValidationError(
            f"ZHIPU_KB_ID 含引号字符（{kb_id!r}），疑似把引号包进了配置值"
        )
    return api_key, kb_id


def main() -> int:
    print("=" * 62)
    print("智谱托管知识库 ID 上线前校验")
    print("=" * 62)

    try:
        api_key, kb_id = check_config()
    except ValidationError as exc:
        return fail(str(exc))

    print("API Key: 已从 ZHIPUAI_API_KEY 读取（内容不在日志输出）")
    print(f"待校验知识库 ID: {kb_id!r}")
    print("-" * 62)

    try:
        try:
            record = fetch_detail(api_key, kb_id)
            source = "知识库详情接口"
        except EndpointUnavailable as exc:
            print(f"[兜底] 知识库详情接口不可用（{exc}），改用知识库列表接口分页扫描")
            record = scan_list(api_key, kb_id)
            source = "知识库列表接口（兜底）"
    except ValidationError as exc:
        return fail(str(exc))

    # ---- 走到这里，已拿到"HTTP 200 + code=200 + id 完全一致"的正向证据 ----
    print(f"[OK] 校验方式: {source}")
    print(f"[OK] 知识库名称 name: {record.get('name', '<未返回>')!r}")
    print(f"[OK] 文档数量 document_size: {record.get('document_size', '<未返回>')}")
    print(f"[OK] 总字数 word_num: {record.get('word_num', '<未返回>')}")
    print("-" * 62)
    print(f"校验结论: 有效（校验通过）—— 知识库 {kb_id!r} 存在，且当前 API Key 可访问")
    print("RESULT: PASS")
    return EXIT_PASS


if __name__ == "__main__":
    exit_code = EXIT_FAIL
    try:
        exit_code = main()
    except Exception as exc:  # 未预期异常也绝不放行，统一按不通过处理
        print(f"脚本发生未预期异常（{type(exc).__name__}: {exc}）")
        exit_code = fail("脚本异常退出，无法确认知识库有效")
    sys.exit(exit_code)
