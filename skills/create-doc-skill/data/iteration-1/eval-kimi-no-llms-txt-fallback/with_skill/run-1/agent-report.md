# Agent final report (with_skill, Kimi)

quick_validate passes; package_skill builds kimi-api.skill; no key-like strings; 0 hits on api.moonshot.cn (52 fetches, all docs site).

| File | Lines |
|---|---|
| kimi-api/SKILL.md (router: base URLs, bearer auth, live model names, per-model reasoning config, 12 cross-cutting rules) | 96 |
| references/models-and-thinking.md | 541 |
| references/chat-completions.md | 650 |
| references/tool-calling.md | 623 |
| references/files-and-batch.md | 599 |
| references/responses-messages-and-utilities.md | 598 |
| references/errors-and-limits.md | 303 |
| evals/evals.json (7 scenarios / 25 expectations) | 85 |
| kimi-api-workspace/verification-plan.md (P0-P3 tests, P4 = 127 ⚠ items, P5 = 10 doc self-contradictions) | 202 |
| process-log.md (52 URLs) | 159 |

The 400 "tool_choice 'specified' is incompatible with thinking enabled" is quoted from docs (guide/use-tool-choice.md), not observed live; all error strings labeled doc-transcribed/unverified.

## Skill feedback (new version)
1. explore.md only says try /llms.txt at domain root; real index at /docs/llms.txt (and /docs/openapi.json). Fallback path never needed.
2. No guidance for domain migration (moonshot.cn -> kimi.com canonical).
3. No guidance for 199-page index vs 60-fetch budget, or multi-product doc sites (Hosted Agents scoped to a router entry).
4. skill-creator deps under-documented: pyyaml; package_skill.py only works as python -m scripts.package_skill.
5. write.md sub-agent template should require "error strings are doc quotes, not observed".
6. Sub-agent completion notifications unreliable; coordinator's "no children running" was wrong once; sub-agents should write reports to disk.
7. verify.md no-key downgrade doesn't say whether Step 4 should run in draft-only delivery.
8. macOS `cut -c` corrupted UTF-8; warn for Chinese docs.
