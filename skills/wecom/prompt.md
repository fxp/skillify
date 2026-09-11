把这份 skill 装进你的 Agent，让它写企业微信（WeCom）服务端 API 的接入代码时不再凭记忆编参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill wecom --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill wecom --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/wecom/wecom.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」「照通用经验写容易错的地方（来自文档，未实测）」三节；
2. `references/` 下有 7 个 `.md`，其中 `callbacks-crypto.md` 讲的是回调 URL 验证与消息加解密（WXBizMsgCrypt）；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 1 处「文档与探测不符」的标记（在 `customer-contact.md`）。

## 这份 skill 覆盖什么

企业微信开发者中心（`developer.work.weixin.qq.com`）的服务端 API 中，企业自建应用最常接的七块：
access_token 与各类应用 secret、通讯录（成员 / 部门 / 标签）、应用消息与群机器人、
客户联系（外部联系人、客户群、「联系我」、群发、欢迎语——企业微信的 CRM 能力）、审批、回调配置与消息加解密、错误码与频率限制。

重点讲清通用经验最容易写错的地方：token 放 URL 而不是 header、secret 按应用区分不能混用、
客户联系和审批要先把自建应用配进「可调用接口的应用」、回调 AES 填充按 32 字节、客户联系 API 操作不触发回调。

## 版本

文档版，抓取于 **2026-09-11**，**未用真实凭证验证**——只做了无凭证探测（伪造参数确认路径、鉴权失败格式与 token 位置），
报错描述大多是文档原文。实际调用报错时，**以 API 的真实报错为准**，并去 `developer.work.weixin.qq.com/document/` 核实最新情况。
