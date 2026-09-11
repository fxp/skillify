把这份 skill 装进你的 Agent，让它写钉钉开放平台的接入代码时不再凭记忆混用新旧两套 API。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill dingtalk --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill dingtalk --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/dingtalk/dingtalk.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」和「照通用经验写容易错的地方」三节；
2. `references/` 下有 7 个 `.md`，其中 `events.md` 讲的是 Stream 模式与 HTTP 回调加解密；
3. 在 reference 里 `grep '<!-- Gap:'` 能搜到 4 处「探测证实的文档错误」标记。

## 这份 skill 覆盖什么

钉钉开放平台（`open.dingtalk.com`）企业开发最常接的 7 块：access token（企业内部应用、第三方企业应用、
用户 OAuth、免登）、通讯录、消息（工作通知 / 自定义机器人 / 企业机器人 / 互动卡片与 AI 流式卡片）、OA 审批、考勤、
事件订阅（Stream 模式与 HTTP 回调加解密）、错误码与限流。
重点是**新版 `api.dingtalk.com`（token 放 `x-acs-dingtalk-access-token` header）与旧版 `oapi.dingtalk.com`
（token 放 `access_token` 参数）两套并存、不能混用**——放错位置、按 HTTP 状态码判成败，是最常见的坑。

内容不是文档搬运：用伪造值做了 14 次无凭证探测，查出 **4 处官方文档写错的地方**（示例传参方式、接口路径、
错误码、错误字段名），另有 20 余处文档自相矛盾或未说明的地方逐一标了 ⚠。

## 版本

文档版，抓取于 2026-09-11，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `open.dingtalk.com/document` 核实最新情况。
