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

**示例响应**：

```json
{
    "code": "Success",
    "msg": "",
    "data": {
        "assets": 1000,
        "accumulate": 1000,
        "voucher_balance": 1000
    }
}
```

**注意事项**：`assets`（当前余额）、`accumulate`（累计消费）、`voucher_balance`（代金券余额）三个数值都是**整数，除以 1000 才是"元"**——比如 `assets: 1000` 代表余额 1 元，不要直接把返回的整数当成"元"展示给用户。

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
