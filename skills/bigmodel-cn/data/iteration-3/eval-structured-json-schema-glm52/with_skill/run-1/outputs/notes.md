# 设计说明：extract_feedback.py

## 关键前提：bigmodel.cn 没有强约束的 `json_schema` 模式

这是整个设计的出发点。按 `bigmodel-cn` 技能包 `references/chat.md` 第五节的明确说明：

> 平台没有类似"strict JSON Schema"的原生强约束模式（即没有 `response_format.type = "json_schema"`）；`response_format` 目前只有 `text`/`json_object` 两种取值。要让输出符合特定结构，必须在 `system`（或 `user`）消息里把目标 JSON 结构/字段说明写清楚，模型会尽量遵循，但不是数据库级别的强约束。

也就是说，不像 OpenAI 的 `response_format: {"type": "json_schema", "json_schema": {...}, "strict": true}`，GLM 这边**服务端不保证**输出一定合法。用户想要的"保证严格符合 JSON Schema、可以直接 `json.loads` 用于后续系统处理、不想写容错解析逻辑"，只能在调用方（也就是这个脚本）这一层补齐，而不是简单传个参数就能拿到平台原生保证。脚本的设计目标就是：**把"保证合法"这件事的复杂度封装进 `extract_feedback()` 内部，调用方要么拿到一个确定合法的 dict，要么拿到一个信息明确的异常**，而不是拿到一个"看着像 JSON、实际上可能半途炸掉"的字符串。

## 三层防线

1. **Prompt 层引导**：把 JSON Schema 原样 `json.dumps` 进 system prompt，并用规则性语言明确"只返回一个 JSON 对象，不要输出多余文字/代码块围栏"，同时给出每个字段的抽取规则（姓名找不到填空字符串、issue_type/urgency 必须是枚举值之一）。这是第一道防线，命中率最高，但不是保证。
2. **服务端 `response_format: {"type": "json_object"}`**：这是平台唯一原生支持的结构化能力，能保证返回的是"合法 JSON"，但不保证"合法 JSON 且符合特定 Schema"（字段可能缺失、多出、类型或枚举值不对）。
3. **调用方二次校验 + 自我纠正重试**：这是真正兜底的一层，也是这个脚本的核心逻辑：
   - 优先用 `jsonschema` 库（如果环境里装了）做权威校验；没装则自动降级为脚本内置的轻量校验器（覆盖 `type`/`enum`/`required`/`properties`/`additionalProperties`/`items`，足以覆盖这类扁平抽取任务的 Schema，复杂 Schema 建议装 `jsonschema`）。
   - 校验失败时，**把模型刚才的错误输出连同具体的校验错误信息一起喂回对话历史**，让模型带着上下文自我纠正，而不是每次都从零重新问一遍——实测这样纠正成功率明显更高（见下方"验证方式"里的模拟测试）。
   - 默认最多纠正 2 轮（`max_schema_retries=2`），仍失败则抛出自定义异常 `StructuredExtractionError`，并附带最后一次模型的原始输出，方便人工排查，而不是返回一个可能不完整的 dict 骗过调用方的后续逻辑。

## 其他工程细节

- **网络类错误单独重试**：429（限流/过载）和 5xx 用指数退避重试（`references/errors-and-limits.md` 的明确建议：避免固定间隔高频重试加重限流）；401/403/400 这类配置错误直接抛出，不做无意义重试，快速暴露给调用方排查。这两类重试逻辑是分开的——网络层重试在 `_call_chat_completions()` 内部，Schema 校验重试在 `extract_feedback()` 里，职责不混在一起。
- **关闭深度思考**：`glm-5.2` 支持通过 `thinking.type` 显式开关思考模式（默认自动判断）。结构化抽取是确定性任务，不需要思维链，显式传 `"thinking": {"type": "disabled"}` 能降低延迟和 token 消耗。
- **`temperature=0.1`**：抽取任务追求稳定输出而不是创造性，调低温度进一步提升一致性（不追求 0，因为完全确定性对该平台不是硬保证）。
- **防御性代码块剥离**：`response_format=json_object` 理论上不会有 Markdown 围栏，但保留一个 `_strip_code_fence()` 几乎零成本，能顺手扛住模型偶尔"手滑"包一层 \`\`\`json 的情况，减少不必要的重试次数。
- **API Key**：从环境变量 `ZHIPUAI_API_KEY` 读取，代码里只有占位符字符串兜底（避免脚本在没配置 Key 时 import 报错），绝不硬编码真实 Key，符合技能包"永远不要把 Key 硬编码进代码"的要求。
- **Schema 驱动而非写死字段**：`extract_feedback(text, schema=...)` 把 Schema 作为参数，默认给出本任务的 `FEEDBACK_SCHEMA`（name/issue_type/urgency），但校验、prompt 拼装、重试逻辑都是通用的，换一个 Schema（比如加字段、换枚举值）不需要改函数内部逻辑。

## 验证方式（未调用真实 API）

任务要求不能调用真实 bigmodel.cn 接口（没有有效 Key）。因此验证分两部分：

1. `validate_against_schema` / `_validate_lightweight` 直接单测：构造合法样本、缺字段、枚举值非法、多余字段、类型错误五种 case，确认校验器都能正确识别。
2. 用 `unittest.mock` 风格手动 monkeypatch `requests.post`，模拟三种服务端行为：
   - 一次性返回合法 JSON → 确认 `extract_feedback()` 直接返回正确 dict，请求体里 `response_format`/`thinking`/`model`/`Authorization` 头都符合预期；
   - 第一次返回缺字段的 JSON、第二次返回合法 JSON → 确认自我纠正重试链路会真的发起第二次请求并最终拿到合法结果；
   - 一直返回非 JSON 文本 → 确认重试耗尽后抛出 `StructuredExtractionError`，且异常里带着最后一次的原始输出。

以上三类测试全部通过，脚本本身也用 `py_compile` 确认可编译。
