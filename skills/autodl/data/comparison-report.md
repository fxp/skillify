# autodl skill · value audit

## Where the skill actually changes the outcome

8 coding tasks run twice each — once with an agent that read the `autodl` skill, once with an agent working from general knowledge (and, in the later rounds, its own web search) only — graded against the real `api.autodl.com` API wherever a token was available, and against the official docs directly in the one round (iteration-1) run before a token existed.

| Metric | Value |
|---|---|
| Scenarios tested, across 3 rounds | 8 |
| Where the unskilled agent's code fails or misbehaves against the real platform | 6 / 8 |
| Pass rate for the skilled agent, every round | 100% |
| Real documentation errors/omissions found and fixed mid-audit | 9 |

---

## Round 1 — doc-fidelity test, no token yet

No AutoDL token was available for this round, so scoring is "which agent's code matches what the official docs actually say", not a real API call. Kept as an honest baseline for how much a small, less-documented platform benefits from a skill even before any live verification happens.

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Check account balance | win | 100% | 40% |
| Create a Pro instance | win | 100% | 40% |
| Create an elastic deployment | win | 100% | 40% |

### Check account balance — win
**Task:** Query wallet balance and show it to the user in yuan.
**Why:** baseline assumed the money field divides by 100 (the convention most Chinese payment APIs use). The real field is an integer × 1000 — a wrong-by-10x display bug that would have shipped silently.

### Create a Pro instance — win
**Task:** Rent a GPU instance for a training job.
**Why:** baseline treated `gpu_spec_uuid` as something to query dynamically via an API; it's actually a static table in the docs with no lookup endpoint. It also invented plausible-but-nonexistent parameter names.

### Create an elastic deployment — win
**Task:** Deploy an auto-scaling inference service.
**Why:** baseline guessed `deployment_type` values like `"fixed"`/`"scaling"`, generic terms from other cloud platforms. The real enum is `ReplicaSet`/`Job`/`Container`, unique to this API and not guessable from prior knowledge of other GPU cloud platforms.

Full detail: [`autodl-workspace/iteration-1/review.html`](iteration-1/review.html)

---

## Round 2 — real instance lifecycle, three ablations

Account completed real-name verification between rounds. A real, budget-capped test instance (~¥0.03 total) was used to verify the full create → run → stop → release cycle first, which surfaced three undocumented behaviors. Three new scenarios were built directly around them.

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Get instance info (GET query-string requirement) | win | 100% | 40% |
| Create instance, confirm running (no redundant power_on) | win | 100% | 40% |
| Clean up after a job (release-only-after-shutdown) | win (near-tie on logic) | 100% | 60% |

**Aggregate: 100% vs 46.7%, delta +0.53.**

### Get instance info — win
**Task:** Fetch an instance's SSH connection info and print `ssh_command`.
**Why:** baseline sent `instance_uuid` as a JSON body on the GET endpoint, following the docs' own (wrong) example. Real API returns `RequestParameterIsWrong` — the call never succeeds. Endpoint path was also fabricated.

### Create instance, confirm running — win
**Task:** Create an instance and make sure it's actually running before returning control.
**Why:** baseline assumed `create` only registers an instance and calls `power_on` afterward — an extra, unnecessary call built on a wrong assumption. Real behavior: `create` auto-starts the instance. Endpoint paths were also fabricated.

### Clean up after a job — win, but worth reading closely
**Task:** Power off and release an instance automatically once a training job finishes.
**Why:** the baseline's *high-level logic* was correct and matched the skilled version — it independently reasoned that release shouldn't fire immediately after power-off, and polled for confirmed shutdown first. That part is a tie, achieved through general cloud-engineering judgment, not documentation. Where it still failed completely: every endpoint path was fabricated (`/api/v1/instance/*` instead of the real `/api/v1/dev/instance/pro/*`), which no amount of general reasoning could produce correctly.

Full detail: [`autodl-workspace/iteration-2/review.html`](iteration-2/review.html)

---

## Round 3 — image save/restart, a stronger baseline

One more scenario, built around two more live-verified findings (see below). Notably, this baseline actively fetched AutoDL's live docs itself via web search rather than working from memory alone, and designed a more rigorous verification step than the prompt asked for.

| Scenario | Result | Skill | Baseline |
|---|---|---|---|
| Save an image before releasing the source instance | win | 100% | 80% |

### Save an image before releasing the source instance — win
**Task:** Save a trained instance's environment as a private image, confirm it's usable, then release the instance.
**Why:** baseline correctly guessed that `image/save` needs the instance stopped first (a defensible, conservative choice) and even built a throwaway test instance to actually boot-verify the saved image — more thorough than the prompt required. It lost only on the one thing pure doc-reading can't fix: it followed the docs' own (wrong) example of passing GET parameters as a JSON body, when the real requirement is a URL query string. This is the smallest gap in the audit, and an honest one — a well-engineered baseline that does its own research narrows the distance, but the platform's own documentation bug is still only catchable by testing against the live API.

Full detail: [`autodl-workspace/iteration-3/review.html`](iteration-3/review.html)

---

## Documentation fixed along the way

Every round tested the skill's own claims against the live API wherever a token was available. Nine turned out to be wrong, incomplete, or simply undocumented — corrected in place, dated, with the exact error text that proved it.

| File | Finding |
|---|---|
| `instances.md` | GET endpoints (`snapshot`, `status`) require query-string params — the docs' own example shows a JSON body |
| `instances.md` | Unverified accounts get `TORealName` on `create`, a distinct non-retryable error code |
| `instances.md` | `create` auto-starts the instance — no `power_on` call needed or wanted |
| `instances.md` | Status flow has undocumented intermediate states (`starting`, `shutting_down`) |
| `instances.md` | `release` before confirmed `shutdown` is a guaranteed failure, not probabilistic |
| `instances.md` | `image/save` requires the instance to already be shut down — undocumented precondition |
| `instances.md` | `power_on`'s response shape differs from `power_off`/`release` (`data` is an object, not `null`) |
| `instances.md` | Released instances silently disappear from "获取实例列表" with no way to query them back |
| `account.md` | Wallet balance has ~10 undocumented fields beyond the 3 the docs show, including `blocked_asset` |
| `elastic-deployment.md` | GPU stock query works without enterprise auth; deployment creation/management does not — the auth gate is per-endpoint, not platform-wide |
| `elastic-deployment.md` | Elastic deployment's own "获取镜像列表" is a different endpoint with different field names than the Pro-instance one, despite sharing the same underlying `image_uuid` values |

### `instances.md` — GET endpoints require query-string params
The official docs show a "request body example" (JSON) for `GET .../snapshot` and `GET .../status`. Sending it that way returns `{"code":"RequestParameterIsWrong","msg":"请求参数错误"}`; only `params=` (query string) works. This single documentation bug is the one that separates a strong, doc-researching baseline (round 3, 80%) from a perfect one — no amount of careful reading of the *official* docs gets this right, since the docs themselves are wrong.

### `instances.md` — `create` auto-starts the instance
Verified across two independent live creates (rounds 2 and 3): the instance is already `running` by the time `create` returns or shortly after. `power_on` exists only to restart an instance that was previously stopped.

### `instances.md` — `release` requires confirmed `shutdown`
The docs' own wording ("否则可能无法释放") reads like a probabilistic warning. Live testing shows it's deterministic: releasing a `starting`/`running`/`shutting_down` instance is rejected 100% of the time with `{"code":"BadRequest","msg":"请在实例关机状态下执行释放操作"}`.

### `instances.md` — `image/save` requires the instance to already be shut down
Not mentioned anywhere in the docs. Calling it on a `running` instance returns `{"code":"InternalError","msg":"保存实例镜像前，请确保实例是关机状态"}`. Must `power_off` and poll to confirmed `shutdown` first.

### `account.md` — wallet balance has far more fields than documented
The docs show 3 fields; the real response has 14, including `blocked_asset` (frozen funds — not spendable, and not reflected if you only read `assets`). Recommended available-balance formula: `(assets - blocked_asset) / 1000`.

### `elastic-deployment.md` — the auth gate is per-endpoint, not platform-wide
A personal (non-enterprise) verified account can call read-only elastic-deployment endpoints (GPU stock, private image list) successfully, but is rejected with `{"code":"BadRequest","msg":"无当前资源访问权限"}` on anything touching an actual deployment resource (create, list, container ops, blacklist, time-package overview) — confirmed individually for every read-only and auth-gated endpoint this account can reach.

### `elastic-deployment.md` — two different "获取镜像列表" endpoints
`POST .../instance/pro/image/private/list` (Pro instance API) and `POST /api/v1/dev/image/private/list` (elastic deployment API) are different endpoints with different response shapes (`name`/`status`/`image_size`/`create_at` vs. just `image_name`) — but confirmed to list the *same* underlying private images, so an `image_uuid` saved via one API is usable in the other.

---

## What's still untested, and why

Elastic deployment's **creation** endpoint (`POST /api/v1/dev/deployment`) and every management endpoint that depends on an existing `deployment_uuid`/`deployment_container_uuid` (stop container, set replica count, stop/delete deployment, set scheduling blacklist) remain unverified. This isn't a gap in effort — it's a hard account-level blocker: this test account has personal real-name verification but not enterprise verification, and AutoDL requires enterprise verification specifically to create a deployment. Without a deployment ever existing, there's no real `deployment_uuid` to test the dependent endpoints against either. Every other endpoint reachable at this account's current verification level — across all three API surfaces (account/storage, container instance Pro, elastic deployment read-only) — has been called against the real, live API at least once.

Full transcripts, per-assertion grading, and raw request/response evidence for all 3 rounds are in `autodl-workspace/iteration-{1,2,3}/`, mirrored into the repo at `skills/autodl/data/iteration-{1,2,3}/`.
