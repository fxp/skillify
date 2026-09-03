# process-log.md — Kimi API skill 生成过程记录

日期：2026-09-03。执行的技能：`create-doc-skill-workspace/skill-snapshot/SKILL.md`（generate-skill-from-api-docs）。约束：无 API Key、不做任何真实 Moonshot 调用、≤60 次页面抓取、≤25 分钟。

## 1. 探测过的 URL（按时间顺序，HTTP 状态）

全部用 `curl -sS -L -A "Mozilla/5.0"` 抓取，状态码为跟随重定向后的最终状态。前 9 条是手动勘探，第 10–56 条是一次 `xargs -P 8` 并发批量拉取（下表按 URL 字典序，因为并发完成顺序无意义），第 57 条是事后补抓。

| # | URL | HTTP |
|---|---|---|
| 1 | https://platform.moonshot.cn/llms.txt | 404 |
| 2 | https://platform.moonshot.cn/docs/llms.txt | 200 |
| 3 | https://platform.moonshot.cn/openapi.json | 404 |
| 4 | https://platform.moonshot.cn/docs/openapi.json | 200 |
| 5 | https://platform.moonshot.cn/docs | 200 |
| 6 | https://platform.moonshot.cn/sitemap.xml | 200 |
| 7 | https://platform.moonshot.cn/robots.txt | 200 |
| 8 | https://platform.moonshot.cn/docs/sitemap.xml | 200 |
| 9 | https://platform.kimi.com/docs/llms.txt | 200 |
| 10 | https://platform.moonshot.cn/docs/api/balance.md | 200 |
| 11 | https://platform.moonshot.cn/docs/api/batch-cancel.md | 200 |
| 12 | https://platform.moonshot.cn/docs/api/batch-create.md | 200 |
| 13 | https://platform.moonshot.cn/docs/api/batch-list.md | 200 |
| 14 | https://platform.moonshot.cn/docs/api/batch-retrieve.md | 200 |
| 15 | https://platform.moonshot.cn/docs/api/chat.md | 200 |
| 16 | https://platform.moonshot.cn/docs/api/errors.md | 200 |
| 17 | https://platform.moonshot.cn/docs/api/estimate.md | 200 |
| 18 | https://platform.moonshot.cn/docs/api/files-content.md | 200 |
| 19 | https://platform.moonshot.cn/docs/api/files-delete.md | 200 |
| 20 | https://platform.moonshot.cn/docs/api/files-list.md | 200 |
| 21 | https://platform.moonshot.cn/docs/api/files-retrieve.md | 200 |
| 22 | https://platform.moonshot.cn/docs/api/files-upload.md | 200 |
| 23 | https://platform.moonshot.cn/docs/api/files.md | 200 |
| 24 | https://platform.moonshot.cn/docs/api/list-models.md | 200 |
| 25 | https://platform.moonshot.cn/docs/api/messages.md | 200 |
| 26 | https://platform.moonshot.cn/docs/api/models-overview.md | 200 |
| 27 | https://platform.moonshot.cn/docs/api/overview.md | 200 |
| 28 | https://platform.moonshot.cn/docs/api/responses.md | 200 |
| 29 | https://platform.moonshot.cn/docs/api/signatures-verify.md | 200 |
| 30 | https://platform.moonshot.cn/docs/get-api-key.md | 200 |
| 31 | https://platform.moonshot.cn/docs/guide/engage-in-multi-turn-conversations-using-kimi-api.md | 200 |
| 32 | https://platform.moonshot.cn/docs/guide/kimi-k2-6-quickstart.md | 200 |
| 33 | https://platform.moonshot.cn/docs/guide/kimi-k2-7-code-quickstart.md | 200 |
| 34 | https://platform.moonshot.cn/docs/guide/kimi-k3-quickstart.md | 200 |
| 35 | https://platform.moonshot.cn/docs/guide/response_format.md | 200 |
| 36 | https://platform.moonshot.cn/docs/guide/tool-call-repeat.md | 200 |
| 37 | https://platform.moonshot.cn/docs/guide/troubleshooting.md | 200 |
| 38 | https://platform.moonshot.cn/docs/guide/use-batch-api.md | 200 |
| 39 | https://platform.moonshot.cn/docs/guide/use-context-caching-feature-of-kimi-api.md | 200 |
| 40 | https://platform.moonshot.cn/docs/guide/use-dynamic-tool-loading.md | 200 |
| 41 | https://platform.moonshot.cn/docs/guide/use-json-mode-feature-of-kimi-api.md | 200 |
| 42 | https://platform.moonshot.cn/docs/guide/use-kimi-api-for-file-based-qa.md | 200 |
| 43 | https://platform.moonshot.cn/docs/guide/use-kimi-api-to-complete-tool-calls.md | 200 |
| 44 | https://platform.moonshot.cn/docs/guide/use-kimi-vision-model.md | 200 |
| 45 | https://platform.moonshot.cn/docs/guide/use-official-tools.md | 200 |
| 46 | https://platform.moonshot.cn/docs/guide/use-partial-mode-feature-of-kimi-api.md | 200 |
| 47 | https://platform.moonshot.cn/docs/guide/use-reasoning-effort.md | 200 |
| 48 | https://platform.moonshot.cn/docs/guide/use-thinking-models.md | 200 |
| 49 | https://platform.moonshot.cn/docs/guide/use-tool-choice.md | 200 |
| 50 | https://platform.moonshot.cn/docs/guide/use-web-search.md | 200 |
| 51 | https://platform.moonshot.cn/docs/guide/utilize-the-streaming-output-feature-of-kimi-api.md | 200 |
| 52 | https://platform.moonshot.cn/docs/hosted-agents/quickstart.md | 200 |
| 53 | https://platform.moonshot.cn/docs/introduction.md | 200 |
| 54 | https://platform.moonshot.cn/docs/models.md | 200 |
| 55 | https://platform.moonshot.cn/docs/pricing/chat.md | 200 |
| 56 | https://platform.moonshot.cn/docs/pricing/limits.md | 200 |
| 57 | https://platform.moonshot.cn/docs/guide/kimi-k3-tool-calling-best-practice.md | 200 |

合计 57 次抓取（预算 60）。零次 API 调用（`api.moonshot.cn` 从未被访问）。

勘探结论：
- `https://platform.moonshot.cn/llms.txt`（根路径）→ 404（返回的是 Next.js 的 HTML 404 页）。**技能第一步只写了"根路径试 /llms.txt"**，我顺手多试了 `/docs/llms.txt` 才拿到（200，39.8KB，199 个页面链接，末尾有 "OpenAPI Specs" 一节）。同理 `/openapi.json` 404、`/docs/openapi.json` 200（118KB，OpenAPI 3.1，16 个 endpoint）。
- `platform.moonshot.cn` 与 `platform.kimi.com` 是同一站点的双域名（robots.txt Host 指向 kimi.com，llms.txt 内链全是 kimi.com，但用 moonshot.cn 域名加 `.md` 后缀同样 200）。
- `/docs/sitemap.xml` 有 199 个 URL，其中约 120 个是"托管智能体"（hosted-agents / api-reference/会话、记忆库、触发器…）的独立产品线，超出"Kimi 模型 API"范围，本次只抓了 hosted-agents/quickstart 一页作为范围说明，未整理进技能。

## 2. 用到的工具 / 脚本

| 工具 | 用途 |
|---|---|
| `curl`（Bash） | 全部页面探测与抓取；每次调用记录 `%{http_code}` 到 `probes.log` |
| `xargs -P 8` + `fetch.sh` | 47 个 `.md` 页面并发批量下载到 scratch `pages/`（第一次用 `export -f` 在 zsh 下失败，改成独立脚本文件后成功） |
| `expand_openapi.py`（自写，Python 标准库 json） | 解析 `/docs/openapi.json`，对每个 endpoint 递归展开 `$ref`，按 tag 生成 8 份可读 schema 摘要（`schema/*.txt`，共 1118 行） |
| `grep` / `sed` / `awk` | 从 15.7k 行 Markdown 里定位 base URL、temperature、限速表等关键段落 |
| `/anthropic-skills:skill-creator`（Skill 工具加载） | 取得 skill 目录规范（SKILL.md + references/ + evals/evals.json、<500 行）与 evals.json 格式 |
| `skill-creator/scripts/package_skill.py` | 最终校验（"Skill is valid"）并打包到 scratch `pkg/kimi-api.skill`（未放进 outputs，非交付要求） |
| Agent 子代理 ×2（general-purpose） | 并行撰写 `references/chat-completions.md` 与 `references/tools.md`（各给统一写作规范 `WRITING-SPEC.md` + 源文件路径） |
| `python3 -c json.load` / `grep -rnE 'sk-…'` | evals.json 合法性、全目录 Key 泄漏检查（无） |

未使用：浏览器工具（纯 Markdown 源码足够）、`uv`（没有需要安装的包）、`run_eval.py` / `run_loop.py` / `improve_description.py`（原因见下）。

## 3. 技能各步骤：执行 / 跳过 及原因

### 第一步：抓取与勘探 — **执行**
- 1.1 找 llms.txt：执行。根路径 404，`/docs/llms.txt` 命中。
- 1.2 找 OpenAPI：执行。`/docs/openapi.json` 命中，用 Python 展开 `$ref` 落地 schema 摘要（技能要求的做法）。`securitySchemes` = bearerAuth，servers = `https://api.moonshot.cn`。
- 1.3 批量下载 Markdown 源页：执行。llms.txt 链接加 `.md` 后缀直接返回纯 Markdown（含 MDX 组件标签），`xargs -P 8` 并发。
- 1.4 摸清鉴权：执行。`Authorization: Bearer $MOONSHOT_API_KEY`，Anthropic 入口 base_url 不同。

### 第二步：结构化撰写 — **执行**
- 先加载 skill-creator 再建目录（按技能要求）。
- 按开发者意图分组成 7 个 reference（models / chat-completions / tools / vision-and-files / batch / responses-and-messages / errors-and-limits），不照抄文档目录树。例如"PDF 问答"在官方分散在 files-upload、files-content、file-based-qa、vision 四页，合并到 vision-and-files.md 一张选型表里。
- 并行委派：计划派 4 个子代理，**只成功启动 2 个**（另外 2 个触发 "Concurrent subagent limit reached (20)" 且提示不要重试）。vision-and-files、batch、responses-and-messages、errors-and-limits、models 五个文件改由我自己撰写。
- SKILL.md 只做路由 + 跨领域规则 + "10 个最容易写错的点" + 检查清单，81 行。
- 每个 reference 强制带"尚未验证"状态行和末尾"待验证疑点"节（这是我在写作规范里加的要求，技能本身没写，但对第三步缺席时的可追溯性很关键）。

### 第三步：真实 API 验证与修正 — **跳过（无 Key，且任务明确禁止任何真实调用）**
- 替代产出：`verification-plan.md`（109 行，8 个测试组、约 55 条测试项，每条注明来源疑点与回写位置），以及各 reference 末尾合计约 90 条"待验证疑点"。
- 纯读文档就已经发现的**文档自相矛盾**（技能第三步警告的那类问题，在没有 Key 的情况下只能标记不能裁决）：
  1. `docs/api/files-upload` 示例对 `kimi-k3` 传 `temperature=0.6`，`docs/api/models-overview` 说 K3 温度固定 1.0、传其他值报错。
  2. 文件 `purpose` 合法值：错误码页列 6 个（含 `batch_output`、`lambda`），OpenAPI 枚举只有 4 个。
  3. OpenAPI 的 `tool_choice` 枚举对所有模型一样，models-overview 说 `required` 在 K2.x 报错。
  4. OpenAPI `tools[].type` 只有 `function`，联网搜索页用 `builtin_function`；K3 quickstart 又说联网搜索"近期不建议使用"。
  5. 流式 `usage` 的位置三处文档写法不一致（`choices[].usage` vs 顶层 vs 末尾空 choices 帧）。
  6. `max_tokens` 在 OpenAPI 标 DEPRECATED，但几乎所有指南示例仍在用。
  7. OpenAPI 的请求 `Message` schema 没有 `reasoning_content` / `tool_calls` / `tool_call_id` 字段，且 `content` 标必填"不得为空"，但指南要求回传 `reasoning_content`、Partial Mode 用空 content。

### 第四步：真实对照实验 — **部分执行**
- 已做：`evals/evals.json` 8 个场景、36 条断言，全部选"OpenAI 直觉会写错"的点（迁移时删 temperature、图片 URL 不支持、PDF 不能传 file_id、工具循环要回传 reasoning_content、Batch 不支持 K3、K2.6 才能关思考、Anthropic 入口去掉 budget_tokens 等）。
- 跳过：`run_eval.py` / `run_loop.py` 跑 with-skill vs baseline、grader 打分、`aggregate_benchmark.py`。原因：技能第四步第 3 点要求"打分依据真实调用结果"，没有 Key 时 grader 只能靠文档，而文档本身已发现 7 处自相矛盾，此时跑对照只会把文档错误固化成"正确答案"；另外时间盒 25 分钟也不允许再跑 16 个子代理。

### 第五步：打包发布 — **部分执行**
- 已做：`package_skill.py` 校验通过。
- 跳过：`improve_description.py` 描述优化（需要 `claude -p` 跑 20 条触发查询 × 3 次 × 5 轮，远超时间盒；且描述应在验证后定稿）。当前 description 已手写覆盖产品名/域名/模型名/SDK 名/中文别称。

## 4. 产出清单

```
outputs/
├── kimi-api/
│   ├── SKILL.md                              81 行
│   ├── references/
│   │   ├── models.md                         69 行
│   │   ├── chat-completions.md              348 行（子代理）
│   │   ├── tools.md                         320 行（子代理）
│   │   ├── vision-and-files.md              205 行
│   │   ├── batch.md                         195 行
│   │   ├── responses-and-messages.md        222 行
│   │   └── errors-and-limits.md             145 行
│   └── evals/evals.json                     114 行（8 场景 / 36 断言）
├── verification-plan.md                     109 行
└── process-log.md                           本文件
```

## 5. 对技能本身（skill-snapshot/SKILL.md）的反馈

1. **llms.txt 的探测路径写窄了**：只说根路径 `/llms.txt`。本站根路径 404、`/docs/llms.txt` 才有；OpenAPI 同理在 `/docs/openapi.json`。建议改成"依次试 `/llms.txt`、`/<docs-prefix>/llms.txt`、`/llms-full.txt`"，并提示先看 `robots.txt` / `sitemap.xml` 找 docs 前缀。
2. **没有"没有 Key 时怎么办"的分支**：第三、四步被写成绝对不可跳过，但现实中经常先没 Key。建议明确一个降级路径：每个 reference 强制"未验证"状态行 + "待验证疑点"节 + 独立 verification-plan，evals 先写断言不跑对照。这次是我自己补的约定。
3. **并行子代理数量假设不成立**：技能建议一次派 4–6 个子代理，本次环境并发上限被占满只成功 2 个。建议加一句"启动失败时自己顺序写，不要重试"。
4. **`export -f` 式并发抓取在 zsh 下不工作**：技能里"用 `xargs -P 8` 并发"是对的，但示例应写成独立脚本文件而不是 shell 函数。
5. **对 MDX 源码没有提示**：`.md` 页面里大量 `<DocTable rows={[...]}/>`、`<Accordion>`、`<CodeGroup>` 等 JSX，关键表格（限速等级、参数固定值）藏在 JSX 数组里，纯文本 grep 需要额外处理。建议提一句。
6. **范围裁剪没有指导**：本站 199 页里 60% 是另一条产品线（托管智能体）。技能应提示"先用 sitemap/llms.txt 分产品线，和用户确认范围"——本次我按用户原话"Kimi 开放平台文档"自行裁掉了 hosted-agents，只在 SKILL.md 里声明未覆盖。
7. **时间盒与技能的期望体量冲突**：完整走完五步（含 run_loop 描述优化）远超 25 分钟；技能没有给"最小可交付版本"的定义。
8. 技能引用了 `skills/bigmodel-cn` 作为范例（相对路径 `../bigmodel-cn`），本次任务禁止读其他技能目录，所以无法参考——这条依赖应改为把范例格式内联进技能本身。
