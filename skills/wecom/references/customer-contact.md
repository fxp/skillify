# 客户联系（企业微信 CRM）：外部联系人、客户群、「联系我」、群发与欢迎语

来源：`developer.work.weixin.qq.com/document/path/92109`（概述）、`92571`（配置了客户联系功能的成员）、`92113` / `92114` / `92994`（客户列表 / 详情 / 批量详情）、
`92115`（备注）、`92117` / `92118`（企业标签 / 打标签）、`92120` / `92122`（客户群）、`92228`（联系我）、`92229`（加入群聊）、
`92135`（创建企业群发）、`92137`（新客户欢迎语）、`92129` / `92130`（回调）。抓取于 2026-09-11。
**未用真实凭证验证**；报错与行为均为「文档原文，未实测」，标「无凭证探测（2026-09-11）」的除外。

## 目录

1. 开工前的三项配置（不做一定 48002）
2. ID 与术语
3. 成员与客户：follow_user 列表 / 客户列表 / 客户详情 / 批量客户详情 / 修改备注
4. 客户标签：企业标签库 / 打标签
5. 客户群：列表 / 详情
6. 「联系我」与「加入群聊」
7. 企业群发与新客户欢迎语
8. 回调事件
9. 典型任务：新客户自动欢迎 + 按渠道打标签

## 1. 开工前的三项配置（不做一定 48002）

1. **使用范围**：「客户联系 → 权限配置 → 使用范围」配置哪些成员可使用联系客户功能，「如未配置，则无法调用后文提到的相关接口」。
   没配置客户联系功能的成员添加的外部联系人**不算客户**，客户列表接口不会返回。
2. **可调用接口的应用**：要用自建应用调客户联系接口，必须把它加到「客户联系 → 可调用接口的应用」里，然后用**这个自建应用的 secret** 换 token。
   错误码 48002 排查原文：「客户联系相关的接口，只能由系统应用“客户联系”调用，或由配置到客户联系“可调用应用”列表中的自建应用调用」。
3. **别用系统应用 secret**：各接口页注明「从2023年12月1日0点起，不再支持通过系统应用secret调用接口，存量企业暂不受影响」。新接入一律走第 2 条。

另外：自建应用**只能操作可见范围内的成员**的客户；接收回调还需在该应用「接收消息 → 接收的消息事件类型」勾选“外部联系人变更回调”。

## 2. ID 与术语

| 名称 | 说明 |
|---|---|
| userid | 企业成员账号（跟进人 / 服务人员） |
| external_userid | 外部联系人 ID（`wm` / `wo` 开头的示例值）。「对于同一个外部联系人，**不同调用方（企业/第三方服务商）获取到的ExternalUserId是不同的**」 |
| chat_id | 客户群 ID，同样不同调用方拿到的不同 |
| follow_user | 添加了某客户的企业成员（一个客户可被多名成员添加） |
| state | 企业自定义渠道参数（「联系我」/ 获客链接里设置），添加事件与客户详情里回传 |
| add_way | 客户**来源**（固定枚举），与 state（**渠道**，自定义）不是一回事 |

2019-05-23 起旧路径 `/cgi-bin/crm/*` 改为 `/cgi-bin/externalcontact/*`，「原URL仍可正常使用」，但旧路径返回旧字段名（如 `customer_contacts` 而不是 `follow_user`）。新代码只用 `externalcontact`。

## 3. 成员与客户

### 获取配置了客户联系功能的成员列表
**Endpoint**: `GET /cgi-bin/externalcontact/get_follow_user_list?access_token=ACCESS_TOKEN`
响应：`{"errcode":0,"errmsg":"ok","follow_user":["zhangsan","lissi"]}`；只返回应用可见范围内的成员。
无凭证探测（2026-09-11）：假 token → `{"errcode":40014,"errmsg":"invalid access_token","follow_user":[]}`。

### 获取客户列表
**Endpoint**: `GET /cgi-bin/externalcontact/list?access_token=ACCESS_TOKEN&userid=USERID`
**用途**: 某个成员添加的全部客户 external_userid（不分页）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| userid | string | 是 | 企业成员 userid |

响应：`{"errcode":0,"errmsg":"ok","external_userid":["woAJ2GCAAAXtWyujaWJHDDGi0mACAAA","wmqfasd1e1927831291723123109rAAA"]}`
无凭证探测（2026-09-11）：假 token → `{"errcode":40014,"errmsg":"invalid access_token","external_userid":[]}`——空列表不代表“没有客户”。

### 获取客户详情
**Endpoint**: `GET /cgi-bin/externalcontact/get?access_token=ACCESS_TOKEN&external_userid=EXTERNAL_USERID&cursor=CURSOR`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| external_userid | string | 是 | 外部联系人 userid，**不是企业成员账号** |
| cursor | string | 否 | 上次返回的 next_cursor。**跟进人超过 500 人时需要分页** |

```python
def get_customer(tok, ext_id):
    detail, follows, cursor = None, [], None
    while True:
        params = {"external_userid": ext_id, **({"cursor": cursor} if cursor else {})}
        r = wecom_call(tok, "GET", "externalcontact/get", params=params)
        detail = r["external_contact"]
        follows += r.get("follow_user", [])
        cursor = r.get("next_cursor")
        if not cursor:
            return detail, follows
```

响应关键字段（文档原文）：

| 字段 | 说明 |
|---|---|
| external_contact.name | 微信用户返回微信昵称；企业微信联系人返回对外展示的别名或实名 |
| external_contact.type | **1 = 微信用户，2 = 企业微信用户** |
| external_contact.avatar / gender / unionid | 第三方应用和代开发应用均不可获取（gender 统一返回 0）；unionid 仅微信用户且企业绑定了微信开发者 ID 时有 |
| external_contact.corp_name / corp_full_name / position / external_profile | 仅企业微信用户有；corp_full_name 仅企业自建应用可获取 |
| follow_user[].userid / remark / description / createtime | 跟进成员与其备注 |
| follow_user[].tags[] | `{group_name, tag_name, tag_id, type}`，type：1 企业设置，2 用户自定义（**不返回 tag_id**），3 规则组标签 |
| follow_user[].remark_mobiles / remark_corp_name | 备注手机号（第三方、代开发不可获取）/ 备注企业名（仅微信客户） |
| follow_user[].add_way | 来源，见下表 |
| follow_user[].state | 渠道参数 |
| follow_user[].oper_userid | 发起添加的一方：成员主动加为成员 userid；客户主动加为客户 external_userid |
| next_cursor | 跟进人多于 500 人时返回 |

add_way 枚举（文档原文）：0 未知、1 扫描二维码、2 搜索手机号、3 名片分享、4 群聊、5 手机通讯录、6 微信联系人、8 安装第三方应用时自动添加的客服人员、
9 搜索邮箱、10 视频号添加、11 日程参与人、12 会议参与人、13 添加微信好友对应的企业微信、14 智慧硬件专属客服、15 上门服务客服、16 获客链接、
17 定制开发、18 需求回复、21 第三方售前客服、22 可能的商务伙伴、24 接受微信账号收到的好友申请、201 内部成员共享、202 管理员/负责人分配。

2025-12-18 起的调整（文档原文）：代开发应用获取客户详情「不再返回客户头像、性别及员工备注的手机号」；服务商应用在试用期 / 低活跃 / 长期未使用时可获取的客户范围收窄。

### 批量获取客户详情
**Endpoint**: `POST /cgi-bin/externalcontact/batch/get_by_user?access_token=ACCESS_TOKEN`
**用途**: 按成员批量拉客户详情，比「list + 逐个 get」省调用次数。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| userid_list | string[] | 是 | — | 成员 userid 列表，**最多 100 个** |
| cursor | string | 否 | — | 分页游标，首次可不填 |
| limit | int | 否 | 50 | 最大 100，超过取 100 |

```python
def iter_customers(tok, userids):
    for i in range(0, len(userids), 100):
        cursor = ""
        while True:
            r = wecom_call(tok, "POST", "externalcontact/batch/get_by_user",
                           json={"userid_list": userids[i:i+100], "cursor": cursor, "limit": 100})
            for item in r.get("external_contact_list", []):
                yield item["external_contact"], item["follow_info"]
            if r.get("fail_info", {}).get("unlicensed_userid_list"):
                log.warning("无互通许可：%s", r["fail_info"]["unlicensed_userid_list"])
            cursor = r.get("next_cursor")
            if not cursor:
                break
```

注意：
- 返回的是 `external_contact_list[].follow_info`（**单个对象**，对应请求里的某个成员），不是 `follow_user` 数组；标签只给 `tag_id` 列表（企业标签和规则组标签），**个人标签不返回**。
- 部分 userid 无互通许可时仍成功，列在 `fail_info.unlicensed_userid_list`；**全部**无许可直接报 `701008`。

### 修改客户备注信息
**Endpoint**: `POST /cgi-bin/externalcontact/remark?access_token=ACCESS_TOKEN`

<!-- Gap: 文档把本接口（以及 get_corp_tag_list / add_corp_tag / edit_corp_tag / del_corp_tag / add_msg_template / send_welcome_msg）的请求方式标为「POST(HTTP)」；无凭证探测（2026-09-11）POST http://qyapi.weixin.qq.com/cgi-bin/externalcontact/remark 返回 nginx 301 重定向到 https，只能用 https。 -->
⚠ 请求方式文档标为「POST(HTTP)」，但无凭证探测（2026-09-11）：`POST http://qyapi.weixin.qq.com/cgi-bin/externalcontact/remark` → **HTTP 301** 跳转到 https；
改走 `https://` → `{"errcode":40014,"errmsg":"invalid access_token"}`（路径存在）。一律用 https，别照抄“HTTP”。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| userid | string | 是 | 企业成员 userid |
| external_userid | string | 是 | 外部联系人 userid |
| remark | string | 否 | 备注，最多 20 个字符 |
| description | string | 否 | 描述，最多 150 个字符 |
| remark_company | string | 否 | 备注企业名，最多 20 个字符，**只在外部联系人为微信用户时有效** |
| remark_mobiles | string[] | 否 | 备注手机号，**覆盖旧值**。清空：文档原文「请在remark_mobiles填写一个空字符串("")」——是传 `""` 还是 `[""]` ⚠ 文档未说明，待实测 |
| remark_pic_mediaid | string | 否 | 备注图片 media_id |

五个可选字段不可同时为空。应用只能改可见范围内成员添加的客户。

## 4. 客户标签

### 获取企业标签库
**Endpoint**: `POST /cgi-bin/externalcontact/get_corp_tag_list?access_token=ACCESS_TOKEN`（文档同样标“POST(HTTP)”，见上方 Gap）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| tag_id | string[] | 否 | 要查询的标签 id |
| group_id | string[] | 否 | 要查询的标签组 id（返回组及组内全部标签） |

- 都不传返回全部；**同时传时忽略 tag_id，只按 group_id 过滤**。
- 响应 `tag_group[]`：`group_id`、`group_name`、`create_time`、`order`、`deleted`（只在指定 id 查询时返回）、`tag[]{id,name,create_time,order,deleted}`。

### 添加 / 编辑 / 删除企业标签

| Endpoint | 关键参数 | 规则（文档原文） |
|---|---|---|
| `POST /cgi-bin/externalcontact/add_corp_tag` | `group_id` 或 `group_name`、`order`、`tag[{name, order}]`（name 必填，≤30 字符） | 填 group_id 则忽略 group_name 和组 order；group_name 已存在则在该组下新建；不支持空标签组；同组同名只建一个；**每企业最多 10000 个企业标签** |
| `POST /cgi-bin/externalcontact/edit_corp_tag` | `id`（标签或标签组 id，必填）、`name`、`order` | 不能与已有组 / 同组标签重名 |
| `POST /cgi-bin/externalcontact/del_corp_tag` | `tag_id[]`、`group_id[]`（不可同时为空） | 组内标签全删则组自动删除 |

- `agentid` 参数「仅旧的第三方多应用套件需要填」，自建应用不要传。
- 「应用仅能编辑和删除本应用创建的标签」。

### 编辑客户企业标签（给客户打标签）
**Endpoint**: `POST /cgi-bin/externalcontact/mark_tag?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| userid | string | 是 | **添加了该客户的成员** userid |
| external_userid | string | 是 | 外部联系人 userid |
| add_tag | string[] | 否 | 要打的企业标签 id |
| remove_tag | string[] | 否 | 要移除的标签 id |

- 标签是「成员 × 客户」维度的：同一客户被两名成员添加，要分别打。请确保 external_userid 是该 userid 的外部联系人（否则 84061）。
- add_tag / remove_tag 不可同时为空；每个成员对同一客户最多 3000 个标签。
- 并发给同一组客户和成员打标签会 `45035`（并发冲突），批量打标签请串行或按成员分片。

## 5. 客户群

### 获取客户群列表
**Endpoint**: `POST /cgi-bin/externalcontact/groupchat/list?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| status_filter | int | 否 | 0 | 0 全部；1 离职待继承；2 离职继承中；3 离职继承完成 |
| owner_filter.userid_list | string[] | 否 | — | 群主过滤，最多 100 个。**不填时可见范围超过 1000 人会报 81017**；群主为离职成员时必须指定 |
| cursor | string | 否 | — | 首次不填 |
| limit | int | **是** | — | 1 ~ 1000 |

- 响应：`group_chat_list[{chat_id, status}]`、`next_cursor`（为空表示没有更多）。
- 旧版 `offset + limit` 分页（offset+limit ≤ 50000）将废弃，用 cursor。

### 获取客户群详情
**Endpoint**: `POST /cgi-bin/externalcontact/groupchat/get?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| chat_id | string | 是 | — | 客户群 ID |
| need_name | int | 否 | 0 | 1 时返回 `member_list[].name` |

响应 `group_chat`：`chat_id`、`name`、`owner`、`create_time`、`notice`、`member_list[]`（`userid`、`type` 1 企业成员 / 2 外部联系人、`unionid`、`join_time`、
`join_scene` 1 直接邀请 / 2 邀请链接 / 3 扫群二维码、`invitor.userid`（仅本企业成员邀请时）、`group_nickname`、`name`）、`admin_list[]`、`member_version`。

- 「如果发生群信息变动，会立即收到群变更事件，但是部分信息是异步处理，可能需要等一段时间调此接口才能得到最新结果」——收到事件马上查可能拿到旧数据。
- `member_version` 可配合群变更事件判断成员是否真的变化，减少调用。
- 群主必须在应用可见范围内。

## 6. 「联系我」与「加入群聊」

### 配置客户联系「联系我」方式
**Endpoint**: `POST /cgi-bin/externalcontact/add_contact_way?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| type | int | 是 | — | 1 单人，2 多人 |
| scene | int | 是 | — | 1 在小程序中联系，2 通过二维码联系 |
| style | int | 否 | — | 小程序控件样式（scene=1） |
| remark | string | 否 | — | 备注，≤30 字符 |
| skip_verify | bool | 否 | **true** | 客户添加时是否无需验证 |
| state | string | 否 | — | 渠道参数，≤30 字符，客户详情与添加事件里回传 |
| user | string[] | 否 | — | 使用成员；**type=1 时必填且只能一个** |
| party | int[] | 否 | — | 使用部门；只在 type=2 有效 |
| is_temp | bool | 否 | false | 临时会话模式（**仅医疗行业**企业可创建，仅单人） |
| expires_in / chat_expires_in | int | 否 | 7 天 / 24 小时 | 临时会话二维码有效期 / 会话有效期，最多 14 天 |
| unionid | string | 否 | — | 限定可临时会话的客户 |
| is_exclusive | bool | 否 | false | 同一外部企业客户只能添加同一个员工 |
| conclusions | object | 否 | — | 结束语，仅临时会话有效 |

```python
r = wecom_call(tok, "POST", "externalcontact/add_contact_way", json={
    "type": 1, "scene": 2, "user": ["zhangsan"], "state": "offline_expo_2026", "remark": "展会渠道",
})
save(config_id=r["config_id"], qr_code=r["qr_code"])   # config_id 务必持久化
```

响应：`{"errcode":0,"errmsg":"ok","config_id":"42b3...","qr_code":"https://p.qpic.cn/wwhead/..."}`（qr_code 仅 scene=2 返回）

注意（文档原文）：
- 「用户需要妥善存储返回的config_id，**config_id丢失可能导致用户无法编辑或删除「联系我」**」；通过 API 添加的「联系我」**不会在管理端展示**。
- 每企业通过 API 最多 **50 万**个「联系我」（与「加入群聊」共用额度）；临时会话不占数量但每日最多 10 万个。
- 使用成员必须已激活、已实名、且配置了客户联系功能（否则 41054）；每个联系方式最多 100 个使用成员（含部门展开）。
- 无凭证探测（2026-09-11）：假 token 调本接口 → `{"errcode":40014,"errmsg":"invalid access_token"}`，路径存在。

### 其他「联系我」接口

| Endpoint | 参数 | 说明 |
|---|---|---|
| `POST /cgi-bin/externalcontact/get_contact_way` | `config_id` | 返回 `contact_way{...}`，含 qr_code、user、party、state 等 |
| `POST /cgi-bin/externalcontact/list_contact_way` | `start_time`（默认 90 天前）、`end_time`、`cursor`、`limit`（默认 100，最多 1000） | 只返回 config_id 列表；**仅可获取 2021-07-10 以后创建的**；不含临时会话 |
| `POST /cgi-bin/externalcontact/update_contact_way` | `config_id` + 要改的字段 | remark / user / party 是**覆盖**；已失效的临时会话不能编辑 |
| `POST /cgi-bin/externalcontact/del_contact_way` | `config_id` | — |
| `POST /cgi-bin/externalcontact/close_temp_chat` | `userid`、`external_userid` | 断开临时会话，断开前自动发结束语 |

结束语 `conclusions`：text.content ≤4000 字节；image / link / miniprogram 三选一（同时填按 image > link > miniprogram 取）；
构造时 image 只能填 media_id，查询时返回 pic_url。

### 客户群「加入群聊」
**Endpoint**: `POST /cgi-bin/externalcontact/groupchat/add_join_way?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| scene | int | 是 | — | 1 群的小程序插件，2 群的二维码插件 |
| chat_id_list | string[] | 是 | — | 使用该配置的客户群，**最多 5 个** |
| auto_create_room | int | 否 | 1 | 群满后自动建新群 |
| room_base_name / room_base_id | string / int | 否 | — | 自动建群名前缀与起始序号（如“销售客服群10”“销售客服群11”…） |
| remark | string | 否 | — | 超过 30 字符截断 |
| state | string | 否 | — | ≤30 个 UTF-8 字符，客户群详情里回传 |

返回 `config_id`；配套 `get_join_way` / `update_join_way` / `del_join_way`（参数 config_id）。「应用仅能获取和管理由本应用创建的「加入群聊」二维码」。

## 7. 企业群发与新客户欢迎语

### 创建企业群发
**Endpoint**: `POST /cgi-bin/externalcontact/add_msg_template?access_token=ACCESS_TOKEN`（文档标“POST(HTTP)”，见上方 Gap）

**关键行为（文档原文，加粗为原文强调）**：
- 「**调用该接口并不会直接发送消息给客户/客户群，需要成员确认后才会执行发送**」——它创建的是“群发任务”，成员在客户端点确认才发出。要做“自动触达”的需求，这个接口满足不了。
- 「**仅会推送给最后跟客户进行聊天互动的企业成员**」。
- 每位客户 / 每个客户群每月最多接收条数为**当月天数**（可在群发助手里调为每周 7 条或每天 1 条），超出的收不到。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| chat_type | string | 否 | single | single 发给客户；group 发给客户群 |
| external_userid | string[] | 否 | — | 仅 single 有效，最多 1 万个；指定后 tag_filter 不生效 |
| chat_id_list | string[] | 否 | — | 仅 group 有效，最多 2000 个（客户端 4.1.10+ 生效） |
| tag_filter.group_list[].tag_list | string[] | 否 | — | 同组“或”、不同组“且”；每组 ≤100 个 |
| sender | string | 否 | — | 发送成员；**group 时必填**；只给 sender 相当于选了该成员所有客户 |
| allow_select | bool | 否 | false | 允许成员重新选择（仅客户群发） |
| text.content | string | 否 | — | ≤4000 字节 |
| attachments | object[] | 否 | — | ≤9 个；msgtype：image / link / miniprogram / video / file |

- text 与 attachments 不能同时为空；image 的 media_id 与 pic_url 二选一（pic_url 只能用“上传图片”接口得到的链接）。
- 对客户群发，sender、external_userid、tag_filter 不可同时为空。
- 响应：`fail_list`（无效或无法发送的 external_userid / chatid）、`msgid`。创建后立即查群发记录可能 41063（派发中）。

### 发送新客户欢迎语
**Endpoint**: `POST /cgi-bin/externalcontact/send_welcome_msg?access_token=ACCESS_TOKEN`（文档标“POST(HTTP)”，见上方 Gap）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| welcome_code | string | 是 | 添加客户事件里的 `WelcomeCode`，**有效期 20 秒** |
| text.content | string | 否 | ≤4000 字节 |
| attachments | object[] | 否 | ≤9 个 |

规则（文档原文）：
- 「企业仅可在收到相关事件后**20秒内**调用，且只可调用一次」。
- 管理端已为该成员配置了欢迎语时，事件里**不会**带 welcome_code。
- 已下发 → `41051`（无需重试）；其他应用正在发 → `41096`（不代表成功，可重试）。多个应用都收到 welcome_code 时**仅最先调用的应用成功**。
- 长期未登录企业微信的成员无法发送欢迎语。
- text 与附件可以同时发，会以多条消息触达。
- ⚠ 文档自相矛盾：参数表写 `attachments.msgtype`「可选image、link、miniprogram或者video」，但请求示例与下方参数表都包含 `file`（`file.media_id`）。

## 8. 回调事件

「当用户在客户端或管理端进行某种操作后，会回调相应的事件给开发者。**通过API进行的操作不会产生回调**」——你用 API 改备注、打标签、建标签，不会收到对应事件。

接收条件：自建应用配置在「客户联系 - 可调用接口的应用」中，设置了 API 接收消息，并勾选“外部联系人变更回调”。签名 / 解密 / 响应见 `callbacks-crypto.md`。

| Event | ChangeType | 触发 |
|---|---|---|
| change_external_contact | add_external_contact | 配置了客户联系功能的成员添加外部联系人（带 `State`、`WelcomeCode`） |
| change_external_contact | edit_external_contact | 成员修改客户备注、手机号或标签 |
| change_external_contact | add_half_external_contact | 外部联系人免验证添加成员（此时尚未成为双向好友） |
| change_external_contact | del_external_contact | 成员删除客户 |
| change_external_contact | del_follow_user | 客户删除成员 |
| change_external_contact | transfer_fail | 客户接替失败（需“分配在职或离职成员的客户”权限） |
| change_external_chat | create / update / dismiss | 客户群创建 / 变更 / 解散 |
| change_external_tag | create / update / delete / shuffle | 企业客户标签创建 / 变更 / 删除 / 重排（需“管理企业客户标签”权限） |

添加企业客户事件明文（文档原文）：

```xml
<xml>
  <ToUserName><![CDATA[toUser]]></ToUserName>
  <FromUserName><![CDATA[sys]]></FromUserName>
  <CreateTime>1403610513</CreateTime>
  <MsgType><![CDATA[event]]></MsgType>
  <Event><![CDATA[change_external_contact]]></Event>
  <ChangeType><![CDATA[add_external_contact]]></ChangeType>
  <UserID><![CDATA[zhangsan]]></UserID>
  <ExternalUserID><![CDATA[woAJ2GCAAAXtWyujaWJHDDGi0mAAAA]]></ExternalUserID>
  <State><![CDATA[teststate]]></State>
  <WelcomeCode><![CDATA[WELCOMECODE]]></WelcomeCode>
</xml>
```

「如果外部联系人和成员已经开始聊天或已通过「外部联系人免验证添加成员事件」得到的welcomecode发送欢迎语，则不会继续返回welcomecode。
成员添加其他企业的企业微信联系人（商务伙伴）时，将自动递名片打招呼，不再回调welcomecode」——代码要容忍 WelcomeCode 缺失。

## 9. 典型任务：新客户自动欢迎 + 按渠道打标签

流程：扫「联系我」二维码（带 state）→ 企业微信推 `add_external_contact` 事件 → **20 秒内**用 WelcomeCode 发欢迎语 → 按 state 给客户打企业标签。

```python
import threading
from flask import Flask, request
# crypto = WeComCrypto(token, encoding_aes_key, corpid)   见 callbacks-crypto.md
# tok = WeComToken(corpid, <已配置到客户联系可调用应用的自建应用 secret>)

STATE_TAGS = {"offline_expo_2026": ["etXXXX_expo"]}      # state → 企业标签 id（先用 get_corp_tag_list 查）
app = Flask(__name__)

@app.post("/wecom/callback")
def on_event():
    xml = crypto.decrypt_post(request.args["msg_signature"], request.args["timestamp"],
                              request.args["nonce"], request.data)
    ev = parse_xml(xml)
    if ev.get("Event") == "change_external_contact" and ev.get("ChangeType") == "add_external_contact":
        threading.Thread(target=handle_new_customer, args=(ev,), daemon=True).start()
    return ""                                   # 立即 200，业务异步；5 秒内无响应会被重试（重复事件要幂等）

def handle_new_customer(ev):
    uid, ext, state = ev["UserID"], ev["ExternalUserID"], ev.get("State", "")
    if ev.get("WelcomeCode"):                   # 可能缺失：管理端已配欢迎语 / 已开始聊天 / 商务伙伴
        try:
            wecom_call(tok, "POST", "externalcontact/send_welcome_msg",
                       json={"welcome_code": ev["WelcomeCode"], "text": {"content": "您好，我是您的专属顾问～"}})
        except WeComError as e:
            if e.errcode not in (41051,):       # 41051 已下发，忽略
                log.error("welcome failed %s", e)
    if state in STATE_TAGS:
        wecom_call(tok, "POST", "externalcontact/mark_tag",
                   json={"userid": uid, "external_userid": ext, "add_tag": STATE_TAGS[state]})
```

要点：欢迎语必须在 20 秒内发出，所以事件处理要“先返回、后处理”，但后台任务也不能排队太久；打标签是 API 操作，**不会**再触发 `edit_external_contact` 回调。
