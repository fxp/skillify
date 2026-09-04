# NOTES — 设计选择与已知不确定性

## 结论一览

| 项目 | 选择 | 置信度 |
|---|---|---|
| API 平面 | 火山引擎 **Open API（管理面）** `https://open.volcengineapi.com`，`Service=ark`，`Region=cn-beijing` | 高 |
| 鉴权 | 火山引擎标准 **HMAC-SHA256 签名（AK/SK，"V4" 风格）**，支持 STS `X-Security-Token` | 高 |
| Version | `2024-01-01`（方舟 Open API 当前通用版本号） | 中高 |
| Action | 默认 `GetAgentPlanQuota`，请求体 `{"PlanType":"Personal"}` | **低 — 未经官方文档核实** |
| 响应字段 | 5h / week / month 三个窗口的 Total / Used / Remaining / ResetTime | **低 — 采用容错解析** |

## 为什么选管理面 Open API + AK/SK，而不是推理面 API Key

方舟有两套接口：

1. **推理面** `https://ark.cn-beijing.volces.com/api/v3/...`，`Authorization: Bearer <ARK_API_KEY>`。只负责 chat/embeddings 等模型调用，API Key 是资源级凭证，看不到账号级的套餐/计费信息。
2. **管理面** `https://open.volcengineapi.com/?Action=...&Version=2024-01-01`，火山引擎统一 AK/SK 签名。所有"账号维度"的资源（Endpoint、模型服务、订阅/套餐）都挂在这里，权限由 IAM 策略控制。

Agent Plan 套餐余量是账号级订阅信息，只能落在管理面。因此工具实现了完整的火山引擎签名（`volc_signer.py`），凭证从 `VOLC_ACCESSKEY` / `VOLC_SECRETKEY` 读取——这是火山引擎官方 SDK 的默认环境变量名，与现有部署习惯一致。

## 未经验证的部分（重要）

我没有可用凭证，也未读取任何本地文档，以下内容是基于对火山引擎 Open API 命名惯例的推断，**上线前必须用 `--dump-raw` 核对一次**：

- **Action 名称**：`GetAgentPlanQuota` 是猜测。真实名称可能是 `DescribeAgentPlanUsage`、`GetSubscriptionQuota`、`ListAgentPlanQuotas` 等。通过 `ARK_QUOTA_ACTION` 环境变量或 `--action` 覆盖即可，无需改代码。
- **请求参数**：假定用 `PlanType` 区分个人版/团队版。若接口按 `PlanId` / `SubscriptionId` 定位，需在 `fetch_quota_response()` 中补一行。
- **AFP 与窗口字段**：解析器（`parse_quotas`）对键名做了大小写/下划线无关匹配，同时兼容"按窗口名做 key 的字典"和"带 `Window`/`Period` 字段的列表"两种形态，并能由 Total/Used/Remaining 任意两者推出第三者。如果官方返回的窗口名不在 `_WINDOW_ALIASES` 中，把新别名加进去即可。
- **是否真有独立 Open API**：也存在一种可能——Agent Plan 用量目前仅在控制台展示，或者暴露在推理面 `ark.cn-beijing.volces.com` 的某个 `/api/v3/.../usage` 路径下用 API Key 鉴权。若核实后是后者，只需替换 `ArkOpenApiClient.call()` 为一次 Bearer GET，解析与告警逻辑不变；代码已把"取数"与"解析/告警"分层，方便替换。

## 工程细节

- 零第三方依赖（`urllib` + `hmac`），便于放进 cron / 容器。
- 429 / 5xx / 网络错误：指数退避重试（默认 3 次，`ARK_HTTP_MAX_RETRIES` 可调），每次重试重新签名以避免 `X-Date` 过期。
- 错误统一抛 `QuotaError`，携带 `ResponseMetadata.Error.Code/Message` 与 `RequestId`，便于向火山工单反馈。
- 退出码：0 正常、1 有窗口低于阈值、2 配置/请求错误；`--json` 供上游程序消费。
- 阈值比较为严格 `<`（剩余 9.99% 告警，10.00% 不告警），`--threshold` 限定 0..100。
- 单元测试覆盖签名确定性、Header/URL 形态、两种响应形态解析、阈值边界、CLI 退出码；`sample_response.json` 供离线演示。

## 首次接入建议步骤

1. 在 IAM 给 AK 授予方舟只读策略（如 `ArkReadOnlyAccess`）。
2. `python ark_afp_quota.py --dump-raw -v`，观察实际 Action 是否被接受（`InvalidAction` 说明名称要改）。
3. 用真实响应校准 `_WINDOW_ALIASES` / 字段别名，跑 `python -m unittest` 回归。
4. 接入 cron，用退出码 1 触发通知。
