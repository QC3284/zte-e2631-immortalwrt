# E4-研2：thin（25 patch）镜像 U-Boot env 读取回归的离线根因分析

日期：2026-11-27　作者：iwrt-baseline　状态：离线分析结论 + 给 base-builder 的修改建议
边界：本文只做静态/离线分析，未改任何代码、未动 uboot-port/、未接触设备。

## 0. 结论摘要

| 项目 | 判定 | 置信度 |
| --- | --- | --- |
| 现象是否存在 | 是。thin 25-patch 镜像（banner `ge6678e875e60`）在 RAM 链上 `Loading Environment from MTD...` 后打印 `*** Warning - bad CRC, using default environment`，随后回退默认 env 并给 eth0 随机 MAC `26:a1:2f:29:78:ac`（同一原因的两个表现） | 高（设备实测一次） |
| 触发范围 | 设备证据只能收敛到 **0023 + 0024 + 0025** 三个补丁：设备上 env 正常的最新一代镜像是 22-patch（494,208 B），25-patch thin 失败，中间的 24-patch 构建**从未上过设备**。静态证据进一步把**行为差异**收敛到 0025 的那一行 defconfig | 高（约 80–85%） |
| 机制 | env/MTD/SPI/malloc 相关代码在两份二进制里**字节级等价**，env 相关 config 符号**完全相同**，所以不可能是这些路径的逻辑 bug；只能是运行时状态差异：重定位/堆基址平移 `0x2743C`（160,828 B），以及 env 之前少了 3 个 initcall | 中低（离线不可判；约 45% 地址/布局、30% 初始化时序、10% SCTLR.A、15% 一次性读错） |
| 是否阻塞 0026 验收 | 不阻塞（按修正后的决策）：**保留 0025**，改用「重试 + 诊断」补丁处理 env 回归，见 §12；§8-A 的「去掉 0025」建议已撤回 | 中（需设备验证重试是否治愈） |

最重要的一条给上层的可执行结论：**E4 v1 不需要 0025 的瘦身**。0025 只省了 174,032 B，而 0026–0029 只增加 39,776 B，E4 完全不缺这个空间。把 0025 从 E4 构建里拿掉，是在根因未钉死前零风险解阻验收的做法。

## 1. 输入与证据口径

本分析引用的构建产物都在本机 `~/zte/e2631-t5-artifacts/` 下，日志在仓库 `evidence/` 下。

| 角色 | 构建 | u-boot.bin | banner | 设备实测 |
| --- | --- | --- | --- | --- |
| 上设备 env 正常的基准 | run 44991454540（22-patch，可复现构建 a） | 494,208 B | `gf355ce89283c` | 是，env OK |
| 同上（另两次 22/23-patch 构建） | run 44982672016、44981256822、44983615483 | 494,208 B | `g6bd1fbd087ba`、`gdfcc418f2f3f`、`gc7ac1db6eb7f` | 是，env OK |
| 24-patch（含 0023+0024，未含 0025） | run 45985501668 | 494,880 B | `gcbcaeea0d172` | **否**（全部 evidence 日志里搜不到该 banner） |
| 25-patch thin（含 0025） | run 45988430055 | 320,848 B | `ge6678e875e60` | 是，**env 失败** |
| 29-patch E4（thin + 0026–0029） | run 46002766353 | 360,624 B | `ga9d4df78ce6e` | 否（尚未验收） |

关键 log 行：

- env 失败：`evidence/e2b-session/thin-run2/serial.txt:52`（thin banner）、`:58`（`*** Warning - bad CRC, using default environment`）、`:62`（随机 MAC）。同一份日志 `:26` 与 `:33` 是 flash 上 15-patch 镜像（banner `g85df6772a444`）在几秒前的 `Loading Environment from MTD... OK`。
- env 正常：`evidence/e2b-session/serial-run1.txt:33` 与 `:59`；`evidence/e2-failure/serial-run1.txt:34` 与 `:60`（后者是 22-patch RAM 镜像，`Net: eth0: ethernet@92000000`，未回退默认 env）。
- 22-patch RAM 镜像读 env 正常的归档结论：`evidence/e2b-session-20261127.md` §10.5（MAC `00:41:71:00:00:50`，即 flash env 里的固定 MAC）。
- flash env 块本身合法：`evidence/b1-env-session-20261121.md:13-14`、`:75-80`（存储 CRC = 重算 CRC = `0xF95A816E`，26 条目，块 sha256 `6e2c01da...`）。该块随后又被多次设备会话读过（15-patch 镜像每次冷启动都 `OK`），到 thin 会话前仍是合法块。

## 2. 隔离：设备证据 + 静态证据

设备证据按时间顺序只覆盖两类镜像：

1. 22-patch 系列（494,208 B）：env 读 OK。
2. 25-patch thin（320,848 B）：env 读失败。

两者之间新增了 0023、0024、0025 三个补丁；24-patch 构建（45985501668）没有设备日志，因此**设备证据不能单独排除 0023/0024**。这不是我最初的说法，特此更正。

静态看三个补丁改了什么（`uboot-port/patches/` 实测 diff 文件列表）：

| 补丁 | 改动文件 | 能否影响 env 读取 |
| --- | --- | --- |
| 0023 `drivers/net: report TX failures...` | 仅 `drivers/net/zx279128s_eth.c` | 否。以太网在 `board_init_r` 后段才初始化，晚于 env；env 阶段该文件没有任何代码被执行 |
| 0024 `board: zte: assert the staging...` | `board/zte/zxhn-e2631/e2631boot.c`、`e2631flash.c`、`drivers/net/zx279128s_eth.c` | 否。三个文件全部是编译期 `static_assert` / 构建期断言，不产生运行时行为 |
| 0025 `configs: zxhn-e2631: drop the unused EFI, MMC, FAT...` | 仅 `configs/zx279128s_zte_zxhn-e2631_defconfig`，一行 `+# CONFIG_MMC is not set`（该文件第 36 行） | 是（唯一候选）：MMC 默认 y → 选 BLK → EFI_LOADER/BOOTSTD/FAT 等 56 个符号连锁消失，二进制体积 -174,032 B、env 之前的 initcall 变少 |

因此：**触发补丁 = 0025**，置信度高（约 80–85%）；保留 15% 的余量是因为没有做过「0025 单独回退」的构建实测，理论上 0023/0024 引入的 672 B 代码/数据也可能通过布局影响触发（见 §5）。

## 3. 0025 的 config 影响面

两份 `.config`（24-patch 45985501668 与 thin 45988430055）逐行 diff 结果：

- `diff` 共 140 行：**56 个符号从 `=y` 消失**、新增 6 行 `# CONFIG_... is not set`、其余 78 行是被删分节头/注释。全部是 `# CONFIG_MMC is not set` 的连锁：EFI_LOADER 及全部 EFI_*、BOOTSTD/BOOTMETH_*、PXE_UTILS、MENU、EVENT/DM_EVENT、BOOTDEV_ETH、BLK/BLOCK_CACHE、MMC/DM_MMC、FS_FAT/FAT_*、CHARSET、LIB_UUID、PARTITION_UUIDS、SHA1、SMBIOS、LAST_STAGE_INIT。
- **与 env/MTD/SPI/内存相关的符号完全不变**：`CONFIG_ENV_SIZE=0x20000`、`CONFIG_ENV_OFFSET=0xc0000`、`CONFIG_ENV_ADDR=0x0`、`CONFIG_ENV_IS_IN_MTD=y`、`CONFIG_ENV_MTD_DEV="spi-nand0"`、`CONFIG_MTD=y`、`CONFIG_DM_MTD=y`、`CONFIG_MTD_SPI_NAND=y`、`CONFIG_SPI=y`、`CONFIG_DM_SPI=y`、`CONFIG_SPI_MEM=y`、`CONFIG_SPI_ZX=y`、`CONFIG_SYS_MALLOC_LEN=0x400000`、`CONFIG_CUSTOM_SYS_INIT_SP_ADDR=0x48000000`、`CONFIG_SYS_LOAD_ADDR=0x42000000`。
- 唯一被删掉的 env 相关行是 `# CONFIG_ENV_IS_IN_MMC is not set`（MMC 没了，该行自然消失），不影响行为。

结论：**env 读取路径的编译产物在两份镜像里应当是同一份代码**，这一点在 §4 得到验证。

## 4. 字节级等价证明（反汇编比对）

方法：capstone 5.0.7 反汇编两份 `u-boot.bin`（链接基址 0x47F00000，`file_off = vaddr - 0x47F00000`），对函数做「归一化」比较（把绝对地址字面量抹成符号位，其余逐条指令比较）。

| 符号 | 24-patch 地址 | thin 地址 | 大小 | 归一化结果 |
| --- | --- | --- | --- | --- |
| `env_mtd_load` | 0x47F2DB60 | 0x47F216D8 | 0x13C | 相同（76 条指令，仅绝对地址字面量不同） |
| `mtd_probe_devices` | — | — | 2832 B | 相同（247 条） |
| `mtd_read` | — | — | 252 B | 相同（62 条） |
| `spi_mem_exec_op` | — | — | 456 B | 相同（113 条） |
| `nanddev_isbad` | — | — | 152 B | 相同（38 条） |
| `env_import` | — | — | 220 B | 相同（49 条） |
| `memalign` / `malloc` | — | — | 392 B / 1524 B | 相同（98 条 / 372 条） |

另外直接比对了 `mtd_read`/`mtd_block_isbad`/`nanddev_isbad`/`mtd_probe_devices`/`spinand_mtd_read`/`spi_mem_exec_op`/`zx_qspi_exec_op`/`zx_qspi_probe`/`spinand_probe` 等函数在两次构建中的 code bytes：**除重定位地址外逐字节相同**。

结论：排除「env/MTD/SPI 代码逻辑在两版之间被改坏」这一整类解释。差异只能来自运行时。

## 5. 运行时差异清单

### 5.1 重定位地址与堆基址平移（第一候选）

- 24-patch：`bss` 结束 0x47F75E6C → `mon_len = 0x75E6C`；`relocaddr = 0x50000000 - mon_len = 0x4FF8A194`；`malloc` 区起点（= 堆基址）= `relocaddr - CONFIG_SYS_MALLOC_LEN(0x400000) = 0x4FB8A194`。
- thin：`bss` 结束 0x47F4EA30 → `mon_len = 0x4EA30`；`relocaddr = 0x4FFB15D0`；堆基址 = `0x4FBB15D0`。
- 平移量：`0x2743C` = **160,828 B**（约 157 KiB）。
- `env/mtd.c:152` 的 `memalign(ARCH_DMA_MINALIGN, CONFIG_ENV_SIZE)` 是重定位后堆上的**第一次大分配**（env 之前的 initcall 分配都走 early malloc / 小对象），所以 env 缓冲区的物理地址在两版之间**正好差这 160,828 B**。

如果存在任何与缓冲区物理地址相关的行为（DMA/位翻转/未初始化内存路径/上一级 bootloader 遗留内存），这就是唯一被改变的量。

### 5.2 env 之前少跑的 initcall（第二候选）

`common/board_r.c` 的顺序（行号为 U-Boot c1958b5f 附近）：`initr_malloc`(:619) → `initr_dm`(:629，`dm_init_and_scan(false)` + `dm_autoprobe`) → `initr_lmb`(:647) → `efi_memory_init`(:649，**thin 中消失**) → `initr_dm_devices`(:657) → stdio/serial(:658-659) → `initr_mmc`(:703，**thin 中消失**) → `initr_env`(:712)。

其中 `efi_init_early`（thin 中消失）唯一的 CPU 状态动作是 `allow_unaligned()`（`lib/efi_loader/efi_setup.c:192`，最终在 `arch/arm/cpu/armv7/sctlr.S` 清 SCTLR.A 位）。注意 patch 0011 已经移除 `CONFIG_SKIP_LOWLEVEL_INIT`，所以 `arch/arm/cpu/armv7/start.S` 的 `cpu_init_cp15` 在 U-Boot 入口确实会跑，并把 SCTLR.A 置 1；EFI 消失后 env 之前没有代码再清 A 位（见 5.4）。

### 5.3 被排除的 config 侧影响

- `CONFIG_LAST_STAGE_INIT` 的执行点在 `initr_env` **之后**，无关。
- `CONFIG_EVENT`/`CONFIG_DM_EVENT` 消失后只少一次 `event_notify_null(EVT_DM_POST_INIT_R)`；本构建树里没有注册该事件的处理器（只有 i.MX/RISC-V 相关驱动），无关。
- `CONFIG_MENU`/`BOOTSTD` 不影响 `e2631boot` 这条显式 `bootcmd` 路径。

### 5.4 SCTLR.A（第三候选，低）

若 SCTLR.A=1 且 env 路径里出现未对齐访问，现象应是数据异常或 abort，而不是静默 bad CRC；但无法完全排除某条路径在 A=1 下产生错误数据。判别成本低（一个 `allow_unaligned()` 调用），列入备用矩阵。

## 6. env 读取路径与两种可观察的失败形态

代码（本仓库 patch 0007 落地后的树，`uboot-src/env/mtd.c`）：

- `env/mtd.c:142` `env_mtd_load()`；`:152` 先 `memalign(ARCH_DMA_MINALIGN, CONFIG_ENV_SIZE)`，**在** `setup_mtd_device()` 之前。
- `env/mtd.c:158` `setup_mtd_device()`：`mtd_probe_devices()` + `get_mtd_device_nm("spi-nand0")`；若失败会打印 `*** Warning - get_mtd_device_nm() failed, ...`（`:24` 附近），**与本次观测到的 bad CRC 不同**，所以设备查询本身成功。
- `env/mtd.c:168-186` 读循环：按 `mtd->writesize` 分块；仅在块边界调用 `mtd_block_isbad()`（`:171`），读失败会打印 `mtd_read() failed`（`:179`）。`mtd_read` 返回 >=0 表示成功（返回值是纠错位数），所以**本次日志说明读调用成功、但数据不对或读到的是被跳过的擦除块**。
- `env/mtd.c:188` `env_import(buf, 1, H_EXTERNAL)`；`env/common.c:443` 内 `:452` 用 `crc32(0, ep->data, ENV_SIZE=0x1FFFC)` 对比存储 CRC，不等则 `:453` `env_set_default("bad CRC", 0)` —— 正是日志里的字符串。
- `env/common.c:603` `env_relocate()`：仅当 `gd->env_valid` 无效时才打印那条 Warning；`env/env.c:192`/`:200` 打印 `Loading Environment from ...` 与 `... OK`。

因此失败形态只有两种：

1. **读到错误字节**：`mtd_read` 成功但缓冲区内容与 flash 不符（瞬时读错、地址相关副作用、缓冲区被覆盖）。
2. **块被判定为坏块**：`mtd_block_isbad(0xC0000)` 为真 → `offset += erasesize` 跳到 0xE0000（该块是全 FF，见 U-逆1 结论）→ CRC 必然失败，打印同样一句话，且不会打印 `mtd_read() failed`。

两种形态用一个调试构建即可区分：在 `env/mtd.c:188` 之前失败时打印 `offset` 与缓冲区前 64 B 的 hexdump + `crc32(buf, 0x1FFFC)`。若 hexdump 全是 FF 则是形态 2；若像被截断/错位的 env 文本则是形态 1。

## 7. 排序假设与置信度

| # | 假设 | 置信度 | 判别方式 |
| --- | --- | --- | --- |
| H1 | 重定位/堆地址平移 160,828 B，使 env 缓冲区落在某个地址敏感路径上（DMA/缓存/tlb/遗留内存） | ~45% | 构建 B：thin + 纯 padding（`.rodata` 约 160 KB），代码与此前完全相同，只把 `mon_len` 拉回 24-patch 大小 |
| H2 | env 前少跑 3 个 initcall（EFI/MMC）改变首次 SPI-NAND 探测与首次 MTD 读的时序，暴露 PIO/ECC 时序边界 | ~30% | 构建 D：thin + 只在 env 前插一段等价延时或重新 `mtd_probe_devices()`；或设备上重复启动看是否间歇 |
| H3 | SCTLR.A=1 未被清，某条路径在 A=1 下产出错误数据 | ~10% | 构建 C：thin + `board_init_f` 里调用 `allow_unaligned()` |
| H4 | 一次性读错（样本只有 1 次 thin 启动） | ~15% | **零构建**：同一 thin 镜像 RAM 链启动 5 次，若任一次 env OK 则倾向 H4 |

注意：若 H4 成立，则 0025 完全无关，回归只是 SPI-NAND 读的偶发问题；这会影响后续「env 写回」设计的稳定性判断，因此设备重复测试价值很高（成本接近零）。

## 8. 给 base-builder 的修改建议（按优先级）

> 2026-11-27 决策更新：本节 A 项（去掉 0025）已由 Lead 撤回，保留 0025；实际采用 C（重试）+ B（诊断打印）合并为一个新补丁，详见 §12。

### A. （已撤回）E4 构建不带 0025

- 具体改动：从 E4 系列中去掉 patch `0025-configs-zxhn-e2631-drop-the-unused-EFI-MMC-FAT-and-standard-boot.patch`，即恢复 `configs/zx279128s_zte_zxhn-e2631_defconfig` 第 36 行的 `# CONFIG_MMC is not set`（不写该行）。保留 0001–0024 + 0026–0029。
- 尺寸预测：494,880 B（24-patch）+ 39,776 B（0026–0029 的增量，由 29-patch 360,624 − 25-patch 320,848 得出）= **534,656 B**，低于 CI 门限 645,120 B（硬上限 653,312 B），余量约 110 KB。
- 前置验证：新镜像必须在设备 RAM 链上确认 `Loading Environment from MTD... OK`，再做 0026 的救援验收；这是 E4 验收前的必检项。
- 风险：若 H1 成立，任何体积变化（包括 +39,776 B）都会再平移堆地址，env 仍可能失败——所以「不带 0025」不能当作根因已解决，只是把已知失败的配置排除掉；设备复验是硬门槛。

### B. 诊断构建（一次构建，钉死 H1/H2/H3 之一）

- B（测 H1）：在当前 thin 代码上仅加约 160 KB 的 `.rodata` padding（例如 `char e2631_pad[0x27400] __attribute__((used)) = {1};`），使 `mon_len` 回到 24-patch 附近。若 env OK → 地址/布局敏感（H1）；若仍失败 → 排除 H1。
- C（测 H3）：在 `board/zte/zxhn-e2631/zxhn-e2631.c` 的 `board_init_f`（或 `board_late_init` 之前）调用 `allow_unaligned()`。
- D（测 H2）：在 `initr_env` 之前插入等价于被删 initcall 的行为（最小者：连续两次 `mtd_probe_devices()` + 一次 `mdelay(50)`），观察是否改变结果。
- 调试打印（任何诊断构建都建议加）：`env/mtd.c:188` 失败分支打印 `offset`、`crc32(buf, 0x1FFFC)`、前 64 B hexdump。

### C. 与根因无关的加固（建议无论结论如何都做，但排在根因之后）

- 在 `env_mtd_load()`（`env/mtd.c:142-199`）里对 `env_import` 失败做最多 3 次重读重试，仍失败才回退默认 env；这样偶发读错（H4）不会直接丢掉全部持久化 env。
- 不在 env 阶段做任何 flash 写（保持 patch 0007 的只读语义；写回仍走 task-59 的 e2631env 设计）。

## 9. 顺带更正：thin 会话里的 0x48000000「可见性异常」是命令地址漏零

`evidence/e2b-session/thin-run2/serial.txt` 第 72–81 行：

```
=> mtd read spi-nand0 0x48000000 0x2300000 0x800
=> md 0x480000 4          ← 少了两位 0，实际查看的是 0x00480000
=> md 0x480020 8
=> crc32 0x480020 0x40
=> iminfo 0x480020
```

第 190–204 行对 0x42000000 也是同一模式（`md 0x420000`、`crc32 0x420020`、`iminfo 0x420020`）。同一份日志的正确地址对照是存在的：`e2631boot` 自己内部从 0x42000000 读 uImage 并校验 header/data CRC 全部通过、随后成功引导内核（第 190、212 行）。

因此 `evidence/e2b-session-20261127.md` §10.5 与 `evidence/e2b-session/thin-run2/README.md` 里记为「0x48000000 可见性异常」的观察**不成立**，应更正为会话脚本的地址笔误。与此不同，22-patch 会话在 `evidence/e2b-session/serial-run1.txt:234-247` 用**正确**地址 0x420020 仍得到 `Wrong Image Type`，那个 F1 现象是另一件事，不在本文范围。

## 10. 未决问题

1. thin 镜像是否只用过一次（单样本）；需要设备重复启动测试（零构建）。
2. 0025 单独回退是否真的恢复 env（构建 A 未做；本机不做编译，走 CI）。
3. 若确认是地址敏感/时序问题，是否存在更小的等价修法（例如给 env 缓冲区固定到一个不随 `mon_len` 变化的地址），需要 B/C/D 结果后再定形态。
4. 该问题与 spi-nand 读的偶发错误是否同一根因（影响 env 写回可靠性评估，见 task-59 设计的前提）。

## 11. 复现

- 产物：`/home/qc233/zte/e2631-t5-artifacts/uboot-defconfig-45988430055/e2631-uboot-45988430055/`（thin）、`/home/qc233/zte/e2631-t5-artifacts/uboot-69-45985501668/e2631-uboot-45985501668/`（24-patch）、`/home/qc233/zte/e2631-t5-artifacts/uboot-e4-46002766353/e2631-uboot-46002766353/`（29-patch E4）。
- 两份 `.config`/`u-boot.map`/`u-boot.bin`/`UBOOT-INFO.txt` 都在上述目录；本次 diff 直接用它们，无需重新构建。
- 反汇编比对脚本思路：`python3` + capstone（`PYTHONPATH=/tmp/pylibs`），链接基址 0x47F00000，`Cs(CS_ARCH_ARM, CS_MODE_ARM)`，对 `u-boot.map` 中的符号取地址与大小，逐函数反汇编并把 `#0x47f...` 立即数抹平后比较。

## 12. 决策更新（2026-11-27，Lead 裁定）：保留 0025，改走重试 + 诊断

**结论：保留 patch 0025。§8-A「E4 构建不带 0025」的建议撤回，不再执行。**

理由是与本文范围无关、但优先级更高的跨构建 F1 相关性（Lead 掌握的证据）：

| 构建 | 0025（MMC OFF 瘦身） | 以太网补丁（0018–0020） | bootm 结果 |
| --- | --- | --- | --- |
| 22-patch（494,208 B） | OFF（MMC ON） | 有 | **失败**：0x42000000 读为全 0，「Wrong Image Type」 |
| 25-patch thin（320,848 B） | **ON** | 有 | **正常**（继续引导内核） |
| 15-patch flash 镜像 | OFF（MMC ON） | 无 | 正常（日常冷启动） |

即：现代系列（有以太网补丁）里 bootm 的成功与 0025 的瘦身同时出现；去掉 0025 有重新引入 F1 的风险，而 F1 破坏的是引导路径本身，比 env 回归更严重。因此接受「保留 0025 + 修复 env 回归」的方案。

**修复形态（由 base-builder 实现为一个新补丁）：**

1. 选项 C（加固）：`env_mtd_load()`（`uboot-src/env/mtd.c:142-199`）在 `env_import` 失败时，把整个读取循环重试最多 3 次，仍失败才 `env_set_default` 回退默认 env。保持 env 阶段只读，不做任何 flash 写。
2. 选项 B（诊断）：最终失败时打印实际读取偏移 `offset`、`crc32(buf, 0x1FFFC)` 与缓冲区前 64 B 的 hexdump（插入点在 `env/mtd.c:188` 的 `env_import` 之前/失败分支）。

**诊断判读（一次设备启动即可落到 H1–H4 之一）：**

- hexdump 全 FF → 坏块跳过路径：`mtd_block_isbad(0xC0000)` 为真，`offset` 跳到 0xE0000 的擦除块（§6 形态 2）。
- hexdump 是错位/乱码的 env 文本或非 FF 垃圾 → 读到错误字节（§6 形态 1），结合重试结果判断是否 H1/H2。
- 重试后 env 读取成功 → H4 成立（偶发读错），重试补丁本身就是修复。
- 重试 3 次仍失败且字节形态稳定 → 指向 H1（地址/布局）或 H2（时序），用 §8-B 的判别构建（B/C/D）收口；届时再定 H1/H2/H3 的具体修法，**仍然保留 0025**。

**会话级第二机会（零额外断电）：** 设备脚本设计为——首轮 RAM 启动若 env 失败，驱动重启回 flash 提示符并再加载同一镜像一次，才判定失败。若第二次 env 正常，则 H4 得到确认，重试补丁的价值同时被验证。

**当前状态：** 本文证据已冻结；重试+诊断补丁的编码与设备验证由 base-builder / verify-docs 执行，本文只记录决策与判读口径。task-77 卡按 Lead 指示保持 completed，不再做看板动作。
