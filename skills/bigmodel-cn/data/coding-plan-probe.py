"""Probe: standard API key vs Coding Plan key across bigmodel.cn endpoints.

Reads keys from env; never prints them. Only prints HTTP status + trimmed body.
  ZHIPUAI_API_KEY          -> standard platform key
  GLM_CODING_PLAN_API_KEY  -> Coding Plan key (personal/team), optional
"""
import json, os, sys, requests

KEYS = {
    "standard": os.environ.get("ZHIPUAI_API_KEY") or os.environ.get("BIGMODEL_API_KEY") or os.environ.get("ZAI_API_KEY"),
    "coding_plan": os.environ.get("GLM_CODING_PLAN_API_KEY") or os.environ.get("CODING_PLAN_API_KEY"),
}
print("keys available:", {k: bool(v) for k, v in KEYS.items()})

STD = "https://open.bigmodel.cn/api/paas/v4"
CODING = "https://open.bigmodel.cn/api/coding/paas/v4"
ANTH = "https://open.bigmodel.cn/api/anthropic"

CHAT = {"model": "glm-5.3-flash", "messages": [{"role": "user", "content": "回复一个字：好"}], "max_tokens": 16, "thinking": {"type": "disabled"}}

def call(label, method, url, key, json_body=None, headers=None):
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if headers: h.update(headers)
    try:
        r = requests.request(method, url, headers=h, json=json_body, timeout=60)
        body = r.text
        try:
            j = r.json()
            if "choices" in j:
                body = "OK choices[0].message.content=" + repr(j["choices"][0]["message"].get("content"))[:80] + f" usage={j.get('usage')}"
            elif "content" in j and isinstance(j["content"], list):
                body = "OK anthropic content=" + repr(j["content"][0].get("text"))[:80] + f" usage={j.get('usage')}"
            elif "data" in j and isinstance(j["data"], list):
                body = f"OK data[] len={len(j['data'])} first={json.dumps(j['data'][0], ensure_ascii=False)[:160]}"
            else:
                body = json.dumps(j, ensure_ascii=False)[:300]
        except Exception:
            body = body[:300]
        print(f"[{label}] {r.status_code} {body}")
    except Exception as e:
        print(f"[{label}] EXC {e}")

for kname, key in KEYS.items():
    if not key:
        continue
    print(f"\n===== key = {kname} =====")
    call(f"{kname} -> STD chat", "POST", f"{STD}/chat/completions", key, CHAT)
    call(f"{kname} -> CODING chat", "POST", f"{CODING}/chat/completions", key, CHAT)
    call(f"{kname} -> ANTH messages", "POST", f"{ANTH}/v1/messages", key,
         {"model": "glm-5.3-flash", "max_tokens": 16, "messages": [{"role": "user", "content": "回复一个字：好"}]},
         headers={"anthropic-version": "2023-06-01"})
    # anthropic endpoint with x-api-key header instead of Bearer
    try:
        r = requests.post(f"{ANTH}/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                          json={"model": "glm-5.3-flash", "max_tokens": 16, "messages": [{"role": "user", "content": "回复一个字：好"}]}, timeout=60)
        print(f"[{kname} -> ANTH messages (x-api-key)] {r.status_code} {r.text[:200]}")
    except Exception as e:
        print("EXC", e)
    call(f"{kname} -> CODING models list", "GET", f"{CODING}/models", key)
    call(f"{kname} -> STD models list", "GET", f"{STD}/models", key)
    call(f"{kname} -> CODING embeddings", "POST", f"{CODING}/embeddings", key, {"model": "embedding-3", "input": "hello"})
    call(f"{kname} -> CODING web_search", "POST", f"{CODING}/web_search", key, {"search_engine": "search_pro", "search_query": "智谱 GLM"})
    call(f"{kname} -> CODING images", "POST", f"{CODING}/images/generations", key, {"model": "glm-image", "prompt": "a red apple"})
    call(f"{kname} -> CODING chat glm-5.3 (thinking on)", "POST", f"{CODING}/chat/completions", key,
         {"model": "glm-5.3", "messages": [{"role": "user", "content": "1+1=?"}], "max_tokens": 64})
    call(f"{kname} -> CODING chat glm-4.5-air (legacy)", "POST", f"{CODING}/chat/completions", key,
         {"model": "glm-4.5-air", "messages": [{"role": "user", "content": "1+1=?"}], "max_tokens": 64})
    call(f"{kname} -> CODING chat glm-4.6v (vision model)", "POST", f"{CODING}/chat/completions", key,
         {"model": "glm-4.6v", "messages": [{"role": "user", "content": "1+1=?"}], "max_tokens": 64})
