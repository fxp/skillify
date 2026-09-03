#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
save_image_and_release.py

Automates the following workflow against an AutoDL (https://www.autodl.com) container
instance using AutoDL's "容器实例 Pro" Open API, called directly over HTTP with the
`requests` library (no SDK):

    1. Make sure the source instance is shut down (image saving needs a quiescent
       system disk).
    2. Save the instance's system disk as a new private image.
    3. Poll until the image finishes processing on the server side.
    4. (Optional, on by default) Actually *prove* the image is usable: spin up a
       small throw-away instance from the freshly-saved image, wait for it to reach
       "running", then power it off and release it again. This is the only way to
       be reasonably sure the image really boots, rather than just trusting that
       the "save" call reported success.
    5. Only after the image has been verified, release (释放/删除) the original
       source instance so it stops being billed.

API reference used (AutoDL "容器实例Pro API", https://www.autodl.com/docs/instance_pro_api/):

    Base URL   : https://api.autodl.com
    Auth header: "Authorization: <your_token>"   (token from
                 AutoDL console -> 账户 -> 设置 -> 开发者Token)

    POST /api/v1/dev/instance/pro/power_off              {instance_uuid}
    POST /api/v1/dev/instance/pro/power_on                {instance_uuid, payload, start_command?}
    GET  /api/v1/dev/instance/pro/status                  {instance_uuid}
    GET  /api/v1/dev/instance/pro/snapshot                {instance_uuid}
    POST /api/v1/dev/instance/pro/image/save              {instance_uuid, image_name}
    POST /api/v1/dev/instance/pro/image/private/list      {page_index, page_size}
    POST /api/v1/dev/instance/pro/create                  {gpu_spec_uuid, image_uuid, req_gpu_amount,
                                                             expand_system_disk_by_gb, cuda_v_from,
                                                             data_center_list?, instance_name?, start_command?}
    POST /api/v1/dev/instance/pro/release                 {instance_uuid}

    Every response is a JSON object shaped like:
        {"code": "Success", "msg": "...", "request_id": "...", "data": <payload or null>}
    A non-"Success" code is treated as an error.

IMPORTANT - things this script assumes / guesses because they are not 100% nailed
down by the public docs (see the "ASSUMPTIONS" block below and the final report):
  - The exact set of instance status strings ("running" / "shutdown" / ... ).
  - Whether /image/save requires the instance to already be stopped (we stop it
    ourselves to be safe, regardless).
  - Whether /create implicitly powers the new instance on (we call power_on
    explicitly afterwards to not depend on that).
  - The private image list endpoint is used (with client-side filtering by
    image_uuid/image_name) to poll save status, since no dedicated
    "get single image" endpoint is documented.

Usage example:

    export AUTODL_TOKEN="xxxxxxxxxxxxxxxxxxxxxxxx"

    python3 save_image_and_release.py \
        --instance-uuid container-xxxxxxxxxx \
        --image-name my-training-env-2026-09-03 \
        --verify-gpu-spec-uuid gpu-xxxxxxxxxx \
        --verify-cuda-v-from 113 \
        --yes

    # To skip the (paid) boot-test verification and just trust the "finished"
    # status reported by the image/save + image/private/list calls:
    python3 save_image_and_release.py \
        --instance-uuid container-xxxxxxxxxx \
        --image-name my-training-env-2026-09-03 \
        --skip-deep-verify --yes
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_URL = "https://api.autodl.com"

# Status strings we treat as "instance is off" / "instance is on" respectively.
# NOTE (assumption): AutoDL's own console/docs are not fully explicit about the
# canonical spelling, so we match against a small set of plausible variants
# case-insensitively rather than a single hard-coded string.
STOPPED_STATUSES = {"shutdown", "stopped", "stop", "poweroff", "power_off"}
RUNNING_STATUSES = {"running", "start", "started"}
FAILED_IMAGE_STATUSES = {"failed", "fail", "error"}
FINISHED_IMAGE_STATUSES = {"finished", "success", "succeed", "succeeded"}


class AutoDLAPIError(RuntimeError):
    """Raised when the AutoDL API returns a non-success code, or the HTTP call fails."""


class TimeoutWaitingForState(RuntimeError):
    """Raised when polling for a target state exceeds the configured timeout."""


@dataclass
class AutoDLClient:
    token: str
    base_url: str = DEFAULT_BASE_URL
    timeout_sec: float = 30.0
    session: requests.Session = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": self.token,
                "Content-Type": "application/json",
            }
        )

    # -- low level -----------------------------------------------------

    def _call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        """Call one AutoDL endpoint and return the parsed `data` field.

        AutoDL documents some endpoints as GET with a JSON request body (unusual,
        but that's what the docs show), so we always send `json=body` regardless
        of method rather than moving fields into query params.
        """
        url = self.base_url.rstrip("/") + path
        try:
            resp = self.session.request(method, url, json=body or {}, timeout=self.timeout_sec)
        except requests.RequestException as exc:
            raise AutoDLAPIError(f"HTTP request to {path} failed: {exc}") from exc

        try:
            payload = resp.json()
        except ValueError as exc:
            raise AutoDLAPIError(
                f"{path} returned non-JSON response (HTTP {resp.status_code}): {resp.text[:500]!r}"
            ) from exc

        if resp.status_code >= 400 or payload.get("code") not in (None, "Success"):
            raise AutoDLAPIError(
                f"{path} failed: HTTP {resp.status_code}, code={payload.get('code')!r}, "
                f"msg={payload.get('msg')!r}, request_id={payload.get('request_id')!r}"
            )
        return payload.get("data")

    # -- instance control ------------------------------------------------

    def get_instance_status(self, instance_uuid: str) -> str:
        data = self._call("GET", "/api/v1/dev/instance/pro/status", {"instance_uuid": instance_uuid})
        # Docs say the response is "a status string", but APIs like this commonly
        # wrap it in {"status": "..."} - handle both shapes defensively.
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("status", "instance_status", "state"):
                if key in data:
                    return str(data[key])
        raise AutoDLAPIError(f"Unrecognized status payload for {instance_uuid}: {data!r}")

    def power_off(self, instance_uuid: str) -> None:
        self._call("POST", "/api/v1/dev/instance/pro/power_off", {"instance_uuid": instance_uuid})

    def power_on(self, instance_uuid: str, payload: str = "gpu", start_command: Optional[str] = None) -> None:
        body: Dict[str, Any] = {"instance_uuid": instance_uuid, "payload": payload}
        if start_command:
            body["start_command"] = start_command
        self._call("POST", "/api/v1/dev/instance/pro/power_on", body)

    def release_instance(self, instance_uuid: str) -> None:
        self._call("POST", "/api/v1/dev/instance/pro/release", {"instance_uuid": instance_uuid})

    def create_instance(
        self,
        gpu_spec_uuid: str,
        image_uuid: str,
        cuda_v_from: int,
        req_gpu_amount: int = 1,
        expand_system_disk_by_gb: int = 0,
        data_center_list: Optional[List[str]] = None,
        instance_name: Optional[str] = None,
        start_command: Optional[str] = None,
    ) -> str:
        body: Dict[str, Any] = {
            "gpu_spec_uuid": gpu_spec_uuid,
            "image_uuid": image_uuid,
            "cuda_v_from": cuda_v_from,
            "req_gpu_amount": req_gpu_amount,
            "expand_system_disk_by_gb": expand_system_disk_by_gb,
        }
        if data_center_list:
            body["data_center_list"] = data_center_list
        if instance_name:
            body["instance_name"] = instance_name
        if start_command:
            body["start_command"] = start_command
        data = self._call("POST", "/api/v1/dev/instance/pro/create", body)
        # Docs: "Instance ID in `data` field" - handle both a bare string and a
        # {"instance_uuid": ...} wrapper defensively.
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("instance_uuid", "uuid", "id"):
                if key in data:
                    return str(data[key])
        raise AutoDLAPIError(f"Unrecognized create-instance response: {data!r}")

    # -- image management -------------------------------------------------

    def save_image(self, instance_uuid: str, image_name: str) -> str:
        data = self._call(
            "POST",
            "/api/v1/dev/instance/pro/image/save",
            {"instance_uuid": instance_uuid, "image_name": image_name},
        )
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("image_uuid", "uuid", "id"):
                if key in data:
                    return str(data[key])
        raise AutoDLAPIError(f"Unrecognized save-image response: {data!r}")

    def list_private_images(self, page_index: int = 1, page_size: int = 50) -> List[Dict[str, Any]]:
        data = self._call(
            "POST",
            "/api/v1/dev/instance/pro/image/private/list",
            {"page_index": page_index, "page_size": page_size},
        )
        if isinstance(data, dict):
            for key in ("list", "items", "images", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        if isinstance(data, list):
            return data
        raise AutoDLAPIError(f"Unrecognized image list response: {data!r}")

    def find_image(self, image_uuid: str, page_size: int = 50, max_pages: int = 20) -> Optional[Dict[str, Any]]:
        """Scan the private image list (paginated) for a given image_uuid."""
        for page_index in range(1, max_pages + 1):
            images = self.list_private_images(page_index=page_index, page_size=page_size)
            if not images:
                return None
            for img in images:
                uuid_val = img.get("image_uuid") or img.get("uuid") or img.get("id")
                if uuid_val == image_uuid:
                    return img
            if len(images) < page_size:
                return None
        return None


# --------------------------------------------------------------------------
# Polling helpers
# --------------------------------------------------------------------------

def wait_for_instance_status(
    client: AutoDLClient,
    instance_uuid: str,
    target_statuses: set,
    timeout_sec: float,
    poll_interval_sec: float,
    label: str,
) -> str:
    deadline = time.monotonic() + timeout_sec
    last_status = "?"
    while time.monotonic() < deadline:
        last_status = client.get_instance_status(instance_uuid)
        print(f"  [{label}] instance {instance_uuid} status = {last_status!r}")
        if last_status.strip().lower() in target_statuses:
            return last_status
        time.sleep(poll_interval_sec)
    raise TimeoutWaitingForState(
        f"Timed out after {timeout_sec}s waiting for instance {instance_uuid} to reach "
        f"one of {target_statuses} ({label}); last observed status = {last_status!r}"
    )


def wait_for_image_finished(
    client: AutoDLClient,
    image_uuid: str,
    timeout_sec: float,
    poll_interval_sec: float,
) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        img = client.find_image(image_uuid)
        if img is None:
            print(f"  [image-save] image {image_uuid} not visible in private image list yet...")
        else:
            status = str(img.get("status", "")).strip().lower()
            print(f"  [image-save] image {image_uuid} status = {status!r}")
            if status in FINISHED_IMAGE_STATUSES:
                return img
            if status in FAILED_IMAGE_STATUSES:
                raise AutoDLAPIError(f"Image {image_uuid} save failed (status={status!r}): {img!r}")
        time.sleep(poll_interval_sec)
    raise TimeoutWaitingForState(
        f"Timed out after {timeout_sec}s waiting for image {image_uuid} to finish saving"
    )


# --------------------------------------------------------------------------
# Main workflow
# --------------------------------------------------------------------------

def confirm(prompt: str, assume_yes: bool) -> None:
    if assume_yes:
        return
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted by user.")
        sys.exit(1)


def run(args: argparse.Namespace) -> int:
    client = AutoDLClient(token=args.token, base_url=args.base_url)

    print(f"== Step 0: check current status of source instance {args.instance_uuid} ==")
    status = client.get_instance_status(args.instance_uuid)
    print(f"  current status: {status!r}")

    print("== Step 1: ensure source instance is powered off before saving the image ==")
    if status.strip().lower() not in STOPPED_STATUSES:
        print(f"  instance is not stopped (status={status!r}); sending power_off ...")
        client.power_off(args.instance_uuid)
        wait_for_instance_status(
            client,
            args.instance_uuid,
            STOPPED_STATUSES,
            timeout_sec=args.power_off_timeout,
            poll_interval_sec=args.poll_interval,
            label="power-off",
        )
    else:
        print("  instance already stopped, skipping power_off.")

    print(f"== Step 2: save system disk as new private image '{args.image_name}' ==")
    image_uuid = client.save_image(args.instance_uuid, args.image_name)
    print(f"  save_image accepted, image_uuid = {image_uuid}")

    print("== Step 3: poll until the image finishes processing ==")
    image_info = wait_for_image_finished(
        client,
        image_uuid,
        timeout_sec=args.image_save_timeout,
        poll_interval_sec=args.poll_interval,
    )
    print(f"  image finished: {image_info}")

    if args.skip_deep_verify:
        print("== Step 4: SKIPPED deep verification (--skip-deep-verify) ==")
        print("  Only the platform-reported 'finished' status is being trusted as proof of usability.")
    else:
        print("== Step 4: deep-verify the image actually boots (creates a temporary test instance) ==")
        if not args.verify_gpu_spec_uuid:
            print(
                "  ERROR: --verify-gpu-spec-uuid is required for deep verification "
                "(or pass --skip-deep-verify to bypass this check)."
            )
            return 2

        test_instance_uuid = client.create_instance(
            gpu_spec_uuid=args.verify_gpu_spec_uuid,
            image_uuid=image_uuid,
            cuda_v_from=args.verify_cuda_v_from,
            req_gpu_amount=1,
            expand_system_disk_by_gb=0,
            data_center_list=args.verify_data_center,
            instance_name=f"verify-{args.image_name}"[:64],
        )
        print(f"  created temporary verification instance: {test_instance_uuid}")

        try:
            # Explicitly power it on rather than assuming /create already started it.
            print("  powering on verification instance ...")
            client.power_on(test_instance_uuid, payload="gpu")
            wait_for_instance_status(
                client,
                test_instance_uuid,
                RUNNING_STATUSES,
                timeout_sec=args.verify_boot_timeout,
                poll_interval_sec=args.poll_interval,
                label="verify-boot",
            )
            print("  verification instance reached 'running' - image boots successfully.")
        finally:
            print("  tearing down verification instance (power off + release) ...")
            try:
                client.power_off(test_instance_uuid)
                wait_for_instance_status(
                    client,
                    test_instance_uuid,
                    STOPPED_STATUSES,
                    timeout_sec=args.power_off_timeout,
                    poll_interval_sec=args.poll_interval,
                    label="verify-power-off",
                )
            except (AutoDLAPIError, TimeoutWaitingForState) as exc:
                print(f"  WARNING: failed to cleanly power off verification instance: {exc}")
            try:
                client.release_instance(test_instance_uuid)
                print("  verification instance released.")
            except AutoDLAPIError as exc:
                print(
                    f"  WARNING: failed to release verification instance {test_instance_uuid}; "
                    f"you may need to release it manually via the console. Error: {exc}"
                )

    print(
        "== Step 5: image saved and (optionally) verified. Ready to release the "
        f"original source instance {args.instance_uuid}. =="
    )
    if args.no_release:
        print("  --no-release passed: leaving the source instance intact. Nothing more to do.")
        return 0

    confirm(
        f"About to permanently release instance {args.instance_uuid} "
        f"(image '{args.image_name}' / {image_uuid} has been saved and verified). Continue?",
        args.yes,
    )

    # release requires the instance to already be stopped; we stopped it in Step 1.
    status = client.get_instance_status(args.instance_uuid)
    if status.strip().lower() not in STOPPED_STATUSES:
        print(f"  instance status is {status!r}, powering off again before release ...")
        client.power_off(args.instance_uuid)
        wait_for_instance_status(
            client,
            args.instance_uuid,
            STOPPED_STATUSES,
            timeout_sec=args.power_off_timeout,
            poll_interval_sec=args.poll_interval,
            label="pre-release-power-off",
        )

    client.release_instance(args.instance_uuid)
    print(f"  instance {args.instance_uuid} released successfully.")
    print()
    print("Done. Summary:")
    print(f"  New private image : {args.image_name} ({image_uuid})")
    print(f"  Source instance   : {args.instance_uuid} -> released")
    return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Save an AutoDL container instance's system disk as a private image, "
            "verify the image is usable, then release the source instance."
        )
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AUTODL_TOKEN"),
        help="AutoDL developer token. Defaults to the AUTODL_TOKEN environment variable.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL override.")
    parser.add_argument("--instance-uuid", required=True, help="Source instance to image and release.")
    parser.add_argument("--image-name", required=True, help="Name for the new private image.")

    parser.add_argument(
        "--skip-deep-verify",
        action="store_true",
        help=(
            "Skip creating a temporary test instance from the new image. If set, only the "
            "platform-reported 'finished' image status is trusted."
        ),
    )
    parser.add_argument(
        "--verify-gpu-spec-uuid",
        default=None,
        help="GPU spec UUID to use for the temporary verification instance (required unless --skip-deep-verify).",
    )
    parser.add_argument(
        "--verify-cuda-v-from",
        type=int,
        default=113,
        help="Minimum CUDA version code (e.g. 113 = CUDA 11.3+) for the verification instance. Default: 113.",
    )
    parser.add_argument(
        "--verify-data-center",
        action="append",
        default=None,
        help="Data center to try for the verification instance. Repeatable.",
    )

    parser.add_argument("--no-release", action="store_true", help="Do everything except the final release step.")
    parser.add_argument("-y", "--yes", action="store_true", help="Do not prompt before releasing the source instance.")

    parser.add_argument("--poll-interval", type=float, default=15.0, help="Seconds between status polls. Default: 15.")
    parser.add_argument(
        "--power-off-timeout", type=float, default=300.0, help="Seconds to wait for an instance to power off. Default: 300."
    )
    parser.add_argument(
        "--image-save-timeout",
        type=float,
        default=1800.0,
        help="Seconds to wait for the image save to finish. Default: 1800 (30 min).",
    )
    parser.add_argument(
        "--verify-boot-timeout",
        type=float,
        default=600.0,
        help="Seconds to wait for the verification instance to reach 'running'. Default: 600.",
    )

    args = parser.parse_args(argv)
    if not args.token:
        parser.error("An API token is required: pass --token or set the AUTODL_TOKEN environment variable.")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except (AutoDLAPIError, TimeoutWaitingForState) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
