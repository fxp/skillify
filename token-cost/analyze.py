# -*- coding: utf-8 -*-
"""token 成本分析：每次运行的成本、每次成功的成本、cache 的作用。

用法： python3 analyze.py            # 主口径：只算交付那次尝试
       python3 analyze.py --all-attempts
"""
import json, pathlib, sys, statistics, subprocess, collections

HERE = pathlib.Path(__file__).resolve().parent
WS = HERE.parent

# 复用采集器
src = (HERE / "aggregate_tokens.py").read_text(encoding="utf-8")
ns = {"__name__": "collector"}
exec(src.split('print(f"采集到')[0], ns)
usage_of, slug_of, ROUNDS = ns["usage_of"], ns["slug_of"], ns["ROUNDS"]
W = (ns["W_INPUT"], ns["W_CACHE_W"], ns["W_CACHE_R"], ns["W_OUTPUT"])
MODE = "all" if "--all-attempts" in sys.argv else "last"


def scores(ws, rd, sc, cfg):
    """读该场景该配置每次运行的判分（满分=1.0）。"""
    f = WS / ws / rd / "summary.json"
    if not f.exists():
        return []
    s = json.loads(f.read_text(encoding="utf-8"))
    return (s.get(f"{sc}/{cfg}") or {}).get("scores", [])


rows = []
for ws, rd, scens, n in ROUNDS:
    for sc in scens:
        for cfg in ("with_skill", "without_skill"):
            sco = scores(ws, rd, sc, cfg)
            for run in range(1, n + 1):
                u = usage_of(slug_of(f"{ws}-{rd}", sc, cfg, run), mode=MODE)
                if not u:
                    continue
                u["score"] = sco[run - 1] if run - 1 < len(sco) else None
                rows.append({"ws": ws, "rd": rd, "sc": sc, "cfg": cfg, "run": run, **u})

S = [r for r in rows if r["cfg"] == "with_skill"]
B = [r for r in rows if r["cfg"] == "without_skill"]
print(f"口径 = {MODE}；skill {len(S)} 次 / baseline {len(B)} 次\n")


def mw_u(a, b):
    """Mann-Whitney U 的正态近似 p 值（双尾）——数据右偏，不适合 t 检验。"""
    n1, n2 = len(a), len(b)
    allv = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i = {}, 0
    vals = [v for v, _ in allv]
    r = [0.0] * len(vals)
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[k] = avg
        i = j + 1
    r1 = sum(r[k] for k in range(len(allv)) if allv[k][1] == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    sd = (n1 * n2 * (n1 + n2 + 1) / 12) ** 0.5
    if sd == 0:
        return 1.0
    z = (u1 - mu) / sd
    # 正态双尾
    import math
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def block(title, key, unit=""):
    a = [r[key] for r in S]
    b = [r[key] for r in B]
    ma, mb = statistics.mean(a), statistics.mean(b)
    da, db = statistics.median(a), statistics.median(b)
    p = mw_u(a, b)
    print(f"{title}")
    print(f"  均值   skill {ma:>12,.0f}{unit}   baseline {mb:>12,.0f}{unit}   {(ma-mb)/mb*100:+7.1f}%")
    print(f"  中位数 skill {da:>12,.0f}{unit}   baseline {db:>12,.0f}{unit}   {(da-db)/db*100:+7.1f}%")
    print(f"  Mann-Whitney 双尾 p = {p:.4f}{'  ← 显著' if p < 0.05 else ''}\n")


print("=" * 96)
print("一、每次运行的成本")
print("=" * 96)
block("线上总 token（input + cache写 + cache读 + output）", "wire")
block("计费当量（cache读×0.1，cache写×1.25，output×5）", "billable")
block("WebFetch 次数", "web_fetch")
block("对话轮数（去重后的真实 API 调用次数）", "turns")

print("=" * 96)
print("二、cache 起了多大作用")
print("=" * 96)
for lab, grp in (("读了说明书", S), ("baseline", B)):
    ci = statistics.mean(r["input"] for r in grp)
    cr = statistics.mean(r["cache_r"] for r in grp)
    cw = statistics.mean(r["cache_w"] for r in grp)
    co = statistics.mean(r["output"] for r in grp)
    tot = ci + cr + cw
    print(f"{lab:12s} 输入侧 {tot:>10,.0f}  其中 cache 命中 {cr:>10,.0f} ({cr/tot*100:5.1f}%)  "
          f"未命中 {ci:>9,.0f}  cache 写入 {cw:>7,.0f}  输出 {co:>8,.0f}")
sa = statistics.mean(r["wire"] for r in S) / statistics.mean(r["wire"] for r in B) - 1
ba = statistics.mean(r["billable"] for r in S) / statistics.mean(r["billable"] for r in B) - 1
print(f"\n不计 cache 折扣（按线上 token 直接比）： skill {sa*100:+.1f}%")
print(f"计入 cache 折扣（cache 读只算 0.1 倍）：  skill {ba*100:+.1f}%")
print(f"→ **cache 把说明书的额外成本吸收掉了大部分**：{sa*100:+.1f}% → {ba*100:+.1f}%\n")

print("=" * 96)
print("三、每完成一次「正确」任务的成本（满分才算成功）")
print("=" * 96)
tot_s = tot_b = suc_s = suc_b = 0
print(f"{'场景':32s} {'skill 成功/次':>12s} {'base 成功/次':>12s} {'skill 每次成功':>14s} {'base 每次成功':>14s}  {'差':>8s}")
for ws, rd, scens, n in ROUNDS:
    for sc in scens:
        a = [r for r in S if r["ws"] == ws and r["rd"] == rd and r["sc"] == sc]
        b = [r for r in B if r["ws"] == ws and r["rd"] == rd and r["sc"] == sc]
        if not a or not b:
            continue
        ok_a = sum(1 for r in a if (r["score"] or 0) >= 0.999)
        ok_b = sum(1 for r in b if (r["score"] or 0) >= 0.999)
        ca = sum(r["billable"] for r in a)
        cb = sum(r["billable"] for r in b)
        tot_s += ca; tot_b += cb; suc_s += ok_a; suc_b += ok_b
        pa = f"{ca/ok_a:,.0f}" if ok_a else "∞（0 次成功）"
        pb = f"{cb/ok_b:,.0f}" if ok_b else "∞（0 次成功）"
        d = f"{(ca/ok_a)/(cb/ok_b)-1:+.0%}" if ok_a and ok_b else "—"
        print(f"{sc:32s} {ok_a:>6d}/{len(a):<5d} {ok_b:>6d}/{len(b):<5d} {pa:>14s} {pb:>14s}  {d:>8s}")
print("-" * 96)
print(f"{'合计':32s} {suc_s:>6d}/{len(S):<5d} {suc_b:>6d}/{len(B):<5d} "
      f"{tot_s/suc_s:>14,.0f} {tot_b/suc_b:>14,.0f}  {(tot_s/suc_s)/(tot_b/suc_b)-1:>+8.0%}")

print("\n" + "=" * 96)
print("四、按平台")
print("=" * 96)
for ws in ("bigmodel-cn-workspace", "autodl-workspace", "volcengine-ark-workspace"):
    a = [r for r in S if r["ws"] == ws]; b = [r for r in B if r["ws"] == ws]
    if not a:
        continue
    wa, wb = statistics.mean(r["wire"] for r in a), statistics.mean(r["wire"] for r in b)
    ba_, bb = statistics.mean(r["billable"] for r in a), statistics.mean(r["billable"] for r in b)
    oa = sum(1 for r in a if (r["score"] or 0) >= 0.999); ob = sum(1 for r in b if (r["score"] or 0) >= 0.999)
    pa = sum(r["billable"] for r in a) / oa if oa else float("inf")
    pb = sum(r["billable"] for r in b) / ob if ob else float("inf")
    print(f"{ws:26s} wire {wa/wb-1:+7.1%}   计费当量 {ba_/bb-1:+7.1%}   "
          f"每次成功 {pa:,.0f} vs {pb:,.0f} ({pa/pb-1:+.0%})")

if "--json" in sys.argv:
    (HERE / "analysis.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n写入 analysis.json")
