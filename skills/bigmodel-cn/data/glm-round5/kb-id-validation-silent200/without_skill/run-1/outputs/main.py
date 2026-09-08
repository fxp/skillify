#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前校验智谱托管知识库 ID 是否真实存在且可用(发布流水线卡点)。

用法
----
    ZHIPU_KB_ID=<知识库ID> ZHIPUAI_API_KEY=<APIKey> python3 main.py

输出固定一行结论(便于流水线抓取):
    校验结论: 有效 —— ...
    校验结论: 无效 —— ...
退出码: 0 = 有效(放行); 1 = 无效(卡点拦截)。流水线应依赖退出码。

判定为"有效"的必要条件(缺一不可)
----------------------------------
1. 环境变量 ZHIPU_KB_ID、ZHIPUAI_API_KEY 均已设置且非空;
2. 知识库详情接口返回 HTTP 200;
3. 响应是 JSON 对象,且不含 error 字段;
4. 响应体业务码 code == 200;
5. data 为对象,且其中的知识库 ID 与 ZHIPU_KB_ID 完全一致。

为什么不能只看 HTTP 状态码
--------------------------
智谱该系列接口的响应自带业务码:HTTP 200 只代表"通信成功",
出错时业务码放在响应体的 code 字段里,且完全可能以 HTTP 200 携带
业务错误(即"静默 200")。因此本校验逐层核对 HTTP 状态码、error
字段、业务码、data.id 回显,任何一层不符合都判无效。

fail-closed 原则
-----------------
除上述全部满足之外的任何情况——网络异常、超时、4xx/5xx、鉴权失败、
JSON 解析失败、字段缺失或类型不符、ID 不一致——一律判"无效"。
宁可误报无效,绝不把无效 ID 判成有效放上线。
例外说明:知识库存在但文档数为 0 时仍判"有效",但会打印醒目警告
(ID 本身是好的;如需更严格可把该分支改为判无效)。

接口依据(智谱开放平台官方文档/OpenAPI 规范,"知识库详情"):
    GET https://open.bigmodel.cn/api/llm-application/open/knowledge/{id}
    认证: Authorization: Bearer <ZHIPUAI_API_KEY>
    成功响应: {"data": {"id": ..., "name": ..., "document_size": ..., ...},
               "code": 200, "message": "...", "timestamp": ...}
    失败响应: {"code": <非200>, "message": "..."}(HTTP 状态码不保证非 200)

依赖: 仅 requests(pip install requests)。
"""

import os
import sys
import time
from urllib.parse import quote

try:
    import requests
except ImportError:
    # 连 HTTP 库都缺失时也必须"拦截"而不是放行
    print("校验结论: 无效 —— 运行环境缺少依赖 requests(请先 pip install requests)")
    sys.exit(1)

API_BASE = "https://open.bigmodel.cn/api"
CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 10
MAX_ATTEMPTS = 3        # 网络异常/5xx 时的重试次数;4xx 等确定性失败不重试
RETRY_BACKOFF_S = 1.0


def conclude(valid, detail):
    """全脚本唯一的结论出口,保证结论口径统一。返回退出码。"""
    print()
    if valid:
        print("校验结论: 有效 —— %s" % detail)
        return 0
    print("校验结论: 无效 —— %s" % detail)
    print("(fail-closed:宁可误报无效,也不放坏 ID 上线;退出码=1,流水线应拦截)")
    return 1


def fetch_knowledge_base(kb_id, api_key):
    """调用知识库详情接口。返回 (resp, None) 或 (None, 失败原因)。"""
    url = "%s/llm-application/open/knowledge/%s" % (API_BASE, quote(kb_id, safe=""))
    headers = {
        "Authorization": "Bearer %s" % api_key,
        "Accept": "application/json",
    }
    reason = "未发起请求"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print("[INFO] GET %s (第 %d/%d 次尝试)" % (url, attempt, MAX_ATTEMPTS))
            resp = requests.get(
                url,
                headers=headers,
                timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
            )
        except requests.RequestException as exc:
            reason = "网络异常 %s: %s" % (type(exc).__name__, exc)
            print("[WARN] %s" % reason)
        else:
            print("[INFO] HTTP 状态码: %d" % resp.status_code)
            if resp.status_code < 500:  # 4xx 是确定性失败,重试无意义
                return resp, None
            reason = "HTTP %d(服务端错误)" % resp.status_code
            print("[WARN] %s" % reason)
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_S * attempt)
    return None, reason


def main():
    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()

    if not kb_id:
        return conclude(False, "环境变量 ZHIPU_KB_ID 未设置或为空")
    if not api_key:
        return conclude(False, "环境变量 ZHIPUAI_API_KEY 未设置或为空")

    print("[INFO] 待校验知识库 ID: %s" % kb_id)

    resp, err = fetch_knowledge_base(kb_id, api_key)
    if resp is None:
        return conclude(
            False, "重试 %d 次仍无法完成校验(%s),按无效处理" % (MAX_ATTEMPTS, err)
        )

    if resp.status_code != 200:
        body = (resp.text or "").strip().replace("\n", " ")[:200]
        return conclude(
            False,
            "接口返回 HTTP %d 而非 200(鉴权失败/无权限/知识库不存在等),"
            "响应片段: %s" % (resp.status_code, body),
        )

    try:
        payload = resp.json()
    except ValueError:
        return conclude(
            False, "HTTP 200 但响应不是合法 JSON: %r" % (resp.text or "")[:200]
        )

    if not isinstance(payload, dict):
        return conclude(False, "HTTP 200 但响应 JSON 不是对象: %r" % (payload,))

    if payload.get("error") is not None:
        return conclude(
            False, "HTTP 200 但响应含 error 字段: %r" % (payload.get("error"),)
        )

    code = payload.get("code")
    if code != 200:
        return conclude(
            False,
            "HTTP 200 但业务码 code=%r != 200(静默 200 携带业务错误,例如知识库"
            "不存在),message=%r" % (code, payload.get("message")),
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        return conclude(
            False, "响应缺少 data 对象(data=%r),无法确认知识库存在" % (data,)
        )

    returned_id = data.get("id")
    if not isinstance(returned_id, str) or returned_id.strip() != kb_id:
        return conclude(
            False,
            "响应回显的知识库 ID(%r)与待校验 ID(%r)不一致或缺失" % (returned_id, kb_id),
        )

    name = data.get("name")
    doc_size = data.get("document_size")
    detail = "知识库存在且当前 API Key 可访问(id=%s" % kb_id
    if isinstance(name, str) and name:
        detail += ", 名称=%r" % name
    if isinstance(doc_size, int):
        detail += ", 文档数=%d" % doc_size
    detail += ")"

    if doc_size == 0:
        print()
        print("[警告] 该知识库当前文档数为 0,上线后检索将命中不到任何内容,请确认是否符合预期")
        print("       (ID 本身有效,本次不拦截;如需更严格可把该分支改为判无效)")

    return conclude(True, detail)


if __name__ == "__main__":
    sys.exit(main())
