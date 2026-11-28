# E2631 自定义 U-Boot：A1 RAM 链 + A2 SPI-NAND 只读路径 + A3 槽位启动（kit 侧交付物）

本目录是 task-43/task-44/task-47/task-50/task-51/task-53 与 C1b 修复的产物：对 U-Boot 主线的 patch 系列
（0001/0002 为 A1 移植，0003 为首个 CI 构建暴露的链接修复，0004 为 A1 串口修复，0005 为 A2 的 SPIFC +
SPI-NAND 只读路径，0006/0007 为 A3 的槽位感知启动 + 只读 env，0008/0009 为 C1a 的 bootm ATAGS 修复 +
env 日志名称诊断，0010 为产品入口 0x47F00000，0011 为跳转前的 CP15 归一化，0012 为厂商 board_eth_init
的网络参考时钟/SerDes/管脚补齐，0013 为厂商在板级表回放后补驱动的两根 GPIO（PCIe 端点复位/供电线），0014 为自更新命令 `e2631flash`/`e2631verify`/`e2631slot`（flash 源先经 1 MiB bounce buffer 暂存，payload 与 readback 各打印 CRC32），0015 为 `CONFIG_CMD_MTD_WRITE` 开关（我们的 defconfig 关掉它，`e2631flash` 成为镜像里唯一的 MTD 写入口），0016 为 class-1 跨槽回退（选中槽 uImage 校验失败时自动改启另一槽一次，只回退本次启动、不写 flash/env），0017 为 `e2631env` 环境写回（白名单 + 厂商键快照 + 坏块预检/擦除/全 FF/写入/回读五步），0018/0019/0020 为 E2 U-Boot 以太网（MDIO 总线 + 交换机/流量管理器/DMA 初始化 + datapath 驱动与 `e2631net` 调试命令；固定 16 MiB DMA arena，单口 lan1），0021/0022 为 checkpatch 收口（新增一段 MAINTAINERS 条目覆盖板级/SoC/驱动/DTS/defconfig/命令文档，新增 `doc/usage/cmd/e2631net.rst` 用法页；两个 patch 都不含代码改动）
、0025 为 defconfig-only 瘦身（`# CONFIG_MMC is not set` 一行；MMC=n → BLK=n 级联丢掉 EFI loader / 标准启动 / FAT / 块缓存，控制台少 `bootefi`/`eficonfig`/`bootflow`/`bcb`，`bootm` 与全部 `e2631*` 命令不变）、0026/0027/0028 为 E4 v1 救援模式（bl-mt798x-dhcpd 的最小 TCP/DHCP 栈 + `e2631flash` 五步写 job API + `e2631rescue` 的 DHCP/HTTP 救援页；只写 mtd0 的 U-Boot 区 `0x20000..0xC0000`（655360 B，写长度 0xA0000，源指针=镜像首地址）并复用 `e2631flash` 五步写，带 SHA-256 契约与结构校验，不自动重启）、0029 为厂商 TOPCRM 软复位（`0x94000044`）替换占位 `reset_cpu()`、0030 为环境区读取重试与失败现场打印（3 次重试仍失败才回落默认环境，打印偏移、CRC32 与前 64 字节）、0031 为 F2 的 TX 诊断（描述符变体运行时可切换，默认仍是内核的 directed-egress 描述符；`e2631net tx` 发广播探测帧并打印全量 TX/桥块状态，`e2631net sbrg allow` 回放 egress mask 复位值；只加诊断，不改默认发送路径）、0032 为 F2 根因修复（交换转发控制 `0x1cc000` 写 `17` 而不是误植的 `BIT(17)`：内核驱动与厂商 U-Boot 都写 `17`，写错时 TM 收下描述符并报完成、交换机却不转发、帧不上线；另新增 `e2631net bmu` 寄存器转储、`0x1fc` 改称 `dma err`、SBRG 状态常显）、0034 为冷启动救援修复（`do_e2631rescue()` 在 `net_init()`/`eth_init()` 之前显式调用幂等的 `e2631_net_refclk_init()`：flash 冷启动直接进救援时 `e2631boot` 还没跑过，网络参考时钟/SerDes 未建立，内部 PHY 的 MDIO 不应答、`phy_startup()` 约 5 s 后超时（-110，`no usable Ethernet device`）；RAM 验收当时能过只是因为先跑过 `e2631net`/`e2631boot`）、0035 为恢复键进救援（board_late_init 里裸 MMIO 轮询 reset/GPIO18 与 mesh/GPIO20，任一键连续按住 2 s 就把 `bootcmd` 在 RAM 内改成 `e2631rescue`；松手取消，不写 env/flash，另加只读 `e2631key` 诊断命令）、0036 为 E4 v2 的共享槽核心与槽写入器（Linux 侧 `e2631-fwslot` 逻辑编译进 U-Boot，`e2631_slotcore.c` 与 kit `tests/native/uboot/` 副本逐字节一致并有主机 fixture；`e2631fwslot.c` 是镜像里唯一写固件槽的 MTD shim）、0037 为 `rootfs_data` 擦除/全 FF 校验与一次性启动槽覆盖（只认名为 `rootfs_data` 且偏移/长度精确匹配的分区；`e2631_next_slot` 只改本次启动，不写 env）、0038 为救援页的分阶段环境写（begin/poll/end，同一五步写、同一白名单/厂商快照）、0039 为 E4 v2.1 多功能救援（`/slots`、`/env`、`/backup` 只读接口与 `/firmware`、`/boot`、`/factory`、`/env`、`/console` 写/控制接口；固件包只写目标槽，bootloader/slot/rootfs_data/env 各有唯一 owner），0040/0041 为 task-94 防御性自检（所有 SHA-256 使用显式清零的 `sha256_context`，哈希前校验上传窗口基址/长度；`rescue_fmt` 在输出游标离开已登记缓冲区时打印 FATAL 并拒绝渲染，`/status`、`/slots` 返回 500 `output cursor corrupted`）、0042 为 E4 v3 的尺寸回收（defconfig 关掉 `CONFIG_CMD_FDT` 与 `CONFIG_CMD_TFTPBOOT`，实测省 12,380 B；代价是控制台没有 `fdt`/`tftp`，主机到 U-Boot 的网络传输改由救援页承担，串口恢复仍可用 `loadx` + `e2631flash`）、0043 为产品串比较对齐 Linux（`E2631_PRODUCT_LEN` 16→17，主机 fixture 增第 17 字节向量、涨到 52 项）、0044 为 `POST /console` 原始长度检查（257 B 以上返回 400 `only a single command is allowed`，不再静默截断并执行前缀）、0045 为 E4 v3 系统信息与启动日志（GET `/sysinfo` 固定键序含 CP15/SPI-NAND id/时钟寄存器，GET `/log` 返回进入救援时抓取的 console 记录快照、`?download=1` 加附件头；`/status` 增 `log_bytes`/`log_overflow`）、0046 为只读完整性校验（POST `/integrity` 对 mtd0 `0x20000..0xC0000` 算 CRC32+SHA-256，可带 `expect` 或 `X-E2631-Expected-Sha256` 比对，返回 `match=ok|mismatch|absent`）、0047 为槽与 rootfs 备份流（`/backup?part=slot0|slot1|rootfs|header`，整槽用 1 MiB cache-aligned bounce、先两遍读算 CRC32/SHA-256 再流）、0048 为确认重启与蓝灯心跳（POST `/reboot` 需 `X-E2631-Confirm: reboot`，先回 `result=accepted` 再等 `DATA_SENT` 约 300 ms 调 `reset_cpu()`；救援期间 GPIO0 bit8 按 1 Hz 闪、退出时恢复原 DIR/DATA）、0049 为 DHCP 配置进 env（`e2631_dhcp_ipaddr`/`netmask`/`pool_start`/`pool_size` 优先于旧 `dhcpd_pool_*`，非法值回落默认并在 `/status` 报 `dhcp_source=fallback` 与 `dhcp_warning`）、0052 为 task-93 的 DHCP 池误报修复（干净环境下 `/status` 曾报 `dhcp_source=fallback`：`rescue_dhcp_load()` 用 `s_addr & 0xff` 取到的是一字节 192 而不是主机八位组 1，默认池 100..200 因此被误判为包含服务器；改为经 `ntohl()` 取最后一字节并把校验收进 `e2631dhcp.h` 的主机 fixture）、0053 为 task-95 的救援页面流式发送（v3 页面 gzip 24,904 B 超过 16,384 B 的响应缓冲，`GET /` 曾因 `rescue_reply()` 装不下而直接关连接、空回复；改为 4 KiB 分块经 `mtk_tcp_send_data()` + `DATA_SENT` 推进流式发送，块算术收进 `e2631page.h` 并有主机 fixture）、0054 为 task-95 的请求 URI 与连接释放修复（URI 不再复制进 96 B 的 `path[96]`，改指向请求头原始行，`/console` 的 257 B 长度门在未截断的原始 query 上判定；`REMOTE_CLOSED` 连接现在释放 pdata 与 1 MiB 备份 bounce buffer——此前每个死连接泄漏约 17.7 KB 加 1 MiB，三次大备份后 4 MiB 堆耗尽、新连接 calloc 失败即被 RST，表现为 257 B 请求后救援'卡死'）。0055 为 task-97 的最小 DNS 应答器（移植上游 bl-mt798x-dhcpd 的 DNS 服务器，A 记录应答，`dnsd_domain` 默认 `failsafe.lan`，host fixture 29 项）、0056 为最小 RFC-854 telnet 服务器（TCP 23，单连接、IAC ECHO/SGA、行编辑、4 KiB 输出环、console record 捕获、Ctrl-C 走 `mtk_tcp_abort_request()`；`telnet_port` 可改端口）、0057 为救援页控制台端点（`POST /console/exec` multipart `cmd`/可选 `token`、`POST /console/poll` JSON 输出、`POST /console/abort`、`POST /console/clear`；与 telnetd 共享唯一执行槽，忙时 503/`console is busy`，网络命令结束后在主循环重初始化 eth 并重注册 DHCP/DNS handler，`/console?cmd=` 保留为回退）、0058 为环境候选块与 flash 键集对齐（`fdtcontroladdr` 与 `serial@...` 的 stdio 等运行时键在对比前临时改回 flash 值/删除，真正的 no-change 写不再被厂商白名单拒绝）、0059 为 `/env` 写路径的 DHCP 池范围规则（`e2631_dhcp_pool_ok()` 检查池与服务器地址冲突，非法返回 400 而不是 403）。
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
| patch 0023 | `uboot-port/patches/0023-drivers-net-report-TX-failures-and-keep-timed-out-BMU-buffers.patch`（F2-a：send 失败不再静默——打印原因、所需 buffer 数、BMU 状态；移植内核 pending-retry，超时请求留给下一次收取） |
| patch 0023 sha256 | `e38d0545d0463101e19a26760a29fc7ebbc6b8b5782cce836ffc9d5e725c87d3` |
| patch 0024 | `uboot-port/patches/0024-board-zte-assert-the-staging-kernel-copy-and-DMA-arena-geometry.patch`（防御性 geometry：staging / kernel copy / DMA arena 的编译期断言） |
| patch 0024 sha256 | `8bf4e048b1726c795b04ebb92ec361e7a91814fded24f83b3e1432a88b0f79e1` |
| patch 0025 | `uboot-port/patches/0025-configs-zxhn-e2631-drop-the-unused-EFI-MMC-FAT-and-standard-boot.patch`（defconfig 瘦身：`# CONFIG_MMC is not set` → 级联丢掉 EFI/标准启动/FAT/块缓存） |

| patch 0025 sha256 | `af158e9fb09bc1853a0ff7bf5a32d7201b9ebf8dd04a02a1087e0cccf76218d4` |
| patch 0026 | `uboot-port/patches/0026-net-import-the-minimal-TCP-stack-and-DHCP-server-for.patch`（E4 v1：bl-mt798x-dhcpd 的 TCP/DHCP 栈 + 本树 legacy net API 适配 + `arp_wait_clear()` + `PROT_TCP` 钩子） |
| patch 0026 sha256 | `727b6f1f48db406c6c24ffc86c101fefad4780f7b93ad17ef424b5d5958b9682` |
| patch 0027 | `uboot-port/patches/0027-e2631flash-expose-the-five-step-writer-for-the-rescu.patch`（E4 v1：`e2631flash.h` 把五步写暴露成 job API，救援页复用同一 writer） |
| patch 0027 sha256 | `e6a52064d33e0fe43570462f10764e8c41e03d6bfc800918f951aa4db9a5b2a0` |
| patch 0028 | `uboot-port/patches/0028-board-zte-add-the-web-bootloader-rescue-e2631rescue.patch`（E4 v1：`e2631rescue` DHCP + HTTP + gzip 页面 + SHA-256/确认头契约 + mtd0 五步写；task-78 修正写窗口为 `0x20000..0xC0000`、源指针=镜像首地址） |
| patch 0028 sha256 | `ef442221929cfcd817f84784cd6f83cb9576a7e76652831b829057ca3865dd21` |
| patch 0029 | `uboot-port/patches/0029-board-zte-reset-the-SoC-through-the-vendor-TOPCRM-re.patch`（task-76：厂商 `reset` = 50 ms 延迟 + 向 `TOPCRM+0x44`（`0x94000044`）写 1） |
| patch 0029 sha256 | `a016c9dfc1a62e1f8721d603bd773437f273b204f46ffeb1794c61fdfbfe81ea` |
| patch 0030 | `uboot-port/patches/0030-env-retry-the-MTD-environment-read-and-dump-the-fail.patch`（task-77/U-0031：`env_mtd_load()` 整段读+import 重试 3 次，最终失败打印偏移、stored/computed/buffer CRC32 与前 64 字节；env 仍只读） |
| patch 0030 sha256 | `5c171e5965b295df0dc16c06eb49684cd7504d1a97bcf06de1b02682ef56994a` |
| patch 0031 | `uboot-port/patches/0031-drivers-net-add-the-TX-probe-and-the-bridge-block-dump.patch`（task-78/F2b：TX 描述符变体运行期开关 + `e2631net tx/mode/sbrg` 探针；默认仍是内核描述符，不新增写路径） |
| patch 0031 sha256 | `d431d1fb805da056a2ac2f851f31cf45f14e6fc37de8d20d5ff95023af001fc3` |
| patch 0032 | `uboot-port/patches/0032-drivers-net-write-17-to-the-switch-forward-control.patch`（task-78/F2c：交换转发控制 `0x1cc000` 写 `17`（与内核驱动/厂商 U-Boot 一致），修正误植的 `BIT(17)`；新增 `e2631net bmu` 转储，`0x1fc` 按厂商语义改称 `dma err`，SBRG 状态常显） |
| patch 0032 sha256 | `8d1d11fdeae32fef0e2cccd364ffe1cad0dcaf3fc38f90728f8b5250e68d58a5` |
| patch 0033 | `uboot-port/patches/0033-board-zte-match-the-rescue-HTTP-header-names-case-in.patch`（task-78/E4 phase-1：请求头名比较两侧都折成小写；头名/头值辅助函数移入无依赖的 `e2631http.h`；主机侧 fixture `uboot-port/tests/rescue_headers_test.c` 在 CI 回放混合大小写请求） |
| patch 0033 sha256 | `5657f596688825f2111fd3fea3108fbe93e2973231f28947d0c2faa56d2e21ca` |
| patch 0034 | `uboot-port/patches/0034-board-zte-bring-up-the-network-clocks-for-a-cold-rescue.patch`（task-78/E4 cold boot：`do_e2631rescue()` 在 `net_init()`/`eth_init()` 前调用幂等的 `e2631_net_refclk_init()`，让救援能从 flash 冷启动提示符独立工作；CI 断言该调用留在 `do_e2631rescue()` 内） |
| patch 0034 sha256 | `eef4625c0e3689acf7055de3636b2edc5a7a4d0f4e89cc0c3ee0161fc0c1e986` |
| patch 0035 | `uboot-port/patches/0035-board-zte-enter-the-web-rescue-when-a-recovery-key-is-held.patch`（task-82：`board_late_init()` 里裸 MMIO 轮询 reset/GPIO18 与 mesh/GPIO20（bank1 bit2/bit4，低=按下），任一键连续按住 2 s → `env_set("bootcmd", "e2631rescue")`（仅 RAM）并打印提示；松手取消；新增只读 `e2631key` 命令） |
| patch 0035 sha256 | `9bb04c566e4319debba7a32509a2d07e37e45fe5166ca8229eef75c92d0734e4` |
| patch 0036 | `uboot-port/patches/0036-board-zte-add-the-shared-slot-core-and-the-slot-writ.patch`（E4 v2：共享槽核心 `e2631_slotcore.{c,h}` + 槽写入器 `e2631fwslot.{c,h}`；包解析/身份/守卫/槽扫描校验/版本头打标，slot 区唯一写者） |
| patch 0036 sha256 | `0496364d698de5e4e042d07654f1ed7e1aba9235d4130ba5205c58f0a85f24cb` |
| patch 0037 | `uboot-port/patches/0037-board-zte-add-the-rootfs_data-reset-and-the-one-shot.patch`（E4 v2：`e2631factory` 只擦/校验 `rootfs_data`（按名核对 `0x3360000`/`0x4A0000`，不匹配即拒绝）；DTS 只加这一个 fixed partition；`e2631_next_slot` 一次性启动槽覆盖） |
| patch 0037 sha256 | `4e71152c02de9fce7a8165dee5e29b97a05999edd37e29d3aafd9d68eb75f5f3` |
| patch 0038 | `uboot-port/patches/0038-board-zte-expose-a-staged-env-write-to-the-web-rescu.patch`（E4 v2：`e2631env` 导出 begin/poll/end 分阶段 env 写，复用同一五步/白名单/厂商快照，写者仍只有 `e2631env.c`） |
| patch 0038 sha256 | `8f39cbbb3cd37099167b4cb0aa07ac84436f3802fd9db6e6b54bac80502661f9` |
| patch 0039 | `uboot-port/patches/0039-board-zte-extend-the-web-rescue-to-the-v2.1-endpoint.patch`（E4 v2.1：`e2631rescue` 增加 GET `/slots`、`/env`、`/backup` 与 POST `/firmware`、`/boot`、`/factory`、`/env`、`/console`；console 记录尾部捕获 4 KiB；备份按 16 KiB 流式；所有写只启动 owner 的状态机） |
| patch 0039 sha256 | `41a80fc113357ed3abdf7647ada25d6b85edf3f35f9c82798bca9ca706e8a5af` |
| patch 0040 | `uboot-port/patches/0040-rescue-harden-the-digests-against-uninitialised-state.patch`（task-94 防御：所有 SHA-256 走显式清零的 `sha256_context`；`rescue_sha256()` 校验上传窗口基址/长度，越界打印 FATAL 并拒绝；`sha256_csum_wd()` 被替换，CI 禁止其回归） |
| patch 0040 sha256 | `d274ff0f586caefa0a7fb77caa59e0e515af02829062639129a89a537077112e` |
| patch 0041 | `uboot-port/patches/0041-rescue-stop-rendering-when-the-output-cursor-is-corrupted.patch`（task-94 防御：`rescue_fmt()` 在已登记缓冲区内校验 `*p`/`*left`，失配即 FATAL 并拒绝渲染；`/status`、`/slots` 返回 500 `output cursor corrupted`；状态渲染末尾校验 `p == buf + (bufsz - left)`） |
| patch 0041 sha256 | `cf03f0e239e286551cb24f619c8d45fc4fd27d4b74a8d7df7164b6e953c64e1b` |
| patch 0042 | `uboot-port/patches/0042-drop-the-fdt-and-tftp-commands.patch`（E4 v3 尺寸回收：defconfig 关 `CONFIG_CMD_FDT` 与 `CONFIG_CMD_TFTPBOOT`，实测 8,229 + 4,151 = 12,380 B；网络传输由救援页承担） |
| patch 0042 sha256 | `6f322294061909aa36c74de87c8f618d6fb019da47775e74b84ec422947516c8` |
| patch 0043 | `uboot-port/patches/0043-board-zte-compare-the-17-byte-product-string-like-Li.patch`（E4 v3：`E2631_PRODUCT_LEN` 16→17，与 Linux `e2631-fwslot` 的 `sizeof(PRODUCT)-1` 一致；fixture 增加第 17 字节向量） |
| patch 0043 sha256 | `5bbe5d2b6b91384de357c49b94c9f5610713512a860385cdbc679e24a0e9068b` |
| patch 0044 | `uboot-port/patches/0044-board-zte-reject-an-over-long-console-command-instead.patch`（E4 v3：`rescue_query_raw_len()` 在解码前检查原始长度，>256 B 返回 400 `only a single command is allowed`） |
| patch 0044 sha256 | `aa0e9b0a69e33bfbf077e0023dde0bdba686ca5bec428de4c1be513bf03e63ac` |
| patch 0045 | `uboot-port/patches/0045-board-zte-report-the-system-state-and-the-boot-log.patch`（E4 v3：GET `/sysinfo`、`/log` 与 `/status` 的 `log_bytes`/`log_overflow`；CP15 读取经 `e2631soc.c` 导出） |
| patch 0045 sha256 | `65a8751b1d6daa42d54d3ffe5271f0a138754aeb79bfd851126852b66ad85166` |
| patch 0046 | `uboot-port/patches/0046-board-zte-add-the-read-only-flash-integrity-check.patch`（E4 v3：POST `/integrity`，mtd0 `0x20000..0xC0000` 的 CRC32+SHA-256 与可选 expect 比对；GET 405、busy 409、读失败 500） |
| patch 0046 sha256 | `746fead6b0a265de3b7684cff16cc7d1c90bf15fc91c3dd49ce36b4ad634bc0b` |
| patch 0047 | `uboot-port/patches/0047-board-zte-stream-the-slot-and-rootfs-backups.patch`（E4 v3：`/backup` 增加 slot0/slot1/rootfs/header，整槽 1 MiB cache-aligned bounce、先两遍读再流；`/status` 报 `backup`/`backup_part`） |
| patch 0047 sha256 | `1960f78df83062ec95d93115162ad93a2d139813a97961d461de21393badc4e3` |
| patch 0048 | `uboot-port/patches/0048-board-zte-add-the-confirmed-reboot-and-the-blue-LED-.patch`（E4 v3：POST `/reboot` 需 confirm 头、先 accepted 后约 300 ms 复位；蓝灯 GPIO0 bit8 1 Hz 心跳并在退出时恢复 DIR/DATA） |
| patch 0048 sha256 | `5f5dba995c699f03189e7fd1e0eb6906790d8afdb97e679eb9b2bc0820d5e0b0` |
| patch 0049 | `uboot-port/patches/0049-board-zte-let-the-environment-move-the-DHCP-server.patch`（E4 v3：`e2631_dhcp_*` 优先于旧 `dhcpd_pool_*`/内置默认；非法值回落并在 `/status` 报 fallback+warning；`/env` 对四键做语义校验） |
| patch 0049 sha256 | `ba15e88c0095e65e934e1fb8829e988e8f1e7c3fb9d9f5b6a5d74367af67d904` |
| patch 0050 | `uboot-port/patches/0050-rescue-include-the-timestamp-header.patch`（task-92 构建修复：`e2631rescue.c` 显式 include `timestamp.h`，`/sysinfo` 的 `U_BOOT_DATE`/`U_BOOT_TIME` 才能编译） |
| patch 0050 sha256 | `cbdaed605b5ddb5f958d8290c9b55250722bb3fbbcb09ccfc5d24c9c02d30791` |
| patch 0051 | `uboot-port/patches/0051-drop-the-mii-command.patch`（task-92 P2：defconfig 关掉 `CONFIG_CMD_MII`，实测省 11,520 B，把统一 v3 构建从 410,040 B 压回 398,520 B） |
| patch 0051 sha256 | `db9df403d25d8faa5ff6d3f1647f32850d8cc50d20cf80656e0f1e110e5f2230` |
| patch 0052 | `uboot-port/patches/0052-rescue-read-the-DHCP-pool-host-octet-through-ntohl.patch`（task-93：DHCP 池校验改经 `ntohl()` 取主机八位组，收进 `e2631dhcp.h`；主机 fixture `uboot-port/tests/dhcp_pool_test.c` 覆盖干净默认、冲突边界与 1..254 范围，CI 打印 `rescue dhcp pool fixture: PASS (14 checks)`） |
| patch 0052 sha256 | `c001ef53485f3eb04bb870c99bebe6583b26ed8738cacf5ad3d2d21e3dd47f5c` |
| patch 0053 | `uboot-port/patches/0053-rescue-stream-the-rescue-page.patch`（task-95：`GET /` 的 24,904 B gzip 页面按 4 KiB 分块流式发送，不再拷进 16 KiB 的 `c->out`；`e2631page.h` 提供分块算术，主机 fixture `uboot-port/tests/page_stream_test.c` 覆盖长度边界与末块） |
| patch 0053 sha256 | `0633333af61a80af68df2aa5f27b212dd0c76a5e4e9982d2d81764b5b828aba0` |
| patch 0054 | `uboot-port/patches/0054-rescue-keep-the-URI-untruncated-and-release-dead-connections.patch`（task-95：请求 URI 指向原始头行、不再截断进 96 B 缓冲；`e2631query.h` 提供原始 query 长度与 256 B 门；`REMOTE_CLOSED` 释放 pdata/备份缓冲，主机 fixture `uboot-port/tests/console_query_test.c` 覆盖 256/257 边界与 275 B 请求行） |
| patch 0054 sha256 | `caac484bb3b2b4640eac0fd618baa5e9773058c7624f5c9d65f064b96f8084d9` |
| patch 0055 | `uboot-port/patches/0055-net-add-the-minimal-DNS-responder-for-the-rescue-pag.patch`（task-97：最小 DNS 服务，A 记录、NXDOMAIN/NODATA、前一 UDP handler 链；主机 fixture `uboot-port/tests/dnsd_test.c` 29 项） |
| patch 0055 sha256 | `d20aa3d04a1c326e75a827fe0f1dc8a87b5e0b7515c2ad283aed647be041fb96` |
| patch 0056 | `uboot-port/patches/0056-net-add-the-minimal-telnet-server-for-the-rescue-pag.patch`（task-97：最小 RFC-854 telnetd，TCP 23/`telnet_port`，单连接、IAC、行编辑、console record 捕获、Ctrl-C abort） |
| patch 0056 sha256 | `c6d8e38038c38e78a6277eedceee88b1e616723f77ba1ae7eae9e9a3bc8fc59f` |
| patch 0057 | `uboot-port/patches/0057-rescue-run-console-commands-from-the-web-page-task-9.patch`（task-97：`/console/exec`、`/console/poll`、`/console/abort`、`/console/clear`，与 telnetd 共享执行槽，`e2631webconsole.h` 主机 fixture 13 项） |
| patch 0057 sha256 | `df6203b04844e53849c33a475c3f3501826e49b62dc858162456465679943d71` |
| patch 0058 | `uboot-port/patches/0058-env-align-the-candidate-block-with-the-flash-key-set.patch`（task-97：环境候选块与 flash 基线键集对齐，运行时键不参与 diff；`e2631env_align.h` 主机 fixture 13 项） |
| patch 0058 sha256 | `e2a251f0c0776c4a989ebe0e69e64978493146a0f795809c23101d88e3d4f899` |
| patch 0059 | `uboot-port/patches/0059-rescue-apply-the-pool-range-rule-to-the-env-write-pa.patch`（task-97：`/env` 写路径的 DHCP 池范围规则，冲突/越界 400；DHCP pool fixture 由 14 项扩到 18 项） |
| patch 0059 sha256 | `032a3a7fb4311cfa633fb39a172896d3f52862b196d3498df86f47f093e4c886` |
| am 之后 tree | `f8144b84cda597ad387d87ee39c6b50a2bbd6898`（与机器无关，59 个 patch） |
| TEXT_BASE | `0x47F00000` |
| 载荷上限 | `0x9F800` 字节 |
| 构建可复现 | `E2631_UBOOT_SOURCE_DATE_EPOCH=1795103079`（固定 banner 时间）+ `git am --committer-date-is-author-date`（固定版本 token）；同 pin 两次 CI 构建字节一致（task-69 item d，见 §4 item 15） |

以上 pin 值同 [uboot-port/commits.env](commits.env)（构建可复现行的两项固定写在 workflow 与 commits.env，见 §4 item 15）；CI 必须按"commit → 每个 patch sha256 → 结果 tree"三段校验，
补丁数量由 `uboot-port/patches/` 目录决定，不写死。

最省带宽的取基线方式（只取一个 SHA）：

```sh
mkdir u-boot && cd u-boot
git init -q .
git remote add origin https://github.com/u-boot/u-boot.git
git fetch -q --depth 1 origin c1958b5f6cce03956d309ce422b5d9f819955d4a
git -c advice.detachedHead=false checkout -q FETCH_HEAD
git -c user.name=ci -c user.email=ci@localhost am ../uboot-port/patches/*.patch

test "$(git rev-parse HEAD^{tree})" = 0b48c04ad18e8df251a1ec93a2614b3a6337e06b
```

## 2. 新增/修改的文件

| 文件 | 作用 |
| --- | --- |
| `arch/arm/Kconfig` | 新增 `ARCH_ZX279128`（select CPU_V7A），source mach Kconfig |
| `arch/arm/Makefile` | `machine-$(CONFIG_ARCH_ZX279128) += zx279128s` |
| `arch/arm/mach-zx279128s/Kconfig` | `SYS_SOC="zx279128s"`、`TARGET_ZXHN_E2631`、source 板级 Kconfig |
| `arch/arm/mach-zx279128s/Makefile` | A1 无 SoC 私有代码（secondboot 已完成初始化），只留占位说明 |
| `board/zte/zxhn-e2631/Kconfig` | `SYS_BOARD`/`SYS_VENDOR`/`SYS_CONFIG_NAME` |

| `board/zte/zxhn-e2631/Makefile` | 编译 `zxhn-e2631.o`、`e2631boot.o`（A3）、`e2631soc.o`（C1b）、`e2631net.o`（A5）、`e2631flash.o`（D-U1）、`e2631env.o`（U-0017）与 `e2631rescue.o`（E4） |
| `board/zte/zxhn-e2631/e2631boot.c` | A3：`e2631boot` 命令（槽位扫描/选择/uImage 校验/`bootm`）+ `board_late_init()` 覆盖 `bootcmd`；C1b：`bootm` 前调用 `e2631_soc_prepare_linux()`；A5：`bootm` 前调用 `e2631_net_refclk_init()`；U-0016：选中槽 uImage 失败时经 `e2631_try_boot_slot()` 改试另一槽一次（class-1 回退，无 flash/env 写）；U-0017：`board_late_init()` 在覆盖 `bootcmd` 之前调用 `e2631_env_snapshot()` 保存四个厂商键；task-82：`board_late_init()` 末尾裸 MMIO 轮询 reset(GPIO18)/mesh(GPIO20)，任一键连续按 2 s 就把 `bootcmd` 在 RAM 内改成 `e2631rescue`（另有只读 `e2631key` 命令） |
| `board/zte/zxhn-e2631/e2631soc.c` | C1b：厂商顺序的 CP15 清理 + `e2631soc` 只读报告命令（SCTLR/CLIDR/TTBR0/VBAR/ACTLR 前后值；不启动、不写 flash/env） |
| `board/zte/zxhn-e2631/e2631soc.h` | `e2631_soc_prepare_linux()` 原型（`e2631boot.c` 与 `e2631soc.c` 共用一条代码路径） |
| `board/zte/zxhn-e2631/e2631net.c` | A5：厂商 `board_eth_init()` 的参考时钟/SerDes/CRM2/管脚序列（pinmux 六个整字、只驱动八个输出、`0x9400000C` 的 `bits[21:20]` 时钟选择）+ `e2631refclk` 前后 dump 命令（不启动、不写 flash/env）；E2 起 `e2631_net_refclk_init()` 幂等（`refclk_done`），`e2631boot` 与以太网驱动的 `start()` 可以各调一次 |
| `board/zte/zxhn-e2631/e2631net.h` | `e2631_net_refclk_init()` 原型（`e2631boot.c` 与 `e2631net.c` 共用一条代码路径） |
| `board/zte/zxhn-e2631/e2631flash.c` | D-U1：`e2631flash`（块对齐擦除→全 0xFF 校验→写入→读回逐字节比较，RAM 或 NAND 偏移两种来源，1 MiB bounce buffer，payload/readback CRC32，DO NOT POWER OFF）、`e2631verify`（只读 CRC32）与 `e2631slot`（复用 `e2631boot` 扫描函数打印槽位表）；E2 起拒绝任何落在 16 MiB 网络 DMA arena 里的 RAM 源（`static_assert` + 运行期 `e2631_check_ram_range()`），`e2631verify` 用同一检查 |
| `board/zte/zxhn-e2631/e2631env.c` | U-0017：`e2631env check/diff/save`（唯一 env 写入口）；`save` = 坏块预检→擦除→全 0xFF 校验→写入→回读逐字节比较，只用 `CONFIG_ENV_OFFSET`/`CONFIG_ENV_SIZE` 常量（4 条编译期断言），白名单只放 `e2631_*` 与 `bootdelay`，导出前恢复 `bootcmd`/`bootargs`/`memsize`/`versioninfo` 快照，写前后断言 `0xE0000..0xFFFFF` 仍为全 0xFF；无变化时打印 `nothing to write` 且不擦除 |
| `board/zte/zxhn-e2631/e2631env.h` | `e2631_env_snapshot()` 原型（`e2631boot.c` 与 `e2631env.c` 共用） |

| `board/zte/zxhn-e2631/zxhn-e2631.c` | `dram_init`/`dram_init_banksize` 从内嵌 DT 读 256 MiB；0029 起 `reset_cpu()` 走厂商 TOPCRM 软复位（`mdelay(50)` + `writel(1, 0x94000044)`，写后自旋） |
| `board/zte/zxhn-e2631/e2631flash.h` | E4 起暴露五步写 job API（`e2631_flash_begin/erase/blank_check/write_image/readback/compare/end`），救援页只经它写 mtd0，不新增第二个 MTD 写实现 |
| `board/zte/zxhn-e2631/e2631rescue.c` | E4 v1：`e2631rescue` 命令（DHCP + 极简 HTTP + gzip 救援页；0034 起 `do_e2631rescue()` 先调幂等的 `e2631_net_refclk_init()`，保证冷启动第一条命令即可用）；GET `/`、GET `/status`、POST `/flash?mode=validate|write`（655360 B 原始 body、`X-E2631-SHA256`/`X-E2631-Confirm: write` 契约、结构校验），校验通过后经 `e2631_flash_*` 五步写 mtd0 `0x20000..0xC0000`（源指针=镜像首地址，写长度 0xA0000）；不写 env/保留区、不自动重启 |
| `board/zte/zxhn-e2631/e2631_slotcore.{c,h}` | E4 v2（0036）：Linux 侧 `e2631-fwslot` 的纯逻辑（固件包解析、身份/守卫、槽扫描与校验、版本头打标）编进 U-Boot；与 kit `tests/native/uboot/` 副本逐字节一致，CI 主机 fixture 编译运行（51 checks） |
| `board/zte/zxhn-e2631/e2631fwslot.{c,h}` | E4 v2（0036）：固件槽 MTD shim——`e2631_fwslot_validate/begin/poll/end` 状态机，坏块预检→擦整槽→按 128 KiB 写 body→回读 slot 扫描/校验→写 512 B 版本头；镜像里唯一写 slot 区的模块 |
| `board/zte/zxhn-e2631/e2631factory.{c,h}` | E4 v2（0037）：`rootfs_data` 擦除 + 全 FF 校验；按名找分区并核对 `mtd->offset==0x3360000 && size==0x4A0000`，不匹配直接 `rootfs_data layout mismatch` |
| `board/zte/zxhn-e2631/e2631boot.c`（0037 增量） | E4 v2：`e2631_next_slot` 一次性覆盖本次启动槽位（只读 `slots[].valid`，非法值打印忽略；不改 env/flash） |
| `board/zte/zxhn-e2631/e2631env.{c,h}`（0038 增量） | E4 v2：导出 `e2631_env_write_begin/poll/end` 分阶段写（同一五步、同一白名单与厂商快照；写者仍只有 `e2631env.c`） |
| `board/zte/zxhn-e2631/e2631rescue.c`（0039 增量） | E4 v2.1：GET `/slots`、`/env`、`/backup`，POST `/firmware`、`/boot`、`/factory`、`/env`、`/console`；写全部经四个 owner 的状态机，备份只读 16 KiB 流式 |
| `tests/native/uboot/e2631_slotcore.{c,h}`；`uboot-port/tests/slotcore_test.c`；`uboot-port/tests/shim/` | E4 v2（0036）：kit 侧 slotcore 副本、主机 fixture 与最小 shim；CI 比对副本后编译运行 |
| `board/zte/zxhn-e2631/e2631http.h` | E4 phase-1（0033）：无依赖的 HTTP/1.x 头名/头值辅助函数（头名大小写不敏感，RFC 7230 §3.2）；`e2631rescue.c` 与主机 fixture 共用同一份实现 |
| `net/mtk_dnsd.c` / `include/net/mtk_dnsd.h` | task-97（0055）：最小 DNS 服务（移植上游 bl-mt798x-dhcpd，GPL-2.0）；A 记录应答、NXDOMAIN/NODATA、前一 UDP handler 链；纯 inline 线格式 helper 由 `uboot-port/tests/dnsd_test.c`（29 项）在主机上验证 |
| `net/mtk_telnetd.c` / `include/net/mtk_telnetd.h` | task-97（0056）：最小 RFC-854 telnet 服务器（TCP 23，环境 `telnet_port` 可改）；单连接、IAC ECHO/SGA、行编辑、4 KiB 输出环、console record 捕获，Ctrl-C 触发 `mtk_tcp_abort_request()`；与 web console 共享唯一执行槽（弱符号 `failsafe_console_is_busy`） |
| `board/zte/zxhn-e2631/e2631webconsole.h` | task-97（0057）：`/console/exec` 的 multipart 边界/字段解析与 JSON 转义（纯 inline），由 `uboot-port/tests/webconsole_test.c`（13 项）验证 |
| `board/zte/zxhn-e2631/e2631env_align.h` | task-97（0058）：环境候选块与 flash 基线的 per-key 规则（白名单 KEEP、运行时键改回基线值或删除），由 `uboot-port/tests/env_align_test.c`（13 项）验证 |
| `uboot-port/tests/dnsd_test.c` / `env_align_test.c` / `webconsole_test.c` | task-97 主机 fixture：CI 在 `git am` 之后、交叉编译之前编译运行（DNS 29 项、env align 13 项、web console 13 项）；DHCP pool fixture 同时扩到 18 项 |
| `uboot-port/tests/rescue_headers_test.c` | E4 phase-1（0033）：kit 仓库侧主机 fixture（不进树），用捕获的混合大小写 GET/POST 头块回放真实辅助函数；CI 在 `git am` 之后用宿主机 gcc 编译运行 |
| `net/mtk_tcp.c` / `net/mtk_tcp_priv.h` / `include/net/mtk_tcp.h` | E4：从 bl-mt798x-dhcpd（GPL-2.0，`e4cf4dc7`）移植的最小 TCP 栈，公开 API 头与私有协议头分开 |
| `net/mtk_dhcpd.c` / `include/net/mtk_dhcpd.h` | E4：从同一上游移植的 DHCP 服务器（去掉自带 console 命令，只留 start/stop/is_running） |
| `net/arp.c` / `net/arp.h`；`net/net.c`；`net/Kconfig` / `net/Makefile` | E4：新增 `arp_wait_clear()`；`CONFIG_MTK_TCP` 时在 `PROT_TCP` 分发处把包交给 `mtk_receive_tcp()`；新增 `MTK_TCP`/`MTK_TCP_VERBOSE`/`MTK_DHCPD` Kconfig 与 Makefile 条目 |
| `board/zte/zxhn-e2631/MAINTAINERS` | 维护者与文件范围 |
| `include/configs/zx279128s_zte_zxhn-e2631.h` | `CFG_SYS_SDRAM_BASE=0x40000000`、`CFG_PL011_CLOCK=0`、`CFG_SYS_HZ_CLOCK=500000000` |
| `arch/arm/dts/zx279128s-zte-zxhn-e2631.dts` | memory / PL011 / A9 global timer / 500 MHz fixed-clock；E2 起还有 `mdio@9a101000`（`zte,zx279128s-mdio` + `ethernet-phy@c`）与 `ethernet@92000000`（`zte,zx279128s-gmac`、`phy-handle=<&phy12>`、`zte,switch-port=<2>`）；E4 v2（0037）起 SPI-NAND 下只声明一个 `fixed-partitions` 子分区 `rootfs_data`（`0x03360000`/`0x004A0000`），其它区域仍按绝对偏移访问 |
| `drivers/net/zx279128s_eth.h` | E2：交换机/流量管理器/DMA 寄存器与 16 MiB arena 偏移、`e2631_net_refclk_init()` 原型（0018 引入，MDIO 驱动与以太网驱动共用） |
| `drivers/net/zx279128s_mdio.c` | E2：clause-22 MDIO 主控制器（`0x9a101000`）；首次传输时懒初始化（先跑板级参考时钟 hook），支持 devad 0 的 read/write；`mii` 命令可直接使用 |
| `drivers/net/zx279128s_eth.c` | E2：`zx_hw_init()`（复位/时钟门控/PP/索引表/TM 队列表/BMU/DMA 环/交换机/MAC）+ U-Boot `eth_ops`（BMU 缓冲池、TX 描述符与 TX_DONE、RX queue 0 轮询、free_pkt 归还） + `e2631net` 状态命令；`start()` 调 `e2631_net_refclk_init()`（幂等） |
| `drivers/net/Kconfig`；`drivers/net/Makefile` | E2：`MDIO_ZX279128S` 与 `ETH_ZX279128S`（`depends on DM_ETH && NET_LEGACY`，select `DM_MDIO`/PHYLIB/PHY_GIGE；不能同时 depends DM_MDIO 与 select PHYLIB，否则 Kconfig 递归依赖） |
| `arch/arm/dts/Makefile` | `dtb-$(CONFIG_TARGET_ZXHN_E2631) += zx279128s-zte-zxhn-e2631.dtb` |

| `configs/zx279128s_zte_zxhn-e2631_defconfig`；D-U1 增加 `# CONFIG_CMD_MTD_WRITE is not set`，让 `e2631flash` 成为镜像里唯一的 MTD 写入口（0015）；E4 增加 `CONFIG_MTK_TCP`/`CONFIG_MTK_DHCPD`/`CONFIG_SHA256`（`MTK_TCP_VERBOSE` 关闭）；E4 v2.1 增加 `CONFIG_CONSOLE_RECORD=y` 与 `CONFIG_CONSOLE_RECORD_OUT_SIZE=0x4000` | A1/A2/A3 配置（已用 `make savedefconfig` 归一；A3 增加 `BOARD_LATE_INIT`/`SUPPORT_PASSING_ATAGS`/`ENV_IS_IN_MTD` 与只读 env 参数；0011 移除 `CONFIG_SKIP_LOWLEVEL_INIT`，让标准 `cpu_init_cp15`/`cpu_init_crit` 在入口重新生效）；E2 增加 `CMD_DHCP`/`CMD_MII`/`CMD_PING`/`NET_RANDOM_ETHADDR`/`ETH_ZX279128S`/`MDIO_ZX279128S`（`NET`/`NET_LEGACY`/`DM_ETH`/`DM_MDIO`/`PHYLIB`/`PHY_GIGE`/`CMD_NET`/`CMD_TFTPBOOT` 是默认 y，savedefconfig 不重复写） |
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
| 恢复键进救援（0035） | 无（纯软件） | 上电后按住 reset 或 mesh 键约 6 s（覆盖 secondboot→`board_late_init` 的 2 s 轮询窗口）即把 `bootcmd` 在 RAM 内改成 `e2631rescue`；松手取消、不写 env/flash；`e2631key` 只读打印两键电平 |
| 救援模式（E4 v1） | `e2631rescue` + 0x46000000 上传区（0026-0028；0034 冷启动补参考时钟） | 串口进入；lan1 上跑 DHCP（192.168.1.1/24，池从 .100）与极简 HTTP；页面只刷 mtd0 的 U-Boot 区 `0x20000..0xC0000`（655360 B 整镜像，源指针=镜像首地址，SHA-256 + 结构校验后再经 `e2631_flash_*` 五步写）；secondboot `0x0..0x20000`、env `0xC0000..0xE0000` 与保留区 `0xE0000..0xFFFFF` 一律不碰；成功不自动重启，Ctrl-C 退出 |
| 软复位 | 厂商 TOPCRM `0x94000044`（0029） | `reset_cpu()` 先 `mdelay(50)`，再向 `TOPCRM+0x44` 写 1；BootROM 随后重跑 secondboot 并重新加载 U-Boot。没有 L2/SCU/时钟副作用，也不新增 MTD 写路径 |

### 内存图（staging / kernel copy / DMA arena）

E2 失败分析（[evidence/e2-session-failure-analysis-20261122.md](../evidence/e2-session-failure-analysis-20261122.md) §4）
用实测值核对了这三个区间；**它们互不重叠**，Lead 卡上早期的 `0x4554xxxx` 是十进制/十六进制换算错误：
3,491,146 B = `0x35454A`，从 `0x42000000` 起算止于 `0x4235454A`，不是 `0x4554xxxx`。

| 区域 | 地址范围 | 大小 / 说明 |
| --- | --- | --- |
| DRAM | `0x40000000..0x4FFFFFFF` | 256 MiB，secondboot 已初始化 |
| ATAGS | `0x40000100..0x400001FF` | `E2631_ATAGS_ADDR`，`CFG_SYS_SDRAM_BASE+0x100`；0008 起 `board_late_init()` 设置 `bi_boot_params` |
| kernel copy | `0x40008000..0x403FFFFF`（最大） | `E2631_KERNEL_LOAD_ADDR`，uImage data 拷入处；`E2631_KERNEL_MAX = 0x400000-0x20`，所以最大止于 `0x403FFFE0` |
| uImage staging | `0x42000000..` | `CONFIG_SYS_LOAD_ADDR`（tftp/loadx 的目标）。E2 会话实测 3,491,146 B → 止于 `0x4235454A`，距 arena 还有 46.8 MiB；只有 staged 数据超过 48 MiB（`0x45000000-0x42000000`）才会碰到 arena |
| e2631flash bounce | `0x44000000..0x440FFFFF` | 1 MiB；flash→flash 更新时先读入，避免边擦边读 |

| net DMA arena | `0x45000000..0x45FFFFFF` | 16 MiB，BMU 缓冲池 + TM 表 + RX/TX 环；网络启动后硬件会写入 |
| rescue upload buffer | `0x46000000..0x460FFFFF` | E4 v1：1 MiB，HTTP 上传的 655360 B mtd0 镜像先落在这里；`static_assert` 保证它高于 arena 且低于 `0x4f000000`，网络工作区不会被覆盖 |
| firmware staging | `0x46100000..0x47CFFFFF` | E4 v2：`/firmware` 上传的固件包暂存区（上限 `E2631_FW_STAGE_MAX=0x1C00000`，包上限 `0x1BE0214`）；编译期断言它 ≥ `0x46100000`、高出 arena 16 MiB、止于 `0x47F00000` 链接区之下 |
| relocated U-Boot | DRAM 顶部（`< 0x50000000`） | 重定位目标；`e2631flash` 只允许 `0x40000000..0x4EFFFFFF` 作为 RAM 源 |

0024 把这张图写成编译期断言：arena 必须高于 staging 且低于 DRAM 顶、bounce 高于 staging、
staging 到 arena 之间至少留 48 MiB、kernel copy 窗口必须止于 staging 之下。
这些断言防的是**将来**把地址改坏或 staged 镜像变大；它们不是 E2 失败的修复项。

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


1. `git rev-parse HEAD^{tree}` == `f8144b84cda597ad387d87ee39c6b50a2bbd6898`；每个 patch 的 sha256 与 §1 一致，
   且 `git rev-list --count <baseline>..HEAD` 等于 patch 数量（当前 59）。
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

   `CONFIG_CMD_DHCP=y`、`CONFIG_CMD_MII=y`、`CONFIG_CMD_PING=y`（E4 v3 起还要求
   `# CONFIG_CMD_TFTPBOOT is not set` 与 `# CONFIG_CMD_FDT is not set`）；
   E4 起还要求 `CONFIG_MTK_TCP=y`、`CONFIG_MTK_DHCPD=y`、`CONFIG_SHA256=y` 且
   `# CONFIG_MTK_TCP_VERBOSE is not set`；E4 v2.1 起还要求 `CONFIG_CONSOLE_RECORD=y` 与
   `CONFIG_CONSOLE_RECORD_OUT_SIZE=0x4000`（`/console` 的 4 KiB 尾部捕获）；task-97 起还要求
   `CONFIG_MTK_DNSD=y` 与 `CONFIG_MTK_TELNETD=y`（DNS 与 telnet 服务确实编进镜像）。
3. 镜像尺寸：`size=$(stat -c%s build/u-boot.bin); test "$size" -le 653312`
   （超限就裁命令/驱动；这条对应 mtd0 载荷上限 0x9F800，是刷写阶段的硬前置）。E4 v3 起还要求
   强制尺寸门禁；task-97 起 headroom 由 240 KiB 调为 193,312 B，即
   `size <= 653312 - 193312 = 460000`（460,000 B 自我门；硬上限 653,312 B、打包门 645,120 B 与页 32,768 B 预算不变），
   打印 `E4 v3 size gate: ...`。
4. 入口点：`readelf -h build/u-boot` 的 Entry point 应为 `0x47F00000`（readelf 打印小写 `0x47f00000`，CI 统一转小写比较）。
5. 上传 CI artifact：`u-boot.bin`、`u-boot.map`、`.config`、构建日志；记录 run URL。
6. checkpatch（CI 门禁，见 §6）：CI 以 `--ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF` 跑
   `u-boot/scripts/checkpatch.pl --no-tree --terse`，要求 **0 errors / 0 warnings**。ignore 列表在 workflow 里
   逐类注释，并由运行期断言钉成“恰好这四类”；这四类之外的任何 warning 或任何 error 都会让 uboot-build 失败。
   不加 ignore 时的原始统计是 0 errors / 26 reviewed warnings（0008/0009 各 0/0；0011 与 0012 各 0/2；0013 0/0；
   0014 0/4；0015 0/5；0016 0/0；0017 0/2；0018 修正后 0/1；0019 0/1；0020 0/1；0021 0/0；0022 0/1；
   0036-0039 各 0/0；0040/0041 各 0/0；0042-0049 各 0/0；0050/0051 各 0/0；0052 0/0；0053/0054 各 0/0；0055-0059 各 0/0，无新增豁免），分项与原因见 §6；
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

10. A3/C1b/A5/D-U1/U-0017/E2/E4 二进制：`grep -aq 'e2631boot'`、`'e2631soc'`、`'e2631refclk'`、`'e2631flash'`、
    `'e2631verify'`、`'e2631slot'`、`'e2631env'`、`'e2631net'`、`'e2631rescue'` 与 `'spi-nand0'` 都要在 `build/u-boot.bin` 里命中（槽位/CP15/网络时钟/
    自更新/env/以太网/救援命令与 env 设备名确实链接进镜像），且五条 usage 文本（flash/verify/slot/env/rescue 帮助首行）、
    `DO NOT POWER OFF`、救援页的 `X-E2631-SHA256`/`X-E2631-Confirm: write` 与 E2 的 `lan1 up` 启动日志也能 grep 到。
    E4 v2.1 起二进制还须含 `serve the web failsafe (v1+v2) on lan1`、`X-E2631-Part`、
    `only a single command is allowed`、`rootfs_data` + `layout mismatch`（工厂模块用 `%s` 拼接）、`slot is not bootable`、
    `package size out of range`、`refusing to overwrite a working vendor system`。
    E4 v3 起还须含 `X-E2631-Log-Bytes`、`X-E2631-Expected-Sha256`、`e2631-bootlog.txt`、`method not allowed`。
    task-97 起还须含 `console is busy`、`dnsd: started, resolving`、`cannot start the telnet server`、`cannot start the DNS server`。
    0053/0054 不新增二进制文本（页面响应的 `serve the web failsafe` 帮助串与 400 body 文本均已存在），改用源码 marker 与主机 fixture 断言。
11. A3/C1a/C1b/A5 修复（0008/0009/0011/0012）：`grep -q 'bi_boot_params' board/zte/zxhn-e2631/e2631boot.c`、
    `grep -q 'define ENV_NAME(_name) .name = _name,' include/env_internal.h`、
    `grep -q 'e2631_soc_prepare_linux' board/zte/zxhn-e2631/e2631boot.c`、
    `grep -q 'mcr p15' board/zte/zxhn-e2631/e2631soc.c`、
    `grep -q 'e2631_net_refclk_init' board/zte/zxhn-e2631/e2631boot.c`、
    `grep -q 'E2631_GPIO_PCIE_RST0' board/zte/zxhn-e2631/e2631net.c`、

    `grep -q 'e2631_stage_source' board/zte/zxhn-e2631/e2631flash.c`（0014 的 bounce staging）、
    `grep -q 'e2631_flash_begin' board/zte/zxhn-e2631/e2631rescue.c` 且 `e2631rescue.c` 不含 `mtd_write`/`mtd_erase`
    （E4 复用五步写、没有第二写入口）、`grep -q 'ZX279128S_TOPCRM_SOFT_RST' board/zte/zxhn-e2631/zxhn-e2631.c`
    （0029 的复位路径）、
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
14. D-U1 写入口（0026-0039 起四个 owner）：`.config` 与 defconfig 都必须有 `# CONFIG_CMD_MTD_WRITE is not set`；
    对 `build/u-boot` 反汇编做**调用点白名单**——所有 `mtd_write`/`mtd_erase`/`mtd_special_write_oob` 的
    `bl` 只能落在 `e2631_*` 函数（含内联后的 helper 名）或 `fw_block_erase`/`fw_block_write`/`fa_erase_step`/
    `fa_blank_step` 里；写调用点限定 **7..16 个**，且四个 owner 模式（`e2631_write_range|e2631_erase_range|do_e2631flash`、
    `e2631_fwslot|fw_block_`、`e2631_factory|fa_erase_step`、`e2631_env_write_block|do_e2631env_save|e2631_env_write_poll`）
    各至少 1 个调用点，防止白名单空过。另一个源码层扫描要求 `board/zte/zxhn-e2631/*.c` 里只有
    `e2631flash.c`/`e2631env.c`/`e2631fwslot.c`/`e2631factory.c` 允许出现 MTD 写调用（`e2631boot.c` 与
    `e2631rescue.c` 另由专门门禁断言为 0）。`e2631env.c` 还必须保留 `DO NOT POWER OFF DURING WRITE`、
    `mtd_block_isbad`、`e2631_env_vendor_names` 与 `nothing to write` 四个安全标记；`e2631flash.c` 保留
    `E2631_ENV_OFF`/`E2631_BOOTLOADER_OFF`/`e2631_flash_check`/`DO NOT POWER OFF`/`overlaps secondboot`/
    `overlaps the environment`。
15. 可复现构建（task-69 item d）：pin loader 必须导出 `SOURCE_DATE_EPOCH=$E2631_UBOOT_SOURCE_DATE_EPOCH`
    （`E2631_UBOOT_SOURCE_DATE_EPOCH=1795103079`，U-Boot `Makefile:2327-2351` 用它生成 banner 时间），
    patch 重放必须带 `git am --committer-date-is-author-date`（版本 token 只由 base+patch 决定）。因此 banner
    固定为 `U-Boot 2027.01-rc2-gf355ce89283c (Nov 19 2026 - 15:44:39 +0000)`；同一 head 连续两次 dispatch 的
    `u-boot.bin`/mtd0/`.config`/`u-boot.map` 逐字节相同，证据见
    [evidence/uboot-reproducible-build-20261122.md](../evidence/uboot-reproducible-build-20261122.md)。

16. F2-a + geometry（task-69 items 1/2，patch 0023/0024）：源码形状——`drivers/net/zx279128s_eth.c` 含
    `bmu_alloc_pending`（pending-retry 状态）、send 失败打印 `1 buffer required`（附原因 / BMU 状态 / 计数），
    `e2631net` 打印 BMU alloc 的 failed/late/pending 计数；三处 geometry 断言（driver、`e2631flash.c`、
    `e2631boot.c`）必须存在。二进制必须含 `TX buffer allocation failed`。真机签名（后续会话记录）：
    `dhcp` 失败若由 BMU 分配引起，串口出现该行与 BUF_ALLOC/BUF_ID/FREE_STATUS，`e2631net` 的计数可以区分
    “从未发出”和“发出但没回”；`0x4554xxxx` 的旧说法已按实测更正为 `0x4235454A`（见 §3 内存图）。

17. defconfig 瘦身（task-69，patch 0025）：只加一行 `# CONFIG_MMC is not set`。MMC 在 ARM 上默认 y 且 `select BLK`，
    BLK 又让 `EFI_LOADER`（armv7 默认 y）和 `BOOTSTD`（`default y if BLK`）回来，`FS_FAT`/`FAT_WRITE` 由
    `EFI_LOADER` imply——这些在 E2631 上都没有用武之地（无 eMMC/SD、无 FAT 介质，启动走 `e2631boot` + `bootm`）。
    级联结果：`.config` 少 56 个 `=y` 符号、0 个新增；控制台少 `bootefi`（含 bootmgr/binary 变体）、
    `eficonfig`、`bootflow`、`bcb`（FAT/MMC/PXE 命令本来就没编进去）。CI 断言 `.config` 与 defconfig 不再出现
    MMC/BLK/EFI/BOOTSTD/FAT 栈，并保留 `CMD_BOOTM`/`CMD_MTD`/`CMD_DHCP`/`CMD_TFTPBOOT`/`CMD_MII`/`CMD_PING`/
    `OF_LIBFDT`/`LMB`；`e2631boot`/`e2631flash`/`e2631env`/网络驱动与 MTD 写白名单不变。真机签名：串口命令表
    里不再有上述命令，`bootm` 与全部 `e2631*` 命令仍在。
    实测（run 45988430055）：`u-boot.bin` 494,880 → 320,848 B（**-174,032 B，-35.17%**），距 CI 门禁余量

    324,272 B；56 个 `=y` 符号消失、0 新增。

18. E4 v1 + 复位 + env 重试（0026-0030）：`.config` 含 `CONFIG_MTK_TCP`/`CONFIG_MTK_DHCPD`/`CONFIG_SHA256`；二进制含
    `e2631rescue`、`serve the web failsafe (v1+v2) on lan1`、`X-E2631-SHA256`、`X-E2631-Confirm: write`
    与 `e2631rescue: PASS: mtd0 updated`；源码形状——`e2631rescue.c` 含 `e2631_flash_begin`/`sha256_csum_wd`/
    `e2631_failsafe_html_gz` 且不含 `mtd_write`/`mtd_erase`（写路径唯一），`zxhn-e2631.c` 含
    `ZX279128S_TOPCRM_SOFT_RST` 与 `mdelay(50)`。D-U1 调用点白名单仍覆盖四个 owner（救援页只调
    `e2631_flash_*`/槽/工厂/env 的 API，不新增 writer）。task-78 的写窗口回归门禁断言 `E2631_RESCUE_FLASH_OFF=0x20000`、
    `LEN=0xA0000`、`MTD0_END=0xC0000 == CONFIG_ENV_OFFSET`、源指针是镜像首地址、erase/write/compare 三窗一致；
    task-77 的 env 门禁断言 `ENV_MTD_READ_RETRIES` 与失败现场打印（`env_mtd: stored crc ...`）存在。真机签名（后续零写入会话记录）：进入 `e2631rescue` 后 PC 从 DHCP 取到
    192.168.1.100+ 地址、`GET /` 出现救援页、`GET /status` 的阶段行递增、上传错误 SHA 的镜像被拒绝且

    flash 未擦除；成功路径最后一行是 `e2631rescue: PASS: mtd0 updated, CRC32 0x...` 且不自动重启。
    实测（run 46002766353）：`u-boot.bin` 320,848 → 360,624 B（+39,776 B，+12.40%），超出 Option A 的 34 KB 估算上限 4,960 B；距 mtd0 载荷硬上限余量 292,688 B。
    合并构建（run 46010298863，banner `g6db632ad6e5b`，30 个 patch，tree `3be7118d...`）：`u-boot.bin` 361,448 B
    （较上一构建 +824 B；相对 slim 320,848 B 为 +40,600 B / +12.65%），mtd0 sha256
    `62bf1244d69471e2454be966694421dc2d6f8c8ce427393f7b056837d4893d71`，装配后首 0x800 sha256
    `036d5dc72ee0d0fd020e1a542ee7b93ab750ec3ba1cc700e402ba9acd6ce0f4a`（模板 `19a9d546...`），env 块未变，
    D-U1 白名单当时仍是 4 个 site（0036-0039 之前）；`E4 rescue window gate` / `env retry gate` 均通过，checkpatch 0/0（24 CHECK 均既有）。
19. F2 TX 诊断（0031，task-78）：默认 TX 模式必须仍是内核描述符（源码 `static int zx_tx_mode = ZX_TX_MODE_PP;`），
    源码含 `zx_tx_mode_names` 与 `ZX_SBRG_EGRESS`，二进制含 `e2631net: tx probe`、`switch fwd ctrl` 与 `dump the traffic manager, BMU and DMA registers`；
    D-U1 白名单与救援/env 语义不变。真机签名见 §5 的「F2 TX 出口诊断」小节：`e2631net tx 3` 在某个模式下
    使 `MAC TX frames` 增长/主机抓到广播 ARP，即定位成功。
20. F2 根因修复（0032，task-78）：`ZX_SW_FWD_CTRL_ON` 必须是 `17`（不是 `BIT(17)`），源码含 `zx_cmd_bmu`
    与 `e2631net: switch fwd ctrl 0x%08x (expected 0x%08x)`，二进制含 `switch fwd ctrl` 与
    `dump the traffic manager, BMU and DMA registers`；真机 `e2631net bmu` 的 `switch fwd ctrl` 应读回
    `0x00000011`，且 `e2631net tx 3` 后 `MAC TX frames` 必须增长。
21. E4 救援请求头修复（0033，task-78/E4 phase-1）：`rescue_headers_test.c` 主机 fixture 在 `git am` 之后、
    交叉编译之前编译运行并打印 `rescue header fixture: PASS`；源码含 `e2631_http_header_value`（`e2631rescue.c`）
    与 `e2631_http_name_is`（`e2631http.h`）。二进制里头的比较两侧必须都走大小写折叠。
22. E4 冷启动救援（0034，task-78/E4 cold boot）：`e2631rescue.c` 含 `#include "e2631net.h"`，且 `do_e2631rescue()`
    函数体内含 `e2631_net_refclk_init();`（CI 用 awk 截取该函数再 grep，缺一即失败）；打印
    `cold rescue gate: do_e2631rescue brings up the network reference clocks`。
23. 恢复键进救援（0035，task-82）：awk 截取 `int board_late_init(void)` 后必须 grep 到 `e2631_rescue_key_state`；
    源码必须含 `env_set("bootcmd", "e2631rescue")`、`#define E2631_KEY_RESET … 18`、`#define E2631_KEY_MESH … 20`；
    `e2631boot.c` 不得出现任何 `mtd_write`/`mtd_erase`/`mtd_special_write_oob`；二进制必须含
    `e2631key: reset (gpio18)` 帮助文本。打印
    `key rescue gate: ...`。该任务的 +1 KiB 尺寸门禁只适用于 0035 单独增量；0036-0039 加入后它已被
    E4 v2.1/v3 尺寸门禁取代（见 item 26）。

24. E4 v2 模块 C（0036/0037，task-84）：`tests/native/uboot/e2631_slotcore.{c,h}` 必须在 `git am` 之后与
    `board/zte/zxhn-e2631/` 同名文件逐字节一致（CI `cmp`），主机 fixture 编译运行并打印
    `slot core fixture: PASS (52 checks, package/identity/guard/stamp vectors)`；源码含
    `e2631_fwslot_validate`/`e2631_fwslot_begin`/`e2631_fwslot_poll`/`e2631_factory_begin`/`e2631_factory_poll`；
    U-Boot DTS 含 `fixed-partitions`、`"rootfs_data"`、`0x03360000 0x004a0000`；`e2631boot.c` 含
    `e2631_next_slot_override` 与 `env_get("e2631_next_slot")`，救援侧含 `env_set("e2631_next_slot"`。
25. E4 v2.1 端点（0038/0039，task-84）：救援源码含 `e2631_env_write_begin`/`e2631_env_write_poll`、
    `console_record_reset_enable`、`rescue_console_run`、`hexport_r`、`rescue_backup_part`、`sha256_starts`、
    `X-E2631-Part`；`.config` 含 `CONFIG_CONSOLE_RECORD=y` 与 `CONFIG_CONSOLE_RECORD_OUT_SIZE=0x4000`；
    二进制文本见 item 10 的 v2.1 列表；`e2631env.c` 的 `static_assert(` 仍为 4 条、坏块预检仍在 erase 之前。
26. 四 owner 写者与尺寸预算（0036-0039 起，0042 起改为 v3 预算，task-97 起放宽为 460,000 B）：见 item 14
    的白名单描述；E4 v3 的尺寸门禁是 u-boot.bin ≤ `E2631_UBOOT_HARD_LIMIT`（653,312 B）−
    `E2631_UBOOT_HEADROOM_MIN`（193,312 B）= 460,000 B（自我门；硬上限 653,312 B 与 645,120 B 的打包门不变），
    打印 `E4 v3 size gate: ...`。`E2631_UBOOT_SIZE_BASELINE`（405,368 B，run 46109519805）只用于说明起点。
    旧的 `E2631_UBOOT_V2_*`、`E2631_UBOOT_KEY_*` pin 与对应门禁均已退役（见 commits.env 注释）。

27. task-94 救援自检（0040/0041）：`e2631rescue.c` 必须含 `rescue_fmt_range`、`output cursor corrupted`、`memset(&ctx, 0, sizeof(ctx))`；**整个 `board/zte/zxhn-e2631/` 都不得再出现 `sha256_csum_wd`**；`u-boot.bin` 必须含 `output cursor corrupted` 与 `refusing to hash` 两条文本；打印 `rescue self-check gate: ...`。
28. E4 v3 端点（0042-0049，task-90）：`e2631rescue.c` 必须含 `e2631_query_raw_len`（0044 引入的检查，0054 起移进 `e2631query.h` 并改名）、`rescue_sysinfo_text`、`rescue_log_snapshot`、`rescue_integrity`、`rescue_handle_reboot`、`rescue_led_start`、`rescue_dhcp_load`；`e2631_slotcore.h` 的 `E2631_PRODUCT_LEN` 必须是 17U；`net/mtk_dhcpd.c` 必须含 `e2631_dhcp_pool_start`；二进制文本见 item 10 的 v3 列表；打印 `E4 v3 rescue gate: ...`。
29. slot core 主机 fixture 的检查数（task-90）：fixture 输出必须命中 `(52 checks`（0043 增加第 17 字节产品向量），否则 53 个环境里的老副本会被当成通过。
31. task-93 DHCP 池修复（0052）：`e2631rescue.c` 必须含 `e2631_dhcp_pool_ok(` 且不得再出现 `ip.s_addr & 0xff`（原始网络序掩码）；`e2631dhcp.h` 必须含 `e2631_dhcp_host_octet` 与 `e2631_dhcp_pool_ok`；`uboot-port/tests/dhcp_pool_test.c` 在 `git am` 之后编译运行并打印 `rescue dhcp pool fixture: PASS (14 checks)`；CI 打印 `DHCP pool gate: host octet through ntohl() and the shared pool check`。
32. task-95 页面流式发送（0053）：`e2631rescue.c` 必须含 `rescue_page_start(c`、`e2631_page_chunk_len`、`#define E2631_RESCUE_PAGE_CHUNK 4096U`，且不得再出现 `rescue_reply(c, 200, "OK", "text/html`（页面不能再整块拷进响应缓冲）；`e2631page.h` 提供分块算术；`uboot-port/tests/page_stream_test.c` 在页面生成后按真实 gzip 长度编译运行并打印 `page stream fixture: PASS`；CI 打印 `page stream gate: GET / streams the gzip page in chunks`。
33. task-95 请求解析与连接释放（0054）：`e2631rescue.c` 必须含 `e2631_query_raw_len`、`e2631_console_cmd_len_ok`、`c->path = rest;`，且不得再出现 `snprintf(c->path`；`e2631query.h` 提供原始 query 长度；`rescue_tcp_cb()` 的 `REMOTE_CLOSED` 分支必须调用 `rescue_conn_closed(c);`，备份流结束/失败路径必须先 `c->backup_buf = NULL;` 再关连接；`uboot-port/tests/console_query_test.c` 编译运行并打印 `console query fixture: PASS (14 checks)`；CI 打印 `console query gate: untruncated URI, raw length guard, released connections`。
34. task-97 上游对齐服务（0055-0057）：`.config` 含 `CONFIG_MTK_DNSD=y`、`CONFIG_MTK_TELNETD=y`；
    `net/mtk_dnsd.c`、`net/mtk_telnetd.c`、`net/mtk_dnsd.h`、`e2631webconsole.h`、`e2631env_align.h` 必须存在；
    救援源码含 `rescue_webconsole_exec_start`、`rescue_webconsole_poll`、`webconsole_net_reinit`、
    `failsafe_console_is_busy`、`mtk_telnetd_start`、`mtk_dnsd_start`；telnetd 内有 `weak failsafe_console_is_busy`；
    `net/mtk_dnsd.c` 含 `mtk_dnsd_start`，`net/mtk_telnetd.c` 含 `mtk_telnetd_poll`；DNS fixture（`dnsd_test.c`，
    29 项，编译时用 `-idirafter` 避免 U-Boot 的 `include/stdio.h` 遮住主机 stdio）与 web console fixture
    （`webconsole_test.c`，13 项）在 CI 运行；打印 `task-97 gate: DNS + telnet + web console wired, shared console slot, env candidate aligned`。
35. task-97 env 修复（0058/0059）：`e2631env.c` 必须含 `e2631_env_align_with_baseline`；`e2631env_align.h` 提供
    per-key KEEP/SET/DELETE 规则，`env_align_test.c`（13 项）在 CI 运行并打印 `env align fixture: PASS`；
    `e2631rescue.c` 必须含 `e2631_dhcp_pool_ok(` 且不得再出现 `s_addr & 0xff`；DHCP pool fixture 期望
    `(18 checks`（新加 254 边界与服务器在池内的用例）。
36. task-97 尺寸预算：`E2631_UBOOT_HEADROOM_MIN` 由 245,760 改为 193,312（自我门 460,000 B）；CI 的
    `E4 v3 size gate` 断言随之打印 460000 上限，硬上限 653,312 B、打包门 645,120 B 与页 32,768 B 预算不变。
30. task-92 统一构建（0050/0051）：0050 只加 `#include <timestamp.h>`（checkpatch 0/0；否则 `/sysinfo` 编译失败）；0051 按预算裁决做 P2，defconfig 写 `# CONFIG_CMD_MII is not set`。命令集断言随之改为：bootm/MTD/DHCP/PING/OF_LIBFDT/LMB 必须 `=y`，`# CONFIG_CMD_TFTPBOOT is not set` 必须成立，`CONFIG_CMD_MII` 允许保留或回收（CI 打印 `command set: mii retained|reclaimed`）；页 I18N 保持不动。

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


### F2 TX 出口诊断（task-78；零写入，只发探测帧）

背景与判读见 [evidence/uboot-f2-tx-probe-20261127.md](../evidence/uboot-f2-tx-probe-20261127.md)。零写入会话里
（RAM 链装载后）按顺序跑：

```sh
md.l 0x92340100 1                      # TM status 基线
e2631net bmu                          # switch fwd ctrl 应为 0x00000011；TM/BMU/DMA 窗口
e2631net sbrg                          # 记录 egress 0..4、VLAN 1、learn
e2631net mode pp;         e2631net tx 3
e2631net mode pp-alt;     e2631net tx 3
e2631net mode vendor;     e2631net tx 3
e2631net mode vendor-alt; e2631net tx 3
e2631net sbrg allow;      e2631net mode pp; e2631net tx 3
e2631net                               # 终态；MAC TX frames 增长即修复生效
```

主机在 lan1 上 `tcpdump -e -n` 记录。判据：任意一次 `e2631net tx` 之后 `MAC TX frames` 有端口增长
（或主机收到 60 B 广播 ARP）→ 命中的模式/掩码即根因；若全部不动，保存 `dma err` 前后值、`TM status`
前后差、`last descriptor` 四字与 `SBRG egress`/VLAN 值，作为与厂商链/Linux 链对照的原始数据。
本阶段不写 flash、不改 env；`e2631net sbrg allow` 只写桥块 egress 寄存器，断电即复位。
SBRG 块在 `0x92000000` 基址上：原始读地址是 `0x95883c0`，旧清单里的 `md.l 0x3883c0 1` 读的是错误
地址（会话里读到 0，无意义），0032 起以 `e2631net sbrg` 的输出为准（learn/port ctrl/egress 每次
都会打印）。C2（CPU egress mask）已被现场数据否定，修复窗口的首要判据是 `e2631net bmu` 的
`switch fwd ctrl = 0x00000011`。
2026-11-28 已用零写入 RAM 会话验证通过：修复后第一次 `e2631net tx 3` 就让 MAC TX frames 端口 2 增长、
主机收到广播 ARP（证据 §8.2）；未修复时同一会话的计数与线缆都是零。

### E4 v1 救援模式验收（需要真机会话；会写 mtd0，需用户单独批准）

救援路径只用于把已验证的 `mtd0` 整镜像（655360 B）刷进 U-Boot 区 `0x20000..0xC0000`（写长度 0xA0000，源指针=镜像首地址）。进入前先记录
`mtd0` 全盘 sha256 与 0xC0000 env 块 sha256；整个过程不写 env、不写 secondboot、不自动重启。写入前必须先让
verify-docs 的离线门禁 `e4_prewrite_check.py --archive <artifact 目录>` 通过（30 项检查；kit tree 不一致会失败），
再申请用户批准。

E4 phase-1（2026-11-28）：0033 修复了所有 POST `/flash` 因请求头大小写不匹配而返回 `unsupported request`
的缺陷；每次构建都会先跑主机侧 fixture（`uboot-port/tests/rescue_headers_test.c`），回放混合大小写的
GET/POST 头块，失败即中止构建。真机复测按下面第 1、2、3 步做只读校验即可。

冷启动（0034，2026-11-28）：救援必须能从 **flash 冷启动后的第一个命令** 独立工作。0033 之前从 flash 提示符
直接跑 `e2631rescue` 会得到 `Waiting for PHY auto negotiation to complete......... TIMEOUT !` /
`zx279128s: PHY startup failed (-110)` / `e2631rescue: no usable Ethernet device`：冷启动时 `e2631boot` 还没跑过，
网络参考时钟与 SerDes 没建立，内部 PHY 不应答 MDIO。0034 让 `do_e2631rescue()` 在 `net_init()`/`eth_init()`
之前调用幂等的 `e2631_net_refclk_init()`（与 `e2631boot`、eth 驱动 start 同一函数，`refclk_done` 守卫不会重复下发），
CI 用 awk 截取该函数断言这个调用必须存在。RAM 链验收当时能过，只是因为先跑过 `e2631net`/`e2631boot`。
真机复测（2026-11-28，零 mtd0 写入）：0034 镜像经 userdata 暂存 + `mtd read` + `go` 载入后，
`e2631rescue` 作为**第一条网络命令**即 GREEN——`auto negotiation ... done`、
`zx279128s: lan1 up, 1000 Mbit/s full duplex, MAC 00:41:71:00:00:50`、页面与 validate 均 PASS，
结束时 mtd0/region 未变；证据见 [evidence/e4-coldrescue-0034-20261128.md](../evidence/e4-coldrescue-0034-20261128.md)
（kit 提交 `636b0ae`）。本轮是 warm reset + RAM 载入，不是把 0034 刷进 flash 后的真冷启动；后者仍待第三次写 mtd0 的批准。

控制台输入（重要）：救援服务循环用 `ctrlc()` + `tstc()/getchar()` 轮询控制台，**服务期间不要向 U-Boot 控制台
发送任何字符**（包括回车/换行）；`Ctrl-C` 是唯一被识别的输入，会退出救援（若正在擦/写，会中断并打印危险
WARNING）。因此网页操作期间串口终端应保持静默，等页面显示结果后再决定是否 Ctrl-C。

同一次开机内重复进入（v1 已知限制）：第一次 Ctrl-C 退出后再跑 `e2631rescue`，第二次 `eth_init()` 成功、
也打印 `lan1 up, 1000 Mbit/s`，但主机 ARP/SYN 收不到应答（2026-11-28 写验收 run-1 记录）。静态审计显示网络栈/
驱动没有一次性初始化开关，差异只剩缓存的 PHY 对象（第二次 `genphy_update_link()` 因 `phydev->link=1` 跳过
autoneg 等待）与 `zx_hw_reset()` 之后的硬件状态；根因未定前，把救援当作 **每次开机只用一次**：需要重进时先
`reset` 或断电，再从冷启动提示符进入。

1. U-Boot 提示符执行 `e2631rescue`：串口应打印监听 lan1、本机 IP（192.168.1.1）以及 DHCP/HTTP 启动行；
   接在 lan1 的 PC 应能从 DHCP 拿到 192.168.1.100 起的地址。
2. 浏览器打开 `http://192.168.1.1/`：页面来自内嵌 gzip（Content-Encoding: gzip），不需要外网。
3. 先点“仅校验”上传镜像：页面提示设备端 SHA-256 与浏览器计算值；不匹配（或文件被改）必须报错且不擦除。
   `GET /status` 在此期间不出现 erase/write 阶段。
4. 再以 `mode=write` 上传同一镜像并带确认头：`GET /status` 依次出现
   `stage=erase`→`blank`→`write`→`readback`→`compare`→`done`；串口同步打印阶段与 CRC32。
5. 成功签名：`e2631rescue: PASS: mtd0 updated, CRC32 0x...` 与 `nothing was rebooted; ...`；串口与页面都提示
   需要手动复位（`reset` 或断电）。失败签名：`e2631rescue: FAIL: ...`，不改变 flash 的其它区域。
6. 结束后按 §5 的复位方式重启，再以只读手段复核 mtd0 sha256；写后读回由五步写内部完成，整盘 sha 仍需外部复核。
7. 中途 Ctrl-C 若正在擦/写，串口打印 `e2631rescue: WARNING: the flash update was interrupted...`；这是最危险的
   窗口，只能靠串口 + 厂商/第二级链路恢复，所以实际写之前必须先通过“仅校验”。


### E4 v2.1 多功能救援（0036-0039，task-84；固件/工厂写需单独批准）

页面已扩展为六个标签（系统状态/固件更新/引导区/环境变量/串口台/恢复出厂），契约以
[evidence/e4-v2-contract-design-20261128.md](../evidence/e4-v2-contract-design-20261128.md) §1-§15 为准，
救援源 `e2631rescue.c` 与页面实现必须按同一套 `result=...`/`error=...` 行通信：

- GET `/slots`：两槽 valid/intact/identity/serial/version/header_at，`next_slot`/`next_reason`，mtd5/mtd6/mtd8 分区名；
- GET `/env`：只读 `key=value` 列表（`hexport_r`）；GET `/backup?part=bootloader|tag|wifi|usercfg|defcfg`（默认 bootloader）：
  raw 流 + `X-E2631-CRC32/SHA256/Offset/Length/Part` 头，16 KiB 一块，同一时刻只允许一个备份；
- POST `/firmware?mode=validate|write&slot=auto|0|1`：包暂存 `0x46100000`，14 项结构/CRC/越界/坏块校验 + 槽守卫；
  唯一拒绝是目标槽为 intact 的厂商系统（`refusing to overwrite a working vendor system`）；write 只写目标槽（整槽擦→128 KiB body→
  512 B 版本头→回读校验，失败擦头并报 `verify failed, header erased`）；
- POST `/boot?slot=0|1`：由 `e2631_next_slot` 只对本次启动生效（RAM，不写 env）；POST `/factory?confirm=reset`：只擦/校验 `rootfs_data`；
- POST `/env?key=&value=&confirm=write`（另需请求头 `X-E2631-Confirm: write`）：白名单 `e2631_*`+`bootdelay`，单键，
  走 `e2631env` 五步状态机（diff→check→erase→write→readback→verify→done）；
- POST `/console?cmd=`：单条命令、无 stdin 共享，输出取控制台记录尾部 4 KiB（换行转义 `\n`、反斜杠转义 `\\`），
  非 `bootm`/`reset` 类长命令请只接物理串口操作。

写者 owner 不变：bootloader=`e2631flash`、slot=`e2631fwslot`、rootfs_data=`e2631factory`、env=`e2631env`；
`/console` 不新增写路径，`/backup` 永不写。忙时 409；参数/校验错误 400、权限性拒绝 403/400，响应体都是
`result=error` + `error=<短 ASCII>`；成功不自动重启，页面只提示断电重启或手动 `reset`。
验收顺序：先在 RAM 链做零写入 validate/负例/页面交互（含一次 `/console`、`/env` 与 `/backup`），
固件 write 与 `/factory` 必须单独批准；写后回读 slot/`rootfs_data` 校验并记录 mtd0 与目标槽 sha256。

### E4 v3 状态/日志/完整性/重启/DHCP（0042-0049，task-90；构建由 task-92 统一）

契约以 [evidence/e4-v3-contract-delta-20261128.md](../evidence/e4-v3-contract-delta-20261128.md) 为准（页面已在 task-91 实现，
C 侧必须与 `tools/mock-failsafe.mjs` 行为一致）。本批新增/变化的端点：

- **控制台命令回收（0042）**：defconfig 关掉 `CONFIG_CMD_FDT` 与 `CONFIG_CMD_TFTPBOOT`（12,380 B）。控制台不再有 `fdt`/`tftp`/
  `tftpboot`；主机到 U-Boot 的网络传输改走救援页（`POST /flash` 与 `POST /firmware`），串口恢复仍可用 `loadx` + `e2631flash`。
  `CONFIG_CMD_MTD`/`bootm`/`e2631*` 命令不受影响，D-U1 的写 owner 规则不变。
- **GET `/sysinfo`**：固定键序的只读系统表（版本/banner/构建时间/板卡/SoC/DRAM/mtd0/SPI-NAND 参数与 id/CP15 寄存器/
  9 个时钟寄存器/cpu_mhz=`1000`+`source=known`）。全部只读，不写 flash/env，幂等无缓存。
- **GET `/log`**：进入 `e2631rescue` 时（打印 banner 前）把 console record ring 读成快照；body 是原始文本行，
  头带 `X-E2631-Log-Bytes`/`X-E2631-Log-Overflow`/`Content-Length`；`?download=1` 加 `Content-Disposition`。
- **POST `/integrity`**：只读计算 mtd0 `0x20000..0xC0000` 的 CRC32+SHA-256；`expect` 可来自 query 或
  `X-E2631-Expected-Sha256`（query 优先，必须 64 hex），返回 `match=ok|mismatch|absent`。GET 为 405，写任务/备份期间 409。
- **GET `/backup` 扩展（0047）**：除 v2.1 的五个小分区外，新增 `slot0`/`slot1`（各 `0x1C00000`）、`rootfs`（按 `next_slot` 选
  `0x00B00000`/`0x02700000`，`0x1100000`）与 `header`（`0x1C00000`/`0x3800000`，`0x20000`）。整槽用 1 MiB cache-aligned bounce、
  先两遍读（CRC32+SHA-256）再流式发送；单个备份可能持续数分钟，期间 `/status` 报 `backup=active`/`backup_part`，其它写任务 409。
- **POST `/reboot`（0048）**：空 body + `X-E2631-Confirm: reboot`；任一写任务或备份进行中 409；应答 `result=accepted`/`reboot=1`
  并等 ACK，约 300 ms 后调 0029 的 TOPCRM 软复位。页面只提示“设备正在重启，约 20-30 秒后回到系统”。
- **蓝灯心跳（0048）**：救援期间 GPIO0 bit8（active-low）1 Hz 闪；进入时保存 bank0 DIR/DATA，退出/Ctrl-C/错误/复位前恢复原值，
  不驱动绿/红灯，`/status` 不加 LED 字段。
- **DHCP 配置（0049）**：`e2631_dhcp_ipaddr`/`e2631_dhcp_netmask`/`e2631_dhcp_pool_start`（1..254）/`e2631_dhcp_pool_size`（1..200）
  优先于旧的 `dhcpd_pool_start/size` 与内置默认；非法值回落默认并在 `/status` 报 `dhcp_source=fallback` 与 `dhcp_warning`，
  `POST /env` 对这四个键做语义校验（池不越过 .254、不含服务器地址）。干净环境必须保持 `dhcp_source=default` 且无 warning
  （0052：主机八位组经 `ntohl()` 取，192.168.1.1 的主机八位组是 1，默认池 100..200 不包含它）。

尺寸：0042 回收 12,380 B、0051 再回收 11,520 B、0052 只加 32 B、0053/0054 净减 72 B；第三次统一 v3 构建
（run 46126880665）最终 `u-boot.bin` 398,480 B（≤ 407,552，余量 9,072 B，比 v3 基线 405,368 B 低 6,888 B；
硬上限 653,312 − 240 KiB headroom 的算法见 §4 item 3/26）。零写入验收顺序：先只读 `/sysinfo`、`/log`、`/integrity` 与五个小分区备份，再跑 `validate` 负例；
`/reboot` 与整槽备份放在用户批准的真机会话里最后一次做，不要在写任务进行中触发。
### E4 v3.1 上游对齐服务（0055-0059，task-97；零写入优先）

救援页之外，v3.1 把上游 failsafe 的三种交互补齐，全部复用既有单执行槽与写 owner：

- **DNS（0055）**：救援期间 UDP 53 应答 `dnsd_domain`（默认 `failsafe.lan`）的 A 查询，
  其他名字 NXDOMAIN、非 A 查询 NOERROR/NODATA；地址取活动 `net_ip`。启动失败只 WARNING，不影响救援。
  真机验收：主机把救援网卡的 DNS 指到 192.168.1.1 后 `nslookup failsafe.lan 192.168.1.1` 应返回 192.168.1.1。
- **telnetd（0056）**：TCP 23（`telnet_port` 可覆盖），`telnet 192.168.1.1` 得到 `=>` 提示符；
  命令在 `mtk_telnetd_poll()` 的延迟执行路径里跑，输出经 console record 流式回传；Ctrl-C 对执行中的命令
  发 abort。单连接、无历史、不写 env/flash。
- **Web console（0057）**：`POST /console/exec`（multipart `cmd`，可选 `token`，环境
  `failsafe_console_token` 非空时校验，256 B 上限）、`POST /console/poll`（JSON `data/avail/overflow/busy`）、
  `POST /console/abort`、`POST /console/clear`；与 telnetd 共享一个执行槽，任一方执行中另一方得
  503 / `console is busy`。执行网络命令后主循环在回调链外重新 `eth_init()` 并重注册 DHCP/DNS handler。
  `/console?cmd=` 保留为回退路径。
- **env 候选对齐（0058）**：写 env 时先按 flash 基线的键集对齐候选块（`fdtcontroladdr` 与
  `serial@...` stdio 等运行时键改回 flash 值/删除，写后恢复 RAM），真正的 no-change 写返回
  `result=ok keys=0` 而不是 403；厂商白名单与快照保护不变。
- **/env 池范围（0059）**：`/env` 对 `e2631_dhcp_pool_start/size` 走共享 `e2631_dhcp_pool_ok()`，
  池越过 .254 或包含服务器地址返回 400 `error=bad value`（此前同样的候选块问题会先撞白名单 403）。

零写入验收顺序（同一 RAM 链会话）：先 `GET /sysinfo`、`GET /log`、`POST /integrity` 与五个小分区
`/backup` 确认只读；再 `GET / 页面并点 DNS/telnet/web console；`POST /firmware?mode=validate` 用合法包
只跑校验（不写）；`POST /env` 做一次 no-change（`key=bootdelay&value=<当前值>`）与一次非法池值负例；
最后退出救援并核对 mtd0/region/env/secondboot 四个 sha 未变。UDP 魔法包触发（net_abort）本轮不做：
3 s 的 bootdelay 窗口在 eth init 完成前就关闭，延长窗口会与既有 bootdelay=3 裁决冲突并增加每次开机延迟，
**technically deferred**，不是被“按键固定”否掉的；若以后要支持，需先决定窗口策略。

### 恢复键进救援（0035，task-82；零写入）

操作：断电 → 按住 reset 键或 mesh 键不放 → 上电 → 保持约 6 s（secondboot 到 `board_late_init()` 约 3–4 s，
再加 2 s 轮询窗口；串口出现 `e2631rescue: recovery key held...` 或救援启动行即可松手）。触发后 autoboot 的
bootdelay 结束即进入救援页（DHCP/HTTP 同上面的 E4 流程）；若在窗口内松手，会打印
`e2631rescue: key released, booting normally` 并照常启动固件。

实现与边界：`board_late_init()` 末尾用裸 MMIO 读 GPIO bank1 的 DATA（`0x94407040 + 0x14`，bit2 = reset、
bit4 = mesh，低电平=按下），只采用进入函数时已经按下的键；窗口内任一已按键保持按下即触发，全部松开即取消。
`bootcmd` 只在 RAM 里改成 `e2631rescue`，不 saveenv、不写 flash，4 个 MTD 写点 allowlist 不变；
`e2631key` 可只读打印两键状态，用于标定与诊断。

语义替换：内核层“按住 reset 过启动 = 恢复出厂”（rc.button hold ≥ 5 s）被这个手势取代；恢复出厂将挪进救援页
（后续模块）。首次真机验证必须零写入（RAM 链）：确认 GPIO 读在本 U-Boot 的 board_late_init 阶段安全、窗口和
6 s 操作指引可复现之后，才进入刷写讨论。

## 6. 已知限制与风险

- **F2 的诊断开关是临时的**：0031 的 TX 模式默认等于内核描述符，`e2631net tx/mode/sbrg` 只在控制台显式调用时
  才行动；定位完成后若最终需要改默认描述符或 DMA arena 地址，另开补丁并重钉 pin，不在本 patch 里改默认行为。
- **F2 根因修复（0032）是单点常量改动**：`ZX_SW_FWD_CTRL_ON` 由误植的 `BIT(17)` 改为 `17`（内核驱动与
  厂商 U-Boot 都写 17，证据见 [evidence/uboot-f2-tx-probe-20261127.md](../evidence/uboot-f2-tx-probe-20261127.md) §8）。
  真机若仍不上线，先看 `e2631net bmu` 的 `switch fwd ctrl` 回读；回滚只需还原该常量，不涉及其它寄存器。
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

- **`reset` 依赖厂商 TOPCRM 软复位**：0029 起 `reset_cpu()` 先等 50 ms，再向 `TOPCRM+0x44`
  （`0x94000044`）写 1；BootROM 会重跑 secondboot 并重新加载 U-Boot，DDR 也会重新初始化，所以
  不能靠复位保留任何 RAM 状态。没有 L2/SCU 副作用，也没有旁路 MTD 写；如果真机上这条写不触发复位，
  串口会停在自旋前的提示，用断电恢复。
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

- **恢复键触发尚未真机验证（0035）**：`board_late_init()` 直接读 GPIO DATA，而本 U-Boot 的冷启动链此前只在 `e2631net`/救援入口之后碰过这批寄存器（厂商 Linux 里 devmem2 读 GPIO 曾把板子读挂，是厂商 OS 环境的历史现象）。首次验证走零写入 RAM 链：从 flash 提示符加载新镜像，按住键看提示与救援页；若 board_late_init 阶段读 GPIO 卡住，串口会停住、断电即可恢复（未写 flash）。2 s 窗口与“上电后约 6 s”的操作指引需要用真机矩阵标定。
- **E4 救援是“每次开机只用一次”**：0034 已让救援从 flash 冷启动第一条命令就可用（自带参考时钟初始化），但同一次开机内 Ctrl-C 退出后再进第二次，DHCP/ARP 可能不再应答（v1 已知限制，见 §5 E4 验收的命令台输入与重复进入两段）。重进前先 `reset`/断电；救援期间别往 U-Boot 控制台打字，Ctrl-C 是唯一被识别的输入。
- **E4 救援页直接写 mtd0，变砖风险最高**：`e2631rescue` 的写窗口是 U-Boot 区 `0x20000..0xC0000`（655360 B，到 env 前为止）；
  写前必须通过 SHA-256 + 结构校验，且页面要求 `X-E2631-Confirm: write` 才进入五步写。成功不自动重启；
  写期间掉电会留下半写镜像，只能靠串口 + 厂商/第二级链路恢复。该路径复用 `e2631_flash_*`，没有第二条
  MTD writer；写入前的“仅校验”与写后整盘 sha256 复核是强制步骤。
- **E4 v2.1 救援页无鉴权（用户裁决，2026-11-28）**：`/console`、`/env`、`/firmware`、`/factory` 在 lan1 上没有口令门。
  任何能接上 lan1 并拿到 DHCP 地址的人都能执行单条 U-Boot 命令（含 `mtd erase` 之外的受限命令）、写白名单 env、
  擦 `rootfs_data`、或按契约写目标固件槽；安全边界是**物理 LAN 信任**，不要把救援链暴露到 WAN，不要在不可信网络上
  保持救援模式运行。`/console` 还允许阻塞式命令（没有超时保护），可能把救援会话卡住；阻塞类操作只接物理串口。
- **E4 v3 删掉了控制台的 `fdt`/`tftp` 命令（0042）**：这是尺寸回收的代价，不是回归。恢复/更新通道改为救援页（`POST /flash`、
  `POST /firmware`）与串口 `loadx` + `e2631flash`；若需要在控制台做设备树/变量调试，请临时打开 defconfig 里的对应符号
  （默认关闭），并预期镜像会超过 407,552 B 门禁。
- **E4 v3 的 `/reboot` 会真复位（0048）**：只在确认头 + 空 body 下触发，写任务/备份期间 409；复位前救援 LED 恢复原值。
  RAM 链上 `/reboot` 会重跑 BootROM→secondboot→已写入的 U-Boot，若镜像只在 RAM 里，复位后就回到 flash 镜像——
  这是预期行为，页面文案不能写成“已升级”。
- **整槽备份很慢（0047）**：`/backup?part=slot0|slot1` 各 `0x1C00000`（28 MiB），要两遍读（先哈希再流），
  在 100 Mbit 链路上按分钟计；期间 `/status` 的 `backup=active` 会阻止其它写任务。不要在救援页同时开多个大备份。
- **E4 v3 的页面曾超出单个响应缓冲（task-95，0053 修复）**：`GET /` 原先把整块 gzip 页面拷进 16,384 B 的 `c->out`，
  v3 页面 24,904 B 装不下，v3 设备探针里 `GET /` 直接空回复（curl 56）；0053 改为 4 KiB 分块流式发送后，
  页面大小不再受响应缓冲限制（仍受页面预算 32,768 B 与 U-Boot 尺寸门禁约束）。
- **E4 v3 的尺寸门禁会把页面算进来（task-92）**：v3 页面 gzip 约 24,904 B（v1 基线 13,773 B），加上 v3 C 代码后
  u-boot.bin 可能逼近 407,552 B；若 task-92 构建被门禁拒绝，按 Lead 裁决先回收 P2 的 `CONFIG_CMD_MII`（约 5,724 B，
  预批），仍不足才砍页面 I18N（最后手段，需用户授权）——I18N 优先于 mii 保留。
- **E4 v2.1 的写路径只能在受控会话里验收**：`/firmware` 写目标槽（整槽擦/写/回读）、`/factory` 擦 `rootfs_data` 都是
  破坏性操作；首次验收必须在 RAM 链、已记录目标槽/整盘 sha256 的前提下，由用户单独批准，先跑 net-zero validate 与负例矩阵，
  再跑一次真实的空槽/净零写入，写后回读 slot 校验并核对 mtd0 未变。固件包上限 `0x1BE0214`、暂存 `0x46100000`，
  暂存区与 DMA arena/U-Boot 链接区之间的编译期断言见 §3 内存图。
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

  [evidence/uboot-checkpatch-maintainers-20261122.md](../evidence/uboot-checkpatch-maintainers-20261122.md)。0023-0030 在四类 ignore 后均 0 errors / 0 warnings（0026 另有 24 条非阻断 CHECK，统计口径同上）。自用 fork，不提交上游。
- 本机不编译（硬规则）；编译证据只能来自 task-44 的 CI run。

- **v3.1 救援服务无鉴权（用户裁决）**：DNS/telnet/web console 与救援写接口都只在 lan1 上监听，页面没有口令门
  （用户明确“把功能都加上，不要再说安不安全”），只在文档里标注风险：不要把 lan1 接到不可信网络；telnetd 不提供
  stdin 会话隔离，`failsafe_console_token` 只保护 web console 的 exec 端点，不保护 telnet 端口。
- **console 命令是阻塞执行**：`/console/exec` 与 telnetd 都在主 poll 循环里同步跑 `run_command()`，
  长命令（如全盘 `mtd read`）会阻塞 DHCP/HTTP 响应；页面按 4 KiB 尾捕获显示，UI 侧用 busy/abort。
- **DNS/telnet 是可选服务**：任一启动失败只打印 WARNING，救援 HTTP 不依赖它们；若端口被占用或栈空间不足，
  先抓串口日志再决定是否回退（回滚只需去掉 rescue_loop 里的 start 调用，不影响写路径）。

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

- **E4**：v1 救援模式由 0026/0027/0028 交付（TCP/DHCP 栈、`e2631flash` job API、`e2631rescue`），
  只刷 mtd0 的 U-Boot 区、不刷槽位/固件；复位由 0029 补齐。第一次真机救援会话按 §5 的 E4 步骤记录，
  写路径只在用户单独批准的会话里使用。v2 再谈自动进入救援（E3）与更多上传目标。
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
- 2026-11-22（task-69 item d，可复现构建，option B）：`uboot-port/commits.env` 新增冻结 pin
  `E2631_UBOOT_SOURCE_DATE_EPOCH=1795103079`（pinned base `c1958b5f…` 的 committer 时间
  `2026-11-19T15:44:39Z`），workflow 把它导出为 `SOURCE_DATE_EPOCH`，patch 重放改为
  `git am --committer-date-is-author-date`——版本 token 与 banner 时间从此只由 base+patch 决定（kit `be1e405`；
  无代码/history 改动，22 个 patch 与 tree `c812dd86…` 均未动）。连续两次 dispatch（run `44991454540` /
  `44991704112`，同 head `be1e405`）SUCCESS：banner 固定为
  `U-Boot 2027.01-rc2-gf355ce89283c (Nov 19 2026 - 15:44:39 +0000)`；两次的 `u-boot.bin`（494,208 B sha256
  `3cf000291b1b2d7552b4e7859204a310640dba81fbba5e60b36f99d7b89f355d`，crc32 `3ccc7333`）、mtd0 镜像（sha256
  `18255c2cbe6b50a178e9531895e50820025f8840522276a6aafbe22f86589ce3`，crc32 `e70fb953`）、`.config`、
  `u-boot.map`、命令帮助与 env 块（`6eee153b…`）逐字节相同，`cmp` 全部 IDENTICAL；证据见
  [evidence/uboot-reproducible-build-20261122.md](../evidence/uboot-reproducible-build-20261122.md)。真机会话改用
  这件可复现产物（取代 run `44983615483`）。- 2026-11-27（task-69 items 1/2，E2 F2-a + geometry，patch 0023/0024）：0023 让 `eth_send` 不再静默——
  BMU 分配失败打印原因、所需 buffer 数（1）与 BMU 状态，并移植内核 `zx_bmu_alloc_bp()`
  （`zx279128s-main.c:43-83`）的 pending-retry：超时请求保持 pending，下一次调用先收迟到 buffer，不再丢帧；
  `e2631net` 增打印 failed/late/pending 与 BUF_ALLOC/BUF_ID。0024 为防御性 geometry 断言
  （staging `0x42000000` / kernel copy `0x40008000` / arena `0x45000000`），并在 §3 内存图纠正卡片时代的
  `0x4554xxxx` 换算错误（3,491,146 B 止于 `0x4235454A`）。重钉结果 tree
  `721bb82538df42dca98fd633b98faa0582256850`（24 个 patch；0023 sha256 `e38d0545…`、0024 sha256
  `8bf4e048…`）。CI uboot-build run `45985501668`（head `454c105`，其上是 task-71 的 artifact 统计提交）
  SUCCESS：banner `U-Boot 2027.01-rc2-gcbcaeea0d172`、`u-boot.bin` 494,880 B sha256
  `15bfa0c1484d96a4ab90e774a47798251116a9abebd3480f29762dabf64d692a` crc32 `7db1de62`、mtd0 镜像 sha256
  `c45baf4fd1831ec90b501f78dc1c02f18da0fd2bae80ba9f142a1a9a81895ae7` crc32 `e6a2274e`、env 块 `6eee153b…`
  未变、checkpatch 0 errors / 0 warnings（3 条既有 CHECK 不阻断）；证据见
  [evidence/uboot-e2-fix-20261127.md](../evidence/uboot-e2-fix-20261127.md)。
- 2026-11-27（task-69 defconfig 瘦身，patch 0025）：加一行 `# CONFIG_MMC is not set`；MMC=n 连带 BLK=n，于是
  EFI loader、标准启动（BOOTSTD）、FAT、块缓存及其 helper 库（event/SMBIOS/SHA1/UUID 等）全部消失——`.config`
  少 56 个 `=y` 符号、0 个新增；控制台少 `bootefi`/`eficonfig`/`bootflow`/`bcb`，`bootm`、`e2631boot`、
  `e2631flash`、`e2631env`、网络驱动与 MTD 写白名单不变。重钉后 tree `ac98701595404b43ecd48ea43d6ff7f3cf7676fb`
  （25 个 patch；0025 sha256 `af158e9f…`）。CI uboot-build run `45988430055`（head `98592c2`）SUCCESS：
  `u-boot.bin` 320,848 B（比 24-patch 的 494,880 B 少 174,032 B，-35.17%）sha256
  `339289583f80bd60b7214fa65ad9a4b5a3ca68eb37d95bd1bad65215265ee2fa` crc32 `92257c50`、banner
  `U-Boot 2027.01-rc2-ge6678e875e60`、mtd0 镜像 sha256
  `99886ea0966877fa4978faad2b52df58ceb698ad627a049763957ddbb92bfe51` crc32 `13051599`、env 块
  `6eee153b…` 未变、checkpatch 0 errors / 0 warnings；证据见
  [evidence/uboot-defconfig-slim-20261127.md](../evidence/uboot-defconfig-slim-20261127.md)。

- 2026-11-27（task-72/task-76，E4 v1 + 复位）：新增 patch 0026-0029——最小 TCP/DHCP 栈、`e2631flash` 五步写
  job API、`e2631rescue` 救援页（DHCP + HTTP + gzip 页面 + SHA-256/确认头契约 + 结构校验）与
  `reset_cpu()` 的厂商 TOPCRM 软复位；重钉结果 tree 为
  `e7dc246351aba6b8c946967addc0971b4f4e97f4`（29 个 patch）。D-U1 调用点白名单仍为 4 个 site；救援只写
  mtd0 `0x20000..0xC0000`（655360 B），不碰 env/secondboot/保留区。CI 构建与验收值见

  [evidence/uboot-e4-rescue-20261127.md](../evidence/uboot-e4-rescue-20261127.md)。
  CI run `46002766353`（kit head `c91e976`）全绿：banner `U-Boot 2027.01-rc2-ga9d4df78ce6e`、
  `u-boot.bin` 360,624 B sha256 `49acded8d7b7a664dab7f45aab683b020cc583004aa423c3c47d996c064354e6`、
  mtd0 sha256 `79dab60d3ce0e3eb72037cd6afb3431b89071824c6449df377d62cb233095a28`、env 块
  `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426` 未变；救援页资产 raw 9,216 B /
  gzip 4,456 B（上限 6,144 B）。

- 2026-11-27（task-78/task-77，救援写窗口修正 + env 读重试）：verify-docs 在首个 E4 构建后审出 0028 的写窗口
  与源指针错误（原 `0x20000..0xA0000`、源 `img+0x20000`），按 Lead 要求就地修正为整 U-Boot 区
  `0x20000..0xC0000`（655360 B，源=镜像首地址，erase/write/compare 同窗），并加 workflow 回归门禁；同时新增
  patch 0030 给 `env_mtd_load()` 加 3 次重试与失败现场打印（保留 0025，不丢 bootm 交接路径）。合并构建 run
  `46010298863`（banner `g6db632ad6e5b`，30 patch，tree `3be7118d...`）全绿：`u-boot.bin` 361,448 B sha256
  `a693afdb...`、mtd0 sha256 `62bf1244...`、env 块 `6eee153b...` 未变、白名单 4 site。真机写入仍需用户批准，
  且先由 verify-docs 的 `e4_prewrite_check.py --archive` 离线门禁通过。

- 2026-11-27（task-78/F2b，TX 出口死路诊断）：F2 会话确认「TM 收下描述符、帧不上线且本机任何 MAC 端口计数不动」，
  且发送错误诊断（BMU 分配失败/TX completion 超时）从未触发；静态对照显示 U-Boot 的初始化与 TX 描述符是内核
  驱动的逐行移植，而厂商 U-Boot 的描述符只在两处不同（queue 0 而非 40+port、word3 bit0=0），另有 CPU 桥端口
  egress mask（0x3883c0，U-Boot 从未写过）这一可丢包点（后来 A 会话证明掩码原本就是复位值、该假设被否定，
  见 0032 条目）。新增 patch 0031：TX 描述符变体运行期开关（默认仍是
  内核描述符）、`e2631net tx [count]` 广播探测帧、`e2631net mode`、`e2631net sbrg [allow]`（含 VLAN 1 读取与
  CPU 端口 egress mask 恢复），输出固定打印 DMA/TM/描述符/各 MAC 端口 TX 计数/桥块掩码；零写入真机检查单见 §5
  「F2 TX 出口诊断」。本 patch 不写 flash、不改默认发送路径。CI 构建 run `46022545621`（head `642e9b0`，
31 个 patch，tree `55aebf1afad2406965e5ee77a470f5b79f527eb2`）全绿：banner `U-Boot 2027.01-rc2-ge84e13107885`、
`u-boot.bin` 364,728 B sha256 `d493042d…` crc32 `1c354a00`、mtd0 镜像 sha256 `e1e5ceb3…` crc32 `48bf0511`、
装配后首 0x800 sha256 `e9ec454f…`、env 块 `6eee153b…` 未变、白名单 4 site、checkpatch 0 errors / 0 warnings
（24 条既有 CHECK 不阻断）；证据见 [evidence/uboot-f2-tx-probe-20261127.md](../evidence/uboot-f2-tx-probe-20261127.md) §7。

- 2026-11-28（task-78/F2c，F2 根因）：把 F2 的「TM 收下描述符、帧不上线」定位到交换转发控制
  `0x1cc000`：U-Boot 移植时把内核的 `ZX_SW_FWD_CTRL_ON = 17` 误写成 `BIT(17)`（写 0x00020000）。
  内核 `zx279128s-main.c` 的 switch 初始化写 17，厂商 U-Boot 也在其 switch 初始化里写同一个 17
  （payload `0x47f310c8`，由 `0x47f2ff6c` 从以太网初始化调用）；三份实现里只有我们的值不同。新增
  patch 0032：把常量改回 17，新增 `e2631net bmu`（TM buffer 窗口/BMU 池/DMA ring 窗口/switch fwd ctrl）
  与每次探测的 BMU 块上报，`0x1fc` 按厂商语义改称 `dma err`，`e2631net sbrg` 每次打印桥块状态、
  `allow` 只回放复位值。真机判据：`e2631net bmu` 的 `switch fwd ctrl` 读回 `0x00000011` 且
  `e2631net tx 3` 后 MAC TX frames 增长。CI 构建 run `46030383958`（head `739b8e8`，32 个 patch，
  tree `ae72334756d47f05a247f0dea63f81c0ca7265dc`）全绿：banner `U-Boot 2027.01-rc2-gd38f69c44523`、
  u-boot.bin 365,872 B sha256 `e87a858046b865acfd8e83f1bfbd14cae262a3b16c9738a9edc321cc6a1adc6b`
  crc32 `0966526e`、mtd0 sha256 `4fa8bd4d0e4600fd4c3463848135c7239a21f7e2cdb6f4865c462b888ddcb857`
  crc32 `1ffd8cb2`、env 块 `6eee153b...` 未变；checkpatch 0E/0W、D-U1 白名单 4 site。
  真机验证（同上，零写入 RAM 会话，2026-11-28）：`switch fwd ctrl` 0x00000000 → 0x00000011，`e2631net tx 3`
  让 MAC TX frames 端口 2 从 0 涨到 3（后续 6/9/12），主机抓到 12 个 60 B 广播 ARP，mtd0 未变——
  F2 根因确认，见 [evidence/uboot-f2-tx-probe-20261127.md](../evidence/uboot-f2-tx-probe-20261127.md) §8.2。

- 2026-11-28（task-78/E4 phase-1，救援请求头名修复）：E4 v1 阶段一验收发现所有 `POST /flash` 都返回 HTTP 400
  `unsupported request`：`rescue_name_is()` 只把收到的请求头行折成小写，却拿调用方的混合大小写字面量
  （`Content-Length`/`X-E2631-SHA256`/`X-E2631-Confirm`）去比较，`'c' != 'C'` 使任何请求头都匹配不上；
  `GET /` 与 `/status` 不读请求头所以看起来正常。新增 patch 0033：比较两侧都折成小写，头名/头值辅助函数
  移入无依赖的 `e2631http.h`；新增主机 fixture `uboot-port/tests/rescue_headers_test.c`，CI 在 `git am` 之后、
  交叉编译之前编译运行（失败即中止），防止同类缺陷再进镜像。CI 构建 run `46036894542`（head `a97b76c`，
  33 个 patch，tree `cd67a0414737dcbb860072ddbaaf3de16a306b46`）全绿：banner `U-Boot 2027.01-rc2-g30dca5f54503`、
  u-boot.bin 365,872 B sha256 `3dbbfc49e7fa580fe5327f9b0f11cddc0fe0d0f92e5a9fde9c37a7efdf133bb6` crc32 `34b252a4`、
  mtd0 sha256 `8a38896e9164faa7aca4e9c2737e9d0c2b720f5576ce3ee3ef147109aa0b2bb9` crc32 `79ef8c50`、
  env 块 `6eee153b...` 未变；`rescue header fixture: PASS`、`mtd writer sites: 4`、checkpatch 0E/0W。
  真机复测（2026-11-28，零写入 RAM 会话）：`POST /flash?mode=validate` 返回 HTTP 200 `result=ok`、
  错误摘要返回 HTTP 400 `error=sha256 mismatch` 且 `/status` 保持 idle（零擦写），`GET /`、`/status`、F1 全 PASS，
  证据见 [evidence/e4-rescue-acceptance-20261128.md](../evidence/e4-rescue-acceptance-20261128.md) §11（run-2）；
  写模式验收仍待用户单独批准。

- 2026-11-28（task-78/E4 cold boot，救援独立启动修复）：flash 上 E4 镜像冷启动后，提示符第一条命令
  `e2631rescue` 报 PHY autoneg TIMEOUT / `PHY startup failed (-110)` / `no usable Ethernet device`——冷启动时
  `e2631boot` 还没跑过，网络参考时钟/SerDes 未建立，内部 PHY 不应答 MDIO；RAM 链验收能过只因先跑过
  `e2631net`。新增 patch 0034：`do_e2631rescue()` 在 `net_init()`/`eth_init()` 之前调用幂等的
  `e2631_net_refclk_init()`，CI 新增 cold rescue gate（awk 截取 `do_e2631rescue()` 后断言该调用存在）。
  同时把两条真机运维规则写进 §5：救援服务期间不要向 U-Boot 控制台发任何字符（Ctrl-C 是唯一被识别的
  输入，会中断排队中的写并打印 WARNING）；同一次开机内救援只用一次（第二次进入 ARP/SYN 不应答，重进前
  先 reset/断电）。CI 构建 run `46046018929`（run 40，head `9ffadd5`，34 个 patch，tree
  `0480ef834d718b827e32c1ae9b787f671ca3f5a1`）全绿：banner `U-Boot 2027.01-rc2-g1673d5c89c7b`、
  u-boot.bin 365,872 B sha256 `b7ea6bbc138e1b3cbea6389fbaae89419d1d7e46e0668ef88637dd2cd14ac33d`
  crc32 `9f2b707d`、mtd0 sha256 `23395533c123ea1099c951fee55a73f264636ca9d33d8298b160efb6d0fdb7d1`
  crc32 `1e5ff289`、env 块 `6eee153b...` 未变；日志含 `cold rescue gate: do_e2631rescue brings up the
  network reference clocks`、`mtd writer sites: 4`、checkpatch 0E/0W。构建身份见
  [evidence/uboot-e4-rescue-20261127.md](../evidence/uboot-e4-rescue-20261127.md) §5.2.1。
  真机复测 GREEN（2026-11-28，零 mtd0 写入）：0034 镜像经 userdata 暂存 + `mtd read` 载入，`e2631rescue`
  作为第一条网络命令完成 autoneg/lan1 1 Gbps/页面/validate，mtd0 `d87db54a…` 与 region `8a38896e…` 未变；
  证据 [evidence/e4-coldrescue-0034-20261128.md](../evidence/e4-coldrescue-0034-20261128.md)（kit `636b0ae`）。
  真冷启动（刷入 0034 后）仍待用户批准。

- 2026-11-28（task-82，恢复键进救援）：新增 patch 0035——`board_late_init()` 末尾用裸 MMIO 轮询 reset（GPIO18，
  bank1 bit2）与 mesh（GPIO20，bank1 bit4），任一键连续按住 2 s 就把 `bootcmd` 在 RAM 内改成 `e2631rescue`
  并打印 `e2631rescue: recovery key held, booting the web rescue`；松手取消（`key released, booting normally`）。
  只采用进入时已按下的键，不 saveenv、不写 flash，MTD 写点 allowlist 仍 4 个；新增只读 `e2631key`
  诊断命令。用户操作指引：上电后按住 reset 或 mesh 约 6 s。内核层“按住 reset 过启动 = 恢复出厂”的手势
  由救援取代，恢复出厂将挪进救援页（后续模块）。CI 新增 key rescue 门禁与 +1 KiB 尺寸门禁。
  真机验证（零写入 RAM 链）待排期。
  CI run `46095932548`（run 42，head `a3426f8`）绿：35 patches / post-am tree `a3e940a8…`、checkpatch 0 errors
  / 0 warnings、`u-boot.bin` 366,600 B（基线 365,872 B，+728 B，1 KiB 门禁内）、sha256 `795ddf59…`、
  crc32 `02121525`；mtd0 镜像 sha256 `f1489840…`、crc32 `dcbfd83a`；env 块 `6eee153b…` 未变；
  MTD 写点仍 4 个；key rescue 与 recovery-key size 门禁均现于日志。首个 run `46095628957` 因新 pin
  未导出到门禁步骤而失败（尺寸本身合格），修复见 `a3426f8`。证据
  [evidence/uboot-key-rescue-20261128.md](../evidence/uboot-key-rescue-20261128.md) §5。
- 2026-11-28（task-84，E4 v2.1 模块 C）：新增 patch 0036-0039——共享槽核心与槽写者（包解析/身份/守卫/
  擦槽/写 body/写版本头/回读/失败擦头）、rootfs_data 恢复出厂与一次性启动槽 `e2631_next_slot`、
  e2631env 分阶段写 API、`e2631rescue` 的 v2.1 端点（/slots、/env、/backup 五分区、/firmware
  validate|write、/boot、/factory、/console、/env 写）。写 owner 仍是 e2631flash / e2631fwslot /
  e2631factory / e2631env 四个；v1 的 /flash 与净载荷契约不变；页面资产 gzip 13,773 B（限 32,768）。
  39 patches / post-am tree `788fda24b59a21b4e8a3491b166be48978e22a0b`。
  CI run `46109519805`（run 46，head `065742d`）绿：14/14 步、checkpatch 0E/0W、slot core fixture
  51 项 PASS、`mtd writer sites: 9`、E4 v2.1 门禁与尺寸门禁通过；`u-boot.bin` 405,368 B
  （≤407,560 B）sha256 `481368a4e7350229a79192f47398413bb236f17e998520e9b7a0b6671f0555bf`
  crc32 `0c5ef993`；mtd0 镜像 sha256 `856703a10c741bae202eb308c548fe5a24d5ac15ac9c8200f973d48a8f272bbe`
  crc32 `64c4e55d`；装配后首 0x800 sha256
  `c034cfd5d766b3a7e11b3505563eb97edca8b8484ed74bdda80ef7458df65752`；env 块 `6eee153b…` 未变；
  banner `U-Boot 2027.01-rc2-g49f13e0cbe40`。三次 CI 失败均为门禁脚本问题（`66aae3a` boot_c 未定义、
  `796c2a4` 工厂错误串由 %s 拼接、`065742d` -O2 内联后的 do_ 前缀）。真机验收（零写入 validate +
  只读探针 + 首次真实写）交 task-86，需 Lead/用户批准。证据
  [evidence/uboot-e4-v2-20261128.md](../evidence/uboot-e4-v2-20261128.md)。
- 2026-11-28（task-94，救援自检防御）：新增 patch 0040/0041——所有 SHA-256 改为显式清零的 `sha256_context` 并在哈希前校验上传窗口基址/长度（`rescue_sha256()` 越界即 FATAL），`rescue_fmt()` 在输出游标离开已登记缓冲区时 FATAL 并拒绝渲染，`/status`、`/slots` 返回 500 `output cursor corrupted`；41 patches / tree `58c996fe8151ca81f45829d8fb5c41f7aea3b38b`；构建由 task-92 统一重跑（CI 身份待填）。证据 [evidence/uboot-rescue-defenses-20261128.md](../evidence/uboot-rescue-defenses-20261128.md)。
- 2026-11-28（task-90，E4 v3 C 实现）：新增 patch 0042-0049——defconfig 回收 `CONFIG_CMD_FDT`/`CONFIG_CMD_TFTPBOOT`（12,380 B）、
  产品串按 Linux 比较 17 B、`/console` 原始长度检查、GET `/sysinfo` 与 `/log`、POST `/integrity`、`/backup` 的槽/rootfs/header 流、
  POST `/reboot` 与蓝灯心跳、DHCP 配置进 env（`e2631_dhcp_*`）；49 patches / tree `8b32cd3c0f050c02e640efe36d30cb50446ec09d`；
  slot core fixture 52 项；尺寸门禁改为 `<= 653,312 − 245,760 = 407,552 B`。构建由 task-92 统一重跑（身份见下一条）。证据
  [evidence/uboot-e4-v3-20261128.md](../evidence/uboot-e4-v3-20261128.md)。

- 2026-11-28（task-92，E4 v3 统一构建）：CI run `46121809714`（head `7322b7f`）19/19 步绿——49-patch 首次构建在
  `e2631rescue.c:1172` 因 `U_BOOT_DATE` 未声明失败（0050 补 `#include <timestamp.h>`，checkpatch 0/0），
  第二次构建 `u-boot.bin` 410,040 B 超 v3 门禁 2,488 B（按预算裁决做 P2，0051 关 `CONFIG_CMD_MII`，
  实测省 11,520 B，页 I18N 未动），第三次构建 398,520 B（≤ 407,552，余量 9,032 B）。51 patches / tree
  `5ca68fa0bde4258a7b19b94a3acbfd13acd5ecf9`；fixture 52 项、mtd writer sites 9、checkpatch 0/0、
  页面 gzip 24,904 B（≤ 32,768）。产物身份：u-boot.bin sha256 `d498aea1ea04daab1f2af7fb5efe7b4c46b72d8686b30ba95ce28f10c2067973`
  crc32 `a9189ba3`；mtd0 镜像 sha256 `1be77a160be62f852f80a0ac6c82a19b7329433eb87d13d878b490198ee957ac` crc32 `099eca4a`；
  装配后首 0x800 sha256 `d2fc14b6f3baa69c25f4ae9f3cb5dda27d595ca75757b70afbcec5d4bcfc46ec`；
  banner `U-Boot 2027.01-rc2-g2bd1efb71eb1`；env 块 `6eee153b…`；artifact `e2631-uboot-46121809714`
  （id 15254266546，553,598 B）。无 Release/tag、无 firmware.yml、无设备动作。证据
  [evidence/uboot-e4-v3-20261128.md](../evidence/uboot-e4-v3-20261128.md) §8。
- 2026-11-28（task-93，DHCP 池误报修复）：新增 patch 0052——`rescue_dhcp_load()` 原先用 `s_addr & 0xff` 取主机八位组，
  在小端机上得到的是第一字节（192.168.1.1 → 192），默认池 100..200 被误判为包含服务器，干净环境也报
  `dhcp_source=fallback` + `dhcp_warning=e2631_dhcp_pool_start`。改为 `ntohl()` 取最后一字节，并把范围/冲突校验收进
  `e2631dhcp.h`；新增主机 fixture `uboot-port/tests/dhcp_pool_test.c`（14 项，含 first-octet 回归守卫）；52 patches /
  tree `cf1ff6c50f0295bb279f7dd333ddd3f41145d265`；构建由 task-92 重开后在 run 46124073666 重跑（见下一条）。证据
  [evidence/uboot-e4-v3-20261128.md](../evidence/uboot-e4-v3-20261128.md) §9。
- 2026-11-28（task-92 重开，第二次统一构建）：run `46124073666`（head `eb19224`，52 patches）22/22 步绿、约 2 分钟。
  `u-boot.bin` **398,552 B**（比 51-patch 构建 +32 B），crc32 `bd3c9269`，sha256
  `3031d610741d3c0b173d464d31b667ccd169b01f2dfb2833d06efd8ff6257610`；`mtd0.bin` 655,360 B crc32 `64f5fe0b`
  sha256 `c10b521601ef6d03b340a13e56a0f82178bb5dad7be39a93de6889dcadc13d31`；装配后首 0x800 sha256
  `47ae703aebc0be48beb4236965dfb2a4250be455b597a3733ffe6dce7e774f48`；banner `U-Boot 2027.01-rc2-g0b0d0199f691`；
  env 块 `6eee153b…`、`.config` `1e925cf2…` 未变；artifact `e2631-uboot-46124073666`（id 15254433840，553,694 B）。
  门禁：`E4 v3 size gate: 398552 <= 407552`（余量 9,000 B）、结构门禁余量 254,760 B (39.00%)、slot core fixture 52、
  DHCP pool fixture 14、mii reclaimed (P2 applied)、writer sites 9、checkpatch 0E/0W、页面 gzip 24,904 B 未变。
  无 Release/tag、无 firmware.yml、无设备动作。证据 [evidence/uboot-e4-v3-20261128.md](../evidence/uboot-e4-v3-20261128.md) §9.4。
- 2026-11-28（task-95，v3 设备探针的两个确定性缺陷）：t92 Phase A 探针（run-1，零写）发现 `GET /` 空回复
  （curl rc=56）与 `POST /console?cmd=<257 B>` 后所有请求被 RST。前者根因是 `rescue_reply()` 把 24,904 B gzip 页面
  拷进 16,384 B 的 `c->out`（v2.1 页面 13,773 B 时才装得下）；后者根因有两层——URI 被复制进 96 B 的 `path[96]`，
  257 B 命令在长度门前已被截成 82 B，且 `REMOTE_CLOSED` 连接既不释放 pdata（每连接约 17.7 KB）也不释放 `/backup`
  的 1 MiB bounce buffer，三次大备份泄漏约 3 MiB，4 MiB 堆耗尽后新连接 `calloc` 失败即被 RST（Ctrl-C 走
  `close_all_conn` 释放存活连接，故看起来“能恢复”）。新增 patch 0053（页面按 4 KiB 分块流式发送，`e2631page.h` +
  主机 fixture 16 项）与 0054（URI 指向原始头行、`e2631query.h` 提供原始 query 长度/256 B 门、`REMOTE_CLOSED`
  释放 pdata、备份缓冲先释放再关连接；主机 fixture 14 项）；54 patches / tree
  `0b48c04ad18e8df251a1ec93a2614b3a6337e06b`；构建由 task-92 第三次重建执行（身份见下一条）。证据
  [evidence/uboot-e4-v3-defects-20261128.md](../evidence/uboot-e4-v3-defects-20261128.md)。
- 2026-11-28（task-92 重开 t92c，第三次统一构建）：run `46126880665`（head `1e430a2`，54 patches）24/24 步绿、约 2 分钟。
  `u-boot.bin` **398,480 B**（比 52-patch 构建小 72 B），crc32 `d77a87d4`，sha256
  `926b1b480230c0d45b7a978c412eb2595d9abb0f28286eafcedcad023abb4c84`；`mtd0.bin` 655,360 B crc32 `155f3041`
  sha256 `0562a4c8cfd1134830a9e29282f15c1cf2af5c81792457cabdc11e0a6074c6b6`；装配后首 0x800 sha256
  `e373501de671693fe91c4e1b8f51229dbf38c6840e032f0a9a173ca519bd8c16`；banner `U-Boot 2027.01-rc2-gb52cb68dc9b9`；
  env 块 `6eee153b…`、`.config` `1e925cf2…` 未变；artifact `e2631-uboot-46126880665`（id 15256310660，553,704 B）。
  门禁：`E4 v3 size gate: 398480 <= 407552`（余量 9,072 B）、结构余量 254,832 B (39.01%)、slot core 52、DHCP pool 14、
  console query 14、page stream 16（7 chunks / 24,904 B）、page stream + console query gate 绿、mii reclaimed (P2)、
  writer sites 9、checkpatch 0E/0W、页面 gzip 24,904 B 未变。无 Release/tag、无 firmware.yml、无设备动作。
  证据 [evidence/uboot-e4-v3-defects-20261128.md](../evidence/uboot-e4-v3-defects-20261128.md) §9。

- 2026-11-28（task-97，上游架构对齐）：按用户“能跟上上游就跟上游一样”的指示，实现上游 failsafe 的真实架构——
  0055 最小 DNS 服务、0056 最小 RFC-854 telnetd（TCP 23）、0057 web console `exec/poll/abort/clear`
  （与 telnetd 共享唯一执行槽、网络命令后主循环重入 eth；`/console?cmd=` 保留回退）、0058 env 候选块与
  flash 键集对齐（真实的 no-change 写返回 keys=0 而非 403）、0059 `/env` 的 DHCP 池范围规则（400 而非 403）。
  UDP 魔法包触发（net_abort）经评估 **technically deferred**：3 s bootdelay 窗口在 eth init 完成前关闭，
  延长窗口与既有 bootdelay=3 裁决冲突且增加每次开机延迟——这是技术结论，不是“按键固定”的借口。
  59 patches / tree `f8144b84cda597ad387d87ee39c6b50a2bbd6898`；尺寸自我门按裁决由 407,552 B 放宽到
  460,000 B（`E2631_UBOOT_HEADROOM_MIN` 245,760 → 193,312，硬上限 653,312 B 与打包门 645,120 B 不变）；
  主机 fixture：DNS 29 项、env align 13 项、web console 13 项、DHCP pool 14→18 项、slot core 52 项；
  checkpatch 0055-0059 各 0/0。构建由 task-92 统一执行（身份待填）。证据
  [evidence/uboot-e4-v31-20261128.md](../evidence/uboot-e4-v31-20261128.md)。
