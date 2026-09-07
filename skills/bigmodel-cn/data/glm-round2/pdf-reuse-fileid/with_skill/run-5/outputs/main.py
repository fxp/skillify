#!/usr/bin/env python3
"""把 contract.pdf 交给智谱 BigModel 的模型阅读，然后连问三个问题并打印答案。

核心设计（为什么这样写）：
- PDF 只上传一次：POST /paas/v4/files（multipart），purpose 必须传 "user_data"。
  chat/completions 里 file 类型只认 user_data 上传的 file_id；用 agent /
  code-interpreter 等 purpose 上传虽然能成功，但拿那个 file_id 去引用必定报
  1210「文件解析失败，请检查文件可访问性和格式」。
- 三个问题复用同一个 file_id：每轮请求 content 数组里只带
  {"type": "file", "file": {"file_id": ...}} 这个几十字节的引用，不再重传文件、
  也不 base64 内联，省带宽省 token。文件在平台侧保留 30 天，之后更多轮提问
  继续复用同一个 file_id 即可（不要每轮重新上传）。
- 本地完全不解析 PDF（无 PyPDF2/pdfplumber/pypdf 等依赖），识别全部由平台完成。
- 模型用 glm-5.3-flash：原生多模态，支持 content 里 type=file 的文件输入。
- 网络层对 429/5xx/瞬断做指数退避重试；4xx（参数/鉴权错误）重试无意义，
  直接报错退出。

依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
运行：python3 main.py
"""

import os
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api"
# 原生多模态模型，支持 content 中 type=file 输入；换模型时须确认支持文件输入
CHAT_MODEL = "glm-5.3-flash"
# 关键参数：file_id 只有以 purpose=user_data 上传，chat 接口才能正常解析
UPLOAD_PURPOSE = "user_data"
TIMEOUT = 120      # 单次请求超时（秒）
MAX_RETRIES = 4    # 瞬时错误最多尝试 4 次（1s/2s/4s 指数退避）

QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的合同总金额是多少？",
    "这份合同的违约金怎么算？",
]


def find_contract_pdf():
    """按 脚本同目录 -> 当前目录 -> 各级祖先目录(含 fixtures) 的顺序找 contract.pdf。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "contract.pdf"),
        os.path.abspath("contract.pdf"),
    ]
    d = script_dir
    for _ in range(6):
        candidates.append(os.path.join(d, "contract.pdf"))
        candidates.append(os.path.join(d, "fixtures", "contract.pdf"))
        d = os.path.dirname(d)
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("找不到 contract.pdf，已尝试: " + "; ".join(candidates))


def call_api(method, url, *, api_key, **kwargs):
    """统一请求封装：校验 HTTP 状态与业务 error 字段，仅对可重试错误做指数退避。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as e:
            last_err = f"网络异常: {e}"
            retryable = True
        else:
            try:
                data = resp.json()
            except ValueError:
                data = None
                last_err = f"HTTP {resp.status_code}: 非 JSON 响应 {resp.text[:200]}"
            else:
                err = data.get("error") if isinstance(data, dict) else None
                if resp.ok and not err:
                    return data
                last_err = f"HTTP {resp.status_code}: {data}"
            # 429（限流/过载）和 5xx 值得重试；401/400/403 等是配置问题，重试无意义
            retryable = resp.status_code >= 500 or resp.status_code == 429
        if not retryable or attempt == MAX_RETRIES:
            break
        wait = 2 ** (attempt - 1)
        print(f"请求失败（{last_err}），{wait}s 后第 {attempt + 1} 次尝试…", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"请求 {url} 失败，最后一次错误：{last_err}")


def upload_pdf(api_key, path):
    """上传 PDF 一次，返回 file_id。purpose=user_data 是 chat 接口能引用的前提。"""
    with open(path, "rb") as f:
        data = call_api(
            "POST",
            f"{BASE_URL}/paas/v4/files",
            api_key=api_key,
            files={"file": (os.path.basename(path), f, "application/pdf")},
            data={"purpose": UPLOAD_PURPOSE},
        )
    return data["id"]


def ask(api_key, file_id, question):
    """复用已有 file_id 提一个问题（不重传文件），返回模型回答文本。"""
    data = call_api(
        "POST",
        f"{BASE_URL}/paas/v4/chat/completions",
        api_key=api_key,
        json={
            "model": CHAT_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        # 只带文件引用，不带文件内容
                        {"type": "file", "file": {"file_id": file_id}},
                        {"type": "text", "text": question},
                    ],
                }
            ],
            # glm-5.3 系列在标准端点强制思考（传 disabled 会报 1210），
            # 合同字段抽取这类事实型问题用 low 档更快更省 token
            "reasoning_effort": "low",
        },
    )
    choice = data["choices"][0]
    content = (choice["message"].get("content") or "").strip()
    if not content:
        return f"(模型未返回内容，finish_reason={choice.get('finish_reason')})"
    return content


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    pdf_path = find_contract_pdf()
    print(f"PDF 路径: {pdf_path}")

    # 全程只上传这一次；后面所有轮次（含未来的提问）都复用这个 file_id
    file_id = upload_pdf(api_key, pdf_path)
    print(f"已上传，file_id = {file_id}")
    print("以下三个问题全部复用该 file_id，不再重新上传文件。\n")

    for i, question in enumerate(QUESTIONS, 1):
        print(f"问题 {i}：{question}")
        print(f"回答 {i}：{ask(api_key, file_id, question)}")
        print()


if __name__ == "__main__":
    main()
