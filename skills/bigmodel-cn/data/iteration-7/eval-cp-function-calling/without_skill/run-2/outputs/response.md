已写好 `main.py`，用 `requests` 直接调智谱 HTTP 接口完成一次完整的 function calling 闭环。

## 运行方式

```bash
pip install requests          # zoneinfo 是 Python 3.9+ 标准库，无需额外安装
export GLM_KEY=你的智谱APIKey
python3 main.py
```

预期输出类似：

```
[user] 现在东京几点了？
[tool] get_current_time({'timezone': 'Asia/Tokyo'}) -> {"timezone": "Asia/Tokyo", "datetime": "2026-09-03 15:42:10", "utc_offset": "+0900", "weekday": "Thursday"}

[assistant] 现在东京时间是 2026 年 9 月 3 日 15:42（UTC+9）。
```

## 脚本要点

1. **端点**：Coding Plan 用专属地址 `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`（与普通 API 的 `/api/paas/v4` 不同，Coding Plan 的 Key 只能走这个前缀）。如需切换，可设环境变量 `GLM_BASE_URL`；模型名默认 `glm-5.3`，可用 `GLM_MODEL` 覆盖。
2. **鉴权**：`Authorization: Bearer $GLM_KEY`。
3. **工具定义**：`tools` 字段用 OpenAI 兼容的 `{"type": "function", "function": {...}}` 结构，`tool_choice: "auto"`。
4. **本地工具**：`get_current_time(timezone)` 用 `zoneinfo.ZoneInfo` 按 IANA 时区（如 `Asia/Tokyo`）计算当前时间，返回 JSON 字符串；时区非法时返回带 `error` 的 JSON，让模型能自行纠正。
5. **闭环逻辑**：
   - 第一次请求带 `tools` 发送问题；
   - 若返回的 `message.tool_calls` 非空，把这条 assistant 消息（含 `tool_calls`）原样 append 到 `messages`；
   - 逐个解析 `function.arguments`（JSON 字符串）执行本地函数，把结果以 `{"role": "tool", "tool_call_id": ..., "content": ...}` 回传；
   - 再次请求，直到模型不再发起 tool call，打印最终 `content`。
   - 循环上限 5 轮，防止死循环。
6. **错误处理**：非 200 时把响应体打印到 stderr 再抛错，便于排查 Key/额度/模型名问题；缺少 `GLM_KEY` 时直接提示退出。

## 完整代码

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

import requests

BASE_URL = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
CHAT_URL = f"{BASE_URL.rstrip('/')}/chat/completions"
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")


def get_current_time(timezone: str = "UTC") -> str:
    """返回指定 IANA 时区的当前时间（本地计算）。"""
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        return json.dumps({"error": f"unknown timezone: {timezone}",
                           "hint": "use IANA name like Asia/Tokyo"}, ensure_ascii=False)
    now = datetime.now(dt_timezone.utc).astimezone(tz)
    return json.dumps({
        "timezone": timezone,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc_offset": now.strftime("%z"),
        "weekday": now.strftime("%A"),
    }, ensure_ascii=False)


TOOL_REGISTRY = {"get_current_time": get_current_time}

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "获取指定时区的当前日期和时间。",
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string",
                             "description": "IANA 时区名称，例如 Asia/Tokyo、Asia/Shanghai、America/New_York"}
            },
            "required": ["timezone"],
        },
    },
}]


def chat(messages, api_key, tools=None):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": messages, "temperature": 0.1}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        print(f"[HTTP {resp.status_code}] {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    data = resp.json()
    if "choices" not in data:
        raise RuntimeError(f"unexpected response: {json.dumps(data, ensure_ascii=False)}")
    return data["choices"][0]["message"]


def run_tool_call(tool_call):
    fn_name = tool_call["function"]["name"]
    raw_args = tool_call["function"].get("arguments") or "{}"
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except json.JSONDecodeError:
        args = {}
    fn = TOOL_REGISTRY.get(fn_name)
    result = fn(**args) if fn else json.dumps({"error": f"unknown tool: {fn_name}"}, ensure_ascii=False)
    print(f"[tool] {fn_name}({args}) -> {result}")
    return {"role": "tool", "tool_call_id": tool_call["id"], "content": result}


def main():
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("请先设置环境变量 GLM_KEY（智谱 API Key）", file=sys.stderr)
        sys.exit(1)

    question = "现在东京几点了？"
    messages = [
        {"role": "system", "content": "你是一个乐于助人的助手。需要知道当前时间时，请调用工具而不是猜测。"},
        {"role": "user", "content": question},
    ]
    print(f"[user] {question}")

    for _ in range(5):
        msg = chat(messages, api_key, tools=TOOLS)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            print(f"\n[assistant] {msg.get('content', '')}")
            return
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            messages.append(run_tool_call(tc))

    print("[warn] 超过最大工具调用轮数，退出。", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
```

## 可能遇到的问题

- **401 / 鉴权失败**：确认 `GLM_KEY` 是 Coding Plan 的 Key，且请求的是 `/api/coding/paas/v4` 前缀；用普通 Key 或走错前缀都会失败。
- **模型名不存在**：如果 `glm-5.3` 在你的套餐里不可用，改 `GLM_MODEL=glm-4.7`（或其他套餐内可用模型）即可，其余代码不变。
- **`zoneinfo` 找不到时区数据**（少数精简系统）：`pip install tzdata`。
