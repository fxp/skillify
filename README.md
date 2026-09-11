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
| `kingdee` | 金蝶云星空（K/3 Cloud）WebAPI：第三方授权签名、单据查询 / 保存 / 提交 / 审核 / 下推、物料客户供应商与多组织分配、总账凭证与应收应付；不覆盖星瀚 / 苍穹 / 旗舰版 / 精斗云 / KIS | **文档版**（2026-09-11）：整理自无需登录的旧版官方 API 文档（7.5.1800.6，2020-10）与官方 Python SDK 源码，未用真实凭证验证；新版 API 中心需登录、未抓取，可能有更新。业务接口部署在客户服务器上，只探测了旧公网网关。验证计划见 `skills/kingdee/data/verification-plan.md` |

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
