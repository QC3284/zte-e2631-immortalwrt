# E4-研1：bl-mt798x-dhcpd 移植评估与空间预算（task-70）

日期：2026-11-27。性质：只读调研（读上游源码、本地 U-Boot 源码、kit 既有证据；未改
`uboot-port/patches`、未动树 fork、未碰真机、未派 CI）。所有尺寸均为「估算」，方法见 §4.1，
不确定度 ±50%；凡是实测数字都标了来源。

## 0. 结论摘要

1. **上游坐标要纠正**：用户/Lead 口述的 `981213/bl-mt798x-dhcpd` 不存在（`git ls-remote`
   返回 Repository not found；`981213` 名下没有该仓库）。实际维护的仓库是
   **https://github.com/Yuzhii0718/bl-mt798x-dhcpd**（master，HEAD
   `e4cf4dc72d451dc7a86c9508390ad5a2e50743c4`，2026-10-08，GPL-2.0），其底层是
   hanwckf/bl-mt798x，U-Boot 树为 `uboot-mtk-20250711/`（U-Boot 2025.07）。
   研究以 Yuzhii 仓为准。
2. **可复用面比想象小、但核心够用**：TCP/HTTP/DHCP 服务端（`net/mtk_tcp.c`、
   `net/mtk_httpd.c`、`net/mtk_dhcpd.c`，MediaTek 2022 + Yuzhii 2026，GPL-2.0）与
   gzip 资源嵌入机制可移植；**failsafe 的全部高级模块（刷机、备份、env、主题、控制台、
   UBI）深度绑定 MTK 板级胶水（`board/mediatek/common/mmc_helper.h`、mtkupgrade、
   NMBM/GPT/UBI）**，只能重写，不能整段搬运。
3. **E4 v1（DHCP + 最小 HTTP 上传 + e2631flash 五步刷写）估算 16–34 KB（中位 ~25 KB）**，
   在现有 159,104 B 基线余量内即可装下，无需捐献子系统；C（菜单 + TFTP + Web）约
   22–44 KB；B（完整 Web UI）约 85–137 KB，只有砍掉 i18n 才接近基线余量，推荐用
   「EFI/FAT/MMC/bootstd ≈130 KB linked」的捐献预算兜底（Lead m04017）。
4. **决定性门槛是 F2（TX 不通）**：救援模式的价值全部建立在设备能回包上；F2 未修复前
   E4 v1 不可验收。**最新进展**：F2-a 的代码修复已经落地（kit `8e16330`，patch 0023
   「诚实 TX 错误 + 内核 BMU pending-retry」、patch 0024 几何断言，24 patch 构建绿，
   见 `evidence/uboot-e2-fix-20261127.md`），但**零写入真机复测协议（该文档 §5）尚未执行**，
   所以按设备级标准 F2 仍算红——E4 开工前必须先跑完那份复测。F1（bootm 静默返回）只影响
   「刷完自动起内核」这一步的极端分支，产品级 flash boot 目前是绿的，但验收时必须把
   `e2631boot` 失败路径显式报错。
5. **推荐**：v1 只做 A（串口命令 `e2631rescue` 进入；DHCP 服务器 + 单页 HTTP + 一次
   mtd0 上传 + e2631flash 五步 + 重启）；S 项（TFTP 第二通道、verify-only、显示
   sha256/槽表）按剩余预算逐项加；B 不进入 v1。E3（菜单）与 E4 代码可并行，最后
   只做一行菜单项集成。

## 1. 上游事实（2026-11-27 实测）

### 1.1 仓库与版本

| 项 | 值 | 证据 |
|---|---|---|
| 主仓 | `https://github.com/Yuzhii0718/bl-mt798x-dhcpd` | gh api 实测 |
| 默认分支 | `master` | gh api |
| HEAD | `e4cf4dc72d451dc7a86c9508390ad5a2e50743c4`（2026-10-08，"net: mtk_httpd: fix crash on POST without body"） | `git clone --depth 1` |
| 最近 release | `2026.10.30-1213-all`（此前 2026.08.31/07.15/06.05/05.01 均为 `-all`） | gh api releases |
| 许可 | GPL-2.0（仓库 LICENSE 18,092 B = GPL-2.0 全文） | `LICENSE` |
| 基线 | hanwckf/bl-mt798x（clone HEAD `36916669d0874306638196c5327a20c2ef215bed`，2026-04-13） | 本地 /tmp 对照 clone |
| U-Boot | `uboot-mtk-20250711/`，VERSION 2025 / PATCHLEVEL 07 | `Makefile` |
| 架构 | arm64（MT798x）+ ATF/FIP/GPT 链；不涉及本机 arm32 | 目录 `atf-*/mt798x_*/generate_gpt.sh` |
| 用户口述的 981213 仓 | **不存在**（Repository not found） | `git ls-remote` 实测 |

补充：上游 release 资产**只构建 default 变体**（72 块板子的 FIP/BL2 + 构建日志 tar.gz
561,758 B），`configs-openwrt/` 40 个 defconfig 不带 Web UI；README 明说 openwrt 变体
当前无 failsafe web UI。即 Web UI 只存在于 default 变体，不能假设 openwrt 变体可参考。

### 1.2 功能组成（README + 代码实测）

- **MTK_DHCPD**：U-Boot 内置 DHCP 服务器，救砖时 PC 免配置拿 IP。
  `CONFIG_MTK_DHCPD`、`CONFIG_MTK_DHCPD_USE_CONFIG_IP`、
  `CONFIG_MTK_DHCPD_POOL_START_HOST`（默认 100）、`CONFIG_MTK_DHCPD_POOL_SIZE`（默认 101）
  （`net/Kconfig:256/264/273/280`）。
- **WEBUI_FAILSAFE**：failsafe Web UI（主题 bootstrap/gl/mtk），功能：系统信息、工厂(RF)
  更新、备份下载、flash 编辑器、web 终端、env 管理器、主题管理器、i18n、重启、UBI 卷管理；
  开关项 `WEBUI_FAILSAFE_*`（FACTORY/BACKUP/ENV/CONSOLE/FLASH/UBI/SIMG/I18N/ADVANCED）
  （`failsafe/Kconfig` 5,006 B）。
- **MTK_TCP / MTK_HTTPD / MTK_DNSD / MTK_TELNETD / MTK_NET_ABORT**：自带的用户态 TCP/IP
  与 HTTP/DNS/Telnet 服务，以及 UDP 37541 的 uBootEnter/BreedEnter 兼容触发
  （`net/Kconfig:223-299`）。
- **引导集成**：bootmenu 项 `"Start Web failsafe"` → `cmd = "httpd"`
  （`board/mediatek/common/bootmenu_mtd.c:165-170`）；4 s 长按按键 → `httpd`
  （`cmd/glbtn.c:432`）；`MTK_WEB_FAILSAFE_AFTER_BOOT_FAILURE` 时
  `cmd_mtkboardboot.c:24` / `cmd_mtkchainload.c:27` 失败后自动进 web。
- 构建：`build.sh` 选择 UI 变体/主题/SIMG/UBI/NAND_RAW；资源由 npm 在构建期
  minify+gzip 后嵌入（`failsafe/embedded/*/embed.S`）。

### 1.3 自有文件与尺寸（`uboot-mtk-20250711/`，字节）

| 文件 | 字节 | 说明 |
|---|---:|---|
| `net/mtk_tcp.c` | 43,007 | 用户态 TCP（MediaTek 2022，GPL-2.0） |
| `net/mtk_httpd.c` | 21,581 | HTTP 服务器与 multipart 上传（同上） |
| `net/mtk_dhcpd.c` | 18,225 | DHCP 服务器（Yuzhii 2026） |
| `net/mtk_dnsd.c` | 8,273 | DNS 服务器（Yuzhii 2026） |
| `net/mtk_telnetd.c` | 43,288 | Telnet 服务（Yuzhii 2026） |
| `net/net_abort.c` | 9,632 | UDP 37541 触发（Yuzhii 2026） |
| `net/mtk_tcp.h` / `mtk_httpd.h` / `mtk_dhcpd.h` / `mtk_dnsd.h` / `mtk_telnetd.h` | 2,804 / 2,770 / 520 / 459 / 1,637 | 头文件 |
| `failsafe/failsafe_core.c` | 13,242 | `httpd` 命令与服务编排 |
| `failsafe/modules/` 合计 | 152,097 | backup 16,442 / console 14,092 / env 9,745 / flash 21,852 / helpers 13,309 / misc 19,383 / nand_raw 4,508 / theme 9,205 / ubi 27,797 / upgrade 15,764 |
| `failsafe/embedded/fsdata-bootstrap/` | 426,932 | 源码（main.js 60,629、i18n.js 81,959、style.css 63,488、flash_js.js 41,727 等） |
| `failsafe/embedded/fsdata-gl/` / `fsdata-mtk/` | 58,250 / 58,250 | 另外两套主题源码 |

资源嵌入成本 = **gzip 后大小**（上游 CI 构建日志实测，72 板日志给出的 26 个资产合计
**70,858 B**）：i18n.js 18,468；style.css 8,195；main.js 9,336；theme.js 1,387；
其余核心/页面资产 33,472；逐项如 index 1,201、flash 1,567、settings 2,431、
flash_js 6,072、console_js 3,659、backup_js 2,186、env_js 774、settings_js 1,693 等。
服务端以 `Content-Encoding: gzip` 直出（`net/mtk_httpd.c:309`），**U-Boot 不需要
inflate 解压器**——这是上游最重要的一条省空间设计，可原样继承。

### 1.4 上游镜像尺寸（参考，不是可比数字）

构建日志实测：U-Boot 二进制 692,944–971,280 B（arm64 MT7981 常见 921,448；bt_r320
728,016；GL-MT3000 921,256；E87N 971,192）；FIP 里 BL33 = 0xE0F68 = 921,448 B。
**不能用 921 KB 直接对标我们的 494 KB**：他们的镜像含 DSA 交换、NMBM、UBI/GPT、
ATF 交接、MTK 板级胶水等我们完全没有的子系统；Web/DHCP 栈只是差额中的一小块。

### 1.5 与 hanwckf 基线的差异（`uboot-mtk-20250711` 同路径 diff）

- 文件数：基线 36,590 → fork 37,165（新增 592、删除 17、修改 161）。
- `net/`：新增 4（dhcpd/dnsd/telnetd/net_abort），修改 8（Kconfig、Makefile、arp.c/h、
  mtk_httpd.c、mtk_tcp.c/h、net.c）——说明 TCP 栈依赖对基线 `net.c`/`arp.c` 的修改。
- `failsafe/`：新增 91、修改 3（Kconfig/Makefile/fs.c）、删除 15（旧 failsafe.c/fsdata）。
- `board/mediatek/common/`：新增 7、修改 40（bootmenu_*、mtd_helper 43,701、
  mmc_helper 33,583、failsafe.c 3,982 等）——**板级胶水是最大修改面**。
- 另有大块**与 Web UI 无关**的 MT7987/7988/MT7621 支持（arch +122 文件、drivers +34、
  defenvs +42、configs +107），统计时必须剔除，不能算进 Web 栈成本。

### 1.6 许可与归属

- `net/mtk_tcp.c`、`net/mtk_httpd.c`：`SPDX-License-Identifier: GPL-2.0`，
  `Copyright (C) 2022 MediaTek Inc.` / Weijie Gao（hanwckf 基线已有，Yuzhii 修改）。
- `failsafe/modules/upgrade.c`、`board/mediatek/common/failsafe.c`：同上 MediaTek 2022。
- `net/mtk_dhcpd.c`、`net/mtk_dnsd.c`、`net/net_abort.c`、`failsafe/failsafe_core.c`、
  `failsafe/modules/*`：Yuzhii0718 2026，`SPDX-License-Identifier: GPL-2.0`，文件头注明
  "This file is part of the project bl-mt798x-dhcpd"。
- 结论：GPL-2.0 与我们的 uboot-port（GPL-2.0+）兼容，搬运/改写必须保留原版权
  声明与 SPDX；新增文件沿用我们的 `// SPDX-License-Identifier: GPL-2.0+` 头。

## 2. 复用判定（逐子系统）

### 2.1 可直接复用（verbatim 或极小适配）

| 子系统 | 判定 | 依据 |
|---|---|---|
| gzip 资源嵌入机制（`embed.S` + `fs.c` 的 linker-list `fs_desc`） | **可搬** | 只用 `linker_lists.h`/`string.h`，与平台无关；我们已开 linker list |
| 资源以 gzip 直出、U-Boot 不带解压器 | **可搬** | `mtk_httpd.c:309` |
| `include/cyclic.h`、`u-boot/schedule.h` 的定时调度 | **可搬** | 已对照：两版 `cyclic_register()` 原型一致，`schedule.h` 在我们 2027.01-rc2 树里存在 |
| DHCP 服务器协议逻辑（`mtk_dhcpd.c`） | **可改写搬运** | 只依赖 legacy net API，不依赖 DSA/MTK 硬件；池地址是 Kconfig 常量 |
| HTTP multipart 上传/下载框架（`mtk_httpd.c`） | **可搬运** | 上传缓冲通过弱函数 `httpd_get_upload_buffer_ptr()` 交给板级（`mtk_httpd.c:104,528`），正是我们要接 e2631flash 的接口 |
| 页面直出（不开解压、不依赖 FAT） | **可搬** | 页面由 C 数组（gzip 资源）直接服务，不读文件系统 |

### 2.2 需要适配（我们 2027.01-rc2 的 net API 漂移）

上游 2025.07 的 MTK 栈依赖一批 MediaTek/legacy 辅助函数；在 `include/net.h`、
`include/net-common.h`、`net/` 里查我们 2027.01-rc2 树：

| 符号 | 我们的树 |
|---|---|
| `net_loop`、`eth_rx`、`eth_init`、`eth_halt`、`net_set_udp_header` | **存在**（`include/net-common.h`） |
| `net_set_udp_handler`、`net_clear_handlers`、`net_send_udp_packet`、`net_tx_packet`、`net_set_ip_header`、`net_null_ethaddr`、`eth_needs_reinit`、`net_ret` | **未找到**（上游/MTK 私有扩展，或 2027 已删除） |

→ 移植 MTK 栈必须做一层 **compat shim**（或回移这些 helper），这是源文件层面看不出来、
但会直接决定工期的风险。好在 `CONFIG_NET_LEGACY=y` 仍打开，`net_loop` 主循环接口还在；
shim 主要是「注册 UDP 处理器」和「发送 UDP/以太帧」几处，估算 +1–3 KB 代码与 2–4 天调试。

### 2.3 需要重写（不能搬）

| 子系统 | 原因 | 我们的替代 |
|---|---|---|
| `failsafe_core.c` 的 `httpd` 服务编排 | 依次起 MTK DHCP/DNS/Telnet + 页面注册，但依赖 MTK 板级初始化顺序 | 写我们自己的 `e2631rescue`（约 300–500 行），只起 eth + dhcpd + httpd |
| `failsafe/modules/upgrade.c` | 含 `board/mediatek/common/mmc_helper.h`、mtkupgrade、mtdparts 校验 | 我们的 `e2631_flash_upload()`：校验 mtd0 镜像 → 调 `e2631flash` 命令/core → 回显 CRC |
| `failsafe/modules/flash.c` | 584/720/838/908 行调 `mmc_read/write/erase_generic`；分区/GPT 语义 | v1 不做 flash 编辑器；只保留「上传整块 mtd0 镜像」一个动作 |
| `failsafe/modules/backup.c` | 含 MMC/part/NAND raw，下载整分区 | v1 不做；最多保留 env/槽头只读下载（可选 S 项） |
| `failsafe/modules/env.c` | 依赖 `env_internal.h`/`env_save`，而我们的 `CONFIG_CMD_SAVEENV` 关闭，env 写回是自有 `e2631env save` 设计 | v1 不做 env 编辑；若做，重写为调 `e2631env` |
| `failsafe/modules/ubi.c` / `nand_raw.c` / GPT / SIMG / NMBM | 我们没有 UBI/GPT/SIMG/NMBM | 全砍 |
| `board/mediatek/common/` 全部 | MTK 板级初始化、mtkboardboot、mtkupgrade、mmc_helper | 我们的 `board/zte/zxhn-e2631/` 已有 e2631boot/e2631flash/e2631env |
| bootmenu 集成 | 上游是在 MTK bootmenu 里加一项 | 若做 E3，用主线 `cmd/bootmenu.c` + 一项 `httpd`；E4 v1 用串口命令，不改菜单 |
| build.sh / ATF / FIP / GPT 工具 | 平台完全不同 | 用我们既有 `uboot-build.yml` 与 kit 打包链 |

**量化「MMC 依赖」改写成本**：高级模块 152,097 B 源码中，经 grep 确认与
`board/mediatek/common/mmc_helper.h` 直接相关的调用集中在 `upgrade.c`、`flash.c`、
`backup.c`、`helpers.c`、`misc.c`；剔除这些板级分支后，可保留/改写的是
「HTTP 表单解析 + 页面渲染 + 资源查找 + 少量信息采集」，估计可复用源码 ~55–65%（
~85–98 KB），其余 35–45% 必须重写/删除。对应到编译产物：高级模块 14–28 KB（而非
原样 25–45 KB）。

### 2.4 必须丢弃

i18n（gz 18,468 B）、web 终端（telnetd 43,288 B 源码 ≈ 6.5–13 KB 编译）、flash 编辑器、
env 编辑器、UBI 卷管理、备份下载、工厂(RF)更新、主题管理器（theme.js 等）、HTTPS、
FAT/FS 浏览、EFI/USB/MMC/PXE/bootstd 相关一切。

### 2.5 关键核查：failsafe Web UI 是否依赖将被砍掉的子系统（Lead m04017 问题）

实测 grep 全部 `failsafe/*.c`、`failsafe/modules/*.c`、`net/mtk_*.c`、`net/net_abort.c`：

- **没有** `efi_*` 调用、**没有** U-Boot `fs_read/fs_write/fat_*` 调用；
  `failsafe/fs.c` 里的 `fs_find_file()` 只是**嵌入式资源表**查找（linker-list
  `fs_desc`），与 FAT/文件系统无关（`failsafe/fs.c:12-15`）。
- MMC 只出现在 `board/mediatek/common/mmc_helper.h` 的 include 与
  `mmc_read/write/erase_generic`、`mmc_get_blk_desc` 调用里，集中在高级模块
  （`flash.c:584,720,838,908`；`backup.c:214,556,659`；`helpers.c`、`misc.c`、
  `upgrade.c` 的板级信息采集）。
- 结论：**核心栈（TCP/HTTP/DHCP/DNS/资源嵌入）不依赖 EFI/FAT/MMC/bootstd**；高级模块
  的 MMC/part/UBI 代码是 MTK 板级胶水，必须重写而不是直搬。因此“砍掉 EFI/FAT/MMC/
  bootstd 后直接搬 Web UI”不成立——要么只搬核心栈（A 方案），要么连带重写高级模块
  （B 方案，成本已计入 §4.2）。

## 3. 架构差异表

| 维度 | MT798x 上游 | E2631 / 我们的栈 | 判定 | 理由 |
|---|---|---|---|---|
| 交换/DSA | DSA switch（mt753x），多口 | 单口静态 DM_ETH，ZX279128S switch port 2 + PP bridge，无 DSA | **配置/适配** | DHCP/HTTP 只认一个 netdev；E2 驱动已把 lan1 注册成单口，不搬 DSA |
| 以太网驱动 | `mtk_eth` + NMBM 类 glue | `drivers/net/zx279128s_eth.c`（我们自己的 E2 驱动） | **不搬（已有）** | E4 不新增网口驱动；F2 修好前 E4 不可用 |
| 内存布局 | BL31 0x43000000；上传缓冲 `ram_base + 0x6000000` = 0x46000000 | TEXT_BASE 0x47F00000（非 PIE）；SYS_LOAD_ADDR 0x42000000；e2631flash bounce 0x44000000；net DMA arena 0x45000000–0x45FFFFFF；relocaddr≈0x4FF94000，LMB 保留 [0x4EB70000–0x4EB72FFF] 与 [0x4EB73EB0–0x4FFFF000] | **必须适配** | 上传缓冲选 0x46000000（1 MiB，避开 arena 与 reloc；需 mem_map/LMB 复核）；地址写死，不能照抄 PIE 相对偏移 |
| PIE/重定位 | 上游为 PIE/固定布局混合 | 我们固定 0x47F00000、非 PIE | **必须适配** | 资源/缓冲必须是绝对地址常量；链接脚本文本地址不变 |
| 启动链 | ATF/FIP/GPT、mtkboardboot、mtkupgrade、NMBM | secondboot → 我们的 U-Boot → e2631boot（槽选择 + bootm）；e2631flash/e2631env 自有 | **必须重写** | 只保留「起内核」和「写 mtd0」两条我们已验证的路径 |
| Flash 模型 | mtdparts + UBI/GPT/NMBM | mtd0 raw + 双槽 + slot 头；mtd0 镜像区 0x20000..0xC0000（0xA0000 B） | **必须重写** | 校验/写入用 e2631flash；不导入 mtdparts/UBI |
| env | 可写 env（`env_save`） | `CONFIG_CMD_SAVEENV` 关闭；env 写回是 `e2631env save` 设计（task-59） | **必须重写（若做 env 编辑）** | v1 不做 env 编辑 |
| U-Boot 版本 | 2025.07 | 2027.01-rc2（c1958b5f） | **必须适配** | net helper API 漂移（§2.2）；`cyclic`/`schedule` 兼容 |
| Cache/DMA | 上游 caches 开，需 cache maintenance | 我们 `SYS_ICACHE_OFF/DCACHE_OFF/L2CACHE_OFF`（b45 已核） | **适配（简化）** | 无 D-cache，上传/发送缓冲无需 flush；仍需保证缓冲在 DRAM 且 4 字节对齐 |
| 许可 | GPL-2.0 | GPL-2.0+ | **兼容** | 保留版权/SPDX 即可 |

## 4. 尺寸预算

### 4.1 方法

用本机 24-patch 构建的 `u-boot.map` 实测「编译字节 / 源码字节」密度校准：中位
**0.170**，范围 0.053–0.423；取 **0.15–0.30** 作为上游源码的估算区间（同一 ARM32、
GCC、`-Os`；上游 arm64 通常略密）。代表性样本：`net/net.o` 0.113（40,553→4,588）、
`net/bootp.o` 0.128（29,529→3,783）、`net/tftp.o` 0.163（25,719→4,195）、
`net/arp.o` 0.205、`net/ping.o` 0.223、`eth-uclass.o` 0.219；
我们板级更密：`e2631flash.o` 0.362（15,083→5,458）、`e2631env.o` 0.350、
`e2631boot.o` 0.283。**所有数字 ±50%**；真实值以 CI 的 `UBOOT-SIZES.txt` 为准。

### 4.2 逐功能估算（编译后字节，区间 [0.15,0.30]×源码，中位 ≈0.20）

| 功能 | 上游源码 B | 估算编译 B | 备注 |
|---|---:|---:|---|
| TCP 栈 `net/mtk_tcp.c` | 43,007 | 6,451–12,902（~8,600） | 最大单件；若只做「单连接 HTTP」可裁 20–30% |
| HTTP 服务 `net/mtk_httpd.c` | 21,581 | 3,237–6,474（~4,300） | 含 multipart、弱上传钩子 |
| DHCP 服务 `net/mtk_dhcpd.c` | 18,225 | 2,734–5,468（~3,600） | 独立于硬件 |
| DNS 服务 `net/mtk_dnsd.c` | 8,273 | 1,241–2,482（~1,650） | 可选 |
| compat shim（§2.2） | 新增 ~5–8 KB | 1,000–2,400 | 2027 API 适配 |
| `e2631rescue` 板级编排（新增） | 新增 ~8–12 KB | 1,600–3,600 | 起 eth、静态 IP、服务循环、串口回显 |
| 上传→e2631flash 桥（新增） | 新增 ~6–9 KB | 1,200–2,700 | 校验 magic/长度、调用 e2631flash、回显 CRC |
| 最小页面资源（gzip） | 手写 ~4–6 KB | **2–4 KB gz** | 单页 + 进度 JS（可含浏览器端 SHA-256） |
| net_abort（可选） | 9,632 | 1,445–2,890（~1,900） | UDP 37541 触发 |
| boot menu（E3） | `cmd/bootmenu.c` 16,404 | 2,461–4,921（~3,300） | 加 lib/menu 与胶水 ≈4–7 KB |
| failsafe core（B 用） | 13,242 | 1,986–3,973 | 页面注册/服务编排，B 才需要 |
| 高级模块（B 用，重写后） | 152,097→可复用 ~60% | 14,000–28,000 | 已剔除 MMC/UBI/GPT/nand_raw |
| 完整 bootstrap 资源（B 用） | gz 实测 | **70,858**（无 i18n 则 52,390；core+main+style 51,003） | 固定值，无估算 |
| 完整 gl/mtk 主题（B 用） | gz 实测 | 各一套 51–71 KB | 不必两套 |

### 4.3 我们的现状与可捐献子系统

实测 24-patch 构建（`evidence/t71-uboot-payload-budget-20261127.md`）：

- 载荷窗口 mtd0 `0x20800..0xBFFFF`；硬上限 **653,312 B**（0x9F800）；
  CI 门禁 **645,120 B**（8,192 B 安全余量）。
- 当前 `u-boot.bin`：494,880 B（24 patch，run 33）；基线余量 **158,432 B**
  （24.25%），距 CI 门禁 150,240 B。任务卡引用的 494,208 B / 159,104 B 是 22-patch
  口径，两者差 672 B，下文按 **159,104 B** 作为「基线预算」表述并注明。
- Lead m04017 给出的可捐献对象（对象 `.text`，合计 150,220 B）：
  EFI loader 100,460；MMC 14,321；FAT 16,835；PXE/bootstd/bootflow 18,604。
  按「对象→链接镜像 ≈0.87×」折算约 **130,700 B**。于是总预算 ≈
  **159,104 + 130,700 ≈ 289,800 B（≈283 KiB）**。

注意：捐掉 EFI/FAT/MMC/PXE 只是把我们**不用**的代码移出镜像；A/C 方案的新代码本身
不依赖它们（MUST 6），所以不捐也能做 A/C，捐了则余量翻倍、且必须成对删除相关命令
（`bootefi`、`fat*`、`mmc`、`bootflow`/`pxe`），并在 CI checker 里加「不得回引」守卫。

### 4.4 A/B/C 预算表（假定预算、余量、风险）

| 方案 | 内容 | 新代码估算（含资源） | 假定预算 | 余量 | 超出风险 |
|---|---|---:|---:|---:|---|
| **A 最小救援**（v1 推荐） | DHCP 服务 + TCP/HTTP 核心 + 单页上传 + e2631flash 五步 + 重启；串口命令进入 | **16–34 KB（中位 25）** | 基线 159,104 B（**不捐**）；若捐则 289,800 B | 125–143 KB（不捐） | 低；TCP 栈若被 F2 调试拖长可裁连接数/日志 |
| **C 菜单+TFTP+Web** | A + E3 bootmenu 一项 + net_abort 触发 + 可选 DNS；TFTP 复用现有 `tftp` 命令（只加服务端页面入口） | **22–44 KB（中位 33）** | 基线 159,104 B（可不捐）；建议捐 EFI/MMC 求稳 | 115–137 KB | 低–中；菜单与网络无耦合 |
| **B 完整 Web UI** | A + failsafe 框架 + env/备份/主题/控制台模块（重写版）+ 完整 bootstrap 资源（无 i18n） | **85–137 KB（中位 110）** | 捐献预算 289,800 B | ~180 KB（捐）；若只用基线余量则 22–74 KB | 高：模块改写量大、面积随主题增长；必须捐且裁 i18n |

### 4.5 必砍清单（与尺寸）

i18n gz 18,468；web 终端（telnetd 源码 43,288 → 估 6.5–13 KB）；UBI 模块 27,797 B 源码；
nand_raw 4,508 B 源码；flash 编辑器（21,852 源码，只保留 mtd0 上传 ≈1/4）；backup 下载
（16,442 源码）；GPT/SIMG/NMBM/主题管理器；EFI（在现状里 99,311 链接字节，可捐）、
FAT 16,835、MMC 14,321、bootstd/bootflow/PXE 18,604（对象口径）。
把「可捐」+「不搬」分开记：前者是腾预算，后者是范围裁剪。

### 4.6 MUST 6 检查

- 新代码只允许 include：`<command.h>`、`<env.h>`、`<net.h>`、`<net-common.h>`、
  `<linux/mtd/mtd.h>`、`<mtd.h>`、`<log.h>`、`<linux/...>`、`<u-boot/crc.h>` 等；
- **禁止** `<efi.h>`/`<efi_loader.h>`、`<fs.h>`/`<fat.h>`、`<mmc.h>`、
  `<bootstd.h>`/`<bootflow.h>`、`<ubi_uboot.h>`；
- CI 建议加静态守卫：`board/zte/zxhn-e2631/e4/` 与 `net/mtk_*.c` 的 include/调用里出现
  上述符号即失败；并在 `UBOOT-INFO.txt` 记录本选项的假定预算与实测增量。

## 5. 刷写路径（card Q4）

### 5.1 两条候选

1. **RAM 缓冲 → e2631flash（推荐）**：网页把 **恰好 655,360 B（0xA0000）** 的 mtd0 镜像
   上传进 RAM（弱钩子 `httpd_get_upload_buffer_ptr()` 返回 **0x46000000**，1 MiB 区，
   避开 0x45000000 起的 net DMA arena 与 0x4EB70000 起的 U-Boot 保留区），校验后
   `e2631flash 0x46000000 0x20000 0xA0000` 一次调用完成五步；
   `len ≤ 1 MiB` 与 `off` 对齐约束都满足（`e2631flash.c:5-8,171-217`）。
2. **userdata 暂存 → e2631flash（备选）**：先把镜像写进 userdata（0x3F00000，47 MiB，
   目前空），readback 校验后再以 `<src>=闪存偏移` 方式调用 e2631flash（源会先经 1 MiB
   bounce 0x44000000 暂存）。优点：上传与擦写解耦，掉电只损失暂存；缺点：多一次
   写 userdata、多一步清理，且仍要面对同一次擦写窗口。

**推荐 1**（本机实际只用 640 KiB，RAM 路径最短、无额外 flash 磨损）；**2 作为可选 S 项**。

### 5.2 五步与校验（MUST 3/4）

- 写入前校验（全部在 RAM 内完成，失败不动 flash）：
  1) 文件大小 == 0xA0000（655,360 B），否则拒绝；
  2) 镜像头 magic `0x73383231`（"128s"）位于镜像 +0x10、载荷长度字段 +0x14 在
     `0x800..0x9F800` 且 `0x800+len ≤ 0xA0000`；
  3) 目标区间固定 `0x20000..0xC0000`，代码里写死，**不接受网页传任何 offset**；
  4) 头块 0x800 B 的 CRC32/内容自检；可选：浏览器端算 SHA-256 显示；
  5) 拒绝 `>0xA0000`、空文件、非 0xA0000。
- 写入：`e2631flash` 五步 = **erase → all-FF verify → write → read back → compare**
  （`e2631flash.c:5-8` 注释即五步；失败逐块打印并返回非 0）。
- 写入范围：只 `0x20000..0xC0000`；**secondboot 0x0..0x20000、env 0xC0000..0xE0000、
  保留区 0xE0000..0xFFFFF 一律不碰**（e2631flash 自身也会拒绝这几段）。
- 错误上报：DHCP 超时、HTTP 错误、镜像拒绝、erase/blank/write/readback/compare 失败，
  都必须同时出现在浏览器页面与串口控制台（MUST 5），不允许静默返回。

### 5.3 掉电窗口与回滚

- 擦写窗口 = 0xA0000（640 KiB，5 个 0x20000 擦除块）的 erase+write；具体耗时未实测
  （估 1–5 s）。窗口内掉电可能使 U-Boot 镜像区不完整，secondboot 的
  `backup header!!` 冗余机制语义未验（`docs/U-Boot结构分析-2026-11-15.md`），
  **不能假定自动恢复**；最坏情况需要拆机编程器。
- 因此 v1 的硬性要求：网页刷机时串口必须可用（有我们 U-Boot 的串口控制台，
  `loadx`+go 可救）；host 上保留原 mtd0 镜像与 sha256；刷写前屏幕/串口回显 old/new
  版本、槽表、镜像 sha256/CRC32（S 项）。
- 不自作主张做「双分区 A/B 引导区」——留作后续。

## 6. 行为与验收

完整需求（MUST/SHOULD/WON'T）写在设计文档
`docs/E4-多功能U-Boot设计-2026-11-27.md` 的 §1；本处只记结论：v1 正常上电行为不变
（e2631boot 自动起槽），救援只由串口命令 `e2631rescue` 进入（本板无用户按键，不做
按键手势；启动计数触发属 E5）。救援模式内 DHCP 服务器（lan1）+ HTTP:80 + 一次上传、
五步刷写、重启；不要求 host 配置 DHCP/TFTP。验收命令见设计文档 §7。

**F2 未修复 = 整个 E4 v1 无意义**：DHCP 租约、页面、上传都要求 TX 回包。F2-a 已在代码
层修复（patch 0023 把 `eth_send` 的静默 `-ENOSPC` 改成打印原因/所需 buffer/BMU 状态，并
移植内核 pending-retry 收取迟到 buffer；patch 0024 加 staging/kernel-copy/arena 编译期
断言），24-patch 构建 CI 绿（run 45985501668）；但真机侧尚未按
`evidence/uboot-e2-fix-20261127.md` §5 的零写协议复测（`mii info` → `e2631net` 计数 →
`dhcp` → 失败即时读 BMU 寄存器 → 抓包判读）。E4 的实现任务以该复测 PASS 为入口条件。
F1（bootm 静默返回）影响「刷完自动起槽」的异常分支：产品级 flash boot 当前是绿的，但
页面/串口必须把 e2631boot 失败显式打印，不能静默。

## 7. E3（菜单）vs E4（DHCP+Web）依赖

- **E3 代码独立**：主线 `cmd/bootmenu.c`（我们树里已有，16,404 B 源码）+
  `CONFIG_CMD_BOOTMENU` + 默认 `bootmenu_*` env；估 4–7 KB。可以在 E4 之前或并行落地，
  不依赖网络。
- **E4 v1 不依赖 E3**：入口是串口命令 `e2631rescue`，不靠菜单。E4 完成后，给 E3 加
  `"Start Web failsafe" → "e2631rescue"` 一项即可（一行），这一步串行在两件事都绿之后。
- **必须串行的只有**：两条路径共用同一个 eth 初始化/服务循环时，先定 `e2631rescue`
  （E4）的入口与退出语义，E3 菜单项后接；其余并行。
- 上游的 `MTK_WEB_FAILSAFE_AFTER_BOOT_FAILURE` 依赖启动计数，属 E5（未排期），v1 不做。

## 8. 未决问题（需要 Lead/用户拍板）

- **Q1 预算口径**：A/C 用基线 159,104 B 即可（不捐子系统）；B 才需要 Lead 的捐献预算
  （290 KB）。是否现在就裁 EFI/FAT/MMC/PXE？（裁了 A 余量翻倍，但改变现有镜像能力）
- **Q2 上传缓冲地址**：0x46000000 + 1 MiB 需在目标 U-Boot 版本上用 mem_map/LMB/bdinfo
  复核一次（我们记录里 relocaddr≈0x4FF94000、LMB 保留自 0x4EB70000 起，0x46000000
  应安全；但要实测 `md` 前后不被 malloc/堆占用）。
- **Q3 DHCP 池与地址**：设备固定 192.168.1.1，池 192.168.1.100+（沿用上游默认）？
  是否需要在页面显示租约/IP？la n1 口上的 PHY 0a–0d 用现有 E2 PHY 驱动。
- **Q4 F2 真机复测排期**：patch 0023/0024 已绿，但 `evidence/uboot-e2-fix-20261127.md` §5
  的零写入复测（mii/e2631net/dhcp/BMU 寄存器/抓包）谁做、何时做；未 PASS 则 E4 不验收。
- **Q5 F1 边界**：网页刷完后的「重启」若 e2631boot 静默返回，页面应如何呈现（报错并停
  在串口，而不是假装成功）。
- **Q6 是否要 S 项**：TFTP 第二通道（复用现有 tftp 命令 + 服务端 API 小改动）、
  verify-only、槽表/sha256 显示——按预算逐项选。
- **Q7 B 是否做、何时做**：做则需 Lead 批准捐献 + 模块重写工期（估 ≥1–2 周）。
- **Q8 安全**：网页刷机窗口内是否强制「串口已连接」提示（MUST 级建议，写入设计文档）。

## 9. 复现

- 上游：`git clone --depth 1 https://github.com/Yuzhii0718/bl-mt798x-dhcpd /tmp/bl-mt798x-dhcpd`；
  HEAD `e4cf4dc72d451dc7a86c9508390ad5a2e50743c4`；源码尺寸 `find/fstat`；
  gzip 资产尺寸取自 release build-logs（`build-logs_20261030-121357.tar.gz`，
  "gzip" 步骤与 U-Boot size 行）。
- 本地 U-Boot：`/home/qc233/zte/uboot-src`（含 `board/zte/zxhn-e2631/e2631flash.c`、
  `e2631boot.c`）；构建产物 `.config`/`u-boot.map` 取
  `/home/qc233/zte/e2631-t5-artifacts/t71-run1-45984779157/`（run 32）与
  `.../t71-run33-45985501668/`（run 33）。
- 尺寸基线：`evidence/t71-uboot-payload-budget-20261127.md`（门禁 645,120 / 硬上限
  653,312 / 24-patch 494,880 B / 余量 158,432 B）；F2-a 修复与真机复测协议见
  `evidence/uboot-e2-fix-20261127.md`。
- 既有 E 系列设计：`docs/多功能U-Boot可行性-2026-11-14.md`（P0–P4 阶段；
  本文件不改变其阶段划分，只把 E4 的可行性、尺寸与刷写路径量化）。

## 10. 低置信度与边界

- 所有编译尺寸为密度估算（§4.1），±50% 以内；真实值必须由 CI `UBOOT-SIZES.txt` 复核。
- 上游 arm64 编译密度可能比我们 arm32 略高，故估算偏保守（宁大勿小）。
- 未验证：`mtk_tcp.c` 在我们 2027 老式 net API 上的实际改动量（shim 大小 1–3 KB 是估）、
  `httpd_get_upload_buffer_ptr` 单次上传的最大字节（受 TCP 窗口/缓冲影响，640 KiB 需实测）、
  e2631flash 擦写窗口的实际耗时与掉电后果、secondboot backup-header 语义。
- 本文件只读调研：未改 `uboot-port/patches`、未动树 fork、未碰真机、未派 CI。
