把这份 skill 装进你的 Agent，让它写 Apify 平台接入代码时不再把 `apify-client`（调平台 API 的客户端库）和 `apify`（自己开发 Actor 用的 SDK）这两个名字撞车的包搞混，也不会拿 `status: SUCCEEDED` 当成"抓到了有意义结果"的充分证据。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill apify --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill apify --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/apify/apify.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认的几件事」和「能力域导航」三节；
2. `references/` 下有 7 个 `.md`，其中 `pricing-and-billing.md` 讲的是 compute unit（1 CU = 1GB 内存跑 1 小时）和四选一的 Actor 定价模型；
3. 在 `references/running-actors.md` 里能搜到「⚠ 文档原文，未实测」字样（这是文档版，全篇未做真实调用）。

## 这份 skill 覆盖什么

Apify（`apify.com` / `docs.apify.com`）是一个以 **Actor**（跑在 Apify 云端 Docker 容器里的爬虫/自动化程序，数千个由社区发布在 Apify Store）为核心的大型 Web 抓取与自动化市场，外加一套通用的 REST API 层。本 skill 的定位刻意收窄：只覆盖"不管跑哪个 Actor,都要用到的平台机制"——运行 Actor（同步/异步、传输入、run 生命周期与状态）、从 Dataset/Key-value store 读结果、Request Queue API、Webhooks、从 Store 挑选 Actor、按 compute unit 计费的定价模型；具体某个 Actor 自己的输入字段不在覆盖范围内。

重点是两个来自官方 OpenAPI 规范和文档正文的反直觉发现：**"Apify Client SDK" ≠ "Apify SDK"，名字故意撞在一起是最容易踩的坑**——`apify-client` 是从自己代码里调用 Apify 平台 API 的客户端库（启动 run、读 storage），`apify`（JS 和 Python 包名都叫 `apify`，官方也管它叫 "Apify SDK"）则是用来编写一个跑在 Apify 平台上的 Actor 本体的库（`Actor.init()`/`Actor.getInput()`/`Actor.pushData()`），两者输入输出、鉴权方式、使用场景完全不同，搞混了代码根本跑不起来，本 skill 只覆盖前者。**platform 层的 `status: SUCCEEDED` 不等于"这次抓取拿到了有意义的结果"**——`status` 反映的是 Actor 进程有没有正常退出（类似 exit code 语义），目标站点把请求全部拦截、或压根没匹配到数据，Actor 依然可以正常退出得到 `SUCCEEDED`；判断任务有没有真正达成目的，除了看 `status`，还要看 `statusMessage`/`exitCode`，以及实际检查 dataset 条目数量或 key-value store 里 `OUTPUT` 记录是不是空的。

另外一个成本相关的提醒：Apify 计费**不能按"每次调用固定几个 credit"估算**（和 Firecrawl/Exa/Tavily 那种模式完全不同）——基本单位是 compute unit，叠加数据传输/代理/存储读写用量，再叠加 Actor 开发者自选的四种定价模型（免费/纯平台用量/自定义事件收费/包月租用），同一任务换个 Actor 或换个目标站点，实际花费可能差几倍到几十倍。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `docs.apify.com` 核实最新情况。
