# 无凭证探测日志

日期：2026-09-17（UTC 14:59 起）。全部使用明显伪造的 appid/secret/access_token/code，未使用任何真实凭证，未创建任何账号资源，每个 endpoint ≤3 次探测，未做压力测试。响应中未出现本机出口 IP 等敏感信息，无需脱敏。

## 1. 换 token（`GET /cgi-bin/token`，对应 `references/auth.md` 第 2 节）

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=wx_test_fake_00000000&secret=fakesecret0000000000000000000000"
{"errcode":40013,"errmsg":"invalid appid rid: 6aac005a-01bfdbee-79769285"}
HTTP_STATUS:200
```

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/token?appid=wx_test_fake_00000000&secret=fakesecret0000000000000000000000"
{"errcode":40013,"errmsg":"invalid appid rid: 6aac005c-5fd159ee-09f109e9"}
HTTP_STATUS:200
```
（去掉 `grant_type` 参数，报错仍是 `40013 invalid appid`，不是参数缺失类错误——说明 appid 校验在其他参数校验之前。）

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=test&secret=test"
{"errcode":40013,"errmsg":"invalid appid rid: 6aac005e-5b65d458-6d0936e1"}
HTTP_STATUS:200
```

## 2. 稳定版换 token（`POST /cgi-bin/stable_token`，对应 `references/auth.md` 第 3 节）

```
$ curl -sS -X POST -H "Content-Type: application/json" -w "\nHTTP_STATUS:%{http_code}\n" \
  -d '{"grant_type":"client_credential","appid":"wx_test_fake_00000000","secret":"fakesecret0000000000000000000000","force_refresh":false}' \
  "https://api.weixin.qq.com/cgi-bin/stable_token"
{"errcode":40013,"errmsg":"invalid appid rid: 6aac0060-297a2899-4b3fff85"}
HTTP_STATUS:200
```
（确认该接口确实按 POST + JSON body 解析参数，而不是忽略 body 只看 query string——否则不会命中 appid 校验并返回同样的 `40013`。）

## 3. 伪造 access_token 调只读/写接口（对应 `references/errors-and-limits.md` 第 1 节）

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/menu/get?access_token=fake_token_00000000000000000000000000000000"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac0063-7ed08fb9-1250f724"}
HTTP_STATUS:200
```

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/menu/get"
{"errcode":41001,"errmsg":"access_token missing rid: 6aac0064-355b48ab-4c5b487e"}
HTTP_STATUS:200
```

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/user/info?access_token=fake_token_00000000000000000000000000000000&openid=ofake_openid_0000000000000&lang=zh_CN"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac0067-64b57aeb-64b4a99a"}
HTTP_STATUS:200
```

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/tags/get?access_token=fake_token_00000000000000000000000000000000"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac006a-385fd043-15491734"}
HTTP_STATUS:200
```

```
$ curl -sS -X POST -H "Content-Type: application/json" -w "\nHTTP_STATUS:%{http_code}\n" \
  -d '{"touser":"ofake_openid_0000000000000","msgtype":"text","text":{"content":"probe"}}' \
  "https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token=fake_token_00000000000000000000000000000000"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac0075-1b3628cf-4ed2dcbf"}
HTTP_STATUS:200
```

```
$ curl -sS -X POST -H "Content-Type: application/json" -w "\nHTTP_STATUS:%{http_code}\n" \
  -d '{"touser":"ofake_openid_0000000000000","template_id":"faketemplateid000000000000","data":{}}' \
  "https://api.weixin.qq.com/cgi-bin/message/template/send?access_token=fake_token_00000000000000000000000000000000"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac0077-33f385b5-58f65b9f"}
HTTP_STATUS:200
```

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/getcallbackip?access_token=fake_token_00000000000000000000000000000000"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac007f-16cdf738-3c46b187"}
HTTP_STATUS:200
```

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/get_api_domain_ip?access_token=fake_token_00000000000000000000000000000000"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac0082-316556aa-1b285699"}
HTTP_STATUS:200
```

```
$ curl -sS -X POST -H "Content-Type: application/json" -w "\nHTTP_STATUS:%{http_code}\n" \
  -d '{"appid":"wx_test_fake_00000000"}' \
  "https://api.weixin.qq.com/cgi-bin/clear_quota?access_token=fake_token_00000000000000000000000000000000"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac008b-789ac8d9-508328d8"}
HTTP_STATUS:200
```

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/get_current_selfmenu_info?access_token=fake_token_00000000000000000000000000000000"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac008e-7f11abbd-008f13cb"}
HTTP_STATUS:200
```

```
$ curl -sS -X POST -H "Content-Type: application/json" -w "\nHTTP_STATUS:%{http_code}\n" \
  -d '{"begin_openid":""}' \
  "https://api.weixin.qq.com/cgi-bin/tags/members/getblacklist?access_token=fake_token_00000000000000000000000000000000"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac0090-43ce2338-7242cc82"}
HTTP_STATUS:200
```

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/cgi-bin/ticket/getticket?access_token=fake_token_00000000000000000000000000000000&type=jsapi"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, could get access_token by getStableAccessToken, more details at https://mmbizurl.cn/s/JtxxFh33r rid: 6aac0093-2c783a73-3d95418a"}
HTTP_STATUS:200
```

## 4. 网页授权（`sns/*`，对应 `references/oauth.md`）

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/sns/oauth2/access_token?appid=wx_test_fake_00000000&secret=fakesecret0000000000000000000000&code=fake_code_000000&grant_type=authorization_code"
{"errcode":40013,"errmsg":"invalid appid, rid: 6aac007a-6c02c771-26bf69c4"}
HTTP_STATUS:200
```
（注意错误文案是 `"invalid appid, rid:"`——appid 后带逗号，与 `cgi-bin/token` 的 `"invalid appid rid:"`（不带逗号）不同。）

```
$ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "https://api.weixin.qq.com/sns/userinfo?access_token=fake_snstoken_00000000000000&openid=ofake_openid_0000000000000&lang=zh_CN"
{"errcode":40001,"errmsg":"invalid credential, access_token is invalid or not latest, rid: 6aac007d-476fb159-54f0678e"}
HTTP_STATUS:200
```
（对比第 3 节的 `cgi-bin` 系列报错，本条**不带**"could get access_token by getStableAccessToken"的提示，说明 `sns` 系列 access_token 由独立子系统处理，`getStableAccessToken` 机制对它不适用。）

## 5. 小结

- 18 次探测（本文件记录 14 条代表性请求；另有 4 条同类重复未逐一列出，均为相同 `errcode`/结构）全部返回 **HTTP 200**，业务结果体现在 JSON 的 `errcode` 字段，无一次返回非 200 状态码。
- 没有发现任何"文档描述的行为与探测结果不符"的情况（即没有 `<!-- Gap: -->` 级别的发现）——本次探测的价值在于**确认**了文档描述的"HTTP 200 + errcode"模式、`40013`/`40001`/`41001` 等错误码的真实文案，以及两套 access_token 系统在报错文案上的可观测差异，这些均已写回对应 reference 文件并标注"无凭证探测（2026-09-17）"。
- 探测范围内没有涉及任何会产生副作用的操作（未创建菜单、未发送任何真实消息、未修改任何账号配置）；`clear_quota`、`tags/members/getblacklist`、`message/custom/send` 等写类接口均因伪造 access_token 在鉴权阶段即被拒绝，未触达实际业务逻辑。
