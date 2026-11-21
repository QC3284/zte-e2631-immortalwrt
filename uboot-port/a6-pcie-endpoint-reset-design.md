# A6：PCIe 端点复位/供电线（pin 2 / pin 51）

状态：patch 0013（2026-11-22）。范围：E2631 板级；不碰 SoC 通用代码。

## 1. 背景与现象

A5（patch 0012）把厂商 `board_eth_init()` 的参考时钟/SerDes/管脚序列补齐后，flash 链上以太网恢复：
MDIO 10-13 四个 PHY 出现、`lan1`/`wan` link up、flow offload 正常。但同一次会话里 **PCIe 仍不工作**：
内核只枚举到两个 PCIe root port（`1cf2:6830`），没有任何 endpoint；`lspci` 里没有 `14c3:7906`（bus0）
与 `14c3:790a`（bus1），`mt7915e` 无法绑定，`e2631-wifi-boot` 以 `mt7916 init failed` 结束；152 s 后
rescan 也找不到设备。用厂商 U-Boot 引导同一内核时两个 endpoint 正常出现。

## 2. 两链差异（A5 run-3 残留）

verify-docs 在 A5 会话里做了两链 post 状态对比（我们的 flash 链 vs 厂商 U-Boot），200 vs 220 个字里
只剩 10 个字不同：

| 寄存器 | 我们的值 | 厂商值 | 解释 |
| --- | --- | --- | --- |
| `0x94400018` | 0400001b | 0400081b | LSP0 CRPM offset 0x18 = SPI 时钟寄存器；内核 clk 驱动会配置（`clk-zx279128s.c` 的 lsp0 `spi` 条目），与 PCIe 无关 |
| `0x94407014` / `0x94407020` | bit2=0 | bit2=1 | GPIO bank0 pin 2 DATA / 输出镜像 |
| `0x944070d4` / `0x944070e0` | bit3=0 | bit3=1 | GPIO bank3 pin 51 DATA / 输出镜像 |
| `0x9A101004/8/14/18/1c` | 0 | 8f08 / 1040 / 19a0 | 厂商以太网 probe 的 MDIO 控制器内部寄存器；内核 MDIO 驱动重新初始化 |

因此 bootloader 侧仍受我们控制、且真正不同的外设状态只有 **pin 2 与 pin 51 这两根 GPIO 线**。

## 3. 厂商逆向（关键证据）

`zte_gpio_init()`（`0x47f2f314`）并不止于板级表回放，它后面还有两段循环：

1. `0x47f2f61c`–`0x47f2f668`：再次遍历 52 项板级表，条件 `index == 0x33`（51）且 `dir == 1`（输出），
   调用 `gpio_set(pin, 1)`。表索引 51 的项是 **pin 2**（`en=1`、`dir=1`、`val=0`）。
2. `0x47f2f66c`–`0x47f2f6c0`：同样遍历，条件 `index == 0x32`（50），表索引 50 的项是 **pin 51**
   （`en=1`、`dir=1`、`val=0`）。

两段都无视表里的 `val=0`，直接把对应 pin 驱高。厂商板级表在 vendor payload 的 file offset `0x59b28`，
每项 28 字节（`+0x00` pin、`+0x04` dir、`+0x08` val、`+0x0c` enabled）；索引 50/51 的原始项分别是
`0x33/1/0/1` 与 `0x02/1/0/1`。

另外，对厂商 U-Boot 全文做字面量扫描：`0xf000000`、`0xf100000`、`0x9500000`、`0x9600000`、
`0x1c000000`、`0x2c000000`（PCIe host/ctrl/config）**零命中**；也没有任何 PCIe PHY 寄存器写。也就是说
厂商 bootloader 不初始化 PCIe 控制器/PHY——这些完全由内核驱动完成（`pcie-zx279128s.c` 的 DWC 初始化与
`phy-zx279128s-pcie.c` 的 CRM1 PHY 时序）。bootloader 唯一能影响 PCIe 的就是这两根 GPIO 的外围状态。

## 4. 假设与依据

两根线的功能没有硬件文档；我们的工作假设是 **两个 PCIe endpoint 的复位/供电使能**，依据：

- A5 差分里只剩这两根仍受 bootloader 控制的线；
- 厂商代码在板级初始化完成时特意把它们驱高，且覆盖表值；
- 厂商链（两线高）能枚举两个 endpoint，flash 链（两线低）只有 root port；
- 内核 PCIe 驱动的 reset/enable GPIO 来自 H3600 时期的 DTS 猜测（`gpio3` 5/7 = pin 53/55），并不覆盖 pin 2/51。

## 5. 实现（patch 0013）

`board/zte/zxhn-e2631/e2631net.c`：

- 新增 `E2631_GPIO_PCIE_RST0 = 2`、`E2631_GPIO_PCIE_RST1 = 51`；
- 在 `e2631_pinmux_gpio_init()` 的板级表输出回放循环之后，先 `e2631_gpio_drive(2, 1)`，
  `mdelay(4)`（厂商在 loop B 之前就有这个 4 ms 等待），再 `e2631_gpio_drive(51, 1)`；
- 只对 SET 寄存器做 RMW（写 1 位置位），幂等；`e2631boot` 与 `e2631refclk` 共用同一路径（0012 的调用点）。

不新增命令：验收用 U-Boot 自带的 `md` 读 GPIO 寄存器即可。

## 6. 输出与验收

U-Boot 侧（提示符或 `e2631boot` 之前）：

```
md.l 0x94407014 1     # bank0 DATA，bit2 应为 1（0x...004）
md.l 0x944070d4 1     # bank3 DATA，bit3 应为 1（0x...008）
```

内核侧（零写入会话记录）：

1. `lspci` 出现两个 endpoint：`14c3:7906`（bus0）与 `14c3:790a`（bus1）；
2. `mt7915e` 绑定成功，`e2631-wifi-boot` 不再报 `previous initialization unfinished`/`mt7916 init failed`；
3. `br-lan` 有 PHY，eth 链路不受影响（0012 的验收项保持）；
4. 全程不写 flash、不写 env。

CI（uboot-build.yml）断言：series tree `f04e5ed9525c87bddc329b24a311dfa4a302b750`（13 个 patch，含厂商 4 ms 间隔）、
`E2631_GPIO_PCIE_RST0` 形状 gate。

## 7. 风险与回退

- 若这两根线并非 PCIe 相关、或造成其它外设变化：删掉 `e2631_pinmux_gpio_init()` 末尾的两行
  `e2631_gpio_drive()` 即回到 A5 状态，eth 与启动链不受影响。
- 表值 0 与特例 1 的冲突由厂商代码决定；本补丁照抄厂商特例，不自行推断。
- 该补丁只影响 E2631 板型，不碰 SoC 通用代码，也不改 0001–0012。

## 8. 参考

- [evidence/uboot-a5-20261122.md](../evidence/uboot-a5-20261122.md)（A5 会话与两链差分）
- verify-docs A5 run-3：`/home/qc233/zte/e2631-p3/c1b1fix/a5-refclk/run-3/residual-vs-vendor.txt`
- 厂商 payload 反汇编：`zte_gpio_init 0x47f2f314`、板级表 `0x47f59b28`、特例循环 `0x47f2f61c`/`0x47f2f66c`
- [a5-net-refclk-design.md](a5-net-refclk-design.md)（网络参考时钟/SerDes）