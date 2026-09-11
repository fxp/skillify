把这份 skill 装进你的 Agent，让它写法大大（FASC OpenAPI 5.1）电子签的接入代码时不再凭记忆编签名算法和接口参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill fadada --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill fadada --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/fadada/fadada.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」和「照通用经验写容易错的地方（来自文档，未实测）」三节；
2. `references/` 下有 7 个 `.md`，其中 `sign-tasks.md` 讲签署任务的创建、提交、撤销与查询，`auth-and-signing.md` 讲 X-FASC-Sign 请求签名；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 3 处「文档与无凭证探测不符」的标记。

## 这份 skill 覆盖什么

法大大开放平台（`dev.fadada.com`，FASC OpenAPI 5.1）最常接的链路：AppId/AppSecret 换 accessToken 与 X-FASC-* 请求签名、
个人 / 企业认证授权、文件上传与处理、签署任务全流程（创建、添加文档与参与方、提交、撤销 / 删除 / 作废、查询、签署链接、下载）、
签署模板与文档模板、回调事件接收与验签、错误码与限流。组织、印章、计费、审批、合同起草与归档、工具能力等模块未展开。

凭通用经验最容易写错的两处：**签名不是"用 AppSecret 直接 HMAC"，而是先用时间戳派生临时密钥的两步算法**；
**业务参数走表单字段 `bizContent`，不是 JSON body**。skill 里把这类坑、文档自相矛盾的地方逐条标了 ⚠。

## 版本

文档版，抓取于 2026-09-11，未用真实凭证验证。只做了无凭证探测（伪造 AppId / token 的 8 次请求），其中 3 处与文档不符已用 Gap 标注。
实际调用报错时，**以 API 的真实返回为准**，并去 `dev.fadada.com` 核实最新文档。
