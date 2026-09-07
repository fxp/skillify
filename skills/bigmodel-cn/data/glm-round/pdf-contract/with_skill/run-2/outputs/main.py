#!/usr/bin/env python3
"""用智谱 BigModel 的多模态模型读取 contract.pdf，抽取合同编号与合同总金额。

设计要点：
- 完全不做本地 PDF 解析（不依赖 PyPDF2 / pdfplumber / pypdf 等），
  PDF 以二进制原样上传到智谱文件接口，再由模型自己阅读文件内容。
- file_id 必须用 purpose=user_data 上传，chat/completions 的 file 类型
  只认这种用途的文件 ID（agent / code-interpreter 等用途会报 1210 解析失败）。
- 模型选 glm-5.3-flash：原生多模态旗舰，官方文档的"文件理解"示例即用它读 PDF。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import json
import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api"
CHAT_MODEL = "glm-5.3-flash"  # 多模态模型，支持 file 类型输入
TIMEOUT = (30, 300)  # (连接超时, 读取超时)——上传与模型读 PDF 都可能较慢

PROMPT = (
    "请阅读附件中的合同文件（扫描件转写稿），从中抽取两个字段，"
    "严格只返回一个 JSON 对象，不要输出任何解释、markdown 代码块或其他文字：\n"
    '{"contract_number": "<合同编号，按原文照抄；找不到填 null>", '
    '"total_amount": "<合同总金额，保留币种、大小写与数字形式，按原文照抄；找不到填 null>"}'
)


def die(msg: str) -> None:
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(1)


def check_response(resp: requests.Response, action: str) -> dict:
    """统一处理 HTTP 失败与业务错误（响应体里的 error.code / error.message）。"""
    try:
        data = resp.json()
    except ValueError:
        die(f"{action}失败: HTTP {resp.status_code}，响应不是 JSON: {resp.text[:300]}")
    err = data.get("error") if isinstance(data, dict) else None
    if err:
        die(f"{action}失败: [{err.get('code')}] {err.get('message')}")
    if not resp.ok:
        die(f"{action}失败: HTTP {resp.status_code}: {resp.text[:300]}")
    return data


def find_contract_pdf() -> str:
    """按候选顺序定位 contract.pdf：当前目录、脚本目录，并逐级向上（含 fixtures/）。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    for root in (os.getcwd(), script_dir):
        for depth in range(6):
            base = os.path.abspath(os.path.join(root, *[".."] * depth))
            candidates.append(os.path.join(base, "contract.pdf"))
            candidates.append(os.path.join(base, "fixtures", "contract.pdf"))
    for path in dict.fromkeys(candidates):  # 去重且保持顺序
        if os.path.isfile(path):
            return path
    die("找不到 contract.pdf。已尝试: " + "、".join(dict.fromkeys(candidates)))


def upload_pdf(headers: dict) -> str:
    """上传 PDF 到文件接口，返回 file_id。注意 purpose 必须是 user_data。"""
    pdf_path = find_contract_pdf()
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=headers,
            files={"file": ("contract.pdf", f, "application/pdf")},
            data={"purpose": "user_data"},
            timeout=TIMEOUT,
        )
    data = check_response(resp, f"上传 PDF（{pdf_path}）")
    file_id = data.get("id")
    if not file_id:
        die(f"上传 PDF 成功但未返回文件 id: {json.dumps(data, ensure_ascii=False)[:300]}")
    return file_id


def extract_fields(headers: dict, file_id: str) -> str:
    """把 file_id 作为多模态消息交给模型，返回模型回复文本。"""
    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "file", "file": {"file_id": file_id}},
                ],
            }
        ],
        # 简单抽取任务，用最低推理强度换速度（glm-5.3-flash 仅接受 low/high/max）
        "reasoning_effort": "low",
        "max_tokens": 1024,
    }
    resp = requests.post(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
        timeout=TIMEOUT,
    )
    data = check_response(resp, "调用模型")
    choices = data.get("choices") or []
    if not choices:
        die(f"模型未返回 choices: {json.dumps(data, ensure_ascii=False)[:300]}")
    choice = choices[0]
    content = (choice.get("message") or {}).get("content")
    if not content:
        die(f"模型未返回内容（finish_reason={choice.get('finish_reason')}）")
    return content


def parse_fields(content: str) -> dict:
    """从模型回复中解析 JSON；对代码围栏、思考标签等常见包裹做兜底。"""
    text = content.strip()
    if "<think>" in text and "</think>" in text:  # 个别视觉模型会把思考混在 content 里
        text = text.split("</think>", 1)[1].strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:  # 剥掉可能夹带的解释文字 / ```json 围栏
        text = text[start : end + 1]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        die(f"模型回复不是合法 JSON: {content[:300]}")
    if not isinstance(obj, dict):
        die(f"模型返回的 JSON 不是对象: {content[:300]}")

    def pick(*keys):
        for k in keys:
            if obj.get(k) is not None:
                return obj[k]
        return None

    return {
        "contract_number": pick("contract_number", "合同编号", "contract_no"),
        "total_amount": pick("total_amount", "合同总金额", "total"),
    }


def delete_file(headers: dict, file_id: str) -> None:
    """用完即删，避免文件在平台上堆积（清理失败不影响主流程）。"""
    try:
        requests.delete(f"{BASE_URL}/paas/v4/files/{file_id}", headers=headers, timeout=TIMEOUT)
    except requests.RequestException:
        pass


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("环境变量 ZHIPUAI_API_KEY 未设置，请先: export ZHIPUAI_API_KEY=你的Key")
    headers = {"Authorization": f"Bearer {api_key}"}

    file_id = upload_pdf(headers)
    try:
        content = extract_fields(headers, file_id)
    finally:
        delete_file(headers, file_id)

    fields = parse_fields(content)
    print(f"合同编号: {fields['contract_number'] if fields['contract_number'] is not None else '未找到'}")
    print(f"合同总金额: {fields['total_amount'] if fields['total_amount'] is not None else '未找到'}")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:
        die(f"网络请求失败: {e}")
