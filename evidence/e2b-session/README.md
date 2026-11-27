# task-67 E2-B 会话附件索引

- 任务：task-67 rev3（E2 零写入设备会话：以太网 + bootm 复核）
- 正文：`../e2b-session-20261127.md`
- 会话：2026-11-27 18:45:21–18:58:24 CST；补充只读探针 19:03–19:25（f1diag + ramtest 1–5）
- 产物：uboot-build run 44991704112，banner `U-Boot 2027.01-rc2-gf355ce89283c`，u-boot.bin sha256 `3cf000291b1b2d7552b4e7859204a310640dba81fbba5e60b36f99d7b89f355d`（22 patches，tree `c812dd8689ccf146deeec83bd0e74067c8b8abc5`）
- 结论：RED —— F2 42 次 BOOTP broadcast 期间物理线 0 帧（决定性）；F1 签名 = `Wrong Image Type`（镜像对 bootm 不可见），与 2026-11-22 的静默返回不同；另记录 md vs crc32 可见性观察（待复现）
- 零写入：U-Boot 侧 51 条命令无写；唯一写入为 Linux 侧 userdata（mtd10）1 擦 + 1 写 + 读回

| 文件 | 说明 |
| --- | --- |
| `session-results.json` | 会话结果：51 条 U-Boot 命令、BMU 快照、F2/F1 输出、审计、捕获链前后状态 |
| `driver-run1.txt` | 驱动时间线（staging → 暂停捕获 → reboot → F2 → F1 → 恢复） |
| `serial-run1.txt` | 会话窗口串口原始字节（CRLF 保留） |
| `tcpdump.txt` | 主机 `tcpdump -e -n -vv` 原始输出（66 帧；U-Boot MAC 0 帧、BOOTP/DHCP 0 行） |
| `dnsmasq.txt` / `http.txt` / `testfile.json` | 主机 DHCP/TFTP、HTTP staging 与测试文件参数 |
| `tool-e2b_session.py` | 会话驱动源码 |
| `tool-f1diag.py` / `f1diag-result.json` / `serial-f1diag.txt` / `tool-f1diag-run.txt` | f1diag 只读诊断（mtd read 2 页到 0x43000000 + md/crc32） |
| `tool-ramtest.py` / `ramtest-result.json` / `serial-ramtest.txt` | 0x46000000 RAM 检查 + flash→RAM 读可见性 |
| `tool-ramtest{2,3,4,5}.py` / `ramtest{2,3,4,5}-result.json` / `serial-ramtest{2,3,4,5}.txt` | 可见性观察定位探针（原始串口字节 + 结果 JSON） |
| `artifact-SHA256SUMS.txt` / `artifact-UBOOT-INFO.txt` | 产物构建清单（sha256、22 patches、tree、工具链、Hardware tested NO） |
| `SHA256SUMS.txt` | 本目录校验清单 |

复现入口：正文 §8.1（thin 镜像会话）与 §8.2（可见性观察复现步骤）。所有串口输出均另存原始字节，`cat -v` 可核对 `^M` 行尾。
