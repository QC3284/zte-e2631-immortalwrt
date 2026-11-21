# C1b-1 修复交付：patch 0011（CP15 归一化）构建与 e2631soc 契约

日期：2026-11-21。范围：kit 仓库 iwrt-adaptation 分支的 U-Boot port（`uboot-port/`），CI 构建产物与
设备会话（Session A）判读规则。本轮不写 flash、不写 env、不接触设备。

## 1. 目标与边界

- 问题：C1b-1 首次 flash 启动时，我们的 U-Boot 在 `Starting kernel ...` 后静默挂死；同一内核经厂商
  `cspstart` / RAM 链都健康。根因分析见 [p2-flashboot-kernel-hang-20261121.md](p2-flashboot-kernel-hang-20261121.md)
  与 [uboot-port/a4-soc-state-design.md](../uboot-port/a4-soc-state-design.md)。
- 修复：patch 0011——跳内核前按厂商 `cleanup_before_linux()`（`0x47f00534`）顺序做 CP15 归一化；
  defconfig 移除 `CONFIG_SKIP_LOWLEVEL_INIT` 让入口归一化恢复；新增 `e2631soc` 只读诊断命令。
- 不做：PL310/SCU/ACTLR/时钟初始化（厂商镜像同样不做）、env 写入、flash 写入、本地编译。

## 2. 交付物

- patch：`uboot-port/patches/0011-board-zte-normalise-CP15-before-the-Linux-hand-off.patch`，
  sha256 `98aa4b3914ff1741e0621116b4d630ab43f448d7d0ca31496c2001e815b51095`（12,446 B）。
- 系列：11 个 patch，post-am tree `c8914654a4787fdc67c30bea44de5d70d39e8fdc`（pin 在 `uboot-port/commits.env`）。
- kit 提交：`dcdf4a5`（patch/pin/workflow/README/design doc）、`270707b`（commits.env 头注释修复）——
  分支 `iwrt-adaptation`，tip `270707b68fd467904c96697cda3b7124938b3678`。

## 3. CI 构建结果

- `uboot-build.yml` run `44921033410`（workflow_dispatch，head `270707b`）：SUCCESS，全部 gate 通过。
  URL：https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44921033410
- 同 tip 的 kit check：`check.yml` run `44921032701` SUCCESS。
- 过程记录：首次 dispatch run `44920790242` 在读取 pin 的 sourcing 步骤失败——新增头注释的第二行漏了
  `#`，`bash` 把 `the C1b flash-boot CP15 fix).` 当命令解析；`270707b` 修复后重跑。
- 构建值：

| 项目 | 值 |
| --- | --- |
| banner token | `g6f5036fa039d`（`U-Boot 2027.01-rc2-g6f5036fa039d (Nov 21 2026 - 15:48:04 +0000)`） |
| u-boot.bin | 449,240 B（limit 653,312 B，margin 204,072 B） |
| u-boot.bin sha256 | `bef0d841bc26e2dc9db4484e26285d23d8d3bf9e1a63ad81f080c28b026206f4` |
| mtd0 镜像 sha256 | `83457522357bc4d55f4a36d3dd912ff9184c31dad754cec3dff3a9d1f7c2412e`（655,360 B） |
| mtd0 载荷长度 | 0x6dad8（449,240 B），边界 0x20000..0xC0000 |
| mtd0 头块（装配后镜像前 0x800 B） | sha256 `703463fc0868840e5cdc5bf70c88ffb1f13b5527b4c500da7280855271d812b1` |
| vendor 头模板（重写 +0x14 长度前的输入块） | sha256 `19a9d54614e9d5cdfb7573495609448cdf1a740e470fbebcac5783c8e9b93510` |
| env 块 | `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`（与前三份产物逐字节一致） |
| entry point | 0x47f00000 |
| 工具链 | arm-none-eabi-gcc 13.2.1 20231009 |

- `.config` 关键项：`# CONFIG_SKIP_LOWLEVEL_INIT is not set`、`# CONFIG_SKIP_LOWLEVEL_INIT_ONLY is not set`、
  `CONFIG_TEXT_BASE=0x47F00000`、`CONFIG_CUSTOM_SYS_INIT_SP_ADDR=0x48000000`、
  `# CONFIG_POSITION_INDEPENDENT is not set`、`CONFIG_ENV_IS_IN_MTD=y`、`# CONFIG_CMD_SAVEENV is not set`。
- 二进制串：`e2631boot`（18 处）、`e2631soc`（5 处）、`spi-nand0`、`zte,zx29-uart` 均在。

> 勘误（2026-11-21）：`UBOOT-INFO.txt` 里 `mtd0 image header` 那一行的 sha256 是 **vendor 模板输入块**
> （`19a9d546…`），重写 `+0x14` 长度字段之前的字节；装配后镜像头块实际哈希是 `703463fc…`。两者只差
> 4 字节长度字段，镜像本身正确。本记录按装配后值引用。
- checkpatch：0 errors / 9 warnings（全部为已知项：MAINTAINERS 路径检查 5、livetree 2、new command 2）；
  其中 0011 自身 0 errors / 2 warnings。

## 4. 产物清单

本地目录：`/home/qc233/zte/e2631-t5-artifacts/uboot-c1b-fix-44921033410/e2631-uboot-44921033410/`
（`u-boot.bin`、`e2631-uboot-mtd0.bin`、`e2631-env-block.bin`、`.config`、`u-boot.map`、`build.log`、
`checkpatch.txt`、`UBOOT-INFO.txt`、`SHA256SUMS`）。

## 5. e2631soc 输出契约

一次运行输出（`e2631soc` 命令，或 bootm 自动路径的前四行）：

```
e2631soc: before  SCTLR=0x........ (M=. C=. I=.) CLIDR=0x........ TTBR0=0x........ VBAR=0x........ ACTLR=0x........ DACR=0x........ CCSIDR=0x........
e2631soc: running vendor-order CP15 cleanup
e2631soc: after   SCTLR=0x........ (M=. C=. I=.) CLIDR=0x........ TTBR0=0x........ VBAR=0x........ ACTLR=0x........ DACR=0x........ CCSIDR=0x........
e2631soc: read-only L2/SCU: PL310 0x00c00000 ctrl=0x........ aux=0x........ SCU 0x00800000 ctrl=0x........
e2631soc: back at the prompt, nothing was booted
```

- 数值 32-bit 十六进制；M/C/I 为 0/1 十进制；CCSIDR 读取前 CSSELR=0（L1 data）。
- PL310/SCU 只读，不写任何寄存器。
- `bootm` 自动路径打印前四行，没有最后一行。

## 6. 判读规则

- 新 build 的入口归一化已恢复（`SKIP_LOWLEVEL_INIT` 关闭）：`e2631soc` 的 before 采样很可能已经是
  M=0、C=0、I=1 的归一化状态。此时 before/after 主要证明 dump 路径与幂等性，不再代表 secondboot
  继承值。
- 若 before 出现 M=1 或 C=1：说明入口归一化没有生效（例如实际运行的不是本 build），优先查启动链与
  banner token。
- 若 `e2631soc` 命令存在但 PL310/SCU 行挂死：说明 secondboot 未给这两个控制器上时钟；先去掉只读行，
  CP15 dump 不受影响。
- 若新 build 连 banner 都没有：入口 `cpu_init_cp15`/`cpu_init_crit` 链（含 `lowlevel_init`/`s_init`）
  出问题——这是本轮新增的失败模式，先查入口代码，不要归因到内核。

## 7. 设备会话（Session A）命令契约

零 flash 写入的 A/B（已执行，2026-11-21 23:58，实测见 §7.1）：

1. 从当前已烧入的旧 U-Boot（sha `010379fd…`，banner `g2797f3dd3860`）进入命令行；
2. 把新 `u-boot.bin` 载到 `0x47F00000`（`loadx`/`xmodem`），`go 0x47F00000`；
3. 新 banner 应为 `g6f5036fa039d`；
4. 运行 `e2631soc`，抓取上面 5 行（判读规则见 §6）；
5. 运行 `e2631boot` 确认 RAM 链内核仍能启动（证明 CP15 清理不破坏 RAM 链）；
6. 全程不执行 `mtd`/`erase`/`saveenv`。

每个步骤的串口记录由 verify-docs 落盘；本文件只定义命令与期望字符串，不替代实测证据。

### 7.1 Session A 实测结果（2026-11-21 23:58，verify-docs）

- 环境：旧 flash U-Boot（sha `010379fd…`，banner `g2797f3dd3860`）→ `loadx` 449,240 B 到 `0x47F00000` →
  `go` → 新 banner `g6f5036fa039d`；`e2631soc` 5 行 + `e2631boot` 前 4 行；mtd0 未写。
- 原始值（before == after）：`SCTLR=0x08c50878 (M=0 C=0 I=0)`、`CLIDR=0x09200003`、`TTBR0=0x5fafefdb`、
  `VBAR=0x4ff94000`、`ACTLR=0x00000000`、`DACR=0x67deafef`、`CCSIDR=0x701fe019`。
- L2/SCU：PL310 基址 `0x00c00000` 的 ctrl=0、aux=0x02030000；SCU ctrl=0；md 探针 type=0x410000c9、
  latency=0x00000111、SCU cfg=0x00000501。
- 判读：`I=0` 由 `SYS_ICACHE_OFF` 设计（`cpu_init_crit` 清 I 位）；`TTBR0`/`DACR` 是 MMU 关闭下的残留，
  内核 head.S 会重置；`ACTLR=0` 与厂商一致；`CCSIDR` 解出 32 KB、4 路、32 B line、256 组 L1 D 几何；
  PL310/SCU 都处于禁用状态，aux 不是 stock 的 `0x76430001`，与厂商逆向结论一致——没有 L2/SCU 写需求。
- 结论：内核启动、无 panic/abort；patch 0011 对 RAM 链无回归，bootm 前清理幂等。但该链在 `e2631soc`
  之前已被入口归一化（以及旧 U-Boot 的清理）置为 M=C=0，before==after **不能**证明 C1b 的脏缓存机制；
  决定性验证仍是 Session C（secondboot → 我们的 U-Boot → 内核）。

### 7.2 网络异常（Session A 新发现，待归因）

- 内核日志：`zx279128s-eth ... port 0: PHY connect failed`（-ENODEV，2.70 s）与
  `RTNL: assertion failed at drivers/net/phy/phylink.c (2716)`；`/sys/class/net` 只有 lo/br-lan，br-lan DOWN；
  `MT7916 initialization failed`（152 s）。
- patch 0011 只改 CP15（`e2631soc.c`、`e2631boot.c` 一处调用、defconfig 一行），没有 clock/reset/GPIO/
  pinmux/PCIe/DTS 代码，不能通过寄存器写把 PHY 或 MT7916 置于复位状态。
- 关键环境差异：本次是第一条**厂商 U-Boot 板级初始化没有运行**的链（secondboot → 我们的 U-Boot → 内核）；
  C1a 的 WiFi 成功运行是从厂商控制台 `go` 启动，厂商板级初始化已经跑过。
- 假设：自定义 bootloader 链缺少内核/DT 依赖的厂商板级外设初始化（GMAC/MDIO clock/reset、PCIe/MT7916），
  或应改在内核 DT/时钟依赖侧解决。
- 下一步：采集 dmesg/clk_summary/PCIe 设备/net operstate；逆向厂商 U-Boot 板级初始化（DRAM/UART 之外的
  clock/reset/PCIe/GMAC/GPIO/pinmux 写）；在归因前不进行 Session B 的 flash 写。

## 8. 零写审计与安全性

- CI 产物中的 env 块 sha256 与上一构建完全一致（`6eee153b…`），说明 env 文本/打包未被 patch 0011 改变。
- `e2631soc` 与 bootm 路径只做 CP15 与只读读取，不写 flash、不写 env。
- 入口归一化只在 RAM 中执行，不改 mtd0 内容。

## 9. 风险与回退

- 入口配置影响所有链（含厂商 `go` RAM 链）：已用构建 gate 与串口契约约束；RAM 链回归时优先回退 0011。
- 单独 revert 0011 可回到仅 0010 的状态；0010 的 `0x47F00000` 入口与文档不依赖 0011。
- 厂商 `cleanup_before_linux` 的字节级等价性未逐指令证明；本轮采用其顺序与寄存器操作集合，并在文档
  中记录取舍（不做 L2/SCU 写）。

## 10. 参考

- [p2-flashboot-kernel-hang-20261121.md](p2-flashboot-kernel-hang-20261121.md)（厂商逆向与根因候选）
- [uboot-port/a4-soc-state-design.md](../uboot-port/a4-soc-state-design.md)（修复设计、契约、验收）
- [uboot-port/README.md](../uboot-port/README.md)（pin、CI 断言、A1/A2/A3 步骤）
- Session A 原始串口记录与网络异常取证由 verify-docs 落盘（kit `evidence/` 目录）；本文件只引用数值。
- [c1b1a-write-rehearsal-20261121.md](c1b1a-write-rehearsal-20261121.md)（写通道演练）
