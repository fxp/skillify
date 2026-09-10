把这份 skill 装进你的 Agent，让它写AutoDL的接入代码时不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

```
npx -y skills add fxp/skillify --skill autodl --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

其他 Agent（Codex / OpenCode / Cursor / Cline 等）同样用上面这条命令，
或直接下载 <https://github.com/fxp/skillify/raw/main/skills/autodl/autodl.skill>
按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「当前事实」和「你的训练数据在这几点上是错的」两节；
2. `references/` 下有 3 个 `.md`，其中 `instances.md` 讲的是容器实例 Pro API；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 5 处「文档与实测不符」的标记。

## 这份 skill 覆盖什么

按量租 GPU 的国内算力平台：容器实例的创建 / 开关机 / 存镜像 / 释放，以及弹性部署。**官方文档把 GET 接口的传参方式写错了**，照抄必然失败。

内容不是文档搬运：**11 条官方文档写错或漏写的地方是用真实 API 调用查出来并改正的**，每条都带实测日期与证明它的报错原文。
SKILL.md 只做分流与规则（约 100 行），细节按需从 `references/` 加载。

## 版本

内容抓取与验证于 **2026-09**。平台迭代较快——实际调用报「参数非法」或「模型不存在」时，
**以 API 的真实报错为准**，并去官方文档核实最新情况。
