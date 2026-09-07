# -*- coding: utf-8 -*-
"""GLM-5.3 执行器轮评分器：判定全部来自脚本执行真实 API 的结果。

用法： ZHIPUAI_API_KEY=... python3 grade.py
"""
import json, os, re, shutil, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
KEY = os.environ.get("ZHIPUAI_API_KEY", "")
if not KEY:
    sys.exit("export ZHIPUAI_API_KEY first")
TIMEOUT = 300
CONTRACT_NO = "HT-2026-0917-XJ"
AMOUNT_PAT = re.compile(r"4[,，]?870[,，]?000|4870000|487\s*万|肆佰捌拾柒万")
BATCH_PAT = re.compile(r"batch_[0-9A-Za-z]{6,}")

PDF_LIBS = {"PyPDF2", "pypdf", "pdfplumber", "fitz", "pymupdf", "pdfminer"}

def imports_pdf_lib(path):
    """真的 import 了本地 PDF 解析库才算数——注释里写'不使用 PyPDF2'不算。"""
    import ast
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in PDF_LIBS:
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in PDF_LIBS:
                return True
    return False


def redact(s):
    return (s or "").replace(KEY, "<KEY>")

def run(run_dir, fixtures):
    main = run_dir / "outputs" / "main.py"
    if not main.exists():
        return None
    cached = run_dir / "exec_result.json"
    if "--regrade" in sys.argv and cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    work = run_dir / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copy(main, work / "main.py")
    for f in fixtures:
        shutil.copy(ROOT / "fixtures" / f, work / f)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")}
    env["PYTHONIOENCODING"] = "utf-8"
    env["ZHIPUAI_API_KEY"] = KEY
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-W", "ignore", "main.py"], cwd=str(work), env=env,
                           capture_output=True, text=True, timeout=TIMEOUT)
        res = {"exit_code": p.returncode, "stdout": p.stdout[-6000:], "stderr": p.stderr[-4000:], "timed_out": False}
    except subprocess.TimeoutExpired as e:
        res = {"exit_code": None, "stdout": (e.stdout if isinstance(e.stdout, str) else "")[-6000:],
               "stderr": "TIMEOUT", "timed_out": True}
    res["seconds"] = round(time.time() - t0, 1)
    res["stdout"], res["stderr"] = redact(res["stdout"]), redact(res["stderr"])
    (run_dir / "exec_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res

def grade(scen, run_dir, res):
    out, err = res["stdout"], res["stderr"]
    both = out + err
    ok_exit = res["exit_code"] == 0
    no_1210 = "1210" not in both
    ev = f"exit={res['exit_code']} {res['seconds']}s :: {err[-200:]}"
    if scen == "batch-pipeline":
        m = BATCH_PAT.search(out)
        rows = [("脚本退出码为 0", ok_exit, ev),
                ("stdout 出现 batch 任务 id", bool(m), f"matched={m.group(0) if m else None}"),
                ("全程未出现 1210（模型白名单 / custom_id 长度）", no_1210, f"no_1210={no_1210}")]
    else:
        has_no = CONTRACT_NO in out
        has_amt = bool(AMOUNT_PAT.search(out))
        local = imports_pdf_lib(run_dir / "outputs" / "main.py")
        rows = [("脚本退出码为 0 且未在本地解析 PDF", ok_exit and not local, ev + f" local_parse={local}"),
                (f"stdout 出现合同编号 {CONTRACT_NO}", has_no, f"found={has_no}"),
                ("stdout 出现合同总金额", has_amt, f"found={has_amt}")]
    return rows

SCEN = {"batch-pipeline": ["comments.txt"], "pdf-contract": ["contract.pdf"]}
summary = {}
for scen, fixtures in SCEN.items():
    for cfg in ("with_skill", "without_skill"):
        scores = []
        for run_dir in sorted((ROOT / scen / cfg).glob("run-*")):
            res = run(run_dir, fixtures)
            if res is None:
                print(f"{scen:16s} {cfg:14s} {run_dir.name}  NO main.py"); continue
            rows = grade(scen, run_dir, res)
            exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
            passed = sum(1 for r in exp if r["passed"])
            g = {"expectations": exp,
                 "summary": {"passed": passed, "failed": len(exp)-passed, "total": len(exp),
                             "pass_rate": round(passed/len(exp), 3)},
                 "executor": "glm-5.3",
                 "notes": "graded purely by executing the script against the live API"}
            (run_dir / "grading.json").write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
            scores.append(passed/len(exp))
            print(f"{scen:16s} {cfg:14s} {run_dir.name}  {passed}/{len(exp)}  ({res['seconds']}s)")
        if scores:
            mean = sum(scores)/len(scores)
            sd = (sum((s-mean)**2 for s in scores)/len(scores))**0.5
            summary[f"{scen}/{cfg}"] = {"runs": len(scores), "scores": [round(s,3) for s in scores],
                                        "mean": round(mean,3), "stdev": round(sd,3)}
(ROOT/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n=== summary (executor: glm-5.3) ===")
for k, v in summary.items():
    print(f"{k:34s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  runs={v['scores']}")
