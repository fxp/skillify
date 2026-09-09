#!/usr/bin/env python3
"""
知识库 ID 校验脚本

用途：验证智谱托管知识库 ID 是否存在且可用
特点：
1. 保守校验：宁可误报无效，绝不放行无效 ID
2. 严格检查 HTTP 状态码和业务错误码
3. 明确的输出结论
4. 适合作为发布流水线的卡点检查

使用方法：
export ZHIPU_KB_ID=你的知识库ID
export ZHIPUAI_API_KEY=你的API密钥
python3 main.py
"""

import os
import sys
import requests
from typing import Optional, Dict, Any

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_ENDPOINT = f"{BASE_URL}/llm-application/open/knowledge"
HEADERS_TEMPLATE = {"Content-Type": "application/json"}


def get_env_vars() -> tuple[str, str]:
    """获取必要的环境变量"""
    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()

    if not kb_id:
        print("❌ 错误：未设置 ZHIPU_KB_ID 环境变量")
        sys.exit(1)

    if not api_key:
        print("❌ 错误：未设置 ZHIPUAI_API_KEY 环境变量")
        sys.exit(1)

    return kb_id, api_key


def create_headers(api_key: str) -> Dict[str, str]:
    """创建请求头"""
    headers = HEADERS_TEMPLATE.copy()
    headers["Authorization"] = f"Bearer {api_key}"
    return headers


def check_knowledge_base(kb_id: str, headers: Dict[str, str]) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    检查知识库是否存在

    返回：
    - (True, data): 知识库存在，data 是详细信息
    - (False, None): 知识库不存在
    - (False, error_info): 发生错误
    """
    url = f"{API_ENDPOINT}/{kb_id}"

    try:
        print(f"🔍 正在查询知识库详情...")
        resp = requests.get(url, headers=headers, timeout=10)

        # 重要：根据文档，知识库 API 即使出错也返回 HTTP 200
        # 需要检查响应体中的 code 字段
        if resp.status_code != 200:
            print(f"❌ 意外错误：HTTP 状态码 {resp.status_code}（预期 200）")
            return False, {"error": f"HTTP {resp.status_code}", "response": resp.text}

        try:
            data = resp.json()
        except ValueError:
            print("❌ 错误：响应不是有效的 JSON 格式")
            return False, {"error": "Invalid JSON response", "response": resp.text}

        # 根据文档，知识库不存在时返回 code: 100013
        if data.get("code") == 100013:
            print("❌ 检测到知识库不存在（错误码 100013）")
            return False, None

        # 成功响应的 code 应该是 200
        if data.get("code") == 200:
            print("✅ 知识库存在且可访问")
            return True, data

        # 其他错误码视为无效
        if "code" in data:
            print(f"❌ 检测到错误（错误码 {data['code']}）：{data.get('message', '未知错误')}")
            return False, {"error": f"API error {data['code']}", "response": data}

        # 没有 code 字段，响应格式异常
        print("⚠️  警告：响应格式异常，缺少 code 字段")
        return False, {"error": "Missing code in response", "response": data}

    except requests.exceptions.Timeout:
        print("❌ 错误：请求超时（10秒）")
        return False, {"error": "Request timeout"}
    except requests.exceptions.ConnectionError:
        print("❌ 错误：无法连接到服务器")
        return False, {"error": "Connection error"}
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常：{str(e)}")
        return False, {"error": str(e)}


def validate_knowledge_base(kb_id: str, data: Dict[str, Any]) -> tuple[bool, str]:
    """
    进一步验证知识库是否真的可用
    """
    # 检查基本字段
    if not data.get("id"):
        print("❌ 错误：响应缺少知识库 ID")
        return False, "响应缺少知识库 ID"

    if data["id"] != kb_id:
        print(f"❌ 错误：返回的知识库 ID 不匹配（期望 {kb_id}，实际 {data['id']}）")
        return False, "ID 不匹配"

    # 检查知识库名称
    name = data.get("name")
    if not name:
        print("❌ 错误：知识库缺少名称")
        return False, "知识库缺少名称"

    print(f"📚 知识库名称：{name}")

    # 检查文档数量
    document_size = data.get("document_size", 0)
    print(f"📄 文档数量：{document_size}")

    # 如果没有文档，仍然认为知识库存在但不推荐使用
    if document_size == 0:
        print("⚠️  警告：知识库中没有文档")
        return True, "知识库存在但无文档"

    # 检查总字数
    length = data.get("length", 0)
    word_num = data.get("word_num", 0)
    print(f"📊 总字数：{word_num:,} 字（分词后长度：{length:,}）")

    return True, "知识库存在且有文档"


def main():
    """主函数"""
    print("=" * 60)
    print("智谱AI知识库 ID 校验工具")
    print("=" * 60)

    # 获取环境变量
    kb_id, api_key = get_env_vars()
    print(f"\n📝 待校验知识库 ID：{kb_id}")

    # 创建请求头
    headers = create_headers(api_key)

    # 检查知识库是否存在
    exists, result = check_knowledge_base(kb_id, headers)

    if not exists:
        if result is None:
            print("\n🚫 校验结论：知识库不存在")
        else:
            print(f"\n🚫 校验结论：知识库不可用 - {result.get('error', '未知错误')}")

        print("\n❌ 校验失败：知识库 ID 无效")
        sys.exit(1)

    # 知识库存在，进一步验证
    print("\n🔬 进一步验证知识库状态...")
    is_valid, message = validate_knowledge_base(kb_id, result)

    if not is_valid:
        print(f"\n⚠️  校验结论：知识库存在问题 - {message}")
        print("❌ 校验失败：知识库不可用")
        sys.exit(1)

    # 输出最终结论
    print("\n" + "=" * 60)
    print("✅ 校验结论：知识库有效且可用")
    print("=" * 60)
    print(f"📋 知识库详情：")
    print(f"   - ID: {result.get('id')}")
    print(f"   - 名称: {result.get('name')}")
    print(f"   - 文档数量: {result.get('document_size', 0)}")
    print(f"   - 总字数: {result.get('word_num', 0):,} 字")
    print(f"   - 向量化模型: {result.get('embedding_model', '未知')}")
    print("\n✅ 可以安全上线使用")

    sys.exit(0)


if __name__ == "__main__":
    main()