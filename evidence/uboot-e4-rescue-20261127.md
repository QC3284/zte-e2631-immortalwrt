# E4 v1 救援模式与厂商复位：CI 构建记录（task-72 / task-76，2026-11-27）

## 0. 结论

- E4 v1（救援模式）与厂商复位已作为 patch 0026-0029 进入 kit；首个构建 run `46002766353`（head `c91e976`）
  全绿，但随后 verify-docs 审出 patch 0028 的写窗口/源指针缺陷（§2.1），已修正；task-77 又给 env 读取加了
  重试与失败现场打印（patch 0030）。合并后的 30 个 patch 的 post-am tree 是
  `3be7118d0e192cc2157ce2f734a5496d6d8738c1`，构建身份见 §4.1。
- 镜像：banner `U-Boot 2027.01-rc2-ga9d4df78ce6e (Nov 19 2026 - 15:44:39 +0000)`，`u-boot.bin` 360,624 B
  （sha256 `49acded8d7b7a664dab7f45aab683b020cc583004aa423c3c47d996c064354e6`，crc32 `b431eb15`），
  mtd0 镜像 sha256 `79dab60d3ce0e3eb72037cd6afb3431b89071824c6449df377d62cb233095a28`，env 块保持
  `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426` 未变。
- 尺寸：defconfig 瘦身后的 320,848 B → 360,624 B（+39,776 B，+12.40%）。设计文档的 Option A 估算是
  +16..34 KB，本次超出估算上限 4,960 B（+4.84 KiB），但距 mtd0 载荷硬上限仍有 292,688 B 余量；若 Lead
  要求严格 ≤34 KB，可再做一个只删未用命令/子系统的 defconfig-only patch，不影响本功能。
- 写入口不变量未变：D-U1 调用点白名单仍恰好 4 个 site（`e2631_write_range`/`e2631_erase_range`/
  `do_e2631flash`/`e2631_env_write_block`，`-O2` 内联后落在 `do_e2631flash`/`do_e2631env_save`）；救援页只经
  `e2631_flash_*` job API 写 mtd0，没有第二个 MTD 写实现。

## 1. 交付

| patch | 内容 |
| --- | --- |
| 0026 | 最小 TCP 栈 + DHCP 服务器（bl-mt798x-dhcpd，GPL-2.0，`e4cf4dc7`），适配本树 legacy net API；新增 `arp_wait_clear()` 与 `CONFIG_MTK_TCP` 的 `PROT_TCP` 钩子 |
| 0027 | `e2631flash.h` 五步写 job API（begin/erase/blank_check/write_image/readback/compare/end），救援页复用 |
| 0028 | `e2631rescue`：DHCP + 极简 HTTP + gzip 救援页 + SHA-256/确认头契约 + 结构校验 + mtd0 五步写（task-78 修正窗口/源指针） |
| 0029 | 厂商 TOPCRM 软复位：`mdelay(50)` 后向 `0x94000044` 写 1，替换占位 `reset_cpu()` |
| 0030 | task-77：`env_mtd_load()` 读+import 重试 3 次；最终失败打印偏移、CRC32 与前 64 字节，env 仍只读 |
| 0034 | task-78/E4 cold boot：`do_e2631rescue()` 在 `net_init()`/`eth_init()` 前显式调用幂等的 `e2631_net_refclk_init()`，让救援从 flash 冷启动第一条命令即可用；CI 新增 cold rescue gate（§5.2） |

## 2. 运行契约（v1 冻结）

- 入口：串口执行 `e2631rescue`；lan1 上 DHCP 服务器（本机 192.168.1.1/24，池从 192.168.1.100 起）与
  HTTP 服务器（80 端口）启动；Ctrl-C 退出，退出时若正在写会打印中断告警。
- `GET /`：内嵌 gzip 救援页（`Content-Type: text/html`、`Content-Encoding: gzip`），无外网依赖。
- `GET /status`：`text/plain`，每行 `key=value`；`stage` 取值 idle/staged/validating/erase/blank/write/
  readback/compare/done/error，另有 `progress`、`crc32`、`sha256`、`browser_sha256`、`sha_match`、`result`、
  `error`。
- `POST /flash?mode=validate|write`：raw body 必须恰好 655,360 B（mtd0 整镜像）；`mode=write` 还要求
  `X-E2631-SHA256`（小写 hex，整文件 SHA-256）与 `X-E2631-Confirm: write`；校验/结构检查失败一律 HTTP 400 +
  `result=error`，不进入擦除。结构检查：size、`+0x10` 内层 magic `0x73383231`、`+0x14` payload 长度窗口、
  padding 全 0xFF、payload 含 `U-Boot 20`。v1 没有 header CRC（保持厂商头格式与 net-zero 字节一致）。
- 写窗口：mtd0 `0x20000..0xC0000`（U-Boot 区 655360 B，写长度 0xA0000，源指针=镜像首地址，到 env 前为止）；
  secondboot `0x0..0x20000`、env `0xC0000..0xE0000`、保留区 `0xE0000..0xFFFFF` 一律不碰；成功后不自动重启，
  串口/页面都提示手动 `reset` 或断电。

### 2.1 task-78 写窗口修正（设备写入前）

首个构建的 0028 写的是 `0x20000..0xA0000`、长度 `0x80000`，并且 begin/write/compare 的源指针误加了
`0x20000`：头 0x800 字节永远不会落盘，payload 被整体前移，erase 窗口也短了 0x20000，而回读比较用的
是同一条错位的源——会打印 PASS 并损坏 flash。修正为 OFF=0x20000、LEN=0xA0000、MTD0_END=0xC0000
（= `CONFIG_ENV_OFFSET`），三处源指针都改成镜像首地址，并用编译期断言 + CI 回归门禁锁死
（源=镜像首地址、erase/write/compare 同窗、窗口 0x20000..0xC0000）。本文件后续的构建身份与验收步骤
都以修正后的镜像为准。

## 3. CI 门禁（新增/沿用）

- 配置：`CONFIG_MTK_TCP=y`、`CONFIG_MTK_DHCPD=y`、`CONFIG_SHA256=y`、`# CONFIG_MTK_TCP_VERBOSE is not set`。
- 二进制：`e2631rescue` 命令与 `serve the web bootloader rescue on lan1`、`X-E2631-SHA256`、
  `X-E2631-Confirm: write`、`e2631rescue: PASS: mtd0 updated` 必须命中。
- 源码形状：`e2631rescue.c` 含 `e2631_flash_begin`/`sha256_csum_wd`/`e2631_failsafe_html_gz`，且不含
  `mtd_write`/`mtd_erase`；`zxhn-e2631.c` 含 `ZX279128S_TOPCRM_SOFT_RST` 与 `mdelay(50)`。
- 写窗口回归（task-78）：断言 `E2631_RESCUE_FLASH_OFF=0x20000`、`LEN=0xA0000`、`MTD0_END=0xC0000 ==
  CONFIG_ENV_OFFSET`、三处源指针是镜像首地址、erase/write/compare 同窗；出现 `img + E2631_RESCUE_FLASH_OFF`
  或 `rescue_image() +` 直接失败。
- env 重试（task-77）：`env/mtd.c` 含 `ENV_MTD_READ_RETRIES`、读循环重试、`env_mtd_dump_failure` 与
  `env_mtd: stored crc 0x%08x, data crc 0x%08x` 诊断串。
- UBOOT-INFO：分别报告装配后 mtd0 首 0x800 sha256 与厂商模板 sha256（模板的 +0x14 长度字段会被重写），
  banner 用完整 token 匹配（`U-Boot <year>.<mm>-rc<n>-g<sha> `），不再匹配 `U-Boot 20` 前缀。
- 救援页资产：`tools/embed-failsafe.sh` 生成确定性 gzip（本次 raw 9,216 B / gzip 4,456 B，上限 6,144 B），
  workflow 在 `git am` 之后、`make` 之前嵌入。
- 保留：`# CONFIG_CMD_MTD_WRITE is not set`、`# CONFIG_CMD_SAVEENV is not set`、MTD 写调用点白名单、
  `CONFIG_TEXT_BASE=0x47F00000`、入口点、尺寸上限、可复现构建（`SOURCE_DATE_EPOCH` +
  `git am --committer-date-is-author-date`）。

## 4. 首个构建（run 46002766353；写窗口缺陷，已被 §4.1 取代）

| 项 | 值 |
| --- | --- |
| kit head | `c91e9765032a11ee240264c38b864c4ac63bdb8e` |
| uboot-build run | `46002766353`（SUCCESS） |
| kit check.yml run | `46002763627`（SUCCESS） |
| banner | `U-Boot 2027.01-rc2-ga9d4df78ce6e (Nov 19 2026 - 15:44:39 +0000)` |
| u-boot.bin | 360,624 B / sha256 `49acded8d7b7a664dab7f45aab683b020cc583004aa423c3c47d996c064354e6` / crc32 `b431eb15` |
| mtd0 镜像 | 655,360 B / sha256 `79dab60d3ce0e3eb72037cd6afb3431b89071824c6449df377d62cb233095a28` / crc32 `f5f18b5c` |
| mtd0 首 0x800 | sha256 `1b55581d0372b1abe6ec36ceb11cd22f4828ccf3509a69bc9d269e8c227f4eb9`（装配后；模板输入仍是 `19a9d546...`） |
| env 块 | sha256 `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`（未变） |
| `.config` | sha256 `d3a8450a810064adce1152741cf563237a587e1c2875ad598eaa6c5f969a7a5a` |
| checkpatch | 0 errors / 0 warnings（四类 ignore 后；0026 另有 24 条非阻断 CHECK） |
| artifact | `/home/qc233/zte/e2631-t5-artifacts/uboot-e4-46002766353/e2631-uboot-46002766353/` |

命令帮助（E2631-COMMAND-HELP.txt）：`e2631flash`/`e2631verify`/`e2631slot`/`e2631env`/`e2631rescue` 五段与
二进制字符串均已确认；`e2631rescue` 短帮助为 `serve the web bootloader rescue on lan1`。

## 4.1 合并构建（task-78 + task-77，run 46010298863）

| 项 | 值 |
| --- | --- |
| kit head | `b995ecdd949185b9c129d60913ef82aef183b75e` |
| uboot-build run | `46010298863`（SUCCESS，head `b995ecd`） |
| kit check.yml run | `46010266268`（SUCCESS） |
| 30 patch post-am tree | `3be7118d0e192cc2157ce2f734a5496d6d8738c1` |
| banner | `U-Boot 2027.01-rc2-g6db632ad6e5b (Nov 19 2026 - 15:44:39 +0000)` |
| u-boot.bin | 361,448 B / sha256 `a693afdb7f14e04115deecaf0f599c52329caa2cdf381d7ec650b8c7e056cbc3` / crc32 `4139ba37` |
| mtd0 镜像 | 655,360 B / sha256 `62bf1244d69471e2454be966694421dc2d6f8c8ce427393f7b056837d4893d71` / crc32 `fed99379` |
| mtd0 首 0x800（装配后） | sha256 `036d5dc72ee0d0fd020e1a542ee7b93ab750ec3ba1cc700e402ba9acd6ce0f4a` |
| 厂商模板 0x800（输入） | sha256 `19a9d54614e9d5cdfb7573495609448cdf1a740e470fbebcac5783c8e9b93510` |
| env 块 | `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`（未变） |
| `.config` | `d3a8450a810064adce1152741cf563237a587e1c2875ad598eaa6c5f969a7a5a` |
| checkpatch | 0 errors / 0 warnings（四类 ignore 后；24 条非阻断 CHECK 全部在 0026 既有代码） |
| D-U1 白名单 | `mtd writer sites: 4`（未变） |
| 新门禁 | `E4 rescue window gate: ...`、`env retry gate: ...` 均输出；0 条 `##[error]` |
| 尺寸 | 相对首个 E4 构建 360,624 → 361,448 B（+824 B）；相对 slim 320,848 B 为 +40,600 B（+12.65%）；距 CI 门禁余量 283,672 B |
| artifact | `/home/qc233/zte/e2631-t5-artifacts/uboot-e4fix-46010298863/e2631-uboot-46010298863/`（SHA256SUMS 11/11 通过） |

真机写入顺序不变：先由 verify-docs 的离线门禁 `e4_prewrite_check.py --archive <上面目录>` 通过，再申请用户
批准；本构建不自动重启，写后外部复核 mtd0 全盘 sha256 应等于 `62bf1244...`。

## 5. 零写入真机验收（下一次设备会话，写入步骤需用户单独批准）

1. 先做 RAM 链或 flash 链只读验证：`e2631rescue` 启动服务但**不创建写任务**；PC 能 DHCP、能打开页面、
   `GET /status` 为 `stage=idle`。
2. 上传一个错误文件（长度错误/坏 magic/错误 SHA）：必须 HTTP 400 + `result=error`，`/status` 不出现
   erase/write，flash 内容不变（前后 mtd0 全盘 sha256 相同）。
3. 上传正确 net-zero mtd0 镜像并点“仅校验”：返回 `result=ok` 与 CRC32；此时仍未擦除。
4. 只有在用户批准的写会话里才点“写入待命”：记录写前 mtd0 全盘 sha，观察阶段行与串口日志，结束后
   复核写后 mtd0 sha 与预期一致（新镜像 `79dab60d...`），再执行 `reset`。
5. 若写中途失败/断电：串口仍是唯一恢复通道，按 task-54 的 rescue ladder 处理；救援页不自动重启。

## 5.1 E4 phase-1 验收缺陷与修复（patch 0033，2026-11-28）

E4 v1 阶段一（只读：`GET /` + `/status` + POST validate）在 F2 修复构建（banner `gd38f69c44523`）上
暴露一个固件缺陷：`GET /` 与 `GET /status` 正常，但 `POST /flash?mode=validate`（655360 B net-zero body +
`X-E2631-SHA256`）返回 HTTP 400 `result=error error=unsupported request`。tcpdump 证明 TCP 握手、GET 200
与 POST 请求都已到达，问题在请求处理而不是传输。

根因：`rescue_name_is()` 把收到的头行字符逐个折成小写（`rescue_lower(line[i])`），却与调用方传入的
**混合大小写**字面量比较（`rescue_lower(line[i]) != name[i]`）。`'c' != 'C'`，于是
`rescue_header_value(hdr, "Content-Length", ...)` 永远返回 false，`rescue_handle_request()` 直接落到
`goto bad` → “unsupported request”，validate 与 write 两条路径都被阻断。GET 不读请求头，所以此前
看起来正常，TCP 栈也从未有问题。

修复（patch 0033）：比较两侧都折成小写（`e2631_http_lower(line[i]) != e2631_http_lower(name[i])`），
调用方保留可读的 HTTP 拼写；头名与头值辅助函数移进无依赖的 `board/zte/zxhn-e2631/e2631http.h`，
`e2631rescue.c` 只留 `rescue_header_value()` 包装。新增主机侧 fixture
`uboot-port/tests/rescue_headers_test.c`：用捕获的混合大小写 GET/POST 头块（`Content-Length`、
`X-E2631-SHA256`、`X-E2631-Confirm`、全小写变体，以及错误前缀/缺冒号/方法行等反例）回放真实辅助函数；
CI 在 `git am` 之后、交叉编译之前用宿主机 gcc `-Wall -Wextra -Werror` 编译运行，输出
`rescue header fixture: PASS (mixed-case GET/POST blocks resolve)`，失败即中止构建。

真机复测（patch 0033 构建）：按 §5 的第 1、2、3 步重跑；成功签名是 POST validate 返回 `result=ok` +
CRC32（或页面显示校验通过），`/status` 保持 idle，mtd0 不变。write 验收仍需用户单独批准。

### 5.1.1 CI 构建身份（run 46036894542，33 个 patch）

| 项 | 值 |
| --- | --- |
| 运行 | `E2631 A1/A2/A3 U-Boot - iwrt-adaptation - run 39`，run id `46036894542`，head `a97b76c` |
| post-am tree | `cd67a0414737dcbb860072ddbaaf3de16a306b46`（33 commits） |
| banner | `U-Boot 2027.01-rc2-g30dca5f54503 (Nov 19 2026 - 15:44:39 +0000)` |
| u-boot.bin | 365,872 B sha256 `3dbbfc49e7fa580fe5327f9b0f11cddc0fe0d0f92e5a9fde9c37a7efdf133bb6` crc32 `34b252a4` |
| mtd0 image | sha256 `8a38896e9164faa7aca4e9c2737e9d0c2b720f5576ce3ee3ef147109aa0b2bb9` crc32 `79ef8c50` |
| 装配后首 0x800 | sha256 `232513cb16f11c15299716b14cdc3c4fb4e4b2d787c6cd10b01309be0acd29c9` |
| env 块 | `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`（未变） |
| 门禁 | `rescue header fixture: PASS (mixed-case GET/POST blocks resolve)`；`rescue header gate`；`mtd writer sites: 4`；checkpatch `0 errors / 0 warnings`；入口 0x47f00000 |
| 归档 | `/home/qc233/zte/e2631-t5-artifacts/uboot-e4hdr-46036894542/e2631-uboot-46036894542/`（SHA256SUMS 校验通过） |

真机验证（verify-docs，2026-11-28 00:55–00:57，RESCUE_PASS）：同一产物经 userdata 暂存 → flash 15-patch
U-Boot `g85df6772a444` → `mtd read` 暂存镜像 + `crc32 0x34b252a4` → `go` → 新 banner `g30dca5f54503`；
`POST /flash?mode=validate` 返回 HTTP 200 `result=ok sha_match=ok`（此后 `/status` 仍 `stage=idle`），错误摘要
（64 个 `0`）返回 HTTP 400 `error=sha256 mismatch` 且不进入 erase/write；`GET /`、`/status`、F1 Linux 启动
全部 PASS；mtd0 `f9239040…` / region `b1ea9a48…` / env `6e2c01da…` 前后不变，U-Boot 写命令零调用。
证据见 [evidence/e4-rescue-acceptance-20261128.md](../evidence/e4-rescue-acceptance-20261128.md) §11 与
`evidence/e4-rescue-acceptance/run-2/`（kit 提交 `589b4d4`）。写模式验收仍需用户单独批准。

## 5.2 冷启动救援修复（patch 0034，2026-11-28）

真机证据（verify-docs 常驻检查，flash 上 E4 镜像冷启动；`write-run-2/session/serial.log`）：中断 autoboot 后在
提示符直接跑 `e2631rescue`，串口出现
`ethernet@92000000 Waiting for PHY auto negotiation to complete......... TIMEOUT !`、
`zx279128s: PHY startup failed (-110)`、`e2631rescue: no usable Ethernet device`。同一镜像在 RAM 链
（先跑过 `e2631net`/`e2631boot`）救援正常，boot log 里也已打印 `Net:   eth0: ethernet@92000000`。

结论：冷启动第一条命令进救援时，网络参考时钟/SerDes 还没建立，内部 PHY 的 MDIO 不应答，
`phy_startup()` 约 5 s 后超时（-110）。0034 让 `do_e2631rescue()` 在 `net_init()`/`eth_init()` 之前显式调用
幂等的 `e2631_net_refclk_init()`（`refclk_done` 守卫；`e2631boot` 与 eth 驱动 start 也调用同一函数，不会重复下发），
保证“救援不需要先跑别的命令”。CI 新增 cold rescue gate：`e2631rescue.c` 必须 include `e2631net.h`，且
`awk` 截取 `do_e2631rescue()` 后必须能 grep 到 `e2631_net_refclk_init();`。

同一次交付还把两条真机运维规则写进 README §5：救援服务期间不要向 U-Boot 控制台发送任何字符
（`Ctrl-C` 是唯一被识别的输入，会中断排队中的写并打印 WARNING）；同一次开机内救援只用一次
（第二次进入 ARP/SYN 不应答，重进前先 `reset`/断电；静态审计见 task-78 记录）。

静态备注：E2 的 eth 驱动 `start` 自引入起就在最前面调用同一 helper，因此 0034 的直接效果是把“参考时钟
先于 net_init/eth_init（MDIO/PHY probe）”变成显式、不可退化的约束；若真机冷启动救援仍超时，下一层怀疑
是 PHY/SerDes 首次上电的复位与 autoneg 时序，而不是调用缺失。

### 5.2.1 冷启动修复构建身份（run 46046018929，34 个 patch）

- kit 提交 `9ffadd5`（patch 0034 + re-pin + cold rescue gate + README/evidence）；post-am tree
  `0480ef834d718b827e32c1ae9b787f671ca3f5a1`（34 patches），patch 0034 sha256
  `eef4625c0e3689acf7055de3636b2edc5a7a4d0f4e89cc0c3ee0161fc0c1e986`，干净重放验证树一致。
- 构建：uboot-build run `46046018929`（run 40，head `9ffadd5`）SUCCESS；kit check.yml run `46046016648` SUCCESS。
- banner `U-Boot 2027.01-rc2-g1673d5c89c7b (Nov 19 2026 - 15:44:39 +0000)`；`u-boot.bin` 365,872 B
  sha256 `b7ea6bbc138e1b3cbea6389fbaae89419d1d7e46e0668ef88637dd2cd14ac33d` crc32 `9f2b707d`；
  mtd0 镜像 655,360 B sha256 `23395533c123ea1099c951fee55a73f264636ca9d33d8298b160efb6d0fdb7d1`
  crc32 `1e5ff289`；装配后首 0x800 头 sha256 `232513cb16f11c15299716b14cdc3c4fb4e4b2d787c6cd10b01309be0acd29c9`
  （模板输入仍 `19a9d546…`）；env 块 `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426` 未变；
  `.config` `d3a8450a810064adce1152741cf563237a587e1c2875ad598eaa6c5f969a7a5a`；入口 `0x47f00000`。
- 日志证据：`rescue header fixture: PASS`、`cold rescue gate: do_e2631rescue brings up the network reference clocks`、
  `mtd writer sites: 4 (e2631flash and the e2631env writer; -O2 inlines the static helpers)`、
  `e2631env safety guards: present`、checkpatch `errors=0 warnings=0`、
  `Reproducible: git am --committer-date-is-author-date, SOURCE_DATE_EPOCH=1795103079`；
  E4 窗口门禁 / env retry / F2 两个门禁均 PASS。
- 归档路径：`/home/qc233/zte/e2631-t5-artifacts/uboot-coldrescue-46046018929/e2631-uboot-46046018929/`
  （SHA256SUMS 11/11 通过；verify-docs 的 `e4_prewrite_check.py --archive <目录>` 可据此跑离线门禁）。


## 6. 风险与边界

- 写窗口只在 mtd0 U-Boot 区，固件槽位与 env 不在救援范围内（用户裁决：v1/v2 都不刷固件镜像）。
- v1 不校验 payload 内容本身（没有 header CRC），只做结构 + SHA-256 + 回读比较；payload 单字节翻转若同时
  伪造了 SHA 头则无法检出，页面 SHA-256 只是信息性 + 传输完整性。
- 救援页是 U-Boot 内的单线程轮询服务（无中断、无多连接），只适合维护会话；正常启动不初始化网络。
- 复位依赖厂商 TOPCRM 寄存器；若真机上该写不触发复位，串口会停在自旋前提示，断电恢复。
- 救援是“每次开机只用一次”：0034 修好冷启动入口后，同一次开机内 Ctrl-C 退出再进第二次仍可能 RX 不应答
  （缓存的 PHY 对象与 master reset 后状态；见 uboot-port/README.md §5 E4 段）。
- 救援服务期间不要向 U-Boot 控制台发送任何字符（含回车）；`Ctrl-C` 是唯一被识别的输入，会中断排队中的
  flash 写并打印 WARNING。

## 7. 参考

- [docs/E4-多功能U-Boot设计-2026-11-27.md](../docs/E4-多功能U-Boot设计-2026-11-27.md)
- [evidence/e4-bl-mt798x-dhcpd-study-20261127.md](e4-bl-mt798x-dhcpd-study-20261127.md)
- [evidence/e4-reset-re-20261127.md](e4-reset-re-20261127.md)
- [uboot-port/README.md](../uboot-port/README.md) §1/§4/§5
