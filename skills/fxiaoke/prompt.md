把这份 skill 装进你的 Agent，让它写纷享销客（CRM）开放平台的接入代码时不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill fxiaoke --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill fxiaoke --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/fxiaoke/fxiaoke.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」「照通用经验写容易错的地方」三节；
2. `references/` 下有 8 个 `.md`，其中 `custom-objects.md` 讲的是 apiName 以 `__c` 结尾的自定义对象；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 3 处「探测证实的文档错误」标记。

## 这份 skill 覆盖什么

纷享销客 CRM 开放平台（`open.fxiaoke.com`，文档在 `developer.fxiaoke.com/openapi_v2`）最常接的 8 块：
鉴权与公共参数（新旧两代传参、按所在云选域名）、对象与字段描述、查询条件与分页（含 offset 1 万上限的深翻页）、
客户 / 联系人 / 线索 / 商机等预置对象、`__c` 自定义对象、通讯录、企信消息推送、错误码与限流。

内容不是文档搬运：**把 1300 页文档里自相矛盾、互相复制错的地方逐条标了 ⚠**，
并用无凭证探测查出 3 处文档写错的地方（API 域名、两个错误码的含义），每条都带探测日期和响应原文。

## 版本

文档版，抓取于 **2026-09-11**，**未用真实凭证验证**。实际调用报「参数不合法」「无此操作的数据权限」时，
**以 API 的真实报错为准**，并去 `developer.fxiaoke.com/openapi_v2` 核实最新情况。
