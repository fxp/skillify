把这份 skill 装进你的 Agent，让它写 Moka（摩卡）招聘 ATS 与 People 人事开放 API 的接入代码时照文档写，不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill moka --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill moka --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/moka/moka.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」「照通用经验写容易错的地方（来自文档，未实测）」三节；
2. `references/` 下有 8 个 `.md`，其中 `people-hr.md` 讲的是 Moka People 人事 API（部门、员工任职数据、新增 / 离职员工、待入职）；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 1 处「文档与探测不符」的标记（在 `auth.md`）。

## 这份 skill 覆盖什么

Moka 开放平台（`open.mokahr.com`）的两套接口：

- **ATS 招聘**（`api.mokahr.com/api-platform`）：组织架构与用户同步、职位与招聘需求、候选人与申请（增量拉取、上传简历、移动阶段、归档）、面试、Offer、入职标记、主动推送；
- **People 人事**（`api.mokahr.com/api-platform/hcm/oapi`）：部门、员工任职数据、新增 / 更新 / 离职员工、待入职、职位职务、主动推送；
- 两套共用的错误码、限流、分页与时间格式。

重点讲清通用经验最容易写错的地方：两套 API 鉴权不同、People 每个请求都要 MD5withRSA 签名且每个能力一个 apiCode、
ATS 各接口成功码不统一、分页方式至少五种、`PUT /v2/departments` 是会标记删除的全量同步、Webhook 要对原始 body 验签。

## 版本

文档版，抓取于 **2026-09-11**，**未用真实凭证验证**——只做了无凭证探测（伪造 Key / 签名，确认鉴权失败格式、接口路径是否存在、域名），
报错描述大多是文档原文。实际调用报错时，**以 API 的真实报错为准**，并去 `www.mokahr.com/docs/api/` 与 `people.mokahr.com/docs/api/view/v1.html` 核实最新情况。
