# C1b-1 写 mtd0 后闪存启动卡死：只读诊断、厂商路径对照与 env 变更披露

日期：2026-11-21 / 2026-11-22。作者：verify-docs（验证门禁/文档/端到端）。状态：**未提交**，待 Lead 审阅后决定是否推送。
范围：真机只读诊断 + 厂商 RAM 链对照 + 既有日志/产物比对；本会话**没有任何由我们发出的 flash 写命令**（详见 §7）。静态根因分析由 iwrt-baseline 独立完成，见 evidence/p2-flashboot-kernel-hang-20261121.md。

## 0. 结论摘要

1. 我们把自研 U-Boot（448,112 B，sha256 010379fd...，入口 0x47F00000）写入 mtd0 0x20000..0xC0000 后，冷启动链路正常走到 Starting kernel ...（22:20:38），随后**完全静默 13 分钟以上**：无内核日志、无 panic、无复位、网络不通。
2. 同一份 U-Boot 二进制、同一个 slot1 内核、同样的 bootm 参数，在“经厂商 U-Boot 初始化后再进入”的 RAM 链上可以正常启动内核（C1b-0）；把厂商 bootloader 装回 RAM 并用它自己的 cspstart 启动同一个 slot1 镜像，也在 3 秒内进入用户态（Phase B）。因此**唯一失败环节是我们 U-Boot 在闪存链上到内核的交接**。
3. 静态根因（iwrt-baseline，evidence/p2-flashboot-kernel-hang-20261121.md §4/§5/§8）：厂商 U-Boot 在入口和跳内核前各做一次 **CP15 状态归一**（失效 L1/TLB/BTB、clean+invalidate D-cache、关 MMU/D-cache）；我们的构建因为 CONFIG_SKIP_LOWLEVEL_INIT=y + SYS_ICACHE_OFF/SYS_DCACHE_OFF/SYS_L2CACHE_OFF=y，两条归一通道都被编译掉，bootm 前只剩 invalidate（不能 clean/flush、不能关 D-cache/MMU）。若 secondboot/BootROM 留下 D-cache/MMU 开启，内核镜像与 ATAGS 的脏行不会写回 DRAM，内核读到旧内存后静默死亡。厂商并不碰 PL310/SCU/ACTLR/时钟（全量反汇编 0 引用），所以修复方向是 CP15 归一，不是 L2 驱动。
4. 修复与验证方案：新构建加入 e2631soc 命令（不复位地执行缺失的归一序列），先做 RAM 链实测（Session A），再把新镜像写入 flash（Session B）、冷启动验证（Session C）。本轮已备好三个驱动，等待新产物。
5. **披露**：诊断期间（Phase B）厂商 bootloader 在 cspstart 流程里自行改写了 mtd0 的 env 块（0xC0000..0xE0000）。这不是我们发出的写命令；我们的 U-Boot 镜像区、secondboot 区、slot 头均完好。Lead 已决定在 Session B 先用已演练的 erase/write 通道把 env 恢复成已知良好块，再做刷写。

## 1. 时间线（2026-11-21 晚）

| 时间 | 事件 |
| --- | --- |
| 22:05:12 | v2 写入会话发出 erase 0x20000 0xA0000，5 个擦除块；读回全 FF |
| 22:09:51 | 发出写命令，320 页；读回成功；22:14:30 readback md == 新镜像 |
| 22:16:21 | env/secondboot 回读校验通过，WRITE VERIFIED + HOLD（未复位） |
| 22:20:26 | 用户断电上电（冷启动） |
| 22:20:27 | BootROM -> secondboot -> **我们的 banner 从闪存出现**（g2797f3dd3860） |
| 22:20:28-38 | Loading Environment from MTD OK；e2631boot 选 slot1；uImage CRCs good；Loading Kernel Image to 40008000 |
| 22:20:38 | Starting kernel ...，之后串口 0 字节（最后仅 23 B CRLF），静默 13+ 分钟 |
| 22:47:15 | Phase A 诊断驱动 READY，等待用户冷启动 |
| 22:50:18 | 用户冷启动；在闪存 U-Boot 提示符截停 autoboot（首发因正则不允许尾随空格误判，已修正） |
| 22:52:48 | attach 到我们的 flash 提示符，完成只读检查（version/bdinfo/printenv/e2631boot info/mtd list） |
| 22:55:28-22:59:14 | Phase B：从 flash 提示符 loadx 厂商 U-Boot RAM 镜像 -> go -> 厂商控制台就绪 |
| 23:18:43-23:18:49 | 厂商控制台执行 cspstart -> Starting kernel ... -> Run /sbin/init（同一个 slot1 镜像，用户态起来） |
| 23:20 之后 | 用户态完整起来：MT7916 ready ~53.7 s、WiFi 初始化完成、br-lan 转发；SSH 取证 |

## 2. 判据与关键事实

### 2.1 失败链（闪存）的 bootm 输入

- U-Boot：U-Boot 2027.01-rc2-g2797f3dd3860，从闪存（mtd0 0x20800 载荷）启动。
- bdinfo：boot_params=0x40000100（patch 0008 生效，task-53 修复成立）、DRAM 0x40000000/0x10000000、relocaddr 0x4ff94000、arch_number 0x0、devicetree embed。
- printenv：MTD env 646/131068 B，bootcmd=e2631boot、bootdelay=3、loadaddr=0x42000000、memsize=256M、B1 四个 e2631_* 变量在位、无 bootargs（由 e2631boot 在 bootm 前写入 RAM）。
- e2631boot info：slot0 at 0x00700000，serial 7，V1.0.0.7B5.8000，header 0x01c60000；slot1 at 0x02300000，serial 12，ImmortalWrt v1.10.0，header 0x03800000；decision=slot1。
- bootm 输出：Image Name: ARM ImmortalWrt Linux-6.18.60、Data Size 3,491,050、Load/Entry 40008000、Verifying Checksum ... OK、Working FDT set to 0、Loading Kernel Image to 40008000，然后 Starting kernel ...。
- 与成功的 RAM 链逐行相同（除进入 U-Boot 之前的最后一段代码不同）。

### 2.2 对照证据

1. **同二进制 RAM 链成功**：C1b-0 会话用同一 u-boot.bin（sha256 010379fd...）经 xmodem 到 0x47F00000，go 后 autoboot e2631boot -> 内核正常（printk: console [ttyAMA0] enabled 起）。
2. **同镜像厂商路径成功**：Phase B 把厂商 U-Boot RAM 镜像（426,048 B，sha256 a4c640ad...）loadx 到 0x47F00000 后 go，进入厂商控制台，cspstart 启动同一个 slot1 镜像：23:18:46 Starting kernel ...，23:18:49 Run /sbin/init，随后完整用户态与 WiFi。
3. 说明 slot1 内核/rootfs 健康、bootm 参数正确，问题只在我们 U-Boot 闪存链的内核交接。

## 3. Phase A：闪存链只读诊断

驱动：/home/qc233/zte/e2631-p3/c1b1_diag.py（selftest/preflight/session/attach）。会话目录：/home/qc233/zte/e2631-p3/c1b1-diag/attach-1/。

发现（全部只读）：

- 提示符截停：在自动启动 3 秒窗口内发送空格可以停在提示符（串口会回显一长串空格）。首版驱动的提示符结束正则为 \r?\n=>[ ]?$，不允许尾随空格，导致 60 秒后误报 MISS；修正为 \r?\n=>[ \t]*$ 并增加 --attach 后续跑。
- version：U-Boot 2027.01-rc2-g2797f3dd3860 (Nov 21 2026 - 11:20:33 +0000)。
- bdinfo：见 §2.1。
- printenv：见 §2.1；MTD env 读取正常（646/131068 bytes）。
- e2631boot info：见 §2.1。
- mtd list：spi-nand0 0x8000000（128 MiB），block 0x20000，min I/O 0x800，OOB 64/avail 62，ECC strength 1/step 512 —— 与 Linux 侧一致。

结论：**bootm 的输入与成功链完全一致**，ATAGS/boot_params/镜像/CRC/槽位选择都不是原因；差异只能来自进入内核时的 CPU/缓存/MMU 状态。

## 4. Phase B：厂商 bootloader 路径对照

驱动：/home/qc233/zte/e2631-p3/c1b1_phaseb.py、c1b1_phaseb2.py。会话目录：/home/qc233/zte/e2631-p3/c1b1-diag/phaseb-1/2/3/。

- 从我们的 flash 提示符用 loadx 0x47F00000 装载厂商 U-Boot RAM 镜像（40.1 s），全量 md 校验通过，go 0x47f00000，厂商控制台按 Press 1 + 密码进入（22:59:14）。
- 厂商 printenv/help 实测：bootcmd 只是 setenv bootargs ...（结尾裸分号、无 boot），run bootcmd 不启动；bootk 是 TFTP 引导；cspstart 是 pdt_cspboot_run 路径；cspboot 只做初始化。
- cspstart 实测：23:18:43 发送，23:18:46 Starting kernel ...，23:18:49 Run /sbin/init as init process，VFS 以只读 squashfs 挂载 device 31:7（我们的 slot1 rootfs），随后 MT7916 ready ~53.7 s、WiFi 自动初始化完成。驱动 verdict GREEN（23:20:08）。
- 该路径日志包含 Image Name: ARM ImmortalWrt Linux-6.18.60、zteboot_search_firmware correct header has been found @1c60000 等厂商引导器输出。

结论：**slot1 内核+rootfs 本身健康**；在我们 U-Boot 闪存链上失败的唯一环节是“从我们的 bootm 跳入内核”。

## 5. 根因（引用 iwrt-baseline 静态分析）

详见 evidence/p2-flashboot-kernel-hang-20261121.md（iwrt-baseline，未提交）。要点：

1. 厂商 U-Boot 在入口 cpu_init_crit 与跳内核前 cleanup_before_linux 各做一次 CP15 状态归一：失效 L1 I/D、TLB、BTB；clean+invalidate D-cache by set/way；关 MMU 与 D-cache；关 I-cache。
2. 我们的构建：CONFIG_SKIP_LOWLEVEL_INIT=y 让 start.S 跳过 cpu_init_cp15/cpu_init_crit；SYS_ICACHE_OFF/SYS_DCACHE_OFF/SYS_L2CACHE_OFF=y 让 icache_disable()/dcache_disable() 变成空实现，v7_outer_cache_disable() 是空弱符号；bootm 前的 cleanup_before_linux() 实际只剩 invalidate（不能 clean/flush，不能关 D-cache/MMU）。
3. 因此闪存链上内核继承 secondboot/BootROM 留下的 CP15/缓存/MMU 状态；若 D-cache 或 MMU 为开，我们 U-Boot 写内核/ATAGS 的脏行不会回写 DRAM，bootm 的 invalidate 反而丢弃它们，内核读到旧内存后静默死亡（候选 C1/C2，高）。
4. 厂商**不做** PL310/L2、SCU、ACTLR、CPU PLL 初始化（全量反汇编 0 处真实引用），所以这些不是差异；修复方向是把缺失的 CP15 归一补回来，而不是加 L2 驱动。

## 6. env 块被厂商 bootloader 自行改写（披露）

- 现象：Phase B 的 cspstart 启动内核时，厂商 bootloader 自己执行了 zteboot_update_bootpara -> Saving Environment to NAND... -> 擦除/写入 mtd0 env 块。串口原文（c1b1-diag/phaseb-3/serial.log 第 221-224 行）：
  - Saving Environment to NAND...
  - Erasing 0xc0000 - 0xe0000:<nand_erase_skip_bad_,609>!mtdpart=0x1,...,mtdpartoffset=0xc0000,mtdPartsize=0x40000,length=0x20000
  - Writing to Nand:<nand_write_skip_bad_,504>!mtdpart=0x1,...,length=0x20000
- 这是厂商 bootloader 的正常行为，不是我们发出的命令：该会话命令白名单仅 loadx/go/version/help/printenv/mtd list/cspstart，写审计为 0 条 nand/mtd write、0 条 erase、0 条 saveenv。
- 影响范围（当前 mtd0 dump：/home/qc233/zte/e2631-p3/c1b1-diag/mtd0-now/mtd0-now.bin，sha256 d571b76404df1596dd58b710cff84e1ede92e6a29798abe5dcc50198d286b0f5）：
  - 与预期（写入新镜像后的 3c8a8c5b...）相比，差异仅 25 段 / 789 B，全部在 0xC0000..0xC0343；
  - secondboot 区 0..0x20000 = 540db435...（基线）未变；
  - 我们的 U-Boot 镜像区 0x20000..0xC0000 = baf28b6d...（等于 mtd0 镜像 sha）未变；
  - 尾部 0xE0000..0x100000 = b5a41c37...（基线）未变；
  - slot 头（mtd5/mtd6）未变：slot1 version 头 d707f2c8...、slot1 uImage 头 68765a72...、slot0 厂商头 c579e3a9...，与 A3 参考一致；
  - env 新内容 27 项，CRC 有效（stored=computed=0xc8e93924），新增一项 bootargs=console=ttyAMA0,115200n8 root=/dev/mtdblock8 ro rootfstype=squashfs mem=256M，versioninfo 被破坏成 setenv 片段；bootcmd/bootdelay/memsize 未变。
- 处置（Lead 决定）：Session B 先用已演练的 erase+write 通道恢复已知良好 env 块（6e2c01da...），使 mtd0 回到 3c8a8c5b...，再做新镜像刷写。新常设规则：**任何厂商 RAM 会话之后，env 块都视为已漂移，ladder 基线前必须校验/恢复**。

## 7. 零写审计与恢复

- 本会话（Phase A/B）由我们发出的命令：loadx、go、version、help、printenv、mtd list、mtd read、cspstart；**无** nand/mtd write、无 erase、无 saveenv、无 tftp、无 bootm。
- 设备在 Phase B 之后保持运行（厂商路径启动的 ImmortalWrt，WiFi up、SSH 可用），未做任何复位/断电之外的写操作。
- 当前设备状态（2026-11-21 23:30 只读检查）：ImmortalWrt v1.10.0 / r0-86cddb7 / zx279128/generic / kernel 6.18.60 / uptime 656 s；PANICS=0；mt7915e 19 行；MT7916 ready 55.83 s；fwslot info：running=1 next=1，slot0 serial 7 / V1.0.0.7B5.8000，slot1 serial 12 / ImmortalWrt v1.10.0，两个槽位 valid+intact。
- 恢复路径（已验证可用）：冷启动 -> 我们的 flash 提示符 -> loadx 厂商 U-Boot RAM 镜像 -> go -> 厂商控制台 -> cspstart -> Linux；或直接用已演练的 mtd0 erase+write 回滚厂商区。

## 8. 修复与验证计划（待新构建）

1. **新构建**：在 U-Boot 里实现无条件、不依赖 CONFIG_SYS_*CACHE_OFF 的 CP15 归一序列（clean+invalidate L1 D-cache、关 MMU/D-cache、失效 I-cache/TLB/BTB），并加 e2631soc 命令，在闪存链提示符下先执行归一、再 e2631boot。构建走 GitHub Actions，本机不编译。
2. **Session A（RAM 链实测，零 flash 写）**：冷启动 -> 我们的 flash 提示符 -> 只读 md 探测 PL310/SCU 寄存器（0xc00100/0xc00104/0xc00000/0xc00108/0x800000/0x800004） -> loadx 新 u-boot.bin -> go 0x47F00000 -> 新 banner -> 再探测 -> e2631soc -> 再探测（并记录命令打印的 CP15 前后状态） -> e2631boot -> 内核是否起来。若起来，根因确认、修复有效。
3. **Session B（env 恢复 + 新镜像刷写）**：冷启动 -> 我们的 flash 提示符 -> 恢复 env 块（erase 0x20000@0xC0000 -> FF gate -> 写 6e2c01da... -> 断言回读，mtd0 回到 3c8a8c5b...） -> 新 mtd0 镜像 ladder（loadx -> 全量 md -> erase 5 块@0x20000 -> FF gate -> 写 320 页 -> 断言回读 -> env/secondboot/tail 基线校验） -> HOLD。
4. **Session C（冷启动验收）**：断电上电 -> 新 banner 从闪存启动 -> e2631boot -> 内核起来 -> SSH 回读 mtd0 == 新预期 sha + health（PANICS=0 / MT7916 ready） = P2 GREEN。
5. 三个会话驱动已备好并自测：/home/qc233/zte/e2631-p3/c1b1fix_session{A,B,C}.py；本次会话只做只读诊断，尚未执行 A/B/C。

## 9. 未决与待办

- 新构建的 u-boot.bin / e2631-uboot-mtd0.bin 产物、banner token、e2631soc 命令契约由 base-builder CI 交付，Lead 转达后执行 Session A。
- Session A 的 md PL310/SCU 探测可能显示“无变化”（静态分析显示厂商也不碰这些寄存器）；决定性证据是 e2631soc 打印的 CP15 前后状态 + 内核是否起来。
- 证据文档、会话记录与驱动在三个会话完成后统一整理并（经 Lead 批准）提交。

## 10. 附件与路径

- 失败链日志：/home/qc233/zte/e2631-p3/c1b1-final-v2/run-1/serial.log（10,737,796 B，最后一次尝试）。
- Phase A：/home/qc233/zte/e2631-p3/c1b1-diag/attach-1/（preflight.json、session-results.json、version.txt、bdinfo.txt、printenv.txt、e2631boot-info.txt、mtd-list.txt、serial.log）。
- Phase B：/home/qc233/zte/e2631-p3/c1b1-diag/phaseb-{1,2,3}/（vendor-printenv.txt、vendor-help.txt、boot-attempt-*.txt、serial.log、session-results.json）。
- 当前 mtd0 dump：/home/qc233/zte/e2631-p3/c1b1-diag/mtd0-now/mtd0-now.bin。
- 基线/预期：/home/qc233/zte/e2631-p3/b1-env-session/resume-1/target-mtd0.bin（887a7f6c...；env 块 6e2c01da...）；旧镜像 mtd0 预期 3c8a8c5b...。
- 驱动：/home/qc233/zte/e2631-p3/c1b1_diag.py、c1b1_phaseb.py、c1b1_phaseb2.py、c1b1fix_session{A,B,C}.py。
