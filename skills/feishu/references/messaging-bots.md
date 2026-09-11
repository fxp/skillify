# 消息与机器人（应用机器人 + 自定义群机器人 webhook）

来源：`open.feishu.cn/document/server-docs/im-v1/*`、`client-docs/bot-v3/*`、`server-docs/group/chat/*`（抓取于 2026-09-11）。
Base URL `https://open.feishu.cn/open-apis`。**报错码与行为描述除标注「无凭证探测」外均为文档原文，未实测。**

## 目录

1. [先选对机器人类型](#1-先选对机器人类型)
2. [发送消息](#2-发送消息)
3. [content 怎么构造（text / post / image / interactive / file）](#3-content-怎么构造)
4. [回复、编辑、更新卡片、撤回、查单条](#4-回复编辑更新卡片撤回查单条)
5. [获取会话历史消息](#5-获取会话历史消息)
6. [上传图片 / 文件](#6-上传图片--文件)
7. [chat_id 从哪来：机器人所在的群列表](#7-chat_id-从哪来)
8. [批量发送消息（给很多人发通知）](#8-批量发送消息)
9. [接收消息事件 im.message.receive_v1](#9-接收消息事件)
10. [自定义群机器人 webhook](#10-自定义群机器人-webhook)
11. [发送消息错误码](#11-发送消息错误码)
12. [容易写错的地方](#12-容易写错的地方)

---

## 1. 先选对机器人类型

| 对比项 | 应用机器人 | 自定义群机器人 |
|---|---|---|
| 怎么来 | 开发者后台建应用 → 开启「机器人」能力 → **发布并经管理员审核** | 群设置 → 群机器人 → 添加「自定义机器人」，无需审核 |
| 怎么发消息 | `POST /open-apis/im/v1/messages` + tenant_access_token | `POST https://open.feishu.cn/open-apis/bot/v2/hook/<hook_id>`，**不用 access token** |
| 能发给谁 | 可用范围内的用户（单聊）、所在的群 | **只能发到它所在的那一个群** |
| 卡片交互回调 / 响应 @ / 读消息 / 建群 / 读通讯录 | ✅ | ❌（卡片只能跳链接） |
| 频控 | 接口频控 + 同一用户 / 同一群 5 QPS | 单租户单机器人 100 次/分钟、5 次/秒 |
| 请求体大小 | 文本 150 KB；卡片、富文本 30 KB | 20 KB |

"往告警群推一条消息"用自定义机器人最省事；要单聊、要接收用户消息、要卡片按钮回调，必须用应用机器人。
**两者请求体格式不同**（见第 10 节），不能混用：发送消息内容结构文档明确"本文不适用于自定义机器人"。

---

## 2. 发送消息

**Endpoint**: `POST /open-apis/im/v1/messages?receive_id_type=<类型>`
**用途**: 应用机器人（或以用户身份）给用户或群发一条消息。频控 1000 次/分钟、50 次/秒；另有**同一用户 5 QPS、同一群（群内机器人共享）5 QPS**。

前提（文档原文）：应用已开启机器人能力并**发布版本**；给用户发时用户在机器人**可用范围**内；给群发时机器人**在群里且有发言权限**。
权限（任一）：`im:message`、`im:message:send_as_bot`、`im:message:send`（历史）。以用户身份发需同时有 `im:message` 和"以用户身份发送消息"权限。

**关键参数**

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|---|
| `receive_id_type` | query | string | **是** | — | `open_id` / `union_id` / `user_id` / `email` / `chat_id`；**没有默认值** |
| `receive_id` | body | string | 是 | — | 与 `receive_id_type` 对应；给用户发推荐 open_id |
| `msg_type` | body | string | 是 | — | `text`、`post`、`image`、`file`、`audio`、`media`、`sticker`、`interactive`、`share_chat`、`share_user`、`system`（仅机器人单聊） |
| `content` | body | **string** | 是 | — | **JSON 序列化后的字符串**，结构随 `msg_type` 变，见第 3 节 |
| `uuid` | body | string | 否 | — | 去重键：相同 uuid 在 **1 小时内最多成功发送一条**；≤50 字符；发不同内容时每次都要换 |

**示例请求**

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d '{"receive_id":"oc_84983ff6516d731e5b5f68d4ea2e1da5","msg_type":"text","content":"{\"text\":\"部署完成\"}"}'
```

```python
import json, uuid, requests

def send_text(receive_id: str, text: str, id_type: str = "open_id") -> str:
    r = requests.post(f"{BASE}/open-apis/im/v1/messages",
                      params={"receive_id_type": id_type},
                      headers={"Authorization": f"Bearer {tenant_access_token()}"},
                      json={"receive_id": receive_id,
                            "msg_type": "text",
                            "content": json.dumps({"text": text}, ensure_ascii=False),   # 注意：字符串，不是对象
                            "uuid": str(uuid.uuid4())},
                      timeout=10)
    body = r.json()
    if body.get("code") != 0:
        raise RuntimeError(f"{body.get('code')} {body.get('msg')} logid={r.headers.get('X-Tt-Logid')}")
    return body["data"]["message_id"]           # om_ 开头
```

SDK 写法（文档场景示例同款）：

```python
from lark_oapi.api.im.v1 import *
req = CreateMessageRequest.builder().receive_id_type("chat_id") \
    .request_body(CreateMessageRequestBody.builder()
                  .receive_id("oc_xxx").msg_type("text")
                  .content(lark.JSON.marshal({"text": "部署完成"}))
                  .build()).build()
resp = client.im.v1.message.create(req)
```

**示例响应**（文档原文，节选）

```json
{"code": 0, "msg": "success", "data": {
  "message_id": "om_dc13264520392913993dd051dba21dcf", "msg_type": "interactive",
  "create_time": "1615380573411", "chat_id": "oc_5ad11d72b830411d72b836c20",
  "sender": {"id": "cli_9f427eec54ae901b", "id_type": "app_id", "sender_type": "app", "tenant_key": "736588c9260f175e"},
  "body": {"content": "..."}}}
```

**注意事项**

- `create_time` / `update_time` 是**毫秒**时间戳字符串。
- `receive_id_type=user_id` 时需要字段权限 `contact:user.employee_id:readonly`。
- 群自定义机器人不能调这个接口。
- 无凭证探测（2026-09-11）：伪造 `Bearer t-...` → HTTP 400 + `code 99991663`。

---

## 3. content 怎么构造

以下 JSON 是 `content` **反序列化后**的样子；实际请求要 `json.dumps` 成字符串再放进 `content`（适用于发送、回复、编辑接口；
不适用于批量发送接口和自定义机器人）。

**text**

```json
{"text": "第一行\n第二行 <at user_id=\"ou_xxx\">Tom</at> <at user_id=\"all\"></at>"}
```

换行用 `\n`（序列化后是 `\\n`）；@ 人用 `<at user_id="open_id 或 user_id"></at>`，@ 所有人 `<at user_id="all"></at>`。
要发 Markdown，文档推荐改用 `post` 里的 `md` 标签（支持 CommonMark 0.31 + GFM）。

**post（富文本）**

```json
{"zh_cn": {"title": "项目更新通知", "content": [
  [{"tag": "text", "text": "第一行:", "style": ["bold"]},
   {"tag": "a", "href": "https://www.feishu.cn", "text": "超链接"},
   {"tag": "at", "user_id": "ou_1avnmsbv3k45jnk34j5"}],
  [{"tag": "img", "image_key": "img_7ea74629-9191-4176-998c-2e603c9c5e8g"}]
]}}
```

- 外层是语言键（`zh_cn` / `en_us`），`content` 是**二维数组**：每个内层数组是一个段落。
- 图片、视频元素必须**单独成段**。
- 可用标签：`text`、`a`、`at`、`img`、`media`、`emotion`、`md` 等（完整列表 ⚠ 以文档「发送消息内容结构」页为准）。

**image**：`{"image_key": "img_v2_xxx"}`——`image_key` 来自上传图片接口（第 6 节）。

**file**：`{"file_key": "file_v2_xxx"}`——来自上传文件接口；机器人**只能发自己上传的文件**（`230017`）。

**interactive（卡片）**，三种写法：

```json
{"type": "card", "data": {"card_id": "7371713483664506900"}}
{"type": "template", "data": {"template_id": "AAqigYkzabcef", "template_version_name": "1.0.0", "template_variable": {"key1": "value1"}}}
{"schema": "2.0", "header": {"title": {"tag": "plain_text", "content": "标题"}}, "body": {"elements": [{"tag": "markdown", "content": "**加粗**"}]}}
```

分别是：卡片实体 ID（流式 / 局部更新场景）、卡片搭建工具的模板（支持变量）、直接写卡片 JSON（不支持变量）。
历史接口 `/open-apis/message/v4/send/` 用 `card` 字段；**`im/v1/messages` 统一用 `content`**。

---

## 4. 回复、编辑、更新卡片、撤回、查单条

| 我想 | Endpoint | 关键点 |
|---|---|---|
| 回复某条消息 | `POST /open-apis/im/v1/messages/:message_id/reply` | body 同发送（`msg_type`、`content`、`uuid`）；`reply_in_thread: true` 以话题形式回复（默认 `false`；原消息已是话题则默认话题回复） |
| 编辑已发消息 | `PUT /open-apis/im/v1/messages/:message_id` | **只支持 text / post**；一条最多编辑 20 次；只能编辑自己发的；超过管理员设定的可编辑时间不行 |
| 更新已发卡片 | `PATCH /open-apis/im/v1/messages/:message_id` | 编辑卡片要用这个，不是 PUT |
| 撤回 | `DELETE /open-apis/im/v1/messages/:message_id` | 机器人只能撤回自己发的；群主可撤回群内指定消息；批量发送的消息要用批量撤回接口 |
| 查单条内容 | `GET /open-apis/im/v1/messages/:message_id` | |

频控均为 1000 次/分钟、50 次/秒。`message_id` 以 `om_` 开头；批量发送得到的是 `bm-` 开头，不能用上面这些接口。

---

## 5. 获取会话历史消息

**Endpoint**: `GET /open-apis/im/v1/messages`
**用途**: 拉取某个群 / 单聊 / 话题里的历史消息。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `container_id_type` | string | 是 | — | `chat`（单聊和群聊）或 `thread`（话题） |
| `container_id` | string | 是 | — | `oc_...` 群 ID 或话题 ID |
| `start_time` / `end_time` | string | 否 | — | **秒级**时间戳（注意：消息响应里的时间是毫秒）；`thread` 不支持时间范围 |
| `sort_type` | string | 否 | `ByCreateTimeAsc` | 或 `ByCreateTimeDesc`；**翻页过程中不能改** |
| `page_size` | int | 否 | `20` | 范围 1–50 |
| `page_token` | string | 否 | — | |

```bash
curl -s "https://open.feishu.cn/open-apis/im/v1/messages?container_id_type=chat&container_id=oc_234jsi43d3ssi993d43545f&start_time=1608594809&sort_type=ByCreateTimeDesc&page_size=50" \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN"
```

注意：普通群里的话题消息用 `chat` 只能拿到话题根消息，回复要用 `container_id_type=thread` 再拉。

---

## 6. 上传图片 / 文件

**Endpoint**: `POST /open-apis/im/v1/images`（`multipart/form-data`）
**用途**: 上传图片拿 `image_key`，用于 image 消息、post 的 img 标签、卡片、头像。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `image_type` | string | 是 | `message`（发消息用）或 `avatar`（设置头像） |
| `image` | file | 是 | ≤10 MB 且不能为 0 字节；GIF ≤2000×2000，其他 ≤12000×12000，头像 ≤4096×4096 |

```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/im/v1/images' \
  -H "Authorization: Bearer $TENANT_ACCESS_TOKEN" \
  -F 'image_type=message' -F 'image=@./chart.png'
```

```python
with open("chart.png", "rb") as f:
    r = requests.post(f"{BASE}/open-apis/im/v1/images",
                      headers={"Authorization": f"Bearer {tenant_access_token()}"},   # 不要手动设 Content-Type
                      data={"image_type": "message"}, files={"image": f}, timeout=30)
image_key = r.json()["data"]["image_key"]
```

**上传文件**：`POST /open-apis/im/v1/files`（multipart），返回 `file_key`。字段细节 ⚠ 本 skill 未展开，以文档页为准；
文档提醒上传时选的文件类型要和发送的 `msg_type` 匹配（例如 MP4 要用 `media`，否则 `230055`）。

---

## 7. chat_id 从哪来

**Endpoint**: `GET /open-apis/im/v1/chats`
**用途**: 列出 access_token 代表的用户或机器人**所在的群**（不含单聊）。要机器人能力。频控 1000 次/分钟、50 次/秒。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `user_id_type` | string | 否 | `open_id` | 影响 `owner_id` |
| `sort_type` | string | 否 | — | `ByCreateTimeAsc` 或 `ByActiveTimeDesc`（后者翻页时可能**漏群**，文档原文） |
| `page_size` | int | 否 | `20` | 最大 100 |
| `page_token` | string | 否 | — | |

响应 `data.items[]`：`chat_id`（`oc_` 开头）、`name`、`owner_id`（群主是机器人时为空）、`external`、`tenant_key`、`chat_status`（`normal` / `dissolved` / `dissolved_save`）。
其他拿 chat_id 的方式：收到的消息事件里有 `chat_id`；创建群接口返回；在群设置里查看。

---

## 8. 批量发送消息

**Endpoint**: `POST /open-apis/message/v4/batch_send/`（注意是**旧版路径**，结尾有 `/`）
**用途**: 给多个用户或多个部门的成员发同一条通知。

- 只能发给用户，**不能发群**；指定的用户 / 部门须在机器人可用范围内。
- 得到的消息 ID 以 `bm-` 开头，不支持编辑、回复，只能批量撤回、查推送与阅读人数、查整体进度。
- 单个应用每天最多 50 万条；**异步**，有延迟，按顺序处理。
- `content` 结构与第 3 节**不同**（第 3 节明确不适用于本接口），请求体字段 ⚠ 本 skill 未展开，以文档页为准。
- 只给一个人 / 一个群发、或不能有延迟，用第 2 节接口。

---

## 9. 接收消息事件

**事件类型**: `im.message.receive_v1`（v2.0 结构）。订阅与验签见 [events-callbacks.md](events-callbacks.md)。

权限决定能收到哪些消息（文档原文）：

| 想收 | 需要的权限 |
|---|---|
| 用户发给机器人的单聊 | `im:message.p2p_msg` 或 `im:message.p2p_msg:readonly` |
| 群里 @ 机器人（仅用户） | `im:message.group_at_msg` 或 `im:message.group_at_msg:readonly` |
| 群里 @ 机器人（含其他机器人） | `im:message.group_at_msg.include_bot:readonly` |
| 群里所有消息（仅用户） | `im:message.group_msg`（敏感权限） |
| 群里所有消息（含其他机器人） | `im:message.group_msg.include_bot:read` |

事件体（文档原文，节选）：

```json
{"schema": "2.0",
 "header": {"event_id": "5e3702a84e847582be8db7fb73283c02", "event_type": "im.message.receive_v1",
            "create_time": "1608725989000", "token": "rvaYgk...", "app_id": "cli_9f53...", "tenant_key": "2ca1..."},
 "event": {
   "sender": {"sender_id": {"union_id": "on_...", "user_id": "e33ggbyz", "open_id": "ou_..."}, "sender_type": "user"},
   "message": {"message_id": "om_...", "chat_id": "oc_...", "chat_type": "group", "message_type": "text",
               "content": "{\"text\":\"@_user_1 hello\"}",
               "mentions": [{"key": "@_user_1", "id": {"open_id": "ou_..."}, "name": "Tom"}]}}}
```

- `message.content` 同样是 **JSON 字符串**，要再 `json.loads` 一次；@ 在文本里是占位符 `@_user_1`，真实身份在 `mentions`。
- 用 `sender.sender_type` 区分发送者是 `user` 还是机器人，避免机器人回复自己形成死循环。
- **去重用 `message.message_id`，文档明确"不要依赖 event_id"**（与事件总览"v2.0 用 event_id 去重"的通用说法不同，⚠ 文档自相矛盾，本事件按本页处理）。
- 要回复这条消息：`POST /open-apis/im/v1/messages/{message_id}/reply`。

---

## 10. 自定义群机器人 webhook

**Endpoint**: `POST https://open.feishu.cn/open-apis/bot/v2/hook/<hook_id>`
**用途**: 往机器人所在的群推送消息。webhook 地址即凭证，**不要提交到公开仓库**。不需要、也不接受 access token。

**请求体**（`Content-Type: application/json`）——**注意 `content` 是对象，不是字符串**：

```json
{"msg_type": "text", "content": {"text": "新更新提醒 <at user_id=\"ou_xxx\">Tom</at>"}}
```

| msg_type | 请求体 |
|---|---|
| `text` | `{"msg_type":"text","content":{"text":"..."}}` |
| `post` | `{"msg_type":"post","content":{"post":{"zh_cn":{"title":"...","content":[[{"tag":"text","text":"..."}]]}}}}`——比应用机器人多一层 `post` |
| `image` | `{"msg_type":"image","content":{"image_key":"img_..."}}` |
| `share_chat` | `{"msg_type":"share_chat","content":{"share_chat_id":"oc_..."}}`（只能分享所在群） |
| `interactive` | `{"msg_type":"interactive","card":{...卡片 JSON...}}`——**卡片放在 `card` 字段，不是 `content`** |

@ 人只支持 open_id 或 user_id（卡片里不支持 email、union_id）；外部群里只能用 open_id。自定义机器人卡片**不支持回传交互**，只能跳 URL。

### 10.1 安全设置（在群里配置，可叠加）

| 方式 | 效果 | 失败返回（文档原文） |
|---|---|---|
| 自定义关键词（最多 10 个） | 消息的文本类参数值（`text`、`title`）至少含一个关键词；**不检查 `href`** | `{"code":19024,"msg":"Key Words Not Found"}` |
| IP 白名单（最多 10 个，支持 `1.2.3.*` / CIDR） | 只处理白名单 IP 的请求 | `{"code":19022,"msg":"Ip Not Allowed"}` |
| 签名校验 | 请求体带 `timestamp` + `sign` | `{"code":19021,"msg":"sign match fail or timestamp is not within one hour from current time"}` |

### 10.2 签名算法（和常见 HMAC 用法反过来）

把 `timestamp + "\n" + secret` **当作 HMAC 的 key**，对**空字符串**做 HmacSHA256，再 Base64。`timestamp` 是**秒**，与当前时间相差不超过 1 小时。

```python
import base64, hashlib, hmac, os, time, requests

def gen_sign(secret: str) -> tuple[str, str]:
    ts = str(int(time.time()))                                   # 秒，不是毫秒
    string_to_sign = f"{ts}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()  # msg 为空
    return ts, base64.b64encode(digest).decode("utf-8")

def push_alert(text: str):
    ts, sign = gen_sign(os.environ["FEISHU_BOT_SECRET"])
    r = requests.post(os.environ["FEISHU_BOT_WEBHOOK"], json={
        "timestamp": ts, "sign": sign,
        "msg_type": "text", "content": {"text": text},           # 对象，不要 json.dumps
    }, timeout=10)
    body = r.json()
    if body.get("code", body.get("StatusCode")) != 0:            # 失败时 HTTP 仍可能是 200
        raise RuntimeError(body)
```

```bash
curl -s -X POST "$FEISHU_BOT_WEBHOOK" -H 'Content-Type: application/json' \
  -d '{"msg_type":"text","content":{"text":"request example"}}'
```

### 10.3 响应与限制

- 成功（文档原文）：`{"StatusCode":0,"StatusMessage":"success","code":0,"data":{},"msg":"success"}`；`StatusCode`/`StatusMessage` 是兼容字段，文档建议用 `code`。
- 请求体格式错误：`{"code":9499,"msg":"Bad Request","data":{}}`。
- 无凭证探测（2026-09-11）：全零伪造 hook ID → **HTTP 200** + `{"code":19001,"data":{},"msg":"param invalid: incoming webhook access token invalid"}`。
  19001 在自定义机器人指南里 ⚠ 文档未说明。
- 请求体 ≤20 KB；频控单租户单机器人 100 次/分钟、5 次/秒；**避开 10:00、17:30 这类整点半点**，否则可能遇到系统压力导致的 `11232` 限流。
- 服务器时间偏差大会导致签名"过期"，检查 NTP。

---

## 11. 发送消息错误码

发送消息接口专有错误码（HTTP 400，文档原文，未实测）：

| code | 含义 / 处理 |
|---|---|
| 230001 | 参数错误，看返回的具体信息 |
| 230002 | 机器人不在该群 |
| 230006 | 应用未启用机器人能力（开启后要发版） |
| 230013 | 目标用户不在机器人可用范围内 |
| 230017 | 机器人不是资源拥有者（只能发自己上传的文件） |
| 230018 | 群设置禁止（如仅指定成员可发言） |
| 230020 | 触发频率限制 |
| 230022 / 230028 | 内容含敏感信息 / 未过数据防泄漏审查（明文手机号、邮箱可能触发） |
| 230025 | 消息体超长（文本 150 KB，卡片 / 富文本 30 KB） |
| 230027 | 缺少权限 |
| 230029 | 用户已离职 |
| 230034 | `receive_id` 与 `receive_id_type` 不匹配或无效 |
| 230035 | 无发送权限（禁言、被屏蔽、租户沟通管控） |
| 230038 | 跨租户单聊不允许 |
| 230053 | 用户设置了不再接收机器人消息 |
| 230099 | 创建卡片内容失败，看子错误码 |
| 232009 | 群已解散 |

通用错误码表里与消息相关的还有 `11232`/`11233`/`11247`（创建消息触发限流）、`19036`（消息超过 30 KB）等，见 [errors-and-limits.md](errors-and-limits.md)。

---

## 12. 容易写错的地方

1. **`content` 在应用机器人接口里是字符串，在自定义机器人 webhook 里是对象**，卡片在 webhook 里还要改放 `card` 字段。套错格式分别报 230001 / 9499 类错误。
2. **`receive_id_type` 必填且没有默认值**，放在 query 里，不是 body 里。
3. 自定义机器人签名：key 是 `timestamp\nsecret`、消息为空、时间戳单位秒——照"HMAC(secret, message)"的习惯写必然 19021。
4. 自定义机器人失败时 HTTP 200，要判 body 的 `code`。
5. 消息响应时间是毫秒，历史消息查询参数 `start_time`/`end_time` 是秒。
6. 编辑只支持 text/post（PUT），卡片更新用 PATCH；批量发送的 `bm-` 消息不能编辑回复。
7. 接收消息事件用 `message_id` 去重；`content` 要二次 `json.loads`；过滤 `sender_type != "user"` 防自回复。
8. 开启机器人能力、改权限、改可用范围之后都要**发布版本**，否则 230006 / 230013。
