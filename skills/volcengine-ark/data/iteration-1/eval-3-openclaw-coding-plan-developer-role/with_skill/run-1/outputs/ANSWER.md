# OpenClaw + 火山方舟 Coding Plan：两个问题的解释与修正

修正后的配置见同目录 `openclaw.json`（只含 `models` / `agents` / `gateway` 三个节点，按官方建议**合并**进你现有的 `~/.openclaw/openclaw.json`，不要整份覆盖）。改完执行：

```bash
pkill -f openclaw; openclaw gateway restart
```

如果 `~/.openclaw/agents/main/agent/models.json` 也存在且 `baseUrl` 和全局不一致，把它删掉（它优先级高于 `openclaw.json`），再重启 gateway。

---

## 问题一：`HTTP 400 ... messages.role ... invalid value: developer`

**原因**：方舟的 OpenAI 兼容接口只接受 `system` / `user` / `assistant` / `tool` 四种 role，不支持 OpenAI 新版协议里的 `developer` role。OpenClaw 默认把系统提示按 `developer` 角色发出去，方舟网关直接拒绝。这条报错已在 2026-09-04 用真实 API 复现（Agent Plan 入口，同一网关），原文：

```json
{"error":{"code":"InvalidParameter","message":"The parameter `messages.role` specified in the request are not valid: invalid value: `developer`, supported values are: `system`, `assistant`, `user`, `tool`. Request id: ...","param":"","type":"BadRequest"}}
```

**修法**：在 provider 下**每一个 model 对象里**加

```json
"compat": { "supportsDeveloperRole": false }
```

OpenClaw 会改用 `system` 角色发送。注意 `compat` **必须放在 model 级别**，放到 provider 级别会报 `Unrecognized key: "compat"`（官方 FAQ 明确说明）。`openclaw.json` 里两个模型都已经加好。

---

## 问题二：Base URL `https://ark.cn-beijing.volces.com/api/v3` 是错的

你的担心是对的。同一个域名下有三套互不通用的入口，Base URL / Key / model 三者必须配套：

| | 标准后付费 API | **Coding Plan（你买的这套）** | Agent Plan |
|---|---|---|---|
| OpenAI 协议 Base URL | `.../api/v3` | **`.../api/coding/v3`** | `.../api/plan/v3` |
| Anthropic 协议 Base URL（Claude Code 用） | — | `.../api/coding` | `.../api/plan` |
| Key | 方舟 API Key | **方舟 API Key（同一把）** | Agent Plan 专属 Key |
| `model` 写法 | 带日期 Model ID，如 `doubao-seed-2-0-lite-260428` | **小写 Model Name，如 `doubao-seed-2.0-lite`** | 同 Coding Plan |

`/api/v3` 是**标准后付费**入口。Coding Plan 用的是方舟 API Key，这把 Key 打 `/api/v3` **不会报错**，请求会正常成功——但**不消耗套餐额度，而是从后付费余额里按 token 扣钱**。官方文档原话：「请勿使用 `https://ark.cn-beijing.volces.com/api/v3`：该 Base URL 不会消耗您的 Coding Plan 额度，而是会产生额外费用。」所以这是最坑的一种错：表面一切正常，账单在别处。

OpenClaw 走 OpenAI 协议，正确值是：

```
https://ark.cn-beijing.volces.com/api/coding/v3
```

建议顺手去控制台费用中心看一眼，之前的调用是否已经产生了后付费账单。

**模型名 `doubao-seed-2.0-lite` 是对的**。Coding Plan / Agent Plan 入口用的就是这种不带日期、版本号用点的小写 Model Name。它在 Coding Plan 支持列表里，也是官方算额度的基准模型。补充两点：

- 实测 Plan 入口会把 `doubao-seed-2.0-lite` 解析到一个固定日期版本（响应 `model` 字段回显 `doubao-seed-2-0-lite-260215`），Name 本身无法锁版本，这是正常现象。
- 如果之前在 `/api/v3` 下用 `doubao-seed-2.0-lite` 也跑通了，说明标准入口也接受 Name——但那仍然是后付费。

---

## 配置里其他几处的说明

- **provider id `volcengine-plan`**：官方 Coding Plan 文档里 OpenClaw 示例的 id，`agents.defaults.model.primary` 与 `agents.defaults.models` 白名单里的 `volcengine-plan/...` 前缀要和它一致；如果你原来用了别的 id，三处一起改。
- **`"api": "openai-completions"`**：你的报错是 Chat Completions 形态（`messages.role`），说明当前走的就是这个；官方通用示例也可选 `"openai-responses"`（Plan 入口已支持 Responses API），两者都可以，`compat` 写法不变。
- **`apiKey`**：填控制台「API Key 管理」里的方舟 API Key（不是 Agent Plan 专属 Key，那把 Key 打 `/api/coding/v3` 会 401）。OpenClaw 要求把 Key 写进文件，请把 `~/.openclaw/openclaw.json` 权限收紧（`chmod 600`）。
- **`ark-code-latest`**：可选的第二个模型，是"控制台切换"占位名——配置文件填它，然后在控制台「开通管理」里选具体模型或 Auto 模式（3–5 分钟生效）。注意**不能**直接把 `model` 写成 `auto`，实测返回 404 `UnsupportedModel`。
- **`contextWindow` / `maxTokens` / `input`** 是 OpenClaw 侧声明，不影响方舟计费；`doubao-seed-2.0-lite` 支持视觉理解，所以 `input` 含 `"image"`。
- **可选：记忆检索 Embedding**。Coding Plan 附带 `doubao-embedding-vision`，想用 OpenClaw 的 `memorySearch` 时在 `agents.defaults` 下加（同样走 `/api/coding/v3` + 方舟 Key，会消耗套餐额度）：

  ```json
  "memorySearch": {
    "provider": "openai",
    "model": "doubao-embedding-vision",
    "remote": {
      "baseUrl": "https://ark.cn-beijing.volces.com/api/coding/v3",
      "apiKey": "<你的方舟 API Key>"
    }
  }
  ```

## 验证方式

不要用 curl 直接打 `/api/coding/v3` 测连通性——官方声明 Coding Plan 「仅限 AI 编程工具内使用，不能用于 API 调用」，在非编程工具里调用可能被判滥用停用。重启 gateway 后在 `openclaw tui` 里 `/models` 看列表、发一句话看是否正常回复即可；再去 Coding Plan 控制台（`console.volcengine.com/ark/region:cn-beijing/subscription/coding-plan`）确认额度在减少、后付费账单不再增长。

若改完仍报错，常见对应关系：`401 AuthenticationError` = Key 类型和 Base URL 不配对；`400 InvalidSubscription` = 账号没有生效中的 Coding Plan；`404 UnsupportedModel` = 模型名不在套餐内或写成了 `auto`；`429 QuotaExceeded` = 5 小时 / 周 / 月额度用完，等刷新。
