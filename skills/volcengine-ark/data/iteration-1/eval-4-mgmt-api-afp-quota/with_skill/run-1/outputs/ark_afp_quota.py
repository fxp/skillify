#!/usr/bin/env python3
"""Query the remaining AFP quota of a Volcengine Ark *Agent Plan* (personal edition).

Reads the 5-hour / weekly / monthly (and, when present, daily) AFP windows via
the Ark management-plane Action ``GetAFPUsage`` and prints a warning for every
window whose remaining share is below a threshold (default 10 %).

Why the management plane
------------------------
AFP quota is an *account* attribute, not something the inference (data-plane)
endpoints ``/api/plan/v3`` expose. The data-plane Agent Plan API Key cannot be
used here; the management plane requires a Volcengine Access Key / Secret Key
(HMAC-SHA256 "Signature V4" request signing, Service ``ark``, Region
``cn-beijing``).

Endpoint
    POST https://ark.cn-beijing.volcengineapi.com/?Action=GetAFPUsage&Version=2024-01-01
    body: {}                         (no request parameters)
    Result: {"PlanType": "Medium",
             "AFPFiveHour": {"Quota": "10000", "Used": "1234",
                             "SubscribeTime": 1756800000000, "ResetTime": 1756818000000},
             "AFPDaily": {...}, "AFPWeekly": {...}, "AFPMonthly": {...}}
    ``Quota`` / ``Used`` are strings (AFP), timestamps are epoch milliseconds.

Optionally ``GetPersonalPlan`` (body ``{"Plan": "AgentPlan"}``) is called for
the plan status / expiry.

Credentials (environment variables only, never hard-code):
    VOLC_ACCESSKEY      Access Key ID   (prefer an IAM sub-user AK with Ark permission)
    VOLC_SECRETKEY      Secret Access Key
    VOLC_SESSION_TOKEN  optional, for temporary STS credentials

Transport
    ``--transport auto`` (default) uses the official ``volcengine-python-sdk``
    (``volcenginesdkcore.UniversalApi``) when it is installed and falls back to a
    dependency-free implementation of the Volcengine signing algorithm using only
    the standard library.

Exit codes
    0  all windows above threshold
    2  at least one window at/below threshold (handy for cron / CI)
    1  request or parsing error
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import hmac
import json
import logging
import os
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional

__all__ = [
    "ArkMgmtError",
    "AfpWindow",
    "AfpUsage",
    "ArkManagementClient",
    "StdlibSigner",
    "get_afp_usage",
    "get_personal_plan",
    "find_low_windows",
    "main",
]

LOG = logging.getLogger("ark_afp_quota")

# --- Management-plane constants (see references/management-api.md) ---------------
MGMT_HOST = "ark.cn-beijing.volcengineapi.com"
MGMT_SERVICE = "ark"
MGMT_REGION = "cn-beijing"
MGMT_VERSION = "2024-01-01"

ACTION_GET_AFP_USAGE = "GetAFPUsage"
ACTION_GET_PERSONAL_PLAN = "GetPersonalPlan"

ENV_AK = "VOLC_ACCESSKEY"
ENV_SK = "VOLC_SECRETKEY"
ENV_SESSION_TOKEN = "VOLC_SESSION_TOKEN"

# Window key in the GetAFPUsage result -> human label.
# 5h / week / month govern text + embedding models; the daily window only applies to
# image / video / speech / Harness usage (those are exempt from the 5h and weekly caps).
WINDOW_LABELS: Dict[str, str] = {
    "AFPFiveHour": "5 小时",
    "AFPDaily": "日 (仅图片/视频/语音/Harness)",
    "AFPWeekly": "周",
    "AFPMonthly": "月",
}
PRIMARY_WINDOWS = ("AFPFiveHour", "AFPWeekly", "AFPMonthly")

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_THRESHOLD_PERCENT = 10.0


class ArkMgmtError(RuntimeError):
    """A management-plane call failed (transport, HTTP or API-level error)."""

    def __init__(self, message: str, *, code: Optional[str] = None,
                 http_status: Optional[int] = None, request_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.request_id = request_id

    def __str__(self) -> str:  # pragma: no cover - formatting only
        parts = [super().__str__()]
        if self.code:
            parts.append(f"code={self.code}")
        if self.http_status is not None:
            parts.append(f"http={self.http_status}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " | ".join(parts)


# --- Data model ------------------------------------------------------------------
@dataclass(frozen=True)
class AfpWindow:
    key: str
    quota: Decimal
    used: Decimal
    subscribe_time_ms: Optional[int] = None
    reset_time_ms: Optional[int] = None

    @property
    def label(self) -> str:
        return WINDOW_LABELS.get(self.key, self.key)

    @property
    def remaining(self) -> Decimal:
        # Never report negative remaining (overage postpaid can push Used past Quota).
        return max(self.quota - self.used, Decimal(0))

    @property
    def remaining_percent(self) -> Optional[Decimal]:
        """Remaining share in percent, or None when Quota is 0 / unknown."""
        if self.quota <= 0:
            return None
        return (self.remaining / self.quota) * 100

    def is_below(self, threshold_percent: float) -> bool:
        pct = self.remaining_percent
        if pct is None:
            # Quota 0 means the window is not sold on this plan (or the API returned
            # nothing usable); do not raise a false alarm.
            return False
        return pct <= Decimal(str(threshold_percent))

    @property
    def reset_time(self) -> Optional[_dt.datetime]:
        return _ms_to_local(self.reset_time_ms)

    @property
    def subscribe_time(self) -> Optional[_dt.datetime]:
        return _ms_to_local(self.subscribe_time_ms)

    def to_dict(self) -> Dict[str, Any]:
        pct = self.remaining_percent
        return {
            "window": self.key,
            "label": self.label,
            "quota": str(self.quota),
            "used": str(self.used),
            "remaining": str(self.remaining),
            "remaining_percent": None if pct is None else float(round(pct, 2)),
            "subscribe_time": _iso(self.subscribe_time),
            "reset_time": _iso(self.reset_time),
        }


@dataclass
class AfpUsage:
    plan_type: Optional[str]
    windows: List[AfpWindow] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def window(self, key: str) -> Optional[AfpWindow]:
        for w in self.windows:
            if w.key == key:
                return w
        return None

    @classmethod
    def from_result(cls, result: Mapping[str, Any]) -> "AfpUsage":
        windows: List[AfpWindow] = []
        for key in WINDOW_LABELS:
            obj = result.get(key)
            if not isinstance(obj, Mapping):
                continue
            windows.append(
                AfpWindow(
                    key=key,
                    quota=_to_decimal(obj.get("Quota"), f"{key}.Quota"),
                    used=_to_decimal(obj.get("Used"), f"{key}.Used"),
                    subscribe_time_ms=_to_int_or_none(obj.get("SubscribeTime")),
                    reset_time_ms=_to_int_or_none(obj.get("ResetTime")),
                )
            )
        if not windows:
            raise ArkMgmtError(
                "GetAFPUsage returned no AFP windows (expected AFPFiveHour/AFPWeekly/AFPMonthly); "
                f"raw Result keys: {sorted(result.keys())}"
            )
        return cls(plan_type=result.get("PlanType"), windows=windows, raw=dict(result))


def find_low_windows(usage: AfpUsage, threshold_percent: float,
                     keys: Optional[List[str]] = None) -> List[AfpWindow]:
    """Return the windows whose remaining share is at/below ``threshold_percent``."""
    wanted = set(keys) if keys else None
    return [w for w in usage.windows
            if (wanted is None or w.key in wanted) and w.is_below(threshold_percent)]


# --- Helpers ---------------------------------------------------------------------
def _to_decimal(value: Any, field_name: str) -> Decimal:
    if value is None or value == "":
        return Decimal(0)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ArkMgmtError(f"Field {field_name} is not numeric: {value!r}") from exc


def _to_int_or_none(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ms_to_local(ms: Optional[int]) -> Optional[_dt.datetime]:
    if ms is None:
        return None
    return _dt.datetime.fromtimestamp(ms / 1000, tz=_dt.timezone.utc).astimezone()


def _iso(value: Optional[_dt.datetime]) -> Optional[str]:
    return value.isoformat(timespec="seconds") if value else None


def _unwrap_result(payload: Any, action: str) -> Dict[str, Any]:
    """Return ``Result`` from a management-plane envelope, raising on API errors."""
    if not isinstance(payload, Mapping):
        raise ArkMgmtError(f"{action}: unexpected response type {type(payload).__name__}")
    meta = payload.get("ResponseMetadata") or {}
    err = meta.get("Error") if isinstance(meta, Mapping) else None
    if err:
        raise ArkMgmtError(
            f"{action} failed: {err.get('Message', '')}".strip(),
            code=err.get("Code"),
            request_id=meta.get("RequestId"),
        )
    if "Result" in payload:
        result = payload["Result"]
        if result is None:
            result = {}
        if not isinstance(result, Mapping):
            raise ArkMgmtError(f"{action}: Result is not an object: {result!r}")
        return dict(result)
    # Some SDK code paths hand back the already-unwrapped Result.
    return dict(payload)


# --- Transport 1: official SDK (volcengine-python-sdk) ----------------------------
class _SdkTransport:
    """Call any Action through ``volcenginesdkcore.UniversalApi``.

    ``volcenginesdkark.ARKApi`` (checked against volcengine-python-sdk 5.0.48) does not
    expose the 2026 Plan Actions (GetAFPUsage / GetPersonalPlan / ...), so the generic
    UniversalApi is the SDK-supported way to reach them.
    """

    def __init__(self, ak: str, sk: str, session_token: Optional[str],
                 timeout: float) -> None:
        import volcenginesdkcore  # type: ignore  # imported lazily; optional dependency

        cfg = volcenginesdkcore.Configuration()
        cfg.ak = ak
        cfg.sk = sk
        cfg.region = MGMT_REGION
        cfg.host = MGMT_HOST
        if session_token:
            cfg.session_token = session_token
        self._core = volcenginesdkcore
        self._api = volcenginesdkcore.UniversalApi(volcenginesdkcore.ApiClient(cfg))
        self._timeout = timeout

    def call(self, action: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        info = self._core.UniversalInfo(
            method="POST",
            service=MGMT_SERVICE,
            version=MGMT_VERSION,
            action=action,
            content_type="application/json",
        )
        try:
            data = self._api.do_call(info, dict(body), _request_timeout=self._timeout)
        except self._core.rest.ApiException as exc:  # HTTP 4xx/5xx
            raise _from_sdk_exception(exc, action) from exc
        return _unwrap_result(data, action)


def _from_sdk_exception(exc: Any, action: str) -> ArkMgmtError:
    status = getattr(exc, "status", None)
    body = getattr(exc, "body", None)
    code = request_id = None
    message = f"{action} HTTP error"
    if body:
        try:
            if isinstance(body, bytes):
                body = body.decode("utf-8", "replace")
            parsed = json.loads(body)
            meta = parsed.get("ResponseMetadata", {}) if isinstance(parsed, dict) else {}
            err = meta.get("Error") or {}
            code = err.get("Code")
            request_id = meta.get("RequestId")
            if err.get("Message"):
                message = f"{action} failed: {err['Message']}"
        except (ValueError, AttributeError):
            message = f"{action} HTTP error: {str(body)[:300]}"
    return ArkMgmtError(message, code=code, http_status=status, request_id=request_id)


# --- Transport 2: standard library only -------------------------------------------
class StdlibSigner:
    """Volcengine HMAC-SHA256 request signing (the algorithm documented at
    https://www.volcengine.com/docs/6369/67269), implemented with the standard library.

    Kept deliberately small: POST with a JSON body to ``https://<host>/?Action=..&Version=..``.
    """

    ALGORITHM = "HMAC-SHA256"
    SIGNED_HEADERS = ("content-type", "host", "x-content-sha256", "x-date")

    def __init__(self, ak: str, sk: str, *, region: str = MGMT_REGION,
                 service: str = MGMT_SERVICE, host: str = MGMT_HOST,
                 session_token: Optional[str] = None) -> None:
        self.ak = ak
        self.sk = sk
        self.region = region
        self.service = service
        self.host = host
        self.session_token = session_token

    @staticmethod
    def _sha256_hex(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    @staticmethod
    def canonical_query(params: Mapping[str, str]) -> str:
        return "&".join(
            f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(str(v), safe='-_.~')}"
            for k, v in sorted(params.items())
        )

    def sign(self, method: str, query: Mapping[str, str], body: bytes,
             now: Optional[_dt.datetime] = None) -> Dict[str, str]:
        """Return the full header set (including Authorization) for one request."""
        now = now or _dt.datetime.now(_dt.timezone.utc)
        x_date = now.strftime("%Y%m%dT%H%M%SZ")
        short_date = x_date[:8]
        content_type = "application/json"
        payload_hash = self._sha256_hex(body)

        header_values = {
            "content-type": content_type,
            "host": self.host,
            "x-content-sha256": payload_hash,
            "x-date": x_date,
        }
        canonical_headers = "".join(f"{h}:{header_values[h]}\n" for h in self.SIGNED_HEADERS)
        signed_headers = ";".join(self.SIGNED_HEADERS)
        canonical_request = "\n".join([
            method.upper(),
            "/",
            self.canonical_query(query),
            canonical_headers,
            signed_headers,
            payload_hash,
        ])
        credential_scope = f"{short_date}/{self.region}/{self.service}/request"
        string_to_sign = "\n".join([
            self.ALGORITHM,
            x_date,
            credential_scope,
            self._sha256_hex(canonical_request.encode("utf-8")),
        ])
        k_date = self._hmac(self.sk.encode("utf-8"), short_date)
        k_region = self._hmac(k_date, self.region)
        k_service = self._hmac(k_region, self.service)
        k_signing = self._hmac(k_service, "request")
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        headers = {
            "Content-Type": content_type,
            "Host": self.host,
            "X-Date": x_date,
            "X-Content-Sha256": payload_hash,
            "Authorization": (
                f"{self.ALGORITHM} Credential={self.ak}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }
        if self.session_token:
            headers["X-Security-Token"] = self.session_token
        return headers


class _StdlibTransport:
    def __init__(self, ak: str, sk: str, session_token: Optional[str], timeout: float) -> None:
        self._signer = StdlibSigner(ak, sk, session_token=session_token)
        self._timeout = timeout

    def call(self, action: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        query = {"Action": action, "Version": MGMT_VERSION}
        payload = json.dumps(dict(body), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = self._signer.sign("POST", query, payload)
        url = f"https://{MGMT_HOST}/?{StdlibSigner.canonical_query(query)}"
        req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
            parsed = _safe_json(raw)
            try:
                _unwrap_result(parsed, action)  # raises with Code/Message when present
            except ArkMgmtError as api_err:
                api_err.http_status = status
                raise api_err from exc
            raise ArkMgmtError(f"{action} HTTP {status}: {raw[:300]!r}", http_status=status) from exc
        except urllib.error.URLError as exc:
            raise ArkMgmtError(f"{action}: network error: {exc.reason}") from exc
        parsed = _safe_json(raw)
        if parsed is None:
            raise ArkMgmtError(f"{action} HTTP {status}: non-JSON body {raw[:300]!r}",
                               http_status=status)
        return _unwrap_result(parsed, action)


def _safe_json(raw: bytes) -> Optional[Any]:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


# --- Client ----------------------------------------------------------------------
class ArkManagementClient:
    """Thin client for Ark management-plane Actions (AK/SK signed)."""

    def __init__(self, ak: Optional[str] = None, sk: Optional[str] = None,
                 session_token: Optional[str] = None, *, transport: str = "auto",
                 timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        ak = ak or os.environ.get(ENV_AK)
        sk = sk or os.environ.get(ENV_SK)
        session_token = session_token or os.environ.get(ENV_SESSION_TOKEN) or None
        if not ak or not sk:
            raise ArkMgmtError(
                f"Missing credentials: set {ENV_AK} and {ENV_SK} "
                "(Volcengine Access Key / Secret Key from https://console.volcengine.com/iam/keymanage; "
                "the Agent Plan API Key does NOT work for the management plane)."
            )
        self.transport_name, self._transport = self._pick_transport(
            transport, ak, sk, session_token, timeout)

    @staticmethod
    def _pick_transport(transport: str, ak: str, sk: str, session_token: Optional[str],
                        timeout: float):
        if transport not in ("auto", "sdk", "stdlib"):
            raise ValueError(f"unknown transport {transport!r}")
        if transport in ("auto", "sdk"):
            try:
                return "sdk", _SdkTransport(ak, sk, session_token, timeout)
            except ImportError:
                if transport == "sdk":
                    raise ArkMgmtError(
                        "volcengine-python-sdk is not installed; "
                        "pip install volcengine-python-sdk  or use --transport stdlib")
                LOG.debug("volcengine-python-sdk not installed, using stdlib signer")
        return "stdlib", _StdlibTransport(ak, sk, session_token, timeout)

    def call(self, action: str, body: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        LOG.debug("management-plane call %s via %s", action, self.transport_name)
        return self._transport.call(action, body or {})

    def get_afp_usage(self) -> AfpUsage:
        return AfpUsage.from_result(self.call(ACTION_GET_AFP_USAGE, {}))

    def get_personal_plan(self, plan: str = "AgentPlan") -> Dict[str, Any]:
        return self.call(ACTION_GET_PERSONAL_PLAN, {"Plan": plan})


def get_afp_usage(client: Optional[ArkManagementClient] = None) -> AfpUsage:
    return (client or ArkManagementClient()).get_afp_usage()


def get_personal_plan(client: Optional[ArkManagementClient] = None,
                      plan: str = "AgentPlan") -> Dict[str, Any]:
    return (client or ArkManagementClient()).get_personal_plan(plan)


# --- CLI -------------------------------------------------------------------------
def _fmt_amount(value: Decimal) -> str:
    return f"{value:,.0f}" if value == value.to_integral_value() else f"{value:,.2f}"


def _display_width(text: str) -> int:
    """Terminal cell width (CJK characters occupy two cells)."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(width - _display_width(text), 0)


def render_text(usage: AfpUsage, plan: Optional[Mapping[str, Any]],
                threshold_percent: float, low: List[AfpWindow]) -> str:
    lines: List[str] = []
    title = f"火山方舟 Agent Plan 个人版 AFP 额度（套餐档位: {usage.plan_type or '未知'}）"
    lines.append(title)
    if plan:
        end_time = plan.get("EndTime") or "?"
        lines.append(
            f"套餐状态: {plan.get('Status', '?')}  到期: {end_time}  "
            f"自动续费: {'开' if plan.get('AutoRenew') else '关'}"
        )
    lines.append("")
    label_width = max(28, max(_display_width(w.label) for w in usage.windows) + 2)
    header = (f"{_pad('窗口', label_width)}{'剩余 AFP':>14}{'总额度':>14}"
              f"{'剩余%':>9}  下次重置")
    lines.append(header)
    lines.append("-" * _display_width(header))
    for w in usage.windows:
        pct = w.remaining_percent
        pct_s = "n/a" if pct is None else f"{pct:.1f}%"
        reset = w.reset_time.strftime("%Y-%m-%d %H:%M") if w.reset_time else "-"
        flag = "  <-- 告警" if w in low else ""
        lines.append(
            f"{_pad(w.label, label_width)}{_fmt_amount(w.remaining):>14}{_fmt_amount(w.quota):>14}"
            f"{pct_s:>9}  {reset}{flag}"
        )
    lines.append("")
    if low:
        for w in low:
            pct = w.remaining_percent or Decimal(0)
            reset = w.reset_time.strftime("%Y-%m-%d %H:%M") if w.reset_time else "未知"
            lines.append(
                f"[ALERT] {w.label} 额度剩余 {pct:.1f}% "
                f"({_fmt_amount(w.remaining)} / {_fmt_amount(w.quota)} AFP)，"
                f"低于 {threshold_percent:g}% 阈值；重置时间 {reset}"
            )
    else:
        lines.append(f"OK: 所有窗口剩余额度均高于 {threshold_percent:g}%")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ark_afp_quota",
        description="查询火山方舟 Agent Plan 个人版剩余 AFP（5 小时 / 周 / 月），低于阈值时告警。",
    )
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_PERCENT,
                   help="剩余百分比阈值，低于(含)则告警，默认 10")
    p.add_argument("--all-windows", action="store_true",
                   help="日额度窗口也参与告警判断（默认只看 5 小时 / 周 / 月）")
    p.add_argument("--plan", action="store_true",
                   help="额外调用 GetPersonalPlan 显示套餐状态与到期时间")
    p.add_argument("--json", action="store_true", help="以 JSON 输出（便于接监控）")
    p.add_argument("--transport", choices=("auto", "sdk", "stdlib"), default="auto",
                   help="auto: 有官方 SDK 就用，否则用内置签名实现")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                   help="单次请求超时秒数")
    p.add_argument("-v", "--verbose", action="store_true", help="调试日志")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    if not 0 <= args.threshold <= 100:
        print("--threshold must be within 0..100", file=sys.stderr)
        return 1

    try:
        client = ArkManagementClient(transport=args.transport, timeout=args.timeout)
        usage = client.get_afp_usage()
        plan_info: Optional[Dict[str, Any]] = None
        if args.plan:
            try:
                plan_info = client.get_personal_plan("AgentPlan")
            except ArkMgmtError as exc:
                LOG.warning("GetPersonalPlan failed, continuing without plan info: %s", exc)
    except ArkMgmtError as exc:
        hint = ""
        if exc.code and "ResourceNotFound" in exc.code:
            hint = " (当前账号没有生效中的 Agent Plan 个人版套餐)"
        elif exc.http_status in (401, 403) or (exc.code and "Signature" in exc.code):
            hint = " (检查 AK/SK 是否正确、是否授予了方舟权限；这里不能用 Agent Plan API Key)"
        print(f"ERROR: {exc}{hint}", file=sys.stderr)
        return 1

    keys = None if args.all_windows else list(PRIMARY_WINDOWS)
    low = find_low_windows(usage, args.threshold, keys)

    if args.json:
        out = {
            "plan_type": usage.plan_type,
            "plan": plan_info,
            "threshold_percent": args.threshold,
            "transport": client.transport_name,
            "windows": [w.to_dict() for w in usage.windows],
            "alerts": [w.key for w in low],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(render_text(usage, plan_info, args.threshold, low))

    for w in low:
        pct = w.remaining_percent or Decimal(0)
        print(f"[ALERT] {w.label}: 剩余 {pct:.1f}% <= {args.threshold:g}%", file=sys.stderr)
    return 2 if low else 0


if __name__ == "__main__":
    sys.exit(main())
