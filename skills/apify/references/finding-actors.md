# 从 Apify Store 挑选 Actor

> 来自 Apify 官方 OpenAPI 规范和 `docs.apify.com/actors/running/actors-in-store.md`（抓取于 2026-09-21）。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录。

**本文件只讲"怎么用搜索/筛选机制找到合适的 Actor"，不收录具体 Actor 列表**——Apify Store 里有数千个社区维护的 Actor，具体某个 Actor 好不好用、输入输出长什么样，属于运行时决策，不属于本 skill 范围。

## `GET /v2/store`：搜索/筛选

**用途**：在 Apify Store 里搜公开 Actor，可用于"根据任务描述找一个现成 Actor"这类场景（比如 AI agent 自主选择 Actor）。

**关键参数**
| 参数 | 类型 | 说明 |
|---|---|---|
| `search` | string | 在 title / name / description / username / readme 里做文本匹配 |
| `sortBy` | string，枚举 | `relevance`（默认）/ `popularity` / `newest` / `lastUpdate` |
| `category` | string | 按分类过滤 |
| `username` | string | 只看某个开发者发布的 Actor |
| `pricingModel` | string，枚举 | `FREE` / `FLAT_PRICE_PER_MONTH`（rental）/ `PRICE_PER_DATASET_ITEM`（老式按结果计费）/ `PAY_PER_EVENT` |
| `allowsAgenticUsers` | boolean | 只看/排除"允许 AI agent 自动调用"的 Actor |
| `responseFormat` | string，枚举 `full`/`agent` | `agent` 返回为 LLM 消费精简过的字段集（只有 `id`/`title`/`name`/`username`/`description`/`notice`/`badge`/`categories`/精简版 `stats`），token 消耗更小，适合 agent 场景 |
| `includeUnrunnableActors` | boolean，默认 `false` | **默认会排除"不适合自动运行"的 Actor**（比如开发者未通过 KYC 认证、或权限过高又用户量不足的 full-permission Actor）——`⚠ 文档原文，未实测`：这个默认过滤行为如果没注意到，可能会觉得"搜不到某个明明存在的 Actor"，其实是被安全过滤掉了，需要显式传 `true` 才能看到 |
| `limit` / `offset` | number | 分页，`limit` 默认与上限都是 1000 |

**示例请求**（面向 agent 场景，找免费或按用量付费的抓取类 Actor）
```bash
curl "https://api.apify.com/v2/store?token=$APIFY_API_TOKEN&search=website%20crawler&responseFormat=agent&pricingModel=PAY_PER_EVENT&sortBy=popularity&limit=10"
```

**响应核心字段**（`data.items[]`）
| 字段 | 说明 |
|---|---|
| `id` / `name` / `username` / `title` / `description` | 基本信息，`username/name` 拼成 `~` 分隔的引用形式可直接用于启动 |
| `notice` | 枚举 `NONE`/`RESIDENTIAL_PROXY_REQUIRED`/`UNDER_MAINTENANCE`——启动前应该检查这个字段，`UNDER_MAINTENANCE` 的 Actor 大概率跑不稳定 |
| `stats.totalRuns` / `stats.totalUsers` / `stats.actorReviewRating` | 热度和口碑指标,帮助从多个同类 Actor 里挑选 |
| `stats.publicActorRunStats30Days.{SUCCEEDED,FAILED,ABORTED,TIMED-OUT,TOTAL}` | 最近 30 天的运行成功率——挑选 Actor 时的重要信号,失败率高的谨慎选用 |
| `currentPricingInfo.pricingModel` | 见上方 `pricingModel` 枚举,决定怎么估算这次调用的成本（详见 `references/pricing-and-billing.md`） |
| `readmeSummary` | LLM 生成的 README 摘要,比完整 README 省 token,适合 agent 先粗筛再决定要不要拉完整 README |

## 挑选时的注意事项

- **同一类任务往往有多个 Actor 可选**（比如"抓网页内容"，官方的 `apify/website-content-crawler` 之外还有大量社区版本），`stats.publicActorRunStats30Days` 和 `actorReviewRating` 是比"名字听起来像不像"更可靠的筛选依据。
- **拿到 Actor 引用后，具体要传什么输入字段不在这个搜索响应里**——需要另外查该 Actor 的详情（`GET /v2/acts/{actorId}` 或它在 Console 里的 Input 标签页 / input schema）。
- 通过 MCP、Agent Skills 等"AI agent 自主选择并运行 Actor"的场景，官方专门给了 `allowsAgenticUsers`/`responseFormat=agent`/`includeUnrunnableActors` 这几个参数做适配，这是与"人工在 Console 里搜索"场景刻意做出的差异化设计。
