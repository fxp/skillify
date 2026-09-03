# 答复

脚本已保存为 `main.py`，直接 `python3 main.py` 即可运行（需要先 `pip install requests`，并设置环境变量 `ZHIPUAI_API_KEY` 与 `GLM_CODING_PLAN_API_KEY`）。

## 两把 Key 的分工

| 步骤 | 模型 | 使用的 Key | 端点 |
|---|---|---|---|
| 余弦相似度 | `embedding-3` | `ZHIPUAI_API_KEY`（按量付费） | `https://open.bigmodel.cn/api/paas/v4/embeddings` |
| 一句话判断 | `glm-5.3` | `GLM_CODING_PLAN_API_KEY`（套餐额度，优先） | `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions` |

原因：GLM Coding Plan 套餐额度只覆盖 GLM 系列对话模型，并且需要走 coding 专用端点 `/api/coding/paas/v4`；embedding 模型不在套餐范围内，所以 `embedding-3` 必须用开放平台按量付费 Key。对话部分优先走套餐 Key；如果没设套餐 Key、或套餐端点调用失败（如额度用尽），脚本会自动回退到按量付费 Key 调用同一模型，并在输出里标明本次实际走的是哪条额度。

## 脚本要点

- 纯 `requests` 直调 HTTP，`Authorization: Bearer <key>`，JSON body。
- 一次 embeddings 请求同时传入两句话（`input` 为列表），本地用纯 Python 算余弦相似度，不依赖 numpy。
- 把相似度数值一并喂给 `glm-5.3`，`temperature=0.1`，要求只用一句话回答。
- 缺 `ZHIPUAI_API_KEY` 会直接报错退出；缺 `GLM_CODING_PLAN_API_KEY` 只给警告并全部走按量付费。

## 运行示例

```bash
export ZHIPUAI_API_KEY=...
export GLM_CODING_PLAN_API_KEY=...
pip install requests
python3 main.py
```

预期输出形如：

```
句子 A: 今天天气很好
句子 B: 天气不错
embedding-3 余弦相似度: 0.8xxx
[info] 对话调用使用: GLM Coding Plan 套餐额度
glm-5.3 的判断: 这两句话意思相近，都是在说天气好。
```

注意：`glm-5.3` 模型名与套餐端点路径是按当前智谱开放平台的约定写的，若实际账号可用模型列表不同，只需改 `CHAT_MODEL` / `CODING_BASE` 两个常量。
