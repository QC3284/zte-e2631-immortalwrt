# ZXHN E2631 闪存启动内核静默挂起 —— 厂商 U-Boot 早期初始化差异静态分析

日期：2026-11-21。作者：iwrt-baseline（A 系列根因支持）。状态：Lead 已审阅接受（2026-11-21），随本次提交入库。
范围：纯静态逆向 + 既有日志/产物比对；未做任何设备操作、未改任何源码或树内文件。

## 0. 结论摘要

现象：我们的 U-Boot 从闪存启动（BootROM -> secondboot -> 我们的 banner -> e2631boot -> bootm）后，内核在 `Starting kernel ...` 之后完全静默（最早的内核输出本应是约 0.15 s 的 `printk: console [ttyAMA0] enabled`），13 分钟以上无任何后续；而**同一份** U-Boot 二进制、同一个 slot1 内核、同样的 bootm 参数，在经厂商 U-Boot 控制台 `go` 进 RAM 链时能正常启动内核。

静态结论：

1. 厂商 U-Boot **不做** PL310/L2、A9 SCU、ACTLR(aux control)、CPU PLL/时钟的“早期初始化”。整个 426,048 B 载荷的全量线性反汇编里，0x00c00000/0x00800000/0x00800200/0x00800600/0x00800620 这些外设基址没有任何真实引用（唯一两处 `mov r3,#0x800000` 在它自己的 `watchdog` 命令处理器 0x47f00560-0x47f00654 里，写的是 TWD 看门狗 0x800620 起的寄存器），CP15 ACTLR（c1,c0,1）写操作为 0 处。
2. 厂商 U-Boot 真正做的是**两次 CP15 状态归一**：入口 `cpu_init_crit` 0x47f0021c（失效 L1 I/D、TLB、BTB，关 D-cache/MMU、开 I-cache），以及跳内核前 `cleanup_before_linux` 0x47f00534（关 I-cache、ICIALLU/BPIALL、D-cache clean+invalidate by set/way、关 MMU+D-cache）。
3. 我们的 U-Boot 因为 `CONFIG_SKIP_LOWLEVEL_INIT=y` + `CONFIG_SYS_ICACHE_OFF/DCACHE_OFF/L2CACHE_OFF=y`，**上述两条归一通道都被关掉**：start.S 里 `bl cpu_init_cp15` 与 `bl cpu_init_crit` 都被 `#if !CONFIG_IS_ENABLED(SKIP_LOWLEVEL_INIT)` 跳过；cache-cp15.c 里 `icache_disable()/dcache_disable()` 变成空函数；`v7_outer_cache_disable()` 是空弱符号；`cleanup_before_linux_select(CBL_ALL)` 实际只剩两条 invalidate（无法 flush、无法关 D-cache/MMU、无法碰 L2）。
4. 于是闪存链上，内核是在「secondboot/BootROM 留下的 CP15/缓存/MMU 状态」下被进入的；RAM 链上，厂商 U-Boot 的 `go` 在跳转前刚执行过 0x47f00534，状态被归一。**这是两条链在“进入我们 U-Boot”以及“进入内核”时唯一被静态证实的系统性差异**。

排序候选（详见 §7）：

- **C1（高）D-cache 未被 flush/关闭**：BootROM/secondboot 若留下 D-cache 打开，则我们 U-Boot 把内核写到 0x40008000、ATAGS 写到 0x40000100 的写命可能仍留在 L1 脏行里，跳内核前没有任何 flush，内核读到旧 DRAM -> 早期静默死亡。
- **C2（高）MMU 未被关闭**：内核/自解压器假定进入时 MMU 关；若继承 MMU 开（带 BootROM 的页表/域设置），自解压器设置 TTBR/SCTLR 的过程会进入未定义状态。与 C1 同根。
- **C3（中）L1 I-cache/BTB/TLB 未在入口失效**：入口不执行 cpu_init_cp15，若 BootROM 留了 I-cache/BTB 条目，理论上有 stale 指令风险（地址不同的概率高，故为中）。
- **C4（低）BootROM/secondboot 遗留的定时器/GIC/看门狗私有状态**。
- **C5（低）厂商 board_init_r 里的 GPIO/clkm/UART/NAND/eth 初始化缺失**：内核都会自己重做。

已排除：镜像/载荷不同（闪入载荷与 C1b-0 成功所用 u-boot.bin 字节相同，sha256 010379fd...）、bootargs/ATAGS 差异（两条链都走我们自己的 bootm）、bootpara@0x40007000（内核注释明确说该页被 zImage 自解压器当页表覆盖）、厂商自定义 ATAG 0x54410011（只有厂商 bootm 会加，我们两条链都没有）、L2/SCU/ACTLR（厂商也不碰，不是差异）、CPU PLL（默认不重配）、secondboot 的 `backup header!!`（原厂正常启动日志同样打印）。

建议下一步（§8）：在 U-Boot 入口和 bootm 前打印 SCTLR/CLIDR/CCSIDR/TTBR0/VBAR/ACTLR 做两条链的实测对比（决定性 A/B），并在 board_late_init 或 bootm 钩子里实现一份**无条件**的、不走 config stub 的 CP15 归一序列；加 `e2631soc` 命令在闪存链提示符下先跑归一、再 `e2631boot` 手测，不需额外写 flash。

## 1. 输入、工具与地址换算

输入：

- 厂商 U-Boot 载荷：`evidence/p2-oob/vendor-uboot-ram.bin`，426,048 B（0x68040），sha256 a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30（仓库内 tracked）。
- 成功（RAM 链）日志：`evidence/c1b0-entry/serial.txt`（本仓库）。
- 失败（闪存链）日志：`/home/qc233/zte/e2631-p3/c1b1-final-v2/run-1/serial.log`（本地，139,688 行，最后一次尝试结束于第 139688 行，无后续复位/BootROM 行）。
- 原厂正常启动日志：`/home/qc233/zte/e2631-serial-boot-002.log`。
- 隔离会话记录：`/home/qc233/zte/e2631-p3/c1b1-diag/`（attach-1 的 bdinfo/printenv、phaseb-1/2 的厂商控制台会话）。
- 我们 U-Boot 源码：`/home/qc233/zte/uboot-src`；构建目录：`/home/qc233/zte/uboot-build-a1`。
- 树：`/home/qc233/zte/iwrt-tree`（内核 DTS/驱动注释见 §6）。

工具：Python 3 + capstone 5.0.7（`PYTHONPATH=/tmp/pylibs`，`Cs(CS_ARCH_ARM, CS_MODE_ARM)`，`skipdata=True`）。

地址换算（实测标定）：

- 厂商 U-Boot 载荷：vaddr = 0x47F00000 + file_off；对应 mtd0 文件偏移 = file_off + 0x20800。
- secondboot：vaddr = 0x00200000 + (mtd0_file_off - 0x800)，代码体 mtd0 0x800..0x68AB。
- 交叉验证：厂商载荷字符串 `*** Press 1 means entering boot mode***` 在 vaddr 0x47f3c297，换成 mtd0 偏移 0x5CA97；“Press 1”子串起点 0x5CA9B，与 Lead 实测值一致。

## 2. 两条链的事实基线（同一份 U-Boot 二进制）

闪存链（失败）`serial.log` 139655-139688：

```
non secure uboot
backup header!!
Jump
U-Boot 2027.01-rc2-g2797f3dd3860 (Nov 21 2026 - 11:20:33 +0000)
Model: ZTE ZXHN E2631 (ZX279128S)
DRAM:  256 MiB
WARNING: Caches not enabled
Loading Environment from MTD... OK
Net:   No ethernet found.
Hit any key to stop autoboot: 3 2 1 0
e2631boot: slot0 at 0x00700000: serial 7 ...
e2631boot: slot1 at 0x02300000: serial 12, version "ImmortalWrt v1.10.0", header 0x03800000
e2631boot: cspboot would boot slot1
e2631boot: uImage "ARM ImmortalWrt Linux-6.18.60": load 0x40008000 entry 0x40008000, 3491146 bytes at 0x42000000
e2631boot: header and data CRCs are good
## Booting kernel from Legacy Image at 42000020 ...
   Image Type:   ARM Linux Kernel Image (uncompressed)
   Data Size:    3491050 Bytes = 3.3 MiB
   Load Address: 40008000
   Entry Point:  40008000
   Verifying Checksum ... OK
   Loading Kernel Image to 40008000
Starting kernel ...
（到此为止，日志结束；13+ 分钟无输出，也无新的 BootROM/secondboot 行）
```

RAM 链（成功）`evidence/c1b0-entry/serial.txt`：第 142 行同一 banner（版本/编译时刻逐字相同），第 146 行同一 `WARNING: Caches not enabled`，第 154 行 autoboot 倒计时，第 157 行 e2631boot 选择 slot1，第 169 行 `Starting kernel ...`，第 171 行 `[ 0.152910] printk: console [ttyAMA0] enabled` 开始正常内核日志。

关键同一性证据：

1. 两份二进制相同：C1b-0 成功时经 xmodem 发送的 u-boot.bin 是 `/home/qc233/zte/e2631-t5-artifacts/uboot-47f-44898534408/u-boot.bin`，448,112 B（0x6D670），sha256 010379fde3496fdcbbe835c249cff2bd79234f946918266721e098dd64479f75。C1b-1v2 写入的 mtd0 镜像（`/home/qc233/zte/e2631-p3/c1b1-expected-mtd0.bin`，sha256 3c8a8c5b0f9db1953628919d650ff7af6d24e07c48e9a31d5b228881a9f36ffb）的 U-Boot 载荷从 0x20800 起与它**逐字节相同**（本次实测），头部长度字段 0x20014 已改为 0x6d670，正好等于 u-boot.bin 大小。
2. 两条链的内核输入相同：同一 slot1 uImage（3491146 B，`ARM ImmortalWrt Linux-6.18.60`，load/entry 0x40008000），同一 `## Booting kernel from Legacy Image at 42000020` 输出，CRC OK。
3. attach-1（闪存链 U-Boot 提示符）实测 bdinfo：boot_params=0x40000100，DRAM 0x40000000/0x10000000，relocaddr=0x4ff94000；printenv 26 项；与 RAM 链会话一致。

不同点只有一个：**进入我们 U-Boot 之前最后执行的代码**。RAM 链是厂商 U-Boot 的 `go` 0x47f03890（先 `bl cleanup_before_linux` 0x47f00534，再跳）；闪存链是 secondboot 的 `Jump`。

附带事实（不影响本分析）：当前 mtd0 回读（`/home/qc233/zte/e2631-p3/c1b1-diag/mtd0-now/mtd0-now.bin`，sha256 d571b764...）与写入镜像只差 env 块（0xC0000..0xC0245，789 B），U-Boot 载荷区 0x20000..0xC0000 逐字节相同 —— 差异来自诊断会话里厂商控制台执行的 saveenv（env 从 26 项变 27 项、CRC 0xf95a816e -> 0xc8e93924、多了 bootargs 一项）。

## 3. 厂商 U-Boot 引导调用图：bootk / cspstart 到底是什么

命令表项是 6 字结构（name_ptr, maxargs, repeatable, cmd_fn, usage_ptr, help_ptr）。实测：

| 命令 | name 地址 | maxargs | cmd_fn | 说明 |
| --- | --- | --- | --- | --- |
| bootk | 0x47f3a6d1 | 2 | 0x47f10364 | usage "boot kernel" @0x47f3a975 |
| cspstart | 0x47f3c6be | 1 | 0x47f15ca0（函数体就是 `b 0x47f15c10`） | usage "start kernel." @0x47f3c6c7 |
| bootm | - | - | 0x47f03f00 | 标准 bootm |
| go | - | - | 0x47f03890 | 跳应用 |
| boot / bootd | - | - | 0x47f03940 | getenv bootcmd + run_command |
| tftp | - | - | 0x47f08664 | 网络装载 |

### 3.1 bootk = 纯 TFTP 引导，没有 SoC 初始化

0x47f10364：argc<=1 时打印 help；名字长度 >0x80 报错；先 sprintf `setenv bootargs console=ttyAMA0,115200n8 rdinit=/sbin/init mem=%dM ser...`（mem 取全局 [0x47f6d570]>>20）并 run_command；再 sprintf `tftp 0x%.8x %s`（0x42000000）并 run_command；最后 sprintf `bootm 0x%.8x`（0x42000000）并 run_command。全程没有 PL310/SCU/ACTLR/时钟/GPIO 写。

### 3.2 cspstart = pdt_cspboot_run 0x47f15c10

全局 pdt 上下文 getter 0x47f14390 返回字面量 0x47f6800c（`ldr r0,[pc]; bx lr`）。注册：`zteboot_register_base_bp` 0x47f14464 写 [obj+0]=0x47f6809c；`zteboot_register_base_mtd` 0x47f1439c 写 [obj+0x7c]=0x47f41818（nand 适配器，另有一套 nor 适配器 0x47f14f74/0x47f14f90）。

`pdt_cspboot_init` 0x47f15b7c（cspboot 命令）只做初始化：打印 `pdt_cspboot_init:883 Start to initialize cspboot...`，注册 bp/mtd，执行 `set ipaddr 192.168.1.1`/`set serverip 192.168.1.100`，调 `pdt_cspboot_info_init` 0x47f15ad4 填 ops 表，打印 `pdt_cspboot_init:917 Cspboot initialization is done.`。这就是隔离会话里 `cspboot` 命令“只 init 不启动”的原因。

`pdt_cspboot_info_init` 0x47f15ad4 填的字段（实测）：

| 偏移 | 值 | 含义 |
| --- | --- | --- |
| +0x00 | 0x47f6809c | base_bp 指针 |
| +0x04 | 0x40007000 | bootpara 缓冲 |
| +0x24 | 0x40008000 | 内核入口 |
| +0x28 | 0x42000000 | 装载窗口顶（memtop） |
| +0x2c | 0 | - |
| +0x30 | 0x47f15808 | **start-kernel op** |
| +0x34 | 0x47f12a18 | search/select op |
| +0x38 | 0x47f162c0 | zteboot_select_pdtver |
| +0x3c / +0x40 | 0x1351 / 0x5211 | 版本点号 |
| +0x60 | 0x47f14534 | 回调 |
| +0x88 | 0x47f14b74 | 回调 |

（+0x08/+0x0c/+0x10/+0x34/+0x84/+0x64 由 0x47f13b4c 的默认表仅在为空时补：0x47f12c7c、0x47f13270、0x47f131f4、0x47f12a18、0x47f11e40、0x47f12680；+0x30/+0x38 已有值，不覆盖。）

`pdt_cspboot_run` 0x47f15c10：取 obj；`blx [obj+0x34]`（zteboot_search_firmware 0x47f12a18，返回 0 则打印 `No image found!` 并返回 -1）；`blx [obj+0x38]`（zteboot_select_pdtver 0x47f162c0，打印 `Select firmware` 与 `pdt_getimg select = %d, serial0=0x%x, serial1=0x%x,`，返回 <0 则返回 -1）；`blx [obj+0x30]`（start-kernel op 0x47f15808）；返回后打印 `Start kernel failed`。

start-kernel op 0x47f15808 内部（与厂商日志逐行对应）：打印 `pdt_start_kernel` 段；调 0x47f15308 `pdt_getreal_kernelfs`（读 slot 内核窗口 4 MiB 校验 CRC，日志 `verify_kernel readflash @0x2300000 size:0x400000 at ram:0x42020020`）；调 [obj+0x10] 回调两次；调 `zteboot_do_settings` 0x47f163bc（重写 bootargs/bootcmd/memsize/versioninfo，必要时 saveenv）；最后 sprintf `bootm 0x%x`（字符串 @0x47f3c18c）并用 run_command 包装 0x47f0f364 执行。原厂日志第 199 行 `arg=bootm 0x42020020;` 就是这条路径。

### 3.3 结论

bootk 与 cspstart/bootm 路径里**没有**任何 PL310、SCU、ACTLR、CPU PLL、GPIO、DDR 的初始化。厂商正常启动日志（`e2631-serial-boot-002.log` 第 70-76、147-213 行）完整显示：初始化 -> 选 slot1 -> 读 4 MiB 内核窗口到 0x42020020 -> 保存 bootpara -> `arg=bootm 0x42020020;` -> `Starting kernel ...`。唯一在跳内核前动 CPU 状态的是标准 ARM bootm 路径里的 `boot_jump_linux` 0x47f01c48 -> `cleanup_before_linux` 0x47f00534。

## 4. 厂商跳内核前的 CP15/缓存动作（实测指令序列）

厂商 `go` 处理器 0x47f03890 也调同一个函数（0x47f038c8 `bl 0x47f00534`，然后 0x47f03880 才是跳转），所以 RAM 链成功时，我们 U-Boot 是在“刚被归一过的 CPU 状态”下被进入的。

`cleanup_before_linux` 0x47f00534 的确切顺序：

| 步骤 | 地址 | 动作 |
| --- | --- | --- |
| 1 | 0x47f0180c | 空 stub（mov r0,#0; bx lr） |
| 2 | 0x47f01b80 | 关 I-cache：SCTLR &= ~0x1000（bit12） |
| 3 | 0x47f00ecc | ICIALLU（mcr p15,0,rX,c7,c5,0）；BPIALL（c7,c5,6）；DSB（c7,c10,4）；ISB（c7,c5,4） |
| 4 | 0x47f01c14 | 若 SCTLR.C=1：先 CISW（clean+invalidate D-cache by set/way，见 0x47f00dfc arg=2），再 SCTLR &= ~0x5（关 MMU 位 0 与 D-cache 位 2） |
| 5 | 0x47f00ee8 | 空 stub |
| 6 | 0x47f00f08 | invalidate D-cache by set/way（0x47f00dfc arg=1，mcr p15,0,rX,c7,c6,2） |
| 7 | 0x47f00530 | 空 stub |

0x47f00dfc 是 set/way 维护例程：读 CCSIDR（mrc p15,1,r4,c0,c0,1）与 CSSELR（mcr p15,2,rX,c0,c0,0），逐 level/way 循环，arg=2 用 c7,c14,2（CISW），arg=1 用 c7,c6,2（ISW），末尾 DSB。

入口侧 `cpu_init_crit` 0x47f0021c-0x47f00230 做 SCTLR 位操作（`bic #0x2000`、`bic #7`、`orr #2`、`orr #0x800`、`orr #0x1000`，即关 MMU/D-cache、开 I-cache），并失效 L1 I/D、TLB、BTB —— 这就是主线 U-Boot 的 cpu_init_cp15/cpu_init_crit 等价物。

**注意：厂商不做 L2/PL310 维护**（全量扫描 0x00c00000 引用为 0）；也不碰 SCU/ACTLR/CNTFRQ。所以这些不是“厂商会做而我们没做”的项。

## 5. 我们的 U-Boot：两条归一通道都被配置关闭

构建配置（`/home/qc233/zte/uboot-build-a1/.config`）：

```
39 CONFIG_SKIP_LOWLEVEL_INIT=y
41 CONFIG_SYS_ICACHE_OFF=y
42 CONFIG_SYS_DCACHE_OFF=y
71 CONFIG_SYS_L2CACHE_OFF=y
```

入口（`uboot-src/arch/arm/cpu/armv7/start.S:117-125`）：`#if !CONFIG_IS_ENABLED(SKIP_LOWLEVEL_INIT)` 同时包住 `bl cpu_init_cp15`（:120）和 `bl cpu_init_crit`（:123，再套 !SKIP_LOWLEVEL_INIT_ONLY）。我们的配置让两条都跳过：入口不失效 I/D cache、不失效 TLB/BTB、不关 MMU/D-cache、不开 I-cache。

缓存 API 被 stub 掉：`arch/arm/lib/cache-cp15.c:265-282`（SYS_ICACHE_OFF 下 `icache_enable/icache_disable` 直接 return）、`:297-310`（SYS_DCACHE_OFF 下 `dcache_enable/dcache_disable` 直接 return）；`arch/arm/cpu/armv7/cache_v7.c:208` 的 `__weak void v7_outer_cache_disable(void) {}` 在 SYS_L2CACHE_OFF 下永远不会被 l2c 实现覆盖。`arch/arm/lib/cache.c:41-44` 的默认 `enable_caches()` 只打印 `WARNING: Caches not enabled`（两份日志都出现，但**RAM 链同样出现**，说明该行本身不是差异信号，真正差异是进入状态）。

跳内核前（`arch/arm/cpu/armv7/cpu.c:26-75`，`cleanup_before_linux_select(CBL_ALL)`，CBL_ALL=3/CBL_DISABLE_CACHES=1 见 `include/cpu_func.h:104-110`；bootm 调用点 `arch/arm/lib/bootm.c:269,331,414`）：

```
dcache_disable();        /* SYS_DCACHE_OFF -> 空 */
v7_outer_cache_disable();/* L2 未初始化 -> 空弱符号 */
invalidate_dcache_all(); /* 真实执行 */
icache_disable();        /* SYS_ICACHE_OFF -> 空 */
invalidate_icache_all(); /* 真实执行 */
```

即：**能失效，但不能 flush，不能关 D-cache/MMU，不能碰 L2**。若进入时 D-cache/MMU 是开的，则我们的 bootm 唯一能做的只是“把 L1 里未回写的脏数据丢掉”（invalidate 而不是 clean），这恰好会把内核镜像/ATAGS 的写丢失，使内核读到旧 DRAM。

（VBAR 不是问题：`arch/arm/lib/crt0.S:170` 仍会 `bl relocate_vectors`。TWD 看门狗也没有直接引用。）

对照表：

| 阶段 | 原厂链 | RAM 链（成功） | 闪存链（挂起） |
| --- | --- | --- | --- |
| 进入 U-Boot 前最后动作 | 厂商 cpu_init_cp15/cpu_init_crit 归一 | 厂商 `go` 的 cleanup 0x47f00534 归一 | secondboot `Jump`（无归一） |
| 我们的 U-Boot 入口归一 | 不适用 | 跳过（SKIP_LOWLEVEL_INIT） | 跳过 |
| bootm 前 cleanup | 厂商自己完整做 | 只剩 invalidate | 只剩 invalidate |
| 内核进入状态 | 正常 | 正常（厂商归一过） | **继承 BootROM/secondboot 状态** |

## 6. 已排除项（逐条证据）

1. **镜像/载荷不同**：见 §2 的第 1 条，闪入载荷与 RAM 链成功所用 u-boot.bin 逐字节相同（sha256 010379fd...）。头部 digest（0x2d4 起 32 B，厂商值 aa19ebce...）没有随新载荷更新，但非安全启动（secondboot 打印 `non secure uboot`），不校验；且**原厂正常日志同样打印 `backup header!!`**（`e2631-serial-boot-002.log:17` 以及每次启动），所以该行是正常路径，不是我们镜像的异常。
2. **内核镜像/CRC/装载/入口不同**：两条链 bootm 输出逐行相同（见 §2）。
3. **bootargs/ATAGS/boot_params 不同**：两条链都由我们的 bootm 构造（`Working FDT set to 0`、r2=0x40000100），闪存链 attach-1 bdinfo 亦为 0x40000100。
4. **bootpara@0x40007000 缺失**：内核源码注释明确：`iwrt-tree/target/linux/zx279128/files/drivers/mtd/parsers/zx279128s-slotpart-core.c:14-16` —— “The v1.3 slotfix tried to read cspboot's bootpara block from RAM; the zImage decompressor uses that page for its own page tables (dumped on hardware: 0x40007000 holds section descriptors), so the block never survives to the kernel.”；`zx279128s-slotpart.c:14-16` 同义。厂商自己在每次启动也都重存 bootpara（原厂日志 147/157/173 行），内核不依赖它。
5. **厂商自定义 ATAG 0x54410011（bootpara）**：构造器 0x47f152b4 只被 0x47f01f64（厂商 bootm 的 ATAGS 准备）调用，追加 0x157 字 + 0x554 B base_bp 拷贝；我们的 bootm 两条链都不加，RAM 链也成功了 -> 不是差异。
6. **L2/PL310、SCU、ACTLR、CNTFRQ**：厂商全量扫描 0 引用/0 写（§0/§4）；原厂链也没开 L2（vendor 启动到内核之间无 0xc00000 访问）。内核的 l2x0 驱动按 DTS 重配（patch 026：l2cc@c00000，注释给出 stock AUX_CTRL=0x76430001 与 shared-override 依赖），U-Boot 不需要匹配。
7. **CPU PLL/时钟**：0x47f01338 只被 0x47f0158c（`clk_pll` env 处理器 0x47f0152c）调用；env 里没有 clk_pll，厂商只打印现状。原厂 banner `1000MHZ` 是 secondboot 已设好的频率读数。
8. **secondboot**：mtd0 0x800..0x68AB 全量扫描无 SCTLR/ACTLR 写、无 0xc00000/0x800000/0x800200/0x800600/0x800620 引用、无 CP15 c15 操作 —— 它不做缓存/MMU/L2/SCU 配置，也不能替我们归一。
9. **看门狗**：厂商只有 `watchdog` 命令处理器直接碰 TWD 0x800620-0x800634；正常启动路径无引用；secondboot 也无。日志中挂起后 13+ 分钟没有新的 BootROM 行，倾向“未复位”（但串口捕获可能已停，见 §9）。

## 7. 排序候选列表

| 排名 | 候选 | 可能性 | 机制 | 证据 | 验证 |
| --- | --- | --- | --- | --- | --- |
| 1 | **C1 继承 D-cache 未 flush/未关** | 高 | BootROM/secondboot 若留 D-cache 开，我们 U-Boot 写内核到 0x40008000、写 ATAGS 0x40000100 的脏行走不到 DRAM；bootm 前只有 invalidate（丢弃）没有 clean | §5 stub 链；§4 厂商在 go 前做 clean+invalidate；无其它差异 | 入口/bootm 前打印 SCTLR 的 C 位；或先做完整 clean+disable 再 boot |
| 2 | **C2 继承 MMU 未关** | 高 | 内核/自解压器假定 MMU 关；TTBR/SCTLR 重设时若 MMU 已开，页表切换未定义 | 同 C1（同一根因的另一位） | 打印 SCTLR 的 M 位/TTBR0 |
| 3 | **C3 入口未失效 L1 I/BTB/TLB** | 中 | SKIP_LOWLEVEL_INIT 跳过 cpu_init_cp15；stale 指令/BTB 条目理论可致静默跑飞 | start.S:117-125 | 实现入口归一后对比 |
| 4 | C4 BootROM/secondboot 遗留的 timer/GIC/TWD 私有状态 | 低 | 内核会重配；但若某私有寄存器把 CPU 停住/复位会静默 | 厂商也不碰（TWD 除外），故非“厂商 vs 我们”差异 | 挂起后再采样串口/复位源 |
| 5 | C5 厂商 board_init_r 外设初始化缺失（GPIO 0x94200000、clkm 0x94000000、UART/NAND/eth） | 低 | 内核驱动都会重做；GPIO 复用若被 secondboot 留成非默认，可能影响但不应致 150 ms 内死 | 厂商初始化序列地址已定位 | 先修 C1/C2，再观察 |
| 6 | C6 闪存装载路径差异（backup header / 长度 / 尾块） | 已排除 | - | §6.1：原厂同样打印；载荷字节相同 | - |

排名逻辑：两条链唯一的系统性差异是“进 U-Boot 前的 CP15 状态是否被厂商归一”，而我们的配置恰好把入口归一和跳转前归一两条路都关掉了；其余候选要么厂商也不做（不是差异），要么内核会自己重做。

## 8. 验证与修复建议

### 8.1 决定性诊断（先做，只读）

在 U-Boot 里加一个只读寄存器转储（入口 earliest、board_late_init、bootm 前各一次）：

```
SCTLR  (c1,c0,0)   CLIDR  (c0,c0,1)   CCSIDR (c0,c0,1 w/ CSSELR)
TTBR0  (c2,c0,0)   DACR   (c3,c0,0)   VBAR   (c12,c0,0)
ACTLR? (c1,c0,1)  —— 只读；若在 QEMU/真机上读不到就跳过
```

然后分别跑两条链：闪存链直接从上电日志抓；RAM 链再走一次 `xmodem 到 0x47F00000 + go`（厂商 cleanup 之后），抓同样三点。对比 SCTLR 的 M(bit0)/C(bit2)/I(bit12) 与 TTBR0 —— 若闪存链进入时 C 或 M 为 1，C1/C2 即确认。

### 8.2 修复形状（与主线一致，不发明厂商行为）

在 board_late_init（或 bootm 前 hook）实现一份**无条件、不依赖 CONFIG_SYS_*CACHE_OFF** 的 asm 序列，等价于主线 cpu_init_cp15 + cleanup：

1. 读 SCTLR；若 C=1：clean+invalidate L1 D-cache by set/way（c7,c14,2），然后 SCTLR.M|C=0；
2. invalidate L1 D by set/way（c7,c6,2）；ICIALLU（c7,c5,0）；BPIALL（c7,c5,6）；TLBIALL（c8,c7,0）；DSB/ISB；
3. 关 I-cache（SCTLR bit12=0）；
4. 可选：PL310 0x00c00000 clean+invalidate all（0x7B0/0x77C = 视 way 数写掩码）后 sync 0x730，再清 aux bit0（0x104 &= ~1）—— 内核会按 DTS 重配，安全；
5. 不要写 ACTLR/SCU/CNTFRQ（没有厂商值可对，内核自己配置）。

同一序列放进 `e2631soc` 命令，用于：闪存链 U-Boot 提示符下先执行 `e2631soc`，再执行 `e2631boot`（**不复位**）——如果内核能起来，C1/C2 确认且修复有效，且不需要额外写 flash。

### 8.3 约束

- 构建走 GitHub Actions（CI-only 提交），本机不做全量编译；
- 任何设备写/flash 操作需 Lead + 用户批准，我本轮只做静态分析与文档。

### 8.4 后续（Lead 2026-11-21 决定）
- 修复补丁（uboot-port patch 0011）按本报告改为 **CP15-only**：去掉 PL310/SCU 写，只做主线口径的 CP15/缓存/MMU 归一；e2631soc 命令 = 同一归一系列 + 入口寄存器回报（SCTLR/TTBR0/CLIDR/VBAR）。
- 可选后续实验（不阻塞今晚的 green；2026-11-21 与 verify-docs 对齐的采集契约）：决定性证据是 SCTLR 的 M(bit0)/C(bit2)/I(bit12) 前后值。e2631soc 当前只报 SCTLR + PL310 + SCU；TTBR0/VBAR 为 nice-to-have（两行打印），CLIDR/CCSIDR/ACTLR 不要求。Session A 采法：闪存链旧 U-Boot（010379fd，cleanup 为 stub，不改 SCTLR）提示符 -> md 读 PL310 ctrl/aux 与 SCU ctrl -> loadx 新 u-boot.bin -> go -> e2631soc 前后值 -> e2631boot（hand-off 前再打印一次）。判定：before 的 M=1 或 C=1 -> 假设确认，after 应读 M=0,C=0,I=0（同时验证 cleanup 实现）；before 全 0 -> 假设弱化，转查 §7 的 C3/C4。RAM 链 vendor 对照默认不做（vendor 会话有 env 漂移风险，且归一顺序已实测、无判定价值）；md 只能读内存，CP15 只能靠 e2631soc 回报。
- 记录口径：本报告的“排除项”基于当时的 vendor 载荷 sha256 a4c640ad… 与 C1b 镜像 010379fd…；若后续重建导致哈希变化需重跑 §10 的比对。

## 9. 低置信与未决

- 没有实测 SCTLR：本文 C1/C2 是“厂商做、我们不做”的静态不对称 + RAM/闪存链唯一差异推出来的，不是直接观测。8.1 是决定性实验。
- secondboot 是否通过非 BL 路径（例如 BootROM 服务/协处理器）改变状态，静态无法排除。
- 挂起后是否发生复位：失败日志在 `Starting kernel ...` 处结束，没有新的 `Boot SPI NAND`/BootROM 行；若串口捕获已停则不能定论。
- 厂商 `versioninfo`/`bootargs` 的 saveenv 副作用已污染当前 mtd0 的 env 块（§2 附带事实），后续实验应以 c1b1-expected-mtd0.bin 为基准。

## 10. 复现方法

1. 取 vendor 载荷（仓库内 tracked）：`evidence/p2-oob/vendor-uboot-ram.bin`；vaddr = 0x47F00000 + file_off。
2. capstone 全量反汇编：`PYTHONPATH=/tmp/pylibs python3`，`Cs(CS_ARCH_ARM, CS_MODE_ARM)`，`md.skipdata=True`，先过滤以 `.` 开头的伪指令再读 operands；base=0x47f00000。
3. 关键扫描：MCR c1,c0,0（SCTLR，编码 0xEE010F10）、c1,c0,1（ACTLR，0xEE010F30）、立即数 0xc00000/0x800000/0x800200/0x800600/0x800620；字符串与 xref 用 `ldr` 字面量池反查。
4. 日志比对：`evidence/c1b0-entry/serial.txt` 与 `/home/qc233/zte/e2631-p3/c1b1-final-v2/run-1/serial.log`；哈希/镜像比对用 `/home/qc233/zte/e2631-p3/c1b1-expected-mtd0.bin` 与 `e2631-t5-artifacts/uboot-47f-44898534408/u-boot.bin`。

---

附：关键地址速查

| 名称 | vaddr |
| --- | --- |
| pdt 全局上下文 | 0x47f6800c |
| pdt_cspboot_init | 0x47f15b7c |
| pdt_cspboot_info_init | 0x47f15ad4 |
| pdt_cspboot_run | 0x47f15c10 |
| cspstart 命令处理器 | 0x47f15ca0 |
| bootk 命令处理器 | 0x47f10364 |
| start-kernel op | 0x47f15808 |
| zteboot_do_settings | 0x47f163bc |
| zteboot_select_pdtver | 0x47f162c0 |
| zteboot_search_firmware | 0x47f12a18 |
| vendor cleanup_before_linux | 0x47f00534 |
| vendor boot_jump_linux | 0x47f01c48 |
| vendor cpu_init_crit | 0x47f0021c |
| vendor go 处理器 | 0x47f03890 |
| vendor 自定义 ATAG 构造 | 0x47f152b4 |

