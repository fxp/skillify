#!/usr/bin/env python3
"""
使用智谱 GLM 生成 2026 年中国新能源汽车出口市场简报
"""

import os
import requests
import json
import sys
from typing import Dict, Any, Optional

def generate_market_report() -> str:
    """使用智谱 GLM 生成市场简报"""

    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API 端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建提示词，要求生成详细的市场简报
    prompt = """请作为资深行业分析师，为撰写一份关于"2026 年中国新能源汽车出口"的详细市场简报。
要求：
1. 简报不少于 600 字
2. 必须包含多个小标题，结构清晰
3. 包含具体数据和事实支持
4. 内容完整，可以直接用于周报
5. 涵盖市场现状、发展趋势、挑战机遇等方面

请直接输出完整的市场简报，不要额外的解释文字。"""

    # 构建请求数据
    payload = {
        "model": "glm-5.3",
        "messages": [
            {"role": "system", "content": "你是专业的行业分析师，擅长撰写深入的市场分析报告。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000,  # 确保足够生成长篇报告
        "temperature": 0.7,
        "top_p": 0.9
    }

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        response_data = response.json()

        # 提取生成的文本
        if 'choices' in response_data and len(response_data['choices']) > 0:
            content = response_data['choices'][0]['message']['content']
            return content.strip()
        else:
            raise ValueError("API 响应格式异常，无法获取内容")

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API 请求失败: {e}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"解析 API 响应失败: {e}")

def validate_report(report: str) -> Dict[str, Any]:
    """验证报告的质量和完整性"""

    # 检查字数
    char_count = len(report)
    word_count = len(report.split())

    # 检查是否包含小标题
    has_subheadings = any(line.startswith('#') or '：' in line for line in report.split('\n') if line.strip())

    # 检查是否包含具体数据（数字）
    has_data = any(char.isdigit() for char in report)

    # 检查内容是否完整（没有明显截断）
    is_complete = not (
        report.endswith('...') or
        report.endswith('……') or
        report.endswith('。') and len(report) < 300 or  # 可能被截断
        ('更多' in report or '详细' in report) and len(report) < 500
    )

    return {
        'char_count': char_count,
        'word_count': word_count,
        'has_subheadings': has_subheadings,
        'has_data': has_data,
        'is_complete': is_complete,
        'meets_requirement': char_count >= 600
    }

def main():
    """主函数"""

    print("正在生成 2026 年中国新能源汽车出口市场简报...")

    try:
        # 生成报告
        report = generate_market_report()

        # 验证报告
        validation = validate_report(report)

        # 打印报告
        print("\n" + "="*60)
        print("2026 年中国新能源汽车出口市场简报")
        print("="*60 + "\n")

        print(report)

        print("\n" + "-"*60)
        print("报告质量验证结果：")
        print(f"- 字数：{validation['char_count']} 字")
        print(f"- 词数：{validation['word_count']} 词")
        print(f"- 包含小标题：{'是' if validation['has_subheadings'] else '否'}")
        print(f"- 包含具体数据：{'是' if validation['has_data'] else '否'}")
        print(f"- 内容完整性：{'完整' if validation['is_complete'] else '可能不完整'}")
        print(f"- 字数达标：{'是' if validation['meets_requirement'] else '否（需要至少 600 字）'}")

        # 确认字数和完整性
        if validation['meets_requirement'] and validation['is_complete']:
            print("\n✅ 报告生成成功！内容完整且字数达标。")
        elif not validation['meets_requirement']:
            print("\n⚠️ 警告：报告字数不足 600 字，可能需要重新生成。")
        else:
            print("\n⚠️ 警告：报告内容可能不完整，请检查。")

        # 如果内容不完整，尝试重新生成
        if not validation['is_complete'] or not validation['meets_requirement']:
            print("\n正在尝试重新生成完整的报告...")
            report = generate_market_report()
            validation = validate_report(report)

            print("\n重新生成后的报告：")
            print("="*60 + "\n")
            print(report)

            print(f"\n重新验证：字数 {validation['char_count']} 字，达标 {'是' if validation['meets_requirement'] else '否'}")

    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()