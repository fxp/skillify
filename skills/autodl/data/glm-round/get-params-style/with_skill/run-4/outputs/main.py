#!/usr/bin/env python3
"""查询一台 AutoDL 容器实例（Pro）的当前状态。

用法：
    AUTODL_TOKEN=<你的token> AUTODL_INSTANCE_UUID=<实例uuid> python3 main.py

退出码（便于脚本里分支处理）：
    0  成功查到状态
    1  本地问题：环境变量缺失 / 网络异常 / 响应无法解析
    2  实例不存在（请求本身合法，是 UUID 对应不到实例）
    3  请求本身有误（参数错误）
    4  鉴权 / 账号权限问题
    5  其他未归类的 API 错误
"""

import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
STATUS_URL = f"{BASE_URL}/api/v1/dev/instance/pro/status"

# 已知会撞上的错误（code, msg 关键字）→ 归类。
# AutoDL 文档没有稳定的错误码枚举表，所以 code 之外再拿 msg 文本做兜底匹配。
NOT_FOUND_HINTS = ("RecordNotFoundError", "未查询到")
BAD_REQUEST_HINTS = ("RequestParameterIsWrong", "参数错误")
AUTH_HINTS = ("TORealName", "无当前资源访问权限", "Unauthorized")


def die(exit_code: int, message: str) -> None:
    print(message)
    sys.exit(exit_code)


def classify_api_error(code: str, msg: str) -> int:
    """把 API 层错误归到「实例不存在 / 请求写错 / 鉴权问题 / 其他」四类。"""
    if code in NOT_FOUND_HINTS or any(h in msg for h in NOT_FOUND_HINTS):
        return 2
    if code in BAD_REQUEST_HINTS or any(h in msg for h in BAD_REQUEST_HINTS):
        return 3
    if code in AUTH_HINTS or any(h in msg for h in AUTH_HINTS):
        return 4
    return 5


def main() -> None:
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    instance_uuid = os.environ.get("AUTODL_INSTANCE_UUID", "").strip()

    if not token:
        die(1, "错误：环境变量 AUTODL_TOKEN 未设置（控制台 → 账号 → 设置 → 开发者Token）。")
    if not instance_uuid:
        die(1, "错误：环境变量 AUTODL_INSTANCE_UUID 未设置（实例 ID 形如 pro-76576c61fdf1）。")

    try:
        # 两个容易踩的坑（均已实测验证，官方文档示例是错的/易误导）：
        # 1) Authorization 直接放裸 token，不要加 "Bearer " 前缀；
        # 2) GET 接口必须用查询字符串传参（params=），放进 json body 会报
        #    {"code": "RequestParameterIsWrong", "msg": "请求参数错误"}。
        resp = requests.get(
            STATUS_URL,
            headers={"Authorization": token},
            params={"instance_uuid": instance_uuid},
            timeout=15,
        )
    except requests.exceptions.RequestException as exc:
        die(1, f"错误：请求未能完成（网络/DNS/超时），不是 API 返回的业务错误：{exc}")

    if resp.status_code != 200:
        die(
            1,
            f"错误：HTTP {resp.status_code}，未拿到正常业务响应。"
            f"响应片段：{resp.text[:300]!r}。请检查 token 是否有效、本机网络能否访问 {BASE_URL}。",
        )

    try:
        payload = resp.json()
    except ValueError:
        die(1, f"错误：响应不是合法 JSON：{resp.text[:300]!r}")

    code = str(payload.get("code", ""))
    msg = str(payload.get("msg", ""))
    request_id = payload.get("request_id", "")

    if code == "Success":
        # data 直接就是状态字符串，如 "running"；starting/shutting_down 是实测存在
        # 但文档未列出的中间态，照原样打印，不要当作异常。
        status = payload.get("data")
        print(f"实例 {instance_uuid} 当前状态：{status}")
        return

    category = classify_api_error(code, msg)
    diag = f"（code={code!r}, msg={msg!r}, request_id={request_id!r}）"

    if category == 2:
        die(
            2,
            "实例不存在：请求本身是合法的，但这个 instance_uuid 对应不到任何实例。\n"
            f"  原始返回：{diag}\n"
            "排查建议：UUID 是否抄错（形如 pro-xxxxxxxxxxxx）；实例是否已被释放"
            "（已释放的实例查不到）。可调用 POST /api/v1/dev/instance/pro/list "
            "列出账号下现存的实例核对 UUID。代码和传参方式不需要改。",
        )
    elif category == 3:
        die(
            3,
            "请求本身有误：参数格式或传参方式不对，API 没有把这个请求当成合法查询。\n"
            f"  原始返回：{diag}\n"
            "排查建议：instance_uuid 是否为空串/带空格/混入换行；格式是否正确"
            "（形如 pro-xxxxxxxxxxxx 的字符串）；本脚本已按实测要求用 URL 查询字符串传参，"
            "若你改过代码，注意 GET 接口不能用 JSON body 传参。",
        )
    elif category == 4:
        die(
            4,
            "鉴权/账号权限问题：token 无效，或账号认证等级不够。\n"
            f"  原始返回：{diag}\n"
            "排查建议：核对 AUTODL_TOKEN 是否最新有效；未实名认证的账号先到控制台完成认证。",
        )
    else:
        die(5, f"其他 API 错误：{diag}")


if __name__ == "__main__":
    main()
