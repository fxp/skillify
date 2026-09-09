import os
import requests
import json
import re
import time

def get_api_key():
    """从环境变量获取API Key"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return None
    return api_key

def generate_market_report():
    """生成2026年中国新能源汽车出口市场简报"""
    api_key = get_api_key()
    if not api_key:
        return None

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 设计一个高效的提示词，在有限的token内生成高质量内容
    prompt = """请基于以下最新数据生成一份关于2026年中国新能源汽车出口的市场简报：

**最新数据参考**：
- 2026年前4个月，中国汽车出口累计达135.2万辆，同比增长48.4%
- 新能源汽车出口：2026年前两个月出口58.3万辆，同比激增1.1倍
- 4月单月出口同比增长超过110%，创历史新高
- 2026年1-5月出口前十国家：巴西(28.9万)、比利时(15.5万)、英国(18.9万)、阿联酋(5.3万)、意大利等
- 主要企业表现：比亚迪上半年新能源客车出口2233辆，市场份额22.15%；奇瑞表现优异
- 咨询公司预测2026年中国汽车出口将增长到1000万辆

要求：

1. 内容结构：
   - 市场规模与增长趋势
   - 主要出口国家与地区分析
   - 竞争格局与主要企业表现
   - 发展机遇与挑战
   - 未来展望

2. 内容要求：
   - 使用提供的最新数据，结合行业背景进行分析
   - 包含具体数字和增长率
   - 有小标题，结构清晰
   - 正文不少于600汉字
   - 分析要有深度和见解，体现专业性

3. 输出格式：
   - 直接输出正文，不需要任何开场白或结束语
   - 使用markdown格式，包含2-3级标题
   - 段落之间空一行

请确保内容专业、准确、有数据支撑，展现中国新能源汽车出口的强劲态势和发展前景。"""

    payload = {
        "model": "glm-5.3",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000,  # 严格遵守不超过1000的限制
        "temperature": 0.7,
        "stream": False
    }

    try:
        print("正在生成市场简报...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            # 提取token使用情况
            usage = result.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

            return {
                "content": content,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }
        else:
            print("API响应格式异常")
            return None

    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        return None
    except Exception as e:
        print(f"未知错误: {e}")
        return None

def count_chinese_characters(text):
    """统计中文字符数"""
    # 匹配中文字符
    chinese_chars = re.findall(r'[一-鿿]', text)
    return len(chinese_chars)

def print_report_with_stats(report):
    """打印市场简报和统计信息"""
    if not report or not report.get("content"):
        print("未能生成市场简报")
        return

    content = report["content"]
    chinese_count = count_chinese_characters(content)

    print("=" * 60)
    print("2026年中国新能源汽车出口市场简报")
    print("=" * 60)
    print()
    print(content)
    print()
    print("=" * 60)
    print("统计信息")
    print("=" * 60)
    print(f"正文中文字数: {chinese_count}")
    print(f"总字符数: {len(content)}")
    print(f"Token使用情况:")
    print(f"  输入Token数: {report['prompt_tokens']}")
    print(f"  输出Token数: {report['completion_tokens']}")
    print(f"  总Token数: {report['total_tokens']}")
    print(f"  预估费用: ${report['completion_tokens'] * 0.002 / 1000:.4f}")  # 假设glm-5.3每千token2美元

    # 验证是否满足要求
    print("\n要求验证:")
    print(f"  ✓ 字数要求(≥600): {'满足' if chinese_count >= 600 else '不满足'}")
    print(f"  ✓ Token限制(≤1000): {'满足' if report['completion_tokens'] <= 1000 else '不满足'}")

def main():
    """主函数"""
    print("开始生成2026年中国新能源汽车出口市场简报...")
    print("API Key:", os.environ.get('ZHIPUAI_API_KEY', '未设置')[:10] + "..." if os.environ.get('ZHIPUAI_API_KEY') else '未设置')
    print()

    report = generate_market_report()

    if report:
        print_report_with_stats(report)
    else:
        print("生成市场简报失败，请检查API Key和网络连接。")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())