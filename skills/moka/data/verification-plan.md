# Moka skill 验证计划（待真实凭证）

当前状态：文档版，抓取于 2026-09-11，**未用真实凭证验证**；无凭证探测见 `probe-log.md`（50 次请求 + 4 个本地复算脚本）。

需要的测试资源：
- ATS：一个**测试租户**（可用 `api-staging-3.mokahr.com`）的 API Key、`orgId`；OAuth2 的 `clientID` / `clientSecret`；CSM 配置的 webhook URL 与 signing key（可选 AES 密钥 / IV）；
  一个测试职位、一个测试流程、2 个测试申请；CSM 开通「外部系统创建 Offer」。
- People：测试租户的 apiKey、`entCode`、RSA 私钥（向 CSM 确认密钥由谁生成、公钥在哪登记）、一个超管邮箱作 `userName`；
  在「对外接口设置」为每个待测能力建接口拿 `apiCode`；一个公网 HTTPS 回调地址。
- 所有凭证只走环境变量；测完删除测试部门 / 用户 / 职位 / 招聘需求 / 员工 / 待入职记录；全仓库 grep 凭证前缀。

## P0：鉴权与"开头几件事"（错了全盘皆错）

| # | 要验证的结论 | 怎么测 | 判定 | 成本 |
|---|---|---|---|---|
| 1 | ATS Basic 必须 `KEY:`（带冒号）；不带冒号是否也能过 | 同一 Key 分别用 `base64("KEY:")` 与 `base64("KEY")` 调 `GET /v1/archiveReasons` | 记录两种结果，更新 auth.md 第 3 节 ⚠ | 0 |
| 2 | 真实 Key 下的成功 / 参数错误 / 鉴权错误的 HTTP 状态与 body（探测只看到了伪造 Key 的 500） | 真实 Key 调 `GET /v1/archiveReasons`；再调 `PUT move_application_stage` 不带参数 | 记录 HTTP 码与 body 结构 | 0 |
| 3 | OAuth2：`getToken` 返回 `expiresIn` 与 30 分钟续期行为；哪些接口接受 Bearer | 换 token；用 Bearer 调 `GET /v1/departments`、`POST /v3/data/getApplictaions`、`POST /v1/jobs/getJobs` | 列出接受 / 拒绝 Bearer 的接口 | 0 |
| 4 | OAuth2 `clientID` 大小写是否敏感 | 用真实凭证分别传 `clientID` / `clientId` | 一个成功一个 110020 → 敏感 | 0 |
| 5 | People 签名：用真实私钥按 auth.md `people_sign()` 签，能否通过 | `POST /v1/batch/data` pageSize=1 | `code:200` | 0 |
| 6 | People 签名失败 / timestamp 超 3 分钟 / nonce 重复 / nonce 9–10 位 的各自报错 | 逐项构造 | 记录 code 与 msg；确定 nonce 上限（8 还是 10） | 0 |
| 7 | People 鉴权失败真实返回（探测：伪造 Key → 403 无 code；文档：401 / 100001） | 真实 Key + 错误 sign | 若仍 403 → 维持 Gap；若出现 401/100001 → 修正 auth.md Gap 描述 | 0 |
| 8 | ATS 与 People 的 apiKey 是否同一个 | 用 ATS Key 调 People（带正确签名） | 通过 / 拒绝 | 0 |

## P1：⚠ 清单（文档未说明 / 自相矛盾）

| # | ⚠ 条目（所在文件） | 测法 | 判定 |
|---|---|---|---|
| 9 | `/v1/data/applications` 的 `fromTime` 格式、`next` 能否跨天复用（candidates.md） | 分别传 `2026-09-01`、`2026-09-01 00:00:00`、ISO8601；隔天用旧 `next` | 记录接受的格式与 next 行为 |
| 10 | `list_by_condition` 时间窗 > 3 个月（candidates.md） | 传 4 个月窗口 | 报错还是截断 |
| 11 | `move_application_stage` 参数放 body、跨流程阶段（candidates.md） | 各测一次 | 记录报错 |
| 12 | `uploadResume` 成功码 0、`websiteSourceName` 类型、`senondSourceId`（candidates.md） | 上传一份测试简历（无职位） | 记录响应；清理候选人 |
| 13 | 官网申请失败响应格式（candidates.md） | 缺必填字段投递 | 记录格式 |
| 14 | 创建面试 `startTime` 时区、`round` 取值、`signedInAt` 是否真必填（interviews-offers.md） | 创建 1 场电话面试后查 V3 `startTime` 毫秒值 | 反推时区；省略 signedInAt 看报错 |
| 15 | `sendOffer` 不传 `hrEmail` 是否报错；通知开关默认值（interviews-offers.md） | 测试申请上操作 | 记录 |
| 16 | Offer `salaryNumber` 单位与读回类型（interviews-offers.md） | 创建 offer `salaryNumber=30000` 后 V3 读回 | 看系统界面显示 3 万还是 3 千万 |
| 17 | 更新职位不传 `displayOnOfficialSite` 是否下架（jobs.md） | 已发布测试职位上只改 title | 看官网是否仍展示 |
| 18 | `getJobs` 的 `commitment` 传数字 / 中文（jobs.md） | 各传一次 | 哪个生效 |
| 19 | V3 职位详情 `sence` vs `scene`（jobs.md） | 各传一次 | 哪个生效 |
| 20 | 官网职位列表不带 Key 是否返回数据（jobs.md，探测只到参数校验） | 用真实 orgId + `mode=social` 不带鉴权 | 返回数据 → 写明"公开接口" |
| 21 | 部门同步 / V3 用户列表成功码 0 vs 200（ats-org-users.md） | 测试租户各调一次 | 记录 |
| 22 | People `/v1/roster/onboarding` pageSize 50 vs 200（people-hr.md） | 传 60 | 报错 / 截断 |
| 23 | People 用错数据源 apiCode 调 `/v1/batch/data`（people-hr.md） | 用部门 apiCode 调 | 报错还是别的数据 |
| 24 | People 新增员工必填字段；待入职 `onBoardingDate` 格式（people-hr.md） | 最小字段新增到测试部门后离职 | 记录；清理 |
| 25 | ATS webhook：重试策略、`triggeredAt` 单位、签名串 = 原始字节？加密时签名对象（webhooks.md） | 测试租户点「导入EHR」，回调先返回 500 观察重试，再返回 200；开 AES 后再推一次 | 记录 |
| 26 | ATS webhook AES 密钥 / IV 格式（webhooks.md） | 向 CSM 索取后用 `decrypt_webhook_data` 解 | 能解 → 确认格式 |
| 27 | People 推送超时 1s vs 3s（webhooks.md） | 回调里 sleep 2s 返回 200 | 是否触发重推 |
| 28 | ATS 除 HC 外的限流与超限返回（errors-and-limits.md） | **不做压力测试**；只从生产日志观察 | — |
| 29 | 无时区时间字符串的时区（errors-and-limits.md） | 同 #14 | — |

## P2：每类关键结论各测一次

| # | 结论 | 测法 | 判定 |
|---|---|---|---|
| 30 | `PUT /v2/departments` 漏传部门会标记删除 | 测试租户：全量同步 A、B；再只传 A | `result.delete=1`、B `deletedByApi=1`；随后恢复 |
| 31 | `POST /v2/departments/sync/incremental` 只新增 | 新增 C | 不影响 A、B |
| 32 | `/v2/users/syncInfo` `departmentCode:[]` = 所有部门；首次 `deactivated=1` 不创建 | 各测一次 | 与文档一致 |
| 33 | `/v3/data/getApplictaions` 真实可用、每批 ≤ 20 | 传 21 个 ID | 记录报错 |
| 34 | `PUT /v1/applications/{id}/hired` 传 `hcId: null` 报错 | 测试申请 | 与文档一致 |
| 35 | People 员工写接口两层信封 | 新增重复工号员工 | 外层 code 0、内层逐条 success=false |
| 36 | People 限流 HTTP 600 | **不主动触发**；观察生产 | — |

## 需要资料包 / 外部文档才能确认的点（本次未下载）

- 「系统内置字段code映射表.xlsx」（ATS 文档链接的 OSS 文件）：内置字段 code 对照，可能影响 `customData` / 字段映射。
- 《Moka ATS 标准交付集成开发方案》（石墨文档）与《Moka People 用户帮助中心 - 文档&集成》：鉴权、签名、密钥配置流程的官方说明。
- 以上拿到后，优先核对 People RSA 密钥来源（auth.md 第 6.2 节 ⚠）。
