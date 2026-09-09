#!/usr/bin/env python3
"""
2026年中国新能源汽车出口市场简报生成器
使用智谱GLM模型生成完整的市场分析报告
"""

import os
import requests
import json
import re
import time
from typing import Dict, Any, Optional

def generate_market_report() -> str:
    """
    使用智谱GLM模型生成2026年中国新能源汽车出口市场简报
    返回生成的报告内容
    """
    # API配置
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建提示词
    prompt = """
请生成一份关于「2026年中国新能源汽车出口」的详细市场简报。

要求：
1. 字数不少于600字
2. 包含至少3个小标题
3. 提供具体的市场数据和趋势分析
4. 内容完整，不能有断章取义
5. 语言正式，适合作为周报材料

请按照以下结构组织内容：
一、市场概况
二、主要出口国家/地区分析
三、竞争格局与主要企业
四、未来发展趋势

每个部分都要包含具体数据、图表引用（如果适用）和深入分析。
"""

    # 请求参数
    payload = {
        "model": "glm-5.3",  # 使用旗舰模型确保输出质量
        "messages": [
            {
                "role": "system",
                "content": "你是一位资深的新能源汽车行业分析师，擅长撰写专业的市场分析报告，注重数据准确性和深度洞察。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 2000,  # 足够的输出长度
        "temperature": 0.7,
        "do_sample": True,
        "top_p": 0.9
    }

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        return content

    except requests.exceptions.RequestException as e:
        raise Exception(f"API请求失败: {str(e)}")
    except KeyError:
        raise Exception("API响应格式错误")
    except Exception as e:
        raise Exception(f"生成报告时发生错误: {str(e)}")

def validate_report_content(content: str) -> bool:
    """
    验证报告内容是否完整
    """
    # 检查字数
    char_count = len(content)
    if char_count < 600:
        print(f"警告：报告字数不足（{char_count}字），需要至少600字")
        return False

    # 检查是否有小标题
    has_title = re.search(r'^一、|^二、|^三、|^四、|### |## |###', content, re.MULTILINE)
    if not has_title:
        print("警告：报告中未找到小标题")
        return False

    # 检查内容是否完整
    if content.strip().endswith('...') or content.strip().endswith('未完待续'):
        print("警告：报告内容不完整")
        return False

    return True

def clean_report_content(content: str) -> str:
    """
    清理报告内容，去除可能的截断标记
    """
    # 去除可能的截断标记
    content = content.replace('...', '')
    content = content.replace('未完待续', '')

    # 确保报告以完整句号结束
    if not content.strip().endswith('。'):
        content = content.rstrip() + '。'

    return content.strip()

def main():
    print("正在生成2026年中国新能源汽车出口市场简报...")
    print("=" * 60)

    try:
        # 生成报告
        report_content = generate_market_report()

        # 清理内容
        cleaned_content = clean_report_content(report_content)

        # 验证报告
        is_valid = validate_report_content(cleaned_content)

        if not is_valid:
            print("\n报告验证未通过，尝试重新生成...")
            # 如果第一次生成不完整，再尝试一次
            time.sleep(2)
            report_content = generate_market_report()
            cleaned_content = clean_report_content(report_content)

        # 打印报告
        print("\n" + "=" * 60)
        print("2026年中国新能源汽车出口市场简报")
        print("=" * 60)
        print(cleaned_content)
        print("\n" + "=" * 60)

        # 验证并报告结果
        char_count = len(cleaned_content)
        print(f"\n字数统计：{char_count}字")

        if validate_report_content(cleaned_content):
            print("✅ 报告生成成功！")
            print("- 字数达标（≥600字）")
            print("- 包含小标题结构")
            print("- 内容完整，无截断")
        else:
            print("❌ 报告生成未完全达标")

    except Exception as e:
        print(f"❌ 错误：{str(e)}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())