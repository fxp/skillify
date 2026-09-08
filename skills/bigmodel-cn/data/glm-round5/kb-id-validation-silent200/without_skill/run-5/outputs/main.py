#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前校验智谱托管知识库 ID（环境变量 ZHIPU_KB_ID）是否存在、是否可用。

用途：挂在发布流水线上做卡点。原则是 fail-closed ——
宁可误报"无效 / 不通过"，也绝不把一个无效（不存在、不可访问、不可用）
的知识库 ID 判成有效放上线。任何一步拿不到"肯定有效"的证据
（网络异常、HTTP 非 200、响应体不是合法 JSON、业务 code != 200、
返回 ID 与配置不一致、列表中查不到、空库等）都直接判为不通过。

用法：
    ZHIPU_KB_ID=<知识库ID> ZHIPUAI_API_KEY=<API Key> python3 main.py

退出码：0 = 校验通过（知识库存在且可用）；1 = 校验不通过（一律拦截）。

接口依据（智谱开放平台官方文档 https://docs.bigmodel.cn ，知识库 API）：
  - 知识库详情：GET https://open.bigmodel.cn/api/llm-application/open/knowledge/{id}
  - 知识库列表：GET https://open.bigmodel.cn/api/llm-application/open/knowledge?page=&size=
  - 鉴权：Authorization: Bearer <API_KEY>
  - 成功响应：HTTP 200，body = {"code": 200, "data": {...}, "message": ..., "timestamp": ...}
  - 失败响应：body 仅含 {"code": <错误码>, "message": <错误信息>}
  特别注意：失败时 HTTP 状态码很可能仍是 200（"静默 200"），
  所以必须校验响应体里的业务 code、data 及 data.id，绝不能只看 HTTP 状态码。
"""

import os
import sys
import time
from urllib.parse import quote

import requests

KB_API_BASE = "https://open.bigmodel.cn/api/llm-application/open/knowledge"
HTTP_TIMEOUT = (10, 30)   # (连接超时, 读取超时)，单位秒
MAX_ATTEMPTS = 3          # 仅对网络类瞬时故障 / HTTP 5xx 重试
RETRY_BACKOFF = (1, 2)    # 两次重试的间隔秒数
LIST_PAGE_SIZE = 50       # 列表接口分页大小
MAX_LIST_PAGES = 200      # 列表翻页上限，防止异常响应导致死循环
USER_AGENT = "kb-id-prelaunch-check/1.0"


class Fatal(Exception):
    """校验不通过（含"无法确认有效"），异常消息即为失败原因。"""


def http_request(session, method, url, *, params=None, headers=None, what):
    """发请求（带超时；仅对网络异常 / HTTP 5xx 做少量重试）。

    返回 requests.Response；重试耗尽仍失败时抛 Fatal（fail-closed）。
    """
    last_error = "未知错误"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = session.request(
                method, url, params=params, headers=headers, timeout=HTTP_TIMEOUT
            )
        except requests.RequestException as exc:
            last_error = "%s: %s" % (type(exc).__name__, exc)
        else:
            if resp.status_code < 500:
                return resp
            last_error = "HTTP %s" % resp.status_code
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF[attempt - 1])
    raise Fatal(
        "%s 请求失败（已尝试 %d 次，最后一次原因：%s）；"
        "无法确认知识库有效，按不通过处理" % (what, MAX_ATTEMPTS, last_error)
    )


def check_success_body(resp, what):
    """统一校验响应并返回 data 对象。

    必须同时满足：HTTP 200、body 是 JSON 对象、业务 code == 200、
    data 是对象。任何一条不满足都抛 Fatal —— 尤其是HTTP 200 但
    body 里带业务错误码的"静默 200"情况。
    """
    snippet = (resp.text or "")[:300].replace("\n", " ")

    if resp.status_code != 200:
        hint = {
            401: "API Key 无效或未认证",
            403: "无权限访问该资源",
            404: "资源不存在（知识库 ID 不存在或接口路径不可用）",
            429: "请求被限流",
        }.get(resp.status_code, "非预期的 HTTP 状态码")
        raise Fatal(
            "%s 返回 HTTP %s（%s），响应片段：%s；按不通过处理"
            % (what, resp.status_code, hint, snippet)
        )

    try:
        payload = resp.json()
    except ValueError:
        raise Fatal(
            "%s 返回 HTTP 200 但响应体不是合法 JSON（疑似网关/代理异常），"
            "响应片段：%s；按不通过处理" % (what, snippet)
        )

    if not isinstance(payload, dict):
        raise Fatal(
            "%s 响应 JSON 不是对象：%r；按不通过处理" % (what, payload)
        )

    biz_code = payload.get("code")
    if biz_code != 200:
        raise Fatal(
            "%s 返回 HTTP 200 但业务错误码 code=%r, message=%r"
            "（静默 200，不能只看 HTTP 状态码）；按不通过处理"
            % (what, biz_code, payload.get("message"))
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise Fatal(
            "%s 响应缺少 data 对象（code=200 但 data=%r，响应异常）；按不通过处理"
            % (what, data)
        )
    return data


def verify_via_detail(session, kb_id, headers):
    """第一道校验：知识库详情接口。

    要求：HTTP 200 + 业务 code=200 + data.id 与待校验 ID 完全一致。
    返回 data（知识库详情 dict）；任何异常抛 Fatal。
    """
    url = "%s/%s" % (KB_API_BASE, quote(kb_id, safe=""))
    print("[1/3] 调用知识库详情接口：GET %s" % url)
    resp = http_request(session, "GET", url, headers=headers, what="知识库详情接口")
    data = check_success_body(resp, "知识库详情接口")

    returned_id = data.get("id")
    if returned_id is None or str(returned_id).strip() != kb_id:
        raise Fatal(
            "知识库详情接口返回的 ID 与配置不一致：接口返回 id=%r，"
            "ZHIPU_KB_ID=%r；按不通过处理" % (returned_id, kb_id)
        )
    print("  通过：业务 code=200，返回 id 与配置一致，名称=%r" % (data.get("name"),))
    return data


def verify_via_list(session, kb_id, headers):
    """第二道校验：知识库列表接口逐页查找，二次确认该 ID 确实存在。

    返回列表中匹配的条目；找不到（或翻页异常、超上限）抛 Fatal / 返回 None。
    """
    print("[2/3] 调用知识库列表接口做二次核验：GET %s?page=&size=" % KB_API_BASE)
    page = 1
    scanned = 0
    while page <= MAX_LIST_PAGES:
        resp = http_request(
            session, "GET", KB_API_BASE,
            params={"page": page, "size": LIST_PAGE_SIZE},
            headers=headers,
            what="知识库列表接口(第 %d 页)" % page,
        )
        data = check_success_body(resp, "知识库列表接口(第 %d 页)" % page)
        items = data.get("list")
        if not isinstance(items, list):
            raise Fatal(
                "知识库列表响应格式异常：data.list 不是列表（%r）；按不通过处理"
                % (items,)
            )
        if not items:
            break
        for item in items:
            if isinstance(item, dict) and item.get("id") is not None:
                if str(item.get("id")).strip() == kb_id:
                    print("  通过：在知识库列表第 %d 页找到了该 ID" % page)
                    return item
        scanned += len(items)
        total = data.get("total")
        if isinstance(total, bool) or not isinstance(total, int):
            total = None
        if total is not None and scanned >= total:
            break
        if len(items) < LIST_PAGE_SIZE:
            break
        page += 1
    else:
        raise Fatal(
            "知识库列表翻页超过 %d 页仍未完成核验（数据量异常）；按不通过处理"
            % MAX_LIST_PAGES
        )
    return None


def verify_usable(detail):
    """第三道校验：知识库可用性（必须有文档，空库无法提供检索）。"""
    print("[3/3] 检查知识库可用性（文档数量 document_size）...")
    doc_size = detail.get("document_size")
    if isinstance(doc_size, bool) or not isinstance(doc_size, int):
        raise Fatal(
            "详情响应中 document_size 缺失或类型异常（%r），"
            "无法确认知识库有内容；按不通过处理" % (doc_size,)
        )
    if doc_size <= 0:
        raise Fatal(
            "知识库存在但 document_size=%d（空库，无法提供检索内容），不可用；"
            "按不通过处理" % doc_size
        )
    print("  通过：document_size=%d > 0" % doc_size)
    return doc_size


def print_pass(kb_id, detail, doc_size):
    print()
    print("=" * 64)
    print("校验结论：有效 —— 知识库存在且可用，允许上线")
    print("=" * 64)
    print("  知识库 ID     ：%s" % kb_id)
    print("  名称          ：%r" % (detail.get("name"),))
    print("  文档数        ：%s" % doc_size)
    print("  分词后总长度  ：%s" % (detail.get("length"),))
    print("  总字数        ：%s" % (detail.get("word_num"),))
    print("  向量化模型 ID ：%s" % (detail.get("embedding_id"),))
    print("  判定依据      ：详情接口 HTTP 200 且业务 code=200 且返回 ID 一致；")
    print("                  列表接口中可见该 ID；document_size=%s > 0" % doc_size)
    print("=" * 64)


def print_fail(reason):
    print()
    print("=" * 64)
    print("校验结论：无效（校验不通过）—— 已拦截，禁止上线")
    print("=" * 64)
    print("  失败原因：%s" % reason)
    print("=" * 64)


def main():
    print("=" * 64)
    print("智谱托管知识库 ID 上线前校验（发布流水线卡点）")
    print("=" * 64)

    kb_id = (os.environ.get("ZHIPU_KB_ID") or "").strip()
    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()

    if not kb_id:
        print_fail("环境变量 ZHIPU_KB_ID 未设置或为空，没有可校验的知识库 ID")
        return 1
    if not api_key:
        print_fail("环境变量 ZHIPUAI_API_KEY 未设置或为空，无法调用智谱 API")
        return 1

    print("待校验知识库 ID：%s" % kb_id)

    headers = {
        "Authorization": "Bearer %s" % api_key,
        "User-Agent": USER_AGENT,
    }
    session = requests.Session()

    try:
        detail = verify_via_detail(session, kb_id, headers)

        item = verify_via_list(session, kb_id, headers)
        if item is None:
            raise Fatal(
                "详情接口可查到，但在该 API Key 名下的知识库列表中未找到此 ID"
                "（可能已被删除、不属于当前账号或状态异常）；按不通过处理"
            )

        doc_size = verify_usable(detail)
    except Fatal as exc:
        print_fail(str(exc))
        return 1
    except Exception as exc:  # 任何未预期异常一律按不通过处理（fail-closed）
        print_fail("校验过程出现未预期异常：%s: %s" % (type(exc).__name__, exc))
        return 1

    print_pass(kb_id, detail, doc_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
