# -*- coding: utf-8 -*-
"""Execute iteration-7 scripts against the real API and grade them.

Usage:
  GLM_CODING_PLAN_API_KEY=... ZHIPUAI_API_KEY=... python3 run_iter7.py [--only run-1]

For every eval-*/{with_skill,without_skill}/run-N/outputs/main.py that has no
grading.json yet (or when --force), run `python3 main.py` with only the env vars
the task promised, capture stdout/stderr/exit code into exec_result.json, then
write grading.json (fields: text / passed / evidence) from the exec result plus
static checks on the source. Keys are never written anywhere.
"""
import json, os, re, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent / "iteration-7"
PLAN = os.environ.get("GLM_CODING_PLAN_API_KEY", "")
STD = os.environ.get("ZHIPUAI_API_KEY", "")
if not PLAN or not STD:
    sys.exit("export GLM_CODING_PLAN_API_KEY and ZHIPUAI_API_KEY first")

ENV_FOR = {
    "cp-requests-basic": {"GLM_KEY": PLAN},
    "cp-openai-sdk-stream": {"GLM_CODING_PLAN_API_KEY": PLAN},
    "cp-anthropic-sdk": {"GLM_CODING_PLAN_API_KEY": PLAN},
    "cp-function-calling": {"GLM_KEY": PLAN},
    "cp-two-keys-embed-chat": {"GLM_CODING_PLAN_API_KEY": PLAN, "ZHIPUAI_API_KEY": STD},
    "cp-implicit-plan-wording": {"ZHIPU_API_KEY": PLAN},
    "cp-claude-code-settings-exec": {},
}
CODING = "open.bigmodel.cn/api/coding/paas/v4"
ANTH = "open.bigmodel.cn/api/anthropic"

def run_settings(run_dir):
    """Validate a generated settings.json by calling /v1/messages for each mapped model with the plan key."""
    import requests
    sj = run_dir / "outputs" / "settings.json"
    if not sj.exists():
        return None
    t0 = time.time()
    res = {"exit_code": 1, "stdout": "", "stderr": "", "timed_out": False, "models": {}}
    try:
        cfg = json.loads(sj.read_text(encoding="utf-8"))
        env = cfg.get("env", cfg)
        base = env.get("ANTHROPIC_BASE_URL", "").rstrip("/")
        res["base_url"] = base
        res["has_token_var"] = "ANTHROPIC_AUTH_TOKEN" in env
        for alias in ("ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL"):
            m = env.get(alias)
            if not m:
                continue
            r = requests.post(f"{base}/v1/messages", headers={"Authorization": f"Bearer {PLAN}", "anthropic-version": "2023-06-01"},
                              json={"model": m, "max_tokens": 32, "messages": [{"role": "user", "content": "回复一个字：好"}]}, timeout=120)
            res["models"][alias] = {"model": m, "status": r.status_code, "body": redact(r.text[:160])}
        res["exit_code"] = 0
        res["stdout"] = json.dumps(res["models"], ensure_ascii=False)
    except Exception as e:
        res["stderr"] = f"{type(e).__name__}: {e}"
    res["seconds"] = round(time.time() - t0, 1)
    (run_dir / "exec_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res

def run_script(run_dir, env_extra):
    main = run_dir / "outputs" / "main.py"
    if not main.exists():
        return None
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "TMPDIR")}
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(env_extra)
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-W", "ignore", str(main)], cwd=str(main.parent), env=env,
                           capture_output=True, text=True, timeout=240)
        res = {"exit_code": p.returncode, "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:], "timed_out": False}
    except subprocess.TimeoutExpired as e:
        res = {"exit_code": None, "stdout": (e.stdout or "")[-4000:] if isinstance(e.stdout, str) else "", "stderr": "TIMEOUT", "timed_out": True}
    res["seconds"] = round(time.time() - t0, 1)
    res["env_keys"] = sorted(env_extra)
    (run_dir / "exec_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res

def redact(s):
    return s.replace(PLAN, "<PLAN_KEY>").replace(STD, "<STD_KEY>")

def grade_settings(run_dir, res):
    ms = res.get("models", {})
    parsed = res["exit_code"] == 0 and bool(res.get("base_url")) and res.get("has_token_var", False)
    def ok_for(alias):
        return alias in ms and ms[alias]["status"] == 200
    sonnet = ok_for("ANTHROPIC_DEFAULT_SONNET_MODEL") or ok_for("ANTHROPIC_MODEL")
    others = [a for a in ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_SMALL_FAST_MODEL") if a in ms]
    all_others = bool(others) and all(ms[a]["status"] == 200 for a in others)
    ev = json.dumps({a: (v["model"], v["status"]) for a, v in ms.items()}, ensure_ascii=False)
    rows = [("settings.json parses as JSON with an env object; ANTHROPIC_BASE_URL and ANTHROPIC_AUTH_TOKEN are present", parsed, f"base_url={res.get('base_url')} has_token_var={res.get('has_token_var')} err={res.get('stderr','')[:120]}"),
            ("A live POST to <ANTHROPIC_BASE_URL>/v1/messages with the plan key succeeds (HTTP 200) for the sonnet-mapped model", sonnet, ev),
            ("A live POST to <ANTHROPIC_BASE_URL>/v1/messages with the plan key succeeds (HTTP 200) for the haiku-mapped model and the opus-mapped model (every model alias Claude Code may request must be usable under the plan)", all_others, ev)]
    exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
    passed = sum(1 for r in exp if r["passed"])
    g = {"expectations": exp, "summary": {"passed": passed, "failed": len(exp) - passed, "total": len(exp), "pass_rate": round(passed / len(exp), 3)},
         "notes": "end_to_end_success=" + ("yes" if (parsed and sonnet and all_others) else "no")}
    (run_dir / "grading.json").write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
    return g

def grade(eval_name, run_dir, res):
    if eval_name == "cp-claude-code-settings-exec":
        return grade_settings(run_dir, res)
    src = (run_dir / "outputs" / "main.py").read_text(encoding="utf-8", errors="replace")
    out = res["stdout"].strip()
    ok = res["exit_code"] == 0 and len(out) > 0
    err_tail = redact((res["stderr"] or "")[-300:] + " | stdout: " + out[-200:])
    exec_ev = f"exit={res['exit_code']} seconds={res['seconds']} stdout_len={len(out)} :: {err_tail}"
    rows = []
    if eval_name == "cp-requests-basic":
        rows = [("Executing `python3 main.py` with only GLM_KEY (a Coding Plan key) exported exits 0 and prints a non-empty model answer", ok, exec_ev),
                ("Request goes to the Coding Plan endpoint https://open.bigmodel.cn/api/coding/paas/v4/chat/completions", CODING in src, "grep coding/paas/v4 in main.py")]
    elif eval_name == "cp-openai-sdk-stream":
        rows = [("Executing `python3 main.py` with only GLM_CODING_PLAN_API_KEY exported exits 0 and prints a non-empty streamed poem", ok, exec_ev),
                ("base_url is the Coding Plan endpoint https://open.bigmodel.cn/api/coding/paas/v4", CODING in src, "grep coding/paas/v4 in main.py")]
    elif eval_name == "cp-anthropic-sdk":
        raw = bool(re.search(r"TextBlock\(|ThinkingBlock\(|type='thinking'|\"type\": \"thinking\"|\[.*Block", out))
        rows = [("Executing `python3 main.py` with only GLM_CODING_PLAN_API_KEY exported exits 0 and prints a non-empty answer", ok, exec_ev),
                ("base_url is https://open.bigmodel.cn/api/anthropic", ANTH in src, "grep api/anthropic in main.py"),
                ("Code handles the response content list correctly (prints the text block, not a thinking block or the raw list)", ok and not raw, "stdout looks like prose" if not raw else "stdout contains raw block repr")]
    elif eval_name == "cp-function-calling":
        has_time = bool(re.search(r"\d{1,2}\s*[:：点]\s*\d{0,2}", out))
        loop = ("tool_call_id" in src) and re.search(r"['\"]role['\"]\s*:\s*['\"]tool['\"]", src) is not None
        rows = [("Executing `python3 main.py` with only GLM_KEY (a Coding Plan key) exported exits 0 and prints a final answer that mentions a time", ok and has_time, exec_ev),
                ("Request goes to https://open.bigmodel.cn/api/coding/paas/v4/chat/completions", CODING in src, "grep coding/paas/v4 in main.py"),
                ("Tool-call loop is implemented (tool_calls parsed, role=tool message with tool_call_id sent back)", loop, "grep tool_call_id + role tool in main.py")]
    elif eval_name == "cp-implicit-plan-wording":
        rows = [("Executing `python3 main.py` with only ZHIPU_API_KEY (holding a Coding Plan key) exported exits 0 and prints a non-empty model answer", ok, exec_ev),
                ("Request goes to the Coding Plan endpoint https://open.bigmodel.cn/api/coding/paas/v4/chat/completions, i.e. the agent recognised the plan from the wording", CODING in src, "grep coding/paas/v4 in main.py")]
    elif eval_name == "cp-two-keys-embed-chat":
        has_num = bool(re.search(r"0\.\d+|1\.0", out))
        routing = ("ZHIPUAI_API_KEY" in src and "GLM_CODING_PLAN_API_KEY" in src and CODING in src)
        rows = [("Executing `python3 main.py` with both keys exported exits 0 and prints a similarity score and a model sentence", ok and has_num, exec_ev),
                ("Embeddings call uses the standard key (Coding Plan key cannot call embeddings), chat call uses the plan key on the coding endpoint", routing and ok, "both env names + coding endpoint in source, and the run succeeded (a plan key on embeddings would have failed with 1113)")]
    exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
    passed = sum(1 for r in exp if r["passed"])
    g = {"expectations": exp, "summary": {"passed": passed, "failed": len(exp) - passed, "total": len(exp), "pass_rate": round(passed / len(exp), 3)},
         "notes": "end_to_end_success=" + ("yes" if ok else "no")}
    (run_dir / "grading.json").write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
    return g

only = None
force = "--force" in sys.argv
for a in sys.argv[1:]:
    if a.startswith("--only="):
        only = a.split("=", 1)[1]
for eval_dir in sorted(ROOT.glob("eval-*")):
    name = eval_dir.name[len("eval-"):]
    for cfg in ("with_skill", "without_skill"):
        for run_dir in sorted((eval_dir / cfg).glob("run-*")):
            if only and run_dir.name != only:
                continue
            if (run_dir / "grading.json").exists() and not force:
                continue
            res = run_settings(run_dir) if name == "cp-claude-code-settings-exec" else run_script(run_dir, ENV_FOR[name])
            if res is None:
                continue
            g = grade(name, run_dir, res)
            print(f"{name:26s} {cfg:13s} {run_dir.name} exit={res['exit_code']} e2e={'OK ' if g['notes'].endswith('yes') else 'FAIL'} pass={g['summary']['passed']}/{g['summary']['total']}")
