"""火山方舟 Agent Plan（个人版 Medium）—— Anthropic 协议入口模型锁定脚本。

用 Anthropic 兼容协议（即 Claude Code 走的那个入口）发一次对话请求，
并核对「实际服务的模型」确实是 doubao-seed-2.0-lite（AFP 抵扣系数 0.5）。

用法：
    export ARK_AGENT_PLAN_API_KEY=<Agent Plan 专属 API Key>
    python3 main.py

要点（均来自 2026-09-04 对该入口的真实 API 验证）：
- Agent Plan 的 Anthropic 协议 Base URL 是 https://ark.cn-beijing.volces.com/api/plan，
  Messages 全路径 POST /api/plan/v1/messages。不能打 /api/v3（后付费入口，专属 Key 打过去是 401），
  也不能打 /api/coding（那是 Coding Plan）。
- 鉴权头 `Authorization: Bearer <Key>` 与 `x-api-key: <Key>` 都接受，需带 anthropic-version。
- model 必须显式填小写 Model Name（点号分隔）。绝对不能留空或填 claude-*：
  该入口会把 claude-* 静默路由到 doubao-seed-2.1-turbo（系数 2.5），不报错但多烧 5 倍 AFP；
  也不能填 auto（404）。
- Plan 入口会把 Model Name 解析成带日期的版本返回：请求 doubao-seed-2.0-lite，
  响应 model 是 doubao-seed-2-0-lite-260215（点变连字符 + 日期后缀，版本随平台升级会漂移）。
  因此核对规则是「系列匹配」：等于模型名本身，或 模型名（点->连字符）+ '-' + 6~8 位日期。
"""

import os
import re
import sys

import requests

ANTHROPIC_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan"
MESSAGES_URL = ANTHROPIC_BASE_URL + "/v1/messages"

# 必须显式指定的 Model Name：doubao-seed-2.0-lite（Agent Plan 全档可用，系数 0.5/0.5）
REQUESTED_MODEL = "doubao-seed-2.0-lite"


def served_model_matches(requested: str, served: str) -> bool:
    """判断服务端实际返回的模型是否就是请求的那个系列。

    Plan 入口的响应 model 字段是解析后的带日期版本号（点号会换成连字符），
    例如 doubao-seed-2.0-lite -> doubao-seed-2-0-lite-260215。
    日期后缀长度不固定（6~8 位），且会随平台升级漂移，所以只锁「模型系列」：
    允许 served 等于 requested 本身，或 等于 requested（点->连字符）+"-"+日期。
    其余任何值（如 doubao-seed-2-1-turbo-260628、auto、glm-5.3）都算不一致。
    """
    if not served:
        return False
    bases = {re.escape(requested), re.escape(requested.replace(".", "-"))}
    pattern = "(?:" + "|".join(sorted(bases)) + r")(-\d{6,8})?"
    return re.fullmatch(pattern, served) is not None


def main() -> None:
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未设置环境变量 ARK_AGENT_PLAN_API_KEY。\n"
            "请在 Agent Plan 控制台「使用配置 → 配置专属API Key」获取专属 Key"
            "（它与方舟 API Key / Coding Plan Key 不通用）。",
            file=sys.stderr,
        )
        sys.exit(2)

    headers = {
        "Authorization": f"Bearer {api_key}",  # 实测 Bearer 与 x-api-key 两种头都接受
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": REQUESTED_MODEL,
        "max_tokens": 1024,  # Anthropic 协议必填；一句话回答绰绰有余
        "thinking": {"type": "disabled"},  # lite 默认开思考；关掉省输出 token（实测该入口+该模型支持 disabled）
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
    }

    print(f"Endpoint: {MESSAGES_URL}")
    print(f"我请求的模型: {REQUESTED_MODEL}")
    try:
        resp = requests.post(MESSAGES_URL, headers=headers, json=payload, timeout=120)
    except requests.RequestException as exc:
        print(f"请求异常：{exc}", file=sys.stderr)
        sys.exit(2)

    if resp.status_code != 200:
        # 常见错误：401 = Key/Base URL 不配对（专属 Key 只在 /api/plan* 有效）；
        # 404 UnsupportedModel = model 填了套餐外名字或 auto。
        print(f"请求失败：HTTP {resp.status_code}\n{resp.text}", file=sys.stderr)
        sys.exit(2)

    data = resp.json()
    served_model = data.get("model", "")
    answer = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    )
    usage = data.get("usage", {})

    print()
    print(f"回答: {answer}")
    if usage:
        print(
            f"用量: input_tokens={usage.get('input_tokens')}, "
            f"output_tokens={usage.get('output_tokens')}"
        )
    print()
    print("=" * 64)
    print(f"我请求的模型:         {REQUESTED_MODEL}")
    print(f"服务端实际返回的模型: {served_model}")
    print("=" * 64)

    if served_model_matches(REQUESTED_MODEL, served_model):
        print("[OK] 模型核对通过：实际服务的确实是 doubao-seed-2.0-lite 系列（AFP 系数 0.5）。")
    else:
        print(
            "[ALERT] ⚠️⚠️⚠️ 模型不一致报警 ⚠️⚠️⚠️\n"
            f"  期望: {REQUESTED_MODEL}（或其带日期版本，如 doubao-seed-2-0-lite-260215）\n"
            f"  实际: {served_model or '<响应中无 model 字段>'}\n"
            "  本次请求没有按预期的低成本模型（系数 0.5）服务，AFP 可能按更高系数抵扣！\n"
            "  提示：若实际是 doubao-seed-2-1-turbo-*，多半是模型名被静默路由"
            "（该入口会把 claude-* / 未知名换成 2.1-turbo，系数 2.5）；\n"
            "  若实际是 auto，说明走到了 ark-code-latest 路由。请核对请求里的 model 字段。",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
