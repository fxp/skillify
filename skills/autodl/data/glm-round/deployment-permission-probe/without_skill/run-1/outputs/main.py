#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoDL 弹性部署探路脚本（只读探测，绝不创建任何部署/实例/容器）

目的：
  1. 确认当前账号能否使用「弹性部署」API（官方文档明确：使用弹性部署 API 需先完成企业认证）；
  2. 查询各区 RTX 4090 GPU 库存；
  3. 若不可用，把失败原因归类为：凭证(Token)问题 / 账号资质问题 / 接口用法问题 /
     服务端问题 / 本地网络问题，并给出对应的应对建议。

只读保证（本脚本仅调用以下查询类接口，不涉及任何创建/停止/删除动作）：
  - POST /api/v1/dev/wallet/balance            查询账户余额（用于验证 Token 是否有效，
                                                与企业认证无关，可作交叉对照）
  - POST /api/v1/dev/deployment/list           查询部署列表（弹性部署 API 的权限探针）
  - POST /api/v1/dev/machine/region/gpu_stock  查询 GPU 库存
  注意：这三个接口虽为 POST，语义均为「查询」，不会产生任何资源变更。

接口依据（2026-09 抓取官方文档）：
  - 弹性部署 API: https://www.autodl.com/docs/esd_api_doc/
  - API 总入口:   https://www.autodl.com/docs/common_api/
  鉴权方式：请求头 "Authorization": "<开发者Token>"（裸 token，无 Bearer 前缀）
  响应格式：{"code": "Success", "msg": "", "data": ...}；失败时 code != "Success"、msg 含原因。
  官方文档未列出失败错误码枚举，因此本脚本结合 HTTP 状态码、msg 关键词、
  以及「余额接口 vs 部署接口」的交叉对照来归类，并始终打印原始证据供人工复核。

用法：
  export AUTODL_TOKEN="你的开发者Token"    # 获取位置：AutoDL 控制台 -> 设置 -> 开发者Token
  python3 main.py

退出码：0 = 可以创建（读探针通过）；1 = 不可以（原因已分类）；2 = 无法判定。
"""

import os
import sys
import time

import requests

BASE_URL = "https://api.autodl.com"
TIMEOUT_SEC = 20
REQUEST_GAP_SEC = 0.2  # 各区库存查询之间的间隔，避免请求过快

# ---- 只读探针接口 ----
PATH_WALLET_BALANCE = "/api/v1/dev/wallet/balance"
PATH_DEPLOYMENT_LIST = "/api/v1/dev/deployment/list"
PATH_GPU_STOCK = "/api/v1/dev/machine/region/gpu_stock"

TARGET_GPU = "RTX 4090"
TARGET_GPU_KEY = "4090"  # 本地匹配含 "4090" 的型号（覆盖 RTX 4090 / RTX 4090D 等）

# 官方文档附录中的全部地区代码（region_sign）
REGION_SIGNS = [
    ("westDC2", "西北企业区(文档标注推荐)"),
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

# ---- 失败原因分类 ----
CAT_TOKEN = "凭证(Token)问题"
CAT_QUALIFICATION = "账号资质问题"
CAT_API_USAGE = "接口用法问题"
CAT_SERVICE = "服务端问题"
CAT_NETWORK = "本地网络问题"
CAT_UNKNOWN = "无法归类(需人工看原始证据)"

ADVICE = {
    CAT_TOKEN: (
        "应对：到 AutoDL 控制台 -> 设置 -> 开发者Token 重新生成/复制 Token，\n"
        "      确认环境变量 AUTODL_TOKEN 传入的值无多余空格/引号/换行后重跑。"
    ),
    CAT_QUALIFICATION: (
        "应对：官方文档要求『使用弹性部署API需先认证企业』。\n"
        "      到 AutoDL 控制台完成企业认证，或联系 AutoDL 客服/商务为账号开通弹性部署权限，\n"
        "      通过后再跑本脚本复核。"
    ),
    CAT_API_USAGE: (
        "应对：接口用法与线上不一致。核对官方文档 https://www.autodl.com/docs/esd_api_doc/\n"
        "      的路径/方法/参数（注意 API 版本可能更新），确认无新版本接口后调整脚本。"
    ),
    CAT_SERVICE: (
        "应对：服务端异常（5xx/网关错误），与账号无关。稍等后重跑；\n"
        "      若持续存在，查看 AutoDL 公告/状态页或联系客服。"
    ),
    CAT_NETWORK: (
        "应对：本机到 api.autodl.com 的网络不通或被代理/防火墙拦截，\n"
        "      检查代理设置、DNS 解析后重跑。"
    ),
    CAT_UNKNOWN: (
        "应对：响应形态未落入已知分类。请把上方「原始证据」区块的内容\n"
        "      对照官方文档或提交给 AutoDL 客服人工判断。"
    ),
}


def trim(text, limit=200):
    """截断长文本，便于单行打印原始证据。"""
    text = str(text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def call_api(session, path, payload=None):
    """
    调用 AutoDL OpenAPI。
    返回 (transport_ok, http_status, body, note)：
      transport_ok=True 表示拿到了 HTTP 响应（业务成败需再看 body["code"]）；
      transport_ok=False 表示网络层失败，note 含原因。
    """
    url = BASE_URL + path
    try:
        resp = session.post(url, json=payload if payload is not None else {}, timeout=TIMEOUT_SEC)
    except requests.exceptions.Timeout:
        return False, None, None, "请求超时(>%ds)" % TIMEOUT_SEC
    except requests.exceptions.ConnectionError as exc:
        return False, None, None, "连接失败: %s" % trim(exc, 160)
    except requests.exceptions.RequestException as exc:
        return False, None, None, "请求异常: %s" % trim(exc, 160)

    body = None
    try:
        body = resp.json()
    except ValueError:
        pass  # 网关可能返回 HTML 错误页，保留 body=None 并由调用方归类
    note = "" if body is not None else "响应非 JSON: %s" % trim(resp.text, 160)
    return True, resp.status_code, body, note


def classify_failure(http_status, body, note):
    """
    把一次失败归类。优先级：网络层 -> HTTP 状态码 -> 业务层 msg 关键词 -> 兜底 UNKNOWN。
    官方未公开错误码枚举，故为启发式分类，调用方应同时打印原始证据。
    """
    code = str(body.get("code", "")) if isinstance(body, dict) else ""
    msg = str(body.get("msg", "") or body.get("message", "") or "") if isinstance(body, dict) else ""
    low = (code + " " + msg).lower()

    # 1) 网络层失败
    if note:
        return CAT_NETWORK, note

    # 2) HTTP 状态码（语义明确，可信度最高）
    if http_status == 401:
        return CAT_TOKEN, "HTTP 401：Token 缺失或已失效"
    if http_status == 403:
        return CAT_QUALIFICATION, "HTTP 403：服务端拒绝授权（弹性部署要求企业认证，通常是账号未完成认证/未开通权限）"
    if http_status in (404, 405):
        return CAT_API_USAGE, "HTTP %d：接口路径或 HTTP 方法不匹配（也可能是该功能未对当前账号/环境开放，请结合 msg 判断）" % http_status
    if http_status is not None and 500 <= http_status < 600:
        return CAT_SERVICE, "HTTP %d：服务端错误" % http_status
    if http_status != 200:
        return CAT_UNKNOWN, "HTTP %d：非预期状态码" % http_status

    # 3) HTTP 200 但业务失败：按 code/msg 关键词归类
    if any(k in msg for k in ("企业", "实名", "资质", "审核", "开通", "未开放")) and "token" not in low:
        return CAT_QUALIFICATION, "业务层返回（疑似要求企业认证/开通）: %s" % trim(msg)
    if any(k in low for k in ("token", "鉴权", "登录", "unauthorized", "auth")):
        return CAT_TOKEN, "业务层返回（疑似凭证无效）: %s" % trim(msg)
    if any(k in low for k in ("参数", "param", "argument", "field", "invalid", "格式")):
        return CAT_API_USAGE, "业务层返回（疑似参数/格式不被接受）: %s" % trim(msg)
    if any(k in low for k in ("权限", "permission", "denied", "forbidden", "禁止")):
        return CAT_QUALIFICATION, "业务层返回（疑似权限不足）: %s" % trim(msg)
    if code and code != "Success":
        return CAT_UNKNOWN, "业务层失败 code=%s msg=%s（官方文档未列出该错误码，需人工判断）" % (code, trim(msg))
    return CAT_UNKNOWN, "响应形态未预期"


def probe_balance(session):
    """Step 1：查余额，验证 Token 本身是否有效（该接口与企业认证无关）。"""
    print("=" * 72)
    print("[Step 1] 验证 Token：POST %s （账户余额接口，与企业认证无关）" % PATH_WALLET_BALANCE)
    result = {"ok": False, "category": None, "reason": "", "evidence": "", "balance_yuan": None}
    transport_ok, status, body, note = call_api(session, PATH_WALLET_BALANCE, payload={})
    code = str(body.get("code", "")) if isinstance(body, dict) else ""
    msg = str(body.get("msg", "") or "") if isinstance(body, dict) else ""
    result["evidence"] = "HTTP %s, code=%s, msg=%s%s" % (
        status, code or "(非JSON)", trim(msg) or "(空)", ("；" + note) if note else "")
    print("  原始证据: %s" % result["evidence"])

    if transport_ok and status == 200 and code == "Success":
        data = body.get("data") or {}
        assets = data.get("assets")
        if isinstance(assets, (int, float)):
            result["balance_yuan"] = assets / 1000.0  # 文档：金额除以 1000 等于元
        result["ok"] = True
        print("  -> Token 有效 ✓")
        if result["balance_yuan"] is not None:
            print("  -> 账户余额: %.2f 元（代金券余额 %.2f 元）" % (
                result["balance_yuan"],
                (data.get("voucher_balance") or 0) / 1000.0 if isinstance(data.get("voucher_balance"), (int, float)) else 0.0))
    else:
        category, reason = classify_failure(status if transport_ok else None, body, note)
        result["category"], result["reason"] = category, reason
        print("  -> Token 验证失败：%s（%s）" % (category, reason))
    return result


def probe_deployment_list(session, token_ok):
    """Step 2：查部署列表（只读）。官方文档：弹性部署 API 需先完成企业认证，
    因此本接口可读即代表资质门槛已通过；被拒则按证据归类原因。"""
    print("=" * 72)
    print("[Step 2] 部署权限探针：POST %s （body: page_index=1, page_size=10；只读）" % PATH_DEPLOYMENT_LIST)
    result = {"ok": False, "category": None, "reason": "", "evidence": "", "deployment_total": None}
    transport_ok, status, body, note = call_api(
        session, PATH_DEPLOYMENT_LIST, payload={"page_index": 1, "page_size": 10})
    code = str(body.get("code", "")) if isinstance(body, dict) else ""
    msg = str(body.get("msg", "") or "") if isinstance(body, dict) else ""
    result["evidence"] = "HTTP %s, code=%s, msg=%s%s" % (
        status, code or "(非JSON)", trim(msg) or "(空)", ("；" + note) if note else "")
    print("  原始证据: %s" % result["evidence"])

    if transport_ok and status == 200 and code == "Success":
        data = body.get("data") or {}
        if isinstance(data, dict) and isinstance(data.get("result_total"), int):
            result["deployment_total"] = data["result_total"]
        result["ok"] = True
        total = result["deployment_total"]
        print("  -> 弹性部署 API 可访问 ✓（当前已有部署数: %s）" % (total if total is not None else "未知"))
    else:
        category, reason = classify_failure(status if transport_ok else None, body, note)
        # 交叉对照：余额接口成功而部署接口失败 => 排除 Token 问题
        if token_ok and category == CAT_TOKEN:
            category, reason = CAT_QUALIFICATION, (
                reason + "；注意：余额接口已成功，Token 本身有效，此处被拒更像是部署功能对账号未开放")
        result["category"], result["reason"] = category, reason
        print("  -> 部署 API 不可用：%s（%s）" % (category, reason))
    return result


def parse_gpu_stock(data):
    """
    解析 gpu_stock 的 data 字段。文档示例为列表，元素是以型号名为 key 的对象：
      [{"RTX 4090": {"idle_gpu_num": 215, "total_gpu_num": 2285}}, ...]
    兼容平铺形态 {"gpu_name": ..., "idle_gpu_num": ...} 与 dict 形态。
    返回 {型号: (idle, total)} 中型号含 TARGET_GPU_KEY 的条目。
    """
    found = {}
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]

    for item in items:
        if not isinstance(item, dict):
            continue
        idle = item.get("idle_gpu_num")
        total = item.get("total_gpu_num")
        if isinstance(idle, int) and isinstance(total, int) and (
                "gpu_name" in item or "name" in item):
            name = str(item.get("gpu_name") or item.get("name"))
            if TARGET_GPU_KEY in name:
                found[name] = (idle, total)
            continue
        for name, stats in item.items():
            if not isinstance(stats, dict):
                continue
            if TARGET_GPU_KEY in str(name):
                idle = stats.get("idle_gpu_num")
                total = stats.get("total_gpu_num")
                if isinstance(idle, int) and isinstance(total, int):
                    found[str(name)] = (idle, total)
    return found


def probe_gpu_stock(session):
    """Step 3：逐区查询 RTX 4090 库存（只读；region_sign 为文档附录全部地区）。"""
    print("=" * 72)
    print("[Step 3] %s 库存查询：POST %s （body: region_sign + gpu_name_set=['%s']；只读）"
          % (TARGET_GPU, PATH_GPU_STOCK, TARGET_GPU))
    stock_rows = []   # (region, label, {型号: (idle, total)})
    error_rows = []   # (region, label, 分类, 原因)
    for region, label in REGION_SIGNS:
        payload = {"region_sign": region, "gpu_name_set": [TARGET_GPU]}
        transport_ok, status, body, note = call_api(session, PATH_GPU_STOCK, payload=payload)
        code = str(body.get("code", "")) if isinstance(body, dict) else ""
        msg = str(body.get("msg", "") or "") if isinstance(body, dict) else ""
        if transport_ok and status == 200 and code == "Success":
            found = parse_gpu_stock(body.get("data"))
            if found:
                for name, (idle, total) in sorted(found.items()):
                    print("  %-12s %-24s %s: 空闲 %d / 总量 %d" % (region, "(%s)" % label, name, idle, total))
                stock_rows.append((region, label, found))
            else:
                print("  %-12s %-24s 无 %s 库存记录" % (region, "(%s)" % label, TARGET_GPU))
        else:
            category, reason = classify_failure(status if transport_ok else None, body, note)
            print("  %-12s %-24s 查询失败：%s（%s）" % (region, "(%s)" % label, category, reason))
            error_rows.append((region, label, category, reason))
        time.sleep(REQUEST_GAP_SEC)
    return stock_rows, error_rows


def conclude(token_r, deploy_r, stock_rows, error_rows):
    """汇总三类探针结果，给出最终结论与退出码。"""
    stock_regions = {region for region, _, _ in stock_rows}
    total_idle = sum(idle for _, _, found in stock_rows for _, (idle, _) in found.items())

    print("=" * 72)
    print("                          探 测 结 论")
    print("=" * 72)

    if token_r["ok"] and deploy_r["ok"]:
        print("能否创建弹性部署: 可以（本次验证范围内）")
        print("  判定链: Token 有效（余额接口 200/Success）")
        print("          -> 部署列表可读（deployment/list 200/Success）")
        print("          -> 官方『弹性部署 API 需企业认证』的资质门槛已通过，")
        print("             创建接口在参数正确的前提下应当可用。")
        print("  注意:   本脚本未实际创建资源；实际创建还受余额、库存、镜像/参数")
        print("           等运行时因素影响，这些只有真正创建时才能验证。")
    elif not token_r["ok"]:
        category = token_r["category"] or CAT_UNKNOWN
        can_decide = category in (CAT_TOKEN,)
        print("能否创建弹性部署: %s" % ("不可以（凭证层面即被拦下）" if can_decide else "无法判定"))
        print("原因分类: %s" % category)
        print("判定依据: 余额接口 %s" % token_r["evidence"])
        print("          （连与资质无关的账户接口都失败，尚未探测到部署资质层面）")
        print(ADVICE.get(category, ADVICE[CAT_UNKNOWN]))
        if not can_decide:
            return 2
        return 1
    else:
        category = deploy_r["category"] or CAT_UNKNOWN
        decisive = category in (CAT_QUALIFICATION, CAT_API_USAGE, CAT_TOKEN)
        print("能否创建弹性部署: %s" % ("不可以" if decisive else "无法判定（本次探测被服务端/网络异常阻断）"))
        print("原因分类: %s" % category)
        print("判定依据: Token 有效（余额接口成功）—— 排除凭证问题；")
        print("          部署列表接口 %s" % deploy_r["evidence"])
        if category == CAT_SERVICE:
            print("          （账户接口正常而部署接口 5xx，倾向服务端局部异常，不代表账号不行）")
        print(ADVICE.get(category, ADVICE[CAT_UNKNOWN]))
        if decisive:
            return 1
        return 2

    print("-" * 72)
    if token_r["balance_yuan"] is not None:
        print("账户余额: %.2f 元（余额过低会影响实际创建/运行，请自行确认）" % token_r["balance_yuan"])
    if stock_regions:
        print("%s 库存: %d 个区有货，空闲合计 %d 张（明细见 Step 3）"
              % (TARGET_GPU, len(stock_regions), total_idle))
    elif error_rows:
        cats = sorted({cat for _, _, cat, _ in error_rows})
        print("%s 库存: 未能获取（库存接口在全部 %d 个区均失败，失败分类: %s）"
              % (TARGET_GPU, len(REGION_SIGNS), "、".join(cats)))
        print("          若失败分类与 Step 2 一致（如均要求企业认证），则与部署结论互相印证。")
    else:
        print("%s 库存: 所有区均查询成功但无库存记录（当前无货或未上架）" % TARGET_GPU)
    print("=" * 72)
    return 0


def main():
    print("AutoDL 弹性部署探路脚本（只读，不创建任何资源）")
    print("API Host: %s | 鉴权: Authorization 头（裸 Token，来自环境变量 AUTODL_TOKEN）" % BASE_URL)
    print()

    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print("错误: 未设置环境变量 AUTODL_TOKEN")
        print("获取位置: AutoDL 控制台 -> 设置 -> 开发者Token")
        print("设置方式: export AUTODL_TOKEN=\"你的Token\" 后重新运行 python3 main.py")
        return 2

    session = requests.Session()
    session.headers.update({
        "Authorization": token,  # 官方文档：headers = {"Authorization": "token"}，无 Bearer 前缀
        "User-Agent": "autodl-deploy-probe/1.0",
    })

    token_r = probe_balance(session)
    print()
    deploy_r = probe_deployment_list(session, token_ok=token_r["ok"])
    print()
    stock_rows, error_rows = probe_gpu_stock(session)
    print()

    return conclude(token_r, deploy_r, stock_rows, error_rows)


if __name__ == "__main__":
    sys.exit(main())
