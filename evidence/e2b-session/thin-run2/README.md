# thin-run2 — E2 thin(25-patch) RAM 链会话附件（task-67 rev4 / 2026-11-27）

本目录是 `evidence/e2b-session-20261127.md` 第 10 节的附件：thin 25-patch（defconfig diet）镜像的零写入 RAM 链复测。

- 会话时间：2026-11-27 19:58:52–20:02:16（run-2，GREEN）；失败的第 1 次尝试 19:54:40 仅由端口冲突导致，零写入。
- 产物：CI run 45988430055，`/home/qc233/zte/e2631-t5-artifacts/uboot-defconfig-45988430055/e2631-uboot-45988430055/`；banner `U-Boot 2027.01-rc2-ge6678e875e60`；u-boot.bin 320,848 B sha256 `33928958…` crc32 `0x92257c50`；25 patches；post-am tree `ac987015…`。
- 结果：F1 = KERNEL_STARTED（thin 镜像内核能起）；F2 = 物理线 0 帧（仍未闭环）；0x48000000 可见性异常复现；新增 thin 镜像 env `bad CRC` 回归候选（见文档 10.5）。
- 零写入：U-Boot 侧无 mtd write/erase/saveenv；唯一写入是 Linux 侧 userdata staging（erase+write+readback）；mtd0 `f9239040…` 与 image region `b1ea9a48…` 前后一致。

## 文件

| 文件 | 说明 |
| --- | --- |
| `session-results.json` | run-2 驱动结果（checks、staging、F1/F2、BMU 快照、postcheck） |
| `serial.txt` | run-2 原始串口字节（hub 记录；与 console-history 相同） |
| `driver.txt` / `driver-stdout.txt` | 驱动日志（stdout 与文件同内容） |
| `tcpdump.txt` | 主机侧 enp0s20u1u4u2c2 抓包（68 行；U-Boot MAC 0 帧、BOOTP 0 行） |
| `dnsmasq.txt` / `http.txt` / `testfile.json` | 主机 dnsmasq/TFTP 测试文件与 staging 服务日志 |
| `session-results-run1-failed-staging.json` / `driver-run1-failed-staging.txt` | 第 1 次尝试（18081 端口被 E4 mock-rescue 占用，wget 取到错误字节，零写入） |
| `staging-http-run1.txt` / `http-run1.txt` | 第 1 次尝试的 HTTP 服务日志 |
| `artifact-SHA256SUMS.txt` / `artifact-UBOOT-INFO.txt` | 构建产物清单、patch/tree/工具链事实 |
| `tool-e2t_session.py` | 本次会话驱动（preflight/session/anomaly/F1/F2/postcheck） |
| `SHA256SUMS.txt` / `.gitattributes` | 本目录校验清单；`*.txt` 标记 `-text` 保留 CRLF |

## 关键原始行（serial.txt 行号）

- 26：flash 15-patch U-Boot banner `g85df6772a444`；33：`Loading Environment from MTD... OK`。
- 44–50：`mtd read spi-nand0 0x47f00000 0x3f00000 0x80000` → `crc32 0x47f00000 0x4e550 = 0x92257c50` → `go 0x47f00000`。
- 52：thin banner `ge6678e875e60`；58：`*** Warning - bad CRC, using default environment`；62：random MAC `26:a1:2f:29:78:ac`。
- 72–90：0x48000000 异常复测（md 全 0、crc32 `758d6336`、iminfo Unknown）。
- 91–136：F2（mii info / e2631net 含 patch-0023 BMU 计数行 / dhcp 7×BOOTP 35.58 s）。
- 187–207：F1 判别（load CRCs good；md/crc32/iminfo 零视图）。
- 208–228：plain `e2631boot`（e2631soc、Starting kernel）；370：`Please press Enter`。