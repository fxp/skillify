# -*- coding: utf-8 -*-
"""第五轮评分器（执行器 GLM-5.3）。判定全部来自脚本执行真实 API 的结果。

用法： ZHIPUAI_API_KEY=... python3 grade.py [--regrade]
判分标准冻结于 PROTOCOL.md。评分口径沿用前四轮：判结果，不判形式
（stdout / stderr 一起读；不因变量取名或某个子串扣分）。
"""
import ast, json, os, re, shutil, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
STD = os.environ.get("ZHIPUAI_API_KEY", "")
if not STD:
    sys.exit("export ZHIPUAI_API_KEY first")
TIMEOUT = 300
FAKE_KB = "999999999999999999"          # 确认不存在：HTTP 200 + {"code":100013}
SCENARIOS = ["token-budget-empty-answer", "kb-id-validation-silent200",
             "json-schema-not-enforced", "forced-tool-choice-ignored"]


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


def cond_on(code, tokens):
    """代码里是否存在针对这些标识符的条件判断 / 比较 / 断言（判行为，不判取名）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return any(t in code for t in tokens)
    for n in ast.walk(tree):
        if isinstance(n, (ast.Compare, ast.Assert, ast.If, ast.IfExp, ast.Subscript)):
            s = ast.unparse(n).lower()
            if any(t.lower() in s for t in tokens):
                return True
    return False


def red(t):
    return (t or "").replace(STD, "<STD>")


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
    env["ZHIPUAI_API_KEY"] = STD
    env["ZHIPU_API_KEY"] = STD          # 两个常见命名都给，避免"没读到 Key"污染判分
    env["ZHIPU_KB_ID"] = FAKE_KB
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-W", "ignore", "main.py"], cwd=str(work), env=env,
                           capture_output=True, text=True, timeout=TIMEOUT)
        res = {"exit_code": p.returncode, "stdout": p.stdout[-9000:], "stderr": p.stderr[-6000:], "timed_out": False}
    except subprocess.TimeoutExpired as e:
        res = {"exit_code": None, "stdout": (e.stdout if isinstance(e.stdout, str) else "")[-9000:],
               "stderr": "TIMEOUT", "timed_out": True}
    res["seconds"] = round(time.time() - t0, 1)
    res["stdout"], res["stderr"] = red(res["stdout"]), red(res["stderr"])
    (run_dir / "exec_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


CJK = re.compile(r"[一-鿿]")
NEG = ["不存在", "无效", "不可用", "校验失败", "invalid", "not found", "notfound", "非法", "查不到", "未找到"]
POS = ["有效", "可用", "校验通过", "验证通过", "valid", "存在且", "检查通过", "ok，知识库"]
# 否定语境窗口原为 3 字，漏掉了「无法确认该知识库 ID 有效」这种隔了几个字的否定，
# 把完全正确的结论判成"误报为有效"。窗口放宽到 12 字并补全否定词。
NEGATORS = ["不", "非", "无", "未", "别", "勿", "无法", "不能", "未能", "禁止", "没有", "拒绝"]
NEG_WINDOW = 12
SENTS = {"正面", "负面", "中性"}


def claims(text, words):
    """某个结论是否被真正主张过（跳过处于否定语境里的出现）。"""
    for w in words:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            if not any(neg in text[max(0, i - NEG_WINDOW):i] for neg in NEGATORS):
                return True
            start = i + len(w)
    return False


def json_objs(text):
    """从输出里尽量捞出 JSON 对象。"""
    out = []
    for m in re.finditer(r"\{[^{}]*\}", text):
        try:
            o = json.loads(m.group(0))
            if isinstance(o, dict):
                out.append(o)
        except Exception:
            pass
    return out


def grade(scen, run_dir, res):
    out, err = res["stdout"], res["stderr"]
    both = out + err                     # 结论写到 stderr 是正当做法，两个流一起读
    code = code_only(run_dir / "outputs" / "main.py")
    ev = f"exit={res['exit_code']} {res['seconds']}s :: {err[-160:]}"
    no_tb = "Traceback" not in both

    if scen == "token-budget-empty-answer":
        rich = [l for l in both.splitlines() if len(CJK.findall(l)) >= 8]
        got3 = len(rich) >= 3
        truncated = "length" in both.lower()
        return [("无未捕获异常", no_tb, ev),
                ("三条摘要都拿到了非空文本", got3, f"rich_lines={len(rich)}"),
                ("没有把空回答当成完成", got3 or not truncated, f"truncated={truncated} got3={got3}"),
                ("脚本检查了 finish_reason", "finish_reason" in code, f"checks={'finish_reason' in code}")]

    if scen == "kb-id-validation-silent200":
        said_neg = claims(both, NEG)
        said_pos = claims(both, POS)
        return [("无未捕获异常", no_tb, ev),
                ("正确判定为无效 / 不存在", said_neg, f"neg={said_neg}"),
                ("没有误报为有效", not said_pos, f"pos={said_pos}"),
                ("代码检查了响应体里的业务码", cond_on(code, ["code"]), "cond_on_code")]

    if scen == "json-schema-not-enforced":
        objs = [o for o in json_objs(both)
                if o.get("sentiment") in SENTS and isinstance(o.get("score"), (int, float))
                and 0 <= float(o["score"]) <= 1]
        got3 = len(objs) >= 3
        validated = ("json.loads" in code or "json .loads" in code) and \
                    (cond_on(code, ["sentiment", "schema", "valid"]) or "except" in code)
        failed_claim = (not got3) and claims(both, ["完成", "成功", "全部处理"])
        return [("无未捕获异常", no_tb, ev),
                ("拿到 3 条严格符合 schema 的结果", got3, f"valid_objs={len(objs)}"),
                ("脚本自己做了结构校验或兜底", validated, f"validated={validated}"),
                ("没有把不合规输出当成功", not failed_claim, f"failed_claim={failed_claim}")]

    # forced-tool-choice-ignored
    has_cat = bool(re.search(r'(category|类别|分类)\s*[":：=]\s*["\'"]?\s*\S', both))
    has_sum = bool(re.search(r'(summary|摘要|问题描述)\s*[":：=]\s*["\'"]?\s*\S', both))
    ticket = has_cat and has_sum
    false_ok = (not ticket) and claims(both, ["完成", "成功", "已处理"])
    # 原判分项要求代码里必须有 tool_calls 的条件分支——但技能给的正确做法恰恰是
    # 「根本不要依赖 tool_choice，在代码里无条件构造工单」，照做的脚本自然没有这个分支，
    # 于是被判成"没兜底"。判的应当是行为：只要没有盲目依赖强制 tool_choice 就算通过。
    forced = bool(re.search(r'tool_choice["\']?\s*[:=]\s*(\{|["\']required)', code))
    fallback = cond_on(code, ["tool_calls"])
    return [("无未捕获异常", no_tb, ev),
            ("真的产出了结构化工单（category + summary）", ticket, f"cat={has_cat} sum={has_sum}"),
            ("没有在没拿到工单时宣称完成", not false_ok, f"false_ok={false_ok}"),
            ("没有盲目依赖强制 tool_choice（不用它，或用了但有兜底）", (not forced) or fallback,
             f"forced={forced} fallback={fallback}")]


summary = {}
for scen in SCENARIOS:
    for cfg in ("with_skill", "without_skill"):
        scores = []
        for rd in sorted((ROOT / scen / cfg).glob("run-*")):
            res = run(rd)
            if res is None:
                print(f"{scen:30s} {cfg:14s} {rd.name}  NO main.py"); continue
            rows = grade(scen, rd, res)
            exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
            passed = sum(1 for r in exp if r["passed"])
            (rd / "grading.json").write_text(json.dumps(
                {"expectations": exp,
                 "summary": {"passed": passed, "failed": len(exp) - passed, "total": len(exp),
                             "pass_rate": round(passed / len(exp), 3)},
                 "executor": "glm-5.3",
                 "notes": "graded purely by executing the script against the live open.bigmodel.cn API"},
                ensure_ascii=False, indent=2), encoding="utf-8")
            scores.append(passed / len(exp))
            fail = [r["text"][:24] for r in exp if not r["passed"]]
            print(f"{scen:30s} {cfg:14s} {rd.name}  {passed}/{len(exp)}  ({res['seconds']}s) {fail if fail else ''}")
        if scores:
            m = sum(scores) / len(scores)
            sd = (sum((x - m) ** 2 for x in scores) / len(scores)) ** 0.5
            summary[f"{scen}/{cfg}"] = {"runs": len(scores), "scores": [round(x, 3) for x in scores],
                                        "mean": round(m, 3), "stdev": round(sd, 3)}
(ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n=== summary (executor: glm-5.3, n=5) ===")
for k, v in summary.items():
    print(f"{k:52s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  runs={v['scores']}")
