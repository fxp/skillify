---
name: autodl
description: 接入 AutoDL（autodl.com）GPU 算力租用平台 API 的使用手册——涵盖账户余额查询、容器实例（单卡/多卡 GPU 实例）的创建/开关机/释放/存镜像、以及弹性部署（按副本数自动伸缩的容器集群，适合部署推理服务/批量任务）。当用户提到"AutoDL""autodl.com""自动化开关 AutoDL 实例""AutoDL API""弹性部署""AutoDL Pro 实例"，或者要求写代码调用 AutoDL 相关能力（租 GPU、管理实例、部署推理服务、查算力库存）时，应主动使用本技能，不要凭记忆编造接口参数或误用其他 GPU 云平台（如 RunPod/Vast.ai/AWS）的接口习惯。
---
# AutoDL 接入指南

按量租用 GPU 的国内算力平台：容器实例的创建 / 开关机 / 存镜像 / 释放，以及弹性部署。
**本页只做分流与规则，字段表和示例在 `references/`。**

## 当前事实

| 项 | 值 |
| :--- | :--- |
| Base URL | `https://api.autodl.com` |
| 鉴权 | `Authorization: <TOKEN>`（**不带 `Bearer` 前缀**），Token 走环境变量 `AUTODL_TOKEN` |
| 响应结构 | 统一 `{"code": "Success"/其他, "msg": "", "data": …}`，`code != "Success"` 即出错 |
| 金额单位 | **整数，除以 1000 才是「元」**（余额、弹性部署价格区间都一样） |
| GET 传参 | **一律用 query string**（`params=`），不管文档示例长什么样 |

## 你的训练数据在这几点上是错的

以下每条都用真实 Token 打出来验证过，含一次完整实例生命周期（实测花费约 5 元）：

1. **官方文档把 GET 接口的传参方式写错了。** `GET .../instance/pro/snapshot` 和 `.../status`
   文档展示的是「请求 Body 示例」（JSON），实测放进 body 直接返回
   `{"code":"RequestParameterIsWrong"}`；**只有 query string 才被正确解析**。
2. **`create` 会自动开机。** 创建成功后状态直接是 `running`，不需要也不应该再调 `power_on`——
   那个接口是用来重启一台已关机实例的。
3. **`release` 必须先确认 `shutdown`。** 文档写「否则可能无法释放」像是概率性警告，
   实测是 **100% 确定性拒绝**。状态流转还有文档没列的 `starting` / `shutting_down` 中间态。
4. **`image/save` 要求实例已关机**——文档完全没写这个前置条件。对 `running` 实例调用返回
   `{"code":"InternalError","msg":"保存实例镜像前，请确保实例是关机状态"}`。
5. **金额是「元 × 1000」。** 真实余额 29.29 元对应 `assets = 29290`。
   套用国内支付类 API 常见的「除以 100」会把数字放大 10 倍，而且**不会报错**。
6. **余额响应里有 `blocked_asset`（冻结金额），文档没提。** 可用余额应算
   `(assets - blocked_asset) / 1000`，只看 `assets` 会高估。
7. **企业认证门槛按接口区分，不是套在整个弹性部署 API 上。** 查 GPU 库存、查私有镜像列表
   个人实名就能调；碰到具体部署资源（创建 / 列表 / 容器操作）才被 `BadRequest` 拒。

## 🔴 写「创建实例 / 创建部署」类代码前，先问一句

未实名认证的账号创建实例会被 `{"code":"TORealName"}` 拒绝；未企业认证调弹性部署创建会被
`{"code":"BadRequest","msg":"无当前资源访问权限"}` 拒绝。**这不是参数错误、不是重试能解决的问题，
也不会因为余额充足而绕过。** 所以涉及创建资源时，先问用户「账号实名 / 企业认证做了吗」，
而不是把它当运行时才暴露的报错。查余额、查列表、查库存这类只读接口不受此限。

## 我要做什么 → 读哪一份

| 我要做什么 | 读 | 核心 endpoint |
| :--- | :--- | :--- |
| 查余额、切换专用 NFS 存储 | [`account.md`](references/account.md) | `/api/v1/dev/wallet/balance` |
| 创建 / 查询 / 开关机 / 释放实例，保存镜像 | [`instances.md`](references/instances.md) | `/api/v1/dev/instance/pro/*` |
| 弹性部署（按副本数伸缩的容器集群）、GPU 库存、地区与 CUDA 编码表 | [`elastic-deployment.md`](references/elastic-deployment.md) | `/api/v1/dev/deployment/*`、`/machine/region/gpu_stock` |

## House rules（写代码前必读）

- **别信 HTTP 状态码，判 `data.code`。** 响应统一 200，出错信息在 body 里。
- **没有稳定的错误码枚举表。** 只能靠 `msg` 文本判断，别写 `switch`。已实测到的组合：
  `RequestParameterIsWrong`（传参方式或格式不对）、`RecordNotFoundError`（资源不存在但请求合法）、
  `BadRequest`（认证等级不够）、`TORealName`（未实名）、`InternalError`（规格暂无库存，可重试）。
- **`gpu_spec_uuid` 是算力规格 ID，不是 GPU 型号名**，且没有接口可动态查询——见 `instances.md` 里的对照表。
- **「当前算力规格暂无库存」是良性报错**，换规格或稍等重试即可，别和权限类错误混淆。
- **释放前先轮询确认真的 `shutdown`**，`shutting_down` 中间态释放会被拒。

## 文档与实测不符之处

在 reference 里统一用 `<!-- Gap: … -->` 标记（5 处），可直接 grep 定位。
上方「训练数据错误」一节已全部覆盖。

## 验证边界

**已验证**：账户 + 容器实例 Pro API 全部接口、弹性部署全部只读接口，含完整生命周期实测。
**未验证**：弹性部署的**创建**接口及所有依赖 `deployment_uuid` 的管理接口——
测试账号只有个人实名、无企业认证，这是账号级硬阻塞，不是没花力气。
