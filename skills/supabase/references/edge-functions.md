# Edge Functions：Deno 运行时的 serverless 函数

> 来自 https://supabase.com/docs/guides/functions、`guides/functions/quickstart`、`guides/functions/auth`、`guides/functions/dependencies`、`guides/functions/secrets`、`guides/functions/limits`、`guides/getting-started/migrating-to-new-api-keys`（Edge Function 部分）。抓取于 2026-09-21。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录。

## 目录

- [是 Deno，不是 Node](#是-deno不是-node)
- [创建与部署](#创建与部署)
- [调用方式](#调用方式)
- [鉴权模式](#鉴权模式)
- [环境变量与 secrets](#环境变量与-secrets)
- [限制](#限制)

## 是 Deno，不是 Node

**Edge Functions 只支持 TypeScript，运行在 Deno 上，不是 Node.js 兼容层**——这是本 skill 要点名的最大陷阱：很多"这个 npm 包能不能直接用"的判断，凭 Node 经验会出错。

- **导入 npm 包必须带 `npm:` 说明符前缀**，裸 `import x from 'package'` 不工作：

  ```ts
  import { createClient } from 'npm:@supabase/supabase-js@2'
  import Stripe from 'npm:stripe'
  ```

- **内置 Node API 走 `node:` 前缀**：`import process from 'node:process'`。
- **JSR/deno.land 模块**走 `jsr:`/直接 URL：`import path from 'jsr:@std/path@1.0.8'`。
- 每个函数建议有自己独立的 `deno.json`（管依赖版本，等价于 `package.json`），而不是整个 `supabase/functions` 目录共用一份——避免改一个函数的依赖版本连带影响另一个函数。旧的 `import_map.json` 方式仍支持但官方称为 legacy，两者都存在时 `deno.json` 优先。
- **任何依赖原生编译/多线程的 npm 包在这个运行时下不受支持**，官方文档点名的例子正是图片处理常用的 `libvips`/`sharp`——这类"Node 生态里理所当然能用的包"在 Edge Functions 里会失败，需要找纯 JS/Wasm 替代（比如换成 Deno 自己的图片处理库或调用外部服务），不能假设"npm 上能装的包就能在 Edge Function 里跑起来"。
- Web Worker API（以及等价的 Node `vm` 模块）不可用。
- 私有 npm registry 需要函数目录下自己的 `.npmrc`，同样是"每个函数独立配置"的模式。

`⚠ 文档原文，未实测`。

## 创建与部署

```bash
supabase functions new hello-world    # 生成 supabase/functions/hello-world/index.ts
supabase functions serve hello-world  # 本地跑，依赖 Docker
supabase functions deploy hello-world # 部署到全球边缘节点
supabase functions deploy             # 不带函数名 = 部署全部
```

默认生成的模板代码：

```ts
export default {
  fetch: withSupabase({ auth: ['publishable', 'secret'] }, async (req, ctx) => {
    const { name } = await req.json()
    return Response.json({ message: `Hello ${name}!` })
  }),
}
```

`export default { fetch }` 和 `Deno.serve(handler)` 是等价的两种写法；`fetch` 风格额外的好处是同一份代码理论上也能跑在 Cloudflare Workers/Bun 这类同样认 `fetch` handler 协议的运行时上（未验证这种可移植性的实际效果）。`⚠ 文档原文，未实测`。

## 调用方式

```bash
curl --request POST '<SUPABASE_URL>/functions/v1/hello-world' \
  --header 'apikey: <PUBLISHABLE_KEY>' \
  --header 'Content-Type: application/json' \
  --data '{"name":"Production"}'
```

```js
const { data, error } = await supabase.functions.invoke('hello-world', {
  body: { name: 'JavaScript' },
})
```

需要自己处理 CORS（如果会被浏览器直接调用）。

## 鉴权模式

新的 `@supabase/server` SDK（`npm:@supabase/server`）把"验证调用方身份 + 拿一个配好权限的 client"打包成一个 `withSupabase` 包装器，按声明的 `auth` 模式匹配：

| 模式 | 接受什么 | 拿到的 client |
| --- | --- | --- |
| `'user'` | `Authorization` 上的用户 JWT | `ctx.supabase`（受该用户 RLS 约束） |
| `'secret'` | `apikey` 上的 secret key | `ctx.supabaseAdmin`（绕过 RLS） |
| `'publishable'` | `apikey` 上的 publishable key | 无特殊身份，仅验证是合法的项目 key |
| `'none'` | 任何调用方，不做检查 | 用于对外签名 webhook（自己在 handler 里验证签名） |

```ts
import { withSupabase } from 'npm:@supabase/server'

export default {
  fetch: withSupabase({ auth: 'user' }, async (_req, ctx) => {
    // ctx.supabase 已经按调用者的 RLS 权限配置好
    return Response.json({ email: ctx.userClaims?.email })
  }),
}
```

- **面向用户调用的函数**：保持 `verify_jwt = true`（默认值，平台会先校验 JWT 再进你的代码）+ `auth: 'user'`。
- **服务间调用的函数**（cron、`pg_net`、另一个 Edge Function）：`verify_jwt = false` + `auth: 'secret'`——因为新版 secret key **不是 JWT**，平台内置的 `verify_jwt` 检查理解不了它，必须关掉这个平台检查，改由 SDK/自己的代码验证。
- `auth` 可以传数组按顺序尝试多种模式：`auth: ['user', 'secret']`，用 `ctx.authMode` 判断实际匹配到哪种。
- 外部 webhook（Stripe、GitHub 这类不发送 Supabase 凭证、而是自己签名请求体的调用方）用 `auth: 'none'` 跳过 SDK 的凭证检查，**必须**在 handler 里自己验证签名，否则等于完全不鉴权。
- 不用 `@supabase/server` SDK、自己手写鉴权时，要注意**新版 publishable/secret key 只应该放在 `apikey` header**，很多 Supabase 客户端默认也会把同一个值塞进 `Authorization: Bearer`，这会被平台当 JWT 解析报 `Invalid JWT`——用新 key 时记得给对应函数设 `verify_jwt = false`，让自己的代码/SDK 而不是平台内置检查来处理鉴权。

`⚠ 文档原文，未实测`。

## 环境变量与 secrets

运行时自动注入（不需要自己配置）：

| 变量 | 内容 |
| --- | --- |
| `SUPABASE_URL` | 项目 URL |
| `SUPABASE_PUBLISHABLE_KEYS` / `SUPABASE_SECRET_KEYS` | 按 key 名索引的 JSON 对象（新版），例如 `JSON.parse(Deno.env.get('SUPABASE_SECRET_KEYS'))['default']` |
| `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | 旧版 key，仍然存在，但读取意味着走的是被弃用的路径 |
| `SUPABASE_JWKS` | 用于验证用户 JWT 的 JSON Web Key Set |

自定义 secrets（第三方 API key 等）用 `supabase secrets set` 管理，或在 Dashboard **Edge Functions > Secrets** 里配置，运行时通过 `Deno.env.get('MY_SECRET')` 读取；**自定义 secret 名不能以 `SUPABASE_` 开头**（该前缀保留给平台自己用）。

## 限制

| 项目 | 数值 |
| --- | --- |
| 内存上限 | 256MB |
| Wall clock 时长 | 免费版 150s，付费版 400s |
| CPU 时间 | 每请求 2s（不含异步 I/O 等待） |
| 请求空闲超时 | 150s（超时返回 504） |
| 函数体积 | CLI 本地打包 20MB / 服务端打包（Dashboard/Management API）5MB |
| 单函数最大并发递归调用 | 约 5000 次/分钟 |
| Secrets 数量/大小 | 最多 100 个，单个最大 48 KiB |
| 出站端口限制 | 25、587 端口禁止外呼（常见邮件协议端口，防滥用） |

出错时响应带 `sb-error-code` header，可编程识别（`EDGE_FUNCTION_ERROR` 未捕获异常、`IDLE_TIMEOUT` 超时无响应、`WORKER_LIMIT`/`WORKER_RESOURCE_LIMIT` 资源超限等），完整列表见 `references/errors-and-limits.md`。

`⚠ 文档原文，未实测`。
