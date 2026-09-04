#!/usr/bin/env python3
"""Pre-commit verification for the volcengine-ark skill + workspace."""
import json, os, re, sys, glob

# Layout-agnostic: works from the repo (skills/volcengine-ark/{,data}) and from the
# local build workspace (volcengine-ark/ + volcengine-ark-workspace/ as siblings).
HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(HERE, "iteration-1")):        # repo: .../volcengine-ark/data
    SKILL = os.path.dirname(HERE)
    WS = HERE
else:                                                        # local build workspace
    SKILL = os.path.join(HERE, "volcengine-ark")
    WS = os.path.join(HERE, "volcengine-ark-workspace")
ROOT = os.path.dirname(SKILL)
fails, warns = [], []
def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond: fails.append(msg)

print("== 1. skill structure ==")
check(os.path.isfile(f"{SKILL}/SKILL.md"), "SKILL.md exists")
refs = sorted(glob.glob(f"{SKILL}/references/*.md"))
check(len(refs) == 14, f"14 reference files present (found {len(refs)})")
check(os.path.isfile(f"{SKILL}/evals/evals.json"), "evals/evals.json exists")
check(not glob.glob(f"{SKILL}/references/*.done"), "no leftover .done build markers")

print("== 2. frontmatter ==")
skill_md = open(f"{SKILL}/SKILL.md").read()
m = re.match(r"^---\n(.*?)\n---\n", skill_md, re.S)
check(bool(m), "frontmatter block parses")
if m:
    fm = m.group(1)
    name = re.search(r"^name:\s*(\S+)", fm, re.M)
    desc = re.search(r"^description:\s*(.+)$", fm, re.M)
    check(bool(name) and name.group(1) == "volcengine-ark", "name is volcengine-ark")
    check(bool(desc), "description present")
    if desc:
        d = desc.group(1)
        check(len(d) <= 1024, f"description <= 1024 chars (is {len(d)})")
        check("<" not in d and ">" not in d, "description has no angle brackets")
    allowed = {"name","description","license","allowed-tools","metadata","compatibility"}
    keys = set(re.findall(r"^([a-z-]+):", fm, re.M))
    check(keys <= allowed, f"only allowed frontmatter keys (found {sorted(keys)})")

print("== 3. every reference linked from SKILL.md exists ==")
linked = set(re.findall(r"references/([a-z0-9-]+\.md)", skill_md))
have = {os.path.basename(p) for p in refs}
missing = linked - have
orphan = have - linked
check(not missing, f"no dangling reference links (missing: {sorted(missing)})")
check(not orphan, f"every reference file is linked (orphans: {sorted(orphan)})")

print("== 4. JSON artifacts parse ==")
jsons = [f"{SKILL}/evals/evals.json", f"{WS}/trigger-eval.json",
         f"{WS}/iteration-1/benchmark.json"] \
        + sorted(glob.glob(f"{WS}/iteration-1/*/eval_metadata.json")) \
        + sorted(glob.glob(f"{WS}/iteration-1/*/*/run-1/grading.json")) \
        + sorted(glob.glob(f"{WS}/iteration-1/*/*/run-1/timing.json"))
bad = []
for p in jsons:
    try: json.load(open(p))
    except Exception as e: bad.append(f"{os.path.relpath(p, ROOT)}: {e}")
check(not bad, f"all {len(jsons)} JSON artifacts parse ({bad[:2]})")

print("== 5. eval + grading completeness ==")
ev = json.load(open(f"{SKILL}/evals/evals.json"))
check(len(ev["evals"]) == 8, f"8 eval scenarios defined (found {len(ev['evals'])})")
check(all(e.get("expectations") for e in ev["evals"]), "every scenario has expectations")
check(len(glob.glob(f"{WS}/iteration-1/*/*/run-1/grading.json")) == 16, "16 grading.json (8 scenarios x 2 configs)")
check(len(glob.glob(f"{WS}/iteration-1/*/*/run-1/timing.json")) == 16, "16 timing.json")
check(len(glob.glob(f"{WS}/iteration-1/*/verdict.md")) == 8, "8 verdict.md")

print("== 6. grading.json uses viewer-required field names ==")
badf = []
for p in sorted(glob.glob(f"{WS}/iteration-1/*/*/run-1/grading.json")):
    g = json.load(open(p))
    if "expectations" not in g or "summary" not in g: badf.append(p); continue
    for e in g["expectations"]:
        if not {"text","passed","evidence"} <= set(e): badf.append(p); break
check(not badf, f"all grading.json use text/passed/evidence ({[os.path.relpath(x,ROOT) for x in badf[:2]]})")

print("== 7. tally matches the report ==")
ws_p = ws_t = bs_p = bs_t = 0
for d in sorted(glob.glob(f"{WS}/iteration-1/eval-*")):
    for cfg, acc in (("with_skill","w"), ("without_skill","b")):
        s = json.load(open(f"{d}/{cfg}/run-1/grading.json"))["summary"]
        if acc == "w": ws_p += s["passed"]; ws_t += s["total"]
        else: bs_p += s["passed"]; bs_t += s["total"]
print(f"         skill {ws_p}/{ws_t}   baseline {bs_p}/{bs_t}")
check((ws_p, ws_t) == (37, 37), "skill scores 37/37 as reported")
check((bs_p, bs_t) == (18, 37), "baseline scores 18/37 as reported")
wins = sum(1 for p in glob.glob(f"{WS}/iteration-1/*/verdict.md")
           if open(p).read().lstrip().startswith("Result: win")
           or "\nResult: win" in open(p).read())
ties = sum(1 for p in glob.glob(f"{WS}/iteration-1/*/verdict.md") if "Result: tie" in open(p).read())
print(f"         verdicts: {wins} win / {ties} tie")
check(wins == 7 and ties == 1, "7 wins + 1 tie as reported")

print("== 8. verification claims are dated and evidenced ==")
allref = "".join(open(p).read() for p in refs) + skill_md
n_verified = allref.count("已用真实 API 验证")
check(n_verified >= 40, f"live-verification markers present ({n_verified})")
check("2026-09-04" in allref, "verification date stamped")
# a claim is dated if 2026-09-04 appears on the same line; the convention note in
# coding-plan.md refers to the marker itself rather than asserting anything.
undated = []
for f in refs + [f"{SKILL}/SKILL.md"]:
    for n, line in enumerate(open(f), 1):
        if "已用真实 API 验证" not in line: continue
        if "标了「已用真实 API 验证」的条目" in line: continue   # convention note, not a claim
        if "2026-09-04" not in line:
            undated.append(f"{os.path.basename(f)}:{n}")
check(not undated, f"every live-verification claim is dated on its own line ({undated})")

print("== 9. hygiene ==")
leak = []
for p in glob.glob(f"{SKILL}/**/*", recursive=True):
    if os.path.isfile(p) and not p.endswith(".skill"):
        try: t = open(p, errors="ignore").read()
        except Exception: continue
        # needle assembled at runtime so this file does not match itself
        needle = "ark-" + "a59113ca"
        if needle in t: leak.append(p)
check(not leak, f"no API key material in repo ({leak[:2]})")

print("== 10. probe script still valid ==")
import ast
for p in (f"{WS}/probe.py", f"{WS}/precheck.py"):
    try: ast.parse(open(p).read()); ok = True
    except Exception as e: ok = False; print(e)
    check(ok, f"{os.path.basename(p)} parses")

print("\n" + ("ALL CHECKS PASSED" if not fails else f"{len(fails)} FAILURE(S):\n  - " + "\n  - ".join(fails)))
sys.exit(1 if fails else 0)
