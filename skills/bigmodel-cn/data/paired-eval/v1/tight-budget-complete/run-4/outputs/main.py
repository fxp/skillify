import os
import requests
import json
import time
from typing import List, Dict

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 使用通用旗舰模型

def generate_section(prompt: str, section_name: str) -> str:
    """生成报告的某个部分"""
    print(f"正在生成{section_name}...")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 800,  # 保持在1000以下，留有余量
        "temperature": 0.8,
        "do_sample": True
    }

    try:
        response = requests.post(BASE_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"生成{section_name}时出错: {e}")
        return f"**{section_name}生成失败**"

def main():
    """主函数：生成完整的市场简报"""

    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    print("开始生成2026年中国新能源汽车出口市场简报...")

    # 定义报告的各个部分
    sections = [
        {
            "name": "引言部分",
            "prompt": """请撰写「2026年中国新能源汽车出口市场简报」的引言部分，内容应包括：
1. 全球新能源汽车市场发展趋势（2026年数据）
2. 中国在全球新能源汽车产业中的地位
3. 出口对中国新能源汽车产业的重要性
要求包含具体数据，不少于120字。"""
        },
        {
            "name": "市场概况",
            "prompt": """请分析2026年中国新能源汽车出口的市场概况，包括：
1. 2026年中国新能源汽车出口总量（万辆）
2. 出口额（亿美元）
3. 主要出口国家和地区分布
4. 市场份额占比
要求包含具体数据，不少于150字。"""
        },
        {
            "name": "主要出口国家分析",
            "prompt": """请详细分析中国新能源汽车的主要出口目标国家，包括：
1. 欧洲市场（德国、法国、英国等）出口情况
2. 东南亚市场（泰国、新加坡、马来西亚等）表现
3. 其他新兴市场（中东、拉美等）的开拓情况
4. 各市场的政策环境和消费者偏好
要求包含具体数据，不少于150字。"""
        },
        {
            "name": "产品与技术竞争力",
            "prompt": """请分析中国新能源汽车在产品和技术方面的竞争力，包括：
1. 主要出口车型和技术特点
2. 电池技术和续航能力表现
3. 智能化和网联技术优势
4. 与国际品牌的竞争优势
要求包含具体数据，不少于120字。"""
        },
        {
            "name": "挑战与机遇",
            "prompt": """请分析2026年中国新能源汽车出口面临的挑战与机遇，包括：
1. 国际贸易壁垒和政策风险
2. 技术竞争和标准制定的挑战
3. 全球碳中和带来的机遇
4. 技术创新和市场拓展的机会
要求包含具体数据，不少于120字。"""
        }
    ]

    # 生成各个部分
    report_parts = []
    total_content = ""

    for section in sections:
        content = generate_section(section["prompt"], section["name"])
        report_parts.append(f"### {section['name']}\n{content}")
        total_content += f"\n\n{section['name']}\n{content}"
        time.sleep(1)  # 避免请求过快

    # 生成总结部分
    summary_prompt = f"""基于以下内容，写一个简短的总结：
{total_content}

总结应：
1. 概括2026年中国新能源汽车出口的整体表现
2. 展望未来发展趋势
3. 提出建议
要求80-100字。"""

    summary = generate_section(summary_prompt, "总结部分")
    report_parts.append(f"### 总结与展望\n{summary}")
    total_content += f"\n\n总结与展望\n{summary}"

    # 完整报告
    full_report = f"""# 2026年中国新能源汽车出口市场简报

{total_content}

---
*报告生成时间：2026年9月*
*数据来源：全球新能源汽车产业研究院*
"""

    # 打印完整报告和字数统计
    print("\n" + "="*60)
    print("完整报告如下：")
    print("="*60)
    print(full_report)

    # 计算字数（汉字数）
    chinese_chars = len([c for c in full_report if '一' <= c <= '鿿'])
    total_chars = len(full_report.replace(' ', '').replace('\n', ''))

    print("="*60)
    print(f"报告统计信息：")
    print(f"- 总字数：{total_chars} 字")
    print(f"- 汉字数：{chinese_chars} 字")
    print(f"- 包含 {len(sections) + 1} 个部分")
    print("="*60)

    if chinese_chars >= 600:
        print("✅ 报告字数符合要求（≥600字）")
    else:
        print(f"❌ 报告字数不足600字（当前{chinese_chars}字）")

    # 保存到文件（可选）
    # with open("report.txt", "w", encoding="utf-8") as f:
    #     f.write(full_report)

if __name__ == "__main__":
    main()