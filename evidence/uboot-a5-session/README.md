# A5 真机会话附件（2026-11-22 01:2x–01:5x）

配套正文：[../uboot-a5-device-session-20261122.md](../uboot-a5-device-session-20261122.md)。

| 文件 | 内容 |
| --- | --- |
| `tool-c1b1_a5_refclk.py` | 会话驱动（指纹门禁、pre/post md、loadx、e2631refclk、SerDes 读回、e2631boot、内核探针、verdict） |
| `tool-a5_pci_probe.py` | 只读 PCIe/Wi-Fi 诊断（/sys/bus/pci、rescan、wifi-on） |
| `preflight-run3.json` | run-3 前置事实（artifact/基线/设备/捕获链） |
| `run3-session-results.json` | run-3 全量结果（pre/post words、refclk 值、SerDes、探针、verdict） |
| `run1-driver-console.txt` / `run2-driver-console.txt` | 前两次中止的驱动控制台（TypeError / bytes token 缺陷） |
| `run2-loader-tail.txt` | run-2 hub 日志尾部：patch-0012 banner `g9a7538311376` 装入 RAM |
| `run3-prelude-refclk.txt` | run-3 串口选段：新 banner、e2631refclk before/after、prompt |
| `run3-kernel-evidence.txt` | run-3 内核侧证据：eth PHY/link、PCIe Device not found、Wi-Fi 重试 |
| `interim-capture-lines.txt` | 捕获链日志中厂商链启动那一段的选行（曾误标为 A5 自动启动；见正文 §4 更正：厂商 U-Boot 2013.04 链） |
| `residual-vs-vendor.txt` | 我方 post 状态 vs 厂商 post-init 的 10 个残余字 |
| `pci-probe.json` | 只读 PCIe/Wi-Fi 诊断结果（rescan 无效、wifi-on 空） |
| `zero-write-check.txt` | 会话后只读 SSH 的 mtd0 sha256 与健康数据（= pre-session 值） |
| `artifact-SHA256SUMS.txt` / `artifact-UBOOT-INFO.txt` | CI 产物自带的校验清单与构建信息 |
| `SHA256SUMS.txt` | 本目录附件校验和 |
