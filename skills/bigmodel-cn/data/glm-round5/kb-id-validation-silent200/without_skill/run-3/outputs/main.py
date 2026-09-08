#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智谱（bigmodel.cn）托管知识库 ID 上线前校验脚本 —— 发布流水线卡点。

用法：
    ZHIPU_KB_ID=<知识库ID> ZHIPUAI_API_KEY=<API Key> python3 main.py

环境变量：
    ZHIPU_KB_ID      待校验的知识库 ID
    ZHIPUAI_API_KEY  智谱开放平台 API Key（HTTP Bearer 鉴权）

校验策略（失败关闭 fail-closed：宁可误报无效，绝不把无效 ID 判为有效）：

    第 1 步 存在性 —— GET /api/llm-application/open/knowledge/{kb_id}
        必须同时满足以下三条，才认定知识库存在：
          a) HTTP 状态码为 200；
          b) 响应体 JSON 中的业务码 code == 200；
          c) data.id 与 ZHIPU_KB_ID 逐字符完全相等。
        404 / 业务错误码 / 响应体对不上 / 无法解析 → 一律判为无效。

    第 2 步 可用性 —— GET /api/llm-application/open/document?knowledge_id=...
        要求 code == 200 且 data.total > 0（空知识库检索必然落空，视为不可用），
        并与详情接口返回的 document_size 交叉核对，不一致视为响应可疑，不放行。

    网络异常 / 超时 / HTTP 5xx / 429 会自动重试（共 3 次尝试）；重试耗尽、
    鉴权失败（401/403）属于“无法确认”，同样按不通过处理，阻断发布。

为什么不拿“知识库检索”接口当校验证据：
    POST /api/llm-application/open/knowledge/retrieve 对不存在的知识库 ID
    并未承诺报错，可能仍然返回 HTTP 200 + 空 data。“200 但空结果”既可能是
    “库不存在”，也可能是“正常库没召回”，无法作为存在性证明——这是典型的
    静默 200 陷阱。本脚本只认详情接口的明确回执，从源头避免坏 ID 蒙混上线。

退出码（流水线直接以此为卡点依据）：
    0  校验通过：知识库存在且非空，可用
    1  校验不通过：ID 不存在 / 无权访问 / 响应异常 / 知识库为空
    2  无法确认（网络、鉴权、服务端故障等），按不通过处理
    3  配置错误（环境变量缺失）
"""

import os
import sys
import time

import requests

API_BASE = "https://open.bigmodel.cn/api/llm-application/open"
KB_DETAIL_URL = API_BASE + "/knowledge/{kb_id}"
KB_DOCUMENT_LIST_URL = API_BASE + "/document"

REQUEST_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3          # 网络异常 / 5xx / 429 时的总尝试次数
RETRY_BACKOFF_SECONDS = 2 # 重试退避基数（第 n 次失败后睡 n*基数 秒）

EXIT_VALID = 0
EXIT_INVALID = 1
EXIT_INCONCLUSIVE = 2
EXIT_CONFIG_ERROR = 3

CONCLUSION_TEXT = {
    EXIT_VALID: "✅ 有效（VALID）",
    EXIT_INVALID: "❌ 无效（INVALID）",
    EXIT_INCONCLUSIVE: "⚠️ 无法确认（UNVERIFIED，按无效处理）",
    EXIT_CONFIG_ERROR: "⛔ 配置错误（CONFIG_ERROR，按无效处理）",
}


def mask_secret(value):
    """脱敏展示 API Key，避免密钥进入流水线日志。"""
    if not value:
        return "(空)"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "..." + value[-4:]


def truncate(text, limit=200):
    text = ("" if text is None else str(text)).strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


def request_with_retry(session, method, url, **kwargs):
    """带重试的 HTTP 请求。

    只对瞬时故障重试：网络异常 / 超时 / HTTP 5xx / 429。
    返回 (response, error)：response 为 None 表示重试耗尽仍未拿到可用响应。
    """
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = session.request(method, url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
        except requests.RequestException as exc:
            last_error = "网络异常 {}: {}".format(type(exc).__name__, exc)
        else:
            if resp.status_code < 500 and resp.status_code != 429:
                return resp, None
            last_error = "HTTP {}（服务端错误/限流）".format(resp.status_code)
        if attempt < MAX_ATTEMPTS:
            print("    第 {} 次尝试失败（{}），{}s 后重试...".format(
                attempt, last_error, RETRY_BACKOFF_SECONDS * attempt))
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    return None, "{}（已尝试 {} 次）".format(last_error, MAX_ATTEMPTS)


def parse_json_object(resp):
    """把响应解析为 dict；失败时返回 (None, 可打印的原因)。"""
    try:
        body = resp.json()
    except ValueError:
        return None, "HTTP {}，响应体不是合法 JSON：{}".format(resp.status_code, truncate(resp.text))
    if not isinstance(body, dict):
        return None, "HTTP {}，响应体不是 JSON 对象：{}".format(resp.status_code, truncate(resp.text))
    return body, None


def body_success(body):
    """官方包装结构中业务码 code == 200 才算成功（兼容 int/str 两种返回）。"""
    return str(body.get("code")) == "200"


def body_is_auth_error(resp, body):
    """HTTP 或业务码指向鉴权失败（Key 本身的问题，属于“无法确认”而非“库无效”）。"""
    if resp.status_code in (401, 403):
        return True
    return body is not None and str(body.get("code")) in ("401", "403")


def body_error_desc(body):
    return "code={}, message={}".format(body.get("code", "(缺失)"), truncate(body.get("message")))


def check_existence(session, kb_id):
    """第 1 步：知识库是否存在。

    返回 (退出码, 知识库元数据或 None, 结论说明)。
    只有详情接口给出“HTTP 200 + code 200 + data.id 完全匹配”的明确回执才算存在。
    """
    url = KB_DETAIL_URL.format(kb_id=kb_id)
    print("\n[1/2] 校验知识库是否存在")
    print("    GET {}".format(url))

    resp, error = request_with_retry(session, "GET", url)
    if resp is None:
        return EXIT_INCONCLUSIVE, None, "无法确认知识库是否存在：{}".format(error)

    body, parse_error = parse_json_object(resp)
    if body_is_auth_error(resp, body):
        return EXIT_INCONCLUSIVE, None, (
            "API Key 鉴权失败（HTTP {}），无法确认。请检查 ZHIPUAI_API_KEY 是否正确、是否有效".format(
                resp.status_code))
    if parse_error:
        # 无法解析的响应不能作为“存在”的证据，一律判无效（失败关闭）
        return EXIT_INVALID, None, "详情接口响应异常，不能证明知识库存在：{}".format(parse_error)
    if not body_success(body):
        return EXIT_INVALID, None, (
            "知识库不存在，或当前 API Key 无权访问它（HTTP {}；{}）。ID：{}".format(
                resp.status_code, body_error_desc(body), kb_id))

    data = body.get("data")
    returned_id = data.get("id") if isinstance(data, dict) else None
    if not isinstance(returned_id, str) or returned_id != kb_id:
        return EXIT_INVALID, None, (
            "详情接口返回的 data.id（{!r}）与待校验 ID（{!r}）不一致，"
            "视为无效（防止静默 200 造成误判）".format(returned_id, kb_id))

    return EXIT_VALID, data, "知识库存在（详情接口明确回执，ID 完全匹配）"


def check_usability(session, kb_id, kb_meta):
    """第 2 步：知识库是否可用（非空库、文档数交叉一致）。

    返回 (退出码, 信息 dict 或 None, 结论说明)。
    """
    print("\n[2/2] 校验知识库是否可用（非空、可检索）")
    print("    GET {}?knowledge_id={}&page=1&size=100".format(KB_DOCUMENT_LIST_URL, kb_id))

    resp, error = request_with_retry(
        session, "GET", KB_DOCUMENT_LIST_URL,
        params={"knowledge_id": kb_id, "page": 1, "size": 100})
    if resp is None:
        return EXIT_INCONCLUSIVE, None, "无法确认知识库内容：{}".format(error)

    body, parse_error = parse_json_object(resp)
    if body_is_auth_error(resp, body):
        return EXIT_INCONCLUSIVE, None, "API Key 鉴权失败（401/403），无法确认知识库内容"
    if parse_error:
        return EXIT_INCONCLUSIVE, None, "文档列表响应异常，无法确认可用性：{}".format(parse_error)
    if not body_success(body):
        return EXIT_INVALID, None, (
            "知识库存在，但读取文档列表失败（HTTP {}；{}），无法确认其可用".format(
                resp.status_code, body_error_desc(body)))

    data = body.get("data")
    total = data.get("total") if isinstance(data, dict) else None
    if not isinstance(total, int) or isinstance(total, bool):
        return EXIT_INVALID, None, "文档列表响应中缺少有效的 data.total，无法确认知识库是否为空"

    if total <= 0:
        return EXIT_INVALID, None, (
            "知识库存在但没有任何文档（data.total={}）：检索必然落空，判定为不可用。"
            "请先上传文档并等待解析完成".format(total))

    # 与详情接口的 document_size 交叉核对，防止被异常响应蒙混过关
    detail_count = kb_meta.get("document_size") if isinstance(kb_meta, dict) else None
    if isinstance(detail_count, int) and not isinstance(detail_count, bool) and detail_count != total:
        return EXIT_INCONCLUSIVE, None, (
            "详情接口 document_size={} 与文档列表 total={} 不一致，疑似响应异常，"
            "本次不放行；请重跑，持续出现请人工排查".format(detail_count, total))

    return EXIT_VALID, {"document_total": total}, "知识库非空，共 {} 个文档".format(total)


def print_conclusion(exit_code, summary):
    print("\n" + "=" * 62)
    print("校验结论：" + CONCLUSION_TEXT[exit_code])
    print(summary)
    if exit_code == EXIT_VALID:
        print("发布卡点：放行（退出码 0）")
    else:
        print("发布卡点：阻断（宁可误报无效，不放坏 ID 上线；退出码 {}）".format(exit_code))
    print("=" * 62, flush=True)


def main():
    # 保证中文/符号在任何 CI locale 下都能输出，避免日志乱码导致看不清结论
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 62)
    print("智谱托管知识库 ID 上线前校验（发布卡点，失败关闭）")
    print("=" * 62)

    kb_id = (os.environ.get("ZHIPU_KB_ID") or "").strip()
    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()

    print("待校验知识库 ID：{}".format(kb_id or "(未配置)"))
    print("API Key：{}".format(mask_secret(api_key)))

    if not kb_id:
        msg = "配置错误：环境变量 ZHIPU_KB_ID 未设置或为空，无从校验"
        print("\n❌ " + msg)
        print_conclusion(EXIT_CONFIG_ERROR, msg)
        return EXIT_CONFIG_ERROR
    if not api_key:
        msg = "配置错误：环境变量 ZHIPUAI_API_KEY 未设置或为空，无法调用接口验证"
        print("\n❌ " + msg)
        print_conclusion(EXIT_CONFIG_ERROR, msg)
        return EXIT_CONFIG_ERROR

    session = requests.Session()
    session.headers.update({
        "Authorization": "Bearer " + api_key,
        "Accept": "application/json",
    })

    # 第 1 步：存在性。不通过则无需继续。
    code, kb_meta, msg = check_existence(session, kb_id)
    print("    → " + msg)
    if code != EXIT_VALID:
        print_conclusion(code, msg)
        return code

    # 第 2 步：可用性（非空、文档数交叉一致）。
    code, info, msg = check_usability(session, kb_id, kb_meta)
    print("    → " + msg)
    if code != EXIT_VALID:
        print_conclusion(code, msg)
        return code

    name = kb_meta.get("name") if isinstance(kb_meta, dict) else None
    summary = "知识库存在且可用：ID「{}」完全匹配，名称「{}」，共 {} 个文档。".format(
        kb_id, (str(name) if name else "(未命名)"), info["document_total"])
    print_conclusion(EXIT_VALID, summary)
    return EXIT_VALID


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # 兜底：任何未预期异常都按“无法确认”失败关闭，绝不放行
        print("\n⚠️ 校验过程发生未预期异常：{}: {}".format(type(exc).__name__, exc), file=sys.stderr)
        print_conclusion(EXIT_INCONCLUSIVE,
                         "未预期异常 {}: {}".format(type(exc).__name__, exc))
        sys.exit(EXIT_INCONCLUSIVE)
