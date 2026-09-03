# GLM Coding Plan + requests 的 Function Calling 示例

脚本已保存为 `main.py`，直接运行：

```bash
export GLM_KEY="你的 GLM Coding Plan API Key"
python3 main.py
```

预期输出类似：

```
[tool] get_current_time({"timezone": "Asia/Tokyo"}) -> {"timezone": "Asia/Tokyo", "datetime": "2026-09-03 15:42:10", "utc_offset": "+0900", "weekday": "Thursday"}

最终回答： 现在东京时间是 2026 年 9 月 3 日 15:42（星期四）。
```

## 几个关键点（Coding Plan 与标准 API 不同，容易踩坑）

1. **Base URL 必须是 Coding 端点**：`https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`（比标准端点多了一层 `/coding`）。套餐 Key 打标准端点 `…/api/paas/v4` 会返回 `429` + `{"error":{"code":"1113","message":"余额不足或无可用资源包"}}`——这不是要你充值，是端点用错了。
2. **鉴权**：`Authorization: Bearer $GLM_KEY`，Key 从环境变量读，不硬编码。
3. **模型**：套餐内可用 `glm-5.3` / `glm-5.3-flash`；脚本用 `glm-5.3`。
4. **`tool_choice` 只支持 `"auto"`**：智谱不支持 OpenAI 那种强制指定某个函数的写法（传了不报错但被当成 auto）。
5. **多轮闭环的消息顺序**：模型返回的 `assistant` 消息（含 `tool_calls`，Coding 端点还会带 `reasoning_content`）要**原样**追加进 `messages`，紧接着追加 `role: "tool"` 消息并携带对应的 `tool_call_id`，然后再请求一次拿最终回答。脚本用一个小循环处理，兼容模型连续调用多次工具或一次返回多个 `tool_calls`。
6. **判断是否需要执行工具**看 `message.tool_calls` 是否非空，而不是看 `content` 是否为空（tool call 时 `content` 常为 `null`）。
7. `function.arguments` 是 JSON 字符串，脚本先 `json.loads` 再按函数名从注册表分发执行；时区用标准库 `zoneinfo`（Python 3.9+），无需额外依赖，只需 `pip install requests`。

## 一点提醒

官方条款写明 Coding Plan 套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code 等）。自己写脚本直连 Coding 端点技术上能跑通（已有实测），但属于条款之外的用法，是否消耗套餐额度、是否被限制以官方为准；生产系统建议改用标准 API Key + `…/api/paas/v4`（脚本只需改 `BASE_URL` 和环境变量名，请求体完全一样）。
