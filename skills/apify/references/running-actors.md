# 启动 Actor：同步/异步、输入、run 生命周期

> 全篇内容来自 Apify 官方 OpenAPI 规范（`docs.apify.com/api/openapi.json`）和 `docs.apify.com/actors/running*` 系列文档页（抓取于 2026-09-21）。**没有经过真实 API 调用验证**，行为性描述统一标 `⚠ 文档原文，未实测`。

目录：
- [三种启动方式怎么选](#三种启动方式怎么选)
- [异步启动：POST /v2/actors/{actorId}/runs](#异步启动post-v2actorsactoridruns)
- [同步启动：run-sync 系列](#同步启动run-sync-系列)
- [Run 对象与生命周期状态](#run-对象与生命周期状态)
- [Run 相关操作：get / abort / resurrect / reboot](#run-相关操作get--abort--resurrect--reboot)
- [Actor Task：把输入配置保存下来复用](#actor-task把输入配置保存下来复用)
- [用 apify-client 而不是裸 HTTP](#用-apify-client-而不是裸-http)

## 三种启动方式怎么选

| 方式 | Endpoint | 特点 | 适合场景 |
|---|---|---|---|
| 异步启动 | `POST /v2/actors/{actorId}/runs` | 立即返回 run 对象（通常是 `READY`/`RUNNING` 状态），不等待完成 | 长任务、需要轮询/webhook 通知、需要在多个 run 之间并发调度 |
| 同步 + 拿 KV 记录 | `POST/GET /v2/actors/{actorId}/run-sync` | 阻塞等待 run 结束（最长 300 秒），响应体是 run 默认 key-value store 里 `OUTPUT` 记录的原始内容 | 遗留模式，Actor 只往 KV store 写单条结果（如一次计算、一张截图）时用；官方文档称其为"legacy approach"，已被下方的 Actor output schema 机制取代 |
| 同步 + 拿数据集条目 | `POST/GET /v2/actors/{actorId}/run-sync-get-dataset-items` | 阻塞等待 run 结束（最长 300 秒），响应体直接是 dataset items 数组 | 短任务（几十秒内能出结果），想要"一次 HTTP 调用直接拿到抓取结果"，不想自己写轮询逻辑 |

`⚠ 文档原文，未实测`：两个 `run-sync*` 端点都受 `MAX_ACTOR_JOB_SYNC_WAIT_SECS = 300` 秒硬限制，超过这个时间 HTTP 请求本身会报超时错误——但**这不等于把后台的 run 中止了**，run 依然在继续跑，只是这次 HTTP 请求拿不到结果了。如果要在超时后仍然拿到结果，需要自己记下这次调用产生的 run（响应头或者切到异步方式），再用 `GET /v2/actor-runs/{runId}` 查。

Actor 路径可以用三种写法：数字/字母 ID（如 `HDSasDasz78YcAPEB`）、`username~actor-name`（如 `apify~website-content-crawler`）、或旧式 `/v2/acts/...` 前缀（已废弃但仍可用，等价于 `/v2/actors/...`）。

## 异步启动：`POST /v2/actors/{actorId}/runs`

**用途**：启动一个 Actor，立刻返回，不等待完成。

**Endpoint**: `POST /v2/actors/{actorId}/runs`

**路径参数**
| 参数 | 说明 |
|---|---|
| `actorId` | Actor ID 或 `username~actor-name` |

**Query 参数**
| 参数 | 类型 | 说明 |
|---|---|---|
| `timeout` | number | 本次 run 的超时秒数，不传则用 Actor 自身配置的默认值 |
| `memory` | number | 内存 MB，必须是 2 的幂，最小 128。不建议随意改，除非 Actor 文档明确建议 |
| `maxItems` | number | 仅对"按结果条数付费"的老式 pay-per-result Actor 生效，封顶计费条目数（**不保证**实际只返回这么多条，只保证不为超出部分收费） |
| `maxTotalChargeUsd` | number | 封顶这次 run 的总花费（跨所有定价模型都生效），Actor 内部可通过环境变量 `ACTOR_MAX_TOTAL_CHARGE_USD` 读到 |
| `restartOnError` | boolean | run 失败时是否自动重启 |
| `build` | string | 指定 build tag 或 build number，不传则用 Actor 配置里的默认 build（通常是 `latest`） |
| `waitForFinish` | number | 最长等待多少秒（0–60）。在这个时间内跑完，返回的 run 对象会是终态（如 `SUCCEEDED`）；没跑完就返回当前的过渡态（如 `RUNNING`）。**这不是真正的同步调用**，上限只有 60 秒，比 `run-sync` 的 300 秒短很多 |
| `webhooks` | string | Base64 编码的 JSON 数组，一次性（ad-hoc）webhook 定义，见 `references/webhooks.md` |
| `forcePermissionLevel` | string，枚举 `LIMITED_PERMISSIONS`/`FULL_PERMISSIONS` | 临时覆盖这次 run 的权限级别 |

**请求体**：Actor 的输入 JSON（`Content-Type: application/json`），具体字段由该 Actor 自己的 input schema 决定，不在本 skill 范围内——运行前去该 Actor 的 Store 页面 Input 标签页查。

**示例请求**
```bash
curl -X POST "https://api.apify.com/v2/actors/apify~website-content-crawler/runs?token=$APIFY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"startUrls": [{"url": "https://apify.com"}]}'
```
```python
import os, requests

resp = requests.post(
    "https://api.apify.com/v2/actors/apify~website-content-crawler/runs",
    params={"token": os.environ["APIFY_API_TOKEN"]},
    json={"startUrls": [{"url": "https://apify.com"}]},
)
run = resp.json()["data"]
print(run["id"], run["status"], run["defaultDatasetId"])
```

**示例响应**（201，节选关键字段，完整字段见下方"Run 对象"）
```json
{
  "data": {
    "id": "HG7ML7M8z78YcAPEB",
    "actId": "HDSasDasz78YcAPEB",
    "status": "READY",
    "defaultDatasetId": "wmKPijuyDnPZAPRMk",
    "defaultKeyValueStoreId": "eJNzqsbPiopwJcgGQ",
    "defaultRequestQueueId": "FL35cSF7jrxr3BY39"
  }
}
```

**注意事项**
- 响应里的 `defaultDatasetId` / `defaultKeyValueStoreId` / `defaultRequestQueueId` 是这次 run 专属的存储，用于下一步读结果（见 `references/reading-run-output.md`）——**必须保存下来**，之后不能反查。
- 402（Payment required）表示用量超限、余额不足，或者这是一次没有鉴权/支付凭证的 agentic 调用——`⚠ 文档原文，未实测`。

## 同步启动：`run-sync` 系列

**Endpoint**: `POST/GET /v2/actors/{actorId}/run-sync-get-dataset-items`

**用途**：启动 Actor，阻塞等待跑完（最长 300 秒），响应体直接是 dataset 条目数组本身——**不是** `{"data": [...]}` 信封，也不是 run 对象。

**关键参数**：除了和异步启动相同的一套（`timeout`/`memory`/`maxItems`/`maxTotalChargeUsd`/`restartOnError`/`build`/`webhooks`，没有 `waitForFinish`，因为整个调用本身就是"同步"的），还支持 `GET /v2/datasets/{datasetId}/items` 的全部格式化参数（`format`/`fields`/`omit`/`unwind`/`flatten`/`desc`/`clean`/`limit`/`offset` 等，见 `references/reading-run-output.md`）——即"启动 + 取数据集条目"一步到位。

**示例响应**（201）
```json
[
  { "myValue": "some value", "myOtherValue": "some other value" }
]
```

**Endpoint**: `POST/GET /v2/actors/{actorId}/run-sync`

**用途**：启动 Actor，阻塞等待跑完，响应体是这次 run 默认 key-value store 里 `OUTPUT` 记录的原始内容（可以用 `outputRecordKey` 参数换成别的 key，默认 `OUTPUT`）。**`⚠ 文档原文`：官方称这是被 Actor output schema 取代的 legacy 方式**——Actor 不一定会真的往 `OUTPUT` 这个 key 写东西，写没写完全取决于该 Actor 的实现，如果没写，响应就是空的。适合"这个 Actor 本来就只产出单条结果/一张截图/一份文件"的场景，不适合期待表格型结果的场景（那种用 `run-sync-get-dataset-items`）。

**注意事项**
- 两个 `run-sync*` 端点都没有 `Location` 响应头之类的 run 追踪信息（`⚠ 文档原文，未实测`，实际是否返回 run id 相关头未确认）——如果既想要同步拿结果、又想留一份 run id 供事后查询，更稳妥的做法可能是异步启动 + 轮询，而不是依赖 sync 端点。
- 网络中断导致连接断开时，run 本身在后台会继续跑完，但这次调用拿不到结果——需要长连接超时配置足够宽松，见端点文档原文提示。

## Run 对象与生命周期状态

**状态机**（来自 `docs.apify.com/actors/running/runs-and-builds.md`）：

| 状态 | 类型 | 含义 |
|---|---|---|
| `READY` | 初始 | 已创建，还没分配到 worker |
| `RUNNING` | 过渡 | 正在某台 worker 上执行 |
| `SUCCEEDED` | 终态 | 成功结束 |
| `FAILED` | 终态 | 失败 |
| `TIMING-OUT` | 过渡 | 正在超时中 |
| `TIMED-OUT` | 终态 | 已超时 |
| `ABORTING` | 过渡 | 正在被中止 |
| `ABORTED` | 终态 | 已被中止 |

**⚠ 这是本 skill 最重要的一条跨领域规则（也写进了 SKILL.md）：`status === "SUCCEEDED"` 只代表 Actor 进程正常退出（platform 层面的"成功"，类似 exit code 语义），不代表业务上真的抓到了想要的数据。** 目标网站把请求全部拦截、搜索词没有匹配结果，Actor 代码完全可以在这些情况下正常调用 `Actor.exit()` 并得到 `SUCCEEDED`。要判断这次 run 是否真正达成目的，除了 `status`，还要看：
- `statusMessage` / `isStatusMessageTerminal`：Actor 自己上报的状态消息，部分 Actor 会在这里说明"0 条结果"之类的情况；
- `exitCode`：Actor 进程的退出码；
- **实际检查 `defaultDatasetId` 对应数据集的条目数量，或者 `defaultKeyValueStoreId` 里 `OUTPUT` 记录的内容是不是空的。**

Run 对象核心字段（`GET /v2/actor-runs/{runId}` 或任意启动端点的响应）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | run 的唯一 ID |
| `actId` | string | 被运行的 Actor ID |
| `actorTaskId` | string\|null | 若是通过 task 启动，这里是 task ID |
| `status` | string，枚举见上表 | 当前状态 |
| `statusMessage` | string\|null | Actor 自报的状态说明 |
| `isStatusMessageTerminal` | boolean\|null | `statusMessage` 是否已是最终消息 |
| `meta.origin` | string，枚举 `DEVELOPMENT/WEB/API/SCHEDULER/TEST/WEBHOOK/ACTOR/CLI/CI/STANDBY/MCP` | 这次 run 是怎么被触发的 |
| `pricingInfo` | object | 定价模型信息（见 `references/pricing-and-billing.md`） |
| `stats.computeUnits` | number | 本次 run 消耗的 compute unit |
| `options.{build,timeoutSecs,memoryMbytes,diskMbytes,maxItems,maxTotalChargeUsd}` | object | 实际生效的运行参数 |
| `buildId` / `buildNumber` | string | 使用的 build |
| `exitCode` | number\|null | Actor 进程退出码 |
| `defaultDatasetId` / `defaultKeyValueStoreId` / `defaultRequestQueueId` | string | 这次 run 专属的三种默认存储 ID |
| `usage` | object | 原始用量单位（`ACTOR_COMPUTE_UNITS`/`DATASET_READS`/`PROXY_RESIDENTIAL_TRANSFER_GBYTES` 等） |
| `usageUsd` / `usageTotalUsd` | object / number | 上述用量换算成美元（**官方原话**：这个金额按查询时刻的当前单价折算，仅供参考，不代表最终精确账单） |
| `chargedEventCounts` | object | pay-per-event 定价下各事件被计费的次数 |
| `containerUrl` | string | 若该 Actor 内部起了 web server（Standby 模式），这是访问地址 |

**⚠ 文档原文，未实测**：`stats`/`usageTotalUsd` 等聚合字段在 run 刚结束时可能还没完全一致（最终一致性），官方建议 run 结束后等约 10 秒再查询，才能拿到准确的最终值。

## Run 相关操作：get / abort / resurrect / reboot

**⚠ 重要**：规范里 `/v2/actors/{actorId}/runs/{runId}` 这条路径下的 get/abort/metamorph 等操作都已标为 `[DEPRECATED]`，官方建议改用扁平命名空间 `/v2/actor-runs/{runId}/...`。**启动新 run 仍然用 `POST /v2/actors/{actorId}/runs`**（这个端点本身没有被废弃），只有"对一个已存在的 runId 做后续操作"才切到 `/v2/actor-runs/{runId}`。

| 操作 | Endpoint | 说明 |
|---|---|---|
| 查询 | `GET /v2/actor-runs/{runId}` | 不需要鉴权 token 也能查（用 run 的"难猜 ID"本身当访问凭证），但不带 token 时某些字段会被隐藏（`⚠ 文档原文，未实测`，具体哪些字段未验证） |
| 中止 | `POST /v2/actor-runs/{runId}/abort?gracefully=<bool>` | 只对 `READY`/`RUNNING`/`TIMING-OUT` 状态的 run 生效，其余状态调用无效果。默认立即杀死进程；`gracefully=true` 时会先给 Actor 发 `aborting` 和 `persistState` 事件，30 秒宽限期后才强制终止——打算之后 resurrect 这次 run 的话应该用 gracefully 版本，让 Actor 有机会持久化状态 |
| 复活 | `POST /v2/actor-runs/{runId}/resurrect` | 把处于终态（`SUCCEEDED`/`FAILED`/`ABORTED`/`TIMED-OUT`）的 run 重新拉回 `RUNNING`，容器用同一份存储重启；可以在复活时顺带调整 `timeout`/`memory`/`build`（比如先中止一个跑挂了的 run，改好代码重新 build，再 resurrect 到新 build 上） |
| 重启容器 | `POST /v2/actor-runs/{runId}/reboot` | 保留同一个 run，只重启容器（不同于 resurrect，不改变终态判定） |
| 更新 | `PUT /v2/actor-runs/{runId}` | 修改 run 的部分可变属性 |
| 删除 | `DELETE /v2/actor-runs/{runId}` | 删除 run 及其未命名的默认存储 |
| 查日志 | `GET /v2/actor-runs/{runId}/log` | 拉这次 run 的日志文本 |
| PPE 手动扣费 | `POST /v2/actor-runs/{runId}/charge` | 仅对 pay-per-event 定价的 Actor 有效，Actor 自身代码之外手动触发一次计费事件 |

`⚠ 文档原文，未实测`：`resurrect` 之后，`duration` 统计不包含"未运行的那段时间"，超时计时器从 resurrect 那一刻重新开始算。

## Actor Task：把输入配置保存下来复用

Task = 一个 Actor + 一份保存好的输入配置，本质是给同一个 Actor 存多套"预设参数"，方便重复触发而不用每次都传完整 input。Endpoint 前缀是 `/v2/actor-tasks/{actorTaskId}/...`，运行方式和 Actor 完全对应（`runs`、`run-sync`、`run-sync-get-dataset-items`、`runs/last`）：

```bash
curl -X POST "https://api.apify.com/v2/actor-tasks/$TASK_ID/run-sync-get-dataset-items?token=$APIFY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"maxCrawlPages": 5}'
```

**注意事项**：POST 请求体里传的字段只会覆盖 task 保存的默认输入里对应的字段，没传的字段沿用 task 保存的值（再没有就落回 Actor 自身 input schema 的默认值）——不是"完全替换"整份输入，这一点和直接调 Actor（第一次就必须给出完整 input）不同。

## 用 apify-client 而不是裸 HTTP

绝大多数场景直接用官方 client 库比手写 HTTP 更省事，它内建了"启动 + 等待完成 + 读结果"的便捷方法：

**JavaScript**（`npm install apify-client`）
```javascript
import { ApifyClient } from 'apify-client';

const client = new ApifyClient({ token: process.env.APIFY_API_TOKEN });

// call() = 启动 Actor 并等待跑完（内部调用 Run Actor + 轮询，不是 run-sync 端点）
const run = await client.actor('apify/website-content-crawler').call({
  startUrls: [{ url: 'https://apify.com' }],
});

const { items } = await client.dataset(run.defaultDatasetId).listItems();
console.log(items);
```

**Python**（`pip install apify-client`）
```python
import os
from apify_client import ApifyClient

client = ApifyClient(os.environ["APIFY_API_TOKEN"])

run = client.actor("apify/website-content-crawler").call(
    run_input={"startUrls": [{"url": "https://apify.com"}]}
)

items = client.dataset(run["defaultDatasetId"]).list_items().items
print(items)
```

**注意事项**
- `.call()` 内部是"调用 `POST /v2/actors/{actorId}/runs` 异步启动 + 轮询直到终态"，**不是**走 `run-sync` 端点，所以没有 300 秒硬限制，但也意味着会产生多次轮询请求。
- Python 侧还提供 `ApifyClientAsync`（`asyncio` 风格），JS 侧的 client 本身就是 Promise-based。
- `⚠ 文档自相矛盾`：`docs.apify.com/storage.md` 页面写"Python SDK 需要 Python 3.8 及以上"，但 `docs.apify.com/sdk/python/docs/overview.md` 页面写"Python SDK 需要 Python 3.11 及以上"——这是两处官方文档互相矛盾（注意这里说的是 **Actor 开发用的 `apify` SDK**，不是本文说的 `apify-client`；`apify-client` 本身的 Python 版本要求未在抓取的页面中明确写出，`⚠ 文档未说明`）。写代码前建议按较严格的 3.11+ 为准，或实测确认。
