# bigmodel-cn skill · value audit

## Where the skill actually changes the outcome

14 coding tasks run twice each — once with an agent that read the `bigmodel-cn` skill, once with an agent working from general knowledge only — then graded against the real `open.bigmodel.cn` API, not against assumptions.

| Metric | Value |
|---|---|
| Scenarios tested, across 5 rounds | 14 |
| Where the unskilled agent's code fails against the real API | 7 / 14 |
| Pass rate for the skilled agent, every round | 100% |
| Real documentation errors found and fixed mid-audit | 7 |

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

### `realtime.md` — An undocumented event precedes the one the spec describes
A live WebSocket session showed `session.created` arriving immediately on connect, before `session.updated` — an event the AsyncAPI spec never mentions. Code that only waits for `session.updated` can misread the handshake.

---

Every "win" and "tie" above was checked against `open.bigmodel.cn` with a real API key — not inferred from the OpenAPI spec alone, which itself proved wrong in two of the cases documented. Full transcripts and per-assertion grading for all 5 rounds are in `bigmodel-cn-workspace/`.
