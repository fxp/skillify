# 鉴权：access_token、IP 白名单与连通性检测

目录：[1. 文档站现状](#1-文档站现状) · [2. 获取 access_token](#2-获取-access_token) · [3. 获取稳定版 access_token（推荐）](#3-获取稳定版-access_token推荐) · [4. 获取微信 API 服务器 IP](#4-获取微信-api-服务器-ip) · [5. 获取微信推送服务器 IP](#5-获取微信推送服务器-ip) · [6. 网络通信检测](#6-网络通信检测) · [7. 注意事项汇总](#7-注意事项汇总)

**除标「无凭证探测」的条目外，行为描述均为文档原文，未实测。**

## 1. 文档站现状

截至抓取时（2026-09-17），旧版文档路径 `developers.weixin.qq.com/doc/offiaccount/...`（历史上同时覆盖订阅号与服务号）已经下线，访问会被重定向。官方公告原文："原公众号文档（包含订阅号与服务号）已升级为公众号（原订阅号）与服务号文档。" 现分成两套入口：

- **服务号**：`https://developers.weixin.qq.com/doc/service/`（本 skill 的抓取来源）
- **公众号（原订阅号）**：`https://developers.weixin.qq.com/doc/subscription/`

两者共用同一个服务端域名 `api.weixin.qq.com` 和同一套 `access_token` 机制；差异主要体现在**账号认证状态/类型决定哪些接口能开通**（例如模板消息、网页授权 `snsapi_userinfo`、自定义菜单历史上都要求"已认证"账号），不是协议或鉴权方式本身的差异。写代码调用本 skill 覆盖的接口时两套账号类型可以套用同一份实现；如果账号是订阅号且某接口报权限类错误，去 `/doc/subscription/` 交叉确认该能力是否对订阅号开放。

## 2. 获取 access_token

**Endpoint**: `GET https://api.weixin.qq.com/cgi-bin/token`
**用途**: 获取全局唯一的后台接口调用凭据，几乎所有服务端接口都要在 URL 上带着它。

**关键参数**（Query String）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| grant_type | string | 是 | 固定填 `client_credential` |
| appid | string | 是 | 公众号/服务号的 AppID |
| secret | string | 是 | AppID 对应的 AppSecret |

**示例请求**
```bash
curl "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=$WECHAT_MP_APPID&secret=$WECHAT_MP_SECRET"
```
```python
import os, requests
resp = requests.get(
    "https://api.weixin.qq.com/cgi-bin/token",
    params={
        "grant_type": "client_credential",
        "appid": os.environ["WECHAT_MP_APPID"],
        "secret": os.environ["WECHAT_MP_SECRET"],
    },
    timeout=10,
).json()
if resp.get("errcode"):
    raise RuntimeError(f"get token failed: {resp}")
access_token, expires_in = resp["access_token"], resp["expires_in"]  # 7200
```

**示例响应**
```json
{"access_token": "ACCESS_TOKEN", "expires_in": 7200}
```

**注意事项**
- 有效期 7200 秒（文档原文），必须缓存并提前刷新，不要每次调用都重新获取——换 token 接口本身有每日调用额度（见 `errors-and-limits.md`）。
- 不同应用类型的 access_token 互相隔离，只能用于对应类型的接口。
- AppSecret 可在开发者后台冻结/解冻；冻结后本接口报 `40243`，但不影响账号基础功能、不影响第三方授权调用、不影响云开发调用（文档原文）。
- **无凭证探测（2026-09-17）**：
  ```
  $ curl "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=wx_test_fake_00000000&secret=fakesecret0000000000000000000000"
  {"errcode":40013,"errmsg":"invalid appid rid: 6aac005a-01bfdbee-79769285"}
  HTTP_STATUS:200
  ```
  去掉 `grant_type` 参数重试，返回值仍是 `40013 invalid appid`（不是 `40002 invalid grant_type` 或参数缺失类错误），说明服务端先校验 appid 格式、再校验其他参数——文档没有说明校验顺序，这条是探测得到的行为，不代表未来一定如此。
- 官方现推荐改用第 3 节的 `getStableAccessToken`；用伪造 access_token 调用只读接口时，`40001` 的报错文案会主动提示"could get access_token by getStableAccessToken"（见 `errors-and-limits.md` 第 2 节的探测记录）。

## 3. 获取稳定版 access_token（推荐）

**Endpoint**: `POST https://api.weixin.qq.com/cgi-bin/stable_token`
**用途**: 官方推荐替代第 2 节接口的新版换取方式，同样返回 7200 秒有效期的 access_token，但**和 `/cgi-bin/token` 换出来的 token 互相隔离**（文档原文："此接口和 getAccessToken 互相隔离，且比其更加稳定"）——两套接口各自维护自己的 token 状态，不要把用其中一个接口换到的 token 交给另一个接口的刷新逻辑复用。

**关键参数**（Request Body，JSON）
| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| grant_type | string | 是 | - | 固定填 `client_credential` |
| appid | string | 是 | - | AppID |
| secret | string | 是 | - | AppSecret |
| force_refresh | boolean | 否 | false | `false`：有效期内重复调用不刷新（推荐，绝大多数场景用这个）；`true`：强制让上次的 access_token 失效并换新 |

**示例请求**
```bash
curl -X POST "https://api.weixin.qq.com/cgi-bin/stable_token" \
  -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credential\",\"appid\":\"$WECHAT_MP_APPID\",\"secret\":\"$WECHAT_MP_SECRET\",\"force_refresh\":false}"
```

**示例响应**
```json
{"access_token": "ACCESS_TOKEN", "expires_in": 7200}
```

**注意事项**
- 这是本接口与第 2 节接口最大的区别：**请求方式是 POST + JSON body，不是 GET + query string**（无凭证探测证实用 JSON body 能正确触发 appid 校验，返回 `40013`，而不是"缺少参数"类错误，说明服务端确实按 JSON body 解析）。
- `force_refresh=true` 会使旧 token 失效，多进程/多实例共享同一个 appid 时要小心：一个实例强制刷新会让其他实例手里的 token 失效，一般只在怀疑 token 泄漏时才用。
- 不支持云调用、不支持第三方平台调用（文档原文，第三方场景仍需用 `component_access_token` 体系）。

## 4. 获取微信 API 服务器 IP

**Endpoint**: `GET https://api.weixin.qq.com/cgi-bin/get_api_domain_ip`
**用途**: 拿到"你的服务器主动访问 `api.weixin.qq.com` 时，微信侧对外呈现的 IP 段"，用于给自己的出站防火墙/安全组放行。**不要和第 5 节的推送服务器 IP 搞混**——方向相反。

**关键参数**（Query String）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| access_token | string | 是 | 接口调用凭据 |

**示例响应**
```json
{"ip_list": ["101.226.x.x", "..."]}
```

**注意事项**
- 用途是"开发者服务器主动访问 api.weixin.qq.com 的远端地址"（文档原文）——如果你的出站流量做了 IP 限制，用这份列表放行。

## 5. 获取微信推送服务器 IP

**Endpoint**: `GET https://api.weixin.qq.com/cgi-bin/getcallbackip`
**用途**: 拿到"微信服务器主动推送消息/事件到你服务器时"所用的来源 IP 段，用于给自己接收回调的入站防火墙放行。方向与第 4 节相反：第 4 节是你打出去，这里是微信打进来。

**关键参数**（Query String）
| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| access_token | string | 是 | 接口调用凭据 |

**示例响应**
```json
{"ip_list": ["140.207.x.x", "..."]}
```

**注意事项**
- 常见错误是拿这份 IP 去限制"你调用 api.weixin.qq.com"的出站流量，应该反过来只用于入站回调（`events.md` 的服务器配置）的来源校验。

## 6. 网络通信检测

**Endpoint**: `POST https://api.weixin.qq.com/cgi-bin/callback/check`
**用途**: 排查"配置的回调 URL 连不上"问题的官方诊断工具：对 URL 域名做 DNS 解析，再对解析出的每个 IP 做一次 ping，返回丢包率和耗时。适合在配置服务器地址（见 `events.md`）后连不通时先跑一次，而不是盲猜网络问题。

**关键参数**（Request Body，JSON）
| 参数 | 类型 | 必填 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| action | string | 是 | `all` | 检测动作：`dns`（仅域名解析）/ `ping`（仅 ping）/ `all`（全部） |
| check_operator | string | 是 | `DEFAULT` | 检测运营商：`CHINANET`（电信）/ `UNICOM`（联通）/ `CAP`（腾讯）/ `DEFAULT`（自动选择） |

**示例响应**（字段名，未实测具体取值）
```json
{"dns": [{"ip": "...", "real_operator": "..."}], "ping": [{"ip": "...", "from_operator": "...", "package_loss": 0, "time": 0}]}
```

**注意事项**
- 这是排障工具，不是业务接口；调用它本身也要合法 access_token，所以回调 URL 完全打不通、连 access_token 都还没拿到时用不上它，先确认 access_token 链路。

## 7. 注意事项汇总

- 所有本节接口的鉴权方式一致：`access_token` 放 URL 查询参数。
- 成功判定统一看响应体的 `errcode`（数字，`0` 或缺省即成功），不要用 HTTP 状态码判断——本节所有探测请求，无论对错都返回 HTTP 200（见下方无凭证探测记录）。
- **无凭证探测（2026-09-17）**，用伪造 `access_token=fake_token_00000000000000000000000000000000` 分别调 `get_api_domain_ip` 与 `getcallbackip`：
  ```
  $ curl "https://api.weixin.qq.com/cgi-bin/get_api_domain_ip?access_token=fake_token_00000000000000000000000000000000"
  {"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, ... rid: 6aac0082-316556aa-1b285699"}
  HTTP_STATUS:200

  $ curl "https://api.weixin.qq.com/cgi-bin/getcallbackip?access_token=fake_token_00000000000000000000000000000000"
  {"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, ... rid: 6aac007f-16cdf738-3c46b187"}
  HTTP_STATUS:200
  ```
  两者报错格式一致，符合文档描述的统一错误码体系。
