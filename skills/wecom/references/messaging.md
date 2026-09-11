# 应用消息、群机器人、应用群聊与素材上传

来源：`developer.work.weixin.qq.com/document/path/90235`（消息概述）、`90236`（发送应用消息）、`94867`（撤回）、`94888`（更新模版卡片）、
`90244` / `90245` / `90248`（应用群聊）、`99110`（消息推送，原“群机器人”）、`90253`（上传临时素材）、`90312`（频率）。抓取于 2026-09-11。
**未用真实凭证验证**；报错与行为均为「文档原文，未实测」，标「无凭证探测（2026-09-11）」的除外。

## 目录

1. 选哪条通道
2. 发送应用消息 `message/send`：公共参数与返回
3. 各消息类型的消息体
4. 撤回 / 更新模板卡片
5. 上传临时素材 `media/upload`
6. 群机器人（消息推送）webhook
7. 应用群聊 `appchat`
8. 接收人格式速查（最容易写错）

## 1. 选哪条通道

| 通道 | 发给谁 | 凭证 | 典型用途 | 频率（文档原文） |
|---|---|---|---|---|
| 应用消息 `POST /cgi-bin/message/send` | 成员单聊（按 userid / 部门 / 标签） | 自建应用 access_token + `agentid` | 审批通知、告警私信 | 每应用 ≤ 账号上限数×200 人次/天；同一成员 ≤30 次/分、1000 次/小时，**超过被丢弃不下发** |
| 群机器人（消息推送）`POST /cgi-bin/webhook/send?key=KEY` | 某一个群（内部群） | **webhook 里的 key**，不用 token | 运维告警推群 | 每个机器人 ≤ **20 条/分钟** |
| 应用群聊 `POST /cgi-bin/appchat/send` | **应用自己通过接口创建**的内部群 | 自建应用 token，且应用可见范围必须是**根部门** | 应用拉群协同 | 每企业 2 万人次/分；每成员在群里收同一应用消息 ≤200 条/分、1 万条/天，**超过丢弃接口不报错** |
| 客户群发 `externalcontact/add_msg_template` | 外部客户 / 客户群 | 客户联系可调用应用的 token | 营销触达 | 见 `customer-contact.md`；**需成员确认才发出** |

- 应用消息**不能**发到普通群；应用群聊只能发到本应用 `appchat/create` 建的群，且「不支持添加企业外部联系人进群」。
- 发给外部客户走客户联系，不走 message/send。

## 2. 发送应用消息

**Endpoint**: `POST https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=ACCESS_TOKEN`
**用途**: 以某个应用的身份给成员发单聊消息。

**公共参数**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| touser | string | 否 | — | 成员 ID 列表，**多个用 `\|` 分隔**，最多 1000 个；`"@all"` 表示该应用可见范围全员 |
| toparty | string | 否 | — | 部门 ID 列表，`\|` 分隔，最多 100 个；touser 为 @all 时忽略 |
| totag | string | 否 | — | 标签 ID 列表，`\|` 分隔，最多 100 个；touser 为 @all 时忽略 |
| msgtype | string | 是 | — | text / image / voice / video / file / textcard / news / mpnews / markdown / miniprogram_notice / template_card |
| agentid | int | 是 | — | 企业应用 id，**整型**；必须与 token 所属应用一致（否则 301002） |
| safe | int | 否 | 0 | 0 可对外分享；1 不能分享且显示水印；2 仅企业内分享（**仅 mpnews 支持 2**） |
| enable_id_trans | int | 否 | 0 | id 转译，见下文 |
| enable_duplicate_check | int | 否 | 0 | 重复消息检查：间隔内同样内容（请求 json）的消息不会重复收到 |
| duplicate_check_interval | int | 否 | 1800 | 秒，最大不超过 4 小时 |

touser、toparty、totag 不能同时为空。

**示例请求**

```bash
curl -s -X POST "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"touser":"zhangsan|lisi","msgtype":"text","agentid":1000002,"text":{"content":"服务器 CPU 超过 90%"}}'
```

```python
def send_text(app_tok, agentid: int, userids: list[str], content: str):
    r = wecom_call(app_tok, "POST", "message/send", json={
        "touser": "|".join(userids),          # 竖线分隔的字符串，不是数组
        "msgtype": "text",
        "agentid": agentid,                   # int
        "text": {"content": content},         # ≤2048 字节，超过截断
    })
    bad = {k: r[k] for k in ("invaliduser", "invalidparty", "invalidtag", "unlicenseduser") if r.get(k)}
    if bad:
        log.warning("部分接收人无效：%s", bad)  # errcode 仍是 0
    return r["msgid"]                          # 撤回用
```

**示例响应**（文档原文）

```json
{
  "errcode": 0, "errmsg": "ok",
  "invaliduser": "userid1|userid2", "invalidparty": "partyid1|partyid2", "invalidtag": "tagid1|tagid2",
  "unlicenseduser": "userid3|userid4",
  "msgid": "xxxx",
  "response_code": "xyzxyz"
}
```

**注意事项**

- **部分接收人无权限或不存在时，发送仍然执行，返回 errcode 0 + 无效部分**；常见原因是接收人不在应用可见范围内。`unlicenseduser` 是在可见范围内但无基础接口许可的人。**全部**无效时才报错 `81013`。
- 返回包中的 userid「不区分大小写，统一转为小写」——比对时先 lower()。
- 如果在管理端设置了“在微工作台中始终进入主页”，微信端只能收到文本消息，且文本长度限制 **20 字节**，超出截断。
- 发送频率超限的消息「被丢弃不下发」而**不报错**——发送成功不等于送达。
- 调用建议：避开每小时 0 分、30 分的高峰。
- 无凭证探测（2026-09-11）：假 token 调本接口 → `{"errcode":40014,"errmsg":"invalid access_token"}`，HTTP 200；加 `debug=1` 结果相同。

## 3. 各消息类型的消息体

以下只列 `msgtype` 对应的对象；公共参数见上表。

| msgtype | 消息体 | 关键限制（文档原文） |
|---|---|---|
| text | `"text": {"content": "..."}` | content ≤ 2048 字节，超过截断；支持 `\n` 换行和 `<a href>` 链接；支持 id 转译 |
| image | `"image": {"media_id": "MEDIA_ID"}` | media_id 来自上传临时素材 |
| voice | `"voice": {"media_id": "..."}` | 同上 |
| video | `"video": {"media_id": "...", "title": "...", "description": "..."}` | title ≤128 字节，description ≤512 字节 |
| file | `"file": {"media_id": "..."}` | safe=1 保密消息只支持 txt/pdf/doc/docx/ppt/pptx/xls/xlsx/xml/jpg/jpeg/png/bmp/gif |
| textcard | `"textcard": {"title","description","url","btntxt"}` | title ≤128 字符、description ≤512 字符（**必填**）、url 必填 ≤2048 字节需带协议头；btntxt 默认“详情”≤4 字；description 支持 `<div class="gray/highlight/normal">` |
| news | `"news": {"articles": [{"title","description","url","picurl","appid","pagepath"}]}` | 1~8 条；url 与小程序二选一必填；appid+pagepath 同时填写后忽略 url |
| mpnews | `"mpnews": {"articles": [{"title","thumb_media_id","author","content_source_url","content","digest"}]}` | 图文内容存企业微信；content 支持 html ≤666K 字节；thumb_media_id 必填 |
| markdown | `"markdown": {"content": "..."}` | ≤ **2048** 字节，utf8；只支持子集（标题、加粗、链接、行内代码、引用、`<font color="info/comment/warning">`）；微工作台不支持 |
| miniprogram_notice | `"miniprogram_notice": {"appid","page","title","description","emphasis_first_item","content_item":[{"key","value"}]}` | 只允许绑定了小程序的应用发送；**不支持 @all**；title / description 4~12 个汉字；content_item ≤10 个 |
| template_card | `"template_card": {"card_type": "text_notice" / "news_notice" / "button_interaction" / "vote_interaction" / "multiple_interaction", ...}` | 见下 |

**模板卡片（text_notice 为例）**

```json
{
  "touser": "zhangsan", "msgtype": "template_card", "agentid": 1000002,
  "template_card": {
    "card_type": "text_notice",
    "source": {"desc": "监控平台", "desc_color": 1},
    "main_title": {"title": "磁盘告警", "desc": "prod-db-01"},
    "emphasis_content": {"title": "95%", "desc": "磁盘使用率"},
    "sub_title_text": "请尽快清理",
    "horizontal_content_list": [{"keyname": "机房", "value": "广州"}],
    "card_action": {"type": 1, "url": "https://example.com/alert/123"}
  }
}
```

- text_notice 中 **`card_action` 必填**（type 1 跳 url / 2 跳小程序）；`main_title.title` 与 `sub_title_text` 至少填一个。
- horizontal_content_list ≤6 条（type 1 url / 2 附件 media_id / 3 成员详情 userid），jump_list ≤3 条。
- 填了 `action_menu` 时 `task_id` 必填（同一应用不能重复，字母数字 `_-@`，≤128 字节）。
- 按钮交互 / 投票 / 多选型，以及带 action_menu 的卡片支持回调；「**没有配置回调接口的应用不可发送支持回调的卡片**」。
- 发送后返回 `response_code`（72 小时有效、只能用一次），用于更新卡片。
- 版本要求：投票 / 多选型需客户端 3.1.12+，其余 3.1.6+；微工作台不支持。

**id 转译**（`enable_id_trans: 1`）：在支持字段里写 `$userName=USERID$`、`$departmentName=DEPARTMENT_ID$`、`$userAlias=USERID$`、`$userAliasOrName=USERID$`，
发出时替换为姓名 / 部门名。支持字段：text.content、textcard.title/description、news.title/description、mpnews.title/digest/content、
miniprogram_notice.title/description/content_item.value、template_card 的 source.desc/main_title.title/main_title.desc/sub_title_text/horizontal_content_list.value。
语法不对或无权限时「不替换该项内容，保留原样」。适合第三方应用拿不到姓名时展示名字。

## 4. 撤回 / 更新模板卡片

### 撤回应用消息
**Endpoint**: `POST /cgi-bin/message/recall?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| msgid | string | 是 | message/send 返回的 msgid |

- 只能撤回 **24 小时内**的消息；仅撤回企业微信端，**微信插件端不支持撤回**。
- 撤回与发送必须是同一个应用，否则 40058（错误码排查原文）。

### 更新模版卡片消息
**Endpoint**: `POST /cgi-bin/message/update_template_card?access_token=ACCESS_TOKEN`

```json
{
  "userids": ["userid1", "userid2"], "partyids": [2, 3], "tagids": [44, 55], "atall": 0,
  "agentid": 1, "response_code": "response_code",
  "button": {"replace_name": "已处理"}
}
```

- **注意接收人字段在这里是数组**（`userids` / `partyids` / `tagids`），和 message/send 的竖线字符串不同。
- `response_code` 来自发送返回或用户点击回调（`template_card_event` 的 ResponseCode），72 小时有效、各只能用一次。
- 仅按钮交互 / 投票 / 多选型，以及填了 action_menu 的文本通知 / 图文展示型可更新。更新为新卡片的完整结构见文档 94888。

## 5. 上传临时素材

**Endpoint**: `POST /cgi-bin/media/upload?access_token=ACCESS_TOKEN&type=TYPE`
**用途**: 拿 media_id 给 image / voice / video / file 消息、成员头像、审批附件等使用。

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| type | query | 是 | image / voice / video / file |
| media | multipart 字段名 | 是 | form-data 里要带 `filename`、filelength、content-type；filename 决定消息里展示的文件名 |

```python
with open("report.pdf", "rb") as f:
    r = requests.post(
        "https://qyapi.weixin.qq.com/cgi-bin/media/upload",
        params={"access_token": app_tok.get(), "type": "file"},
        files={"media": ("月报.pdf", f, "application/octet-stream")},   # 字段名必须是 media
        timeout=60,
    ).json()
media_id = r["media_id"]   # 3 天内有效
```

响应（文档原文）：`{"errcode":0,"errmsg":"","type":"image","media_id":"1G6nrLmr...","created_at":"1380000000"}`
——注意 `created_at` 是**字符串**时间戳。

限制（90253 文档原文）：所有文件 > 5 字节；图片 10MB（JPG/PNG）；语音 2MB、≤60s、**仅 AMR**；视频 10MB（MP4）；普通文件 20MB。
⚠ 文档自相矛盾：全局错误码 45001 写「图片不可超过5M；音频不可超过5M；文件不可超过20M」，与本页的图片 10MB / 语音 2MB 不一致。保守起见图片按 5MB 控制。

- media_id **3 天过期**；同一企业内应用之间可共享。
- 永久图片请用“上传图片”接口（90256，本 skill 未抓取正文；频率：每企业每月 3000 张、每天 1000 张）。

## 6. 群机器人（消息推送）webhook

**Endpoint**: `POST https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=KEY`
**用途**: 往一个群推消息。不需要 corpid / secret / access_token，**key 就是凭证**。

「一定要保护好消息推送的webhook地址，避免泄漏！不要分享到github、博客等可被公开查阅的地方」——key 走环境变量 / 密钥管理，不要写进代码仓库。

```bash
curl -s "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=${WECOM_WEBHOOK_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"msgtype":"text","text":{"content":"部署完成","mentioned_list":["wangqing","@all"]}}'
```

```python
import os, base64, hashlib, requests
WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"

def bot_send(payload: dict):
    r = requests.post(WEBHOOK, params={"key": os.environ["WECOM_WEBHOOK_KEY"]}, json=payload, timeout=10).json()
    if r.get("errcode", 0) != 0:
        raise RuntimeError(r)

bot_send({"msgtype": "markdown", "markdown": {"content": "**告警** <font color=\"warning\">CPU 95%</font>\n> 主机：prod-01"}})

img = open("chart.png", "rb").read()
bot_send({"msgtype": "image", "image": {"base64": base64.b64encode(img).decode(), "md5": hashlib.md5(img).hexdigest()}})
```

| msgtype | 消息体 | 限制（文档原文） |
|---|---|---|
| text | `{"content","mentioned_list","mentioned_mobile_list"}` | content ≤2048 字节 utf8；mentioned_list 为 userid 列表，`"@all"` 提醒所有人；拿不到 userid 可用 mentioned_mobile_list（手机号） |
| markdown | `{"content"}` | ≤ **4096** 字节；子集语法同应用消息，支持 `<font color>`；content 里可用 `<@userid>` @人 |
| markdown_v2 | `{"content"}` | ≤4096 字节；支持列表、表格、多级引用、图片、代码块、分割线；**不支持字体颜色和 @群成员**；客户端 4.1.36 以下（安卓 4.1.38 以下）显示为纯文本 |
| image | `{"base64","md5"}` | **不是 media_id**；md5 是图片原始字节（base64 编码前）的 md5；图片 ≤2M，JPG/PNG |
| news | `{"articles":[{"title","description","url","picurl"}]}` | 1~8 条；**url 必填**（应用消息的 news url 是可选） |
| file / voice | `{"media_id"}` | media_id 必须用**本机器人的** `webhook/upload_media` 上传，应用的 media/upload 拿到的不能用 |
| template_card | `{"card_type":"text_notice"/"news_notice", ...}` | 结构与应用消息的模板卡片相近，但字数建议不同（如 main_title.title 建议 ≤26 字）；news_notice 的 `card_image` 必填 |

- 频率：「每个消息推送发送的消息不能超过20条/分钟」。
- 无凭证探测（2026-09-11）：假 key（全 0 UUID）或不带 key → `{"errcode":93000,"errmsg":"invalid webhook url, ..."}`，HTTP 200。
  错误码 93000 文档原文：「消息推送webhookurl不合法或者消息推送已经被移除出群」。

### 机器人文件上传
**Endpoint**: `POST https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key=KEY&type=TYPE`

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| key | query | 是 | webhook 的 key |
| type | query | 是 | voice / file |
| media | multipart 字段名 | 是 | 需带 filename |

- 返回 `media_id`，3 天有效，「只能是对应上传文件的消息推送可以使用」。
- 限制：文件 > 5 字节；file ≤20M；voice ≤2M、≤60s、仅 AMR。
- 无凭证探测（2026-09-11）：假 key + 空文件 → `{"errcode":44001,"errmsg":"empty media data, ..."}`——**文件校验先于 key 校验**，所以上传返回 44001 不代表 key 是对的。

## 7. 应用群聊

「仅支持企业内的自建应用接入使用，且要求自建应用的可见范围是**根部门**」（否则 48002）。不能拉外部联系人。

### 创建群聊会话
**Endpoint**: `POST /cgi-bin/appchat/create?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | string | 否 | 群名，≤50 个 utf8 字符，超过截断 |
| owner | string | 否 | 群主 userid；不填从 userlist 随机选 |
| userlist | **string[]** | 是 | 群成员 id，**至少 2 人，至多 2000 人** |
| chatid | string | 否 | 自定义群 id，≤32 字符，仅 0-9a-zA-Z；不填系统生成 |

响应：`{"errcode":0,"errmsg":"ok","chatid":"CHATID"}`。每企业创建群 ≤1000/天。刚建的群不发消息，旧版客户端可能看不到。

### 应用推送消息到群
**Endpoint**: `POST /cgi-bin/appchat/send?access_token=ACCESS_TOKEN`

```json
{"chatid": "CHATID", "msgtype": "text", "text": {"content": "你的快递已到", "mentioned_list": ["wangqing", "@all"]}, "safe": 0}
```

- 没有 `agentid` 参数，chatid 必须是**该应用创建**的群。
- 支持 text / image / voice / video / file / textcard / news / mpnews / markdown（消息体同应用消息）。
- 限制：每企业 2 万人次/分；未认证或小型企业 15w 人次/小时、中型 35w、大型 70w；每成员在群中收同一应用消息 ≤200 条/分、1 万条/天，**超过丢弃接口不报错**。
- 修改 / 获取群聊会话：`appchat/update`、`appchat/get`（文档 98913 / 98914，本 skill 未抓取正文）。

## 8. 接收人格式速查（最容易写错）

同一个平台里，接收人字段有三种写法，按接口区分：

| 接口 | 字段 | 格式 |
|---|---|---|
| `message/send` | touser / toparty / totag | **`"a\|b\|c"` 字符串** |
| `message/send` 返回 | invaliduser / invalidparty / invalidtag | `"a\|b"` 字符串（userid 已转小写） |
| `message/update_template_card` | userids / partyids / tagids | **数组** |
| `appchat/create` | userlist | **数组** |
| `appchat/send`、`webhook/send` | mentioned_list | **数组**，`"@all"` 为特殊值 |
| `tag/addtagusers` | userlist / partylist | **数组**（返回的 invalidlist 却是 `"a\|b"` 字符串） |
