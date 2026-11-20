# task-38 验收附件索引

- 任务：C-验1 RUN6 parity 验收（verify-docs）
- 正文：`../c-plan-parity-20261121.md`
- RUN6 v3：run 44815428424（kit 38fce86c，树 fork 86cddb79）
- 终稿判定：PASS-REVIEWED-DIFFS（expected 23 / allowed 13 / unexpected 0），kernel-deep STAMP-ONLY

| 文件 | 说明 |
| --- | --- |
| `verify-task38.sh` | 端到端验收脚本（下载/sums/SOURCE-INFO/verify_img/apk DB/compare/kernel-deep/APK key） |
| `t38-policy-run5-to-run6.json` | 逐条理由的允许桶终稿（7 rootfsExact / 1 versionFiles / 1 infoKeys） |
| `t38-check-compare.mjs`、`t38-json-field.mjs` | 结论判定辅助 |
| `run6v3-verify.log` | 端到端验收日志，结束于 `[verify-task38] OK` |
| `compare-RUN5-vs-RUN6v3.md/.json` | 比较器完整报告 |
| `kernel-deep-RUN6v3.md/.json` | kernel 深比结果（STAMP-ONLY） |
| `verify-img-RUN6v3.log` | BOOT-READY 逐项 PASS |
| `SOURCE-INFO-RUN6-v3.txt` | 产物内 SOURCE-INFO 原文 |
| `selftest-run5-as-candidate.log` | 工具自测：RUN5 vs RUN5 = PASS-BYTE-IDENTICAL |
| `negctl/policy-pre-extension.json` | 补记前策略（负对照） |
| `negctl/pre-extension-report.md/.json` | 补前策略下的 FAIL 报告（unexpected = 5） |

