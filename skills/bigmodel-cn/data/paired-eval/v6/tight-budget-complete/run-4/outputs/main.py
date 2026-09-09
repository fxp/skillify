import os
import requests
import json
import time

def generate_market_report():
    """生成2026年中国新能源汽车出口市场简报"""

    # API配置
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 定义报告的各个部分
    sections = [
        {
            "title": "一、市场概述",
            "prompt": "请生成2026年中国新能源汽车出口市场的概述，包括总体规模、增长趋势等关键信息，内容要有数据支撑，控制在250字左右。"
        },
        {
            "title": "二、出口现状分析",
            "prompt": "请分析2026年中国新能源汽车出口的现状，包括出口数量、金额、主要特点等，需要具体数据，控制在250字左右。"
        },
        {
            "title": "三、主要出口市场",
            "prompt": "请列举2026年中国新能源汽车的主要出口市场，如欧洲、东南亚等地区，并分析各市场的特点和份额，控制在250字左右。"
        },
        {
            "title": "四、主要出口企业",
            "prompt": "请介绍2026年中国新能源汽车出口的主要企业，包括比亚迪、蔚来等企业的表现和优势，控制在250字左右。"
        },
        {
            "title": "五、未来趋势展望",
            "prompt": "请展望2027年中国新能源汽车出口的发展趋势，包括技术、市场、政策等方面，控制在250字左右。"
        },
        {
            "title": "六、总结",
            "prompt": "请总结2026年中国新能源汽车出口的整体情况，面临的挑战和机遇，控制在200字左右。"
        }
    ]

    report_content = ""

    print("开始生成市场简报...")

    for i, section in enumerate(sections):
        print(f"\n正在生成第 {i+1}/{len(sections)} 部分：{section['title']}")

        payload = {
            "model": "glm-4.7-flash",  # 使用免费模型
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的汽车行业分析师，请根据最新的市场数据，生成专业的分析报告。内容要准确、客观，有数据支撑。"
                },
                {
                    "role": "user",
                    "content": section['prompt']
                }
            ],
            "max_tokens": 1000,  # 严格遵守不超过1000的限制
            "temperature": 0.7,
            "stream": False
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()

            # 获取生成的内容
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 检查是否生成了内容
            if content:
                report_content += f"\n{section['title']}\n"
                report_content += content + "\n"
                print(f"✓ {section['title']} 生成成功")

                # 显示token使用情况
                usage = result.get("usage", {})
                total_tokens = usage.get("total_tokens", 0)
                print(f"  使用tokens: {total_tokens}")

                # 避免请求过于频繁
                time.sleep(1)
            else:
                print(f"✗ {section['title']} 生成失败，内容为空")

        except requests.exceptions.RequestException as e:
            print(f"✗ 请求失败: {e}")
            return None
        except Exception as e:
            print(f"✗ 发生错误: {e}")
            return None

    # 合并完整的报告
    full_report = """2026年中国新能源汽车出口市场简报

"""
    full_report += report_content

    # 计算字数
    char_count = len(full_report.replace("\n", "").replace(" ", ""))

    # 打印完整报告和字数
    print("\n" + "="*50)
    print("完整的市场简报如下：")
    print("="*50)
    print(full_report)
    print("="*50)
    print(f"\n报告总字数：{char_count} 字")

    if char_count >= 600:
        print("\n✓ 报告字数符合要求（不少于600字）")
    else:
        print(f"\n⚠ 报告字数不足600字，仅有{char_count}字")

    return full_report

if __name__ == "__main__":
    generate_market_report()