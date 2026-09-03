已写好 `main.py`，用 `requests` 直接调 HTTP，完整跑通「提问 → 模型发起 tool call → 本地执行 `get_current_time` → 以 `role="tool"` 回传 → 打印最终回答」的闭环。

## 运行方式

```bash
pip install requests          # 仅此一个第三方依赖；zoneinfo 是 Python 3.9+ 标准库
export GLM_KEY="你的 GLM Coding Plan API Key"
python3 main.py
```

预期输出类似：

```
[用户] 现在东京几点了？
[工具调用] get_current_time({"timezone": "Asia/Tokyo"})
[工具结果] {"timezone": "Asia/Tokyo", "datetime": "2026-09-03 18:42:10", "utc_offset": "+0900", "weekday": "Thursday"}
[模型] 现在东京时间是 2026 年 9 月 3 日 18:42（周四，UTC+9）。
```

## 几个针对 Coding Plan 的关键点（写错就跑不通）

1. **Base URL 必须是套餐专用端点**：`https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`，比标准端点多一层 `/coding`。套餐 Key 打到标准的 `…/api/paas/v4` 会报 **HTTP 429 + code 1113「余额不足」**——这不是要充值，是端点用错了。脚本里对 1113 做了专门的提示。
2. **不要在 Base URL 后面再拼 `/v1`**：`…/coding/paas/v4/v1/chat/completions` 会 404。
3. **模型用 `glm-5.3`**（套餐内可用的是 `glm-5.3` / `glm-5.3-flash`），鉴权是 `Authorization: Bearer <GLM_KEY>`。
4. **请求体字段与标准 API 完全一致**：`tools`（`type: function`，`name/description/parameters` 均必填）、`tool_choice: "auto"`（智谱目前只支持 `auto`，不支持强制指定函数）。
5. **消息顺序**：必须先把模型返回的 `assistant` 消息（含 `tool_calls`）原样加回 `messages`，再紧跟对应的 `tool` 消息（`tool_call_id` 指回 `tool_calls[].id`），再发第二次请求。
6. **Coding 端点默认开启 Preserved Thinking**：脚本把返回的 `reasoning_content` 原样带回历史，保持多轮推理连贯（标准端点默认不带，这是两端点的差异之一）。
7. 脚本支持一次响应里多个 `tool_calls`（逐个执行、各回传一条 `tool` 消息），并做了最多 5 轮的循环上限、`finish_reason` 异常检查、未知时区/未知工具的兜底。

## 提醒

官方条款写明 GLM Coding Plan「仅限在官方支持的指定工具与产品环境中使用」（Claude Code、OpenCode、Kilo Code 等）。自己写脚本直接调 Coding 端点在技术上能通（已有实测，函数调用 `tool_calls` 正常返回），但属于条款之外的用法，是否消耗套餐额度、是否会被限制以官方为准；生产系统建议用标准 API Key 走 `…/api/paas/v4`（只需改 `BASE_URL` 一行）。
