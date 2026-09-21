---
name: apify
description: 接入 Apify（apify.com / docs.apify.com）平台的 API 使用手册——一个以 Actor（预制或自建的爬虫/自动化程序）为核心的大型 Web 抓取与自动化市场，本 skill 覆盖跑通任意 Actor 所需的平台机制：运行 Actor（同步/异步、传输入、run 生命周期与状态）、从 Dataset/Key-value store 读结果、Request Queue API、Webhooks、从 Store 挑选 Actor、以及按 compute unit 计费的定价模型。当用户提到 "Apify" "apify.com" "docs.apify.com" "api.apify.com" "apify-client" "Apify SDK" "Actor"（在 Apify 语境下）"Apify Store" "compute unit" "CU 计费"，或要写代码调用 Apify 平台 API / 运行某个 Apify Actor 时，应主动使用本技能，不要凭记忆编造字段名、把 Apify Client SDK 和 Apify SDK（Crawlee 的 Actor 打包工具）搞混，也不要套用 Firecrawl/Exa/Tavily 那种"每次调用固定 credits"的直觉去估算 Apify 的成本。不覆盖：如何挑选/评价某个具体第三方 Actor 的好坏（本 skill 只讲怎么用 Store 搜索机制找 Actor，不做 Actor 目录）；如何用 Apify SDK / Crawlee 自己开发一个 Actor（本 skill 只覆盖"调用别人写好的 Actor"这一侧的平台 API）。
---

# Apify 平台接入指南

Apify（docs.apify.com）是一个以 **Actor**（跑在 Apify 云端 Docker 容器里的爬虫/自动化程序，有数千个由社区发布在 Apify Store 里）为核心的大型 Web 抓取与自动化平台，外加一个通用的 REST API 层，用来运行任意 Actor、拉取它的输出、管理存储、配置 webhook。

**本 skill 的定位很窄，是故意的**：Apify Store 里有数千个第三方 Actor，各自的输入 schema、输出字段、定价完全不同，不可能也不应该在这里逐一收录。本 skill 只覆盖"不管跑哪个 Actor,都要用到的平台机制"——怎么发起一次 run、怎么判断它是否真的跑成功、怎么把结果取出来、怎么算钱。选定具体 Actor 之后,该 Actor 自己的输入字段要去它在 Store 里的页面查（`GET /v2/acts/{actorId}` 或 Actor 详情页的 Input 标签页），不属于本 skill 范围。

## ⚠ 验证状态

**本 skill 的第 1、2 步（抓取文档 + 结构化撰写）已完整做完，但第 3 步（用真实 API key 逐条验证）尚未进行——写作时没有可用的 Apify API token。**

- 所有字段名、参数、端点行为、状态码、定价数字均来自 **Apify 官方 OpenAPI 规范**（`docs.apify.com/api/openapi.json`，`info.version: v2-2026-09-10T091137Z`，抓取于 2026-09-21）和 **docs.apify.com 官方文档页面原文**（同日抓取），不是凭训练记忆编写的。
- 但是：**没有一条结论经过真实调用验证**。每个 reference 文件里的行为性描述都标了 `⚠ 文档原文，未实测`；文档字面写的"必填"是否真的报错、"默认值"是否真的生效、静默失效还是抛错——这些统统未知，规范和真实行为不一致的情况在其他平台上已经反复出现过。
- 验证计划见 `apify-workspace/verification-plan.md`，拿到 key 后按优先级逐条测,测完把对应 reference 里的 `⚠ 文档原文，未实测` 改写成"已用真实 API 验证（日期）：……"并附原始响应/报错。
- `evals/evals.json` 里的场景是基于文档字面推测的"有经验开发者会凭直觉写错"的陷阱,同样未经真实调用验证評分,仅供后续对照实验使用。

## 用之前先确认的几件事

1. **Base URL 固定为 `https://api.apify.com/v2`。** 文档站自己的 API reference 挂在 `docs.apify.com/api/v2`，但那是文档,真正发请求要打 `api.apify.com`。存在一个已废弃但仍可用的 `/v2/acts/` 前缀,和 `/v2/actors/` 等价,新代码一律用 `/v2/actors/`。
2. **鉴权**：`Authorization: Bearer <APIFY_API_TOKEN>` header（推荐），或 `?token=<APIFY_API_TOKEN>` query 参数（不推荐,会留在浏览器历史/服务器日志里）。Token 在 Apify Console 的 **Settings → Integrations** 页面拿。公开资源的**只读 GET**请求可以不带 token（比如公开 Actor 的信息、通过一个"难猜的" run ID 读它的 run 详情/存储）,但**创建型/修改型请求、以及用 `username~resourcename` 这种命名法引用资源时必须带 token**。
3. **两套完全不同的东西都叫"Apify SDK",名字撞车,极易选错包**（详见下方"跨领域通用规则"第 1 条）：
   - **调用平台 API（本 skill 覆盖的场景）** → 装 **`apify-client`**（JS: `npm install apify-client`；Python: `pip install apify-client`）。
   - **自己开发一个跑在平台上的 Actor**（本 skill 不覆盖）→ 装 **`apify`**（JS: `npm install apify`；Python: `pip install apify`，这个包官方也叫"Apify SDK"）,通常还会配合通用爬虫框架 **Crawlee**（`npm install crawlee` / `pip install crawlee`）。
4. **一次 run 到底花多少钱,不能按"一次调用固定 X 个 credit"估算**——不同 Actor 的定价模型完全不同（免费用量、按平台用量付费、按开发者自定义事件付费、包月租用四选一，只有部分是"发布者规定的固定单价"）,同一个 Actor 跑不同任务时实际耗时/耗资源也天差地别。开跑前一定看该 Actor 的 Store 页面 Pricing 区块,预算敏感场景用 `maxTotalChargeUsd` 参数封顶。详见 `references/pricing-and-billing.md`。

## 30 秒跑通第一个请求

同步跑一个 Actor 并直接拿到它的结果（数据集里的条目）,不用自己轮询 run 状态：

```bash
curl "https://api.apify.com/v2/acts/apify~website-content-crawler/run-sync-get-dataset-items?token=$APIFY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"startUrls": [{"url": "https://apify.com"}], "maxCrawlPages": 1}'
```

```python
import os, requests

token = os.environ["APIFY_API_TOKEN"]
actor_id = "apify~website-content-crawler"  # username~actor-name 形式
resp = requests.post(
    f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items",
    params={"token": token},
    json={"startUrls": [{"url": "https://apify.com"}], "maxCrawlPages": 1},
)
items = resp.json()  # 直接是条目数组，不是 {"data": {...}} 信封
print(items)
```

`⚠ 文档原文，未实测`：这个同步端点最长等 300 秒（`MAX_ACTOR_JOB_SYNC_WAIT_SECS`），超时只是 HTTP 请求失败,**不会中止后台那次 run 本身**。生产环境批量跑、或单次任务可能超过几分钟时,应改用异步的 `POST /v2/actors/{actorId}/runs` + 轮询/webhook,见 `references/running-actors.md`。

## 能力域导航

| 我想做什么 | 读哪个文件 | 涉及的核心 endpoint |
|---|---|---|
| 启动一个 Actor（同步/异步）、传输入、判断 run 到底成没成功 | [`references/running-actors.md`](references/running-actors.md) | `POST /v2/actors/{actorId}/runs`、`.../run-sync`、`.../run-sync-get-dataset-items`、`GET /v2/actor-runs/{runId}` |
| 从一次已完成（或正在跑）的 run 里把结果取出来——表格型用 Dataset,单值/文件用 Key-value store | [`references/reading-run-output.md`](references/reading-run-output.md) | `GET /v2/datasets/{datasetId}/items`、`GET/PUT /v2/key-value-stores/{storeId}/records/{recordKey}` |
| 直接操作 Request Queue（一般用不到,只有自建爬取任务时才用） | [`references/request-queues.md`](references/request-queues.md) | `POST /v2/request-queues`、`.../requests/batch` |
| run 完成/失败时收到通知,而不是自己轮询 | [`references/webhooks.md`](references/webhooks.md) | `POST /v2/webhooks`、`?webhooks=` ad-hoc 参数 |
| 从 Apify Store 里搜/筛一个适合任务的 Actor | [`references/finding-actors.md`](references/finding-actors.md) | `GET /v2/store` |
| 搞清楚这次 run 会花多少钱、四种定价模型怎么选、compute unit 怎么算 | [`references/pricing-and-billing.md`](references/pricing-and-billing.md) | `GET /v2/users/me/usage/monthly`、`GET/PUT /v2/users/me/limits` |
| 查报错原因、分页约定、限流阈值 | [`references/errors-and-limits.md`](references/errors-and-limits.md) | 通用错误结构、`offset`/`limit`/`exclusiveStartKey` |

## 跨领域的通用规则（写代码前必读）

1. **"Apify Client SDK" ≠ "Apify SDK"，名字故意撞在一起,是最容易踩的坑。** `apify-client` 是从你自己的代码/服务器/agent **调用** Apify 平台 API 的客户端库（启动 run、读 storage）——绝大多数集成需要的就是这个。`apify`（JS 和 Python 包名都叫 `apify`，官方也管它叫 "Apify SDK"）是用来**编写一个跑在 Apify 平台上的 Actor 本体**的库（`Actor.init()` / `Actor.getInput()` / `Actor.pushData()` 这一套生命周期 API）,配合通用爬虫框架 Crawlee（`crawlee` 包,可以脱离 Apify 平台独立使用）。如果任务是"写代码调一个 Apify 上的 Actor",要的是 `apify-client`；如果任务是"自己写一个 Actor 发到 Apify 上",要的是 `apify` + 可能的 `crawlee`——这两件事的输入输出、鉴权方式、使用场景完全不同,搞混了代码根本跑不起来。本 skill 只覆盖前者。
2. **platform 层的 `status: SUCCEEDED` 不等于"这次抓取拿到了有意义的结果"。** Run 的 `status` 字段反映的是 Actor 进程有没有正常退出（类似 exit code 语义,而不是业务语义）——目标站点把 Actor 的请求全部拦截、或者压根没匹配到任何数据,Actor 代码依然可以正常退出并得到 `SUCCEEDED`。判断"这次任务有没有真正达成目的",除了看 `status`,还要看 `statusMessage`/`isStatusMessageTerminal`（Actor 自己上报的状态消息）、`exitCode`,以及**实际检查 dataset 的条目数量或 key-value store 里 `OUTPUT` 记录的内容是不是空的**。官方 Actor Output Schema 文档里专门提到"哪怕 Actor 没有任何输出也要定义一个空的 output schema,这样消费者才知道是'正常空结果'而不是'运行失败'"——反过来说明,默认情况下"空结果"和"运行失败"极易被混为一谈,不能仅凭 `status === 'SUCCEEDED'` 就断定拿到了想要的数据。见 `references/running-actors.md`。
3. **一个 Actor 的运行成本,不能按"每次调用固定花费"估算,这一点和 Firecrawl / Exa / Tavily 这类"每次调用固定几个 credit"的 API 完全不同。** Apify 计费的基本单位是 **compute unit（1 CU = 1GB 内存跑 1 小时）**,叠加数据传输、代理、存储读写等平台用量,再叠加 Actor 开发者自选的四选一定价模型（免费 / 纯平台用量 / 按开发者自定义事件收费 / 包月租用）。同一个任务换一个 Actor、甚至同一个 Actor 换一个目标站点,实际花费都可能差几倍到几十倍。不要把"调一次 API 大概几分钱"的直觉带过来,详见 `references/pricing-and-billing.md`。
4. **Dataset API 的分页默认值和大多数平台不一样：`limit` 参数文档原文写的是"默认不限制条数"（不像很多 API 默认给 20/50/100 条）,`offset` 默认 0。`⚠ 文档原文，未实测`——没有真实调用验证这个"无限制"在服务端是否真的没有隐藏上限,大数据集场景务必显式传 `limit` 分页读取,不要假设一次请求就能拿完。** Key-value store 的 `GET .../keys` 端点分页方式完全不同,用的是 `exclusiveStartKey` 游标（因为 key 按 UTF-8 二进制序排列,不是插入顺序）,不是 `offset`/`limit`——这两套存储 API 的分页语义不能混用。
5. **Run 相关的旧端点 `/v2/actors/{actorId}/runs/{runId}/...`（get/abort/metamorph/reboot 等）在当前 OpenAPI 规范里已标为 `[DEPRECATED]`，官方建议改用扁平的 `/v2/actor-runs/{runId}/...` 命名空间。** 但**发起一次新 run 仍然用 `POST /v2/actors/{actorId}/runs`**（这个端点本身不是废弃的）,只有"拿到 runId 之后对这次 run 做的后续操作"才应该切到 `/v2/actor-runs/{runId}` 这条路径,不要整体套用旧写法。
6. **同步端点（`run-sync`、`run-sync-get-dataset-items`）返回的响应体格式和异步端点完全不同：异步 `POST /v2/actors/{actorId}/runs` 返回的是包在 `{"data": {...run 对象...}}` 里的 run 元数据；`run-sync-get-dataset-items` 直接返回数据集条目数组本身,没有 `data` 信封；`run-sync` 返回的是 key-value store 里 `OUTPUT` 记录的原始内容（可能是任意 content-type,不一定是 JSON）。三者混用会导致解析代码直接崩掉。**

## 目录结构

```
apify/
├── SKILL.md
├── references/
│   ├── running-actors.md       # 启动 Actor（同步/异步）、输入、run 生命周期与状态、Actor tasks
│   ├── reading-run-output.md   # Dataset API（结果条目、分页、格式转换）+ Key-value store API（OUTPUT 记录、文件）
│   ├── request-queues.md       # Request Queue API（何时需要直接操作它）
│   ├── webhooks.md             # 标准 webhook + ad-hoc webhook,run 完成通知
│   ├── finding-actors.md       # Apify Store 搜索/筛选机制
│   ├── pricing-and-billing.md  # compute unit、四种 Actor 定价模型、用量查询
│   └── errors-and-limits.md    # 错误结构、限流、分页约定速查
└── evals/
    └── evals.json              # 对照实验场景（打包时自动排除）
```

内容整理自 `docs.apify.com`（官方 OpenAPI 规范 `api/openapi.json` + 文档页面原文,抓取于 2026-09-21）,**没有经过真实 API 调用验证**——补验证前,实际调用报错永远优先信任真实 API 返回,不信任本 skill 的文字描述。
