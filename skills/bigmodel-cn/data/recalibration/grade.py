# -*- coding: utf-8 -*-
"""校准轮评分器：全部判定来自脚本执行结果，无人工判断。

用法：
  ZHIPUAI_API_KEY=... python3 grade.py

对 recalibration/<scenario>/<config>/run-N/outputs/main.py 逐个执行，
按 PROTOCOL.md 固定的判分标准打分，写 grading.json + exec_result.json。
Key 只通过环境变量注入，不写入任何文件。
"""
import json, os, re, shutil, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
KEY = os.environ.get("ZHIPUAI_API_KEY", "")
if not KEY:
    sys.exit("export ZHIPUAI_API_KEY first")
FIXTURE = ROOT / "fixtures" / "feedback.txt"
TIMEOUT = 300


def redact(s):
    return (s or "").replace(KEY, "<KEY>")


def run(run_dir, argv_extra, needs_fixture):
    main = run_dir / "outputs" / "main.py"
    if not main.exists():
        return None
    work = run_dir / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copy(main, work / "main.py")
    if needs_fixture:
        shutil.copy(FIXTURE, work / "feedback.txt")

    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")}
    env["PYTHONIOENCODING"] = "utf-8"
    env["ZHIPUAI_API_KEY"] = KEY

    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-W", "ignore", "main.py", *argv_extra],
                           cwd=str(work), env=env, capture_output=True,
                           text=True, timeout=TIMEOUT)
        res = {"exit_code": p.returncode, "stdout": p.stdout[-4000:],
               "stderr": p.stderr[-4000:], "timed_out": False}
    except subprocess.TimeoutExpired as e:
        res = {"exit_code": None,
               "stdout": (e.stdout if isinstance(e.stdout, str) else "")[-4000:],
               "stderr": "TIMEOUT", "timed_out": True}
    res["seconds"] = round(time.time() - t0, 1)
    res["stdout"] = redact(res["stdout"])
    res["stderr"] = redact(res["stderr"])
    (run_dir / "exec_result.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def grade_json_extraction(run_dir, res):
    work = run_dir / "work"
    ok_exit = res["exit_code"] == 0
    out = None
    for cand in list(work.glob("out.json")) + list(work.glob("**/out.json")):
        try:
            out = json.loads(cand.read_text(encoding="utf-8"))
            break
        except Exception:
            pass
    parsed = out is not None
    is_arr8 = isinstance(out, list) and len(out) == 8
    want = {"name", "issue_type", "urgency"}
    if isinstance(out, list) and out:
        key_ok = sum(1 for r in out if isinstance(r, dict) and set(r.keys()) == want)
        urg_ok = sum(1 for r in out if isinstance(r, dict)
                     and str(r.get("urgency", "")).lower() in ("low", "medium", "high"))
        key_frac, urg_frac = key_ok / len(out), urg_ok / len(out)
    else:
        key_ok = urg_ok = 0
        key_frac = urg_frac = 0.0

    ev = f"exit={res['exit_code']} {res['seconds']}s :: {redact(res['stderr'])[-200:]}"
    rows = [
        ("脚本退出码为 0", ok_exit, ev),
        ("out.json 存在且是合法 JSON", parsed, f"parsed={parsed}"),
        ("顶层是数组且长度为 8", is_arr8,
         f"type={type(out).__name__} len={len(out) if isinstance(out, list) else 'n/a'}"),
        ("每条记录的键恰好是 name/issue_type/urgency", key_frac >= 0.999,
         f"{key_ok}/{len(out) if isinstance(out, list) else 0} 条合格"),
        ("每条记录 urgency ∈ low|medium|high", urg_frac >= 0.999,
         f"{urg_ok}/{len(out) if isinstance(out, list) else 0} 条合格"),
    ]
    return rows, {"key_frac": round(key_frac, 3), "urg_frac": round(urg_frac, 3)}


def grade_forced_tool(run_dir, res):
    ok_exit = res["exit_code"] == 0
    marker = "[TOOL] lookup_order called" in (res["stderr"] + res["stdout"])
    answer = len(res["stdout"].strip()) > 0 and "Traceback" not in res["stdout"]
    ev = f"exit={res['exit_code']} {res['seconds']}s :: stderr_tail={redact(res['stderr'])[-160:]}"
    rows = [
        ("脚本退出码为 0", ok_exit, ev),
        ("工具真的被调用（stderr 出现 [TOOL] lookup_order called）", marker,
         f"marker_found={marker}"),
        ("stdout 有非空最终回答且不是报错栈", answer,
         f"stdout_len={len(res['stdout'].strip())}"),
    ]
    return rows, {}


SCENARIOS = {
    "json-extraction": (grade_json_extraction, [], True),
    "forced-tool-call": (grade_forced_tool, ["今天北京天气怎么样？"], False),
}

summary = {}
for scen, (grader, argv, fixture) in SCENARIOS.items():
    for cfg in ("with_skill", "without_skill"):
        scores = []
        for run_dir in sorted((ROOT / scen / cfg).glob("run-*")):
            res = run(run_dir, argv, fixture)
            if res is None:
                print(f"{scen:18s} {cfg:14s} {run_dir.name}  NO main.py")
                continue
            rows, extra = grader(run_dir, res)
            exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
            passed = sum(1 for r in exp if r["passed"])
            g = {"expectations": exp,
                 "summary": {"passed": passed, "failed": len(exp) - passed,
                             "total": len(exp), "pass_rate": round(passed / len(exp), 3)},
                 "extra": extra,
                 "notes": "graded purely by executing the script against the live API"}
            (run_dir / "grading.json").write_text(
                json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
            scores.append(passed / len(exp))
            print(f"{scen:18s} {cfg:14s} {run_dir.name}  {passed}/{len(exp)}  {extra}")
        if scores:
            mean = sum(scores) / len(scores)
            var = sum((s - mean) ** 2 for s in scores) / len(scores)
            summary[f"{scen}/{cfg}"] = {
                "runs": len(scores), "scores": [round(s, 3) for s in scores],
                "mean": round(mean, 3), "stdev": round(var ** 0.5, 3)}

(ROOT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n=== summary ===")
for k, v in summary.items():
    print(f"{k:34s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  runs={v['scores']}")
