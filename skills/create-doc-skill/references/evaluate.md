# 第四步：用真实对照实验证明价值

目标：不交付"我觉得这份 skill 应该有用"，交付"实测出来的：有用在哪、体现在哪几个具体场景、哪些场景其实没差别"。

## 设计场景

- **专挑"有经验的开发者会凭其他平台的直觉写错"的任务**。Hello World 测不出价值——这类模式预训练语料覆盖得很好，两版代码都会对，第一轮很可能全是平局，这很正常，如实记录。
- **最好的场景直接来自第 3 步发现的偏差**：不支持的参数静默失效、批处理独立的模型白名单、需要显式开关才出现的响应字段、鉴权 header 没有 Bearer 前缀、GET 必须走 query string。
- **prompt 写成普通的功能需求，不暗示坑在哪**："客服机器人必须先查订单再回答任何问题"，而不是"注意 tool_choice 不支持强制"。
- 每轮 3-4 个场景；所有轮次加起来覆盖每个主要能力域至少一次。
- **同一组场景换一个模型 / 版本再跑一轮**，分离"模型特有的坑"和"平台通用的坑"。智谱案例里 `thinking: disabled` 在 glm-5.3 报错、在 glm-5.2 正常，只跑一轮会把模型特有行为写成平台规则。

场景写进 `<skill>/evals/evals.json`，格式按 skill-creator 的 `references/schemas.md`：

```json
{
  "skill_name": "<platform>",
  "evals": [
    {
      "id": 1,
      "prompt": "用 <平台> 写一个 …（普通功能需求，不提示坑）",
      "expected_output": "能在真实 API 上跑通的代码：…",
      "files": [],
      "expectations": [
        "代码没有使用 <平台> 不支持的 <参数>，或对其做了 <正确处理>",
        "…"
      ]
    }
  ]
}
```

## 跑对照

这一步是 **spawn 子 Agent**，不是跑 skill-creator 的 `run_eval.py`（那个只评估触发描述）。每个场景两个版本 **在同一轮里同时发出**：

- **with_skill**：子 Agent 先读 skill 再写代码。prompt 里给 skill 路径、任务、输出目录。
- **without_skill**：完全相同的任务，不给 skill 路径。唯一变量是有没有 skill。
- 改进已有 skill 时，baseline 用旧版快照（`cp -r <skill> <workspace>/skill-snapshot/`），输出到 `old_skill/`。

目录结构：

```
<skill>-workspace/
├── skill-snapshot/                     # 迭代时的旧版
├── comparison-report.md                # 全部轮次的价值审计报告
└── iteration-N/
    ├── eval-<descriptive-name>/
    │   ├── eval_metadata.json          # eval_id / eval_name / prompt / assertions
    │   ├── with_skill/
    │   │   ├── outputs/                # 子 Agent 产出的代码
    │   │   ├── timing.json             # 从任务通知里拿 total_tokens / duration_ms，当场记
    │   │   └── grading.json
    │   └── without_skill/  (同上)
    ├── benchmark.json / benchmark.md   # aggregate_benchmark.py 产出
    └── review.html                     # generate_review.py --static 产出
```

子 Agent 完成时的通知里有 `total_tokens` 和 `duration_ms`，**当场写进 `timing.json`**，这个数据不会持久化在别处。

## 打分

- **依据真实调用结果**，不是"代码读起来像不像对"。用第 3 步实测过的报错去判定：这段代码在生产环境跑不跑得通？必要时把两版代码真的跑一次（最小规模）。
- 智谱案例第 1 轮的教训：baseline 省略了 `search_engine`，初判为 skill 获胜；重新真实调用发现该字段被静默默认，实际是平局。**事后纠正比让错误判定站着强。**
- 按 `agents/grader.md` 给每个 run 写 `grading.json`，`expectations[]` 用 `text` / `passed` / `evidence` 三个字段名（viewer 依赖精确字段名）。能用脚本检查的断言写脚本，跨轮复用。
- 汇总（Python ≥ 3.10）：

```bash
cd <skill-creator-dir>
python3.12 -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <platform>
python3.12 eval-viewer/generate_review.py <workspace>/iteration-N --skill-name <platform> \
  --benchmark <workspace>/iteration-N/benchmark.json --static <workspace>/iteration-N/review.html
```

第 2 轮起加 `--previous-workspace <workspace>/iteration-<N-1>`。

## 诚实报告

- **平局和胜利一样值得记录**。"7 赢 7 平"比夸大的"14 战全胜"更让人相信这份评测是认真做的。
- 平局的常见原因要写出来：冷门细节恰好在预训练语料里（baseline 猜对了真实的音色名）；baseline 的防御性编程绕过了它自己都不知道的坑（在多个位置探测字段，恰好命中真实位置；强制调用失败后本地兜底）。
- 一个场景的"胜利"如果是靠模型特有行为，换模型跑一轮变成平局，也照实写：这说明 skill 正确地没有过度泛化那条规则。

## `comparison-report.md` 格式

写在 `<skill>-workspace/comparison-report.md`，**Markdown，不做 HTML 或 Artifact**。结构：

```markdown
# <platform> skill · value audit

一段话：多少个场景、跑了几轮、对照什么打分（真实 API / 文档保真度）。

| Metric | Value |
| 场景数（跨 N 轮） | … |
| baseline 代码在真实 API 上失败的场景 | x / N |
| skill 版通过率 | … |
| 评测中发现并修正的文档错误 | … |

## Round 1 — <这一轮在测什么>
**Model:** <模型> · N 个场景

| Scenario | Result | Skill | Baseline |
| … | win / tie | 100% | 40% |

### <场景名> — win / tie
**Task:** 一句话说任务。
**Why:** baseline 具体错在哪（引用真实报错），或为什么打平。

（每轮重复）

## Documentation fixed along the way
| File | Finding |
每条一小节：文档写的是什么、实测是什么、证据。

结尾一句：所有 win / tie 都对照真实 API（或说明是文档保真度）判定，完整 transcript 在 `<workspace>/`。
```

数字背后的推理过程才是能让人信任这份评测的东西，不要只给一个"通过率 92%"。
