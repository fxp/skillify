#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询一台 AutoDL 容器实例(Pro)的当前状态。

用法:
    export AUTODL_TOKEN="你的开发者Token"            # 控制台 → 账号 → 设置 → 开发者Token
    export AUTODL_INSTANCE_UUID="pro-xxxxxxxxxxxx"   # 实例 UUID
    python3 main.py

核心设计——刻意区分两类失败, 因为排查方向完全不同:
  1)【实例不存在】(退出码 2): 请求本身合法, 只是这个 UUID 在当前账号下查不到。
     典型原因: UUID 抄错/没复制全、实例已被释放、实例属于别的账号。
     → 排查方向在实例一侧: 去控制台核对, 不用改代码。
  2)【请求有误】(退出码 3): 请求在"查哪台实例"这一步之前就被拒绝, 是参数/
     鉴权/本地环境变量的问题, 与实例是否存在无关。
     → 排查方向在请求一侧: 检查 Token、环境变量、传参方式。
  其余无法归类的情况(网络故障、服务端错误、未知错误码)退出码 4, 会原样打印
  服务端返回的 code/msg/request_id, 便于进一步定位或找客服。

实现依据(AutoDL 官方文档 + 真实调用验证):
  - Base URL 固定为 https://api.autodl.com;
  - 鉴权头是 "Authorization: <token>", 没有 "Bearer " 前缀;
  - GET 接口的参数必须放 URL 查询字符串(params=)。官方文档把示例写成 JSON body
    是错的, 实测用 body 传参会精确地返回"请求参数错误";
  - 响应统一为 {"code": "Success"/..., "msg": ..., "data": ...}, data 直接是状态
    字符串(如 "running")。平台没有公开的错误码枚举表, 已知的两个关键组合:
      RecordNotFoundError / "未查询到相关实例"  → 资源不存在, 请求本身合法
      RequestParameterIsWrong / "请求参数错误"  → 请求本身有问题
"""

import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
STATUS_URL = BASE_URL + "/api/v1/dev/instance/pro/status"
REQUEST_TIMEOUT_SECONDS = 15

# 退出码: 方便 shell/CI 里直接区分失败原因
EXIT_OK = 0
EXIT_INSTANCE_NOT_FOUND = 2  #【实例不存在】
EXIT_BAD_REQUEST = 3         #【请求有误】
EXIT_UNCLASSIFIED = 4        #【无法判定】网络/服务端/未知错误

# 实测观察到的状态值; starting/shutting_down 是中间态, 官方文档未列出。
# 平台可能新增状态, 查不到说明的按原文展示, 不当作错误。
STATUS_DESCRIPTIONS = {
    "starting": "启动中(刚创建或刚开机, 尚未完全就绪)",
    "running": "运行中",
    "shutting_down": "关机中(还没关完, 此时执行释放操作会被拒绝)",
    "shutdown": "已关机(此时可以重新开机或释放实例)",
}


def die(exit_code, message):
    print(message)
    sys.exit(exit_code)


def read_env(name):
    """读环境变量, 去掉首尾空白; 若值整体被引号包住则去掉引号并提醒。"""
    value = os.environ.get(name, "").strip()
    for quote in ('"', "'"):
        if len(value) >= 2 and value.startswith(quote) and value.endswith(quote):
            cleaned = value[1:-1].strip()
            print("[提示] 环境变量 %s 的值整体被引号包裹, 已自动去掉: %r → %r"
                  % (name, value, cleaned))
            value = cleaned
            break
    return value


def main():
    token = read_env("AUTODL_TOKEN")
    instance_uuid = read_env("AUTODL_INSTANCE_UUID")

    # ---- 1. 本地先检查环境变量: 缺了它们请求根本发不出去, 属于"请求有误" ----
    missing = [name for name, value in
               (("AUTODL_TOKEN", token), ("AUTODL_INSTANCE_UUID", instance_uuid))
               if not value]
    if missing:
        die(
            EXIT_BAD_REQUEST,
            "【请求有误】缺少环境变量: " + ", ".join(missing) + "\n"
            "  请求根本没有发出去, 和实例是否存在无关。需要设置:\n"
            "    AUTODL_TOKEN          开发者Token(控制台 → 账号 → 设置 → 开发者Token)\n"
            "    AUTODL_INSTANCE_UUID  实例UUID(格式形如 pro-76419909953e)",
        )

    # ---- 2. 发请求 ----
    try:
        resp = requests.get(
            STATUS_URL,
            headers={"Authorization": token},          # 注意: 没有 "Bearer " 前缀
            params={"instance_uuid": instance_uuid},   # GET 接口用查询字符串传参
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout:
        die(EXIT_UNCLASSIFIED,
            "【无法判定】请求超时(%ds): %s\n"
            "  网络不通或平台暂时无响应, 稍后重试即可; 这既不是实例不存在, 也不是参数错误。"
            % (REQUEST_TIMEOUT_SECONDS, STATUS_URL))
    except requests.exceptions.RequestException as exc:
        die(EXIT_UNCLASSIFIED,
            "【无法判定】网络请求失败: %s\n"
            "  常见原因是本机断网、DNS 解析失败或代理配置问题, 与实例本身无关。" % exc)

    # ---- 3. 解析响应: AutoDL 统一返回 {"code", "msg", "data", "request_id"} ----
    try:
        payload = resp.json()
    except ValueError:
        payload = None

    if not isinstance(payload, dict):
        body_preview = (resp.text or "").strip()[:200]
        die(EXIT_UNCLASSIFIED,
            "【无法判定】收到了非 JSON 响应(HTTP %s), 无法按平台的错误结构分类。\n"
            "  响应内容前 200 字符: %r\n"
            "  若持续出现, 多半是网关/平台侧问题, 可带着这段内容咨询 AutoDL 客服。"
            % (resp.status_code, body_preview))

    code = str(payload.get("code") or "")
    msg = str(payload.get("msg") or "")
    request_id = payload.get("request_id") or ""
    request_id_hint = ("(request_id=%s, 可提供给客服溯源)" % request_id) if request_id else ""

    # ---- 4. 成功 ----
    if resp.status_code == 200 and code == "Success":
        status = payload.get("data")
        description = STATUS_DESCRIPTIONS.get(status,
                                              "未知状态(平台可能新增了状态值, 原样展示)")
        print("实例 %s 当前状态: %s —— %s" % (instance_uuid, status, description))
        sys.exit(EXIT_OK)

    # ---- 5. 失败分类: 先识别"实例不存在", 再识别"请求有误", 其余原样上报 ----
    if code == "RecordNotFoundError" or "未查询到" in msg:
        die(EXIT_INSTANCE_NOT_FOUND,
            "【实例不存在】服务器确认请求格式合法, 但当前账号下查不到这台实例。\n"
            "  实例UUID: %s\n"
            "  服务端返回: code=%s, msg=%s %s\n"
            "  这个结果说明请求本身没问题, 排查方向在实例一侧:\n"
            "    1. 核对 UUID 是否复制完整、有无笔误(格式形如 pro-76419909953e);\n"
            "    2. 实例可能已被释放——已释放的实例查询不到, 实例列表接口也不会再返回它;\n"
            "    3. 确认这台实例属于 AUTODL_TOKEN 对应的账号: 拿 A 账号的 token 去\n"
            "       查 B 账号的实例, 得到的也是这个报错。"
            % (instance_uuid, code, msg, request_id_hint))

    if code == "RequestParameterIsWrong" or "请求参数错误" in msg:
        die(EXIT_BAD_REQUEST,
            "【请求有误】服务器在参数校验阶段就拒绝了请求, 还没走到\"查哪台实例\"这一步,\n"
            "  实例存不存在此时无从谈起。排查方向在请求一侧:\n"
            "    1. 检查 AUTODL_INSTANCE_UUID 的值, 不能为空、不能夹带引号/空格/换行\n"
            "       (当前实际发送的值: %r);\n"
            "    2. 如果改过本脚本: 这个 GET 接口的 instance_uuid 必须放 URL 查询字符串\n"
            "       (requests 的 params=), 放进 json= 会精确地触发这个错误——\n"
            "       官方文档示例恰好把传参方式写错了, 已实测验证;\n"
            "    3. 确认请求的是 GET %s, instance_uuid 是字符串类型。\n"
            "  服务端返回: code=%s, msg=%s %s"
            % (instance_uuid, STATUS_URL, code, msg, request_id_hint))

    if resp.status_code in (401, 403):
        die(EXIT_BAD_REQUEST,
            "【请求有误】鉴权失败(HTTP %s), Token 未被服务器接受。\n"
            "  服务端返回: code=%s, msg=%s %s\n"
            "  排查方向:\n"
            "    1. AUTODL_TOKEN 是否正确、是否已在控制台被重置\n"
            "       (控制台 → 账号 → 设置 → 开发者Token, 重新复制一次);\n"
            "    2. Token 复制时是否带上了多余字符。本脚本发送的头是\n"
            "       \"Authorization: <token>\"(无 Bearer 前缀), 若改过脚本别画蛇添足加 Bearer。"
            % (resp.status_code, code, msg, request_id_hint))

    # 平台没有公开的错误码枚举表, 识别不出来的不硬猜, 原样上报。
    # 已知参考: TORealName=账号未实名认证; BadRequest/"无当前资源访问权限"=账号权限
    # 等级不够; InternalError=平台侧内部错误(如规格暂无库存)。
    die(EXIT_UNCLASSIFIED,
        "【无法判定】平台返回了未识别的错误, 既不属于\"实例不存在\", 也不是常见的参数错误。\n"
        "  HTTP 状态: %s; 服务端返回: code=%r, msg=%r %s\n"
        "  可结合上面的已知错误码参考判断, 或带着 request_id 咨询 AutoDL 客服。"
        % (resp.status_code, code, msg, request_id_hint))


if __name__ == "__main__":
    main()
