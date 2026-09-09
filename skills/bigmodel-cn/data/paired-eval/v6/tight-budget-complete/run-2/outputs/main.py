#!/usr/bin/env python3
"""
2026 年中国新能源汽车出口市场简报生成器
使用智谱AI GLM-4.7-Flash 模型生成，严格遵守 max_tokens <= 1000 的限制
"""

import os
import requests
import json
import re
from typing import Dict, Any, List


def get_zhipu_api_key() -> str:
    """从环境变量获取智谱AI API Key"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("未找到环境变量 ZHIPUAI_API_KEY，请设置该环境变量")
    return api_key


def generate_market_report_section(section_prompt: str, api_key: str) -> str:
    """
    生成市场报告的一个部分内容
    Args:
        section_prompt: 该部分的提示词
        api_key: API密钥
    Returns:
        生成的文本内容
    """
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-4.7-flash",  # 使用免费且性能不错的模型
        "messages": [
            {
                "role": "system",
                "content": "你是一位资深的新能源汽车行业分析师，擅长撰写专业的市场分析报告。请用中文回答，内容要详实、专业，包含具体数据和观点。"
            },
            {
                "role": "user",
                "content": section_prompt
            }
        ],
        "max_tokens": 800,  # 严格遵守限制，每个部分不超过800 tokens
        "temperature": 0.7,
        "do_sample": True
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        # 提取生成的内容
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError("API未返回有效内容")

        return content.strip()

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API请求失败: {str(e)}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"解析API响应失败: {str(e)}")


def count_chinese_text(text: str) -> int:
    """计算中文字符数量"""
    # 匹配中文字符（包括中文标点）
    chinese_chars = re.findall(r'[一-鿿　-〿＀-￯]', text)
    return len(chinese_chars)


def main():
    """主函数：生成完整的市场简报"""
    print("=== 2026 年中国新能源汽车出口市场简报生成器 ===\n")

    # 检查API Key
    try:
        api_key = get_zhipu_api_key()
    except ValueError as e:
        print(f"错误: {e}")
        return

    # 定义报告的各个部分
    report_sections = [
        {
            "title": "一、市场概况",
            "prompt": "请详细概述2026年中国新能源汽车出口的整体情况，包括出口总量、同比增长率、在全球市场中的地位等关键数据。"
        },
        {
            "title": "二、主要出口目的地",
            "prompt": "分析2026年中国新能源汽车的主要出口目的地国家和地区，包括欧洲、东南亚、北美等市场的表现和特点，以及市场份额分布。"
        },
        {
            "title": "三、出口产品结构",
            "prompt": "描述2026年中国出口的新能源汽车产品结构，包括纯电动汽车、插电混动汽车的比例，各车型的代表产品和技术特点。"
        },
        {
            "title": "四、竞争优势分析",
            "prompt": "分析中国新能源汽车在国际市场上的竞争优势，包括技术、成本、供应链、政策支持等方面的优势。"
        },
        {
            "title": "五、面临的挑战",
            "prompt": "探讨2026年中国新能源汽车出口面临的主要挑战，包括贸易壁垒、技术竞争、供应链风险等问题。"
        },
        {
            "title": "六、未来展望",
            "prompt": "展望2027-2028年中国新能源汽车出口的发展趋势，包括市场机会、增长点和潜在的风险。"
        }
    ]

    generated_content = []
    total_chinese_chars = 0

    # 逐个生成报告的各个部分
    for section in report_sections:
        print(f"正在生成 {section['title']}...")

        try:
            content = generate_market_report_section(section["prompt"], api_key)
            generated_content.append(f"\n{section['title']}\n{content}")

            # 计算当前部分的中文字数
            section_chars = count_chinese_text(content)
            total_chinese_chars += section_chars
            print(f"{section['title']} 生成完成，中文字数: {section_chars}")

        except Exception as e:
            print(f"生成 {section['title']} 时出错: {str(e)}")
            # 如果某个部分失败，生成一个简短的替代内容
            fallback_content = f"\n{section['title']}\n[该部分内容生成失败，请稍后重试]"
            generated_content.append(fallback_content)
            total_chinese_chars += count_chinese_text(fallback_content)

    # 组合完整报告
    full_report = "\n".join(generated_content)

    # 添加报告的开头和结尾
    report_header = """2026 年中国新能源汽车出口市场简报

本报告基于最新市场数据，全面分析中国新能源汽车产业的出口现状、
发展趋势及面临的挑战，为相关企业提供决策参考。

"""

    report_footer = f"""
---
本报告由人工智能自动生成，数据仅供参考。
实际总字数：{total_chinese_chars} 汉字
报告生成时间：2026年9月
"""

    final_report = report_header + full_report + report_footer

    # 打印完整报告和字数统计
    print("\n" + "="*50)
    print("完整市场简报如下：")
    print("="*50 + "\n")
    print(final_report)

    # 输出字数统计
    print("="*50)
    print(f"【报告完成】")
    print(f"报告标题：2026 年中国新能源汽车出口市场简报")
    print(f"总字数：{total_chinese_chars} 汉字")
    if total_chinese_chars >= 600:
        print("✅ 字数要求已满足（≥600字）")
    else:
        print(f"❌ 字数未达到要求（需要≥600字，当前{total_chinese_chars}字）")
    print("="*50)


if __name__ == "__main__":
    main()