import os
import requests
import json
import time

# 配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

def search_information(query):
    """搜索相关信息"""
    try:
        payload = {
            "model": "glm-5.3",
            "messages": [{"role": "user", "content": query}],
            "tools": [{
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_bing",
                    "search_result": True,
                    "count": 10
                }
            }],
            "max_tokens": 800
        }

        resp = requests.post(f"{BASE_URL}/chat/completions", headers=HEADERS, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()

        # 提取内容并记录来源
        content = result["choices"][0]["message"]["content"]
        sources = []

        # 获取搜索来源
        if "web_search" in result:
            for source in result["web_search"]:
                sources.append(f"{source.get('title', '未知标题')} - {source.get('link', '无链接')}")

        return content, sources, result.get("usage", {})

    except Exception as e:
        print(f"搜索失败: {e}")
        return "", [], {}

def generate_section(section_prompt, section_title):
    """生成报告的某个部分"""
    try:
        payload = {
            "model": "glm-5.3",
            "messages": [
                {"role": "system", "content": "你是一位资深的汽车行业市场分析师，请根据用户提供的信息生成详细、专业的市场分析报告。要求：1) 内容详实，数据准确；2) 逻辑清晰，结构合理；3) 语言专业，分析深入。"},
                {"role": "user", "content": section_prompt}
            ],
            "max_tokens": 800,
            "temperature": 0.7,
            "top_p": 0.9
        }

        resp = requests.post(f"{BASE_URL}/chat/completions", headers=HEADERS, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()

        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})

        return f"## {section_title}\n\n{content}", usage

    except Exception as e:
        print(f"生成 {section_title} 失败: {e}")
        return f"## {section_title}\n\n暂无数据", {}

def main():
    print("开始生成 2026 年中国新能源汽车出口市场简报...")

    # 检查 API Key
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 第一步：搜索最新数据
    print("\n1. 搜索最新市场数据...")
    search_query = "2026年中国新能源汽车出口数据 市场规模 出口量 主要出口国家 政策支持"
    market_data, sources, search_usage = search_information(search_query)

    if not market_data:
        print("搜索失败，无法获取数据")
        return

    print(f"搜索完成，使用了 {search_usage.get('total_tokens', 0)} tokens")

    # 第二步：生成引言部分
    print("\n2. 生成引言部分...")
    intro_prompt = f"""
    请根据以下信息，生成一份关于2026年中国新能源汽车出口市场的引言部分：

    {market_data}

    要求：
    - 简要介绍中国新能源汽车出口的重要性和发展背景
    - 概括当前市场状况和主要特点
    - 引用关键数据支撑观点
    - 字数控制在300字左右
    """

    intro, intro_usage = generate_section(intro_prompt, "引言：中国新能源汽车出口概况")

    # 第三步：生成出口分析部分
    print("\n3. 生成出口数据分析...")
    export_prompt = f"""
    请根据以下信息，生成2026年中国新能源汽车出口市场的详细分析：

    {market_data}

    要求：
    - 分析主要出口国家/地区分布
    - 出口车型和品牌表现
    - 出口量和市场规模数据
    - 国际市场竞争格局分析
    - 使用具体数据支撑分析
    - 字数控制在400字左右
    """

    export_data, export_usage = generate_section(export_prompt, "一、出口市场分析")

    # 第四步：生成政策环境部分
    print("\n4. 生成政策环境分析...")
    policy_prompt = f"""
    请根据以下信息，分析影响中国新能源汽车出口的政策环境：

    {market_data}

    要求：
    - 分析国家层面的支持政策
    - 国际贸易政策的影响
    - 技术标准和认证要求
    - 政策对出口的促进作用和面临的挑战
    - 字数控制在300字左右
    """

    policy, policy_usage = generate_section(policy_prompt, "二、政策环境分析")

    # 第五步：生成发展趋势部分
    print("\n5. 生成发展趋势预测...")
    trend_prompt = f"""
    请根据以下信息，预测2026-2027年中国新能源汽车出口的发展趋势：

    {market_data}

    要求：
    - 预测未来出口量增长趋势
    - 新兴市场的机会
    - 技术发展方向
    - 潜在的风险和挑战
    - 提出发展建议
    - 字数控制在300字左右
    """

    trend, trend_usage = generate_section(trend_prompt, "三、发展趋势与建议")

    # 第六步：生成总结部分
    print("\n6. 生成总结...")
    summary_prompt = f"""
    请基于以上所有分析，生成一份总结：

    市场概况：{intro.replace('## 引言：中国新能源汽车出口概况', '')}

    出口分析：{export_data.replace('## 一、出口市场分析', '')}

    政策环境：{policy.replace('## 二、政策环境分析', '')}

    发展趋势：{trend.replace('## 三、发展趋势与建议', '')}

    要求：
    - 总结核心观点
    - 强调竞争优势和机遇
    - 客观分析面临的挑战
    - 展望未来发展前景
    - 字数控制在200字左右
    """

    summary, summary_usage = generate_section(summary_prompt, "总结")

    # 汇总完整报告
    full_report = f"""# 2026年中国新能源汽车出口市场简报

{intro}

{export_data}

{policy}

{trend}

{summary}

---
*数据来源：*
"""

    for i, source in enumerate(sources[:5], 1):
        full_report += f"\n{i}. {source}"

    # 统计字数
    chinese_chars = len([c for c in full_report if '一' <= c <= '鿿'])
    total_chars = len(full_report)

    # 输出报告
    print("\n" + "="*50)
    print("2026年中国新能源汽车出口市场简报")
    print("="*50)
    print(full_report)
    print("\n" + "="*50)
    print(f"报告统计：")
    print(f"- 中文字符数：{chinese_chars}")
    print(f"- 总字符数：{total_chars}")
    print(f"- 总 Token 使用量：{search_usage.get('total_tokens', 0) + intro_usage.get('total_tokens', 0) + export_usage.get('total_tokens', 0) + policy_usage.get('total_tokens', 0) + trend_usage.get('total_tokens', 0) + summary_usage.get('total_tokens', 0)}")
    print("="*50)

if __name__ == "__main__":
    main()