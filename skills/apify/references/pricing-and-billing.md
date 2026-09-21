# 定价与计费：compute unit、四种 Actor 定价模型

> 来自 `docs.apify.com/actors/running/usage-and-resources.md`、`docs.apify.com/actors/running/actors-in-store.md`、`docs.apify.com/actors/publishing/monetize/pricing-and-costs.md`、`apify.com/pricing.md`（抓取于 2026-09-21）以及官方 OpenAPI 规范里 run 对象的 `pricingInfo`/`usage`/`usageUsd` 字段定义。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录，价格数字属于易变信息，使用前建议到 `apify.com/pricing` 核实是否已更新。

**⚠ 这是 Apify 和 Firecrawl / Exa / Tavily 这类"每次调用固定 N 个 credit"的 API 最大的不同点**：Apify 没有统一的"每次调用扣多少"，成本由（a）平台资源消耗（compute unit + 数据传输 + 代理 + 存储读写）和（b）该 Actor 开发者选择的定价模型共同决定，两者都会随"跑哪个 Actor、跑什么任务"剧烈变化。**估算成本前必须看具体 Actor 的 Store 页面 Pricing 区块，不能套用固定单价的直觉。**

目录：
- [底层：compute unit 是什么](#底层compute-unit-是什么)
- [Actor 层：四选一的定价模型](#actor-层四选一的定价模型)
- [订阅计划与折扣档位](#订阅计划与折扣档位)
- [怎么控制/预估花费](#怎么控制预估花费)
- [查用量的 API](#查用量的-api)

## 底层：compute unit 是什么

**1 compute unit（CU） = 1GB 内存跑 1 小时。**

```
CU = 内存(GB) × 运行时长(小时)
```

例：`1024MB` 内存跑 6 分钟 = `1GB × 0.1小时 = 0.1 CU`。

内存分配规则（见 `references/running-actors.md` 的 `memory` 参数）：必须是 2 的幂，最小 128MB，最大 32768MB；CPU 按内存自动配比（每 4096MB 对应 1 个完整 CPU 核心，不是整数倍时按比例分）；磁盘空间是内存的 2 倍。

**决定 CU 消耗的因素（重要性从高到低，`⚠ 文档原文`）**：
1. 用浏览器（Puppeteer/Playwright）还是纯 HTTP（Cheerio）——浏览器可能慢 20 倍；
2. 任务批次大小和频率——大批量一次跑比多次短 run 更省（避免重复冷启动开销）；
3. 目标页面复杂度——重页面（如 Amazon、Facebook）解析耗时可能是普通页面的 3 倍。

除 CU 外，平台用量还包括：**数据传输**（内部/外部，按 GB）、**代理**（住宅代理按 GB、SERP 代理按每千次、机房代理按 IP）、**存储操作**（dataset/KV store/request queue 的读写次数，按每千次计，单价很低）。这些统称"平台用量"（platform usage），run 对象的 `usage`/`usageUsd` 字段里都有。

## Actor 层：四选一的定价模型

Apify Store 里每个 Actor 的详情页会标明它属于哪种模型——**这是决定"这次调用到底多贵"的关键变量，同一类任务换一个 Actor 可能价格结构完全不同**：

| 模型（`pricingModel` 枚举值） | 你付的钱 | 特点 |
|---|---|---|
| `FREE`（免费用量档） | 不额外收费，只消耗你计划里的免费额度 | 罕见，多为示例/测试性质的 Actor |
| **Pay per usage**（对应 `pricingInfo` 里没有额外 markup 的情况） | 只付平台用量（CU+代理+存储+传输），开发者不加价 | 最接近"按实际消耗算账"，但**事前很难精确估算**——最佳做法是先在小范围试跑（比如只抓几页）观察实际消耗,再外推 |
| **Pay per event**（`PAY_PER_EVENT`，即 PPE） | 按 Actor 开发者自定义的"事件"付固定单价（如"每抓到一条帖子 $0.002"、"每次启动 $0.01"） | **多数 PPE Actor 把平台用量已经打包进事件单价里，但也有一部分单独再收平台用量的钱——文档原文明确提示"要检查该 Actor 页面的 Pricing 区块确认是否包含"**，不能假设所有 PPE Actor 都是"事件费 = 总费用" |
| `FLAT_PRICE_PER_MONTH`（rental，包月租用） | 试用期后按月付固定租金 + 平台用量另计 | **官方正在淘汰这个模型**：2026-04-01 起不能新发布/改价，2026-10-01 起全部下线迁移到 pay-per-usage，选 Actor 时应尽量避开还标着这个模型的 |
| `PRICE_PER_DATASET_ITEM`（老式按结果计费，规范里仍可见 `tieredPricing` 结构） | 按抓到的结果条数付费，价格随用户的订阅折扣档位（`FREE`/`BRONZE`/`SILVER`/`GOLD`/`PLATINUM`/`DIAMOND`）变化 | 遗留模型，规范里通过 `pricingInfo.tieredPricing` 体现分档单价 |

**⚠ 补充**：这五种（含免费档）都可能同时叠加平台用量成本——只有明确写"包含平台用量"的 PPE Actor 是例外。启动前一定去看 Actor 页面自己的 Pricing 说明，不要只看 `pricingModel` 这个枚举名字就下结论。

## 订阅计划与折扣档位

你自己账号的订阅计划决定两件事：CU 单价、以及能拿到的折扣档位（影响 PPE Actor 和平台用量单价）：

| 计划 | 月费 | CU 单价 | 折扣档位 |
|---|---|---|---|
| Free | $0 | $0.2/CU | 无折扣（相当于 `FREE` 档） |
| Starter | $19 | $0.2/CU | Bronze |
| Scale | $199 | $0.16/CU | Silver |
| Business | $999 | $0.13/CU | Gold |

平台用量各分项单价示例（FREE/BRONZE 档，`⚠ 文档原文` 数字易变，用前核实）：住宅代理 $8/GB，SERP 代理 $2.5/千次，数据传输(外部) $0.2/GB，dataset 写 $0.005/千次，KV store 写 $0.05/千次——都远小于 CU 本身，通常 CU 和代理费是大头。

预付额度用不完**不会**结转到下个计费周期，会直接清零；超出预付额度的部分按 pay-as-you-go 计入下一张账单（免费版超额直接被限制，付费版可以继续用直到账单封顶）。

## 怎么控制/预估花费

1. **启动 run 时传 `maxTotalChargeUsd`**（见 `references/running-actors.md`）——跨所有定价模型都生效的硬顶，达到后 Actor 会被优雅终止（不保证立即停止，但保证不会超收）。
2. **PPE Actor 还可以单独传 `maxItems`** 限制"按结果条数计费"部分的条数上限（这个参数只对 legacy pay-per-result 模型生效）。
3. **没法事前精确估算时（大多数 pay-per-usage Actor 都是这种情况），先用免费计划小范围试跑**（比如只给几个 URL），在 Console 的 Billing 页面看实际消耗，再按比例外推到目标规模。
4. Store 搜索时可用 `pricingModel` 参数直接筛掉不想要的定价类型（见 `references/finding-actors.md`）。

## 查用量的 API

| Endpoint | 用途 |
|---|---|
| `GET /v2/users/me/usage/monthly?date=YYYY-MM-DD` | 当前账号本计费周期的用量汇总 + 按天明细，字段包括 `monthlyServiceUsage`（各服务项用量）、`totalUsageCreditsUsdBeforeVolumeDiscount`/`totalUsageCreditsUsdAfterVolumeDiscount` |
| `GET /v2/users/me/limits` | 查当前账号的用量限额配置 |
| `PUT /v2/users/me/limits` | 修改限额（`⚠ 文档未说明`具体哪些限额字段可写，需要实测确认） |

`⚠ 文档原文`：run 对象里的 `usageTotalUsd`/`usageUsd` 是按**查询时刻**的当前单价折算出来的美元金额，仅供参考——如果计费周期内单价发生变化，历史 run 显示的美元数字可能和最终账单对不上，只用于粗略估算，不要当作精确账单来源。
