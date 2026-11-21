# C1b 刷写前准备：厂商 U-Boot RAM 载荷与刷后救援路径

> 任务：task-54（P2-C1b 预刷写准备；纯只读/文档，无设备操作、无 flash 写入）。
> 日期：2026-11-21。关联：`docs/救砖手册-2026-11-15.md` §6.7（本次新增）、`uboot-port/README.md` §7（C1b 刷写阶段）、
> `evidence/p2-uboot-research-20261121.md`、`evidence/chip-level-layout-20261120.md`、`evidence/b1-env-session-20261121.md`。
> 输出：`vendor-uboot-ram.bin`（426,048 B，随本文件入库）、`vendor-uboot-region-0x20000-0xC0000.bin`（655,360 B，本机文件，不入库）、手册 §6.7。

## 1. 结论摘要

1. **厂商 U-Boot RAM 载荷已抽出并入库**：`vendor-uboot-ram.bin` = mtd0 的 `0x20800..0x88840`，426,048 B，
   sha256 `a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30`。来源是钉死的 11-15 mtd0 dump；
   U-Boot 区自 11-15 未被写过（B1 只写过 env 区，§3.1 有证据），因此该载荷与当前设备一致。
2. **载荷是位置相关的**：运行时基址 `0x47F00000`，映射 `vaddr = 0x47F00000 + (file_off - 0x20800)`；
   必须装到 `0x47F00000` 再 `go`，装到其它地址会跑飞（§2.2）。
3. **我们的 U-Boot 具备串口装载器**：`loadx`（XMODEM）/`loady`（YMODEM）/`loadb`（Kermit）都在，
   因为 U-Boot 把这三个命令编在 `#if defined(CONFIG_CMD_LOADB)` 里，而我们的 .config 是 `CONFIG_CMD_LOADB=y`（§4.1）。
   网络（tftp）虽然编进去了，但**没有 ZX279128S 以太网驱动**，刷后控制台不能靠 tftp（§4.2）。
4. **刷后救援有两条不同层级的路**：
   - **A. U-Boot 能起、系统起不来**：在 `=> ` 控制台用 `loadx` + `mtd write` 把 U-Boot 区写回（首选，命令齐备），
     或 `loadx` 厂商载荷 + `go 0x47F00000` 临时回厂商控制台；详见 §5。
   - **B. U-Boot 映像本身不启动（Jump 后无 banner）**：secondboot 没有交互控制台，只剩编程器（§6.4/§6.6）。
     这是 C1b 的**真砖风险**，必须在刷前接受/演练（§7）。
5. **厂商帮助里宣传的 `nand write.uboot` 不能当作已验证的回滚手段**：help 文本确实存在（§5.3），
   但对整份厂商 U-Boot 载荷做交叉引用扫描，**找不到该子命令的派发代码**（§5.3 的静态证据）；只能列为"待真机演练"。
6. **§6.6 的芯片级写回表仍然适用**：C1b 不改变任何物理布局/分区偏移，只改变 mtd0 内 `0x20000..0xC0000` 的 U-Boot 区内容；
   env 区（`0xC0000..0xDFFFF`）不动（§8）。

## 2. 产物、哈希与提取命令

来源 dump（钉死）：

| 项 | 值 |
|---|---|
| 文件 | `/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin` |
| 大小 | 1,048,576 B（1 MiB） |
| sha256 | `de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f` |
| 与程序员 dump 的关系 | v2-ECC 前 1 MiB 与它逐字节相同（`evidence/chip-level-layout-20261120.md`） |
| 与当前设备的关系 | 当前 mtd0 = `887a7f6c…0fa9f`（B1 saveenv 改了 env 区）；`0x20000..0xC0000` 的 U-Boot 区未变（`evidence/b1-env-session-20261121.md`） |

产物 1（**入库**，救援输入）：`evidence/p2-oob/vendor-uboot-ram.bin`

```bash
# 提取命令（在 kit 仓库根目录执行；需要上面的 mtd0 dump）
dd if=/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin \
   of=evidence/p2-oob/vendor-uboot-ram.bin bs=1 \
   skip=$((0x20800)) count=$((0x88840-0x20800)) status=none
sha256sum evidence/p2-oob/vendor-uboot-ram.bin
# 期望：a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30  (426,048 B)
```

产物 2（**本机文件、不入库**，mtd-write 回滚用）：`evidence/p2-oob/vendor-uboot-region-0x20000-0xC0000.bin`

```bash
dd if=/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin \
   of=evidence/p2-oob/vendor-uboot-region-0x20000-0xC0000.bin bs=1 \
   skip=$((0x20000)) count=$((0xC0000-0x20000)) status=none
sha256sum evidence/p2-oob/vendor-uboot-region-0x20000-0xC0000.bin
# 期望：3b49d4fb50875ddf635704875c9b67878a643bfd993a6b5c9aebb75f22e32222  (655,360 B)
```

> 为什么不入库产物 2：它是从 mtd0 备份截出来的"整段 U-Boot 区"，C1b 刷写前本来就要从**当前设备**重新读一份
> mtd0 备份（§7 第 1 条），到时候用同一条 dd 命令生成即可；它的 sha256 只是用来核对"新旧 region 一致"。
> 产物 1 入库的原因：它是刷后救命的输入，426 KB 很便宜，且必须随仓库可复现（`*.bin` 的 .gitignore 例外由
> `git add -f` 完成，本文件即为例外理由的记录）。

### 2.1 子块哈希（定位/替换用）

| 子块 | 文件范围（mtd0） | 大小 | sha256 |
|---|---|---|---|
| U-Boot 头块 | `0x20000..0x20800` | 2,048 B | `19a9d54614e9d5cdfb7573495609448cdf1a740e470fbebcac5783c8e9b93510` |
| U-Boot 载荷 | `0x20800..0x88800` | 425,984 B（0x68000） | `fbff1ebf35244d7bd9e011a969737acc77322ea750735a7ce9be6f8ea868e806` |
| 64 B 尾标记 | `0x88800..0x88840` | 64 B | `c0893058409e1d6245e124dacd9f70b55458f92342cbd9639091348c5f36edbc` |
| 整个 U-Boot 区（头块+载荷+尾标记+FF 填充） | `0x20000..0xC0000` | 655,360 B（0xA0000） | `3b49d4fb50875ddf635704875c9b67878a643bfd993a6b5c9aebb75f22e32222` |
| RAM 载荷（载荷+尾标记，即产物 1） | `0x20800..0x88840` | 426,048 B（0x68040） | `a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30` |

布局（与 `evidence/uboot-re-20261115.md`、`evidence/p2-c-tools-20261121.md` 一致）：
头块 2,048 B（+0x10 魔法 `128s`，+0x14 长度 0x68000）→ 载荷 425,984 B（运行时基址 `0x47F00000`）→
64 B 尾标记（内容以 `AAAAAAAA555555554444444499999999` 开头，含 `V1.0.0` 与 `2023-08-28 19:11:52`）→
FF 填充到 `0xC0000` → env 区 `0xC0000..0xDFFFF`。产物 1 尾部 64 B 的 hex 为
`aaaaaaaa55555555444444449999999956312e302e30000000000000000000ff323032332d30382d32382031393a31313a353200408808000000000000001000`。

### 2.2 载荷头部（位置相关证据）

```text
00000000: 1400 00ea 14f0 9fe5 14f0 9fe5 14f0 9fe5   ; ARM 向量表：b reset(+0x58) + 7 个 ldr pc
00000010: 14f0 9fe5 14f0 9fe5 14f0 9fe5 14f0 9fe5
00000020: 8002 f047 e002 f047 4003 f047 a003 f047   ; 0x47f00280/2e0/340/3a0 …
00000030: 0004 f047 6004 f047 c004 f047 7856 3412   ; … /400/460/4c0 + 0x12345678
```

- 第二行起的字是绝对地址（`0x47f00280` 等），不是偏移；所以**只能把 RAM 载荷放到 `0x47F00000` 再跑**。
  这与 `uboot-port/README.md` §6"入口必须等于链接地址（非 PIE）"是同一条约束在厂商镜像上的体现。

## 3. 输入有效性

### 3.1 为什么 11-15 dump 的 U-Boot 区仍等于当前设备

- B1 env 会话（2026-11-21 16:47）唯一一次 `saveenv` 只改了 env 区：全 mtd0 sha256 从 `de4ea5bd…` 变成 `887a7f6c…`，
  差 462 B 全部落在 `0xC0000..0xC02AA`（`evidence/b1-env-session-20261121.md`；TEAM-NOTES "B1 env 会话 GREEN"）。
- 因此 `0x20000..0xC0000`（U-Boot 区）与 11-15 dump 逐字节相同，产物 1/2 对当前设备有效。

### 3.2 为什么不用 v2 程序员 dump 重新抽

v2-ECC 的前 1 MiB 与 11-15 mtd0 相同（`evidence/chip-level-layout-20261120.md`），抽出来哈希也应当一致；
11-15 dump 是本机文件、路径稳定，故以它为准。

## 4. 刷后控制台的装载通道（为什么是 loadx，不是 tftp）

### 4.1 loadx 存在的证明（不是记忆）

- 钉死的 U-Boot 源 `c1958b5f6cce03956d309ce422b5d9f819955d4a` 的 `cmd/load.c`：
  `#if defined(CONFIG_CMD_LOADB)#` 从 :1158 开始，:1167 的 `U_BOOT_CMD(loadx, 3, 0, do_load_serial_bin, …)`、
  :1175 的 `U_BOOT_CMD(loady, …)` 都在这个条件块内；`cmd/Kconfig` :1430 的 `config CMD_LOADB` 默认 y，
  :1469 只有 `CMD_LOADXY_TIMEOUT`，**没有独立的 CMD_LOADX/CMD_LOADY 符号**（所以 .config 里看不到它们是正常的）。
- 我们的 C1a 修复产物 `.config`（`/home/qc233/zte/e2631-t5-artifacts/uboot-c1a-fix-44892376502/.config`）：
  `CONFIG_CMD_LOADB=y`、`CONFIG_CMD_LOADS=y`。
- 同一产物 `u-boot.bin`（448,096 B，sha256 `2c90fc558dd8e35f50c887040cd25e00f98325e13e35422de1bc52d056de3eb3`）里
  存在 help 字符串 `load binary file over serial line (xmodem mode)`（file offset 0x5620b）与运行时提示
  `## Ready for binary (xmodem) download to 0x%08lX at %d bps...`（file offset 0x56082）。
- 结论：刷后我们的控制台可以 `loadx <addr>` 收 XMODEM；协议实现是 U-Boot 的 xyzModem（与厂商 `xmodem` 同族，
  但 **block size 是否接受 1024 B 需真机演练**；不行就用 128 B 块，见 §4.4）。

### 4.2 tftp 为什么不行

产物 `.config` 有 `CONFIG_CMD_NET=y / CONFIG_CMD_TFTPBOOT=y / CONFIG_NET=y / CONFIG_DM_ETH=y`，
但**没有任何 ZX279128S 以太网驱动实例**（`.config` 无对应驱动选项；当前 U-Boot 树也只移植了 SPI/UART/timer），
所以 `tftp` 编进去了却找不到可用网卡。刷后不要指望 tftp；串口是唯一装载通道。

### 4.3 我们的控制台里可用于救援的命令（产物证据）

`.config`：`CONFIG_CMD_MTD=y / CONFIG_MTD=y / CONFIG_DM_MTD=y / CONFIG_MTD_SPI_NAND=y / CONFIG_MTD_PARTITIONS=y`、
`CONFIG_CMD_BOOTM=y / CONFIG_CMD_GO=y / CONFIG_CMD_MEMTEST=y / CONFIG_CMD_MEMORY=y / CONFIG_CMD_CRC32=y`。
binary 里的 help 行：

```text
mtd read[.raw][.oob][.benchmark]                <name> <addr> [<off> [<size>]]
mtd write[.raw][.oob][.dontskipff][.benchmark]  <name> <addr> [<off> [<size>]]
mtd erase[.dontskipbad]                         <name>        [<off> [<size>]]
```

另：`e2631boot`（槽位选择命令）、`bootm`、`go`、`memtest`、`printenv`、`loadb/loads/loadx/loady`；
**没有** `saveenv`（`CONFIG_CMD_SAVEENV` 关闭，env 只读）；`reset` 不工作（只打印 "no reset controller, power-cycle the board"）；
提示符是 `=> `（`.config` 的 `CONFIG_SYS_PROMPT="=> "`），autoboot 3 s（`CONFIG_BOOTDELAY=3`、`CONFIG_AUTOBOOT=y`）。

### 4.4 主机侧发送器

- 本机 **没有** `sx/lsz`（lrzsz 未安装）；有 `picocom`、`minicom`、`socat`、python3 + pyserial 3.5。
- C1a 已跑通的发送器是串口 hub 的 `xmodem` op（1 KiB 块；见 `evidence/c1a-bootm/tool-c1a_bootm.py` 里
  `ctl_call({"op": "xmodem", "path": ..., "block_size": 1024, "command": "xmodem 0x43000000"})`）。
  刷后要把 command 换成 `loadx 0x47F00000`/`loadx 0x42000000`，并先做块大小/握手实测。
- 备选：minicom 的 xmodem 发送；或写一个 ~50 行 pyserial XMODEM-CRC 发送器（不装新包）。
  **本任务不写发送器代码**（属于 C1b-0/C1b 会话的演练项，见 §7 第 3/4 条）。

## 5. 刷后救援路径

### 5.1 A 层：我们的 U-Boot 能起（banner/`=>` 可见）

进入：上电 → secondboot 日志（`Boot SPI NAND` … `Jump`，不变）→ 我们的 U-Boot banner →
`Hit any key to stop autoboot: 3` 时发任意键 → `=> `。**没有** 厂商的 `*** Press 1 …***`，**没有** 厂商控制台密码
（密码只属于厂商 U-Boot；见 `docs/救砖手册-2026-11-15.md` §6.2）。

A1（首选）**mtd write 回滚 U-Boot 区**：

1. 用 `vendor-uboot-region-0x20000-0xC0000.bin`（655,360 B）或从当前 mtd0 备份截出的同段；
2. `loadx 0x42000000`（把 0x42000000 作暂存，避开其他区域），收到 655,360 B；
3. `mtd write spi-nand0 0x42000000 0x20000 0xA0000`（设备名 `spi-nand0` 来自 patch 0007 的 `ENV_MTD_DEV`；
   mtd write 走 MTD 层、由 SPI-NAND 驱动带 ECC 写；默认跳过空页，FF 填充页不写也安全）；
4. `mtd read spi-nand0 0x43000000 0x20000 0xA0000`，用 `cmp 0x42000000 0x43000000 0xA0000`（或 `crc32`）回读校验；
5. 断电重上（`reset` 是 no-op），应回到厂商 U-Boot 链。

**未验证点**：这条路径的命令语法/配置已静态验证，但"用本 U-Boot 写 mtd0 后 secondboot 仍能读回"没有真机演练；
写的过程中掉电是新增风险。执行前必须完成 §7 的写路径演练（至少在未用区做一次同路径写/读/校验），并由用户批准。

A2 **临时回厂商控制台（不写 flash）**：

1. `loadx 0x47F00000` 收 `vendor-uboot-ram.bin`（426,048 B；必须 0x47F00000，§2.2）；
2. `go 0x47F00000`；3 s 内按 `1` 进厂商 boot-mode 控制台（密码同 §6.2，实测 `5cE080@fyBD` 可用）；
3. 在厂商控制台里再做诊断/回滚（见 A3）。

**未验证点**：这是 C1a 的反方向（C1a 是从厂商控制台 `go` 我们的 U-Boot；这里是我们的 U-Boot `go` 厂商 U-Boot）。
机制上等价于 secondboot 装载厂商 U-Boot 后的状态（厂商会自行重定位/初始化），但**没有演练过**，必须真机验证一次。

A3 **厂商侧回滚 `nand write.uboot`**：见 §5.3——帮助文本有、派发代码未证实，不列为可用手段。

A4 系统槽问题（不是 U-Boot 问题）：`e2631boot` 会打印选槽理由，可手动 `e2631boot` 重试；
槽位/内核问题走手册 §4/§5 的既有路径（RAM 内核、切槽等）。U-Boot 区回滚与槽位回滚是两件事。

### 5.2 B 层：U-Boot 映像本身不启动（最坏情况）

secondboot 没有交互控制台：`Jump` 之后如果没有我们（或厂商）的 banner，串口就只剩 secondboot 的几行日志，
没有任何输入通道。此时**只剩编程器**（`docs/救砖手册-2026-11-15.md` §6.4/§6.6，回写未验证）。
C1b 的刷前验收必须明确接受这个残余风险，并尽量用 §7 的 RAM 链演练把"映像内容/入口"风险提前消掉。

### 5.3 nand write.uboot：帮助文本证据 vs 静态代码证据

厂商 U-Boot 帮助文本（mtd0 file 0x6173f / vaddr `0x47f40f3f`）：

```text
nand write.uboot - addr off size
    write uboot to nand with 4-bit-ecc, compatible with bootrom.
```

（详细解释串在 file 0x61764 / vaddr `0x47f40f64`；语法即 `nand write.uboot <addr> <off> <size>`。）

但在厂商 U-Boot 载荷（`vendor-uboot-ram.bin`，基址 0x47F00000）上：

- `nand` 命令表项在 payload off `0x5f164`：name=`nand`、maxargs=16、repeatable=1、handler=`0x47f0761c`、
  usage=`NAND sub-system`、help=`0x47f40d9c`；
- 反汇编 handler（0x47f0761c 起）的派发只比较 `info/device/erase/read/write/dump/markbad/biterr` 与后缀
  `.raw/.oob/.jffs2/.e/.i/.spread/.part/.chip`，未知后缀打印 `Unknown nand command suffix '%s'.`；
- 对整份载荷做绝对指针扫描：**没有任何字指向** `write.uboot`（0x47f40f44）、`.uboot`（0x47f40f49）、
  `uboot`（0x47f40f4a）、help 串（0x47f40f64）或 `0x47f31935` 的 `uboot`；PC 相对（ADR/`movw`+`movt`）扫描也没有命中；
- 因此：**帮助文本存在，但静态证据找不到该子命令的派发路径**。它可能是厂商帮助串的残留，或派发用了尚未识别的
  间接方式（该 U-Boot 2013.04 的代码变体）。在真机演练证明之前，**不得把它写成可用回滚手段**。

## 6. 刷后世界与刷前世界的差异（操作者视角）

| 现象 | 刷前（厂商 U-Boot） | 刷后（我们的 U-Boot） |
|---|---|---|
| BootROM/secondboot 日志 | `Boot SPI NAND` / `start read bootheader` / `backup header!!` / `non secure boot` / `Jump` | **不变**（secondboot 不动） |
| banner | `U-Boot 2013.04 …` | `U-Boot 2027.01-rc2-g…`（CI 构建 id） |
| 3 s 提示 | `*** Press 1 means entering boot mode***` | `Hit any key to stop autoboot: 3` |
| 控制台密码 | 有（§6.2） | **没有**（直接 `=>`） |
| 提示符 | 厂商提示符 | `=> ` |
| 启动决策 | 厂商 cspboot/upgrade 链 | `e2631boot`：扫 slot0/slot1 版本头（magic+CRC1），serial 大者胜，读 `slot+0x20` 的 uImage → `bootm 0x42000020` |
| 厂商命令（cspboot/cspstart/cspnand/cspnor/mtddebug/upgrade/nand write.uboot） | 有 | **没有** |
| 我们的命令（mtd read/write/erase、bootm、go、memtest、loadb/loads/loadx/loady、printenv、e2631boot） | 没有 | 有 |
| env | 厂商块（0xC0000）可 `saveenv` | 同一块**只读**（`CONFIG_CMD_SAVEENV` 关闭；启动期 `bootcmd=e2631boot` 只写 RAM） |
| 复位 | 厂商 `reset` 有效 | `reset` 打印 "no reset controller, power-cycle the board"；只能断电/重上电 |
| 网络 | 厂商 U-Boot 有以太网（历史会话用过 tftp） | 无以太网驱动，tftp 不可用；串口是唯一装载通道 |
| Linux | 由厂商 cspboot 链启动 | 由 `e2631boot` 启动；启动成功后 SSH/系统与现在一致 |

## 7. C1b 预刷写就绪清单（建议按序，全部需要用户批准才动手）

1. **重新读一份当前 mtd0 备份**（刷前状态），核对 `0x20000..0xC0000` 与本文 `3b49d4fb…` 一致；
   env 区应为 26 项（B1 后状态）。备份放本机 + 另一份离机（不要只留一份）。
2. **C1b-0（RAM 链）验收 0x47F00000 映像**：用 task-55 的 10-patch 产物，从厂商控制台 tftp/xmodem 到
   `0x47F00000` + `go 0x47F00000`，确认 banner/autoboot/`e2631boot`/内核完整启动（只读会话，不写 flash）。
   这是"入口=链接地址"和内容正确性的真机证据；**没有这一步不要刷**。
3. **loadx 收包演练**（C1b-0 会话内，只读）：在我们的控制台 `loadx 0x42000000` 收一个小文件（例如 4 KiB），
   用 `md.b`/`cmp` 核对；同时试 1 KiB 块与 128 B 块（主机侧 hub/minicom/pyserial 三选一），确认块大小与握手。
4. **写路径演练**（需要额外批准，属于"写 flash"）：在 `0x7F00000..0x8000000`（§6.6.1：不属于任何分区的 1 MiB 空区，全 FF）
   做 `mtd erase` → `mtd write` 测试图样 → `mtd read` + `cmp` → 再 `mtd erase` 恢复。
   验证"我们 U-Boot 的 mtd write 在该 SPI-NAND/ECC 上能写能读"；**不要在 mtd0 上试第一次写**。
5. **A2 路径演练**（只读）：`loadx 0x47F00000` + `go 0x47F00000` 回厂商控制台，确认厂商 U-Boot 能接管；
   这次演练决定 A2/A3 是否可写进手册的"可用"等级。
6. **电源与在场**：用户在场、稳定供电、串口采样链已停；写 mtd0 期间不得断电/休眠。
7. **验收判据**：C1b 写完后第一次冷启动必须看到我们 U-Boot banner + e2631boot 槽位日志 + 内核启动；
   若失败，按 §5.1/§5.2 执行，回滚完成后记录串口全文与 mtd0 sha256。

## 8. 与 §6.6（芯片级恢复）的关系

- **物理布局/分区偏移不变**：C1b 只改变 mtd0 的 `0x20000..0xC0000`（U-Boot 区）内容；
  §6.6.1 的分区↔芯片偏移表、§6.6.2 的回写规则（只写主区、OOB 由编程器/MTD 生成、坏块、跨机禁止）全部继续适用。
- **mtd0 内的 env 区（0xC0000..0xDFFFF）不在 C1b 写入范围**：它仍是 B1 后的 26 项厂商块；C1b 前后不变。
- **v2 整片 dump（`4a20e693…`）是 C1b 之前的状态**：如果将来用芯片级回写恢复，它会同时把 U-Boot 区恢复成厂商版本
  （这正是我们想要的兜底），但也会把 env 区恢复成 22 项旧状态、把槽位/overlay 恢复成 11-20 的状态——按 §6.6.3 的时效警告对待。
- **§6.4 编程器**：仍是 B 层（U-Boot 映像不启动）唯一手段；本任务没有改变它的"未验证"等级。

## 9. 风险清单（C1b 相关）

| # | 风险 | 影响 | 现有缓解 |
|---|---|---|---|
| R1 | 写 mtd0 过程中掉电 | 引导区半写 → 真砖 | 稳定供电、用户在场、短窗口、写后回读校验；接受残余风险 |
| R2 | 我们的 U-Boot 映像本身不启动 | `Jump` 后无 banner，无控制台 | C1b-0 RAM 链演练（§7 第 2 条）；入口/内容/autoboot 全链验证后才刷 |
| R3 | mtd write 的 ECC/坏块行为与 secondboot 期望不一致 | 写成功但 secondboot 读不回 | §7 第 4 条未用区写路径演练；payload 上限 0x9F800 校验 |
| R4 | 回滚文件丢失/被改动 | 无法回滚 | 产物 1 入库 + sha256；产物 2 可随时从 mtd0 备份再生成；双份备份 |
| R5 | loadx 块大小/握手不兼容 | 收包失败（不写 flash，可重试） | §7 第 3 条演练；128 B 块兜底 |
| R6 | 回滚命令 `nand write.uboot` 实际不可用 | A3 手段失效 | 不把它当主路径；主路径是 A1（mtd write） |
| R7 | 反方向 `go` 厂商 U-Boot 未演练 | A2/A3 可能不可用 | §7 第 5 条只读演练；失败则退回 A1/编程器 |
| R8 | 环境变量/校准区被误写 | 身份/无线数据损坏 | 写范围严格限制 0x20000+0xA0000；env 0xC0000 不碰 |
| R9 | 版本/槽位判断误读 | 刷后从错误槽启动 | e2631boot 已有 serial 比较与 CRC 校验；保留 slot0 厂商槽 |
| R10 | 文档把"未验证"写成"可用" | 救援时误操作 | 本文件与手册 §6.7 都显式标注证据等级 |

## 10. 未验证项 / 开放问题

- Q1：我们的 U-Boot `loadx` 是否接受 1 KiB XMODEM 块？（C1a 的 1 KiB 是厂商 `xmodem` 命令；我们的 xyzModem 默认 128 B 更稳。）
- Q2：主机侧用哪个发送器最稳（hub xmodem op / minicom / pyserial）？
- Q3：A2 反方向 `go 0x47F00000` 厂商 U-Boot 是否一次成功（DRAM/UART 重初始化、重定位）？
- Q4：厂商 `nand write.uboot` 是否真的有派发路径？（静态证据为否；只有真机试命令才能确定。）
- Q5：我们的 `mtd write` 写 mtd0 时坏块表/ECC 参数与 secondboot 是否一致？（未用区演练 + 回读是现有最好验证。）
- Q6：写 0x20000+0xA0000 时是否应该 `.dontskipff`（本区尾部有 FF 填充页；默认跳过更安全还是全写更一致？）——演练决定。
- Q7：C1b 的刷写工具链最终走哪条（Linux 侧？RAM 链 U-Boot `mtd write`？）——由 Lead 的 C1b 方案决定；本文只准备救援/回滚。
- Q8：C1b 后 `e2631boot` 失败时的默认行为（停在 `=>` 还是自动重试）需在刷前确认。

## 11. 证据文件

| 文件 | 说明 |
|---|---|
| `evidence/p2-oob/vendor-uboot-ram.bin` | 本任务产物 1（入库）；426,048 B；sha256 `a4c640ad…` |
| `evidence/p2-oob/vendor-uboot-region-0x20000-0xC0000.bin` | 本机产物 2（不入库）；655,360 B；sha256 `3b49d4fb…` |
| `evidence/p2-oob/sha256sums.txt` | 既有 P2 OOB 会话哈希清单（本任务未改） |
| `docs/救砖手册-2026-11-15.md` §6.7 | 操作版救援章节（本次新增） |
| `evidence/uboot-re-20261115.md` | 厂商 U-Boot 逆向基线（基址/命令表/密码） |
| `evidence/c1a-bootm-20261121.md` | C1a 装载/启动链证据（xmodem 发送器来源） |
| `evidence/chip-level-layout-20261120.md` | §6.6 芯片级布局依据 |
| `uboot-port/README.md` | C1b 映像入口（patch 0010，0x47F00000）与阶段边界 |

## 12. 复现检查清单（离线可跑）

```bash
cd /home/qc233/zte/e2631-immortalwrt
# 1) 源 dump 哈希
sha256sum /home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin
#   期望 de4ea5bd…4d5f3f

# 2) 重建两个产物并核对
dd if=/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin of=/tmp/vendor-uboot-ram.bin \
   bs=1 skip=$((0x20800)) count=$((0x88840-0x20800)) status=none
sha256sum /tmp/vendor-uboot-ram.bin   # 期望 a4c640ad…
cmp /tmp/vendor-uboot-ram.bin evidence/p2-oob/vendor-uboot-ram.bin && echo "ram payload OK"

dd if=/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin of=/tmp/vendor-uboot-region.bin \
   bs=1 skip=$((0x20000)) count=$((0xA0000)) status=none
sha256sum /tmp/vendor-uboot-region.bin # 期望 3b49d4fb…
cmp /tmp/vendor-uboot-region.bin evidence/p2-oob/vendor-uboot-region-0x20000-0xC0000.bin && echo "region OK"

# 3) 头块/尾标记抽查
xxd -s 0x10 -l 8 /tmp/vendor-uboot-region.bin    # 128s + 0x68000
xxd -s $((0xA0000-0x200)) -l 64 /tmp/vendor-uboot-region.bin | tail -2  # 尾标记 V1.0.0
```

