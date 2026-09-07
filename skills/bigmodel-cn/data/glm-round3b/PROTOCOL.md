# 第三轮-b：修复技能后重测引用场景（开跑前冻结）

## 为什么有这一轮

第三轮 `cited-web-answer` 两边都拿不到链接（10/10 全失分）。排查发现**根因在技能自己身上**：
技能建议"显式传 search_engine（如 search_pro）"，而实测 `search_pro` / `search_std`
返回的来源 `link` **恒为空字符串**——只有 `search_pro_bing` / `_jina` / `_quark` / `_sogou` 带真实链接。
5 个 skill 版忠实执行了这条错误建议，全军覆没。

**这是评测查出了技能的缺陷**，不是场景无效。技能已于 2026-09-07 修正
（`references/tools.md` 加入引擎—链接对照表，`chat.md` 改掉"如 search_pro"的错误示例）。
本轮用修正后的技能重跑同一场景，验证修复是否真的有效。

## 场景 cited-web-answer（与第三轮完全相同的任务）

写联网问答脚本，答案后必须附上**接口真实返回的**来源标题与可点击 URL。

**判分（满分 3）**：① 退出码 0 ② stdout 至少 2 条 http(s) 链接
③ 链接取自接口返回（代码读了 `web_search` / `search_result` 数组）

条件不变：执行 Agent = GLM-5.3、两边都能 WebFetch、n=5、纯执行判分。
