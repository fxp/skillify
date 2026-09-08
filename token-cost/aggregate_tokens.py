# -*- coding: utf-8 -*-
"""从 Claude Code 的会话 transcript 里统计每次评测运行的真实 token 消耗。

数据来源是 ~/.claude/projects/<cwd-slug>/*.jsonl —— 每次 `claude -p` 运行的完整记录，
其中每条 assistant 消息都带 usage，含 cache_creation_input_tokens / cache_read_input_tokens。

用法： python3 aggregate_tokens.py [--json out.json]

口径说明见 README-token-cost.md。
"""
import json, pathlib, re, sys, collections

PROJ = pathlib.Path.home() / ".claude" / "projects"
PREFIX = "-Users-chopinfeng-Workspace-Skillify-"

# 计费当量权重（以 input token 为 1 单位）。Anthropic 官方比价：
#   cache 写入 = 1.25×input，cache 读取 = 0.1×input，output = 5×input（Sonnet 档）
# 智谱 Coding Plan 是配额制不按 token 计价，所以这里给的是"当量"而非金额，
# 便于换任何一家的价格重新加权；原始四项计数同时保留。
W_INPUT, W_CACHE_W, W_CACHE_R, W_OUTPUT = 1.0, 1.25, 0.1, 5.0


def slug_of(round_dir, scenario, cfg, run):
    """把运行目录路径还原成 Claude Code 的 project slug。"""
    return (PREFIX + round_dir.replace("/", "-").replace("_", "-")
            + "-" + scenario.replace("_", "-")
            + "-" + cfg.replace("_", "-")
            + "-run-" + str(run))


def usage_of(slug, mode="last"):
    """统计一次运行的 token。

    两个必须处理的坑（都会把结论做假，已实测确认）：
    1. Claude Code 的 JSONL **每个 content block 写一行，每行都带完整 usage**——
       同一次 API 调用会出现好几行。必须按 message.id 去重，否则 token 数虚高约 4 倍。
    2. 有的 run 因为 900s 超时被重跑过，目录下会有多个 transcript。
       mode="last" 只取产出了交付脚本的那一次；mode="all" 把所有尝试都算进去（真实付出的成本）。
    """
    d = PROJ / slug
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
    if not files:
        return None
    use = files[-1:] if mode == "last" else files
    agg = collections.Counter()
    seen = {}
    for f in use:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                o = json.loads(line)
            except Exception:
                continue
            m = o.get("message") or {}
            if m.get("role") != "assistant":
                continue
            u = m.get("usage")
            mid = m.get("id")
            if isinstance(u, dict) and mid and (f.name, mid) not in seen:
                seen[(f.name, mid)] = True
                agg["input"] += u.get("input_tokens", 0) or 0
                agg["cache_w"] += u.get("cache_creation_input_tokens", 0) or 0
                agg["cache_r"] += u.get("cache_read_input_tokens", 0) or 0
                agg["output"] += u.get("output_tokens", 0) or 0
            for blk in (m.get("content") or []):
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    nm = blk.get("name", "")
                    agg["tool_calls"] += 1
                    if nm in ("WebFetch", "WebSearch"):
                        agg["web_fetch"] += 1
                    elif nm == "Read":
                        agg["reads"] += 1
    if not seen:
        return None
    agg["turns"] = len(seen)
    agg["attempts"] = len(use)
    agg["transcripts"] = len(files)
    for k in ("web_fetch", "reads", "tool_calls"):
        agg.setdefault(k, 0)
    agg["wire"] = agg["input"] + agg["cache_w"] + agg["cache_r"] + agg["output"]
    agg["billable"] = round(agg["input"] * W_INPUT + agg["cache_w"] * W_CACHE_W
                            + agg["cache_r"] * W_CACHE_R + agg["output"] * W_OUTPUT)
    return dict(agg)


# 所有 GLM 执行轮：(工作区目录, 轮次目录, [场景], n)
ROUNDS = [
    ("bigmodel-cn-workspace", "glm-round",   ["batch-pipeline", "pdf-contract"], 3),
    ("bigmodel-cn-workspace", "glm-round2",  ["batch-best-model", "pdf-reuse-fileid"], 5),
    ("bigmodel-cn-workspace", "glm-round3",  ["cited-web-answer", "rag-index-embeddings"], 5),
    ("bigmodel-cn-workspace", "glm-round3b", ["cited-web-answer"], 5),
    ("bigmodel-cn-workspace", "glm-round4",  ["plan-1113-fix", "async-model-pinning"], 5),
    ("bigmodel-cn-workspace", "glm-round5",  ["token-budget-empty-answer", "kb-id-validation-silent200",
                                              "json-schema-not-enforced", "forced-tool-choice-ignored"], 5),
    ("autodl-workspace", "glm-round", ["balance-unit", "get-params-style",
                                       "deployment-permission-probe"], 5),
    ("volcengine-ark-workspace", "glm-round", ["anthropic-entry-model-pinning", "kimi-max-tokens-empty",
                                               "plan-embeddings-shape"], 5),
]

MODE = "all" if "--all-attempts" in sys.argv else "last"
print(f"口径: {MODE} (transcript 按 message.id 去重)")
rows = []
missing = []
for ws, rd, scens, n in ROUNDS:
    for sc in scens:
        for cfg in ("with_skill", "without_skill"):
            for run in range(1, n + 1):
                slug = slug_of(f"{ws}-{rd}", sc, cfg, run)
                u = usage_of(slug, mode=MODE)
                if u is None:
                    missing.append(slug)
                    continue
                rows.append({"workspace": ws, "round": rd, "scenario": sc,
                             "config": cfg, "run": run, **u})

print(f"采集到 {len(rows)} 次运行的 token 记录；未找到 transcript 的 {len(missing)} 次")
if missing[:5]:
    for m in missing[:5]:
        print("   缺:", m)

if not rows:
    sys.exit("没有采集到数据")


def summarize(subset, label):
    if not subset:
        return None
    k = len(subset)
    agg = {f: sum(r[f] for r in subset) / k for f in
           ("input", "cache_w", "cache_r", "output", "wire", "billable", "turns",
            "web_fetch", "reads", "tool_calls")}
    agg["n"] = k
    agg["label"] = label
    return agg


def fmt(a):
    return (f"{a['label']:14s} n={a['n']:>3d}  "
            f"wire={a['wire']:>10,.0f}  billable={a['billable']:>10,.0f}  "
            f"in={a['input']:>7,.0f}  cw={a['cache_w']:>9,.0f}  cr={a['cache_r']:>10,.0f}  "
            f"out={a['output']:>7,.0f}  turns={a['turns']:>4.1f}  "
            f"tools={a['tool_calls']:>4.1f}  fetch={a['web_fetch']:>4.1f}  reads={a['reads']:>4.1f}")


print("\n" + "=" * 128)
print("总体（每次运行的平均值）")
print("=" * 128)
for cfg, lab in (("with_skill", "读了说明书"), ("without_skill", "baseline")):
    a = summarize([r for r in rows if r["config"] == cfg], lab)
    print(fmt(a))
ws_ = summarize([r for r in rows if r["config"] == "with_skill"], "skill")
wo_ = summarize([r for r in rows if r["config"] == "without_skill"], "base")
for key, name in (("wire", "线上总 token"), ("billable", "计费当量"), ("turns", "对话轮数"),
                  ("tool_calls", "工具调用次数"), ("web_fetch", "WebFetch 次数"), ("reads", "Read 次数")):
    if wo_[key] == 0:
        print(f"  {name:16s} skill {ws_[key]:.1f} vs baseline {wo_[key]:.1f}")
        continue
    d = (ws_[key] - wo_[key]) / wo_[key] * 100
    print(f"  {name:16s} skill 相对 baseline： {d:+6.1f}%   ({ws_[key]:,.1f} vs {wo_[key]:,.1f})")

print("\n" + "=" * 128)
print("按平台")
print("=" * 128)
for ws in ("bigmodel-cn-workspace", "autodl-workspace", "volcengine-ark-workspace"):
    sub = [r for r in rows if r["workspace"] == ws]
    if not sub:
        continue
    print(f"\n--- {ws} ---")
    a = summarize([r for r in sub if r["config"] == "with_skill"], "读了说明书")
    b = summarize([r for r in sub if r["config"] == "without_skill"], "baseline")
    print(fmt(a)); print(fmt(b))
    for key, name in (("wire", "线上总 token"), ("billable", "计费当量")):
        print(f"  {name}： {(a[key]-b[key])/b[key]*100:+.1f}%")

print("\n" + "=" * 128)
print("按场景（wire / billable，skill vs baseline）")
print("=" * 128)
for ws, rd, scens, n in ROUNDS:
    for sc in scens:
        sub = [r for r in rows if r["workspace"] == ws and r["round"] == rd and r["scenario"] == sc]
        a = summarize([r for r in sub if r["config"] == "with_skill"], "s")
        b = summarize([r for r in sub if r["config"] == "without_skill"], "b")
        if not a or not b:
            continue
        dw = (a["wire"] - b["wire"]) / b["wire"] * 100
        db = (a["billable"] - b["billable"]) / b["billable"] * 100
        tag = "↓省" if dw < 0 else "↑增"
        print(f"{rd:12s} {sc:30s} wire {a['wire']:>9,.0f} vs {b['wire']:>9,.0f} ({dw:+6.1f}%)  "
              f"billable {a['billable']:>9,.0f} vs {b['billable']:>9,.0f} ({db:+6.1f}%)  {tag}")

if "--json" in sys.argv:
    out = pathlib.Path(sys.argv[sys.argv.index("--json") + 1])
    out.write_text(json.dumps({"rows": rows, "weights": {
        "input": W_INPUT, "cache_write": W_CACHE_W, "cache_read": W_CACHE_R, "output": W_OUTPUT}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n写入", out)
