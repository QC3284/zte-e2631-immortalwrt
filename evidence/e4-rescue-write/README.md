# E4 救援写模式验收附件（2026-11-28）

对应证据文档：../e4-rescue-write-acceptance-20261128.md

本次写入验收使用 E4 产物（34 patches 之前的 patch 0026-0033，banner g30dca5f54503，tree cd67a041…）：
STEP-1 净零写、STEP-2 E4 写均在同一 e2631rescue 会话内完成，/status done 后一次 Ctrl-C，
独立控制台回读通过，reset 回 flash E4 启动，postcheck mtd0 = d87db54a…。

冷启动救援失败（e2631rescue 首命令 PHY autoneg timeout）的原文在 serial.txt 末尾：
第 195-199 行；根因是 do_e2631rescue 只调用 eth_init()，缺 e2631_net_refclk_init()。
patch 0034 已由 base-builder 构建，待冷启动零写入验收。

文件：
- driver.txt / driver-stdout.txt：驱动日志
- serial.txt / console-history.txt：原始串口字节与控制台历史
- session-results.json：驱动真实输出（verdict=ERROR，error=resident rescue 阶段）
- step1/step2 的 page/post/status done 响应
- postcheck.txt：Linux postcheck 读数
- tool-e4_rescue_write.py：本次驱动
- artifact-SHA256SUMS.txt / artifact-UBOOT-INFO.txt
- SHA256SUMS.txt：本目录校验清单
