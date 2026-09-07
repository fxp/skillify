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
└── <skill>-workspace/             # 评测产物（不随 skill 分发）
    ├── comparison-report.md       # 全部轮次的 skill vs baseline 价值审计报告
    └── iteration-N/
        ├── benchmark.json / .md   # 该轮 pass rate / 耗时 / tokens 汇总
        ├── review.html            # skill-creator 自带的逐用例审阅页
        └── eval-<name>/
            ├── with_skill/run-*/     # 带 skill 的运行记录、outputs、grading.json
            └── without_skill/run-*/  # 不带 skill 的 baseline 运行记录
```

当前包含的 skill：

| Skill | 覆盖平台 | 评测状态 |
|---|---|---|
| `bigmodel-cn` | 智谱 AI 开放平台（open.bigmodel.cn，GLM 系列）+ GLM Coding Plan 编程套餐 | 7 轮 25 个场景（第 7 轮为真实执行的端到端成功率），见 `bigmodel-cn-workspace/comparison-report.md` |
| `autodl` | AutoDL GPU 算力平台 API（账户 / 容器实例 Pro / 弹性部署） | 3 轮 7 个场景，真实实例生命周期已验证，见 `autodl-workspace/comparison-report.md` |
| `create-doc-skill` | 元技能：把任意开放平台的开发者文档站生成为一份经真实调用验证的接入 skill（本工作区方法论的可复用版本，原名 `generate-skill-from-api-docs`） | 1 轮 2 个场景（新版 vs 旧版快照），见 `create-doc-skill-workspace/comparison-report.md` |
| `volcengine-ark` | 火山引擎·火山方舟（ark.cn-beijing.volces.com，豆包 Doubao / Seedream / Seedance 及方舟上的 GLM / Kimi / DeepSeek / MiniMax）+ Agent Plan 与 Coding Plan 两套订阅套餐 | 1 轮 8 个场景，Agent Plan 入口经真实调用验证（约 45 次），见 `volcengine-ark-workspace/comparison-report.md` |

## 评测流程

1. 在 `<skill>/evals/evals.json` 里写场景与断言。
2. 每个场景各跑一次带 skill 与不带 skill 的 agent，输出落在 `iteration-N/eval-<name>/`。
3. 用 grader 按断言评分，写入 `grading.json`；用 `aggregate_benchmark.py` 汇总成 `benchmark.json` / `benchmark.md`。
4. 断言必须以真实 API 的实际返回为准，不能只看 OpenAPI 规范；评测过程中发现的文档错误直接改回 `references/`。
5. 所有轮次做完后，写一份 `comparison-report.md`。

## 报告格式约定

- 对比报告统一为 `<skill>-workspace/comparison-report.md`，以后新增的 skill 也遵守此约定。
- 报告结构：顶部指标汇总表；每轮一张「场景 / 结果 / skill 得分 / baseline 得分」表，每个场景附 **Task** 和 **Why** 两段说明；结尾列出评测中修正的文档条目。
