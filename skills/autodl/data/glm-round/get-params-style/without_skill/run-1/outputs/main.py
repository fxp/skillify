#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询一台 AutoDL 容器实例(Pro)的当前状态。

用法:
    export AUTODL_TOKEN="你的开发者Token"            # 控制台 -> 设置 -> 开发者Token
    export AUTODL_INSTANCE_UUID="pro-xxxxxxxxxxxx"   # 实例ID(UUID)
    python3 main.py

接口依据(官方文档):
    - API文档(HOST/鉴权):    https://www.autodl.com/docs/common_api/
    - 容器实例Pro API(实例): https://www.autodl.com/docs/instance_pro_api/
      GET  {HOST}/api/v1/dev/instance/pro/status   参数 instance_uuid(必填)
      POST {HOST}/api/v1/dev/instance/pro/list     参数 page_index / page_size
    - 响应为统一信封: {"code": "Success", "data": ..., "msg": "", "request_id": "..."}

本脚本的重点是把两类失败区分开(排查方向完全不同):
    1) 实例不存在/不属于当前账号 —— 去核对 UUID 和实例本身;
    2) 请求本身有误(Token 无效、参数错、网络问题) —— 去修脚本侧配置。
官方文档没有公布错误码表,所以判定依据是 HTTP 状态码 + code/msg 关键词;
信号模糊时,再用「实例列表接口」交叉验证该 UUID 是否真的存在于当前账号下,
尽量给出有依据的结论而不是猜测。

退出码:
    0  查询成功
    2  实例不存在(或当前账号下查不到)
    3  请求有误(缺少环境变量 / Token 无效 / 参数错误 / 网络失败)
    4  无法判定(服务端异常且交叉验证也失败)
"""

import json
import os
import sys

import requests

API_HOST = "https://api.autodl.com"
STATUS_URL = API_HOST + "/api/v1/dev/instance/pro/status"
LIST_URL = API_HOST + "/api/v1/dev/instance/pro/list"
TIMEOUT = (10, 30)  # (连接超时, 读取超时),单位秒
LIST_PAGE_SIZE = 100
LIST_MAX_PAGES = 50

EXIT_OK = 0
EXIT_NOT_FOUND = 2
EXIT_REQUEST_ERROR = 3
EXIT_UNKNOWN = 4

# code/msg 中的关键词。英文做小写子串匹配,中文原样匹配。
NOT_EXIST_HINTS = (
    "not exist", "not found", "no such", "does not exist", "doesn't exist",
    "unknown instance", "不存在", "未找到", "无此", "已释放",
)
AUTH_HINTS = (
    "unauthorized", "forbidden", "token", "credential", "auth",
    "鉴权", "认证", "授权", "令牌", "无权限", "权限不足", "未登录",
)

NOT_FOUND_HINT = """排查建议(问题在实例侧,不用改脚本):
    - 到 AutoDL 控制台核对环境变量 AUTODL_INSTANCE_UUID 是否抄错;
    - 实例可能已被释放,或属于其他账号/子账号;
    - 该开放接口面向「容器实例 Pro」,若实例是普通容器实例,请到控制台确认实例类型。"""

REQUEST_HINT = """排查建议(问题在请求侧,不用动实例):
    - 核对环境变量 AUTODL_TOKEN:控制台 -> 设置 -> 开发者Token,注意复制完整、无多余字符;
    - 容器实例Pro API 需要先完成个人实名认证或企业认证;
    - 确认本机网络/代理可以访问 api.autodl.com。"""


def match_any(text, hints):
    return any(h in text for h in hints)


def snippet(text, limit=400):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def describe_response(resp, payload):
    """把原始响应当成一行调试信息,便于排查时直接复制给支持人员。"""
    if isinstance(payload, dict):
        parts = ["HTTP %s" % resp.status_code,
                 "code=%r" % payload.get("code"),
                 "msg=%r" % payload.get("msg")]
        if payload.get("request_id"):
            parts.append("request_id=%s" % payload.get("request_id"))
    else:
        parts = ["HTTP %s" % resp.status_code, "body=%r" % snippet(resp.text)]
    return "    原始响应: " + ", ".join(str(p) for p in parts)


def extract_longest_list(node):
    """在未知结构的 data 里找最长的列表,用来判断分页是否已到最后一页。"""
    best = []
    if isinstance(node, list):
        best = node
        for item in node:
            sub = extract_longest_list(item)
            if len(sub) > len(best):
                best = sub
    elif isinstance(node, dict):
        for value in node.values():
            sub = extract_longest_list(value)
            if len(sub) > len(best):
                best = sub
    return best


def instance_exists_in_account(headers, instance_uuid):
    """用「实例列表」接口交叉验证 UUID 是否存在于当前账号。

    官方文档未给出 data 的详细结构,所以用「UUID 是否出现在整段 JSON 里」
    这种与结构无关的方式判断,分页结束与否用返回条数推测。

    返回 (True | False | None, 依据说明);None 表示无法确认。
    """
    for page in range(1, LIST_MAX_PAGES + 1):
        try:
            resp = requests.post(
                LIST_URL,
                json={"page_index": page, "page_size": LIST_PAGE_SIZE},
                headers=headers,
                timeout=TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            return None, "实例列表接口请求失败: %s: %s" % (exc.__class__.__name__, exc)
        if resp.status_code in (401, 403):
            return None, "实例列表接口返回 HTTP %s(Token 可能无效)" % resp.status_code
        try:
            payload = resp.json()
        except ValueError:
            return None, "实例列表接口返回非 JSON(HTTP %s)" % resp.status_code
        code = str(payload.get("code", ""))
        if code.lower() != "success":
            return None, "实例列表接口返回 code=%r msg=%r(HTTP %s)" % (
                payload.get("code"), payload.get("msg"), resp.status_code)
        data_text = json.dumps(payload.get("data"), ensure_ascii=False)
        if instance_uuid in data_text:
            return True, "账号实例列表第 %d 页中存在该 UUID" % page
        rows = extract_longest_list(payload.get("data"))
        if len(rows) < LIST_PAGE_SIZE:
            return False, "已遍历账号下实例列表共 %d 页,未见该 UUID" % page
    return None, "实例列表超过 %d 页,未能完整确认" % LIST_MAX_PAGES


def main():
    token = (os.environ.get("AUTODL_TOKEN") or "").strip()
    instance_uuid = (os.environ.get("AUTODL_INSTANCE_UUID") or "").strip()

    missing = [name for name, value in
               (("AUTODL_TOKEN", token), ("AUTODL_INSTANCE_UUID", instance_uuid))
               if not value]
    if missing:
        print("[请求有误] 缺少环境变量: %s" % "、".join(missing))
        print("    用法: export AUTODL_TOKEN='...' && "
              "export AUTODL_INSTANCE_UUID='...' && python3 main.py")
        return EXIT_REQUEST_ERROR

    headers = {"Authorization": token}

    # 第一步:直接查实例状态。
    # 官方文档把这个 GET 接口的参数写在「请求Body示例」里,没说明实际放
    # query 还是 body,这里两者都带,兼容服务端任意一种解析方式。
    try:
        resp = requests.get(
            STATUS_URL,
            params={"instance_uuid": instance_uuid},
            json={"instance_uuid": instance_uuid},
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        print("[请求有误] 请求未能送达 AutoDL API(网络层错误,与实例存在与否无关)。")
        print("    %s: %s" % (exc.__class__.__name__, exc))
        print(REQUEST_HINT)
        return EXIT_REQUEST_ERROR

    try:
        payload = resp.json()
    except ValueError:
        payload = None

    if resp.status_code == 200 and isinstance(payload, dict) \
            and str(payload.get("code", "")).lower() == "success":
        data = payload.get("data")
        if isinstance(data, str):
            status_text = data.strip() or "(空)"
        elif data is None:
            status_text = "(接口返回成功,但未返回状态字段)"
        else:
            status_text = json.dumps(data, ensure_ascii=False)
        print("[成功] 实例 %s 当前状态: %s" % (instance_uuid, status_text))
        if payload.get("request_id"):
            print("    request_id: %s" % payload.get("request_id"))
        return EXIT_OK

    # 第二步:失败了,先找明确信号。
    code = str(payload.get("code", "")) if isinstance(payload, dict) else ""
    msg = str(payload.get("msg", "")) if isinstance(payload, dict) else ""
    blended = (code + " " + msg).lower()
    looks_auth = resp.status_code in (401, 403) or match_any(blended, AUTH_HINTS)
    looks_missing = match_any(blended, NOT_EXIST_HINTS)

    if resp.status_code in (401, 403) or (looks_auth and not looks_missing):
        print("[请求有误] 鉴权/凭证被拒绝 —— 请求本身没被接受,实例存在与否未知。")
        print(describe_response(resp, payload))
        print(REQUEST_HINT)
        return EXIT_REQUEST_ERROR

    if looks_missing and not looks_auth:
        print("[实例不存在] 接口明确报告找不到该实例 —— 不是请求写错了。")
        print(describe_response(resp, payload))
        print(NOT_FOUND_HINT)
        return EXIT_NOT_FOUND

    # 第三步:信号模糊(如 4xx/5xx 且 msg 看不懂、非 JSON 响应等),
    # 用实例列表接口交叉验证,给出有依据的结论。
    exists, evidence = instance_exists_in_account(headers, instance_uuid)
    if exists is True:
        print("[请求有误] 状态接口报错,但账号实例列表里确实有这个 UUID ——"
              " 实例在,是这次状态查询请求本身出了问题。")
        print(describe_response(resp, payload))
        print("    交叉验证: %s" % evidence)
        print(REQUEST_HINT)
        return EXIT_REQUEST_ERROR
    if exists is False:
        print("[实例不存在] 状态接口报错,且账号实例列表里也找不到这个 UUID ——"
              " 问题在实例侧,不是请求写错了。")
        print(describe_response(resp, payload))
        print("    交叉验证: %s" % evidence)
        print(NOT_FOUND_HINT)
        return EXIT_NOT_FOUND

    print("[无法判定] 状态接口与实例列表接口都失败了,暂时无法区分是实例不存在还是请求有误。")
    print(describe_response(resp, payload))
    print("    交叉验证: %s" % evidence)
    print("    建议: 稍后重试;若持续出现,携带上面的 request_id 联系 AutoDL 支持。")
    return EXIT_UNKNOWN


if __name__ == "__main__":
    sys.exit(main())
