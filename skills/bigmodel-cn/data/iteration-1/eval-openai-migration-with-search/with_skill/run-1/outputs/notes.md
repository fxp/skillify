# 迁移说明与假设

## 采用的方案
- 沿用 `openai` Python SDK（不换库），只改 `OpenAI(...)` 的两个构造参数：
  - `api_key`：换成智谱 API Key（示例中从环境变量 `ZHIPU_API_KEY` 读取，未设置时用占位字符串，不会真的发请求）。
  - `base_url`：`https://open.bigmodel.cn/api/paas/v4/`（智谱官方文档明确的 OpenAI 兼容端点）。
  - `model`：换成智谱模型代码 `glm-5.3`。
- 联网搜索通过 `chat.completions.create(tools=[...])` 里加一个 `{"type": "web_search", "web_search": {...}}` 工具项实现，这是智谱文档里"三层联网检索能力"中的第二层（内嵌在 chat/completions 里，平台自动判断是否要搜索、自动执行、自动把结果糅合进回答），不是我编造的参数，来源是技能包 `references/tools.md` 第 380 行和 `references/chat.md` 第 433 行的工具类型对照表。

## 做出的假设
1. **默认模型选 `glm-5.3`**：技能文档里多处示例（快速开始、OpenAI 兼容层示例）都用它作为默认旗舰对话模型，用来对应原脚本里未指明的 OpenAI 模型（如 `gpt-4o`）。如果用户原脚本用的是更轻量的模型，可以按 `references/models.md` 换成 `glm-5.3-flash` 等。
2. **搜索引擎选 `search_pro`**：文档说它"多引擎协同、召回率更高"，作为通用场景的合理默认；`search_std` 更省成本，可按需替换。
3. **`search_recency_filter` 设为 `oneYear`**：为了体现"查最新信息"的意图，但文档默认值是 `noLimit`；这是我加的默认收紧，不是强制要求，按业务需要可以去掉或改成 `oneMonth`/`oneDay`。
4. **API Key 环境变量名用 `ZHIPU_API_KEY`**：技能文档里官方示例常用 `ZAI_API_KEY`（对应 zai-sdk）或 `ZHIPUAI_API_KEY`（通用示例），三者并无强制统一命名；选了语义上更直观的 `ZHIPU_API_KEY`，实际项目里换成团队约定的变量名即可。
5. **`tool_choice` 未显式传**：文档说 `tool_choice` 目前默认且仅支持 `"auto"`，web_search 又是平台自动执行的工具（不是需要显式授权调用的 function），所以没有传这个参数，保持默认行为。

## 不确定 / 建议实际调用时验证的点
1. **`web_search` 工具项在 `tools` 数组里的确切 JSON 结构**：技能包的 `references/chat.md` 只给出了一张字段对照表（`web_search.enable`、`search_engine`、`search_query` 等字段名），**没有给出一段完整可复制的 JSON 示例**（不像 `function` 类型和独立的 `POST /paas/v4/web_search` 接口那样有现成的请求体样例）。我是按照同一张表里 `function`/`mcp` 两种工具类型"顶层 `type` 字段 + 与 type 同名的嵌套对象装参数"的一致模式，推断出 `{"type": "web_search", "web_search": {"enable": true, "search_engine": "search_pro", ...}}` 这个结构。**建议接入时先用一次真实请求验证这个嵌套结构是否正确**（比如 `enable` 字段是否真的需要显式传 `true`，还是只要 `tools` 里出现 `type: "web_search"` 就默认启用），如遇到"参数非法"报错，以 API 实际报错和 `docs.bigmodel.cn` 最新文档为准。
2. **响应体里 `web_search` 引用数组能否通过 OpenAI Python SDK 的返回对象直接读到**：这是智谱在标准 `ChatCompletion` 响应之外附加的顶层扩展字段，OpenAI 官方 SDK 用 pydantic 模型解析响应，我不能 100%确定当前版本的 `openai` 库会把这类未在其 schema 中定义的顶层字段透传到 `response.model_extra`（不同大版本的 `openai` SDK 对"额外字段"的处理策略可能不同）。代码里做了防御性读取（先尝试 `response.web_search`，再尝试 `response.model_extra.get("web_search")`），读不到就跳过来源展示，不影响主回答，但**如果需要稳定拿到引用来源，更稳妥的做法是绕过 SDK 的响应解析，直接用 `requests` 发起该请求并解析原始 JSON**（示例可参考 `references/tools.md` 里 `web_search`/`reader` 接口的 `requests` 写法），或改用智谱官方 `zai-sdk`。
3. **`temperature=0` 等 OpenAI 常见写法在智谱这边不兼容**：文档提到智谱 `temperature` 合法区间是 `(0,1)`（不包含 0），如果原始 OpenAI 代码里有 `temperature=0` 或 `do_sample=False` 之类的写法要求确定性输出，迁移时需要相应调整（示例脚本本身没有设置 `temperature`，未受影响，但这是常见的迁移隐患，一并记录）。

## 未做的事
- 未实际调用 bigmodel.cn API（没有真实 Key），仅做了 `python -m py_compile` 语法检查，保证脚本可运行、无语法错误。
- 未处理流式输出（`stream=True`）——原始任务描述的是"简单的现有脚本"，判断非流式调用已经覆盖"迁移 + 联网搜索"的核心诉求；如需要流式，思路一致（`stream=True` 后按 SSE chunk 解析 `delta.content`），可参考 `references/sdk-and-compat.md` 里的流式示例。
