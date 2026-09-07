#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoDL 弹性部署「探路」脚本（全程只读，绝不创建任何资源）

回答两个问题：
  1. 当前账号（AUTODL_TOKEN 对应的账号）现在能不能创建弹性部署？
     —— 若不能，归因到三类之一：账号资质问题 / 接口用错 / 服务本身有问题
  2. RTX 4090 现在有没有库存？分别在哪些地区？

探测原理（只用只读接口，不发任何创建/修改请求）：
  - POST /api/v1/dev/wallet/balance
      查余额。任何有效 Token 都能调，先确认 Token 本身有效、顺便看余额。
  - POST /api/v1/dev/deployment/list   {"page_index": 1, "page_size": 10}
      查部署列表。它与「创建部署」同属"账号部署资源"类接口，权限门槛一致：
      未企业认证 → {"code":"BadRequest","msg":"无当前资源访问权限"}
      未实名认证 → {"code":"TORealName","msg":"未完成实名认证,认证后才可使用"}
      请求参数错 → {"code":"RequestParameterIsWrong","msg":"请求参数错误"}
      因此该接口返回 Success 即代表账号已过企业认证门槛、具备创建部署的资格；
      被拒时按错误码/错误信息归因，不需要真的去创建一个部署来试错。
  - POST /api/v1/dev/machine/region/gpu_stock   {"region_sign": ..., "gpu_name_set": ["RTX 4090"]}
      逐地区查 RTX 4090 库存。只读接口，未企业认证的账号也能正常调用。

安全声明：本脚本只调用上述三个只读接口，绝不调用
  POST /api/v1/dev/deployment（创建部署）、PUT / DELETE 类管理接口、
  以及容器实例 Pro 的任何创建/开关机/释放接口。

其他约定（来自官方文档与实测）：
  - Base URL 固定 https://api.autodl.com
  - 鉴权头没有 Bearer 前缀：Authorization: <token>
  - 响应统一 {"code": "Success"/其他, "msg": ..., "data": ...}，无独立错误码枚举表
  - 金额字段是"元 × 1000"的整数；gpu_stock 的库存按"调度 1 张卡"口径统计

退出码：0=可创建部署；1=不可创建(账号资质)；2=接口用错；3=服务本身有问题；
        4=Token 未设置或无效；5=无法归类的未知错误
"""

import os
import sys
import time

import requests

BASE_URL = "https://api.autodl.com"
TIMEOUT = 15  # 单次请求超时（秒）
RETRIES = 2   # 网络类错误总尝试次数

TARGET_GPU = "RTX 4090"

# 地区代码全表（官方文档附录；创建部署的 dc_list 与查库存的 region_sign 同用这套代码）
REGIONS = [
    ("westDC2",      "西北企业区（推荐）"),
    ("westDC3",      "西北B区"),
    ("beijingDC1",   "北京A区"),
    ("beijingDC2",   "北京B区"),
    ("beijingDC4",   "L20专区（原北京C区）"),
    ("beijingDC3",   "V100专区（原华南A区）"),
    ("neimengDC1",   "内蒙A区"),
    ("neimengDC3",   "内蒙B区"),
    ("foshanDC1",    "佛山区"),
    ("chongqingDC1", "重庆A区"),
    ("yangzhouDC1",  "3090专区"),
]

# ---- 归因分类 ----
V_OK            = "ok"            # 具备创建部署权限
V_QUALIFICATION = "qualification" # 账号资质问题（未实名 / 未企业认证）
V_API_MISUSE    = "api_misuse"    # 接口用错（本脚本的请求构造有问题）
V_SERVICE       = "service"       # 服务本身有问题（网络不通 / 5xx / 响应异常）
V_TOKEN         = "token"         # Token 未设置或无效
V_UNKNOWN       = "unknown"       # 平台返回了文档未覆盖的错误，无法机械归类

EXIT_CODES = {
    V_OK: 0, V_QUALIFICATION: 1, V_API_MISUSE: 2,
    V_SERVICE: 3, V_TOKEN: 4, V_UNKNOWN: 5,
}

VERDICT_TEXT = {
    V_OK:            "✅ 可以创建部署",
    V_QUALIFICATION: "❌ 账号资质问题（不是接口用错，也不是服务故障）",
    V_API_MISUSE:    "❌ 接口用错了（请求构造问题，需要修脚本/参数）",
    V_SERVICE:       "❌ 服务本身有问题（网络或平台侧故障）",
    V_TOKEN:         "❌ Token 未设置或无效",
    V_UNKNOWN:       "⚠️ 无法归类（平台返回了文档未覆盖的错误）",
}


def call_api(session, method, path, *, json_body=None):
    """调用 AutoDL API，把响应归一成 dict；网络异常自动重试一次。"""
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.request(method, BASE_URL + path, json=json_body, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_err = "%s: %s" % (type(exc).__name__, exc)
            if attempt < RETRIES:
                time.sleep(1.5)
                continue
            return {"http_status": None, "code": None, "msg": "", "data": None,
                    "raw": "", "network_error": last_err}
        try:
            body = resp.json()
        except ValueError:
            return {"http_status": resp.status_code, "code": None, "msg": "",
                    "data": None, "raw": resp.text[:500], "network_error": None}
        return {"http_status": resp.status_code, "code": body.get("code"),
                "msg": body.get("msg", ""), "data": body.get("data"),
                "raw": "", "network_error": None}


def classify_failure(r):
    """把 deployment/list 的一次失败调用归因到：账号资质 / 接口用错 / 服务故障。

    平台没有稳定的错误码枚举表，只能靠 code + msg 文本 + HTTP 状态判断。
    """
    code = r["code"] or ""
    msg = r["msg"] or ""
    status = r["http_status"]

    if r["network_error"]:
        return (V_SERVICE,
                "网络请求失败：%s" % r["network_error"],
                "检查本机网络/代理后重跑；若持续失败，到 AutoDL 控制台或服务状态页确认平台是否正常。")
    if r["raw"]:
        return (V_SERVICE,
                "响应不是 JSON（HTTP %s）：%s" % (status, r["raw"][:200]),
                "网关/平台返回了异常内容，稍后重试；持续出现则联系 AutoDL 支持。")
    if status is not None and status >= 500:
        return (V_SERVICE,
                "服务端返回 HTTP %s（code=%s, msg=%s）" % (status, code, msg),
                "平台侧错误，稍等重试；持续出现则联系 AutoDL 支持或查看服务状态。")
    if code == "TORealName" or "实名认证" in msg:
        return (V_QUALIFICATION,
                "账号未完成实名认证（code=%s, msg=%s）" % (code, msg),
                "到 AutoDL 控制台完成个人实名认证后重跑本脚本。这是账号前置条件，"
                "不是代码问题也不是服务故障，重试或改参数都没用。")
    if "无当前资源访问权限" in msg or (code == "BadRequest" and ("权限" in msg or "认证" in msg)):
        return (V_QUALIFICATION,
                "账号未完成企业认证，无部署资源访问权限（code=%s, msg=%s）" % (code, msg),
                "弹性部署的创建/管理类接口需要企业认证：到控制台完成企业认证后再试；"
                "若暂不做企业认证，可改用容器实例 Pro API（个人实名即可）跑单机推理服务。")
    if "权限" in msg or "认证" in msg:
        return (V_QUALIFICATION,
                "疑似认证/权限不足（code=%s, msg=%s）" % (code, msg),
                "到控制台核对账号认证状态（实名认证 + 企业认证）后重跑。")
    if code == "RequestParameterIsWrong" or "参数" in msg:
        return (V_API_MISUSE,
                "平台判定请求参数错误（code=%s, msg=%s）" % (code, msg),
                "本脚本发的是 JSON body 的 POST 请求；报参数错误说明平台接口可能已改版，"
                "请对照官方文档（autodl.com/docs/esd_api_doc/）核对该接口的路径与参数。")
    return (V_UNKNOWN,
            "文档未覆盖的错误（HTTP %s, code=%s, msg=%s）" % (status, code, msg),
            "请把上方原始响应对照官方文档，或询问 AutoDL 支持后再判断。")


def main():
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print("❌ 环境变量 AUTODL_TOKEN 未设置。")
        print("   获取方式：AutoDL 控制台 → 账号 → 设置 → 开发者Token")
        return EXIT_CODES[V_TOKEN]

    session = requests.Session()
    # AutoDL 的鉴权头没有 Bearer 前缀，直接放 token 原值
    session.headers.update({"Authorization": token})

    # ---------- 第 1 步：校验 Token（查余额，只读） ----------
    print("=" * 64)
    print("第 1 步 / 3：校验 Token（POST /api/v1/dev/wallet/balance，只读）")
    print("=" * 64)
    r = call_api(session, "POST", "/api/v1/dev/wallet/balance")
    if r["network_error"]:
        print("❌ 网络请求失败：%s" % r["network_error"])
        print("   连 AutoDL API 都无法连通，属于网络/服务问题，后续探测无法进行。")
        return EXIT_CODES[V_SERVICE]
    if r["raw"]:
        print("❌ 响应不是 JSON（HTTP %s）：%s" % (r["http_status"], r["raw"][:200]))
        print("   平台/网关返回异常内容，属于服务侧问题。")
        return EXIT_CODES[V_SERVICE]
    if r["http_status"] is not None and r["http_status"] >= 500:
        print("❌ 服务端错误：HTTP %s" % r["http_status"])
        return EXIT_CODES[V_SERVICE]
    if r["code"] != "Success":
        print("❌ 查余额失败（HTTP %s, code=%s, msg=%s）"
              % (r["http_status"], r["code"], r["msg"]))
        print("   查余额对任何有效 Token 都开放，它失败基本等于 Token 本身无效/过期，")
        print("   请检查 AUTODL_TOKEN 是否为控制台『开发者Token』的原值（不要加 Bearer 前缀）。")
        return EXIT_CODES[V_TOKEN]

    wallet = r["data"] or {}
    assets = wallet.get("assets", 0)
    blocked = wallet.get("blocked_asset", 0)
    available = (assets - blocked) / 1000.0  # 金额字段是"元 × 1000"的整数
    print("✅ Token 有效。可用余额：%.2f 元（冻结 %.2f 元，累计消费 %.2f 元）"
          % (available, blocked / 1000.0, wallet.get("accumulate", 0) / 1000.0))
    if available < 1:
        print("   ⚠️ 可用余额不足 1 元：即使资质通过，创建部署也会因余额不足被拒，建议先充值。")

    # ---------- 第 2 步：探测部署创建权限（查部署列表，只读） ----------
    print()
    print("=" * 64)
    print("第 2 步 / 3：探测能否创建弹性部署（POST /api/v1/dev/deployment/list，只读）")
    print("=" * 64)
    print("说明：「查部署列表」与「创建部署」同属部署资源类接口、权限门槛一致（需企业认证），")
    print("      用它探测权限既准确，又不会真的创建任何部署。")
    r = call_api(session, "POST", "/api/v1/dev/deployment/list",
                 json_body={"page_index": 1, "page_size": 10})
    if r["code"] == "Success":
        verdict = V_OK
        extra = ""
        if isinstance(r["data"], dict) and r["data"].get("result_total") is not None:
            extra = "（账号当前已有 %s 个部署）" % r["data"]["result_total"]
        reason = "部署资源类接口调用成功，账号已通过企业认证门槛，具备创建部署的资格。%s" % extra
        advice = ("可以进入创建部署阶段；创建前建议先按第 3 步的库存结果选择地区与 GPU 型号，"
                  "并注意 gpu_name_set 用型号名字符串（如 \"RTX 4090\"），不是容器实例 API 的 gpu_spec_uuid。")
    else:
        verdict, reason, advice = classify_failure(r)
    print(VERDICT_TEXT[verdict])
    print("   依据：%s" % reason)
    print("   建议：%s" % advice)

    # ---------- 第 3 步：查 RTX 4090 库存（逐地区，只读） ----------
    print()
    print("=" * 64)
    print("第 3 步 / 3：查询 %s 库存（POST /api/v1/dev/machine/region/gpu_stock，只读）"
          % TARGET_GPU)
    print("=" * 64)
    rows, failed, variant_seen = [], [], False
    for region_code, region_name in REGIONS:
        r = call_api(session, "POST", "/api/v1/dev/machine/region/gpu_stock",
                     json_body={"region_sign": region_code,
                                "gpu_name_set": [TARGET_GPU]})
        if r["code"] != "Success":
            why = r["network_error"] or ("HTTP %s code=%s msg=%s"
                                         % (r["http_status"], r["code"], r["msg"]))
            failed.append((region_name, region_code, why))
            continue
        # data 是列表，每项形如 {"RTX 4090": {"idle_gpu_num": n, "total_gpu_num": m, ...}}
        found = {}
        for item in (r["data"] or []):
            if not isinstance(item, dict):
                continue
            for gpu_name, stock in item.items():
                if isinstance(stock, dict):
                    found[gpu_name] = (stock.get("idle_gpu_num", 0),
                                       stock.get("total_gpu_num", 0))
        rows.append((region_name, region_code, found))

    for region_name, region_code, found in rows:
        if not found:
            print("   - %s（%s）：无该型号" % (region_name, region_code))
            continue
        parts = []
        for gpu_name, (idle, total) in found.items():
            parts.append("%s 空闲 %s / 总 %s" % (gpu_name, idle, total))
            if gpu_name != TARGET_GPU:
                variant_seen = True
        print("   - %s（%s）：%s" % (region_name, region_code, "；".join(parts)))
    for region_name, region_code, why in failed:
        print("   - %s（%s）：查询失败——%s" % (region_name, region_code, why))

    total_idle = sum(found[TARGET_GPU][0] for _, _, found in rows if TARGET_GPU in found)
    total_all = sum(found[TARGET_GPU][1] for _, _, found in rows if TARGET_GPU in found)
    in_stock = [(name, found[TARGET_GPU][0]) for name, _, found in rows
                if TARGET_GPU in found and found[TARGET_GPU][0] > 0]

    # ---------- 汇总结论 ----------
    print()
    print("=" * 64)
    print("探路结论")
    print("=" * 64)
    print("1) 能否创建弹性部署：%s" % VERDICT_TEXT[verdict])
    print("   原因：%s" % reason)
    if in_stock:
        regions_txt = "、".join("%s %s 张" % (n, i) for n, i in in_stock)
        print("2) %s 库存：共 %s 张空闲 / %s 张总数；有货地区：%s"
              % (TARGET_GPU, total_idle, total_all, regions_txt))
    else:
        print("2) %s 库存：查询的所有地区均无空闲卡（属库存问题，不是权限问题；换型号或稍后再试）"
              % TARGET_GPU)
    if variant_seen:
        print("   注：上方明细里还出现了 %s 的变体型号，创建部署时可一并放进 gpu_name_set。"
              % TARGET_GPU)
    if failed:
        print("   注：有 %d 个地区库存查询失败（见上方明细），不影响权限结论。" % len(failed))
    print("   注：库存按「调度 1 张卡」口径统计，数字不能当作能同时开多卡的保证。")
    print("3) 安全说明：本次探测只调用了只读接口（查余额 / 查部署列表 / 查库存），")
    print("   没有创建任何部署或实例，也没有修改账号下的任何资源。")
    return EXIT_CODES.get(verdict, EXIT_CODES[V_UNKNOWN])


if __name__ == "__main__":
    sys.exit(main())
