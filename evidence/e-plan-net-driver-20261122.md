# 多功能 U-Boot E1：U-Boot 以太网驱动移植可行性调研（task-65）

> 日期：2026-11-22 · 性质：只读静态调研（内核源码 + U-Boot 2027.01-rc2 源码 + 厂商 U-Boot 反汇编 + 既有真机证据）。
> 本文件不包含任何代码改动；设备未操作。结论落盘于本文件，供 E1 实施（patch 0018+）直接引用。

## 0. 结论

可以只做一个 MAC 口、只走 CPU 路径；不需要 PPE/NAT 卸载，也不需要交换机 VLAN/bridge 卸载。但交换机核心、TM/BMU/DMA 和 PP bridge 的初始化不能省——它们不是加速选件，而是 CPU 收发帧的必经通路。patch 0012 已经把参考时钟/SerDes/pinmux 做完（e2631net.c:227 的 e2631_net_refclk_init），剩下的是 GMAC 寄存器块（0x92000000，4 MiB）里的初始化序列和 TX/RX 描述符路径。

工作量判定：3 个 patch / 约 1100–1200 行 / 3 个里程碑，不是 1 个 patch 能收的。最可能的拦路虎是 TX/RX 数据通路的初始化顺序（PP bridge 的 mode-2 TX、TM/BMU/DMA、trap 表），不是 PHY；PHY 侧已有真机证据表明 genphy 就够用（见 §3.11）。

对 Lead 四个框架问题的直接回答：

| 问题 | 回答 |
|---|---|
| 一个 MAC 口能否在 CPU/FFE 路径上工作，不做 PPE offload、不做 switch VLAN？ | 能。PPE（zx279128s-ppe.c）与 FFE（zx279128s-ffe.c）都是运行期软件加速设施，基础收发的数据通路不经过它们。 |
| 是否必须先把 switch 初始化？ | 是，但只指 SoC 的 switch 核心（forwarding/trap/port enable）与 PP bridge（sbrg/classifier 最小集）；不需要 VLAN 表、FDB、bridge offload 这些交换机高级逻辑。内核注释明说 mode-2 TX 走 PP bridge，且 bootloader 只在 TFTP 时初始化它（zx279128s-main.c:360-363）。 |
| 是否还需要 0012 之外的时钟/SerDes 工作？ | 不需要再写 PLL/SerDes；但 U-Boot 自己用网口时必须在 eth start 时主动调用 e2631_net_refclk_init()（当前只有 e2631boot 在 load 内核前调用，见 e2631boot.c:319），并把它做成幂等。 |
| 代价 | 3 个 patch（0018/0019/0020），约 1100–1200 行新增/改写，两个功能补丁 + 一个收尾补丁；3 个里程碑见 §5。 |

## 1. 基线（2026-11-22 实测）

- U-Boot：2027.01-rc2，flash 链自我验收 banner g85df6772a444（evidence/t61-uboot-flash-acceptance-20261122.md:14）。最近一次构建载荷 450,936 B（/home/qc233/zte/e2631-t5-artifacts/uboot-a6-44934077401/e2631-uboot-44934077401/u-boot.bin）。
- 镜像上限：U-Boot 载荷区 0x20000..0xC0000，上限 0x9F800 = 653,312 B（uboot-port/README.md:42、:287-288）。当前余量约 202 KB。
- 内核源（tree /home/qc233/zte/iwrt-tree/target/linux/zx279128）：files/drivers/net/ethernet/zte/zx279128s-main.c 1502 行、zx279128s-ffe.c 403、zx279128s-ppe.c 854、zx279128s-switch.c 354、zx279128s-eth.h 385、files/drivers/net/mdio/mdio-zx279128s.c 157、files/drivers/net/phy/sanechips.c 152；总计 3852 行。
- 现有 U-Boot 补丁序列 0001–0016（uboot-port/patches/，0016 为跨槽回退）；网络相关只有 0012 参考时钟/SerDes/pinmux（e2631net.c:227），以及 0013 的两条 GPIO 晚驱动。
- env：厂商模板已含 ipaddr=192.168.1.1、serverip=192.168.1.100、netmask=255.255.255.0、gatewayip=192.168.1.1、ethaddr=00:41:71:00:00:50、ethact=eth0（evidence/b1-env-current-20261121.txt:8-18）。
- 真机内存布局（闪存链 U-Boot 提示符 bdinfo，evidence/c1b1-flashboot-20261121.md:37）：DRAM 0x40000000/0x10000000（256 MiB），boot_params 0x40000100，relocaddr 0x4ff94000，fdt 0x4fff0ff0；kernel 由 e2631boot 从 0x42000000 搬到 0x40008000（e2631boot.c:77、:81、:497）。
- 本调研的厂商 U-Boot 反汇编对象：evidence/p2-oob/vendor-uboot-ram.bin（426,048 B，sha256 a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30，vaddr = 0x47F00000 + file offset）。

## 2. 内核驱动的 keep/drop 表

| 源文件（行数） | 移植（约） | 丢弃（约） | 判定与理由 |
|---|---:|---:|---|
| zx279128s-main.c（1502） | 740 | 762 | 保留：BMU/RX 释放/端口/MAC、TM 间接窗口与表初始化、pp_init、hw_reset、hw_init、TX、RX（行段见下）。丢弃：netdev/phylink/ethtool/MIB/debugfs/probe 的 Linux 胶水，由 U-Boot eth_ops 重写替代。 |
| mdio-zx279128s.c（157） | 62 | 95 | 保留：clause-22 传输协议（:41-96）与控制器初始化寄存器（:124-129）。丢弃：clk/devm/of_mdiobus 的 Linux 设备模型部分。 |
| phy/sanechips.c（152） | 0（M1）；可选 70 | 152 | ZX5201 厂商初始化（:60-131）。内核在同一硬件上绑定的是 genphy 且网络正常（§3.11），M1 不需要；若出现 link 只 100M/不稳，再把 config_init 作为 PHY 驱动/fixup 移植。 |
| zx279128s-ppe.c（854） | 6–32 | 822+ | 只保留 trap-DMAC/ONU-MAC 表的 2 条寄存器写语义（:627-658 的 ppe_active=false 分支），其余 NAT/flow 卸载全部丢弃。 |
| zx279128s-ffe.c（403） | 0 | 403 | 软件 flow 卸载（在 PPE 之上），U-Boot 无 IP 转发，不需要。 |
| zx279128s-switch.c（354） | 0 | 354 | Linux bridge/switchdev 卸载、FDB/VLAN，U-Boot 无 bridge，不需要。 |
| zx279128s-eth.h（385） | 约 150 | — | 只取寄存器定义与常量（:31-246），重写成 U-Boot 头文件。 |

main.c 的移植行段（可直接作为编写顺序）：

- BMU 分配/释放 :50-106；RX 槽释放 :122-136；描述符清零/消费 :144-154。
- MAC 速率/使能 :158-192；trap DMAC :237-242；DMA 使能 :244-252。
- TM 间接写/读 :254-300；TM 表初始化 :312-352（1168 次间接写：400 queue + 384 RED + 384 sched）。
- PP bridge/classifier 最小初始化 :356-399；主复位 :402-417；hw_init 总序列 :419-571。
- TX :578-690；RX :705-847（含坏槽重同步与 class 释放）。
- 可丢弃的 Linux 部分：probe/phylink/netdev/ethtool/MIB/debugfs :893-1210、:1211-1452。

## 3. 最小寄存器初始化序列（每步带内核 file:line）

> 顺序不能改：内核在 DMA 和 MAC 静默状态下初始化 PP/TM/BMU，最后才开 DMA（main.c:356-363、:427-430、:1403-1404）。

### 3.0 前置：参考时钟/SerDes/pinmux/GPIO
- 入口：e2631_net_refclk_init()（/home/qc233/zte/uboot-src/board/zte/zxhn-e2631/e2631net.c:227）：PLL 0x94000050/54、TOP CRM 0x94000008、SerDes 24 写 0x9FE00000、CRM2 0x94100010、0x9400004C、0x9A100004、0x9400000C bits[21:20]=01；pinmux/GPIO 表见 :148-224。
- 现状：只有 e2631boot 在 load 内核前调用（e2631boot.c:319）。U-Boot 交互式用网口（dhcp/ping/tftp）时必须先执行它；建议在 eth start 里调用，并在函数内加 static 幂等保护，避免随后 e2631boot 重复执行 PLL/SerDes 序列。

### 3.1 MDIO 控制器（0x9A101000）
- 初始化：读 CMD(0x14)，清 START/BIT15/BIT13，置 CLK_DIV(BIT12)；STATUS(0x10)=0；CFG(0x0C)=0（mdio-zx279128s.c:124-129）。
- 传输：CMD = op|addr<<5|reg，置 START，轮询 STATUS bit0 DONE（10 us 步进、2 ms 超时），读 DATA_RD(0x08) 或写 DATA_WR(0x04)（:41-96）。
- 控制器寄存器是全局的，U-Boot 单进程无需锁。

### 3.2 主复位与时钟门控
- 0x92000008 = 0，等 10 ms，再 = 0xffffffff（main.c:407-410）。
- 关 5 个 MAC 口、关 DMA、BMU_CTRL=0（:412-416）。
- TM_INT_MASK = ~0（:429）。
- 0x92040018 &= ~GENMASK(1,0)；0x9204001c = GENMASK(4,0)（:432-435）。

### 3.3 PP bridge / sbrg / classifier 最小初始化（模式 2 TX 的前提）
- 0x92380000 = 2（PP reset），等 1–2 ms（main.c:365-366）。
- 0x92388004 = 0x000200ff；0x92388008 = 0x0000dfdf；0x923881c0 = 0；0x92388340 = 0xff5ffdff；0x92388344 = 0x3e；0x92388380 = 0x3f；0x9238863c = 0xaaaaaaaa；0x923881c4 = 0x5555；0x92388188 = 0x000bf874；0x923882c0 = 0xff；0x92388300 = 0xffff；0x92388304 = 0x3e（:368-392）。
- classifier：0x9238c080 = 0x0000309a；0x9238c088 = 0；0x9238c0cc = 1；0x923a0010 = 0；0x923a0014 = 0（:394-398）。
- 依据：main.c:360-363 注释——mode-2 TX 走 PP bridge，“bootloader 只在 TFTP 时初始化它，直接 NAND 启动时没有做，所以我们自己做”。

### 3.4 TM 表（tab0/tab1 + 1168 条间接写）
- tab0（0x800000 起点，4096 项）逐项写 big-endian u16 i；tab1（0x808000，512 项）同理（main.c:438-447；尺寸 eth.h:218-219、:238-239）。
- queue 表 400 项：CPU 队列 0–15 用 0x00800400 并加 carries，16–399 用 0；RED 384 项 0x00200020；SCHED 384 项 0xff803fff/0x0100ff80/0x00100200/32（main.c:312-350）。
- 间接窗口：0x92344014 = index|table<<22[|read]，轮询 0x92344018 bit0，数据 0x9234401c+4i（main.c:254-300；eth.h:93-104）。
- 表地址：0x923400e8 = tab0_dma；0x923400ec = tab1_dma；0x923400fc = 0x08000800；0x923400f4 = buf_pool_dma；0x923400f8 = buf_pool_dma + 0x800000；0x923400f0 = rx_ring_dma；0x92340004 = 16（main.c:453-459；eth.h:82-88）。

### 3.5 TM/DMA 控制值
- 0x92350028 = 1；0x9235002c = 1；0x92350030 = 25000（500 us×50）；0x92350034 = 64；0x92350004 = 0x7f；0x92350020 = 32；0x92350024 = 32；0x92350388 = 0x00131217；0x92340000 |= BIT(6)（main.c:464-475；eth.h:136-145）。

### 3.6 BMU
- CTRL=0；CFG1=CFG2=0x0104c040；LIMIT1=4096/32-1=127；LIMIT2=15；THRES1=4096<<16；THRES2=0x2000000；BUF_ALLOC=0；最后 CTRL bit0 使能（main.c:477-490）。
- 必须 4096 个 buffer（8 MiB pool）：2048 个时冷启动 NAND 后 BMU 的 BPPE 外部空闲表填不满，只靠 ~64 项内部 cache（main.c:481-485 注释，实测结论）。

### 3.7 DMA 环
- tx_ring 清 0（1024×16 B，arena 0xC00000）；rx_ring 清 0（8 队列×16 KiB，arena 0xA00000）（main.c:494-501；eth.h:236-245）。
- 0x92350050 = buf_pool_dma+0xB00000（area50）；0x92350060 = tx_ring_dma；0x9235003c = 0x00400040（main.c:507-509）。
- RX 环基址写在 0x923400f0（TM_BUF_F0，名字有误导；内核就是把 rx_ring_dma 写这里，main.c:458）。
- RX 队列计数：0x92350100 + q*4，低 16 位为可用帧数（main.c:710；eth.h:145）。
- 每队列固定 1024 描述符、16 B/描述符、队列步长 0x4000（eth.h:233-245）。

### 3.8 交换机核心
- 0x921cc000 = BIT(17)（FWD_CTRL_ON，main.c:515）。
- 0x921d428c + 4*idx = 1，idx 映射 {0,1,2,3,4,5,6} 对应 port_to_sw_idx（main.c:517-522）。
- 0x921d4000/04、0x921d4040/44 全 0xffffffff（上下行所有 class 送 CPU，main.c:529-532）。
- trap ethertype：0x921d41c4 = ETH_P_IP<<16|ETH_P_IPV6；0x921d41c8 = ETH_P_ARP<<16|ETH_P_8021Q；0x921d41c0 = 0（main.c:541-543）。
- port filter：0x921c0060 + 4*p 清 GENMASK(25,23)（main.c:546-550）。
- trap DMAC：0x921d41a0 + idx*8 写自己的 MAC（低 4 字节、高 2 字节），idx 0（main.c:237-242；eth.h:46-47）；ONU MAC 表 0x921d4120 的 16×8 B 清 0（ppe.c:650-654，ppe_active=false 时写 none）。PPE 未启用时，目的 MAC 是本机的单播靠 trap DMAC 送 CPU（ppe.c:620-624、:655-657）。

### 3.9 MAC 口（0x92200000 + p*0x40000）
- 每口写：ctrl 0x00 = 0x00bbe000；0x08 = 0x80000001；0x04 = 0x0000fffe；0x0e0 = 0x00011200；0x0d00 = 50；0x0d30 = 168；0x070 = 0x00300002；0x0b4 = 0x4000；0x0b00 = 0x0010ff11（main.c:552-565）。
- 速率：1000M 全双工 = 清 ctrl 的 MII/BIT14、置 BIT13（main.c:158-180）；使能位 GENMASK(1,0)（:182-192）。
- 只使能选定的那一个口；其余口保持 ctrl 写好后 disabled（内核先全部 init，再由 open 的 link_up 使能，main.c:223-224）。

### 3.10 DMA 使能与中断
- 0x92350000：清 GENMASK(19,16)，置 BIT21，再置 bit0 使能（main.c:244-252）；内核在 probe 所有 port/NAPI 就绪后才调用（main.c:1403-1404）。
- U-Boot 不用中断：保持 TM_INT_MASK=~0（main.c:429），轮询 RX 队列计数。

### 3.11 PHY（clause-22 + genphy 足够）
- 4 个内部 PHY 在 MDIO 地址 0x0a–0x0d（board dts:215-233：phy10..phy13；端口映射 port0=lan3/phy10、port1=lan2/phy11、port2=lan1/phy12、port3=wan/phy13，board dts:156-190）。
- 真机证据：无厂商 U-Boot 的冷启动链里内核逐个绑定这 4 个 PHY、lan1/wan 1000 Mb/s Full（evidence/t61-uboot-flash-acceptance-20261122.md:14、:126-127）；c1a 日志显示绑定的是 Generic PHY（evidence/c1a-bootm/run-2/boot-segment.txt:113-116），说明内核在这块板上用 genphy 就能 link + 转发。
- 因此 U-Boot 用 phylib 的 genphy 是最小路径；sanechips.c 的 ZX5201 初始化（:60-131）作为 link 异常时的备选。厂商 U-Boot 在 board_eth_init 里还会对 4 个 PHY 的 0x14 寄存器做一次 0x800/0x1140 的 advertise 修正（反汇编 0x47f1fe68/0x47f1fee0），同样列入备选而非 M1。
- U-Boot 侧：phy_connect(bus, addr, dev, PHY_INTERFACE_MODE_INTERNAL) → phy_config() → phy_startup()；genphy 是 U-Boot 内置 fallback 驱动（drivers/net/phy/phy.c:456-465）。

### 3.12 TX / RX 数据通路（U-Boot 必须逐字段复刻）
TX（main.c:661-674；描述符 16 B）：
- BMU 分配 bp：0x92348014 写 bit0 请求，轮询 busy 位，读 0x9234800c bit31 有效、bp=低 16 位（main.c:50-83）。
- 数据区 = arena + bp*2048 + 16；帧拷贝到 +16。
- desc[0]=0x80|queue<<20；desc[1]=0x10000；desc[2]=0x21000000|(len&0x3fff)<<9；desc[3]=0x3|(len&0x3fff)<<2；byte7=(bp&0x7f)<<1；byte8=bp>>7。
- 写 0x92350064=1 启动；0x92350068 低 16 位是完成计数，按它回收（main.c:585-601）。
- queue = 40 + switch_port（eth.h:253；本 board 默认 port2=lan1 → queue 42）。

RX（main.c:709-847）：
- 轮询 0x92350100（q0）；desc: byte7 bit1.. / byte8 得 bp；desc[3] bit2..15 得 len；byte6>>3 得端口。
- 数据在 arena + bp*2048 + 16；class = byte6 & 1。
- 处理完：描述符 4 字清零（main.c:144-154），然后按 class 计数发释放：0x92344068 = count<<4|class<<3|queue，0x92344064 = busy（main.c:122-136）；最后把 bp 还 BMU（0x92348010 写 bp，先确认 0x923480dc 有 free slot，main.c:85-106）。
- 满环/丢槽情况内核有重同步与坏槽跳过逻辑（main.c:727-789）；U-Boot 只做最小子集即可，但“先清描述符、再释放槽”的顺序不能反（main.c:138-143 注释）。

## 4. U-Boot 集成方案

### 4.1 驱动模型与结构
- 新文件 drivers/net/zx279128s_eth.c（DM_ETH 驱动，compatible zte,zx279128s-gmac），Kconfig 符号建议 ETH_ZX279128S（select PHYLIB、PHY_GIGE），Makefile 一行。
- probe：只做 dev_read_addr / mdio_alloc + mdio_register（总线名 zx-mdio@9a101000）、读 PHY 地址与默认端口号；不碰硬件寄存器（MDIO 时钟来自 LSP1，refclk 未跑时访问无意义）。
- start：refclk（幂等）→ §3.2–§3.10 全序列 → phy_connect/phy_config/phy_startup → 按 phydev 的 speed/duplex 写 MAC 并 enable → 写 trap DMAC → DMA enable → TM_INT_MASK=~0。
- send：BMU 分配、拷贝、填描述符、mb()/barrier()、kick、轮询 TX_DONE；环满先等完成（U-Boot 发包极少，等待即可）。
- recv：读 q0 计数，无帧返回 -EAGAIN；有帧解析并返回包指针（指向 arena+16），把 bp/class/queue 记在 priv 里；free_pkt 里清描述符、释放 RX 槽、还 BMU（net/eth-uclass.c:457-458 会在处理完包后调用 free_pkt）。
- stop：TM_INT_MASK=~0、DMA disable、MAC port disable。
- 缓存：当前 defconfig 是 SYS_ICACHE_OFF/SYS_DCACHE_OFF，物理地址即 DMA 地址；仍需在描述符/收发包前后加 mb()（dsb，arch/arm/include/asm/io.h:168）。若以后开 cache，send 前 flush_dcache_range、recv 前/后 invalidate，照 U-Boot 其他 eth 驱动惯例。
- 复用面：DM_ETH 与 eth_ops 定义见 include/net-common.h:304-325；U-Boot 自带 NET/legacy 栈、PHYLIB、genphy，不需要自己实现 ARP/UDP/TFTP。

### 4.2 DTS 增量（arch/arm/dts/zx279128s-zte-zxhn-e2631.dts）
现有 U-Boot DTS 明确未写 Ethernet（该文件第 6 行注释 "Ethernet and ... intentionally left out"）。建议增加：

    mdio: mdio@9a101000 {
        compatible = "zte,zx279128s-mdio";
        reg = <0x9a101000 0x18>;
        #address-cells = <1>;
        #size-cells = <0>;
        phy12: ethernet-phy@c { reg = <12>; };
    };

    ethernet@92000000 {
        compatible = "zte,zx279128s-gmac";
        reg = <0x92000000 0x400000>;
        phy-handle = <&phy12>;
        phy-mode = "internal";
        zte,switch-port = <2>;      /* port2 = lan1，queue 42 */
    };

PHY 地址从 phy-handle 子节点 reg 读取；端口号默认 2（lan1），可被 env e2631ethport 覆盖。内核 DTS 的同一组节点可作对照：SoC patch 026 的 gmac/mdio（patches-6.18/026-...patch:220-255、:424-433），board dts:156-233。

### 4.3 defconfig 增量
当前 configs/zx279128s_zte_zxhn-e2631_defconfig 没有任何 NET/ETH 行（全走默认）。需要显式加入：

    CONFIG_NET=y
    CONFIG_NET_LEGACY=y
    CONFIG_NETDEVICES=y
    CONFIG_DM_ETH=y
    CONFIG_PHYLIB=y
    CONFIG_PHY_GIGE=y
    CONFIG_ETH_ZX279128S=y
    CONFIG_CMD_NET=y
    CONFIG_CMD_DHCP=y
    CONFIG_CMD_PING=y
    CONFIG_CMD_TFTPBOOT=y
    CONFIG_CMD_MII=y

说明：NET/NET_LEGACY 默认 y（net/Kconfig:10-36），NETDEVICES select DM_ETH（drivers/net/Kconfig:96-99）；PHYLIB 无默认（drivers/net/phy/Kconfig:8），PHY_GIGE 无默认（drivers/net/Kconfig:107）；CMD_DHCP、CMD_PING 无默认，必须显式打开（cmd/Kconfig:2250-2255、:2309-2313），CMD_TFTPBOOT 默认 y（:2322-2327）。CMD_MII 便于 bring-up 时 mii info/mii read 逐 PHY 验证。

### 4.4 DMA arena 与内存布局
- 需要 16 MiB 连续 32 位物理内存（kernel 布局：buffer pool 8 MiB + tab0/tab1 + rx/tx ring，相对偏移见 eth.h:236-245）。
- 建议固定基址 0x45000000（16 MiB → 0x45000000–0x45FFFFFF），在 Kconfig/board 头文件中定义。理由与冲突核查：
  - 0x40000000 起 DRAM，0x40000100 是 ATAGS，0x40008000 是内核，0x42000000 是 uImage staging（e2631boot.c:77、:497）。
  - 0x44000000 已被 e2631flash 的 1 MiB bounce buffer 占用（e2631flash.c:64-65），不能用。
  - 0x47F00000 是 U-Boot 链接/预重定位地址；重定位目标在 0x4FF94000 以上（evidence/c1b1-flashboot-20261121.md:37），0x45xxxxxx 两者都不碰。
  - e2631flash 接受 [0x40000000,0x4F000000) 的 RAM 源地址（e2631flash.c:51-52）；实施时应在 e2631flash 里加一条“源地址不得落入 arena”的检查，或文档约定 tftp/e2631flash 不用 0x45000000–0x45FFFFFF。
- 不能靠 malloc：U-Boot 堆在重定位后的高地址区，没有 16 MiB 连续可用空间；固定保留区最稳。

### 4.5 refclk 幂等
在 e2631net.c:227 的函数内加 static bool done（或判断某寄存器已到位）后直接返回；这样 eth start 与 e2631boot.c:319 的第二次调用都不会重复跑 PLL/SerDes 序列（序列含 100/50/100/100/200/200 ms 延迟，重复跑既慢又有扰动风险）。

### 4.6 端口选择与 env
默认 lan1 = switch port2 = PHY12 = TM queue 42。若测试机接在别的口（lan2/lan3/wan），bring-up 期可加 env e2631ethport=1/2/3/4（对应 port/phy/queue）或直接改 DTS 的 zte,switch-port。DHCP/静态 IP 都直接复用现有 env 键（§1）。

### 4.7 镜像大小
当前 450,936 B，上限 653,312 B，余量 202,376 B。legacy net 栈 + phylib + 驱动估计 +50–80 KB，仍有余量；但 patch 0018 起每次 CI 都应对 build/u-boot.bin 加 size <= 0x9F800 断言（uboot-port/README.md:287 已有手工步骤，建议进 CI）。

## 5. 里程碑与零写入测试协议

| 里程碑 | 内容 | 通过判据 |
|---|---|---|
| M1 | driver + MDIO + §3.2–§3.10 + refclk 幂等；DTS/defconfig | 启动出现 Net: eth0: ...；mii info 能看到 0x0c 的 ID/link；e2631refclk 不再必需（start 内已做） |
| M2 | TX 通路 | 主机 tcpdump 看到板子发出的 DHCP DISCOVER/ARP（MAC 00:41:71:00:00:50）；0x92350068 完成计数递增 |
| M3 | RX + DHCP + ping + tftp | dhcp 拿到地址；ping 192.168.1.100 通；tftp 0x43000000 <file> 后长度/内容校验一致 |

零写入测试协议（不写 flash，失败可断电回退）：
1) CI 构建带网口的 U-Boot；核对 size/sha256。
2) 在当前已刷 U-Boot 提示符（v3, g85df6772a444）执行 loadx 0x47F00000，xmodem 送入新 u-boot.bin；再 go 0x47F00000。安全前提：U-Boot 已把自身重定位到 ~0x4FF94000（evidence/c1b1-flashboot-20261121.md:37），0x47F00000 只是镜像/链接地址，覆盖它不影响正在运行的代码；该做法与 C1b-0 的 RAM 链干跑一致（evidence/c1b0-entry-20261121.md）。
3) 在新 U-Boot 提示符上先静态验证：setenv ipaddr 192.168.1.1; setenv serverip 192.168.1.100; ping 192.168.1.100；然后 dhcp；然后 tftp 0x43000000 test.bin 并用 md/主机侧核对。tftp 目标地址不要用 0x45000000（arena）。
4) 全程 CONFIG_CMD_SAVEENV 为关，env 改动只在 RAM；失败直接断电，回到 flash 里的 v3。
5) 主机侧准备：TFTP server root 放 test.bin、抓包（tcpdump -i <if> -e）观察 DHCP/ARP；建议 DHCP server 与 tftp server 同一台（serverip=192.168.1.100）。

## 6. 工作量估算

| patch | 内容 | 行数（估） |
|---|---|---:|
| 0018 | drivers/net/zx279128s_eth.c 骨架 + MDIO + §3.2–§3.10 初始化 + refclk 幂等 + DTS + defconfig + Kconfig/Makefile | 700–800 |
| 0019 | TX/RX 数据通路（BMU 分配/释放、TX 描述符与回收、RX 解析/释放、free_pkt、trap DMAC/MAC 表） | 250–300 |
| 0020 | 收尾：端口/env 选择、e2631net 调试命令（dump TM/BMU/DMA 计数、PHY/链路状态）、文档、CI size 断言 | 100–150 |
| 合计 | 2 个功能补丁 + 1 个收尾补丁 | 1050–1250 |

说明：0017 按 task-59 的既定编号留给 env 写回（e2631env），本 E1 从 0018 起编号。按一次集成会话 4–6 小时估算，M1+M2 约 1 个会话，M3 取决于数据通路调试，可能再 1–2 个会话。

## 7. 风险登记

| ID | 风险 | 可能性/影响 | 依据 | 缓解 |
|---|---|---|---|---|
| R1 | TX 走不通（DHCP 请求发不出/发错口） | 中/高 | mode-2 TX 依赖 PP bridge 与 TM queue 定向（main.c:360-363、:665-668） | 严格照 §3.3、§3.12 顺序；加 e2631net dump TX_DONE；主机抓包定位 |
| R2 | RX 收不到（队列计数不动） | 中/高 | RX 环基址在 TM_BUF_F0、8 队列布局、trap 表任一错都静默失败（main.c:458、:709-847） | 先只开 q0；上电后先 md 0x92350100 看计数；核对 trap DMAC/ethertype |
| R3 | BMU buffer 池不足/耗尽 | 中/中 | 2048 个在冷启动后 BMU 外部表填不满（main.c:481-485） | 固定 4096（8 MiB），按内核参数 |
| R4 | arena 与其它 RAM 用途冲突 | 低/高 | 0x44000000 已被 e2631flash 占用；tftp/e2631flash 可指向任意 [0x40000000,0x4F000000) | arena 固定 0x45000000；e2631flash 加重叠检查；测试协议避开 |
| R5 | PHY link 不上或只有 100M | 低/中 | 内核用 genphy 已 1Gbps（t61 证据）；但厂商 U-Boot 另有 PHY 0x14 fixup | 先 genphy；失败再移植 sanechips.c:60-131 或 0x14 fixup；mii read 逐寄存器定位 |
| R6 | refclk 未执行/重复执行 | 中/中 | 当前只在 e2631boot 调用（e2631boot.c:319），交互 dhcp 前没人跑；序列有 ~750 ms 延迟 | eth start 调用 + static 幂等；M1 用 e2631refclk 交叉验证 |
| R7 | 镜像超 0x9F800 | 低/低 | 现 450,936 B，余量 202 KB | CI size 断言；必要时裁 CMD、MII、IPv6 等 |
| R8 | 缓存一致性 | 低/低 | 当前 caches off；若未来开 cache | mb()/dma barriers；开 cache 时补 flush/invalidate |
| R9 | PHY 地址/端口映射和实物接法不符 | 中/低 | 默认 lan1（port2/phy12）；测试机可能插在别的口 | env e2631ethport 覆盖；M1 前先 mii info 扫 0a–0d |
| R10 | e2631boot 与网口并存时 RAM 互相干扰（tftp 目标/arena/kernel staging） | 低/中 | e2631boot 用 0x42000000；e2631flash 用 0x44000000；arena 0x45000000 | 文档 + 命令里加地址范围检查 |

单一最可能拦路虎：R1/R2 的 TX/RX 数据通路初始化顺序（PP bridge + TM/BMU/DMA + trap 表），不是 PHY。建议 M1 先把所有初始化写完并加 e2631net dump，再分 TX/RX 两步验收。

## 8. 未决问题（需要 Lead/用户拍板）

1. 测试拓扑：U-Boot 网口测试时主机接哪个物理口（默认 lan1）？TFTP/DHCP server 地址是否 192.168.1.100？
2. 是否接受在 e2631flash 中加入“源地址不得落入 arena”的运行时检查（会影响 e2631flash 行为，但只多一段范围判断）？
3. M1 是否需要 mii 命令（CMD_MII，约 +2 KB）以便现场逐 PHY 调试？
4. 是否现在就把 PHY 0x14 advertise fixup / ZX5201 config 一并移植（更稳但增加 0018 行数），还是等 link 出问题再说？
5. 网口在 U-Boot 自动启动路径里的定位：只作为手动 rescue（dhcp/tftp + e2631boot），还是要加自动 TFTP 启动？后者涉及 env bootcmd（厂商 bootcmd 不可持久，见 evidence/p2-flashboot-kernel-hang-20261121.md 与 B1 设计）。
6. 是否保留 multi-port 可能（同一驱动暴露多个 udevice）？本设计只做一个口，多口留到 E 阶段之后。

## 9. 复现与证据索引

- 内核行号：以上所有 file:line 均相对 /home/qc233/zte/iwrt-tree/target/linux/zx279128/；可用 sed -n '<line>p' 逐条复核。
- 厂商 U-Boot 反汇编：board_eth_init 0x47f00850（调用 0x47f1fe38 MDIO/PHY 注册、0x47f30b54 eth_register、0x47f2fe38 refclk/SerDes、0x47f20444 MDIO 时钟）；eth start 0x47f305fc → 0x47f2ffc0 全量初始化；反汇编中出现的寄存器族与内核 hw_init 一致（0x92040018/1c、0x92348000+、0x923400e8/ec/f0/f4/f8/fc、0x92344xxx/0x92350xxx、0x921c0000/0x921d4000+、0x92200000+、0x9238c000/0x923a00xx），证明厂商 U-Boot 也是全量初始化，不是只写时钟。工具：capstone 5.x + PYTHONPATH=/tmp/pylibs（脚本 /tmp/e_eth*.py，按需重建）。
- 真机证据：evidence/t61-uboot-flash-acceptance-20261122.md（flash 自举、网络/PHY 验收）、evidence/c1a-bootm/run-2/boot-segment.txt:113-116（Generic PHY 绑定）、evidence/c1b1-flashboot-20261121.md:37（bdinfo 内存图）、evidence/b1-env-current-20261121.txt:8-18（网络 env 键）、evidence/p2-vendorless-network-gap-20261122.md（refclk/SerDes 缺口与 0012 依据）、evidence/p2-flashboot-kernel-hang-20261121.md（CP15/缓存状态与 bootm 流程）。
- 源码：U-Boot /home/qc233/zte/uboot-src（2027.01-rc2）；内核 tree /home/qc233/zte/iwrt-tree（e2631 分支）。
