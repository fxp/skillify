# 火山方舟 · SDK 与协议兼容 速查

本文覆盖：官方 SDK（Python / Go / Java）安装升级与客户端初始化（`base_url`、超时、重试、AK/SK）、SDK 常见用法骨架、用 OpenAI SDK / LangChain 直连三套入口（标准 `/api/v3`、Coding Plan `/api/coding/v3`、Agent Plan `/api/plan/v3`）的初始化对照表、Anthropic 协议兼容入口现状、Ark CLI、方舟文档 MCP、环境变量配置、以及公告中影响兼容性的条目。行为描述来自文档，标注处均**未实测**；标 **已用真实 API 验证（2026-09-04，Agent Plan Medium）** 的结论在 Agent Plan `/api/plan/v3` 与 `/api/plan/v1/messages` 入口实测，标准 `/api/v3` 与 Coding Plan 入口预期相同但未测。

## 目录
1. [入口 × SDK 初始化总表](#1-入口--sdk-初始化总表)
2. [官方 SDK 安装与升级](#2-官方-sdk-安装与升级)
3. [官方 SDK 客户端初始化与常见用法](#3-官方-sdk-客户端初始化与常见用法)
4. [兼容 OpenAI SDK](#4-兼容-openai-sdk)
5. [Anthropic 协议兼容入口](#5-anthropic-协议兼容入口)
6. [Ark CLI](#6-ark-cli)
7. [方舟文档 MCP](#7-方舟文档-mcp)
8. [环境变量配置要点](#8-环境变量配置要点)
9. [快速入门(新手版)与产品更新公告中的兼容性条目](#9-快速入门新手版与产品更新公告中的兼容性条目)
10. [来源页面](#来源页面)

---

## 1. 入口 × SDK 初始化总表

三套入口只改 **base_url** 与 **key**，`model` 字段格式随入口变化。表中环境变量：`ARK_API_KEY` = 方舟 API Key（标准 + Coding Plan 共用），`ARK_AGENT_PLAN_API_KEY` = Agent Plan 专属 Key。

| | 标准 API（后付费） | Coding Plan | Agent Plan |
|---|---|---|---|
| OpenAI 协议 Base URL | `https://ark.cn-beijing.volces.com/api/v3` | `https://ark.cn-beijing.volces.com/api/coding/v3` | `https://ark.cn-beijing.volces.com/api/plan/v3` |
| Anthropic 协议 Base URL | `https://ark.cn-beijing.volces.com/api/v3/compatible`（仅「Agent 场景模型调用的正确姿势」页出现，见第 5 节 ⚠） | `https://ark.cn-beijing.volces.com/api/coding` | `https://ark.cn-beijing.volces.com/api/plan`（已实测 `POST /api/plan/v1/messages` 可用，见 5.4） |
| Key 环境变量 | `ARK_API_KEY` | `ARK_API_KEY` | `ARK_AGENT_PLAN_API_KEY` |
| `model` 填法 | 带日期 Model ID `doubao-seed-2-1-pro-260628` 或接入点 `ep-xxxx` | 小写 Model Name `doubao-seed-2.0-lite`、`ark-code-latest`（控制台切） | 小写 Model Name、`ark-code-latest`（控制台选 Auto 时响应 `model: "auto"`）。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：直填 `auto` → 404 `UnsupportedModel`；带日期 Model ID 被接受但静默按 Name 路由（`doubao-seed-2-0-lite-260428` → 响应 `doubao-seed-2-0-lite-260215`），见 `errors-and-limits.md` §5.4 / §5.9 |
| `openai` Python | `OpenAI(base_url=..., api_key=os.environ["ARK_API_KEY"])` | 同左，换 base_url | `OpenAI(base_url=..., api_key=os.environ["ARK_AGENT_PLAN_API_KEY"])` |
| `openai` Node | `new OpenAI({ baseURL, apiKey: process.env.ARK_API_KEY })` | 同左 | `apiKey: process.env.ARK_AGENT_PLAN_API_KEY` |
| `volcenginesdkarkruntime.Ark` | `Ark(api_key=..., base_url=...)`（默认 base_url 即标准入口） | `Ark(api_key=..., base_url="…/api/coding/v3")` ⚠ 文档未给 Plan 入口的官方 SDK 示例，待实测 | 同左 ⚠ |
| LangChain | `ChatOpenAI(openai_api_base=..., openai_api_key=..., model=...)` | 同左 | 同左 |
| Claude Code | — | `ANTHROPIC_BASE_URL=…/api/coding` + `ANTHROPIC_AUTH_TOKEN=$ARK_API_KEY` | `ANTHROPIC_BASE_URL=…/api/plan` + `ANTHROPIC_AUTH_TOKEN=$ARK_AGENT_PLAN_API_KEY` |
| Codex CLI / OpenCode / Cline / Cursor / OpenClaw | 标准 base_url | `…/api/coding/v3` | `…/api/plan/v3`（Codex：Override OpenAI Base URL） |
| 是否允许程序直调 | 是 | 官方口径「不可用于 API 调用」，仅 AI 编程工具内 | 文本 / 向量化模型同 Coding Plan；图片 / 视频 / 语音模型通过 API 调 |
| 计费 | 按 token 后付费 | 套餐额度 | AFP 抵扣 / 超额后付费 |

**用错入口不会报错**：Plan Key + `/api/v3`（若 Key 通用）或 Plan 模型名 + `/api/v3` 走后付费扣余额，套餐额度不动。Coding Plan 快速开始原文：「请勿使用 `https://ark.cn-beijing.volces.com/api/v3`：该 Base URL 不会消耗您的 Coding Plan 额度，而是会产生额外费用。」

---

## 2. 官方 SDK 安装与升级

| 语言 | 前提 | 安装 | 升级 / 指定版本 | 版本查询 |
|---|---|---|---|---|
| Python | Python ≥ 3.7 | `pip install 'volcengine-python-sdk[ark]'`（Windows CMD 用双引号；`uv pip install 'volcengine-python-sdk[ark]'` 更快；源码安装解压后 `pip install .`） | `pip install 'volcengine-python-sdk[ark]' -U` | PyPI；加密能力需 ≥ `1.0.104` |
| Go | Go ≥ 1.18，`go mod init <project>` | `go get -u github.com/volcengine/volcengine-go-sdk`，然后 `go mod tidy` | `go get -u github.com/volcengine/volcengine-go-sdk@<VERSION>` | https://github.com/volcengine/volcengine-go-sdk/releases |
| Java | Java ≥ 1.8，**仅服务端，不支持 Android** | Maven `com.volcengine:volcengine-java-sdk-ark-runtime:LATEST`；Gradle `implementation 'com.volcengine:volcengine-java-sdk-ark-runtime:LATEST'` | 把 `LATEST` 换成指定版本 | https://github.com/volcengine/volcengine-java-sdk/releases；加密能力需 ≥ `0.2.50` |

- Python 包 import 名：`from volcenginesdkarkruntime import Ark, AsyncArk`；Go：`import "github.com/volcengine/volcengine-go-sdk/service/arkruntime"`（模型类型在 `.../arkruntime/model`、Responses 在 `.../arkruntime/model/responses`）；Java：`com.volcengine.ark.runtime.service.ArkService`。
- 判断新旧 SDK：import 路径含 `ark` 为 v3；含 `maas` 为已淘汰的 v1/v2（FAQ）。
- Windows `Failed building wheel for volcengine-python-sdk`：开注册表 `LongPathsEnabled=1`（FAQ）。
- 文档页注：`uv pip install pip install 'volcengine-python-sdk[ark]'` 多打了一个 `pip install`，是文档笔误。

---

## 3. 官方 SDK 客户端初始化与常见用法

底层 endpoint：所有 `client.chat.completions.create` 打 `POST {base_url}/chat/completions`，`client.responses.create` 打 `POST {base_url}/responses`，与 OpenAI 协议一致。

### 3.1 初始化参数（Python `Ark` / `AsyncArk`）
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `api_key` | str | 与 `ak`/`sk` 二选一 | 读环境变量 `ARK_API_KEY` ⚠ 文档示例均显式传入，是否自动读环境变量未说明 | 方舟 API Key |
| `ak` / `sk` | str | 与 `api_key` 二选一 | — | 火山 Access Key / Secret Key；SDK 内部调管控面 `GetApiKey` 换临时 Key，**此接口限流很低，务必单例**；此时 `model` **必须是 Endpoint ID** |
| `base_url` | str | 否 | `https://ark.cn-beijing.volces.com/api/v3` | 「默认无需配置，连接非默认区域服务端点时使用」 |
| `timeout` | int/float 秒 | 否 | 连接 60 s、socket 600 s | 深度思考模型推荐 `1800` |
| `max_retries` | int | 否 | 2 | 瞬时故障自动重试次数 |
| `http_client` | `httpx.Client` | 否 | — | 禁代理：`httpx.Client(proxies={'http://': None, 'https://': None})` |

Go：`arkruntime.NewClientWithApiKey(key, arkruntime.WithTimeout(30*time.Minute), arkruntime.WithRetryTimes(2), arkruntime.WithBaseUrl(url))`；AK/SK 用 `arkruntime.NewClientWithAkSk(ak, sk, ...)`。默认 600 s 端到端总超时。
Java：`ArkService.builder().apiKey(k).baseUrl(u).timeout(Duration.ofSeconds(1800)).connectTimeout(Duration.ofSeconds(20)).retryTimes(2).build()`；AK/SK 用 `.ak(ak).sk(sk)`；用完 `service.shutdownExecutor()`。默认连接 60 s、socket 600 s。

### 3.2 同步 / 流式 / 多模态骨架（Python）
```python
import os
from volcenginesdkarkruntime import Ark

client = Ark(api_key=os.environ["ARK_API_KEY"],
             base_url="https://ark.cn-beijing.volces.com/api/v3",
             timeout=1800, max_retries=2)          # 单例复用，勿每次请求新建

# 同步
r = client.chat.completions.create(
    model="doubao-seed-2-1-pro-260628",              # 标准入口：Model ID 或 ep-xxx
    messages=[{"role": "user", "content": "Hello"}])
print(r.choices[0].message.content)

# 流式
for chunk in client.chat.completions.create(model="doubao-seed-2-1-pro-260628",
        messages=[{"role": "user", "content": "Hello"}], stream=True):
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")

# 多模态（图片理解）：content 为数组，image_url 支持 http(s) URL 或 data:image/...;base64,
r = client.chat.completions.create(model="doubao-seed-2-1-pro-260628", messages=[{
    "role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/a.png", "detail": "auto"}},
        {"type": "text", "text": "图里有什么？"}]}])

# Responses API
resp = client.responses.create(model="doubao-seed-2-1-pro-260628", input="hello")
```
⚠ 上述流式 / 多模态骨架按 OpenAI 协议惯例写，SDK 常见使用示例页只给了同步与 Responses 例子；字段名以对话 Chat API 页为准。

### 3.3 Access Key 鉴权（企业精细化权限）
```python
client = Ark(ak=os.environ["VOLC_ACCESSKEY"], sk=os.environ["VOLC_SECRETKEY"],
             base_url="https://ark.cn-beijing.volces.com/api/v3")
r = client.chat.completions.create(model="ep-2025xxxx-xxxxx",   # 必须是 Endpoint ID
                                   messages=[{"role": "user", "content": "Hello"}])
```
原理：SDK 调管控面 `GetApiKey`（1262825）换临时 API Key；该接口限流低，非单例会触发 429 `APIAccountRpmRateLimitExceeded`（文档原文，未实测）。

### 3.4 自定义 header（`extra_headers`）
| Header | 值 | 用途 | 限制 |
|---|---|---|---|
| `X-Client-Request-Id` | 自定义 ID | 串联客户端 / 服务端日志，报售后时提供 | Chat API、批量 Chat API |
| `x-is-encrypted` | `true` | 推理会话应用层加密（免费） | Python ≥ 1.0.104、Java ≥ 0.2.50；仅文本 / 图片理解模型、Chat API；图片仅 Base64 可加密；Java 需加 BouncyCastle `bcprov-jdk18on` / `bcpkix-jdk18on` 1.78.1 |
| `X-Fornax-Trace` | `true` | 开启数据上报（限时免费） | 仅 Responses API；不生效则升级 SDK |

Python：`client.chat.completions.create(..., extra_headers={"X-Client-Request-Id": "my-id"})`
Go：`client.CreateChatCompletion(ctx, req, arkruntime.WithCustomHeader(model.ClientRequestHeader, "my-id"))`；任意头 `arkruntime.WithCustomHeader("X-Fornax-Trace", "true")`
Java：`service.createChatCompletion(request, Map.of(Const.CLIENT_REQUEST_HEADER, "my-id"))`

### 3.5 单例
「请使用单例方式请求模型服务，勿重复创建实例导致额外资源消耗。」一个进程一个 `Ark` / `ArkService` / `arkruntime.Client`，复用发多次请求。

---

## 4. 兼容 OpenAI SDK

方舟数据面「尽可能兼容 OpenAI API」；社区 SDK 不由火山维护。要求 `openai>=1.0`、Python ≥ 3.7。

### 4.1 Python 初始化 + `extra_body` 传 `thinking` + `extra_headers`
```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://ark.cn-beijing.volces.com/api/v3",   # Coding Plan: /api/coding/v3 ; Agent Plan: /api/plan/v3
                api_key=os.environ["ARK_API_KEY"])                     # Agent Plan: ARK_AGENT_PLAN_API_KEY

r = client.chat.completions.create(
    model="doubao-seed-2-1-pro-260628",       # Plan 入口改为小写 Model Name，如 doubao-seed-2.0-lite
    messages=[{"role": "user", "content": "Hello"}],
    extra_body={"thinking": {"type": "enabled"}},          # OpenAI SDK 没有的字段走 extra_body；"disabled" 关思考
    extra_headers={"X-Client-Request-Id": "202406251728190000B7EA7A9648AC08D9"})
print(r.choices[0].message.content)
```
- 不要用 `developer` role：方舟只支持 `system` / `user` / `assistant` / `tool`，否则 400（文档原文见 errors-and-limits.md）。
- `thinking.type` 与 `reasoning_effort` 在请求里显式传时以请求为准，否则用接入点 / 模型默认值（2026-04 公告）。`glm-5.3` 默认开思考且不支持关闭。
- 思考内容在 `choices[].message.reasoning_content`（明文摘要）与 `choices[].message.encrypted_content`（加密块，Seed 2.1 / evolving 等新模型需原样回传），见「Agent 场景模型调用的正确姿势」。

### 4.2 Node
```js
import OpenAI from "openai";
const client = new OpenAI({
  baseURL: "https://ark.cn-beijing.volces.com/api/v3",
  apiKey: process.env.ARK_API_KEY,
});
const r = await client.chat.completions.create({
  model: "doubao-seed-2-1-pro-260628",
  messages: [{ role: "user", content: "Hello" }],
  // @ts-ignore 非 OpenAI 标准字段直接放顶层即可透传
  thinking: { type: "enabled" },
});
```
⚠ 文档只给 Python 示例，Node 写法按 openai-node 惯例推断（顶层多余字段会被序列化透传），未实测。

### 4.3 curl（等价请求）
```bash
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{"model":"doubao-seed-2-1-pro-260628","messages":[{"role":"user","content":"Hello"}],"thinking":{"type":"enabled"}}'
```

### 4.4 LangChain
```python
import os
from langchain_openai import ChatOpenAI          # pip install langchain-openai
llm = ChatOpenAI(openai_api_key=os.environ["ARK_API_KEY"],
                 openai_api_base="https://ark.cn-beijing.volces.com/api/v3",
                 model="doubao-seed-2-1-pro-260628")
print(llm.invoke("Hello"))
```
传 `thinking` 用 `ChatOpenAI(..., extra_body={"thinking": {"type": "enabled"}})` 或 `model_kwargs` ⚠ 文档未给，未实测。

### 4.5 不兼容 / 差异清单
| 项 | 说明 |
|---|---|
| `developer` role | 不支持；已实测 Plan 入口 400 `InvalidParameter`（`supported values are: system, assistant, user, tool`），见 `errors-and-limits.md` §5.6 |
| 向量化 `/embeddings` | 兼容 OpenAI SDK 页：「向量化能力模型不支持 OpenAI API，请使用方舟 SDK」（`client.multimodal_embeddings.create`）；但 Coding / Agent Plan 的 OpenClaw 配置用 `provider: openai` + `…/api/coding/v3` 调 `doubao-embedding-vision`，且 2026-03 公告「doubao-embedding-vision-251215 模型支持 coding plan」→ 文档自相矛盾，**已用真实 API 验证（2026-09-04，Agent Plan Medium）**裁决：`POST /api/plan/v3/embeddings`（OpenAI 形态，`input` 字符串）**可用**，`client.embeddings.create(model="doubao-embedding-vision", input="...")` 返回 `data[0].embedding`（默认 2048 维，`dimensions=1024` 生效）；`input` 传方舟多模态数组报 400 `InvalidParameter`（`input[0] ... expected a string`），含图片要走 `/embeddings/multimodal`（响应 `data.embedding` 单对象）。标准入口 `/api/v3/embeddings` 未测。详见 `embeddings-speech.md` §2.3 |
| 文本向量化模型 | 已逐步下线，用多模态向量化 |
| 非 OpenAI 字段 | `thinking`、`reasoning_effort`（值 `high` 等）、`caching`、`encrypted_content` 等经 `extra_body` 传 |
| Responses API | `/api/v3/responses` 与 `/api/plan/v3/responses`（Agent Plan 2026-05 公告支持）；Coding Plan 是否支持 Responses ⚠ 文档未说明。**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`POST /api/plan/v3/responses` 可用——`store: true` 响应含 `expire_at`，`GET /responses/{id}` 200，`previous_response_id` 续轮正确回忆上一轮，`DELETE /responses/{id}` 返回 `{"id":...,"object":"response","deleted":true}`，`model: ark-code-latest` 也可用（响应 `model: "auto"`） |
| 加密 header `x-is-encrypted` | 仅官方 Python / Java SDK 会做客户端加密；用 openai SDK 传这个头的行为 ⚠ 未说明 |

---

## 5. Anthropic 协议兼容入口

### 5.1 文档现状
| 入口 | 文档出现语境 | 鉴权 header | 结论 |
|---|---|---|---|
| `https://ark.cn-beijing.volces.com/api/coding` | Coding Plan 接入 Claude Code：`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN=<方舟 API Key>` | Claude Code 用 `ANTHROPIC_AUTH_TOKEN` → 发 `Authorization: Bearer`（Claude Code 行为）；原生 SDK 用 `x-api-key` 是否被接受 ⚠ 文档未说明（Agent Plan 入口实测两种头都接受，Coding Plan 预期相同但未测） | 文档只在 Claude Code 语境出现 |
| `https://ark.cn-beijing.volces.com/api/plan` | Agent Plan 接入 Claude Code，同上，Key 为 Agent Plan 专属 | **已用真实 API 验证（2026-09-04，Agent Plan Medium）**：`Authorization: Bearer <PlanKey>` 与 `x-api-key: <PlanKey>` **都接受**；请求带 `anthropic-version: 2023-06-01` 正常，不带未测 | 已实测可用（`POST /api/plan/v1/messages`，见 5.4）；`model: claude-*` 被静默路由到 `doubao-seed-2-1-turbo-260628`；官方口径文本模型不可 API 直调 |
| `https://ark.cn-beijing.volces.com/api/v3/compatible/v1/messages`（curl 示例）/ `/api/compatible/v1/messages`（对照表） | 「Agent 场景模型调用的正确姿势」（2636748，2026-09-01）的「Anthropic 兼容 API」页签 | curl 用 `-H "x-api-key: $ARK_API_KEY" -H "anthropic-version: 2023-06-01"` | **标准入口存在 Anthropic 兼容 API**，与 auth.md「文档未列出」结论不同；同一页两处路径不一致 → ⚠ 文档自相矛盾（`/api/v3/compatible/v1/messages` vs `/api/compatible/v1/messages`），待实测。示例 model 为 `doubao-seed-evolving`（小写 Name 而非 Model ID）⚠ |

### 5.2 标准入口 Anthropic 兼容 API（文档原文骨架，未实测）
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/v3/compatible/v1/messages` ⚠（或 `/api/compatible/v1/messages`）
**用途**: 用 Anthropic Messages 协议（`messages` / `tools.input_schema` / `tool_use` / `tool_result` / `thinking` 块）调方舟模型；Agent 场景要把 `type=="thinking"` 块（`thinking` 文本 + `signature`）整块、按原顺序回传，放在 `tool_use` 之前，不要过滤重构。
**关键参数**（对照表给出的推荐值）
| 参数 | 说明 |
|---|---|
| `model` | 示例 `doubao-seed-evolving` |
| `max_tokens` | 必须显式传，Agent 场景建议 ≥ 128000 |
| `thinking` | `{"type": "enabled"}`，Agent 场景显式开，不用 `auto` |
| `output_config.effort` | `"high"`（对应 OpenAI 协议的 `reasoning_effort`） |
| `temperature` / `top_p` | 推荐 1 / 0.95 |
```bash
curl https://ark.cn-beijing.volces.com/api/v3/compatible/v1/messages \
  -H "Content-Type: application/json" -H "x-api-key: $ARK_API_KEY" -H "anthropic-version: 2023-06-01" \
  -d '{"model":"doubao-seed-evolving","max_tokens":128000,"thinking":{"type":"enabled"},
       "messages":[{"role":"user","content":"你好"}]}'
```
```python
# 原生 Anthropic SDK 直连——文档未给示例，按 header 推断，⚠ 待实测
import os, anthropic
client = anthropic.Anthropic(api_key=os.environ["ARK_API_KEY"],
                             base_url="https://ark.cn-beijing.volces.com/api/v3/compatible")
msg = client.messages.create(model="doubao-seed-evolving", max_tokens=128000,
                             thinking={"type": "enabled"},
                             messages=[{"role": "user", "content": "你好"}])
```
Agent Plan 入口同理且**已实测可用**：`base_url="https://ark.cn-beijing.volces.com/api/plan"` + `ARK_AGENT_PLAN_API_KEY`，SDK 打 `{base_url}/v1/messages`，见 5.4。Coding Plan `/api/coding` 预期相同但未测；两者都违反 Plan「仅 AI 工具内使用」口径。

### 5.3 Claude Code 配置（Plan 入口的官方用法）
`~/.claude/settings.json`：
```json
{"env": {
  "ANTHROPIC_AUTH_TOKEN": "<ARK_API_KEY 或 ARK_AGENT_PLAN_API_KEY>",
  "ANTHROPIC_BASE_URL": "https://ark.cn-beijing.volces.com/api/coding",
  "ANTHROPIC_MODEL": "<MODEL_NAME 或 ark-code-latest>",
  "ANTHROPIC_DEFAULT_HAIKU_MODEL": "<小模型>", "ANTHROPIC_DEFAULT_SONNET_MODEL": "<MODEL_NAME>", "ANTHROPIC_DEFAULT_OPUS_MODEL": "<MODEL_NAME>",
  "CLAUDE_CODE_SUBAGENT_MODEL": "<MODEL_NAME>",
  "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
  "CLAUDE_CODE_EXTRA_BODY": "{\"thinking\":{\"type\":\"enabled\"}}"
}}
```
Agent Plan 把 `ANTHROPIC_BASE_URL` 换成 `…/api/plan`。本地 `.bashrc` / `.zshrc` 里已有 `ANTHROPIC_*` 会冲突，先清理。也可 `arkcli helper` 自动写入。

**`ANTHROPIC_MODEL` 必须显式设置**（**已用真实 API 验证（2026-09-04，Agent Plan Medium）**）：Plan 入口对 `claude-*` 模型名**不报错**，`model: "claude-sonnet-4-5"` 被静默路由到 `doubao-seed-2-1-turbo-260628`（抵扣系数 2.5）。Claude Code 没设 `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL` 时发的就是 `claude-*` 名，于是会在毫无报错的情况下按 2.1-turbo 烧 AFP。配置后在响应 `model` 或控制台用量页核对一次。

### 5.4 Agent Plan 入口 Anthropic 协议 `POST /api/plan/v1/messages`（已实测）
**Endpoint**: `POST https://ark.cn-beijing.volces.com/api/plan/v1/messages`（`anthropic` SDK：`base_url="https://ark.cn-beijing.volces.com/api/plan"`）
**用途**: 用 Anthropic Messages 协议直连 Agent Plan，Claude Code 走的就是它。文本模型官方口径「不可用于 API 调用」，程序直连的合规风险自负。

**已用真实 API 验证（2026-09-04，Agent Plan Medium）**：
- **鉴权**：`Authorization: Bearer $ARK_AGENT_PLAN_API_KEY` 与 `x-api-key: $ARK_AGENT_PLAN_API_KEY` 都返回 200；实测请求都带了 `anthropic-version: 2023-06-01`，不带的行为未测。
- **响应**：标准 Anthropic Message 对象——`{"id":"...","type":"message","role":"assistant","model":"doubao-seed-2-0-lite-260215","content":[{"type":"thinking","thinking":"..."},{"type":"text","text":"2"}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":59,"output_tokens":190,"cache_read_input_tokens":0}}`。思维链以 `thinking` block 返回（默认开），`usage` 带 `cache_read_input_tokens`。
- **`thinking: {"type":"disabled"}`** 生效：`content` 只剩 `text` block，`output_tokens` 降到 1。
- **`stream: true`**：标准 Anthropic SSE，`event: message_start`（含 `message.model`、`usage`）→ `content_block_start`（`{"type":"text","text":""}`）→ 逐 token `content_block_delta`（`delta.type: "text_delta"`）…，`anthropic` SDK 的 `messages.stream()` 可直接消费。
- **model 静默路由（最重要）**：`model: "claude-sonnet-4-5"` → 200，响应 `"model":"doubao-seed-2-1-turbo-260628"`；`model: "doubao-seed-2-0-lite-260428"`（带日期）→ 200，响应 `"model":"doubao-seed-2-0-lite-260215"`。两者都不报错，只能在响应 `model` 看出来。填小写 Model Name（`doubao-seed-2.0-lite` 等）并核对响应。
- `/api/plan/v3/chat/completions` 的 OpenAI 协议与本入口共用同一把 Key、同一套模型；直填 `auto` 在 OpenAI 协议入口 404，本入口未测 `auto`。
- Coding Plan `/api/coding/v1/messages` 与标准 `/api/v3/compatible/v1/messages` 未测（⚠ 见 5.1 / 5.2）。

```bash
curl https://ark.cn-beijing.volces.com/api/plan/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_AGENT_PLAN_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"doubao-seed-2.0-lite","max_tokens":64,"thinking":{"type":"disabled"},
       "messages":[{"role":"user","content":"用一个词回答：1+1=?"}]}'
```

```python
import os, anthropic

client = anthropic.Anthropic(api_key=os.environ["ARK_AGENT_PLAN_API_KEY"],      # SDK 以 x-api-key 发送，实测被接受
                             base_url="https://ark.cn-beijing.volces.com/api/plan")
msg = client.messages.create(model="doubao-seed-2.0-lite", max_tokens=64,        # 不要写 claude-*：会被静默路由到 2.1-turbo
                             thinking={"type": "disabled"},
                             messages=[{"role": "user", "content": "用一个词回答：1+1=?"}])
assert msg.model.startswith("doubao-seed-2-0-lite"), msg.model                    # 核对实际服务模型
print(msg.content[-1].text)   # "2"
```

---

## 6. Ark CLI

- 环境：Node.js ≥ 16。安装 `npm install -g @volcengine/ark-cli`（Coding Plan 指南写 `@volcengine/ark-cli@latest`），验证 `arkcli --version`。
- 登录：`arkcli auth login`（交互选项目 Project、消费模式 Type：`coding-plan` 等）；`arkcli auth login volc-sso`（浏览器 SSO，推荐）；`arkcli auth login --no-browser`（远程终端）；`arkcli auth status`。重新选择配置先 `arkcli config reset` 再登录。
- `arkcli helper`：TUI 助手，选 Plan profile（如 `coding-plan_cn-beijing_personal (Coding Plan)`）→ 默认 model → 要配置的 AI Agent（Claude Code / Codex / OpenCode / OpenClaw / Trae），自动写入工具配置（含 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`）。
- `arkcli +connect`：把 Ark CLI skill 装进本机 AI Agent（Claude Code / Cursor / TRAE / Gemini CLI 等）；卸载 `arkcli +connect uninstall`。也可把 `https://lf3-static.bytednsdoc.com/obj/eden-cn/psjryh/ljhwZthlaukjlkulzlp/intro/volc.md` 交给 Agent 自动安装。

命令结构：`arkcli +<shortcut>`、`arkcli <domain> <resource> <verb>`、`arkcli <domain> +<shortcut>`、`arkcli api <registered-action> --params '{...}'`；任意命令 `--help`。

| 领域 | 命令入口 | 能力 |
|---|---|---|
| 认证 / Profile | `arkcli auth`、`arkcli profile` | 登录、状态、身份、生成 / 切换 API Key、多 Profile |
| 对话 | `arkcli +chat` | 多模态、多轮、流式、思考参数 |
| 生成 | `arkcli +gen` | 文生图 / 图生图 / 文生视频 / 图生视频 |
| 理解 | `arkcli +understand` | 图片 / 文档 / 视频 / 音频 |
| 模型 | `arkcli models`（`models search` 等） | 查询、搜索、详情、可用参数 |
| 推理资源 | `arkcli infer`、`arkcli +deploy` | 接入点 CRUD / 启停、一键部署 |
| 精调 | `arkcli train`（`train finetune create`） | SFT / LoRA / DPO / RL |
| Managed Agents | `arkcli agent` | Agent / Skill / Env / Session / File / Memory Store / Vault / MCP OAuth |
| 文档 | `arkcli docs` | 检索方舟文档、按 URL 取正文 |
| 用量 / 账单 / 价格 | `arkcli usage`、`arkcli billing`、`arkcli pricing` | 用量、免费额度、资源包、分账、模型 / 套餐价格 |
| 套餐 | `arkcli plans`（`plans get`、`plans buy --plan coding-plan --type pro --duration 1 [--yes]`、`plans renew ...`） | 查询 / 购买 / 续费 Agent Plan、Coding Plan；不加 `--yes` 只预览 |
| 集成 | `arkcli +connect`、`arkcli +code-example` | 安装 skill、多语言代码示例 |
| 诊断 | `arkcli doctor` | 账号 / 模型 / 接入点诊断、产物来源验证 |

全局 flag：`--api-key`、`--base-url`（自定义数据面 Base URL）、`--profile`、`--project-name`、`--region`、`--format json`（默认）、`--transform <GJSON>`、`--debug`、`--dry-run`、`--page-all` / `--page-limit <n>`（默认 10）/ `--page-delay`（默认 200 ms）。

⚠ 未在文档中出现的子命令（如 `arkcli config` 除 `reset` 之外的用法）请以 `--help` 为准。

---

## 7. 方舟文档 MCP

- Server：`https://mcp.ark-doc-resources.cn/mcp/`，MCP 2024-11-05，Streamable HTTP，**无鉴权、只读**。旧域名 `https://sd6j8o9hu8aldae0o6es0.apigateway-cn-beijing.volceapi.com/mcp` 于 2026-08-17 下线。
- 配置片段（Claude Code 写 `~/.claude.json` 或项目 `.mcp.json`；Cursor `~/.cursor/mcp.json`；Windsurf `~/.codeium/windsurf/mcp_config.json`；VS Code `.vscode/mcp.json`；TRAE 设置面板）：
```json
{"mcpServers": {"ark-docs-mcp": {"url": "https://mcp.ark-doc-resources.cn/mcp/"}}}
```
- 工具：`ark_search_docs`、`ark_list_docs`、`ark_fetch_doc`（分块，`has_more` 时按 `chunk_start += chunk_count` 续拉）、`ark_list_apis`、`ark_get_spec`（须按 `service` 或 `api_path` 过滤）、`ark_search_examples`（query 里写语言）、`ark_list_models`、`ark_get_model`。
- 客户端缓存陈旧 → 重启 MCP session。

---

## 8. 环境变量配置要点

「环境变量配置指南」（1820161）不在本地材料中 ⚠；以下来自快速入门（1399008）、获取 API Key 并配置（1541594）、Plan 接入页。

| 变量 | 用途 |
|---|---|
| `ARK_API_KEY` | 方舟 API Key（标准 + Coding Plan）。macOS / Linux `export ARK_API_KEY="..."`（写入 `~/.zshrc` / `~/.bashrc` 持久化）；Windows CMD `setx ARK_API_KEY "..."`（新开窗口生效）；PowerShell `$env:ARK_API_KEY = "..."`（仅当前会话） |
| `ARK_AGENT_PLAN_API_KEY` | Agent Plan 专属 Key（本 skill 约定名） |
| `VOLC_ACCESSKEY` / `VOLC_SECRETKEY` | Access Key 鉴权（数据面 AK/SK、管控面 API） |
| `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL` / `CLAUDE_CODE_SUBAGENT_MODEL` | Claude Code 接 Plan 入口 |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` | 关遥测，避免静默耗额度 |
| `CLAUDE_CODE_EXTRA_BODY={"thinking":{"type":"enabled"}}` | Claude Code 开深度思考 |
| `no_proxy=` / 禁 `HTTP_PROXY` | 解决 `httpx.InvalidURL` / `ArkAPIConnectionError` |

- 一个主账号最多 50 个 API Key；Key 属于创建时的项目空间，可额外限制 Model ID / 接入点 / 调用 IP；不能跨项目。
- 新手版脚本兼容历史 UUID 与新格式 `ark-<uuid>-<suffix>` 的 Key。
- 不要把 Key 硬编码进代码（官方与本 skill 一致）。

---

## 9. 快速入门(新手版)与产品更新公告中的兼容性条目

**快速入门(新手版)（2272060）**
- 零依赖脚本包 `ark_quickstart_package.zip`：Windows `scripts/zero_dependency/windows/run_windows.bat`（PowerShell），macOS `scripts/zero_dependency/mac/run_mac.command`（curl）；输入 API Key 即调一次 Chat。
- `scripts/init_dev_env/setup_{windows.bat,mac.sh}`：用 `uv` 下载 Python 3.12、建 `.venv`、装方舟 SDK，生成 `run_demo.{bat,sh}`；`python/gen_example.py` 按需生成示例并可把 `ARK_API_KEY` 写入项目 `.env`。
- 开通 Seedance 2.0 需账户余额 > 200 元或购资源包。
- 「API Key 无效」多为复制带空格。

**产品更新公告（1159177）影响 SDK / 兼容性的条目**
| 时间 | 条目 |
|---|---|
| 2026-07 | Coding / Agent Plan 上线 `doubao-seed-2.1-turbo`、`doubao-seed-evolving`（1M 上下文）；Agent Plan Medium+ 上线 Kimi K3；新增模型激活管控面 API（批量开通、自动开通开关、查询）；产物验证接口 |
| 2026-06 | Agent Plan 开通模型与 Harness 超额后付费；新增管控面 API：创建 / 续费 / 查询个人版套餐、查询 Agent Plan / Coding Plan 支持的模型列表、轮换个人版 API Key；Embedding API `multi_embedding` 多向量输出与压缩传输 |
| 2026-05 | Agent Plan 上线（AFP 计费），支持 Responses API、Codex CLI；DeepSeek-V4 系列；Chat API 低延迟模式 |
| 2026-04 | 接入点可配 `thinking` 默认值，请求显式传 `thinking.type` / `reasoning_effort` 时以请求为准；Image Generation 输入图上限 10 MB → 30 MB；API Key 维度分账 |
| 2026-03 | `doubao-embedding-vision-251215` 支持 Coding Plan；Responses API Prefill 支持上下文缓存 |
| 2026-02 | **错误码变更**：Seed 2.0 起请求过快由 `ServerOverloaded` 改为 `RequestBurstTooFast`；视觉模型增加安全审核错误码 |
| 2026-01 | Coding Plan 支持 auto 模式与多模型 |

---

## 来源页面
| 标题 | URL | 文档更新时间 |
|---|---|---|
| 安装及升级 SDK | https://www.volcengine.com/docs/82379/1541595 | 2026-07-02 |
| SDK 常见使用示例 | https://www.volcengine.com/docs/82379/1544136 | 2026-07-07 |
| 兼容 OpenAI SDK | https://www.volcengine.com/docs/82379/1330626 | 2026-06-23 |
| 获取 API Key 并配置 | https://www.volcengine.com/docs/82379/1541594 | 2026-04-27 |
| Base URL 及鉴权 | https://www.volcengine.com/docs/82379/1298459 | 2026-06-23 |
| 快速入门 | https://www.volcengine.com/docs/82379/1399008 | 2026-09-01 |
| 快速入门(新手版) | https://www.volcengine.com/docs/82379/2272060 | 2026-07-20 |
| Ark CLI 使用指南 | https://www.volcengine.com/docs/82379/2536875 | 2026-08-14 |
| Ark CLI：Coding Plan 个人版使用指南 | https://www.volcengine.com/docs/82379/2656115 | 2026-08-21 |
| 方舟文档 MCP | https://www.volcengine.com/docs/82379/2289964 | 2026-07-20 |
| 产品更新公告 | https://www.volcengine.com/docs/82379/1159177 | 2026-08-05 |
| Coding Plan 个人版 · 常见问题 | https://www.volcengine.com/docs/82379/2165245 | 2026-08-24 |
| Coding Plan 个人版 · 快速开始 | https://www.volcengine.com/docs/82379/1928261 | 2026-08-28 |
| Coding Plan 个人版 · Claude Code | https://www.volcengine.com/docs/82379/1928262 | 2026-08-28 |
| Agent Plan 个人版 · 快速开始 | https://www.volcengine.com/docs/82379/2373738 | 2026-08-28 |
| Agent Plan 个人版 · 其他工具 | https://www.volcengine.com/docs/82379/2373746 | 2026-08-28 |
| Agent Plan 个人版 · 套餐概览 | https://www.volcengine.com/docs/82379/2366394 | 2026-08-31 |
| Agent 场景模型调用的正确姿势 | https://www.volcengine.com/docs/82379/2636748 | 2026-09-01 |
| 常见问题 | https://www.volcengine.com/docs/82379/1359411 | 2026-07-07 |
