# create-doc-skill · value audit

`create-doc-skill` 是 `generate-skill-from-api-docs` 的重写版（改名 + 拆 references + 加脚本）。本报告对比 **新版（with_skill）** 与 **旧版快照（old_skill）** 在两个"草稿模式"场景上的表现：每个场景各跑一次，执行模型 claude-fable-5-1，没有真实 API key，因此打分依据是产物结构和过程记录，不是真实调用。

| Metric | Value |
|---|---|
| 场景数（1 轮） | 2 |
| 每场景断言数 | 9 |
| 新版通过率 | 18 / 18 |
| 旧版通过率 | 18 / 18 |
| 新版用了自带脚本的运行 | 2 / 2（旧版 0 / 2，旧版没有脚本） |
| 出现文件互相覆盖的运行 | 3 / 4（与版本无关） |
| 评测中修正的 skill 指引条目 | 9 |

结论先说：**按断言看是平局**。旧版对一个能力足够强的执行者已经能产出结构等价的草稿；新版的价值体现在过程而不是终态——脚本复用、更少的抓取次数、密度高得多的 endpoint 级不确定性标记，以及执行者对指引本身的抱怨从"缺失/错误"变成了"可以再细一点"。

---

## Round 1 — 无 key 草稿模式

**Model:** claude-fable-5-1 · 2 个场景 · 每配置 1 次运行

| Scenario | Result | Skill | Baseline (old) |
|---|---|---|---|
| Resend：有 llms.txt，OpenAPI 链接是错的 | tie | 9 / 9 | 9 / 9 |
| Kimi 开放平台：根路径无 llms.txt，测 fallback | tie | 9 / 9 | 9 / 9 |

### Resend：有 llms.txt，OpenAPI 链接是错的 — tie
**Task:** 给 Resend（resend.com/docs）做接入 skill，TypeScript 示例，没有 key，做到草稿 + 验证计划 + 评测场景。
**Why:** 两版都发现 `llms.txt` 的 OpenAPI 段列的是 `package.json`，都去 GitHub 找到了真正的 `resend-openapi`（108 个操作），都产出了路由型 SKILL.md、按意图分组的 references、逐文件的"未验证"声明、按成本排序的验证计划和陷阱型 evals。差异在过程：新版用 `fetch_docs.sh` / `openapi_summary.py`，11 次抓取（旧版 14 次），references 里 132 处 ⚠ 标记（旧版 26 处），多覆盖了 templates / automations / events 一个能力域；代价是 +380s、+2 万 tokens、内容量 2.1 倍。两版都出现了父 Agent 与写作子 Agent 互相覆盖文件的问题。

### Kimi 开放平台：根路径无 llms.txt — tie
**Task:** 把 platform.moonshot.cn/docs 整理成 skill，Python 示例，没有 key。
**Why:** 场景本意是测"没有索引时的 fallback"，结果两版都在探了 sitemap 之后发现索引其实在 `/docs/llms.txt`（并指向 `platform.kimi.com`），fallback 路径没真正用上——这是评测设计失误，同时也暴露了 skill 只写了根路径的问题。两版都正确把 Hosted Agents 这个独立产品裁掉。新版 references 里 102 处 endpoint 级"文档未说明/待验证"标记，旧版把疑点集中在每个文件末尾一节共 13 条；新版把文档里抄来的 `400 tool_choice 'specified' is incompatible with thinking enabled` 起初写得像实测，被追问后补了"文档原文"标注——这条直接变成了新版 write.md / verify.md 的规则。

---

## 评测中修正的 skill 指引条目

旧版执行者报告的缺口（新版重写时已覆盖）：

| 位置 | 发现 |
|---|---|
| 旧 SKILL.md 第 4 步 | 说用 skill-creator 的 `run_eval.py` / `run_loop.py` 跑 with/without 对照。实际那两个脚本只测触发描述；对照要 spawn 子 Agent |
| 旧 SKILL.md 全文 | 没有"无 key"分支，第 3、4 步写成不可跳过；两个执行者都只能自己发明降级方案 |
| 旧 SKILL.md 第 2 步 | 引用 `../bigmodel-cn/SKILL.md` 作范本，独立安装后路径不存在 |
| 旧 SKILL.md 第 1 步 | 没提 `llms-full.txt`；OpenAPI 只在厂商 GitHub 上时没有提示去哪找 |

新版执行者报告并已在本轮后修正的条目：

| 文件 | 发现 |
|---|---|
| `explore.md` | 只试根路径 `/llms.txt`；Kimi 的索引在 `/docs/llms.txt`，且指向另一个域名。已加路径前缀变体和 canonical 域名说明 |
| `explore.md` | 没说 `llms-full.txt` 可替代逐页抓取。已改为优先 |
| `explore.md` | Mintlify 的 `.md` 导出剥掉 `ParamField` / `DocTable`，字段表在 Markdown 里看不到。已加说明 |
| `explore.md` | 多产品文档站没有裁范围的指引。已加"先裁范围"一节和抓取优先级 |
| `write.md` | 委派没有并发保护，4 次里 3 次互相覆盖。已加 `.done` 标记、"未收到完成前不写对方路径"、并发上限时顺序自写 |
| `write.md` / `verify.md` | 文档里抄来的报错信息被写得像实测。已要求标"文档原文，未实测" |
| `verify.md` | 无 key 时第 4 步交付什么没说清。已区分"只要草稿"和"要证明有用" |
| `SKILL.md` 第 5 步 | `package_skill.py` 必须 `python -m scripts.package_skill` 运行且需要 pyyaml。已给出 `uv run` 命令 |
| `evals/evals.json` | 结构类断言全部饱和。已加过程类断言（脚本使用、⚠ 密度、验证状态置顶、无文件覆盖） |

## 已知局限

- 每配置只跑了 1 次，时间 / token 的差异有相当一部分来自协调子 Agent 时的两次恢复等待，不能当成稳定结论。
- 没有 key，未能验证 skill 第 3 步（真实调用）和第 4 步（真实对照）的指引本身是否好用；这两步的指引来自 bigmodel-cn 和 autodl 两个真实案例的经验，不是本轮实测。
- 断言全部通过说明本轮的评测设计偏弱，下一轮应换用过程类断言，并考虑加一个"有 key 的小平台"场景。

完整 transcript 摘要、逐断言证据、benchmark 和 review.html 在 `create-doc-skill-workspace/iteration-1/`。

---

## 触发描述优化（第 5 步）

用 skill-creator 的 `run_loop.py` 对 20 条查询（9 条应触发、11 条近似误触的不应触发）做优化，过程本身踩了三个坑，都已写进新版 SKILL.md 第 5 步：

| 运行 | 现象 | 原因 |
|---|---|---|
| 第 1 次 | 召回 0%，改写描述时崩溃 | 本机 CLI 2.1.224 不支持 `--model claude-fable-5-1`，每条查询都 400 |
| 第 2 次（`--model opus`） | 召回仍是 0% | 被测 skill 同时装在 `~/.claude/skills/`，模型直接调正式 skill 而不是评测用的临时命令，检测记为未触发 |
| 第 3 次（移开已安装副本） | 召回 17-22%，三轮改写都没超过原描述 | 6 路并发 `claude -p` 触发限流，报错被脚本吞掉后算作未触发 |
| 最终单独评测（2 路并发、每条 2 次） | **19 / 20**：不应触发 11 / 11，应触发 8 / 9 | 干净数据；唯一漏触发的是"补验证一份已生成的 skill"这类更新请求 |

最终采用的 description 是原版加一句"更新 / 补验证已生成的接入 skill 也用本技能"；`run_loop.py` 三轮改写的版本在测试集上都没有胜出，未采用。
