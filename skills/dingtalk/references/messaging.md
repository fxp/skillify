# 消息：工作通知 / 机器人 / 互动卡片

来源：open.dingtalk.com/document 下「消息通知概述」「发送工作通知」「获取工作通知消息的发送结果 / 发送进度」「撤回工作通知消息」
「使用模板发送工作通知消息」「消息通知类型」「机器人概述」「自定义机器人发送群消息」「自定义机器人安全设置」「机器人发送群聊消息」
「批量发送人与机器人会话中机器人消息」「消息发送与接收类型」「机器人接收消息」「机器人回复/发送消息」「创建并投放卡片」
「AI卡片流式更新」「事件回调（卡片）」（抓取于 2026-09-11），以及文档站链接的官方 `dingtalk-stream-sdk-python` README。
**除标「无凭证探测」的条目外均为文档原文，未实测。** 鉴权见 `auth.md`，接收回调的通道选择见 `events.md`。

## 目录

1. [先选对通道](#1-先选对通道)
2. [工作通知（旧版 API）](#2-工作通知旧版-api)
3. [自定义机器人（Webhook）](#3-自定义机器人webhook)
4. [企业机器人：主动发消息（新版 API）](#4-企业机器人主动发消息新版-api)
5. [企业机器人：接收消息与回复](#5-企业机器人接收消息与回复)
6. [互动卡片与 AI 流式卡片](#6-互动卡片与-ai-流式卡片)
7. [⚠ 未说明 / 矛盾之处](#7--未说明--矛盾之处)

---

## 1. 先选对通道

| 场景 | 用什么 | Endpoint | 凭证 |
| --- | --- | --- | --- |
| 以应用名义给员工发通知（出现在「工作通知」会话） | 工作通知 | `POST oapi /topapi/message/corpconversation/asyncsend_v2` | 应用 token（query）+ `agent_id` |
| 往**任意群**（含外部群）推告警 / 播报，不需要交互 | 自定义机器人 | `POST oapi /robot/send?access_token=<webhook token>` | 机器人 Webhook 里的 access_token（**不是应用 token**）+ 可选加签 |
| 企业内部群里以应用机器人身份发消息 | 企业机器人群聊 | `POST api /v1.0/robot/groupMessages/send` | 应用 token（header）+ `robotCode` + `openConversationId` |
| 给员工发机器人单聊消息（批量） | 企业机器人单聊 | `POST api /v1.0/robot/oToMessages/batchSend` | 应用 token（header）+ `robotCode` |
| 回复用户 @机器人 的那条消息 | 收到的 `sessionWebhook` | 回调里给的 URL | 无需 token，有过期时间 |
| 可交互 / 可更新的卡片、AI 打字机效果 | 互动卡片 | `POST api /v1.0/card/instances/createAndDeliver` + `PUT /v1.0/card/streaming` | 应用 token（header） |

机器人类型对照（「机器人概述」原文）：企业机器人 / 第三方企业应用机器人支持内部群 + 单聊；**自定义机器人只支持群聊（外部群和内部群），不支持单聊**；群模板机器人只支持内部群。

"任务类"提醒（审批任务等）文档明确说工作通知做不到，应使用待办接口（本 skill 未覆盖）。

---

## 2. 工作通知（旧版 API）

### 发送工作通知

**Endpoint**: `POST https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token=...`
**用途**: 以某个微应用的名义推送到员工的「工作通知」会话。**异步**：返回 `task_id`，不代表已送达。
2020-11-27 以后创建的第三方企业应用须改用「使用模板发送工作通知消息」（`sendbytemplate`）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| agent_id | Long | 是 | 发送所用微应用的 AgentID（开发者后台应用详情页） |
| userid_list | String | 否 | **逗号分隔字符串**（不是数组），最多 100 个 |
| dept_id_list | String | 否 | 逗号分隔，最多 20 个；含子部门全部用户 |
| to_all_user | Boolean | 否 | 为 false 时必须指定 userid_list 或 dept_id_list 之一 |
| msg | JSON Object | 是 | 消息体，≤2048 字节；**一次只能一种 msgtype**：text / image / voice / file / link / oa / markdown / action_card |

```bash
curl -X POST "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token=$TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"agent_id\":$DINGTALK_AGENT_ID,\"userid_list\":\"user123,user456\",
       \"msg\":{\"msgtype\":\"markdown\",\"markdown\":{\"title\":\"日报提醒\",\"text\":\"## 请提交日报\"}}}"
```

```python
import os, requests

def send_work_notice(token: str, userids: list[str], msg: dict) -> int:
    r = requests.post(
        "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2",
        params={"access_token": token},
        json={"agent_id": int(os.environ["DINGTALK_AGENT_ID"]),
              "userid_list": ",".join(userids[:100]),      # 逗号分隔字符串，≤100
              "msg": msg},
        timeout=10)
    d = r.json()
    if d.get("errcode") != 0:
        raise RuntimeError(d)
    return d["task_id"]
```

**示例响应**：`{"errcode": 0, "task_id": 256271667526, "request_id": "4jzllmte0wau"}`

**msg 常用格式**（「消息通知类型」原文）

```json
{"msgtype": "text", "text": {"content": "月会通知"}}
{"msgtype": "markdown", "markdown": {"title": "首屏会话透出的展示内容", "text": "## 标题\n* 列表"}}
{"msgtype": "link", "link": {"messageUrl": "https://...", "picUrl": "@lALOACZwe2Rk", "title": "测试", "text": "测试"}}
{"msgtype": "action_card", "action_card": {"title": "会话列表文案", "markdown": "正文", "single_title": "查看详情", "single_url": "https://..."}}
{"msgtype": "oa", "oa": {"message_url": "https://...", "head": {"bgcolor": "FFBBBBBB", "text": "头部标题"},
                        "body": {"title": "正文标题", "form": [{"key": "姓名:", "value": "张三"}], "content": "大段文本"}}}
```

- markdown `text` 最大 5000 字符；text `content` 建议 500 字符内。
- action_card 独立跳转用 `btn_orientation`（"0" 竖直 / "1" 横向）+ `btn_json_list[{title, action_url}]`，与 `single_title/single_url` 二选一。
- 注意工作通知的字段是 **snake_case**（`action_card`、`single_url`），自定义机器人是 **camelCase**（`actionCard`、`singleURL`），别混。
- oa 的 `head.text` 在工作通知里"会被替换为当前应用名称"；`status_bar` 只支持 userid 接收者且 ≤5 人，不支持部门、`to_all_user` 不能为 true。

**限额——超出后"接口返回成功，但用户无法接收到"**（文档原文加粗）：
内部应用单次 ≤5000 人（三方 1000）；同一员工一天只能收一条**内容相同**的消息；内部应用每人每天 ≤500 条（三方 100 条，⚠ 另一页写 50）；
每分钟 ≤5000 人接收。**所以 errcode=0 不等于送达**，重要通知要查发送结果。

### 获取发送结果 / 发送进度 / 撤回

| 接口 | Endpoint | body | 时间窗 |
| --- | --- | --- | --- |
| 发送结果 | `POST oapi /topapi/message/corpconversation/getsendresult` | `agent_id`、`task_id` | 24 小时内；接收人 >100 时不支持（会"调用超时"） |
| 发送进度 | `POST oapi /topapi/message/corpconversation/getsendprogress` | `agent_id`、`task_id` | 说明写 7 天内，参数说明写 24 小时内 ⚠ |
| 撤回 | `POST oapi /topapi/message/corpconversation/recall` | `agent_id`、**`msg_task_id`** | 24 小时内 |

撤回接口的参数名是 `msg_task_id`，不是 `task_id`。

发送结果 `send_result` 字段：`invalid_user_id_list`、`forbidden_user_id_list`（被流控过滤实际未发）、`failed_user_id_list`、
`read_user_id_list`、`unread_user_id_list`、`invalid_dept_id_list`、`forbidden_list[{code, count, userid}]`。
流控 code：`143105` 单应用给单人每日推送超限、`143106` 重复内容、`143103/143104` QPM 超限；进度 `status`：0 未开始 / 1 处理中 / 2 处理完毕。

```python
def confirm_delivery(token: str, task_id: int) -> dict:
    r = requests.post("https://oapi.dingtalk.com/topapi/message/corpconversation/getsendresult",
                      params={"access_token": token},
                      json={"agent_id": int(os.environ["DINGTALK_AGENT_ID"]), "task_id": task_id}, timeout=10)
    res = r.json()["send_result"]
    if res.get("forbidden_user_id_list") or res.get("forbidden_list"):
        print("被流控未送达:", res.get("forbidden_list"))
    return res
```

### 使用模板发送（第三方企业应用专用）

`POST oapi /topapi/message/corpconversation/sendbytemplate`：`agent_id`、`template_id`（开发者后台开发管理页）、
`userid_list`（≤5000）、`dept_id_list`（≤500，二者不能同时为空）、`data`（模板变量，key/value 均为字符串的 JSON 字符串）。
"消息模板只支持第三方企业应用，不支持企业内部应用"，且模板须审核通过（`885006 消息模板不可用`）。

---

## 3. 自定义机器人（Webhook）

**Endpoint**: `POST https://oapi.dingtalk.com/robot/send?access_token=<Webhook 里的 token>[&timestamp=...&sign=...]`
**用途**: 在群设置里添加的"自定义机器人"往群里推消息。**token 是 Webhook 地址里的 access_token，与应用 token 无关**，也不需要换取。

**安全设置三选（可叠加）**：自定义关键词（≤10 个，消息须至少包含 1 个）、加签、IP 白名单（不支持 IPv6）。

**加签**：`sign = urlEncode(Base64(HmacSHA256(key=secret, msg=timestamp + "\n" + secret)))`，timestamp 为毫秒，与服务器时间误差 ≤1 小时，
secret 是安全设置页 `SEC` 开头的字符串。

```python
import base64, hashlib, hmac, os, time, urllib.parse, requests

def robot_send(payload: dict) -> dict:
    token, secret = os.environ["DINGTALK_WEBHOOK_TOKEN"], os.environ.get("DINGTALK_WEBHOOK_SECRET")
    params = {"access_token": token}
    if secret:                                             # 开了加签才需要
        ts = str(round(time.time() * 1000))
        digest = hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
        params |= {"timestamp": ts, "sign": base64.b64encode(digest).decode()}   # requests 会再做一次 URL 编码
    r = requests.post("https://oapi.dingtalk.com/robot/send", params=params, json=payload, timeout=10)
    d = r.json()
    if d.get("errcode") not in (0, "0"):
        raise RuntimeError(d)
    return d

robot_send({"msgtype": "markdown",
            "markdown": {"title": "监控报警", "text": "#### 监控报警 @13800000000\n> CPU 95%"},
            "at": {"atMobiles": ["13800000000"], "isAtAll": False}})
```

文档的 Python 加签示例是先 `urllib.parse.quote_plus` 再手工拼 URL；用 `requests` 的 `params=` 时传未编码的 Base64 值即可，**不要编码两次**。

**请求体**（camelCase）

| 字段 | 说明 |
| --- | --- |
| msgtype | `text` / `markdown` / `link` / `actionCard` / `feedCard`（Webhook 方式不支持 image / audio / file / video） |
| text.content | 文本；要 @ 人需在 content 里写 `@手机号` 或 `@userId`，并在 `at` 里列出 |
| markdown.title / markdown.text | title 是会话列表展示的标题，不是正文标题 |
| link.messageUrl / title / text / picUrl | |
| actionCard.title / text / singleTitle / singleURL 或 btns[{title, actionURL}] / btnOrientation | |
| feedCard.links[{title, messageURL, picURL}] | |
| at.atMobiles / at.atUserIds / at.isAtAll | `at` 与 `text` 同级；最多 @50 人 |
| msgUuid | 幂等 key：超时重试时用同一个值避免重复发 |

**限额**：每个机器人每分钟最多 20 条，超过限流 10 分钟（`410100`）。

**错误码**（文档原文）：`310000`（关键词不匹配 / timestamp 无效 / sign 不匹配 / IP 不在白名单，errmsg 分别为
`keywords not in content` / `invalid timestamp` / `sign not match` / `ip X.X.X.X not in whitelist`）、`400102 机器人已停用`、
`400106 机器人不存在`、`400105 不支持的消息类型`、`43004 无效的HTTP HEADER Content-Type`、`430101–430104 内容不合规`。

<!-- Gap: 文档错误码表写 access_token 不存在为 400101，实测随机伪造 token 返回 300005 "token is not exist" -->
**无凭证探测（2026-09-11）**：随机伪造的 64 位 hex token 返回 `{"errcode":300005,"errmsg":"token is not exist"}`，
**不是文档写的 `400101 access_token不存在`**；用大家都会试的 `access_token=test` 则返回
`{"errcode":660026,"errmsg":"sending too many messages per minute"}`（这个共享假值被频繁调用，先撞上限流）。
按 errmsg 判断 token 错误时要同时认 300005。

文档响应示例写 `"errcode":"0"`（字符串），字段表写 Number ⚠ 文档自相矛盾，判断时两种都接受。

---

## 4. 企业机器人：主动发消息（新版 API）

### 机器人发送群聊消息

**Endpoint**: `POST https://api.dingtalk.com/v1.0/robot/groupMessages/send`，header `x-acs-dingtalk-access-token`，权限点 `qyapi_robot_sendmsg`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| msgKey | String | 是 | 消息模板 key，如 `sampleText`、`sampleMarkdown` |
| msgParam | String | 是 | **JSON 字符串**（不是对象），≤15000 字节 |
| openConversationId | String | 是 | 群会话 ID（`cid...`） |
| robotCode | String | 是 | 机器人编码；须与 token 所属应用匹配 |
| coolAppCode | String | 否 | 以群聊酷应用方式安装机器人时**必须**传 |

```python
import json, os, requests

def bot_group_send(token: str, cid: str, text: str) -> str:
    r = requests.post("https://api.dingtalk.com/v1.0/robot/groupMessages/send",
                      headers={"x-acs-dingtalk-access-token": token},
                      json={"robotCode": os.environ["DINGTALK_ROBOT_CODE"],
                            "openConversationId": cid,
                            "msgKey": "sampleMarkdown",
                            "msgParam": json.dumps({"title": "播报", "text": text}, ensure_ascii=False)},
                      timeout=10)
    r.raise_for_status()
    return r.json()["processQueryKey"]          # 用于查已读 / 撤回
```

接口方式**暂不支持 @**（「机器人回复/发送消息」原文），要 @ 人用 Webhook / sessionWebhook 方式。
常见错误：`invalidParameter.robotCode.auth`（appkey 与 robotCode 不匹配）、`invalidParameter.msgParam.invalid`（msgParam 必须是 json 格式）、
`invalidParameter.msgKey.invalid`、`invalid.openConversationId`、`resource.unavailable`（机器人停用或会话未安装酷应用）。

### 批量发送人与机器人会话（单聊）消息

**Endpoint**: `POST https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend`（注意路径大小写 `oToMessages`）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| robotCode | String | 是 | 必须是企业内部应用机器人的 robotCode |
| userIds | Array of String | 是 | 接收人 userid，**每次最多 20 个**（⚠ 错误码说明写上限 100） |
| msgKey | String | 是 | 同上 |
| msgParam | String | 是 | JSON 字符串 |

响应：`processQueryKey`、`invalidStaffIdList`、`flowControlledStaffIdList`（被限流的 userid）。
撤回：`POST /v1.0/robot/otoMessages/batchRecall`（注意这里是小写 `otoMessages`，参数未转录）。

### msgKey 速查（「消息发送与接收类型 · 接口方式」原文）

| msgKey | msgParam |
| --- | --- |
| sampleText | `{"content": "xxxx"}` |
| sampleMarkdown | `{"title": "xxxx", "text": "xxxx"}` |
| sampleImageMsg | `{"photoURL": "xxxx"}`（完整 URL 或 mediaId） |
| sampleLink | `{"text", "title", "picUrl", "messageUrl"}` |
| sampleActionCard | `{"title", "text", "singleTitle", "singleURL"}` |
| sampleActionCard2…5 | `{"title", "text", "actionTitle1", "actionURL1", "actionTitle2", "actionURL2", ...}`（2–5 为竖排多按钮） |
| sampleActionCard6 | `{"title", "text", "buttonTitle1", "buttonUrl1", "buttonTitle2", "buttonUrl2"}`（横向两按钮） |
| sampleAudio | `{"mediaId", "duration"}` |
| sampleFile | `{"mediaId", "fileName", "fileType"}` |
| sampleVideo | `{"duration", "videoMediaId", "videoType", "picMediaId"}` |

mediaId 来自「上传媒体文件」`POST oapi /media/upload`（参数未转录）。

---

## 5. 企业机器人：接收消息与回复

用户 @机器人或与机器人单聊时，钉钉把消息推给你。两种接收方式（选型见 `events.md`）：

- **Stream 模式（推荐）**：不需要公网地址。机器人回调的 topic 固定为 `/v1.0/im/bot/messages/get`。
- **HTTP 模式**：钉钉 POST 到你的地址，header 带 `timestamp`（毫秒）和 `sign`，需验签。

### Stream 模式（官方 Python SDK `dingtalk-stream`）

```python
# pip install dingtalk-stream      —— 示例改写自官方 README
import os, dingtalk_stream
from dingtalk_stream import AckMessage

class EchoHandler(dingtalk_stream.ChatbotHandler):
    async def process(self, callback: dingtalk_stream.CallbackMessage):
        msg = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        self.reply_text(f"收到：{msg.text.content.strip()}", msg)
        return AckMessage.STATUS_OK, "OK"

credential = dingtalk_stream.Credential(os.environ["DINGTALK_APP_KEY"], os.environ["DINGTALK_APP_SECRET"])
client = dingtalk_stream.DingTalkStreamClient(credential)
client.register_callback_handler(dingtalk_stream.chatbot.ChatbotMessage.TOPIC, EchoHandler())
client.start_forever()
```

README 原文提醒：v0.13.0 起方法名从拼错的 `register_callback_hanlder` 改为 `register_callback_handler`，旧代码升级要改。

### HTTP 模式验签

`sign == Base64(HmacSHA256(key=appSecret, msg=timestamp + "\n" + appSecret))`，且 `timestamp` 与当前时间相差不超过 1 小时（文档原文）。

```python
import base64, hashlib, hmac, os, time

def verify_bot_request(headers) -> bool:
    ts, sign = headers.get("timestamp", ""), headers.get("sign", "")
    if not ts.isdigit() or abs(time.time() * 1000 - int(ts)) > 3600 * 1000:
        return False
    secret = os.environ["DINGTALK_APP_SECRET"]
    expect = base64.b64encode(hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expect, sign)
```

### 消息体关键字段

| 字段 | 说明 |
| --- | --- |
| msgtype | `text` / `richText` / `picture` / `audio` / `video` / `file` |
| text.content | 仅 text 类型有；注意可能带前导空格（示例 `" text"`） |
| content.downloadCode | 图片 / 语音 / 视频 / 文件的下载码，用 `POST /v1.0/robot/messageFiles/download` 换临时链接 |
| conversationType | `"1"` 单聊 / `"2"` 群聊（字符串） |
| conversationId | 会话 ID（群里可当 openConversationId 用） |
| senderStaffId | **发送者 userid**；机器人发布上线后才返回；外部群的外部成员为空 |
| senderId / chatbotUserId / msgId | **加密 ID，不是 userid** |
| senderUnionId | 发送人 unionid |
| sessionWebhook / sessionWebhookExpiredTime | 本会话回复地址及其过期时间（毫秒） |
| robotCode | 机器人编码；自定义机器人没有 |
| isInAtList / atUsers[{dingtalkId, staffId, unionId}] | @ 信息 |

群聊中 @机器人时**不支持接收语音、视频、文件**消息（文档原文）。
用 `sessionWebhook` 回复时消息体格式同自定义机器人 Webhook（`msgtype` + 对应字段），支持 @，过期后不可用。

**调用量超额**：Webhook 和 Stream 用量超出后，收到的消息没有 text / content 字段，带 `errorMessage`，错误码 `20001`
"受调用量超量影响，当前我的消息服务已经暂停"，需升级专业版或购买增购包（文档原文）。处理函数要能容忍 `text` 缺失。

---

## 6. 互动卡片与 AI 流式卡片

### 创建并投放卡片

**Endpoint**: `POST https://api.dingtalk.com/v1.0/card/instances/createAndDeliver`，权限点 `Card.Instance.Write`。
**用途**: 一次调用创建卡片实例并投放到群聊 / 单聊酷应用 / 机器人单聊 / 吊顶。卡片模板先在开发者后台「卡片平台」搭建，拿到 `cardTemplateId`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| cardTemplateId | String | 是 | 卡片模板 ID |
| outTrackId | String | 是 | **你自己生成**的卡片唯一 ID；换模板或数据发新卡要用全新的；后续更新 / 流式都用它（超 64 字符报错） |
| cardData.cardParamMap | Map<String,String> | 是 | 模板变量；**值只支持字符串**（数字、布尔也要转成字符串） |
| openSpaceId | String | 是 | `dtv1.card//<SpaceType>.<SpaceId>`，多个场域用 `;` 连接 |
| callbackType | String | 否 | `STREAM` 或 `HTTP`（必须大写） |
| callbackRouteKey | String | 否 | HTTP 回调时的路由 key（先注册回调地址） |
| imGroupOpenSpaceModel | Object | 否 | 群聊场域信息；用它时 `supportForward` 必填 |
| imGroupOpenDeliverModel.robotCode | String | 否 | 群聊投放用的机器人编码；用 `imGroupOpenDeliverModel` 时必填 |
| imRobotOpenSpaceModel / imRobotOpenDeliverModel | Object | 否 | 机器人单聊（`spaceType: IM_ROBOT`） |
| userIdType | Integer | 否 | 1（默认）userId / 2 unionId |
| privateData | Map | 否 | 按 userid 下发的私有数据 |

| 场域 | SpaceType | SpaceId |
| --- | --- | --- |
| IM 群聊 | IM_GROUP | openConversationId |
| IM 单聊酷应用 | IM_SINGLE | openConversationId |
| IM 机器人单聊 | IM_ROBOT | userId / unionId |
| 吊顶 | ONE_BOX | openConversationId |

```python
import uuid, requests

def send_group_card(token: str, cid: str, template_id: str, params: dict) -> str:
    out_track_id = uuid.uuid4().hex
    body = {
        "cardTemplateId": template_id,
        "outTrackId": out_track_id,
        "callbackType": "STREAM",
        "cardData": {"cardParamMap": {k: str(v) for k, v in params.items()}},   # 值必须是字符串
        "openSpaceId": f"dtv1.card//IM_GROUP.{cid}",
        "imGroupOpenSpaceModel": {"supportForward": True},
        "imGroupOpenDeliverModel": {"robotCode": os.environ["DINGTALK_ROBOT_CODE"]},
    }
    r = requests.post("https://api.dingtalk.com/v1.0/card/instances/createAndDeliver",
                      headers={"x-acs-dingtalk-access-token": token}, json=body, timeout=10)
    r.raise_for_status()
    return out_track_id
```

`robotCode` 取值（文档原文）：场景群用群机器人 robotCode；非场景群的企业内部机器人"使用机器人的AppKey"；第三方企业机器人用 robotCode。
响应结构本次未转录 ⚠。

### AI 卡片流式更新

**Endpoint**: `PUT https://api.dingtalk.com/v1.0/card/streaming`，权限点 `Card.Streaming.Write`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| outTrackId | String | 是 | 与创建卡片时一致 |
| guid | String | 是 | 每次调用唯一，用于幂等 |
| key | String | 是 | 要流式更新的模板变量名 |
| content | String | 是 | 本次内容；单次 ≤1K，总大小建议 ≤3K |
| isFull | Boolean | 否 | 默认 false（增量）。**变量绑定 markdown 时必须为 true 且每次传全量内容** |
| isFinalize | Boolean | 否 | true 时卡片从「输入中」切到「完成」 |
| isError | Boolean | 否 | true 时切到「出错」 |

```python
def stream_markdown(token: str, out_track_id: str, key: str, chunks):
    text = ""
    for piece in chunks:
        text += piece
        requests.put("https://api.dingtalk.com/v1.0/card/streaming",
                     headers={"x-acs-dingtalk-access-token": token},
                     json={"outTrackId": out_track_id, "guid": uuid.uuid4().hex, "key": key,
                           "content": text, "isFull": True, "isFinalize": False}, timeout=10).raise_for_status()
    requests.put("https://api.dingtalk.com/v1.0/card/streaming",
                 headers={"x-acs-dingtalk-access-token": token},
                 json={"outTrackId": out_track_id, "guid": uuid.uuid4().hex, "key": key,
                       "content": text, "isFull": True, "isFinalize": True}, timeout=10).raise_for_status()
```

响应：`{"success": true, "result": true}`。

### 卡片交互回调

- Stream：创建卡片时 `callbackType: "STREAM"`，Stream 客户端注册 topic `/v1.0/card/instances/callback`。
- HTTP：先 `POST /v1.0/card/callbacks/register`（body `apiSecret`、`callbackUrl`、`callbackRouteKey`、`forceUpdate`），
  创建卡片时 `callbackType: "HTTP"` + 同一个 `callbackRouteKey`。
- 回调请求体与需要返回的结构本次未转录 ⚠，见文档「互动卡片 · 事件回调」。

---

## 7. ⚠ 未说明 / 矛盾之处

- 工作通知三方应用每人每日上限 100（发送页）vs 50（发送结果页错误码说明）⚠ 文档自相矛盾。
- `getsendprogress` 时间窗：接口说明"7天内"，`task_id` 参数说明"仅支持查询24小时内的任务" ⚠ 文档自相矛盾。
- `oToMessages/batchSend` 的 `userIds`：参数表"每次最多传20个"，错误码 `invalidParameter.userIds.overMax` 说明"最大限制100" ⚠ 文档自相矛盾。
- 自定义机器人响应示例 `errcode` 为字符串，字段表为 Number ⚠ 文档自相矛盾。
- 旧版 `topapi` 接口文档的 curl 全部用表单（`application/x-www-form-urlencoded`，`msg` 以 JSON 字符串传），本文件示例用 JSON body；
  JSON body 在 topapi 上的行为未实测 ⚠（出问题时改用 `data=` 表单、`msg=json.dumps(...)`）。
- `createAndDeliver` 响应字段、卡片回调的请求 / 应答格式 ⚠ 本次未转录。
