# 消息推送（企信 / 服务号）与事件回调现状

> 来源：https://developer.fxiaoke.com/openapi_v2/common/system/other/message/ 下 text / compound / image / send / revoke 页、
> common/system/other/ERP/push 页（抓取于 2026-09-11），旧版 wiki「发送消息」（artiId=24）、「接口调用说明」（artiId=169）。
> **本文件全部为文档原文，未实测。** 请求头、thirdTraceId、`FxkClient` 见 `auth.md`。

## 目录
1. 先说结论：能推什么、不能收什么
2. 发文本消息
3. 发复合消息（卡片）：可跳转到 CRM 对象详情
4. 发图文消息
5. 服务号发消息 / 撤回消息
6. 事件回调 / 数据变更订阅：公开文档没有
7. 反方向：把 ERP 数据推进纷享（ERP 集成平台推送接口）
8. 本文件的 ⚠

---

## 1. 先说结论

| 方向 | 能力 | Endpoint |
| --- | --- | --- |
| 你 → 纷享员工 | 发文本 / 复合 / 图文消息（企信，应用身份） | `POST /cgi/message/send`，靠 `msgType` 区分 |
| 你 → 纷享员工 | 服务号发消息、撤回消息 | `POST /cgi/app/message/send`、`POST /cgi/app/message/revoke` |
| 你 → 纷享 | ERP 数据推送进纷享 ERP 集成平台 | `POST /cgi/crm/erp/syncdata/objdata/push` |
| 纷享 → 你 | **CRM 数据变更事件回调 / 订阅** | **新版、旧版公开文档都没有接口说明**（见第 6 节） |

发消息前提：快速开始第 4.2 步配置应用时的「服务号：用于企信发消息」（⚠ 文档未说明应用发消息 `/cgi/message/send` 是否也必须配置服务号）。

## 2. 发文本消息

**Endpoint**: `POST /cgi/message/send?thirdTraceId={uuid4}`

**关键参数**（参数在 body 顶层，**没有 `data` 包裹**）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| toUser | List | 是 | 接收者员工 ID 列表，**最多 500 人** |
| msgType | String | 是 | 固定 `text` |
| text.content | String | 是 | 文本内容 |

**示例请求**

```bash
curl -sS -X POST "https://$FXK_HOST/cgi/message/send?thirdTraceId=$(uuidgen | tr A-Z a-z)" \
  -H "authorization: Bearer $FXK_TOKEN" -H "x-fs-ea: $FXK_EA" -H "x-fs-userid: $FXK_USER_ID" \
  -H 'Content-Type: application/json' \
  -d '{"toUser": ["1000", "1001"], "msgType": "text", "text": {"content": "今日有 3 条新线索待跟进"}}'
```

```python
def send_text(fxk, to_users: list[str], content: str):
    for i in range(0, len(to_users), 500):              # 每次最多 500 人
        fxk.post("/cgi/message/send", {"toUser": to_users[i:i + 500], "msgType": "text",
                                       "text": {"content": content}})
```

**示例响应**：`{"traceId": "E-O.827xxxxxx", "errorDescription": "success", "errorMessage": "OK", "errorCode": 0}`

**注意事项**
- `toUser` 的 ID 形态：新版页写「开放平台员工ID列表」，示例是占位符 `TOUSER1`；旧版 wiki 同样写法、配合旧版传参（`FSUID_…`）。
  新版 header 传参下填 CRM 员工 ID 还是 FSUID ⚠ 文档未说明——按 `auth.md` 第 3 节，默认填员工 ID，需要 FSUID 时加 `"convertUserId": true`。
- 旧版 wiki 的错误示例：`{"errorCode": 20016, "errorMessage": "corpAccessToken error"}`；码表相关码：`10015` 缺少参数 toUser、`11016` toUser 不合法、`11017` msgType 不合法、`12003` 未支持的消息类型、`12005` 文本消息内容为空。

## 3. 发复合消息（卡片）

**Endpoint**: `POST /cgi/message/send?thirdTraceId={uuid4}`，`msgType: "composite"`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| toUser | List | 是 | 最多 500 人 |
| msgType | String | 是 | 固定 `composite` |
| composite.head.title | String | 是 | 头部标题 |
| composite.first.content | String | 否 | 内容标题 |
| composite.form[] | List | 否 | 内容列表，每项 `label` + `value` |
| composite.remark.content | String | 否 | 内容摘要 |
| composite.link.title | String | 是 | 点击跳转链接的标题 |
| composite.link.url | String | 是 | 点击跳转地址，可以用纷享内部跳转地址 |

跳到某条 CRM 数据详情的内部地址（旧版 wiki 24 给出的结构）：

```
fs://CRM/udobj?{"objDescApiName":"AccountObj","objDataId":"5ff2780b7132bb0001bade16"}
```

```python
import json

def notify_new_account(fxk, to_users, acc_id, acc_name, owner_name):
    link = "fs://CRM/udobj?" + json.dumps({"objDescApiName": "AccountObj", "objDataId": acc_id},
                                          separators=(",", ":"), ensure_ascii=False)
    fxk.post("/cgi/message/send", {
        "toUser": to_users,
        "msgType": "composite",
        "composite": {
            "head": {"title": "新客户分配提醒"},
            "first": {"content": acc_name},
            "form": [{"label": "负责人", "value": owner_name}],
            "remark": {"content": "请在 24 小时内完成首次跟进"},
            "link": {"title": "查看客户", "url": link},
        },
    })
```

- ⚠ 文档未说明：`fs://` 链接是否要 URL 编码（旧版 wiki 原文是转义引号的 JSON 直接拼接）；新版页只写到 `fs://CRM/udobj?` 就截断了。

## 4. 发图文消息

**Endpoint**: `POST /cgi/message/send?thirdTraceId={uuid4}`，`msgType: "articles"`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| toUser | List | 是 | 最多 500 人 |
| msgType | String | 是 | 固定 `articles` |
| articles[] | List | 是 | 图文条目，**一次最多 7 条** |
| articles[].title | String | 是 | 标题，最长 45 字符 |
| articles[].author | String | 否 | 作者，最长 8 字符 |
| articles[].description | String | 否 | 摘要，最长 140 字符 |
| articles[].coverImage | String | 是 | 封面图的 mediaId |
| articles[].coverImageInContent | Boolean | 否 | type 为 TEXT 时正文是否显示封面，默认 false |
| articles[].type | String | 是 | `TEXT` 或 `URL` |
| articles[].content | String | 是 | type=TEXT 时为正文；type=URL 时为链接地址 |

```json
{
  "toUser": ["1000"],
  "msgType": "articles",
  "articles": [
    {"title": "九月销售简报", "description": "本月新增客户 128 家", "coverImage": "<mediaId>",
     "type": "URL", "content": "https://intranet.example.com/report/2026-09"}
  ]
}
```

- `coverImage` 要的是 **mediaId**。新版传参默认文件参数用 npath（见 `objects-and-fields.md` 第 6 节）；消息封面图用哪种 ID、是否要 `"convertMediaId": true` ⚠ 文档未说明。
  文档站有「上传消息文件」页（`common/system/other/file/uploadMsgFile.html`，路径 `/media/upload/message`），本 skill 未整理其参数。
- ⚠ 文档笔误：content 说明里写「当 imageTextType 为 URL 时」，参数名其实是 `type`。

## 5. 服务号发消息 / 撤回消息

| 动作 | Endpoint | 文档列出的参数 |
| --- | --- | --- |
| 服务号发消息 | `POST /cgi/app/message/send` | ⚠ 页面参数表是撤回接口的复制品（`serviceId`「需要撤回消息的服务号」+ `messageId`） |
| 撤回消息 | `POST /cgi/app/message/revoke` | `serviceId`（String，必填，发消息的服务号）、`messageId`（String，必填，消息 id） |

```json
{"serviceId": "<服务号ID>", "messageId": "<要撤回的消息ID>"}
```

- ⚠ 文档自相矛盾：「服务号发消息」页的请求参数和示例与「撤回消息」页一字不差，发消息真正需要的收件人、内容字段没有写。旧版 wiki 有「应用挂接服务号发消息」（artiId=120），本 skill 未整理。
- ⚠ 文档未说明：`messageId` 从哪里来（发消息接口的返回示例里没有消息 id）。

## 6. 事件回调 / 数据变更订阅：公开文档没有

- 新版文档站（1295 个中文页面路由）里没有「事件订阅 / 回调地址 / 验签 / 加解密」相关页面。
- 旧版 wiki「接口调用说明」（artiId=169）在「企业内部应用开发」目录描述里提到「纷享开放能力介绍：应用免登、纷享免登、**事件变更订阅**」，
  但旧版 wiki 1191 篇文章里没有一篇讲事件订阅的接口、回调格式或签名校验。
- 所以：**不要凭其他平台（钉钉 / 飞书 / 企业微信）的经验编造纷享的回调 URL、签名算法或事件体结构。** 需要时让用户向纷享客服 / 实施索取资料。
- 文档里能做的替代方案是**增量轮询**：按 `last_modified_time GT <上次同步时间>` 用 `/cgi/crm/v2/data/query` 或 `/cgi/crm/custom/v2/data/findSimple` 拉变更
  （findSimple 的文档示例就是这么写的，见 `query-and-paging.md` 第 8 节）。注意限流与每日配额（`errors-and-limits.md`）。
- 被作废 / 删除的数据用增量轮询能不能拿到（`is_deleted` 字段是否会返回）⚠ 文档未说明。

## 7. 反方向：把 ERP 数据推进纷享

**Endpoint**: `POST /cgi/crm/erp/syncdata/objdata/push?thirdTraceId={uuid4}`
**用途**: 「ERP 提供对外的数据推送接口」——配合纷享后台「连接器 / ERP 集成平台」使用，把外部系统数据推给纷享，再由集成平台同步到 CRM 对象。不是给你接收事件用的。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data.objAPIName | String | 否 | ERP 侧对象 apiName |
| data.dataCenterId | String | 否 | 数据中心 id（CRM 管理后台 → 连接器 → 连接对象 → 生成 api 的推送接口处可找到） |
| data.id | String | 否 | 传值表示数据体完全按标准 ERP 集成平台格式；不传表示非标准格式，需要在推送接口设置函数 |
| data.masterFieldVal | Map | 否 | 主对象数据 |
| data.detailFieldVals | Map | 否 | 从对象数据列表，key 为从对象名 |
| data.directSync | Boolean | 否 | 是否实时同步 |
| data.destObjectApiName | String | 否 | 目标对象 apiName；实时同步时必填 |

```json
{
  "data": {
    "objAPIName": "erpSalesOrderObj",
    "dataCenterId": "63f82854a8bd974420925e83",
    "id": "111",
    "directSync": false,
    "masterFieldVal": {"number": "04270002", "order_account_id": "042700001", "order_origin_price": "100"},
    "detailFieldVals": {"erpSalesOrderProductObj": [{"number": "04270002-0001", "product_id": "000", "product_price": "100"}]}
  }
}
```

这需要先在纷享后台配好 ERP 集成平台的连接对象；只想直接写 CRM 数据时用 `crm-preset-objects.md` / `custom-objects.md` 的 create 接口即可。

## 8. 本文件的 ⚠

- ⚠ 文档未说明：应用发消息是否必须配置服务号（第 1 节）；新版传参下 `toUser` 填哪种员工 ID（第 2 节）；`fs://` 链接是否需编码（第 3 节）；图文封面用 mediaId 还是 npath（第 4 节）；`messageId` 来源（第 5 节）；增量轮询能否拿到删除数据（第 6 节）。
- ⚠ 文档自相矛盾：「服务号发消息」页参数是撤回接口的复制品（第 5 节）。
- ⚠ 文档笔误：图文消息 `imageTextType` 应为 `type`（第 4 节）。
- 事件回调 / 变更订阅：公开文档缺失，不是 skill 遗漏（第 6 节）。
