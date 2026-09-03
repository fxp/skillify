"""
高并发客服问答机器人 —— 基于智谱 GLM-5.2 (bigmodel.cn)

设计目标（按重要性排序）：
  1. 响应延迟尽量低（简单问答场景，不需要模型做多步推理）
  2. 单次调用成本尽量低
  3. 能扛住高并发（多个客服会话同时进行）

关键省钱/提速点：
  - 显式关闭深度思考：thinking={"type": "disabled"}
    * 这一步只对 GLM-5.2 及以下到 GLM-4.5 之间的模型有效 —— 这些模型的思考行为是
      "模型自动判断是否思考"，可以用 thinking.type 显式开关。
    * 千万不要把这段代码原样套到 glm-5.3 / glm-5.3-flash 上：这两个模型强制开启
      思考，传 thinking.type="disabled" 会直接报业务错误码 1210
      （"该模型始终思考，不支持关闭思考；请使用 low、high 或 max"）。
      如果以后把 model 换成 5.3 系列，必须把关闭思考的逻辑换成
      reasoning_effort="low"（只能调低，不能彻底关闭）。
    * thinking 关闭后 reasoning_effort 不再生效（该参数仅在 thinking 开启时才起
      作用），所以这里不传 reasoning_effort，避免产生"这个参数到底有没有用"的误解。
  - max_tokens 设置得比较小（默认 512）：简单客服问答不需要几万字的输出，显式设置
    上限可以防止模型跑题写长文，白白消耗 completion token。
  - do_sample=False（贪心解码）：客服问答场景更需要稳定、可复现的回答，而不是
    创造性；贪心解码也省去了 temperature/top_p 采样的调参心智负担。如果产品上需要
    更"有温度"的话术，可以自行改回 do_sample=True + 较低的 temperature。
  - system prompt 固定不变：bigmodel.cn 的上下文缓存是隐式自动生效的，只要多次请求
    的前缀（典型如 system prompt）保持完全一致，重复部分就有机会命中缓存，从而降低
    该部分的计费与耗时。所以这里把 system prompt 抽成模块级常量，不要每次请求都
    临时拼接/微调它。
  - 用 requests.Session + 连接池 + 并发信号量：智谱的限流是按"同时处理中的并发请求数"
    计算的，不是 QPS。用无上限的线程池硬发请求，触发限流（错误码 1302/1305）的概率会
    显著上升。这里用一个 Semaphore 把同时在途的请求数钳制在 MAX_CONCURRENCY 以内，
    并把连接池大小设成同一个数字，避免连接数成为新的瓶颈。
  - 对 429（1302/1305/1308/1310）和 5xx 做指数退避重试，对 4xx（参数错误/鉴权错误）
    直接失败不重试 —— 重试参数错误没有意义，只会浪费延迟和配额。
  - 同步（非流式）调用：客服问答的回答通常很短，流式输出带来的"首字延迟更低"的收益
    对短回答意义不大，反而会让高并发下的代码复杂度（SSE 解析、连接保持更久）上升。
    如果后续产品要求"逐字打字机效果"，可以把 stream 改成 True，参考技能包
    references/chat.md 第三节的 SSE 解析方式。

用法：
    export ZHIPUAI_API_KEY="你的真实 API Key"   # 从 bigmodel.cn 控制台获取，不要硬编码
    python support_bot.py
"""

from __future__ import annotations

import concurrent.futures
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 注意：这里选用的是 glm-5.2 —— 支持显式关闭深度思考。
# 如果换成 glm-5.3 / glm-5.3-flash，思考是强制开启的，不能这样关闭，
# 只能用 reasoning_effort="low" 把思考强度调到最低（不是真正关闭）。
MODEL = "glm-5.2"

# system prompt 固定不变，便于命中 bigmodel.cn 的隐式上下文缓存，降低重复部分的成本。
SYSTEM_PROMPT = (
    "你是一个电商平台的客服助手，只回答关于订单、物流、退换货、账户等常见问题。"
    "回答要简洁、直接、口语化，控制在 3 句话以内；遇到无法确定的问题，"
    "明确告知用户需要转人工客服，不要编造信息。"
)

# 触发退避重试的业务错误码（限流 / 平台过载 / 用量上限）。
RETRYABLE_ERROR_CODES = {"1302", "1305", "1308", "1310"}


class GLMAPIError(RuntimeError):
    """封装 bigmodel.cn 返回的业务错误（HTTP 状态码 + 业务 error.code + message）。"""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"[HTTP {status_code}][code {code}] {message}")

    @property
    def is_retryable(self) -> bool:
        # 429 类限流/过载错误值得退避重试；401/403/400 类配置或参数错误重试没有意义。
        return self.status_code == 429 or self.code in RETRYABLE_ERROR_CODES or self.status_code >= 500


@dataclass
class SupportBotClient:
    """高并发场景下复用的 GLM-5.2 客服问答客户端。

    一个进程内建议只创建一个实例并复用（内部持有连接池 + 并发信号量），
    不要每次请求都 new 一个新的 Session。
    """

    api_key: str = field(default_factory=lambda: os.environ.get("ZHIPUAI_API_KEY", ""))
    model: str = MODEL
    max_concurrency: int = 20          # 与账户在控制台看到的并发额度对齐，别拍脑袋设很大
    connect_timeout: float = 3.05      # 连接超时：略大于 3 的整数倍，requests 官方推荐写法
    read_timeout: float = 15.0         # 读超时：简单问答场景不需要给太久
    max_retries: int = 3               # 仅针对 429/5xx 的退避重试次数
    max_tokens: int = 512              # 简单问答不需要很长的输出，显式限死，防止跑题超长

    def __post_init__(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "未设置 API Key：请先 export ZHIPUAI_API_KEY=<你的 Key>，"
                "从 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取，"
                "不要把 Key 硬编码进代码。"
            )

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
        # 连接池大小和并发信号量对齐，避免"信号量放行了，但连接池不够用还得排队新建连接"。
        adapter = HTTPAdapter(
            pool_connections=self.max_concurrency,
            pool_maxsize=self.max_concurrency,
        )
        self._session.mount("https://", adapter)

        # 智谱的限流按"同时处理中的并发请求数"计算，不是 QPS，
        # 所以用信号量把同时在途的请求数钳制住，而不是无限制地开线程猛发。
        self._semaphore = threading.Semaphore(self.max_concurrency)

    def ask(self, user_question: str, *, user_id: Optional[str] = None) -> "AskResult":
        """向 GLM-5.2 发起一次同步问答，返回回答文本 + 用量信息。

        阻塞方法，线程安全（可以被多个线程同时调用，内部用信号量控制真正的并发度）。
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_question},
            ],
            # ↓↓↓ 本脚本的核心优化点：显式关闭深度思考 ↓↓↓
            # 仅对 glm-5.2（以及 glm-5.1/glm-5/glm-4.6/glm-4.5 等"自动判断是否思考"
            # 的模型）有效；glm-5.3 系列强制思考，这个参数会直接报错。
            "thinking": {"type": "disabled"},
            "max_tokens": self.max_tokens,
            "do_sample": False,   # 贪心解码：结果稳定可复现，且不用纠结 temperature/top_p
            "stream": False,      # 简单问答回答短，非流式足够，逻辑也更简单
            "request_id": str(uuid.uuid4()),
        }
        if user_id:
            payload["user_id"] = user_id

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            with self._semaphore:
                try:
                    resp = self._session.post(
                        BASE_URL,
                        json=payload,
                        timeout=(self.connect_timeout, self.read_timeout),
                    )
                except requests.RequestException as exc:
                    # 网络层错误（连接失败/超时）：也按可重试处理
                    last_error = exc
                    self._sleep_backoff(attempt)
                    continue

            if resp.status_code == 200:
                body = resp.json()
                message = body["choices"][0]["message"]
                usage = body.get("usage", {})
                return AskResult(
                    content=message.get("content", ""),
                    finish_reason=body["choices"][0].get("finish_reason", ""),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                )

            # 非 200：尝试解析业务错误码，决定是否值得重试
            code, message = _parse_error_body(resp)
            err = GLMAPIError(resp.status_code, code, message)
            last_error = err
            if not err.is_retryable or attempt == self.max_retries:
                raise err
            self._sleep_backoff(attempt)

        # 理论上不会走到这里，兜底抛出最后一次的错误
        assert last_error is not None
        raise last_error

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        # 指数退避 + 抖动，避免"限流了 -> 所有线程同时固定间隔重试 -> 加重限流"的雪崩效应
        delay = min(8.0, (2 ** attempt)) + random.uniform(0, 0.5)
        time.sleep(delay)


@dataclass
class AskResult:
    content: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def _parse_error_body(resp: requests.Response) -> tuple[str, str]:
    try:
        err = resp.json().get("error", {})
        return str(err.get("code", "")), str(err.get("message", resp.text))
    except ValueError:
        return "", resp.text


def _demo_single_call() -> None:
    bot = SupportBotClient()
    result = bot.ask("我的订单显示已发货，但是三天了物流信息一直没更新，能帮我查一下吗？")
    print("回答:", result.content)
    print(
        f"finish_reason={result.finish_reason} "
        f"prompt_tokens={result.prompt_tokens} "
        f"completion_tokens={result.completion_tokens} "
        f"total_tokens={result.total_tokens}"
    )


def _demo_concurrent_calls() -> None:
    """模拟高并发场景：多个用户同时提问，线程池 worker 数量与客户端的并发信号量对齐。"""
    questions = [
        "怎么申请退货？",
        "运费险是什么，怎么用？",
        "我想修改收货地址，订单还没发货可以改吗？",
        "优惠券过期了能补发吗？",
        "支付失败但是钱被扣了，怎么办？",
    ]

    bot = SupportBotClient(max_concurrency=5)
    with concurrent.futures.ThreadPoolExecutor(max_workers=bot.max_concurrency) as pool:
        futures = {pool.submit(bot.ask, q): q for q in questions}
        for future in concurrent.futures.as_completed(futures):
            question = futures[future]
            try:
                result = future.result()
                print(f"[Q] {question}\n[A] {result.content}\n")
            except GLMAPIError as exc:
                print(f"[Q] {question}\n[调用失败，不重试或重试耗尽] {exc}\n")


if __name__ == "__main__":
    _demo_single_call()
    print("-" * 60)
    _demo_concurrent_calls()
