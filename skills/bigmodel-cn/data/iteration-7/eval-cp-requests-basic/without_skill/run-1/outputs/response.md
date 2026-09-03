已写好 `main.py`，只依赖 `requests`，直接用 HTTP 调用智谱的 Chat Completions 接口。

## 使用方法

```bash
pip install requests
export GLM_KEY="你的智谱 API Key"
python3 main.py
```

脚本会把 `glm-5.3` 对「用一句话介绍 Python」的回答打印到 stdout。

## 脚本要点

- **端点**：GLM Coding Plan 套餐走专属的 coding 端点 `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`，套餐额度只在这个端点生效。如果你之后想用普通按量计费的 Key，设置 `GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4` 即可切换，无需改代码。
- **鉴权**：`Authorization: Bearer $GLM_KEY`，Key 只从环境变量读取，不写死在代码里；未设置时会给出明确报错并退出码 1。
- **请求体**：OpenAI 兼容格式，`model` 为 `glm-5.3`（可用 `GLM_MODEL` 环境变量覆盖），`messages` 为单轮 user 消息，`stream: false`。
- **响应解析**：取 `choices[0].message.content` 打印；HTTP 非 200、网络异常、JSON 结构不符都会把原始信息打到 stderr，方便排查。

## 一点提醒

- 如果接口返回 `1211`/模型不存在之类的错误，说明该 Key 对应的套餐里没有 `glm-5.3` 这个模型名，可按控制台里列出的可用模型名通过 `GLM_MODEL` 环境变量改一下。
- 如果返回 401/1002，通常是 Key 不对，或者用了普通 Key 调 coding 端点（反之亦然），检查一下 `GLM_BASE_URL` 与 Key 类型是否匹配。
