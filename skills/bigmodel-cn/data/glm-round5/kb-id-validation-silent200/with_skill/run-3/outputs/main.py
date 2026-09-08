#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前卡点：校验 ZHIPU_KB_ID 指定的智谱托管知识库是否存在、能否使用。

用法：
    ZHIPU_KB_ID=<知识库ID> ZHIPUAI_API_KEY=<APIKey> python3 main.py

退出码（供发布流水线卡点判定）：
    0  通过：平台明确确认该知识库存在，且当前 API Key 能访问到它
    1  不通过：平台明确表示该知识库不存在 / 不可用
    2  不通过：无法确认（配置缺失、网络异常、响应异常等），一律按无效处理

卡点原则是 fail-closed：只有拿到「HTTP 200 + 业务 code==200 + data.id 与待校验
ID 一致」的铁证才判有效；其余任何情况一律不通过，宁可误报无效，也不放坏 ID 上线。

特别注意（这族接口的坑，来自真实调用验证）：/llm-application/open/* 出错时
HTTP 状态码依然是 200，真实结果在响应体的 code 字段里——查不存在的知识库返回
HTTP 200 + {"code":100013,"message":"知识库不存在"}。所以绝不能只依赖
resp.raise_for_status()，必须解析 JSON 后判断 code。
"""

import os
import sys
import urllib.parse

import requests

BASE_URL = "https://open.bigmodel.cn/api"
KNOWLEDGE_DETAIL_PATH = "/llm-application/open/knowledge/{}"
TIMEOUT_SECONDS = 15

EXIT_PASS = 0        # 有效
EXIT_INVALID = 1     # 明确无效
EXIT_UNVERIFIED = 2  # 无法确认，同样不放行


def conclude(passed, conclusion, detail, exit_code):
    """打印最终校验结论，并以对应退出码结束进程。"""
    print(f"[{'PASS' if passed else 'FAIL'}] {conclusion}")
    if detail:
        print(f"        {detail}")
    sys.exit(exit_code)


def snippet(text, limit=300):
    """截取响应片段用于报错展示，避免刷屏。"""
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "...(截断)"


def main():
    kb_id = (os.environ.get("ZHIPU_KB_ID") or "").strip()
    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()

    print("== 智谱托管知识库 ID 上线前校验 ==")

    if not kb_id:
        conclude(False, "校验结论：不通过 —— 环境变量 ZHIPU_KB_ID 未设置或为空",
                 "没有可校验的知识库 ID，按无效处理。", EXIT_INVALID)
    if not api_key:
        conclude(False, "校验结论：不通过 —— 环境变量 ZHIPUAI_API_KEY 未设置或为空",
                 "缺少 API Key，无法向平台求证，按无效处理。", EXIT_UNVERIFIED)

    # 对 ID 做 URL 编码，防止其中的特殊字符改变请求路径
    url = BASE_URL + KNOWLEDGE_DETAIL_PATH.format(urllib.parse.quote(kb_id, safe=""))
    print(f"待校验知识库 ID：{kb_id}")
    print(f"校验方式：GET {url}（知识库详情接口）")

    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        conclude(False, "校验结论：不通过 —— 无法确认知识库有效性，按无效处理",
                 f"请求平台接口失败（网络/超时等）：{exc.__class__.__name__}: {exc}",
                 EXIT_UNVERIFIED)

    if resp.status_code != 200:
        conclude(False, "校验结论：不通过 —— 接口返回非 200，无法确认知识库有效性",
                 f"HTTP {resp.status_code}，响应片段：{snippet(resp.text)}",
                 EXIT_UNVERIFIED)

    try:
        payload = resp.json()
    except ValueError:
        conclude(False, "校验结论：不通过 —— 响应不是合法 JSON，无法确认知识库有效性",
                 f"响应片段：{snippet(resp.text)}", EXIT_UNVERIFIED)

    if not isinstance(payload, dict) or "code" not in payload:
        conclude(False, "校验结论：不通过 —— 响应缺少 code 字段，无法确认知识库有效性",
                 f"响应内容：{snippet(str(payload))}", EXIT_UNVERIFIED)

    code = payload.get("code")
    message = payload.get("message", "")

    # 关键判定：这族接口出错时 HTTP 仍是 200，必须看业务码 code 是否为 200
    if str(code) != "200":
        conclude(False, f"校验结论：不通过 —— 知识库 ID 无效（平台返回 code={code}）",
                 f"平台消息：{snippet(str(message))}。"
                 "（例如 100013 表示「知识库不存在」；鉴权/参数类错误也会走业务码）",
                 EXIT_INVALID)

    data = payload.get("data")
    if not isinstance(data, dict) or not data.get("id"):
        conclude(False, "校验结论：不通过 —— 平台返回 code=200 但未带回知识库详情，无法证实 ID 有效",
                 f"响应内容：{snippet(str(payload))}", EXIT_UNVERIFIED)

    if str(data.get("id")) != kb_id:
        conclude(False, "校验结论：不通过 —— 返回的知识库 ID 与待校验 ID 不一致，按无效处理",
                 f"平台返回 id={data.get('id')!r}，待校验 id={kb_id!r}", EXIT_UNVERIFIED)

    print(f"知识库名称：{data.get('name')}")
    print(f"文档数量：{data.get('document_size')}，总字数：{data.get('word_num')}")
    conclude(True, f"校验结论：通过 —— 知识库 {kb_id} 存在，且当前 API Key 可以访问",
             "平台已返回该知识库详情（code=200），可作为上线依据。", EXIT_PASS)


if __name__ == "__main__":
    main()
