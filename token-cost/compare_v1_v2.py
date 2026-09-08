# -*- coding: utf-8 -*-
"""v1 说明书 / v2 精简说明书 / baseline 三方对比：token 与准确率。

8 个场景 × n=5。任务文本逐字相同、harness 相同、判分器是各场景原来那一份冻结的，
唯一变量是说明书版本。
"""
import json, pathlib, statistics, collections

HERE = pathlib.Path(__file__).resolve().parent
WS = HERE.parent
src = (HERE / "aggregate_tokens.py").read_text(encoding="utf-8")
ns = {"__name__": "c"}
exec(src.split('print(f"采集到')[0], ns)
usage_of = ns["usage_of"]
PREF = "-Users-chopinfeng-Workspace-Skillify-bigmodel-cn-workspace-"

SC = {"cited-web-answer": "glm-round3b", "rag-index-embeddings": "glm-round3",
      "plan-1113-fix": "glm-round4", "async-model-pinning": "glm-round4",
      "json-schema-not-enforced": "glm-round5", "kb-id-validation-silent200": "glm-round5",
      "batch-best-model": "glm-round2", "pdf-reuse-fileid": "glm-round2"}


def slug(kind, sc, rd, run):
    if kind == "v2":
        return f"{PREF}v2-eval-{sc}-with-skill-run-{run}"
    cfg = "with-skill" if kind == "v1" else "without-skill"
    return f"{PREF}{rd}-{sc}-{cfg}-run-{run}"


def scores(kind, sc, rd):
    if kind == "v2":
        f = WS / "bigmodel-cn-workspace" / "v2-eval" / "summary.json"
        return json.loads(f.read_text(encoding="utf-8"))[sc]["scores"]
    f = WS / "bigmodel-cn-workspace" / rd / "summary.json"
    cfg = "with_skill" if kind == "v1" else "without_skill"
    return json.loads(f.read_text(encoding="utf-8"))[f"{sc}/{cfg}"]["scores"]


DATA = {k: [] for k in ("v1", "v2", "base")}
PER_SC = collections.defaultdict(dict)
for sc, rd in SC.items():
    for kind in ("v1", "v2", "base"):
        sco = scores(kind, sc, rd)
        rows = []
        for run in range(1, 6):
            u = usage_of(slug(kind, sc, rd, run))
            if not u:
                continue
            u["score"] = sco[run - 1] if run - 1 < len(sco) else None
            u["sc"] = sc
            rows.append(u)
            DATA[kind].append(u)
        PER_SC[sc][kind] = rows

NAME = {"v1": "v1 说明书", "v2": "v2 精简版", "base": "baseline"}


def agg(rows, f):
    return statistics.mean(r[f] for r in rows)


print(f"每组运行数： v1={len(DATA['v1'])}  v2={len(DATA['v2'])}  baseline={len(DATA['base'])}\n")
print("=" * 100)
print("一、token（8 个场景 × n=5 的平均）")
print("=" * 100)
print(f"{'':12s} {'线上总 token':>14s} {'计费当量':>12s} {'Read 次数':>10s} {'WebFetch':>10s} {'轮数':>7s}")
for k in ("base", "v1", "v2"):
    r = DATA[k]
    print(f"{NAME[k]:12s} {agg(r,'wire'):>14,.0f} {agg(r,'billable'):>12,.0f} "
          f"{agg(r,'reads'):>10.1f} {agg(r,'web_fetch'):>10.1f} {agg(r,'turns'):>7.1f}")
for a, b, lab in (("v2", "v1", "v2 相对 v1"), ("v2", "base", "v2 相对 baseline"), ("v1", "base", "v1 相对 baseline")):
    dw = agg(DATA[a], "wire") / agg(DATA[b], "wire") - 1
    db = agg(DATA[a], "billable") / agg(DATA[b], "billable") - 1
    print(f"  {lab:18s} 线上 {dw:+7.1%}   计费当量 {db:+7.1%}")

print("\n" + "=" * 100)
print("二、准确率（满分率）")
print("=" * 100)
for k in ("base", "v1", "v2"):
    r = DATA[k]
    full = sum(1 for x in r if (x["score"] or 0) >= 0.999)
    mean = statistics.mean(x["score"] or 0 for x in r)
    print(f"{NAME[k]:12s} 满分 {full:>2d}/{len(r):<3d} ({full/len(r):.1%})   平均分 {mean:.3f}")

print("\n" + "=" * 100)
print("三、每做对一次的计费当量")
print("=" * 100)
for k in ("base", "v1", "v2"):
    r = DATA[k]
    ok = sum(1 for x in r if (x["score"] or 0) >= 0.999)
    tot = sum(x["billable"] for x in r)
    print(f"{NAME[k]:12s} {tot/ok:>12,.0f}   （总花费 {tot:,} ÷ 成功 {ok} 次）")
base_cps = sum(x["billable"] for x in DATA["base"]) / sum(1 for x in DATA["base"] if (x["score"] or 0) >= 0.999)
for k in ("v1", "v2"):
    r = DATA[k]
    cps = sum(x["billable"] for x in r) / sum(1 for x in r if (x["score"] or 0) >= 0.999)
    print(f"  {NAME[k]} 相对 baseline： {cps/base_cps-1:+.1%}")

print("\n" + "=" * 100)
print("四、逐场景（线上 token / 满分率）")
print("=" * 100)
print(f"{'场景':30s} {'v1 token':>10s} {'v2 token':>10s} {'省':>7s}   {'v1 满分':>7s} {'v2 满分':>7s} {'base':>6s}")
for sc in SC:
    r1, r2, rb = PER_SC[sc]["v1"], PER_SC[sc]["v2"], PER_SC[sc]["base"]
    w1, w2 = agg(r1, "wire"), agg(r2, "wire")
    f = lambda rr: f"{sum(1 for x in rr if (x['score'] or 0) >= 0.999)}/{len(rr)}"
    print(f"{sc:30s} {w1:>10,.0f} {w2:>10,.0f} {w2/w1-1:>+7.1%}   {f(r1):>7s} {f(r2):>7s} {f(rb):>6s}")

print("\n" + "=" * 100)
print("五、Read 读入的字符量（说明书被读进上下文的实际体积）")
print("=" * 100)


def read_chars(kind):
    P = pathlib.Path.home() / ".claude" / "projects"
    tot, n = [], 0
    for sc, rd in SC.items():
        for run in range(1, 6):
            d = P / slug(kind, sc, rd, run)
            fs = sorted(d.glob("*.jsonl"), key=lambda x: x.stat().st_mtime) if d.is_dir() else []
            if not fs:
                continue
            lines = [json.loads(l) for l in fs[-1].read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
            idmap = {}
            for o in lines:
                for blk in ((o.get("message") or {}).get("content") or []):
                    if isinstance(blk, dict) and blk.get("type") == "tool_use" and blk.get("name") == "Read":
                        idmap[blk.get("id")] = (blk.get("input") or {}).get("file_path", "")
            s = 0
            for o in lines:
                for blk in ((o.get("message") or {}).get("content") or []):
                    if isinstance(blk, dict) and blk.get("type") == "tool_result" and blk.get("tool_use_id") in idmap:
                        c = blk.get("content")
                        s += len(c) if isinstance(c, str) else sum(len(x.get("text", "")) for x in c if isinstance(x, dict))
            tot.append(s); n += 1
    return statistics.mean(tot) if tot else 0


for k in ("base", "v1", "v2"):
    print(f"{NAME[k]:12s} 每次运行 Read 读入 {read_chars(k):>10,.0f} 字符")
