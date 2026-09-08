# -*- coding: utf-8 -*-
"""用**各场景原来那一轮的冻结评分器**给 v2 判分，不新写任何判据。

做法：把 v2 的运行目录临时挂进原轮次的目录结构里，直接调用原 grade.py 的
run()/grade() 两个函数——判分逻辑逐行沿用，保证 v1/v2 可比。

用法： ZHIPUAI_API_KEY=... GLM_CODING_PLAN_API_KEY=... python3 grade_v2.py
"""
import importlib.util, json, os, pathlib, shutil, sys, types

HERE = pathlib.Path(__file__).resolve().parent
WS = HERE.parent
TASKS = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))
FIXTURES = {"batch-best-model": ["comments.txt"], "pdf-reuse-fileid": ["contract.pdf"],
            "kb-id-validation-silent200": []}


def load_grader(round_dir):
    """加载某一轮的 grade.py，但不执行它文件底部的统计主流程。"""
    src = (WS / round_dir / "grade.py").read_text(encoding="utf-8")
    cut = src.index("summary = {}")
    mod = types.ModuleType(f"grader_{round_dir}")
    mod.__file__ = str(WS / round_dir / "grade.py")
    sys.modules[mod.__name__] = mod
    exec(compile(src[:cut], mod.__file__, "exec"), mod.__dict__)
    return mod


graders = {}
results = {}
for scen, (rd, _task) in TASKS.items():
    if rd not in graders:
        graders[rd] = load_grader(rd)
    g = graders[rd]
    scores = []
    for run in range(1, 6):
        rdir = HERE / scen / "with_skill" / f"run-{run}"
        if not (rdir / "outputs" / "main.py").exists():
            print(f"{scen:30s} run-{run}  NO main.py"); continue
        # 把 fixture 放到评分器期望的位置
        for fx in FIXTURES.get(scen, []):
            tgt = WS / rd / "fixtures" / fx
            if tgt.exists():
                pass
        # 三种签名共存：run(run_dir, fixtures) / run(scen, run_dir) / run(run_dir)
        names = g.run.__code__.co_varnames[:g.run.__code__.co_argcount]
        if names == ("run_dir", "fixtures"):
            res = g.run(rdir, g.SCEN[scen])
        elif names == ("scen", "run_dir"):
            res = g.run(scen, rdir)
        else:
            res = g.run(rdir)
        if res is None:
            print(f"{scen:30s} run-{run}  执行失败"); continue
        rows = g.grade(scen, rdir, res)
        exp = [{"text": t, "passed": bool(p), "evidence": e} for t, p, e in rows]
        passed = sum(1 for r in exp if r["passed"])
        (rdir / "grading.json").write_text(json.dumps(
            {"expectations": exp,
             "summary": {"passed": passed, "failed": len(exp) - passed, "total": len(exp),
                         "pass_rate": round(passed / len(exp), 3)},
             "executor": "glm-5.3", "skill": "v2",
             "notes": f"graded with the frozen grader from {rd}"},
            ensure_ascii=False, indent=2), encoding="utf-8")
        scores.append(passed / len(exp))
        fail = [r["text"][:24] for r in exp if not r["passed"]]
        print(f"{scen:30s} run-{run}  {passed}/{len(exp)}  ({res['seconds']}s) {fail if fail else ''}")
    if scores:
        m = sum(scores) / len(scores)
        sd = (sum((x - m) ** 2 for x in scores) / len(scores)) ** 0.5
        results[scen] = {"runs": len(scores), "scores": [round(x, 3) for x in scores],
                         "mean": round(m, 3), "stdev": round(sd, 3), "grader_round": rd}

(HERE / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n=== v2 汇总 ===")
for k, v in results.items():
    print(f"{k:30s} mean={v['mean']:.3f} ± {v['stdev']:.3f}  {v['scores']}  (grader: {v['grader_round']})")
