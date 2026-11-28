# E4 v3 追加功能契约与页面设计（task-89）

日期：2026-11-28（草稿，随 task-90/91/92 实施与复核更新）
状态：契约增量 + 页面设计，供 task-90（U-Boot C）、task-91（页面 v3）、task-92（门禁/构建）、task-93（真机验收）实施。
依据：任务卡 task-89；用户 2026-11-28 裁决「能加上的就加上，加不上的就不管」；Lead m14641 清单；v2/v2.1 契约 `evidence/e4-v2-contract-design-20261128.md`；构建产物 `uboot-e4v2-46109519805`。

## 0. 结论摘要

| # | 追加项 | 判定 | C/资源成本估计 | 主要风险 |
|---|---|---|---|---|
| ① | POST /reboot | 可行 | 约 150 B | 远端重启；只在用户点击时执行 |
| ② | GET /backup?part=slot0\|slot1\|rootfs\|header | 可行 | 约 350 B（复用现有流式代码，改 part 表 + 1 MiB 块） | 28 MB 传输/ACK 窗口；占用单飞锁 |
| ③ | GET /log | 可行 | 约 450 B | 只做「进入救援时快照」，不含之后日志 |
| ④ | GET /sysinfo | 可行 | 约 650 B | CP15 读取与 SPI-NAND ID 需复用/导出 helper |
| ⑤ | POST /integrity | 可行 | 约 480 B | 读 655,360 B 约 0.1–0.3 s；与写任务互斥 |
| ⑥ | LED 救援指示 | 可行 | 约 250 B | 蓝灯闪；退出/重启恢复原电平 |
| ⑦ | DHCP 配置页（e2631_dhcp_*） | 可行 | 约 600 B | 配错后下次救援网络不可达，页面需给恢复默认 |
| ⑧ | I18N 中英 | 条件可行 | 页面 gzip +5,500～7,000 B（仅页面资产，不进 C 代码） | 与 32,768 B / 240 KB 双预算冲突时按用户授权砍 I18N |
| 补 | 产品前缀 16→17（patch 0040） | 必须 | 约 0（一行宏 + 夹具） | 与 Linux `e2631-fwslot` 的 17 B 比较对齐 |

预算结论（详见 §12）：当前 u-boot.bin 405,368 B，硬上限 653,312 B，余量 247,944 B；任务卡硬门「二进制余量 ≥ 240 KB」= 245,760 B，只剩 2,184 B 余量。必须先做回收包 P1：关闭 `CONFIG_CMD_FDT`（8,229 B）与 `CONFIG_CMD_TFTPBOOT`（4,151 B），回收约 12,380 B，再容纳 v3 的 C 代码与页面资产增长。若实测超出，再启用 P2 关闭 `CONFIG_CMD_MII`（约 5,724 B）；仍不够则按用户授权砍 I18N。

## 1. 通用规则

- 基址与端口：`http://<设备LAN地址>/`，默认 `192.168.1.1:80`；DHCP 客户端池默认 `.100` 起（见 §9）。
- 响应：全部 `text/plain; charset=utf-8` 的 `key=value` 行（下载类除外），行序按本文固定；`result=` 为 `ok|error|accepted`，`error=` 为短文本（页面必须容忍未知键并在未知 `result` 时按错误处理）。
- 方法/路径：未知路径 `404 result=error error=not found`；已知路径方法不符 `405 result=error error=method not allowed`；写任务/备份占用时 `409 result=error error=busy`。
- 确认头：所有会改变设备状态的动作必须同时带 `X-E2631-Confirm: <动作>`（`write`/`reset`/`reboot`），缺失或值不符 `400 result=error error=missing confirm`；`/reboot` 用 `reboot`，不复用 `write`。
- 空 body：`/reboot`、`/integrity` 不带 body；带非空 body 时 `400 result=error error=bad body`。
- 单飞：同一时刻只允许一个写任务（flash/firmware/factory/envwrite）或一个 `/backup` 流；`/reboot` 在任一任务或备份进行中返回 409。
- 超时：控制类端点 10 s；`/integrity` 建议 15 s；`/backup` 整槽 120 s（页面用浏览器原生下载，不自行计时）；`/reboot` 响应在复位前发出，客户端可能在复位后收不到 FIN，属正常。
- 安全性：救援页无鉴权（用户明确接受）；新增 `/reboot` 与既有 `/console` 同属 LAN 内可执行动作，文档记录，不加口令门。

## 2. GET /status v3 追加字段

保留 v1/v2/v2.1 全部键，追加（不得改名）：

| 键 | 值 | 来源/说明 |
|---|---|---|
| `log_bytes` | 十进制 | 进入救援时抓取的启动日志字节数（快照） |
| `log_overflow` | `0|1` | 抓取前 CONFIG_CONSOLE_RECORD 是否已溢出 |
| `dhcp_ip` | 点分 IPv4 | 本次救援实际使用的 LAN 地址 |
| `dhcp_netmask` | 点分 IPv4 | 实际掩码 |
| `dhcp_pool_start` | 十进制 | 实际池起点（host 字节） |
| `dhcp_pool_size` | 十进制 | 实际池大小 |
| `dhcp_source` | `env|default|fallback` | env 生效/未设置/设置非法已回落 |
| `dhcp_warning` | 文本（可空） | 非法键的逗号列表，例如 `bad e2631_dhcp_pool_size` |
| `backup` | `idle|active` | 是否有 `/backup` 流在跑 |
| `backup_part` | 文本（可空） | 当前流的分区名 |
| `reboot_pending` | `0|1` | 已接受 `/reboot`、等待复位 |

## 3. GET /sysinfo

请求：GET，无参数、无 body；只读。响应 `text/plain`，固定键序：

```
result=ok
version=<version_string()>
banner=<version_string()>
build=<U_BOOT_DATE> <U_BOOT_TIME>
board=ZTE ZXHN E2631
soc=ZX279128S
cpu=ARM Cortex-A9
dram=0x<gd->ram_size>          # 16 进制
dram_mb=<十进制 MiB>
mtd0_size=0x100000
spi_nand=spi-nand0
spi_size=0x8000000
spi_erasesize=0x20000
spi_writesize=0x800
spi_oobsize=0x40
spi_id=<10 位十六进制>        # spinand->id.data[5]
sctlr=0x........
midr=0x........
clidr=0x........
ttbr0=0x........
vbar=0x........
actlr=0x........
dacr=0x........
pll_a9_cfg0=0x........        # 0x94000018
pll_a9_cfg1=0x........        # 0x9400001c
top_ctrl8=0x........          # 0x94000008
top_clk_sel=0x........        # 0x9400000c
crm2_10=0x........            # 0x94100010
crm_4c=0x........             # 0x9400004c
lsp1_04=0x........            # 0x9a100004
net_pll_cfg0=0x........       # 0x94000050
net_pll_cfg1=0x........       # 0x94000054
cpu_mhz=<十进制或 unknown>
cpu_mhz_source=known|pll|unknown
```

实现要点：
- DRAM/板级信息取 `gd->ram_size`、`version_string()`、`U_BOOT_DATE/U_BOOT_TIME`；
- MTD 字段取 `spi-nand0` 的 `struct mtd_info`（`size/erasesize/writesize/oobsize`）；SPI ID 取 `mtd_to_spinand(mtd)->id.data[5]`（`include/linux/mtd/spinand.h:270` `SPINAND_MAX_ID_LEN`、`:691 mtd_to_spinand`）；
- CP15 读取复用 `board/zte/zxhn-e2631/e2631soc.c` 的 inline asm（SCTLR/CLIDR/TTBR0/VBAR/ACTLR/DACR/MIDR）；建议把只读 helper 导出到 `e2631soc.h`，不要复制两套；
- `cpu_mhz`：优先按内核 `target/linux/zx279128/files/drivers/clk/zte/clk-zx279128s.c:150-160` 的 PLL 公式（`osc * (fbdiv + frac/2^24) / pd1 / pd2`，`osc` 用 DTS 的晶振频率）从 `0x94000018/1c` 计算，`cpu_mhz_source=pll`；若取不到晶振/公式有疑，输出 `cpu_mhz=1000` 与 `cpu_mhz_source=known`（secondboot 固定 A9 1 GHz，实测数据见 `evidence/p2-flashboot-kernel-hang-20261121.md`），或 `unknown`；不得让字段缺失导致页面崩；
- 读取失败：`500 result=error error=<短原因>`；不写 flash、不写 env；
- 重复调用幂等；不加缓存（页面只在标签打开/刷新时调用）。

## 4. GET /log

语义：**进入救援模式时的启动日志快照**，不是实时日志流；快照之后页面/救援动作产生的输出不再进入该快照。

数据来源：`CONFIG_CONSOLE_RECORD=y`（defconfig:20-21，`CONFIG_CONSOLE_RECORD_OUT_SIZE=0x4000`）的 ring；`console_record_init` 在 `board_f.c:957` 与 `board_r.c:623` 的 INITCALL 已启动记录。`e2631rescue` 入口处（打印救援 banner 之前）用 `console_record_readline()` 读空 ring，拼成一块静态缓冲区（malloc 或静态 16,384 B），记录 `log_bytes` 与溢出位（`GD_FLG_RECORD_OVF`）。

端点：
- `GET /log`：`text/plain; charset=utf-8`，body 为原始日志行（保留 `\n`，不转义）；响应头 `X-E2631-Log-Bytes: <十进制>`、`X-E2631-Log-Overflow: 0|1`、`Content-Length`。
- `GET /log?download=1`：同上 + `Content-Disposition: attachment; filename="e2631-bootlog.txt"`。
- 方法不符 405；读取失败（缓冲区未建立）500 `result=error error=log unavailable`。
- 快照只生成一次；页面多次刷新返回同一内容。页面显示「日志截止进入救援模式时」。

## 5. POST /integrity

只读完整性自检：对 mtd0 `0x20000..0xC0000`（655,360 B，U-Boot 镜像区）计算 CRC32 与 SHA-256，复用 `e2631verify` 的读路径（`e2631flash.c:417` `do_e2631verify`），不写 flash。

请求：POST，空 body。可选期望摘要：query `expect=<64 hex>` 或 header `X-E2631-Expected-Sha256: <64 hex>`（二选一；同时给以 query 为准）。

响应 200 `text/plain`：
```
result=ok
offset=0x20000
length=0xa0000
crc32=0x........
sha256=<64 hex>
match=ok|mismatch|absent
expected=<64 hex>        # 仅当请求提供 expected 时
```

错误：expected 非 64 位小写/大写十六进制 → `400 result=error error=bad sha256`；method=GET → 405；已有写任务或 backup 进行中 → `409 result=error error=busy`；读失败 → `500 result=error error=flash read failed`。
页面按钮「完整性自检」调用；页面可把返回的 `crc32` 与 `/status` 的 `bootloader_region_crc32` 比对显示「一致/不一致」。

## 6. GET /backup?part= slot0|slot1|rootfs|header

在 v2.1 的五个分区（`bootloader/tag/wifi/usercfg/defcfg`）基础上追加四个整槽/窗口下载，全部只读：

| part | 物理偏移 | 长度 | 说明 |
|---|---|---|---|
| `slot0` | `0x00700000` | `0x01C00000`（29,360,128 B） | 完整 slot0 |
| `slot1` | `0x02300000` | `0x01C00000`（29,360,128 B） | 完整 slot1 |
| `rootfs` | `next_slot==0 ? 0x00B00000 : 0x02700000` | `0x01100000`（17,825,792 B） | 下一次启动槽的 rootfs 窗口（对齐 mtd7 alias 语义） |
| `header` | `next_slot==0 ? 0x01C00000 : 0x03800000` | `0x00020000`（131,072 B） | 下一次启动槽的版本头块 |

传输：沿用 v2.1 的流式实现（`rescue_backup_start`/`rescue_backup_block`），但整槽类使用 1 MiB bounce 缓冲（`malloc_cache_aligned`）按 1 MiB 分块 `mtd_read` 后 `mtk_tcp_send_data`；发送前先完整读一遍计算 CRC32+SHA-256（两遍读），响应头在 body 前；`Content-Length` 必须精确。小分区仍可用 16 KiB 块。

响应（与 v2.1 相同头）：`application/octet-stream`、`Content-Disposition: attachment; filename="e2631-<part>.bin"`、`Content-Length`、`X-E2631-CRC32`、`X-E2631-SHA256`、`X-E2631-Offset`、`X-E2631-Length`、`X-E2631-Part`。

约束：`/backup` 仍不占写锁，但同一时刻只允许一个流（否则 409 busy）；传输中 `/reboot` 返回 409；未知 part 400；method 不符 405。页面只读下载，不提供写回。

## 7. POST /reboot

用途：让用户从救援页把设备复位回正常启动（patch 0029 已把 `reset_cpu()` 接到厂商 TOPCRM `0x94000044`）。

请求：POST，空 body，必须带 `X-E2631-Confirm: reboot`。
守卫：任一写任务（flash/firmware/factory/envwrite）或 `/backup` 流进行中 → `409 result=error error=busy`；不做部分重启。
时序：先 `200 result=accepted\nreboot=1\n` 并等待 TCP ACK（`mtk_tcp_send_data` 返回），在救援循环里 `get_timer` 延时约 300 ms 后调用 `reset_cpu(0)`（`e2631soc.c`/`zxhn-e2631.c` 现有 vendor reset 路径）；串口打印 `resetting ...`。
页面语义：成功文案固定为「设备正在重启，约 20–30 秒后回到系统；重启后不再处于救援模式」；页面在收到 accepted 后禁用按钮并停止轮询，不自动刷新；不使用 U-Boot `reset` 命令（Linux 运行时按住 reset ≥5 s 是恢复出厂语义，页面不得提示）。
失败：若复位未发生（理论上 patch 0029 已真机验证），页面超时提示「请断电重启」；不得在复位前擦写任何 flash。

## 8. LED 救援指示

硬件：蓝色 LED = 板级 DTS `led_blue`，`&gpio0 8`（flat 8，bank0 bit8），active-low，默认熄灭（`target/linux/zx279128/dts/zx279128s-zte-zxhn-e2631.dts:95-99`）。

行为：
- `e2631rescue` 进入时保存 bank0 的 `DIR`（`0x94407000`）与 `DATA`（`0x94407014`）32 位值；把 bit8 设为输出，按 1 Hz（500 ms 亮/500 ms 灭，active-low 即 DATA bit8 0/1 交替）闪烁；
- 在救援循环里用 `get_timer` 翻转，不额外建线程/中断；
- 退出路径（Ctrl-C、错误返回、/reboot 复位前）恢复保存的 DIR/DATA 对应 bit（只改 bit8，其他位保持）；
- 不驱动绿灯（内核心跳）/红灯（状态）；
- `/status` 不新增 LED 字段；页面文案：「蓝色 LED 慢闪 = 救援模式；离开救援或重启后恢复」。

## 9. DHCP 配置（e2631_dhcp_* env 白名单键）

新增四个 env 键（白名单前缀 `e2631_` 已允许写；`e2631env` 五步写所有者不变）：

| 键 | 默认 | 取值 | 说明 |
|---|---|---|---|
| `e2631_dhcp_ipaddr` | `192.168.1.1` | 点分 IPv4 | 救援模式 LAN 地址（HTTP 基址） |
| `e2631_dhcp_netmask` | `255.255.255.0` | 点分 IPv4 | 掩码 |
| `e2631_dhcp_pool_start` | `100` | 1..254 | DHCP 池起始 host 字节 |
| `e2631_dhcp_pool_size` | `101` | 1..200 | 池大小（100..200 共 101 个） |

优先级：`e2631_dhcp_*` > 旧 `dhcpd_pool_start`/`dhcpd_pool_size`（只读兼容，页面不写） > 内置默认。服务器地址/掩码不再从旧 `ipaddr`/`netmask` 取（避免与 vendor env 混用）。

应用时机：只在 `e2631rescue` 启动时读取；页面写入成功后提示「下次进入救援模式生效（Ctrl-C 退出后重新执行 e2631rescue，或断电重启后按键进入）」，不在运行中改网络。

校验：地址/掩码必须合法；池起点 1..254；池大小 1..200；池起点+大小−1 ≤ 254；池不得包含服务器地址。启动时非法值 → 回落到默认并在 `/status` 报 `dhcp_source=fallback`、`dhcp_warning=`。`POST /env` 对这四个键额外做语义校验（非法 → `400 result=error error=bad value`），其余键仍按 v2.1 规则。

实现：`rescue_loop()` 在 `net_init()` 前读配置，设置 `net_ip/net_netmask/net_gateway/net_dns_server`；`net/mtk_dhcpd.c` 的 `dhcpd_get_pool_start_host/size` 增加 `e2631_dhcp_*` 优先分支（不写 env）；服务器 IP/掩码从 `net_ip/net_netmask` 取（现有 `CONFIG_MTK_DHCPD_USE_CONFIG_IP` 未开启）。

页面：环境变量标签新增「DHCP 配置」卡片（四个输入框 + 保存 + 恢复默认），prefill 自 `/env` 的 `e2631_dhcp_*`（缺失用默认值）；保存时逐键 POST /env（每键等 `/status` op=envwrite 完成），双确认；显示 `/status` 的 `dhcp_*` 生效值与 warning。

## 10. I18N 中英双语（条件项）

用户授权：功能全加，但预算超时先砍 I18N。实现只在页面，不改 C/协议。

方案：单文件内建字典 `I18N = { zh: {...}, en: {...} }`；元素用 `data-i18n`（文本）、`data-i18n-title`（title/aria-label）标记；`t(key, params)` 插值；侧栏顶部语言开关（`id=lang`，中文/EN）；默认 zh；`localStorage` 键 `e2631_lang`；切换时更新 `<html lang>`、所有 `data-i18n` 节点与动态生成文本；缺失键回落 zh；不引入外部 i18n 库/字体/CDN。

覆盖：六个标签名、卡片标题、按钮、字段标签、状态/阶段/进度/结果映射、警告/确认文案、客户端错误；设备返回的 `error=` 原文不翻译（只加本地化前缀）；`/log` 内容不翻译；文件名/CRC/SHA 不变。

预算：约 140 个键；预计 gzip +5,500～7,000 B（当前 13,773 B → 约 19,300～20,800 B，限 32,768 B）。task-91 实测；若页面 gzip > 26,000 B 或二进制余量门被破，按用户授权整块删除 I18N（保留中文单语），不裁其它功能。

## 11. 页面 v3 设计（单文件、无外部资源、照上游 failsafe 形态）

现有六标签不变：系统状态 / 固件更新 / 引导区 / 环境变量 / 串口台 / 恢复出厂。v3 增量：

### 11.1 系统状态
- 新增「系统信息」卡片：`GET /sysinfo` 表格（键 → 本地化标签），刷新按钮；显示版本/DRAM/CP15/SPI ID/时钟；失败显示错误文本；
- 新增「启动日志」卡片：`<pre id="logbox">` + 刷新 + 下载（`/log?download=1`）+ 溢出标记（`X-E2631-Log-Overflow`）；文案「截止进入救援模式时」；
- 新增「完整性自检」卡片：按钮「自检 mtd0 镜像区」，显示 CRC32/SHA-256 与「与 /status 记录一致/不一致」；
- 新增一行救援提示：蓝色 LED 慢闪 = 救援模式。

### 11.2 固件更新
保持 v2.1：文件选择、槽位 auto/0/1、校验、写入门控（devsha/sha_match/guard）、进度、断电重启文案；不改。

### 11.3 引导区
- 分区备份下拉扩展为 9 项：v2.1 五分区 + `slot0`/`slot1`/`rootfs`/`header`；显示物理偏移/长度；
- 整槽/窗口下载用浏览器原生下载（服务端 `Content-Length`），页面显示「正在下载 …（可能 28 MB，请等待）」；下载失败给错误；
- 新增「重启设备」卡片：按钮 `id=rebootgo` → `confirm()` 双确认 → `POST /reboot` + `X-E2631-Confirm: reboot`；accepted 后显示「设备正在重启，约 20–30 秒后回到系统」，禁用按钮、停止轮询，不自动刷新；
- 仍然不提供写回分区。

### 11.4 环境变量
保持 v2.1 只读总表 + 白名单编辑；新增「DHCP 配置」卡片（见 §9）：四个输入框、保存（逐键写）、恢复默认、生效说明与 `/status dhcp_*` 显示。

### 11.5 串口台
保持 v2.1（单命令 + stdout + 历史 + 截断标记）；不提供 stdin；不新增 /reboot 命令入口。

### 11.6 恢复出厂
保持 v2.1；不因 v3 改动。

### 11.7 全局交互/可访问性
- 无外部 URL/字体/脚本/样式；纯内联 CSS/JS；
- 语言开关、六标签键盘可达；`:focus-visible`；`prefers-reduced-motion` 下禁用过渡（硬件 LED 不受影响）；
- 屏幕 ≤760 px 单列；
- 所有写/重启动作 `confirm()`；确认文案含后果与断电风险；
- 页面不自动重试写操作；网络错误显示并允许手动重试；
- 页面 gzip 预算 32,768 B；生成/嵌入仍由 `tools/embed-failsafe.sh`（确定性，符号不变）。

## 12. 尺寸预算与回收方案

### 12.1 当前基线（artifact `uboot-e4v2-46109519805`）

| 项 | 值 |
|---|---:|
| u-boot.bin | 405,368 B |
| 载荷硬上限 | 653,312 B |
| 当前余量 | 247,944 B |
| 任务卡硬门余量 | 245,760 B（240 KB） |
| 硬门以上可增长空间 | 2,184 B |
| 页面 gzip | 13,773 B / 32,768 B |

### 12.2 回收包 P1（必须，task-90 的 defconfig 改动）

| 配置 | 关闭的对象（UBOOT-SIZES 实测） | 预计回收 |
|---|---|---:|
| `# CONFIG_CMD_FDT is not set` | `cmd/fdt.o` 8,166 text + 63 data | 8,229 B |
| `# CONFIG_CMD_TFTPBOOT is not set` | `net/tftp.o` 4,137 text + 14 data | 4,151 B |
| 合计 | | 12,380 B |

代价：`/console` 的 `fdt`、`tftp` 命令消失；救援页/正常启动不使用这两条命令（tftp 从未是 v1/v2 功能；页面用 HTTP 上传）。需在 `uboot-port/README.md` 记录命令面收窄。
P2（仅当实测超出）：`# CONFIG_CMD_MII is not set`（`cmd/mii.o` 5,696+28=5,724 B；同时确认 `CMD_MDIO` 是否随之消失）。

### 12.3 v3 增量估计

| 项 | 估计 |
|---|---:|
| `/sysinfo` | 650 B |
| `/log`（快照 + 端点） | 450 B |
| `/integrity` | 480 B |
| `/backup` 整槽/窗口（part 表 + 1 MiB 流） | 350 B |
| `/reboot` | 150 B |
| LED 保存/闪烁/恢复 | 250 B |
| DHCP env + dhcpd 分支 | 600 B |
| 其他（字符串/错误分支） | 200 B |
| 页面资产增长（I18N + 新卡片，按 gzip 增量） | 5,500～7,000 B |
| 合计 | 8,630～10,130 B |

### 12.4 门禁与裁决

- 二进制硬门：`653,312 − size(u-boot.bin) ≥ 245,760`；按 P1 回收 12,380 B 后，可增长预算 = 2,184 + 12,380 = 14,564 B；上表上限 10,130 B，预计通过（余量约 4,400 B）；
- 页面硬门：gzip ≤ 32,768 B；当前 13,773 + I18N 约 7,000 = 20,773 B，预计通过；
- 若二进制门破：先用 P2（+5,724 B）；仍破则按用户授权整块砍 I18N（C 代码不动）；页面门破同样先砍 I18N；
- 最终数字由 task-92 用新构建的 `UBOOT-SIZES.txt`、`u-boot.bin`、`E2631-FAILSAFE-ASSET.txt` 复核；本文估计值只作事前预算，不作为验收值。

## 13. patch 0040：产品前缀 16→17 B 对齐

现状：U-Boot `e2631_slotcore.c:122-123` 用 `memcmp(hdr + E2631_H_PRODUCT, E2631_PRODUCT_STRING, E2631_PRODUCT_LEN)`，`e2631_slotcore.h:63` 为 `16U`；Linux `e2631-fwslot.c:644` 用 `strncmp(..., PRODUCT, sizeof(PRODUCT)-1)` 比较 17 B。真实包的 H_PRODUCT 在 `hdr+0x6c` 是 `"ZXHN E2631 V1.0.0" + NUL`（32 B 字段），两边都接受；只有构造第 17 字节不同时不一致，且 U-Boot 是宽松一侧。

patch 0040（必须随 v3 构建窗口落地）：
1. `e2631_slotcore.h:63`：`#define E2631_PRODUCT_LEN 16U` → `17U`；
2. `uboot-port/tests/slotcore_test.c`：增加对拍向量——把合法包头 H_PRODUCT 的第 17 字节（`hdr[0x6c+16]`）改为 `'X'`，期望 `E2631_PKG_WRONG_PRODUCT`；保留真实包向量（第 17 字节为 NUL）必须仍通过；
3. 不改其它字段/CRC/槽逻辑；pkg 校验顺序不变；
4. 编号：task-90 实施时若 0040 已被 v3 功能占用，产品前缀补丁用下一个空闲编号，但必须同一批构建，Lead 批准编号调整；
5. 契约 §5.1 的产品比较长度从 16 B 改为 17 B（本文件生效）。

## 14. 写所有者与不变式（不变）

| 对象 | 所有者 | v3 动作 |
|---|---|---|
| bootloader mtd0 镜像区 | `e2631flash` | 无新增（仍 `/flash`） |
| 启动槽 | `e2631-fwslot` | 无新增（仍 `/firmware`）；`/backup` 只读 |
| overlay（rootfs_data） | `e2631factory` | 无新增（仍 `/factory`） |
| env 块 | `e2631env` | 无新增写路径；`/env` 支持 `e2631_dhcp_*` 语义校验 |
| 只读 | 无 | `/sysinfo`、`/log`、`/integrity`、`/backup`、`/status`、`/slots`、`/console` |

不变式：`/backup`/`/integrity`/`/sysinfo`/`/log` 永不写 flash 或 env；`/reboot` 不写 flash；新增端点不引入第三个槽写入实现。

## 15. 安全说明（只写文档，不设口令门）

- 救援页无鉴权；新的 `/reboot` 允许 LAN 内任意主机让设备重启（DoS 级，但救援模式只在按键触发后运行，正常启动不监听网络）；
- `/backup` 可下载完整 slot0/slot1（包含厂商/自编固件内容，不含 env 块；`bootloader` part 仍只含 U-Boot 区）；
- `/sysinfo` 暴露 MAC 以外的硬件信息（不输出 MAC，除非后续明确要求）；
- `/console` 仍可执行任意单条命令（含 reset、mtd 擦写）；页面仅做二次确认；
- 若将来收紧：优先加口令或命令白名单；v3 不做。

## 16. mock 级正/负验收用例

实现：`tools/mock-failsafe.mjs` 已扩展 v3 端点（本地 node，无设备）。用例与实测（2026-11-28，`PORT=18095`，`E2631_MOCK_BOOTLOADER` 指向净零镜像 `b1ea9a48...`）：

| 端点 | 正例 | 负例 | 实测 |
|---|---|---|---|
| GET /sysinfo | 200，含 result/version/board/dram/spi_id/CP15/时钟键 | POST → 405 | 200，34 行 |
| GET /log | 200，`X-E2631-Log-Bytes` | POST → 405 | 200，304 B |
| GET /log?download=1 | 200 + Content-Disposition | 方法不符 405 | 通过 |
| POST /integrity | 200，crc32=0x0721e716、sha256=b1ea9a48…、match=absent/ok/mismatch | GET 405；expect 非 64 hex → 400 | 全部通过 |
| GET /backup?part=slot0\|slot1\|rootfs\|header | 200，长度 29,360,128 / 29,360,128 / 17,825,792 / 131,072，头齐全 | part=slot2 → 400；POST → 405；并发 → 409 | 通过 |
| POST /reboot | 确认头正确 → 200 result=accepted reboot=1；/status reboot_pending=1 | 缺确认 400；任务中 409 | 通过 |
| POST /env DHCP 键 | 合法值 → 200 keys=1，/status 生效 | pool_size=201、ip=999.1.1.1 → 400 bad value | 通过 |
| 回归 | v2.1 `--v21` mock 自测 PASS=138 FAIL=0 NOTE=1；v1 默认 PASS=19 FAIL=0 | — | 通过 |

复现：`PORT=18095 E2631_MOCK_BOOTLOADER=<净零镜像 b1ea9a48…> node tools/mock-failsafe.mjs`；本文件写就时 mock 的 sha256 为 `97f4cebd22879a0d26cc9911973d7ccb5d9776523a3aa002bfaddb5c620879fd`（改动 mock 后需更新）。

mock 限制：数据为合成/零填充；`/reboot` 不真的重启；整槽下载内容非真实槽数据；`/integrity` 的 bootloader 缓冲由 `E2631_MOCK_BOOTLOADER` 决定。

## 17. 移交

- **task-90（base-builder，U-Boot C）**：patch 0040（前缀 17 B）+ v3 补丁（按 0041 起）：defconfig P1 回收、`/sysinfo`、`/log` 快照、`/integrity`、`/backup` 四 part、`/reboot`、LED、DHCP env + `mtk_dhcpd` 分支；不碰 `/flash`/`/firmware`/`/factory`/`/env` 既有语义；
- **task-91（页面）**：按 §11 实现，I18N 条件项，更新 `uboot-port/failsafe/README.md`、mock 文案；embed 后实测 gzip；
- **task-92（门禁/构建）**：二进制余量门（240 KB）与页面门（32,768 B）写入 workflow/checker；`UBOOT-SIZES.txt`、`SHA256SUMS`、`UBOOT-INFO` 文案；
- **task-93（真机验收）**：零写全端点 + `/reboot` 一次（用户批准）+ 整槽下载哈希 + `/log`/`/sysinfo`/`/integrity` + DHCP 配置下次救援生效 + LED 观察；不得写 mtd0/slot/env（除显式批准的 env 配置写入）；
- 本文与 `docs/E4-多功能U-Boot设计-2026-11-27.md` §16 同步。

## 18. 待决/风险

1. 28 MB 流式下载的 TCP 窗口/ACK 行为与整槽读时间需真机验证；若过慢，可改用 512 KiB 块；
2. `/log` 只到救援入口，用户若想看之后日志，需要另开实时日志通道（v3 不做）；
3. LED 保存/恢复读 bank 寄存器在 U-Boot 下已由 vendor 读 strap 证明安全，但蓝灯极性/接线需真机确认（active-low 已知）；
4. DHCP 配错会让下次救援页不可达；页面必须显著提示恢复默认需要再次进入救援（或串口 setenv）；
5. I18N 为条件项，最终以 gzip/余量实测为准；
6. 回收 P1 会移除 `fdt`/`tftp` 命令，需在文档与 `/console` 帮助中说明；
7. `/reboot` 依赖 patch 0029 真机已验证的 TOPCRM 复位；真机验收只做一次，且执行前确认无写任务；
8. patch 编号 0040 可能被 v3 功能先占用；产品前缀补丁必须同批构建，编号由 Lead 最终确认。

