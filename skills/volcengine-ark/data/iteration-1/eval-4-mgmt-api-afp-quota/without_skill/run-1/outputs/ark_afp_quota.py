#!/usr/bin/env python3
"""ark_afp_quota - 查询火山方舟 Agent Plan（个人版）套餐剩余 AFP 并在低于阈值时告警。

用法:
    export VOLC_ACCESSKEY=...   # 火山引擎 IAM Access Key
    export VOLC_SECRETKEY=...   # 火山引擎 IAM Secret Key
    python ark_afp_quota.py                 # 表格输出，剩余 < 10% 打印 ALERT
    python ark_afp_quota.py --threshold 20  # 自定义阈值（百分比）
    python ark_afp_quota.py --json          # 机器可读输出
    python ark_afp_quota.py --dump-raw      # 打印原始响应，用于核对字段映射
    python ark_afp_quota.py --mock-file sample_response.json   # 离线解析测试

退出码:
    0  所有窗口剩余 >= 阈值
    1  至少一个窗口剩余 < 阈值（便于 cron / CI 触发告警）
    2  配置或请求错误

仅依赖标准库。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from volc_signer import Credentials, sign_request

LOG = logging.getLogger("ark_afp_quota")

# ---------------------------------------------------------------------------
# Configuration (all overridable through environment variables)
# ---------------------------------------------------------------------------

DEFAULT_HOST = os.environ.get("VOLC_OPENAPI_HOST", "open.volcengineapi.com")
DEFAULT_REGION = os.environ.get("VOLC_REGION", "cn-beijing")
DEFAULT_SERVICE = os.environ.get("ARK_OPENAPI_SERVICE", "ark")
DEFAULT_VERSION = os.environ.get("ARK_OPENAPI_VERSION", "2024-01-01")
# NOTE: the Action name for Agent Plan quota is *not* verified against the
# official docs (see NOTES.md). Override with ARK_QUOTA_ACTION if it differs.
DEFAULT_ACTION = os.environ.get("ARK_QUOTA_ACTION", "GetAgentPlanQuota")
DEFAULT_PLAN_TYPE = os.environ.get("ARK_PLAN_TYPE", "Personal")
DEFAULT_THRESHOLD_PCT = float(os.environ.get("ARK_ALERT_THRESHOLD_PCT", "10"))
DEFAULT_TIMEOUT_S = float(os.environ.get("ARK_HTTP_TIMEOUT", "15"))
MAX_RETRIES = int(os.environ.get("ARK_HTTP_MAX_RETRIES", "3"))

WINDOW_ORDER: Sequence[str] = ("5h", "week", "month")
WINDOW_LABELS: Mapping[str, str] = {"5h": "5 小时", "week": "本周", "month": "本月"}

# Candidate spellings the API might use for each rolling window. Matched
# case-insensitively after stripping "_", "-" and spaces.
_WINDOW_ALIASES: Mapping[str, Sequence[str]] = {
    "5h": ("5h", "5hour", "5hours", "fivehour", "fivehours", "hour5", "rolling5h", "session"),
    "week": ("week", "weekly", "7d", "7day", "7days"),
    "month": ("month", "monthly", "30d", "30day", "30days", "billingcycle"),
}
# Candidate field names for numbers inside a window object.
_TOTAL_KEYS = ("Total", "Limit", "Quota", "TotalAfp", "TotalAFP", "Capacity", "Max")
_USED_KEYS = ("Used", "Usage", "Consumed", "UsedAfp", "UsedAFP")
_REMAIN_KEYS = ("Remaining", "Remain", "Left", "Available", "Balance", "RemainingAfp", "RemainingAFP")
_RESET_KEYS = ("ResetTime", "ResetAt", "RefreshTime", "NextResetTime", "ExpireTime", "WindowEnd")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class WindowQuota:
    window: str  # "5h" | "week" | "month"
    total: float
    remaining: float
    used: Optional[float] = None
    reset_time: Optional[str] = None

    @property
    def remaining_pct(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(100.0, self.remaining / self.total * 100.0))

    def below(self, threshold_pct: float) -> bool:
        return self.remaining_pct < threshold_pct


class QuotaError(RuntimeError):
    """Raised for configuration, transport, or API-level errors."""


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class ArkOpenApiClient:
    def __init__(
        self,
        credentials: Credentials,
        *,
        host: str = DEFAULT_HOST,
        region: str = DEFAULT_REGION,
        service: str = DEFAULT_SERVICE,
        version: str = DEFAULT_VERSION,
        timeout: float = DEFAULT_TIMEOUT_S,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._creds = credentials
        self._host = host
        self._region = region
        self._service = service
        self._version = version
        self._timeout = timeout
        self._max_retries = max(0, max_retries)

    def call(self, action: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        """POST a JSON-body Open API action and return the decoded response."""
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        attempt = 0
        while True:
            attempt += 1
            signed = sign_request(
                credentials=self._creds,
                method="POST",
                host=self._host,
                path="/",
                query={"Action": action, "Version": self._version},
                body=payload,
                region=self._region,
                service=self._service,
                extra_headers={"Accept": "application/json"},
            )
            req = urllib.request.Request(
                signed.url, data=signed.body, headers=signed.headers, method=signed.method
            )
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    raw = resp.read()
                    status = resp.status
            except urllib.error.HTTPError as e:
                raw = e.read()
                status = e.code
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt <= self._max_retries:
                    self._sleep_backoff(attempt, f"network error: {e}")
                    continue
                raise QuotaError(f"network error calling {action}: {e}") from e

            data = self._decode(raw, status)
            err = (data.get("ResponseMetadata") or {}).get("Error")
            if status >= 400 or err:
                code = (err or {}).get("Code", f"HTTP{status}")
                msg = (err or {}).get("Message", raw[:300].decode("utf-8", "replace"))
                if (status == 429 or status >= 500) and attempt <= self._max_retries:
                    self._sleep_backoff(attempt, f"{code}: {msg}")
                    continue
                rid = (data.get("ResponseMetadata") or {}).get("RequestId", "-")
                raise QuotaError(f"{action} failed [{code}] {msg} (RequestId={rid})")
            return data

    @staticmethod
    def _decode(raw: bytes, status: int) -> Dict[str, Any]:
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError as e:
            raise QuotaError(f"non-JSON response (HTTP {status}): {raw[:300]!r}") from e
        if not isinstance(data, dict):
            raise QuotaError(f"unexpected response shape (HTTP {status}): {type(data).__name__}")
        return data

    @staticmethod
    def _sleep_backoff(attempt: int, reason: str) -> None:
        delay = min(8.0, 0.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.25)
        LOG.warning("attempt %d failed (%s); retrying in %.1fs", attempt, reason, delay)
        time.sleep(delay)


# ---------------------------------------------------------------------------
# Response normalisation
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch not in "_- ")


def _match_window(name: str) -> Optional[str]:
    n = _norm(name)
    for canonical, aliases in _WINDOW_ALIASES.items():
        if n in aliases or any(a in n for a in aliases if len(a) >= 4):
            return canonical
    return None


def _pick(d: Mapping[str, Any], keys: Iterable[str]) -> Optional[Any]:
    lowered = {_norm(k): v for k, v in d.items()}
    for k in keys:
        if _norm(k) in lowered:
            return lowered[_norm(k)]
    return None


def _to_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _window_from_obj(window: str, obj: Mapping[str, Any]) -> Optional[WindowQuota]:
    total = _to_float(_pick(obj, _TOTAL_KEYS))
    used = _to_float(_pick(obj, _USED_KEYS))
    remaining = _to_float(_pick(obj, _REMAIN_KEYS))
    if total is None and used is not None and remaining is not None:
        total = used + remaining
    if remaining is None and total is not None and used is not None:
        remaining = total - used
    if total is None or remaining is None:
        return None
    if used is None:
        used = total - remaining
    reset = _pick(obj, _RESET_KEYS)
    return WindowQuota(
        window=window,
        total=total,
        remaining=remaining,
        used=used,
        reset_time=str(reset) if reset is not None else None,
    )


def _iter_candidate_containers(result: Any) -> Iterable[Any]:
    """Yield ``result`` and nested dict/list values that could hold the quotas."""
    yield result
    if isinstance(result, dict):
        for v in result.values():
            if isinstance(v, (dict, list)):
                yield from _iter_candidate_containers(v)
    elif isinstance(result, list):
        for v in result:
            if isinstance(v, (dict, list)):
                yield from _iter_candidate_containers(v)


def parse_quotas(response: Mapping[str, Any]) -> List[WindowQuota]:
    """Extract the 5h / week / month AFP quotas from an Open API response.

    Tolerates the two shapes Volcengine Open APIs commonly use:

    1. Mapping keyed by window::
           {"Result": {"Quotas": {"FiveHour": {"Total": ..., "Remaining": ...}, ...}}}
    2. List of window objects::
           {"Result": {"Quotas": [{"Window": "Week", "Limit": ..., "Used": ...}, ...]}}
    """
    result = response.get("Result", response)
    found: Dict[str, WindowQuota] = {}

    for container in _iter_candidate_containers(result):
        if isinstance(container, dict):
            for key, val in container.items():
                if not isinstance(val, dict):
                    continue
                w = _match_window(str(key))
                if w and w not in found:
                    q = _window_from_obj(w, val)
                    if q:
                        found[w] = q
        elif isinstance(container, list):
            for item in container:
                if not isinstance(item, dict):
                    continue
                label = _pick(item, ("Window", "Period", "Cycle", "Type", "Name", "Granularity"))
                if label is None:
                    continue
                w = _match_window(str(label))
                if w and w not in found:
                    q = _window_from_obj(w, item)
                    if q:
                        found[w] = q
        if len(found) == len(WINDOW_ORDER):
            break

    if not found:
        raise QuotaError(
            "could not locate any 5h/week/month quota in the response; "
            "run with --dump-raw and adjust the field aliases in ark_afp_quota.py"
        )
    return [found[w] for w in WINDOW_ORDER if w in found]


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------


def _fmt_num(v: Optional[float]) -> str:
    if v is None:
        return "-"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def render_table(quotas: Sequence[WindowQuota], threshold: float) -> str:
    rows = [("窗口", "总额 AFP", "已用 AFP", "剩余 AFP", "剩余 %", "重置时间", "状态")]
    for q in quotas:
        status = "ALERT" if q.below(threshold) else "OK"
        rows.append(
            (
                WINDOW_LABELS.get(q.window, q.window),
                _fmt_num(q.total),
                _fmt_num(q.used),
                _fmt_num(q.remaining),
                f"{q.remaining_pct:5.1f}%",
                q.reset_time or "-",
                status,
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(r)) for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def alerts_for(quotas: Sequence[WindowQuota], threshold: float) -> List[str]:
    out = []
    for q in quotas:
        if q.below(threshold):
            out.append(
                f"[ALERT] Agent Plan {WINDOW_LABELS.get(q.window, q.window)} 窗口剩余 "
                f"{_fmt_num(q.remaining)} / {_fmt_num(q.total)} AFP "
                f"({q.remaining_pct:.1f}%) 低于 {threshold:g}% 阈值"
                + (f"，重置时间 {q.reset_time}" if q.reset_time else "")
            )
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_credentials() -> Credentials:
    ak = os.environ.get("VOLC_ACCESSKEY") or os.environ.get("VOLC_ACCESS_KEY")
    sk = os.environ.get("VOLC_SECRETKEY") or os.environ.get("VOLC_SECRET_KEY")
    token = os.environ.get("VOLC_SESSION_TOKEN")
    if not ak or not sk:
        raise QuotaError("missing credentials: set VOLC_ACCESSKEY and VOLC_SECRETKEY")
    return Credentials(access_key=ak, secret_key=sk, session_token=token)


def fetch_quota_response(args: argparse.Namespace) -> Dict[str, Any]:
    if args.mock_file:
        with open(args.mock_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    client = ArkOpenApiClient(
        load_credentials(),
        host=args.host,
        region=args.region,
        version=args.version,
        timeout=args.timeout,
    )
    body: Dict[str, Any] = {"PlanType": args.plan_type}
    return client.call(args.action, body)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ark_afp_quota",
        description="查询火山方舟 Agent Plan 个人版 5小时/周/月 剩余 AFP，低于阈值告警。",
    )
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_PCT,
                   help="告警阈值（剩余百分比），默认 %(default)s")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    p.add_argument("--dump-raw", action="store_true", help="同时打印 API 原始响应")
    p.add_argument("--mock-file", metavar="PATH", help="从本地 JSON 文件读取响应（不发起请求）")
    p.add_argument("--action", default=DEFAULT_ACTION, help="Open API Action，默认 %(default)s")
    p.add_argument("--plan-type", default=DEFAULT_PLAN_TYPE, help="套餐类型，默认 %(default)s")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--region", default=DEFAULT_REGION)
    p.add_argument("--version", default=DEFAULT_VERSION, help="Open API Version")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    if not (0 <= args.threshold <= 100):
        print("error: --threshold must be within 0..100", file=sys.stderr)
        return 2

    try:
        response = fetch_quota_response(args)
        quotas = parse_quotas(response)
    except QuotaError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    alerts = alerts_for(quotas, args.threshold)

    if args.dump_raw:
        print(json.dumps(response, ensure_ascii=False, indent=2), file=sys.stderr)

    if args.json:
        out = {
            "plan": "AgentPlan",
            "plan_type": args.plan_type,
            "threshold_pct": args.threshold,
            "windows": [
                {**asdict(q), "remaining_pct": round(q.remaining_pct, 2),
                 "alert": q.below(args.threshold)}
                for q in quotas
            ],
            "alerts": alerts,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(render_table(quotas, args.threshold))
        missing = [WINDOW_LABELS[w] for w in WINDOW_ORDER if w not in {q.window for q in quotas}]
        if missing:
            print(f"注意：响应中未找到以下窗口：{', '.join(missing)}", file=sys.stderr)
        for line in alerts:
            print(line)

    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
