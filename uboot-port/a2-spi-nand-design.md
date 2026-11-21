# A2 设计：自定义 U-Boot 的 SPI-NAND 只读路径

状态：随 task-50 的 patch 0005 一并交付。依据：
[evidence/p2-uboot-research-20261121.md](../evidence/p2-uboot-research-20261121.md) §2.2/§2.4、
[evidence/chip-level-layout-20261120.md](../evidence/chip-level-layout-20261120.md)、
[evidence/p2-oob-recon-20261121.md](../evidence/p2-oob-recon-20261121.md)，以及内核树 fork
（`4b09208b`）中的 `target/linux/zx279128/files/drivers/spi/spi-zx.c`（728 行）。
本设计不发明寄存器语义：所有偏移/位域都来自该内核驱动，而该驱动来自 ZTE SDK 的寄存器定义
（见源码头注释）。

## 1. 目标与边界

- **目标**：A1 RAM 链上让自定义 U-Boot 探测 ZX279128S SPIFC → SPI-NAND
  （FORESEE F35SQA001G，READID `0xCD/0x71/0x71`，128 MiB，2048+64），并用内置 `mtd` 命令
  读出 flash 内容（`mtd list`、`mtd read`）。这是 A3「槽位感知启动」的地基：A3 要读槽头、
  把 uImage 读进 RAM 再 `bootm`，先得证明这条读路径与内核 MTD 看到的内容一致。
- **只读**：A2 验收只跑读命令，**不执行 erase/program**。驱动层面实现 PIO 的读/写两条
  FIFO 路径——因为 SPI-NAND 探测本身就需要 `SET_FEATURE` 写 1 字节（读 ID、读配置、开 ECC、
  解锁块），这是探测的一部分，不是 flash 写入。
- **不做（留给后续阶段）**：env（B1 单独设计）、网络 `tftp`、DMA、中断、独立时钟/复位驱动、
  SPI-NOR、`mtd write/erase` 的用户接口。
- **全程 RAM**：厂商 U-Boot 控制台 `tftp 0x43000000` + `go 0x43000000` 装载；断电即恢复，
  **不写 flash**。

## 2. 现成件与缺口

U-Boot 2027.01-rc2（pin `c1958b5f`）已具备（均已在本 pin 的源码中核对）：

| 现成件 | 位置 | 本阶段用法 |
| --- | --- | --- |
| `spi-mem` 框架 | `drivers/spi/spi-mem.c`、`include/spi-mem.h` | 控制器只实现 `mem_ops`；无 dirmap 时框架自动回退 `spi_mem_no_dirmap_read/write` → `adjust_op_size` + `exec_op` |
| SPI-NAND 核心 | `drivers/mtd/nand/spi/core.c` | DM 驱动 `spi_nand`（`UCLASS_MTD`，compatible `spi-nand`）；片内 ECC、OOB、MTD 注册全部复用 |
| FORESEE 芯片条目 | `drivers/mtd/nand/spi/foresee.c` | `F35SQA001G`：`0x71,0x71`、`NAND_MEMORG(1,2048,64,64,1024,20,1,1,1)`、`NAND_ECCREQ(1,512)`、`HAS_QE_BIT` |
| `mtd` 命令 | `cmd/mtd.c`（`CONFIG_CMD_MTD`） | `mtd list`、`mtd read <name> <addr> [<off> [<size>]]`，只读探测足够 |
| DM SPI / DT 解析 | `drivers/spi/spi-uclass.c` | 子节点 `spi-max-frequency`、`spi-rx-bus-width`、`spi-tx-bus-width`、`reg` 直接生效 |

**唯一缺口**：ZX SPIFC 控制器（0x94406000）的 U-Boot 驱动。内核树 fork 已有该驱动
（`patches-6.18/022` 为 DT binding、`023` 为 Kconfig/Makefile；驱动本体在
`files/drivers/spi/spi-zx.c`），本阶段把它降级为只含 **PIO** 的 U-Boot 驱动。

## 3. 内核驱动 → U-Boot DM 映射

| 内核侧 | U-Boot 侧 | 处理 |
| --- | --- | --- |
| `platform_driver` + `spi_controller` | `U_BOOT_DRIVER(id=UCLASS_SPI)` + `dm_spi_ops` | 直接映射；`priv_auto = struct zx_qspi` |
| `spi_controller_mem_ops {adjust_op_size, supports_op, exec_op}` | 同名结构，但回调参数是 `struct spi_slave *` 而非 `spi_mem *` | 直接移植；`spi_mem_default_supports_op(slave, op)` 替代内核同名函数 |
| `devm_ioremap_resource()` | `dev_read_addr_ptr(dev)` | 无 platform resource |
| `devm_clk_get_enabled("pclk"/"wclk")` | `clk_get_by_index()` + `clk_enable()`，**可选** | U-Boot 没有 ZX CRPM 时钟驱动，DT 不写 `clocks`；probe 取不到时钟时打 debug 日志并沿用 secondboot 已编程的输入时钟（风险见 §9） |
| `reset_control_assert/deassert()` | 无 | 不做复位；依赖 secondboot 的控制器状态 |
| IRQ + `devm_request_irq` | 无 | 纯 PIO 轮询（内核注释也说明 PIO 下 IRQ 无收益） |
| DMA（`dma_rx`/`dma_tx`、sg、completion） | 无 | 只搬 PIO 路径；2112 字节页读走 FIFO 足够 |
| `ctrl->min/max_speed_hz`、`clk_round_rate` | `dm_spi_ops.set_speed` 回调 | 无时钟 provider 时只记录频率、返回 0；有时钟时才 `clk_set_rate` |
| `ctrl->mode_bits` | `dm_spi_ops.set_mode` | 只接受 mode 0（SPI-NAND 即 mode 0）；其他 CPOL/CPHA 返回 `-EINVAL` |
| `spi_register_controller()` | 驱动模型自动绑定 | 无需代码 |
| `dev_info/dev_err` | `dev_info/dev_err`（`dm/device_compat.h`） | 直接替换 |

`spi_mem_exec_op()` 在 U-Boot 里会先 `spi_claim_bus()`，而 `dm_spi_claim_bus()` 要求控制器同时
提供 `set_speed` 和 `set_mode`（缺一个就 `-EINVAL`），所以这两个看似"空"的回调必须存在。

## 4. 寄存器映射（内核定义，逐字保留）

| 寄存器 | 偏移 | 关键位 |
| --- | --- | --- |
| `VER` | 0x00 | 只读标识（本 SoC 为 `0x01040000`） |
| `START` | 0x04 | `BIT(0)` 启动一次传输 |
| `EN` | 0x08 | `BIT(0)` EN、`BIT(1)` EN_BACK（回读确认） |
| `CTRL0` | 0x0c | `BIT(17)` SCLK_PAUSE_CLR_ALLOW、`BIT(16)` SCLK_PAUSE_EN、`BIT(15)` TXFIFO_CLR、`BIT(14)` RXFIFO_CLR、`BIT(10)` TXFIFO_THRES、`BIT(6)` RXFIFO_THRES、`BIT(5)` TX_DMA_EN、`BIT(4)` RX_DMA_EN、`BIT(3)` WDOG_EN、`BIT(1)` SPI_MODE、`BIT(0)` WR_PROTECT |
| `CTRL1` | 0x10 | `BIT(4)` ADDR_TX_EN、`BIT(2)` DUMMY_TX_EN、`BIT(1)` READ_DATA_EN、`BIT(0)` WRITE_DATA_EN |
| `CTRL2` | 0x14 | `[15:12]` DUMMY_BYTE_NUM（内核固定写 `1<<12`）、`[10:8]` DUMMY_BIT_NUM、`[6:5]` ADDR_BYTE_NUM（0=8b,1=16b,2=24b,3=32b）、`BIT(4)` ADDR_MULTI_LINE_EN、`BIT(2)` DATA_MULTI_LINE_EN、`BIT(0)` TRANS_MOD |
| `BYTE_NUM` | 0x18 | 数据字节数 - 1 |
| `ADDR` | 0x1c | 地址值 |
| `INS` | 0x20 | 命令 opcode |
| `TIMING` | 0x24 | `[17:16]` 采样点，probe 保证为 1 |
| `INT_EN` | 0x28 | 本阶段写 0（纯轮询） |
| `INT_RAW` | 0x2c | `BIT(7)` TX_BYD_THRES、`BIT(6)` RX_BYD_THRES、`BIT(5)` TX_UNDERRUN、`BIT(4)` RX_OVERRUN、`BIT(2)` WDOG_OVERRUN、`BIT(1)` FMT_ERR、`BIT(0)` CMD_END |
| `INT_SW_CLR` | 0x30 | 写 `GENMASK(7,0)` 清全部中断 |
| `SW` | 0x34 | `[20:16]` TX FIFO 可写字数、`[12:8]` RX FIFO 可读字数；另有 TX/RX_BYD_THRES、SCLK_PAUSE_FLAG、WAIT_FLAG、FORMAT_ERR |
| `DATA` | 0x38 | 32 位 FIFO 数据口 |

FIFO 深度 16 个字（64 字节）。PIO 轮询超时沿用内核值：FIFO 30000 µs、CMD_END 1000 µs。

## 5. exec_op 移植（按内核 PIO 路径）

1. `CTRL0` 读-改-写：清 `TX_DMA_EN|RX_DMA_EN`，置 `RXFIFO_CLR|TXFIFO_CLR|TXFIFO_THRES|RXFIFO_THRES`；
2. 地址：`CTRL1 |= ADDR_TX_EN`；`CTRL2[6:5]` 按 `addr.buswidth * addr.nbytes` 取 8/16/24/32 位；
3. dummy：`CTRL1 |= DUMMY_TX_EN`；`CTRL2 |= 1<<12`（与内核一致，固定 1 字节）；
4. 数据：IN → `READ_DATA_EN`，OUT → `WRITE_DATA_EN`；`buswidth==4` →
   `DATA_MULTI_LINE_EN|TRANS_MOD`，`buswidth==2` → `DATA_MULTI_LINE_EN`；
5. 写 `CTRL0/CTRL1/CTRL2`，写 `INT_SW_CLR = GENMASK(7,0)`；
6. 数据长度：`BYTE_NUM = data.nbytes - 1`；
7. 写 `ADDR`、`INS`，写 `START = BIT(0)`；
8. PIO：按 `SW` 的 FIFO 计数分批搬 32 位字。**与内核的差异**：内核用
   `ALIGN(len,4)/4` 个 32 位字读写并假设缓冲区按字对齐；U-Boot 版用
   `memcpy` 做首尾处理（整字部分 memcpy 到/从 u32，尾部字节单独 memcpy 到/从最后一个字），
   因此对非 4 字节对齐和非 4 的倍数长度都安全——SPI-NAND 的 1 字节 `SET_FEATURE` 就属于后者；
9. 轮询 `INT_RAW.CMD_END`（1000 µs），若 `FMT_ERR` 置位返回 `-EIO`。

`supports_op` 采用内核约束：命令必须 1 字节单线；地址 ≤4 字节且单线；dummy ≤15 字节且单线；
拒绝"数据 OUT + 双线"（控制器不能双线发数据）。`adjust_op_size` 把单次数据截到 4096 字节
（内核 `ZX_QSPI_MAX_DATA`）。SPI-NAND 页读为 2112 字节，无需分片。

## 6. ECC-on-read 决定

- 芯片是 FORESEE F35SQA001G：片内 ECC 4 bit/512 B（`NAND_ECCREQ(1,512)`），OOB 空闲区
  `offset=2, len=62`（前 2 字节为坏块标记）。
- U-Boot 的 SPI-NAND 核心在 `spinand_init_flash()` 里通过 `spinand_ecc_enable()` 写
  `CFG_ECC_ENABLE`，之后按"整页 2048+64 = 2112 字节"读 cache，并由 `GET_FEATURE` 的
  status 判断是否已纠错/不可纠错；`mtd read` 返回的就是纠错后的数据。
- **决定：读路径保持片内 ECC 打开**，与内核 MTD 看到的数据一致；**不**在 U-Boot 里关 ECC
  去读裸页。理由：A2 的用途是"读内核/槽头并启动"，必须与内核读法一致；编程器裸 dump 的
  OOB 全 FF，不代表 flash 的读语义（见 evidence 的 OOB 取证结论）。
- 验收方法：同一区域分别由内核 MTD 和 U-Boot `mtd read` 读出，逐字节比较；若差异只在 OOB
  或 ECC 状态，先查是否绕过/重复启用了 ECC。

## 7. DT 与 Kconfig/defconfig

DT（`arch/arm/dts/zx279128s-zte-zxhn-e2631.dts`）新增：

    spi@94406000 {
        compatible = "zte,zx279128s-spifc";
        reg = <0x94406000 0x1000>;
        #address-cells = <1>;
        #size-cells = <0>;

        flash@0 {
            compatible = "spi-nand";
            reg = <0>;
            spi-max-frequency = <50000000>;
            spi-rx-bus-width = <2>;
            spi-tx-bus-width = <1>;
        };
    };

- compatible 与内核 binding（`Documentation/devicetree/bindings/spi/zte,zx279128s-spifc.yaml`）
  一致（`zte,zx279128s-spifc`，驱动也接受 `zte,zx29-qspi`）。
- **故意不写 `clocks`**：U-Boot 没有 ZX CRPM 时钟 provider，写了也拿不到；probe 容忍无时钟。
- 内核的 e2631 DTS 里同名节点用于对比（`spi-rx-bus-width=2`、`spi-tx-bus-width=1`、50 MHz）。

Kconfig（`drivers/spi/Kconfig`）：新增 `config SPI_ZX`（`depends on ARCH_ZX279128`、
`select SPI_MEM`），放在 `if DM_SPI` 内。
defconfig 增加：`CONFIG_SPI=y`、`CONFIG_DM_SPI=y`、`CONFIG_SPI_ZX=y`、`CONFIG_MTD=y`、
`CONFIG_DM_MTD=y`、`CONFIG_MTD_SPI_NAND=y`、`CONFIG_CMD_MTD=y`
（`SPI_MEM` 由 `SPI_ZX`/`MTD_SPI_NAND` select，不进 defconfig）。

## 8. 载荷预算与构建门

- 当前 A1 镜像约 348 KiB（上一次 CI 产物 347,640 B 量级）；上限 653,312 字节（secondboot 从 mtd0 0x20800 按封装头长度拷贝，
  载荷可到 0xBFFFF，env 从 0xC0000 开始）。SPI/MTD/SPI-NAND 预计增加几十 KiB，余量 >250 KiB。
- CI（`.github/workflows/uboot-build.yml`）按 pin 校验 patch 链后在 ubuntu-24.04 上交叉编译，
  新增门：`CONFIG_SPI_ZX=y`、`CONFIG_DM_SPI=y`、`CONFIG_MTD_SPI_NAND=y`、`CONFIG_CMD_MTD=y`、
  内嵌 DTB 含 `zte,zx279128s-spifc` 与 `spi-nand`、载荷 ≤ `E2631_UBOOT_PAYLOAD_MAX`；
  现有 entry=0x43000000 门不变。
- 本地不做全量编译（本机弱），只做静态检查：`git am` 链后的 tree hash、`dtc`、defconfig 符号、
  `scripts/checkpatch.pl`。

## 9. 风险与缓解

| 风险 | 等级 | 缓解 / 判断依据 |
| --- | --- | --- |
| 控制器输入时钟/门控状态未知（secondboot 可能没开 SPIFC 的 CRPM 门） | **中** | 这是 A2 最大不确定项。DT 不写 clocks，probe 只做 EN/EN_BACK 与 TIMING 采样点；真机先用 `md.l 0x94406000 8` 看 EN/VER 回读。若读全 0 或 EN_BACK 不来，下一步是 A3 前补一个最小 CRPM 时钟驱动（内核 `clk-zx279128s.c` 有寄存器参照）或在 secondboot 已开的门控上继续（厂商 U-Boot 读 NAND 说明门控大概率已开）。 |
| 引脚复用/复位状态 | 低 | 厂商 U-Boot 同一控制器读 NAND，secondboot 已配置 pinmux。 |
| 采样点（TIMING[17:16]） | 低 | probe 按内核逻辑保证 =1；仍读坏数据时用 `md` 对比原始寄存器。 |
| 无 DMA/中断导致读慢 | 低 | A2 只读少量字节（mtd0 头、槽头）和单页测试；整片读取不是 A2 目标。 |
| 片内 ECC 与编程器裸 dump 不一致 | 低 | 见 §6：以"内核怎么读"为准，验收逐字节对比。 |
| 载荷超限 | 低 | CI 硬门；当前余量 >250 KiB。 |
| U-Boot 无 CRPM 驱动导致 `clk_*` 失败的代码路径 | 低 | probe/set_speed 都有"无时钟"分支，返回 0 并记录频率。 |
| 写路径被误用 | 低 | A2 文档与验收只允许 `mtd list`/`mtd read`；驱动虽实现 PIO 写（探测需要），但没有任何自动写命令。 |

## 10. 验收

1. **CI**：`uboot-build.yml` 在 task-50 的 patch 0005 上编译通过，配置门/DTB 字符串门/载荷门全绿。
2. **静态**：fresh clone pin `c1958b5f` + `git am` 0001-0005 的 tree hash 写入 `commits.env`；
   `dtc` 编译 DTS；`make defconfig` 后上述符号全部为 `=y`；checkpatch 0 errors。
3. **真机（后续 A2 会话，用户批准）**：`tftp` + `go` 后
   `mtd list` 应显示 `spi-nand0`（128 MiB、2 KiB 页、64 B OOB），
   `mtd read spi-nand0 0x42000000 0 0x800` 后 `md.b` 与已知 mtd0 头 dump 逐字节一致；
   再读 slot 头验证。**不执行任何写/擦命令。**
