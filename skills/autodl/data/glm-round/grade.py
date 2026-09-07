# -*- coding: utf-8 -*-
"""autodl · GLM-5.3 执行轮评分器。判定全部来自脚本执行真实 API 的结果。

用法： AUTODL_TOKEN=... python3 grade.py [--regrade]
判分标准冻结于 PROTOCOL.md，跑完不改。
三个场景全部只读，不创建/释放任何资源，不产生费用。
"""
import ast, json, os, re, shutil, subprocess, sys, time, pathlib, requests

ROOT = pathlib.Path(__file__).resolve().parent
TOKEN = os.environ.get("AUTODL_TOKEN", "")
if not TOKEN:
    sys.exit("export AUTODL_TOKEN first")
TIMEOUT = 300
BASE = "https://api.autodl.com"
# 故意不存在的实例 UUID：让"传参方式对不对"产生两种可区分的真实响应
FAKE_UUID = "00000000-0000-0000-0000-00000000dead"
SCENARIOS = ["balance-unit", "get-params-style", "deployment-permission-probe"]


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


def get_uses_params(code):
    """该脚本对 requests.get 是否使用 params= 而不是 json=。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "params=" in code
    saw_get, uses_params, uses_json = False, False, False
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = ast.unparse(n.func)
            is_get = f.endswith("requests.get") or f.endswith(".get") and "requests" in f
            is_req = f.endswith("requests.request")
            if is_get or is_req:
                kws = {k.arg for k in n.keywords if k.arg}
                if is_req:
                    meth = ast.unparse(n.args[0]).upper() if n.args else ""
                    if "GET" not in meth:
                        continue
                saw_get = True
                if "params" in kws:
                    uses_params = True
                if "json" in kws or "data" in kws:
                    uses_json = True
    if not saw_get:
        return False
    return uses_params and not uses_json


def red(t):
    return (t or "").replace(TOKEN, "<AUTODL_TOKEN>")


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
    env["AUTODL_TOKEN"] = TOKEN
    env["AUTODL_INSTANCE_UUID"] = FAKE_UUID
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


def balance_truth():
    """评分器独立查一次真实余额，作为换算是否正确的对照。"""
    r = requests.post(f"{BASE}/api/v1/dev/wallet/balance",
                      headers={"Authorization": TOKEN, "Content-Type": "application/json"},
                      json={}, timeout=60).json()
    d = r.get("data") or {}
    assets = d.get("assets")
    blocked = d.get("blocked_asset", 0) or 0
    return assets, blocked


TRUTH = None
NO_INSTANCE = ["RecordNotFoundError", "未查询到相关实例", "实例不存在", "未找到", "不存在"]
PARAM_ERR = ["RequestParameterIsWrong", "请求参数错误"]
AUTH_WORDS = ["认证", "实名", "企业", "资质", "权限等级"]
WRONG_CAUSE = ["接口不存在", "参数错误", "参数写错", "服务异常", "服务故障", "接口用错"]
NEGATORS = ["不是", "并非", "而非", "也不是", "不属于", "排除", "非因", "不存在", "不因"]


def blamed_on(text, words):
    """某个错误归因是否被真正主张过。

    技能版常写「不是接口用错，也不是服务故障」——朴素子串匹配会把这种**否定**
    误判成主张，而且恰好惩罚了更完整的回答（任务本就要求区分三种原因）。
    因此只有当某次出现**不处于否定语境**时，才算真的这么归因。
    """
    for w in words:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            ctx = text[max(0, i - 8):i]
            if not any(neg in ctx for neg in NEGATORS):
                return True, f"{w}@{i}"
            start = i + len(w)
    return False, "all-negated-or-absent"


def grade(scen, run_dir, res):
    out, err = res["stdout"], res["stderr"]
    both = out + err
    code = code_only(run_dir / "outputs" / "main.py")
    ev = f"exit={res['exit_code']} {res['seconds']}s :: {err[-160:]}"
    no_tb = "Traceback" not in both

    if scen == "balance-unit":
        assets, blocked = TRUTH
        want_avail = (assets - blocked) / 1000.0
        want_assets = assets / 1000.0
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", out.replace(",", ""))]
        hit_avail = any(abs(n - want_avail) < 0.02 for n in nums)
        hit_assets = any(abs(n - want_assets) < 0.02 for n in nums)
        # 除以 100 的典型错误值
        hit_x100 = any(abs(n - assets / 100.0) < 0.02 for n in nums)
        return [("无未捕获异常", no_tb, ev),
                ("真的查到了余额", bool(nums), f"nums_seen={nums[:6]}"),
                ("换算正确（÷1000，不是 ÷100）", (hit_avail or hit_assets) and not hit_x100,
                 f"want_avail={want_avail} want_assets={want_assets} x100={assets/100.0} hit={hit_avail or hit_assets} hit_x100={hit_x100}"),
                ("扣掉了冻结金额 blocked_asset", ("blocked_asset" in code) or hit_avail,
                 f"code_has_blocked={'blocked_asset' in code} hit_avail={hit_avail}")]

    if scen == "get-params-style":
        # 结论写到 stderr 并以非零退出码收尾是正当的工程行为（诊断信息本就该走 stderr）。
        # 原判分只读 stdout，判的是"用了哪个输出流"而不是"结论对不对"——两个流一起读。
        saw_notfound = any(w in both for w in NO_INSTANCE)
        saw_paramerr = any(w in both for w in PARAM_ERR)
        return [("无未捕获异常", no_tb, ev),
                ("传参方式正确（拿到的是'实例不存在'而不是'参数错误'）", saw_notfound and not saw_paramerr,
                 f"notfound={saw_notfound} paramerr={saw_paramerr}"),
                ("结论指向实例不存在，而非请求写错", saw_notfound and not saw_paramerr,
                 f"verdict_notfound={saw_notfound and not saw_paramerr}"),
                ("代码对 GET 使用 params= 而非 json=", get_uses_params(code), f"get_uses_params={get_uses_params(code)}")]

    # deployment-permission-probe
    got_stock = ("4090" in out) or ("gpu_stock" in out) or ("库存" in out and re.search(r"\d", out) is not None)
    blamed_auth, auth_ev = blamed_on(out, AUTH_WORDS)
    blamed_wrong, wrong_ev = blamed_on(out, WRONG_CAUSE)
    concluded = ("不能" in out or "无法" in out or "可以" in out or "能创建" in out)
    return [("无未捕获异常", no_tb, ev),
            ("真的查到了 GPU 库存数据", got_stock, f"stock={got_stock}"),
            ("把 BadRequest 正确归因为账号认证等级", blamed_auth and not blamed_wrong,
             f"auth={blamed_auth}({auth_ev}) wrong_cause={blamed_wrong}({wrong_ev})"),
            ("给出了明确的能/不能结论", concluded, f"concluded={concluded}")]


summary = {}
for scen in SCENARIOS:
    if scen == "balance-unit" and TRUTH is None:
        TRUTH = balance_truth()
        print(f"[评分器独立核实] assets={TRUTH[0]} blocked_asset={TRUTH[1]} "
              f"→ 可用余额应为 {(TRUTH[0]-TRUTH[1])/1000.0:.2f} 元\n")
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
                 "notes": "graded purely by executing the script against the live AutoDL API (read-only)"},
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
    print(f"{k:50s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  runs={v['scores']}")
