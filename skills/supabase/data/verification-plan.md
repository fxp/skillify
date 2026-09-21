# Supabase skill 验证计划

拿到一个可用的 Supabase 项目（免费版即可，Data API/Auth/Storage/Realtime/Edge Functions 免费版都能用到）之后，按下面的优先级逐条实测，测完把对应 reference 文件里的 `⚠ 文档原文，未实测` 改写成"已用真实 API 验证（日期）：……"并附原始响应/报错片段，同时更新 `supabase/SKILL.md` 顶部"⚠ 验证状态"一节。

## 准备工作

- 建一个新的测试项目（**不要用生产项目**，因为验证过程会故意制造 RLS 报错、故意漏 grant、故意用 service_role 做危险操作）。
- 从 Dashboard **Settings > API Keys** 拿到：`anon`/`sb_publishable_...`、`service_role`/`sb_secret_...`、Project URL。三份都要，很多验证项就是对比这两类 key 在同一请求下的不同表现。
- 建 2-3 张测试表（一张公开只读、一张需要登录才能读写、一张模拟"用户只能碰自己的行"），方便后面 RLS 验证复用。
- Key 全程只用环境变量传递给命令，不写进任何文件；验证结束后 `grep -rn` 一遍确认没有把 key 残留进 reference/日志。

## 优先级 1：SKILL.md 开头"先确认的几件事"（错了全盘皆错）

1. **grant 缺失 vs RLS 过滤的两种失败模式**：对同一张表，先不 grant 任何权限给 anon，确认真的报 `42501`；再补上 grant 但故意让 RLS policy 条件不满足，确认真的是 `200` + 空数组而不是报错。这是 SKILL.md 里最核心的一条断言，必须验证。
2. **新旧两套 key 的行为是否真的等价**：用 `anon` 和 `sb_publishable_...` 分别发同一个请求，确认返回结果/角色映射一致；用 `service_role` 和 `sb_secret_...` 分别发同一个请求，确认都能绕过 RLS。
3. **新版 secret key 的浏览器保护**：带一个典型浏览器 `User-Agent` header 用 `sb_secret_...` 发请求，确认是否真的返回 401；同样的请求把 `User-Agent` 换成非浏览器值，确认能正常工作。
4. **新版 key 放 `Authorization: Bearer` 是否真的失败**：`apikey` 放 publishable key 正常，`Authorization: Bearer` 也放 publishable key（而不是 JWT），确认返回什么错误、错误信息是否如文档所说。
5. **已登录用户请求的两个 header 是否需要不同的值**：`apikey` 固定用 anon/publishable key，`Authorization: Bearer` 换成登录后拿到的 access_token，确认 RLS 按 `authenticated` + 正确的 `auth.uid()` 生效（比如查询一张 `using (auth.uid() = user_id)` 的表，确认能读到属于自己的行、读不到别人的行）。

## 优先级 2：REST API / PostgREST（`references/rest-api.md`）

1. filter 操作符逐个测一遍最常用的几个：`eq`、`gte`/`lte`、`like`/`ilike`、`in`、`is.null`，确认 URL 编码方式和返回结果符合预期。
2. `select` 的关联查询（join）：建一对有外键关系的表，测左连接默认行为（主表全返回、关联字段为空数组）和 `!inner`（只返回有匹配关联行的主表行）两种情况的实际返回结构差异。
3. 同一张表被两个外键指向时的消歧语法（`别名:外表!约束名(...)`），确认不加消歧会报 `PGRST201` 歧义错误。
4. upsert：`Prefer: resolution=merge-duplicates` + `on_conflict=<唯一列>`，先插入一行,再用同样的唯一值 upsert 一次改字段,确认改的是同一行而不是插入新行；同样测 `ignore-duplicates` 确认原行真的没被覆盖。
5. 分页与计数：`Range` header 和 `?limit&offset` 两种写法是否返回一致结果；`Prefer: count=exact` 的 `Content-Range` 响应头格式是否如文档描述。
6. `DELETE` 不带过滤条件时的真实行为（在测试表上小心验证,不要在有真实数据的表上做）。
7. RPC 调用一个自建的简单 Postgres 函数，测 `GET`（只读函数）和 `POST`（一般函数）两种方式。

## 优先级 3：Auth 与 RLS（`references/auth-and-rls.md`）

1. 邮箱密码注册 + 登录全流程，原始 HTTP（`POST /auth/v1/token?grant_type=password`）跑一遍，确认返回的 JWT 结构和文档描述的 claim 列表一致（`sub`/`role`/`aal`/`app_metadata`/`is_anonymous` 等）。
2. `auth.uid()` 在未登录请求（纯 anon key，无用户 JWT）里是否真的返回 `null`，进而验证 `using (auth.uid() = user_id)` 这类策略对未登录请求是否安全拒绝。
3. `UPDATE` policy 缺少对应 `SELECT` policy 时的实际行为（文档只说"不会正常工作"，没说具体报什么错还是静默返回什么）。
4. `SECURITY DEFINER` 函数打破策略递归引用（`42P17`）的完整复现：先故意写两张表互相 exists 引用触发递归错误，确认报错信息，再用 `security definer` 函数改写后确认恢复正常。
5. `service_role`/secret key **携带用户 session** 时是否真的按该用户 RLS 走（而不是自动绕过）——这是文档里一条重要但容易被忽略的细节，必须验证：用 service_role 初始化客户端，手动设置一个普通用户的 JWT，确认这次查询受不受 RLS 限制。
6. `app_metadata` 改动后，已签发的旧 JWT 是否真的不会立刻反映新值（需要等 token 刷新）。

## 优先级 4：Storage（`references/storage.md`）

1. Public bucket 的公开 URL 和 private bucket 的签名 URL/`authenticated` 路径 GET，两种访问方式各测一次。
2. `x-upsert: true` header 覆盖已有文件路径，确认默认行为（不带这个 header）真的返回 `400 Asset Already Exists`。
3. 覆盖上传（`upsert`）在只给 `INSERT` policy、没给 `SELECT`+`UPDATE` policy 时是否真的失败，验证文档"需要额外权限"的说法。
4. `storage.objects` 上写一条"用户只能碰自己文件夹"的 policy（用 `storage.foldername(name)` + `auth.uid()`），验证跨用户上传/读取会被拒绝。
5. 签名 URL 在轮换 JWT 签名密钥/停用旧版 key 后是否真的不受影响（这条验证成本较高，可以先跳过，标注"未验证，文档声称独立于 Auth 密钥体系"）。

## 优先级 5：Realtime（`references/realtime.md`）

1. **publication + RLS 双重条件**：只做 RLS 不加 publication，确认订阅"成功"但收不到任何消息；补上 `alter publication supabase_realtime add table ...` 后确认开始收到消息。这是本 skill 点名的核心陷阱，必须验证。
2. **DELETE 事件不受 RLS 保护**：给一张表配置"只有 owner 能 select"的策略并加入 publication，用一个非 owner 的客户端订阅 delete 事件，确认 owner 删除该行时非 owner 客户端是否真的能收到 delete payload（如果文档准确，应该能收到，尽管这个非 owner 客户端本来 select 不到这行数据）。
3. `replica identity full` 对 `old_record` 是否出现的影响，分别在开/不开的情况下测 UPDATE 和 DELETE 的 payload。
4. Private channel（`realtime.messages` 上的 policy + `private: true`）的 Broadcast 收发权限验证，包括故意不满足 policy 条件时是否真的连不上或收不到。
5. 公开连接 24 小时强制断开的说法验证成本高（要等 24 小时或找到缩短窗口的测试方式），可以先跳过或查是否有测试环境的加速配置。

## 优先级 6：Edge Functions（`references/edge-functions.md`）

1. 一个最小函数走完 `supabase functions new` → `serve` 本地 → `deploy` → 真实 HTTP 调用的全流程。
2. `npm:` 说明符导入一个普通 npm 包（成功）和尝试导入 `sharp`（预期失败），对比错误信息，确认"原生编译包不支持"的说法和实际报错内容。
3. `auth: 'user'` / `auth: 'secret'` / `auth: 'none'` 三种模式各测一次，确认 `ctx.supabase`/`ctx.supabaseAdmin`/`ctx.userClaims` 的实际内容符合预期。
4. `verify_jwt = false` + 新版 secret key 放 `apikey`（不放 `Authorization`）的组合是否能正常工作，对比不设 `verify_jwt = false` 时是否报 `Invalid JWT`。
5. 环境变量注入：确认 `SUPABASE_SECRET_KEYS` 等新变量的 JSON 结构和文档描述一致。
6. 限制类数字（内存 256MB、CPU 2s）验证成本高，可以只验证超限后报什么错误码（`WORKER_LIMIT`），不需要精确测出边界值。

## 完成验证后

- 把每条实测结果写回对应 reference 文件，格式固定为："已用真实 API 验证（YYYY-MM-DD）：……" + 原始响应/报错片段。
- 重新审视 SKILL.md 的"跨领域通用规则"，把验证中发现的、文档没写清楚但实测才暴露的陷阱补充进去（尤其关注静默失效类行为）。
- 跑第 4 步（with/without skill 对照实验，spawn 子 Agent 版本），产出 `comparison-report.md`（Markdown，按仓库约定不做 HTML）。
- 全仓库 `grep` 一遍确认没有真实 key 泄漏进任何文件；测试项目里创建的表/bucket/函数用完清理，避免残留计费资源。
