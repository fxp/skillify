# -*- coding: utf-8 -*-
"""知识库 / RAG 端点的字段级实测（agents-assistant-knowledge.md 是验证率最低的文件）。

用法： ZHIPUAI_API_KEY=... python3 kb-probe.py
会真实创建一个知识库、上传一份文档、检索、然后清理干净。所有请求/响应记进 kb-verification-log.jsonl。
Key 只从环境变量读，日志里做脱敏。
"""
import io, json, os, sys, time, pathlib, requests

KEY = os.environ.get("ZHIPUAI_API_KEY", "")
if not KEY:
    sys.exit("export ZHIPUAI_API_KEY first")
H = {"Authorization": f"Bearer {KEY}"}
APP = "https://open.bigmodel.cn/api/llm-application/open"
LOG = pathlib.Path(__file__).resolve().parent / "kb-verification-log.jsonl"
LOG.write_text("", encoding="utf-8")


def red(t):
    return (t or "").replace(KEY, "<KEY>")


def call(label, method, url, **kw):
    try:
        r = requests.request(method, url, headers=H, timeout=180, **kw)
        try:
            body = r.json()
        except Exception:
            body = {"_raw": r.text[:400]}
    except Exception as e:
        body, r = {"_exc": str(e)[:200]}, None
    rec = {"label": label, "method": method, "url": url.replace(APP, "{APP}"),
           "status": getattr(r, "status_code", None), "response": body}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(red(json.dumps(rec, ensure_ascii=False)) + "\n")
    return getattr(r, "status_code", None), body


def show(label, st, body, keys=True):
    if st == 200 and isinstance(body, dict):
        inner = body.get("data") if isinstance(body.get("data"), dict) else None
        k = list(inner.keys())[:8] if inner else list(body.keys())[:8]
        note = f"data.keys={k}" if inner else f"keys={k}"
        print(f"  [{label:34s}] {st}  {note if keys else ''} {str(body)[:90]}")
    else:
        print(f"  [{label:34s}] {st}  {str(body)[:150]}")


print("=== 1. 创建知识库（技能称 embedding_id=11 是 Embedding-3） ===")
st, b = call("create_kb", "POST", f"{APP}/knowledge",
             json={"embedding_id": 11, "name": "skillify 验证用知识库",
                   "description": "字段级实测，用完即删", "background": "blue", "icon": "book"})
show("POST /knowledge", st, b)
kb_id = None
if isinstance(b, dict):
    d = b.get("data")
    kb_id = (d.get("id") if isinstance(d, dict) else None) or b.get("id")
print("  -> knowledge_id =", kb_id)
if not kb_id:
    sys.exit("创建失败，终止")

try:
    print("\n=== 2. 知识库列表 / 详情 / 用量 ===")
    show("GET /knowledge", *call("list_kb", "GET", f"{APP}/knowledge", params={"page": 1, "size": 10}))
    show("GET /knowledge/{id}", *call("kb_detail", "GET", f"{APP}/knowledge/{kb_id}"))
    show("GET /knowledge/capacity", *call("kb_capacity", "GET", f"{APP}/knowledge/capacity"))

    print("\n=== 3. 上传文档（multipart） ===")
    doc = ("发票开具政策\n\n公司开具增值税专用发票需在订单完成后 7 个工作日内申请，"
           "逾期需联系客服人工处理。普通发票支持随时申请。\n\n"
           "退换货政策\n\n签收后 15 日内可无理由退货，商品需保持完好。").encode("utf-8")
    st, b = call("upload_doc", "POST", f"{APP}/document/upload_document/{kb_id}",
                 files={"files": ("policy.txt", io.BytesIO(doc), "text/plain")},
                 data={"knowledge_id": kb_id})
    show("POST /document/upload_document/{id}", st, b)
    doc_id = None
    if isinstance(b, dict):
        d = b.get("data")
        if isinstance(d, dict):
            ok = d.get("successInfos") or d.get("success_infos") or []
            if ok and isinstance(ok, list) and isinstance(ok[0], dict):
                doc_id = ok[0].get("documentId") or ok[0].get("document_id") or ok[0].get("id")
    print("  -> document_id =", doc_id)

    print("\n=== 4. 文档列表 / 详情 ===")
    show("GET /document", *call("list_doc", "GET", f"{APP}/document",
                                params={"knowledge_id": kb_id, "page": 1, "size": 10}))
    if doc_id:
        show("GET /document/{id}", *call("doc_detail", "GET", f"{APP}/document/{doc_id}"))

    print("\n=== 5. 等待向量化后检索 ===")
    for i in range(10):
        time.sleep(6)
        st, b = call(f"retrieve_try{i}", "POST", f"{APP}/knowledge/retrieve",
                     json={"knowledge_ids": [str(kb_id)], "query": "发票多久内要申请", "top_k": 3})
        rows = []
        if st == 200 and isinstance(b, dict):
            d = b.get("data")
            if isinstance(d, dict):
                rows = d.get("rows") or d.get("list") or []
            elif isinstance(d, list):
                rows = d
        if rows:
            print(f"  [POST /knowledge/retrieve       ] {st}  第 {i+1} 次轮询命中 {len(rows)} 条")
            print("     单条字段:", list(rows[0].keys())[:8])
            print("     内容片段:", str(rows[0].get("content"))[:80])
            break
        else:
            print(f"  [POST /knowledge/retrieve       ] {st}  第 {i+1} 次：{str(b)[:100]}")

    print("\n=== 6. 全模态检索端点 /zrag/retrieval/retrieve ===")
    show("POST /zrag/retrieval/retrieve",
         *call("zrag", "POST", "https://open.bigmodel.cn/api/zrag/retrieval/retrieve",
               json={"knowledge_ids": [str(kb_id)], "query": "发票", "top_k": 3}))

    print("\n=== 7. chat/completions 挂 retrieval 工具 ===")
    show("chat + retrieval tool",
         *call("chat_retrieval", "POST", "https://open.bigmodel.cn/api/paas/v4/chat/completions",
               json={"model": "glm-4.6", "max_tokens": 120,
                     "messages": [{"role": "user", "content": "发票要在几个工作日内申请？"}],
                     "tools": [{"type": "retrieval", "retrieval": {"knowledge_id": str(kb_id)}}]}))
finally:
    print("\n=== 8. 清理 ===")
    if 'doc_id' in dir() and doc_id:
        show("DELETE /document/{id}", *call("del_doc", "DELETE", f"{APP}/document/{doc_id}"))
    show("DELETE /knowledge/{id}", *call("del_kb", "DELETE", f"{APP}/knowledge/{kb_id}"))
    print(f"\n完整请求/响应记录: {LOG}")
