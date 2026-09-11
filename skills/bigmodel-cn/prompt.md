把这份 skill 装进你的 Agent，让它写智谱 BigModel 的接入代码时不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill bigmodel-cn --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill bigmodel-cn --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/bigmodel-cn/bigmodel-cn.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「当前事实」和「你的训练数据在这几点上是错的」两节；
2. `references/` 下有 10 个 `.md`，其中 `coding-plan.md` 讲的是 GLM Coding Plan 编程套餐；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 9 处「文档与实测不符」的标记。

## 这份 skill 覆盖什么

智谱开放平台（`open.bigmodel.cn`）全部能力：GLM 系列对话与多模态、图像与视频生成、
语音识别与合成、向量化与重排序、联网搜索、文件与批处理、托管知识库、Agents、GLM-Realtime、
OpenAI / Claude / LangChain 兼容层，**以及 GLM Coding Plan 编程套餐**——
套餐的 Key、Base URL、可用模型都与标准 API 不同，「买了套餐却报 1113 余额不足」是最常见的坑。

内容不是文档搬运：**16 条官方文档写错或漏写的地方是用真实 API 调用查出来并改正的**，
每条都带实测日期与证明它的报错原文。

## 版本

内容抓取与验证于 **2026-09**。平台迭代较快——实际调用报「参数非法」或「模型不存在」时，
**以 API 的真实报错为准**，并去 `docs.bigmodel.cn` 核实最新情况。
