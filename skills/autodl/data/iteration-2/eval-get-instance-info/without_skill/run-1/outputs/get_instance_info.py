#!/usr/bin/env python3
"""
get_instance_info.py

Query the details of an AutoDL (autodl.com) container instance -- with
special emphasis on how to SSH into it -- by calling AutoDL's Open API
directly over HTTP with the `requests` library (no AutoDL SDK).

WHY THIS SHAPE
---------------
AutoDL's public "Open API" (control-panel -> "开发者/开放平台" -> API 文档,
published at https://www.autodl.com/docs/api_v1/) is *not* a classic REST
API. Every documented endpoint is called with HTTP POST and takes its
parameters as a JSON object in the request body (Content-Type:
application/json) -- including the instance UUID -- rather than as query
string parameters. Authentication is done with a per-user "Token" (created
in the console under "开发者令牌" / API Key) sent in an `Authorization`
request header, not as a query param either.

So this script:
  - Sends the instance_uuid in the JSON request body (POST), not in the
    URL query string. This matches AutoDL's documented calling convention,
    avoids leaking an account-identifying UUID into server/proxy access
    logs and shell history the way a query string would, and lets us grow
    the payload (e.g. extra filters) without touching the URL.
  - Sends the API token via the `Authorization` header, never via query
    string, so it cannot leak through URL logging either.

NOTE / DISCLAIMER
------------------
This script is written from general knowledge of AutoDL's Open API shape
and was *not* validated against a live account or the current docs page
(no network calls were made while writing it). The endpoint path and the
exact field names in the JSON response are a best-effort reconstruction.
Before relying on this in production:
  1. Double-check the endpoint path and payload shape against the current
     docs at https://www.autodl.com/docs/api_v1/ (log into the AutoDL
     console to view it).
  2. Adjust `INSTANCE_DETAIL_PATH` / the request body / the response
     field names below if they differ.

The script is defensive about the response shape: it prints whatever
fields it finds, and falls back to dumping the raw JSON if the fields it
expects for SSH info aren't present, so it stays useful even if the exact
schema differs slightly from what's assumed here.

CONFIGURATION (environment variables)
--------------------------------------
AUTODL_TOKEN          (required) Your AutoDL API token, created in the
                       console under "开发者令牌" / "API Key".
AUTODL_INSTANCE_UUID  (required) The instance's UUID (as shown in the
                       console instance list / URL), e.g. "container-xxxx".
AUTODL_API_BASE        (optional) Override the API base URL.
                       Default: https://api.autodl.com

Usage:
    export AUTODL_TOKEN="your-token-here"
    export AUTODL_INSTANCE_UUID="your-instance-uuid-here"
    python3 get_instance_info.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("AUTODL_API_BASE", "https://api.autodl.com").rstrip("/")

# Best-effort guess at the documented "get instance detail" endpoint.
# AutoDL's Open API groups everything under /api/v1/... and uses POST with
# a JSON body for essentially every call (including "list"/"detail"
# style reads), so this follows that convention.
INSTANCE_DETAIL_PATH = "/api/v1/instance"

REQUEST_TIMEOUT_SECONDS = 15


def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: required environment variable {name} is not set.", file=sys.stderr)
        sys.exit(1)
    return value


def fetch_instance_info(token: str, instance_uuid: str) -> dict[str, Any]:
    """
    Call AutoDL's Open API to fetch details for a single container
    instance.

    Sends the instance_uuid in the JSON request body (POST), matching
    AutoDL's documented API convention -- see the module docstring for the
    reasoning.
    """
    url = f"{API_BASE}{INSTANCE_DETAIL_PATH}"

    headers = {
        # AutoDL's Open API authenticates via a bearer-style token in the
        # Authorization header. Some AutoDL docs show the raw token with
        # no "Bearer " prefix -- if your account's token is rejected with
        # an auth error, try switching between "Bearer <token>" and the
        # raw "<token>" here.
        "Authorization": token,
        "Content-Type": "application/json",
    }

    # instance_uuid travels in the JSON body, not as a query parameter.
    payload = {"instance_uuid": instance_uuid}

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def extract_ssh_info(data: dict[str, Any]) -> dict[str, Any]:
    """
    Best-effort extraction of SSH connection details from the instance
    detail payload. AutoDL's console shows a ready-made "SSH指令"
    (ssh command) plus a root password for each running instance, so the
    API response is assumed to carry equivalent fields. Field names are
    checked defensively since the exact schema wasn't verified live.
    """
    ssh_info: dict[str, Any] = {}

    # A single ready-to-use ssh command, e.g.:
    #   "ssh -p 20000 root@region-1.autodl.com"
    for key in ("ssh_command", "sshCommand", "ssh_cmd"):
        if key in data:
            ssh_info["ssh_command"] = data[key]
            break

    # Discrete host/port/user fields, in case the API exposes them
    # separately instead of (or in addition to) a combined command.
    host = data.get("ssh_host") or data.get("proxy_host") or data.get("host")
    port = data.get("ssh_port") or data.get("proxy_port") or data.get("port")
    user = data.get("ssh_user") or data.get("username") or "root"

    if host and port:
        ssh_info.setdefault("ssh_command", f"ssh -p {port} {user}@{host}")
        ssh_info["host"] = host
        ssh_info["port"] = port
        ssh_info["user"] = user

    for key in ("root_password", "password", "rootPassword"):
        if key in data:
            ssh_info["password"] = data[key]
            break

    return ssh_info


def print_instance_info(payload: dict[str, Any]) -> None:
    """Pretty-print the instance details, highlighting SSH connection info."""

    # AutoDL API responses are commonly wrapped as
    # {"code": "Success", "msg": "", "data": {...}}. Unwrap that if present,
    # otherwise assume the payload itself is the instance data.
    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], dict):
        code = payload.get("code")
        msg = payload.get("msg")
        if code not in (None, "Success", "success", 0, "0"):
            print(f"API returned an error: code={code!r} msg={msg!r}", file=sys.stderr)
            print("Raw response:", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
            sys.exit(1)
        data = payload["data"]
    else:
        data = payload

    print("=" * 60)
    print("AutoDL Instance Info")
    print("=" * 60)

    field_labels = [
        ("instance_uuid", "Instance UUID"),
        ("uuid", "Instance UUID"),
        ("status", "Status"),
        ("gpu_name", "GPU"),
        ("machine_id", "Machine ID"),
        ("region_sign", "Region"),
        ("region", "Region"),
        ("image_name", "Image"),
        ("cpu_num", "CPU cores"),
        ("memory_size", "Memory (GB)"),
        ("gpu_idle_mem", "GPU idle memory"),
        ("created_time", "Created at"),
        ("expenditure_time", "Expires at"),
    ]
    printed_keys = set()
    for key, label in field_labels:
        if key in data and key not in printed_keys:
            print(f"{label:20s}: {data[key]}")
            printed_keys.add(key)

    print("-" * 60)
    print("SSH connection")
    print("-" * 60)
    ssh_info = extract_ssh_info(data)
    if ssh_info:
        if "ssh_command" in ssh_info:
            print(f"{'SSH command':20s}: {ssh_info['ssh_command']}")
        if "host" in ssh_info:
            print(f"{'Host':20s}: {ssh_info['host']}")
        if "port" in ssh_info:
            print(f"{'Port':20s}: {ssh_info['port']}")
        if "user" in ssh_info:
            print(f"{'User':20s}: {ssh_info['user']}")
        if "password" in ssh_info:
            print(f"{'Password':20s}: {ssh_info['password']}")
    else:
        print("Could not find recognizable SSH fields in the response.")
        print("Dumping the full instance payload instead:")
        print(json.dumps(data, ensure_ascii=False, indent=2))

    print("=" * 60)
    print("Full raw response (for reference):")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    token = get_required_env("AUTODL_TOKEN")
    instance_uuid = get_required_env("AUTODL_INSTANCE_UUID")

    try:
        payload = fetch_instance_info(token, instance_uuid)
    except requests.exceptions.RequestException as exc:
        print(f"ERROR: request to AutoDL API failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print_instance_info(payload)


if __name__ == "__main__":
    main()
