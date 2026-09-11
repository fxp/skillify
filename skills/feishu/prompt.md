把这份 skill 装进你的 Agent，让它写飞书开放平台（open.feishu.cn）的接入代码时不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill feishu --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill feishu --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/feishu/feishu.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」和「照通用经验写容易错的地方（来自文档，未实测）」三节；
2. `references/` 下有 8 个 `.md`：`auth.md`、`contacts.md`、`messaging-bots.md`、`bitable.md`、`approval.md`、
   `corehr.md`、`events-callbacks.md`、`errors-and-limits.md`，其中 `messaging-bots.md` 讲了自定义群机器人 webhook 的签名算法；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 2 处「文档与探测不符」的标记（都在 `errors-and-limits.md`）。

## 这份 skill 覆盖什么

飞书开放平台企业开发者最常接的 8 块：tenant / app / user 三种 access token（含 OAuth v3 端点）、
通讯录用户与部门、消息与机器人（应用机器人 + 自定义群机器人 webhook）、多维表格、审批、
飞书人事（企业版员工与入职，附标准版花名册）、事件订阅与回调（challenge、验签、解密、去重）、错误码 / 频控 / 分页。

重点是「照别家平台习惯会写错」的地方：换 token 失败 HTTP 仍是 200、`content` 在两种机器人里一个是字符串一个是对象、
自定义机器人签名把 `timestamp\n密钥` 当 HMAC 的 key、事件验签是纯 SHA-256 不是 HMAC、`user_id_type` 默认 `open_id`、
多维表格日期写毫秒且写入读出格式不对称……每条都标了文档出处。

## 版本

**文档版，抓取于 2026-09-11，未用真实凭证验证。** 只做过 20 次无凭证探测（伪造 ID / token，不创建任何资源），
结论写在各 reference 里并注明「无凭证探测」。实际调用报错时**以 API 的真实返回为准**，并去 `open.feishu.cn/document` 核实最新情况。
