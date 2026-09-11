# 商品：创建、编辑、上下架、查询、库存价格

内容整理自 https://doc.youzanyun.com/ （抓取于 2026-09-11）。**未用真实凭证验证。**
报错与行为描述未标注来源的都是「文档原文，未实测」；本文件唯一的探测结论来自 `youzan-workspace/probe-log.md`。调用格式见 `auth-token.md` 第 4 节。

## 目录
1. 新商品模型：item_id 与 channel_item_id
2. 创建商品 `youzan.item.common.create.1.0.0`
3. 编辑商品 `youzan.item.common.update.1.0.0`
4. 上下架 `youzan.item.display.update.1.0.0`
5. 查询详情 `youzan.item.itemdetail.get.1.0.0` / `youzan.item.detail.get.1.0.1`
6. 商品列表 `youzan.item.base.search.1.0.0` / `youzan.items.onsale.get.3.0.0`
7. 改价改库存
8. 删除 `youzan.item.delete.3.0.1`
9. 商品消息
10. 单位与时间格式速查
11. ⚠ 本文件的文档矛盾 / 未说明

---

## 1. 新商品模型

新版商品开放（`youzan.item.common.*`、`youzan.item.itemdetail.get`、`youzan.item.base.search` 等）统一了微商城和连锁的商品模型：

| 字段 | 新版含义 | 老版接口 / 其他域 |
|---|---|---|
| `item_id` | 商品 ID，**在所有分店和渠道都一样** | 老版里同一商品在总部、门店、网店 id 不同 |
| `channel_item_id` | 渠道商品 ID，不同分店 / 渠道不同，**等于老版的 item_id** | — |
| `sku_id` / `channel_sku_id` | 同上的规格维度 | — |

- 订单里的 `orders[].item_id` / `sku_id`：微商城和 `unified_item_id` 一致；门店 / 连锁对应的是**渠道**商品 id（trade.get 字段说明），跨接口关联时注意用对哪一个。
- `channel`：0 网店、1 门店。微商城单店一律传 0。
- 零售门店、连锁：`item.common.create` 创建后**不会自动发布到门店 / 网店渠道**，要再调 `youzan.item.channel.publish` 才能售卖；微商城创建即可售（商品开放说明页）。

## 2. 创建商品

**Endpoint**: `POST /api/youzan.item.common.create/1.0.0`（计费）
**用途**: 创建实物、虚拟、电子卡券、蛋糕烘焙、海淘五类商品。

**关键参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| publish_code | String | 是 | 商品发布类型：`00000000000000000` 实物、`01000000000100000` 蛋糕烘焙、`01000000004304300` 海淘、`00000000000000002` 虚拟、`00000000000000003` 电子卡券（后者取自 base.search 的枚举说明） |
| title | String | 是 | ≤ 100 字，受违禁词控制 |
| media.image_ids | List<Long> | 是 | 主图 id，**先用 `youzan.materials.storage.platform.img.upload` 上传拿 id**；不传 → `121009313 至少上传一张图片` |
| specs[] | List | 多规格必传 | `spec_name`（规格项名，如“颜色”）、`spec_values[]`（`spec_name`、`spec_value_name`、`spec_image_id`）、`is_show_spec_picture` |
| skus[].spec_values[] | List | 否 | 该 SKU 的规格组合：`spec_name`、`spec_value_name` |
| skus[].price | Long | 是 | **价格，单位分** |
| skus[].cost_price | Long | 否 | 成本价，分 |
| skus[].spot_stock_num | Long | 否 | 现货库存 |
| skus[].sku_code / sku_barcode | String | 否 | 规格编码 / 条码 |
| skus[].item_weight | Long | 否 | 重量，克 |
| skus[].disable_status | Integer | 否 | 0 启用、1 禁用（至少一个启用） |
| item_code / item_barcode | String | 否 | 商品编码 / 条码 |
| display | Integer | 否 | 默认 1 上架；0 放入仓库 |
| auto_display_on_time | Long | 否 | 定时上架时间，**毫秒**；0 立即出售 |
| distribution_mark | object | 否 | `is_express`、`is_city_delivery`、`is_self_pick`；快递发货时 `delivery_template_id` 与 `postage`（统一邮费，**分**）二选一 |
| stock_deduct_mark.stock_deduct_mode | Integer | 否 | 0 拍下减库存、1 付款减库存、2 非预占付款扣库存 |
| content | String | 否 | 商品描述，5 ~ 25000 字 |
| origin | String | 否 | 划线价（单位 ⚠ 文档未说明） |
| group_ids / classification_id / brand_id / item_category | — | 否 | 分组、分类、品牌、类目（叶子类目 id） |
| pre_sale_mark | object | 否 | 预售：`deposit`（定金，分）、各时间字段（毫秒） |

**示例请求**（按参数表拼装，未实测：两种颜色、各 19.90 元、各 100 件）
```bash
curl -X POST "https://open.youzanyun.com/api/youzan.item.common.create/1.0.0?access_token=$YOUZAN_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' -d @- <<'JSON'
{
  "publish_code": "00000000000000000",
  "title": "纯棉T恤",
  "media": {"image_ids": [123456789]},
  "specs": [{"spec_name": "颜色", "spec_values": [
      {"spec_name": "颜色", "spec_value_name": "红"},
      {"spec_name": "颜色", "spec_value_name": "黑"}]}],
  "skus": [
    {"spec_values": [{"spec_name": "颜色", "spec_value_name": "红"}], "price": 1990, "spot_stock_num": 100, "sku_code": "TS-RED"},
    {"spec_values": [{"spec_name": "颜色", "spec_value_name": "黑"}], "price": 1990, "spot_stock_num": 100, "sku_code": "TS-BLK"}
  ],
  "distribution_mark": {"is_express": true, "postage": 0},
  "display": 1
}
JSON
```
```python
from decimal import Decimal
def yuan_to_fen(v) -> int:
    return int((Decimal(str(v)) * 100).quantize(Decimal("1")))

params = {
    "publish_code": "00000000000000000", "title": title,
    "media": {"image_ids": image_ids},                 # 必填，先上传图片
    "specs": [{"spec_name": "颜色", "spec_values": [{"spec_name": "颜色", "spec_value_name": c} for c in colors]}],
    "skus": [{"spec_values": [{"spec_name": "颜色", "spec_value_name": c}],
              "price": yuan_to_fen("19.90"), "spot_stock_num": 100} for c in colors],
}
created = call("youzan.item.common.create", "1.0.0", params, kdt_id=kdt_id)
item_id, alias = created["item_id"], created["alias"]
```

**示例响应**（文档原文）
```json
{"trace_id": "yz7-...", "code": 200, "data": {"item_id": 4315547367, "alias": "363do8d32dom7bq"}, "success": true, "message": "successful"}
```
错误：`121009313` 至少一张图片、`301000004` 参数非法、`301000002` 参数缺失（看 message 定位字段）。

**注意事项**
- 价格传分（整数），**19.90 元传 1990**；传 19.9 会被当成 19.9 分或类型错误。
- `specs` 与 `skus[].spec_values` 的规格项名 / 值要一一对应 → 具体校验规则 ⚠ 文档未说明。
- `youzan.item.add.1.0.0`（老接口，建议单店 30 QPS）在不同店铺类型的必填 JSON 各不相同（`resource/doc/5220`），新接入优先用 `item.common.create`。

## 3. 编辑商品

**Endpoint**: `POST /api/youzan.item.common.update/1.0.0`
- 支持微商城单店、新商品模型的零售单店、连锁总部；**不支持修改连锁分店商品**。
- `item_id` 必填；**除必填字段外，不传的字段不更新**。
- **规格是覆盖式更新**：要改规格必须传完整的 specs + skus；只想改某个 sku 的库存 / 价格，用 `youzan.item.quantity.update.4.0.0` 和 `youzan.item.price.update.1.0.0`（这两个参数表本 skill 未收录 ⚠）。
- 成功返回 `data.item_id`、`data.alias`；异常 `30100012`（llms 摘要）。

## 4. 上下架

**Endpoint**: `POST /api/youzan.item.display.update/1.0.0`

```json
{"request": {"kdt_id": 12345, "item_ids": [365112687], "channel": 0, "display": 1}}
```
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| request.kdt_id | Long | 是 | 店铺 id；总部改分店渠道商品时传分店 kdt_id |
| request.item_ids | List<Long> | 是 | 连锁传总部网店商品 id |
| request.channel | Integer | 是 | 0 网店、1 门店 |
| request.display | Integer | 是 | 0 下架、1 上架 |

- 参数**包在 `request` 对象里**，不是顶层。
- 参加营销活动的商品不能下架：`121001010`。
- 连锁分店不能自己上下架门店 / 网店渠道商品。

## 5. 查询商品详情

### `youzan.item.itemdetail.get.1.0.0`（新模型，推荐）
```json
{"request": {"kdt_id": 12345, "item_id": 365112687, "channel": 0}}
```
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| request.kdt_id | Long | 是 | 查分店商品传分店 kdt_id |
| request.channel | Integer | 是 | 0 网店、1 门店；微商城传 0 |
| request.item_id | Long | 三选一 | 微商城**只能**用 item_id（否则 `301002567`） |
| request.item_barcode / item_code | String | 三选一 | 仅零售店铺 |

响应 `data`：`item_id`、`alias`、`title`、`item_type`（0 实物、1 虚拟、2 服务）、`publish_code`、`sold_status`（1 发售中、2 已售罄、3 部分售罄）、
`item_price_param.price`（**分**）、`sku_list[]`（`sku_id`、`price` 分、`cost_price` 分、`stock_num`…）、`channels[]`（渠道维度的 `channel_item_id`、`channel_sku_list`…）。
- **门店渠道（channel=1）的 `stock_num`、`spot_stock_num`、`plan_stock_num` 是乘 1000 的值**；文档推荐用 `stock_num_str`、`spot_stock_num_str`、`plan_stock_num_str`。
- 不支持：门店商品反查网店商品、分店查总部商品、分店跨渠道查。
- 错误：`122001001` 商品不存在、`301000002` 缺 item_id / item_barcode / item_code。

### `youzan.item.detail.get.1.0.1`（“查询单商品明细接口-推荐使用”）
参数 `item_id` 或 `alias`（单店二选一；**连锁不支持 alias**）、`node_kdt_id` / `node_item_id`（连锁网店）。价格字段同样是**分**（`data.item_price_param.price`、`data.sku_list[].price`）。`122001001` 商品不存在。

无凭证探测（2026-09-11，×2）：`/api/youzan.item.detail.get`（缺版本号）→ `gw_err_resp.err_code 4001 非法请求地址`；`Content-Type: text/plain` → `4007`。

## 6. 商品列表

### `youzan.item.base.search.1.0.0`（新模型）
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| kdt_id | Long | 是 | 店铺 id |
| channel | Integer | 是 | 0 网店、1 门店 |
| item_ids / group_ids / item_codes / sku_codes … | List | 否 | **所有 List 参数最多 20 个** |
| is_displays | List<Integer> | 否 | 0 仓库中、1 出售中和已售罄；不传查 0 和 1 |
| sold_status_list | List<Integer> | 否 | 配合 `is_displays=[1]` 使用（见文档枚举） |
| title | String | 否 | 标题 |
| publish_code | String | 否 | 按发布类型筛 |
| item_range_query.min_update_time / max_update_time | Long | 否 | 更新时间范围，**毫秒** |
| sorts | List<String> | 否 | `CREATED_TIME_DESC`（默认）、`UPDATE_TIME_ASC`… |
| page_no / page_size | Integer | 否 | `page_no × page_size ≤ 5000`；错误码说明写 pageSize 不能大于 50 |
| search_after | — | 否 | 游标方式，不限总数，需与 page_size、sorts 保持一致（字段细节 ⚠ 本 skill 未收录） |

响应 `data.paginator`（`page_no`、`page_size`、`total_count`）、`data.items[]`：`item_id`、`channel_item_id`、`title`、`alias`、`display`（0 下架、1 上架、8 不可售）、`sold_status`、`start_sold_time`（**秒**）、`item_code`、`delete`（0/1）…
错误：`200000026` 非法的 page 或 pageSize（翻页超过 5000 条或 pageSize > 50）、`18910002` 参数为空。

### `youzan.items.onsale.get.3.0.0`（老版，出售中；仓库中用 `youzan.items.inventory.get.3.0.0`）
| 参数 | 说明 |
|---|---|
| q | 名称 / 编码搜索 |
| tag_id | 商品分组 id |
| channel | -1 全部、0 网店（默认）、1 门店 |
| page_no | 1 ~ 100 |
| page_size | < 200，且 `page_no × page_size < 4000` |
| order_by | `created_time:desc`、`update_time:asc`、`price:desc`、`sold_num:desc` |
| update_time_start / update_time_end | **毫秒**时间戳 |

响应 `data.count`、`data.items[]`：`item_id`、`alias`、`title`、`price`（**分**）、`quantity`（总库存）、`created_time` / `update_time`（字符串）。建议单店 300 QPS。
增量同步商品：用 `update_time_start/end` 或 `item_range_query` 按窗口拉，配合商品消息。

## 7. 改价改库存

- **老接口 `youzan.item.sku.update.3.0.0`**（仅微商城、教育商品；不支持零售）：
  `item_id`（Long，必填）、`sku_id`（Long，必填）、`quantity`（**String**）、`price`（**Double，单位元**，精确两位）、`item_no`。
  → 同一平台上创建接口的价格是“分”，这个老接口是“元”。错误 `123005001` 商品不存在、`123004002` SKU 不存在、`123003023` 开启了库存同步修改不生效。建议单店 50 QPS。
- 新模型推荐 `youzan.item.price.update.1.0.0`、`youzan.item.quantity.update.4.0.0`（参数与单位 ⚠ 本 skill 未收录，调用前打开原文确认）。
- 批量改 SKU 价：`youzan.item.batch.update.sku.price.1.0.0`（建议 30 QPS，参数未收录）。

## 8. 删除商品

`POST /api/youzan.item.delete/3.0.1`，参数 `item_id`。**底层异步处理，返回成功不代表删除成功，需要二次反查**（例如轮询 itemdetail.get 直到 `122001001`）。建议单店 20 QPS。

## 9. 商品消息（详见 `messages.md`）

| 消息 | 触发 | 说明 |
|---|---|---|
| `ITEM_INFO` | 新增、编辑、分类编辑 | msg 含 itemId、alias、标题、价格等 |
| `ITEM_STATE` | 删除、上下架、售罄 / 恢复 | msg = `{"data": {...最新值}, "change_fields": [...]}`；`is_display` 0 下架 / 1 上架 / 8 不可售 |
| `ITEM_SKU_INFO` | 规格新增 / 编辑 / 删除 | 含 stock_num、price |
| `youzan_item_SkuStockChanged` | 规格库存变更 | **不含库存值**，要再调查询接口 |
| `youzan_item_skuStockOrSoldNumUpdated` | 库存或销量变更 | — |

文档提醒：库存等高频事件要**去重防抖**；部分消息只推关键字段，需要调 API 补全；连锁下总部与分店可能各推一条相同事件。

## 10. 单位与时间格式速查

| 接口 | 字段 | 单位 / 格式 |
|---|---|---|
| item.common.create | `skus.price`、`cost_price`、`postage`、`pre_sale_mark.deposit` | **分**（Long） |
| item.itemdetail.get / item.detail.get / items.onsale.get | `price` 类字段 | **分** |
| item.sku.update.3.0.0 | `price` | **元**（Double） |
| trade.get（订单） | `orders[].price` 等 | 元（String） |
| itemdetail.get，channel=1 | `stock_num` 等 | **× 1000**，用 `*_str` 字段 |
| item.common.create | `auto_display_on_time`、预售时间 | 毫秒 |
| item.base.search | `item_range_query.*` | 毫秒；响应 `start_sold_time` 是**秒** |
| items.onsale.get | `update_time_start/end` | 毫秒；响应时间是字符串 |

## 11. ⚠ 本文件的文档矛盾 / 未说明

- `origin`（划线价）单位 → ⚠ 文档未说明
- `specs` 与 `skus[].spec_values` 的对应校验规则 → ⚠ 文档未说明
- `item.price.update.1.0.0`、`item.quantity.update.4.0.0`、`batch.update.sku.price`、`search_after` 细节 → ⚠ 未收录
- `item.delete.3.0.1` 异步删除的生效延迟 → ⚠ 文档未说明
- 老接口 `item.sku.update` 价格是元、新接口是分 → 不是矛盾但极易写错，按接口区分
