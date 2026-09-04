# Skill Benchmark: volcengine-ark

**Model**: Fable 5.1（执行与大部分评分）；评分中途因额度切换 Opus 5
**Date**: 2026-09-04T05:37:04Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8 (1 run each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 48% ± 32% | +0.52 |
| Time | 364.4s ± 155.1s (2,915s total) | 201.1s ± 68.3s (1,609s total) | +163.3s |
| Tokens | 139,575 avg/run (1,116,598 total) | 66,016 avg/run (528,126 total) | +2.1x |

> 注：Tokens 行由 `timing.json` 手工填入。`aggregate_benchmark.py` 的 token 统计读的是 `grading.json.execution_metrics`（本次评分未填该字段），其原始输出 `6944 ± 19640` 不可用。判词见各 `eval-*/verdict.md`，完整分析见 `../comparison-report.md`。
