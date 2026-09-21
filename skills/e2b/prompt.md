把这份 skill 装进你的 Agent，让它写 E2B 沙箱代码时不再假设超时到期后沙箱只是被暂停——默认行为是直接**杀掉**，文件系统和内存状态永久丢失，也不会把 JS 的毫秒超时（`timeoutMs`）和 Python 的秒超时（`timeout`）弄混。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill e2b --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill e2b --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/e2b/e2b.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 4 件事」和「我要做什么 → 读哪一份」三节；
2. `references/` 下有 5 个 `.md`，其中 `lifecycle-and-cost.md` 讲的是 create/connect、超时、暂停/恢复/快照、自动唤醒和按秒计费的公式；
3. 在 `references/errors-and-limits.md` 里能搜到「⚠ 文档原文，未实测」字样（这是文档版，全篇未做真实调用）。

## 这份 skill 覆盖什么

E2B（`e2b.dev` / `docs.e2b.dev`）是让 AI Agent 在隔离的 Linux microVM（"沙箱"）里运行生成代码、shell 命令和文件操作的云平台，几乎完全通过 SDK 使用（Python `e2b` / `e2b-code-interpreter`，JS/TS `e2b` / `@e2b/code-interpreter` / `@e2b/cli`）：创建/连接沙箱、运行代码（Code Interpreter）和 shell 命令、文件系统读写/上传/下载、生命周期管理（超时、暂停/恢复、快照、自动唤醒）、通过公网 URL 暴露端口、按秒计费。

重点是文档原文里最大的一个坑：**新建沙箱默认 5 分钟超时，`onTimeout` 默认是 `"kill"`——不是暂停**。一个跑超过 5 分钟又没有延长超时的 Agent 任务会永久丢失沙箱、它的文件系统和任何内存中的状态，无法恢复；要避免这种情况，要么传更长的超时，要么定期调用 `setTimeout()`/`set_timeout()`，要么在创建时设置 `lifecycle: { onTimeout: "pause", autoResume: true }` 让超时变成暂停而不是销毁。第二个坑是**超时的单位因语言而异**——JS/TS 是 `timeoutMs`（毫秒），Python 是 `timeout`（秒），两者默认都是 5 分钟但单位写错会差 1000 倍。另外 `Sandbox.connect()` 只会延长超时、永远不会缩短它（新到期时间是 `max(当前到期时间, now + timeout)`），这一点也常被想当然地当成"重新设置超时"。

内容不是文档搬运：写作时（2026-09-21）没有可用的 API key，所以 skill 明确跳过了 `create-doc-skill` 方法论的第 3 步（真实 API 验证）和第 4 步（有/无 skill 对照实验），每条事实性陈述都标了 `⚠ 文档原文，未实测`，没有一条经过真实 API 响应、真实报错或真实账单确认。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `docs.e2b.dev` 核实最新情况。
