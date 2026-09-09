#!/usr/bin/env python3
"""
智谱GLM市场简报生成器
生成2026年中国新能源汽车出口市场简报
"""

import os
import requests
import json
import time
import re

def generate_market_report():
    """使用智谱GLM生成市场简报"""

    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建请求 payload
    payload = {
        "model": "glm-5.3",
        "messages": [
            {
                "role": "system",
                "content": "你是一位资深的汽车行业市场分析师，请生成一份专业、详实的市场简报。要求：\n1. 不少于600字\n2. 包含小标题\n3. 包含具体数据和事实\n4. 结构清晰，逻辑严谨\n5. 语言专业但不失易懂"
            },
            {
                "role": "user",
                "content": "请生成一份2026年中国新能源汽车出口市场简报，要求包含以下内容：\n\n一、出口总体情况\n- 2026年出口总量及增长率\n- 出口金额及市场规模\n- 占全球市场份额\n\n二、主要出口目的地\n- 按地区分析（欧洲、东南亚、北美等）\n- 重点市场占比\n- 市场变化趋势\n\n三、主要出口企业\n- 比亚迪、上汽、蔚来、小鹏等企业表现\n- 出口销量排名\n- 市场份额分布\n\n四、出口产品结构\n- 乘用车与商用车比例\n- 纯电动与插混车型分布\n- 各级别车型占比\n\n五、面临的挑战与机遇\n- 国际贸易壁垒\n- 技术竞争态势\n- 发展机遇分析\n\n六、未来发展趋势\n- 2027年预测\n- 技术发展方向\n- 市场展望\n\n请确保内容完整，数据详实，格式规范。"
            }
        ],
        "max_tokens": 2048,
        "temperature": 0.7,
        "top_p": 0.9,
        "stream": False
    }

    # 发送请求
    print("正在生成市场简报...")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        # 提取生成的内容
        content = result["choices"][0]["message"]["content"]
        return content

    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        return None
    except KeyError as e:
        print(f"响应格式错误: {e}")
        return None

def validate_content(content):
    """验证生成内容的完整性和字数"""
    if not content:
        return False, "内容为空"

    # 去除多余的空白字符
    content = content.strip()

    # 检查内容长度
    word_count = len(content)
    if word_count < 600:
        return False, f"字数不足：{word_count}字，要求不少于600字"

    # 检查是否包含小标题（支持中文数字和Markdown格式）
    if not (re.search(r'^[一二三四五六七八九十]+、', content, re.MULTILINE) or
            re.search(r'^## [一二三四五六七八九十]+、', content, re.MULTILINE)):
        return False, "未检测到规范的小标题格式"

    return True, f"内容完整，字数达标：{word_count}字"

def main():
    """主函数"""
    print("=" * 60)
    print("2026年中国新能源汽车出口市场简报生成器")
    print("=" * 60)

    # 生成市场简报
    report = generate_market_report()

    if not report:
        print("生成失败，请检查API Key和网络连接")
        return

    # 验证内容
    is_valid, message = validate_content(report)
    if not is_valid:
        print(f"内容验证失败: {message}")
        print("\n生成的内容：")
        print("-" * 40)
        print(report)
        print("-" * 40)
        return

    # 输出结果
    print("\n" + "=" * 60)
    print("2026年中国新能源汽车出口市场简报")
    print("=" * 60)
    print(report)
    print("=" * 60)
    print(message)
    print("✅ 简报生成成功！")

if __name__ == "__main__":
    main()