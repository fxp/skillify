把这份 skill 装进你的 Agent，让它写 TAPD（腾讯敏捷研发协作平台）开放 API 的接入代码时不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill tapd --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill tapd --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/tapd/tapd.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」「照通用经验写容易错的地方（来自文档，未实测）」三节；
2. `references/` 下有 7 个 `.md`，其中 `webhooks-events.md` 讲的是 Webhook 事件订阅（两条接入渠道、事件名、报文字段与 secret 校验）；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 3 处「文档与探测不符」的标记（`auth.md`、`webhooks-events.md`、`query-errors-limits.md` 各 1 处）。

## 这份 skill 覆盖什么

TAPD 开放平台（`open.tapd.cn`，API 域名 `api.tapd.cn`）里研发团队最常接的七块：
鉴权（API 账号 HTTP Basic、开放应用 access_token、OAuth 与 scope）与项目前置、需求、缺陷、任务与迭代、
工时与测试用例 / 测试计划、Webhook 事件订阅与推送、通用查询语法 / 分页 / 错误码与频率限制。

重点讲清通用经验最容易写错的地方：API 账号不是登录账号、创建和更新是同一个 POST、
查询运算符写在值里（`modified=>…`、`status=a|b`）、`page×limit` 超过 20000 要改用游标、
缺陷和需求的字段名不一样、工时的唯一约束、Webhook 没有签名且默认是 form 编码。

## 版本

文档版，抓取于 **2026-09-11**，**未用真实凭证验证**——只做了无凭证探测（伪造凭证确认鉴权失败格式、拼错路径的返回、http 明文行为），
报错描述大多是文档原文。实际调用报错时，**以 API 的真实报错为准**，并去 `open.tapd.cn/document/api-doc/` 核实最新情况。
