> 内容整理自 platform.kimi.com/docs（抓取于 2026-09-03），**尚未用真实 API 调用验证**；实际报错优先信任 API。

# Kimi API 错误码、限速与排障

来源页：`/docs/api/errors`、`/docs/pricing/limits`、`/docs/guide/troubleshooting`、`/docs/introduction`。鉴权与 base_url 见 `auth.md`（`Authorization: Bearer $MOONSHOT_API_KEY`，`https://api.moonshot.cn/v1`）。

## 目录

1. [错误响应结构](#1-错误响应结构)
2. [错误码总表（按 HTTP 状态码）](#2-错误码总表按-http-状态码)
3. [中国站 / 国际站 Key 隔离](#3-中国站--国际站-key-隔离)
4. [账户等级与限速](#4-账户等级与限速)
5. [重试策略](#5-重试策略)
6. [问题排查清单](#6-问题排查清单)
7. [Python 示例：按 error.type 分支处理并退避重试](#7-python-示例按-errortype-分支处理并退避重试)
8. [与 OpenAI 直觉不同的点](#8-与-openai-直觉不同的点)

---

## 1. 错误响应结构

HTTP 200 表示成功；4xx / 5xx 表示失败，响应体为统一 JSON：

```json
{
    "error": {
        "type": "content_filter",
        "message": "The request was rejected because it was considered high risk"
    }
}
```

- 只有 `type` 与 `message` 两个字段；文档未提及 `code` / `param` 字段（OpenAI 风格的 `error.code` 不要依赖）。
- **例外：504** 由网关返回 **HTML 超时页面**而不是 JSON，`r.json()` 会抛异常，需先判断状态码再解析。
- **499** 是服务端记录的"客户端已断开"状态，客户端一般拿不到这个响应，表现为本地 Connection / Timeout 异常。

## 2. 错误码总表（按 HTTP 状态码）

`/docs/api/errors` 的表格里有多行"典型 message"列实际填的是原因说明、message 原文缺失；这些行统一标 `⚠ 文档未说明`，不要拿说明文字去做字符串匹配。

### 400 — 请求错误

| HTTP | error.type | 典型 message | 原因 | 处理 |
|---|---|---|---|---|
| 400 | `content_filter` | `The request was rejected because it was considered high risk` | 输入**或模型输出**触发内容安全审查 | 修改提示词、缩小请求范围、移除可能误判的内容后再试；平台不提供命中的具体规则 |
| 400 | `invalid_request_error` | ⚠ 文档未说明 | 请求格式错误、缺少必填参数或参数类型非法 | 对照接口文档检查请求体 |
| 400 | `invalid_request_error` | `Input token length too long` | 输入 tokens 超过模型最大上下文 | 缩短输入或换更大上下文模型（`kimi-k3` 1M） |
| 400 | `invalid_request_error` | ⚠ 文档未说明 | `prompt_tokens + max_tokens` 超过模型规格 | 减小 `max_completion_tokens`（`max_tokens` 已弃用）或换模型 |
| 400 | `invalid_request_error` | ``Invalid purpose: xxx, only `file-extract`, `batch`, `batch_output`, `lambda`, `image` and `video` accepted`` | 文件上传 `purpose` 不合法 | 改为上述六个取值之一 |
| 400 | `invalid_request_error` | `File size is too large, max file size is 100MB, please confirm and re-upload the file` | 上传文件超过 100MB | 压缩或拆分后重传 |
| 400 | `invalid_request_error` | `File size is zero, please confirm and re-upload the file` | 上传文件大小为 0 | 检查文件是否损坏或为空 |
| 400 | `invalid_request_error` | ⚠ 文档未说明 | 上传文件总数超过上限（上限数值 ⚠ 文档未说明） | 删除不再使用的早期文件后重试 |

### 401 — 认证错误

| HTTP | error.type | 典型 message | 原因 | 处理 |
|---|---|---|---|---|
| 401 | `invalid_authentication_error` | `Invalid Authentication` | API Key 无效或格式错误；**最常见是用错平台的 Key**（`.ai` 的 Key 打到 `.cn` 端点） | 检查 `Authorization: Bearer <key>` 与 Key 所属平台，见第 3 节 |
| 401 | `incorrect_api_key_error` | `Incorrect API key provided` | 未提供 API Key 或 Key 错误 | 确认 `MOONSHOT_API_KEY` 已设置且是开放平台的 Key（不是 Kimi Code / Kimi 会员的） |

### 403 — 权限错误

| HTTP | error.type | 典型 message | 原因 | 处理 |
|---|---|---|---|---|
| 403 | `permission_denied_error` | `The API you are accessing is not open` | 该 API 暂未对当前账号开放 | 联系平台 / 等待开放 |
| 403 | `permission_denied_error` | `You are not allowed to get other user info` | 试图访问其他用户信息 | 检查接口权限范围 |
| 403 | `permission_denied_error` | `Your IP is not allowed to access this organization` | 调用 IP 不在组织白名单内（国际站常见） | 联系管理员添加 IP |

### 404 — 资源不存在

| HTTP | error.type | 典型 message | 原因 | 处理 |
|---|---|---|---|---|
| 404 | `resource_not_found_error` | ⚠ 文档未说明 | 模型不存在（含已下线的 `moonshot-v1-*`、`kimi-k2.5`、`kimi-k2-*`、`kimi-latest`），或当前账号无权访问该模型（如未充值就调 `kimi-k3`） | 检查 `model` 拼写；用同一 Key 调 `GET /v1/models` 看目标模型是否在列表里；检查账户 tier / 余额 |

> 若看到的是 `model_not_found`，那是 **OpenAI 服务器**返回的：OpenAI SDK 没设 `base_url`，请求根本没到 Kimi。设 `base_url="https://api.moonshot.cn/v1"`。

### 429 — 速率限制 / 额度不足

429 不是单一原因，**先看 `error.type`**：

| HTTP | error.type | 典型 message | 原因 | 处理 |
|---|---|---|---|---|
| 429 | `engine_overloaded_error` | `The engine is currently overloaded, please try again later` | 服务节点负载高（高峰期容量压力），与你的账户无关 | 按 `Retry-After` 等待、降低并发、指数退避重试；**充值 / 升 Tier 不能消除** |
| 429 | `exceeded_current_quota_error` | ⚠ 文档未说明 | 账户欠费或已停用 | 检查余额与账单 |
| 429 | `exceeded_current_quota_error` | ⚠ 文档未说明 | 账户 token 额度不足（含代金券失效） | 调查询余额接口（文档 `/docs/api/balance`，路径未在本材料中给出）看 `available_balance`，充值后再试 |
| 429 | `rate_limit_reached_error` | ⚠ 文档未说明 | 触发组织级**并发**限制 | 降低并发或等待指定时间后重试 |
| 429 | `rate_limit_reached_error` | 片段：`Your account reached max request`（完整原文 ⚠ 文档未说明） | 触发组织级 **RPM** 限制；常因 SDK 自动重试放大请求数 | 按响应提示等待后重试；Tier0 注意关掉 SDK 自动重试 |
| 429 | `rate_limit_reached_error` | `Your account {uid}<{ak-id}> request reached TPM rate limit, current:{current_tpm}, limit:{max_tpm}` | 触发组织级 **TPM** 限制（按 prompt + `max_completion_tokens` 预估计数） | 降低频率 / 显式设小 `max_completion_tokens` / 升级 tier |
| 429 | `rate_limit_reached_error` | ⚠ 文档未说明 | 触发组织级 **TPD** 限制（仅 Tier0 有 TPD 上限） | 次日恢复或充值升级 |

- 因 429 中断的请求**不扣费**。
- `rate_limit_reached_error` 的 message 里 `{uid}<{ak-id}>` 与 `limit` 可以用来确认"到底是哪个账号、哪把 Key 在打"——若 limit 与后台 Tier 不符，八成是混用了别人 / 别的账号的 Key。

### 499 / 500 / 503 / 504 — 连接与服务端错误

| HTTP | error.type | 典型 message | 原因 | 处理 |
|---|---|---|---|---|
| 499 | `client_closed_request` | ⚠ 文档未说明 | 客户端在服务端返回前断开：流式响应被中间代理切断、用户主动取消、本地超时太短 | 检查 KeepAlive、SDK / 代理超时设置；注意服务端可能已完成并计费 |
| 500 | `server_error` | ⚠ 文档未说明 | 服务端内部错误 | 稍后重试；持续出现则附 `request_id` 联系 api-service@moonshot.ai |
| 500 | `unexpected_output` | ⚠ 文档未说明 | 服务端内部错误（模型输出异常） | 同上 |
| 503 | `server_unavailable` | ⚠ 文档未说明 | 服务暂时不可用，通常与节点扩容 / 维护有关 | 稍后重试 |
| 504 | （无 JSON；网关 HTML 页 `504 Gateway Time-out`） | `504 Gateway Time-out` | 非流式长请求等待时间过长，网关超时 | 改用 `stream=True`；见下方超时时长的矛盾说明 |

⚠ 文档自相矛盾 —— 504 的触发时长：`/docs/api/errors` 说"服务端 **900 秒**无响应，网关返回 HTML 超时页面"；`/docs/introduction#处理响应` 说"通常我们会设置一个 **2 小时**的超时时间，单个请求超过这个时间返回 504"。两处都写在这里；无论哪个是真的，结论一致：长生成请求用流式。

## 3. 中国站 / 国际站 Key 隔离

| | 中国站 | 国际站 |
|---|---|---|
| 控制台 | `platform.kimi.com` | `platform.kimi.ai` |
| base_url | `https://api.moonshot.cn/v1` | `https://api.moonshot.ai/v1` |
| 账户 / 余额 / API Key | 完全独立 | 完全独立 |

- 混用返回 **401 `invalid_authentication_error`**。收到 401 第一件事就是核对 Key 与端点是否同一平台。
- 另外三层隔离也常被混淆：**开放平台 API Key ≠ Kimi Code Key ≠ Kimi 会员权益**，付费方式、余额和 Key 均不互通；把其他产品的 Key 填到开放平台端点会报 401 或 404。
- 国际站有组织级 IP 白名单，IP 不在白名单返回 403 `Your IP is not allowed to access this organization`。

## 4. 账户等级与限速

限速按**累计充值金额**分级（代金券不计入；新用户 15 元代金券不能用于 `kimi-k3`，K3 需实际充值 ≥ 10 元）：

| 用户等级 | 累计充值金额 | 并发 | RPM | TPM | TPD |
|---|---|---|---|---|---|
| Tier0 | ¥ 0 | 1 | 3 | 500,000 | 1,500,000 |
| Tier1 | ¥ 50 | 15 | 100 | 2,000,000 | Unlimited |
| Tier2 | ¥ 100 | 40 | 100 | 3,000,000 | Unlimited |
| Tier3 | ¥ 500 | 50 | 200 | 3,000,000 | Unlimited |
| Tier4 | ¥ 5,000 | 60 | 200 | 4,000,000 | Unlimited |
| Tier5 | ¥ 20,000 | 100 | 300 | 5,000,000 | Unlimited |

概念：

- **并发**：同一时间最多同时处理的请求数。**RPM**：每分钟请求数。**TPM**：每分钟 token 数。**TPD**：每天 token 数。
- 四个维度任一先到即触发 429（例：RPM 20 时发 20 个各 100 token 的请求就被限，即使 TPM 远未用满）。
- **TPM 的计数方式**：按 `prompt tokens + 请求里的 max_completion_tokens` 预估，**不看实际生成量**；没传 `max_completion_tokens` 就用模型默认值计。`kimi-k3` 的默认 `max_completion_tokens` 为 131072，所以 Tier0（TPM 500,000）不显式设 `max_completion_tokens` 时，每个 K3 请求都按 ≥131k 计（推导自两处文档，⚠ 尚未实测）。计费才按实际生成 token。
- 限速作用范围：`/docs/introduction` 说"在**用户级别**而非密钥级别实施"，`/docs/api/errors` 说"**组织级**"并发 / RPM / TPM / TPD —— ⚠ 文档自相矛盾（也可能只是措辞不同）。共同点：**不是按 Key 分的**，多建 Key 不能扩额度。
- 所有模型**共享**同一套限速。
- 集群到容量上限时平台可临时下调各类限速；账户被判定异常行为会触发风控限速，**触发后无法解除**。

## 5. 重试策略

| 情况 | 该不该重试 | 怎么做 |
|---|---|---|
| 429 `engine_overloaded_error` | 重试 | 优先读 `Retry-After` 响应头等待；没有则指数退避（如 1s 起、×2、封顶 30–60s，加抖动）；同时**降并发** |
| 429 `rate_limit_reached_error`（并发 / RPM / TPM） | 重试 | 按 message 提示等待；RPM / TPM 是分钟窗口，退避不要短于几秒；文档未说明这类响应是否带 `Retry-After` ⚠ 文档未说明 |
| 429 `rate_limit_reached_error`（TPD） | 当天别重试 | 次日恢复；或充值到 Tier1+ 取消 TPD 上限 |
| 429 `exceeded_current_quota_error` | 不重试 | 充值 / 处理欠费后再发；重试只会继续 429 |
| 500 `server_error` / `unexpected_output`、503 `server_unavailable` | 重试（有限次） | 指数退避，2–3 次仍失败则记录 `request_id` 上报 |
| 504（HTML）、本地 Connection / Timeout | 先改流式再重试 | 非流式长请求先切 `stream=True`；注意服务端可能已经完成并计费，幂等性自己保证 |
| 400 `content_filter` | 不原样重试 | 输出侧也可能触发，修改 / 缩小输入后再试 |
| 400 其他 `invalid_request_error`、401、403、404 | 不重试 | 修请求 / Key / 模型名 |

SDK 自动重试的坑：OpenAI SDK 默认对连接错误、408、409、429、>=500 自动重试 2 次（一次操作 = 最多 3 次请求），全部计入 RPM。**Tier0 RPM 只有 3，一次失败请求就把整分钟额度耗光**。建议 `OpenAI(max_retries=0)` 自己控制重试；排查限速问题时先查客户端实际发了几次请求。

## 6. 问题排查清单

按症状查（覆盖 `/docs/guide/troubleshooting` 全部条目）：

| 症状 | 排查 / 结论 |
|---|---|
| 401 / 404 / permission denied | 依次：① Key 来自哪个产品（开放平台 ≠ Kimi Code）；② Key 所属区域与端点一致（`.com`↔`.cn`，`.ai`↔`.ai`）；③ 有可用余额、代金券支持目标模型；④ 同一 Key 调 `GET /v1/models` 看模型是否在列表；⑤ 模型名与接入方式匹配（API / Codex 用 `kimi-k3`，Claude Code 用别名 `kimi-k3[1m]`）；⑥ 清理旧环境变量、代理、CC Switch 等本地路由里的旧配置 |
| 充值后仍 429 | 看 `error.type`：过载→退避；限速→降频或升 Tier；额度→查 `available_balance` 再充值。另查 SDK 自动重试是否放大了请求数 |
| 报错里的 TPM / RPM limit 与后台 Tier 不符 | 几乎都是用错 Key（别人给的 Key、多账号混用）；对照 message 里的 `{uid}<{ak-id}>` |
| 一分钟只调一次却报 `Your account reached max request` | SDK 自动重试 ×3 计入 RPM，Tier0 直接打满；设 `max_retries=0` |
| `model_not_found` | 没设 `base_url`，请求打到了 OpenAI |
| `content_filter` | 输入或**输出**含敏感内容；平台不给具体规则；经第三方工具调用时先确认错误确实来自 Kimi（第三方可能有自己的审查话术） |
| 超时 / `Connection Error` / `Connection Time Out` | ① 代码或 SDK 默认超时；② 代理服务器网络与超时；③ 非流式长生成时中间网关等不到 header 就断连 → **开 `stream=True`** |
| 504 | 网关超时（900s 或 2h，见第 2 节矛盾说明），改流式 |
| 客户端没显示结果但账户扣费了 | 客户端超时 / 断连不等于服务端失败。查：HTTP 状态码与 `request_id`；响应 `usage`；客户端是否自动重试 / 起子 Agent / 循环调工具；控制台用量看板；客户端超时日志。仍对不上→带组织 ID、项目、时间、`request_id`、模型、客户端版本、脱敏日志、账单，走 API 问题反馈表单 |
| 查消费明细 / 反馈异常扣费 | 控制台用量看板与计费明细，按时间、项目、模型、`request_id` 与客户端日志、`usage` 逐条对照；后台协助需上面同一套材料 |
| `request_id` 怎么拿 | 文档多处要求提供 `request_id`，但**在哪个响应头 / 字段里 ⚠ 文档未说明**。可尝试：openai SDK 的 `e.request_id` / `completion._request_id`（读 `x-request-id` 头，Kimi 是否返回该头未验证）；或用 MoonPalace 调试工具抓完整请求响应 |
| 第三方 Agent / IDE 配好仍报错 | 拆两层：先用同 Key、端点、模型直接 curl；直连失败先修余额 / 鉴权 / 权限 / 参数；直连成功则看工具日志（协议转换、流式、超时、自动重试）；CC Switch、Trae 等非官方维护，需同时找对应工具支持 |
| 内容不完整 / 被截断 | 看 `choice.finish_reason`，为 `length` 即超过 `max_completion_tokens`，多余内容被丢弃。续写用 Partial Mode；避免截断用 estimate-token-count 接口（文档 `/docs/api/estimate`）算输入后设置 `max_completion_tokens ≤ 模型上下文 − 输入 tokens` |
| 输入 token 超长 | `kimi-k3` 上限 1M（约 150 万汉字），`kimi-k2.7-code` / `kimi-k2.6` 256K（约 40 万汉字，均为估算）；1 token ≈ 1.5–2 汉字 |
| 输出长度上限 | `kimi-k3`：`max_completion_tokens` 默认 131072，最大 `1024*1024 − prompt_tokens`；`kimi-k2.7-code` / `kimi-k2.6`：`256*1024 − prompt_tokens` |
| 设了 `max_completion_tokens=2000` 却输出不到 2000 字 | 它是上限不是目标，不进 prompt。要控字数：≤1000 字在 prompt 里明说 + 检测后二轮纠正；更长的按章节模板占位逐段填充。`max_tokens` 已弃用，用 `max_completion_tokens` |
| 相似 prompt 有的 3s 有的 20s | 响应时间与生成 token 数成正比；用 `stream=True` 观察 TTFT，首 token 时间通常稳定 |
| `tool_calls` 反复调同一工具 | 先查消息布局（`choice.message` 原样回填、`tool_call_id` 匹配、流式正确拼接 `tool_calls`），仍无效在业务侧做重复检测 + 系统提示词提醒 |
| 数值计算错 | 模型生成有不确定性，用 `tool_calls` 提供计算器 |
| 答不出今天日期 | 把日期写进 system prompt |
| API 结果与 Kimi 智能助手不一致 | 不同产品：模型版本、System Prompt、上下文管理、工具配置都不同，属正常 |
| 联网搜索 | 内置 `$web_search`，在 `tools` 里以 `builtin_function` 声明；**当前正在升级，近期不建议使用，文档已过时** |
| 文件抽取不准 / 图片识别不了 | 文本类文件抽文字；图片文件和纯图片 PDF **不再支持抽取**，要理解图片用 `purpose="image"` 上传 |
| 想用 `file_id` 引用文件内容 | 不支持 |
| 用 base64 塞文件内容 | 别这么做，token 巨量消耗；支持的格式走 `/v1/files` 抽取，二进制文件模型无法解析 |
| Context Caching 要配置吗 | 不用，自动对重复初始前缀尝试缓存；保持 system prompt / 工具定义 / 长文档前缀稳定 |
| `kimi-k3` 使用条件 / 推理强度 / 关思维链 | 需实际充值 ≥10 元（15 元代金券不可用）；顶层 `reasoning_effort` 取 `low` / `high` / `max`，默认 `max`；思维链关不掉，嫌长就设 `low` |
| 先体验再充值 | Playground 做最小测试；调试阶段用 MoonPalace 抓完整请求 |
| 不用 SDK 时怎么处理错误 | 判 `status_code == 200` 再取 `choices`，否则 `r.json()["error"]["type"/"message"]`（504 是 HTML，先判状态码） |

## 7. Python 示例：按 error.type 分支处理并退避重试

```python
import os
import random
import time

from openai import (
    OpenAI,
    APIStatusError,        # 收到了 HTTP 响应但状态码非 2xx
    APIConnectionError,    # 没拿到响应：连接失败 / 超时（含 APITimeoutError）
)

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.cn/v1",   # 不设会打到 OpenAI，报 model_not_found
    max_retries=0,                            # 关掉 SDK 自动重试，自己控制（Tier0 RPM 只有 3）
    timeout=600,
)

# 该退避重试的 error.type；其它 4xx 一律不重试
RETRYABLE_TYPES = {
    "engine_overloaded_error",   # 429，服务端过载
    "rate_limit_reached_error",  # 429，并发 / RPM / TPM（TPD 单独处理）
    "server_error",              # 500
    "unexpected_output",         # 500
    "server_unavailable",        # 503
}


def kimi_error_type(e: APIStatusError) -> str | None:
    """从 {"error": {"type", "message"}} 里取 type；504 是 HTML，取不到则返回 None。"""
    t = getattr(e, "type", None)
    if t:
        return t
    body = e.body
    if isinstance(body, dict):
        return (body.get("error") or body).get("type")
    return None


def backoff_seconds(e: APIStatusError, attempt: int) -> float:
    retry_after = e.response.headers.get("Retry-After")   # engine_overloaded_error 会给
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return min(60.0, 2.0 ** attempt) + random.uniform(0, 1)   # 指数退避 + 抖动


def chat(messages, model="kimi-k3", max_attempts=5, **kwargs):
    for attempt in range(max_attempts):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=kwargs.pop("max_completion_tokens", 4096),  # 显式设小，TPM 按它预估
                **kwargs,
            )
        except APIStatusError as e:
            status = e.status_code
            etype = kimi_error_type(e)
            request_id = getattr(e, "request_id", None)   # 来自 x-request-id 头，Kimi 是否返回未验证
            print(f"[{status}] type={etype} request_id={request_id} msg={e.message}")

            if status == 401:
                raise RuntimeError("Key 无效：确认是开放平台 Key，且 .com 的 Key 打 api.moonshot.cn、.ai 的打 api.moonshot.ai") from e
            if status == 404:
                raise RuntimeError("模型不存在或无权访问：用 GET /v1/models 核对，检查是否已下线 / 是否需充值") from e
            if etype == "content_filter":
                raise ValueError("内容审查（输入或输出）：修改输入后再试，原样重试无意义") from e
            if etype == "exceeded_current_quota_error":
                raise RuntimeError("余额不足 / 欠费：充值后再试") from e
            if etype == "rate_limit_reached_error" and "TPD" in (e.message or ""):
                raise RuntimeError("触发 TPD 日限：次日恢复或升级 Tier") from e
            if status == 504 or etype in RETRYABLE_TYPES:
                if attempt == max_attempts - 1:
                    raise
                wait = backoff_seconds(e, attempt)
                if status == 504:
                    print("504 网关超时：长生成请改 stream=True；服务端可能已完成并计费")
                print(f"retry in {wait:.1f}s")
                time.sleep(wait)
                continue
            raise   # 400 其它 invalid_request_error、403 等：修请求，不重试
        except APIConnectionError as e:
            # 连接失败 / 本地超时：先怀疑 SDK timeout、代理、非流式长生成；服务端可能已计费
            if attempt == max_attempts - 1:
                raise
            time.sleep(min(60.0, 2.0 ** attempt))


if __name__ == "__main__":
    completion = chat([{"role": "user", "content": "你好"}])
    print(completion.choices[0].message.content)
    print(completion.usage)   # 对账时和控制台计费明细逐条对照
```

要点：

- `e.body` 在 openai SDK 里通常已被剥成内层 `error` 对象，`e.type` 直接可用；上面的 helper 兼容两种形状，并容忍 504 的 HTML 体。
- 判断 TPD 用的是 message 关键字匹配，因为四种 `rate_limit_reached_error` 共用同一个 `type`，只有 message 能区分；TPD 的 message 原文 ⚠ 文档未说明，实际以 API 返回为准。
- 流式请求（`stream=True`）的错误同样以 `APIStatusError` 抛出在 `create()` 阶段；中途断流表现为迭代时的连接异常。

## 8. 与 OpenAI 直觉不同的点

1. **429 有三个完全不同的含义**（过载 / 限速 / 欠费），按 OpenAI 习惯"429 就退避重试"会在欠费时无限空转，在过载时以为是自己超速去升 Tier。
2. **TPM 按 `max_completion_tokens` 预扣**而非实际生成，K3 默认 131072，不设的话 Tier0 每分钟只够发 3 个请求——而且 RPM 本来也只有 3。
3. **SDK 默认重试 2 次会吃掉 Tier0 全部 RPM**，`max_retries=0` 在 OpenAI 上是可选项，在这里是必选项。
4. **504 不是 JSON**，通用的 `resp.json()["error"]` 解析会先炸在这里。
5. **限速按用户 / 组织，不按 Key**，多建 Key 无效。
6. 错误体只有 `type` + `message`，没有 `code`；`model_not_found` 出现说明请求根本没到 Kimi。
