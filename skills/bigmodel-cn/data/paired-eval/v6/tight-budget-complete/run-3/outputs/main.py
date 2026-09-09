#!/usr/bin/env python3
"""
2026 年中国新能源汽车出口市场简报生成器

由于网关限制，单次请求 max_tokens 不能超过 1000，因此将内容分成多个部分生成。
"""

import os
import requests
import json
import time
from typing import List, Dict, Optional


class NEVMarketReportGenerator:
    """新能源汽车市场简报生成器"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://open.bigmodel.cn/api/paas/v4"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.model = "glm-4.7-flash"  # 使用免费模型

    def generate_section(self, prompt: str, section_name: str, max_tokens: int = 900) -> str:
        """生成报告的一个部分"""
        print(f"正在生成 {section_name}...")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位专业的汽车行业分析师，专精于新能源汽车市场研究。请提供准确、详实、数据驱动的分析内容。使用正式、专业的中文表达，包含具体数据和小标题。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stream": False
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()

            content = result["choices"][0]["message"]["content"]
            print(f"✓ {section_name} 生成完成")
            return content.strip()

        except requests.exceptions.RequestException as e:
            print(f"✗ {section_name} 生成失败: {e}")
            return f"### {section_name}\n\n生成失败，请检查API配置。"

    def generate_introduction(self) -> str:
        """生成报告引言"""
        prompt = """请生成「2026 年中国新能源汽车出口」市场简报的引言部分。

要求：
1. 开篇点明中国新能源汽车产业的重要地位
2. 简要介绍 2026 年出口的整体情况
3. 提出报告的主要分析框架
4. 字数控制在 200 字左右

请包含具体年份（2026年）和关键数据。"""

        return self.generate_section(prompt, "引言", 200)

    def export_scale_and_growth(self) -> str:
        """生成出口规模与增长情况"""
        prompt = """请生成「2026 年中国新能源汽车出口」的规模与增长分析部分。

要求：
1. 包含具体的数据和增长率
2. 分析出口量、出口额等关键指标
3. 对比前几年的变化趋势
4. 指出增长的主要驱动力
5. 字数控制在 250 字左右

请包含具体年份（2026年）和量化数据。"""

        return self.generate_section(prompt, "出口规模与增长", 250)

    def generate_markets_analysis(self) -> str:
        """生成主要出口市场分析"""
        prompt = """请生成「2026 年中国新能源汽车出口」的主要市场分析部分。

要求：
1. 分析欧洲、东南亚、北美等主要出口市场
2. 各市场的占比和增长情况
3. 重点国家的政策和市场特点
4. 出口产品结构（乘用车、商用车等）
5. 字数控制在 200 字左右

请包含具体年份（2026年）和区域数据。"""

        return self.generate_section(prompt, "主要出口市场分析", 200)

    def generate_enterprises_analysis(self) -> str:
        """生成主要出口企业情况"""
        prompt = """请生成「2026 年中国新能源汽车出口」的主要企业分析部分。

要求：
1. 分析比亚迪、蔚来、小鹏等头部企业的表现
2. 企业的出口策略和竞争优势
3. 海外布局和本地化生产情况
4. 字数控制在 150 字左右

请包含具体年份（2026年）和企业名称。"""

        return self.generate_section(prompt, "主要出口企业分析", 150)

    def generate_future_trends(self) -> str:
        """生成未来发展趋势"""
        prompt = """请生成「2026 年中国新能源汽车出口」的未来发展趋势部分。

要求：
1. 分析技术发展趋势（电池、智能化等）
2. 市场格局演变预测
3. 政策环境影响
4. 国际竞争态势
5. 字数控制在 200 字左右

请包含具体年份（2026年）和前瞻性分析。"""

        return self.generate_section(prompt, "未来发展趋势", 200)

    def generate_challenges_opportunities(self) -> str:
        """生成挑战与机遇"""
        prompt = """请生成「2026 年中国新能源汽车出口」的挑战与机遇部分。

要求：
1. 分析面临的主要挑战（贸易壁垒、技术标准等）
2. 发展机遇和增长点
3. 应对策略建议
4. 字数控制在 200 字左右

请包含具体年份（2026年）和实用建议。"""

        return self.generate_section(prompt, "挑战与机遇", 200)

    def generate_conclusion(self) -> str:
        """生成报告结论"""
        prompt = """请生成「2026 年中国新能源汽车出口」的结论部分。

要求：
1. 总结主要观点和发现
2. 展望未来发展前景
3. 给出综合性评价
4. 字数控制在 150 字左右

请包含具体年份（2026年）和总结性观点。"""

        return self.generate_section(prompt, "结论", 150)

    def generate_full_report(self) -> str:
        """生成完整的市场简报"""
        print("=" * 60)
        print("开始生成 2026 年中国新能源汽车出口市场简报")
        print("=" * 60)

        # 生成各个部分
        introduction = self.generate_introduction()
        scale_growth = self.export_scale_and_growth()
        markets = self.generate_markets_analysis()
        enterprises = self.generate_enterprises_analysis()
        trends = self.generate_future_trends()
        challenges = self.generate_challenges_opportunities()
        conclusion = self.generate_conclusion()

        # 组合完整报告
        full_report = f"""# 2026 年中国新能源汽车出口市场简报

{introduction}

## 出口规模与增长情况

{scale_growth}

## 主要出口市场分析

{markets}

## 主要出口企业分析

{enterprises}

## 未来发展趋势

{trends}

## 挑战与机遇

{challenges}

## 结论

{conclusion}

---
*报告生成时间：2026年9月*
"""

        return full_report

    def count_chinese_characters(self, text: str) -> int:
        """统计中文字符数"""
        # 统计中文字符（包括中文标点）
        chinese_chars = len([c for c in text if '一' <= c <= '鿿'])
        return chinese_chars


def main():
    """主函数"""
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')

    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        print("例如：export ZHIPUAI_API_KEY='your_api_key_here'")
        return

    # 创建生成器实例
    generator = NEVMarketReportGenerator(api_key)

    # 生成完整报告
    full_report = generator.generate_full_report()

    # 输出报告
    print("\n" + "=" * 60)
    print("2026 年中国新能源汽车出口市场简报")
    print("=" * 60)
    print("\n")
    print(full_report)

    # 统计字数
    char_count = generator.count_chinese_characters(full_report)
    print(f"\n总字数：{char_count} 汉字")

    # 验证字数是否达到要求
    if char_count >= 600:
        print("✓ 报告字数符合要求（≥600字）")
    else:
        print("✗ 报告字数不足600字")

    return full_report


if __name__ == "__main__":
    main()