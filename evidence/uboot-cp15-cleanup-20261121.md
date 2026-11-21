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
| mtd0 头块 | 0x800 B，sha256 `19a9d54614e9d5cdfb7573495609448cdf1a740e470fbebcac5783c8e9b93510` |
| env 块 | `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`（与前三份产物逐字节一致） |
| entry point | 0x47f00000 |
| 工具链 | arm-none-eabi-gcc 13.2.1 20231009 |

- `.config` 关键项：`# CONFIG_SKIP_LOWLEVEL_INIT is not set`、`# CONFIG_SKIP_LOWLEVEL_INIT_ONLY is not set`、
  `CONFIG_TEXT_BASE=0x47F00000`、`CONFIG_CUSTOM_SYS_INIT_SP_ADDR=0x48000000`、
  `# CONFIG_POSITION_INDEPENDENT is not set`、`CONFIG_ENV_IS_IN_MTD=y`、`# CONFIG_CMD_SAVEENV is not set`。
- 二进制串：`e2631boot`（18 处）、`e2631soc`（5 处）、`spi-nand0`、`zte,zx29-uart` 均在。
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

零 flash 写入的 A/B（等待用户/Lead 排期，本轮不执行）：

1. 从当前已烧入的旧 U-Boot（sha `010379fd…`，banner `g2797f3dd3860`）进入命令行；
2. 把新 `u-boot.bin` 载到 `0x47F00000`（`loadx`/`xmodem`），`go 0x47F00000`；
3. 新 banner 应为 `g6f5036fa039d`；
4. 运行 `e2631soc`，抓取上面 5 行（判读规则见 §6）；
5. 运行 `e2631boot` 确认 RAM 链内核仍能启动（证明 CP15 清理不破坏 RAM 链）；
6. 全程不执行 `mtd`/`erase`/`saveenv`。

每个步骤的串口记录由 verify-docs 落盘；本文件只定义命令与期望字符串，不替代实测证据。

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
- [c1b1a-write-rehearsal-20261121.md](c1b1a-write-rehearsal-20261121.md)（写通道演练）
