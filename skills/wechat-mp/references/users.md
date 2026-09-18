# 用户管理：关注者列表、用户信息、标签、黑名单

目录：[1. 获取关注用户列表](#1-获取关注用户列表) · [2. 获取用户基本信息（单个/批量）](#2-获取用户基本信息单个批量) · [3. 设置备注名](#3-设置备注名) · [4. 标签管理](#4-标签管理) · [5. 黑名单管理](#5-黑名单管理) · [6. 转换 openid（账号迁移）](#6-转换-openid账号迁移) · [7. UnionID 机制](#7-unionid-机制) · [8. 注意事项汇总](#8-注意事项汇总)

**除标「无凭证探测」的条目外，行为描述均为文档原文，未实测。**

所有接口鉴权方式一致：URL 查询参数 `access_token=ACCESS_TOKEN`（见 `auth.md`）。

## 1. 获取关注用户列表

**Endpoint**: `GET /cgi-bin/user/get`
**用途**: 分页拉取账号全部关注者的 openid 列表（只有 openid，没有昵称等信息，需要再配合第 2 节接口取详情）。

**关键参数**（Query String）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| access_token | string | 是 | 接口调用凭据 |
| next_openid | string | 否 | 上一批列表的最后一个 openid；不填默认从头拉取 |

**示例响应**
```json
{
  "total": 2,
  "count": 2,
  "data": {"openid": ["OPENID1", "OPENID2"]},
  "next_openid": "OPENID2"
}
```

**注意事项**
- `count` 单批最大 10000（文档原文）；超过则需拿 `next_openid` 翻页，直到返回的 `count` 小于请求上限或 `next_openid` 为空。
- 只返回 openid，不含昵称/头像等信息；要展示用户资料需要再调第 2 节接口逐个或批量取。

## 2. 获取用户基本信息（单个/批量）

**Endpoint**: `GET /cgi-bin/user/info`（单个）、`POST /cgi-bin/user/info/batchget`（批量）
**用途**: 用 openid 换取用户的关注状态、语言、关注时间、备注、分组、unionid 等资料。

**关键参数**——单个（Query String）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| access_token | string | 是 | 接口调用凭据 |
| openid | string | 是 | 用户 openid |
| lang | string | 否 | 返回语言，默认未说明 |

**关键参数**——批量（Request Body，JSON）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| user_list | array\<object\> | 是 | 每项含 `openid`、可选 `lang` |

**示例响应**（单个，字段来自文档）
```json
{
  "subscribe": 1,
  "openid": "OPENID",
  "subscribe_time": 1716000000,
  "unionid": "UNIONID",
  "remark": "",
  "groupid": 0
}
```

**注意事项**
- `subscribe=0` 表示用户当前未关注，此时**拉取不到其余信息**（文档原文）——不要假设有 openid 就一定能拿到昵称等字段。
- 响应里的 `language` 字段文档标注**"该字段不再提供"**，不要依赖它判断用户语言。
- `unionid` 字段**只有账号绑定了微信开放平台账号后才会出现**，见第 7 节；没绑定时响应里不含该字段（不是空字符串，是键缺失）。
- 若用户曾多次关注又取关，`subscribe_time` 取最后一次关注时间（文档原文）。

## 3. 设置备注名

**Endpoint**: `POST /cgi-bin/user/info/updateremark`
**用途**: 公众号运营者给粉丝加备注（只有运营者自己能看到，不是给用户看的昵称）。

**关键参数**（Request Body）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| openid | string | 是 | 用户 openid |
| remark | string | 是 | 新备注名，长度须小于 30 字节 |

## 4. 标签管理

**用途**: 对公众号自己创建的标签做增删改查，以及给用户批量打标签/取消标签、按标签拉用户。

| 操作 | Endpoint | 关键参数（Request Body） |
| --- | --- | --- |
| 创建标签 | `POST /cgi-bin/tags/create` | `tag.name`（≤30 字符） |
| 获取标签列表 | `GET /cgi-bin/tags/get` | 无 |
| 修改标签名 | `POST /cgi-bin/tags/update` | `tag.id`、`tag.name` |
| 删除标签 | `POST /cgi-bin/tags/delete` | `tag.id` |
| 按标签拉用户 openid | `POST /cgi-bin/user/tag/get` | `tagid`、`next_openid`（分页） |
| 批量打标签 | `POST /cgi-bin/tags/members/batchtagging` | `openid_list`（**最多 50 个**）、`tagid` |
| 批量取消标签 | `POST /cgi-bin/tags/members/batchuntagging` | `openid_list`、`tagid` |
| 查用户所属标签 ID 列表 | `POST /cgi-bin/tags/getidlist` | `openid` |

**示例请求**（批量打标签）
```python
requests.post(
    "https://api.weixin.qq.com/cgi-bin/tags/members/batchtagging",
    params={"access_token": access_token},
    json={"openid_list": openids[:50], "tagid": tagid},
)
```

**注意事项**
- `batchtagging` 每次最多 50 个 openid（文档原文，明确写在参数说明里）；`batchuntagging` 的参数说明没重复这个上限，`⚠ 文档未说明` 是否同样限 50，按 50 一批处理更安全。
- 标签 ID (`tagid`/`id`) 由微信分配，不是自己起的字符串；创建后从响应里取。

## 5. 黑名单管理

**Endpoint**: `POST /cgi-bin/tags/members/getblacklist`（查）、`POST /cgi-bin/tags/members/batchblacklist`（拉黑）、`POST /cgi-bin/tags/members/batchunblacklist`（取消拉黑）

**关键参数**
| 接口 | 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| 查黑名单 | begin_openid | string | 否 | 起始 openid，为空从头拉取（同关注列表的翻页方式） |
| 拉黑 | openid_list | array | 是 | 需要拉黑的 openid 列表 |
| 取消拉黑 | openid_list | array | 是 | 需要取消拉黑的 openid 列表 |

**注意事项**
- 黑名单路径前缀是 `/cgi-bin/tags/members/...`，容易被当成标签接口误读——它和"标签"没有直接关系，只是路径共用了 `tags/members` 前缀。
- 文档未说明黑名单用户是否仍计入"关注用户列表"（第 1 节）的 `total`，标 `⚠ 文档未说明`。

## 6. 转换 openid（账号迁移）

**Endpoint**: `POST /cgi-bin/changeopenid`
**用途**: 公众号/服务号账号迁移后，原账号关注用户的 openid 会变化；用这个接口把旧账号的 openid 批量转换成新账号的 openid。

**注意事项**
- 仅账号迁移审核完成后可调用，**最多保留 15 天**，超期接口失效（文档原文）。
- 原账号为个人主体的不支持此接口。
- **必须在原账号被冻结之前**（最好在提交迁移审核前）就拿到原账号的用户列表，一旦原账号被回收就无法再获取。
- 迁移未完成时调用无返回结果或报错（文档原文，未说明具体错误码，`⚠ 文档未说明`）。

## 7. UnionID 机制

同一个微信用户在不同公众号下的 `openid` 不同；如果开发者名下有多个公众号，或需要打通公众号、小程序、移动应用之间的用户账号体系，要先在微信开放平台（`open.weixin.qq.com`）把这些账号绑定到同一个开放平台账号下，绑定后各账号返回的用户信息里才会带上同一个 `unionid`。这是跨账号识别同一用户的唯一途径，不能靠比较 openid。

## 8. 注意事项汇总

- 判空技巧：`subscribe=0` 时不要读其余字段；`unionid` 未绑定开放平台账号时字段直接不存在。
- 批量接口（打标签、拉黑）都要注意 `openid_list` 的条数上限；没写明上限的（取消打标签、取消拉黑）按同一量级处理，不要假设无限制。
- 涉及用户列表的接口全部走"游标翻页"（`next_openid`/`begin_openid`），不是 `page`/`limit` 式分页，遍历时要用响应里返回的游标继续下一页，而不是自己递增页码。
