#!/usr/bin/env python3

import os
import requests

api_key = os.getenv('ZHIPUAI_API_KEY')
base_url = 'https://open.bigmodel.cn/api/paas/v4/rerank'

def rerank_documents(texts):
    headers = {'Authorization': f'Bearer {api_key}'}
    data = {'model': 'glm-5.3', 'texts': texts}
    response = requests.post(base_url, headers=headers, json=data)
    return response.json()['results']

if __name__ == '__main__':
    texts = [
        "签收后 15 日内可无理由退货，商品需保持完好",
        "增值税专用发票需在订单完成后 7 个工作日内申请，逾期需联系客服",
        "公司地址位于北京市海淀区，工作日 9:00-18:00 办公",
        "普通发票支持随时申请，无时间限制",
        "满 199 元包邮，偏远地区除外"
    ]
    reranked_results = rerank_documents(texts)
    for i, result in enumerate(reranked_results):
        print(f"{result['text']}
Score: {result['score']}")