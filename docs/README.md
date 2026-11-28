# docs/ 索引

本目录按「先读什么」排序。所有条目都是本仓库历史与证据的一部分；状态描述以文件内
实际内容为准，本文只做导航。

## 从这里开始

| 文件 | 内容 |
|---|---|
| [architecture.md](architecture.md) | 地图：仓库结构、从源码到可启动镜像的链路、槽位几何、验证栈 |
| [immortalwrt-migration.md](immortalwrt-migration.md) | ImmortalWrt 基线迁移的决策、证据与风险；基底升级 runbook 在 §8 |
| [known-issues.md](known-issues.md) | 机器可读的诚实清单：每个已修/未修问题、证据与规避方式 |
| [救砖手册-2026-11-15.md](救砖手册-2026-11-15.md) | 救砖手册：串口 / U-Boot 控制台 / TFTP RAM 引导 / failsafe / 回原厂槽位路径 / 自定义 U-Boot 刷后救援（§6.7） / 危险区与禁止事项 |
| [updates.md](updates.md) | 在线更新机制：原地升级不变量、e2631-upgrade 流程、槽位适配 |
| `../BUILD.md`、`../README.md` | 构建步骤 / 状态与取舍（仓库根目录） |

## 实施记录（按任务）

| 文件 | 内容 |
|---|---|
| [immortalwrt-migration.md](immortalwrt-migration.md) | T1 决策 + T4 门禁/文档实施状态 + §8 基底升级 runbook |
| [t3-packaging-release-ci.md](t3-packaging-release-ci.md) | T3：产物名与版本口径、在线更新与镜像白名单修复、CI 改造、host 侧模拟证据、仍需 CI/真机证明的事项 |
| [treefork-migration-design.md](treefork-migration-design.md) | T-12 设计：设备支持改为 QC3284/immortalwrt 树 fork 的真实提交，套件只留构建/打包/发布 |
| [../evidence/immortalwrt-verify-20261114.md](../evidence/immortalwrt-verify-20261114.md) | T5：ImmortalWrt 适配的端到端构建与产物验证报告（本地门禁、CI run、产物 sha256、未覆盖项） |
| [../evidence/t20-verification-20261114.md](../evidence/t20-verification-20261114.md) | T-20：树 fork 重钉重建对的独立验证（RUN1/RUN2 产物哈希、两层门禁、APK 钉值、A==B 逐字节一致、与基线差异复核） |
| [../evidence/cold-boot-sampling-20261114.md](../evidence/cold-boot-sampling-20261114.md) | T-19 与回归：MT7916 冷启动采样（v1.10.0 11/11 + r0-83df1a9 3/3，累计 14/14，0 失败签名）与完成度只读核查 |
| [../evidence/r-verify4-parity-20261115.md](../evidence/r-verify4-parity-20261115.md) | R-验4：RUN5 merge 候选 parity（PASS-REVIEWED-DIFFS、kernel merge-class 归因、RUN4 失败记录） |
| [../evidence/c-plan-parity-20261121.md](../evidence/c-plan-parity-20261121.md) | C-验1：RUN6（方案 C，target 改名 zx279128）对 RUN5 的 parity 验收（RUN6 v3 PASS-REVIEWED-DIFFS，expected 23 / allowed 13 / unexpected 0，kernel STAMP-ONLY，含首轮 5 条归因与负对照） |
| [../evidence/t38/](../evidence/t38/) | task-38 验收附件：verify-task38.sh、终稿策略、端到端日志、比较器/kernel-deep/verify_img 报告、负对照 |
| [../evidence/p2-oob-recon-20261121.md](../evidence/p2-oob-recon-20261121.md) | P2-P1：mtd0 OOB 只读取证（512 页表、normal/RAW 全 FF、跨分区对照、ECC 布局未证实、READID 推断、U-Boot 区界核对） |
| [../evidence/p2-oob/](../evidence/p2-oob/) | task-42 取证附件：OOB 表/二进制、headblock/env/secondboot hex、会话日志、工具源码与 sha256 清单 |
| [../evidence/a1-banner-acceptance-20261121.md](../evidence/a1-banner-acceptance-20261121.md) | task-49/task-50 设备段：A1/A2 u-boot.bin 经 vendor xmodem 装入 RAM 并 go 的 banner/prompt 验收（A1 4910ee2045bd、A2 38bee433d177；mtd list + 两次只读读回；零 flash 写入以 mtd0 sha256 前后一致实证；含工具缺陷修复与主机路由陷阱记录） |
| [../evidence/a1-banner-acceptance/](../evidence/a1-banner-acceptance/) | task-49 验收附件：驱动脚本、session/a2 results JSON、驱动与 health 日志、串口选段 |
| [../evidence/a3-ramchain-20261121.md](../evidence/a3-ramchain-20261121.md) | P2-A3：slot-aware 启动 RAM 链只读验收（banner g8a9d1f7eecfa、md.b 448,072 B 0 差异、info 0.81 s 决策 slot1、load 4.61 s 3,491,146 B CRC 通过不 boot、4 个 mtd 切片 0 差异、mtd0 sha256 前后一致、reset no-op 需断电；含解析器缺陷与主机路由陷阱记录） |
| [../evidence/a3-ramchain/](../evidence/a3-ramchain/) | A3 验收附件：驱动/health 脚本、两次 session results JSON、驱动日志、串口选段、参考切片、零写入证据 |
| [../evidence/b1-env-session-20261121.md](../evidence/b1-env-session-20261121.md) | P2-B1：vendor U-Boot env 定制真机会话（一次 saveenv 持久化 4 条旁路变量；修正为字母序插入预测 CRC 0xF95A816E / env 块 sha 6e2c01da…；回读 byte-identical、mtd0 差异 462 B 全在 env 块内、bootcmd/bootdelay 未变、设备健康；含第一段中止零写入与工具缺陷记录） |
| [../evidence/b1-env-session/](../evidence/b1-env-session/) | B1 会话附件：两段驱动脚本、results/回读 JSON、预测与实读 env 块、串口/驱动/health 日志、sha256 清单 |
| [../evidence/c1a-bootm-20261121.md](../evidence/c1a-bootm-20261121.md) | P2-C1a：A3 U-Boot bootm 干跑（预闪写门禁）——首跑 RED（boot_prep_linux 构造 ATAGS 时 data abort，bi_boot_params 未初始化，内核未启动）→ task-53 修复后重跑 PASS（bootm 启动生产内核、用户态起来；零写入，mtd0 sha256 前后一致；恢复 stock 链健康）；含 §11.4 重跑证据与 C1b 冻结结论 |
| [../evidence/c1a-bootm/](../evidence/c1a-bootm/) | C1a 附件：首跑驱动/results/预检、abort 原文、恢复验证与 health；`run-2/` 为重跑 PASS 附件（postcheck、恢复段、驱动、sha256 清单） |
| [../evidence/c1b0-entry-20261121.md](../evidence/c1b0-entry-20261121.md) | P2-C1b-0：0x47F00000 产品入口 RAM 链干跑 GREEN（新 banner g2797f3dd3860、xmodem 448,112 B、md 抽查、env MTD 只读、e2631boot→bootm→内核/用户态；零 flash 写入以 mtd0 sha256 前后一致实证；SSH reboot 恢复 stock 链；含 C1b-1 写通道计划变更记录） |
| [../evidence/c1b0-entry/](../evidence/c1b0-entry/) | C1b-0 附件：驱动、results/preflight、串口/驱动/health 日志、artifact UBOOT-INFO/SHA256SUMS/config、sha256 清单 |
| [../evidence/c1b1a-write-rehearsal-20261121.md](../evidence/c1b1a-write-rehearsal-20261121.md) | P2-C1b-1a：写通道 dress rehearsal GREEN（run-1 冷启动：loadx 128 B/1 KiB、mtd write/read/cmp/erase 0x7F00000 块全 clean；run-2 SSH warm reboot：reverse go → vendor Press-1 → 密码 → `=>` → version → reset → stock Linux；零越界写入，mtd0 前后 887a7f6c… 不变） |
| [../evidence/c1b1a-write-rehearsal/](../evidence/c1b1a-write-rehearsal/) | C1b-1a 附件：两次 run 的 results/preflight/驱动日志、串口选段（scratch 写/擦、vendor 控制台/reset）、驱动源码、sha256 清单 |
| [../evidence/p2-flashboot-kernel-hang-20261121.md](../evidence/p2-flashboot-kernel-hang-20261121.md) | A-研0：闪存链内核静默挂起的厂商 U-Boot 早期初始化差异静态分析——厂商不做 PL310/SCU/ACTLR/时钟初始化，只做入口 cpu_init_crit 与跳前 cleanup 两次 CP15 归一；我们的 SKIP_LOWLEVEL_INIT + SYS_*CACHE_OFF 把两条通道都关掉；含 bootk/cspstart 调用图、排序候选、排除项（载荷同哈希、bootpara 被 zImage 解压器页表覆盖）、修复/验证建议 |
| [../evidence/p2-vendorless-network-gap-20261122.md](../evidence/p2-vendorless-network-gap-20261122.md) | A-研1：无厂商 U-Boot 链路的网络缺失定位——厂商 board_eth_init 的 ref_clk_set/pll_cfg_fractional/SerDes（0x9FE00000）参考时钟序列没有被复刻是主因（内核侧全树无引用、时钟驱动自述 PLL 归 bootloader）；含精确 MMIO 写表、GPIO 18 条表（LED/按键/未知脚）、DTS 覆盖结论、product_vid 排除、patch 0012 建议与验证计划、Q1-Q5 未决项 |
| [../evidence/uboot-a5-device-session-20261122.md](../evidence/uboot-a5-device-session-20261122.md) | A5 真机会话：patch 0012 网络参考时钟 / SerDes 零写入验收——e2631refclk 7 个寄存器 before/after 全契约 PASS、SerDes 24/24 读回 PASS、以太网缺口确认修复（四 PHY + 1 Gbps）、正式 run-3 PCIe/Wi-Fi 确定性 FAIL（patch 0012 把 flat GPIO 2/51 拉低、端点停在复位）；run-2 的“PCIe 成功”复核为厂商链、已更正；残余 10 字差（GPIO pin2/pin51）交 patch 0013；零 flash 写入实证 |
| [../evidence/uboot-a5-session/](../evidence/uboot-a5-session/) | A5 附件：会话驱动与 PCIe 只读探针、run-1/2/3 驱动控制台与 results、e2631refclk 串口选段、内核证据、观察 B 捕获选行、残余差分、零写入核对、artifact 构建信息、sha256 清单 |
| [../evidence/uboot-a6-device-session-20261122.md](../evidence/uboot-a6-device-session-20261122.md) | A6 真机会话：patch 0013 两条 PCIe 端点复位线零写入验收 GREEN——GPIO pin2 `0x94407014`=0x0000db2c（bit2）、pin51 `0x944070d4`=0x0000e028（bit3）与厂商残差逐位一致；两条 PCIe Gen.1 x1 link + 14c3:7906/790a 端点；四 PHY + lan1/wan 1 Gbps；MT7916 ready 176 s + 双频转发；mtd0 零变化；含 Wi-Fi latency 观察项与驱动 KeyError 工具缺陷记录 |
| [../evidence/uboot-a6-session/](../evidence/uboot-a6-session/) | A6 附件：v3 驱动与修正版、独立判据脚本、results/preflight、串口/内核选段、只读 SSH 终态、前两次中止输出、postcheck、artifact 校验信息、sha256 清单 |
| [../evidence/t61-uboot-flash-acceptance-20261122.md](../evidence/t61-uboot-flash-acceptance-20261122.md) | task-61 / D-U4 真机自持刷写验收：无串口桥接刷入 patch-0014（Linux HTTP staging + 旧 U-Boot mtd read/crc32/erase/write 桥接；CRC 链 0x0721e716→0x804737c5 全 FF→写→0x0721e716；写入审计 1 erases + 1 write；单次用户断电后新 banner g85df6772a444 从 flash 起、e2631boot→slot1→内核、PCIe 两端点/四 PHY/双频 AP 全绿；mtd0 == f9239040… 与预计算一致；旧串口路径 >5.5 min vs 1.24 s + 约 3 s） |
| [../evidence/t61-uboot-flash/](../evidence/t61-uboot-flash/) | task-61 验收附件：会话驱动、preflight/host-facts/session-results、驱动日志、串口会话选段、断电后冷启动段、sha256 清单 |
| [../evidence/t62-session-b-flash-20261122.md](../evidence/t62-session-b-flash-20261122.md) | Session B 真机写入验收（2026-11-22 03:00-03:24）：旧 U-Boot 桥接 → 厂商 RAM 控制台 → v3 U-Boot g85c7367a3106 → env 块恢复（6e2c01da）+ image 区写入（f6d179da）手工擦/FF/写/读回阶梯；审计恰 2 erase + 2 write；刷后 mtd0 == 5ebb5ab3…（用户断电冷启动 + 后续只读复核双重确认）；含 cmp 假失败驱动缺陷与「不要 dump mtd 到串口」教训 |
| [../evidence/t62-session-b-flash/](../evidence/t62-session-b-flash/) | Session B 附件：驱动、preflight/session-results、驱动日志、串口原文精选、断电后只读诊断、expected-mtd0 重构脚本与 sha256 清单 |
| [U-Boot-env写回与启动计数设计-2026-11-22.md](U-Boot-env写回与启动计数设计-2026-11-22.md) | D-U2 设计：env 写回（W1 受控写通道、厂商格式/坏块/掉电风险、0xE0000 保留）+ class-1/class-2 回退与启动计数设计、patch 0014/0015 计划与 CI 断言；证据见 [../evidence/p2-env-writeback-design-20261122.md](../evidence/p2-env-writeback-design-20261122.md) |
| [../evidence/uboot-env-writeback-20261122.md](../evidence/uboot-env-writeback-20261122.md) | U-0017（task-64）：U-Boot env 写回交付——patch 0017 新增 `e2631env check/diff/save`（唯一 env 写入口，五步写：坏块预检→擦除→全 0xFF→写入→逐字节回读；4 条编译期布局断言；白名单 `e2631_*`+`bootdelay`；厂商键快照；`0xE0000` 保留扇区写前后全 FF；无变化不擦除）；`env/mtd.c` `.save` 保持 NULL、saveenv/eraseenv 仍关闭；CI run 44978733720 GREEN（banner g9a4028535269、u-boot.bin 465,600 B、mtd0 sha e2a76f75…、env 块未变、checkpatch 0E/22W）；第一次真机 save 待批准 |
| [../evidence/e-plan-net-driver-20261122.md](../evidence/e-plan-net-driver-20261122.md) | E-研1（task-65）：U-Boot 以太网驱动移植可行性——keep/drop 表（main.c 1502→保留约 740 行；mdio 157→62；ppe 仅 trap-DMAC 子集；ffe/switch 全弃）、最小寄存器初始化序列（PP bridge/TM 表/BMU 4096 buffer/DMA 环/交换机核心/MAC/PHY，全部带内核 file:line）、DTS/defconfig/16 MiB arena 0x45000000 方案、3 patch（0018-0020）/约 1100-1200 行/3 里程碑估算与 R1-R10 风险（最可能的拦路虎是 TX/RX 数据通路初始化顺序而非 PHY；switch 核心必须初始化但无需 VLAN/PPE 卸载） |
| [../evidence/uboot-checkpatch-maintainers-20261122.md](../evidence/uboot-checkpatch-maintainers-20261122.md) | checkpatch 门禁（option A）：四类显式豁免（FILE_PATH_CHANGES/CMD_TEST/LIVETREE/PREFER_IF，workflow 逐类注释 + 运行期断言恰好四类，其余 warning/error 直接失败）、本地负向测试、CI run 44983615483 的 0/0 checkpatch 产物（banner gc7ac1db6eb7f、u-boot.bin sha256 a07f0e56…、mtd0 sha256 f7ef0bdb…、env 块未变、tree c812dd86…）；并实测同一 tree 重跑只差 28 个版本/时间字节（git am committer date + U_BOOT_DATE/TIME），给出 SOURCE_DATE_EPOCH + --committer-date-is-author-date 的可复现方案 |
| [../evidence/uboot-reproducible-build-20261122.md](../evidence/uboot-reproducible-build-20261122.md) | U-Boot 可复现构建（task-69 item d）：workflow 加 `git am --committer-date-is-author-date` + 固定 `SOURCE_DATE_EPOCH=1795103079`（pinned base committer 时间），banner 固定为 `U-Boot 2027.01-rc2-gf355ce89283c (Nov 19 2026 - 15:44:39 +0000)`；连续两次 dispatch（run 44991454540 / 44991704112，同 head be1e405）的 u-boot.bin（sha256 3cf00029…、494,208 B）、mtd0（sha256 18255c2c…）、.config、u-boot.map、命令帮助与 env 块逐字节相同；无代码/history 改动，tree 仍 c812dd86… |
| [../evidence/uboot-e2-fix-20261127.md](../evidence/uboot-e2-fix-20261127.md) | E2 修复（task-69 items 1/2）：patch 0023 让 eth_send 不再静默（打印 BMU 原因/所需 buffer 数/状态）并移植内核 pending-retry（超时请求保持 pending，下一次收迟到 buffer）；patch 0024 加 staging/kernel-copy/arena 编译期断言并把 0x4554xxxx 换算错误更正为 0x4235454A；24 patches tree 721bb82…，CI run 45985501668 GREEN（banner gcbcaeea0d172、u-boot.bin sha256 15bfa0c1…、mtd0 sha256 c45baf4f…、env 块未变、checkpatch 0E/0W） |
| [../evidence/uboot-defconfig-slim-20261127.md](../evidence/uboot-defconfig-slim-20261127.md) | E4 前置的 defconfig 瘦身（task-69）：只加 `# CONFIG_MMC is not set`，MMC=n→BLK=n 级联丢掉 EFI/标准启动/FAT/块缓存（56 个 `=y` 符号消失、0 新增；控制台少 bootefi/eficonfig/bootflow/blkcache）；u-boot.bin 494,880 → 320,848 B（-174,032 B，-35.17%），25 patches tree ac987015，CI run 45988430055 GREEN（banner ge6678e875e60、u-boot.bin sha256 33928958…、mtd0 sha256 99886ea0…、env 块未变、checkpatch 0E/0W） |
| [../evidence/uboot-f2-tx-probe-20261127.md](../evidence/uboot-f2-tx-probe-20261127.md) | F2b TX 出口死路定位（task-78）：现场事实（TM 收下描述符、MAC 计数不动、无错误打印）、三份实现（U-Boot/内核/厂商 U-Boot 反汇编）对照与 7 个候选的判别手段、patch 0031 的 `e2631net tx/mode/sbrg` 命令契约、零写入 RAM 会话检查单与判读表 |
| [../evidence/uboot-e4-rescue-20261127.md](../evidence/uboot-e4-rescue-20261127.md) | E4 v1 + 厂商复位（task-72/task-76）：patch 0026-0029（最小 TCP/DHCP 栈、`e2631flash` 五步写 job API、`e2631rescue` DHCP+HTTP+gzip 页面+SHA-256/确认头契约+mtd0 五步写、TOPCRM 0x94000044 软复位）；29 patches tree e7dc2463…，CI run 46002766353 GREEN（banner ga9d4df78ce6e、u-boot.bin 360,624 B sha256 49acded8…、mtd0 sha256 79dab60d…、env 块未变、checkpatch 0E/0W）；尺寸 320,848→360,624 B（+39,776 B，超 34 KB 估算 4,960 B）；零写入救援验收步骤与写窗口边界 |
| [../evidence/e4-reset-re-20261127.md](../evidence/e4-reset-re-20261127.md) | task-76：厂商 U-Boot 2013.04 reset 路径逆向——`resetting ...` 后 50 ms 向 TOPCRM+0x44（0x94000044）写 1，BootROM 重跑 secondboot（DDR 重新初始化）；draft patch 在 uboot-port/patches/0029 落地 |
| [../evidence/uboot-key-rescue-20261128.md](../evidence/uboot-key-rescue-20261128.md) | task-82 恢复键进救援：patch 0035——`board_late_init()` 裸 MMIO 轮询 reset（GPIO18/bank1 bit2）与 mesh（GPIO20/bank1 bit4），任一键连续按 2 s 就把 `bootcmd` 在 RAM 内改成 `e2631rescue` 并打印提示，松手取消；只读 `e2631key`；不写 env/flash、不改波特率/refclk 顺序、MTD 写点仍 4 个；CI 新增 key rescue 门禁与 +1 KiB 尺寸门禁；含零写入真机验证计划（GPIO 早启动读安全性） |
| [../evidence/uboot-e4-v2-20261128.md](../evidence/uboot-e4-v2-20261128.md) | E4 v2.1 模块 C（task-84）：patch 0036-0039 交付——共享槽核心/槽写者（包 14 项校验、守卫、擦整槽、写版本头、回读、失败擦头）、rootfs_data 恢复出厂 + 一次性启动槽 `e2631_next_slot`、env 分阶段写 API、`e2631rescue` 的 /slots /env /backup /firmware /boot /factory /console 端点；写 owner 仍为 e2631flash/e2631fwslot/e2631factory/e2631env；39 patches tree 788fda24，CI run 46109519805 GREEN（banner g49f13e0cbe40、u-boot.bin 405,368 B sha256 481368a4…、mtd0 sha256 856703a1…、env 块未变、checkpatch 0E/0W、slot core fixture 51 项、MTD writer sites 9、尺寸 405,368 ≤ 407,560）；三次 CI 失败均为门禁脚本问题；真机验收（零写入 validate + 只读探针 + 首次真实写）交 task-86 需批准 |

| [E4-多功能U-Boot设计-2026-11-27.md](E4-多功能U-Boot设计-2026-11-27.md) | E4 设计稿：MUST/SHOULD/WON'T 需求、A/B/C 方案对照（逐条回答 MUST、假定预算）、v1 最小救援规格（串口 `e2631rescue`→DHCP+单页 HTTP→e2631flash 五步→重启）、刷写路径/掉电回滚、行为合同与可执行验收、F2/E3 依赖 |
| [../evidence/e4-bl-mt798x-dhcpd-study-20261127.md](../evidence/e4-bl-mt798x-dhcpd-study-20261127.md) | E4-研1（task-70）：bl-mt798x-dhcpd 移植评估——上游实为 Yuzhii0718 仓（981213 仓不存在）、核心 TCP/HTTP/DHCP 可搬但高级模块绑定 MTK MMC/UBI 胶水须重写、逐文件尺寸与 gzip 资产 70,858 B、密度校准 0.15–0.30、A/B/C 预算（16–34 / 22–44 / 85–137 KB vs 基线 159,104 B + 捐献 289,800 B）、刷写/RAM 缓冲 0x46000000/五步校验、F2 真机复测门槛 |
| [../evidence/e2b-session-20261127.md](../evidence/e2b-session-20261127.md) | task-67 rev3 / E2-B 真机会话：22-patch RAM 链 U-Boot 的以太网与 bootm 复核——F2 在 42 次 BOOTP broadcast 期间物理线 0 帧（决定性；主机 tcpdump 66 帧内 U-Boot MAC 0 帧、dnsmasq 无 DHCP 事务）、BMU 三寄存器只有 FREE_STATUS 变化；F1 本产物签名为 `Wrong Image Type`（e2631boot load 自校验 header/data CRC 通过，但 0x420020 对 md/bootm 不可见；与 2026-11-22 静默返回不同）；另记录 md vs crc32 可见性观察（待复现，不作解释）；零 mtd0 写入（51 条 U-Boot 命令审计，唯一写入为 userdata staging）；§10 追加 thin 25-patch 复测（2026-11-27 19:58–20:02，run-2 GREEN）：F1 = KERNEL_STARTED（e2631boot 交接成功）、F2 在 DEFAULT env 下物理线仍 0 帧（待 env 回归修复后重跑才能定论）、0x48000000 可见性异常复现、thin 镜像 env bad CRC 回归候选、run-1 根因=外来通配监听占用 18080/18081；零 mtd0 写入（唯一写入 userdata staging） |
| [../evidence/e2b-session/](../evidence/e2b-session/) | task-67 会话附件：session-results、驱动/串口原始字节、tcpdump、dnsmasq/http、f1diag 与 5 轮只读探针结果、产物构建清单、sha256 清单 |
| [../evidence/e2b-session/thin-run2/](../evidence/e2b-session/thin-run2/) | task-67 thin 会话附件：run-2 session-results、原始串口字节、驱动日志、主机 tcpdump（U-Boot MAC 0 帧 / BOOTP 0 行）、dnsmasq/http、run-1 端口冲突失败记录、thin 产物构建清单、驱动脚本、sha256 清单 |
| [../evidence/e4-rescue-acceptance-plan-20261127.md](../evidence/e4-rescue-acceptance-plan-20261127.md) | E4-验1（task-75）：救援模式验收方案 + 无浏览器脚本——零净载荷钉死为当前镜像区 sha256 b1ea9a48…（整 mtd0 f9239040…），Phase 1 userdata 暂存 + mtd read + go 的 RAM 链、S0–S9 步骤、拒绝矩阵（size±1/坏 magic/长度/ padding/banner/摘要不符/payload-flip）、X-E2631-SHA256 传输完整性 vs --expected-sha 权威性、默认 validate-only + 双开关写入、mock 自测 37/50 PASS |
| [../evidence/t74-f2-session-20261127.md](../evidence/t74-f2-session-20261127.md) | task-74 / T74-F2 真机会话：E4 组合产物（patch 0026-0030，banner g6db632ad6e5b）RAM 链 GREEN——ENV OK（env 回归未复现、patch-0030 重试未触发、H1 升级）、F2 NO_WIRE_FRAMES（57 次 BOOTP 无地址；tcpdump 39 帧全为主机、U-Boot MAC 0 帧；DMA 环/TX start/端口使能已置但 MAC TX frames 恒 0，patch-0023 重试路径未被触发）、T74 NO_ANOMALY（写/读/mtd read 全正常，历史 0x42/0x48 可见性异常关闭为探针地址缩写错误）、F1 KERNEL_STARTED 8.31 s；零 mtd0 写入（282 条 U-Boot 命令审计，唯一写为 userdata staging） |
| [../evidence/t74-f2/](../evidence/t74-f2/) | task-74 附件：run-2/run-1 session-results、驱动与原始串口字节、主机 tcpdump、dnsmasq/http、修正版驱动、产物校验清单、sha256 清单 |
| [../evidence/f2-probe-20261127.md](../evidence/f2-probe-20261127.md) | F2 TX 探针真机会话（task-78 构建）：31 补丁 U-Boot（banner ge84e13107885，u-boot.bin sha256 d493042d…）RAM 链验证——F2_PROBE_NO_MOVE（pp / pp-alt / vendor / vendor-alt / allow 重跑全部无 MAC TX 帧、网线 0 设备帧）；C2 排除（SBRG egress 复位值 0:0xfe 1:0xfd 2:0xfb 3:0xf7 4:0xef，allow 为 no-op）；C3 VLAN1 三 word 全 0 仍未排除；hw tx idx 恒 0、第 11 帧起 TX completion timed out、tx done 读清 0x10000/0x20000；两处修正（md.l 0x003883c0 非 SBRG 寄存器，实际为 0x92000000+0x3883c0；sbrg 不带 allow 只打印 VLAN1）；env/mtd0/镜像区零变化，F1 KERNEL_STARTED，唯一写入为 userdata staging |
| [../evidence/f2-probe/](../evidence/f2-probe/) | task-78 探针附件：session-results、原始串口字节与探针段、驱动与日志、主机 tcpdump、产物构建清单、sha256 清单 |
| [../evidence/f2-fixed-20261128.md](../evidence/f2-fixed-20261128.md) | F2 修复验证（task-78 构建 patch 0032）：F2_FIXED——第一次 e2631net tx 3（pp）后 MAC TX frames 端口 2 = 3、网线出现 3 个 60 字节广播 ARP（源 00:41:71:00:00:50）；最终 fwd ctrl 0x00000011、MAC TX frames 0:0 1:0 2:12 3:0 4:0、12 个设备 ARP；vendor-alt 描述符变体未发送（独立观察，默认 pp 不受影响）；F1 KERNEL_STARTED 8.68 s；mtd0 f9239040… / 镜像区 b1ea9a48… 前后一致，唯一写入 userdata staging |
| [../evidence/f2-fixed/](../evidence/f2-fixed/) | F2 修复验证附件：session-results、原始串口字节与探针段、驱动日志、主机 tcpdump（12 个设备 ARP）、产物构建清单、sha256 清单 |
| [../evidence/e4-rescue-acceptance-20261128.md](../evidence/e4-rescue-acceptance-20261128.md) | E4 救援验收第一阶段（validate-only）run-1 RED -> run-2 PASS：run-2 用 patch 0033（33 patches，banner g30dca5f54503，tree cd67a041…）在 RAM 链上验证——GET / 页面 PASS（gzip 4456 B sha 8f16817b…，解压 9216 B sha 30a8f03e…）、/status PASS、`POST /flash?mode=validate` 返回 200 result=ok sha_match=ok（crc32 0x0721e716）、错误摘要负向 400 `sha256 mismatch` 且 stage 保持 idle；零 mtd0 写入（唯一写 userdata staging），F1 KERNEL_STARTED 8.68 s；run-1 的 400 `unsupported request` 根因（patch 0028 `rescue_name_is()` 头部大小写比较缺陷）与修复记录保留在 §5/§7/§11 |
| [../evidence/e4-rescue-acceptance/](../evidence/e4-rescue-acceptance/) | E4 救援验收附件：run-1（RED）preflight、串口/控制台原文、tcpdump 与 HTTP 行、页面 gzip/解压、原始响应、根因摘录、净零载荷摘要；run-2（PASS）同套 + 错误摘要负向响应 + 独立 sha256 清单 |
| [../evidence/e4-rescue-write-acceptance-20261128.md](../evidence/e4-rescue-write-acceptance-20261128.md) | E4 写模式验收（task-79）：E4 镜像（patch 0026-0033，banner g30dca5f54503）RAM 链上同一 rescue 会话完成 STEP-1 净零写（crc32 0x0721e716）与 STEP-2 E4 写（crc32 0x79ef8c50），/status done 后一次 Ctrl-C；独立回读 0x79ef8c50，env stored 0xF95A816E / region 0xe826c394，secondboot 0x9848a667；reset 回 flash E4 启动，postcheck mtd0 d87db54a…、区域 8a38896e…、PANICS=0、MT7916=1；冷启动 e2631rescue 首命令 FAIL（PHY -110，缺 refclk 初始化，patch 0034 修复队列）；驱动在 resident-rescue 阶段退出码 2，session-results 记录 ERROR；§12 最终 0034 第三写 PASS（mtd0 ac06d7bc…），flash 提示符救援页面+validate PASS；真冷启动（物理断电/上电，2026-11-28 09:12）GREEN，见 §13 |
| [../evidence/e4-rescue-write/](../evidence/e4-rescue-write/) | task-79 附件：驱动日志、串口原始字节、session-results、step1/step2 状态机响应、postcheck、final-0034 第三写/救援包、final-coldboot 真冷启动包、驱动与产物清单、sha256 清单 |
| [../evidence/e4-coldrescue-0034-20261128.md](../evidence/e4-coldrescue-0034-20261128.md) | patch 0034 冷启动救援顺序修复零写入真机验证（warm reset + RAM 加载）：从当前 flash E4 提示符加载 0034（banner g1673d5c89c7b，u-boot sha b7ea6bbc…）后 e2631rescue 作为第一条网络命令 —— PHY autoneg done、lan1 up 1 Gbps、GET / 页面 gzip 8f16817b…、/status idle、validate 200 result=ok sha_match=ok（crc32 0x1e5ff289）；Ctrl-C + e2631boot 回 Linux；mtd0 d87db54a… / region 8a38896e… 未变，15/15 checks GREEN；真冷启动需 0034 刷写后的第三写验收 |
| [../evidence/e4-coldrescue-0034/](../evidence/e4-coldrescue-0034/) | patch 0034 冷启动救援验证附件：results.json、驱动/串口/控制台、page/status/validate 响应、首跑失败输出、驱动与产物清单、sha256 清单 |
| [../evidence/recovery-button-research-20261128.md](../evidence/recovery-button-research-20261128.md) | 恢复键调研（task-80）：reset = flat GPIO 18（`&gpio1 2`）/ mesh = flat GPIO 20（`&gpio1 4`），均低有效（DTS、厂商板级表 entry[27]/[29]、ledkey_m 三方一致）；内核现状（reset 短按重启、按住 ≥5 s factory reset；mesh 仅 WPS 灯闪 120 s、无配对动作；hotplug 初始化即上报按下 → 「按住过启动」今天等于 factory reset）；厂商 U-Boot 只在 boot-mode shell 读 pin18（约 5.25 s 释放等待后跑 `downver version`+`reset`，本 payload 无 downver 命令 → 死代码，正常启动路径从不进入）；上游 `glbtn` 4 s 长按 → `httpd` 先例（需 DM_GPIO/button，本 U-Boot 40-60 行裸 MMIO 复刻）；选项 A/B/C/D 对照与推荐 A（reset 连续 2 s，`board_late_init` 内 RAM 改 bootcmd → `e2631rescue`）、实现草图、风险/零写入验证矩阵、SSH 证据缺口 |
| [../evidence/e4-v2-contract-design-20261128.md](../evidence/e4-v2-contract-design-20261128.md) | 救援 UI v2 模块契约（task-83）：新增 `/firmware`（槽位写，默认 next_slot=serial 最大，校验/守卫/擦整槽/写 body+版本头 serial+1/回读/失败擦头回退，逐条对齐 `e2631-fwslot`）、`/slots`、`/env`、`/backup`（mtd0 0x20000..0xC0000 + CRC32/SHA-256）、`/boot`（RAM 覆盖仅本次）、`/factory`（只擦按名核对的 `rootfs_data` 0x3360000/0x4A0000，双确认）；`/flash` v1 契约不变；写所有者矩阵（bootloader=e2631flash、槽=e2631fwslot、overlay=e2631factory、env 不暴露）、0x46100000 暂存区/上限 0x1BE0214、页面五标签/32 KiB 预算与 6144→32768 闸门顺序、task-84/81/85/86 交接与 10 项待 Lead 拍板 |
| [../evidence/failsafe-redesign-20261128.md](../evidence/failsafe-redesign-20261128.md) | E4 v2 救援页重做（task-81）：五标签（系统状态/固件更新/引导区/环境变量/恢复出厂）、上游 failsafe 形态（侧边栏+卡片+进度+注意事项，不搬资产）；页面 raw 34,069 B / gzip 10,962 B（限 32,768，gzip sha 36d9a176…），v1 /flash 契约不变、v2 端点按 task-83 契约；纯 JS SHA-256 对拍 node crypto、node tools/mock-failsafe.mjs 离线预览（127.0.0.1）；checker 107 PASS、make check 绿；**v2.1（task-88）扩为六标签**（新增串口台；环境变量白名单可写；引导区分区备份下拉），新增 `/console?cmd=`（单命令+stdout，无 stdin）、`POST /env`（仅 bootdelay/e2631_*，复用 e2631env 五步）、`GET /backup?part=`（5 分区只读），UBI/SIMG/I18N 明确不做、不设口令门；页面 raw 44,003 B / gzip 13,773 B（sha 496c5651…，限 32,768），mock 覆盖新端点，见 §10 |

| 文件 | 内容 |
|---|---|
| [01-情报汇总与事实核验-2026-10-13.md](01-情报汇总与事实核验-2026-10-13.md) | 事实总表：A 级=从字节重算，B 级=读到一次，C 级=推断；含包格式逐字段验证 |
| [02-实施计划-2026-10-13.md](02-实施计划-2026-10-13.md) | 工作日志（按节，含被证伪的假设——重试前值得先读） |
| [原厂加速方案逆向-2026-10-28.md](原厂加速方案逆向-2026-10-28.md) | PPE / NPP / IDM / TM 私有加速栈的逆向结论 |
| [原生无线驱动重写-2026-11-02.md](原生无线驱动重写-2026-11-02.md) | `native` 分支：不用 mt76，按原厂 4.1.25 二进制重写 WFDMA/MCU 层的过程与结论 |
| [wanlan-adaptive-逆向记录-2026-10-27.md](wanlan-adaptive-逆向记录-2026-10-27.md) | 原厂 WAN/LAN 自适应机制与手动 WAN 口实现的依据 |
| [有线吞吐测量-2026-10-29.md](有线吞吐测量-2026-10-29.md) | 有线吞吐 / 硬件卸载实测数据 |
| [p2-7-wifi-accel-评估-2026-10-28.md](p2-7-wifi-accel-评估-2026-10-28.md) | Wi-Fi 硬件加速路线评估 |
| [v1.5-驱动对齐与逆向移植报告-2026-10-28.md](v1.5-驱动对齐与逆向移植报告-2026-10-28.md) | v1.5 驱动对齐与逆向移植报告 |
| [refs-local/](refs-local/) | 早期本地调研笔记（原厂分区/挂载/硬件视图/槽位定案等，纯文本） |

## 版本记录

| 文件 | 内容 |
|---|---|
| [relnotes-v1.9.0.md](relnotes-v1.9.0.md) | v1.9.0：47 MiB userdata 自动接管、槽位布局扩到 17M、内置插件、homeproxy |
| [relnotes-v1.8.0.md](relnotes-v1.8.0.md) | v1.8.0 更新日志 |
| [v1.3-progress.md](v1.3-progress.md)、[v1.4-progress.md](v1.4-progress.md) | v1.3 / v1.4 阶段进展记录 |

## 维护约定

- `board/` 下的 `ser-*.log`、`firstboot-openwrt.txt` 是采集到的设备证据，**保留原样**（含旧品牌字样）。
- 迁移后的品牌为 `ImmortalWrt v1.10.0`、产物 `e2631-immortalwrt-*.bin`。T-12 起设备支持
  落在 [QC3284/immortalwrt](https://github.com/QC3284/immortalwrt) 的 `e2631` 分支；套件
  不再包含 overlay / patch series / `apply.sh`，旧基底通道已退役，见
  [immortalwrt-migration.md](immortalwrt-migration.md)。
- 结论变更需附新证据并更新 [immortalwrt-migration.md](immortalwrt-migration.md) §7.1 与
  [known-issues.md](known-issues.md) 对应条目。
