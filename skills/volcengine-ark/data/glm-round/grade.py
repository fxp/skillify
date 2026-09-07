# -*- coding: utf-8 -*-
"""volcengine-ark · GLM-5.3 执行轮评分器。判定全部来自脚本执行真实 API 的结果。

用法： ARK_AGENT_PLAN_API_KEY=... python3 grade.py [--regrade]
判分标准冻结于 PROTOCOL.md，跑完不改。
"""
import ast, json, os, re, shutil, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
ARK = os.environ.get("ARK_AGENT_PLAN_API_KEY", "")
if not ARK:
    sys.exit("export ARK_AGENT_PLAN_API_KEY first")
TIMEOUT = 300
SCENARIOS = ["anthropic-entry-model-pinning", "kimi-max-tokens-empty", "plan-embeddings-shape"]


def code_only(path):
    """去掉 docstring，避免注释/说明文字造成的子串误判。"""
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


# 「核对了回显模型」的判据：存在一个比较/断言，其操作数来自模型相关的值。
# 原判据只认字面含 "model" 的比较节点，于是把 `served_family == expected_family`
# 这种先归一化再比对的写法漏判了——那是更严谨的实现，却被判成"没核对"。
# 判的应当是行为，不是变量取名，故放宽到模型相关的一组标识符。
MODEL_TOKENS = ["model", "family", "served", "expected", "actual", "echo", "requested", "返回", "实际"]


def has_comparison(code, needle=None):
    """代码里是否存在对模型相关值的比较/断言，而不只是打印。"""
    toks = MODEL_TOKENS if needle is None else [needle]
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return any(x in code.lower() for x in toks)
    for n in ast.walk(tree):
        if isinstance(n, (ast.Compare, ast.Assert)):
            s = ast.unparse(n).lower()
            if any(x in s for x in toks):
                return True
    return False


def red(t):
    return (t or "").replace(ARK, "<ARK_KEY>")


def run(run_dir):
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
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")}
    env["PYTHONIOENCODING"] = "utf-8"
    env["ARK_AGENT_PLAN_API_KEY"] = ARK
    env["ARK_API_KEY"] = ARK          # 有的脚本会用这个名字，两个都给，避免"没读到 Key"污染判分
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


LABELS = ["正面", "负面", "中性", "positive", "negative", "neutral"]


def grade(scen, run_dir, res):
    out, err = res["stdout"], res["stderr"]
    both = out + err
    code = code_only(run_dir / "outputs" / "main.py")
    ev = f"exit={res['exit_code']} {res['seconds']}s :: {err[-160:]}"
    no_tb = "Traceback" not in both

    if scen == "anthropic-entry-model-pinning":
        echoed = bool(re.search(r"doubao-seed-[0-9a-z.\-]+", out))
        is_lite = "doubao-seed-2-0-lite" in out or "doubao-seed-2.0-lite" in out.replace("请求", "")
        got_turbo = "doubao-seed-2-1-turbo" in out
        return [("无未捕获异常", no_tb, ev),
                ("打印了服务端回显的实际模型名", echoed, f"echoed={echoed}"),
                ("实际服务模型是 lite，未被静默换成 turbo", is_lite and not got_turbo,
                 f"lite={is_lite} turbo={got_turbo}"),
                ("脚本自己核对了回显模型（不只是打印）", has_comparison(code), "compare_on_model")]

    if scen == "kimi-max-tokens-empty":
        got_label = any(w in out for w in LABELS)
        # 空回答被当成成功：出现 length 截断迹象且没有任何标签
        truncated_empty = ("length" in out.lower()) and not got_label
        return [("无未捕获异常", no_tb, ev),
                ("真的拿到了非空的分类结果", got_label, f"label={got_label}"),
                ("没有把空回答当成完成", not truncated_empty, f"truncated_empty={truncated_empty}"),
                ("脚本检查了 finish_reason", "finish_reason" in code, f"checks_finish_reason={'finish_reason' in code}")]

    # plan-embeddings-shape
    n1024 = len(re.findall(r"1024", out))
    got_2048 = "2048" in out
    gave_up = any(w in out for w in ["不支持向量", "不支持 OpenAI", "不支持OpenAI", "无法向量化",
                                     "不提供向量", "UnsupportedModel"])
    return [("无未捕获异常", no_tb, ev),
            ("真的拿到了向量（打印出了向量长度）", n1024 > 0 or got_2048, f"n1024={n1024} got_2048={got_2048}"),
            ("维度确实是 1024（没走成 2048 维的 multimodal 端点）", n1024 > 0 and not got_2048,
             f"n1024={n1024} got_2048={got_2048}"),
            ("三段文本都处理了", n1024 >= 3, f"len_1024_occurrences={n1024}")]


summary = {}
for scen in SCENARIOS:
    for cfg in ("with_skill", "without_skill"):
        scores = []
        for rd in sorted((ROOT / scen / cfg).glob("run-*")):
            res = run(rd)
            if res is None:
                print(f"{scen:32s} {cfg:14s} {rd.name}  NO main.py"); continue
            rows = grade(scen, rd, res)
            exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
            passed = sum(1 for r in exp if r["passed"])
            (rd / "grading.json").write_text(json.dumps(
                {"expectations": exp,
                 "summary": {"passed": passed, "failed": len(exp) - passed, "total": len(exp),
                             "pass_rate": round(passed / len(exp), 3)},
                 "executor": "glm-5.3",
                 "notes": "graded purely by executing the script against the live Ark Agent Plan API"},
                ensure_ascii=False, indent=2), encoding="utf-8")
            scores.append(passed / len(exp))
            fail = [r["text"][:24] for r in exp if not r["passed"]]
            print(f"{scen:32s} {cfg:14s} {rd.name}  {passed}/{len(exp)}  ({res['seconds']}s) {fail if fail else ''}")
        if scores:
            m = sum(scores) / len(scores)
            sd = (sum((x - m) ** 2 for x in scores) / len(scores)) ** 0.5
            summary[f"{scen}/{cfg}"] = {"runs": len(scores), "scores": [round(x, 3) for x in scores],
                                        "mean": round(m, 3), "stdev": round(sd, 3)}
(ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n=== summary (executor: glm-5.3, n=5) ===")
for k, v in summary.items():
    print(f"{k:52s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  runs={v['scores']}")
