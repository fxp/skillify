"""用智谱开放平台 rerank 接口，对候选文档按与问题的相关性从高到低排序并打印原文和分数。

运行前设置环境变量：
    export ZHIPUAI_API_KEY="你的APIKey"
然后直接运行：
    python3 main.py
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/rerank"

QUERY = "增值税专用发票要多久内申请"

DOCUMENTS = [
    "签收后 15 日内可无理由退货，商品需保持完好",
    "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
    "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
    "普通发票支持随时申请，无时间限制",
    "满 199 元包邮，偏远地区除外",
]


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY，请先执行 export ZHIPUAI_API_KEY=你的Key")

    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "rerank",
                "query": QUERY,
                "documents": DOCUMENTS,
                # 不传 top_n（默认 0 = 返回全部候选的分数）；
                # rerank 的 results 默认只有 index 和分数、不带原文，
                # 传 return_documents=True 让响应附带原文，便于核对
                "return_documents": True,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        sys.exit(f"网络请求失败: {exc}")

    if not resp.ok:
        # 标准端点出错时 body 里通常带 error.code / error.message，打出来便于排查
        try:
            err = resp.json().get("error", {})
            sys.exit(f"请求失败 HTTP {resp.status_code}: {err.get('code')} {err.get('message')}")
        except ValueError:
            sys.exit(f"请求失败 HTTP {resp.status_code}: {resp.text[:200]}")

    results = resp.json().get("results") or []
    if not results:
        sys.exit("接口未返回任何结果")

    # 接口本身按相关性降序返回，这里再排一次确保从高到低
    results.sort(key=lambda r: r.get("relevance_score", 0), reverse=True)

    for item in results:
        # 用 index 回溯本地候选数组，保证打印的一定是输入原文
        text = DOCUMENTS[item["index"]]
        print(f"{text}  分数: {item.get('relevance_score')}")


if __name__ == "__main__":
    main()
