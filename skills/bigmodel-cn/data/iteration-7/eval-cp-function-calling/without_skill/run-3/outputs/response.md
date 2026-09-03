已写好 `main.py`，用 `requests` 直接调智谱 OpenAI 兼容的 `chat/completions` 接口完成一次完整的 function calling 闭环。

## 运行方式

```bash
pip install requests
export GLM_KEY="你的 Coding Plan API Key"
python3 main.py
```

预期输出类似：

```
[tool call] get_current_time({'timezone': 'Asia/Tokyo'})
[tool result] {"timezone": "Asia/Tokyo", "datetime": "2026-09-03 15:42:10", "utc_offset": "+0900", "weekday": "Thursday"}

=== 模型最终回答 ===
现在东京时间是 2026 年 9 月 3 日 15:42（UTC+9）。
```

## 脚本要点

1. **端点**：默认使用 GLM Coding Plan 专属地址 `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`。如果你的 Key 是普通按量付费 Key（或报 401/1113 之类的权限错误），用 `GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4` 覆盖即可；模型名也可用 `GLM_MODEL` 覆盖，默认 `glm-5.3`。
2. **鉴权**：`Authorization: Bearer $GLM_KEY`。
3. **本地工具** `get_current_time(timezone)`：用标准库 `zoneinfo` 按 IANA 时区名（如 `Asia/Tokyo`）取当前时间，返回 JSON 字符串；时区名非法时返回 error 字段而不是抛异常。
4. **工具声明**：OpenAI 风格的 `tools=[{"type":"function","function":{name, description, parameters(JSON Schema)}}]`，`tool_choice="auto"`。
5. **调用循环**：
   - 第一次请求带上 system + user 消息；
   - 若返回的 `message.tool_calls` 非空，把这条 assistant 消息（含 `tool_calls`）原样追加到上下文，逐个解析 `function.arguments`（JSON 字符串）并执行本地函数；
   - 每个结果以 `{"role":"tool","tool_call_id":<id>,"content":<结果>}` 追加回 messages，再次请求；
   - 直到模型返回不含 `tool_calls` 的纯文本，打印为最终回答。最多循环 5 轮以防死循环。
6. **错误处理**：缺少 `GLM_KEY`、HTTP 非 200、响应体带 `error` 时打印原因并以非零码退出，方便排查。

依赖只有 `requests`（Python 3.9+ 自带 `zoneinfo`）。
