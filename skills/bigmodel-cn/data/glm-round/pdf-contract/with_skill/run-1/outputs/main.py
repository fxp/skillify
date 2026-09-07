#!/usr/bin/env python3
"""把合同 PDF 扫描件交给智谱 BigModel 的多模态模型读取，抽取「合同编号」与「合同总金额」。

本地不做任何 PDF 解析（不用 PyPDF2 / pdfplumber / pypdf 抠文字）：
整个 PDF 以 base64 data URI 内联进 chat/completions 的多模态 file 输入
（单文件 ≤50M，见 https://docs.bigmodel.cn 的对话补全 API），由模型自己读文件。

运行方式：
    ZHIPUAI_API_KEY=你的Key python3 main.py [contract.pdf 的路径]
"""

import base64
import json
import os
import sys
from pathlib import Path

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3-flash"  # 原生多模态旗舰，支持 file 类型输入
MAX_FILE_BYTES = 50 * 1024 * 1024  # 平台限制：file 类型单文件 ≤50M


def find_pdf() -> Path:
    """按 传入参数 → 脚本所在目录 → 当前目录 → 脚本上级目录 的顺序找 contract.pdf。"""
    here = Path(__file__).resolve().parent
    candidates = []
    if len(sys.argv) > 1:
        candidates.append(Path(sys.argv[1]))
    candidates += [
        here / "contract.pdf",
        Path.cwd() / "contract.pdf",
        here.parent / "contract.pdf",
    ]
    for path in candidates:
        if path.is_file():
            return path
    searched = "\n  ".join(str(p) for p in candidates)
    sys.exit(
        "找不到 contract.pdf，搜索过以下位置：\n"
        f"  {searched}\n"
        "也可以显式指定路径：python3 main.py /path/to/contract.pdf"
    )


def parse_model_json(content: str) -> dict:
    """从模型输出中解析 JSON。

    视觉模型不支持 response_format=json_object（该参数仅纯文本模型支持），
    只能靠 prompt 约束 + 客户端兜底：容忍代码块围栏或夹带的解释文字。
    """
    text = content.strip()
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            result = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            return result
    sys.exit(f"无法从模型输出解析出 JSON，原始输出：\n{content}")


def extract_contract_fields(pdf_path: Path) -> dict:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit(
            "请先设置环境变量 ZHIPUAI_API_KEY"
            "（Key 从 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取）"
        )

    raw = pdf_path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        sys.exit(f"文件过大：{len(raw)} 字节，超过 file 类型单文件 50M 限制")
    file_data = "data:application/pdf;base64," + base64.b64encode(raw).decode("ascii")

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {"file_data": file_data, "filename": pdf_path.name},
                    },
                    {
                        "type": "text",
                        "text": (
                            "这是一份合同扫描件（PDF）。请仔细阅读全文，抽取「合同编号」和「合同总金额」，"
                            '只输出一个 JSON 对象，格式为 {"合同编号": "...", "合同总金额": "..."}，'
                            "不要输出任何解释文字，也不要用 Markdown 代码块包裹。"
                            "字段值照抄合同原文：编号保留原文写法；金额保留原文的数字、币种与大写金额（如有）。"
                            "某项信息确实不存在时，对应字段填 null。"
                        ),
                    },
                ],
            }
        ],
        # glm-5.3-flash 在标准端点强制开启思考（传 disabled 会报 1210），
        # 两字段抽取属于轻量任务，用 low 档即可，快且省 token。
        "reasoning_effort": "low",
        "max_tokens": 4096,
    }

    print(f"正在把 {pdf_path.name}（{len(raw)} 字节）交给 {MODEL} 读取…", file=sys.stderr)
    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=(10, 300),
    )
    if not resp.ok:
        sys.exit(f"API 请求失败 HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        data = resp.json()
    except ValueError:
        sys.exit(f"API 返回了非 JSON 内容（HTTP {resp.status_code}）: {resp.text[:500]}")
    if data.get("error"):
        sys.exit(f"API 业务错误: {data['error']}")

    choice = (data.get("choices") or [{}])[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason not in (None, "stop"):
        sys.exit(f"模型未正常结束（finish_reason={finish_reason}）: {data}")
    content = (choice.get("message") or {}).get("content") or ""
    return parse_model_json(content)


def main() -> None:
    pdf_path = find_pdf()
    result = extract_contract_fields(pdf_path)
    print(f"合同编号：{result.get('合同编号') if result.get('合同编号') is not None else '未找到'}")
    print(f"合同总金额：{result.get('合同总金额') if result.get('合同总金额') is not None else '未找到'}")


if __name__ == "__main__":
    main()
