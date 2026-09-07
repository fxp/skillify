#!/usr/bin/env python3
"""查询一台 AutoDL 容器实例（Pro）的当前状态。

用法：
    AUTODL_TOKEN=<开发者Token> AUTODL_INSTANCE_UUID=<实例UUID> python3 main.py

要点（来自 AutoDL 官方文档 + 实测验证）：
- 鉴权头是 ``Authorization: <token>``，没有 Bearer 前缀；
- GET /api/v1/dev/instance/pro/status 的 instance_uuid 必须放在 URL 查询字符串
  （官方文档示例误写成 JSON body，实测放 body 会返回 RequestParameterIsWrong）；
- 响应结构为 {"code": ..., "msg": ..., "data": ..., "request_id": ...}，成功时
  code == "Success"，data 直接就是状态字符串（如 "running"）；
- 官方没有错误码枚举表，只能结合 code 和 msg 文本判断错误原因。本脚本重点区分
  「实例不存在」（RecordNotFoundError / 未查询到相关实例）和「请求本身写错了」
  （RequestParameterIsWrong / 请求参数错误）两类错误——排查方向完全不同。
"""

import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
STATUS_URL = f"{BASE_URL}/api/v1/dev/instance/pro/status"
TIMEOUT_SECONDS = 15

# 退出码：不同的失败原因给不同的码，方便外层脚本判断
EXIT_OK = 0
EXIT_ENV_MISSING = 1
EXIT_INSTANCE_NOT_FOUND = 2
EXIT_BAD_REQUEST = 3
EXIT_AUTH_FAILED = 4
EXIT_API_ERROR = 5
EXIT_NETWORK_ERROR = 6

# 已实测到的实例状态及含义（starting / shutting_down 是文档未列出的中间态）
STATE_HINTS = {
    "starting": "开机中（刚创建或刚下发开机指令，还未完全就绪，此时不能释放）",
    "running": "运行中",
    "shutting_down": "关机中（还没关完，此时不要执行释放/保存镜像）",
    "shutdown": "已关机（此时才可以释放实例或保存镜像）",
}


def main() -> int:
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    instance_uuid = os.environ.get("AUTODL_INSTANCE_UUID", "").strip()

    missing = [
        name
        for name, value in (
            ("AUTODL_TOKEN", token),
            ("AUTODL_INSTANCE_UUID", instance_uuid),
        )
        if not value
    ]
    if missing:
        print(f"[环境变量缺失] 请先设置：{'、'.join(missing)}")
        print("  AUTODL_TOKEN         开发者Token（控制台 → 账号 → 设置 → 开发者Token）")
        print("  AUTODL_INSTANCE_UUID 实例UUID（形如 pro-76576c61fdf1）")
        return EXIT_ENV_MISSING

    # 注意：Authorization 头直接放 token，不带 Bearer 前缀
    try:
        resp = requests.get(
            STATUS_URL,
            headers={"Authorization": token},
            params={"instance_uuid": instance_uuid},  # GET 用查询字符串，不是 json body
            timeout=TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        print(f"[网络错误] 请求没能到达 AutoDL 服务器，请检查网络 / 代理设置：{exc}")
        return EXIT_NETWORK_ERROR

    if resp.status_code in (401, 403):
        print(f"[鉴权失败] HTTP {resp.status_code}：Token 无效或没有权限。")
        print("请到 控制台 → 账号 → 设置 → 开发者Token 重新获取，并确认 AUTODL_TOKEN 的值。")
        return EXIT_AUTH_FAILED

    if resp.status_code != 200:
        print(f"[HTTP 错误] 状态码 {resp.status_code}，响应原文：{resp.text[:500]}")
        return EXIT_API_ERROR

    try:
        body = resp.json()
    except ValueError:
        print(f"[响应异常] 返回的不是 JSON，响应原文：{resp.text[:500]}")
        return EXIT_API_ERROR

    code = str(body.get("code", ""))
    msg = str(body.get("msg", ""))
    request_id = str(body.get("request_id", ""))

    if code == "Success":
        status = body.get("data")
        hint = STATE_HINTS.get(status, "（未收录的状态，按原样展示）")
        print(f"实例 {instance_uuid} 当前状态：{status} —— {hint}")
        return EXIT_OK

    # 附上 request_id，方便拿着它去找官方排查
    rid = f"（request_id: {request_id}）" if request_id else ""

    # ── 情况一：实例不存在（请求本身是合法的，问题出在这台实例上）──────────
    # 实测特征：code=RecordNotFoundError，msg=未查询到相关实例
    if code == "RecordNotFoundError" or "未查询到" in msg or "不存在" in msg:
        print(f"[实例不存在] AutoDL 说查不到这台实例：{msg} {rid}")
        print("请求本身是合法的，问题出在实例上，建议按这个方向排查：")
        print(f"  1. 核对 AUTODL_INSTANCE_UUID（当前值：{instance_uuid}）是否复制完整、")
        print("     有没有多余的空格/引号/错位字符；")
        print("  2. 这台实例是否已经被释放——已释放的实例查询接口查不回来；")
        print("  3. 该 UUID 是否属于当前 Token 对应的账号（别的账号的实例查不到）。")
        print("  可调用 POST /api/v1/dev/instance/pro/list 列出本账号现存实例来交叉确认。")
        return EXIT_INSTANCE_NOT_FOUND

    # ── 情况二：请求本身写错了（实例可能好好的，是调用方式/参数格式有问题）──
    # 实测特征：code=RequestParameterIsWrong，msg=请求参数错误
    if code == "RequestParameterIsWrong" or "参数" in msg:
        print(f"[请求参数错误] 请求被服务端判为格式/参数不合法：{msg} {rid}")
        print("实例不一定有问题，是这次请求本身没写对，建议按这个方向排查：")
        print(f"  1. instance_uuid 的值（当前值：{instance_uuid}）是否为合法格式（形如")
        print("     pro-xxxxxxxxxxxx，不能为空、不能是 GPU 型号等其他 ID）；")
        print("  2. 是否复用了别的脚本报错——本脚本已按官方实测要求用 URL 查询字符串传参，")
        print("     如果你是在自己的代码里复现此错误，请检查是否误把参数放进了 JSON body。")
        return EXIT_BAD_REQUEST

    # ── 其他已知类型：账号资质 / 权限 / 平台内部错误 ──────────────────────
    print(f"[API 返回错误] code={code}，msg={msg} {rid}")
    if code == "TORealName" or "实名认证" in msg:
        print("账号未完成实名认证，请先到控制台完成认证后重试（重试请求没有意义）。")
    elif code == "BadRequest" or "权限" in msg:
        print("当前账号没有该资源的访问权限，请确认 Token 对应账号的认证等级/资源归属。")
    else:
        print("未知错误类型，可凭上方 request_id 联系 AutoDL 官方排查。")
    return EXIT_API_ERROR


if __name__ == "__main__":
    sys.exit(main())
