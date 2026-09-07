#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoDL 弹性部署「探路」脚本（纯只读，绝不创建任何部署/实例）。

要回答的两件事：
  1. 当前账号到底能不能创建弹性部署；
  2. RTX 4090 现在有没有库存。

如果不能创建，把原因归入三类之一（三类应对方式完全不同）：
  A. 账号资质问题（未实名 / 未企业认证）  -> 去控制台补认证
  B. 接口用法问题（调用方式 / 传参错了）  -> 改代码
  C. 服务端问题（5xx / 超时 / 不可达）    -> 稍后重试或找客服
  另有一个前置问题：Token 本身无效        -> 先换 Token 再探测

探测思路（只调用只读查询接口，不触碰任何创建/停止/删除类接口）：
  1) POST /api/v1/dev/wallet/balance
     任何认证等级都可调。验证 Token 是否有效、服务是否可达。
  2) POST /api/v1/dev/image/private/list
     已验证「免企业认证」的只读接口。它成功即说明请求格式正确、服务正常，
     用来把「账号资质问题」和「接口用错 / 服务问题」区分开。
  3) POST /api/v1/dev/deployment/list      <-- 核心权限探针
     与「创建部署」同属「账号自己的部署资源」类接口，共享同一道企业认证门槛，
     且鉴权拦截发生在参数校验之前（未认证账号即使参数全对也会被拒）。
     因此：查部署列表成功 == 创建部署的认证门槛已通过，
     不需要真的创建一个部署来试。
  4) POST /api/v1/dev/machine/region/gpu_stock
     逐地区查 RTX 4090 库存，同样免企业认证。

用法：
  export AUTODL_TOKEN=你的开发者Token   # 控制台 -> 账号 -> 设置 -> 开发者Token
  python3 main.py

退出码：0 = 可以创建部署；1 = 不能（账号资质原因）；2 = 探路未定论（Token/接口/服务）。
依赖：仅 requests（pip install requests）。
"""

import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
TARGET_GPU = "RTX 4090"
TIMEOUT = 20  # 单次请求超时（秒）

# 地区代码表来自官方文档附录（www.autodl.com/docs/esd_api_doc/）
REGIONS = [
    ("westDC2", "西北企业区(推荐)"),
    ("westDC3", "西北B区"),
    ("beijingDC1", "北京A区"),
    ("beijingDC2", "北京B区"),
    ("beijingDC4", "L20专区"),
    ("beijingDC3", "V100专区"),
    ("neimengDC1", "内蒙A区"),
    ("neimengDC3", "内蒙B区"),
    ("foshanDC1", "佛山区"),
    ("chongqingDC1", "重庆A区"),
    ("yangzhouDC1", "3090专区"),
]

# 结论分类
CAT_OK = "OK"            # 可以创建部署
CAT_ACCOUNT = "ACCOUNT"  # A. 账号资质问题
CAT_USAGE = "USAGE"      # B. 接口用法问题
CAT_SERVICE = "SERVICE"  # C. 服务端问题
CAT_TOKEN = "TOKEN"      # 前置问题：Token 无效
CAT_UNKNOWN = "UNKNOWN"  # 无法自动归类，需人工看原始返回


def call_api(session, method, path, json_body=None):
    """调用 AutoDL API 并解析统一响应体 {"code", "msg", "data"}。

    返回 dict：net_ok（网络层是否成功）/ status / code / msg / data。
    网络层失败（超时、连接失败、5xx、非 JSON 响应）一律 net_ok=False，
    归入「服务端问题」方向处理。

    注意：AutoDL 的鉴权头没有 Bearer 前缀，直接是 Authorization: <token>。
    """
    try:
        resp = session.request(method, BASE_URL + path, json=json_body, timeout=TIMEOUT)
    except requests.RequestException as exc:
        return {"net_ok": False, "status": None, "code": None,
                "msg": "网络请求失败: %s" % exc, "data": None}
    if resp.status_code >= 500:
        return {"net_ok": False, "status": resp.status_code, "code": None,
                "msg": "服务端错误 HTTP %d" % resp.status_code, "data": None}
    try:
        payload = resp.json()
    except ValueError:
        return {"net_ok": False, "status": resp.status_code, "code": None,
                "msg": "响应不是 JSON（HTTP %d）" % resp.status_code, "data": None}
    if not isinstance(payload, dict):
        return {"net_ok": False, "status": resp.status_code, "code": None,
                "msg": "响应 JSON 结构异常: %r" % (payload,), "data": None}
    return {"net_ok": True, "status": resp.status_code,
            "code": payload.get("code"), "msg": payload.get("msg") or "",
            "data": payload.get("data")}


def describe_res(res):
    """把一次调用结果压缩成一行可读描述，用于打印。"""
    if not res["net_ok"]:
        return "%s（HTTP %s）" % (res["msg"], res["status"])
    return "code=%s, msg=%s" % (res["code"], res["msg"])


def probe_balance(session):
    """查余额：验证 Token 有效性与服务连通性（任何认证等级都可用）。"""
    return call_api(session, "POST", "/api/v1/dev/wallet/balance")


def probe_image_list(session):
    """查私有镜像列表：免企业认证的只读接口，用于交叉验证请求格式与服务状态。"""
    return call_api(session, "POST", "/api/v1/dev/image/private/list",
                    {"page_index": 1, "page_size": 1})


def probe_deployment_list(session):
    """核心权限探针：查部署列表（只读）。

    该接口与「创建部署」共享同一道企业认证门槛；门槛判断发生在参数校验
    之前，参数全对也拦。查列表成功即代表创建部署不会被资质门槛拦下。
    """
    return call_api(session, "POST", "/api/v1/dev/deployment/list",
                    {"page_index": 1, "page_size": 1})


def scan_gpu_stock(session):
    """逐地区查询 RTX 4090 库存（只读、免企业认证）。

    响应 data 是列表，每项形如 {"RTX 4090": {"idle_gpu_num": 215,
    "total_gpu_num": 2285, "chip_corp": "nvidia", ...}}。
    返回 (rows, error_count)。
    """
    rows = []
    errors = 0
    for region_sign, region_name in REGIONS:
        res = call_api(session, "POST", "/api/v1/dev/machine/region/gpu_stock",
                       {"region_sign": region_sign, "gpu_name_set": [TARGET_GPU]})
        row = {"sign": region_sign, "name": region_name,
               "idle": None, "total": None, "err": ""}
        if not res["net_ok"] or res["code"] != "Success":
            errors += 1
            row["err"] = describe_res(res)
        else:
            for item in res["data"] or []:
                if not isinstance(item, dict):
                    continue
                for gpu_name, stock in item.items():
                    if TARGET_GPU in str(gpu_name) and isinstance(stock, dict):
                        row["idle"] = stock.get("idle_gpu_num")
                        row["total"] = stock.get("total_gpu_num")
        rows.append(row)
    return rows, errors


def make_verdict(bal, img, dep):
    """根据探针结果给出（结论分类, 依据说明）。"""
    # ---- 前置：Token / 服务基线（查余额）----
    if not bal["net_ok"]:
        return CAT_SERVICE, "基线接口（查余额）网络层失败：%s" % bal["msg"]
    if bal["code"] != "Success":
        m = bal["msg"]
        if any(k in m for k in ("token", "Token", "鉴权", "登录", "认证",
                                "Unauthorized", "unauthorized")):
            return CAT_TOKEN, "查余额返回 %s / %s，Token 疑似无效或已过期" % (bal["code"], m)
        return CAT_UNKNOWN, "查余额返回业务错误：%s / %s" % (bal["code"], m)

    fmt_ok = bool(img and img["net_ok"] and img["code"] == "Success")
    cross = ""
    if fmt_ok:
        cross = "；交叉验证：免认证只读接口调用正常，可排除接口用法与服务问题"

    # ---- 核心探针：部署列表 ----
    if dep["net_ok"] and dep["code"] == "Success":
        return CAT_OK, "部署列表查询成功，账号已通过与「创建部署」相同的认证门槛"

    msg = dep["msg"]
    if dep["net_ok"] and dep["code"] != "Success" and ("权限" in msg or "认证" in msg):
        if "实名" in msg or dep["code"] == "TORealName":
            return CAT_ACCOUNT, "账号未完成实名认证：%s / %s%s" % (dep["code"], msg, cross)
        return CAT_ACCOUNT, ("部署资源类接口被鉴权拦截：%s / %s（未完成企业认证的典型返回）%s"
                             % (dep["code"], msg, cross))
    if dep["net_ok"] and dep["code"] == "RequestParameterIsWrong":
        return CAT_USAGE, "部署列表接口报请求参数错误：%s / %s" % (dep["code"], msg)
    if not dep["net_ok"]:
        if fmt_ok:
            return CAT_SERVICE, ("查余额/镜像列表均正常，唯独部署列表接口失败：%s"
                                 % dep["msg"])
        return CAT_SERVICE, "多个接口网络层失败，服务疑似异常：%s" % dep["msg"]
    return CAT_UNKNOWN, "部署列表返回未预期的错误：%s / %s（请把原始返回发给人工核对）" % (dep["code"], msg)


def print_verdict(cat, detail):
    print("\n" + "=" * 62)
    print("结论")
    print("=" * 62)
    if cat == CAT_OK:
        print("[OK] 账号【可以】创建弹性部署")
        print("  依据：%s" % detail)
        print("  提醒：这只是资质探路，本脚本未创建任何资源。后续真正创建部署时，")
        print("        若返回「当前算力规格暂无库存」属库存问题（换规格/稍后重试），")
        print("        不是权限问题，别和资质错误混淆。")
    elif cat == CAT_ACCOUNT:
        print("[BLOCKED] 账号【不能】创建弹性部署，原因归类：A. 账号资质问题")
        print("  依据：%s" % detail)
        print("  应对：到 AutoDL 控制台完成相应认证——弹性部署要求企业认证，")
        print("        仅个人实名不够；认证完成后重跑本脚本复验。")
    elif cat == CAT_USAGE:
        print("[ERROR] 探测受阻，原因归类：B. 接口用法问题（代码/传参，不是账号问题）")
        print("  依据：%s" % detail)
        print("  应对：检查调用方式——POST 接口参数放 JSON body、鉴权头无 Bearer 前缀、")
        print("        部署列表的 page_index/page_size 必填；对照官方文档修正后重跑。")
    elif cat == CAT_SERVICE:
        print("[ERROR] 探测受阻，原因归类：C. 服务端问题（不是账号问题）")
        print("  依据：%s" % detail)
        print("  应对：稍等后重试；若持续失败，查看 AutoDL 服务状态或联系客服。")
    elif cat == CAT_TOKEN:
        print("[ERROR] 探测受阻：Token 无效（先于三类原因的前置问题）")
        print("  依据：%s" % detail)
        print("  应对：控制台 -> 账号 -> 设置 -> 开发者Token 重新获取，")
        print("        export AUTODL_TOKEN=新Token 后重跑本脚本。")
    else:
        print("[UNKNOWN] 无法自动归类，需人工判断")
        print("  依据：%s" % detail)


def exit_code(cat):
    return {CAT_OK: 0, CAT_ACCOUNT: 1}.get(cat, 2)


def main():
    print("=" * 62)
    print("AutoDL 弹性部署探路（只读探测，不会创建任何部署/实例）")
    print("=" * 62)

    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print("未检测到环境变量 AUTODL_TOKEN，无法探测。")
        print("请先执行: export AUTODL_TOKEN=你的开发者Token")
        print("（获取位置：AutoDL 控制台 -> 账号 -> 设置 -> 开发者Token）")
        return 2

    session = requests.Session()
    # AutoDL 鉴权头没有 Bearer 前缀（与多数平台不同），直接放 token
    session.headers.update({"Authorization": token})

    # ---- 1/4 Token 与服务连通性 ----
    print("\n[1/4] 验证 Token 与服务连通性（POST /api/v1/dev/wallet/balance）")
    bal = probe_balance(session)
    if bal["net_ok"] and bal["code"] == "Success":
        data = bal["data"] if isinstance(bal["data"], dict) else {}
        assets, blocked = data.get("assets"), data.get("blocked_asset") or 0
        if isinstance(assets, (int, float)):
            # 金额单位是「元 x 1000」的整数，可用余额要扣掉冻结部分
            print("  [ok] Token 有效、服务可达；可用余额约 %.2f 元"
                  % ((assets - blocked) / 1000.0))
        else:
            print("  [ok] Token 有效、服务可达")
    else:
        print("  [fail] %s" % describe_res(bal))
        cat, detail = make_verdict(bal, None, None)
        print_verdict(cat, detail)
        return exit_code(cat)

    # ---- 2/4 交叉验证：免企业认证的只读接口 ----
    print("\n[2/4] 交叉验证（POST /api/v1/dev/image/private/list，免企业认证的只读接口）")
    img = probe_image_list(session)
    if img["net_ok"] and img["code"] == "Success":
        print("  [ok] 调用成功——请求格式正确、服务正常（该接口不需要企业认证）")
    else:
        print("  [fail] %s（若为参数错误，说明我们的调用方式有问题）" % describe_res(img))

    # ---- 3/4 核心权限探针 ----
    print("\n[3/4] 权限探针（POST /api/v1/dev/deployment/list，与创建部署同门槛，只读）")
    dep = probe_deployment_list(session)
    if dep["net_ok"] and dep["code"] == "Success":
        print("  [ok] 调用成功——账号已通过部署资源类接口的鉴权门槛")
    else:
        print("  [fail] %s" % describe_res(dep))

    # ---- 4/4 RTX 4090 库存 ----
    print("\n[4/4] 查询 %s 库存（POST /api/v1/dev/machine/region/gpu_stock）" % TARGET_GPU)
    rows, errors = scan_gpu_stock(session)
    total_idle, regions_in_stock = 0, 0
    for r in rows:
        if r["err"]:
            print("  [x] %s [%s]: 查询失败 %s" % (r["name"], r["sign"], r["err"]))
            continue
        if r["idle"] is None and r["total"] is None:
            print("  [-] %s [%s]: 无该型号" % (r["name"], r["sign"]))
            continue
        idle = r["idle"] or 0
        mark = "  <-- 有货" if idle > 0 else "（无空闲）"
        print("  [*] %s [%s]: 空闲 %s / 总量 %s%s" % (r["name"], r["sign"], idle,
                                                      r["total"], mark))
        total_idle += idle
        if idle > 0:
            regions_in_stock += 1
    print("  ----")
    if errors == len(REGIONS):
        print("  所有地区查询均失败——若上面第 1/2 步正常，多为接口用法问题；否则疑似服务问题")
    else:
        print("  汇总：%s 总空闲 %d 张，分布在 %d 个地区"
              % (TARGET_GPU, total_idle, regions_in_stock))
        print("  注意：库存按「单容器 1 张卡」口径统计，多卡容器的调度不以保证；")
        print("        库存随时变化，创建前建议再查一次。")

    # ---- 结论 ----
    cat, detail = make_verdict(bal, img, dep)
    print_verdict(cat, detail)
    return exit_code(cat)


if __name__ == "__main__":
    sys.exit(main())
