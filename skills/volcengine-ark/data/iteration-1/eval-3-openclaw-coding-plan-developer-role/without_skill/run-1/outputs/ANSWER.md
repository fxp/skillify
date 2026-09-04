# OpenClaw + 火山方舟 Coding Plan：两个问题的原因与修法

> 修好的 provider 配置见同目录 `openclaw.json`。把其中 `models` 和 `agents.defaults.model` 两段合并进你的 `~/.openclaw/openclaw.json`（provider 名字 `volcengine-coding` 可以随意改，但 `agents.defaults.model.primary` 里的前缀要跟着改）。
> 说明：本答案基于我对 OpenClaw 与火山方舟平台的既有认知整理，未联网核对；文末列了几处建议你在控制台 / 官方文档里再确认一下的点。

---

## 问题 1：`HTTP 400 The parameter messages.role specified in the request are not valid: invalid value: developer`

### 原因

- 火山方舟的 Chat Completions 接口（`/chat/completions`）只接受 `system` / `user` / `assistant` / `tool` 四种 `messages[].role`。`developer` 是 OpenAI 在 o1 / gpt-5 系列之后新引入的角色（用来替代 `system`），方舟并不认这个值，所以直接 400。
- OpenClaw 底层的 OpenAI 兼容适配层（pi-ai 的 `openai-completions`）有一个"发现是推理模型就把 system prompt 以 `developer` 角色发送"的行为。你的模型 `doubao-seed-2.0-lite` 是带思考能力的模型（配置里 `reasoning: true`，或者被自动判定为推理模型），于是 OpenClaw 把系统提示词打成了 `role: "developer"` 发给方舟。
- 这不是 base URL 的问题：换成 `/api/coding/v3` 之后同样会报这个错，因为两条链路背后都是方舟的 Chat Completions 校验。

### 修法

在 provider 上显式声明"这家不支持 developer 角色"，OpenClaw 就会退回 `system`：

```json
"compat": {
  "supportsDeveloperRole": false,
  "supportsStore": false,
  "supportsReasoningEffort": false
}
```

- `supportsDeveloperRole: false` —— 关键项，system prompt 恢复为 `role: "system"`。
- `supportsStore: false` —— 不发 OpenAI 专有的 `store` 字段，避免方舟报"未知参数"。
- `supportsReasoningEffort: false` —— 不发 `reasoning_effort`（方舟的思考开关是 `thinking: {type: ...}`，不认 `reasoning_effort`）。

另一种"粗暴"修法是把模型的 `reasoning` 设为 `false`，developer 角色也会消失，但会丢掉 OpenClaw 对推理模型的一些处理（比如 thinking 相关 UI），不推荐；用 `compat` 更干净。

---

## 问题 2：base URL 与模型名

### base URL：`https://ark.cn-beijing.volces.com/api/v3` 填错了（对 Coding Plan 而言）

火山方舟有两套入口，用同一把 API Key，但计费口径完全不同：

| 用途 | Base URL | 计费 |
|---|---|---|
| 普通按量付费（模型推理 / 在线推理接入点） | `https://ark.cn-beijing.volces.com/api/v3` | 按 token 计费，需要在控制台"开通模型服务" |
| **Coding Plan（编码套餐）** | **`https://ark.cn-beijing.volces.com/api/coding/v3`** | 走套餐额度，不另计 token 费 |

你现在填的是 `/api/v3`，会出现两种情况之一：

1. 该模型在按量付费里已经开通 → 请求成功，但**扣的是按量付费余额，Coding Plan 的额度一点没用上**；
2. 没开通 / 账户无余额 → 直接报错（4xx，"model not activated / 账户欠费"一类）。

所以 Coding Plan 用户必须把 `baseUrl` 改成 `https://ark.cn-beijing.volces.com/api/coding/v3`。OpenClaw 会在这个前缀后面拼 `/chat/completions`，不要在末尾多加斜杠或路径。

### 模型名：`doubao-seed-2.0-lite` 本身没问题，但要确认在套餐范围内

- Coding Plan 的模型是按**模型名**直接调用（`doubao-seed-2.0-lite`、`doubao-seed-2.0-pro`、`doubao-seed-2.0-code`，以及套餐内接入的第三方模型如 `kimi-k2.5`、`glm-4.7`、`deepseek-v3.2` 等），**不需要**创建 `ep-xxxx` 推理接入点。
- 但 Coding Plan 只覆盖套餐页面列出的那几个模型，套餐外的模型走 coding 入口会被拒。`doubao-seed-2.0-lite` 按我的了解是在套餐里的；建议在控制台"编码套餐 → 支持模型"页面核对一遍，我在 `openclaw.json` 里顺手把 `pro` / `code` 两个也注册了，方便你切换（`openclaw models list` 能看到）。
- 如果你之后要用按量付费入口（`/api/v3`），模型名同样可以直接用 `doubao-seed-2.0-lite`（方舟已支持按 Model ID 调用），前提是先在控制台开通该模型。

---

## 配置说明（`openclaw.json` 逐项）

```json5
{
  models: {
    mode: "merge",                       // 保留 OpenClaw 内置 provider，只叠加我们这一个
    providers: {
      "volcengine-coding": {
        baseUrl: "https://ark.cn-beijing.volces.com/api/coding/v3",  // Coding Plan 专用入口
        apiKey: "${ARK_API_KEY}",        // 从环境变量读取；也可以直接写明文 key
        api: "openai-completions",       // 方舟是 OpenAI Chat Completions 兼容协议
        compat: { supportsDeveloperRole: false, supportsStore: false, supportsReasoningEffort: false },
        models: [ { id: "doubao-seed-2.0-lite", reasoning: true, input: ["text","image"], cost: {...0}, contextWindow: 256000, maxTokens: 32000 }, ... ]
      }
    }
  },
  agents: { defaults: { model: { primary: "volcengine-coding/doubao-seed-2.0-lite" } } }
}
```

几点补充：

- `apiKey` 用了 `${ARK_API_KEY}` 占位，请 `export ARK_API_KEY=你的方舟APIKey`（写进 shell profile 或 OpenClaw gateway 的环境）。不想用环境变量就直接把 key 字符串填进去。
- `cost` 全部填 0 只是为了让 OpenClaw 的用量统计不乱算；Coding Plan 本身是套餐计费。
- `contextWindow` / `maxTokens` 是按 Seed 2.0 系列公开规格填的保守值（256K 上下文、32K 输出），可按控制台标注调整。
- 我没有引用 OpenClaw 可能自带的 `volcengine` 内置 provider，因为它默认指向 `/api/v3`（按量付费）；单独起一个 `volcengine-coding` 更清楚。

## 改完之后

```bash
openclaw config validate            # 语法 / schema 检查（若你的版本没有此命令可跳过）
openclaw models list                # 应能看到 volcengine-coding/doubao-seed-2.0-lite
openclaw gateway restart            # 让 gateway 重新加载配置
```

然后随便发一条消息，`openclaw logs --follow`（或 gateway 日志）里请求应打到 `.../api/coding/v3/chat/completions`，且不再出现 `developer` 角色报错。

## 建议再核对的点

1. `supportsDeveloperRole` 等 `compat` 字段名以你安装的 OpenClaw 版本文档为准（`openclaw config schema` 或 docs 的 Model providers → compat 一节）；老版本若没有 `compat`，退路是把 `reasoning` 设为 `false`。
2. Coding Plan 当前支持的模型列表和每个模型的上下文 / 输出上限，以控制台"编码套餐"页面为准。
3. 如果你想改走 Anthropic Messages 协议（`api: "anthropic-messages"`，base URL 去掉 `/v3` 即 `https://ark.cn-beijing.volces.com/api/coding`），方舟 Coding Plan 也提供这条兼容链路（Claude Code 接入就是这么配的），同样不会有 developer 角色的问题；但 OpenAI 兼容链路对 OpenClaw 更常规，优先建议上面的方案。
