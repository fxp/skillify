# Realtime：订阅表变更、Broadcast、Presence

> 来自 https://supabase.com/docs/guides/realtime/concepts、`guides/realtime/postgres-changes`、`guides/realtime/authorization`、`guides/realtime/subscribing-to-database-changes`、`guides/realtime/error_codes`。抓取于 2026-09-21。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录。

## 目录

- [三种能力](#三种能力)
- [Postgres Changes：订阅表变更](#postgres-changes订阅表变更)
- [启用条件：publication + RLS，两个都要满足](#启用条件publication--rls两个都要满足)
- [DELETE 事件不受 RLS 保护，这是设计如此](#delete-事件不受-rls-保护这是设计如此)
- [Broadcast 与 Presence：私有 Channel 需要单独鉴权](#broadcast-与-presence私有-channel-需要单独鉴权)
- [连接方式与限制](#连接方式与限制)

## 三种能力

Realtime 是一个 WebSocket 服务，围绕 **Channel**（用一个字符串 topic 标识的"房间"）提供三类不同的能力，容易被误当成同一个东西的不同用法，实际上数据来源和鉴权机制都不同：

| 能力 | 数据来源 | 用途 |
| --- | --- | --- |
| **Postgres Changes** | 数据库的逻辑复制流（WAL） | 表被 insert/update/delete 时自动推送，不需要业务代码显式触发 |
| **Broadcast** | 客户端主动发送的任意消息 | 类似普通 pub/sub，业务代码自己决定发什么、什么时候发 |
| **Presence** | 客户端连接状态 | "谁在线/谁在这个房间"，连接断开自动清理 |

## Postgres Changes：订阅表变更

```js
const channel = supabase
  .channel('schema-db-changes')
  .on(
    'postgres_changes',
    { event: '*', schema: 'public', table: 'todos' }, // event: INSERT | UPDATE | DELETE | '*'
    (payload) => console.log(payload)
  )
  .subscribe()
```

- `event` 支持单独监听 `INSERT`/`UPDATE`/`DELETE`，或 `*` 全部。
- 可以用 `filter` 参数按列过滤（语法和 REST filter 的操作符一致，比如 `filter: 'status=eq.done'`），减少不必要的推送。
- 默认 payload 只带 **`new` 记录**（insert/update 后的新值）；要同时拿到 **`old` 记录**（更新前的值、或被删除的那一行），需要在表上开：

  ```sql
  alter table todos replica identity full;
  ```

  不开这个，`UPDATE`/`DELETE` 的 payload 里 `old_record` 缺失或不完整。`⚠ 文档原文，未实测`。

## 启用条件：publication + RLS，两个都要满足

**这是最容易踩的坑：只在客户端订阅、或只在 Dashboard 打开了"Realtime"开关，都不代表这张表真的会推送变更。** 两个条件缺一不可：

1. **表要加进 `supabase_realtime` 这个 Postgres publication**，否则数据库的复制流根本不会产生这张表的变更事件——Realtime 服务收不到，自然也推不出去：

   ```sql
   alter publication supabase_realtime add table todos;
   ```

   （Dashboard 里对应 **Database > Publications** 页面的勾选框，效果相同。）

2. **调用方对该表有 grant，且能通过 RLS `SELECT` 策略读到这一行**——Postgres Changes 只会把"这个角色本来就有权限 select 到的行"的变更推给它，RLS 策略在这里同时控制"能不能查"和"能不能收到变更通知"。

只满足第 2 条、没做第 1 条，客户端订阅会成功建立（不报错）但永远收不到任何 payload——这种"看起来订阅成功、实际收不到消息"的静默失败,排查时优先检查 publication 有没有加这张表。`⚠ 文档原文，未实测`。

## DELETE 事件不受 RLS 保护，这是设计如此

**官方文档明确指出**：RLS policy 不适用于 `DELETE` 语句本身,因为一行数据一旦被删除,Postgres 没有办法再对"这一行原本长什么样、这个角色本来能不能看到它"做判断。结果是——

- **只要一张表加进了 `supabase_realtime` publication,这张表的 delete 事件会推给所有订阅了这张表的客户端,不受这张表的 SELECT policy 限制。**
- 要限制 delete 事件的可见范围，只能通过**不把这张表加进 publication**、或**把删除操作放进一个不同的表/走软删除（`UPDATE ... SET deleted_at = now()`，这样走的是 UPDATE 而非 DELETE，受 RLS 正常约束）**这类结构性手段，policy 本身管不了。
- 这一点在"只关心某个 delete 事件是否该发给自己"的多租户/权限隔离场景下是真实的安全隐患：默认假设"RLS 保护了 select 就同样保护了 delete 通知"是错的。

对应地，**过滤 delete 事件**（用 `filter` 参数）同样要求表开了 `replica identity full`（否则 delete payload 里没有足够字段可供过滤）。`⚠ 文档原文，未实测`。

## Broadcast 与 Presence：私有 Channel 需要单独鉴权

Broadcast/Presence 默认走**公开 channel**（任何持有 anon/publishable key 的客户端都能加入、收发消息），要做访问控制需要显式切到 **private channel**，机制和 Postgres Changes 完全不同——不是给业务表加 policy,而是给一张专门的系统表 `realtime.messages` 加 RLS policy：

```sql
create policy "authenticated can receive broadcast"
on "realtime"."messages"
for select
to authenticated
using (
  exists (
    select 1 from rooms_users
    where user_id = (select auth.uid())
      and room_topic = (select realtime.topic())
      and realtime.messages.extension = 'broadcast'
  )
);
```

客户端要配合声明 `private: true` 才会真正走这套鉴权：

```js
const channel = supabase.channel('room-1', { config: { private: true } })
```

- 不能直接在 `realtime` schema 里建表/建函数（会报 `permission denied for schema realtime`），但**管理 `realtime.messages` 上的 RLS policy 是被允许的**,这是官方给出的唯一合法接入点。
- Dashboard **Realtime Settings** 里有一个"Allow public access"总开关，要强制走 private channel 必须先关掉它,否则即使写了 private policy,公开 channel 依然可用,等于没生效。
- Postgres Changes 既可以挂在公开 channel 也可以挂在私有 channel 上，机制不冲突。
- 访问策略在客户端连接期间被缓存，不是每条消息都重新查一次数据库；JWT 过期后如果没有发送新 token,连接会被断开而不是继续用旧权限。

`⚠ 文档原文，未实测`。

## 连接方式与限制

- 客户端库内部维护 WebSocket 连接（`wss://<project_ref>.supabase.co/realtime/v1/websocket`），一般不需要手写协议帧,除非要做客户端库不支持的语言/平台。
- 未经 Supabase Auth 用户级鉴权升级的公开连接，**最长只能维持 24 小时**，到点断开，需要业务代码处理重连。
- 并发连接数、每个 Channel 的消息速率、数据库连接池大小都受项目的 Compute Add-on 规格限制，规格越小上限越低,具体数字见 `references/errors-and-limits.md`。

`⚠ 文档原文，未实测`。
