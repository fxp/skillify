# -*- coding: utf-8 -*-
"""第三轮评分器：判定全部来自脚本执行真实 API 的结果。

用法： ZHIPUAI_API_KEY=... python3 grade.py [--regrade]
"""
import ast, json, os, re, shutil, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
KEY = os.environ.get("ZHIPUAI_API_KEY", "")
if not KEY:
    sys.exit("export ZHIPUAI_API_KEY first")
TIMEOUT = 300
URL_PAT = re.compile(r"https?://[^\s\"'）)\]，,、]{8,}")


def code_only(path):
    """去掉注释与文档字符串，只留可执行代码。"""
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


def reads_api_sources(path):
    """来源是否取自接口返回：读了响应里的 web_search / search_result 数组，
    而不是让模型在正文里自己编链接。"""
    code = code_only(path)
    return ("web_search" in code and re.search(r"\[\s*['\"]web_search['\"]\s*\]|get\(\s*['\"]web_search['\"]", code) is not None) \
        or re.search(r"\[\s*['\"]search_result['\"]\s*\]|get\(\s*['\"]search_result['\"]", code) is not None



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
        res = {"exit_code": p.returncode, "stdout": p.stdout[-8000:], "stderr": p.stderr[-4000:], "timed_out": False}
    except subprocess.TimeoutExpired as e:
        res = {"exit_code": None, "stdout": (e.stdout if isinstance(e.stdout, str) else "")[-8000:],
               "stderr": "TIMEOUT", "timed_out": True}
    res["seconds"] = round(time.time() - t0, 1)
    res["stdout"], res["stderr"] = redact(res["stdout"]), redact(res["stderr"])
    (run_dir / "exec_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def grade(scen, run_dir, res):
    out, err = res["stdout"], res["stderr"]
    ok_exit = res["exit_code"] == 0
    main = run_dir / "outputs" / "main.py"
    ev = f"exit={res['exit_code']} {res['seconds']}s :: {err[-200:]}"
    if scen == "cited-web-answer":
        urls = URL_PAT.findall(out)
        from_api = reads_api_sources(main)
        rows = [("脚本退出码为 0", ok_exit, ev),
                ("stdout 至少出现 2 条 http(s) 来源链接", len(urls) >= 2, f"找到 {len(urls)} 条: {urls[:2]}"),
                ("来源取自接口返回（读了 web_search / search_result 数组）", from_api,
                 f"reads_api_sources={from_api}")]
    else:
        vec = None
        for cand in list((run_dir / "work").glob("vectors.json")) + list((run_dir / "work").glob("**/vectors.json")):
            try:
                vec = json.loads(cand.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

        def vec_count(v):
            if isinstance(v, list):
                return len(v)
            if isinstance(v, dict):
                for k in ("vectors", "embeddings", "data", "items"):
                    if isinstance(v.get(k), list):
                        return len(v[k])
            return 0

        n = vec_count(vec)
        no_1214 = not hit_error(out + err, "1214")
        # top-3：stdout 里应出现来自 faq.txt 的原文行
        faq = (ROOT / "fixtures" / "faq.txt").read_text(encoding="utf-8").splitlines()
        hits = sum(1 for line in faq if line.strip() and line.strip() in out)
        rows = [("脚本退出码为 0", ok_exit, ev),
                ("vectors.json 含 150 条向量", n == 150, f"实际 {n} 条"),
                ("全程未出现 1214（embeddings 单次最多 64 条）", no_1214, f"no_1214={no_1214}"),
                ("stdout 打印了 top-3 检索结果（命中 faq 原文）", hits >= 3, f"命中 {hits} 条原文")]
    return rows


SCEN = {"cited-web-answer": [], "rag-index-embeddings": ["faq.txt"]}
summary = {}
for scen, fixtures in SCEN.items():
    for cfg in ("with_skill", "without_skill"):
        scores = []
        for run_dir in sorted((ROOT / scen / cfg).glob("run-*")):
            res = run(run_dir, fixtures)
            if res is None:
                print(f"{scen:22s} {cfg:14s} {run_dir.name}  NO main.py"); continue
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
            fail = [r["text"][:26] for r in exp if not r["passed"]]
            print(f"{scen:22s} {cfg:14s} {run_dir.name}  {passed}/{len(exp)}  ({res['seconds']}s) {fail if fail else ''}")
        if scores:
            mean = sum(scores)/len(scores)
            sd = (sum((s-mean)**2 for s in scores)/len(scores))**0.5
            summary[f"{scen}/{cfg}"] = {"runs": len(scores), "scores": [round(s, 3) for s in scores],
                                        "mean": round(mean, 3), "stdev": round(sd, 3)}
(ROOT/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n=== summary (executor: glm-5.3, n=5) ===")
for k, v in summary.items():
    print(f"{k:40s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  runs={v['scores']}")
