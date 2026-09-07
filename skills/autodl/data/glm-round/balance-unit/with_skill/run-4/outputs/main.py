#!/usr/bin/env python3
"""AutoDL 账户余额监控脚本（运维值班用）。

查询 AutoDL 账户可用余额并按「元」打印；可用余额低于 20 元时打印醒目告警。
设计为直接被监控系统 / cron 以 `python3 main.py` 方式调用。

用法：
    AUTODL_TOKEN=<你的开发者Token> python3 main.py

Token 获取：AutoDL 控制台 → 账号 → 设置 → 开发者Token。

退出码约定（监控据此区分"低余额告警"和"脚本故障"）：
    0  查询成功，可用余额不低于阈值
    1  查询成功，但可用余额低于阈值（低余额告警）
    2  脚本故障（Token 未配置 / 网络失败 / API 报错 / 响应结构异常）。
       故障时绝不打印任何余额数字——宁可报故障，也不能让监控把失败误读成余额正常。

接口依据（AutoDL 官方 API 文档 https://www.autodl.com/docs/common_api/）：
    POST https://api.autodl.com/api/v1/dev/wallet/balance（无请求参数）
    鉴权头为 `Authorization: <token>`，注意没有 Bearer 前缀。
    响应顶层结构 {"code": "Success"/其他, "msg": "...", "data": {...}}，
    code 不等于 "Success" 即为失败。

⚠️ 单位（务必不要再搞错，历史上这里翻过车）：
    API 返回的 assets / blocked_asset 等金额字段是整数，单位是「元 × 1000」
    （毫元），必须除以 1000 才是元——已用真实调用验证：余额 29.29 元时
    assets 返回 29290。本脚本全程用整数（毫元）做比较和运算，仅在最终
    展示时做精确的十进制换算，不经过浮点运算，保证监控数字准确。
    可用余额 = (assets - blocked_asset) / 1000，blocked_asset 是冻结金额，
    冻结的钱不能花，不能只看 assets。
"""

import os
import sys
import time

import requests

API_BASE = "https://api.autodl.com"
BALANCE_ENDPOINT = f"{API_BASE}/api/v1/dev/wallet/balance"

ALARM_THRESHOLD_YUAN = 20  # 低余额告警阈值（元）
# 阈值换算成毫元（元 × 1000）做整数比较，避免浮点误差在 20 元边界误报/漏报。
# 「低于 20 元」按严格小于处理：恰好 20.000 元不告警。
ALARM_THRESHOLD_MILLI = ALARM_THRESHOLD_YUAN * 1000

REQUEST_TIMEOUT = 15  # 秒。监控脚本必须带超时，否则网络挂起会卡住整个监控
MAX_ATTEMPTS = 3      # 失败重试次数，避免偶发网络抖动造成误报/漏报
RETRY_INTERVAL = 2    # 重试间隔（秒）

EXIT_OK = 0
EXIT_LOW_BALANCE = 1
EXIT_ERROR = 2


def fail(message: str) -> None:
    """打印故障信息并以退出码 2 结束（故障 ≠ 余额正常，监控必须能区分）。"""
    print(f"[错误] {message}", file=sys.stderr)
    sys.exit(EXIT_ERROR)


def parse_balance(payload: object) -> tuple:
    """校验余额响应并返回 (assets, blocked_asset)，均为整数毫元。

    结构不符 / 业务失败 / 字段缺失或类型异常时抛 ValueError。
    对结构宁可不信任也不猜：解析不了就当故障退出，绝不输出错误数字。
    """
    if not isinstance(payload, dict):
        raise ValueError(f"响应顶层不是 JSON 对象：{payload!r}")
    if payload.get("code") != "Success":
        raise ValueError(
            f"API 返回失败：code={payload.get('code')!r}, msg={payload.get('msg')!r}"
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"响应缺少 data 对象：{payload!r}")
    assets = data.get("assets")
    blocked = data.get("blocked_asset", 0)  # 真实响应已验证有此字段；缺失则按 0 冻结
    if not isinstance(assets, int) or not isinstance(blocked, int):
        # 按已验证的行为，金额字段应为整数；出现其他类型说明 API 行为变了，
        # 拒绝猜测，报故障让人来确认，防止单位/类型变化导致告警失灵。
        raise ValueError(
            f"金额字段类型异常（预期整数毫元）：assets={assets!r}, "
            f"blocked_asset={blocked!r}"
        )
    return assets, blocked


def fetch_balance_milli(token: str) -> tuple:
    """调用余额接口，返回 (余额毫元, 冻结毫元)。

    带超时和有限次重试；重试耗尽仍失败则直接以退出码 2 结束。
    """
    last_error = "未知错误"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                BALANCE_ENDPOINT,
                # 注意：AutoDL 的鉴权头没有 Bearer 前缀，直接放 token
                headers={"Authorization": token},
                timeout=REQUEST_TIMEOUT,
            )
            try:
                payload = resp.json()
            except ValueError:
                raise ValueError(
                    f"HTTP {resp.status_code}，响应不是合法 JSON：{resp.text[:200]!r}"
                )
            return parse_balance(payload)
        except requests.RequestException as exc:
            last_error = f"网络请求失败：{exc}"
        except ValueError as exc:
            last_error = str(exc)
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_INTERVAL)
    fail(f"查询余额失败（已尝试 {MAX_ATTEMPTS} 次）：{last_error}")


def format_yuan(milli: int) -> str:
    """把整数毫元（元 × 1000）精确格式化成元的字符串（3 位小数）。

    用整数除法而不是 milli / 1000 浮点除，结果精确到毫（0.001 元），
    不存在二进制浮点误差。
    """
    sign = "-" if milli < 0 else ""
    milli = abs(milli)
    return f"{sign}{milli // 1000}.{milli % 1000:03d}"


def main() -> None:
    # 监控环境（cron 等）locale 常常是 ASCII，这里强制 UTF-8 输出，
    # 保证告警横幅里的字符在任何环境下都能打印、绝不为编码问题崩溃。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        fail("环境变量 AUTODL_TOKEN 未设置（Token 获取：控制台 → 账号 → 设置 → 开发者Token）")

    assets_milli, blocked_milli = fetch_balance_milli(token)
    available_milli = assets_milli - blocked_milli  # 冻结金额不可用，必须扣除

    available_str = format_yuan(available_milli)
    threshold_str = format_yuan(ALARM_THRESHOLD_MILLI)

    if available_milli < ALARM_THRESHOLD_MILLI:
        bar = "*" * 60
        print(bar)
        print("!!!          AutoDL 低余额告警  🚨🚨🚨          !!!")
        print(bar)
        print(f"  可用余额 {available_str} 元，已低于阈值 {threshold_str} 元")
        print(
            f"  账户余额 {format_yuan(assets_milli)} 元｜冻结 "
            f"{format_yuan(blocked_milli)} 元"
        )
        print("  请立即充值，避免 GPU 实例因欠费被停机！")
        print(bar)
        sys.exit(EXIT_LOW_BALANCE)

    print(
        f"[正常] AutoDL 可用余额：{available_str} 元"
        f"（账户余额 {format_yuan(assets_milli)} 元 - 冻结 "
        f"{format_yuan(blocked_milli)} 元，告警阈值 {threshold_str} 元）"
    )
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
