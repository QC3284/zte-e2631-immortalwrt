# RUN5 证据包（R-验4）

本目录是 evidence/r-verify4-parity-20261115.md 的机器可读配套证据。

- verify-task26.sh：一键复算脚本（下载 -> SHA256SUMS -> SOURCE-INFO -> verify_img ->
  apk DB -> 两条 compare-parity -> kernel-deep -> merge-class 归因 -> APK 公钥）。
  用法：bash verify-task26.sh 44766496013 --kernel-merge-class
- t26-policy-merge.json / t26-policy-baseline.json：两条对比的评审策略（逐条带理由）。
- baseline-vs-RUN5-reviewed.md/.json：基线 43572710065 到 RUN5 44766496013。
- RUN3-vs-RUN5-reviewed.md/.json：RUN3 43623162108 到 RUN5。
- kernel-deep-44766496013.md/.json：解压内核逐字节分类（NON-STAMP-DIFF，2,371,928 B）。
- kernel-merge-class-44766496013.json：内核 merge-class 归因（66 个内核输入文件 = 13 个
  target/linux/generic 补丁 + 53 个 package/kernel 文件；config/版本/seed 不变）。
- run5-verify.log：完整运行日志（VERIFY_EXIT=0，PASS-REVIEWED-DIFFS x2）。

RUN5 结论：GREEN。bin 22,020,628 B，sha256 3a5914edac7dd973c4a86c2c97de5854ed348466701204d5d0903b1972439050。
