# 企业微信 skill 验证计划（待真实凭证）

当前状态：文档版，抓取于 2026-09-11，**未用真实凭证验证**；无凭证探测见 `probe-log.md`。
需要的测试资源：一个测试企业（可用企业微信免费注册的测试企业）、一个自建应用（可见范围含 2 名测试成员）、
通讯录同步 secret、客户联系与审批的“可调用接口的应用”配置、一个可公网访问的回调 URL、一个测试群机器人。
所有凭证只走环境变量；测试完删除测试成员 / 部门 / 标签 / 「联系我」/ 审批单，全仓库 grep 凭证前缀。

## P0：开头三件事（错了全盘皆错）

| # | 要验证的结论 | 怎么测 | 判定 | 成本 |
|---|---|---|---|---|
| 1 | gettoken 成功返回 `expires_in: 7200`、token ≤512 字节 | 用自建应用 secret 调 gettoken | 字段与文档一致 | 0 |
| 2 | 真实 token 放 `Authorization: Bearer` 头仍报 41001（无凭证探测已证实假 token 的情况） | 同一真实 token 分别放 header / query 调 `user/get` | header → 41001，query → 0 | 0 |
| 3 | 自建应用 token 调 `user/create` → 48002；通讯录同步 token 调 `message/send` → 48002 | 各调一次 | 错误码与文档一致 | 0 |
| 4 | 新建自建应用未配可信 IP → 60020；配置后约 1 分钟生效 | 从未配置的 IP 调用，再配置后轮询 | 60020 → 0 | 0 |

## P1：⚠ 清单（文档矛盾 / 未说明）

| # | ⚠ 条目 | 测法 | 判定 |
|---|---|---|---|
| 5 | 临时素材图片上限 10MB vs 5MB | 上传 6MB、11MB JPG | 6MB 成功 → 以 90253 为准；失败 → 45001 为准 |
| 6 | 语音上限 2MB vs 5MB | 上传 3MB AMR | 同上 |
| 7 | `user/list` 是否认 `fetch_child=1` | 带 / 不带 fetch_child 调子部门成员 | 返回是否包含子部门成员 |
| 8 | 通讯录同步 secret 能否创建 / 删除部门；非空部门能否删除 | department/create、department/delete | 记录错误码 |
| 9 | getcallbackip 是否返回带 `*` 的 IP 段 | 调一次 | 记录格式 |
| 10 | applyevent 省略 `use_template_approver` 是否等同 0 | 省略该字段且不传 process | 报错 → 实为必填 |
| 11 | `new_money` 单位与小数 | 提交 `"12.34"`，getapprovaldetail 读回，并在客户端查看 | 显示 12.34 元还是 0.12 元 |
| 12 | getapprovalinfo 游标字段 | 拉 >100 条 | 返回的是 `new_next_cursor` 还是 `next_cursor` |
| 13 | 欢迎语附件 msgtype=file 是否可用 | send_welcome_msg 带 file 附件 | 成功 / 报错 |
| 14 | remark_mobiles 清空写法 | 分别传 `""` 与 `[""]` | 哪种清空成功 |
| 15 | 回调 echostr / Encrypt 中 `+` 的编码 | 抓 10 次真实回调原始 query | 是否出现未编码的 `+` |
| 16 | 回调 XML / JSON 格式切换入口 | 管理后台查看接收消息设置 | 是否存在 JSON 选项 |
| 17 | 取消关注事件的 Event 字面值 | 测试成员取消关注应用 | 记录 Event 值 |
| 18 | gettoken 频率上限 | **不测**（会触发 IP 封禁），只观察生产日志 | — |

## P2：每类关键结论各测一次

| # | 结论 | 测法 | 判定 |
|---|---|---|---|
| 19 | message/send 部分无效接收人 → errcode 0 + invaliduser；全部无效 → 81013 | touser 混入不存在的 userid；再全不存在 | 与文档一致 |
| 20 | touser 传数组会怎样（静默失效还是报错） | `"touser": ["a","b"]` | 记录 errcode——**重点关注静默失效** |
| 21 | tag/addtagusers 的 userlist 传 `"a\|b"` 字符串 | 调一次 | 是否 40035 / 40070 |
| 22 | 回调解密 PKCS#7 32 字节 | 用 `callbacks-crypto.md` 的实现接一次真实回调，并用 16 字节 unpad 对比 | 32 字节实现成功 |
| 23 | 被动回复加密包能被企业微信接受 | 对“进入应用”事件被动回复 text | 成员收到回复 |
| 24 | 客户联系 API 操作不产生回调 | 用 API mark_tag 后观察回调 | 无 edit_external_contact 事件 |
| 25 | WelcomeCode 20 秒时效 | 收到事件后 25 秒再调 send_welcome_msg | 41050 |
| 26 | add_msg_template 不直接下发 | 创建群发后查看客户是否收到 | 需成员确认才收到 |
| 27 | webhook image 用 base64+md5；file 必须用 webhook/upload_media 的 media_id | 用应用 media/upload 的 media_id 发机器人 file | 报错码 |
| 28 | HTTP→HTTPS：真实 token 用 `http://` POST | POST http://…/externalcontact/remark | 301 后 body 是否丢失 |

## 验证后要做的事

- 每条结论改回对应 reference，写「已用真实 API 验证（日期）：…」+ 原始报错 / 响应片段；文档本身错的加 `<!-- Gap: … -->` 并升到 SKILL.md。
- 用 `evals/evals.json` 跑 with / without skill 对照，写 `comparison-report.md`（Markdown）。
- 同步更新 `site.json` 的 probed / gotchas 与产品站数字。
