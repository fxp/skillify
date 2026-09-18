# 自定义菜单：创建、查询、删除、个性化菜单

目录：[1. 创建自定义菜单](#1-创建自定义菜单) · [2. 查询菜单](#2-查询菜单两个接口) · [3. 删除菜单](#3-删除菜单) · [4. 个性化菜单](#4-个性化菜单) · [5. 菜单点击事件推送](#5-菜单点击事件推送) · [6. 注意事项汇总](#6-注意事项汇总)

**除标「无凭证探测」的条目外，行为描述均为文档原文，未实测。**

## 1. 创建自定义菜单

**Endpoint**: `POST /cgi-bin/menu/create`
**用途**: 创建/覆盖公众号的底部自定义菜单（一次调用即覆盖全部，不是增量添加）。

**关键参数**（Request Body，JSON）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| button | array\<object\> | 是 | 一级菜单数组，每项见下表 |

**button 结构**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| type | string | 一级菜单是叶子节点时必填（与 `sub_button` 互斥） | 枚举见下 |
| name | string | 是 | 一级菜单 ≤16 字节，二级菜单 ≤60 字节 |
| key | string | click 类必填 | 事件回传的 key 值，≤128 字节 |
| url | string | view/miniprogram 类必填 | ≤1024 字节 |
| media_id | string | media_id/view_limited 类必填 | 需先用永久素材接口拿到 |
| appid / pagepath | string | miniprogram 类必填 | 小程序 appid **必须小写**（文档原文特别强调） |
| article_id | string | article_id/article_view_limited 类必填 | "发布"系列接口拿到的合法 article_id |
| sub_button | array | 否 | 二级菜单数组，与 `type` 互斥 |

**type 枚举**: `click` / `view` / `scancode_push` / `scancode_waitmsg` / `pic_sysphoto` / `pic_photo_or_album` / `pic_weixin` / `location_select` / `media_id` / `article_id` / `article_view_limited` / `miniprogram`

**示例请求**
```bash
curl -X POST "https://api.weixin.qq.com/cgi-bin/menu/create?access_token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "button": [
      {"type": "click", "name": "今日歌曲", "key": "V1001_TODAY_MUSIC"},
      {"name": "菜单", "sub_button": [
        {"type": "view", "name": "搜索", "url": "https://www.baidu.com"},
        {"type": "miniprogram", "name": "小程序", "url": "https://mp.weixin.qq.com", "appid": "wx286xxxxxx", "pagepath": "pages/index"}
      ]}
    ]
  }'
```

**注意事项**
- **最多 3 个一级菜单，每个一级菜单最多 5 个二级菜单**（文档原文）。
- 字数限制文档有两种口径同时出现：参数表写"不超过 16/60 个字节"，说明文字写"一级菜单最多 4 个汉字，二级菜单最多 8 个汉字，多出来的部分将会以...代替"——**按字节数（UTF-8 下一个汉字 3 字节）折算，16 字节 ≈ 5 个汉字、60 字节 ≈ 20 个汉字，和"4 个汉字/8 个汉字"的口径对不上**，`⚠ 文档自相矛盾`，未做真实调用验证哪个是准确上限，先按更严格的"4 个汉字/8 个汉字"设计文案，避免创建成功但客户端截断显示。
- 创建后菜单**不会立即在客户端生效**：用户进入公众号会话页/profile 页时，若上次拉取菜单距今超过 5 分钟才会重新拉取；测试时可尝试取消关注再重新关注来立即看到效果。
- `type` 与 `sub_button` 互斥：填了 `sub_button` 就不能再填 `type`（该菜单项变成纯目录，不可点击触发事件）。

## 2. 查询菜单（两个接口）

**Endpoint A**: `GET /cgi-bin/menu/get` — 查"用接口创建的"菜单结构
**Endpoint B**: `GET /cgi-bin/get_current_selfmenu_info` — 查"当前实际生效"的菜单

**关键区别**（文档原文）：如果公众号菜单是通过 API 设置的，`get_current_selfmenu_info` 返回的是这份"开发配置"；**如果菜单是运营者直接在公众平台官网用可视化编辑器发布的，`menu/get` 查不到（或查到的是旧的 API 配置），要用 `get_current_selfmenu_info` 才能看到网站发布的最新菜单**——两个接口不能互相替代，混用会读到过期或错误的菜单结构。

**示例响应**（`get_current_selfmenu_info`）
```json
{"is_menu_open": 1, "selfmenu_info": {"button": [{"type": "view", "name": "...", "url": "...", "sub_button": {"list": []}}]}}
```

**注意事项**
- `is_menu_open=0` 表示菜单当前未开启，此时 `selfmenu_info` 可能为空，先判断这个字段再读菜单结构。

## 3. 删除菜单

**Endpoint**: `GET /cgi-bin/menu/delete`
**用途**: 删除当前使用中的自定义菜单（全部删除，不支持删单个一级菜单项）。无请求体，只需 `access_token`。

## 4. 个性化菜单

**用途**: 让不同用户群体（按标签或客户端平台）看到不一样的菜单，在默认菜单之外叠加匹配规则。

| 操作 | Endpoint | 关键参数 |
| --- | --- | --- |
| 创建个性化菜单 | `POST /cgi-bin/menu/addconditional` | `button`（1-3 个一级菜单，结构同第 1 节）、`matchrule` |
| 删除个性化菜单 | `POST /cgi-bin/menu/delconditional` | `menuid`（创建时返回的菜单 ID） |
| 测试匹配结果 | `POST /cgi-bin/menu/trymatch` | `user_id`（openid 或微信号），返回该用户会命中哪个菜单 |

**matchrule 结构**（至少一个非空字段，文档原文）
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| tag_id | string | 用户标签 ID（见 `users.md` 第 4 节） |
| client_platform_type | string | 客户端类型：`1`=iOS，`2`=Android，`3`=Others |

**注意事项**
- 个性化菜单是在默认菜单（第 1 节）之上叠加的匹配规则，不是替代默认菜单；建议改动前先用 `trymatch` 确认命中结果，避免线上误配置影响全部用户。
- `⚠ 文档未说明`：多条个性化菜单规则同时匹配同一用户时的优先级如何判定，文档未给出，实现前建议先用 `trymatch` 对目标用户群实测确认，不要假设"后创建的优先"或"先创建的优先"。

## 5. 菜单点击事件推送

用户点击自定义菜单后，微信通过回调 URL 推送事件（点击子菜单目录本身不产生事件推送）。

| Event | 触发菜单 type | 关键字段 |
| --- | --- | --- |
| `CLICK` | `click` | `EventKey` = 创建菜单时填的 `key` |
| `VIEW` | `view` | `EventKey` = 创建菜单时填的 `url` |
| `scancode_push` / `scancode_waitmsg` 等 | 对应 type | 触发客服消息配额，见 `messaging.md` 第 3 节 |

**注意事项**
- 第 3～8 种菜单类型（扫码、拍照发图等）仅在 iPhone 5.4.1+ / Android 5.4+ 客户端生效，旧版本点击无响应也无事件推送（文档原文，`menu.md`/`messaging.md` 共同适用）。

## 6. 注意事项汇总

- `menu/create` 是整体覆盖，不是增量更新；要改一个按钮也要把全部 `button` 数组重新提交一遍。
- 查询菜单要认清 `menu/get`（API 配置）与 `get_current_selfmenu_info`（实际生效，兼容官网发布的菜单）的区别。
- 个性化菜单叠加规则、多规则命中优先级未在文档中说明，先用 `trymatch` 验证再上线。
- 小程序类型按钮的 `appid` 必须小写。
