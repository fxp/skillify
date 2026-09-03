# 诊断：不是智谱的 bug，也不需要充值 —— 你打错了接口地址

## 结论先行

- **1113 "余额不足或无可用资源包"** 是账单/计费层面的报错，它说的是你账户里的 **"通用 API 余额 / 按量资源包"** 为 0，而不是你的 Coding Plan 额度用完了。
- 你的 Coding Plan Max 额度并没有被消耗，因为你的请求根本没有走到 Coding Plan 的计费通道上。
- **原因**：`https://open.bigmodel.cn/api/paas/v4/` 是智谱的**通用按量付费接口**，只扣通用余额/资源包。GLM Coding Plan 是一个**独立的套餐产品**，必须通过 **专用的 Coding 接口地址** 调用才会走套餐额度：
  - 国内（bigmodel.cn）：`https://open.bigmodel.cn/api/coding/paas/v4/`
  - 海外（z.ai）：`https://api.z.ai/api/coding/paas/v4/`

你用通用地址打请求 → 系统按"按量付费"结算 → 你账户里没充过通用余额 → 返回 1113（HTTP 状态码碰巧是 429，容易让人误以为是限流，其实是计费拒绝）。

所以：**不要去充值**。充值只是给通用按量账户加钱，等于让你在已经买了套餐的情况下再额外付一次费。

## 修正后的代码

只需要改 `base_url` 一处（注意路径中多了一段 `coding/`）：

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GLM_KEY"],
    # Coding Plan 专用地址：在 /api 和 /paas 之间多了 /coding
    base_url="https://open.bigmodel.cn/api/coding/paas/v4/",
)

r = client.chat.completions.create(
    model="glm-5.3",
    messages=[{"role": "user", "content": "hi"}],
)
print(r.choices[0].message.content)
```

如果你在 Claude Code / Cline / Roo Code 等工具里配置，也是同一个原则，例如 Claude Code 用 Anthropic 兼容协议时：

```bash
export ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic"
export ANTHROPIC_AUTH_TOKEN="$GLM_KEY"
```

## 改完之后仍然报错时的排查清单

按顺序检查，通常前两条就能解决：

1. **API Key 是否来自购买套餐的那个账号**
   Coding Plan 绑定在账号上，用同一账号在开放平台"API Keys"页面生成的 key 即可；如果你手上的 key 是另一个账号（比如公司账号/旧账号）的，就会继续报 1113。

2. **模型名是否在 Coding Plan 支持列表里**
   Coding Plan 只覆盖套餐页列出的编码模型（GLM 系列的主力编码模型，以及配套的视觉/轻量模型）。请到套餐详情页核对 `glm-5.3` 这个名字是否在支持列表里、拼写是否完全一致（区分大小写，不要带多余空格）。如果模型不在套餐范围内，请求会被转到按量计费，于是又是 1113。

3. **套餐状态**
   在开放平台"资源包 / 套餐"页面确认 Coding Plan 状态为"生效中"，没有过期，且额度显示正常。你是上周购买的，正常情况下这一项不会有问题。

4. **区分 429 的两种含义**
   - `code: 1113` → 计费拒绝（本次的情况），换地址即可。
   - `code: 1302 / 1305` 之类带"并发/频率"字样的 → 才是真正的限流。Coding Plan 有 5 小时滚动窗口的用量上限，如果短时间用得很猛会遇到这种，等窗口刷新即可，也不需要充值。

5. **不要在错误的通道里"试探性充值"**
   如果你已经往通用账户充了钱，用通用地址调用就会真的开始扣那笔钱，而套餐额度依旧原封不动——这是最常见的"钱花了两遍"的坑。

## 一句话总结

Coding Plan 的额度只在 `/api/coding/paas/v4/`（或 `/api/anthropic`）这些**专用地址**上生效；把 `base_url` 里加上 `coding/` 就好，不要充值。
