#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoDL 弹性部署「创建权限 + RTX 4090 库存」探路脚本（纯只读，不创建任何资源）。

要回答的两件事：
  1. 当前账号（AUTODL_TOKEN 对应的账号）现在能不能创建弹性部署？
  2. RTX 4090 目前各地区还有没有库存？

为什么不创建部署也能判断"能不能创建"：
  AutoDL 弹性部署的权限门槛是按接口区分的——
    * 查余额、查 GPU 库存：不需要企业认证，任何有效账号都能调；
    * "账号部署资源"类接口（部署列表 / 时长包 / 黑名单 / 创建部署等）：统一要求
      企业认证，未认证一律返回 {"code": "BadRequest" 或 "1502",
      "msg": "无当前资源访问权限"}，且鉴权先于参数/资源校验（传不存在的
      deployment_uuid 也报同样的权限错）。
  因此用只读的 POST /api/v1/dev/deployment/list 当"创建权限探针"：它与创建部署
  走同一道企业认证闸门，但纯查询、不产生任何资源。探针通过 → 账号具备创建部署
  的权限资格；探针被权限拒绝 → 账号资质问题，真去创建也必然同样被拒。
  再用"任何账号都能调"的余额 / 库存接口做交叉验证：同一个 token 余额、库存都
  正常，唯独部署资源类接口被拒 → 问题在账号资质，不是接口用错（其他接口同一
  token 正常），也不是服务故障（服务有正常返回）。

失败原因归类（三类应对完全不同，外加一种凭证问题）：
  账号资质问题  未企业认证（无当前资源访问权限）/ 未实名（TORealName）
  接口用法问题  RequestParameterIsWrong、404、传参方式不对等
  服务端问题    5xx、超时、连接失败
  token 无效    凭证问题，三种之外，先换 token 再探

用法：AUTODL_TOKEN=你的token python3 main.py
退出码：0 = 探路完成（结论以输出为准）；1 = token 无效提前中止；2 = 缺少 AUTODL_TOKEN
"""

import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
TIMEOUT = 15  # 单个请求超时（秒）

TARGET_GPU = "RTX 4090"

# 官方文档附录的全部地区代码（创建部署的 dc_list 与查库存的 region_sign 共用这一套）
REGIONS = [
    ("westDC2", "西北企业区（推荐）"),
    ("westDC3", "西北B区"),
    ("beijingDC1", "北京A区"),
    ("beijingDC2", "北京B区"),
    ("beijingDC4", "L20专区（原北京C区）"),
    ("beijingDC3", "V100专区（原华南A区）"),
    ("neimengDC1", "内蒙A区"),
    ("neimengDC3", "内蒙B区"),
    ("foshanDC1", "佛山区"),
    ("chongqingDC1", "重庆A区"),
    ("yangzhouDC1", "3090专区"),
]

# 本脚本只调用以下三个只读接口，绝不调用创建部署 / 停止 / 删除等任何变更类接口：
#   POST /api/v1/dev/wallet/balance            查余额（验证 token 是否有效）
#   POST /api/v1/dev/deployment/list           查部署列表（创建权限探针）
#   POST /api/v1/dev/machine/region/gpu_stock  查 GPU 库存

QUALIFICATION = "账号资质问题"
USAGE = "接口用法问题"
SERVICE = "服务端问题"
CREDENTIAL = "token无效"
UNKNOWN = "无法归类"


def call_api(session, method, path, json_body=None):
    """调用 AutoDL API，返回 (http_status, payload 或 None, 网络层错误文本 或 None)。"""
    try:
        resp = session.request(method, BASE_URL + path, json=json_body, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        return None, None, f"请求超时（>{TIMEOUT}s）"
    except requests.exceptions.ConnectionError as exc:
        return None, None, f"连接失败：{exc}"
    except requests.exceptions.RequestException as exc:
        return None, None, f"请求异常：{exc}"
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    return resp.status_code, payload, None


def classify_failure(status, payload, net_err):
    """把一次失败调用归类。平台没有稳定的错误码枚举表，以 msg 文本为主要依据。"""
    code = str(payload.get("code", "")) if isinstance(payload, dict) else ""
    msg = str(payload.get("msg", "")) if isinstance(payload, dict) else ""
    if net_err or status is None:
        return SERVICE, f"{net_err or '无 HTTP 响应'}——网络层失败，疑似服务/网络不可用"
    if status in (401, 403) or "token" in (code + msg).lower() or "unauthorized" in (code + msg).lower():
        return CREDENTIAL, f"HTTP {status}, code={code}, msg={msg}——token 未通过鉴权"
    if code == "TORealName" or "实名" in msg:
        return QUALIFICATION, f"code={code}, msg={msg}——账号未完成实名认证"
    if "无当前资源访问权限" in msg or ("权限" in msg and code in ("BadRequest", "1502")):
        return QUALIFICATION, f"code={code}, msg={msg}——弹性部署资源类接口要求企业认证，当前账号认证等级不够"
    if code == "RequestParameterIsWrong" or "参数" in msg or status == 404:
        return USAGE, f"HTTP {status}, code={code}, msg={msg}——请求参数或接口地址/传参方式不对"
    if status >= 500:
        return SERVICE, f"HTTP {status}, code={code}, msg={msg}——服务端错误"
    if code == "InternalError":
        return SERVICE, f"code={code}, msg={msg}——服务端内部错误"
    return UNKNOWN, f"HTTP {status}, code={code}, msg={msg}"


def probe_balance(session):
    """探针 1：查余额。任何有效 token 都能调，用来验证凭证与连通性。"""
    print("=" * 66)
    print("探针 1/3：查余额 POST /api/v1/dev/wallet/balance（验证 token 有效性）")
    status, payload, err = call_api(session, "POST", "/api/v1/dev/wallet/balance")
    if isinstance(payload, dict) and payload.get("code") == "Success":
        data = payload.get("data") or {}
        # 金额字段是"元 × 1000"的整数，除以 1000 才是元；可用余额要再减去冻结部分
        assets = data.get("assets") or 0
        blocked = data.get("blocked_asset") or 0
        available = (assets - blocked) / 1000.0
        print(f"  ✓ token 有效。余额 {assets / 1000:.2f} 元，冻结 {blocked / 1000:.2f} 元，可用约 {available:.2f} 元")
        return {"ok": True, "available": available}
    category, reason = classify_failure(status, payload, err)
    print(f"  ✗ 失败 [{category}] {reason}")
    if isinstance(payload, dict):
        print(f"    原始响应：{payload}")
    return {"ok": False, "category": category, "reason": reason}


def probe_deployment_permission(session):
    """探针 2：查部署列表。与创建部署同一道企业认证闸门，纯只读，是本脚本的核心探针。"""
    print("=" * 66)
    print("探针 2/3：查部署列表 POST /api/v1/dev/deployment/list（创建权限探针，只读不创建）")
    # page_index / page_size 为必填；不带其他过滤条件，只取第 1 页即可
    status, payload, err = call_api(
        session, "POST", "/api/v1/dev/deployment/list",
        json_body={"page_index": 1, "page_size": 10},
    )
    if isinstance(payload, dict) and payload.get("code") == "Success":
        data = payload.get("data") or {}
        total = data.get("result_total")
        total_str = total if isinstance(total, int) else "未知数量"
        print(f"  ✓ 探针通过：部署资源类接口正常返回（账号名下已有部署 {total_str} 个）。")
        print("    该接口与“创建部署”共享同一道企业认证门槛 → 账号具备创建部署的资格。")
        return {"ok": True}
    category, reason = classify_failure(status, payload, err)
    print(f"  ✗ 失败 [{category}] {reason}")
    if isinstance(payload, dict):
        print(f"    原始响应：{payload}")
    return {"ok": False, "category": category, "reason": reason}


def iter_stock_entries(data):
    """解析库存响应。data 是数组，每个元素形如 {"RTX 4090": {"idle_gpu_num": .., ...}}。"""
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                for gpu_name, info in entry.items():
                    yield str(gpu_name), info if isinstance(info, dict) else {}
    elif isinstance(data, dict):  # 防御：万一平台改成字典直出的形式
        for gpu_name, info in data.items():
            yield str(gpu_name), info if isinstance(info, dict) else {}


def probe_gpu_stock(session):
    """探针 3：逐地区查 RTX 4090 库存。此接口不需要企业认证，任何有效账号可调。"""
    print("=" * 66)
    print(f"探针 3/3：查 GPU 库存 POST /api/v1/dev/machine/region/gpu_stock（筛选 {TARGET_GPU}）")
    rows, failures = [], []
    for region, label in REGIONS:
        status, payload, err = call_api(
            session, "POST", "/api/v1/dev/machine/region/gpu_stock",
            json_body={"region_sign": region, "gpu_name_set": [TARGET_GPU]},
        )
        if not (isinstance(payload, dict) and payload.get("code") == "Success"):
            category, reason = classify_failure(status, payload, err)
            failures.append((region, category, reason))
            print(f"  ✗ {region}（{label}）查询失败 [{category}]")
            continue
        for gpu_name, info in iter_stock_entries(payload.get("data")):
            if TARGET_GPU not in gpu_name:
                continue
            idle = info.get("idle_gpu_num")
            total = info.get("total_gpu_num")
            rows.append({
                "region": region, "label": label, "gpu_name": gpu_name,
                "idle": idle if isinstance(idle, int) else -1,
                "total": total if isinstance(total, int) else -1,
                "chip_corp": info.get("chip_corp", ""),
                "cpu_arch": info.get("cpu_arch", ""),
            })
        if not any(TARGET_GPU in r["gpu_name"] for r in rows if r["region"] == region):
            rows.append({"region": region, "label": label, "gpu_name": TARGET_GPU,
                         "idle": 0, "total": 0, "chip_corp": "", "cpu_arch": "", "absent": True})
    if rows:
        rows.sort(key=lambda r: -(r["idle"] if r["idle"] >= 0 else 0))
        print(f"  {'地区代码':<12} {'地区名称':<14} {'空闲卡数':>8} {'总卡数':>8}")
        for r in rows:
            idle_str = str(r["idle"]) if r["idle"] >= 0 else "N/A"
            total_str = str(r["total"]) if r["total"] >= 0 else "N/A"
            mark = "（无该型号）" if r.get("absent") else ""
            print(f"  {r['region']:<12} {r['label']:<14} {idle_str:>8} {total_str:>8} {mark}")
    if failures and not rows:
        region, category, reason = failures[0]
        print(f"  ✗ 所有 {len(REGIONS)} 个地区都查询失败，首个错误 [{category}] {reason}")
        return {"ok": False, "category": category, "reason": reason}
    return {"ok": True, "rows": rows, "failures": failures}


def print_verdict(balance, deploy, stock):
    print()
    print("=" * 66)
    print("探路结论")
    print("=" * 66)

    print()
    print("一、当前账号能不能创建弹性部署？")
    if deploy["ok"]:
        print("  ✅ 能（权限层面没有障碍）。")
        print("     依据：部署列表接口（与创建部署同一道企业认证闸门）返回 Success，")
        print("           说明账号已完成创建部署所需的认证等级，token 和接口用法均正常。")
        print("     注意：这只确认“有资格创建”。真正创建时仍可能遇到个别规格临时无库存、")
        print("           余额不足等运行期问题，与权限无关。")
    else:
        cat = deploy["category"]
        if cat == QUALIFICATION:
            print("  ❌ 不能。原因归类：【账号资质问题】——不是接口用错，也不是服务故障。")
            if balance.get("ok"):
                print("     依据：① 同一个 token 查余额正常 → token 有效、服务在线；")
                print("           ② 库存等公开只读接口可用 → 接口地址与传参方式正确；")
                print("           ③ 唯独部署资源类接口被“无当前资源访问权限”拒绝 →")
                print("              弹性部署要求企业认证，当前账号未完成，属于认证等级不足。")
            else:
                print(f"     依据：{deploy['reason']}")
            print("     应对：到 AutoDL 控制台完成企业认证（个人实名不够），完成后重跑本脚本")
            print("           复核；代码本身不需要改。")
        elif cat == USAGE:
            print("  ⚠️ 暂不能下结论：探针疑似被【接口用法问题】拦下（请求没发对）。")
            print(f"     依据：{deploy['reason']}")
            print("     应对：核对接口地址 / 参数名 / 传参方式（本平台所有 GET 接口一律用")
            print("           query string 传参；鉴权头是 Authorization: <token>，不带 Bearer），")
            print("           修正脚本后重跑。")
        elif cat == SERVICE:
            print("  ❌ 暂不能判定：探针遇到【服务端问题】（5xx / 超时 / 连不上）。")
            print(f"     依据：{deploy['reason']}")
            if balance.get("ok"):
                print("     补充：余额接口同一时刻正常，可能是部署类接口单独故障，稍后重试；")
                print("           若持续失败请联系平台或查看 status 页。")
        elif cat == CREDENTIAL:
            print("  ⚠️ 探针返回鉴权失败，但与余额结果矛盾，罕见情况。")
            print(f"     原始信息：{deploy['reason']}")
            print("     应对：请把上方“原始响应”反馈出来人工判断。")
        else:
            print(f"  ⚠️ 无法归类，请把上方“原始响应”反馈出来人工判断：{deploy['reason']}")

    print()
    print(f"二、{TARGET_GPU} 库存情况：")
    if stock.get("ok"):
        rows = stock["rows"]
        in_stock = [r for r in rows if r["idle"] > 0]
        idle_sum = sum(r["idle"] for r in in_stock)
        if in_stock:
            best = max(in_stock, key=lambda r: r["idle"])
            names = "、".join(f"{r['region']}({r['idle']}张)" for r in in_stock)
            print(f"  ✅ 有货：{len(in_stock)}/{len(rows)} 个地区有空闲卡，合计空闲 {idle_sum} 张。")
            print(f"     最充裕的地区：{best['region']}（{best['label']}），空闲 {best['idle']} 张。")
            print(f"     明细：{names}")
        else:
            print(f"  ❌ 无货：{len(rows)} 个地区都没有 {TARGET_GPU} 空闲卡（或平台无此型号）。")
        print("     提醒：库存按“单容器调度 1 张卡”的口径统计——查到 2 张不代表能一次调度")
        print("           到同机的 2 张卡；多卡容器要做重试/降级准备。")
        if stock.get("failures"):
            print(f"     另有 {len(stock['failures'])} 个地区查询失败（已跳过，见上方日志）。")
    else:
        print(f"  ✗ 库存查询失败 [{stock['category']}] {stock['reason']}")

    print()
    print("（本脚本全程只做只读查询：查余额、查部署列表、查库存；未创建、未变更任何资源。）")


def main():
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print("缺少环境变量 AUTODL_TOKEN（获取路径：控制台 → 账号 → 设置 → 开发者Token）。")
        print("用法：AUTODL_TOKEN=你的token python3 main.py")
        return 2

    # AutoDL 鉴权头没有 Bearer 前缀，直接放 token 本身
    session = requests.Session()
    session.headers.update({"Authorization": token})

    balance = probe_balance(session)
    if not balance["ok"] and balance["category"] == CREDENTIAL:
        print()
        print("提前中止：token 未通过鉴权。这既不是账号资质问题也不是服务问题，")
        print("请先到控制台重新获取开发者 Token 再跑本脚本。")
        return 1

    deploy = probe_deployment_permission(session)
    stock = probe_gpu_stock(session)
    print_verdict(balance, deploy, stock)
    return 0


if __name__ == "__main__":
    sys.exit(main())
