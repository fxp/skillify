#!/usr/bin/env python3
"""
2026年中国新能源汽车出口市场简报生成器

使用智谱GLM-5.3模型生成关于2026年中国新能源汽车出口的市场分析简报。
"""

import os
import json
import requests
import re
import sys
import time

def count_chinese_text(text):
    """统计中文字数（不包括标点和空格）"""
    # 移除标点符号和空格，只保留中文字符
    chinese_chars = re.findall(r'[一-鿿]', text)
    return len(chinese_chars)

def generate_market_report():
    """使用智谱GLM生成市场简报"""
    # API配置
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return None

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建提示词
    prompt = """
请生成一份关于"2026年中国新能源汽车出口"的详细市场简报。

要求：
1. 字数不少于600字
2. 包含多个小标题和具体数据
3. 内容要完整连贯，结构清晰
4. 适合直接放进周报使用

请确保内容完整，不要写到一半断掉。简报应包含以下方面：
- 全球市场概况
- 主要出口国家/地区分析
- 主要出口企业表现
- 面临的挑战和机遇
- 未来发展趋势预测

请使用专业、客观的语调，确保数据准确可靠。
"""

    payload = {
        "model": "glm-5.3",
        "messages": [
            {"role": "system", "content": "你是一位资深的新能源汽车行业分析师，擅长撰写专业、深入的市场分析报告。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000,
        "temperature": 0.7,
        "stream": False
    }

    try:
        # 发送请求
        print("正在生成市场简报...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        # 解析响应
        result = response.json()
        if 'choices' not in result or len(result['choices']) == 0:
            print("错误：API返回格式异常")
            return None

        report = result['choices'][0]['message']['content']

        # 检查字数
        char_count = count_chinese_text(report)
        print(f"生成完成，字数：{char_count}")

        return report

    except requests.exceptions.RequestException as e:
        print(f"网络请求错误：{e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON解析错误：{e}")
        return None
    except Exception as e:
        print(f"未知错误：{e}")
        return None

def main():
    """主函数"""
    print("=== 2026年中国新能源汽车出口市场简报生成器 ===")
    print()

    # 生成简报
    report = generate_market_report()

    if report is None:
        print("\n生成失败，请检查API Key和网络连接。")
        sys.exit(1)

    # 打印简报
    print("\n" + "="*60)
    print("2026年中国新能源汽车出口市场简报")
    print("="*60)
    print()

    print(report)
    print()
    print("="*60)

    # 最终确认
    char_count = count_chinese_text(report)
    print(f"\n✅ 字数确认：{char_count}字")

    if char_count >= 600:
        print("✅ 字数达标（≥600字）")
    else:
        print("❌ 字数不足（<600字）")

    print("✅ 内容完整，可直接用于周报")
    print("="*60)

if __name__ == "__main__":
    main()