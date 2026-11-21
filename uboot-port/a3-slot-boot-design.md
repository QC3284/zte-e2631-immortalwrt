# A3 设计：自定义 U-Boot 的槽位感知启动（只读）

状态：随 task-51 的 patch 0006/0007 一并交付。依据：
[evidence/p2-uboot-research-20261121.md](../evidence/p2-uboot-research-20261121.md)、
[evidence/chip-level-layout-20261120.md](../evidence/chip-level-layout-20261120.md)、
[evidence/b1-env-design-20261121.md](../evidence/b1-env-design-20261121.md)、
[evidence/b1-env-current-20261121.txt](../evidence/b1-env-current-20261121.txt)，
以及内核树 fork（`4b09208b`）的 `target/linux/zx279128/files/drivers/mtd/parsers/`
（`zx279128s-slotpart.c`/`zx279128s-slotpart-core.c`，槽位解析的权威实现）与
[tools/lib/mtd0.mjs](../tools/lib/mtd0.mjs)（mtd0 地图）。本文不发明偏移：所有常量都来自上述材料。

## 1. 目标与边界

- **目标**：在自定义 U-Boot 里复刻 cspboot 的槽位选择（magic + CRC1 + serial），把胜出槽位的
  legacy uImage 内核读入 RAM，`bootm` 启动。同一份二进制既可用于 A1/A2 的 RAM 链
  （RAM 链：厂商 U-Boot `tftp 0x47F00000` + `go 0x47F00000`；task-55 起与 secondboot 的固化入口 `0x47F00000` 是同一个链接地址）。
- **只读**：A3 不写 flash、不 `saveenv`、不碰 mtd0，也不执行任何 erase/program。env 只从厂商块
  `0xC0000` 读入（失败回退默认 env）；env 的持久化策略属于 B1（需用户批准）。
- **不做**：写 mtd0/写槽位（刷写阶段）、网络、DMA/中断、根文件系统槽位选择（内核 slotpart 的职责）、
  DTB 提取（内核用 append-dtb）。

## 2. 单二进制、两条进入路径

| 路径 | 进入方式 | TEXT_BASE | 说明 |
| --- | --- | --- | --- |
| RAM 链（A1/A2/A3 验收） | 厂商 U-Boot `tftp 0x47F00000` + `go 0x47F00000` | `0x47F00000` | 断电即恢复，零砖风险 |
| 固化入口（后续，需用户批准） | secondboot 装到 `0x47F00000` 后 `blx` | `0x47F00000`（task-55 起与 RAM 链一致） | A3 代码不依赖进入地址；非 PIE，入口必须等于链接地址 |

两种路径共享同一份 `u-boot.bin`，差别只是 TEXT_BASE（入口）与谁把镜像放进 RAM。A3 的槽位代码
只依赖 secondboot 已完成的 DRAM/UART/SPI-NAND 初始化，不读进入地址，所以 TEXT_BASE 变化不影响逻辑。
`bootcmd` 在两条路径上一致：`board_late_init` 在 RAM 内覆盖 env 的 `bootcmd`，autoboot 随后调用
`e2631boot`。

## 3. 槽位格式与选择语义

槽位几何（[chip-level-layout 证据](../evidence/chip-level-layout-20261120.md)）：

| 项 | 值 |
| --- | --- |
| slot0 | `0x00700000` |
| slot1 | `0x02300000` |
| 每槽跨度 | `0x01C00000`（28 MiB） |
| 擦除块 | `0x20000`（128 KiB）；版本头一定落在擦除块边界 |
| 我们的版本头 | slot + `0x1500000` |
| 厂商 slot0 版本头 | slot + `0x1560000`（绝对 `0x1C60000`） |
| 内核 uImage | slot + `0x20`，load=entry `0x40008000`，comp=none |

版本头 512 字节，本阶段用到的字段（`zx279128s-slotpart-core.c`）：

| 偏移 | 含义 |
| --- | --- |
| `0x10` | 版本字符串，32 字节 |
| `0x34` | 内核大小（仅记录） |
| `0xa4` | CRC1：`crc32(0, hdr, 0xa4)`（反射 IEEE `0xEDB88320`，与 U-Boot `crc32()` 同算法） |
| `0xf4` | 内层 magic：`33 33 33 33 66 66 66 66 99 99 99 99 cc cc cc cc` |
| `0x1f0` | 槽位起始标记（本阶段不用） |
| `0x1f4` | serial（升级序号，u32 LE） |
| `0x1fc` | CRC2（覆盖 serial；cspboot 不校验，A3 也不校验） |

**选择规则（与 cspboot 逐字一致）**：在槽内每 128 KiB 找内层 magic、只校验 CRC1；
`slot0.serial < slot1.serial` 或 `slot0.serial == 0` → slot1，否则 slot0；相等 → slot0；
单槽有效 → 该槽；两槽都无效 → 不启动；**没有自动回退**。

**与内核 patch 033 的差别**：两者都用 magic+CRC1 判有效；双有效时内核 `decide()` 取
`serial1 > serial0 ? 1 : 0`。唯一实质差异是一个边角：`slot0.serial == 0` 且 slot1 也有效时，
cspboot 选 slot1，内核 `decide()` 选 slot0（两 serial 都为 0 时）。本机实测 serial 为 slot0=7、
slot1=11（均非 0），该边角不可达；A3 按 cspboot 实现，因为启动目标应与厂商链一致。若将来刷写链
会写出 serial 0，需要再对齐。**这不是需要停工的语义分歧，记录于此。**

**为什么扫描**：厂商槽头在 `+0x1560000`，我们在 `+0x1500000`，没有共同的固定 delta；cspboot
本身也是全槽扫描。每槽 448 个擦除块，A3 读两个头就停（第一个有效头即胜出），预计 <2 s；
真机记录实测值。若将来嫌慢，可先试两个已知 delta 再回退全扫描。

## 4. env 策略（只读）

- 目标块：绝对偏移 `0xC0000`，128 KiB（`0xC0000`–`0xDFFFF`），布局
  `[u32 LE CRC32][0x1FFFC data]`。这与 U-Boot 的 `env_t`/`ENV_SIZE` 逐字节一致
  （`CONFIG_ENV_SIZE` 0x20000 时 `ENV_SIZE = 0x1FFFC`），CRC 实测 `0xAFFCEC3E`。
- Kconfig：`ENV_IS_IN_MTD=y`、`ENV_MTD_DEV` 为 `spi-nand0`、`ENV_OFFSET=0xc0000`
  （`0xC0000 / 0x20000 = 6`，满足擦除块对齐）、`ENV_SIZE=0x20000`。
- **只读保证**：关闭 `CMD_SAVEENV`（默认 y），A3 不提供任何写 env 的命令；env 只在 RAM 内被
  `board_late_init` 覆盖 `bootcmd`。
- 载入失败（CRC 坏/设备缺失）：env 驱动打印失败并回退默认 env，`CONFIG_BOOTCOMMAND` 为
  `e2631boot`，启动路径不依赖已载入 env 的 `bootcmd` 内容。

### 4.1 `<NULL>` 名称的真相（task-53 更正）

C1a 真机日志是 `Loading Environment from <NULL>... OK`，当时被读成“env-mtd 未生效”。读源码可知：
`env_load()` 只在其 `drv->load()` 返回 0 时打印 `OK`（`env/env.c:172-230`），而 `ENV_NAME()` 在
`CONFIG_CMD_SAVEENV` 关闭时被定义成空（`include/env_internal.h` 原第 176-184 行），于是所有 env
驱动的 `.name` 都是 NULL，`%s` 打印出 `<NULL>`。因此 **MTD env 实际上载入成功了**
（`env/mtd.c:142-199` 的 `env_mtd_load()` 返回 0 才会走到 OK），C1a 的“未生效”是名称缺失造成的
误判；也不需要改 probe/init 顺序。patch 0009 让 `.name` 无条件定义，日志变为
`Loading Environment from MTD... OK`；它与启动逻辑无关，可独立回退。运行期复核见 §8 的 `printenv`
厂商值检查。
- **上游健壮性缺陷与修复**：`env/mtd.c` 的 `env_mtd_load()` 在 `setup_mtd_device()` 失败时 `goto out`，
  而 `out` 处无条件 `put_mtd_device(mtd_env)`；此时 `mtd_env` 未初始化，`put_mtd_device()` 不做 NULL
  检查并直接解引用，SPI-NAND 探测失败会在提示符之前 panic。patch 0007 修两行
  （`mtd_env = NULL` 初始化 + `if (mtd_env)`），否则“只读 env”会把本来可调试的失败变成硬崩。
- `ENV_IS_NOWHERE`：`ENV_IS_DEFAULT` 只在没有任何 `ENV_IS_IN_*` 时 select NOWHERE；启用 MTD 后它
  自动消失（savedefconfig 确认）。
- `bootdelay`：沿用厂商 env 的 3 s；B1 才决定改 0 + 旁路变量。

## 5. bootcmd 序列

1. `board_late_init`（`CONFIG_BOARD_LATE_INIT=y`，在 `initr_env` 之后执行）→
   `env_set("bootcmd", "e2631boot")`，仅 RAM；载入的厂商 `bootcmd` 属于厂商 U-Boot，不改 flash。
2. autoboot 等 `bootdelay`（3 s）→ 执行 env 的 `bootcmd` → `e2631boot`。
3. `e2631boot`：`mtd_probe_devices()` → `get_mtd_device_nm("spi-nand0")` → 扫 slot0/slot1 →
   按 §3 选槽 → 读 slot+`0x20` 的 uImage 头 → 校验 magic/type/os/comp/hcrc/size →
   把 marker+image 读到 `CONFIG_SYS_LOAD_ADDR=0x42000000` → 校验 dcrc → 设 `bootargs` →
   `bootm 0x42000020`。
4. `bootargs` 与内核 `CONFIG_CMDLINE` 相同：
   `console=ttyAMA0,115200n8 earlycon root=/dev/mtdblock7 rootfstype=squashfs ro rootwait`
   （内核 `CONFIG_CMDLINE_FORCE=y`，实际以后者为准，设 env 只为与厂商/cspboot 链一致）。
5. `bootm` 走 ATAGS（`CONFIG_SUPPORT_PASSING_ATAGS=y`）；内核 `CONFIG_ARM_APPENDED_DTB=y`，
   r2 不是 FDT 时使用追加在 zImage 后的 DTB，与厂商 bootm 当前启动本设备的方式一致。
6. 只读子命令：`e2631boot info`（只打印槽头与选择）、`e2631boot load`（含 uImage 校验与载入，
   不 boot）、`e2631boot`（= boot）。

### 5.1 ATAGS 缓冲区（patch 0008，C1a 修复）

`bootm` 在跳转内核前把 ARM ATAGS 写到 `bd->bi_boot_params`（`arch/arm/lib/bootm.c:47`、`:336`）。
本板 `bd_info` 在 `reserve_board()` 中被清零，且配置里没有 `CONFIG_SYS_MALLOC_BOOTPARAMS`，所以
在此之前该指针是无效值；C1a 干跑就在第二个 tag（`ATAG_MEM`）写入时 data abort
（`pc 0x4300178c`、`r1=0x967fc480`）。patch 0008 在 `board_late_init()`（早于 autoboot，因此早于
`bootm`）设置 `gd->bd->bi_boot_params = CFG_SYS_SDRAM_BASE + 0x100`（= `0x40000100`），并用两条
`static_assert` 保证 `ATAGS_ADDR > CFG_SYS_SDRAM_BASE` 且 `ATAGS_ADDR + 0x100 <= 0x40008000`
（内核 load 地址）。当前配置下 ATAGS 只含 CORE、一个 MEM 与 END 三个 tag，共 44 字节，0x100 字节
窗口足够；该窗口不与内核、uImage staging（0x42000000）、重定位 U-Boot（0x4ff…）重叠。内核用
append-dtb（`ARM_APPENDED_DTB=y`、`ATAG_DTB_COMPAT` 关、`CMDLINE_FORCE=y`），不消费这些 ATAGS，
但 `bootm` 必须先写完它们才能进入内核。

## 6. 大小预算

A2 镜像 `u-boot.bin` 为 444152 B；A3 + task-53（patch 0006–0009）CI 实测 448096 B（上限
653312 = `0x9F800`，余量 205216 B ≈ 200 KiB）。patch 0006 新增约 250 行 C，0007 约 3 行，
0008 约 20 行（ATAGS 赋值 + 两条 `static_assert`，只加 24 B），0009 约 5 行；CI 仍按
`<= 653312` 卡住。

## 7. 风险与回退

- **env 在提示符之前载入**：`initr_env` 早于 `board_late_init` 与命令提示符，SPI-NAND 探测异常会在
  提示符前暴露。已修 `env_mtd_load()` 的未初始化指针（§4）；若仍怀疑 env 路径，只回退 0007 重建即可
  （0006 的启动逻辑不依赖 env）。
- **全槽扫描成本**：2×448 块，预计 <2 s；A3 真机记录实测值。
- **ATAGS / append-dtb**：0008 已修 C1a 的 `bi_boot_params` data abort；若内核在 “FDT and ATAGS
  support not compiled in” 处 panic，说明 `SUPPORT_PASSING_ATAGS` 丢了；若内核不认追加 DTB，回退
  方案是在 uImage 数据段里找 `0xD00DFEED` 的 FDT 交给 bootm（当前不做，因为厂商链就是 ATAGS 方式）。
  重跑 C1a 时若在 `boot_prep_linux` 再次 abort，先确认 0008 是否在镜像里、`bi_boot_params` 是否被
  后续代码改写。
- **活动槽位不是 slot1 时的 rootfs**：cmdline 的 `root=/dev/mtdblock7` 指向 DTS 固定分区
  （即 slot1 根文件系统）。若将来最高 serial 落在 slot0，A3 会把 slot0 的内核与 slot1 的根走在一起。
  当前实测 slot1 serial 11 > slot0 7，A3 验收只覆盖现状；“按活动槽位切换根文件系统”属于后续阶段
  （与内核 slotpart/升级链一起）。
- **无有效槽位**：`e2631boot` 打印原因并失败返回，不会掉回厂商 `bootcmd`（env 已被覆盖）。
- 不校验版本头 CRC2、不校验版本字符串内容（与 cspboot 同）。

## 8. 验收（只读）

A3 真机会话（需用户批准；只读、不写 flash）建议顺序：

1. `e2631boot info`：应显示 slot0（serial 7、厂商版）与 slot1（serial 11、ImmortalWrt v1.10.0）
   的版本头偏移，结论 `cspboot would boot slot1`。
2. `e2631boot load`：应显示 uImage 名 `ARM ImmortalWrt Linux-6.18.60`、load/entry `0x40008000`、
   大小 3491850、hcrc/dcrc OK，且**不 boot**。
3. 与 A2 的 `mtd read spi-nand0 ...` 结果对照 slot1 版本头字节（同一区域两次读取一致）。
4. `e2631boot` 完整走 `bootm`（C1a 重跑必需）：`Loading Kernel Image to 40008000` 之后不得再出现
   data abort，串口应继续出现 ImmortalWrt 内核启动日志。
5. env 证据：启动日志应为 `Loading Environment from MTD... OK`（0009）；`printenv` 应显示厂商值
   （`bootdelay=3`、`bootcmd`、`ethaddr`/`ipaddr`/`memsize` 等不在编译期默认 env 中的值），而当前
   生效的 `bootcmd` 已被 RAM 内改成 `e2631boot`。
6. **禁止** `mtd write`/`mtd erase`/`nand write`/`saveenv`（`CMD_SAVEENV` 已编掉）。

## 9. 变更记录与关联

- 2026-11-21（task-51）：patch 0006（槽位解析 + `e2631boot` + ATAGS/bootcmd）、patch 0007
  （env-mtd 只读 + `env/mtd.c` 健壮性修复）；本设计说明首版。
- 2026-11-21（task-53）：patch 0008（`board_late_init()` 设置 `bi_boot_params` + 编译期边界断言，
  修 C1a 的 `boot_prep_linux` data abort）与 patch 0009（`ENV_NAME` 无条件定义，env 日志名称恢复）；
  新增 §4.1 `<NULL>` 更正与 §5.1 ATAGS 缓冲区。
- 相关：[README.md](README.md) §3/§5、[a2-spi-nand-design.md](a2-spi-nand-design.md)（SPI-NAND 读路径）、
  [evidence/chip-level-layout-20261120.md](../evidence/chip-level-layout-20261120.md)（槽位实测内容）、
  [evidence/b1-env-design-20261121.md](../evidence/b1-env-design-20261121.md)（env 块取证）。
