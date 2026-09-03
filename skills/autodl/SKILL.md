---
name: autodl
description: 接入 AutoDL（autodl.com）GPU 算力租用平台 API 的使用手册——涵盖账户余额查询、容器实例（单卡/多卡 GPU 实例）的创建/开关机/释放/存镜像、以及弹性部署（按副本数自动伸缩的容器集群，适合部署推理服务/批量任务）。当用户提到"AutoDL""autodl.com""自动化开关 AutoDL 实例""AutoDL API""弹性部署""AutoDL Pro 实例"，或者要求写代码调用 AutoDL 相关能力（租 GPU、管理实例、部署推理服务、查算力库存）时，应主动使用本技能，不要凭记忆编造接口参数或误用其他 GPU 云平台（如 RunPod/Vast.ai/AWS）的接口习惯。
---

# AutoDL（autodl.com）GPU 算力平台接入指南

AutoDL 是一个面向个人开发者和企业的 GPU 算力租用平台。本技能包覆盖它的 REST API——不是控制台网页操作，是可以写代码调用的编程接口，目前分三块：账户/存储、容器实例 Pro（单实例管理）、弹性部署（多副本自动伸缩）。

## ⚠️ 账户/容器实例 Pro API 已用真实 API 验证；弹性部署仅创建/管理类接口仍未验证

已用真实 Token 验证过账户/容器实例 Pro API 的**全部接口**：查余额、切换专用 NFS、查实例/镜像列表、查 GPU 库存、**创建实例 → 开机运行 → 关机 → 保存镜像 → 重新开机 → 再关机 → 释放**完整生命周期都真实跑通过（实测总花费不到 5 元），过程中发现并修正了好几处真实问题：① 官方文档自己写错了 GET 接口的传参方式；② 未实名认证的账号创建实例会被拒绝；③ 保存镜像前必须先关机，文档没写这个前置条件；④ `power_on` 的响应结构和 `power_off`/`release` 不一样（见下方"跨领域的通用规则"）。

弹性部署 API 里**所有只读查询接口也已用真实调用验证**（镜像列表、GPU 库存、部署列表、时长包、调度黑名单），并确认了权限门槛是按接口区分、不是整个 API 一刀切。**只有"创建部署"和依赖已有部署/容器 UUID 的管理类接口（停止容器、设置副本数、停止/删除部署、设置调度黑名单）仍未验证**——测试账号没有企业认证，创建不了部署，这些接口自然也拿不到真实的 `deployment_uuid`/`container_uuid` 去测，这部分内容还是忠实转录自文档，未经真实调用确认。

另外做过一轮**文档保真度对照测试**（3 个场景，读了这份技能包的 Agent vs 完全凭通用知识写代码的 Agent，对照官方文档判定谁写对了，不是真实调用打分）：通过率 100% vs 40%，详见 `../../autodl-workspace/iteration-1/review.html`。AutoDL 相对小众，公开语料对它 API 细节的覆盖比 `bigmodel-cn` 那种头部平台少得多，所以没装技能包时编造接口的情况比 bigmodel-cn 测试时更严重。

## 🔴 写"创建实例/创建部署"类代码前，先确认账号已完成实名认证

**已用真实 API 调用验证（2026-09）——这是一个会导致代码 100% 跑不通的硬性前提，不是可选提醒**：`POST /api/v1/dev/instance/pro/create` 在未完成个人实名认证（或企业认证）的账号上会被平台直接拒绝，返回：

```json
{"code": "TORealName", "msg": "未完成实名认证,认证后才可使用"}
```

这不是参数错误、不是重试能解决的问题，也**不会因为账号余额充足而绕过**——哪怕预算再多，认证没做就是创建不了。弹性部署 API 同理，未企业认证会被 `{"code":"BadRequest","msg":"无当前资源访问权限"}` 拒绝。

**所以：只要任务涉及"创建实例"或"创建部署"，写代码之前先问用户一句"账号实名认证/企业认证做了吗"**，而不是把这个当成运行时才会暴露的报错去处理。查余额、查实例列表、查镜像列表、查 GPU 库存这类**只读**接口不受此限制，未认证账号也能正常调用，可以用来提前探路（比如先查 GPU 库存看看有没有货），但不代表账号已经具备创建资源的资格。

补充一个真实创建时可能遇到的良性报错：`{"code":"InternalError","msg":"当前算力规格暂无库存, 请修改配置或稍等再试"}`——这是某个 `gpu_spec_uuid` 当前没货，换一个规格或稍等重试即可，不是账号权限问题也不是代码写错了，别和 `TORealName`/`BadRequest` 这两个权限类错误搞混。

## 用之前先确认另外两件事

1. **Base URL 固定为** `https://api.autodl.com`。
2. **鉴权和大多数平台不一样，没有 `Bearer` 前缀**：请求头直接是 `Authorization: <你的token>`（注意不是 `Authorization: Bearer <token>`）。Token 获取位置：控制台 → 账号 → 设置 → 开发者Token。

## 30 秒跑通第一个请求（查余额）

```python
import requests

resp = requests.post(
    "https://api.autodl.com/api/v1/dev/wallet/balance",
    headers={"Authorization": "your_token"},
)
print(resp.json())
```

## 能力域导航

| 我想做什么 | 参考文件 | 涉及的核心 endpoint |
| :--- | :--- | :--- |
| 查余额、切换专用 NFS 存储 | [`references/account.md`](references/account.md) | `POST /api/v1/dev/wallet/balance`、`POST /api/v1/dev/exclusive_nfs/mount` |
| 创建/查询/开关机/释放单个 GPU 实例，保存镜像 | [`references/instances.md`](references/instances.md) | `POST /api/v1/dev/instance/pro/create`、`GET .../snapshot`、`GET .../status`、`.../power_on`、`.../power_off`、`.../release`、`.../image/save` |
| 部署自动伸缩的容器集群（推理服务/批量任务），查 GPU 库存 | [`references/elastic-deployment.md`](references/elastic-deployment.md) | `POST /api/v1/dev/deployment`、`.../deployment/list`、`.../deployment/container/*`、`POST /api/v1/dev/machine/region/gpu_stock` |

**该用容器实例 Pro API 还是弹性部署 API？** 只需要一台机器手动跑跑代码、调试模型 → 用容器实例 Pro API；需要"根据负载自动维持 N 个副本""跑完一批任务自动释放""对外提供稳定的推理服务" → 用弹性部署 API。两者的鉴权门槛不同（后者需要企业认证），GPU 型号的表示方式也不同（前者用 `gpu_spec_uuid` 如 `pro6000-p`，后者用 `gpu_name_set` 如 `"RTX 4090"`），不能把一个接口的参数值套到另一个接口上。

## 跨领域的通用规则

- **所有 GET 接口都要用 URL 查询字符串传参，不要用 JSON body**——已用真实 API 验证：`references/instances.md` 里 `GET .../snapshot` 和 `GET .../status` 这两个接口，**官方文档自己的示例写错了**（文档展示的是"请求 Body 示例"），实测把参数放进 `requests.get(url, json={...})` 的 body 会直接报 `{"code":"RequestParameterIsWrong","msg":"请求参数错误"}`；改用 `requests.get(url, params={...})` 才能被正确解析。不管某个 GET 接口的文档示例长什么样，都优先假设它要 query string，遇到 `RequestParameterIsWrong` 先检查传参方式。
- **响应体统一结构**：`{"code": "Success"/其他, "msg": "", "data": ...}`。`code` 不等于 `"Success"` 即视为出错，错误信息在 `msg` 里——文档没有提供独立的错误码枚举表，只能靠 `msg` 的文本内容判断错误原因，写错误处理时不要假设有稳定的错误码可以做 `switch`。已实测到的几个真实错误 `code`/`msg` 组合，可以作为"这类字符串错误码长什么样"的参考：`RequestParameterIsWrong`/"请求参数错误"（传参方式或格式不对）、`RecordNotFoundError`/"未查询到相关实例"（查询的资源不存在，但请求本身合法）、`BadRequest`/"无当前资源访问权限"（账号认证等级不够，比如未企业认证却调弹性部署接口）、`TORealName`/"未完成实名认证,认证后才可使用"（账号未实名，见上方红色提示）、`InternalError`/"当前算力规格暂无库存"（某个 `gpu_spec_uuid` 临时没货，换个规格或重试）。
- **创建实例会自动开机，不要多余地再调用一次开机接口**：已用真实调用验证——`POST .../instance/pro/create` 成功后实例已经在启动/运行了，`POST .../instance/pro/power_on` 只用于重启一台之前被关过机的实例。
- **金额单位统一是"元 × 1000"的整数**：无论是余额（`wallet/balance` 的 `assets`）还是弹性部署的价格区间（`price_from`/`price_to`），都要除以 1000 才是"元"。
- **GPU 型号有两套完全不同的标识方式**：容器实例 Pro API 用 `gpu_spec_uuid`（如 `pro6000-p`），弹性部署 API 用 `gpu_name_set`（GPU 型号名称字符串，如 `"RTX 4090"`）。写同时用到两套接口的代码时，不要把这两套值搞混或试图共用一个配置项。
- **CUDA 版本统一用整数编码**：去掉版本号的点，`11.8` → `118`。两套 API 都这么编码，规则一致。
- **私有镜像 UUID 在两套实例 API 间通用，但"查镜像列表"接口本身不通用**：已用真实调用验证——用容器实例 Pro API 保存出来的镜像，同一个 `image_uuid` 在两套 API 各自的"获取镜像列表"接口里都查得到，说明底层是同一份镜像仓库，`image_uuid` 可以跨两套 API 直接使用；但**这两个"获取镜像列表"是完全不同的接口**——容器实例 Pro API 的是 `POST .../instance/pro/image/private/list`，返回字段含 `image_uuid`/`name`/`status`/`image_size`/`create_at`；弹性部署的是 `POST /api/v1/dev/image/private/list`，返回字段只有 `id`/`image_name`/`image_uuid`，字段名不一样（`name` vs `image_name`）也没有 `status`/`image_size`，两者路径和字段都不能混用。
- **保存镜像前必须先关机**：已用真实调用验证——`POST .../instance/pro/image/save` 对一台 `running` 状态的实例直接调用会被拒绝，返回 `{"code":"InternalError","msg":"保存实例镜像前，请确保实例是关机状态"}`，文档没有写这个前置条件。正确顺序是 `power_off` → 轮询确认 `shutdown` → 再 `image/save`。
- **`power_on` 的响应结构和 `power_off`/`release` 不一样**：已用真实调用验证——`power_off`/`release` 成功时 `data` 是 `null`，但 `power_on` 成功时 `data` 是 `{"description": "开机指令已下发，请稍后关注实例最新状态"}`，是个带字段的对象。写统一的响应解析代码时不要假设所有开关机类接口的 `data` 形状一致。
- **实例/容器内置环境变量可以省掉一次 API 调用**：容器 UUID（`AutoDLContainerUUID`）、部署 UUID（`AutoDLDeploymentUUID`）、实际调度到的地区（`AutoDLDataCenter`）都能直接从容器内环境变量读到，不需要反过来调 API 查"我是谁"。
- **地区代码、CUDA 版本编码、公共镜像 UUID 这几张附录表**统一放在 [`references/elastic-deployment.md`](references/elastic-deployment.md) 末尾，`references/instances.md` 只放了 GPU 规格 ID 这一张专属于它的表，避免重复维护两份几乎一样的表格。

## 目录结构

```
autodl/
├── SKILL.md                          # 你正在读的这份
└── references/
    ├── account.md                    # 余额、NFS 存储切换
    ├── instances.md                  # 容器实例 Pro API + GPU 规格 ID 表
    └── elastic-deployment.md         # 弹性部署 API + 地区/CUDA/镜像附录表
```

内容整理自 `www.autodl.com/docs/`（抓取于 2026-09）。平台会持续上新 GPU 型号和镜像，如果某个 `gpu_spec_uuid`/`image_uuid` 调用报"不存在"，优先去控制台核实最新值，而不是死守本技能包列出的几行示例表格。
