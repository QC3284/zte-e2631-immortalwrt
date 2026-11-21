# C1b-1 故障与修复：内核跳转前的 CP15 归一化（patch 0011）

本文记录 2026-11-21 首次 flash 启动静默挂死的根因、厂商 U-Boot 逆向证据与 patch 0011 的设计/验收。
只读、不写 flash；不含刷写步骤。

## 1. 现象

- C1b-1 v2 把我们的 U-Boot（448,112 B，entry `0x47F00000`，sha256 `010379fd…`）写入 mtd0 `0x20000..0xC0000`
  后冷启动：BootROM → secondboot → 我们的 banner（`g2797f3dd3860`）→ env MTD OK → `e2631boot` 选 slot1 →
  uImage 头部/数据 CRC 通过 → `Loading Kernel Image to 40008000` → `Starting kernel ...` → 静默 13+ 分钟，
  无 panic、无复位、无网络。
- 对照组：同一 `u-boot.bin`、同一 slot1 内核在 RAM 链（厂商 U-Boot 控制台 `tftp 0x47F00000` + `go`）能进
  Linux；厂商 `cspstart` 直接用自家 loader 启动同一 slot1 内核也能进用户态（23:18:46 / 23:19:40）。
- 所以 boot path、内核字节、CRC、ATAGS（`boot_params=0x40000100`）都不是问题；差异在 secondboot 交接的
  CPU/SoC 状态。

## 2. 厂商 U-Boot 逆向测量结论

对象：`evidence/p2-oob/vendor-uboot-ram.bin`（426,048 B，sha256 `a4c640ad…`，vaddr = `0x47F00000` + file
offset），完整线性 capstone 反汇编（约 106K 条指令）。证据文档：
[evidence/p2-flashboot-kernel-hang-20261121.md](../evidence/p2-flashboot-kernel-hang-20261121.md)（iwrt-baseline，§3-§8）。

- 入口：reset（`0x47f00058`）→ cpu_init_cp15/cpu_init_crit（`0x47f0021c`）：invalidate L1 I/D、TLB、BP；
  SCTLR 清 V、清 M/C，I-cache 开、D-cache/MMU 关。
- 跳转前：go handler（`0x47f03890`）在 `0x47f038c8` 调 cleanup_before_linux（`0x47f00534`）：
  (a) `0x47f01b80` SCTLR.I=0；
  (b) `0x47f00ecc` ICIALLU + BPIALL + DSB + ISB；
  (c) 若 SCTLR.C：clean+invalidate D by set/way（`0x47f00dfc` arg=2），然后 SCTLR.M|C=0（`0x47f01c14`）；
  (d) `0x47f00f08` invalidate D by set/way（arg=1）+ DSB。
- PL310：全镜像 0 次引用（`#0xc00000` 0 次，无 CP15 c15 操作，无 L2 enable/disable/invalidate）。
- SCU：0 次；A9 SCU `0x00800000` 只出现在厂商 watchdog 命令处理里对 TWD WDT（`0x80062x`）的访问。
- ACTLR（c1,c0,1）：0 次写；SCTLR 写只出现在上述入口/cleanup/cache helper/MMU 开关点。
- 结论：厂商在跳内核前只做 CP15 归一化，不做 PL310/SCU/ACTLR/时钟初始化；内核自己初始化 L2/SCU。

## 3. 根因

我们的 port 当时 defconfig 是：

```
CONFIG_SKIP_LOWLEVEL_INIT=y
CONFIG_SYS_ICACHE_OFF=y
CONFIG_SYS_DCACHE_OFF=y
CONFIG_SYS_L2CACHE_OFF=y
```

- `SKIP_LOWLEVEL_INIT=y` 让 start.S 跳过 `cpu_init_cp15` 和 `cpu_init_crit`（`arch/arm/cpu/armv7/start.S:118-124`），
  secondboot 留下的 CP15 状态被原样继承；
- `SYS_*CACHE_OFF` 让 `icache_disable`/`dcache_disable` 变成空桩、`v7_outer_cache_disable` 是空弱符号
  （`arch/arm/lib/cache-cp15.c:265-330`、`arch/arm/cpu/armv7/cache_v7.c:154-179/208`），于是 bootm 前的
  `cleanup_before_linux_select(CBL_ALL)`（`arch/arm/cpu/armv7/cpu.c:26-75`）退化成只调
  `invalidate_dcache_all`/`invalidate_icache_all`，而这两个在该配置下也是空桩；
- 如果 secondboot 交接时 D-cache 是开的（BootROM 留下的状态；secondboot 自身没有 SCTLR/ACTLR 写），
  刚载入的 `0x40008000` 内镜像和 `0x40000100` 的 ATAGS 可能还在脏 L1 行里；只 invalidate 不 flush 会把
  脏行丢掉，DRAM 里留下旧内容，内核在第一条串口输出前就死了；
- RAM 链之所以能启动：厂商 U-Boot 的 `go` 在跳转前已经跑过 `0x47f00534` 的完整清理，我们的 U-Boot
  继承的是归一化后的状态。

## 4. 修复（patch 0011）

1. defconfig 移除 `CONFIG_SKIP_LOWLEVEL_INIT`：标准 `cpu_init_cp15`/`cpu_init_crit` 在入口重新生效；
   `lowlevel_init`/`s_init` 仍是 U-Boot 通用空弱符号，不做时钟/DRAM/UART（secondboot 已完成）。
2. 新增 `board/zte/zxhn-e2631/e2631soc.c`：`e2631_soc_prepare_linux()` 以纯内联汇编执行第 2 节的
   cleanup 顺序（I off → ICIALLU+BPIALL+DSB+ISB → D clean+invalidate by set/way → 清 M/C →
   D invalidate by set/way）；不依赖 `SYS_*CACHE_OFF` 桩，也不做 PL310/SCU/ACTLR 写。
3. `e2631boot.c` 在 `bootm` 前的最后一步调用它（single code path）。
4. 新增 `e2631soc` 命令：运行同一函数，先打印 before dump，再打印 `running vendor-order CP15 cleanup`，
   再打印 after dump，最后回到 `=>`，不启动、不写 flash、不写 env。
5. env 保持只读：`CONFIG_CMD_SAVEENV` 仍编掉，`ENV_IS_IN_MTD` 只加载；本补丁不增加任何 env 写。

## 5. e2631soc 输出契约

一次运行输出（换行分隔，数值为 32-bit 十六进制；M/C/I 为 0/1）：

```
e2631soc: before  SCTLR=0x........ (M=. C=. I=.) CLIDR=0x........ TTBR0=0x........ VBAR=0x........ ACTLR=0x........ DACR=0x........ CCSIDR=0x........
e2631soc: running vendor-order CP15 cleanup
e2631soc: after   SCTLR=0x........ (M=. C=. I=.) CLIDR=0x........ TTBR0=0x........ VBAR=0x........ ACTLR=0x........ DACR=0x........ CCSIDR=0x........
e2631soc: read-only L2/SCU: PL310 0x00c00000 ctrl=0x........ aux=0x........ SCU 0x00800000 ctrl=0x........
e2631soc: back at the prompt, nothing was booted
```

- CCSIDR 读取前把 CSSELR 指向 L1 data（level 0），两次 dump 描述同一 cache。
- PL310/SCU 只读（`0x00c00000` + `0x100/0x104`，`0x00800000` + `0x000`），不做任何写。
- `bootm` 自动路径会打印同样的前 4 行（`e2631_soc_prepare_linux()` 内），但没有最后一行；autoboot 日志里
  看到它们属正常。

## 6. 验收

1. CI（`uboot-build.yml`）必须：11 个 patch、post-am tree `c8914654…`、
   `# CONFIG_SKIP_LOWLEVEL_INIT is not set`、二进制含 `e2631boot`/`e2631soc`/`spi-nand0`、形状断言
   （`e2631boot.c` 调 `e2631_soc_prepare_linux`、`e2631soc.c` 有 `mcr p15`）、载荷 ≤ `0x9F800`、
   entry `0x47F00000`。
2. RAM 链 A/B（零写入，先做）：厂商控制台 `tftp 0x47F00000` + `go`，在提示符跑 `e2631soc` 记录前后
   dumps（此时厂商 `go` 已清理过，after 应与 before 基本一致），再 `e2631boot` 确认内核仍能启动。
3. flash 链（需用户批准）：把新 mtd0 镜像写入后冷启动，预期：banner → env MTD OK → `e2631boot` 选 slot1 →
   `e2631soc: before ...`（此时 before 的 SCTLR 可能显示 M/C=1）→ after M=C=0 → `Starting kernel ...` →
   内核起来。若仍静默，用 before/after dumps 判定是入口段还是清理段，不得在没有新证据前继续写 flash。
4. mtd0/env 零写审计：本次改动的两条路径都不写 flash；env 块由 CI 从跟踪文本重建，sha256 应与上一产物
   一致（CI 输出记录）。

## 7. 边界与风险

- 入口配置改动影响所有链：RAM 链（厂商 `go`）也会跑标准入口归一化；必须先做第 6.2 的 RAM 链 A/B。
- 非 PIE / TEXT_BASE 约定不变：0010 的入口 = 链接地址 `0x47F00000`，本补丁不改。
- 不做 PL310/SCU/ACTLR/时钟初始化是有证据的取舍（厂商也不做）；若后续设备证据显示 L2 状态异常，再单独
  立项读-改-验证，而不是在启动路径里盲写寄存器。
- 回退：单独 revert 0011 可回到仅 0010 的状态；0010 的入口地址与文档不依赖 0011。
- `e2631soc` 的 PL310/SCU 读取依赖 secondboot 已给这两个控制器上时钟；若真机读挂死，说明该假设不成立，
  先把只读行拆掉再定位（CP15 dumps 不受影响）。

## 8. 参考

- [evidence/p2-flashboot-kernel-hang-20261121.md](../evidence/p2-flashboot-kernel-hang-20261121.md)（iwrt-baseline，厂商逆向 §3-§8）
- [evidence/uboot-re-20261115.md](../evidence/uboot-re-20261115.md)（mtd0 布局/入口）
- [evidence/c1b1a-write-rehearsal-20261121.md](../evidence/c1b1a-write-rehearsal-20261121.md)（写通道演练）
- [README.md](README.md)（pin、CI 断言、A1/A2/A3 步骤）
- 内核侧地址来源：`target/linux/zx279128/patches-6.18/026-ARM-dts-zte-Add-ZX279128S-SoC-description.patch`
  （l2cc `0x00c00000`、SCU `0x00800000`、GIC `0x00801000`）
