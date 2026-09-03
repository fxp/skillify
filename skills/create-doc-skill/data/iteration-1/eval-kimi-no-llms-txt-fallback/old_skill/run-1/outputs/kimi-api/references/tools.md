# Kimi API 工具调用（tool_calls）参考

> 状态：文档草稿，基于 2026-09-03 抓取的 platform.moonshot.cn/docs 官方文档 + /docs/openapi.json 撰写，**尚未用真实 API 调用验证**。

本文只覆盖 `POST /v1/chat/completions` 上的工具调用：自定义 function 工具、`tool_choice`、内置 `$web_search`、Formula 官方工具、kimi-k3 动态加载工具、重复调用排查。通用聊天参数 / 流式文本 / JSON mode 见 `chat-completions.md`。

## 工具定义格式

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "查询指定城市的实时天气（写清楚作用和使用场景，模型据此决定是否调用）",
    "parameters": {
      "type": "object",
      "properties": {"city": {"type": "string", "description": "城市名称"}},
      "required": ["city"]
    },
    "strict": true
  }
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `type` | string | 是 | — | 目前只有 `function`（内置工具用 `builtin_function`，见下文） |
| `function.name` | string | 是 | — | 必须匹配 `^[a-zA-Z_][a-zA-Z0-9-_]{0,127}$`；不允许 `$`（`$` 前缀保留给内置函数）；同一请求内不可重复，重复返回 400 `function name xxx is duplicated` |
| `function.description` | string | 否 | — | schema 中非必填，但指南要求写清作用与使用场景；动态加载时必须提供 |
| `function.parameters` | object | 是 | — | JSON Schema，顶层固定 `type: object`；需符合 MFJS（Moonshot Flavored JSON Schema）规范：https://github.com/MoonshotAI/walle/blob/main/docs/mfjs-spec.zh.md |
| `function.strict` | boolean | 否 | `true` | 为 true 时严格按 `parameters` 约束模型输出的 arguments；为 false 时只保证 arguments 是合法 JSON 对象 |

要点：
- `parameters` 可用 walle CLI 自检（response_format 的 schema 描述中给出的命令）：`go install github.com/moonshotai/walle/cmd/walle@latest && walle -schema '<schema>' -level strict`。
- `tools` 里的内容计入总 Tokens，`tools + messages` 合计不能超过模型上下文窗口。
- 模型一次可返回多个 `tool_calls`（不同工具或同一工具不同参数），无依赖的调用倾向于并行发出。
- `functions` / `function_call` 旧参数不支持，只认 `tools` / `tool_calls`。

来源: docs/api/chat (openapi tools 字段), docs/guide/use-kimi-api-to-complete-tool-calls, docs/guide/use-official-tools

### 工具调用
**Endpoint**: `POST /v1/chat/completions`
**用途**: 带 `tools` 发起请求，模型决定是否调用工具并以 JSON 输出参数；应用执行后用 `role:"tool"` 消息回传，模型再生成最终回复。

**关键参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `tools` | array | 否 | — | 工具列表，格式见上；**每次请求都要完整带上**（服务端不记忆） |
| `tool_choice` | string \| object | 否 | `auto` | `auto` / `none` / `required` / `{"type":"function","function":{"name":"..."}}`，模型限制见下文 |
| `messages[].role="assistant"` + `tool_calls` | — | — | — | 模型返回的 assistant 消息必须**原封不动**追加回 `messages`（含 `tool_calls`、`reasoning_content`） |
| `messages[].role="tool"` | object | — | — | 字段：`tool_call_id`（必须等于对应 `tool_calls[].id`）、`content`（字符串，约定 `json.dumps` 结果）、`name`（指南示例带上，api 页示例未带，openapi 未列出） |

**示例请求**

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k3",
    "messages": [{"role": "user", "content": "今天北京的天气怎么样？"}],
    "tools": [{"type": "function", "function": {
      "name": "get_weather", "description": "查询指定城市的实时天气",
      "parameters": {"type": "object", "properties": {"city": {"type": "string", "description": "城市名称"}}, "required": ["city"]}}}],
    "tool_choice": "auto"
  }'
```

完整 Python 循环（`openai` SDK，kimi-k3）：

```python
import os, json
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

tools = [{"type": "function", "function": {
    "name": "get_weather", "description": "查询指定城市的实时天气",
    "parameters": {"type": "object", "properties": {"city": {"type": "string", "description": "城市名称"}},
                   "required": ["city"]}}}]

def get_weather(args: dict) -> dict:
    return {"city": args["city"], "weather": "晴", "temperature_c": 24}

tool_map = {"get_weather": get_weather}
messages = [{"role": "system", "content": "你是 Kimi。"},
            {"role": "user", "content": "今天北京的天气怎么样？"}]

finish_reason = None
while finish_reason is None or finish_reason == "tool_calls":
    completion = client.chat.completions.create(model="kimi-k3", messages=messages, tools=tools)
    choice = completion.choices[0]
    finish_reason = choice.finish_reason
    if finish_reason == "tool_calls":
        messages.append(choice.message)          # 原样回传：含 tool_calls 与 reasoning_content
        for tc in choice.message.tool_calls:     # 可能有多个，必须逐个回传结果
            args = json.loads(tc.function.arguments)   # arguments 是 JSON 字符串
            result = tool_map[tc.function.name](args)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "name": tc.function.name, "content": json.dumps(result, ensure_ascii=False)})
print(choice.message.content)
```

**示例响应**（`finish_reason="tool_calls"` 时）

```json
{"choices": [{"index": 0, "finish_reason": "tool_calls",
  "message": {"role": "assistant", "content": "", "reasoning_content": "...",
    "tool_calls": [{"id": "get_weather:0", "type": "function",
      "function": {"name": "get_weather", "arguments": "{\"city\": \"北京\"}"}}]}}],
 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cached_tokens": 0}}
```

**注意事项**
- 用 `finish_reason == "tool_calls"` 判断是否需要执行工具；此时 `content` 通常为空，但偶尔非空（模型解释为何调用），可展示给用户。
- 每个 `tool_call` 必须有且仅有一条对应的 `role:"tool"` 消息，数量不一致或 `tool_call_id` 对不上都报错；多个 tool 消息之间顺序不敏感；id 唯一性只在当轮局部要求。
- `tool_call_id not found`：几乎都是没把返回的 assistant 消息 append 回 `messages`，或 append 时丢了 `tool_calls` 字段。
- **思考模型的 `reasoning_content` 必须回传**：kimi-k3、kimi-k2.7-code 始终保留思考，多轮与工具调用都要把完整 assistant message 原样回传（含 `reasoning_content`），不要只保留 `content`；kimi-k2.6 在一次工具调用循环内也应保留 `reasoning_content`，跨轮是否保留由 `thinking.keep` 决定（默认 `null` 不保留）。用 SDK 时直接 `messages.append(choice.message)` 最稳妥；自己拼 dict 时要显式带上 `reasoning_content`。

来源: docs/guide/use-kimi-api-to-complete-tool-calls, docs/api/chat, docs/guide/use-thinking-models, docs/guide/kimi-k3-quickstart

## 流式输出中的 tool_calls

- `finish_reason` 只在最后一个 chunk 出现，流式下应以 `delta.tool_calls` 是否存在来判断是否有工具调用。
- 先输出 `delta.content`（以及思考模型的 `reasoning_content`），再输出 `delta.tool_calls`，必须等 content 结束后才能识别工具调用。
- 首个 tool_call chunk 给出 `id`、`type`、`function.name`，后续 chunk 只给 `function.arguments` 片段，需按顺序拼接。
- 多个 tool_calls 时用 `index` 字段区分，按 `index` 定位再拼接。

```python
stream = client.chat.completions.create(model="kimi-k3", messages=messages, tools=tools, stream=True)
message = {"role": "assistant", "content": "", "tool_calls": []}
for chunk in stream:
    for choice in chunk.choices:
        delta = choice.delta
        if delta.content:
            message["content"] += delta.content
        for tc in delta.tool_calls or []:
            while len(message["tool_calls"]) <= tc.index:
                message["tool_calls"].append({"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
            slot = message["tool_calls"][tc.index]
            if tc.id: slot["id"] = tc.id
            if tc.type: slot["type"] = tc.type
            if tc.function and tc.function.name: slot["function"]["name"] = tc.function.name
            if tc.function and tc.function.arguments: slot["function"]["arguments"] += tc.function.arguments
# 拼好后 message 与非流式的 choice.message 等价，同样需要 append 回 messages 再回传 tool 结果
```

来源: docs/guide/use-kimi-api-to-complete-tool-calls (处理流式输出中的 tool_calls)

## tool_choice

| 取值 | 行为 | 模型限制 |
|---|---|---|
| `"auto"`（默认） | 模型自行决定是否调用 | 全部模型 |
| `"none"` | 本轮不产生 `tool_calls`，直接输出文本，降低延迟与 token | 全部模型 |
| `"required"` | 本轮必须至少调用一个工具（请求中需声明 `tools`） | **仅 kimi-k3**；kimi-k2.6 / kimi-k2.7-code 传入会报错 |
| `{"type":"function","function":{"name":"get_weather"}}` | 强制调用指定函数 | **与思考开启不兼容**，思考开启时返回 400 `tool_choice 'specified' is incompatible with thinking enabled` |

- `tool_choice` 是请求级参数，每次独立生效；改动它**不会破坏前缀缓存**，可按请求粒度切换。
- 典型用法（tool search 模式）：首轮 `required` 强制调用 `search_tools`，拿到工具后恢复 `auto`。
- kimi-k3 与 kimi-k2.7-code 无法关闭思考，因此按文档推断"指定函数对象"在这两个模型上不可用，只有 `kimi-k2.6` + `thinking.type="disabled"` 才能用（见疑点）。

来源: docs/guide/use-tool-choice, docs/api/models-overview

## 内置联网搜索 `$web_search`

声明时只需 `type` 和 `name`，不用写 `parameters`：

```python
tools = [{"type": "builtin_function", "function": {"name": "$web_search"}}]
```

- `builtin_function` 类型专门表示 Kimi 内置工具；`$` 前缀是内置函数的约定，普通 function 名不允许 `$`。可与普通 `function` 工具在同一 `tools` 中混用。
- 流程与普通工具完全一致，区别在于**搜索由 Kimi 执行**：模型返回 `finish_reason="tool_calls"`、`function.name="$web_search"`，你只需把 `json.loads(arguments)` 原封不动 `json.dumps` 回去作为 `role:"tool"` 消息的 `content`（示例同样带 `tool_call_id` 和 `name`），Kimi 收到后才真正执行搜索并生成 `finish_reason="stop"` 的回复。
- 模型生成的 `arguments` 里会额外带 `usage.total_tokens`（`arguments["usage"]["total_tokens"]`），表示搜索结果将占用的 tokens；这些 tokens 在完成整个流程时计入 `prompt_tokens`。文档示例：搜索内容 13046 tokens，最终 prompt_tokens 13212。
- 搜索结果会显著拉长上下文，文档建议用 1M 上下文的 kimi-k3，避免 `Input token length too long`。
- 计费：除 tokens 外，**每次联网搜索另收一次调用费用**（详见 docs/pricing/tools，本次抓取未含该页）。
- 切换到自建搜索：把 `$web_search` 换成自己的 `function` 定义（补 `description`/`parameters`），并把"原样返回 arguments"的实现换成真正的 search/crawl 逻辑，其余循环代码不变。

```python
def search_impl(arguments: dict) -> dict:
    return arguments   # 使用 $web_search 时原样返回即可

# 循环体内：
if tc.function.name == "$web_search":
    args = json.loads(tc.function.arguments)
    print("search tokens:", args.get("usage", {}).get("total_tokens"))
    result = search_impl(args)
messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": json.dumps(result)})
```

来源: docs/guide/use-web-search, docs/guide/troubleshooting

## 官方工具（Formula API）

web-search 页和官方工具页都建议：在 `kimi-k3` 上做联网搜索优先走 Formula 官方工具通道（标准 `function` tool，OpenAI 协议）。可用官方工具（uri 形如 `moonshot/<name>:latest`，namespace 目前只支持 `moonshot`）：

| 名称 | 说明 | 名称 | 说明 |
|---|---|---|---|
| `web-search` | 实时互联网检索（按次收费） | `fetch` | URL 内容提取为 Markdown |
| `convert` | 单位换算（长度/质量/温度/货币等） | `quickjs` | QuickJS 安全执行 JavaScript |
| `date` | 日期时间处理 | `code-runner` | Python 代码执行 |
| `base64` | Base64 编解码 | `excel` | Excel / CSV 分析 |
| `memory` | 记忆存储与检索 | `rethink` | 整理想法 |
| `random-choice` | 随机选择 | `mew` | 随机猫叫与祝福 |

除 `web-search` 按次收费外其余目前限时免费；负载到上限时可能临时限流。

四步流程：
1. `GET /v1/formulas/{uri}/tools` → 返回 `{"object":"list","tools":[...]}`，`tools` 是标准 function 定义数组，直接并入请求 `tools`（多个 formula 时自己维护 `function.name -> uri` 映射，且 name 不能重复）。
2. `POST /v1/chat/completions` 带上 `tools`，模型返回普通 `function` 类型 `tool_calls`（示例 id `web_search:0`，name `web_search`）。
3. `POST /v1/formulas/{uri}/fibers`，body `{"name": <function.name>, "arguments": <function.arguments 原字符串>}`，**arguments 不要反序列化**，直接透传；此步产生 tool_call 计费。返回 fiber 对象：`status` 为 `succeeded` 或错误；结果在 `context.output`，`web-search` 是 protected 工具，结果在 `context.encrypted_output`（`----MOONSHOT ENCRYPTED BEGIN----...----MOONSHOT ENCRYPTED END----`），该字符串可直接作为 tool 消息 `content`。
4. 把 assistant 消息（含 `tool_calls`）和 `role:"tool"` 结果（`tool_call_id` 对齐）追加后再次请求，直到没有 `tool_calls`。

```python
import os, requests
BASE, URI = "https://api.moonshot.cn/v1", "moonshot/web-search:latest"
H = {"Authorization": f"Bearer {os.environ['MOONSHOT_API_KEY']}"}
def call(m, p, body=None):
    r = requests.request(m, BASE + p, headers=H, json=body, timeout=120); r.raise_for_status(); return r.json()

tools = call("GET", f"/formulas/{URI}/tools")["tools"]
messages = [{"role": "user", "content": "月之暗面最近有什么消息"}]
while True:
    msg = call("POST", "/chat/completions", {"model": "kimi-k3", "messages": messages, "tools": tools})["choices"][0]["message"]
    if not msg.get("tool_calls"):
        print(msg["content"]); break
    messages.append(msg)   # 官方示例只保留 role/content/tool_calls；思考模型建议整条原样回传
    for tc in msg["tool_calls"]:
        fiber = call("POST", f"/formulas/{URI}/fibers", {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]})
        ctx = fiber.get("context", {})
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": ctx.get("output") or ctx.get("encrypted_output") or ""})
```

```bash
curl https://api.moonshot.cn/v1/formulas/moonshot/web-search:latest/tools -H "Authorization: Bearer $MOONSHOT_API_KEY"
curl -X POST https://api.moonshot.cn/v1/formulas/moonshot/web-search:latest/fibers \
  -H "Content-Type: application/json" -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{"name": "web_search", "arguments": "{\"query\": \"月之暗面最近有什么消息\"}"}'
```

来源: docs/guide/use-official-tools, docs/guide/kimi-k3-quickstart (官方工具)

## 动态加载工具（仅 kimi-k3）

在 `messages` 任意位置插入一条**没有 `content`、只有 `tools`** 的 `system` 消息，即可从该位置起让模型看到这些工具：

```python
messages = [
    {"role": "system", "content": "你是 Kimi。"},
    {"role": "user", "content": "帮我计算一下 23 * 47 的结果。"},
    {"role": "system", "tools": [{"type": "function", "function": {
        "name": "Calculator", "description": "计算器，只支持单个算术表达式的求值",
        "parameters": {"type": "object", "properties": {"expr": {"type": "string", "description": "算术表达式，javascript 语法"}},
                       "required": ["expr"]}}}]},
]
completion = client.chat.completions.create(model="kimi-k3", messages=messages)   # OpenAI SDK 可直接透传，无需 extra_body
print(completion.choices[0].message.tool_calls)
```

规则：
- 格式与顶层 `tools` 完全一致，必须是**完整定义**（`name`、`description`、`parameters`），不能只传名字或引用顶层工具。
- 与顶层 `tools` 并存，模型同时看到两类工具；位置决定可见范围（只影响之后的对话）。
- 该消息不能带 `content`，否则 400（`cannot be used with content`）。
- 目前仅 `kimi-k3` 支持；kimi-k2.6 等模型上会返回 `tokenization failed`。
- 服务端不记忆动态声明：后续请求必须在历史中原样保留该消息，否则工具失效（且前缀变化会使缓存失效）。

缓存友好原则（与自动前缀缓存叠加）：新声明**只追加到 `messages` 末尾**、不要在中间插入/修改；已注入的声明后续请求原样保留；每轮都用的核心工具固定放顶层 `tools` 且不再改动（顶层 `tools` 声明不影响缓存命中）。前缀缓存门槛：上一请求 prompt tokens > 256 才会被缓存。

Tool Search 模式（API 无专门接口，自行组合）：顶层 `tools` 只放一个自建 `search_tools`；system prompt 里给出可搜索的工具目录/关键词；模型调用 `search_tools` 后，应用把命中工具的完整定义通过 `{"role":"system","tools":[...]}` 追加进 `messages`；模型随后即可直接调用。首轮可配合 `tool_choice="required"` 强制先搜工具。

来源: docs/guide/use-dynamic-tool-loading, docs/guide/kimi-k3-quickstart (动态加载工具), docs/api/chat (KimiK3 messages 描述)

## Kimi K3 工具调用最佳实践（要点汇总）

官方专门页面 `docs/guide/kimi-k3-tool-calling-best-practice` 在本次抓取中**未获得**，以下是其他页面引用到的要点：
- 大量工具（几十上百个）不要一次性放顶层 `tools`，用动态加载按需注入，降低 token 与选错率（Lazy-Load、工具目录思路）。
- 首轮 `tool_choice="required"` 强制走工具链路（如强制检索/查库），后续恢复 `auto`。
- 核心工具固定在顶层、按需工具动态追加，保持前缀稳定以持续命中缓存；`tool_choice` 可随请求变化不影响缓存。
- 推理强度用顶层 `reasoning_effort`（low/high/max，默认 max）；会话中途切换档位会破坏前缀缓存，开始前定好。
- 多轮与工具调用始终原样回传完整 assistant message（含 `reasoning_content`）。

来源: docs/guide/use-tool-choice, docs/guide/use-dynamic-tool-loading, docs/api/models-overview, docs/guide/kimi-k3-quickstart

## 排查：模型重复调用同一个工具

判定：连续多次 `function.name` 与 `function.arguments` 完全相同，且工具结果没有带来新信息。

先查消息布局（大多数"重复"其实是布局错误）：
1. `finish_reason=tool_calls` 时是否把 `choice.message` 原封不动 append 回 `messages`；
2. 每个 `tool_call` 是否都有对应的 `role=tool` 消息；
3. `tool_call_id` 是否与 `tool_call.id` 完全一致；
4. `stream=True` 时是否正确按 `index` 拼接了 `tool_calls`，尤其是 `function.arguments`。

布局无误仍重复：在业务侧做重复检测，并把提醒追加到下一轮的 `role=system` 提示词中（`<system-reminder>` 只是提示词写法，不是 API 字段）：
- 连续重复 3 次：追加 "You are repeating the exact same tool call with identical parameters. Please carefully analyze the previous result. If the task is not yet complete, try a different method or parameters instead of repeating the same call."
- 达到 5 次：追加更明确的提示，包含 `tool`、`repeated_times`、`arguments`，并要求 "Do not call this exact same tool with the exact same arguments again... choose a different next action, different parameters, or finish the task"。
- 达到 8 次：再次追加上述提示。
- 只有"同一工具、同一参数、连续多次、结果无进展"同时成立才触发，避免误判。

来源: docs/guide/tool-call-repeat, docs/guide/troubleshooting

## 待验证疑点

- (a) `role:"tool"` 消息的 `name` 字段：tool-calls 指南、web-search 指南示例都带 `name`，api/chat 页与 k3-quickstart 示例只带 `tool_call_id` + `content`，openapi messages 项未列 `tool_call_id`（只有 role/content/name/partial）。需确认 `name` 是否必需、缺 `tool_call_id` 是否报错。
- (a) openapi 中 `tools[].type` 枚举只有 `function`，但 web-search 指南使用 `type: "builtin_function"`；schema 未覆盖内置工具，需确认 `$web_search` 在 kimi-k3 上当前是否仍可用。
- (a) `$web_search` 状态自相矛盾：web-search 页说"kimi-k3 始终推理，可直接配合使用"，k3-quickstart"重要限制"却说"联网搜索正在更新，近期不建议用于生产流程"，且两页都建议 kimi-k3 优先走 Formula 官方工具通道。需实测哪条通道可用、行为差异。
- (a) openapi `tool_choice` 描述四种取值不分模型，但 models-overview 明确 kimi-k2.6 / kimi-k2.7-code 不支持 `required`（报错）；schema 未表达该限制。
- (b) 指定函数对象的 `tool_choice` "与思考开启不兼容"（use-tool-choice）。kimi-k3、kimi-k2.7-code 无法关闭思考，是否意味着这两个模型上完全不能用指定函数？kimi-k2.6 `thinking.type="disabled"` 时是否可用？文档未直接说明。
- (b) `function.strict` 默认 `true` 且 `parameters` 需符合 MFJS：不符合时是"返回错误"还是"warning"（response_format 的描述是"错误或 warning"），普通 JSON Schema 里常见的 `additionalProperties`、`$ref`、`oneOf` 等在 MFJS 下能否通过，未验证。
- (b) `function.name` 正则允许 `-`（`^[a-zA-Z_][a-zA-Z0-9-_]{0,127}$`），与 OpenAI 惯例（允许 `.`）不同；含 `.` 的函数名是否 400 需确认。
- (b) tool_call id 格式：指南示例是 `search:0`、`web_search:0`，api 页示例是 `call_xxx`；同一轮多个调用的 id 是否为 `name:index`，未验证，代码不应依赖格式。
- (b) 流式：文档称"先输出 delta.content 再输出 delta.tool_calls"，思考模型的 `delta.reasoning_content` 与 tool_calls 的先后顺序、以及 tool_calls chunk 中是否也带 `reasoning_content`，未说明。
- (b) 思考模型多轮回传：k3 与 k2.7-code 要求整条 assistant message（含 `reasoning_content`）原样回传；若省略 `reasoning_content` 是报错还是静默降质，文档未说明。官方工具页的 requests 示例只回传 `role/content/tool_calls`（丢弃 reasoning_content），与 thinking-models 页的要求冲突。
- (b) 动态加载 system 消息：非 K3 模型报 `tokenization failed`，具体 HTTP 状态码 / error.type 未给出；同一请求内多条动态工具消息重复声明同名工具是否算 `duplicated`，未说明。
- (b) `$web_search` 的 `arguments.usage.total_tokens` 只是预估还是精确值；每次搜索的单次费用金额在 docs/pricing/tools（本次未抓取）。
- (b) Formula fiber：`status` 非 `succeeded` 时的错误枚举、`encrypted_output` 是否只对 `web-search` 出现、`GET /formulas/{uri}/tools` 是否需要 URL 编码 `:`，均未说明。
- (b) 官方页面 `docs/guide/kimi-k3-tool-calling-best-practice` 本次未抓到（多个页面引用），本文"最佳实践"一节是从其他页面拼出的，需补抓核对。
- (c) 与 OpenAI 差异：`tools` 必须每次请求完整携带（含 `$web_search`）；`required` 仅 K3；指定函数对象在思考开启时 400；`functions`/`function_call` 不支持；tool 消息数量必须与 `tool_calls` 严格一一对应，少一条即报错；`$` 前缀名字保留给内置函数。
