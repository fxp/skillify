import os
import requests
import json
import time

def get_api_key():
    """从环境变量获取 API Key"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        exit(1)
    return api_key

def generate_content(prompt, max_tokens=1000, api_key=None):
    """调用智谱AI生成内容"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-5.3",
        "messages": [
            {"role": "system", "content": "你是一位专业的市场分析师，擅长撰写行业分析报告。请准确、专业、详细地回答问题。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": False
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        print(f"API 请求失败: {e}")
        return None
    except KeyError as e:
        print(f"响应解析失败: {e}")
        return None

def count_chinese(text):
    """统计中文字数"""
    # 去除空格和标点符号
    chinese_chars = [char for char in text if '一' <= char <= '鿿']
    return len(chinese_chars)

def main():
    # 获取API密钥
    api_key = get_api_key()

    # 定义要生成的各个部分
    sections = [
        {
            "title": "一、市场概述",
            "prompt": "请详细分析2026年中国新能源汽车市场的整体概况，包括市场规模、增长趋势、主要特点等。要求数据翔实，分析深入，字数约200字。"
        },
        {
            "title": "二、出口数据分析",
            "prompt": "请分析2026年中国新能源汽车出口的关键数据，包括出口总量、出口额、同比增长率、主要出口车型等。要求包含具体数据，字数约200字。"
        },
        {
            "title": "三、主要出口市场分析",
            "prompt": "请分析2026年中国新能源汽车的主要出口目标市场，包括欧洲、东南亚、中东等地区的市场特点和增长情况。要求分析具体，字数约200字。"
        },
        {
            "title": "四、未来发展趋势",
            "prompt": "请展望2026年后中国新能源汽车出口的未来发展趋势，包括技术路线、市场格局、政策影响等方面。要求分析前瞻，字数约100字。"
        }
    ]

    # 生成各个部分的内容
    full_report = ""
    total_chinese_chars = 0

    print("正在生成市场简报...")
    print("-" * 50)

    for section in sections:
        print(f"正在生成：{section['title']}")
        content = generate_content(section["prompt"], max_tokens=1000, api_key=api_key)

        if content:
            # 添加标题和内容
            section_text = f"\n{section['title']}\n{content}\n"
            full_report += section_text

            # 统计当前部分的中文字数
            current_chars = count_chinese(content)
            total_chinese_chars += current_chars
            print(f"{section['title']} 完成，中文字数：{current_chars}")
        else:
            print(f"{section['title']} 生成失败，跳过")

        # 添加延迟，避免请求过快
        time.sleep(1)

    # 输出完整报告
    print("\n" + "=" * 50)
    print("2026年中国新能源汽车出口市场简报")
    print("=" * 50)
    print(full_report)

    # 统计并输出总字数
    print(f"\n报告总字数：{total_chinese_chars} 字")

    # 验证字数要求
    if total_chinese_chars >= 600:
        print("\n✅ 报告满足不少于600字的要求")
    else:
        print(f"\n❌ 报告字数不足600字（实际{total_chinese_chars}字），不满足要求")

if __name__ == "__main__":
    main()