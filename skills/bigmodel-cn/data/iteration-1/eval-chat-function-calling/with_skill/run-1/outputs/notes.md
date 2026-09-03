# notes.md — weather_agent.py

## 做了什么

`weather_agent.py` 是一个命令行天气助手，直接用标准库 `requests` 调用智谱开放平台
`POST https://open.bigmodel.cn/api/paas/v4/chat/completions`，模型用 `glm-5.3`，
实现了完整的 Function Calling 闭环：

1. 注册一个 `get_weather(city)` 工具（`type: "function"`），随请求传给模型。
2. 模型判断需要查天气时返回 `finish_reason == "tool_calls"` 且 `message.tool_calls` 非空。
3. 脚本把 assistant 消息（含 `tool_calls`）原样追加回 `messages`，本地执行
   `get_weather`（返回 mock 数据），再把结果包成 `role: "tool"` 消息（带上对应的
   `tool_call_id`）追加进去。
4. 再次调用 `chat/completions`，直到模型给出 `finish_reason != "tool_calls"` 的最终
   自然语言回答为止（用 `MAX_TOOL_CALL_ROUNDS` 防止死循环）。

未使用官方 `zhipuai`/`zai-sdk`，未使用流式（`stream=false`），因为任务重点是把
"工具调用协议"的请求/响应结构做对，流式再叠加 `tool_stream` 拼接逻辑会让核心逻辑更难
审查。API Key 从环境变量 `ZHIPUAI_API_KEY` 读取，未硬编码。

## 做出的假设

- **模型选择 `glm-5.3`**：任务里用户明确点名"GLM-5.3"，`references/models.md` 确认
  该模型代码存在且是当前旗舰通用对话/长程 Agent 模型，原生支持 `tools`（function 类型）。
- **`tool_choice: "auto"`**：`chat.md` 里明确说这是目前唯一支持的取值，所以显式传了
  `"auto"` 而不是留空，行为上等价，但显式写出更利于阅读代码的人理解协议约束。
- **`thinking`/`reasoning_effort` 显式传参**：`glm-5.3` 强制开启深度思考、无法关闭，
  只能调 `reasoning_effort`（仅接受 `low`/`high`/`max`）。为了避免默认 `max` 档位让一次
  简单的天气问答产生过多思考 token/延迟，脚本里选择了 `"high"`。这是我的主观选择，
  换成 `"max"` 或干脆不传（走默认 `max`）也完全合规。
- **mock 天气数据的形状**：文档只要求"可以返回 mock 数据"，没有约束字段名。我参考了
  `chat.md` 示例里的 `{"city", "temperature", "condition"}` 结构做了扩展（加了
  `humidity_pct`、`wind`、`source: "mock-data"`），字段名是我自己设计的，不是平台强制
  的 schema——工具返回值的字段完全由业务方自定义，模型只是把它当文本读。
- **`get_weather` 对未知城市的兜底**：没有让脚本对陌生城市报错，而是返回一个通用兜底
  mock 值，这样可以保证"工具执行 → 传回模型 → 模型给出最终回答"这条链路总能跑通，便于
  演示/测试。真实业务里这里应该是调用真实天气 API 并处理"城市不存在"之类的错误。
- **把 `reasoning_content` 一并存回历史（Preserved/Interleaved Thinking）**：
  `chat.md` 第六节提到 GLM-4.5 起默认支持"交错式思考"，工具调用场景下"必须显式保留
  `reasoning_content` 并在把工具结果传回时一并带上"，所以 `build_assistant_message`
  里加了这一段。这是按文档字面要求做的，但没有用真实 API Key 实测验证过效果差异（见下）。

## 不确定 / 没有把握的地方

- **`reasoning_content` 缺失时的具体后果没有实测**：文档说交错式思考下不带
  `reasoning_content` 会"降低效果甚至失效"，但没说清楚"失效"是报错还是只是效果变差。
  脚本里做法是"有就带上，没有（`None`）就不加这个字段"（`if message.get("reasoning_content")
  is not None`），这是我认为最安全的写法，但没有用真实请求验证过 `glm-5.3` 在工具调用响应
  里是否总会带 `reasoning_content`，或者只在某些情况下才有。
- **`thinking`/`reasoning_effort` 是否会影响 `tool_calls` 的产生方式**：文档没有明确说
  深度思考强度会不会改变模型选择是否调用工具、或改变 `tool_calls` 的结构，我假设不会
  （只影响 `reasoning_content` 的长度/质量），但这一点没有官方文档逐字确认，也没法用
  真实 API 验证。
- **视觉/工具混合场景不适用**：`chat.md` 提到视觉模型的 `tools` 只支持 `function` 类型
  且仅 `glm-5.3-flash`/`glm-4.6v`/`autoglm-phone` 支持，本脚本用的是纯文本模型
  `glm-5.3`，这条限制不适用，但如果之后有人把 `MODEL` 改成视觉模型，需要重新核对
  `tools`/`tool_choice` 的支持范围。
- **未做真实网络调用验证**：按任务要求没有用真实 API Key 调用 bigmodel.cn，所以请求体
  字段名、响应体解析路径（`choices[0].message.tool_calls`、`.finish_reason` 等）都是严格
  照抄 `references/chat.md` 里的示例和字段表写的，逻辑上应该正确，但没有实际 HTTP 往返
  验证过（比如平台是否会在某些情况下返回和文档描述不完全一致的字段）。
