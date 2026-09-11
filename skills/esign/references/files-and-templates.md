# 文件上传与模板填充（SaaS API V3）

> 内容整理自 e签宝开放平台《合同文件签署服务API V3》文件类 / 合同模板类、《流程模板签署服务API》、
> 帮助文档《文件上传常见报错及解决方法》《如何计算文件的Content-MD5值》（抓取于 2026-09-11）。
> **未用真实凭证调用验证**；下文的报错与行为除特别注明外均为「文档原文，未实测」。
> 示例里的 `esign_request()` 是 [auth-and-signing.md §5](auth-and-signing.md) 的签名封装。

## 目录

1. [先选：待签文件从哪来](#1-先选待签文件从哪来)
2. [上传本地文件 · 步骤一：获取上传地址](#2-上传本地文件--步骤一获取上传地址)
3. [上传本地文件 · 步骤二：PUT 文件流](#3-上传本地文件--步骤二put-文件流)
4. [查询文件上传状态（必须轮询）](#4-查询文件上传状态必须轮询)
5. [检索文件关键字坐标](#5-检索文件关键字坐标)
6. [文件模板（docTemplate）：制作 / 查询 / 填写生成文件](#6-文件模板doctemplate制作--查询--填写生成文件)
7. [流程模板（signTemplate）简述](#7-流程模板signtemplate简述)
8. [一段可运行的完整流程（Python）](#8-一段可运行的完整流程python)
9. [⚠ 本文件的未说明 / 矛盾之处](#9--本文件的未说明--矛盾之处)

---

## 1. 先选：待签文件从哪来

文档《SaaS API 产品概念说明》给了三条路：

| 方式 | 用到的接口 | 适合 |
| --- | --- | --- |
| ① 直接上传完整文件 | `POST /v3/files/file-upload-url` → PUT 文件流 → `GET /v3/files/{fileId}` | 业务系统自己能生成 PDF |
| ② 文件模板填充生成 | 上传底稿 → `POST /v3/doc-templates/doc-template-create-url`（人工在页面拖控件）→ `POST /v3/files/create-by-doc-template` | 同一份合同反复填不同数据 |
| ③ 流程模板直接发起 | `POST /v3/sign-flow/create-by-sign-template` | 企业在 e签宝官网配好了填写方 / 签署方 / 顺序 |

①② 最终都得到一个 **fileId**，再交给 `POST /v3/sign-flow/create-by-file` 发起签署（见 [sign-flows.md](sign-flows.md)）。
③ 一步生成合同拟定 + 签署流程。

几个跨方式的规则（文档原文）：
- 文件模板（docTemplate）归属开发者，不需要用户授权；流程模板（signTemplate）归属企业用户，用别家企业的要先拿授权。
- **沙箱与正式环境的模板不互通，要分别制作**；接口制作的文件模板不会同步到 e签宝 SaaS 官网。
- 文件名不可含 `/ \ : * " < > | ？` 及 emoji，长度 ≤100 字符；必须带真实扩展名。

---

## 2. 上传本地文件 · 步骤一：获取上传地址

**Endpoint**: `POST /v3/files/file-upload-url`
**用途**: 拿到 `fileId`（此时状态为“未上传”）和一个 60 分钟有效的 `fileUploadUrl`。这一步**只传文件元信息，不传文件内容**。

**关键参数**（body，JSON）

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| contentMd5 | string | 是 | — | 文件的 Content-MD5：`Base64(MD5 原始 16 字节)`，**不是** 32 位 hex 再 Base64 |
| contentType | string | 是 | — | 只能 `application/octet-stream` 或 `application/pdf`；步骤二 PUT 的 Content-Type 必须与它一致，否则 403 |
| fileName | string | 是 | — | 必须带真实扩展名（`合同.pdf`、`合同.docx`），扩展名要与真实文件类型一致 |
| fileSize | int64 | 是 | — | 字节数 |
| convertToPDF | boolean | 否 | false | 非 PDF 文件要用于签署或做 PDF 模板时**必须 true**；已是 PDF 就传 false / 不传 |
| convertToHTML | boolean | 否 | false | 仅 .doc/.docx；做 HTML 模板时必须 true |
| convertToOFD | boolean | 否 | false | OFD 不支持专属云、海外签、批量签、解约、水印、模板、关键字定位 |
| dedicatedCloudId | string | 否 | — | 专属云项目 ID（普通对接不用） |
| internalUrl | boolean | 否 | false | 专属云内网地址（普通对接不用） |

限制：单文件 ≤50MB，单页 ≤20MB。支持 pdf / docx / doc / rtf / xlsx / xls / pptx / ppt / wps / et / dps / jpeg / jpg / png / bmp / tiff / tif / gif / html / htm；
除 pdf 外都需转换。文档建议“直接传 PDF，其他格式本地先转”，避免转换耗时和版式问题。

**示例请求**

```bash
# 签名头的计算见 auth-and-signing.md；这里只展示 body
curl -X POST "$ESIGN_HOST/v3/files/file-upload-url" \
  -H "X-Tsign-Open-App-Id: $ESIGN_APP_ID" -H 'X-Tsign-Open-Auth-Mode: Signature' \
  -H "X-Tsign-Open-Ca-Timestamp: $TS" -H "X-Tsign-Open-Ca-Signature: $SIG" \
  -H 'Accept: */*' -H 'Content-Type: application/json; charset=UTF-8' -H "Content-MD5: $BODY_MD5" \
  --data '{"contentMd5":"<文件的Content-MD5>","contentType":"application/pdf","convertToPDF":false,"fileName":"劳动合同.pdf","fileSize":25426}'
```

```python
import base64, hashlib, os

def file_content_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode()      # 注意是 digest() 不是 hexdigest()

path = "劳动合同.pdf"
r = esign_request("POST", "/v3/files/file-upload-url", body={
    "contentMd5": file_content_md5(path),
    "contentType": "application/pdf",
    "convertToPDF": False,
    "fileName": os.path.basename(path),
    "fileSize": os.path.getsize(path),
})
file_id, upload_url = r["data"]["fileId"], r["data"]["fileUploadUrl"]
```

**示例响应**（文档原文，节选）

```json
{"code": 0, "message": "成功",
 "data": {"fileId": "c64665aa4f***33cd773", "fileUploadUrl": "https://esignoss.esign.cn/...?Expires=...&OSSAccessKeyId=...&Signature=..."}}
```

**注意事项**
- 这里有**两个不同的 MD5**：body 里的 `contentMd5` 是**文件**的；请求头 `Content-MD5` 是**这段 JSON body** 的（参与请求签名）。
- 错误码（文档原文，未实测）：`1430002 参数错误: 文件名字长度不能大于100 / 文件大小不能为0 / 当前文件类型不支持转换HTML`，`1430601 创建合同失败: 文件名含有特殊字符`。

---

## 3. 上传本地文件 · 步骤二：PUT 文件流

**Endpoint**: `PUT {fileUploadUrl}`（步骤一返回的完整 URL，指向 OSS，不是 openapi 域名）
**用途**: 把文件二进制上传到 OSS。**不要带 e签宝的签名头**，这一步由 URL 里的 OSS 签名鉴权。

**请求头**

| 头 | 必填 | 说明 |
| --- | --- | --- |
| Content-MD5 | 是 | 与步骤一 body 的 `contentMd5` 完全一致 |
| Content-Type | 是 | 与步骤一 body 的 `contentType` 完全一致（`application/octet-stream` 或 `application/pdf`） |

Body 是文件原始字节（上传印章图片也是字节流，不要传 Base64 字符串）。

```bash
curl -X PUT "$UPLOAD_URL" -H "Content-MD5: $FILE_MD5" -H 'Content-Type: application/pdf' --data-binary @劳动合同.pdf
```

```python
import requests
with open(path, "rb") as f:
    resp = requests.put(upload_url, data=f.read(), timeout=120,
                        headers={"Content-MD5": file_content_md5(path), "Content-Type": "application/pdf"})
print(resp.status_code, resp.text)   # 成功时文档示例为 {"errCode":0,"msg":"成功"}
```

**响应**：`{"errCode": 0, "msg": "成功"}`——注意字段名是 `errCode` / `msg`，不是 `code` / `message`。
**`errCode == 0` 只代表 OSS 收到了，不代表文件可用**，转换与状态更新是异步的，必须走 §4 轮询。

**OSS 常见报错**（帮助文档原文，未实测）

| HTTP | OSS Code / 消息 | 原因 |
| --- | --- | --- |
| 405 | MethodNotAllowed | 没用 PUT |
| 400 | InvalidDigest | 请求头 Content-MD5 与实际字节流算出的不一致 |
| 403 | SignatureDoesNotMatch | 用了 GET/DELETE；或 Content-MD5 / Content-Type 与步骤一 body 不一致；或字节流与算 MD5 时的不一致 |
| 403 | AccessDenied `Request has expired.` | 上传地址已过 60 分钟，重新走步骤一 |
| 403 | AccessDenied `Query string authentication requires...` / `bucket acl` | URL 被截断或被 HTML 转义（`&amp;`），原样使用 URL |
| 403 | InvalidAccessKeyId | URL 中 `security-token` 不完整或含转义字符 |

---

## 4. 查询文件上传状态（必须轮询）

**Endpoint**: `GET /v3/files/{fileId}`
**用途**: 确认文件已上传 / 转换完成，拿文件名、页数、临时下载地址。**只有 `fileStatus` 为 2 或 5 时 fileId 才能用于发起签署或做模板。**

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| fileId | path | 是 | 文件 ID |
| pageSize | query | 否 | 布尔，默认 false；true 时返回首页宽高 `pageWidth`/`pageHeight`（px） |

`fileStatus` 枚举（文档原文）：0 未上传，1 上传中，**2 上传完成 / 已转 HTML**，3 上传失败，4 等待转 PDF，**5 已转 PDF**，
6 加水印中，7 加水印完毕，8 转 PDF 中，9 转 PDF 失败，10 等待转 HTML，11 转 HTML 中，12 转 HTML 失败。

文档建议的轮询规则：2 或 5 立即停止；1、4、6、8、10、11 每 3 秒重试；总时长不超过 90 秒，超时按异常处理。
（3、9、12 是失败终态，文档没写重试建议，按失败处理。）

```python
import time

def wait_file_ready(file_id: str, timeout_s: int = 90) -> dict:
    deadline = time.time() + timeout_s
    while True:
        d = esign_request("GET", f"/v3/files/{file_id}")["data"]
        st = d["fileStatus"]
        if st in (2, 5):
            return d
        if st in (3, 9, 12):
            raise RuntimeError(f"file {file_id} failed, fileStatus={st}")
        if time.time() > deadline:
            raise TimeoutError(f"file {file_id} not ready after {timeout_s}s, fileStatus={st}")
        time.sleep(3)
```

响应字段：`fileId`、`fileName`、`fileSize`（预留，恒为空）、`fileStatus`、`fileDownloadUrl`（60 分钟有效）、`fileTotalPageCount`、`pageWidth`、`pageHeight`。
错误码（文档原文）：`1430608 查询合同信息失败: 合同不存在`、`1430802 操作人无权限`。

---

## 5. 检索文件关键字坐标

**Endpoint**: `POST /v3/files/{fileId}/keyword-positions`（推荐）；旧版 `GET /v3/files/{fileId}/keyword-positions?keywords=a,b`（不推荐）
**用途**: 在文本型 PDF 里找关键字坐标，用来给签署区 `positionX/positionY` 定位。扫描件 / 图片 PDF 查不到。

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| fileId | path | 是 | 已上传的文件 |
| keywords | body（list） | 是 | 最多 30 个；不支持 Adobe 无法解析的特殊字符 |

```python
r = esign_request("POST", f"/v3/files/{file_id}/keyword-positions", body={"keywords": ["甲方盖章", "乙方签字"]})
for kp in r["data"]["keywordPositions"]:
    if kp["searchResult"]:
        p = kp["positions"][0]
        print(kp["keyword"], p["pageNum"], p["coordinates"][0])   # {"positionX": 90.0, "positionY": 190.611}
```

**注意事项**
- 返回的是**关键字第一个字的左下角**坐标；直接拿来当签章中心点，章会压在字上，通常要按印章尺寸自行偏移。
  坐标系与印章尺寸的换算文档另有《印章图片尺寸和坐标》帮助页（⚠ 本 skill 未抓取该页）。
- **为什么推荐 POST**：GET 版把中文关键字放在 query 里，实际 URL 要 urlencode，但签名串里的 PathAndParameters 不能编码，
  文档自己也说“因为请求头的签名计算涉及到URL编码问题，不够便捷不再推荐”。
- 错误码（文档原文）：`1437509 解析文档关键字失败，PDF header not found.`、`1435002 参数错误:未指定关键字`、`1437511 文档不存在：%s`。

---

## 6. 文件模板（docTemplate）：制作 / 查询 / 填写生成文件

典型链路：上传底稿（§2–§4）→ 获取制作模板页面，让运营在页面拖控件 → 查控件 ID/Key → 每次业务用数据填充生成新 fileId → 发起签署。

### 6.1 获取制作合同模板页面

**Endpoint**: `POST /v3/doc-templates/doc-template-create-url`

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| docTemplateName | string | 是 | — | 模板名称 |
| docTemplateType | int32 | 否 | 0 | 0 PDF 模板；1 HTML 模板（需要动态增加表格行时用；底稿须是上传时 `convertToHTML=true` 的 doc/docx） |
| fileId | string | 是 | — | 底稿文件 ID |
| redirectUrl | string | 否 | — | 制作完成后跳转 |
| signerRoles | list | 否 | — | 签署方角色标识（如“甲方”“乙方”），之后可在控件详情里按角色查签署区坐标 |
| hiddenOriginComponents / basicComponentsType / customComponents / customComponentGroups / showReplaceFraft | — | 否 | — | 控制页面上可用的控件（字段名 `showReplaceFraft` 原文如此） |

响应：`docTemplateId`（务必保存）、`docTemplateCreateUrl`（短链）/ `docTemplateCreateLongUrl`（长链），**链接 24 小时有效**；
过期后用 `POST /v3/doc-templates/{docTemplateId}/doc-template-edit-url` 重新拿编辑链接。

```python
r = esign_request("POST", "/v3/doc-templates/doc-template-create-url", body={
    "docTemplateName": "劳动合同模板", "docTemplateType": 0, "fileId": base_file_id,
    "signerRoles": ["甲方", "乙方"],
})
tpl_id, create_url = r["data"]["docTemplateId"], r["data"]["docTemplateCreateUrl"]
```

错误码（文档原文）：`1430011 文件底稿还不是已经上传/转换的PDF`（底稿没轮询到 2/5 就调了）、`1430002 templateName不能为空`（⚠ 字段表叫 docTemplateName，报错文案写 templateName）。

### 6.2 查询合同模板中控件详情

**Endpoint**: `GET /v3/doc-templates/{docTemplateId}`
返回 `docTemplateName` 和 `components[]`：`componentId`（系统生成）、`componentKey`（制作时自定义）、`componentName`、`required`、
`componentType`（1 单行文本，2 数字，3 日期，6 签章区域，8 多行文本，9 复选，10 单选，11 图片，14 下拉框，15 勾选框，16 身份证，17 备注区域，18 动态表格，19 手机号，21 签署日期，23 人民币大写）、
`componentPosition`（含 `componentPositionY` 等；**HTML 模板不返回位置**）、`componentSpecialAttribute`。

### 6.3 填写模板生成文件

**Endpoint**: `POST /v3/files/create-by-doc-template`
**用途**: 用 `docTemplateId` + 控件值生成一份新的 PDF，返回新的 `fileId`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| docTemplateId | string | 是 | 模板 ID |
| fileName | string | 是 | 生成文件名（同样的特殊字符 / 100 字符限制） |
| components | array | 是 | 每项 `componentId` 与 `componentKey` **二选一**（同时传会报错）；`componentValue` 为填充值 |
| components[].componentValue | string | 否 | 按控件类型填；动态表格新增行时 `insertRow` 必须 true（格式见文档 case3 页面，⚠ 本 skill 未抓取） |
| requiredCheck | boolean | 否 | 默认 false。只对 **PDF** 模板生效；true 时必填控件缺值报“'XX控件名称'填充内容缺失”。**HTML 模板总是强制校验必填** |

```python
r = esign_request("POST", "/v3/files/create-by-doc-template", body={
    "docTemplateId": tpl_id,
    "fileName": "张三-劳动合同.pdf",
    "components": [
        {"componentKey": "employeeName", "componentValue": "张三"},
        {"componentKey": "startDate", "componentValue": "2026/10/01"},
    ],
    "requiredCheck": True,
})
filled_file_id = r["data"]["fileId"]
```

响应：`fileId`、`fileDownloadUrl`（PDF 模板返回；**HTML 模板默认返回 null**，要用 `GET /v3/files/{fileId}` 查）。
填充出的 fileId 发起签署前，同样建议用 `GET /v3/files/{fileId}` 确认状态（⚠ 文档没写填充生成是否也是异步）。

错误码（文档原文，未实测）：`1430002 参数错误: componentId和componentKey只允许其中一个有值`、`… 不能同时为空`、
`1430011 componentKey:%s无效`、`1430011 参数错误：控件id或控件key重复,%s`、`1430601 创建合同失败: 身份证号码有误,请检查!`、`1430011 模板拥有者不匹配`。
HTML 动态模板填充的表格行数 ≤2000，填充后样式可能变化。

### 6.4 其他模板接口（路径来自错误码页 / 目录，字段未展开）

| 接口 | 用途 |
| --- | --- |
| `GET /v3/doc-templates?pageNum=1&pageSize=20` | 模板列表；`pageSize` 最大 20（超过报 `1430002 每页条数不能大于20`） |
| `DELETE /v3/doc-templates/{docTemplateId}` | 删除模板 |
| `POST /v3/doc-templates/{docTemplateId}/doc-template-edit-url` | 编辑模板页面 |
| `POST /v3/doc-templates/doc-template-preview-url` | 预览模板页面 |
| `POST /v3/doc-templates/doc-template-fill-url` / `POST /v3/doc-templates/fill-task-result` | 让用户在页面填写模板 / 查填写结果 |
| `GET /v3/files/{fileId}/detail` | 查询 HTML 模板填写后文件 |
| `POST /v3/doc-templates/{docTemplateId}/copy` | 复制模板 |

---

## 7. 流程模板（signTemplate）简述

流程模板是企业在 e签宝配置好的“填写方 + 签署方 + 顺序 + 文件 + 控件”，与 SaaS 官网互通。目前只支持 PDF。

| 接口 | 用途 |
| --- | --- |
| `POST /v3/sign-templates/sign-template-create-url` | 获取《创建流程模板》页面链接 |
| `GET /v3/sign-templates` | 流程模板列表 |
| `GET /v3/sign-templates/detail` | 流程模板详情（拿 `participantId`、控件 ID） |
| `POST /v3/sign-flow/create-by-sign-template` | 通过流程模板创建合同拟定和签署流程 |
| `POST /v3/sign-flow/{signFlowId}/draft-url` | 获取填写页面链接 |
| `GET /v3/sign-flow/{signFlowId}/status` | 查询合同拟定和签署流程状态 |

`create-by-sign-template` 关键参数（文档原文）：`signTemplateId`（必填）、`signFlowConfig.signFlowTitle`（必填）、
`signFlowConfig.autoStart`（**默认 true**，拟定完自动开启签署）、`signFlowConfig.autoFinish`（**默认 false**）、
`participants[]`（模板参与方配置为“使用模板时指定 / 固定企业”时必传；`participantId` 用详情接口查，`orgParticipant` / `psnParticipant` 二选一）、
`signFlowInitiator`、`addCopiers`、`addAttachments`。
企业参与方传 `orgId` 时必须配 `transactor.transactorPsnId`；传 `orgName` 时必须配 `transactorPsnAccount` + `transactorName`（二者不能混用）。
个人参与方传 `psnAccount` 时 `psnName` 必传，传 `psnId` 时 `psnName` 不能传。
用别家企业的流程模板要先拿到 `use_org_template` / `manage_org_template` 等授权（见 [identity-authorization.md](identity-authorization.md)）。

---

## 8. 一段可运行的完整流程（Python）

```python
import os
path = "劳动合同.pdf"
up = esign_request("POST", "/v3/files/file-upload-url", body={
    "contentMd5": file_content_md5(path), "contentType": "application/pdf",
    "fileName": os.path.basename(path), "fileSize": os.path.getsize(path),
})["data"]
with open(path, "rb") as f:
    put = requests.put(up["fileUploadUrl"], data=f.read(), timeout=120,
                       headers={"Content-MD5": file_content_md5(path), "Content-Type": "application/pdf"})
put.raise_for_status()
info = wait_file_ready(up["fileId"])            # fileStatus ∈ {2,5}
pos = esign_request("POST", f"/v3/files/{up['fileId']}/keyword-positions",
                    body={"keywords": ["乙方（签字）"]})["data"]["keywordPositions"][0]
# → 把 up["fileId"] 和坐标交给 sign-flows.md §3 的 create-by-file
```

---

## 9. ⚠ 本文件的未说明 / 矛盾之处

| 位置 | 问题 |
| --- | --- |
| §2 | `contentMd5` 参数说明链接到 `dev-guide3/wdrh4b`，帮助文档目录又链接到 `helper/wdrh4b`，两处内容相同（⚠ 链接不统一，不影响算法） |
| §4 | 失败终态 3 / 9 / 12 是否可重试 ⚠ 文档未说明 |
| §5 | 关键字坐标与签章区坐标（签章区中心点还是左下角）的换算 ⚠ 本 skill 未抓取《印章图片尺寸和坐标》 |
| §6.1 | 字段 `docTemplateName` 与错误文案 `templateName不能为空` 名字不一致（⚠ 文档自相矛盾，按字段表传） |
| §6.3 | 填充生成文件是否需要轮询状态 ⚠ 文档未说明；控件值格式（日期、勾选、动态表格）在未抓取的 case3 页面 |
