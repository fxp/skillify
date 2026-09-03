> 内容整理自 platform.kimi.com/docs（抓取于 2026-09-03），**尚未用真实 API 调用验证**；实际报错优先信任 API。所有报错原文均引自文档页面，非实测观察。

# 工具调用（tools / tool_calls / tool_choice / 内置与官方工具）

来源页：guide/use-kimi-api-to-complete-tool-calls、guide/use-tool-choice、guide/use-dynamic-tool-loading、guide/use-web-search、guide/use-official-tools、guide/kimi-k3-tool-calling-best-practice、guide/tool-call-repeat，以及 openapi.json 的 Chat 段。

## 目录

1. [先看：和 OpenAI 不一样的地方](#1-先看和-openai-不一样的地方)
2. [我想让模型调用我自己的函数（基础循环）](#2-我想让模型调用我自己的函数基础循环)
3. [我想在流式输出里处理 tool_calls](#3-我想在流式输出里处理-tool_calls)
4. [我想强制 / 禁止 / 指定工具：tool_choice](#4-我想强制--禁止--指定工具tool_choice)
5. [我想联网搜索：三种方式对比](#5-我想联网搜索三种方式对比)
6. [我想用官方工具（Formula）](#6-我想用官方工具formula)
7. [我有几十上百个工具：动态加载 + tool search](#7-我有几十上百个工具动态加载--tool-search)
8. [模型反复调用同一个工具怎么办](#8-模型反复调用同一个工具怎么办)
9. [错误速查](#9-错误速查)
10. [⚠ 汇总](#10--汇总)

---

## 1. 先看：和 OpenAI 不一样的地方

| 项目 | Kimi 的行为 | 直觉会怎么写错 |
|---|---|---|
| `tool_choice: "required"` | 仅 `kimi-k3` 支持；`kimi-k2.6` / `kimi-k2.7-code` 传入报错 | 在 K2.x 上照 OpenAI 写 `required` |
| `tool_choice: {"type":"function","function":{"name":...}}` | 文档支持该写法，但 **"思考开启时传入会返回 400 错误（`tool_choice 'specified' is incompatible with thinking enabled`）"**。K3 与 K2.7-code 思考不可关，因此这种写法按文档推断只在 `kimi-k2.6` + `thinking: disabled` 下可用（⚠ 文档未直接说明 K3 的情况，为推断） | 在 K3 上指定单个函数 |
| 回传 assistant 消息 | 必须把返回的 `choice.message` **原样**追加进 `messages`，思考模型要含 `reasoning_content`；否则报 `tool_call_id not found` 或丢推理链 | 手工构造 `{"role":"assistant","tool_calls":[...]}` 只挑字段 |
| `role=tool` 消息 | 必须带 `tool_call_id`；文档示例同时带 `name`；`content` 用字符串（`json.dumps`）；**每个 tool_call 都要有对应 tool 消息**，缺一条模型会拒绝请求 | 只回传部分结果 |
| 内置联网搜索 | `{"type": "builtin_function", "function": {"name": "$web_search"}}`；收到调用后把 `arguments` 原样回传 | 写 `web_search` / `web_search_preview`，或自己去搜 |
| 动态加载工具 | `messages` 里插一条 `{"role":"system","tools":[...]}`（不能带 `content`）；**仅 `kimi-k3` 支持**，其他模型报 `tokenization failed` | 以为所有模型都行 |
| `tools` 声明 | **每次请求都要完整带上**，服务端不记住 | 只在第一轮传 |
| 采样参数 | 不要传 `temperature` 等（见 models-and-thinking.md） | 加 `temperature=0` 求稳定 |
| K3 前提 | 账户需累计充值 ≥ ¥10（新人 15 元代金券不能用于 K3） | 用新账号直接调 K3 |

---

## 2. 我想让模型调用我自己的函数（基础循环）

**Endpoint**: `POST /v1/chat/completions`
**用途**: 声明 `tools`，模型返回 `finish_reason == "tool_calls"` 和 `message.tool_calls[]`，由你的程序执行后以 `role=tool` 回传，循环直到 `finish_reason == "stop"`。模型不会替你执行工具。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `tools` | array | 否 | — | 每项 `{"type": "function", "function": {"name", "description", "parameters"}}`；`parameters` 为 JSON Schema。`name` 中不允许出现 `$`（`$` 前缀保留给内置工具）。`tools` 内容计入 prompt tokens |
| `tools[].function.name` | string | 是 | — | 须匹配 `^[a-zA-Z_][a-zA-Z0-9-_]{0,127}$`；同一请求内不能重复，否则 400 `invalid_request_error`（`function name xxx is duplicated`） |
| `tools[].function.parameters` | object | 是 | — | JSON Schema，顶层固定 `"type": "object"`；须符合 MFJS（Moonshot Flavored JSON Schema）规范 |
| `tools[].function.strict` | boolean | 否 | `true` | `true` 严格按 schema 约束 `arguments` 结构；`false` 只保证是合法 JSON 对象 |
| `tool_choice` | string \| object | 否 | `"auto"` | `"auto"` / `"none"` / `"required"`（仅 K3）/ 函数对象（见 §4） |
| `messages[].tool_calls` | array | — | — | assistant 消息里由模型生成；回传时必须完整保留 |
| `messages[]`（role=tool） | object | — | — | `{"role":"tool","tool_call_id": <tool_call.id>, "name": <function.name>, "content": <str>}` |

**响应里的关键字段**

```json
{
  "choices": [{
    "finish_reason": "tool_calls",
    "message": {
      "role": "assistant",
      "content": "",
      "reasoning_content": "...",          // 思考模型会有；回传时保留
      "tool_calls": [{
        "id": "call_xxx",
        "type": "function",
        "function": {"name": "get_weather", "arguments": "{\"city\": \"北京\"}"}
      }]
    }
  }]
}
```

`function.arguments` 是 **JSON 字符串**，要 `json.loads`。`finish_reason` 枚举：`stop` / `length` / `tool_calls`；为 `tool_calls` 时 `content` 通常为空，偶尔是模型对"为什么调用"的解释，可按需展示。`tool_calls[].id` 在文档示例里出现过 `call_xxx`、`search:0`、`web_search:0` 几种形态，⚠ 文档未说明格式约定，只透传不解析。

**示例请求（curl，单轮，看模型怎么产出 tool_calls）**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [{"role": "user", "content": "今天北京的天气怎么样？"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "查询指定城市的实时天气",
        "parameters": {
          "type": "object",
          "properties": {"city": {"type": "string", "description": "城市名称"}},
          "required": ["city"]
        }
      }
    }]
  }'
```

**示例（Python，完整循环，非流式）**

```python
import json
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询指定城市的实时天气",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名称"}},
            "required": ["city"],
        },
    },
}]

def get_weather(city: str) -> dict:
    return {"city": city, "weather": "晴", "temperature_c": 26}   # 换成真实实现

TOOL_MAP = {"get_weather": get_weather}

def run(user_input: str) -> str:
    messages = [
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": user_input},
    ]
    finish_reason = None
    while finish_reason is None or finish_reason == "tool_calls":
        completion = client.chat.completions.create(
            model="kimi-k3",
            messages=messages,
            tools=TOOLS,                 # 每次请求都完整带上
            # 不传 temperature / top_p：Kimi 各模型固定
        )
        choice = completion.choices[0]
        finish_reason = choice.finish_reason
        if finish_reason == "tool_calls":
            # 原样回传：SDK 对象里已包含 reasoning_content（思考模型）与 tool_calls
            messages.append(choice.message)
            for tc in choice.message.tool_calls:
                fn = TOOL_MAP.get(tc.function.name)
                args = json.loads(tc.function.arguments)
                result = fn(**args) if fn else f"Error: unable to find tool '{tc.function.name}'"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": json.dumps(result, ensure_ascii=False),
                })
    return choice.message.content

print(run("今天北京的天气怎么样？"))
```

如果你自己维护 dict 而不是直接 append SDK 对象，用 `choice.message.model_dump(exclude_none=True)`，别手工挑 `role/content/tool_calls` 三个字段——会丢 `reasoning_content`。

**注意事项**

- 一次可能返回多个 `tool_calls`（并行调用）。**必须对每一个都回传一条 `role=tool`**，顺序不敏感，但 `tool_call_id` 要与 `tool_calls[].id` 一一对应；少回传模型会"认为请求不合法而拒绝请求"。
- 报 `tool_call_id not found`：几乎都是没把返回的 assistant 消息（含 `tool_calls`）先 append 进 `messages`。
- `tools` + `messages` 的 token 总和不能超过模型上下文窗口。
- 文档把 `role=tool` 消息的 `name` 字段写在示例里，OpenAPI 摘要中 tool 消息是否要求 `name` ⚠ 文档未说明；照示例带上最稳妥。
- ⚠ 文档自相矛盾：guide/use-official-tools 的示例回传 assistant 消息时只保留 `role/content/tool_calls` 三个字段（丢掉 `reasoning_content`），而 guide/use-thinking-models 明确要求 K3 / K2.7-code 必须原样回传含 `reasoning_content`。以思考模型页为准，等真实调用判定是否报错或静默降质。

### 思考模型下的工具循环：`reasoning_content` 回传规则

| 模型 | 当前工具循环内（一次 tool_calls 往返的多步） | 跨对话轮次 |
|---|---|---|
| `kimi-k3` | 必须回传（Preserved Thinking 始终开启） | 必须回传 |
| `kimi-k2.7-code` / `-highspeed` | 必须回传 | 必须回传（`thinking.keep` 恒 `"all"`） |
| `kimi-k2.6` 思考开启 | 必须回传 | `thinking.keep=null`（默认）服务端忽略；`"all"` 需回传 |

- 回传时 `role=assistant` 消息直接带 `reasoning_content` 字段（指南以 curl 示范；OpenAPI 请求 schema 未列出该字段）。K2.x 的 `thinking` 参数在 OpenAI SDK 里走 `extra_body={"thinking": {...}}`。
- 思考模型工具循环建议 `max_tokens >= 16000`，避免 `reasoning_content` + `content` 截断。⚠ 文档自相矛盾：OpenAPI 把 `max_tokens` 标为"已弃用，请使用 `max_completion_tokens`"，而思考模型 / 联网搜索指南示例仍用 `max_tokens`；新代码优先 `max_completion_tokens`。
- `reasoning_content` 计入 token（输入输出都算）。

---

## 3. 我想在流式输出里处理 tool_calls

**Endpoint**: `POST /v1/chat/completions`，`stream: true`
**用途**: 边流式打印文本边拼接工具调用参数。

文档给出的规则：

1. `finish_reason` 只在最后一个数据块出现，**用 `delta.tool_calls` 是否存在判断本轮是否为工具调用**，不要等 `finish_reason`。
2. 下发顺序：`delta.reasoning_content`（思考模型）→ `delta.content` → `delta.tool_calls`；必须等 content 输出完才能识别 tool_calls。
3. 第一个数据块里给出 `tool_call.id`、`type` 和 `function.name`，后续数据块只增量输出 `function.arguments` 片段，**追加拼接、不能覆盖**，流结束后再 `json.loads`。
4. 一次返回多个 `tool_calls` 时，每个 delta 里的 tool_call 带 `index` 字段标识是第几个，按 `index` 归并。
5. 以 `data: [DONE]` 作为流结束的唯一判据；收到 `finish_reason` 但没收到 `[DONE]` 仍视为不完整。

**示例（Python，拼接逻辑）**

```python
import json
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

def stream_once(messages, tools):
    """返回 (assistant_message_dict, finish_reason)。assistant_message_dict 可直接 append 回 messages。"""
    msg = {"role": "assistant", "content": "", "tool_calls": []}
    reasoning = ""
    finish_reason = None
    stream = client.chat.completions.create(
        model="kimi-k3", messages=messages, tools=tools, stream=True,
        stream_options={"include_usage": True},
    )
    for chunk in stream:
        if not chunk.choices:
            continue                      # 最后的 usage 块没有 choices
        choice = chunk.choices[0]
        delta = choice.delta
        if choice.finish_reason:
            finish_reason = choice.finish_reason
        rc = getattr(delta, "reasoning_content", None)
        if rc:
            reasoning += rc
        if delta.content:
            msg["content"] += delta.content
            print(delta.content, end="", flush=True)
        if delta.tool_calls:
            for tc in delta.tool_calls:
                i = tc.index
                while len(msg["tool_calls"]) <= i:
                    msg["tool_calls"].append({"id": "", "type": "function",
                                              "function": {"name": "", "arguments": ""}})
                slot = msg["tool_calls"][i]
                if tc.id:
                    slot["id"] = tc.id
                if tc.type:
                    slot["type"] = tc.type          # $web_search 会是 builtin_function
                if tc.function and tc.function.name:
                    slot["function"]["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["function"]["arguments"] += tc.function.arguments
    if reasoning:
        msg["reasoning_content"] = reasoning   # 思考模型：回传时必须保留
    if not msg["tool_calls"]:
        del msg["tool_calls"]
    return msg, finish_reason
```

之后的循环与 §2 相同：`messages.append(msg)`，对每个 `msg["tool_calls"]` 执行并回传 `role=tool`。

**注意事项**

- `stream_options.include_usage` 才有最后的 usage 块；该块 `choices` 为空，遍历时要跳过。
- 用 `delta.tool_calls` 非空作为"本轮是工具调用"的信号，文档明确建议这样做。
- 流式下 `tool_call.type` 与声明一致（`function` / `builtin_function`）。⚠ 文档自相矛盾：OpenAPI 响应 schema 里 `tool_calls[].type` 枚举只有 `function`，流式指南却说会返回 `builtin_function`；按声明类型处理。
- ⚠ 文档自相矛盾：tool_calls 指南的流式示例把 `messages` 初始化为 `[{}, {}]` 并注释"设置了 n=2"，但请求里没传 `n`，且 models-overview 写明 `n` 固定为 1；只处理 `choices[0]` 即可。

---

## 4. 我想强制 / 禁止 / 指定工具：tool_choice

**Endpoint**: `POST /v1/chat/completions` 的 `tool_choice` 字段
**用途**: 请求级参数，只约束本次生成；**不影响前缀缓存**，可按请求粒度切换。

| 取值 | 含义 | 支持模型（按文档） |
|---|---|---|
| 不传 / `"auto"` | 模型自行决定 | 全部 |
| `"none"` | 不产生任何 `tool_calls`，直接文本回复，省 token | 全部 |
| `"required"` | 本轮至少调用一个工具（须已声明 `tools`）；典型用法：首轮强制 `search_tools`，之后恢复 `auto` | **仅 `kimi-k3`**；K2.6 / K2.7-code 传入报错 |
| `{"type": "function", "function": {"name": "get_weather"}}` | 强制调用指定工具 | 文档原文："思考开启时传入会返回 400 错误（`tool_choice 'specified' is incompatible with thinking enabled`）"。K3 和 K2.7-code 思考不可关 → 推断只有 `kimi-k2.6` + `thinking: {"type":"disabled"}` 可用。⚠ 文档自相矛盾：models-overview 说 K2.x 只是"不支持 required"，K2.6 quickstart 却说 K2.6 的 `tool_choice` "只能使用 auto 和 none，取任何其他值将会报错"（该页语境是思考开启） |

**示例（curl，K3 强制首轮检索）**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{"model": "kimi-k3", "tool_choice": "required",
       "messages": [{"role": "user", "content": "今天北京的天气怎么样？"}],
       "tools": [{"type": "function", "function": {"name": "get_weather", "description": "查询指定城市的实时天气",
         "parameters": {"type": "object", "properties": {"city": {"type": "string", "description": "城市名称"}}, "required": ["city"]}}}]}'
```

**示例（Python）**

```python
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[{"role": "user", "content": "今天北京的天气怎么样？"}],
    tools=TOOLS,
    tool_choice="required",      # 首轮强制；下一轮改回 "auto"
)
print(completion.choices[0].message.tool_calls)
```

**注意事项**

- 用 `required` 前确认请求里声明了 `tools`。`none` 时 `tools` 仍占 prompt tokens，只是不会被调用。
- ⚠ 文档自相矛盾：openapi.json 对 `kimi-k2.6` / `kimi-k2.7-code` 的请求 schema 也把 `required` 列在 `tool_choice` 枚举里，而 models-overview 明确说这两个模型不支持、传入报错；以 models-overview（和实际报错）为准。
- 想"指定单个工具"又要用 K3：文档没有给可行写法。替代做法是 `required` + `tools` 里只放那一个工具（⚠ 未验证是否等价）。

---

## 5. 我想联网搜索：三种方式对比

| 方式 | 声明 | 谁执行搜索 | 计费 | 适用模型 |
|---|---|---|---|---|
| A. 内置 `$web_search`（推荐） | `{"type": "builtin_function", "function": {"name": "$web_search"}}` | Kimi 平台；你只需把 `arguments` 原样回传 | 搜索结果计入 `prompt_tokens`，另外每次搜索收一次调用费（见 pricing/tools） | 文档示例 `kimi-k3`；`kimi-k2.6` 思考开启也可用 |
| B. 官方工具 Formula `moonshot/web-search:latest` | `GET /v1/formulas/{uri}/tools` 取声明，再走普通 function 流程 | 你调用 `POST /v1/formulas/{uri}/fibers` 执行（此步计费） | tool_call 计费 + tokens | 示例 `kimi-k3` |
| C. 自己实现 `search` / `crawl` 函数 | 普通 `function` | 你 | 只有 tokens | 全部 |

### 5A. 内置 `$web_search`

**Endpoint**: `POST /v1/chat/completions`
**用途**: 不想接搜索引擎、抓网页、清洗内容时用。`$` 前缀是 Kimi 内置函数约定（普通 function 名里禁止 `$`）。可与普通 `function` 在同一 `tools` 里混用。

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `tools[]` | object | 是 | — | `{"type": "builtin_function", "function": {"name": "$web_search"}}`，不需要 `description` / `parameters` |

**示例（curl）**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{"model": "kimi-k3",
       "messages": [{"role": "user", "content": "请搜索 Moonshot AI Context Caching 技术，并告诉我它是什么。"}],
       "tools": [{"type": "builtin_function", "function": {"name": "$web_search"}}]}'
```

返回的 `tool_calls[].type` 为 `builtin_function`，`function.arguments` 里带 `usage.total_tokens`（本次搜索结果将占用的 tokens，随后计入 `prompt_tokens`；文档示例：13046 → 最终轮 `prompt_tokens` 13212）。

**示例（Python）**

```python
import json
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")
TOOLS = [{"type": "builtin_function", "function": {"name": "$web_search"}}]

def search_impl(arguments: dict):
    # 使用 Kimi 内置 $web_search 时，原封不动返回 arguments 即可；搜索由平台执行。
    # 想换成自己的搜索服务时只改这个函数，其余循环不变。
    return arguments

def ask(question: str) -> str:
    messages = [{"role": "system", "content": "你是 Kimi。"},
                {"role": "user", "content": question}]
    finish_reason = None
    while finish_reason is None or finish_reason == "tool_calls":
        completion = client.chat.completions.create(model="kimi-k3", messages=messages, tools=TOOLS)
        choice = completion.choices[0]
        finish_reason = choice.finish_reason
        if finish_reason == "tool_calls":
            messages.append(choice.message)
            for tc in choice.message.tool_calls:
                args = json.loads(tc.function.arguments)
                if tc.function.name == "$web_search":
                    # 文档示例：args 里可能带 usage.total_tokens，表示搜索结果占用的 token
                    result = search_impl(args)
                else:
                    result = f"Error: unable to find tool by name '{tc.function.name}'"
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "name": tc.function.name,
                                 "content": json.dumps(result, ensure_ascii=False)})
    return choice.message.content
```

**注意事项**

- 每次请求都要完整带上 `tools` 声明（文档在代码注释里反复强调）。
- 搜索结果会进入 prompt，`prompt_tokens` 会明显变大；文档示例从 `arguments["usage"]["total_tokens"]` 读取搜索内容占用的 token 数（⚠ 该字段结构文档只在示例里出现，未在参数表中定义）。
- ⚠ 文档未说明：`$web_search` 的 `arguments` 除 `usage` 外还有哪些字段；是否支持 `tool_choice: "required"` 强制搜索；每次搜索的调用费金额（pricing/tools 页不在本次材料内）。
- 搜索结果显著拉长上下文，易触发 `Input token length too long`，文档建议用 1M 上下文的 `kimi-k3`。

### 5B. 官方 Formula `web-search`：见 §6。

---

## 6. 我想用官方工具（Formula）

**Endpoint**: `GET /v1/formulas/{uri}/tools`、`POST /v1/formulas/{uri}/fibers`（均在 `https://api.moonshot.cn/v1` 下；**不在 openapi.json 里**，只在文档页出现）
**用途**: 平台托管的现成工具，通过 Formula 引擎执行，模型侧仍是标准 `function` 流程。除 `web-search` 按次收费外其余限时免费；负载到上限可能临时限流。

| name（uri 为 `moonshot/<name>:latest`） | 描述 |
|---|---|
| `web-search` | 实时信息及互联网检索（按次收费，单价 ⚠ 文档未说明） |
| `convert` | 长度/质量/体积/温度/面积/时间/能量/压力/速度/货币单位换算 |
| `rethink` / `random-choice` / `mew` | 整理想法 / 随机选择 / 随机猫叫和祝福 |
| `memory` | 记忆存储和检索（对话历史、用户偏好持久化） |
| `excel` | Excel / CSV 分析 |
| `date` / `base64` | 日期时间处理 / Base64 编解码 |
| `fetch` | URL 内容提取为 Markdown |
| `quickjs` / `code-runner` | QuickJS 安全执行 JavaScript / Python 代码执行 |

Formula URI 形如 `moonshot/web-search:latest`：namespace 目前只支持 `moonshot`，tag 默认 `latest`。注意工具 `function.name` 是 `web_search`（下划线），uri 里是 `web-search`（连字符）；同时用多个 formula 时自己维护 `function.name -> formula_uri` 映射。

**四步流程（文档原文）**

1. `GET /v1/formulas/{uri}/tools` → 响应 `{"tools": [...]}`，直接作为 chat 的 `tools`
2. `POST /v1/chat/completions` 带上这些 `tools` → 模型返回 `function` 类型 `tool_calls`
3. `POST /v1/formulas/{uri}/fibers`，body `{"name": <function.name>, "arguments": <function.arguments 原字符串>}`（此步产生 tool_call 计费）→ 结果在 `context.output` 或 `context.encrypted_output`
4. 再次 `POST /v1/chat/completions`，带 assistant 消息（含 `tool_calls`）和 `role=tool` 结果

**示例（curl，直接执行一次 fiber）**

```bash
export FORMULA_URI="moonshot/web-search:latest"
curl -X POST "https://api.moonshot.cn/v1/formulas/${FORMULA_URI}/fibers" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{"name": "web_search", "arguments": "{\"query\": \"月之暗面最近有什么消息\"}"}'
```

**示例（Python，requests）**

```python
import os
import requests

BASE = "https://api.moonshot.cn/v1"
HEADERS = {"Authorization": f"Bearer {os.environ['MOONSHOT_API_KEY']}", "Content-Type": "application/json"}
FORMULA_URI = "moonshot/web-search:latest"

def call(method, path, body=None):
    r = requests.request(method, BASE + path, headers=HEADERS, json=body, timeout=120)
    r.raise_for_status()
    return r.json()

tools = call("GET", f"/formulas/{FORMULA_URI}/tools")["tools"]
messages = [{"role": "system", "content": "你是 Kimi。"},
            {"role": "user", "content": "月之暗面最近有什么消息"}]
while True:
    resp = call("POST", "/chat/completions", {"model": "kimi-k3", "messages": messages, "tools": tools})
    message = resp["choices"][0]["message"]
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        print(message["content"]); break
    messages.append(message)          # 原样回传（含 reasoning_content）；官方示例只挑了三个字段，见 ⚠
    for tc in tool_calls:
        fn = tc["function"]
        fiber = call("POST", f"/formulas/{FORMULA_URI}/fibers", {"name": fn["name"], "arguments": fn["arguments"]})
        ctx = fiber.get("context", {})
        result = ctx.get("output") or ctx.get("encrypted_output") or ""
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
```

**示例响应（`POST .../fibers` 成功，文档原样字段）**

```json
{"id": "fiber-...", "object": "fiber", "created_at": 1753440997, "lambda_id": "lambda-...",
 "status": "succeeded",
 "context": {"input": "{\"name\":\"web_search\",\"arguments\":\"{\\\"query\\\": \\\"...\\\"}\"}",
             "encrypted_output": "----MOONSHOT ENCRYPTED BEGIN----...----MOONSHOT ENCRYPTED END----"},
 "formula": "moonshot/web-search:latest", "organization_id": "...", "project_id": "proj-..."}
```

失败时 `status` 为各类错误值，错误信息可能在顶层 `error` 或 `context.error`（思考模型指南示例两处都查）；⚠ 文档未说明 `status` 完整枚举。

**注意事项**

- `web-search` 是 protected 工具，结果在 `context.encrypted_output`，形如 `----MOONSHOT ENCRYPTED BEGIN---- ... ----MOONSHOT ENCRYPTED END----`，**原样塞进 tool 消息即可**，模型能解。
- `function.arguments` 是 JSON 字符串，透传给 fibers 时不要再 `json.loads`。
- ⚠ 文档未说明：Formula 端点的完整请求/响应 schema（不在 openapi.json）、免费工具的免费期限、Formula 接口是否受 RPM 限速。
- ⚠ 文档自相矛盾：Formula 示例的 `tool` 消息没有 `name` 字段，而 tool_calls 指南示例有；`reasoning_content` 的处理也不一致（见 §2）。

---

## 7. 我有几十上百个工具：动态加载 + tool search

**Endpoint**: `POST /v1/chat/completions`，在 `messages` 中插入 `{"role": "system", "tools": [...]}`
**用途**: 避免"工具定义膨胀"——不把全部工具放顶层 `tools`，而是对话进行到需要时再注入；与前缀缓存叠加。

**关键规则**

| 规则 | 说明 |
|---|---|
| 位置即可见范围 | 携带 `tools` 的 system 消息出现在哪，工具从哪开始对模型可见；与顶层 `tools` 的全局工具并存 |
| 必须是完整定义 | 格式与顶层 `tools` 完全一致，不能只给名字 |
| 不能带 `content` | 带了 400，报错原文 `cannot be used with content` |
| 仅 K3 | 其他模型（如 `kimi-k2.6`）返回 `tokenization failed` |
| 按请求生效 | 服务端不记忆；后续请求要原样保留已注入的声明才能继续用且命中缓存 |
| 追加不插入 | 新声明追加到 `messages` 末尾不影响已有前缀缓存；修改/删除中间消息会让其后缓存失效。缓存门槛：上一请求 prompt tokens > 256 |

**示例（curl）**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{"model": "kimi-k3", "messages": [
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "帮我计算一下 23 * 47 的结果。"},
        {"role": "system", "tools": [{"type": "function", "function": {
          "name": "Calculator", "description": "计算器，只支持单个算术表达式的求值",
          "parameters": {"type": "object", "properties": {"expr": {"type": "string", "description": "算术表达式"}}, "required": ["expr"]}}}]}]}'
```

**示例（Python）**

```python
completion = client.chat.completions.create(
    model="kimi-k3",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "帮我计算一下 23 * 47 的结果。"},
        {   # 动态加载：只有 tools，没有 content
            "role": "system",
            "tools": [{
                "type": "function",
                "function": {
                    "name": "Calculator",
                    "description": "计算器，只支持单个算术表达式的求值",
                    "parameters": {"type": "object",
                                   "properties": {"expr": {"type": "string", "description": "算术表达式"}},
                                   "required": ["expr"]},
                },
            }],
        },
    ],
)
print(completion.choices[0].message.tool_calls)
```

OpenAI SDK 会把 `messages` 里未知字段透传，文档说可直接这样写。

**Tool search 模式（K3 最佳实践页）**

1. 顶层 `tools` 只放你后端实现的 `search_tools`（按关键词返回工具名和简介）和少量核心工具；system prompt 里告诉模型可搜索的领域标签。
2. 首轮 `tool_choice: "required"` 强制模型先调 `search_tools`；之后恢复 `"auto"`（切换 `tool_choice` 不破坏缓存）。
3. 拿到候选后，把完整声明用一条 `{"role":"system","tools":[...]}` **追加**到 `messages` 末尾。
4. 模型在后续轮次直接调用这些工具；后续请求原样保留该声明。
5. `reasoning_effort` 在会话开始前定好（切换会打断前缀缓存）。

**注意事项**

- 平台没有专门的 tool search 接口，上面是应用层组合。
- ⚠ 文档未说明：单条 system-tools 消息可注入的工具数量上限；动态注入的工具与顶层同名时以谁为准。

---

## 8. 模型反复调用同一个工具怎么办

判定"重复"：连续多次 `function.name` 与 `function.arguments` 完全相同，且工具结果没有带来新信息。

**先排查消息布局**（绝大多数情况是这里错）：

1. `finish_reason=tool_calls` 时是否把 `choice.message` **原封不动** append 进 `messages`；
2. 每个 `tool_call` 是否都有对应 `role=tool` 消息；
3. `tool_call_id` 是否与 `tool_call.id` 完全一致；
4. 流式下 `function.arguments` 是否拼接完整。

**业务侧检测 + system 提醒**（文档建议阈值 3 / 5 / 8 次）：在下一轮请求的 `system` 消息里追加提醒，例如：

```text
<system-reminder>
You are repeating the exact same tool call with identical parameters. Please carefully analyze the previous result. If the task is not yet complete, try a different method or parameters instead of repeating the same call.
</system-reminder>
```

达到 5 次时换成下面这条（8 次再追加一次）：

```text
<system-reminder>
You have repeatedly called the same tool with identical parameters many times.
Repeated tool call detected:
- tool: {tool_name}
- repeated_times: {repeat_count}
- arguments: {tool_arguments}
The previous repeated calls did not make progress. Do not call this exact same tool with the exact same arguments again.
Carefully inspect the latest tool result and choose a different next action, different parameters, or finish the task if enough evidence has been gathered.
</system-reminder>
```

`<system-reminder>` 只是提示词写法，不是 API 特殊字段，合并进 `role=system` 内容即可。只在"同工具、同参数、连续重复、无新进展"同时成立时触发，避免误判。

---

## 9. 错误速查

| 现象 / 报错（均引自文档） | 原因 | 处理 |
|---|---|---|
| `tool_call_id not found` | 没回填带 `tool_calls` 的 assistant 消息 | `messages.append(choice.message)` |
| tool 消息数 ≠ `tool_calls` 数 / id 对不上 → 请求被拒 | 漏回传某个并行调用 | 每个 `tool_call` 一条 `role=tool` |
| 400 `function name xxx is duplicated` | 一次请求内 `function.name` 重复（含 formula 工具撞名） | 合并 / 改名 |
| 400 `cannot be used with content` | 动态工具 system 消息带了 `content` | 拆成两条 system 消息 |
| `tokenization failed` | 非 `kimi-k3` 模型用动态加载 | 换 `kimi-k3` 或用顶层 `tools` |
| `tool_choice: "required"` 报错 | `kimi-k2.6` / `kimi-k2.7-code` 不支持 | 只在 `kimi-k3` 用 |
| 400 `tool_choice 'specified' is incompatible with thinking enabled` | 思考开启时用指定函数对象 | 改 `required`（K3），或 `kimi-k2.6` 关闭思考 |
| `Input token length too long` | 搜索 / 工具结果撑爆上下文 | 用 `kimi-k3`（1M）；裁剪工具返回 |
| 函数名含 `$` 被拒 | `$` 前缀保留给内置函数 | 改名 |
| 流式 `arguments` 解析失败 | 片段被覆盖而非追加，或未等 `[DONE]` | 按 `index` 追加拼接，流结束后再 `json.loads` |
| `temperature` / `n` 报 `invalid_request_error` | 参数固定不可改 | 不要显式传 |

---

## 10. ⚠ 汇总

| 位置 | 类型 | 内容 |
|---|---|---|
| §1 / §4 | 推断 | 函数对象 `tool_choice` 在 K3 上会 400 —— 由"思考开启时 400"+"K3 思考不可关"推出，文档未直接写 K3 |
| §2 | 未说明 | `role=tool` 消息是否必须带 `name` |
| §2 / §6 | 自相矛盾 | official-tools 示例回传 assistant 时丢弃 `reasoning_content`，与思考模型页要求冲突 |
| §2 | 未说明 | `tool_calls[].id` 的格式约定（示例出现 `call_xxx` / `search:0` 两种） |
| §2 | 自相矛盾 | `max_tokens` 在 OpenAPI 标记弃用，指南示例仍在用 |
| §3 | 自相矛盾 | OpenAPI 响应 `tool_calls[].type` 枚举只有 `function`，流式指南说会返回 `builtin_function` |
| §3 | 自相矛盾 | tool_calls 指南流式示例按 `n=2` 初始化，但 `n` 固定为 1 |
| §4 | 自相矛盾 | openapi.json 给 K2.x 的 `tool_choice` 枚举含 `required`，models-overview 说不支持 |
| §4 | 自相矛盾 | K2.6 的 `tool_choice`：models-overview 说仅不支持 `required`；K2.6 quickstart 说除 auto/none 外都报错 |
| §4 | 未验证 | `required` + 单工具 是否等价于指定函数 |
| §5A | 未说明 | `$web_search` 的 `arguments` 结构（示例出现 `usage.total_tokens`）；能否与 `required` 组合；每次搜索的调用费金额 |
| §6 | 未说明 | fibers `status` 完整枚举与错误格式、web-search 单价、限速；Formula endpoint 不在 openapi.json |
| §6 | 自相矛盾 | Formula 示例 tool 消息无 `name` |
| §7 | 未说明 | 动态注入工具数量上限；与顶层同名工具的优先级 |

所有报错原文（`tool_call_id not found`、`tokenization failed`、`cannot be used with content`、`tool_choice 'specified' is incompatible with thinking enabled`）均引自文档页，**未经真实调用观察**。
