#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoDL 容器实例训练后自动清理脚本。

用途：训练任务结束（无论成功还是异常退出）后，自动把当前这台 AutoDL 容器实例
"关机 -> 释放"，避免训练跑完了还占着资源、持续计费。

用法：
    1. 把你的训练逻辑放进 `run_training()`（或者直接把这个脚本的
       `cleanup_instance()` 函数 import 到你自己的训练脚本里，在训练主流程的
       try/finally 里调用它）。
    2. 设置环境变量 AUTODL_TOKEN 为你的开发者 Token（控制台 -> 账号 -> 设置 ->
       开发者Token），不要把 Token 硬编码进代码。
    3. 需要清理哪台实例默认从容器内置环境变量 AutoDLContainerUUID 读取
       （AutoDL 官方会自动注入这个变量到实例容器内，不需要额外调 API 查“我是谁”）；
       如果要在实例外部/本机测试，可以用 AUTODL_INSTANCE_UUID 环境变量覆盖。

接口约定（来自 AutoDL 容器实例 Pro API 文档，已实测确认）：
    - Base URL 固定为 https://api.autodl.com
    - 鉴权头是 `Authorization: <token>`，没有 "Bearer " 前缀
    - 所有 GET 接口的参数必须放进 URL query string（requests 的 params=），
      不能放进 JSON body —— 官方文档自己的示例是错的，实测放 body 会返回
      RequestParameterIsWrong
    - 统一响应结构：{"code": "Success"/其他, "msg": "...", "data": ...}，
      code 不等于 "Success" 就是出错，只能靠 msg 文本判断原因（没有稳定的错误码
      枚举表可以做 switch）
    - 关机后不是立刻就能释放：状态会先变成 "shutting_down"（关机中），过几秒
      才变成 "shutdown"（关机完成）。对一台还没到 shutdown 状态的实例调用
      release 会 100% 被拒绝，返回 {"code":"BadRequest","msg":"请在实例关机
      状态下执行释放操作"}，不是概率性失败。所以必须先 power_off，然后轮询
      status 直到状态变为 "shutdown"，再调用 release —— 不能 power_off 后
      立刻紧接着调 release。
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("autodl-cleanup")

BASE_URL = "https://api.autodl.com"

# 关机后轮询状态的间隔和总超时时间。实测关机（shutting_down -> shutdown）一般
# 只需要几秒，但网络抖动或平台繁忙可能更久，超时时间留得宽松一些。
POLL_INTERVAL_SECONDS = 5
SHUTDOWN_TIMEOUT_SECONDS = 300

# 中间态：处于这些状态说明关机还没完成，继续轮询即可，不算异常。
IN_PROGRESS_STATES = {"shutting_down"}
SHUTDOWN_DONE_STATE = "shutdown"


class AutoDLAPIError(RuntimeError):
    """AutoDL API 返回了非 Success 的业务错误码。"""

    def __init__(self, code: str, msg: str, endpoint: str):
        self.code = code
        self.msg = msg
        self.endpoint = endpoint
        super().__init__(f"[{endpoint}] code={code} msg={msg}")


def _get_token() -> str:
    token = os.environ.get("AUTODL_TOKEN")
    if not token:
        raise RuntimeError(
            "环境变量 AUTODL_TOKEN 未设置。请先在 AutoDL 控制台 -> 账号 -> 设置 -> "
            "开发者Token 获取 Token，再通过环境变量传入，不要把 Token 写死在代码里。"
        )
    return token


def _get_instance_uuid(explicit: Optional[str] = None) -> str:
    """确定要清理的实例 UUID。

    优先级：显式传入的参数 > AUTODL_INSTANCE_UUID 环境变量 > 容器内置的
    AutoDLContainerUUID 环境变量（AutoDL 平台会自动注入到实例容器内，代表
    “当前正在运行代码的这台实例”，不需要反过来调 API 查询）。
    """
    if explicit:
        return explicit
    env_override = os.environ.get("AUTODL_INSTANCE_UUID")
    if env_override:
        return env_override
    container_uuid = os.environ.get("AutoDLContainerUUID")
    if container_uuid:
        return container_uuid
    raise RuntimeError(
        "无法确定要清理的实例 UUID：既没有显式传参，也没有 AUTODL_INSTANCE_UUID / "
        "AutoDLContainerUUID 环境变量可用。请显式传入 instance_uuid，或者确认这个"
        "脚本是在目标 AutoDL 实例容器内运行的。"
    )


def _request(method: str, path: str, *, token: str, payload: Optional[dict] = None) -> Any:
    """统一的请求封装，处理鉴权头、GET/POST 传参方式差异、以及业务错误码。"""
    url = f"{BASE_URL}{path}"
    headers = {"Authorization": token}

    if method == "GET":
        # GET 接口必须用 query string 传参，不能用 JSON body（文档示例是错的）。
        resp = requests.get(url, headers=headers, params=payload, timeout=30)
    elif method == "POST":
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
    else:
        raise ValueError(f"不支持的 HTTP method: {method}")

    resp.raise_for_status()
    body = resp.json()

    code = body.get("code")
    if code != "Success":
        raise AutoDLAPIError(code=code, msg=body.get("msg", ""), endpoint=path)

    return body.get("data")


def get_status(instance_uuid: str, token: str) -> str:
    """查询实例当前状态字符串，如 "running" / "shutting_down" / "shutdown"。"""
    data = _request(
        "GET",
        "/api/v1/dev/instance/pro/status",
        token=token,
        payload={"instance_uuid": instance_uuid},
    )
    return data


def power_off(instance_uuid: str, token: str) -> None:
    """对实例发起关机。这是异步操作，返回成功只代表关机指令已下发，不代表已关完。"""
    logger.info("发起关机请求：instance_uuid=%s", instance_uuid)
    _request(
        "POST",
        "/api/v1/dev/instance/pro/power_off",
        token=token,
        payload={"instance_uuid": instance_uuid},
    )


def wait_until_shutdown(
    instance_uuid: str,
    token: str,
    *,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    timeout: float = SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    """轮询实例状态，直到确认变为 "shutdown"（关机完成）才返回。

    这是判断"何时可以安全调用 release"的唯一依据 —— 不是在 power_off 请求
    返回后就立刻调 release（power_off 只是异步下发关机指令），也不是等一个
    固定的 sleep 时间就假设关完了。必须实际轮询 status 接口拿到 "shutdown"
    这个终态。中间会经过一个官方文档未列出的过渡态 "shutting_down"，这个状态
    继续等待即可，不当作异常。
    """
    deadline = time.monotonic() + timeout
    last_status = None

    while True:
        status = get_status(instance_uuid, token)
        if status != last_status:
            logger.info("实例状态：%s", status)
            last_status = status

        if status == SHUTDOWN_DONE_STATE:
            return

        if status not in IN_PROGRESS_STATES and status != "running":
            # 未知状态：不确定是否安全释放，不武断处理，交给调用方决定。
            logger.warning(
                "实例状态 %r 既不是已知的中间态也不是已知的运行态，继续轮询观察，"
                "但如果长期停留在这个状态请人工检查控制台。",
                status,
            )

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"等待实例 {instance_uuid} 关机超时（{timeout}s），当前状态仍为 "
                f"{status!r}，为安全起见不会继续调用 release，请人工检查。"
            )

        time.sleep(poll_interval)


def release(instance_uuid: str, token: str) -> None:
    """释放实例（不可逆，等价于彻底销毁并停止计费）。只能对 shutdown 状态的实例调用。"""
    logger.info("发起释放请求：instance_uuid=%s", instance_uuid)
    _request(
        "POST",
        "/api/v1/dev/instance/pro/release",
        token=token,
        payload={"instance_uuid": instance_uuid},
    )
    logger.info("实例已释放：instance_uuid=%s", instance_uuid)


def cleanup_instance(instance_uuid: Optional[str] = None) -> None:
    """训练结束后的完整清理流程：关机 -> 轮询确认关机完成 -> 释放。

    安全判断是否可以调用 release 的依据是"轮询 status 接口，实际观察到状态
    变为 shutdown"，而不是"power_off 请求本身返回了 200/Success 就直接往下
    调 release"—— power_off 只是异步下发指令，实测对还处于 running/
    shutting_down 状态的实例调用 release 会被 100% 拒绝
    （BadRequest / "请在实例关机状态下执行释放操作"）。
    """
    token = _get_token()
    target_uuid = _get_instance_uuid(instance_uuid)

    logger.info("开始清理流程，目标实例：%s", target_uuid)

    current_status = get_status(target_uuid, token)
    if current_status == SHUTDOWN_DONE_STATE:
        logger.info("实例已经是 shutdown 状态，跳过 power_off，直接释放。")
    else:
        power_off(target_uuid, token)
        wait_until_shutdown(target_uuid, token)

    release(target_uuid, token)
    logger.info("清理流程完成：实例 %s 已关机并释放。", target_uuid)


def run_training() -> None:
    """占位：这里替换成你真正的训练逻辑（例如调用你的 train.py 里的 main()）。"""
    logger.info("训练任务开始（示例占位，请替换为真实训练代码）...")
    time.sleep(1)
    logger.info("训练任务结束。")


def main() -> int:
    """训练 + 清理的主流程。

    用 try/finally 包裹训练逻辑：无论训练是正常跑完还是中途抛异常，finally
    里的清理都会执行，避免训练失败时实例被落下没人管、一直计费。
    """
    training_error: Optional[BaseException] = None
    try:
        run_training()
    except BaseException as exc:  # noqa: BLE001 - 训练异常也要保证清理会执行
        training_error = exc
        logger.exception("训练过程中发生异常，仍会继续执行清理流程。")
    finally:
        try:
            cleanup_instance()
        except Exception:
            logger.exception(
                "清理流程本身失败了 —— 实例可能仍在运行/计费，请登录 AutoDL 控制台"
                "手工检查并关机/释放。"
            )
            return 1

    if training_error is not None:
        # 清理已完成，但训练本身是失败的，仍以非零退出码告知调用方。
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
