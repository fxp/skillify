# ark_afp_quota

查询火山方舟 **Agent Plan 个人版** 套餐在 5 小时 / 周 / 月三个窗口的剩余 AFP，剩余低于阈值（默认 10%）时打印告警并以退出码 1 结束，方便接入 cron / 监控。

仅依赖 Python 3.8+ 标准库。

```bash
export VOLC_ACCESSKEY=AKLT...
export VOLC_SECRETKEY=...
python ark_afp_quota.py                # 表格 + 告警
python ark_afp_quota.py --json         # JSON 输出
python ark_afp_quota.py --threshold 20 # 自定义阈值
python ark_afp_quota.py --dump-raw     # 打印原始响应（首次接入时用于核对字段）
python ark_afp_quota.py --mock-file sample_response.json   # 离线演示
python -m unittest test_ark_afp_quota -v                  # 单元测试
```

若官方 Action / 字段名与默认值不同，可通过 `ARK_QUOTA_ACTION`、`ARK_OPENAPI_VERSION`、`ARK_PLAN_TYPE` 等环境变量或对应命令行参数覆盖，详见 `NOTES.md`。

Cron 示例（每 30 分钟检查一次，告警时通过邮件发出）：

```cron
*/30 * * * * cd /opt/ark_afp_quota && ./ark_afp_quota.py >/tmp/afp.txt 2>&1 || mail -s "Ark AFP low" me@example.com </tmp/afp.txt
```
