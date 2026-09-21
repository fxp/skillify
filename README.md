# Skillify

把第三方平台的开发者文档，打磨成 **AI Agent 通用的「SaaS 说明书」**——一份 `SKILL.md` 加一组按主题拆分的 `references/`，不绑定具体哪个 Agent，任何能读取 Skill 格式的执行环境都能直接装上用。每个 skill 对应一个可分发的目录（含 `SKILL.md`、`references/`、`evals/`），以及一个同名的 `*-workspace/` 目录存放评测过程产物。

## 目录结构

```
Skillify/
├── CLAUDE.md                      # 本工作区的约定（Claude 会自动读取）
├── README.md
├── <skill>/                       # 可分发的 skill 本体
│   ├── SKILL.md                   # 触发描述 + 主流程
│   ├── references/                # 按主题拆分的接口手册
│   └── evals/evals.json           # 评测用例与断言
├── <skill>.skill                  # package_skill.py 打包产物（bigmodel-cn、create-doc-skill 已打包）
├── agent-setup-prompts-reference/ # Cloudflare / Netlify / Stripe / Vercel / Supabase 的 Agent 安装提示词与 skills 仓库快照 + 横向分析（analysis.md）
└── <skill>-workspace/             # 评测产物（不随 skill 分发）
    ├── comparison-report.md       # skill vs baseline 价值审计报告（GLM-5.3 口径）
    └── glm-round*/                # 每一轮基准
        ├── PROTOCOL.md            # 开跑前冻结的场景与判分标准
        ├── run_agents.sh          # 用 GLM-5.3 作执行 Agent 跑两组任务
        ├── grade.py               # 真实执行生成的脚本并按冻结标准判分
        ├── summary.json           # 逐场景均值 / 标准差 / 每次得分
        └── <scenario>/
            ├── with_skill/run-*/     # outputs/main.py、exec_result.json、grading.json
            └── without_skill/run-*/  # 不带 skill 的 baseline 运行记录
```

当前包含的 skill：

| Skill | 覆盖平台 | 评测状态 |
|---|---|---|
| `bigmodel-cn` | 智谱 AI 开放平台（open.bigmodel.cn，GLM 系列）+ GLM Coding Plan 编程套餐 | 以 **GLM-5.3 为执行 Agent** 的 5 轮基准：12 场景 / 122 次运行，其中 **4 个统计显著**（p = 0.008 / 0.048 / 0.048 / 0.048），7 个打平、1 个领先但不显著；合并满分率 skill 54/56 vs baseline 35/56（p = 9×10⁻⁶）；实测查出并修正 16 条文档错误。见 `bigmodel-cn-workspace/comparison-report.md`。<br>**另有 5 轮说明书优化尝试全部失败**（拆分 reference / 陷阱速查表 / 代码片段），在弱执行器 `glm-4.5-flash` 上均不如未优化的原版，已回退；见 `bigmodel-cn-workspace/weak-exec/RESULTS.md` |
| `autodl` | AutoDL GPU 算力平台 API（账户 / 容器实例 Pro / 弹性部署） | 以 **GLM-5.3 为执行 Agent**：3 场景 / 30 次运行，1 个统计显著（p = 0.008，5/5 vs 0/5）；全部只读接口零费用；实测修正 11 条文档错误。见 `autodl-workspace/comparison-report.md` |
| `create-doc-skill` | 元技能：把任意开放平台的开发者文档站生成为一份经真实调用验证的接入 skill（本工作区方法论的可复用版本，原名 `generate-skill-from-api-docs`） | 1 轮 2 个场景（新版 vs 旧版快照），见 `create-doc-skill-workspace/comparison-report.md` |
| `volcengine-ark` | 火山引擎·火山方舟（ark.cn-beijing.volces.com，豆包 Doubao / Seedream / Seedance 及方舟上的 GLM / Kimi / DeepSeek / MiniMax）+ Agent Plan 与 Coding Plan 两套订阅套餐 | 以 **GLM-5.3 为执行 Agent**：3 场景 / 30 次运行，**0 个达到统计显著**（技能在 2 个场景领先但 n=5 不够，1 个场景是出题失误）；另经真实调用探针约 45 次，修正 8 条文档 / SDK 错误。见 `volcengine-ark-workspace/comparison-report.md` |
| `fxiaoke` | 纷享销客 CRM 开放平台（open.fxiaoke.com，客户 / 联系人 / 线索 / 商机与 `__c` 自定义对象、通讯录、企信消息） | **文档版**（2026-09-11）：整理自官方文档，未用真实凭证验证；10 次无凭证探测证实 3 处文档错误（错误码表与实际返回不符、示例域名不是 API 网关）。对照实验待凭证到位，验证计划见 `skills/fxiaoke/data/verification-plan.md` |
| `beisen` | 北森 iTalent OpenAPI 新版 v3.0（换 token 与全局约定、组织与岗位、员工与任职记录、入转调离、假勤、招聘、错误码与限流） | **文档版**（2026-09-11）：整理自开放文档站的公开接口（新版接口文档 718 篇、错误码 276 条），未用真实凭证验证；枚举选项表与管理后台需登录、未抓取。10 次无凭证探测证实 1 处文档错误（文档模板里的换 token 地址 `/token` 返回 404，实际是 `/OAuth/Token`）。验证计划见 `skills/beisen/data/verification-plan.md` |
| `moka` | Moka 招聘（ATS）与人事（People）开放 API（两套鉴权与 RSA 签名、组织与账号同步、职位与 HC、候选人与简历、面试与 Offer、员工档案、推送） | **文档版**（2026-09-11）：整理自两份公开 API 文档，未用真实凭证验证；无凭证探测证实 1 处文档错误（People 鉴权失败实际是 HTTP 403，文档写 401 / 100001），另发现 ATS 用错 Key 返回 HTTP 500、文档里拼错的路径 `getApplictaions` 才是真路径。验证计划见 `skills/moka/data/verification-plan.md` |
| `kingdee` | 金蝶云星空（K/3 Cloud）WebAPI：第三方授权签名、单据查询 / 保存 / 提交 / 审核 / 下推、物料客户供应商与多组织分配、总账凭证与应收应付；不覆盖星瀚 / 苍穹 / 旗舰版 / 精斗云 / KIS | **文档版**（2026-09-11）：整理自无需登录的旧版官方 API 文档（7.5.1800.6，2020-10）与官方 Python SDK 源码，未用真实凭证验证；新版 API 中心需登录、未抓取，可能有更新。业务接口部署在客户服务器上，只探测了旧公网网关。验证计划见 `skills/kingdee/data/verification-plan.md` |
| `yonyou` | 用友 YonBIP 公有云开放平台（按租户查网关与签名取 token、组织、客户 / 供应商 / 物料档案、采购与销售订单、总账凭证、事件订阅）；不覆盖 NC / U8 等本地部署版本 | **文档版**（2026-09-11）：整理自开放平台公开接口（236 篇接入文档 + 40 份 API 详情），未用真实凭证验证；25 次无凭证探测证实 3 处文档错误（两个示例接口地址在网关上未注册、会计期间接口返回纯文本而非 JSON）。验证计划见 `skills/yonyou/data/verification-plan.md` |
| `tapd` | TAPD 开放 API（API 账号 Basic 与开放应用 token、需求、缺陷、任务与迭代、工时与测试用例、Webhook、查询语法与分页） | **文档版**（2026-09-11）：整理自官方文档（400 页），未用真实凭证验证；20 次无凭证探测证实多处与文档不符（拼错的路径不带凭证也返回 200 + `status:1`、伪造 token 返回 422 而非 401、`http://` 不跳转 https、示例命令 `curl –u` 用的是破折号）。验证计划见 `skills/tapd/data/verification-plan.md` |
| `feishu` | 飞书开放平台（三种 access token 与 OAuth、通讯录、消息与机器人、多维表格、审批、飞书人事、事件订阅；含 Lark 国际版域名） | **文档版**（2026-09-11）：整理自官方文档（157 页），未用真实凭证验证；20 次无凭证探测证实 2 处文档错误（路径或方法写错返回纯文本 HTTP 404，而非文档列出的 JSON 错误码）。验证计划见 `skills/feishu/data/verification-plan.md` |
| `dingtalk` | 钉钉开放平台（新版 api.dingtalk.com 与旧版 oapi.dingtalk.com 两套服务端 API：鉴权、通讯录、工作通知与机器人、OA 审批、考勤、Stream / HTTP 事件订阅） | **文档版**（2026-09-11）：整理自官方文档，未用真实凭证验证；14 次无凭证探测证实 4 处文档错误（旧版 token 接口只认 query 参数、第三方 token 路径缺 `/v1.0`、机器人错误码、错误码表字段名）；回调解密代码经文档测试向量离线校验。验证计划见 `skills/dingtalk/data/verification-plan.md` |
| `alipay` | 支付宝开放平台·商户收款（v2 网关与 v3 两套协议、当面付、电脑网站 / 手机网站 / APP 支付、查询退款关单、异步通知验签、沙箱） | **文档版**（2026-09-11）：整理自官方文档与官方 v3 描述文件，未用真实凭证验证；10 次伪造 app_id 探测证实多处文档错误（v3 未签名返回 400 而非文档说的 401、SDK 文档里的旧沙箱域名证书已过期、v3 描述文件的沙箱地址不可用等）。验证计划见 `skills/alipay/data/verification-plan.md` |
| `wecom` | 企业微信服务端 API（access_token 与应用 secret、通讯录、应用消息与群机器人、客户联系 CRM、审批、回调加解密） | **文档版**（2026-09-11）：整理自官方文档（69 页），未用真实凭证验证；26 次无凭证探测证实 1 处文档错误（客户联系接口标注的 http 实际 301 到 https）；回调加解密代码用文档示例在本地跑通。验证计划见 `skills/wecom/data/verification-plan.md` |
| `wechatpay` | 微信支付商户 APIv3·直连商户（请求签名与应答验签、JSAPI / 小程序 / Native / H5 / APP 下单、查单关单、退款、回调解密、账单对账） | **文档版**（2026-09-11）：整理自官方文档（222 页），未用真实凭证验证，未发起任何交易；13 次伪造商户号探测证实 2 处文档错误（4xx 应答不带 `Wechatpay-*` 签名头、交易类接口 401 不带 `Request-ID`）；签名示例用文档公开测试私钥离线复算。验证计划见 `skills/wechatpay/data/verification-plan.md` |
| `youzan` | 有赞云开放 API（自用型 / 工具型换 token、订单发货、售后退款、商品、客户与积分、消息推送验签） | **文档版**（2026-09-11）：整理自官方文档（126 页），未用真实凭证验证；22 次无凭证探测证实 1 处文档错误（网关错误包在 `gw_err_resp` 里，不是文档说的顶层 `code`；错误响应一律 HTTP 200）。验证计划见 `skills/youzan/data/verification-plan.md` |
| `fadada` | 法大大电子签 FASC OpenAPI 5.1（换 token 与 X-FASC 签名、个人 / 企业授权、文件上传与处理、签署任务、模板、回调验签） | **文档版**（2026-09-11）：整理自官方文档与官方 Python SDK 源码，未用真实凭证验证；8 次无凭证探测证实 3 处文档错误（缺鉴权头返回 100012 而非文档写的 100010、AppId 无效与时间戳过期都是 HTTP 200 + 100001、错误响应多一个 `success` 字段）。验证计划见 `skills/fadada/data/verification-plan.md` |
| `qiyuesuo` | 契约锁电子签开放平台（x-qys-open-* 签名头、合同草稿与文档、签署位置与签署链接、撤回作废、印章与企业 / 个人认证、回调） | **文档版**（2026-09-11）：整理自官方文档（133 页）与官方 GitHub 示例，未用真实凭证验证；无凭证探测证实 2 处文档缺漏（鉴权失败实际返回 HTTP 441 / 442，两个码都不在错误码表里；错误响应同时带 `code` 与 `responseCode`，文档各页只写其一）。验证计划见 `skills/qiyuesuo/data/verification-plan.md` |
| `esign` | e签宝 SaaS API V3（HmacSHA256 请求签名与 Content-MD5、文件上传与模板、签署流程、个人 / 机构认证授权、回调） | **文档版**（2026-09-11）：整理自官方文档（110 页），未用真实凭证验证；无凭证探测核对了网关鉴权失败格式（HTTP 401「无效的应用」）与换 token 接口的错误码，未发现可证实的文档错误。验证计划见 `skills/esign/data/verification-plan.md` |
| `firecrawl` | Firecrawl 网页抓取/爬取/搜索 API（api.firecrawl.dev v2：单页抓取 17 种输出格式、批量抓取、整站递归爬取、URL 发现、网页搜索、结构化抽取） | **已实测**（2026-09-21）：用真实 Key 验证核心端点，查出 2 个静默失败陷阱（JSON 格式裸字符串不带 schema 时 `success:true` 但抽取实际失败；`/extract` 端点已被运行时标记废弃但文档页推荐迁移到另一个不同的端点，两处权威来源互相矛盾）与 2 处反直觉默认行为（`map` 不会自动扩展到整站；`search` 默认抓取每条结果全文）。5 场景对照实验：3 个完胜、2 个无 skill 版本凭合理工程直觉蒙对大方向但细节仍错，如实记录未夸大。见 `skills/firecrawl/data/comparison-report.md` |
| `exa` | Exa 语义搜索 API（api.exa.ai：Search、Contents、Find Similar、Answer、Agent 自主研究） | **文档版**（2026-09-21）：整理自官方 OpenAPI 规范（v2.0.0）与 `llms-full.txt`，未用真实凭证验证；交叉核对 OpenAPI 发现 `type` 参数已从训练数据熟悉的 neural/keyword 改成 instant/fast/auto/deep 等新枚举、`/findSimilar` 已被规范标记废弃、规范自身对 `resolvedSearchType` 字段是否废弃自相矛盾。对照实验待凭证到位，验证计划见 `skills/exa/data/verification-plan.md` |
| `e2b` | E2B 云沙箱平台（e2b.dev，Python/JS SDK 为主：代码解释器执行、Shell 命令、文件系统、沙箱生命周期与计费） | **文档版**（2026-09-21）：整理自 `docs.e2b.dev` 全站文档（270 页）与官方 OpenAPI 规范，未用真实凭证验证；同时交叉参考了 E2B 官方发布的 agent 专用 `e2b.dev/SKILL.md`（仅作对照，未照抄）。重点标注了默认超时会直接杀死长任务、代码解释器状态跨调用保留但 Shell 命令不保留这类反直觉行为。验证计划见 `skills/e2b/data/verification-plan.md` |
| `browserbase` | Browserbase 云端浏览器基础设施（sessions REST API + Stagehand 自然语言浏览器控制，代理/反检测/CAPTCHA） | **文档版**（2026-09-21）：整理自官方文档全站抓取，未用真实凭证验证；找出多处文档自相矛盾（免费套餐并发数文档两处不一致、`keepAlive` 描述引用了已不存在的套餐名、Selenium Node.js 两篇官方文档给出两种不同的鉴权头注入方式）。验证计划见 `skills/browserbase/data/verification-plan.md` |
| `perplexity` | Perplexity 搜索/问答 API（api.perplexity.ai：Sonar Chat Completions 带引用溯源、新的多供应商 Agent API、独立 Search API、Embeddings） | **文档版**（2026-09-21）：整理自官方文档与 OpenAPI 摘要，未用真实凭证验证；发现 API 表面已经从训练数据熟悉的"纯 Sonar 对话补全"扩展成四块（Router/Agent API/Search/Embeddings），文档里反复标注 Sonar 对话补全正在被引导迁移到新的 Agent API；Agent API 不传 `tools` 就只返回普通无引用回答，容易被当成默认自带联网检索。验证计划见 `skills/perplexity/data/verification-plan.md` |
| `pinecone` | Pinecone 向量数据库（api.pinecone.io：Vectors/Records/Documents 三条并行数据面、混合检索、集成 embedding 与 rerank、Serverless 索引） | **文档版**（2026-09-21）：整理自官方 OpenAPI 规范（`db_control`/`db_data`/`inference` 三份）与 `llms.txt`，未用真实凭证验证；发现一个索引上有三种互不通用的数据面（经典向量 API、集成 embedding 的 Records API、2026-07 新增带全文检索的 Documents API），当前二选一互斥；文档站自身对 Go SDK 大版本号（v4/v5/v6）三处不一致。验证计划见 `skills/pinecone/data/verification-plan.md` |
| `linear` | Linear GraphQL API（api.linear.app/graphql，唯一入口，无 REST：Issues/Teams/Projects/Cycles/WorkflowState，个人 API key 与 OAuth 两套鉴权、webhook、游标分页） | **文档版**（2026-09-21）：整理自 `developers.linear.app` 全部 26 篇文档页 + 官方 GraphQL SDL 规范原文（52,378 行，直接从字段类型/`required` 标记提取，不靠 prose 猜），未用真实凭证验证；核心发现是三个入口用三种不同鉴权头格式（个人 key 裸传不带 `Bearer`、OAuth token 要带 `Bearer`、官方托管 MCP server 也要带 `Bearer`，同一产品内部不统一）、`WorkflowState` 的 ID 按 team 严格隔离（跨 team 复用会静默失败）、默认分页在 50 条静默截断无报错。对照实验待凭证到位，验证计划见 `skills/linear/data/verification-plan.md` |
| `notion` | Notion API（developers.notion.com，api.notion.com：2026-03-11 版本，2025-09-03 起 database 拆分出 data source 概念、pages/blocks 树状内容模型、rich text 数组格式、search） | **文档版**（2026-09-21）：整理自 `llms.txt`/`llms-full.txt`（36k 行）+ 官方 OpenAPI 规范 + 约 160 篇真实文档页，未用真实凭证验证；确认当前版本确实建立在 database→data source 拆分架构上（不是训练记忆里的旧模型），且官方目前**没有 Python SDK**、只有 `@notionhq/client`（JS）；核心陷阱是 integration 必须在 Notion UI 里被显式"Add connections"共享到每个页面/数据库，否则合法 token 也只会拿到 404 而不是权限类报错，且 `Notion-Version` header 缺失不是报错而是静默返回和预期不同的响应形状。对照实验待凭证到位，验证计划见 `skills/notion/data/verification-plan.md` |
| `supabase` | Supabase 后端即服务（supabase.com/docs：PostgREST 自动生成的表 REST API、Auth、Storage、Realtime、Deno Edge Functions） | **文档版**（2026-09-21）：整理自 `supabase.com/docs` 的 `llms.txt` 与逐页抓取 + `postgrest.org` 的过滤语法文档，未用真实凭证验证；核心发现是官方正在把旧的 JWT 格式 `anon`/`service_role` key 迁移到新的非 JWT 短字符串 `sb_publishable_...`/`sb_secret_...`（两套并存到 2026 年底），且 `anon` key 被 RLS 拦掉时返回的是 `200` + 空数组（不是报错），容易被误判成"查询没结果"而不是权限问题；另外发现一个训练数据大概率没有的安全细节——RLS 保护不了 Realtime 的 DELETE 广播事件（Postgres 没法对一行已经不存在的记录做策略判断）。对照实验待凭证到位，验证计划见 `skills/supabase/data/verification-plan.md` |
| `stripe` | Stripe 支付 API（docs.stripe.com/api：PaymentIntents/Checkout Sessions、Customers、Subscriptions、Webhook 签名校验、幂等键） | **文档版**（2026-09-21）：整理自 `docs.stripe.com/llms.txt`（含专门给 LLM Agent 看的"Instructions for Large Language Model Agents"一节）与官方 OpenAPI 规范，未用真实凭证验证，**明确声明本 skill 不能用于自主转移真实资金**；确认 Stripe 当前官方推荐默认走 Checkout Sessions + Payment Element，明确建议"除非用户明确要求，否则不要用 PaymentIntent API"（比训练记忆里常见的手写 PaymentIntents+Elements 教程更省代码）；另发现 Stripe 自己的 agent 安全机制——打了 agent 标签的 Restricted API Key 会对退款、取消订阅等操作默认触发双人审批。对照实验待凭证到位（且严格限定在 test mode），验证计划见 `skills/stripe/data/verification-plan.md` |
| `sentry` | Sentry 错误监控（docs.sentry.io：摄入 API 用 DSN 走官方 SDK、管理 API `sentry.io/api/0/...` 用 auth token 查询/管理 issue、event、release、webhook） | **文档版**（2026-09-21）：整理自 `docs.sentry.io/llms.txt` + 官方 OpenAPI 规范（147 路径/234 操作），未用真实凭证验证；核心陷阱是两套完全独立的凭证体系（往 Sentry 里报错用项目 DSN 走 SDK；从外部查询/管理用 auth token 走管理 API，混用会直接失败）、EU 区域账号的管理 API base URL 是 `de.sentry.io` 不是通用的 `sentry.io`（硬编码域名会全部打到错账号）、批量 resolve issue 端点对超出权限范围的 ID 是静默跳过而不是报错。对照实验待凭证到位，验证计划见 `skills/sentry/data/verification-plan.md` |
| `twilio` | Twilio 短信/语音/OTP API（www.twilio.com/docs：Account SID + Auth Token 的 HTTP Basic Auth、Messages 短信、Verify 二次验证、Voice + TwiML、webhook 签名校验） | **文档版**（2026-09-21）：整理自 `docs.twilio.com` 官方文档与 `twilio-oai` 仓库的官方 OpenAPI 规范（v2010/Verify v2/IAM v1），未用真实凭证验证；核心陷阱是鉴权走 HTTP Basic（不是这批其余 skill 统一用的 Bearer token，在同一个项目里连续接了好几个 API 之后最容易写错）、手机号必须是 E.164 格式否则同步报错（错误码 21211/60200）、Verify 是"发起"和"校验"两次独立调用（第一次调用本身不返回验证码）、被叫方（inbound webhook）必须回 TwiML（XML）而不是常规 REST 调用期待的 JSON，两个方向的协议完全不同。对照实验待凭证到位，验证计划见 `skills/twilio/data/verification-plan.md` |
| `apify` | Apify 网页抓取/自动化平台（Actor 运行与市场、Dataset/Key-Value Store/Request Queue、Webhook；`apify` Actor 开发 SDK 与 `apify-client` 平台调用 SDK 是两个不同的包） | **文档版**（2026-09-21）：整理自官方 OpenAPI 规范（231 端点）与 `llms-full.txt`，未用真实凭证验证；计费模型是"计算单位 × 每个 Actor 各自的定价方案"，和 Firecrawl/Exa/Tavily 的固定 credits 模型完全不同，容易被套用错误的成本估算方式。验证计划见 `skills/apify/data/verification-plan.md` |
| `tavily` | Tavily 搜索与内容 API（api.tavily.com，专为 AI Agent / RAG 设计：Search、Extract、Crawl/Map、Research 深度研究、Python/JS SDK、CLI、MCP、keyless、x402） | **文档版**（2026-09-21）：整理自官方 OpenAPI 3.0.3 规范与 `llms-full.txt` 全站文档，**连无凭证探测都还没做**（没有对 `api.tavily.com` 发起过任何真实请求），比其余「文档版」条目更早期；靠交叉阅读 OpenAPI / Best Practices / Changelog / CLI 文档找出 4 处文档自相矛盾（`max_results` 默认值 10 vs 5、`chunks_per_source` 对 `basic` 深度是否生效、Python SDK 的 `map`/`mapping` 方法名、MCP 工具清单两处文档不一致）。对照实验待凭证到位，验证计划见 `skills/tavily/data/verification-plan.md` |
| `elevenlabs` | ElevenLabs 语音 AI 平台（elevenlabs.io，api.elevenlabs.io：文本转语音含 WebSocket/SSE 流式、语音转文本 Scribe 含实时转录、Instant/Professional Voice Cloning 与 Voice Design、对话式语音 Agent 平台 ElevenAgents/Conversational AI、各产品独立计费单位） | **文档版**（2026-09-21）：整理自 `llms.txt` 索引页 + API Reference 逐端点 Markdown 导出 + 定价计算器实时页面文本，**连无凭证探测都还没做**；`openapi.json`/`asyncapi.json` 规范文件本身返回 `401 Unauthorized`（浏览器直接打开也一样），无法下载核对，字段表全部来自各 endpoint 自己的 Markdown 导出页。靠交叉阅读多篇文档找出 3 处文档自相矛盾（PVC 训练耗时"几分钟" vs "3~6 小时"两种说法、STT 附加参数计费的百分比口径与定价页固定单价口径换算不完全对得上、多声道转录时长上限 1 小时 vs 10 小时）与一条强合规规则（PVC 即使征得本人同意也不能由他人账号代为创建）。对照实验待凭证到位，验证计划见 `skills/elevenlabs/data/verification-plan.md` |
| `slack` | Slack 开发者平台（docs.slack.dev，`api.slack.com` 已把正文迁移过去：OAuth v2 与细粒度 scope、Web API `chat.postMessage`/`conversations.*`、Block Kit 与 mrkdwn、Events API 与 Socket Mode、slash command 与交互组件、限流分级） | **文档版**（2026-09-21）：整理自 `docs.slack.dev` 的 `llms-full-platform.txt` 索引与近 50 篇官方页面，未用真实 App/bot token 验证；做了 4 次无凭证探测证实"HTTP 状态码恒为 200、错误信号在响应体 `ok`/`error` 字段"这条核心断言（`not_authed`/`invalid_auth`/`unknown_method`）。对照实验待凭证到位，验证计划见 `skills/slack/data/verification-plan.md` |
| `airtable` | Airtable Web API（airtable.com/developers/web/api：个人访问令牌与 OAuth 细粒度 scope、记录读取与 `filterByFormula` 公式过滤、记录批量增删改、字段类型与只读计算字段、附件专用上传流程、Metadata API 读写 base/table/field 结构、按 base 分层限流） | **文档版**（2026-09-21）：整理自 `llms.txt` 索引下的全部 API reference Markdown 导出页 + 从页面渲染 HTML 内嵌数据中提取出的完整 OpenAPI 3.1.0 规范（无独立公开的 `/openapi.json` 路径）+ `support.airtable.com` 公式函数参考页，**连无凭证探测都还没做**；最大发现是官方文档正文和内嵌规范都**没有**明确写出批量写请求的记录数上限，只能靠官方并列推荐的 `pyairtable` 源码硬编码 `MAX_RECORDS_PER_REQUEST = 10` 佐证；另确认 `filterByFormula` 是 Airtable 自有公式语言（非 MongoDB 风格操作符对象）、计算字段只读、附件大文件上传走独立的 `content.airtable.com` 域名。对照实验待凭证到位，验证计划见 `skills/airtable/data/verification-plan.md` |
| `hubspot` | HubSpot CRM API（developers.hubspot.com，api.hubapi.com：私有应用 access token / 新版 Service Key beta / OAuth 应用鉴权、统一的 `crm/objects/{objectType}` 对象增删改查覆盖 contacts/companies/deals/自定义对象、associations 关联 API、CRM Search 的 `filterGroups` 过滤、批量端点、自定义对象 Schemas API、burst+daily 双重限流） | **文档版**（2026-09-21）：整理自 `llms.txt` 索引与各 API reference 页面内嵌的 OpenAPI 片段，**连无凭证探测都还没做**；核心发现是 HubSpot 已从训练语料常见的 `hapikey` 鉴权彻底转向私有应用 token / OAuth，且 2026-09 起改为日期版本化 API（`/crm/objects/2026-09/...`），但即使是当前文档自身，各页面示例代码在 `v3` 与 `2026-09` 两种路径前缀之间也不统一；交叉阅读发现 2 处文档自相矛盾（"API Limit Increase" 加购后的 burst 限速一处写 200/10秒、另一处写 250/10秒；创建记录的 OpenAPI 规范把 `associations` 标为必填字段，但站内全部示例代码都省略它）与一条训练截止后新出现的规则（2026-09 起对 CRM 写请求强制执行账号管理员配置的校验规则，影响范围未定论）。对照实验待凭证到位，验证计划见 `skills/hubspot/data/verification-plan.md` |
| `resend` | Resend 交易邮件 API（resend.com/docs，api.resend.com：Bearer token 鉴权、`POST /emails` 发信（附件/CC-BCC/定时发送）、`POST /emails/batch` 单次最多 100 封、自定义发信域名的 SPF/DKIM/DMARC 验证、React Email / Resend Templates、Webhook 送达/退信/投诉事件、限流与配额） | **文档版**（2026-09-21）：整理自官方 `llms.txt`/`docs/llms.txt` 索引（77 篇页面）与官方 OpenAPI 规范（v1.5.0），未用真实凭证验证；核心发现是未验证域名发信会明确返回 `403 validation_error`（不是静默回退到共享域名），且 Node SDK 返回 `{data,error}` 而 Python SDK 是 raise 异常，两者错误处理机制完全相反；另证实一处规范与文档自相矛盾（`POST /emails/batch` 的 OpenAPI schema 允许 `attachments` 字段，但两处独立文档正文都明确说批量端点不支持附件）与一处规范缺口（5 个 webhook 管理端点只在文档正文出现、`openapi.json` 里完全没有）。对照实验待凭证到位，验证计划见 `skills/resend/data/verification-plan.md` |

**两个等级**：「已实测」的 skill 每条结论都用真实 API Key 调过，并做了装与不装的对照实验；「文档版」按 `create-doc-skill` 的降级方案产出（抓取文档 + 无凭证探测 + 写好评测用例），SKILL.md 开头有「验证状态」一节，文档转录的报错一律标「文档原文，未实测」，拿到凭证后补测升级。

## 装到你的 Agent

把这句话发给 Claude Code / Codex / Cursor，它会自己装好（把加粗部分换成你要的 skill 名）：

```
读 https://github.com/fxp/skillify/blob/main/skills/bigmodel-cn/prompt.md 并照它执行
```

或者直接给命令：

```
npx -y skills add fxp/skillify --skill bigmodel-cn --yes
```

每份 skill 都配了 `prompt.md`（六段模板：安装 → 自检 → 覆盖范围 → 版本），
里面明确写了 Agent 做不到的那一步（Claude Code 的 `/reload-plugins` 需要人手动执行），
也要求它安装前先做幂等检查，不会要求跳过全局配置变更的确认。

## Skill 的三层结构

三份 skill 都按**分段披露**组织，Agent 不会一次读完全部内容：

| 层 | 是什么 | 什么时候加载 | 体积 |
| :-- | :-- | :-- | :-- |
| 1 | `description`（frontmatter） | **永远在场**，是触发器 | 一段话 |
| 2 | `SKILL.md` 正文 | 触发后 | 5–8 KB / 74–89 行 |
| 3 | `references/*.md` | 按需打开 | 3–14 份 |

第 2 层只做四件事：**当前事实**（Base URL、活的模型名）、**纠正训练记忆**、**路由表**、**house rules**，
本身几乎不含字段表。文档与实测不符之处在 reference 里用 `<!-- Gap: … -->` 统一标记，可直接 grep。

> ⚠️ **一个反直觉的实测结论：第三层不能为了省 token 而拆细。**
> 做过一轮把大 reference 拆小、并在 SKILL.md 里加「只读你需要的那节」的版本——
> token 确实降了，**准确率却掉了**（弱执行器上 22/40 vs 原版 27/40）。
> 弱模型不知道该开哪一份，省下的正是它写对代码所必需的上下文。
> 分层的意义是**让常驻层职责单一**，不是让细节层变薄。详见
> `bigmodel-cn-workspace/weak-exec/RESULTS.md`。

## 评测流程

1. 在 `glm-round*/PROTOCOL.md` 里写场景与判分标准，**开跑前冻结**。
2. `run_agents.sh` 用 **GLM-5.3** 作执行 Agent，对每个场景各跑 n 次带 skill 与不带 skill 的任务；
   两侧都能联网查文档，Agent 写代码时拿不到 Key。
3. `grade.py` 用真实 Key **执行**生成的脚本，按冻结标准判分，写入 `grading.json` / `summary.json`。
4. 判据必须以真实 API 的实际返回为准，不能只看 OpenAPI 规范；发现的文档错误直接改回 `references/`。
5. 用 Fisher 精确检验算满分率的双尾 p；打平、落后、出题失误一律如实记录。
6. 所有轮次做完后，写一份 `comparison-report.md`。

**执行器不可混用**：不同模型担任执行 Agent 的结果不能合并统计。早期用 Claude 执行的轮次已从所有报告中删除。

**测"优化有没有用"要换弱执行器**：GLM-5.3 配一份像样的说明书就在 92%~97% 满分，天花板效应让
n=5 测不出任何差异。换 `glm-4.5-flash`（实测未被静默重路由）后原版掉到 27/40，才有 32.5% 的
测量空间。五轮优化尝试正是在这个条件下被证伪的。

## 什么样的场景才有区分度

反复出现打平之后，复盘总结出一个可复用的出题配方——**三条缺一不可**：

1. **任务约束堵死绕行路线**。坑只有在任务逼着走那条路时才会被踩到，否则称职的 Agent 会绕过去
   （例：不加"要复用 file_id"这句，Agent 就用 base64 内联，完全避开 `purpose` 的坑）。
2. **正确答案不在文档正文里**。只存在于报错信息里、或与 OpenAPI 规范矛盾的知识，联网也查不到。
3. **错误是静默的或延迟暴露**。上传成功不代表能用；HTTP 200 不代表拿到了想要的字段。

**第 ② 条是决定性的那一条。** 第五轮专门挑了 4 个 HTTP 200 的静默失败来扩证，结果**零显著**——
因为那四个坑的正确答案官方文档里查得到（思考 token 计入 `max_tokens`、`tool_choice` 仅支持 `auto`
都是文档写明的），能联网的称职 Agent 自己就会了。**「静默」是必要条件，不充分。**

还有一条只有踩过才知道的**第 ② 条推论**：正确答案也不能出现在**任务描述本身**里。
火山方舟那轮有个场景就是这么废掉的——任务里写了"必须确保用的是 doubao-seed-2.0-lite"，
于是两侧都显式传了模型名，静默换模型的坑根本没机会触发。

反例：embeddings 单次 64 条上限会响亮报错，而"分批"是任何工程师的默认习惯——
这类"响亮且符合常识"的坑不适合作为区分度场景，实测确实打平。
AutoDL 的余额换算（元×1000）同理：联网查得到，baseline 5/5 都算对了。

## 报告格式约定

- 对比报告统一为 `<skill>-workspace/comparison-report.md`，以后新增的 skill 也遵守此约定。
- 报告结构：顶部指标汇总表；每轮一张「场景 / 结果 / skill 得分 / baseline 得分」表，每个场景附 **Task** 和 **Why** 两段说明；结尾列出评测中修正的文档条目。
