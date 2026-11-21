# A5 真机会话：patch 0012 网络参考时钟 / SerDes 重放的零写入验收（2026-11-22）

> 会话驱动、串口/内核选段、残余差分与零写入实证都在 [uboot-a5-session/](uboot-a5-session/)；
> patch 0012 的设计、CI 产物与寄存器表见 [uboot-a5-20261122.md](uboot-a5-20261122.md)（base-builder / Lead 维护，本文不重复）。

## 0. 结论

| 项 | 结果 | 证据 |
| --- | --- | --- |
| e2631refclk 契约（7 个寄存器 before/after） | **PASS** | run-3 串口选段；e2631boot 内再次执行同样命中 |
| SerDes 0x9fe00000 24 字读回 | **PASS** 24/24 | `run3-session-results.json` |
| 以太网（PHY 10-13 / lan1 / wan 1 Gbps / mdio_wclk 2.5 MHz） | **PASS（已确认修复）** | 内核日志 2.72 s 枚举四 PHY，14.6 s / 30.6 s lan1 Link Up，31.8 s wan Link Up |
| PCIe 端点（14c3:7906 / 14c3:790a） | **FAIL（正式 run-3）**，但**同一镜像在 run-2 的自动启动里出现过两个端点** | 见 §3 / §4，判定 INCONCLUSIVE |
| MT7916 / Wi-Fi | **FAIL（正式 run-3）**；观察 B 里正常 | 同上 |
| 零 flash 写入 | **PASS** | mtd0 sha256 前后都是 `d571b764...d286b0f5` |

一句话：**patch 0012 的以太网缺口确认修好**；正式 run-3 里 PCIe 两个主机都在 link training 阶段
`Device not found`，于是 Wi-Fi 起不来；但 run-2 驱动中止后 U-Boot 自动启动的同一条 RAM 链上，
内核枚举到了两个 14c3 端点且 MT7916 ready。两次观察互相矛盾，本次会话无法复现同一状态，
因此 PCIe 侧结论标 **INCONCLUSIVE**，归因交给 patch 0013（GPIO pin 2 / pin 51，见 §5 H1）与 A6 会话。

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

## 4. 观察 B：run-2 中止后的自动启动（PCIe / MT7916 正常）

run-2 在 01:38:26 装入 patch-0012 U-Boot 并校验通过、出现新 banner 后，`stop_autoboot` 抛异常，
驱动随即停止；U-Boot 自己的 3 s autoboot 继续执行 `e2631boot` 把同一镜像的内核启动起来。
捕获链在 01:38:28 恢复（events `reader-start pid=3309788`），随后记录到的这次启动（`e2631-serial-boot-002.log`，行号为文件行）：

```
5586: Starting kernel ...
5596: [    0.589378] zx279128s-pcie f000000.pcie: PCIe Gen.1 x1 link up
5610: [    0.591111] pci 0000:01:00.0: [14c3:7906] type 00 class 0x028000 PCIe Endpoint
5650: [    0.691145] pci 0001:01:00.0: [14c3:790a] type 00 class 0x028000 PCIe Endpoint
5679: [    0.861134] VFS: Mounted root (squashfs filesystem) readonly on device 31:7.
5799: [   54.486818] wifi-on: done: 7906=mt7915e 790a=
5800: [   54.584489] e2631-wifi-boot: MT7916 ready
5801: [   54.836899] e2631-wifi-boot: automatic Wi-Fi initialization complete
```

（同一段内容在日志里因重复 reader 追加了一份，行 5869–5875 是同样序列的副本；摘录见 `interim-capture-lines.txt`。）

**归属说明（诚实标注）**：这次启动的 loader 行没有完整保留（捕获链在 loader 打印后才恢复，日志里还有
重复 reader 段），因此“这一 boot 就是 run-2 自动启动”依据的是驱动时间线 + 内容一致性，而不是一条
`e2631boot:` 行。内核输出本身完整：两个端点、MT7916 ready、Wi-Fi complete 都出现过。
这次启动**没有**执行显式的 `e2631refclk` 命令（驱动在中止前就死了）。

## 5. 归因假设（待 patch 0013 / A6 判别）

**H1（base-builder 2026-11-22 02:05 反汇编，当前最强）**：厂商 `zte_gpio_init()` 在板级表回放之后还有两段循环
（`0x47f2f61c`、`0x47f2f66c`），把表项 51 与 50 对应的输出脚 **pin 2 / pin 51 强制拉高**（表值为 0）。
这两个脚正好对应本次 10 个残余字里的 `0x94407014` bit2 与 `0x944070d4` bit3；vendor U-Boot 对 PCIe
host/PHY 寄存器（0xf000000、0xf100000、0x9500000、0x9600000、0x1c000000、0x2c000000）**零引用**，
所以 bootloader 侧 PCIe 唯一依赖就是这两条 reset/power enable 线。patch 0013 已在 CI（run `44933539990`，
kit commit `21234b0`）里加“表回放后把 pin 2/pin 51 拉高”，A6 会话验证。

**H2（双次执行 / 时序）**：run-3 里 `e2631refclk` 被显式执行一次、`e2631boot` 前又执行一次（`e2631boot` 的 load 路径
自动调用同一函数，所以 run-3 实际执行两次）；run-2 的自动启动只经过 `e2631boot` 的 load 路径（一次）。若序列对 PLL/GPIO 不是幂等（例如两次拉低再拉高
pin 2/51，或 PLL 重复 relock），第二次执行就可能把 PCIe 使能线留在低电平——与 H1 的“低位=无端点”一致。

**H3（读侧影响）**：run-3 在 e2631refclk 与 e2631boot 之间还做了 post-dump（含 `md 0x9fe00000 24` 读 SerDes 块）。
run-2 没有这些读。若 SerDes/时钟块读取有副作用（例如需要时钟域就绪），也会造成两次观察差异；A6 可对比“读与不读”。

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

