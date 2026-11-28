# E4 救援写模式验收（task-79）—— 写入 PASS、patch-0034 最终写入、flash 提示符救援与真冷启动 GREEN

日期：2026-11-28（CST）
设备：ZTE ZXHN E2631 / ZX279128S，ImmortalWrt v1.10.0，kernel 6.18.60
产物：旧 E4 镜像（run 46036894542，patch 0026-0033，tree cd67a041…）；最终 0034 镜像（run 46046018929，patch 0026-0034，tree 0480ef83…）
结论：旧 E4 镜像的 STEP-1 净零写入、STEP-2 真实写入、独立回读、reset 与 flash 启动均 PASS；从 flash 提示符直接运行 e2631rescue 暴露 PHY/refclk 缺口（§8），patch 0034 修复后，最终把 0034 镜像写入 mtd0 的第三写 PASS，并从 flash 提示符以 e2631rescue 作为第一条网络命令完成页面与 validate（§12）。截至本文件，task-79 仅剩真冷启动（用户断电/上电）验收；该验收已于 2026-11-28 09:12-09:14 完成并 GREEN（§13）。

## 0. 摘要

| 项 | 结果 |
|---|---|
| 产物/暂存 | u-boot.bin 365,872 B sha256 3dbbfc49…；padded 524,288 B sha256 3ed8250b…；userdata 擦/写/回读 OK |
| RAM 链 | go 0x47F00000 -> banner g30dca5f54503 -> env sanity OK（27 项，ethaddr 00:41:71:00:00:50） |
| STEP-1 净零 | POST 01:41:03 accepted；/status done 01:41:08；crc32 0x0721e716 = want |
| STEP-2 E4 | 同一 rescue 会话；POST 01:41:10 accepted；done 01:41:15；crc32 0x79ef8c50 = want |
| 独立回读 | 01:41:16 区域 crc32 0x79ef8c50；env stored 0xF95A816E / region 0xe826c394；secondboot 0x9848a667 |
| reset | 01:41:17 reset -> flash E4 banner g30dca5f54503 prompt 01:41:20（RESET GREEN） |
| postcheck | mtd0 d87db54a…、区域 8a38896e…、env 6e2c01da…、secondboot 540db435…、tail b5a41c37…、PANICS=0、MT7916=1、WiFi=1 |
| 冷启动救援 | FAIL：PHY startup failed (-110)，e2631rescue: no usable Ethernet device（§8） |
| 0034 最终写 | 08:58:11 POST accepted -> /status done 08:58:16；crc32 0x1e5ff289 = want；串口显示 PASS: mtd0 updated |
| 0034 独立回读 | region 0x1e5ff289；env 0xF95A816E/0xe826c394；secondboot 0x9848a667 |
| 0034 flash 启动 | reset -> Boot SPI NAND -> secondboot -> banner g1673d5c89c7b |
| flash 提示符救援 | e2631rescue 为第一条网络命令：PHY done、lan1 up；GET / 200、validate 200 sha_match=ok |
| 0034 postcheck | mtd0 ac06d7bc…、region 23395533…、env/secondboot/tail 不变、PANICS=0、MT7916=1、WiFi=1、fwslot s12/s7 |
| 0034 驱动 | 原始 verdict=FAIL（两个 harness 记账缺陷）；离线复核 corrected=GREEN，见 §12.7 |
| 0034 真冷启动 | 09:12:41 物理断电/上电 -> BootROM -> banner g1673d5c89c7b -> e2631boot -> kernel -> Linux；health mtd0 ac06d7bc…、PANICS=0、MT7916=1（§13） |
| 驱动 | 01:42:50 抛错退出码 2；session-results.json 仍由 finally 写出并记录 error；无伪造数据 |

## 1. 输入与基线

- 产物目录：/home/qc233/zte/e2631-t5-artifacts/uboot-e4hdr-46036894542/e2631-uboot-46036894542/
- u-boot.bin：365,872 B，sha256 3dbbfc49e7fa580fe5327f9b0f11cddc0fe0d0f92e5a9fde9c37a7efdf133bb6，crc32 0x34b252a4，banner U-Boot 2027.01-rc2-g30dca5f54503
- e2631-uboot-mtd0.bin：655,360 B，sha256 8a38896e9164faa7aca4e9c2737e9d0c2b720f5576ce3ee3ef147109aa0b2bb9，crc32 0x79ef8c50
- env 块：6eee153b…（模板）；本机 env 块基线 6e2c01da…，stored CRC 0xF95A816E
- 会话前 flash：mtd0 f9239040…（= vendor 区 887a7f6c + 净零区 b1ea9a48 + 基线尾）；写后目标 mtd0 d87db54a…
- secondboot 0x0..0x20000：540db435…（crc32 0x9848a667）；tail 0xE0000..0x100000：b5a41c37…
- 驱动：/home/qc233/zte/e2631-p3/e2/drivers/e4_rescue_write.py（附件 tool-e4_rescue_write.py）

## 2. 预检

驱动 --preflight 结果 ok=true：artifact pins（sha/crc/大小/banner/E4 镜像/net-zero）全 true；主机直连 192.168.1.1 dev enp0s20u1u4u2c2 src 192.168.1.191；设备 mtd0 f9239040、区域 b1ea9a48、env 6e2c01da、secondboot 540db435；fwslot 运行 slot1 serial 12，slot0 serial 7 原样；重建当前/目标 mtd0 均一致。

## 3. 会话时间线（2026-11-28 CST）

- 01:40:22 会话开始；01:40:25 STAGING GREEN：copy 0.26 s、erase 0.83 s、write 0.39 s、readback 0.24 s、sync 0.18 s
- 01:40:48 从 Linux 复位进入 flash 15-patch U-Boot（当时 flash 还是 15-patch 镜像），停 autoboot；mtd read 暂存 + crc32 0x34b252a4 通过
- 01:40:54 go 0x47F00000 -> E4 RAM 镜像 banner g30dca5f54503；env block OK（stored 0xF95A816E / region 0xe826c394）；env sanity 27 项；help e2631rescue 存在
- 01:41:03 STEP-1 POST；01:41:08 done；01:41:10 STEP-2 POST（同一 rescue 会话）；01:41:15 done
- 01:41:16 一次 Ctrl-C + 独立回读 + env + secondboot；01:41:17 reset；01:41:20 flash E4 banner prompt
- 01:42:50 从 flash E4 prompt 运行 e2631rescue 失败（§8），驱动退出码 2
- 01:45:24 我手动 e2631boot 回 Linux；驱动的 finally 在等到 Linux 后补采 postcheck，写出 session-results.json（§9）

## 4. STEP-1 净零写入

- 请求：POST /flash?mode=write，body 为当前镜像区 655,360 B（sha256 b1ea9a48…），X-E2631-SHA256 同值，X-E2631-Confirm: write
- HTTP：200，result=accepted，sha_match=ok，dt=1.63 s
- /status 序列（驱动逐次轮询）：staged 0 -> erase 10 -> blank 30 -> write 45 -> readback 80 -> compare 90 -> done 100
- 结果：done，crc32 0x0721e716（want 0x0721e716），STEP-1 STATUS-DONE 01:41:08
- 该步内容与写前完全一致，因此 crc 相同属于预期；真正的“写入发生过”证据在 STEP-2 与最终整芯片摘要

## 5. STEP-2 E4 写入（同一 rescue 会话）

- 请求：POST /flash?mode=write，body 为 E4 655,360 B 镜像（sha256 8a38896e…），同样的确认头
- HTTP：200，result=accepted，sha_match=ok，dt=1.57 s
- /status：staged 0 -> erase 10 -> blank 30 -> write 45 -> readback 80 -> compare 90 -> done 100（01:41:10-01:41:15）
- 结果：done，crc32 0x79ef8c50（want 0x79ef8c50），STEP-2 STATUS-DONE 01:41:15
- 串口原文：e2631rescue: erasing mtd0 0x20000..0xc0000 / writing 655360 bytes to mtd0 / PASS: mtd0 updated, CRC32 0x79ef8c50
- 整个救援阶段没有任何控制台输入；两次 POST 之间也没有 Ctrl-C 或命令

## 6. 独立控制台回读（救援退出后）

- mtd read spi-nand0 0x46000000 0x20000 0xa0000：Reading 655360 byte(s) (320 page(s))；crc32 0x46000000 0xa0000 = 0x79ef8c50
- env 块：mtd read 0x47000000 0xc0000 0x20000；md 首字 0xF95A816E；crc32 = 0xe826c394
- secondboot：mtd read 0x48000000 0x0 0x20000；crc32 = 0x9848a667
- 结论：写窗口正确，env 与 secondboot 未被触碰

## 7. reset 与 flash 启动 postcheck

- 01:41:17 保存 reset 命令；01:41:18-20 串口：Boot SPI NAND -> secondboot -> OUR banner g30dca5f54503 -> prompt；RESET GREEN
- 01:45:24 从该 prompt 运行 e2631boot -> kernel start；SSH 恢复后 postcheck：
  - mtd0 d87db54ae30af930b67793defe78d3fb64c5b74315306cea69fe952e42fe1338
  - 镜像区 8a38896e9164faa7aca4e9c2737e9d0c2b720f5576ce3ee3ef147109aa0b2bb9
  - env 6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893
  - secondboot 540db4350cca5e77228b65ba3b387ea86be545e7f10a81db19b81d6f7816e1fd
  - tail b5a41c3758763bbec72769fab4a2533bf2db0b6312d93d25a695f9e4b9e02260
  - PANICS=0、OOPS=0、MT7916=1、WiFi complete=1、KERNEL=6.18.60
  - fwslot：running slot1 serial 12；slot0 serial 7 原样
- 预期目标 mtd0 d87db54a… 与实测完全一致；写入验收 PASS

## 8. 冷启动救援 FAIL（独立缺口）

在 flash E4 prompt 上，e2631rescue 是第一个网络命令（尚未运行 e2631boot/e2631net），串口原文：

    => e2631rescue
    e2631rescue: starting lan1 at 192.168.1.1/24, DHCP pool 192.168.1.100+
    ethernet@92000000 Waiting for PHY auto negotiation to complete......... TIMEOUT !
    zx279128s: PHY startup failed (-110)
    e2631rescue: no usable Ethernet device

源码定位：board/zte/zxhn-e2631/e2631rescue.c:850-853，do_e2631rescue 只调用 eth_init()，没有调用 e2631_net_refclk_init()；而 RAM 链的 e2631rescue 之所以能工作，是因为此前的 F2/e2631net 已经完成 refclk/PHY 初始化。flash 冷启动路径直接进救援模式时 refclk 未初始化，PHY autoneg 超时。

影响：用户在没有 RAM 链、只有 flash 的情况下无法使用 e2631rescue；这是产品缺口，不是本次写入失败。
修复队列：base-builder patch 0034（cold-boot rescue）已构建：banner g1673d5c89c7b、u-boot.bin sha256 b7ea6bbc…、mtd0 sha256 23395533…，待冷启动零写入验收。

## 9. 驱动异常与结果文件

- 01:42:50 驱动在 resident-rescue 阶段抛 RuntimeError('e2631rescue never printed the HTTP-ready line')；退出码 2。
- 该错误发生在写入/复位全部完成之后；写入、回读、reset、flash 启动的证据在抛出前已经记录。
- finally 仍执行：停止 tcpdump/hub、恢复抓取链、等待 Linux；我在 01:45 手动 e2631boot 回 Linux 后，finally 补采 postcheck 并写出 session-results.json。该文件是真实运行结果（含 error 字段），不是事后伪造；只是 postcheck 的采集时间晚于错误。
- 已知 cosmetic 缺陷：readback.crc_ok 字段因 crc32 输出无 0x 前缀而显示 false；真正的 final_readback 检查用 readback.crc == 0x79ef8c50，结果 true。证据保留原样并在 §6 给出实测 crc。

## 10. 写入与审计

- Linux 侧唯一写入：userdata 暂存（mtd erase userdata + mtd write padded 524,288 B + dd 回读），以及 sync
- U-Boot 侧写入：恰好 2 次 POST，每次由 e2631rescue 内部执行 erase/blank/write/readback/compare；写窗口 mtd0 0x20000..0xC0000
- 未使用：saveenv、nand write/erase、mtd erase（手动）、e2631flash、loadx/xmodem
- 最终 mtd0 与目标摘要一致；env、secondboot、tail 与写入前逐字节一致

## 11. 后续

1. 旧 E4 的 flash 提示符救援缺口已由 patch 0034 修复；0034 已在 2026-11-28 第三写中刷入 mtd0，并从 flash 提示符验证 resident rescue（§12）。
2. task-79 最后一项（真冷启动）已于 2026-11-28 09:12-09:14 完成：物理断电/上电 -> flash 0034 -> Linux，health 全绿（§13）。
3. 证据附件见 evidence/e4-rescue-write/ 与各目录 SHA256SUMS.txt。

## 12. task-79 最终会话：patch-0034 第三写与 flash 提示符救援（2026-11-28）

### 12.1 产物与基线

- 产物目录：/home/qc233/zte/e2631-t5-artifacts/uboot-coldrescue-46046018929/e2631-uboot-46046018929/
- u-boot.bin：365,872 B，sha256 b7ea6bbc138e1b3cbea6389fbaae89419d1d7e46e0668ef88637dd2cd14ac33d，crc32 0x9f2b707d，banner U-Boot 2027.01-rc2-g1673d5c89c7b
- e2631-uboot-mtd0.bin：655,360 B，sha256 23395533c123ea1099c951fee55a73f264636ca9d33d8298b160efb6d0fdb7d1，crc32 0x1e5ff289
- 会话前 flash（旧 E4 第三写后的状态）：mtd0 d87db54a…、region 8a38896e…、env 6e2c01da…、secondboot 540db435…
- 预期写后 mtd0：ac06d7bcccfc1ed2baa18e792cffce8c7912981eb5491e5b3ea67b1a1172325f（基线 mtd0 的 0x20000..0xC0000 替换为 0034 镜像；构造脚本见驱动 expected_final）
- 驱动：/home/qc233/zte/e2631-p3/e2/e4_final_0034.py（附件 tool-e4_final_0034.py）

### 12.2 run-1 驱动 bug（无设备写）

08:55:10 run-1 在 staging 前报 RuntimeError: reconstruction current sha mismatch。原因是驱动 expected_final() 用 0034 镜像（23395533）拼“当前”mtd0，而实际当前镜像区是旧 E4（8a38896e）。device_before 门禁已先行通过：live mtd0 就是 d87db54a…、region 8a38896e…、env 6e2c01da…、secondboot 540db435…；没有 byte 级设备差异，也没有 staging/写入/POST。修复 = OLD_IMAGE 指向旧 E4 mtd0 镜像；重算得到 cur=d87db54a、final=ac06d7bc、final_ok=true。

### 12.3 run-2 时间线

- 08:57:44 会话开始；08:57:54 STAGING GREEN：copy 0.23 s、erase 0.85 s、write 0.38 s、readback 0.26 s、sync 0.18 s
- SSH 侧 reboot -> flash 旧 E4 提示符 g30dca5f54503；mtd read userdata 0x3F00000 -> 0x47F00000；crc32 0x9f2b707d 通过；go 0x47F00000
- 08:58:05 RAM 0034 提示符 banner g1673d5c89c7b；env block state=OK（stored 0xF95A816E / region 0xe826c394）；env sanity 27 项（26 flash key + fdtcontroladdr），ethaddr 00:41:71:00:00:50；help e2631rescue 存在
- 08:58:11 POST /flash?mode=write（0034 镜像，X-E2631-SHA256=23395533…，X-E2631-Confirm: write）-> 200 result=accepted sha_match=ok
- /status：staged 0 -> blank 30 -> write 45 -> readback 80 -> compare 90 -> done 100（08:58:11-08:58:16）；done 时 crc32=0x1e5ff289、result=ok、sha_match=ok
- 串口原文：e2631rescue: erasing mtd0 0x20000..0xc0000 / e2631flash: erasing block 0x20000..0xa0000 / writing 655360 bytes to mtd0 / PASS: mtd0 updated, CRC32 0x1e5ff289 / nothing was rebooted
- 08:58:17 仅一次 Ctrl-C（e2631rescue: left the rescue mode）；控制台回读：region crc32 0x1e5ff289；env md 首字 0xF95A816E、crc32 0xe826c394；secondboot crc32 0x9848a667
- 08:58:18 reset -> 串口 Boot SPI NAND / start read bootheader / start read secondboot / banner U-Boot 2027.01-rc2-g1673d5c89c7b（来自 flash）
- 08:58:21 停 autoboot -> 0034 flash 提示符；08:58:22 e2631rescue 作为从 flash 提示符发出的第一条网络命令（其前只有 version，无 e2631net/e2631boot）：PHY auto negotiation done、zx279128s: lan1 up, 1000 Mbit/s full duplex
- 08:58:28 resident rescue HTTP：GET / 200（gzip 4456 B，解压 9216 B，sha256 30a8f03e…）；/status 初始 stage=idle；POST /flash?mode=validate（0034 镜像）-> 200 result=ok sha_match=ok；/status 后 stage=idle crc32=0x1e5ff289 sha_match=ok；Ctrl-C 退出
- 08:58:39 e2631boot -> Starting kernel -> Linux 恢复；会话后只读 SSH 复核见 12.4

### 12.4 写后 live postcheck（只读 SSH）

- MTD0=ac06d7bcccfc1ed2baa18e792cffce8c7912981eb5491e5b3ea67b1a1172325f（与重建一致）
- REGION=23395533c123ea1099c951fee55a73f264636ca9d33d8298b160efb6d0fdb7d1
- ENV=6e2c01da…、SECONDBOOT=540db435…、TAIL=b5a41c37…（均与写前一致）
- PANICS=0、OOPS=0、MT7916=1、WiFi complete=1、VERSION=ImmortalWrt v1.10.0、KERNEL=6.18.60
- fwslot：running slot1 serial 12，slot0 serial 7 原样

### 12.5 写入审计

- Linux 侧唯一写入：userdata 暂存（erase + write padded 524,288 B + readback + sync，全部 rc 0）
- U-Boot 侧写入：恰好一次 POST；e2631rescue 内部一次 erase（5 个 eraseblock，0x20000..0xC0000）+ 一次 write（655,360 B / 320 pages）
- 未触碰：env 块 0xC0000..0xE0000、secondboot 0x0..0x20000、tail 0xE0000..0x100000；未使用 saveenv/mtd write/erase/nand write/erase/e2631flash/loadx/xmodem
- U-Boot 命令清单无 forbidden 项；POST 只有 write-post 一条

### 12.6 flash 提示符救援的验收意义

旧 E4 在 §8 的失败是“flash 冷启动路径直接进 e2631rescue，refclk 未初始化 -> PHY -110”。patch 0034 在 do_e2631rescue 里先调用 e2631_net_refclk_init() 再 net init。本次从 flash 提示符（BootROM -> secondboot -> 0034 U-Boot）以 e2631rescue 第一条网络命令复测：PHY autoneg done、lan1 up 1 Gbps、GET / 200、validate 200 sha_match=ok。因此 §8 的缺口在 0034 上已关闭。

注意：本段是 reset（温复位）后的 flash 提示符，不是物理断电冷启动；真冷启动仍是 task-79 的最后一个 gate，由 Lead 安排用户断电/上电后记录。

### 12.7 驱动原始 verdict=FAIL 的两个 harness 记账缺陷

原始 session-results-original.json 的 25 项检查中 23 项 true，只有：

1. env_sanity=false：驱动把空字符串作为 boot_text 传给 env_sanity，导致 boot_env_ok 恒 false。实际 boot text 含 Loading Environment from MTD... OK，串口中 bad CRC / default environment / Warning: ethernet 计数均为 0；printenv 26 个 flash key + fdtcontroladdr，missing=[]、mismatched=[]、values_ok=true、ethaddr/bootdelay/bootcmd/stdio 全部 ok。修复：env_sanity 接收真实 console history。
2. mt7916=false：postcheck 只读一次 dmesg，当时 Wi-Fi 还没起来。修复：postcheck 轮询 device_facts 直到 MTD0==ac06d7bc、PANICS=0、MT7916=1（300 s 超时），记录每次尝试。live postcheck 已确认 MT7916=1。

两处都是 harness 记账，不是产品失败；离线复核文件 corrected-classification.json 把这两项按实测修正后 verdict=GREEN，原始文件保持 FAIL 原样以保留真实输出。修复后的驱动未再跑设备（不重复写入），仅 py_compile 通过；真冷启动会话可使用同一轮询逻辑。

### 12.8 结论

- task-79 写入部分：旧 E4 的 STEP-1/STEP-2 PASS；0034 第三写 PASS；独立回读 PASS；reset 到 flash 0034 启动 PASS；flash 提示符救援（页面 + validate）PASS；live postcheck PASS。
- task-79 真冷启动（物理断电/上电）验收：GREEN，见 §13。

## 13. task-79 最后一项：真冷启动（物理断电/上电）—— GREEN

### 13.1 触发与方式

- 2026-11-28 09:05:48 启动被动冷启动 watcher，从 /home/qc233/zte/e2631-serial-boot-002.log 的当前 offset 721374 开始读取；不向控制台发送任何输入，不写 flash。
- 用户在 09:12 前后物理断电并重新上电；watcher 记录到新的一段 BootROM 启动。

### 13.2 串口标记（完整段复读）

| 标记 | 出现 |
|---|---|
| Boot SPI NAND / start read secondboot（BootROM -> secondboot） | 是 |
| banner U-Boot 2027.01-rc2-g1673d5c89c7b（来自 flash） | 是 |
| Loading Environment from MTD... OK | 是 |
| e2631boot: slot0 / slot1 / cspboot would boot slot1 | 是 |
| Starting kernel ... | 是 |
| Run /sbin/init as init process | 是 |
| Please press Enter to activate this console | 是 |
| e2631-wifi-boot: waiting 25s -> MT7916 ready -> automatic Wi-Fi initialization complete | 是 |

- 无 panic/abort/reset 标记；没有任何控制台输入；完整串口段 21,101 B，见附件 serial-segment-full.txt。

### 13.3 只读 SSH postcheck（uptime 64 s）

- MTD0=ac06d7bcccfc1ed2baa18e792cffce8c7912981eb5491e5b3ea67b1a1172325f（与 §12 写入结果一致）
- REGION=23395533c123ea1099c951fee55a73f264636ca9d33d8298b160efb6d0fdb7d1
- ENV=6e2c01da…、SECONDBOOT=540db435…、TAIL=b5a41c37…（全部与写前一致，冷启动没有改动 flash）
- PANICS=0、OOPS=0、MT7916=1、WiFi complete=1、VERSION=ImmortalWrt v1.10.0、KERNEL=6.18.60
- fwslot：running slot1 serial 12，slot0 serial 7 原样

### 13.4 watcher 的原始 FAIL 与 harness 修复

- watcher 原始 verdict=FAIL。原因：循环退出条件写成 deadline - 1700，而 deadline 是启动后 1800 s，启动 100 s 后该条件已经恒真；kernel 标记后约 1 s watcher 就退出并去做 health，没读到后面的 console/Wi-Fi 行（health 反而证明 Linux 已起）。
- 这是纯 harness 计时缺陷，不是启动失败。修复：linux 标记优先退出；kernel 标记后最多再等 90 s；同时增加 init/console 标记。修复后的 watcher 未再跑真冷启动（不重复要求用户断电），离线用完整串口段复核 corrected-classification.json -> GREEN。
- 原始 watcher 输出保存在 watcher-original-results.json，未改动。

### 13.5 结论

- 真冷启动从 BootROM 经 secondboot、flash 0034 U-Boot、e2631boot 到 Linux 全链路通过；网络、Wi-Fi、mtd0 全部符合预期。
- 至此 task-79 的写入、回读、复位启动、flash 提示符救援、真冷启动五项全部 GREEN。

## 附件

- driver.txt / driver-stdout.txt：驱动日志与 stdout（含 step1/step2 状态机）
- serial.txt / console-history.txt：原始串口字节与 Console 历史（含 resident rescue 失败原文）
- session-results.json：驱动真实输出（含 error、postcheck、checks、verdict=ERROR）
- step1/step2 的 page/post/status done 响应；postcheck.txt
- tool-e4_rescue_write.py：本次驱动
- final-coldboot/：§13 真冷启动证据包（watcher-original-results.json、corrected-classification.json、serial-segment-full.txt、health.txt、capture 日志、修复后的 watcher、SHA256SUMS.txt）
- final-0034/：§12 的完整证据包（session-results-original.json、corrected-classification.json、serial/console、POST/status、resident page/status/validate、live-postcheck.txt、tool-e4_final_0034.py、SHA256SUMS.txt）
- artifact-SHA256SUMS.txt / artifact-UBOOT-INFO.txt

