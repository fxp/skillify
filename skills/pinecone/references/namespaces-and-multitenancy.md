# 命名空间与多租户

> 整理自 `guides/index-data/indexing-overview#namespaces`、`guides/manage-data/manage-namespaces`、`guides/index-data/design-for-multitenancy`、`guides/index-data/implement-multitenancy`、`guides/core-concepts/architecture`。抓取于 2026-09-21，**未经真实调用验证**。

## 目录

- [命名空间是什么、隔离语义](#命名空间是什么隔离语义)
- [命名空间怎么创建](#命名空间怎么创建)
- [列出 / 删除命名空间](#列出--删除命名空间)
- [多租户设计：namespace-per-tenant vs metadata 过滤](#多租户设计namespace-per-tenant-vs-metadata-过滤)
- [容易踩的坑：默认命名空间](#容易踩的坑默认命名空间)

## 命名空间是什么、隔离语义

一个索引内部按 namespace 分区，**每一次 upsert/query/fetch/delete/list 请求只作用于一个 namespace**（没有跨 namespace 联合查询的 API）。这个隔离是架构层面强制的（数据面按 namespace 组织存储的 "slab" 文件，见 `guides/core-concepts/architecture`），不是靠应用层过滤实现的软隔离——**查询不会意外"穿透"到其它 namespace**,这点是可以放心依赖的（不是本 skill 需要重点提醒 Agent 防范的方向,反而是下面这条更容易出错)。

命名空间的两个主要用途：

- **多租户隔离**：一个客户一个 namespace，天然数据隔离,删除某租户数据只需删除对应 namespace。
- **加速查询**：把数据按业务维度切分到多个 namespace,单次查询只扫描目标 namespace,比"单一大 namespace + metadata 过滤再筛选"更快也更省 RU（见 pricing-and-limits.md,RU 计费和 namespace 大小直接挂钩)。

命名空间**在 upsert 时自动隐式创建**,不存在时首次 upsert 会自动建出来,不需要提前调用创建接口。

## 命名空间怎么创建

需要预先声明可过滤字段（`filterable` schema）时才需要显式创建（这个能力需要 API 版本 `2025-10` 或更新）：

```python
namespace = index.create_namespace(
    name="example-namespace",
    schema={"fields": {
        "document_id": {"filterable": True},
        "document_title": {"filterable": True},
    }},
)
```

不显式声明 schema 时,所有 metadata 字段默认都建索引用于过滤（可能增加写入/存储开销）,只想索引部分字段时见 `guides/index-data/configure-metadata-indexing`（本 skill 未详细覆盖该页面，需要时单独查阅）。

## 列出 / 删除命名空间

```python
for namespace in index.list_namespaces():
    print(namespace.name, ":", namespace.record_count)
```

默认每页最多 100 个 namespace，有 `pagination_token` 时代表还有更多。响应里的 `size_bytes` 是**近似值**——文档原文特别提醒：值为 `0` 不代表 namespace 真的是空的（size tracking 上线前写入的数据、以及刚删除但还没被 compaction 清理掉的数据都可能读到 `0`）。

删除整个 namespace：`index.delete(namespace="...", delete_all=True)` 或专门的 namespace 删除接口（⚠ 具体端点未在抓取材料中完整确认，按 delete_all 方式转录）。每个 plan 的 namespace 数量上限不同（Starter 100 到 Enterprise 1,000,000），需要更高上限要联系 Support。

## 多租户设计：namespace-per-tenant vs metadata 过滤

官方给出两种模式（详见 `guides/index-data/design-for-multitenancy`，本 skill 只转录结论，未展开该页全部内容）：

| 模式 | 优点 | 缺点 |
|---|---|---|
| 一租户一 namespace | 隔离更彻底,查询更快更省 RU,删除租户数据是删 namespace 这一个操作 | namespace 数量受 plan 限制,租户数极多时可能撞上限 |
| 单 namespace + metadata 过滤 | 不受 namespace 数量上限约束 | 每次查询要扫描更大范围再过滤,RU 消耗和延迟都更高;删除租户数据要用 filter 批量删,不是原子操作 |

一般建议：租户数在 plan 的 namespace 上限内时优先用 namespace-per-tenant;租户数远超上限（如 to-C 场景每个终端用户一个"租户"）时才考虑 metadata 过滤或者租户分片到多个 namespace。

## 容易踩的坑：默认命名空间

不传 `namespace` 参数时,请求会落到一个默认命名空间——**但不同 API/SDK 版本里这个默认值具体是什么⚠未完全统一确认**：Vectors API 的旧版文档惯例是空字符串 `""`；Documents API 的官方示例代码（`bring-your-own-vectors` quickstart）里出现的是字面量字符串 `"__default__"`。这两者是否指向同一个底层命名空间、字符串形式是否等价，**本 skill 未实测确认**,是验证计划里的高优先级项。

实际后果：如果 upsert 时忘记传 `namespace`（落到默认命名空间）、查询时又显式传了某个具体的 namespace 名字（或反过来）,会查到 **0 条结果但不报任何错误**,很容易被误判成"索引本身是空的"或"embedding 没生效",而不是命名空间打错了。**强烈建议生产代码里永远显式传 `namespace` 参数,不依赖任何隐式默认值**,并在调试"查询查不到刚写入的数据"时,第一步就去确认两次调用的 namespace 字符串是否完全一致。
