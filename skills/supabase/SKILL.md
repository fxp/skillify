---
name: supabase
description: 接入 Supabase（supabase.com/docs）的开发者手册，面向用 Supabase 做后端的 AI Agent 场景——涵盖数据库自动生成的 REST API（PostgREST：filter 查询字符串语法、select 的关联查询/join、Prefer 头 upsert）、anon/service_role（及新版 publishable/secret）key 与 Row Level Security 的权限关系、Auth（注册登录、JWT 结构、auth.uid() 与 RLS 的联动）、Storage（bucket、上传下载、公开/签名 URL）、Realtime（对表变更的 WebSocket 订阅）、Edge Functions（Deno 运行时的 serverless 函数）。当用户提到 "Supabase" "supabase.com" "supabase-js" "supabase-py" "@supabase/supabase-js" "PostgREST" "anon key" "service_role" "Row Level Security" "RLS"，或要写代码调用 Supabase 的数据库/鉴权/存储/实时/函数能力时，应主动使用本技能，不要凭记忆编造 filter 查询字符串写法或搞混 anon/service_role 该用在哪一侧。不覆盖：Supabase Management API（管理组织/项目/分支的平台级 API，和本 skill 讲的项目内 Data API 是两回事）、GraphQL（pg_graphql 扩展）、自托管部署。
---

# Supabase 接入指南

Supabase（supabase.com）是一个 Postgres-as-a-backend 平台，围绕一个真实的 Postgres 数据库打包了几块彼此独立但共享同一套鉴权/权限模型的产品：**Data API**（PostgREST 自动从表结构生成的 REST 接口）、**Auth**（用户注册登录、JWT 签发）、**Storage**（文件对象存储）、**Realtime**（WebSocket 订阅）、**Edge Functions**（Deno 运行时的 serverless 函数）。这几块产品深度不一，本 skill **不追求平均覆盖**：REST/RLS/Auth 是几乎所有 Agent 生成代码都会用到的核心，写得最细；Storage/Realtime/Edge Functions 覆盖常见任务；GraphQL、Management API（管理项目/组织本身，而不是项目里的数据）、自托管部署完全不覆盖，需要时应查官方文档。

## ⚠ 验证状态

**本 skill 目前只完成了第 1、2 步（抓取官方文档 + 结构化撰写），第 3 步（用真实 API key 逐条验证）尚未进行——写作时没有可用的 Supabase 项目和 key。**

- 所有字段名、query string 语法、错误码、header 格式均来自 **supabase.com/docs 官方页面原文**（`llms.txt` 索引下的 guides，抓取于 2026-09-21）和 **postgrest.org 官方文档**（PostgREST 是 Supabase Data API 的底层实现，两者对 filter/select/Prefer 语法的描述一致），不是凭训练记忆编写的。
- 但是：**没有一条结论经过真实调用验证**。每个 reference 文件里涉及"实际行为"的描述都标了 `⚠ 文档原文，未实测`——文档说的"必填"是否真的报错、RLS 策略写错时是报错还是静默返回空、`Prefer` 头的组合是否真按文档生效，这些统统未经验证。其他平台的经验（智谱、AutoDL 案例）表明文档和真实行为不一致是常态，不是例外。
- 验证计划见 `supabase-workspace/verification-plan.md`，拿到 key 后按优先级逐条测，测完把对应 reference 里的 `⚠ 文档原文，未实测` 改写成"已用真实 API 验证（日期）：……"并附原始响应/报错。
- `evals/evals.json` 里的场景是基于文档字面推测的"有经验开发者会凭其他后端框架的直觉写错"的陷阱，同样未经真实调用验证打分，仅供后续对照实验使用。

## 用之前先确认的几件事

1. **这是全篇最重要的一条：三种 key 分两个安全等级，用错的后果是把整个数据库暴露给所有人。**

   | 等级 | 旧命名（JWT，官方计划 2026 年底前弃用但目前仍是主流） | 新命名（短字符串，非 JWT，官方推荐） | 映射到的 Postgres 角色 | 能不能出现在浏览器/客户端代码里 |
   | --- | --- | --- | --- | --- |
   | 低权限 | `anon` | `sb_publishable_...` | 未登录时 `anon`；用户用 Supabase Auth 登录后该请求变成 `authenticated` | **可以**，专门设计给公开代码用 |
   | 高权限 | `service_role` | `sb_secret_...` | `service_role`（带 Postgres 的 `BYPASSRLS` 属性） | **绝不可以**，只能在你自己控制的服务端/Edge Function/Worker 里用 |

   `service_role` / `sb_secret_...` **完全绕过 Row Level Security**，不是"权限更大的用户"而是"没有行级限制"——一旦这个 key 出现在前端 bundle、Git 仓库或日志里，等于任何人都能读写你整个数据库的任意一行，不需要再攻破别的东西。写任何 Supabase 相关代码前，先确认这段代码跑在哪：**跑在用户设备/浏览器上的一律用 anon/publishable key**；只有明确跑在你控制的服务器、Edge Function、CI 脚本里才能用 service_role/secret key。

2. **anon key 权限不够时，表现是"悄悄成功"而不是报错，容易被误判为"代码没问题"。** Postgres 对 Data API 请求做两层检查，顺序固定：
   - 先查 **grant**（`GRANT SELECT ON table TO anon` 这类）——没有 grant 直接报 `42501 permission denied`，这是真正的"报错"。
   - 再查 **RLS policy**——有 grant 但策略把这一行过滤掉了，**不报错，返回 `200` + 空数组/空结果**，看起来像是"查询执行成功但恰好没数据"。
   
   所以用 anon key 调用返回空结果时，不能默认是"这个表本来就没数据"，要先确认 RLS 策略而不是查询语法。反过来，新建表默认 RLS 未开启，此时任何有 grant 的角色（包括 anon）能读写**全表所有行**——"忘记开 RLS"和"开了 RLS 但策略写错"是两种完全不同、后果也不同的坑，都要在导出到生产前检查。

3. **不要把 `anon` Postgres 角色和 Supabase Auth 里的"匿名用户"（Anonymous sign-in）搞混。** 前者是"这个请求没带用户 JWT"的角色标识；后者是 Auth 的一个具体登录方式，登录后该用户其实拥有 `authenticated` 角色和一个真实 `auth.uid()`，只是 JWT 里 `is_anonymous: true`。RLS 策略里 `to anon` 和"排除匿名登录用户"不是一回事。

4. **两套 key 系统眼下同时有效**，Supabase 正在把 `anon`/`service_role`（JWT，形如 `eyJ...`）迁移到 `sb_publishable_...`/`sb_secret_...`（短字符串，非 JWT），计划 2026 年底前弃用旧的。老教程、老代码、大多数训练语料里出现的都是 `anon`/`service_role`——两套目前功能等价、行为一致（安全属性完全相同），本 skill 两套都讲，新项目建议直接用新命名。**关键差异**：新 key 必须放在 `apikey` header，放到 `Authorization: Bearer` 会被当 JWT 解析而失败；已登录用户的会话 JWT 永远放 `Authorization: Bearer`，与 `apikey`（哪种 key 都行）是两个不同的 header、装两个不同的值。

## 30 秒跑通第一个请求

假设已经在 Dashboard 建好一个 `todos` 表，并 `grant select on public.todos to anon`：

```bash
curl 'https://<PROJECT_REF>.supabase.co/rest/v1/todos?select=*' \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

```python
import os
from supabase import create_client

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_PUBLISHABLE_KEY"],  # 老项目用 SUPABASE_ANON_KEY 的值也行
)
resp = supabase.table("todos").select("*").execute()
print(resp.data)
```

成功返回该表所有 `anon` 角色可见的行（受 RLS 影响，见上）。`⚠ 文档原文，未实测`。

## 能力域导航

| 我想做什么 | 读哪个文件 | 涉及的核心接口 |
| --- | --- | --- |
| 直接对表做增删改查、过滤、分页、关联查询、批量 upsert | [`references/rest-api.md`](references/rest-api.md) | `GET/POST/PATCH/DELETE /rest/v1/{table}`、`POST /rest/v1/rpc/{function}` |
| 该用 anon 还是 service_role、RLS policy 怎么写、用户注册登录、JWT 里有什么、`auth.uid()` 怎么和 RLS 联动 | [`references/auth-and-rls.md`](references/auth-and-rls.md) | `POST /auth/v1/signup`、`POST /auth/v1/token?grant_type=password`、`GET /auth/v1/user`、`create policy` |
| 上传/下载文件、建 bucket、公开 URL vs 签名 URL、storage 的 RLS | [`references/storage.md`](references/storage.md) | `POST /storage/v1/object/{bucket}/{path}`、`GET /storage/v1/object/(public|sign)/...` |
| 订阅表变更（insert/update/delete）、Broadcast、Presence | [`references/realtime.md`](references/realtime.md) | WebSocket `wss://.../realtime/v1/websocket`，`channel().on('postgres_changes', …)` |
| 写一个跑在 Deno 上的 serverless 函数、怎么鉴权调用方、部署 | [`references/edge-functions.md`](references/edge-functions.md) | `POST /functions/v1/{function-name}` |
| 查错误码含义、限流、各产品的硬限制 | [`references/errors-and-limits.md`](references/errors-and-limits.md) | PostgREST/Storage/Edge Functions 错误码表 |

## 跨领域的通用规则（写代码前必读）

1. **key 选型 = 安全问题，不是配置细节。** 见上方"确认几件事"第 1、2 条，这是本 skill 唯一要求放进 SKILL.md 正文（而不只是 reference）的规则，因为它是"看起来能跑通、实际上留了后门"或"看起来报错、实际上只是权限设错"这两类最容易被 Agent 忽略的坑的共同根源。
2. **PostgREST 的 filter 是 URL query string，不是 JSON body。** `GET /rest/v1/todos?id=eq.5&score=gte.10` 这种 `column=operator.value` 写法，和大多数"在请求体里传一个 filter 对象"的 REST API 习惯完全不同；`POST`/`PATCH`/`DELETE` 同样用 query string 表达"作用在哪些行"，body 只放要写入的数据。细节见 `references/rest-api.md`。
3. **REST 请求的两个鉴权 header 职责不同，不要合并成一个。** `apikey` 标识"哪个项目/哪把项目级 key"；`Authorization: Bearer` 装的是**用户的会话 JWT**（登录后）或**同一把 apikey 的值**（未登录时的通用写法）。已登录场景下这两个 header 的值应该不同——`apikey` 还是 publishable/anon key，`Authorization` 换成用户登录后拿到的 access token，RLS 才会按 `authenticated` + `auth.uid()` 生效而不是退回 `anon`。
4. **Realtime 的 Postgres Changes 需要两件事同时满足才会收到消息，只做一件是常见的"订阅了但收不到"根因**：(a) 该表已 `alter publication supabase_realtime add table <table>`（或在 Dashboard Publications 里勾选），(b) 调用方对该表有 grant + 能通过 RLS 读到这一行。**DELETE 事件是唯一的例外**：Postgres 层面 RLS 无法对"已经被删除的行"做判断，所以 delete 广播**不受 RLS 限制**，只受 publication 是否包含该表限制——设计涉及删除通知的功能时要单独考虑这一点，不能假设"RLS 保护了 select 就保护了 delete 通知"。
5. **Edge Functions 跑在 Deno 上，不是 Node**，多数 npm 包能通过 `import x from 'npm:package@version'` 这种带 `npm:` 前缀的说明符使用（普通 `import x from 'package'` 不行），但任何依赖原生编译/多线程的包（典型例子：图片处理常用的 `sharp`/`libvips`）在这个运行时下不受支持，需要找纯 JS/Wasm 替代或换用 Deno/Web 标准 API。细节见 `references/edge-functions.md`。
6. **`service_role`/secret key 绕过 RLS 只在请求不带用户 access token 时成立。** 如果用 service_role key 初始化的客户端又设置了某个用户的 session（比如服务端先帮用户登录再复用同一个 client），这次请求会按该用户的 RLS 权限走，而不是自动拿到管理员权限——"用了 service_role client"不等于"这次调用一定绕过 RLS"，取决于有没有夹带用户 JWT。
7. **官方 client library 包名**：JS/TS 用 `@supabase/supabase-js`，Python 用 `supabase`（PyPI 包名是 `supabase`，导入名一致，GitHub 仓库叫 `supabase-py`），此外还有 Dart（`supabase_flutter`）、Swift（`supabase-swift`）、Kotlin（`supabase-kt`，社区维护）。不确定包名时以这份列表为准，不要凭其他平台命名习惯猜测（比如误当成 `supabase-client`）。

## 本 skill 不覆盖

Management API（`api.supabase.com`，管理组织/项目/分支/配置本身的平台级 API，和本 skill 讲的"项目内数据 API"是两回事，不要混用）、GraphQL（`pg_graphql` 扩展提供的 `/graphql/v1` 端点）、自托管部署（Docker/Kubernetes 自建 Supabase 栈）、数据库扩展生态（pgvector 向量检索、Cron、Queues 等，各自足够大，需要时单独查）、第三方 Auth 提供商细节（各 OAuth provider 的具体配置步骤）、S3 兼容的 Storage 协议入口。这些的入口都在 supabase.com/docs 左侧导航，需要时按同样的方法论单独补。

## 目录结构

```
supabase/
├── SKILL.md
├── references/
│   ├── rest-api.md          # PostgREST：filter/select/embedding、Prefer 头、mutations、分页
│   ├── auth-and-rls.md      # key 选型细节、RLS policy 写法、注册登录、JWT、auth.uid()
│   ├── storage.md           # bucket、上传下载、公开/签名 URL、storage.objects 的 RLS
│   ├── realtime.md          # postgres_changes、Broadcast、Presence、publication 与 RLS 要求
│   ├── edge-functions.md    # Deno 运行时、鉴权模式、npm 依赖、部署、限制
│   └── errors-and-limits.md # 各产品错误码表、限流、硬限制
└── evals/
    └── evals.json           # 对照实验场景（打包时自动排除）
```

内容整理自 https://supabase.com/docs（`llms.txt` 索引下的 guides，抓取于 2026-09-21）与 https://postgrest.org（PostgREST 官方文档，Supabase Data API 的底层实现），实际调用报错优先信任 API 而非本文档。
