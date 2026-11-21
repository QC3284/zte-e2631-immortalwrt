# A1/A2 banner 验收设备会话（task-49 + task-50 设备验证）

状态：**完成（A1 GREEN；A2 追加段 GREEN）** —— 设备侧九条判据全部通过；会话脚本的 verdict 字段因**主机侧路由陷阱**记 FAIL，已复核为环境问题（§12），不影响设备结论。
日期：2026-11-21
任务：task-49（A1 banner 验收设备会话，owner: verify-docs）；同一会话叠加 A2（SPI-NAND 只读路径）验证，约充 task-50 设备段。
前置：A1 ZTE UART 修复（task-47）与 A2 SPI-NAND 栈（task-50）均已入库并通过 CI；本会话只做真机 RAM 链验收。
用户操作：3 次断电/上电（A1 冷启动、A1→A2 阶段切换、恢复回 Linux），均由 Lead 转告并成功执行。

## 1. 目的与验收标准

把修复版 A1（以及可选 A2）u-boot.bin 经 vendor 控制台 xmodem 装载到 RAM，go 后看到主线条 banner、控制台可用；A2 额外验证只读 SPI-NAND 路径。随后恢复回 Linux，**全程零 flash 写入**。

### 1.1 A1 验收（task-49 硬标准）

| # | 标准 | 判据 | 结果 |
|---|------|------|------|
| 1 | xmodem 装载且逐字节一致 | xmodem EOT ack；crc32 一致（host 528a7131）；md.b 全文比对 0 差异 | **PASS**（EOT ack + md.b 347,824/347,824 B 0 差异；vendor 2013 控制台无 crc32，见 §5 说明） |
| 2 | serial banner 出现 | 出现 U-Boot 2027.01-rc2-g4910ee2045bd（短哈希 4910ee2045bd 为唯一硬 token，时间戳忽略） | **PASS**（banner 原文见 §6，serial.log:21773） |
| 3 | banner 后 prompt 存活 | help/version 可执行并回到 prompt；reset 回 Linux（或断电），设备健康（0 panic、MT7916 ready） | **PASS**（§7；reset 命令存在但本 SoC 实测 no-op，改用用户断电恢复，§8/§12 健康全绿） |
| 4 | 零 flash 写入 + 抓取链就位 | 仅发送 xmodem/md.b/crc32/go/help/version/echo/reset/mtd list/mtd read；会话前后 supervisor-002 + bootwatch-002 在位 | **PASS**（白名单拦截写入命令；会话后 mtd0 sha256 与 pre-session 基线完全一致，§12） |

### 1.2 A2 追加验收（只读 SPI-NAND）

| # | 标准 | 判据 | 结果 |
|---|------|------|------|
| 5 | A2 装载与完整性 | 同 A1：xmodem EOT ack；crc32 一致（host 5428b85b）；md.b 全文 0 差异 | **PASS**（EOT ack + md.b 444,152/444,152 B 0 差异；crc32 同 §5 原因跳过） |
| 6 | A2 banner | 出现 U-Boot 2027.01-rc2-g38bee433d177（短哈希 38bee433d177） | **PASS**（§10，serial.log:27797） |
| 7 | mtd 枚举 | mtd list 显示 spi-nand0、block size 0x20000 bytes、min I/O 0x800 bytes、OOB size 64 bytes（含 128 MiB 容量信息） | **PASS**（§11，五项断言全 true） |
| 8 | 只读读回校验 | mtd read（0x20000 头块、0xC0000 环境块各 0x2000 B）→ md.b 与 mtd0 dump 逐字节一致 | **PASS**（两次读回各 8,192 B，mismatches 0 / gaps 0，§11） |
| 9 | 零写入 | 只用 mtd list / mtd read；绝不发送 mtd write/erase、nand write/erase、saveenv（发送前有命令白名单断言） | **PASS**（白名单在发送前拒绝写入命令；mtd0 sha256 前后一致，§12） |

> crc32 项说明：vendor U-Boot 2013.04 控制台**没有** crc32 命令（发送后回 "Unknown command 'crc32' - try 'help'"），因此判据 1/5 的 crc32 字节校验以**md.b 全文逐字节比对**替代（更强）；镜像内 A1/A2 的 crc32 命令随后在 prompt 存活检查中以 0x100 范围验证可用（§7/§10）。

## 2. 输入与产物

### 2.1 A1（UART 修复）

| 项 | 值 |
|----|----|
| 产物 | /home/qc233/zte/e2631-t5-artifacts/uboot-a1-fix-44875722425/files/e2631-uboot-a1-44875722425/u-boot.bin |
| 大小 | 347,824 B（limit 0x9F800 = 653,312 B） |
| sha256 | 5310f998824a4c52dd46a18315ac0b989f2545f632477a5769ad5f2e5b4dc742 |
| banner token | U-Boot 2027.01-rc2-g4910ee2045bd（偏移 0x49D01） |
| host crc32 | 528a7131（设备侧未校验，见 §5） |
| U-Boot 基线 | c1958b5f6cce03956d309ce422b5d9f819955d4a（v2027.01-rc2），post-am tree 418ae89f09b34238daf37d0db78b4485001ffc2c |
| CI run | 44875722425 |

### 2.2 A2（SPI-NAND 只读路径）

| 项 | 值 |
|----|----|
| 产物 | /home/qc233/zte/e2631-t5-artifacts/uboot-a2-44877441503/e2631-uboot-44877441503/u-boot.bin |
| 大小 | 444,152 B（limit 0x9F800） |
| sha256 | a1df51f360eb70d9f4622f2f417a75726819c8661531ab24f62415a63ba2a626 |
| banner token | U-Boot 2027.01-rc2-g38bee433d177（偏移 0x5C16F；短哈希 38bee433d177） |
| host crc32 | 5428b85b（设备侧未校验，见 §9） |
| post-am tree | 4cfd4a4fd3db0dc34aa46155370562323f58e90d（与 uboot-port/commits.env 的 E2631_UBOOT_TREE_SHA 一致） |
| CI run | 44877441503（kit 提交 b218040） |

两份产物均在装载前由驱动重算 sha256/大小并校验 banner token 偏移（A2: token_offset=377,199，sha_ok/size_ok/token_ok 全 true）。

### 2.3 命令表（离核查 u-boot.map 的 U-Boot 命令表符号）

两份镜像均含：help、version、go、md、crc32、echo、reset；A2 另含 mtd。因此 §1.1 的 help/version 与阶段切换/恢复所需的 reset 命令在镜像内已存在（若 reset_cpu 在本 SoC 上无效，驱动会打印需要断电的提示并等待，作为回退——本次实测确实按回退路径走）。

### 2.4 A2 读回比对基准（mtd0 dump）

| 区域 | 偏移 | 长度 | dump 片段 sha256 |
|------|------|------|------------------|
| U-Boot 头块 | 0x20000 | 0x2000 | 1396981cf005b304d9d9477ff798e0745b0a474b386f43c292139a7a8cd8602a |
| U-Boot 环境块 | 0xC0000 | 0x2000 | 6b3309ad8e682eaea57f1d1327eb9ecfacb3a5747d6c91040f9f8b3856c5f459 |
| dump 全文件 | — | 1,048,576 B | de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f |

### 2.5 会话期间修复的驱动缺陷（记录以便复查）

前四次尝试（combined-1..3）的失败全部来自主机侧驱动，不是设备问题：

1. md.b 解析器贪婪正则把 ASCII 列一起吞掉，导致长度 >16 B 的行错位 → 假差异（combined-1/2）。改为：按行取地址后**只取前 16 个 token**，并允许最后一行 1..16 token 的短行；修复后 combined-4 全镜像 0 差异，且对 combined-1 原始串口 dump 离线复算同样 0 差异。
2. 控制台提示符检测用 b"=>" 任意位置匹配，会误命中 ASCII 列里的 0x3D 0x3E → 新增 md_read 等 b"\r\n=> " 真 prompt。
3. xmodem 握手竞态：旧流程先等设备发 C、再由 hub reset 输入缓冲等下一个 C，产生空窗，vendor receiver 超时并把后续数据当控制台输入回显（combined-3）。改为 hub 自己发 "xmodem <addr>\r" 后立即探 C/NAK。
4. hub 读线程与 xmodem_send 并发 read 同一 tty → SerialException "device reports readiness to read but returned no data (device disconnected or multiple access on port?)"（15:24 A2 装载即因此失败）。加 reader_idle Event，发送前等读线程让出串口。
5. 卡死的 vendor xmodem receiver 用 CAN CAN（0x18 0x18）+ Ctrl-C + CR 解除，已加入 attach 与 xmodem 重试循环（a2-only-3 会话即以此恢复）。
6. 新增 a2_only_accept.py（仅 A2 单阶段）与 a1a2_banner_accept.py 的 --start-mode cold|vendor-prompt|uboot-prompt、crc32 可选、阶段失败不中止。

## 3. 设备与抓取链基线（preflight，2026-11-21 14:58）

| 项 | 状态 |
|----|------|
| 设备 | ImmortalWrt v1.10.0（Linux，ping 192.168.1.1 通） |
| 抓取链 supervisor-002 | pid 56272 |
| 抓取链 bootwatch-002 | pid 56279 |
| tty 占用 | /dev/ttyCH343USB0 holder pid 56278（capture cat） |
| 最近 reader-start | 2026-11-21T14:39:08+08:00 |
| preflight 结果 | OK（artifacts/capture/scripts/dump 四项全过） |

会话期间 serial 必须单读：脚本先停抓取链、由 serialhub 接管；结束后 kill hub 并 restore_capture.sh 重启 supervisor-002 + bootwatch-002 并再验证 pid/事件。会话窗口内的 boot 只进 hub 原始日志 serial.log（单读限制）。

## 4. 会话流程与时间线

| 时间（CST） | 事件 |
|-------------|------|
| 15:04:23 | capture paused（supervisor 56272 / bootwatch 56279 / tty holder 56278 全部退出），hub pid 72726 就绪；驱动打印 READY，Lead 转告用户上电（第 1 次） |
| 15:05:07 | 冷启动捕获 "Press 1 means entering boot mode" → 发送 1 → vendor 密码通过 → stock U-Boot 2013.04 控制台就绪 |
| 15:05:43 | combined-1：A1 xmodem 完成（340 blocks / 347,824 B / 35.0 s / EOT ack）；crc32 不可用；md 解析器缺陷报假差异 → 未 go |
| 15:10:19 | combined-2：复现同一解析缺陷（原始串口 dump 离线复算 8 个 16 KiB 块全 0 差异） |
| 15:12:43 | combined-3：xmodem 握手竞态失败（33,792 B 后 vendor 把数据当控制台输入回显） |
| 15:15:40 | combined-4：attach 到既有 vendor 控制台（start-mode=vendor-prompt） |
| 15:16:16 | A1 xmodem 完成（crc32 判 unavailable，见 §5） |
| 15:16:23–15:18:47 | A1 md.b 全文比对 347,824/347,824 B，0 差异（22 块，每块 16,384 B，尾块 3,760 B） |
| 15:18:50 | go 0x43000000 → banner 4910ee2045bd；prompt 存活检查通过；A1 OK=True |
| 15:19:05 | A1 镜像内 reset 实测 no-op → 打印 POWER CYCLE REQUIRED (stage transition)，等待用户断电 |
| 15:24:00 | 用户上电（第 2 次）后冷启动、vendor 控制台就绪；A2 xmodem 立即失败（驱动并发读 tty 缺陷，§2.5 第 4 条） |
| 15:24:07 | capture 恢复（87112/87119）；该次会话 verdict FAIL（纯工具原因，设备未受影响） |
| 15:37:47 | a2-only-3 会话 attach（设备仍在 vendor prompt；先前卡死的 xmodem receiver 已用 CAN CAN 解除） |
| 15:38:29 | A2 xmodem 完成（434 blocks / 444,152 B / 41.5 s / EOT ack） |
| 15:38:37–15:41:47 | A2 md.b 全文比对 444,152/444,152 B，0 差异（28 块，尾块 1,784 B） |
| 15:41:50 | go 0x43000000 → banner 38bee433d177 |
| 15:41:51 | A2 prompt 存活（alive/reset/mtd 均 true） |
| 15:41:55–15:41:58 | mtd list 五项断言 + 两次只读 mtd read 全部 0 差异；STAGE OK=True MTD_OK=True |
| 15:42:13 | A2 镜像内 reset 同样 no-op → 打印 POWER CYCLE REQUIRED for recovery |
| 15:43:35 | 用户上电（第 3 次）后 Linux 回连成功（recovery linux.ok=true） |
| 15:43:42 | capture 链恢复（supervisor-002 96223 / bootwatch-002 96230 / tty holder 96229） |
| 15:44:14 | 会话 verdict FAIL —— 仅因主机侧 health 路由陷阱（§12） |
| 15:44–15:46 | 主机直连链路恢复；post-health 全绿；只读 SSH 复核 mtd0 sha256 与 pre-session 基线一致 |

用户共执行 3 次断电/上电：第 1 次 A1 冷启动（15:04 后），第 2 次阶段切换（15:19 后），第 3 次恢复（15:42 后）。

## 5. A1：xmodem 装载与逐字节比对

combined-4 驱动记录（combined-4/driver.console.log）：

- xmodem：`stage a1 xmodem: {"mode": "crc", "blocks": 340, "bytes_sent": 347824, "elapsed_s": 35.0, "eot_acked": true}`（CRC 模式，128 B 数据块）
- crc32：`{"available": false, "device_crc32": null, "host_crc32": "528a7131", "ok": false, "raw": "crc32 0x43000000 0x54EB0\r\nUnknown command 'crc32' - try 'help'\r\n=>"}`
- 采用全文 md.b 比对作为字节等价证据：`{"ok": true, "bytes_compared": 347824, "mismatches": 0, "first_mismatch_offset": null, "gaps": 0}`
- 比对窗口 15:16:23–15:18:47（约 2 分 24 秒），每块约 7.1 s，尾块 3,760 B / 1.6 s；0 重试触发（每块允许一次重试）

首轮（combined-1，15:05:43）装出的数据相同，但受 §2.5 第 1 条解析器缺陷影响误报 mismatch；对原始串口日志离线复算证明 8 个 16 KiB 块全部 0 差异。修复解析器后 combined-4 正式判定 0 差异，两者一致。

## 6. A1：go 与 banner 验收

15:18:50 发送 `go 0x43000000`，串口原文（combined-4/serial.log）：

- :21770 `## Starting application at 0x43000000 ...`
- :21773 / :21868 `U-Boot 2027.01-rc2-g4910ee2045bd (Nov 21 2026 - 06:30:06 +0000)`
- :21775 `Model: ZTE ZXHN E2631 (ZX279128S)`
- :21776 `DRAM:  256 MiB`

驱动判定：`stage a1 go: banner_token_seen=True prompt_seen=True banner_line='U-Boot 2027.01-rc2-g4910ee2045bd (Nov 21 2026 - 06:30:06 +0000)'`。短哈希 4910ee2045bd 命中，A1 banner 验收 **PASS**。

## 7. A1：banner 后 prompt 存活

驱动判定：`stage a1 prompt: alive=True reset=True mtd=False`（`stage a1 OK=True`）。

- echo 回显：:21872 `=> echo A1-PROMPT-ALIVE` / :21873 `A1-PROMPT-ALIVE`
- in-image crc32 可用：:21875 `CRC32 for 43000000 ... 430000ff ==> 660a59e8`
- help 输出含 reset 命令（`reset - Perform RESET of the CPU`），无 mtd 命令（与 §2.3 命令表一致）
- version 命令正常回显（驱动 ok）

结论：banner 后 prompt 存活、命令系统可用，标准 3 的 prompt 部分 **PASS**；reset 实际执行结果见 §8。

## 8. 阶段切换（A1 → vendor 控制台 → A2）

- A1 help 含 reset（prev_help_has_reset=true），但执行 reset 后设备**未复位**（reset_rebooted=false，reset_unknown=false）——本 SoC 的 reset_cpu 在 A1 镜像中为 no-op。
- 15:19:05 驱动按回退路径打印 `POWER CYCLE REQUIRED (stage transition): unplug >=5 s, replug; waiting 600s`；Lead 转告用户断电/重插，用户执行（第 2 次）。
- 15:24:00 冷启动 "Press 1" 捕获 → vendor 密码 → stock U-Boot 控制台就绪；`stage transition: {"method": "power-cycle", "prev_help_has_reset": true, "reset_rebooted": false, "reset_unknown": false, "ok": true}`。
- 随后 A2 xmodem 因驱动并发读 tty 立即失败（§2.5 第 4 条），该次会话 15:24:07 恢复抓取链后记 FAIL；设备无异常，仍停在 vendor 控制台等待。

## 9. A2：xmodem 装载与逐字节比对

a2-only-3 驱动记录：

- attach：`{"ok": true, "tail": "<INTERRUPT>\r\n=>"}`（15:37:47；此前卡死的 vendor xmodem receiver 已用 CAN CAN 解除）
- 产物校验：`sha_ok=True size_ok=True token_offset=377199`
- xmodem：`{"mode": "crc", "blocks": 434, "bytes_sent": 444152, "elapsed_s": 41.5, "eot_acked": true, "error": null}`
- crc32：`{"available": false, "device_crc32": null, "host_crc32": "5428b85b", "ok": false, "raw": "crc32 0x43000000 0x6C6F8\r\nUnknown command 'crc32' - try 'help'\r\n=>"}`（同 §5 原因，以全文 md.b 替代）
- md.b：`{"ok": true, "bytes_compared": 444152, "mismatches": 0, "first_mismatch_offset": null, "gaps": 0}`；窗口 15:38:37–15:41:47（约 3 分 10 秒），28 块，0 重试

## 10. A2：go、banner 与 prompt

15:41:50 发送 `go 0x43000000`，串口原文（a2-only-3/serial.log）：

- :27794 `## Starting application at 0x43000000 ...`
- :27797 / :27893 `U-Boot 2027.01-rc2-g38bee433d177 (Nov 21 2026 - 06:51:40 +0000)`
- :27799 `Model: ZTE ZXHN E2631 (ZX279128S)`
- :27900 `CRC32 for 43000000 ... 430000ff ==> 660a59e8`

驱动判定：banner_token_seen=True；`A2 prompt: alive=True reset=True mtd=True stage_ok=True`（15:41:51）。短哈希 38bee433d177 命中，A2 banner 验收 **PASS**。

## 11. A2：mtd list 与只读读回

mtd list（a2-only-3/serial.log:27952 起）关键行：

- `List of MTD devices:`
- ` - block size: 0x20000 bytes`（:27959）
- ` - min I/O: 0x800 bytes`（:27960）
- ` - OOB size: 64 bytes`（:27961）
- ` - OOB available: 62 bytes`（:27962）
- ` - ECC strength: 1 bits`（:27963）
- ` - ECC step size: 512 bytes`（:27964）
- ` - 0x000000000000-0x000008000000 : "spi-nand0"`（:27966，128 MiB 容量）

断言结果：`{"header": true, "spi_nand": true, "block_size": true, "min_io": true, "oob_size": true}`。

两次只读 mtd read（每次 0x2000 B = 4 pages）：

| 区域 | 命令 | 设备回显 | md.b 比对 |
|------|------|----------|-----------|
| U-Boot 头块 | `mtd read spi-nand0 0x4C000000 0x20000 0x2000` | :27968 `Reading 8192 byte(s) (4 page(s)) at offset 0x00020000` | offset 131072, size 8192, read_error false, mismatches 0, first_mismatch null, gaps 0, ok true（15:41:55） |
| U-Boot 环境块 | `mtd read spi-nand0 0x4C100000 0xC0000 0x2000` | :28483 `Reading 8192 byte(s) (4 page(s)) at offset 0x000c0000` | offset 786432, size 8192, read_error false, mismatches 0, first_mismatch null, gaps 0, ok true（15:41:58） |

两者对应 §2.4 的 dump 片段 sha256（1396981c… / 6b3309ad…），读回数据与 mtd0 现存内容逐字节一致。`A2 STAGE OK=True MTD_OK=True`（15:41:58）。

## 12. recovery 与设备健康

- A2 reset 同样 no-op → 15:42:13 `POWER CYCLE REQUIRED for recovery`；用户断电/上电（第 3 次）。
- 15:43:35 `recovery: {"method": "power-cycle", "reset_in_help": true, "reset_rebooted": false, "linux": {"ok": true, "marker": true}}`（Linux 回连成功）。
- 15:43:42 capture 链恢复：supervisor-002 pid 96223 / bootwatch-002 pid 96230 / tty holder 96229；events tail 见 a2-only-3-results.json。

### 12.1 会话 verdict FAIL 的唯一原因：主机侧路由陷阱

会话内 health 检查得到：`route: 192.168.1.1 via 192.168.5.1 dev enp4s0f2 src 192.168.5.92`，ping 通但 SSH 三次 `Connection refused`。原因：当时 Wi-Fi（wlp3s0）掉线，192.168.1.0/24 经用户家庭网网关 192.168.5.1 出去了——那是**另一台 ZTE 设备**（port 22 关闭），不是本机。设备本身已正常启动。

恢复后 post-health（a2-only-3-post-health.txt）：`route: 192.168.1.1 dev enp0s20u1u4u2c2 src 192.168.1.191`（USB 网卡直连设备 LAN），ping 3/3 0% loss，rtt ~1.99 ms；随后：

- VERSION=ImmortalWrt v1.10.0；UPTIME=118
- MTD0=`mtd0: 00100000 00020000 "bootloader"`
- PANICS=0；MT7916=1
- WIFIBOOT=`[ 54.861331] e2631-wifi-boot: automatic Wi-Fi initialization complete`

### 12.2 只读 SSH 复核（会话后，askpass 方式）

- VERSION=ImmortalWrt v1.10.0
- UNAME=Linux ImmortalWrt 6.18.60 #0 SMP Fri Nov 20 20:46:22 2026 armv7l GNU/Linux
- RELEASE=DISTRIB_REVISION='r0-86cddb7'
- DMESG_PANIC=0；MT7916=1；WIFIBOOT 54.861331
- mtd0 sha256 = de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f —— **与 pre-session 基线完全相同**；mtd0 1,048,576 B，OOB 64 B；uptime 167

### 12.3 恢复引导事件（bootwatch-002 session 6）

- userspace_init 2026-11-21T07:43:53Z
- wifi_wait 07:44:07（28.401700 s）
- mt7916_ready 07:44:33（54.703448 s）
- wifi_done 07:44:33（54.861331 s）

## 13. 结论

**GREEN —— A1 与 A2 全部九条判据通过，且已用 mtd0 sha256 前后一致实证零 flash 写入。**

| # | 判据对应 | 证据位置 |
|---|----------|----------|
| 1 | A1 xmodem EOT ack + 全文 md.b 0 差异（crc32 以 md.b 替代，镜像内 crc32 另证可用） | §5、§7、combined-4-driver.txt |
| 2 | A1 banner 4910ee2045bd | §6、a1-serial-excerpt.txt |
| 3 | A1 prompt 存活 + reset 命令存在（no-op → 断电恢复）；恢复后 0 panic、MT7916 ready | §7、§8、§12 |
| 4 | 零写入 + 抓取链在位 | §12.2、§4、a2-only-3-results.json |
| 5 | A2 xmodem EOT ack + 全文 md.b 0 差异 | §9 |
| 6 | A2 banner 38bee433d177 | §10 |
| 7 | mtd list 五项断言 | §11 |
| 8 | 两次只读读回 0 差异 | §11 |
| 9 | 只用 mtd list/read；白名单拒绝写入命令 | §2.5 末、§12.2 |

残余风险与后续项：

1. **reset_cpu 在本 SoC 上 no-op**（A1/A2 均实测）：阶段切换与恢复都靠用户断电。A3（task-51）如带 reset 实现，应在其独立设备会话中复测；在此之前任何 RAM 链会话都必须把「需要用户断电」计入流程。
2. vendor 控制台无 crc32，且本次未在镜像内对全镜像跑 crc32（只验证 0x100 范围可用）；全文 md.b 逐字节比对强度更高，已满足判据。
3. A2 只验证了**只读** mtd 路径（list/read + 与 dump 逐字节比对）。真正写 flash（nand write / mtd write / 刷 A1 到 boot 区）不在本会话，必须另行获批并配套救砖预案。
4. 主机排障规则：设备操作前必须确认 `ip route get 192.168.1.1` 走直连（wlp3s0 192.168.1.124 或 USB 网卡 192.168.1.191），否则会命中用户家庭网里的另一台 ZTE 设备。
5. 本次 A2 设备证据同时充 task-50 的设备段验收（SPI-NAND 只读路径 + mtd 命令 + 读回一致性）。

## 14. 附录

### 14.1 仓内证据（本目录）

| 文件 | sha256 |
|------|--------|
| combined-4-session-results.json | 5f535ca831c9aff94624dad80ac5959269854b9ab17c0647a3094aab510a0650 |
| combined-4-driver.txt | 5c63f315986ff7c8344757b2430d97915e49a816c9881b90e91fcb2b07248949 |
| combined-4-health.txt | 0e38714987ac0b5d4c7dcce94e58a21fe3cbc7e6c591ac4901d10b20990be9c3 |
| a2-only-3-results.json | 48def6ce07bc4df5f41768c491de106c7b73ae262fd0839b726d3a459ae2fdc1 |
| a2-only-3-driver.txt | 421452b4f3d82ecec200c7f84108861c71e57ccfbcd661f19582f9fd7a0b01c2 |
| a2-only-3-health.txt | c90c763058faa03c3f31b87a0aa21a3cd351dabbfc62ac489c1f720062a51d9a |
| a2-only-3-post-health.txt | 745071c91a34ef97945468cfc3621a587b97db7a88f58dfedb725ea5b35b2bf0 |
| a1-serial-excerpt.txt | 7e3f9e3e06bc1d7a29b459b05562ce075ba52bc7231070417a54b80270a9c7a6 |
| a2-serial-excerpt-part1.txt | 4433ae99d8a1fa59bbab59ce38878f32c109b308a4ee67635b41c191d14d8bc7 |
| a2-serial-excerpt-part2.txt | 3c962a523bd2b0ee4da7bed07cb60db55e57270d227d4c740dc2d3615e2242f0 |

驱动脚本（完整可复查）：tool-a1_banner_accept.py、tool-a1a2_banner_accept.py、tool-a2_only_accept.py、tool-serialhub.py、tool-ctl.py、tool-a1_banner_health.sh。

> 驱动日志用 .txt 命名以避开仓库的 `*.log` 忽略规则；内容与主机侧 .log 相同，sha256 不变。

### 14.2 主机侧原始日志（体积大，未入仓）

| 文件 | 大小 | sha256 |
|------|------|--------|
| /home/qc233/zte/e2631-p3/a1-banner-accept/combined-4/serial.log | 1,726,424 B | e93bd02cc4d17aba04fab7e6bfc44f10b9b45ebc677a4d10edf49744beb8a948 |
| /home/qc233/zte/e2631-p3/a1-banner-accept/a2-only-3/serial.log | 2,289,152 B | a796dfeafefd523c45bab493dcc941d60972de5ff021ec71be00f13128778fc0 |
| （a2-only-3 console-transcript.txt 与 serial.log 内容相同，同大小） | 2,289,152 B | 同上 |

### 14.3 抓取链状态（会话结束后）

- supervisor-002 pid 96223（raw log /home/qc233/zte/e2631-serial-boot-002.log）
- bootwatch-002 pid 96230（boot-sessions-002.jsonl、bootwatch-002.state.json）
- events：/home/qc233/zte/e2631-serial-capture-002-events.log（会话内 reader-end/reader-start 记录见 a2-only-3-results.json 的 capture_after 字段）
- 注意：旧路径 /home/qc233/zte/e2631-serial-boot.log 属旧链（11 月 15 日），勿引用。

### 14.4 零写入声明与命令白名单

- 会话发送的全部命令：xmodem、md.b、crc32、go、help、version、echo、reset、mtd list、mtd read；驱动在发送前用正则白名单拒绝 mtd write/erase、nand write/erase、saveenv 等。
- 唯一与 flash 相关的操作是 A2 的 mtd read（只读）；未执行任何 erase/write/upgrade/saveenv。
- 会话后设备 mtd0 sha256 与 pre-session dump 完全一致（§12.2），是零 flash 写入的直接证据。

### 14.5 复现要点

1. 预检：抓取链在位（supervisor-002 + bootwatch-002）、/dev/ttyCH343USB0 单读、直连路由确认。
2. 运行 `python3 a1a2_banner_accept.py --second-artifact <A2 bin> --second-token "U-Boot 2027.01-rc2-g38bee433d177"`（或 `python3 a2_only_accept.py` 单跑 A2）。
3. 驱动打印 READY FOR USER POWER CYCLE 时由 Lead 转告用户断电 >=5 s 后上电；阶段切换/恢复同样需要一次断电。
4. 结束自动恢复抓取链并跑 health；若 health 走错路由，先修主机直连再复跑（§12.1）。
