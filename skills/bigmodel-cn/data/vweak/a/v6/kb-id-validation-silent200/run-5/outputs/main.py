# main.py

import os

# 从环境变量读取知识库 ID 和 API Key
kb_id = os.environ['ZHIPU_KB_ID']
api_key = os.environ['ZHIPUAI_API_KEY']

# 配置 API 地址
base_url = 'https://open.bigmodel.cn/api/paas/v4'

# 构造 API 请求
url = f'{base_url}/knowledgebase/validate'
headers = {'Authorization': f'Bearer {api_key}'}

# 发送请求
response = requests.get(url, headers=headers)

# 打印校验结论
if response.status_code == 200:
    print(f'知识库 {kb_id} 存在且可用')
else:
    print(f'知识库 {kb_id} 无效或不可用')
