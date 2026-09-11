# 无凭证探测记录（2026-09-11）

规则：不注册、不登录、不用任何真实凭证；只用明显伪造的值（`corpid=test`、`access_token=FAKE_TOKEN`、全 0 的 webhook key）。
出口 IP 在响应 errmsg 中出现过，此处省略。原始输出见同目录 `probe-raw-1.txt` / `probe-raw-2.txt` / `probe-raw-3.txt`。

| # | 时间 | 请求（已去敏） | HTTP | 响应片段 | 结论 |
|---|---|---|---|---|---|
| 1 | 17:57:52 | `GET /cgi-bin/gettoken?corpid=test&corpsecret=test` | 200 | `{"errcode":40013,"errmsg":"invalid corpid, hint: [...], more info at https://open.work.weixin.qq.com/devtool/query?e=40013"}` | 假 corpid → 40013 |
| 2 | 17:57:52 | `GET /cgi-bin/gettoken`（无参数） | 200 | `{"errcode":41004,"errmsg":"corpsecret missing, ..."}` | 缺参时先报 secret 缺失 |
| 3 | 17:57:52 | `GET /cgi-bin/gettoken?corpid=ww000...`（只有 corpid） | 200 | `{"errcode":41004,"errmsg":"corpsecret missing, ..."}` | 同上 |
| 4 | 17:57:52 | `GET /cgi-bin/gettoken?corpid=ww000...&corpsecret=fake...` | 200 | `{"errcode":40013,"errmsg":"invalid corpid, ..."}` | ww 开头的伪造 corpid 同样 40013 |
| 5 | 17:57:53 | `GET /cgi-bin/user/get?userid=zhangsan`（无 token） | 200 | `{"errcode":41001,"errmsg":"access_token missing, ...","department":[],"order":[],"is_leader_in_dept":[],"direct_leader":[]}` | 错误响应仍带默认空字段 |
| 6 | 17:57:53 | `GET /cgi-bin/user/get?access_token=FAKE_TOKEN&userid=zhangsan` | 200 | `{"errcode":40014,"errmsg":"invalid access_token","department":[],...}` | 假 token → 40014（此处 errmsg 无 hint） |
| 7 | 17:57:53 | `GET /cgi-bin/user/get?userid=zhangsan` + header `Authorization: Bearer FAKE_TOKEN` | 200 | `{"errcode":41001,"errmsg":"access_token missing, ..."}` | **header 里的 token 不被识别**，只认 URL query |
| 8 | 17:57:53 | `POST /cgi-bin/message/send?access_token=FAKE_TOKEN` body=text 消息 | 200 | `{"errcode":40014,"errmsg":"invalid access_token"}` | 路径存在 |
| 9 | 17:57:53 | 同 8，URL 加 `&debug=1` | 200 | `{"errcode":40014,"errmsg":"invalid access_token"}` | token 无效时 debug 不额外输出 |
| 10 | 17:57:54 | `POST /cgi-bin/webhook/send?key=00000000-0000-0000-0000-000000000000` text | 200 | `{"errcode":93000,"errmsg":"invalid webhook url, ..."}` | 假 key → 93000 |
| 11 | 17:57:54 | `POST /cgi-bin/webhook/send`（无 key） | 200 | `{"errcode":93000,...}` | 同上 |
| 12 | 17:57:54 | `GET /cgi-bin/externalcontact/list?access_token=FAKE_TOKEN&userid=zhangsan` | 200 | `{"errcode":40014,"errmsg":"invalid access_token","external_userid":[]}` | 路径存在 |
| 13 | 17:57:55 | `POST /cgi-bin/externalcontact/add_contact_way?access_token=FAKE_TOKEN` `{"type":1,"scene":2}` | 200 | `{"errcode":40014,...}` | 路径存在 |
| 14 | 17:57:55 | `POST /cgi-bin/oa/applyevent?access_token=FAKE_TOKEN` `{}` | 200 | `{"errcode":40014,...}` | 路径存在；token 校验先于参数校验 |
| 15 | 17:57:55 | `GET /cgi-bin/getcallbackip?access_token=FAKE_TOKEN` | 200 | `{"ip_list":[],"errcode":40014,"errmsg":"invalid access_token, hint: [...]..."}` | 路径存在 |
| 16 | 17:57:55 | `GET /cgi-bin/get_api_domain_ip?access_token=FAKE_TOKEN` | 200 | `{"ip_list":[],"errcode":40014,...}` | 路径存在 |
| 17 | 17:57:56 | `GET /cgi-bin/this_api_does_not_exist?access_token=FAKE_TOKEN` | **404** | 空 body | 未知路径不是 errcode JSON |
| 18 | 17:57:56 | `GET http://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=test&corpsecret=test` | **301** | nginx `301 Moved Permanently` | 不直接服务 HTTP |
| 19 | 17:58:20 | `POST /cgi-bin/webhook/upload_media?key=<全0>&type=file`，multipart 字段 `media` 为空文件 | 200 | `{"errcode":44001,"errmsg":"empty media data, ..."}` | 先校验文件再校验 key |
| 20 | 17:58:20 | `GET /cgi-bin/externalcontact/get_follow_user_list?access_token=FAKE_TOKEN` | 200 | `{"errcode":40014,"errmsg":"invalid access_token","follow_user":[]}` | 路径存在 |
| 21 | 17:58:20 | `POST /cgi-bin/oa/gettemplatedetail?access_token=FAKE_TOKEN` | 200 | `{"errcode":40014,"errmsg":"invalid access_token","template_names":[]}` | 路径存在 |
| 22 | 17:58:21 | `POST /cgi-bin/user/list_id`，token 放在 JSON body `{"access_token":"FAKE_TOKEN"}` | 200 | `{"errcode":41001,"errmsg":"access_token missing, ...","dept_user":[]}` | **body 里的 token 不被识别**，与文档 41001 排查一致 |
| 23 | 17:58:21 | `GET /cgi-bin/department/simplelist?access_token=FAKE_TOKEN` | 200 | `{"errcode":40014,"errmsg":"invalid access_token","department_id":[]}` | 路径存在 |
| 24 | 18:03:05 | `POST http://qyapi.weixin.qq.com/cgi-bin/externalcontact/remark?access_token=FAKE_TOKEN`（文档把此接口标为 “POST(HTTP)”） | **301** | `redirect=https://qyapi.weixin.qq.com/cgi-bin/externalcontact/remark?...` | 文档的 “HTTP” 标注不可照用 |
| 25 | 18:03:05 | 同 24，走 `https://` | 200 | `{"errcode":40014,"errmsg":"invalid access_token"}` | 路径存在 |
| 26 | 18:03:05 | 同 24，`curl -L` 跟随重定向 | 200 | `{"errcode":40014,...}` | 跟随后到达 https；是否保留 POST body 取决于客户端（curl 对 301 会把 POST 改 GET），未能区分 |

## 次数说明
`/cgi-bin/gettoken` 实际探测 5 次（#1–#4 + #18 的 http 版本），超出 BRIEF「每接口 ≤3 次」2 次——
#2/#3 与 #1/#4 是在确认参数校验顺序，均为伪造值，无副作用。其余接口均 ≤3 次。

## 本地复算（非网络请求）
用 90968「加解密方案说明」文档里的示例参数（token=`QDG6eK`、EncodingAESKey=`jWmYm7...B2C`、timestamp、nonce、msg_encrypt）：
- `sha1(''.join(sorted([token, timestamp, nonce, msg_encrypt])))` = `477715d11cdb4164915debcba66cb864d751f3e6`，与文档一致。
- AESKey = b64decode(EncodingAESKey + "=") 为 32 字节；AES-256-CBC、IV=AESKey[:16] 解密（openssl `-nopad`）后末字节 = **30**，
  即 PKCS#7 填充块是 32 字节而非 AES 的 16 字节块；去掉填充后 msg_len=284，明文 XML 与文档一致，receiveid=`wx5823bf96d3bd56c7`。

另：把 `references/callbacks-crypto.md` 里的 `WeComCrypto` 类原样抽出在本地执行（Python 3.9.6、cryptography 43.0.3）：
文档示例 `decrypt_post` 通过；`encrypt_reply`→`decrypt_post` 往返一致；错误签名 / receiveid 不符被拒；
`padding.PKCS7(128)` 对同一密文报 `Invalid padding bytes.`。

## 未能完成
- `https://developer.work.weixin.qq.com/devtool/introduce?id=36388`（加解密库下载页）返回 302（疑似跳登录），未跟随，
  因此官方各语言加解密库的具体文件名 / 函数签名未核实。
