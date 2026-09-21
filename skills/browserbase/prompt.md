把这份 skill 装进你的 Agent，让它写 Browserbase / Stagehand 接入代码时不再把 Stagehand v4 当成包着 Playwright 的旧架构（v4 是 CDP 原生，`act`/`extract`/`observe` 挂在 Stagehand 实例上、不挂在 `page` 上），也不会忘记显式关闭会话导致按分钟持续计费。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill browserbase --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill browserbase --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/browserbase/browserbase.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」和「能力域导航」三节；
2. `references/` 下有 6 个 `.md`，其中 `identity-and-stealth.md` 讲的是代理、CAPTCHA 自动破解、Verified 反爬身份、允许域名限制、自定义 CA 证书；
3. 在 `references/sessions-rest.md` 里能搜到「⚠ 文档自相矛盾」字样——记录了比对官方多个页面后发现的真实不一致（比如 `keepAlive` 字段说明写"Available on the Hobby Plan"，但当前公开方案名称里根本没有"Hobby"这个档位）。

## 这份 skill 覆盖什么

Browserbase（`browserbase.com` / `docs.browserbase.com`）是面向 AI agent 的云端浏览器基础设施："the Browser Agent Platform"：原始会话管理 REST API（建会话、拿 CDP/Selenium 连接地址、列出/终止会话、录像与日志）、用 Playwright/Puppeteer/Selenium 驱动会话、自家的自然语言浏览器框架 Stagehand（`act`/`extract`/`observe`，`@browserbasehq/stagehand` 包）、完全托管的 Browserbase Agents 产品、代理/CAPTCHA 破解/Verified 反爬身份、会话生命周期与录像调试、按浏览器分钟/代理流量计费。

重点是两个真实发现的陷阱：**会话不显式关闭会持续计费**——浏览器时长按分钟计费且有 1 分钟最低消费，`keepAlive: true` 的会话不会自己结束（会一直跑到 6 小时超时上限），文档原文明确写"stop your keep alive sessions explicitly...you may be charged for the unneeded browser minutes"，写代码时必须有一条"用完调 `bb.sessions.update(id, {status: "REQUEST_RELEASE"})`"的路径，不能假设脚本正常退出就等于会话结束。**Stagehand v4 是 CDP 原生架构，不是包着 Playwright 的旧版本**——如果训练记忆里 Stagehand 是"继承 Playwright 的 `Page` 对象、调 `page.act(...)`"，那是 v2/v3 的旧形状；v4 里没有 Playwright/Puppeteer/Patchright 互操作层，`act`/`extract`/`observe` 是 `Stagehand` 实例自己的方法。另外两个安全相关开关默认值不对称：`solveCaptchas` 默认 `true`（自动破解验证码，耗时 5-30 秒），`proxies` 默认 `false`，如果只想要一个"干净不做额外处理"的会话，两个都要显式设置。

内容不是文档搬运：抓取比对多份官方页面后发现了三处文档自身矛盾（免费版并发数一处说"一次一个会话"、定价表却写"3 个"；`keepAlive` 字段的方案名和当前实际方案名对不上；"Update a Session" 的摘要说能改多个字段，但 OpenAPI 规范只定义了 `status` 一个字段），都逐条标了出来留给真实验证裁决，没有替官方文档定论。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `docs.browserbase.com` / `docs.stagehand.dev` 核实最新情况。
