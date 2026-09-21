# hubspot skill 验证计划（待真实 API Key）

现状：文档版，抓取于 2026-09-21（`https://developers.hubspot.com/docs` → llms.txt 索引 + 各 endpoint 页面内嵌的 OpenAPI 片段 + Markdown 正文），**没有做过任何真实 API 调用**，也没有跑 with/without skill 对照实验。

测试原则：Token 只走环境变量，不写入任何文件；每条结论改回对应 reference 文件时按 verify.md 的固定格式写"已用真实 API 验证（日期）：传 X 返回 `{...}`"；创建类操作（联系人/公司/交易/自定义对象记录）用完立即批量删除清理，不在测试账号里留垃圾；自定义对象 schema 创建后如果不再需要，删除时要先清空该 schema 下的全部记录/属性/关联才能删 schema 本身。每次调用记录到 `verification-log.md`（日期、endpoint、请求要点、原始响应片段）。

获取测试账号：HubSpot 有免费的 Developer Test Account（挂在开发者账号下，随时可建，数据和真实客户账号完全隔离，不产生费用），是本计划的首选测试环境，不需要用真实生产账号或付费订阅。

## P0 —— SKILL.md"用之前先确认的 3 件事" + 通用规则第 1、2、7、8 条（最高优先级，且成本极低——多数是只读或幂等操作）

| # | 结论/假设 | 怎么测 | 判定 |
|---|---|---|---|
| 1 | `Authorization: Bearer <私有应用token>` 能调通 `GET /crm/v3/objects/contacts` | 创建一个 Developer Test Account 下的私有应用（勾 `crm.objects.contacts.read`），用它的 token 调一次 | 200 + `results[]`；记录实际返回的默认字段集合，核对是否和 `references/objects.md` 描述的一致 |
| 2 | 旧式 `hapikey` query 参数对 CRM 对象端点确实已失效 | 用一个随便编的字符串当 `?hapikey=xxx` 调 `GET /crm/v3/objects/contacts`（不带 Bearer 头） | 预期 401；确认报错信息是否明确提示"该用 Bearer token"还是通用的鉴权失败信息 |
| 3 | `company` 文本属性和真实关联的区别（SKILL.md 通用规则第 2 条） | 创建一条联系人只传 `properties.company = "Acme Inc"`（不传 `associations`），再调 `GET /crm/v3/objects/contacts/{id}/associations/companies` | 预期返回空列表/无关联，证实"设置 company 字段不创建关联"这条断言；如果这个假设是错的（比如 HubSpot 做了某种智能匹配自动建关联）,是本 skill 最需要修正的一条 |
| 4 | 创建记录省略 `associations` 字段是否真的不报错（`references/objects.md` 标的"文档自相矛盾"那条） | 调 `POST /crm/v3/objects/contacts`,请求体只有 `properties`,不传 `associations` | 预期 201 成功;如果报错缺失必填字段,说明 OpenAPI 规范的 `required: [associations, properties]` 才是权威,要改写 objects.md 和 batch.md 的说法 |
| 5 | 2026-09 起的"CRM 写校验强制执行"新规则实际影响范围（SKILL.md 通用规则第 7 条） | 分别对 `/crm/v3/objects/contacts` 和 `/crm/objects/2026-09/contacts` 发起同一个写请求(比如更新一个不存在的自定义属性),对比两个路径前缀下报错是否有差异 | 确认该规则是只影响 `2026-09` 路径前缀还是所有版本前缀都受影响,这个结论要升级进 SKILL.md 第 7/8 条 |
| 6 | `v3` 和 `2026-09` 两个路径前缀对同一个 endpoint 是否真的等价(SKILL.md 通用规则第 8 条) | 对同一条记录分别用两个前缀调 `GET`,对比响应体字段是否完全一致 | 若有差异（字段增减、类型变化）要在 objects.md 明确写出差异点,不能再笼统说"等价" |

## P1 —— objects.md / batch.md 的具体断言（低成本，标准 CRUD + 小批量）

| # | 结论 | 怎么测 | 判定 |
|---|---|---|---|
| 7 | Contacts 创建不传任何必填属性是否真的不报错 | `POST /crm/v3/objects/contacts` 空 `properties: {}` | 确认"contacts 无强制必填属性"这条断言 |
| 8 | Companies 创建时 `domain` 和 `name` 都不传是否报错 | `POST /crm/v3/objects/companies`，`properties: {}` | 确认"至少给 domain 或 name 之一"是否是真实校验而非仅推荐 |
| 9 | Deals 不传 `pipeline` 时是否真的用默认 pipeline，而不是报错 | `POST /crm/v3/objects/deals`，只传 `dealname` + `dealstage`（有效的默认 pipeline 阶段值），不传 `pipeline` | 确认 `using-object-apis.md` 的"必需属性表"（写 pipeline 必填）和 `deals/guide.md` 正文（写"不传则用默认"）哪个准确——这是 objects.md 里未特别标注但值得核实的潜在矛盾 |
| 10 | 属性内部名 vs 显示标签的真实差异 | 在测试账号 UI 里手动创建一个属性，标签设为和内部名明显不同的文字（如内部名 `test_field_1`，标签设成"客户偏好"），然后调 `GET /crm/properties/v3/contacts/test_field_1` | 确认响应里 `name`/`label` 字段分别是什么，验证 objects.md 关于二者不对应的核心论点 |
| 11 | Upsert 用 `email` 做 idProperty 时"不支持部分 upsert"具体是什么行为（objects.md 标的 `⚠ 文档未说明`） | 先创建一条有 `firstname`+`lastname` 的联系人，再用 `email` 做 idProperty 发起只带 `phone` 字段的 upsert | 对比 upsert 后 `firstname`/`lastname` 是否被清空，坐实"不支持部分 upsert"到底是"整条覆盖清空其他字段"还是别的行为 |
| 12 | 批量端点超过 100 条的真实报错行为（batch.md 标的最高优先级未验证项） | 用 101 条 `inputs` 调 `POST /crm/v3/objects/contacts/batch/create` | 确认是 400 报错（附什么错误码/文案）还是静默只处理前 100 条 |
| 13 | Multi-status（207）响应的真实触发条件 | 批量创建 2 条联系人，其中一条故意传一个不存在的属性名，都带 `objectWriteTraceId` | 确认响应 HTTP 状态码确实是 207，`errors[].context.objectWriteTraceId` 能正确对应回失败的那条 |
| 14 | Schemas API 路径确实是 `/crm-object-schemas/v3/schemas` 而不是别的猜测路径 | 调 `GET /crm-object-schemas/v3/schemas`（需要 `crm.schemas.custom.read` scope） | 确认该路径可用，且 `/crm/objects/v3/schemas`、`/crm/schemas/v3` 两种"看起来合理"的猜测路径确实不可用（404），坐实这是一个真实陷阱而非臆测 |

## P2 —— associations.md 的具体断言

| # | 结论 | 怎么测 | 判定 |
|---|---|---|---|
| 15 | contact→company 默认关联 typeId=279、primary=1 是否准确 | 创建一条联系人和一条公司，`PUT /crm/v3/objects/contacts/{id}/associations/default/companies/{id}` 建立默认关联后，`GET .../associations/companies` 查看返回的 `associationTypes[].typeId` | 确认默认无标签关联对应的 typeId 数值，核对是否等于文档给出的表格外的"default"值（⚠ 关联类型 ID 表里没有单独列出"default 无标签关联"对应的数值，用的是单独的 `/associations/default/...` 端点，这条本身也值得澄清） |
| 16 | 批量关联 `batch/associate/default` 端点的单请求上限 | 尝试超过 2000 条（或先测 10 条确认端点可用，再视预算决定是否测上限） | associations.md 目前对这个端点的上限标了"参照批量创建 2000，未单独验证" |
| 17 | 关联 API 独立限流数字（burst 100/150/200，daily 500k/1M）是否和响应头一致 | 连续快速调用关联相关端点，观察响应头里的 `X-HubSpot-RateLimit-Max` | 对比响应头实际值和文档表格，判断关联 API 是否真的有独立于对象 API 的限流响应头 |

## P3 —— search.md 的具体断言

| # | 结论 | 怎么测 | 判定 |
|---|---|---|---|
| 18 | filterGroups 的 AND/OR 语义（本 skill 最核心的陷阱断言） | 构造一个"两个 filterGroups 各一个条件"的搜索和"一个 filterGroups 两个条件"的搜索，用同一批测试数据对比结果集大小 | 这是全 skill 最重要的一条待验证结论，即使其他都没测完也要优先测这条 |
| 19 | `IN`/`NOT_IN` 操作符是否真的要求字符串小写 | 对一个字符串属性用 `IN` 操作符传大写值 vs 小写值 | 确认大写是报错、不匹配、还是被静默转小写 |
| 20 | search 端点是否真的不返回限流响应头 | 调用一次 search 端点，检查响应头列表 | 核对 errors-and-limits.md 关于 search 端点限流头缺失的断言 |
| 21 | 单次查询超过 10,000 条翻页上限的真实报错 | 需要一个有 10,000+ 条记录的测试数据集，成本较高，可选做/降级为读文档转录 | 确认第 10,001 条起的 `after` 翻页是 400 还是别的行为 |

## P4 —— errors-and-limits.md 的矛盾数字（需要真实付费订阅，测试账号可能无法验证，标记为长期待办）

| # | 项目 | 备注 |
|---|---|---|
| 22 | API Limit Increase 加购后 burst 到底是 200 还是 250/10秒 | 需要一个购买了该加购项的真实付费账号，Developer Test Account 大概率没有这个加购，短期内可能无法验证，先保留矛盾记录 |
| 23 | OAuth 应用响应确实不带 `X-HubSpot-RateLimit-Daily*` 头 | 需要先建一个 OAuth 应用走完整授权流程，比私有应用 token 复杂得多，优先级低于 P0-P2 |
| 24 | 429 响应体 `policyName` 在 burst 场景下的具体取值 | 需要真的把 burst 限额打满触发 429，注意别在测试账号上无意义地刷爆限额影响其他验证项，放在所有其他验证完成后最后做 |

## 完成后

- 每条结论改回对应 reference 文件，写「已用真实 API 验证（日期）：传 X 返回 `{...}`」；文档本身的错误或已确认的自相矛盾同时升到 `SKILL.md`"跨领域的通用规则"一节。
- `SKILL.md`"⚠ 验证状态"从"文档版，未验证"改成分区写清"已验证 / 仍是文档转录"。
- 跑 `evals/evals.json` 的 5 个场景做 with/without skill 对照（子 Agent 各写一版代码，用本计划里验证过的真实报错去判两版代码能不能在生产环境跑通），写 `hubspot-workspace/comparison-report.md`（Markdown，按本工作区 `CLAUDE.md` 的约定，不生成 HTML/Artifact）。
- 全仓库 `grep` token 前 8 位，确认没有残留；测试期间创建的联系人/公司/交易/自定义对象记录/自定义对象 schema 全部清理（记录移入回收站 90 天内会占用账号配额，建议用批量归档端点清理；schema 需要先清空记录再删）。
