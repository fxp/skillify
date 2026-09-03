# 两把 Key 分工 + embedding 相似度 + glm-5.3 点评

脚本已保存为 `main.py`，直接 `python3 main.py` 即可运行（依赖 `pip install requests`）。

## Key 分工（尽量用套餐额度）

| 步骤 | 模型 | 用哪把 Key | 接口 | 原因 |
|---|---|---|---|---|
| 1. 余弦相似度 | `embedding-3` | `ZHIPUAI_API_KEY`（按量付费） | `https://open.bigmodel.cn/api/paas/v4/embeddings` | GLM Coding Plan 套餐只覆盖对话/编码模型，**不包含 Embedding**，只能走开放平台按量付费 |
| 2. 一句话点评 | `glm-5.3` | `GLM_CODING_PLAN_API_KEY`（套餐） | `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions` | 套餐额度专用端点，OpenAI 兼容格式；若未设置套餐 Key，自动回退到按量付费 Key + `/api/paas/v4` |

## 运行方式

```bash
export ZHIPUAI_API_KEY="你的开放平台Key"
export GLM_CODING_PLAN_API_KEY="你的CodingPlanKey"
python3 main.py
```

预期输出形如：

```
[1/2] 使用 embedding-3（开放平台按量付费）计算余弦相似度 ...
「今天天气很好」与「天气不错」的余弦相似度：0.8xxx

[2/2] 使用 glm-5.3（GLM Coding Plan 套餐）判断语义是否相近 ...
glm-5.3 的回答：这两句话意思相近，都在表达天气好。
```

## 实现要点

- 全程用 `requests.post` 直接调 HTTP，`Authorization: Bearer <key>`，无 SDK 依赖。
- 一次 embeddings 请求同时传两句（`input` 为列表），按返回的 `index` 排序后取向量，余弦相似度用纯 Python 计算，不依赖 numpy。
- 把算出来的相似度一并塞进 prompt，让 `glm-5.3` 只用一句话回答是否相近（`max_tokens=200`、`temperature=0.3`）。
- 非 200 响应、`error` 字段、网络异常、响应解析失败都会以中文错误信息退出，方便排查 Key 或额度问题。

## 注意

- 如果 Coding Plan 端点对 `glm-5.3` 返回模型不可用或 401/403，说明该套餐未覆盖此模型/端点，可临时 `unset GLM_CODING_PLAN_API_KEY` 让脚本回退到按量付费。
- 若你的套餐调用地址与上面不同（以智谱控制台“接入地址”为准），改 `CODING_BASE_URL` 一处即可。
