把这份 skill 装进你的 Agent，让它写 Supabase 接入代码时不再搞混 `anon`/`service_role`（或新命名 `sb_publishable_...`/`sb_secret_...`）两种 key 该用在哪一侧——用错的后果是把整个数据库暴露给所有人，而不是普通的配置错误。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill supabase --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill supabase --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/supabase/supabase.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认的几件事」和「能力域导航」三节；
2. `references/` 下有 6 个 `.md`，其中 `auth-and-rls.md` 讲的是 anon/service_role key 与 Row Level Security 的权限联动；
3. 在 `SKILL.md` 里能搜到「42501」字样，确认的是"anon key 权限不够时，grant 缺失才是真报错（42501），RLS 策略过滤掉的行是悄悄返回 200 + 空结果"这条区分，而不是笼统的权限说明。

## 这份 skill 覆盖什么

Supabase（`supabase.com/docs`）是 Postgres-as-a-backend 平台，围绕一个真实的 Postgres 数据库打包了 Data API（PostgREST 自动生成的 REST 接口）、Auth、Storage、Realtime、Edge Functions（Deno 运行时）。skill 不追求平均覆盖：REST/RLS/Auth 是几乎所有 Agent 生成代码都会用到的核心，写得最细；Storage/Realtime/Edge Functions 覆盖常见任务；GraphQL、Management API、自托管部署完全不覆盖。

重点是两个真实发现的陷阱：**anon key 权限不够时表现是"悄悄成功"而不是报错**——Postgres 对 Data API 请求做两层检查，先查 grant（没有 grant 直接报 `42501 permission denied`，这是真报错），再查 RLS policy（有 grant 但策略把这行过滤掉了，不报错，返回 200 + 空数组，看起来像是"查询执行成功但恰好没数据"）,用 anon key 调用返回空结果时不能默认是"这个表本来就没数据"，要先确认 RLS 策略；**`service_role`/secret key 完全绕过 Row Level Security，不是"权限更大的用户"而是"没有行级限制"**，一旦这个 key 出现在前端 bundle、Git 仓库或日志里，等于任何人都能读写整个数据库的任意一行——写任何 Supabase 代码前要先确认这段代码跑在用户设备/浏览器（只能用 anon/publishable key）还是自己控制的服务端（才能用 service_role/secret key）。此外两套 key 系统（旧 JWT 命名 vs 新短字符串命名）目前同时有效，新 key 必须放 `apikey` header 而不是 `Authorization: Bearer`，否则会被当 JWT 解析而失败。

内容不是文档搬运：skill 把 PostgREST 的 filter 是 URL query string（不是 JSON body，和大多数"请求体传 filter 对象"的 REST API 习惯完全不同）这类容易混淆的边界写清楚，还记录了 Realtime 的 DELETE 事件不受 RLS 限制（只受 publication 是否包含该表限制）这个例外。全篇没有可用的真实项目和 key，字段名/query string 语法/错误码来自 `supabase.com/docs` 与 `postgrest.org` 官方文档原文交叉核对，但没有一条结论经过真实调用验证，标注 ⚠ 文档原文，未实测。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。**实际调用时报错与 skill 不一致，以 API 的真实报错为准**，并去 `supabase.com/docs` 核实最新情况；RLS 策略写错时的具体报错形态、`Prefer` 头组合是否按文档生效是验证计划里的优先项。
