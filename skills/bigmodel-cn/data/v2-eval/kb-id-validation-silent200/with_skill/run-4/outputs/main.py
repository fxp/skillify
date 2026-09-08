#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前卡点：校验配置里的智谱托管知识库 ID 是否存在且可用。

用法（无命令行参数，全部走环境变量）：

    ZHIPUAI_API_KEY=xxx ZHIPU_KB_ID=know-xxx python3 main.py

退出码（供发布流水线判断）：
    0  校验通过，知识库存在且当前可用于检索
    1  校验不通过（知识库不存在 / 鉴权失败 / 网络异常 / 结构异常 / 无就绪文档……）
    2  本地配置缺失（ZHIPUAI_API_KEY 或 ZHIPU_KB_ID 未设置）

设计原则：这是发布卡点，**宁可误报无效，绝不把无效 ID 说成有效**。
任何网络错误、非预期 HTTP 状态、无法解析的响应、结构异常，一律判"无效"并阻断，
不存在任何"出错后猜测放行"的路径。

两个来自实测的坑（官方文档未写明，务必不要改掉对应逻辑）：
  1) /llm-application/open/* 这族接口业务出错时 HTTP 状态码仍然是 200，
     真实结果在响应体 code 里（如 {"code":100013,"message":"知识库不存在"}）。
     所以 resp.raise_for_status() 在这里永远不会触发，成功与否必须判 body["code"] == 200。
  2) 上传成功 ≠ 文档可检索：向量化在后台异步执行，失败时没有任何通知，
     检索端永远返回 200 + 空数组，与"没有相关内容"无法区分。
     所以"能不能用"必须检查文档的 embedding_stat（0=处理中 1=成功 2=失败）
     和 failInfo，不能只看知识库详情接口返回 code=200。
"""

import os
import sys
import time
import urllib.parse

import requests

BASE_URL = "https://open.bigmodel.cn/api"
REQUEST_TIMEOUT = (10, 30)    # (连接超时, 读超时)，单位秒
MAX_ATTEMPTS = 3              # 仅对网络层错误（连接失败/超时）重试；收到响应绝不重试
PAGE_SIZE = 100               # 文档列表分页大小
MAX_DOCUMENTS_TO_SCAN = 1000  # 文档就绪检查最多扫描的文档数，超出则如实报告"部分检查"

EXIT_OK = 0        # 校验通过
EXIT_INVALID = 1   # 校验不通过，一律不放行
EXIT_CONFIG = 2    # 环境变量缺失


class ValidationError(Exception):
    """校验不通过。message 是给人看的原因，会直接打进结论。"""


def call_api(method, path, api_key, params=None):
    """发请求并把一切异常情形统一转成 ValidationError（失败即抛，绝不吞掉）。

    只对"根本没收到响应"的网络层错误做有限重试——重试不会把坏 ID 变成好 ID
    （坏 ID 会收到 HTTP 200 + code=100013 的确定性响应，照样判失败），
    只是为了少一些网络抖动导致的误报。收到任何响应后一律不再重试。
    """
    url = BASE_URL + path
    headers = {"Authorization": "Bearer " + api_key}

    resp = None
    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.request(
                method, url, headers=headers, params=params, timeout=REQUEST_TIMEOUT
            )
            break
        except requests.RequestException as exc:
            last_err = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(attempt)  # 1s、2s 退避
    if resp is None:
        raise ValidationError(
            "网络异常：请求 %s %s 连续 %d 次失败（%s），无法确认知识库状态，按无效处理"
            % (method, url, MAX_ATTEMPTS, last_err)
        )

    # 注意：这族接口业务出错时 HTTP 也是 200，所以这里只拦网关/鉴权层的非 200；
    # 成功与否的最终判据是下面的 body["code"]。
    if resp.status_code != 200:
        raise ValidationError(
            "接口层异常：%s %s 返回 HTTP %d（非 200），响应片段：%s"
            % (method, path, resp.status_code, resp.text[:300])
        )

    try:
        body = resp.json()
    except ValueError:
        raise ValidationError(
            "响应无法解析：%s %s 返回了非 JSON 内容：%s"
            % (method, path, resp.text[:300])
        )

    if not isinstance(body, dict) or "code" not in body:
        raise ValidationError(
            "响应结构异常：%s %s 的返回里缺少 code 字段：%s"
            % (method, path, repr(body)[:300])
        )

    code = body.get("code")
    message = body.get("message", "")
    print("  [API] %s %s -> HTTP %d, code=%s, message=%r" % (method, path, resp.status_code, code, message))

    # ★ 关键判定：HTTP 200 不代表成功，必须业务码 code == 200
    if code != 200:
        hint = ""
        if code == 100013:
            hint = "（100013 = 知识库不存在：ID 拼错、已被删除，或不属于当前 API Key 的账号）"
        raise ValidationError(
            "业务失败：%s %s 返回 code=%s, message=%r %s"
            % (method, path, code, message, hint)
        )
    return body


def fetch_kb_detail(api_key, kb_id):
    """第一步：查知识库详情，确认 ID 真实存在。"""
    path = "/llm-application/open/knowledge/" + urllib.parse.quote(kb_id, safe="")
    body = call_api("GET", path, api_key=api_key)
    data = body.get("data")
    if not isinstance(data, dict):
        raise ValidationError(
            "知识库详情响应结构异常：data 不是对象，实际类型 %s" % type(data).__name__
        )
    returned_id = str(data.get("id", ""))
    if returned_id != kb_id:
        raise ValidationError(
            "返回的知识库 id（%r）与待校验 id（%r）不一致，按无效处理" % (returned_id, kb_id)
        )
    return data


def scan_documents(api_key, kb_id):
    """第二步：拉取文档列表，供后续判断向量化就绪状态。"""
    docs = []
    page = 1
    truncated = False
    while True:
        body = call_api(
            "GET",
            "/llm-application/open/document",
            api_key=api_key,
            params={"knowledge_id": kb_id, "page": page, "size": PAGE_SIZE},
        )
        data = body.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("list"), list):
            raise ValidationError(
                "文档列表响应结构异常：data.list 不是数组：%s" % repr(data)[:300]
            )
        batch = data["list"]
        docs.extend(batch)
        total = data.get("total")
        if not batch:  # 空页即到底
            break
        if isinstance(total, int) and len(docs) >= total:
            break
        if len(docs) >= MAX_DOCUMENTS_TO_SCAN:
            truncated = True
            break
        page += 1
    return docs, truncated


def classify_documents(docs):
    """按 embedding_stat 把文档分成 就绪/处理中/失败 三类。

    0=处理中、1=成功、2=失败 是实测语义（文档未完整枚举）。判定从保守出发：
    failInfo 里带错误信息的一律算失败；状态值不在已知范围的一律算失败。
    """
    ready, processing, failed = [], [], []
    for doc in docs:
        name = str(doc.get("name") or doc.get("id") or "未命名文档")
        stat = doc.get("embedding_stat")
        fail_msg = ""
        fail_info = doc.get("failInfo")
        if isinstance(fail_info, dict):
            fcode = fail_info.get("embedding_code")
            fmsg = str(fail_info.get("embedding_msg") or "").strip()
            if fcode not in (None, 0) or fmsg:
                fail_msg = "embedding_code=%s, embedding_msg=%s" % (fcode, fmsg)
        if stat == 1 and not fail_msg:
            ready.append(name)
        elif stat == 0 and not fail_msg:
            processing.append(name)
        else:
            failed.append((name, stat, fail_msg))
    return ready, processing, failed


def run_checks(api_key, kb_id):
    """执行全部校验。通过则返回通过摘要；不通过抛 ValidationError。"""
    print("[1/2] 校验知识库是否存在（GET /llm-application/open/knowledge/{id}）……")
    detail = fetch_kb_detail(api_key, kb_id)
    print(
        "  知识库存在：name=%r, document_size=%s, word_num=%s, embedding_id=%s"
        % (
            detail.get("name"),
            detail.get("document_size"),
            detail.get("word_num"),
            detail.get("embedding_id"),
        )
    )

    print("[2/2] 校验知识库是否可用（检查文档向量化状态）……")
    docs, truncated = scan_documents(api_key, kb_id)
    if not docs:
        raise ValidationError(
            "知识库存在但没有任何文档：检索接口将永远返回空结果，等价于不可用。"
            "请先上传文档并等向量化完成。"
        )
    ready, processing, failed = classify_documents(docs)
    print(
        "  文档统计：共 %d 篇，就绪 %d，处理中 %d，失败 %d"
        % (len(docs), len(ready), len(processing), len(failed))
    )
    if truncated:
        print(
            "  注意：文档数超过扫描上限 %d，仅检查了前 %d 篇（部分检查）。"
            % (MAX_DOCUMENTS_TO_SCAN, len(docs))
        )
    if failed:
        sample = "; ".join(
            "%s (embedding_stat=%s%s)" % (n, s, ", " + m if m else "")
            for n, s, m in failed[:5]
        )
        more = " ……等共 %d 篇" % len(failed) if len(failed) > 5 else ""
        raise ValidationError(
            "有 %d 篇文档向量化失败，这些内容在检索时会静默缺失"
            "（检索端只会返回 200 + 空结果，不会报错）：%s%s。"
            "请删除或重新向量化失败文档。" % (len(failed), sample, more)
        )
    if not ready:
        raise ValidationError(
            "全部 %d 篇文档仍在向量化处理中（embedding_stat=0），此刻检索不到任何内容。"
            "请等向量化完成后再执行本卡点。" % len(docs)
        )
    if processing:
        print(
            "  警告：仍有 %d 篇文档在向量化处理中，这些文档暂时检索不到（不影响本次结论）。"
            % len(processing)
        )
    return "知识库 %s（%s）存在且可用：%d 篇文档已就绪" % (
        kb_id,
        detail.get("name"),
        len(ready),
    )


def conclude(ok, summary=None, reason=None):
    print("=" * 62)
    if ok:
        print("校验结论：有效 —— %s" % summary)
        print("=" * 62)
        print("KB_VALIDATION=PASS")
        sys.exit(EXIT_OK)
    else:
        print("校验结论：无效 —— 已按失败处理，阻断发布，不放行。")
        print("失败原因：%s" % reason)
        print("=" * 62)
        print("KB_VALIDATION=FAIL")
        sys.exit(EXIT_INVALID)


def main():
    print("=" * 62)
    print("智谱托管知识库 ID 上线前校验（发布卡点）")
    print("=" * 62)

    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()
    raw_kb_id = os.environ.get("ZHIPU_KB_ID") or ""
    kb_id = raw_kb_id.strip()
    if raw_kb_id != kb_id:
        print("注意：ZHIPU_KB_ID 含首尾空白，已去除（%r -> %r）" % (raw_kb_id, kb_id))

    if not api_key:
        print("配置错误：环境变量 ZHIPUAI_API_KEY 未设置或为空。")
        print("KB_VALIDATION=FAIL")
        sys.exit(EXIT_CONFIG)
    if not kb_id:
        print("配置错误：环境变量 ZHIPU_KB_ID 未设置或为空。")
        print("KB_VALIDATION=FAIL")
        sys.exit(EXIT_CONFIG)

    print("待校验知识库 ID：%s" % kb_id)
    try:
        summary = run_checks(api_key, kb_id)
    except ValidationError as exc:
        conclude(ok=False, reason=str(exc))
    conclude(ok=True, summary=summary)


if __name__ == "__main__":
    main()
