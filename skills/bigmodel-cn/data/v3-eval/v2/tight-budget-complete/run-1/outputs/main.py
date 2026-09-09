# -*- coding: utf-8 -*-
"""生成《2026 年中国新能源汽车出口市场简报》。

网关硬约束：单次请求的 max_tokens 绝对不能超过 1000。
应对策略：
  1. 选用 glm-4.6 并显式传 thinking.type="disabled"。
     （glm-5.3 在标准端点强制思考，思考 token 计入 max_tokens，
      小预算下会拿到 finish_reason=length 且 content 为空。）
  2. 全文拆成 5 节，每节独立一次请求，单次 max_tokens=800，
     拼装成完整正文，保证正文不少于 600 汉字。
  3. 每节校验 finish_reason 与字数；任何一节拿不到完整内容，
     或拼装后正文不足 600 汉字，都明确报出卡点，绝不输出半截。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
API_KEY_ENV = "ZHIPUAI_API_KEY"

# 网关对单次请求 max_tokens 的硬上限，绝不可超
GATEWAY_MAX_TOKENS_CAP = 1000
# 本脚本每次请求实际下发的 max_tokens（留 200 安全余量）
MAX_TOKENS_PER_REQUEST = 800

# 正文（不含大标题与小标题）的汉字数下限
MIN_BODY_HANZI = 600
# 单节正文的汉字数下限，低于此值视为该节生成失败
MIN_SECTION_HANZI = 130

MODEL = "glm-4.6"

REPORT_TITLE = "2026 年中国新能源汽车出口市场简报"

# (小标题, 该节的写作要点)
SECTIONS = [
    ("一、出口总体规模与增速",
     "全年新能源汽车出口量（万辆）、出口额（亿美元）、同比增速，"
     "以及新能源在整车出口总量中的占比。"),
    ("二、区域市场格局",
     "欧洲、东南亚、拉美、中东等主要目的区域的份额分化，"
     "增速最快的区域及其原因。"),
    ("三、竞争格局与头部企业",
     "比亚迪、奇瑞、上汽、吉利等头部企业的出口量或份额排位，"
     "纯电与插混的结构变化。"),
    ("四、主要挑战与风险",
     "欧盟反补贴关税、部分市场贸易壁垒、滚装船运力、"
     "海外本地化建厂与合规成本。"),
    ("五、趋势展望",
     "2026 年内及 2027 年展望：本地化生产比例、插混/增程出口增速、"
     "品牌出海与价格趋势。"),
]

HANZI_RE = re.compile(r"[一-鿿]")


def count_hanzi(text):
    """统计文本中的汉字数（不含标点、数字、字母）。"""
    return len(HANZI_RE.findall(text))


class GenerateError(Exception):
    """生成失败，message 里写清楚卡在哪一步、原因是什么。"""


def chat(messages):
    """调用一次 chat/completions，返回 (content, finish_reason, usage)。

    单次请求 max_tokens 固定为 MAX_TOKENS_PER_REQUEST，
    发送前断言不超过网关硬上限。
    """
    if MAX_TOKENS_PER_REQUEST > GATEWAY_MAX_TOKENS_CAP:
        raise GenerateError(
            "配置错误：MAX_TOKENS_PER_REQUEST=%d 超过网关上限 %d"
            % (MAX_TOKENS_PER_REQUEST, GATEWAY_MAX_TOKENS_CAP)
        )

    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise GenerateError(
            "卡在鉴权：环境变量 %s 未设置，无法调用 API。请先 export %s=<你的Key>"
            % (API_KEY_ENV, API_KEY_ENV)
        )

    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS_PER_REQUEST,
        # 关闭深度思考：思考 token 会计入 max_tokens，开着会在小预算下被截断
        "thinking": {"type": "disabled"},
        "temperature": 0.6,
        "stream": False,
    }
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    if resp.status_code != 200:
        raise GenerateError(
            "卡在第 %d 次 HTTP 请求：状态码 %s，响应片段 %s"
            % (0, resp.status_code, resp.text[:300])
        )

    try:
        data = resp.json()
    except ValueError:
        raise GenerateError("响应不是合法 JSON：%s" % resp.text[:300])

    if data.get("error"):
        err = data["error"]
        raise GenerateError(
            "API 返回错误：code=%s message=%s" % (err.get("code"), err.get("message"))
        )

    # 异步端点会静默换模型，同步端点按理不会，但读回 model 字段核对一遍
    echoed_model = data.get("model", MODEL)
    if not echoed_model.lower().startswith(MODEL):
        print("[警告] 响应 model 字段为 %s，与请求的 %s 不一致" % (echoed_model, MODEL))

    choices = data.get("choices") or []
    if not choices:
        raise GenerateError("响应中没有 choices：%s" % json.dumps(data, ensure_ascii=False)[:300])

    choice = choices[0]
    content = (choice.get("message") or {}).get("content") or ""
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}

    if finish_reason != "stop":
        # length=被 max_tokens 截断；sensitive=内容安全拦截
        raise GenerateError(
            "该节未正常结束：finish_reason=%s（length 表示被 max_tokens 截断，"
            "content 可能只有半截，不能交付）" % finish_reason
        )
    if not content.strip():
        raise GenerateError("该节 content 为空（finish_reason=%s）" % finish_reason)

    return content.strip(), finish_reason, usage


def generate_section(index, heading, points, attempt):
    """生成一节正文。返回正文文本（不含小标题）。"""
    outline = "\n".join("  %d. %s" % (i + 1, h) for i, (h, _) in enumerate(SECTIONS))
    messages = [
        {
            "role": "system",
            "content": (
                "你是一名新能源汽车行业的市场分析师。你正在为一份题为《%s》的简报逐节撰写正文。"
                "写作要求："
                "1) 只输出本节正文段落本身，不要输出小标题、编号、markdown 记号或任何开场白；"
                "2) 每节正文 150~220 个汉字，成段连贯，不使用列表；"
                "3) 必须包含具体数据（数量、金额、百分比、年份），数据基于行业公开口径给出合理估计即可；"
                "4) 不要写“如需”“下面是”之类的元话语。" % REPORT_TITLE
            ),
        },
        {
            "role": "user",
            "content": (
                "简报提纲如下：\n%s\n\n请撰写第 %d 节《%s》的正文。\n"
                "本节要点：%s\n"
                "只输出这一节的正文（150~220 个汉字，含具体数据），不要输出标题。"
                % (outline, index + 1, heading, points)
            ),
        },
    ]
    print("[请求 %d] 第 %d/%d 节《%s》（第 %d 次尝试，max_tokens=%d，<= 上限 %d）..."
          % (attempt, index + 1, len(SECTIONS), heading, attempt,
             MAX_TOKENS_PER_REQUEST, GATEWAY_MAX_TOKENS_CAP))
    content, finish_reason, usage = chat(messages)
    hanzi = count_hanzi(content)
    print("  finish_reason=%s, completion_tokens=%s, 本节汉字数=%d"
          % (finish_reason, usage.get("completion_tokens"), hanzi))
    if hanzi < MIN_SECTION_HANZI:
        raise GenerateError(
            "第 %d 节《%s》正文仅 %d 个汉字，低于单节下限 %d，内容不完整"
            % (index + 1, heading, hanzi, MIN_SECTION_HANZI)
        )
    return content


def generate_section_with_retry(index, heading, points, retries=2):
    last_err = None
    for attempt in range(1, retries + 2):
        try:
            return generate_section(index, heading, points, attempt)
        except GenerateError as exc:
            last_err = exc
            print("  [重试] %s" % exc)
            time.sleep(2)
    raise GenerateError(
        "卡在第 %d 节《%s》：重试 %d 次仍失败，最后原因：%s"
        % (index + 1, heading, retries, last_err)
    )


def main():
    # 缺 Key 是确定性失败，直接报出卡点，不进入重试
    if not os.environ.get(API_KEY_ENV):
        raise GenerateError(
            "卡在鉴权：环境变量 %s 未设置，无法调用 API。请先 export %s=<你的Key>"
            % (API_KEY_ENV, API_KEY_ENV)
        )

    print("模型：%s（thinking 已关闭，避免推理 token 占用 max_tokens 预算）" % MODEL)
    print("网关硬上限 max_tokens=%d，本脚本单次请求 max_tokens=%d，共 %d 次请求\n"
          % (GATEWAY_MAX_TOKENS_CAP, MAX_TOKENS_PER_REQUEST, len(SECTIONS)))

    bodies = []
    for i, (heading, points) in enumerate(SECTIONS):
        bodies.append(generate_section_with_retry(i, heading, points))
        print()

    # 拼装全文：大标题 + 各小标题 + 正文
    parts = [REPORT_TITLE, ""]
    for (heading, _), body in zip(SECTIONS, bodies):
        parts.append(heading)
        parts.append(body)
        parts.append("")
    full_text = "\n".join(parts).rstrip()

    # 正文汉字数（剔除大标题与小标题，只统计各节正文）
    body_hanzi = sum(count_hanzi(b) for b in bodies)
    total_hanzi = count_hanzi(full_text)

    print("=" * 60)
    print(full_text)
    print("=" * 60)
    print("正文字数（不含标题，汉字）：%d" % body_hanzi)
    print("全文字数（含标题，汉字）：%d" % total_hanzi)

    if body_hanzi < MIN_BODY_HANZI:
        print("卡在终检：正文仅 %d 个汉字，未达到 %d 的要求，以上内容不予交付。"
              % (body_hanzi, MIN_BODY_HANZI), file=sys.stderr)
        sys.exit(1)

    print("达标：正文 %d 汉字 >= %d；所有请求 max_tokens=%d <= %d。"
          % (body_hanzi, MIN_BODY_HANZI, MAX_TOKENS_PER_REQUEST, GATEWAY_MAX_TOKENS_CAP))


if __name__ == "__main__":
    try:
        main()
    except GenerateError as exc:
        print("生成失败：%s" % exc, file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as exc:
        print("生成失败：网络/HTTP 层出错：%s" % exc, file=sys.stderr)
        sys.exit(1)
