# 模板消息 与 订阅通知：三套并存机制的选型与调用

目录：[1. 三套机制怎么选](#1-三套机制怎么选) · [2. 模板消息（旧，仍在用）](#2-模板消息旧仍在用) · [3. 订阅通知（新，推荐）](#3-订阅通知新推荐) · [4. 一次性订阅消息（更旧，授权链接型）](#4-一次性订阅消息更旧授权链接型) · [5. 注意事项汇总](#5-注意事项汇总)

**除标「无凭证探测」的条目外，行为描述均为文档原文，未实测。**

## 1. 三套机制怎么选

微信服务号文档目前（抓取时）同时存在三套"服务号主动推送非客服消息给用户"的机制，官方原文在模板消息页顶部写着**"服务号订阅通知功能开启灰度测试，模板消息能力可正常使用"**——即新旧两套目前并行，具体某个账号看到哪套取决于灰度进度，写代码前先去账号后台"功能"页确认实际开放的能力，不要假设。

| 机制 | 触发前提 | 频率限制 | 发送接口 | 何时用 |
| --- | --- | --- | --- | --- |
| **模板消息**（第 2 节） | 服务号需认证，申请行业类目、从公共库选模板 | 账号级：日调用上限（默认较高，无强制单次限制） | `POST /cgi-bin/message/template/send` | 传统"服务通知"场景，如信用卡刷卡、购买成功通知；不需要用户额外操作 |
| **订阅通知**（第 3 节，推荐） | 用户需在图文/网页里主动点击订阅组件完成授权 | 一次性：授权一次发一条；长期：仅开放政务民生/医疗等公共服务类目 | `POST /cgi-bin/message/subscribe/bizsend` | 官方主推的新机制，模板消息的替代方向 |
| **一次性订阅消息**（第 4 节，更旧） | 用户需跳转 `mp.weixin.qq.com` 专属授权链接完成单次订阅 | 单次授权只能发一条，同一用户同一 `scene` 多次授权不叠加 | `POST /cgi-bin/message/template/subscribe` | 历史遗留集成，新项目不建议再接 |

三者互不通用：模板消息用的 `template_id` 来自模板消息自己的模板库（`get_industry`/`add_template` 体系），订阅通知和一次性订阅消息各自也有自己的模板/授权体系，**同一个 `template_id` 不能跨机制使用**。

## 2. 模板消息（旧，仍在用）

**核心接口**: `POST /cgi-bin/message/template/send`
**用途**: 面向已关注用户发送服务类通知，不支持营销/广告类内容。

**使用规则**（文档原文）
- 只有**已认证**服务号才能申请模板消息使用权限。
- 需先申请合适的服务类目（见 `references/template-subscribe.md` 第 1 节的类目页链接），**每个账号最多设置 5 个类目，每月最多改 5 次**；改类目或删类目会连带删除该类目下已选用的模板。
- 选类目后从公共模板库选用模板，**每个账号可同时使用 25 个模板**。
- 日调用上限默认 10 万次，账号粉丝数达到 10W/100W/1000W 会相应提升（以账号后台实际数字为准）。
- 模板参数键名规则：**模板中的参数内容必须以 `.DATA` 结尾，否则视为保留字**（文档原文，这是模板消息独有的约定，订阅通知的键名约定不同，见第 3 节）。

**关键参数**（Request Body，JSON）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| touser | string | 是 | 接收者 openid |
| template_id | string | 是 | 模板 ID |
| url | string | 否 | 点击跳转链接；和 `miniprogram` 都不填则不跳转，都填则优先跳小程序 |
| miniprogram.appid / miniprogram.pagepath | string | 否 | 跳小程序时填写 |
| data | object | 是 | 形如 `{"key1": {"value": any}, "key2": {"value": any}}` |
| client_msg_id | string | 否 | 幂等 ID，**同一 openid + client_msg_id 10 分钟内只发一条**，超过 10 分钟不保证去重效果 |

**示例请求**
```bash
curl -X POST "https://api.weixin.qq.com/cgi-bin/message/template/send?access_token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "touser": "OPENID",
    "template_id": "TEMPLATE_ID",
    "url": "https://example.com/order/123",
    "data": {"first": {"value": "您的订单已发货"}, "keyword1": {"value": "京东快递"}}
  }'
```

**发送结果事件推送**（回调 `MsgType=event`，`Event=TEMPLATESENDJOBFINISH`）
| Status | 含义 |
| --- | --- |
| `success` | 送达成功 |
| `failed:user block` | 用户设置了拒收服务号消息，送达失败 |
| `failed:system failed` | 其他原因失败 |

**注意事项**
- `client_msg_id` 的去重窗口只有 **10 分钟**，不是永久幂等；超过 10 分钟的重复请求会被当作新消息发送。
- 海外账号没有 `url` 跳转能力（文档原文）。
- `TEMPLATESENDJOBFINISH` 事件里的 `errcode`/`Status` 才是真正的送达结果，调用 `send` 本身返回 `errcode=0` 只代表"任务已受理"，不代表已送达。

## 3. 订阅通知（新，推荐）

**核心接口**: `POST /cgi-bin/message/subscribe/bizsend`（文档原文标注的用途路径，另见接口列表 `/cgi-bin/message/subscribe/bizsend`）
**用途**: 官方主推的新机制。用户需要先在图文消息或网页里主动点击"订阅通知组件"完成授权，公众号才能按需下发。

**接口列表**
| 接口名称 | Endpoint |
| --- | --- |
| 获取类目 | `GET /wxaapi/newtmpl/getcategory` |
| 获取类目下公共模板 | `GET /wxaapi/newtmpl/getpubtemplatetitles` |
| 获取模板关键词列表 | `GET /wxaapi/newtmpl/getpubtemplatekeywords` |
| 选用模板到私有库 | `POST /wxaapi/newtmpl/addtemplate` |
| 获取已选用模板列表 | `GET /wxaapi/newtmpl/gettemplate` |
| 删除私有模板 | `POST /wxaapi/newtmpl/deltemplate` |
| 发送订阅通知 | `POST /cgi-bin/message/subscribe/bizsend` |

**两种订阅类型**（文档原文，这是本节最容易和"模板消息"或"一次性订阅消息"搞混的地方）
- **一次性订阅**：用户订阅一次，公众号可以不限时间地下发**一条**对应通知。
- **长期订阅**：用户订阅一次，公众号可以长期多次下发；**仅向政务民生、医疗等公共服务领域开放**，普通账号申请不到长期订阅类目。

**接入步骤**（文档原文）
1. 服务号后台"添加功能插件"开通订阅通知。
2. 按账号所属行业申请合适的服务类目。
3. 在公共模板库选用合适的订阅通知模板到私有库。
4. 在图文消息（每篇最多插入 10 个订阅通知组件，每个组件最多 5 条通知，**且一个组件不能同时包含一次性订阅和长期订阅**）或网页（需配合开放标签能力，仅限 JS 安全域名，已认证账号最多配置 5 个安全域名）里插入订阅组件，供用户点击订阅。
5. 用户点击并允许弹窗后即完成订阅；开发者调用发送接口下发。

**关键参数**（`bizsend`，Request Body，JSON）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| touser | string | 是 | 接收者 openid |
| template_id | string | 是 | 订阅通知模板 ID（来自本节模板库，**不是模板消息的 template_id**） |
| page | string | 否 | 点击后跳转的页面（限本账号关联小程序内页面），不填则不跳转 |
| data | object | 是 | 形如 `{"phrase3": {"value": "审核通过"}, "name1": {"value": "订阅"}, "date2": {"value": "2019-12-25 09:42"}}` |
| miniprogram_state | string | 是 | `developer` / `trial` / `formal`（正式版），默认 formal |
| lang | string | 是 | `zh_CN`/`en_US`/`zh_HK`/`zh_TW`，默认 zh_CN |

**注意事项**
- `data` 里的键名示例是 `phrase3`/`name1`/`date2` 这种**不带 `.DATA` 后缀**的裸键名，和第 2 节模板消息"参数键必须以 `.DATA` 结尾"的规则不同——**两套机制的键名约定不一样，照抄模板消息的键名格式到订阅通知会不生效**（`⚠ 文档未说明`：文档没有明确解释为什么两者不同，只是示例呈现方式不一致，未做真实调用验证具体后果，先按各自示例的字面格式实现）。
- `miniprogram_state`/`lang` 是**必填**参数（不是可选），即使不跳小程序也要传（文档原文明确标"是"）。
- 长期订阅资格由类目决定，不是接口参数可以指定的，普通电商/服务类账号即使传了长期订阅的 `template_id` 大概率也申请不到对应类目。

## 4. 一次性订阅消息（更旧，授权链接型）

**用途**: 通过引导用户打开一个 `mp.weixin.qq.com` 专属授权链接来换取"一次"下发权限，机制上早于第 3 节的订阅通知组件方案。文档原文标注"服务号一次性订阅消息能力可正常使用"，但已被第 3 节机制事实上取代，新项目不建议再接。

**第一步：引导用户打开授权链接**
```
https://mp.weixin.qq.com/mp/subscribemsg?action=get_confirm&appid=APPID&scene=1000&template_id=TEMPLATE_ID&redirect_url=ENCODED_URL&reserved=RANDOM#wechat_redirect
```
| 参数 | 必填 | 说明 |
| --- | --- | --- |
| action | 是 | 固定填 `get_confirm` |
| appid | 是 | 服务号 AppID |
| scene | 是 | 0–10000 的整型订阅场景值；**同一用户在同一 `scene` 下多次授权不叠加，只能下发一条，要多条需要用不同 `scene`** |
| template_id | 是 | 一次性订阅消息的模板 ID（后台接口权限列表可查） |
| redirect_url | 是 | 授权后跳转地址，需 UrlEncode，域名要和登记的业务域名一致（不能带路径） |
| reserved | 否 | 防 CSRF 用的随机值，原样带回 |
| #wechat_redirect | 是 | 必须带 |

用户同意/取消后跳转到 `redirect_url/?openid=OPENID&template_id=TEMPLATE_ID&action=confirm|cancel&scene=SCENE&reserved=RESERVED`。

**第二步：发送**
**Endpoint**: `POST /cgi-bin/message/template/subscribe`
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| touser | string | 是 | 用户 openid（来自第一步回调的 `openid`） |
| template_id | string | 是 | 与授权链接一致的模板 ID |
| url | string | 否 | 跳转链接，**需 ICP 备案** |
| miniprogram | object | 否 | 跳小程序配置 |
| scene | string | 是 | 与授权时一致的场景值 |
| title | string | 是 | 消息标题，**15 字以内** |
| data | object | 是 | 消息内容 |

**注意事项**
- 每授权一次只能下发一条；要发多条必须让用户重新走一遍授权链接（不同 `scene`）。
- 与第 3 节的路径都含 `template/subscribe`/`subscribe/bizsend` 字样，容易和新版接口路径搞混，调用前对照本表核实完整路径。

## 5. 注意事项汇总

- 先确认账号后台实际开放的是哪一套（模板消息 / 订阅通知 / 一次性订阅消息），三者的 `template_id` 体系、`data` 键名格式、触发前提都不通用。
- 模板消息 `data` 键名要求以 `.DATA` 结尾；订阅通知的官方示例键名不带该后缀；两者不要互相套用格式。
- 判断是否真送达要看事件回调（模板消息的 `TEMPLATESENDJOBFINISH`），接口调用本身返回成功只代表任务受理。
- 长期订阅只对政务民生/医疗等公共服务类目开放，普通商业账号默认只能用一次性订阅。
