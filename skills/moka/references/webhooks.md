# 主动推送（Webhooks）：ATS 与 People 两套机制

> 来源：ATS「主动推送说明（Webhooks）」<https://www.mokahr.com/docs/api/#webhooks>、
> People「主动推送API（Webhooks）」<https://people.mokahr.com/docs/api/view/v1.html#api-webhooks>（均抓取于 2026-09-11）。
> **文档版，未用真实凭证 / 真实推送验证。** 行为描述除标「本地复算」外均为「文档原文，未实测」。

## 目录

1. [两套推送一眼对比](#1-两套推送一眼对比)
2. [ATS：配置与请求格式](#2-ats配置与请求格式)
3. [ATS：签名校验（HMAC-SHA256）](#3-ats签名校验hmac-sha256)
4. [ATS：可选的 data 字段加密（AES-256-CBC）](#4-ats可选的-data-字段加密aes-256-cbc)
5. [ATS：事件与负载](#5-ats事件与负载)
6. [ATS：怎么回复、怎么让用户跳转](#6-ats怎么回复怎么让用户跳转)
7. [People：配置、请求方式与校验](#7-people配置请求方式与校验)
8. [People：事件清单与枚举](#8-people事件清单与枚举)
9. [People：超时、重试与幂等](#9-people超时重试与幂等)
10. [Python 接收端示例（Flask）](#10-python-接收端示例flask)
11. [⚠ 汇总](#11--汇总)

---

## 1. 两套推送一眼对比

| 项 | ATS（招聘） | People（人事） |
| :--- | :--- | :--- |
| 谁来配置 | 把公网 HTTPS URL 交给 **CSM** 配置，CSM 回给你一个 **signing key** | 自己在 People「设置 - 对外接口设置」里配置推送接口与 HTTPS URL |
| 方法 | `POST`，JSON body | **多数是 `GET`**，参数全在 query；少数（待办、消息、部分假勤 / 绩效）是 `POST` JSON |
| 负载 | 完整业务数据（候选人、面试…） | **只有 ID**（`employeeId`、`nodeUid`…），详情要回调查询接口 |
| 真实性校验 | `?sign=` = HMAC-SHA256(signing key, body) 的十六进制 | `pwd` = 你在「对外接口设置」配的密钥，**明文放在 URL 里**；无签名 |
| 可选加密 | AES-256-CBC 加密 `data` 字段（找 CSM 开通） | 无 |
| 成功回复 | 任意 2xx | HTTP 200 + JSON `{"code":"200","msg":"success","data":""}` |
| 重试 | ⚠ 文档未说明 | 15s、5m、1h、6h，最多 4 次；URL 带 `requestUniqueKey`，重试不变 |
| 鉴权 | 推送请求**不带** API Key（文档原文） | 请求头 Header：无 |

## 2. ATS：配置与请求格式

- 文档原文：「请提供给CSM一个公网可以访问的HTTPS的URL……我们配置好后会提供给你一个签名密钥（signing key）」。
- **只支持 HTTPS endpoint**，但文档原文说 Moka「并不会去向CA验证证书的有效性，所以你可以提供self-signed证书」。
- 请求：`POST <你的 URL>?sign=<hex>`，`Content-Type` JSON，统一信封：

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | string | 唯一标识该请求 |
| `event` | string | 事件类型，如 `pushCandidate` |
| `triggeredAt` | timestamp | 触发时间。⚠ 文档未说明单位：示例 `1505296287` 是**秒**，而面试负载里的时间字段是**毫秒** |
| `data` | object | 事件数据（开通加密后变成十六进制密文字符串） |

- 另有 WebService（SOAP）方式：把 WSDL 地址交给 CSM；方法名 `pushCandidate`，参数为 xml（字段同 JSON），返回 `true` / `false`；
  签名使用 Bearer 方式（文档指向 node-soap 的 `BearerSecurity`）。只有 RESTful 方式支持跳转（第 6 节）。

## 3. ATS：签名校验（HMAC-SHA256）

文档原文：签名放在请求 URL 的 query 里，例如 `https://your-endpoint.com/moka?sign=d23da96c…`；
「需要你用signing key作为密钥、请求body作为内容，通过`HMAC-SHA256`来计算得出结果，并与请求URL中的signature进行比较」。
文档 JS 示例是 `crypto.createHmac('sha256', signKey).update(JSON.stringify(body)).digest('hex')`。

**本地复算（2026-09-11，无网络）**：文档示例 body `{name:'test', email:'test@mokahr.com'}`、key `qwer`：

| 被签名的字符串 | HMAC-SHA256 hex | 与文档一致？ |
| :--- | :--- | :--- |
| `{"name":"test","email":"test@mokahr.com"}`（紧凑 JSON，等价 `JSON.stringify`） | `7d6981ccf0d789e29e4f5940fe9a7e9385d8a211ad44ecaaba335fb14dd2a32d` | **一致** |
| `{"name": "test", "email": "test@mokahr.com"}`（Python `json.dumps` 默认带空格） | `7c94db41…f08b105` | 不一致 |

所以：

- **对原始请求体字节做 HMAC**（Flask `request.get_data()`），不要先 `json.loads` 再 `json.dumps`——Python 默认分隔符带空格、默认把中文转成 `\uXXXX`，都会让签名对不上。
- 如果框架已经把 body 解析掉、拿不到原始字节，退而求其次用 `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))`（等价 `JSON.stringify`，保持原键序）。
- 用 `hmac.compare_digest` 做常量时间比较；hex 按小写比。
- ⚠ 文档未说明：Moka 发送的 body 字节是否与它签名时 `JSON.stringify` 的结果完全一致（例如是否有换行、键序）。上面的"原始字节优先、紧凑 JSON 兜底"就是为此。
- ⚠ 文档未说明：开通 data 加密后，签名是对加密前还是加密后的 body 计算。

## 4. ATS：可选的 data 字段加密（AES-256-CBC）

文档原文：加密算法 AES-256，16 进制，CBC 模式；**只加密 body 里的 `data` 字段**，不加密 `id`、`event`、`triggeredAt`；开通与设置密钥找 CSM。

文档给的 Node 示例：加密 `createCipheriv('aes-256-cbc', signKey, signIv)` + `update(JSON.stringify(data),'utf8','hex')`。

**⚠ 文档示例代码有误（本地执行证实，2026-09-11，复跑两次一致）**：文档的解密函数写成
`createDecipheriv(...).update(signStr, 'utf8', 'hex')` 与 `final('hex')`——输入编码和输出编码写反了。
用文档自己的加密函数生成密文、再用文档解密函数解，Node 抛 `ERR_OSSL_BAD_DECRYPT`；改成 `update(hex, 'hex', 'utf8') + final('utf8')` 才得到原文。

Python 解密（本地复算：能正确解出上述 Node 加密结果）：

```python
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sympad

def decrypt_webhook_data(hex_str: str, key: str, iv: str) -> str:
    """key / iv 按 UTF-8 字节使用（Node createCipheriv 传字符串时的行为）：key 32 字节、iv 16 字节。"""
    d = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv.encode("utf-8"))).decryptor()
    padded = d.update(bytes.fromhex(hex_str)) + d.finalize()
    u = sympad.PKCS7(128).unpadder()                      # Node 默认 PKCS#7 填充
    return (u.update(padded) + u.finalize()).decode("utf-8")   # 得到 JSON 字符串，再 json.loads
```

- ⚠ 文档未说明：CSM 给的密钥 / IV 是什么格式（原始字符串、hex 还是 Base64）、长度多少。上面按"32 字符 key + 16 字符 IV 的原始字符串"实现，拿到真实密钥后先确认。

## 5. ATS：事件与负载

### 5.1 `pushCandidate`（推送候选人信息）
**触发**：文档原文「目前在Moka中是由"导入EHR"按钮点击触发」——是 HR **手动点按钮**才推，不是阶段变化自动推。
**用途**：待发 offer 的候选人推到 OA / EHR 审批，待入职候选人推到 EHR 建档。

关键字段（文档示例整理，完整字段表见文档「推送候选人信息」）：

| 字段 | 说明 |
| :--- | :--- |
| `data.applicationId` / `data.candidateId` | 申请 ID / 候选人 ID，后续调 ATS 接口用 |
| `data.name` `phone` `email` `gender` `birthDate` `citizenId` `certificateType` | 候选人基本信息（示例里 `birthDate` 是 ISO8601 字符串） |
| `data.stageName` | 当前阶段名，如「待入职」 |
| `data.job` | `{title, department, departmentCode, parentDepartmentCode, departmentPath, jobId, jobDescription, customFields[]}` |
| `data.jobManager` / `data.operator` | 职位负责人 / 点按钮的操作人（含 email、工号） |
| `data.educationInfo[]` / `experienceInfo[]` / `customFields[]` | 教育、工作经历、自定义字段（`customFields[].section` 标明属于哪个模块） |
| `data.resumeUrl` | 简历下载地址，是带 `Expires` 的签名 OSS 链接——**收到后尽快下载转存**，不要只存 URL |
| `data.hireMode` | 1 社招 / 2 校招 |

### 5.2 `createInterviewsInfo` / `updateInterviewsInfo` / `deleteInterviewsInfo`（推送面试信息）
**触发**：文档原文「由添加面试完成确认按钮点击时触发」。

| 字段 | 说明 |
| :--- | :--- |
| `data.applicationIds[]` | 涉及的申请 ID |
| `data.interviewType` | 1 现场 / 2 集体 / 3 电话 / 4 视频 / 5 叫号 |
| `data.createTime` | 毫秒时间戳 |
| `data.creator` | `{id, name, email, phone}` |
| `data.interviews[]` | 每场：`event_id`、`applicationIds`、`roundId`/`roundName`、`roomId`/`roomName`、`address{id,country,cityId,address}`、`startTime`/`endTime`（**毫秒**时间戳）、`interviewerIds`、`interviewee[]{id,name,email,phone,jobId,jobTitle,intervieweeUrl}`、`interviewer[]{id,name,email,phone,interviewerUrl}` |

- ⚠ 文档字段类型有误：信封表把 `id`、`event`、`triggeredAt` 的类型都写成 `array`，示例里是字符串 / 数字；`interviews[].event_id` 也标成 `array`，示例是字符串。按示例处理。

## 6. ATS：怎么回复、怎么让用户跳转

- 文档原文：「成功接收并处理webhook请求后，返回2xx即可。Moka在接收到非2xx的结果时，会提示用户导入失败」；错误信息可放 body，如 `{"msg":"当前数据存在错误"}`。
  因为是 HR 点按钮触发，**失败信息会直接展示给 HR**，写成人能看懂的中文。
- ⚠ 文档自相矛盾：「推送面试信息」一节又给了返回表 `code`（0 成功、非 0 失败）、`msg`、`data`。稳妥做法：**HTTP 200 + `{"code":0,"msg":"success"}`**，同时满足两种说法。
- 跳转外部系统（仅 RESTful）：在响应 body 里返回

```json
{"redirectUrl": {"pcUrl": "https://oa.example.com/offer/123?token=…", "mobileUrl": "https://m.oa.example.com/offer/123?token=…"}}
```

  Moka 会按用户设备跳 PC 或移动端。⚠ 文档字段表把 `redirectUrl` 类型写成 `array`，示例是对象——按示例用对象。文档建议链接带临时 token 以免二次登录。

## 7. People：配置、请求方式与校验

- 在 People「对外接口设置」里建推送接口：选**数据源**（如【员工任职信息】）和**监控信息类型**（如【入职】【信息变更】），填公网 HTTPS URL。
- **多数事件是 GET**，参数在 query，例如员工入职通知：

```
https://您的公网回调地址?apiCode=9db2672b8fb19d&employeeId=3873&modifyType=1&sourceType=1&pwd=1
```

  文档还写明推送 URL 会统一增加唯一流水号参数 `requestUniqueKey`。

| 参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `apiCode` | String | 该推送接口的接口编码——用它区分是哪条推送配置 |
| `pwd` | String | 你在「对外接口设置」配的密钥，文档原文「客户可以校验数据的合法性」。标为「否」必填：没配就不会有 |
| `sourceType` | int | 数据源，见第 8 节枚举 |
| `modifyType` | int | 变更类型，见第 8 节枚举 |
| `employeeId` / `obId` / `nodeUid` / `positionId` / `dutyId` | Long / String | 按 sourceType 出现，见第 8 节 |
| `ts` | Long | 推送时间 |
| `requestUniqueKey` | — | 推送流水号，重试不变 |

- **校验只能靠 `pwd` + `apiCode`**，没有签名：一定要配 `pwd`，用常量时间比较；日志里别打印完整 URL（pwd 在里面）。
- **推送只给 ID**：拿 `employeeId` 调 `POST /v1/batch/data`（`uuidList=[employeeId]`）取详情，见 `people-hr.md`。
- **POST 类事件**（9 个：待办和消息 - 消息通知 / 待办通知；假勤 - 外出、加班审批单、班次变更、排班变更；绩效 - 三个活动通知）：请求头无、body 为 JSON。
  例如待办通知 body 字段：`flowTaskInsId`、`taskType`（0 发起 / 1 审批 / 2 抄送 / 7 任务 / 8 试用期 / 9 绩效）、`editType`（1 新增 / 2 修改 / 3 删除 / 4 继承）、
  `taskStatus`（1 未完成 / 2 已完成 / 3 取消）、`title`、`content`、`taskEmployeeId`、`flowInstanceId`、`flowInstanceResult`（0 审批中 / 1 结束）、`taskResult`（1 拒绝 / 2 同意）、`url`。
  文档原文：接入标准消息的前提是接入 People 单点登录。
- 文档原文：每天凌晨 People 会按生效日期自动处理变更，所以「用户发现自身未操作数据但是收到了推送的变更数据，属于正常情况」——**别把"无人操作的推送"当异常告警**。

## 8. People：事件清单与枚举

`sourceType` / `modifyType` 枚举（文档「附录：组织人事通知的枚举类」原文）：

| sourceType | 含义 | modifyType | 携带的 ID |
| :--- | :--- | :--- | :--- |
| `1` | 员工任职信息 | `1` 入职（确认入职）、`2` 离职、`3` 信息变更 | `employeeId` |
| `2` | 组织架构 | `1` 新增、`2` 停用、`3` 编辑 | `nodeUid` |
| `3` | 职务信息 | `1` 新增、`2` 停用、`3` 编辑 | `dutyId`（modifyType=2、3 且职务模式租户） |
| `4` | 职位信息 | `1` 新增、`2` 停用、`3` 编辑 | `positionId`（modifyType=2、3 且职位模式租户） |
| `5` | 入职状态 | `1` 已入职（弃用）、`2` 放弃入职 | `employeeId`、`obId`（入职 id） |
| `6` | 兼岗信息 | `3` 信息变更 | `employeeId` |

文档列出的全部推送（按文档顺序）：

| 分组 | 事件 | 方法 |
| :--- | :--- | :--- |
| 人事 | 新增 / 变更 / 取消待入职员工；员工入职；员工信息变更；员工转正；员工离职；离职办理通过；离职审批通过；兼岗信息变更；家庭成员变更；合同信息变更 | GET |
| 组织 | 新增 / 编辑 / 停用部门 | GET |
| 职务 / 职位 | 新增 / 停用 / 编辑职务或职位 | GET |
| 待办和消息 | 消息通知、待办通知 | POST |
| 假勤 | 出差 / 请假审批单（GET）；外出 / 加班审批单、班次变更、排班变更（POST） | 混合 |
| 绩效 | 活动状态变更、活动环节状态变更、活动被评估人变更 | POST |

每个事件的触发场景（例如「员工信息变更」包括移动端自助改信息、花名册修改、发起异动 / 转正 / 离职审批、导入平台更新）见文档对应小节。

## 9. People：超时、重试与幂等

- ⚠ 文档自相矛盾：「重试机制」一节写「需要在**1秒内**以HTTP 200状态码响应」；「如何使用webhooks」一节写「超时时间 **<= 3s**」。按 1 秒设计：**先回 200，再异步处理**。
- 回复格式（文档原文）：`{"code":"200", "msg":"success", "data":"" }`，JSON。注意 `code` 是字符串 `"200"`。
- 重试（文档原文）：失败后以 **15s、5m、1h、6h** 间隔重推，**最多 4 次**；`requestUniqueKey` 重试时不变 → 用它做幂等键。
- 文档原文要求客户端保障幂等；回调地址须公网可达。

## 10. Python 接收端示例（Flask）

```python
import hashlib, hmac, json, os, threading
from flask import Flask, request, jsonify

app = Flask(__name__)
ATS_SIGN_KEY = os.environ["MOKA_WEBHOOK_SIGN_KEY"].encode()
PEOPLE_PWD = os.environ["MOKA_PEOPLE_WEBHOOK_PWD"]
seen_keys = set()                      # 生产换成 Redis / 数据库唯一键

def ats_sign_ok(raw: bytes, sign: str) -> bool:
    cands = [raw]
    try:                               # 兜底：等价 JSON.stringify 的紧凑序列化
        cands.append(json.dumps(json.loads(raw), ensure_ascii=False, separators=(",", ":")).encode())
    except ValueError:
        pass
    return any(hmac.compare_digest(hmac.new(ATS_SIGN_KEY, c, hashlib.sha256).hexdigest(), sign.lower())
               for c in cands)

@app.post("/moka/ats-webhook")
def ats_webhook():
    raw = request.get_data()           # 原始字节，别先解析
    if not ats_sign_ok(raw, request.args.get("sign", "")):
        return jsonify({"code": 1, "msg": "签名校验失败"}), 401
    evt = json.loads(raw)
    if evt["event"] == "pushCandidate":
        d = evt["data"]                # 开通加密时：json.loads(decrypt_webhook_data(d, KEY, IV))
        # ... 写入 EHR；失败时返回非 2xx + 中文 msg，HR 会在 Moka 里看到
        return jsonify({"code": 0, "msg": "success"}), 200
    if evt["event"] in ("createInterviewsInfo", "updateInterviewsInfo", "deleteInterviewsInfo"):
        return jsonify({"code": 0, "msg": "success"}), 200
    return jsonify({"code": 0, "msg": "ignored"}), 200

@app.route("/moka/people-webhook", methods=["GET", "POST"])
def people_webhook():
    q = request.args
    if not hmac.compare_digest(q.get("pwd", ""), PEOPLE_PWD):
        return jsonify({"code": "401", "msg": "bad pwd", "data": ""}), 401
    key = q.get("requestUniqueKey") or f'{q.get("apiCode")}:{q.get("sourceType")}:{q.get("modifyType")}:{q.get("employeeId") or q.get("nodeUid")}:{q.get("ts")}'
    if key not in seen_keys:
        seen_keys.add(key)
        payload = dict(q) | (request.get_json(silent=True) or {})
        threading.Thread(target=handle_people_event, args=(payload,), daemon=True).start()
    return jsonify({"code": "200", "msg": "success", "data": ""}), 200   # 1 秒内返回

def handle_people_event(p: dict):
    if p.get("sourceType") == "1" and p.get("employeeId"):
        pass  # 调 POST /v1/batch/data {"uuidList":[int(p["employeeId"])], "pageSize":1, "pageNum":1} 取详情
```

## 11. ⚠ 汇总

- ⚠ 文档未说明：ATS 推送失败是否重试、重试间隔。
- ⚠ 文档未说明：ATS `triggeredAt` 单位（示例为秒）；签名串是否与发送字节完全一致；加密时签名对象；AES 密钥 / IV 格式。
- ⚠ 文档示例代码有误（本地执行证实）：ATS 解密示例 `update(signStr,'utf8','hex')` 编码写反，会抛 `ERR_OSSL_BAD_DECRYPT`。
- ⚠ 文档自相矛盾：ATS 回复"2xx 即可" vs 面试推送返回表要求 `code:0`；`redirectUrl` 类型 array vs 示例对象；信封字段类型标 `array`。
- ⚠ 文档自相矛盾：People 响应时限 1 秒 vs ≤ 3 秒。
