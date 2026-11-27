# F2 TX 探针会话附件（2026-11-27）

对应文档：../f2-probe-20261127.md

会话：2026-11-27 23:18:42–23:20:56，第 31 补丁构建（banner U-Boot 2027.01-rc2-ge84e13107885）。
结论：F2_PROBE_NO_MOVE（四种发送模式和 sbrg allow 重跑均无 MAC TX 帧、无网线帧）。
零 flash 写入；唯一写入为 Linux 侧 userdata staging。

| 文件 | 内容 |
| --- | --- |
| serial.txt | 会话原始串口字节（23,896 B） |
| serial-probe-segment.txt | 探针段选录（serial.txt 第 110-215 行） |
| session-results.json | 驱动结构化结果（43,541 B），probe 字段含全部原始命令输出 |
| driver.txt | 驱动日志 |
| console-history.txt | 控制台历史 |
| tcpdump.txt | 主机侧 enp0s20u1u4u2c2 抓包（23 帧全为主机生成） |
| http.txt / dnsmasq.txt / testfile.json | 主机服务记录（本会话未用于 F2） |
| tool-e2631_f2_probe_session.py | 本次会话驱动 |
| artifact-SHA256SUMS.txt / artifact-UBOOT-INFO.txt | 产物归档校验与构建信息 |
| SHA256SUMS.txt | 本目录 12 项校验清单 |
| .gitattributes | *.txt -text（保留串口原始 CRLF） |

关键原文位置：

- serial.txt 第 118 行：e2631net sbrg 仅输出 VLAN1 三个 word（全 0）。
- serial.txt 第 132-204 行：模式扫描与 sbrg allow。
- serial.txt 第 196-197 行：egress before/after 均为 0:0xfe 1:0xfd 2:0xfb 3:0xf7 4:0xef。
- serial.txt 第 203 行：第二次 TX completion timed out。
- session-results.json 的 probe.segments / probe.final_state / probe.wire_totals / probe.verdict。

复现校验：cd evidence/f2-probe && sha256sum -c SHA256SUMS.txt