"""联网问答小工具：调用智谱 GLM（带联网搜索）回答一个写死的问题，
并把接口真实返回的搜索来源（标题 + 可点击 URL）打印到 stdout。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

只依赖 requests + 标准库。
"""
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"

# 要拿到可点击的来源链接，搜索引擎不能随便选：
# 实测 search_std / search_pro 返回的来源 link 恒为空串（HTTP 200、不报错），
# 只有下列引擎才带真实链接。search_pro_bing 未列在官方参数表但实测可用，
# 故放在首位，报参数错误时依次回退。
SEARCH_ENGINES = ["search_pro_bing", "search_pro_quark", "search_pro_sogou"]


def ask_with_web_search(question: str, api_key: str) -> dict:
    """调用 chat/completions 并开启联网搜索，返回响应 JSON。"""
    last_error = "unknown"
    for engine in SEARCH_ENGINES:
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": question}],
            "tools": [
                {
                    "type": "web_search",
                    "web_search": {
                        "enable": True,
                        "search_engine": engine,
                        # 关键：不显式传 search_result=true 时，搜索照跑、答案照给，
                        # 但响应体里完全没有 web_search 来源数组，出处会静默丢失。
                        "search_result": True,
                        "search_recency_filter": "oneYear",
                    },
                }
            ],
            # glm-5.3 强制开启思考，且思考 token 计入 max_tokens，
            # 预算给小了会导致 finish_reason=length、答案为空串。
            "max_tokens": 4096,
            "stream": False,
        }
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=120,
        )
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.ok and "error" not in body:
            return body

        err = body.get("error", {}) or {}
        last_error = (
            f"HTTP {resp.status_code}, "
            f"code={err.get('code')}, message={err.get('message') or resp.text[:200]}"
        )
        # 只有参数类错误（如引擎名不被接受，通常返回 400）才值得换引擎重试；
        # 鉴权失败、余额不足等换引擎也没用，直接跳出报错。
        if resp.status_code != 400:
            break
    raise RuntimeError(f"调用智谱 API 失败：{last_error}")


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）")

    body = ask_with_web_search(QUESTION, api_key)

    choice = body["choices"][0]
    answer = (choice["message"].get("content") or "").strip()
    finish_reason = choice.get("finish_reason", "")
    # 空答案的判据是 finish_reason，不是空串本身。
    if finish_reason == "length":
        sys.exit("错误：答案被 max_tokens 截断（finish_reason=length），请调大 max_tokens 重试")
    if not answer:
        sys.exit(f"错误：模型未返回内容（finish_reason={finish_reason}）")

    print(answer)
    print()

    # 来源列表只取接口真实返回的 web_search 数组，绝不让模型自己编链接。
    sources = body.get("web_search") or []
    clickable = [s for s in sources if (s.get("link") or "").strip()]
    missing = len(sources) - len(clickable)

    print("=" * 64)
    print("参考来源（联网搜索接口真实返回，可点击核对）")
    print("=" * 64)
    if not clickable:
        sys.exit("错误：接口本次未返回任何带链接的来源，无法提供可核对的 URL")

    for i, src in enumerate(clickable, 1):
        title = (src.get("title") or "(无标题)").strip() or "(无标题)"
        link = src["link"].strip()
        meta = " / ".join(
            x for x in ((src.get("media") or "").strip(), (src.get("publish_date") or "").strip()) if x
        )
        header = f"[{i}] {title}" + (f"（{meta}）" if meta else "")
        print(f"{header}\n    {link}")
    if missing:
        print(f"\n注：另有 {missing} 条来源因接口未返回链接（link 为空）未展示。")


if __name__ == "__main__":
    main()
