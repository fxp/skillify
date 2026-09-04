# NOTES — 火山方舟 Embedding 本地语义搜索

## 文件

| 文件 | 作用 |
|---|---|
| `config.py` | 读取 `.env` / 环境变量（key、base_url、模型、维度、目录） |
| `ark_embeddings.py` | 方舟 Embedding 客户端封装：文本走 OpenAI 兼容 `/embeddings`，图片/统一空间走方舟私有 `/embeddings/multimodal` |
| `indexer.py` | 扫描 `notes/*.md` 与 `imgs/*.png`，切块、向量化、L2 归一化，存 `.index/embeddings.npy` + `meta.json`；支持增量（按文件 sha1） |
| `search.py` | 查询向量化 → 点积（=余弦）→ top-k；支持 `--by-file` 聚合、`--image` 以图搜 |

```bash
pip install -r requirements.txt
cp .env.example .env && $EDITOR .env      # 填 ARK_API_KEY
python indexer.py                          # 首次全量，之后增量
python search.py "上季度 OKR 复盘"          # top5
python search.py --by-file -k 5 "部署流程"
python search.py --image imgs/arch.png     # 以图搜图 / 搜文
```

## 端点选择

- **base_url**：`https://ark.cn-beijing.volces.com/api/v3`（方舟 OpenAI 兼容网关）。`OpenAI(api_key=ARK_API_KEY, base_url=...)` 即可。
- **Agent Plan 的注意点（需要你在控制台核对，我无法在没有 key 的情况下验证）**：
  1. 方舟的套餐类（Coding Plan 等）历史上使用**独立 base_url**（如 Coding Plan 是 `.../api/coding/v3`），且套餐通常**只覆盖对话模型**，Embedding 很可能仍按量计费或需要另开。若 Agent Plan 控制台给了专属 base_url，写进 `ARK_BASE_URL`；若 Embedding 不在套餐内，用同一个 key 打普通 `/api/v3` 即可（按量计费）。
  2. 如果 Agent Plan 只允许通过接入点（`ep-xxxxxxxx`）调用，把接入点 ID 填进 `ARK_MULTIMODAL_MODEL` / `ARK_TEXT_MODEL`，代码无需改动。
  3. 首次跑 `python indexer.py -v`，若返回 404/`ModelNotOpen`，先在控制台“开通管理”里开通对应 Embedding 模型。
- **两条通路**：
  - `/embeddings`（OpenAI 兼容）：`client.embeddings.create(model, input=[...], encoding_format="float", dimensions=...)`。支持批量（单次 ≤256 条），仅文本。
  - `/embeddings/multimodal`（方舟私有）：OpenAI SDK 没有对应方法，代码用 `client.post("/embeddings/multimodal", body=..., cast_to=httpx.Response)` 复用 SDK 的鉴权 / 重试 / 超时，然后自行 `.json()` 解析。已在本地确认 openai SDK 1.x 与 2.x 均支持 `cast_to=httpx.Response` 直通。

## 为什么默认“统一向量空间”（`EMBED_BACKEND=multimodal`）

- 余弦相似度只在**同一模型**产出的向量之间有意义。如果笔记用文本模型、截图用视觉模型，两组向量不可比，只能维护两个索引、分别检索，无法用一句话同时召回“笔记+截图”并统一排序。
- 所以默认让**笔记文本和截图都走 `doubao-embedding-vision-250615`**：一个 `embeddings.npy`，一次点积，图片可以被文本 query 召回（截图里有文字时效果尤其好）。
- 代价：多模态接口一次只产出一个向量，文本无法批量，笔记多时请求数更多（但本地笔记量级完全可接受；SDK 已配 3 次重试）。
- 若只要文本、追求批量效率，改 `EMBED_BACKEND=text`，走 `doubao-embedding-large-text-250515` 批量接口，图片会被跳过并告警。**切换后端 / 模型必须 `--rebuild`**，`indexer.py` 检测到 `meta.json` 中模型不一致会自动全量重建。

## 响应形状（两者不同，代码里 `_extract_embedding` 兼容处理）

OpenAI 兼容 `/embeddings`（`data` 是**数组**，按 `index` 对齐输入）：
```json
{"object":"list","data":[{"object":"embedding","index":0,"embedding":[...]}],
 "model":"doubao-embedding-large-text-250515","usage":{"prompt_tokens":12,"total_tokens":12}}
```

方舟 `/embeddings/multimodal`（`data` 是**单个对象**，一次请求一个向量）：
```json
{"id":"...","object":"list","created":1710000000,"model":"doubao-embedding-vision-250615",
 "data":{"object":"embedding","embedding":[...]},
 "usage":{"prompt_tokens":1234,"total_tokens":1234,
          "prompt_tokens_details":{"image_tokens":1200,"text_tokens":34}}}
```
请求体：`input` 为数组，元素为 `{"type":"text","text":"..."}` 或 `{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}`；同时给文本+图片会融合成一个向量（代码用文件名作为截图 caption 一起送入）。图片用 data URL 内嵌，无需公网可访问；大小上限保守设为 10MB，超出请先压缩。

## 维度选择

| 模型 | 原生维度 | 可截断到 |
|---|---|---|
| doubao-embedding-vision-250615（默认） | 2048 | 1024 / 512 / 256 |
| doubao-embedding-large-text-250515 | 2048 | 1024 / 512 / 256 |
| doubao-embedding-text-240715 | 2560 | 2048 / 1024 / 512 |

- 默认 `EMBED_DIM` 留空 = 用原生 2048。几百到几千条笔记，`(N, 2048)` float32 只有几十 MB，numpy 一次点积毫秒级，没必要降维。
- 若要降维（如 1024），两个模型均为 Matryoshka 训练：文本接口通过 `dimensions` 参数由服务端截断；多模态接口代码采用**客户端截取前 k 维再 L2 归一化**（等价做法，且不依赖该接口是否接受 `dimensions`）。
- 所有向量入库前都做 L2 归一化，检索时 `index.vectors @ q` 即余弦相似度，不必每次再算范数。
- `meta.json` 记录了构建时的模型与维度；查询维度与索引不一致时 `search.py` 会直接报错提示重建，避免静默出错。

## 其他实现决策

- **切块**：按空行分段贪心合并到 ≤1500 字，超长段按字符切并保留 200 字重叠。中文 1500 字约 1500–2200 token，远低于 4096/8192 token 限制。文件名作为前缀参与向量化，让标题语义进入向量。
- **增量**：按文件 sha1 判断变化，改动的文件先删旧向量再追加；被删除的文件会从索引移除。
- **未验证项（无 key，未真实调用）**：模型 ID 与维度表来自我对方舟文档的记忆，multimodal 响应形状为 `data` 单对象亦是；`_extract_embedding` 对两种形状都做了兼容，但首次运行建议加 `-v` 观察日志。本地已用 mock 跑通切块、索引、增量、检索全流程（不含网络）。
