#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前校验智谱（bigmodel.cn）托管知识库 ID 是否真实存在、可用。

用作发布流水线卡点脚本，直接运行：

    ZHIPUAI_API_KEY=xxx ZHIPU_KB_ID=know-xxx python3 main.py

退出码（流水线按此卡点）：
    0 —— 校验通过：知识库存在，且当前 API Key 能访问它；
    1 —— 校验不通过：凡是无法确认为有效的情况一律拦截，宁可误报无效，
         也绝不把一个坏 ID 放上线。包括：环境变量缺失、网络异常/超时、
         HTTP 非 200、业务码非 200、响应体结构异常、回显 ID 不一致。

实现要点（来自 bigmodel-cn 接入手册的实测结论）：
    知识库这一族接口（/llm-application/open/*、/zrag/*）出错时 HTTP 状态码
    依然是 200，真实结果在响应体的 code 字段里。例如查一个不存在的知识库，
    返回的是 HTTP 200 + {"code":100013,"message":"知识库不存在"}。
    因此 raise_for_status()/HTTP 200 完全不能作为成功判据，
    必须判断 body["code"] == 200，并对响应体结构做防御性校验。
"""

import os
import sys
import time
from urllib.parse import quote

import requests

BASE_URL = "https://open.bigmodel.cn/api"
TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 2  # 网络类异常（连接失败/超时）最多重试 1 次，降低流水线误拦
RETRY_WAIT_SECONDS = 2.0


def conclude(ok, reason, extra=()):
    """统一打印校验结论，返回退出码。"""
    print("=" * 62)
    if ok:
        print("校验结论：有效（知识库存在且当前 API Key 可访问，允许上线）")
    else:
        print("校验结论：无效（已拦截，禁止上线）")
    print(reason)
    for item in extra:
        print(f"  - {item}")
    print("=" * 62)
    return 0 if ok else 1


def fetch_knowledge_detail(api_key, kb_id):
    """GET /llm-application/open/knowledge/{id}，网络类异常重试后仍失败则抛出。"""
    url = f"{BASE_URL}/llm-application/open/knowledge/{quote(kb_id, safe='')}"
    headers = {"Authorization": f"Bearer {api_key}"}
    last_exc = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < MAX_ATTEMPTS:
                print(f"第 {attempt} 次请求失败：{exc}，{RETRY_WAIT_SECONDS:.0f}s 后重试…")
                time.sleep(RETRY_WAIT_SECONDS)
    raise last_exc


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()

    # ---- 前置检查：配置缺失即拦截（无法确认有效 = 无效） ----
    if not kb_id:
        return conclude(False, "环境变量 ZHIPU_KB_ID 未设置或为空，没有可校验的知识库 ID。")
    if not api_key:
        return conclude(
            False,
            "环境变量 ZHIPUAI_API_KEY 未设置或为空，无法发起校验请求。",
            ["提示：Key 缺失时无法确认知识库有效性，按无效拦截。"],
        )

    print(f"待校验知识库 ID：{kb_id}")
    print(f"校验接口：GET {BASE_URL}/llm-application/open/knowledge/{{id}}")

    # ---- 发起请求 ----
    try:
        resp = fetch_knowledge_detail(api_key, kb_id)
    except requests.exceptions.RequestException as exc:
        return conclude(
            False,
            f"请求知识库详情失败（网络异常或超时）：{exc}",
            ["提示：网络问题导致无法确认，按无效拦截；请排查网络后重试。"],
        )

    print(f"接口返回：HTTP {resp.status_code}")

    # HTTP 非 200 只可能是网关/鉴权层问题，直接拦截。
    if resp.status_code != 200:
        return conclude(
            False,
            f"HTTP 状态码异常：{resp.status_code}（预期 200）。",
            [f"响应片段：{resp.text[:300]!r}"],
        )

    # ---- 解析响应体 ----
    try:
        body = resp.json()
    except ValueError:
        return conclude(
            False,
            "响应体不是合法 JSON（可能是网关错误页），无法读取业务码。",
            [f"响应片段：{resp.text[:300]!r}"],
        )

    # ---- 核心判断：真实结果在 body.code，不在 HTTP 状态码 ----
    # 这族接口出错时 HTTP 恒为 200：不存在的知识库返回 code=100013。
    # 用 str() 归一化，兼容 code 以字符串 "200" 返回的情况。
    code = body.get("code")
    if str(code) != "200":
        return conclude(
            False,
            f"接口返回业务码非 200：code={code!r}，message={body.get('message')!r}。",
            [
                "提示：100013 通常表示知识库不存在（ID 写错或已被删除）；"
                "鉴权/权限问题也会走业务码，请结合 message 判断。",
            ],
        )

    data = body.get("data")
    if not isinstance(data, dict):
        return conclude(
            False,
            "响应 code=200 但缺少 data 对象，无法确认知识库详情。",
            [f"原始响应：{body!r}"],
        )

    # 回显 ID 必须与配置一致，防止“成功但答非所问”的响应被误判为有效。
    echoed_id = data.get("id")
    if echoed_id != kb_id:
        return conclude(
            False,
            f"响应回显的知识库 ID（{echoed_id!r}）与配置的 ZHIPU_KB_ID（{kb_id!r}）不一致。",
            [f"原始 data：{data!r}"],
        )

    # ---- 校验通过 ----
    extra = [
        f"名称：{data.get('name')}",
        f"文档数：{data.get('document_size')}",
        f"总字数：{data.get('word_num')}",
        f"接口返回：code={code}, message={body.get('message')!r}",
    ]
    if not data.get("document_size"):
        extra.append(
            "警告：该知识库当前没有任何文档，检索会返回空结果；"
            "若上线依赖检索内容，请先确认文档已上传且向量化完成（文档详情的 "
            "embedding_stat==1）再发布。此警告不改变 ID 本身的有效性。"
        )
    return conclude(True, f"知识库 {kb_id} 存在，且当前 API Key 可以访问。", extra)


if __name__ == "__main__":
    sys.exit(main())
