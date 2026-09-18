# 错误码与限流：全局错误码、调用配额、报警排查

目录：[1. 成功/失败判定](#1-成功失败判定) · [2. 常用错误码速查](#2-常用错误码速查) · [3. 调用配额与清零](#3-调用配额与清零) · [4. 接口报警与自动屏蔽](#4-接口报警与自动屏蔽) · [5. 注意事项汇总](#5-注意事项汇总)

**除标「无凭证探测」的条目外，行为描述均为文档原文，未实测。**

## 1. 成功/失败判定

**所有 `cgi-bin`/`sns` 系列接口统一用 HTTP 200 + 响应体 `errcode`（数字）判定成功与否，`errcode` 缺省或为 `0` 才算成功**；业务错误也是 HTTP 200，不要用 HTTP 状态码分支处理成功/失败。

**无凭证探测（2026-09-17）汇总**：对换 token、菜单查询、用户信息、标签、客服消息、模板消息、网页授权、回调 IP 等 14 个不同接口分别用伪造 `appid`/`secret`/`access_token` 探测，**18 次请求全部返回 HTTP 200**，业务结果全部体现在 JSON 里的 `errcode`/`errmsg`，无一例外。完整命令与响应见 `wechat-mp-workspace/probe-log.md`。

## 2. 常用错误码速查

（来自全局错误码文档，文档原文，未逐条实测；带 ✓ 的已在无凭证探测中复现）

| errcode | 英文描述 | 说明 |
| --- | --- | --- |
| -1 | system error | 系统繁忙，稍候重试 |
| 0 | ok | 请求成功 |
| 40001 ✓ | invalid credential, access_token is invalid or not latest | AppSecret 错误或 access_token 无效；探测得到的报错文案会附带"could get access_token by getStableAccessToken"的建议链接 |
| 40013 ✓ | invalid appid | appid 不合法；探测证实校验优先级在 appid 上，早于 grant_type 等其他参数 |
| 41001 ✓ | access_token missing | 请求里完全没带 `access_token` 参数 |
| 41002 | appid missing | 缺少 appid 参数 |
| 42001 | access_token expired | access_token 超时 |
| 40014 | invalid access_token | access_token 不合法（和 40001 的区别文档未清楚界定，`⚠ 文档未说明`，遇到时都按"重新换 token 重试一次"处理） |
| 45009 | api freq out of limit | 接口调用超过频率限制（见第 3 节） |
| 45011 | api minute-quota reach limit | 分钟级调用太频繁，下一分钟再试 |
| 48001 | api unauthorized | 接口功能未授权，去后台"接口权限"确认是否已开通 |
| 48004 | api forbidden for irregularities | 接口因违规被封禁，登录 mp.weixin.qq.com 查看详情 |
| 61004 / 45035 / 40164 | access clientip is not registered | 调用方 IP 不在白名单，需要先在后台加白名单 |
| 43001 / 43002 | require GET / POST method | 请求方法用错了 |
| 43003 | require https | 必须用 HTTPS |
| 50002 | user limited | 用户账号被冻结或注销 |

**排障工具**：官方提供"API 诊断工具"（`developers.weixin.qq.com/console/devtools/debug`）以及本节第 3 节的 `getridinfo` 接口——**每条报错文案末尾的 `rid` 就是排障凭证**，拿着它调 `getridinfo` 能查到该次请求更详细的失败原因。

## 3. 调用配额与清零

**新注册账号日调用额度**（部分，文档原文，具体数字随粉丝数分档提升）
| 接口 | 每日限额 |
| --- | --- |
| 获取 access_token | 2000 |
| 自定义菜单创建 | 1000 |
| 自定义菜单查询 | 10000 |
| 移动用户分组 | 100000 |
| 发送客服消息 | 500000 |
| 高级群发接口 | 100 |
| 获取关注者列表 | 500 |
| 获取用户基本信息 | 5000000 |
| 获取网页授权 access_token / 刷新 / 拉用户信息 | 无限额 |

测试号（申请页专用）的限额显著更低（如获取 access_token 仅 200/日），**不要用测试号的配额去估算生产账号的余量**。粉丝数超过 10W/100W/1000W 时部分接口额度会自动提升，以账号后台"接口权限"页当前显示的数字为准，不要硬编码上表数字。

**查询/清零调用次数**
| 操作 | Endpoint | 关键参数 |
| --- | --- | --- |
| 查某个接口当前配额、调用次数、频率限制 | `POST /cgi-bin/openapi/quota/get?access_token=` | `cgi_path`（如 `/cgi-bin/message/custom/send`，**不要带 `https://api.weixin.qq.com` 前缀，也不能漏掉开头的 `/`，否则报 `76003`**，文档原文明确警告） |
| 清零指定接口调用次数 | `POST /cgi-bin/openapi/quota/clear?access_token=` | `cgi_path`，格式要求同上（清零口径按视频号小店场景另有 `/channels/ec/` 前缀变体） |
| 清零账号全部接口调用次数 | `POST /cgi-bin/clear_quota?access_token=` | `appid` |
| 用 AppSecret 清零（**不需要 access_token**，也不带在 query 里） | `POST /cgi-bin/clear_quota/v2`（无 access_token 参数，直接用 body 里的 appid+appsecret 鉴权） | `appid`、`appsecret` |
| 用报错里的 rid 反查详情 | `POST /cgi-bin/openapi/rid/get?access_token=` | `rid` |

**注意事项**（文档原文）
- 每个账号**每月共 10 次清零机会**（后台手动清零 + 调接口清零合计消耗同一份额度）。
- 实时调用量统计可能有约 1% 的误差（统计口径/时间差异导致）。
- 第三方平台代公众号调用时，实际消耗的是**公众号自己的配额**，不是第三方平台的配额。

## 4. 接口报警与自动屏蔽

微信公众平台向开发者服务器推送消息/事件失败达到阈值时，会把报警发到开发者配置的微信报警群（配置路径：开发者平台 - 服务号 - 接口管理 - 接口告警）。

**通用报警类型**（所有开发者都要关注）
| 类型 | 触发条件 |
| --- | --- |
| DNS 失败 / DNS 超时 | 推送时解析回调域名失败，超时阈值 5 秒 |
| 连接超时 / 请求超时 | 连接开发者服务器超时（5 秒），或连上了但 5 秒内没收到响应 |
| 回应失败 | 收到的响应不合法（不是 `success`/空串或合法加密回包） |
| **MarkFail（自动屏蔽）** | **多次推送失败后，微信会暂时停止向该服务器推送消息，1 分钟后自动解除** |

**注意事项**
- `MarkFail` 是最容易被忽略的一条：如果开发者服务器短时间内连续超时/回应失败，接下来**一分钟内新消息根本不会被推送过来**，此时代码层面看不到任何错误（因为压根没收到请求），排查"为什么突然收不到用户消息"时要先看接口告警群里有没有 MarkFail 记录，而不是怀疑代码本身。
- 报警内容里的"错误样例"会带首次失败时开发者的响应内容（回应失败场景）或来源 IP（超时场景），是定位问题的第一手材料。
- 第三方平台开发者（`open.weixin.qq.com` 申请）还需要关注 `component_verify_ticket` 推送失败/超时等额外报警类型，本 skill 不展开第三方平台场景。

## 5. 注意事项汇总

- 永远用 `errcode==0` 判成功，不用 HTTP 状态码——本 skill 全部无凭证探测都验证了这一点。
- `cgi_path` 类参数（配额查询/清零）格式要求严格：不带域名前缀、必须带开头斜杠，写错直接报 `76003`。
- MarkFail 自动屏蔽窗口只有 1 分钟，但如果监控/告警配置不到位，开发者可能完全不知道消息被暂停推送过。
- 每月 10 次的清零机会是账号级别的稀缺资源，批量调试阶段不要频繁清零，先看 `getapiquota` 的实时余量再决定是否需要清零。
