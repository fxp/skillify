# NOTES — 火山方舟标准 API · 豆包 Seed 2.0 lite 客服问答（Node.js）

> 未用真实 Key 调用过。请求形态（Base URL / 鉴权 / `thinking` / `stream_options` / usage 收尾 chunk）依据方舟官方文档与 `volcengine-ark` skill 中在 Agent Plan 入口做过的实测结论；标准入口 `/api/v3` 本身在 skill 里标为「文档转录，未实测」，下文对应处已注明。

## 文件

| 文件 | 作用 |
|---|---|
| `customer-service.js` | 入口脚本。单问单答 / stdin 管道 / 交互式多轮（`/reset` `/usage` `/exit`），流式打印回答，结束打印 token 用量与耗时 |
| `ark-client.js` | 零依赖流式客户端：请求构造、SSE 解析、错误映射（错误码 → 排查提示）、建连阶段重试、超时、取消 |
| `ark-client.test.js` | `node --test`，用注入的 `fetchImpl` 模拟方舟响应，16 个用例全部通过（不联网） |
| `package.json` | `"type": "module"`，Node ≥ 18.17，无第三方依赖 |
| `.env.example` | 环境变量说明 |

运行：

```bash
export ARK_API_KEY=<方舟 API Key>
node customer-service.js "你们的退货政策是什么？"     # 单问单答
node customer-service.js                               # 交互式多轮
npm test                                               # 单元测试（无网络）
```

回答走 **stdout**，用量 / 提示 / 错误走 **stderr**，方便把回答单独管道出去。

## 三个关键选择

### 1. Base URL：`https://ark.cn-beijing.volces.com/api/v3`

同一域名下有三套互不通用的入口：标准后付费 `/api/v3`、Coding Plan `/api/coding/v3`、Agent Plan `/api/plan/v3`。用户说的是「方舟 API Key + 模型已开通」，即标准后付费，所以用 `/api/v3`。

- `/api/plan/v3`、`/api/coding/v3` 是套餐入口：Key 类型 / `model` 格式都不一样，且官方口径「不可用于普通 API 调用」。方舟 API Key 打 Plan 入口预期 401。
- 反之套餐用户如果误用 `/api/v3`，不会报错，而是**直接从后付费余额扣钱**。本脚本面向后付费，所以走 `/api/v3` 是正确的；`ark-client.js` 里检测到 baseURL 指向 `/api/plan|coding` 时只给 warning 不阻止，便于复用。

### 2. Key：`ARK_API_KEY`，`Authorization: Bearer <key>`

- 控制台 → API Key 管理 里的「方舟 API Key」（标准 + Coding Plan 共用这一种）。**不是** Agent Plan 专属 Key——那把 Key 打 `/api/v3` 实测 401 `AuthenticationError`。
- Key 只从环境变量读，不写进代码 / 命令行参数；脚本启动时缺 Key 直接退出并提示。
- 新老两种 Key 格式（UUID / `ark-<uuid>-<suffix>`）都有效；代码 `trim()` 掉首尾空格。

### 3. Model：`doubao-seed-2-0-lite-260428`（可用 `ARK_MODEL` 覆盖）

- 标准入口用**带日期版本的 Model ID，版本号用连字符**；`doubao-seed-2.0-lite`（小写、点分、无日期）是 Plan 入口的 Model Name 写法。标准入口传 Model Name 是否被接受，skill 标记为未测——所以默认值用 Model ID。
- 选 `260428` 而不是 `260215`：模型列表里 `doubao-seed-2-0-lite-260428` 是 2.0 lite 的最新版（256k 上下文、128k 输出、RPM 30000 / TPM 5,000,000），支持 `thinking.type: disabled`。
- 如果账号策略要求用接入点（404 `InvalidEndpointOrModel.ModelIDAccessDisabled`），把 `ARK_MODEL` 设成控制台创建的 `ep-xxx` 即可，代码不需改。
- 响应里的 `model` 字段会回显**实际服务的版本**，脚本在用量区打印出来，用于核对没有被路由到别的版本。

## 三个功能要求怎么实现的

| 要求 | 实现 | 依据 |
|---|---|---|
| 关闭深度思考 | 请求体顶层 `"thinking": {"type": "disabled"}` | 方舟私有字段，不在 OpenAI 规范里。`doubao-seed-2-0-lite` 默认**开**思考（实测不传时 `reasoning_tokens: 109`），传 `disabled` 实测生效（`reasoning_tokens: 0`）。因为不用 OpenAI SDK，所以不涉及 `extra_body` |
| 流式输出 | `"stream": true`，自写 SSE 解析器逐 `data:` 行派发 `delta.content` | 标准 SSE，`data: [DONE]` 结束 |
| 结束时打印用量 | `"stream_options": {"include_usage": true}`；`[DONE]` 之前会多一个 `choices: []` 且带完整 `usage` 的 chunk，其余 chunk `usage: null` | 豆包系列流式默认 `usage: null`，不带 `include_usage` 就拿不到用量；实测 usage 只在末尾 chunk 出现 |

打印的用量：`prompt_tokens`（含 `cached_tokens`）、`completion_tokens`（含 `reasoning_tokens`）、`total_tokens`、实际服务模型、总耗时与首字耗时。交互模式下还有 `/usage` 累计。

## 为什么不用 `openai` npm 包

skill 里 Node 的 openai SDK 示例是从 Python 示例推断的（顶层多余字段 `thinking` 能否透传**未实测**），而 `thinking` 是本任务的核心要求。用 Node 18+ 内置 `fetch` 直接发请求，字段完全可控、零依赖、无版本漂移；代价是自己写 SSE 解析和重试，已在 `ark-client.js` 实现并有测试覆盖。想换成 openai SDK：`new OpenAI({ baseURL: ".../api/v3", apiKey })` 后 `create({ ..., stream: true, stream_options: { include_usage: true }, thinking: { type: "disabled" } })`，跑通后检查 usage 里 `reasoning_tokens` 是否为 0 以确认 `thinking` 确实被发出去了。

## 防的坑

1. **`role` 只能是 `system` / `user` / `assistant` / `tool`**。OpenAI 新版 SDK 默认的 `developer` role 在方舟返回 400 `InvalidParameter`（实测）。`validateMessages()` 在本地就拒绝，不发请求。
2. **usage 收尾 chunk 没有 `choices`**。消费流时先判 `chunk.choices?.[0]` 是否存在，否则会在末尾 `undefined.delta` 崩掉。
3. **`max_tokens` 与 `max_completion_tokens` 互斥**（方舟 400）。思考已关闭，回答长度用 `max_tokens`（默认 1024，`ARK_MAX_TOKENS` 可调）即可；两者同传本地直接抛错。若以后打开思考，改用 `max_completion_tokens`（豆包的 `max_tokens` 不限思维链，但 kimi-k3 等第三方模型会把思维链算进去截空回答）。
4. **流式中途不重试**。客户端中断 / 服务端中止时已生成的 token 照样计费，所以重试只发生在**拿到响应头之前**（网络错误、429 限流类、500），指数退避 + 抖动、尊重 `Retry-After`，默认最多 2 次。429 中 `QuotaExceeded`（免费额度耗尽）和 `SetLimitExceeded`（自设限额）不重试；401 / 403 / 404 / 400 不重试。限流请求方舟不计费，重试安全。
5. **两段超时**：建连 / 首包 30 s，收流期间 chunk 间空闲 90 s（`ArkTimeoutError`）。Ctrl+C 走 `AbortController` 立即断连，避免继续产生 token。
6. **错误 body 可能为空**（路径不存在时 404 空 body）。`ArkApiError.fromResponse` 先判空再 `JSON.parse`，永远不会因解析错误 body 而崩。判别只用 `error.code`（`error.type` 实测可能为空串），并从 message 里抽出 `Request id` 供提工单。
7. **常见错误码映射成排查提示**：`AuthenticationError`（Key 类型 / 空格）、`ModelNotOpen` / `OperationDenied.ServiceNotOpen`（去「开通管理」开通——标准入口的前置条件）、`InvalidEndpointOrModel.NotFound`（Model ID 格式 vs Model Name）、`AccountOverdueError`（欠费 1 分钟即停服）等。
8. **SSE 解析按「一行 `data:` = 一个事件」**，而不是按规范把多行 data 用 `\n` 拼接：OpenAI 兼容服务器每行就是一个完整 JSON，规范拼接在服务器不发空行时会把两个 JSON 粘在一起。同时处理跨 TCP 包切断的行（含多字节汉字中间被切）、CRLF、`:` 注释行、`event:` 行；消费者提前退出时 `reader.cancel()` 释放连接。
9. **思考被意外打开的自检**：如果 delta 里出现 `reasoning_content`，只在 stderr 提示一次、不混进回答；用量里 `reasoning_tokens > 0` 时也打警告。这两个都不该在 `thinking.disabled` 下发生，出现即说明参数没生效或模型版本变了。
10. **多轮上下文只回传 `role` + `content`**。关闭思考后没有 `reasoning_content` / `encrypted_content` 需要回传；system prompt 固定放最前面，有利于隐式前缀缓存命中（`cached_tokens`）。
11. **计费提醒**：标准入口是按 token 后付费（doubao-seed-2.0-lite 输入 0.6 元 / 百万 token 起、输出 3.6 元起，按输入长度分档），要严格控费可在控制台「开通管理 → 推理限额」设上限（触发后 429 `SetLimitExceeded`）。
12. **`X-Client-Request-Id`**：每次请求带一个 UUID，方便与方舟服务端日志对账；`ARK_DEBUG=1` 会把请求体和每个 SSE chunk 打到 stderr。

## 验证方式（无 Key）

- `npm test`：16 个用例覆盖请求形态、SSE 边界、usage 收尾、错误映射、重试 / 不重试、超时、取消、role 校验。
- 用本地 mock SSE 服务器（放在会话 scratchpad，未随交付）跑过 `customer-service.js` 的单问单答、401、stdin 管道三条路径，输出与预期一致。
- 拿到 Key 后第一次真实调用建议加 `ARK_DEBUG=1`，核对：响应 `model` 为 `doubao-seed-2-0-lite-260428`、无 `reasoning_content`、`reasoning_tokens: 0`、末尾 usage chunk 存在。
