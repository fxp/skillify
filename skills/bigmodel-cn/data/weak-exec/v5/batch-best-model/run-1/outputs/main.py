import os
import requests
import json
import io

# API配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

def main():
    # 检查API Key是否存在
    if not API_KEY:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    # 读取comments.txt文件
    try:
        with open("/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/v2-eval/comments.txt", "r", encoding="utf-8") as f:
            comments = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("错误：找不到comments.txt文件")
        return

    print(f"读取到 {len(comments)} 条评论")

    # 构造Batch请求文件内容（JSONL格式）
    # 根据参考文件，Batch API支持的最好模型是glm-4-plus
    # 每条评论进行情感分类，输出正面/负面/中性
    requests_data = []
    for i, comment in enumerate(comments):
        custom_id = f"sentiment-{i+1:05d}"  # custom_id必须至少6个字符

        request_entry = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-4-plus",  # Batch API白名单中最好的模型
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的情感分类专家。请对用户评论进行情感分类，只返回一个结果：正面、负面或中性。分类标准：\n- 正面：表达满意、赞扬、推荐、再次购买等积极情绪\n- 负面：表达不满、抱怨、要求退款、批评等消极情绪\n- 中性：客观描述、中立评价、无明显情绪倾向\n请只返回分类结果，不要解释。"
                    },
                    {
                        "role": "user",
                        "content": f"请对以下评论进行情感分类：{comment}"
                    }
                ],
                "max_tokens": 10,  # 只需要一个词就够了
                "temperature": 0.1  # 降低随机性，确保结果一致
            }
        }
        requests_data.append(request_entry)

    print(f"已构造 {len(requests_data)} 个Batch请求")

    # 创建JSONL文件内容
    jsonl_content = "\n".join([json.dumps(req, ensure_ascii=False) for req in requests_data])

    # 上传Batch请求文件
    print("正在上传Batch请求文件...")
    try:
        files = {
            "file": ("batch_requests.jsonl", io.BytesIO(jsonl_content.encode()), "application/json")
        }
        data = {"purpose": "batch"}

        upload_response = requests.post(
            f"{BASE_URL}/files",
            headers=headers,
            files=files,
            data=data
        )
        upload_response.raise_for_status()
        file_info = upload_response.json()
        input_file_id = file_info["id"]
        print(f"文件上传成功，文件ID: {input_file_id}")
    except requests.exceptions.RequestException as e:
        print(f"文件上传失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
        return

    # 创建Batch任务
    print("正在创建Batch任务...")
    try:
        batch_request = {
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {
                "description": "评论情感分析任务",
                "total_requests": len(requests_data)
            }
        }

        batch_response = requests.post(
            f"{BASE_URL}/batches",
            headers={**headers, "Content-Type": "application/json"},
            json=batch_request
        )
        batch_response.raise_for_status()
        batch_info = batch_response.json()
        batch_id = batch_info["id"]
        print(f"Batch任务创建成功！")
        print(f"Batch任务ID: {batch_id}")
        print(f"任务状态: {batch_info['status']}")
        print(f"请使用此ID查询任务状态或获取结果")
    except requests.exceptions.RequestException as e:
        print(f"Batch任务创建失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
        return

if __name__ == "__main__":
    main()