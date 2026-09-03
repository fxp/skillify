#!/usr/bin/env python3
"""
cleanup.py — Automatically power off and release an AutoDL (AutoDL.com) container
instance once a training job finishes, so it stops burning money / holding
resources.

USAGE
-----
As a library, wrapped around your training run:

    from cleanup import cleanup_instance

    try:
        run_training()
    finally:
        cleanup_instance()

Or as a standalone script, chained after your training command in a shell script:

    python train.py && python cleanup.py
    # (use `;` instead of `&&` if you want cleanup to run even when training fails)

CONFIGURATION (environment variables)
--------------------------------------
AUTODL_TOKEN           (required) API token, generated from the AutoDL console
                        under "Account -> Settings -> API 密钥 / Access Token".
                        NEVER hard-code the real token in this file — always
                        read it from the environment / a secrets manager.
AUTODL_INSTANCE_UUID    (required) The instance's uuid. AutoDL also exposes this
                        inside a running container via the env var
                        $AutoDL_ContainerUuid — this script falls back to that
                        name automatically if AUTODL_INSTANCE_UUID isn't set.
AUTODL_API_BASE         (optional) Override the API base URL, default
                        "https://api.autodl.com".
AUTODL_DRY_RUN          (optional) Set to "1"/"true" to log what would happen
                        without making any real HTTP calls. Useful for testing
                        this script safely.

IMPORTANT — VERIFY BEFORE RELYING ON THIS IN PRODUCTION
---------------------------------------------------------
The exact request/response shape of AutoDL's HTTP API (endpoint paths, field
names, status enum values) is filled in here from general knowledge of how
this class of "power off then release" GPU-rental API is typically shaped,
NOT from a verified, up-to-date copy of AutoDL's official API docs. Endpoints
are isolated in the `AutoDLClient` class below (`power_off`, `get_instance`,
`release`) — before trusting this in production, open the AutoDL console's
API documentation page and confirm/adjust:
  1. the base URL and endpoint paths,
  2. the auth header AutoDL expects (this script sends the raw token in an
     "Authorization" header, which is the common convention),
  3. the exact field names in the JSON payloads/responses (this script's
     `_extract_status` tries several common key names defensively), and
  4. the instance status string(s) that mean "fully powered off".
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("autodl-cleanup")


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DEFAULT_API_BASE = "https://api.autodl.com"

# Statuses (best-effort guess at AutoDL's enum) that indicate the instance is
# fully shut down and therefore safe to release.
SHUTDOWN_STATUSES = {"shutdown", "stopped", "poweroff", "power_off", "off"}

# Statuses that indicate the instance is still shutting down / busy and we
# should keep polling.
TRANSIENT_STATUSES = {"stopping", "shutting_down", "queue", "pending"}


@dataclass
class CleanupConfig:
    token: str
    instance_uuid: str
    api_base: str = DEFAULT_API_BASE
    dry_run: bool = False
    # How long to wait for the instance to actually reach a "shutdown" state
    # before we give up and abort the release (safety: never release blind).
    shutdown_poll_timeout_s: float = 180.0
    shutdown_poll_interval_s: float = 5.0
    # HTTP-level resilience
    http_timeout_s: float = 15.0
    max_retries: int = 3
    retry_backoff_base_s: float = 2.0

    @classmethod
    def from_env(cls) -> "CleanupConfig":
        token = os.environ.get("AUTODL_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "AUTODL_TOKEN is not set. Export it before running this script, "
                "e.g.:  export AUTODL_TOKEN='<your-autodl-api-token>'"
            )

        instance_uuid = (
            os.environ.get("AUTODL_INSTANCE_UUID", "").strip()
            # AutoDL containers expose this env var by default at runtime.
            or os.environ.get("AutoDL_ContainerUuid", "").strip()
        )
        if not instance_uuid:
            raise RuntimeError(
                "AUTODL_INSTANCE_UUID is not set (and $AutoDL_ContainerUuid was "
                "not found either). Set it to the instance's uuid, e.g.:\n"
                "  export AUTODL_INSTANCE_UUID='container-xxxxxxxx'"
            )

        api_base = os.environ.get("AUTODL_API_BASE", DEFAULT_API_BASE).rstrip("/")
        dry_run = os.environ.get("AUTODL_DRY_RUN", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        return cls(token=token, instance_uuid=instance_uuid, api_base=api_base, dry_run=dry_run)


class AutoDLAPIError(RuntimeError):
    """Raised when the AutoDL API returns an error or an unexpected response."""


# --------------------------------------------------------------------------
# Thin HTTP client for the AutoDL open API
# --------------------------------------------------------------------------

class AutoDLClient:
    def __init__(self, config: CleanupConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                # Common convention for this class of API: raw token in the
                # Authorization header. Adjust to "Bearer <token>" if AutoDL's
                # docs specify that scheme instead.
                "Authorization": config.token,
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str, json: Optional[dict] = None) -> dict:
        url = f"{self.config.api_base}{path}"

        if self.config.dry_run:
            log.info("[DRY RUN] %s %s payload=%s", method, url, json)
            return {"code": "Success", "msg": "dry-run", "data": {}}

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = self.session.request(
                    method, url, json=json, timeout=self.config.http_timeout_s
                )
                resp.raise_for_status()
                body = resp.json()

                # AutoDL-style APIs commonly wrap results as
                # {"code": "Success", "msg": "...", "data": {...}}.
                # Treat anything other than an explicit success code as an error
                # if a `code` field is present; otherwise just return the body.
                code = body.get("code")
                if code is not None and str(code).lower() not in ("success", "ok", "0"):
                    raise AutoDLAPIError(
                        f"AutoDL API returned an error for {method} {path}: {body}"
                    )
                return body

            except (requests.RequestException, AutoDLAPIError, ValueError) as exc:
                last_exc = exc
                if attempt == self.config.max_retries:
                    break
                sleep_s = self.config.retry_backoff_base_s * (2 ** (attempt - 1))
                log.warning(
                    "Request %s %s failed (attempt %d/%d): %s — retrying in %.1fs",
                    method,
                    path,
                    attempt,
                    self.config.max_retries,
                    exc,
                    sleep_s,
                )
                time.sleep(sleep_s)

        raise AutoDLAPIError(
            f"Request {method} {path} failed after {self.config.max_retries} attempts"
        ) from last_exc

    # -- Endpoints -----------------------------------------------------
    # NOTE: paths/payload field names are best-effort — verify against the
    # official AutoDL API docs before production use (see module docstring).

    def power_off(self, instance_uuid: str) -> dict:
        """Power off (关机) the instance. This is a graceful shutdown request;
        it does NOT delete the instance or its disk — data/env is preserved,
        but billing for GPU time stops (storage billing usually continues
        until `release` is called)."""
        log.info("Requesting power_off for instance %s", instance_uuid)
        return self._request(
            "POST", "/api/v1/instance/power_off", json={"instance_uuid": instance_uuid}
        )

    def get_instance(self, instance_uuid: str) -> dict:
        """Fetch current instance status."""
        return self._request(
            "POST", "/api/v1/instance", json={"instance_uuid": instance_uuid}
        )

    def release(self, instance_uuid: str) -> dict:
        """Release (释放) the instance: irreversibly destroys the container and
        its disk. Only call this once the instance is confirmed powered off."""
        log.info("Requesting release for instance %s", instance_uuid)
        return self._request(
            "POST", "/api/v1/instance/release", json={"instance_uuid": instance_uuid}
        )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _extract_status(instance_payload: dict) -> str:
    """Defensively pull a status string out of a `get_instance` response,
    trying a few plausible key names/locations since the exact schema isn't
    verified against live docs."""
    data = instance_payload.get("data", instance_payload) or {}
    if isinstance(data, dict) and "instance" in data and isinstance(data["instance"], dict):
        data = data["instance"]

    for key in ("status", "instance_status", "state"):
        val = data.get(key)
        if val:
            return str(val).strip().lower()

    return ""


def wait_until_shutdown(client: AutoDLClient, config: CleanupConfig) -> bool:
    """Poll instance status until it reports a shutdown-like state, or until
    `shutdown_poll_timeout_s` elapses. Returns True if confirmed shut down,
    False if we timed out without confirmation."""
    if config.dry_run:
        log.info("[DRY RUN] Skipping status poll, assuming shutdown confirmed.")
        return True

    deadline = time.monotonic() + config.shutdown_poll_timeout_s
    while time.monotonic() < deadline:
        try:
            payload = client.get_instance(config.instance_uuid)
        except AutoDLAPIError as exc:
            log.warning("Status check failed, will retry: %s", exc)
            time.sleep(config.shutdown_poll_interval_s)
            continue

        status = _extract_status(payload)
        log.info("Instance %s status: %r", config.instance_uuid, status or "<unknown>")

        if status in SHUTDOWN_STATUSES:
            log.info("Instance confirmed powered off.")
            return True

        if status and status not in TRANSIENT_STATUSES and status not in SHUTDOWN_STATUSES:
            # Unexpected status (e.g. still "running", or an error state) —
            # keep polling until timeout rather than guessing.
            log.debug("Status not yet terminal, continuing to poll.")

        time.sleep(config.shutdown_poll_interval_s)

    log.warning(
        "Timed out after %.0fs waiting for instance %s to confirm shutdown.",
        config.shutdown_poll_timeout_s,
        config.instance_uuid,
    )
    return False


def cleanup_instance(config: Optional[CleanupConfig] = None) -> None:
    """Power off and then release the AutoDL instance.

    Safety model: `release` is only called after the instance is *polled and
    confirmed* to be in a shutdown state (not merely "immediately after the
    power_off call returned 200 OK"). power_off is asynchronous on AutoDL's
    side — a 200 response only means the shutdown request was accepted, not
    that the GPU/container has actually stopped — so calling release right
    away risks hitting the instance mid-shutdown. If confirmation doesn't
    arrive within `shutdown_poll_timeout_s`, release is skipped and this
    raises, so you don't silently destroy an instance that might still be
    mid-job or mid-shutdown.
    """
    config = config or CleanupConfig.from_env()
    client = AutoDLClient(config)

    log.info(
        "Starting AutoDL cleanup for instance=%s api_base=%s dry_run=%s",
        config.instance_uuid,
        config.api_base,
        config.dry_run,
    )

    # Step 1: power off.
    client.power_off(config.instance_uuid)

    # Step 2: poll status until confirmed shut down (or timeout).
    confirmed = wait_until_shutdown(client, config)
    if not confirmed:
        raise AutoDLAPIError(
            "Aborting: instance did not confirm shutdown within the timeout "
            "window, so release was NOT called. Re-run cleanup, or check the "
            "instance manually in the AutoDL console before releasing it."
        )

    # Step 3: release (irreversible — destroys container + disk).
    client.release(config.instance_uuid)
    log.info("Instance %s released successfully. Cleanup complete.", config.instance_uuid)


def main() -> int:
    try:
        cleanup_instance()
    except Exception as exc:  # noqa: BLE001 - top-level script guard
        log.error("Cleanup failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
