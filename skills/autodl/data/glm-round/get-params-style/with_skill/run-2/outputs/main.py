#!/usr/bin/env python3
"""查询一台 AutoDL 容器实例（Pro）的当前状态。

用法:
    export AUTODL_TOKEN="你的开发者Token"          # 控制台 → 账号 → 设置 → 开发者Token
    export AUTODL_INSTANCE_UUID="pro-xxxxxxxx"
    python3 main.py

接口要点（官方文档 + 真实调用验证）:
- GET /api/v1/dev/instance/pro/status，参数 instance_uuid 必须放在 URL query string
  （requests 的 params=），放 JSON body 会返回 RequestParameterIsWrong;
- 鉴权头是裸 Token: Authorization: <token>，没有 "Bearer " 前缀;
- 响应统一为 {"code": "Success"/..., "msg": ..., "data": ...}，成功时 data 直接是
  状态字符串（如 "running"; 实测还存在 "starting"/"shutting_down"/"shutdown" 等中间态，
  轮询时属正常现象，不要当成异常）。

本脚本的核心目标：把「实例不存在」和「请求本身写错」这两类失败分开提示，
退出码也随之区分，方便排障和上游脚本判断:
    0 成功 | 1 环境变量缺失 | 2 实例不存在 | 3 请求本身写错 | 4 认证/权限 | 5 其他
"""

import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
STATUS_URL = f"{BASE_URL}/api/v1/dev/instance/pro/status"
TIMEOUT_SECONDS = 15

EXIT_OK = 0
EXIT_ENV_MISSING = 1
EXIT_NOT_FOUND = 2  # 实例不存在：请求本身是合法的，只是这个 UUID 查不到
EXIT_BAD_REQUEST = 3  # 请求本身写错：参数格式/传参方式有问题，和实例是否存在无关
EXIT_AUTH = 4  # Token 无效 / 账号权限不足
EXIT_OTHER = 5


def main() -> int:
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    instance_uuid = os.environ.get("AUTODL_INSTANCE_UUID", "").strip()

    missing = [
        name for name, value in
        (("AUTODL_TOKEN", token), ("AUTODL_INSTANCE_UUID", instance_uuid))
        if not value
    ]
    if missing:
        print(f"[环境变量缺失] 请先设置 {', '.join(missing)} 再运行。", file=sys.stderr)
        return EXIT_ENV_MISSING

    try:
        resp = requests.get(
            STATUS_URL,
            # 注意：不带 Bearer 前缀；GET 接口用 params（query string）传参
            headers={"Authorization": token},
            params={"instance_uuid": instance_uuid},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        print(f"[网络错误] 请求没能到达 AutoDL API：{exc}", file=sys.stderr)
        print("请先排查本机网络/代理/DNS，这与实例本身是否存在无关。", file=sys.stderr)
        return EXIT_OTHER

    # 平台正常时业务结果都在 JSON 体里（code/msg），HTTP 状态码仅作兜底参考
    try:
        payload = resp.json()
    except ValueError:
        print(
            f"[请求异常] API 返回了非 JSON 内容（HTTP {resp.status_code}），"
            f"响应开头：{resp.text[:200]!r}",
            file=sys.stderr,
        )
        print("通常是请求目标不对或被网关拦截，请核对脚本 URL 与 Token。", file=sys.stderr)
        return EXIT_BAD_REQUEST if resp.status_code in (400, 404, 405, 422) else EXIT_OTHER

    code = str(payload.get("code") or "")
    msg = str(payload.get("msg") or "")
    data = payload.get("data")

    if code == "Success":
        print(f"实例 {instance_uuid} 当前状态: {data}")
        return EXIT_OK

    # 先排除认证类失败（HTTP 401，或 msg 明确指向 token），避免和其他类别混淆
    if resp.status_code == 401 or "token" in msg.lower():
        print(f"[认证失败] HTTP {resp.status_code}, code={code!r}, msg={msg!r}", file=sys.stderr)
        print(
            "请检查 AUTODL_TOKEN 是否为有效的开发者 Token"
            "（控制台 → 账号 → 设置 → 开发者Token），Token 可能已过期或被重置。",
            file=sys.stderr,
        )
        return EXIT_AUTH

    # ---- 以下两类是要严格区分的核心场景 ----

    # 场景一：实例不存在。请求格式完全合法，API 只是找不到这台实例。
    if code == "RecordNotFoundError" or "未查询到相关实例" in msg or "not found" in msg.lower():
        print(f"[实例不存在] code={code!r}, msg={msg!r}", file=sys.stderr)
        print("请求本身是合法的，只是 API 查不到这台实例。可能原因：", file=sys.stderr)
        print(f"  1. AUTODL_INSTANCE_UUID（{instance_uuid}）抄错或复制不完整；", file=sys.stderr)
        print("  2. 实例已被释放——已释放的实例不会再出现在任何查询里；", file=sys.stderr)
        print("  3. 实例属于其他账号，当前 Token 无权查看。", file=sys.stderr)
        print("排查建议：用「获取实例列表」接口核对当前账号还能看到哪些实例。", file=sys.stderr)
        return EXIT_NOT_FOUND

    # 场景二：请求本身写错。参数格式/传参方式有问题，和实例是否存在无关。
    if code == "RequestParameterIsWrong" or "请求参数错误" in msg or "参数" in msg:
        print(f"[请求参数错误] code={code!r}, msg={msg!r}", file=sys.stderr)
        print("这是请求构造的问题，不代表实例不存在。可能原因：", file=sys.stderr)
        print(f"  1. AUTODL_INSTANCE_UUID（{instance_uuid}）格式非法（正常形如 pro-xxxxxxxx）；", file=sys.stderr)
        print("  2. 脚本被改动过，比如把 GET 参数改成了 JSON body——"
              "AutoDL 的 GET 接口只接受 URL query string。", file=sys.stderr)
        return EXIT_BAD_REQUEST

    # 账号资质类：请求合法、实例可能存在，但账号认证等级不够（如实名/企业认证）
    if code in ("TORealName", "BadRequest"):
        print(f"[账号/权限问题] code={code!r}, msg={msg!r}", file=sys.stderr)
        print("请求格式没问题，是当前账号的认证等级或资源权限不足"
              "（如未实名认证、无该资源访问权限），需到控制台完成认证。", file=sys.stderr)
        return EXIT_AUTH

    # 未枚举到的错误：原样给出 code/msg 供人工判断（官方没有稳定的错误码表）
    print(f"[未知错误] HTTP {resp.status_code}, code={code!r}, msg={msg!r}, data={data!r}", file=sys.stderr)
    print("AutoDL 未提供错误码枚举表，请根据上方 msg 文本进一步排查。", file=sys.stderr)
    return EXIT_OTHER


if __name__ == "__main__":
    sys.exit(main())
