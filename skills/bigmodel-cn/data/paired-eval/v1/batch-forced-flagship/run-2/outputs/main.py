import os
import json
import requests
import uuid
import time

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

def read_comments():
    """读取评论文件"""
    comments_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/paired-eval/fixtures/comments.txt"
    with open(comments_file, "r", encoding="utf-8") as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

def create_jsonl_batch_requests(comments):
    """创建 Batch API 所需的 JSONL 格式请求"""
    batch_requests = []

    for i, comment in enumerate(comments, 1):
        # 生成唯一的 custom_id，至少6个字符
        custom_id = f"req-{i:04d}"

        request = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-5.3",  # 尝试使用 glm-5.3
                "messages": [
                    {
                        "role": "system",
                        "content": """你是一个专业的情感分类助手。请对用户评论进行情感分析，要求：
1. 只输出一个分类结果：正面、负面、中性
2. 简要说明理由（10字以内）
3. 以JSON格式返回，格式如下：
{"sentiment": "正面/负面/中性", "reason": "理由"}"""
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 50
            }
        }
        batch_requests.append(request)

    return batch_requests

def upload_batch_file(jsonl_content):
    """上传 Batch 请求文件"""
    try:
        files = {
            "file": ("batch_requests.jsonl", jsonl_content, "application/json")
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
            print(f"✗ 文件上传失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None

    except Exception as e:
        print(f"✗ 文件上传异常: {str(e)}")
        return None

def create_batch_task(input_file_id):
    """创建 Batch 任务"""
    try:
        payload = {
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {
                "description": "用户评论情感分类任务",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_requests": len(read_comments())
            }
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
            print(f"✓ Batch 任务创建成功!")
            print(f"任务ID: {batch_info['id']}")
            print(f"任务状态: {batch_info['status']}")
            print(f"请通过以下方式查看任务进度:")
            print(f"  curl -H 'Authorization: Bearer {API_KEY}' '{BASE_URL}/paas/v4/batches/{batch_info['id']}'")
            return batch_info["id"]
        else:
            print(f"✗ Batch 任务创建失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None

    except Exception as e:
        print(f"✗ Batch 任务创建异常: {str(e)}")
        return None

def fallback_to_standard_api(comments):
    """当 Batch API 不支持 glm-5.3 时的备选方案"""
    print("\n⚠️ 检测到 Batch API 可能不支持 glm-5.3")
    print("将使用标准 API 逐条处理（注意：这会消耗实时并发额度）")

    results = []

    for i, comment in enumerate(comments, 1):
        try:
            response = requests.post(
                f"{BASE_URL}/paas/v4/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={
                    "model": "glm-5.3",
                    "messages": [
                        {
                            "role": "system",
                            "content": """你是一个专业的情感分类助手。请对用户评论进行情感分析，要求：
1. 只输出一个分类结果：正面、负面、中性
2. 简要说明理由（10字以内）
3. 以JSON格式返回，格式如下：
{"sentiment": "正面/负面/中性", "reason": "理由"}"""
                        },
                        {
                            "role": "user",
                            "content": f"请对以下评论进行情感分类：{comment}"
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 50
                }
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                results.append({
                    "comment": comment,
                    "result": content,
                    "index": i
                })
                print(f"处理完成 {i}/{len(comments)}: {content}")
            else:
                print(f"✗ 处理第 {i} 条评论失败: {response.status_code}")
                results.append({
                    "comment": comment,
                    "error": response.text,
                    "index": i
                })

        except Exception as e:
            print(f"✗ 处理第 {i} 条评论异常: {str(e)}")
            results.append({
                "comment": comment,
                "error": str(e),
                "index": i
            })

        # 避免请求过快
        time.sleep(0.1)

    # 保存结果到文件
    with open("/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/paired-eval/v1/batch-forced-flagship/run-2/outputs/sentiment_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 处理完成！结果已保存到 outputs/sentiment_results.json")
    return results

def main():
    """主函数"""
    print("=" * 60)
    print("用户评论情感分析 - GLM-5.3 Batch API 处理")
    print("=" * 60)

    # 检查 API Key
    if not API_KEY:
        print("✗ 错误：请设置环境变量 ZHIPUAI_API_KEY")
        print("示例: export ZHIPUAI_API_KEY='your_api_key_here'")
        return

    # 读取评论
    print("\n1. 读取评论文件...")
    comments = read_comments()
    print(f"✓ 共读取 {len(comments)} 条评论")

    # 创建 JSONL 请求
    print("\n2. 创建 Batch 请求...")
    batch_requests = create_jsonl_batch_requests(comments)
    jsonl_content = "\n".join([json.dumps(req) for req in batch_requests])
    print(f"✓ 共创建 {len(batch_requests)} 个请求")

    # 上传文件
    print("\n3. 上传请求文件...")
    input_file_id = upload_batch_file(jsonl_content)

    if input_file_id:
        # 尝试创建 Batch 任务
        print("\n4. 创建 Batch 任务...")
        batch_id = create_batch_task(input_file_id)

        if batch_id:
            print(f"\n🎉 任务提交成功！")
            print(f"请使用以下命令查看任务状态：")
            print(f"python3 -c \"import requests; import json; r = requests.get('https://open.bigmodel.cn/api/paas/v4/batches/{batch_id}', headers={{'Authorization': 'Bearer {API_KEY}'}}); print(json.dumps(r.json(), indent=2))\"")
        else:
            print(f"\n⚠️ Batch 任务创建失败，可能是 glm-5.3 不在支持列表中")
            print("建议使用备选方案或更换为 Batch 支持的模型（如 glm-4-plus）")
    else:
        print(f"\n⚠️ 文件上传失败，可能是 glm-5.3 不在 Batch 支持列表中")
        print("尝试使用备选方案...")

    # 备选方案：使用标准 API
    if not input_file_id or not batch_id:
        print("\n" + "=" * 60)
        print("启动备选方案：使用标准 API 逐条处理")
        print("=" * 60)
        fallback_to_standard_api(comments)

if __name__ == "__main__":
    main()