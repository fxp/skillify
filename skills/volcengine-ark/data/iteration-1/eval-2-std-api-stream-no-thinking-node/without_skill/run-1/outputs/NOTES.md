# NOTES — 方舟标准 API × 豆包 Seed 2.0 lite 客服问答脚本

## 文件

| 文件 | 作用 |
|---|---|
| `index.js` | CLI 入口：交互式多轮 / `--question` 单问 / stdin 管道；流式打印回答，结束打印 token 用量 |
| `ark-client.js` | 零依赖的方舟 Chat Completions 流式客户端（SSE 解析、超时、重试、错误映射） |
| `package.json` | ESM，Node ≥ 18.17（依赖全局 `fetch`、Web Streams、`node:util.parseArgs`） |
| `.env.example` | 环境变量样例 |

无第三方依赖，`npm install` 不需要执行；`export ARK_API_KEY=...` 后直接 `node index.js`。

## 关键选择

### Base URL
`https://ark.cn-beijing.volces.com/api/v3`，接口 `POST /chat/completions`。这是方舟「标准 API」（OpenAI 兼容协议）的地址；如果之后要换 OpenAI SDK，`baseURL` 填这个、`apiKey` 填方舟 Key 即可。通过 `ARK_BASE_URL` 可覆盖（例如走自建网关）。

### 鉴权
`Authorization: Bearer <ARK_API_KEY>`。Key 只从环境变量读取，不接受命令行参数（避免进入 shell history / `ps` 输出），不写日志。

### 模型
默认 `doubao-seed-2-0-lite-260215`，可用 `ARK_MODEL` 或 `--model` 覆盖。
- 方舟的 Model ID 必须带版本日期后缀（形如 `-260215`）；不带后缀会报 `InvalidEndpointOrModel`。**请以控制台「模型广场 → Doubao-Seed-2.0-lite → 模型 ID」处显示的字符串为准**，本文件里的后缀是我凭记忆写的，若实际版本号不同请改 `.env`。
- 也可以填推理接入点 ID（`ep-2025...`），效果等同，且支持接入点级别的限流/计费隔离。
- 直接用 Model ID 调用的前提是该模型已在「开通管理」中开通（题目已确认）。

### 关闭深度思考
请求体中传 Ark 扩展字段：
```json
"thinking": { "type": "disabled" }
```
Seed 1.6 / 2.0 系列均默认开启思考（`auto`/`enabled`），客服场景对延迟敏感、问题简单，关掉能显著降低首字延迟和 `completion_tokens`（思考内容也计费）。
- 该字段不是 OpenAI 标准字段，OpenAI 官方 SDK 需通过 `extra_body` 传；本脚本用原生 `fetch` 直接放在 body 里。
- 如果某个版本模型不接受 `thinking` 而是用 `reasoning_effort`（`"minimal"`），把 `ark-client.js` 中 `payload.thinking = ...` 那一行替换即可，其他逻辑不变。
- 即便关闭了思考，脚本仍然把 `delta.reasoning_content` 与 `delta.content` 分开处理：reasoning 默认丢弃（`--show-reasoning` 时打到 stderr），绝不会混入给用户看的回答。

### 流式输出
`stream: true`，响应为 `text/event-stream`。自己实现 SSE 解析而不是 `split('\n\n')`，原因：
- TCP 分片会把一行 JSON 切成两个 chunk，必须做行缓冲；
- 处理 `\r\n`、`: keep-alive` 注释行、多行 `data:`、无尾部空行的最后一个事件；
- 以 `data: [DONE]` 作为结束哨兵。

### 结束时打印 token 用量
`stream_options: { include_usage: true }`。方舟按 OpenAI 语义在最后一个 chunk（`choices: []`）里给出 `usage`：
```
prompt_tokens / completion_tokens / total_tokens
prompt_tokens_details.cached_tokens        （命中上下文缓存时）
completion_tokens_details.reasoning_tokens （思考 token；关思考后应为 0 或缺省）
```
脚本把这些字段、`model`、response `id`（用于工单排查）、耗时统一打印到 **stderr**，stdout 只输出回答正文，方便 `node index.js -q "..." > answer.txt` 这种管道用法。若服务端没返回 usage（网关吞掉末尾 chunk / 不支持 include_usage），会明确提示而不是静默。

## 防住的坑

1. **SSE 半行拆包** —— 行缓冲 + `TextDecoder({stream:true})`，避免 `JSON.parse` 偶发失败。
2. **`[DONE]` 与流内错误** —— `[DONE]` 直接结束；流里出现 `{"error":{...}}`（HTTP 200 但业务错）抛 `ArkApiError`。
3. **非流式响应伪装** —— 若 `Content-Type` 不是 `text/event-stream`（例如网关忽略了 `stream`），读出正文报错，而不是解析出一堆乱码。
4. **超时** —— `AbortController` 覆盖「连接 + 整条流」；默认 60s，`ARK_TIMEOUT_MS` 可调。Ctrl-C 也走同一个 abort。
5. **重试** —— 仅对 429/5xx/网络错误且**尚未收到任何字节**时重试（最多 2 次，指数退避，尊重 `Retry-After`）。流已开始就不重试，避免重复输出。
6. **finish_reason 检查** —— `length` 时警告可能被 `max_tokens=1024` 截断；`content_filter` 等也会显示。
7. **思考内容泄露** —— `reasoning_content` 独立通道，永不进入 answer/历史。
8. **上下文无限增长** —— 多轮模式只保留最近 10 轮（system 永远保留），防止 prompt_tokens 越聊越贵/超长。
9. **错误提示可操作** —— 401 → 检查 Key；404/`ModelNotOpen`/`InvalidEndpointOrModel` → 模型未开通或 ID 写错；429 → 限流。同时打印 request id 便于提工单。
10. **客服 system prompt 安全约束** —— 限定业务范围、不编造、不索取敏感信息、无法处理时转人工。

## 未验证事项（本次无 API Key，未发起真实请求）

- `doubao-seed-2-0-lite-260215` 的版本后缀请与控制台核对。
- 方舟对 Seed 2.0 是否仍接受 `thinking.type=disabled`（1.6 系列确认支持）；如报参数错误，改用 `reasoning_effort`。
- 错误响应 header 中 request id 的具体键名（脚本同时尝试 `x-request-id` 与 `x-client-request-id`，并优先用流首个 chunk 的 `id`）。

## 快速自测（拿到 Key 后）

```bash
export ARK_API_KEY=...
node index.js -q "我昨天下的订单还没发货，怎么查物流？"
# stdout: 流式回答；stderr: --- Token 用量 --- 区块
```
