# process-log.md — kimi-api skill 生成过程记录

任务：把 https://platform.moonshot.cn/docs 整理成 skill（无 API Key；Python 示例）。执行日期 2026-09-03。遵循 `/Users/chopinfeng/Workspace/Skillify/create-doc-skill/SKILL.md` 及其 references/explore.md、write.md、verify.md、evaluate.md。

**关于真实 API 调用的声明：全程零次请求 `api.moonshot.cn`。** 下表 52 次请求全部指向文档站 `platform.moonshot.cn` / `platform.kimi.com`。skill 与验证计划中引用的所有报错原文（`tool_choice 'specified' is incompatible with thinking enabled`、`tokenization failed`、`cannot be used with content`、`tool_call_id not found`、`Invalid purpose: ...` 等）**均抄自文档页面，不是实测观察**，各处已标注"文档引用 / 未验证"。

## 1. 探测与抓取的全部 URL（按时间顺序，含 HTTP 状态）

| # | URL | HTTP | 用途 / 结果 |
|---|---|---|---|
| 1 | https://platform.moonshot.cn/llms.txt | 404 | llms.txt 探测（text/html; charset=utf-8，36258B） |
| 2 | https://platform.moonshot.cn/llms-full.txt | 404 | 文档入口 / SPA 壳（HTML）（text/html; charset=utf-8，36263B） |
| 3 | https://platform.moonshot.cn/docs/llms.txt | 200 | **真实 llms.txt，199 条链接，指向 platform.kimi.com/docs/*.md**（text/plain; charset=utf-8，39864B） |
| 4 | https://platform.moonshot.cn/sitemap.xml | 200 | sitemap（仅 2 条 URL，指向 platform.kimi.com）（application/xml，1044B） |
| 5 | https://platform.moonshot.cn/robots.txt | 200 | robots.txt（给出 docs/sitemap.xml 与 canonical host）（text/plain; charset=UTF-8，234B） |
| 6 | https://platform.moonshot.cn/openapi.json | 404 | OpenAPI 规范探测（text/html; charset=utf-8，36262B） |
| 7 | https://platform.moonshot.cn/docs/openapi.json | 200 | **真实 OpenAPI 3.1.0，16 endpoints**（application/json，118237B） |
| 8 | https://platform.moonshot.cn/api-reference/openapi.json | 404 | OpenAPI 规范探测（text/html; charset=utf-8，36280B） |
| 9 | https://platform.moonshot.cn/swagger.json | 404 | OpenAPI 规范探测（text/html; charset=utf-8，36262B） |
| 10 | https://platform.moonshot.cn/docs | 200 | 文档入口 / SPA 壳（HTML）（text/html; charset=utf-8，409709B） |
| 11 | https://platform.moonshot.cn/docs/guide/start-using-kimi-api | 200 | 文档入口 / SPA 壳（HTML）（text/html; charset=utf-8，409709B） |
| 12 | https://platform.kimi.com/docs/openapi-hosted-agents.yaml | 200 | 托管智能体 OpenAPI（64 paths，仅记录，未展开）（text/yaml，391285B） |
| 13 | https://platform.kimi.com/docs/api/batch-create.md | 200 | fetch_docs.sh → `pages/docs_api_batch-create.md`（创建批处理任务） |
| 14 | https://platform.kimi.com/docs/api/chat.md | 200 | fetch_docs.sh → `pages/docs_api_chat.md`（Chat Completions API） |
| 15 | https://platform.kimi.com/docs/api/errors.md | 200 | fetch_docs.sh → `pages/docs_api_errors.md`（常见错误码说明） |
| 16 | https://platform.kimi.com/docs/api/estimate.md | 200 | fetch_docs.sh → `pages/docs_api_estimate.md`（计算 Token） |
| 17 | https://platform.kimi.com/docs/api/files-upload.md | 200 | fetch_docs.sh → `pages/docs_api_files-upload.md`（上传文件） |
| 18 | https://platform.kimi.com/docs/api/messages.md | 200 | fetch_docs.sh → `pages/docs_api_messages.md`（Messages API） |
| 19 | https://platform.kimi.com/docs/api/models-overview.md | 200 | fetch_docs.sh → `pages/docs_api_models-overview.md`（模型参数参考） |
| 20 | https://platform.kimi.com/docs/api/overview.md | 200 | fetch_docs.sh → `pages/docs_api_overview.md`（API 概述） |
| 21 | https://platform.kimi.com/docs/api/responses.md | 200 | fetch_docs.sh → `pages/docs_api_responses.md`（Responses API） |
| 22 | https://platform.kimi.com/docs/api/signatures-verify.md | 200 | fetch_docs.sh → `pages/docs_api_signatures-verify.md`（校验请求签名） |
| 23 | https://platform.kimi.com/docs/changelog/changelog/changelog.md | 200 | fetch_docs.sh → `pages/docs_changelog_changelog_changelog.md`（平台新功能发布记录） |
| 24 | https://platform.kimi.com/docs/get-api-key.md | 200 | fetch_docs.sh → `pages/docs_get-api-key.md`（快速开始） |
| 25 | https://platform.kimi.com/docs/guide/auto-reconnect.md | 200 | fetch_docs.sh → `pages/docs_guide_auto-reconnect.md`（自动断线重连） |
| 26 | https://platform.kimi.com/docs/guide/engage-in-multi-turn-conversations-using-kimi-api.md | 200 | fetch_docs.sh → `pages/docs_guide_engage-in-multi-turn-conversations-using-kimi-api.md`（配置多轮对话参数） |
| 27 | https://platform.kimi.com/docs/guide/kimi-k2-6-quickstart.md | 200 | fetch_docs.sh → `pages/docs_guide_kimi-k2-6-quickstart.md`（Kimi K2.6） |
| 28 | https://platform.kimi.com/docs/guide/kimi-k2-7-code-quickstart.md | 200 | fetch_docs.sh → `pages/docs_guide_kimi-k2-7-code-quickstart.md`（Kimi K2.7 Code） |
| 29 | https://platform.kimi.com/docs/guide/kimi-k3-quickstart.md | 200 | fetch_docs.sh → `pages/docs_guide_kimi-k3-quickstart.md`（Kimi K3） |
| 30 | https://platform.kimi.com/docs/guide/kimi-k3-tool-calling-best-practice.md | 200 | fetch_docs.sh → `pages/docs_guide_kimi-k3-tool-calling-best-practice.md`（Kimi K3 API 工具调用最佳实践） |
| 31 | https://platform.kimi.com/docs/guide/response_format.md | 200 | fetch_docs.sh → `pages/docs_guide_response_format.md`（使用 response_format 控制模型输出格式） |
| 32 | https://platform.kimi.com/docs/guide/tool-call-repeat.md | 200 | fetch_docs.sh → `pages/docs_guide_tool-call-repeat.md`（如何解决重复调用问题） |
| 33 | https://platform.kimi.com/docs/guide/troubleshooting.md | 200 | fetch_docs.sh → `pages/docs_guide_troubleshooting.md`（问题排查） |
| 34 | https://platform.kimi.com/docs/guide/use-batch-api.md | 200 | fetch_docs.sh → `pages/docs_guide_use-batch-api.md`（使用 Batch API 批量处理任务） |
| 35 | https://platform.kimi.com/docs/guide/use-context-caching-feature-of-kimi-api.md | 200 | fetch_docs.sh → `pages/docs_guide_use-context-caching-feature-of-kimi-api.md`（使用 Kimi API 的 Context Caching 功能） |
| 36 | https://platform.kimi.com/docs/guide/use-dynamic-tool-loading.md | 200 | fetch_docs.sh → `pages/docs_guide_use-dynamic-tool-loading.md`（动态加载工具） |
| 37 | https://platform.kimi.com/docs/guide/use-json-mode-feature-of-kimi-api.md | 200 | fetch_docs.sh → `pages/docs_guide_use-json-mode-feature-of-kimi-api.md`（使用 Kimi API 的 JSON Mode） |
| 38 | https://platform.kimi.com/docs/guide/use-kimi-api-for-file-based-qa.md | 200 | fetch_docs.sh → `pages/docs_guide_use-kimi-api-for-file-based-qa.md`（使用 Kimi API 进行文件问答） |
| 39 | https://platform.kimi.com/docs/guide/use-kimi-api-to-complete-tool-calls.md | 200 | fetch_docs.sh → `pages/docs_guide_use-kimi-api-to-complete-tool-calls.md`（使用 Kimi API 完成工具调用（tool_calls）） |
| 40 | https://platform.kimi.com/docs/guide/use-kimi-vision-model.md | 200 | fetch_docs.sh → `pages/docs_guide_use-kimi-vision-model.md`（配置 Kimi 视觉模型） |
| 41 | https://platform.kimi.com/docs/guide/use-official-tools.md | 200 | fetch_docs.sh → `pages/docs_guide_use-official-tools.md`（如何在 Kimi API 中使用官方工具） |
| 42 | https://platform.kimi.com/docs/guide/use-partial-mode-feature-of-kimi-api.md | 200 | fetch_docs.sh → `pages/docs_guide_use-partial-mode-feature-of-kimi-api.md`（使用 Kimi API 的 Partial Mode） |
| 43 | https://platform.kimi.com/docs/guide/use-reasoning-effort.md | 200 | fetch_docs.sh → `pages/docs_guide_use-reasoning-effort.md`（推理强度） |
| 44 | https://platform.kimi.com/docs/guide/use-thinking-models.md | 200 | fetch_docs.sh → `pages/docs_guide_use-thinking-models.md`（思考模型） |
| 45 | https://platform.kimi.com/docs/guide/use-tool-choice.md | 200 | fetch_docs.sh → `pages/docs_guide_use-tool-choice.md`（工具调用约束） |
| 46 | https://platform.kimi.com/docs/guide/use-web-search.md | 200 | fetch_docs.sh → `pages/docs_guide_use-web-search.md`（使用 Kimi API 的联网搜索功能） |
| 47 | https://platform.kimi.com/docs/guide/utilize-the-streaming-output-feature-of-kimi-api.md | 200 | fetch_docs.sh → `pages/docs_guide_utilize-the-streaming-output-feature-of-kimi-api.md`（使用 Kimi API 的流式输出功能） |
| 48 | https://platform.kimi.com/docs/hosted-agents/quickstart.md | 200 | fetch_docs.sh → `pages/docs_hosted-agents_quickstart.md`（快速开始） |
| 49 | https://platform.kimi.com/docs/introduction.md | 200 | fetch_docs.sh → `pages/docs_introduction.md`（主要概念） |
| 50 | https://platform.kimi.com/docs/models.md | 200 | fetch_docs.sh → `pages/docs_models.md`（模型列表） |
| 51 | https://platform.kimi.com/docs/pricing/chat.md | 200 | fetch_docs.sh → `pages/docs_pricing_chat.md`（模型推理价格说明） |
| 52 | https://platform.kimi.com/docs/pricing/limits.md | 200 | fetch_docs.sh → `pages/docs_pricing_limits.md`（充值与限速） |

合计 52 次 HTTP 请求（上限约 60）。

## 2. 使用的工具 / 脚本（按使用顺序）

| 工具 | 用途 |
|---|---|
| `Read` / `cat` | 读 create-doc-skill 的 SKILL.md、references/explore.md、write.md、verify.md、evaluate.md，以及 scripts/ 头部 |
| 自写 `probe.sh`（`curl -sSL -A Mozilla -w '%{http_code}\t%{size_download}\t%{content_type}'`） | 探测 llms.txt / OpenAPI / sitemap / robots 等 12 个候选 URL，全部记入 `probes.tsv` |
| `python3` 单行脚本 | 校验 `/docs/openapi.json` 是否真是 OpenAPI（`openapi: 3.1.0`，14 paths / 16 operations，`securitySchemes.bearerAuth`） |
| `create-doc-skill/scripts/openapi_summary.py`（`python3.12`） | 把规范展开成 8 个按 tag 的摘要文件（Batch / Billing / Chat / Files / Messages / Models / Responses / Utilities，共 1517 行） |
| `grep` 筛出 40 条链接 → `llms-subset.txt` | 从 199 条链接中按主题挑核心 API 页（跳过 100+ 页托管智能体 API reference、协议/隐私、研究博客） |
| `create-doc-skill/scripts/fetch_docs.sh llms-subset.txt docs 8` | 并发拉取 40 个 `.md` 源页，全部 200，产出 `docs/index.tsv`（标题 / URL / 本地文件 / 状态） |
| `grep -nE` 定向检索源页 | 取路由层需要的精确写法（`$web_search` 的 `builtin_function`、Batch 模型白名单、`partial` 位置、`stream_options.include_usage`、`max_completion_tokens` 默认值等） |
| `Skill: anthropic-skills:skill-creator` | 加载 frontmatter 规范与 `references/schemas.md`（evals.json 字段名） |
| `Agent` × 6（general-purpose，并行） | 各写一个 reference 文件；输入只给 `auth.md` + 对应的 openapi-summary + 源页，禁止用记忆，要求标 `⚠` |
| `Bash` heredoc | 写 `auth.md`、SKILL.md、evals.json、verification-plan.md、本日志 |
| `python3` | 校验 evals.json 可解析、description 无尖括号且 ≤1024 字符；最终用 `package_skill.py`/`quick_validate.py` 校验 frontmatter |

未使用：浏览器（Chrome / 内置 Browser）、ego-browser、WebFetch、任何 Moonshot API 调用（无 key，按约束不调用）。

## 3. 按 create-doc-skill 的步骤：做了什么、跳过什么、为什么

### 动手前"先和用户确认三件事"
- 有无 key：任务已说明无 key → 不问，按 verify.md 的降级方案执行。
- 语言：任务指定 Python → 示例 curl + Python（`openai` SDK 优先，裸 HTTP 用 `requests`）。
- 输出位置：任务指定 → skill 放 `outputs/kimi-api/`，评测/验证产物放兄弟目录 `outputs/kimi-api-workspace/`（沿用 skill 的 `<skill>-workspace/` 约定）。
- 顺带检查官方 MCP / llms-full.txt：`llms-full.txt` 404；未见官方 MCP server 提及（Playground 里有 ModelScope MCP 配置页，与 API 接入无关）。

### 第 1 步 抓取与勘探 — 已执行（有偏离）
- 按 explore.md 先试 `https://platform.moonshot.cn/llms.txt` → **404**。skill 只给了根路径这一种写法；我额外试了 `/docs/llms.txt` → 200，是真实索引（199 条）。**这一点 explore.md 没有提示**（Mintlify 类站点 llms.txt 常挂在文档子路径下），见"问题反馈"。
- 同理 `/openapi.json` 404、`/docs/openapi.json` 200。explore.md 的常见路径清单里没有 `/docs/openapi.json`。
- 因为 `/docs/llms.txt` 和 `/docs/openapi.json` 都拿到了，**没有进入第 4 节的 fallback**（sitemap / DOM 渲染 / 手工清单）。sitemap.xml 顺手看了：只有 2 条 URL，对本任务无用；robots.txt 指出另有 `/docs/sitemap.xml`（未抓，预算原因）。
- 域名发现：llms.txt、sitemap、robots 全部指向 **platform.kimi.com** 为 canonical，`platform.moonshot.cn` 只是仍可访问的旧域名；API 域名仍是 `api.moonshot.cn`。写进 SKILL.md 与 auth.md。
- `openapi_summary.py` 正常工作（需 python3.12，与 skill 说明一致）。
- `fetch_docs.sh` 以本地文件为输入正常工作；因预算 60 次只拉了 40/199 页（核心 API + guide），托管智能体（Hosted Agents，独立产品，64 个 endpoint）只抓了其 OpenAPI YAML 和 quickstart，在 SKILL.md 里做"不在范围内 + 去哪找规范"的路由说明。
- 产出：`auth.md`（鉴权精确格式、三个 base_url、模型名单）。

### 第 2 步 结构化撰写 — 已执行
- 先加载 `anthropic-skills:skill-creator`，读了 `references/schemas.md`。
- 按 write.md 的骨架写 SKILL.md（验证状态 → 先确认 4 件事 → 30 秒请求 → 导航表 → 通用规则 → 目录）。
- 按开发者意图分 6 个 reference（不照抄文档目录：文档把"文件问答"拆在 files-upload / file-based-qa / vision 三处，skill 合并进 files-and-batch.md + chat-completions.md 的视觉小节并互相引用）。
- 6 个子 Agent 并行，prompt 用 write.md 的模板（输入清单、endpoint 统一格式、禁止编造、`⚠` 标记、行数区间、回复末尾列出 ⚠ 清单）。
- **偏离**：write.md 建议"models.md 这类需要全局视野的文件自己写"，我因 25 分钟时限也委派了（`models-and-thinking.md`），收回后由我通读校对。

### 第 3 步 真实 API 验证 — 按降级方案执行，未做真实调用
- 无 key，且任务明令禁止调用。按 verify.md "没有 key 时"：
  - SKILL.md 顶部加"验证状态"一节，声明全部为文档转录；每个 reference 首行同样声明。
  - 写 `kimi-api-workspace/verification-plan.md`：P0（鉴权 / 模型名 / 余额）→ P1（SKILL.md 每条通用规则各一次最小调用）→ P2（文件 / Batch，含清理）→ P3（Responses / Messages / 工具接口）→ P4（各 reference 的 ⚠ 清单汇总）。每条含 endpoint、测法、判定标准、成本。
  - 子 Agent 报上来的 `⚠ 文档自相矛盾`（504 超时 900 秒 vs 2 小时；限速"用户级"vs"组织级"等）已作为待验证项列入，而不是替文档裁决。
- 未做：verification-log.md（没有可记录的调用）、key 泄漏 grep（没有 key；但仍 grep 了 `sk-` 确认示例里没有形似 key 的字符串）。

### 第 4 步 对照实验 — 只做了场景设计，未跑对照
- 写了 `evals/evals.json`：7 个场景、25 条 expectations，全部是"凭 OpenAI 直觉会写错"型（固定 temperature、thinking 走 extra_body、tool_choice required 仅 K3、file-extract 流程、Batch 不支持 K3、stream_options 取 usage、$web_search、partial 位置），prompt 写成普通需求不暗示坑。
- 未 spawn with/without 对照子 Agent、未打分、未写 comparison-report.md：evaluate.md 要求"打分依据真实调用结果"，无 key 时只能做"文档保真度对照"，且本次任务范围是"草稿 + 验证计划 + 评测场景"。评测场景已按 schemas.md 格式就绪，拿到 key 后先跑 verification-plan 再跑对照，这样打分才有真实报错可依据。

### 第 5 步 打包发布 — 部分执行
- 做了：`description` 按 skill-creator 的"pushy"风格手写（含产品名、两个域名、API 域名、env 变量名、模型名、常见别称"月之暗面"），无尖括号、≤1024 字符；用 `package_skill.py` 校验 frontmatter（结果见第 4 节）。
- 未做：`run_loop.py` 描述优化（需要 `claude -p` 跑 20 条触发查询 × 3 次 × 5 轮，远超 25 分钟时限，且 skill 自己也说"等 skill 定稿后再做"）；未安装到 `~/.claude/skills/`（草稿阶段，且任务只要求放到 outputs）。

## 4. 交付物与校验结果

| 文件 | 行数 |
|---|---|
| `kimi-api-workspace/verification-plan.md` | 202 |
| `kimi-api/SKILL.md` | 96 |
| `kimi-api/evals/evals.json` | 86 |
| `kimi-api/references/chat-completions.md` | 650 |
| `kimi-api/references/errors-and-limits.md` | 303 |
| `kimi-api/references/files-and-batch.md` | 599 |
| `kimi-api/references/models-and-thinking.md` | 541 |
| `kimi-api/references/responses-messages-and-utilities.md` | 598 |
| `kimi-api/references/tool-calling.md` | 623 |
| `process-log.md` | 本文 |

校验（均在本次会话执行）：
- `quick_validate.py`（skill-creator，`uv run --python 3.12 --with pyyaml`）：`Skill is valid!`；description 563 字符、无尖括号；name `kimi-api` kebab-case。
- `package_skill.py`（需 `python -m scripts.package_skill`，直接跑脚本会 `ModuleNotFoundError: scripts`）：打包成功，产物 `kimi-api.skill` 放在 scratch，未放进 outputs；打包内容 = SKILL.md + 6 个 references，`evals/` 已排除。
- `evals/evals.json`：可解析，7 个场景 / 25 条 expectations，字段按 skill-creator `references/schemas.md`。
- 泄漏检查：`grep -rnE 'sk-[A-Za-z0-9]{10,}|MOONSHOT_API_KEY=\S{10,}'` outputs → 无匹配。
- 请求日志复核：`probes.tsv` 与 `docs/index.tsv` 中 `api.moonshot.cn` 出现 0 次；全部 52 次请求都是文档站。
- 所有输出文件均为合法 UTF-8（第一版 verification-plan.md 因 macOS `cut -c` 按字节截断产生了非法字节，已用 Python 重建）。
- verification-plan.md 的 P4 附录：从 6 个 reference 自动汇总 127 条 ⚠（models-and-thinking 25、chat-completions 15、tool-calling 20、files-and-batch 30、responses-messages-and-utilities 17、errors-and-limits 20）。

## 5. 对 create-doc-skill 本身的反馈（不清楚 / 不对 / 跑不通的地方）

1. **explore.md 只说试 `https://<docs-domain>/llms.txt`**。本站根路径 404，真正的索引在 `/docs/llms.txt`（OpenAPI 同理在 `/docs/openapi.json`）。建议把 `/docs/llms.txt`、`/<docs-prefix>/llms.txt` 和 `/docs/openapi.json` 加进候选路径清单，并提示先看 `robots.txt`（本站 robots 直接给出了 `/docs/sitemap.xml` 和 canonical host）。
2. **域名迁移没有对应指引**：用户给的是 `platform.moonshot.cn`，所有索引都指向 `platform.kimi.com`。explore.md 应加一句"llms.txt / sitemap 里的链接域名和用户给的不一致时，以索引里的为 canonical，并在 SKILL.md 里两个域名都列出来"。
3. **fetch 预算与 199 条链接冲突时没有筛选指引**。我按"核心 API + guide 优先、独立子产品只抓规范 + 快速开始"取舍；建议在 explore.md 加"多产品文档站按产品切分，一次只做一个产品，其他产品在 SKILL.md 做路由"，并明示 fetch_docs.sh 接受本地截取过的 llms.txt 子集（我是读脚本源码才确定的）。
4. **skill-creator 脚本依赖没写全**：SKILL.md 只说需要 Python ≥ 3.10，实际 `quick_validate.py` / `package_skill.py` 还需要 `pyyaml`，且 `package_skill.py` 必须以 `python -m scripts.package_skill` 方式在 skill-creator 目录下运行，直接 `python scripts/package_skill.py` 会 `ModuleNotFoundError`。建议把 `uv run --with pyyaml python -m scripts.package_skill` 写成标准命令。
5. **write.md 的子 Agent 模板缺一条**：应要求子 Agent 在文件里显式写明"报错原文引自文档，非实测"。本次有子 Agent（及我自己第一版 SKILL.md）把文档里的报错 message 写得像实测结论，被协调方追问后才补标注。verify.md 的降级方案也应把这条列为必做。
6. **write.md 建议 models.md 自己写**，但 25 分钟时限下不现实；实际委派后质量可接受。建议改成"可委派，但 SKILL.md 的'先确认 N 件事'必须由主 Agent 从 auth.md + 模型页亲自核对"（我确实这么做了，并纠正了自己第一版 SKILL.md 里关于指定函数 tool_choice 的错误）。
7. **子 Agent 完成通知不可靠**：6 个并行子 Agent 中有 2 个的完成通知我没有及时收到（被协调方唤醒时才发现文件已在盘上、且行数已变），另有 1 个（tool-calling）在协调方告知"没有子 Agent 在运行"时文件尚不存在，我按指示自己写了 502 行版本；该子 Agent 实际仍在运行，随后以我的版本为基底合并了它的补充（最终 623 行），并在回复里说明了这次合并。evaluate.md 说"timing.json 数据只在通知里有"，这种情况下就拿不到；建议让子 Agent 把行数 / ⚠ 清单同时写到 `<scratch>/reports/<domain>.md`，主 Agent 以文件为准。
8. **evaluate.md 与"无 key 只做草稿"任务的衔接不清**：任务只要"草稿 + 验证计划 + 评测场景"，skill 没有说明这种交付里第 4 步做到哪一步（只写 evals.json？还是也跑文档保真度对照？）。我选择只写 evals.json。建议 verify.md 的降级方案明确"无 key 时第 4 步是否要跑、跑了怎么标注"。
9. **规范之外的 endpoint 没有处理指引**：Formula 官方工具接口（`/v1/formulas/{uri}/tools`、`/fibers`）只在文档页出现、不在 openapi.json 里。skill 应提示"文档页里出现而规范里没有的 endpoint 要单独标出并优先验证"——我在 tool-calling.md 里标了。
10. **多字节文本工具坑**：write.md / evaluate.md 的示例命令若用 `cut -c` 处理中文会产生非法 UTF-8（本次踩到）。建议在 skill 里提醒截断/汇总中文文本用 Python 而不是 `cut`。
