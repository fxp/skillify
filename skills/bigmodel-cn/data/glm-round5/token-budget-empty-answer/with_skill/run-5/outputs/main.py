#!/usr/bin/env python3
"""用智谱 GLM 给商品评论做一句话摘要，每条回复的 token 预算硬性控制在 32 以内。

为什么不能只设 max_tokens=32 了事：
GLM 新系列是混合思考模型，思考(reasoning) token 会优先消耗 max_tokens 配额。
对着默认开思考的模型把 max_tokens 设成 32，思维链会先把预算烧光，返回
content="" 且 finish_reason="length"——HTTP 层面看起来"成功"，实际一个字的
摘要都没拿到。

因此本脚本做了三件事：
1. 默认用可关闭思考的免费模型 glm-4.5-flash，并显式传
   thinking={"type": "disabled"}，让 32 的预算全部留给摘要正文
   （若指定 glm-5.3——它在标准端点关不掉思考——则改传 reasoning_effort="low"）；
2. 逐条校验 finish_reason 与 content：拿不到摘要就带着原因明确报错，
   绝不打印空字符串冒充完成；
3. 只对限流/过载/5xx/网络错误做指数退避重试，配置类 4xx 直接报错不重试。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py                     # 默认 glm-4.5-flash
    GLM_MODEL=glm-4.6 python3 main.py   # 换模型

退出码：0 全部成功；1 有失败项；2 未配置 API Key。
评论量再上一个量级时建议改走 Batch API（不占同步并发额度），这里保持顺序同步调用。
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4.5-flash"  # 免费、128K 上下文、支持关闭思考，适合大批量低成本摘要
MAX_TOKENS = 32                  # 每条回复的 token 预算上限（思考也计入，所以必须关思考）
MAX_ATTEMPTS = 3                 # 含首次调用，仅对限流/过载/5xx/网络错误重试
RETRYABLE_CODES = {"1302", "1305", "1308", "1310"}  # 限流/平台过载/用量上限
ERROR_ADVICE = {
    "1000": "检查 ZHIPUAI_API_KEY 是否正确",
    "1001": "请求缺少 Authorization 头",
    "1003": "API Key 已过期或无效",
    "1113": "标准端点余额不足（若用的是 GLM Coding Plan 套餐 Key，它不能打标准端点）",
    "1210": "请求参数非法（例如给强制思考的 glm-5.3 传 thinking.type=disabled）",
    "1211": "模型名不存在，检查 model 拼写",
    "1301": "输入内容触发内容安全策略",
}

REVIEWS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]

SYSTEM_PROMPT = (
    "你是商品评论摘要助手。把用户给的评论压缩成一句不超过20个字的中文摘要，"
    "优点和缺点都要保留；直接输出摘要本身，不要引号、序号或任何解释。"
)


class SummaryError(Exception):
    """单条摘要失败，message 是可以直接给用户看的原因。"""


def thinking_control(model: str) -> dict:
    """按模型返回防思考参数：思考 token 会计入 max_tokens，必须先把它挤出去。"""
    m = model.lower()
    if m.startswith("glm-5.3"):
        # glm-5.3/5.3-flash 在标准端点强制思考，传 disabled 会报 1210；
        # reasoning_effort="low" 实测 reasoning_tokens=0，等价于不思考
        return {"reasoning_effort": "low"}
    if m.startswith(("glm-5.2", "glm-5.1", "glm-5", "glm-4.7", "glm-4.6", "glm-4.5")):
        # 这些系列支持显式关闭思考
        return {"thinking": {"type": "disabled"}}
    # GLM-4.5 以下不支持 thinking 参数，传了可能报 1210，不传（它们本来也不思考）
    return {}


def parse_error(resp: requests.Response) -> tuple:
    """从错误响应里取业务错误码和消息，错误体格式：{"error":{"code":..,"message":..}}"""
    try:
        err = (resp.json() or {}).get("error") or {}
    except ValueError:
        err = {}
    return str(err.get("code", "?")), str(err.get("message") or resp.text[:200])


def truncate_json(data: dict, limit: int = 300) -> str:
    text = json.dumps(data, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


def validate_summary(data: dict) -> dict:
    """校验响应真的拿到了摘要正文；拿不到时抛出带具体原因的错误。"""
    choices = data.get("choices") or []
    if not choices:
        raise SummaryError(f"响应中没有 choices 字段：{truncate_json(data)}")
    choice = choices[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    has_reasoning = bool((message.get("reasoning_content") or "").strip()) or bool(reasoning_tokens)

    if content and finish_reason in (None, "stop"):
        return {"summary": content, "usage": usage}

    if finish_reason == "length":
        if not content and has_reasoning:
            raise SummaryError(
                f"max_tokens={MAX_TOKENS} 的预算全部被思考链消耗"
                f"（reasoning_tokens={reasoning_tokens or '未知'}，正文 0 字），"
                f"模型没来得及输出任何摘要。请改用可关闭思考的模型（如 {DEFAULT_MODEL}）"
                f"或调大预算"
            )
        raise SummaryError(
            f"输出在 max_tokens={MAX_TOKENS} 处被截断（finish_reason=length），"
            f"正文只有 {len(content)} 字，不完整故不采用；可精简提示词或调大预算"
        )
    if finish_reason == "sensitive":
        raise SummaryError("触发内容安全策略，生成被拦截（finish_reason=sensitive）")
    if finish_reason == "stop":
        detail = "正文被写进了 reasoning_content" if has_reasoning else "content 为空"
        raise SummaryError(f"模型正常结束但{detail}（finish_reason=stop），拿不到摘要")
    raise SummaryError(f"异常结束：finish_reason={finish_reason!r}，content={content!r}")


def summarize(api_key: str, model: str, review: str) -> dict:
    """调用 GLM 摘要一条评论，成功返回 {"summary", "usage"}，失败抛 SummaryError。"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": review},
        ],
        "max_tokens": MAX_TOKENS,
    }
    payload.update(thinking_control(model))

    last_error = "请求未发出"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=60,
            )
        except requests.RequestException as exc:
            last_error = f"网络错误：{exc}"
            retryable = True
        else:
            if resp.status_code == 200:
                return validate_summary(resp.json())
            code, message = parse_error(resp)
            last_error = f"HTTP {resp.status_code}，业务错误码 {code}：{message}"
            if code in ERROR_ADVICE:
                last_error += f"（{ERROR_ADVICE[code]}）"
            if (
                code == "1210"
                and "thinking" in payload
                and ("思考" in message or "thinking" in message.lower())
            ):
                # 该模型不吃 thinking 参数（如强制思考型号）：去掉后立即重试，
                # 让校验阶段去暴露"预算被思考吃光"的真实问题
                payload.pop("thinking")
                continue
            retryable = resp.status_code >= 500 or (
                resp.status_code == 429 and code in RETRYABLE_CODES
            )
        if retryable and attempt < MAX_ATTEMPTS:
            time.sleep(2 ** (attempt - 1))  # 1s、2s 指数退避
            continue
        break
    raise SummaryError(last_error)


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱 API。", file=sys.stderr)
        print("请先执行：export ZHIPUAI_API_KEY=<你的API Key>", file=sys.stderr)
        return 2

    model = os.environ.get("GLM_MODEL", "").strip() or DEFAULT_MODEL
    print(f"模型：{model}；每条回复 token 预算：{MAX_TOKENS}\n")

    succeeded = 0
    for index, review in enumerate(REVIEWS, 1):
        print(f"[{index}/{len(REVIEWS)}] 评论：{review}")
        try:
            result = summarize(api_key, model, review)
        except SummaryError as exc:
            print(f"      ✗ 摘要获取失败：{exc}\n")
            continue
        usage = result["usage"]
        print(f"      ✓ 摘要：{result['summary']}")
        print(
            f"      用量：completion {usage.get('completion_tokens', '?')}/{MAX_TOKENS}"
            f" tokens，prompt {usage.get('prompt_tokens', '?')} tokens\n"
        )
        succeeded += 1

    if succeeded == len(REVIEWS):
        print(f"完成：{succeeded}/{len(REVIEWS)} 条评论全部拿到摘要。")
        return 0
    print(
        f"未完成：仅 {succeeded}/{len(REVIEWS)} 条成功，失败原因见上；"
        "未拿到摘要的条目不会输出占位文本。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
