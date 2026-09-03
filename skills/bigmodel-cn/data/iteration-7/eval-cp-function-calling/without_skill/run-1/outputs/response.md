# GLM Coding Plan Function Calling 示例(requests 直连 HTTP)

脚本已保存为 `main.py`,直接运行即可:

```bash
pip install requests          # Python 3.9+ 自带 zoneinfo,无需额外依赖
export GLM_KEY=你的key
python3 main.py
```

预期输出类似:

```
[user] 现在东京几点了?
[tool] get_current_time({"timezone": "Asia/Tokyo"}) -> {"timezone": "Asia/Tokyo", "datetime": "2026-09-03 20:01:52", "utc_offset": "+0900", "weekday": "Thursday"}

[assistant] 现在东京时间是 2026 年 9 月 3 日(星期四)20:01。
```

## 脚本要点

1. **Endpoint / 鉴权**
   - Coding Plan 专用地址:`https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`
   - 请求头 `Authorization: Bearer $GLM_KEY`,请求体为 OpenAI 兼容的 chat/completions 格式
   - 如果你的 Key 是普通开放平台 Key,设置 `GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4` 即可切换;模型名可用 `GLM_MODEL` 覆盖(默认 `glm-5.3`)

2. **工具定义**:`tools=[{"type":"function","function":{name, description, parameters(JSON Schema)}}]`,并设置 `tool_choice="auto"`

3. **本地实现**:`get_current_time(timezone)` 用标准库 `zoneinfo.ZoneInfo` 计算指定 IANA 时区(如 `Asia/Tokyo`)的当前时间,返回 dict,非法时区返回 `{"error": ...}`

4. **Tool call 回路**
   - 第一次请求后检查 `choices[0].message.tool_calls`
   - 把模型的 assistant 消息(含 `tool_calls`)原样追加到 `messages`
   - 对每个 tool call:`json.loads(function.arguments)` 解析参数 -> 调用本地函数 -> 追加 `{"role":"tool","tool_call_id":<id>,"content":<JSON 字符串>}`
   - 再次请求,直到模型不再返回 `tool_calls`,打印 `message.content` 作为最终回答
   - 循环上限 5 轮,防止死循环

5. **错误处理**:缺少 `GLM_KEY` 直接提示退出;HTTP 非 200 或响应含 `error` 字段时抛出异常并打印原始返回,方便排查(例如 Key 无效、模型名不可用、endpoint 与套餐不匹配)。

## 如果跑不通的排查方向

- 401/403:确认 Key 属于 Coding Plan;若是普通开放平台 Key,改用 `GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4`
- 模型不存在:用 `GLM_MODEL` 换成套餐内可用的模型名(如 `glm-4.7`、`glm-5` 等)
- 网络超时:脚本 `timeout=60`,可按需调大
