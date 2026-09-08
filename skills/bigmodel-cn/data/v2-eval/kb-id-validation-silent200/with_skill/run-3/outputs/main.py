#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上线前校验智谱（bigmodel.cn）托管知识库 ID 是否存在、是否可用。

用途：
    作为发布流水线的卡点脚本：校验环境变量 ZHIPU_KB_ID 指向的知识库确实存在，
    且当前 ZHIPUAI_API_KEY 有权限读取它。

设计原则（fail-closed：宁可误报无效，绝不放过坏 ID）：
    * 任何无法**明确证明有效**的情况——网络错误、超时、重定向、HTTP 非 200、
      响应不是 JSON、业务 code 非 200、data 缺失、回显 ID 不一致——
      一律判为"校验不通过"，退出码 1，阻断上线。
    * 只有业务 code == 200 且响应 data.id 与待校验 ID 完全一致，才判"有效"。

为什么不能只看 HTTP 状态码（实测坑，官方文档未写）：
    llm-application/open/* 这一族接口出错时 HTTP 状态码**依然是 200**，
    真实结果在响应体的 code 字段里：
        - 知识库不存在 -> HTTP 200 + {"code":100013,"message":"知识库不存在"}
        - 成功         -> HTTP 200 + {"code":200,  "data":{...}, "message":"success"}
    因此 resp.raise_for_status() 在这里永远不会触发，必须判断 body["code"]。

为什么不用 /knowledge/retrieve 做可用性探测：
    检索接口在"文档向量化失败"和"确实没有相关内容"时都返回 HTTP 200 + 空数组，
    无法区分，不能作为卡点信号。所以本脚本以"详情接口可读到且 ID 回显一致"
    作为有效性判据；知识库内文档是否向量化完成（embedding_stat==1）不属于
    ID 校验的范围，仅在文档数为 0 时给出警告。

环境变量：
    ZHIPU_KB_ID     待校验的知识库 ID（必填）
    ZHIPUAI_API_KEY 智谱开放平台 API Key（必填，https://bigmodel.cn/usercenter/proj-mgmt/apikeys）

退出码：
    0  校验通过：知识库存在且当前 Key 可访问，允许上线
    1  校验不通过：ID 确认无效，或无法确认有效（一律按无效阻断）

用法：
    python3 main.py
"""

import os
import sys
import time
from urllib.parse import quote

import requests

API_BASE = "https://open.bigmodel.cn/api"
KB_DETAIL_PATH = "/llm-application/open/knowledge/{kb_id}"

REQUEST_TIMEOUT = 15  # 单次请求超时（秒）
MAX_ATTEMPTS = 2      # 网络/网关瞬时故障的重试次数（只减少误报，不放松判定标准）
RETRY_BACKOFF = 2     # 重试间隔（秒）

# 业务码：200 = 成功；100013 = 知识库不存在（实测值，官方文档未枚举错误码）
CODE_OK = "200"
CODE_KB_NOT_FOUND = "100013"

EXIT_PASS = 0
EXIT_BLOCK = 1


def fail(reason: str, hint: str = "", confirmed_invalid: bool = False) -> int:
    """打印"校验不通过"结论并返回失败退出码（fail-closed）。"""
    print()
    if confirmed_invalid:
        print("校验结论：不通过 —— 知识库 ID 确认无效（阻断上线）")
    else:
        print("校验结论：不通过 —— 无法确认有效，按无效处理（阻断上线）")
    print(f"  原因：{reason}")
    if hint:
        print(f"  提示：{hint}")
    return EXIT_BLOCK


def validate(kb_id: str, api_key: str) -> int:
    """调用知识库详情接口校验 kb_id，返回退出码。"""
    url = API_BASE + KB_DETAIL_PATH.format(kb_id=quote(kb_id, safe=""))
    headers = {"Authorization": f"Bearer {api_key}"}

    resp = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,  # 正常 API 不应发生重定向；出现即视为异常
            )
        except requests.RequestException as exc:
            # 网络/超时错误：重试后仍失败则 fail-closed，绝不猜测为有效
            if attempt < MAX_ATTEMPTS:
                print(f"  第 {attempt} 次尝试请求异常（{exc.__class__.__name__}），{RETRY_BACKOFF}s 后重试...")
                time.sleep(RETRY_BACKOFF)
                continue
            return fail(
                f"请求失败（网络/超时）：{exc.__class__.__name__}: {exc}",
                "请检查网络与 open.bigmodel.cn 的连通性后重跑。",
            )

        # 网关类 5xx 可能是瞬时故障，重试一次；最终仍失败会落到下面非 200 分支
        if 500 <= resp.status_code < 600 and attempt < MAX_ATTEMPTS:
            print(f"  第 {attempt} 次尝试收到 HTTP {resp.status_code}，{RETRY_BACKOFF}s 后重试...")
            time.sleep(RETRY_BACKOFF)
            continue
        break

    if resp is None:  # 防御性分支，正常不可达
        return fail("请求未能发出。")

    # 1) HTTP 状态码：该族接口正常时恒为 200；其他值说明链路异常，无法确认
    if resp.status_code != 200:
        return fail(
            f"HTTP 状态码 {resp.status_code}（预期 200），无法确认知识库有效。响应片段：{resp.text[:300]!r}",
        )

    # 2) 响应必须是合法 JSON 对象（例如被网关/代理劫持时会返回 HTML）
    try:
        body = resp.json()
    except ValueError:
        return fail(f"响应不是合法 JSON：{resp.text[:300]!r}")
    if not isinstance(body, dict):
        return fail(f"响应体不是 JSON 对象：{str(body)[:300]!r}")

    # 3) 关键判定：业务 code（这族接口出错时 HTTP 仍是 200，真相只在 code 里）
    code = str(body.get("code", ""))
    message = str(body.get("message", ""))

    if code != CODE_OK:
        if code == CODE_KB_NOT_FOUND:
            return fail(
                f"知识库不存在（code={code}, message={message!r}）。",
                "请核对 ZHIPU_KB_ID 是否与控制台中的知识库 ID 完全一致。",
                confirmed_invalid=True,
            )
        return fail(
            f"接口返回业务错误（code={code}, message={message!r}），无法确认知识库有效。",
            "常见原因：API Key 无效/无权限、账号或配额问题。请核对 ZHIPUAI_API_KEY 后重跑。",
        )

    # 4) code == 200 仍需核对 data，防止把"看似成功"的响应当成有效
    data = body.get("data")
    if not isinstance(data, dict):
        return fail(f"code=200 但 data 缺失或不是对象：{str(body)[:300]!r}")

    echoed_id = str(data.get("id", ""))
    if not echoed_id:
        return fail(f"code=200 但响应 data.id 为空，无法确认知识库身份：{str(data)[:300]!r}")
    if echoed_id != kb_id:
        return fail(
            f"响应回显的知识库 ID（{echoed_id!r}）与待校验 ID（{kb_id!r}）不一致，按无效处理。"
        )

    # ---- 全部检查通过 ----
    print()
    print("校验结论：通过 —— 知识库存在且当前 API Key 可访问（允许上线）")
    print(f"  知识库 ID    : {kb_id}")
    print(f"  名称         : {data.get('name', '(未返回)')}")
    print(f"  文档数量     : {data.get('document_size', '(未返回)')}")
    print(f"  总字数       : {data.get('word_num', '(未返回)')}")
    print(f"  向量化模型 ID: {data.get('embedding_id', '(未返回)')}")

    doc_size = data.get("document_size")
    if isinstance(doc_size, int) and doc_size == 0:
        print("  [警告] 该知识库当前没有任何文档：ID 本身有效，但检索不会返回任何内容。")
        print("         若上线后依赖检索结果，请先上传文档并确认向量化完成（文档 embedding_stat==1）。")

    return EXIT_PASS


def main() -> int:
    kb_id = (os.environ.get("ZHIPU_KB_ID") or "").strip()
    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()

    print("=" * 64)
    print("智谱托管知识库 ID 上线前校验（fail-closed：无法确认有效即阻断）")
    print("=" * 64)

    if not kb_id:
        return fail("环境变量 ZHIPU_KB_ID 未设置或为空。")
    if not api_key:
        return fail(
            "环境变量 ZHIPUAI_API_KEY 未设置或为空。",
            "请到 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取 Key 并通过环境变量注入。",
        )

    print(f"待校验知识库 ID：{kb_id}")
    print(f"校验接口      ：GET {KB_DETAIL_PATH.format(kb_id='<id>')}")
    return validate(kb_id, api_key)


if __name__ == "__main__":
    sys.exit(main())
