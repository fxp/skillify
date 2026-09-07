#!/usr/bin/env python3
"""用智谱 BigModel 的 Batch API 批量对用户评论做情感分类(正面/负面/中性)。

流程:
1. 读取脚本同目录下的 comments.txt(每行一条评论);
2. 生成 batch_requests.jsonl(每行一个 chat/completions 请求,带唯一 custom_id);
3. 以 purpose=batch 上传该文件;
4. 创建 batch 任务,把 batch 任务 id 打印到 stdout(不等待任务完成)。

用法:
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"

# Batch 只支持一份模型白名单(在文件上传阶段就会校验,写了白名单外的模型报 1210 模型名称错误),
# 平台旗舰 glm-5.3/glm-5.2 并不在白名单内。白名单里当前最强的文本模型是 glm-5.1
# (Coding 对齐 Claude Opus 4.6 档位,200K 上下文),强于 glm-5-turbo/glm-4-plus/glm-4-air 等。
# 分类质量优先,选它而不是免费的 glm-4-flash 等轻量档。
MODEL = "glm-5.1"

# 需与创建 batch 任务时的 endpoint 字段一致,也是 .jsonl 每行的 url
BATCH_ENDPOINT = "/v4/chat/completions"

SYSTEM_PROMPT = (
    "你是用户评论情感分类器。对给定的一条用户评论判断整体情感倾向，"
    "只输出一个词作为答案：正面、负面 或 中性，不要输出任何解释或其他文字。"
    "判断标准：表达满意、称赞、推荐或复购意愿的为正面；表达不满、抱怨、投诉或要求退换货的为负面；"
    "客观陈述、信息询问，或褒贬并存且整体倾向不明的为中性。"
)


def log(msg):
    """进度信息走 stderr,保证 stdout 里只有最终的 batch 任务 id。"""
    print(msg, file=sys.stderr)


def auth_headers():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误: 未设置环境变量 ZHIPUAI_API_KEY,请先 export ZHIPUAI_API_KEY=你的Key")
    return {"Authorization": "Bearer " + api_key}


def load_comments(comments_path):
    # utf-8-sig: 文件带 BOM 时也能正确去除
    lines = comments_path.read_text(encoding="utf-8-sig").splitlines()
    comments = [line.strip() for line in lines if line.strip()]
    if not comments:
        sys.exit("错误: %s 里没有读到任何评论" % comments_path)
    return comments


def build_request_file(comments, jsonl_path):
    with jsonl_path.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, start=1):
            request = {
                # custom_id 必须唯一且最短 6 个字符(过短如 "r1" 会在上传阶段被拒),补零保证字典序
                "custom_id": "request-%06d" % i,
                "method": "POST",
                "url": BATCH_ENDPOINT,
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": "评论：" + comment},
                    ],
                    "temperature": 0.1,
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")


def check_response(resp, action):
    """校验响应并返回解析后的 JSON;失败时直接终止并给出可读的错误信息。"""
    try:
        data = resp.json()
    except ValueError:
        sys.exit("%s失败: HTTP %d, 响应不是 JSON: %s" % (action, resp.status_code, resp.text[:500]))
    if not resp.ok:
        sys.exit("%s失败: HTTP %d, %s" % (action, resp.status_code, data))
    if isinstance(data, dict) and data.get("error"):
        sys.exit("%s失败: %s" % (action, data["error"]))
    return data


def main():
    headers = auth_headers()
    script_dir = Path(__file__).resolve().parent
    comments_path = script_dir / "comments.txt"
    if not comments_path.exists():
        sys.exit("错误: 找不到评论文件 %s" % comments_path)

    comments = load_comments(comments_path)
    jsonl_path = script_dir / "batch_requests.jsonl"
    build_request_file(comments, jsonl_path)
    log("已生成 %d 条请求 -> %s" % (len(comments), jsonl_path.name))

    try:
        # 1. 上传请求文件,purpose 必须为 batch;模型白名单校验发生在这一步
        with jsonl_path.open("rb") as f:
            upload = check_response(
                requests.post(
                    BASE_URL + "/paas/v4/files",
                    headers=headers,
                    files={"file": f},
                    data={"purpose": "batch"},
                    timeout=120,
                ),
                "上传请求文件",
            )
        file_id = upload["id"]
        log("请求文件上传成功: %s" % file_id)

        # 2. 创建 batch 任务(预计 24 小时内完成,此处不轮询等待)
        batch = check_response(
            requests.post(
                BASE_URL + "/paas/v4/batches",
                headers=dict(headers, **{"Content-Type": "application/json"}),
                json={
                    "input_file_id": file_id,
                    "endpoint": BATCH_ENDPOINT,
                    "metadata": {"description": "用户评论情感分类: 正面/负面/中性"},
                },
                timeout=60,
            ),
            "创建 batch 任务",
        )
    except requests.RequestException as e:
        sys.exit("网络请求失败: %s" % e)

    log("batch 任务创建成功,初始状态: %s" % batch.get("status"))
    print(batch["id"])


if __name__ == "__main__":
    main()
