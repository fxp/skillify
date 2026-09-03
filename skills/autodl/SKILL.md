---
name: autodl
description: 接入 AutoDL（autodl.com）GPU 算力租用平台 API 的使用手册——涵盖账户余额查询、容器实例（单卡/多卡 GPU 实例）的创建/开关机/释放/存镜像、以及弹性部署（按副本数自动伸缩的容器集群，适合部署推理服务/批量任务）。当用户提到"AutoDL""autodl.com""自动化开关 AutoDL 实例""AutoDL API""弹性部署""AutoDL Pro 实例"，或者要求写代码调用 AutoDL 相关能力（租 GPU、管理实例、部署推理服务、查算力库存）时，应主动使用本技能，不要凭记忆编造接口参数或误用其他 GPU 云平台（如 RunPod/Vast.ai/AWS）的接口习惯。
---

# AutoDL（autodl.com）GPU 算力平台接入指南

AutoDL 是一个面向个人开发者和企业的 GPU 算力租用平台。本技能包覆盖它的 REST API——不是控制台网页操作，是可以写代码调用的编程接口，目前分三块：账户/存储、容器实例 Pro（单实例管理）、弹性部署（多副本自动伸缩）。

## ⚠️ 本技能包尚未做真实 API 调用验证

内容忠实转录自官方文档站（`www.autodl.com/docs/`），但**没有可用的 AutoDL API Token 做过实际调用测试**——不像本仓库另一份 `bigmodel-cn` 技能包那样，每一条关键结论都用真实 Key 验证过。用这份技能包写代码时，如果遇到和文档描述不一致的真实报错，**优先信任 API 的实际行为**，并考虑回来修正这份技能包（做法可参考 [`skills/generate-skill-from-api-docs`](../generate-skill-from-api-docs) 里"真实 API 验证"那一步）。

## 用之前先确认三件事

1. **Base URL 固定为** `https://api.autodl.com`。
2. **鉴权和大多数平台不一样，没有 `Bearer` 前缀**：请求头直接是 `Authorization: <你的token>`（注意不是 `Authorization: Bearer <token>`）。Token 获取位置：控制台 → 账号 → 设置 → 开发者Token。
3. **认证门槛因接口而异**：容器实例 Pro API 需要"个人实名认证或企业认证"任一即可；弹性部署 API **必须企业认证**，个人实名认证不够。写代码前先跟用户确认账号认证状态，账号门槛不够会导致所有调用失败。

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

- **响应体统一结构**：`{"code": "Success"/其他, "msg": "", "data": ...}`。`code` 不等于 `"Success"` 即视为出错，错误信息在 `msg` 里——文档没有提供独立的错误码枚举表，只能靠 `msg` 的文本内容判断错误原因，写错误处理时不要假设有稳定的错误码可以做 `switch`。
- **金额单位统一是"元 × 1000"的整数**：无论是余额（`wallet/balance` 的 `assets`）还是弹性部署的价格区间（`price_from`/`price_to`），都要除以 1000 才是"元"。
- **GPU 型号有两套完全不同的标识方式**：容器实例 Pro API 用 `gpu_spec_uuid`（如 `pro6000-p`），弹性部署 API 用 `gpu_name_set`（GPU 型号名称字符串，如 `"RTX 4090"`）。写同时用到两套接口的代码时，不要把这两套值搞混或试图共用一个配置项。
- **CUDA 版本统一用整数编码**：去掉版本号的点，`11.8` → `118`。两套 API 都这么编码，规则一致。
- **私有镜像 UUID 在两套实例 API 间通用**：容器实例 Pro API 保存出来的私有镜像，`image_uuid` 也可以直接填进弹性部署 API 的 `image_uuid` 字段，反之亦然；公共基础镜像 UUID 也是两边共用同一套。
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
