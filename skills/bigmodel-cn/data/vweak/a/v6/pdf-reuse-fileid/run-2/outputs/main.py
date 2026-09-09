# main.py

import os
import requests

def get_contract_info(file_id):
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    headers = {
        "Authorization": "Bearer " + os.environ["ZHIPUAI_API_KEY"]
    }

    questions = [
        "合同编号是什么",
        "合同总金额是多少",
        "违约金怎么算"
    ]

    for question in questions:
        response = requests.post(
            f "{base_url}/chat/completions",
            headers=headers,
            json={
                "model": "glm-5.3-flash",
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "file",
                            "file": {
                                "file_id": file_id
                            }
                        },
                        {
                            "type": "text",
                            "text": question
                        }
                    ]
                }
            }
        )
        print(question, response.json()["choices"][0]["message"]["content"])