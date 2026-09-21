# Exa Agent：`POST /agent/runs` 及配套接口

> ⚠ 本文件全部内容整理自官方文档（https://docs.exa.ai/agent/quickstart 、`/docs/agent/best-practices`）与 OpenAPI 规范（`Agent` 分组，7 个 endpoint），**未经真实 API 调用验证**。这是文档站里除 Search/Contents/Answer 外最突出的"研究/Agent"产品面（一级导航、独立 quickstart + best-practices + examples 三篇文档），本 skill 按任务要求重点覆盖；比它更大的 Websets（`/v0/websets/*`，39 个 endpoint）未覆盖，见 `SKILL.md` 导航表。

目录：[何时用 Agent 而不是 Search](#何时用-agent-而不是-search) · [创建 run](#创建-run) · [轮询与 SSE](#轮询与-sse) · [effort 与定价](#effort-与定价) · [结构化输出与 grounding](#结构化输出与-grounding) · [input.data / input.exclusion](#inputdata--inputexclusion) · [Exa Connect 数据源](#exa-connect-数据源) · [续接、取消、停止、删除](#续接取消停止删除) · [Zero Data Retention](#zero-data-retention) · [错误结构](#错误结构) · [注意事项汇总](#注意事项汇总)

## 何时用 Agent 而不是 Search

文档原文的判断标准："Exa Agent is higher-latency and async by design. For a single low-latency search where you orchestrate the calls yourself, start with the Search API."

用 Agent 的场景：从开放式条件建列表并逐条富化；对一个已知实体做多字段研究并要求引用；"先找到 A，再找 A 的决策者"这类多跳任务；从长耗时网络研究产出结构化 JSON；把网络检索和 Exa Connect 的第三方数据源合并成一份有依据的结果；基于上一次 run 的结果追加请求（"再找 10 个"）。

## 创建 run

**Endpoint**: `POST https://api.exa.ai/agent/runs`
**用途**: 创建一个异步 Agent run。**默认立即返回 run 对象**（`status: "queued"`），不是等跑完再返回——这是本文件最重要的一条认知，见 `SKILL.md` 跨领域规则第 10 条。

**关键参数**（请求体顶层）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | — | 自然语言问题/指令 |
| `effort` | enum | 否 | `auto` | `minimal`/`low`/`medium`/`high`/`xhigh`/`auto`/`max`，见下节 |
| `systemPrompt` | string | 否 | — | 指导行为：信源偏好、去重、新颖性约束 |
| `input.data` | array\<object\> | 否 | — | 待处理/富化的现有记录 |
| `input.exclusion` | array\<object\> | 否 | — | 明确要排除的记录/实体 |
| `outputSchema` | object 或 null | 否 | — | JSON Schema（支持 draft-07/2019-09/2020-12），驱动 `output.structured` |
| `previousRunId` | string | 否 | — | 续接某个已完成 run 的上下文，发起一个**新** run（不会复用旧 run 的 ID） |
| `metadata` | object | 否 | — | 调用方自定义的追踪信息，原样存储 |
| `dataSources[].provider` | enum | 否 | — | `fiber`/`financial_datasets`/`similarweb`/`baselayer`/`affiliate`/`particle`/`jinko`/`polymarket`，见"Exa Connect"节 |
| `budget.maxCostDollars` | number | 否 | `auto`→$5，`max`→$20 | 仅对 `auto`/`max` 生效，取值 $1–$100，是**上限**不是固定价，提前完成则少花 |

**请求头**

| Header | 说明 |
|---|---|
| `Accept: text/event-stream` | 走 SSE 而不是一次性 JSON 响应 |
| `Exa-Beta: agent-max-effort-2026-07-27` | 使用 `effort: "max"`（Beta）必须带这个 token |

**示例请求**

```bash
curl -s -X POST "https://api.exa.ai/agent/runs" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EXA_API_KEY" \
  -d '{
    "query": "Find engineering leaders at AI infrastructure companies that raised a Series A or B in the last 6 months.",
    "effort": "auto",
    "outputSchema": {
      "type": "object",
      "properties": {
        "people": {
          "type": "array",
          "maxItems": 10,
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "job_title": {"type": "string"},
              "linkedin_url": {"type": "string", "format": "uri"}
            },
            "required": ["name", "job_title", "linkedin_url"]
          }
        }
      },
      "required": ["people"]
    }
  }'
```

```python
from exa_py import Exa

exa = Exa()
run = exa.agent.runs.create(
    query="Find engineering leaders at AI infrastructure companies that raised a Series A or B in the last 6 months.",
    output_schema={...},  # 同上
    effort="auto",
)
```

**示例响应**（创建成功，⚠ 文档原文，未实测）：返回一个 `status: "queued"` 的 run 对象，`id` 形如 `agent_run_01j...`。⚠ 文档未说明：`status: "queued"` 时 `output`/`usage`/`costDollars` 这几个响应 schema 里标为必填的字段具体是什么值（空字符串？零值？全部省略但 schema 仍标 required？）——OpenAPI 规范把它们标成 required，但创建请求的例子只给了请求体没给创建时刻的响应体，是 P1 验证项。

## 轮询与 SSE

不用 SSE 时，保存返回的 `id`，轮询 `GET /agent/runs/{id}` 直到 `status` 变成终态（`completed`/`failed`/`cancelled`）：

```python
run = exa.agent.runs.poll_until_finished(run_id, poll_interval=4000)
print(run.output.structured if run.output else None)
```

```bash
while true; do
  RUN_JSON="$(curl -s "https://api.exa.ai/agent/runs/$RUN_ID" -H "Authorization: Bearer $EXA_API_KEY")"
  STATUS="$(echo "$RUN_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ] && { echo "$RUN_JSON"; break; }
  sleep 4
done
```

或在创建请求上加 `Accept: text/event-stream`（或 SDK 的 `stream=True`），保持连接直到 run 到达终态：

| 事件 | `data` payload | 用途 |
|---|---|---|
| `agent_run.created` | `{id, status: "queued", createdAt}` | 请求被接受即拿到 run ID |
| `agent_run.started` | `{id, status: "running"}` | 开始处理 |
| `agent_run.completed` | 完整的 run 对象 | 从 `data.output.text`/`.structured` 读结果，`data.output.grounding` 读引用 |
| `agent_run.failed` | `{id, status: "failed", error}` | 用 `error.code`/`error.message`，没有 `output` |
| `agent_run.cancelled` | `{id, status: "cancelled", ...}` | 停止消费流 |

⚠ 文档原文特别提醒：`agent_run.source.added` 事件只是"实时预览"，不是最终引用列表，**权威的引用以终态事件的 `output.grounding` 为准**；同一研究步骤的事件靠 `callId` 关联，"部分检索轨迹描述是异步生成的，可能晚于它描述的来源/工具事件到达"——不能靠事件到达顺序做关联。未识别的事件名要向前兼容忽略，不要因为遇到新事件类型就报错中断。

**回放已存储事件**：`GET /agent/runs/{id}/events`，非 ZDR run 才可用；`Accept: text/event-stream` 以 SSE 回放，`Last-Event-ID` 跳过已处理的事件；回放只发送"请求时刻已落盘的事件"然后关闭连接，**不会**继续跟随一个仍在运行的 run。

## effort 与定价

| `effort` | 单价 | 适用场景（文档原文） |
|---|---|---|
| `minimal` | $0.012/次 | 成本最低的查找，非常窄的事实性任务，短答案 |
| `low` | $0.025/次 | 简单查找，窄事实任务 |
| `medium` | $0.10/次 | 大多数标准研究任务的默认起点 |
| `high` | $0.50/次 | 更难的研究，更多引用，更严格的完整性 |
| `xhigh` | $1.00/次 | 完整性优先于成本/延迟的高价值任务 |
| `auto`（默认） | 按用量计费，默认封顶 $5 | 范围不确定的任务（建列表等） |
| `max`（Beta，需 `Exa-Beta` 头） | 按用量计费，默认封顶 $20 | 最高强度研究 |

固定 effort 是"每次请求一口价"；`auto`/`max` 是"按 ACU（Agent Compute Unit，$0.10/单位）+ 检索次数（$0.005/次）+ 联系方式富化（邮箱 $0.02/个、电话 $0.07/个）计量，封顶不超过 `budget.maxCostDollars`"。`budget` 只对 `auto`/`max` 生效，固定 effort 不接受 `budget`。

## 结构化输出与 grounding

完成的 run 包含：

- `output.text`：自然语言答案/摘要
- `output.structured`：符合 `outputSchema` 的校验后 JSON；**没传 `outputSchema` 时是 `null`**；schema 里"证据不支持的字段可能返回 `null`"——即使字段在 `required` 里，证据不足时也可能拿到 `null` 而不是报错，⚠ 文档原文未细说这和 `required` 的校验关系怎么处理
- `output.grounding[]`：`{field, citations[], confidence}`，`field` 用点路径/下标指向 `output.structured` 里的具体字段（如 `companies[0].funding`）

文档给的验证类任务最佳实践：schema 里可能验证不到的字段设为 nullable 且不放进 `required`，让 agent 在证据不足时返回 `null` 而不是编造；用一个三态枚举（如 `present`/`absent`/`cannot_verify`）区分"核实后确认不存在"和"核实失败"——"网站打不开"不等于"没有这个页面"的证据。

## `input.data` / `input.exclusion`

- `input.data`：已有的一批记录，让 Agent 逐条富化字段或基于这些记录发现更多实体。
- `input.exclusion`：明确排除的记录/实体（比如"列出最可爱的动物，但排除山羊和熊猫"）。

两者都是"任意 JSON 值数组"（`array<object>`，每个元素是自由形态的 key-value），没有固定 schema，具体怎样的记录形状最容易被 Agent 正确理解，⚠ 文档未给出字段命名规范，需按具体任务设计。

## Exa Connect 数据源

`dataSources[].provider` 接入第三方付费数据源，让 Agent 在网页检索之外调用专属工具，无需在 `dataSources` 之外单独开关"网页检索"（网页索引始终可用）：

| provider | 数据 | 计价（文档另页） |
|---|---|---|
| `fiber` | Fiber.ai 的 B2B 公司/人物/LinkedIn 数据库 | $0.02/credit |
| `financial_datasets` | 27,000+ 美股代码的结构化财务/市场数据 | 见 Connect 定价页 |
| `similarweb` | 网站流量、全球排名、竞品发现 | 见 Connect 定价页 |
| `baselayer` | 美国企业核验/KYB（高管、注册信息、风险分） | $0.15–$4.00/order（按操作类型） |
| `affiliate` | 跨商户/联盟网络的商品目录 | 见 Connect 定价页 |
| `particle` | 播客转录（含说话人和时间戳） | 见 Connect 定价页 |
| `jinko` | 航班/酒店搜索与实时价格 | 见 Connect 定价页 |
| `polymarket` | 预测市场赔率、历史价格、订单簿、持仓 | 见 Connect 定价页 |

每个 `dataSources` 条目**启用该 provider 的全部工具**（"Each entry enables all of that provider's tools"），不能只挑 provider 下的某个子工具。`outputSchema` 里某个字段如果明确写了"来自 Similarweb"这类描述，Agent 会优先调对应 provider 工具而不是靠网页猜——即数据源的选用一定程度上由 schema 描述驱动，不是显式路由参数。这几个 provider 的定价和字段细节本 skill 未展开，需要时读 `/docs/agent/connect/<provider>.md`。

## 续接、取消、停止、删除

| 操作 | Endpoint | 语义 |
|---|---|---|
| 续接 | `previousRunId` 传入 `POST /agent/runs` | 把上一个已完成 run 的上下文带入**新** run，新 run 有自己的 `id`；`previousRunId` 必须属于同一个 team，否则 `PREVIOUS_RUN_NOT_FOUND`；对方 run 未完成会报 `PREVIOUS_RUN_NOT_COMPLETED` |
| 取消 | `POST /agent/runs/{id}/cancel` | 立即终止排队中或运行中的 run，**不返回任何结果**；已消耗的用量仍计费；对已是终态的 run 调用会直接返回该 run 现状而不报错 |
| 提前完成 | `POST /agent/runs/{id}/stop` | 让运行中的 run 提前收尾，**返回已收集到的部分结果**（区别于 cancel 的"不返回结果"）；文档原文写明**目前只支持 `max` effort 的 run**，且同样要求 `Exa-Beta: agent-max-effort-2026-07-27` 头；已是终态的 run 调用同样直接返回现状 |
| 删除 | `DELETE /agent/runs/{id}` | 删除已存储的 run 记录；响应 `{id, object, deleted: true}` |
| 查找 run ID | `GET /agent/runs?limit=&cursor=` | 按创建时间倒序分页列出团队的 run，`hasMore`/`nextCursor` 做游标分页 |

`cancel` 和 `stop` 的区别是本文件里最容易搞混的一对：**cancel 直接放弃、不给结果；stop 只对 `max` effort 生效、给部分结果**——用 `cancel` 去"优雅收尾拿部分结果"是错的用法。

## Zero Data Retention

ZDR 按团队开启（需联系销售）。开启后：用 SSE 实时消费输出，或在留存窗口内轮询；run 数据在执行期间可用，终态后**只保留 10 分钟**，之后不可再取；`previousRunId` 不可用；`dataSources` 不可用（带了直接 400）。

## 错误结构

**Agent API 的错误信封和 Search/Contents/Answer 不同**（本 skill 认为是最容易踩的坑之一，已升到 `SKILL.md` 跨领域规则第 5 条）：

```json
{
  "error": {
    "type": "INVALID_REQUEST",
    "code": "INVALID_OUTPUT_SCHEMA",
    "message": "..."
  }
}
```

| `error.type` | 覆盖的 `error.code` 示例 |
|---|---|
| `INVALID_REQUEST` | `INVALID_REQUEST`、`INVALID_OUTPUT_SCHEMA`、`INVALID_DATA_SOURCE` |
| `AUTHENTICATION_ERROR` | 团队/鉴权上下文缺失 |
| `RATE_LIMIT_ERROR` | 含 `CONCURRENCY_LIMIT_REACHED`（50 个并发 run 上限） |
| `NOT_FOUND` | `TEAM_NOT_FOUND`、`RUN_NOT_FOUND`、`PREVIOUS_RUN_NOT_FOUND` |
| `SERVER_ERROR` | 服务端错误或 run 超时；也覆盖 `PREVIOUS_RUN_NOT_COMPLETED`、`TIMEOUT` |

## 注意事项汇总

- 创建 run 默认异步返回 `status: "queued"`，必须轮询或 SSE 才能拿到结果，不是同步等待。
- `POST /agent/runs` 按 **2 次请求**计入团队 QPS（`GET` 轮询/列表/事件不计入 QPS）；并发上限独立于 QPS，是 50 个同时进行的 run。
- `effort: "max"` 和 `POST .../stop` 都需要 `Exa-Beta: agent-max-effort-2026-07-27` 请求头，不带头会被拒绝（文档写"requests with effort: max must include..."，具体拒绝的错误码未说明）。
- `budget.maxCostDollars` 只对 `auto`/`max` 生效，固定 effort（`minimal`…`xhigh`）传 `budget` 会怎样文档未说明。
- `cancel` 不返回结果，`stop` 返回部分结果但只对 `max` effort 开放——不要把两者当作同一个"提前结束"操作的两种叫法。
- 错误信封是嵌套的 `{"error": {"type", "code", "message"}}`，和 Search/Contents/Answer 的扁平 `{"requestId", "error", "tag"}` 不兼容，不能共用同一个错误解析器。
- ZDR 开启后 `previousRunId` 和 `dataSources` 都不可用，终态后仅保留 10 分钟可查询。
