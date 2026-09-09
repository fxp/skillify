import os, requests

r = requests.post(
    "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['GLM_KEY']}"},
    json={
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}]
    }
)
print(r.json()["choices"][0]["message"]["content"])