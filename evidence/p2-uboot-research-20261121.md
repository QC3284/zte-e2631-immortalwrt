# 自定义 U-Boot 可行性调研：主线移植、原厂二进制修改与刷写工具链（2026-11-21）

任务：task-40（P2-研1「U-Boot 定制可行性调研」）。对象：ZTE ZXHN E2631（Sanechips ZX279128S，双 Cortex-A9，256 MiB DRAM，128 MiB SPI-NAND）。
目标：给出「自定义 U-Boot」的可执行可行性矩阵（路径 / 工作量 / 风险 / 前置 / 推荐），供立项与用户拍板。

方法（只读）：本地源码与文档、mtd0 静态反汇编、U-Boot 主线仓库实测抓取（GitHub API，2026-11-21）、公开资料交叉验证。
**本轮未连设备、未本地编译、未写 flash、未改源码。** 本文件是 task-40 的唯一仓内产物。

关联：[docs/多功能U-Boot可行性-2026-11-14.md](../docs/多功能U-Boot可行性-2026-11-14.md)、[docs/U-Boot结构分析-2026-11-15.md](../docs/U-Boot结构分析-2026-11-15.md)、[evidence/uboot-re-20261115.md](uboot-re-20261115.md)（U-逆1 偏移依据）、[docs/救砖手册-2026-11-15.md](../docs/救砖手册-2026-11-15.md)、[docs/gpl-request-draft-2026-11-14.md](../docs/gpl-request-draft-2026-11-14.md)。

---

## 0. 结论速览

### 0.1 三条路可行，但要分先后

| 路径 | 内容 | 工作量（活跃人日） | 主要风险 | 硬前置 | 建议阶段 |
| --- | --- | --- | --- | --- | --- |
| **A 主线 U-Boot 移植** | 用 U-Boot 主线（2027.01-rc2 代）替换厂商 2013.04，保留 secondboot | 12–20 天，约 3–6 个日历周（业余） | 首次写引导区不可完全回滚；SPI 控制器驱动是大头 | C + mtd0 OOB/ECC 取证 + RAM 链 POC | 长期方案，分 A1/A2/A3 |
| **B 原厂二进制修改** | 不改架构，只改 env 默认值、控制台密码摘要等可定位点 | 1–3 天 + 1 次需批准的设备会话 | 写 boot 区失败=真砖；不能加新能力 | C 的刷写/回滚协议 | 短期收益，先做 |
| **C 打包 + 刷写工具链** | 镜像头封装、env 生成、二进制定点修改、回读校验 | 3–5 天工具 + 1–2 天演练文档 | 工具本身不碰设备 | 无（可完全离线） | **最先落地**，A/B 共同前置 |

推荐组合：**C → B → A**。只要「去控制台密码 + 改默认 env + 把 tftp+bootm 做成开机脚本」，做到 B 即可（vendor U-Boot 自带 tftp/bootm/setenv，不需要新驱动），约 1–2 周。要完整可控、可维护、可分发、无厂商密码的引导链，才需要 A；A 的第一阶段（RAM 链 POC）不写 flash，零风险。

### 0.2 本次新增的三个关键事实（改变 A 的成本判断）

1. **secondboot 已替 U-Boot 做好 CPU1 停车环。** 反汇编 0x200840 起：MPIDR 分流，非 CPU0 执行 `wfe` 后 `mov pc, 0x200800` 循环；内核 platsmp 正是依赖它，在启动时把 0x200800 两个字改成跳 `secondary_startup`。⇒ 保留 secondboot 的自定义 U-Boot **不需要实现 SMP 交接**，只要不碰 SRAM 0x200800。
2. **U-Boot 主线已具备大部分现成件**：PL011 串口、Cortex-A9 global timer 驱动（compatible 正好是 `arm,cortex-a9-global-timer`）、`spi-mem`、SPI-NAND 框架（`foresee.c` 已有 F35SQA001G/F35SQA002G，ID 0x71/0x71、2048+64、128 MiB）、MTD env（`env/mtd.c`）、`sysreset_syscon`、`mtd` 命令。⇒ 缺口收缩为：**ZX SPI 闪存控制器驱动（移植内核 patch 023 的 PIO 版）+ mach/board 骨架 + 配置**，不是从零写 U-Boot。
3. **厂商 env 与 U-Boot 主线 env 格式逐字节兼容**：两边都是 `[u32 LE CRC32][0x1FFFC 数据]`，CRC32 覆盖数据区（U-Boot `include/env_internal.h:57-62`、`env/common.c:452`；vendor 侧 RE §5 实测 CRC=0xAFFCEC3E）。⇒ 自定义 U-Boot 可沿用 0xC0000 既有 env 区。

### 0.3 最大的风险（先说）

- **mtd0 的 U-Boot 区（0x20000–0xA0000）写入方案未验证。** 两次整片 dump 的 64 B spare/OOB 全是 0xFF（手册 §6.6），说明编程器只导出了主区；而本芯片是**片内 ECC**（4 bit/512 B，校验位固定占每 16 B OOB 段的 8..15 字节，见内核 patch 028 与 IWRT backport 436）。写回时 ECC 位不对，BootROM 读 secondboot 就会失败。
- 写引导区的工具优先级：**vendor U-Boot 自带命令 > 编程器 > Linux 侧强写**。vendor U-Boot 有专门的 `nand write.uboot - addr off size`，紧跟 `write uboot to nand with 4-bit-ecc, compatible with bootrom.`（@file 0x6173f/0x61760），这是厂商留给写 boot 区的通道；参数语义尚未实测。
- OOB/ECC 观测与写回验证完成前，**把首次刷引导区当成不可逆操作**。

### 0.4 需要用户拍板

1. 要 A（完整自定义 U-Boot）还是 B（去密码 + env 定制）就够？
2. 是否批准一次「只读 OOB 取证」设备会话（读 mtd0 spare，不写）？
3. 是否批准一次「RAM 链 POC」设备会话（vendor 控制台 tftp+go 启动自编译 U-Boot，不写 flash）？
4. 是否接受首次写引导区的风险（编程器回写未验证）？
5. 是否发出 GPL 源码索取函（vendor U-Boot 2013.04 源码对 header/cspboot/ECC 细节是降险项）？

---

## 1. 事实基线（本次复核）

### 1.1 引导链与 mtd0 镜像地图

引导链（串口实测，`/home/qc233/zte/e2631-uboot-help.log`；手册 §1.4）：BootROM（`Boot SPI NAND / start read bootheader / start read secondboot / non secure boot / Jump`）→ secondboot（CRPM、DDR 1333 Mbps、串口、SPI-NAND、CPU1 停车、加载 U-Boot）→ U-Boot 2013.04 (Aug 28 2023 - 18:40:22) → cspboot（扫两个槽头、按 serial 选固件）→ Linux。

mtd0（1 MiB，flash 0x0）内部布局（RE 证据 §2）：

| 文件偏移 | 长度 | 内容 |
| --- | --- | --- |
| 0x0–0x7FF | 0x800 | secondboot 封装头（+0x10 魔数 "128s"、+0x14 LE 载荷长度、+0x80 "0001ZXIC.."、+0x90 "BOOTROM"、+0xA0 "RSA2048"、+0xAC=4、+0xB0=0x6100、+0x2D4 起 32 B 未知摘要） |
| 0x800–0x68AB | ~0x60AB | secondboot 代码（运行时 0x00200000 + 文件偏移；声明长度 0x8000，实际代码到 0x68AB，0 填充到 0x1FFFF） |
| 0x20000–0x207FF | 0x800 | U-Boot 封装头（结构同上，+0xB0=0x66080） |
| 0x20800–0x8683F | 0x68000 | U-Boot 载荷（运行时 0x47F00000 + (偏移-0x20800)；2013.04 的 416 KiB 镜像） |
| 0x86800 / 0x88800 | 0x40×2 | 载荷尾部/镜像尾部 64 B 描述块（可选，secondboot 不校验） |
| 0x88840–0xBFFFF | ~222 KiB | 0xFF 空区（载荷上限 0x9F800，即载荷末 ≤ 0xA0000；0xA0000–0xBFFFF 另有 128 KiB 空闲） |
| 0xC0000–0xDFFFF | 0x20000 | env：[u32 LE CRC32][0x1FFFC 数据] |
| 0xE0000–0xFFFFF | 0x20000 | 0xFF 空区（保留） |

RE 结论（§3、§4）：secondboot 跳 U-Boot 前**只查两道门**——安全启动 strap（[0x9A10701C]&1，本机 0）与封装头 +0x10 的 32 位魔数 0x73383231（"128s"）；然后按 +0x14 长度 memcpy 到 0x47F00000 并 blx，**没有 CRC、签名、长度上界**；+0x2D4 摘要也不校验。

### 1.2 新增证据：CPU1 停车环在 secondboot 里

地址换算同 RE（secondboot 运行时 = 0x00200000 + 文件偏移）。0x200840 起反汇编：

    0x200840  mrc p15, 0, r0, c0, c0, 0     ; MIDR
    0x200844  mrc p15, 0, r0, c0, c0, 5     ; MPIDR
    0x200848  and r0, r0, #0xf
    0x20084c  mov r1, #0
    0x200850  cmp r1, r0
    0x200854  beq 0x200864                  ; CPU0 继续
    0x200858  wfe
    0x20085c  ldr r0, [pc, #0x140]          ; 字面量 @file 0x9a4 = 0x00200800
    0x200860  mov pc, r0                    ; CPU1：醒来回 SRAM 0x200800 再走一遍
    0x200864  ...                           ; CPU0：切 SVC、清 cache/BSS，继续主流程

内核侧约定：树 fork `target/linux/zx279128/files/arch/arm/mach-zte/platsmp-zx279128s.c:5-9`（bootloader 从片上 SRAM 运行，把非 CPU0 核赶进 WFE→跳 SRAM 起始循环）；启动第二核时内核把 SRAM 起始（DT `mmio-sram@0x00200800`）两个字换成 `ldr pc,[pc,#-4]` + `secondary_startup` 地址再 `dsb_sev()`（同文件 :32、:49-53）。
⇒ 自定义 U-Boot 无需处理 CPU1；只要内核启动前不改写 SRAM 0x200800，SMP 交接照旧。A 里最不确定的「多核怎么办」被消掉。

### 1.3 vendor U-Boot 2013.04：能力与限制

- 实测 43 个命令（help log；手册 §4.2）：串口、TFTP/DHCP/PING、bootm/bootz、md/mw/mtest、nand/mtddebug、upgrade、saveenv/setenv/printenv、go、reset、watchdog 等；**无 usb/mmc**。
- 已有实测：TFTP+bootm RAM 引导（2026-10 真机记录，docs/01:112-118；手册 §4.5）；串口控制台+密码（手册 §4.1）。
- flash 写命令：`nand write.uboot`（写 U-Boot，4-bit ECC，兼容 BootROM）、`nand read/write/erase`、`mtddebug read/write/erase`（分区列表：read 串为 boot/env/kernel/kernel1/other/all，write 串只列 boot/env/kernel/all）、`upgrade`（boot/image/version，TFTP 下载）、`saveenv`。除 saveenv 外均未在真机验证（手册 §7.2 列为禁用）。
- 版本 U-Boot 2013.04（Aug 28 2023 构建），GPLv2；源码索取草稿 `docs/gpl-request-draft-2026-11-14.md:19-22`。
- 尺寸预算：载荷 ≤ 0x9F800（约 638 KiB）；主线 U-Boot 含 DM/MTD/SPI/命令通常 400–600 KiB，够用但需裁剪。

### 1.4 SoC 资源与内核侧可复用代码

| 资源 | 地址/参数 | 内核侧证据 | U-Boot 侧现状 |
| --- | --- | --- | --- |
| CPU | 2× Cortex-A9，1 GHz，无 VFP/NEON（软浮点） | patch 026 dtsi；seed config SOFT_FLOAT | 通用 armv7 |
| UART0 | PL011 @0x94404000，115200 8N1 | patch 026 serial0；`clk-zx279128s.c:504`（uart0 wclk 可 25M/100M） | `serial_pl01x.c`（clock=0 可跳过 baud 设置） |
| Timer | A9 global timer @0x800200（compatible `arm,cortex-a9-global-timer`，clock=a9_periph）；TWD @0x800600 | patch 026 dtsi；clk 驱动 :281（a9_periph=cpu/2） | `arm_global_timer.c` / `arm_twd_timer.c`（compatible 完全匹配） |
| SRAM | @0x00200800，0x1000；SMP 停车向量 | patch 026 dtsi；platsmp | 不碰即可 |
| SPI 闪存控制器 | SPIFC @0x94406000（QSPI，PIO+DMA） | patch 022/023；`spi-zx.c:1-9,61,379,568-571` | **无**，需移植（PIO 子集） |
| SPI-NAND | 128 MiB，2 KiB 页 + 64 B OOB，片内 4 bit/512 ECC | IWRT backport 436；patch 028（OOB/BBM） | 框架 + foresee F35SQA001G 条目已有 |
| 时钟 | topcrm @0x94000000（25 MHz 晶振）、lsp0crpm @0x94400000 | patch 026 dtsi；clk 驱动 | 最小只需 fixed-clock，不移植完整 CRPM |
| DRAM | 256 MiB @0x40000000；DDR init 在 secondboot | 串口日志；secondboot 反汇编 | 板级 `gd->ram_size=0x10000000` |
| 以太网 | GMAC @0x92000000，ZTE 4-port switch/PPE | patch 020/021；`zx279128s-main.c` | 无主线驱动；MVP 不做，网络引导用 vendor U-Boot |

### 1.5 U-Boot 主线实测快照（2026-11-21）

- 仓库 `u-boot/u-boot`，main @ `c1958b5f6cce03956d309ce422b5d9f819955d4a`（2026-11-19），Makefile 2027.01-rc2；递归树 39249 blob，未截断。
- **无任何 ZTE/Sanechips/ZX 板级或 mach 代码**：无 `board/zte`、`arch/arm/mach-zte`、`mach-sanechips`；只有 `dts/upstream/Bindings/arm/zte.yaml` 与 `dts/upstream/src/arm/zte/zx297520v3*.dts(i)`（binding import，不能用于 ZX279128S）。
- 现成可用件（文件存在+关键实现已核实）：`drivers/mtd/nand/spi/foresee.c`（F35SQA002G 0x72/0x72；**F35SQA001G 0x71/0x71，1 Gbit、2048+64、1024 块**）；`drivers/mtd/nand/spi/core.c`（probe 后 `sprintf(mtd->name, "spi-nand%d")` + `add_mtd_device()`）；`env/mtd.c`（`ENV_IS_IN_MTD`/`ENV_MTD_DEV`）；`cmd/mtd.c`（CMD_MTD）；`arm_global_timer.c`、`arm_twd_timer.c`；`serial_pl01x.c`；`sysreset_syscon.c`。
- 芯片 ID 待核实：vendor 日志 `manuid=cd chipid=71`（识别为 FSNAND F35SQA001G），而 IWRT 内核 backport 436 的 HYF1GQ4UDACAE 是 0xc9 厂商 ID。U-Boot 里打印一次 READID 即可定论：0xCD/0x71 用现成 foresee 条目；若是 0xC9，把内核 heyangtek.c 的厂商条目搬进 U-Boot（结构相同，照抄即可，<1 天）。

---

## 2. 路径 A：主线 U-Boot 移植（可行，三阶段）

### 2.1 总体判断

**可行**，且比 2026-11-14 的判断乐观，因为可**保留 secondboot**：DDR、PLL/时钟、串口、SPI-NAND 读取、CPU1 停车全部继承；U-Boot 只需从 0x47F00000 接管。U-Boot 侧要做的是 mach/board 骨架、串口、timer、reset、SPI 控制器、SPI-NAND/env、从槽位读内核并 bootm——**不需要 SPL、DDR init、SMP 代码**。secondboot 只认「0x800 封装头 + "128s" + 长度」，自定义镜像合法（头块其余字节保持原样）。
代价：引导链仍有闭源 secondboot + BootROM；完全开源引导需重写 DDR 初始化，属另一量级项目，不推荐。A 的产出是「可维护、可定制、可分发（GPL 部分）的 U-Boot 段」。

### 2.2 需要新增/修改的清单

| 文件/组件 | 内容 | 预计 |
| --- | --- | --- |
| `arch/arm/mach-zx279128s/{Kconfig,Makefile}` + cpu/sysmap 最小件 | SOC 选择、内存映射（UART/SPI/SRAM）、board_init 前置 | 2–4 天 |
| `board/zte/zxhn-e2631/{Kconfig,Makefile,board.c,MAINTAINERS}` | dram_init（256 MiB）、board_init（UART/env）、可选 late init 读槽头 | 2–3 天 |
| `arch/arm/dts/zx279128s-zte-zxhn-e2631.dts` | 从内核 DTS 裁剪 + fixed-clock（a9_periph 500 MHz、UART 待测）+ spi-nand 节点 | 1–2 天 |
| `configs/zx279128s_zte_zxhn-e2631_defconfig` | TEXT_BASE=0x47F00000、SYS_SDRAM_BASE、ENV_IS_IN_MTD、DM_MTD/SPI、CMD_MTD、PL011、ARM_GLOBAL_TIMER、SYSRESET_SYSCON | 1 天 |
| `drivers/spi/spi-zx.c`（U-Boot 版） | 移植内核 patch 023 的 **PIO** 路径到 spi-mem `exec_op`（不搬 DMA/中断），覆盖 PP/READ/WRITE/ERASE | 4–8 天（最大单项） |
| SPI-NAND 芯片支持 | 先验证 foresee 0x71/0x71；若 ID=0xC9 加 heyangtek 厂商条目 | 0.5–1 天 |
| env | `CONFIG_ENV_IS_IN_MTD`、`ENV_MTD_DEV="spi-nand0"`、`ENV_OFFSET=0xC0000`、`ENV_SIZE=0x20000` | 0.5 天 |
| 启动流程 | 读 slot1 的 uImage（slot1+0x20）→ bootm；内核 `CMDLINE_FORCE=y`，bootargs 非硬依赖；保留内存/TFTP 开发路径 | 1–2 天 |
| 文档+复现脚本 | 构建说明、RAM 链步骤、刷写步骤（与 §4 合并） | 1–2 天 |

合计约 **12–20 个活跃人日**；业余节奏 3–6 个日历周（含串口调试返工缓冲）。

### 2.3 启动流程设计（目标态）

1. BootROM 读 secondboot（0x0）；secondboot 初始化 DDR/时钟/串口/SPI-NAND，设置 CPU1 停车，读 U-Boot 封装头（0x20000）并拷贝载荷到 0x47F00000，跳转。
2. 自定义 U-Boot 从 0x47F00000 启动：PL011 banner（时钟未知时 `CFG_PL011_CLOCK=0` 跳过 baud 设置，沿用 secondboot 的 115200）；timer 用 A9 global timer（fixed-clock 500 MHz）。
3. 探测 SPIFC → SPI-NAND（spi-nand0）→ 读 env（0xC0000，CRC32 与 vendor 相同）→ CRC 坏则用内置默认 env。
4. bootcmd：读 slot1 的 uImage 到 0x43000000 → bootm；失败停控制台（可 mtd read/mw/go 手工救）。
5. 内核用内置 cmdline（kit bootstrap 已保证 CMDLINE_FORCE=y），root 指向 slot 解析出的 mtdblock；U-Boot 不依赖精确 root= 传参。
6. 可选 P3：网络（GMAC 是 ZTE 私有 4-port switch，U-Boot 无驱动，成本高）——MVP 不做；需要网络先用 vendor U-Boot TFTP 载入。

### 2.4 分阶段验收

| 阶段 | 内容 | 写 flash？ | 验收标准 |
| --- | --- | --- | --- |
| **A1 RAM 链 POC** | 最小编译（串口+timer+mem，链接 0x43000000），vendor 控制台 `tftp 0x43000000` + `go 0x43000000` | 否 | 串口出现自定义 banner；md/mtest 可跑；断电即恢复，零风险 |
| **A2 读启动链** | 加 SPIFC/SPI-NAND/env/mtd，在 RAM 里跑：读 env、mtd read 读 slot1 uImage、bootm 启 Linux | 否 | RAM 里的自定义 U-Boot 能把现有系统从 NAND 启动（证明驱动与槽位逻辑） |
| **A3 刷入+救援演练** | 按 §4 通道写 mtd0 U-Boot 区；做断电/坏镜像演练与回滚 | 是（需批准+OOB 方案） | 冷启动进自定义 U-Boot；能启动系统；回滚原 dump 后正常 |

**A3 之前全部零砖风险**——这是推荐先做 A1 的原因。

### 2.5 风险与缓解

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 首次写 boot 区失败→真砖 | 高 | 先做 §4.4 OOB/ECC 取证；只走已验证通道（C1/C3）；保留原 dump；A3 前把「编程器回写验证」列为前置 |
| 芯片 ID 0xCD vs 0xC9 | 低 | A1 打印 READID；必要时照抄内核厂商条目 |
| UART 时钟未知 | 低 | `CFG_PL011_CLOCK=0` 先跳过；或从 lsp0crpm/实测反推（25M/100M） |
| timer 频率 | 低 | fixed-clock=a9_periph=CPU/2（按 clk 驱动 :281，1 GHz⇒500 MHz）；sleep 1 对照秒表校准 |
| 封装头 +0x2D4 摘要语义未知 | 低 | 原样保留（secondboot 不校验），不改这些字节 |
| 载荷长度/大小预算 | 低 | 生成器自动填 +0x14；载荷 ≤0x9F800，超限报错 |
| 交接状态（MMU/cache/CPU 模式）未知 | 中 | A1 从最保守配置开始；串口逐段定位；通用 armv7 start.S 覆盖常见状态 |
| 无主线 SoC 支持，维护成本 | 中 | 自用 fork 分支 + 静态 CI 门（类似现有 tree fork）；不追上游 |
| MVP 无网络 | 低 | vendor U-Boot TFTP 装载；或 mtd read/go 手工救 |
| 法律/GPL | 低 | U-Boot 主线 GPLv2+，发布附源码；vendor 2013.04 二进制不重分发 |

### 2.6 法律与合规

U-Boot 2013.04 以 GPLv2 发布；对 GPL 部分的**私有修改** GPLv2 允许（§2 不限制自用修改，§3 只约束分发）。路径 A 产物全部来自 U-Boot 主线（GPLv2+），可随本项目 fork 分发（附源码），不涉及 ZTE 专有代码。路径 B 的「修改后的 vendor 二进制」**不要对外分发**（ZTE 代码 + GPL/专有混合，有合规争议），自用可以。项目已定「不给上游提 issue/PR」，A 的移植只放自用 fork。

---

## 3. 路径 B：原厂 U-Boot 二进制手术

### 3.1 可改点总表

偏移以 `mtd0-bootloader.bin`（sha256 `de4ea5bd…`）为准；「写？」= 是否必须写 mtd0 引导区。

| # | 位置 | 现值/内容 | 改法 | 效果 | 写？ | 风险 |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | env 区 0xC0000（128 KiB） | `[CRC32][0x1FFFC 数据]`（bootdelay/bootcmd/ipaddr…） | **首选** vendor 控制台 `setenv …`+`saveenv`（U-Boot 自己重算 CRC）；离线改：生成同格式数据并重算 CRC32 | 改倒计时、默认 IP/MAC/serverip、bootcmd 脚本（可把 tftp+bootm 写成自动网络启动） | 是（只写 env 区） | 低（env 坏了通常仍能进 U-Boot） |
| B2 | 0x61F80，20 B | 控制台密码的无盐 SHA1 摘要 SHA1("5cE080@fyBD") | 改成另一个已知密码的 SHA1（长度受固件 "passwd is too long" 限制，具体上限未测）；不要试图留空/明文 | 换控制台密码（代码路径没有「删除密码」开关，除非 B3 语义确认） | 是（写 U-Boot 区） | 中（改错最多进不了控制台，系统仍能启动） |
| B3 | 0x61F94，u32 | 密码相关使能 flag（RE §Q4 提到，语义未逐位确认） | 暂不改；等 B2 实测后再评估 | 可能实现「无密码进控制台」 | 是 | 中高（语义未确认） |
| B4 | 0x51F9C / 0x5201E–0x52173 | 内置 fallback env（仅 env 区 CRC 坏时用） | 可不改；要改只做等长替换 | 影响 env 坏时的默认网络参数 | 否（随镜像） | 低收益 |
| B5 | 0x5AC99 等字符串区 | "Hit 1 to upgrade software version" 等 | 不建议改（代码路径未 RE） | 仅提示文案 | 是 | 低收益/中风险 |
| B6 | cspboot/upgrade 逻辑 | 槽位选择/升级校验 | 不动（改错丢救援路径） | — | — | 高 |

> B 的「高性价比集合」只有 **B1（env）+ B2（密码）**；B3 未确认不做，B4–B6 不做。

### 3.2 不改二进制就能拿到的收益（纯 env）

vendor U-Boot 已含 tftp/dhcp/ping/bootm/setenv/saveenv/run/go/mtddebug 等命令（§1.3），仅用 env 就能：改 bootdelay（默认 3 s）、bootcmd、ipaddr/serverip/ethaddr；写「先尝试网络 TFTP 载入指定镜像，失败再走原厂 cspboot」的 bootcmd 脚本；保留原厂 Press 1 升级路线不变。这些只需一次 `saveenv`（写 env 区，风险最低的 flash 写）。

### 3.3 CRC / 校验处理

- env：`crc32(0, data@0xC0004, 0x1FFFC)` 写入 0xC0000 的 4 B；与 U-Boot 主线算法一致（`env/common.c:452`）。saveenv 自动处理；离线生成见 §4 工具。
- U-Boot 封装头：secondboot 不校验 CRC/签名（RE §4）；只做**等长**原地 patch（B2）时头块完全不用动；若替换整个载荷（A），生成器填 +0x14 长度，其余字节从原头块复制。
- 槽位版本头 CRC 与 U-Boot 无关，B 不碰。

### 3.4 刷写与回滚

B1（env）走 `saveenv`（U-Boot 自己写+自己校验），风险最低；B2 走 §4.3 boot 区写入通道，必须先完成 §4.4 的 OOB 取证与回滚准备。**任何写操作前先读出当前 mtd0 并保存 sha256**（基线见手册 §2.3）。

### 3.5 工作量

离线准备（改密码摘要、生成 env、算 CRC、回读脚本）0.5–1 天；1 次设备会话（进入、printenv、B1 改 env、验证重启；如需 B2 按 §4 写 boot 区并回读）0.5–1 天 + 用户批准。合计 1–3 天（含文档）。

---

## 4. 路径 C：镜像打包 + 刷写工具链

### 4.1 工具清单（建议进 kit，与现有 host/、tools/ 风格一致）

| 工具 | 作用 | 验收（离线） |
| --- | --- | --- |
| `tools/mkuboot-image.mjs` | 生成 U-Boot 区镜像（覆盖 0x20000–0xA0000，共 0x80000 字节）：0x800 头块从原 dump 模板复制（只改 +0x14=载荷长度，+0x2D4 原样），载荷放 0x20800，尾部按需保留 trailer；超 0x9F800 报错 | 对 vendor 原镜像「拆-装」往返：输出与 mtd0[0x20000:0xA0000] 逐字节一致（除自动填的长度字段） |
| `tools/e2631-env.mjs` | env 文本 ⇄ 0x20000 区块：解析/生成 key=value、pad 0x1FFFC、写 LE CRC32 | 对现网 env 解析-重生成，输出逐字节等于原块（CRC=0xAFFCEC3E） |
| `tools/patch-uboot.mjs` | 定点 patch：`password=<new>` → 0x61F80 写 SHA1；打印 before/after hex | 对原 dump patch，只有目标字节变化；SHA1 与 sha1sum 对拍 |
| `tools/verify-mtd0.mjs` | 回读比对：给串口/文件块与 sha256 基线，报告差异偏移 | 原 dump 自比对 0 差异；篡改副本报出偏移 |
| 文档（手册新增 §6.7） | 打包、刷写、校验、回滚步骤 | 审阅 + 演练记录 |

### 4.2 镜像格式规格（工具要固化）

| 偏移（相对 0x20000） | 字段 | 取值/规则 |
| --- | --- | --- |
| 0x000–0x7FF | 头块 | 从 mtd0[0x20000:0x20800] 原样复制；不重排/不清零 |
| +0x10 | 魔数 "128s" | 0x73383231（LE），保持 |
| +0x14 | u32 LE 载荷长度 | = 载荷字节数（如 0x68000）；secondboot 只按它 memcpy |
| +0x80/+0x90/+0xA0/+0xAC/+0xB0 | "0001ZXIC.."/"BOOTROM"/"RSA2048"/4/0x66080 | 保持原值 |
| +0x2D4–0x2F3 | 32 B 未知摘要 | 保持原值（secondboot 不校验） |
| +0x800 起 | 载荷 | ≤0x9F800（载荷末 ≤0xA0000），超限报错 |
| env（0xC0000，独立工具） | `[u32 LE CRC32][0x1FFFC 数据]` | CRC32 覆盖 0x1FFFC 数据区；数据为 NUL 分隔 key=value，尾部 0x00 填充 |

### 4.3 刷写通道矩阵

| 通道 | 前提 | 写什么 | 证据等级 | 风险/备注 |
| --- | --- | --- | --- | --- |
| **C1 vendor U-Boot 控制台 + TFTP + `nand write.uboot <addr> <off> <size>`** | 串口+控制台密码；PC 直连 LAN1（192.168.1.100）；TFTP 服务 | mtd0 的 U-Boot 区（按厂商命令语义，通常只写 0x20000 起） | 命令存在=实测；语义/参数=**未验证** | 厂商专门为写 U-Boot 设计（4-bit ECC，兼容 BootROM），首选；写前必须 §4.4 取证 + 先空跑 `nand read` 校验地址/长度语义 |
| **C2 vendor `upgrade boot`（TFTP 下载 bootloaderfile）** | 同上；env 默认 `bootloaderfile=bootloader.bin` | 可能写整个 boot 区（是否含 secondboot 未知） | 命令存在=实测；格式/校验流程=**未验证** | 若连 secondboot 一起重写，风险最高；优先级低于 C1，C1 走通前不碰 |
| **C3 编程器（SPI-NAND 128 MiB）** | 拆焊/WSON8 夹子、支持片内 ECC 的编程器、同机 dump | 整片或 mtd0 区 | 布局=实测（v2 dump）；**回写未验证** | v2 dump 的 OOB 全 FF，不能原样回写；须按片内 ECC 重新生成 spare（或 ECC-on 模式）；不一致则 BootROM 读 secondboot 失败；不解决 ECC 前只是最后手段 |
| **C4 Linux 内写 mtd0** | 改 DT 去掉 bootloader 分区 read-only + 用户批准 | mtd0 | 当前被 DTS 挡住（手册 §6.3） | 不建议：改内核/DT 且绕过安全设计，救砖时反而最不可靠 |

其他：vendor 还有 `mtddebug write - addr partition off size`（分区列表同 §1.3：read 串含 kernel1/other，write 串只列 boot/env/kernel/all；write @0x593a8、read @0x5934f、erase @0x5949e），更通用但「boot 分区」范围未验证，写 U-Boot 优先 C1 专用命令。写入期间绝对不断电；写后必须回读比对（§4.5）。

### 4.4 写入前必做的只读取证（关键，本轮新增建议）

1. **读 mtd0 的 OOB/spare**：从运行系统读 /dev/mtd0 每页 64 B OOB（mtdchar `MEMREADOOB` ioctl 或 `nanddump --oob`；只读操作，DTS read-only 不阻止读）。512 页×64 B=32 KiB，覆盖 secondboot+U-Boot+env 头部。用途：确认片内 ECC 位布局（预期每 16 B 段 offset 8–15 是 ECC、0–1 是 BBM）与 v2 dump OOB 全 FF 的成因，判断编程器 ECC-on 写是否可能。
2. **建立回滚基线**：`dd if=/dev/mtd0 of=/tmp/mtd0-before.bin bs=1M count=1` + sha256（应等于 de4ea5bd…），保存 U-Boot 头块 0x20000–0x207FF 与 env 区 0xC0000–0xC021F 原始 hex。
3. **验证 C1 读路径**：vendor 控制台 `nand read`/`mtddebug read` 把 U-Boot 区读回 RAM，与 dump 逐字节 cmp（建立「读命令地址语义」基线；读不通不谈写）。
4. **确认芯片真实 READID**（顺带解决 0xCD/0xC9 歧义）。

### 4.5 写入/校验/回滚协议

1. 写前：保存 mtd0 全镜像 + 目标区原始字节 + sha256。
2. 写前：`tftp` 下载新镜像到 RAM，先 `cmp`/`md` 抽样验证传输完整。
3. 写：只用 §4.3 已确认通道；写 env 用 saveenv（不手写区块）。
4. 写后：立即 `nand read` 回读同一区域到 RAM，与源镜像 cmp（全等才继续）；再读 env 区验证 `printenv` 正常。
5. 重启：先 `reset` 进 U-Boot 验证；再冷启动验证 secondboot→U-Boot→Linux 全链；记录完整串口日志。
6. 回滚：仍能进 vendor U-Boot → 用原 dump 走 C1 写回（前提 C1 已验证）；进不了 → 编程器（未验证）；事先约定停止条件（串口无输出=停在 secondboot 之前段，只能编程器）。
7. 每次写入在 `evidence/` 留记录：命令、地址/长度、sha256、回读结果、串口日志路径。

### 4.6 与救砖手册的衔接

- 建议验证通过后在 `docs/救砖手册-2026-11-15.md` 增加 **§6.7「自定义 U-Boot 的打包与刷写」**（本轮不直接改该文件，避免与 Lead 编辑冲突）：内容 = §4.2 格式 + §4.3 C1 步骤 + §4.5 校验/回滚 + 风险。
- **救援前置缺口**：手册 §4.5 已指出 CI 不产出 `initramfs.uImage`，导致「U-Boot 控制台后的 TFTP RAM 引导」还不能当实战恢复手段。U-Boot 项目会放大这条路径的重要性（自定义 U-Boot 调试也靠 TFTP），建议把补该产物列 P2 前置 CI 任务（一行 workflow 改动）。
- 手册 §6.4/§6.6 的编程器结论（回写未验证、OOB 全 FF）在本文保持并强化：编程器是最后手段，不是常规回滚。

### 4.7 工作量

工具 3–5 天（含离线往返测试）+ 演练/文档 1–2 天；设备验证需 1–2 次批准会话。**未写设备前全部可离线完成**，适合先排期。

---

## 5. 三路对比与推荐

### 5.1 对比表

| 维度 | A 主线移植 | B 二进制修改 | C 工具链 |
| --- | --- | --- | --- |
| 能拿到的能力 | 完整自定义引导：无厂商密码、自定 bootcmd/bootmenu、可加驱动/网络引导（需另做）、可维护可分发 | 去/换控制台密码、改默认 env、脚本网络启动；不能加新驱动 | 不直接产生能力，是 A/B 前置 |
| 工作量 | 12–20 活跃人日+调试 | 1–3 天+1 次会话 | 3–5 天+演练 |
| 首次写 flash 风险 | 高（写 U-Boot 区） | 中（B1 低；B2 中） | 低（离线） |
| 主要不确定性 | SPIFC 驱动 + ECC 写入方案 | flag 语义（B3）；写 boot 区 | C1 命令语义/ECC 参数 |
| 可维护性 | 好（GPL、可 CI） | 差（一次性 patch） | 好 |
| 法律 | 干净（GPLv2+ 自用 fork 可分发） | 自用可；不可分发修改版 | 干净 |
| 推荐 | 长期目标，A1 先行 | 短期目标，先做 B1 | **无条件先做** |

### 5.2 推荐路线（阶段化，每阶段独立有价值）

| 阶段 | 内容 | 写 flash | 产出 |
| --- | --- | --- | --- |
| P0 | C 工具链（mkuboot/env/patch/verify）+ 文档 | 否 | 可复现镜像与校验物 |
| P1 | 只读 OOB 取证 + vendor `nand read` 语义基线 | 否 | ECC/OOB 事实 + 可用读命令 |
| P2 | B1（env 定制，含网络启动脚本）+ 可选 B2（换密码） | 是（env/boot 区） | 短期收益：免密码、默认网络参数、开机脚本 |
| P3 | A1（RAM 链 POC，最小 U-Boot） | 否 | 「secondboot 能加载自定义 U-Boot」硬证据 |
| P4 | A2（RAM 里跑完整驱动 + 从 NAND 启动 Linux） | 否 | 驱动与槽位逻辑验证 |
| P5 | A3（刷入 + 救援演练）或保持 RAM/vendor 方案 | 是（需批准） | 长期可维护自定义引导 |

**建议**：P0–P2 立即排期（低风险见效快）；P3 作为 A 的立项门槛（零风险、信息量大）；P4/P5 视 P3 结果与用户对砖风险接受度决定。

### 5.3 各阶段验收要点

- P0：工具对原 dump 往返一致；env 解析-重生成字节相同；CI 无回归。
- P1：拿到 mtd0 前 32 KiB OOB 表；确认 ECC 段/BBM 位置；`nand read` 读回 U-Boot 区与 dump 逐字节相等。
- P2：`printenv` 可见新 env；冷启动仍正常进系统；串口日志留档。
- P3：串口出现自定义 banner → md/mtest 可用 → reset 后 vendor 链不受影响。
- P4：RAM 里的自定义 U-Boot 中 `mtd read` → `bootm` 进入 Linux。
- P5：冷启动全链 + 回滚演练各一次。

---

## 6. 风险登记

| # | 风险 | 等级 | 证据 | 缓解 |
| --- | --- | --- | --- | --- |
| R1 | 写 mtd0 U-Boot 区 ECC/OOB 不匹配 → secondboot 读 U-Boot 失败 → 真砖 | 高 | 两次 dump OOB 全 FF（手册 §6.6）；片内 ECC（patch 028/backport 436）；vendor `nand write.uboot` 的 4-bit ECC 说明 | 先 §4.4 OOB 取证；只走已验证通道；保留原 dump；A3 前把编程器回写列为条件 |
| R2 | 编程器回写方案未验证 | 高 | 手册 §6.4/§6.6 | P1 后再评估；未验证前不把编程器当保底 |
| R3 | 芯片 ID 歧义（0xCD/0xC9） | 低 | vendor 日志 manuid=cd chipid=71；backport 436 为 0xc9 | A1 打印 READID；按需照抄内核厂商条目 |
| R4 | UART 时钟/baud 未知 | 低 | `clk-zx279128s.c:504` 可 25M/100M | `CFG_PL011_CLOCK=0` 跳过设置；或实测写死 |
| R5 | secondboot 交接状态未知 | 中 | RE 未逐项确认 | A1 从最保守配置开始；串口逐段定位 |
| R6 | 封装头 +0x2D4/trailer 语义未知 | 低 | RE §2.1/§2.2；secondboot 不校验 | 原样保留 |
| R7 | U-Boot 体积超预算 | 低 | 载荷 ≤0x9F800；vendor 0x68000 | 生成器校验；裁剪配置 |
| R8 | 无主线 SoC 支持→维护成本 | 中 | U-Boot main 无 mach-zte（§1.5） | 自用 fork+静态 CI 门；不追上游 |
| R9 | vendor 升级命令误用（C2） | 高 | 语义未验证（手册 §7.2 禁用） | C1 走通前不碰 C2 |
| R10 | 法律/分发 | 低 | 见 §2.6/§3.5 | 发布只走 A；B 仅自用 |
| R11 | 设备唯一性（mtd0/mtd1 身份） | 高 | 手册 §6.6.2 第 6 条 | 所有实验限本机；不跨机写入 |

---

## 7. 后续任务拆解建议

| 编号 | 任务 | 前置 | 验收物 |
| --- | --- | --- | --- |
| K1 | kit 加 mkuboot/env/patch/verify 工具 + 离线往返测试 | 无 | 对原 dump 往返一致测试 + 工具文档 |
| K2 | mtd0 OOB 只读取证（设备会话，需批准） | K1 | OOB 表/日志 + ECC 结论入 evidence |
| K3 | vendor `nand read`/`mtddebug read` 语义基线 + READID | K2 | 读回与 dump 对拍记录 |
| E1 | env 定制（bootdelay/bootcmd/网络） | K1、K3 | printenv 前后记录 + 冷启动日志 |
| E2 | 控制台密码替换（可选） | K1、K3、批准 | 新密码可登录 + 回读校验 |
| A1 | 最小 U-Boot RAM 链 POC（串口/timer/mem，链接 0x43000000） | C1、C3 | 串口 banner 日志 + 可重复 tftp/go 步骤 |
| A2 | 加 SPIFC/SPI-NAND/env/mtd，RAM 里从 NAND 启动 Linux | A1 | mtd read+bootm 成功日志 |
| A3 | 正式镜像（链接 0x47F00000）+ 刷入 + 救援演练 | A2、K2、批准 | 冷启动全链日志 + 回滚演练记录 |
| A4 | 可选：网络/GMAC 或 bootmenu | A3 | 按需立项 |

---

## 8. 证据索引

本地：

| 事实 | 证据 |
| --- | --- |
| mtd0 布局/头块/trailer/env | [evidence/uboot-re-20261115.md](uboot-re-20261115.md) §2、§5；[docs/U-Boot结构分析-2026-11-15.md](../docs/U-Boot结构分析-2026-11-15.md) §1–§3 |
| secondboot 只查 strap+魔数、无 CRC/签名，跳 0x47F00000 | 同上 §3、§4（F_verify @0x2058D4） |
| CPU1 停车环在 secondboot | 本文 §1.2 反汇编（0x200840–0x200860；字面量 @file 0x9a4 = 0x00200800）；树 fork `files/arch/arm/mach-zte/platsmp-zx279128s.c:5-9,32,49-53` |
| vendor U-Boot 命令/help/串口日志 | `/home/qc233/zte/e2631-uboot-help.log`；手册 §4.1–§4.3 |
| env/password/upgrade/mtddebug/nand 字符串偏移 | 本文 §1.3/§3.1；mtd0 dump（`/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin`，sha256 `de4ea5bd…`） |
| 分区/芯片级偏移与 OOB 全 FF | 手册 §2.1、§6.6；`evidence/chip-level-layout-20261120.md` |
| 升级不写引导区 | `docs/architecture.md:82-83`、`tools/mkfactory.mjs:167`（`bootIncl=0`；引自手册 §0） |
| 内核 SPI/时钟/UART/timer 节点 | 树 fork `target/linux/zx279128/patches-6.18/022、023、026`；`files/drivers/spi/spi-zx.c:1-9,61,379,568-571`；`files/drivers/clk/zte/clk-zx279128s.c:249-255,281,504-510` |
| 片内 ECC/OOB 布局（8..15/16B 段，BBM 0–1） | 树 fork `patches-6.18/028-*`；IWRT backport `target/linux/generic/backport-6.18/436-v7.3-mtd-spinand-add-support-for-HeYangTek-HYF1GQ4UDACAE.patch` |
| initramfs 产物缺口 | 手册 §4.5；`.github/workflows/firmware.yml:120-124,190-199` |
| GPL 索取草稿 | `docs/gpl-request-draft-2026-11-14.md:19-22,48-55` |

上游（2026-11-21 实测）：

- U-Boot 主线 `https://github.com/u-boot/u-boot`，main @ `c1958b5f6cce03956d309ce422b5d9f819955d4a`（2026-11-19），Makefile=2027.01-rc2。
- 关键文件（main）：`drivers/mtd/nand/spi/foresee.c`（F35SQA001G 0x71/0x71）、`drivers/mtd/nand/spi/core.c`（spi-nand%d + add_mtd_device）、`env/mtd.c`、`env/Kconfig`、`include/env_internal.h:57-62,79-84`、`env/common.c:443-465`、`drivers/timer/arm_global_timer.c`、`arm_twd_timer.c`、`drivers/serial/serial_pl01x.c`、`drivers/sysreset/sysreset_syscon.c`、`cmd/mtd.c`、`cmd/Kconfig`（CMD_MTD）。

外部参考（对比用，不作为本机证据）：

- `zx297520v3-mainline/zx297520v3-loader`（Sanechips ZX297520V3 USB 下载协议；思路是「不碰 flash 启动主线 U-Boot」，与 A1 的 RAM 链验证同构）；
- `1234205a/zte-sr1010-research`（ZX279133 cspboot 引导链审计；SR1010 已有改 vendor U-Boot 的先例）；
- `Zlion-Y/e2631-mainline-zx279128s`、`cubingmucus998/zte-zx279128s-recon`、`omokas/ZX279128S-UART-Boot`（同 SoC 主线/RE 工作）；
- 博客 `blog.zlion.top/posts/zte-e2631-mainline-linux-port/`；right.com.cn 帖「中兴ZX279127S/ZX279128S rootfs CRC校验过程研究」。

---

## 9. 待验证清单（诚实）

1. `nand write.uboot` 的 <off>/<size> 语义、是否只写 U-Boot 区、写后是否自带校验（**未验证**，C1 前提）。
2. mtd0 OOB 真实内容与片内 ECC 写入方式（**未验证**，需 P1 取证）。
3. 编程器 ECC-on 模式回写 boot 区是否可行（**未验证**，唯一保底手段）。
4. 芯片真实 READID（0xCD/0xC9）与 U-Boot 驱动匹配（待 A1 打印）。
5. PL011 实际时钟（25/100 MHz）与 `CFG_PL011_CLOCK=0` 是否可靠（待 A1 实测）。
6. A9 global timer 的 a9_periph 实际频率（按 clk 驱动推 500 MHz，待 sleep 1 校准）。
7. secondboot 交接时 MMU/cache/CPU 模式与 U-Boot 通用 armv7 start.S 的兼容性（待 A1）。
8. vendor `upgrade boot` 的文件格式与是否重写 secondboot（**未验证**，暂禁用）。
9. 自定义 U-Boot 对原厂 Press 1 升级模式、cspboot 槽位选择是否有隐性影响（A 下 cspboot 被绕过，需确认 slot 头不被 U-Boot 破坏）。
10. B2 之后密码 flag（0x61F94）语义（**未确认**，不在 B 最低集合内）。

---

## 10. 方法与限制

- 「实测」= 本地文件/源码可复现，或有既有串口日志/产物；「静态」= 反汇编/字符串/源码阅读；「推断」明确标注。
- 反汇编工具 capstone 5.0.9（x86 主机无 ARM objdump），仅只读分析，脚本不落仓。
- 上游 U-Boot 事实通过 GitHub API 拉取指定 SHA 的文件核对，未依赖记忆中的版本状态。
- 未做真机操作、未编译 U-Boot/内核、未改内核或 kit 源码；§2.2 等工作量是工程估算，不是实测工期。
- 结论会随 P1/P3 实测修订；修订请在文末追加变更记录。
