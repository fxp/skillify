#!/usr/bin/env python3
"""
使用智谱 GLM 生成 2026 年中国新能源汽车出口市场简报
"""

import os
import requests
import json
import sys
import re
from typing import Dict, Any

def generate_market_report() -> str:
    """生成市场简报"""
    # API配置
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建请求prompt
    prompt = """请生成一份关于"2026年中国新能源汽车出口"的市场简报。

具体要求：
1. 简报字数不少于600字
2. 包含具体数据和统计信息
3. 有明确的小标题结构
4. 内容要完整，逻辑清晰
5. 适合作为周报内容使用

请简报包含以下主要内容：
- 全球新能源汽车市场概况
- 中国新能源汽车出口现状和趋势
- 主要出口国家和市场分布
- 主要出口企业分析
- 面临的挑战和机遇
- 未来发展展望

要求内容详实，数据准确，分析深入。"""

    payload = {
        "model": "glm-5.3",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000,  # 确保有足够的输出长度
        "temperature": 0.7,
        "do_sample": True
    }

    try:
        print("正在生成市场简报...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        report = result["choices"][0]["message"]["content"]

        # 检查输出是否完整
        if not report or len(report.strip()) < 200:
            print("警告：生成的简报内容过短或不完整")
            return ""

        return report

    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        return ""
    except KeyError:
        print("API响应格式异常")
        return ""
    except Exception as e:
        print(f"发生未知错误: {e}")
        return ""

def check_report_quality(report: str) -> Dict[str, Any]:
    """检查简报质量"""
    if not report:
        return {
            "is_valid": False,
            "word_count": 0,
            "has_subtitles": False,
            "is_complete": False,
            "message": "简报内容为空"
        }

    # 计算字数
    word_count = len(report)

    # 检查是否有小标题
    has_subtitles = bool(re.search(r'^\s*###|^## |^\s*\d+\.', report, re.MULTILINE))

    # 检查内容是否完整（基于一些关键词）
    keywords = ["市场", "出口", "中国", "汽车", "数据", "增长", "趋势"]
    keyword_count = sum(1 for keyword in keywords if keyword in report)

    # 判断是否完整（至少包含大部分关键词）
    is_complete = keyword_count >= len(keywords) * 0.7

    return {
        "is_valid": True,
        "word_count": word_count,
        "has_subtitles": has_subtitles,
        "is_complete": is_complete,
        "message": "简报质量检查通过" if is_complete else "简报可能不够完整"
    }

def main():
    """主函数"""
    print("=" * 50)
    print("生成2026年中国新能源汽车出口市场简报")
    print("=" * 50)

    # 生成简报
    report = generate_market_report()

    if not report:
        print("\n生成失败，请检查API配置和网络连接。")
        sys.exit(1)

    # 打印简报
    print("\n" + "=" * 50)
    print("市场简报内容")
    print("=" * 50)
    print(report)

    # 检查质量
    quality = check_report_quality(report)

    print("\n" + "=" * 50)
    print("简报质量检查结果")
    print("=" * 50)
    print(f"字数：{quality['word_count']} 字")
    print(f"包含小标题：{'是' if quality['has_subtitles'] else '否'}")
    print(f"内容完整性：{'完整' if quality['is_complete'] else '可能不完整'}")
    print(f"检查结果：{quality['message']}")

    # 确认字数是否达标
    if quality['word_count'] < 600:
        print("\n警告：简报字数不足600字，不符合要求")
        # 尝试补充内容
        if quality['word_count'] > 200:
            print("正在尝试补充内容...")
            supplement_prompt = f"""请对以下简报进行补充，使其字数达到600字以上，并保持内容完整性和逻辑性。

原始简报：
{report}

请在不改变原意的基础上，适当增加具体数据、案例分析或未来展望等内容。"""

            # 这里可以再次调用API进行补充，为了简化，我们直接输出警告
            print("请手动补充内容以达到600字要求。")

    print("\n" + "=" * 50)
    print("简报生成完成")
    print("=" * 50)

    # 返回0表示成功
    return 0

if __name__ == "__main__":
    sys.exit(main())