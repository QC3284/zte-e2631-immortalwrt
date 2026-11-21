# 厂商 U-Boot PCIe 初始化链逆向 —— A5 "Device not found" 根因与 patch-0013 评审

- 日期：2026-11-22
- 任务：task-57 跟进（Lead m03343，P2 紧急）：厂商 U-Boot PCIe 初始化链逆向
- 性质：只读静态分析（capstone 反汇编）。未接设备、未改源码、未提交（待 Lead 审阅）
- 结论一句话：A5 镜像（patch 0001-0012）不含"厂商晚驱动 GPIO 2/51 拉高"这一步（patch 0013），而 patch 0012 的板级表会把这两根线显式拉低；两根线正是两个 MT7916 端点的复位/使能线（工作假设），所以 A5 链上"两个 RC 根端口都在、端点全无"是确定性结果，不是竞态。另外 patch-0013 当前有一个会让 U-Boot 编译失败的括号缺陷，且缺少厂商的 4 ms 间隔，详见第 7 节。

## 0. 结论摘要（按证据强度排序）

- R1（已证实）厂商把 GPIO flat 2（bank0 line2）和 flat 51（bank3 line3）先按板级表拉低，随后在 zte_gpio_init() 末尾分两轮循环拉高，中间有 4 ms 延时。调用点在 board_init_r()（0x47f01614 bl 0x47f2f314），不在 cspboot 命令路径里；cspboot/pdt 路径没有任何 GPIO 调用。这两根线最合理的工作假设是"两个 PCIe 端点（MT7916 系列）的复位/使能"，一根线对一个端点。
- R2（已证实）A5 正式镜像（run 44929440623，u-boot.bin sha256 e3c52ba4132910b1…，token U-Boot 2027.01-rc2-g9a7538311376）的 UBOOT-INFO 里 "Port patches sha256" 恰好 12 个哈希，与本地 uboot-port/patches/0001…0012 一一对应；patch 0013（本地 sha256 7dc49eb987e7e17a…）不在其中（0013 文件时间 01:59 晚于 A5 构建时间 17:20:55，当时还是 untracked）。所以 A5 链从不把 2/51 拉高。
- R3（已证实）patch 0012 的 e2631_gpios[] 数组包含 {51,0},{2,0}，e2631_pinmux_gpio_init() 在表循环里用 CLR 把两根线拉低；之后没有晚驱动。A5 的 residual dump 正好显示 our 侧 bank0 DATA bit2=0、bank3 DATA bit3=0（vendor 侧为 1），与该代码路径一致。
- R4（已证实）厂商 U-Boot 没有任何 PCIe 控制器/RC 寄存器初始化：没有 pci 命令（43 条 help 里无 pci），没有 pcie 字符串，对 RC 基址 0x0f000000/0x0f100000、ctrl 0x09500000/0x09600000、配置窗 0x1c000000/0x2c000000、CRM2 gate/reset 0x94100070/74 均无访问。它只做 SerDes/参考时钟（patch 0012 已复刻）+ 这两根 GPIO；RC 控制器初始化是内核驱动的职责。=> 除 patch 0013 外，没有别的厂商 PCIe 初始化需要补。
- R5（已证实）0x94400018 bit11 属于 SPI-NAND/SPIFC 初始化（函数 0x47f1f6ec），与 PCIe 无关；我们的链不写它、flash 仍正常，可忽略。0x94100024 厂商从未写过，是伪线索。
- R6（重要）"同一 patch-0012 镜像早先自动启动曾经枚举到端点"这个观察在磁盘证据里找不到对应日志：所有枚举到 14c3:7906/790a 的日志都属于 vendor U-Boot 先跑的链（RAM 链）或 patch 0012 之前的镜像（如 token g2797f3dd3860，见 evidence/c1b0-entry/serial.txt:178/192/218/232：两条链路 link up + 两个端点 + 四 PHY）。这些旧镜像没有 patch 0012 的 GPIO 表，端点复位线继承 vendor 链的"高"状态，所以能枚举；A5 首次把这两根线拉低，于是"翻车"。这解释了两类运行结果的翻转，属于镜像内容差异而非竞态。请 Lead 核对当时那次运行的 U-Boot token。
- R7（缺陷）patch-0013 当前会把 e2631_pinmux_gpio_init() 的收尾右花括号删掉而不补回（diff 里只有减号那一行，全补丁没有任何补回右花括号的行；当前 e2631net.c 花括号计数 46/45），U-Boot 编译必然失败。且两次拉高之间没有厂商的 4 ms 间隔。最小修正见第 7 节。

## 1. 输入与地址换算

- 厂商 U-Boot 二进制：e2631-immortalwrt/evidence/p2-oob/vendor-uboot-ram.bin，426,048 B，sha256 a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30。
- 换算：vaddr = 0x47F00000 + 文件偏移；mtd0 偏移 = 文件偏移 + 0x20800。
- A5 构建：/home/qc233/zte/e2631-t5-artifacts/uboot-a5-44929440623/e2631-uboot-44929440623/：u-boot.bin 450,904 B sha256 e3c52ba4132910b1807708eadfc8a6f7c7b9740782e84df6afa6d2e7a861ecf2；UBOOT-INFO.txt 的 "Port patches sha256" 12 项 = 0001..0012；banner 日期 "Nov 21 2026 - 17:20:55 +0000"。
- A5 运行证据：/home/qc233/zte/e2631-p3/c1b1fix/a5-refclk/run-3/{serial.log,session-results.json,preflight.json,residual-vs-vendor.txt}；同目录 run-1/run-2 为 RAM 链（loadx 到 0x47f00000 后 go）；console-1/、pci-probe/ 为该镜像的后续探测。
- 对照日志：evidence/c1b0-entry/serial.txt（旧镜像 + vendor 链，端点枚举成功）、/home/qc233/zte/e2631-serial-boot-002.log（原厂完整启动，两条链路 0.609/0.719 s link up，端点 7906/790a，line 420-421 wifi-on）。
- 内核侧：iwrt-tree/target/linux/zx279128/files/drivers/pci/controller/dwc/pcie-zx279128s.c（第 86-101 行的板级 reset/enable 时序、第 224/233 行的 reset-gpios/enable-gpios 可选获取）；target/linux/zx279128/dts/zx279128s-zte-zxhn-e2631.dts（241-260 行，pcie0 仍是 H3600 猜测的 reset-gpios = <&gpio3 5> / enable-gpios = <&gpio3 7>）。

## 2. 厂商晚驱动 GPIO 的精确代码（问题 1 的答案）

### 2.1 调用位置：board_init_r，不是 cspboot

- board_init_r 0x47f015c0；其 0x47f01614 处 bl 0x47f2f314 调 zte_gpio_init。同一序列里随后还有 bl 0x47f205d0、环境/时钟/NAND 初始化，最后 eth_initialize 0x47f2b914 -> board_eth_init 0x47f00850（其 4 个 helper：0x47f1fe38、0x47f30b54、0x47f2fe38 = 参考时钟/SerDes、0x47f20444）。
- 对全部 28 处 GPIO 低层调用点做过扫描：除了 GPIO 命令实现区（0x47f2dc*，详见 2.3）外，全部集中在 zte_gpio_init 0x47f2f314-0x47f2f6c0；cspboot / pdt_cspboot_init / pdt_cspboot_run / zteboot_* 路径里没有任何 GPIO 调用。因此"cspboot 在 board init 之后又驱动了 2/51"应更正为：zte_gpio_init() 自己在 board_init_r 里就做了，早于 board_eth_init 和 console。

### 2.2 板级表与两轮晚驱动（0x47f2f61c 起）

板级行：product_vid=31（E1630）行基址 0x47f44e54；[row+0x58]=52（条目数），[row+0x60]=[row+0x64]=0x47f59b28（条目数组）；条目 28 B：+0x00 pin、+0x04 dir（1=输出）、+0x08 value、+0x0c valid。相关条目：

| 表索引 | pin | dir | value | 说明 |
|---|---|---|---|---|
| 47 | 55 | out | 0 | 未知低输出（H3600 曾猜 gpio3 7 enable，未证实） |
| 48 | 52 | out | 0 | 未知低输出 |
| 49 | 54 | out | 0 | 未知低输出 |
| 50 | 51 | out | 0 | 晚驱动拉高（flat 51 = &gpio3 3） |
| 51 | 2 | out | 0 | 晚驱动拉高（flat 2 = &gpio0 2） |

晚驱动代码（逐条实测）：

| 地址 | 指令 | 作用 |
|---|---|---|
| 0x47f2f61c | mov r5,#0 | 循环 A 索引=0 |
| 0x47f2f624-0x47f2f640 | 取 board 行、count、entry 数组、valid | 遍历条目 |
| 0x47f2f64c-0x47f2f654 | ldrb r0,[r0,#4] / cmp r5,#0x33 / cmpeq r0,#1 | 索引=0x33（=51）且输出 |
| 0x47f2f65c | ldr r0,[r3,r2] | r0 = 表[51].pin = 2 |
| 0x47f2f660 | bl 0x47f2dcf4 | gpio_set(2, 1)（r1 仍为 1） |
| 0x47f2f66c-0x47f2f674 | mov r0,#4 / bl 0x47f256b8 | 4 ms 延时（见 2.3） |
| 0x47f2f678-0x47f2f6b4 | 循环 B 同上 | 索引=0x32（=50）且输出 |
| 0x47f2f6b8 | bl 0x47f2dcf4 | gpio_set(51, 1)（pin 来自表[50]） |
| 0x47f2f600-0x47f2f618 | bl 0x47f2f24c / str / print | 计算 bootsel 打印后返回 |

要点：
1. 两轮循环是先 pin 2 拉高 -> 4 ms -> pin 51 拉高；表里的 0 值先被主循环按"输出低"写下去，晚驱动再覆盖为高。
2. gpio_set 0x47f2dcf4 的实测语义：基址来自全局指针 *(0x47f42a6c)（初值 0x94407000），bank = (pin>>4)<<6（0x40 步进），line = pin & 0xf；value!=0 -> 读 [bank+0x18](SET) 或上 bit 写回；value==0 -> 读 [bank+0x1c](CLR) 或上 bit 写回。即 SET/CLR 都是读写-或-写回。
3. 方向寄存器：gpio_dir_out 0x47f2dd5c 对 [bank+0x00](DIR) 置 bit；gpio_dir_in 0x47f2dd34 清 bit。晚驱动不再改方向（主循环已置输出）。
4. 主循环对每个输出还有"置方向后 1 ms、写值后 1 ms"的延时；patch 0012 没复刻这两处 1 ms（影响很小，补上更贴近原厂）。

### 2.3 延时单位确认

- 0x47f256b8(n)：循环 n 次，每次 mov r0,#0x3e8（1000）后 bl 0x47f25688。
- 0x47f25688(us)：把参数按 <=0x493e0（300000）分块，bl 0x47f010c4（udelay）逐块延时，总时长 = 参数微秒。
- 因此 mov r0,#4 + bl 0x47f256b8 = 4 ms，与"两次拉高之间 4 ms"一致。

## 3. 两根引脚的身份（问题 4 的答案）

- flat 编号 = bank*16 + line（GPIO 基址 0x94407000，bank 步进 0x40）：
  - flat 2 = &gpio0 2（bank0 bit2）——不是 LED、不是按键；
  - flat 51 = &gpio3 3（bank3 bit3）——不是 H3600 用的 &gpio3 5 / &gpio3 7。
- A5 residual-vs-vendor 的 10 个字差异中，与 GPIO 相关的 4 个正好对应这两根线：
  - 0x94407014 bank0 DATA：our 0x0000db28，vendor 0x0000db2c（bit2 差）；
  - 0x94407020 bank0 +0x20：our 0x00000100，vendor 0x00000104（bit2 差）；
  - 0x944070d4 bank3 DATA：our 0x0000e020，vendor 0x0000e028（bit3 差）；
  - 0x944070e0 bank3 +0x20：our 0，vendor 0x8（bit3 差）。
- +0x20 不是我们驱动写的：它是 SET/CLR 之后的"输出数据镜像"（读回语义）。证据：两条链 bank0 +0x20 的 bit8 都为 1（pin 8 板级表拉高）、被 CLR 拉低的 pin 都不置位，而 vendor 只在晚驱动 SET 后才出现 bit2/bit3。=> 重新拉高这两根线后，+0x20 的差异会自动消失。
- 功能判断：厂商二进制没有字符串/注释说明这两根线；原厂 E2631 DTS 的 PCIe 节点也没有 reset/enable GPIO（见 docs/refs-local/E2631原厂硬件视图-2026-10-12.txt:57/:219）。结合"两条链路各挂一个 7906/790a 端点、两根线一先一后拉高、且 A5 拉低后两个端点都消失"，工作假设为每个端点一根复位/电源使能线；不排除其中一根是公共 power enable、另一根是 PERST# 释放（4 ms 顺序即为 power->reset）。要原理图/示波器才能定死。

## 4. 问题 2：0x94400018 bit11 与 0x94100024

### 4.1 0x94400018 bit11 = SPI-NAND/SPIFC 初始化，与 PCIe 无关

- 写入点在 0x47f1f7a8-0x47f1f7b8，函数 0x47f1f6ec（调用者 0x47f174dc / 0x47f17504 = nand_init 路径）。该函数同时含字符串 "failed to allocate data->bi_table structure."（0x47f3e608）、"manuid=%x,%x"，并写 SPIFC 块 0x94406000；同一段代码还写 0x94200008 |= 0x05550000（pinmux）、0x9400000c bits[21:20]=0b01。
- 实测指令：ldr r3,[r2,#0x18]（r2=0x94400000，由 0x94000000+0x400000 得到）-> bic r3,#0x1f800 -> orr r3,#0x800 -> str r3,[r2,#0x18]，即 bits[16:11] = 0b000001，bit11 置 1。
- 结论：这是 LSP0（NAND 控制器）的时钟/引脚配置字段；我们的链不写它，SPI-NAND 读写仍正常（mtd0 读写/启动均正常），所以与 "Device not found" 无关，不需要补。

### 4.2 0x94100024：厂商从未写

- 全镜像字面量扫描：CRM2 基址 0x94100000 只出现两次（0x47f1ffa8、0x47f2fed8 两个字面量槽），对应两处代码：
  - 0x47f2fe38（board_eth_init 的第 3 个 helper，refclk/SerDes）尾部 0x47f2fe9c-0x47f2fec8：写 0x94100010（清 bit11，bits[9:6] <- (0x9a107008>>24)&0xf）——patch 0012 已复刻；
  - 0x47f1ff8c：读写 0x94100078（读、bic 0xf8、orr 0xa0、写，然后 b 0x47f00674 延时 200 ms），但全镜像找不到它的 bl/blx 调用者，实际不可达/未被使用。
- 0x94100024 没有任何访问（字面量与"基址+0x24"两种形式都查过）。内核侧 PCIe 用的是 CRM2 的 clock gate 0x94100070 与 reset 0x94100074（由 CCF/reset 驱动管理），也不是 0x94100024。
- 结论：0x94100024 是伪线索，无需写。

## 5. 问题 3：厂商 U-Boot 没有任何 PCIe RC 初始化

- 命令表（help 输出，43 条）无 pci 命令；全镜像无 pcie 字符串。
- 对以下基址做"4 字节对齐字面量"扫描，命中数均为 0：0x0f000000、0x0f100000、0x09500000、0x09600000、0x1c000000、0x2c000000。原始 find 命中的 34/75/64 处都是未对齐的数据/ASCII，例如 0x47f314c4 处上下文 0c000000 0f000f00 01000000，不是代码引用的字面量。
- 厂商 PCIe 相关工作只有：patch 0012 已复刻的 SerDes 表（0x9fe00000）+ 参考时钟（0x94000050/54、0x94000008、0x94100010、0x9400004c、0x9a100004）+ 本报告的 GPIO 晚驱动。
- 结论：内核 pcie-zx279128s 驱动负责 RC 初始化/链路训练；排除"还有一段厂商 RC 初始化没搬"这一可能。

## 6. 判断：A5 为什么两个端点都没有

### 6.1 A5 镜像构成（硬证据）

UBOOT-INFO.txt 的 "Port patches sha256" 12 项与本地 sha256 逐项相符：0001 1e051c22…、0002 71fdce39…、0003 d16e7b56…、0004 ce6a01ef…、0005 43dcac25…、0006 35ba682a…、0007 bf54aa98…、0008 d75f809f…、0009 4bf75d5a…、0010 57ce9d80…、0011 98aa4b39…、0012 9c075c60…；0013 本地 hash 为 7dc49eb987e7e17a…，不在列表。A5 banner 时间 17:20:55；0013 文件时间 01:59（次日），当时尚未提交。

### 6.2 代码路径与观测一致

- patch 0012：e2631_gpios[] = { {8,1},{40,1},{60,0},{55,0},{52,0},{54,0},{51,0},{2,0} }；e2631_pinmux_gpio_init() 用 CLR 把 51 和 2 拉低；e2631_net_refclk_init() 在 e2631boot 的 if (load) 分支里调用，因此从 flash 或 RAM 链只要走 e2631boot 都会执行。
- A5 实测：f000000.pcie: Device not found（1.489 s）、f100000.pcie: Device not found（2.579 s）；两个 RC 根端口 [1cf2:6830] 在 0000:00:00.0/0001:00:00.0 正常枚举；无 7906/790a；对内 PHY 正常（mdio 0a-0d，2.72 s），以太网已修好（lan1 link up 14.6 s）。
- vendor 链实测：0.609/0.719 s 两条 "PCIe Gen.1 x1 link up"，端点 7906（bus0）/790a（bus1），四 PHY，wifi-on 成功；其 GPIO 状态为 2/51 高。
- 所以差异只剩这两根线：我们的链把它们固定在低电平，端点处于复位/掉电状态；RC 控制器本身和 PHY 都是好的。两根线一拉低，两个端点同时消失，与"一根线对一个端点"的假设自洽。

### 6.3 "翻转"的解释与待核对项

- 磁盘上所有枚举到 14c3:7906/790a 的日志都是：
  - vendor U-Boot 先跑、内核由旧版我们的 U-Boot（无 patch 0012 GPIO 表，token g2797f3dd3860，2026-11-21 11:20 构建）引导：evidence/c1b0-entry/serial.txt:21 vendor banner -> :138 go 0x47f00000 -> :142 我们的旧 banner -> :178/192/218/232 两条 link up + 两个端点 + 四 PHY；
  - 或其它 vendor-first 链（c1a-bootm/run-2、c1b1a-rehearsal、c1b1-diag/phaseb-3、vendor-compare、md-dump）。
- 对 token g9a7538311376（A5 镜像）的磁盘日志，没有任何一份出现 14c3:7906/790a；run-3/console-1/pci-probe 全是 Device not found。
- 因此最可能的事实是："早先能枚举"的运行用的是旧镜像或 vendor-first 链（旧镜像不驱动 2/51，端点复位线继承 vendor 的高电平），而非同一 A5 镜像的竞态。请核对当时那次运行的 U-Boot token/启动路径；如果确为 g9a7538311376 且走 e2631boot，则除 R1 外还有第二个变量（端点电源/PERST 时序），需要在 patch 0013 之后用冷启动+热复位 A/B 再查。

## 7. patch-0013 评审与最小补丁建议（给 base-builder）

### 7.1 缺陷 1（阻断）：补丁删掉了函数收尾的右花括号

- 文件：uboot-port/patches/0013-board-zte-drive-the-two-late-GPIO-lines-high.patch（当前 untracked，sha256 7dc49eb987e7e17a7f75d73ca9d4f82fa2e4ad7f891e92134c6c6fe54e957175）；对应源码 uboot-src/board/zte/zxhn-e2631/e2631net.c（HEAD f4466dba）。
- diff 的 hunk @@ -187,7 +205,15 @@ 里删除了原函数的右花括号，而整个补丁没有任何补回右花括号的行；源码花括号计数 46 个左、45 个右（不配对）。结果是 e2631_pinmux_gpio_init() 没有收尾，后面的函数定义变成嵌套函数，U-Boot 编译报错（function definition is not allowed here 一类）。
- 修正：两条 e2631_gpio_drive(...) 之后、/* The vendor ref_clk_set(0) ... */ 注释之前，补回一个右花括号。修正后按 uboot-port/commits.env 流程重算 patch sha256 与 post-am tree sha，uboot-build.yml 会用 tree sha 校验。

### 7.2 缺陷 2：缺少厂商的 4 ms 间隔

- 当前补丁把 2 和 51 连续拉高；厂商是 pin2 高 -> 4 ms -> pin51 高。若两根线分别是 power enable 与 reset（或反之），顺序/间隔不可省。建议：e2631_gpio_drive(2, 1); mdelay(4); e2631_gpio_drive(51, 1);
- 如要更贴近原厂，主表循环里每根输出"置方向后 1 ms、写值后 1 ms"也可补（厂商代码里有 1 ms 调用），但对 PCIe 端点不是关键。

### 7.3 建议的可选诊断命令（便于下次设备会话取证）

在 e2631net.c 加一个只读命令（如 e2631gpio），在 e2631boot 前后打印：0x94407000(bank0 DIR)、0x94407014(bank0 DATA)、0x94407018(SET)、0x9440701c(CLR)、0x94407020(+0x20 镜像)，以及 bank3 的 0x944070c0/0xd4/0xd8/0xdc/0xe0。便于在 prompt 处确认 2/51 已为高，并把 A6 证据留在串口日志里。

### 7.4 验证计划（设备步骤仍需用户批准；本报告不接设备）

1. 修正 7.1/7.2 后出 A6 镜像（patch 0001-0013），CI 的 uboot-build 与 kit 的 hash 门禁须绿。
2. 按既有 C1b-1 流程写 mtd0（先备份/核对 sha256，写后 readback 比对），冷启动。
3. 期望内核日志：两条 zx279128s-pcie ... PCIe Gen.1 x1 link up；pci 0000:01:00.0 [14c3:7906]、pci 0001:01:00.0 [14c3:790a]；四 PHY 9a101000.mdio:0a..0d；wifi-on 正常。
4. 在 U-Boot prompt 用 md 复核：0x94407014=0x0000db2c、0x944070d4=0x0000e028、0x94407020=0x00000104、0x944070e0=0x00000008（与 vendor 一致）。
5. 冷启动通过后再做热复位重复一次（检验端点复位/电源时序是否经得起 warm reboot）；如热复位偶发失败，再加大释放后的稳定延时（如 10/50/100 ms）做参数扫描。
6. 回退：串口 loadx 载入上一版 mtd0 镜像 -> mtd write spi-nand0 ... 0x20000 0xA0000 -> mtd read+cmp（沿用 C1b-1 既有通道；vendor nand write.uboot 仍不可依赖）。

### 7.5 若 A6 仍无端点（备选）

- 先确认 2/51 确实被拉高（7.3 的 dump）、端点供电轨/PERST 极性；
- 扫 4/10/50/100 ms 释放延时；试"先低 100 ms 再高"的上电复位序列；
- 最后才考虑 H3600 的 flat 53/55 猜测（厂商板级表根本没有 flat 53；patch 0012 已把 flat 55 拉低，而内核 DTS 又把 55 当 enable 拉高——见 7.6，这两个猜测互相矛盾，优先级最低）。

### 7.6 顺带发现：内核 DTS 的 reset/enable 猜测会主动驱动 53/55

- pcie-zx279128s.c:86-101：host_init 在第一次 probe 时对可选的 reset-gpios/enable-gpios 做 reset=1 -> 100 ms -> reset=0 -> enable=1 -> 200 ms 的时序（zx279128s_board_released 只跑一次）；第 224/233 行以 GPIOD_ASIS 可选获取。
- 板级 DTS（zx279128s-zte-zxhn-e2631.dts:249-255）仍带 H3600 猜测：reset-gpios = <&gpio3 5>（flat 53，厂商板级表里没有）、enable-gpios = <&gpio3 7>（flat 55，厂商表里是输出低、晚驱动也不拉高）。
- 影响：A5 链上内核把 55 拉高、53 做了一次复位脉冲，而厂商内核完全不做这两步（原厂 E2631 DTS 无这些属性）；这既可能是无效动作，也可能在真线上产生冲突。建议在 patch 0013 验证通过后，把这两个猜测属性从板级 DTS 删除（让 U-Boot 的 2/51 晚驱动成为唯一复位/使能动作，与厂商一致）；若将来能确认 53/55 的真实用途，再按实测补回。

## 8. 风险与开放问题

- Q1：2/51 的物理功能（端点复位/电源使能/别的）——需要原理图或示波器；当前只能凭"拉低即两个端点都消失"推断。
- Q2："早先枚举"的确切运行 token/启动路径——请 Lead 核对（本报告在磁盘上找不到 A5 token 的枚举日志）。
- Q3：4 ms 间隔是否足够/必要；热复位下端点是否会掉——A6 冷/热各验一次。
- Q4：内核 DTS 的 53/55 猜测删除后是否影响 pcie probe（应无：devm_gpiod_get_optional 返回 NULL，host_init 跳过板级时序）。
- Q5：如果 A6 后单端点成功、另一个失败，则说明两根线不是一一对应，需要交换/拆分时序再试。
- 风险：写 mtd0 仍是最高风险动作（首启失败只能靠串口 loadx 或编程器）；A6 验证前必须先备份当前 mtd0 并核对 sha256。

## 9. 复现方法（本次用的只读脚本）

- Python + capstone 5.x：PYTHONPATH=/tmp/pylibs python3
- 关键步骤：
  1. Cs(CS_ARCH_ARM, CS_MODE_ARM) 对 vendor-uboot-ram.bin 反汇编，vaddr = 0x47F00000 + off；
  2. 对 0x47f2f5e0-0x47f2f6e0 反汇编得到第 2 节的晚驱动序列；对 0x47f2dcf4/0x47f2dd34/0x47f2dd5c 反汇编得到 GPIO 低层语义；
  3. 读板级表：row=0x47f44e54，count=[row+0x58]，array=[row+0x60]，entry stride 0x1c，逐条打印 pin/dir/value/valid（结果见 2.2 表）；
  4. 字面量扫描：struct.pack("<I", addr) 在文件中查找，只接受 4 字节对齐命中（排除数据/ASCII 的未对齐假命中）；
  5. 延时语义：0x47f256b8 -> 0x47f25688 -> 0x47f010c4(udelay) 的调用链 + 0x493e0 分块字面量。
- 所有结论均可由上述脚本在不接设备的前提下重放；本报告未修改任何源码/镜像。
