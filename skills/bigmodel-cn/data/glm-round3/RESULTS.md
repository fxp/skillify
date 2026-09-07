# 第三轮 + 第三轮-b 结果（2026-09-07）

执行 Agent = GLM-5.3，两边都能 WebFetch，n=5，纯执行判分。

## 一句话结论

这一轮最有价值的产出不是分数，而是**评测查出了技能自己写错的一条建议**；改掉之后重测，
同一个场景从「skill 输给 baseline」变成「skill 4/5 vs baseline 0/5，p = 0.048」。

## 结果

| 场景 | skill | baseline | 说明 |
| :--- | :--- | :--- | :--- |
| rag-index-embeddings | 1.000 ± 0.000 | 1.000 ± 0.000 | 打平：两边都主动按 64 条分批 |
| cited-web-answer（修复前） | 0.600 ± 0.133 | 0.667 ± 0.000 | **skill 反而更低** |
| cited-web-answer（修复后，3b） | **0.933 ± 0.133** | **0.600 ± 0.133** | 满分率 4/5 vs 0/5，**Fisher p = 0.0476** ✅ |

## 技能被查出的缺陷

任务要求"给出可点击的来源链接"。10 个脚本（两边都是）**代码全都写对了**：
设了 `search_result: true`、读了 `link` 字段。但运行时一条链接都拿不到。

逐层排查后定位到真因——**`link` 是否为空完全取决于 `search_engine`**：

| search_engine | 返回条数 | `link` 非空 |
| :--- | :--- | :--- |
| `search_std` | 10 | **0** |
| `search_pro` | 10 | **0** |
| `search_pro_sogou` | 50 | 50 |
| `search_pro_quark` / `_jina` / `_bing` | 10 | 10 |

HTTP 200、条数正常、`title`/`content`/`publish_date` 全齐，唯独 `link` 是空字符串——典型静默失效。
而技能原文写的是"显式传 `search_engine`（如 `search_pro`）"，
**5 个 skill 版忠实执行了这条错误建议，全部拿不到链接**。

附带发现：`search_pro_jina`、`search_pro_bing` 这两个可用引擎**在官方参数表里根本没有列出**。

## 修复与验证（第三轮-b）

技能修正内容：`references/tools.md` 加入引擎—链接对照表并在参数表就地标注，
`references/chat.md` 把"如 `search_pro`"这个错误示例改成明确的选择指引。

用修正后的技能重跑同一场景，引擎选择出现完全分离：

| | 选的引擎 | 满分 |
| :--- | :--- | :--- |
| skill 版 | `search_pro_bing` / `search_pro_quark` ×3 / `search_pro_sogou` | 4/5 |
| baseline | `search_pro` ×5 | 0/5 |

（skill 那次未满分是 run-1 拿到链接但条数不足 2 条；baseline run-5 还额外退出码非 0。）

## 三点值得记录的观察

1. **写错的说明书比没有说明书更糟。** 修复前 skill 版（0.600）低于 baseline（0.667）——
   因为它更一致地执行了一条错误指示。baseline 的分散反而让它偶尔蒙对。
2. **两边都没有编造链接。** 拿不到来源时，脚本如实打印"接口未返回来源链接"。
   这是好行为，但我的断言只认结果不认诚实，一律判失败——设计判分标准时值得注意。
3. **embeddings 场景打平是合理的。** 64 条上限会响亮报错，而"分批"是任何称职工程师的默认习惯，
   不需要专门知识。这类"响亮且符合常识"的坑不适合作为区分度场景。
