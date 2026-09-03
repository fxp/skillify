import json, subprocess, sys, re
from pathlib import Path
I = Path(sys.argv[1]); helpers = Path(sys.argv[2])
# assertion index -> list of check names; judgment notes appended
MAP = {
 "eval-resend-mintlify-llms-txt": [
  ["probed_llms_txt_or_openapi"], ["skill_md_states_auth_header","skill_md_cites_source_for_auth"],
  ["skill_md_under_200_lines","skill_md_has_nav_table","skill_md_no_full_param_tables"], ["references_at_least_3"],
  ["every_file_marks_unverified","no_fabricated_verified_claims"], ["verification_plan_exists","verification_plan_cheap_first"],
  ["evals_json_at_least_3"], ["examples_read_key_from_env","no_real_looking_secrets"], ["used_skill_creator"]],
 "eval-kimi-no-llms-txt-fallback": [
  ["probed_llms_txt_or_openapi","fallback_when_no_index"], ["skill_md_states_auth_header","skill_md_cites_source_for_auth"],
  ["skill_md_under_200_lines","skill_md_has_nav_table","skill_md_no_full_param_tables"], ["references_at_least_3"],
  ["every_file_marks_unverified","no_fabricated_verified_claims"], ["verification_plan_exists","verification_plan_cheap_first"],
  ["evals_json_at_least_3"], ["examples_read_key_from_env","no_real_looking_secrets"], ["used_skill_creator"]],
}
# manual judgments (reviewer read the evals prompts / reference file names / marker counts)
JUDG = {
 ("eval-resend-mintlify-llms-txt","with_skill"): {3:"6 refs grouped by intent (sending, domains+api-keys, webhooks+receiving, audiences+broadcasts, templates+automations+events, errors); 132 ⚠ markers", 6:"6 scenarios: BullMQ retry idempotency, 600 PDF batch limits, Next.js webhook signature, raw-fetch on Workers, multi-tenant domains+scoped keys, segment newsletter — all analogy traps", 7:"TypeScript (SDK + fetch), process.env.RESEND_API_KEY"},
 ("eval-resend-mintlify-llms-txt","old_skill"): {3:"5 refs grouped by intent (sending, domains+account, webhooks+receiving, audiences+broadcasts, errors); 26 ⚠ VERIFY markers", 6:"8 scenarios: Workers without SDK, 300 PDF invoices, schedule/cancel, webhook handler, template alias, EU-region domain, pagination generator, inbound — trap-style", 7:"TypeScript, env var; no secrets"},
 ("eval-kimi-no-llms-txt-fallback","with_skill"): {3:"6 refs by intent; 102 '文档未说明/待验证' markers at endpoint level", 6:"7 scenarios: fixed sampling params on k2.6, forced tool call before answer, PDF file-extract flow, 200k-review batch (K3 excluded), stream usage, $web_search builtin, partial mode — analogy traps", 7:"Python, os.environ; no secrets"},
 ("eval-kimi-no-llms-txt-fallback","old_skill"): {3:"7 refs by intent; unclear places collected in a '待验证疑点' section per file (13 markers) rather than inline", 6:"8 scenarios: gpt-4o migration with temperature, image URL (unsupported), PDF upload, k3 tool loop, batch on strongest model, stream thinking+usage, disable thinking+JSON, anthropic SDK migration — analogy traps", 7:"Python, env var; no secrets"},
}
for ed in sorted(I.glob("eval-*")):
    meta = json.load(open(ed/"eval_metadata.json"))
    for cfg in ("with_skill","old_skill"):
        rd = ed/cfg/"run-1"
        checks = json.loads(subprocess.check_output([sys.executable, str(helpers), str(rd)]))
        exps = []
        for i, text in enumerate(meta["assertions"]):
            names = MAP[ed.name][i]
            passed = all(checks[n]["passed"] for n in names)
            ev = "; ".join(f"{n}: {checks[n]['evidence'][:140]}" for n in names)
            j = JUDG.get((ed.name,cfg),{}).get(i)
            if j: ev += " | reviewer: " + j
            exps.append({"text": text, "passed": passed, "evidence": ev})
        timing = json.load(open(rd/"timing.json")) if (rd/"timing.json").exists() else {}
        n = len(exps); p = sum(e["passed"] for e in exps)
        extra = {k: checks[k] for k in ("used_bundled_scripts",) if k in checks}
        g = {"expectations": exps, "summary": {"passed": p, "failed": n-p, "total": n, "pass_rate": round(p/n,3)},
                          "total_tokens": timing.get("total_tokens"), "tokens": timing.get("total_tokens"),
             "execution_metrics": {"total_tokens": timing.get("total_tokens")},
             "process_observations": extra,
             "claims": [], "user_notes_summary": {"uncertainties": [], "needs_review": [], "workarounds": []}}
        json.dump(g, open(rd/"grading.json","w"), ensure_ascii=False, indent=2)
        print(f"{ed.name}/{cfg}: {p}/{n}  scripts_used={extra.get('used_bundled_scripts',{}).get('passed')}  t={timing.get('total_duration_seconds')}s tok={timing.get('total_tokens')}")
