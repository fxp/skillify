#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把同目录下的 faq.txt 灌进智谱开放平台（bigmodel.cn）托管知识库。

流程：
  1. 读取环境变量 ZHIPUAI_API_KEY 和同目录 faq.txt
  2. 创建知识库                 POST   /llm-application/open/knowledge
  3. 上传 faq.txt              POST   /llm-application/open/document/upload_document/{kb_id}
  4. 等待文档解析/向量化        GET    /llm-application/open/document/{doc_id}
  5. 【关键校验】真实检索一次   POST   /llm-application/open/knowledge/retrieve
     —— 官方 FAQ 明确说明：只有文档状态到「处理完成」后才能检索。
        上传接口返回成功 ≠ 可检索，所以这里必须真实发起一次检索，
        检索不到内容就明确报错并给出诊断信息，绝不报喜不报忧。
  6. 无论成功失败，最后都删除本次创建的知识库，并确认删除成功。

接口依据（智谱官方文档）: https://docs.bigmodel.cn/api-reference/知识库-api/
仅依赖 requests，可直接 `python3 main.py` 运行。
"""

import os
import re
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------- 基本配置

API_BASE = "https://open.bigmodel.cn/api/llm-application/open"

# embedding_id: 3=Embedding-2, 11=Embedding-3, 12=Embedding-3-pro（官方枚举）
EMBEDDING_ID = 11

VERIFY_TIMEOUT = 600       # 「等解析 + 检索校验」总预算（秒）
POLL_DOC_INTERVAL = 5      # 轮询文档状态的间隔（秒）
POLL_RETRIEVE_INTERVAL = 10  # 检索探测的间隔（秒）
HTTP_TIMEOUT = (10, 60)    # (连接超时, 读超时)

# embedding_stat 官方文档未公布枚举，FAQ 给出的状态流是：
#   数据处理中 → 索引构建中 → 处理完成（另有「数据异常」失败态）。
# 文档示例里 embedding_stat=0 与 failInfo(失败码) 同现，据此保守约定：
DOC_STAT_DONE = 3          # 疑似「处理完成」；状态没到 3 不算失败，只是继续等
# 真正的失败判定只认 failInfo（embedding_code / embedding_msg），
# 最终成败以第 5 步的真实检索结果为准。

KB_NAME_PREFIX = "faq-upload-verify"


class StepError(Exception):
    """流程失败，message 会原样展示给用户。"""


class ApiError(StepError):
    """HTTP / 业务码层面的接口错误。"""


# ---------------------------------------------------------------- 接口封装

def api(session, method, path, *, params=None, json_body=None, files=None, timeout=HTTP_TIMEOUT):
    """调用知识库 API，统一校验 HTTP 状态与业务码（code != 200 视为失败）。"""
    url = API_BASE + path
    try:
        resp = session.request(method, url, params=params, json=json_body,
                               files=files, timeout=timeout)
    except requests.RequestException as exc:
        raise ApiError(f"网络请求失败 [{method} {url}]: {exc}") from exc

    try:
        body = resp.json()
    except ValueError:
        raise ApiError(
            f"接口返回非 JSON [{method} {path}]: HTTP {resp.status_code}, "
            f"body={resp.text[:200]!r}") from None

    biz_code = body.get("code")
    if resp.status_code >= 400 or (biz_code is not None and biz_code != 200):
        raise ApiError(
            f"接口报错 [{method} {path}]: HTTP {resp.status_code}, "
            f"code={biz_code}, message={body.get('message')!r}")
    return body


def doc_failure_reason(doc):
    """从文档详情里提取向量化失败原因；没失败返回 None。"""
    info = doc.get("failInfo") or {}
    code = info.get("embedding_code")
    msg = info.get("embedding_msg")
    if (code not in (None, 0)) or (msg not in (None, "", "None")):
        return f"文档向量化失败: embedding_code={code}, embedding_msg={msg}"
    return None


# ---------------------------------------------------------------- 探测用的查询语句

def pick_probe_query(text):
    """从 faq.txt 里挑一行有实际内容的句子当检索 query（内容不可预知，动态生成）。"""
    best = ""
    for raw in text.splitlines():
        line = raw.strip()
        line = re.sub(r"^[\s>*#\-•·]+", "", line)
        line = re.sub(r"^\d{1,3}[.、．)）]?\s*", "", line)
        line = re.sub(r"^(?:Q|问|Question)[:：.、]?\s*", "", line, flags=re.IGNORECASE)
        line = line.strip()
        if 8 <= len(line) <= 80:
            return line[:50]
        if len(line) > len(best):
            best = line
    if best:
        return best[:50]
    return text.strip()[:50] or "常见问题"


def probe_nuggets(query):
    """从 query 里抽「内容指纹」：中文相邻二字组 + 长英文/数字词，用于核对检索内容。"""
    cjk = "".join(re.findall(r"[一-鿿]", query))
    nuggets = {cjk[i:i + 2] for i in range(len(cjk) - 1)}
    nuggets |= set(re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{3,}", query))
    return nuggets


# ---------------------------------------------------------------- 主流程各步

def create_knowledge_base(session):
    name = f"{KB_NAME_PREFIX}-{time.strftime('%Y%m%d%H%M%S')}"
    body = api(session, "POST", "/knowledge", json_body={
        "name": name,
        "description": "临时知识库：faq.txt 上传+可检索性校验，用完即删",
        "embedding_id": EMBEDDING_ID,
    })
    kb_id = (body.get("data") or {}).get("id")
    if not kb_id:
        raise ApiError(f"创建知识库成功但未返回 id: {body}")
    print(f"[1/5] 创建知识库 ... OK  name={name}  id={kb_id}")
    return kb_id


def upload_document(session, kb_id, faq_path):
    with open(faq_path, "rb") as fh:
        body = api(session, "POST", f"/document/upload_document/{kb_id}",
                   files={"files": (faq_path.name, fh, "text/plain")},
                   timeout=(10, 300))
    data = body.get("data") or {}
    for fail in data.get("failedInfos") or []:
        raise ApiError(f"上传失败: 文件 {fail.get('fileName')} 原因 {fail.get('failReason')}")
    success = data.get("successInfos") or []
    doc_id = None
    for item in success:
        if item.get("fileName") == faq_path.name or len(success) == 1:
            doc_id = item.get("documentId") or item.get("document_id")
            break
    if not doc_id:
        raise ApiError(f"上传接口未返回文档 id: {body}")
    print(f"[2/5] 上传文档 {faq_path.name} ... OK  documentId={doc_id}")
    return doc_id


def wait_until_retrievable(session, kb_id, doc_id, query):
    """
    第 3、4 步合并：先轮询文档向量化状态，再用真实检索做最终裁决。
    只有检索真的命中本知识库的内容才算通过。
    """
    start = time.monotonic()
    deadline = start + VERIFY_TIMEOUT            # 总预算
    status_deadline = start + VERIFY_TIMEOUT * 0.6  # 状态轮询最多占 60%，剩余留给检索探测
    consecutive_errors = 0
    last_doc = {}

    print("[3/5] 等待文档解析 / 向量化（状态流: 数据处理中→索引构建中→处理完成）...")
    while time.monotonic() < status_deadline:
        try:
            detail = api(session, "GET", f"/document/{doc_id}")
            consecutive_errors = 0
        except ApiError as exc:
            consecutive_errors += 1
            if consecutive_errors >= 5:
                raise ApiError(f"连续 5 次查询文档状态失败，放弃: {exc}") from exc
            time.sleep(POLL_DOC_INTERVAL)
            continue

        last_doc = detail.get("data") or {}
        reason = doc_failure_reason(last_doc)
        if reason:
            raise StepError(f"[3/5] {reason}（文档 id={doc_id}，知识库 id={kb_id}）")

        stat = last_doc.get("embedding_stat")
        waited = int(time.monotonic() - start)
        print(f"      已等 {waited:>3}s  embedding_stat={stat}  word_num={last_doc.get('word_num')}")
        if stat == DOC_STAT_DONE:
            break
        time.sleep(POLL_DOC_INTERVAL)

    print("[4/5] 检索校验：用文件原文片段作为 query 真实检索一次 ...")
    nuggets = probe_nuggets(query)
    while True:
        try:
            body = api(session, "POST", "/knowledge/retrieve", json_body={
                "query": query,
                "knowledge_ids": [kb_id],
                "top_k": 5,
                "recall_method": "mixed",
            })
            consecutive_errors = 0
        except ApiError as exc:
            consecutive_errors += 1
            if consecutive_errors >= 5:
                raise ApiError(f"连续 5 次检索请求失败，放弃: {exc}") from exc
            if time.monotonic() > deadline:
                raise StepError(f"检索校验失败：检索接口不可用。最后错误: {exc}")
            time.sleep(POLL_RETRIEVE_INTERVAL)
            continue

        hits = body.get("data") or []
        if isinstance(hits, dict):        # 防御：兼容 data.list 结构
            hits = hits.get("list") or []

        matched = []
        foreign = []
        for item in hits:
            meta = item.get("metadata") or {}
            if kb_id in (meta.get("knowledge_id"),) or doc_id in (meta.get("doc_id"),):
                matched.append(item)
            else:
                foreign.append(item)

        if matched:
            top = matched[0]
            top_text = (top.get("text") or "")
            hit_nuggets = [n for n in nuggets if n in top_text] if nuggets else None
            score = top.get("score")
            print(f"      命中 {len(matched)} 条来自本知识库的切片，最高分 {score}")
            if hit_nuggets is not None and not hit_nuggets:
                raise StepError(
                    "检索校验失败：接口返回了切片，但内容与 faq.txt 原文对不上"
                    f"（query={query!r}，返回首条内容 {top_text[:120]!r}）。"
                    "疑似库内文档内容异常，请勿当作成功。")
            if hit_nuggets:
                print(f"      内容指纹匹配 OK（命中特征: {sorted(hit_nuggets)[:5]}）")
            else:
                print("      query 无可用内容指纹，已按 knowledge_id 匹配判定")
            print(f"      检索校验通过，总耗时 {int(time.monotonic() - start)}s")
            return

        waited = int(time.monotonic() - start)
        if time.monotonic() > deadline:
            diag = (f"embedding_stat={last_doc.get('embedding_stat')}, "
                    f"word_num={last_doc.get('word_num')}, "
                    f"本次检索返回 {len(hits)} 条"
                    + (f"（其中 {len(foreign)} 条不属于本知识库）" if foreign else ""))
            raise StepError(
                f"检索校验失败：等待 {waited}s 后仍检索不到本知识库内容（query={query!r}）。"
                f"文档状态: {diag}。"
                "常见原因：文档仍在解析/建索引、向量化失败、或平台索引延迟；"
                "请勿视为上传成功。")

        print(f"      已等 {waited:>3}s，检索暂未命中（返回 {len(hits)} 条），继续重试 ...")
        time.sleep(POLL_RETRIEVE_INTERVAL)


def cleanup(session, kb_id):
    """删除本次创建的知识库并确认删干净；删不掉必须大声警告。"""
    if not kb_id:
        return True
    ok = True
    try:
        api(session, "DELETE", f"/knowledge/{kb_id}")
        print(f"[5/5] 删除知识库 {kb_id} ... OK")
    except ApiError as exc:
        print(f"[5/5] 删除知识库失败！请手动到控制台删除 id={kb_id}。原因: {exc}")
        return False

    # 确认真的删掉了（翻页查列表）
    try:
        page, still_there = 1, False
        while page <= 10:
            body = api(session, "GET", "/knowledge",
                       params={"page": page, "size": 100})
            items = (body.get("data") or {}).get("list") or []
            if any(it.get("id") == kb_id for it in items):
                still_there = True
                break
            total = (body.get("data") or {}).get("total") or 0
            if page * 100 >= total or not items:
                break
            page += 1
        if still_there:
            print(f"[5/5] 警告：删除接口返回成功，但知识库 {kb_id} 仍在列表中，请手动确认！")
            ok = False
        else:
            print("      已确认知识库从列表中消失，清理完成")
    except ApiError as exc:
        print(f"[5/5] 警告：无法查询知识库列表确认删除结果（{exc}），请手动确认 id={kb_id}")
        ok = False
    return ok


# ---------------------------------------------------------------- 入口

def read_faq(path):
    if not path.exists():
        raise StepError(f"找不到 {path}，请把 faq.txt 和 main.py 放在同一目录")
    if path.stat().st_size == 0:
        raise StepError(f"{path} 是空文件，没有可上传的内容")
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise StepError(f"{path} 既不是 UTF-8 也不是 GBK 编码，无法读取")
    if not text.strip():
        raise StepError(f"{path} 没有实际内容")
    return text


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）", file=sys.stderr)
        return 2

    faq_path = Path(__file__).resolve().parent / "faq.txt"
    faq_text = read_faq(faq_path)
    query = pick_probe_query(faq_text)
    print(f"目标文件: {faq_path}（{len(faq_text.splitlines())} 行，{len(faq_text)} 字符）")
    print(f"检索校验用的 query（取自文件原文）: {query!r}")

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key}"

    kb_id = None
    cleanup_ok = True
    outcome = "失败"
    detail = ""
    try:
        kb_id = create_knowledge_base(session)
        doc_id = upload_document(session, kb_id, faq_path)
        wait_until_retrievable(session, kb_id, doc_id, query)
        outcome = "成功"
        detail = "faq.txt 已上传，且真实检索确认命中本知识库内容"
    except StepError as exc:
        detail = str(exc)
        print(f"\n[FAIL] {detail}", file=sys.stderr)
    except KeyboardInterrupt:
        detail = "用户中断（Ctrl+C）"
        print(f"\n[FAIL] {detail}", file=sys.stderr)
    finally:
        if kb_id:
            cleanup_ok = cleanup(session, kb_id)

    print("\n" + "=" * 60)
    print(f"结论: {outcome} —— {detail}")
    if kb_id:
        print(f"知识库清理: {'完成' if cleanup_ok else '未完成（见上方警告）'} (id={kb_id})")
    print("=" * 60)
    return 0 if (outcome == "成功" and cleanup_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
