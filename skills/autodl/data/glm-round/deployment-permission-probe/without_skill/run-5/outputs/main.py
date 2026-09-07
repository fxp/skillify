#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoDL 弹性部署「能否创建」探针（只读探测，绝不创建/修改任何资源）。

背景
----
准备用 AutoDL 弹性部署跑推理服务，正式动手前先摸清楚两件事：
  1. 当前账号到底有没有创建弹性部署的权限；
  2. RTX 4090 现在有没有库存。

官方帮助文档（https://www.autodl.com/docs/esd_api_doc/ 等）明确：
  - 弹性部署 API 仅面向完成「企业认证」的账号；
  - 个人实名/企业认证的普通账号可以调用通用接口（钱包、容器实例 Pro 等）。

探测思路（对应三种失败原因的区分）
----------------------------------
第 0 步  检查 AUTODL_TOKEN 环境变量（缺 Token 属本地配置问题，先排除）；
第 1 步  用「任何有效 Token 都能调」的通用只读接口（钱包余额，必要时加
         容器实例列表）验证 Token 本身是否有效——401 说明是 Token 的问题，
         与账号资质/接口/服务无关；
第 2 步  调弹性部署自己的只读接口（部署列表、时长包概览）探测权限：
           200 + code=Success       -> 弹性部署 API 可用，具备创建权限；
           401                      -> Token 无效（配置问题）；
           403 / 提示企业认证、权限  -> 账号资质问题（未企业认证）；
           400/404/405、参数类报错  -> 接口用错（路径/方法/参数不匹配）；
           5xx、超时、连接失败      -> 服务端问题；
第 3 步  逐个数据中心查 RTX 4090 库存（只读）并汇总。

安全声明：本脚本只调用下列 5 个「查询类」接口，全部无副作用——
  POST /api/v1/dev/wallet/balance             查询钱包余额
  POST /api/v1/dev/instance/pro/list          查询容器实例列表
  POST /api/v1/dev/deployment/list            查询弹性部署列表
  GET  /api/v1/dev/deployment/ddp/overview    查询已购时长包
  POST /api/v1/dev/machine/region/gpu_stock   查询 GPU 库存
创建部署（POST /api/v1/dev/deployment）、停止/删除/改副本数等一切写接口
在本脚本中一律不出现、不调用。

用法：AUTODL_TOKEN=你的开发者Token python3 main.py
退出码：0 = 具备创建权限（库存见输出）；1 = 不能创建（原因见输出）；
        2 = 本地配置问题（缺少 AUTODL_TOKEN 或 requests）。
"""

import os
import sys

try:
    import requests
except ImportError:
    print("[错误] 缺少 requests 库，请先安装：pip3 install requests")
    sys.exit(2)

API_HOST = "https://api.autodl.com"
TARGET_GPU = "RTX 4090"
TIMEOUT = (10, 20)  # (连接超时, 读取超时) 秒

# 只读接口（method, path, 用途）——写接口刻意不在此出现
EP_WALLET = ("POST", "/api/v1/dev/wallet/balance", "查询钱包余额（通用接口，验 Token 用）")
EP_INST_LIST = ("POST", "/api/v1/dev/instance/pro/list", "查询容器实例列表（通用接口）")
EP_DEPLOY_LIST = ("POST", "/api/v1/dev/deployment/list", "查询弹性部署列表（弹性部署接口）")
EP_DDP = ("GET", "/api/v1/dev/deployment/ddp/overview", "查询已购时长包（弹性部署接口）")
EP_GPU_STOCK = ("POST", "/api/v1/dev/machine/region/gpu_stock", "查询 GPU 库存（弹性部署接口）")

# 弹性部署数据中心代码（官方文档 附录1）
DATA_CENTERS = [
    ("westDC2", "西北企业区(推荐)"),
    ("westDC3", "西北B区"),
    ("beijingDC1", "北京A区"),
    ("beijingDC2", "北京B区"),
    ("beijingDC3", "V100专区(原华南A区)"),
    ("beijingDC4", "L20专区(原北京C区)"),
    ("neimengDC1", "内蒙A区"),
    ("neimengDC3", "内蒙B区"),
    ("foshanDC1", "佛山区"),
    ("chongqingDC1", "重庆A区"),
    ("yangzhouDC1", "3090专区"),
]

# 结果归类
CAT_OK = "OK"                    # 调用成功
CAT_TOKEN = "TOKEN"              # Token 无效/过期（本地配置问题）
CAT_QUAL = "QUALIFICATION"       # 账号资质问题（未企业认证/无权限）
CAT_MISUSE = "API_MISUSE"        # 接口用错（路径/方法/参数不匹配）
CAT_SVC = "SERVICE"              # 服务端问题（5xx/超时/连不上）
CAT_UNKNOWN = "UNKNOWN"          # 无法归类（输出原始报错，人工判断）

CAT_DESC = {
    CAT_TOKEN: "Token 配置问题（不是账号资质、不是接口用错、也不是服务故障）",
    CAT_QUAL: "账号资质问题（弹性部署仅对企业认证账号开放）",
    CAT_MISUSE: "接口用错（路径/方法/参数与服务端不匹配）",
    CAT_SVC: "服务端问题（5xx / 超时 / 无法连接）",
    CAT_UNKNOWN: "无法自动归类，请根据原始报错人工判断",
}

CAT_ADVICE = {
    CAT_TOKEN: "到 控制台 -> 设置 -> 开发者Token 重新生成 Token，更新 AUTODL_TOKEN 后重跑本脚本。",
    CAT_QUAL: "到 控制台 -> 账号安全 -> 实名认证 完成「企业认证」后重试；"
              "代码和接口本身没问题，也无需等服务恢复。若已认证仍报错，请联系 AutoDL 客服核对开通状态。",
    CAT_MISUSE: "对照官方文档核对请求路径/方法/参数（文档更新可能导致接口变动）："
                "https://www.autodl.com/docs/esd_api_doc/ ，修正后再探测。",
    CAT_SVC: "本地代码与账号资质暂无异常证据，建议间隔几分钟后重跑本脚本；"
             "持续失败请查看 AutoDL 官方公告/状态或联系客服。",
    CAT_UNKNOWN: "请把上面的原始响应贴出来人工分析，或对照官方文档核对。",
}


def call_api(session, method, path, body=None):
    """发一次请求，统一解析成 {status, code, msg, data, network_error, bad_json, raw}。"""
    res = {"status": None, "code": None, "msg": "", "data": None,
           "network_error": False, "bad_json": False, "raw": ""}
    url = API_HOST + path
    try:
        if method == "GET":
            r = session.get(url, timeout=TIMEOUT)
        else:
            r = session.post(url, json=body if body is not None else {}, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        res["msg"] = "请求超时"
        res["network_error"] = True
        return res
    except requests.exceptions.ConnectionError:
        res["msg"] = "连接失败（网络不可达或服务端拒绝连接）"
        res["network_error"] = True
        return res
    except requests.exceptions.RequestException as e:
        res["msg"] = "请求异常: %r" % (e,)
        res["network_error"] = True
        return res

    res["status"] = r.status_code
    res["raw"] = r.text[:300]
    try:
        payload = r.json()
    except ValueError:
        res["bad_json"] = True
        res["msg"] = "响应不是 JSON（可能是网关/HTML 错误页）"
        return res
    if isinstance(payload, dict):
        res["code"] = payload.get("code")
        res["msg"] = payload.get("msg") or ""
        res["data"] = payload.get("data")
    else:
        res["bad_json"] = True
        res["msg"] = "响应 JSON 结构异常"
    return res


def classify(res):
    """把一次调用结果归入 CAT_*。归类依据 HTTP 状态码 + 业务码 + 报错关键词，
    原始报错始终会打印出来，便于人工复核。"""
    if res["network_error"] or res["bad_json"]:
        return CAT_SVC
    status = res["status"]
    msg = (res["msg"] or "").lower()

    if status == 200 and res["code"] == "Success":
        return CAT_OK
    if status == 401:
        return CAT_TOKEN
    # 企业认证/权限类关键词优先（弹性部署未认证的典型报错）
    if status == 403 or any(w in msg for w in
                            ("企业", "实名", "认证", "权限", "forbidden", "permission", "enterprise")):
        return CAT_QUAL
    # Token 类关键词
    if any(w in msg for w in ("token", "unauthorized", "登录", "鉴权", "过期")):
        return CAT_TOKEN
    # 参数/路径/方法类
    if status in (400, 404, 405) or any(w in msg for w in
                                        ("参数", "param", "not found", "不存在", "method")):
        return CAT_MISUSE
    if status is not None and status >= 500:
        return CAT_SVC
    return CAT_UNKNOWN


def fmt_res(res):
    """单行可读的结果摘要。"""
    if res["network_error"]:
        return "网络层失败: %s" % res["msg"]
    if res["bad_json"]:
        return "HTTP %s, 非 JSON 响应: %s" % (res["status"], res["raw"])
    return "HTTP %s, code=%s, msg=%s" % (res["status"], res["code"], res["msg"] or "<空>")


def run_probe(session, ep, body=None):
    """调用一个接口：打印一行探测日志，返回 (结果, 归类)。"""
    method, path, desc = ep
    tag = "%s %s（%s）" % (method, path, desc)
    res = call_api(session, method, path, body)
    cat = classify(res)
    mark = "OK " if cat == CAT_OK else "失败"
    print("      - %s\n          -> [%s] %s" % (tag, mark, fmt_res(res)))
    return res, cat


def probe_stock(session):
    """逐数据中心查询 RTX 4090 库存。返回 (行列表, 空闲总数, 跳过原因)。
    行元素: (region_sign, 区名, 归类, idle, total, 说明)"""
    rows = []
    idle_total = 0
    skip_reason = None
    for sign, cname in DATA_CENTERS:
        if skip_reason:
            rows.append((sign, cname, "SKIPPED", None, None, skip_reason))
            continue
        res, cat = run_probe(session, EP_GPU_STOCK,
                             {"region_sign": sign, "gpu_name_set": [TARGET_GPU]})
        if cat != CAT_OK:
            rows.append((sign, cname, cat, None, None, res["msg"] or ("HTTP %s" % res["status"])))
            if cat in (CAT_TOKEN, CAT_QUAL):
                skip_reason = "前面区域已报 %s 类错误，后续区域跳过" % (
                    "Token" if cat == CAT_TOKEN else "权限/资质")
            continue
        info = None
        data = res["data"]
        if isinstance(data, dict):
            info = data.get(TARGET_GPU)
            if info is None:  # 兜底：data 可能嵌套一层
                for v in data.values():
                    if isinstance(v, dict) and TARGET_GPU in v:
                        info = v[TARGET_GPU]
                        break
        if isinstance(info, dict):
            idle = info.get("idle_gpu_num")
            total = info.get("total_gpu_num")
            rows.append((sign, cname, CAT_OK, idle, total, ""))
            if isinstance(idle, int):
                idle_total += idle
        else:
            rows.append((sign, cname, CAT_OK, None, None, "返回成功但无 %s 数据（该区可能无此卡型）" % TARGET_GPU))
    return rows, idle_total, skip_reason


def main():
    print("=" * 68)
    print(" AutoDL 弹性部署权限探针（只读探测，不会创建/修改任何部署或实例）")
    print("=" * 68)

    # ---- 第 0 步：本地配置 ----
    print("\n[0/4] 检查环境变量 AUTODL_TOKEN")
    token = (os.environ.get("AUTODL_TOKEN") or "").strip()
    if not token:
        print("      - 缺少 AUTODL_TOKEN！请先执行: export AUTODL_TOKEN=你的开发者Token")
        print("      - Token 获取路径: 控制台 -> 设置 -> 开发者Token")
        print("\n结论: 尚未开始探测（本地配置问题，未发起任何网络请求）。")
        return 2
    print("      - OK（长度 %d）" % len(token))

    session = requests.Session()
    session.headers.update({"Authorization": token, "Content-Type": "application/json"})

    # ---- 第 1 步：Token 有效性（通用接口做基线）----
    print("\n[1/4] 验证 Token 有效性（通用只读接口基线）")
    wallet_res, wallet_cat = run_probe(session, EP_WALLET, {})
    balance_note = ""
    if wallet_cat == CAT_OK and isinstance(wallet_res.get("data"), dict):
        assets = wallet_res["data"].get("assets")
        if isinstance(assets, (int, float)):
            balance_note = "（账户余额约 %.2f 元）" % (assets / 1000.0)
            print("          %s" % balance_note.strip())
    token_valid = wallet_cat == CAT_OK
    inst_cat = None
    if not token_valid:
        inst_res, inst_cat = run_probe(session, EP_INST_LIST, {"page_index": 1, "page_size": 1})
        token_valid = inst_cat == CAT_OK

    # ---- 第 2 步：弹性部署接口权限探测 ----
    print("\n[2/4] 探测弹性部署 API 权限（只读接口，不创建任何资源）")
    deploy_res, deploy_cat = run_probe(session, EP_DEPLOY_LIST, {"page_index": 1, "page_size": 1})
    ddp_res, ddp_cat = run_probe(session, EP_DDP)
    # 任一弹性部署只读接口成功即证明该 API 可用
    esd_ok = deploy_cat == CAT_OK or ddp_cat == CAT_OK
    # 主判定取部署列表的结果；网络失败等场景退回时长包结果
    esd_cat = deploy_cat if deploy_cat != CAT_SVC else ddp_cat

    # ---- 第 3 步：RTX 4090 库存 ----
    print("\n[3/4] 查询 %s 库存（逐数据中心，只读）" % TARGET_GPU)
    stock_rows, idle_total, skip_reason = probe_stock(session)
    ok_rows = [r for r in stock_rows if r[2] == CAT_OK]
    has_stock_rows = [r for r in ok_rows if isinstance(r[3], int)]
    print("      ----------------------------------------------------------")
    for sign, cname, cat, idle, total, note in stock_rows:
        if cat == CAT_OK and isinstance(idle, int):
            line = "空闲 %s / 总 %s" % (idle, total)
        elif cat == CAT_OK:
            line = "无数据"
        elif cat == "SKIPPED":
            line = "跳过"
        else:
            line = "查询失败（%s）" % (note or cat)
        print("      - %-30s %-8s %s" % ("%s %s" % (sign, cname), cat if cat != CAT_OK else "OK", line))

    # ---- 第 4 步：汇总结论 ----
    print("\n[4/4] 汇总结论")
    print("=" * 68)

    # 判定优先级：Token 问题 -> 弹性部署权限归类
    if not token_valid and wallet_cat == CAT_TOKEN and (inst_cat in (None, CAT_TOKEN)) \
            and esd_cat in (CAT_TOKEN, CAT_SVC):
        verdict = CAT_TOKEN
    elif esd_ok:
        verdict = CAT_OK
    elif esd_cat == CAT_TOKEN and token_valid:
        # Token 对通用接口有效、但弹性部署接口 401：本质是账号未开通弹性部署权限
        verdict = CAT_QUAL
    else:
        verdict = esd_cat if esd_cat in (CAT_QUAL, CAT_MISUSE, CAT_SVC, CAT_TOKEN) else CAT_UNKNOWN

    if verdict == CAT_OK:
        print("① 能否创建弹性部署: 可以（权限层面）")
        print("   弹性部署只读接口调用成功，说明 Token 有效且账号具备弹性部署权限；")
        print("   实际创建能否成功还取决于库存、余额和创建参数。%s" % balance_note)
    else:
        print("① 能否创建弹性部署: 不能（或暂不可判断）")
        print("② 原因归类: %s" % CAT_DESC[verdict])
        evid = []
        if wallet_cat is not None:
            evid.append("通用接口(%s): %s" % (EP_WALLET[1].split("（")[0], fmt_res(wallet_res)))
        evid.append("弹性部署接口(%s): %s" % (EP_DEPLOY_LIST[1].split("（")[0], fmt_res(deploy_res)))
        print("   依据:")
        for e in evid:
            print("     - %s" % e)
        if verdict == CAT_QUAL and not token_valid:
            print("   注意: 通用接口也未成功，请先按下面的建议修复 Token，再重跑区分资质问题。")
    if verdict != CAT_OK:
        print("③ 建议下一步: %s" % CAT_ADVICE[verdict])

    # 库存小结
    print("%s RTX 4090 库存:" % ("④" if verdict == CAT_OK else "④"))
    if skip_reason:
        print("   无法查询库存: %s（库存接口属于弹性部署 API，权限被拒时同样查不了）" % skip_reason)
    elif has_stock_rows:
        best = max(has_stock_rows, key=lambda r: (r[3] if isinstance(r[3], int) else 0))
        print("   %d 个数据中心返回数据，合计空闲 %d 张；空闲最多: %s %s（空闲 %s / 总 %s）。" % (
            len(has_stock_rows), idle_total, best[0], best[1], best[3], best[4]))
        print("   （官方说明: 库存按单卡调度口径统计，多卡容器可能无法在单机调度）")
    else:
        print("   %d 个数据中心均无 %s 库存数据。" % (len(ok_rows), TARGET_GPU))
    print("=" * 68)

    exit_code = 0 if verdict == CAT_OK else 1
    print("退出码: %d（0=具备创建权限; 1=不能创建/需先处理上述问题）" % exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
