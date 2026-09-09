import os
import requests
import json
import time

def generate_report_section(prompt, model="glm-4.7-flash", max_tokens=1000):
    """生成报告的一个部分"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "do_sample": True,
    }

    try:
        print(f"正在发送请求到模型 {model}，max_tokens={max_tokens}")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        # 检查响应格式
        if "choices" not in result or len(result["choices"]) == 0:
            print("错误: API 返回格式异常，没有 choices 字段")
            return None

        content = result["choices"][0]["message"]["content"]
        print(f"成功生成内容，长度: {len(content)} 字符")
        return content

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP 错误: {http_err}")
        try:
            error_info = http_err.response.json()
            print(f"错误详情: {error_info}")
            if "error" in error_info:
                error_code = error_info["error"].get("code", "Unknown")
                error_msg = error_info["error"].get("message", "Unknown error")
                print(f"错误代码: {error_code}, 错误信息: {error_msg}")
        except:
            print("无法解析错误响应")
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"请求异常: {req_err}")
        return None
    except Exception as e:
        print(f"未知错误: {e}")
        return None

def main():
    # 检查 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return

    print("正在生成「2026 年中国新能源汽车出口」市场简报...\n")

    # 生成报告引言
    print("正在生成引言部分...")
    intro_prompt = """请生成「2026 年中国新能源汽车出口」市场简报的引言部分。
要求：
1. 简要介绍中国新能源汽车产业的发展背景
2. 提到新能源汽车出口的重要性和现状
3. 字数控制在 200 字以内
4. 语言正式、专业，适合市场报告使用"""

    intro = generate_report_section(intro_prompt)
    if not intro:
        print("生成引言失败")
        return
    print("引言生成完成\n")

    # 生成出口规模分析
    print("正在生成出口规模分析...")
    scale_prompt = """请生成「2026 年中国新能源汽车出口规模分析」部分。
要求：
1. 包含具体数据和统计信息
2. 分析出口量、出口额的增长趋势
3. 提及主要出口市场和地区分布
4. 字数控制在 250 字以内
5. 包含至少 3 个具体数据点"""

    scale = generate_report_section(scale_prompt)
    if not scale:
        print("生成出口规模分析失败")
        return
    print("出口规模分析生成完成\n")

    # 生成竞争优势分析
    print("正在生成竞争优势分析...")
    advantage_prompt = """请生成「中国新能源汽车出口竞争优势分析」部分。
要求：
1. 分析中国新能源汽车的核心竞争优势
2. 提及产业链、技术、成本等方面的优势
3. 对比国际竞争对手的情况
4. 字数控制在 250 字以内
5. 提及至少 2-3 个具体优势点"""

    advantage = generate_report_section(advantage_prompt)
    if not advantage:
        print("生成竞争优势分析失败")
        return
    print("竞争优势分析生成完成\n")

    # 生成挑战与机遇
    print("正在生成挑战与机遇分析...")
    challenge_prompt = """请生成「中国新能源汽车出口面临的挑战与机遇」部分。
要求：
1. 分析当前面临的主要挑战（如贸易壁垒、技术标准等）
2. 提到未来发展的重要机遇
3. 字数控制在 200 字以内
4. 平衡客观分析挑战和积极展望机遇"""

    challenge = generate_report_section(challenge_prompt)
    if not challenge:
        print("生成挑战与机遇分析失败")
        return
    print("挑战与机遇分析生成完成\n")

    # 生成未来展望
    print("正在生成未来展望...")
    outlook_prompt = """请生成「2026-2027 年中国新能源汽车出口展望」部分。
要求：
1. 展望未来 1-2 年的发展趋势
2. 提出发展建议和预测
3. 字数控制在 200 字以内
4. 展望要积极、前瞻、有说服力"""

    outlook = generate_report_section(outlook_prompt)
    if not outlook:
        print("生成未来展望失败")
        return
    print("未来展望生成完成\n")

    # 组合完整报告
    full_report = f"""# 2026 年中国新能源汽车出口市场简报

## 引言
{intro}

## 出口规模分析
{scale}

## 中国新能源汽车出口竞争优势分析
{advantage}

## 面临的挑战与机遇
{challenge}

## 未来展望
{outlook}
"""

    # 打印完整报告
    print("\n" + "="*50)
    print("「2026 年中国新能源汽车出口」市场简报")
    print("="*50 + "\n")
    print(full_report)

    # 计算字数
    char_count = len(full_report.replace(' ', ''))
    print(f"报告总字数: {char_count} 字")

    # 验证字数要求
    if char_count >= 600:
        print("\n✓ 报告字数满足要求（不少于 600 字）")
    else:
        print(f"\n✗ 报告字数不足 600 字，当前只有 {char_count} 字")

if __name__ == "__main__":
    main()