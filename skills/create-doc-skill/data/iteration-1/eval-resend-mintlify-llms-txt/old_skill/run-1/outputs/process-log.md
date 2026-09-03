# Process log — Resend skill draft (old_skill / skill-snapshot run)

Date: 2026-09-03. Skill followed: `create-doc-skill-workspace/skill-snapshot/SKILL.md` (generate-skill-from-api-docs). Constraints: no live API calls, ≤60 fetches, ~25 min, TypeScript examples.

## 1. URLs probed, in order (HTTP status)

| # | URL | Status | Purpose |
|---|---|---|---|
| 1 | https://resend.com/docs/llms.txt | 200 | step 1.1 llms.txt index (probe) |
| 2 | https://resend.com/llms.txt | 200 | same file at site root |
| 3 | https://resend.com/docs/llms-full.txt | 200 | full-corpus export (probe) |
| 4 | https://resend.com/docs/openapi.json | 404 | step 1.2 OpenAPI guess |
| 5 | https://resend.com/docs/api-reference/openapi.json | 404 | OpenAPI guess |
| 6 | https://resend.com/docs/openapi/openapi.json | 404 | OpenAPI guess |
| 7 | https://resend.com/docs/introduction.md | 200 | confirm `.md` suffix trick works |
| 8 | https://resend.com/docs/api-reference/introduction.md | 200 | same |
| 9 | https://resend.com/docs/llms.txt | 200 | download (372 lines, 362 links) |
| 10 | https://resend.com/docs/llms-full.txt | 200 | download (62,748 lines, 2.1 MB, all 360 pages inline) |
| 11 | https://api.github.com/repos/resend/resend-openapi/contents/ | 200 | locate real OpenAPI file (linked from docs/sdks) |
| 12 | https://raw.githubusercontent.com/resend/resend-openapi/main/resend.yaml | 200 | (not used) |
| 13 | https://raw.githubusercontent.com/resend/resend-openapi/main/resend.json | 200 | **OpenAPI 3.1.2, info.version 1.5.1, 67 paths / 108 operations** — primary schema source |
| 14 | https://raw.githubusercontent.com/resend/resend-openapi/main/openapi.yaml | 404 | guess |

Total fetches: 14 (limit 60). No request was made to `api.resend.com`. No API key was used or written anywhere (grep for `re_[A-Za-z0-9]{20,}` over the outputs dir is empty; examples use `process.env.RESEND_API_KEY` / `$RESEND_API_KEY`).

## 2. Tools and scripts used

| Tool | What for |
|---|---|
| `curl -s -o … -w "%{http_code}"` | all probes/downloads above |
| Python 3 (stdlib only, inline heredocs) | (a) parse `resend.json`: list operations, `securitySchemes` (bearerAuth only), servers; (b) recursive `$ref` expansion → `openapi-summary.txt` (1,719 lines) with params/request/response per operation; (c) split `llms-full.txt` into 360 per-page files by `# Title\nSource: URL` markers (`pages/<slug>.md`, `pages-index.txt`) |
| `strip.py` (small Python filter) | drop non-TS/curl code fences and Mintlify `theme={…}` attrs from pages before reading, to stay inside the time-box |
| `grep`/`sed`/`awk` | targeted extraction from pages |
| `Skill` tool → `anthropic-skills:skill-creator` | loaded as the snapshot skill requires (step 2); used its `references/schemas.md` for `evals/evals.json` format and `scripts/quick_validate.py` for validation |
| `Agent` tool × 3 (general-purpose, parallel) | assigned `references/sending.md`, `references/audiences-and-broadcasts.md`, `references/webhooks-and-receiving.md` + `references/domains-and-account.md` from a shared writing spec (`writing-spec.md`) — step 2.4 of the skill. Only `sending.md` and `webhooks-and-receiving.md` were delivered; the other two agents ended without writing, so I wrote `audiences-and-broadcasts.md` and `domains-and-account.md` myself from the same sources |
| Post-write review script (Python) | extracted every backticked snake_case identifier from the four reference files and checked it exists in `openapi-summary.txt` or `llms-full.txt` — 0 unknown identifiers (only the word `snake_case` itself); `grep -rE 're_[A-Za-z0-9_]{8,}'` over outputs — 0 hits |
| `Write`/`Edit` | SKILL.md, errors-and-limits.md, evals.json, verification-plan.md, this log |
| `quick_validate.py` (skill-creator) | frontmatter/structure validation — "Skill is valid!" |

Scratch dir: `/private/tmp/claude-501/-Users-chopinfeng-Workspace-Skillify/5ec28aad-b335-43f0-bc64-9891f0727768/scratchpad/eval1-old/` (llms.txt, llms-full.txt, resend-openapi.json, openapi-summary.txt, pages/, writing-spec.md, url-log.txt).

## 3. Skill steps followed / skipped

| Skill step | Done? | Notes |
|---|---|---|
| 1.1 Find `llms.txt` | ✅ | Found at both `/docs/llms.txt` and `/llms.txt`. Bonus: `llms-full.txt` exists and contains every page, so a single fetch replaced the "batch download with `xargs -P 8`" sub-step. |
| 1.2 Find OpenAPI | ✅ (detour) | Not at any of the three paths the skill suggests. The `llms.txt` "OpenAPI Specs" section is **bogus** — it lists `package.json`, `pnpm-lock.yaml`, `renovate.json` (a Mintlify export artefact). The real spec is on GitHub (`resend/resend-openapi`), linked from the docs/sdks page. Parsed and `$ref`-expanded with Python as instructed. |
| 1.3 Batch-download Markdown | ✅ (variant) | Confirmed `.md` suffix works (2 probes) but used `llms-full.txt` split locally instead of 360 individual fetches — same content, 1 fetch instead of 360. **Caveat discovered:** the Mintlify export strips the `name` attribute from `<ParamField>` / `<ResponseField>` tags, so parameter *names* are missing from the Markdown; the OpenAPI spec had to be the source of truth for names. |
| 1.4 Auth format | ✅ | `securitySchemes.bearerAuth` (http/bearer); docs add the mandatory `User-Agent` header (403/1010 otherwise) — not in the OpenAPI spec. |
| 2 Load skill-creator, init structure | ✅ | Loaded via `Skill` tool; structure per its anatomy (SKILL.md + references/ + evals/). SKILL.md is 67 lines (routing + cross-cutting rules only). |
| 2 Endpoint block format | ✅ | Spec'd in `writing-spec.md` (Endpoint / Purpose / Key params table / TS example / curl / Response / Gotchas). |
| 2.4 Parallel sub-agents | ✅ | 3 agents, one message, shared spec, explicit "do not invent fields" rule. I wrote SKILL.md and errors-and-limits.md myself (needs global view), as the skill suggests. |
| 3 Real API verification | ⏭️ **skipped by constraint** | No key. Replaced by `verification-plan.md`: 23 concrete checks (V1–V23), 8 of which are doc self-contradictions found during reading, each mapped to the reference section to update and to the eval scenario it would re-grade. Every unverified claim in the skill carries a header note; contradictions carry `⚠ VERIFY:`. |
| 4 Comparison experiment | ⏭️ partially | Scenarios written to `evals/evals.json` (8 evals, 4–5 expectations each) targeting "experienced dev guesses wrong" traps per the skill's guidance; runs **not** executed (task said draft only). Grading would use `run_eval.py`/`aggregate_benchmark.py` per the skill. |
| 5.1 `improve_description.py` | ⏭️ skipped | Needs `claude -p` runs and user review of trigger queries — out of scope for a draft; description written "pushy" by hand per skill-creator guidance. |
| 5.2 `package_skill.py` | ⏭️ partially | Ran `quick_validate.py` only (it is what package_skill calls first); did not produce a `.skill` archive since the deliverable is the directory. |
| 5.3 Split oversized references | n/a | Files are 150–320 lines each. |

## 4. Doc-vs-reality discrepancies recorded (for the eval writer)

1. `llms.txt` "OpenAPI Specs" section points at package/lockfile JSON, not a spec.
2. `llms-full.txt` / `.md` pages drop `ParamField` names → Markdown alone cannot tell you field names.
3. Idempotency key: 2nd SDK argument (idempotency guide) vs inside payload (Node quickstart AI-prompt block).
4. `scheduled_at`: natural language (docs) vs ISO-8601-only (OpenAPI description).
5. `restricted_api_key` listed under both 401 and 403.
6. Webhook retry schedule differs between `webhooks/introduction` and `webhooks/retries-and-replays`.
7. `resend.webhooks.verify()` example indexes `req.headers['svix-id']` on a `NextRequest`.
8. Chained `templates.create({...}).publish()` snippet is unlikely to type-check against a `{data,error}` promise.
9. Attachments guide's local-file example puts HTML in the `text` field.
10. Pagination errors are documented as 422 while the intro table maps bad params to 400.
11. OpenAPI lists **no request body** for `PATCH /emails/{email_id}` although the docs send `{ "scheduled_at": ... }` (found by the sending.md writer).
12. Received-email response fields `raw.download_url` / `html_format` (and the `html_format` query param) exist in the docs but not in the OpenAPI spec (found by the webhooks writer).
13. `GET /emails/{id}` docs sample includes `scheduled_at` and `tags[]`, absent from the OpenAPI response schema.

## 5. Output files (all under `…/old_skill/outputs/`)

| File | Lines | Author |
|---|---|---|
| `resend/SKILL.md` | 67 | me |
| `resend/references/sending.md` | 359 | sub-agent |
| `resend/references/webhooks-and-receiving.md` | 314 | sub-agent |
| `resend/references/audiences-and-broadcasts.md` | 206 | me (fallback) |
| `resend/references/domains-and-account.md` | 134 | me (fallback) |
| `resend/references/errors-and-limits.md` | 120 | me |
| `resend/evals/evals.json` | 114 (8 scenarios) | me |
| `verification-plan.md` | 65 (23 checks) | me |
| `process-log.md` | this file | me |

`⚠ VERIFY` markers across references: 26. `quick_validate.py`: "Skill is valid!".

## 6. Where the snapshot skill's instructions were unclear or did not fit

- Step 1.2 assumes the OpenAPI file lives on the docs host and that `llms.txt` "often lists it at the end" — here the `llms.txt` OpenAPI section was garbage (package/lockfile JSON) and the real spec was only discoverable via the docs' SDK page → GitHub. The skill should say "also check the vendor's GitHub org and the SDKs/OpenAPI docs page".
- Step 1.3 (`xargs -P 8` per-page download) is redundant when `llms-full.txt` exists; the skill should tell readers to try `llms-full.txt` first. It should also warn that Mintlify exports drop `ParamField` names, so Markdown alone is not enough for field tables.
- The skill hard-requires steps 3–4 (real key, real runs) with no guidance for the "no key yet" case; I improvised a verification plan + unverified-status banners. A sanctioned "draft mode" checklist would help.
- Step 2 says to load skill-creator and "init the skill directory per its spec" — skill-creator has no init script; only `quick_validate.py`/`package_skill.py`. The reference to `skills/bigmodel-cn/SKILL.md` as the model was off-limits per task constraints, so the SKILL.md layout was derived from the skill text alone.
- Step 5 (`improve_description.py`, `package_skill.py`) needs `claude -p` runs and user review; not runnable in a draft-only, time-boxed pass — the skill could mark it optional for drafts.
- Delegation guidance (2.4) does not mention that sub-agents may silently fail to write; a "verify each delegated file exists and passes a field-name cross-check" step would have saved a round-trip.
