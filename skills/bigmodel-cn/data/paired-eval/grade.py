# -*- coding: utf-8 -*-
"""v3-eval 评分器。判定全部来自脚本执行真实 API 的结果。判分标准冻结于 PROTOCOL.md。

用法： SKILL_VER=v2|v3 ZHIPUAI_API_KEY=... GLM_CODING_PLAN_API_KEY=... python3 grade.py [--regrade]

口径沿用前几轮：判结果不判形式（stdout/stderr 一起读；不因变量取名或某个子串扣分）。
"""
import ast, json, os, re, shutil, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
VER = os.environ.get("SKILL_VER", "v1")
STD = os.environ.get("ZHIPUAI_API_KEY", "")
PLAN = os.environ.get("GLM_CODING_PLAN_API_KEY", "")
if not STD or not PLAN:
    sys.exit("export ZHIPUAI_API_KEY and GLM_CODING_PLAN_API_KEY first")
TIMEOUT = 420
SCEN = ["tts-asr-roundtrip", "plan-vision-ocr", "rerank-restore-docs", "long-cited-answer",
        "long-report-complete", "tight-budget-complete",
        "batch-forced-flagship", "kb-fallback"]
FIXTURES = {"plan-vision-ocr": ["invoice.png"],
            "batch-forced-flagship": ["comments.txt"],
            "kb-fallback": ["faq.txt"]}

SRC_TEXT = "发票需要在七个工作日内申请"
DOCS = ["签收后 15 日内可无理由退货", "增值税专用发票需在订单完成后 7 个工作日内申请",
        "公司地址位于北京市海淀区", "普通发票支持随时申请", "满 199 元包邮"]



def max_token_values(code):
    """取出脚本里所有 max_tokens 的实际取值——字面量、模块级常量引用都算。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return [int(m) for m in re.findall(r"max_tokens[\"']?\s*[:=]\s*(\d+)", code)]
    consts = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
           and isinstance(n.value.value, int):
            for tgt in n.targets:
                if isinstance(tgt, ast.Name):
                    consts[tgt.id] = n.value.value

    def resolve(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        # min(MAX, 1000) / MAX - 100 之类：取能算出来的常量部分
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("min", "max"):
            vals = [resolve(a) for a in node.args]
            vals = [v for v in vals if v is not None]
            return (min(vals) if node.func.id == "min" else max(vals)) if vals else None
        if isinstance(node, ast.BinOp):
            l, r = resolve(node.left), resolve(node.right)
            if l is not None and r is not None:
                if isinstance(node.op, ast.Add): return l + r
                if isinstance(node.op, ast.Sub): return l - r
                if isinstance(node.op, ast.Mult): return l * r
        return None

    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == "max_tokens":
                    r = resolve(v)
                    if r is not None:
                        out.append(r)
        if isinstance(n, ast.keyword) and n.arg == "max_tokens":
            r = resolve(n.value)
            if r is not None:
                out.append(r)
    # 兜底：变量名本身就叫 MAX_TOKENS 之类
    if not out:
        for k, v in consts.items():
            if "max_token" in k.lower():
                out.append(v)
    return out


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
                # 函数体只有 docstring 时，剥掉会留下空 body，ast.unparse 产出的代码
                # 语法非法（`def f():` 后面没东西），下游再 ast.parse 就会失败。补一个 pass。
                if not b:
                    b.append(ast.Pass())
    ast.fix_missing_locations(tree)
    try:
        return ast.unparse(tree)
    except Exception:
        return src


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
    env["ZHIPUAI_API_KEY"] = STD
    env["ZHIPU_API_KEY"] = STD
    env["GLM_CODING_PLAN_API_KEY"] = PLAN
    env["GLM_KEY"] = PLAN
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-W", "ignore", "main.py"], cwd=str(work), env=env,
                           capture_output=True, text=True, timeout=TIMEOUT)
        res = {"exit_code": p.returncode, "stdout": p.stdout[-9000:], "stderr": p.stderr[-6000:], "timed_out": False}
    except subprocess.TimeoutExpired as e:
        res = {"exit_code": None, "stdout": (e.stdout if isinstance(e.stdout, str) else "")[-9000:],
               "stderr": "TIMEOUT", "timed_out": True}
    res["seconds"] = round(time.time() - t0, 1)
    # 落盘的音频文件（tts 场景要看首字节）
    auds = []
    for f in sorted(work.rglob("*")):
        if f.is_file() and f.suffix.lower() in (".wav", ".mp3", ".pcm", ".raw", ".m4a", ".ogg"):
            auds.append({"name": f.name, "size": f.stat().st_size,
                         "head": f.read_bytes()[:4].hex()})
    res["audio_files"] = auds
    res["stdout"], res["stderr"] = red(res["stdout"]), red(res["stderr"])
    (run_dir / "exec_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def longest_cjk_overlap(a, b):
    """a 中最长的、也出现在 b 里的连续汉字片段长度。"""
    best = 0
    for i in range(len(a)):
        for j in range(i + best + 1, len(a) + 1):
            s = a[i:j]
            if not re.fullmatch(r"[一-鿿]+", s):
                break
            if s in b:
                best = max(best, len(s))
            else:
                break
    return best


def grade(scen, run_dir, res):
    out, err = res["stdout"], res["stderr"]
    both = out + err
    code = code_only(run_dir / "outputs" / "main.py")
    ev = f"exit={res['exit_code']} {res['seconds']}s :: {err[-150:]}"
    no_tb = "Traceback" not in both

    if scen == "tts-asr-roundtrip":
        auds = res.get("audio_files", [])
        real = [a for a in auds if a["head"].startswith("52494646") or a["head"].startswith("494433")
                or a["head"].startswith("fff")]
        overlap = longest_cjk_overlap(SRC_TEXT, both)
        transcribed = overlap >= 3
        verdict = any(w in both for w in ["一致", "匹配", "相符", "链路通", "通了", "成功"])
        return [("无未捕获异常", no_tb, ev),
                ("落盘音频是真 WAV/MP3 而非裸 PCM", bool(real),
                 f"files={[(a['name'], a['head']) for a in auds]}"),
                ("ASR 真的转写出了内容", transcribed, f"最长汉字重合={overlap}"),
                ("给出了比对结论且转写确实成功", verdict and transcribed, f"verdict={verdict}")]

    if scen == "plan-vision-ocr":
        gave_up = any(w in both for w in ["套餐不支持视觉", "不支持视觉", "无法识别图片", "套餐不含视觉",
                                          "不支持图片", "无法处理图片"])
        # 真的调通：有模型对图片的回答（非空且不是纯错误信息）
        answered = (len(re.findall(r"[一-鿿]", out)) >= 20) and not gave_up
        plan_ep = ("coding/paas/v4" in code) or ("api/anthropic" in code)
        echoed = bool(re.search(r"glm-[0-9a-z.\-]+", out))
        return [("无未捕获异常", no_tb, ev),
                ("真的调通了视觉模型（没有错误地断言套餐不支持）", answered,
                 f"answered={answered} gave_up={gave_up}"),
                ("用的是套餐端点", plan_ep, f"plan_endpoint={plan_ep}"),
                ("打印了服务端回显的实际模型名", echoed, f"echoed={echoed}")]

    if scen == "rerank-restore-docs":
        hits = sum(1 for d in DOCS if longest_cjk_overlap(d.replace(" ", ""), both.replace(" ", "")) >= 5)
        has_score = bool(re.search(r"0\.\d{2,}|1\.0{2,}", both))
        # 【已作废】原第 4 项"最相关的排在第一"测的是平台 rerank 模型的排序质量，
        # 不是 Agent 或说明书能左右的东西——直接探针确认：接口自己就把"普通发票支持随时申请"
        # 排在第一，且与正确文档的 relevance_score 并列 1.0000000000。
        # 换成一条真正测得到脚本行为的：是否按接口返回的顺序稳定输出（而不是自己乱排）。
        flat = both.replace(" ", "")
        order = [i for i in range(5)
                 if flat.find(DOCS[i][:6].replace(" ", "")) >= 0]
        printed_all = len(order) >= 4
        return [("无未捕获异常", no_tb, ev),
                ("输出了文档原文而不是序号", hits >= 3, f"命中原文段数={hits}/5"),
                ("输出了相关性分数", has_score, f"has_score={has_score}"),
                ("五段候选都完整呈现（≥4 段）", printed_all, f"呈现段数={len(order)}/5")]

    if scen == "tight-budget-complete":
        body_cjk = len(re.findall(r"[一-鿿]", out))
        enough = body_cjk >= 600
        # 原判据用正则只认字面数字，脚本写 MAX_TOKENS = 1000 再引用变量就检不出来
        # （5 次运行全被误判为"没遵守约束"）。改成 AST：解析常量赋值再解引用。
        mts = max_token_values(code)
        obeyed = bool(mts) and all(v <= 1000 for v in mts)
        honest = enough or any(w in both for w in ["未达标", "不足", "没有达到", "卡在"])
        return [("无未捕获异常", no_tb, ev),
                ("正文 ≥600 汉字", enough, f"正文汉字={body_cjk}"),
                ("遵守 max_tokens ≤ 1000", obeyed, f"max_tokens取值={mts}"),
                ("没有把截断的半截内容丢出来", honest, f"enough={enough}")]

    if scen == "batch-forced-flagship":
        bid = re.search(r"batch_[0-9A-Za-z_\-]{6,}", both)
        hit1210 = bool(re.search(r'["\']?code["\']?\s*[:=]\s*["\']?1210', both)) or "模型名称错误" in both
        explained = any(w in both for w in ["白名单", "不支持", "已改用", "改为", "降级", "不在", "替换"])
        return [("无未捕获异常", no_tb, ev),
                ("最终真的创建成功了 batch", bool(bid), f"batch_id={bid.group(0) if bid else None}"),
                ("没有卡在 1210 上退出", bool(bid) or not hit1210, f"hit1210={hit1210} got_id={bool(bid)}"),
                ("说明了为什么换模型", explained or not hit1210, f"explained={explained}")]

    if scen == "kb-fallback":
        faq = (ROOT / "fixtures" / "faq.txt").read_text(encoding="utf-8")
        # 检索结果里是否出现 faq 原文的连续片段
        hit = 0
        for line in faq.splitlines():
            s = line.strip().replace(" ", "")
            if len(s) >= 8 and s[:8] in both.replace(" ", ""):
                hit += 1
        retrieved = hit >= 1
        checks_stat = "embedding_stat" in code
        claims_ok = any(w in both for w in ["成功", "完成", "可检索", "检索到"])
        honest = retrieved or not claims_ok
        return [("无未捕获异常", no_tb, ev),
                ("检查了 embedding_stat", checks_stat, f"checks={checks_stat}"),
                ("最终真的检索到了内容（含降级方案）", retrieved, f"命中 faq 原文行数={hit}"),
                ("结论诚实（检索不到就不谎称成功）", honest, f"retrieved={retrieved} claims_ok={claims_ok}")]

    if scen == "long-report-complete":
        # 实测：glm-4.6 写这份简报，思考链要 2400+ 字。max_tokens=800 → 正文 0 字；
        # 1500 → 正文 289 字仍截断；3000 才完整；关掉思考则 1500 就够。
        body_cjk = len(re.findall(r"[一-鿿]", out))
        enough = body_cjk >= 600
        truncated = bool(re.search(r"finish_reason[^\n]{0,20}length", both)) and not enough
        headings = len(re.findall(r"(^|\n)\s*(#{1,4}\s|[一二三四五六七八九十]+[、.]|\d+[、.])", out))
        # 撞上截断后是否自己补救了（加预算 / 关思考 / 重试），而不是把半截丢出来
        remedied = enough or (not truncated)
        return [("无未捕获异常", no_tb, ev),
                ("简报正文 ≥600 汉字", enough, f"正文汉字={body_cjk}"),
                ("没有把被截断的半截内容丢出来", remedied, f"truncated={truncated} enough={enough}"),
                ("有小标题结构", headings >= 2, f"标题数={headings}")]

    # long-cited-answer
    links = re.findall(r"https?://[^\s\"'）)\],]{6,}", both)
    truncated_end = bool(re.search(r"(finish_reason[^\n]{0,20}length|被截断|截断)[^\n]{0,40}$", both.strip()))
    complete = not truncated_end
    reads_api = ("web_search" in code) or ("search_result" in code)
    return [("无未捕获异常", no_tb, ev),
            ("答案完整未被截断", complete, f"truncated_end={truncated_end}"),
            ("至少 2 条 http(s) 来源链接", len(links) >= 2, f"links={len(links)}"),
            ("来源取自接口返回而非编造", reads_api, f"reads_api={reads_api}")]


summary = {}
for scen in SCEN:
    scores = []
    for rd in sorted((ROOT / VER / scen).glob("run-*")):
        res = run(scen, rd)
        if res is None:
            print(f"{VER} {scen:22s} {rd.name}  NO main.py"); continue
        rows = grade(scen, rd, res)
        exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
        passed = sum(1 for r in exp if r["passed"])
        (rd / "grading.json").write_text(json.dumps(
            {"expectations": exp,
             "summary": {"passed": passed, "failed": len(exp) - passed, "total": len(exp),
                         "pass_rate": round(passed / len(exp), 3)},
             "executor": "glm-5.3", "skill": VER},
            ensure_ascii=False, indent=2), encoding="utf-8")
        scores.append(passed / len(exp))
        fail = [r["text"][:22] for r in exp if not r["passed"]]
        print(f"{VER} {scen:22s} {rd.name}  {passed}/{len(exp)}  ({res['seconds']}s) {fail if fail else ''}")
    if scores:
        m = sum(scores) / len(scores)
        sd = (sum((x - m) ** 2 for x in scores) / len(scores)) ** 0.5
        summary[scen] = {"runs": len(scores), "scores": [round(x, 3) for x in scores],
                         "mean": round(m, 3), "stdev": round(sd, 3)}
(ROOT / f"summary-{VER}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n=== {VER} 汇总 ===")
for k, v in summary.items():
    full = sum(1 for x in v["scores"] if x >= 0.999)
    print(f"{k:24s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  满分 {full}/{len(v['scores'])}  {v['scores']}")
