# 弹性部署 API（Elastic Deployment / ESD）

来源：`www.autodl.com/docs/esd_api_doc/`

管理"部署"（deployment）——按副本数量自动伸缩、批量管理多个容器的服务，适合跑常驻推理服务、批量训练任务等场景。**创建/管理部署需要先完成企业认证**，门槛比 `references/instances.md` 里的容器实例 Pro API（个人实名或企业认证均可）更高，调用前务必和用户确认账号类型。

**已用真实 API 调用验证（2026-09）**：企业认证门槛**不是套在整个弹性部署 API 上**，而是按接口区分——`POST /api/v1/dev/deployment/list`（查部署列表）、`GET /api/v1/dev/deployment/ddp/overview`（查时长包）这类涉及"账号自己的部署资源"的接口，未企业认证会返回 `{"code":"BadRequest","msg":"无当前资源访问权限"}`；但 `POST /api/v1/dev/image/private/list`（查私有镜像列表）、`POST /api/v1/dev/machine/region/gpu_stock`（查 GPU 库存）这类不涉及具体部署资源的只读查询接口，个人认证账号一样能正常调用。也就是说：**创建部署前可以先用个人认证账号调库存/镜像列表探路，但真要创建部署本身，账号必须企业认证**。

## 核心概念

- **部署（deployment）**：一个部署配置，定义了要跑什么镜像、什么规格、调度到哪些地区、副本数量等；一个部署可以对应多个正在运行的"容器"。
- **容器（container）**：部署实际调度出来的、正在某台物理机上运行的实例，归属于某个部署。
- **`deployment_type` 三种类型**（创建部署时必选）：
  | 类型 | 用途 | 相关必填字段 |
  | --- | --- | --- |
  | `ReplicaSet` | 维持固定数量的常驻副本（副本挂了自动补） | `replica_num` |
  | `Job` | 批量跑任务，跑完即止，可控制并发数 | `replica_num`（总数）+ `parallelism_num`（同时运行数） |
  | `Container` | 单个容器，不涉及副本概念 | — |

## 获取私有镜像列表

**Endpoint**: `POST /api/v1/dev/image/private/list`

**关键参数**：`page_index`、`page_size`（int，必填）、`offset`（int，选填）。

**注意事项**：弹性部署**不支持从外部导入镜像**——只能用平台内创建并保存的自定义镜像（在 autodl.com 网页上操作），或用下方附录里的公共基础镜像 UUID。

**✅ 已用真实 API 调用验证（2026-09）**：个人认证账号（无企业认证）直接可用，符合上方总览说的"只读查询接口不需要企业认证"。**但要注意这个接口和 `references/instances.md` 里容器实例 Pro API 的"获取镜像列表"（`POST /api/v1/dev/instance/pro/image/private/list`）是两个不同路径、返回字段也不一样的接口**——这个弹性部署专用的版本，真实响应每条记录是 `{"id", "image_name", "image_uuid"}`，字段名是 `image_name` 不是 `name`，也**没有** `status`/`image_size`/`create_at` 这几个字段（那几个字段只在容器实例 Pro API 的镜像列表里出现）。两套 API 都叫"获取镜像列表"、路径和字段却不一样，是本平台又一个容易踩的重名坑。

---

## 创建部署

**Endpoint**: `POST /api/v1/dev/deployment`

**关键参数（顶层）**

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 | 部署名称 |
| deployment_type | string | 是 | `ReplicaSet` / `Job` / `Container`，见上方"核心概念" |
| replica_num | int | ReplicaSet/Job 必填 | 副本数量 |
| parallelism_num | int | Job 必填 | 同时运行的容器数量上限 |
| reuse_container | bool | 否 | 是否复用已停止的容器，能显著提升创建速度 |
| reuse_container_scope | string | 否 | `all`（默认，账号内所有部署的容器都可复用）或 `deployment`（仅本部署内复用） |
| container_template | object | 是 | 见下表 |

**`container_template` 关键字段**（这是整个 API 里字段最多的一个对象，逐条列出）

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| dc_list | list\<string\> | 是 | 可调度地区列表，见下方"地区代码"附录；**`region_sign` 字段已废弃，用这个** |
| gpu_name_set | list\<string\> | 是 | 可调度的 GPU 型号名称（如 `"RTX 4090"`），**这里填的是型号名字符串，不是 `references/instances.md` 里那套 `gpu_spec_uuid`** |
| gpu_num | int | 是 | 单容器所需 GPU 数量 |
| cuda_v_from / cuda_v_to | int | 是 | 可调度机器的 CUDA 版本范围，整数编码见下方"CUDA 版本编码"；**`cuda_v` 字段已废弃**（除非 `deployment_type=Container`，此时仍用 `cuda_v` 单值，见下方示例） |
| memory_size_from / memory_size_to | int | 是 | 内存范围，单位 GB |
| cpu_num_from / cpu_num_to | int | 是 | CPU 核心数范围，单位 1vCPU |
| price_from / price_to | int | 是 | 可接受的价格范围，单位是"元 × 1000"——比如 0.1 元要填 `100` |
| image_uuid | string | 是 | 私有镜像 UUID 或公共基础镜像 UUID |
| cmd | string | 是 | 容器启动命令 |
| cmd_before_shutdown | string | 否 | 停止容器前执行的命令，**超时时间 5 秒**，超时会直接强制停止，不要在这里放耗时操作 |
| service_6006_port_protocol / service_6008_port_protocol | string | 否 | `http`（默认）或 `tcp` |

**示例请求（ReplicaSet 类型）**：

```python
import requests
resp = requests.post(
    "https://api.autodl.com/api/v1/dev/deployment",
    headers={"Authorization": "your_token"},
    json={
        "name": "api自动创建",
        "deployment_type": "ReplicaSet",
        "replica_num": 2,
        "reuse_container": True,
        "container_template": {
            "dc_list": ["westDC2", "westDC3"],
            "gpu_name_set": ["RTX 4090"],
            "gpu_num": 1,
            "cuda_v_from": 113,
            "cuda_v_to": 128,
            "cpu_num_from": 1,
            "cpu_num_to": 100,
            "memory_size_from": 1,
            "memory_size_to": 256,
            "cmd": "sleep 100",
            "price_from": 10,       # 0.01 元/小时
            "price_to": 9000,       # 9 元/小时
            "image_uuid": "image-db8346e037",
        },
    },
)
print(resp.json())
```

`Job` 类型额外传 `parallelism_num`；`Container` 类型不传 `replica_num`/`parallelism_num`，且 `container_template` 里用单值 `cuda_v`（不是 `cuda_v_from`/`cuda_v_to`）——三种类型的请求体形状**不完全一致**，照抄文档示例时要对应 `deployment_type` 选对模板，不要用同一份模板改 `deployment_type` 字段就直接用。

**示例响应**：`data.deployment_uuid`。

---

## 获取部署列表

**Endpoint**: `POST /api/v1/dev/deployment/list`

**关键参数**：`page_index`/`page_size`（必填）、`name`（精确匹配，不支持模糊查询）、`status`（`running`/`stopped`，不填则全部）、`deployment_uuid`（均选填）。

**✅ 已用真实 API 调用验证（2026-09）**：属于"账号自己的部署资源"这一类，个人认证账号（无企业认证）调用会被拒绝，返回 `{"code":"BadRequest","msg":"无当前资源访问权限"}`——和上方总览一致。

---

## 查询容器事件

**Endpoint**: `POST /api/v1/dev/deployment/container/event/list`

**用途**: 查某个部署下容器的状态变化事件流（`creating` → `created` → `starting` → `running` → `shutting_down` → `shutdown` 等）。

**关键参数**：`deployment_uuid`（必填）、`deployment_container_uuid`（选填，筛选单个容器）、`page_index`/`page_size`（必填）、`offset`（选填）。

**注意事项**：文档明确建议的轮询模式——"可以通过对请求中的 `offset` 参数进行设置，轮询该接口获取最新的容器事件"，做实时事件监控时用这个模式，而不是反复全量拉取事件列表。

---

## 查询容器列表

**Endpoint**: `POST /api/v1/dev/deployment/container/list`

**用途**: 列出某个部署下的所有容器实例，支持按 GPU 型号/CPU/内存/价格/状态等多条件筛选。

**关键参数**（均选填，除了必填的 `page_index`/`page_size`）：`deployment_uuid`（必填）、`container_uuid`、`date_from`/`date_to`、`gpu_name`、`cpu_num_from`/`cpu_num_to`、`memory_size_from`/`memory_size_to`、`price_from`/`price_to`、`released`（是否查已释放实例）、`status`（数组，可传多个状态）。

**响应关键字段**：`info.ssh_command`、`info.root_password`、`info.service_6006_port_url`、`info.service_6008_port_url`——和 Pro 实例 API 类似，直接给了完整连接方式；`info.service_url`/`info.proxy_host`/`info.custom_port` 已废弃，不要用。

**注意事项**：如果需要在容器内部（比如启动脚本里）拿到自己的容器 UUID，不用调 API，直接读环境变量 `AutoDLContainerUUID`（还有 `AutoDLDeploymentUUID`、`AutoDLDataCenter` 也是容器内置环境变量）。

---

## 停止某个容器

**Endpoint**: `PUT /api/v1/dev/deployment/container/stop`

**关键参数**

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| deployment_container_uuid | string | 是 | 容器 UUID |
| decrease_one_replica_num | bool | 否 | **仅对 ReplicaSet 类型有效**——设为 true 时，停止容器的同时把副本数减 1（否则系统会自动补一个新容器维持副本数） |
| no_cache | bool | 否 | 是否不放入复用池（默认放入，如果部署开了 `reuse_container`） |
| cmd_before_shutdown | string | 否 | 覆盖部署创建时设置的 `cmd_before_shutdown`（同样 5 秒超时） |

---

## 设置副本数量

**Endpoint**: `PUT /api/v1/dev/deployment/replica_num`

**关键参数**：`deployment_uuid`、`replica_num`（均必填）。**仅支持 `ReplicaSet` 类型的部署**，对 `Job`/`Container` 类型调用无意义。

---

## 停止部署

**Endpoint**: `PUT /api/v1/dev/deployment/operate`

**关键参数**：`deployment_uuid`（必填）、`operate`（必填，**目前只能填 `"stop"`**，没有别的可选值）。

---

## 删除部署

**Endpoint**: `DELETE /api/v1/dev/deployment`

**关键参数**：`deployment_uuid`（必填）。

**注意事项**：如果部署还没停止就直接删除，系统会自动先停止再删除——不强制要求先调"停止部署"，但如果对成本敏感、想确认停止和删除是两个独立可控的步骤，建议还是显式先调停止。

---

## 设置调度黑名单

**Endpoint**: `POST /api/v1/dev/deployment/blacklist`

**用途**: 某个容器所在的物理机出现异常（比如开机异常慢）时，把该主机拉黑一段时间，之后调度不会再分配到这台机器。

**关键参数**：`deployment_container_uuid`（必填，通过这个容器所在的主机来定位要拉黑的机器）、`expire_in_minutes`（选填，默认 24 小时=1440 分钟，最长 30 天）、`comment`（选填，备注）。

## 获取生效中的调度黑名单

**Endpoint**: `GET /api/v1/dev/deployment/blacklist`

无请求参数。返回当前生效中的黑名单列表，含 `machine_id`、`data_center`、`expired_time` 等。

**✅ 已用真实 API 调用验证（2026-09）**：和"获取部署列表"、"获取已购时长包数据"一样属于"账号自己的部署资源"这一类——个人认证账号（无企业认证）调用会被拒绝，返回 `{"code":"BadRequest","msg":"无当前资源访问权限"}`，即使不带任何参数也一样，说明门槛判断和参数无关，是纯按接口区分的。

---

## 获取弹性部署 GPU 库存

**Endpoint**: `POST /api/v1/dev/machine/region/gpu_stock`

**用途**: 创建部署前先查目标地区/型号还有没有空闲 GPU，避免创建后一直调度不到资源。

**关键参数**：`region_sign`（必填，见下方地区代码附录）、`cuda_v_from`/`cuda_v_to`（选填）、`gpu_name_set`/`memory_size_from`/`memory_size_to`/`cpu_num_from`/`cpu_num_to`/`price_from`/`price_to`（均选填，用于进一步筛选）。

**注意事项**：文档原文强调——查询按"调度 1 张卡"的口径统计库存，如果查到某型号库存为 2，这 2 张卡可能分布在两台不同机器上；如果一个容器需要同时占用 2 张卡，实际不一定能调度成功。**库存数字不能直接当成"能同时开几张卡"的保证**，写自动化脚本时对这类边界要做好重试/降级处理。

**已用真实 API 调用验证（2026-09）**：真实响应比文档示例多两个字段，`data` 数组每一项的库存对象里还有 `chip_corp`（芯片厂商，如 `"nvidia"`）和 `cpu_arch`（CPU 架构，如 `"x86"`），不只是文档写的 `idle_gpu_num`/`total_gpu_num` 两个字段。另外这个接口本身不需要企业认证也能调用——本 token 没有企业认证（调 `deployment/list` 会返回 `1502` 权限错误，见下），但 GPU 库存查询依然正常返回数据，说明"查库存"和"建部署"这两类接口的权限门槛不一样，不要假设整个弹性部署 API 都需要企业认证才能调用任何一个接口。

---

## 获取已购时长包数据

**Endpoint**: `GET /api/v1/dev/deployment/ddp/overview`

**用途**: 查询购买的 GPU 时长包（预付费套餐）用量。

**关键参数**：`deployment_uuid`（必填，query string 参数，不是 body）。

**注意事项**：本文档介绍的这几个弹性部署 GET 接口里，这是唯一一个用 query string 传参的（`requests.get(url, params=...)` 而不是 `json=...`）。**但这不代表"query string 传参"在整个 AutoDL API 里很罕见**——`references/instances.md` 里容器实例 Pro API 的两个 GET 接口（`snapshot`/`status`），官方文档虽然写的是 JSON body 示例，但已用真实调用验证那两个接口实际也只认 query string，文档本身在那两处示例写错了。**结论：这个平台所有 GET 接口，无论文档怎么示例，都优先假设需要用 query string 传参，遇到报 `RequestParameterIsWrong` 再检查是不是传参方式搞反了。**

**示例响应**：`total`/`balance` 单位是**秒**，不是小时或元。

**✅ 已用真实 API 调用验证（2026-09）**：个人认证账号（无企业认证）调用会被拒绝，返回 `{"code":"BadRequest","msg":"无当前资源访问权限"}`——即使传一个不存在的 `deployment_uuid`，报的也是这个权限错误而不是"记录不存在"，说明鉴权检查在查资源之前就先拦下了。

---

## 附录：地区代码（`dc_list` / `region_sign`）

创建部署（`dc_list`）、查 GPU 库存（`region_sign`）、切换 NFS 存储（`data_center`）都用这套代码。容器启动后可以从容器内环境变量 `AutoDLDataCenter` 读到自己实际调度到的地区。

| 地区 | 代码 |
| --- | --- |
| 西北企业区（推荐） | `westDC2` |
| 西北B区 | `westDC3` |
| 北京A区 | `beijingDC1` |
| 北京B区 | `beijingDC2` |
| L20专区（原北京C区） | `beijingDC4` |
| V100专区（原华南A区） | `beijingDC3` |
| 内蒙A区 | `neimengDC1` |
| 内蒙B区 | `neimengDC3` |
| 佛山区 | `foshanDC1` |
| 重庆A区 | `chongqingDC1` |
| 3090专区 | `yangzhouDC1` |

## 附录：CUDA 版本编码（`cuda_v_from`/`cuda_v_to`/`cuda_v`）

整数编码，去掉版本号里的点：`11.8` → `118`，`12.1` → `121`，依此类推。

**选型建议**（来自文档原文）：如果你的框架需要的 CUDA 版本在这套编码里找不到精确对应值（比如需要 11.5），选**兼容你所需版本的最低可选值**（比如选 `118`），因为高版本驱动向下兼容低版本 CUDA；但版本选得越高，会把可调度的机器范围收得越窄，影响能调度到的卡的数量——不要为了"保险"无脑选最高版本。

## 附录：公共基础镜像 UUID（节选）

和 `references/instances.md` 里 Pro 实例 API 的公共镜像表是**同一套 UUID**，两个接口的 `image_uuid` 字段可以互通使用同一个公共镜像。完整列表见控制台。

## 附录：容器内环境变量

| 变量名 | 含义 |
| --- | --- |
| `AutoDLContainerUUID` | 当前容器的 UUID |
| `AutoDLDeploymentUUID` | 所属部署的 UUID |
| `AutoDLDataCenter` | 实际调度到的地区代码 |
