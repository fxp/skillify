已写好 `main.py`,直接 `python3 main.py` 即可运行(依赖 `pip install requests`)。

## 两把 Key 的分工

| 步骤 | 模型 | 用哪把 Key | 端点 | 原因 |
|---|---|---|---|---|
| 1. 计算余弦相似度 | `embedding-3` | `ZHIPUAI_API_KEY`(按量付费) | `https://open.bigmodel.cn/api/paas/v4/embeddings` | Coding Plan 套餐只覆盖对话模型,不包含 embedding 接口,套餐 Key 调不通 |
| 2. 判断语义是否相近 | `glm-5.3` | **优先 `GLM_CODING_PLAN_API_KEY`(套餐额度)** | `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions` | 套餐 Key 必须走 `/api/coding/paas/v4` 这个专用前缀;若未设置或调用失败,自动回退到 `ZHIPUAI_API_KEY` + 通用端点 |

## 脚本做了什么

1. 读取两个环境变量;`ZHIPUAI_API_KEY` 缺失则直接报错退出(embedding 没有替代方案)。
2. 用 `requests.post` 调 `embedding-3`,一次传入两句话,按 `index` 排序取回两个向量,纯 Python 算余弦相似度并打印(保留 4 位小数)。
3. 把两句话和相似度一起塞进 prompt,要求 `glm-5.3` "只用一句话"回答是否相近;先走 Coding 端点用套餐额度,失败再走开放平台按量付费,打印回答。
4. 所有 HTTP 非 200 或返回体含 `error` 都会抛出并把原始响应打到 stderr,方便排查 Key/额度问题。

## 运行

```bash
export GLM_CODING_PLAN_API_KEY=...   # 套餐 Key
export ZHIPUAI_API_KEY=...           # 开放平台 Key
pip install requests
python3 main.py
```

预期输出示例:

```
[1/2] 使用 ZHIPUAI_API_KEY(按量付费)调用 embedding-3 ...
「今天天气很好」 与 「天气不错」 的余弦相似度: 0.8xxx

[2/2] 使用 GLM_CODING_PLAN_API_KEY(套餐额度)调用 glm-5.3 ...
glm-5.3 的判断: 这两句话意思相近,都在说天气好。
```

## 注意事项

- 如果套餐 Key 返回 401/1xxx 类错误,多半是把它打到了通用端点,或者套餐不含 `glm-5.3`;脚本会自动回退,但回退部分会消耗按量付费余额。
- 若智谱后续把 embedding 纳入套餐,只需把第 1 步的 `OPEN_BASE`/`open_key` 换成 `CODING_BASE`/`coding_key` 即可。
