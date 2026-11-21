# A5：网络参考时钟 / SerDes / 管脚初始化（patch 0012）

本说明对应 `uboot-port/patches/0012-board-zte-bring-up-the-network-reference-clocks.patch`。
它是 C1b-1 之后暴露的第二个"闪存链缺口"：腾挪 CP15 之后内核能启动，但网络 PHY 与 PCIe 端点仍然沉默。
A5 只补**让内核能自己接管硬件所需的板级上电状态**（参考时钟、SerDes、pinmux、GPIO），不做网络协议栈，
不做 PCIe host 或 PHY 驱动——那些仍由内核负责。

## 1. 现象与对照

| 项 | 厂商 U-Boot 引导（stock / cspstart） | 我们的 flash 链（secondboot → 我们的 U-Boot → bootm） |
| --- | --- | --- |
| MDIO 总线 | 四个内部 PHY 在地址 10-13 应答，lan1/wan 1 Gbps | `9a101000.mdio` 时钟在走（`mdio_wclk` 50 MHz），但 10-13 全部不应答，`br-lan` DOWN |
| PCIe | 端点 `14c3:790a` 枚举，MT7916 固件加载、双频转发 | 两个根端口只有 `[1cf2:6830]`，无端点 |
| 时钟 | `pll_lsp` 1 GHz、`mdio_wclk` 2.5 MHz、CRM2 的 pcie0/1 使能 | `mdio_wclk` 50 MHz，其余缺失 |

同一硬件、同一内核与 rootfs（verify-docs 的 vendor-chain 对照，2026-11-22）。差分就是厂商 U-Boot
`board_eth_init()` 在启动时做的板级初始化，而我们的 flash 链从未执行它（RAM 链也没有，但 RAM 链验收
不测网络，所以此前没有暴露）。内核侧不能补：`clk-zx279128s.c:8-10` 明确假设 bootloader 已完成网络 PLL，
且没有任何内核驱动触碰 `0x94000008/0x94000050/0x94000054`、`0x94100010`、`0x9FE00000`、`0x9A107008`、
`0x9A100004`——DTS 无法描述"bootloader 才该做的时钟树初始化"。

## 2. 厂商证据（iwrt-baseline，evidence/p2-vendorless-network-gap-20261122.md）

调用链（vendor payload vaddr = `0x47F00000 + file offset`）：

```
board_init_r 0x47f015c0
  -> eth_initialize 0x47f2b914          (board_eth_init 指针 0x47f2ba9c = 0x47f00850)
       -> 0x47f1fe38  MDIO 设备注册（name "279112mdio"）
       -> 0x47f30b54  eth 设备注册
       -> 0x47f2fe38  ref clock + SerDes（pll_cfg_fractional 0x47f2f8bc）
       -> 0x47f20444  0x9400004C / 0x9A100004
  -> 0x47f2f314  zte_gpio_init（pinmux + 18 项 GPIO 表）
```

厂商串口日志（vendor-chain run-2，`search 'ref_clk_set success'`）：

```
Net:   enter ref_clk_set.. mode = 0 .
enter pll_cfg_fractional
ref_clk_set success!
gpon serdes init
rxpll_ready
addr 0x9400004c before value is 38000
addr 0x9400004c after value is 381ff
eth0
```

## 3. 寄存器序列（patch 0012 实现）

### 3.1 分数 PLL（`0x94000050` / `0x94000054`）

1. `0x94000050`：bit31=1（PLL 启动）、bit27=0、bit24=0、bits[23:18]=1、FBDIV[17:6]=0x5D、PD1[5:3]=5、
   PD2[2:0]=3；
2. `0x94000054 = (old & 0xFF000000) | 0x004FDF3B`；
3. `mdelay(100)` → 清 `0x94000050` bit31（结束启动）→ `mdelay(50)`；
4. 网络 PLL：`0x94000050 = (old & 0x76000000) | 0x0004176B`。

### 3.2 SerDes（`0x9FE00000`，25 次写）

| 偏移 | 值 | 偏移 | 值 |
| --- | --- | --- | --- |
| +0x00 | 0x800010A7 | +0x30 | 0x20242000 |
| +0x04 | 0x0F | +0x34 | 0xC0593D44 |
| +0x08 | 0x540 | +0x38 | 0x42F |
| +0x0C | 4 | +0x3C | 0 |
| +0x10 | 0 | +0x40 | 0x003C0000，随后 0x003C0040 |
| +0x14 | 0x018A6400 | +0x44 | 0xEAC0A013 |
| +0x18 | 0x08B50140 | +0x48 | 0x101038CA |
| +0x1C | 0x01216000 | +0x4C | 0x5A000 |
| +0x20 | 0x40000000 | +0x50 | 0x33333333 |
| +0x24 | 0x0B570001 | +0x54 | 0x33333333 |
| +0x28 | 0 | +0x58 | 0x03E23333 |
| +0x2C | 0 | +0x5C | 0x00040244 |

`0x94000008` 的 bit5/bit4 时序包住 SerDes 写：清 bit5+bit4 → delay 100 → 置 bit5 → delay 100 →
写 SerDes → 置 bit4。

### 3.3 CRM2 参考时钟选择（`0x94100010`）

清 bit11；`bits[9:6] = (readl(0x9A107008) >> 24) & 0xF`（参考时钟源来自 strap 寄存器）。

### 3.4 LSP1 时钟（`0x9400004C` / `0x9A100004`）

`0x9400004C` 的 `bits[8:0] = 0x1FF`（厂商日志 0x38000 → 0x381FF）；`mdelay(200)`；
`0x9A100004 = 0x0001381B`；`mdelay(200)`。

### 3.5 Pinmux 与 GPIO 输出（`0x94200000` / `0x94407000`）

厂商 `zte_gpio_init()`（`0x47f2f314`）不是只做几处 `|=`：它先 OR 三个 bit，再按板级表整字写入六个
pinmux 寄存器（循环 `0x47f2f458`：`ldr r1,[entry+0x40+i*4]; str r1,[0x94200000+i*4]`，i=0..5）。
产品 id 31（E1630 V1.0.0）的板级表在 payload 文件偏移 `0x44e74`，pinmux 六字为 `0x0f3ffffa`、
`0x00effeff`、`0x0555ffff`、`0x003dbf85`、`0`、`0`，与厂商链 md 末态逐字相同；因此 0012 也先做
`[0] |= 0xC00`、`[+4] |= 0xC0`、`[+0xC] |= 0x00180E80`，再写入六个整字（只 OR 会留下不同的 mux）。

GPIO 表 52 项里本产品启用 18 项；其中十个输入（strap 5/15/62/61/43/47/46/45、按键 18/20）复位后 DIR
位已经是 0，与厂商清 DIR 的结果相同，故不写；只驱动八个输出：8=1、40=1、60=0（三色 LED）、
55=0、52=0、54=0、51=0、2=0（板级表值）。

- 寄存器模型：bank = `0x94407000 + 0x40 * (pin >> 4)`，line = `pin & 0xF`；DIR `+0x00`（1=输出）、
  DATA `+0x14`、置位 `+0x18`、清零 `+0x1C`。
- **`+0x20` 是硬件维护的输出镜像**：厂商 GPIO 助手从不写它，md 里只有被驱动为高的 bank 出现对应 bit
  （bank0 `0x104` = pin2/8、bank2 `0x100` = pin40、bank3 `0x8` = pin51），由 SET/CLR 自然产生，故不写。
- **厂商提示符处 pin2 与 pin51 为高**，但板级表值为 0：那是板 init 之后厂商启动工具（cspboot）驱动的，
  0012 按表值写 0，并把这一差异记录在案，不悄悄复制 1。
- **不驱动 flat 53**：那是 kernel 板级 DTS 里 `pcie0 reset-gpios <&gpio3 5>` 的 H3600 时期猜测，
  不在厂商 18 项表里；盲目驱动可能改变 PCIe 复位语义。

### 3.6 时钟 mux `0x9400000C`（厂商以太网 probe 的额外写）

厂商 `board_eth_init()` 之后，它的以太网驱动 probe（`0x47f1f6xx`）还做了一组 CRM 写：
`0x9400000C` 清 `bits[21:20]` 再置 bit20（`0x47f1f790..0x47f1f7a0`）、`0x94100008 |= 0x05550000`、
`0x94100018` 清 `0x1F800` 置 `0x800`、`0x94100024` 清 `0x30000` 置 `0x10000`，并轮询 `0x94100008` bit1。
两链 dump 里只有 `0x9400000C` 真的不同（`0x00417800` -> `0x00517800`，00 变 01）；`0x94100008/18` 两链
已相同（secondboot 已置好），`0x94100024` 未 dump。因此 0012 只重放 `0x9400000C` 的 `bits[21:20]=0b01`，
其余三处**刻意不写**（未证明不同，不做无依据的 SoC 写）。

## 4. 代码与调用路径

- `board/zte/zxhn-e2631/e2631net.c|.h`：`e2631_net_refclk_init()` 与 `e2631refclk` 命令。
- `e2631boot.c`：解析完参数、确认要 `bootm` 后调用 `e2631_net_refclk_init()`；命令路径与自动路径
  完全同一条函数，方便真机 A/B。
- `e2631refclk` 输出（两行 before、两行 after，32 位小写十六进制）：

```
e2631refclk: before  PLL0=... PLL1=... CTRL8=...
e2631refclk: before  CRM2_10=... CTRL4C=... LSP1_04=... CTRL0C=...
e2631refclk: running the vendor network reference-clock and SerDes sequence
e2631refclk: after   PLL0=... PLL1=... CTRL8=...
e2631refclk: after   CRM2_10=... CTRL4C=... LSP1_04=... CTRL0C=...
e2631refclk: back at the prompt, nothing was booted
```

寄存器（7 个）：`0x94000050`、`0x94000054`、`0x94000008`、`0x94100010`、`0x9400004C`、`0x9A100004`、`0x9400000C`。
命令不启动、不写 flash、不写 env。

## 5. 验收

### 5.1 CI（uboot-build.yml）

- 12 个 patch、tree `5de49c199b0515b95fc0ea21264b3f0bb3418eed`、patch sha256 与 §1 表一致；
- `u-boot.bin` 含 `e2631refclk`；`e2631boot.c` 引用 `e2631_net_refclk_init`；
  `e2631net.c` 仍含厂商值 `0x004fdf3b`、`0x003c0040`、`0x0001381b` 与板级 pinmux 字
  `0x0f3ffffa`、`0x003dbf85`、`0x9400000C` 的 `0x00100000`；
- checkpatch 0 errors；载荷仍远低于 `0x9F800`。

### 5.2 内核侧成功签名（真机会话，零写入）

1. `/sys/class/mdio_bus/*/phy*` 出现地址 10-13 的四个 PHY，`lan1`/`wan` carrier up 1 Gbps；
2. `lspci` 出现 `14c3:790a`（vendor-chain 实测；若 `14c3:7906` 也出现则一并记录）；
3. `MT7916 ready` 出现在内核日志，双频可转发；
4. `pll_lsp` ≈ 1 GHz、`mdio_wclk` 与厂商链一致（2.5 MHz）。

### 5.3 设备会话步骤（需用户批准，零 flash 写入）

1. 从当前系统 `reboot -f` 进我们的 flash U-Boot 提示符；
2. 先 `md` dump 0012 的寄存器集（pre-init 状态），再 `e2631refclk`（before/after），再 `e2631boot`；
3. 内核起来后记录 §5.2 的四项；`mtd0` sha256 与进入前一致；全程不写 flash/env。

### 5.4 失败定位

- PHY 仍不应答：对比 `e2631refclk` 的 before/after 与厂商日志（`Net: enter ref_clk_set..` 到 `eth0`）；
  重点看 `0x94000054`、`0x94100010`（CRM2 pcie0/1 使能）与 `0x9400004C`。
- PCIe 不枚举：检查 `0x94100010` 的 bits[9:6] 与 `0x9400004C` 的 `0x1FF` 是否生效。
- 网络口无 link：执行 `md 0x94200000 4` 与 `md 0x94407000 0x40` 核对 pinmux/GPIO。
- `0x9FE00000` md 挂死：说明该块时钟未开（secondboot 状态下不应发生）；记录并改用"只读 0x94000008
  确认 bit4 后再写 SerDes"的顺序，必要时把 SerDes 表写移到门控检查之后。

## 6. 风险与回退

- **重放厂商值，不是自配时钟**：`0x94000050/54` 等写的就是厂商 `board_eth_init()` 的确定值，寄存器集先按两链 pre/post dump 裁剪（留下值确实不同或 pre 不可读的项）；`0x9400000C` 来自 probe 但两链 dump 证明不同，也一并重放；内核 clk
  驱动不重编程它们，因此必须保持厂商语义。若真机异常，先跑 `e2631refclk` 对照 before/after。
- **只在 E2631 板型执行**：不碰 SoC 通用代码；其它板子/上游不受影响。
- **回退**：删掉 `e2631boot.c` 里 `if (load) e2631_net_refclk_init();` 一行（或整 patch）即可，
  启动链其余部分不依赖它。
- **幂等**：所有写要么是确定值、要么是 read-modify-write；重复执行结果相同（`e2631refclk` 后紧接着
  `e2631boot` 再跑一次不会漂移）。
- **RAM 链**：入口配置改动（0011）与网络初始化（0012）同样作用于 RAM 链；RAM 链验收不测网络，
  该项由下一次真机会话（flash 链优先）验证。

## 7. 参考

- `evidence/p2-vendorless-network-gap-20261122.md`：厂商 `board_eth_init()` 逆向（iwrt-baseline）
- 两链 pre/post md dump：`/home/qc233/zte/e2631-p3/c1b1fix/md-dump/`（`md-our-chain.txt`、`md-vendor-chain.txt`、`md-diff.txt`，62 个不同 32 位字）
- `evidence/uboot-cp15-cleanup-20261121.md`：C1b-1 的 CP15 修复与 Session A 数值
- `uboot-port/a4-soc-state-design.md`：C1b-1 设计（同一 flash 链缺口的第一个修复）
- `uboot-port/README.md`：pin、CI 断言与真机步骤总表
