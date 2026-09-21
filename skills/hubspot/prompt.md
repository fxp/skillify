把这份 skill 装进你的 Agent，让它写 HubSpot CRM API 代码时不再凭训练记忆假设还在用早已弃用的 `hapikey` 鉴权，也不会把 `company` 这种纯文本属性当成真实关联、或把 `filterGroups` 的 AND/OR 顺序搞反。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill hubspot --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill hubspot --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/hubspot/hubspot.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「用之前先确认 3 件事」「能力域导航」三节；
2. `references/` 下有 6 个 `.md`，其中 `associations.md` 讲的是关联（association）为什么是独立 API 而不是字段；
3. 在 `SKILL.md` 里能搜到「⚠ 文档自相矛盾」字样，附带两处官方文档给出不同数字/措辞的具体出处。

## 这份 skill 覆盖什么

HubSpot CRM API（`developers.hubspot.com` 是文档站，真正的 API 域名是 `api.hubapi.com`）的统一对象模型：contacts/companies/deals 等标准对象与自定义对象共用的 `crm/objects/{objectType}` 增删改查、鉴权（私有应用 access token / 新版 Service Key beta / OAuth）、associations（关联）、search（filterGroups 过滤）、batch 批量操作、限流与错误处理。

内容不是文档搬运，重点是两处真实发现的反直觉陷阱：一是**鉴权已经不是训练语料里常见的「HubSpot API Key」**——那种全局 `hapikey` query 参数式鉴权多年前已弃用，当前是按 scope 授权的 `Authorization: Bearer <token>`（私有应用 token 或 OAuth），凭记忆套用旧鉴权方式会直接错；二是**关联（association）不是记录上的一个字段，是独立的 API 调用**——HubSpot 自己的文档示例本身就是这个陷阱的活证据：创建联系人时给的示例请求体里 `company: "HubSpot"` 只是一个纯文本属性，只设置它「看起来做对了」但不会创建任何真实关联，能在公司详情页关联列表、associations API 里被查到的关联必须另外调用 associations 相关端点建立。SKILL.md 还如实标注了抓取时发现的两处文档自相矛盾：私有应用页与限流总页对「API Limit Increase」加购后的 burst 限速给出不同数字（200 vs 250 次/10 秒），以及 2026-09 起 HubSpot 对 CRM 写操作强制执行管理员配置校验规则这条新变化，文档没写清楚是否只影响新版日期路径前缀——两处都标了 `⚠` 未擅自裁决，留给拿到真实 key 后核实。

## 版本

文档版，抓取于 2026-09-21，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `developers.hubspot.com/docs` 核实最新情况（该文档抓取日期晚于模型训练截止日期，HubSpot 期间发布了日期版本化 API 等新变化）。
