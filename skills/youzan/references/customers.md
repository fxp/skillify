# 客户、会员、积分与标签

内容整理自 https://doc.youzanyun.com/ （抓取于 2026-09-11）。**未用真实凭证验证**，本文件没有探测结论，
错误码与行为描述都是「文档原文，未实测」。调用格式见 `auth-token.md` 第 4 节。

## 目录
1. 名词与 ID：yz_open_id 是主键；account_type 有两套写法
2. 手机号 → yz_open_id `youzan.user.basic.get.3.0.1`
3. 创建客户 `youzan.scrm.customer.create.3.0.0`
4. 更新客户 `youzan.scrm.customer.update.3.0.0`
5. 查询客户详情 `youzan.scrm.customer.detail.get.1.0.1`
6. 搜索客户 `youzan.scrm.customer.list.1.0.0` / 按手机号批量 `youzan.scrm.customer.list.phone.1.0.0`
7. 积分：查询 / 加 / 减
8. 给客户打标签 `youzan.scrm.tag.relation.add.4.0.0`
9. 双向同步：消息、防回环、数据中心
10. ⚠ 本文件的文档矛盾 / 未说明

---

## 1. 名词与 ID

- **用户**是平台级（所有有赞账号），**客户**是商家级（关注公众号、访问店铺、下单、导入等都会成为某商家的客户），**会员**是有会员等级或会员卡的客户（会员概述页）。
- 主键用 **`yz_open_id`**（有赞对外统一 openId）。`fans_id` / `fans_type` / `buyer_id` 在多个接口里已标废弃；`user_id`、`yz_uid`、`account_id` 都是账号 id（常见参数页 3028）。
- **`account_type` 有两套写法，接口之间不通用**：

| 接口 | account_type 类型 | 取值 |
|---|---|---|
| `scrm.customer.detail.get`（`account_info.account_type`）、`crm.customer.points.*`（`user.account_type`） | **Integer** | 1 有赞粉丝 id；2 手机号；3 三方帐号（App 开店的 open_user_id）；5 yz_open_id（推荐） |
| `scrm.tag.relation.add`、`scrm.customer.update`（`account.account_type`）、`customer.create` 响应 | **String** | `FansID`、`Mobile`、`YouZanAccount`、`OpenUserId`、`WeiXinOpenId`、`YzOpenId` |

  把 `"Mobile"` 传给积分接口，或把 `2` 传给打标接口，都会参数错误。`account_id` 一律传**字符串**（传数字可能 5001，FAQ 33694）。

## 2. 手机号 → yz_open_id

**Endpoint**: `POST /api/youzan.user.basic.get/3.0.1`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| mobile | String | 二选一 | 手机号 |
| country_code | String | 否 | 如 `+86` |
| yz_open_id | String | 二选一 | 反查用户简要信息 |

响应 `data`：`yz_open_id`、`avatar`、`nick_name`、`mobile`。
另有 `youzan.users.info.query`（FAQ 4946、客户会员场景页推荐，可一并拿到微信 openid、union_id）→ 两份 FAQ 推荐不同接口，⚠ 文档自相矛盾（未说明差异）。

## 3. 创建客户

**Endpoint**: `POST /api/youzan.scrm.customer.create/3.0.0`（建议单店 QPS 200）
**用途**: 把三方系统里**有手机号**的客户同步到有赞。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| mobile | String | 是 | 手机号（11 位，否则 `141500101 invalid params`） |
| country_code | String | 否 | 默认 `+86` |
| is_mobile_auth | Boolean | 否 | 是否授权手机号，默认 false |
| customer_create.name | String | 否 | 姓名 |
| customer_create.gender | Short | 否 | 0 未知、1 男、2 女 |
| customer_create.birthday | String | 否 | `yyyy-MM-dd HH:mm:ss` |
| customer_create.remark | String | 否 | 备注 |
| customer_create.ascription_kdt_id | Long | 否 | 归属分店（连锁） |
| customer_create.wei_xin / outer_card_no | String | 否 | 微信号 / 外部卡号 |
| customer_create.contact_address | object | 否 | 地区信息 |
| label_info.src_way / src_channel | Integer | 否 | 来源方式（2008 系统打通）/ 来源渠道（2000 三方门店） |

```bash
curl -X POST "https://open.youzanyun.com/api/youzan.scrm.customer.create/3.0.0?access_token=$YOUZAN_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"mobile":"13800000000","customer_create":{"name":"张三","gender":1,"birthday":"1990-01-01 00:00:00"}}'
```
响应 `data`：`account_id`、`account_type`（**字符串**，如 `YouZanAccount`）、`yz_open_id`。
- 已存在 → `143001027 customer already exist`（场景页另写 `141502109`）：同步时把它当“成功，改走 update”。
- 连锁：总店 token 不传归属分店 → 客户算总店；传了 → 属于该分店；网店 token 无论传不传都属于网店。
- 自定义资料项相关错误 `141502130`~`141502134`。

## 4. 更新客户

`POST /api/youzan.scrm.customer.update/3.0.0`（参数表未抓取，以下来自 FAQ 5081 的示例请求）：
```json
{"customer_update": {"birthday": "1988-02-29", "gender": 1, "name": "李沛伦", "remark": "没有啥",
                     "contact_address": {"address": "新风南里", "area_code": 518001}},
 "account": {"account_id": "15252364036", "account_type": "Mobile"}}
```
- 注意这里的 `account_type` 是字符串 `Mobile`，生日示例是 `yyyy-MM-dd`（创建接口写 `yyyy-MM-dd HH:mm:ss`）→ ⚠ 文档未说明两种格式是否都接受。
- 客户变更消息里带 `external_request_id`，对应本接口传入的同名参数（可用于识别自己触发的更新）→ 参数位置 ⚠ 文档未说明。

## 5. 查询客户详情

**Endpoint**: `POST /api/youzan.scrm.customer.detail.get/1.0.1`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| yz_open_id | String | 表中标“是” | 推荐 |
| account_info.account_type | Integer | 表中标“是” | 1 粉丝 id、2 手机号、5 yz_open_id |
| account_info.account_id | String | 表中标“是” | |
| fields | String | 是 | 逗号分隔：`user_base`、`tags`、`benefit_cards`、`benefit_level`、`benefit_rights`、`credit`（积分）、`behavior`、`giftcard`、`prepaid`、`coupon`、`level`、`auth_info` |
| is_do_ext_point | Boolean | 否 | 默认 true，会触发“查询客户详细信息”扩展点 |

参数表把 `yz_open_id` 和 `account_info` 都标为必填，但说明写“yz_open_id 和帐号 ID 不能同时为空” → ⚠ 文档自相矛盾；传 yz_open_id 并同时给 `account_info={account_type:5, account_id:同一个 yz_open_id}` 最稳。

```python
d = call("youzan.scrm.customer.detail.get", "1.0.1", {
    "yz_open_id": yz_open_id,
    "account_info": {"account_type": 5, "account_id": yz_open_id},
    "fields": "user_base,tags,credit,level",
}, kdt_id=kdt_id)
```
响应 `data`：`name`、`mobile`、`mobile_country_code`、`gender`（1 男、2 女）、`show_name`、`created_at`、`updated_at`、`member_created_at`、`outer_card_no`、`cards[]`… 以及按 fields 返回的积分、标签等。
- `created_at` 描述是“Unix 时间戳，单位：秒”，示例值 `1594296126604` 是 13 位（毫秒）→ ⚠ 文档自相矛盾，按位数判断。
- 错误：`141001107` 客户不存在、`144100000` 不是该店铺客户（先 create）、`144100001` 客户不存在或已注销、`141500101` 参数错误。

## 6. 搜索客户 / 按手机号批量查

**`youzan.scrm.customer.list.1.0.0`**（按创建时间降序；拉历史存量用它，增量接消息）

| 参数 | 类型 | 说明 |
|---|---|---|
| is_member | Short | 0 非会员、1 会员，不传查全部 |
| created_at_start / created_at_end | Long | 成为客户时间，**秒级时间戳** |
| created_member_at_start / _end | Long | 成为会员时间，秒 |
| tag_ids | List<Long> | 标签 id |
| has_mobile | Boolean | 是否有手机号 |
| page_no | Integer | 最多 500 页 |
| page_size | Integer | 最多 50 |

- 总量上限 **10000 条**（超出 `142710032 超过列表获取总数`）→ 按 `created_at_*` 切窗口拉。
- 响应 `data.total`、`data.record_list[]`：`yz_open_id`、`name`、`mobile`、`is_member`、`points`、`trade_count`、`created_at`（秒）、`is_mobile_auth`。
- 页数与每页的描述：“最多支持500页(以每页默认值20为单位，客户查询最大为10000)”与 page_size 上限 50 并存 → ⚠ 文档未说明 page_size=50 时是否仍可翻 500 页（以 10000 总量为准）。

**`youzan.scrm.customer.list.phone.1.0.0`**：`phones`（List<String>，一次最多 50 个）→ 返回 `yz_open_id`、`created_time` 等。
**`youzan.scrm.customer.list.yzopenid.1.0.0`**：按 `yz_open_ids` 批量查（llms 摘要）。

## 7. 积分

| 动作 | API | 请求体形状 |
|---|---|---|
| 查当前积分 | `youzan.crm.customer.points.get.1.0.0` | `{"user": {"account_id": "...", "account_type": 5}}`（顶层 user） |
| 加积分 | `youzan.crm.customer.points.increase.4.0.0` | `{"params": {"user": {...}, "points": 10, "reason": "...", "biz_value": "...", "biz_token": "..."}}`（**包在 params 里**） |
| 减积分 | `youzan.crm.customer.points.decrease.4.0.0` | 同上 |

加 / 减积分参数（`params.*`）：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| user.account_id | String | 是 | 账号 id |
| user.account_type | Integer | 是 | 1 / 2 / 3 / 5（5 = yz_open_id，推荐） |
| points | Integer | 是 | 变动值（正数） |
| reason | String | 是 | 变动原因（为空 → `141503112`） |
| biz_value | String | 否 | 业务唯一标识（如订单号） |
| biz_token | String | 否 | 同一 biz_value 下多次操作的区分（如同一订单多次退款） |
| is_do_ext_point | Boolean | 否 | 默认 true 走扩展点 |
| check_customer | Boolean | 否 | 默认 false |
| source_kdt_id | Long | 否 | 积分变更店铺 |
| created_at | String | 否 | 必须小于当前时间，`yyyy-MM-dd HH:mm:ss` |

- **幂等**：加积分以 `account_id + biz_value + biz_token` 生成幂等键，重复请求只加一次；减积分“相同唯一标识只扣一次”。重复命中 → `142100106 重复操作`，按成功处理。**所以 biz_value / biz_token 一定要传且稳定**，否则重试会重复加分。
- 连锁店铺**只能用总部**加减积分，网店 / 门店 → `142100002 暂无操作权限`。
- 用户从未有过积分时减积分 → `142100103 账面不存在`；`141503101 user not exists`。
- 响应 `data.is_success` 是**字符串** `"true"` / `"false"`（文档：“兼容 Iron 此为 string”）。
- 限流页列的是 3.1.0 旧版（100 次/秒/店）；4.0.0 → ⚠ 文档未说明。同一客户并发过高 → `141500203 api rate limiting`。

```python
def add_points(call, kdt_id, yz_open_id, points, order_no, reason, seq="0"):
    res = call("youzan.crm.customer.points.increase", "4.0.0", {"params": {
        "user": {"account_id": yz_open_id, "account_type": 5},
        "points": int(points), "reason": reason,
        "biz_value": order_no, "biz_token": f"{order_no}:{seq}",   # 稳定的幂等键
    }}, kdt_id=kdt_id)
    return str(res.get("is_success")).lower() == "true"
```

## 8. 给客户打标签

**Endpoint**: `POST /api/youzan.scrm.tag.relation.add/4.0.0`（建议单店 **5 次/秒**）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| account_type | String | 是 | `FansID` / `Mobile` / `YouZanAccount` / `OpenUserId` / `WeiXinOpenId` / `YzOpenId` |
| account_id | String | 是 | 账号 id |
| tags[].tag_name | String | 是 | 标签名，≤ 32 字符；单次最多 20 个；**标签不存在会自动创建** |

```json
{"account_type": "YzOpenId", "account_id": "LnhGm4rh576452722916618240", "tags": [{"tag_name": "高价值"}]}
```
响应 `data` 为 Boolean；`142400105` 客户不存在 / 打标失败。删除未分组标签用 `youzan.scrm.tag.relation.delete.4.0.0`（单次最多 20 个）。
新体系推荐“分组标签”（可同步企微），接口是 `youzan.scrm.tag.category.*` / `youzan.scrm.tag.template.*`（本 skill 不展开）。

## 9. 双向同步：消息、防回环、数据中心

- 客户增量：订阅 `SCRM_CUSTOMER_EVENT`（status `CUSTOMER_CREATED` / `CUSTOMER_UPDATED`，msg 需 urldecode，含 `mobile`、`is_member`、`src`、`is_log_off` 注销标记）。客户来源 `src`：100 关注公众号、200 普通下单、300 后台批量导入、400 后台新建或接口创建。
- 积分增量：订阅 `POINTS`；msg 里 **`client_hash` = md5(client_id)**，为空表示非第三方操作；等于你自己 client_id 的 md5 就是**你自己调接口造成的变动**，同步回自有系统时要跳过，否则会形成回环（积分场景页）。有容器积分扩展点产生的变动不推送。
- 积分双向同步先定**唯一数据中心**：文档给了五种方案，并明确“双向加积分可能引起资损”；**扣减积分不可异步**（否则可能资损），加积分可以异步。建议定期全量对账。
- 客户合并 `OPEN_PUSH_SCRM_MEMBER_MERGE`、手机号变更 `OPEN_PUSH_SCRM_MEMBER_MOBILE_CHANGE`：维护映射表时要订阅（llms 摘要）。

## 10. ⚠ 本文件的文档矛盾 / 未说明

- 手机号换 yz_open_id：`user.basic.get` vs `users.info.query` → ⚠ 文档自相矛盾
- `customer.detail.get` 的必填项（yz_open_id 与 account_info 都标必填又说不能同时为空）；`created_at` 秒 vs 13 位示例 → ⚠ 文档自相矛盾
- `customer.update` 完整参数表未收录；生日格式 `yyyy-MM-dd` vs `yyyy-MM-dd HH:mm:ss` → ⚠ 文档未说明
- 客户已存在错误码 `143001027`（接口页）vs `141502109`（场景页）→ ⚠ 文档自相矛盾，两个都按“已存在”处理
- 积分 4.0.0 接口 QPS → ⚠ 文档未说明
- `customer.list` 页数上限与 page_size 的关系 → ⚠ 文档未说明
