# 错误码、限速、计费与工具接口

> 状态：文档草稿，基于 2026-09-03 抓取的 platform.moonshot.cn/docs 官方文档 + /docs/openapi.json 撰写，**尚未用真实 API 调用验证**。

## 1. 错误响应结构

所有接口失败时返回：
```json
{"error": {"type": "content_filter", "message": "The request was rejected because it was considered high risk", "code": "..."}}
```
（`code` 字段在 OpenAPI 里有、错误码页面示例里没有——以实际响应为准。）OpenAI SDK 会把它抛成 `openai.BadRequestError` 等异常，`e.body["error"]["type"]` 可取到类型。

## 2. 错误码表（来源: docs/api/errors）

| HTTP | error.type | 典型 message / 场景 | 处理 |
|---|---|---|---|
| 400 | `content_filter` | The request was rejected because it was considered high risk | 输入或输出触发安全审查，改提示词 |
| 400 | `invalid_request_error` | 格式错误 / 缺必填 / 类型非法 | 对照接口文档检查请求体（**包括传了固定值参数如 temperature**） |
| 400 | `invalid_request_error` | Input token length too long | 输入超上下文，缩短或换更大上下文模型 |
| 400 | `invalid_request_error` | prompt tokens + max_tokens 超过模型规格 | 减小 `max_completion_tokens` |
| 400 | `invalid_request_error` | Invalid purpose: xxx, only `file-extract`, `batch`, `batch_output`, `lambda`, `image` and `video` accepted | 文件 purpose 不合法 |
| 400 | `invalid_request_error` | File size is too large, max file size is 100MB | 拆分/压缩 |
| 400 | `invalid_request_error` | File size is zero | 文件为空 |
| 400 | `invalid_request_error` | 上传文件总数超过上限 | 删除旧文件（上限 1000 个） |
| 401 | `invalid_authentication_error` | Invalid Authentication | Key 无效或 header 格式错 |
| 401 | `incorrect_api_key_error` | Incorrect API key provided | 未提供或 Key 错误；**中国站 platform.kimi.com 与国际站 platform.kimi.ai 的 Key/余额完全隔离，混用 401** |
| 403 | `permission_denied_error` | The API you are accessing is not open / You are not allowed to get other user info / Your IP is not allowed to access this organization | 接口未开放 / 越权 / IP 不在白名单 |
| 404 | `resource_not_found_error` | 模型不存在或无权限 | 检查 model 拼写；**已下线模型（moonshot-v1-*、kimi-k2.5、kimi-k2-* 等）返回 404** |
| 429 | `engine_overloaded_error` | The engine is currently overloaded, please try again later | 看 `Retry-After`，指数退避 |
| 429 | `exceeded_current_quota_error` | 欠费/停用 或 token 额度不足 | 查余额、充值 |
| 429 | `rate_limit_reached_error` | 组织级并发 / RPM / TPM / TPD 限制 | 降并发、等待、提升等级 |
| 499 | `client_closed_request` | 客户端提前断开 | 检查代理/超时/KeepAlive |
| 500 | `server_error` / `unexpected_output` | 服务端错误 | 重试；持续出现带 `request_id` 联系 api-service@moonshot.ai |
| 503 | `server_unavailable` | 暂不可用 | 稍后重试 |
| 504 | （网关 HTML 页面，非 JSON） | 服务端 900 秒无响应 | **长请求改用 `stream: true`** |

排障顺序（来源: docs/guide/troubleshooting）：
1. 401/404 → 先确认 Key 来自"开放平台"而非 Kimi Code / Kimi 会员（三者 Key 与余额不互通），再确认站点（cn vs ai），再用同一个 Key 调 `GET /v1/models` 看目标模型在不在列表里。Claude Code 里模型别名是 `kimi-k3[1m]`，直连 API 用 `kimi-k3`。
2. 429 → 看 `error.type` 区分过载 / 限速 / 欠费。**OpenAI SDK 默认自动重试**，一次操作可能放大为多次请求占用限速额度；因 429 中断的请求不扣费。
3. 输出被截断 → 看 `finish_reason == "length"`，增大 `max_completion_tokens` 或用 Partial Mode 续写。
4. 客户端没显示结果但扣费了 → 服务端可能已完成；核对 HTTP 状态、`request_id`、`usage`、客户端是否自动重试。

## 3. 速率限制（来源: docs/pricing/limits, docs/introduction）

按**累计充值金额**分级（代金券不计入）：

| 等级 | 累计充值 | 并发 | RPM | TPM | TPD |
|---|---|---|---|---|---|
| Tier0 | ¥0 | 1 | 3 | 500,000 | 1,500,000 |
| Tier1 | ¥50 | 15 | 100 | 2,000,000 | 无限 |
| Tier2 | ¥100 | 40 | 100 | 3,000,000 | 无限 |
| Tier3 | ¥500 | 50 | 200 | 3,000,000 | 无限 |
| Tier4 | ¥5,000 | 60 | 200 | 4,000,000 | 无限 |
| Tier5 | ¥20,000 | 100 | 300 | 5,000,000 | 无限 |

要点：
- 限速在**用户级**而非 Key 级，且**所有模型共享**同一份额度。
- 网关计算 TPM/TPD 时，**如果请求带了 `max_completion_tokens`，就按 `prompt_tokens + max_completion_tokens` 预扣**（计费仍按实际用量）。K3 默认 `max_completion_tokens=131072`，在 Tier0（TPM 50 万）下少量请求就可能触发 TPM——按需把 `max_completion_tokens` 设小。
- 集群高负载时平台可临时调整限速；触发风控限速后无法解除。
- 新用户 15 元代金券不能用于 `kimi-k3`；充值 ≥10 元后解锁 K3（来源: docs/guide/troubleshooting）。

建议的重试策略：对 `engine_overloaded_error` / `rate_limit_reached_error` / 5xx 做指数退避（尊重 `Retry-After`）；对 `exceeded_current_quota_error`、400、401、403、404 **不要重试**。

## 4. 计费概念（来源: docs/pricing/chat）

- Input 与 Output 均按 token 计费；上下文缓存命中的输入 token 有单独（更低）单价，`usage.cached_tokens` 给出命中数。
- 通过 file-extract 抽取后放入对话的文档内容按输入 token 计费。
- K3 不按上下文长度分段计价，统一单价。
- 各模型具体单价在 `docs/pricing/chat-k3`、`chat-k27-code`、`chat-k26`、`pricing/batch`、`pricing/tools` 页面（**本草稿未抓取这些页面，单价请现查**）。

## 5. 工具类接口

### 列出模型
**Endpoint**: `GET /v1/models`
```bash
curl https://api.moonshot.cn/v1/models -H "Authorization: Bearer $MOONSHOT_API_KEY"
```
```python
for m in client.models.list().data:
    print(m.id)          # SDK 对象只暴露标准字段；扩展字段用 m.model_extra 或 with_raw_response
```
响应元素含扩展字段：`context_length`、`supports_image_in`、`supports_video_in`、`supports_reasoning`（OpenAPI 定义）。用它确认当前 Key 能访问哪些模型。

### 查询余额
**Endpoint**: `GET /v1/users/me/balance`（OpenAI SDK 没有对应方法，用 requests）
```python
import os, requests
r = requests.get("https://api.moonshot.cn/v1/users/me/balance",
                 headers={"Authorization": f"Bearer {os.environ['MOONSHOT_API_KEY']}"})
print(r.json())
# {"code": 0, "data": {"available_balance": 49.5, "voucher_balance": 0.0, "cash_balance": 49.5}, "scode": "0x0", "status": true}
```
`available_balance ≤ 0` 时无法调用推理接口；`cash_balance` 可为负（欠费），此时 `available_balance == voucher_balance`。响应外层是 `code/data/scode/status` 包装，不是 OpenAI 风格。

### 估算 Token 数
**Endpoint**: `POST /v1/tokenizers/estimate-token-count`
**用途**: 请求前估算输入 token（含图片/视频动态 token）；输入结构与 chat/completions 一致（`model` + `messages`）。
```python
r = requests.post("https://api.moonshot.cn/v1/tokenizers/estimate-token-count",
    headers={"Authorization": f"Bearer {os.environ['MOONSHOT_API_KEY']}"},
    json={"model": "kimi-k3", "messages": [{"role": "user", "content": "你好，1+1等于多少？"}]})
print(r.json()["data"]["total_tokens"])
```
`model` 枚举：`kimi-k3`、`kimi-k2.7-code`、`kimi-k2.7-code-highspeed`、`kimi-k2.6`。响应 `{"data": {"total_tokens": N}}`。最佳实践：先估算 prompt tokens，再据此设置 `max_completion_tokens`（上限 = 上下文窗口 − prompt_tokens）。

### 校验请求签名
**Endpoint**: `POST /v1/signatures/verify`
**用途**: 证明某次请求确实由 Kimi API 处理、且用的是指定模型（防中间层偷换模型）。流程：
1. 调 Chat/Responses/Messages 时带 header `X-Msh-Request-Nonce: <uuid4>`（只允许一个非空值；值非法时请求照常执行但不返回签名头）。
2. 响应头拿 `Msh-Request-Timestamp`（Unix 毫秒）和 `Msh-Request-Signature`（`reqsigv1_` 前缀）。
3. POST 校验：
```python
import os, uuid, requests
from openai import OpenAI
client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

nonce, model = str(uuid.uuid4()), "kimi-k3"
raw = client.chat.completions.with_raw_response.create(
    model=model, messages=[{"role": "user", "content": "你好"}],
    extra_headers={"X-Msh-Request-Nonce": nonce})
ts, sig = int(raw.headers["Msh-Request-Timestamp"]), raw.headers["Msh-Request-Signature"]

ok = requests.post("https://api.moonshot.cn/v1/signatures/verify",
    headers={"Authorization": f"Bearer {os.environ['MOONSHOT_API_KEY']}"},
    json={"nonce": nonce, "timestamp": ts, "model": model, "signature": sig}).json()
print(ok)   # {"valid": true}
```
签名只证明"该时间点 Kimi 接受了这个 nonce + model"，不证明请求成功或响应完整；服务端不记录 nonce，重放同一组参数仍返回 `valid: true`，防重放要自己做。

来源: docs/api/list-models, balance, estimate, signatures-verify, schema utilities/billing/models

---

## 待验证疑点

- **[文档不一致] 文件 `purpose` 合法值**：错误码页说 `file-extract, batch, batch_output, lambda, image, video`，OpenAPI 枚举只有 `file-extract, image, video, batch`。`batch_output`/`lambda` 是否可由用户上传、还是仅系统生成，需实测。
- 错误响应里 `error.code` 字段是否真的存在（OpenAPI 有、错误页示例无）。
- `GET /v1/models` 的扩展字段（`context_length`、`supports_*`）是否真的返回；OpenAI SDK 是否会静默丢弃它们。
- **限速按 `max_completion_tokens` 预扣**：需实测 Tier0/Tier1 账号带 `max_completion_tokens=131072` 连续发几次是否 429，以及不传时按什么值预扣（K3 默认 131072？）。
- 传了固定值参数（`temperature=0.6`）到底返回哪个 `error.type` 和 message 原文——这是最常见的"OpenAI 直觉"错误，需要精确的报错文案。
- 调用已下线模型（`moonshot-v1-8k`）实际的 `error.type`/message 原文。
- 429 的 `Retry-After` 头是否总是返回。
- `estimate-token-count` 是否支持带 `tools` 的请求（schema 只有 model+messages）；对 `ms://` 文件引用是否可估算。
- 余额接口对国际站 Key 的行为、`scode` 字段含义。
- 各模型单价（本次未抓 pricing/chat-k3 等页面）。
