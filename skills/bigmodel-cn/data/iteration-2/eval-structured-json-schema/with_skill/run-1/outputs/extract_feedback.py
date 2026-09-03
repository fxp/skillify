#!/usr/bin/env python3
"""
从客户反馈文本中抽取结构化信息（name / issue_type / urgency），
使用智谱开放平台（bigmodel.cn）GLM-5.3 模型，通过标准库风格的 requests 直接调 HTTP 接口。

重要背景（来自 bigmodel-cn 技能包 references/chat.md 第五节）：
    智谱开放平台目前 **没有** 类似 OpenAI 的 `response_format.type = "json_schema"`
    的原生强约束模式。`response_format` 只支持 `text` / `json_object` 两种取值：
      - `json_object` 只保证模型输出是"语法合法的 JSON"（不会夹带解释性文字、
        不会输出非 JSON 内容），但 **不保证** 输出符合你给定的字段结构 / 类型 / 枚举值。
    因此，"结果一定合法且严格符合 JSON Schema" 这件事，平台本身无法从服务端保证，
    必须在客户端做两件事来逼近这个保证：
      1. 把目标 JSON Schema 明确写进 system prompt，并开启 `response_format: json_object`，
         把模型"跑偏"的概率降到最低；
      2. 拿到结果后用 JSON Schema 做二次校验（本脚本内置轻量校验器，若环境中装了
         `jsonschema` 库则优先使用它），校验失败就把错误信息喂回给模型，
         要求它修正后重新输出，最多重试 N 次；仍失败则抛出明确异常，
         而不是把一个不合规的字典悄悄传给下游系统。

用法：
    export ZHIPUAI_API_KEY="你的真实 API Key"   # 从 bigmodel.cn 控制台获取，切勿硬编码
    python extract_feedback.py

注意：本文件中的 API Key 通过环境变量读取，仓库里不包含任何真实 Key。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

# ---------------------------------------------------------------------------
# 1. 基础配置
# ---------------------------------------------------------------------------

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"

# GLM-5.3 强制开启深度思考（thinking），无法关闭，只能用 reasoning_effort 调节强度，
# 取值仅接受 low / high / max（见 references/models.md 与 references/chat.md 第六节）。
# 这是一个简单的信息抽取任务，不需要长链条推理，这里选 "low" 以降低延迟和 token 消耗；
# 如果实测发现抽取质量不稳定，可以调高到 "high" 甚至 "max"。
REASONING_EFFORT = "low"

REQUEST_TIMEOUT_SECONDS = 60
MAX_REPAIR_ATTEMPTS = 3  # 首次请求 + 最多 N 次"喂回错误重试"

# ---------------------------------------------------------------------------
# 2. 目标 JSON Schema
#
# 字段的具体取值集合（issue_type / urgency 的枚举）是本脚本代为设计的合理默认值，
# 因为用户没有给出业务方自己的分类体系。落地前请根据实际业务口径替换这里的枚举值。
# ---------------------------------------------------------------------------

FEEDBACK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "客户姓名；若原文完全没有提及姓名，返回空字符串 \"\"",
        },
        "issue_type": {
            "type": "string",
            "enum": [
                "billing",       # 账单/费用问题
                "technical",     # 产品/技术故障
                "shipping",      # 物流/配送
                "account",       # 账户/登录相关
                "complaint",     # 一般投诉/服务态度
                "inquiry",       # 咨询/一般问题
                "other",         # 其他，无法归类
            ],
            "description": "问题类型，必须是给定枚举值之一",
        },
        "urgency": {
            "type": "string",
            "enum": ["low", "medium", "high", "urgent"],
            "description": "紧急程度，必须是给定枚举值之一",
        },
    },
    "required": ["name", "issue_type", "urgency"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# 3. 轻量 JSON Schema 校验器（无第三方依赖时的兜底实现）
#
# 只覆盖本脚本实际用到的子集：type=object/string、properties、required、
# enum、additionalProperties=False。如果环境里装了 `jsonschema` 库，
# 优先使用它做更完整、更标准的校验。
# ---------------------------------------------------------------------------


class SchemaValidationError(ValueError):
    """校验失败时抛出，message 里带上具体原因，方便回填给模型重试。"""


def _validate_with_jsonschema_lib(data: Any, schema: dict[str, Any]) -> None:
    import jsonschema  # type: ignore[import-not-found]

    validator_cls = jsonschema.Draft7Validator
    validator = validator_cls(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        messages = [f"- {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
        raise SchemaValidationError("JSON Schema 校验失败：\n" + "\n".join(messages))


def _validate_minimal(data: Any, schema: dict[str, Any]) -> None:
    """不依赖第三方库的最小化校验，仅覆盖本脚本用到的 schema 特性。"""
    if not isinstance(data, dict):
        raise SchemaValidationError(f"顶层结果必须是 JSON object，实际拿到: {type(data).__name__}")

    required = schema.get("required", [])
    missing = [key for key in required if key not in data]
    if missing:
        raise SchemaValidationError(f"缺少必填字段: {missing}")

    properties: dict[str, Any] = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = [key for key in data.keys() if key not in properties]
        if extra:
            raise SchemaValidationError(f"出现了 schema 之外的多余字段: {extra}")

    for key, value in data.items():
        prop_schema = properties.get(key)
        if prop_schema is None:
            continue

        expected_type = prop_schema.get("type")
        if expected_type == "string" and not isinstance(value, str):
            raise SchemaValidationError(f"字段 {key} 应为字符串，实际是 {type(value).__name__}")

        enum_values = prop_schema.get("enum")
        if enum_values is not None and value not in enum_values:
            raise SchemaValidationError(f"字段 {key} 的取值 {value!r} 不在允许的枚举范围内: {enum_values}")


def validate_against_schema(data: Any, schema: dict[str, Any]) -> None:
    """优先用 jsonschema 库校验；未安装则退回内置的最小化校验。"""
    try:
        _validate_with_jsonschema_lib(data, schema)
    except ImportError:
        _validate_minimal(data, schema)


# ---------------------------------------------------------------------------
# 4. 调用 GLM-5.3 并抽取结构化信息
# ---------------------------------------------------------------------------


def _build_system_prompt(schema: dict[str, Any]) -> str:
    schema_text = json.dumps(schema, ensure_ascii=False, indent=2)
    return (
        "你是客户反馈信息抽取助手。请从用户提供的客户反馈文本中抽取结构化信息，"
        "并且只返回一个 JSON 对象，不要输出任何 JSON 之外的文字、markdown 代码块标记或解释。\n\n"
        "返回的 JSON 必须严格符合下面这份 JSON Schema（字段名、类型、枚举取值都不能偏离）：\n"
        f"{schema_text}\n\n"
        "抽取规则：\n"
        "- name：客户姓名。原文没有提及姓名时，返回空字符串 \"\"，不要编造姓名。\n"
        "- issue_type：从 schema 给定的枚举值中选出最贴切的一个，不确定时选 \"other\"。\n"
        "- urgency：结合语气、措辞（如是否提到损失、截止时间、多次投诉、威胁投诉/退款等）"
        "判断紧急程度，从 schema 给定的枚举值中选出最贴切的一个。\n"
        "- 严禁输出 schema 之外的字段，严禁省略必填字段。"
    )


def extract_feedback(
    feedback_text: str,
    *,
    api_key: str,
    schema: dict[str, Any] = FEEDBACK_SCHEMA,
    model: str = MODEL,
    reasoning_effort: str = REASONING_EFFORT,
    max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """
    调用 GLM-5.3 从一段客户反馈文本中抽取结构化信息，返回一个已通过 schema 校验的 dict。

    保证行为：
      - 成功时，返回值一定是通过 `schema` 校验的 dict，调用方可以直接使用，无需再写
        任何容错解析逻辑。
      - 失败时（多次重试后仍拿不到合法/合规 JSON，或 HTTP/网络层出错），抛出异常
        （requests 的异常，或本文件定义的 SchemaValidationError / json.JSONDecodeError），
        绝不会返回半成品或猜测性的结果——调用方应当用 try/except 捕获并按自己的业务
        逻辑降级（记录日志、转人工等）。
    """
    http = session or requests.Session()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _build_system_prompt(schema)},
        {"role": "user", "content": feedback_text},
    ]

    last_error: Exception | None = None

    for attempt in range(1, max_repair_attempts + 1):
        payload = {
            "model": model,
            "messages": messages,
            # json_object 只保证"语法合法的 JSON"，不保证符合我们的 schema，
            # 所以下面仍然要做应用层的 schema 校验 + 重试。
            "response_format": {"type": "json_object"},
            # glm-5.3 无法关闭 thinking，只能调节强度；简单抽取任务用 low 即可。
            "reasoning_effort": reasoning_effort,
            "temperature": 0.1,  # 结构化抽取任务，降低随机性，减少格式跑偏概率
        }

        response = http.post(
            BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        body = response.json()
        if "error" in body:
            # 智谱的业务错误码放在 body["error"]，即便 HTTP 状态码是 200 也可能出现。
            err = body["error"]
            raise RuntimeError(f"bigmodel.cn API 返回业务错误 code={err.get('code')}: {err.get('message')}")

        content = body["choices"][0]["message"]["content"]

        try:
            data = json.loads(content)
            validate_against_schema(data, schema)
            return data  # 成功：拿到合法且符合 schema 的结果
        except (json.JSONDecodeError, SchemaValidationError) as exc:
            last_error = exc
            if attempt == max_repair_attempts:
                break

            # 把模型刚才的错误输出 + 具体错误原因喂回去，要求它修正后重新只输出 JSON。
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "你上一次的输出不符合要求，原因如下：\n"
                        f"{exc}\n\n"
                        "请重新只输出一个符合 schema 的 JSON 对象，不要包含任何其他文字。"
                    ),
                }
            )

    raise RuntimeError(
        f"连续 {max_repair_attempts} 次尝试后仍未拿到合法且符合 schema 的 JSON，最后一次错误: {last_error}"
    )


# ---------------------------------------------------------------------------
# 5. 示例入口
# ---------------------------------------------------------------------------

SAMPLE_FEEDBACK = (
    "你好，我是李明，上周买的智能音箱到现在还是连不上 App，"
    "客服电话打了三次都没解决，孩子生日礼物眼看就要用不上了，"
    "麻烦今天之内给我解决，不然我就申请退款了！"
)


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY。\n"
            "请先执行: export ZHIPUAI_API_KEY='你的真实 API Key'\n"
            "（API Key 从 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取，切勿硬编码到代码里）",
            file=sys.stderr,
        )
        sys.exit(1)

    result = extract_feedback(SAMPLE_FEEDBACK, api_key=api_key)

    # 到这里 result 已经是通过 schema 校验的合法 dict，可以直接喂给下游系统。
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
