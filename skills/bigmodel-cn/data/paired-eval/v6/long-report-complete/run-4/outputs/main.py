#!/usr/bin/env python3
import os
import requests
import json
import re
import time

def generate_market_report():
    """使用智谱 GLM 生成 2026 年中国新能源汽车出口市场简报"""

    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return False

    # API 配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建请求 payload
    payload = {
        "model": "glm-5.3",  # 使用旗舰模型，支持长文本输出
        "messages": [
            {
                "role": "system",
                "content": """你是一位资深的市场分析师，擅长撰写专业的行业市场简报。
请生成一份关于"2026 年中国新能源汽车出口"的详细市场简报。
要求：
1. 不少于 600 字
2. 包含多个小标题和具体数据
3. 内容完整，结构清晰
4. 分析深入，有数据支撑
5. 语言专业但不晦涩"""
            },
            {
                "role": "user",
                "content": """请生成一份关于"2026 年中国新能源汽车出口"的市场简报。
要求：
1. 不少于 600 字
2. 包含多个小标题和结构清晰
3. 提供具体的市场数据、出口量、增长率等
4. 分析主要出口市场、主要企业表现
5. 展望未来发展趋势
6. 内容要完整，不能写到一半断掉"""
            }
        ],
        "max_tokens": 2000,  # 设置足够的输出长度
        "temperature": 0.7,  # 保持一定的创造性
        "do_sample": True
    }

    print("正在生成市场简报...")

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 检查响应是否有效
        if 'choices' not in result or len(result['choices']) == 0:
            print("错误：API 返回的响应格式不正确")
            return False

        content = result['choices'][0]['message']['content']

        # 检查内容是否完整
        if not content or len(content.strip()) < 100:
            print("错误：生成的内容过短或不完整")
            return False

        # 打印生成的简报
        print("\n" + "="*60)
        print("2026 年中国新能源汽车出口市场简报")
        print("="*60)
        print("\n")

        print(content)

        # 确认字数
        word_count = len(content.strip())
        print("\n" + "-"*60)
        print(f"字数统计：{word_count} 字")

        if word_count >= 600:
            print("✅ 字数达标（不少于 600 字）")
        else:
            print("❌ 字数不足（少于 600 字）")

        # 检查是否有明显的截断
        if content.endswith('...') or '未完' in content or '待续' in content:
            print("⚠️  警告：内容可能不完整")
        else:
            print("✅ 内容完整")

        print("-"*60)
        print("\n简报生成完成！")

        return True

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
        return False
    except json.JSONDecodeError as e:
        print(f"解析响应失败：{e}")
        return False
    except Exception as e:
        print(f"发生错误：{e}")
        return False

if __name__ == "__main__":
    success = generate_market_report()
    if not success:
        exit(1)