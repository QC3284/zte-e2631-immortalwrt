# task-61 / D-U4 真机自持刷写验收：无串口桥接刷入 patch-0014 并冷启动确认（2026-11-22）

> 设计见 [../evidence/uboot-du1-20261122.md](uboot-du1-20261122.md)；产物基线见 [../evidence/uboot-class1-fallback-20261122.md](uboot-class1-fallback-20261122.md) 与 [../evidence/uboot-ci-build-20261121.md](uboot-ci-build-20261121.md)；本目录附件见 [t61-uboot-flash/](t61-uboot-flash/)。

## 0. 结论：**GREEN**

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| Phase A：Linux 经 HTTP 取镜像 → userdata 暂存 → 回读 | **PASS**：wget 640 KiB 0.24 s；sha256 = b1ea9a48…；mtd erase userdata 0.66 s；mtd write … userdata 0.29 s；回读 sha256 = b1ea9a48… 0.15 s | §4；session-results.json |
| Phase B：旧 U-Boot 桥接（读 staging → CRC → 擦 → FF 哨兵 → 写 → 回读 CRC） | **PASS**：0x0721e716 → 0x804737c5（全 FF）→ 写 320 页 → 0x0721e716 | §5；serial-session-excerpt.txt |
| 写入审计 | **PASS**：U-Boot 侧恰好 1 次 erase + 1 次 write（只碰 0x20000..0xC0000）；Linux 侧恰好 1 erase + 1 write（仅 userdata）；loadx/xmodem 命令数 = 0 | §9；session-results.json audit |
| 单次用户断电后的冷启动 | **PASS**：新 banner U-Boot 2027.01-rc2-g85df6772a444 从 flash 起；env MTD OK；e2631boot 决策 slot1；内核/用户态起来 | §6；boot-segment-after-flash.txt |
| 刷后 mtd0 全片 sha256 | **PASS**：设备侧 f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4 == 写入前算出的期望值（逐字节证明） | §6/§7；Lead 只读 SSH 复核 |
| 硬件与系统 | **PASS**：PCIe 两条 Gen.1 x1 + 14c3:7906/790a；4 MDIO PHY；lan1/wan 1000 Mb/s Full；双频 AP E2631；MT7916 ready 63.285 s；panic/Oops/BUG = 0；fwstate BAR0/FW_STATE 正常 | §7 |
| 零串口文件传输 | **PASS**：本会话没有 loadx/xmodem 传文件；串口只做控制台 | §9 |

一句话：**无串口文件传输的桥接刷写首次真机验收通过**——640 KiB 镜像经以太网 HTTP 进 Linux 暂存区，旧 U-Boot 用已有的 mtd read/crc32/erase/write 把镜像桥接进 image 区，单次用户断电后新 U-Boot 从 flash 启动，mtd0 全片 sha256 与预计算值完全一致，硬件全绿。旧串口路径的 5.5 分钟级传输被 1.24 s + 约 3 s 取代。

## 1. 输入与产物

| 项 | 值 |
| --- | --- |
| U-Boot 产物 | CI run 44943940449（kit tip 0d53ccc；D-U1 patch 0014 命令：e2631flash / e2631verify / e2631slot） |
| u-boot.bin | 456,416 B，sha256 21b0d804483c7cbb82e2ca92968b6706ed0f740429e6e6c935bf34e16a881af8 |
| 新 banner token | U-Boot 2027.01-rc2-g85df6772a444 |
| 新 mtd0 镜像 | 655,360 B，sha256 b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a，CRC32 0x0721e716 |
| 镜像结构断言 | magic 128s、+0x14 长度字段 = 456,416、payload@0x800 == u-boot.bin、尾部全 FF（preflight） |
| post-am tree | 31843b38628ccf9c3e0b542ec4db014b6612755d（15 个 patch；patch 0014 为本次自持刷写命令） |
| 摄取通道 | 主机 HTTP http://192.168.5.92:18080/uboot-0014-mtd0.bin（设备 WAN 192.168.5.101 可达；设备侧 wget 实测 sha 一致） |
| 术前设备状态 | flash U-Boot = patch-0013 v3（banner g85c7367a3106）；mtd0 5ebb5ab3…；env 块 6e2c01da…；secondboot 540db435… |

## 2. 方案与断电预算

- 目标：把 patch-0014 镜像写进 flash，**全程零串口文件传输**，只用 **1 次用户断电**。
- Phase A（Linux 控制台）：HTTP 下载镜像到 /tmp（tmpfs）→ sha256 校验 → mtd erase userdata → mtd write image userdata → dd if=/dev/mtd10 … | sha256sum 回读（userdata 暂存区，label 形式，绝对偏移 0x3F00000、47 MiB，未挂载）。
- Phase B（旧 patch-0013 flash U-Boot 控制台）：mtd read 把 staging 读回 RAM → crc32 门禁 → mtd erase image 区（5 块）→ 读回 + crc32 全 FF 哨兵 → mtd write → 读回 + crc32 门禁；任何不一致立即停。
- Phase C（用户断电 1 次）：冷启动新 U-Boot → e2631boot → 内核 → 只读验收。
- 旧 U-Boot 的 mtd write 不会自动擦除（C1b-1 v1 事故根因），因此 Phase B 的手工阶梯把 erase → FF 校验 → write → readback 作为硬门禁；新 U-Boot 里同一阶梯由 e2631flash 内建（见 §10）。

## 3. 术前基线（preflight，全部只读）

| 项 | 设备侧实测 | 期望 | 判定 |
| --- | --- | --- | --- |
| /etc/e2631-version / kernel | ImmortalWrt v1.10.0 / 6.18.60 | 同 | PASS |
| 全片 mtd0 sha256 | 5ebb5ab3… | 与写入前基线一致（不假设） | PASS |
| secondboot 0x0..0x20000 sha256 | 540db435… | 与基线一致 | PASS |
| env+tail 0xC0000..0x100000 sha256 | e84546dd… | 与基线一致 | PASS |
| image 区 0x20000..0xC0000 sha256 | f6d179da… | = patch-0013 v3 镜像 | PASS |
| userdata 几何 | label=userdata，chip 0x3F00000，size 0x2F00000，未挂载 | 0x3F00000 / 0x2F00000 | PASS |
| 镜像下载 | wget 成功，sha256 b1ea9a48… | = 产物 sha | PASS |
| 预计算刷后 mtd0 sha256 | f9239040…（image 区外字节逐区 sha 复核后 + 新镜像） | 写入前报告给 Lead | PASS |

> 工具缺陷记录：第一次 preflight 用“按 /proc/mtd 顺序累加 offset”的错误假设，得到 userdata offset 0x54C0000（实际 DTS 里 rootfs/rootfs_data/slot1-header 嵌套在 slot1 span 内），preflight 正确返回 ok=False 并阻止了后续写操作。修正为“顶层分区 = mtd0..mtd4 → slot0 → slot1 → userdata”后重跑 ok=True。此缺陷只影响预检解析，不涉及任何写。

## 4. Phase A：Linux staging（无串口传输）

| 步骤 | 命令 | 结果 | 耗时 |
| --- | --- | --- | --- |
| 下载 | wget -O /tmp/e2631-new-mtd0.bin http://192.168.5.92:18080/uboot-0014-mtd0.bin | 640 KiB，Download completed (655360 bytes) | **0.24 s** |
| 校验 | sha256sum /tmp/e2631-new-mtd0.bin | b1ea9a48… = 产物 sha | **0.10 s** |
| 擦暂存区 | mtd erase userdata | 成功（stock mtd CLI 成功时无输出；由下一步回读证明） | **0.66 s** |
| 写暂存区 | mtd write /tmp/e2631-new-mtd0.bin userdata | 成功 | **0.29 s** |
| 回读 | dd if=/dev/mtd10 bs=4096 count=160 \| sha256sum | b1ea9a48… | **0.15 s** |
| 落盘 | sync; echo SYNCED | SYNCED | **0.06 s** |

Phase A 命令总耗时 **1.24 s**（设备串口控制台实测，驱动侧墙钟）。写入仅限 userdata 暂存分区；其它分区 0 写。

## 5. Phase B：旧 U-Boot 桥接（串口仅控制台）

原文摘录（serial-session-excerpt.txt）：

    => mtd read spi-nand0 0x44000000 0x3f00000 0xa0000
    Reading 655360 byte(s) (320 page(s)) at offset 0x03f00000
    => crc32 0x44000000 0xa0000
    CRC32 for 44000000 ... 4409ffff ==> 0721e716
    => mtd erase spi-nand0 0x20000 0xa0000
    Erasing 0x00020000 ... 0x000bffff (5 eraseblock(s))
    => mtd read spi-nand0 0x45000000 0x20000 0xa0000
    Reading 655360 byte(s) (320 page(s)) at offset 0x00020000
    => crc32 0x45000000 0xa0000
    CRC32 for 45000000 ... 4509ffff ==> 804737c5
    => mtd write spi-nand0 0x44000000 0x20000 0xa0000
    Writing 655360 byte(s) (320 page(s)) at offset 0x00020000
    => mtd read spi-nand0 0x45000000 0x20000 0xa0000
    Reading 655360 byte(s) (320 page(s)) at offset 0x00020000
    => crc32 0x45000000 0xa0000
    CRC32 for 45000000 ... 4509ffff ==> 0721e716

CRC 链：staging 0x0721e716 → 擦后全 FF 哨兵 0x804737c5 → 写入 → 回读 0x0721e716（三个门禁全 PASS）。

时间线（driver-console.txt）：04:16:32 发送 reboot -f → 04:16:33 捕获旧 flash banner 并停 autoboot → 04:16:36 U-Boot 控制台就绪 → 04:16:39 写后回读 CRC 通过。**从 reboot 到写校验完成 7 s**（其中 04:16:36–04:16:39 的 6 条 U-Boot 命令约 3 s；mtd read 640 KiB 在 NAND 上 <1 s）。

## 6. 单次用户断电后的冷启动（Phase C）

用户断电 1 次（提前告知）后，恢复中的串口捕获链记录完整启动段（boot-segment-after-flash.txt）：

    Boot SPI NAND -> start read bootheader -> start read secondboot -> non secure boot -> Jump
    enter bootloader... -> crpm init -> ddr init 1333 Mbps -> serial init -> backup header!!
    U-Boot 2027.01-rc2-g85df6772a444 (Nov 21 2026 - 20:01:16 +0000)
    Loading Environment from MTD... OK
    e2631boot: slot0 at 0x00700000: serial 7, version "V1.0.0.7B5.8000", header 0x01c60000
    e2631boot: slot1 at 0x02300000: serial 12, version "ImmortalWrt v1.10.0", header 0x03800000
    e2631boot: cspboot would boot slot1
    e2631boot: uImage "ARM ImmortalWrt Linux-6.18.60": load 0x40008000 entry 0x40008000, 3491146 bytes at 0x42000000
    e2631boot: header and data CRCs are good
    Starting kernel ...
    [0.589351] zx279128s-pcie f000000.pcie: PCIe Gen.1 x1 link up
    [0.591099] pci 0000:01:00.0: [14c3:7906] ... PCIe Endpoint
    [0.699366] zx279128s-pcie f100000.pcie: PCIe Gen.1 x1 link up
    [0.701084] pci 0001:01:00.0: [14c3:790a] ... PCIe Endpoint
    [0.885003] VFS: Mounted root (squashfs filesystem) readonly on device 31:7.
    [63.285269] e2631-wifi-boot: MT7916 ready
    [63.543446] e2631-wifi-boot: automatic Wi-Fi initialization complete

**mtd0 全片 sha256（设备侧，只读 SSH）= f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4，与写入前的预计算值逐字节一致**——Phase A+B 的写入在芯片上被证明精确。

## 7. 刷后硬件与系统验收（只读）

主机直连设备 LAN（NIC enp0s20u1u4u2c2 @192.168.1.191，设备 LAN MAC e0:b6:68:ac:f3:d8）后只读 SSH 复核：

| 项 | 实测 |
| --- | --- |
| 系统 | ImmortalWrt SNAPSHOT r0-86cddb7，target zx279128/generic；/etc/e2631-version = ImmortalWrt v1.10.0 |
| fwslot | running slot 1，slot1 serial=12 [running] [next boot]；slot0 serial=7 完好 |
| PCIe | /sys/bus/pci/devices = 0000:00:00.0、0000:01:00.0、0001:00:00.0、0001:01:00.0 |
| 以太网 | lan1 up + ethtool 1000 Mb/s Full；wan up + 1000 Mb/s Full；lan2/lan3 down |
| Wi-Fi | iw dev：phy1-ap0、phy0-ap0，SSID E2631；MT7916 ready @63.285 s |
| 内核异常 | dmesg panic/Oops/BUG 计数 = 0 |
| fwstate | e2631-fwstate BAR0=0x1030000c remap=0x103fe26c FW_STATE=0 |
| 负载 | uptime 约 2 min，load 0.54 |

## 8. 计时对比（无串口 vs 旧串口路径）

| 阶段 | 旧路径（Session B 实测，2026-11-22） | 本次无串口路径 |
| --- | --- | --- |
| u-boot.bin 传输 | loadx 456 KB 级 **42.0 s** | 无需（镜像经 HTTP 直取） |
| mtd0 镜像传输 | loadx 655,360 B **60.1 s** | wget 640 KiB **0.24 s** |
| 640 KiB 校验 | md.b **4m36s**（FF gate 4m36s、readback 4m38s） | staging+回读 CRC **<1 s**；U-Boot 侧 crc32 秒级 |
| 合计（镜像上传+校验） | **>5.5 min** | **1.24 s（Linux）+ 约 3 s（U-Boot 命令）** |

串口数据量：旧路径约 **1.2 MB** 文件传输；新路径 **0 字节**文件传输（串口仅控制台）。

## 9. 写入与命令审计

- U-Boot 侧命令（session-results.json audit）：mtd erase 恰 1 条 = mtd erase spi-nand0 0x20000 0xa0000；mtd write 恰 1 条 = mtd write spi-nand0 0x44000000 0x20000 0xa0000；loadx/xmodem 计数 = 0。
- Linux 侧写命令：mtd erase userdata 1 条、mtd write … userdata 1 条；其它分区 0 写。
- 未触碰：env 区 0xC0000..0xE0000（staging 数据在 0x3F00000 的 userdata 区；image 写入 0x20000..0xC0000 不重叠）；secondboot 0x0..0x20000 未写（术前 region sha 与基线一致，术后冷启动 secondboot→U-Boot 链路正常）。
- 断电次数：**1 次**（用户执行，提前告知）；进入 U-Boot 用 reboot -f，无额外断电。

## 10. 诚实说明：-74/EIO 风险与本会话的关系

- C1b-1 v1 事故根因：U-Boot 的 mtd write（旧 patch-0013）**不自动擦除**，直接写非空页会产生不可纠错位，随后的 mtd read 报 -74（EIO），并且驱动曾在读到旧 RAM 时误判“回滚成功”。修复路径是显式 erase → 全 FF 校验 → write → readback 的阶梯，该阶梯此后真机验证过（C1b-1 恢复会话 + v2 写入）。
- **本会话（旧 U-Boot 没有 e2631flash）正是用这套手工阶梯完成桥接**：erase → 读回 + CRC32 全 FF 哨兵 → write → 读回 + CRC32。因此这次写入不依赖任何“mtd write 会自动擦除”的假设。
- **刷入的新镜像（patch-0014，15 patch）已经内建同一阶梯**：e2631flash 先打印 DO NOT POWER OFF 横幅，再按块 erase → 校验全 FF → write → readback CRC32；同时新 defconfig 关闭 CONFIG_CMD_MTD_WRITE，即 e2631flash 是 flash 上唯一的写者。也就是说：**本次验收之后，无串口自更新在结构上避免了 -74/EIO 类风险**；本会话的手工阶梯是最后一次需要手工拼装的写路径。
- 尚未安装：16-patch 镜像（patch 0016 cross-slot fallback，mtd0 sha 869866d4…）不在本次范围，留给后续维护窗口。

## 11. 后续（不在本任务）

- 新 U-Boot 在 flash 后，验收 e2631verify / e2631flash / e2631slot 的“从 staging 直接刷”路径（下一次更新窗口，无需串口、无需 Linux mtd CLI）。
- 16-patch 镜像的类 1/类 2 回退在后续维护窗口安装与验收。

## 12. 附件清单（t61-uboot-flash/）

| 文件 | 内容 |
| --- | --- |
| tool-c1b3_noserial.py | 会话驱动（Phase A Linux staging + Phase B U-Boot 桥接；命令白名单与 CRC 门禁） |
| preflight.json | 术前只读基线（设备事实/几何/region sha/下载校验/期望 sha） |
| host-facts.json | 主机侧产物校验与期望 mtd0 sha 计算 |
| session-results.json | 会话结果（含逐命令耗时、CRC 门禁、审计） |
| driver-console.txt | 驱动日志（时间线 + 每条命令耗时） |
| serial-session-excerpt.txt | Phase A/B 串口控制台原文 |
| boot-segment-after-flash.txt | 断电后冷启动串口段（新 banner→内核→Wi-Fi） |
| SHA256SUMS.txt | 本目录文件校验和 |
