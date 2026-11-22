# E2 U-Boot 以太网驱动设计（patch 0018-0020）

## 1. 背景与范围

E2 之前，自定义 U-Boot 已经能把内核从 flash 启动起来（A1/A2/A3/C1b），闪存链的参考时钟/SerDes/GPIO
也已按厂商 `board_eth_init()` 补齐（A5/A6）。但 U-Boot 自己没有网络驱动：更新 mtd0 镜像只能靠串口
loadx（实测约 10.9 KB/s），640 KiB 要 60 s 以上。E2 的目标是把 lan1 接进 U-Boot 网络栈，让
`tftp`/`dhcp`/`ping` 可以在提示符下使用，为后续“以太网 → userdata 暂存 → 重启进 U-Boot →
`e2631flash` 自更新”的路径（D-U1 已交付命令）打基础。

范围（Lead task-66 GO）：

- **做**：MDIO 总线（PHY 10-13）、交换机/流量管理器/DMA 初始化、lan1（switch port 2、PHY 12）的
  发送/接收、固定 16 MiB DMA arena、`e2631net` 状态命令、`e2631flash`/`e2631verify` 的 arena 保护。
- **不做**：其它三个 PHY 的 U-Boot 协议栈、PHY fixup、中断/NAPI、autoboot rescue 与网络引导回退（E3）、
  多队列/多口、DMA 运行时分配。

## 2. 内核驱动的 keep / drop

初始化与帧路径来自 `target/linux/zx279128/files/drivers/net/ethernet/zte/zx279128s-main.c`
（1502 行）与 `docs/.../zx279128s-eth.h`。U-Boot 复用其中的寄存器序列与位域，丢掉 Linux 专属部分：

| 内核代码 | U-Boot 处理 |
| --- | --- |
| `zx_hw_init()`（复位/门控/PP/TM 表/BMU/DMA 环/交换机/MAC 初值） | 移植进 `drivers/net/zx279128s_eth.c`，逐字段同值 |
| MDIO（`mdio-zx279128s.c`） | 新 `zx279128s_mdio.c`，只保留 clause-22 devad 0 的 read/write |
| `dma_alloc_coherent` 的 16 MiB arena | 固定地址 `0x45000000`（U-Boot 不做运行时 DMA 分配） |
| NAPI/中断/RX 环形收包 | 轮询：RX queue 0 计数 + 描述符解析；TX 轮询 `TX_DONE` |
| `netdev`/`sk_buff`/多口/PHY fixup/ethtool | 不搬；单一 `eth_ops` 端口 |

## 3. 初始化顺序（`zx_hw_init()`）

1. 主复位 `0x92000008`=0 → 10 ms → `0xffffffff`；五口 disable、DMA disable、`BMU_CTRL`=0。
2. `TM_INT_MASK`=全 1；`0x92040018` 清低 2 位；`0x9204001C`=`0x1f`（五口时钟）；PP 复位/桥/分类器。
3. 两张空闲索引表（tab0 4096 项、tab1 512 项，big-endian u16=i）→ `mb()`。
4. 1168 条 TM 队列表：CPU 队列 0-15 的 limit = 1023 + 上次残留，16-399 = `0x00800400`；RED 384 条 =
   `0x00200020`；SCHED 384 条 = `0xff803fff/0x0100ff80/0x00100200/32`。
5. TM 缓冲池/表地址：`0x923400E8/EC`=tab0/tab1、`0xF4/F8`=arena/arena+8 MiB、`0xF0`=rx ring、
   `0x08000800` 表上限、`16` 起始。DMA/TM 控制值（`0x28`=1、`0x2C`=1、RX IRQ 节流、`0x7F`、32/32、
   `0x388`=`0x00131217`、`TM_CTRL`|=b6）。
6. BMU：`CTRL`=0、CFG1/2=`0x0104c040`、LIMIT1=127、LIMIT2=15、THRES1=`4096<<16`、THRES2=`0x2000000`、
   `0x3A00E0`=17、`CTRL` bit0 使能。4096 个 2048 B 缓冲（2048 个时 BMU 在冷启动后不填外部 free list）。
7. 描述符环清零：TX 1024×16 B、RX 8 队列×0x4000；写 `DMA_AREA50`、`DMA_TX_RING`、`RING_CFG`=`0x00400040`，
   读一次 `TX_DONE` 清计数 → `mb()`。
8. 交换机：转发开、7 个 port index 使能、上下行所有 class 使能、trap IPv4/IPv6/ARP/VLAN、清端口过滤。
9. 五个 MAC 口写厂商初值并设 1000M full，全部 disable；真正使用的口由 `start()` 再 enable。

## 4. 16 MiB arena 与内存图

arena = `0x45000000..0x45FFFFFF`，布局与内核一次的 `dma_alloc` 分配一致：

| 偏移 | 用途 | 大小 |
| --- | --- | --- |
| `+0x000000` | BMU 缓冲池（4096 × 2048 B） | 8 MiB |
| `+0x800000` | tab0（4096 × u16） | 0x2000 |
| `+0x808000` | tab1（512 × u16） | 0x400 |
| `+0xA00000` | RX 环（8 队列 × 0x4000） | 0x20000 |
| `+0xB00000` | area50 | 0x100000 |
| `+0xC00000` | TX 环（1024 × 16 B） | 0x4000 |

相邻地址（全部固定，不重叠）：

```
0x40000000  DRAM base
0x40000100  ATAGS（0008）
0x40008000  内核 load
0x42000000  uImage / TFTP 暂存（可用：0x43000000 也安全）
0x44000000  e2631flash bounce buffer（1 MiB）
0x45000000  16 MiB network DMA arena   ← 网络启动后是活数据
0x46000000  空闲
0x47F00000  U-Boot 链接/入口
0x48000000  初始栈
...
```

arena 与 bounce buffer、内核、uImage 的边界在 `e2631flash.c` 里有 `static_assert`；运行期
`e2631_check_ram_range(tag, src, len)` 同时检查“在可用 DRAM 内”和“不与 arena 重叠”，`e2631flash`
与 `e2631verify` 都走它。

## 5. TX / RX 描述符与 BMU

- **BMU alloc**：写 `0x92348014` bit0 → 轮询 busy 清 → 读 `0x9234800C`（bit31 有效，低 16 位 bp）。
- **BMU free**：轮询 `0x923480DC` 的 free-slot 位 → 写 bp 到 `0x92348010`。
- **TX 描述符（16 B）**：`desc[0]=0x80|(queue<<20)`（queue = 40 + switch_port = 42）、`desc[1]=0x10000`、
  `desc[2]=0x21000000|((len&0x3fff)<<9)`、`desc[3]=0x3|((len&0x3fff)<<2)`；byte7=(bp&0x7f)<<1、
  byte8=bp>>7。写 `0x92350064`=1 启动，轮询 `0x92350068` 低 16 位完成计数（读清）。数据区
  `arena + bp*2048 + 16`。
- **RX**：读 `0x92350100`（queue 0）低 16 位可用帧数；描述符 byte7/8→bp、`desc[3]` bits15:2→len、
  byte6 bit0→class；数据区同 TX。**先清 4 个描述符字再归还** RX slot，因为满环时硬件会立刻复用 slot；
  归还用 `count<<4|class<<3|queue` 写 `0x92344068` 再置 `0x92344064` bit0。
- 发送长度 < `ETH_ZLEN` 时补零到 60 B；>1536 B 拒绝。

## 6. 生命周期与输出契约

`start()`：`e2631_net_refclk_init()`（A5 的时钟/SerDes，幂等）→ `zx_hw_init()` → `dm_eth_phy_connect()`
→ PHY 12（`phy-handle=<&phy12>`）`phy_config`/`phy_startup` → link 检查 → MAC speed/duplex、trap MAC、
DMA enable、TM 中断全屏蔽 → 打印 `zx279128s: lan1 up, <speed> Mbit/s <duplex> duplex, MAC <mac>`。
`stop()`：DMA/MAC disable。`write_hwaddr()`：网络已启动时重写 trap MAC。

`e2631net` 输出（供会话脚本解析）：

```
e2631net: lan1 switch port 2, started|stopped
e2631net: PHY 12 link up|no link, <speed> Mbit/s <duplex> duplex
e2631net: MAC ctrl 0x........, TM int 0x........, BMU free 0x........, TX done <n>
e2631net: RX queue counts <q0> <q1> ... <q7>
```

## 7. 验收

CI（`uboot-build.yml`，静态）：post-am tree `10ade1ec0f7a3a7943783d6ba6146840fda6d4bf`、20 patches；
E2 配置符号全 `=y`；内嵌 DTB 含 `zte,zx279128s-gmac`/`zte,zx279128s-mdio`/`ethernet-phy`；二进制含
`e2631net` 与 `lan1 up`；源码形状：驱动调 `e2631_net_refclk_init`、`refclk_done` 幂等、
`e2631flash.c` 的 arena 常量与 `e2631_check_ram_range("e2631verify", ...)`、DTS 的 `zte,switch-port`；
MTD 写入口白名单保持 4 site（E2 不新增 MTD 写路径）。checkpatch 0 errors / 25 reviewed warnings。

真机（另排会话，零 flash 写）：按 README §5.4 跑 `e2631net` / `mii info`（PHY 10-13，lan1=0x0c）/
`dhcp` / `ping <host>` / `tftp 0x43000000 <file>`（不要用 arena 地址）/ `e2631verify`；记录串口日志。

## 8. 风险与回滚

- 单口 lan1；lan2/lan3/wan 走内核，PHY fixup/多口留 M2。
- TX/RX 轮询、无中断：大文件 TFTP 会占满 CPU；仅用于救砖/更新，可接受。
- arena 固定地址：改地址必须同时改 `zx279128s_eth.h` 与 `e2631flash.c`，CI 形状门禁会失败；
  tftp 目标必须避开 arena。
- 回滚：E2 是三个独立 patch，可单独 revert 0018-0020（0018 的共享头被 0019/0020 依赖，需按 0020→0019→0018
  逆序）；A5/A6 的时钟与 GPIO 不受影响，e2631boot 启动路径不变。
- 尚未真机演练：CI 只证明编译、配置、设备树与形状；第一次真机会话按 README §5.4 验收。

## 9. 参考

- [README.md](README.md) §2/§3/§4/§5.4
- [a5-net-refclk-design.md](a5-net-refclk-design.md)（时钟/SerDes 序列）
- `target/linux/zx279128/files/drivers/net/ethernet/zte/zx279128s-main.c`、`zx279128s-eth.h`（内核同硅片实现）
- `drivers/net/zx279128s_eth.h` / `zx279128s_eth.c` / `zx279128s_mdio.c`（patch 0018-0020）
