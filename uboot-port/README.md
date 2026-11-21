# E2631 自定义 U-Boot：A1 RAM 链 + A2 SPI-NAND 只读路径 + A3 槽位启动（kit 侧交付物）

本目录是 task-43/task-44/task-47/task-50/task-51 的产物：对 U-Boot 主线的 patch 系列（0001/0002 为
A1 移植，0003 为首个 CI 构建暴露的链接修复，0004 为 A1 串口修复，0005 为 A2 的 SPIFC + SPI-NAND 只读
路径，0006/0007 为 A3 的槽位感知启动 + 只读 env）、pin 文件、两份设计说明
（[a2-spi-nand-design.md](a2-spi-nand-design.md)、[a3-slot-boot-design.md](a3-slot-boot-design.md)），
以及供 task-44/task-48（CI 构建）和后续真机 A1/A2/A3 会话使用的说明。
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
- **A3（本次交付）**：槽位感知启动。在 U-Boot 内复刻 cspboot 的槽位选择（版本头内层 magic + CRC1 +
  serial），从胜出槽位的 `slot+0x20` 读出 legacy uImage 内核并用 `bootm` 启动（ATAGS 路径，内核自带
  append-dtb）；env 从厂商块 `0xC0000` 只读载入，`saveenv` 编译掉。只读、不写 flash；设计与验收见
  [a3-slot-boot-design.md](a3-slot-boot-design.md)。
- **不做（后续阶段）**：写 mtd0/写槽位（刷写阶段，需用户批准）、网络、CPU1/SMP 交接（secondboot 已
  完成停车）、DDR/时钟初始化（secondboot 已完成）、时钟/复位驱动（依赖 secondboot 的控制器状态）、
  env 持久化（B1）、按活动槽位切换根文件系统。
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
| am 之后 tree | `40f52fb46d9987d8082babac151f9f8dcbdcba4a`（与机器无关，7 个 patch） |
| TEXT_BASE | `0x43000000` |
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
test "$(git rev-parse HEAD^{tree})" = 40f52fb46d9987d8082babac151f9f8dcbdcba4a
```

## 2. 新增/修改的文件

| 文件 | 作用 |
| --- | --- |
| `arch/arm/Kconfig` | 新增 `ARCH_ZX279128`（select CPU_V7A），source mach Kconfig |
| `arch/arm/Makefile` | `machine-$(CONFIG_ARCH_ZX279128) += zx279128s` |
| `arch/arm/mach-zx279128s/Kconfig` | `SYS_SOC="zx279128s"`、`TARGET_ZXHN_E2631`、source 板级 Kconfig |
| `arch/arm/mach-zx279128s/Makefile` | A1 无 SoC 私有代码（secondboot 已完成初始化），只留占位说明 |
| `board/zte/zxhn-e2631/Kconfig` | `SYS_BOARD`/`SYS_VENDOR`/`SYS_CONFIG_NAME` |
| `board/zte/zxhn-e2631/Makefile` | 编译 `zxhn-e2631.o` 与 `e2631boot.o`（A3） |
| `board/zte/zxhn-e2631/e2631boot.c` | A3：`e2631boot` 命令（槽位扫描/选择/uImage 校验/`bootm`）+ `board_late_init()` 覆盖 `bootcmd` |
| `board/zte/zxhn-e2631/zxhn-e2631.c` | `dram_init`/`dram_init_banksize` 从内嵌 DT 读 256 MiB |
| `board/zte/zxhn-e2631/MAINTAINERS` | 维护者与文件范围 |
| `include/configs/zx279128s_zte_zxhn-e2631.h` | `CFG_SYS_SDRAM_BASE=0x40000000`、`CFG_PL011_CLOCK=0`、`CFG_SYS_HZ_CLOCK=500000000` |
| `arch/arm/dts/zx279128s-zte-zxhn-e2631.dts` | memory / PL011 / A9 global timer / 500 MHz fixed-clock |
| `arch/arm/dts/Makefile` | `dtb-$(CONFIG_TARGET_ZXHN_E2631) += zx279128s-zte-zxhn-e2631.dtb` |
| `configs/zx279128s_zte_zxhn-e2631_defconfig` | A1/A2/A3 配置（已用 `make savedefconfig` 归一；A3 增加 `BOARD_LATE_INIT`/`SUPPORT_PASSING_ATAGS`/`ENV_IS_IN_MTD` 与只读 env 参数） |

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

## 3. 关键设计参数

| 项 | 值 / 决定 | 说明 |
| --- | --- | --- |
| `TEXT_BASE` | `0x43000000` | **只用于 A1/A2 RAM 链**：厂商 U-Boot `tftp 0x43000000` + `go 0x43000000`。产品/A3 仍由 secondboot 装到 `0x47F00000`，那时改 TEXT_BASE 后重编 |
| 初始栈 | `CONFIG_CUSTOM_SYS_INIT_SP_ADDR=0x48000000` | 256 MiB DRAM 中段，远离镜像与重定位目标（重定位在 DRAM 顶部附近） |
| DRAM | `0x40000000` + 256 MiB | secondboot 完成 DDR 初始化；板级只知道大小，不做 DDR init |
| UART0 | ZTE 变体 PL011 @ `0x94404000`，115200 8N1 | compatible `zte,zx29-uart` 选择 ZTE 偏移表（DR 0x04 / FR 0x14 / LCRH 0x30 / CR 0x34；IBRD/FBRD 0x24/0x28 与标准相同）。`CFG_PL011_CLOCK=0`：输入时钟未知，**跳过 IBRD/FBRD 设置**，沿用 secondboot 的 115200；DT 里故意不写 `clock` 属性 |
| Timer | A9 global timer @ `0x800200` | DT `fixed-clock` a9_periph = 500 MHz（CPU 1 GHz / 2）；`CFG_SYS_HZ_CLOCK` 作为 DT 查询失败的回退 |
| Cache/MMU | 全关 | `SYS_ICACHE_OFF`/`SYS_DCACHE_OFF`/`SYS_L2CACHE_OFF`：secondboot→vendor U-Boot→`go` 的交接状态（MMU/cache/CPU 模式）未知，A1 用最保守配置 |
| env | `ENV_IS_IN_MTD`（只读） | A3 从厂商块 `0xC0000`/`0x20000` 只读载入（格式与 `env_t` 逐字节兼容）；`saveenv` 编掉；持久化策略（bootdelay/旁路变量）留给 B1 |
| 槽位启动 | `e2631boot`（A3） | 扫描两槽每 128 KiB 块找版本头（内层 magic + CRC1），serial 大者胜出（`slot0.serial==0` 也按小处理）；从 `slot+0x20` 读 uImage 到 `0x42000000` 后 `bootm`；ATAGS + 内核 append-dtb |
| 设备树 | `OF_EMBED` | DTB 内嵌进 `u-boot.bin`，`go` 跳转无需外部 DTB；后续再考虑分离/追加格式 |
| SPI-NAND | 只读（A2，0005） | SPIFC PIO + U-Boot SPI-NAND 核心 + FORESEE F35SQA001G + `mtd` 读；不写 flash、不碰 env |
| 网络 | 无 | 网络引导仍用厂商 U-Boot 的 tftp |
| 刷写 | 不做 | A3 只读；写 mtd0/槽位属于之后的刷写阶段（需用户批准） |
| CPU1/SRAM | 不碰 | secondboot 已把 CPU1 停在 `wfe` → SRAM `0x200800` 循环；内核 platsmp 依赖该约定，U-Boot 不得改写 SRAM |

### 启动流程（A1）

1. BootROM 读 secondboot；secondboot 初始化 DDR/时钟/串口/SPI-NAND，停 CPU1，然后加载厂商 U-Boot。
2. 厂商 U-Boot 控制台（串口 115200）执行 `tftp 0x43000000 u-boot.bin`、`go 0x43000000`。
3. 自定义 U-Boot 从 `0x43000000` 起步（`_start` 向量表第一条就是 `b reset`），打印 banner，
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

1. `git rev-parse HEAD^{tree}` == `40f52fb46d9987d8082babac151f9f8dcbdcba4a`；每个 patch 的 sha256 与 §1 一致，
   且 `git rev-list --count <baseline>..HEAD` 等于 patch 数量（当前 7）。
2. `.config` 精确包含：`CONFIG_ARCH_ZX279128=y`、`CONFIG_TARGET_ZXHN_E2631=y`、
   `CONFIG_TEXT_BASE=0x43000000`、`CONFIG_OF_EMBED=y`、`CONFIG_ARM_GLOBAL_TIMER=y`、
   `CONFIG_TIMER=y`、`CONFIG_PL01X_SERIAL=y`、`CONFIG_DM_SERIAL=y`、`CONFIG_CLK=y`、
   `CONFIG_SPI=y`、`CONFIG_DM_SPI=y`、`CONFIG_SPI_ZX=y`、`CONFIG_MTD=y`、`CONFIG_DM_MTD=y`、
   `CONFIG_MTD_SPI_NAND=y`、`CONFIG_CMD_MTD=y`。
3. 镜像尺寸：`size=$(stat -c%s build/u-boot.bin); test "$size" -le 653312`
   （超限就裁命令/驱动；这条对应 mtd0 载荷上限 0x9F800，是刷写阶段的硬前置）。
4. 入口点：`readelf -h build/u-boot` 的 Entry point 应为 `0x43000000`。
5. 上传 CI artifact：`u-boot.bin`、`u-boot.map`、`.config`、构建日志；记录 run URL。
6. checkpatch（可选，见 §6）：`git format-patch c1958b5f..HEAD` 后跑
   `u-boot/scripts/checkpatch.pl --no-tree`，本系列 **0 errors / 7 reviewed warnings**。
7. 内嵌 DTB 的 uart0 compatible 是 `zte,zx29-uart`：`grep -aq 'zte,zx29-uart' build/u-boot.bin`
   （OF_EMBED 把 DTB 打进镜像）。少了这条，构建会通过但 A1 串口仍然静默，正是 task-45 的故障模式。
8. 内嵌 DTB 的 SPI 节点：`grep -aq 'zte,zx279128s-spifc' build/u-boot.bin` 且
   `grep -aq 'spi-nand' build/u-boot.bin`（A2 的控制器/芯片节点；防止 DTS 或 defconfig 被误删而
   构建仍通过）。
9. A3 配置：`CONFIG_BOARD_LATE_INIT=y`、`CONFIG_SUPPORT_PASSING_ATAGS=y`、
   `CONFIG_SETUP_MEMORY_TAGS=y`、`CONFIG_BOOTCOMMAND="e2631boot"`、`CONFIG_ENV_IS_IN_MTD=y`、
   `CONFIG_ENV_MTD_DEV="spi-nand0"`、`CONFIG_ENV_OFFSET=0xc0000`、`CONFIG_ENV_SIZE=0x20000`；
   并且 `# CONFIG_CMD_SAVEENV is not set`（A3 不能写 env）、`CONFIG_ENV_IS_NOWHERE` 未启用。
10. A3 二进制：`grep -aq 'e2631boot' build/u-boot.bin` 且 `grep -aq 'spi-nand0' build/u-boot.bin`
    （槽位命令与 env 设备名确实链接进镜像）。

## 5. A1 真机步骤（需用户批准；只读/纯 RAM，不写 flash）

前置：串口线接 UART0（115200 8N1），进入厂商 U-Boot 控制台（控制台密码见救砖手册）。
A1 会话只允许 `tftp`/`go`/`md`/`mtest`/`reset` 一类命令；**禁止任何 `nand write*`、`mtddebug write`、
`upgrade`、`saveenv`**（这些是刷写阶段才讨论的写通道）。

1. 在主机上起 TFTP 服务，把 CI 的 `u-boot.bin` 放到根目录。
2. 厂商控制台：`tftp 0x43000000 u-boot.bin`（确认 "Bytes transferred" 与文件大小一致）。
3. `go 0x43000000`。
4. 预期串口出现 U-Boot banner（版本 v2027.01-rc2 代）、`Model: ZTE ZXHN E2631 (ZX279128S)`、
   `DRAM: 256 MiB`、`Core: ARMv7`，随后是 `E2631>` 提示符与 `bdinfo` 输出。
5. 验证：`bdinfo`（DRAM/重定位）、`md.l 0x800200 8`（global timer 计数在走）、`mtest`（安全区间）、
   `reset` 或断电后应能正常回到厂商 U-Boot。
6. 记录完整串口日志（含 tftp 大小、banner、bdinfo、md、mtest 结果）作为 A1 验收证据，落盘到
   evidence/ 并汇报 Lead。

失败定位顺序：无任何输出 → 先确认镜像是 0004 之后（compatible `zte,zx29-uart` 选中 ZTE 偏移表），
再确认 115200 与接线；banner 后异常 → cache/MMU 交接或
timer fixed-clock 假设；`go` 立即返回/复位 → 入口地址或镜像是否完整传输。

### A2 真机读路径检查（后续会话，需用户批准；只读、不写 flash）

装载方式与 A1 相同（`tftp 0x43000000 u-boot.bin` + `go 0x43000000`），之后**只允许读命令**：

1. `mtd list`：应出现 `spi-nand0`，大小 128 MiB、页 2048、OOB 64。
2. `mtd read spi-nand0 0x42000000 0 0x800`，再 `md.b 0x42000000 0x40`，与已知 mtd0 头 dump 逐字节对比。
3. 读 slot 头（偏移见 [evidence/chip-level-layout-20261120.md](../evidence/chip-level-layout-20261120.md)）验证；
   内核 MTD 与 U-Boot 读同一区域应一致（片内 ECC 都开，见设计说明 §6）。
4. 若 `mtd list` 没有设备或 FIFO 超时：先 `md.l 0x94406000 8` 看 EN/VER 回读并记录完整日志，再按
   [设计说明](a2-spi-nand-design.md) §9 的"时钟/门控 → 采样点 → 引脚复用"顺序定位。
5. **禁止** `mtd write`/`mtd erase`/`nand write`/`saveenv`；刷写阶段之前不讨论写 flash。

### A3 只读验收（本次交付；需用户批准；只读、不写 flash）

装载方式同 A1/A2（`tftp 0x43000000 u-boot.bin` + `go 0x43000000`）。启动后 `board_late_init()` 会把
`bootcmd` 指向 `e2631boot`，3 s 后自动执行；也可在提示符下手动跑只读子命令：

1. `e2631boot info`：打印两槽的版本头偏移、serial、version，以及 `cspboot would boot slotN`。当前
   设备应显示 slot0（serial 7、`V1.0.0.7B5.8000`、头在 `0x1C60000`）与 slot1（serial 11、头在
   `0x1500000`），结论 slot1。
2. `e2631boot load`：校验 `slot+0x20` 的 uImage（magic/type/os/comp/hcrc/size/dcrc），打印名称、
   load/entry、大小与 CRC 结论，并载入到 `0x42000000` 但**不 boot**。
3. 与 A2 的 `mtd read spi-nand0 ...` 对照 slot1 版本头字节；两次读取应一致。
4. （可选）直接 `e2631boot` 走完整 `bootm`：串口应看到 ImmortalWrt 内核启动。
5. env 检查：`printenv` 应显示厂商 env 的值（`bootdelay=3`、厂商 `bootcmd` 等），但当前生效的
   `bootcmd` 已被 RAM 内改成 `e2631boot`；`saveenv` 命令不存在（已编掉）。
6. **禁止** `mtd write`/`mtd erase`/`nand write`/`saveenv`；A3 不写 flash、不持久化 env。

失败定位：`e2631boot: spi-nand0 is not available` → 先回到 A2 的 `mtd list`；`no valid version
header` → 用 `mtd read` 直接 dump 槽头核对偏移/CRC；`bootm` 报 “FDT and ATAGS support not compiled
in” → defconfig 的 `CONFIG_SUPPORT_PASSING_ATAGS` 丢了。

## 6. 已知限制与风险

- **交接状态未知**（MMU/cache/CPU 模式）：A1 全关 cache/MMU、`SKIP_LOWLEVEL_INIT`，从最保守状态开始；
  若真机异常，优先怀疑这里。
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
- **载荷 0x9F800**：刷写阶段封装/写 mtd0 前必须满足；secondboot 封装头其它字节（+0x2D4 摘要等）在
  刷写阶段必须原样保留。
- **checkpatch**：本系列 0 errors、7 reviewed warnings，均为已核对的已知项——4 条 "does MAINTAINERS
  need updating?"（patch 0001 新建 `arch/arm/mach-zx279128s/`、patch 0002 新建 `board/zte/zxhn-e2631/`、
  patch 0005 新建 `drivers/spi/spi-zx.c`、patch 0006 新增 `board/zte/zxhn-e2631/e2631boot.c` 各一条；
  checkpatch 按单 patch 看不到后续 patch 的 MAINTAINERS 更新）+ 2 条 "Use the livetree API"
  （板级 `fdtdec_setup_mem_size_base()`/`fdtdec_setup_memory_banksize()` 是 U-Boot 板级读 /memory 的
  常规 API，checkpatch 的 LIVETREE 检查对板级代码是误报）+ 1 条 "Possible new command - make sure you
  add a test"（`e2631boot` 是自用板级命令，U-Boot 树里没有对应 DM 测试；A3 验收是只读子命令 + 真机
  会话，不新增测试目录）。自用 fork，不提交上游。
- 本机不编译（硬规则）；编译证据只能来自 task-44 的 CI run。

## 7. 与后续阶段的关系

- **A2**：SPIFC + SPI-NAND 只读路径已由 patch 0005 交付（RAM 链内 `mtd list`/`mtd read`）。芯片 ID
  实测为 `0xCD/0x71`，用现成 FORESEE `F35SQA001G` 条目（若出现 `0xC9` 再加 heyangtek 条目）。
- **A3**：槽位感知启动已由 patch 0006/0007 交付（`e2631boot` + 只读 env）。剩下的 `TEXT_BASE` 改回
  secondboot 装载地址 `0x47F00000`、env 持久化（B1）、按活动槽位切换根文件系统放在后续会话。
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
