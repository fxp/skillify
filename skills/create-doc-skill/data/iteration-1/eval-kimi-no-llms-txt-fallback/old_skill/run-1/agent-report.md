# Agent final report (old_skill, Kimi)

package_skill.py validated; no key-like strings; evals.json parses; every reference has "unverified draft" header and "待验证疑点" section; 57/60 fetches used; api.moonshot.cn never contacted.

| File | Lines | Notes |
|---|---|---|
| kimi-api/SKILL.md | 81 | routing table, cross-cutting rules, "10 things OpenAI intuition gets wrong" |
| references/models.md | 69 | |
| references/chat-completions.md | 348 | (subagent) |
| references/tools.md | 320 | (subagent) |
| references/vision-and-files.md | 205 | |
| references/batch.md | 195 | |
| references/responses-and-messages.md | 222 | |
| references/errors-and-limits.md | 145 | |
| evals/evals.json | 114 | 8 scenarios, 36 assertions |
| verification-plan.md | 109 | ~55 items in 8 groups |
| process-log.md | 153 | 57 URLs with status |

Seven doc-vs-schema contradictions found from reading alone, flagged not resolved.

## Skill feedback (old version)
1. llms.txt path too narrow: root /llms.txt was 404; real one is /docs/llms.txt (same for openapi.json).
2. No "no API key" branch; invented one.
3. Parallel subagent assumption failed: only 2 launched (concurrency cap), wrote other 5 files myself.
4. xargs -P with a shell function fails under zsh (export -f); needs a script file.
5. MDX not mentioned: key tables inside <DocTable rows={[...]}> JSX, invisible to naive grep.
6. No scope-cutting guidance: 60% of 199 pages are a separate Hosted Agents product; excluded.
7. Skipped run_eval.py / improve_description.py (time box).
8. References ../bigmodel-cn as style example, which was forbidden; format should be inlined.
