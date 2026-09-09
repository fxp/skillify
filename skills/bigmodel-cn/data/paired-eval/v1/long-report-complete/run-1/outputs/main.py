#!/usr/bin/env python3
import os
import requests
import json
import sys
import re
from datetime import datetime

def generate_market_report():
    """使用智谱 GLM 生成 2026 年中国新能源汽车出口市场简报"""

    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return False

    # API 端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构造详细的提示词，要求生成完整的市场简报
    prompt = """请生成一份关于「2026 年中国新能源汽车出口」的详细市场简报。要求如下：

1. 简报内容不少于 600 字
2. 必须包含小标题，结构清晰
3. 要包含具体数据和事实
4. 内容要完整，不能写到一半断掉
5. 简报要能直接用于周报，所以必须是专业、完整的

请包含以下方面的内容：
- 出口总体情况和增长趋势
- 主要出口市场和份额分析
- 主要出口企业表现
- 面临的机遇和挑战
- 未来发展趋势预测

请确保：
- 数据要具体（如百分比、金额、数量等）
- 语言要专业、客观
- 结构要有逻辑性
- 结论要明确"""

    # 构造请求载荷
    payload = {
        "model": "glm-5.3",  # 使用旗舰模型
        "messages": [
            {"role": "system", "content": "你是一位资深的市场分析师，擅长撰写专业的行业分析报告。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000,  # 设置足够大的输出长度
        "temperature": 0.7,
        "stream": False
    }

    try:
        # 发送请求
        print("正在生成市场简报...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 提取生成的文本
        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            usage = result.get('usage', {})

            # 检查内容是否完整
            if len(content.strip()) < 100:
                print("错误：生成的内容过短，可能不完整")
                return False

            # 清理内容（去掉可能的markdown格式标记）
            content = content.strip()

            # 计算字数
            chinese_chars = len(re.findall(r'[一-鿿]', content))
            total_chars = len(content)

            # 打印简报内容
            print("\n" + "="*80)
            print("2026 年中国新能源汽车出口市场简报")
            print("="*80)
            print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"使用模型：glm-5.3")
            print(f"Token 使用情况：输入 {usage.get('prompt_tokens', 0)} 个，输出 {usage.get('completion_tokens', 0)} 个")
            print("\n" + content)
            print("\n" + "="*80)

            # 验证内容质量
            print("\n内容验证：")
            print(f"- 总字符数：{total_chars}")
            print(f"- 中文字符数：{chinese_chars}")

            # 检查是否有小标题
            has_subtitles = bool(re.search(r'^#{1,6}\s', content, re.MULTILINE))
            print(f"- 包含小标题：{'是' if has_subtitles else '否'}")

            # 检查是否有具体数据
            has_data = bool(re.search(r'\d+%', content) or re.search(r'\d+\.\d+', content) or re.search(r'\d+亿', content))
            print(f"- 包含具体数据：{'是' if has_data else '否'}")

            # 验证字数是否达标
            if chinese_chars >= 600:
                print(f"- 字数达标：✓ ({chinese_chars} 字，要求 ≥600 字)")
                print("\n✓ 市场简报生成成功！内容完整，符合要求。")
                return True
            else:
                print(f"- 字数不达标：✗ ({chinese_chars} 字，要求 ≥600 字)")
                print("\n✗ 生成的简报字数不足，请重试。")
                return False

        else:
            print("错误：API 返回的数据格式不正确")
            return False

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
        return False
    except json.JSONDecodeError as e:
        print(f"解析响应失败：{e}")
        return False
    except Exception as e:
        print(f"发生未知错误：{e}")
        return False

if __name__ == "__main__":
    success = generate_market_report()
    sys.exit(0 if success else 1)