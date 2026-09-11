# 通讯录：成员、部门、标签

来源：`developer.work.weixin.qq.com/document/path/90193`（概述）、`90195`–`90201`（成员）、`95402` / `95895`（手机号 / 邮箱换 userid）、
`96067`（成员ID列表）、`90205`–`90208`、`95350` / `95351`（部门）、`90213` / `90214` / `90216`（标签）、`96079`（通讯录同步接口调整）、
`90967` / `90970` / `90971`（通讯录回调）。抓取于 2026-09-11。
**未用真实凭证验证**；报错与行为均为「文档原文，未实测」，标「无凭证探测（2026-09-11）」的除外。

## 目录

1. 先选 token：读和写用的不是同一个 secret
2. 成员：读取 / 部门成员 / 成员ID列表 / 手机号邮箱换 userid
3. 成员：创建 / 更新 / 删除
4. 部门：创建 / 更新 / 删除 / 子部门ID列表 / 单个部门详情 / 部门列表
5. 标签：列表 / 成员 / 增加成员
6. 通讯录变更回调
7. 典型任务：把外部 HR 系统同步到企业微信

## 1. 先选 token：读和写用的不是同一个 secret

| 操作 | 可以用的 token | 限制 |
|---|---|---|
| 读成员姓名、部门名等详情 | **自建应用** token | 只能读**应用可见范围内**的；2022-06-20 后新建的自建应用读不到头像、性别、手机、邮箱、企业邮箱、个人二维码、地址（需成员 OAuth2 授权） |
| 只拿 userid / 部门 ID 做比对 | **通讯录同步** token → `user/list_id`、`department/simplelist` | `user/list_id`「仅支持通过“通讯录同步secret”调用」 |
| 创建 / 更新 / 删除成员 | **通讯录同步** token（或第三方通讯录应用） | 「仅通讯录同步助手或第三方通讯录应用可调用」 |
| 创建 / 更新 / 删除部门 | 文档写「第三方仅通讯录应用可以调用」 | ⚠ 文档表述不一致：部门写接口的权限说明没有提“通讯录同步助手”，而成员写接口明确写了；概述页（90193）说通讯录同步 secret 可以对部门“添加、修改、删除”。按概述页理解为通讯录同步 secret 可写，待实测 |

关键时间点（文档原文）：

- **2022-06-20 起**：除通讯录同步外的基础应用（客户联系、微信客服、会话存档、日程等）以及新建的自建应用 / 代开发应用，调读取类接口不再返回敏感字段（头像、性别、手机、邮箱、企业邮箱、员工个人二维码、地址）。
- **2022-08-15 起**：通讯录同步助手的“新增 IP”（过去 90 天未使用过的 IP）不能再调「读取成员 / 获取部门成员 / 获取部门成员详情 / 获取部门列表 / 获取单个部门详情 / 导出成员 / 导出成员详情 / 导出部门」，错误码 `48009`。
  写入接口不受影响。「建议“通讯录同步”功能仅用于将外部通讯录写入企业微信的场景」。
- 通讯录同步必须配置企业可信 IP（不允许第三方服务商 IP）。

写代码时把两个 token 分开：`contact_tok`（通讯录同步 secret，用于写和 list_id）、`app_tok`（自建应用 secret，用于读详情）。
缓存实现见 `access-token.md`。下文示例中的 `wecom_call(tok, method, path, params=..., json=...)` 指 `errors-and-limits.md` 里的统一封装。

## 2. 成员：读取

### 读取成员
**Endpoint**: `GET /cgi-bin/user/get?access_token=ACCESS_TOKEN&userid=USERID`
**用途**: 按 userid 取单个成员详情。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| userid | string | 是 | 成员 UserID，**不区分大小写**，1~64 字节 |

权限：应用须拥有该成员的查看权限（在可见范围内）。

```bash
curl -s "https://qyapi.weixin.qq.com/cgi-bin/user/get?access_token=${TOKEN}&userid=zhangsan"
```

```python
u = wecom_call(app_tok, "GET", "user/get", params={"userid": "zhangsan"})
print(u["name"], u["department"], u.get("main_department"), u["status"])
```

响应关键字段（文档原文）：

| 字段 | 说明 |
|---|---|
| userid / name | 成员 ID / 名称（第三方拿不到 name，返回 userid 代替） |
| department / order / is_leader_in_dept | 所属部门 ID 列表、对应排序、是否部门负责人（三者按下标一一对应） |
| main_department | 主部门 |
| direct_leader | 直属上级 userid 列表（最多 1 个） |
| mobile / gender / email / biz_mail / avatar / address / qr_code | 敏感字段，见上文 2022-06-20 限制；拿不到时 gender 返回 0 |
| status | 激活状态：**1=已激活，2=已禁用，4=未激活，5=退出企业** |
| extattr / external_profile / external_position | 扩展属性 / 对外属性 / 对外职务 |
| open_userid | 仅第三方应用可获取 |

注意：
- 无凭证探测（2026-09-11）：假 token 返回 `{"errcode":40014,"errmsg":"invalid access_token","department":[],"order":[],"is_leader_in_dept":[],"direct_leader":[]}`——**失败响应也带空列表字段**，必须先判 errcode。
- 把 token 放 `Authorization: Bearer` header → `41001 access_token missing`（无凭证探测 2026-09-11）。

### 获取部门成员（只有 userid + name）
**Endpoint**: `GET /cgi-bin/user/simplelist?access_token=ACCESS_TOKEN&department_id=DEPARTMENT_ID`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| department_id | int | 是 | 部门 id |

响应：`{"errcode":0,"errmsg":"ok","userlist":[{"userid":"zhangsan","name":"张三","department":[1,2],"open_userid":"xxxxxx"}]}`

### 获取部门成员详情
**Endpoint**: `GET /cgi-bin/user/list?access_token=ACCESS_TOKEN&department_id=DEPARTMENT_ID`
**用途**: 部门下所有成员的完整字段（同「读取成员」）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| department_id | int | 是 | 部门 id |

注意：
- 文档：「如需获取该部门及其子部门的所有成员，需先获取该部门下的子部门，然后再获取子部门下的部门成员，逐层递归获取」。
- ⚠ 文档自相矛盾：错误码 45029（回包过大）的排查说明写「/cgi-bin/user/list … 同时不要指定fetch_child=1」，但本接口参数表**没有** `fetch_child` 参数。按参数表写，不要依赖 fetch_child。
- 通讯录同步 token 从新 IP 调用会被拒（48009）。

### 获取成员ID列表
**Endpoint**: `POST /cgi-bin/user/list_id?access_token=ACCESS_TOKEN`
**用途**: 取企业全部 userid 与部门的对应关系，用于增量同步比对。**仅支持通讯录同步 secret**。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| cursor | string | 否 | 分页游标，首次不填，之后填上次返回的 `next_cursor` |
| limit | int | 否 | 1 ~ 10000 |

```python
def all_dept_users(contact_tok):
    cursor, out = "", []
    while True:
        body = {"limit": 10000, **({"cursor": cursor} if cursor else {})}
        r = wecom_call(contact_tok, "POST", "user/list_id", json=body)
        out += r.get("dept_user", [])
        cursor = r.get("next_cursor")
        if not cursor:          # 文档：next_cursor 为空表示没有更多数据
            return out
```

响应：`{"errcode":0,"errmsg":"ok","next_cursor":"aaaaaaaaa","dept_user":[{"userid":"zhangsan","department":1},{"userid":"zhangsan","department":2}]}`
——**一个成员在多个部门会出现多条**，按 userid 去重。

无凭证探测（2026-09-11）：把 token 放 JSON body `{"access_token": ...}` → `41001 access_token missing`。

### 手机号获取 userid
**Endpoint**: `POST /cgi-bin/user/getuserid?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| mobile | string | 是 | 通讯录中的手机号，5~32 字节 |

响应：`{"errcode":0,"errmsg":"ok","userid":"zhangsan"}`（第三方应用拿到的是密文 userid）

注意：「若出错的次数超出企业人数上限的20%，会导致1天不可调用」——批量导入前先清洗手机号，不要拿一堆脏数据逐个试。
不存在或不在可见范围 → `46004`。

### 邮箱获取 userid
**Endpoint**: `POST /cgi-bin/user/get_userid_by_email?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| email | string | 是 | — | 邮箱 |
| email_type | int | 否 | 1 | 1-企业邮箱；2-个人邮箱 |

## 3. 成员：创建 / 更新 / 删除

### 创建成员
**Endpoint**: `POST /cgi-bin/user/create?access_token=ACCESS_TOKEN`
**用途**: 新建成员。「仅通讯录同步助手或第三方通讯录应用可调用」。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| userid | string | 是 | 1~64 字节，只能由数字、字母和 `_-@.` 组成，**首字符必须是数字或字母**；唯一性检查忽略大小写 |
| name | string | 是 | 1~64 个 utf8 字符 |
| mobile | string | 否 | 企业内唯一；**mobile / email 不能同时为空**；大陆号码可省略 `+86`，其他地区必须带国际码 |
| email | string | 否 | 6~64 字节，企业内唯一 |
| department | int[] | 否 | 所属部门 id 列表，≤100 个。**不填或为 0 时放到“其他（待设置部门）”；填了不存在的部门会在“待设置部门”下新建同名部门** |
| order | int[] | 否 | 个数必须与 department 一致 |
| is_leader_in_dept | int[] | 否 | 个数必须与 department 一致，1 是负责人 |
| main_department | int | 否 | 主部门 |
| direct_leader | string[] | 否 | 直属上级，最多 1 个 |
| position | string | 否 | 0~128 字符 |
| gender | string | 否 | "1" 男，"2" 女 |
| enable | int | 否 | 1 启用，0 禁用 |
| to_invite | bool | 否 | 是否发邀请，**默认 true**（每天自动下发一次，最多 3 个工作日） |
| extattr | object | 否 | 扩展属性需先在管理端添加，否则**未知属性被忽略** |
| biz_mail / alias / telephone / avatar_mediaid / external_profile / external_position / nickname / address | — | 否 | 见文档 90195 |

```python
wecom_call(contact_tok, "POST", "user/create", json={
    "userid": "zhangsan", "name": "张三", "mobile": "13800000000",
    "department": [2], "main_department": 2, "to_invite": False,
})
```

响应：`{"errcode":0,"errmsg":"created","created_department_list":{"department_info":[{"name":"xxxx","id":123}]}}`
——`created_department_list` 是因为你填了不存在的部门而**自动新建**的部门。看到它通常说明部门 ID 映射错了。

注意：
- 每个部门下的部门 + 成员总数 ≤ 3 万；「建议保证创建department对应的部门和创建成员是串行化处理」。
- `department` 是**数字数组**，写成字符串会 41019（错误码排查原文：“所属部门是数字数组格式，不是字符串”）。
- 常见错误：60102 UserID 已存在、60104 手机号已存在、45024 企业人数达上限。

### 更新成员
**Endpoint**: `POST /cgi-bin/user/update?access_token=ACCESS_TOKEN`
**用途**: 只更新传入的字段。权限同创建。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| userid | string | 是 | 要更新的成员 |
| name / mobile / department / order / position / … | — | 否 | 同创建 |
| biz_mail_alias | object | 否 | `{"item": [...]}`，最多 5 个，**覆盖式更新**，传空会清空 |

注意（文档原文）：
- 「若成员已激活企业微信，则需成员自行修改（此情况下该参数被忽略，**但不会报错**）」——对已激活成员改 mobile 会静默失效。
- userid 由系统自动生成时**仅允许修改一次**，新值用 `new_userid` 指定（其他情况改 userid 报 301036）。
- biz_mail / biz_mail_alias 与其他字段的更新**不具备原子性**，可能部分成功。
- 响应 `{"errcode":0,"errmsg":"updated"}`。

### 删除成员
**Endpoint**: `GET /cgi-bin/user/delete?access_token=ACCESS_TOKEN&userid=USERID`
**用途**: 删除单个成员。注意是 **GET**，不是 DELETE / POST。

- 「若是绑定了腾讯企业邮，则会同时删除邮箱账号」。
- 响应 `{"errcode":0,"errmsg":"deleted"}`。
- 批量删除成员接口（`90199`）本 skill 未抓取正文；错误码排查说“批量删除成员最多指定 200 人”。

## 4. 部门

### 创建部门
**Endpoint**: `POST /cgi-bin/department/create?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | string | 是 | 同一层级不能重名；1~64 个 UTF-8 字符，不能含 `\:*?"<>｜` |
| name_en | string | 否 | 需管理端开启多语言才生效 |
| parentid | int | 是 | 父部门 id，32 位整型；**根部门为 1** |
| order | int | 否 | order 大的排前，[0, 2^32) |
| id | int | 否 | 指定时**必须大于 1**；不填自动生成 |

响应：`{"errcode":0,"errmsg":"created","id":2}`
限制：最多 15 层；部门总数 ≤ 3 万；每个部门下节点 ≤ 3 万。

### 更新部门
**Endpoint**: `POST /cgi-bin/department/update?access_token=ACCESS_TOKEN`
参数：`id`（必填）、`name`、`name_en`、`parentid`、`order`（都可选，**未指定的不更新**）。parentid 不能是自己或子部门（60010 循环关系）。

### 删除部门
**Endpoint**: `GET /cgi-bin/department/delete?access_token=ACCESS_TOKEN&id=ID`
同样是 **GET**。部门下有子部门或成员时能否删除 ⚠ 本次抓取的页面正文未写明，请以实测报错为准。

### 获取子部门ID列表（推荐）
**Endpoint**: `GET /cgi-bin/department/simplelist?access_token=ACCESS_TOKEN&id=ID`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | int | 否 | 获取该部门及其**递归**子部门；不填取全量组织架构 |

响应：`{"errcode":0,"errmsg":"ok","department_id":[{"id":2,"parentid":1,"order":10},{"id":3,"parentid":2,"order":40}]}`
权限：普通自建应用只能拉可见范围内的；**通讯录同步助手可获取企业所有部门 id**。
无凭证探测（2026-09-11）：假 token → `{"errcode":40014,"errmsg":"invalid access_token","department_id":[]}`。

### 获取单个部门详情
**Endpoint**: `GET /cgi-bin/department/get?access_token=ACCESS_TOKEN&id=ID`（id 必填）
返回部门名称、负责人等；通讯录同步助手从新 IP 调用被拒（96079）。

### 获取部门列表（不推荐）
**Endpoint**: `GET /cgi-bin/department/list?access_token=ACCESS_TOKEN&id=ID`
- 文档：「由于该接口性能较低，建议换用获取子部门ID列表与获取单个部门详情」。
- 响应 `department[]`：`id`、`name`、`name_en`、`department_leader`、`parentid`（根部门为 1）、`order`。

## 5. 标签

### 获取标签列表
**Endpoint**: `GET /cgi-bin/tag/list?access_token=ACCESS_TOKEN`
响应：`{"errcode":0,"errmsg":"ok","taglist":[{"tagid":1,"tagname":"a"}]}`
权限：自建应用或通讯录同步助手可获取所有标签；第三方仅自己创建的。

### 获取标签成员
**Endpoint**: `GET /cgi-bin/tag/get?access_token=ACCESS_TOKEN&tagid=TAGID`
响应：`tagname`、`userlist[{userid,name}]`、`partylist[]`；只含应用可见范围内的成员。

### 增加标签成员
**Endpoint**: `POST /cgi-bin/tag/addtagusers?access_token=ACCESS_TOKEN`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| tagid | int | 是 | 标签 ID |
| userlist | **string[]** | 否 | 成员 ID 列表，单次 ≤ 1000；与 partylist 不能同时为空 |
| partylist | **int[]** | 否 | 部门 ID 列表，单次 ≤ 100 |

```python
r = wecom_call(app_tok, "POST", "tag/addtagusers",
               json={"tagid": 12, "userlist": ["user1", "user2"], "partylist": [4]})
if r.get("invalidlist") or r.get("invalidparty"):
    print("部分非法：", r.get("invalidlist"), r.get("invalidparty"))
```

注意：
- **这里是 JSON 数组**；而发应用消息的 `touser` 是 `"user1|user2"` 竖线分隔的字符串（见 `messaging.md`）。错误码 40035 / 40070 排查都点名了“userlist 是数组不是字符串”。
- 部分非法仍返回 `errcode: 0`，附 `invalidlist`（**竖线分隔字符串** `"usr1|usr2"`）和 `invalidparty`（数组）；全部非法才返回 `40070 all list invalid`。
- 「调用的应用必须是指定标签的创建者」，否则 60011 / 81011。每个标签下部门数 + 人数 ≤ 3 万。

## 6. 通讯录变更回调

配置入口：通讯录同步助手在「管理工具 → 通讯录同步 → 设置接收事件服务器」填 URL / Token / EncodingAESKey；代开发应用默认回调。
签名校验、解密、响应规则全部见 `callbacks-crypto.md`。解密后的明文统一形如：

```xml
<xml>
  <ToUserName><![CDATA[toUser]]></ToUserName>
  <FromUserName><![CDATA[sys]]></FromUserName>
  <CreateTime>1403610513</CreateTime>
  <MsgType><![CDATA[event]]></MsgType>
  <Event><![CDATA[change_contact]]></Event>
  <ChangeType>create_user</ChangeType>
  <UserID><![CDATA[zhangsan]]></UserID>
  <Department><![CDATA[1,2,3]]></Department>
</xml>
```

| Event | ChangeType | 说明 |
|---|---|---|
| change_contact | create_user / update_user / delete_user | 成员新增 / 更新 / 删除 |
| change_contact | create_party / update_party / delete_party | 部门新增 / 更新 / 删除 |
| change_contact | update_tag | 标签成员变更 |

注意（文档原文）：
- **2022-08-15 后**通讯录同步助手**新配置或修改**的回调 URL：新增成员事件只回调 `UserID` / `Department`；更新成员事件只在部门相关变更或 UserID 变更时触发，且只带 `UserID` / `Department` / `NewUserId`。
  老 URL 不受影响，但**一旦修改保存回调 URL 就切到新规则**。
- `Department`、`IsLeaderInDept` 在 XML 里是**逗号分隔字符串**（`"1,2,3"`），不是数组。
- 「由通讯录同步助手通过api发起的新增成员触发的事件不回调给通讯录同步助手应用」——自己 API 写入的变更不会回调给自己，别指望靠回调确认写入结果。

## 7. 典型任务：把外部 HR 系统同步到企业微信

1. 用**通讯录同步 token** 调 `department/simplelist`（不传 id）拿全量部门 ID 树，调 `user/list_id` 分页拿全量 userid-部门关系。
2. 和 HR 系统做差集：先建部门（**父部门先于子部门**，串行），再建成员（`department` 用数字数组，`to_invite` 按需关闭），再更新 / 删除。
3. 需要姓名等详情做比对时，不能用通讯录同步 token 从新 IP 读（48009），改用可见范围为全公司的自建应用 token 调 `user/list`。
4. 每步都判 `errcode`；`created_department_list` 非空说明部门映射错了，应回滚排查。
5. 更大规模的全量覆盖可用「异步导入接口」（`batch/replaceuser` 等，文档 90978 分组），本 skill 未抓取正文。
