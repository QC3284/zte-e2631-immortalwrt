# A6 真机会话附件（2026-11-22 02:2x–02:4x）

配套正文：[../uboot-a6-device-session-20261122.md](../uboot-a6-device-session-20261122.md)。

| 文件 | 内容 |
| --- | --- |
| `tool-c1b1_a6_pcie.py` | run-3 实际使用的驱动（含 pci_txt 提前引用 probes_late 的 KeyError 缺陷，见正文 §6） |
| `tool-c1b1_a6_pcie-fixed.py` | 同一驱动的修正版（pci 端点改为探针全部收集后重算；未在本轮真机运行） |
| `tool-a6_postcheck.py` | 主机侧独立判据脚本（从 serial/results/只读 SSH 输出重算产品级 verdict） |
| `preflight-run3.json` | run-3 前置事实（产物、捕获链、串口占用、vendor 密码权限） |
| `session-results.json` | run-3 驱动结果（artifact contract、refclk 值、GPIO 门禁、内核标记、早期探针） |
| `driver.stdout.txt` / `session-driver.txt` | run-3 驱动控制台与驱动日志 |
| `serial-a6-segment.txt` | run-3 串口选段（refclk before/after、GPIO 两字、e2631boot、bootm） |
| `boot-a6-tail.txt` | run-3 内核启动日志选段（e2631soc、PCIe、eth、Wi-Fi 重试） |
| `device-readonly.txt` | run-3 后只读 SSH 采集（uptime 251 s：PCIe 端点、四 PHY、1 Gbps、MT7916 ready、双频、mtd0） |
| `v2-run1-gate-excerpt.txt` / `v3-run2-gate-order-excerpt.txt` | 前两次中止的驱动输出（门禁读到的冷值，零写入） |
| `postcheck.json` | 独立判据结果（product_verdict=GREEN，21 项全过） |
| `artifact-SHA256SUMS.txt` / `artifact-UBOOT-INFO.txt` | CI 产物自带校验与构建信息 |
| `SHA256SUMS.txt` | 本目录附件校验和（不含本文件自身） |

