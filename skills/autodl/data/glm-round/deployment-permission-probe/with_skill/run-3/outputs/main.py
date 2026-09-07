#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoDL 弹性部署 · 创建权限探针（只读探测，不创建任何资源）。

回答两件事：
  1. 当前账号现在能不能"创建弹性部署"；
  2. RTX 4090 在各可调度地区有没有库存。

为什么"不创建也能探明能不能创建"：
  AutoDL 弹性部署的权限门槛是【按接口区分】的（2026-09 真实调用验证）：
    - 查 GPU 库存 / 查镜像列表：只读公共查询，未企业认证也能调；
    - 创建部署 / 查部署列表 / 查调度黑名单 / 查时长包：涉及账号自己的部署
      资源，共用同一道【企业认证】门槛——未企业认证的账号调用会返回
      {"code":"BadRequest","msg":"无当前资源访问权限"}。
  因此用只读的"部署列表"+"调度黑名单"两个接口即可探明账号是否具备创建部署
  所需的认证等级，全程不产生任何真实资源、不产生费用。

失败原因归类（三类应对方式完全不同）：
  账号资质问题：TORealName（未实名认证）／
                BadRequest + 无当前资源访问权限（未企业认证）→ 去控制台做认证
  接口用错了  ：RequestParameterIsWrong、HTTP 404 等 → 修我们的代码/参数
  服务本身问题：超时、连接失败、HTTP 5xx、InternalError、响应非 JSON → 重试/找平台
  （另设"Token 无效"一类：环境变量里的 Token 不对，先修凭证再谈其他）

安全性声明：本脚本只调用只读接口（余额 / 部署列表 / 调度黑名单 / GPU 库存），
不会创建、修改或删除任何部署、实例、容器。

用法：
  export AUTODL_TOKEN="你的开发者Token"    # 控制台 → 账号 → 设置 → 开发者Token
  python3 main.py

退出码：0 结论明确（无论"能"还是"不能"创建）；2 AUTODL_TOKEN 未设置；3 无法得出结论。

接口依据：https://www.autodl.com/docs/esd_api_doc/ 与 https://www.autodl.com/docs/common_api/
"""

import json
import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
REQUEST_TIMEOUT = 20  # 单次请求超时（秒）
TARGET_GPU = "RTX 4090"

# 弹性部署全部可调度地区（官方文档附录），查库存时逐区扫描
REGION_NAMES = {
    "westDC2": "西北企业区",
    "westDC3": "西北B区",
    "beijingDC1": "北京A区",
    "beijingDC2": "北京B区",
    "beijingDC4": "L20专区（原北京C区）",
    "beijingDC3": "V100专区（原华南A区）",
    "neimengDC1": "内蒙A区",
    "neimengDC3": "内蒙B区",
    "foshanDC1": "佛山区",
    "chongqingDC1": "重庆A区",
    "yangzhouDC1": "3090专区",
}

# 探测结果归类
CAT_OK = "OK"
CAT_ACCOUNT = "账号资质问题"
CAT_API_USAGE = "接口用错了"
CAT_SERVICE = "服务本身问题"
CAT_TOKEN = "Token 无效"
CAT_UNKNOWN = "无法归类"

EXIT_OK = 0
EXIT_NO_TOKEN = 2
EXIT_INCONCLUSIVE = 3


def rule(char="=", width=68):
    return char * width


def fmt_payload(payload, limit=300):
    """把 JSON 响应压成一行短文本，便于原样展示。"""
    if payload is None:
        return "(无 JSON 响应体)"
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(payload)
    return text if len(text) <= limit else text[:limit] + "...(截断)"


def call_api(method, path, token, json_body=None):
    """发起一次 API 请求；网络/解析异常不抛出，统一装进返回值。

    返回 {"status": HTTP 状态码或 None, "payload": 解析后的 JSON 或 None,
          "error": 网络层/解析层错误描述或 None}
    """
    url = BASE_URL + path
    try:
        resp = requests.request(
            method,
            url,
            headers={"Authorization": token},  # 注意：AutoDL 鉴权头没有 Bearer 前缀
            json=json_body,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return {"status": None, "payload": None,
                "error": "网络请求失败（超时/无法连接）: %s" % (exc,)}

    try:
        payload = resp.json()
    except ValueError:
        snippet = (resp.text or "")[:200] or "(空响应体)"
        return {"status": resp.status_code, "payload": None,
                "error": "HTTP %s 且响应不是 JSON: %s" % (resp.status_code, snippet)}
    return {"status": resp.status_code, "payload": payload, "error": None}


def classify(result):
    """把一次调用的结果归入上面定义的类别。返回 (类别, 说明文本)。

    AutoDL 没有稳定的错误码枚举表，以 code + msg 文本为准（2026-09 实测）：
      TORealName                -> 未实名认证（账号资质）
      BadRequest + 权限/认证字样 -> 认证等级不够（账号资质，弹性部署=未企业认证）
      RequestParameterIsWrong   -> 请求参数/传参方式不对（接口用错）
      InternalError             -> 平台内部错误（服务问题）
    """
    if result["error"] is not None:
        # 网络失败 / 网关返回非 JSON —— 都算服务/网络侧，不是我们参数的问题
        return CAT_SERVICE, result["error"]

    status = result["status"]
    payload = result["payload"] or {}
    code = str(payload.get("code", ""))
    msg = str(payload.get("msg", ""))

    if code == "Success":
        return CAT_OK, "code=Success"

    if code == "TORealName":
        return CAT_ACCOUNT, "code=%s, msg=%r —— 账号未完成实名认证" % (code, msg)
    if code == "BadRequest" and ("权限" in msg or "认证" in msg):
        return CAT_ACCOUNT, ("code=%s, msg=%r —— 账号认证等级不够"
                             % (code, msg))
    if code == "BadRequest":
        return CAT_API_USAGE, "code=%s, msg=%r —— 请求被拒绝" % (code, msg)
    if code in ("RequestParameterIsWrong", "RecordNotFoundError"):
        return CAT_API_USAGE, "code=%s, msg=%r" % (code, msg)
    if code == "InternalError":
        return CAT_SERVICE, "code=%s, msg=%r —— 平台内部错误" % (code, msg)

    if status == 401:
        return CAT_TOKEN, "HTTP 401 —— Token 无效或过期"
    if status == 403:
        return CAT_UNKNOWN, "HTTP 403 —— 被拒绝（需结合 msg 人工判断）"
    if status == 404:
        return CAT_API_USAGE, "HTTP 404 —— 接口路径可能不对"
    if status is not None and 500 <= status <= 599:
        return CAT_SERVICE, "HTTP %s —— 服务端错误" % status

    return CAT_UNKNOWN, "HTTP %s, code=%s, msg=%r" % (status, code, msg)


# ---------------------------------------------------------------- 步骤 1

def probe_token_and_balance(token):
    """查余额：任何认证等级的账号都能调，用来验证 Token 是否有效。

    返回 (类别, 可用余额元数或 None)。
    """
    print("\n" + rule("-"))
    print("[步骤 1] 验证 Token 并查余额   POST /api/v1/dev/wallet/balance")
    print(rule("-"))

    result = call_api("POST", "/api/v1/dev/wallet/balance", token)
    cat, detail = classify(result)
    print("  原始返回: %s" % fmt_payload(result["payload"]))
    if result["error"]:
        print("  传输层  : %s" % result["error"])

    balance = None
    if cat == CAT_OK:
        data = (result["payload"] or {}).get("data") or {}
        if isinstance(data, dict):
            assets = data.get("assets")
            blocked = data.get("blocked_asset") or 0
            if isinstance(assets, (int, float)):
                balance = (assets - blocked) / 1000.0  # 接口单位是 元×1000
                print("  ✓ Token 有效；可用余额 ≈ %.2f 元"
                      "（assets=%s, 冻结=%s）" % (balance, assets, blocked))
            else:
                print("  ✓ Token 有效；但响应里没有 assets 字段，余额未知")
        else:
            print("  ✓ Token 有效；但响应 data 结构异常，余额未知")
    else:
        print("  ✗ 余额查询失败，归类【%s】：%s" % (cat, detail))
    return cat, balance


# ---------------------------------------------------------------- 步骤 2

def probe_deployment_permission(token):
    """核心探针：用与"创建部署"共用同一道企业认证门槛的两个只读接口，
    探明账号能否创建部署。不创建任何资源。

    返回 {"verdict": "yes"/"no"/"unknown", "category": 归类,
          "headline": 一句话结论, "basis": 判定依据, "advice": 应对建议}
    """
    print("\n" + rule("-"))
    print('[步骤 2] 探测"能否创建部署"（只读，不创建任何资源）')
    print(rule("-"))
    print("  原理：创建部署需要【企业认证】，而只读的『部署列表』『调度黑名单』")
    print("        与它共用同一道门槛（2026-09 实测：未企业认证调这两个接口")
    print("        返回 code=BadRequest, msg=无当前资源访问权限）。")
    print("        所以『这两个接口能调通 == 账号具备创建部署的认证等级』。")

    print("\n  ◆ 主探针：查部署列表   POST /api/v1/dev/deployment/list"
          '   body={"page_index": 1, "page_size": 1}')
    res_list = call_api("POST", "/api/v1/dev/deployment/list", token,
                        json_body={"page_index": 1, "page_size": 1})
    cat_list, detail_list = classify(res_list)
    print("    原始返回: %s" % fmt_payload(res_list["payload"]))
    if res_list["error"]:
        print("    传输层  : %s" % res_list["error"])
    print("    判定    : 【%s】" % cat_list)

    print("\n  ◆ 交叉验证：查生效中的调度黑名单   GET /api/v1/dev/deployment/blacklist")
    res_bl = call_api("GET", "/api/v1/dev/deployment/blacklist", token)
    cat_bl, detail_bl = classify(res_bl)
    print("    原始返回: %s" % fmt_payload(res_bl["payload"]))
    if res_bl["error"]:
        print("    传输层  : %s" % res_bl["error"])
    print("    判定    : 【%s】" % cat_bl)

    consistent = cat_list == cat_bl
    if consistent:
        print("\n  两个探针结论一致（%s），置信度高。" % cat_list)
    else:
        print("\n  ！两个探针结论不一致（部署列表=%s，黑名单=%s），以主探针"
              "（部署列表）为准，置信度降低。" % (cat_list, cat_bl))

    payload_code = str((res_list["payload"] or {}).get("code", ""))

    if cat_list == CAT_OK:
        return {
            "verdict": "yes",
            "category": None,
            "headline": "能（权限前提满足，推定结论）",
            "basis": ("部署列表接口正常返回 code=Success%s。它与创建部署共用同一道"
                      "企业认证门槛，说明账号已具备创建弹性部署所需的认证等级。"
                      % ("，黑名单交叉验证同样通过" if cat_bl == CAT_OK else
                         "（黑名单交叉验证未通过，建议重跑确认）")),
            "advice": ("可以进入下一步：准备镜像和 container_template 正式创建部署"
                       "（注意运行时还需库存、余额等条件满足）。"),
        }

    if cat_list == CAT_ACCOUNT:
        if payload_code == "TORealName":
            basis = ("部署列表返回 code=TORealName, msg=未完成实名认证——账号连"
                     "实名认证都没做，更不可能有创建部署所需的企业认证。")
            advice = ("先到 AutoDL 控制台完成【个人实名认证】；注意即便实名通过，"
                      "创建弹性部署仍需【企业认证】。")
        else:
            basis = ("部署列表返回 code=BadRequest, msg=无当前资源访问权限——"
                     "2026-09 实测这是『账号未完成企业认证』的标准返回；弹性部署"
                     "的创建门槛是企业认证，高于容器实例 Pro API（个人实名即可）。")
            advice = ("到 AutoDL 控制台完成【企业认证】后重跑本脚本验证；期间如有"
                      "临时需求，可退而用容器实例 Pro API（个人实名即可）先跑通"
                      "推理服务原型。")
        return {
            "verdict": "no",
            "category": CAT_ACCOUNT,
            "headline": "不能 —— 账号资质问题（不是接口用错，也不是服务故障）",
            "basis": basis + ("黑名单交叉验证返回相同错误，判定一致。"
                              if cat_bl == CAT_ACCOUNT else ""),
            "advice": advice,
        }

    if cat_list == CAT_API_USAGE:
        return {
            "verdict": "unknown",
            "category": CAT_API_USAGE,
            "headline": "无法判断 —— 我们的调用方式有问题（接口用错了）",
            "basis": ("部署列表被参数校验拦截：%s。请求到达了服务且通过了鉴权，"
                      "失败出在请求构造上，不是账号资质问题。" % detail_list),
            "advice": ("对照官方文档核对请求方式（本脚本已按文档：POST + JSON "
                       "body、Authorization 头不带 Bearer 前缀、page_index/"
                       "page_size 必填）；修正后重跑。"),
        }

    if cat_list == CAT_SERVICE:
        return {
            "verdict": "unknown",
            "category": CAT_SERVICE,
            "headline": "无法判断 —— 服务本身/网络问题",
            "basis": "部署列表调用失败：%s。" % detail_list,
            "advice": ("先确认本机能访问 api.autodl.com（步骤 1 余额接口若正常，"
                       "则更像平台侧问题）；稍后重试，持续失败联系 AutoDL 支持。"
                       "与账号资质无关。"),
        }

    if cat_list == CAT_TOKEN:
        return {
            "verdict": "unknown",
            "category": CAT_TOKEN,
            "headline": "无法判断 —— Token 问题",
            "basis": ("部署列表返回鉴权失败：%s。若步骤 1 余额正常而这里 401，"
                      "说明该接口对 Token 有额外要求，需人工核对。" % detail_list),
            "advice": "在控制台重新生成开发者 Token 后重跑。",
        }

    return {
        "verdict": "unknown",
        "category": CAT_UNKNOWN,
        "headline": "无法判断 —— 返回了文档未覆盖的错误",
        "basis": "部署列表：%s；黑名单：%s。" % (detail_list, detail_bl),
        "advice": ("把上方原始返回对照官方文档（www.autodl.com/docs/esd_api_doc）"
                   "人工判断；注意区分是权限类还是参数类错误。"),
    }


# ---------------------------------------------------------------- 步骤 3

def probe_gpu_stock(token, gpu_name):
    """逐区扫描弹性部署 GPU 库存。该接口是只读公共查询，不需要企业认证，
    所以无论步骤 2 结论如何都能独立给出库存答案。

    返回 {"rows": [(地区码, 地区名, idle, total), ...], "errors": [(地区码, 原因)]}
    """
    print("\n" + rule("-"))
    print("[步骤 3] 查 %s 库存   POST /api/v1/dev/machine/region/gpu_stock"
          "（逐区扫描 %d 个可调度地区）" % (gpu_name, len(REGION_NAMES)))
    print(rule("-"))

    rows, errors = [], []
    for region_code, region_name in REGION_NAMES.items():
        res = call_api("POST", "/api/v1/dev/machine/region/gpu_stock", token,
                       json_body={"region_sign": region_code,
                                  "gpu_name_set": [gpu_name]})
        cat, detail = classify(res)
        if cat != CAT_OK:
            errors.append((region_code, detail))
            continue

        # 响应 data 是列表，每一项形如 {"RTX 4090": {"idle_gpu_num": 215, ...}}
        data = (res["payload"] or {}).get("data")
        idle = total = None
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                for name, stats in item.items():
                    if name == gpu_name and isinstance(stats, dict):
                        idle = stats.get("idle_gpu_num")
                        total = stats.get("total_gpu_num")
        rows.append((region_code, region_name, idle, total))

    print("  %-12s %-20s %8s %8s  %s" % ("地区码", "地区", "空闲", "总数", "状态"))
    for code, name, idle, total in rows:
        if idle is None:
            status = "无此型号返回"
        elif idle > 0:
            status = "有货"
        else:
            status = "有该型号但当前无空闲"
        print("  %-12s %-20s %8s %8s  %s"
              % (code, name, "—" if idle is None else idle,
                 "—" if total is None else total, status))
    for code, detail in errors:
        print("  %-12s 查询失败：%s" % (code, detail))

    # 官方文档提示：库存按“调度 1 张卡”口径统计，多卡容器不能直接当保证
    print("\n  注：库存按『调度 1 张卡』口径统计——空闲 2 张可能分属两台机器，")
    print("      单容器需要多卡时不代表一定能调度成功，需留重试/降级余地。")
    return {"rows": rows, "errors": errors}


# ---------------------------------------------------------------- 汇总

def final_report(perm, stock, balance):
    print("\n" + rule("="))
    print("探测结论")
    print(rule("="))

    print("\n【问题 1】当前账号能否创建弹性部署？")
    print("  答：%s" % perm["headline"])
    print("  依据：%s" % perm["basis"])
    print("  应对：%s" % perm["advice"])
    print("  （说明：本脚本未调用创建接口 POST /api/v1/dev/deployment，"
          "『能创建』指认证/权限前提满足的推定结论）")

    print("\n【问题 2】%s 有没有库存？" % TARGET_GPU)
    rows, errors = stock["rows"], stock["errors"]
    in_stock = [(c, n, i) for c, n, i, _ in rows if isinstance(i, int) and i > 0]
    total_idle = sum(i for _, _, i in in_stock)
    if in_stock:
        detail = "、".join("%s(%s) %d 张" % (c, n, i) for c, n, i in in_stock)
        print("  答：有 —— %d 个地区有货，合计空闲 %d 张（单卡口径）"
              % (len(in_stock), total_idle))
        print("      %s" % detail)
    elif rows and not errors:
        print("  答：没有 —— 各可调度地区当前均无空闲的 %s"
              "（或该地区没有这个型号）。" % TARGET_GPU)
    else:
        print("  答：无法确认 —— 库存查询失败 %d/%d 个地区。"
              % (len(errors), len(errors) + len(rows)))
    if errors:
        print("      失败地区（不影响问题 1 的权限结论）：%s"
              % "、".join(c for c, _ in errors))
    if perm["verdict"] == "yes" and balance is not None and balance < 10.0:
        print("      顺带提醒：余额仅 ≈ %.2f 元，正式创建部署会产生计费。" % balance)

    print("\n【安全性声明】本次探测只调用了 4 类只读接口（余额、部署列表、")
    print("              调度黑名单、GPU 库存），未创建、修改或删除任何")
    print("              部署/实例/容器，不产生资源与费用。")


def main():
    print(rule())
    print("AutoDL 弹性部署 · 创建权限探针（只读探测，不创建任何资源）")
    print("目标：%s 库存查询 + 创建部署权限确认" % TARGET_GPU)
    print(rule())

    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print("✗ 环境变量 AUTODL_TOKEN 未设置。")
        print("  Token 获取：AutoDL 控制台 → 账号 → 设置 → 开发者Token")
        print('  用法：export AUTODL_TOKEN="你的token" && python3 main.py')
        return EXIT_NO_TOKEN

    balance_cat, balance = probe_token_and_balance(token)
    if balance_cat == CAT_TOKEN:
        print("\n结论：Token 无效，先在控制台重新生成开发者 Token 再重跑本脚本。")
        print("      （此情况下无法判断账号资质，也不必怀疑接口或服务。）")
        return EXIT_INCONCLUSIVE
    if balance_cat != CAT_OK:
        print("\n  ！余额接口异常（%s），继续后续探测——各探针独立判定。"
              % balance_cat)

    perm = probe_deployment_permission(token)
    stock = probe_gpu_stock(token, TARGET_GPU)
    final_report(perm, stock, balance)

    return EXIT_OK if perm["verdict"] in ("yes", "no") else EXIT_INCONCLUSIVE


if __name__ == "__main__":
    sys.exit(main())
