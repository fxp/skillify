#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoDL 弹性部署能力探测脚本(只读探路,不创建任何部署/容器/实例)。

背景:
    我们准备用 AutoDL 弹性部署跑推理服务,先探路确认:
      1) 当前账号到底能不能创建弹性部署;
      2) RTX 4090 各区域有没有库存;
      3) 如果不能,原因属于哪一类(三类的应对方式完全不同):
           - 账号资质问题(未完成企业认证/无权限) -> 去控制台做企业认证
           - 接口用错(路径/方法/参数/鉴权头)      -> 对照官方文档改代码
           - 服务本身问题(5xx/超时/网络不可达)     -> 稍后重试或找客服

探测原理(只调用只读查询接口,绝无创建类调用):
    1) POST /api/v1/dev/wallet/balance
       通用接口,做基线:验证 Token 是否有效、API 服务是否可达。
    2) POST /api/v1/dev/deployment/list
       弹性部署的只读接口。官方文档说明"使用弹性部署API需先认证企业",
       即整套弹性部署 API 由企业认证统一把门,且没有独立的资质查询接口;
       因此该接口能通 == 账号已过资质门 == 具备创建部署的权限。
    3) POST /api/v1/dev/machine/region/gpu_stock
       按区域查询 RTX 4090 库存(idle_gpu_num / total_gpu_num)。
       注意:库存按"单卡调度"口径统计,2 卡容器未必放得下。

用法:
    export AUTODL_TOKEN="你的开发者Token"    # 控制台 -> 设置 -> 开发者Token
    python3 main.py

退出码:
    0   探测通过,账号可以创建弹性部署
    10  不能创建:账号资质问题(企业认证/权限)
    20  探测失败:接口用错(路径/方法/参数)
    30  探测失败:服务本身问题(5xx/超时/网络不可达)
    40  Token 无效(先换 Token 再谈其他)
    50  原因无法自动归类,请查看原始返回人工判断
    2   环境问题(缺 AUTODL_TOKEN 环境变量或缺 requests 库)

依赖: 仅 requests(pip3 install requests)
文档: https://www.autodl.com/docs/esd_api_doc/  (弹性部署 API)
      https://www.autodl.com/docs/common_api/    (通用 API)
"""

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("[环境错误] 缺少 requests 库,请先安装: pip3 install requests")
    sys.exit(2)

BASE_URL = "https://api.autodl.com"
TIMEOUT_SECONDS = 15
TARGET_GPU = "RTX 4090"

# 官方文档列出的弹性部署区域(region_sign, 备注)
REGIONS: List[Tuple[str, str]] = [
    ("westDC2", "西北企业区,文档推荐"),
    ("westDC3", ""),
    ("beijingDC1", ""),
    ("beijingDC2", ""),
    ("beijingDC3", "V100"),
    ("beijingDC4", "L20"),
    ("neimengDC1", ""),
    ("neimengDC3", ""),
    ("foshanDC1", ""),
    ("chongqingDC1", ""),
    ("yangzhouDC1", "3090"),
]

# ===== 结论分类 =====
V_OK = "OK"                        # 探测通过
V_QUALIFICATION = "QUALIFICATION"  # 账号资质问题(企业认证/权限)
V_MISUSE = "API_MISUSE"            # 接口用错(路径/方法/参数)
V_SERVICE = "SERVICE_ERROR"        # 服务本身问题(5xx/超时/网络不可达)
V_TOKEN = "TOKEN_INVALID"          # Token 无效
V_UNKNOWN = "UNKNOWN"              # 无法自动归类

EXIT_CODES = {
    V_OK: 0,
    V_QUALIFICATION: 10,
    V_MISUSE: 20,
    V_SERVICE: 30,
    V_TOKEN: 40,
    V_UNKNOWN: 50,
}

VERDICT_TEXT = {
    V_OK: "通过",
    V_QUALIFICATION: "失败 -> 账号资质问题(企业认证/权限)",
    V_MISUSE: "失败 -> 接口用错(路径/方法/参数)",
    V_SERVICE: "失败 -> 服务本身问题(5xx/超时/网络)",
    V_TOKEN: "失败 -> Token 无效",
    V_UNKNOWN: "失败 -> 无法自动归类",
}

SUGGESTIONS = {
    V_OK: "账号已具备弹性部署 API 权限,可以编写创建逻辑"
          "(POST /api/v1/dev/deployment)。注意:库存按单卡口径统计,多卡容器未必放得下。",
    V_QUALIFICATION: "应对:到 AutoDL 控制台完成企业认证后重跑本脚本。"
                     "这是账号资质问题——代码不用改,也不是服务故障。",
    V_MISUSE: "应对:对照官方文档 https://www.autodl.com/docs/esd_api_doc/ 核对"
              "路径/HTTP方法/参数/鉴权头;若官方接口已变更,以最新文档为准。这不是账号问题。",
    V_SERVICE: "应对:稍后重试;若持续失败,查看 AutoDL 公告/状态或联系客服。"
               "账号与代码大概率没问题,不要急着改。",
    V_TOKEN: "应对:到 控制台 -> 设置 -> 开发者Token 重新生成,并"
             " export AUTODL_TOKEN=新Token 后重跑。",
    V_UNKNOWN: "应对:请把上方打印的原始返回(HTTP状态/code/msg)交给人工或客服判断。",
}

# 官方未提供错误码表,只能按 HTTP 状态 + code/msg 关键字推断失败类别
STRONG_CERT_KEYWORDS = ("企业", "认证", "资质", "实名", "审核", "开通", "certif", "enterprise")
PERM_KEYWORDS = ("权限", "无权", "未授权", "permission", "forbidden", "denied")
TOKEN_KEYWORDS = ("token", "apikey", "api key", "令牌", "未登录", "请登录", "登录过期", "鉴权")


@dataclass
class ApiResult:
    """一次 API 调用的原始结果(只记录,不改动任何服务端状态)。"""
    path: str
    purpose: str
    network_ok: bool = True
    status: Optional[int] = None
    body: Optional[Dict[str, Any]] = None  # JSON 返回(dict);非 dict 或解析失败为 None
    raw: str = ""                          # 非 JSON/非 dict 返回时的截断预览
    error: str = ""                        # 网络层异常信息


def call_api(session: requests.Session, path: str, body: Dict[str, Any], purpose: str) -> ApiResult:
    """POST 一个 JSON 请求,捕获网络层异常;只发请求并记录响应,不做重试。"""
    result = ApiResult(path=path, purpose=purpose)
    try:
        resp = session.post(BASE_URL + path, json=body, timeout=TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        result.network_ok = False
        result.error = "请求超时(>%d 秒)" % TIMEOUT_SECONDS
        return result
    except requests.exceptions.ConnectionError as exc:
        result.network_ok = False
        result.error = "连接失败(服务不可达或本地网络问题): %s" % _short(str(exc))
        return result
    except requests.exceptions.RequestException as exc:
        result.network_ok = False
        result.error = "请求异常: %s" % _short(str(exc))
        return result

    result.status = resp.status_code
    try:
        parsed = resp.json()
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        result.body = parsed
    else:
        result.raw = _short(resp.text if resp.text else str(parsed))
    return result


def _short(text: str, limit: int = 200) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "..."


def classify(res: ApiResult) -> Tuple[str, str]:
    """把一次调用结果归类为: 通过 / 账号资质 / 接口用错 / 服务问题 / Token无效 / 无法归类。"""
    if not res.network_ok:
        return V_SERVICE, res.error
    if res.body is not None and res.body.get("code") == "Success":
        return V_OK, ""

    code = str(res.body.get("code", "")) if res.body else ""
    msg = str(res.body.get("msg", "")) if res.body else ""
    detail = "HTTP %s | code=%r | msg=%r" % (res.status, code, msg)
    if res.raw:
        detail += " | 原始返回: %s" % res.raw
    text = (code + " " + msg).lower()

    has_cert = any(k in text for k in STRONG_CERT_KEYWORDS)
    has_perm = any(k in text for k in PERM_KEYWORDS)
    has_token = any(k in text for k in TOKEN_KEYWORDS)

    # 文本关键字优先于 HTTP 状态:比如 401 + "需企业认证" 应归为资质问题
    if has_cert or has_perm:
        return V_QUALIFICATION, detail
    if has_token:
        return V_TOKEN, detail
    if res.status == 401:
        return V_TOKEN, detail + "(401 且无其他线索,通常是 Token 无效)"
    if res.status == 403:
        return V_QUALIFICATION, detail + "(403 通常是权限/资质门槛)"
    if res.status in (404, 405):
        return V_MISUSE, detail + "(路径或 HTTP 方法不对)"
    if res.status in (400, 422):
        return V_MISUSE, detail + "(请求参数被拒绝)"
    if res.status is not None and res.status >= 500:
        return V_SERVICE, detail + "(服务端错误)"
    if res.status == 200 and not code:
        return V_MISUSE, detail + "(返回体不符合文档约定,可能路径打到了错误的服务)"
    return V_UNKNOWN, detail


def extract_stock_rows(node: Any, rows: List[Dict[str, Any]]) -> None:
    """递归找出含 idle_gpu_num/total_gpu_num 的对象;官方未给出 data 的精确结构,做兼容解析。"""
    if isinstance(node, dict):
        if "idle_gpu_num" in node or "total_gpu_num" in node:
            rows.append(node)
            return
        for value in node.values():
            extract_stock_rows(value, rows)
    elif isinstance(node, list):
        for value in node:
            extract_stock_rows(value, rows)


def format_stock(data: Any) -> Tuple[Optional[str], Optional[int]]:
    """把库存 data 解析为 (可读文本, 最大可用卡数);解析不出结构时返回 (None, None)。"""
    rows: List[Dict[str, Any]] = []
    extract_stock_rows(data, rows)
    if not rows:
        return None, None
    parts = []
    max_idle: Optional[int] = None
    for row in rows:
        name = row.get("gpu_name") or row.get("gpu_type") or row.get("name") or TARGET_GPU
        idle = row.get("idle_gpu_num")
        total = row.get("total_gpu_num")
        parts.append("%s: 可用 %s / 总计 %s" % (
            name,
            idle if idle is not None else "?",
            total if total is not None else "?",
        ))
        if isinstance(idle, int):
            max_idle = idle if max_idle is None else max(max_idle, idle)
    return "; ".join(parts), max_idle


def show(res: ApiResult, verdict: str, detail: str, note: str = "") -> None:
    """打印一次探测的证据(接口/HTTP/响应码/判定),方便人工复核。"""
    print("  接口: POST %s(%s)" % (res.path, res.purpose))
    if not res.network_ok:
        print("  网络层: %s" % res.error)
    else:
        body = res.body or {}
        print("  HTTP: %s | code=%r | msg=%r" % (res.status, body.get("code"), body.get("msg")))
        if res.raw:
            print("  原始返回(截断): %s" % res.raw)
    print("  判定: %s" % VERDICT_TEXT[verdict])
    if detail and verdict != V_OK:
        print("        %s" % detail)
    if note:
        print("  %s" % note)


def conclude(v_balance: str, v_list: str, stock_verdicts: List[str]) -> Tuple[str, str]:
    """汇总三步证据,给出最终结论与依据。主判据是 deployment/list(与创建部署同一权限门)。"""
    corroborated = (
        v_list in (V_QUALIFICATION, V_TOKEN, V_SERVICE, V_MISUSE)
        and stock_verdicts
        and all(v == v_list for v in stock_verdicts)
    )
    extra = "且 GPU 库存接口(同属弹性部署 API)返回同类错误,相互印证。" if corroborated else ""

    if v_list == V_OK:
        return V_OK, (
            "弹性部署只读接口 deployment/list 调用成功。官方文档说明整套弹性部署 API "
            "需先通过企业认证才能调用,因此账号已过资质门、具备创建部署的权限。"
            "100% 确认需实际创建一次,但本次按约定只探路、未实际创建。"
        )
    if v_list == V_QUALIFICATION:
        return V_QUALIFICATION, (
            "弹性部署接口被拒,返回内容指向企业认证/权限(证据见上)。"
            "这是账号资质问题:接口调用和服务本身都没问题。%s" % extra
        )
    if v_list == V_MISUSE:
        return V_MISUSE, (
            "弹性部署接口返回 404/400 类错误(证据见上),属于接口调用层问题"
            "(路径/方法/参数),先修正调用才能判断账号资质。%s" % extra
        )
    if v_list == V_SERVICE:
        return V_SERVICE, (
            "API 连不上或服务端 5xx(证据见上),属于服务本身/网络问题,"
            "与账号资质无关。%s" % extra
        )
    if v_list == V_TOKEN:
        if v_balance == V_TOKEN:
            return V_TOKEN, "通用接口与弹性部署接口都报 Token 问题,先换 Token 再重跑。"
        return V_UNKNOWN, (
            "通用接口正常但弹性部署接口报 Token 相关错误,自动归类失败,"
            "请人工核对上方原始返回。"
        )
    return V_UNKNOWN, "弹性部署接口失败原因无法自动归类,请人工核对上方原始返回。"


def main() -> None:
    print("=" * 68)
    print("AutoDL 弹性部署能力探测(只读探路)")
    print("目标: 1) 账号能否创建弹性部署  2) %s 库存  3) 失败原因归类" % TARGET_GPU)
    print("声明: 只调用只读查询接口,不会创建任何部署/容器/实例")
    print("=" * 68)

    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print("\n[环境错误] 未设置环境变量 AUTODL_TOKEN。")
        print("请先执行: export AUTODL_TOKEN=\"你的开发者Token\"  "
              "(获取路径: AutoDL 控制台 -> 设置 -> 开发者Token)")
        sys.exit(2)

    session = requests.Session()
    session.headers.update({"Authorization": token})

    # ---- 第 1 步: 基线,验证 Token 有效性与 API 连通性 ----
    print("\n---- 第 1 步: 基线鉴权(通用接口 wallet/balance) ----")
    r_balance = call_api(session, "/api/v1/dev/wallet/balance", {},
                         "验证 Token 是否有效、API 服务是否可达")
    v_balance, d_balance = classify(r_balance)
    note = ""
    if v_balance == V_OK:
        data = (r_balance.body or {}).get("data")
        if isinstance(data, dict) and isinstance(data.get("assets"), int):
            note = "账户余额: %.2f 元" % (data["assets"] / 1000.0)
    show(r_balance, v_balance, d_balance, note)

    # ---- 第 2 步: 弹性部署权限探针(只读 list) ----
    print("\n---- 第 2 步: 弹性部署权限探针(只读 deployment/list) ----")
    r_list = call_api(session, "/api/v1/dev/deployment/list",
                      {"page_index": 1, "page_size": 10},
                      "弹性部署 API 与创建部署同一权限门(企业认证)")
    v_list, d_list = classify(r_list)
    note = ""
    if v_list == V_OK:
        data = (r_list.body or {}).get("data")
        lst = data.get("list") if isinstance(data, dict) else None
        count = len(lst) if isinstance(lst, list) else "未知"
        note = "现有部署数量: %s(只读统计,未做任何改动)" % count
    show(r_list, v_list, d_list, note)

    # ---- 第 3 步: RTX 4090 库存(按区域,只读) ----
    regions = REGIONS if v_list == V_OK else REGIONS[:2]
    print("\n---- 第 3 步: %s 库存查询(按区域,只读) ----" % TARGET_GPU)
    if v_list != V_OK:
        print("  (第 2 步未通过,先只抽查 %d 个区域做佐证)" % len(regions))
    stock_verdicts: List[str] = []
    in_stock: List[str] = []
    out_stock: List[str] = []
    for sign, remark in regions:
        label = "%s(%s)" % (sign, remark) if remark else sign
        res = call_api(session, "/api/v1/dev/machine/region/gpu_stock",
                       {"region_sign": sign, "gpu_name_set": [TARGET_GPU]},
                       "查询 %s 的 %s 库存" % (sign, TARGET_GPU))
        verdict, detail = classify(res)
        stock_verdicts.append(verdict)
        if verdict == V_OK:
            text, max_idle = format_stock((res.body or {}).get("data"))
            if text:
                availability = "有货" if (max_idle or 0) > 0 else "无货"
                print("  %s: %s -> %s" % (label, text, availability))
                (in_stock if (max_idle or 0) > 0 else out_stock).append(sign)
            else:
                print("  %s: 调用成功但未解析到库存结构(该区域可能无此卡型)" % label)
                out_stock.append(sign)
        else:
            print("  %s: 查询失败,%s | %s" % (label, VERDICT_TEXT[verdict], detail))

    # ---- 汇总结论 ----
    verdict, reason = conclude(v_balance, v_list, stock_verdicts)
    print("\n" + "=" * 68)
    print("探测结论")
    print("=" * 68)
    if verdict == V_OK:
        print("能否创建弹性部署: [可以] (高置信,依据见下)")
    elif verdict == V_QUALIFICATION:
        print("能否创建弹性部署: [不能] —— 原因归类: 1/账号资质问题")
    elif verdict == V_MISUSE:
        print("能否创建弹性部署: [未能确认] —— 原因归类: 2/接口用错(先修调用再判断账号)")
    elif verdict == V_SERVICE:
        print("能否创建弹性部署: [未能确认] —— 原因归类: 3/服务本身问题")
    elif verdict == V_TOKEN:
        print("能否创建弹性部署: [未能确认] —— Token 无效(先换 Token)")
    else:
        print("能否创建弹性部署: [未能确认] —— 原因无法自动归类")
    print("依据: %s" % reason)
    print("建议: %s" % SUGGESTIONS[verdict])

    print("\n%s 库存汇总(单卡调度口径):" % TARGET_GPU)
    if in_stock:
        print("  有货区域: %s" % ", ".join(in_stock))
    if out_stock:
        print("  无货/无数据区域: %s" % ", ".join(out_stock))
    if not in_stock and not out_stock:
        print("  (库存查询全部失败,见第 3 步证据)")

    print("\n安全声明: 本次仅调用了余额/部署列表/GPU 库存三类只读查询接口,")
    print("未创建、未修改、未删除任何部署、容器或实例。")
    sys.exit(EXIT_CODES[verdict])


if __name__ == "__main__":
    main()
