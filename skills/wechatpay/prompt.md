把这份 skill 装进你的 Agent，让它写微信支付（商户 APIv3）的接入代码时，不再凭记忆编签名和参数。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已经安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill wechatpay --yes
```

装完之后，在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill wechatpay --yes`，
或者直接下载 <https://github.com/fxp/skillify/raw/main/skills/wechatpay/wechatpay.skill>，按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认下面三点，任何一点不成立都说明没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」「照通用经验写容易错的地方」这三节；
2. `references/` 下有 7 个 `.md` 文件，其中 `notifications.md` 讲的是支付回调和退款回调的验签与 AEAD_AES_256_GCM 解密；
3. 在 reference 里 `grep '<!-- Gap:'`，能搜到 2 处「文档与探测结果不符」的标记。

## 这份 skill 覆盖什么

微信支付商户平台（`pay.weixin.qq.com`）APIv3 的直连商户部分，包括：
- APIv3 请求签名与应答验签（微信支付公钥 / 平台证书）
- JSAPI / 小程序 / Native / H5 / APP 下单，以及前端调起支付的签名
- 查单与关单、退款
- 支付回调和退款回调的验签与解密
- 交易账单和资金账单
- 错误码与重试决策

**服务商模式、合单支付、分账、商家转账、营销工具和所有 V2 接口都不覆盖。**

这份内容不是简单搬运文档：
- 做了 13 次无凭证探测，确认了鉴权失败、缺 User-Agent、时间戳过期、v2 和 v3 错误模型的真实返回；
- 用文档公开的测试私钥离线复算了签名示例，发现有 2 个官方示例复算不出来；
- 所有文档自相矛盾或没说清楚的地方，都汇总在 SKILL.md 末尾。

## 版本

文档版，抓取于 2026-09-11，未用真实凭证验证。字段、错误码和行为描述来自官方文档原文，没有经过真实调用验证。
实际调用时如果报错，**以 API 返回的真实报错为准**，并到 `pay.weixin.qq.com/doc/v3/merchant` 核实最新情况。
