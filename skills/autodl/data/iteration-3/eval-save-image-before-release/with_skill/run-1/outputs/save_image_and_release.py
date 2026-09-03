#!/usr/bin/env python3
"""
AutoDL 容器实例 -> 存私有镜像 -> 确认镜像可用 -> 释放实例

用途：一台已经跑完训练、装好了整套环境的 AutoDL 容器实例，把它存成私有镜像，
方便以后直接用这个镜像开新实例（不用重装环境），确认镜像真的存好、可用之后，
再把这台实例释放掉，避免继续计费。

只用标准库 requests 直接调 AutoDL 的 HTTP API，不依赖 AutoDL 官方 SDK。

用法：
    export AUTODL_TOKEN="你的开发者 Token"          # 控制台 -> 账号 -> 设置 -> 开发者Token
    export AUTODL_INSTANCE_UUID="pro-xxxxxxxxxxxx"  # 要保存镜像并释放的实例
    export AUTODL_IMAGE_NAME="my-training-env-20260903"  # 新私有镜像的名字，可选，不填会自动生成
    python save_image_and_release.py

本脚本严格遵循 AutoDL 容器实例 Pro API 的几条关键约束（均来自官方接口文档 +
真实调用验证过的行为，而不是凭常识猜测）：

1. Base URL 固定为 https://api.autodl.com；鉴权是 `Authorization: <token>`，
   注意没有 "Bearer " 前缀，这点和大多数平台不一样。
2. 所有 GET 接口（查状态、查快照）必须用 URL 查询字符串（requests 的 params=）
   传参，不能用 JSON body——官方文档自己的示例反而是错的（示例写的是 body），
   实测传 body 会直接返回 RequestParameterIsWrong。
3. 响应体统一是 {"code": ..., "msg": ..., "data": ...} 结构，`code` 不等于
   "Success" 就是出错，没有稳定的错误码枚举表，只能靠 code 字符串 + msg 文本
   判断，比如：
     - TORealName      -> 账号未实名/未企业认证，重试没有意义
     - BadRequest      -> 常见于"实例还没关机就想释放"
     - RequestParameterIsWrong -> 参数传法不对（比如 GET 接口传了 body）
     - RecordNotFoundError -> 查询的资源不存在
     - InternalError   -> 常见于"实例还在运行就想存镜像"，或 GPU 规格缺货
4. 保存镜像前必须先关机——这是文档没有写、但真实调用会被强制拒绝的前置条件：
   对一台 running 状态的实例直接调 image/save，会返回
   {"code":"InternalError","msg":"保存实例镜像前，请确保实例是关机状态"}。
   所以流程必须是：power_off -> 轮询状态直到 shutdown -> image/save。
5. 关机是异步的，中间会经过 shutting_down 这个文档没写的中间态，几秒后才变
   shutdown；轮询逻辑只应该判断"是否等于目标状态"，把其他值（starting/
   shutting_down）都当"还没到"处理，不要当成异常报警。
6. 保存镜像本身也是异步的——image/save 调用成功、拿到 image_uuid，不代表镜像
   已经存好，必须再轮询"获取镜像列表"接口，确认对应 image_uuid 的 status
   变成 finished，才算是镜像真的可用了。
7. 释放实例前也必须先确认处于 shutdown 状态——对一台 starting/running 的实例
   直接调 release，会 100% 确定地被拒绝（BadRequest /
   "请在实例关机状态下执行释放操作"），不是概率性的，所以同样要先关机、
   轮询确认 shutdown，再释放。
8. 金额没有用到这里（本脚本不查余额），但如果后续要扩展查余额，要记得
   wallet/balance 返回的金额单位是"元 x 1000"的整数，需要自己除以 1000。
"""

from __future__ import annotations

import os
import sys
import time
import dataclasses
from typing import Any, Optional

import requests

BASE_URL = "https://api.autodl.com"

# 关机 / 保存镜像 都是异步操作，轮询间隔与超时时间可以按需要调整。
POLL_INTERVAL_SECONDS = 5
POWER_OFF_TIMEOUT_SECONDS = 5 * 60
IMAGE_SAVE_TIMEOUT_SECONDS = 20 * 60

# 关机流程里已知会出现的中间态；轮询时遇到这些状态视为"还没到目标状态"，
# 而不是异常。
KNOWN_TRANSIENT_STATUSES = {"starting", "shutting_down"}


class AutoDLAPIError(RuntimeError):
    """AutoDL 接口返回了非 Success 的 code。"""

    def __init__(self, code: str, msg: str, request_id: Optional[str] = None):
        self.code = code
        self.msg = msg
        self.request_id = request_id
        super().__init__(f"[{code}] {msg}" + (f" (request_id={request_id})" if request_id else ""))


class AutoDLRealNameRequiredError(AutoDLAPIError):
    """账号未完成实名认证/企业认证——重试没有意义，需要人工去控制台完成认证。"""


class AutoDLTimeoutError(RuntimeError):
    """轮询超时，实例/镜像迟迟没有到达期望状态。"""


@dataclasses.dataclass
class AutoDLClient:
    token: str
    base_url: str = BASE_URL
    timeout_seconds: float = 30.0
    session: requests.Session = dataclasses.field(default_factory=requests.Session)

    def _headers(self) -> dict:
        # 注意：AutoDL 的鉴权直接是 "Authorization: <token>"，没有 "Bearer " 前缀。
        return {"Authorization": self.token}

    def _handle_response(self, resp: requests.Response) -> Any:
        resp.raise_for_status()
        body = resp.json()
        code = body.get("code")
        msg = body.get("msg", "")
        request_id = body.get("request_id")
        if code != "Success":
            if code == "TORealName":
                raise AutoDLRealNameRequiredError(code, msg, request_id)
            raise AutoDLAPIError(code, msg, request_id)
        return body.get("data")

    def _post(self, path: str, json: Optional[dict] = None) -> Any:
        resp = self.session.post(
            f"{self.base_url}{path}",
            headers=self._headers(),
            json=json or {},
            timeout=self.timeout_seconds,
        )
        return self._handle_response(resp)

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        # 所有 GET 接口都必须用 query string 传参（requests 的 params=），
        # 不能用 json= body——官方文档示例是错的，body 传参会返回
        # RequestParameterIsWrong。
        resp = self.session.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            params=params or {},
            timeout=self.timeout_seconds,
        )
        return self._handle_response(resp)

    # ---- 实例相关 ----

    def get_instance_status(self, instance_uuid: str) -> str:
        """只查状态，比 snapshot 轻量，适合轮询。data 直接就是状态字符串。"""
        data = self._get(
            "/api/v1/dev/instance/pro/status",
            params={"instance_uuid": instance_uuid},
        )
        return data

    def power_off_instance(self, instance_uuid: str) -> None:
        self._post(
            "/api/v1/dev/instance/pro/power_off",
            json={"instance_uuid": instance_uuid},
        )

    def release_instance(self, instance_uuid: str) -> None:
        self._post(
            "/api/v1/dev/instance/pro/release",
            json={"instance_uuid": instance_uuid},
        )

    def wait_for_instance_status(
        self,
        instance_uuid: str,
        target_status: str,
        timeout_seconds: float,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        last_status: Optional[str] = None
        while time.monotonic() < deadline:
            status = self.get_instance_status(instance_uuid)
            if status != last_status:
                print(f"  实例 {instance_uuid} 当前状态: {status}")
                last_status = status
            if status == target_status:
                return
            # starting/shutting_down 等是已知的中间态，继续轮询即可；
            # 其他未知状态同样按"还没到目标状态"处理，不当成异常提前中断。
            time.sleep(poll_interval_seconds)
        raise AutoDLTimeoutError(
            f"实例 {instance_uuid} 在 {timeout_seconds} 秒内没有到达目标状态 "
            f"'{target_status}'（最后一次观察到的状态: {last_status}）"
        )

    # ---- 镜像相关 ----

    def save_image(self, instance_uuid: str, image_name: str) -> str:
        """保存镜像是异步的，这里只是发起请求，返回新镜像的 image_uuid。
        拿到 image_uuid 不代表镜像已经存好，还要用 list_private_images 轮询确认。
        """
        data = self._post(
            "/api/v1/dev/instance/pro/image/save",
            json={"instance_uuid": instance_uuid, "image_name": image_name},
        )
        image_uuid = data["image_uuid"]
        return image_uuid

    def list_private_images(self, page_index: int = 1, page_size: int = 50) -> list:
        data = self._post(
            "/api/v1/dev/instance/pro/image/private/list",
            json={"page_index": page_index, "page_size": page_size},
        )
        # 宽松解析：不同版本的响应结构里实际的记录列表字段名可能不完全一致，
        # 常见形态是 {"list": [...], "max_page": ..., "result_total": ...}。
        if isinstance(data, dict):
            return data.get("list") or data.get("data") or []
        if isinstance(data, list):
            return data
        return []

    def find_private_image(self, image_uuid: str) -> Optional[dict]:
        page_index = 1
        page_size = 50
        while True:
            records = self.list_private_images(page_index=page_index, page_size=page_size)
            if not records:
                return None
            for record in records:
                if record.get("image_uuid") == image_uuid:
                    return record
            if len(records) < page_size:
                return None
            page_index += 1

    def wait_for_image_finished(
        self,
        image_uuid: str,
        timeout_seconds: float,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    ) -> dict:
        deadline = time.monotonic() + timeout_seconds
        last_status: Optional[str] = None
        while time.monotonic() < deadline:
            record = self.find_private_image(image_uuid)
            if record is not None:
                status = record.get("status")
                if status != last_status:
                    print(f"  镜像 {image_uuid} 当前状态: {status}")
                    last_status = status
                if status == "finished":
                    return record
            else:
                print(f"  镜像 {image_uuid} 暂未出现在镜像列表中，继续等待...")
            time.sleep(poll_interval_seconds)
        raise AutoDLTimeoutError(
            f"镜像 {image_uuid} 在 {timeout_seconds} 秒内没有变为 'finished' 状态"
            f"（最后一次观察到的状态: {last_status}）"
        )


def confirm_image_usable(record: dict) -> None:
    """对保存完成的镜像做一次基本可用性校验。

    AutoDL 的 API 没有提供"试跑一下这个镜像"的接口，能做的确认手段就是：
    状态确实是 finished，并且镜像大小是一个合理的正数（不是 0 或缺失，
    0 通常意味着保存过程出了问题、没有真正落盘）。
    """
    status = record.get("status")
    if status != "finished":
        raise RuntimeError(f"镜像状态不是 finished，实际为 {status!r}，不能视为可用")

    image_size = record.get("image_size")
    if not isinstance(image_size, (int, float)) or image_size <= 0:
        raise RuntimeError(
            f"镜像状态是 finished，但 image_size 异常（{image_size!r}），"
            "存疑，不建议直接当作可用镜像使用"
        )

    print(
        f"  镜像校验通过：image_uuid={record.get('image_uuid')}, "
        f"name={record.get('name')}, status={status}, "
        f"image_size={image_size}, create_at={record.get('create_at')}"
    )


def main() -> int:
    token = os.environ.get("AUTODL_TOKEN")
    instance_uuid = os.environ.get("AUTODL_INSTANCE_UUID")
    image_name = os.environ.get("AUTODL_IMAGE_NAME") or (
        f"auto-saved-{instance_uuid}-{int(time.time())}" if instance_uuid else None
    )

    if not token:
        print("错误：请通过环境变量 AUTODL_TOKEN 提供开发者 Token"
              "（控制台 -> 账号 -> 设置 -> 开发者Token）", file=sys.stderr)
        return 1
    if not instance_uuid:
        print("错误：请通过环境变量 AUTODL_INSTANCE_UUID 指定要保存镜像并释放的实例 UUID",
              file=sys.stderr)
        return 1

    client = AutoDLClient(token=token)

    try:
        print(f"[1/6] 查询实例 {instance_uuid} 当前状态...")
        current_status = client.get_instance_status(instance_uuid)
        print(f"  当前状态: {current_status}")

        if current_status == "shutdown":
            print("  实例已经是关机状态，跳过关机步骤。")
        else:
            print(f"[2/6] 关机实例 {instance_uuid}...")
            client.power_off_instance(instance_uuid)
            print("  已下发关机指令，轮询等待状态变为 shutdown"
                  "（会经过 shutting_down 中间态，属于正常现象）...")
            client.wait_for_instance_status(
                instance_uuid, target_status="shutdown",
                timeout_seconds=POWER_OFF_TIMEOUT_SECONDS,
            )
            print("  实例已关机。")

        # 保存镜像前必须确保实例处于关机状态——这是真实调用验证出的强制前置
        # 条件，运行中的实例直接调 image/save 会被 InternalError 拒绝。
        print(f"[3/6] 保存私有镜像（image_name={image_name!r}）...")
        image_uuid = client.save_image(instance_uuid, image_name)
        print(f"  已发起保存请求，新镜像 image_uuid={image_uuid}"
              "（保存是异步的，接下来轮询确认真正完成）")

        print(f"[4/6] 轮询镜像 {image_uuid} 状态，等待变为 finished...")
        image_record = client.wait_for_image_finished(
            image_uuid, timeout_seconds=IMAGE_SAVE_TIMEOUT_SECONDS,
        )
        print("  镜像保存完成。")

        print("[5/6] 确认镜像真的可用...")
        confirm_image_usable(image_record)

        # 释放前必须再次确认实例处于 shutdown 状态——对 starting/running 状态
        # 的实例直接释放会 100% 被 BadRequest 拒绝，不是概率性问题。保存镜像
        # 期间实例本身状态不会变化（保存镜像不需要重新开机），但这里仍显式
        # 复查一次，避免依赖"保存镜像不改变实例状态"这个未在文档中明确承诺的假设。
        print(f"[6/6] 释放实例 {instance_uuid} 以停止计费...")
        status_before_release = client.get_instance_status(instance_uuid)
        if status_before_release != "shutdown":
            print(f"  实例当前状态为 {status_before_release}，重新等待其变为 shutdown...")
            client.wait_for_instance_status(
                instance_uuid, target_status="shutdown",
                timeout_seconds=POWER_OFF_TIMEOUT_SECONDS,
            )
        client.release_instance(instance_uuid)
        print("  实例已释放。")

        print("\n全部完成:")
        print(f"  新私有镜像 image_uuid = {image_uuid}")
        print(f"  镜像名称               = {image_name}")
        print(f"  已释放的实例 instance_uuid = {instance_uuid}")
        print("  以后可以直接用这个 image_uuid 作为 image_uuid 参数创建新实例，"
              "无需重新配置环境。")
        return 0

    except AutoDLRealNameRequiredError as exc:
        print(
            "错误：账号未完成实名认证/企业认证，AutoDL 直接拒绝了相关操作，"
            "重试没有意义，需要先去控制台完成认证。\n"
            f"  原始错误: {exc}",
            file=sys.stderr,
        )
        return 2
    except AutoDLAPIError as exc:
        print(f"错误：AutoDL 接口返回失败 - {exc}", file=sys.stderr)
        return 3
    except AutoDLTimeoutError as exc:
        print(f"错误：等待超时 - {exc}", file=sys.stderr)
        return 4
    except requests.RequestException as exc:
        print(f"错误：HTTP 请求失败 - {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
