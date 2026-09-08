#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前校验智谱(bigmodel.cn)托管知识库 ID 是否真实存在、可用。

挂在发布流水线做卡点:
  - 校验通过(判定有效) -> 退出码 0,放行;
  - 其余任何情况        -> 退出码 1,拦截。

判定原则:宁可误报无效,绝不把无效 ID 说成有效。只有当
「HTTP 状态码 == 200」且「响应体 code == 200」且「data 结构可信、ID 一致」
同时成立才判定有效;环境变量缺失、网络错误、超时、响应不可解析、
业务错误码、ID 不匹配等一律判定无效。

为什么不能只靠 raise_for_status():这套知识库接口(/llm-application/open/*)
出错时 HTTP 状态码依然返回 200,真实结果在响应体的 code 字段里——查询一个
不存在的知识库,返回的是 HTTP 200 + {"code":100013,"message":"知识库不存在"}。
所以必须显式校验响应体的 code,HTTP 层通过只是必要条件,不是充分条件。

接口:GET {BASE_URL}/llm-application/open/knowledge/{id}
鉴权:Authorization: Bearer <ZHIPUAI_API_KEY>

用法:
    ZHIPUAI_API_KEY=xxx ZHIPU_KB_ID=know-xxx python3 main.py
"""

import os
import sys
import time
from typing import NoReturn

try:
    import requests
except ImportError:
    print("[FAIL] 缺少 requests 库,请先安装:pip install requests")
    print("校验结论:知识库 ID 无效(校验未通过,已拦截)")
    sys.exit(1)

BASE_URL = "https://open.bigmodel.cn/api"
KNOWLEDGE_DETAIL_PATH = "/llm-application/open/knowledge/{kb_id}"

REQUEST_TIMEOUT_SECONDS = 15  # 单次请求超时,防止流水线被挂死
MAX_ATTEMPTS = 3              # 网络/服务端瞬态错误的重试次数,最终仍失败则判无效
RETRY_BACKOFF_SECONDS = 2     # 重试间隔


def fail(reason: str) -> NoReturn:
    """判定无效:打印结论并以非零退出码结束,阻断流水线。"""
    print(f"[FAIL] {reason}")
    print("校验结论:知识库 ID 无效(校验未通过,已拦截)")
    sys.exit(1)


def evaluate_response(resp: requests.Response, kb_id: str) -> NoReturn:
    """逐层校验响应,全部通过才判定有效;任何一层不过都立即拦截。"""
    # 第一层:HTTP 状态码。注意这套接口出错时也可能回 200,这只是必要条件。
    if resp.status_code != 200:
        fail(
            f"HTTP 状态码为 {resp.status_code}(预期 200),"
            f"响应片段:{resp.text[:200]!r}"
        )

    # 第二层:响应体必须是合法的 JSON 对象。
    try:
        body = resp.json()
    except ValueError:
        fail(f"响应体不是合法 JSON,响应片段:{resp.text[:200]!r}")
    if not isinstance(body, dict):
        fail(f"响应体不是 JSON 对象:{str(body)[:200]!r}")

    # 第三层(关键):业务错误码。HTTP 200 不代表成功——查不存在的知识库
    # 返回的就是 HTTP 200 + code=100013"知识库不存在"。
    code = body.get("code")
    if str(code) != "200":
        hint = "(100013 通常即「知识库不存在」)" if str(code) == "100013" else ""
        fail(f"接口返回业务错误:code={code!r}, message={body.get('message')!r}{hint}")

    # 第四层:成功负载必须携带可信的 data,且其中的 id 与待校验 ID 一致。
    data = body.get("data")
    if not isinstance(data, dict):
        fail(f"响应缺少可用的 data 对象,无法确认知识库存在:{str(body)[:200]!r}")
    returned_id = data.get("id")
    if returned_id is not None and str(returned_id) != kb_id:
        fail(f"返回的知识库 id({returned_id!r})与待校验 ID({kb_id!r})不一致")

    # 走到这里才算真正通过:明确判定有效。
    print("[PASS] 知识库校验通过:ID 存在且详情接口可正常访问")
    print(f"  - 知识库 ID : {returned_id if returned_id is not None else kb_id}")
    print(f"  - 名称      : {data.get('name')!r}")
    print(f"  - 文档数量  : {data.get('document_size')}")
    print(f"  - 总字数    : {data.get('word_num')}")
    print(f"  - 向量模型  : embedding_id={data.get('embedding_id')}")
    print("校验结论:知识库 ID 有效")
    sys.exit(0)


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("环境变量 ZHIPUAI_API_KEY 未设置或为空,无法发起校验")

    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()
    if not kb_id:
        fail("环境变量 ZHIPU_KB_ID 未设置或为空,无法发起校验")

    # ID 会拼进 URL 路径:含 / ? # 或内嵌空白的值必然不是合法知识库 ID,
    # 直接判无效,不发起请求(也避免拼出预期外的路径)。
    if any(ch in kb_id for ch in "/?#") or any(ch.isspace() for ch in kb_id):
        fail(f"ZHIPU_KB_ID 含非法字符(不允许 /、?、# 或空白):{kb_id!r}")

    url = BASE_URL + KNOWLEDGE_DETAIL_PATH.format(kb_id=kb_id)
    print(f"待校验知识库 ID:{kb_id}")
    print(f"校验接口:{url}")

    headers = {"Authorization": f"Bearer {api_key}"}
    last_error = "未知错误"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_error = f"请求异常:{type(exc).__name__}: {exc}"
        else:
            # 5xx/408/429 视为瞬态错误,重试;其余状态码交由逐层校验判定。
            if resp.status_code >= 500 or resp.status_code in (408, 429):
                last_error = f"HTTP {resp.status_code}"
            else:
                evaluate_response(resp, kb_id)
        suffix = "将重试" if attempt < MAX_ATTEMPTS else "停止重试"
        print(f"第 {attempt}/{MAX_ATTEMPTS} 次尝试失败({last_error}),{suffix}")
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS)

    fail(
        f"连续 {MAX_ATTEMPTS} 次尝试均失败,最后错误:{last_error}"
        "(无法确认有效,按无效拦截)"
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # 兜底:未预料的异常也按"无效"拦截,绝不带病放行
        fail(f"校验过程出现未预料的异常:{type(exc).__name__}: {exc}")
