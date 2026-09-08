"""用智谱 GLM 给商品评论做一句话摘要（每条回复 token 预算 <= 32）。

关键设计说明（为什么这样写）：

1. 模型选 glm-4-flash-250414（免费）。两个原因：
   - 成本：评论量大，免费模型把单条成本压到零；
   - 预算：它是 GLM-4 系列，不支持 thinking 参数、不产生思维链，max_tokens=32
     全部留给摘要正文。若用 glm-5.3/glm-4.7 这类强制思考的模型（glm-5.3 在标准
     端点传 thinking:disabled 会直接报 1210），思维链 token 会计入
     completion_tokens，32 个 token 可能在正文生成前就被烧光，content 返回空
     字符串、finish_reason=length——这是小 token 预算下最容易踩的坑。
2. max_tokens 只限制生成内容、不含输入（官方文档确认），逐条评论单独请求，
   用响应里的 usage.completion_tokens 逐条核对预算。
3. 拿不到摘要文本时，明确报告原因（HTTP 状态/业务错误码/finish_reason/usage），
   绝不打印一个空字符串还说完成了。
"""

import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4-flash-250414"  # 免费模型；GLM-4 系列无思维链，不要传 thinking 参数
MAX_TOKENS = 32  # 每条回复的 token 硬预算
MAX_ATTEMPTS = 3  # 仅对网络异常 / 429 / 5xx 退避重试

SYSTEM_PROMPT = (
    "你是商品评论摘要助手。用一句不超过20个字的中文概括评论的核心观点（含优缺点），"
    "直接输出摘要正文，不要解释、不要引号、不要任何前后缀。"
)

REVIEWS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]


def describe_api_error(resp: requests.Response) -> str:
    """把非 200 响应整理成可读原因，优先解析智谱业务错误体 {"error":{"code","message"}}。"""
    try:
        err = (resp.json() or {}).get("error") or {}
    except ValueError:
        return f"HTTP {resp.status_code}，响应体不是 JSON: {resp.text[:200]!r}"
    code = err.get("code", "未知")
    message = err.get("message", "无错误信息")
    return f"HTTP {resp.status_code}，业务错误码 {code}: {message}"


def summarize_review(api_key: str, review: str) -> dict:
    """对单条评论调用 GLM 做摘要。

    返回 dict：
      成功 -> {"ok": True, "summary": ..., "finish_reason": ..., "completion_tokens": ..., "warning": ...}
      失败 -> {"ok": False, "reason": 具体原因}
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},  # 固定 system 前缀，利于上下文缓存命中
            {"role": "user", "content": review},
        ],
        "max_tokens": MAX_TOKENS,  # 硬预算：只限生成侧，不含输入
        "temperature": 0.3,  # 摘要要稳定；不动 top_p，避免两参数同时精细调整
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_reason = "未知错误"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            last_reason = f"网络异常: {exc!r}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 ** (attempt - 1))
            continue

        if resp.status_code != 200:
            last_reason = describe_api_error(resp)
            # 只有 429（限流/平台过载）和 5xx 值得退避重试；4xx 是配置/参数问题，重试无意义
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < MAX_ATTEMPTS:
                    time.sleep(2 ** (attempt - 1))
                continue
            return {"ok": False, "reason": last_reason}

        try:
            data = resp.json()
        except ValueError:
            return {"ok": False, "reason": f"HTTP 200 但响应体不是 JSON: {resp.text[:200]!r}"}

        choices = data.get("choices") or []
        if not choices:
            return {"ok": False, "reason": f"HTTP 200 但响应缺少 choices，原始响应: {data}"}

        choice = choices[0]
        message = choice.get("message") or {}
        content = (message.get("content") or "").strip()
        finish_reason = choice.get("finish_reason")
        usage = data.get("usage") or {}
        completion_tokens = usage.get("completion_tokens")

        if not content:
            # 关键兜底：拿不到文本必须说清原因，绝不打印空字符串充数
            hint = ""
            if finish_reason == "length":
                hint = (
                    f"（finish_reason=length：{MAX_TOKENS} 个 token 预算在生成正文之前就被耗尽，"
                    "通常是思考类模型的思维链占满了 completion_tokens；"
                    "请换无思维链的模型或调大 max_tokens）"
                )
            elif finish_reason == "sensitive":
                hint = "（finish_reason=sensitive：内容被安全策略拦截）"
            elif finish_reason == "network_error":
                hint = "（finish_reason=network_error：模型推理异常）"
            return {
                "ok": False,
                "reason": (
                    f"模型未返回任何摘要文本，finish_reason={finish_reason!r}，"
                    f"completion_tokens={completion_tokens}，"
                    f"reasoning_content={'有' if message.get('reasoning_content') else '无'} {hint}"
                ),
            }

        warning = ""
        if finish_reason == "length":
            warning = "注意：finish_reason=length，摘要在预算内被截断"
        if completion_tokens is not None and completion_tokens > MAX_TOKENS:
            warning += f"注意：completion_tokens={completion_tokens} 超出 {MAX_TOKENS} 预算"
        return {
            "ok": True,
            "summary": content,
            "finish_reason": finish_reason,
            "completion_tokens": completion_tokens,
            "warning": warning,
        }

    return {"ok": False, "reason": f"重试 {MAX_ATTEMPTS} 次后仍失败，最后原因: {last_reason}"}


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：环境变量 ZHIPUAI_API_KEY 未设置，无法调用智谱 API。", file=sys.stderr)
        print("请先执行: export ZHIPUAI_API_KEY=<你的 API Key>", file=sys.stderr)
        return 1

    print(f"模型: {MODEL} | 每条回复 token 预算: {MAX_TOKENS}\n")
    failures = 0
    for i, review in enumerate(REVIEWS, 1):
        result = summarize_review(api_key, review)
        print(f"[{i}] 原评论: {review}")
        if not result["ok"]:
            failures += 1
            print(f"    ✗ 未取得摘要——原因: {result['reason']}\n")
            continue
        tokens = result["completion_tokens"]
        token_line = f"    tokens: {tokens if tokens is not None else '未知'} / {MAX_TOKENS}"
        if result["warning"]:
            token_line += f"（{result['warning']}）"
        print(f"    摘要: {result['summary']}")
        print(token_line + "\n")

    total = len(REVIEWS)
    if failures:
        print(f"完成：{total - failures}/{total} 条成功，{failures} 条失败，失败原因见上方输出。")
        return 1
    print(f"完成：{total}/{total} 条评论全部取得摘要，每条回复均在 {MAX_TOKENS} token 预算内。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
