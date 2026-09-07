#!/usr/bin/env python3
"""查询一台 AutoDL 容器实例(Pro)的当前状态。

用法:
    AUTODL_TOKEN=<开发者Token> AUTODL_INSTANCE_UUID=<实例ID> python3 main.py

接口(依官方文档,2026-09 核对):
    GET https://api.autodl.com/api/v1/dev/instance/pro/status
    请求 Body: {"instance_uuid": "<实例ID>"}
    成功返回: {"code": "Success", "data": "<状态字符串>", "msg": "", "request_id": "..."}
    文档: https://www.autodl.com/docs/instance_pro_api/

本脚本的核心目标是把两类排查方向完全不同的失败显式区分开:
    A. 实例不存在    —— 请求本身是合法的,只是服务器上没有这台实例
                        (UUID 抄错 / 实例已被释放 / 实例不在当前 Token 的账号下);
    B. 请求本身有误  —— Token 失效、参数/格式错误、请求过于频繁等,
                        此时服务器还没轮到判断"实例存不存在"。
另外单独报告:本地环境变量缺失(请求未发出)、网络故障、AutoDL 服务端错误。
官方文档未公布错误码表,因此分类依据 = HTTP 状态码 + 业务 code/msg 的语义关键字,
并在所有失败输出里附上服务器原始响应,便于人工复核。

退出码:
    0  查询成功
    1  本地配置错误(环境变量缺失,请求未发出)
    2  实例不存在
    3  请求本身有误(鉴权 / 参数 / 频率限制)
    4  网络错误
    5  AutoDL 服务端错误(5xx,建议稍后重试)
    9  未归类错误
"""

import json
import os
import sys

import requests

API_HOST = "https://api.autodl.com"
STATUS_URL = f"{API_HOST}/api/v1/dev/instance/pro/status"
REQUEST_TIMEOUT = 15  # 秒

# 退出码:0 成功 / 1 本地配置 / 2 实例不存在 / 3 请求有误 / 4 网络 / 5 服务端 / 9 未归类
EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_NOT_FOUND = 2
EXIT_BAD_REQUEST = 3
EXIT_NETWORK = 4
EXIT_SERVER = 5
EXIT_UNKNOWN = 9

# 常见实例状态中文对照。官方文档只示例了 "running",其余按常见取值给出;
# 遇到未收录的值时原样展示,不做猜测。
STATUS_ZH = {
    "running": "运行中",
    "starting": "启动中",
    "restart": "重启中",
    "restarting": "重启中",
    "stopping": "关机中",
    "shutdown": "已关机",
    "stopped": "已关机",
    "releasing": "释放中",
    "released": "已释放",
    "error": "异常",
    "abnormal": "异常",
}

# 错误分类用的关键字(对业务 code + msg 的小写拼接文本做子串匹配)
NOT_FOUND_HINTS = ("notfound", "not found", "no such", "not exist",
                   "不存在", "未找到", "没有找到", "已释放", "已删除", "released", "deleted")
AUTH_HINTS = ("unauthorized", "forbidden", "token", "auth", "login",
              "鉴权", "认证", "登录", "权限")
RATE_HINTS = ("ratelimit", "rate limit", "too many", "频繁", "限流")
PARAM_HINTS = ("badrequest", "invalid", "param", "missing",
               "参数", "格式", "必填")


def snippet(text, limit=300):
    """压成单行并截断,便于放进错误提示里。"""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "...(截断)"


def report_not_found(raw_desc, request_id):
    print("[实例不存在] 请求已正常发出并到达 AutoDL,但服务器找不到这台实例——"
          "问题不在 Token 或请求格式上。", file=sys.stderr)
    print("  请沿这个方向排查:", file=sys.stderr)
    print("    1. AUTODL_INSTANCE_UUID 是否抄错(Pro 实例 ID 形如 pro-xxxxxxxxxxxx,"
          "控制台实例列表可查);", file=sys.stderr)
    print("    2. 该实例是否已被释放/删除(释放后原 UUID 即作废);", file=sys.stderr)
    print("    3. 该实例是否属于 AUTODL_TOKEN 对应的账号(须用实例所在账号的 Token 查询)。", file=sys.stderr)
    print(f"  服务器响应: {raw_desc}", file=sys.stderr)
    if request_id:
        print(f"  request_id: {request_id}(向客服反馈时可附上)", file=sys.stderr)


def report_bad_request(reason, raw_desc, request_id):
    print(f"[请求本身有误] {reason}", file=sys.stderr)
    print("  这种情况下服务器尚未判断实例是否存在——先修好请求,再谈实例问题。", file=sys.stderr)
    print("  请沿这个方向排查:", file=sys.stderr)
    print("    1. Token 是否有效/过期:www.autodl.com → 控制台 → 账号 → 设置 → 开发者Token,"
          "必要时重新生成并更新 AUTODL_TOKEN;", file=sys.stderr)
    print("    2. AUTODL_INSTANCE_UUID 是否完整、有无多余空格或换行;", file=sys.stderr)
    print("    3. 若提示请求过于频繁,等几十秒再试即可。", file=sys.stderr)
    print(f"  服务器响应: {raw_desc}", file=sys.stderr)
    if request_id:
        print(f"  request_id: {request_id}(向客服反馈时可附上)", file=sys.stderr)


def classify_and_report(resp, payload):
    """对失败响应分类并打印针对性提示。payload 为 dict,响应不是 JSON 对象时为 None。

    返回对应退出码。
    """
    status_code = resp.status_code
    code = msg = request_id = ""
    if payload is not None:
        code = str(payload.get("code", "") or "").strip()
        msg = str(payload.get("msg", "") or "").strip()
        request_id = str(payload.get("request_id", "") or "").strip()
    blob = f"{code} {msg}".lower()

    has_json_body = payload is not None
    raw_desc = f"HTTP {status_code}, code={code or '(空)'}, msg={msg or '(空)'}"
    if not has_json_body:
        raw_desc += f", 原始 body={snippet(resp.text)}"

    # ① 鉴权/权限类:请求侧问题(先于 404 判断,避免把"没权限看这台实例"误报成"实例不存在")
    if status_code in (401, 403) or any(h in blob for h in AUTH_HINTS):
        report_bad_request(
            f"鉴权失败(HTTP {status_code}):Token 无效/过期,或当前账号无权访问。",
            raw_desc, request_id)
        return EXIT_BAD_REQUEST

    # ② 实例不存在:请求合法,但目标资源找不到(HTTP 404,或业务 code/msg 明说不存在)
    if status_code == 404 or (has_json_body and any(h in blob for h in NOT_FOUND_HINTS)):
        report_not_found(raw_desc, request_id)
        if not has_json_body:
            print("  注意: 这个 404 的响应体不是标准业务 JSON,也可能是接口路径已变更,"
                  "请对照官方文档核实。", file=sys.stderr)
        return EXIT_NOT_FOUND

    # ③ 频率限制:请求侧(临时性)
    if status_code == 429 or any(h in blob for h in RATE_HINTS):
        report_bad_request("请求过于频繁,被限流(HTTP 429)。", raw_desc, request_id)
        return EXIT_BAD_REQUEST

    # ④ 参数/请求格式类:请求侧问题
    if status_code in (400, 405, 415, 422) or any(h in blob for h in PARAM_HINTS):
        report_bad_request(f"参数或请求格式有误(HTTP {status_code})。", raw_desc, request_id)
        return EXIT_BAD_REQUEST

    # ⑤ 服务端错误:请求和实例都可能没问题
    if status_code >= 500:
        print(f"[AutoDL 服务端错误] HTTP {status_code},请求大概率没问题,建议稍后重试。",
              file=sys.stderr)
        print(f"  服务器响应: {raw_desc}", file=sys.stderr)
        return EXIT_SERVER

    # ⑥ 兜底:无法归类,原样给出信息
    print("[未归类错误] 无法判断属于哪一类,请根据原始响应排查。", file=sys.stderr)
    print(f"  服务器响应: {raw_desc}", file=sys.stderr)
    if has_json_body:
        print(f"  完整响应: {json.dumps(payload, ensure_ascii=False)}", file=sys.stderr)
    return EXIT_UNKNOWN


def main():
    token = (os.environ.get("AUTODL_TOKEN") or "").strip()
    instance_uuid = (os.environ.get("AUTODL_INSTANCE_UUID") or "").strip()

    # 0) 本地配置:请求发出前就能确定的错误,单独归类,不和 API 返回混淆
    missing = []
    if not token:
        missing.append("AUTODL_TOKEN")
    if not instance_uuid:
        missing.append("AUTODL_INSTANCE_UUID")
    if missing:
        print(f"[本地配置错误] 缺少环境变量: {'、'.join(missing)}——"
              "请求尚未发出,与 AutoDL 服务和实例无关。", file=sys.stderr)
        if not token:
            print("  Token 获取: 登录 www.autodl.com → 控制台 → 账号 → 设置 → 开发者Token",
                  file=sys.stderr)
        if not instance_uuid:
            print("  实例 ID: 控制台实例列表中查看,Pro 实例形如 pro-xxxxxxxxxxxx",
                  file=sys.stderr)
        return EXIT_CONFIG

    headers = {"Authorization": token}  # 官方示例: headers = {"Authorization": "您的token"},无 Bearer 前缀

    # 官方文档把 GET 的参数放在请求 Body;这里同时带上 query 参数,
    # 以防中间层丢弃 GET body(服务器一般会忽略多余的 query 参数)。
    try:
        resp = requests.get(
            STATUS_URL,
            params={"instance_uuid": instance_uuid},
            json={"instance_uuid": instance_uuid},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        print(f"[网络错误] 请求 {STATUS_URL} 超时(>{REQUEST_TIMEOUT}s):本机网络或 AutoDL 服务不可达。",
              file=sys.stderr)
        return EXIT_NETWORK
    except requests.exceptions.ConnectionError as exc:
        print(f"[网络错误] 无法建立连接(DNS/网络/代理问题): {snippet(str(exc))}", file=sys.stderr)
        return EXIT_NETWORK
    except requests.exceptions.RequestException as exc:
        print(f"[未归类错误] 请求异常: {snippet(str(exc))}", file=sys.stderr)
        return EXIT_UNKNOWN

    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        payload = None

    # 成功:业务 code 为 "Success"(文档口径),data 即状态字符串
    if payload is not None and str(payload.get("code", "")).strip() == "Success":
        status = payload.get("data")
        if isinstance(status, str):
            zh = STATUS_ZH.get(status)
            suffix = f"({zh})" if zh else "(未收录的中文对照,以原始值为准)"
            print(f"实例 {instance_uuid} 当前状态: {status} {suffix}")
        else:
            print(f"实例 {instance_uuid} 查询成功, 原始 data: {json.dumps(status, ensure_ascii=False)}")
        return EXIT_OK

    return classify_and_report(resp, payload)


if __name__ == "__main__":
    sys.exit(main())
