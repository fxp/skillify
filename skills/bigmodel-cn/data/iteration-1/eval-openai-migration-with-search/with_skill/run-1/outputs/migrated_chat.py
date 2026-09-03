"""
聊天功能：从 OpenAI 迁移到智谱 GLM（bigmodel.cn），并加上联网搜索能力。

=== 迁移前（假设的原始代码）大致长这样 ===

    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": user_question}],
    )
    print(resp.choices[0].message.content)

=== 迁移到智谱的思路（"尽量少改代码"） ===

智谱开放平台（bigmodel.cn）提供与 OpenAI SDK 完全兼容的接口层：继续用
`from openai import OpenAI`，只需要改两个构造参数——`api_key` 换成智谱
的 Key，`base_url` 指向智谱的兼容端点——以及把 `model` 换成智谱的模型
代码。业务代码里 `client.chat.completions.create(...)` 的调用方式、
返回结构（`resp.choices[0].message.content`）完全不变。

联网搜索能力也不需要跳出 OpenAI SDK 自己搭一套框架：智谱在
`chat.completions.create()` 的标准 `tools` 参数里原生支持一个
`type: "web_search"` 的工具项（这是官方文档里"三层联网检索能力"中的
第二层：直接嵌在 chat/completions 里，由平台自动判断搜索意图、执行搜索
并把结果糅合进模型回答，不需要像 function calling 那样自己写"模型要
参数 -> 我方执行 -> 把结果传回模型"的多轮循环）。命中搜索后，响应体
顶层还会带一个 `web_search` 数组，列出被引用的网页（标题/链接/摘要等），
可以用来在回答后面展示信息来源。

参考：bigmodel-cn skill 的 references/sdk-and-compat.md（OpenAI SDK 兼容层）
      与 references/tools.md / references/chat.md（web_search 工具）。
"""

import os

from openai import OpenAI

# --------------------------------------------------------------------------
# 1. 客户端初始化 —— 这是从 OpenAI 迁移过来时唯一需要改的"结构性"代码
# --------------------------------------------------------------------------
# 原来: OpenAI(api_key=os.environ["OPENAI_API_KEY"])
# 现在: base_url 指向智谱的 OpenAI 兼容端点，api_key 换成智谱的 API Key。
#
# API Key 请在智谱开放平台控制台申请：
#   https://bigmodel.cn/usercenter/proj-mgmt/apikeys
# 强烈建议通过环境变量注入，不要把 Key 硬编码进代码里。
client = OpenAI(
    api_key=os.environ.get("ZHIPU_API_KEY", "your-zhipu-api-key-here"),
    base_url="https://open.bigmodel.cn/api/paas/v4/",
)

# 智谱的模型代码和 OpenAI 的不是一回事，需要显式换成智谱的模型名。
# glm-5.3 是智谱当前的旗舰对话模型（对应旧代码里可能用的 gpt-4o / gpt-4 之类）。
MODEL_NAME = "glm-5.3"


# --------------------------------------------------------------------------
# 2. 联网搜索工具定义
# --------------------------------------------------------------------------
# 加进 tools 数组里的 web_search 工具项。字段来自官方文档对 chat/completions
# 里 web_search 工具类型的说明（与独立的 POST /paas/v4/web_search 接口共享
# 同一套搜索参数，如 search_engine / search_recency_filter / count 等）。
#
# 不需要手写 function-calling 的"模型返回调用请求 -> 你执行 -> 回传结果"
# 循环：web_search 是平台侧直接执行的工具，命中后结果会被直接注入模型的
# 回答里，同时在响应顶层附带 web_search 引用列表。
WEB_SEARCH_TOOL = {
    "type": "web_search",
    "web_search": {
        "enable": True,
        # 四个可选搜索引擎：search_std（基础版，性价比高）/ search_pro（高阶，
        # 召回率更高，适合大多数场景）/ search_pro_sogou（搜狗，适合社交/百科/
        # 医疗类垂直内容）/ search_pro_quark（夸克，适合垂直内容精准检索）。
        "search_engine": "search_pro",
        # 优先返回近期内容，避免模型引用过期信息；如果不需要限定时间范围，
        # 可以去掉这一项（默认 noLimit）。
        "search_recency_filter": "oneYear",
        # medium=摘要（默认，满足常规问答）；high=更详细的网页内容，
        # 适合需要深入分析的问题，但会消耗更多 token。
        "content_size": "medium",
    },
}


def ask(user_question: str, *, use_web_search: bool = True) -> str:
    """
    向智谱 GLM 提问，默认开启联网搜索，让模型在回答前先查最新信息。

    与迁移前的调用方式几乎一样：还是一次 client.chat.completions.create()
    调用，只是多传了一个 tools 参数。tool_choice 不需要显式设置——
    web_search 是平台自动判断是否需要搜索并执行的工具，不是需要你强制
    指定的 function。
    """
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个严谨的助手。如果问题涉及时效性信息（新闻、价格、"
                "版本号、政策等），请优先使用搜索到的最新结果作答，并在"
                "回答中体现信息的时效性。"
            ),
        },
        {"role": "user", "content": user_question},
    ]

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        tools=[WEB_SEARCH_TOOL] if use_web_search else None,
    )

    choice = response.choices[0]
    answer = choice.message.content or ""

    # 命中搜索时，响应顶层会带一个 web_search 数组（引用来源列表）。
    # 这是 OpenAI 的 ChatCompletion 响应结构里本来没有的智谱扩展字段，
    # 官方 openai SDK 对未知的顶层字段一般会保留在 model_extra 里，
    # 这里做了防御性读取，读不到就不展示来源（不影响主回答）。
    sources = getattr(response, "web_search", None)
    if sources is None:
        model_extra = getattr(response, "model_extra", None) or {}
        sources = model_extra.get("web_search")

    if sources:
        lines = [answer, "", "参考来源："]
        for item in sources:
            title = item.get("title") if isinstance(item, dict) else getattr(item, "title", None)
            link = item.get("link") if isinstance(item, dict) else getattr(item, "link", None)
            if title or link:
                lines.append(f"- {title or '(无标题)'} {link or ''}".strip())
        answer = "\n".join(lines)

    return answer


if __name__ == "__main__":
    question = "最近有什么值得关注的 AI 大模型新发布？请简要总结。"
    print(ask(question))
