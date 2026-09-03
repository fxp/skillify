## main.py 已写好

文件：`/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/iteration-7/eval-cp-implicit-plan-wording/without_skill/run-2/outputs/main.py`

运行：

```bash
pip install requests   # 如果还没装
export ZHIPU_API_KEY="你的key"
python3 main.py
```

### 关键点：编程套餐要用 coding 专用地址

你买的是 **GLM Coding Plan（编程套餐 Pro）**，它和普通按量付费 API 走的是**不同的接口地址**：

| 计费方式 | Chat Completions 地址 |
|---|---|
| 按量付费 | `https://open.bigmodel.cn/api/paas/v4/chat/completions` |
| **编程套餐（你这种）** | `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions` |

用套餐 Key 去调普通地址，常见结果是报余额不足 / 无权限（1113、1211 之类的错误码），因为套餐额度不在按量账户里。所以脚本默认走 `api/coding/paas/v4`，请求格式仍是 OpenAI 兼容格式（`Authorization: Bearer <key>` + `model` + `messages`）。

脚本做了几件事：

- 从 `ZHIPU_API_KEY` 读 Key，没设置时给出明确提示并退出。
- 调 `glm-5.3`（可用 `ZHIPU_MODEL` 环境变量换模型），非流式，`thinking` 设为 `disabled`，避免回答被塞进推理字段导致 `content` 为空。
- 对 HTTP 错误 / 接口错误码做了打印，并在报余额或权限错误时提示你检查 Key 类型；如果你其实要用按量付费 Key，设 `ZHIPU_BASE_URL="https://open.bigmodel.cn/api/paas/v4"` 即可切换。
- 只把 `choices[0].message.content` 打印出来（若为空则兜底取 `reasoning_content`）。

### 两个说明

1. 编程套餐官方定位是给 Claude Code / Cline 等编程工具用的，直接用 HTTP 调 coding 地址是可以的，但套餐的 5 小时额度就是按这些调用来消耗，请求会正常计入配额。
2. 我这边没有网络和 Key，脚本只做了语法检查（`py_compile` 通过），没有真实跑一遍。如果运行时提示模型名不存在，把 `ZHIPU_MODEL` 换成套餐里实际支持的型号（例如 `glm-4.7` / `glm-5` 系列）再试。
