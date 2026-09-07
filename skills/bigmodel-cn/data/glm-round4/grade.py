# -*- coding: utf-8 -*-
"""第四轮评分器（执行器 GLM-5.3）。判定全部来自脚本执行真实 API 的结果。

用法： ZHIPUAI_API_KEY=... GLM_CODING_PLAN_API_KEY=... python3 grade.py [--regrade]
"""
import ast, json, os, re, shutil, subprocess, sys, time, pathlib, requests

ROOT = pathlib.Path(__file__).resolve().parent
STD = os.environ.get("ZHIPUAI_API_KEY", "")
PLAN = os.environ.get("GLM_CODING_PLAN_API_KEY", "")
if not STD or not PLAN:
    sys.exit("export ZHIPUAI_API_KEY and GLM_CODING_PLAN_API_KEY first")
TIMEOUT = 300

ENV_FOR = {"plan-1113-fix": {"GLM_KEY": PLAN},
           "kb-upload-readiness": {"ZHIPUAI_API_KEY": STD},
           "async-model-pinning": {"ZHIPUAI_API_KEY": STD}}
FIXTURES = {"kb-upload-readiness": ["faq.txt"]}


def code_only(path):
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = getattr(n, "body", [])
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
               and isinstance(b[0].value.value, str):
                b.pop(0)
    return ast.unparse(tree)


def err_code(text, code):
    return bool(re.search(r'["\']?code["\']?\s*[:=]\s*["\']?' + code, text))


KNOWN = {"1113": ["余额不足", "无可用资源包"]}


def hit_error(text, code):
    return err_code(text, code) or any(m in text for m in KNOWN.get(code, []))


def red(t):
    return (t or "").replace(STD, "<STD>").replace(PLAN, "<PLAN>")


def run(scen, run_dir):
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
    for f in FIXTURES.get(scen, []):
        shutil.copy(ROOT / "fixtures" / f, work / f)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")}
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(ENV_FOR[scen])
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-W", "ignore", "main.py"], cwd=str(work), env=env,
                           capture_output=True, text=True, timeout=TIMEOUT)
        res = {"exit_code": p.returncode, "stdout": p.stdout[-8000:], "stderr": p.stderr[-6000:], "timed_out": False}
    except subprocess.TimeoutExpired as e:
        res = {"exit_code": None, "stdout": (e.stdout if isinstance(e.stdout, str) else "")[-8000:],
               "stderr": "TIMEOUT", "timed_out": True}
    res["seconds"] = round(time.time() - t0, 1)
    res["stdout"], res["stderr"] = red(res["stdout"]), red(res["stderr"])
    (run_dir / "exec_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def kb_truth():
    """评分器独立验证：本账号的知识库向量化到底能不能用。
    自己建库、传一份文档、查 embedding_stat，再清理。返回 True=可用。"""
    APP = "https://open.bigmodel.cn/api/llm-application/open"
    H = {"Authorization": f"Bearer {STD}"}
    try:
        kb = requests.post(f"{APP}/knowledge", headers=H,
                           json={"embedding_id": 11, "name": "grader-truth-check"}, timeout=90).json()["data"]["id"]
        import io
        r = requests.post(f"{APP}/document/upload_document/{kb}", headers=H,
                          files={"files": ("t.txt", io.BytesIO("发票需在 7 个工作日内申请。".encode()), "text/plain")},
                          timeout=120).json()
        did = r["data"]["successInfos"][0]["documentId"]
        stat = None
        for _ in range(8):
            time.sleep(8)
            stat = requests.get(f"{APP}/document/{did}", headers=H, timeout=60).json().get("data", {}).get("embedding_stat")
            if stat in (1, 2):
                break
        requests.delete(f"{APP}/document/{did}", headers=H, timeout=60)
        requests.delete(f"{APP}/knowledge/{kb}", headers=H, timeout=60)
        return stat == 1, stat
    except Exception as e:
        return None, f"exc:{str(e)[:60]}"


KB_USABLE, KB_STAT = None, None
SUCCESS_WORDS = ["成功", "完成", "可以检索", "可检索", "就绪", "ready", "success"]
FAIL_WORDS = ["失败", "不可用", "无法检索", "检索不到", "未就绪", "错误", "fail", "error", "不能用"]


def grade(scen, run_dir, res):
    out, err = res["stdout"], res["stderr"]
    both = out + err
    ok_exit = res["exit_code"] == 0
    main = run_dir / "outputs" / "main.py"
    code = code_only(main)
    ev = f"exit={res['exit_code']} {res['seconds']}s :: {err[-180:]}"

    if scen == "plan-1113-fix":
        return [("脚本退出码为 0", ok_exit, ev),
                ("stdout 有非空模型回答且不是报错栈", len(out.strip()) > 0 and "Traceback" not in out, f"stdout_len={len(out.strip())}"),
                ("全程未出现 1113", not hit_error(both, "1113"), f"no_1113={not hit_error(both,'1113')}")]

    if scen == "kb-upload-readiness":
        # 说明：知识库向量化经实测是「间歇性」的——同一账号有时成功有时 embedding_stat=2。
        # 因此不能拿评分器某一刻的全局真值去判每一次运行，只能判「结论是否有该次运行自身的证据支撑」。
        checks_stat = "embedding_stat" in code
        tail = out[-1200:]
        claims_ok = any(w in tail for w in SUCCESS_WORDS)
        reports_fail = any(w in tail for w in FAIL_WORDS)
        # 该次运行自身观测到的证据
        saw_retrieved = ("内容片段" in out or "检索到" in out
                         or bool(re.search(r"命中\s*[1-9]", out)))
        saw_failure = ("embedding_stat" in out and re.search(r"embedding_stat[^0-9]{0,4}2", out) is not None) \
            or "failInfo" in out or "知识不可用" in out or "文档损坏" in out
        if claims_ok and not reports_fail:
            verdict_ok = saw_retrieved          # 宣称成功，必须真的检索到过内容
            note = f"宣称成功；自身证据 检索到内容={saw_retrieved}"
        elif reports_fail:
            verdict_ok = saw_failure or not saw_retrieved   # 报失败，须有失败依据
            note = f"报告不可用；自身证据 失败信号={saw_failure}"
        else:
            verdict_ok = False
            note = "未给出明确结论"
        cleaned = ("已删除" in out) or ("清理" in out and "完成" in out) or ("已清理" in out)
        return [("无未捕获异常（非零退出码若属主动报警则不扣分）", "Traceback" not in both,
                 ev + f" traceback={'Traceback' in both}"),
                ("代码真的读取了 embedding_stat 做就绪校验", checks_stat, f"checks_embedding_stat={checks_stat}"),
                ("结论有该次运行自身的证据支撑（不空口宣称成功）", verdict_ok, note),
                ("按要求清理了临时知识库", cleaned, f"cleaned={cleaned}")]

    # async-model-pinning
    asked = "glm-4.6" in out
    actual = "glm-4.7" in out
    mismatch = any(w in out for w in ["不一致", "不匹配", "mismatch", "警告", "报警", "WARN", "⚠"])
    # 检出不一致后以非零退出码报警是正确工程行为，不能按「退出码必须为 0」扣分
    return [("无未捕获异常（非零退出码若属主动报警则不扣分）", "Traceback" not in both,
             ev + f" traceback={'Traceback' in both}"),
            ("stdout 同时出现请求模型 glm-4.6 与实际模型 glm-4.7", asked and actual, f"asked={asked} actual={actual}"),
            ("正确检出模型不一致并报警", mismatch, f"flagged={mismatch}")]


summary = {}
for scen in ENV_FOR:
    if scen == "kb-upload-readiness" and KB_USABLE is None:
        KB_USABLE, KB_STAT = kb_truth()
        print(f"[评分器独立核实] 本账号知识库向量化可用性 = {KB_USABLE}（embedding_stat={KB_STAT}）\n")
    for cfg in ("with_skill", "without_skill"):
        scores = []
        for rd in sorted((ROOT / scen / cfg).glob("run-*")):
            res = run(scen, rd)
            if res is None:
                print(f"{scen:22s} {cfg:14s} {rd.name}  NO main.py"); continue
            rows = grade(scen, rd, res)
            exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
            passed = sum(1 for r in exp if r["passed"])
            (rd / "grading.json").write_text(json.dumps(
                {"expectations": exp,
                 "summary": {"passed": passed, "failed": len(exp)-passed, "total": len(exp),
                             "pass_rate": round(passed/len(exp), 3)},
                 "executor": "glm-5.3",
                 "notes": "graded purely by executing the script against the live API"},
                ensure_ascii=False, indent=2), encoding="utf-8")
            scores.append(passed/len(exp))
            fail = [r["text"][:26] for r in exp if not r["passed"]]
            print(f"{scen:22s} {cfg:14s} {rd.name}  {passed}/{len(exp)}  ({res['seconds']}s) {fail if fail else ''}")
        if scores:
            m = sum(scores)/len(scores)
            sd = (sum((x-m)**2 for x in scores)/len(scores))**0.5
            summary[f"{scen}/{cfg}"] = {"runs": len(scores), "scores": [round(x, 3) for x in scores],
                                        "mean": round(m, 3), "stdev": round(sd, 3)}
(ROOT/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n=== summary (executor: glm-5.3, n=5) ===")
for k, v in summary.items():
    print(f"{k:44s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  runs={v['scores']}")
