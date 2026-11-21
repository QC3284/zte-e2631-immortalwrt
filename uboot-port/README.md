# E2631 自定义 U-Boot：A1 最小 RAM 链移植（kit 侧交付物）

本目录是 task-43/task-44 的产物：对 U-Boot 主线的 patch 系列（0001/0002 为 A1 移植，0003 为首个
CI 构建暴露的链接修复）、pin 文件，
以及供 task-44（CI 构建）和后续真机 A1 会话使用的说明。**只含代码与文档；A1 阶段不写 flash。**

依据：[evidence/p2-uboot-research-20261121.md](../evidence/p2-uboot-research-20261121.md) §2（路径 A 分阶段）、
[evidence/uboot-re-20261115.md](../evidence/uboot-re-20261115.md)（mtd0 布局/偏移）、
[tools/lib/mtd0.mjs](../tools/lib/mtd0.mjs)（mtd0 地图，含本次修正的载荷边界）。

## 0. 阶段与范围

- **A1（本次交付）**：纯 RAM 链 POC。PL011 控制台 + Cortex-A9 global timer + DRAM；由厂商 U-Boot
  控制台用 `tftp` 把镜像装到 RAM，`go` 跳转运行。断电即恢复，**零砖风险**。
- **不做**：SPI 控制器、SPI-NAND、env、mtd、网络、bootm、CPU1/SMP 交接（secondboot 已完成停车）、
  DDR/时钟初始化（secondboot 已完成）。这些都留给 A2/A3。
- 引导链：BootROM → secondboot（闭源，已完成 DDR/时钟/串口/SPI-NAND/CPU1 停车）→ 厂商 U-Boot 2013.04
  →（A1 用 tftp+go）自定义 U-Boot。A3 才把自定义 U-Boot 写进 mtd0 0x20000..0xC0000（镜像区 0xA0000 字节）。

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
| am 之后 tree | `abab1858bfee030bfdbc18bc227189a6e8ba5d83`（与机器无关） |
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
test "$(git rev-parse HEAD^{tree})" = abab1858bfee030bfdbc18bc227189a6e8ba5d83
```

## 2. 新增/修改的文件（12 个，209 行）

| 文件 | 作用 |
| --- | --- |
| `arch/arm/Kconfig` | 新增 `ARCH_ZX279128`（select CPU_V7A），source mach Kconfig |
| `arch/arm/Makefile` | `machine-$(CONFIG_ARCH_ZX279128) += zx279128s` |
| `arch/arm/mach-zx279128s/Kconfig` | `SYS_SOC="zx279128s"`、`TARGET_ZXHN_E2631`、source 板级 Kconfig |
| `arch/arm/mach-zx279128s/Makefile` | A1 无 SoC 私有代码（secondboot 已完成初始化），只留占位说明 |
| `board/zte/zxhn-e2631/Kconfig` | `SYS_BOARD`/`SYS_VENDOR`/`SYS_CONFIG_NAME` |
| `board/zte/zxhn-e2631/Makefile` | 编译 `zxhn-e2631.o` |
| `board/zte/zxhn-e2631/zxhn-e2631.c` | `dram_init`/`dram_init_banksize` 从内嵌 DT 读 256 MiB |
| `board/zte/zxhn-e2631/MAINTAINERS` | 维护者与文件范围 |
| `include/configs/zx279128s_zte_zxhn-e2631.h` | `CFG_SYS_SDRAM_BASE=0x40000000`、`CFG_PL011_CLOCK=0`、`CFG_SYS_HZ_CLOCK=500000000` |
| `arch/arm/dts/zx279128s-zte-zxhn-e2631.dts` | memory / PL011 / A9 global timer / 500 MHz fixed-clock |
| `arch/arm/dts/Makefile` | `dtb-$(CONFIG_TARGET_ZXHN_E2631) += zx279128s-zte-zxhn-e2631.dtb` |
| `configs/zx279128s_zte_zxhn-e2631_defconfig` | A1 配置（25 行，已用 `make savedefconfig` 归一） |

补丁 0003（2026-11-21，task-44 首个真实构建暴露）：只改 2 个文件——defconfig 增加
`# CONFIG_DISPLAY_CPUINFO is not set`、`# CONFIG_BOARD_INIT is not set`（A1 没有 DM CPU 驱动、
也没有板级 chip select），板级文件补 `reset_cpu()` 占位实现（A1 无复位控制器，打印提示后返回）。
它不改基线、不改 TEXT_BASE，也不改载荷上限。

## 3. 关键设计参数

| 项 | 值 / 决定 | 说明 |
| --- | --- | --- |
| `TEXT_BASE` | `0x43000000` | **只用于 A1 RAM 链**：厂商 U-Boot `tftp 0x43000000` + `go 0x43000000`。产品/A2/A3 仍由 secondboot 装到 `0x47F00000`，那时改 TEXT_BASE 后重编 |
| 初始栈 | `CONFIG_CUSTOM_SYS_INIT_SP_ADDR=0x48000000` | 256 MiB DRAM 中段，远离镜像与重定位目标（重定位在 DRAM 顶部附近） |
| DRAM | `0x40000000` + 256 MiB | secondboot 完成 DDR 初始化；板级只知道大小，不做 DDR init |
| UART0 | PL011 @ `0x94404000`，115200 8N1 | `CFG_PL011_CLOCK=0`：输入时钟未知，**跳过 IBRD/FBRD 设置**，沿用 secondboot 的 115200；DT 里故意不写 `clock` 属性 |
| Timer | A9 global timer @ `0x800200` | DT `fixed-clock` a9_periph = 500 MHz（CPU 1 GHz / 2）；`CFG_SYS_HZ_CLOCK` 作为 DT 查询失败的回退 |
| Cache/MMU | 全关 | `SYS_ICACHE_OFF`/`SYS_DCACHE_OFF`/`SYS_L2CACHE_OFF`：secondboot→vendor U-Boot→`go` 的交接状态（MMU/cache/CPU 模式）未知，A1 用最保守配置 |
| env | `ENV_IS_NOWHERE` | A1 不读写 env；A2 再加 MTD env（0xC0000，格式与厂商逐字节兼容） |
| 设备树 | `OF_EMBED` | DTB 内嵌进 `u-boot.bin`，`go` 跳转无需外部 DTB；A2 再考虑分离/追加格式 |
| 网络/SPI/NAND | 无 | A1 不做；网络引导用厂商 U-Boot 的 tftp |
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

1. `git rev-parse HEAD^{tree}` == `abab1858bfee030bfdbc18bc227189a6e8ba5d83`；每个 patch 的 sha256 与 §1 一致，
   且 `git rev-list --count <baseline>..HEAD` 等于 patch 数量。
2. `.config` 精确包含：`CONFIG_ARCH_ZX279128=y`、`CONFIG_TARGET_ZXHN_E2631=y`、
   `CONFIG_TEXT_BASE=0x43000000`、`CONFIG_OF_EMBED=y`、`CONFIG_ARM_GLOBAL_TIMER=y`、
   `CONFIG_TIMER=y`、`CONFIG_PL01X_SERIAL=y`、`CONFIG_DM_SERIAL=y`、`CONFIG_CLK=y`。
3. 镜像尺寸：`size=$(stat -c%s build/u-boot.bin); test "$size" -le 653312`
   （超限就裁命令/驱动；这条对应 mtd0 载荷上限 0x9F800，是 A3 的硬前置）。
4. 入口点：`readelf -h build/u-boot` 的 Entry point 应为 `0x43000000`。
5. 上传 CI artifact：`u-boot.bin`、`u-boot.map`、`.config`、构建日志；记录 run URL。
6. checkpatch（可选，见 §6）：`git format-patch c1958b5f..HEAD` 后跑
   `u-boot/scripts/checkpatch.pl --no-tree`，本系列 **0 errors / 4 reviewed warnings**。

## 5. A1 真机步骤（需用户批准；只读/纯 RAM，不写 flash）

前置：串口线接 UART0（115200 8N1），进入厂商 U-Boot 控制台（控制台密码见救砖手册）。
A1 会话只允许 `tftp`/`go`/`md`/`mtest`/`reset` 一类命令；**禁止任何 `nand write*`、`mtddebug write`、
`upgrade`、`saveenv`**（这些是 A3 才讨论的写通道）。

1. 在主机上起 TFTP 服务，把 CI 的 `u-boot.bin` 放到根目录。
2. 厂商控制台：`tftp 0x43000000 u-boot.bin`（确认 "Bytes transferred" 与文件大小一致）。
3. `go 0x43000000`。
4. 预期串口出现 U-Boot banner（版本 v2027.01-rc2 代）、`Model: ZTE ZXHN E2631 (ZX279128S)`、
   `DRAM: 256 MiB`、`Core: ARMv7`，随后是 `E2631>` 提示符与 `bdinfo` 输出。
5. 验证：`bdinfo`（DRAM/重定位）、`md.l 0x800200 8`（global timer 计数在走）、`mtest`（安全区间）、
   `reset` 或断电后应能正常回到厂商 U-Boot。
6. 记录完整串口日志（含 tftp 大小、banner、bdinfo、md、mtest 结果）作为 A1 验收证据，落盘到
   evidence/ 并汇报 Lead。

失败定位顺序：无任何输出 → 串口/PL011（时钟未知，先确认 115200）；banner 后异常 → cache/MMU 交接或
timer fixed-clock 假设；`go` 立即返回/复位 → 入口地址或镜像是否完整传输。

## 6. 已知限制与风险

- **交接状态未知**（MMU/cache/CPU 模式）：A1 全关 cache/MMU、`SKIP_LOWLEVEL_INIT`，从最保守状态开始；
  若真机异常，优先怀疑这里。
- **PL011 输入时钟未知**：暂用 `CFG_PL011_CLOCK=0` 跳过波特率设置；若串口乱码，下一步从 lsp0crpm/实测反推
  （25 MHz / 100 MHz 候选）再改 DT 或头文件。
- **timer 500 MHz 是假设**（a9_periph = CPU/2，A9 1 GHz）；真机用 `sleep 1` 对照秒表校准，必要时修正。
- **A1 无 env/SPI/NAND/网络/bootm**：这是有意的阶段边界，不是缺陷。
- **A1 的 `reset` 命令不做复位**：没有复位控制器驱动，`reset` 只打印提示并返回；需要复位时用
  厂商 U-Boot 的 `reset` 或断电。厂商控制台本身仍可正常复位，A2/A3 再补复位路径。
- **载荷 0x9F800**：A3 封装/写 mtd0 前必须满足；secondboot 封装头其它字节（+0x2D4 摘要等）在 A3 必须原样保留。
- **checkpatch**：本系列 0 errors、4 reviewed warnings，均为已核对的已知项——2 条 "does MAINTAINERS
  need updating?"（patch 0001 新建 `arch/arm/mach-zx279128s/`、patch 0002 新建 `board/zte/zxhn-e2631/`
  各一条；checkpatch 按单 patch 看不到后续 patch 的 MAINTAINERS 更新）+ 2 条 "Use the livetree API"
  （板级 `fdtdec_setup_mem_size_base()`/`fdtdec_setup_memory_banksize()` 是 U-Boot 板级读 /memory 的
  常规 API，checkpatch 的 LIVETREE 检查对板级代码是误报）。自用 fork，不提交上游。
- 本机不编译（硬规则）；编译证据只能来自 task-44 的 CI run。

## 7. 与后续阶段的关系

- **A2**：加 SPIFC/SPI-NAND/env/mtd，在 RAM 里读 env 与 slot1 uImage 并 bootm；TEXT_BASE 改回
  secondboot 装载地址 `0x47F00000`，加 MTD env（`0xC0000`/`0x20000`）、SPI-NAND 芯片 ID 实测
  （0xCD/0x71 用现成 foresee 条目，0xC9 加 heyangtek 条目）。
- **A3**：按刷写工具链（路径 C）写 mtd0 U-Boot 区；需要 OOB/ECC 取证、写通道验证、回滚演练与用户批准。
  在 A3 之前，A1/A2 都不写 flash。
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
