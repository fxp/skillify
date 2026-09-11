# 文件上传与处理（拿到 fileId）

> 来源：dev.fadada.com FASC OpenAPI 5.1「API文档 / 文档处理」（通过网络文件地址上传、上传本地文件、文件处理）与「API概览」，抓取于 2026-09-11。
> **未用真实凭证验证**：报错与行为描述均为文档原文，未实测。请求封装 `fasc_call` 见 [auth-and-signing.md](auth-and-signing.md)。

## 1. 为什么必须有这一步

签署任务里的 `docs[].docFileId`、`attachs[].attachFileId`，以及企业授权链接里的营业执照 `licenseFileId`，**只接受 `/file/process` 返回的 `fileId`**。
上传接口返回的 `fddFileUrl` 只是存储地址，不是 fileId，直接塞进签署任务是错的。

```
本地文件：POST /file/get-upload-url ──> PUT 文件流到 uploadUrl ──> POST /file/process(fddFileUrl, fileName) ──> fileId
网络文件：POST /file/upload-by-url(fileUrl) ─────────────────────> POST /file/process(fddFileUrl, fileName) ──> fileId
```

`/file/process` 还负责把 doc / docx / 图片等转换成最终签署用的 PDF（或 OFD）。

## 2. 选哪条路

| 你手上有什么 | 走哪条 | 说明 |
| --- | --- | --- |
| 服务器本地文件 / 内存里的字节 | `/file/get-upload-url` + PUT | 最常用；uploadUrl 30 分钟有效 |
| 一个法大大能访问的公网 URL | `/file/upload-by-url` | 法大大去拉文件；URL 必须带扩展名、需 URL 编码 |
| 企业文档模板 + 要填的值 | `/doc-template/fill-values` | 直接得到 fileId，见 [templates.md](templates.md) |
| 已在法大大上的文档模板 | 不需要上传 | 签署任务 `docs[].docTemplateId` 直接引用 |

## 3. fileType：文件"用途"，不是文件格式

三个接口都有 `fileType`，取值（文档原文）：

| 取值 | 用途 | 支持格式 |
| --- | --- | --- |
| `doc` | 用于签署的文档，**只有这种用途的文件才能加入签署任务的文档列表**；本地文件要验签也用 `doc` | PDF 签署：doc、docx、wps、pdf、xls、xlsx、jpg、jpeg、png、bmp 转 PDF；OFD 签署：doc、docx、xls、xlsx、ofd 转 OFD。建议直接传 PDF/OFD |
| `attach` | 签署任务附件、文件比对、合同智审、合同起草协商、纸质合同归档、本地存储任务出证 | 附件：doc、docx、wps、jpg、jpeg、png、tiff、pdf、xls、xlsx、zip、rar、mp4、amr、mp3、wav、txt、ofd |
| `auth` | 获取企业授权链接时的营业执照 | ≤5M |

单文件不超过 50M。

## 4. 获取上传地址

**Endpoint**: `POST /file/get-upload-url`

**用途**: 拿一个预签名的上传地址，后端用 PUT 把文件流传上去。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `fileType` | string | 是 | `doc` / `attach` / `auth`，见 §3 |
| `storageType` | string | 否 | `opdm` 传到接入方本地服务器 / `cloud` 传到法大大云端；不传时应用开了"本地存储"就自动走本地 |

**示例请求**

```bash
fasc_call /file/get-upload-url '{"fileType":"doc"}'
```

**示例响应**

```json
{"code": "100000", "msg": "请求成功",
 "data": {"uploadUrl": "https://file-test-os1.fadada.com/…?sign=q-sign-algorithm%3Dsha1…",
          "fddFileUrl": "https://file-test-os1.fadada.com/…"}}
```

| 字段 | 说明 |
| --- | --- |
| `uploadUrl` | 上传地址，≤500 字符，**30 分钟有效** |
| `fddFileUrl` | 存储中的源文件地址，≤250 字符，后面 `/file/process` 用 |

## 5. PUT 上传文件流

**Endpoint**: `PUT <uploadUrl>`（不是 FASC 接口，**不需要 X-FASC 签名头**）

- 用应用**后端**把文件字节 PUT 到 `uploadUrl`。文档 Java 示例设置 `Content-Type: application/octet-stream`。
- 返回 **HTTP 200 即上传成功**（文档原文），没有 JSON 包装。
- 上传的源文件必须带扩展名（如 `合同.doc`），否则后续处理可能失败。

```bash
curl -sS -X PUT --upload-file ./劳动合同.pdf -H 'Content-Type: application/octet-stream' "$UPLOAD_URL" -o /dev/null -w '%{http_code}\n'
```

- ⚠ 文档示例的 uploadUrl 里带 `content-type=image%2Fpng` 之类的签名参数，预签名是否绑定 Content-Type 文档未说明；按文档示例用 `application/octet-stream`，如 PUT 返回 403 先查这里。

## 6. 通过网络地址上传

**Endpoint**: `POST /file/upload-by-url`

**用途**: 让法大大从一个 URL 拉取文件，得到 `fddFileUrl`。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `fileType` | string | 是 | 同 §3 |
| `fileUrl` | string | 是 | 网络文件 URL，≤2000；**源文件必须带扩展名**；需 URL 编码（文档示例 `URLEncoder.encode("http://www.xxx.com/合同.doc", "UTF-8")`） |
| `storageType` | string | 否 | 同 §4 |

**示例请求**

```python
from urllib.parse import quote
from fasc_client import fasc_call

r = fasc_call("/file/upload-by-url", {
    "fileType": "doc",
    "fileUrl": quote("https://files.example.com/contracts/劳动合同.pdf", safe=""),
})
fdd_file_url = r["fddFileUrl"]
```

**示例响应**：`{"code":"100000","msg":"请求成功","data":{"fddFileUrl":"https://doc-test-os1.fadada.com/…"}}`

- 返回的仍然是 `fddFileUrl`，**还要再调 `/file/process`** 才有 fileId。
- ⚠ "需要进行编码"是指整个 URL 做一次 `URLEncoder.encode`（连 `://` 一起编码）还是只编码路径中的中文，文档未说明；上例按文档示例整体编码。

## 7. 文件处理

**Endpoint**: `POST /file/process`

**用途**: 对已上传的文件做后处理（格式转换），生成签署任务要用的 `fileId`。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `fddFileUrlList` | array | 是 | 待处理文件列表，**每次最多 10 份**，每份 ≤50M；批量时图片与非图片不能混在一起 |
| `fddFileUrlList[].fileType` | string | 是 | `doc` / `attach` / `auth` |
| `fddFileUrlList[].fddFileUrl` | string | 是 | 上一步返回的源文件地址 |
| `fddFileUrlList[].fileName` | string | 是 | 文件名，**必须带扩展名且与上传文件扩展名一致**，≤200；不能含 `/ \ : * " < > \| ?` |
| `fddFileUrlList[].fileFormat` | string | 否 | 转换后格式：`pdf`（默认，国际加密标准）/ `ofd`（国密） |
| `storageType` | string | 否 | 同 §4 |
| `separation` | boolean | 否 | 多张图片一起处理时是否每张单独成一个 PDF，默认 false（合成一个） |

**示例请求**

```bash
fasc_call /file/process '{"fddFileUrlList":[{"fileType":"doc","fddFileUrl":"'"$FDD_FILE_URL"'","fileName":"劳动合同.pdf"}]}'
```

**示例响应**

```json
{"code": "100000", "msg": "请求成功",
 "data": {"fileIdList": [{"fileId": "18438605689", "fileType": "doc",
                          "fddFileUrl": "https://…", "fileName": "劳动合同.pdf", "fileTotalPages": 3}]}}
```

| 字段 | 说明 |
| --- | --- |
| `fileIdList[].fileId` | 文件 ID，≤32 字符；**顺序与请求里的源文件一一对应** |
| `fileIdList[].fileType` / `fddFileUrl` / `fileName` | 批量时用来对应是哪份文件 |
| `fileIdList[].fileTotalPages` | 总页数（仅 `doc` 有值） |

**注意事项**

- 文件最多 1000 页。
- 签署文件一定是 PDF 或 OFD；`doc` 用途的非 PDF/OFD 源文件会在这里被转换。
- 文件名扩展名和上传文件不一致 → `211157 文件处理失败，文件后缀名与源文件不匹配`（文档原文）。
- ⚠ 文档字段表写"文件名不支持以下 9 个字符"，但列出的字符个数与写法在不同页面不一致（有的页面含 `u007C`、有的含全角 `？`）。保守做法：文件名只用中英文、数字、下划线、短横线和点。
- ⚠ fileId 的有效期、能否跨多个签署任务复用，文档未说明。

## 8. 端到端示例（Python）

```python
import os
import requests
from fasc_client import fasc_call


def upload_local_file(path: str, file_type: str = "doc", file_format: str = "pdf") -> str:
    """本地文件 -> fileId（可直接用作 docFileId / attachFileId）"""
    up = fasc_call("/file/get-upload-url", {"fileType": file_type})
    with open(path, "rb") as f:
        r = requests.put(up["uploadUrl"], data=f,
                         headers={"Content-Type": "application/octet-stream"}, timeout=120)
    if r.status_code != 200:                       # 200 即成功，无 JSON
        raise RuntimeError(f"PUT 上传失败 HTTP {r.status_code}: {r.text[:200]}")
    item = {
        "fileType": file_type,
        "fddFileUrl": up["fddFileUrl"],
        "fileName": os.path.basename(path),        # 带扩展名，与上传文件一致
    }
    if file_type == "doc":
        item["fileFormat"] = file_format
    processed = fasc_call("/file/process", {"fddFileUrlList": [item]})
    return processed["fileIdList"][0]["fileId"]


if __name__ == "__main__":
    print(upload_local_file("劳动合同.pdf"))
```

## 9. 端到端示例（shell）

```bash
# 依赖 auth-and-signing.md 里的 fasc_call，且已 export FASC_TOKEN
R=$(fasc_call /file/get-upload-url '{"fileType":"doc"}')
UPLOAD_URL=$(printf '%s' "$R" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["uploadUrl"])')
FDD_FILE_URL=$(printf '%s' "$R" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["fddFileUrl"])')
curl -sS -X PUT --upload-file ./contract.pdf -H 'Content-Type: application/octet-stream' "$UPLOAD_URL" -o /dev/null -w 'PUT %{http_code}\n'
fasc_call /file/process "{\"fddFileUrlList\":[{\"fileType\":\"doc\",\"fddFileUrl\":\"$FDD_FILE_URL\",\"fileName\":\"contract.pdf\"}]}"
```

## 10. 相关接口（本 skill 不展开）

「API概览 / 文档处理」还列出这些接口，签名方式相同，参数去官网看：

| 接口 | 说明 |
| --- | --- |
| `/file/get-keyword-positions` | 上传得到 fileId 后查文档中关键字坐标，便于用坐标方式设置控件 |
| `/file/verify-sign` | 对已签署完成的文档做签章有效性验证（本地文件验签也要先以 `doc` 用途上传处理） |
| `/file/ofd-file-merge` | 在已签章的 OFD 上追加一份未签章 OFD |
| PDF 文件合并、查询文档首页宽高、获取签章定位页面链接 | 见「文档处理」目录 |

## 11. ⚠ 汇总

- PUT 预签名是否绑定 Content-Type（§5）。
- `fileUrl` 的编码方式（§6）。
- 文件名禁用字符在不同页面写法不一（§7）。
- fileId 有效期与复用（§7）。
