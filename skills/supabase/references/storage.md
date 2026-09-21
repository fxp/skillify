# Storage：文件上传、下载、访问控制

> 来自 https://supabase.com/docs/guides/storage/quickstart、`guides/storage/buckets/fundamentals`、`guides/storage/security/access-control`、`guides/storage/uploads/standard-uploads`、`guides/storage/serving/downloads`、`guides/storage/debugging/error-codes`。抓取于 2026-09-21。**没有经过真实 API 调用验证**，标 `⚠ 文档原文，未实测` 处均为文档转录。

## 目录

- [概念：bucket / 文件 / 路径](#概念bucket--文件--路径)
- [建 bucket](#建-bucket)
- [上传](#上传)
- [下载与访问：公开 URL vs 签名 URL](#下载与访问公开-url-vs-签名-url)
- [访问控制：storage.objects 上的 RLS](#访问控制storageobjects-上的-rls)
- [错误码要点](#错误码要点)

## 概念：bucket / 文件 / 路径

- **Bucket** 是文件的容器，粒度上大致对应"一组需要相同安全/访问规则的文件"（比如 `avatars` 一个 bucket、`private-documents` 另一个）。
- 文件路径是任意字符串（用 `/` 分层模拟"文件夹"，Storage 里没有真正的目录概念），必须遵守 AWS S3 对象键命名规范。
- Bucket 建立时选择 **public** 还是 **private**（也可以事后改），这个选择直接决定默认的访问方式，见下文。

## 建 bucket

```sql
insert into storage.buckets (id, name) values ('avatars', 'avatars');
```

```js
const { data, error } = await supabase.storage.createBucket('avatars')
```

## 上传

标准上传方式适合 **≤6MB** 的文件（官方建议超过这个尺寸改用 TUS 断点续传接口，标准方式理论上限是 5GB 但建议只用于小文件）：

```bash
curl -X POST "<SUPABASE_URL>/storage/v1/object/avatars/public/avatar1.png" \
  -H "apikey: <KEY>" \
  -H "Authorization: Bearer <TOKEN>" \
  --data-binary "@/local/path/avatar1.png"
```

```js
const { data, error } = await supabase.storage
  .from('avatars')
  .upload('public/avatar1.png', file)
```

- **默认不允许覆盖同路径已存在的文件**，直接返回 `400 Asset Already Exists`。要覆盖，传 `upsert: true`（客户端库）或 `x-upsert: true`（原始 HTTP header）——**这是任务里点名的一个陷阱**：Storage 的"覆盖写入"开关是一个 HTTP header，不是 REST 表那种 `Prefer: resolution=merge-duplicates`，两套 upsert 语法互不相通，写代码时不要把这两个产品的 upsert 写法搞混。
- 覆盖写入（`upsert`）在 RLS 层面需要**额外的 `SELECT` 和 `UPDATE` 权限**，光有 `INSERT` policy 只够"上传到全新路径"，不够"覆盖已有路径"。`⚠ 文档原文，未实测`。
- 两个客户端同时上传同一路径且都不带 `upsert`：先完成的那个成功，其余的收到 `400 Asset Already Exists`；都带 `upsert` 时则最后完成的那个生效。`⚠ 文档原文，未实测`。
- 不传 `contentType` 时按文件扩展名猜测 MIME type，需要精确控制时显式传。
- 官方不建议频繁覆盖同一路径：CDN 缓存传播到边缘节点需要时间，覆盖后短期内不同地区用户可能读到不同版本；更推荐写新路径而不是原地覆盖。

## 下载与访问：公开 URL vs 签名 URL

**Public bucket**：文件对任何知道 URL 的人直接可访问，受益于 CDN 高缓存命中率：

```
https://<project_ref>.supabase.co/storage/v1/object/public/<bucket>/<path>
```

```js
const { data } = supabase.storage.from('bucket').getPublicUrl('filePath.jpg')
```

加 `?download` 参数让浏览器触发下载而不是直接展示；`?download=customname.jpg` 还能指定保存文件名。

**Private bucket**：没有公开 URL，只有两条路径能拿到内容：

1. **签名 URL**（推荐给"临时分享给某个用户"的场景）：服务端调用生成一个带时限的一次性 URL，之后任何人拿着这个 URL 都能在过期前访问，不需要额外携带 token：

   ```js
   const { data, error } = await supabase.storage
     .from('bucket')
     .createSignedUrl('private-document.pdf', 3600) // 有效期秒数
   ```

   签名 URL 用的是**独立于项目 JWT 签名密钥的专用内部 key**——轮换/吊销 Auth 的 JWT 签名密钥、停用旧版 key、从 HS256 切到非对称签名，都不会让已经签发的签名 URL 失效；要主动吊销签名 URL 只能联系 Supabase 支持。`⚠ 文档原文，未实测`。

2. **携带用户 `Authorization` header 直接 GET**：`GET /storage/v1/object/authenticated/<bucket>/<path>`，走 RLS，权限判断方式和查表一致。

## 访问控制：storage.objects 上的 RLS

Storage 内部把所有文件的元数据存在一张普通表 `storage.objects` 里，**访问控制的实现就是这张表上的 RLS policy**，和普通业务表用的是完全相同的机制——这意味着"给业务表写 RLS policy"的经验直接可以迁移过来，不是另一套单独的配置系统。

- **默认没有任何 policy 时，非 public bucket 完全不能上传**（Storage 对没有匹配 policy 的写操作是默认拒绝，不是默认允许）。
- 每种操作对应的最小 policy：
  - 上传：`for insert` 授予 `INSERT`
  - 覆盖上传：额外加 `SELECT` + `UPDATE`
  - 下载/读取：`for select` 授予 `SELECT`
  - 删除：`for delete` 授予 `DELETE`
- 典型"用户只能碰自己文件夹"写法，用 `storage.foldername(name)` 取路径的第一段和 `auth.uid()`/`auth.jwt()->>'sub'` 比对：

  ```sql
  create policy "own folder only"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'my_bucket_id'
    and (storage.foldername(name))[1] = (select auth.jwt()->>'sub')
  );
  ```

- **Public bucket 本身已经公开可读，不需要额外 policy** 就能通过公开 URL 访问；如果还想通过 API 方式（比如 `list`）浏览 bucket 内容，才需要专门的 `select` policy，且要用 `storage.allow_any_operation()` 之类的辅助函数限定，否则容易连带把"列出全部文件"的能力一起开放出去。`⚠ 文档原文，未实测`。
- **service key 完全绕过 Storage 的 RLS**（和数据库那侧的 `service_role` 是同一套 bypass 逻辑），只能用于你自己控制的服务端。

## 错误码要点

Storage 错误统一是 `{"code": "...", "message": "..."}` 格式，几个常见的：

| Code | HTTP | 含义 |
| --- | --- | --- |
| `NoSuchBucket` | 404 | bucket 不存在，或存在但当前角色没权限访问（两种情况返回码相同，不能仅凭 404 区分） |
| `InvalidJWT` | 401 | token 过期或格式错误 |
| `ResourceAlreadyExists` / `KeyAlreadyExists` | 409 | 路径已存在且没传 `x-upsert:true` |
| `AccessDenied` | 403 | RLS policy 不允许这次操作 |
| `EntityTooLarge` | 413 | 超过项目的文件大小上限（Dashboard **Storage Settings** 里可调） |

完整表见 `references/errors-and-limits.md`。`⚠ 文档原文，未实测`。
