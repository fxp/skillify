# 网页授权（OAuth2.0）：snsapi_base 与 snsapi_userinfo

目录：[1. 四步流程总览](#1-四步流程总览) · [2. 跳转授权链接](#2-跳转授权链接) · [3. 用 code 换网页授权 access_token](#3-用-code-换网页授权-access_token) · [4. 拉取用户信息](#4-拉取用户信息) · [5. 刷新与校验网页授权 token](#5-刷新与校验网页授权-token) · [6. 注意事项汇总](#6-注意事项汇总)

**除标「无凭证探测」的条目外，行为描述均为文档原文，未实测。**

## 1. 四步流程总览

1. 引导用户进入授权页面（`open.weixin.qq.com`，第 2 节）。
2. 用户同意后，回调页面 URL 上带 `code`。
3. 用 `code` 换取**用户授权 access_token**（第 3 节；**与 `auth.md` 里那个全局 access_token 是两套完全不同的 token**，文档原文明确写"注意：此 access_token 与基础支持的 access_token 不同"）。
4. 用这个用户授权 access_token + openid 拉取用户信息（第 4 节，`scope=snsapi_userinfo` 时才有数据）。

**适用账号**：只有**已认证**的服务号才能使用网页授权（文档原文），另外已认证的政府/事业单位/媒体类型公众号也有权限；未认证账号、多数其他账号类型不支持。

## 2. 跳转授权链接

```
https://open.weixin.qq.com/connect/oauth2/authorize?appid=APPID&redirect_uri=REDIRECT_URI&response_type=code&scope=SCOPE&state=STATE#wechat_redirect
```

**关键参数**
| 参数 | 必填 | 说明 |
| --- | --- | --- |
| appid | 是 | 已认证服务号的 AppID |
| redirect_uri | 是 | 授权后回调地址，需 urlEncode；域名必须与公众平台后台「网页授权域名」配置一致 |
| response_type | 是 | 固定填 `code` |
| scope | 是 | `snsapi_base` 或 `snsapi_userinfo`，见下 |
| state | 否 | 回调时原样带回，≤128 字节，字符集 `a-zA-Z0-9` |
| `#wechat_redirect` | 是 | 无论直接打开还是 302 重定向都必须带 |
| forcePopup | 否 | 强制弹窗确认，默认 `false`；命中特殊静默授权场景时此参数不生效 |

**scope 两种取值的精确区别**（这是本节最容易凭直觉选错的地方）
| scope | 是否弹授权页 | 能拿到什么 | 是否要求已关注 |
| --- | --- | --- | --- |
| `snsapi_base` | **不弹窗**，静默跳转 | 仅 openid | 不要求 |
| `snsapi_userinfo` | **弹窗**，需用户手动同意 | 昵称、头像、性别、所在地等基本信息 | **不要求**——用户只要点了同意授权，不关注公众号也能拿到信息（文档原文特别强调） |

**部署要点**
- 需先在公众平台后台「设置与开发 - 账号设置 - 功能设置」配置"网页授权域名"，**填的是裸域名（如 `www.qq.com`），不能带协议头**；配置后只有该域名下页面能发起授权，子域名/父域名不共享（如 `pay.qq.com`、`qq.com` 都不行）。
- 如果账号把授权管理委托给了第三方平台，不需要自己额外配置。

## 3. 用 code 换网页授权 access_token

**Endpoint**: `GET /sns/oauth2/access_token`

**关键参数**（Query String）
| 参数 | 必填 | 说明 |
| --- | --- | --- |
| appid | 是 | 服务号 AppID |
| secret | 是 | 服务号 AppSecret |
| code | 是 | 第 2 步回调拿到的 code（一次性，用后失效） |
| grant_type | 是 | 固定填 `authorization_code` |

**示例请求**
```bash
curl "https://api.weixin.qq.com/sns/oauth2/access_token?appid=$WECHAT_MP_APPID&secret=$WECHAT_MP_SECRET&code=$CODE&grant_type=authorization_code"
```

**示例响应**
```json
{
  "access_token": "SNS_ACCESS_TOKEN",
  "expires_in": 7200,
  "refresh_token": "SNS_REFRESH_TOKEN",
  "openid": "OPENID",
  "scope": "snsapi_userinfo"
}
```

**注意事项**
- 响应体的 `access_token` 字段名和 `auth.md` 里的全局 access_token 字段名撞了，但**不是同一个 token、不能互换使用**——网页授权的 `access_token` 只能用于第 4/5 节的 `sns/*` 接口，不能拿去调 `cgi-bin/*` 系列接口。
- 同时返回的 `openid` 就是这次授权用户的 openid，第 4 步取用户信息要用它。

## 4. 拉取用户信息

**Endpoint**: `GET /sns/userinfo`
**前提**: 仅 `scope=snsapi_userinfo` 换到的授权才有完整信息；`snsapi_base` 换到的 token 调用本接口大概率拿不到昵称等字段（`⚠ 文档未说明`具体返回什么，未做真实调用验证，实现时不要假设 base 授权也能拿到昵称）。

**关键参数**（Query String）
| 参数 | 必填 | 说明 |
| --- | --- | --- |
| access_token | 是 | 第 3 步拿到的**网页授权** access_token（不是全局 access_token） |
| openid | 是 | 第 3 步返回的 openid |
| lang | 否 | `zh_CN`（简体，默认）/ `zh_TW`（繁体）/ `en`（英语） |

**注意事项**
- 若开发者账号绑定了微信开放平台账号，响应里会带 `unionid`（见 `users.md` 第 7 节），逻辑与全局用户信息接口的 unionid 规则一致。

## 5. 刷新与校验网页授权 token

**刷新**: `GET /sns/oauth2/refresh_token?appid=APPID&grant_type=refresh_token&refresh_token=REFRESH_TOKEN`
**校验是否仍有效**: `GET /sns/auth?access_token=ACCESS_TOKEN&openid=OPENID`

**注意事项**
- 网页授权 access_token 有效期同样是 7200 秒，但**过期后不能像全局 token 那样直接重新调 `/cgi-bin/token`**，必须用 `refresh_token` 走本节的刷新接口；`refresh_token` 的有效期文档未在本页给出明确天数，`⚠ 文档未说明`，实现时不要硬编码假设值，过期后引导用户重新授权。
- `/sns/auth` 只是校验 token 有效性，不返回用户信息，不能替代第 4 节。

## 6. 注意事项汇总

- **两套 access_token 不要混用**：全局 access_token（`cgi-bin/*`）与网页授权 access_token（`sns/*`）分别有各自的换取、刷新、校验接口，字段名相同但值不通用。
- `snsapi_base` 静默、只拿 openid；`snsapi_userinfo` 要用户手动确认、能拿基本信息且不要求已关注——按实际需要选 scope，静默场景滥用 `snsapi_userinfo` 会给用户造成不必要的授权打扰。
- 授权回调域名配置精确到路径前缀（全域名下所有路径都能用），但协议头、子域名/父域名不能混用。
- **无凭证探测（2026-09-17）**：
  ```
  $ curl "https://api.weixin.qq.com/sns/oauth2/access_token?appid=wx_test_fake_00000000&secret=fakesecret0000000000000000000000&code=fake_code_000000&grant_type=authorization_code"
  {"errcode":40013,"errmsg":"invalid appid, rid: 6aac007a-6c02c771-26bf69c4"}
  HTTP_STATUS:200

  $ curl "https://api.weixin.qq.com/sns/userinfo?access_token=fake_snstoken_00000000000000&openid=ofake_openid_0000000000000&lang=zh_CN"
  {"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, rid: 6aac007d-476fb159-54f0678e"}
  HTTP_STATUS:200
  ```
  两点观察：① `sns/oauth2/access_token` 的错误文案是"invalid appid**,** rid:"（appid 后带逗号），而 `cgi-bin/token`（见 `auth.md`）是"invalid appid **rid:**"（不带逗号）——两个子系统的错误文案格式存在细微差异，写日志解析正则时不要假设全站统一。② `sns/userinfo` 的 `40001` 报错文案**不带**"could get access_token by getStableAccessToken"的提示（`cgi-bin` 系列的伪造 token 报错都带这句），间接印证网页授权 token 确实由独立子系统处理，不受 `getStableAccessToken` 机制影响。
