# E4 救援写模式验收（task-79）—— 写入 PASS、复位 PASS、冷启动救援 FAIL

日期：2026-11-28（CST）
设备：ZTE ZXHN E2631 / ZX279128S，ImmortalWrt v1.10.0，kernel 6.18.60
产物：uboot-build run 46036894542，34 个 patch 之前的 E4 镜像（patch 0026-0033，tree cd67a041…）
结论：STEP-1 净零写入 PASS、STEP-2 真实 E4 写入 PASS、独立回读 PASS、reset 回 flash 启动 PASS；从 flash 冷提示符直接运行 e2631rescue FAIL（PHY autoneg timeout，见 §8）。写入验收本身通过，失败点是救援模式在 flash 冷启动路径上的 refclk 初始化缺口，归入 patch 0034 修复队列。

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

1. patch 0034 冷启动救援验收：冷启动（用户断电或至少 flash E4 冷复位）-> 中断 autoboot -> e2631rescue 作为第一条命令 -> PHY autoneg 正常、GET /、/status、validate PASS；零写入。
2. 第三写（把 patch 0034 镜像刷入 flash）需要 Lead 再次向用户申请批准；本文件不包含该动作。
3. 证据附件见 evidence/e4-rescue-write/ 与 SHA256SUMS.txt。

## 附件

- driver.txt / driver-stdout.txt：驱动日志与 stdout（含 step1/step2 状态机）
- serial.txt / console-history.txt：原始串口字节与 Console 历史（含 resident rescue 失败原文）
- session-results.json：驱动真实输出（含 error、postcheck、checks、verdict=ERROR）
- step1/step2 的 page/post/status done 响应；postcheck.txt
- tool-e4_rescue_write.py：本次驱动
- artifact-SHA256SUMS.txt / artifact-UBOOT-INFO.txt

