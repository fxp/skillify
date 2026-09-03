#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_feedback.py

用智谱 GLM-5.2 从客户反馈文本中抽取结构化信息（姓名 name / 问题类型 issue_type /
紧急程度 urgency），保证返回值是严格符合调用方给定 JSON Schema 的合法 dict，
可以直接在业务代码里 `result = extract_feedback(text)` 使用，无需再写容错解析逻辑。

背景（为什么需要这么多“看起来多余”的代码）
--------------------------------------------------
智谱开放平台（bigmodel.cn）的 `chat/completions` 接口 `response_format` 目前只有
`text` / `json_object` 两档，**没有** OpenAI 那种 `json_schema` 强约束模式——
平台不会在服务端帮你保证输出 100% 满足某个 JSON Schema，模型仍然可能：
  1. 输出格式正确的 JSON，但字段缺失 / 类型错误 / 枚举值超出范围；
  2. 在极端情况下夹带解释性文字或 Markdown 代码块围栏；
  3. 触发限流 (429) 或平台过载 (500 系列) 导致请求失败。

所以“严格符合 JSON Schema”这件事，只能由**调用方**（也就是这个脚本）来兜底：
把 Schema 写进 prompt 引导模型 + 用真正的 Schema 校验器二次校验 + 校验失败时
把错误信息喂回给模型自我纠正（最多重试几次）+ 网络/限流错误做指数退避重试。
这样业务代码拿到的要么是一个保证合法的 dict，要么是一个信息明确的异常，
不会再出现“看似是 JSON、其实解析半途炸掉”的情况。

依赖
----
- 标准库：json / os / re / time / typing
- 第三方：requests（HTTP 调用，题目指定必须用它）
- 可选第三方：jsonschema（如果已安装，用它做严格校验；没装则自动降级为本文件内置的
  轻量校验器，覆盖 type/enum/required/properties/additionalProperties/items 等常见关键字，
  足以覆盖“客户反馈抽取”这类扁平结构。复杂 Schema 建议安装 `pip install jsonschema`）。

用法
----
    export ZHIPUAI_API_KEY="你的真实 API Key"   # 从 bigmodel.cn 控制台获取
    python extract_feedback.py

或者作为库使用：

    from extract_feedback import extract_feedback, FEEDBACK_SCHEMA
    result = extract_feedback("客户张先生反馈发货太慢了，很不满意，要求尽快处理。")
    # result == {"name": "张先生", "issue_type": "物流配送", "urgency": "high"}
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests

# --------------------------------------------------------------------------
# 平台常量（严格按照 bigmodel-cn 技能包的规范：固定 Base URL + Bearer 鉴权 +
# API Key 一律从环境变量读取，绝不硬编码进代码）
# --------------------------------------------------------------------------
API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.2"
API_KEY_ENV_VAR = "ZHIPUAI_API_KEY"

# 从环境变量读取 API Key；本任务明确要求不真实调用接口，这里用占位符兜底，
# 方便脚本在没有配置 Key 的环境下也能被 import / 静态检查，而不会在 import 阶段就报错。
API_KEY = os.environ.get(API_KEY_ENV_VAR, "PLACEHOLDER_API_KEY_SET_ZHIPUAI_API_KEY_ENV_VAR")

# --------------------------------------------------------------------------
# 调用方给定的 JSON Schema —— 这是本脚本承诺“严格符合”的唯一标准。
# 按需替换成你自己的 Schema，extract_feedback() 是 Schema 驱动的，不写死字段。
# --------------------------------------------------------------------------
FEEDBACK_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "客户姓名；反馈原文中确实没有提到姓名时，返回空字符串 \"\"",
        },
        "issue_type": {
            "type": "string",
            "enum": ["产品质量", "物流配送", "售后服务", "账单支付", "功能建议", "其他"],
            "description": "问题类型，必须从枚举值中选择，无法归类时选“其他”",
        },
        "urgency": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "紧急程度：low=不影响使用/可延后处理，medium=有影响但不紧急，"
            "high=明确表达不满/催促/影响使用需尽快处理",
        },
    },
    "required": ["name", "issue_type", "urgency"],
    "additionalProperties": False,
}


class StructuredExtractionError(RuntimeError):
    """多次重试后仍无法拿到符合 Schema 的合法 JSON 时抛出。

    携带最后一次模型的原始输出和具体校验错误，方便排查，而不是把半成品数据
    悄悄塞给调用方——“拿到即合法，否则抛异常”是这个脚本对调用方的唯一承诺。
    """

    def __init__(self, message: str, last_raw_content: Optional[str] = None):
        super().__init__(message)
        self.last_raw_content = last_raw_content


# --------------------------------------------------------------------------
# 轻量 JSON Schema 校验器（stdlib-only 降级方案）
#
# 只实现了这个任务量级会用到的关键字：type / enum / properties / required /
# additionalProperties / items。如果环境里装了 `jsonschema`，优先用它（更全、
# 更权威），这里只是保证“没装第三方校验库也能跑”。
# --------------------------------------------------------------------------
_PY_TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def _validate_lightweight(instance: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    errors: List[str] = []

    schema_type = schema.get("type")
    if schema_type is not None:
        expected_types = schema_type if isinstance(schema_type, list) else [schema_type]
        py_types = tuple(_PY_TYPE_MAP[t] for t in expected_types if t in _PY_TYPE_MAP)
        # bool 是 int 的子类，避免 True/False 被误判成 number/integer
        if py_types and not (
            isinstance(instance, py_types)
            and not (isinstance(instance, bool) and bool not in py_types)
        ):
            errors.append(f"{path}: 期望类型 {expected_types}，实际是 {type(instance).__name__}")
            return errors  # 类型都不对，后面的字段级校验没有意义

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: 值 {instance!r} 不在允许的枚举范围 {schema['enum']} 内")

    if schema.get("type") == "object" and isinstance(instance, dict):
        properties = schema.get("properties", {})
        for req_key in schema.get("required", []):
            if req_key not in instance:
                errors.append(f"{path}: 缺少必填字段 '{req_key}'")
        if schema.get("additionalProperties") is False:
            extra_keys = set(instance.keys()) - set(properties.keys())
            if extra_keys:
                errors.append(f"{path}: 出现了 Schema 未定义的字段 {sorted(extra_keys)}")
        for key, sub_schema in properties.items():
            if key in instance:
                errors.extend(_validate_lightweight(instance[key], sub_schema, f"{path}.{key}"))

    if schema.get("type") == "array" and isinstance(instance, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(instance):
                errors.extend(_validate_lightweight(item, item_schema, f"{path}[{i}]"))

    return errors


def validate_against_schema(instance: Any, schema: Dict[str, Any]) -> List[str]:
    """返回校验错误列表；空列表代表完全符合 Schema。

    优先使用第三方 `jsonschema` 库（若已安装），它是 JSON Schema 规范的权威实现，
    覆盖度远超本文件的手写校验器；未安装时自动降级为 `_validate_lightweight`。
    """
    try:
        import jsonschema  # type: ignore

        validator_cls = jsonschema.Draft202012Validator if hasattr(
            jsonschema, "Draft202012Validator"
        ) else jsonschema.Draft7Validator
        validator = validator_cls(schema)
        return [f"{'.'.join(str(p) for p in e.path) or '$'}: {e.message}" for e in validator.iter_errors(instance)]
    except ImportError:
        return _validate_lightweight(instance, schema)


# --------------------------------------------------------------------------
# 从模型原始输出里稳健地取出 JSON 文本
# --------------------------------------------------------------------------
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_code_fence(text: str) -> str:
    """response_format=json_object 下模型理论上不会包代码块，但保留这一层防御
    几乎零成本，能顺手扛住模型偶尔的“习惯性” ```json ... ``` 包裹。"""
    return _CODE_FENCE_RE.sub("", text).strip()


# --------------------------------------------------------------------------
# 核心调用：一次 HTTP 请求（内部已处理网络类错误的指数退避重试）
# --------------------------------------------------------------------------
def _call_chat_completions(
    messages: List[Dict[str, str]],
    *,
    max_retries: int = 3,
    timeout: float = 60.0,
) -> str:
    """调用 GLM-5.2，开启 json_object 模式，返回 `choices[0].message.content` 原始字符串。

    仅对网络层/限流/平台过载（429、5xx、超时、连接错误）做指数退避重试；
    401/403/400 这类配置或参数错误直接抛出，重试没有意义（技能包
    references/errors-and-limits.md 里的明确建议）。
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        # 结构化抽取是确定性任务，不需要模型“自由发挥”，也不需要深度思考——
        # glm-5.2 允许显式关闭 thinking，关掉能降低延迟和 token 消耗。
        "thinking": {"type": "disabled"},
        "temperature": 0.1,
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(API_BASE_URL, headers=headers, json=payload, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
        else:
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            if resp.status_code in (401, 403, 400):
                # 配置/参数错误：Key 无效、参数非法等，重试无意义，直接报错。
                raise RuntimeError(
                    f"调用 GLM-5.2 失败（{resp.status_code}，不可重试）：{resp.text}"
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = RuntimeError(
                    f"调用 GLM-5.2 失败（{resp.status_code}，可重试）：{resp.text}"
                )
            else:
                raise RuntimeError(f"调用 GLM-5.2 失败（{resp.status_code}）：{resp.text}")

        if attempt < max_retries:
            backoff_seconds = (2 ** attempt) + 0.1 * attempt  # 指数退避，避免固定间隔猛发请求
            time.sleep(backoff_seconds)

    raise RuntimeError(f"调用 GLM-5.2 连续失败 {max_retries + 1} 次，最后一次错误：{last_exc}")


# --------------------------------------------------------------------------
# 对外主入口
# --------------------------------------------------------------------------
def extract_feedback(
    feedback_text: str,
    schema: Dict[str, Any] = FEEDBACK_SCHEMA,
    *,
    max_schema_retries: int = 2,
) -> Dict[str, Any]:
    """从客户反馈文本中抽取结构化信息，返回严格符合 `schema` 的 dict。

    参数：
        feedback_text: 客户反馈原文。
        schema: 目标 JSON Schema，默认用本文件里的 FEEDBACK_SCHEMA
                （name / issue_type / urgency）。传入你自己的 Schema 也可以复用整套流程。
        max_schema_retries: 模型输出不满足 Schema 时，把错误信息喂回去让它自我纠正的
                最大重试次数（不含首次请求）。

    返回：
        一个保证通过 `validate_against_schema` 校验的 dict，可以直接用于后续系统处理。

    异常：
        StructuredExtractionError: 重试用尽后仍未拿到合法结果，附带最后一次的原始输出，
            便于人工排查（比如反馈文本本身信息不足、或模型持续输出了 Schema 之外的值）。
    """
    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
    system_prompt = (
        "你是客户反馈结构化抽取助手。请仔细阅读用户提供的客户反馈文本，"
        "抽取出结构化信息，并且只返回一个 JSON 对象，不要输出任何多余的文字、"
        "解释或 Markdown 代码块围栏。\n\n"
        "返回的 JSON 必须严格符合以下 JSON Schema：\n"
        f"{schema_str}\n\n"
        "抽取规则：\n"
        "- 姓名如果原文中出现称呼（如“张先生”“李女士”“王先生”），按原文称呼填写；"
        "完全没有提到任何称呼时，name 填空字符串 \"\"。\n"
        "- issue_type 必须从 Schema 给定的枚举值里选一个最贴切的，不要自造新词。\n"
        "- urgency 综合反馈的语气、是否明确表达不满/催促、是否影响正常使用来判断，"
        "同样必须是 Schema 枚举值之一。\n"
        "- 只输出 JSON 本身，第一个字符必须是 `{`，最后一个字符必须是 `}`。"
    )

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": feedback_text},
    ]

    last_raw_content: Optional[str] = None

    for attempt in range(max_schema_retries + 1):
        raw_content = _call_chat_completions(messages)
        last_raw_content = raw_content
        cleaned = _strip_code_fence(raw_content)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            error_summary = f"返回内容不是合法 JSON：{exc}"
        else:
            schema_errors = validate_against_schema(parsed, schema)
            if not schema_errors:
                return parsed  # 校验通过，直接返回给调用方，不用再做任何容错解析
            error_summary = "返回的 JSON 不符合 Schema：\n" + "\n".join(f"- {e}" for e in schema_errors)

        if attempt < max_schema_retries:
            # 把模型刚才的错误输出 + 具体校验错误喂回对话，让它在下一轮自我纠正，
            # 而不是每次都从零重新问一遍（带着错误上下文，纠正成功率更高）。
            messages.append({"role": "assistant", "content": raw_content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"上一次的输出有问题：\n{error_summary}\n\n"
                        "请重新输出，只返回一个严格符合 Schema 的 JSON 对象，不要有任何多余内容。"
                    ),
                }
            )

    raise StructuredExtractionError(
        f"重试 {max_schema_retries + 1} 次后，模型仍未返回符合 Schema 的合法 JSON。",
        last_raw_content=last_raw_content,
    )


# --------------------------------------------------------------------------
# 演示入口
# --------------------------------------------------------------------------
if __name__ == "__main__":
    sample_feedback = (
        "客户张先生反馈：上周下单的净水器一直没有发货，物流信息也没有更新，"
        "已经打了两次客服电话都没解决，非常不满，要求今天之内给出明确答复，否则要退货。"
    )

    if API_KEY.startswith("PLACEHOLDER_API_KEY"):
        print(
            f"[提示] 尚未设置环境变量 {API_KEY_ENV_VAR}，当前使用占位符 API Key，"
            "真实调用会在鉴权阶段失败（401）。请先执行：\n"
            f'  export {API_KEY_ENV_VAR}="你的真实 API Key"\n'
            "再运行本脚本。以下调用会按预期失败，这只是演示脚本结构，不代表代码有误。\n"
        )

    try:
        result = extract_feedback(sample_feedback)
        print("抽取结果：")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except StructuredExtractionError as exc:
        print(f"[抽取失败] {exc}")
        print(f"最后一次模型原始输出：{exc.last_raw_content}")
    except RuntimeError as exc:
        print(f"[请求失败] {exc}")
