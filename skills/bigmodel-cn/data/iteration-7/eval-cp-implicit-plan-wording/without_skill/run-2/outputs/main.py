#!/usr/bin/env python3
"""用 requests 直接调用智谱 GLM Coding Plan（编程套餐）的 HTTP 接口。

注意：编程套餐（包月、按 5 小时额度）和普通按量付费 API 走的是不同的接口地址：
  - 按量付费:  https://open.bigmodel.cn/api/paas/v4/chat/completions
  - 编程套餐:  https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
用套餐的 Key 去调按量付费地址，通常会报 "余额不足 / 无权限" 之类的错误，
所以这里默认使用 coding 地址。可通过环境变量 ZHIPU_BASE_URL 覆盖。

运行：
  export ZHIPU_API_KEY="你的key"
  python3 main.py
"""

import json
import os
import sys

import requests

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = os.environ.get("ZHIPU_MODEL", "glm-5.3")
PROMPT = "用一句话介绍 Rust"


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 ZHIPU_API_KEY", file=sys.stderr)
        print('请先执行：export ZHIPU_API_KEY="你的key"', file=sys.stderr)
        return 1

    base_url = os.environ.get("ZHIPU_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": PROMPT},
        ],
        # 关闭深度思考，避免回答被塞进 reasoning 字段、content 为空
        "thinking": {"type": "disabled"},
        "stream": False,
        "temperature": 0.7,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    try:
        data = resp.json()
    except ValueError:
        print(f"HTTP {resp.status_code}，返回不是 JSON：{resp.text[:500]}", file=sys.stderr)
        return 1

    if resp.status_code != 200 or "error" in data:
        print(f"接口返回错误（HTTP {resp.status_code}）：", file=sys.stderr)
        print(json.dumps(data, ensure_ascii=False, indent=2), file=sys.stderr)
        if base_url == DEFAULT_BASE_URL:
            print(
                "\n提示：如果是 1113/1211 之类的余额或权限错误，请确认这个 Key 属于"
                "编程套餐；如果你实际用的是按量付费 Key，可设置\n"
                '  export ZHIPU_BASE_URL="https://open.bigmodel.cn/api/paas/v4"',
                file=sys.stderr,
            )
        return 1

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        print("返回结构异常：", json.dumps(data, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    content = (message.get("content") or "").strip()
    if not content:
        # 部分推理模型会把内容放在 reasoning_content 里，兜底一下
        content = (message.get("reasoning_content") or "").strip()

    print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
