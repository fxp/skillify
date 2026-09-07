#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoDL 弹性部署「探路」脚本
==========================

目的
----
在真正创建弹性部署之前，只用只读接口回答三个问题：
  1. 我们账号现在能不能创建部署（权限/资质层面）？
  2. 如果不能，原因属于哪一类：账号资质 / 接口用错 / 服务端问题？
     （三类原因的应对完全不同：认证企业 vs 改代码 vs 等服务恢复）
  3. RTX 4090 目前在哪些区域有库存？

安全性承诺（重要）
------------------
本脚本 **绝不创建、修改或删除任何资源**，全程只调用以下 3 个只读查询接口：
  - POST /api/v1/dev/wallet/balance           查账户余额（验证 Token 有效 + 服务可用）
  - POST /api/v1/dev/deployment/list          查部署列表（探测弹性部署 API 权限）
  - POST /api/v1/dev/machine/region/gpu_stock 查各区域 GPU 库存
注意：AutoDL 官方的查询类接口本身就是 POST（文档如此），POST 不等于创建。
文档中真正创建部署的接口是 POST /api/v1/dev/deployment，本脚本不会调用它，
也不会调用任何 PUT / DELETE（停部署、删部署等）接口。

接口依据（官方文档，2026-09 查证）
------------------------------------
  - API 文档总览:  https://www.autodl.com/docs/common_api/
  - 弹性部署 API:  https://www.autodl.com/docs/esd_api_doc/
  - 容器实例 Pro:  https://www.autodl.com/docs/instance_pro_api/
要点：
  - 鉴权方式: 请求头 {"Authorization": "<token>"}，无 Bearer 前缀，
    Token 获取位置: 控制台 -> 设置 -> 开发者Token
  - 弹性部署 API 文档明确写了「使用弹性部署API需先认证企业」，
    即未完成企业认证是最常见的"账号资质"类失败原因。
  - 官方未公开错误码表，因此失败原因按 HTTP 状态码 + code/msg 关键词
    启发式归类；归类不出时会原样打印服务端返回，供人工核对。

用法
----
  export AUTODL_TOKEN="控制台->设置->开发者Token 里的值"
  python3 main.py

退出码
------
  0   探路成功：账号具备使用弹性部署 API 的权限（服务/接口均正常）
  10  不能创建：账号资质问题（最常见：未完成企业认证）
  20  不能创建：接口使用问题（路径/参数/鉴权头用法不对）
  30  不能创建：服务端问题（5xx / 超时 / 网络不可达）
  40  Token 无效（先修 Token，其余结论无从谈起）
  50  本地配置问题（缺少环境变量 AUTODL_TOKEN / 未安装 requests）
  60  失败原因无法自动归类（请把脚本输出交给人工对照官方文档判断）
"""

import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("[本地配置错误] 缺少 requests 库，请先执行: pip3 install requests")
    sys.exit(50)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
BASE_URL = "https://api.autodl.com"  # 官方文档给出的 API 域名
TIMEOUT = 15                         # 单次请求超时（秒）
REGION_QUERY_GAP = 0.2               # 逐区域查库存的请求间隔（秒），避免请求过快

# 官方文档《弹性部署API》附录：region_sign 与区域对照表
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

TARGET_GPU_KEYWORD = "4090"  # 匹配 RTX 4090 / 4090D 等 4090 系全部型号

# 退出码
EXIT_OK = 0         # 具备创建部署权限，服务与接口均正常
EXIT_ACCOUNT = 10   # 账号资质问题（典型：未完成企业认证）
EXIT_API = 20       # 接口使用问题（路径/参数/鉴权方式不对）
EXIT_SERVICE = 30   # 服务端问题（5xx/超时/不可达）
EXIT_TOKEN = 40     # Token 无效
EXIT_LOCAL = 50     # 本地配置问题（缺 AUTODL_TOKEN、缺 requests）
EXIT_UNKNOWN = 60   # 无法自动归类

CATEGORY_EXIT = {
    "account": EXIT_ACCOUNT,
    "api": EXIT_API,
    "service": EXIT_SERVICE,
    "token": EXIT_TOKEN,
    "unknown": EXIT_UNKNOWN,
}

CATEGORY_DESC = {
    "account": "账号资质问题（服务端判定该账号无权使用弹性部署，需先完成企业认证等）",
    "api": "接口使用问题（路径/参数/鉴权头与官方文档不符，改调用方代码即可）",
    "service": "服务端问题（5xx/超时/网络不可达，与服务方或网络环境有关）",
    "token": "Token 无效（先到 控制台->设置->开发者Token 重新获取）",
    "unknown": "无法自动归类（请人工对照原始返回判断）",
}

# 关键词表（全部小写后做包含匹配）。官方未公开错误码表，只能启发式归类。
TOKEN_INVALID_HINTS = [
    "token无效", "token错误", "token过期", "invalid token", "token is invalid",
    "token is expired", "unauthorized", "未登录", "登录失效", "鉴权失败",
    "身份验证失败", "not authenticated",
]
PERMISSION_HINTS = [
    "企业认证", "认证企业", "未认证", "请先认证", "实名认证", "无权限", "权限不足",
    "未开通", "无权访问", "不允许", "资质", "白名单", "forbidden", "access denied",
    "permission denied", "permissiondenied", "not allowed",
]
NOT_FOUND_HINTS = [
    "not found", "接口不存在", "路径错误", "no route", "method not allowed",
    "404", "service not found",
]
PARAM_HINTS = [
    "参数错误", "参数不合法", "必填", "校验失败", "invalid param", "invalid parameter",
    "invalid request", "bad request", "missing",
]
SERVICE_HINTS = [
    "internal error", "server error", "internal server", "bad gateway",
    "service unavailable", "gateway timeout", "服务器错误", "服务器内部",
    "系统繁忙", "繁忙", "稍后重试", "降级", "熔断",
]


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def new_session(token):
    """按官方文档构造带鉴权头的会话：headers = {"Authorization": "<token>"}"""
    s = requests.Session()
    s.headers.update({
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "autodl-deploy-permission-probe/1.0",
    })
    return s


def post_json(session, path, payload):
    """调用一个只读查询接口，返回统一结构，绝不抛异常。

    返回 dict:
      transport: bool  是否完成了 HTTP 往返（False = 网络/超时层面失败）
      status:    int   HTTP 状态码（无响应时为 None）
      body:      dict  服务端 JSON（解析失败时为原始文本截断）
      error:     str   网络/解析错误描述
    """
    url = BASE_URL + path
    try:
        resp = session.post(url, json=payload, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        return {"transport": False, "status": None, "body": None,
                "error": "请求超时（%ss）: %s" % (TIMEOUT, url)}
    except requests.exceptions.ConnectionError:
        return {"transport": False, "status": None, "body": None,
                "error": "连接失败（域名解析/网络不可达/TLS）: %s" % url}
    except requests.exceptions.RequestException as e:
        return {"transport": False, "status": None, "body": None,
                "error": "请求异常: %s (%s)" % (url, e)}

    try:
        body = resp.json()
    except ValueError:
        body = (resp.text or "")[:500]
    return {"transport": True, "status": resp.status_code, "body": body, "error": None}


def body_text(result, limit=400):
    """把响应体压成一行短文本，便于打印原始返回。"""
    body = result.get("body")
    if body is None:
        return result.get("error") or ""
    if isinstance(body, dict):
        return json.dumps(body, ensure_ascii=False)[:limit]
    return str(body)[:limit]


def classify_failure(result):
    """把一次失败的调用归类为 account / api / service / token / unknown。

    归类优先级：先看网络层（服务问题），再按 401 -> 403/权限词 -> 404/405/参数词
    -> 5xx/服务词 的顺序扫关键词；都未命中归 unknown 并保留原始返回。
    """
    if not result["transport"]:
        return "service", result["error"]

    status = result["status"]
    body = result["body"] if isinstance(result["body"], dict) else {}
    code = str(body.get("code", "") or "")
    msg = str(body.get("msg", "") or body.get("message", "") or "")
    text = (code + " " + msg).lower()
    raw = "HTTP %s, code=%r, msg=%r" % (status, code[:80], msg[:200])

    if status == 401 or any(h in text for h in TOKEN_INVALID_HINTS):
        return "token", raw
    if status == 403 or any(h in text for h in PERMISSION_HINTS):
        return "account", raw
    if status in (404, 405) or any(h in text for h in NOT_FOUND_HINTS):
        return "api", raw
    if status == 400 or any(h in text for h in PARAM_HINTS):
        return "api", raw
    if status >= 500 or any(h in text for h in SERVICE_HINTS):
        return "service", raw
    return "unknown", raw


# ---------------------------------------------------------------------------
# 第 1 步：验证 Token 与服务可用性（只读：查余额）
# ---------------------------------------------------------------------------
def step1_token_and_service(session):
    """返回 (状态, 原始返回)。状态: ok / token / service / 其他归类。"""
    print("=" * 72)
    print("第 1 步  验证 Token 与服务可用性（只读查余额）")
    print("  POST /api/v1/dev/wallet/balance")
    print("=" * 72)
    result = post_json(session, "/api/v1/dev/wallet/balance", {})
    print("  HTTP 状态: %s" % result["status"])

    if not result["transport"]:
        print("  [失败] %s" % result["error"])
        return "service", result["error"]

    body = result["body"]
    if isinstance(body, dict) and body.get("code") == "Success":
        data = body.get("data") or {}
        assets = data.get("assets")
        voucher = data.get("voucher_balance")
        print("  [OK] Token 有效，API 服务响应正常")
        if isinstance(assets, (int, float)):
            print("  账户余额: %.2f 元" % (assets / 1000.0))  # 文档: 金额除以1000等于元
        if isinstance(voucher, (int, float)):
            print("  代金券余额: %.2f 元" % (voucher / 1000.0))
        return "ok", body_text(result)

    category, raw = classify_failure(result)
    print("  [失败] %s" % CATEGORY_DESC[category])
    print("  原始返回: %s" % body_text(result))
    return category, raw


# ---------------------------------------------------------------------------
# 第 2 步：探测弹性部署 API 权限（只读：查部署列表）
# ---------------------------------------------------------------------------
def step2_deployment_permission(session, token_validated):
    """只读调用 deployment/list 探测权限。返回 (状态, 原始返回, 现有部署数)。

    官方查询接口即 POST；这里绝不调用创建接口 POST /api/v1/dev/deployment。
    若第 1 步已证明 Token 有效，而本步仍返回 401/鉴权类错误，
    则更可能是权限不足的另一种表现，归为账号资质问题。
    """
    print()
    print("=" * 72)
    print("第 2 步  探测弹性部署 API 权限（只读查部署列表，不会创建任何东西）")
    print("  POST /api/v1/dev/deployment/list")
    print("=" * 72)
    result = post_json(session, "/api/v1/dev/deployment/list",
                       {"page_index": 1, "page_size": 10})
    print("  HTTP 状态: %s" % result["status"])

    if not result["transport"]:
        print("  [失败] %s" % result["error"])
        return "service", result["error"], None

    body = result["body"]
    if isinstance(body, dict) and body.get("code") == "Success":
        data = body.get("data") or {}
        deploy_list = data.get("list") or []
        total = data.get("result_total", len(deploy_list))
        print("  [OK] 弹性部署 API 可用，账号具备使用权限")
        print("  当前部署数: %s（本次未创建/未改动任何部署）" % total)
        return "ok", body_text(result), total

    category, raw = classify_failure(result)
    if category == "token" and token_validated:
        # Token 已在第 1 步验证有效，这里再报鉴权错通常是权限问题
        print("  [注意] Token 已在第 1 步验证有效，此处的鉴权类报错按权限不足处理")
        category = "account"
    print("  [失败] %s" % CATEGORY_DESC[category])
    print("  原始返回: %s" % body_text(result))
    return category, raw, None


# ---------------------------------------------------------------------------
# 第 3 步：查询 RTX 4090 库存（只读：按区域查 GPU 库存）
# ---------------------------------------------------------------------------
def parse_gpu_stock(data):
    """把 gpu_stock 的 data 解析成 {GPU型号: {"idle": n, "total": n}}。

    官方示例: "data": [ {"RTX 4090": {"idle_gpu_num": 215, "total_gpu_num": 2285}}, ...]
    为兼容格式变化，同时支持 data 直接是 dict（型号->统计）的形态。
    """
    stocks = {}
    items = []
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = data
    for item in items:
        if not isinstance(item, dict):
            continue
        for gpu_name, stat in item.items():
            if not isinstance(stat, dict):
                continue
            try:
                idle = int(stat.get("idle_gpu_num") or 0)
                total = int(stat.get("total_gpu_num") or 0)
            except (TypeError, ValueError):
                continue
            cur = stocks.setdefault(gpu_name, {"idle": 0, "total": 0})
            cur["idle"] += idle
            cur["total"] += total
    return stocks


def step3_gpu_stock(session, dep_status):
    """逐区域查询库存，筛出 4090 系。返回 (4090结果行列表, 失败区域列表)。

    若第 2 步已判定权限/接口/服务失败，库存接口（同属弹性部署 API）大概率同样
    失败，此时只试查 1 个区域确认行为，不再浪费 11 次请求。
    """
    print()
    print("=" * 72)
    print("第 3 步  查询 RTX 4090 库存（只读，按区域查询）")
    print("  POST /api/v1/dev/machine/region/gpu_stock")
    print("=" * 72)

    regions = REGIONS if dep_status == "ok" else REGIONS[:1]
    if dep_status != "ok":
        print("  [提示] 第 2 步未通过，库存接口与部署接口同族，只试查首个区域确认行为")

    rows_4090 = []   # [(区域名, region_sign, GPU型号, idle, total)]
    failed = []      # [(区域名, 分类, 原因)]
    for sign, cn_name in regions:
        result = post_json(session, "/api/v1/dev/machine/region/gpu_stock",
                           {"region_sign": sign})
        if not result["transport"]:
            failed.append((cn_name, "service", result["error"]))
            continue
        body = result["body"]
        if isinstance(body, dict) and body.get("code") == "Success":
            stocks = parse_gpu_stock(body.get("data"))
            for gpu_name, stat in stocks.items():
                if TARGET_GPU_KEYWORD in gpu_name.upper():
                    rows_4090.append((cn_name, sign, gpu_name,
                                      stat["idle"], stat["total"]))
        else:
            category, raw = classify_failure(result)
            failed.append((cn_name, category, raw))
        time.sleep(REGION_QUERY_GAP)

    if rows_4090:
        print("  %-14s %-12s %-16s %8s %8s" % ("区域", "region_sign", "GPU型号",
                                               "空闲卡数", "总卡数"))
        for cn_name, sign, gpu_name, idle, total in rows_4090:
            print("  %-14s %-12s %-16s %8d %8d" % (cn_name, sign, gpu_name,
                                                   idle, total))
        idle_sum = sum(r[3] for r in rows_4090)
        print("  ----")
        print("  4090 系合计空闲: %d 张（跨 %d 个区域）"
              % (idle_sum, len(set((r[1]) for r in rows_4090))))
    else:
        print("  [结果] 没有任何区域报告 4090 系库存"
              "（可能是售罄/该区域无此型号，或库存接口不可用——见下方失败信息）")

    if failed:
        print("  查询失败的区域:")
        for cn_name, category, raw in failed:
            print("    - %s: [%s] %s" % (cn_name, category, raw))
    print("  [注意] 官方文档提示：库存按「单容器 1 张卡」估算，多卡容器不一定能调度")
    return rows_4090, failed


# ---------------------------------------------------------------------------
# 结论
# ---------------------------------------------------------------------------
def print_conclusion(dep_status, dep_raw, rows_4090):
    print()
    print("=" * 72)
    print("结论")
    print("=" * 72)

    if dep_status == "ok":
        print("  1) 能否创建部署: 可以（权限层面通过，弹性部署 API 对本账号可用）")
        print("     依据: 只读接口 deployment/list 调用成功。本次未实际创建任何资源。")
        print("     注意: 权限通过不等于创建必成功，还取决于余额、库存和创建参数。")
    else:
        print("  1) 能否创建部署: 不能（探路阶段即失败，原因见下）")
        print("     原因归类: %s" % CATEGORY_DESC[dep_status])
        print("     服务端原始返回: %s" % (dep_raw or "（无）"))
        if dep_status == "account":
            print("     应对: 到 控制台 完成企业认证（官方文档: 使用弹性部署API需先")
            print("            认证企业）。这是账号侧问题，改接口调用代码没有用。")
        elif dep_status == "api":
            print("     应对: 核对接口路径/参数/鉴权头是否与官方文档一致")
            print("            (https://www.autodl.com/docs/esd_api_doc/)。")
        elif dep_status == "service":
            print("     应对: 服务端/网络问题，稍后重试；持续失败需联系 AutoDL。")
        else:
            print("     应对: 请把本脚本输出发给开发，对照官方文档人工判断。")

    print()
    if rows_4090:
        idle_sum = sum(r[3] for r in rows_4090)
        print("  2) RTX 4090 库存: 有，4090 系合计空闲 %d 张（明细见第 3 步表格）" % idle_sum)
    else:
        print("  2) RTX 4090 库存: 未查到可用的 4090 库存（详见第 3 步输出）")
    print()
    print("  再次确认: 本脚本只调用了 3 个只读查询接口，没有创建任何部署或实例。")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print("AutoDL 弹性部署探路脚本（只读探测，不创建任何资源）")
    print("API: %s   时间: %s" % (BASE_URL, time.strftime("%Y-%m-%d %H:%M:%S")))
    print()

    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print("[本地配置错误] 未设置环境变量 AUTODL_TOKEN")
        print("  获取方式: AutoDL 控制台 -> 设置 -> 开发者Token")
        print("  设置方式: export AUTODL_TOKEN=\"你的token\" 后重新运行")
        sys.exit(EXIT_LOCAL)

    session = new_session(token)

    # 第 1 步：Token + 服务可用性
    st1, raw1 = step1_token_and_service(session)
    if st1 == "service":
        print()
        print_conclusion("service", "第 1 步即失败，弹性部署 API 未探测: %s" % raw1, [])
        print("  （连通性/服务都不通时，后两步结论无从谈起）")
        sys.exit(EXIT_SERVICE)
    if st1 != "ok":
        # token 无效 / 或其他归类失败：无有效凭据则后两步结论不可信
        print()
        print_conclusion(st1 if st1 in ("token",) else "unknown", raw1, [])
        sys.exit(CATEGORY_EXIT.get(st1, EXIT_UNKNOWN))

    # 第 2 步：弹性部署权限探测
    st2, raw2, _deploy_total = step2_deployment_permission(session,
                                                           token_validated=True)

    # 第 3 步：RTX 4090 库存
    rows_4090, _failed = step3_gpu_stock(session, st2)

    # 结论与退出码
    print_conclusion(st2, raw2, rows_4090)
    if st2 == "ok":
        sys.exit(EXIT_OK)
    sys.exit(CATEGORY_EXIT.get(st2, EXIT_UNKNOWN))


if __name__ == "__main__":
    main()
