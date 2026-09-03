# 容器实例 Pro API

来源：`www.autodl.com/docs/instance_pro_api/`

管理"容器实例"（单个 GPU 实例，对应控制台里手动创建、按量计费的那种实例）：创建、查询、开关机、释放、保存镜像。**使用这套 API 前必须完成个人实名认证或企业认证**，未认证账号调用会被拒绝。

**已用真实 API 调用验证（2026-09）**：和 `references/elastic-deployment.md` 里的发现一致，认证门槛是**按接口区分，不是整个 API 一刀切**——本节的查询类接口（获取实例列表、获取镜像列表）在未实名认证的账号上也能正常调用；但真正"创建实例"（`POST .../instance/pro/create`）在未实名认证的账号上会被拒绝，返回 `{"code":"TORealName","msg":"未完成实名认证,认证后才可使用"}`，这是一个和"参数错误"（`RequestParameterIsWrong`）完全不同的错误码，写错误处理代码时要分开处理——前者是账号资质问题（应该提示用户去控制台完成认证，重试没有意义），后者才是真的参数写错了。

如果需求是"根据流量/负载自动伸缩多个容器副本"（比如部署一个推理服务），应该用 `references/elastic-deployment.md` 里的弹性部署 API，而不是这里的单实例 API——两者是完全不同的两套接口、两套鉴权门槛（弹性部署要求企业认证），不要混用。

## 创建实例

**Endpoint**: `POST /api/v1/dev/instance/pro/create`

**用途**: 创建一个按量计费的容器实例（**目前只支持按量计费方式创建**，不支持包月/包年等其他计费方式）。

**关键参数**

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| gpu_spec_uuid | string | 是 | 算力规格 ID（不是 GPU 型号名称！），见下方"GPU 规格 ID 对照表" |
| req_gpu_amount | int | 是 | GPU 数量，取值 1-4 |
| image_uuid | string | 是 | 镜像 UUID，私有镜像用"获取镜像列表"接口查，公共基础镜像见下方对照表 |
| expand_system_disk_by_gb | int | 是 | 系统盘扩容大小（GB），取值 0-500 |
| cuda_v_from | int | 是 | 调度机器最低需支持的 CUDA 版本，用整数编码（如 `113` = CUDA 11.3），见下方"CUDA 版本编码"说明 |
| data_center_list | list\<string\> | 否 | 指定候选地区列表，不填则系统自动选择，地区代码见 `references/elastic-deployment.md` 附录 |
| instance_name | string | 否 | 实例备注名 |
| start_command | string | 否 | 开机后自动执行的命令；**该命令执行失败不会导致实例关机** |

**示例请求**：

```python
import requests
resp = requests.post(
    "https://api.autodl.com/api/v1/dev/instance/pro/create",
    headers={"Authorization": "your_token"},
    json={
        "data_center_list": ["westDC3", "beijingDC2"],
        "req_gpu_amount": 1,
        "expand_system_disk_by_gb": 0,
        "gpu_spec_uuid": "pro6000-p",
        "image_uuid": "image-xxxxxxxxx",
        "cuda_v_from": 113,
        "instance_name": "API创建的实例",
        "start_command": "sleep 1",
    },
)
print(resp.json())
```

**示例响应**：

```json
{"code": "Success", "data": "pro-76419909953e", "msg": "", "request_id": "..."}
```

`data` 字段直接就是新建实例的 `instance_uuid` 字符串（不是对象）。

**✅ 已用真实 API 调用验证完整生命周期（2026-09，实名认证账号，`gpu_spec_uuid=v-48g`）**：`create` → 立即查状态就是 `"running"`（**实例创建成功后会自动开机，不需要额外调用"开机实例"接口**——"开机实例"接口是用来重新启动一台已经关机的实例，不是创建后的必经步骤）→ `power_off` → 状态先变 `"shutting_down"`、几秒后变 `"shutdown"`（这两个中间状态文档没有单独列出）→ `release` 成功。全程实际花费约 **0.03 元**（几分钟的 4090-48G 按量计费）。`gpu_spec_uuid` 库存会实时变化，某个规格暂时没货会返回 `{"code":"InternalError","msg":"当前算力规格暂无库存, 请修改配置或稍等再试"}`，这种情况下换一个规格或稍等重试即可，不是代码写错了。

同一次真实调用里，`snapshot` 接口返回的字段比文档示例更多：`jupyter_port`/`service_6006_port`/`service_6008_port` 是独立的数字端口字段（配合已经文档化的 `jupyter_domain`/`service_6006_domain`/`service_6008_domain` 使用），另外还有一个目前用途不明、始终为空的 `cg_application_info` 对象——照抄文档示例字段的解析代码，遇到额外字段不要报错，做宽松解析。

---

## 获取实例详情

**Endpoint**: `GET /api/v1/dev/instance/pro/snapshot`

**用途**: 查询实例的完整快照——SSH 连接信息、Jupyter 地址、端口映射、CPU/内存/磁盘使用率等。

**关键参数**：`instance_uuid`（string，必填），**用 URL 查询字符串传，不是 JSON body**（见下方注意事项）。

**示例请求**：

```python
import requests
resp = requests.get(
    "https://api.autodl.com/api/v1/dev/instance/pro/snapshot",
    headers={"Authorization": "your_token"},
    params={"instance_uuid": "pro-76576c61fdf1"},  # 用 params，不是 json
)
print(resp.json())
```

**示例响应关键字段**：

| 字段 | 说明 |
| --- | --- |
| `ssh_command` | 可直接执行的 SSH 登录命令 |
| `proxy_host` / `ssh_port` / `root_password` | 拆分开的 SSH 连接三要素 |
| `jupyter_domain` / `jupyter_token` | JupyterLab 访问地址与 token |
| `service_6006_domain` / `service_6008_domain` | 6006/6008 端口映射出的公网访问地址（常用于跑 TensorBoard、Gradio、Web 服务等） |
| `usage_info.valid` | 实例监控数据是否有效——实例刚启动时可能还没有采集到数据 |

**注意事项**：这个接口一次性把"怎么连上这台机器"的全部信息都给了（SSH/Jupyter/HTTP 端口映射），比自己拼 SSH 命令更可靠——直接用返回的 `ssh_command`，不要自己用 `proxy_host`+`ssh_port` 手工拼接（字段名和格式后续可能调整，拼接容易出错）。

**⚠️ 已用真实 API 调用验证（2026-09）：官方文档本身在这个接口写错了传参方式**——文档展示的是"请求Body示例"（JSON），但实测把 `instance_uuid` 放进 JSON body（`requests.get(url, json={...})`）会直接返回 `{"code":"RequestParameterIsWrong","msg":"请求参数错误"}`；改用 URL 查询字符串（`requests.get(url, params={...})`）才会被正确解析（返回 `RecordNotFoundError`/正常数据）。**这个坑对下面"获取实例状态"接口同样成立**——两个 GET 接口的官方文档示例都误导成了 JSON body 传参，实际都得用 query string。

---

## 获取实例状态

**Endpoint**: `GET /api/v1/dev/instance/pro/status`

**用途**: 只查状态，比查完整详情（snapshot）更轻量，适合轮询。

**关键参数**：`instance_uuid`（string，必填），**同样必须用 URL 查询字符串传**，不是 JSON body——原因见上方"获取实例详情"的验证说明。

**示例请求**：

```python
import requests
resp = requests.get(
    "https://api.autodl.com/api/v1/dev/instance/pro/status",
    headers={"Authorization": "your_token"},
    params={"instance_uuid": "pro-76576c61fdf1"},
)
print(resp.json())
```

**示例响应**：`data` 直接是状态字符串，如 `"running"`。已用真实调用观察到的完整状态流转：`running` → 调用 `power_off` 后先变 `shutting_down` → 几秒后变 `shutdown`（关机完成，可以释放了）——`shutting_down` 这个中间态文档没提，轮询代码如果只判断"是否等于 shutdown"、忽略中间态，逻辑上是安全的，但如果错误地把 `shutting_down` 当成异常状态处理就会误报。

---

## 获取实例列表

**Endpoint**: `POST /api/v1/dev/instance/pro/list`

**关键参数**：`page_index`、`page_size`（均为 int，必填）。

**注意事项**：分页字段是 `page_index`/`page_size`，响应里对应 `max_page`/`result_total`——和下面弹性部署 API 的分页参数命名规则一致，可以复用同一套分页封装。

---

## 开机实例

**Endpoint**: `POST /api/v1/dev/instance/pro/power_on`

**用途**：重新启动一台**已经关机**的实例。**不要在创建实例之后再调用一次这个接口**——已用真实调用验证：`create` 成功后实例会自动开机，创建请求返回时/返回后立刻查状态就已经是 `running`，`power_on` 只在"实例之前被关过机、现在要再开起来"这个场景下才需要调用。

**关键参数**

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| instance_uuid | string | 是 | 实例 ID |
| payload | string | 是 | 固定填 `"gpu"`——**目前 API 不支持以无卡模式开机**，只能有卡开机 |
| start_command | string | 否 | 本次开机执行的命令，会**覆盖**创建实例时设置的 `start_command` |

---

## 关机实例

**Endpoint**: `POST /api/v1/dev/instance/pro/power_off`

**关键参数**：`instance_uuid`（string，必填）。

---

## 释放实例

**Endpoint**: `POST /api/v1/dev/instance/pro/release`

**关键参数**：`instance_uuid`（string，必填）。

**注意事项**：**必须先关机再释放**，文档原话"否则可能无法释放"——写自动化脚本时，释放前要先调用 power_off 并确认状态变为已关机，不要图省事直接调释放接口。

---

## 保存镜像

**Endpoint**: `POST /api/v1/dev/instance/pro/image/save`

**关键参数**

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| instance_uuid | string | 是 | 要保存镜像的实例 |
| image_name | string | 是 | 新镜像名称 |

**示例响应**：`data.image_uuid` 是新镜像的 UUID，但**保存是异步的**——拿到 `image_uuid` 不代表镜像已经保存完成，要用下面"获取镜像列表"接口查 `status` 字段确认状态（如 `finished`）。

---

## 获取镜像列表

**Endpoint**: `POST /api/v1/dev/instance/pro/image/private/list`

**关键参数**：`page_index`、`page_size`（均为 int，必填）。

**示例响应**：每条记录含 `image_uuid`、`name`、`status`、`image_size`、`create_at`。

---

## 附录：GPU 规格 ID 对照表（`gpu_spec_uuid`）

**这套 ID 只在容器实例 Pro API 里用**，和弹性部署 API 用的 `gpu_name_set`（直接填 GPU 型号名称字符串，如 `"RTX 4090"`）是两套完全不同的标识方式，两个接口不能混用同一个值——这是本平台最容易踩的坑之一。

| 网页显示的 GPU 型号 | 规格名称 | `gpu_spec_uuid` |
| --- | --- | --- |
| H800-80G | 通用型 | `h800` |
| 4090-48G | 通用型 | `v-48g` |
| PRO6000-96G | 性能型 | `pro6000-p` |
| 4080(S)-32G | 性能型 | `v-32g-p` |
| 3090-48G | 通用型 | `v-48g-350w` |
| 5090-32G | 性能型 | `5090-p` |
| 4090D | 通用型 | `4090D` |

上表未覆盖官网会持续上新的规格；如果调用报"规格不存在"一类的错误，去控制台创建实例页面核对最新的 `gpu_spec_uuid`，不要死记这张表。

## 附录：公共基础镜像 UUID（节选）

| image_uuid | 框架 | 镜像 |
| --- | --- | --- |
| `base-image-l2t43iu6uk` | PyTorch | cuda11.8-cudnn8-devel-ubuntu20.04-py38-torch2.0.0 |
| `base-image-l374uiucui` | PyTorch | cuda11.3-cudnn8-devel-ubuntu20.04-py38-torch1.11.0 |
| `base-image-uxeklgirir` | TensorFlow | cuda11.2-cudnn8-devel-ubuntu20.04-py38-tf2.9.0 |
| `base-image-mbr2n4urrc` | Miniconda | cuda11.6-cudnn8-devel-ubuntu20.04-py38 |
| `base-image-l2843iu23k` | TensorRT | cuda11.8-cudnn8-devel-ubuntu20.04-py38-trt8.5.1 |

完整、最新的公共镜像列表请到 AutoDL 控制台创建实例页面查看——文档原文标注"更多新上线的镜像请联系客服"，说明这张表官方自己也没有维护成权威源，不要假设这几行覆盖了全部可用镜像。
