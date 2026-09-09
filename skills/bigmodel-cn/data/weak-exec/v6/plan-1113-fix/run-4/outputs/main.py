import os, requests
import json

# 从环境变量读取GLM Coding Plan API Key
api_key = os.environ.get("GLM_KEY")
if not api_key:
    print("错误：请设置GLM_KEY环境变量")
    exit(1)

# 使用Coding Plan专用的API端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

data = {
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "用一句话介绍 Python"}]
}

try:
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    result = response.json()

    # 打印模型的回答
    if "choices" in result and len(result["choices"]) > 0:
        print(result["choices"][0]["message"]["content"])
    else:
        print("响应格式异常：", json.dumps(result, indent=2, ensure_ascii=False))

except requests.exceptions.HTTPError as e:
    print(f"HTTP错误: {e.response.status_code}")
    print(f"错误信息: {e.response.text}")
except Exception as e:
    print(f"其他错误: {str(e)}")