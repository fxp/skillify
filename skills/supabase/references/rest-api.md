# REST API：直接查询/修改表（PostgREST）

> 来自 https://supabase.com/docs/guides/api、`guides/api/quickstart`、`guides/api/creating-routes`、`guides/api/securing-your-api`、`guides/database/joins-and-nesting`、supabase-js 客户端参考（`llms/js.txt`），以及 https://postgrest.org 官方文档（PostgREST 是这套 REST 接口的底层实现，字段级语法以它为准）。抓取于 2026-09-21。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档/规范转录。

## 目录

- [基本概念](#基本概念)
- [鉴权 header](#鉴权-header)
- [select：选列与关联查询（join）](#select选列与关联查询join)
- [filter：query string 语法](#filter query-string-语法)
- [排序、分页、计数](#排序分页计数)
- [insert / update / delete](#insert--update--delete)
- [upsert：靠 Prefer 头，不是单独的 HTTP 方法](#upsert靠-prefer-头不是单独的-http-方法)
- [调用 Postgres 函数（RPC）](#调用-postgres-函数rpc)
- [客户端库 vs 原始 HTTP](#客户端库-vs-原始-http)

## 基本概念

Supabase 在项目的 Postgres 数据库上自动生成一层 REST 接口，用的是开源的 **PostgREST**。这意味着：

- 你**不写任何后端代码**——建一张表，它立刻对应一个 REST 路由；建一个视图、一个 Postgres 函数，同样自动出现在 API 里。
- Base URL 固定为 `https://<project_ref>.supabase.co/rest/v1/`，表名/视图名直接接在后面：`GET /rest/v1/todos`。
- 每个请求最终被 PostgREST 编译成**一条 SQL 语句**执行，这决定了它的能力边界和语法风格都更贴近 SQL，而不是常见的"资源+动作"REST 设计。
- 一个表/视图/函数能不能被这层 API 看到，取决于它所在的 schema 是否在 Dashboard 的 **Integrations > Data API > Exposed schemas** 里；默认只暴露 `public`。`⚠ 文档原文，未实测`。

## 鉴权 header

每个请求需要两个 header，职责不同：

| Header | 装什么 | 缺了会怎样 |
| --- | --- | --- |
| `apikey` | 项目级 key：`anon`/`sb_publishable_...`（客户端场景）或 `service_role`/`sb_secret_...`（服务端场景） | 必填，缺了整个 API gateway 层直接拒绝，不进 PostgREST |
| `Authorization: Bearer <token>` | 用户已登录时放该用户的**会话 access token**；未登录时官方示例里常直接重复放同一把 `apikey` 的值 | 决定这次请求在 Postgres 里跑成 `anon`、`authenticated` 还是 `service_role` 角色，从而决定 RLS 按谁的策略算 |

```bash
# 未登录 / 公开数据
curl '<SUPABASE_URL>/rest/v1/todos' \
  -H "apikey: <SUPABASE_PUBLISHABLE_KEY>" \
  -H "Authorization: Bearer <SUPABASE_PUBLISHABLE_KEY>"

# 已登录用户（RLS 里 auth.uid() 才能拿到值）
curl '<SUPABASE_URL>/rest/v1/todos' \
  -H "apikey: <SUPABASE_PUBLISHABLE_KEY>" \
  -H "Authorization: Bearer <用户登录后拿到的 access_token>"
```

新版 `sb_publishable_.../sb_secret_...` key **不是 JWT**，只能放 `apikey`；放到 `Authorization: Bearer` 会被当作 JWT 解析而失败（迁移期为兼容也接受，但不代表通过了鉴权）。见 `references/auth-and-rls.md`。`⚠ 文档原文，未实测`。

## select：选列与关联查询（join）

`select` 是唯一同时控制"要哪些列"和"要不要带出关联表"的 query 参数。

**只选部分列**

```
GET /rest/v1/todos?select=id,task,created_at
```

不传 `select` 时默认等价于 `select=*`。

**JSON/JSONB 字段取子路径**：`->`（返回 JSON）、`->>`（返回文本）

```
GET /rest/v1/users?select=id,address->>city
```

**改名**：`别名:原列名`

```
GET /rest/v1/messages?select=id,body,sentAt:created_at
```

**关联查询（embedding）**：把外键指向的表名当成一个"嵌套列"直接写进 `select`，PostgREST 会自动发现外键关系并拼成一次 SQL 里的 join，返回结果里这张表以嵌套数组/对象的形式出现：

```
GET /rest/v1/orchestral_sections?select=name,instruments(name)
```

对应的客户端写法（JS）：

```js
const { data, error } = await supabase
  .from('orchestral_sections')
  .select(`
    name,
    instruments (
      name
    )
  `)
```

- **默认是 left join**：主表的每一行都会出现，关联表没有匹配行时该字段是空数组/`null`，不会因为关联表没数据就丢主表的行。
- **同一张表被两个外键各引用一次时要显式消歧**（否则 PostgREST 不知道走哪个外键），语法是 `别名:外表!外键约束名(列...)`：

  ```
  GET /rest/v1/messages?select=content,from:sender_id(name),to:receiver_id(name)
  ```

- **`!inner` 把 left join 改成 inner join**，同时才能对关联表的字段做"顶层过滤"（即只返回关联表里有匹配行的主表行，而不是主表全返回、关联字段是空数组）：

  ```
  GET /rest/v1/instruments?select=name,orchestral_sections!inner(name)&orchestral_sections.name=eq.percussion
  ```

  不加 `!inner` 时同样的 `orchestral_sections.name=eq.percussion` 只过滤"嵌套数组里的元素"，主表本身的行数不受影响——这是任务描述里点名的一个非直观行为：**过滤条件加没加 `!inner` 决定的是"哪些主表行出现"还是"主表行里嵌套数组的内容"，两种语义都合法，选错一个就会让 Agent 以为"关联过滤没生效"**。
- 关联表上可以单独 `.order()`、`.limit()`，语法是前缀关联表名：`?select=*,actors(*)&actors.order=last_name`。

以上语法均来自 postgrest.org 官方文档与 Supabase `joins-and-nesting` 指南。`⚠ 文档原文，未实测`。

## filter：query string 语法

**这是和"发一个 JSON filter 请求体"的直觉差异最大的地方**：PostgREST 的过滤条件全部编码在 URL query string 里，格式固定为 `列名=操作符.值`，多个条件之间默认是 **AND**（用 `&` 连接）。

| 操作符 | 含义 | 示例 |
| --- | --- | --- |
| `eq` | `=` | `?status=eq.active` |
| `neq` | `<>` | `?status=neq.archived` |
| `gt` / `gte` | `>` / `>=` | `?age=gte.18` |
| `lt` / `lte` | `<` / `<=` | `?score=lt.100` |
| `like` / `ilike` | `LIKE` / `ILIKE`，通配符用 `*` 代替 `%` | `?name=ilike.*john*` |
| `match` / `imatch` | 正则匹配（区分/不区分大小写） | `?email=match.^[a-z]+@` |
| `in` | `IN`，值列表用 `()` 包裹 | `?id=in.(1,2,3)` |
| `is` | `IS`，专用于 null/true/false | `?deleted_at=is.null` |
| `cs` | 包含（`@>`，用于数组/JSON） | `?tags=cs.{a,b}` |
| `cd` | 被包含于（`<@`） | `?tags=cd.{a,b,c}` |
| `ov` | 有交集（数组/range） | `?period=ov.[2026-01-01,2026-06-30]` |
| `fts` / `plfts` / `phfts` / `wfts` | 全文检索（`to_tsquery`/`plainto_tsquery`/`phraseto_tsquery`/`websearch_to_tsquery`） | `?content=fts(english).cat` |

**NOT**：给操作符加 `not.` 前缀 —— `?status=not.eq.archived`。

**OR**：单独的 `or` 参数，值是逗号分隔的 `列.操作符.值` 列表，外面套括号 —— `?or=(age.lt.18,age.gt.65)`。`or` 可以和 `and(...)` 嵌套组合。

**注意 `is` 和 `eq` 不能互换**：判断 `NULL` 必须用 `is`，`?column=eq.null` 不会按预期工作（PostgREST/postgrest.org 文档明确区分这两者）。`⚠ 文档原文，未实测`。

**对应的客户端方法名基本是操作符的全称或驼峰变体**（`.eq()`、`.neq()`、`.gt()`、`.gte()`、`.lt()`、`.lte()`、`.like()`、`.ilike()`、`.in()`、`.is()`、`.contains()`=`cs`、`.containedBy()`=`cd`、`.overlaps()`=`ov`、`.textSearch()`=fts 系列），逃生舱是 `.filter(column, operator, value)`——这个方法直接透传 PostgREST 原始语法，`in`/`cs` 这类需要手写括号/花括号：

```js
.filter('id', 'in', '(5,6,7)')
.filter('tags', 'cs', '{a,b}')
```

链式调用里**过滤方法必须在 `.select()` 之后**，顺序反了会报错（`.eq().select()` 不行，`.select().eq()` 才对）。`⚠ 文档原文，未实测`。

## 排序、分页、计数

- **排序**：`?order=score.desc`，多列 `?order=score.desc,created_at.asc`。
- **分页两种等价写法**：
  - Query 参数：`?limit=20&offset=40`
  - `Range` 请求头（PostgREST 原生方式）：`Range: 40-59`（0-based，闭区间）
  - 响应总带 `Content-Range` 头说明实际返回范围，不传精确计数时总数部分是 `*`（未知）。
- **要精确/估算总数**，加 `Prefer` 头：
  - `Prefer: count=exact` —— 精确总数，大表上可能慢
  - `Prefer: count=planned` —— 用 Postgres 统计信息估算，快但可能不准
  - `Prefer: count=estimated` —— 数据量小于某阈值时精确、超过阈值时退化成 planned

  对应客户端：`.select('*', { count: 'exact', head: true })`。

以上分页语法来自 postgrest.org 官方文档。`⚠ 文档原文，未实测`。

## insert / update / delete

- `POST /rest/v1/{table}`，body 是 JSON 对象（单条）或 JSON 数组（批量）。
- `PATCH /rest/v1/{table}?id=eq.5`，用 query string 过滤条件圈定"改哪些行"，body 只放要改的字段。
- `DELETE /rest/v1/{table}?id=eq.5`，同样靠 query string 过滤条件圈定范围——**没有过滤条件的 `DELETE` 会删掉整张表能被该角色看到的所有行**，这是任务里点名的"直觉差异"之一：不是"删除需要额外确认"的安全设计，是纯粹按 SQL 语义执行。
- **默认不返回写入/修改后的行**（`Prefer: return=minimal` 是默认值），要拿到结果需要显式要求：
  - `Prefer: return=representation` —— 返回完整的受影响行
  - `Prefer: return=headers-only` —— 只在 `Location` 响应头给出新建资源的定位（需要表有主键）
  - 对应客户端写法：在 `.insert()/.update()/.delete()` 后再链一个 `.select()`。
- `update()`/`delete()` 在开启 RLS 的表上，实际生效范围是"该角色的 `UPDATE`/`DELETE` 策略 `using` 子句筛出的行"和"query string 过滤条件"的交集；对 `UPDATE` 来说还需要一条对应的 `SELECT` 策略存在，否则更新即使被允许也拿不到返回行。见 `references/auth-and-rls.md`。

`⚠ 文档原文，未实测`。

## upsert：靠 Prefer 头，不是单独的 HTTP 方法

Upsert 复用 `POST`，靠 `Prefer` 头里的 `resolution` 值告诉 PostgREST 冲突时怎么处理——**这是任务里点名的另一个非直觉点**：没有专门的 `UPSERT` HTTP 方法或独立 `PUT /upsert` 路径。

```bash
curl -X POST '<SUPABASE_URL>/rest/v1/users?on_conflict=username' \
  -H "apikey: <KEY>" -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -H "Prefer: resolution=merge-duplicates,return=representation" \
  -d '{"username": "supabot", "message": "bar"}'
```

- `Prefer: resolution=merge-duplicates` —— 冲突时用新值覆盖已有行（等价于 SQL 的 `ON CONFLICT DO UPDATE`）
- `Prefer: resolution=ignore-duplicates` —— 冲突时保留原行不动（等价于 `ON CONFLICT DO NOTHING`）
- **默认按主键判断冲突**，所以 body 必须带全部主键列；要按某个 `UNIQUE` 列（而不是主键）判断冲突，用 `?on_conflict=列名` 指定。
- 也可以用单行的 `PUT /rest/v1/{table}?id=eq.4` 做 upsert，但 body 必须包含**全部列**（包括主键），不是部分字段更新。
- 多个 `Prefer` 值用逗号连接，例如同时要 upsert 语义和拿回结果：`Prefer: resolution=merge-duplicates,return=representation`。

客户端封装：

```js
const { data, error } = await supabase
  .from('users')
  .upsert({ username: 'supabot', message: 'bar' }, { onConflict: 'username' })
  .select()
```

改过表结构（尤其是主键）之后，PostgREST 的 schema 缓存可能没刷新导致 upsert 表现异常，官方建议改表结构后 `notify pgrst, 'reload config'` 或等自动重载。`⚠ 文档原文，未实测`。

## 调用 Postgres 函数（RPC）

任何标了 `EXECUTE` 权限给对应角色的 Postgres 函数都能通过 `POST /rest/v1/rpc/{function_name}` 调用，body 是参数的 JSON 对象；**只读**（`STABLE`/`IMMUTABLE`）函数也可以用 `GET /rest/v1/rpc/{function_name}?参数=值` 调用。

```js
const { data, error } = await supabase.rpc('echo', { say: 'hi' })
```

函数返回值是 `TABLE`/`SETOF` 类型时，返回结果同样可以像查表一样再叠加 `.select()`/`.eq()` 等过滤。函数必须在暴露的 schema 里，且 `SECURITY DEFINER` 函数要格外小心——它会以创建者权限运行，若创建者有 `BYPASSRLS`，相当于给调用方开了后门（细节见 `references/auth-and-rls.md`）。`⚠ 文档原文，未实测`。

## 客户端库 vs 原始 HTTP

官方客户端库（`@supabase/supabase-js`、Python 的 `supabase` 包等）本质是把上面这套 query string / header 语法包装成链式方法，行为应该一致，但当官方 SDK 没覆盖到的能力（比如某些 `Prefer` 组合、罕见操作符）时可以退回 `.filter()`/直接发 HTTP 请求。写代码时优先用客户端库；需要精确控制 header（比如手写 `Prefer`）或调试"客户端库好像没按预期发请求"时，对照这份文件里的原始语法直接用 `curl`/`requests` 验证。
