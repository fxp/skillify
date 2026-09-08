#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱托管知识库 ID 上线前校验（发布流水线卡点）。

用法:
    ZHIPUAI_API_KEY=<你的API Key> ZHIPU_KB_ID=<知识库ID> python3 main.py

退出码（流水线按退出码卡点）:
    0  校验通过：知识库存在且可访问
    1  校验不通过：ID 无效，或因任何原因无法确认有效（一律按无效处理）
    2  配置错误：环境变量缺失或值明显非法

设计原则: fail-closed —— 宁可误报无效，绝不把坏 ID 放上线。
只有「知识库详情接口与文档列表接口都明确返回响应体 code==200，
且详情数据与待校验 ID 自洽」才判定有效；其余任何情况一律判定不通过。

关键坑（docs.bigmodel.cn API 参考 + 技能包 2026-09 实测确认）:
    /llm-application/open/* 这一族知识库接口出错时 HTTP 状态码依然是 200，
    真实结果在响应体的 code 字段里：查一个不存在的知识库，返回的是
    HTTP 200 + {"code":100013,"message":"知识库不存在"}。
    因此 resp.raise_for_status() 在这里永远拦不住坏 ID，
    必须判定响应体 code == 200，并核对 data.id 与待校验 ID 一致。
"""

import os
import sys
import time
import urllib.parse

import requests

BASE_URL = "https://open.bigmodel.cn/api"
KNOWLEDGE_DETAIL_URL = BASE_URL + "/llm-application/open/knowledge/{kb_id}"
DOCUMENT_LIST_URL = BASE_URL + "/llm-application/open/document"

SUCCESS_CODE = "200"          # 该接口族成功 = 响应体 code==200（不是 HTTP 状态码）
KB_NOT_FOUND_CODE = "100013"  # 已实测: HTTP 200 + {"code":100013,"message":"知识库不存在"}

REQUEST_TIMEOUT = 15          # 单次请求超时（秒）
MAX_ATTEMPTS = 3              # 瞬时故障（网络错误/HTTP 429/5xx）的最大尝试次数
RETRY_BASE_DELAY = 2          # 重试退避基数（秒），实际等待 2s、4s
RESPONSE_SNIPPET_LIMIT = 300  # 打印响应片段的最大长度，防止刷屏


class ConfigError(Exception):
    """环境变量缺失或格式明显非法（退出码 2）。"""


class ValidationError(Exception):
    """校验不通过：ID 无效，或无法确认有效（退出码 1）。"""


def mask_secret(value):
    """打码显示 API Key，避免完整 Key 进入流水线日志。"""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def snippet(text, limit=RESPONSE_SNIPPET_LIMIT):
    """压缩响应体为单行短片段，用于日志。"""
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…(已截断)"


def fmt(value):
    return "-" if value is None else str(value)


def body_code(payload):
    """归一化响应体业务码：兼容整数 200 与字符串 "200"；缺失返回空串。"""
    return str(payload.get("code", "")).strip()


def load_config():
    """读取环境变量并做最基本的格式检查，返回 (kb_id, api_key)。"""
    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()
    if not api_key:
        raise ConfigError("环境变量 ZHIPUAI_API_KEY 未设置或为空")
    kb_id = (os.environ.get("ZHIPU_KB_ID") or "").strip()
    if not kb_id:
        raise ConfigError("环境变量 ZHIPU_KB_ID 未设置或为空")
    if any(ch.isspace() for ch in kb_id):
        raise ConfigError(
            "ZHIPU_KB_ID 含内部空白字符（%r），疑似复制粘贴出错" % kb_id)
    return kb_id, api_key


def fetch_json_with_retry(session, method, url, **kwargs):
    """发请求并返回解析后的响应体 dict。

    仅对瞬时故障（网络异常 / HTTP 429 / 5xx）做有限次退避重试；
    4xx 等确定性失败、响应体不是 JSON 对象等情况直接判失败。
    重试耗尽同样判失败——按 fail-closed 原则，无法确认有效即按无效处理。
    """
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            last_error = "网络错误：%s: %s" % (type(exc).__name__, exc)
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = "HTTP %d（限流或服务端瞬时故障），响应体：%s" % (
                    resp.status_code, snippet(resp.text))
            elif resp.status_code != 200:
                raise ValidationError(
                    "请求 %s 返回 HTTP %d（非 200），响应体：%s"
                    % (url, resp.status_code, snippet(resp.text)))
            else:
                try:
                    payload = resp.json()
                except ValueError:
                    raise ValidationError(
                        "HTTP 200 但响应体不是合法 JSON：%s" % snippet(resp.text))
                if not isinstance(payload, dict):
                    raise ValidationError(
                        "HTTP 200 但响应体不是 JSON 对象：%s" % snippet(resp.text))
                return payload
        if attempt < MAX_ATTEMPTS:
            delay = RETRY_BASE_DELAY * attempt
            print("  [重试] 第 %d/%d 次尝试失败：%s" % (attempt, MAX_ATTEMPTS, last_error))
            print("  [重试] %d 秒后重试…" % delay)
            time.sleep(delay)
    raise ValidationError(
        "连续 %d 次尝试均失败，最后错误：%s（无法确认知识库有效，按无效处理）"
        % (MAX_ATTEMPTS, last_error))


def ensure_business_success(payload, what):
    """校验响应体业务码。

    这是本脚本的核心：该接口族出错时 HTTP 仍是 200，
    唯一可信的成败信号是响应体 code==200。
    """
    code = body_code(payload)
    if code != SUCCESS_CODE:
        if code == KB_NOT_FOUND_CODE:
            raise ValidationError(
                "%s：知识库不存在（响应体 code=%s，message=%s）。"
                "注意：该接口出错时 HTTP 状态码仍为 200，此处按响应体 code 判定"
                % (what, code, fmt(payload.get("message"))))
        raise ValidationError(
            "%s：响应体 code=%s（message=%s）。"
            "该接口 HTTP 状态码不能反映成败，按响应体 code 判定为失败"
            % (what, code, fmt(payload.get("message"))))


def validate_knowledge_base(session, kb_id):
    """执行两道检查，全部通过才返回；任何一道不过都抛 ValidationError。"""
    quoted_id = urllib.parse.quote(kb_id, safe="")

    # ---- 检查 1/2：知识库详情（存在性的权威判据）----
    print("[执行] 检查 1/2：知识库详情 GET /llm-application/open/knowledge/<ID>")
    detail = fetch_json_with_retry(
        session, "GET", KNOWLEDGE_DETAIL_URL.format(kb_id=quoted_id))
    ensure_business_success(detail, "知识库详情接口返回失败")

    data = detail.get("data")
    if not isinstance(data, dict) or not data:
        raise ValidationError(
            "知识库详情接口 code=200 但 data 缺失或不是对象，无法确认知识库有效")
    if data.get("id") != kb_id:
        raise ValidationError(
            "知识库详情返回的 data.id=%r 与待校验 ID=%r 不一致，数据不自洽，按无效处理"
            % (data.get("id"), kb_id))
    print("[OK] 详情接口 HTTP 200 且响应体 code=200，data.id 与待校验 ID 一致")

    doc_size = data.get("document_size")
    print("       知识库名称(name)         : %s" % fmt(data.get("name")))
    print("       文档数量(document_size)  : %s" % fmt(doc_size))
    print("       总字数(word_num)         : %s" % fmt(data.get("word_num")))
    print("       向量化模型(embedding_id) : %s" % fmt(data.get("embedding_id")))
    if doc_size == 0:
        print("[警告] 该知识库文档数量为 0：ID 本身有效，但检索结果将始终为空，"
              "请确认是否符合上线预期")

    # ---- 检查 2/2：文档列表可读（确认"能用"，而不只是"存在"）----
    print("[执行] 检查 2/2：文档列表 GET /llm-application/open/document?knowledge_id=<ID>")
    doc_list = fetch_json_with_retry(
        session, "GET", DOCUMENT_LIST_URL,
        params={"knowledge_id": kb_id, "page": 1, "size": 1})
    ensure_business_success(doc_list, "文档列表接口返回失败")

    doc_data = doc_list.get("data")
    if not isinstance(doc_data, dict):
        raise ValidationError(
            "文档列表接口 code=200 但 data 缺失或不是对象，无法确认知识库可用")
    print("[OK] 文档列表接口 HTTP 200 且响应体 code=200，知识库可正常访问")
    print("       服务端报告文档总数(total): %s" % fmt(doc_data.get("total")))


def main():
    print("=" * 64)
    print("智谱托管知识库 ID 上线前校验（fail-closed：无法确认有效一律按无效处理）")
    print("=" * 64)
    try:
        kb_id, api_key = load_config()
    except ConfigError as exc:
        print("[FAIL] 配置错误：%s" % exc)
        print("-" * 64)
        print("校验结论：无效（FAIL）——配置缺失，未执行线上校验，阻断发布")
        return 2

    print("待校验知识库 ID（ZHIPU_KB_ID）: %s" % kb_id)
    print("API Key（ZHIPUAI_API_KEY）    : %s" % mask_secret(api_key))
    print("-" * 64)

    session = requests.Session()
    session.headers["Authorization"] = "Bearer %s" % api_key

    try:
        validate_knowledge_base(session, kb_id)
    except ValidationError as exc:
        print("[FAIL] %s" % exc)
        print("-" * 64)
        print("校验结论：无效（FAIL）——阻断发布；若怀疑误报，请检查网络、"
              "API Key 权限与平台状态后重试")
        return 1
    except Exception as exc:  # 兜底：任何未预期异常也绝不能放行
        print("[FAIL] 校验过程出现未预期异常：%s: %s" % (type(exc).__name__, exc))
        print("-" * 64)
        print("校验结论：无效（FAIL）——异常兜底，阻断发布")
        return 1

    print("-" * 64)
    print("校验结论：有效（PASS）——知识库存在且可访问，允许上线")
    return 0


if __name__ == "__main__":
    sys.exit(main())
