# Auth、Key 选型与 Row Level Security

> 来自 https://supabase.com/docs/guides/getting-started/api-keys、`guides/getting-started/migrating-to-new-api-keys`、`guides/api/securing-your-api`、`guides/database/postgres/row-level-security`、`guides/auth`、`guides/auth/jwts`、`guides/auth/jwt-fields`、`guides/auth/passwords`。抓取于 2026-09-21。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录。

## 目录

- [Key 类型详解](#key-类型详解)
- [Grant 与 RLS：两道独立的闸门](#grant-与-rls两道独立的闸门)
- [写 RLS policy](#写-rls-policy)
- [Auth：注册、登录、拿 JWT](#auth注册登录拿-jwt)
- [JWT 结构与 auth.uid()](#jwt-结构与-authuid)
- [绕过 RLS 的几种方式](#绕过-rls-的几种方式)

## Key 类型详解

Supabase 项目里始终存在两套key机制并行：

| | 旧（JWT，长字符串 `eyJ...`） | 新（短字符串，官方推荐） |
| --- | --- | --- |
| 低权限，给客户端用 | `anon` | `sb_publishable_...` |
| 高权限，只能服务端用 | `service_role` | `sb_secret_...` |

- **两套同时有效**，创建新 key 不会让旧 key 失效，是否停用旧 key 是 Dashboard 里单独的一步。Supabase 计划在 **2026 年底前弃用** `anon`/`service_role`，但目前文档、SDK、大多数现存代码仍以旧命名为主，本 skill 两套都覆盖。
- **两套的安全语义完全相同**：低权限档映射到 Postgres `anon`/`authenticated` 角色，受 RLS 约束；高权限档映射到 `service_role` 角色，带 `BYPASSRLS` 属性，**完全绕过 RLS**。选错档次的后果不因为用的是新命名还是旧命名而不同。
- **新 key 不是 JWT**，只能放 `apikey` header；放 `Authorization: Bearer` 会被当 JWT 解析失败（迁移期兼容性检查会接受，但那只是格式检查通过，不代表鉴权通过）。旧 key 因为本身就是 JWT，两个 header 都能放。
- **新 secret key 多一层保护**：请求带浏览器 `User-Agent` 时直接返回 `401`，防止不小心被打包进前端代码后还能用；旧 `service_role` 没有这层保护，泄漏后立刻可用。
- 本地 `supabase start` 打印的 publishable/secret key 只对本地栈有效，和线上项目的 key 无关联。`⚠ 文档原文，未实测`。

**该用哪个 key，按代码运行的位置判断，不是按"这段代码看起来重不重要"判断**：

- 跑在用户设备上的任何代码（网页、打包后的 App、CLI 工具、任何用户能反编译/抓包看到的地方）→ **anon / publishable**。
- 只跑在你自己控制、用户拿不到的地方（你的服务器、Edge Function、CI/CD 脚本、定时任务）→ **service_role / secret**，且**永远不要**把它传到浏览器、写进公开仓库、打进日志、放进 URL query string。

## Grant 与 RLS：两道独立的闸门

Data API 对每个请求做两层独立检查，顺序固定，行为**不对称**：

1. **Grant**（`GRANT SELECT/INSERT/UPDATE/DELETE ON table TO 角色`）：决定这个角色能不能碰这张表。没有对应 grant，直接返回 **`42501 permission denied`**（真正的 HTTP 错误，`service_role` 也不例外——grant 检查不看 `BYPASSRLS`）。
2. **RLS policy**：决定这个角色能碰到表里的哪些**行**。Grant 通过但策略把某一行排除，**不报错**，该行就是"看不见"——`SELECT` 场景下少一行，`UPDATE`/`DELETE` 场景下该行"没有被匹配"（不算失败，只是影响 0 行），返回码依然是成功的 `2xx`。

**这两种失败模式在应用层表现完全不同，混淆是最常见的调试弯路**：

| 失败原因 | 现象 | 排查方向 |
| --- | --- | --- |
| 缺 grant | 报 `42501` 错误 | 检查 `GRANT ... TO <角色>` 语句 |
| RLS policy 把行过滤掉了 | 不报错，返回空结果/未修改任何行 | 检查 policy 的 `using`/`with check` 表达式，以及当前请求实际映射到哪个角色 |

- **新建表默认没有开 RLS**。如果这张表所在 schema 的角色已经有 grant（很多现有项目的历史遗留：`public` schema 下新表默认给 `anon`/`authenticated`/`service_role` 都发了全部 CRUD 权限，Supabase 正在把这个默认改成不自动发放，但存量项目未必已经切换），未开 RLS 的表相当于对所有持有对应 grant 的角色完全开放，**不是"没配置等于安全"，是"没配置等于全开放"**。
- 官方建议：**开 RLS 和设 grant 放进同一次迁移**，先 `revoke all`，再按需 `grant`，最后写 policy，避免"grant 早于 policy 生效"的窗口期。
- 一张表在暴露的 schema 里但没有 RLS 也没被撤销默认 grant，属于文档明确标注的"危险"配置。

`⚠ 文档原文，未实测`。

## 写 RLS policy

Policy 本质是自动拼进查询的 `WHERE` 条件，按操作类型分别写（Postgres 不支持一个 policy 覆盖多种操作）：

```sql
alter table public.profiles enable row level security;

-- 读：只能看自己的
create policy "select own profile"
on profiles for select
to authenticated
using ( (select auth.uid()) = user_id );

-- 写：只能建自己的行
create policy "insert own profile"
on profiles for insert
to authenticated
with check ( (select auth.uid()) = user_id );

-- 改：using 决定能改哪些已有行，with check 决定改完之后的新值是否合法
create policy "update own profile"
on profiles for update
to authenticated
using ( (select auth.uid()) = user_id )
with check ( (select auth.uid()) = user_id );
```

要点：

- **务必用 `to` 子句显式限定角色**（`to authenticated` / `to anon`），不写默认对所有角色生效，容易把本该只给登录用户的策略意外套到 `anon` 头上。
- **`UPDATE` 没有对应 `SELECT` policy 时行为不完整**：官方文档明确提示 UPDATE 操作依赖一条 SELECT 策略才能正常工作，缺失时更新可能"看起来成功但拿不到返回行"或行为不符合预期。`⚠ 文档原文，未实测`。
- `auth.uid()` 在没有登录用户的请求（比如纯 anon key 调用）里返回 `null`，而 SQL 里 `null = 任何值` 恒为 `false`——写 `using (auth.uid() = user_id)` 在未登录场景会"安全地"拒绝所有行，但如果本意是要显式拒绝、最好写成 `using (auth.uid() is not null and auth.uid() = user_id)` 让意图更明确，避免和"策略写错导致意外拒绝"混淆。
- 把 `(select auth.uid())` 包一层 `select`（而不是裸 `auth.uid()`）是官方推荐的性能写法，能让 Postgres 优化器按语句缓存一次而不是按行重复调用；同理给 policy 过滤用到的列建索引。
- **`SECURITY DEFINER` 函数**能用来打破策略互相引用导致的 `42P17 infinite recursion detected in policy` 死循环（两张表的策略互相 exists 查对方），做法是把"查询另一张表"的逻辑挪进一个属主是 `postgres`（带 `bypassrls`）的函数里，函数内部 `set search_path = ''` 并给每个名字加 schema 前缀，防止调用方通过同名对象劫持权限。
- **视图默认不受 RLS 约束**（Postgres 特性，视图默认以创建者身份执行），Postgres 15+ 可以在建视图时加 `with (security_invoker = true)` 让视图遵守查询者自己的 RLS；旧版本只能靠不对外暴露该视图所在 schema、或收回视图本身的 grant 来控制。

`⚠ 文档原文，未实测`。

## Auth：注册、登录、拿 JWT

邮箱密码是最基础的方式，客户端库封装了整个流程：

```js
// 注册
const { data, error } = await supabase.auth.signUp({
  email: 'user@example.com',
  password: 'example-password',
})

// 登录
const { data, error } = await supabase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'example-password',
})
```

原始 HTTP（登录，`grant_type=password`）：

```bash
curl -X POST '<SUPABASE_URL>/auth/v1/token?grant_type=password' \
  -H "apikey: <PUBLISHABLE_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "example-password"}'
```

- 托管项目默认要求邮箱验证后才能登录（本地/自托管默认不要求），行为受 Dashboard **Auth Providers** 页配置控制。
- 登录成功返回一个 session，里面的 `access_token` 就是要放进后续请求 `Authorization: Bearer` 的 JWT；客户端库会自动管理这个 token 的存储和刷新，手写 HTTP 调用需要自己保存并在过期后用 `refresh_token` 换新的。`⚠ 文档原文，未实测`。
- Supabase Auth 还支持 magic link/OTP、OAuth 社交登录、SAML SSO、匿名登录、MFA 等方式，本 skill 只覆盖邮箱密码这条最基础路径，其余需要时查官方对应子页面。

## JWT 结构与 auth.uid()

Supabase 签发的 access token 是标准三段式 JWT（`header.payload.signature`），关键 claim：

| Claim | 含义 | 与 RLS 的关系 |
| --- | --- | --- |
| `sub` | 用户 UUID | `auth.uid()` 就是读这个字段 |
| `role` | Postgres 角色：`anon` / `authenticated` / `service_role` | RLS `to` 子句匹配的就是这个 |
| `aal` | 认证强度（`aal1` 单因素 / `aal2` 含 MFA） | 可在 policy 里用 `auth.jwt()->>'aal'` 判断，强制敏感操作要求 MFA |
| `app_metadata` | 应用写入、**用户自己改不了**的数据 | 适合放权限位/角色位，policy 里安全可信 |
| `user_metadata` | 用户可以自己通过 `auth.updateUser()` 改的数据 | **不要**用来做鉴权判断，用户能自己改 |
| `is_anonymous` | 是否匿名登录用户 | 区分"真实注册用户"和"Auth 的匿名会话"要看这个，不要看 `role` |

- `auth.jwt()` 能在 policy 里读取任意 claim（比如 `auth.jwt() -> 'app_metadata' -> 'teams'` 判断团队成员身份），但**改 `app_metadata` 之后现有 JWT 不会立刻更新**，要等 token 刷新才生效——如果 policy 依赖刚改的权限位，判断"改完立刻生效"是错的假设。`⚠ 文档原文，未实测`。
- 除了 Supabase Auth 签发的用户 JWT，`anon`/`service_role` 这两把旧版 key 本身也是**长期有效**的 JWT（`role` claim 直接是 `anon`/`service_role`，没有 `sub`），这也是它们和新版 `sb_publishable_/sb_secret_` 短字符串 key 的本质区别——新 key 不是 JWT，不能像旧 key 一样被当作"可以自己解码检查"的 token。

## 绕过 RLS 的几种方式（明确知道自己在做什么时才用）

1. **`service_role`/`sb_secret_...` key**：常规做法，仅限服务端代码。**但仅在请求不携带用户 access token 时才 100% 绕过**——如果用这把 key 初始化的客户端又设置了某个用户的 session/JWT，这次具体请求会按该用户的 RLS 权限走，不会自动获得管理员权限。
2. **`SECURITY DEFINER` 函数**：函数以创建者（通常是 `postgres`，带 `bypassrls`）身份运行，可以在函数内部合法地跳过某张表的 RLS，前提是这类函数**不能被暴露进 Data API 的 schema**（否则相当于把绕过 RLS 的能力直接开放给任何持有对应 `EXECUTE` grant 的角色）。
3. **给自定义 Postgres 角色加 `bypassrls` 属性**（`alter role xxx with bypassrls`）：用于系统级访问，不要和任何面向最终用户的登录凭证关联。

`⚠ 文档原文，未实测`。
