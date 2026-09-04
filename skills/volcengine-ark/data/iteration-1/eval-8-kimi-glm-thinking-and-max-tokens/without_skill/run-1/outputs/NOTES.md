# NOTES — kimi-k3 vs glm-5.3 code review on Volcengine Ark

## Files

- `review_compare.py` — the script. `python review_compare.py [file] [--max-tokens N] [--json out.json]`
- `requirements.txt` — only dependency is the `openai` SDK (Ark is OpenAI-compatible).

## Endpoint and auth

- API key is read from `ARK_API_KEY`; the script exits with a clear message if it is missing. Nothing is hard-coded.
- Base URL defaults to `https://ark.cn-beijing.volces.com/api/coding/v3`, the endpoint Ark uses for the subscription (Agent/Coding Plan) models where `kimi-k3` / `glm-5.3` are addressed by plain model name instead of an endpoint id. If your plan lives under the standard endpoint, set `ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3`. Model ids are overridable via `ARK_KIMI_MODEL` / `ARK_GLM_MODEL` in case the console lists a versioned name.

## Limiting output length (~300 tokens)

Two layers, because `max_tokens` alone produces truncated reviews rather than short ones:

1. `max_tokens=300` (CLI `--max-tokens`) is the hard cap on the completion for both models.
2. The system prompt asks for a fixed short structure (verdict / at most 3 issues / at most 2 nits, under ~200 words, no code restatement, no closing remarks). This makes the model *plan* a short answer so it finishes before hitting the cap.

The script checks `finish_reason == "length"` and prints a warning when a review was actually cut off, and it reports `completion_tokens` per model in the summary table so you can see how close each one got to the budget.

## Controlling thinking

- **glm-5.3**: called with `extra_body={"thinking": {"type": "disabled"}}`, Ark's request-level switch for turning chain-of-thought off on reasoning-capable models. With thinking off, the whole 300-token budget goes to the visible answer and no `reasoning_content` is returned. The user prompt also says "直接给结论，不要展开推理过程" as a belt-and-braces instruction.
- **kimi-k3**: left at the model's default reasoning behaviour (the request was only to disable thinking on GLM). Caveat: on Ark, hidden reasoning tokens are counted inside `max_tokens`, so if Kimi thinks at length the visible answer can be shortened or cut. The script surfaces this: it reads `usage.completion_tokens_details.reasoning_tokens` when present, notes how many characters of `reasoning_content` came back, and warns on `finish_reason == "length"`. If that happens in practice, either raise `--max-tokens` for Kimi or add the same `thinking: disabled` flag to its `ModelSpec` (one-line change in `build_specs()`).

## Comparison output

Each model's review is printed in full, followed by a summary table with prompt/completion/reasoning token counts, finish reason and latency. `--json` writes the same data (including any `reasoning_content`) to a file for diffing.

## Not verified

No API calls were made while writing this (no key available). The parameter names above come from Ark's public OpenAI-compatible API; if `thinking` is rejected for a given model the SDK will raise an `APIError`, which the script catches and prints per model without aborting the other one.
