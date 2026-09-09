#!/usr/bin/env python3
"""
2026年中国新能源汽车出口市场简报生成器
"""

import os
import requests
import json
import time
from typing import List, Dict

# API 配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 生成提示词模板
PROMPTS = [
    {
        "role": "user",
        "content": "请作为新能源汽车行业分析师，为'2026年中国新能源汽车出口市场概述'撰写内容，要求不少于200字，包含以下要点：\n1. 全球市场概况\n2. 中国新能源汽车出口的总体趋势\n3. 主要出口国家和地区分布\n4. 市场份额和增长率数据\n\n请用中文回答，内容要专业、准确、有数据支撑。"
    },
    {
        "role": "user",
        "content": "继续为'2026年中国新能源汽车出口市场概述'补充内容，要求不少于200字，包含以下要点：\n1. 主要出口企业分析\n2. 竞争优势和核心竞争力\n3. 面临的主要挑战\n4. 出口产品质量和技术水平\n\n请用中文回答，内容要专业、准确。"
    },
    {
        "role": "user",
        "content": "继续为'2026年中国新能源汽车出口市场概述'补充内容，要求不少于200字，包含以下要点：\n1. 政策支持和政府举措\n2. 未来发展趋势预测\n3. 国际市场机遇和挑战\n4. 行业发展建议\n\n请用中文回答，内容要专业、前瞻。"
    }
]

def generate_section(prompt: Dict, model: str = "glm-4-flash-250414", max_tokens: int = 1000) -> str:
    """生成市场简报的一个部分"""
    payload = {
        "model": model,
        "messages": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "top_p": 0.9
    }

    try:
        response = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            return content
        else:
            return "生成失败：响应格式错误"

    except requests.exceptions.RequestException as e:
        return f"请求失败: {str(e)}"
    except json.JSONDecodeError as e:
        return f"解析失败: {str(e)}"

def generate_market_report() -> List[str]:
    """生成完整的市场简报"""
    report_sections = []

    print("正在生成 2026 年中国新能源汽车出口市场简报...")
    print("=" * 60)

    for i, prompt in enumerate(PROMPTS):
        print(f"\n正在生成第 {i+1} 部分...")
        section_content = generate_section(prompt)

        if section_content and not section_content.startswith("生成失败"):
            report_sections.append(section_content)
            print(f"✓ 第 {i+1} 部分生成完成")
            print("-" * 40)
            print(section_content[:200] + "..." if len(section_content) > 200 else section_content)
            print("-" * 40)
        else:
            print(f"✗ 第 {i+1} 部分生成失败: {section_content}")

    return report_sections

def count_chinese_chars(text: str) -> int:
    """统计中文字符数"""
    # 去除空白字符
    text = text.strip()
    # 统计中文字符、标点符号
    chinese_chars = len([char for char in text if '一' <= char <= '鿿'])
    return chinese_chars

def main():
    """主函数"""
    print("2026 年中国新能源汽车出口市场简报生成器")
    print("=" * 60)

    # 生成报告
    sections = generate_market_report()

    if not sections:
        print("\n错误：未能生成任何内容")
        return

    # 整合报告
    full_report = "\n\n".join(sections)

    # 添加标题
    title = "\n\n# 2026 年中国新能源汽车出口市场简报\n\n"
    full_report = title + full_report

    # 添加小标题
    formatted_report = f"""## 市场概况与发展趋势

{sections[0]}

## 企业竞争与核心优势

{sections[1]}

## 政策支持与未来展望

{sections[2]}
"""

    # 打印完整报告
    print("\n" + "=" * 60)
    print("完整市场简报")
    print("=" * 60)
    print(formatted_report)

    # 统计字数
    total_chars = count_chinese_chars(formatted_report)

    print("\n" + "=" * 60)
    print(f"报告完成！总字数：{total_chars} 字")

    # 检查是否满足要求
    if total_chars >= 600:
        print("✓ 报告字数达到要求（不少于 600 字）")
    else:
        print(f"✗ 报告字数不足 600 字（当前 {total_chars} 字）")

    print("=" * 60)

if __name__ == "__main__":
    main()