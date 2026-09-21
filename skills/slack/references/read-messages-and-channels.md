# 读取消息与频道

> ⚠ 本文件全篇未经真实 API 调用验证，所有行为断言标注为"文档原文，未实测"。

- [频道类型：public / private / im / mpim](#channel-types)
- [conversations.list：列出频道](#conversations-list)
- [conversations.history：读频道历史](#conversations-history)
- [conversations.replies：读一个线程](#conversations-replies)
- [conversations.info / conversations.members](#info-members)
- [加入频道（conversations.join）](#join)
- [翻页（cursor pagination）](#pagination)

## 频道类型：public / private / im / mpim {#channel-types}

⚠ 文档原文，未实测。Slack 把"所有能收发消息的地方"统一抽象成 **conversation**，`conversations.*` 系列方法通吃这四种类型：

| 类型 | ID 前缀 | 说明 | 对应 scope（读历史） |
|---|---|---|---|
| public channel | `C` | 公开频道，workspace 内任何人可加入/可见 | `channels:history` |
| private channel | `G`（Slack Connect 共享后前缀可能变成 `C`，见下） | 私有频道，仅成员可见 | `groups:history` |
| im | `D` | 1:1 私信 | `im:history` |
| mpim | `G` | 多人私信（group DM） | `mpim:history` |

`conversations.list` 的 `types` 参数接受这四个值的逗号分隔组合（`public_channel`、`private_channel`、`im`、`mpim`），**默认只返回 `public_channel`**——如果不显式传 `types`，私有频道和 DM 不会出现在结果里，这是常见的"为什么我的私有频道列不出来"疑惑点。

**频道 ID 不总是稳定的**：频道在 Slack Connect 场景下被跨组织共享时，private 频道的 ID 前缀可能从 `G` 变成 `C`。不要把 ID 硬编码当作永久不变的值，需要用某个 well-known 频道时用 `conversations.list` 按名字查一遍。

**判断类型**：读取到的 conversation 对象里有布尔字段 `is_channel`/`is_group`/`is_im`/`is_mpim`/`is_private`/`is_shared`，比"看 ID 前缀猜类型"更可靠。

## conversations.list：列出频道 {#conversations-list}

**Endpoint**: `GET https://slack.com/api/conversations.list`
**Scope**: bot/user `channels:read` / `groups:read` / `im:read` / `mpim:read`（对应你想列出的类型）
**Rate limit**: Tier 2（约 20+ 次/分钟）

**关键参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `types` | string | 否 | `public_channel` | 逗号分隔，见上表 |
| `exclude_archived` | boolean | 否 | `false` | 排除已归档频道 |
| `limit` | number | 否 | `100` | 单页大小，上限 1000（建议 ≤200） |
| `cursor` | string | 否 | — | 翻页游标 |

**示例请求**

```bash
curl -G https://slack.com/api/conversations.list \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  --data-urlencode "types=public_channel,private_channel" \
  --data-urlencode "limit=200"
```

```python
resp = client.conversations_list(types="public_channel,private_channel", limit=200)
for ch in resp["channels"]:
    print(ch["id"], ch["name"], ch["is_private"])
```

**注意事项**

- 返回的是**精简版** conversation 对象，要拿完整信息（如 topic 历史、完整成员数）用 `conversations.info` 按 ID 查单个。
- 混合查询 `im`/`mpim` 时**返回条数可能明显少于 `limit`**，即使还有更多结果——这是文档明确说的"特性不是 bug"，务必用 `next_cursor` 判断是否还有下一页，而不是用"返回条数 < limit"来判断已到最后一页。
- `not_in_channel` 不适用于本方法——`conversations.list` 本身不要求 bot 是频道成员，只要有对应的 `*:read` scope 就能列出（能不能进一步读历史是另一回事，见下）。

## conversations.history：读频道历史 {#conversations-history}

**Endpoint**: `GET https://slack.com/api/conversations.history`
**Scope**: bot/user `channels:history` / `groups:history` / `im:history` / `mpim:history`（按频道类型）
**Rate limit**: Tier 3（内部自用 app / 已上架 Marketplace 的 app）；**⚠ 对 2025-05-29 之后创建、且未上架 Marketplace 的商业分发 app，被降到 Tier 1：每分钟 1 次、`limit` 上限和默认值都降到 15 条**（详见 [errors-and-limits.md](errors-and-limits.md)）。⚠ 文档原文，未实测

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `channel` | string | 是 | 频道 ID |
| `limit` | number | 否 | 默认 100，上限 999（受上面提到的 Tier 限制影响） |
| `oldest` / `latest` | string | 否 | Unix 时间戳，限定时间范围；默认 `latest` 是当前时间 |
| `inclusive` | boolean | 否 | 是否把 `oldest`/`latest` 本身对应的消息也包含进结果 |
| `cursor` | string | 否 | 翻页游标 |

**示例请求**

```bash
curl -G https://slack.com/api/conversations.history \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  --data-urlencode "channel=C0123456789" \
  --data-urlencode "limit=50"
```

```python
resp = client.conversations_history(channel="C0123456789", limit=50)
for msg in resp["messages"]:
    print(msg.get("user"), msg.get("text"), msg["ts"])
```

**注意事项**

- **`not_in_channel`**：bot token 必须是该频道成员才能读历史（这是最常见的报错原因）；**user token 例外**——user token 可以读它本人能看到的、哪怕自己（作为 bot 代表的那个人）不在的 public 频道历史。
- 消息数组按时间**倒序**（最新的在前）。`type` 字段区分真实消息（`"message"`）和频道事件（成员加入/改名等），只有 `type: "message"` 才是"人写的内容"。
- 找某一条特定消息：`oldest=<ts>` + `inclusive=true` + `limit=1` 是文档推荐的精确定位手法。
- 读线程内的回复**不能**用本方法（只会拿到父消息本身），要用 `conversations.replies`。
- 读 DM 历史同样走本方法（传 DM 的 `D...` ID），需要额外的 bot 相关 legacy scope，见方法文档。

## conversations.replies：读一个线程 {#conversations-replies}

⚠ 文档原文，未实测。**Endpoint**: `GET https://slack.com/api/conversations.replies`。参数结构和 `conversations.history` 基本一致，多一个必填的 `ts`（线程父消息的 `ts`）。同样受 2025-05-29 那条 Tier 1 限流新规影响（非 Marketplace 商业分发 app）。返回结果里第一条是父消息本身，后面依次是线程回复。

## conversations.info / conversations.members {#info-members}

⚠ 文档原文，未实测。

- **`conversations.info`**：按频道 ID 查完整的 conversation 对象（topic/purpose/成员数/各种布尔标志位），`conversations.list` 只给精简版，需要完整信息时补查这个。
- **`conversations.members`**：分页列出某频道的所有成员 ID，用于"这个人在不在频道里"之类的判断。

## 加入频道（conversations.join） {#join}

⚠ 文档原文，未实测。**Endpoint**: `POST https://slack.com/api/conversations.join`，scope 需要 `channels:join`。Bot 只能**主动加入 public 频道**（这个方法不能用来加入 private 频道——private 频道必须被现有成员邀请）。想让 agent"先确保自己在频道里再发消息/读历史"，可以先尝试 `conversations.join`（对已加入的频道调用是幂等的，不会报错），失败再走邀请流程。

## 翻页（cursor pagination） {#pagination}

⚠ 文档原文，未实测。`conversations.*` 系列统一用游标分页：

1. 第一次请求设置合理的 `limit`（建议 ≤200，即使方法允许更大）。
2. 响应里有 `response_metadata.next_cursor`；非空就说明还有下一页。
3. 下一次请求把这个值原样传给 `cursor` 参数。
4. **不带 `cursor`/`limit`（走"无分页"的老式调用方式）会触发更严格的限流**——一次性想拉全量数据（如整个 `users.list`）务必显式分页，不要图省事不传 `limit`。
