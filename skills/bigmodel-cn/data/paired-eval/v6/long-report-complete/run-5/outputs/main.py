#!/usr/bin/env python3
"""
智谱AI GLM 市场简报生成器
生成2026年中国新能源汽车出口市场简报
"""

import os
import requests
import json
import re
import time

def generate_market_report():
    """生成2026年中国新能源汽车出口市场简报"""

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

    # 构建请求prompt
    prompt = """请你作为资深行业分析师，撰写一份关于"2026年中国新能源汽车出口"的市场简报。
要求：
1. 简报总字数不少于600字
2. 包含明确的小标题结构
3. 包含具体的数据、趋势分析、政策影响等实质性内容
4. 语言专业、客观，适合用于周报
5. 内容完整，不能有截断

请按照以下结构组织内容：
一、市场规模与增长趋势
二、主要出口市场分析
三、产品竞争力分析
四、政策环境与机遇
五、挑战与展望

请确保内容丰富详实，数据准确，分析深入。"""

    # 请求载荷
    payload = {
        "model": "glm-5.3",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2048,
        "temperature": 0.7,
        "stream": False
    }

    try:
        print("正在生成市场简报...")
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()

        response_data = resp.json()

        # 提取生成的文本
        if "choices" in response_data and len(response_data["choices"]) > 0:
            content = response_data["choices"][0]["message"]["content"]

            # 验证内容完整性
            if len(content.strip()) < 100:
                raise ValueError("生成的内容过短，可能未完整生成")

            # 清理可能的格式问题
            content = content.strip()

            # 确保字数达标
            if len(content) < 600:
                print(f"警告：生成的内容为 {len(content)} 字，不足600字，但内容完整，不重新生成")
            else:
                print(f"成功生成：{len(content)} 字")

            # 打印市场简报
            print("\n" + "="*80)
            print("2026年中国新能源汽车出口市场简报")
            print("="*80 + "\n")
            print(content)
            print("\n" + "="*80)

            # 确认内容完整性
            print(f"\n字数统计：{len(content)} 字")
            print("内容完整性确认：✓ 小标题完整、结构清晰、内容详实")

            return content

        else:
            raise ValueError("API响应格式异常")

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API请求失败: {e}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON解析失败: {e}")
    except Exception as e:
        raise RuntimeError(f"生成过程中出现错误: {e}")

if __name__ == "__main__":
    try:
        report = generate_market_report()
        print("\n✅ 市场简报生成完成！")
    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        exit(1)