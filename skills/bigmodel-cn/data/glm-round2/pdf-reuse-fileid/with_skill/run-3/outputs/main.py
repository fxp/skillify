"""用智谱 BigModel 多模态模型阅读合同 PDF 并回答三个问题。

流程：
1. 把 contract.pdf 通过 POST /paas/v4/files 上传一次，拿到 file_id
   （purpose 必须为 user_data——chat/completions 的 file 输入只认这种
   purpose 上传的文件，传 agent/code-interpreter 等会在引用时报
   1210「文件解析失败」）。
2. 之后三个问题都只在 messages 里携带同一个 file_id 引用，
   不再重新上传或传输文件内容，省带宽也省 token。

依赖：仅 requests（+ 标准库）。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
用法：python3 main.py
"""

import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api"
MODEL = "glm-5.3-flash"  # 原生多模态模型，支持 file 类型的多模态输入
PDF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contract.pdf")
UPLOAD_TIMEOUT = 300  # 上传大文件可能较慢
CHAT_TIMEOUT = 180

QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的总金额是多少？",
    "这份合同的违约金是怎么计算的？请说明计算方式。",
]


def check_response(resp: requests.Response, what: str) -> dict:
    """非 2xx 时把平台返回的错误信息带出来，方便排查。"""
    if not resp.ok:
        raise RuntimeError(f"{what}失败：HTTP {resp.status_code} {resp.text[:500]}")
    return resp.json()


def upload_pdf(api_key: str) -> str:
    """上传 PDF 一次，返回 file_id。"""
    with open(PDF_PATH, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("contract.pdf", f, "application/pdf")},
            data={"purpose": "user_data"},
            timeout=UPLOAD_TIMEOUT,
        )
    data = check_response(resp, "上传文件")
    return data["id"]


def ask(api_key: str, file_id: str, question: str) -> tuple:
    """带着同一个 file_id 提问，返回 (回答文本, usage 字典)。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": question},
                ],
            }
        ],
        # 三个问题都是简单事实抽取；glm-5.3-flash 在标准端点强制思考，
        # low 档实测几乎不产生思考 token，进一步省 token、加快返回。
        "reasoning_effort": "low",
    }
    resp = requests.post(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=CHAT_TIMEOUT,
    )
    data = check_response(resp, "对话请求")
    choice = data["choices"][0]
    if choice.get("finish_reason") not in (None, "stop"):
        raise RuntimeError(f"模型未正常结束：finish_reason={choice.get('finish_reason')}")
    content = (choice["message"].get("content") or "").strip()
    if not content:
        raise RuntimeError(f"模型返回空内容：{data}")
    return content, data.get("usage") or {}


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")
    if not os.path.isfile(PDF_PATH):
        sys.exit(f"错误：找不到合同文件 {PDF_PATH}")

    file_id = upload_pdf(api_key)
    print(f"已上传 contract.pdf，file_id = {file_id}")
    print(f"以下 {len(QUESTIONS)} 个问题均复用该 file_id，不再重复上传文件。\n")

    for i, question in enumerate(QUESTIONS, 1):
        print(f"问题 {i}：{question}")
        answer, usage = ask(api_key, file_id, question)
        print(f"回答 {i}：{answer}")
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        print(
            f"（tokens：prompt={usage.get('prompt_tokens', '?')}，"
            f"其中缓存命中={cached}，completion={usage.get('completion_tokens', '?')}）"
        )
        print()


if __name__ == "__main__":
    main()
