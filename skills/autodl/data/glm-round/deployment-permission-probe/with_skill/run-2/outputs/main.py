#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoDL 弹性部署「探路」脚本（纯只读，不会创建/修改/释放任何资源）。

目的
----
1. 判断当前账号（环境变量 AUTODL_TOKEN 对应的账号）【能不能创建弹性部署】；
2. 顺带查询 RTX 4090 在各地区的库存。

为什么用只读接口就能判断"能否创建部署"
--------------------------------------
AutoDL 弹性部署 API 的企业认证门槛是按接口类别生效的（2026-09 已用真实调用验证）：
`POST /api/v1/dev/deployment/list`（查部署列表）和创建部署 `POST /api/v1/dev/deployment`
同属"账号自己的部署资源"一类，共用同一道企业认证门槛——未企业认证的账号调它
会返回 {"code":"BadRequest","msg":"无当前资源访问权限"}。
所以本脚本用【只读】的 deployment/list 当主探针：
  - 返回 Success             -> 门槛已过，账号具备创建部署的权限资格；
  - 返回"无当前资源访问权限" -> 账号资质问题（未企业认证），创建部署同样会被拦；
  - "未完成实名认证"         -> 账号资质问题（连基础实名都没做）；
  - 参数错误 / 5xx / 超时     -> 分别对应"接口用错"/"服务问题"，与账号资质无关。
再用 GET /api/v1/dev/deployment/blacklist（同属部署资源类，也被同一道门槛拦截）
做交叉验证。查 GPU 库存不需要企业认证，所以无论权限结论如何都会照常查询。
全程不调用任何创建/开关机/删除类接口。

用法
----
    export AUTODL_TOKEN="你的开发者Token"    # 控制台 -> 账号 -> 设置 -> 开发者Token
    python3 main.py

退出码：0=权限层面可以创建部署；1=不能创建（账号资质问题）；
        2=接口用错/服务问题/无法归类；3=探路未完成（Token 无效或网络不通）。
"""

import json
import os
import sys

import requests

# Base URL 固定为官方地址；环境变量覆盖仅供本地 mock 自测，不影响默认行为
BASE_URL = os.environ.get("AUTODL_API_BASE", "https://api.autodl.com")
TIMEOUT_SECONDS = 15
TARGET_GPU = "RTX 4090"  # 弹性部署 API 用 GPU 型号名字符串（gpu_name_set），不是容器实例 Pro 那套 gpu_spec_uuid

# 地区代码表（创建部署的 dc_list 与查库存的 region_sign 共用这一套）
REGIONS = [
    ("westDC2", "西北企业区(推荐)"),
    ("westDC3", "西北B区"),
    ("beijingDC1", "北京A区"),
    ("beijingDC2", "北京B区"),
    ("beijingDC4", "L20专区(原北京C区)"),
    ("beijingDC3", "V100专区(原华南A区)"),
    ("neimengDC1", "内蒙A区"),
    ("neimengDC3", "内蒙B区"),
    ("foshanDC1", "佛山区"),
    ("chongqingDC1", "重庆A区"),
    ("yangzhouDC1", "3090专区"),
]

# 诊断类别：前三个对应用户要区分的三种原因，后两个是前置/兜底类别
CAT_OK = "OK"
CAT_ACCOUNT = "账号资质问题"
CAT_USAGE = "接口用错"
CAT_SERVICE = "服务/网络问题"
CAT_TOKEN = "Token 鉴权问题"
CAT_UNKNOWN = "无法归类"

# 退出码
EXIT_CAN_CREATE = 0        # 权限层面可以创建部署
EXIT_NO_PERMISSION = 1     # 不能创建：账号资质问题
EXIT_USAGE_OR_SERVICE = 2  # 接口用错 / 服务问题 / 无法归类
EXIT_PROBE_FAILED = 3      # 探路没完成：Token 无效或网络不通


# ---------------------------------------------------------------- 基础工具

def call_api(session, method, path, *, params=None, json_body=None):
    """发一次请求，返回统一结构；不抛网络异常（转成 transport_error）。"""
    url = BASE_URL + path
    try:
        resp = session.request(method, url, params=params, json=json_body,
                               timeout=TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as exc:
        return {"http_status": None, "body": None,
                "transport_error": "%s: %s" % (type(exc).__name__, exc), "text_head": ""}
    try:
        body = resp.json()
    except ValueError:
        body = None
    # 非 JSON 响应（比如网关吐 HTML）时保留一小段原文，方便排查
    text_head = "" if body is not None else resp.text[:200].replace("\n", " ")
    return {"http_status": resp.status_code, "body": body,
            "transport_error": None, "text_head": text_head}


def classify_result(res):
    """把一次调用的结果归入诊断类别。

    平台没有稳定的错误码枚举表，只能靠官方 msg 文本判断（技能包实测结论），
    所以这里的匹配以 msg 关键词 + HTTP 状态为主，匹配不到一律落到"无法归类"
    并展示原始响应，绝不猜。
    """
    if res["transport_error"]:
        return CAT_SERVICE, "请求未送达或超时（%s）——无法区分平台故障与本地网络问题" % res["transport_error"]

    status, body = res["http_status"], res["body"]
    if body is None:  # 响应不是 JSON
        if status is not None and status >= 500:
            return CAT_SERVICE, "HTTP %s 且响应非 JSON（疑似网关/服务端异常）：%s" % (status, res["text_head"])
        if status in (404, 405):
            return CAT_USAGE, "HTTP %s（接口路径或 HTTP 方法不对）" % status
        return CAT_UNKNOWN, "HTTP %s 且响应非 JSON：%s" % (status, res["text_head"])

    code = str(body.get("code", ""))
    msg = str(body.get("msg", ""))
    if code == "Success":
        return CAT_OK, ""
    # Token / 鉴权问题（此时下任何结论都不可靠，必须先换有效 Token）
    if (status in (401, 403) or "token" in msg.lower() or "unauthorized" in msg.lower()
            or "鉴权" in msg or "未登录" in msg):
        return CAT_TOKEN, "code=%r, msg=%r, HTTP=%s" % (code, msg, status)
    # 账号资质问题之一：未完成实名认证（创建任何资源的硬性前提）
    if code == "TORealName" or "实名认证" in msg:
        return CAT_ACCOUNT, "未完成实名认证（code=%r, msg=%r）" % (code, msg)
    # 账号资质问题之二：弹性部署的企业认证门槛
    if "无当前资源访问权限" in msg or "权限" in msg:
        return CAT_ACCOUNT, "无当前资源访问权限（code=%r, msg=%r）——弹性部署接口的企业认证门槛" % (code, msg)
    # 接口用错：参数/路径/方法
    if code == "RequestParameterIsWrong" or "参数" in msg:
        return CAT_USAGE, "请求参数被拒（code=%r, msg=%r）——先核对传参方式与字段" % (code, msg)
    if status in (404, 405):
        return CAT_USAGE, "HTTP %s（接口路径或 HTTP 方法不对）" % status
    # 服务问题
    if status >= 500 or code in ("InternalError", "ServiceUnavailable", "InternalServerError"):
        return CAT_SERVICE, "服务端错误（code=%r, msg=%r, HTTP=%s）" % (code, msg, status)
    return CAT_UNKNOWN, "code=%r, msg=%r, HTTP=%s" % (code, msg, status)


def brief(value, limit=300):
    """紧凑打印 JSON，超长截断。"""
    try:
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "…(截断)"


def step_banner(title):
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


# ---------------------------------------------------------------- 各探针

def probe_balance(session):
    """步骤1：查余额（只读）。用途：验证 Token 有效，顺带展示可用余额。"""
    step_banner("步骤 1/4  验证 Token 并查余额    POST /api/v1/dev/wallet/balance")
    res = call_api(session, "POST", "/api/v1/dev/wallet/balance")
    cat, detail = classify_result(res)
    print("  HTTP %s | 响应: %s" % (res["http_status"], brief(res["body"])))
    if cat == CAT_OK:
        data = (res["body"] or {}).get("data") or {}
        assets, blocked = data.get("assets"), data.get("blocked_asset") or 0
        # 金额单位是"元 x1000"的整数，可用余额 = (assets - blocked_asset) / 1000
        if isinstance(assets, int):
            print("  -> Token 有效；可用余额 %.2f 元（assets=%s, blocked_asset=%s，均除以 1000 换算为元）"
                  % ((assets - blocked) / 1000.0, assets, blocked))
        else:
            print("  -> Token 有效（余额字段缺失，原始响应见上）")
    else:
        print("  -> 失败：[%s] %s" % (cat, detail))
    return cat, detail


def probe_deployment_gate(session):
    """步骤2（主探针）：查部署列表（只读）。

    与创建部署共用同一道企业认证门槛，用它探测"能否创建部署"，
    避免真的创建资源。分页下标的基数（0 还是 1）文档没写死，
    先按 1 试，若报参数错误再退回 0 重试一次，避免把分页起点误判成"接口用错"。
    """
    step_banner("步骤 2/4  部署权限探针(主)     POST /api/v1/dev/deployment/list")
    for page_index in (1, 0):
        res = call_api(session, "POST", "/api/v1/dev/deployment/list",
                       json_body={"page_index": page_index, "page_size": 10})
        cat, detail = classify_result(res)
        wrong_param = (cat == CAT_USAGE
                       and str((res["body"] or {}).get("code")) == "RequestParameterIsWrong")
        if not wrong_param:
            break
        print("  page_index=%s 报参数错误，换 page_index=0 重试一次…" % page_index)
    print("  HTTP %s | 响应: %s" % (res["http_status"], brief(res["body"])))
    if cat == CAT_OK:
        print("  -> 探针通过：账号具备访问部署资源类的权限（与创建部署同一道门槛）")
    else:
        print("  -> 失败：[%s] %s" % (cat, detail))
    return cat, detail


def probe_blacklist(session):
    """步骤3（交叉验证）：查生效中的调度黑名单（只读，无参数）。

    同属"账号部署资源"类接口、同一道企业认证门槛，用它验证步骤2的结论
    是不是权限门槛造成，而不是 deployment/list 单个接口的问题。
    """
    step_banner("步骤 3/4  部署权限探针(交叉)  GET  /api/v1/dev/deployment/blacklist")
    res = call_api(session, "GET", "/api/v1/dev/deployment/blacklist")
    cat, detail = classify_result(res)
    print("  HTTP %s | 响应: %s" % (res["http_status"], brief(res["body"])))
    if cat == CAT_OK:
        print("  -> 探针通过：与部署资源类接口的权限门槛结论可互为印证")
    else:
        print("  -> 失败：[%s] %s" % (cat, detail))
    return cat, detail


def probe_gpu_stock(session):
    """步骤4：逐地区查 RTX 4090 库存（只读，且不需要企业认证，个人认证账号也能查）。"""
    step_banner("步骤 4/4  查 %s 库存      POST /api/v1/dev/machine/region/gpu_stock" % TARGET_GPU)
    results = []  # (region_code, region_name, idle_num or None, error_detail or None)
    for region_code, region_name in REGIONS:
        res = call_api(session, "POST", "/api/v1/dev/machine/region/gpu_stock",
                       json_body={"region_sign": region_code,
                                  "gpu_name_set": [TARGET_GPU]})
        cat, detail = classify_result(res)
        if cat != CAT_OK:
            print("  - %-12s(%s): 查询失败 —— %s" % (region_code, region_name, detail))
            results.append((region_code, region_name, None, detail))
            continue
        items = (res["body"] or {}).get("data")
        if not isinstance(items, list):
            items = []
        idle = 0
        for item in items:
            if isinstance(item, dict):
                idle += int(item.get("idle_gpu_num") or 0)
        if items:
            print("  - %-12s(%s): 空闲 %d 张；明细: %s"
                  % (region_code, region_name, idle,
                     " | ".join(render_stock_item(i) for i in items)))
        else:
            print("  - %-12s(%s): 无 %s 可调度条目" % (region_code, region_name, TARGET_GPU))
        results.append((region_code, region_name, idle, None))
    return results


def render_stock_item(item):
    """渲染单条库存记录；除已知识别的外，其余字段原样带出，避免丢信息。"""
    if not isinstance(item, dict):
        return repr(item)
    parts = []
    if item.get("gpu_name"):
        parts.append(str(item["gpu_name"]))
    parts.append("空闲 %s / 总量 %s" % (item.get("idle_gpu_num", "?"), item.get("total_gpu_num", "?")))
    for key in ("chip_corp", "cpu_arch"):
        if key in item:
            parts.append("%s=%s" % (key, item[key]))
    price = item.get("price")
    if isinstance(price, (int, float)):  # 价格单位同样是"元 x1000"
        parts.append("价格 %.2f 元/小时" % (price / 1000.0))
    known = {"gpu_name", "idle_gpu_num", "total_gpu_num", "chip_corp", "cpu_arch", "price"}
    extra = {k: v for k, v in item.items() if k not in known}
    if extra:
        parts.append("其他字段 %s" % brief(extra, 120))
    return "，".join(parts)


# ---------------------------------------------------------------- 结论与主流程

def verdict_text(gate_cat, gate_detail):
    """把主探针的归类结果翻译成明确结论 + 对应的应对建议。"""
    if gate_cat == CAT_OK:
        return ("✅ 结论：当前账号【可以】创建弹性部署。\n"
                "   依据：只读探针 deployment/list 返回 Success，说明已通过弹性部署的企业认证门槛\n"
                "   （该门槛与创建部署 POST /api/v1/dev/deployment 共用）。\n"
                "   注意：这只确认\"账号资质/权限\"这一关；真正创建时仍可能因所选地区库存不足\n"
                "   （报\"当前算力规格暂无库存\"，属正常可重试错误）或参数不合适而失败，与权限无关。")
    if gate_cat == CAT_ACCOUNT:
        if "实名认证" in gate_detail:
            return ("❌ 结论：当前账号【不能】创建弹性部署，原因属于【账号资质问题】。\n"
                    "   依据：%s。连基础实名认证都未完成，这是创建任何资源的硬性前提。\n"
                    "   应对：先到控制台完成个人实名认证；弹性部署还进一步要求企业认证，\n"
                    "   实名后若仍报\"无当前资源访问权限\"，再完成企业认证即可。" % gate_detail)
        return ("❌ 结论：当前账号【不能】创建弹性部署，原因属于【账号资质问题】。\n"
                "   依据：%s。\n"
                "   应对：到 AutoDL 控制台完成【企业认证】——改参数、换接口、加余额都绕不过这道门槛。\n"
                "   若暂时无法企业认证，可退而用容器实例 Pro API（个人实名即可）跑推理服务。" % gate_detail)
    if gate_cat == CAT_USAGE:
        return ("⚠️ 结论：探路请求本身被接口判为参数/路径错误，原因属于【接口用错】，\n"
                "   并不能据此判断账号有没有权限。\n"
                "   依据：%s。\n"
                "   应对：核对 ① Base URL 是否为 https://api.autodl.com ② 鉴权头是否为\n"
                "   \"Authorization: <token>\"（没有 Bearer 前缀）③ POST 用 JSON body、GET 用 query string\n"
                "   ④ 字段名/类型是否与文档一致。修正后重跑本脚本再下结论。" % gate_detail)
    if gate_cat == CAT_SERVICE:
        return ("⚠️ 结论：平台接口超时/5xx/不可达，原因属于【服务本身问题】（或本地网络不通）。\n"
                "   依据：%s。\n"
                "   应对：稍后重试；若所有只读接口都挂，可到官方渠道确认平台状态。\n"
                "   这不是账号资质问题，也不需要改代码。" % gate_detail)
    if gate_cat == CAT_TOKEN:
        return ("⛔ 结论：Token 鉴权失败，无法判断账号资质（Token 无效时任何结论都不可靠）。\n"
                "   依据：%s。\n"
                "   应对：到 控制台 → 账号 → 设置 → 开发者Token 重新获取，并更新环境变量 AUTODL_TOKEN。" % gate_detail)
    return ("⚠️ 结论：返回不符合任何已知的权限/参数/服务错误特征，无法归类，请结合上方原始响应\n"
            "   人工核对（已按\"接口用错或服务问题\"的退出码 2 处理）。依据：%s。" % gate_detail)


EXIT_BY_CATEGORY = {
    CAT_OK: EXIT_CAN_CREATE,
    CAT_ACCOUNT: EXIT_NO_PERMISSION,
    CAT_USAGE: EXIT_USAGE_OR_SERVICE,
    CAT_SERVICE: EXIT_USAGE_OR_SERVICE,
    CAT_UNKNOWN: EXIT_USAGE_OR_SERVICE,
    CAT_TOKEN: EXIT_PROBE_FAILED,
}


def cross_check_line(gate_cat, blacklist_cat):
    if gate_cat == blacklist_cat:
        if gate_cat == CAT_OK:
            return "   交叉验证：blacklist 探针同样通过，两个部署资源类接口结论一致。"
        return "   交叉验证：blacklist 探针返回同类错误，进一步印证上面的归类。"
    return ("   交叉验证：⚠️ 两个探针结果不一致（deployment/list=%s vs blacklist=%s），\n"
            "   以 deployment/list 为主，建议结合原始响应人工复核。" % (gate_cat, blacklist_cat))


def stock_summary(stock_results):
    in_stock = [(c, n, i) for (c, n, i, _err) in stock_results if i]
    failed = [(c, _n, err) for (c, _n, i, err) in stock_results if err]
    lines = []
    if in_stock:
        total = sum(i for _c, _n, i in in_stock)
        lines.append("   有货地区 %d 个，合计空闲 %d 张：%s"
                     % (len(in_stock), total,
                        "，".join("%s(%s，%d 张)" % (c, n, i) for c, n, i in in_stock)))
    else:
        lines.append("   所有已查地区当前均无空闲 %s（库存实时变动，可稍后再查）。" % TARGET_GPU)
    if failed:
        lines.append("   查询失败地区 %d 个：%s（不影响权限结论）"
                     % (len(failed), "、".join(c for c, _n, _e in failed)))
    lines.append("   口径提醒：库存按\"调度 1 张卡\"统计——数字为 2 不代表能同时占用 2 张卡，"
                 "多卡容器不一定调度得成。")
    return "\n".join(lines)


def main():
    print("AutoDL 弹性部署探路脚本（只读探针，不会创建/修改/释放任何部署、容器或实例）")
    print("Base URL: %s" % BASE_URL)

    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print("\n⛔ 环境变量 AUTODL_TOKEN 未设置。请先：export AUTODL_TOKEN=\"你的开发者Token\"")
        print("   Token 位置：AutoDL 控制台 → 账号 → 设置 → 开发者Token")
        sys.exit(EXIT_PROBE_FAILED)

    session = requests.Session()
    # AutoDL 鉴权头没有 Bearer 前缀，直接是 "Authorization: <token>"
    session.headers.update({"Authorization": token})

    # ---- 步骤 1：验证 Token ----
    bal_cat, bal_detail = probe_balance(session)
    if bal_cat == CAT_TOKEN:
        # Token 无效时所有接口都会同样失败，继续调用没有意义
        step_banner("探路结论")
        print(verdict_text(CAT_TOKEN, bal_detail))
        print("② RTX 4090 库存：未查询（Token 无效时库存接口同样会被拒）。")
        print("③ 安全声明：本次未创建、修改或释放任何资源。")
        sys.exit(EXIT_PROBE_FAILED)
    if bal_cat == CAT_SERVICE:
        print("  ⚠️ 网络/服务疑似不可用，仍继续尝试后续探针（也可能只是钱包接口单点故障）…")

    # ---- 步骤 2/3：部署权限（主探针 + 交叉验证） ----
    gate_cat, gate_detail = probe_deployment_gate(session)
    bl_cat, _bl_detail = probe_blacklist(session)

    # ---- 步骤 4：RTX 4090 库存（不需要企业认证，无论权限结论如何都查） ----
    stock_results = probe_gpu_stock(session)

    # ---- 汇总 ----
    step_banner("探路结论")
    print("① 能否创建弹性部署：")
    print(verdict_text(gate_cat, gate_detail))
    print(cross_check_line(gate_cat, bl_cat))
    if gate_cat == CAT_ACCOUNT:
        print("   另外：库存查询接口不需要企业认证，下面第②条的库存数据依然有效，"
              "可先评估机型再决定是否推进企业认证。")
    print("② RTX 4090 库存：")
    print(stock_summary(stock_results))
    print("③ 安全声明：本次运行只执行了只读查询（余额/部署列表/调度黑名单/GPU 库存），")
    print("   没有创建任何部署或实例。")
    sys.exit(EXIT_BY_CATEGORY.get(gate_cat, EXIT_USAGE_OR_SERVICE))


if __name__ == "__main__":
    main()
