#!/usr/bin/env python3
"""
评论情感分析脚本
使用智谱AI API对评论进行情感分类
优先使用glm-5.3，如果不可用则回退到Batch API支持的模型
"""

import os
import json
import requests
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 模型配置
PREFERRED_MODEL = "glm-5.3"  # 首选模型
BATCH_FALLBACK_MODEL = "glm-4-plus"  # Batch API 回退模型
BATCH_ENDPOINT = "/paas/v4/chat/completions"

# 情感分析提示
SENTIMENT_PROMPT = """你是一个专业的情感分析师。请对以下用户评论进行情感分类，返回JSON格式结果，包含以下字段：
- sentiment: 情感倾向（"正面"、"负面"、"中性"）
- confidence: 置信度（0-1之间的数值）
- keywords: 关键词列表（影响情感判断的关键词）
- reason: 判断理由（简短说明）

只返回JSON，不要其他内容。

评论内容：{comment}"""

def read_comments(file_path: str) -> List[str]:
    """读取评论文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            comments = [line.strip() for line in f if line.strip()]
        return comments
    except FileNotFoundError:
        print(f"错误：文件 {file_path} 不存在")
        return []
    except Exception as e:
        print(f"读取文件时出错：{e}")
        return []

def create_jsonl_requests(comments: List[str], model: str) -> List[str]:
    """创建JSONL格式的请求"""
    requests = []
    for i, comment in enumerate(comments, 1):
        request_data = {
            "custom_id": f"request-{i:03d}",
            "method": "POST",
            "url": BATCH_ENDPOINT,
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个专业的情感分析师。"},
                    {"role": "user", "content": SENTIMENT_PROMPT.format(comment=comment)}
                ],
                "temperature": 0.1,
                "max_tokens": 500
            }
        }
        requests.append(json.dumps(request_data))
    return requests

def upload_batch_file(jsonl_content: str) -> Optional[str]:
    """上传批处理文件"""
    try:
        files = {
            "file": ("batch_requests.jsonl", jsonl_content, "application/jsonl")
        }
        data = {"purpose": "batch"}

        response = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {API_KEY}"},
            files=files,
            data=data
        )

        if response.status_code == 200:
            file_info = response.json()
            print(f"✓ 文件上传成功: {file_info['id']}")
            return file_info["id"]
        else:
            print(f"✗ 文件上传失败: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"✗ 上传文件时出错: {e}")
        return None

def create_batch_task(input_file_id: str, metadata: Dict = None) -> Optional[str]:
    """创建批处理任务"""
    try:
        payload = {
            "input_file_id": input_file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": metadata or {"description": "评论情感分析"}
        }

        response = requests.post(
            f"{BASE_URL}/paas/v4/batches",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload
        )

        if response.status_code == 200:
            batch_info = response.json()
            print(f"✓ Batch任务创建成功: {batch_info['id']}")
            print(f"  状态: {batch_info['status']}")
            print(f"  请求数量: {batch_info.get('request_counts', {}).get('total', 'N/A')}")
            return batch_info["id"]
        else:
            print(f"✗ 创建Batch任务失败: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"✗ 创建Batch任务时出错: {e}")
        return None

def check_batch_status(batch_id: str) -> Dict:
    """检查Batch任务状态"""
    try:
        response = requests.get(
            f"{BASE_URL}/paas/v4/batches/{batch_id}",
            headers={"Authorization": f"Bearer {API_KEY}"}
        )

        if response.status_code == 200:
            return response.json()
        else:
            print(f"✗ 查询Batch状态失败: {response.status_code}")
            return None

    except Exception as e:
        print(f"✗ 查询Batch状态时出错: {e}")
        return None

def batch_sentiment_analysis(comments: List[str]) -> Optional[str]:
    """使用Batch API进行情感分析"""
    print("📊 尝试使用Batch API进行情感分析...")

    # 创建JSONL请求
    jsonl_requests = create_jsonl_requests(comments, BATCH_FALLBACK_MODEL)
    jsonl_content = "\n".join(jsonl_requests)

    # 上传文件
    input_file_id = upload_batch_file(jsonl_content)
    if not input_file_id:
        return None

    # 创建Batch任务
    batch_id = create_batch_task(input_file_id, {"project": "sentiment_analysis"})
    if not batch_id:
        return None

    return batch_id

def single_api_sentiment_analysis(comments: List[str]) -> List[Dict]:
    """使用标准API进行单次情感分析（回退方案）"""
    print("🔄 使用标准API进行单次情感分析...")

    results = []

    for i, comment in enumerate(comments, 1):
        print(f"处理第 {i}/{len(comments)} 条评论...")

        try:
            response = requests.post(
                f"{BASE_URL}/paas/v4/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={
                    "model": PREFERRED_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的情感分析师。"},
                        {"role": "user", "content": SENTIMENT_PROMPT.format(comment=comment)}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500
                }
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # 尝试解析JSON响应
                try:
                    analysis = json.loads(content)
                    analysis["comment"] = comment
                    analysis["comment_index"] = i
                    results.append(analysis)
                    print(f"✓ 分析完成: {analysis.get('sentiment', '未知')}")
                except json.JSONDecodeError:
                    # 如果不是JSON格式，创建基础结果
                    results.append({
                        "comment": comment,
                        "comment_index": i,
                        "sentiment": "未知",
                        "confidence": 0.0,
                        "keywords": [],
                        "reason": "解析JSON失败",
                        "raw_response": content
                    })
                    print(f"✗ JSON解析失败，使用基础结果")
            else:
                print(f"✗ API调用失败: {response.status_code}")
                results.append({
                    "comment": comment,
                    "comment_index": i,
                    "sentiment": "错误",
                    "confidence": 0.0,
                    "keywords": [],
                    "reason": f"API调用失败: {response.status_code}"
                })

        except Exception as e:
            print(f"✗ 处理评论时出错: {e}")
            results.append({
                "comment": comment,
                "comment_index": i,
                "sentiment": "错误",
                "confidence": 0.0,
                "keywords": [],
                "reason": str(e)
            })

        # 添加延迟避免速率限制
        time.sleep(1)

    return results

def main():
    """主函数"""
    # 读取评论
    comments_file = os.path.join(os.path.dirname(__file__), "../comments.txt")
    comments = read_comments(comments_file)

    if not comments:
        print("❌ 没有找到评论数据")
        return

    print(f"📝 读取到 {len(comments)} 条评论")
    print("=" * 50)

    # 首先尝试使用Batch API
    batch_id = batch_sentiment_analysis(comments)

    if batch_id:
        print("\n🎉 Batch任务创建成功！")
        print(f"📋 任务ID: {batch_id}")
        print("💡 提示：")
        print("  1. 您可以使用此ID查询任务状态")
        print("  2. 任务预计24小时内完成")
        print("  3. 完成后可以下载结果文件")
        print("\n📊 查询任务状态命令:")
        print(f"curl -H 'Authorization: Bearer {API_KEY}' '{BASE_URL}/paas/v4/batches/{batch_id}'")
    else:
        print("\n⚠️ Batch API创建失败，使用标准API处理...")
        results = single_api_sentiment_analysis(comments)

        if results:
            print("\n📊 分析结果预览:")
            for result in results[:3]:  # 显示前3个结果
                print(f"  评论{result['comment_index']}: {result['sentiment']} "
                      f"(置信度: {result['confidence']:.2f})")
            if len(results) > 3:
                print(f"  ... 还有 {len(results) - 3} 个结果")

            # 保存结果
            output_file = os.path.join(os.path.dirname(__file__), "sentiment_results.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n💾 结果已保存到: {output_file}")

if __name__ == "__main__":
    main()