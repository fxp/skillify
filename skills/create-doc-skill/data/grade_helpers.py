#!/usr/bin/env python3
"""Programmatic checks for create-doc-skill eval runs.

Usage: python3 grade_helpers.py <run-dir>   (the dir containing outputs/)
Prints a JSON object of check-name -> {"passed": bool, "evidence": str}.
These cover the mechanical assertions; judgment assertions (trap-style scenarios,
intent-based grouping) still need a reader.
"""
import json, re, sys
from pathlib import Path

run = Path(sys.argv[1]).resolve()
out = run / "outputs"
res = {}

def find_skill_dirs():
    return sorted({p.parent for p in out.rglob("SKILL.md") if "node_modules" not in p.parts})

skills = find_skill_dirs()
res["skill_dir_exists"] = {"passed": bool(skills), "evidence": ", ".join(str(s.relative_to(out)) for s in skills) or "no SKILL.md under outputs/"}
skill = skills[0] if skills else None

def read(p):
    try: return p.read_text(encoding="utf-8", errors="replace")
    except Exception: return ""

# --- SKILL.md routing layer ---
if skill:
    sm = read(skill / "SKILL.md")
    lines = sm.count("\n") + 1
    has_nav = bool(re.search(r"\|\s*.*(想做|intent|I want|参考文件|reference).*\|", sm, re.I)) and sm.count("|---") >= 1
    param_tables = len(re.findall(r"\|\s*(参数|param|field|name)\s*\|\s*(类型|type)", sm, re.I))
    res["skill_md_under_200_lines"] = {"passed": lines <= 200, "evidence": f"{lines} lines"}
    res["skill_md_has_nav_table"] = {"passed": has_nav, "evidence": "navigation table found" if has_nav else "no intent->file table"}
    res["skill_md_no_full_param_tables"] = {"passed": param_tables == 0, "evidence": f"{param_tables} parameter-table headers in SKILL.md"}
    auth = re.search(r"Authorization\s*:\s*(Bearer\s+)?[`<{\w-]+|x-api-key|api[-_]?key", sm, re.I)
    res["skill_md_states_auth_header"] = {"passed": bool(auth), "evidence": auth.group(0) if auth else "no auth header format in SKILL.md"}
    src = re.search(r"(securitySchemes|openapi|llms\.txt|来自文档|文档.*(页|页面|来源)|source[d]?\s*from|according to the docs|docs/[\w/-]+)", sm, re.I)
    res["skill_md_cites_source_for_auth"] = {"passed": bool(src), "evidence": src.group(0) if src else "no citation of docs/openapi as source"}

    refs = sorted((skill / "references").glob("*.md")) if (skill / "references").is_dir() else []
    res["references_at_least_3"] = {"passed": len(refs) >= 3, "evidence": ", ".join(f"{r.name}({read(r).count(chr(10))+1}L)" for r in refs) or "no references/"}

    unverified_pat = re.compile(r"(未经?真实|未验证|未经验证|尚未.*验证|unverified|not (yet )?(been )?verified|not validated against)", re.I)
    missing = [f.name for f in [skill / "SKILL.md", *refs] if not unverified_pat.search(read(f))]
    res["every_file_marks_unverified"] = {"passed": not missing, "evidence": "all files carry an unverified statement" if not missing else "missing in: " + ", ".join(missing)}
    fake_verified = [f.name for f in [skill / "SKILL.md", *refs] if re.search(r"已用真实\s*API\s*(调用)?验证|(?<!NOT yet )(?<!not yet )(?<!not )(?<!NOT )verified against the live API", read(f))]
    res["no_fabricated_verified_claims"] = {"passed": not fake_verified, "evidence": "none" if not fake_verified else "claims of live verification in: " + ", ".join(fake_verified)}

    ev = skill / "evals" / "evals.json"
    try:
        evd = json.loads(read(ev)); n = len(evd.get("evals", []))
        res["evals_json_at_least_3"] = {"passed": n >= 3, "evidence": f"{n} evals; prompts: " + " || ".join(e.get("prompt", "")[:80] for e in evd.get("evals", [])[:6])}
    except Exception as e:
        res["evals_json_at_least_3"] = {"passed": False, "evidence": f"evals.json missing/invalid: {e}"}

# --- verification plan ---
plans = [p for p in out.rglob("*.md") if re.search(r"verif|验证", p.name, re.I) and p.name != "SKILL.md"]
plan_txt = "\n".join(read(p) for p in plans)
cheap_first = bool(re.search(r"(低成本|便宜|cheap|free|只读|read-only|priority|优先|P0|P1)", plan_txt, re.I))
has_endpoints = len(re.findall(r"(GET|POST|PUT|PATCH|DELETE)\s+/", plan_txt)) >= 3
n_ep = len(re.findall(r"(GET|POST|PUT|PATCH|DELETE)\s+/", plan_txt))
res["verification_plan_exists"] = {"passed": bool(plans) and has_endpoints, "evidence": (", ".join(str(p.relative_to(out)) for p in plans) + "; endpoints mentioned: " + str(n_ep)) if plans else "no verification/验证 plan file"}
res["verification_plan_cheap_first"] = {"passed": bool(plans) and cheap_first, "evidence": "priority/cost ordering words present" if cheap_first else "no ordering by cost/priority"}

# --- secrets ---
secret_pat = re.compile(r"(re_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|sk_(live|test)_[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|ghp_[A-Za-z0-9]{30,})")
hits = []
for p in out.rglob("*"):
    if p.is_file() and p.suffix in {".md", ".json", ".ts", ".py", ".js", ".sh", ".yaml", ".yml", ".txt", ".env"}:
        for m in secret_pat.finditer(read(p)):
            hits.append(f"{p.relative_to(out)}: {m.group(0)[:12]}…")
res["no_real_looking_secrets"] = {"passed": not hits, "evidence": "none" if not hits else "; ".join(hits[:5])}

# --- env var usage in examples ---
code_txt = "\n".join(read(p) for p in out.rglob("*.md"))
envs = re.findall(r"process\.env\.[A-Z_]+|os\.environ(\.get)?\[?\(?['\"][A-Z_]+|\$[A-Z_]*(KEY|TOKEN)", code_txt)
res["examples_read_key_from_env"] = {"passed": len(envs) >= 1, "evidence": f"{len(envs)} env-var reads in examples"}

# --- process log evidence ---
log = read(out / "process-log.md")
res["process_log_present"] = {"passed": bool(log.strip()), "evidence": f"{len(log)} chars" if log else "missing"}
res["probed_llms_txt_or_openapi"] = {"passed": bool(re.search(r"llms(-full)?\.txt|openapi|swagger|asyncapi", log, re.I)), "evidence": "; ".join(sorted(set(m.group(0) for m in re.finditer(r"[\w./-]*(llms(-full)?\.txt|openapi[\w./-]*|swagger[\w./-]*)", log, re.I)))[:6]) or "no llms.txt/openapi in process log"}
res["fallback_when_no_index"] = {"passed": bool(re.search(r"sitemap|渲染|rendered|read_page|get_page_text|browser|手工|manual|导航", log, re.I)), "evidence": "; ".join(sorted(set(m.group(0) for m in re.finditer(r"sitemap[\w./-]*|渲染|rendered|read_page|get_page_text|browser|手工|manual", log, re.I)))[:6]) or "no fallback strategy in log"}
res["used_skill_creator"] = {"passed": bool(re.search(r"skill-creator|skill_creator", log + code_txt, re.I)), "evidence": "skill-creator referenced" if re.search(r"skill-creator|skill_creator", log + code_txt, re.I) else "no mention of skill-creator"}
res["used_bundled_scripts"] = {"passed": bool(re.search(r"openapi_summary\.py|fetch_docs\.sh", log)), "evidence": "; ".join(sorted(set(re.findall(r"openapi_summary\.py|fetch_docs\.sh", log)))) or "bundled scripts not used"}

print(json.dumps(res, ensure_ascii=False, indent=2))
