# task-79 真冷启动证据包（2026-11-28）

本目录是一次真实物理断电/上电冷启动的附件，对应 `evidence/e4-rescue-write-acceptance-20261128.md` §13。

- `watcher-original-results.json`：冷启动 watcher 的原始输出，`verdict=FAIL`。原因是 watcher 的退出条件 `deadline-1700` 在启动 100 s 后已过期，kernel 标记后约 1 s 就退出，没等到 Linux console/Wi-Fi 行。它是 harness 计时缺陷，不是启动失败。文件未改动。
- `corrected-classification.json`：用完整串口段（21,101 B）复读的离线复核；BootROM/secondboot/banner/env/e2631boot/kernel/init/console/WiFi/MT7916 标记全部在，读后 health 全部通过，`verdict=GREEN`。
- `serial-segment-full.txt`：从冷启动前 offset 到会话结束的完整串口段（去 CR）。
- `watcher-original-segment.txt`：watcher 原始提前退出时保存的 2,009 B 段（保留证据）。
- `health.txt`：只读 SSH postcheck（mtd0 ac06d7bc…、region 23395533…、env/secondboot/tail 不变、PANICS=0、MT7916=1）。
- `capture.txt` / `capture-stdout.txt`：watcher 日志与 stdout。
- `tool-coldboot_capture.py`：修复后的 watcher（linux 标记优先，kernel 后最多再等 90 s）。
- `SHA256SUMS.txt`：本目录清单。
