#!/usr/bin/env python3
"""
使用智谱 GLM 生成 2026 年中国新能源汽车出口市场简报
"""

import os
import requests
import json
import sys

def generate_market_report():
    """生成市场简报的主函数"""

    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

    # API 配置
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
                "content": "你是一位资深的新能源汽车行业分析师，擅长撰写专业的市场分析报告。请生成一份详细、数据丰富的市场简报，包含具体的数据、小标题和深入分析。报告语言必须是中文。"
            },
            {
                "role": "user",
                "content": "请生成一份关于「2026 年中国新能源汽车出口」的市场简报，要求：\n\n1. 报告长度不少于 600 字\n2. 包含多个小标题，结构清晰\n3. 包含具体的数据和分析\n4. 涵盖出口趋势、市场份额、主要目标市场、面临的挑战和机遇等方面\n5. 数据要具体，要有数字支撑\n6. 语言专业、客观、有深度\n\n请直接输出完整的报告内容，不要包含任何前言或说明性文字。"
            }
        ],
        "max_tokens": 8192,  # 足够大的输出限制
        "temperature": 0.7,
        "top_p": 0.9,
        "stream": False
    }

    try:
        # 发送请求
        print("正在生成市场简报...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 检查响应结构
        if 'choices' not in result or len(result['choices']) == 0:
            print("错误：API 响应格式不正确")
            sys.exit(1)

        # 获取生成的文本
        report = result['choices'][0]['message']['content']

        # 检查输出是否完整
        if not report or len(report.strip()) < 600:
            print("警告：生成的简报可能不完整或不足 600 字")
            print(f"实际字数：{len(report)} 字")

        # 输出简报
        print("\n" + "="*60)
        print("2026 年中国新能源汽车出口市场简报")
        print("="*60)
        print("\n")
        print(report)
        print("\n" + "="*60)

        # 确认字数
        word_count = len(report)
        print(f"\n简报字数：{word_count} 字")

        if word_count >= 600:
            print("✅ 简报字数达标（≥600 字）")
        else:
            print("❌ 简报字数不足（<600 字）")

        # 检查是否有明显截断
        if report.endswith("...") or "未完" in report or "续" in report[-10:]:
            print("⚠️  警告：简报可能被截断，内容不完整")
        else:
            print("✅ 简报内容完整")

        return True

    except requests.exceptions.RequestException as e:
        print(f"网络请求错误：{e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误：{e}")
        sys.exit(1)
    except KeyError as e:
        print(f"响应数据结构错误，缺少字段：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"未知错误：{e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_market_report()