"""用智谱重排序（rerank）接口对候选文档按与问题的相关性排序。

用法：
    export ZHIPUAI_API_KEY=你的APIKey
    python3 main.py
"""

import os
import sys

import requests

RERANK_URL = "https://open.bigmodel.cn/api/paas/v4/rerank"

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
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    resp = requests.post(
        RERANK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "rerank",
            "query": QUERY,
            "documents": DOCUMENTS,
            "top_n": len(DOCUMENTS),  # 默认 0 也是返回全部，这里显式传 5
        },
        timeout=30,
    )

    if not resp.ok:
        print(f"错误：HTTP {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    body = resp.json()
    if "error" in body:
        err = body["error"]
        print(f"错误：{err.get('code')} {err.get('message')}", file=sys.stderr)
        sys.exit(1)

    results = body.get("results") or []
    if not results:
        print("错误：接口未返回任何排序结果", file=sys.stderr)
        sys.exit(1)

    # 接口本身按分数降序返回，这里再显式排一次，保证输出顺序稳定
    results.sort(key=lambda r: r["relevance_score"], reverse=True)

    # 用 index 回溯输入数组下标取原文，确保打印内容与输入逐字一致、可直接贴进工单
    for item in results:
        text = DOCUMENTS[item["index"]]
        print(f"{text} | 相关性分数：{item['relevance_score']:.4f}")


if __name__ == "__main__":
    main()
