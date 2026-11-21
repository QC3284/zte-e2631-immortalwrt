# 无厂商 U-Boot 链路的网络缺失定位（P2 / 2026-11-22）

- 任务来源：Lead m03179（urgent，只读静态分析）+ m03256（聚焦参考时钟/SerDes）
- 分析人：iwrt-baseline
- 约束：只读（不连设备、不写 flash、不改源码、不提交本文件）；结论待 Lead 审阅
- 关键输入：
  - 厂商 U-Boot payload：/home/qc233/zte/e2631-immortalwrt/evidence/p2-oob/vendor-uboot-ram.bin
    （426,048 B，sha256 a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30）
    虚拟地址 = 0x47F00000 + file_off；mtd0 偏移 = file_off + 0x20800
  - 成功链（厂商 U-Boot 先跑，RAM 链）：evidence/c1b0-entry/serial.txt
  - 失败链（无厂商 U-Boot，flash 直启）：/home/qc233/zte/e2631-p3/c1b1fix/session-a/run-1/serial.log
  - 厂商库存启动日志：/home/qc233/zte/e2631-serial-boot-002.log
  - 内核树：/home/qc233/zte/iwrt-tree/target/linux/zx279128/

## 0. 结论摘要

现象回顾：无厂商 U-Boot 时内核能起（CP15 修正已生效），但
zx279128s-eth 92000000.ethernet: error -ENODEV: port 0: PHY connect failed（2.704 s），
随后 phylink.c:2716 的 RTNL 告警；两个 PCIe 控制器均 Device not found
（f000000 @1.549 s、f100000 @2.559 s），MT7916 无法枚举，无 lan/wan 网口；
所有"厂商 U-Boot 先跑"的 RAM 链启动都网络正常（四颗 PHY 9a101000.mdio:0a..0d 正常应答，
两条 PCIe Gen.1 x1 链路 up，端点 14c3:7906 / 14c3:790a）。

本次定位结论（按可能性排序）：

- **F1（主因，高置信）**：厂商 U-Boot 在 board_eth_init 里执行一段"网络 PHY/SerDes 参考时钟"
  初始化（ref_clk_set → pll_cfg_fractional → 拨 0x94000008 → 写 SerDes 模拟块 0x9FE00000
  → 修 0x94100010 → 置 0x9400004C/0x9A100004），我们的 U-Boot 完全没有这段；
  内核侧没有任何驱动/时钟节点能补（见 §4）。这正好解释"MDIO 时钟在跑但四颗 PHY 全不应答、
  两条 PCIe 端点全缺失"——外部 PHY 与 PCIe 端点的参考时钟从未被打开。
- **F2（次要，中置信）**：厂商在 zte_gpio_init 里把 5 个用途未知的引脚（flat 55/52/54/51/2）
  驱动为低，并把 pinmux 0x94200000 的若干位置位；我们的 U-Boot 不做。若这些脚是 PHY/PCIe 的
  模式/使能 strap，则缺少它们也会影响链路。建议 patch 0012 顺带复刻（与厂商同板同值，风险低）。
- **F3（排除项）**：GPIO 8/40/60 只是三颗 LED（厂商表与内核 DTS 完全一致），不是 PHY/PCIe 复位线；
  flat 53（我们 DTS 里 pcie0 的 reset-gpios）厂商表根本未触碰，reset-gpios/enable-gpios
  是从 H3600 抄来的猜测（见 §5.3、§6）。
- **F4（排除项）**：product_vid=31 / vid=31-E1630 只是 8 根 strap 算出的板型编号，用于选板级 GPIO 表，
  不写任何寄存器/efuse，内核全树无人读取，不可能是网络主因（见 §7）。
- **F5（排除项）**：启动选择 bootsel=3 来自 0x94000040 的采样，与网络无关。

## 1. 两条链差异点：厂商 eth_initialize 必然执行

厂商 board_init_r 0x47f015c0 在 0x47f0167c 无条件调用 eth_initialize 0x47f2b914；
eth_initialize 从字面量池取出 board_eth_init 指针 0x47f00850（字面量 0x47f2ba9c，
检查点 0x47f2b954）。board_eth_init 0x47f00850 顺序调用 4 个 helper：

| 顺序 | 地址 | 作用 |
|---|---|---|
| 1 | 0x47f1fe38 | 注册 MDIO 驱动（名字 279112mdio，读写回调 0x47f1fbd8 / 0x47f1fcc4） |
| 2 | 0x47f30b54 | 分配 eth 设备（eth0，MAC 取环境变量 ethaddr） |
| 3 | **0x47f2fe38** | **网络 PHY/SerDes 参考时钟初始化（F1 主体）** |
| 4 | 0x47f20444 | 0x9400004C bits[8:0] 与 0x9A100004 |

这些都在厂商控制台出现之前完成。成功链日志 evidence/c1b0-entry/serial.txt:62-69 原文：

    Net:   enter ref_clk_set.. mode = 0 .
    enter pll_cfg_fractional
    ref_clk_set success!
    gpon serdes init
    rxpll_ready
    addr 0x9400004c before value is 38000
    addr 0x9400004c after value is 381ff
    eth0

失败链日志里整个 Net: 段不存在——因为厂商 U-Boot 从未运行。

## 2. F1 主体：0x47f2fe38 的精确写序列

### 2.1 ref_clk_set(mode=0)（0x47f2fbc4，调用点 0x47f2fe44）

- 打印 enter ref_clk_set.. mode = %d .（字符串 0x47f3fa1f）。
- 读 0x94000050，清 bit31（0x80000000），写回。
- mode 0 走"分数分频 PLL"分支（0x47f2fc10-0x47f2fc2c），调用
  pll_cfg_fractional 0x47f2f8bc，参数：base=0x94000050, arg1=1, arg2=0x5D, arg3=0x004FDF3B,
  arg4=5, arg5=3。
- 返回后 mdelay(50)（mov r0,#0x32; bl 0x47f256b8），打印 ref_clk_set success!（0x47f3fa40）。
- 注：另一分支（mode & ~2 == 1，即 mode 1/3）调用 0x47f2f73c，本机不是该路径。

### 2.2 pll_cfg_fractional（0x47f2f8bc）的精确写

打印 enter pll_cfg_fractional（0x47f3f9cb）；arg2 <= 0x13 时告警
feed back divide value is %d < 20（0x47f3f9e5）。

对 0x94000050（PLL cfg0，读-改-写）：
- 置 bit31，清 bit27（0x08000000）、bit24（0x01000000）；
- bits[23:18] = arg1 = **1**；
- bits[17:6] = arg2 = **0x5D**（FBDIV=93）；
- bits[5:3] = arg4 = **5**（PD1）；
- bits[2:0] = arg5 = **3**（PD2）。

对 0x94000054（cfg1）：
- 中间依次清 bit27、置 bit26、清 bit25、清 bit24（随后被覆盖）；
- 最终 [0x94000054] = (old & 0xFF000000) | 0x004FDF3B（低 24 位 = FRAC）。

随后 mdelay(100)，最后清 0x94000050 的 bit31（PLL 使能）。

净结果：

    0x94000050 = (old & 0x76000000) | 0x0004176B
    0x94000054 = (old & 0xFF000000) | 0x004FDF3B

字段布局与内核 clk 驱动的 PLL 模型一致（PLL_FBDIV GENMASK(17,6)、PLL_PD1 GENMASK(5,3)、
PLL_PD2 GENMASK(2,0)、第二寄存器 PLL_FRAC GENMASK(23,0)），**唯一例外是 bits[23:18]=1
这个 6 bit 字段内核模型没有定义**，说明它不是内核登记的那两颗 PLL（A9 0x18 / AUDIO 0x28）。

### 2.3 拨 0x94000008 的 bit5 / bit4

    0x94000008: 清 bit5 (0x20)、清 bit4 (0x10)  → 写回
                delay 100（0x47f2fe64 -> bl 0x47f25688）
                置 bit5                        → 写回
                delay 100（0x47f2fe78）
                <写 §2.4 SerDes 表>
                置 bit4                        → 写回（0x47f2fe88-0x94）

最终 bits4/5 = 1，其余位保持原值。0x94000008 内核未建模（内核 topcrm 里
TOP_CLK_SEL=0x0c、TOP_CLK_EN=0x14、TOP_PLL_A9=0x18、TOP_PLL_AUDIO=0x28、TOP_USB_EN=0x48），
所以位 4/5 语义未定（见 §9 Q2）。

### 2.4 SerDes/模拟块 0x9FE00000（0x47f2fc58，调用点 0x47f2fe7c）

按 +0x00…+0x5C 顺序共 24 个写（最终值；+0x40 先写 0x003C0000 再写 0x003C0040）：

| 偏移 | 值 | 偏移 | 值 |
|---|---|---|---|
| +0x00 | 0x800010A7 | +0x04 | 0x0000000F |
| +0x08 | 0x00000540 | +0x0C | 0x00000004 |
| +0x10 | 0x00000000 | +0x14 | 0x018A6400 |
| +0x18 | 0x08B50140 | +0x1C | 0x01216000 |
| +0x20 | 0x40000000 | +0x24 | 0x0B570001 |
| +0x28 | 0x00000000 | +0x2C | 0x00000000 |
| +0x30 | 0x20242000 | +0x34 | 0xC0593D44 |
| +0x38 | 0x0000042F | +0x3C | 0x00000000 |
| +0x40 | 0x003C0040（先 0x003C0000） | +0x44 | 0xEAC0A013 |
| +0x48 | 0x101038CA | +0x4C | 0x0005A000 |
| +0x50 | 0x33333333 | +0x54 | 0x33333333 |
| +0x58 | 0x03E23333 | +0x5C | 0x00040244 |

写完打印 gpon serdes init（0x47f3fa69）。同族函数 0x47f2fd4c 是 mode 分支
（epon serdes init 0x47f3fa56 写同一块的不同值），本机路径**不调用**它。
0x9FE00000 与 0x94000000/0x94100000/0x9A100000 是彼此独立的块。

### 2.5 CRM2 0x94100010 修正

    清 bit11 (0x800)；
    bits[9:6] (0x3C0) = ( [0x9A107008] >> 24 ) & 0xF

即用 0x9A107008 的高 4 bit 作为 CRM2 0x10 的 [9:6] 字段。rxpll_ready 打印
（0x47f3fa7c）在 0x94000008 bit4 置位之后、本段 CRM2 写之前。

### 2.6 0x9400004C 与 0x9A100004（helper 4，0x47f20444）

    读 0x9400004C，打印 'addr 0x9400004c before value is %0x'（0x47f3e6da）
    写 (= old & ~0x1FF) | 0x1FF      → 位[8:0] 全 1；日志 0x38000 -> 0x381FF
    打印 'addr 0x9400004c after value is %0x'（0x47f3e6ff）
    delay 0xC8（0x47f00674）
    写 0x9A100004 = 0x0001381B
    delay 0xC8

### 2.7 时序总表（按执行顺序）

1. 0x94000050 清 bit31、0x94000054/0x94000050 配 PLL、mdelay(100)、清 bit31（PLL on）
2. mdelay(50) → 0x94000008 清 bit5/bit4 → delay 100 → 置 bit5 → delay 100
3. 0x9FE00000 24 写 → 打印 gpon serdes
4. 0x94000008 置 bit4 → 打印 rxpll_ready
5. 0x94100010 清 bit11、bits[9:6] 取自 0x9A107008
6. 0x9400004C bits[8:0]=0x1FF → delay 200 → 0x9A100004=0x0001381B → delay 200

## 3. 为什么内核永远补不回来

### 3.1 全树无引用（实测 grep）

对 iwrt-tree/target/linux/zx279128/ 递归 grep：

    94000008 | 94000050 | 94000054 | 94100010 | 9FE00000 | 9a107008 | 9A100004

结果为空；0x9400004c 也只有 USB reset 的位定义，没有本序列的 bits[8:0] 操作。

### 3.2 内核时钟驱动的自述

files/drivers/clk/zte/clk-zx279128s.c:8-10 头注释：

> The boot loader sets up the PLLs and the CPU and bus clocks, and the driver leaves them as they are:
> it reads them once and registers their rates. The gates, and the muxes and dividers of the
> peripherals, are under its control.

zx_top_pll()（同文件 :169-190）只读 cfg0/cfg1 并登记固定因子；LSP PLL 甚至直接写死
（:239-247：公式算 200 MHz，但厂商内核是 1 GHz，未测之前"按厂商速率登记"）。
即：**内核时钟框架把"PLL 由 bootloader 配好"当成前提，并且根本不认识 §2 里那颗 PLL。**

### 3.3 各驱动只碰自己的块

- PCIe PHY：files/drivers/phy/phy-zx279128s-pcie.c 只写 CRM1（0x94000000）：
  CRM1_PHY_CTRL 0x008 的 port0 BIT(15)/BIT(13)/BIT(14)、port1 BIT(27)/BIT(25)/BIT(26)，
  50 ms fsleep；port1 另写 PHY1_CAL1 0x1B4=0x00202D5A、PHY1_CAL0 0x1B0=0x0046C24A；
  最后清 CRM1_MISC 0x024 bit26。**不碰 PLL/SerDes/CRM2。**
- MDIO：files/drivers/net/mdio/mdio-zx279128s.c 只操作 0x9A101000 块
  （DATA_WR 0x04 / DATA_RD 0x08 / CFG 0x0c / STATUS 0x10 / CMD 0x14），probe 时写
  CMD=CLK_DIV|…、STATUS=0、CFG=0。
- GMAC：files/drivers/net/ethernet/zte/zx279128s-main.c 只操作 0x92000000 块，
  含 0x9200000C bit15/13 RGMII 延时；probe 在 :1359 调 phylink_of_phy_connect，
  失败即打印 port %u: PHY connect failed。
- 所以 MDIO 总线时钟"在跑"（内核自己配的 50/125 MHz），但**外部 PHY 的参考时钟**没人开。

### 3.4 回答 Lead：DTS 是否声明了这些时钟输出？

没有，也无法声明：

- 内核 DTS 只声明了可建模的门控：pcie0/1 clocks = crm2（0x94100070 门）+ resets（0x94100074 bits0/3）、
  phys = crm1；mdio clocks = lsp1crpm 的 wclk/pclk（0x9A100000 块 periph reg 0x04 门位）；
  gmac 节点（SoC dtsi patch 026-ARM-dts-zte-Add-ZX279128S-SoC-description.patch 行 220-256）
  **连 clocks/resets 属性都没有**。
- 厂商写的 0x94000008、0x9400004c、0x94000050/54、0x94100010、0x9A100004、0x9A107008、
  0x9FE00000 模拟块，没有任何一个能表达成 CCF 时钟节点；SerDes 模拟块更不是时钟框架的模型对象。
- 因此**改 DTS 修不了**；只能 (a) 由 bootloader（patch 0012）复刻厂商序列，或 (b) 之后写一个
  专门的 ref-clock/SerDes 内核驱动（周期长，作为后续选项）。

## 4. GPIO 映射（任务 2）

### 4.1 厂商机制

zte_gpio_init 0x47f2f314（调用点 0x47f01614，位于 board_init_r）：

1. pinmux 0x94200000：[0] |= 0xC00；[+4] |= 0xC0；[+0xC] |= 0x00180E80；
   若 board_id==1 另有 0x92040018 / 0x94200090 的位操作（本机 board_id=31，不执行）。
2. 调 0x47f2f0b8 对 8 根 strap 脚先设输入再读电平（flat 5,15,62,61,43,47,46,45），
   算出 product_vid（本机 31），存 BSS [0x47f6d62c+4]，打印
   product_vid = %d（0x47f3f7f1）与 vid=%d-%s（0x47f3f803）。
3. 用 product_vid 索引板级表（基址 0x47f42a7c，行宽 0x128；行内 +0x20 id、+0x24 name、
   +0x28 version、+0x58 条目数、+0x60/+0x64 条目指针）。
   本机行 0x47f44e54：id=31、name=E1630、version=V1.0.0、52 条目、条目数组 0x47f59b28。
   条目结构 0x1C 字节：+0 pin、+4 dir（1=输出/0=输入）、+8 value、+0xC valid(1=启用)。
4. 按条目顺序设置方向/电平并打印（即库存日志 §4.2 的顺序）。

厂商 GPIO API（bank 基址 0x94407000 + bank*0x40，bank = pin>>4，line = pin&0xf：
DIR 0x00 置 1 输出 / 清 0 输入，DATA 0x14 读电平，SET 0x18 置位，CLR 0x1C 清零；
内核 files/drivers/gpio/gpio-zx279128s.c 同布局，并注明"每 bank 16 线"，
flat 编号 = bank*16 + line）。

### 4.2 board id 31（E1630）启用的 18 个条目

日志顺序与条目索引完全一致：

| 条目 | pin(flat) | 方向 | 值 | 内核 DTS 对应 |
|---|---|---|---|---|
| 0 | 5 | in | — | &gpio0 5（strap） |
| 1 | 15 | in | — | &gpio0 15（strap） |
| 2 | 62 | in | — | &gpio3 14（strap） |
| 3 | 61 | in | — | &gpio3 13（strap） |
| 4 | 43 | in | — | &gpio2 11（strap） |
| 5 | 47 | in | — | &gpio2 15（strap） |
| 6 | 46 | in | — | &gpio2 14（strap） |
| 7 | 45 | in | — | &gpio2 13（strap） |
| 16 | 8 | out | 1 | &gpio0 8 = 蓝 LED（board dts:95） |
| 17 | 40 | out | 1 | &gpio2 8 = 绿 LED（board dts:88） |
| 18 | 60 | out | 0 | &gpio3 12 = 红 LED（board dts:81） |
| 27 | 18 | in | — | &gpio1 2 = key-reset（board dts:110） |
| 29 | 20 | in | — | &gpio1 4 = key-wps（board dts:116） |
| 47 | 55 | out | 0 | &gpio3 7（我们 DTS 的 pcie0 enable-gpios:251） |
| 48 | 52 | out | 0 | &gpio3 4（内核未用） |
| 49 | 54 | out | 0 | &gpio3 6（内核未用） |
| 50 | 51 | out | 0 | &gpio3 3（内核未用） |
| 51 | 2 | out | 0 | &gpio0 2（内核未用） |

### 4.3 结论

- 三颗 LED（8/40/60）与两个按键（18/20）与内核 DTS 完全吻合：**GPIO 表的主要目的就是 LED/按键**，
  不承担 PHY/PCIe 复位（印证 Lead 的更正 1）。
- 用途未知的 5 个输出（55/52/54/51/2，全部拉低）可能是 PHY/交换/PCIe 的模式或使能脚；
  我们的 U-Boot 完全不做这些驱动。若 F1 修完后链路仍缺，这是第二顺位实验点。
- **flat 53（我们 DTS 的 pcie0 reset-gpios = <&gpio3 5>）不在厂商表里**，厂商 E1630 设备树也
  没有任何 PCIe GPIO 配置（docs/refs-local/E2631原厂硬件视图-2026-10-12.txt:57、:219）。
  我们的 reset-gpios/enable-gpios 是从 H3600 抄来的猜测（docs/02-实施计划-2026-10-13.md:784
  亦已记录），不应作为修复主线。
- 建议 patch 0012 复刻 pinmux + 18 条 GPIO 表（与厂商同板同值，风险低），但**不要**把它
  当作网络修复的主要手段。

## 5. DTS 中 reset-gpios 覆盖情况（任务 3 的 DTS 部分）

- MDIO（board dts:215-232）：只声明 phy10..phy13 的 reg = <10>..<13>，没有
  reset-gpios/phy-reset-gpios/pinctrl；内核 eth 驱动也没有 PHY 复位代码，
  所以 PHY 复位只能靠 bootloader/硬件默认。
- PCIe0（board dts:249-255）：reset-gpios = <&gpio3 5 GPIO_ACTIVE_LOW>、
  enable-gpios = <&gpio3 7 GPIO_ACTIVE_HIGH>——均为 H3600 猜测；PCIe1（:257-260）无板级 GPIO。
- 厂商 E1630 设备树对 PCIe 没有 reg/GPIO/pinctrl（见 §4.3），厂商 U-Boot 的 GPIO 表也不驱动 53。
- 结合 §3：PHY/PCIe 参考时钟来自 SoC 的 PLL/SerDes，不是任何 GPIO；DTS 里也没有这些时钟输出。

## 6. product_vid 语义（排除项）

- product_vid **不落 efuse、不写寄存器、不写 flash**：boot 时由 zte_gpio_init 调
  0x47f2f0b8 采样 8 根 strap 脚电平算得（本机 31），存厂商 U-Boot BSS（全局 0x47f6d62c），
  仅用于选板级表行（31 = E1630）和条件 pinmux。
- 内核全树（target/linux/zx279128/、package/e2631/）grep product_vid|e1630|E1630 为空，
  内核不读、不关心它 → 不可能是网络主因。
- bootsel=3 由 0x47f2f24c 采样 0x94000040 得到，打印于 0x47f2f60c，与网络无关。

## 7. 给 patch 0012 的最小实现建议

原则：只复刻厂商**实测**的写序列；不猜测未验证的位；所有写前先打印 before/after 便于回归定位。

建议新增 e2631_net_refclk_init()（board 文件，板级 board_late_init 里调用，位置在
e2631boot 读镜像之前即可）：

    1) pll_cfg_fractional(base=0x94000050, arg1=1, arg2=0x5D, arg3=0x004FDF3B, arg4=5, arg5=3)
       —— 按 §2.2 的读-改-写实现，含 mdelay(100)、最后清 bit31
    2) mdelay(50)
    3) 0x94000008: 清 bit5、清 bit4；mdelay(100)；置 bit5；mdelay(100)
    4) 写 0x9FE00000 24 个寄存器（§2.4 表，+0x40 两次写）
    5) 0x94000008: 置 bit4
    6) 0x94100010: 清 bit11；bits[9:6] = (readl(0x9A107008) >> 24) & 0xF
    7) 0x9400004C: bits[8:0] = 0x1FF（其余位保留）；mdelay(200)
    8) 0x9A100004 = 0x0001381B；mdelay(200)
    9) （可选，F2）pinmux 0x94200000 三处按位或；按 §4.2 表设置 18 条 GPIO
    10) 打印 0x94000050/0x94000054/0x94000008/0x94100010/0x9400004C/0x9A100004 before/after

注意：
- 0x9FE00000 是模拟/SerDes 块，只在 E2631 板型上做；不要写进通用 SoC 代码。
- 顺序不能乱（先 PLL，再 0x94000008 bit5，再 SerDes，再 bit4，最后 CRM2/0x4c）。
- 若第 1 次上电出现异常，回滚只需去掉该调用（纯 U-Boot 改动，mtd0 写风险与既有流程相同）。

## 8. 验证计划

1. 打补丁构建 → C1b 同流程刷 mtd0 → 冷启动，看内核日志是否出现
   PHY [9a101000.mdio:0a..0d] driver [Generic PHY]、Link is Up、pci 0000:01:00.0 [14c3:7906]、
   pci 0001:01:00.0 [14c3:790a]。
2. U-Boot 里先 md 这些寄存器，确认序列写入值与 §2 表一致（首轮即可定位差异）。
3. 若 PHY 通、PCIe 仍缺 → 试 F2（pinmux + GPIO 表）；若 PCIe 通而 PHY 不通 → 查 PHY 复位/strap。
4. 回归：vendor RAM 链、flash 链两种启动都验证网络，确保没有把旧链弄坏。

## 9. 未决问题（低置信/需实测）

- Q1：0x94000050/54 这颗 PLL 到底供给谁（PHY ref 50/125 MHz？SerDes？PON？）；bits[23:18]=1 的字段语义。
- Q2：0x94000008 bits4/5 是什么（内核未建模）；是否只是 SerDes 块的时钟门/复位释放。
- Q3：0x9FE00000 的 24 个写里哪些是必需的（"gpon serdes"命名暗示 PON 侧，但本机是路由模式，
  该块是否也供外部 PHY 参考时钟需实测）。
- Q4：F2 的 5 个未知输出脚究竟是模式 strap 还是电源使能。
- Q5：长期是否要把 ref-clock 搬进内核驱动（DTS 声明 + 驱动），还是永久留在 U-Boot。

## 10. 复现

- 反汇编：capstone 5.0.9（python3 -m pip install --target /tmp/pylibs capstone），
  脚本 /tmp/an*.py（字符串扫描、字面量 xref、指针表扫描、逐函数反汇编并标注字面量字符串）。
  运行：PYTHONPATH=/tmp/pylibs python3 /tmp/anXX.py。
- 地址换算：厂商 payload 虚拟地址 0x47F00000 + file_off；mtd0 内偏移 file_off + 0x20800。
- 厂商写序列定位：0x47f2f8bc（PLL）、0x47f2fbc4（ref_clk_set）、0x47f2fc58（SerDes 表）、
  0x47f2fe38（总控）、0x47f20444（0x9400004C/0x9A100004）、0x47f2f314（GPIO/pinmux）。
- 成功链证据：evidence/c1b0-entry/serial.txt:62-69；失败链
  /home/qc233/zte/e2631-p3/c1b1fix/session-a/run-1/serial.log（无 Net: 段、无 9a101000.mdio）。
