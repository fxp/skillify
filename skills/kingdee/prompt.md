把这份 skill 装进你的 Agent，让它写金蝶云星空（K/3 Cloud）的对接代码时不再凭记忆编签名算法、接口名和字段标识。

请你自己执行下面的步骤，不要让我手动跑命令。执行前先检查是否已安装过（幂等）。

## 安装

### Claude Code

```
npx -y skills add fxp/skillify --skill kingdee --yes
```

装完在 Claude Code 里执行 `/reload-plugins` 让它生效——**这一步需要我手动做，你无法代劳**。

### 其他 Agent（Codex / OpenCode / Cursor / Cline 等）

同样用 `npx -y skills add fxp/skillify --skill kingdee --yes`，
或直接把 <https://github.com/fxp/skillify/raw/main/skills/kingdee/kingdee.skill>
下载后按你的 Agent 的 skill 安装方式加载。

## 装完自检

装好后请确认这三点，任一不成立就是没装对：

1. `SKILL.md` 里有「⚠ 验证状态」「当前事实」「照通用经验写容易错的地方」三节，开头写明只覆盖金蝶云星空、不覆盖星瀚 / 苍穹 / 旗舰版 / 精斗云；
2. `references/` 下有 6 个 `.md`：`auth-and-connection.md`、`bill-query.md`、`bill-operations.md`、`master-data.md`、`finance-vouchers.md`、`errors-and-responses.md`；
3. `references/auth-and-connection.md` 里有「不用 SDK：签名算法逐步拆解」和「无凭证探测结果」两节。

## 这份 skill 覆盖什么

金蝶云星空 WebAPI（客户自己的星空站点，接口形如 `POST {ServerUrl}/{ServiceName}.common.kdsvc`）：
第三方系统登录授权的签名头（按官方 Python SDK 源码逐步拆解）与会话登录、ExecuteBillQuery 查询与分页、
单据保存 / 提交 / 审核 / 下推 / 禁用作废、物料客户供应商与多组织分配、总账凭证与应收应付、返回结构与报错排查。
**不覆盖**金蝶云星瀚、苍穹、星空旗舰版、精斗云、KIS——接口完全不同，别拿去对接它们。

最常见的坑都在 SKILL.md 顶部：没有公共 API 域名、签名是 base64(hex(HMAC))、查询返回裸二维数组、
改单默认删掉没传的分录、保存 / 提交 / 审核是三个接口。

## 版本

文档版，抓取于 2026-09-11，未用真实凭证验证。内容来自 open.kingdee.com 的公开 API 文档（API 版本 7.5.1800.6）
和官方 Python SDK 8.2.0 源码；需要登录的新版 API 中心没有抓取。实际调用报错时，**以客户星空服务器的真实返回为准**，
并去 `openapi.open.kingdee.com` 核实最新文档。
