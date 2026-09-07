#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoDL 弹性部署「探路」脚本(只读探测,不会创建任何部署/实例)

目的:
  1. 确认当前账号(Token)能不能使用弹性部署 API(即能不能创建部署);
  2. 查询各地区 RTX 4090 库存(空闲/总数);
  3. 如果不能创建,给出原因分类,三种情况的应对完全不同:
       - 账号资质问题(Token 无效 / 未完成企业认证)  -> 去控制台处理认证;
       - 接口用法问题(路径/方法/参数不对)           -> 改脚本;
       - 服务端问题(5xx / 超时)                     -> 等服务恢复或提工单。

判定依据(官方文档 https://www.autodl.com/docs/esd_api_doc/ 与 /docs/common_api/):
  - API 服务地址: https://api.autodl.com
  - 鉴权: 请求头 Authorization 直接放 Token 本体,无 "Bearer " 前缀;
  - 官方文档明确"使用弹性部署API需先认证企业",且没有独立的权限查询接口,
    因此用【只读】的部署列表接口做权限探测:能查到列表 => 账号已具备弹性部署
    API 使用资格(可以创建部署);被拦则进一步区分资质/用法/服务问题;
  - Token 本身是否有效,用【只读】的通用接口查余额验证,以便把
    "Token 失效"与"未企业认证"区分开。

本脚本只调用以下三个只读查询接口,绝不调用创建接口:
  POST /api/v1/dev/wallet/balance             查余额(验证 Token)
  POST /api/v1/dev/deployment/list            查部署列表(验证弹性部署权限)
  POST /api/v1/dev/machine/region/gpu_stock   查 GPU 库存
(创建部署的接口是 POST /api/v1/dev/deployment,本脚本不会请求它。)

用法:
  export AUTODL_TOKEN="你的开发者Token"    # 控制台 -> 设置 -> 开发者Token
  python3 main.py

退出码: 0=可以创建部署; 1=环境问题(如缺Token); 2=不能创建部署(原因见输出); 3=无法归类
"""

import json
import os
import sys

try:
    import requests
except ImportError:
    print("[错误] 缺少 requests 库,请先执行: pip3 install requests")
    sys.exit(1)

API_HOST = "https://api.autodl.com"
TIMEOUT = 15  # 单次请求超时(秒)
RETRIES = 1   # 超时/连接失败时的重试次数,避免把偶发网络抖动误判为服务故障

# 文档附录给出的弹性部署地区标识(region_sign),共 11 个
REGIONS = [
    ("westDC2", "西北企业区(推荐)"),
    ("westDC3", "西北B区"),
    ("beijingDC1", "北京A区"),
    ("beijingDC2", "北京B区"),
    ("beijingDC4", "L20专区(原北京C区)"),
    ("beijingDC3", "V100专区(原华南A区)"),
    ("neimengDC1", "内蒙A区"),
    ("foshanDC1", "佛山区"),
    ("chongqingDC1", "重庆A区"),
    ("yangzhouDC1", "3090专区"),
    ("neimengDC3", "内蒙B区"),
]

GPU_KEYWORD = "4090"  # 客户端再匹配一次,可覆盖 RTX 4090 / RTX 4090D 等型号

# ---- 结论分类 ----
OK = "OK"                # 正常
ACCOUNT = "ACCOUNT"      # 账号资质/凭据问题
API_USAGE = "API_USAGE"  # 接口用法问题
SERVICE = "SERVICE"      # 服务端问题
UNKNOWN = "UNKNOWN"      # 无法归类(原样展示返回,人工判断)

CATEGORY_CN = {
    OK: "正常",
    ACCOUNT: "账号资质/凭据问题",
    API_USAGE: "接口用法问题",
    SERVICE: "服务端问题",
    UNKNOWN: "无法归类",
}

# 官方文档没有公布错误码枚举,这里对 code/msg 做保守的关键词归类,
# 归类不了会按 UNKNOWN 原样打印原始返回,不会瞎猜。
AUTH_KEYWORDS = ("认证", "企业", "资质", "权限", "实名", "禁止",
                 "unauthorized", "forbidden", "enterprise", "authentication", "token")
PARAM_KEYWORDS = ("参数", "param", "invalid", "not found", "notfound",
                  "路径", "方法", "method", "必填", "missing")


def api_post(path, token, payload=None):
    """POST 一个 JSON 请求,返回 (http_status, 解析后的JSON(dict)或None, 错误说明或None)。

    AutoDL 的查询类接口也都是 POST;鉴权头为 Authorization: <Token>(无 Bearer)。
    对超时/连接失败重试 RETRIES 次,仍失败则视为网络/服务不可达。
    """
    headers = {"Authorization": token}
    url = API_HOST + path
    body = payload if payload is not None else {}
    last_err = None
    for _ in range(RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            continue
        try:
            parsed = resp.json()
        except ValueError:
            parsed = None
        if parsed is None:
            err = f"HTTP {resp.status_code},响应不是JSON: {resp.text[:200]!r}"
            return resp.status_code, None, err
        return resp.status_code, parsed, None
    return None, None, f"网络请求失败(已重试{RETRIES}次): {last_err}"


def classify(status, body, err):
    """把一次调用结果归入 OK/ACCOUNT/API_USAGE/SERVICE/UNKNOWN,返回 (分类, 说明)。"""
    if status is None:  # 请求根本没成功(超时/连不上)
        return SERVICE, f"连不上或请求超时:{err}(注意:也可能是本机网络问题)"
    if status == 200:
        if not isinstance(body, dict):
            return SERVICE, f"HTTP 200 但返回的不是JSON(疑似网关/服务异常):{err}"
        code = str(body.get("code", ""))
        msg = str(body.get("msg", ""))
        if code == "Success" and not msg:
            return OK, ""
        text = (code + " " + msg).lower()
        if any(k.lower() in text for k in AUTH_KEYWORDS):
            return ACCOUNT, f"业务错误,命中认证/资质关键词:code={code} msg={msg}"
        if any(k.lower() in text for k in PARAM_KEYWORDS):
            return API_USAGE, f"业务错误,命中参数/用法关键词:code={code} msg={msg}"
        return UNKNOWN, f"业务错误,未能自动归类:code={code} msg={msg}"
    if status == 401:
        return ACCOUNT, "HTTP 401:Token 无效或过期(凭据问题,不是资质问题)"
    if status == 403:
        return ACCOUNT, "HTTP 403:无权限,大概率是未完成企业认证(账号资质问题)"
    if status in (400, 404, 405, 415):
        return API_USAGE, f"HTTP {status}:接口用法问题(路径/方法/参数/请求头不对)"
    if status >= 500:
        return SERVICE, f"HTTP {status}:服务端错误"
    return UNKNOWN, f"HTTP {status}:未预期的状态码,原始返回:{err or body}"


def fmt_yuan(amount):
    """AutoDL 金额字段单位是 元*1000(如 0.1 元存 100)。"""
    try:
        return f"{int(amount) / 1000.0:.2f} 元"
    except (TypeError, ValueError):
        return str(amount)


def describe_deploy_data(data):
    """部署列表接口的返回结构文档未给示例,这里做防御式提取,拿不准就原样展示。"""
    if isinstance(data, dict):
        for key in ("list", "items", "deployments", "records"):
            val = data.get(key)
            if isinstance(val, list):
                return f"现有部署 {len(val)} 条(列表字段名为'{key}')"
        return "返回data字段: " + json.dumps(data, ensure_ascii=False)[:300]
    if isinstance(data, list):
        return f"现有部署 {len(data)} 条"
    return f"返回data: {str(data)[:300]}"


def main():
    print("=" * 64)
    print("AutoDL 弹性部署探路(只读,不会创建任何部署或实例)")
    print("=" * 64)

    token = (os.environ.get("AUTODL_TOKEN") or "").strip()
    if not token:
        print()
        print("[错误] 环境变量 AUTODL_TOKEN 未设置。")
        print("       Token 获取: AutoDL 控制台 -> 设置 -> 开发者Token")
        print("       然后执行:   export AUTODL_TOKEN='你的Token'  再运行 python3 main.py")
        return 1

    # ---------- 第 1 步:验证 Token(通用接口,只读) ----------
    print("\n[1/3] 验证 Token(POST /api/v1/dev/wallet/balance,只读)...")
    st, body, err = api_post("/api/v1/dev/wallet/balance", token)
    cat, why = classify(st, body, err)
    token_ok = cat == OK
    balance_raw = None
    if token_ok:
        data = (body or {}).get("data") or {}
        balance_raw = data.get("assets")
        print(f"  [OK] Token 有效;余额: {fmt_yuan(balance_raw)}"
              f"(累计消费: {fmt_yuan(data.get('accumulate'))})")
    else:
        print(f"  [失败] Token 验证未通过 -> {CATEGORY_CN[cat]}:{why}")
        print("        这一步过不去,先解决 Token 本身(抄错/过期),再谈部署权限。")

    # ---------- 第 2 步:弹性部署权限(核心问题,只读) ----------
    print("\n[2/3] 探测弹性部署 API 权限(POST /api/v1/dev/deployment/list,只读)...")
    print("      官方要求: 使用弹性部署API需先完成企业认证,且无独立权限查询接口,")
    print("      故用只读的部署列表接口代替探测;创建接口 /api/v1/dev/deployment 不会被调用。")
    st2, body2, err2 = api_post("/api/v1/dev/deployment/list", token,
                                {"page_index": 1, "page_size": 10})
    cat2, why2 = classify(st2, body2, err2)
    if cat2 == OK:
        print("  [OK] 部署列表查询成功 => 账号已具备弹性部署 API 权限(可以创建部署)")
        print("        " + describe_deploy_data((body2 or {}).get("data")))
    else:
        print(f"  [失败] 部署列表查询未通过 -> {CATEGORY_CN[cat2]}:{why2}")

    # ---------- 第 3 步:RTX 4090 库存(逐地区,只读) ----------
    stock_rows = []  # (地区中文名, region_sign, gpu_name, idle, total)
    print("\n[3/3] 查询各地区 RTX 4090 库存(POST /api/v1/dev/machine/region/gpu_stock,只读)...")
    if cat2 in (ACCOUNT, SERVICE):
        print(f"  [跳过] 第2步已判定为{CATEGORY_CN[cat2]},库存接口同属弹性部署API,")
        print("         大概率同样失败,先解决上面的问题再跑本脚本复查。")
    else:
        for sign, cn in REGIONS:
            st3, body3, err3 = api_post("/api/v1/dev/machine/region/gpu_stock", token,
                                        {"region_sign": sign})
            cat3, why3 = classify(st3, body3, err3)
            if cat3 != OK:
                print(f"  {cn:<16} {sign:<12} 查询失败: {why3}")
                continue
            found = []
            data3 = (body3 or {}).get("data")
            if isinstance(data3, list):
                # 返回结构: data -> list,每项形如 {"RTX 4090": {"idle_gpu_num": 215, "total_gpu_num": 2285}}
                for item in data3:
                    if not isinstance(item, dict):
                        continue
                    for gpu_name, nums in item.items():
                        if GPU_KEYWORD in str(gpu_name) and isinstance(nums, dict):
                            found.append((str(gpu_name),
                                          nums.get("idle_gpu_num"),
                                          nums.get("total_gpu_num")))
            if found:
                for gpu_name, idle, total in found:
                    stock_rows.append((cn, sign, gpu_name, idle, total))
                    print(f"  {cn:<16} {sign:<12} {gpu_name:<12} 空闲 {idle} / 总数 {total}")
            else:
                print(f"  {cn:<16} {sign:<12} 无 4090 系库存记录")

    # ---------- 汇总结论 ----------
    print("\n" + "=" * 64)
    print("结论")
    print("=" * 64)

    if cat2 == OK:
        print("* 能否创建部署: 可以。只读的部署列表接口(需企业认证)已能正常访问,")
        print("  权限层面没有阻碍(本次未实际创建,创建接口未被调用)。")
        if not token_ok:
            # 真实环境里 Token 无效时两个接口会一起失败;出现这种组合,
            # 更可能是余额接口路径有变,而部署接口的判定才是权威依据。
            print("  注意: 第1步余额接口失败、但第2步部署接口成功,以后者为准;")
            print("  余额接口可能路径有变,不影响\"能否创建部署\"的判定。")
        if isinstance(balance_raw, int) and balance_raw < 1000:  # 余额不足 1 元
            print(f"  注意: 当前余额仅 {fmt_yuan(balance_raw)},实际创建部署可能因余额不足")
            print("  被拒,那属于计费问题,不属于权限问题。")
        rc = 0
    else:
        print(f"* 能否创建部署: 不能(本次仅探测,未尝试创建)。原因分类: {CATEGORY_CN[cat2]}")
        if cat2 == ACCOUNT:
            print("  -> 应对: 账号侧问题,改脚本没用。")
            if not token_ok:
                print("     - Token 无效/过期: 去 控制台->设置->开发者Token 重新获取,")
                print("       重新 export AUTODL_TOKEN 后再跑本脚本。")
            else:
                print("     - Token 有效但被弹性部署接口拦下: 大概率是未完成【企业认证】")
                print("       (官方要求: 使用弹性部署API需先认证企业),去控制台完成企业")
                print("       认证后再跑本脚本复查。")
        elif cat2 == API_USAGE:
            print("  -> 应对: 接口用法问题。请求没按服务端预期发出(路径/方法/参数),")
            print("     对照官方文档 https://www.autodl.com/docs/esd_api_doc/ 核对,")
            print("     或等 AutoDL 更新接口后修订本脚本。")
        elif cat2 == SERVICE:
            print("  -> 应对: 服务端问题(5xx/超时,已重试过)。稍后重试本脚本,")
            print("     持续失败就向 AutoDL 提工单。")
        else:
            print("  -> 应对: 未能自动归类,请把上面的原始 code/msg 对照官方文档判断。")
        rc = 3 if cat2 == UNKNOWN else 2

    if stock_rows:
        summary = {}
        for _, _, gpu_name, idle, total in stock_rows:
            a, b = summary.get(gpu_name, (0, 0))
            summary[gpu_name] = (a + (idle or 0), b + (total or 0))
        print("* RTX 4090 库存汇总(全部地区):")
        for gpu_name, (idle, total) in summary.items():
            print(f"    {gpu_name}: 空闲合计 {idle} 张 / 总数合计 {total} 张"
                  + ("  <- 有货" if idle else "  <- 当前无空闲卡"))
    elif cat2 == OK:
        print("* RTX 4090 库存: 所有地区均无 4090 系记录(可能全部售罄/未上架,")
        print("  或型号名称有变化,可去掉 GPU_KEYWORD 过滤查看全量库存)。")

    print("\n* 本次探路只调用了只读查询接口(余额/部署列表/GPU库存),")
    print("  未创建任何部署或实例。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
