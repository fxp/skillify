"""
高并发智谱 GLM-5.3 客服机器人调用封装（标准库 requests，无第三方 SDK 依赖）。

背景 / 关键结论（写代码前先想清楚，别按字面猜参数）：
  - GLM-5.3 / GLM-5.3-Flash 是"强制思考"模型：`thinking.type` 只接受 "enabled"，
    传 "disabled" 会直接报业务错误码 1210（"该模型始终思考，不支持关闭思考；
    请使用 low、high 或 max。"）。也就是说"关掉深度思考"这个字面需求，在 GLM-5.3
    上是做不到的——能做的是把 `reasoning_effort` 调到最低档 "low"。
  - 实测（官方技能包记录，2026-09）：同一问题下 `reasoning_effort="low"` 时
    `usage.completion_tokens_details.reasoning_tokens` 为 0，效果上已经约等于
    "不思考"；`reasoning_content` 字段在 low 档通常为空，代码里不能假设它非空。
  - 所以本脚本默认 `reasoning_effort="low"`，把思考开销压到（实测）几乎为零，
    这是在"必须用 glm-5.3"前提下能拿到的最优解。如果场景允许换模型，
    `glm-4.6`（`thinking.type` 可显式设为 disabled）或 `glm-4.5-airx` /
    `glm-4-flashx-250414`（官方标注为"高并发、低延迟"专用极速版）会是更彻底的选择，
    详见同目录 notes.md。

高并发场景下真正影响延迟和成本的，不只是思考开关，还有：
  1. max_tokens 上限（简单问答没必要留 65536 的默认值，显式设小上限）；
  2. 连接复用（同一个 requests.Session + HTTPAdapter 连接池，避免每次请求重新握手）；
  3. 并发度控制（用信号量/线程池限制同时在飞的请求数，而不是无限并发硬冲，
     官方文档明确速率限制是按并发请求数算的，不是 QPS）；
  4. 区分错误类型再重试（4xx 配置/参数错误重试没有意义，只有 429/5xx 才做指数退避）。

用法：
    export ZHIPUAI_API_KEY="你的真实 API Key"
    python support_bot.py
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Iterable, Optional

import requests
from requests.adapters import HTTPAdapter

# --------------------------------------------------------------------------
# 基础配置
# --------------------------------------------------------------------------

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
CHAT_ENDPOINT = f"{API_BASE}/chat/completions"

# 永远不要把 Key 硬编码进代码，从环境变量读取。这里用占位符名字，
# 真正跑的时候由外部 `export ZHIPUAI_API_KEY=...` 注入。
API_KEY_ENV_VAR = "ZHIPUAI_API_KEY"

# 简单问答场景下不需要模型长篇大论，显式设一个远小于默认值（65536）的上限，
# 既省 Token 成本，也让单次请求的生成阶段更快结束。
DEFAULT_MAX_TOKENS = 512

# GLM-5.3 强制思考，只能通过 reasoning_effort 调节强度：
# "low" 在实测中 reasoning_tokens=0，是目前能拿到的最低思考开销档位。
DEFAULT_REASONING_EFFORT = "low"

# 客服问答希望回答稳定、不要发散，温度调低（并非 0，保留一点自然度）。
DEFAULT_TEMPERATURE = 0.3
DEFAULT_TOP_P = 0.9

# 业务错误码分类：哪些值得退避重试，哪些是配置/参数问题重试也没用。
RETRYABLE_ERROR_CODES = {"1302", "1305", "1308", "1310"}
# 429 状态码本身也可能对应上面这些码；500/502/503/504 视为可重试的服务端错误。
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}


class SupportBotError(RuntimeError):
    """不可重试的调用错误（鉴权失败、参数错误、内容安全拦截等）。"""


class SupportBotRateLimited(RuntimeError):
    """重试耗尽后仍然被限流/服务过载。"""


@dataclass
class AnswerResult:
    question: str
    content: str
    finish_reason: Optional[str]
    reasoning_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    latency_seconds: float
    request_id: str
    error: Optional[str] = None


# --------------------------------------------------------------------------
# 客户端：连接复用 + 并发控制 + 重试
# --------------------------------------------------------------------------


class SupportBotClient:
    """封装一个可在多线程环境下复用的 GLM-5.3 客服问答客户端。

    - 用单个 requests.Session + HTTPAdapter 连接池复用 TCP/TLS 连接，
      避免高并发下每次请求都重新握手拖慢延迟。
    - 用 threading.Semaphore 限制同时在飞的请求数（并发池思路），
      不对同步接口无限制地猛发并发（官方文档明确提醒过这一点）。
    - 429/5xx 走指数退避 + 抖动重试；4xx 配置/参数错误直接抛出，不重试。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "glm-5.3",
        system_prompt: str = "你是一个简洁、准确的客服助手，只回答用户提出的问题，不要主动展开无关内容。",
        reasoning_effort: str = DEFAULT_REASONING_EFFORT,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        max_concurrency: int = 20,
        connect_timeout: float = 3.0,
        read_timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ.get(API_KEY_ENV_VAR, "")
        if not self.api_key:
            # 不在 import 时强制失败，方便脚本被别的地方 import 做单元测试；
            # 但真正发起请求前必须要有 Key。
            self.api_key = "PLACEHOLDER_API_KEY_SET_VIA_ENV"

        self.model = model
        self.system_prompt = system_prompt
        self.reasoning_effort = reasoning_effort
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = (connect_timeout, read_timeout)
        self.max_retries = max_retries

        self._session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=max_concurrency,
            pool_maxsize=max_concurrency,
            max_retries=0,  # 重试逻辑自己控制，不用 urllib3 内置重试
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

        # 并发池：同时在飞的请求数不超过 max_concurrency。
        self._semaphore = threading.Semaphore(max_concurrency)

    # -- 内部：构造请求体 -------------------------------------------------

    def _build_payload(self, question: str, request_id: str, user_id: Optional[str]) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": question},
            ],
            # GLM-5.3 无法关闭思考，thinking.type 必须保持默认的 "enabled"，
            # 否则会报错码 1210；真正的降本降速靠下面的 reasoning_effort。
            "thinking": {"type": "enabled"},
            "reasoning_effort": self.reasoning_effort,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": False,
            "request_id": request_id,
        }
        if user_id:
            payload["user_id"] = user_id
        return payload

    # -- 内部：单次 HTTP 调用 + 重试 ---------------------------------------

    def _post_with_retry(self, payload: dict) -> dict:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.post(
                    CHAT_ENDPOINT, json=payload, timeout=self.timeout
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                self._sleep_backoff(attempt)
                continue

            if resp.status_code == 200:
                return resp.json()

            # 先看是不是可重试的状态码/业务错误码。
            body = self._safe_json(resp)
            error_code = str((body.get("error") or {}).get("code", ""))
            error_message = (body.get("error") or {}).get("message", resp.text[:500])

            retryable = (
                resp.status_code in RETRYABLE_HTTP_STATUS
                or error_code in RETRYABLE_ERROR_CODES
            )
            if not retryable:
                # 401/1210/1211/... 这类配置或参数问题，重试没有意义，直接抛出。
                raise SupportBotError(
                    f"不可重试的错误 HTTP {resp.status_code} code={error_code}: {error_message}"
                )

            last_exc = SupportBotRateLimited(
                f"HTTP {resp.status_code} code={error_code}: {error_message}"
            )
            if attempt < self.max_retries:
                self._sleep_backoff(attempt)

        raise last_exc or SupportBotRateLimited("重试耗尽，原因未知")

    @staticmethod
    def _safe_json(resp: requests.Response) -> dict:
        try:
            return resp.json()
        except ValueError:
            return {}

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        # 指数退避 + 抖动，避免所有并发请求同时重试造成"重试风暴"。
        base = min(1.0 * (2 ** attempt), 8.0)
        time.sleep(base + random.uniform(0, 0.5))

    # -- 对外接口 -----------------------------------------------------------

    def ask(
        self,
        question: str,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AnswerResult:
        """同步问答一次，返回结构化结果。线程安全，可在线程池中并发调用。"""
        req_id = request_id or str(uuid.uuid4())
        payload = self._build_payload(question, req_id, user_id)

        start = time.monotonic()
        with self._semaphore:  # 控制同时在飞的请求数
            try:
                data = self._post_with_retry(payload)
            except (SupportBotError, SupportBotRateLimited) as exc:
                latency = time.monotonic() - start
                return AnswerResult(
                    question=question,
                    content="",
                    finish_reason=None,
                    reasoning_tokens=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    cached_tokens=0,
                    latency_seconds=latency,
                    request_id=req_id,
                    error=str(exc),
                )
        latency = time.monotonic() - start

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        reasoning_tokens = (
            usage.get("completion_tokens_details", {}) or {}
        ).get("reasoning_tokens", 0)
        cached_tokens = (usage.get("prompt_tokens_details", {}) or {}).get(
            "cached_tokens", 0
        )

        return AnswerResult(
            question=question,
            content=message.get("content", ""),
            finish_reason=choice.get("finish_reason"),
            reasoning_tokens=reasoning_tokens or 0,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            cached_tokens=cached_tokens or 0,
            latency_seconds=latency,
            request_id=req_id,
        )

    def ask_many(
        self,
        questions: Iterable[str],
        user_id: Optional[str] = None,
        max_workers: Optional[int] = None,
    ) -> list[AnswerResult]:
        """高并发批量问答：用线程池并发提交，真实并发上限仍由内部信号量兜底。"""
        questions = list(questions)
        workers = max_workers or min(32, len(questions) or 1)

        results: list[Optional[AnswerResult]] = [None] * len(questions)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_idx = {
                pool.submit(self.ask, q, user_id): i
                for i, q in enumerate(questions)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                results[idx] = future.result()
        return results  # type: ignore[return-value]

    def close(self) -> None:
        self._session.close()


# --------------------------------------------------------------------------
# 演示入口
# --------------------------------------------------------------------------


def main() -> None:
    if not os.environ.get(API_KEY_ENV_VAR):
        print(
            f"[提示] 未检测到环境变量 {API_KEY_ENV_VAR}，本次演示不会真正发起网络请求。\n"
            f"请先执行：export {API_KEY_ENV_VAR}=\"你的真实 API Key\"，再重新运行本脚本。\n"
        )
        return

    client = SupportBotClient(
        model="glm-5.3",
        reasoning_effort="low",  # 简单问答场景，思考开销压到最低档
        max_tokens=256,
        max_concurrency=20,
    )

    sample_questions = [
        "你们的退货政策是什么？",
        "订单发货后一般多久能到？",
        "怎么修改收货地址？",
        "支持哪些支付方式？",
        "会员积分怎么兑换？",
    ]

    try:
        results = client.ask_many(sample_questions, user_id="demo-user")
        for r in results:
            if r.error:
                print(f"[FAIL] Q={r.question!r} error={r.error}")
                continue
            print(
                f"[OK] Q={r.question!r} "
                f"latency={r.latency_seconds:.2f}s "
                f"reasoning_tokens={r.reasoning_tokens} "
                f"completion_tokens={r.completion_tokens} "
                f"cached_tokens={r.cached_tokens} "
                f"finish_reason={r.finish_reason}\n"
                f"    A: {r.content}"
            )
    finally:
        client.close()


if __name__ == "__main__":
    main()
