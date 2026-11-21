# A1 纯 RAM 链 POC 真机会话（task-45，2026-11-21）

状态：**已完成（POC 验收：装载链路通过；A1 banner 未出现，根因已真机确认）**。

- 装载链路 / K3 只读基线 / xmodem 载入 / vendor go 返回路径：真机通过（§4-§6、§8.4）。
- A1 banner 失败根因：U-Boot 主线 PL011 驱动用标准偏移，而 ZX279128S 的 UART0 是 ZTE 变体
  （DR 0x04、FR 0x14、LCRH 0x30、CR 0x34）；已用 A/B 双探针在真机双向证实（§8.5）。
- 修复方向：给 A1 的 U-Boot 增加 ZTE UART 支持（§9，转 task-47）。
- 全程零 flash 写入；设备已用 vendor reset 恢复 Linux，采集链已恢复。

## 1. 验收标准（task-45 任务卡）

1. 进入 vendor U-Boot 控制台（手册 §4.1 的 Press 1 + 密码流程）。
2. 按手册 §4.5 用 TFTP 把 u-boot.bin 载入 RAM；本机无通路时用等效通道（§5.1）。
3. go 0x43000000 后出现自定义 A1 U-Boot 的 banner。
4. 在自定义 U-Boot 里跑 md / mtest。
5. 全程零 flash 写入；结束时断电（A1 无 reset 控制器）或 reset 恢复原厂链。

## 2. 会话环境与产物

| 项 | 值 |
| --- | --- |
| 设备 | ZTE ZXHN E2631，ImmortalWrt v1.10.0，DISTRIB_REVISION r0-86cddb7，target zx279128/generic |
| 设备地址 | 192.168.1.1（SSH 可用；本轮只用它发 reboot -f，不做任何写入） |
| 主机 WiFi | wlp3s0 192.168.1.124/24，连设备 AP E2631 |
| 主机有线 | enp4s0f2 192.168.5.92/24 = 用户家网（唯一有线网口，无空闲网口/网线接设备 LAN1） |
| 串口 | /dev/ttyCH343USB0，115200 8N1；本轮由单读者 hub（serialhub.py）独占 |
| A1 产物 | u-boot.bin，347,640 B，sha256 a3771aca6144879701d5336ae032a6d242fab3e1c90a80dbea0710a6816679b3 |
| 入口/TEXT_BASE | 0x43000000（载荷上限 0x9F800 = 653,312 B） |
| banner | "U-Boot 2027.01-rc2-g7c42c3f6b431 (Nov 21 2026 - 05:06:01 +0000)"，文件偏移 0x49C63 |
| U-Boot 来源 | u-boot/u-boot master c1958b5f6cce03956d309ce422b5d9f819955d4a（v2027.01-rc2）+ 3 个 port 补丁，post-am tree abab1858；CI run 44869143179 |

console 密码按手册 §4.1 输入，不写入仓库。SSH 密码来自 0600 的本地文件，不写入仓库。

## 3. 时间线

| 时间（CST） | 事件 |
| --- | --- |
| 13:17 | 首次进入 vendor 控制台。串口提示 "Press 1 means entering boot mode" → 输 1 → 密码 → "Hit 1 to upgrade software version"；误用 SSH 密码被拒（日志里回显 passwd is error），改用手册 §4.1 密码通过 |
| 13:19-13:22 | K3 只读基线：READID、nand read 语义、OOB；发现 nand read 必须页对齐 |
| 13:22 | 准备 xmodem 传输；串口停在 "xmodem at 43000000" + 接收方 "C" |
| 13:26 | **停电**：主机与设备同时断电（Lead m03527）。旧串口日志 53,073 B 结尾即上面的 "C"；本轮从未发出任何 nand write/erase |
| 13:33 | 主机重启后恢复：停掉 Lead 重启的采集链（控制台需要串口独占），起自己的 hub，SSH reboot -f 重新抓 vendor 启动，重进控制台 |
| 13:36-13:40 | 停电后 K3 复核（§4）；TFTP 连通性探测（§5.1） |
| 13:40-13:42 | xmodem 载入 u-boot.bin（340×1 KiB，33.1 s）；md 四窗口逐字节比对通过 |
| 13:42 | go 0x43000000：vendor 打印 "## Starting application at 0x43000000 ..."，随后 120 s 无任何串口字节 |
| 13:45-13:56 | 根因分析（§7）、探针桩准备与 QEMU 验证（§8）；设备停在该状态，等用户断电恢复 |
| 13:57 | 用户第一次断电（cycle #1）后设备回到 Linux（ImmortalWrt v1.10.0，r0-86cddb7）；SSH reboot -f 进 vendor 控制台 |
| 13:58-13:59 | xmodem 载入并 go stub-zte-ret：真机打印 "E2631 UART probe ZTE-ZX29"、寄存器值、"PROBE-DONE"，vendor 回显 "## Application terminated, rc = 0xA"（§8.4.1）|
| 13:59 | vendor 提示符没有回来：桩未恢复 SP（我们的 bug），控制台失声 → 需要第二次断电 |
| 14:02-14:05 | 改进 start_v2.S 保存/恢复 SP/LR；做同一轮内完成 ZTE/标准偏移 A/B 的 combined 桩；用户第二次断电（cycle #2）|
| 14:05-14:06 | 设备回 Linux；SSH reboot -f 再进 vendor 控制台 |
| 14:06-14:12 | combined 桩迭代 v1/v3/v4（v1 缺 TX 排空、BEGIN 被 LCRH 切换冲掉；v3 加排空后 BEGIN 可见；v4 恢复后再加 settle 延时）→ v4 全绿（§8.4.2、§8.5）|
| 14:12 | vendor reset 回 Linux；14:14:08 恢复 Lead 的采集链（supervisor-002 + bootwatch-002，reader-start pid=38202）|
| 14:13 | Linux 启动完成：e2631-wifi-boot 自动初始化在 53.36 s 完成；身份仍是 ImmortalWrt v1.10.0 / r0-86cddb7 |

## 4. K3 只读基线（停电前 + 停电后各一轮，结果一致）

dump 基线：/home/qc233/zte/e2631-p2/dump2/mtd0-before.bin（mtd0 全 1 MiB，
sha256 de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f，与 task-42 基线一致）。

| 窗口 | nand 偏移 | 长度 | RAM 地址 | 与 dump 比较 | 结果 |
| --- | --- | --- | --- | --- | --- |
| U-Boot 头块 | 0x20000 | 0x800 | 0x4C000000 | dump 0x20000..0x20800 | 2048 B 全同 |
| 载荷起点 | 0x20800 | 0x800 | 0x4C001000 | dump 0x20800..0x21000 | 2048 B 全同 |
| env 页 | 0xC0000 | 0x800 | 0x4C002000 | dump 0xC0000..0xC0800 | 2048 B 全同 |
| nand read.raw | 0x20000，1 页 | 2112 B | 0x4C003000 | 主数据 0x40 B 同；OOB 0x40 B | 主数据一致；OOB 全 FF |

- nand read 必须页对齐：nand read 0x4C001000 0x202D4 0x20 被拒绝，原文
  "Attempt to read non page-aligned data"，" 0 bytes read: ERROR"，且 RAM 保留旧内容（这是早前"伪不一致"的原因）。
- READID（vendor 启动日志，双重来源）："NAND:  manuid=cd,71" 与
  "Manu ID: 0xcd, Chip ID: 0x71 (FSNAND SPI NAND F35SQA001G 128MiB 3,3V)"。
  即 FORESEE 0xCD/0x71，排除 0xC9 假设。
- nand info：sector 128 KiB，page 2048 B，OOB 64 B；nand bad：无坏块。
- 本轮全部动作都是 nand read / read.raw / md / mtest / xmodem / go，**零 flash 写入**。

证据文件：
- 停电前：k3-batch.log、k3-reads-transcript.txt、k3-compare.json、k3b-transcript.txt、k3b-compare.json
- 停电后：post-outage-k3.json、post-outage-k3-transcript.txt

## 5. A1 镜像装载

### 5.1 通道选择：TFTP 不可行，改用 vendor 内置 xmodem

TFTP 是手册 §4.5 的首选通道，但本机没有第二个有线网口：唯一有线口 enp4s0f2 接的是
用户家网 192.168.5.0/24，既不能改它，也没有 USB 网卡/空闲网线接设备 LAN1。
在 vendor U-Boot 里实测：ping 192.168.1.124（主机 WiFi 地址）→
"mac 3 phy status changed: 1000M full-duplex / Using eth0 device / ping failed; host 192.168.1.124 is not alive"。
因此改用 vendor 控制台自带命令 xmodem <addr>（U-Boot 2013.04 命令列表里有），
走串口、零网络、零 flash；host 端用自写 xmodem 发送器（serialhub.py，CRC/校验和自动协商，
离线 pty 测试两种块大小均逐字节通过）。

### 5.2 传输结果

| 项 | 值 |
| --- | --- |
| 命令 | xmodem 0x43000000（vendor 应答 "xmodem at 43000000"，接收方发 "C"） |
| 模式/块大小 | CRC / 1024 B |
| 块数 | 340（pad 520 B，0x1A 填充） |
| 字节数 | 347,640（与文件相同） |
| 耗时 | 33.1 s |
| EOT | 已 ACK（eot_acked=true） |

### 5.3 RAM 逐字节抽检（md.b，vendor 控制台）

| 检查点 | RAM 地址 | 文件偏移 | 长度 | 结果 |
| --- | --- | --- | --- | --- |
| 镜像起点（向量表 b8 00 00 ea） | 0x43000000 | 0x0 | 0x100 | 一致 |
| banner 字符串 | 0x43049C60 | 0x49C60 | 0x100 | 一致（含 "U-Boot 2027.01-rc2-g7c42c3f6b431"） |
| 镜像中段 | 0x43020000 | 0x20000 | 0x100 | 一致 |
| rel.dyn 区尾部 | 0x43054D00 | 0x54D00 | 0xE8 | 一致 |

xmodem 的 CRC 逐块校验 + 四窗口逐字节比对，证明 RAM 里的镜像与 CI 产物一致。

## 6. go 0x43000000 的结果

vendor 输出：

    => go 0x43000000
    ## Starting application at 0x43000000 ...

之后 120 s（poll 20 ms）没有任何新字节：没有第二段启动日志、没有异常打印、没有自动复位回
BootROM（否则会重新出现 "Boot SPI NAND / start read bootheader"），也没有 watchdog 复位。
判定：A1 入口被执行了（vendor go 已跳转），但自定义 U-Boot 没有产生可见输出。

## 7. 根因分析：ZX279128S 的 UART 是 ZTE 变体 PL011，寄存器偏移不同

### 7.1 事实来源

内核在用的补丁（树 fork 的 target/linux/zx279128/patches-6.18/001-amba-serial-amba-pl011-Bring-back-zx29-UART-support.patch，
对应 Linux commit d9ee199c0fef5e4074e241ed328e5c18a790454b）为 ZTE zx29 UART 增加了 vendor_zte
寄存器偏移表。Linux 头文件 include/linux/amba/serial.h 给出具体偏移：

| 寄存器 | ARM PL011 偏移 | ZTE zx29 偏移 |
| --- | --- | --- |
| DR | 0x00 | 0x04 |
| FR | 0x18 | 0x14 |
| LCRH | 0x2c | 0x30 |
| CR | 0x30 | 0x34 |
| IFLS | 0x34 | 0x38 |
| IMSC | 0x38 | 0x40 |
| RIS | 0x3c | 0x44 |
| MIS | 0x40 | 0x48 |
| ICR | 0x44 | 0x4c |
| DMACR | 0x48 | 0x50 |
| IBRD / FBRD | 0x24 / 0x28 | 0x24 / 0x28（相同） |

FR 的位定义也不同：ZTE 的 BUSY=bit8、DSR=bit3、CTS=bit1、RI=bit0；TXFF/RXFE 保持
标准位置 bit5/bit4（vendor_zte 只覆盖了 busy/dsr/cts/ri 四个字段）。

### 7.2 与 A1 镜像的对应关系（静态推导）

A1 的 DT 把 UART0 声明为 compatible = "arm,pl011"，reg = <0x94404000 0x1000>，
没有 clock 属性（CFG_PL011_CLOCK=0），也没有 skip-init。U-Boot 主线 drivers/serial/serial_pl01x.c 里：

1. probe → pl01x_generic_serial_init：往标准 CR 偏移 0x30 写 0 —— 在 ZTE 上 0x30 是 LCRH；
2. probe → pl01x_serial_setbrg → pl01x_generic_setbrg：clock=0，跳过 IBRD/FBRD，
   但往标准 LCRH 偏移 0x2c 写 0x70（ZTE 上这个偏移未定义），
   再往标准 CR 偏移 0x30 写 UARTEN|TXE|RXE|RTS —— **又写进了 ZTE 的 LCRH，ZTE 的 CR(0x34)
   从头到尾没有被写过，UART 一直处于关闭状态**；
3. putc 之后若走到输出，也是往标准 DR 0x00 写（ZTE 保留）、读标准 FR 0x18（ZTE 保留）。

结论：A1 的串口从 probe 起就不可用，banner 与后续输出都会被丢弃；这与 §6 的"完全静默"
完全吻合，而且不需要假设 A1 在更早处崩死。注意：只给 DT 加 skip-init 也不能修好 ——
skip-init 只能跳过 init/setbrg，putc/getc 仍然用错误的 DR/FR 偏移。

### 7.3 待验证点

上述是静态推导。§8 的探针桩用于在真机上直接验证"同一段裸机代码，用 ZTE 偏移能打印、
用标准偏移不能打印"，并顺带证明 vendor go 的调用/返回路径可用。

## 8. 探针桩（QEMU + 真机双验证）

### 8.1 设计

- 位置：/home/qc233/zte/e2631-p3/stub/（start.S / start_v2.S + stub.c / combined_stub.c + stub.ld）；
  最终证据版是 combined_stub_v4.bin，源码与二进制都已收进 evidence/a1-ramchain/；
- 工具链：clang --target=armv7a-none-eabi -marm -O2 -ffreestanding -fno-builtin -nostdlib，
  ld.lld 链接到 0x43000000，llvm-objcopy 取 binary；
- 代码：设置 SP=0x48000000；按目标偏移写 CR/LCRH 使能 UART（不动 IBRD/FBRD，保留
  secondboot 的 115200）；打印 "E2631 UART probe <TAG>" 与 FR/CR/LCRH/IBRD/FBRD 的值，
  打印 "PROBE-DONE"；RETURN 版本最后 return（U-Boot 的 go 是函数调用，会返回并打印
  "## Application terminated"），便于一次会话里连做多个测试；
- 变体（迭代后的最终版）：
  - combined_stub_v4.bin：一次 go 内完成 ZTE 偏移/标准偏移 A/B；start_v2.S 在入口保存
    SP/LR、返回前恢复；切换前后各做一次 TX 排空延时；返回前恢复 vendor 的 CR/LCRH，
    因此跑完还能继续用 vendor 控制台（§8.4.3）；
  - stub-zte-ret.bin / stub-std-ret.bin：更早的单探针版本，保留作对照。前者在真机上给出
    §8.4.1 的第一份证据；后者没有在真机跑（标准偏移会让 UART 失声、需要额外断电，
    A/B 已由 combined 版覆盖）。

### 8.2 QEMU 验证（证明打印/使能逻辑本身正确）

用 -DUART_BASE=0x09000000u -DUSE_STD 编一个 virt 版（QEMU virt 的 PL011 在 0x9000000、
标准偏移），跑 qemu-system-arm -M virt -m 256M -nographic -kernel stub-qemu.elf，实测输出：

    E2631 UART probe STD-PL011
    FR=0x00000090 CR=0x00000301 LCRH=0x00000070 IBRD=0x00000000 FBRD=0x00000000
    PROBE-DONE

说明"先 CR=0、LCRH=0x70、CR=0x301 使能，再轮询 FR.TXFF、写 DR"的裸机逻辑可用；
真机上只需把偏移换成 ZTE 的即可（反汇编已核对：ZTE 版把 0x70 写 0x94404030、
0x301 写 0x94404034、字符写 0x94404004、轮询 0x94404014）。

### 8.3 文件与校验

| 文件 | 大小 | sha256 |
| --- | --- | --- |
| stub-zte.bin | 1,664 B | 5dbf7c4e724937cac719b61ec99c7de942593213651a695349903e3398358a9f |
| stub-zte-ret.bin | 1,668 B | 01dfca3702ed1aa4bdf8ff5f13aa72468e2655a49aa2fe0eeb4665e2e06b0647 |
| stub-std.bin | 1,684 B | 6f9db2ae135294e547f57222df1c1a639afab6eaa5eff8f370d8193752367df0 |
| stub-std-ret.bin | 1,688 B | a6a1d8ea341ff7f723849359f6671783f3236eaf91ea8833fbc0661c7758185d |
| stub-qemu.elf（QEMU 验证用） | - | 见 qemu2.out |
| combined_stub_v4.bin（真机 A/B 最终版） | 3,184 B | 097c9af67500dad4171863fe768eeb3b12f85090b8b0b043c8aae19465a9e6cd |
| start_v2.S（v4 的 SP/LR 恢复入口） | 356 B | 69c40ba748ad7c62c1c0a9a728776c5ad330f957bf15866a9c9842072b8620d0 |

### 8.4 真机复测结果（已完成）

#### 8.4.1 第一次：单探针（cycle #1 之后，stub-zte-ret.bin）

串口原文的关键段（完整 JSON 见证据包 zte-single-probe-verdict.json）：

    xmodem: mode=crc, block=1024, blocks=2, bytes=1668, elapsed=4.7 s, eot_acked=true
    （md.b 全镜像逐字节比对一致）
    => go 0x43000000
    ## Starting application at 0x43000000 ...
    E2631 UART probe ZTE-ZX29
    FR=0x00000130 CR=0x00000301 LCRH=0x00000070 IBRD=0x0000000d FBRD=0x00000024
    PROBE-DONE
    ## Application terminated, rc = 0xA

判读：
- vendor 的 go 确实跳到了 0x43000000 并执行了我们的裸机代码；
- ZTE 偏移可以让这块 UART 正常打印：§7 根因在真机上的第一份证据；
- "Application terminated" 说明桩回到了 vendor U-Boot；
- 但之后 vendor 提示符没有回来：桩把 SP 改成 0x48000000 后没有恢复，U-Boot 带着坏掉的
  栈指针继续跑而挂起（我们的桩 bug，不是设备故障）。设备因此需要第二次断电。
  修复：start_v2.S 在进桩前把 SP/LR 存在 callee-saved 的 r4/r5，返回前恢复（见证据包）。

#### 8.4.2 第二次：combined A/B（cycle #2 之后，combined_stub_v4.bin）

串口原文（A/B 全部在这一段里，见证据包 combined-v4-transcript.txt 与 go-raw）：

    xmodem: mode=crc, block=1024, blocks=4, bytes=3184, elapsed=4.4 s, eot_acked=true
    （md.b 全镜像逐字节比对一致）
    => go 0x43000000
    ## Starting application at 0x43000000 ...
    E2631 UART probe ZTE-ZX29 (combined-v4)
    SAVED_CR=0x00000301 SAVED_LCRH=0x00000070
    ZTE_FR=0x00000130 ZTE_CR=0x00000301 ZTE_LCRH=0x00000070 IBRD=0x0000000d FBRD=0x00000024
    ZTE-PROBE-DONE
    STD-MARKER-BEGIN
    <0xfe 单字节无效字符>
    STD-MARKER-END
    COMBINED-DONE
    ## Application terminated, rc = 0xA
    =>
    => version
    U-Boot 2013.04 (Aug 28 2023 - 18:40:22)
    =>

说明：combined 桩的顺序是"ZTE 偏移打印 → 排空 TX → 标准偏移打印尝试 → 恢复 vendor
CR/LCRH → 再打印"。因此 STD-MARKER-BEGIN 与 STD-MARKER-END 之间就是标准偏移的输出窗口：
那里没有任何可读 ASCII（只有一个无效字节），而用 ZTE 偏移写的所有标记都完整可读。

#### 8.4.3 桩迭代记录（工程细节）

| 版本 | 改动 | 结果 |
| --- | --- | --- |
| v1 | BEGIN 后立刻切标准偏移，未等 TX 排空 | BEGIN 被 LCRH 切换冲掉（主机只收到 1 个字节），不能作为证据 |
| v3 | BEGIN 后加 2,000,000 次 RAM 写延时（写 0x4C100000，防止被编译器优化掉）| BEGIN 可见；但恢复后 END 的头几个字节仍被 LCRH 切换余波打坏 |
| v4 | 恢复 vendor 配置后再加一次同样的延时 | 全部标记可读，A/B 干净（最终证据）|

### 8.5 A/B 判读（真机）

| 观察点 | 期望 | 实测（combined v4）| 判读 |
| --- | --- | --- | --- |
| ZTE 偏移探测 | 可打印 | "E2631 UART probe ZTE-ZX29 (combined-v4)" + 寄存器行 + "ZTE-PROBE-DONE" | 通过：ZTE 偏移正确 |
| 标准 ARM PL011 偏移探测 | 无可读输出 | 无 "STD-PROBE-SHOULD-BE-INVISIBLE"；窗口内只有 1 个无效字节 | 通过：标准偏移驱动不了这块 UART |
| 恢复 vendor 配置 | 可继续打印 | "STD-MARKER-END" + "COMBINED-DONE" 完整可读 | 通过 |
| 返回 vendor U-Boot | 提示符 + 命令可用 | rc 行后有 "=>"，version 正常 | 通过（SP/LR 修复生效）|
| 设备恢复 | reset 回 Linux | vendor reset 后 Linux 正常启动，Wi-Fi 自动初始化 53.36 s | 通过 |

结论：同一段裸机代码，只换 UART 寄存器偏移就决定了串口生死。A1 镜像不打印 banner 的
原因是 U-Boot 主线 serial_pl01x.c 使用标准偏移，而不是 CPU、重定位或时钟问题。

## 9. 结论与后续

- **装载链路（task-45 第 1-2 步）通过**：vendor 控制台、K3 只读基线、xmodem 载入、
  md 逐字节比对全部成功；全程零 flash 写入（只用 nand read/read.raw/md/xmodem/go）。
- **A1 banner 验收（第 3-4 步）未通过，但根因已在真机双向确认**：A1 镜像确实被执行了
  （go 返回并回显 rc），失败点是 U-Boot 主线 PL011 驱动用标准偏移、驱动不了 ZTE 变体
  UART（§7、§8.4、§8.5）。不是镜像装载、CPU 模式或时钟问题。
- 因此 banner/md/mtest 无法在本轮验收；修复归 task-47（A1 串口驱动），修好后按本节
  第 4 条的顺序复测即可闭环。
- 修复建议（下一任务，需重编/重 pin/再跑 uboot-build.yml）：
  1. 在 U-Boot 侧增加 ZTE UART 支持。首选最小改动：在 drivers/serial/serial_pl01x.c 增加
     一个 ZTE 变体（新 compatible，例如 "zte,zx29-uart"；按变体选择偏移表），并把 A1 DT 的
     uart0 compatible 改成它；或新增一个极简 DM serial 驱动（putc/getc/pending/setbrg）；
  2. FR 位：ZTE 的 TXFF/RXFE 仍在 bit5/bit4，可直接沿用；若后续做中断/流控再按
     vendor_zte 的 busy/dsr/cts/ri 位处理；
  3. 不改 secondboot 的 115200：setbrg 保持 clock=0 跳过 IBRD/FBRD，只写 LCRH/CR；
  4. 重新构建后先在 QEMU 用一个 ZTE-偏移的模拟 UART 自测，再做本会话同样的
     xmodem + go 真机复测，banner 出现才算 A1 验收通过。
- A2 不受影响：UART 驱动修好后，A2 的 SPIFC/SPI-NAND/env 可以在同一套下继续。

## 10. 附录

### 10.1 本轮使用的命令（vendor console，只读/内存操作）

    version / bdinfo / nand info / printenv / help xmodem / help nand
    nand read <ram> <page-aligned off> <size>
    nand read.raw <ram> <page-aligned off> <pages>
    md.b <addr> <len>
    xmodem 0x43000000
    go 0x43000000
    mtest（A1 侧，未能到达）

### 10.2 文件位置

- 本轮串口原始日志：/home/qc233/zte/e2631-p3/serial-raw2.log（停电前：serial-raw.log）
- 控制台/传输/比对：phase2.out、phase2-transcript.txt、post-outage-k3.json、
  post-outage-k3-transcript.txt、a1-xmodem2.json、a1-xmodem2-transcript.txt、a1-go.json
- 探针桩工作目录：/home/qc233/zte/e2631-p3/stub/（源码、bin、qemu2.out）
- **本轮证据包（随本文档提交）：evidence/a1-ramchain/**，内含 combined_stub.c、
  start_v2.S、stub.ld、combined_stub_v4.bin、stub-zte-ret.bin、combined-v4-verdict.json、
  combined-v4-transcript.txt、combined-v4-go-raw.txt、zte-single-probe-verdict.json、
  qemu-validation.out、SHA256SUMS
- A1 产物与 CI 记录：/home/qc233/zte/e2631-t5-artifacts/uboot-a1-44869143179/

### 10.3 风险与限制

- A1 无 reset 控制器：控制台跑飞后只能断电恢复；本会话已发生一次意外停电（与设备无关）。
- 串口单读者：控制台会话期间必须停掉采集链，结束前恢复。
- 本机无 TFTP 物理通路；xmodem 是等效通道，但速度受 115200 限制（347 KB / 33 s 可接受）。
- 探针桩会临时改动 UART 寄存器（不是 flash）。第一版 RETURN 桩没有恢复 SP，导致 vendor
  控制台挂起、需要一次额外断电；最终 combined v4 桩在返回前恢复 SP/LR 与 vendor 的
  CR/LCRH，所以 vendor 提示符与命令都正常，最后用 vendor reset 回 Linux 即可。
- 采集链在控制台会话期间按单读者规则停掉，14:14:08 已恢复（supervisor-002 +
  bootwatch-002）；本次 vendor reset 的 Linux 启动日志在 hub 日志（serial-raw2.log）里，
  不在 capture-002 日志里，因此 bootwatch-002 不会生成这一条启动会话记录。
