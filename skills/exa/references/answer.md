# Answer：`POST /answer`

> ⚠ 本文件全部内容整理自官方文档（https://docs.exa.ai/reference/answer 、`/docs/integrations/openai-sdk`）与 OpenAPI 规范（`AnswerRequest`/`AnswerResponse` schema），**未经真实 API 调用验证**。

目录：[基本用法](#基本用法) · [模型选择](#模型选择) · [结构化输出](#结构化输出) · [流式响应](#流式响应) · [OpenAI 兼容接口](#openai-兼容接口) · [注意事项汇总](#注意事项汇总)

## 基本用法

**Endpoint**: `POST https://api.exa.ai/answer`
**用途**: 一步到位地拿"问题的答案"，而不是自己拿 `/search` 结果再做一次 LLM 综合。文档原文："`/answer` performs an Exa search and uses an LLM to generate either: 1. A direct answer for specific queries... 2. A detailed summary with citations for open-ended queries..."——即它会根据问题类型自动决定是给一句话答案还是给带引用的长摘要，不需要调用方指定走哪条路径。

和 `/search` + `outputSchema` 的区别（⚠ 本 skill 推断，非文档原文）：`/answer` 是更轻量、专为"问答"场景设计的端点（$5/1k 次，比 `/search` 略便宜），不支持 `/search` 的检索过滤参数（`includeDomains`/`category` 等都不在 `/answer` 的请求体里）；需要过滤信源、要结构化多条目列表、或要 Deep Search 级别的多轮检索时应该用 `/search`。

**关键参数**（请求体顶层）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | — | 自然语言问题或指令 |
| `stream` | boolean | 否 | `false` | 为 `true` 时走 SSE，逐 token 返回 |
| `text` | boolean | 否 | `false` | `true` 时每条引用来源附带 `citations[].text`（完整正文），`false` 时不带 |
| `model` | enum | 否 | `exa` | `exa`/`exa-pro`/`exa-research`/`exa-fast`，见下节 |
| `systemPrompt` | string | 否 | — | 额外指令：信源偏好、新颖性约束等 |
| `userLocation` | string | 否 | — | 两位 ISO 国家码 |
| `outputSchema` | object | 否 | — | JSON Schema Draft 7，让 `answer` 字段返回结构化对象而不是字符串 |

**示例请求**

```bash
curl -s -X POST "https://api.exa.ai/answer" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EXA_API_KEY" \
  -d '{ "query": "What is the current valuation of SpaceX?" }'
```

```python
from exa_py import Exa

exa = Exa()
response = exa.answer("What caused the 2008 financial crisis?")
print(response.answer)
```

**示例响应**（⚠ 文档原文，未实测）

```json
{
  "requestId": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "answer": "$350 billion.",
  "citations": [
    {
      "id": "https://www.theguardian.com/science/2024/dec/11/...",
      "url": "https://www.theguardian.com/science/2024/dec/11/...",
      "title": "SpaceX valued at $350bn as company agrees to buy shares from ...",
      "author": "Dan Milmo",
      "publishedDate": "2024-12-11T00:00:00.000Z",
      "text": "SpaceX valued at $350bn as company agrees to buy shares from ..."
    }
  ],
  "costDollars": { "total": 0.005 }
}
```

`citations[].text` 只有在请求里 `text: true` 时才会出现（规范原文："Only present when text contents are requested."）——不传 `text` 就只有 `title`/`url`/`publishedDate`/`author`/`id`/`image`/`favicon`，没有正文。

## 模型选择

`model` 支持四个取值：`exa`（默认）、`exa-pro`、`exa-research`、`exa-fast`。⚠ **文档未说明**这四个模型在质量、延迟、价格上的具体差异——OpenAPI 规范只给出了枚举值和默认值，官方定价页（`/docs/admin/pricing`）只按 `/answer` 端点整体给了 $5/1k 次一个价格，没有按 `model` 细分。是否 `exa-pro`/`exa-research` 会有独立计价、`exa-research` 是否等价于走 Deep Search 或 Exa Agent 的检索深度，都要实测确认。

## 结构化输出

`outputSchema` 遵循 JSON Schema Draft 7，触发后 `answer` 字段从字符串变成匹配该 schema 的对象：

```json
{
  "query": "What is the capital of France and its population?",
  "outputSchema": {
    "type": "object",
    "properties": {
      "capital": { "type": "string" },
      "population": { "type": "number" }
    },
    "required": ["capital"]
  }
}
```

响应里 `answer` 字段的类型是 `oneOf[string | object]`——不传 `outputSchema` 时是字符串，传了之后是对象。写解析代码时不能假设 `answer` 永远是字符串。

## 流式响应

`stream: true` 时走 SSE，逐 token 返回生成内容。官方 SDK 提供专门的流式方法：

```python
for chunk in exa.stream_answer("Explain quantum computing"):
    print(chunk, end="", flush=True)
```

⚠ 文档未说明：流式响应的 SSE 事件名称、每个事件的 payload 结构、以及引用（`citations`）在流式模式下是在流中途给出还是只在最后一个事件里给出，OpenAPI 规范对 `/answer` 没有像 `/search` 那样给出 `AnswerStreamChunk` 的详细 schema 说明（对比：`/search` 的 stream 分支有独立的 `SearchStreamChunk` schema）。

## OpenAI 兼容接口

`/answer` 还可以通过 OpenAI 的 Chat Completions 接口形态调用：把 `base_url` 换成 `https://api.exa.ai`、`model` 传字符串 `"exa"`，用 `extra_body` 传 Exa 专属参数（如 `text: true`）：

```python
from openai import OpenAI

client = OpenAI(base_url="https://api.exa.ai", api_key=EXA_API_KEY)
completion = client.chat.completions.create(
    model="exa",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What are the latest developments in quantum computing?"},
    ],
    extra_body={"text": True},
)
```

文档原文明确："`/chat/completions` routes to `/answer`"——这不是一个独立实现，只是同一个 `/answer` 端点的另一层协议外壳，鉴权、计费、错误行为预期应该一致（⚠ 未实测确认是否完全一致）。

## 注意事项汇总

- `answer` 字段类型随 `outputSchema` 是否传而在字符串/对象之间切换，解析代码要按这个分支处理，不能写死成字符串。
- `citations[].text` 默认不存在，要 `text: true` 才会带正文，容易被当成"citations 默认应该有正文摘录"。
- 错误信封是扁平结构 `{"requestId", "error", "tag"}`，和 `/search`/`/contents` 一致，和 Agent API 的嵌套结构不同（见 `references/errors-and-limits.md`）。
- `model` 四选项之间的实际差异未在文档里说明，选型前建议先用默认 `exa` 测试是否够用，再考虑升级到 `exa-pro`/`exa-research`。
- 402（无信用额度/预算超限）和 429（限流）与其他端点共用同一套错误码表。
