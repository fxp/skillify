import os
import json
import requests
import io
from pathlib import Path

def read_comments(file_path):
    """读取评论文件，每行一条评论"""
    with open(file_path, 'r', encoding='utf-8') as f:
        comments = [line.strip() for line in f if line.strip()]
    return comments

def create_jsonl_batch_requests(comments, model="glm-5.3"):
    """创建批处理请求的 JSONL 内容"""
    lines = []
    for i, comment in enumerate(comments):
        # custom_id 最少需要6个字符
        custom_id = f"req-{i+1:06d}"

        # 构造请求体
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个情感分析专家，请对用户评论进行情感分类。请只返回JSON格式，包含两个字段：sentiment（取值为'正面'、'负面'或'中性'）和score（0到1之间的数字，表示情感强度，0为最负面，1为最正面）。"
                },
                {
                    "role": "user",
                    "content": f"请对以下评论进行情感分类：{comment}"
                }
            ],
            "temperature": 0.1,
            "max_tokens": 200
        }

        line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": body
        }
        lines.append(json.dumps(line, ensure_ascii=False))

    return "\n".join(lines)

def upload_batch_file(jsonl_content, api_key, base_url):
    """上传批处理文件"""
    headers = {"Authorization": f"Bearer {api_key}"}

    # 使用BytesIO来处理内存中的jsonl内容
    jsonl_bytes = io.BytesIO(jsonl_content.encode('utf-8'))

    files = {"file": ("batch_requests.jsonl", jsonl_bytes, "application/json")}
    data = {"purpose": "batch"}

    response = requests.post(
        f"{base_url}/paas/v4/files",
        headers=headers,
        files=files,
        data=data
    )
    response.raise_for_status()
    return response.json()

def create_batch_job(input_file_id, api_key, base_url):
    """创建批处理任务"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v4/chat/completions",
        "auto_delete_input_file": True,
        "metadata": {
            "description": "用户评论情感分析任务",
            "total_requests": input_file_id
        }
    }

    response = requests.post(
        f"{base_url}/paas/v4/batches",
        headers=headers,
        json=payload
    )
    response.raise_for_status()
    return response.json()

def main():
    # 配置
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    base_url = "https://open.bigmodel.cn/api"
    comments_file = "comments.txt"

    # 读取评论
    try:
        comments = read_comments(comments_file)
        print(f"成功读取 {len(comments)} 条评论")
    except FileNotFoundError:
        print(f"错误：找不到文件 {comments_file}")
        return

    # 尝试使用指定的模型（glm-5.3）
    models_to_try = ["glm-5.3", "glm-5.1"]  # glm-5.3 不在Batch白名单中，失败后降级

    for model in models_to_try:
        print(f"\n尝试使用模型: {model}")

        try:
            # 创建JSONL请求
            jsonl_content = create_jsonl_batch_requests(comments, model)
            print(f"创建JSONL内容成功，长度: {len(jsonl_content)} 字符")

            # 上传文件
            print("正在上传批处理文件...")
            upload_result = upload_batch_file(jsonl_content, api_key, base_url)
            input_file_id = upload_result["id"]
            print(f"文件上传成功，ID: {input_file_id}")

            # 创建批处理任务
            print("正在创建批处理任务...")
            batch_result = create_batch_job(input_file_id, api_key, base_url)
            batch_id = batch_result["id"]
            status = batch_result["status"]

            print(f"\n✅ 批处理任务创建成功！")
            print(f"Batch ID: {batch_id}")
            print(f"任务状态: {status}")
            print(f"请使用以下URL查看任务进度:")
            print(f"{base_url}/batches/{batch_id}")

            return  # 成功则退出

        except requests.exceptions.HTTPError as e:
            error_msg = e.response.json() if e.response else str(e)

            # 检查是否是模型不在白名单中的错误
            if "模型名称错误" in error_msg or "1210" in str(error_msg):
                print(f"⚠️  模型 {model} 不在Batch API白名单中，尝试下一个模型...")
                if model == models_to_try[-1]:
                    print("错误：所有可用模型都已尝试，无法创建批处理任务")
                    print("Batch API支持的模型（白名单）：glm-5.1, glm-5-turbo, glm-4, glm-4-plus, glm-4-flash等")
                    print("建议使用同步API或联系智谱客服确认最新白名单")
                continue
            else:
                print(f"❌ 请求失败: {error_msg}")
                return
        except Exception as e:
            print(f"❌ 发生错误: {str(e)}")
            return

if __name__ == "__main__":
    main()