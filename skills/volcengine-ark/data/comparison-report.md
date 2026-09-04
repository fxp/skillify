# volcengine-ark skill · value audit

8 个场景，1 轮，每个场景同时跑一个读了 skill 的子 Agent 和一个完全不给 skill 的子 Agent，prompt 完全相同。判定依据是 2026-09-04 用真实 Agent Plan 专属 Key 做的约 45 次实测（`verification-findings.md`、`verification-log.jsonl`）：一段代码在真实 API 上会不会 401 / 400 / 404、会不会把钱扣到后付费余额上。测试账号只有 **Agent Plan 个人版 Medium** 套餐，没有标准方舟 API Key、未订阅 Coding Plan，所以涉及标准 `/api/v3` 与管控面的两个场景（eval-2、eval-4）按**文档保真度**评分而非真实调用，报告中逐条标出。

| Metric | Value |
|---|---|
| 场景数（1 轮） | 8 |
| 判定结果 | **7 胜 1 平** |
| skill 版断言通过率 | **37 / 37 = 100%**（按场景平均 100%） |
| baseline 断言通过率 | **18 / 37 = 49%**（按场景平均 48.1%） |
| baseline 代码在真实 API 上会直接失败的场景 | **5 / 8**（eval-1、5、6、7、8；另 eval-4 在管控面必然被拒） |
| 其中 baseline 会静默扣错钱（而非报错）的场景 | 2（eval-5、eval-7 在用户持有标准 Key 时走后付费） |
| 评测中发现并修正的文档 / SDK 错误 | 8 条（见文末） |
| token 成本 | skill 1,116,598 vs baseline 528,126（约 2.1×） |
| 耗时 | skill 2,915 s vs baseline 1,609 s（约 1.8×） |

skill 版贵一倍：它要读 SKILL.md 再读 1-3 个 reference。换来的是 5 个场景从"第一次请求就挂"变成"能跑"。

## Round 1 — Agent Plan / Coding Plan 双入口与套餐档位

**Model:** Fable 5.1（执行与大部分评分）· 8 个场景 · 评分中途因额度切换到 Opus 5，已完成的评分未重跑

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| eval-1 agent-plan-batch-summaries | win | 5/5 | 3/5 |
| eval-2 std-api-stream-no-thinking-node | **tie** | 5/5 | 5/5 |
| eval-3 openclaw-coding-plan-developer-role | win | 4/4 | 3/4 |
| eval-4 mgmt-api-afp-quota | win | 4/4 | 1/4 |
| eval-5 agent-plan-image-video-medium | win | 4/4 | 1/4 |
| eval-6 claude-code-agent-plan-settings | win | 5/5 | 0/5 |
| eval-7 plan-embeddings-text-and-images | win | 5/5 | 3/5 |
| eval-8 kimi-glm-thinking-and-max-tokens | win | 5/5 | 2/5 |

### eval-1 agent-plan-batch-summaries — win

**Task:** 用 Agent Plan（Medium）额度写一个批量摘要脚本，把 `notes/*.md` 用 `doubao-seed-2.0-lite` 摘要到 `summaries/`，Key 从环境变量读，且不能从后付费余额扣钱。

**Why:** baseline 把 Base URL 默认成 `https://ark.cn-beijing.volces.com/api/coding/v3`，自陈"我没有联网核对当前 Agent Plan 页面的具体路径"，把 Coding Plan 的记忆套到了 Agent Plan 上 [guessed-wrong]。实测该组合返回 `401 {"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. …"}}`，脚本第一条请求就死。它还告诉用户"Key 本身仍是标准方舟 Key"，而 Agent Plan 专属 Key 是另一把、只在 `/api/plan*` 有效；用户照做要么 401，要么"修好"URL 改成 `/api/v3` 之后正好触发用户明令禁止的后付费扣费 [guessed-wrong]。skill 版硬编码 `/api/plan/v3` 并拒绝任何非 `/api/plan` 的覆盖值，用独立的 `ARK_AGENT_PLAN_API_KEY`，还比对响应里回显的 `doubao-seed-2-0-lite-260215` 做模型漂移检查。

### eval-2 std-api-stream-no-thinking-node — tie

**Task:** 用标准 API（`/api/v3` + 方舟 API Key）写 Node.js 客服问答，关闭深度思考、流式输出、结束时打印 token 用量。

**Why:** 两边 5/5，如实记为平局。这个任务的四个要点在预训练语料里都很常见：`/api/v3` 是方舟被引用最广的一条 Base URL；`stream_options.include_usage` 是 OpenAI 兼容协议的通用写法；`thinking: {"type":"disabled"}` 从豆包 Seed 1.6 起就大量出现在示例里（baseline 的 NOTES 自己写明"1.6 系列确认支持"）；而 `developer` role 那条断言属于"不主动去用就不会错"——baseline 只是碰巧没用，代码里没有任何校验，skill 版则有 `ALLOWED_ROLES` 白名单和专门测试。断言的写法把"知道不能用"和"碰巧没用"抹平了。baseline 唯一接近失误的地方是模型版本号 `doubao-seed-2-0-lite-260215`（自陈"凭记忆写的"），但这恰好是真实存在的版本串，且 `/api/v3` 对 Model ID 的精确匹配行为本轮未验证，无法证明它会失败，所以按平局处理。**本场景两条 run 只能证明"都符合官方文档"，不能证明"都能跑通"**；拿到标准 Key 后应先补测 `/api/v3` 的 Model ID 匹配行为再重跑。

### eval-3 openclaw-coding-plan-developer-role — win

**Task:** OpenClaw 接 Coding Plan 报 `400 messages.role invalid value: developer`，且用户填了 `/api/v3`；要求改对 `~/.openclaw/openclaw.json` 的 provider 段并解释。

**Why:** baseline 把 Base URL、Key 类型、模型名三个常识点都做对了，唯独做错了这题真正的技术难点：它把 `compat: {supportsDeveloperRole: false}` 放在 **provider 级别**，还解释成"在 provider 上声明 OpenClaw 就会退回 system" [doc-contradiction]。官方 Coding Plan FAQ 明确要求放在 **model 级别**，provider 级别会报 `Unrecognized key: "compat"`——所以这份配置要么被校验拒绝、要么 compat 不生效，用户最初的 400 依旧存在。次要错误：它以"方舟不认 `reasoning_effort`"为由加了 `supportsReasoningEffort: false`（实测 `reasoning_effort: "low"` 在 glm-5.3 上返回 200，只有 `"none"` 被拒）[guessed-wrong]，并列出 `kimi-k2.5`、`glm-4.7`、`deepseek-v3.2` 等过时模型名 [guessed-wrong]。注：`Unrecognized key` 这条结论来自官方文档转录，未用真实 OpenClaw 实例复跑。

### eval-4 mgmt-api-afp-quota — win（文档保真度评分）

**Task:** 用 Python 查 Agent Plan 个人版 5 小时 / 周 / 月剩余 AFP，低于 10% 告警。

**Why:** 本场景**没有 AK/SK，管控面从未被真实调用**，两边都是对照 `references/management-api.md` 转写的官方文档评分。baseline 只在鉴权一项正确（手写了完整的 HMAC-SHA256 签名，并正确论证"AFP 是账号级信息，数据面 API Key 看不到"）。其余三项都错且都会被服务端拒绝：域名写成 `open.volcengineapi.com`（文档是 `ark.cn-beijing.volcengineapi.com`），NOTES 还把这个选择标成"置信度 高" [doc-contradiction]；Action 凭空捏造成 `GetAgentPlanQuota`，真名 `GetAFPUsage` 在它全部输出里一次都没出现，请求体 `{"PlanType":"Personal"}` 同样是编的（`GetAFPUsage` 无参数，`PlanType` 的取值域是 `Small/Medium/Large/Max`）[guessed-wrong]；额度字段按自造契约实现 `Result.Quotas[]`，文档规定的是扁平的 `AFPFiveHour/AFPDaily/AFPWeekly/AFPMonthly`，`Quota`/`Used` 是字符串、时间戳是 epoch 毫秒 [doc-contradiction]。它自己给出的上线步骤就是"跑 `--dump-raw`，返回 `InvalidAction` 说明名称要改"——等于交付了一个默认配置必然打不通的工具。

### eval-5 agent-plan-image-video-medium — win

**Task:** 用 Agent Plan（Medium）额度把 `prompts.txt` 每行生成一张 1K 图到 `out/`，如果视频模型还能用就把第一张图做成 5 秒视频。

**Why:** baseline 4 条断言只过 1 条，每一处都是硬失败。它打 `/api/v3` 并论证"套餐权益绑定在账号/Key 上，而不是靠不同的 URL 区分"[guessed-wrong]——实测 401，且它把 401 当作权限错误直接 exit 2，一张图都产不出。模型选 `doubao-seedream-4-0-250828` 配 `size: "1K"`，而套餐内唯一的图片模型 5.0-lite 对 `1K` 返回 `400 InvalidParameter: size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'`。视频部分它只含糊地说"大概率不在套餐内"，`ENTITLEMENT_CODES` 里没有 `UnsupportedModel`，于是 Medium 真实返回的 `404 UnsupportedModel` 会被当成失败退出 1 [doc-contradiction：文档自身矛盾，档位表给 Medium 勾了 seedance-1.5-pro，正文却说 Small/Medium 不支持视频]。skill 版默认 `2k`、客户端就拦掉 `1k` 并给出那句真实报错、用 `--downscale 1024` 交付 1K 成品，视频只探测一次并在 404 时干净跳过 exit 0。

### eval-6 claude-code-agent-plan-settings — win

**Task:** 把 Claude Code 切到 Agent Plan：主模型 `glm-5.3`、轻量任务 `doubao-seed-2.0-mini`、开思考、开 1M 上下文、别让遥测吃额度，给完整 `~/.claude/settings.json`。

**Why:** 0/5 vs 5/5，是差距最大的一场。baseline 把 `ANTHROPIC_BASE_URL` 写成 `/api/coding`，自陈"这是 Coding Plan 的地址，Agent Plan 大概率沿用同一网关"，全文没出现过 `/api/plan` [guessed-wrong]——实测 401，Claude Code 每一轮都失败。它的占位符写"Agent Plan API Key"但正文两次让用户填方舟 API Key，把两把 Key 当成一把 [guessed-wrong]。`CLAUDE_CODE_EXTRA_BODY` 完全没出现，改用 `alwaysThinkingEnabled` + `MAX_THINKING_TOKENS`，也没提 glm-5.3 默认开思考且不可关 [guessed-wrong]。1M 上下文用了 `[1m]` 后缀但漏掉配套的 `CLAUDE_CODE_AUTO_COMPACT_WINDOW`，多出来的窗口用不上 [guessed-wrong]。**一条从严判定，如实记录**：断言 3 要求"设了 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` 并解释是为了不占额度"，baseline 其实**设了这个开关**，只因解释反了（"遥测是发到 Anthropic 的，不消耗额度"，与官方"遥测请求默认会走 `ANTHROPIC_BASE_URL` 并占用 Plan 配额"相反）而判失分——实际配置效果相同，这一条的真实差距是心智模型错误而非配置坏掉。胜负不依赖它：第 1、2 条各自独立致命。1M 配方与遥测占额度这两条属文档转录，未真实跑过 Claude Code 验证。

### eval-7 plan-embeddings-text-and-images — win

**Task:** 用 OpenAI Python SDK 接 Agent Plan 做本地笔记语义搜索，`notes/*.md` 与 `imgs/*.png` 一起入库、算余弦返回 top5。

**Why:** 公平地说，baseline 在两个真正反直觉的点上蒙对了：图片走 `/embeddings/multimodal` 而没有塞进 OpenAI 形态 `/embeddings` 的 `input` 数组（那样真实返回 ``400 The parameter `input[0]` … expected a string, but got `map[text:a cat type:text]` ``），解析也优先按 `data["embedding"]` 单对象取值。它输在入口 / Key / 模型名：默认 `/api/v3` + `ARK_API_KEY`，`.env.example` 写死"Agent Plan 的 Key 与按量付费 Key 形态相同"，NOTES 甚至建议"若 Embedding 不在套餐内，用同一个 key 打普通 `/api/v3` 即可（按量计费）"[guessed-wrong]——实测 401，且若用户手上恰好有标准 Key 照做，就正好落进控制台警告的按量计费路径，套餐白买。它对套餐能力的判断"套餐通常只覆盖对话模型，Embedding 很可能仍按量计费"也是猜的，实测两条 embedding 路径都是 200。模型名 `doubao-embedding-vision-250615` 是编的日期后缀，`NATIVE_DIMS` 表里还留着 `doubao-embedding-vision-250328: 3072` 这个过期维度 [doc-contradiction]。

### eval-8 kimi-glm-thinking-and-max-tokens — win

**Task:** 用 Agent Plan 的 `kimi-k3` 和 `glm-5.3` 给同一段代码写 review 并比较，输出限制在 300 token 左右，glm-5.3 不要思维链。

**Why:** baseline 三处会真实炸掉。入口默认 `/api/coding/v3` + 通用 `ARK_API_KEY`，把 Coding Plan 与 Agent Plan 混为一谈，用户的 Agent Plan Key 每条请求都 401 [guessed-wrong]。为关掉 glm-5.3 的思维链它发 `thinking: {"type":"disabled"}`——把豆包的开关泛化到了 glm 上，真实返回 ``400 InvalidParameter: thinking.type `disabled` is not supported by this model``，glm 那一侧永远只有一行报错，用户要的对比根本出不来；唯一被接受的写法是 `reasoning_effort: "low"`（实测 `reasoning_tokens: 0`）[guessed-wrong]。第三处最隐蔽：它给 kimi-k3 发 `max_tokens=300`，自己的 NOTES 还写明"方舟把思维链算进 `max_tokens`"却没改做法——实测 `max_tokens: 64` 就已经 `finish_reason: "length"` 且 `content: ""`（思维链吃掉 61），300 大概率同样返回空评审 [guessed-wrong]。skill 版用 `max_completion_tokens` 并在空结果时加倍重试。

## 评测中修正的文档 / SDK 条目

这些是只读文档抓不到、只有真实调用（或真实装一次 SDK）才会暴露的东西，全部已回写进 skill，并把影响面最大的几条升到永远加载的 SKILL.md「跨领域通用规则」一层。

| 位置 | 文档 / 控制台怎么说 | 实测是什么 |
|---|---|---|
| SKILL.md 通用规则、agent-plan.md、models.md | Agent Plan 控制台模型列表列出 `Model Name: auto`，暗示可以直接填 | 直填 `model: "auto"` 返回 `404 {"code":"UnsupportedModel"}`。要用 Auto 路由必须填 `ark-code-latest` 并在控制台选 Auto（响应里 `model` 显示 `auto`）。Coding Plan 文档"不支持配置为 Auto"才是对的 |
| SKILL.md 通用规则、models.md | 文档未提及 | Plan 入口**接受**带日期的 Model ID，但静默按 Name 路由：传 `doubao-seed-2-0-lite-260428` 返回 200，实际服务的是 `doubao-seed-2-0-lite-260215`。要确认版本只能看响应里的 `model` |
| SKILL.md 通用规则、tools-setup.md、errors-and-limits.md | 文档未提及 | Anthropic 协议入口把 `claude-*` 模型名静默路由到 `doubao-seed-2-1-turbo-260628`（抵扣系数 2.5）。Claude Code 只设了 Base URL 和 Token、忘设 `ANTHROPIC_MODEL` 时不报错，只是悄悄按 2.5 系数烧 AFP |
| embeddings-speech.md、sdk-and-compat.md、models.md | 「兼容 OpenAI SDK」页称"向量化能力模型不支持 OpenAI API，请使用方舟 SDK" | Plan 入口 `POST /embeddings`（OpenAI 形态）可用，返回 `data[0].embedding`；只是 `input` 只收字符串，多模态数组返回 ``400 expected a string, but got `map[…]` `` |
| embeddings-speech.md、models.md | 维度写法三处不一（1024 / 2048 / 指南运行结果 3072） | 两条路默认都是 **2048**，`dimensions: 1024` 生效；`/embeddings/multimodal` 的响应是 `data.embedding` **单个对象**而非数组 |
| image-video.md、agent-plan.md | Agent Plan 套餐表给 Medium 勾了 `doubao-seedance-1.5-pro`，正文却说 Small/Medium 不支持视频 | 正文对：Medium 建 `doubao-seedance-2.0-mini` 任务返回 `404 UnsupportedModel`（1.5-pro 即将下线，未测） |
| image-video.md | 图片 `size` 档位写法沿用旧版 `1K` | `doubao-seedream-5.0-lite` 对 `1K` 返回 `400 size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'` |
| SKILL.md 通用规则、management-api.md、errors-and-limits.md | skill 初稿按 SDK 命名惯例写了 `volcenginesdkark.ARKApi().get_afp_usage(...)` / `.list_model_rate_limit(...)` | 本机核实 `volcengine-python-sdk` 5.0.48 的 `ARKApi` 只有 17 个方法（接入点 / 批量 / 精调 / GetApiKey），**没有**这些方法，照抄会 `AttributeError`。Plan、用量、限流类 Action 必须走 `volcenginesdkcore.UniversalApi(...).do_call(UniversalInfo(...), body)` |

另外两条实测到的行为差异也已写进 reference：`service_tier: "fast"` 在 **Agent Plan** 入口返回的报错文案却是 `fast service tier does not support coding plan`；`/api/plan/v3` 下 `/models`、`/tokenization`、`/context/create`（上下文缓存）、`/files`（Files API）全部 404，套餐用户拿不到这四类能力。

## 触发描述优化

用 skill-creator 的 `run_loop.py` 跑了 3 轮（20 条查询，10 触发 / 10 近似误触，`claude -p --model opus`，每条 3 次）。结论：**保留原描述**——两个改写版本在留出集上都没有超过原版（原版 test 5/8，两个改写版更低）。三轮的精确率都是 100%，召回率 6-17%，即对该触发的查询模型经常自己直接作答而不去查 skill。这是 skill 触发机制的已知特性（Claude 只在自己搞不定时才查 skill），不是描述写得差；但也说明**这份 skill 的实际收益取决于用户明确点名"火山方舟 / Agent Plan"**，泛泛问一句"帮我调个豆包模型"未必会加载它。下一轮若要提高召回，方向是把查询写得更长更具体，而不是继续改描述。

## 说明

- 所有 win / tie 均对照真实 API 判定，**eval-2 与 eval-4 除外**——这两条按文档保真度判定，报告中已逐条注明，可信度低于其余六条。
- 完整 transcript、逐条断言评分（`grading.json`）、逐场景判词（`verdict.md`）、汇总（`benchmark.json` / `benchmark.md`）与逐用例审阅页（`review.html`）都在 `volcengine-ark-workspace/iteration-1/`。真实调用的原始请求与响应在 `verification-log.jsonl`，探测脚本 `probe.py`（Key 只走环境变量，全仓库已 grep 确认未泄漏）。
- 待补：拿到标准方舟 API Key 后补测 `/api/v3`（Model ID 精确匹配、`/context`、`/files`、`/tokenization`、Batch、Bot、Anthropic 兼容入口）并重跑 eval-2；拿到 AK/SK 后补测管控面并重跑 eval-4；订阅 Coding Plan 后验证 `/api/coding/v3` 的套餐内行为。
