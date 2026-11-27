# F2b：U-Boot 发送路径出口死路的定位（task-78）

结论：F2 会话里“发不出去”不是 BMU 分配失败、也不是发送函数报错——加密完成后流量管理器**确实**收走了
描述符（TX_DONE 轮询从不超时，TM 中断状态出现 0x7700/0x2700 的新位），但主机线上与本机任何 MAC 端口的
TX 计数都看不到帧。也就是说帧在“TM/包处理器 → MAC 端口”之间被丢掉了。本补丁把唯一的运行期变量
（描述符变体）和三个可能的丢包点（CPU 桥端口 egress mask、VLAN 成员、TM 硬件读指针）都做成可在
U-Boot 提示符下一次全会话里逐一排除的探针，**不改默认发送路径、不写 flash**。

## 0. 现场事实（evidence/t74-f2-session-20261127.md，verify-docs 零写入会话）

- `dhcp` 42 次 BOOTP（267 s）+ 15 次短超时，无地址；`ping`/`tftp` 同样失败；主机 tcpdump 39 帧全来自主机，
  设备 MAC `00:41:71:00:00:50` 零帧。
- 整个日志 **0 条** `zx279128s: TX completion timed out`、**0 条** `TX buffer allocation failed`
  （0023 的失败诊断没有触发）；BMU BUF_ALLOC/BUF_ID=0、无 pending，分配不是问题。
- 快照：`dma_tx_start=1` 持续为 1；`dma_tx_done` 读为 0（该计数器读后自清，发送里的轮询已经把它读掉）；
  TM 状态在 `dhcp` 后 0x00007700、`ping/tftp` 后 0x00002700（冷启动时已见 0x00005500）；
  `lan1 MAC TX frames` 每次快照都是 0（读的是 port 2 的 0x92280768）；SW_FWD_CTRL=0x00020000、
  SPA 端口使能 1 1 1 1 1；FREE_STATUS 0x110→0x111/0x80000111。
- 同一硬件上 Linux 由我方 U-Boot 启动后四 PHY、lan1 1 Gbps、WAN DHCP 全正常，说明硬件与内核路径没问题，
  问题只在 U-Boot 自己的发送路径。

## 1. 静态对照：三份实现只在描述符上分歧

- **U-Boot 驱动 vs 内核驱动**（drivers/net/zx279128s_eth.c vs target/linux/zx279128/.../zx279128s-main.c）：
  `zx_hw_init`/`zx_pp_init`/`zx_tm_init`/`zx_hw_reset`/`zx_dma_enable`/`zx_mac_enable`/
  `zx_mac_set_speed` 与 TX 描述符逐字一致（queue=40+port，desc[3]=0x3|len<<2），门铃都是向
  `0x92350064` 写 1；差别只有 `dma_wmb()` 对 `mb()`，以及 U-Boot 在门铃后轮询 TX_DONE。
- **厂商 U-Boot 反汇编**（evidence/p2-oob/vendor-uboot-ram.bin，0x47F00000+文件偏移）：
  描述符 word0=0x80（**queue 0**，不是 40+port）、word1=0x10000、word2=0x21000000|len<<9、
  word3=0x2|len<<2（**bit0=0**，内核/U-Boot 是 0x3）。厂商在写门铃前 flush 描述符缓存，
  并从 `0x923501FC & 3` 读“硬件取到的环槽号”，门铃仍是 `0x92350064=1`。
- 厂商初始化在 SBRG 块写 `0x3881c0 = 0xff`（学习开），内核/U-Boot 写 0（学习关，交给 Linux 网桥）；
  厂商还写 `0x1d4000/0x1d4040` 等 SPA 块，我们的值与内核一致。
- 桥块语义（内核 zx279128s-switch.c 注释）：egress mask 决定“源桥端口能把帧发给哪些目的端口”，
  桥端口 0 是 CPU 端口；内核只在网桥事件里改写它，U-Boot 从不写 `0x3883c0`（CPU 源端口的 mask）。
  一旦开关复位把它清 0，CPU 发出的帧就只会在桥块里被丢掉——与现场“TM 收下、MAC 计数不动”吻合。

## 2. 候选与判别方法（按成本排序）

| # | 候选 | 判别手段 | 期望信号 |
|---|------|----------|----------|
| C1 | 描述符变体（queue 40+p vs queue 0；word3 bit0） | `e2631net mode pp/pp-alt/vendor/vendor-alt` + `e2631net tx 3` | 某个模式下 MAC TX frames 增长且主机抓到广播 ARP |
| C2 | CPU 桥端口 egress mask | `e2631net sbrg` 读 0..4；`e2631net sbrg allow` 后重发 | `egress 0:0x00` → allow 后变 0xfe 且帧出现 |
| C3 | VLAN 1 成员 | `e2631net sbrg` 打印 VLAN 1 三个 word | word0 bit0（VALID）或 untag 位缺失 |
| C4 | TM 是否真的取走环 | `e2631net`/`e2631net tx` 打印 `hw tx idx (0x923501FC)` | 发送前后指针前进 |
| C5 | TM 状态位含义 | 发送前后 `TM status`、与厂商链/Linux 对照 | 位模式差异说明是完成还是错误 |
| C6 | DMA 地址窗口（arena 0x45000000 vs 厂商 0x41000000） | 仅在前 5 项都排除后考虑下移 arena（需新构建） | 帧出现 |
| C7 | 学习开关（vendor 0xff vs 内核 0） | 记录对照；directed-egress 不应依赖 | 仅作参考 |

## 3. 本补丁（0031）交付的命令契约

```
e2631net                  # 链路/PHY/MAC/TM/BMU/RX 队列 + TX/桥块全量状态
e2631net tx [count]       # 按当前模式发 count 个 60 B 广播 ARP 探测帧，打印前后状态
e2631net mode [name]      # 查看或切换 TX 描述符变体：0=pp 1=pp-alt 2=vendor 3=vendor-alt
e2631net sbrg [allow]     # 打印 SBRG 学习位/端口控制/egress 0..4 + VLAN 1 三个 word；
                          # allow 把 egress 0..4 恢复为“除自己以外都可发”
```

默认仍是内核描述符（`ZX_TX_MODE_PP`），所以 `dhcp`/`tftp`/`e2631boot` 等正常路径行为不变；
探测帧走的就是 `zx_send_frame()`（与 `send()` 同一条路径），因此结果可以直接外推到 DHCP/TFTP。
输出字段（节选）：

- `tx mode <name>, sent N, failed M`
- `dma ctrl / ring cfg / tx ring`、`tx start / tx done / hw tx idx / last done`
- `last descriptor <w0 w1 w2 w3>`（发送的最后一帧的描述符原文）
- `TM ctrl / TM status`
- `MAC TX frames 0:.. 1:.. 2:.. 3:.. 4:..`（帧若从别的端口出去会在这里显形）
- `SBRG learn / port ctrl / egress 0:.. 1:.. 2:.. 3:.. 4:..`
- `SPA port en ...; SW fwd 0x........`

## 4. 下一次零写入 RAM 会话的检查单（会话 A：我方 U-Boot，仅 RAM 链）

前置：同 A1 方式用厂商控制台把新 `u-boot.bin` 下载到 `0x47F00000` 并 `go`，进入 `=>` 提示符；
主机接 lan1，`tcpdump -i <if> -e -n` 记录。整个过程只读/只发探测帧，不写 flash、不动 env。

```
md.l 0x92340100 1        # TM status 发送前基线
md.l 0x3883c0 1          # CPU 桥端口（port 0）egress mask 写前值
e2631net sbrg            # 记录 egress 0..4、VLAN 1、learn
e2631net mode pp
e2631net tx 3            # 记录全量输出；主机看是否有 60 B 广播 ARP
e2631net mode pp-alt
e2631net tx 3
e2631net mode vendor
e2631net tx 3
e2631net mode vendor-alt
e2631net tx 3
e2631net sbrg allow
e2631net mode pp
e2631net tx 3
e2631net                 # 终态；仍然 hw tx idx 不动且 MAC 计数全 0 → 记录后停
```

判读：只要某个 `e2631net tx` 之后 `MAC TX frames` 有任意端口增长（主机也收到帧），C1/C2 即定位成功，
把命中的模式（以及 `sbrg` 的 egress/VLAN 值）写进本文件 §0；若全部不动，记录 `hw tx idx` 前后值、
`TM status` 前后差、`last descriptor` 四字、`egress 0..4` 与 VLAN 1，作为与
“厂商链 + Linux 链”对照的原始数据（C4/C5 的判别材料）。
`md.l 0x3883c0 1` 的写前值与 `e2631net sbrg allow` 之后的读回值必须成对出现在串口日志里：
这是判断 C2 时「掩码确实被改动」的唯一数据，不能只记终态。

## 5. 风险与边界

- 只加诊断命令与一个运行期开关；默认 TX 路径、`e2631boot`/`e2631flash`/`e2631env`/救援模式语义不变，
  不新增 MTD 写路径（D-U1 白名单仍是 4 个 site）。
- `e2631net sbrg allow` 只写桥块 5 个 egress 寄存器（`0x3883c0..0x3883d0`），不写 flash；
  断电/复位即恢复原值，不影响后续启动。
- 探测帧是 60 B 广播 ARP，不依赖 IP 配置；唯一副作用是主机侧可能看到几条 ARP 广播。
- 若最终确认需要改 arena 地址或默认描述符，另开补丁并重钉 pin；本 patch 不动默认行为。

## 6. 参考

- [evidence/t74-f2-session-20261127.md](t74-f2-session-20261127.md)（F2 会话原始记录与寄存器快照）
- [evidence/e2-session/thin-run2/](e2-session/thin-run2/)（上一次 F2 的串口/JSON/tcpdump）
- [uboot-port/e2-net-driver-design.md](../uboot-port/e2-net-driver-design.md) §5（描述符与 BMU 约定）
- 内核对照：`target/linux/zx279128/files/drivers/net/ethernet/zte/zx279128s-main.c`（TX 路径）、
  `zx279128s-switch.c`（egress mask/VLAN）、`zx279128s-eth.h`（SBRG 寄存器）
- 厂商反汇编：`evidence/p2-oob/vendor-uboot-ram.bin` @ 0x47F00000（`0x47f30a10` 描述符构造、
  `0x47f304ac` 门铃、`0x47f2f314` 板级 GPIO/SBRG 初始化）

## 7. CI 构建与产物（run 46022545621，31 个 patch）

- kit head `642e9b0`（iwrt-adaptation），workflow `uboot-build.yml` run `46022545621`（run 37）SUCCESS；
  post-am tree `55aebf1afad2406965e5ee77a470f5b79f527eb2`，31 个 patch。
- 可复现项：`git am --committer-date-is-author-date` + `SOURCE_DATE_EPOCH=1795103079`（UBOOT-INFO 记录）。
- banner：`U-Boot 2027.01-rc2-ge84e13107885 (Nov 19 2026 - 15:44:39 +0000)`。
- `u-boot.bin` 364,728 B（上限 653,312），sha256 `d493042d98ecea79e11cfa4a3e6b3a31e661851299802a440954963059206380`，
  crc32 `1c354a00`。
- mtd0 镜像 655,360 B sha256 `e1e5ceb3944fd0eb100911dc813a9d2ad9a950cc976c3f02ca245e6badcb99bc`，
  crc32 `48bf0511`；装配后首 0x800 sha256 `e9ec454fdae871f44526b6df30c05dabed97dcbd4e7d7e2259419ef4983df344`。
- env 块 sha256 `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`（未变）。
- D-U1：构建日志 `mtd writer sites: 4 (e2631flash and the e2631env writer; -O2 inlines the static helpers)`；
  `e2631flash safety guards: present`。
- 新增门禁输出：`F2 TX probe gate: default mode pp, probe frames and bridge-block dump present`；
  checkpatch 0 errors / 0 warnings（24 checks，全部为既有 0026 代码的 CHECK）。
- 尺寸：比 E4 修复构建（361,448 B）多 3,280 B（+0.91%）；比 defconfig 瘦身版（320,848 B）多 43,880 B（+13.68%）；
  距 CI 门禁 645,120 B 余 280,392 B。
- 构建产物本地：`/home/qc233/zte/e2631-t5-artifacts/uboot-task78-46022545621/e2631-uboot-46022545621/`
  （SHA256SUMS 11/11 校验通过）。
