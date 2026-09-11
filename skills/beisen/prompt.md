把这份 skill 装进你的 Agent，让它写北森 iTalent OpenAPI 的接入代码时不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill beisen --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill beisen --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/beisen/beisen.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」「照通用经验写容易错的地方（来自文档，未实测）」三节；
2. `references/` 下有 7 个 `.md`，其中 `employees.md` 讲的是员工与任职记录的全量 / 增量同步（时间窗滚动查询 scrollId）；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 1 处「文档与探测不符」的标记（在 `auth-and-conventions.md`）。

## 这份 skill 覆盖什么

北森开放平台（`open.italent.cn`，接口域名 `openapi.italent.cn`）新版 v3.0 接口里，企业最常对接的七块：
换 token 与连接器 / 受信 IP、组织与岗位、员工与任职记录（全量 / 增量同步、ID 反查、字段翻译）、
入职 / 转正 / 调动 / 离职、假勤（休假、余额、考勤记录、打卡读取与异步推送）、招聘（申请、应聘者、流程阶段、职位、入职管理）、错误码与限流。

重点讲清通用经验最容易写错的地方：token 是表单 POST 到 `/OAuth/Token`、查询接口也是 POST 且用 scrollId 滚动（10 秒过期、90 天窗口）、
默认取到的是“最新”而不是“当前”任职、各类 ID 类型不同、三套响应外壳、异步推送要用 `X-PAAS-Request-ID` 查结果。

## 版本

文档版，抓取于 **2026-09-11**，**未用真实凭证验证**——只做了无凭证探测（伪造 tenant_id / token，确认 token 接口地址、鉴权失败格式），
报错描述大多是文档原文。实际调用报错时，**以 API 的真实报错为准**，并去 `open.italent.cn/#/open-document` 核实最新情况。
