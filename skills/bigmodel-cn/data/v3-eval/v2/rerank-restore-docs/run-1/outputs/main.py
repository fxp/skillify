"""用智谱开放平台的重排序（rerank）接口，对候选文档按问题相关性排序。

用法:
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
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY 再运行本脚本")

    resp = requests.post(
        RERANK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "rerank",
            "query": QUERY,
            "documents": DOCUMENTS,
            "top_n": 0,  # 0 表示返回全部候选结果
            "return_documents": True,  # 让响应直接带回原文
        },
        timeout=60,
    )
    if resp.status_code != 200:
        sys.exit(f"接口调用失败 HTTP {resp.status_code}: {resp.text}")

    results = resp.json().get("results")
    if not results:
        sys.exit("接口没有返回任何排序结果")

    # 接口不保证返回顺序，客户端按分数从高到低重排
    ranked = sorted(results, key=lambda r: r["relevance_score"], reverse=True)

    # 只打印原文和分数，不带序号，方便直接贴进工单
    for item in ranked:
        # 优先用响应回传的原文；若缺失则按下标回溯本地列表，确保一定是原文
        doc = item.get("document") or DOCUMENTS[item["index"]]
        print(f"{doc} —— 相关性分数: {item['relevance_score']:.6f}")


if __name__ == "__main__":
    main()
