#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前校验智谱（bigmodel.cn）托管知识库 ID 是否存在、能否使用。

用途：
    发布流水线卡点。校验配置里的知识库 ID（环境变量 ZHIPU_KB_ID）在智谱
    开放平台上是否真实存在，且当前 API Key（环境变量 ZHIPUAI_API_KEY）能
    访问到它。

用法：
    ZHIPUAI_API_KEY=xxx ZHIPU_KB_ID=know-xxx python3 main.py

退出码（流水线以退出码 0 作为唯一放行条件）：
    0  校验通过：知识库存在且可访问；
    1  明确无效：知识库不存在 / 鉴权失败 / 接口返回业务错误 / 返回的 ID
       与待校验 ID 不一致 / 环境变量缺失等确定性失败；
    2  无法确认：网络超时、服务端 5xx、响应体不是预期 JSON 等瞬时或未知
       故障——按无效处理，同样不放行。

实现要点（为什么不能只看 HTTP 状态码）：
    知识库这族接口（/llm-application/open/*）出错时 HTTP 状态码依然是 200，
    真实结果在响应体的 code 字段里：查询不存在的知识库，返回的是
    HTTP 200 + {"code":100013,"message":"知识库不存在"}。
    因此 raise_for_status() 在这里防不住坏 ID，必须同时判定：
    HTTP 200 且响应体 code == 200 且 data.id 与待校验 ID 完全一致，
    三者全部满足才输出“有效”。
"""

import os
import sys
import time
import urllib.parse

import requests

BASE_URL = "https://open.bigmodel.cn/api"
KB_DETAIL_TEMPLATE = "/llm-application/open/knowledge/{kb_id}"

REQUEST_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3          # 只对网络层瞬时故障重试，不会把失败响应重试成“通过”
RETRY_BACKOFF_SECONDS = 1.0

EXIT_VALID = 0
EXIT_INVALID = 1
EXIT_INCONCLUSIVE = 2


def log(message):
    print(message, flush=True)


def preview(text, limit=300):
    """截断响应体片段，仅用于日志排查。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…(已截断)"


def request_with_retry(api_key, kb_id):
    """调用知识库详情接口。返回 (resp, None) 或 (None, 最后一次错误说明)。

    只对网络异常、5xx、429 重试；拿到确定的响应（含业务错误）立刻返回，
    交给 evaluate() 判定，绝不在这里吞掉错误。
    """
    # 对 ID 做 URL 编码，避免 ID 中若混入 /、? 等字符时改变请求路径
    url = BASE_URL + KB_DETAIL_TEMPLATE.format(
        kb_id=urllib.parse.quote(kb_id, safe="")
    )
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "Accept": "application/json",
    }

    last_error = "未知错误"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt - 1))
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_error = "网络请求失败：{}: {}".format(type(exc).__name__, exc)
            log("[尝试 {}/{}] {}".format(attempt, MAX_ATTEMPTS, last_error))
            continue
        if resp.status_code >= 500 or resp.status_code == 429:
            last_error = "服务端暂不可用：HTTP {}".format(resp.status_code)
            log("[尝试 {}/{}] {}".format(attempt, MAX_ATTEMPTS, last_error))
            continue
        return resp, None
    return None, last_error


def evaluate(resp, kb_id):
    """判定详情接口的响应。

    返回 (结论, 原因, data)。结论取值：
        "valid"        —— 知识库确认存在且可访问，data 为详情字典；
        "invalid"      —— 明确无效；
        "inconclusive" —— 无法确认（按无效处理）。
    """
    # 第一层：HTTP 状态码。这族接口业务错误通常也返回 200，
    # 非 200 只可能是网关/鉴权等更外层的问题，一律不放行。
    if resp.status_code != 200:
        return (
            "invalid",
            "HTTP 状态码为 {}（非 200），响应：{}".format(
                resp.status_code, preview(resp.text)
            ),
            None,
        )

    # 第二层：响应体必须是 JSON 对象
    try:
        payload = resp.json()
    except ValueError:
        return (
            "inconclusive",
            "响应体不是合法 JSON：{}".format(preview(resp.text)),
            None,
        )
    if not isinstance(payload, dict):
        return (
            "inconclusive",
            "响应体不是 JSON 对象：{}".format(preview(str(payload))),
            None,
        )

    # 第三层：真实结果在响应体 code 里（这就是“HTTP 200 掩盖错误”的坑）
    if "code" not in payload:
        return (
            "inconclusive",
            "响应体缺少 code 字段，无法判定：{}".format(preview(str(payload))),
            None,
        )
    code = str(payload.get("code")).strip()
    if code != "200":
        return (
            "invalid",
            "接口返回业务错误 code={} message={!r}（例如 100013=知识库不存在）".format(
                payload.get("code"), payload.get("message")
            ),
            None,
        )

    # 第四层：code=200 还要确认 data 存在、且返回的就是待校验的那个库
    data = payload.get("data")
    if not isinstance(data, dict):
        return (
            "inconclusive",
            "code=200 但缺少 data 对象，无法确认知识库详情：{}".format(
                preview(str(payload))
            ),
            None,
        )
    returned_id = data.get("id")
    if returned_id != kb_id:
        return (
            "invalid",
            "返回的知识库 id（{!r}）与待校验 ID（{!r}）不一致".format(
                returned_id, kb_id
            ),
            None,
        )

    return "valid", "", data


def main():
    log("=" * 62)
    log("智谱托管知识库 ID 上线前校验")
    log("=" * 62)

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()

    if not api_key:
        log("校验结论：无效 —— 环境变量 ZHIPUAI_API_KEY 未设置或为空")
        return EXIT_INVALID
    if not kb_id:
        log("校验结论：无效 —— 环境变量 ZHIPU_KB_ID 未设置或为空")
        return EXIT_INVALID

    log("待校验知识库 ID：{}".format(kb_id))
    log("校验接口：GET {}{}".format(BASE_URL, KB_DETAIL_TEMPLATE.format(kb_id="<ID>")))
    log("API Key 来源：环境变量 ZHIPUAI_API_KEY（已读取，不回显）")
    log("-" * 62)

    resp, error = request_with_retry(api_key, kb_id)
    if resp is None:
        log("重试 {} 次后仍无法获得响应。".format(MAX_ATTEMPTS))
        log("校验结论：无法确认（{}）—— 按无效处理，禁止上线".format(error))
        return EXIT_INCONCLUSIVE

    log("HTTP 状态码：{}".format(resp.status_code))

    verdict, reason, data = evaluate(resp, kb_id)

    if verdict == "valid":
        log("接口返回 code=200，data.id 与待校验 ID 一致。")
        log("知识库名称：{}".format(data.get("name")))
        log("向量化模型 embedding_id：{}".format(data.get("embedding_id")))
        log("文档数量 document_size：{}".format(data.get("document_size")))
        log("总字数 word_num：{}".format(data.get("word_num")))
        if data.get("document_size") == 0:
            log(
                "警告：该知识库当前没有任何文档（document_size=0），"
                "检索不会返回任何内容。ID 本身有效，但是否满足上线要求请人工确认。"
            )
        log("校验结论：有效 —— 知识库存在，且当前 API Key 可访问")
        return EXIT_VALID

    if verdict == "invalid":
        log("校验结论：无效 —— {}；禁止上线".format(reason))
        return EXIT_INVALID

    log("校验结论：无法确认（{}）—— 按无效处理，禁止上线".format(reason))
    return EXIT_INCONCLUSIVE


if __name__ == "__main__":
    sys.exit(main())
