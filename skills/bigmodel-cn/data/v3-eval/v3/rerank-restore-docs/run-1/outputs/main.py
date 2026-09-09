"""用智谱开放平台的 rerank 接口，对候选文档按与问题的相关性从高到低排序。

用法：
    export ZHIPUAI_API_KEY=你的Key
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


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）")

    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "rerank",
            "query": QUERY,
            "documents": DOCUMENTS,
            "top_n": len(DOCUMENTS),  # 显式要求返回全部 5 条，不漏打印
            "return_documents": True,
        },
        timeout=30,
    )

    # 出错时优先把平台返回的 error.code / error.message 打出来，便于排查
    if not resp.ok:
        try:
            err = resp.json().get("error", {})
            sys.exit(
                f"错误：rerank 接口请求失败，HTTP {resp.status_code}"
                f"（code={err.get('code')}, message={err.get('message')}）"
            )
        except ValueError:
            sys.exit(f"错误：rerank 接口请求失败，HTTP {resp.status_code}，响应不是 JSON")

    body = resp.json()
    if "error" in body:
        sys.exit(f"错误：rerank 接口返回错误：{body['error']}")

    results = body.get("results")
    if not results:
        sys.exit("错误：rerank 接口没有返回任何结果")

    # 不依赖服务端的返回顺序，本地按相关性分数从高到低再排一次
    ranked = sorted(results, key=lambda r: r["relevance_score"], reverse=True)

    print(f"问题：{QUERY}")
    print("候选文档（按相关性从高到低）：")
    for item in ranked:
        # results 默认只带 index 和分数；用 index 回到本地列表取原文，
        # 保证打印的是逐字的原始文档内容，可直接贴进工单
        text = DOCUMENTS[item["index"]]
        print(f"{text}    相关性分数：{item['relevance_score']:.6f}")


if __name__ == "__main__":
    main()
