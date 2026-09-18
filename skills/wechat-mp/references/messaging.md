# 消息与客服消息：被动回复、事件推送、客服消息、群发

目录：[1. 被动回复消息（5 秒机制）](#1-被动回复消息5-秒机制) · [2. 常见事件推送](#2-常见事件推送) · [3. 客服消息（48 小时窗口）](#3-客服消息48-小时窗口) · [4. 客服账号与会话管理](#4-客服账号与会话管理) · [5. 高级群发消息](#5-高级群发消息) · [6. 注意事项汇总](#6-注意事项汇总)

**除标「无凭证探测」的条目外，行为描述均为文档原文，未实测。**

被动回复走 XML、经服务器配置的回调地址同步返回；客服消息与群发走标准的 `access_token` + JSON/表单 POST，见 `auth.md`。服务器配置本身（Token/EncodingAESKey/加解密模式）见 `events.md`。

## 1. 被动回复消息（5 秒机制）

**机制**: 用户发消息给公众号，或触发了允许被动回复的事件，微信服务器会向配置好的回调 URL 发一个 POST 请求；开发者在这次 HTTP 响应里直接返回特定 XML 结构，即完成"回复"——**这不是一个独立的 API endpoint，而是对微信这次 POST 请求的响应体**。

**关键规则**（文档原文）
- 微信服务器 **5 秒内收不到响应会断开连接并重试，最多重试 3 次**。
- 排重：普通消息推荐用 `MsgId`；事件类消息推荐用 `FromUserName + CreateTime`。
- 处理不完 5 秒内的逻辑：直接回复字符串 **`success`**（推荐）或**空串**（字节长度为 0，不是 XML 里 `Content` 字段为空），微信不会重试也不会报错；改用客服消息接口异步下发。
- 5 秒内没回复任何内容，或回复了异常数据（比如 JSON），用户会在会话里看到系统提示"该服务号暂时无法提供服务，请稍后再试"。
- 图片等多媒体回复不支持 gif 动图，且需要先通过素材管理接口拿到 `media_id`（临时或永久素材均可）。
- 开启消息加密（见 `events.md`）后，被动回复的 XML 本身也要走同样的 AES 加解密流程。

**示例：回复文本消息**
```xml
<xml>
  <ToUserName><![CDATA[toUser]]></ToUserName>
  <FromUserName><![CDATA[fromUser]]></FromUserName>
  <CreateTime>12345678</CreateTime>
  <MsgType><![CDATA[text]]></MsgType>
  <Content><![CDATA[你好]]></Content>
</xml>
```
`ToUserName`/`FromUserName` 在回复时要对调：把收到消息时的 `FromUserName`（用户 openid）填进回复的 `ToUserName`，反之亦然。

**其余消息类型速查**（结构均为 `<xml>` 包一个与 `MsgType` 同名的子节点）
| MsgType | 必填子字段 | 说明 |
| --- | --- | --- |
| `image` | `Image.MediaId` | 素材管理接口拿到的 media_id |
| `voice` | `Voice.MediaId` | 同上 |
| `video` | `Video.MediaId`、可选 `Title`/`Description` | 同上 |
| `music` | `Music.MusicUrl` 等 | 音乐消息 |
| `news` | `ArticleCount` + `Articles.item[]`（`Title`/`Description`/`PicUrl`/`Url`） | 图文，条数有限制，具体上限见文档原文（未在抓取范围内给出精确数字，`⚠ 文档未说明`，用前建议先用 1 条验证） |

**示例响应（Python，Flask 风格伪代码）**
```python
from flask import request, Response

def wechat_callback():
    # 1) 先做 signature 校验，见 events.md
    xml = parse_incoming_xml(request.data)
    reply = f"""<xml>
  <ToUserName><![CDATA[{xml['FromUserName']}]]></ToUserName>
  <FromUserName><![CDATA[{xml['ToUserName']}]]></FromUserName>
  <CreateTime>{int(time.time())}</CreateTime>
  <MsgType><![CDATA[text]]></MsgType>
  <Content><![CDATA[收到：{xml.get('Content','')}]]></Content>
</xml>"""
    return Response(reply, mimetype="application/xml")
```

## 2. 常见事件推送

事件推送同样通过回调 URL 的 POST 请求送达，`MsgType` 固定为 `event`，用 `Event` 字段区分类型；能否被动回复取决于具体事件类型。

| Event | 触发时机 | 关键字段 |
| --- | --- | --- |
| `subscribe` | 用户关注（含扫码关注） | 普通关注无 `EventKey`；**扫带参数二维码关注时 `EventKey` 带 `qrscene_` 前缀**，`Ticket` 可换二维码图片 |
| `unsubscribe` | 用户取消关注 | 无额外字段；**收到后应删除该用户在自己系统里的全部信息**（文档原文的隐私要求） |
| `SCAN` | 已关注用户扫带参数二维码 | `EventKey` 是**原始场景值，不带 `qrscene_` 前缀**（和 `subscribe` 事件的前缀规则不同，容易搞混） |
| `LOCATION` | 用户上报地理位置（需开启相关权限） | `Latitude`/`Longitude`/`Precision` |
| `CLICK` | 点击 `click` 类型自定义菜单 | `EventKey` 等于创建菜单时填的 `key` |
| `VIEW` | 点击 `view` 类型自定义菜单 | `EventKey` 等于菜单的 `url` |
| `TEMPLATESENDJOBFINISH` | 模板消息发送任务完成 | `MsgID`、`Status`（`success` / `failed:user block` / `failed:system failed`），见 `template-subscribe.md` |

**注意事项**
- `subscribe` 与 `SCAN` 的 `EventKey` 前缀不同是最容易踩的坑：同一个场景值，用户第一次扫码关注时带 `qrscene_` 前缀，之后已关注再扫同一个码触发的是 `SCAN` 不带前缀——代码里按字符串精确匹配场景值时要先判断事件类型再决定是否要去掉前缀。
- 自定义菜单事件（第 3～8 种，扫码推事件、拍照发图等）仅在微信客户端 iPhone 5.4.1+ / Android 5.4+ 生效，旧版本客户端点击无响应也不会有事件推送（文档原文）。
- 事件推送同样受 5 秒/3 次重试机制约束，处理方式与第 1 节一致。

## 3. 客服消息（48 小时窗口）

**Endpoint**: `POST /cgi-bin/message/custom/send`
**用途**: 用户与公众号发生特定交互后，在一个时间窗口内主动推送消息，用于人工客服等场景；和被动回复不同，这是一个独立的、可以异步调用的 API。

**触发条件与下发额度**（文档原文，逐字对照 `errcode` 判断时要注意场景区分）
| 触发场景 | 下发额度 | 额度有效期 |
| --- | --- | --- |
| 用户发送消息 | 5 条 | 48 小时 |
| 点击自定义菜单（仅 `click`/`scancode_push`/`scancode_waitmsg` 三种类型触发） | 3 条 | 1 分钟 |
| 关注公众号 | 3 条 | 1 分钟 |
| 扫描二维码 | 3 条 | 1 分钟 |

文档特别说明：**用户点击菜单触发的是 `CLICK` 事件，走"点击自定义菜单"这条配额规则，不会额外产生"用户发送消息"场景的配额**——即同一次交互不能同时按两套配额计算。

**关键参数**（Request Body，JSON）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| touser | string | 是 | 用户 openid |
| msgtype | string | 是 | `text`/`image`/`voice`/`video`/`music`/`news`/`mpnews`/`mpnewsarticle`/`msgmenu`/`wxcard`/`miniprogrampage` 等，决定下面哪个同名对象必填 |
| text.content | string | msgtype=text 时必填 | 支持插入跳小程序的文字链 |
| customservice.kf_account | string | 否 | 指定用哪个客服账号身份发送 |

**示例请求**
```bash
curl -X POST "https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"touser":"OPENID","msgtype":"text","text":{"content":"您好，已收到您的问题"}}'
```

**注意事项**
- **`mpnews` 类型在"草稿灰度完成后不再支持"**，需改用 `mpnewsarticle` + "发布"系列接口得到的 `article_id`（文档原文，明确写在字段说明里）。
- `⚠ 文档未说明`：超出 48 小时/5 条 或 1 分钟/3 条配额后，接口具体返回什么 `errcode`，文档没有给出；不要假设是某个特定错误码，先按返回体判断，遇到陌生错误码去查全局错误码表（`errors-and-limits.md`）后再决定重试策略。
- 支持"服务通信二次加密和签名"防篡改机制（文档原文提到但未展开），有更高安全要求时参考对应文档单独接入，本 skill 未覆盖。
- 本接口所有用到 `media_id` 的地方，现在都可以直接用素材管理里的**永久素材** `media_id`（文档原文，早期版本只能用临时素材）。

## 4. 客服账号与会话管理

**用途**: 管理多个客服身份（头像、昵称），以及人工客服会话的创建/查询/关闭，配合第 3 节接口以某个客服账号的身份发消息。

| 操作 | Endpoint |
| --- | --- |
| 添加客服账号 | `POST /customservice/kfaccount/add` |
| 修改客服账号 | `POST /customservice/kfaccount/update` |
| 删除客服账号 | `POST /customservice/kfaccount/del` |
| 设置客服头像 | `POST /customservice/kfaccount/uploadheadimg` |
| 邀请微信号绑定客服账号 | `POST /customservice/kfaccount/inviteworker` |
| 获取所有客服账号 | `GET /cgi-bin/customservice/getkflist` |
| 获取在线客服列表 | `GET /cgi-bin/customservice/getonlinekflist` |
| 创建/关闭/查询会话 | `POST /customservice/kfsession/{create,close,getsession,getsessionlist,getwaitcase}` |
| 获取客服聊天记录 | `POST /customservice/msgrecord/getmsglist` |
| 设置客服"正在输入"状态 | `POST /cgi-bin/message/custom/typing` |

**注意事项**
- 添加客服账号每个公众号**最多 100 个**（文档原文）。
- 会话管理接口路径前缀是 `/customservice/...`（不带 `/cgi-bin/`），和客服消息发送、菜单等 `/cgi-bin/...` 前缀不同，容易拼错。

## 5. 高级群发消息

**用途**: 面向全部用户或指定标签/openid 列表的主动群发（区别于第 3 节"客服消息"针对单个用户的、有互动触发条件的推送）。

**接口列表**
| 接口名称 | Endpoint |
| --- | --- |
| 上传群发用的图片 | `POST /cgi-bin/media/uploadimg` |
| 上传图文消息素材（旧接口） | `POST /cgi-bin/media/uploadnews` |
| 根据 openid 列表群发 / 按标签群发 | `POST /cgi-bin/message/mass/send` |
| 全员群发 | `POST /cgi-bin/message/mass/sendall` |
| 预览（发给指定用户校对样式） | `POST /cgi-bin/message/mass/preview` |
| 删除群发 | `POST /cgi-bin/message/mass/delete` |
| 查询群发速度 / 设置群发速度 | `GET /cgi-bin/message/mass/speed/get`、`POST /cgi-bin/message/mass/speed/set` |
| 查询群发状态 | `POST /cgi-bin/message/mass/get` |

**关键参数**（`sendall`，Request Body）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| filter | object | 是 | 圈定接收者（是否 `is_to_all`、按 `tag_id`） |
| msgtype | string | 是 | `mpnews`/`text`/`voice`/`image`/`mpvideo`/`wxcard` |
| clientmsgid | string | 否 | 开发者侧去重 ID，≤32 字节；不填则后台按内容摘要生成 |

**配额与限制**（文档原文，逐条容易被凭直觉写错）
1. **认证公众号**：群发接口每天可成功调用 **1 次**，可选发给全体或某个标签。
2. **认证服务号**：每月（自然月）用户最多能收到 **4 条**群发消息——**无论是后台手动群发还是调接口群发，都计入同一个每月 4 条的用户侧配额**。
3. `is_to_all=true` 且成功群发，才会进入公众号历史消息列表；为防止滥用，**认证公众号一天内只能有一次 `is_to_all=true` 的成功群发（含后台群发），认证服务号一个月内最多 4 次**（同样和后台群发共享次数）。
4. `is_to_all=false` 时服务号可以多次群发，但每个用户一个月最多收到 4 条，超额的那部分会对该用户发送失败（不是接口报错，是部分用户被跳过）。
5. 群发接口**每分钟限制请求 60 次**，超过会被拒绝。
6. 群发全部用户时如果开启了"API 群发保护"，需要管理员在 30 分钟内确认，超时或被拒则本次群发失败。
7. 图文类群发会自动做原创校验，需要提前设置好 `send_ignore_reprint` 等参数。
8. 删除某次群发会导致该次群发用到的素材链接**整体失效**（同一素材被复用时要注意影响面）。

**注意事项**
- "每月 4 条"是**用户维度**的硬上限，不是"每天可调用 1 次"这种调用频率限制；即使 API 调用成功，超过用户月度上限的那部分用户会被跳过而非报错，判断群发是否真的送达要用查询群发状态接口，不能只看 `sendall` 本身的 errcode。
- 图文消息用 `mpnews`/`mpnewsarticle` 引用的 `media_id`/`article_id` 建议通过"草稿箱/新建草稿"和"发布"系列接口获取（本 skill 未覆盖，属于内容生产范畴，见 `SKILL.md` 的"不覆盖"清单）。

## 6. 注意事项汇总

- 三条消息通道时间窗口不同，混淆会导致消息发不出去或被判定超额：被动回复（同步、5 秒内）、客服消息（异步、48 小时/5 条 或 1 分钟/3 条）、群发（主动、公众号 1 条/天，服务号 4 条/月/用户）。
- 事件推送的 `EventKey` 语义随 `Event` 类型变化（`subscribe` 带 `qrscene_` 前缀、`SCAN` 不带、`CLICK`/`VIEW` 分别对应菜单的 `key`/`url`），解析前先看 `Event` 字段再决定怎么读 `EventKey`。
- 涉及 `media_id` 的地方统一可以用永久素材，不要求必须用临时素材（本 skill 未覆盖素材管理接口本身，见 SKILL.md）。
