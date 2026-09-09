#!/usr/bin/env python3
"""
测试脚本逻辑，不依赖真实API调用
"""

import re

def test_fallback_search():
    """测试替代方案的逻辑"""
    print("=== 测试替代方案逻辑 ===\n")

    # 模拟faq内容
    faq_content = """退换货政策

1. 退换货政策的有效期
   - 购买商品后7天内，可申请无理由退货
   - 商品需保持原包装完好，未经使用
   - 退换货政策自签收之日起计算有效期
   - 特殊商品（如生鲜、定制商品）除外

2. 退货流程
   - 联系客服申请退货，提供订单号
   - 客审核通过后，寄回商品
   - 收到商品检查无误后，3个工作日内退款
   - 退款原路返回，运费由买家承担

3. 换货条件
   - 商品存在质量问题可申请换货
   - 收货7天内发现质量问题
   - 需提供问题照片或视频证明
   - 换货运费由卖家承担

4. 退换货须知
   - 退换货需保留完整包装
   - 个人卫生用品不退不换
   - 活动商品需遵循活动规则
   - 最终解释权归本店所有"""

    # 分割成段落
    paragraphs = [p.strip() for p in faq_content.split("\n\n") if p.strip()]

    # 查询
    query = "退换货政策的有效期是多久"
    query_lower = query.lower()

    # 简单的关键词匹配
    matched_paragraphs = []

    for i, para in enumerate(paragraphs):
        # 检查是否包含关键词
        keywords = ["有效期", "退换货", "退货", "换货", "7天", "时间"]
        score = 0
        for keyword in keywords:
            if keyword in para:
                score += 1

        # 标题匹配加分
        if i < len(paragraphs) and "退换货政策" in paragraphs[i]:
            score += 2

        # 直接查询文本匹配加分
        if "有效期" in para and "7天" in para:
            score += 3

        if score > 0:
            matched_paragraphs.append((i, para, score))

    # 按分数排序
    matched_paragraphs.sort(key=lambda x: x[2], reverse=True)

    print("查询：", query)
    print("\n=== 匹配的原文片段 ===")
    if matched_paragraphs:
        for i, (idx, para, score) in enumerate(matched_paragraphs[:5], 1):
            print(f"{i}. [匹配度: {score}] {para}")
            print("-" * 50)
    else:
        print("未找到匹配内容")

    return len(matched_paragraphs) > 0

def test_api_simulation():
    """模拟API调用流程"""
    print("\n=== 模拟API调用流程 ===\n")

    # 模拟知识库创建响应
    print("1. 创建知识库...")
    print("   响应: {'code': 200, 'data': {'id': 'know-123'}}")

    # 模拟文档上传响应
    print("\n2. 上传文档...")
    print("   响应: {'code': 200, 'data': {'successInfos': [{'documentId': 'doc-456'}]}}")

    # 模拟向量化状态检查
    print("\n3. 检查向量化状态...")
    print("   状态: 1 (成功)")

    # 模拟检索响应
    print("\n4. 检索内容...")
    print("   响应: {'code': 200, 'data': [{'text': '购买商品后7天内，可申请无理由退货', 'score': 0.83}]}")

    # 模拟知识库清理
    print("\n5. 清理知识库...")
    print("   完成")

if __name__ == "__main__":
    # 测试替代方案
    success = test_fallback_search()
    print(f"\n替代方案测试: {'成功' if success else '失败'}")

    # 展示流程
    test_api_simulation()

    print("\n" + "="*60)
    print("使用说明：")
    print("1. 设置环境变量: export ZHIPUAI_API_KEY='your-api-key'")
    print("2. 运行主脚本: python3 main.py")
    print("3. 如果托管知识库不可用，会自动使用替代方案")