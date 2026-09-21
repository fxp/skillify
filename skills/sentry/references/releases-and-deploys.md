# Release 与 Deploy（Web API）

> ⚠ 全部内容来自 `openapi-derefed.json`（`github.com/getsentry/sentry-api-schema`，抓取于 2026-09-21）转录，未经真实调用验证。Base URL 统一为 `https://{region}.sentry.io`。需要 `project:releases` scope（见 `auth-and-tokens.md`）。

## 目录

- [Release 是什么，为什么要建它](#release-是什么为什么要建它)
- [创建 Release](#创建-release)
- [列出 / 查询 Release](#列出--查询-release)
- [Deploy——一个 Release 可以对应多次部署](#deploy一个-release-可以对应多次部署)
- [Commit 关联](#commit-关联)
- [Release 文件（source map 等构建产物）](#release-文件source-map-等构建产物)
- [跨项目共享同一个 Release](#跨项目共享同一个-release)

## Release 是什么，为什么要建它

**Release = 一个代码版本**(可以是版本号、commit hash、或任意字符串标识)。官方原话:"Releases are used by Sentry to improve error reporting by correlating first-seen events with the release that may have introduced them, and are required for source maps and other debug features."——即:
- 判断"这个 issue 是哪个版本引入的回归"(`firstRelease` 搜索字段,见 `issues.md`)。
- "标记这个 issue 在下一个 release 里已修复"(issue 的 `statusDetails.inNextRelease`,见 `issues.md`)。
- Source map 上传必须关联到一个具体 release,否则前端压缩后的堆栈跟踪没法还原成源码位置。
- **Release Health**:crash-free session/user 百分比等指标,附加在 release 详情里。

**Deploy 和 Release 是两个概念**:一个 release(同一份代码)可以被部署到多个 environment(先 staging 再 production),对应多条 deploy 记录;而 release 本身只创建一次。

## 创建 Release

**Endpoint**: `POST /api/0/organizations/{organization_id_or_slug}/releases/`
**用途**: 通知 Sentry"这个版本存在了"。**通常在 CI 构建/部署流程里调用**,而不是应用运行时。

**关键请求体字段**

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `version` | string | 是 | 版本标识,可以是版本号/commit hash/任意字符串 |
| `projects` | array<string> | 是 | 关联的项目 slug 列表 |
| `ref` | string | 否 | commit 引用(比如打了 tag 时用) |
| `url` | string(uri) | 否 | 指向这个版本源码的链接(如 GitHub 页面) |
| `dateReleased` | datetime | 否 | 上线时间,不传用当前时间 |
| `commits` | array<object> | 否 | 关联的 commit 列表(`id`/`repository`/`message`/`author_name`/`author_email`/`timestamp`/`patch_set`) |
| `refs` | array<object> | 否 | 每个仓库一条 commit 引用(`commit`/`repository`/`previousCommit`),**推荐用这个而不是已废弃的 `headCommits`** |
| `status` | enum | 否 | `open` 或 `archived` |

**易错点**:**同一个组织内,多个项目如果用了同一个 `version` 字符串,会被 Sentry 当成"同一个 release"处理**(官方原话:"Release versions that are the same across multiple projects within an organization are treated as the same release")——这既是特性也是坑:想给不同项目独立管理 release 时,要确保 `version` 不会意外撞车(比如都用 git 短 hash,不同仓库理论上可能撞;用 `<project>-<version>` 这种带前缀的字符串更安全)。

**示例请求**

```bash
curl -s -X POST "https://us.sentry.io/api/0/organizations/acme/releases/" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "version": "my-service@2026.09.21+1",
    "projects": ["my-service"],
    "refs": [{"repository": "acme/my-service", "commit": "a1b2c3d"}]
  }'
```

**响应状态码**:`201`(新建)或 **`208 Already Reported`**(这个 version 已经存在——不是错误,是幂等提示,CI 脚本重复调用同一个 release 创建不需要额外判重逻辑,⚠ 文档原文,未实测 208 时响应体是否仍返回完整 release 对象)。

## 列出 / 查询 Release

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/releases/`
**参数**:`project`(过滤)、`environment`、`query`(按 version 子串,大小写不敏感)、`per_page`/`cursor`。

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/releases/{version}/`
**用途**: 单个 release 详情。

| 参数 | 说明 |
| :--- | :--- |
| `health` | boolean,`true` 时附带 crash-free session/user 数据(默认 `false`,即**默认不返回 health 数据**,这是一个容易漏掉的可选开关——直接调详情拿不到健康度指标,要显式传 `health=true`) |
| `adoptionStages` | boolean,附带采用阶段数据 |
| `summaryStatsPeriod` / `healthStatsPeriod` | 统计周期,枚举 `1h`/`24h`/`1d`/`2d`/`7d`/`14d`(默认)/`30d`/`48h`/`90d` |
| `status` | 按 `open`/`archived` 过滤 |

**响应关键字段**:`newGroups`(这个 release 引入的新 issue 数)、`commitCount`/`deployCount`、`authors`(参与这次 release 的提交作者列表)、`projects[].healthData`(`crashFreeUsers`/`crashFreeSessions`/`durationP50`/`durationP90`,仅 `health=true` 时有值)。

**Endpoint**: `PUT /api/0/organizations/{organization_id_or_slug}/releases/{version}/`——更新(如归档:`status=archived`)。
**Endpoint**: `DELETE /api/0/organizations/{organization_id_or_slug}/releases/{version}/`——删除,⚠ 文档未说明是否要求先解除关联的 event/issue。

## Deploy——一个 Release 可以对应多次部署

**Endpoint**: `POST /api/0/organizations/{organization_id_or_slug}/releases/{version}/deploys/`
**用途**: 记录"这个 release 部署到了哪个 environment"。

**关键请求体字段**

| 字段 | 必填 | 说明 |
| :--- | :--- | :--- |
| `environment` | 是 | 部署到的 environment 名(如 `production`) |
| `name` | 否 | 部署的可读名称 |
| `url` | 否 | 指向这次部署的链接(如 CI 构建页面) |
| `dateStarted` / `dateFinished` | 否 | 不传 `dateFinished` 则用当前时间 |
| `projects` | 否 | 不传则对 release 关联的全部项目都建 deploy |

**示例请求**

```bash
curl -s -X POST "https://us.sentry.io/api/0/organizations/acme/releases/my-service%402026.09.21%2B1/deploys/" \
  -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"environment": "production"}'
```

注意 `version` 出现在 URL 路径里,如果版本号含 `@`/`+`/`/` 等特殊字符,**要做 URL 编码**(above 示例已编码)。

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/releases/{version}/deploys/`——列出这个 release 的全部 deploy 记录。

## Commit 关联

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/releases/{version}/commits/`——列出这个 release 关联的 commit(建 release 时通过 `commits`/`refs` 传入的那些)。
**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/repos/{repo_id}/commits/`——按仓库列出 commit(不限定 release)。
**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/releases/{version}/commitfiles/`——这个 release 涉及改动的文件列表(用于 suspect commit / code owner 关联)。

## Release 文件（source map 等构建产物）

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/releases/{version}/files/`——列出关联到这个 release 的文件(source map、源码 artifact)。支持按 `query`(名称子串)、`checksum`(精确匹配)过滤。
**Endpoint**: `POST /api/0/organizations/{organization_id_or_slug}/releases/{version}/files/`——上传新文件。
**Endpoint**: `GET`/`PUT`/`DELETE /api/0/organizations/{organization_id_or_slug}/releases/{version}/files/{file_id}/`——单个文件的查/改/删。

**实践提醒**:官方明确建议 source map 上传走 `sentry-cli` 或构建工具插件(webpack/vite/rollup plugin),而不是手写代码直接调这几个文件 endpoint——插件会处理好 debug id 关联、artifact bundle 打包等细节(见 `events.md` 的 source-map-debug 小节,那里描述了上传方式不对时会出现的诊断信息)。这几个 endpoint 本身值得知道存在,但本 skill 不建议手写代码复刻插件逻辑。

## 跨项目共享同一个 Release

项目级也有一套镜像 endpoint(`GET /api/0/projects/{organization_id_or_slug}/{project_id_or_slug}/releases/`、`.../releases/{version}/commits/`、`.../releases/{version}/files/`),**行为和组织级基本对应,但多数是只读**(项目级没有 release 创建/更新/deploy 的 POST/PUT,这些操作只在组织级 endpoint 上)。新代码优先用组织级 endpoint,项目级留给"只想看某个项目视角下的 release 列表"这种场景。

## Session（Release Health 原始数据)

**Endpoint**: `GET /api/0/organizations/{organization_id_or_slug}/sessions/`——release health 指标背后的原始 session 聚合数据查询接口,字段较多(⚠ 本 skill 未展开,用到时查 OpenAPI 规范里 `Releases` 分组的这一条)。多数场景下直接用上面 release 详情的 `health=true` 附带数据就够,这个 endpoint 用于更细粒度的自定义聚合。
