# 第一步：抓取与勘探

目标：在写任何一行 skill 内容之前，先拿到这个平台 API 的**完整、精确**的原始材料。凭"这类平台大概长什么样"的印象去写，就是把训练数据里的记忆当事实——这正是做 skill 要消灭的东西。

## 1. 找 `llms.txt`

直接访问 `https://<docs-domain>/llms.txt`（Mintlify、GitBook、Docusaurus 插件等生成的站点大多有）。它是给 AI 用的页面索引：每行一个 `[标题](URL): 摘要`。

- **根路径 404 不等于没有**。文档挂在子路径下时索引也在子路径下：`/docs/llms.txt`、`/docs/openapi.json`（Kimi 开放平台就是这样，根路径全 404）。把用户给的 URL 的路径前缀也试一遍，再下结论。
- **索引可能指向另一个域名**（`platform.moonshot.cn` 的索引全部指向 `platform.kimi.com`）。以索引里的域名为准抓取，SKILL.md 里两个域名都写上并说明哪个是 canonical。
- **优先找 `llms-full.txt`**（全文拼接）。存在时一次下载等于拉全站，比逐页 `fetch_docs.sh` 便宜一个数量级；用页面标题行或 URL 标记本地切分即可。只有它不存在或大到几十 MB 时才退回 `llms.txt` + 按需拉页。
- 用 `scripts/fetch_docs.sh <llms.txt URL> <out_dir>` 并发把所有页面的 Markdown 源码拉到本地。原理：这类站点的每个页面 URL 结尾加 `.md` 就能拿到纯 Markdown（不用渲染 DOM、不用截图）。脚本会生成 `index.tsv`（标题、URL、本地文件）方便后面按主题分组。
- `llms.txt` 可能是**二级索引**：条目指向的页面本身又是一份索引（Dify 的就是 `_llms/en/cloud.md` 这种「265 pages」的汇总页）。这种情况把二级页面当新的 llms.txt 再跑一次 `fetch_docs.sh`，或者直接用它们，因为二级页面往往已经把该分区的全部正文拼在一起了。
- 拉完先 `wc -l` 看一眼分布：哪些页面特别长（通常是 API reference 主页面）、哪些是快速开始 / SDK 教程（对第 2 步的示例代码有用，但字段以规范为准）。

## 2. 找 OpenAPI / AsyncAPI 规范文件

这是全流程最重要的一份原始材料：它有精确的字段类型、`required` 列表、枚举值、响应结构。人写的 Markdown 教程只挑重点讲，规范才是"完整但没有解释"的那份权威真相。

去哪找：

- `llms.txt` 末尾常有 `## OpenAPI Specs` 段。**但它可能是错的**——见过列出 `package.json`、`pnpm-lock.yaml` 的，说明生成器把仓库里所有 JSON 都当成规范了。列出的链接要实际打开确认是 `openapi: 3.x` / `swagger: 2.0` / `asyncapi:` 开头的文档。
- 常见路径：`/openapi.json`、`/openapi.yaml`、`/api-reference/openapi.json`、`/openapi/openapi.json`、`/swagger.json`、`/api-docs`、`/v1/openapi.json`。Mintlify 站点的规范路径通常写在页面的 frontmatter（`openapi: POST /emails`）里，规范文件本身在文档仓库根目录；用 `curl -sI` 批量探一遍。
- 打开 API reference 页面，看浏览器 Network 面板加载了哪个 JSON（内置 Browser 的 `read_network_requests` 可以直接列）。
- 文档站源码是开源的（很多 Mintlify / Docusaurus 站点在 GitHub 上）：`gh api repos/<org>/<docs-repo>/git/trees/HEAD?recursive=1 | grep -i openapi`。
- WebSocket / 事件类协议找 `asyncapi.json`。

拿到规范后**不要通读原始 JSON**，跑：

```bash
python3 scripts/openapi_summary.py <spec-file-or-url> --out-dir <scratch>/openapi-summary
```

它会递归展开 `$ref`，按 tag（没有 tag 就按路径第一段）把每个 endpoint 输出成可读摘要：method + path、summary、鉴权、参数表（位置 / 类型 / 必填 / 枚举 / 说明）、请求体和响应体的扁平字段列表。`--tag` 只输出某一组，`--grep` 按路径过滤。产出的每个 `<tag>.md` 就是第 2 步派给子 Agent 的输入。

规范和 Markdown 页面不一致时，先记下来，别急着裁决——第 3 步用真实调用来判。

**Markdown 导出会丢表格**。Mintlify 一类站点的 `.md` 导出把 `<ParamField>`、`<DocTable rows={[...]}>` 这种 JSX 组件整个剥掉，参数表、速率档位表在 Markdown 里根本看不到。所以字段表必须来自 OpenAPI；文档站开源时去 GitHub 拉原始 `.mdx` 才能拿到这些表。

## 2b. 先裁范围，再抓全量

文档站常常不止一个产品（Kimi 的 199 页里六成是独立的 Hosted Agents 产品；很多云厂商一个域名下几十个产品）。抓之前先按 `llms.txt` 的标题和 URL 前缀分组，只把用户要的那个 API 的页面和 API reference 划进范围，其余在 SKILL.md 导航表里留一行"本 skill 不覆盖 X，文档在 …"。抓取预算有限时优先级是：OpenAPI 规范 > API reference 页 > 概念 / 限制 / 错误码页 > 快速开始 > SDK 教程。

处理中文文档时注意：macOS 自带的 `cut -c`、`head -c` 按字节切会把 UTF-8 切坏，切文本用 Python 或 `awk`。

## 3. 摸清鉴权方式

从规范的 `components.securitySchemes`（或 Swagger 2 的 `securityDefinitions`）拿到精确格式，再和文档的"快速开始"页面交叉确认：

- header 名字和前缀：`Authorization: Bearer <key>` / `Authorization: <key>`（AutoDL 就是裸 token，没有 Bearer）/ `x-api-key` / 自定义 header
- 有没有第二个必需 header（租户 ID、版本号、`Content-Type` 是否强制）
- key 在控制台哪里生成、有没有"项目 / 应用"层级、不同 key 类型权限是否不同
- 签名类鉴权（HMAC、时间戳 + nonce）要把签名算法完整抄下来，这是最容易写错的部分

这一步就把它写进 scratch 目录的 `auth.md`，第 2 步所有子 Agent 共用。

## 4. 没有 `llms.txt`、也没有规范文件时

国内平台和老站点常见。按这个顺序退：

1. `sitemap.xml` / `sitemap_index.xml`：拿到全量页面 URL，再按路径前缀（`/docs/api/`）筛。
2. 文档站是 SPA 时，`curl` 只能拿到空壳。用内置 Browser 打开页面，`get_page_text` 或 `read_page` 取渲染后的正文；页面多时写个循环。有 `ego-browser` skill 也可以用它批量取正文。
3. 页面里嵌的"在线调试"控件常常在背后请求一个 JSON（接口列表、参数定义），在 Network 面板里找它，往往等价于一份非标准的规范。
4. 实在只有 HTML 手册：按导航栏手工整理页面清单到 `index.tsv`，每页存成 Markdown（`pandoc -f html -t gfm` 或 Browser 取正文）。这种情况下字段类型、必填与否只能靠文档措辞，把不确定的地方都标 `⚠ 文档未说明`，第 3 步重点测这些。

## 产出清单

第一步结束时 scratch 目录里应该有：

```
<scratch>/
├── pages/            # Markdown 源页面（fetch_docs.sh 产出）
├── index.tsv         # 标题 / URL / 本地文件
├── openapi.json      # 规范原文（如有）
├── openapi-summary/  # 按 tag 展开后的摘要（openapi_summary.py 产出）
│   ├── index.md
│   └── <tag>.md
└── auth.md           # 鉴权精确格式、key 获取位置、签名算法
```

这些是第 2 步的输入，不是交付物，不要放进 skill 目录。
