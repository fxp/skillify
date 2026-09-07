# bigmodel-cn skill · value audit

## Where the skill actually changes the outcome

25 coding tasks, 18 run twice and 7 run three times per configuration — once with an agent that read the `bigmodel-cn` skill, once with an agent working from general knowledge only — then graded against the real `open.bigmodel.cn` API, not against assumptions. Round 7 goes one step further: every generated script was actually executed with a real Coding Plan key, and only a script that ran and printed a model answer counts as a success. Round 6 (GLM Coding Plan) was graded first from the official docs and then re-verified live with a real Coding Plan key and a real standard key; every assertion held, and the probe turned up three undocumented behaviours (below).

| Metric | Value |
|---|---|
| Scenarios tested, across 7 rounds | 25 |
| Where the unskilled agent's code fails against the real API | 11 / 25 |
| Round 7 end-to-end execution success, Coding Plan key, 21 runs per side | skill 21 / 21 · baseline 21 / 21 |
| Pass rate for the skilled agent, every round | 100% |
| Real documentation errors found and fixed mid-audit | 14 |

---

## Round 1 — obvious tasks

Chat completion, image→video, an OpenAI-SDK migration. Common enough patterns that general training data already covers them — the audit's first honest result was a tie.

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Tool-calling weather bot | tie | 100% | 100% |
| Image → video pipeline | tie | 100% | 100% |
| OpenAI SDK migration + web search | tie | 100% | 100% |

### Tool-calling weather bot — tie
**Task:** GLM-5.3 command-line assistant that must call a weather function before answering.
**Why:** both agents produced a correct function-calling loop — this pattern is well represented in general knowledge.

### Image → video pipeline — tie
**Task:** GLM-Image generates a frame, CogVideoX-3 animates it, poll the async result.
**Why:** both agents got the endpoints, first-frame parameter, and polling loop right.

### OpenAI SDK migration + web search — tie
**Task:** Swap an existing OpenAI client over to bigmodel.cn, add web search.
**Why:** initially scored as a win — baseline omitted `search_engine`. A live retest showed the field is silently defaulted, not required. Corrected after the fact rather than left standing.

---

## Round 2 — GLM-5.3-specific traps

Four tasks built around behavior verified against the live API first, then handed to both agents as an ordinary feature request — nothing in the prompt hints at the trap.

**Model:** `glm-5.3` · 4 scenarios

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Force a tool call, every turn | win | 100% | 40% |
| Guaranteed-schema JSON extraction | win | 100% | 40% |
| Turn off reasoning for latency | win | 100% | 40% |
| Batch-classify 2,000 reviews, best model | win | 100% | 67% |

### Force a tool call, every turn — win
**Task:** Support bot that must call `lookup_order` before answering anything — even off-topic questions.
**Why:** baseline sets an OpenAI-style forced `tool_choice`, which is silently downgraded to `auto` on this API. On an off-topic message it retries 3 times, then gives up and prints an internal error instead of replying.

### Guaranteed-schema JSON extraction — win
**Task:** Pull name / issue type / urgency out of feedback text as JSON matching an exact schema.
**Why:** baseline uses `response_format:{type:"json_schema"}`. The API accepts it, then ignores it — returns prose, not JSON. Every retry fails the same way; extraction never succeeds.

### Turn off reasoning for latency — win
**Task:** High-concurrency FAQ bot — disable deep-thinking mode to cut cost and latency.
**Why:** baseline sends `thinking:{type:"disabled"}`. On GLM-5.3 that's a hard error, code 1210, every single call — the bot cannot run at all.

### Batch-classify 2,000 reviews, best model — win
**Task:** Sentiment classification via the Batch API — quality matters, pick the newest model.
**Why:** baseline picks glm-4.6 (a real, current model). Batch has its own model allow-list that excludes it — the upload is rejected before a single review is processed.

---

## Round 3 — same 4 tasks, glm-5.2

Re-run to separate model-specific quirks from platform-wide ones. Two stayed broken, two flipped to a tie for two different, equally honest reasons.

**Model:** `glm-5.2` · 4 scenarios

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Force a tool call, every turn | tie | 100% | 100% |
| Guaranteed-schema JSON extraction | win | 100% | 40% |
| Turn off reasoning for latency | tie | 100% | 100% |
| Batch job, user insists on glm-5.2 | win | 100% | 40% |

### Force a tool call, every turn — tie
**Task:** Same order-lookup bot, same wrong belief about `tool_choice`.
**Why:** this baseline's fallback path actually re-synthesizes the call locally when forcing fails — it works, just at 2 model calls per turn instead of 1. Good defensive code covered for a wrong assumption.

### Guaranteed-schema JSON extraction — win
**Task:** Same extraction task, different model.
**Why:** `json_schema` being ignored is a platform behavior, not a GLM-5.3 quirk — confirmed broken again here.

### Turn off reasoning for latency — tie
**Task:** Same request, glm-5.2 instead of glm-5.3.
**Why:** glm-5.2 isn't a forced-thinking model — `thinking:{type:"disabled"}` genuinely works here. The earlier failure really was GLM-5.3-specific; the skilled agent correctly used the direct switch instead of over-generalizing a rule that no longer applies.

### Batch job, user insists on glm-5.2 — win
**Task:** "Use glm-5.2, our other projects already standardized on it."
**Why:** baseline complies literally — glm-5.2 isn't Batch-whitelisted either, so the job fails at upload. The skilled version catches the conflict and substitutes a whitelisted model with a stated reason.

---

## Round 4 — new territory, two more ties

Voice naming and search citations — plausible traps that didn't pan out. Worth showing, not just the wins.

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Text-to-speech, pick a voice | tie | 100% | 100% |
| Web search with visible citations | tie | 100% | 100% |

### Text-to-speech, pick a voice — tie
**Task:** "A gentle female voice" for GLM-TTS.
**Why:** a made-up voice name errors with "音色不存在" — but baseline happened to guess `tongtong`, a real system voice, likely well-represented in public bigmodel.cn material.

### Web search with visible citations — tie
**Task:** Answer with sources listed — title and link — underneath.
**Why:** citations only appear if `search_result:true` is set explicitly. Baseline guessed it anyway, and its defensive multi-location field-probing happened to check the one place the data actually lives.

---

## Round 5 — the largest gap found

A capability OpenAI's API has no equivalent for at all — nothing to pattern-match against, so the baseline agent invented a plausible-sounding pipeline instead.

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Read a PDF contract directly, no local parsing | win | 100% | 40% |

### Read a PDF contract directly, no local parsing — win
**Task:** "The model should just read the file" — no PyPDF2, no pdfplumber.
**Why:** baseline invents a two-step upload-then-download flow using `GET /files/{id}/content` — an endpoint that explicitly rejects anything but Batch output files ("does not support downloading"). It never discovers that chat completions accepts a file directly, or that doing so requires the upload's `purpose` to be exactly `user_data` — `agent` and `code-interpreter` uploads succeed but fail silently later.

---

## Round 6 — GLM Coding Plan, a second billing system

Zhipu sells a subscription product, the GLM Coding Plan, that runs on **a different API key and a different base URL** from the pay-as-you-go API: `…/api/coding/paas/v4` instead of `…/api/paas/v4`, keys created on the plan page instead of the console, only `glm-5.3` / `glm-5.3-flash`, chat only. The skill previously said nothing about it. Four tasks were written the way real users phrase them — nobody says "which billing system am I on".

**Model:** `glm-5.3` · 4 scenarios · baseline 71%, skill 100%

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Batch docstrings via openai SDK on a Coding Plan | win | 100% | 83% |
| Point Claude Code at the Coding Plan | win | 100% | 60% |
| "Bought Max, still get 1113 — should I top up?" | win | 100% | 60% |
| Code-base RAG with embeddings on plan quota | win | 100% | 80% |

### Batch docstrings via openai SDK on a Coding Plan — win
**Task:** Add docstrings to a folder of Python files with `glm-5.3` through the `openai` SDK, key from the environment, user says they are on a Pro Coding Plan.
**Why:** baseline got the `/coding/paas/v4` base URL right — this one fact has spread widely through GitHub issues — but told the user to paste "the console API key", which is the wrong key family. It also disables thinking on `glm-5.3`, which cannot be disabled. The skilled agent read the key from a plan-specific variable, validated the model against the plan's list, and treated `1113` as a configuration error rather than retrying it.

### Point Claude Code at the Coding Plan — win
**Task:** Produce the `~/.claude/settings.json` env block that makes Claude Code run on `GLM-5.3` under the plan.
**Why:** baseline mapped the haiku tier to `glm-4.5-air`, a model the plan does not include, and again pointed the user to the console key page. The skilled agent reproduced the official mapping (`glm-5.3` / `glm-5.3-flash`), the `ANTHROPIC_AUTH_TOKEN` variable, and the plan-page key source. Grading this run also caught a type error in the new reference (`"1"` must be a string in `settings.json`), fixed before packaging.

### "Bought Max, still get 1113 — should I top up?" — win
**Task:** User pastes working-looking code hitting `…/api/paas/v4/` with a plan key and gets `429 / 1113 余额不足`.
**Why:** both agents diagnosed the wrong base URL and told the user not to top up. Baseline then said the plan key is "generated on the open-platform API Keys page" — the opposite of the official note that plan keys and platform keys are not interchangeable — and added an unfounded claim that off-plan models fall back to metered billing. Skill answer followed the reference's check order: key family → base URL → model → balance.

### Code-base RAG with embeddings on plan quota — win
**Task:** Embed a code base with `embedding-3` and answer with `glm-5.3`, "using the plan quota", raw `requests`.
**Why:** baseline correctly guessed that embeddings are not in the plan and split the two base URLs, then read **one** key for both, so half the calls would fail with `1113`. The skilled script reads a standard key for embeddings/rerank and a plan key for chat, with a targeted error message when either is missing. The skilled answer's claim that a plan key on `/embeddings` returns `1113` was later confirmed live.

---

## Round 7 — Coding Plan end-to-end: does the code actually run?

Rounds 1–6 graded code by reading it and probing the API separately. This round removes the reader: each agent had to write a `main.py` (or a `settings.json`), and the harness `bigmodel-cn-workspace/run_iter7.py` executed it with a real Coding Plan key exported and nothing else. Success means exit 0 plus a printed model answer; for the Claude Code config it means a live `/v1/messages` call succeeds for every model alias the config maps. Seven scenarios, three independent runs per side, 42 executions.

**Model:** `glm-5.3` / `glm-5.3-flash` · 7 scenarios × 3 runs · **skill 21/21, baseline 21/21 — tie**

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Plain `requests` call on the plan (`GLM_KEY`) | tie | 3/3 | 3/3 |
| openai SDK, streaming `glm-5.3-flash` | tie | 3/3 | 3/3 |
| anthropic SDK through `/api/anthropic` | tie | 3/3 | 3/3 |
| Function-calling loop (Tokyo time) | tie | 3/3 | 3/3 |
| Two keys: embeddings on standard, chat on plan | tie | 3/3 | 3/3 |
| Plan described only as "编程套餐 Pro，按 5 小时额度" | tie | 3/3 | 3/3 |
| Claude Code `settings.json`, every alias called live | tie | 3/3 | 3/3 |

### Why the baseline no longer fails
**Task family:** the plain integration path — right base URL, right key variable, a chat call that returns.
**Why:** by now the `…/api/coding/paas/v4` base URL and the `1113` symptom are all over GitHub issues, and the unskilled agent reproduced them in 21 of 21 runs, even when the plan was only described as "the 5-hour-quota monthly package". The baseline also split embeddings onto the standard key unprompted in all three two-key runs. On the narrow question "will the first request go through", the skill adds nothing here.

### Where the two sides still differ, invisible to a pass/fail harness
- **Claude Code haiku alias.** Baseline mapped haiku to `glm-4.5-air` in two of three runs. The live call returned 200 only because the coding endpoint silently reroutes `glm-4.5-air` to `glm-5.3-flash` (documented in `coding-plan.md` after the Round 6 probe). The skilled config used the official `glm-5.3-flash` in all three runs. Same exit code, different dependence on undocumented behaviour.
- **Thinking control.** Two baseline scripts sent `thinking: disabled` to `glm-5.3`; that only works on the coding endpoint and would return `1210` on the standard one. The skilled scripts used `reasoning_effort: low` in seven runs, which works on both.
- **Silent fallback.** Every baseline two-key script falls back to the pay-as-you-go key when the plan call fails, so a wrong base URL would quietly start billing the standard account. Two of three skilled runs also included a fallback, so this is a tendency, not a clean split.
- **Cost of the skill.** Skilled runs used about 37% more tokens and 36 s more wall-clock per task (reading the reference files), for identical execution results.

**Reading of the round:** the value of this skill for the Coding Plan is concentrated in the failure modes tested in Round 6 — wrong key family, off-plan models, off-plan capabilities, diagnosing `1113` — not in the happy path, which the base model already handles. The two rounds should be read together.

---

## Round 8 — recalibration: what survives a fair fight

Rounds 1-6 forbade the baseline from searching the web, scored against assertions the skill's own author wrote, and ran n=1 per cell. Round 8 re-runs two of the biggest claimed wins with all three of those fixed: **both sides may search the web**, grading is **100% by executing the script against the live API** (`recalibration/grade.py`, criteria frozen in `recalibration/PROTOCOL.md` before any run), and **n=3**.

| Scenario | As scored in rounds 2-3 | Recalibrated skill | Recalibrated baseline |
|---|---|---|---|
| Guaranteed-schema JSON extraction | 100% vs 40% | 1.000 ± 0.000 | **0.667 ± 0.471** |
| Force a tool call, every turn | 100% vs 40% | 1.000 ± 0.000 | **1.000 ± 0.000 — tie** |

### Force a tool call — the win does not survive
All three baselines independently found the `tool_choice`-is-auto-only limitation in the official function-calling docs and implemented the same local-fallback pattern the skill recommends. Executed against the live API with an off-topic message, all six scripts logged the tool call and answered. The original 100% vs 40% was mostly an artifact of forbidding web search, not a knowledge gap.

### JSON extraction — a real gap, but not the one that was claimed
No baseline fell for `response_format: json_schema`; that fact is also one web search away. The single failure (baseline run-2, reproducible on re-run) came from a different mistake: it never disabled thinking. Measured directly, `glm-4.6` costs 2.8s per request with `thinking: disabled` and 27.7s without (628-957 reasoning tokens) — a ~10x latency difference that blew the 300s budget on 8 records. All three skilled runs disabled it; 2 of 3 baselines did too.

### Round 8b — the Coding Plan claims, same treatment
The two headline Coding Plan scenarios were re-run the same way, with a real plan key injected and no standard key, so a wrong endpoint fails by construction.

| Scenario | As scored in round 6 | Recalibrated skill | Recalibrated baseline |
|---|---|---|---|
| Plan key returns 1113, produce a working fix | 100% vs 60% | 1.000 ± 0.000 | **1.000 ± 0.000 — tie** |
| Long-document summary on plan quota | 100% vs 80% | 1.000 ± 0.000 | **1.000 ± 0.000 — tie** |

All twelve runs scored 3/3 with no `1113` anywhere. Every baseline found `…/api/coding/paas/v4` in the official docs and cited the page; none picked `glm-4-long`, the in-name-only trap for a long-document task, all three choosing `glm-5.3` for its 1M context. One baseline went further than the skill does and flagged that the official terms exclude self-written API integrations from plan quota, shipping a switch back to the standard endpoint.

**A selection bias worth stating:** these scenarios were written the way a user would ask them, deliberately *not* built around the skill's live-probe findings that the docs omit — that a standard key also works on the coding endpoint, that `glm-4.6`/`glm-4.5-air` are silently rerouted, that `thinking: disabled` is rejected on one endpoint and honored on the other, that `1113` has three distinct causes. A scenario built on those would almost certainly favor the skill, and would also be a scenario chosen because the answer was already known. That knowledge is untested here, and these ties do not refute it.

### What this round establishes
Across all four recalibrated scenarios — 24 executions — the skilled side scored 12/12 and the baseline 11/12; three of the four are outright ties. The `100% vs 40%` magnitude does not hold under symmetric conditions. The baseline's stdev of 0.471 on the same configuration — one run scoring 0, two scoring 1.0 — is direct evidence that the earlier n=1 rounds were sampling noise as signal. It does **not** establish significance: 3/3 vs 2/3 is Fisher p = 1.0. Read it as a magnitude correction, not a new claim. Full write-up: `recalibration/RESULTS.md` and `recalibration-cp/RESULTS.md`.

---

## Round 9 — a different executor, and the first significant win

Rounds 1-8 all ran Claude as the executing agent. Round 9 swaps the brain for **GLM-5.3** — Claude Code CLI kept purely as the harness, pointed at `…/api/anthropic` with a Coding Plan key, which is one of Zhipu's officially supported tools for the plan. WebFetch still works in that configuration, so both sides keep researching the docs. n=5, graded purely by execution.

The first two scenarios tied, and the reason is instructive: **a trap only discriminates when the task closes the detour**. Both sides picked cheap older models for a batch job (all whitelisted), and 5 of 6 skipped the upload path entirely by inlining the PDF as base64. Rewriting the tasks to close those routes — "quality matters, use the best model you can" and "we'll ask many rounds, upload once and reuse the file_id" — produced the first significant separation in the whole audit.

| Scenario | Skill | Baseline | Full marks | Fisher p |
|---|---|---|---|---|
| Batch job, "use the best model" | **1.000 ± 0.000** | **0.000 ± 0.000** | 5/5 vs 0/5 | **0.0079** |
| PDF, upload once and reuse file_id | **0.900 ± 0.200** | **0.250 ± 0.000** | 4/5 vs 0/5 | **0.0476** |
| Cited web answers (after fixing the skill) | **0.933 ± 0.133** | **0.600 ± 0.133** | 4/5 vs 0/5 | **0.0476** |
| RAG indexing (64-item embedding cap) | 1.000 | 1.000 | tie | — |

### Where the separation comes from
- **Batch**: both sides honestly chased "the best model". Skilled runs picked `glm-5.1` 5/5 — the strongest model *inside Batch's separate whitelist*. Baselines picked `glm-5.3`, the platform flagship, 5/5 — rejected at **file upload** with `1210 模型名称错误`. That whitelist exists only in the error message, not in the docs prose.
- **PDF**: skilled runs used `purpose=user_data` 5/5. Baselines used `file-extract` / `agent` / nothing, and every upload **succeeded** — one even printed the `file_id` and suggested reusing it next time — before failing at reference time with `1210 文件解析失败`.

### The round that found a bug in the skill itself
The citation scenario first came out *against* the skill (0.600 vs 0.667). All ten scripts were written correctly — `search_result: true` set, `link` field read — yet no run produced a URL. The cause was the skill's own advice to "pass `search_engine` explicitly (e.g. `search_pro`)": measured live, `search_pro` and `search_std` return ten sources whose `link` is an **empty string**, while `search_pro_bing` / `_jina` / `_quark` / `_sogou` return real URLs. Two of those working engines aren't listed in the official parameter table at all. The skilled runs failed *because they followed the skill faithfully*.

After correcting `tools.md` and `chat.md`, the same scenario re-ran with complete separation in engine choice: skilled runs picked bing/quark/sogou, baselines picked `search_pro` 5/5. **A wrong manual is worse than none — it makes the agent fail consistently.**

### Two grader bugs, caught and fixed
Execution-based grading is more objective than assertions, but the grader needs auditing too. Naive substring matching produced a false positive (scripts whose comments said "we do *not* use PyPDF2" were flagged as using it — fixed with AST import detection) and a false negative plus a false positive on error codes (a successful batch id `batch_2096812104876032000` contains `1210`; a real failure printed the message without the code — fixed by matching `code: 1210` structurally or the known error text). Correcting them moved the batch scenario's skilled mean from 0.933 to 1.000.

---

## Documentation fixed along the way

Every audit round tested the skill's own claims against the live API. Seven turned out to be wrong or incomplete — corrected in place, dated, with the exact error text that proved it.

| File | Finding |
|---|---|
| `chat.md` | `web_search.search_engine` requirement is inconsistent across two entry points |
| `chat.md` | `web_search` citations need an explicit opt-in |
| `chat.md` | File input in chat requires `purpose=user_data` specifically |
| `agents-assistant-knowledge.md` | Agent response `content` is an object, not a string |
| `files-batch.md` | Batch accepts a fixed, dated model list — not the general catalog |
| `files-batch.md` | Two smaller Batch corrections (`request_counts` nesting, `custom_id` minimum length) |
| `realtime.md` | An undocumented event precedes the one the spec describes |

### `chat.md` — `web_search.search_engine` requirement is inconsistent across two entry points
Required and enforced on the standalone `/paas/v4/web_search` endpoint (real error `1214` if missing) — but silently defaulted when used as a chat-completions tool. Same field name, different platform behavior depending on which door you use.

### `chat.md` — `web_search` citations need an explicit opt-in
`search_result:true` must be set or the response's `web_search` array — the actual source list — never appears, even though the search itself still ran and shaped the answer.

### `chat.md` — File input in chat requires `purpose=user_data` specifically
Files uploaded with `agent` or `code-interpreter` — both plausible, both accepted at upload time — fail when referenced in a chat message: `"文件解析失败，请检查文件可访问性和格式"`.

### `agents-assistant-knowledge.md` — Agent response `content` is an object, not a string
Documented example showed plain text; the real shape is `{"type":"text","text":"..."}`. Code written against the old example would try string operations on a dict.

### `files-batch.md` — Batch accepts a fixed, dated model list, not the general catalog
Confirmed rejections for glm-4.6, glm-5.1's newer siblings, and both 5.2 and 5.3. Every model this skill recommends elsewhere for quality has to be checked against this separate list first.

### `files-batch.md` — Two smaller Batch corrections
Request counts live under a nested `request_counts` object, not top-level fields as the old example showed. Separately, `custom_id` has an undocumented 6-character minimum — anything shorter fails upload with error `1214`.

### `agents-assistant-knowledge.md` — the knowledge-base API never returns a failing HTTP status
Every endpoint under `llm-application/open/*` and `/zrag/*` answers `HTTP 200` even when the call failed; the real outcome sits in the body's `code`. Querying a non-existent knowledge base returns `200` + `{"code":100013,"message":"知识库不存在"}`; a wrong multipart field name returns `200` + `{"code":400,...}`. `raise_for_status()` never fires, so a RAG pipeline built the obvious way carries the error forward silently. Recorded with the contract spelled out.

### `agents-assistant-knowledge.md` — a successful upload does not mean a retrievable document
Uploading returns `200` with a `documentId` in `data.successInfos`, which reads as complete success. Vectorisation then runs in the background, and when it fails nothing tells you: `POST /knowledge/retrieve` keeps returning `200` + `{"code":200,"data":[]}` forever — indistinguishable from "no relevant content". The only signal is `GET /document/{id}`, whose `embedding_stat` (0 pending / 1 ready / 2 failed) and `failInfo.embedding_msg` carry the truth. On the test account all three uploaded formats — `.pdf`, `.md`, `.txt` — ended at `embedding_stat=2` with `知识不可用，文档损坏` while storage sat at 6,196 of 5,000,000 words, so this may be account-scoped; either way the lesson is to poll for `embedding_stat == 1` rather than assume. The skill now says so.

### `agents-assistant-knowledge.md` — the Assistant example fails if copied verbatim
The reference said `stream` defaults to `true` and showed a synchronous example with `"stream": false`. Measured 2026-09-07 against `glm-4-assistant`: omitting `stream` **and** passing `false` both return `1212 当前模型不支持SYNC调用方式`; only `true` yields the `text/event-stream` response. So the documented default is wrong in the direction that breaks code, and the shipped example was one of the two failing forms. Corrected in the parameter table and both examples.

### `tools.md` / `chat.md` — the search engine decides whether you get any links at all
Sources come back with a `link` field either way, but measured live on 2026-09-07 it is an **empty string** for `search_std` and `search_pro`, and a real URL for `search_pro_sogou` (50 results), `search_pro_quark`, `search_pro_jina` and `search_pro_bing`. The last two aren't in the official parameter table. The skill had been recommending `search_pro` — corrected, with the comparison table in place, because any product that promises checkable citations breaks silently on the wrong engine.

### `chat.md` / `models.md` — the async endpoint silently swaps the model
Verified 2026-09-07 by reading back the echoed `model`: `POST /async/chat/completions` turns `glm-4.6` into `glm-4.7` and `glm-4.7` into `glm-4.7-ali`, a name that appears nowhere in the docs; `glm-4.5-air` and `glm-5.3` pass through untouched. The synchronous endpoint never substitutes. Anything needing reproducibility or billing reconciliation has to read the echoed model rather than trust the request.

### `coding-plan.md` (new) — The Coding Plan is a separate key + endpoint, not a discount tier
The skill's front page, `sdk-and-compat.md`, `errors-and-limits.md` and `models.md` all assumed one key family and one base URL. Official Coding Plan pages document a second family: `…/api/coding/paas/v4` (OpenAI-compatible) and the shared `…/api/anthropic` (Anthropic-compatible), keys from `bigmodel.cn/coding-plan/personal/overview` or the team plan page, `glm-5.3` / `glm-5.3-flash` only, quota on a 5-hour + 7-day cycle, usage restricted to designated coding tools. Live probe confirmed: plan key on the standard endpoint → `429 / 1113`; plan key on embeddings, rerank, tokenizer, async chat, standalone web search, images → the same `1113`; plan key on `reader` → works. Three things the docs do not say: a **standard** key works on the coding endpoint for everything (it is not plan-only); `glm-4.6` and `glm-4.5-air` are silently rerouted to `glm-5.3-flash` alongside the four documented aliases; vision models `glm-4.6v` / `glm-5v-turbo` answer under the plan.

### `chat.md` / `models.md` — "glm-5.3 thinking cannot be disabled" is only true on the standard endpoint
`thinking:{type:"disabled"}` on `glm-5.3` / `glm-5.3-flash` returns `1210` on `…/api/paas/v4` but is accepted on `…/api/coding/paas/v4` with `reasoning_tokens: 0` — with either key. The two endpoints validate parameters differently; the skill now says so instead of stating one rule.

### `realtime.md` — An undocumented event precedes the one the spec describes
A live WebSocket session showed `session.created` arriving immediately on connect, before `session.updated` — an event the AsyncAPI spec never mentions. Code that only waits for `session.updated` can misread the handshake.

---

**Conditions that were not recorded at the time, and matter:** rounds 1-6 ran n=1 per configuration and the baseline agents were instructed not to search the web. Round 8 shows how much of the measured gap depends on those two choices. Every "win" and "tie" above was checked against `open.bigmodel.cn` with a real API key — rounds 1–5 with a standard key, rounds 6 and 7 with both a standard key and a Coding Plan key (`bigmodel-cn-workspace/coding-plan-probe.py`, `bigmodel-cn-workspace/run_iter7.py`). The OpenAPI spec and the Coding Plan pages each proved incomplete in ways only a live call reveals. Full transcripts, per-assertion grading and (for round 7) captured stdout/stderr of every execution are in `bigmodel-cn-workspace/`.
