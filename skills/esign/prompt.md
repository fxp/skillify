把这份 skill 装进你的 Agent，让它写 e签宝（SaaS API V3）电子签的接入代码时不再凭记忆编签名算法和接口参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill esign --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill esign --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/esign/esign.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」和「照通用经验写容易错的地方（来自文档，未实测）」三节；
2. `references/` 下有 6 个 `.md`，其中 `sign-flows.md` 讲签署流程的发起、签署链接、撤销、完结与下载，`auth-and-signing.md` 讲 X-Tsign-Open-Ca-Signature 请求签名；
3. 在 `references/auth-and-signing.md` 里能找到「11. 无凭证探测结果」一节（9 条伪造 appId 的探测记录）。

## 这份 skill 覆盖什么

e签宝开放平台（`open.esign.cn`，SaaS API V3）最常接的链路：X-Tsign-Open-* 请求头与 HmacSHA256 请求签名、
本地文件上传与合同模板填充、签署流程全流程（发起、签署方与签署区、签署链接、查询、撤销、完结、延期催签、下载）、
个人与机构实名认证和用户授权、回调通知接收与验签、错误码与限制。印章、成员、企业控制台、合同管理、解约出证等模块未展开。

凭通用经验最容易写错的两处：**签名串是 7 行换行拼接再 HmacSHA256 取 Base64，Content-MD5 是 MD5 原始字节的 Base64**；
**`autoFinish` 默认 false，签完不调 `/finish` 流程就不会完成、也下载不了合同**。skill 里把这类坑、文档自相矛盾的地方逐条标了 ⚠。

## 版本

文档版，抓取于 2026-09-11，未用真实凭证验证。只做了无凭证探测（伪造 appId / token 的 9 类请求，各复跑两次），没有发现能证实文档写错的结果。
实际调用报错时，**以 API 的真实返回为准**，并去 `open.esign.cn` 核实最新文档。
