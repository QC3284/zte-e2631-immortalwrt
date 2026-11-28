# task-79 final-0034 证据包（2026-11-28）

本目录是一次真实设备会话的附件，对应 `evidence/e4-rescue-write-acceptance-20261128.md` §12。

- `session-results-original.json`：驱动原始输出，`verdict=FAIL`，原因是两个 harness 记账缺陷（`env_sanity` 未收到 boot_text；postcheck 在 MT7916 ready 之前只读一次）。未改动。
- `corrected-classification.json`：离线复核。原始 25 项检查里 23 项为 true；仅 `env_sanity`/`mt7916` 两项为 harness 缺陷。按串口 boot text 与后续 live postcheck 修正后 `verdict=GREEN`。没有重跑设备、没有伪造数据。
- `driver.txt` / `driver-stdout.txt`：驱动日志与 stdout（含 run-1 重建 bug、run-2 完整流程）。
- `serial.txt` / `console-history.txt` / `serial-excerpts.txt`：原始串口字节与关键段（写入 PASS、reset、flash 0034 启动、flash 提示符下的 resident rescue、e2631boot）。
- `write-post.body`、`status/status-00N.body`：POST /flash?mode=write 与 `/status` 状态机响应。
- `resident/`：从 flash 提示符启动 e2631rescue 后的 `GET /`、`/status`、validate 响应。
- `live-postcheck.txt`：会话结束后只读 SSH 采集（mtd0 ac06d7bc…、region 23395533…、env/secondboot/tail 不变、PANICS=0、MT7916=1）。
- `tool-e4_final_0034.py`：本次驱动（已含两处 harness 修复）。
- `artifact-SHA256SUMS.txt` / `artifact-UBOOT-INFO.txt`：CI 产物自带的校验与元数据。
- `SHA256SUMS.txt`：本目录清单（`sha256sum -c` 可验）。
