# 火山方舟 · 错误码 / 限流 / 计费 速查

本文覆盖：调用方舟数据面 API（标准 `/api/v3`、Coding Plan `/api/coding[/v3]`、Agent Plan `/api/plan[/v3]`）时会遇到的错误响应结构与全部推理错误码、Plan 用户最常见的报错及排查顺序、RPM/TPM 限流机制与 `ListModelRateLimit` 查询、可重试策略、后付费计费与欠费停服规则、FAQ 中与开发相关的条目。报错文案除标注 **已用真实 API 验证（2026-09-04，Agent Plan Medium）** 者外均为 **文档原文，未实测**；所有实测都在 Agent Plan 入口（`/api/plan/v3`、`/api/plan/v1/messages`）完成，标准 `/api/v3` 与 Coding Plan `/api/coding` 预期相同但未测。

## 目录
1. [错误响应结构](#1-错误响应结构)
2. [推理错误码全表](#2-推理错误码全表)（400 / 401 / 403 / 404 / 429 / 500）
3. [精调错误码](#3-精调错误码)
4. [Managed Agent 错误码（摘要）](#4-managed-agent-错误码摘要)
5. [Plan 用户最常见的报错](#5-plan-用户最常见的报错)
6. [速率限制（RPM / TPM / TPD / IPM）](#6-速率限制)
7. [重试策略建议](#7-重试策略建议)
8. [计费说明](#8-计费说明)
9. [常见问题中与开发相关的条目](#9-常见问题中与开发相关的条目)
10. [来源页面](#来源页面)

---

## 1. 错误响应结构

**Endpoint**: 适用于三套入口下所有数据面接口（`/chat/completions`、`/responses`、`/embeddings`、`/images/generations`、`/contents/generations/tasks` 等）
**用途**: 请求失败时 HTTP 状态码非 2xx，body 为 JSON。程序判别请用 `error.code`（字符串，可带 `.` 分隔的子码，如 `RateLimitExceeded.EndpointTPMExceeded`），不要解析 `message`。

**字段**
| 字段 | 类型 | 说明 |
|---|---|---|
| `error.code` | string | 错误码，见第 2 节全表；部分带占位符（`InvalidParameter.{{Parameter}}`、`NotFound.{{Parameter}}`） |
| `error.message` | string | 人类可读信息，以 `Request id: {{id}}` 结尾（实测为小写 `id`，且部分 message 与它之间没有句号），报工单时带上 |
| `error.type` | string | 错误类型：`BadRequest` / `Unauthorized` / `Forbidden` / `NotFound` / `TooManyRequests` / `InternalServerError`（与 HTTP 状态码大体对应，但 `InvalidSubscription` 是 400 + `Forbidden`，`InvalidAccountStatus` 是 401 + `Forbidden`，见全表）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：实测出现 `BadRequest`（400 `InvalidParameter`）、`Unauthorized`（401 `AuthenticationError`）、**空串 `""`**（404 `UnsupportedModel`、图片 `size` 的 400 `InvalidParameter`）三种值——`type` 可能为空，判别只用 `code` |
| `error.param` | string | 出错参数名。错误码页（1299023）只给出 状态码 / Type / Code / Message 四列，未给 HTTP 错误 body 示例；**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：HTTP 数据面错误 body 固定为 `{"error":{"code","message","param","type"}}` 四字段，`param` **总是存在**但常为空串 `""`（401 `AuthenticationError`、`developer` role 的 400、404 `UnsupportedModel`、图片 `size` 400 均为空），只有部分参数校验错误填字段名（`"service_tier"`、`"input[0]"`）。 |

**示例响应**（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**，三条原始 body，只改了 Request id）

`POST /api/plan/v3/chat/completions`，`messages[0].role = "developer"` → HTTP 400：
```json
{"error":{"code":"InvalidParameter","message":"The parameter `messages.role` specified in the request are not valid: invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`. Request id: 0217xxxxxxxx","param":"","type":"BadRequest"}}
```

同一 endpoint，`service_tier: "fast"` → HTTP 400（`param` 填了字段名）：
```json
{"error":{"code":"InvalidParameter","message":"The parameter `service_tier` specified in the request are not valid: fast service tier does not support coding plan. Request id: 0217xxxxxxxx","param":"service_tier","type":"BadRequest"}}
```

同一 endpoint，`model: "auto"` → HTTP 404（`type` 为空串）：
```json
{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. Request id: 0217xxxxxxxx","param":"","type":""}}
```

另：`GET /api/plan/v3/files` 与 `GET /api/plan/v3/models` 实测返回 **404 且 body 为空**（没有 `error` 对象）；`POST /api/plan/v3/tokenization`、`POST /api/plan/v3/context/create` 同样 404（body 未记录）——路径在该入口不存在时不走上述结构，客户端要先判 body 是否为空再解析 JSON。

**注意事项**
- 流式（SSE）请求中途出错：图片生成流式事件页（1824137）显示错误以事件 body 内的 `error: {code, message}` 下发，无 `type`/`param`；Chat 流式中途错误的事件格式 ⚠ 文档未说明。
- Managed Agent 的 SSE 阶段错误走 `data.type = "session.error"` 事件，判别字段是 `error.type`（不是 `error.code`），见第 4 节。
- 官方 SDK 会把非 2xx 包装为异常（Python `volcenginesdkarkruntime` 的 `ArkAPIConnectionError` 等，见 FAQ）；`openai` SDK 则抛 `openai.APIStatusError` 系列，`e.status_code` / `e.body["error"]["code"]` 可取到上述字段（SDK 行为，未实测）。

---

## 2. 推理错误码全表

来源：错误码页（1299023，更新 2026-08-18）「推理错误码」表，逐条照抄 Code / HTTP / 含义；「建议处理」为本文归纳。文档原文，未实测。

### 2.1 HTTP 400 · BadRequest —— 参数 / 内容审核

| Code | 含义（文档原文） | 建议处理 |
|---|---|---|
| `MissingParameter` | 请求缺少必要参数 | 对照 API 文档补参数；不可重试 |
| `InvalidParameter` | 请求包含非法参数 | 检查参数名 / 类型 / 枚举值；视觉模型下常见原因见第 9 节「InvalidParameter 与图片」 |
| `InvalidParameter`（message: `The parameter instructions ... caching is not supported for instructions`） | Responses API 中配置过 `instructions` 后，后续轮次无法配置 `Caching` | 去掉 `instructions` 或不用 caching |
| `InvalidParameter`（Lean 相关三条：`not compilable under Lean version %s` / `format ... not supported` / `/`） | 输入不是合法 Lean Code / 格式暂不支持 / 必须包含 theorem | 仅 Lean 证明类模型相关 |
| `InvalidParameter.{{Parameter}}` | 请求参数值不合法 | 按占位符里的参数名修正 |
| `InvalidParameter.TaskTypeConstraint` | 请求参数与模型判定的任务类型不兼容（Seedance），message 里有 `Issues: [0] ... [1] ...` | 按 Issues 逐条改 |
| `InvalidParameter.TaskTypeMismatch` | 指定的任务类型与 Seedance 从 prompt/输入识别的不一致 | 调整提示词和输入素材 |
| `InvalidParameter.UnsupportedParameter` | 参数 `{{Parameter}}` 在此推理接入点不可用 | 换模型 / 接入点，或删掉该参数 |
| `InvalidParameter.TosURLInvalid` | TOS URI 不合法 | 检查 `tos://` 路径 |
| `MissingParameter.{{Parameter}}` | 缺少必要参数 `{{Parameter}}` | 补参数 |
| `Duplicate.Tags.Key` | 对象的标签存在重复 Key | 去重 |
| `InvalidArgumentError`（message `MissingRole：Invalid message: ...`） | `messages` 里有消息体缺少 `role` | 每条消息都要有 `role` |
| `InvalidArgumentError.UnknownRole`（`Unknown the role of message`） | `role` 值不被支持，如 `user_` | 只用 `system` / `user` / `assistant` / `tool`；**`developer` 也不支持**，见第 5 节 |
| `InvalidArgumentError.UnknownRole`（`The Inference role not found`） | 指定的 `inference_role` 未在配置中定义 | 检查 inference_role 配置 |
| `InvalidArgumentError.InvalidImageDetail` | `image_url.detail` 只接受 `auto` / `high` / `low` | 修正枚举值 |
| `InvalidArgumentError.InvalidPixelLimit` | 自定义 `min_pixels` / `max_pixels` 无效（如 min > max 或超服务范围） | 修正像素范围 |
| `InvalidImageURL.EmptyURL` | 传入的图片 URL 为空 | 检查 `image_url.url` |
| `InvalidImageURL.InvalidFormat` | 无法解析图片：Base64 格式错误、数据损坏或格式不支持 | 检查 data URI 前缀与编码 |
| `OutofContextError` | 文本 + 图片编码后总 token 超过模型上下文 | 减图片张数 / 压缩图片 / 精简提示词 |
| `InvalidEndpoint.ClosedEndpoint` | 推理接入点已关闭或暂时不可用 | 稍后重试或联系接入点管理员 |
| `SensitiveContentDetected` | 输入文本可能包含敏感信息 | 换 prompt；不可重试 |
| `SensitiveContentDetected.SevereViolation` | 输入文本可能包含严重违规相关信息 | 同上 |
| `SensitiveContentDetected.Violence` | 输入文本可能包含激进行为相关信息 | 同上 |
| `InputTextSensitiveContentDetected` / `InputImageSensitiveContentDetected` / `InputVideoSensitiveContentDetected` / `InputAudioSensitiveContentDetected` | 输入文本 / 图像 / 视频 / 音频可能包含敏感信息 | 更换输入 |
| `OutputTextSensitiveContentDetected` / `OutputImageSensitiveContentDetected` / `OutputVideoSensitiveContentDetected` / `OutputAudioSensitiveContentDetected` | 生成的文字 / 图像 / 视频 / 音频可能包含敏感信息 | 更换输入内容后重试 |
| `InputTextSensitiveContentDetected.PolicyViolation` / `InputImage...PolicyViolation` / `InputVideo...PolicyViolation` / `InputAudio...PolicyViolation` | 输入可能涉及版权限制 | 更换输入 |
| `OutputVideoSensitiveContentDetected.PolicyViolation` / `OutputAudioSensitiveContentDetected.PolicyViolation` | 生成的视频 / 音频可能涉及版权限制 | 更换输入 |
| `InputImageSensitiveContentDetected.PrivacyInformation` / `InputVideoSensitiveContentDetected.PrivacyInformation` | 输入图片 / 视频可能包含真人 | 更换素材（图生视频 / 图生图常见） |
| `OutputImageSensitiveContentDetected.DeepFake` | 输出图片可能涉及伪造证件等内容风险 | 更换输入 |
| `InputTextRiskDetection` / `InputImageRiskDetection` / `OutputTextRiskDetection` / `OutputImageRiskDetection` | 火山引擎「风险识别」产品检测到敏感内容；message 含 `CSDRequestId` / `Label` / `SubLabel` | 用户自行接入了内容安全检测时出现；按 Label 处理 |
| `ContentSecurityDetectionError` | 火山引擎风险识别产品请求失败（`CSDcode` / `CSDmessage`） | 检查风险识别产品配置，可重试 |

### 2.2 HTTP 400 / 401 · 鉴权与账号

| HTTP | Type | Code | 含义 | 建议处理 |
|---|---|---|---|---|
| 400 | Forbidden | `InvalidSubscription` | Coding Plan 套餐未订阅或已过期。message：`Your account ({{account_identifier}}) does not have a valid coding plan subscription, or your subscription has expired. Please visit {{subscription_check_url}} ...` | 用了 `/api/coding` 入口但没有有效 Coding Plan；去控制台订阅 / 续费，或改用 `/api/v3` 后付费 |
| 401 | Unauthorized | `AuthenticationError` | API Key 或 AK/SK 缺失 / 校验未通过 | 检查 `Authorization: Bearer <key>`；Plan 入口检查是否用错 Key（第 5 节） |
| 401 | Forbidden | `InvalidAccountStatus` | 当前使用的账号异常 | 联系平台 |

### 2.3 HTTP 403 · Forbidden —— 权限 / 欠费 / 状态

| Code | 含义 | 建议处理 |
|---|---|---|
| `AccountOverdueError` | 账号欠费（余额 < 0） | 费用中心充值；代金券也需余额 ≥ 0 才能用（FAQ） |
| `AccessDenied` | 没有访问该资源的权限 | 检查 API Key 所属项目 / IP 白名单 / 模型限制（API Key 可限定 Model ID、接入点、IP） |
| `OperationDenied.ServiceNotOpen` | 模型服务不可用（未开通） | 控制台「开通管理」开通模型 |
| `OperationDenied.ServiceOverdue` | 账单已逾期 | 充值 |
| `OperationDenied.PermissionDenied` | 无权访问基础模型的配置 | IAM 权限 |
| `OperationDenied.InvalidState`（三种 message） | Context ID / 缓存 / File ID 处于非空闲 / 更新中状态 | 等状态变为可用再调 |
| `OperationDenied.UnsupportedPhase` | 操作目标处于特殊状态（不存在 / 被锁定） | 检查目标状态 |
| `OperationDenied.FileQuotaExceeded` | 文件存储额度耗尽 | 删除历史文件（Files API） |
| `OperationDenied.ArkAccessRoleNotFound` | 未对 TOS 资源授权 | 方舟项目配置 → 项目授权 |
| `OperationDenied.TosAccessDenied` | 无权访问 TOS bucket | 检查账号 / 项目对 bucket 的权限 |
| `OperationDenied.ConflictedValidationSet` / `.UnsupportedCustomizationType` / `.CustomizationNotSupported` | 精调：不能同时配验证集与取样百分比 / 模型或版本不支持该训练方法 | 精调任务参数 |

### 2.4 HTTP 404 · NotFound —— 模型 / 接入点

| Code | 含义 | 建议处理 |
|---|---|---|
| `InvalidEndpointOrModel.NotFound` | message：`The model or endpoint %s does not exist or you do not have access to it.` 模型或接入点不存在或无权访问 | 最常见 404。检查 `model` 字段格式与入口是否匹配（第 5 节） |
| `ModelNotOpen` | 账号未开通该模型（`Your account %s has not activated the model %s`） | 「开通管理」开通；Coding/Agent Plan 购买即开通，无需此步 |
| `NotFound.{{Parameter}}` | 指定资源找不到 | 检查 ID |
| `InvalidEndpointOrModel.ModelIDAccessDisabled` | 账号不允许用 Model ID 直调，必须用自定义接入点 `ep-` | 改用 Endpoint ID（企业账号策略） |
| `UnsupportedModel` | `The {{model_name}} model does not support the coding plan feature.` 当前模型不支持 Coding Plan | 换 Coding Plan 支持的 Model Name（第 5 节） |

### 2.5 HTTP 429 · TooManyRequests —— 限流 / 额度

| Code | 含义 | 可重试 | 建议处理 |
|---|---|---|---|
| `RateLimitExceeded.EndpointRPMExceeded` | 接入点 RPM 超限 | 是（退避） | 降 QPS / 提额 |
| `RateLimitExceeded.EndpointTPMExceeded` | 接入点 TPM 超限 | 是（退避） | 降并发 / 减输入长度 / 提额 |
| `ModelAccountRpmRateLimitExceeded` | 账户级该模型 RPM 超限 | 是 | 同上（Model ID 直调时的账户配额） |
| `ModelAccountTpmRateLimitExceeded` | 账户级该模型 TPM 超限 | 是 | 同上 |
| `APIAccountRpmRateLimitExceeded` | 账号对该接口的 RPM 超限（如 `GetApiKey` 临时 Key 接口限流很低） | 是 | 单例复用 client，勿频繁创建 |
| `ModelAccountIpmRateLimitExceeded` | 图片模型 IPM（Images Per Minute）超限 | 是 | 降图片生成频率 |
| `QuotaExceeded`（message `exhausted its free trial quota for the [%s] model`） | 免费试用额度耗尽 | 否 | 开通模型进入后付费 |
| `QuotaExceeded`（message `The request has exceeded the quota`） | 排队中任务数超限（视频生成等异步任务） | 是（等任务完成） | 控制在途任务数 |
| `QuotaExceeded`（message `You have exceeded the 5-hour/weekly/monthly usage quota. It will reset at {{reset_time}}.`） | **Plan 套餐 5 小时 / 周 / 月额度耗尽** | 等 `reset_time` | 见第 5 节 |
| `ServerOverloaded` | 服务资源紧张；`doubao-seed-1.8` 及更早模型触发突增流量限制时返回此码 | 是（退避 + 逐步爬坡） | 参考文档「突发流量处理最佳实践」（1848593） |
| `RequestBurstTooFast` | 请求量激增触发系统保护；`doubao-seed-2.0` 及之后模型返回此码（2026-02 公告：Seed 2.0 起由 `ServerOverloaded` 改为此码） | 是（放缓爬坡） | 逐步增加请求量 |
| `SetLimitExceeded` | 账号对该模型达到自设「推理限额」，服务已暂停 | 否 | 开通管理页调整限额或关闭「安心体验模式」 |
| `InflightBatchsizeExceeded` | 达到当前充值金额对应的最大并发数 | 是（降并发） | 充值解锁更大并发，或降并发 |
| `AccountRateLimitExceeded` | 请求超出 RPM / TPM 限制（通用） | 是 | 退避重试 |

### 2.6 HTTP 500

| Code | 含义 | 建议处理 |
|---|---|---|
| `InternalServiceError` | 内部系统异常 | 可重试；持续复现带 Request ID 提工单 |

公共错误码（火山引擎通用层，如签名错误）见 https://www.volcengine.com/docs/6369/68677 ⚠ 未纳入本地材料。

---

## 3. 精调错误码

| Code | 示例信息 | 说明与建议 |
|---|---|---|
| `InvalidData.MissingKey` | `Data format is not expected:column not found` | 数据集缺列，补全键值 |
| `InvalidData.UnknownKey` | `Wrong Key, parsing sample failed` | 数据中有错误 Key |
| `InvalidData.InvalidValue` | `Unsupported data type:, only pretrain, dialog, dialog-dpo and multimodal supported` / `Content is empty` | 数据集类型仅支持 `pretrain` / `dialog` / `dialog-dpo` / `multimodal`；content 不能为空 |
| `InvalidData.InvalidJsonl` | `not supported` / `No jsonl file available` | 文件须为 `.jsonl` |
| `InvalidData.InvalidJson` | `Expecting value: line 1 column 1 (char 0) in file at row` | 某行 JSON 解析失败 |
| `InvalidData` | `tos objects do not exist` | TOS 数据集路径不存在 |
| `UnknownError` | `service error occur, please contact customer service` | 平台错误，不可重试，提工单 |
| `InternalError` | `task failed, please check the logs` | 看日志后重试，仍失败提工单 |

---

## 4. Managed Agent 错误码（摘要）

Managed Agent（`arkcli agent` / Sessions / Events 接口）错误分两类：**HTTP 阶段**（同步返回，带状态码 + 结构化 body）和 **SSE 阶段**（`data.type = "session.error"` 事件，无 HTTP 状态码，只在 `RunFailed` / `SessionError` / SSE resume-lag 场景出现）。与通用推理错误码不同的项：

| HTTP | Code | 要点 |
|---|---|---|
| 400 | `InvalidAction` / `InvalidPayload` / `EmptyEvents` / `RuntimeRejected` / `MissingSessionModel` / `MissingSessionId` / `ManagedAgentsRequired` / `ManagedAgentsRejected` / `ManagedAgentsInvalidAgent` | create / events 阶段的协议校验；`EmptyEvents` 特指 `events` 数组为空 |
| 401 | `MissingHeader` / `MCPInvalidCredential` / `MCPNeedsReauth` | `Authorization: Bearer <token>` 缺失；出向 MCP 凭证失效 / 需重新 OAuth |
| 403 | `OperationDenied(.<cause>)` / `MCPNetworkDenied` | 子原因码指明商品未开通、子账号缺权限、实名未通过、欠费等；MCP host 不在出向白名单 |
| 404 | `PathNotFound` / `InvalidSession.NotFound` / `InvalidAgent.NotFound` / `InvalidEnvironment.NotFound` / `InvalidVault.NotFound` / `InvalidCredential.NotFound` / `InvalidMemoryStore.NotFound` / `InvalidFile.NotFound` / `ResourceNotFound` / `ManagedAgentNotOpen` / `NotSupportedMCPServer.NotFound` | 资源不存在或无权限；`ManagedAgentNotOpen` 需先在控制台开通 |
| 409 | `Conflict` / `ResourceConflict` / `SessionBusy` | `SessionBusy`：同一 session 已有在途回合，等待或先发 `user.interrupt` |
| 413 | `RequestTooLarge`（业务粒度） / `RequestBodyTooLarge`（传输粒度） | 拆分 / 压缩 |
| 424 | `UpstreamUnavailable` / `MCPInvalidResponse` | 客户侧上游（MCP server、IdP）不可达；`mcp_server_url` 指向了非 MCP 服务 |
| 429 | `APIAccountRpmRateLimitExceeded` / `SessionQuotaExceeded` | 活跃 session 数达配额，先 finish / delete |
| 499 | `RequestCanceled` | 客户端取消 |
| 500 / 502 | `InternalServiceError` / `SideEffectFailed` / `ManagedAgentsUnavailable` | 均可重试 |

SSE 阶段 `error.type` 枚举：`model_overloaded_error`、`model_rate_limited_error`、`model_request_failed_error`、`billing_error`、`unknown_error`（兜底，含 runtime 重试耗尽、Tool Service 致命错误、MCP 工具致命错误、SSE resume 位点超出保留窗口、消费滞后被断开等）。**程序只按 `error.type` 分类，`error.message` 仅展示。**

---

## 5. Plan 用户最常见的报错

按排查顺序排列。前四项互为因果：Base URL、Key、model 三者必须来自同一套入口。

### 5.1 Base URL 用错 → 没报错但被后付费扣钱
- 现象：请求成功，但 Coding / Agent Plan 额度不动，账单出现按 token 后付费费用。
- 原因：用了标准入口 `https://ark.cn-beijing.volces.com/api/v3`。Coding Plan 快速开始（1928261）原文：「请勿使用 `https://ark.cn-beijing.volces.com/api/v3`：该 Base URL 不会消耗您的 Coding Plan 额度，而是会产生额外费用。」Agent Plan 控制台同样提示。
- 正确值：Coding Plan `…/api/coding`（Anthropic 协议）/ `…/api/coding/v3`（OpenAI 协议）；Agent Plan `…/api/plan` / `…/api/plan/v3`。
- 注意：标准 `/api/v3` 用 Model Name（如 `doubao-seed-2.0-lite`）能否成功 ⚠ 文档未说明（标准入口文档只用带日期 Model ID 或 `ep-`）；若成功即被后付费计费。

### 5.2 Key 用错 → 401 `AuthenticationError`
- Coding Plan 用**方舟 API Key**（控制台「API Key 管理」）；Agent Plan 用**Agent Plan 专属 API Key**（Agent Plan 控制台「配置专属 API Key」）。Agent Plan 快速开始（2373738）原文：「为专属 API Key，其他方舟 API Key 如 Coding Plan API Key 无法在 Agent Plan 中使用。」
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：拿 Agent Plan Key 打 `https://ark.cn-beijing.volces.com/api/v3/chat/completions` 与 `/api/coding/v3/chat/completions` 均返回 HTTP **401**，原文 `{"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. Request id: ...","param":"","type":"Unauthorized"}}`——文档「其他 Base URL 无法在 Agent Plan 中使用」属实，报的是通用鉴权错误而不是「套餐不支持」类错误码。同一把 Key 打 `/api/plan/v3/chat/completions` 200。反向（方舟 API Key 打 `/api/plan`）未测，预期同样 401。
- Key 格式：历史 UUID 格式与新格式 `ark-<uuid>-<suffix>` 都有效（快速入门新手版 2272060）。复制时注意首尾空格。

### 5.3 无有效套餐 → 400 `InvalidSubscription`
- 用 `/api/coding` 入口但账号无 Coding Plan 或已过期。HTTP 400、Type `Forbidden`。Agent Plan 入口无套餐时的错误码 ⚠ 文档未说明（错误码表只有 coding plan 版本文案）。

### 5.4 模型不在套餐内 / 档位不支持 / 直填 `auto` → 404 `UnsupportedModel`（已实测）
- Coding Plan：文档明确 `UnsupportedModel`（`The {{model_name}} model does not support the coding plan feature.`，文档原文，未实测）。
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：Agent Plan 入口下列四种请求返回**同一个** HTTP 404 body：`{"error":{"code":"UnsupportedModel","message":"The requested model does not support the agent plan feature. Please refer to the documentation at https://www.volcengine.com/docs/82379/2366394 to select a compatible model. Request id: ...","param":"","type":""}}`（注意 `type` 为空串）：
  - `model: "doubao-seed-2.1-pro"`（套餐外模型）；
  - `model: "doubao-seed-1-8-251228"`（老的带日期 Model ID，Name 不在套餐内）；
  - Medium 档 `POST /contents/generations/tasks`，`model: "doubao-seedance-2.0-mini"`（Small / Medium 不支持视频，与套餐概览正文一致）；
  - `model: "auto"`（控制台「Model Name: auto」是错的；要走 Auto 路由填 `ark-code-latest` 并在控制台选 Auto，实测响应 `model: "auto"`）。
  错误码不区分「套餐外」「档位不够」「不存在」，排查时先对照套餐概览 2366394 的模型表。
- 带日期但 Name 在套餐内的 Model ID（如 `doubao-seed-2-0-lite-260428`）**不报错**：实测 200 但响应 `model` 为 `doubao-seed-2-0-lite-260215`——Plan 入口按 Name 路由并静默忽略版本号，见 §5.9。`ep-xxx` 接入点 ID 在 Plan 入口的返回 ⚠ 未测。
- Small 档请求 `kimi-k3`（Medium 及以上才有，产品更新公告 2026-07）未测（测试账号是 Medium）；按上面 Medium 档套餐外模型的行为，预期同样 404 `UnsupportedModel` ⚠ 待实测。
- OpenClaw 场景 404 `The model or endpoint xxx does not exist or you do not have access to it`：Coding Plan FAQ（2165245）指出常见原因是 `~/.openclaw/openclaw.json` 与 `~/.openclaw/agents/main/agent/models.json` 两处 baseUrl 不一致（后者优先级高），删掉后者重启 gateway。

### 5.5 额度耗尽 → 429 `QuotaExceeded`
- 错误码表原文：`QuotaExceeded` / `You have exceeded the 5-hour/weekly/monthly usage quota. It will reset at {{reset_time}}.` HTTP 429，Type `TooManyRequests`。
- 刷新规则（Coding Plan FAQ / Agent Plan 套餐概览）：5 小时限额按首次请求时间起以 5 小时为周期刷新；周限额每周一 00:00:00；月限额每订阅月第 1 日 00:00:00；Agent Plan 日限额（仅视觉模型等）每日 00:00:00。
- 未开「超额后付费」时额度耗尽**不会**扣其他资源包或余额，只能等刷新；Agent Plan 开了超额后付费则自动切到后付费，无需改 Base URL / Key / model（`auto` 模式、`glm-5.3`、`minimax-m3`、`kimi-k3`、`glm-5.3-flash`、图片 / 视频模型不支持超额后付费）。
- Agent Plan 额度（AFP）：Small 月 20,000 / 周 7,000 / 5h 2,000；Medium 100,000 / 35,000 / 10,000；Large 250,000 / 87,500 / 25,000；Max 500,000 / 175,000 / 50,000；日额度 = 月额度一半（仅部分模型 / Harness）。图片 / 视频 / 语音 / Harness 无 5 小时与周限额。
- Coding Plan 预估次数（Seed 2.0 Lite、Claude Code 未开 Agent Team）：Lite 5h ≈1,200 / 周 ≈9,000 / 月 ≈18,000；Pro ×5。
- Claude Code 后台遥测会走 `ANTHROPIC_BASE_URL` 静默消耗额度，设 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`（1928262 / 2373740）。

### 5.6 `developer` role → 400 `InvalidParameter`（已实测）
- 文档原文（Coding Plan FAQ 2165245）：`HTTP 400: The parameter messages.role specified in the request are not valid: invalid value: developer, supported values are: system, assistant, user, tool.`
- **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/chat/completions`，`messages[0].role = "developer"` → HTTP 400，原文 ``{"error":{"code":"InvalidParameter","message":"The parameter `messages.role` specified in the request are not valid: invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`. Request id: ...","param":"","type":"BadRequest"}}``。
- 原因：方舟 OpenAI 协议不支持 OpenAI 新版的 `developer` role。把 `developer` 改成 `system`；OpenClaw 在 **model 级**加 `"compat": {"supportsDeveloperRole": false}`（放 provider 级会报 `Unrecognized key: "compat"`）。
- 错误码是 `InvalidParameter`（不是错误码表里的 `InvalidArgumentError.UnknownRole`），`param` 为空串，程序判别用 `code == "InvalidParameter"` + message 里的 `messages.role`。

### 5.7 在非 AI 编程工具里直接调 Plan 入口
- Coding Plan 与 Agent Plan（文本 / 向量化模型）官方口径「不可用于 API 调用」，在非 AI 工具中使用「有可能被识别为滥用 / 违规，会导致订阅停用或账号封禁」。触发后的错误码 ⚠ 文档未说明（可能表现为 401 `InvalidAccountStatus` 或 400 `InvalidSubscription`）。

### 5.8 参数被该模型 / 该入口拒绝 → 400 `InvalidParameter`（已实测）
**已用真实 API 验证（2026-09-04，Agent Plan Medium）**，全部在 `/api/plan/v3`，HTTP 400、`code: "InvalidParameter"`，message 原文：

| 请求 | `message`（截去 Request id） | `param` | `type` |
|---|---|---|---|
| `glm-5.3` + `thinking: {"type":"disabled"}` | ``thinking.type `disabled` is not supported by this model`` | `""` | `BadRequest` |
| `glm-5.3` + `reasoning_effort: "none"` | ``reasoning_effort `none` is not supported by this model`` | `""` | `BadRequest` |
| `doubao-seed-2.0-lite` + `service_tier: "fast"` | ``The parameter `service_tier` specified in the request are not valid: fast service tier does not support coding plan.`` | `"service_tier"` | `BadRequest` |
| `POST /images/generations`，`doubao-seedream-5.0-lite` + `size: "1K"` | ``The parameter `size` specified in the request is not valid: size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'.`` | `""` | `""` |
| `POST /embeddings`（OpenAI 形态），`input` 传 `[{"type":"text","text":"a cat"},...]` 数组 | ``The parameter `input[0]` specified in the request are not valid: expected a string, but got `map[text:a cat type:text]` instead.`` | `"input[0]"` | `BadRequest` |

要点：
- 第三方模型（glm-5.3）不接受 `thinking.disabled` 与 `reasoning_effort: none`；要"关思考"只能 `reasoning_effort: "low"`（实测 200、`reasoning_tokens: 0`、无 `reasoning_content`）。豆包 `doubao-seed-2.0-lite` 的 `thinking.disabled` 正常生效。
- `service_tier: "fast"` 在 **Agent Plan** 入口报的却是 "coding plan" 文案，属服务端文案共用，不代表 Key / 入口配错。
- OpenAI 形态 `/embeddings` 的 `input` 只收字符串；含图片走 `/embeddings/multimodal`（见 `embeddings-speech.md` §2.3）。
- 图片 `size` 档位服务端枚举为小写 `2k/3k/4k`（见 `image-video.md` §2.3）。

### 5.9 不报错但扣钱的静默行为（已实测）
**已用真实 API 验证（2026-09-04，Agent Plan Medium）**，以下请求都是 HTTP 200，只有响应 `model` 字段能看出问题：
- **Anthropic 入口把 `claude-*` 模型名静默路由到 2.1-turbo**：`POST /api/plan/v1/messages`，`model: "claude-sonnet-4-5"` → 200，响应 `"model":"doubao-seed-2-1-turbo-260628"`（抵扣系数 2.5）。Claude Code 忘设 `ANTHROPIC_MODEL` 时默认就会发 `claude-*` 名，于是不报错、悄悄按 2.1-turbo 烧 AFP。务必显式设 `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL`，并在账单或响应 `model` 里核对。
- **带日期的 Model ID 被静默换版本**：`/api/plan/v3/chat/completions` 与 `/api/plan/v1/messages` 传 `model: "doubao-seed-2-0-lite-260428"` → 200，响应 `"model":"doubao-seed-2-0-lite-260215"`——Plan 入口按 Name 路由，版本号被忽略，拿不到你指定的版本。Plan 入口只写小写 Model Name。
- `ark-code-latest` 响应 `"model":"auto"`（控制台当前选 Auto），实际路由到哪个模型、按哪个系数扣费在响应里看不到，靠控制台用量页核对。
- （文档原文，未实测）标准入口 `/api/v3` 用对了 Key 时请求成功但走后付费，见 §5.1。

---

## 6. 速率限制

### 6.1 概念
- **RPM**（Requests Per Minute）与 **TPM**（Tokens Per Minute）按**模型**设定，按**账号**计（主账号 + 全部子账号合并）。在控制台「开通管理」查看；提额走客户经理或工单。
- **TPD**（每日 Token 限额）、**IPM**（图片模型每分钟图片数）、内容生成模型的并发任务数 / 创建任务 RPM、实时模型的并发连接数 / 单连接 CPM、TPM：见 `ListModelRateLimit` 返回字段。
- **预扣机制**：收到请求时按输入长度 + 预估输出长度预扣本窗口 TPM，所以「额度明明有剩余却限流」是正常现象（FAQ）。被限流的请求不进入模型生成，**不计费**。
- **接入点限流 vs 账户限流**：用 `ep-` 接入点调用时超限返回 `RateLimitExceeded.Endpoint{RPM,TPM}Exceeded`；用 Model ID 直调时返回 `ModelAccount{Rpm,Tpm}RateLimitExceeded`。
- **低充值账号并发限制**：未充值或历史充值低的账号高并发会被限制（`InflightBatchsizeExceeded`）；FAQ 建议预充值，或改用批量推理（夜间 0–8 点资源充足）。
- **突增流量保护**：Seed 1.8 及更早 → `ServerOverloaded`；Seed 2.0 及之后 → `RequestBurstTooFast`。需逐步爬坡。
- **TPM 保障包 / 模型单元**：付费保障 TPM 的方式，与上下文缓存、结构化输出不能同时使用（FAQ）。

### 6.2 Plan 的 TPM 口径
Agent Plan 套餐概览（2366394）只给定性描述：「Agent Plan 套餐满足正常开发需求的 TPM，超高 TPM 建议使用后付费 API」；Small 建议同时 1 个项目，Medium 1–2 个，Large / Max 2+ 个。**具体 RPM / TPM 数值 ⚠ 文档未说明**；Plan 入口触发限流时返回 `AccountRateLimitExceeded` 还是 `ModelAccount*RateLimitExceeded` ⚠ 待实测。Coding Plan 文档未提 TPM。

### 6.3 ListModelRateLimit —— 查询模型限流
**Endpoint**: `POST https://ark.cn-beijing.volcengineapi.com/?Action=ListModelRateLimit&Version=2024-01-01`（管控面，**仅支持 Access Key 签名鉴权**，Service `ark`、Region `cn-beijing`；API Key 不可用）
**用途**: 查当前账号各基础模型的默认 / 当前 RPM、TPM、TPD 等配额；判断是否已提额。

**请求参数**
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `FoundationModelNames` | string[] | 否 | 基础模型名称列表；为空返回全部 |

**响应字段**（`Items[]`）
| 字段 | 说明 |
|---|---|
| `FoundationModelName` | 基础模型名 |
| `DefaultRateLimit.{Rpm,Tpm,FastTpm,Ipm,LoraTpm}` | 默认配额；`FastTpm` = 低延迟（快速通道）TPM，`LoraTpm` = LoRA 推理 TPM |
| `CurrentRateLimit.{Rpm,Tpm,FastTpm,Ipm,LoraTpm}` | 当前配额（可能已提额） |
| `DefaultTpd` / `CurrentTpd` | 每日 Token 限额 |
| `ContentGenerationRateLimit.{ConcurrentRequests,ConcurrentRequestsFor4K,CreateTaskRpm,CreateTaskRpmFor4K,DeleteTaskRpm,ListTaskRpm}` | 视频 / 内容生成任务限制 |
| `RealtimeRateLimit.{ConcurrentConnections,CPMPerConnection,TPMPerConnection}` | 实时（语音）连接限制 |
| `TotalCount`（顶层） | 记录总数 |

**示例请求**（管控面 SDK 方式；自行签名见 Base URL 及鉴权页）
```python
# pip install volcengine-python-sdk ; 管控面走 AK/SK 签名，这里用官方通用 SDK 的 ark 服务
import os, volcenginesdkcore, volcenginesdkark
cfg = volcenginesdkcore.Configuration()
cfg.ak, cfg.sk, cfg.region = os.environ["VOLC_ACCESSKEY"], os.environ["VOLC_SECRETKEY"], "cn-beijing"
volcenginesdkcore.Configuration.set_default(cfg)
# 已在本机核实（2026-09-04，volcengine-python-sdk 5.0.48）：ARKApi 没有 list_model_rate_limit 方法，
# 需走通用签名调用 UniversalApi（Action 名与 body 照文档原样传），见 management-api.md §1
universal = volcenginesdkcore.UniversalApi(volcenginesdkcore.ApiClient(cfg))
info = volcenginesdkcore.UniversalInfo(method="POST", service="ark", version="2024-01-01",
                                       action="ListModelRateLimit", content_type="application/json")
resp = universal.do_call(info, {"FoundationModelNames": ["doubao-seed-2-1-pro"]})
print(resp)
```

```bash
# curl 需自行实现 HMAC-SHA256 签名（Service=ark, Region=cn-beijing），骨架：
curl -X POST 'https://ark.cn-beijing.volcengineapi.com/?Action=ListModelRateLimit&Version=2024-01-01' \
  -H 'Authorization: HMAC-SHA256 Credential=<AK>/<yyyymmdd>/cn-beijing/ark/request, SignedHeaders=host;x-content-sha256;x-date, Signature=<sig>' \
  -H 'Content-Type: application/json' -H 'Host: ark.cn-beijing.volcengineapi.com' \
  -H 'X-Content-Sha256: <sha256(body)>' -H 'X-Date: <yyyymmddThhmmssZ>' \
  -d '{"FoundationModelNames": []}'
```

---

## 7. 重试策略建议

| 错误 | 是否重试 | 建议 |
|---|---|---|
| 429 `RateLimitExceeded.*` / `ModelAccount*RateLimitExceeded` / `APIAccountRpmRateLimitExceeded` / `AccountRateLimitExceeded` / `ModelAccountIpmRateLimitExceeded` | 是 | 指数退避 + 抖动，起始 1–2 s；限流请求不计费，可放心重试；同时降并发 |
| 429 `ServerOverloaded` / `RequestBurstTooFast` | 是 | 退避后**逐步**爬坡，不要瞬时恢复原并发；长时间闲置的接入点首次调用也可能触发 |
| 429 `InflightBatchsizeExceeded` | 是 | 降并发；根因是充值额度，重试不解决 |
| 429 `QuotaExceeded`（排队任务数超限） | 是 | 等在途任务完成 |
| 429 `QuotaExceeded`（免费额度 / Plan 5h-周-月额度） | 否 | 前者开通模型；后者等 `reset_time` 或开超额后付费 |
| 429 `SetLimitExceeded` | 否 | 控制台改限额 |
| 500 `InternalServiceError` | 是 | 有限次重试（2–3 次），持续失败带 Request ID 提工单 |
| 400 `InvalidEndpoint.ClosedEndpoint` | 是（低频） | 接入点可能在冷启 / 被停，隔几十秒再试，仍失败找管理员 |
| 400 参数类 / 审核类（`Sensitive*`、`*RiskDetection`） | 否 | 修参数 / 换输入 |
| 401 / 403 / 404 | 否 | 修配置（Key、入口、model、开通、权限） |
| 网络层 `ArkAPIConnectionError` / 超时 | 是 | 见 FAQ 代理设置；深度思考模型建议 `timeout=1800` |

官方 SDK 默认 `max_retries=2`（Python / Go / Java），对瞬时故障自动重试；`openai` SDK 默认也是 2 次并自动处理 429 / 5xx 退避（SDK 行为，未实测其对方舟错误码的覆盖范围）。流式请求中途失败**不要**盲目整段重试：已生成 token 会计费（第 8 节）。

---

## 8. 计费说明

### 8.1 三种在线推理计费方式
| | 按 token 后付费 | TPM 保障包 | 模型单元（邀测） |
|---|---|---|---|
| 计费 | 按输入 / 输出 token 后付费，不调用不计费 | 购买 TPM 额度：按天预付费 / 按小时后付费，**不调用也收费** | 按「个」买专属算力：按月预付费 / 按小时后付费，不调用也收费 |
| 服务承诺 | 不承诺 TPM | 保障已购 TPM | 保障预置压测延迟 |
| 支持模型 | 全部 + 豆包 LoRA 精调模型 | 豆包、DeepSeek 系列 | 部分豆包及其精调模型 |
| 价格 | 低 | 中 | 高 |

### 8.2 按 token 后付费口径
- 计费项：**推理输入** `prompt_tokens`、**推理输出** `completion_tokens`；开上下文缓存后加 **缓存命中**（`cached_tokens`，单价低于 `prompt_tokens`）与 **缓存存储**（按小时、每自然小时内最大 token 数）。批量推理的透明前缀缓存命中按 `prompt_tokens` 单价 4 折。
- **免费额度**：新用户每个模型有免费额度，只抵扣在线推理按 token 后付费；批量推理与精调不支持免费额度。开通管理页可查剩余。耗尽后返回 429 `QuotaExceeded`（免费试用额度版）。
- **出账**：在线推理输入 / 输出 / 缓存命中为准实时出账（每 5 分钟出上一周期账单，滞后 5–10 分钟；Seedance 2.0 / 2.5 系列自 2026-07-01 起 30 秒）；缓存存储与精调按小时出账（滞后 1–2 小时）。出账后实时扣款。
- **报错 / 中断是否计费**（FAQ）：客户端中断 → 已输入 token 与服务端已生成 token 计费（非流式场景即使客户端没收到内容也计费）；服务端因审核中止流式 → 已生成部分计费；**RPM / TPM 超限的请求不计费**；批量推理 `errors.jsonl` 里的失败请求不计费。
- 分账：费用中心 → 分账账单 → 明细，按 Endpoint ID / 精调任务 ID / API Key 维度拆账。

### 8.3 欠费停服
- 2025-07-16 起新规则：**欠费 1 分钟即关停**（按小时后付费的模型单元 / TPM 保障包除外，有约 2 小时「欠费-关停」缓冲且期间继续计费）。可用额度（余额 + 代金券）< 待结算账单即视为欠费。
- 欠费 > 1 分钟：无可用资源包的模型服务立即关停；仍有资源包（含免费额度）的模型可继续用到耗尽。
- 报错表现：403 `AccountOverdueError` / `OperationDenied.ServiceOverdue`。代金券在欠费（余额 < 0）时无法抵扣，充值到 ≥ 0 才行。
- 欠费后仍出账 1–2 小时属正常（账单延迟）。要严格控费用「开通管理 → 推理限额」，达限额自动停服（对应 429 `SetLimitExceeded`）。可开「延期免停权益」延长免停时长。

### 8.4 Plan 计费与后付费的关系
- Coding Plan：套餐额度按次数估算，只在 `/api/coding*` 入口且 AI 编程工具内生效；不消耗资源包与余额。
- Agent Plan：AFP 积分抵扣，文本 `(输入 tokens × 系数 + 输出 tokens × 系数) / 10000`（auth.md 口径）；可开「超额后付费」，超额部分按标准「在线推理（常规）」价格出后付费账单，语音按 TTS 3 元/万字符、ASR 1 元/小时。
- 用 `/api/v3` 调 Plan 支持的模型 = 纯后付费，与套餐无关。

---

## 9. 常见问题中与开发相关的条目

来源：常见问题（1359411）、Coding Plan 常见问题（2165245）。

**SDK / 网络**
- `httpx.InvalidURL: Invalid port: ':'` 或 `ValueError: Unknown scheme for proxy URL URL('socks5h://xxx')`：系统代理干扰。Python SDK 传 `http_client=httpx.Client(proxies={'http://': None, 'https://': None})` 禁用代理；无效则 `export no_proxy=`。
- `ArkAPIConnectionError`（域名连接超时）：`ping ark.cn-beijing.volces.com`；不通则关 `HTTP_PROXY`（同上）；ping 通但 `Failed to resolve 'ark.cn-beijing.volces.com' ([Errno -3] Temporary failure in name resolution)` → 在 `/etc/resolv.conf`（文档原文如此，实为 hosts 语义）加 `ark.cn-beijing.volces.com ${ip}`。
- Windows `ERROR: Failed building wheel for volcengine-python-sdk`：长路径限制，注册表 `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1`。
- 判断在用 v3 还是旧版：HTTP 路径含 `/api/v3`；SDK import 路径含 `ark` 为 v3，含 `maas` 为 v1/v2。

**messages 规则**
- 不要求 user / assistant 交替（连续两个 `user` 可以）。
- 只传一条 `system` 消息也可以。
- 不支持 `developer` role（见 5.6）。

**InvalidParameter 与图片（视觉理解）**
- 图片下载超时：默认 5 s；国外站点 / 大图易超时，建议放 TOS 或压到 100 KB 以下。
- 图片服务器 403：对方 ACL 禁了火山源，检查 OSS / COS 安全策略。
- 格式校验：jpg/jpeg、png、gif、webp、bmp、dib、ico 按前 512 字节自动识别；TIFF（`image/tiff`）、SGI（`image/sgi`）、ICNS（`image/icns`）、JPEG2000（`image/jp2`）按 URL 的 `Content-Type` 校验，需在对象存储正确设置元信息。
- token 过大：减图片张数、压缩图片、精简提示词（对应 `OutofContextError`）。
- 视频 TS 格式：`ffmpeg -i input.ts -c copy output.mp4` 转 MP4。

**限流 / 并发**
- 额度有余仍限流：预扣机制（6.1）。
- 高并发被限：低充值账号防控策略；预充值或改批量推理。

**批量推理**
- 任务失败判定：输入文件格式错（某行非 JSON）在任务开始前检测；job 崩溃；超时。单条请求失败（如审核）只写入 error 文件夹，不导致整体失败。
- `CompletionWindow` 最大 / 默认 28 天；输出长度限制与在线推理相同，超限截断；已终止 / 失败任务的部分成功结果保留在 output 且计费。

**权限**
- 控制台提示「最低需要 ArkReadOnlyAccess」：子账号权限只有 `ArkExperienceAccess` 或做了项目隔离；在 IAM 加 `ArkReadOnlyAccess` 或更高、「限制到项目资源」选否。
- API Key 每主账号 50 个；Key 绑定创建时所在项目，不能跨项目访问；接入点跨项目迁移后原 Key 失效。

**Coding Plan 专项**（2165245）
- 购买即开通，无需开通模型 / 创建接入点。
- 多工具共享同一套餐额度。
- Claude Code 开思考：`~/.claude/settings.json` 的 `env` 加 `"CLAUDE_CODE_EXTRA_BODY": "{\"thinking\":{\"type\":\"enabled\"}}"`；OpenCode 在模型 `options` 加 `{"thinking": {"type": "enabled"}}`。
- OpenClaw 图片不识别：模型 `input` 要含 `"image"`，并在 `agents.defaults.imageModel.primary` 指定模型。
- OpenClaw `gateway connect failed: Error: pairing required`：删 `~/.openclaw/devices` 与 `~/.openclaw/identity`，`openclaw gateway install --force && openclaw gateway start`。

---

## 来源页面
| 标题 | URL | 文档更新时间 |
|---|---|---|
| 错误码 | https://www.volcengine.com/docs/82379/1299023 | 2026-08-18 |
| 常见问题 | https://www.volcengine.com/docs/82379/1359411 | 2026-07-07 |
| 模型服务计费说明 | https://www.volcengine.com/docs/82379/1544681 | 2026-09-02 |
| ListModelRateLimit - 查询模型限流 | https://www.volcengine.com/docs/82379/2612140 | 2026-08-20 |
| Coding Plan 个人版 · 常见问题 | https://www.volcengine.com/docs/82379/2165245 | 2026-08-24 |
| Coding Plan 个人版 · 快速开始 | https://www.volcengine.com/docs/82379/1928261 | 2026-08-28 |
| Coding Plan 个人版 · 套餐概览 | https://www.volcengine.com/docs/82379/1925114 | 2026-08-31 |
| Agent Plan 个人版 · 快速开始 | https://www.volcengine.com/docs/82379/2373738 | 2026-08-28 |
| Agent Plan 个人版 · 套餐概览 | https://www.volcengine.com/docs/82379/2366394 | 2026-08-31 |
| Agent Plan 个人版 · 超额后付费规则 | https://www.volcengine.com/docs/82379/2516284 | 2026-08-31 |
| 产品更新公告 | https://www.volcengine.com/docs/82379/1159177 | 2026-08-05 |
| Base URL 及鉴权 | https://www.volcengine.com/docs/82379/1298459 | 2026-06-23 |
| 获取 API Key 并配置 | https://www.volcengine.com/docs/82379/1541594 | 2026-04-27 |
| 快速入门(新手版) | https://www.volcengine.com/docs/82379/2272060 | 2026-07-20 |
| 同声传译 API（error 事件结构） | https://www.volcengine.com/docs/82379/1394617 | 2026-08-13 |
| 图片生成流式响应事件（流式 error 结构） | https://www.volcengine.com/docs/82379/1824137 | 2026-07-24 |
