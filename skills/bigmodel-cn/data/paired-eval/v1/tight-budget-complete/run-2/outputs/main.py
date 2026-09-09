import os
import requests
import json

# 配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 使用glm-5.3模型

# 验证API Key
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

def generate_content(prompt, max_tokens=1000):
    """生成内容的函数，确保不超过max_tokens限制"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.8,
        "stream": False
    }

    try:
        response = requests.post(BASE_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"生成内容时出错: {e}")
        return None

def generate_report():
    """生成完整的2026年中国新能源汽车出口市场简报"""

    # 生成标题和引言
    print("正在生成标题和引言...")
    intro_prompt = """基于以下真实数据，为《2026年中国新能源汽车出口市场简报》写一个标题和引言。

真实数据背景：
- 2026年1-5月中国新能源汽车出口183.3万辆，同比增长78.5%
- 全球市场份额达到61%
- 全年预计出口1000万辆汽车，新能源汽车占据重要比例

要求：
1. 标题要简明扼要，突出主题
2. 引言部分简要介绍中国新能源汽车出口的背景和意义
3. 约150汉字
4. 语言正式、客观"""

    intro = generate_content(intro_prompt, 500)

    # 生成市场概况
    print("正在生成市场概况...")
    market_prompt = """基于以下真实数据，分析2026年中国新能源汽车出口的市场概况：

具体数据：
- 2026年1-5月：新能源汽车出口183.3万辆，同比增长78.5%
- 2026年2月：单月出口32万辆，同比增长120%
- 2026年4月：单月出口43万辆，同比增长1.1倍
- 全球市场份额：61%
- 主要出口市场：欧洲17%、南半球79%、东南亚和西亚46%

要求：
1. 整合以上数据进行分析
2. 展示中国新能源汽车在全球市场的地位
3. 描述主要市场分布情况
4. 约200汉字
5. 语言专业客观"""

    market = generate_content(market_prompt, 500)

    # 生成政策环境分析
    print("正在生成政策环境分析...")
    policy_prompt = """基于以下真实政策背景，分析2026年中国新能源汽车出口的政策环境：

政策背景：
- 2026年1月1日起：商务部等四部门对纯电动乘用车实施出口许可证管理
- 欧盟《新电池法》实施：碳足迹标签、碳边境调节等监管措施
- 各车企加速海外本地化生产布局

要求：
1. 分析国家出口管理政策
2. 欧盟等主要市场的政策影响
3. 贸易壁垒与应对措施
4. 对出口的影响分析
5. 约200汉字
6. 语言专业客观"""

    policy = generate_content(policy_prompt, 500)

    # 生成主要企业表现
    print("正在生成主要企业表现...")
    companies_prompt = """基于以下真实数据，分析2026年中国新能源汽车主要出口企业的表现：

企业目标：
- 比亚迪：海外销量目标130万辆，同比增长24.3%
- 上汽集团：海外销量目标150万辆
- 蔚来汽车：在葡萄牙、希腊等国拓展市场

市场布局：
- 比亚迪：在巴西、泰国、匈牙利建设生产基地
- 其他企业：带动产业链企业海外扩张

要求：
1. 分析头部企业的出口目标和战略
2. 描述海外市场布局情况
3. 分析竞争优势
4. 约200汉字
5. 语言专业客观"""

    companies = generate_content(companies_prompt, 500)

    # 生成技术发展分析
    print("正在生成技术发展分析...")
    tech_prompt = """基于以下背景，分析2026年中国新能源汽车出口的技术发展情况：

技术背景：
- 中国新能源汽车技术竞争力持续提升
- 全球新能源车市场份额达到61%
- 从"出口"向"本地化生产"转变

要求：
1. 分析技术竞争优势
2. 电池和智能驾驶技术进展
3. 国际技术地位
4. 约150汉字
5. 语言专业客观"""

    tech = generate_content(tech_prompt, 500)

    # 生成未来趋势预测
    print("正在生成未来趋势预测...")
    future_prompt = """基于当前发展趋势，预测2027-2030年中国新能源汽车出口的未来趋势：

当前趋势：
- 从"出口"向"本地化生产"转变
- 全球市场份额已达61%
- 各车企加速海外布局

要求：
1. 预测出口规模和市场格局
2. 分析本地化生产趋势
3. 展望技术发展方向
4. 挑战与机遇分析
5. 约150汉字
6. 语言专业客观"""

    future = generate_content(future_prompt, 500)

    # 拼接完整报告
    report = f"""
{'='*50}
2026年中国新能源汽车出口市场简报
{'='*50}

{intro}

{'一、市场概况', '='*30}
{market}

{'二、政策环境分析', '='*30}
{policy}

{'三、主要企业表现', '='*30}
{companies}

{'四、技术发展分析', '='*30}
{tech}

{'五、未来趋势预测', '='*30}
{future}

{'='*50}
报告生成时间：2026年9月
{'='*50}
"""

    return report

if __name__ == "__main__":
    print("开始生成2026年中国新能源汽车出口市场简报...")
    print("注意：由于max_tokens限制为1000，报告将分为多个部分生成")

    report = generate_report()

    # 打印完整报告
    print("\n\n" + "="*60)
    print("2026年中国新能源汽车出口市场简报（完整版）")
    print("="*60)
    print(report)

    # 统计字数
    content_length = len(report.replace(" ", "").replace("\n", ""))
    chinese_count = len([c for c in report if '一' <= c <= '鿿'])

    print(f"\n实际字数统计：")
    print(f"- 总字符数：{content_length}")
    print(f"- 汉字数：{chinese_count}")
    print(f"- 是否达到600汉字要求：{'是' if chinese_count >= 600 else '否'}")

    print("\n报告生成完成！")