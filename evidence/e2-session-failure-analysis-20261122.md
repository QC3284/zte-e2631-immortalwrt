# E2 会话失败分析：内核交接静默返回与无 DHCP DISCOVER

日期：2026-11-22　任务：task-68（E2 会话失败分析）　作者：verify-docs
性质：只读取证与源码分析。本任务没有触碰设备，没有改任何代码；设备停在 RAM 镜像控制台，等用户自行断电（flash 里的 15-patch U-Boot 会 autoboot 回 Linux）。

## 0. 结论摘要

1. F1（内核交接）：从 RAM 载入的 20-patch 镜像里，e2631boot 打印完 slot 摘要、uImage 摘要、CRCs、e2631soc 前后值和 "Loading Kernel Image to 40008000" 之后，**直接回到 "=>" 提示符**，没有 "Starting kernel ..."，也没有任何 abort/pc/lr/panic/复位文本；两次尝试完全一致（stop-safe-1、stop-safe-2）。
2. 按 uboot-src（与产物同源码树，tree c812dd86）穷举 bootm 路径：从 LOADOS 打印之后到 OS_GO 之间，**所有失败分支都有打印**（唯一例外见 2.4），正常返回则必打 "Resetting the board..." 且随后复位。实测两者都没有。**现有源码在已知路径上无法解释这次静默返回**，这本身是必须写进结论的事实，下一步要靠 bootm 子命令分段复测把它定位到具体阶段（见 6.1）。
3. F2（DHCP 无 DISCOVER）：U-Boot 的 E2 以太网驱动是内核驱动的忠实移植——zx_hw_reset / zx_pp_init / zx_hw_init 的寄存器写入逐条一致（72/72），TX 描述符逐字段一致。所以失败点不在"寄存器表写错"，而在 CPU DMA 之下：帧已交给 TM（若走到 doorbell，则 TX_DONE 轮询成功，日志里也确实没有 "TX completion timed out"），但主机侧没有合法 DHCP 报文。剩余候选按证据强度排序见 3.3。
4. Lead 卡片里的重叠假设（arena 0x45000000-0x45FFFFFF 与 staging 0x42000000..0x4554xxxx 重叠）**算术上不成立**：本会话 uImage 总长 3,491,146 B = 0x35454A，staging 结束于 0x4235454A；内核数据拷贝到 0x40008000..0x4035C4EA；与 0x45000000 起点的 arena 最小间距约 46.8 MiB。详见第 4 节。task-69 不要把"移动 staging 或 arena"当作 E2 的修复项；这类越界风险只在将来 stage 超过约 44 MiB 时才成立。
5. 已确认的两个红鲱鱼：e2631net 打印的 "lan1 switch port 2, stopped" 是驱动里 priv->hw_ready 这个软件标志（eth stop 后为 false），不是交换端口状态位；e2631net 的 "TX done 0" 也不能证明没发帧，因为 TX_DONE 计数器"读出即清零"。详见 3.2。

## 1. 输入与证据清单

| 项 | 值 |
| --- | --- |
| 失败会话 | 2026-11-22 12:06:34 起（E2 零写会话，task-67） |
| 产物 | uboot-build run 44982672016；u-boot.bin 494,208 B sha256 75ba2e66b448f08fba42fedffae4b21cd84ad082cb32de6f0d3474effc5ca11d；banner U-Boot 2027.01-rc2-g6bd1fbd087ba；entry 0x47F00000 |
| 源码树 | /home/qc233/zte/uboot-src HEAD 9562097163e43249682e766036073dd3aabf8c86，tree c812dd8689ccf146deeec83bd0e74067c8b8abc5（= UBOOT-INFO 的 post-am tree）；20-patch 树 /home/qc233/zte/uboot-verify20 的 boot/、board/、drivers/net/ 与它逐字节一致 |
| 产物附件 | /home/qc233/zte/e2631-t5-artifacts/uboot-doc-44982672016/e2631-uboot-44982672016/（u-boot.bin、u-boot.map、.config、build.log、UBOOT-INFO.txt、E2631-COMMAND-HELP.txt） |
| 主串口日志 | evidence/e2-failure/serial-run1.txt（原文 /home/qc233/zte/e2631-p3/e2/session/run-1/serial.log，123 行） |
| 停机会话日志 | evidence/e2-failure/serial-stop-safe-1.txt（50 行）、serial-stop-safe-2.txt（39 行） |
| 附着诊断 | evidence/e2-failure/diag-attach-1.json（会话结束后只读 version/e2631net/mii info/md.l/printenv） |
| 主机侧 | dnsmasq 只在现场用 docker logs 看过（无任何 DHCP 事务），容器在清理时删除，**服务器日志没有留存**；/home/qc233/zte/e2631-p3/e2/logs/dnsmasq.log 只是 docker run 的 stdout（4 行镜像/容器哈希），不是服务器日志 |

校验：SHA256SUMS.txt 覆盖上述四个附件。

## 2. F1：内核交接静默返回

### 2.1 原始串口摘录（逐字）

serial-run1.txt 第 80-122 行（20-patch RAM 镜像的控制台，dhcp 失败后由操作者执行 e2631boot；这是第一次观察点）：

```text
=> dhcp
ethernet@92000000 Waiting for PHY auto negotiation to complete........ done
zx279128s: lan1 up, 1000 Mbit/s full duplex, MAC 00:41:71:00:00:50
BOOTP broadcast 1
...（共 4 轮，每轮 7-8 次，每轮之间 "Retry time exceeded; starting again"）
```

serial-stop-safe-1.txt 第 31-50 行（第一次 e2631boot 尝试；提示符最终出现，第 50 行就是 "=> "）：

```text
=> e2631boot
e2631boot: slot0 at 0x00700000: serial 7, version "V1.0.0.7B5.8000", header 0x01c60000
e2631boot: slot1 at 0x02300000: serial 12, version "ImmortalWrt v1.10.0", header 0x03800000
e2631boot: cspboot would boot slot1
e2631boot: slot1 uImage "ARM ImmortalWrt Linux-6.18.60": load 0x40008000 entry 0x40008000, 3491146 bytes at 0x42000000
e2631boot: header and data CRCs are good
e2631soc: before  SCTLR=0x08c50878 (M=0 C=0 I=0) CLIDR=0x09200003 TTBR0=0x4590404a VBAR=0x4ff8a000 ACTLR=0x00000000 DACR=0x00000055 CCSIDR=0x701fe019
e2631soc: running vendor-order CP15 cleanup
e2631soc: after   SCTLR=0x08c50878 (M=0 C=0 I=0) CLIDR=0x09200003 TTBR0=0x4590404a VBAR=0x4ff8a000 ACTLR=0x00000000 DACR=0x00000055 CCSIDR=0x701fe019
e2631soc: read-only L2/SCU: PL310 0x00c00000 ctrl=0x00000000 aux=0x02030000 SCU 0x00800000 ctrl=0x00000000
## Booting kernel from Legacy Image at 42000020 ...
   Image Name:   ARM ImmortalWrt Linux-6.18.60
   Image Type:   ARM Linux Kernel Image (uncompressed)
   Data Size:    3491050 Bytes = 3.3 MiB
   Load Address: 40008000
   Entry Point:  40008000
   Verifying Checksum ... OK
Working FDT set to 0
   Loading Kernel Image to 40008000
=> 
```

serial-stop-safe-2.txt 第 19-39 行（第二次尝试；注意第 20 行 "=> e2631boot" 说明第一次的提示符确实回来了，操作者又输了一条命令）：

```text
   Loading Kernel Image to 40008000
=> e2631boot
（同样的 slot / uImage / CRCs / e2631soc / Booting kernel / Verifying Checksum OK / Working FDT set to 0 / Loading Kernel Image to 40008000）
=> 
```

为了对照，成功交接的样子（同一镜像链路的 A6 会话，evidence/uboot-a6-session/boot-a6-tail.txt）：

```text
   Loading Kernel Image to 40008000

Starting kernel ...

[0.153855] printk: console [ttyAMA0] enabled
```

即：成功时 "Loading Kernel Image to 40008000" 之后必有一个空行加 "Starting kernel ..."。E2 两次都没有。

### 2.2 bootm 各阶段"该打印什么 / 实际打印了什么"

以下行号均为 /home/qc233/zte/uboot-src 当前源码（与产物同一 tree）。

| 阶段 | 源码中成功时的输出 | E2 实测 |
| --- | --- | --- |
| 镜像识别 | "## Booting kernel from Legacy Image at ..."、"Image Name/Type/Data Size/Load/Entry"、"Verifying Checksum ... OK"（boot/bootm.c bootm_find_os 及其调用者） | 全部出现 |
| LOADOS | "   Loading Kernel Image to %lx"（boot/image.c:417-429 print_decomp_msg，由 image_decomp 打印） | 出现 |
| RAMDISK（CONFIG_SYS_BOOT_RAMDISK_HIGH=y，见 .config:369） | rd_data==0 时无输出，boot_ramdisk_high 直接 return 0（boot/image-board.c:608-615） | 无输出=正常 |
| OS_PREP | boot_prep_linux 写 ATAGS，成功无输出（arch/arm/lib/bootm.c:158 起） | 无输出=正常 |
| OS_GO 成功交接 | "\nStarting kernel ...\n\n"（boot/bootm.c:1442-1446 bootm_final） | **缺失** |
| boot_fn 正常返回（非 standalone） | "Resetting the board..."（boot/bootm.c:1356）+ 板级复位文本 "reset: the A1 port has no reset controller..." | **两者都缺失** |
| boot_fn 为 NULL | "ERROR: booting os ... is not supported"（boot/bootm.c:1287-1293） | 缺失 |
| PREP 子命令失败 | "subcommand failed (err=%d)"（boot/bootm.c:1332-1335） | 缺失 |
| 解压失败 | "Image too large: increase CONFIG_SYS_BOOTM_LEN" 或 "<comp>: uncompress error" + "Must RESET board to recover"（boot/bootm.c handle_decomp_error） | 缺失（且镜像是 uncompressed，不该走这里） |
| 镜像覆盖 | "WARNING: legacy format multi component image overwritten" 或 "ERROR: new format image overwritten - must RESET the board to recover"（boot/bootm.c:868-887） | 缺失 |
| LMB 分配失败 | log_err("Unable to allocate memory %#lx for loading OS")（boot/bootm.c:914-925）；CONFIG_LOG 未开时 log_err == printf（include/log.h 回退），一定会打印 | 缺失 |
| machid 环境变量非法 | **静默 return**（arch/arm/lib/bootm.c:318-325 只在 debug 级别打印） | 见 2.4 |
| OPTEE 冲突 | "Cannot start OPTEE-OS from NS"（arch/arm/lib/bootm.c:312-316） | 缺失，且 CONFIG_BOOTM_OPTEE 未开（.config:1567） |

### 2.3 没有任何异常现场

对三份串口日志做全文检查：没有 data abort / prefetch abort / undefined instruction / pc / lr / sp / Resetting CPU / resetting / panic / Oops / BUG 等字样；没有 BootROM 重新开始的 banner；提示符是活着的（stop-safe-1 第 50 行、stop-safe-2 第 20 行和第 39 行，且在 stop-safe-2 里还接受并回显了第二条 e2631boot）。也就是说这不是"跳到内核后挂死/复位"，而是 **bootm 这个命令在 U-Boot 里返回了**。

### 2.4 源码穷举：哪些路径能让 bootm 静默返回

从 "Loading Kernel Image" 打印点（image_decomp 内）往后逐段核对 bootm_run_states（boot/bootm.c:1208 起）：

1. LOADOS：image_decomp 返回非 0 会被 handle_decomp_error 打印；覆盖检查两条分支都会 puts；LMB 地址校验失败会 log_err。**唯一没有打印的返回 1 在 boot/bootm.c:837-840**（lmb_alloc_mem(LMB_MEM_ALLOC_ANY,...) 失败直接 return 1），但它位于"需要解压"的分支里；本镜像 Image Type 明确是 "(uncompressed)"，即 IH_COMP_NONE，不会进入该分支。
2. RAMDISK：CONFIG_SYS_BOOT_RAMDISK_HIGH=y，但 rd_data==0，boot_ramdisk_high 走 else 分支把 initrd_start/end 置 0 后 return 0（boot/image-board.c:608-615），不会产生静默失败。
3. 之后的 `if (ret) goto err;`（boot/bootm.c:1281-1282）：ret 只可能来自上面两步，均排除。
4. OS_PREP：dm-verity 失败、cmdline 失败、subcommand 失败三条都有打印；bootm_process_cmdline_env 的失败分支在编译期被证明不可达（产物里连 "Cmdline setup failed" 字符串都没有）。
5. OS_GO：boot_selected_os 调用 do_bootm_linux(OS_GO) -> boot_jump_linux。后者在 print "Starting kernel ..." 之前只有两个提前返回：OPTEE 冲突（有打印，且配置未开）和 machid 解析失败（**静默**）。
6. machid 路径要求环境变量 machid 存在。stop-safe-1 第 1-29 行正好是完整 printenv：26 项（baudrate、bootcmd、bootdelay、bootfile、bootloaderfile、console、e2631_flashboot、e2631_netboot、e2631_pocgo、e2631_pocload、ethact、ethaddr、fdtcontroladdr、fullfile、gatewayip、hostname、ipaddr、linuzfile、loadaddr、memsize、netmask、netretry、serverip、stderr、stdin、stdout、versioninfo），**没有 machid**。
7. 若 boot_fn 真的返回，boot_selected_os 会返回 BOOTM_ERR_RESET，bootm_run_states 的 err 段打印 "Resetting the board..." 再 reset_cpu；板级 reset_cpu 会打印 "reset: the A1 port has no reset controller, power-cycle the board"。两者都没有出现。

结论（事实层面）：**按当前源码，找不到能产生"打印 Loading Kernel Image 之后静默回到提示符"的路径**；machid 是唯一静默返回点，但环境里没有 machid。因此要么存在我们尚未定位的代码路径（例如某处被链接进产物的第三方/板级覆盖、或编译器优化改变了行为），要么输出在传输中丢失（但提示符紧接着出现，说明串口本身是通的）。这需要在设备上用 bootm 子命令分段复测来判定，见 6.1。

### 2.5 F1 候选（按可检验性排序）

F1-a：**bootm 在 OS_GO 之前就返回**，且返回点是未打印的路径（最可能是我们还没定位的分支）。判别方法：用 `bootm start` / `bootm loados` / `bootm prep` / `bootm go` 四个子命令分段执行，看哪一段返回后下一条命令执行不了（或哪一段之后立刻回提示符）。

F1-b：**boot_jump_linux 走到 machid 分支**，即某个我们没看到的机制给环境塞了 machid（例如 dhcp 写过环境变量，或 MTD env 的读取结果与 printenv 显示不一致）。判别方法：复测时在 e2631boot 前后各执行一次 `printenv machid` 和 `env exists machid; echo $?`，并在 bootm 之前 `setenv machid` 明确删掉。

F1-c：**bootm 实际成功了，但 "Starting kernel ..." 与内核早期输出都丢失**（例如打印瞬间串口 FIFO/中断状态异常）。判别方法：主机侧抓串口原始字节（当前就是串口直连抓的，风险低）；在不同 bootdelay 状态下重复；用 `log`/bootstage 不可用（CONFIG_BOOTSTAGE 未开），所以以"提示符是否回来"为准：如果内核真的起来，主机应当能 ping 通 192.168.1.1 或看到内核日志——本会话两者都没有，F1-c 可能性低。

F1-d：**e2631boot 的 run_command 提前返回**（例如控制台收到多余字节触发中止）。判别方法：复测时操作者完全不按键，由驱动只等待输出；对比 stop-safe 两次都有提示符、且提示符出现时间与 "Loading Kernel Image" 之间的间隔。

## 3. F2：DHCP 没有 DISCOVER

### 3.1 观察事实

- `dhcp` 之前 e2631net 显示 "lan1 switch port 2, stopped"、MAC ctrl 0x00000000、TM int 0x00005500、BMU free 0x00000110、TX done 0、RX 队列计数全 0（serial-run1.txt 第 72-74 行）。
- `dhcp` 触发 eth start：PHY 自协商 "........ done"，打印 "zx279128s: lan1 up, 1000 Mbit/s full duplex, MAC 00:41:71:00:00:50"（第 81-82 行）。
- 随后 4 轮 BOOTP 广播（每轮 7-8 次），每轮 "Retry time exceeded; starting again"，且每轮都重新 "lan1 up"（第 92、102、113 行），说明每轮都做了 eth halt + start。
- 全程没有 "zx279128s: TX completion timed out"（该字符串在产物里存在，见 strings 检查），说明凡是走到 doorbell 的帧，DMA 侧都完成计数了。
- 主机 dnsmasq 现场 docker logs 没有任何 DHCP 事务（没有 DISCOVER 行）；但服务器日志未留存，也没有 tcpdump。
- 会话结束后 diag 附着（diag-attach-1.json）：e2631net 显示 "MAC ctrl 0x00bb2000, TM int 0x00007700, BMU free 0x00000111, TX done 0"，RX 队列计数仍全 0；md.l 0x92350068 1 = 0x00000000。

### 3.2 两个已排除的红鲱鱼

1. "stopped" 是软件标志：drivers/net/zx279128s_eth.c:734 打印的是 priv->hw_ready；它在 .start() 成功后置 true（eth.c:600-652），在 .stop() 里置 false（eth.c:654-665），而 U-Boot 的 dhcp 在放弃时调用 eth_halt() -> .stop()。所以 dhcp 之后看到 "stopped" 是预期行为，不能据此说交换端口没开。
2. "TX done 0" 不能证明没发帧：TX_DONE 是"读出即清零"的完成计数器（eth.c:502 注释；内核驱动同样处理，zx279128s-main.c:587）。diag 读到 0 只说明自上次读之后没有新的完成事件。

### 3.3 F2 候选（按证据强度排序）

F2-a：**eth_send 静默失败**。U-Boot 的 send 在 BMU 分配失败时直接 `return -ENOSPC`，没有任何打印（drivers/net/zx279128s_eth.c:476-478）；BMU 分配本身在超时时也直接返回（eth.c:390-409），**没有移植内核的 pending 语义**（内核把未完成的分配留待下一次调用收取，zx279128s-main.c:43-83）。因此若 BMU 在握手/冷复位后第一次分配超时，U-Boot 会安静地不发帧，日志正好就是"有 BOOTP broadcast 行、没有 TX 超时行、主机看不到帧"。判别方法：下一次会话在 dhcp 失败后读 BMU 寄存器（基址 0x92000000 + 0x348000：BUF_ID 0x9234800c、BUF_ALLOC 0x92348014、FREE_STATUS 0x923480dc），并用 task-69 的诊断打印确认 send 的返回值。

F2-b：**egress 路径（TM 队列 40+port / PP 桥 / MAC 端口）状态问题**。U-Boot 与内核的寄存器程序逐条一致（第 3.4 节），差别只在时序与上下文：U-Boot 每次 eth start 都先做 zx_hw_reset 主复位（eth.c:231-246）再整套初始化，最后才使能 MAC 并开 DMA（eth.c:640-645）；内核是在 probe 阶段做同样的复位与初始化，open 时才开 DMA。若主复位后 PP/SerDes 或 TM 队列的遗留状态与 vendor 初始化不同，CPU TX 可能在 TM/PP 被丢，而 DMA 仍报完成。判别方法：主机 tcpdump + 在 U-Boot 里读 TM 队列 42 的计数（TM table QUEUE_USE 是间接窗口，读法同 eth.c:125-148 的 zx_tm_read0）。

F2-c：**PHY/RGMII 配置差异**。内核用 phylink，设备树 phy-mode = "internal"（target/linux/zx279128/dts/zx279128s-zte-zxhn-e2631.dts:174-181，lan1 = gmac_port2 = phy12）；U-Boot 用 dm_eth_phy_connect + phy_config + phy_startup（eth.c:618-632），没有设置 RGMII 延迟等板级 PHY 参数。若时序不对，帧可能出了 MAC 但线上损坏，dnsmasq（只记合法 DHCP）自然看不到。判别方法：主机 tcpdump 看是否有任何以太网帧（哪怕是坏帧）。

F2-d：**主机侧证据缺口**。没有 tcpdump、dnsmasq 服务器日志未留存，"没有 DISCOVER"目前无法区分"没有帧上线"与"帧上线但非法/被丢弃"。这不是根因候选，而是下一轮必须先补的证据类型。

### 3.4 已完成的静态核对（证明驱动是内核驱动的忠实移植）

- 对内核 zx_hw_reset/zx_pp_init/zx_hw_init（zx279128s-main.c:356-571）与 U-Boot zx_hw_reset/zx_pp_init/zx_hw_init（zx279128s_eth.c:209-373）逐条抽取 writel(值, 寄存器) 做机械比对：两边各 72 条，寄存器集合与值一一对应（只有宏名 vs 十六进制写法、base 变量名不同）。
- TX 描述符：main.c:658-671 与 eth.c:488-495 逐字段一致（desc0 = 0x80 | (40+port)<<20；desc1 = 0x10000；desc2 = 0x21000000 | (len&0x3fff)<<9；desc3 = 0x3 | (len&0x3fff)<<2；字节 7/8 存 BMU bp；写 1 到 TX_START）。
- 缓冲池/arena：都是 4096 x 2048 B，arena 0x45000000 起 16 MiB，tab0 +0x800000，tab1 +0x808000，RX +0xA00000，area50 +0xB00000，TX +0xC00000（eth.h:135-142 与内核头文件同值）。
- TM 表初始化：两边都是 CPU 队列 0-15 按 QUEUE_USE 残留抬高上限，16-399 写 0x00800400，RED 0x00200020，SCHED 0xff803fff/0x0100ff80/0x00100200/32（main.c:312-352 vs eth.c:158-199）。
- 因此"寄存器表写错/描述符格式错"这一类假设已被排除；F2 的剩余候选都必须解释"为什么寄存器一致但帧上不了线"。

## 4. 对 Lead 卡片重叠假设的算术反驳

卡片假设：net DMA arena 0x45000000-0x45FFFFFF 与 staged uImage 0x42000000..0x4554xxxx 重叠，RX 缓冲/BMU 池可能在 CRC 校验之后写坏镜像尾部。核对如下（全部为本次会话实测值）：

| 对象 | 数值 |
| --- | --- |
| uImage 总长（e2631boot 打印 + stop-safe 日志 Data Size 之后的总量） | 3,491,146 B = 0x35454A |
| staging 起点/终点 | 0x42000000 .. 0x42000000+0x35454A = 0x4235454A |
| 内核数据长度（Data Size） | 3,491,050 B = 0x3544EA |
| 内核拷贝目标区间 | 0x40008000 .. 0x4035C4EA |
| DMA arena | 0x45000000 .. 0x45FFFFFF（ZX_DMA_ARENA_SIZE=0x1000000） |
| staging 终点到 arena 起点间距 | 0x45000000 - 0x4235454A = 0x2CABAB6 = 46.8 MiB |

结论：三个区间两两不相交。只有 staged 数据超过约 44 MiB（0x45000000-0x42000000 = 48 MiB，扣除已用）才可能碰到 arena；本会话 3.49 MB 差 13 倍。卡片里的 "0x4554xxxx" 应是十进制/十六进制换算错误（3,491,146 的正确十六进制是 0x35454A，不是 0x354... 之外的 0x4554...）。因此：

1. E2 的 F1/F2 都**不能**用 arena 覆盖 staged uImage 解释；
2. task-69 的 (a) 项不要按卡片原文实现（不要为此移动 staging 或 arena）；
3. "staging 与 arena 越界"这个风险类别仍然真实（将来 stage 大文件时），保留编译期断言/README 内存图是便宜且值得的，但要写成"防御"而不是"E2 的修复"。
## 5. 本次已完成的无设备核对（可复现，不需要设备）

1. 产物字符串检查：u-boot.bin 里 "Starting kernel ...%s"、"Unable to allocate memory %#lx for loading OS"、"Image too large"、"Must RESET board"、"subcommand failed (err=%d)"、"FDT creation failed!"、"machid"、"Using machid 0x%lx from environment"、"Resetting the board..." 均存在；"Cmdline setup failed" 不存在（编译器证明 bootm_process_cmdline_env 恒返回 0）。
2. .config 检查（/home/qc233/zte/e2631-t5-artifacts/uboot-doc-44982672016/e2631-uboot-44982672016/.config）：CONFIG_SYS_BOOT_RAMDISK_HIGH=y（行 369）、CONFIG_LOGLEVEL=4（行 434）、# CONFIG_SILENT_CONSOLE is not set（行 435）、CONFIG_LMB=y（行 1570）、CONFIG_BOOTM_LINUX=y（行 541）、# CONFIG_BOOTSTAGE is not set（行 376）、CONFIG_SUPPORT_PASSING_ATAGS=y（行 183）、CONFIG_SYS_LOAD_ADDR=0x42000000（行 206）、CONFIG_TEXT_BASE=0x47F00000（行 190）。由此确认：静默不可能是全局静默控制台，也不可能是 RAMDISK 或 LMB 未编译。
3. u-boot.map 检查：没有 log_* 符号（CONFIG_LOG 未开），所以 log_err 走 include/log.h 的 printf 回退，LMB 失败信息会出现；lmb_add/lmb_alloc_mem/lmb_init 符号存在（LMB 已启用）。
4. 与内核参考驱动做寄存器级机械差分（第 3.4 节），证明 E2 驱动没有写错寄存器表。
5. 与成功会话的 boot 尾部做文本比对（evidence/uboot-a6-session/boot-a6-tail.txt），确认成功时 "Starting kernel ..." 是必经输出。

## 6. 设备复测协议（供 task-69 使用；需 Lead GO 和用户一次断电）

前提：设备现在是 RAM 镜像控制台；用户断电一次即回到 flash 里的 15-patch U-Boot 并 autoboot 进 Linux（干净恢复，不需要任何 flash 写）。复测仍然是零 flash 写：staging 只写 userdata 数据分区（Linux 侧），U-Boot 侧只读 + go。

### 6.1 F1：用 bootm 子命令分段定位

在 RAM 镜像控制台（或从 flash 提示符 loadx/go 进同一镜像）里，按顺序执行并逐条记录返回与输出：

```text
iminfo 0x420000                       # 记录 type/comp/os/arch/load/entry/data size
md.l 0x40008000 4                     # LOADOS 之前的 RAM 内容
bootm start 0x420020                  # 只做 START/FINDOS/FINDOTHER
iminfo 0x420000                       # start 之后再看一次（应无变化）
bootm loados                          # 只做 LOADOS（应打印 Loading Kernel Image）
bootm loados                          # 第二次；用于确认第一段返回后命令仍可执行
md.l 0x40008000 4                     # 校验内核头部是否已拷到 0x40008000
bootm prep                            # 只做 OS_PREP（ATAGS 写入）
bootm go                              # 只做 OS_GO
```

判读：
- 若某一条子命令之后下一条无法执行/立刻回提示符，则该阶段即失败点（例如 loados 后立即回提示符，即 LOADOS 内部返回；prep 后回提示符，即 boot_prep_linux 返回；go 后回提示符但无 "Starting kernel"，即 boot_jump_linux 的静默返回）。
- 每次执行前 `printenv machid` 与 `env exists machid; echo $?`；另外在 bootm 之前执行 `setenv machid` 清掉，排除 F1-b。
- `bdinfo` 记录 bi_boot_params（应为 0x40000100）、relocaddr、sp；与 A6 会话记录对比。
- 如果 `bootm go` 仍复现静默返回，请保留完整串口字节流（不要只看终端过滤后的文本），并在 session-results 里记录每条命令与提示符之间的原始字节。

### 6.2 F2：先补主机侧证据，再读硬件计数

1. 主机抓包（必须先做）：`tcpdump -i enp0s20u1u4u2c2 -e -n -vv` 记录到文件；至少覆盖 dhcp 的 30 秒。判据：有 BOOTP 帧但 dnsmasq 不认 -> 帧格式/校验问题；完全没有帧 -> MAC/PHY/egress 问题。
2. dnsmasq 日志落盘：启动时把 stdout/stderr 重定向到文件（不再只靠 docker logs），并保留 dhcp-range/interface 配置。
3. U-Boot 侧只读检查（dhcp 失败后）：
```text
e2631net
md.l 0x9234800c 1        # BMU BUF_ID（bit31=VALID，bit15:0=bp）
md.l 0x92348014 1        # BMU BUF_ALLOC（bit0=REQ，bit1:0=BUSY；有挂起请求即嫌疑）
md.l 0x923480dc 1        # BMU FREE_STATUS（bits 8:3 空闲槽）
md.l 0x92350068 1        # DMA TX_DONE（读出即清零，只能看当前值）
```
4. 重复 `e2631net` 之前先 `dhcp` 一次、记录 BMU 三连值；再 `dhcp` 一次、再记录。对比两次的 REQ/BUSY 是否从挂起变为清零，可直接判定 F2-a。

### 6.3 产物侧诊断（仅在 6.1/6.2 仍无法定位时）

按 task-69 的规则新增诊断 patch（0023+，不改 0001-0022 的字节）：在 eth send 的每条失败返回前加 printf（BMU 超时/无缓冲/描述符错误/门铃后超时），在 bootm 相关调用点加阶段打印（LOADOS 返回码、RAMDISK 返回码、boot_fn 解析结果、boot_jump_linux 入口与 machid 值）。这类 patch 只用于 RAM 会话取证，不进入产品镜像、不刷机；是否合并由 task-69/Lead 决定。

### 6.4 安全边界

- 零 flash 写：Linux 侧只写 userdata 数据分区（staging），U-Boot 侧只允许 mtd read/go/md/help/version 类命令；任何 mtd write/erase、saveenv、e2631flash、裸 bootm（除 6.1 的子命令）都要先拿到 Lead 的显式批准。
- 设备当前状态：RAM 镜像控制台；一次断电回 flash 15-patch U-Boot -> autoboot Linux。若用户在断电前要求恢复，不要尝试在 U-Boot 里"救"，直接等断电。
- 复测期间保持 capture chain 单读者，会话结束 restore。

## 7. 给 task-69 的结论与约束

1. **不要**按卡片 (a) 项"移动 staging/arena"作为 E2 修复：第 4 节已证明不重叠。
2. **不要**把 "lan1 switch port 2, stopped" 当作端口没开的证据（3.2），也不要根据 "TX done 0" 判断发送失败。
3. F1 的首要工作是 6.1 的分段复测；在拿到分段结果前，任何"修 bootm"的改动都是在猜。F2 的首要工作是 6.2 的抓包 + BMU 寄存器三连读；F2-a（send 静默失败 + 未移植 pending 语义）是目前证据最强、改动最小、最容易验证的候选。
4. 若 task-69 需要改 U-Boot 源码，请把"诊断打印"和"产品修复"分成两个 patch：诊断只用于 RAM 会话，产品修复必须用 RAM 会话或主机侧证据证明有效后才进入镜像；仍然遵守 0001-0022 字节不变、checkpatch 四类忽略表不变的规则。
5. 本次分析没有触碰设备、没有写 flash、没有改代码；设备停在 RAM 控制台等待用户断电。

## 8. 附件与复现命令

| 文件 | 内容 |
| --- | --- |
| evidence/e2-failure/serial-run1.txt | E2 会话主串口日志（123 行）：boot、staging、go、banner、version、e2631net、mii info、dhcp 4 轮 |
| evidence/e2-failure/serial-stop-safe-1.txt | 第一次 e2631boot 返回提示符（50 行，含完整 printenv 26 项） |
| evidence/e2-failure/serial-stop-safe-2.txt | 第二次 e2631boot 返回提示符（39 行，两次尝试） |
| evidence/e2-failure/diag-attach-1.json | 会话后只读诊断（version/e2631net/mii info/md.l 0x92350068/printenv） |
| evidence/e2-failure/SHA256SUMS.txt | 上述四个文件的 sha256 |

复现关键行：
```text
grep -n "Loading Kernel Image" evidence/e2-failure/serial-stop-safe-*.txt
grep -n "Starting kernel" evidence/e2-failure/serial-stop-safe-*.txt   # 空结果 = F1 现场
grep -n "BOOTP broadcast" evidence/e2-failure/serial-run1.txt
grep -n "TX completion timed out" evidence/e2-failure/serial-run1.txt   # 空结果 = DMA 侧都完成了
```

## 附录 A：关键源码位置

| 主题 | 位置 |
| --- | --- |
| "Starting kernel ..." 打印 | boot/bootm.c:1442-1446（bootm_final） |
| boot_fn 返回后的 "Resetting the board..." | boot/bootm.c:1353-1358 |
| boot_selected_os（返回即 BOOTM_ERR_RESET） | boot/bootm_os.c:582-598 |
| LOADOS 容错 | boot/bootm.c:1250-1257 |
| RAMDISK 状态 | boot/bootm.c:1260-1272；boot/image-board.c:539-619（rd_data==0 -> return 0，608-615） |
| 静默的 lmb_alloc_mem 返回 1 | boot/bootm.c:837-840（仅解压分支） |
| LMB 地址校验（会打印） | boot/bootm.c:914-925 |
| "Loading Kernel Image to" | boot/image.c:417-429 |
| boot_jump_linux：machid 静默返回 | arch/arm/lib/bootm.c:300-359（318-325 machid；330 bootm_final；333-339 r2/FAKE_GO） |
| do_bootm_linux 分派 | arch/arm/lib/bootm.c:377-398 |
| U-Boot eth：reset/pp/hw init | drivers/net/zx279128s_eth.c:209-373 |
| U-Boot eth：TM 表 | drivers/net/zx279128s_eth.c:150-199 |
| U-Boot eth：BMU 分配（无 pending 语义） | drivers/net/zx279128s_eth.c:390-409 |
| U-Boot eth：send（bp<0 静默返回） | drivers/net/zx279128s_eth.c:463-511（476-478） |
| U-Boot eth：start/stop | drivers/net/zx279128s_eth.c:600-665 |
| U-Boot eth：e2631net 打印 | drivers/net/zx279128s_eth.c:726-760（734 hw_ready，746 MAC/TM/BMU/TX 读） |
| 内核参考：BMU pending 语义 | target/linux/zx279128/files/drivers/net/ethernet/zte/zx279128s-main.c:43-83 |
| 内核参考：hw init / xmit | 同文件 356-571 / 605-690 |
| 内核 DTS：lan1=port2=phy12 | target/linux/zx279128/dts/zx279128s-zte-zxhn-e2631.dts:174-181 |

## 附录 B：20-patch 产物 .config 关键项

```text
CONFIG_SUPPORT_PASSING_ATAGS=y          # 183
CONFIG_TEXT_BASE=0x47F00000             # 190
CONFIG_SYS_MALLOC_LEN=0x400000          # 191
CONFIG_SYS_LOAD_ADDR=0x42000000         # 206
CONFIG_SYS_BOOT_RAMDISK_HIGH=y          # 369
# CONFIG_BOOTSTAGE is not set            # 376
CONFIG_LOGLEVEL=4                       # 434
# CONFIG_SILENT_CONSOLE is not set       # 435
CONFIG_BOOTM_LINUX=y                    # 541
# CONFIG_BOOTM_OPTEE is not set          # 1567
CONFIG_LMB=y                            # 1570
```