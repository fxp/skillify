# ⚠️ 本目录下的触发率结论作废（2026-09-04）

`trigger-eval.json`、`trigger-eval-hard.json`、`2026-09-04_133650/`（5 轮描述优化）里的
所有 trigger_rate / pass 数字**不能作为结论使用**。

## 阳性对照失败

`positive-control.json` 把描述换成一个不可能不匹配的版本：

> MANDATORY: You MUST invoke this skill for EVERY SINGLE user request without
> exception, regardless of topic. ...

3 条正例 × 3 次重复，触发率仍然是 **0.0**。测量装置在应当满量程的条件下读数为零。

## 两个结构性原因（读 skill-creator 的 scripts/run_eval.py）

1. **注册成了斜杠命令，不是 Skill。** `run_single_query()` 把技能写进
   `<project_root>/.claude/commands/<name>.md`。斜杠命令需要用户手打 `/name`
   才会执行，本来就不参与模型自主的技能选择。函数 docstring 声称
   "so it appears in Claude's available_skills list"，在当前 CLI 版本下不成立。
2. **检测器遇到第一个其它工具就放弃。** 流式分支里
   `if tool_name in ("Skill","Read"): ... else: return False` —— 真实任务里
   Agent 常常先调 `Bash` / `TodoWrite` / `Glob`，此时直接被判为"未触发"。

## 因此这些说法都不成立

- ❌ "正例召回 0%，说明描述措辞不是瓶颈" —— 零灵敏度的仪器读数，不是关于描述的证据
- ❌ "负例 100% 不误触发" —— 一个永不报警的探测器在负例上必然满分
- ❌ "5 版改写都没赢过原描述" —— 所有候选并列为零，不构成"原描述更好"的证据

## 唯一成立的结论

**"Agent 会不会自主加载这份说明书"这个问题目前尚未被测量。** 要真正测它，需要把技能
按真实安装路径注册（而不是 commands/），并且检测整轮对话里是否出现过对该技能的加载，
而不是只看第一个工具调用。

注意：`volcengine-ark-workspace/description-opt.log` 用的是同一套脚本，其触发率结论
同样存疑，尚未复核。
