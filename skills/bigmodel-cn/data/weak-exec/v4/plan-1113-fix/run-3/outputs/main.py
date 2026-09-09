import os
import requests

# 从环境变量读取 GLM API Key
api_key = os.environ.get('GLM_KEY')
if not api_key:
    print("错误：请设置环境变量 GLM_KEY")
    exit(1)

# Coding Plan 套餐使用专门的端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 请求头
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# 请求数据
data = {
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "用一句话介绍 Python"}]
}

try:
    # 发送请求
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()  # 检查HTTP错误

    # 获取响应
    result = response.json()

    # 打印模型回答
    if 'choices' in result and len(result['choices']) > 0:
        content = result['choices'][0]['message']['content']
        print(content)
    else:
        print("错误：响应格式异常")
        print(result)

except requests.exceptions.RequestException as e:
    print(f"请求失败: {e}")
    if hasattr(e, 'response') and e.response is not None:
        try:
            error_info = e.response.json()
            print(f"错误详情: {error_info}")
        except:
            print(f"响应内容: {e.response.text}")
except Exception as e:
    print(f"发生错误: {e}")