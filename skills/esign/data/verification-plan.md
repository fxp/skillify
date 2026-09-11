# e签宝 SaaS API V3 skill 验证计划

skill 目前是**文档版**（抓取于 2026-09-11，只做了无凭证探测，见 `probe-log.md`）。拿到**沙箱**应用的 AppId / AppSecret、
并把测试机公网出口 IP 加入应用白名单后，按下面的优先级补测。每条结论写回对应 reference，格式：
`**已用真实 API 验证（YYYY-MM-DD）**：做了什么 → 原始响应片段`。
凭证只走环境变量（`ESIGN_APP_ID`、`ESIGN_APP_SECRET`、`ESIGN_HOST=https://smlopenapi.esign.cn`），测完全仓库 grep 一遍；
测试创建的签署流程用完撤销。沙箱有免费调试套餐，余额 / 次数不足时找 e签宝申请（文档原文）；沙箱签署无法律效力。
需要资料包才能确认的点（官方 Java / PHP / .NET / Python DEMO zip、Postman 脚本、验签 Demo zip）按规矩没有下载，列在最后。

## P0 —— 鉴权与签名（错了全盘皆错）

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 1 | §5 `esign_request()` 的签名能通过网关 | `GET /v3/organizations/identity-info?orgName=<开发者企业名>` | `code == 0` | auth-and-signing.md §4–§5 |
| 2 | POST + body 的签名与 Content-MD5 | `POST /v3/files/file-upload-url`（小 PDF 的元信息） | 返回 fileId + fileUploadUrl | auth-and-signing.md §4.3 |
| 3 | 故意用 `requests(json=...)` 重新序列化 body 会导致 `INVALID_SIGNATURE` | 同 #2，MD5 用紧凑 JSON、发送用带空格 JSON | 预期 401 `INVALID_SIGNATURE`；若成功说明网关不校验 Content-MD5，改写 SKILL.md 规则 2 | SKILL.md 规则 2 |
| 4 | POST 带 body 但省略 Content-MD5 头（签名串该行为空）是否通过 | 同 #2 | 记录结果，消掉 ⚠ | auth-and-signing.md §12 |
| 5 | query 中文值：URL 编码、签名串不编码 | #1 用中文 orgName；再试签名串里也编码 | 只有前者成功 | auth-and-signing.md §4.1 |
| 6 | 时间戳 16 分钟前 → `INVALID_TIMESTAMP`；秒级时间戳的报错 | 各调一次 | 记录 message | errors-and-limits.md §2 |
| 7 | 签名改错一位 → `INVALID_SIGNATURE`，HTTP 401 | 调一次 | 记录 | errors-and-limits.md §2 |
| 8 | 非白名单 IP 调用 → `403 IP白名单不匹配` 的 HTTP 状态与 body 形状 | 换出口 IP 调一次 | 记录 | auth-and-signing.md §1 |
| 9 | 业务失败时的 HTTP 状态码 | 用不存在的 signFlowId 查 detail | 记录 HTTP 状态与 `1435011` body | auth-and-signing.md §10、errors-and-limits.md §1 |
| 10 | `Content-Type` 在 GET 时不发送（签名串对应行为空）是否可行 | #1 去掉 Content-Type | 记录 | auth-and-signing.md §3 |

## P1 —— 文件与模板

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 11 | PUT 时 Content-Type 与第一步不一致 → OSS 403 | 第一步 `application/pdf`，PUT 用 `application/octet-stream` | 403 SignatureDoesNotMatch | files-and-templates.md §3 |
| 12 | PUT 成功后 fileStatus 的变化时序（PDF 无需转换时多久到 2） | 连续查 `GET /v3/files/{fileId}` | 记录首次为 2 的耗时 | files-and-templates.md §4 |
| 13 | fileStatus 未到 2/5 就发起 → `1437513` | PUT 后立即 create-by-file（docx + convertToPDF 更易复现） | 记录 | sign-flows.md §3.6 |
| 14 | 关键字坐标的含义（左下角）与签章区坐标的关系 | 用关键字坐标直接落章，看签完文件里章的位置 | 记录偏移规律，补上 ⚠ | files-and-templates.md §5、sign-flows.md §3.5 |
| 15 | 填充模板生成的 fileId 是否需要等状态 | create-by-doc-template 后立刻查状态 | 记录 | files-and-templates.md §6.3 |
| 16 | `docTemplateName` 缺失时的报错文案 | 不传 docTemplateName | 记录是否为 `templateName不能为空` | files-and-templates.md §6.1 |

## P1 —— 签署流程

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 17 | autoStart 默认 true、autoFinish 默认 false | 不传两者创建，查 detail；全部签完后再查 | 创建后状态 1；签完仍为 1；调 /finish 后 2 | sign-flows.md §1 |
| 18 | autoFinish=false 签完未 finish 时下载 → `1437518` | 调下载 | 记录 | sign-flows.md §12 |
| 19 | 未 finish 时是否推送 `SIGN_FLOW_COMPLETE` | 观察回调 | 预期不推 | callbacks.md §7 |
| 20 | 平台自身企业 autoSign=true 不传 orgSignerInfo 能否落章 | 按 sign-flows.md §3.6 | 成功盖章 | sign-flows.md §3.6、§4 |
| 21 | `signerType=2/3` 是否被接受（vs 错误码“只支持0或1”） | 分别构造 | 记录 | sign-flows.md §15 |
| 22 | noticeTypes 默认不发短信 | 用测试手机号作签署人 | 没收到短信 | SKILL.md 规则 6 |
| 23 | sign-url 的 operator 不传时返回什么 | 不传 operator | 记录 | sign-flows.md §6 |
| 24 | 草稿状态取 sign-url → `1437103` | autoStart=false 后取链接 | 记录 | sign-flows.md §6 |
| 25 | revoke 对草稿 / 已完成流程的报错 | 各调一次 | `1437203` | sign-flows.md §9 |
| 26 | delay 第二次 → `流程只能延期一次` | 调两次 | 记录 | sign-flows.md §11 |
| 27 | 文档示例 `signFlowExpireTime: 169111118000` 是否被拒 | 原样传 | 记录 | sign-flows.md §15 |
| 28 | `signFieldStatus` 在详情里是 string 还是 int | 查 detail | 记录 | sign-flows.md §7 |
| 29 | 下载 POST 与 GET 两种方式的返回是否一致；`urlAvailableDate` 传字符串是否接受 | 各调一次 | 记录 | sign-flows.md §12 |

## P1 —— 回调

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 30 | 回调验签公式（hex、timestamp + query 值 + 原始 body） | notifyUrl 带 `?tenant=acme`，记录真实回调并用 `verify_esign_callback` 校验 | 通过 | callbacks.md §3 |
| 31 | 回调头名的实际大小写、Content-Type | 打印原始请求头 | 记录 | callbacks.md §2 |
| 32 | `SIGN_FLOW_COMPLETE.signFlowStatus` 是字符串 | 看原始 body | 记录 | callbacks.md §7 |
| 33 | 回 500 时的重试间隔与次数、重试时 `X-Tsign-Open-TIMESTAMP` 与 body.timestamp 是否变化 | 接收端故意回 500，记录到达时间 | 写出实际间隔表（替换图片） | callbacks.md §4 |
| 34 | Webhook 与 notifyUrl 同时配置、地址相同时是否推两次 | 同时配置 | 记录 | callbacks.md §1 |

## P2 —— 认证授权

| # | 要验证的结论 | 怎么测 | 判定 | 影响文件 |
| --- | --- | --- | --- | --- |
| 35 | 实名模式对已实名用户 → `1450005` / `1450006` | 对开发者本人 / 本企业调实名模式 | 记录 | identity-authorization.md §2 |
| 36 | 标准版应用传高级版 scope（如 `get_psn_identity_info`）时的报错 | 调 psn-auth-url | 记录 code / message | identity-authorization.md §1 |
| 37 | `GET /v3/organizations/{orgId}/authorized-info` 与错误码页写的 `/v3/persons/{psnId}/authorized-info` 哪个对 | 分别调 | 记录 | identity-authorization.md §8 |
| 38 | `redirectDelayTime` 在认证接口传 int 是否接受 | 调一次 | 记录 | identity-authorization.md §5 |

## 需要资料包才能确认、按规矩未下载的点

- 官方 DEMO（`SaaSAPI_V3_Demo_PYTHON.zip` 等）里 Python 版如何序列化 body、是否发送 GET 的 Content-Type——可用于交叉核对 §5 封装。
- `EsignGatewaySign.zip`、`XYAPINotifySafe.zip`（签名 / 回调验签 Demo）里是否有未脱敏的测试向量。
- Postman 脚本里的预请求签名脚本（可对照 StringToSign 的边界情况，例如自选 Headers 的换行）。
- 回调重试间隔图片（`notify3/pmy852`、`notify3/sblzg8` 中的两张图）需要人工看图转录。
