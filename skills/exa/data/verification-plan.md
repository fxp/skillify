# exa skill 验证计划（待真实 API Key）

现状：文档版，抓取于 2026-09-21（`https://docs.exa.ai` → 307 跳转到 `https://exa.ai/docs`），依据 `llms.txt` + OpenAPI 规范 `exa-spec.json`（`info.version: 2.0.0`）+ 十余篇 Markdown 源页整理，**没有做过任何真实 API 调用**，也没有跑 with/without skill 对照实验。

测试原则：Key 只走环境变量，不写入任何文件；每条结论改回对应 reference 时按 verify.md 的固定格式写"已用真实 API 验证（日期）：传 X 返回 `{...}`"；创建/写入类操作（目前已知仅 Agent 富化输出，没有会话外持久化副作用）用完即忘，不需要额外清理账户资源；每次调用记录到 `verification-log.md`（日期、endpoint、请求要点、原始响应片段、花费）。

免费额度：新账号 $20 起，Free Tier 每月再补 $10，足够覆盖下面全部 P0/P1 验证项（预估合计 < $0.50）。

## P0 —— SKILL.md"先确认的三件事" + 本 skill 标为最高优先级的假设（低成本，优先测）

| # | 结论/假设 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 1 | `Authorization: Bearer <key>` 能调通 `POST /search` | 用最小请求体（仅 `query`）调一次 | ~$0.007 | 200 + `results[]` |
| 2 | `x-api-key: <key>` 单独也能调通，效果与 Bearer 等价 | 同一请求换成 `x-api-key` 头 | ~$0.007 | 对比两次响应是否等价；若不等价，SKILL.md"用之前先确认"第 2 条要改 |
| 3 | 两个头同时传、且值不同时，哪个生效 | 故意传一个真 Key 到 `Authorization`、一个错的字符串到 `x-api-key`（反之再试一次） | ~$0.014 | 记录实际生效的是哪个；这个结论直接写回 `errors-and-limits.md`"鉴权"节 |
| 4 | `type: "neural"` / `type: "keyword"`（旧值，不在当前 enum 里）会 400 还是被静默接受/回退 | 分别传这两个非法值调 `/search`，对比传 `type: "auto"` 的响应里 `resolvedSearchType`/结果集是否有可辨识差异 | ~$0.021 | 400 报错记原始错误体；未报错则要确认是否真的按某种默认模式跑了，还是直接原样透传导致上游报错 |
| 5 | `resolvedSearchType` 在真实响应里到底是空字符串还是像 OpenAPI 示例那样有 `"neural"` | 调一次默认 `auto` 类型的 `/search` | 复用 #1 的调用 | 记录真实值，更新 `search.md` 里"文档自相矛盾"那条的裁决结果 |
| 6 | 不传 `contents` 时 `/search` 结果确实没有 `text` 字段 | 最小请求体（仅 `query`）调一次，检查 `results[0]` 的 key 集合 | 复用 #1 | 确认/否证"默认不返回正文"这条跨领域规则 |

## P1 —— evals.json 的 5 个陷阱场景对应的裁决项

| # | 陷阱 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 7 | `/search` 和 `/contents` 内容选项嵌套位置不同（eval #3） | 分别按"正确"和"搞反"两种嵌套方式各调一次 `/contents`（`{"urls":[...],"text":true}` vs `{"urls":[...],"contents":{"text":true}}`） | ~$0.002 | 确认"搞反"的那种是 400 还是被忽略（静默丢字段，返回正文全空）——静默失效比报错更危险，要单独标注 |
| 8 | `POST /findSimilar` 是否还能调通、响应形状 | 用一个真实存在的 URL 调一次（如 `https://arxiv.org` 上的一篇论文页） | ~$0.007（按 /search 同档估） | 确认是否已经下线（404/410）还是仍可用但无新功能；更新 `contents-and-find-similar.md` |
| 9 | `maxAgeHours` 四态语义（省略/0/-1/正整数）是否如文档描述 | 对同一个近期更新过的 URL，分别用 `-1`、`0`、省略三种方式调 `/contents`，对比返回的 `text`/抓取时间戳 | ~$0.003 | 确认 `-1` 真的不触发抓取（比如故意传一个 Exa 从未见过的新 URL，`-1` 应该报错或返回空，而不是自己去抓） |
| 10 | Agent run 创建后立即返回的 `status: "queued"` 响应里 `output`/`usage`/`costDollars` 的真实取值 | 发起一个 `effort: "minimal"` 的最简单 Agent run，不轮询，直接看创建响应 | ~$0.012 | 确认 OpenAPI 标为必填的这几个字段在 `queued` 态下是空对象/零值还是别的占位 |
| 11 | Agent API 错误信封与 Search/Contents/Answer 是否真的不同 | 故意用非法 `outputSchema` 分别调 `/search`（应 400 扁平结构）和 `/agent/runs`（应 400 嵌套结构） | ~$0（400 通常不计费，按文档说明确认） | 对比两次响应体结构，验证 `SKILL.md` 跨领域规则第 5 条 |

## P2 —— 影响成本估算但优先级略低的项

| # | 结论 | 怎么测 | 预期成本 | 判定 |
|---|---|---|---|---|
| 12 | `category: "company"`/`"people"` + `startPublishedDate` 组合是否真的 400 | 调一次 `/search`，`category: "company"` 同时带 `startPublishedDate` | ~$0.007 | 确认错误码/文案，写回 `search.md` |
| 13 | `contents.highlights.dynamic`/`verbosity` 不带 `Exa-Beta` 头时的具体拒绝方式 | 调一次 `/search` 带 `contents.highlights.dynamic: true` 但不带 beta 头 | ~$0.007 | 记录 400 的 `tag`（推测是 `INVALID_REQUEST`，需确认） |
| 14 | `/answer` 的 `model` 四选项（`exa`/`exa-pro`/`exa-research`/`exa-fast`）实际差异 | 同一个问题分别用四个 model 调一次 `/answer` | ~$0.02（按 $5/1k 次估） | 对比延迟、答案长度、是否有独立计费提示；更新 `answer.md`"模型选择"节 |
| 15 | `ids`/`urls` 都不传时 `/contents` 的行为 | 故意发一个空请求体（仅 `{}`）给 `/contents` | 预计不计费（400） | 确认是 400 还是别的；更新 `contents-and-find-similar.md` |
| 16 | Agent `cancel` vs `stop` 的实际返回差异 | 起一个耗时较长的 `effort: "high"` run，几秒后分别在另一个 run 上试 `cancel`，在（若能触发）`max` effort run 上试 `stop` | ~$0.5+（`stop` 需要 `max` effort，成本较高，可选做） | 确认 `cancel` 真的不返回 `output`，`stop` 真的返回部分结果 |

## P3 —— 低优先级/需要企业权限或额外条件，暂不强求

| # | 项目 | 备注 |
|---|---|---|
| 17 | Batch API（`/batches`） | 文档写明需要企业版且需联系 Exa 开通，测试账号大概率无权限，先跳过 |
| 18 | Websets API（`/v0/websets/*`） | 本 skill 明确不覆盖，如需覆盖应作为独立的后续 skill 迭代，不在这次验证范围 |
| 19 | Zero Data Retention 相关行为 | 需要团队开启 ZDR，测试账号默认应该没有，先跳过 |
| 20 | 25 QPS 自动提升的实际触发条件 | 需要 30 天内充值 $1,000，测试成本过高，只做文档转录 |
| 21 | x402 免 Key 支付流程 | 需要链上钱包和 USDC，属于独立的技术栈，优先级低于核心 API 行为验证 |

## 完成后

- 每条结论改回对应 reference 文件，写「已用真实 API 验证（日期）：传 X 返回 `{...}`」；文档本身的错误同时升到 `SKILL.md`"跨领域的通用规则"一节。
- `SKILL.md`"⚠ 验证状态"从"文档版，未验证"改成分区写清"已验证 / 仍是文档转录"，参照 `fxiaoke`/`beisen` 等既有 skill 的写法。
- 跑 `evals/evals.json` 的 5 个场景做 with/without skill 对照（子 Agent 各写一版代码，用本计划里验证过的真实报错去判两版代码能不能在生产环境跑通），写 `exa-workspace/comparison-report.md`（Markdown，按本工作区 `CLAUDE.md` 的约定，不生成 HTML/Artifact）。
- 全仓库 `grep` Key 前 8 位，确认没有残留；如果测试中创建了 Agent run 记录，可选择性 `DELETE /agent/runs/{id}` 清理。
