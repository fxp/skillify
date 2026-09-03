# 账户与存储

来源：`www.autodl.com/docs/common_api/`

## 获取账户余额

**Endpoint**: `POST /api/v1/dev/wallet/balance`

**用途**: 查询当前账户余额、累计消费、代金券余额。

**关键参数**：无请求参数。

**示例请求**：

```python
import requests
resp = requests.post(
    "https://api.autodl.com/api/v1/dev/wallet/balance",
    headers={"Authorization": "your_token"},
)
print(resp.json())
```

**示例响应**（已用真实 API 调用验证，2026-09；文档原文只列了 3 个字段，真实响应字段多得多，补充如下）：

```json
{
    "code": "Success",
    "msg": "",
    "data": {
        "id": 282382,
        "uid": 282383,
        "assets": 29290,
        "blocked_asset": 0,
        "accumulate": 120710,
        "voucher_balance": 0,
        "available_coupon_num": 0,
        "to_expire_voucher_num": 0,
        "certain_conditions_voucher_balance": 0,
        "remittance_code": "ADL00282383",
        "total_recharge_asset": 150000,
        "exclusive_transfer_account": "",
        "created_at": "2023-12-11T15:05:33+08:00",
        "updated_at": "2026-09-03T17:00:18+08:00"
    }
}
```

**注意事项**：

- `assets`（当前余额）、`accumulate`（累计消费）、`voucher_balance`（代金券余额）、`blocked_asset`（冻结金额）、`total_recharge_asset`（累计充值）都是**整数，除以 1000 才是"元"**——已用真实调用验证：真实余额 29.29 元对应的 `assets` 是 `29290`，不要直接把返回的整数当成"元"展示给用户。
- **可用余额建议算 `(assets - blocked_asset) / 1000`**，而不是只看 `assets`——`blocked_asset`（冻结中的金额）文档完全没提，但真实响应里确实有这个字段，冻结金额是不能直接花的。
- `remittance_code` 是账户的对公汇款识别码，`created_at`/`updated_at` 是账户创建/本次查询更新时间，这几个字段文档也没提，但一次真实调用就看到了，写强类型解析代码时不要假设响应只有文档列出的那 3 个字段。

---

## 切换专用 NFS / 文件存储

**Endpoint**: `POST /api/v1/dev/exclusive_nfs/mount`

**用途**: 在"专用 NFS"和"普通文件存储"之间切换。

**关键参数**

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data_center | string | 是 | 地区代码，见 `references/elastic-deployment.md` 附录里的地区对照表 |
| mountable | int | 是 | `1` = 挂载专用 NFS（关闭普通文件存储）；`-1` = 关闭专用 NFS（切回普通文件存储） |

**示例请求**：

```python
import requests
resp = requests.post(
    "https://api.autodl.com/api/v1/dev/exclusive_nfs/mount",
    headers={"Authorization": "your_token"},
    json={"data_center": "westDC2", "mountable": 1},
)
print(resp.json())
```

**示例响应**：

```json
{"code": "Success", "msg": ""}
```

**注意事项**：`mountable` 只接受 `1` 或 `-1`，不是布尔值 `true`/`false`。
