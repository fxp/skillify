把这份 skill 装进你的 Agent，让它写契约锁电子签章开放平台的接入代码时不再凭记忆编签名算法和接口参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill qiyuesuo --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill qiyuesuo --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/qiyuesuo/qiyuesuo.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」和「照通用经验写容易错的地方（来自文档，未实测）」三节；
2. `references/` 下有 6 个 `.md`，其中 `auth-and-signing.md` 讲 x-qys-open-* 请求头与 MD5 签名，`signing.md` 讲签署位置、静默签、签署链接与撤回作废；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 2 处「文档与无凭证探测不符」的标记。

## 这份 skill 覆盖什么

契约锁开放平台（`open.qiyuesuo.com`，API 在 `openapi.qiyuesuo.com` / 测试 `openapi.qiyuesuo.cn`）最常接的链路：
四个 `x-qys-open-*` 请求头与 MD5 签名、合同草稿与合同文档（本地文件 / 云平台模板）、业务分类、发起合同与签署位置、
公章 / 法人章 / 审批静默签、签署页面链接、撤回删除与作废、印章与企业 / 个人认证、合同状态回调与加密回调、错误码与频次限制。
组织架构、模板创建、存证出证、授权管理、信息校验、单点登录、小程序插件与 APP SDK 未展开。

凭通用经验最容易写错的两处：**签名只是 `md5(AppToken + AppSecret + timestamp + nonce)`，不签请求内容，也没有换 token 这一步**；
**合同要"草稿 → 加文档 → 发起"三步，签署位置要用草稿返回的 actionId / signatoryId 绑定**。skill 里把这类坑、文档自相矛盾的地方逐条标了 ⚠。

## 版本

文档版，抓取于 2026-09-11，未用真实凭证验证。只做了无凭证探测（伪造 token、缺鉴权头等 8 组请求，每组复跑两次），其中 2 处与文档不符已用 Gap 标注。
实际调用报错时，**以 API 的真实返回为准**，并去 `open.qiyuesuo.com` 核实最新文档。
