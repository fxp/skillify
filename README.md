# skillify

把 SaaS / 开放平台的开发者文档，变成 AI Agent 可以直接拿去写代码的 Claude Skill——不是"把文档丢给 Agent 转述一遍"，而是**读文档打草稿 → 用真实 API Key 逐条验证 → 用真实前后对照实验证明技能确实有用**再交付。

方法论本身也是一份 Skill：[`skills/create-doc-skill`](skills/create-doc-skill)（原 `generate-skill-from-api-docs`，2026-09 重写：SKILL.md 只留流程与关键判断，细节拆进 `references/`，新增 `scripts/fetch_docs.sh` 与 `scripts/openapi_summary.py`）。

## Skills

| # | Skill | 覆盖范围 | 状态 |
| :-- | :-- | :-- | :-- |
| 1 | [`bigmodel-cn`](skills/bigmodel-cn) | [智谱AI开放平台](https://bigmodel.cn)（`open.bigmodel.cn`）—— GLM 系列对话/多模态模型、图像与视频生成、语音识别合成、Embeddings/Rerank、联网搜索、文件与批处理、托管知识库、Agents API、GLM-Realtime、OpenAI/Claude/LangChain 兼容层、**GLM Coding Plan 编程套餐**（专用 Key / Base URL / 可用模型 / 1113 排错 / Claude Code 配置） | ✅ 已生成，7 轮共 25 个场景真实 API 对照验证（第 7 轮为真实执行的端到端成功率），9 处文档偏差已修正 |
| 2 | [`autodl`](skills/autodl) | [AutoDL 文档](http://www.autodl.com/docs/) —— GPU 算力租用平台的账户/容器实例/弹性部署 API | ✅ 账户 + 容器实例 Pro API 全部接口、弹性部署全部只读接口已用真实 Token 验证；⚠️ 弹性部署创建/管理类接口仍未验证（测试账号没有企业认证，这是账号资质的硬性限制，不是没测） |
| 3 | [`volcengine-ark`](skills/volcengine-ark) | [火山引擎·火山方舟](https://www.volcengine.com/docs/82379)（`ark.cn-beijing.volces.com`）—— 豆包 Doubao / Seed / Seedream / Seedance 及方舟上的 GLM、Kimi、DeepSeek、MiniMax；Chat Completions、Responses API、多模态理解、图片与视频生成、向量化、语音、批量推理、内置工具、管控面 AK/SK 接口，**以及三套互不通用的入口**：标准后付费 API、**Coding Plan** 与 **Agent Plan** 两种订阅套餐（各自的 Base URL / Key / model 名格式 / 计费单位都不同） | ✅ 已生成，Agent Plan 入口用真实专属 Key 实测约 45 次调用；8 个场景对照评测 7 胜 1 平，8 处文档 / SDK 错误已修正；⚠️ 标准 `/api/v3` 与 Coding Plan 套餐内行为未实测（测试账号只有 Agent Plan，没有标准 Key、未订阅 Coding Plan） |

每个 skill 目录下都是一份可以直接安装使用的 SKILL.md + `references/`，外加一个 `data/` 目录留档对照测试的完整过程（prompt、打分依据、报错原文），不只是一个"通过率"数字。`autodl` 一开始是刻意保留的反例（没有 Token，只做了文档保真度测试），拿到真实 Token 后先测了只读接口，账号完成实名认证后又补测了完整的"创建实例 → 运行 → 关机 → 保存镜像 → 重新开机 → 释放"生命周期（真实花费不到 5 元）——过程中发现了 9 处文档本身的错误或遗漏，已全部修正并推动了三轮针对性的 with/without 对照评测。

## 验证结果

**bigmodel-cn**（用真实 `open.bigmodel.cn` API 调用结果打分，不是靠代码审查猜测）：

- 14 个场景，7 个打平（预训练知识本身已经覆盖到）
- 7 个场景没装技能包的版本会在真实调用下失败——典型如：OpenAI 风格的强制 `tool_choice` 被静默降级成 `auto`；`response_format: json_schema` 不报错但被静默忽略；GLM-5.3 无法关闭深度思考（换成 GLM-5.2 又完全没这个限制）；Batch 只认一份和主力模型清单不重合的白名单；PDF 传进对话消息时 `purpose=agent`/`code-interpreter` 上传的文件会静默解析失败，只有 `purpose=user_data` 才行

- 第 6 轮补上了之前完全没覆盖的 **GLM Coding Plan**：智谱有两套隔离的计费体系，套餐 Key 与平台 Key 不通用、Base URL 是 `…/api/coding/paas/v4` 而不是 `…/api/paas/v4`、套餐只含 `glm-5.3`/`glm-5.3-flash` 的对话能力。4 个场景 **100% vs 71%**——没装技能包的版本普遍知道 Coding 端点地址（GitHub issue 里传开了），但把 Key 来源写成控制台 API Keys 页面、把 Claude Code 的 haiku 档映射到套餐外模型、或者用一把 Key 同时打两个端点。用一把真实套餐 Key 和一把标准 Key 逐条实测后，又发现三处文档没写的行为：标准 Key 其实也能打 Coding 端点；`glm-4.6`/`glm-4.5-air` 会被静默路由到 `glm-5.3-flash`；`glm-5.3` "无法关闭思考"只在标准端点成立，Coding 端点传 `thinking: disabled` 会被接受并生效。
- 第 7 轮换了个更硬的标准：让 agent 写出对接脚本后**真的用套餐 Key 执行**，跑通并打印出模型回答才算成功。7 个场景各跑 3 次，**两边都是 21/21，打平**——顺路径上基础模型已经够用，技能包的价值集中在第 6 轮那些失败模式（Key 家族、套餐外模型/能力、1113 诊断），而不在"第一个请求能不能通"。这个平局如实记录，没有为了好看去挑场景。

详见 [`skills/bigmodel-cn/data/comparison-report.md`](skills/bigmodel-cn/data/comparison-report.md)；实测脚本在 [`skills/bigmodel-cn/data/coding-plan-probe.py`](skills/bigmodel-cn/data/coding-plan-probe.py) 与 [`skills/bigmodel-cn/data/run_iter7.py`](skills/bigmodel-cn/data/run_iter7.py)。

**autodl**：

- 文档保真度对照测试（没有真实 Token 时跑的，"对照官方文档判定谁写对了"，不是真实调用打分）：3 个场景 100% vs 40%——没装技能包的版本会编出这个平台并不存在的接口路径和字段：把 GPU 规格 ID 当成可以动态查询的接口（真实是静态文档表格）、账户余额换算系数套用国内支付类 API 常见的"除以100"习惯（真实是"除以1000"）、弹性部署的 `deployment_type` 猜成 `"fixed"`/`"scaling"` 这类通用云平台说法（真实取值是 `ReplicaSet`/`Job`/`Container`）。差距比 bigmodel-cn 更明显，因为 AutoDL 相对小众，公开语料对它 API 细节的覆盖比智谱这类头部平台少得多。详见 [`skills/autodl/data/iteration-1/review.html`](skills/autodl/data/iteration-1/review.html)。
- 拿到真实 Token 后追加验证了只读接口，发现**官方文档自己写错了传参方式**：`GET .../instance/pro/snapshot` 和 `GET .../instance/pro/status` 这两个接口，文档给的示例是 JSON body，但实测必须用 URL 查询字符串传参，用 JSON body 会直接报 `RequestParameterIsWrong`。这类"文档本身有 bug"的发现，只有真实调用能抓到，光靠"读文档写得对不对"的对照测试是测不出来的。
- 账号完成实名认证后，用一台真实创建的实例（真实花费约 0.03 元）跑完了完整生命周期：`create` 会自动开机，不需要额外调用开机接口；状态流转里有文档没写的 `starting`/`shutting_down` 中间态；`release` 前如果没有确认状态真的是 `shutdown`（哪怕只是还在 `shutting_down`），100% 会被拒绝，不是概率性失败。针对这三个发现专门设计了 3 个 with/without-skill 消融场景：**100% vs 46.7%**（delta +0.53），其中一个场景（清理流程）是个值得如实记录的"半打平"——没装技能包的版本单靠通用工程直觉就把"关机不是瞬间完成、release 前要等确认"这个高层逻辑做对了，真正拉开差距的是它编造的接口路径全是假的。详见 [`skills/autodl/data/iteration-2/review.html`](skills/autodl/data/iteration-2/review.html)。
- 又追加验证了两个之前没测过的接口：`power_on`（重新开机一台已关机的实例，确认了它的响应结构和 `power_off`/`release` 不一样，`data` 是带 `description` 字段的对象而不是 `null`）和保存镜像 `image/save`（发现另一处**文档没写的强制前置条件**——运行中的实例直接调用会被拒绝，返回 `{"code":"InternalError","msg":"保存实例镜像前，请确保实例是关机状态"}`，必须先关机）。针对"训练完存镜像再释放实例"这个更复杂的场景又跑了一轮消融测试：**100% vs 80%**（delta +0.20）——这轮 baseline 明显更强，会主动上网查官方文档、还设计了"创建一次性实例真的把镜像跑起来验证可用性"这种超出题目要求的严谨思路，但依然在文档没写对的 GET 传参方式上失分，因为这个信息只有真实调用才能拿到。详见 [`skills/autodl/data/iteration-3/review.html`](skills/autodl/data/iteration-3/review.html)。

- 补测了剩下所有账号权限内能测的接口：账户余额（真实响应比文档多出十来个字段，比如冻结金额 `blocked_asset` 完全没在文档里）、切换专用 NFS（开关各测一次，已确认可逆）、已释放实例会从"获取实例列表"里直接消失、查不回来（文档没提这个默认过滤行为）；弹性部署 API 的全部只读接口（GPU 库存、私有镜像列表、部署列表、时长包、调度黑名单）也都用真实调用逐个确认了权限门槛——**是按接口区分要不要企业认证，不是整个 API 一刀切**。还发现弹性部署自己的"获取镜像列表"和容器实例 Pro API 的"获取镜像列表"是两个不同接口、字段名都不一样，但共享同一份私有镜像仓库（同一个 `image_uuid` 两边都查得到）。至此，这个测试账号权限范围内能调用的接口已经全部用真实请求验证过一遍；唯一测不到的是弹性部署"创建部署"和依赖已有部署/容器 UUID 的管理类接口——这几个接口需要企业认证，属于账号资质的硬性限制，不是漏测。

三轮测试合起来正好说明为什么方法论坚持要走完真实验证这一步——静态测试能测出"有没有编造内容"，测不出"文档本身写没写对、写没写全"；而消融测试的价值也不在于"每次都赢很多"，越到后面 baseline 越聪明、差距越小甚至局部打平，这本身就是诚实的信号，不应该被刻意放大成夸张的胜率。完整的分场景对比表格和逐条"为什么"，见 [`skills/autodl/data/comparison-report.md`](skills/autodl/data/comparison-report.md)。

**create-doc-skill**（方法论本身的重写版，对照对象是重写前的旧版快照）：

- 2 个"没有 key 的草稿模式"场景（Resend：有 llms.txt 但 OpenAPI 链接写错；Kimi 开放平台：根路径没有 llms.txt，测 fallback），新旧两版按断言都是 18/18，**平局**。差异在过程而不是终态：新版用自带的 `fetch_docs.sh` / `openapi_summary.py`，抓取次数更少，references 里 endpoint 级的"未验证"标记密度高得多（132 处 vs 26 处），代价是更多 token 和内容量。评测中顺手修正了 9 条 skill 指引。另外用 skill-creator 的描述优化循环跑了 3 轮触发准确率评测（`data/description-opt/`）。详见 [`skills/create-doc-skill/data/comparison-report.md`](skills/create-doc-skill/data/comparison-report.md)。

**volcengine-ark**（用真实 Agent Plan 专属 Key 的调用结果打分；标准 API 与管控面这两个场景按文档保真度打分，报告里逐条标注）：

- 火山方舟最大的坑不是某个字段写错，而是**同一个域名下有三套互不通用的入口**：标准后付费 `/api/v3`（方舟 API Key + 带日期的 Model ID）、Coding Plan `/api/coding[/v3]`（同一把方舟 API Key + 小写 Model Name）、Agent Plan `/api/plan[/v3]`（**另一把专属 Key** + AFP 抵扣）。Base URL、Key、model 名三者必须配套，配错的后果不是报错，而是 401、或者把钱扣到后付费余额上。8 个场景里有 5 个的 baseline 就死在这一步。
- 8 个场景 **7 胜 1 平**，断言通过率 **37/37 vs 18/37**。唯一的平局是标准 API 的流式对话——`/api/v3`、`stream_options.include_usage`、`thinking: {"type":"disabled"}` 这些在公开语料里够常见，baseline 全做对了，如实记录，没有为了好看去挑场景。
- 真实调用抓到 8 处**只读文档抓不到**的问题，已全部修正并升到 SKILL.md 永远加载的那一层。举三个最贵的：控制台把 `auto` 列成可以直接填的 Model Name，实测直填返回 `404 UnsupportedModel`（只能填 `ark-code-latest` 再去控制台切）；Plan 入口**接受**带日期的 Model ID 却静默按 Name 路由（传 `260428` 实际服务的是 `260215`，只能看响应里的 `model` 字段确认）；Anthropic 协议入口把 `claude-*` 模型名**静默换成** `doubao-seed-2-1-turbo`（抵扣系数 2.5）——Claude Code 只配了 Base URL 和 Token、忘了设 `ANTHROPIC_MODEL` 时不会报错，只是悄悄烧额度。
- 另外五处：文档说"向量化模型不支持 OpenAI API"，实测 Plan 入口 `POST /embeddings` 可用（只是 `input` 只收字符串），而 `/embeddings/multimodal` 的响应是 `data.embedding` **单个对象**不是数组；向量默认维度三处文档写法不一，实测都是 2048；套餐表给 Medium 勾了生视频、正文却说不支持，实测 404 是正文对；`doubao-seedream-5.0-lite` 的 `size` 不认旧写法 `1K`；官方 `volcengine-python-sdk` 的 `ARKApi` 根本没有 `get_afp_usage` 这类方法，套餐与用量查询必须走 `UniversalApi`。
- 触发描述优化跑了 3 轮，结论是**保留原描述**——两个改写版在留出集上都更差。三轮精确率都是 100%、召回率只有 6-17%，即模型经常自己直接作答而不去查 skill；这是 skill 触发机制的已知特性，不是描述写得差，但也说明这份 skill 的实际收益取决于用户明确点名"火山方舟 / Agent Plan"。
- 完整的分场景判词、逐条断言评分与真实请求 / 响应留档，见 [`comparison-report.md`](skills/volcengine-ark/data/comparison-report.md)、[`verification-findings.md`](skills/volcengine-ark/data/verification-findings.md) 与 [`verification-log.jsonl`](skills/volcengine-ark/data/verification-log.jsonl)；探测脚本 [`probe.py`](skills/volcengine-ark/data/probe.py)（Key 只走环境变量），交付前的自检脚本 [`verify_skill.py`](skills/volcengine-ark/data/verify_skill.py)。

## 用法

把某个 skill 目录整份复制到你的 Claude Skills 目录（或用 `skill-creator` 的 `package_skill.py` 打包成 `.skill` 文件安装），Agent 会在检测到相关任务时自动读取。
