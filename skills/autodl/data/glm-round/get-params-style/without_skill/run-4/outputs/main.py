#!/usr/bin/env python3
"""查询一台 AutoDL 容器实例（Pro）的当前状态。

用法：
    AUTODL_TOKEN=你的开发者Token AUTODL_INSTANCE_UUID=pro-xxxxxxxxxxxx python3 main.py

接口依据（官方文档 https://www.autodl.com/docs/instance_pro_api/ ）：
    GET  https://api.autodl.com/api/v1/dev/instance/pro/status
         请求 Body：{"instance_uuid": "pro-xxxxxxxxxxxx"}
    POST https://api.autodl.com/api/v1/dev/instance/pro/list
         请求 Body：{"page_index": 1, "page_size": 100}
    鉴权：请求头 Authorization 直接放 Token（无 Bearer 前缀）。
    响应信封：{"code": "Success", "data": ..., "msg": "", "request_id": "..."}，
             code != "Success" 即业务错误（官方未枚举具体错误码）。

本脚本的核心设计：把两类失败严格区分开（排查方向完全不同）——
    「实例不存在」：Token、鉴权、请求格式都没问题，只是这个 UUID 查不到；
    「请求本身有误」：换任何 UUID 都不会成功（Token 无效/未实名/参数或格式错误）。
区分手段是交叉验证：状态接口报错后，用同一个 Token 再调一次「实例列表」——
    列表也失败   => 问题出在请求/凭证上（与实例是否存在无关）；
    列表能调通   => 凭证没问题，问题锁定在这个 UUID 上；
    列表里有该实例 => 直接用列表里的状态作答，并附上专用接口的错误原文。

退出码：0 查到状态；2 实例不存在；3 请求本身有误；4 网络错误；5 服务端/未知错误。
"""

import os
import sys

import requests

API_HOST = "https://api.autodl.com"
STATUS_URL = API_HOST + "/api/v1/dev/instance/pro/status"
LIST_URL = API_HOST + "/api/v1/dev/instance/pro/list"

CONNECT_TIMEOUT = 10   # 秒
READ_TIMEOUT = 30      # 秒
LIST_PAGE_SIZE = 100
LIST_MAX_PAGES = 50    # 防御性上限：最多翻 50 页

EXIT_OK = 0
EXIT_INSTANCE_NOT_FOUND = 2
EXIT_REQUEST_INVALID = 3
EXIT_NETWORK = 4
EXIT_SERVER_OR_UNKNOWN = 5


class ApiError(Exception):
    """AutoDL 接口返回的业务错误或非标准响应，保留原始信息用于展示。"""

    def __init__(self, http_status, code, msg, request_id=""):
        super().__init__(f"HTTP {http_status} code={code} msg={msg}")
        self.http_status = http_status
        self.code = code or ""
        self.msg = msg or ""
        self.request_id = request_id or ""

    def describe(self):
        parts = ["HTTP %s" % self.http_status]
        parts.append("code=%s" % (self.code or "(无错误码)"))
        if self.msg:
            parts.append("msg=%s" % self.msg)
        if self.request_id:
            parts.append("request_id=%s" % self.request_id)
        return "，".join(parts)


def api_call(method, url, token, payload=None):
    """调用接口，返回 (http_status, envelope, raw_text)。

    envelope 是形如 {"code": ..., "msg": ..., "data": ...} 的响应信封；
    响应不是这种结构时 envelope 为 None。网络层失败抛 requests.RequestException。
    """
    headers = {"Authorization": token, "Content-Type": "application/json"}
    resp = requests.request(
        method, url, headers=headers, json=payload,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    raw = resp.text
    try:
        body = resp.json()
    except ValueError:
        body = None
    envelope = body if isinstance(body, dict) and "code" in body else None
    return resp.status_code, envelope, raw


def unwrap(http_status, envelope, raw):
    """把响应信封拆成 (是否成功, data, ApiError)。"""
    if envelope is None:
        snippet = (raw or "").strip()[:200] or "(空响应)"
        return False, None, ApiError(
            http_status, "", "响应不是标准 JSON 信封，原文片段：" + snippet)
    code = envelope.get("code")
    msg = envelope.get("msg") or ""
    request_id = envelope.get("request_id") or ""
    if code == "Success":
        return True, envelope.get("data"), None
    return False, None, ApiError(http_status, code, msg, request_id)


def fetch_instance_status(token, instance_uuid):
    """查询单台实例状态，成功返回状态字符串（如 "running"），失败抛 ApiError。"""
    http_status, envelope, raw = api_call(
        "GET", STATUS_URL, token, {"instance_uuid": instance_uuid})
    ok, data, err = unwrap(http_status, envelope, raw)
    if not ok:
        raise err
    return data


def fetch_instance_list(token):
    """分页拉取本账号全部实例，成功返回实例 dict 列表，失败抛 ApiError。

    该接口只依赖 Token 和最简单的分页参数，不涉及任何具体实例，
    因此适合用来交叉验证「凭证/请求是否本身就有问题」。
    """
    items = []
    page_index = 1
    while page_index <= LIST_MAX_PAGES:
        http_status, envelope, raw = api_call(
            "POST", LIST_URL, token,
            {"page_index": page_index, "page_size": LIST_PAGE_SIZE})
        ok, data, err = unwrap(http_status, envelope, raw)
        if not ok:
            raise err
        data = data or {}
        items.extend(data.get("list") or [])
        try:
            max_page = max(1, int(data.get("max_page") or 1))
        except (TypeError, ValueError):
            max_page = 1
        if page_index >= max_page:
            break
        page_index += 1
    return items


# 常见状态的中文对照（官方文档只示例了 running/shutdown 等少数值，
# 未收录的状态按原文展示，不瞎猜）。
STATUS_ZH = {
    "starting": "启动中",
    "running": "运行中",
    "restarting": "重启中",
    "stopping": "关机中",
    "shutting_down": "关机中",
    "shutdown": "已关机",
    "stopped": "已关机",
    "releasing": "释放中",
    "released": "已释放",
    "error": "异常",
    "abnormal": "异常",
}


def format_status(status):
    if not isinstance(status, str) or not status.strip():
        return "未知（接口未返回状态字段）"
    s = status.strip()
    zh = STATUS_ZH.get(s.lower())
    if zh:
        return "%s（%s）" % (s, zh)
    return "%s（未收录的状态译文，按原文展示）" % s


# 仅用于给错误补充一句「服务端错误信息本身指向哪边」的旁证；
# 最终结论以「实例列表」交叉验证为准，不依赖这些关键词猜测。
NOT_FOUND_MARKERS = ("notfound", "not found", "notexist", "not exist",
                     "no such", "不存在", "未找到", "没有找到", "已释放")
REQUEST_MARKERS = ("token", "auth", "unauthorized", "forbidden", "permission",
                   "denied", "鉴权", "认证", "令牌", "无效", "param", "参数",
                   "json", "body", "format", "实名", "授权")


def guess_error_kind(err):
    blob = ("%s %s" % (err.code, err.msg)).lower()
    if any(m in blob for m in NOT_FOUND_MARKERS):
        return "instance"
    if any(m in blob for m in REQUEST_MARKERS):
        return "request"
    return "unclear"


def read_env():
    """读取环境变量，返回 (token, instance_uuid, 缺失项说明列表)。"""
    token = (os.environ.get("AUTODL_TOKEN") or "").strip()
    instance_uuid = (os.environ.get("AUTODL_INSTANCE_UUID") or "").strip()
    problems = []
    if not token:
        problems.append(
            "AUTODL_TOKEN 未设置或为空（获取位置：控制台 → 账号 → 设置 → 开发者Token）")
    if not instance_uuid:
        problems.append(
            "AUTODL_INSTANCE_UUID 未设置或为空（实例 UUID 形如 pro-xxxxxxxxxxxx）")
    return token, instance_uuid, problems


def print_kv(lines):
    for line in lines:
        print(line)


def handle_status_error(token, instance_uuid, err):
    """状态接口失败后的分类与报告：区分「实例不存在」和「请求本身有误」。"""
    print("「实例状态」接口返回错误：%s" % err.describe())
    print()
    print("正在用同一个 Token 调「实例列表」做交叉验证，"
          "以区分「实例不存在」和「请求写错了」……")
    print()

    # ---- 交叉验证：列表接口不涉及这台实例，只检验 Token 和请求本身 ----
    try:
        instances = fetch_instance_list(token)
    except requests.RequestException as exc:
        print("[网络错误] 交叉验证时网络中断：%r" % exc)
        print("这既不是「实例不存在」也不是「请求写错」，请检查网络后重试。")
        return EXIT_NETWORK
    except ApiError as list_err:
        if not list_err.code and list_err.http_status >= 500:
            print("[服务端错误] AutoDL 服务端暂时异常，无法完成判定。")
            print("  - 「实例状态」接口失败：%s" % err.describe())
            print("  - 「实例列表」接口也失败：%s" % list_err.describe())
            print("请稍后重试；若持续出现，可凭 request_id 联系 AutoDL 支持。")
            return EXIT_SERVER_OR_UNKNOWN
        # 连最基础的列表接口都失败：问题出在凭证/请求上，与这个 UUID 是否存在无关
        print("[结论：请求本身有误]（与实例是否存在无关，换任何 UUID 都不会成功）")
        print()
        print("判定依据：")
        print("  - 「实例状态」接口失败：%s" % err.describe())
        print("  - 用同一个 Token 调最基础的「实例列表」接口也失败：%s"
              % list_err.describe())
        print()
        print("排查建议：")
        print("  1. 检查 AUTODL_TOKEN 是否正确或已失效：控制台 → 账号 → 设置 → "
              "开发者Token，重新复制一份；")
        print("  2. 容器实例 Pro API 要求账号完成个人/企业实名认证，未实名会鉴权失败；")
        print("  3. 若错误提示参数/JSON/格式问题（如 HTTP 400），"
              "确认本脚本未被改动、环境变量值没有多余字符。")
        print()
        print("（当前 Token 下这台实例是否存在，暂时无法判断——先把请求修好再查。）")
        return EXIT_REQUEST_INVALID

    # ---- 列表能调通：Token、鉴权头、请求格式全部没问题 ----
    matched = [it for it in instances
               if isinstance(it, dict)
               and str(it.get("uuid") or "").strip() == instance_uuid]

    if matched:
        # 专用接口报错但实例确实存在：用列表里的状态回答，并保留错误原文
        it = matched[0]
        print("[查询成功]（状态取自「实例列表」：「实例状态」专用接口报错，"
              "但实例确实存在）")
        print("  实例 UUID：%s" % instance_uuid)
        line = "  当前状态：%s" % format_status(it.get("status"))
        if it.get("sub_status"):
            line += "，sub_status=%s" % it.get("sub_status")
        print(line)
        print()
        print("  专用接口的错误原文（可凭 request_id 反馈给 AutoDL）：%s"
              % err.describe())
        return EXIT_OK

    # 列表成功但没有这台实例。绝大多数情况（服务端返回业务错误码）即实例不存在；
    # 个别非标准响应（无错误码的 4xx/5xx）另行归类，避免误报。
    if err.code:
        print("[结论：实例不存在]（你的 Token 和请求本身都没问题，"
              "不用在凭证和参数上折腾）")
        print()
        print("判定依据：")
        print("  - 「实例状态」接口失败：%s" % err.describe())
        print("  - 同一个 Token 调「实例列表」成功（本账号共 %d 台实例），"
              "说明 Token、鉴权、请求格式都正常；" % len(instances))
        print("    但列表里没有这台实例。")
        if guess_error_kind(err) != "instance":
            print("  - 服务端错误信息没有明说原因，以上结论以交叉验证为准。")
        print()
        print("排查建议：")
        print("  1. 核对 AUTODL_INSTANCE_UUID 是否抄错"
              "（控制台实例页可查，形如 pro-xxxxxxxxxxxx）；")
        print("  2. 实例是否已被释放（释放后无法再查询）；")
        print("  3. Token 与实例是否属于同一个账号；")
        print("  4. 此 API 只覆盖「容器实例 Pro」；普通容器实例不在此范围内。")
        return EXIT_INSTANCE_NOT_FOUND

    if err.http_status in (400, 404):
        print("[结论：请求本身有误]（状态接口返回 HTTP %s 且无业务错误码，"
              "像是接口地址或请求格式的问题；列表接口正常说明 Token 没问题）"
              % err.http_status)
        print()
        print("  - 「实例状态」接口失败：%s" % err.describe())
        print("  - 「实例列表」接口正常。请确认本脚本未被改动（接口路径见文件头部注释）。")
        return EXIT_REQUEST_INVALID

    if err.http_status >= 500:
        print("[服务端错误] 「实例状态」接口返回 HTTP %s；"
              "且实例列表里也没有这台实例，暂无法给出确定结论。"
              % err.http_status)
        print("  - 错误原文：%s" % err.describe())
        print("  - 「实例列表」接口正常（本账号共 %d 台实例）。请稍后重试。"
              % len(instances))
        return EXIT_SERVER_OR_UNKNOWN

    print("[未知错误] 无法归类，完整证据如下，请凭 request_id 联系 AutoDL 支持：")
    print("  - 「实例状态」接口失败：%s" % err.describe())
    print("  - 「实例列表」接口正常（本账号共 %d 台实例，其中不含该 UUID）。"
          % len(instances))
    return EXIT_SERVER_OR_UNKNOWN


def main():
    token, instance_uuid, problems = read_env()
    if problems:
        print("[请求本身有误] 环境变量缺失，请求还没发出去就注定失败：")
        for p in problems:
            print("  - %s" % p)
        print()
        print("用法：AUTODL_TOKEN=xxx AUTODL_INSTANCE_UUID=pro-xxxxxxxxxxxx "
              "python3 main.py")
        return EXIT_REQUEST_INVALID

    try:
        status = fetch_instance_status(token, instance_uuid)
    except requests.RequestException as exc:
        print("[网络错误] 连不上 %s：%r" % (API_HOST, exc))
        print("这既不是「实例不存在」也不是「请求写错」，"
              "请先检查本机网络/代理/防火墙后重试。")
        return EXIT_NETWORK
    except ApiError as err:
        return handle_status_error(token, instance_uuid, err)

    print("[查询成功]")
    print("  实例 UUID：%s" % instance_uuid)
    print("  当前状态：%s" % format_status(status))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
