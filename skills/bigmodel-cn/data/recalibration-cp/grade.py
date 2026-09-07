# -*- coding: utf-8 -*-
"""Coding Plan 校准轮评分器：判定全部来自脚本执行结果。"""
import json, os, re, shutil, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
PLAN = os.environ.get("GLM_CODING_PLAN_API_KEY", "")
if not PLAN:
    sys.exit("export GLM_CODING_PLAN_API_KEY first")
TIMEOUT = 300

def redact(s):
    return (s or "").replace(PLAN, "<PLAN_KEY>")

def run(run_dir, needs_doc):
    main = run_dir / "outputs" / "main.py"
    if not main.exists():
        return None
    work = run_dir / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copy(main, work / "main.py")
    if needs_doc:
        shutil.copy(ROOT / "fixtures" / "report.txt", work / "report.txt")
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")}
    env["PYTHONIOENCODING"] = "utf-8"
    env["GLM_KEY"] = PLAN
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-W", "ignore", "main.py"], cwd=str(work), env=env,
                           capture_output=True, text=True, timeout=TIMEOUT)
        res = {"exit_code": p.returncode, "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:], "timed_out": False}
    except subprocess.TimeoutExpired as e:
        res = {"exit_code": None, "stdout": (e.stdout if isinstance(e.stdout, str) else "")[-4000:],
               "stderr": "TIMEOUT", "timed_out": True}
    res["seconds"] = round(time.time() - t0, 1)
    res["stdout"], res["stderr"] = redact(res["stdout"]), redact(res["stderr"])
    (run_dir / "exec_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res

def grade(scen, res):
    out, err = res["stdout"].strip(), res["stderr"]
    ok_exit = res["exit_code"] == 0
    no_1113 = "1113" not in (out + err)
    clean = "Traceback" not in out
    ev = f"exit={res['exit_code']} {res['seconds']}s :: {err[-200:]}"
    if scen == "plan-1113-fix":
        rows = [("脚本退出码为 0", ok_exit, ev),
                ("stdout 有非空模型回答且不是报错栈", len(out) > 0 and clean, f"stdout_len={len(out)}"),
                ("全程未出现 1113", no_1113, f"no_1113={no_1113}")]
    else:
        rows = [("脚本退出码为 0", ok_exit, ev),
                ("stdout 有 ≥50 字摘要且不是报错栈", len(out) >= 50 and clean, f"stdout_len={len(out)}"),
                ("全程未出现 1113", no_1113, f"no_1113={no_1113}")]
    return rows

SCEN = {"plan-1113-fix": False, "plan-longdoc-model": True}
summary = {}
for scen, needs_doc in SCEN.items():
    for cfg in ("with_skill", "without_skill"):
        scores = []
        for run_dir in sorted((ROOT / scen / cfg).glob("run-*")):
            res = run(run_dir, needs_doc)
            if res is None:
                print(f"{scen:20s} {cfg:14s} {run_dir.name}  NO main.py"); continue
            rows = grade(scen, res)
            exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
            passed = sum(1 for r in exp if r["passed"])
            g = {"expectations": exp,
                 "summary": {"passed": passed, "failed": len(exp)-passed, "total": len(exp),
                             "pass_rate": round(passed/len(exp), 3)},
                 "notes": "graded purely by executing the script with a real Coding Plan key"}
            (run_dir / "grading.json").write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
            scores.append(passed/len(exp))
            print(f"{scen:20s} {cfg:14s} {run_dir.name}  {passed}/{len(exp)}  ({res['seconds']}s)")
        if scores:
            mean = sum(scores)/len(scores)
            sd = (sum((s-mean)**2 for s in scores)/len(scores))**0.5
            summary[f"{scen}/{cfg}"] = {"runs": len(scores), "scores": [round(s,3) for s in scores],
                                        "mean": round(mean,3), "stdev": round(sd,3)}
(ROOT/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n=== summary ===")
for k,v in summary.items():
    print(f"{k:36s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  runs={v['scores']}")
