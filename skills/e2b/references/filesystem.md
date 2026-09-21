# 文件系统操作

⚠ 全文档原文，未实测（抓取自 `docs.e2b.dev`，2026-09-21）。

目录：[读写](#读写) · [一次操作多个文件](#一次操作多个文件) · [从本地磁盘上传](#从本地磁盘上传) · [下载到本地磁盘](#下载到本地磁盘) · [浏览器上传/下载用的预签名 URL](#浏览器上传下载用的预签名-url) · [文件/目录信息](#文件目录信息) · [监听目录变化](#监听目录变化)

所有文件系统操作都挂在 `sandbox.files` 下面。每个方法都有 JS（`camelCase`）和 Python（`snake_case`）两种形式，只是命名风格不同，参数结构是一样的。

## 读写

```python
from e2b import Sandbox

sandbox = Sandbox.create()
file_content = sandbox.files.read('/path/to/file')
sandbox.files.write('/path/to/file', 'file content')
```

```typescript
import { Sandbox } from 'e2b'

const sandbox = await Sandbox.create()
const fileContent = await sandbox.files.read('/path/to/file')
await sandbox.files.write('/path/to/file', 'file content')
```

**方法**：`sandbox.files.read(path)` / `sandbox.files.write(path, data)`
**用途**：最基础的单文件读写原语。`write` 在文件不存在时也会创建它（按 OpenAPI 摘要里文件系统分组的说法，还会确保父目录存在），文件已存在时会覆盖。
**关键参数**：`path` —— 绝对路径，或相对于沙箱用户 home 目录（示例里是 `/home/user`）的相对路径；`data` —— 写入用的字符串或二进制内容。
**注意事项**：⚠ 文档未明确说明除了示例里出现的 `/home/user` 这个约定之外，默认工作目录/相对路径的默认基准到底是什么——在依赖相对路径之前，先确认你所用模板的实际默认用户/cwd（完整文档里的 `template/user-and-workdir`，本次未抓取）。

## 一次操作多个文件

```python
sandbox.files.write_files([
    {"path": "/path/to/a", "data": "file content"},
    {"path": "another/path/to/b", "data": "file content"},
])
```

```typescript
await sandbox.files.write([
  { path: '/path/to/a', data: 'file content' },
  { path: '/another/path/to/b', data: 'file content' },
])
```

**注意事项**：**两个 SDK 里批量写的方法名不一样**——JS 用重载的方式让 `files.write()` 接受一个数组；Python 用的是一个**独立的方法** `files.write_files()`（不是给 `files.write()` 传一个 list）。在 Python 里给 `files.write()` 传 list 不是文档里写的用法。⚠ 文档原文，未实测——Python 实际上是会拒绝一个传给 `write()` 的 list，还是悄悄做了别的事，本次没有核实。

## 从本地磁盘上传

```python
sandbox = Sandbox.create()
with open("path/to/local/file", "rb") as file:
    sandbox.files.write("/path/in/sandbox", file)
```

```typescript
import fs from 'fs'
const sandbox = await Sandbox.create()
const content = fs.readFileSync('/local/path')
await sandbox.files.write('/path/in/sandbox', content)
```

**用途**：常见场景下没有单独的"上传"方法——`files.write()` 直接接受一个本地文件句柄/buffer。上传整个目录其实就是自己遍历本地目录树、拼出一个数组，再调用 `write()`/`write_files()`（没有内建的递归目录上传；参见文档自己给的目录遍历 helper 示例）。

## 下载到本地磁盘

```python
content = sandbox.files.read('/path/in/sandbox')
with open('/local/path', 'w') as file:
    file.write(content)
```

```typescript
import fs from 'fs'
const content = await sandbox.files.read('/path/in/sandbox')
fs.writeFileSync('/local/path', content)
```

**注意事项**：和上传是同样的不对称——"下载"其实就是 `files.read()` 之后自己把结果写到本地磁盘；对于普通的 SDK 到本地磁盘的场景，没有专门的下载方法。

## 浏览器上传/下载用的预签名 URL

```python
sandbox = Sandbox.create(secure=True)  # 创建时必须带 secure=True
signed_url = sandbox.upload_url(path="demo.txt", user="user", use_signature_expiration=10_000)
# 从任意环境（比如浏览器）向 signed_url 发起一个 multipart 表单 POST——不需要 E2B API key
```

```typescript
const sandbox = await Sandbox.create(template, { secure: true })
const publicUploadUrl = await sandbox.uploadUrl('demo.txt', { useSignatureExpiration: 10_000 })
```

**用途**：让一个未鉴权的客户端（浏览器、移动端 App）在不持有 E2B API key 的情况下，直接向/从沙箱上传/下载文件——做法是先在服务端生成一个签名过的、可选带过期时间的 URL。
**关键参数**：`secure: true` **必须在沙箱创建时就设置**——不能在一个已存在的沙箱上后补开启来开始生成签名 URL。`useSignatureExpiration`/`use_signature_expiration` —— 生成的 URL 的可选过期窗口，单位毫秒。
**注意事项**：`sandbox.downloadUrl()`/`download_url()` 是对应的读取侧方法，同样要求先决条件 `secure: true`。⚠ 文档原文，未实测——在一个*没有*用 `secure: true` 创建的沙箱上调用 `uploadUrl`/`upload_url` 会报什么错，本次没有核实。

## 文件/目录信息

```python
sandbox.files.write('test_file', 'Hello, world!')
info = sandbox.files.get_info('test_file')
# EntryInfo(name='test_file.txt', type=<FileType.FILE: 'file'>, path='/home/user/test_file.txt',
#   size=13, mode=0o644, permissions='-rw-r--r--', owner='user', group='user',
#   modified_time='2025-05-26T12:00:00.000Z', symlink_target=None)
```

```typescript
await sandbox.files.write('test_file.txt', 'Hello, world!')
const info = await sandbox.files.getInfo('test_file.txt')
// { name, type: 'file'|'dir', path, size, mode, permissions, owner, group, modifiedTime, symlinkTarget }
```

**用途**：对一个文件或目录做 stat —— 名字、类型（`file`/`dir`）、绝对路径、大小、POSIX mode/permissions、owner/group、mtime，以及 symlink 目标（如果适用）。
**关键参数**：对文件和目录的行为完全一致（用 `type` 字段区分；示例里目录的 `size` 是 `0`）。
**注意事项**：文件在写入时还可以附带自定义的键值对元数据，会在这同一次调用的 `metadata` 字段里返回——见 `docs.e2b.dev/filesystem/metadata`（本次未抓取；⚠ 文档未抓取，如需自定义 metadata 请单独确认参数名）。
另外还有：`files.list(path)`（目录列表——quickstart 里用来列 `/`）、`files.makeDir(path)`/`make_dir(path)`、`files.move(...)`、`files.remove(...)`，对应 OpenAPI 文件系统分组里的 `ListDir`、`MakeDir`、`Move`、`Remove` —— ⚠ 这几个方法的 SDK 参数细节本次没有逐一抓取教程页确认，只是从 OpenAPI 摘要的方法名推断出它们存在；写代码前建议查一下 SDK reference 确认具体签名。

## 监听目录变化

```python
from e2b import Sandbox, FilesystemEventType

sandbox = Sandbox.create()
handle = sandbox.files.watch_dir('/home/user', recursive=True, include_entry=True)
sandbox.files.write('/home/user/my-file', 'hello')
events = handle.get_new_events()  # Python 里是轮询式的
for event in events:
    if event.type == FilesystemEventType.WRITE:
        print(f"wrote to file {event.name}")
```

```typescript
import { Sandbox, FilesystemEventType } from 'e2b'

const sandbox = await Sandbox.create()
const handle = await sandbox.files.watchDir('/home/user', async (event) => {
  if (event.type === FilesystemEventType.WRITE) console.log(`wrote to file ${event.name}`)
}, { recursive: true, includeEntry: true })
await sandbox.files.write('/home/user/my-file', 'hello')
```

**关键参数**
| 参数 | 说明 |
|---|---|
| `recursive` | 同时监听子目录。⚠ 快速创建多层嵌套的新文件夹时，可能会丢失非 CREATE 类型的事件——如果这点很重要，建议提前把目录结构建好。 |
| `includeEntry`/`include_entry` | 在每个事件上附带受影响条目的 stat 信息（path/type/size）。**要求模板的 envd 版本 `v0.6.3+`**——老版本的沙箱调用会抛错。对于 remove 事件，entry 信息可能是空的。 |
| `allowNetworkMounts`/`allow_network_mounts` | 监听 NFS/CIFS/SMB/FUSE 挂载路径需要显式开启这个选项（默认拒绝，因为这类路径上的事件可能不可靠）。**要求模板的 envd 版本 `v0.6.4+`**。其他客户端在沙箱*外部*对同一个网络共享做的修改**不会**被检测到——只能检测到从沙箱内部发起的变更。 |

**注意事项**：事件是**异步投递、可能有延迟**的——不要写完一个文件就立刻关闭/收集 watcher，指望事件已经到了；文档明确警告过这种竞态条件。Python 的 API 是轮询式的（`get_new_events()`）；JS 的是回调式的——不要把一种语言的写法原样照搬到另一种语言里。
