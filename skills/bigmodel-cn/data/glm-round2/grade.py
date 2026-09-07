# -*- coding: utf-8 -*-
"""GLM-5.3 执行器轮 · 第二版评分器。判定全部来自脚本执行真实 API 的结果。

用法： ZHIPUAI_API_KEY=... python3 grade.py [--regrade]
"""
import ast, json, os, re, shutil, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
KEY = os.environ.get("ZHIPUAI_API_KEY", "")
if not KEY:
    sys.exit("export ZHIPUAI_API_KEY first")
TIMEOUT = 300
CONTRACT_NO = "HT-2026-0917-XJ"
BATCH_PAT = re.compile(r"batch_[0-9A-Za-z]{6,}")
PDF_LIBS = {"PyPDF2", "pypdf", "pdfplumber", "fitz", "pymupdf", "pdfminer"}


def imports_pdf_lib(path):
    """真的 import 了本地解析库才算；注释里写"不使用 PyPDF2"不算。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] in PDF_LIBS for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in PDF_LIBS:
                return True
    return False


def code_only(path):
    """去掉注释与文档字符串，只留可执行代码——避免把说明文字当成实现。"""
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
               and isinstance(body[0].value.value, str):
                body.pop(0)
    return ast.unparse(tree)


def uses_upload_fileid(path):
    """是否真的走了「上传拿 file_id 再引用」而不是 base64 内联。"""
    code = code_only(path)
    hits_upload = "/files" in code or "paas/v4/files" in code
    hits_fileid = "file_id" in code
    inline = "file_data" in code or "base64" in code
    return hits_upload and hits_fileid and not inline



# 结构化匹配错误码，避免把 batch id 里凑巧出现的数字当成错误码（第一版就踩过这个坑）
def err_code(text, code):
    pat = re.compile(r'["\']?code["\']?\s*[:=]\s*["\']?' + code)
    return bool(pat.search(text))

KNOWN_MSG = {
    "1210": ["模型名称错误", "文件解析失败", "custom id 长度不足", "文件格式暂不支持"],
    "1214": ["input数组最大不得超过", "参数非法", "cannot both be empty"],
}

def hit_error(text, code):
    return err_code(text, code) or any(m in text for m in KNOWN_MSG.get(code, []))

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
    no_1210 = not hit_error(out + err, "1210")
    main = run_dir / "outputs" / "main.py"
    ev = f"exit={res['exit_code']} {res['seconds']}s :: {err[-200:]}"
    if scen == "batch-best-model":
        m = BATCH_PAT.search(out)
        model = re.search(r'"(glm-[0-9a-z.\-]+)"', code_only(main))
        rows = [("脚本退出码为 0", ok_exit, ev),
                ("stdout 出现 batch 任务 id", bool(m), f"matched={m.group(0) if m else None}"),
                ("全程未出现 1210（模型不在 Batch 白名单）", no_1210,
                 f"no_1210={no_1210} model={model.group(1) if model else '?'}")]
    else:
        upload = uses_upload_fileid(main)
        local = imports_pdf_lib(main)
        rows = [("脚本退出码为 0 且未在本地解析 PDF", ok_exit and not local, ev + f" local_parse={local}"),
                ("真的走了上传拿 file_id 复用的路径（非 base64 内联）", upload, f"upload_fileid={upload}"),
                (f"stdout 出现合同编号 {CONTRACT_NO}", CONTRACT_NO in out, f"found={CONTRACT_NO in out}"),
                ("全程未出现 1210（purpose 用错导致文件解析失败）", no_1210, f"no_1210={no_1210}")]
    return rows


SCEN = {"batch-best-model": ["comments.txt"], "pdf-reuse-fileid": ["contract.pdf"]}
summary = {}
for scen, fixtures in SCEN.items():
    for cfg in ("with_skill", "without_skill"):
        scores = []
        for run_dir in sorted((ROOT / scen / cfg).glob("run-*")):
            res = run(run_dir, fixtures)
            if res is None:
                print(f"{scen:18s} {cfg:14s} {run_dir.name}  NO main.py"); continue
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
            fail = [r["text"][:30] for r in exp if not r["passed"]]
            print(f"{scen:18s} {cfg:14s} {run_dir.name}  {passed}/{len(exp)}  ({res['seconds']}s) {fail if fail else ''}")
        if scores:
            mean = sum(scores)/len(scores)
            sd = (sum((s-mean)**2 for s in scores)/len(scores))**0.5
            summary[f"{scen}/{cfg}"] = {"runs": len(scores), "scores": [round(s, 3) for s in scores],
                                        "mean": round(mean, 3), "stdev": round(sd, 3)}
(ROOT/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n=== summary (executor: glm-5.3, 绕行路线已堵死) ===")
for k, v in summary.items():
    print(f"{k:36s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  runs={v['scores']}")
