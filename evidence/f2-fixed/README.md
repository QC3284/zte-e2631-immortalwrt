# F2 修复验证会话附件（2026-11-28）

对应文档：../f2-fixed-20261128.md

会话：2026-11-28 00:13:13–00:15:20，patch 0032 构建（banner U-Boot 2027.01-rc2-gd38f69c44523）。
结论：F2_FIXED。第一次 e2631net tx 3（pp）即出现 MAC TX frames 端口 2 = 3 与 3 个 60 字节广播 ARP；最终 switch fwd ctrl 0x00000011、MAC TX frames 端口 2 = 12、全会话 12 个设备 ARP。
零写入：U-Boot 40 条命令 forbidden 为空，mtd0 f9239040… 与镜像区 b1ea9a48… 前后一致；唯一写入为 Linux 侧 userdata staging。

| 文件 | 内容 |
| --- | --- |
| serial.txt | 会话原始串口字节（25,481 B） |
| serial-probe-segment.txt | 探针段选录 |
| session-results.json | 驱动结构化结果（50,400 B），probe 字段含 bmu/逐模式/tcpdump 统计 |
| driver.txt | 驱动日志 |
| console-history.txt | 控制台历史 |
| tcpdump.txt | 主机侧 enp0s20u1u4u2c2 抓包（34 帧；12 个 60B 广播 ARP 来自 00:41:71:00:00:50） |
| http.txt / dnsmasq.txt / testfile.json | 主机服务记录（本会话未用于 F2） |
| tool-e2631_f2_probe2_session.py | 本次驱动 |
| artifact-SHA256SUMS.txt / artifact-UBOOT-INFO.txt | 产物归档校验与构建信息 |
| SHA256SUMS.txt | 本目录 12 项校验清单 |
| .gitattributes | *.txt -text（保留串口原始 CRLF） |

关键原文位置：

- serial.txt 第 115-123 行：首次 e2631net bmu（switch fwd ctrl 0x00000000，端口未 start）。
- serial.txt 第 125-126 行：sbrg 首读（learn/port ctrl/egress）。
- serial.txt 第 139 行：基线 MAC TX frames 全 0。
- serial.txt 中段：各模式 tx probe / sent / last descriptor / raw BUF_ID / MAC TX frames。
- 最终 bmu：switch fwd ctrl 0x00000011；最终 state：MAC TX frames 0:0 1:0 2:12 3:0 4:0、SW fwd 0x00000011。

复现校验：cd evidence/f2-fixed && sha256sum -c SHA256SUMS.txt