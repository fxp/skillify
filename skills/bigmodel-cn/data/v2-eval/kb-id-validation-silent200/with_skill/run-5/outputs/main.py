#!/usr/bin/env python3
"""智谱托管知识库 ID 上线前校验（发布流水线卡点）。

用法：
    ZHIPUAI_API_KEY=xxx ZHIPU_KB_ID=know-xxx python3 main.py

退出码：0 = 校验通过（可以放行）；1 = 校验不通过（阻断发布）。

卡点原则（fail-closed）：宁可误报无效，也绝不把无效 ID 放上线。
    只有同时满足以下条件才判定"有效"：
      1) 知识库详情接口返回 HTTP 200 且 body.code == 200 且 data 结构完整；
      2) 返回的 data.id 与待校验的 ZHIPU_KB_ID 完全一致；
      3) 文档列表接口对该知识库同样返回 code == 200。
    环境变量缺失、网络异常、超时、响应无法解析、结构不符等一切
    "无法确认为有效"的情况，一律判定无效并退出 1。

⚠️ 本接口族的关键陷阱（实测确认，官方文档未写明）：
    /llm-application/open/* 下的知识库接口出错时 HTTP 状态码依然是 200，
    真实结果在响应体的 code 字段里——查一个不存在的知识库，返回的是
    HTTP 200 + {"code":100013,"message":"知识库不存在"}。
    因此 resp.raise_for_status() 在这里永远不会触发，必须判断 body["code"]。
"""

import json
import os
import sys
import urllib.parse

import requests

BASE_URL = "https://open.bigmodel.cn/api"
REQUEST_TIMEOUT = 15  # 秒；超时视为"无法确认"，按无效处理


def conclude_invalid(reason, detail=None):
    """打印校验结论并阻断发布（退出码 1）。"""
    print()
    print(f"校验结论：无效 —— {reason}")
    if detail:
        print(f"  详情：{detail}")
    print("（fail-closed：无法确认为有效的，一律按无效处理，已阻断发布）")
    sys.exit(1)


def request_json(method, url, headers, params=None):
    """发请求并解析 JSON 响应体；任何网络层/解析层异常直接判无效。"""
    try:
        resp = requests.request(
            method, url, headers=headers, params=params, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        conclude_invalid(f"请求失败（网络错误或超时）：{method} {url}", repr(exc))

    # 正常情况下本接口族连出错都返回 HTTP 200；这里再显式兜一层，
    # 网关 5xx / 鉴权层拦截等非 200 一律视为"无法确认"→ 无效。
    if resp.status_code != 200:
        conclude_invalid(
            f"HTTP 状态码非 200：{resp.status_code}", resp.text[:300]
        )

    try:
        body = resp.json()
    except ValueError:
        conclude_invalid("响应体不是合法 JSON", resp.text[:300])
    if not isinstance(body, dict):
        conclude_invalid("响应体不是 JSON 对象", str(body)[:300])
    return body


def check_biz_code(body, api_name):
    """校验响应体里的业务状态码——本接口族真实状态的唯一可靠来源。"""
    if body.get("code") != 200:
        conclude_invalid(
            f"{api_name} 返回业务错误（注意：HTTP 仍是 200，真实状态在 body.code，"
            f"典型如 100013 知识库不存在）",
            f"code={body.get('code')!r}, message={body.get('message')!r}",
        )


def main():
    print("=" * 62)
    print("智谱托管知识库 ID 上线前校验（发布流水线卡点）")
    print("=" * 62)

    # ── 0. 读取配置：缺任何一项都无法校验，直接判无效 ──
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()
    if not api_key:
        conclude_invalid("环境变量 ZHIPUAI_API_KEY 未设置或为空")
    if not kb_id:
        conclude_invalid("环境变量 ZHIPU_KB_ID 未设置或为空")

    print(f"待校验知识库 ID：{kb_id}")
    headers = {"Authorization": f"Bearer {api_key}"}

    # ── 1. 知识库详情：确认"存在" ──
    detail_url = (
        f"{BASE_URL}/llm-application/open/knowledge/"
        f"{urllib.parse.quote(kb_id, safe='')}"
    )
    print(f"\n[1/2] GET {detail_url}")
    body = request_json("GET", detail_url, headers)
    check_biz_code(body, "知识库详情")

    data = body.get("data")
    if not isinstance(data, dict):
        conclude_invalid(
            "知识库详情响应缺少 data 对象",
            json.dumps(body, ensure_ascii=False)[:300],
        )
    # 读回 id 核对：防止任何"请求 A 返回 B"式的静默错配
    if data.get("id") != kb_id:
        conclude_invalid(
            "返回的知识库 id 与待校验 ID 不一致",
            f"期望 {kb_id!r}，实际 {data.get('id')!r}",
        )
    print(
        f"  code=200，知识库存在：name={data.get('name')!r}，"
        f"document_size={data.get('document_size')}，"
        f"word_num={data.get('word_num')}"
    )

    # ── 2. 文档列表：确认当前 API Key 对该库"可用"（能正常访问/操作）──
    doc_url = f"{BASE_URL}/llm-application/open/document"
    print(f"\n[2/2] GET {doc_url}?knowledge_id={kb_id}&page=1&size=1")
    doc_body = request_json(
        "GET", doc_url, headers, params={"knowledge_id": kb_id, "page": 1, "size": 1}
    )
    check_biz_code(doc_body, "文档列表")
    doc_data = doc_body.get("data")
    if not isinstance(doc_data, dict):
        conclude_invalid(
            "文档列表响应缺少 data 对象",
            json.dumps(doc_body, ensure_ascii=False)[:300],
        )
    # 注意：文档数为 0 不影响结论——新建的空库也是有效库，这里只做展示。
    print(f"  code=200，文档列表可访问：total={doc_data.get('total')}")

    # ── 全部检查通过，才允许放行 ──
    print()
    print("校验结论：有效")
    print(f"  知识库 {kb_id} 存在，且当前 API Key 可正常访问（详情/文档列表均 code=200）。")
    sys.exit(0)


if __name__ == "__main__":
    main()
