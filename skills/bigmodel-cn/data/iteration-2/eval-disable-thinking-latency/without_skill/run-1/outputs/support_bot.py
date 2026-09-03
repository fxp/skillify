#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GLM-5.3 高并发客服机器人调用示例
==================================

场景：简单问答型客服机器人，不需要模型做复杂推理，但对响应速度和调用成本敏感。
本脚本只用 `requests` 直接调用智谱开放平台（bigmodel.cn）Chat Completions 接口，
不依赖官方 zhipuai SDK，便于精简依赖、方便部署在高并发服务里。

针对"降低不必要开销"做的几件事：
  1. 【关闭深度思考模式】GLM-5.3 属于支持"深度思考"（reasoning/thinking）的模型系列，
     默认可能会先生成一段内部思维链再给出答案，这会显著增加 tokens 消耗和响应延迟。
     对于简单问答场景，通过请求体中的 `thinking: {"type": "disabled"}` 参数关闭该模式，
     模型会跳过思维链、直接输出答案 —— 既提速又省 token 成本。
     （如果你的账号/模型版本参数名不同，请对照最新的 bigmodel.cn API 文档核实该字段，
     常见的等价写法还有 "thinking": {"type": "enabled"|"disabled"}，具体以官方文档为准。）
  2. 【限制输出长度】max_tokens 设置得比较小，避免客服场景里生成不必要的长回复。
  3. 【关闭流式】简单问答一次性返回即可，不需要 stream=True 带来的额外协议开销；
     如果你的场景需要「边生成边显示」的体验，可以把 stream 打开，用 SSE 方式读取。
  4. 【连接复用 + 连接池】使用 requests.Session 并配置较大的连接池（HTTPAdapter），
     在高并发下避免每次请求都重新做 TCP/TLS 握手，显著降低平均延迟。
  5. 【精简 Prompt】只放一条简短的 system prompt，不堆叠无关的少样本示例，减少输入 token。
  6. 【超时 + 有限重试】避免个别慢请求把线程池/连接池占满，拖垮整体并发吞吐。
  7. 【线程池并发】用 ThreadPoolExecutor 模拟高并发客服请求，requests 是同步阻塞库，
     多线程 + 连接池是在标准库 requests 下拿到并发能力的最简单方式
     （如果并发量非常大，更推荐迁移到 httpx/aiohttp 做异步 IO，这里按你的要求保持用 requests）。

免责声明：
  - 本脚本不会实际请求 bigmodel.cn（示例环境没有真实 API Key），仅保证语法可运行、
    逻辑尽量贴近官方文档描述。请在有真实 Key 后自行验证字段名（尤其是 thinking 参数）
    是否与你所用的 GLM-5.3 版本完全一致，官方文档如有调整以官方为准。
  - API Key 请通过环境变量 ZHIPU_API_KEY 注入，不要把密钥硬编码进代码或提交到仓库。
"""

import concurrent.futures
import logging
import os
import time
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("glm_support_bot")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 从环境变量读取 API Key，避免明文写进代码。真正使用前请执行：
#   export ZHIPU_API_KEY="你的真实key"
API_KEY = os.environ.get("ZHIPU_API_KEY", "PLACEHOLDER_API_KEY")

MODEL_NAME = "glm-5.3"

# 高并发相关参数，可根据实际 QPS / 机器资源调整
MAX_WORKERS = 32          # 线程池大小（同时在途的请求数上限）
POOL_MAXSIZE = 64         # requests 连接池大小，建议 >= MAX_WORKERS
CONNECT_TIMEOUT = 3       # 连接超时（秒）
READ_TIMEOUT = 15         # 读取超时（秒），简单问答场景不需要太长
MAX_RETRIES = 2           # 网络抖动/限流时的重试次数

SYSTEM_PROMPT = (
    "你是一个简洁高效的在线客服助手，只回答与产品/服务相关的问题，"
    "用简短清晰的中文直接给出答案，不要输出多余的解释或客套话。"
)


# ---------------------------------------------------------------------------
# Session：连接复用，减少高并发下的握手开销
# ---------------------------------------------------------------------------

def _build_session() -> requests.Session:
    session = requests.Session()

    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        pool_connections=POOL_MAXSIZE,
        pool_maxsize=POOL_MAXSIZE,
        max_retries=retry_strategy,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
            "Connection": "keep-alive",
        }
    )
    return session


# 进程级复用同一个 Session / 连接池，不要每次请求都 new 一个
_session = _build_session()


# ---------------------------------------------------------------------------
# 核心调用函数
# ---------------------------------------------------------------------------

def ask_glm(question: str, session: Optional[requests.Session] = None) -> str:
    """向 GLM-5.3 发起一次单轮问答请求，关闭深度思考模式以降低延迟和成本。"""
    sess = session or _session

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        # 关键优化点：关闭深度思考（reasoning/thinking）模式。
        # 简单问答不需要模型输出思维链，关掉可以省掉这部分 token 生成时间和费用。
        "thinking": {
            "type": "disabled",
        },
        "temperature": 0.3,   # 客服场景希望回答稳定、少发散
        "max_tokens": 256,    # 限制输出长度，避免不必要的长回复消耗 token
        "stream": False,      # 简单问答一次性返回，不用流式协议
    }

    start = time.monotonic()
    try:
        resp = sess.post(
            API_URL,
            json=payload,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
        resp.raise_for_status()
        data = resp.json()

        answer = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        elapsed_ms = (time.monotonic() - start) * 1000

        logger.info(
            "OK  %.0fms  prompt_tokens=%s completion_tokens=%s q=%r",
            elapsed_ms,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            question[:20],
        )
        return answer

    except requests.exceptions.Timeout:
        logger.error("请求超时: q=%r", question[:20])
        return "抱歉，客服系统响应超时，请稍后再试。"

    except requests.exceptions.RequestException as exc:
        logger.error("请求失败: %s  q=%r", exc, question[:20])
        return "抱歉，客服系统暂时繁忙，请稍后再试。"

    except (KeyError, IndexError, ValueError) as exc:
        logger.error("响应解析失败: %s  raw=%r", exc, locals().get("data"))
        return "抱歉，客服系统出现异常，请稍后再试。"


# ---------------------------------------------------------------------------
# 高并发批处理示例
# ---------------------------------------------------------------------------

def handle_batch(questions: List[str]) -> List[str]:
    """
    用线程池并发处理一批用户问题，模拟客服机器人在高并发场景下的调用方式。
    多个线程共享同一个 requests.Session / 连接池，避免每个请求都重新握手。
    """
    results: List[Optional[str]] = [None] * len(questions)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(ask_glm, q): idx for idx, q in enumerate(questions)
        }
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:  # 兜底，防止单个任务异常影响整批结果
                logger.error("任务异常: %s", exc)
                results[idx] = "抱歉，客服系统出现异常，请稍后再试。"

    return results  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 演示入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if API_KEY == "PLACEHOLDER_API_KEY":
        logger.warning(
            "未检测到真实 API Key，当前使用占位符运行（不会得到有效响应）。"
            "请先执行: export ZHIPU_API_KEY=你的真实密钥"
        )

    sample_questions = [
        "你们的退货政策是什么？",
        "订单大概多久能发货？",
        "支持哪些支付方式？",
        "会员有什么优惠？",
        "如何联系人工客服？",
    ]

    logger.info("开始并发处理 %d 个客服问题（线程池大小=%d）...", len(sample_questions), MAX_WORKERS)
    answers = handle_batch(sample_questions)

    print("\n===== 客服问答结果 =====")
    for q, a in zip(sample_questions, answers):
        print(f"Q: {q}\nA: {a}\n")
