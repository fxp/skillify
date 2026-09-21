# Apify skill 验证计划

拿到一个有余额的 Apify API token 之后，按下面的优先级逐条实测，测完把对应 reference 文件里的 `⚠ 文档原文，未实测` 改写成"已用真实 API 验证（日期）：……"并附原始响应/报错片段。同时更新 `apify/SKILL.md` 顶部"⚠ 验证状态"一节。

## 验证用测试 Actor 的选择

需要挑 1-2 个便宜/免费、行为稳定、能覆盖 dataset + key-value store 两种输出的公开 Actor 作为测试对象：

- **首选**：`apify/website-content-crawler`（官方维护，pay-per-usage 计费，行为在文档里反复被引用为例子，适合验证同步/异步 run、dataset 分页、run 状态语义）。用 `maxCrawlPages: 1` 或类似的输入参数把爬取范围限制到 1-2 页,把成本压到几分钱以内。
- **备选（用于验证 KV store OUTPUT 记录模式）**：任意一个官方标注"结果写入 key-value store 而非 dataset"的小型工具类 Actor（比如截图类、单值计算类），具体名字需要在验证时去 Store 搜索确认哪个仍在维护且便宜。
- 每次测试前先看该 Actor 页面的 Pricing 区块确认预期花费，测试全程用 `maxTotalChargeUsd` 封顶（比如设成 `0.5` 美元），避免意外超支。

## 优先级 1：SKILL.md 顶部"先确认的几件事"（错了全盘皆错）

1. 鉴权：`Authorization: Bearer <token>` 是否真的生效；不带 token 调用私有资源是否真的返回 401/403；`?token=` query 参数方式是否同样生效。
2. `/v2/acts/` 旧前缀是否真的和 `/v2/actors/` 等价可用。
3. Base URL 确认 `api.apify.com`（而不是 `docs.apify.com`）。

## 优先级 2：run 启动与生命周期（`references/running-actors.md`）

1. `POST /v2/actors/{actorId}/runs` 异步启动，确认返回的 run 对象字段（尤其 `defaultDatasetId`/`defaultKeyValueStoreId`/`defaultRequestQueueId`/`status`/`exitCode`）。
2. `run-sync-get-dataset-items`：故意传一个会跑很久的输入（或人为设置极短 `timeout`），确认 300 秒超时报错的具体状态码/错误体，并确认超时后原 run 是否真的仍在后台继续跑（用异步方式查同一个 run id 验证）。
3. `run-sync`（拿 KV `OUTPUT` 记录）：确认该 Actor 是否真的写了 `OUTPUT` key，响应 content-type 是什么。
4. 状态语义陷阱：故意让一次 run 抓 0 条结果（比如传一个明显抓不到东西的 URL），确认 `status` 是否依然是 `SUCCEEDED`，`statusMessage`/`isStatusMessageTerminal` 此时的实际取值——这是 evals.json 里 eval #2 的核心前提，必须验证。
5. `POST /v2/actor-runs/{runId}/abort?gracefully=true` vs 不传 `gracefully`：确认两种中止方式在 run 日志/状态上的实际区别。
6. 已废弃的 `/v2/actors/{actorId}/runs/{runId}` 系列端点是否仍然可用（确认"废弃但没下线"的说法）。

## 优先级 3：读结果（`references/reading-run-output.md`）

1. `GET /v2/datasets/{datasetId}/items`：不传 `limit` 时是否真的不限制条数返回全部（对一个已知条目数的数据集验证），还是有隐藏上限。
2. `clean=true`、`unwind`、`flatten`、`fields`/`outputFields` 各自的实际输出效果，和文档描述是否一致。
3. `POST /v2/datasets/{datasetId}/items` 批量写入时，故意让数组里第 3 条不符合 schema（如果能配置 dataset schema），确认是否整个请求被拒绝、`error.data.invalidItems[].itemPosition` 是否准确指出第几条。
4. `GET /v2/key-value-stores/{storeId}/keys` 的游标分页：用一个已知 key 数量的 store（自己写几十条测试数据）验证 `exclusiveStartKey`/`nextExclusiveStartKey`/`isTruncated` 的翻页行为——这是 evals.json 里 eval #5 的核心前提。
5. `GET /v2/key-value-stores/{storeId}/records/{recordKey}` 对不存在的 key 返回什么（404 还是空 200）。

## 优先级 4：定价与用量（`references/pricing-and-billing.md`）

1. 用测试 Actor 的一次真实 run，核对 `stats.computeUnits` 的计算是否符合"内存(GB)×时长(小时)"公式。
2. `usageUsd`/`usageTotalUsd` 与 Apify Console Billing 页面显示的金额是否一致（验证"仅供参考,可能和最终账单有出入"的说法）。
3. `maxTotalChargeUsd` 参数：故意设一个很低的值（如 `$0.01`），确认 run 是否真的被提前终止，以及终止时的 `status`/`statusMessage`。
4. `GET /v2/users/me/usage/monthly`、`GET /v2/users/me/limits` 的实际响应结构。

## 优先级 5：webhook 与 store 搜索（成本低、可选）

1. `POST /v2/webhooks` 创建一个指向 `https://webhook.site/...`（或类似临时收件工具）的 webhook，触发一次 run，确认默认 payload 结构、重试行为（如果收件端故意返回非 2xx）。
2. Ad-hoc webhook 的 base64 参数格式，确认编码细节（是否需要 URL-encode 整个 base64 串）。
3. `GET /v2/store` 的 `includeUnrunnableActors` 默认行为——搜一个已知存在但可能被安全过滤掉的 Actor,对比传/不传这个参数的结果差异。

## 完成验证后

- 把每条实测结果写回对应 reference 文件，格式："已用真实 API 验证（YYYY-MM-DD）：……"+ 原始响应/报错片段。
- 重新审视 SKILL.md 的"跨领域通用规则"，把验证中发现的新陷阱（尤其是文档没写但实测发现的静默失效行为）补充进去。
- 跑第 4 步（with/without skill 对照实验），产出 `comparison-report.md`（Markdown，按仓库约定不做 HTML）。
- 全仓库 grep 一遍确认没有真实 token 泄漏进任何文件。
