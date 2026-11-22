# Session B 真机写入验收：旧 U-Boot 桥接刷入 A6 v3 镜像（2026-11-22 03:00–03:24）

> 后续 T-61 无串口桥接验收见 [t61-uboot-flash-acceptance-20261122.md](t61-uboot-flash-acceptance-20261122.md)；本目录附件见 [t62-session-b-flash/](t62-session-b-flash/)。本记录独立成立：即使不读其它文档，也能还原当时做了什么、为什么、结果如何。

## 0. 结论：**B-WRITE-GREEN-HOLD**

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 写入通道 | 旧 flash U-Boot（g2797f3dd3860）→ 厂商 RAM 控制台 → 我们的 v3 U-Boot（g85c7367a3106）→ 手工 erase/FF/写/回读阶梯 | §3/§4 |
| env 块恢复 | PASS：erase 0xC0000/0x20000（1 块）→ 读回全 FF → 写 131,072 B → 读回 md == 6e2c01da… | §4.1 |
| image 区写入 | PASS：erase 0x20000/0xA0000（5 块）→ 读回全 FF → 写 320 页 655,360 B → 读回 md == f6d179da…（0 差异、0 gaps） | §4.2 |
| 写入审计 | PASS：恰好 2 次 erase + 2 次 write；forbidden 命令 0 条；无 saveenv / nand write / upgrade | §5 |
| 刷后 mtd0 重构值 | 5ebb5ab3…（= 干净基线 887a7f6c 的 image 区替换为 v3 镜像 f6d179da） | §6 |
| 结果确认 | 用户断电冷启动后设备侧 sha256sum /dev/mtd0 == 5ebb5ab3…；后续 T-61 Phase A 只读复核再次 == 5ebb5ab3… | §6 |
| 断电次数 | 本会话 **0 次**（用 SSH reboot -f 进入 flash 链）；写入验证后 HOLD，之后由用户断电一次作为冷启动确认 | §3/§7 |

## 1. 背景与范围

- A6 会话（patch 0013，v3 产物）已在 RAM 链证明 refclk/SerDes + GPIO pin2/pin51 释放后，以太网、PCIe 双端点与 MT7916 全部可用；但 flash 里仍是旧 patch-0011 U-Boot（g2797f3dd3860），它启动内核后网络/PCIe 起不来。
- 因此需要把 A6 v3 镜像（banner g85c7367a3106）真正写进 mtd0 的 0x20000..0xC0000，让 flash 链本身具备 A6 修复。
- 直接写 flash 有已知风险：旧 U-Boot 的 mtd write 不自动擦除（C1b-1 v1 事故：写非空页 → 读回 -74/EIO → 误用 stale RAM 判“回滚成功”）。本次按已验证的安全阶梯执行：先擦、读回全 FF 哨兵、再写、再读回逐窗比较。
- 本会话是“串口桥接”方案的最后一次执行；T-61 已改为 Linux HTTP staging + 新 U-Boot 内建 e2631flash，不再需要串口传文件。

## 2. 输入与产物

| 项 | 值 |
| --- | --- |
| v3 u-boot.bin | 450,936 B，sha256 3bf182f148226b6f64696a05bba5d75ca59426747f87eee3f13c5d2b0269423a，banner U-Boot 2027.01-rc2-g85c7367a3106（产物目录 uboot-a6v3-44935007253） |
| v3 mtd0 镜像 | 655,360 B，sha256 f6d179daa952db910afacde635f259fbe5f2eabf97f3d8aa07d2c09540979a42；结构断言全过（magic 128s、+0x14 长度字段 = 450,936、payload@0x800 == u-boot.bin、尾部全 FF） |
| 厂商 U-Boot RAM 镜像 | 426,048 B，sha256 a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30 |
| 干净基线 mtd0 | 1,048,576 B，sha256 887a7f6c9b407abc734eb9a76f08733a691441f91987369e8626deb8faf0fa9f（secondboot 540db435…；env 块 6e2c01da…；tail b5a41c37…；image 区为厂商区 3b49d4fb…） |
| B1 已验证 env 块 | 131,072 B，sha256 6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893 |
| 旧 patch-0011 镜像 | 655,360 B，sha256 baf28b6da4d6ca1b356389951b9d49765382b35dd382bc81c8a0a589c09464dd |
| 会话前设备 mtd0 | d571b764…（比 3c8a8c5b 多出 env 漂移：更早的厂商链会话里 cspstart 的 zteboot_update_bootpara 改写了 env 块） |
| 期望刷后 mtd0 | 5ebb5ab323bafea4a310e4cb3f78cbb77b3d219ba9fb324927bf28e8d0cc48cf |

## 3. 会话时间线（driver-console.txt 全程记录）

| 时刻 | 事件 | 耗时 |
| --- | --- | --- |
| 03:00:59 | 会话开始；捕获链暂停，serialhub 接管串口 | — |
| 03:01:01 | SSH reboot -f 进入 flash 链 | — |
| 03:01:03 | 旧 flash banner g2797f3dd3860 出现，停 3 s autoboot | — |
| 03:01:06 | 旧 U-Boot 控制台就绪（version 门禁） | — |
| 03:01:06 | loadx 厂商 RAM 镜像 426,048 B 到 0x47f00000 | 40.1 s（417 块，CRC 模式） |
| 03:01:48/50 | md.b 头/尾两窗校验 OK；go 0x47f00000 | — |
| 03:01:51 | 厂商控制台就绪（1 + 密码，stock U-Boot 2013.04） | — |
| 03:01:53 | xmodem v3 u-boot.bin 450,936 B 到 0x47f00000 | 42.1 s（441 块） |
| 03:02:35/37 | md.b 头/尾两窗校验 OK；go 0x47f00000 | — |
| 03:02:37 | v3 banner g85c7367a3106 出现，停 autoboot | — |
| 03:02:40 | v3 控制台就绪 | — |
| 03:02:41 | loadx env 块 131,072 B 到 0x46000000 | 14.1 s（128 块） |
| 03:03:50 | env 在 RAM 的 md == 6e2c01da…；ENV ERASE 发送 | — |
| 03:04:46 | 擦后读回 md 全 FF 哨兵 == b5a41c37…；ENV WRITE 发送 | — |
| 03:05:41 | env 读回 md == 6e2c01da… | — |
| 03:06:37 | secondboot 读回 md == 540db435… 基线 | — |
| 03:06:37 | loadx v3 mtd0 镜像 655,360 B 到 0x44000000 | 60.1 s（640 块） |
| 03:12:13 | 镜像 RAM md == f6d179da…；IMAGE ERASE 发送 | — |
| 03:16:50 | 擦后读回 md 全 FF 哨兵 == 152e56ba…；IMAGE WRITE 发送 | — |
| 03:21:29 | 镜像读回 md == f6d179da…（0 差异、0 gaps） | — |
| 03:22:24 / 03:23:20 / 03:24:15 | 写后 env / secondboot / tail 三个 md 窗均与基线一致 | — |
| 03:24:15 | **WRITE VERIFIED，HOLD（不复位）**；报告期望 mtd0 sha 5ebb5ab3… | — |
| 03:24:21 | 捕获链恢复；VERDICT B-WRITE-GREEN-HOLD | 会话总计约 23 分 22 秒 |

串口数据量：xmodem 共 1,663,416 B（约 1.63 MB），累计约 2 分 36 秒；md.b 十六进制回读占用了会话绝大部分时间（见 §7）。

## 4. 写入阶梯（逐门禁）

### 4.1 env 块（让 mtd0 回到干净基线）

命令与串口原文（serial-excerpt.txt）：

    => mtd erase spi-nand0 0xc0000 0x20000
    Erasing 0x000c0000 ... 0x000dffff (1 eraseblock(s))
    => mtd read spi-nand0 0x45000000 0xc0000 0x20000
    Reading 131072 byte(s) (64 page(s)) at offset 0x000c0000
    => md.b 0x45000000 0x4000            (8 窗，均全 FF)
    => mtd write spi-nand0 0x46000000 0xc0000 0x20000
    Writing 131072 byte(s) (64 page(s)) at offset 0x000c0000
    => mtd read spi-nand0 0x45000000 0xc0000 0x20000
    Reading 131072 byte(s) (64 page(s)) at offset 0x000c0000
    => md.b 0x45000000 0x4000            (8 窗，md == 6e2c01da…)

门禁：擦前 RAM md == 6e2c01da（源正确）→ 擦后全 FF → 写后读回 == 6e2c01da；three gates 全 PASS。

### 4.2 image 区（装入 A6 v3）

    => mtd erase spi-nand0 0x20000 0xa0000
    Erasing 0x00020000 ... 0x000bffff (5 eraseblock(s))
    => mtd read spi-nand0 0x45000000 0x20000 0xa0000
    Reading 655360 byte(s) (320 page(s)) at offset 0x00020000
    => md.b 0x45000000 0x4000            (40 窗，均全 FF)
    => mtd write spi-nand0 0x44000000 0x20000 0xa0000
    Writing 655360 byte(s) (320 page(s)) at offset 0x00020000
    => mtd read spi-nand0 0x45000000 0x20000 0xa0000
    Reading 655360 byte(s) (320 page(s)) at offset 0x00020000
    => md.b 0x45000000 0x4000            (40 窗，md == f6d179da…)

门禁：写入前 RAM 源 md == f6d179da → 擦后全 FF（152e56ba…）→ 写后读回 md == f6d179da（0 差异、0 gaps）；随后 env / secondboot / tail 三个只读窗再次确认未被波及。

## 5. 写入与命令审计

- mtd erase：恰 2 条 —— mtd erase spi-nand0 0xc0000 0x20000；mtd erase spi-nand0 0x20000 0xa0000。
- mtd write：恰 2 条 —— 0x46000000/0xc0000/0x20000；0x44000000/0x20000/0xa0000。
- forbidden 计数：0（无 nand write/erase、无 saveenv、无 upgrade、无 flash 擦除类其它命令）。
- 写范围：env 块 0xC0000..0xE0000 与 image 区 0x20000..0xC0000，两者不相交；secondboot 0x0..0x20000 与 tail 0xE0000..0x100000 全程未写（前后 md 一致）。
- 断电：本会话 0 次；结束时 HOLD、不复位，等用户断电。

## 6. mtd0 重构值与确认

- 重构公式：以干净基线 887a7f6c… 为准，把 image 区（0x20000..0xC0000）替换为 v3 镜像 f6d179da…，其它区（secondboot 540db435…、env 6e2c01da…、tail b5a41c37…）保持 → **5ebb5ab323bafea4a310e4cb3f78cbb77b3d219ba9fb324927bf28e8d0cc48cf**，与本地 expected-mtd0.bin 逐字节相同（差异字节 402,417，全部落在 image 区）。
- 确认 1（冷启动）：写入验证并 HOLD 后，用户断电一次上电；新 U-Boot g85c7367a3106 从 flash 启动 → e2631boot → slot1 → 内核；设备侧 sha256sum /dev/mtd0 == 5ebb5ab3…（serial-after-reboot-003.txt 03:38 的只读诊断），同时以太网/PCIe 双端点/Wi-Fi 全部起来了。
- 确认 2（后续独立复核）：T-61 会话的 Phase A 在任何写之前，用只读 SSH 全片读 mtd0 == 5ebb5ab3…，与本次重构值一致；随后 T-61 才把它改成 f9239040…（15-patch 镜像）。

## 7. 教训

1. **不要把 mtd 大区 dump 到串口。** 115200 baud 下 hex 输出有效带宽约 10 KB/s，一次 640 KiB 的 md.b 回读就要约 4 分 36 秒（本次 image 区三段 md 共约 14 分钟，占会话大半）。后续改用：Linux 侧 dd | sha256sum（640 KiB 0.15 s）、U-Boot 侧 crc32（秒级），串口只做控制台。
2. **mtd write 不擦除。** 任何 flash 写都必须先 erase → 读回全 FF 哨兵 → write → 读回比较；本次手工阶梯与后来 e2631flash 内建阶梯是同一模式。
3. **读回失败要用断言。** C1b-1 v1 的 -74/EIO 教训是“读失败后拿 stale RAM 越过门禁”；本次每个 mtd read 都断言成功且每次 md 都从新读回的数据计算。
4. **HOLD 语义。** 写入验证后不发 reset、不自动继续，等用户断电——给人留出检查/中止窗口。
5. 用户要求“完成后停止一切进一步操作”：本会话在 WRITE VERIFIED + 用户断电冷启动确认后即停止，不再追加任何设备实验；本记录以该确认为终点，后续 T-61 才继续。

## 8. 一个驱动缺陷的诚实记录（cmp 假失败）

写入验证的最后一步曾发过一条可选的 cmp（作为额外保险）：

    => cmp 0x44000000 0x45000000 0xa0000
    word at 0x44000000 (0x00) != word at 0x45000000 (0xffffffff)
    Total of 0 word(s) were the same

这是**驱动侧缺陷，不是产品问题**：在 cmp 之前，tail 区只读被读进了 0x45000000（该区全 FF），把镜像读回用的 0x45000000 内容覆盖了；于是 cmp 实际在比较“0x44000000 的镜像”与“0x45000000 的 tail 全 FF”。写入验证的判定并不依赖这条 cmp——判定依据是 03:21:29 的 image-readback md（40 窗全等、0 gaps）与写后 env/secondboot/tail 三个 md 窗。该缺陷已在驱动中记为“cmp 仅作可选、不得复用被覆盖的 scratch 区”。

## 9. 附件清单（t62-session-b-flash/）

| 文件 | 内容 |
| --- | --- |
| tool-c1b2_sessionB.py | 本会话驱动（厂商 RAM 控制台入口、xmodem、env/image 两段阶梯、md 门禁、HOLD、审计） |
| preflight.json | 会话前只读门禁（产物/image/vendor RAM 哈希、基线、期望值、设备事实、路由、捕获链） |
| session-results.json | 完整结果 JSON（逐命令输出、md 结果、审计、verdict） |
| driver-console.txt | 驱动日志（时间线、每步耗时、门禁结论） |
| serial-excerpt.txt | 串口原文精选（banner、xmodem 报告、env/image 擦写、读回、cmp 缺陷段） |
| serial-after-reboot-003.txt | 用户断电冷启动后的只读诊断（sha256sum /dev/mtd0 == 5ebb5ab3…、PCIe/网口/fwstate） |
| tool-reconstruct-expected-mtd0.py | 重构 expected-mtd0 的脚本（基线 887a7f6c + v3 镜像 → 5ebb5ab3 验证） |
| SHA256SUMS.txt | 本目录文件校验和 |
