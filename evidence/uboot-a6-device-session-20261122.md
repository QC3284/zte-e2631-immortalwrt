# A6 真机会话：patch 0013 两条 PCIe 端点复位线的零写入验收（2026-11-22）

> 产物/设计见 [uboot-a6-20261122.md](uboot-a6-20261122.md) 与 [../uboot-port/a6-pcie-endpoint-reset-design.md](../uboot-port/a6-pcie-endpoint-reset-design.md)；
> 本目录附件见 [uboot-a6-session/](uboot-a6-session/)；A5 的确定性失败记录见 [uboot-a5-device-session-20261122.md](uboot-a5-device-session-20261122.md)。

## 0. 结论：**GREEN**

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| GPIO 门禁 pin2 `0x94407014` bit2 | **PASS**：`0x0000db2c`（= 厂商 post-init 残差目标） | run-3 串口行 28384；`postcheck.json` |
| GPIO 门禁 pin51 `0x944070d4` bit3 | **PASS**：`0x0000e028`（= 厂商残差目标） | run-3 串口行 28386 |
| e2631refclk 契约（7 寄存器 before/after） | **PASS** 7/7 + before_pre | run-3 串口行 28310–28315；`refclk_checks` |
| SerDes `0x9fe00000` 24 字读回 | **PASS** 24/24 | `session-results.json`（post-dump） |
| PCIe：两条 Gen.1 x1 link + 两个端点 | **PASS**：`0000:01:00.0 [14c3:7906]`、`0001:01:00.0 [14c3:790a]` | `device-readonly.txt` |
| 以太网：四个 MDIO PHY + lan1/wan 1 Gbps | **PASS** | 同上（0.875–0.878 s 四 PHY；11.77/28.72 s lan1；29.84 s wan） |
| MT7916：mt7915e 绑定 + ready + 双频转发 | **PASS**：绑定 175.8 s、ready 176.0 s、`phy0-ap0`/`phy1-ap0` up | 同上（注意 latency 见 §5） |
| 零 flash 写入 | **PASS**：mtd0 sha256 前后都是 `d571b764...d286b0f5`，无写命令 | `device-readonly.txt`；`postcheck.json` |
| 驱动自身 verdict | **FAIL（工具缺陷）**：`KeyError('probes_late')` 在早期探针后中止驱动，产品侧不受影响 | §6；`postcheck.json` 独立判定 GREEN |

一句话：**patch 0013 修复确认**。GPIO 两根线在两个方向上与厂商完全一致（残差字归零），
内核枚举到两个 MT7916 端点，以太网四个 PHY 全部 1 Gbps，Wi-Fi 双频最终起来并转发；
全程零 flash 写入。Wi-Fi 就绪比厂商链慢（176 s vs 54 s），单独作为观察项记录（§5），不阻塞 A6。

## 1. 产物与输入

| 项 | 值 |
| --- | --- |
| CI run | `44935007253`（patch 0013 v3，kit tip `24e52c6`，kit CI `44935473609` green） |
| u-boot.bin | 450,936 B，sha256 `3bf182f148226b6f64696a05bba5d75ca59426747f87eee3f13c5d2b0269423a` |
| banner token | `U-Boot 2027.01-rc2-g85c7367a3106`（v3 在两次驱动之间加了厂商的 mdelay(4)） |
| e2631-uboot-mtd0.bin | 655,360 B，sha256 `f6d179daa952db910afacde635f259fbe5f2eabf97f3d8aa07d2c09540979a42`（**未刷写**，仅记录） |
| 入口 / 装载 | TEXT_BASE = 0x47F00000；loadx CRC-1KiB 到 0x47F00000 |
| 设备 | ImmortalWrt v1.10.0 / kernel 6.18.60，运行在 A5 留下的 RAM 链内核（eth 起、PCIe/Wi-Fi 未起） |
| 串口/链路 | /dev/ttyCH343USB0 115200，serialhub 接管（单读），会话后恢复捕获链；主机直连 USB 网卡 192.168.1.191 |

## 2. 三次尝试（全部零写入）

| # | 镜像 | 结果 | 原因 |
| --- | --- | --- | --- |
| run-1 | v2 `g6620d6e97d78` | 门禁读到冷值 `0x00009120` / `0x000070a0`（bit2=0、bit3=0），安全中止，**内核未启动** | 门禁放在 e2631boot 之前、但 patch 0012/0013 的 pinmux/GPIO 初始化在 `e2631_net_refclk_init()` 里，未跑 refclk 时它还没执行 |
| run-2 | v3 `g85c7367a3106` | 同上（驱动仍把门禁放在 refclk 之前；`--with-refclk` 因此没有先执行） | 驱动顺序缺陷，见 §6 |
| run-3 | v3 `g85c7367a3106` | **GREEN**：refclk → 门禁 → e2631boot → 内核 → 网络/Wi-Fi 全部起来 | 修正顺序后一次通过 |

v2 与 v3 的差别只是两次驱动之间的 `mdelay(4)`；run-1 中止发生在写入之前，因此不存在用 v2 启动过内核的记录。
正式 A6 判据全部来自 v3（run-3）。

## 3. run-3 时间线（2026-11-22，attach 模式，无额外断电）

| 时间 | 事件 |
| --- | --- |
| 02:32:40 | 暂停捕获链、serialhub 接管；attach 到上一次留下的我们 U-Boot 提示符（`version` 可见） |
| 02:32:41 | 冷态指纹 6/6 MATCH；pre-dump 200 字 |
| 02:33:24 | loadx patch-0013 v3（450,936 B，1 KiB 块，CRC 模式，42.1 s） |
| 02:36:34 | md.b 全量校验 OK；`go 0x47f00000`；新 banner `g85c7367a3106`；停 autoboot |
| 02:36:38 | **e2631refclk**：before/after 各两行（见 §4），7/7 契约命中；post-dump 21 处差分、key 7/7、SerDes 24/24 |
| 02:36:39 | **GPIO 门禁**：`94407014: 0000db2c`（位 2=1）、`944070d4: 0000e028`（位 3=1），与厂商残差目标逐位一致 |
| 02:36:39 | `e2631boot` → slot1（serial 12，ImmortalWrt v1.10.0）→ uImage `ARM ImmortalWrt Linux-6.18.60` 3,491,146 B，CRC good |
| 02:36:46 | `Starting kernel ...`；02:37:03 用户态 `Please press Enter`；无 panic/abort |
| 02:37:28 | 驱动因 `KeyError('probes_late')` 中止（工具缺陷），捕获链于 02:37:35 恢复；内核继续运行 |
| 02:39–02:44 | 只读 SSH（直连 USB 网卡）采集终态：PCIe 两端点、四 PHY、1 Gbps、MT7916 ready 176 s、双频 up、mtd0 不变 |

## 4. 验收签名（串口/内核原文）

```
e2631refclk: before PLL0=80040faa PLL1=00353f7d CTRL8=10061fcf
e2631refclk: before CRM2_10=00000000 CTRL4C=00038000 LSP1_04=0000081b CTRL0C=00417800
e2631refclk: after PLL0=0004176b PLL1=144fdf3b CTRL8=10061fff
e2631refclk: after CRM2_10=00000100 CTRL4C=000381ff LSP1_04=0001381b CTRL0C=00517800
94407014: 0000db2c                             ,...
944070d4: 0000e028                             (...

```

内核侧（`device-readonly.txt`）：

```
[    0.609358] zx279128s-pcie f000000.pcie: PCIe Gen.1 x1 link up
[    0.611118] pci 0000:01:00.0: [14c3:7906] type 00 class 0x028000 PCIe Endpoint
[    0.719357] zx279128s-pcie f100000.pcie: PCIe Gen.1 x1 link up
[    0.721065] pci 0001:01:00.0: [14c3:790a] type 00 class 0x028000 PCIe Endpoint
[    0.875415] ... lan3 (uninitialized): PHY [9a101000.mdio:0a] driver [Generic PHY] (irq=POLL)
[    0.876382] ... lan2 (uninitialized): PHY [9a101000.mdio:0b] ...
[    0.877329] ... lan1 (uninitialized): PHY [9a101000.mdio:0c] ...
[    0.878287] ... wan  (uninitialized): PHY [9a101000.mdio:0d] ...
[   11.769632] zx279128s-eth 92000000.ethernet lan1: Link is Up - 1Gbps/Full - flow control off
[   28.720756] zx279128s-eth 92000000.ethernet lan1: Link is Up - 1Gbps/Full - flow control off
[   29.839745] zx279128s-eth 92000000.ethernet wan: Link is Up - 1Gbps/Full - flow control off
[  175.823633] mt7915e 0000:01:00.0: registering led 'mt76-phy0'
[  175.887617] mt7915e 0000:01:00.0: registering led 'mt76-phy1'
[  176.035575] e2631-wifi-boot: MT7916 ready
[  176.267343] e2631-wifi-boot: automatic Wi-Fi initialization complete
```

`/sys/bus/pci/devices`：`0000:00:00.0 0x1cf2:0x6830`（root port）、`0000:01:00.0 0x14c3:0x7906`、
`0001:00:00.0 0x1cf2:0x6830`、`0001:01:00.0 0x14c3:0x790a`。`iw dev`：`phy0-ap0` ch1 HE40（SSID E2631）、
`phy1-ap0` ch36 HE80，两者 `operstate=up`；`/sys/class/net` 含 lan1/lan2/lan3/wan/`phy0-ap0`/`phy1-ap0`。

## 5. 观察项：Wi-Fi 就绪 latency（176 s vs 厂商链 54 s）

本次自定义链上 Wi-Fi 不是 54 s 起来，而是：

```
[   29.608375] e2631-wifi-boot: previous initialization unfinished; retrying in 120s
[  149.624682] e2631-wifi-boot: waiting 25s
[  175.823633] mt7915e 0000:01:00.0: registering led 'mt76-phy0'
[  176.035575] e2631-wifi-boot: MT7916 ready
```

PCIe 端点在 0.6 s 就枚举完成，所以这不是端点缺失；更像 wifi-boot 首次尝试在 mt7915e 绑定前就放弃、
按 120 s 重试才把驱动/firmware 拉起来。厂商链（2026-11-22 00:40 会话）是 54 s ready。
该差异**不影响** A6 判据（最终 ready + 双频转发都成立），但它是自定义链与厂商链之间尚未解释的行为差，
留作后续任务（需要时对比 wifi-boot 脚本两条路径的触发时机与 mt7915e 模块加载顺序）。

## 6. 工具缺陷与修正（产品判定不受影响）

1. **门禁顺序**：驱动初稿把 GPIO 门禁放在 e2631boot 之前，但初始化在 `e2631_net_refclk_init()` 内，
   必须先跑一次 e2631refclk 才会执行 pinmux/GPIO 表回放与 patch 0013 的两次拉高。顺序改为
   `e2631refclk → md 门禁 → e2631boot`；rootfs 内文档的设计描述（初始化在 refclk 内、e2631boot 再执行一次且幂等）与此一致。
2. **pci 探针时序**：`pci_txt` 在 `probes_late` 尚未生成时就引用它，导致 `KeyError('probes_late')`，
   在早期探针之后中止驱动（产品内核与后续启动不受影响；网络/Wi-Fi 由捕获链与只读 SSH 补齐证据）。
   修正版见附件 `tool-c1b1_a6_pcie-fixed.py`（端点判据改为全部探针收集后重算）。
3. **写命令审计误报**：serial.log 里 U-Boot 帮助字符串（内存 hex dump 中的 `mtd write[.raw]` / `mtd erase[.dont`）
   会被朴素正则当成命令；`tool-a6_postcheck.py` 先剔除 `^[0-9a-f]{8}:` 的 hex dump 行再匹配，命中为 0。

## 7. 零写入实证与设备现状

- 会话内发出的所有 U-Boot 命令：`version`、`md.l`、`md`、`loadx`、`go`、`e2631refclk`、`e2631boot`（没有 nand/mtd write/erase、
  saveenv、upgrade、tftp、bootm 直调）。
- 会话前 mtd0 sha256 = `d571b76404df1596dd58b710cff84e1ede92e6a29798abe5dcc50198d286b0f5`（A5 后状态）；
  run-3 后只读 SSH 复算同样为 `d571b764...d286b0f5`（`dd if=/dev/mtd0 bs=4096 count=256`），零写入。
- 设备当前运行的是 run-3 的 RAM 链内核（网络 + 双频 Wi-Fi 正常）；flash 仍是旧的 patch-0011 U-Boot
  （`g2797f3dd3860`）——重新上电会回到旧链（无网络/无 Wi-Fi）的已知状态，未做任何恢复动作。
- `/etc/e2631-version` = ImmortalWrt v1.10.0，kernel 6.18.60，panic/Oops 计数 0。

## 8. 下一步（需 Lead/用户 GO）

1. **Session B**：env 恢复（`0xC0000` 块回到 `6e2c01da...`）+ 新 mtd0 镜像刷写梯（v3 的 `e2631-uboot-mtd0.bin`，
   sha256 `f6d179da...`），每步断言 readback；本会话只验证了 RAM 链，flash 链尚未写入。
2. **Session C**：物理断电冷启动，验证 BootROM → secondboot → 我们 flash U-Boot → e2631boot → 内核 + 网络 + Wi-Fi。
3. 观察项跟进：Wi-Fi ready latency 176 s vs 54 s（§5），以及在 flash 链上复测端点/双频。

## 9. 附件（[uboot-a6-session/](uboot-a6-session/)）

| 文件 | 内容 |
| --- | --- |
| `tool-c1b1_a6_pcie.py` | run-3 实际驱动（含 pci 时序缺陷） |
| `tool-c1b1_a6_pcie-fixed.py` | 修正版驱动（未在本轮真机运行） |
| `tool-a6_postcheck.py` | 独立判据脚本（重算 product_verdict） |
| `preflight-run3.json` | run-3 前置事实 |
| `session-results.json` | run-3 驱动结果（artifact contract、refclk、GPIO 门禁、内核标记、早期探针） |
| `driver.stdout.txt` / `session-driver.txt` | 驱动控制台与驱动日志 |
| `serial-a6-segment.txt` | 串口选段（refclk before/after、GPIO 两字、e2631boot、bootm） |
| `boot-a6-tail.txt` | 内核启动选段（e2631soc、PCIe、eth、Wi-Fi 重试） |
| `device-readonly.txt` | 只读 SSH 终态采集 |
| `v2-run1-gate-excerpt.txt` / `v3-run2-gate-order-excerpt.txt` | 前两次中止输出（冷值门禁，零写入） |
| `postcheck.json` | 独立判据结果：product_verdict=GREEN，21 项全过 |
| `artifact-SHA256SUMS.txt` / `artifact-UBOOT-INFO.txt` | CI 产物自带校验与构建信息 |
| `SHA256SUMS.txt` | 附件校验和 |

