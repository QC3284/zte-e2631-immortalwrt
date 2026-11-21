# E2631 自定义 U-Boot：A1 RAM 链 + A2 SPI-NAND 只读路径 + A3 槽位启动（kit 侧交付物）

本目录是 task-43/task-44/task-47/task-50/task-51/task-53 与 C1b 修复的产物：对 U-Boot 主线的 patch 系列
（0001/0002 为 A1 移植，0003 为首个 CI 构建暴露的链接修复，0004 为 A1 串口修复，0005 为 A2 的 SPIFC +
SPI-NAND 只读路径，0006/0007 为 A3 的槽位感知启动 + 只读 env，0008/0009 为 C1a 的 bootm ATAGS 修复 +
env 日志名称诊断，0010 为产品入口 0x47F00000，0011 为跳转前的 CP15 归一化，0012 为厂商 board_eth_init
的网络参考时钟/SerDes/管脚补齐）、pin 文件、四份设计说明
（[a2-spi-nand-design.md](a2-spi-nand-design.md)、[a3-slot-boot-design.md](a3-slot-boot-design.md)、
[a4-soc-state-design.md](a4-soc-state-design.md)、[a5-net-refclk-design.md](a5-net-refclk-design.md)），
以及供 CI 构建和后续真机 A1/A2/A3/C1b 会话使用的说明。
**只含代码与文档；A1/A2/A3 阶段都不写 flash。**

依据：[evidence/p2-uboot-research-20261121.md](../evidence/p2-uboot-research-20261121.md) §2（路径 A 分阶段）、
[evidence/uboot-re-20261115.md](../evidence/uboot-re-20261115.md)（mtd0 布局/偏移）、
[tools/lib/mtd0.mjs](../tools/lib/mtd0.mjs)（mtd0 地图，含本次修正的载荷边界）。

## 0. 阶段与范围

- **A1（已交付）**：纯 RAM 链 POC。ZTE 变体 PL011 控制台（0004 起）+ Cortex-A9 global timer + DRAM；由厂商 U-Boot
  控制台用 `tftp` 把镜像装到 RAM，`go` 跳转运行。断电即恢复，**零砖风险**。
- **A2（已交付）**：SPI-NAND 只读路径。SPIFC（0x94406000）PIO 驱动 + U-Boot 现成的 SPI-NAND 核心与
  FORESEE F35SQA001G 条目 + 内置 `mtd` 命令；在 RAM 链里用 `mtd list` / `mtd read` 读 flash，为 A3 的
  槽位启动打地基。只读、不写 flash；设计与风险见 [a2-spi-nand-design.md](a2-spi-nand-design.md)。
- **A3（已交付）**：槽位感知启动。在 U-Boot 内复刻 cspboot 的槽位选择（版本头内层 magic + CRC1 +
  serial），从胜出槽位的 `slot+0x20` 读出 legacy uImage 内核并用 `bootm` 启动（ATAGS 路径，内核自带
  append-dtb）；env 从厂商块 `0xC0000` 只读载入，`saveenv` 编译掉。只读、不写 flash；设计与验收见
  [a3-slot-boot-design.md](a3-slot-boot-design.md)。C1a 真机干跑暴露了 `bootm` 缺 ATAGS 缓冲区
  （`boot_prep_linux` data abort），patch 0008 修复、0009 修正 env 日志名称；重跑清单见
  [evidence/c1a-bootm-20261121.md](../evidence/c1a-bootm-20261121.md) §11。
- **不做（后续阶段）**：写 mtd0/写槽位（刷写阶段，需用户批准）、网络协议栈/网络引导（A5 只补
  PHY/SerDes 参考时钟与管脚初始化，让内核能自己接管网口与 PCIe；引导仍用厂商 U-Boot 的 tftp）、
  CPU1/SMP 交接（secondboot 已完成停车）、DDR/时钟初始化（secondboot 已完成）、时钟/复位驱动
  （依赖 secondboot 的控制器状态）、env 持久化（B1）、按活动槽位切换根文件系统。
- 引导链：BootROM → secondboot（闭源，已完成 DDR/时钟/串口/SPI-NAND/CPU1 停车）→ 厂商 U-Boot 2013.04
  →（A1/A2/A3 用 tftp+go）自定义 U-Boot。把自定义 U-Boot 写进 mtd0 0x20000..0xC0000（镜像区 0xA0000
  字节）属于之后的刷写阶段。

**载荷预算（2026-11-21 Lead 修正）**：secondboot 从 mtd0 0x20800 按封装头 +0x14 的长度拷贝载荷，
载荷区可一直用到 0xBFFFF，env 区从 0xC0000 开始。因此镜像上限为 **0x9F800 字节 = 653312 = 638 KiB**。
A1 在 RAM 里运行不受此限，但同一个二进制后续要进 mtd0，task-44 的 CI 必须提前按此上限卡住。

## 1. 基线 pin（commit / 每个 patch sha256 / 结果 tree）

| 项 | 值 |
| --- | --- |
| 仓库 / 分支 | `https://github.com/u-boot/u-boot` / `master` |
| 基线 commit | `c1958b5f6cce03956d309ce422b5d9f819955d4a`（2026-11-19，v2027.01-rc2） |
| 基线 tree | `62f07967f69e656689266ee1f3e7116cf4b5fd10` |
| patch 0001 | `uboot-port/patches/0001-arm-zx279128s-add-SoC-support.patch` |
| patch 0001 sha256 | `1e051c226bb0a5fcd44ded121c73acf03b76b7881d46aad7fd1247c19948c535` |
| patch 0002 | `uboot-port/patches/0002-board-zte-add-ZXHN-E2631-A1-support.patch` |
| patch 0002 sha256 | `71fdce39af5700bd440f87fbe1d50ce7fe97a1c2ab15a44e009d47af09250003` |
| patch 0003 | `uboot-port/patches/0003-board-zte-fix-the-A1-link.patch`（首个真实构建的链接修复） |
| patch 0003 sha256 | `d16e7b563adc8693ea59e23900870b07a168f44136218d740c3ba49e44c7b395` |
| patch 0004 | `uboot-port/patches/0004-serial-pl01x-add-the-ZTE-ZX279128S-UART-map.patch`（ZTE 变体 UART 偏移） |
| patch 0004 sha256 | `ce6a01ef5b0c1c47f213a79a30bc3bb13f0b8cdeec10ebb4395ce988b5e746ca` |
| patch 0005 | `uboot-port/patches/0005-spi-add-the-ZX279128S-SPI-flash-controller.patch`（A2：SPIFC PIO + SPI-NAND 只读） |
| patch 0005 sha256 | `43dcac25fe9c57e36898bcdbe7e4462c7bd865826bd7b72e389c7fa5d562f70f` |
| patch 0006 | `uboot-port/patches/0006-board-zte-add-slot-aware-boot.patch`（A3：`e2631boot` 槽位启动） |
| patch 0006 sha256 | `35ba682af0a5b5c71ff41c94c104a99afca609087c3bf42e4721370d6dde26ca` |
| patch 0007 | `uboot-port/patches/0007-env-mtd-load-the-vendor-environment-read-only.patch`（A3：只读 env + `env_mtd_load()` 修复） |
| patch 0007 sha256 | `bf54aa985373952cac402dafacc2b49f9876993b8150541ec13a10d94f800f97` |
| patch 0008 | `uboot-port/patches/0008-board-zte-give-bootm-a-valid-ATAGS-buffer.patch`（C1a：`bi_boot_params` 初始化 + 编译期边界断言） |
| patch 0008 sha256 | `d75f809f91f7cfcca08de5b04a6ec4c77e77df6f64c14a9f73544515a7c20748` |
| patch 0009 | `uboot-port/patches/0009-env-keep-the-location-name-when-saveenv-is-disabled.patch`（env 名称诊断，独立可回退） |
| patch 0009 sha256 | `4bf75d5afe821f0e58dce01c88fa326a3adf4a33c708f5d7c4712d243ad14e91` |
| patch 0010 | `uboot-port/patches/0010-zx279128s-link-the-image-at-the-0x47F00000-boot-entry.patch`（task-55：链接到产品入口 `0x47F00000`） |
| patch 0010 sha256 | `57ce9d808cc771854bb68b03020d9da854d24b0bd621b5971b882e342ff079a0` |
| patch 0011 | `uboot-port/patches/0011-board-zte-normalise-CP15-before-the-Linux-hand-off.patch`（C1b-1：入口归一化 + 跳转前 CP15 清理 + `e2631soc` 只读报告） |
| patch 0011 sha256 | `98aa4b3914ff1741e0621116b4d630ab43f448d7d0ca31496c2001e815b51095` |
| patch 0012 | `uboot-port/patches/0012-board-zte-bring-up-the-network-reference-clocks.patch`（A5：厂商 board_eth_init 的参考时钟/SerDes/管脚序列，按两链 pre/post 寄存器差分裁剪 + `e2631refclk` 前后 dump） |
| patch 0012 sha256 | `9c075c60f5cd6282e8b507d7ee0e02b4fc68544d0f55f4d1b4c43a8f187ed87b` |
| am 之后 tree | `3f1eeb4941ada08255f7bd4b5c936d6a1a3750f4`（与机器无关，12 个 patch） |
| TEXT_BASE | `0x47F00000` |
| 载荷上限 | `0x9F800` 字节 |

以上值同 [uboot-port/commits.env](commits.env)；CI 必须按"commit → 每个 patch sha256 → 结果 tree"三段校验，
补丁数量由 `uboot-port/patches/` 目录决定，不写死。

最省带宽的取基线方式（只取一个 SHA）：

```sh
mkdir u-boot && cd u-boot
git init -q .
git remote add origin https://github.com/u-boot/u-boot.git
git fetch -q --depth 1 origin c1958b5f6cce03956d309ce422b5d9f819955d4a
git -c advice.detachedHead=false checkout -q FETCH_HEAD
git -c user.name=ci -c user.email=ci@localhost am ../uboot-port/patches/*.patch
test "$(git rev-parse HEAD^{tree})" = 3f1eeb4941ada08255f7bd4b5c936d6a1a3750f4
```

## 2. 新增/修改的文件

| 文件 | 作用 |
| --- | --- |
| `arch/arm/Kconfig` | 新增 `ARCH_ZX279128`（select CPU_V7A），source mach Kconfig |
| `arch/arm/Makefile` | `machine-$(CONFIG_ARCH_ZX279128) += zx279128s` |
| `arch/arm/mach-zx279128s/Kconfig` | `SYS_SOC="zx279128s"`、`TARGET_ZXHN_E2631`、source 板级 Kconfig |
| `arch/arm/mach-zx279128s/Makefile` | A1 无 SoC 私有代码（secondboot 已完成初始化），只留占位说明 |
| `board/zte/zxhn-e2631/Kconfig` | `SYS_BOARD`/`SYS_VENDOR`/`SYS_CONFIG_NAME` |
| `board/zte/zxhn-e2631/Makefile` | 编译 `zxhn-e2631.o`、`e2631boot.o`（A3）、`e2631soc.o`（C1b）与 `e2631net.o`（A5） |
| `board/zte/zxhn-e2631/e2631boot.c` | A3：`e2631boot` 命令（槽位扫描/选择/uImage 校验/`bootm`）+ `board_late_init()` 覆盖 `bootcmd`；C1b：`bootm` 前调用 `e2631_soc_prepare_linux()`；A5：`bootm` 前调用 `e2631_net_refclk_init()` |
| `board/zte/zxhn-e2631/e2631soc.c` | C1b：厂商顺序的 CP15 清理 + `e2631soc` 只读报告命令（SCTLR/CLIDR/TTBR0/VBAR/ACTLR 前后值；不启动、不写 flash/env） |
| `board/zte/zxhn-e2631/e2631soc.h` | `e2631_soc_prepare_linux()` 原型（`e2631boot.c` 与 `e2631soc.c` 共用一条代码路径） |
| `board/zte/zxhn-e2631/e2631net.c` | A5：厂商 `board_eth_init()` 的参考时钟/SerDes/CRM2/管脚序列（pinmux 六个整字、只驱动八个输出、`0x9400000C` 的 `bits[21:20]` 时钟选择）+ `e2631refclk` 前后 dump 命令（不启动、不写 flash/env） |
| `board/zte/zxhn-e2631/e2631net.h` | `e2631_net_refclk_init()` 原型（`e2631boot.c` 与 `e2631net.c` 共用一条代码路径） |
| `board/zte/zxhn-e2631/zxhn-e2631.c` | `dram_init`/`dram_init_banksize` 从内嵌 DT 读 256 MiB |
| `board/zte/zxhn-e2631/MAINTAINERS` | 维护者与文件范围 |
| `include/configs/zx279128s_zte_zxhn-e2631.h` | `CFG_SYS_SDRAM_BASE=0x40000000`、`CFG_PL011_CLOCK=0`、`CFG_SYS_HZ_CLOCK=500000000` |
| `arch/arm/dts/zx279128s-zte-zxhn-e2631.dts` | memory / PL011 / A9 global timer / 500 MHz fixed-clock |
| `arch/arm/dts/Makefile` | `dtb-$(CONFIG_TARGET_ZXHN_E2631) += zx279128s-zte-zxhn-e2631.dtb` |
| `configs/zx279128s_zte_zxhn-e2631_defconfig` | A1/A2/A3 配置（已用 `make savedefconfig` 归一；A3 增加 `BOARD_LATE_INIT`/`SUPPORT_PASSING_ATAGS`/`ENV_IS_IN_MTD` 与只读 env 参数；0011 移除 `CONFIG_SKIP_LOWLEVEL_INIT`，让标准 `cpu_init_cp15`/`cpu_init_crit` 在入口重新生效） |

补丁 0003（2026-11-21，task-44 首个真实构建暴露）：只改 2 个文件——defconfig 增加
`# CONFIG_DISPLAY_CPUINFO is not set`、`# CONFIG_BOARD_INIT is not set`（A1 没有 DM CPU 驱动、
也没有板级 chip select），板级文件补 `reset_cpu()` 占位实现（A1 无复位控制器，打印提示后返回）。
它不改基线、不改 TEXT_BASE，也不改载荷上限。

补丁 0004（2026-11-21，task-47 真机 A1 验收阻塞修复）：A1 的 UART0 是 **ZTE 变体 PL011**，寄存器偏移与
ARM 标准不同（DR 0x04、FR 0x14、LCRH 0x30、CR 0x34；无 error clear 寄存器，TXFF/RXFE 位不变）。
它给 `drivers/serial/serial_pl01x.c` 增加 `TYPE_PL011_ZTE` 与 `zte,zx29-uart` compatible（按变体选偏移），
DT 的 uart0 从 `arm,pl011` 切到该 compatible；不改基线、TEXT_BASE、载荷上限与 defconfig
（`CONFIG_PL01X_SERIAL=y` 仍然编译该驱动）。此前 probe 往标准 CR 偏移写使能位，而 ZTE 真正的 CR(0x34)
从未被写，镜像能执行但串口全程静默（见 [evidence/a1-ramchain-poc-20261121.md](../evidence/a1-ramchain-poc-20261121.md) §7/§9）。

补丁 0005（2026-11-21，task-50，A2）：新增 5 个文件变更——`drivers/spi/spi-zx.c`（PIO-only SPIFC 驱动，
仅实现 spi-mem 的 `exec_op`/`supports_op`/`adjust_op_size`；DMA/IRQ/reset/时钟初始化不搬，时钟可选）、
`drivers/spi/Kconfig` 的 `SPI_ZX`、`drivers/spi/Makefile` 一行、DTS 的 `spi@94406000` + `flash@0`
（`zte,zx279128s-spifc` / `spi-nand`）、defconfig 的
`CONFIG_SPI/DM_SPI/SPI_ZX/MTD/DM_MTD/MTD_SPI_NAND/CMD_MTD`。不改基线、TEXT_BASE、载荷上限；寄存器表、
ECC-on-read 决策与风险见 [a2-spi-nand-design.md](a2-spi-nand-design.md)。A2 不写 flash。

补丁 0006（2026-11-21，task-51，A3）：新增 `board/zte/zxhn-e2631/e2631boot.c`（330 行）并接入板级
`Makefile`；defconfig 增加 `CONFIG_BOARD_LATE_INIT`、`CONFIG_SUPPORT_PASSING_ATAGS`（`bootm` 走
ATAGS），`CONFIG_BOOTCOMMAND` 改为 `e2631boot`。命令只读：扫描两槽版本头（内层 magic + CRC1）、
按 cspboot 的 serial 规则选槽、校验并载入 `slot+0x20` 的 legacy uImage、`bootm`；`board_late_init()`
只在 RAM 内把 `bootcmd` 指向它（载入的厂商 `bootcmd` 不改，也不写 flash）。

补丁 0007（2026-11-21，task-51，A3）：`ENV_IS_IN_MTD` 读厂商 env 块（`0xC0000`/`0x20000`，格式与
`env_t` 逐字节兼容），`CONFIG_CMD_SAVEENV` 编译掉（A3 不能写 env）。同时修上游 `env/mtd.c` 的
`env_mtd_load()`：`setup_mtd_device()` 失败时 `mtd_env` 未初始化却仍被 `put_mtd_device()` 解引用，
SPI-NAND 缺失会在提示符前 panic；改为 `mtd_env = NULL` + `if (mtd_env)`。

补丁 0008（2026-11-21，task-53，C1a pre-flash blocker）：只改 `board/zte/zxhn-e2631/e2631boot.c`。
真机 A3 干跑执行 `bootm` 时在 `boot_prep_linux() + 0x74` 发生 data abort（写 ATAG_MEM 的
`str r0,[r1,#4]`，`r1=0x967fc480` 在 DRAM 之外）：移植板级代码从未给 `gd->bd->bi_boot_params`
赋值，而 `bd_info` 在 `reserve_board()` 里被清零、本配置又没开 `CONFIG_SYS_MALLOC_BOOTPARAMS`，
所以 ATAGS 缓冲区指针不是合法 DRAM 地址。patch 在 `board_late_init()`（早于 autoboot/bootm）里把
`bi_boot_params` 指向 `CFG_SYS_SDRAM_BASE + 0x100`，并用两条 `static_assert` 把该窗口钉在 DRAM
base 之上、内核 load 地址 `0x40008000` 之下：将来改常量会在编译期失败而不是在启动时 crash。
ATAGS 只需 44 字节（CORE + 一个 MEM tag + END，`CONFIG_SETUP_MEMORY_TAGS=y`、其余 tag 全关），
预留 0x100 字节；该窗口与内核（0x40008000）、uImage staging（0x42000000）、重定位后的 U-Boot
（0x4ff…）都不冲突。内核本身走 append-dtb（`CONFIG_ARM_APPENDED_DTB=y`、`CONFIG_ATAG_DTB_COMPAT`
未开、`CONFIG_CMDLINE_FORCE=y`），但 `bootm` 必须先写完 ATAGS 才能进入内核。

补丁 0009（2026-11-21，task-53，诊断）：只改 `include/env_internal.h`。`ENV_NAME()` 原本只在
`CONFIG_CMD_SAVEENV` 打开时才定义 `.name`，而 A3 把 `saveenv` 编译掉，于是 `env_load()` 打印
`Loading Environment from <NULL>... OK`——C1a 因此误判“env-mtd 未生效”。源码分析（`env/env.c:172-230`
只在 `drv->load()` 返回 0 时打印 OK；`env/mtd.c:142-199` 的 `env_mtd_load()` 成功才会返回 0）证明
厂商 env 块实际已从 `0xC0000` 载入成功；0009 让名称无条件定义，日志变成
`Loading Environment from MTD... OK`。此 patch 与启动逻辑无关，可单独回退。

补丁 0010（2026-11-21，task-55）：只改 defconfig 的一行（`CONFIG_TEXT_BASE` 从 `0x43000000` 改为
`0x47F00000`），不重写 0001/0002 的源补丁，也不打开 `CONFIG_POSITION_INDEPENDENT`（非 PIE 的修正量假设
运行地址 == 链接地址，入口必须等于链接地址）。RAM 链与产品链地址统一为 `0x47F00000`；证据见
[evidence/uboot-47f-20261121.md](../evidence/uboot-47f-20261121.md)。

补丁 0011（2026-11-21，C1b-1 修复）：defconfig 移除 `CONFIG_SKIP_LOWLEVEL_INIT`（标准入口归一化重新
生效；`lowlevel_init`/`s_init` 仍是空弱符号，不做时钟/DRAM/UART），并新增
`board/zte/zxhn-e2631/e2631soc.c|.h`：`e2631_soc_prepare_linux()` 在 `e2631boot` 的 `bootm` 前执行厂商
`cleanup_before_linux()`（`0x47f00534`）顺序的 CP15 清理（纯内联汇编，不依赖 `SYS_*CACHE_OFF` 桩）；
`e2631soc` 命令跑同一函数并打印 CP15 前后 dumps。厂商逆向证明其在内核前不做 PL310/SCU/ACTLR/时钟
初始化，所以本补丁不写这些寄存器（只读打印）。根因、逆向证据与 A/B 验收见
[a4-soc-state-design.md](a4-soc-state-design.md) 与
[evidence/p2-flashboot-kernel-hang-20261121.md](../evidence/p2-flashboot-kernel-hang-20261121.md)。

补丁 0012（2026-11-22，A5，C1b-1 之后的第二个 flash 链缺口）：新增 `board/zte/zxhn-e2631/e2631net.c|.h`，
在 `e2631boot` 解析完参数、真正要 `bootm` 前调用 `e2631_net_refclk_init()`，按厂商 `board_eth_init()`
（`0x47f00850`）的逐字段顺序补齐闪存链从未执行的板级初始化：分数 PLL（`0x94000050/0x54`）、
`0x94000008` 的 bit4/bit5 时序、`0x9FE00000` 的 25 次 SerDes 表写、CRM2 `0x94100010` 的参考时钟选择、
`0x9400004C` + `0x9A100004`、`0x9400000C` 的 `bits[21:20]=0b01`（厂商以太网 probe 选择的时钟 mux），
以及 `0x94200000` pinmux 与 GPIO 输出。寄存器集按两链 pre/post 差分裁剪过：pinmux 不只做三处 `|=`，
而是按厂商 `zte_gpio_init` 的顺序先 OR 再写入板级表的六个整字（`0x0f3ffffa`、`0x00effeff`、`0x0555ffff`、
`0x003dbf85`、0、0）；18 项 GPIO 里十个输入在复位后 DIR 已为 0、与厂商写入结果相同，故只驱动八个输出
（8=1、40=1、60=0、55=0、52=0、54=0、51=0、2=0）。`e2631refclk` 命令跑同一函数，打印 7 个寄存器的前后值后返回提示符，不启动、不写 flash/env。厂商不做的事（网络协议栈、PCIe host、
PHY 驱动）仍归内核；flat GPIO 53（H3600 时期的 `pcie0 reset-gpios` 猜测）不在厂商表里，故意不驱动。
设计与真机验收签名见 [a5-net-refclk-design.md](a5-net-refclk-design.md) 与
[evidence/p2-vendorless-network-gap-20261122.md](../evidence/p2-vendorless-network-gap-20261122.md)。

## 3. 关键设计参数

| 项 | 值 / 决定 | 说明 |
| --- | --- | --- |
| `TEXT_BASE` | `0x47F00000` | 产品入口：secondboot 把载荷 memcpy 到 `0x47F00000` 后 `blx` 跳入（逆向证据 [evidence/uboot-re-20261115.md](../evidence/uboot-re-20261115.md)）。A1/A2/A3 RAM 链也使用这个地址（厂商 U-Boot 已把自己重定位到 DRAM 顶部，其链接区空闲，见 §5）。移植**不是位置无关**（`CONFIG_POSITION_INDEPENDENT` 未开，`relocate.S` 的修正量假设运行地址 == 链接地址），所以入口必须等于链接地址，改地址必须重编 |
| 初始栈 | `CONFIG_CUSTOM_SYS_INIT_SP_ADDR=0x48000000` | 256 MiB DRAM 中段，远离镜像与重定位目标（重定位在 DRAM 顶部附近） |
| DRAM | `0x40000000` + 256 MiB | secondboot 完成 DDR 初始化；板级只知道大小，不做 DDR init |
| UART0 | ZTE 变体 PL011 @ `0x94404000`，115200 8N1 | compatible `zte,zx29-uart` 选择 ZTE 偏移表（DR 0x04 / FR 0x14 / LCRH 0x30 / CR 0x34；IBRD/FBRD 0x24/0x28 与标准相同）。`CFG_PL011_CLOCK=0`：输入时钟未知，**跳过 IBRD/FBRD 设置**，沿用 secondboot 的 115200；DT 里故意不写 `clock` 属性 |
| Timer | A9 global timer @ `0x800200` | DT `fixed-clock` a9_periph = 500 MHz（CPU 1 GHz / 2）；`CFG_SYS_HZ_CLOCK` 作为 DT 查询失败的回退 |
| Cache/MMU | U-Boot 自身全关，交接状态显式归一化 | `SYS_ICACHE_OFF`/`SYS_DCACHE_OFF`/`SYS_L2CACHE_OFF` 保留（U-Boot 自己不用 cache/MMU）；但 0011 起入口不再跳过 `cpu_init_cp15`/`cpu_init_crit`，且 `bootm` 前执行厂商顺序的 CP15 清理，不再把 secondboot 的 cache/MMU 状态直接交给内核 |
| 入口 CP15 归一化 | `CONFIG_SKIP_LOWLEVEL_INIT` 关闭（0011 起） | 标准 `cpu_init_cp15` 在 `_start` 里 invalidate L1 I/D、TLB、BP，I-cache 开、D-cache/MMU 关；`cpu_init_crit` 只跳空的弱符号 `lowlevel_init`/`s_init`，不做时钟/DRAM/UART。与厂商 `cpu_init_crit 0x47f0021c` 的效果一致 |
| 跳转前 CP15 清理 | `e2631_soc_prepare_linux()`（0011） | `e2631boot` 在 `bootm` 前调用；执行厂商 `cleanup_before_linux()`（`0x47f00534`）的顺序：I-cache 关、ICIALLU+BPIALL+DSB+ISB、D clean+invalidate by set/way（若 SCTLR.C 开）、清 SCTLR.M/C、D invalidate by set/way。纯内联汇编，不依赖 `SYS_*CACHE_OFF` 桩；厂商不做 PL310/SCU/ACTLR 初始化，本实现也不写这些寄存器。`e2631soc` 跑同一函数并打印 SCTLR/CLIDR/TTBR0/VBAR/ACTLR/DACR/CCSIDR 前后值（md 读不到 CP15）与只读的 PL310/SCU 状态，不启动 |
| env | `ENV_IS_IN_MTD`（只读） | A3 从厂商块 `0xC0000`/`0x20000` 只读载入（格式与 `env_t` 逐字节兼容）；`saveenv` 编掉；持久化策略（bootdelay/旁路变量）留给 B1；0009 起日志名称显示为 `MTD`（此前 `<NULL>` 只是 `CMD_SAVEENV` 关闭后 `.name` 没定义，不代表未生效） |
| 槽位启动 | `e2631boot`（A3） | 扫描两槽每 128 KiB 块找版本头（内层 magic + CRC1），serial 大者胜出（`slot0.serial==0` 也按小处理）；从 `slot+0x20` 读 uImage 到 `0x42000000` 后 `bootm`；ATAGS + 内核 append-dtb |
| ATAGS 缓冲区 | `CFG_SYS_SDRAM_BASE + 0x100`（= `0x40000100`） | 0008 在 `board_late_init()` 设置 `gd->bd->bi_boot_params`；`static_assert` 保证 > DRAM base 且 +0x100 ≤ 内核 load `0x40008000`；本配置 `SYS_MALLOC_BOOTPARAMS` 关闭，没有其它代码分配该缓冲区 |
| 设备树 | `OF_EMBED` | DTB 内嵌进 `u-boot.bin`，`go` 跳转无需外部 DTB；后续再考虑分离/追加格式 |
| SPI-NAND | 只读（A2，0005） | SPIFC PIO + U-Boot SPI-NAND 核心 + FORESEE F35SQA001G + `mtd` 读；不写 flash、不碰 env |
| 网络参考时钟/SerDes | `e2631_net_refclk_init()`（0012） | 厂商 `board_eth_init()` 的逐字段重放：分数 PLL `0x94000050/0x54`（第二寄存器先清 bit27/25/24、置 bit26，再以高字节保留的方式写 FRAC）、`0x94000008` bit4/bit5、`0x9FE00000` SerDes 25 写、CRM2 `0x94100010`、`0x9400004C`→`0x9A100004`、`0x9400000C` 的 `bits[21:20]=0b01`（厂商以太网 probe 的时钟 mux，两链 dump 证明不同）；内核 clk 驱动假设 bootloader 已完成该初始化，且无内核驱动碰这些寄存器（DTS 无法描述）。`e2631refclk` 打印前后 7 个寄存器，不启动 |
| Pinmux / GPIO | `0x94200000` + 厂商板级表（0012） | pinmux 先三处 |= 厂商值，再按厂商顺序写入板级表六个整字；GPIO 只驱动八个输出（8=1/40=1/60=0 三色 LED、55/52/54/51/2=0），十个输入（strap 5/15/62/61/43/47/46/45、按键 18/20）复位后 DIR 已为 0，无需写；不驱动 flat 53。全部为板上外设的“回到厂商上电状态”，幂等 |
| 网络协议栈 | 无 | 网络引导仍用厂商 U-Boot 的 tftp；A5 只让内核能自己接管 PHY/PCIe |
| 刷写 | 不做 | A3 只读；写 mtd0/槽位属于之后的刷写阶段（需用户批准） |
| CPU1/SRAM | 不碰 | secondboot 已把 CPU1 停在 `wfe` → SRAM `0x200800` 循环；内核 platsmp 依赖该约定，U-Boot 不得改写 SRAM |

### 启动流程（A1）

1. BootROM 读 secondboot；secondboot 初始化 DDR/时钟/串口/SPI-NAND，停 CPU1，然后加载厂商 U-Boot。
2. 厂商 U-Boot 控制台（串口 115200）执行 `tftp 0x47F00000 u-boot.bin`、`go 0x47F00000`。
3. 自定义 U-Boot 从 `0x47F00000` 起步（`_start` 向量表第一条就是 `b reset`），打印 banner，
   从内嵌 DTB 取 256 MiB DRAM，PL011 沿用 115200，timer 用 500 MHz global timer。
4. `bdinfo` 应显示 DRAM 256 MiB、入口/重定位信息；`md.l 0x94404000 4` 可读 PL011 寄存器；
   `mtest` 可在镜像与栈之外的区间跑内存测试。
5. 断电或 `reset` 回到厂商 U-Boot；**全程不写 flash**。

## 4. 构建（task-44 在 CI 执行；本机不编译，硬规则）

```sh
# 依赖（ubuntu-24.04）
sudo apt-get update
sudo apt-get install -y build-essential bison flex device-tree-compiler python3 swig libssl-dev

# 取基线 + 应用 patch（见 §1），然后：
make O=build zx279128s_zte_zxhn-e2631_defconfig
make O=build -j"$(nproc)"
```

产物：`build/u-boot.bin`（本配置 OF_EMBED，DTB 内嵌）、`build/.config`、`build/u-boot.map`。

### CI 验收断言（task-44 必须实现）

1. `git rev-parse HEAD^{tree}` == `3f1eeb4941ada08255f7bd4b5c936d6a1a3750f4`；每个 patch 的 sha256 与 §1 一致，
   且 `git rev-list --count <baseline>..HEAD` 等于 patch 数量（当前 12）。
2. `.config` 精确包含：`CONFIG_ARCH_ZX279128=y`、`CONFIG_TARGET_ZXHN_E2631=y`、
   `CONFIG_TEXT_BASE=0x47F00000`、`CONFIG_OF_EMBED=y`、`CONFIG_ARM_GLOBAL_TIMER=y`、
   `CONFIG_TIMER=y`、`CONFIG_PL01X_SERIAL=y`、`CONFIG_DM_SERIAL=y`、`CONFIG_CLK=y`、
   `CONFIG_SPI=y`、`CONFIG_DM_SPI=y`、`CONFIG_SPI_ZX=y`、`CONFIG_MTD=y`、`CONFIG_DM_MTD=y`、
   `CONFIG_MTD_SPI_NAND=y`、`CONFIG_CMD_MTD=y`；0011 起还要求 `# CONFIG_SKIP_LOWLEVEL_INIT is not set`
   （入口归一化不能再次被跳过）。
3. 镜像尺寸：`size=$(stat -c%s build/u-boot.bin); test "$size" -le 653312`
   （超限就裁命令/驱动；这条对应 mtd0 载荷上限 0x9F800，是刷写阶段的硬前置）。
4. 入口点：`readelf -h build/u-boot` 的 Entry point 应为 `0x47F00000`（readelf 打印小写 `0x47f00000`，CI 统一转小写比较）。
5. 上传 CI artifact：`u-boot.bin`、`u-boot.map`、`.config`、构建日志；记录 run URL。
6. checkpatch（可选，见 §6）：`git format-patch c1958b5f..HEAD` 后跑
   `u-boot/scripts/checkpatch.pl --no-tree`，本系列 **0 errors / 11 reviewed warnings**（0011 与 0012 各
   0 errors / 2 warnings：新建文件缺 MAINTAINERS 更新、新增自用板级命令，均为已核对项）。
7. 内嵌 DTB 的 uart0 compatible 是 `zte,zx29-uart`：`grep -aq 'zte,zx29-uart' build/u-boot.bin`
   （OF_EMBED 把 DTB 打进镜像）。少了这条，构建会通过但 A1 串口仍然静默，正是 task-45 的故障模式。
8. 内嵌 DTB 的 SPI 节点：`grep -aq 'zte,zx279128s-spifc' build/u-boot.bin` 且
   `grep -aq 'spi-nand' build/u-boot.bin`（A2 的控制器/芯片节点；防止 DTS 或 defconfig 被误删而
   构建仍通过）。
9. A3 配置：`CONFIG_BOARD_LATE_INIT=y`、`CONFIG_SUPPORT_PASSING_ATAGS=y`、
   `CONFIG_SETUP_MEMORY_TAGS=y`、`CONFIG_BOOTCOMMAND="e2631boot"`、`CONFIG_ENV_IS_IN_MTD=y`、
   `CONFIG_ENV_MTD_DEV="spi-nand0"`、`CONFIG_ENV_OFFSET=0xc0000`、`CONFIG_ENV_SIZE=0x20000`；
   并且 `# CONFIG_CMD_SAVEENV is not set`（A3 不能写 env）、`CONFIG_ENV_IS_NOWHERE` 未启用。
10. A3/C1b/A5 二进制：`grep -aq 'e2631boot' build/u-boot.bin`、`grep -aq 'e2631soc' build/u-boot.bin`、
    `grep -aq 'e2631refclk' build/u-boot.bin` 且 `grep -aq 'spi-nand0' build/u-boot.bin`（槽位命令、
    CP15 报告命令、网络时钟报告命令与 env 设备名确实链接进镜像）。
11. A3/C1a/C1b/A5 修复（0008/0009/0011/0012）：`grep -q 'bi_boot_params' board/zte/zxhn-e2631/e2631boot.c`、
    `grep -q 'define ENV_NAME(_name) .name = _name,' include/env_internal.h`、
    `grep -q 'e2631_soc_prepare_linux' board/zte/zxhn-e2631/e2631boot.c`、
    `grep -q 'mcr p15' board/zte/zxhn-e2631/e2631soc.c`、
    `grep -q 'e2631_net_refclk_init' board/zte/zxhn-e2631/e2631boot.c`，且 `e2631net.c` 仍含厂商值
    `0x004fdf3b`、`0x003c0040`、`0x0001381b`、板级 pinmux 字 `0x0f3ffffa`、`0x003dbf85` 与 `0x9400000C` 的 `0x00100000`。形状断言只防回归；编译由 CI 保证，运行期
    （bootm 进内核、env 日志显示 MTD、CP15 前后差值、网络时钟前后差值）由 C1a/C1b 重跑与 Session A 的
    `e2631soc`/`e2631refclk` 输出保证。
12. A5 内核侧成功签名（真机会话记录，不是 CI 断言）：MDIO 地址 10-13 的四个 PHY 出现且 link up；
    `lspci` 出现 `14c3:7906`（bus0）与 `14c3:790a`（bus1）；`br-lan` 有 PHY。详见
    [a5-net-refclk-design.md](a5-net-refclk-design.md) §5。

## 5. A1 真机步骤（需用户批准；只读/纯 RAM，不写 flash）

前置：串口线接 UART0（115200 8N1），进入厂商 U-Boot 控制台（控制台密码见救砖手册）。
A1 会话只允许 `tftp`/`go`/`md`/`mtest`/`reset` 一类命令；**禁止任何 `nand write*`、`mtddebug write`、
`upgrade`、`saveenv`**（这些是刷写阶段才讨论的写通道）。

1. 在主机上起 TFTP 服务，把 CI 的 `u-boot.bin` 放到根目录。
2. 厂商控制台：`tftp 0x47F00000 u-boot.bin`（确认 "Bytes transferred" 与文件大小一致）。
   厂商 U-Boot 启动后已把自己重定位到 DRAM 顶部，`0x47F00000` 处是它放弃的链接映像，
   因此向该地址下载不会破坏正在运行的厂商代码（`bdinfo` 的 relocation offset 可佐证）。
3. `go 0x47F00000`。
4. 预期串口出现 U-Boot banner（版本 v2027.01-rc2 代）、`Model: ZTE ZXHN E2631 (ZX279128S)`、
   `DRAM: 256 MiB`、`Core: ARMv7`，随后是 `=>` 提示符（defconfig 的 `CONFIG_SYS_PROMPT`）与
   `bdinfo` 输出。
5. 验证：`bdinfo`（DRAM/重定位）、`md.l 0x800200 8`（global timer 计数在走）、`mtest`（安全区间）、
   `reset` 或断电后应能正常回到厂商 U-Boot。
6. 记录完整串口日志（含 tftp 大小、banner、bdinfo、md、mtest 结果）作为 A1 验收证据，落盘到
   evidence/ 并汇报 Lead。

失败定位顺序：无任何输出 → 先确认镜像是 0004 之后（compatible `zte,zx29-uart` 选中 ZTE 偏移表），
再确认 115200 与接线；banner 后异常 → cache/MMU 交接或
timer fixed-clock 假设；`go` 立即返回/复位 → 入口地址或镜像是否完整传输。

### A2 真机读路径检查（后续会话，需用户批准；只读、不写 flash）

装载方式与 A1 相同（`tftp 0x47F00000 u-boot.bin` + `go 0x47F00000`），之后**只允许读命令**：

1. `mtd list`：应出现 `spi-nand0`，大小 128 MiB、页 2048、OOB 64。
2. `mtd read spi-nand0 0x42000000 0 0x800`，再 `md.b 0x42000000 0x40`，与已知 mtd0 头 dump 逐字节对比。
3. 读 slot 头（偏移见 [evidence/chip-level-layout-20261120.md](../evidence/chip-level-layout-20261120.md)）验证；
   内核 MTD 与 U-Boot 读同一区域应一致（片内 ECC 都开，见设计说明 §6）。
4. 若 `mtd list` 没有设备或 FIFO 超时：先 `md.l 0x94406000 8` 看 EN/VER 回读并记录完整日志，再按
   [设计说明](a2-spi-nand-design.md) §9 的"时钟/门控 → 采样点 → 引脚复用"顺序定位。
5. **禁止** `mtd write`/`mtd erase`/`nand write`/`saveenv`；刷写阶段之前不讨论写 flash。

### A3 只读验收（本次交付；需用户批准；只读、不写 flash）

装载方式同 A1/A2（`tftp 0x47F00000 u-boot.bin` + `go 0x47F00000`）。启动后 `board_late_init()` 会把
`bootcmd` 指向 `e2631boot`，3 s 后自动执行；也可在提示符下手动跑只读子命令：

0. 先在提示符跑 `e2631soc`（0011 起）：一次运行打印 before/after 的 SCTLR（含 M/C/I 位）、CLIDR、TTBR0、
   VBAR、ACTLR、DACR、CCSIDR 与只读的 PL310/SCU 状态（md 读不到 CP15）；它不启动、不写 flash，也不写 env。
   C1b-1 的现场判定以这组前后差值为准，随后 `e2631boot` 会走同一函数（幂等）。
0.1 再跑 `e2631refclk`（0012 起）：两行 before、两行 after，覆盖 `0x94000050/0x54`、`0x94000008`、
   `0x94100010`、`0x9400004C`、`0x9A100004` 与 `0x9400000C`；记录前后差值（真机 A5 验收的第一手数据），
   它同样不启动、不写 flash/env，随后 `e2631boot` 会走同一函数（幂等）。
1. `e2631boot info`：打印两槽的版本头偏移、serial、version，以及 `cspboot would boot slotN`。当前
   设备应显示 slot0（serial 7、`V1.0.0.7B5.8000`、头在 `0x1C60000`）与 slot1（serial 12、头在
   `0x1500000`，C1a 实测值），结论 slot1。
2. `e2631boot load`：校验 `slot+0x20` 的 uImage（magic/type/os/comp/hcrc/size/dcrc），打印名称、
   load/entry、大小与 CRC 结论，并载入到 `0x42000000` 但**不 boot**。
3. 与 A2 的 `mtd read spi-nand0 ...` 对照 slot1 版本头字节；两次读取应一致。
4. `e2631boot` 走完整 `bootm`（C1a 重跑必需，不再可选）：串口必须依次出现
   `Loading Kernel Image to 40008000` →（不再有 data abort）→ ImmortalWrt 内核启动。0008 之前这里
   固定 data abort 在 `boot_prep_linux`；0008 之后应能进入内核（C1a 只读、不写 flash）。
5. env 检查：启动日志应是 `Loading Environment from MTD... OK`（0009 之前为 `<NULL>`）；`printenv`
   应显示厂商 env 的值（`bootdelay=3`、厂商 `bootcmd`、`ethaddr`/`ipaddr`/`memsize` 等——这些值不在
   编译期默认 env 里，是 env-mtd 真正生效的运行期证据）；当前生效的 `bootcmd` 已被 RAM 内改成
   `e2631boot`；`saveenv` 命令不存在（已编掉）。
6. **禁止** `mtd write`/`mtd erase`/`nand write`/`saveenv`；A3 不写 flash、不持久化 env。

失败定位：`e2631boot: spi-nand0 is not available` → 先回到 A2 的 `mtd list`；`no valid version
header` → 用 `mtd read` 直接 dump 槽头核对偏移/CRC；`bootm` 报 “FDT and ATAGS support not compiled
in” → defconfig 的 `CONFIG_SUPPORT_PASSING_ATAGS` 丢了。

## 6. 已知限制与风险

- **交接状态已显式归一化，但入口配置改动影响所有链**：0011 起 `CONFIG_SKIP_LOWLEVEL_INIT` 关闭并增加
  `bootm` 前 CP15 清理，语义对齐厂商路径；代价是 RAM 链（厂商 `go`）也会多跑一次入口归一化，需要 C1b-0
  的 RAM 链验收先确认 banner/`e2631boot` 不受影响，再谈 flash 写。若真机异常，先用 `e2631soc` 的前后
  dumps 定位是入口段还是清理段。
- **UART 是 ZTE 变体**（0004 起按 `zte,zx29-uart` 选 ZTE 偏移表）：若串口仍无输出，先核对 DT compatible
  与 patch 是否齐全，再查接线/波特率；输入时钟仍未知，暂用 `CFG_PL011_CLOCK=0` 跳过波特率设置，若乱码，
  下一步从 lsp0crpm/实测反推（25 MHz / 100 MHz 候选）再改 DT 或头文件。
- **timer 500 MHz 是假设**（a9_periph = CPU/2，A9 1 GHz）；真机用 `sleep 1` 对照秒表校准，必要时修正。
- **A1/A2 无 env/网络/bootm**：这是有意的阶段边界，不是缺陷。A2 只加 SPI-NAND 读路径；A3 加
  只读 env 与 `bootm`，但仍不写 flash、不写 env。
- **A2 的控制器时钟/门控状态未知**：DT 故意不写 `clocks`（U-Boot 没有 ZX CRPM 时钟驱动），probe 只做
  EN/EN_BACK 与采样点；这是 A2 最大不确定项，真机先看 `md.l 0x94406000 8`，必要时在后续阶段补最小
  CRPM 时钟驱动。
  详见 [a2-spi-nand-design.md](a2-spi-nand-design.md) §9。
- **A1 的 `reset` 命令不做复位**：没有复位控制器驱动，`reset` 只打印提示并返回；需要复位时用
  厂商 U-Boot 的 `reset` 或断电。厂商控制台本身仍可正常复位，后续阶段再补复位路径。
- **A5 网络时钟是“重放厂商值”，不是自己配时钟**：0012 写 `0x94000050/0x54`、`0x94000008`、`0x94100010`、
  `0x9400004C`、`0x9A100004`、`0x9FE00000`、pinmux 六个整字与 GPIO 输出，全部逐字段等于厂商
  `board_eth_init()`/`zte_gpio_init()`；`0x9400000C` 的 `bits[21:20]` 来自厂商以太网 probe（board_eth_init
  之后），两链 dump 显示它确实不同，所以也一并重放。寄存器集按两链 pre/post 差分裁剪：留下“值确实不同或
  pre 状态不可读”的项，丢掉输入 GPIO 与两链已经相同的 CRM2 写；未 dump 到的 `0x94100024` 等不写。
  内核 clk 驱动不会重编程这些 PLL，因此值必须保持厂商语义。若真机 PHY 仍不应答或 PCIe 不枚举，先在 U-Boot
  里跑 `e2631refclk` 看 7 个寄存器的 before/after，再与厂商日志（`Net: enter ref_clk_set..` 到 `eth0`）
  对照；回退只需删掉 `e2631boot.c` 里那一行调用（不影响启动链其余部分）。风险面只在 E2631 板型，
  0012 不碰 SoC 通用代码。
- **入口必须等于链接地址（非 PIE）**：`TEXT_BASE=0x47F00000` 对齐 secondboot 的固定入口；
  U-Boot 未开 `CONFIG_POSITION_INDEPENDENT`，`relocate.S` 的修正量假设运行地址 == 链接地址，
  从其它地址进入会在 banner 之前挂死或 data abort；改地址只能改 defconfig 后重编，不能只改 `go`。
- **载荷 0x9F800**：刷写阶段封装/写 mtd0 前必须满足；secondboot 封装头其它字节（+0x2D4 摘要等）在
  刷写阶段必须原样保留。
- **checkpatch**：本系列 0 errors、11 reviewed warnings（0008/0009 各自 0 errors / 0 warnings；0011 与
  0012 各 0 errors / 2 warnings），均为已核对的已知项——6 条 "does MAINTAINERS
  need updating?"（patch 0001 新建 `arch/arm/mach-zx279128s/`、patch 0002 新建 `board/zte/zxhn-e2631/`、
  patch 0005 新建 `drivers/spi/spi-zx.c`、patch 0006 新增 `board/zte/zxhn-e2631/e2631boot.c`、
  patch 0011 新增 `e2631soc.c|.h`、patch 0012 新增 `e2631net.c|.h` 各一条；checkpatch 按单 patch 看不到
  后续 patch 的 MAINTAINERS 更新）+ 2 条 "Use the livetree API"
  （板级 `fdtdec_setup_mem_size_base()`/`fdtdec_setup_memory_banksize()` 是 U-Boot 板级读 /memory 的
  常规 API，checkpatch 的 LIVETREE 检查对板级代码是误报）+ 3 条 "Possible new command - make sure you
  add a test"（`e2631boot`/`e2631soc`/`e2631refclk` 是自用板级命令，U-Boot 树里没有对应 DM 测试；
  验收是只读子命令 + 真机会话，不新增测试目录）。自用 fork，不提交上游。
- 本机不编译（硬规则）；编译证据只能来自 task-44 的 CI run。

## 7. 与后续阶段的关系

- **A2**：SPIFC + SPI-NAND 只读路径已由 patch 0005 交付（RAM 链内 `mtd list`/`mtd read`）。芯片 ID
  实测为 `0xCD/0x71`，用现成 FORESEE `F35SQA001G` 条目（若出现 `0xC9` 再加 heyangtek 条目）。
- **A3**：槽位感知启动已由 patch 0006/0007 交付（`e2631boot` + 只读 env）。`TEXT_BASE` 已在 task-55 对齐
  secondboot 入口 `0x47F00000`；C1b 的 CP15 归一化由 0011 交付（`e2631soc` + bootm 钩子）。剩下的 env
  持久化（B1）、按活动槽位切换根文件系统放在后续会话。
- **A5**：厂商 `board_eth_init()` 的参考时钟/SerDes/管脚初始化由 patch 0012 交付（`e2631refclk` 前后 dump +
  `e2631boot` 钩子）。内核侧签名（PHY 10-13 + PCIe `14c3:7906`/`14c3:790a`）由下一次零写入真机会话记录；
  网络协议栈/网络引导不在本阶段。
- **刷写阶段（原计划的 A3，重命名为 A4/路径 C）**：写 mtd0 U-Boot 区/写槽位；需要 OOB/ECC 取证、
  写通道验证、回滚演练与用户批准。在此之前，A1/A2/A3 都不写 flash。
- **A1 真机会话**在 task-44 的 CI 产物可用之后进行（用户已批准 RAM 链 POC）。

## 8. 变更记录

- 2026-11-21（task-43）：A1 最小移植的两个 patch、三重 pin（commits.env）与本说明；
- 2026-11-21（task-44）：新增 patch 0003（链接修复：reset_cpu/print_cpuinfo/board_init），
  重钉结果 tree 为 `abab1858bfee030bfdbc18bc227189a6e8ba5d83`；CI workflow `uboot-build.yml`；
  TEXT_BASE=0x43000000（RAM 链）、PL011 `CFG_PL011_CLOCK=0`、A9 global timer fixed-clock、
  载荷上限按修正后的 0x9F800 记录；
- 2026-11-21（task-44 收口）：CI run `44869143179` 绿（head `f1bd383`，12/12 步），artifact
  `e2631-uboot-a1-44869143179`（7 文件，含 `.config`），u-boot.bin sha256
  `a3771aca6144879701d5336ae032a6d242fab3e1c90a80dbea0710a6816679b3`、347,640 B；
  证据见 [evidence/uboot-ci-build-20261121.md](../evidence/uboot-ci-build-20261121.md)。
- 2026-11-21（task-47）：新增 patch 0004（ZTE 变体 PL011 偏移表 + `zte,zx29-uart` compatible），
  重钉结果 tree 为 `418ae89f09b34238daf37d0db78b4485001ffc2c`；根因与 A/B 探针证据见
  [evidence/a1-ramchain-poc-20261121.md](../evidence/a1-ramchain-poc-20261121.md) §7-§9。
- 2026-11-21（task-50）：新增 patch 0005（SPIFC PIO 驱动 + DTS/defconfig 的 SPI-NAND）；重钉结果 tree 为
  `4cfd4a4fd3db0dc34aa46155370562323f58e90d`，设计/ECC/风险见 [a2-spi-nand-design.md](a2-spi-nand-design.md)；
  A2 仍不写 flash。
- 2026-11-21（task-51）：新增 patch 0006（`e2631boot` 槽位感知启动 + ATAGS `bootm`）与 patch 0007
  （`ENV_IS_IN_MTD` 只读厂商 env + `env_mtd_load()` 空指针修复），defconfig 增加 `BOARD_LATE_INIT`/
  `SUPPORT_PASSING_ATAGS`/`ENV_IS_IN_MTD` 并把 `CONFIG_BOOTCOMMAND` 改为 `e2631boot`；重钉结果
  tree 为 `40f52fb46d9987d8082babac151f9f8dcbdcba4a`（7 个 patch）。设计见
  [a3-slot-boot-design.md](a3-slot-boot-design.md)；A3 仍不写 flash、不写 env。
- 2026-11-21（task-53）：新增 patch 0008（C1a：`board_late_init()` 设置
  `gd->bd->bi_boot_params = 0x40000100` + 两条编译期边界断言）与 patch 0009（`ENV_NAME` 无条件定义，
  env 日志从 `<NULL>` 变为 `MTD`）；重钉结果 tree 为
  `aed6c5b700f2a7e405088572c216e2ca23a04996`（9 个 patch）。C1a 重跑清单见
  [evidence/c1a-bootm-20261121.md](../evidence/c1a-bootm-20261121.md) §11。CI run
  `44892376502`（head `67d7eda`）绿：post-am 9 commits / tree 校验通过、checkpatch 0 errors /
  7 reviewed warnings、`u-boot.bin` 448,096 B（上限 653,312）、entry `0x43000000`、artifact
  `e2631-uboot-44892376502`；`u-boot.bin` sha256
  `2c90fc558dd8e35f50c887040cd25e00f98325e13e35422de1bc52d056de3eb3`，mtd0 镜像 sha256
  `f1021b9d64e0ba79bcfc0f89383bebe84980c482b165398b773961e871ba4617`。
- 2026-11-21（C1a 重跑 PASS）：verify-docs 用 task-53 产物完成零写入 `bootm` 干跑并通过——banner
  `U-Boot 2027.01-rc2-gb74974862b8d`、`Loading Environment from MTD... OK`（0009 生效）、`bootm`
  进入内核且无 `data abort`/`prefetch abort`（0008 生效）、slot1 选中、内核 6.18.60 起用户态、
  `mtd0` sha256 前后一致（`887a7f6c…0fa9f`）。记录见
  [evidence/c1a-bootm-20261121.md](../evidence/c1a-bootm-20261121.md) §0.1/§11.4（kit 提交
  `5817fb5`，check.yml run `44896218551` 绿）。C1b（写 mtd0）仍冻结，等 Lead 与用户最终 go。
- 2026-11-21（task-55）：新增 patch 0010（defconfig 的 `CONFIG_TEXT_BASE` 从 `0x43000000` 改为
  `0x47F00000`，对齐 secondboot 的 `blx 0x47F00000` 产品入口；不写源补丁、不开
  `CONFIG_POSITION_INDEPENDENT`）。重钉结果 tree 为
  `1444b0319baa9a850389e6573f4d2d7a24d9a025`（10 个 patch）；RAM 链文档地址全部改为
  `0x47F00000`。旧 `0x43000000` 的 A1/A2/A3/C1a 证据只对应旧产物；新产物的验收是 C1b-0
  会话（装 `0x47F00000` → `go` → banner → autoboot → Linux）。CI run `44898534408`
  （head `7835289`）绿：10 patches / tree 校验通过、checkpatch 0 errors / 7 reviewed
  warnings、`u-boot.bin` 448,112 B、entry `0x47f00000`、banner
  `U-Boot 2027.01-rc2-g2797f3dd3860`；artifact `e2631-uboot-44898534408`，`u-boot.bin`
  sha256 `010379fde3496fdcbbe835c249cff2bd79234f946918266721e098dd64479f75`，mtd0 镜像
  sha256 `baf28b6da4d6ca1b356389951b9d49765382b35dd382bc81c8a0a589c09464dd`。证据见
  [evidence/uboot-47f-20261121.md](../evidence/uboot-47f-20261121.md)。
- 2026-11-21（C1b-1 修复，patch 0011）：新增 `board/zte/zxhn-e2631/e2631soc.c|.h`（厂商顺序 CP15 清理、
  CP15 前后 dumps、`e2631soc` 命令）并从 defconfig 移除 `CONFIG_SKIP_LOWLEVEL_INIT`；重钉结果 tree 为
  `c8914654a4787fdc67c30bea44de5d70d39e8fdc`（11 个 patch）。设计见
  [a4-soc-state-design.md](a4-soc-state-design.md)。CI run `44921033410`（head `270707b`）SUCCESS：banner
  `g6f5036fa039d`、`u-boot.bin` 449,240 B sha256 `bef0d841bc26e2dc9db4484e26285d23d8d3bf9e1a63ad81f080c28b026206f4`、
  mtd0 镜像 sha256 `83457522357bc4d55f4a36d3dd912ff9184c31dad754cec3dff3a9d1f7c2412e`、env 块 `6eee153b…` 未变；
  详见 [evidence/uboot-cp15-cleanup-20261121.md](../evidence/uboot-cp15-cleanup-20261121.md)。
- 2026-11-22（A5，patch 0012）：新增 `board/zte/zxhn-e2631/e2631net.c|.h` 与 `e2631refclk` 命令，按厂商
  `board_eth_init()` 重放参考时钟/SerDes/CRM2/管脚序列，并在 `e2631boot` 的 `bootm` 前调用；寄存器集按 verify-docs 两链 pre/post 寄存器差分裁剪（pinmux 六个整字、只驱动 GPIO 输出、补 `0x9400000C`），重钉结果 tree 为
  `3f1eeb4941ada08255f7bd4b5c936d6a1a3750f4`（12 个 patch）。设计见
  [a5-net-refclk-design.md](a5-net-refclk-design.md)；厂商逆向证据见
  [evidence/p2-vendorless-network-gap-20261122.md](../evidence/p2-vendorless-network-gap-20261122.md)。
  CI run `44928690737`（head `e377498`）SUCCESS：banner `gdd251a1a3390`、`u-boot.bin` 450,888 B
  sha256 `4da8a821659b85b40a08cde1f123ed4c39e46fbdf1b2487b2efde16a4ca11f0a`、mtd0 镜像
  sha256 `0128c7bbdaefc033cc049079ef3948e6b3a14bf2826c1d1b52df9b78ca0aeba1`、env 块 `6eee153b…` 未变；
  详见 [evidence/uboot-a5-20261122.md](../evidence/uboot-a5-20261122.md)。
