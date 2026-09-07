"""查询一台 AutoDL 容器实例（Pro）的当前状态。

用法：
    AUTODL_TOKEN=<你的token> AUTODL_INSTANCE_UUID=<实例uuid> python3 main.py

Token 获取：AutoDL 控制台 -> 账号 -> 设置 -> 开发者Token。

本脚本会刻意区分两类失败，它们的排查方向完全不同：
  1. 实例不存在（RecordNotFoundError / "未查询到相关实例"）——请求本身是合法的，
     只是这台实例查不到：UUID 抄错、实例已被释放等。
  2. 请求本身写错（RequestParameterIsWrong / "请求参数错误"）——实例还没查到就
     被接口拒绝了：传参方式、参数格式有问题，该先检查自己的代码和参数。

退出码：0 成功；2 环境变量缺失；3 实例不存在；4 请求参数错误；
        5 其他 API/响应错误；6 网络错误。可在脚本/CI 里据此分流处理。
"""

import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
STATUS_URL = f"{BASE_URL}/api/v1/dev/instance/pro/status"

# 退出码约定
EXIT_OK = 0
EXIT_ENV_MISSING = 2
EXIT_NOT_FOUND = 3
EXIT_BAD_REQUEST = 4
EXIT_API_ERROR = 5
EXIT_NETWORK = 6

# AutoDL 没有公开稳定的错误码枚举表，code 和 msg 两边都做匹配更稳妥。
# 以下特征均来自真实调用实测（见技能包 references/instances.md）。
NOT_FOUND_CODES = ("RecordNotFoundError",)
NOT_FOUND_MSG_HINTS = ("未查询到相关实例",)
BAD_REQUEST_CODES = ("RequestParameterIsWrong",)
BAD_REQUEST_MSG_HINTS = ("请求参数错误",)

# 实测出现过的状态值及含义；遇到未知状态原样打印，不当成错误。
STATUS_LABELS = {
    "starting": "启动中（刚创建/刚开机，尚未完全就绪）",
    "running": "运行中",
    "shutting_down": "关机中（尚未完全关机）",
    "shutdown": "已关机",
}


def looks_like(code, msg, codes, msg_hints):
    """按错误码或 msg 文本判断错误类别。"""
    return code in codes or any(hint in msg for hint in msg_hints)


def main():
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    instance_uuid = os.environ.get("AUTODL_INSTANCE_UUID", "").strip()

    missing = [
        name
        for name, value in (
            ("AUTODL_TOKEN", token),
            ("AUTODL_INSTANCE_UUID", instance_uuid),
        )
        if not value
    ]
    if missing:
        print(
            "环境变量缺失：" + "、".join(missing)
            + "。请设置 AUTODL_TOKEN（控制台 -> 账号 -> 设置 -> 开发者Token）"
            "和 AUTODL_INSTANCE_UUID 后重试。"
        )
        return EXIT_ENV_MISSING

    # 注意两个坑（均已实测验证）：
    # 1. 鉴权头是 "Authorization: <token>"，没有 Bearer 前缀；
    # 2. 官方文档把这个 GET 接口的参数写在"请求 Body 示例"里，是错的——
    #    放进 JSON body 会返回 RequestParameterIsWrong，必须用 params= 走查询字符串。
    try:
        resp = requests.get(
            STATUS_URL,
            headers={"Authorization": token},
            params={"instance_uuid": instance_uuid},
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[网络错误] 请求没能完成，检查本机网络/代理后再试：{exc}")
        return EXIT_NETWORK

    try:
        payload = resp.json()
    except ValueError:
        print(
            f"[响应异常] 接口返回了无法解析为 JSON 的内容"
            f"（HTTP {resp.status_code}）：{resp.text[:200]!r}"
        )
        return EXIT_API_ERROR

    code = str(payload.get("code", ""))
    msg = str(payload.get("msg", ""))
    request_id = payload.get("request_id", "")

    if code == "Success":
        status = payload.get("data")
        label = STATUS_LABELS.get(status, "未知状态（不代表出错，可能是平台新状态）")
        print(f"实例 {instance_uuid} 当前状态：{status}（{label}）")
        return EXIT_OK

    diag = f"（code={code or '<空>'}, msg={msg or '<空>'}"
    diag += f", request_id={request_id}）" if request_id else "）"

    if looks_like(code, msg, NOT_FOUND_CODES, NOT_FOUND_MSG_HINTS):
        # 请求本身是合法的，只是查不到这台实例。
        print(
            f"[实例不存在] 没有查到 UUID 为 {instance_uuid} 的实例，请求本身没有问题。\n"
            "排查建议：① 确认 UUID 是否抄错（形如 pro-xxxxxxxxxxxx）；"
            "② 实例可能已被释放——已释放的实例不会再出现在任何查询里；"
            "③ 确认该实例属于当前 Token 对应的账号。\n"
            f"接口返回 {diag}"
        )
        return EXIT_NOT_FOUND

    if looks_like(code, msg, BAD_REQUEST_CODES, BAD_REQUEST_MSG_HINTS):
        # 请求在查库之前就被拒绝了，和实例存不存在无关。
        print(
            f"[请求参数错误] 请求本身写错了，接口没有去查实例就拒绝了它。\n"
            "排查建议：① GET 接口参数必须放在 URL 查询字符串（params=），"
            "不能放 JSON body——官方文档的 Body 示例是错的；"
            "② 检查 instance_uuid 的取值和格式是否完整、有无多余空白或转义。\n"
            f"接口返回 {diag}"
        )
        return EXIT_BAD_REQUEST

    # 其他已知类别（如 TORealName 未实名、BadRequest 无权限）原样透出，不做猜测。
    print(
        f"[API 返回错误] HTTP {resp.status_code}，{diag}\n"
        "这既不是\"实例不存在\"也不是\"请求参数错误\"，"
        "请根据 msg 内容判断（如 Token 无效、账号未实名认证、无资源访问权限等）。"
    )
    return EXIT_API_ERROR


if __name__ == "__main__":
    sys.exit(main())
