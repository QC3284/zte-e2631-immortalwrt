# A5 真机会话：patch 0012 网络参考时钟 / SerDes 重放的零写入验收（2026-11-22）

> 会话驱动、串口/内核选段、残余差分与零写入实证都在 [uboot-a5-session/](uboot-a5-session/)；
> patch 0012 的设计、CI 产物与寄存器表见 [uboot-a5-20261122.md](uboot-a5-20261122.md)（base-builder / Lead 维护，本文不重复）。

## 0. 结论

| 项 | 结果 | 证据 |
| --- | --- | --- |
| e2631refclk 契约（7 个寄存器 before/after） | **PASS** | run-3 串口选段；e2631boot 内再次执行同样命中 |
| SerDes 0x9fe00000 24 字读回 | **PASS** 24/24 | `run3-session-results.json` |
| 以太网（PHY 10-13 / lan1 / wan 1 Gbps / mdio_wclk 2.5 MHz） | **PASS（已确认修复）** | 内核日志 2.72 s 枚举四 PHY，14.6 s / 30.6 s lan1 Link Up，31.8 s wan Link Up |
| PCIe 端点（14c3:7906 / 14c3:790a） | **FAIL（确定性）**——patch 0012 把 flat GPIO 2/51 拉低，端点被按在复位里 | run-3 内核日志两条 `Device not found`；根因见 §5 |
| MT7916 / Wi-Fi | **FAIL（确定性，PCIe 的后果）** | run-3：`previous initialization unfinished`、`wifi-on: done: 7906= 790a=`、无 mt7915e 绑定 |
| 零 flash 写入 | **PASS** | mtd0 sha256 前后都是 `d571b764...d286b0f5` |

一句话：本次会话 **PARTIAL**。patch 0012 的网络参考时钟/SerDes 与**以太网缺口确认修好**；
PCIe/Wi-Fi **确定性失败**——iwrt-baseline 的逆向确认 0012 把 flat GPIO 2/51 驱动为低，而厂商是在板级表
回放后把它们拉高（deassert PCIe 端点复位/使能），所以端点每次都停在复位里。修复 = patch 0013
（表回放后把 pin 2 / pin 51 拉高），A6 会话验收。此前草稿把一次厂商链启动误记为 A5 镜像的 PCIe 成功，
已在 §4 复核并更正。

## 1. 输入与产物

| 项 | 值 |
| --- | --- |
| uboot-build CI run | `44929440623`（kit commit `a8c5b91`，patch 0012 的 bit26 修正版） |
| artifact | `/home/qc233/zte/e2631-t5-artifacts/uboot-a5-44929440623/e2631-uboot-44929440623/` |
| `u-boot.bin` | 450,904 B，sha256 `e3c52ba4132910b1807708eadfc8a6f7c7b9740782e84df6afa6d2e7a861ecf2`，首字节 `b8 00 00 ea` |
| banner token | `U-Boot 2027.01-rc2-g9a7538311376` |
| `e2631-uboot-mtd0.bin`（本次未刷） | 655,360 B，sha256 `367b8fa63364d302bc13ade4dd6f9edcd2a49a706a906207fb33e9dc8ced8b41` |
| 组装头块 sha256 | `a80e94e876cb41af784ce420e24a2c0891c2328714d61b55c8266cb43b8a5fbb`（长度字段 0x6E158、payload==u-boot.bin、尾部 FF） |
| 入口 / 期望指纹 | 0x47F00000；冷启动后 PLL0 `80040faa`、PLL1 `00353f7d`、CTRL8 `10061fcf`、CTRL4C `00038000`、CRM2_10 `0`、LSP1_04 `0000081b` |
| 设备 / 基线 | ImmortalWrt v1.10.0（r0-86cddb7）、mtd0 sha256 `d571b76404df1596dd58b710cff84e1ede92e6a29798abe5dcc50198d286b0f5` |
| 捕获链 | 会话期间由 serialhub 接管、结束后恢复 supervisor-002 / bootwatch-002 |

## 2. 三次尝试（前两次中止但都留下了证据）

| 次 | 模式 | 结果 | 中止原因 |
| --- | --- | --- | --- |
| run-1 | `reboot`（从厂商链 Linux `reboot -f` 进我们的 flash 提示符） | 01:29:46 指纹 MATCH 后中止 | 驱动缺陷 1：pre-dump 把已经是字符串的 md 键再 `%x` 格式化，`TypeError`；未 loadx、未 go |
| run-2 | `attach`（复用 run-1 停住的 flash 提示符） | 01:38:26 patch-0012 装入 RAM、md 校验 OK、出现新 banner 后中止 | 驱动缺陷 2：`stop_autoboot` 收到 bytes 去 `.encode()`，`AttributeError`；**e2631refclk 未执行，U-Boot autoboot 继续把内核启动起来了（见 §4）** |
| run-3 | `reboot` 完整流程 | 01:40:33–01:45:44，VERDICT FAIL（仅 `pci_790a` 为 false） | 正常跑完；驱动缺陷 3 是判定口径问题（Wi-Fi 探针把回显的命令文本当输出，手动复核见 §3） |

三次尝试的串口/驱动控制台都在附件里；run-1 与 run-2 都**没有**执行任何 `mtd write` / `nand write` / `saveenv`。
## 3. 观察 A：run-3 正式会话（PCIe FAIL）

时间线（驱动控制台 + 串口）：

```
01:40:34 WAKE 当前 Linux shell → reboot -f 进入 flash 链
01:40:36 我们的 flash banner；停 autoboot
01:40:39 COLD FINGERPRINT MATCH
01:40:40 PRE DUMP words=200（7 个寄存器块）
01:44:32 patch-0012 U-Boot 在 RAM 校验 OK；新 banner g9a7538311376；prompt version ok=True
01:44:36 e2631refclk：before/after 全部命中（下表）
01:44:37 post dump：20 个 pre→post 差分，7 个关键寄存器全部等于契约值；SerDes 24/24
01:44:37 e2631boot（bootm，再次执行 refclk 打印）
01:45:10 内核起来；早期探针
01:45:44 VERDICT FAIL（pci_790a=false）
```

e2631refclk 实测（run-3；e2631boot 内的第二次打印逐字相同）：

| 寄存器 | before | after | 契约 |
| --- | --- | --- | --- |
| PLL0 `0x94000050` | `80040faa` | `0004176b` | PASS |
| PLL1 `0x94000054` | `00353f7d` | `144fdf3b` | PASS（bit28 锁位自置） |
| CTRL8 `0x94000008` | `10061fcf` | `10061fff` | PASS |
| CRM2_10 `0x94100010` | `00000000` | `00000100` | PASS |
| CTRL4C `0x9400004c` | `00038000` | `000381ff` | PASS |
| LSP1_04 `0x9a100004` | `0000081b` | `0001381b` | PASS |
| CTRL0C `0x9400000c` | `00417800` | `00517800` | PASS（bits[21:20]=01） |

内核侧（PASS 项）：

```
[    2.724984] zx279128s-eth 92000000.ethernet lan3 (uninitialized): PHY [9a101000.mdio:0a] driver [Generic PHY]
[    2.725845] ... lan2 ... PHY [9a101000.mdio:0b]
[    2.726680] ... lan1 ... PHY [9a101000.mdio:0c]
[    2.727531] ... wan  ... PHY [9a101000.mdio:0d]
[   14.639693] zx279128s-eth 92000000.ethernet lan1: Link is Up - 1Gbps/Full - flow control off
[   31.759736] zx279128s-eth 92000000.ethernet wan: Link is Up - 1Gbps/Full - flow control off
clk_summary: mdio_wclk 2500000 Hz
```

PCIe / Wi-Fi（FAIL 项）：

```
[    1.489381] zx279128s-pcie f000000.pcie: Device not found
[    2.579380] zx279128s-pcie f100000.pcie: Device not found
/sys/bus/pci/devices: 只有 0000:00:00.0 与 0001:00:00.0（都是 1cf2:6830 根端口）
echo 1 > /sys/bus/pci/rescan（约 153 s）后仍无端点、dmesg 无变化
[   31.347973] e2631-wifi-boot: previous initialization unfinished; retrying in 120s
pci-probe 里 wifi-on: done: 7906= 790a=（两个 ID 都为空）
```

驱动自己的 verdict 是 FAIL，唯一原因是 `pci_790a=false`；Wi-Fi 两个布尔当时被“命令回显”污染（驱动缺陷 3），
手动以 dmesg/wifi-on 原始输出为准，结论同样是 Wi-Fi FAIL。

## 4. 观察 B 复核：那是厂商链的启动，不是 A5 镜像（已更正）

草稿曾写“run-2 中止后自动启动的同一条 RAM 链上出现了两个 14c3 端点和 MT7916 ready”。复核结论：
**该说法错误，现予撤回。**证据：

- `e2631-serial-boot-002.log` 是捕获链的**累计**日志，包含本次会话之前多个会话的启动段，不能只看行号就归给 run-2。
- 该段（`Starting kernel ...` 在行 5587）前面紧邻的是厂商启动路径：行 5395 是 `U-Boot 2013.04 (Aug 28 2023 - 18:40:22)`，
  行 5555–5586 是 `zteboot_do_settings` / `zteboot_search_firmware` 的表与 `bootm` 输出，行 5586 的 `Starting kernel`
  来自厂商 `bootm`，不是我们的 `e2631boot`。
- 决定性反证：全日志 `grep -c 'g9a7538311376'` = **0**，即 **A5 镜像的 banner 从未出现在捕获日志里**；
  同样没有我们 flash U-Boot 的 `g2797f3dd3860`。带 PCIe 枚举的段（行 5042/5087 与 5587/5636 两处）
  都属于厂商 U-Boot 2013.04 的启动链（例如 00:40 的厂商对照会话：loadx vendor U-Boot → go → 厂商控制台 → `cspstart`）。
- run-2 自己的 hub 日志在装入 patch-0012 后的 autoboot 前就结束了；驱动中止后没有留下“A5 镜像启动内核”的
  完整 loader 行。因此**没有任何一条日志能证明 A5 镜像枚举过 PCIe**。

结论：A5 镜像的 PCIe/Wi-Fi 失败是**确定性**的，与厂商链的 PCIe 正常并不矛盾——厂商在做板级初始化时
把 flat GPIO 2/51 拉高，而 patch 0012 把它们拉低。附件 `interim-capture-lines.txt` 保留原摘录，
本节为归属更正；`docs/README.md` 索引文字同步改为确定性失败。

## 5. 根因（iwrt-baseline 逆向，已由 A5 数据佐证）

iwrt-baseline 的静态逆向 [`p2-vendor-pcie-init-20261122.md`](p2-vendor-pcie-init-20261122.md) + base-builder 的
vendor 反汇编给出确定性解释：厂商 `zte_gpio_init()` 在板级表回放之后还有两段循环（`0x47f2f61c`、`0x47f2f66c`），
把表项 51 与 50 对应的输出脚 **pin 2 / pin 51 强制拉高**（表值为 0，间隔约 4 ms），作用是对 PCIe 端点
deassert 复位/使能。patch 0012 按板级表值把这两脚驱动为**低**，于是两个端点被按在复位里，内核只能看到
root port（`Device not found`），Wi-Fi 随之起不来——这与 run-3 的两条 `Device not found` 和
`wifi-on: done: 7906= 790a=` 完全一致。

修复 = **patch 0013**（`uboot-port/patches/0013-...`，CI run `44934077401`，kit tip `384bb73`）：在 0012 的
`e2631_pinmux_gpio_init()` 末尾补上这两次特例拉高，SET 位 RMW、幂等。A6 会话验收其效果。

**之前列出的 H2（双次执行）/ H3（读侧影响）不再是解释 PCIe 失败所必需**：失败可由 0012 的低电平确定性解释。
A6 仍默认采用“只经 `e2631boot` 执行一次”的路径以去掉这两个变量；`--with-refclk` 才显式跑 `e2631refclk` + post-dump。

## 6. 残余差分（我们 post 状态 vs 厂商 post-init，200 vs 220 字）

10 个字（`residual-vs-vendor.txt`）：

| 寄存器 | 我们 | 厂商 | 归属 |
| --- | --- | --- | --- |
| `0x94400018` | `0400001b` | `0400081b` | bit11；base-builder：LSP0 CRPM SPI 时钟（内核 clk 驱动 offset 0x18 `spi`），与 PCIe 无关 |
| `0x94407014` | `0000db28` | `0000db2c` | bank0 DATA bit2 = **pin 2**（H1） |
| `0x94407020` | `00000100` | `00000104` | bank1 DIR bit2（pin 2 对应） |
| `0x944070d4` | `0000e020` | `0000e028` | bank6 DATA bit3 = **pin 51**（H1） |
| `0x944070e0` | `00000000` | `00000008` | bank7 DIR bit3 |
| `0x9a101004/8/14/18/1c` | `0` | `8f08` / `1040` / `19a0` ×3 | MDIO 控制器内部，内核 MDIO 驱动会重初始化，忽略 |

（pin 2 / pin 51 的两次 vendor 强制拉高与厂商 `output gpio: ...` 打印里 2=0、51=0 的“表值”矛盾，
说明覆盖发生在表回放之后——这正是 patch 0013 要补的顺序。）

## 7. 零写入与设备状态

- 会话内没有任何 `mtd write` / `mtd erase` / `nand write` / `saveenv` 命令；所有设备操作只有 loadx（RAM）、md、go、
  e2631refclk、e2631boot（bootm 的 RAM 链）以及只读 SSH。
- 会话后只读 SSH（直连 USB 网卡，`ip route get 192.168.1.1` 不含 `via`）核对：mtd0 sha256 仍为
  `d571b76404df1596dd58b710cff84e1ede92e6a29798abe5dcc50198d286b0f5`（= 会话前 preflight 值），
  `VERSION=ImmortalWrt v1.10.0`、`KERNEL=6.18.60`、`PANICS=0`、uptime 1202 s（`zero-write-check.txt`）。
- 设备当前运行的是 run-3 的 RAM 链内核（eth 起、PCIe/Wi-Fi 未起）；flash 里仍是 patch-0011 的 U-Boot（`g2797f3dd3860`）。
  重新上电会回到我们的 flash U-Boot → e2631boot → 同样的无网络状态；没有做任何恢复动作。

## 8. 下一步（A6）

1. 等 base-builder patch 0013 的 CI 产物（run `44933539990`）交到 Lead，Lead 发 GO + 用户确认（零写入，一次 reboot 或冷启动）。
2. A6 步骤：flash 提示符 → 指纹门禁 → loadx patch-0013 `u-boot.bin` 到 0x47F00000 → go → 新 banner →
   **md.l 0x94407014 1（bit2=1）与 md.l 0x944070d4 1（bit3=1）** → e2631refclk（契约不变）→ e2631boot → 内核。
3. A6 验收：`lspci`/`/sys/bus/pci/devices` 出现 14c3:7906（bus0）与 14c3:790a（bus1）、mt7915e 绑定、
   `e2631-wifi-boot: MT7916 ready`、无 `mt7916 init failed`；mtd0 sha256 不变；剩余差分重算。
4. A6 GREEN → 才讨论 Session B（env 恢复 + 刷写梯）与 Session C（物理断电终裁）；两者仍需 Lead GO。

## 9. 附件

| 文件 | 内容 |
| --- | --- |
| `uboot-a5-session/tool-c1b1_a5_refclk.py` | 会话驱动（548 行；指纹门禁、pre/post md、loadx、e2631refclk、SerDes 读回、e2631boot、内核探针、verdict） |
| `uboot-a5-session/tool-a5_pci_probe.py` | 只读 PCIe/Wi-Fi 诊断 |
| `uboot-a5-session/preflight-run3.json` | run-3 前置事实（artifact/基线/设备/捕获链） |
| `uboot-a5-session/run3-session-results.json` | run-3 全量结果（pre/post words、refclk 值、SerDes、探针、verdict） |
| `uboot-a5-session/run1-driver-console.txt` / `run2-driver-console.txt` | 前两次中止的驱动控制台 |
| `uboot-a5-session/run2-loader-tail.txt` | run-2 hub 尾部：patch-0012 banner 装入 RAM |
| `uboot-a5-session/run3-prelude-refclk.txt` | run-3 串口选段：新 banner、refclk before/after、prompt |
| `uboot-a5-session/run3-kernel-evidence.txt` | run-3 内核证据：PHY/link、PCIe Device not found、Wi-Fi 重试 |
| `uboot-a5-session/interim-capture-lines.txt` | 观察 B 的捕获链选行（PCIe up、14c3:7906/790a、MT7916 ready） |
| `uboot-a5-session/residual-vs-vendor.txt` | 10 个残余字与 refclk/SerDes 摘要 |
| `uboot-a5-session/pci-probe.json` | 只读诊断结果（rescan 无效、wifi-on 空） |
| `uboot-a5-session/zero-write-check.txt` | 会话后只读 SSH 的 mtd0 sha256 与健康数据 |
| `uboot-a5-session/artifact-SHA256SUMS.txt` / `artifact-UBOOT-INFO.txt` | CI 产物自带校验与构建信息 |
| `uboot-a5-session/SHA256SUMS.txt` | 附件校验和 |

