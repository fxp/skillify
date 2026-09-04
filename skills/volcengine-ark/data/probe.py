#!/usr/bin/env python3
"""Live-API probe for the volcengine-ark skill (step 3 verification).

Usage:
  ARK_API_KEY=... ARK_AGENT_PLAN_API_KEY=... python3 probe.py [test-name ...]
Keys are read from env only; never printed. Each test prints: name, HTTP status, trimmed body.
Results are appended to verification-log.jsonl next to this script.
"""
import json, os, sys, time, urllib.request, urllib.error, datetime

STD = "https://ark.cn-beijing.volces.com/api/v3"
CODING = "https://ark.cn-beijing.volces.com/api/coding/v3"
PLAN = "https://ark.cn-beijing.volces.com/api/plan/v3"
PLAN_ANTHROPIC = "https://ark.cn-beijing.volces.com/api/plan"
CODING_ANTHROPIC = "https://ark.cn-beijing.volces.com/api/coding"
STD_KEY = os.environ.get("ARK_API_KEY")
PLAN_KEY = os.environ.get("ARK_AGENT_PLAN_API_KEY")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verification-log.jsonl")

def call(name, url, body=None, key=None, method=None, headers=None, timeout=90, raw_text=False):
    h = {"Content-Type": "application/json"}
    if key: h["Authorization"] = f"Bearer {key}"
    if headers: h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method or ("POST" if data else "GET"))
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, text = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        status, text = -1, repr(e)
    ms = int((time.time() - t0) * 1000)
    trimmed = text if raw_text else text[:1500]
    print(f"\n=== {name} -> HTTP {status} ({ms} ms)\n{trimmed}")
    with open(LOG, "a") as f:
        f.write(json.dumps({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "name": name, "url": url,
                            "method": req.get_method(), "body": body, "status": status, "ms": ms,
                            "response": text[:4000]}, ensure_ascii=False) + "\n")
    return status, text

def chat(base, key, model, extra=None, msgs=None, path="/chat/completions"):
    body = {"model": model, "messages": msgs or [{"role": "user", "content": "用一个词回答：1+1=?"}], "max_tokens": 64}
    if extra: body.update(extra)
    return body, f"{base}{path}"

TESTS = {}
def test(fn): TESTS[fn.__name__] = fn; return fn

# ---------- Agent Plan (dedicated key) ----------
@test
def plan_chat_basic():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.0-lite"); call("plan_chat_basic", u, b, PLAN_KEY)
@test
def plan_chat_auto():
    b, u = chat(PLAN, PLAN_KEY, "auto"); call("plan_chat_auto", u, b, PLAN_KEY)
@test
def plan_chat_ark_code_latest():
    b, u = chat(PLAN, PLAN_KEY, "ark-code-latest"); call("plan_chat_ark_code_latest", u, b, PLAN_KEY)
@test
def plan_chat_model_id_style():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2-0-lite-260428"); call("plan_chat_model_id_style(dated Model ID on plan)", u, b, PLAN_KEY)
@test
def plan_chat_developer_role():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.0-lite", msgs=[{"role": "developer", "content": "be brief"}, {"role": "user", "content": "hi"}])
    call("plan_chat_developer_role", u, b, PLAN_KEY)
@test
def plan_chat_thinking_disabled_glm():
    b, u = chat(PLAN, PLAN_KEY, "glm-5.3", extra={"thinking": {"type": "disabled"}}); call("plan_chat_thinking_disabled_glm-5.3", u, b, PLAN_KEY)
@test
def plan_chat_thinking_disabled_lite():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.0-lite", extra={"thinking": {"type": "disabled"}}); call("plan_chat_thinking_disabled_lite", u, b, PLAN_KEY)
@test
def plan_chat_kimi_k3_medium():
    b, u = chat(PLAN, PLAN_KEY, "kimi-k3"); call("plan_chat_kimi_k3 (Medium plan)", u, b, PLAN_KEY)
@test
def plan_embeddings_openai_style():
    s, t = call("plan_embeddings_openai_style", f"{PLAN}/embeddings", {"model": "doubao-embedding-vision", "input": "hello"}, PLAN_KEY)
    try: print("dims:", len(json.loads(t)["data"][0]["embedding"]), "| keys:", list(json.loads(t).keys()), "| usage:", json.loads(t).get("usage"))
    except Exception as e: print("dims parse fail", e)
@test
def plan_embeddings_multimodal():
    s, t = call("plan_embeddings_multimodal", f"{PLAN}/embeddings/multimodal", {"model": "doubao-embedding-vision", "input": [{"type": "text", "text": "hello"}]}, PLAN_KEY)
    try: print("dims:", len(json.loads(t)["data"]["embedding"]), "| keys:", list(json.loads(t).keys()), "| usage:", json.loads(t).get("usage"))
    except Exception as e: print("dims parse fail", e)
@test
def plan_responses_basic():
    call("plan_responses_basic", f"{PLAN}/responses", {"model": "doubao-seed-2.0-lite", "input": "用一个词回答：1+1=?", "max_output_tokens": 64}, PLAN_KEY)
@test
def plan_anthropic_messages_bearer():
    call("plan_anthropic_messages(Authorization Bearer)", f"{PLAN_ANTHROPIC}/v1/messages",
         {"model": "doubao-seed-2.0-lite", "max_tokens": 64, "messages": [{"role": "user", "content": "用一个词回答：1+1=?"}]},
         PLAN_KEY, headers={"anthropic-version": "2023-06-01"})
@test
def plan_anthropic_messages_xapikey():
    call("plan_anthropic_messages(x-api-key)", f"{PLAN_ANTHROPIC}/v1/messages",
         {"model": "doubao-seed-2.0-lite", "max_tokens": 64, "messages": [{"role": "user", "content": "用一个词回答：1+1=?"}]},
         None, headers={"x-api-key": PLAN_KEY or "", "anthropic-version": "2023-06-01"})
@test
def plan_image_gen():
    call("plan_image_gen seedream-5.0-lite", f"{PLAN}/images/generations",
         {"model": "doubao-seedream-5.0-lite", "prompt": "a red circle on white background, minimal", "size": "1K", "response_format": "url", "watermark": False}, PLAN_KEY, timeout=180)
@test
def plan_video_gen_should_fail_medium():
    call("plan_video_gen (Medium plan: expect refusal)", f"{PLAN}/contents/generations/tasks",
         {"model": "doubao-seedance-2.0-mini", "content": [{"type": "text", "text": "a cat walking --duration 2"}]}, PLAN_KEY)
@test
def plan_key_on_std_base():
    b, u = chat(STD, PLAN_KEY, "doubao-seed-2-0-lite-260428"); call("plan_key_on_std_base(/api/v3 with Agent Plan key)", u, b, PLAN_KEY)
@test
def plan_key_on_coding_base():
    b, u = chat(CODING, PLAN_KEY, "doubao-seed-2.0-lite"); call("plan_key_on_coding_base(/api/coding/v3 with Agent Plan key)", u, b, PLAN_KEY)
@test
def plan_models_list():
    call("plan_models_list GET /models", f"{PLAN}/models", None, PLAN_KEY)
@test
def plan_tokenization():
    call("plan_tokenization", f"{PLAN}/tokenization", {"model": "doubao-seed-2.0-lite", "text": ["hello world"]}, PLAN_KEY)
@test
def plan_chat_stream():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.0-lite", extra={"stream": True, "stream_options": {"include_usage": True}})
    call("plan_chat_stream", u, b, PLAN_KEY)
@test
def plan_chat_tool_choice_forced():
    tools = [{"type": "function", "function": {"name": "get_weather", "description": "get weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.0-lite", extra={"tools": tools, "tool_choice": {"type": "function", "function": {"name": "get_weather"}}, "thinking": {"type": "disabled"}},
                msgs=[{"role": "user", "content": "讲个笑话"}])
    call("plan_chat_tool_choice_forced", u, b, PLAN_KEY)
@test
def plan_chat_json_schema():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.0-lite", extra={"thinking": {"type": "disabled"}, "response_format": {"type": "json_schema", "json_schema": {"name": "ans", "schema": {"type": "object", "properties": {"answer": {"type": "integer"}}, "required": ["answer"], "additionalProperties": False}}}},
                msgs=[{"role": "user", "content": "1+1 等于几？"}])
    call("plan_chat_json_schema", u, b, PLAN_KEY)

# ---------- Standard API (Ark key) ----------
@test
def std_chat_basic():
    b, u = chat(STD, STD_KEY, "doubao-seed-2-0-lite-260428"); call("std_chat_basic", u, b, STD_KEY)
@test
def std_chat_model_name_style():
    b, u = chat(STD, STD_KEY, "doubao-seed-2.0-lite"); call("std_chat_model_name_style(lowercase name on /api/v3)", u, b, STD_KEY)
@test
def std_key_on_plan_base():
    b, u = chat(PLAN, STD_KEY, "doubao-seed-2.0-lite"); call("std_key_on_plan_base(/api/plan/v3 with Ark key)", u, b, STD_KEY)
@test
def std_key_on_coding_base():
    b, u = chat(CODING, STD_KEY, "doubao-seed-2.0-lite"); call("std_key_on_coding_base(/api/coding/v3 with Ark key, no Coding Plan subscription)", u, b, STD_KEY)
@test
def std_embeddings_openai_style():
    call("std_embeddings_openai_style", f"{STD}/embeddings", {"model": "doubao-embedding-vision-251215", "input": "hello"}, STD_KEY)
@test
def std_embeddings_multimodal():
    call("std_embeddings_multimodal", f"{STD}/embeddings/multimodal", {"model": "doubao-embedding-vision-251215", "input": [{"type": "text", "text": "hello"}]}, STD_KEY)
@test
def std_developer_role():
    b, u = chat(STD, STD_KEY, "doubao-seed-2-0-lite-260428", msgs=[{"role": "developer", "content": "be brief"}, {"role": "user", "content": "hi"}])
    call("std_developer_role", u, b, STD_KEY)
@test
def std_tokenization():
    call("std_tokenization", f"{STD}/tokenization", {"model": "doubao-seed-2-0-lite-260428", "text": ["hello world"]}, STD_KEY)

# ---------- batch 2 additions ----------
@test
def plan_chat_not_in_plan_model():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.1-pro"); call("plan_chat_not_in_plan_model(doubao-seed-2.1-pro)", u, b, PLAN_KEY)
@test
def plan_chat_old_model_id():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-1-8-251228"); call("plan_chat_old_model_id(doubao-seed-1-8-251228)", u, b, PLAN_KEY)
@test
def plan_chat_reasoning_effort_glm():
    b, u = chat(PLAN, PLAN_KEY, "glm-5.3", extra={"reasoning_effort": "low"}); call("plan_chat_reasoning_effort_low glm-5.3", u, b, PLAN_KEY)
@test
def plan_chat_max_completion_tokens_kimi():
    b, u = chat(PLAN, PLAN_KEY, "kimi-k3", extra={"max_completion_tokens": 400}); b.pop("max_tokens")
    call("plan_chat_kimi_k3 max_completion_tokens=400", u, b, PLAN_KEY)
@test
def plan_context_create():
    call("plan_context_create", f"{PLAN}/context/create", {"model": "doubao-seed-2.0-lite", "mode": "session", "messages": [{"role": "system", "content": "你是测试助手"}], "ttl": 60}, PLAN_KEY)
@test
def plan_files_list():
    call("plan_files_list GET /files", f"{PLAN}/files", None, PLAN_KEY)
@test
def plan_anthropic_claude_model_name():
    call("plan_anthropic_messages model=claude-sonnet-4-5 (Claude Code default if ANTHROPIC_MODEL unset)", f"{PLAN_ANTHROPIC}/v1/messages",
         {"model": "claude-sonnet-4-5", "max_tokens": 32, "messages": [{"role": "user", "content": "hi"}]}, PLAN_KEY, headers={"anthropic-version": "2023-06-01"})
@test
def plan_anthropic_thinking_disabled():
    call("plan_anthropic_messages thinking disabled (lite)", f"{PLAN_ANTHROPIC}/v1/messages",
         {"model": "doubao-seed-2.0-lite", "max_tokens": 32, "thinking": {"type": "disabled"}, "messages": [{"role": "user", "content": "用一个词回答：1+1=?"}]}, PLAN_KEY, headers={"anthropic-version": "2023-06-01"})
@test
def plan_responses_ark_code_latest():
    call("plan_responses ark-code-latest", f"{PLAN}/responses", {"model": "ark-code-latest", "input": "用一个词回答：1+1=?", "max_output_tokens": 64}, PLAN_KEY)
@test
def plan_embeddings_dims_1024():
    s, t = call("plan_embeddings_openai_style dimensions=1024", f"{PLAN}/embeddings", {"model": "doubao-embedding-vision", "input": "hello", "dimensions": 1024}, PLAN_KEY)
    try: print("dims:", len(json.loads(t)["data"][0]["embedding"]))
    except Exception as e: print("dims parse fail", e)
@test
def plan_embeddings_image_openai_style():
    call("plan_embeddings_openai_style with image part", f"{PLAN}/embeddings",
         {"model": "doubao-embedding-vision", "input": [{"type": "text", "text": "a cat"}, {"type": "image_url", "image_url": {"url": "https://ark-project.tos-cn-beijing.volces.com/images/view.jpeg"}}]}, PLAN_KEY)
@test
def plan_chat_service_tier_fast():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.0-lite", extra={"service_tier": "fast", "thinking": {"type": "disabled"}}); call("plan_chat_service_tier_fast", u, b, PLAN_KEY)


# ---------- batch 3 ----------
@test
def plan_image_gen_2k():
    call("plan_image_gen seedream-5.0-lite size=2k", f"{PLAN}/images/generations",
         {"model": "doubao-seedream-5.0-lite", "prompt": "a red circle on white background, minimal", "size": "2k", "response_format": "url", "watermark": False}, PLAN_KEY, timeout=180)
@test
def plan_chat_mini():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.0-mini", extra={"thinking": {"type": "disabled"}}); call("plan_chat_mini", u, b, PLAN_KEY)
@test
def plan_chat_glm_latest():
    b, u = chat(PLAN, PLAN_KEY, "glm-latest", extra={"reasoning_effort": "low"}); call("plan_chat_glm_latest alias", u, b, PLAN_KEY)
@test
def plan_chat_reasoning_effort_none_glm():
    b, u = chat(PLAN, PLAN_KEY, "glm-5.3", extra={"reasoning_effort": "none"}); call("plan_chat_reasoning_effort_none glm-5.3", u, b, PLAN_KEY)
@test
def plan_responses_store_and_get():
    s, t = call("plan_responses store=true", f"{PLAN}/responses", {"model": "doubao-seed-2.0-lite", "input": "记住数字 42", "max_output_tokens": 32, "store": True, "thinking": {"type": "disabled"}}, PLAN_KEY)
    try:
        rid = json.loads(t)["id"]
        call("plan_responses GET by id", f"{PLAN}/responses/{rid}", None, PLAN_KEY)
        call("plan_responses follow-up previous_response_id", f"{PLAN}/responses", {"model": "doubao-seed-2.0-lite", "input": "我刚说的数字是？只答数字", "previous_response_id": rid, "max_output_tokens": 16, "thinking": {"type": "disabled"}}, PLAN_KEY)
        call("plan_responses DELETE", f"{PLAN}/responses/{rid}", None, PLAN_KEY, method="DELETE")
    except Exception as e: print("store test parse fail", e)
@test
def plan_anthropic_dated_model_id():
    call("plan_anthropic_messages model=doubao-seed-2-0-lite-260428 (dated)", f"{PLAN_ANTHROPIC}/v1/messages",
         {"model": "doubao-seed-2-0-lite-260428", "max_tokens": 16, "thinking": {"type": "disabled"}, "messages": [{"role": "user", "content": "1+1=?"}]}, PLAN_KEY, headers={"anthropic-version": "2023-06-01"})
@test
def plan_anthropic_stream():
    call("plan_anthropic_messages stream", f"{PLAN_ANTHROPIC}/v1/messages",
         {"model": "doubao-seed-2.0-lite", "max_tokens": 16, "stream": True, "thinking": {"type": "disabled"}, "messages": [{"role": "user", "content": "1+1=?"}]}, PLAN_KEY, headers={"anthropic-version": "2023-06-01"})
@test
def plan_chat_prompt_cache_header():
    b, u = chat(PLAN, PLAN_KEY, "doubao-seed-2.0-lite", extra={"thinking": {"type": "disabled"}})
    call("plan_chat with X-Prompt-Cache-Id header", u, b, PLAN_KEY, headers={"X-Prompt-Cache-Id": "skill-probe-1"})

if __name__ == "__main__":
    names = sys.argv[1:] or list(TESTS)
    missing = [n for n in names if n not in TESTS]
    if missing: sys.exit(f"unknown tests: {missing}\navailable: {list(TESTS)}")
    for n in names:
        if n.startswith("plan") and not PLAN_KEY: print(f"skip {n}: ARK_AGENT_PLAN_API_KEY not set"); continue
        if n.startswith("std") and not STD_KEY: print(f"skip {n}: ARK_API_KEY not set"); continue
        TESTS[n]()

