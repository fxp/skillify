"""Volcengine (火山引擎) Open API HMAC-SHA256 "V4"-style request signer.

Pure standard library. Implements the signing scheme used by
``open.volcengineapi.com`` (the management plane shared by Ark and every other
Volcengine product):

    CanonicalRequest =
        HTTPMethod \n CanonicalURI \n CanonicalQueryString \n
        CanonicalHeaders \n SignedHeaders \n HexEncode(SHA256(Payload))
    CredentialScope  = {YYYYMMDD}/{region}/{service}/request
    StringToSign     = HMAC-SHA256 \n {X-Date} \n {CredentialScope} \n
                       HexEncode(SHA256(CanonicalRequest))
    kDate    = HMAC(SecretKey, YYYYMMDD)
    kRegion  = HMAC(kDate, region)
    kService = HMAC(kRegion, service)
    kSigning = HMAC(kService, "request")
    Signature = HexEncode(HMAC(kSigning, StringToSign))

    Authorization: HMAC-SHA256 Credential={AK}/{scope},
                   SignedHeaders={h1;h2;...}, Signature={sig}
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple
from urllib.parse import quote

__all__ = ["Credentials", "SignedRequest", "sign_request"]

_ALGORITHM = "HMAC-SHA256"
_TERMINATOR = "request"


@dataclass(frozen=True)
class Credentials:
    access_key: str
    secret_key: str
    session_token: Optional[str] = None  # STS temporary credentials

    def __post_init__(self) -> None:
        if not self.access_key or not self.secret_key:
            raise ValueError("access_key and secret_key must be non-empty")


@dataclass
class SignedRequest:
    method: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""


def _uri_encode(value: str, *, encode_slash: bool = True) -> str:
    safe = "-_.~" if encode_slash else "-_.~/"
    return quote(value, safe=safe)


def _canonical_query(params: Mapping[str, str]) -> str:
    pairs = sorted(
        (_uri_encode(str(k)), _uri_encode(str(v))) for k, v in params.items()
    )
    return "&".join(f"{k}={v}" for k, v in pairs)


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sign_request(
    *,
    credentials: Credentials,
    method: str,
    host: str,
    path: str,
    query: Mapping[str, str],
    body: bytes,
    region: str,
    service: str,
    content_type: str = "application/json; charset=utf-8",
    extra_headers: Optional[Mapping[str, str]] = None,
    now: Optional[_dt.datetime] = None,
    scheme: str = "https",
) -> SignedRequest:
    """Build a fully signed request for the Volcengine Open API.

    ``now`` is injectable for deterministic unit tests; defaults to UTC now.
    """
    method = method.upper()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = x_date[:8]

    payload_hash = _sha256_hex(body)

    headers: Dict[str, str] = {
        "Host": host,
        "Content-Type": content_type,
        "X-Date": x_date,
        "X-Content-Sha256": payload_hash,
    }
    if credentials.session_token:
        headers["X-Security-Token"] = credentials.session_token
    if extra_headers:
        headers.update(extra_headers)

    # Canonical headers: lower-cased names, trimmed values, sorted by name.
    canon_pairs: Tuple[Tuple[str, str], ...] = tuple(
        sorted((k.lower(), " ".join(v.strip().split())) for k, v in headers.items())
    )
    signed_headers = ";".join(k for k, _ in canon_pairs)
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in canon_pairs)

    canonical_query = _canonical_query(query)
    canonical_uri = _uri_encode(path or "/", encode_slash=False)

    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    scope = f"{short_date}/{region}/{service}/{_TERMINATOR}"
    string_to_sign = "\n".join(
        [_ALGORITHM, x_date, scope, _sha256_hex(canonical_request.encode("utf-8"))]
    )

    k_date = _hmac_sha256(credentials.secret_key.encode("utf-8"), short_date)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    k_signing = _hmac_sha256(k_service, _TERMINATOR)
    signature = hmac.new(
        k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    headers["Authorization"] = (
        f"{_ALGORITHM} Credential={credentials.access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"{scheme}://{host}{canonical_uri}"
    if canonical_query:
        url = f"{url}?{canonical_query}"
    return SignedRequest(method=method, url=url, headers=headers, body=body)
