#!/usr/bin/env python3
"""
GLM-5.2 高并发客服机器人调用脚本
============================================================
用途：面向"简单问答、不需要复杂推理"的客服场景，通过标准库 requests
调用智谱 BigModel 开放平台 GLM-5.2 模型的 Chat Completions 接口。

关键降本增速手段
------------------------------------------------------------
1. 关闭"深度思考"（thinking / reasoning）模式
   GLM-4.5 及之后的系列模型都是"混合推理"架构：默认情况下模型可能
   会先生成一段隐藏的思维链（thinking/reasoning content），再给出
   最终答案。这段思维链本身要消耗生成 token（计费 + 耗时），对于
   客服场景里"今天几点关门""怎么退款"这类简单问答完全是浪费。
   通过在请求体里显式传：
       "thinking": {"type": "disabled"}
   可以让模型跳过思考阶段直接输出答案，能明显降低首字延迟和总生成
   耗时，同时减少计费 token 数量。如果官方接口/SDK 版本不认识这个
   字段，会被忽略而不会报错，不影响脚本可用性；如果你的账号对应的
   接口版本用的是别的开关名（比如某些 SDK 里的 do_sample 或
   extra_body 参数），把 payload 里这一行换成对应字段即可。

2. 限制 max_tokens
   简单问答不需要长篇大论，把 max_tokens 设置得比较小（默认 512），
   既能防止模型"话痨"，也给延迟设了一个硬上限。

3. temperature / top_p 调低
   客服问答追求稳定、可预测的回答，没必要用较高的随机性采样，
   顺带也减少了因为回答跑偏而需要人工重试的概率。

4. 连接复用（requests.Session + HTTPAdapter 连接池）
   高并发场景下，如果每次请求都新建 TCP/TLS 连接，握手开销会成为
   主要的延迟来源。这里用一个全局 Session，并放大连接池
   （pool_connections / pool_maxsize），配合 urllib3 的 Retry 只对
   网络抖动 / 429 / 5xx 做少量自动重试。

5. 用 ThreadPoolExecutor 做并发调度
   requests 本身是同步阻塞的，但客服机器人经常是"多个用户同时提问"
   的场景。这里用线程池 + 共享 Session 并发发起多个请求，对于这种
   I/O 密集型场景线程池已经足够，没必要引入 asyncio/httpx。

6. 默认不开启 stream
   非流式返回对短答案场景实现最简单、吞吐最好算；如果产品需要
   "打字机"效果来降低用户感知延迟，可以用下面的
   generate_answer_stream，同样带上了关闭深度思考的参数。

使用前:
    export BIGMODEL_API_KEY="你的真实 API Key"
    python support_bot.py
"""

import os
import time
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except ImportError:  # 兼容旧版 requests 内置打包的 urllib3
    from requests.packages.urllib3.util.retry import Retry


# ------------------------------------------------------------------
# 基础配置
# ------------------------------------------------------------------
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL_NAME = "glm-5.2"  # 如实际可用模型名不同，请按官方文档调整

# 出于安全考虑，API Key 一律从环境变量读取，不要硬编码在代码里
API_KEY = os.environ.get("BIGMODEL_API_KEY", "PUT_YOUR_API_KEY_HERE")

# 简单问答场景下推荐的默认参数
DEFAULT_MAX_TOKENS = 512
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_P = 0.7
REQUEST_TIMEOUT = (3.05, 20)  # (连接超时秒数, 读取超时秒数)

# 客服机器人的系统提示词：约束回答风格 + 强化"简洁不啰嗦"
SYSTEM_PROMPT = (
    "你是一个电商平台的智能客服助手。"
    "只回答与产品、订单、售后相关的问题，"
    "回答要简洁、直接、口语化，不要输出多余的解释、免责声明或思考过程，"
    "遇到你不确定或超出你能力范围的问题，请引导用户转接人工客服。"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("glm_support_bot")


# ------------------------------------------------------------------
# 全局 Session：连接池复用，避免高并发下反复 TCP/TLS 握手
# ------------------------------------------------------------------
def build_session(pool_maxsize: int = 64) -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=2,                       # 最多重试 2 次（针对网络抖动/限流/服务端错误）
        backoff_factor=0.3,            # 退避：0.3s, 0.6s ...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(
        pool_connections=pool_maxsize,
        pool_maxsize=pool_maxsize,
        max_retries=retry_strategy,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
    )
    return session


# 全局共享 Session；requests.Session 的连接池是线程安全的，
# 多个线程可以复用同一个 Session 发起并发请求。
_session = build_session()


# ------------------------------------------------------------------
# 核心调用：单轮问答，关闭深度思考模式
# ------------------------------------------------------------------
def generate_answer(
    user_message: str,
    session: Optional[requests.Session] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    """
    调用 GLM-5.2 完成一次简单问答，关闭深度思考模式以降低延迟和成本。
    """
    sess = session or _session

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": DEFAULT_TOP_P,
        "stream": False,
        # 关键优化点：显式关闭"深度思考"模式。
        # GLM-4.5/GLM-5 系列是混合推理模型，不关闭的话模型可能会先
        # 生成一段隐藏的 reasoning/thinking 内容再作答，白白增加
        # token 消耗和响应时间——这对简单客服问答场景没有必要。
        "thinking": {"type": "disabled"},
    }

    start = time.monotonic()
    try:
        resp = sess.post(API_URL, data=json.dumps(payload), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.error("调用 GLM API 失败: %s", exc)
        return "抱歉，客服系统暂时繁忙，请稍后再试或转接人工客服。"

    elapsed = time.monotonic() - start
    data = resp.json()

    try:
        answer = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        logger.error("响应格式异常: %s", data)
        return "抱歉，暂时无法理解您的问题，请换一种说法或转接人工客服。"

    usage = data.get("usage", {})
    logger.info(
        "耗时=%.2fs | prompt_tokens=%s completion_tokens=%s total_tokens=%s",
        elapsed,
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        usage.get("total_tokens"),
    )
    return answer


# ------------------------------------------------------------------
# 可选：流式调用（需要"打字机"效果、想降低用户感知延迟时使用）
# ------------------------------------------------------------------
def generate_answer_stream(user_message: str, session: Optional[requests.Session] = None):
    """
    流式返回，逐段 yield 文本片段。同样关闭深度思考模式，
    适合需要尽快展示第一个字的前端场景。
    """
    sess = session or _session

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": DEFAULT_TEMPERATURE,
        "top_p": DEFAULT_TOP_P,
        "stream": True,
        "thinking": {"type": "disabled"},
    }

    with sess.post(
        API_URL,
        data=json.dumps(payload),
        timeout=REQUEST_TIMEOUT,
        stream=True,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if not line.startswith("data:"):
                continue
            chunk = line[len("data:"):].strip()
            if chunk == "[DONE]":
                break
            try:
                event = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            delta = event.get("choices", [{}])[0].get("delta", {})
            piece = delta.get("content")
            if piece:
                yield piece


# ------------------------------------------------------------------
# 高并发批量问答示例：ThreadPoolExecutor + 共享连接池
# ------------------------------------------------------------------
def batch_answer(
    questions: List[Dict[str, str]],
    max_workers: int = 32,
) -> List[Dict[str, str]]:
    """
    并发处理一批客服问题。
    questions: [{"id": "u1", "text": "..."}]
    返回:      [{"id": "u1", "question": "...", "answer": "..."}]

    max_workers 建议不超过 Session 连接池大小
    （build_session 里的 pool_maxsize），否则线程会在争抢连接时互相等待。
    """
    results: List[Optional[Dict[str, str]]] = [None] * len(questions)

    def _task(idx: int, item: Dict[str, str]) -> None:
        answer = generate_answer(item["text"])
        results[idx] = {
            "id": item.get("id", str(idx)),
            "question": item["text"],
            "answer": answer,
        }

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="glm-worker") as pool:
        futures = {
            pool.submit(_task, idx, item): idx for idx, item in enumerate(questions)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                logger.error("第 %s 条问题处理失败: %s", idx, exc)
                results[idx] = {
                    "id": questions[idx].get("id", str(idx)),
                    "question": questions[idx]["text"],
                    "answer": "抱歉，处理您的问题时出现异常，请稍后再试。",
                }

    return results  # type: ignore[return-value]


# ------------------------------------------------------------------
# demo
# ------------------------------------------------------------------
if __name__ == "__main__":
    if API_KEY in (None, "", "PUT_YOUR_API_KEY_HERE"):
        logger.warning(
            "未检测到有效的 BIGMODEL_API_KEY 环境变量，"
            "当前使用的是占位符，实际请求会失败。"
            "请先执行: export BIGMODEL_API_KEY='你的真实key'"
        )

    # 单条问答示例
    single_q = "我的订单什么时候能发货？"
    print("单条问答:", generate_answer(single_q))

    # 批量并发问答示例（模拟高并发场景）
    demo_questions = [
        {"id": "u1", "text": "怎么申请退款？"},
        {"id": "u2", "text": "支持货到付款吗？"},
        {"id": "u3", "text": "会员有什么优惠？"},
        {"id": "u4", "text": "商品可以七天无理由退货吗？"},
    ]
    batch_results = batch_answer(demo_questions, max_workers=8)
    for item in batch_results:
        print(f"[{item['id']}] Q: {item['question']}\n     A: {item['answer']}\n")
