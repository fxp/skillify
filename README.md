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
| `bigmodel-cn` | 智谱 AI 开放平台（open.bigmodel.cn，GLM 系列）+ GLM Coding Plan 编程套餐 | 以 **GLM-5.3 为执行 Agent** 的 5 轮基准：12 场景 / 122 次运行，其中 **4 个统计显著**（p = 0.008 / 0.048 / 0.048 / 0.048），7 个打平、1 个领先但不显著；合并满分率 skill 54/56 vs baseline 35/56（p = 9×10⁻⁶）；实测查出并修正 15 条文档错误。见 `bigmodel-cn-workspace/comparison-report.md`。<br>**另有 5 轮说明书优化尝试全部失败**（拆分 reference / 陷阱速查表 / 代码片段），在弱执行器 `glm-4.5-flash` 上均不如未优化的原版，已回退；见 `bigmodel-cn-workspace/weak-exec/RESULTS.md` |
| `autodl` | AutoDL GPU 算力平台 API（账户 / 容器实例 Pro / 弹性部署） | 以 **GLM-5.3 为执行 Agent**：3 场景 / 30 次运行，1 个统计显著（p = 0.008，5/5 vs 0/5）；全部只读接口零费用；实测修正 11 条文档错误。见 `autodl-workspace/comparison-report.md` |
| `create-doc-skill` | 元技能：把任意开放平台的开发者文档站生成为一份经真实调用验证的接入 skill（本工作区方法论的可复用版本，原名 `generate-skill-from-api-docs`） | 1 轮 2 个场景（新版 vs 旧版快照），见 `create-doc-skill-workspace/comparison-report.md` |
| `volcengine-ark` | 火山引擎·火山方舟（ark.cn-beijing.volces.com，豆包 Doubao / Seedream / Seedance 及方舟上的 GLM / Kimi / DeepSeek / MiniMax）+ Agent Plan 与 Coding Plan 两套订阅套餐 | 以 **GLM-5.3 为执行 Agent**：3 场景 / 30 次运行，**0 个达到统计显著**（技能在 2 个场景领先但 n=5 不够，1 个场景是出题失误）；另经真实调用探针约 45 次，修正 8 条文档 / SDK 错误。见 `volcengine-ark-workspace/comparison-report.md` |

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
