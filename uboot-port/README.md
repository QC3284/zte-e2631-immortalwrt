# E2631 自定义 U-Boot：A1 RAM 链 + A2 SPI-NAND 只读路径 + A3 槽位启动（kit 侧交付物）

本目录是 task-43/task-44/task-47/task-50/task-51/task-53 与 C1b 修复的产物：对 U-Boot 主线的 patch 系列
（0001/0002 为 A1 移植，0003 为首个 CI 构建暴露的链接修复，0004 为 A1 串口修复，0005 为 A2 的 SPIFC +
SPI-NAND 只读路径，0006/0007 为 A3 的槽位感知启动 + 只读 env，0008/0009 为 C1a 的 bootm ATAGS 修复 +
env 日志名称诊断，0010 为产品入口 0x47F00000，0011 为跳转前的 CP15 归一化，0012 为厂商 board_eth_init
的网络参考时钟/SerDes/管脚补齐，0013 为厂商在板级表回放后补驱动的两根 GPIO（PCIe 端点复位/供电线），0014 为自更新命令 `e2631flash`/`e2631verify`/`e2631slot`（flash 源先经 1 MiB bounce buffer 暂存，payload 与 readback 各打印 CRC32），0015 为 `CONFIG_CMD_MTD_WRITE` 开关（我们的 defconfig 关掉它，`e2631flash` 成为镜像里唯一的 MTD 写入口），0016 为 class-1 跨槽回退（选中槽 uImage 校验失败时自动改启另一槽一次，只回退本次启动、不写 flash/env），0017 为 `e2631env` 环境写回（白名单 + 厂商键快照 + 坏块预检/擦除/全 FF/写入/回读五步），0018/0019/0020 为 E2 U-Boot 以太网（MDIO 总线 + 交换机/流量管理器/DMA 初始化 + datapath 驱动与 `e2631net` 调试命令；固定 16 MiB DMA arena，单口 lan1），0021/0022 为 checkpatch 收口（新增一段 MAINTAINERS 条目覆盖板级/SoC/驱动/DTS/defconfig/命令文档，新增 `doc/usage/cmd/e2631net.rst` 用法页；两个 patch 都不含代码改动）、
pin 文件、设计说明
（[a2-spi-nand-design.md](a2-spi-nand-design.md)、[a3-slot-boot-design.md](a3-slot-boot-design.md)、
[a4-soc-state-design.md](a4-soc-state-design.md)、[a5-net-refclk-design.md](a5-net-refclk-design.md)、
[a6-pcie-endpoint-reset-design.md](a6-pcie-endpoint-reset-design.md)、
[e2-net-driver-design.md](e2-net-driver-design.md)、
[a7-self-flash-design.md](a7-self-flash-design.md)、
[docs/U-Boot-env写回与启动计数设计-2026-11-22.md](../docs/U-Boot-env写回与启动计数设计-2026-11-22.md)），
以及供 CI 构建和后续真机 A1/A2/A3/C1b 会话使用的说明。
**只含代码与文档；A1/A2/A3/A5/A6 阶段都不写 flash；D-U1 的写命令只在用户批准的刷写会话里使用。**

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
- **E2（已交付，0018/0019/0020）**：U-Boot 自己的以太网驱动。为四个集成 PHY 加 clause-22 MDIO 总线，
  复用内核驱动的交换机/流量管理器/DMA 初始化（16 MiB arena），把 lan1（switch port 2、PHY 12）接进 U-Boot
  网络栈，提供 `e2631net` 状态命令。目录里的验收命令是 `mii info` / `dhcp` / `ping` / `tftp`（见 §5.4）；
  单口、无中断轮询、不做 autoboot rescue（E3），第一次真机会话另行安排。
- **不做（后续阶段）**：真正写 mtd0/写槽位（D-U1 的写命令已交付，但刷写会话仍需用户批准并先零写入校验）、
  U-Boot 的 autoboot rescue/网络引导回退（E3；E2 只把网口接进 U-Boot 网络栈）、
  CPU1/SMP 交接（secondboot 已完成停车）、DDR/时钟初始化（secondboot 已完成）、时钟/复位驱动
  （依赖 secondboot 的控制器状态）、env 持久化（B1）、按活动槽位切换根文件系统。
- 引导链：BootROM → secondboot（闭源，已完成 DDR/时钟/串口/SPI-NAND/CPU1 停车）→ 厂商 U-Boot 2013.04
  →（A1/A2/A3 用 tftp+go）自定义 U-Boot。把自定义 U-Boot 写进 mtd0 0x20000..0xC0000（镜像区 0xA0000
  字节）由 D-U1 的 `e2631flash` 负责（先零写入校验暂存镜像，再单独一次写入；需用户批准）。

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
| patch 0013 | `uboot-port/patches/0013-board-zte-drive-the-two-late-GPIO-lines-high.patch`（A6：厂商 `zte_gpio_init()` 尾部两根特例 GPIO，pin 2 置 1 → `mdelay(4)` → pin 51 置 1；保留厂商 4 ms 间隔） |
| patch 0013 sha256 | `f6d52c559973dad5cc4e375f72e7dd3ce57b63c8b15f1ca95e5bb011346d5f2c` |
| patch 0014 | `uboot-port/patches/0014-board-zte-add-self-contained-flash-and-verify-commands.patch`（D-U1：`e2631flash`/`e2631verify`/`e2631slot`；flash→flash 源经 `0x44000000` 的 1 MiB bounce buffer 暂存） |
| patch 0014 sha256 | `0bfb4302fec14b6d0d2549cebe4a1ddf311bd50f044849d0bdaf09c1ed943110` |
| patch 0015 | `uboot-port/patches/0015-cmd-mtd-gate-write-and-erase-behind-CMD_MTD_WRITE.patch`（`CONFIG_CMD_MTD_WRITE` 默认 y，本 defconfig 关闭；原始 `mtd write/erase` 子命令编掉） |
| patch 0015 sha256 | `84bfc65f5bb335d5a6d33b93ccfb8e367e210d0af155ddc6ab82eb14fa6c8f3b` |
| patch 0016 | `uboot-port/patches/0016-board-zte-fall-back-to-the-other-slot-on-a-bad-uImage.patch`（class-1 跨槽回退：选中槽 uImage 任一级校验失败时改启另一槽一次） |
| patch 0016 sha256 | `7838e8a22dd46996c9ccb31f9fe116e194641d2a26f548e9854548bfefc62461` |
| patch 0017 | `uboot-port/patches/0017-board-zte-add-a-whitelisted-environment-writer.patch`（U-0017：`e2631env check/diff/save`，唯一 env 写入口，五步安全写 + 白名单 + 厂商键快照） |
| patch 0017 sha256 | `da21478e0fe7c53fdf14f59e81ea3da86733b63998926f25e84b3675f96eca0d` |
| patch 0018 | `uboot-port/patches/0018-drivers-net-add-the-ZX279128S-MDIO-controller.patch`（E2：clause-22 MDIO 总线 + 共享寄存器头 `zx279128s_eth.h`） |
| patch 0018 sha256 | `9a1e079b740d8f253f5c4c9a323a618a5820b8100ccbcff56fae84557d215a9c` |
| patch 0019 | `uboot-port/patches/0019-drivers-net-add-the-ZX279128S-switch-and-traffic-manager-setup.patch`（交换机/流量管理器/DMA 初始化，16 MiB arena 布局） |
| patch 0019 sha256 | `3e615397a428781683f753f42374a74b100d739819de64a63408616b557b4a3f` |
| patch 0020 | `uboot-port/patches/0020-drivers-net-add-the-ZX279128S-Ethernet-driver.patch`（U-Boot 网络驱动：lan1/port 2/PHY 12、轮询 TX/RX、`e2631net`、arena guard） |
| patch 0020 sha256 | `d8b9eb9f93125798c4d17a2fc09b621a5d9f139706263dcbd9160ba6b3e1416a` |
| patch 0021 | `uboot-port/patches/0021-MAINTAINERS-add-the-ZTE-ZXHN-E2631-board-and-the-ZX2.patch`（MAINTAINERS：板级 + SoC + 以太网/MDIO/SPI 驱动 + DTS + defconfig + 命令文档） |
| patch 0021 sha256 | `c66643e1eca8c5cc2313e0136636b0ea22822f38f7207236b41786ba93ab7976` |
| patch 0022 | `uboot-port/patches/0022-doc-add-the-e2631net-usage-page.patch`（`doc/usage/cmd/e2631net.rst`：`e2631net` 用法页） |
| patch 0022 sha256 | `680435c34a4b6ca5154debb0ace1caea7fd7000641e5e572c6477f22b6959b72` |
| am 之后 tree | `c812dd8689ccf146deeec83bd0e74067c8b8abc5`（与机器无关，22 个 patch） |
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
test "$(git rev-parse HEAD^{tree})" = 10ade1ec0f7a3a7943783d6ba6146840fda6d4bf
```

## 2. 新增/修改的文件

| 文件 | 作用 |
| --- | --- |
| `arch/arm/Kconfig` | 新增 `ARCH_ZX279128`（select CPU_V7A），source mach Kconfig |
| `arch/arm/Makefile` | `machine-$(CONFIG_ARCH_ZX279128) += zx279128s` |
| `arch/arm/mach-zx279128s/Kconfig` | `SYS_SOC="zx279128s"`、`TARGET_ZXHN_E2631`、source 板级 Kconfig |
| `arch/arm/mach-zx279128s/Makefile` | A1 无 SoC 私有代码（secondboot 已完成初始化），只留占位说明 |
| `board/zte/zxhn-e2631/Kconfig` | `SYS_BOARD`/`SYS_VENDOR`/`SYS_CONFIG_NAME` |
| `board/zte/zxhn-e2631/Makefile` | 编译 `zxhn-e2631.o`、`e2631boot.o`（A3）、`e2631soc.o`（C1b）、`e2631net.o`（A5）、`e2631flash.o`（D-U1）与 `e2631env.o`（U-0017） |
| `board/zte/zxhn-e2631/e2631boot.c` | A3：`e2631boot` 命令（槽位扫描/选择/uImage 校验/`bootm`）+ `board_late_init()` 覆盖 `bootcmd`；C1b：`bootm` 前调用 `e2631_soc_prepare_linux()`；A5：`bootm` 前调用 `e2631_net_refclk_init()`；U-0016：选中槽 uImage 失败时经 `e2631_try_boot_slot()` 改试另一槽一次（class-1 回退，无 flash/env 写）；U-0017：`board_late_init()` 在覆盖 `bootcmd` 之前调用 `e2631_env_snapshot()` 保存四个厂商键 |
| `board/zte/zxhn-e2631/e2631soc.c` | C1b：厂商顺序的 CP15 清理 + `e2631soc` 只读报告命令（SCTLR/CLIDR/TTBR0/VBAR/ACTLR 前后值；不启动、不写 flash/env） |
| `board/zte/zxhn-e2631/e2631soc.h` | `e2631_soc_prepare_linux()` 原型（`e2631boot.c` 与 `e2631soc.c` 共用一条代码路径） |
| `board/zte/zxhn-e2631/e2631net.c` | A5：厂商 `board_eth_init()` 的参考时钟/SerDes/CRM2/管脚序列（pinmux 六个整字、只驱动八个输出、`0x9400000C` 的 `bits[21:20]` 时钟选择）+ `e2631refclk` 前后 dump 命令（不启动、不写 flash/env）；E2 起 `e2631_net_refclk_init()` 幂等（`refclk_done`），`e2631boot` 与以太网驱动的 `start()` 可以各调一次 |
| `board/zte/zxhn-e2631/e2631net.h` | `e2631_net_refclk_init()` 原型（`e2631boot.c` 与 `e2631net.c` 共用一条代码路径） |
| `board/zte/zxhn-e2631/e2631flash.c` | D-U1：`e2631flash`（块对齐擦除→全 0xFF 校验→写入→读回逐字节比较，RAM 或 NAND 偏移两种来源，1 MiB bounce buffer，payload/readback CRC32，DO NOT POWER OFF）、`e2631verify`（只读 CRC32）与 `e2631slot`（复用 `e2631boot` 扫描函数打印槽位表）；E2 起拒绝任何落在 16 MiB 网络 DMA arena 里的 RAM 源（`static_assert` + 运行期 `e2631_check_ram_range()`），`e2631verify` 用同一检查 |
| `board/zte/zxhn-e2631/e2631env.c` | U-0017：`e2631env check/diff/save`（唯一 env 写入口）；`save` = 坏块预检→擦除→全 0xFF 校验→写入→回读逐字节比较，只用 `CONFIG_ENV_OFFSET`/`CONFIG_ENV_SIZE` 常量（4 条编译期断言），白名单只放 `e2631_*` 与 `bootdelay`，导出前恢复 `bootcmd`/`bootargs`/`memsize`/`versioninfo` 快照，写前后断言 `0xE0000..0xFFFFF` 仍为全 0xFF；无变化时打印 `nothing to write` 且不擦除 |
| `board/zte/zxhn-e2631/e2631env.h` | `e2631_env_snapshot()` 原型（`e2631boot.c` 与 `e2631env.c` 共用） |
| `board/zte/zxhn-e2631/zxhn-e2631.c` | `dram_init`/`dram_init_banksize` 从内嵌 DT 读 256 MiB |
| `board/zte/zxhn-e2631/MAINTAINERS` | 维护者与文件范围 |
| `include/configs/zx279128s_zte_zxhn-e2631.h` | `CFG_SYS_SDRAM_BASE=0x40000000`、`CFG_PL011_CLOCK=0`、`CFG_SYS_HZ_CLOCK=500000000` |
| `arch/arm/dts/zx279128s-zte-zxhn-e2631.dts` | memory / PL011 / A9 global timer / 500 MHz fixed-clock；E2 起还有 `mdio@9a101000`（`zte,zx279128s-mdio` + `ethernet-phy@c`）与 `ethernet@92000000`（`zte,zx279128s-gmac`、`phy-handle=<&phy12>`、`zte,switch-port=<2>`） |
| `drivers/net/zx279128s_eth.h` | E2：交换机/流量管理器/DMA 寄存器与 16 MiB arena 偏移、`e2631_net_refclk_init()` 原型（0018 引入，MDIO 驱动与以太网驱动共用） |
| `drivers/net/zx279128s_mdio.c` | E2：clause-22 MDIO 主控制器（`0x9a101000`）；首次传输时懒初始化（先跑板级参考时钟 hook），支持 devad 0 的 read/write；`mii` 命令可直接使用 |
| `drivers/net/zx279128s_eth.c` | E2：`zx_hw_init()`（复位/时钟门控/PP/索引表/TM 队列表/BMU/DMA 环/交换机/MAC）+ U-Boot `eth_ops`（BMU 缓冲池、TX 描述符与 TX_DONE、RX queue 0 轮询、free_pkt 归还） + `e2631net` 状态命令；`start()` 调 `e2631_net_refclk_init()`（幂等） |
| `drivers/net/Kconfig`；`drivers/net/Makefile` | E2：`MDIO_ZX279128S` 与 `ETH_ZX279128S`（`depends on DM_ETH && NET_LEGACY`，select `DM_MDIO`/PHYLIB/PHY_GIGE；不能同时 depends DM_MDIO 与 select PHYLIB，否则 Kconfig 递归依赖） |
| `arch/arm/dts/Makefile` | `dtb-$(CONFIG_TARGET_ZXHN_E2631) += zx279128s-zte-zxhn-e2631.dtb` |
| `configs/zx279128s_zte_zxhn-e2631_defconfig`；D-U1 增加 `# CONFIG_CMD_MTD_WRITE is not set`，让 `e2631flash` 成为镜像里唯一的 MTD 写入口（0015） | A1/A2/A3 配置（已用 `make savedefconfig` 归一；A3 增加 `BOARD_LATE_INIT`/`SUPPORT_PASSING_ATAGS`/`ENV_IS_IN_MTD` 与只读 env 参数；0011 移除 `CONFIG_SKIP_LOWLEVEL_INIT`，让标准 `cpu_init_cp15`/`cpu_init_crit` 在入口重新生效）；E2 增加 `CMD_DHCP`/`CMD_MII`/`CMD_PING`/`NET_RANDOM_ETHADDR`/`ETH_ZX279128S`/`MDIO_ZX279128S`（`NET`/`NET_LEGACY`/`DM_ETH`/`DM_MDIO`/`PHYLIB`/`PHY_GIGE`/`CMD_NET`/`CMD_TFTPBOOT` 是默认 y，savedefconfig 不重复写） |
| `cmd/Kconfig` | D-U1：新增 `CONFIG_CMD_MTD_WRITE`（bool，默认 y，依赖 `CMD_MTD`） |
| `cmd/mtd.c` | D-U1：write/erase 子命令表项、`do_mtd_io` 写分支、`do_mtd_erase()` 与 `mtd_special_write_oob()` 只在 `CMD_MTD_WRITE` 打开时编译；read/dump 不变 |

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

补丁 0013（2026-11-22，A6，A5 之后的第三个 flash 链缺口）：在 0012 的 `e2631_pinmux_gpio_init()` 末尾补上厂商
`zte_gpio_init()` 的两段尾部特例循环（`0x47f2f61c` 与 `0x47f2f66c`）：它们在板级表回放后再次遍历表，把表索引
51 与 50 对应的使能输出项（pin 2 与 pin 51）无视表值 0 直接置 1。A5 真机会话的两链差分里残留的 10 个寄存器字
正是这两根线（`0x94407014` bit2、`0x944070d4` bit3）；留低时内核只枚举到两个 PCIe root port、没有任何
endpoint（`14c3:7906`/`14c3:790a` 缺失，`mt7915e` 无法绑定），厂商链能看到两个 endpoint。两根线的功能文档未给出，
按“PCIe 端点复位/供电”假设处理；两次置位之间按厂商代码保留 `mdelay(4)`，只做 SET 位 RMW，幂等。设计与验收见
[a6-pcie-endpoint-reset-design.md](a6-pcie-endpoint-reset-design.md)。

补丁 0014（2026-11-22，D-U1，自更新命令）：新增 `board/zte/zxhn-e2631/e2631flash.c`。`e2631flash <src> <off> <len>` 按块对齐擦除 → 校验全 0xFF → 写入 → 读回逐字节比较，打印 PASS/FAIL、首个不一致偏移，以及 staged payload 与 readback 的 CRC32；`<src>` 在 `0x40000000` 及以上是 RAM 地址，小于 `0x10000000` 是 NAND 字节偏移，后者先整段读入 `0x44000000` 的 1 MiB bounce buffer，再擦除/写入，因此 flash→flash 更新不会边擦边读目标；长度上限 1 MiB；擦除前打印 DO NOT POWER OFF，并拒绝未对齐/越界、secondboot（0x00000..0x20000）与 env（0xC0000..0xE0000）。`e2631verify` 只读比较 RAM 与 flash 的 CRC32；`e2631slot` 复用 `e2631boot` 的 `e2631_scan_slot`/`e2631_pick_slot` 打印槽位表，不复制扫描逻辑。串口 loadx 实测约 10.9 KB/s（640 KiB 要 60 s），所以正常更新路径改为以太网 + userdata 暂存 + 重启进 U-Boot，串口只保留救砖用途。

补丁 0015（2026-11-22，D-U1 写入口收口）：上游 `CONFIG_CMD_MTD` 会编译 `mtd write/erase` 子命令，与 `e2631flash` 并存等于多一条无保护写入口。新增 `CONFIG_CMD_MTD_WRITE`（bool，默认 y，保持上游语义），把 `cmd/mtd.c` 的 write/erase 子命令表项、`do_mtd_io` 写分支、整个 `do_mtd_erase()` 与 `mtd_special_write_oob()` 放到 `#if CONFIG_IS_ENABLED(CMD_MTD_WRITE)` 后；本 defconfig 写 `# CONFIG_CMD_MTD_WRITE is not set`，read/dump 不受影响。`env/mtd.c` 的 save/erase 在 `# CONFIG_CMD_SAVEENV is not set` 下由 `ENV_SAVE_PTR`/`ENV_ERASE_PTR` 变为 NULL，且 ARM 链接的 `--gc-sections` 会丢掉未引用段，不构成第二条写路径；CI 用调用点白名单证明镜像里 `mtd_write()`/`mtd_erase()` 的调用只出现在 e2631flash 代码内。

补丁 0016（2026-11-22，U-0016，class-1 跨槽回退）：厂商 cspboot 在选中槽的内核 CRC 不合格时会自动改启另一个
合法槽（`pdt_getreal_kernelfs` 的 `csp_crc` 路径，日志 `not found vaild fs!! -> Total found 2 firmwares(valid:1)`），
而我们的 `e2631boot`（0006）在任一 uImage 校验失败时直接返回。0016 把“启动一个槽”拆成 `e2631_try_boot_slot()`：
先按 cspboot 的 serial 规则选槽并校验其 uImage（头读取、magic/type/OS/压缩、header CRC、大小窗口、短读、
data CRC），任一失败则打印 `slot%d unusable (<reason>), falling back to slot%d (cspboot class-1 parity)` 并
改试另一槽一次；两槽都失败时打印逐槽诊断表（base/serial/version/失败原因）并返回控制台，不调用 `bootm`。
回退无状态：不改版本头/serial、不写“上次启动失败”标志、不计数、不写 flash、不碰 env，且只影响本次启动
（下次仍按 serial 规则选）。健康路径与 `e2631slot` 的扫描/选择代码完全不变。设计依据见
[docs/U-Boot-env写回与启动计数设计-2026-11-22.md](../docs/U-Boot-env写回与启动计数设计-2026-11-22.md) §6.3/§7。

补丁 0017（2026-11-22，U-0017，env 写回）：厂商 env 块在 mtd0 `0xC0000`（`0x20000` 一块），我们的链一直
只读加载；通用 `saveenv` 继续编掉，`env/mtd.c` 的 `.save` 保持 `ENV_SAVE_PTR(env_mtd_save)` → NULL，
新增的 `e2631env` 是镜像里唯一的 env 写入口。`check` 读块、解析并重算 CRC（只读）；`diff` 构建候选块并列出
`save` 会改的键（不写）；`save` 的五步与 `e2631flash` 同构：坏块预检（在擦除之前）→ 擦除 → 读回全 0xFF →
写入 → 读回逐字节比较，结束时打印 old/new CRC 与变化键列表。地址只来自冻结的
`CONFIG_ENV_OFFSET`/`CONFIG_ENV_SIZE`，并有 4 条编译期断言；候选块与当前块相等时打印
`nothing to write` 且不擦除（幂等）。白名单只允许 `e2631_*` 与 `bootdelay`，其余键有差异时列出并拒绝写；
`board_late_init()` 在覆盖 `bootcmd` 前把 `bootcmd/bootargs/memsize/versioninfo` 存快照，导出候选前恢复，
因此持久化块保持厂商兼容。写前写后都断言 `0xE0000..0xFFFFF` 保留扇区仍为全 0xFF。
**与设计稿的偏差（有意）**：设计稿 W1 原打算把 `env/mtd.c` 的 `.save` 直连 `env_mtd_save`；实际改为
`e2631env.c` 内自带五步写、`.save` 继续为 NULL，让通用 `env_mtd_save()`（擦除后直接写、无全 FF 校验）
根本不存在于镜像中，D-U1 白名单因此只覆盖两个安全 writer（`e2631flash` 与 `e2631env`）。另一处加固：
当前 env 块非空但 CRC/解析坏时 `save` **拒绝**重建（fallback env 里没有厂商键，重建会丢 `ethaddr` 等；
让厂商链的 `zteboot_do_settings` 自愈），比设计稿的“允许修复”更保守。env 写入尚未在真机演练；
第一次真实 `save` 并入下一次用户批准的设备会话。

补丁 0018（2026-11-22，E2，MDIO）：四个集成 PHY 在 MDIO 地址 10-13，控制器在 `0x9a101000`（一个命令寄存器 +
一个状态寄存器，clause-22）。新增 `drivers/net/zx279128s_mdio.c`（`MDIO_ZX279128S`，compatible
`zte,zx279128s-mdio`）与共享头 `drivers/net/zx279128s_eth.h`（寄存器/arena 定义 + 板级
`e2631_net_refclk_init()` 原型，MDIO 驱动与后面的以太网驱动共用）。控制器没有可用复位，驱动在**首次传输**时
懒初始化：先调一次板级参考时钟 hook（0012 的幂等函数），再写 CMD/STATUS/CFG，因此提示符下直接 `mii info`
也能工作；`mii` 命令由 MDIO uclass 的 post_probe 注册的 mii_bus 自动获得。注意 Kconfig：`DM_MDIO` 依赖
`PHYLIB`，若驱动同时 `depends on DM_MDIO` 又 `select PHYLIB` 会触发递归依赖，所以用
`depends on DM_ETH && NET_LEGACY` + `select DM_MDIO`。

补丁 0019（2026-11-22，E2，交换机/TM/DMA）：新增 `drivers/net/zx279128s_eth.c` 的前半部分与
`ETH_ZX279128S`：把 Linux 驱动（`target/linux/zx279128/files/.../zx279128s-main.c`）在同一硅片上的
`zx_hw_init()` 搬进 U-Boot——主复位、时钟门控、PP 复位/桥/分类器、两张空闲缓冲索引表（4096/512 项，
big-endian u16）、1168 条 TM 队列表（CPU 队列 0-15 按 1024 槽 RX ring 设上限并叠加上次启动残留，16-399 固定值，
RED 384 与 SCHED 384）、TM/BMU 参数（4096 个 2048 B 缓冲，`LIMIT1=127`、`THRES1=4096<<16`）、DMA/TM 控制值、
TX/RX 描述符环清零、交换机转发/每口 index/上行下行分类/trap ethertype、端口过滤，以及五个 MAC 口的厂商初值。
16 MiB arena 的布局与内核一次 `dma_alloc` 的分配完全一致：`+0x000000` 缓冲池 8 MiB、`+0x800000` tab0、
`+0x808000` tab1、`+0xA00000` 8 个 RX 队列环（每 0x4000）、`+0xB00000` area50、`+0xC00000` TX 环（1024×16 B）。

补丁 0020（2026-11-22，E2，U-Boot 驱动）：把上面的初始化接进 U-Boot 网络栈。新增 `eth_ops`：`start()` 先调
幂等的 `e2631_net_refclk_init()`（A5 时钟/SerDes 必须先于任何 GMAC 寄存器），再跑 `zx_hw_init()`、连 PHY 12、
`phy_startup()` 后按 link 结果设 MAC speed/duplex、写 trap MAC、开 DMA；`send()` 从 BMU 取 2048 B 缓冲
（拷贝到 `arena+bp*2048+16`）、填 16 B TX 描述符（queue = 40 + switch_port）、写 `0x92350064=1` 并轮询
`TX_DONE` 低 16 位；`recv()` 轮询 RX queue 0 计数、解析描述符里的 bp/len/class，`free_pkt()` 把 RX slot 与
缓冲还给硬件。固定 arena 地址 `0x45000000`，没有运行时分配；因为 arena 在网络启动后是活数据，
`e2631flash` 与 `e2631verify` 都拒绝落在其中的 RAM 地址（编译期 + 运行期双重检查）。设备树新增
`mdio@9a101000`/`ethernet-phy@c` 与 `ethernet@92000000`（`phy-handle=<&phy12>`、`zte,switch-port=<2>`），
defconfig 打开 `CMD_DHCP/CMD_MII/CMD_PING/NET_RANDOM_ETHADDR/ETH_ZX279128S/MDIO_ZX279128S`。`e2631net`
打印 switch port、PHY/link/speed、MAC ctrl、TM 中断、BMU 空闲计数与 8 个 RX 队列计数。单口 lan1；
其它三个 PHY、PHY fixup、autoboot rescue 留后续阶段（M2/E3）。设计见 [e2-net-driver-design.md](e2-net-driver-design.md)。

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
| env | `ENV_IS_IN_MTD`（默认只读） | A3 从厂商块 `0xC0000`/`0x20000` 只读载入（格式与 `env_t` 逐字节兼容）；`saveenv` 与 `env/mtd.c` 的 `.save` 都保持关闭/NULL；0009 起日志名称显示为 `MTD`（此前 `<NULL>` 只是 `CMD_SAVEENV` 关闭后 `.name` 没定义，不代表未生效） |
| env 写回 | `e2631env check/diff/save`（0017） | 唯一 env 写入口：`save` = 坏块预检→擦除→全 0xFF 校验→写入→回读逐字节比较，只用 `CONFIG_ENV_OFFSET`/`CONFIG_ENV_SIZE` 常量（4 条编译期断言）；白名单只放 `e2631_*` 与 `bootdelay`，导出前恢复 `bootcmd/bootargs/memsize/versioninfo` 快照；写前后断言 `0xE0000..0xFFFFF` 仍为全 0xFF；无变化时 `nothing to write` 不擦除；非空但 CRC 坏的块拒绝重建（交给厂商链自愈），env 写入尚未真机演练 |
| 槽位启动 | `e2631boot`（A3） | 扫描两槽每 128 KiB 块找版本头（内层 magic + CRC1），serial 大者胜出（`slot0.serial==0` 也按小处理）；从 `slot+0x20` 读 uImage 到 `0x42000000` 后 `bootm`；ATAGS + 内核 append-dtb |
| class-1 跨槽回退 | `e2631_try_boot_slot()` + 一次重试（0016） | cspboot 在选中槽 uImage 坏时改启另一槽；0016 补齐该语义：失败日志 `falling back to slot%d (cspboot class-1 parity)`，两槽都坏时打印诊断表并回控制台；无状态、只影响本次启动、不写 flash/env，serial 选择规则与 `e2631slot` 共用代码不变 |
| ATAGS 缓冲区 | `CFG_SYS_SDRAM_BASE + 0x100`（= `0x40000100`） | 0008 在 `board_late_init()` 设置 `gd->bd->bi_boot_params`；`static_assert` 保证 > DRAM base 且 +0x100 ≤ 内核 load `0x40008000`；本配置 `SYS_MALLOC_BOOTPARAMS` 关闭，没有其它代码分配该缓冲区 |
| 设备树 | `OF_EMBED` | DTB 内嵌进 `u-boot.bin`，`go` 跳转无需外部 DTB；后续再考虑分离/追加格式 |
| SPI-NAND | 只读（A2，0005） | SPIFC PIO + U-Boot SPI-NAND 核心 + FORESEE F35SQA001G + `mtd` 读；不写 flash、不碰 env |
| 网络参考时钟/SerDes | `e2631_net_refclk_init()`（0012） | 厂商 `board_eth_init()` 的逐字段重放：分数 PLL `0x94000050/0x54`（第二寄存器先清 bit27/25/24、置 bit26，再以高字节保留的方式写 FRAC）、`0x94000008` bit4/bit5、`0x9FE00000` SerDes 25 写、CRM2 `0x94100010`、`0x9400004C`→`0x9A100004`、`0x9400000C` 的 `bits[21:20]=0b01`（厂商以太网 probe 的时钟 mux，两链 dump 证明不同）；内核 clk 驱动假设 bootloader 已完成该初始化，且无内核驱动碰这些寄存器（DTS 无法描述）。`e2631refclk` 打印前后 7 个寄存器，不启动 |
| Pinmux / GPIO | `0x94200000` + 厂商板级表（0012） | pinmux 先三处 |= 厂商值，再按厂商顺序写入板级表六个整字；GPIO 先驱动八个输出（8=1/40=1/60=0 三色 LED、55/52/54/51/2=0），十个输入（strap 5/15/62/61/43/47/46/45、按键 18/20）复位后 DIR 已为 0，无需写；不驱动 flat 53。全部为板上外设的“回到厂商上电状态”，幂等 |
| MDIO | clause-22 @ `0x9a101000`（0018） | 四个集成 PHY 在地址 10-13；驱动在首次传输时懒初始化（先跑 0012 的时钟 hook），提示符下 `mii info` 即可用；Kconfig 用 `select DM_MDIO` 避免与 PHYLIB 的递归依赖 |
| U-Boot 以太网（E2） | lan1 = switch port 2 / PHY 12（0018-0020） | 单口接进 U-Boot 网络栈：`mii info` / `dhcp` / `ping` / `tftp`，链路 1 Gbps；`send/recv` 轮询、无中断；其它三个 PHY 与 autoboot rescue（E3）不在本阶段 |
| DMA arena | `0x45000000..0x45FFFFFF`（16 MiB，固定） | 与内核驱动同布局：`+0x000000` 缓冲池 8 MiB、`+0x800000` tab0、`+0x808000` tab1、`+0xA00000` RX 环（8×0x4000）、`+0xB00000` area50、`+0xC00000` TX 环（1024×16 B）。U-Boot 不从这里分配别的内存；`e2631flash` 的 bounce buffer（`0x44000000`+1 MiB）与该 arena 的边界有编译期断言；内核 load `0x40008000`、uImage 暂存 `0x42000000` 都在其下 |
| PCIe 端点复位/供电 | pin 2 / pin 51 置 1（0013） | 厂商 `zte_gpio_init()` 在板级表回放后还有两段按表索引的特例（`0x47f2f61c` 索引 0x33→pin 2；`0x47f2f66c` 索引 0x32→pin 51），无视表值 0 直接置 1；A5 两链差分的残留字正是 `0x94407014` bit2 与 `0x944070d4` bit3。厂商链能枚举 `14c3:7906`/`14c3:790a`，本链留低时只有 root port。功能文档未给出，复位/供电是工作假设；SET 位 RMW，幂等 |
| 网络协议栈 | 仅 U-Boot 网络命令（E2） | `mii`/`dhcp`/`ping`/`tftp` 可用；不做网络引导回退/autoboot rescue（E3）。tftp 目标必须避开 16 MiB arena（例如 `0x43000000`），TFTP 写入的是运行时 DMA 数据区 |
| 刷写 | 命令已交付（D-U1） | A3/A4 刷写会话前只做只读；`e2631flash`/`e2631verify`/`e2631slot`（0014）与唯一写入口开关（0015）已交付，写 mtd0/槽位仍需用户批准并先做零写入暂存 CRC 校验 |
| CPU1/SRAM | 不碰 | secondboot 已把 CPU1 停在 `wfe` → SRAM `0x200800` 循环；内核 platsmp 依赖该约定，U-Boot 不得改写 SRAM |
| 自更新命令 | `e2631flash` / `e2631verify` / `e2631slot`（0014） | `e2631flash` 块对齐擦除 → 全 0xFF 校验 → 写入 → 读回逐字节比较，打印 PASS/FAIL、首个不一致偏移与 staged payload/readback CRC32；`<src>` ≥0x40000000 为 RAM 地址、<0x10000000 为 NAND 字节偏移（先读入 `0x44000000` 的 1 MiB bounce buffer，flash→flash 更新不边擦边读目标）；拒绝未对齐/越界、secondboot 0x00000..0x20000、env 0xC0000..0xE0000 与长度 >1 MiB；擦除前打印 DO NOT POWER OFF。`e2631verify` 只读 CRC32；`e2631slot` 复用 `e2631boot` 的扫描函数 |
| 原始 mtd 写入口 | `CONFIG_CMD_MTD_WRITE`（0015） | 上游 `CONFIG_CMD_MTD` 自带 `mtd write/erase` 子命令；新增 `CONFIG_CMD_MTD_WRITE`（bool，默认 y）把它们编到开关后，本 defconfig 关闭，使 `e2631flash` 成为镜像中唯一调用 `mtd_write()`/`mtd_erase()` 的代码（CI 用调用点白名单证明） |

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

1. `git rev-parse HEAD^{tree}` == `10ade1ec0f7a3a7943783d6ba6146840fda6d4bf`；每个 patch 的 sha256 与 §1 一致，
   且 `git rev-list --count <baseline>..HEAD` 等于 patch 数量（当前 20）。
2. `.config` 精确包含：`CONFIG_ARCH_ZX279128=y`、`CONFIG_TARGET_ZXHN_E2631=y`、
   `CONFIG_TEXT_BASE=0x47F00000`、`CONFIG_OF_EMBED=y`、`CONFIG_ARM_GLOBAL_TIMER=y`、
   `CONFIG_TIMER=y`、`CONFIG_PL01X_SERIAL=y`、`CONFIG_DM_SERIAL=y`、`CONFIG_CLK=y`、
   `CONFIG_SPI=y`、`CONFIG_DM_SPI=y`、`CONFIG_SPI_ZX=y`、`CONFIG_MTD=y`、`CONFIG_DM_MTD=y`、
   `CONFIG_MTD_SPI_NAND=y`、`CONFIG_CMD_MTD=y`；0011 起还要求 `# CONFIG_SKIP_LOWLEVEL_INIT is not set`
   （入口归一化不能再次被跳过）；0015 起还要求 `# CONFIG_CMD_MTD_WRITE is not set`（原始 mtd 写入口被编掉）；
   0017 起还要求 `# CONFIG_CMD_SAVEENV is not set`、没有 `CONFIG_CMD_ERASEENV=y` 与
   `CONFIG_SYS_REDUNDAND_ENVIRONMENT=y`（env 只经 `e2631env` 写、且不做冗余块）；
   E2 起还要求 `CONFIG_DM_ETH=y`、`CONFIG_DM_MDIO=y`、`CONFIG_PHYLIB=y`、`CONFIG_PHY_GIGE=y`、
   `CONFIG_ETH_ZX279128S=y`、`CONFIG_MDIO_ZX279128S=y`、`CONFIG_NET_RANDOM_ETHADDR=y`、
   `CONFIG_CMD_DHCP=y`、`CONFIG_CMD_MII=y`、`CONFIG_CMD_PING=y`、`CONFIG_CMD_TFTPBOOT=y`。
3. 镜像尺寸：`size=$(stat -c%s build/u-boot.bin); test "$size" -le 653312`
   （超限就裁命令/驱动；这条对应 mtd0 载荷上限 0x9F800，是刷写阶段的硬前置）。
4. 入口点：`readelf -h build/u-boot` 的 Entry point 应为 `0x47F00000`（readelf 打印小写 `0x47f00000`，CI 统一转小写比较）。
5. 上传 CI artifact：`u-boot.bin`、`u-boot.map`、`.config`、构建日志；记录 run URL。
6. checkpatch（CI 门禁，见 §6）：CI 以 `--ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF` 跑
   `u-boot/scripts/checkpatch.pl --no-tree --terse`，要求 **0 errors / 0 warnings**。ignore 列表在 workflow 里
   逐类注释，并由运行期断言钉成“恰好这四类”；这四类之外的任何 warning 或任何 error 都会让 uboot-build 失败。
   不加 ignore 时的原始统计是 0 errors / 26 reviewed warnings（0008/0009 各 0/0；0011 与 0012 各 0/2；0013 0/0；
   0014 0/4；0015 0/5；0016 0/0；0017 0/2；0018 修正后 0/1；0019 0/1；0020 0/1；0021 0/0；0022 0/1），分项与原因见 §6；
   四类豁免的必要性与 checkpatch.pl 源码依据（2805、3560-3568、2670-2674 行）见
   [evidence/uboot-checkpatch-maintainers-20261122.md](../evidence/uboot-checkpatch-maintainers-20261122.md)。
7. 内嵌 DTB 的 uart0 compatible 是 `zte,zx29-uart`：`grep -aq 'zte,zx29-uart' build/u-boot.bin`
   （OF_EMBED 把 DTB 打进镜像）。少了这条，构建会通过但 A1 串口仍然静默，正是 task-45 的故障模式。
8. 内嵌 DTB 的 SPI 节点：`grep -aq 'zte,zx279128s-spifc' build/u-boot.bin` 且
   `grep -aq 'spi-nand' build/u-boot.bin`（A2 的控制器/芯片节点；防止 DTS 或 defconfig 被误删而
   构建仍通过）。
9. A3 配置：`CONFIG_BOARD_LATE_INIT=y`、`CONFIG_SUPPORT_PASSING_ATAGS=y`、
   `CONFIG_SETUP_MEMORY_TAGS=y`、`CONFIG_BOOTCOMMAND="e2631boot"`、`CONFIG_ENV_IS_IN_MTD=y`、
   `CONFIG_ENV_MTD_DEV="spi-nand0"`、`CONFIG_ENV_OFFSET=0xc0000`、`CONFIG_ENV_SIZE=0x20000`；
   并且 `# CONFIG_CMD_SAVEENV is not set`（只有显式 `e2631env` 能写 env；0017 起 `CONFIG_CMD_ERASEENV`
   与 `CONFIG_SYS_REDUNDAND_ENVIRONMENT` 也不能打开）、`CONFIG_ENV_IS_NOWHERE` 未启用。
10. A3/C1b/A5/D-U1/U-0017/E2 二进制：`grep -aq 'e2631boot'`、`'e2631soc'`、`'e2631refclk'`、`'e2631flash'`、
    `'e2631verify'`、`'e2631slot'`、`'e2631env'`、`'e2631net'` 与 `'spi-nand0'` 都要在 `build/u-boot.bin` 里命中（槽位/CP15/网络时钟/
    自更新/env/以太网命令与 env 设备名确实链接进镜像），且四条 usage 文本（flash/verify/slot/env 帮助首行）、
    `DO NOT POWER OFF` 与 E2 的 `lan1 up` 启动日志也能 grep 到。
11. A3/C1a/C1b/A5 修复（0008/0009/0011/0012）：`grep -q 'bi_boot_params' board/zte/zxhn-e2631/e2631boot.c`、
    `grep -q 'define ENV_NAME(_name) .name = _name,' include/env_internal.h`、
    `grep -q 'e2631_soc_prepare_linux' board/zte/zxhn-e2631/e2631boot.c`、
    `grep -q 'mcr p15' board/zte/zxhn-e2631/e2631soc.c`、
    `grep -q 'e2631_net_refclk_init' board/zte/zxhn-e2631/e2631boot.c`、
    `grep -q 'E2631_GPIO_PCIE_RST0' board/zte/zxhn-e2631/e2631net.c`、
    `grep -q 'e2631_stage_source' board/zte/zxhn-e2631/e2631flash.c`（0014 的 bounce staging）、
    `grep -q 'e2631_try_boot_slot' board/zte/zxhn-e2631/e2631boot.c` 且源码与二进制都含 `falling back to slot`
    （0016 的 class-1 回退确实编进镜像）、
    `grep -q 'e2631_env_snapshot' board/zte/zxhn-e2631/e2631boot.c`、
    `grep -q 'e2631_env_write_block' board/zte/zxhn-e2631/e2631env.c`、`e2631env.c` 的 `mtd_block_isbad`
    行号在 `mtd_erase` 之前、`grep -c 'static_assert(' == 4`、`0xE0000` 只出现在 `e2631env.c`，
    且 `e2631net.c` 仍含厂商值
    `0x004fdf3b`、`0x003c0040`、`0x0001381b`、板级 pinmux 字 `0x0f3ffffa`、`0x003dbf85` 与 `0x9400000C` 的 `0x00100000`。形状断言只防回归；编译由 CI 保证，运行期
    （bootm 进内核、env 日志显示 MTD、CP15 前后差值、网络时钟前后差值）由 C1a/C1b 重跑与 Session A 的
    `e2631soc`/`e2631refclk` 输出保证。
12. A5 内核侧成功签名（真机会话记录，不是 CI 断言）：MDIO 地址 10-13 的四个 PHY 出现且 link up；
    `lspci` 出现 `14c3:7906`（bus0）与 `14c3:790a`（bus1）；`br-lan` 有 PHY；另外 `md.l 0x94407014 1` 的 bit2 与
    `md.l 0x944070d4 1` 的 bit3 必须为 1（0013 的两根 PCIe 端点线，见 [a6-pcie-endpoint-reset-design.md](a6-pcie-endpoint-reset-design.md)）。详见
    [a5-net-refclk-design.md](a5-net-refclk-design.md) §5。

13. E2 以太网（0018-0020）：源码形状——`drivers/net/zx279128s_eth.c` 调 `e2631_net_refclk_init`、
    `e2631net.c` 含 `refclk_done`（幂等）、`e2631flash.c` 含 `E2631_NET_ARENA_ADDR` 且 `e2631verify` 走
    `e2631_check_ram_range("e2631verify", ...)`、`e2631flash.c` 与 `zx279128s_eth.c` 都钉了 `0x45000000UL`、
    设备树含 `zte,switch-port` 与（二进制）`zte,zx279128s-gmac`/`zte,zx279128s-mdio`/`ethernet-phy`。
    真机签名（后续会话记录）：`mii info` 看到 PHY 10-13、lan1 链路灯亮（1 Gbps），`dhcp` 拿到地址、
    `ping` 通、`tftp 0x43000000 <file>` 下载成功（目标不要用 arena）；`e2631net` 打印 port 2/PHY 12 状态。
14. D-U1/U-0017 写入口：`.config` 与 defconfig 都必须有 `# CONFIG_CMD_MTD_WRITE is not set`；对 `build/u-boot`
    反汇编做**调用点白名单**——所有 `mtd_write`/`mtd_erase`/`mtd_special_write_oob` 的 `bl` 只能落在
    `e2631_write_range`/`e2631_erase_range`/`do_e2631flash`/`e2631_env_write_block`/`do_e2631env_save` 内，
    且写调用点**恰好 4 个**（`-O2` 会把只有一个调用者的 static helper 内联，所以实际符号可能是
    `do_e2631flash` + `do_e2631env_save`；白名单同时保留 helper 名，防止内联策略变化后误报，也防止白名单空过或漏掉第三条写路径）；
    `e2631env.c` 还必须保留 `DO NOT POWER OFF DURING WRITE`、`mtd_block_isbad`、`e2631_env_vendor_names`
    与 `nothing to write` 这四个安全标记。

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
   然后 `md.l 0x94407014 1`、`md.l 0x944070d4 1` 确认 bit2/bit3 为 1（0013 的两根 PCIe 端点线；
   留低时内核只剩 root port、没有 endpoint）。它同样不启动、不写 flash/env，随后 `e2631boot` 会走同一函数（幂等）。
0.2 刷写会话（D-U1，需用户批准；先零写入校验）：`e2631slot` 打印槽位表与 cspboot 会选中的槽；正常更新路径是以太网把 mtd0 新镜像传到 Linux、暂存到 userdata（`/dev/mtd10`，偏移 `0x3F00000`，约 49 MiB，可写且当前未使用），重启进入本 U-Boot 后跑 `e2631flash 3f00000 20000 a0000`（flash 源 `0x3F00000` → mtd0 的 `0x20000`，长度 `0xA0000` = 640 KiB）。命令先打印 DO NOT POWER OFF，把源整段读入 1 MiB bounce buffer 并打印 `staged payload CRC32`，与主机侧 CRC/sha256 核对无误后，才做擦除/写入/读回比较并打印 `readback CRC32`；写前写后各记一次 mtd0 sha256。`e2631verify <ram地址> <off> <len>` 保留 RAM↔flash 的只读 CRC32 比较（串口调试用）。mtd0 被 DTS 设为只读，这也是更新必须回到 U-Boot 的原因；串口 loadx 仅约 10.9 KB/s，只留给救砖。
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

### E2 以太网验收（需要真机会话；U-Boot 内 `mii`/`dhcp`/`ping`/`tftp`，不写 flash）

装载方式同 A1（厂商控制台 `tftp 0x47F00000 u-boot.bin` + `go 0x47F00000`）。注意两次网络的先后：
下载自定义 U-Boot 用的是**厂商 U-Boot 的**网络栈；进入我们的 U-Boot 后，驱动在第一次网络命令时才初始化。
lan1 是 switch port 2、PHY 12（MDIO 地址 `0x0c`），链路 1 Gbps；其它三个 PHY（0x0a/0x0b/0x0d）本阶段不接
U-Boot 网络栈。

1. `e2631net`：应打印 switch port 2、PHY 12 的 link/speed、MAC ctrl、TM 中断、BMU 空闲计数与 8 个 RX 队列计数。
2. `mii info`：应看到地址 10-13 的四个 PHY；lan1 对应 `0x0c`。
3. `dhcp`：拿地址（`HOSTNAME=...`；env 里没有 `ethaddr` 时由 `CONFIG_NET_RANDOM_ETHADDR` 随机生成一个）。
4. `ping <主机>`：验证 TX/RX 环与 trap 路径。
5. `tftp 0x43000000 <文件>`：下载到 `0x43000000`。**不要用 `0x45000000`**——那是驱动固定的 16 MiB DMA arena，
   TFTP 写进去会与 RX/TX 描述符和缓冲池互相覆盖；`e2631flash`/`e2631verify` 也会拒绝该地址。
6. `e2631verify 0x43000000 <off> <len>`：只读比较下载内容与 flash；不写 flash。
7. 记录完整串口日志与收发证据，落盘 evidence/ 并汇报 Lead。

失败定位顺序：`e2631net` 报未 probe → 查 DT compatible/defconfig；`mii info` 无 PHY → 先 `e2631refclk`
确认真机时钟序列；`dhcp` 无包 → 查 lan1 接线/链路与 PHY 12；`TX completion timed out` → 记录 `e2631net`
全量与 `md.l 0x92350068 1`，按 [e2-net-driver-design.md](e2-net-driver-design.md) §7 的 BMU/DMA 顺序定位。

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
- **A6 的两根 GPIO 是“重放厂商特例”，功能靠假设**：0013 把 pin 2 与 pin 51 置 1，依据是厂商
`zte_gpio_init()` 尾部两段按表索引的特例循环与 A5 两链差分的残留字；硬件文档没有说明这两根线的功能，
“PCIe 端点复位/供电”是工作假设。若真机 PCIe 反而变差或这两根线影响别的外设，回退只需删掉
`e2631_pinmux_gpio_init()` 末尾那两行 `e2631_gpio_drive()`，回到 A5 状态；它们不影响 eth。
验收标准是内核能枚举 `14c3:7906`/`14c3:790a` 且 `mt7915e` 绑定成功。

- **E2 只接 lan1，且尚未真机演练**：驱动只把 switch port 2（PHY 12）接进 U-Boot 网络栈；lan2/lan3/wan
  三个 PHY 走内核，PHY 0x14 的 fixup 与多口留给 M2。E2 的证据只有静态检查与 CI 构建（编译、配置符号、
  设备树字符串、arena guard、`e2631net`/`lan1 up` 二进制字符串）；第一次真机会话按 §5.4 的命令集验收，
  串口日志落盘。另外 TX/RX 都是轮询、无中断，TFTP 大文件会占满 CPU 时间（可接受，U-Boot 只用于救砖/更新）。
- **16 MiB DMA arena 与 `e2631flash` 的边界**：arena 固定 `0x45000000..0x45FFFFFF`（缓冲池/索引表/描述符环），
  网络启动后是活数据；`e2631flash` 与 `e2631verify` 的 RAM 源必须避开它（编译期断言 + 运行期
  `e2631_check_ram_range()`），bounce buffer 固定在 `0x44000000`（1 MiB，在其下）。改 arena 地址必须同时改
  `zx279128s_eth.h` 与 `e2631flash.c` 的常量，否则 CI 形状门禁会失败。
- **入口必须等于链接地址（非 PIE）**：`TEXT_BASE=0x47F00000` 对齐 secondboot 的固定入口；
  U-Boot 未开 `CONFIG_POSITION_INDEPENDENT`，`relocate.S` 的修正量假设运行地址 == 链接地址，
  从其它地址进入会在 banner 之前挂死或 data abort；改地址只能改 defconfig 后重编，不能只改 `go`。
- **载荷 0x9F800**：刷写阶段封装/写 mtd0 前必须满足；secondboot 封装头其它字节（+0x2D4 摘要等）在
  刷写阶段必须原样保留。
- **0016 的回退路径尚未真机演练**：源码/二进制字符串门禁只证明 class-1 回退代码确实编进镜像；运行期证明需要
  人为破坏选中槽的 uImage（写 slot 区，需单独批准）或等真实坏槽事件。健康路径不受影响：选槽规则、版本头校验与
  uImage 校验顺序都与 0006 相同，回退只在选中槽失败时才发生，且不改任何持久状态。
- **U-Boot 自更新有变砖风险**：`e2631flash` 直接擦写 mtd0 的 U-Boot 区（0x20000..0xC0000），写入期间掉电会留下
  半写镜像，只能靠串口 + 厂商/第二级引导链路恢复。因此每次写前写后记录 mtd0 sha256、先零写入核对暂存镜像的
  payload CRC32、单独一次写入并读回比较；没有串口恢复手段时不执行。命令只写用户给定范围，明确拒绝 secondboot
  （0x00000..0x20000）与 env（0xC0000..0xE0000）。
- **env 写回尚未真机演练**：0017 的 `e2631env save` 只在代码/CI 层证明（白名单、五步顺序、坏块预检、
  0xE0000 保留扇区、幂等与全 FF 校验）；第一次真实 save 必须并入用户批准的设备会话，先 `e2631env diff`
  核对变化键，再写并回读；写入期间掉电同样只影响 env 块（厂商链/我们的链都会回退默认 env，且厂商
  `zteboot_do_settings` 会重建），但写前仍要记录 0xC0000 块 sha256。
- **checkpatch**：本系列 0 errors、26 reviewed warnings（0008/0009 各 0/0；0011 与 0012 各 0 errors / 2 warnings；
  0013 0/0；0014 0 errors / 4 warnings；0015 0 errors / 5 warnings；0016 0/0；0017 0 errors / 2 warnings；
  0018/0019 各 0 errors / 1 warning、0020 0 errors / 1 warning、0021 0/0、0022 0 errors / 1 warning），
  均为已核对的已知项——11 条 "does MAINTAINERS
  need updating?"（patch 0001 新建 `arch/arm/mach-zx279128s/`、patch 0002 新建 `board/zte/zxhn-e2631/`、
  patch 0005 新建 `drivers/spi/spi-zx.c`、patch 0006 新增 `board/zte/zxhn-e2631/e2631boot.c`、
  patch 0011 新增 `e2631soc.c|.h`、patch 0012 新增 `e2631net.c|.h`、patch 0014 新增 `e2631flash.c`、
  patch 0017 新增 `e2631env.c|.h`、patch 0018 新增 `drivers/net/zx279128s_mdio.c`/`zx279128s_eth.h`、
  patch 0019 新增 `drivers/net/zx279128s_eth.c`、patch 0022 新增 `doc/usage/cmd/e2631net.rst` 各一条；
  checkpatch 按单个 patch 判断，0021 的 MAINTAINERS 更新与 0022 不在同一个 patch 里，所以这些提醒必然存在）
  + 2 条 "Use the livetree API"
  （板级 `fdtdec_setup_mem_size_base()`/`fdtdec_setup_memory_banksize()` 是 U-Boot 板级读 /memory 的
  常规 API，checkpatch 的 LIVETREE 检查对板级代码是误报）+ 8 条 "Possible new command - make sure you
  add a test"（`e2631boot`/`e2631soc`/`e2631refclk`/`e2631flash`/`e2631verify`/`e2631slot`/
  `e2631env`/`e2631net` 都是自用板级命令，U-Boot 树里没有对应 DM 测试；验收是只读子命令 + 真机会话，
  不新增测试目录），
  以及 0015 的 5 条 PREFER_IF（这几处 `#if CONFIG_IS_ENABLED(CMD_MTD_WRITE)` 必须编译期生效才能把原始 mtd
  写入口真正编掉，运行期 `if` 达不到目的，属于结构性豁免）。E2 的六处 `mb()` 与 `extern` 提示已在
  patch 0018-0020 定稿时修掉（内存屏障加注释、MDIO 驱动改包含共享头而不是自己写原型）。0021/0022 这两个
  文档 patch 无法消除上述提醒（checkpatch 逐 patch 独立判断、CMD_TEST 不读文档）。因此 CI 对这四类做**显式**
  豁免：`--ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF`，列表在 workflow 里逐类注释并被运行期断言
  钉成“恰好这四类”，其余任何 warning 或任何 error 都会让 uboot-build 失败，所以 CI 的 checkpatch 结果是
  0 errors / 0 warnings。上面这份逐类分解是本机不加 ignore 时的原始统计；源码依据（2805、3560-3568、
  2670-2674 行）与两次构建的实测见
  [evidence/uboot-checkpatch-maintainers-20261122.md](../evidence/uboot-checkpatch-maintainers-20261122.md)。自用 fork，不提交上游。
- 本机不编译（硬规则）；编译证据只能来自 task-44 的 CI run。

## 7. 与后续阶段的关系

- **A2**：SPIFC + SPI-NAND 只读路径已由 patch 0005 交付（RAM 链内 `mtd list`/`mtd read`）。芯片 ID
  实测为 `0xCD/0x71`，用现成 FORESEE `F35SQA001G` 条目（若出现 `0xC9` 再加 heyangtek 条目）。
- **A3**：槽位感知启动已由 patch 0006/0007 交付（`e2631boot` + 只读 env）；class-1 跨槽回退由 0016 交付
  （选中槽 uImage 坏时改启另一槽一次，无状态、不写 flash/env，见 §2 补丁 0016）。`TEXT_BASE` 已在 task-55 对齐
  secondboot 入口 `0x47F00000`；C1b 的 CP15 归一化由 0011 交付（`e2631soc` + bootm 钩子）；env 写回由 0017
  交付（`e2631env`，白名单 + 厂商键快照 + 五步写，第一次真机 save 待批准）。剩下的启动计数（B1 phase 2）、
  按活动槽位切换根文件系统放在后续会话。
- **A5**：厂商 `board_eth_init()` 的参考时钟/SerDes/管脚初始化由 patch 0012 交付（`e2631refclk` 前后 dump +
  `e2631boot` 钩子）。内核侧签名（PHY 10-13 + PCIe `14c3:7906`/`14c3:790a`）由下一次零写入真机会话记录；
  网络协议栈/网络引导不在本阶段。
- **A6**：PCIe 端点复位/供电线（pin 2 / pin 51）由 patch 0013 交付；A5 内核侧签名里的两个 endpoint
  依赖这两根线为高。下一次零写入会话先 `e2631refclk`（或直接 `e2631boot`）再按 §4 第 12 条验收。
- **E2**：U-Boot 自己的以太网驱动由 patch 0018/0019/0020 交付（MDIO + 交换机/TM/DMA + lan1 驱动 +
  `e2631net`），命令集 `mii info`/`dhcp`/`ping`/`tftp` 见 §5.4；autoboot rescue 与网络引导回退是 E3，
  PHY fixup/多口是 M2。第一次真机会话另行安排。
- **刷写阶段（原计划的 A3，重命名为 A4/路径 C）**：D-U1 已交付 `e2631flash`/`e2631verify`/`e2631slot`（0014）与唯一
  MTD 写入口（0015）。下一次真机会话先做零写入的暂存镜像 CRC 校验与槽位表核对，再单独一次写 mtd0 U-Boot 区并
  读回比较；写前写后 mtd0 sha256、串口恢复链路与用户批准缺一不可。在此之前，A1/A2/A3/A5/A6 都不写 flash。
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
  复查厂商 `pll_cfg_fractional` 后补上 `0x94000054` 的 bit26（分数 PLL 使能位），patch sha256 与 tree 随之重钉；
  CI run `44929440623`（head `9a2b6fc`）SUCCESS：banner `g9a7538311376`、`u-boot.bin` 450,904 B
  sha256 `e3c52ba4132910b1807708eadfc8a6f7c7b9740782e84df6afa6d2e7a861ecf2`、mtd0 镜像
  sha256 `367b8fa63364d302bc13ade4dd6f9edcd2a49a706a906207fb33e9dc8ced8b41`、env 块 `6eee153b…` 未变；
  详见 [evidence/uboot-a5-20261122.md](../evidence/uboot-a5-20261122.md)。

- 2026-11-22（A6，patch 0013）：在 0012 的 `e2631_pinmux_gpio_init()` 之后补厂商 `zte_gpio_init()` 的两段尾部特例（`0x47f2f61c` 索引 0x33→pin 2、`0x47f2f66c` 索引 0x32→pin 51，无视表值 0 置 1），并保留厂商在 loop B 之前的 4 ms 间隔（pin 2 → `mdelay(4)` → pin 51），修掉 A5 会话残留的 PCIe endpoint 缺失（只有 root port、没有 `14c3:7906`/`14c3:790a`）。v3 重钉结果 tree `f04e5ed9525c87bddc329b24a311dfa4a302b750`（13 个 patch），patch sha256 `f6d52c559973dad5cc4e375f72e7dd3ce57b63c8b15f1ca95e5bb011346d5f2c`。设计见 [a6-pcie-endpoint-reset-design.md](a6-pcie-endpoint-reset-design.md)；CI run `44935007253`（head `c6a89a8`）SUCCESS：banner `g85c7367a3106`、`u-boot.bin` 450,936 B sha256 `3bf182f148226b6f64696a05bba5d75ca59426747f87eee3f13c5d2b0269423a`、mtd0 镜像 sha256 `f6d179daa952db910afacde635f259fbe5f2eabf97f3d8aa07d2c09540979a42`、装配后 header sha256 `508c325cbc59b22e4cd78f43d3b51a05926f4725fc1f4bbe0ec7536905d303e9`、env 块 `6eee153b…` 未变；详见 [evidence/uboot-a6-20261122.md](../evidence/uboot-a6-20261122.md)。A6 真机零写入会话（verify-docs）GREEN：`0x94407014`=0xdb2c、`0x944070d4`=0xe028，两条 `PCIe Gen.1 x1 link up` 与 endpoint `14c3:7906`/`14c3:790a` 出现，`mt7915e`/MT7916 就绪、eth 四 PHY 保持、mtd0 未变；详见 [uboot-a6-device-session-20261122.md](../evidence/uboot-a6-device-session-20261122.md)。

- 2026-11-22（D-U1，patch 0014/0015）：新增 `board/zte/zxhn-e2631/e2631flash.c`（`e2631flash` 块对齐擦除→FF 校验→写入→读回比较、RAM 或 NAND 偏移两种来源、1 MiB bounce buffer、payload/readback CRC32、DO NOT POWER OFF；`e2631verify` 只读 CRC32；`e2631slot` 复用 `e2631boot` 扫描函数）并新增 `CONFIG_CMD_MTD_WRITE`（默认 y，本 defconfig 关闭，把原始 `mtd write/erase` 子命令编掉，使 `e2631flash` 成为镜像里唯一的 MTD 写入口）。重钉结果 tree `31843b38628ccf9c3e0b542ec4db014b6612755d`（15 个 patch；0014 sha256 `0bfb4302…943110`、0015 sha256 `84bfc65f…c8f3b`）。设计见 [a7-self-flash-design.md](a7-self-flash-design.md)；CI run `44943940449`（head `0d53ccc`）SUCCESS：banner `g85df6772a444`、`u-boot.bin` 456,416 B sha256 `21b0d804483c7cbb82e2ca92968b6706ed0f740429e6e6c935bf34e16a881af8`、mtd0 镜像 sha256 `b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a`、装配后 header sha256 `95b7a80a46f38933178f06542c9df24183b8c0cdb441aabfb5e6a70699ec8ee7`、env 块 `6eee153b…` 未变、checkpatch 0 errors / 20 warnings；详见 [evidence/uboot-du1-20261122.md](../evidence/uboot-du1-20261122.md)。真机零写入验收与写入会话均待用户批准。
- 2026-11-22（U-0016，patch 0016，class-1 跨槽回退）：`e2631boot` 拆出 `e2631_try_boot_slot()`，选中槽的 uImage 任一级校验失败时打印
  `slot%d unusable (<reason>), falling back to slot%d (cspboot class-1 parity)` 并改试另一槽一次；两槽都失败时打印逐槽诊断表并回控制台，
  不调用 `bootm`。回退无状态（不改版本头/serial、不计数、不写 flash、不碰 env，只影响本次启动），健康路径与 `e2631slot` 代码不变。
  重钉结果 tree `13c92c68921fa781634beb50d0eaffd50e9a7648`（16 个 patch；0016 sha256
  `7838e8a22dd46996c9ccb31f9fe116e194641d2a26f548e9854548bfefc62461`）。CI uboot-build run `44945090940`（head `8811a5b`）SUCCESS：
  banner `g61456c131301`、`u-boot.bin` 457,680 B sha256 `31d2b6d858a9df1660bceb6390f731f03e457d3cad84b82144d53bf20f659977`、
  mtd0 镜像 sha256 `869866d4239219975ea90a310697ecbccdd77181a00c314dd97bdec36fdc58ea`、装配后 header sha256
  `4d3176d1f5be903274161b134af37d0b666c5cdfb4f5d3c75a2d974e97aeadbb`、env 块 `6eee153b…` 未变、checkpatch 0 errors / 20 warnings（0016 本身 0/0）；
  新增 CI 门禁（源码 `e2631_try_boot_slot`/两条日志串 + 二进制 `falling back to slot`）；详见
  [evidence/uboot-class1-fallback-20261122.md](../evidence/uboot-class1-fallback-20261122.md)。
- 2026-11-22（U-0017，patch 0017，env 写回）：新增 `board/zte/zxhn-e2631/e2631env.c|.h`（`e2631env check/diff/save`；
  `save` = 坏块预检→擦除→全 0xFF 校验→写入→回读逐字节比较，4 条编译期布局断言；白名单只放 `e2631_*` 与
  `bootdelay`，导出前恢复 `bootcmd/bootargs/memsize/versioninfo` 快照；写前后断言 `0xE0000..0xFFFFF` 仍为全 0xFF；
  无变化时 `nothing to write` 且不擦除）。`e2631boot.c` 在覆盖 `bootcmd` 前调用 `e2631_env_snapshot()`；`env/mtd.c` 的
  `.save` 保持 NULL、`CONFIG_CMD_SAVEENV`/`ERASEENV` 保持关闭，`e2631env` 成为镜像里唯一的 env 写入口。
  重钉结果 tree `fd511f1e4aff26c8f0bf3187b139eaaf45fbd5bc`（17 个 patch；0017 sha256
  `da21478e0fe7c53fdf14f59e81ea3da86733b63998926f25e84b3675f96eca0d`）。与设计稿的偏差（不 wire `.save`、
  坏 CRC 非空块拒绝重建）见
  [docs/U-Boot-env写回与启动计数设计-2026-11-22.md](../docs/U-Boot-env写回与启动计数设计-2026-11-22.md) §12。
  CI uboot-build run `44978733720`（head `b42e44d`）SUCCESS：banner `g9a4028535269`、`u-boot.bin` 465,600 B
  sha256 `e46f9cf0fdffe7173b7acbdcdc9f9506002c0f09fa6fbf850fa10c31255a9bee`、mtd0 镜像 sha256
  `e2a76f753152403a42bd7f8faf01c5c3cab1c44a4b12c2744600fc4296784e16`、装配后 header sha256
  `1bd3fa812368af4cc2eaa5c8ea5fabf82bd8f679886d378e362e491790813f91`、env 块 `6eee153b…` 未变、
  checkpatch 0 errors / 22 warnings（0017 本身 0/2）；门禁新增 env 配置/源码顺序/静态断言/0xE0000/白名单 4 site 检查；
  详见 [evidence/uboot-env-writeback-20261122.md](../evidence/uboot-env-writeback-20261122.md)。第一次真机
  `e2631env save` 待用户批准。
- 2026-11-22（E2，patch 0018-0020，U-Boot 以太网）：新增 MDIO 控制器驱动（`drivers/net/zx279128s_mdio.c` +
  共享头 `drivers/net/zx279128s_eth.h`）、交换机/流量管理器/DMA 初始化（`drivers/net/zx279128s_eth.c`）、
  U-Boot `eth_ops` 驱动与 `e2631net` 状态命令；DTS 增加 `mdio@9a101000`（PHY12 = lan1）与
  `ethernet@92000000`（`zte,switch-port = 2`）；defconfig 增加
  `CMD_DHCP/CMD_MII/CMD_PING/NET_RANDOM_ETHADDR/ETH_ZX279128S/MDIO_ZX279128S`。`e2631flash`/`e2631verify`
  新增 16 MiB 网络 DMA arena（`0x45000000..0x45FFFFFF`）重叠保护（编译期断言 + 运行期 `e2631_check_ram_range()`），
  `e2631_net_refclk_init()` 改为幂等并在驱动 `start()` 中第二次调用（patch-0012 寄存器序列不变）。
  重钉结果 tree `10ade1ec0f7a3a7943783d6ba6146840fda6d4bf`（20 个 patch；0018/0019/0020 sha256
  `9a1e079b…`/`3e615397…`/`d8b9eb9f…`）。设计见 [e2-net-driver-design.md](e2-net-driver-design.md)，
  真机验收命令见 §5.4。CI uboot-build run `44981256822`（head `a9c2596`）SUCCESS：banner
  `U-Boot 2027.01-rc2-gdfcc418f2f3f`、`u-boot.bin` 494,208 B sha256
  `842192f1713c6b63a7fe5fe49714229a45c17000abdc0bb17d6a34df533f4425`、mtd0 镜像 sha256
  `b384cca09ebdd959f01205e68e86faa3e6911ee9718f87d547ea8c18d55700c9`、装配后 header sha256
  `efafbd0a68b32ca2674e44040d5beca619f742f6584ce586cb31aee66949ab73`、env 块 `6eee153b…` 未变、
  checkpatch 0 errors / 25 reviewed warnings；详见
  [evidence/uboot-e2-20261122.md](../evidence/uboot-e2-20261122.md)。
- 2026-11-22（checkpatch 收口，patch 0021/0022）：新增一段 MAINTAINERS 条目（`ZTE ZXHN E2631 (SANECHIPS
  ZX279128S)`，maintainer QC3284，覆盖板级/SoC/以太网·MDIO·SPI 驱动/DTS/defconfig/命令文档）与
  `doc/usage/cmd/e2631net.rst` 用法页；两个 patch 不含代码改动，0001-0020 的 patch 文件与 sha256 均未变。
  重钉结果 tree `c812dd8689ccf146deeec83bd0e74067c8b8abc5`（22 个 patch；0021 sha256 `c66643e1…`、
  0022 sha256 `680435c3…`）。CI uboot-build run `44982672016`（head `0edf1bf`）SUCCESS：banner
  `U-Boot 2027.01-rc2-g6bd1fbd087ba`、`u-boot.bin` 494,208 B sha256
  `75ba2e66b448f08fba42fedffae4b21cd84ad082cb32de6f0d3474effc5ca11d`、crc32 `e13c0526`、mtd0 镜像 sha256
  `9200fb3594845104ded8b32d494f1702728d9660d07512709931154b9317c739`、env 块 `6eee153b…` 未变。系列
  checkpatch 仍为 0 errors / 26 warnings（0021 为 0/0、0022 为 0/1：checkpatch 逐 patch 独立判断，前面的
  MAINTAINERS 更新无法消掉后面的新文件提醒；CMD_TEST 也不读文档），逐条分类、源码依据与 CI 级四类豁免
  方案见 [evidence/uboot-checkpatch-maintainers-20261122.md](../evidence/uboot-checkpatch-maintainers-20261122.md)。
- 2026-11-22（checkpatch CI 门禁，option A）：checkpatch 步骤改为硬门禁——`--ignore
  FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF`（恰好四类，workflow 里逐类注释原因），ignore 列表在运行期
  被断言为这四类，其余任何 warning 或任何 error 都使 uboot-build 失败；README §4 item 6/§6 写明门禁与原始
  逐类统计，evidence 文件改名为
  [evidence/uboot-checkpatch-maintainers-20261122.md](../evidence/uboot-checkpatch-maintainers-20261122.md)。
  CI uboot-build run `44983615483`（head `828dc1f`）SUCCESS，checkpatch.txt 为 **0 errors / 0 warnings**；
  banner `U-Boot 2027.01-rc2-gc7ac1db6eb7f`、`u-boot.bin` 494,208 B sha256
  `a07f0e56862a63d1e338c9072dfa2af95ed4aaa51e5fdd28a9441c39a9f4b9f7`、crc32 `201bd325`、mtd0 镜像 sha256
  `f7ef0bdb5471b425c6493f3d3655e09663a1e0484abcf19a3f4f0ce7c0a63bf3`、crc32 `3e070d23`、env 块 `6eee153b…`
  未变、post-am tree 仍为 `c812dd86…`。与 run `44982672016` 相比，两份 `u-boot.bin` 只差 28 个字节（全部是
  版本 token 与构建时间戳，见 evidence §4）——U-Boot 版本串含 `git describe` 的 HEAD token（CI 的 `git am`
  用构建时刻做 committer date）且编译期嵌入 `U_BOOT_DATE`/`U_BOOT_TIME`，所以同一 tree 重跑也不会字节相同；
  设备会话使用 run `44983615483` 这件 0/0 产物。若需要字节级可复现构建，可选加 `git am
  --committer-date-is-author-date` + `SOURCE_DATE_EPOCH`（evidence §6，待 Lead 决定）。
