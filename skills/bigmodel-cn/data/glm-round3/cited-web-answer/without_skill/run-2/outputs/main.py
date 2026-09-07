#!/usr/bin/env python3
"""联网问答小工具:调用智谱 BigModel 对话接口并开启联网搜索,
回答写死的问题,并在答案下方列出接口真实返回的搜索来源(标题 + 可点击 URL)。

运行方式:
    export ZHIPUAI_API_KEY="你的 API Key"
    python3 main.py

依赖:仅 requests(pip install requests)。

接口要点(见 https://docs.bigmodel.cn/api-reference/模型-api/对话补全):
- 请求端点 POST https://open.bigmodel.cn/api/paas/v4/chat/completions,
  认证方式为 Authorization: Bearer <API_KEY>。
- 在 tools 中声明 {"type": "web_search", ...} 即开启联网搜索;
  其中 search_result=True 时接口才会在响应中回传搜索来源详情,
  require_search=True 强制先搜索再回答。
- 响应中答案位于 choices[0].message.content;
  搜索来源位于响应顶层 web_search 数组,每项含
  title / link / media / publish_date / content / refer / icon 字段。
  本脚本只把该数组里的 link 原样打印,不做任何模型转述或拼接,
  保证列出的每条来源都是接口真实返回的。
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 可按需换成其它支持联网搜索的模型
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"
TIMEOUT_SECONDS = 120  # 联网搜索耗时较长,放宽超时


def build_payload(question: str) -> dict:
    return {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": question},
        ],
        "stream": False,
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",
                    # 关键:要求接口在响应中回传真实搜索来源(默认 False 不回传)
                    "search_result": True,
                    # 强制先完成联网搜索再给出回答
                    "require_search": True,
                    # 限定一年内的网页,贴合"2026 年发布"这类时效性问题
                    "search_recency_filter": "oneYear",
                },
            }
        ],
    }


def ask_with_web_search(question: str) -> dict:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误: 未设置环境变量 ZHIPUAI_API_KEY,请先执行 export ZHIPUAI_API_KEY=...")

    try:
        resp = requests.post(
            API_URL,
            json=build_payload(question),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        sys.exit(f"错误: 请求智谱接口失败: {exc}")

    if resp.status_code != 200:
        # 尽量把服务端返回的错误信息透出来,便于排查(如 key 无效、模型名不对)
        detail = resp.text[:500]
        sys.exit(f"错误: 接口返回 HTTP {resp.status_code}: {detail}")

    try:
        return resp.json()
    except ValueError:
        sys.exit(f"错误: 接口返回了非 JSON 内容: {resp.text[:500]}")


def extract_answer(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


def extract_sources(data: dict) -> list:
    """从响应中提取接口真实返回的搜索来源。

    优先取响应顶层 web_search 数组(当前文档定义的位置),
    兼容旧结构 choices[0].message.web_search。
    只保留带 link 的条目,link 原样输出、不经任何加工。
    """
    sources = data.get("web_search")
    if not sources:
        message = (data.get("choices") or [{}])[0].get("message") or {}
        sources = message.get("web_search") or []

    result = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "").strip()
        if not link:
            continue  # 没有真实链接的条目不列出,避免误导
        result.append(
            {
                "title": str(item.get("title") or "").strip() or "(无标题)",
                "link": link,
                "media": str(item.get("media") or "").strip(),
                "publish_date": str(item.get("publish_date") or "").strip(),
            }
        )
    return result


def main() -> None:
    data = ask_with_web_search(QUESTION)

    print(f"问题:{QUESTION}")
    print()

    answer = extract_answer(data)
    print(answer or "(模型未返回答案内容)")

    print()
    sources = extract_sources(data)
    print(f"—— 本次回答参考的信息来源(接口 web_search 字段真实返回,共 {len(sources)} 条)——")
    if not sources:
        print("(接口本次未返回任何搜索来源)")
        return
    for index, source in enumerate(sources, start=1):
        extra = " / ".join(part for part in (source["media"], source["publish_date"]) if part)
        suffix = f"({extra})" if extra else ""
        print(f"[{index}] {source['title']} {suffix}")
        # URL 单独成行、原样输出,便于终端/Markdown 中直接点击核对
        print(f"    {source['link']}")


if __name__ == "__main__":
    main()
