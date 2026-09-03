# GLM Coding Plan 函数调用示例（requests 直调 HTTP）

脚本已保存为 `main.py`。运行方式：

```bash
pip install requests
export GLM_KEY="你的 GLM Coding Plan API Key"
python3 main.py
```

预期输出类似：

```
[user] 现在东京几点了？
[tool] get_current_time({"timezone": "Asia/Tokyo"}) -> {"timezone": "Asia/Tokyo", "datetime": "2026-09-03 20:04:11", "utc_offset": "+0900", "weekday": "Thursday"}
[assistant] 现在东京时间是 2026 年 9 月 3 日 20:04（UTC+9，星期四）。
```

## 脚本要点

1. **端点必须用 Coding Plan 专用地址**  
   `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`（比标准 API 多一级 `/coding`）。套餐 Key 打标准端点 `…/api/paas/v4` 会报 HTTP 429 + `1113 余额不足`，这不是要充值，是 Base URL 错了。脚本里对 1113 做了专门提示。
2. **鉴权**：`Authorization: Bearer $GLM_KEY`，Key 只从环境变量读取。
3. **模型**：`glm-5.3`（套餐内可用的是 `glm-5.3` / `glm-5.3-flash`）。
4. **工具定义**：`tools` 数组里一个 `type: "function"`，`name` / `description` / `parameters`（JSON Schema）三者都要填；`tool_choice` 只支持 `"auto"`，不要传强制指定函数的对象写法（会被静默当成 auto）。
5. **函数调用循环**：
   - 第一轮请求 → 判断 `message.tool_calls` 是否非空（不要看 `content` 是否为空）；
   - 把 assistant 消息（含 `tool_calls`，以及 Coding 端点默认返回的 `reasoning_content`）**原样**加回 `messages`；
   - 逐个执行 `tool_calls`（`arguments` 是 JSON 字符串，先 `json.loads`），每个追加一条 `{"role":"tool","tool_call_id":<id>,"content":<JSON 字符串>}`；
   - 再次请求拿最终自然语言回答。循环最多 5 轮，防止死循环。
6. **`get_current_time(timezone)`** 用标准库 `zoneinfo` 本地实现（Python ≥ 3.9），传非法时区时返回 `{"error": ...}` 交给模型处理，而不是让脚本崩溃。

## 一点提醒

官方条款写明 Coding Plan 套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code 等）。自己写脚本直调 Coding 端点在技术上能跑通（已有实测），但属于条款之外的用法，是否扣套餐额度 / 是否被限制以官方为准；正式项目建议改用标准 API Key（Base URL 换回 `…/api/paas/v4`，其余代码不变）。
