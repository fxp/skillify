"""
迁移说明
========
原始代码使用 OpenAI 官方 Python SDK 直连 OpenAI 的聊天补全接口：

    from openai import OpenAI
    client = OpenAI(api_key="sk-...")
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "你好"}],
    )

智谱 AI（Zhipu / BigModel）对外提供了 **OpenAI 兼容接口**，因此不需要更换 SDK，
只需要做两件事：

1. 仍然 `from openai import OpenAI`，但在实例化时改传智谱的 `base_url` 和智谱的
   `api_key`（形如 `{key_id}.{key_secret}`），并把 `model` 换成 GLM 系列模型名
   （如 `glm-4-plus` / `glm-4-flash` / `glm-4-air` 等）。
2. 要让模型具备"联网搜索最新信息"的能力，智谱在 `chat.completions.create` 的
   `tools` 参数里内置了一个特殊工具类型 `web_search`（这是智谱对 OpenAI 协议的
   扩展字段，不是标准 OpenAI 的 function-calling 工具，但因为 Python SDK 只是把
   `tools` 原样序列化成 JSON 发给服务端，所以不需要修改/破解 SDK，直接传即可）。
   模型会在推理过程中自动判断是否需要检索，并把检索结果融合进最终回答里。

因此整体代码改动非常小：换 base_url、换 api_key 来源、换 model 名、给
tools 参数加一个 web_search 工具项。业务侧调用 `chat.completions.create(...)`
的方式完全不变。
"""

import os

from openai import OpenAI

# ---------------------------------------------------------------------------
# 1. 初始化客户端：仍然用 OpenAI SDK，但指向智谱 BigModel 的 OpenAI 兼容端点
# ---------------------------------------------------------------------------
# 智谱的 API Key 建议通过环境变量注入，不要硬编码到代码里。
# 智谱控制台的 Key 格式一般是 "{id}.{secret}"，直接整体作为 api_key 使用即可。
ZHIPU_API_KEY = os.environ.get("ZHIPUAI_API_KEY", "your-api-key-here")
ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"

client = OpenAI(
    api_key=ZHIPU_API_KEY,
    base_url=ZHIPU_BASE_URL,
)

# 智谱 GLM 系列可选模型示例：
#   glm-4-plus   —— 效果最强，适合复杂任务
#   glm-4-air    —— 性价比均衡
#   glm-4-flash  —— 速度快、免费/低成本，适合高并发场景
GLM_MODEL = "glm-4-plus"

# ---------------------------------------------------------------------------
# 2. 联网搜索能力：通过 tools 参数声明智谱内置的 web_search 工具
# ---------------------------------------------------------------------------
# 说明：
#   - type 固定为 "web_search"（智谱对协议的扩展，非标准 OpenAI function tool）。
#   - search_result: True 表示希望在返回结果中附带引用/检索片段，便于溯源展示。
#   - 是否真正触发搜索由模型自行判断（例如问题涉及"最新""今天""实时行情"等），
#     不需要业务代码手动分两步调用。
WEB_SEARCH_TOOL = {
    "type": "web_search",
    "web_search": {
        "enable": True,
        "search_result": True,
    },
}


def chat_with_glm(user_message: str, enable_web_search: bool = True) -> str:
    """
    调用智谱 GLM 模型完成一次对话，可选启用联网搜索。

    与原 OpenAI 版本相比，业务侧调用方式（构造 messages、读取
    response.choices[0].message.content）完全没有变化，
    只是多传了一个 tools 参数用于开启联网搜索。
    """
    messages = [
        {
            "role": "system",
            "content": "你是一个乐于助人的助手。如果问题涉及最新信息、实时数据或"
            "需要联网核实的内容，请优先调用联网搜索工具获取准确信息后再回答。",
        },
        {"role": "user", "content": user_message},
    ]

    create_kwargs = dict(
        model=GLM_MODEL,
        messages=messages,
        temperature=0.7,
    )
    if enable_web_search:
        create_kwargs["tools"] = [WEB_SEARCH_TOOL]

    response = client.chat.completions.create(**create_kwargs)

    choice = response.choices[0]
    answer = choice.message.content or ""

    # 如果开启了联网搜索，智谱可能会在返回中附带检索到的参考资料
    # （具体字段名以官方最新文档为准，这里做了兼容性的容错读取，
    # 不影响主流程，仅用于打印引用来源方便调试/展示）。
    search_results = _extract_search_results(response)
    if search_results:
        print("\n[联网搜索引用来源]")
        for i, item in enumerate(search_results, start=1):
            title = item.get("title") or item.get("name") or "(无标题)"
            link = item.get("link") or item.get("url") or ""
            print(f"  {i}. {title} - {link}")

    return answer


def _extract_search_results(response) -> list:
    """
    尽量兼容地从响应中提取联网搜索的引用结果。
    智谱在返回中可能通过 message.tool_calls 或顶层扩展字段携带搜索结果，
    这里做了防御性解析，取不到就返回空列表，不影响主答案的输出。
    """
    try:
        message = response.choices[0].message
        # 某些版本会把搜索结果放在 tool_calls 里
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            results = []
            for call in tool_calls:
                web_search = getattr(call, "web_search", None)
                if web_search:
                    results.extend(web_search)
            if results:
                return results

        # 某些版本会把搜索结果放在响应顶层的 web_search 字段
        raw = response.model_dump() if hasattr(response, "model_dump") else {}
        if isinstance(raw, dict) and raw.get("web_search"):
            return raw["web_search"]
    except Exception:
        # 提取引用来源失败不应影响主流程
        pass
    return []


if __name__ == "__main__":
    question = "今天有什么值得关注的科技新闻？"
    answer = chat_with_glm(question, enable_web_search=True)
    print("用户问题:", question)
    print("模型回答:", answer)
