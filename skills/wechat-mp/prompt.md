把这份 skill 装进你的 Agent，让它写微信公众平台的接入代码时不再凭记忆混淆模板消息、订阅通知与客服消息，也不会把 snsapi_base 和 snsapi_userinfo 弄反。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill wechat-mp --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill wechat-mp --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/wechat-mp/wechat-mp.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」和「我要做什么」三节；
2. `references/` 下有 8 个 `.md`，其中 `template-subscribe.md` 讲的是模板消息、订阅通知、一次性订阅消息三套机制的区别；
3. 在 `references/errors-and-limits.md` 里能搜到「无凭证探测」字样，附带真实的 curl 命令和响应片段。

## 这份 skill 覆盖什么

微信公众平台服务端 API（`developers.weixin.qq.com/doc/service/`，域名 `api.weixin.qq.com`）开发最常接的 8 块：
access_token 获取（含官方推荐的稳定版接口）、用户管理（关注者列表、用户信息、标签、黑名单）、被动回复与客服消息、
模板消息与订阅通知、自定义菜单、网页授权 OAuth2.0、服务器配置与消息加解密、全局错误码与调用限额。
重点是**模板消息 / 订阅通知 / 一次性订阅消息三套机制目前并存**（官方原文"服务号订阅通知功能开启灰度测试，模板消息能力可正常使用"），
以及 **snsapi_base（静默拿 openid）与 snsapi_userinfo（需用户手动同意才能拿昵称头像）两种网页授权 scope 的精确区别**——
这两处是有经验的开发者也容易凭其他平台习惯写错的地方。

内容不是文档搬运：文档站本身在抓取时已经从旧版 `doc/offiaccount/` 改版拆分为「服务号」与「公众号（原订阅号）」两套入口，
skill 里记录了这个变化，避免 Agent 按训练记忆里的旧 URL 找文档；另外用伪造的 appid/secret/access_token 做了 18 次无凭证探测，
确认了全平台"HTTP 200 + errcode 业务错误码"的统一响应模式、以及两套 access_token（全局 vs 网页授权）在报错文案上的细微差异，
其余文档自相矛盾或未说明之处（如消息推送数据格式 XML/JSON 的矛盾、AES 加解密 IV 推导未写明）标了 ⚠ 留给拿到真实凭证的人补测。

## 版本

文档版，抓取于 2026-09-17，未用真实凭证验证。实际调用时报错与 skill 不一致，
**以 API 的真实报错为准**，并去 `developers.weixin.qq.com/doc/service/` 核实最新情况（公众号运营接口迭代较快）。
