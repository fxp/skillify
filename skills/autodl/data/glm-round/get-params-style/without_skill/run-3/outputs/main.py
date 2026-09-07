#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询一台 AutoDL 容器实例的当前状态。

用法:
    export AUTODL_TOKEN="你的开发者Token"      # 控制台 -> 设置 -> 开发者Token
    export AUTODL_INSTANCE_UUID="实例ID"
    python3 main.py

设计要点:
    排查故障时, 「实例不存在」和「请求本身写错了」是方向完全不同的两类问题,
    本脚本把它们严格区分开, 分别给出不同的提示和不同的退出码:

        0  成功, 查到实例状态
        2  本地配置问题(环境变量没设置)
        3  实例不存在(或已释放 / 不属于当前 Token 对应的账号)
        4  请求本身有问题(参数、调用方式等被服务端拒绝)
        5  鉴权失败(Token 无效/无权限, 属于请求端问题)
        6  服务端错误(5xx, 建议稍后重试)
        7  网络错误(连不上/超时)
        1  其他未分类错误

接口依据(AutoDL 官方文档):
    GET https://api.autodl.com/api/v1/dev/instance/pro/status
    鉴权头: Authorization: <token>   (直接填 Token 本身, 不带 Bearer 前缀)
    请求体: {"instance_uuid": "<实例ID>"}
    成功响应: {"code": "Success", "data": "<状态>", "msg": "", "request_id": "..."}
"""

import json
import os
import sys

import requests

API_BASE = "https://api.autodl.com"
STATUS_URL = API_BASE + "/api/v1/dev/instance/pro/status"
TIMEOUT_SECONDS = 15

# ---- 退出码: 不同失败原因返回不同码, 方便上层脚本/CI 精确判断 ----
EXIT_OK = 0
EXIT_UNKNOWN = 1
EXIT_CONFIG = 2
EXIT_INSTANCE_NOT_FOUND = 3
EXIT_BAD_REQUEST = 4
EXIT_AUTH = 5
EXIT_SERVER = 6
EXIT_NETWORK = 7

# AutoDL 的业务错误统一放在响应体的 code/msg 里, 官方文档未枚举具体错误码,
# 这里通过业务码和错误文案中的关键词识别「实例不存在」这一类错误。
NOT_FOUND_KEYWORDS = (
    "not found", "notfound", "not_found",
    "not exist", "not_exist", "not_exists",
    "no such", "不存在", "未找到", "没有找到", "已释放", "已销毁",
)

# 鉴权类错误的关键词(Token 无效/过期/无权限等, 属于「请求端」问题)
AUTH_KEYWORDS = (
    "unauthorized", "forbidden", "auth", "token", "permission",
    "鉴权", "授权", "无权限", "令牌", "登录",
)


def _matches(keywords, *texts):
    """判断给定的业务码/错误文案里是否出现任一关键词。"""
    joined = " ".join(str(t) for t in texts if t).lower()
    return any(k in joined for k in keywords)


def fail(exit_code, title, detail="", advices=()):
    """按类别打印失败提示并退出; 不同类别的措辞、建议和退出码都不同。"""
    print("[失败] " + title)
    if detail:
        print("  响应/错误详情: " + detail)
    if advices:
        print("  排查建议:")
        for i, advice in enumerate(advices, 1):
            print("    %d. %s" % (i, advice))
    sys.exit(exit_code)


def main():
    token = (os.environ.get("AUTODL_TOKEN") or "").strip()
    instance_uuid = (os.environ.get("AUTODL_INSTANCE_UUID") or "").strip()

    missing = [name for name, value in
               (("AUTODL_TOKEN", token), ("AUTODL_INSTANCE_UUID", instance_uuid))
               if not value]
    if missing:
        fail(EXIT_CONFIG,
             "本地配置问题: 环境变量未设置 -> " + ", ".join(missing),
             advices=("请先在环境里设置 AUTODL_TOKEN(开发者Token) 和 "
                      "AUTODL_INSTANCE_UUID(实例ID) 再运行本脚本。",))

    headers = {
        # 官方要求: Authorization 头直接填 Token 本身, 不要加 "Bearer " 前缀
        "Authorization": token,
        "Content-Type": "application/json",
    }

    # 官方文档对该 GET 接口给出的是「请求 Body 示例」{"instance_uuid": ...},
    # 因此按文档携带 JSON body; 同时挂一份到 query string, 兼容两种网关取参方式。
    try:
        resp = requests.get(
            STATUS_URL,
            headers=headers,
            params={"instance_uuid": instance_uuid},
            json={"instance_uuid": instance_uuid},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout:
        fail(EXIT_NETWORK, "网络错误: 请求超时",
             "请求 %s 超过 %s 秒无响应。" % (STATUS_URL, TIMEOUT_SECONDS),
             ("检查本机网络/代理能否访问 api.autodl.com。",
              "网络恢复后重试。"))
    except requests.exceptions.RequestException as exc:
        fail(EXIT_NETWORK, "网络错误: 请求未能发出/未能建立连接",
             "%s: %s" % (type(exc).__name__, exc),
             ("检查本机网络、DNS 和代理设置。",))

    # 解析响应体(AutoDL 统一返回 JSON: code/msg/data/request_id)
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        payload = {}

    biz_code = str(payload.get("code") or "")
    biz_msg = str(payload.get("msg") or payload.get("errmsg") or "")
    request_id = str(payload.get("request_id") or "")

    detail = "HTTP %s" % resp.status_code
    if biz_code or biz_msg:
        detail += ", code=%r, msg=%r" % (biz_code, biz_msg)
    else:
        detail += ", body=%r" % (resp.text or "")[:200]
    if request_id:
        detail += ", request_id=%s" % request_id

    # ---- 1) 成功: 官方约定 code == "Success", data 即实例状态 ----
    if resp.status_code == 200 and biz_code.lower() == "success":
        status = payload.get("data")
        if isinstance(status, (dict, list)):
            status = json.dumps(status, ensure_ascii=False)
        print("实例 %s 当前状态: %s" % (instance_uuid, status))
        if request_id:
            print("(request_id: %s)" % request_id)
        return EXIT_OK

    not_found_like = _matches(NOT_FOUND_KEYWORDS, biz_code, biz_msg)
    auth_like = (resp.status_code in (401, 403)
                 or _matches(AUTH_KEYWORDS, biz_code, biz_msg))

    # ---- 2) 实例不存在 ----
    # AutoDL 的业务错误多数是 HTTP 200 + code/msg; 部分网关场景会直接回 404。
    # 本脚本调用的是官方文档固定的接口路径, 因此 404 优先按「实例不存在」处理。
    if not_found_like or resp.status_code == 404:
        suffix = "" if not_found_like else \
            "(HTTP 404 且未返回业务错误码, 大概率同样是实例不存在/已释放)"
        fail(EXIT_INSTANCE_NOT_FOUND,
             "实例不存在: 服务端查不到这台实例 " + suffix,
             detail,
             ("到 AutoDL 控制台核对实例 ID 是否抄对(多余空格、复制不全会导致查不到)。",
              "确认实例没有被释放——释放后的实例无法再查询。",
              "确认这台实例属于 AUTODL_TOKEN 对应的账号, 别人账号的实例你查不到。",
              "若以上都排除, 携带 request_id 咨询 AutoDL 客服确认接口是否有变更。"))

    # ---- 3) 请求本身有问题(鉴权/参数/调用方式), 注意: 不是「实例不存在」 ----
    if auth_like:
        fail(EXIT_AUTH,
             "请求被拒绝: 鉴权失败(Token 无效或无权限)。"
             "这属于「请求端」的问题, 不是实例不存在。",
             detail,
             ("到 控制台 -> 设置 -> 开发者Token 页面重新复制或重置 AUTODL_TOKEN。",
              "确认 Token 没有多余空格/换行, 也没有误加 \"Bearer \" 前缀(本脚本原样透传)。",
              "确认该 Token 未过期/未禁用, 且实例属于同一账号。"))

    if 500 <= resp.status_code < 600:
        fail(EXIT_SERVER,
             "服务端错误(5xx): 与你的参数无关, 不是实例不存在的问题。",
             detail,
             ("稍等片刻后重试。",
              "若持续出现, 携带 request_id 联系 AutoDL 客服。"))

    if resp.status_code in (400, 405, 422) or biz_code:
        fail(EXIT_BAD_REQUEST,
             "请求本身有问题: 参数或调用方式被服务端拒绝。"
             "这不是实例不存在——实例在不在还不知道, 请求先没通过校验。",
             detail,
             ("核对 AUTODL_INSTANCE_UUID 的取值与格式(到控制台重新复制一遍最稳妥)。",
              "优先按响应里 msg 的提示修正请求。",
              "若怀疑接口有变更, 对照官方文档核对路径与参数。"))

    fail(EXIT_UNKNOWN, "未能识别的响应, 请根据详情判断", detail,
         ("携带 request_id 与上述详情咨询 AutoDL 客服。"))


if __name__ == "__main__":
    sys.exit(main())
