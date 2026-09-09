import os
import json
import requests
import re

def analyze_sentiment(texts):
    """
    使用智谱 GLM 对文本进行情感分类

    Args:
        texts: 文本列表

    Returns:
        list: 包含情感分析结果的字典列表，格式为 {"sentiment": "正面"/"负面"/"中性", "score": 0到1的数字}
    """
    # 从环境变量读取 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    # API 配置
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 分析结果列表
    results = []

    # 系统提示词，要求输出特定格式的 JSON
    system_prompt = """你是一个专业的情感分析专家。请对用户提供的文本进行情感分析，并严格按照以下 JSON 格式返回结果：
{
    "sentiment": "正面" | "负面" | "中性",
    "score": 0到1之间的数字（表示情感强度，越接近1表示情感越强烈）
}

要求：
1. sentiment 只能是"正面"、"负面"、"中性"三选一
2. score 必须是 0 到 1 之间的数字，保留小数点后2位
3. 只返回 JSON，不要包含任何其他文字或解释
4. 正面情感对应积极评价，负面情感对应消极评价，中性情感为客观或无明显倾向性"""

    # 对每条文本进行情感分析
    for text in texts:
        payload = {
            "model": "glm-4.6",  # 使用 glm-4.6 模型
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析以下文本的情感：\n\n{text}"}
            ],
            "response_format": {"type": "json_object"},  # 启用 JSON 模式
            "thinking": {"type": "disabled"},  # 关闭思考模式以节省 token
            "max_tokens": 200,
            "temperature": 0.1,  # 降低随机性，确保输出稳定
            "do_sample": True
        }

        try:
            # 发送请求
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            # 提取内容
            content = data["choices"][0]["message"]["content"]

            # 清理内容，移除可能的代码块标记
            cleaned_content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()

            # 解析 JSON
            result = json.loads(cleaned_content)

            # 验证结果格式
            if result.get("sentiment") not in ["正面", "负面", "中性"]:
                raise ValueError(f"无效的 sentiment 值: {result.get('sentiment')}")
            if not isinstance(result.get("score"), (int, float)) or not (0 <= result.get("score") <= 1):
                raise ValueError(f"无效的 score 值: {result.get('score')}")

            results.append(result)

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API 请求失败: {e}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"JSON 解析失败: {e}\n原始内容: {content}")
        except Exception as e:
            raise RuntimeError(f"处理文本失败: {e}")

    return results

def main():
    """主函数"""
    # 待分析的文本
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    try:
        # 进行情感分析
        results = analyze_sentiment(texts)

        # 输出结果
        print(json.dumps(results, ensure_ascii=False, indent=2))

        # 验证结果格式
        for i, result in enumerate(results):
            assert "sentiment" in result, f"结果 {i+1} 缺少 sentiment 字段"
            assert "score" in result, f"结果 {i+1} 缺少 score 字段"
            assert result["sentiment"] in ["正面", "负面", "中性"], f"结果 {i+1} 的 sentiment 值无效"
            assert isinstance(result["score"], (int, float)) and 0 <= result["score"] <= 1, f"结果 {i+1} 的 score 值无效"

        print("所有文本情感分析完成！")

    except Exception as e:
        print(f"错误: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())