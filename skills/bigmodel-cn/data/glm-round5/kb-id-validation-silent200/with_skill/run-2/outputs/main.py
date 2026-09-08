#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验配置里的智谱（bigmodel.cn）托管知识库 ID 是否有效。

用途：上线前的发布流水线卡点。
    - 从环境变量 ZHIPUAI_API_KEY 读取 API Key
    - 从环境变量 ZHIPU_KB_ID 读取待校验的知识库 ID
    - 调用官方「知识库详情」接口 GET /llm-application/open/knowledge/{id}
    - 打印校验结论；退出码 0 = 有效（放行），1 = 无效/无法确认（阻断）

校验原则（fail-closed，宁严勿松）：
    只有 API 明确返回「HTTP 200 + 响应体 code=200 + data.id 与配置一致」才判定有效；
    其余任何情况——网络错误、鉴权失败、响应不是 JSON、code!=200、ID 不匹配等——一律判定无效。
    绝不把无效的 ID 说成有效放上线。

本接口族最大的坑（官方文档 + 2026-09 真实调用验证）：
    /llm-application/open/* 下的接口出错时 HTTP 状态码依然是 200，
    真实结果在响应体的 code 字段里——查一个不存在的知识库，
    返回的是 HTTP 200 + {"code":100013,"message":"知识库不存在"}。
    因此绝不能用 raise_for_status() / HTTP 200 当作成功判据，必须检查响应体 JSON 里的 code。
"""

import os
import sys
import time
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("[无效] 缺少依赖库 requests，请先安装：pip3 install requests", file=sys.stderr)
    sys.exit(1)

API_BASE = "https://open.bigmodel.cn/api"
KB_DETAIL_URL = API_BASE + "/llm-application/open/knowledge/{kb_id}"

CONNECT_TIMEOUT = 10  # 建立连接超时（秒）
READ_TIMEOUT = 15     # 读取响应超时（秒）
MAX_ATTEMPTS = 3      # 仅对网络异常 / HTTP 5xx / 429 重试，减少瞬时抖动造成的误报"无效"
RETRY_BACKOFF = 2     # 两次尝试之间的等待秒数

# embedding_id -> 模型名映射（来自官方文档：3=Embedding-2，11=Embedding-3，12=Embedding-3-pro）
EMBEDDING_MODELS = {3: "Embedding-2", 11: "Embedding-3", 12: "Embedding-3-pro"}


def conclude(ok, reason=None, detail=None):
    """打印校验结论并退出进程：ok=True 退出码 0（放行），否则退出码 1（阻断）。"""
    print("=" * 62)
    if ok:
        print("校验结论：【有效】知识库存在且当前 API Key 可访问，卡点放行（退出码 0）")
    else:
        print("校验结论：【无效】无法确认该知识库 ID 有效，禁止上线（退出码 1）")
        if reason:
            print("原因：" + reason)
        if detail:
            print("详情：" + detail)
    print("=" * 62)
    sys.exit(0 if ok else 1)


def get_with_retry(url, headers):
    """发起 GET 请求，仅对网络异常 / HTTP 5xx / 429 重试。

    返回 (requests.Response, None)；全部尝试失败返回 (None, 错误描述)。
    其余状态码（200、4xx 等）视为服务端的确定性应答，直接交回调用方解读。
    """
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        except requests.RequestException as exc:
            last_error = "网络异常 {}: {}".format(type(exc).__name__, exc)
        else:
            if resp.status_code >= 500 or resp.status_code == 429:
                last_error = "服务端返回 HTTP {}（可重试）".format(resp.status_code)
            else:
                return resp, None
        print("[警告] 第 {}/{} 次尝试失败：{}".format(attempt, MAX_ATTEMPTS, last_error))
        if attempt < MAX_ATTEMPTS:
            print("[信息] {} 秒后重试...".format(RETRY_BACKOFF))
            time.sleep(RETRY_BACKOFF)
    return None, last_error


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()

    # 1. 配置完整性：缺任一项都无法校验，直接判无效
    if not kb_id:
        conclude(False, "环境变量 ZHIPU_KB_ID 未设置或为空，没有可校验的知识库 ID")
    if not api_key:
        conclude(False, "环境变量 ZHIPUAI_API_KEY 未设置或为空，无法发起校验")

    # quote(safe="") 把 ID 编码为单个路径段，防止配置值里混入 "/" 等字符拼出别的接口路径
    url = KB_DETAIL_URL.format(kb_id=quote(kb_id, safe=""))
    print("[信息] 待校验知识库 ID（ZHIPU_KB_ID）：{}".format(kb_id))
    print("[信息] 调用知识库详情接口：GET {}".format(url))

    resp, transport_error = get_with_retry(
        url, {"Authorization": "Bearer " + api_key, "Accept": "application/json"})
    if resp is None:
        # fail-closed：连校验都没完成，绝不能放行
        conclude(False,
                 "API 请求未能完成（{} 次尝试均失败），按无效处理".format(MAX_ATTEMPTS),
                 transport_error)

    status = resp.status_code
    body_text = resp.text.strip()
    snippet = body_text[:300] or "<响应体为空>"

    # 2. HTTP 层：非 200 不可能是一次成功的详情查询
    if status != 200:
        if status in (401, 403):
            conclude(False,
                     "HTTP {}：API Key 无效/过期，或对该知识库没有访问权限".format(status),
                     snippet)
        conclude(False, "API 返回 HTTP {} 而非 200，按无效处理".format(status), snippet)

    # 3. 响应体必须是 JSON 对象（注意：即使响应体是错误 JSON，HTTP 也可能是 200）
    try:
        payload = resp.json()
    except ValueError:
        conclude(False, "HTTP 200 但响应体不是合法 JSON，无法确认知识库有效性", snippet)
    if not isinstance(payload, dict):
        conclude(False, "HTTP 200 但响应体不是 JSON 对象，无法确认知识库有效性", str(payload)[:300])

    print("[信息] API 返回：HTTP 200，code={!r}，message={!r}".format(
        payload.get("code"), payload.get("message")))

    # 4. 核心判据：这个接口族出错时 HTTP 仍是 200，必须看响应体 code 是否为 200
    if "code" not in payload:
        conclude(False, "响应体缺少 code 字段（该接口族出错时 HTTP 仍为 200，只能靠 code 判断），按无效处理", snippet)
    if str(payload.get("code")).strip() != "200":
        conclude(False,
                 "API 明确返回失败：知识库不存在或不可访问（如 code=100013 即「知识库不存在」）",
                 "code={!r}，message={!r}".format(payload.get("code"), payload.get("message")))

    data = payload.get("data")
    if not isinstance(data, dict) or not str(data.get("id", "")).strip():
        conclude(False, "响应体 code=200 但缺少有效的知识库数据（data.id 为空），按无效处理", str(payload)[:300])

    # 5. 纵深防御：确认服务端返回的就是配置里那个库，防止异常应答被误判为通过
    returned_id = str(data.get("id")).strip()
    if returned_id != kb_id:
        conclude(False, "API 返回的知识库 ID 与配置值不一致，疑似配置有误或应答异常",
                 "配置 ID={}，API 返回={}".format(kb_id, returned_id))

    # ---- 走到这里才算明确确认：知识库存在，且当前 API Key 可访问 ----
    embedding_id = data.get("embedding_id")
    print("[信息] 知识库名称：{}".format(data.get("name") or "<未返回>"))
    print("[信息] 向量化模型：{}（embedding_id={}）".format(
        EMBEDDING_MODELS.get(embedding_id, "未知模型"), embedding_id))
    document_size = data.get("document_size")
    if document_size is not None:
        print("[信息] 文档数量：{}".format(document_size))
    if data.get("word_num") is not None:
        print("[信息] 总字数：{}".format(data.get("word_num")))
    if document_size == 0:
        # ID 本身有效所以不阻断，但空库上线后检索必然为空，必须显式提醒
        print("[警告] 该知识库存在但文档数量为 0，上线后检索将召回不到任何内容")
        print("[警告] ID 本身有效，本次卡点仍放行；请确认是否应先上传文档再上线")

    conclude(True)


if __name__ == "__main__":
    main()
