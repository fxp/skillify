#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前校验智谱托管知识库 ID 是否存在、是否可用。

用法：
    ZHIPUAI_API_KEY=xxx ZHIPU_KB_ID=know-xxx python3 main.py

设计原则（发布流水线卡点，fail-closed）：
    绝不把无效的知识库 ID 判成有效。任何无法确凿证明"存在且可访问"的情况
    （网络失败、超时、响应无法解析、响应结构异常……）一律按"不通过"处理，
    即宁可误报无效，也不放坏 ID 上线。

关键坑（实测验证，官方文档未写）：这一族知识库接口
（/llm-application/open/*、/zrag/*）出错时 HTTP 状态码依然是 200，
真实结果在响应体的 code 字段里——查不存在的知识库返回
HTTP 200 + {"code":100013,"message":"知识库不存在"}。
因此绝不能只看 HTTP 状态码 / raise_for_status()，必须判 body["code"] == 200。

退出码：
    0  校验通过（知识库存在且当前 API Key 可访问）
    1  校验不通过（知识库无效，或响应结构异常）
    2  配置缺失（环境变量没设）
    3  无法完成校验（网络/HTTP 层失败，按不通过处理）
"""

import os
import sys
import time

import requests
from urllib.parse import quote

BASE_URL = "https://open.bigmodel.cn/api"
KNOWLEDGE_DETAIL_PATH = "/llm-application/open/knowledge/{id}"

# 业务成功码：响应体 code == 200 才代表接口真正成功（HTTP 200 不算数）
SUCCESS_CODE = 200

REQUEST_TIMEOUT = (5, 15)  # (连接超时, 读超时)，单位秒
MAX_ATTEMPTS = 3           # 网络/5xx 重试次数（重试只是减少误报，最终仍 fail-closed）
RETRY_BACKOFF_SECONDS = 1.0

# 退出码
EXIT_VALID = 0
EXIT_INVALID = 1
EXIT_CONFIG_MISSING = 2
EXIT_CANNOT_VERIFY = 3


def fail(exit_code, reason, detail=""):
    """打印校验结论并退出。任何非 0 退出码都会卡住流水线。"""
    print("校验结论：不通过 —— " + reason)
    if detail:
        print("详情：" + detail)
    sys.exit(exit_code)


def main():
    kb_id = (os.environ.get("ZHIPU_KB_ID") or "").strip()
    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()

    if not kb_id:
        fail(EXIT_CONFIG_MISSING, "环境变量 ZHIPU_KB_ID 未设置或为空，没有可校验的知识库 ID")
    if not api_key:
        fail(EXIT_CONFIG_MISSING, "环境变量 ZHIPUAI_API_KEY 未设置或为空，无法调用智谱 API")

    url = BASE_URL + KNOWLEDGE_DETAIL_PATH.format(id=quote(kb_id, safe=""))
    headers = {"Authorization": "Bearer " + api_key}

    print("正在校验智谱知识库 ID：{}".format(kb_id))
    print("请求：GET {}".format(url))

    resp = None
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            # 5xx/429 视为瞬时故障，可重试（这族接口正常时恒为 200，出现 5xx 多为网关问题）
            if resp.status_code >= 500 or resp.status_code == 429:
                last_error = "HTTP {}".format(resp.status_code)
                resp = None
                if attempt < MAX_ATTEMPTS:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue
            break
        except requests.RequestException as exc:  # 连接失败、超时等
            last_error = "{}: {}".format(type(exc).__name__, exc)
            resp = None
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue

    if resp is None:
        # 网络层始终失败：无法确凿证明有效 → 按不通过处理（宁可误报无效）
        fail(EXIT_CANNOT_VERIFY, "请求智谱 API 失败（已重试 {} 次），无法确认知识库有效".format(MAX_ATTEMPTS),
             "最后错误：{}".format(last_error))

    if resp.status_code != 200:
        # 正常情况下这族接口出错也返回 HTTP 200，走到这里说明是网关/鉴权层问题；
        # 无论是哪种，都无法确认知识库有效 → 不通过。
        body_snippet = resp.text[:300] if resp.text else "(空)"
        fail(EXIT_CANNOT_VERIFY,
             "HTTP 状态码 {}（非 200），无法确认知识库有效".format(resp.status_code),
             "响应体：{}".format(body_snippet))

    # ---- HTTP 200 之后才是真正的校验：必须判响应体 code，不能只看状态码 ----
    try:
        body = resp.json()
    except ValueError:
        fail(EXIT_INVALID, "响应体不是合法 JSON，无法确认知识库有效",
             "响应体：{}".format(resp.text[:300]))

    if not isinstance(body, dict) or "code" not in body:
        fail(EXIT_INVALID, "响应体缺少 code 字段（结构异常），按无效处理",
             "响应体：{}".format(str(body)[:300]))

    code = body.get("code")
    if code != SUCCESS_CODE:
        # 典型情况：code=100013, message="知识库不存在"（注意此时 HTTP 仍是 200）
        fail(EXIT_INVALID, "知识库不存在或不可用（接口返回错误码）",
             "code={}, message={}".format(code, body.get("message")))

    data = body.get("data")
    if not isinstance(data, dict) or "id" not in data:
        fail(EXIT_INVALID, "接口返回成功但 data 结构异常（缺少知识库 id），按无效处理",
             "响应体：{}".format(str(body)[:300]))

    # 双重确认：详情里读回的 id 必须与配置的 ID 完全一致
    if str(data.get("id")) != kb_id:
        fail(EXIT_INVALID, "接口返回的知识库 id 与配置的 ZHIPU_KB_ID 不一致，按无效处理",
             "配置 ID={}，接口返回 id={}".format(kb_id, data.get("id")))

    document_size = data.get("document_size")
    print("知识库名称：{}".format(data.get("name")))
    print("文档数量：{}，总字数：{}，向量化模型 embedding_id={}".format(
        document_size, data.get("word_num"), data.get("embedding_id")))
    if document_size == 0:
        # 空知识库检索永远返回空结果，且与"无相关内容"无法区分（另一个实测坑）；
        # ID 本身有效所以不卡点，但必须提醒，避免带病上线。
        print("警告：该知识库当前没有任何文档，检索将永远返回空结果，请确认是否符合预期。")

    print("校验结论：通过 —— 知识库存在，且当前 API Key 可访问（ID: {}）".format(kb_id))
    sys.exit(EXIT_VALID)


if __name__ == "__main__":
    main()
