# ImmortalWrt 基线迁移决策（T1）

> 状态：已采纳并在实施中（T1 决策稿 → T2 落地 base/ → T3 品牌/产物 → T4 门禁/文档；T5 端到端验证已通过，证据见 evidence/immortalwrt-verify-20261114.md，合 main 待用户批准）
> 调研日期：2026-11-14（本文所有 ImmortalWrt / 上游事实均为该日实测；数据源与复现命令见 §1.4、§7.1）
> 调研人：iwrt-baseline（T1）；维护：verify-docs（T4）；基底升级流程见 §8
> 仓库：QC3284/zte-e2631-immortalwrt；工作副本 /home/qc233/zte/e2631-immortalwrt；T1 时 HEAD `3e5440299c9a558f3da9f0bd9d429713573c870d`（main）
> 实施记录（2026-11-14）：`base/` 已随仓库入库（4 个 patch + commits.env + README）；overlay 已按 §3 矩阵迁移；品牌定为 **ImmortalWrt v1.10.0**、产物前缀 `e2631-immortalwrt-*.bin`；`make check` 新增 g_layout、base-pin 两门（见 §6.3）。
> 范围：只读调研 + 本文档。未改任何源码、未推送、未在本机构建；双槽布局/刷写机制不在本轮改动范围内。
> 约束：TEAM-NOTES.md 约束 2（本机不做全量编译，构建与端到端验证走 GitHub Actions）；真机刷写 / GitHub 推送 / 新建仓库 / 正式 Release 需用户批准。

## 0. 结论速览

| 决策项 | 结论 | 关键证据 |
| --- | --- | --- |
| 目标基线 | `immortalwrt/immortalwrt` **master @ `4765b657625ec5bbda74b44400465fe043802b30`**（2026-11-05），kernel **6.18.60**，包管理器 apk | §1.1、§1.3 |
| 不选 25.12 | openwrt-25.12 是 kernel 6.12 线，与本项目 6.18 目标树不匹配 | §1.2 |
| 移植方式 | 把 sanechips PR 的 **4 个提交 vendored 成 patch series**（新增 `base/`），bootstrap 在 iw 钉死 SHA 上 `git am` 后再叠加 overlay | §2.1、§5.1 |
| 内核补丁兼容 | 33 个 target 补丁对 Linux v6.18.60 **32 通过 / 1 需基底提供**（028 依赖 ImmortalWrt 的 heyangtek backport） | §2.2 |
| overlay 矩阵 | 229 个文件中 **直接复用 77 / 复用但需小改 2 / 删除 150 / 重写 0** | §3 |
| argon/homeproxy | **改用 ImmortalWrt feeds 版本，删除 overlay 自带 107+43 个文件**（同名包只能进一个版本） | §3.4 |
| 新增 target 合并结果 | 基底 55 个 target 文件 + overlay 新增 49 = **104 个文件**；4 处覆写基底同名文件 | §3.2 |
| 主要风险 | R1 通用补丁与 target 补丁的顺序/上下文只能靠 CI 验证；R3 品牌/版本/更新链多处硬编码；R4 分区几何常量存在既有漂移 | §2.7、§4.5 |
| 工作量 | T2 约 1.5–3 人日 + 3–5 轮 CI（每轮上限 150 分钟）；T3/T4 各 1–2 人日；本地 0 编译 | §2.6 |

## 1. 基线选择

### 1.1 候选清单（2026-11-14 实测）

| 候选 | 分支 | 精确 SHA | 提交日期（UTC） | kernel | 包管理器 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| **immortalwrt/immortalwrt** | **master** | **`4765b657625ec5bbda74b44400465fe043802b30`** | 2026-11-05T04:06:13Z | **6.18.60** | apk（默认，apk-openssl） | **✅ 推荐** |
| immortalwrt/immortalwrt | openwrt-25.12 | `761b7ff22cbf7c13f28fc631bd70a84d295fd627` | 2026-11-11 | 6.12.116 | apk | ❌ kernel 线不匹配 |
| immortalwrt/immortalwrt | openwrt-24.10 | `af0775ab50d2d0e41f4e558c59208f6c9b8bdf0b` | — | 6.6（旧布局） | opkg→apk 过渡 | ❌ 过旧 |
| openwrt/openwrt | main（对照） | `24c13d794c810e14b52bd6e9720a1f512b5e5f23` | 2026-11-13 | 6.18 | apk | ❌ 没有 ImmortalWrt 包层/品牌，无法满足迁移目标 |
| Zlion-Y/openwrt-sanechips-mirror | pr-zte-zxhn-h3600（**当前基底**） | `db8b8d4130457dbe46558a7cea872dd2dae539e6` | 2026-10-12T17:14:44Z | 6.18.55 | apk（默认，apk-mbedtls） | 迁移源 |

补充事实：

- ImmortalWrt master 的 kernel 版本由 `target/linux/generic/kernel-6.18` 第 1–2 行钉死：`LINUX_VERSION-6.18 = .60`、`LINUX_KERNEL_HASH-6.18.60 = 3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e`。
- master 是移动分支，**T2 必须钉上面这个 SHA**；本文日期之后 master 前进不影响本决策，只需重新验证 4 个提交是否仍可 `git am`。
- openwrt-25.12 已有正式 tag `v25.12.0/1/2`，但 kernel 6.12.116 —— 与 `target/linux/sanechips/Makefile` 的 `KERNEL_PATCHVER:=6.18` 不匹配。

### 1.2 选择 master 的三条理由

1. **内核线唯一匹配**：本项目 `target/linux/sanechips/Makefile` 声明 `KERNEL_PATCHVER:=6.18`，DTS 与 33 个内核补丁（编号 001–034，其中 032 已删除）全部面向 6.18；iw master 的 6.18.60 与基底 6.18.55 属同一 LTS 线。换 25.12 的 6.12 等于重写整个目标移植面，代价最高。
2. **移植起点干净**：sanechips PR 的 4 个提交直接建立在 upstream `936617ab598e`（2026-10-10T11:04:55Z）之上；该提交经 compare 确认为 iw master 的祖先（`ahead_by 6049 / behind_by 0`），即 **4 个提交可以直接重新应用到 iw master 上，不需要 rebase 解冲突**。
3. **移植面仅 4 个提交 / 59 处文件改动（58 个唯一路径）**：1（DWC3 glue）+ 2（mt76 序列化补丁）+ 46（sanechips target）+ 10（H3600 板级），见 §2.1；其中 46+10 是全新目录，不存在与 iw 树的内容冲突。

### 1.3 ImmortalWrt 相对 OpenWrt 的关键差异（与本项目相关）

| 差异点 | ImmortalWrt master | 当前 OpenWrt 基底（PR 分支） | 对本项目的影响 |
| --- | --- | --- | --- |
| kernel | 6.18.60（`target/linux/generic/kernel-6.18:1-2`） | 6.18.55 | 同一 LTS 线；内核补丁需重测（已做，§2.2） |
| 包管理器 | apk 默认，imply `PACKAGE_apk-openssl`（`config/Config-build.in:71-72`） | apk 默认，imply `PACKAGE_apk-mbedtls`（PR 分支同文件 :71-72） | 同为 apk，但 **TLS 后端不同**（openssl vs mbedtls）；seed 第 46 行显式 `libustream-mbedtls=y` 需 T2 复核 |
| feeds | `packages`=immortalwrt/packages、`luci`=immortalwrt/luci，routing/telephony/video=openwrt/*（`feeds.conf.default:1-5`） | git.openwrt.org 的 openwrt feeds | LuCI 来源变化；argon/homeproxy 在 iw feeds 内已存在 → 与 overlay 自带版本冲突（§3.4） |
| 品牌/版本号 | `VERSION_DIST` 默认 ImmortalWrt、`VERSION_NUMBER` 默认 SNAPSHOT、`VERSION_REPO` 默认 downloads.immortalwrt.org/snapshots（`include/version.mk:38-39,29-30,35-36`） | 默认 OpenWrt / downloads.openwrt.org/snapshots | 生成的 `/etc/openwrt_release` 品牌变化；自定义 `/etc/e2631-version` 不受影响但需决策（§4.1） |
| 默认包集 | `libustream-openssl`、`dnsmasq-full`、`partx-utils`（legacy-sdcard）、GPIO feature 只认 `CONFIG_GPIOLIB`（`include/target.mk:28,53,108,319`）；`DEFAULT_PACKAGES.tweak` 已定义但应用行被注释（:62-63,:115） | OpenWrt 默认集 | 镜像体积/默认包会变；seed 显式覆盖的部分需逐项核对 |
| 通用补丁 | `target/linux/generic` 共 688 个 blob：233 个 backport-6.18 + 270 个 pending-6.18 + 73 个 hack-6.18 | 基底同目录但内容不同 | target 补丁与 iw 通用补丁的上下文/顺序交互只能在 CI 上验证（§2.3） |
| 厂商附加包 | `package/` 下有 emortal/（autocore、automount、autosamba、cpufreq、default-settings） | 无 | 与本项目不冲突，属 iw 额外能力，保持默认关闭即可 |
| target/linux/sanechips | **不存在**（0 命中） | 存在（db8b8d4 上 55 个文件） | 必须移植（方案 A 的核心工作） |

### 1.4 采集方法与可复现性

- 通过 `api.github.com`（branches/commits/compare/contents）与 `raw.githubusercontent.com` 只读采集；2026-11-14 当天 GitHub REST core 配额（60/小时）用尽后全部改走 raw，未使用任何写操作。
- 采集到本机 /tmp 的原始文件（可作为复核依据）：`/tmp/iw-version.mk`、`/tmp/iw-feeds.conf.default`、`/tmp/iw-target.mk`、`/tmp/iw-Config-build.in`、`/tmp/iw-config-6.18`、`/tmp/iw-mt76-Makefile`、`/tmp/iw-fstools-Makefile`、`/tmp/iw-usb.mk`、`/tmp/iw-argon-Makefile`、`/tmp/iw-homeproxy-Makefile`、`/tmp/pr4/*.patch`（PR 4 提交）、`/tmp/sanpatch/{base,overlay}`（target 补丁 001–028 + 029–034）。
- 复现命令见 §7.3；本文所有「行号」均指采集当日 raw 文件的行号。

## 2. 移植可行性、工作量与风险

### 2.1 需要移植的 4 个提交（逐提交适用性，实测）

| # | commit | 标题（原文） | 文件数 | 在 iw master 上的适用性 |
| --- | --- | --- | --- | --- |
| 1 | `fbf76e3cd0796e9a6c10388708a6eaccd73057cd` | kernel: add generic DWC3 platform glue package | 1（M `package/kernel/linux/modules/usb.mk`） | ✅ `git apply` 到 iw master 同名文件，offset -8 干净应用 |
| 2 | `773fd136fd9d9cc79b07d17ee645ac9b2b5a0022` | mt76: serialize device reads with outer cache maintenance | 2（M `package/kernel/mt76/Makefile`；A `patches/001-wifi-mt76-serialize-register-reads-with-outer-cache.patch`） | ⚠️ 驱动补丁本体干净（对 iw mt76 pin `0936617d` 验证 OK）；Makefile hunk 与 iw 已有的 `PKG_RELEASE:=2` 冲突（reversed）→ 丢弃该 hunk，改由 apply.sh 把 `:=2` 提到 `:=3` |
| 3 | `36754bf5c24618937c877ba1f36792b6b86fa531` | sanechips: add ZX279128S target | 46（全部为 `target/linux/sanechips/` 下新文件） | ✅ 全新目录，干净添加 |
| 4 | `db8b8d4130457dbe46558a7cea872dd2dae539e6` | sanechips: add support for ZTE ZXHN H3600 | 10（9 新增 + 1 修改 `image/Makefile`） | ✅ 依赖 #3，按顺序应用干净 |

- 4 个提交作者均为 Navid Ghahremani（2026-10-12，+0100），上游 GPL-2.0 代码；本仓库是自用 fork，**不向上游提 issue/PR**，只在仓库内 vendored 保留作者与提交信息。
- 59 处文件改动、58 个唯一路径（`image/Makefile` 在 #3/#4 各出现一次）。
- 结论：**移植不需要 rebase 或改写代码，只需要按序应用 + 对 #2 做一个 hunk 级的本地化处理**。

### 2.2 内核补丁 vs Linux v6.18.60（实测 32 OK / 1 需基底提供）

方法：从 git.kernel.org stable v6.18.60 逐文件拉取全部 65 个 b-side 路径（覆盖 base 001–028 与 overlay 029,030,031,033,034 共 33 个补丁），按序 `patch -p1 -F3` 应用。

- **结果：33 个补丁中 32 个干净应用，1 个无法应用**：
  - 失败项：`028-mtd-spinand-heyangtek-Reserve-both-bad-block-marker-...patch` —— 其目标文件 `drivers/mtd/nand/spi/heyangtek.c` 在 pristine Linux 6.18.0/6.18.55/6.18.60 中都不存在。
  - 原因：该文件由 ImmortalWrt 的通用 backport `target/linux/generic/backport-6.18/436-v7.3-mtd-spinand-add-support-for-HeYangTek-HYF1GQ4UDACAE.patch` 引入；基底 OpenWrt 树也有同一 backport，所以基底能应用、pristine 不能。
  - 结论：**这不是迁移障碍，反而是 iw 基底天然满足 028 的前置条件**；T2 只需断言 436 backport 存在。
- 高风险补丁逐个实测通过（都是与 6.18 内核核心代码交互的）：

| 补丁 | 触及文件 | 对 6.18.60 结果 |
| --- | --- | --- |
| 005 ARM l2c 序列化 | `arch/arm/include/asm/outercache.h`、`arch/arm/mm/Kconfig`、`arch/arm/mm/cache-l2x0.c` | ✅ 干净 |
| 029 jffs2 clean marker | `drivers/mtd/mtdpart.c`、`drivers/mtd/nand/spi/core.c`、`fs/jffs2/{erase,fs,os-linux,scan,wbuf}.c`、`include/linux/mtd/mtd.h` | ✅ 干净 |
| 030 jffs2 跳块 | `fs/jffs2/scan.c` | ✅ 干净 |
| 031 PCIe link retrain | `drivers/pci/quirks.c` | ✅ 干净 |
| 028 spinand bad-block | 依赖 436 backport 提供的 `heyangtek.c` | ⚠️ 需 iw 通用补丁先落位（预期满足） |

- **边界**：该测试只证明「target 补丁 vs Linux 6.18.60 源码」兼容，不覆盖 ImmortalWrt 通用补丁集（233+270+73 个）与 target 补丁的上下文/顺序交互 —— 那只能在真实 CI 编译里验证（§2.3）。

### 2.3 ImmortalWrt 通用补丁交互（本地不可证，CI 门）

- iw `target/linux/generic` 全树 688 blob，其中 backport-6.18 233 个、pending-6.18 270 个、hack-6.18 73 个；与本项目直接相关的有：backport 434/435/436/437（spinand）、pending 140/141/142（jffs2 rename/splice）、530（jffs2 lzma）、532（jffs2 eofdetect）、810/811（PCI 通用 quirk 开关）、487（Etron spinand）、hack 400（fmsh spinand）。
- 本地尝试「先应用 iw 通用补丁，再把 target 028/029/030/031 叠上去」是**不可靠的**：通用补丁需要完整源码上下文，本地 minimal 树无法满足，失败原因是缺文件而不是冲突；反过来 target 补丁在该 minimal 树上能应用，也不能证明它们在真实树上的顺序安全。
- **因此把「CI 编译通过」定为唯一验收门**：T2 第一轮 Actions 构建即为该门的判定；若失败，按补丁粒度二分禁用（先 target 028/029/031 等高风险项）并记录到 known-issues。
- 重要：`target/linux/generic/config-6.18` 与基底同名文件在 apply.sh 触碰的 8 个符号上完全一致（`# CONFIG_SOFTLOCKUP_DETECTOR is not set`、`# CONFIG_DETECT_HUNG_TASK is not set`、`CONFIG_DEFAULT_HUNG_TASK_TIMEOUT=120`、`# CONFIG_MAGIC_SYSRQ_SERIAL is not set`、`# CONFIG_PCIEPORTBUS is not set`、`# CONFIG_PCIEAER is not set`、`# CONFIG_DEVMEM is not set`、`# CONFIG_CMDLINE_BOOL is not set`，iw 行号 6978/1497/1481/3662/5035/5032/1507/1028），所以 apply.sh 的 sed 翻转与断言可原样保留。

### 2.4 包层补丁实测（mt76 / fstools / usb.mk）

| 对象 | iw 钉死版本 | 测试内容 | 结果 |
| --- | --- | --- | --- |
| `package/kernel/linux/modules/usb.mk` | iw master | 应用提交 #1 的 hunk | ✅ offset -8 |
| mt76 驱动补丁 | `0936617dc529ff9da0385221d3fa6de732231177`（2026-10-28，PKG_RELEASE 2） | 加 PR 的 `001-...outer-cache...patch`，再叠 iw 自己的 `100-wifi-mt76-mt76x02-...`、`100-wifi-mt76-mt7996-...`、`101-wifi-mt76-mt76x2u-...` | ✅ 全部干净，无冲突 |
| overlay mt76 补丁 | 同上 | `002-mt7915-use-caldata-file-before-efuse.patch` → `mt7915/eeprom.c` | ✅ 干净 |
| overlay fstools 补丁 | `907cf4496eb58c93daf3c9c65ce32eec6e6546e3`（2026-10-18，PKG_RELEASE 1） | 先应用 iw 的 `100-fstools-support-extroot-for-non-MTD-rootfs_data.patch`，再叠 overlay `203-overlay-ram-fallback.patch` | ✅ 干净 |
| mt76 Makefile | iw 已是 `PKG_RELEASE:=2`（第 4 行） | 提交 #2 想把 `:=1` 改成 `:=2` | ❌ reversed；改由 apply.sh 提到 `:=3` |

### 2.5 target 基础设施与配置兼容性

- `KERNEL_PATCHVER:=6.18`（target Makefile）↔ iw 6.18.60：同一 LTS 线，`target/linux/sanechips/config-6.18`（12,686 B）来自 6.18.55；stable 点版本之间一般无 Kconfig 符号删除，若有旧符号会在 CI 的 oldconfig/编译期暴露（不是本地可预判项）。
- **内核符号存在性**（任务卡第 3 点）：seed/e2631.config 与 target config-6.18 涉及的内核符号（VFP/NEON 关闭、lockup/hung-task 检测、CMDLINE、PPE/SPI 等 target 驱动项）未逐符号在本机核对 —— 存在性只能由 iw 6.18.60 的 Kconfig/oldconfig 给出；已把「构建日志无 unknown symbol / unmet dependency」列入 T2 验收（§6.1 DoD 第 4 条）。
- target 目录结构（`Makefile`、`generic/target.mk`、`image/Makefile`、`dts/`、`files/`、`patches-6.18/`、`base-files/`）与 iw 的 target 框架接口一致；`image/Makefile` 导出 `Device/Default`、`zte-slot-marker`、`uImage-ramboot`，与 `Makefile.e2631` 的 hook 兼容（apply.sh:147-152）。
- `generic/target.mk`（ARCH arm / BOARDNAME Generic / CPU cortex-a9）与 iw 的 `include/target.mk` 无冲突；DEVICE 名 `sanechips_generic_DEVICE_zte_zxhn-e2631` 不变，bootstrap 断言可原样保留。
- feeds 覆盖：iw `immortalwrt/luci` 约 167 个 `luci-app-*` 目录，seed 需要的 luci 应用（ttyd、smartdns、nlbwmon、upnp、wol、adblock-fast、homeproxy、zte-mesh 自有页等）全部在；非 luci 包（sing-box、smartdns、nlbwmon、miniupnpd、adblock-fast）在 immortalwrt/packages 中亦确认存在（2026-11-14 检查）。

### 2.6 工作量估计

| 任务 | 内容 | 估计 |
| --- | --- | --- |
| T2-1 | `base/` 4 个 patch + commits.env（iw SHA、base SHA、tree hash）+ bootstrap/apply/env 改造 | 0.5 人日 |
| T2-2 | feeds/seed/overlay 调整（删 argon+homeproxy、NOTICE/门禁同步、libustream 决策） | 0.5 人日 |
| T2-3 | CI 首轮 + 编译错误分诊（预留 3–5 轮，每轮 ≤150 分钟，含排队） | 1–2 人日 |
| T3 | 品牌/版本/产物命名/更新链常量 + 分区几何常量收口 | 1–2 人日 |
| T4 | 文档全量改写 + 门禁（g_layout、base-pin 断言）+ 测试字符串同步 | 1–2 人日 |
| 合计 | 不含用户审批与真机验证 | **4–7 人日 + CI 墙钟时间** |

### 2.7 风险登记

| 编号 | 风险 | 概率/影响 | 触发点 | 缓解 | 归属 |
| --- | --- | --- | --- | --- | --- |
| R1 | iw 通用补丁与 target 补丁顺序/上下文冲突 | 中/高 | T2 首轮 CI | CI 门 + 按补丁二分禁用 + 记录 | T2 |
| R2 | 本机不能验证，全部依赖 CI | 高/中 | 全过程 | 只用 Actions；每轮日志与 tree hash 落盘 | T2/T5 |
| R3 | 品牌/版本/更新链硬编码 | 高/中 | 首次发布会发现 | §4 清单逐项改 + 测试同步 | T3/T4 |
| R4 | argon/homeproxy 二选一选错 | 中/中 | T2 构建/menu | 采用 iw feeds 版；构建期断言只有一个同名包 | T2 |
| R5 | 分区几何常量既有漂移 | 中/中 | factory 打包/preflight | T3 统一 + T4 加一致性门（§4.5） | T3/T4 |
| R6 | 镜像体积 vs 17 MiB rootfs 窗口 | 中/高 | T2 构建 | argon/homeproxy 用 feed 版体积可控；持续测 squashfs 大小与余量 | T2 |
| R7 | apk-openssl 与 seed 的 libustream-mbedtls | 低/中 | 构建/在线更新 | T2 明确 TLS 后端，更新链实测 | T2 |

## 3. overlay 兼容矩阵（229 文件）

### 3.1 判定规则与总量

- 口径：`overlay/` 目录下 229 个文件（`overlay-removed.txt` 在仓库根，不在 overlay/ 内）；每条判定给出「复用 / 小改 / 重写 / 删除」并附证据。
- 结果：**直接复用 77、复用但需小改 2、删除 150、重写 0**。

| 区域 | 文件数 | 判定 | 去向 |
| --- | --- | --- | --- |
| `target/linux/sanechips/`（base-files/files/dts/image/patches-6.18） | 53 | 复用 51 + 小改 2 | 随 target 一起移植 |
| `package/luci/luci-app-e2631` | 5 | 复用 | 原样 |
| `package/luci/luci-app-e2631-wanport` | 6 | 复用 | 原样 |
| `package/luci/luci-app-zte-mesh` | 5 | 复用 | 原样 |
| `package/network/zte-mesh` | 6 | 复用 | 原样（含 4.5 MB 厂商二进制 tar） |
| `package/firmware/e2631-fwslot` | 2 | 复用 | 原样（静态 C） |
| `package/kernel/mt76` 补丁 | 1 | 复用 | 原样 |
| `package/system/fstools` 补丁 | 1 | 复用 | 原样 |
| `package/luci/luci-theme-argon` | 107 | **删除** | 改用 iw feeds 版（§3.4） |
| `package/luci/luci-app-homeproxy` | 43 | **删除** | 改用 iw feeds 版（§3.4） |
| **合计** | **229** | 复用 77 + 小改 2 + 删除 150 | |

### 3.2 target/linux/sanechips（53 文件）

基底（PR db8b8d4）的 `target/linux/sanechips` 共 55 个文件；overlay 对其 **覆写 4 个、新增 49 个**，合并后 **104 个文件**。

| 子区域 | overlay 文件数 | 其中覆写基底 | 判定与说明 |
| --- | --- | --- | --- |
| `base-files/` | 41 | 3（`etc/board.d/02_network`、`etc/hotplug.d/firmware/11-mt76-caldata`、`lib/upgrade/platform.sh`） | 复用；覆写是项目自身的板级修正（网络口映射、mt76 caldata、sysupgrade 平台钩子），必须覆盖基底同名文件 |
| `files/`（内核模块源码） | 5 | 1（`drivers/net/ethernet/zte/zx279128s-ppe.c`） | 复用；`slotpart.c`、`slotpart-core.c`、`zx279128s-ffe.c`、`zx-ffe-ops.h` 为新增，`ppe.c` 覆写基底版本（overlay 25,412 B vs 基底 23,314 B，含 PPE 硬件卸载改动） |
| `patches-6.18/` | 5（029/030/031/033/034） | 0 | 复用；已对 6.18.60 验证（§2.2）；032 在 overlay-removed.txt 中删除 |
| `dts/`（`zx279128s-zte-zxhn-e2631.dts`） | 1 | 0 | 复用；含 slot/hdr-delta 等分区几何（见 §4.5） |
| `image/Makefile.e2631` | 1 | 0 | **复用但需小改**：第 20–21 行注释与第 77 行 `--header-at 0x1400000` 与当前布局真值 `0x1500000` 不一致（既有漂移，§4.5），T3 统一 |

- `target/linux/sanechips/config-6.18`（内核配置，12,686 B）由基底提供、overlay 不改动；apply.sh 用 sed 在其上翻转 VFP/NEON、lockup 检测等符号，符号基线在 iw 上一致（§2.3）。
- `overlay-removed.txt`（仓库根，4 条）：`target/linux/sanechips/files/arch/arm/mach-zte/zx279128s-slotfix.c`、`target/linux/sanechips/patches-6.18/032-...patch`、`target/linux/sanechips/base-files/etc/uci-defaults/63_e2631_wan_ssh`（含注释行）。机制保留；T2 在 iw 基底上复核删除操作幂等（这些路径在 iw 基底上同样不应存在）。

### 3.3 package 区（26 文件，全部复用）

| 包 | 文件数 | 关键事实 | 迁移动作 |
| --- | --- | --- | --- |
| `luci-app-e2631` | 5 | `include $(TOPDIR)/feeds/luci/luci.mk`；只依赖 luci-base + e2631-fwslot | 原样（iw luci feed 路径相同） |
| `luci-app-e2631-wanport` | 6 | 含 zh_Hans po；luci.mk 生成 `-zh-cn` 翻译包 | 原样 |
| `luci-app-zte-mesh` | 5 | 依赖 `zte-mesh` 包与 rpcd | 原样 |
| `network/zte-mesh` | 6 | 含 `zte-mesh-runtime.tar.gz`（4,523,185 B，厂商 ARM32 二进制）、`PKG_FLAGS:=nonshared`、`DEPENDS @TARGET_sanechips` | 原样；与基底无关；NOTICE 与 secret-scan 白名单条目保留 |
| `firmware/e2631-fwslot` | 2 | 独立静态 C（无包管理器/内核源码依赖，仅依赖 sysupgrade 接口） | 原样 |
| `kernel/mt76` 补丁 | 1 | 对 iw mt76 pin 验证干净（§2.4） | 原样 |
| `system/fstools` 补丁 | 1 | 对 iw fstools pin 验证干净（§2.4） | 原样 |

### 3.4 vendored luci-theme-argon / luci-app-homeproxy：冲突分析与取舍（重点）

**为什么当初 vendor**：基底（旧 openwrt/luci feed）没有 argon、也没有 homeproxy；项目为了「apply 时不联网 clone」而把两份源码复制进 overlay。证据：`overlay/target/linux/sanechips/image/Makefile.e2631:44-46` 注释（Argon 自 v1.3 起 vendored，bootstrap 仅作 fallback）；`NOTICE:24-29` 第 3 条登记了 `overlay/package/luci/luci-theme-argon/`（Apache-2.0 OR MIT）。

**ImmortalWrt feeds 现状（2026-11-14 实测）**：

- `themes/luci-theme-argon`：`PKG_VERSION 3.1.3`、`PKG_RELEASE 20261106`（Makefile:13-14），`PKG_PROVIDES:=luci-app-argon-config`（:15），`LUCI_DEPENDS` 为 `+wget-any +jsonfilter +ucode-mod-math`（:10），`include ../../luci.mk`。
- `applications/luci-app-homeproxy`：存在，`LUCI_DEPENDS` 为 sing-box/firewall4/kmod-nft-tproxy/ucode-mod-digest；与 overlay 版的**运行时文件基本一致**（`root/etc/init.d/homeproxy`、`root/etc/homeproxy/scripts/homeproxy.uc`、`htdocs/.../homeproxy.js` 三处 diff 为空），差异集中在构建胶水（overlay 版加 `LUCI_PKGARCH:=all`、`PKG_NAME`、`include $(TOPDIR)/feeds/luci/luci.mk`、版权年份）。
- overlay 版 argon：107 文件，`PKG_VERSION 3.1.0`、`PKG_RELEASE 20261022`（Makefile:14-15），额外依赖 `+flock +coreutils +coreutils-timeout`（:11），`LUCI_BASENAME:=argon-config`（:13），含 opkg/apk 双分支的 `PKG_PO_VERSION`（:18-26）、`CONFIG_LUCI_CSSTIDY/UTMIN` 构建选项（:28-33）、`conffiles` 只保留 `/etc/config/argon`（:35-37）、`include $(TOPDIR)/feeds/luci/luci.mk`（:39），并包含 `compat/luci-app-argon-config/Makefile` 与 rpcd `luci.argon_update`。

**冲突机制**：包名 `luci-theme-argon` / `luci-app-homeproxy` 同时出现在 overlay `package/` 与 iw feed 中，而构建系统按包名唯一索引 —— 两份同名包只会构建其中一份（取决于扫描顺序），版本、依赖表、菜单项与 ucode 会错配，且**不可控**。因此必须二选一，不能「两边都留」。

**推荐：选 ImmortalWrt feeds 版本，删除 overlay 两份（150 文件，占 overlay 的 65%）**。理由：

1. feed 版是维护中的上游版本（argon 3.1.3 > overlay 3.1.0；homeproxy 运行时文件本就相同）；
2. iw luci feed 是 iw 官方支持的包来源，升级/安全修复随基底前进；
3. 删除后 overlay 从 229 降到 79，apply 与审阅成本显著下降；
4. homeproxy 的 overlay 副本没有 `PKG_VERSION`（本地快照），长期不可追溯。

**代价与同步动作（T2 必须同批完成）**：

- `NOTICE:24-29` 删除第 3 条（argon 版权条目）；
- `scripts/notice-check.sh:9-13` 的 MUST 数组删除 `overlay/package/luci/luci-theme-argon/` 行；
- `scripts/secret-allowlist.txt:8-10` 删除 homeproxy resources 的 glob 及注释（文件删除后该条目失效）；
- `overlay/target/linux/sanechips/image/Makefile.e2631:44-46` 的 vendoring 说明注释同步改写（否则误导后续维护者）；
- `seed/e2631.config` 不需要改包名（仍选 `luci-theme-argon` / `luci-app-homeproxy` / `luci-i18n-homeproxy-zh-cn`），但 T2 要验证 feed 版构建后的默认主题与 homeproxy 运行行为。

**备选（不推荐）**：保留 overlay 版本、在 feeds 层禁用同名包。缺点是要维护 feed 补丁/禁用逻辑，且 luci.mk 扫描仍可能撞名，收益仅是钉死版本。

### 3.5 迁移后的 overlay 形状（79 文件）

- `target/linux/sanechips/`：53 文件（含 5 个 target 补丁、1 个 dts、1 个 image 规则、41 个 base-files、5 个内核模块源码）；
- `package/luci/`：16 文件（e2631 5 + wanport 6 + zte-mesh 5）；
- `package/network/zte-mesh/`：6 文件；`package/firmware/e2631-fwslot/`：2 文件；`package/kernel/mt76/`：1 文件；`package/system/fstools/`：1 文件。
- 合并到 iw 基底后：`target/linux/sanechips` 104 文件（55+49），其余为新增包目录。

## 4. 版本 / 品牌 / 在线更新链影响清单

### 4.1 品牌与版本号字符串

| 位置 | 当前值 | 迁移后变化 | 动作 / 归属 |
| --- | --- | --- | --- |
| `overlay/target/linux/sanechips/base-files/etc/e2631-version:1` | `OpenWrt v1.9.0` | iw 基底不再生成这个自定义文件；文件本身保留 | **需用户决策**：是否改成 ImmortalWrt 品牌（如 `ImmortalWrt v?.?.?`）还是保留 OpenWrt 字样；T3 |
| `base-files/sbin/e2631-upgrade:42-60` | 版本比较：剥掉字母后按数字段比较 | 品牌字符串变化不影响比较逻辑 | 无需改；T3 补测试 |
| `base-files/sbin/e2631-upgrade:127-146` | 降级保护（同逻辑） | 同上 | 无需改 |
| 生成文件 `/etc/openwrt_release` | iw 默认 `DISTRIB_ID=ImmortalWrt`、`VERSION_NUMBER=SNAPSHOT`、`VERSION_REPO=downloads.immortalwrt.org/snapshots` | LuCI「关于」页显示 ImmortalWrt | 无需改；T3 决定是否覆盖（自定义版本文件与 openwrt_release 是两套） |
| `scripts/preflight.sh:123-131`、`overlay/.../sbin/e2631-preflight:121-129` | 读取 `/etc/e2631-version` | 文件仍存在 | 无需改 |

### 4.2 在线更新链（e2631-upgrade）

- `base-files/sbin/e2631-upgrade:28`：`REPOSITORY` 取 `uci e2631.upd.repository`，缺省回退 `Zlion-Y/zte-e2631-openwrt`；`:37` 调用 `https://api.github.com/repos/$REPOSITORY/releases/latest`；镜像可配 `uci e2631.upd.mirror`（:75）。
- 迁移后仓库是 `QC3284/zte-e2631-immortalwrt`：**必须改默认 REPOSITORY**，否则在线更新仍去旧仓库（旧仓库不再发布新版本）。用户可在 LuCI 里覆盖（uci 项），但默认值必须是新仓库。
- 资产名约定：`e2631-openwrt-experimental.bin`（`firmware.yml:41-43`）—— 若 T3 改产物前缀（如 `e2631-immortalwrt-*`），更新链与 `BUILD.md:137`、`scripts/build.sh:73,93`、`host/release.mjs:72`、`host/stage.mjs:28` 必须同步。
- **发布新 Release / 推送仓库需用户批准**（硬约束）；T3 只准备代码与检查表，执行前向 Lead 报批。

### 4.3 CI 变量与产物命名

| 位置 | 当前值/行为 | 迁移动作 |
| --- | --- | --- |
| `.github/workflows/firmware.yml:12` | `timeout-minutes: 150` | 保持（本机不编译；CI 是唯一构建通道） |
| `firmware.yml:16-18` | `E2631_TREE`/`E2631_OUT`/`E2631_VERSION=OpenWrt v1.4`（与仓库 v1.9.0 已不一致） | T3 统一版本号来源，避免 CI 与仓库版本脱节 |
| `firmware.yml:41-43` | 找 `e2631-openwrt-*.bin` 复制为 `release/e2631-openwrt-experimental.bin` | 随产物前缀决策同步 |
| `firmware.yml:44-51` | SOURCE-INFO 记录 base/feeds commit 与 `Hardware tested: NO` | T2 增补 iw SHA + base tree hash |
| `host/release.mjs:52,61,72` | `HEADER_AT` 默认 `0x1500000`；`--version`/`E2631_VERSION`；输出默认 `out/e2631-openwrt-factory.bin` | 版本来源改 T3 决策；HEADER_AT 与真值一致（保持） |
| `host/release.mjs:111-114` | `--run` 从 origin remote 读 GitHub slug | 改仓库后自动适配，无需改 |
| `scripts/build.sh:73,93` | `out/e2631-openwrt-$STAMP.bin` | 随产物前缀决策同步 |

### 4.4 文档/链接/测试中的旧基底与旧仓库引用

| 位置 | 内容 | 动作 / 归属 |
| --- | --- | --- |
| `README.md:4`、`README.en.md:50` | 链接 `Zlion-Y/zte-e2631-openwrt` | T4 改为本 fork 或保留溯源说明 |
| `README.md:76-77,95`、`README.en.md:20-21,87,192`、`BUILD.md:35-39`、`docs/architecture.md:13,47` | 基底=PR 分支 @ db8b8d4、kernel 6.18.55 | T4 改为 iw master @ 4765b65 + base patch 说明 |
| `.env.example:19-21`、`scripts/env.sh:63-67` | 基底变量默认值 | T2 改代码，T4 补文档 |
| `docs/known-issues.md:256-264` | 版本号三段式规则与升级比较 | T4 复核（逻辑不变，品牌名可能要调） |
| `docs/updates.md:37-38` | 检查 GitHub releases/latest | T4 更新仓库名 |
| `tests/test_upgrade.py:37-38,81,84` | 写入 `OpenWrt v1.8.0` | T4 随品牌决策同步 |
| `tests/test-slot-decisions.c:62,129` | 写入 `OpenWrt v1.4` | T4 同步 |
| `board/firstboot-openwrt.txt:4` | `DISTRIB_ID=OpenWrt`（采集到的设备证据） | **保留**（历史证据，不改） |

### 4.5 附带发现：分区几何常量漂移（既有问题，非迁移引入）

**当前布局真值**（2026-11-14 工作副本）：kernel 在 slot+`0x400000`，rootfs 窗口 `0x1100000`（17 MiB），版本头在 slot+`0x1500000`。证据：`tools/verify_img.mjs:290`（`KERNEL_AT=0x400000`、`ROOTFS_SPAN=0x1100000`、`HEADER_AT=0x1500000`）、DTS 的 `zte,hdr-delta = <0x01500000>`（slot0 `0x00700000/0x01c00000`、slot1 `0x02300000/0x01c00000`）、`host/release.mjs:52`（`HEADER_AT` 默认 `0x1500000`）。

**陈旧副本（旧布局 0x1400000/0x1800000 遗留）**：

| 位置 | 陈旧值 | 备注 |
| --- | --- | --- |
| `overlay/.../image/Makefile.e2631:20-21,77` | 注释 16 MiB/`0x1400000`；`--header-at 0x1400000` | 影响 factory 打包参数（T3 修）→ **已修**（T3：注释 17 MiB、`--header-at 0x1500000`） |
| `scripts/preflight.sh:62-66`、`overlay/.../sbin/e2631-preflight:60-64` | `0x1400000` | 预检可能误报 → **已修**（T4 改主机副本为具名常量 `E2631_KERNEL_AT/ROOTFS_SPAN/HEADER_AT`；设备副本由 T2 同步，g_layout 门守） |
| `seed/e2631.config:110-112`（注释） | 20 MiB、rootfs `0x1400000`、header `0x1800000` | 纯注释，误导 → **已修**（T2） |
| `host/release.mjs:7`（注释） | `0x1800000` | 纯注释 → **已修**（T3 改 `0x1500000`） |
| `docs/relnotes-v1.9.0.md:4` | header `0x1100000` | 文档旧值 → **已修**（T4 改 `0x1500000`） |
| DTS 注释（约 340–355 行、462 行） | `0x1400000` | 注释与属性值不一致 → **已修**（T3，随 VERSION 提交） |
| `files/.../slotpart.c:147` 默认 `hdr_delta=0x1400000` | 运行时被 DTS 覆盖 | 低风险 → **已修**（T3 默认改 `0x1500000`；注释同步） |

**为什么现在还能工作**：设备端 `e2631-fwslot.c` 通过 inner magic+CRC1 扫描定位版本头（`slot_scan`，约 405–430 行），不依赖固定偏移；`release.mjs` 默认值与真值一致。**风险集中在**：`Makefile.e2631` 的 factory 打包 `--header-at`、preflight 预检、文档表述。

**建议**：T3 统一为 `0x1500000`/`0x1100000`（17 MiB），T4 增加跨文件一致性门（g_layout：比对 verify_img / release.mjs / Makefile.e2631 / DTS / preflight），防止再次漂移。

## 5. 迁移方案与回滚

### 5.1 方案 A（推荐）：ImmortalWrt 钉 SHA + 4 提交 patch series vendored 进本仓库

机制：在仓库内新增 `base/` 目录，保存 4 个上游提交的 patch 与钉死信息；bootstrap 克隆 iw 到钉死 SHA 后按序 `git am`，再执行原有 overlay apply 流程。

1. `base/0001-kernel-add-generic-DWC3-platform-glue-package.patch`（原样）；
2. `base/0002-mt76-serialize-device-reads-with-outer-cache-maintenance.patch`（**去掉 Makefile hunk**，只保留新增驱动补丁文件；PKG_RELEASE 由 apply.sh 统一提到 `:=3`）；
3. `base/0003-sanechips-add-ZX279128S-target.patch`（原样）；
4. `base/0004-sanechips-add-support-for-ZTE-ZXHN-H3600.patch`（原样）；
5. `base/commits.env`：记录 `E2631_IW_REPO/BRANCH/SHA`、`E2631_BASE_SHA`、4 个 patch 的 sha256、以及 `git am` 之后的 **tree hash**（`git rev-parse HEAD^{tree}`）；
6. `base/README.md`：来源（Zlion-Y/openwrt-sanechips-mirror#pr-zte-zxhn-h3600）、作者、GPL-2.0、为何 vendored、升级方法（iw 前进时重生成 patch 并更新 tree hash）。

`scripts/bootstrap.sh` 新流程（替换现 :28-48 段）：`git clone` iw → `git fetch origin <SHA>` → `git checkout <SHA>` → `git am base/0001..0004` → 断言 tree hash → 校验 `target/linux/sanechips` 存在 → 继续 feeds/seed（iw feeds）。

确定性：**三重钉**（iw 提交 SHA + base patch 内容 sha256 + 应用后 tree hash），任何一环变化都会在 bootstrap 立即失败，而不是产生一个「看起来一样」的构建。

优点：不需要新建/推送 base 仓库（除 T2 正常推送本仓库外无额外审批面）；基底内容随本仓库版本走，可复现。缺点：iw 前进需要重生成 patch（预计每季度一次，成本 <0.5 人日）。

**流程提醒**：T2 要在 GitHub Actions 上构建，必须先把改动推送到 QC3284 仓库 —— 这一步按硬约束**需用户批准**；T2 实施前由 Lead 向用户报批（技术上一轮 CI 即可验证）。

### 5.2 方案 B：在 QC3284 下新建 ImmortalWrt 基底 fork/分支并钉 SHA

- 优点：来源更清晰，本仓库不需要 vendored patch；基底的提交历史独立可查。
- 缺点：需要新建仓库/分支并推送（**需用户批准**）；变成两个仓库的维护关系；CI 需跨仓库 clone；基底更新仍需人工同步。
- 结论：不选；若未来 patch series 维护成本上升（如 iw 半年内大改 target 框架），可作为备选。

### 5.3 方案 C：保留 sanechips/OpenWrt 基底，只换 ImmortalWrt feeds/包层

- 能做：argon/homeproxy 等包换成 iw 版本，LuCI 更丰富。
- 不能做：拿不到 iw 的 kernel 6.18.60、通用补丁、品牌/默认包集；目标（适配到 ImmortalWrt 基底）未达成。
- 结论：不选（工作量最低但目标不符，最多作为过渡验证 feeds 冲突）。

### 5.4 方案 D：改用 openwrt-25.12（kernel 6.12）

- 需要把 33 个 6.18 内核补丁、DTS、mt76 补丁全部回移到 6.12，等价于重写目标移植面。
- 结论：不选（成本最高，收益最低）。

### 5.5 决策矩阵

| 方案 | 内核匹配 | 移植成本 | 长期维护 | 可复现性 | 需用户批准 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| A：iw 钉 SHA + vendored patch series | ✅ 6.18.60 | 中 | 中（季度重生成） | 高（三重钉） | 仅推送需批准 | **推荐** |
| B：iw fork 分支作外部基底 | ✅ | 中高 | 高（双仓） | 高 | 新建+推送需批准 | 备选 |
| C：仅换 feeds | ❌ 6.18.55 | 低 | 低 | 高 | 否 | 不选 |
| D：25.12 / 6.12 | ❌ 6.12 | 高 | 高 | 高 | 否 | 不选 |

### 5.6 回滚计划

1. **代码层**：`scripts/env.sh` 保留 `E2631_BASE_KIND=immortalwrt|legacy` 开关（默认 legacy，直到 T2/T5 验收通过再翻默认）；`.env` 可覆盖回旧基底，`bootstrap.sh`/`apply.sh` 双分支并存一个周期。
2. **失败回滚**：T2 分支 revert 即回到现状；`base/` 目录可保留（不影响旧基底流程）；旧基底 pin（PR 分支 + db8b8d4）仍可 clone，历史产物不受影响。
3. **发布回滚**：T3 只准备、不在用户批准前发布；已发布 Release 不删除，靠 updater 的降级保护（`e2631-upgrade:127-146`）与 A/B 槽回退。
4. **真机回滚**：双槽 + fwslot 机制不变；刷写属需用户批准操作，T2/T3 不碰设备。
5. **文档回滚**：本文与后续文档提交均可单独 revert，不影响构建。

## 6. 下游任务输入清单（T2 / T3 / T4）

### 6.1 T2：构建链打通（可直接开工）

| # | 文件:行 | 改动 | 验收 |
| --- | --- | --- | --- |
| 1 | `scripts/env.sh:63-67` | 增加 `E2631_BASE_KIND`（legacy/immortalwrt）；iw 分支/SHA 默认值（`4765b657...`）；`E2631_BASE_TREE_SHA`；`E2631_PORT_DIR=base` | `make bootstrap` 两种 kind 都能到 apply 阶段 |
| 2 | `base/`（新增） | 4 个 patch + `commits.env` + `README.md`（来源/许可/升级说明）；0002 去 Makefile hunk | `git am` 后 tree hash 与 `commits.env` 一致 |
| 3 | `scripts/bootstrap.sh:28-48` | 改用 iw 仓库/分支/SHA + `git am base/*.patch` + tree hash 断言 + `target/linux/sanechips` 存在断言 | 黑盒：新树可重复生成同一 tree hash |
| 4 | `scripts/bootstrap.sh:62-79` | feeds 改 `immortalwrt/packages` + `immortalwrt/luci`（`--depth 1 --single-branch` 保留）；routing/telephony/video 仍由 apply.sh 注释掉 | `./scripts/feeds update/install -a` 成功 |
| 5 | `scripts/bootstrap.sh:84-103` | defconfig 双重执行与断言保留；汇总实际 `CONFIG_USE_APK`/`CONFIG_PACKAGE_apk-openssl` | 断言 `TARGET_DEVICE=sanechips_generic_DEVICE_zte_zxhn-e2631`、luci、e2631-fwslot |
| 6 | `scripts/apply.sh:13,26,38-48` | 基底校验从「BASE_SHA 等值」改为「BASE_KIND + tree hash / sanechips 目录存在」；wrong-base 拒绝保留 | apply-gate 负例仍拒绝 |
| 7 | `apply.sh:112-117` | 复核 iw `feeds.conf.default` 行格式后调整注释/rm 逻辑 | 无 routing/telephony/video feed 参与构建 |
| 8 | `apply.sh:147-152` | image/Makefile hook 保留 | `Makefile.e2631` 被 include |
| 9 | `apply.sh:154-166` | 保留 mt7915e AutoProbe 删除；**新增**：`PKG_RELEASE:=2` → `:=3`，并断言 PR mt76 补丁存在 | mt76 包重编且补丁生效 |
| 10 | `apply.sh:169-196` | VFP/NEON 关闭逻辑保留 | 断言不出现 VFP 符号 |
| 11 | `apply.sh:200-224` | CMDLINE（mtdblockN 计算）保留 | 断言 CMDLINE 含 root=/dev/mtdblockN |
| 12 | `apply.sh:230-267` | 通用 config 翻转保留（iw 符号已核对一致） | 断言 detectors 关闭 |
| 13 | `apply.sh:268-287` | FFE opt-in 保留 | 默认关闭可构建 |
| 14 | `apply.sh:289-297` | slotpart 配置保留 | 断言 CONFIG 生效 |
| 15 | `apply.sh:317-333` | 孤儿补丁扫描保留（依赖 `git ls-files`，base patch 必须以提交形式落位） | 无孤儿补丁警告 |
| 16 | `apply.sh:335-394` | 结构断言保留，新增：436 backport 存在、iw 基底版本断言 | make check 的 g_apply 通过 |
| 17 | overlay 删除 | 删除 `overlay/package/luci/luci-theme-argon/`（107）与 `luci-app-homeproxy/`（43）；同步 NOTICE/notice-check/secret-allowlist/Makefile.e2631:44-46 注释 | notice-check 与 secret-scan 通过 |
| 18 | `seed/e2631.config:46` | 决策 `libustream-mbedtls`（现显式 =y）vs iw 默认 `libustream-openssl`；建议保留 mbedtls 并验证 apk-openssl 共存 | 构建无冲突、在线更新可用 |
| 19 | `seed/e2631.config` | 核对 iw feeds 包名（homeproxy/sing-box/smartdns/nlbwmon/upnp/wol/adblock-fast/ttyd 等）；`dnsmasq-full` 默认带来的体积 | defconfig 无 unknown package |
| 20 | `.github/workflows/firmware.yml:44-51` | SOURCE-INFO 增补 iw SHA、base tree hash、patch sha256 | 产物元数据可追溯 |

**T2 验收定义（Definition of Done）**：

1. `make bootstrap` + `make apply` 在干净树可重复成功（tree hash 稳定）；
2. GitHub Actions 一轮 `make world` 成功，镜像产物生成且 `tools/verify_img.mjs` 通过；
3. `make check` 全绿（含 g_apply / g_dts / g_notice / g_secret / g_upgrade / g_preflight）；
4. `target/linux/sanechips` 104 文件、kernel 6.18.60；同包名只构建一份（argon/homeproxy 来自 feed）；构建日志无 unknown symbol / unmet dependency；
5. rootfs squashfs 体积在 17 MiB 窗口内并记录余量；
6. SOURCE-INFO 记录完整（iw SHA + tree hash），且 `Hardware tested: NO` 保持诚实；
7. 不修改 `/etc/e2631-version` 品牌（留给 T3）；不推送正式 Release。

### 6.2 T3：品牌 / 版本 / 产物 / 更新链

- 用户决策项：`/etc/e2631-version` 写什么（`OpenWrt vX` vs `ImmortalWrt vX`）；产物前缀是否改 `e2631-immortalwrt-*`（影响 5 处，见 §4.3）。
- `e2631-upgrade:28` REPOSITORY 默认改为本 fork；`:37` API 与资产名保持约定；改后需用测试模拟一次检查与一次升级判断（不真刷）。
- 统一 `firmware.yml:16-18` 的 `E2631_VERSION`（当前 v1.4 与仓库 v1.9.0 脱节）；`BUILD.md:137` 同步。
- 修正 `image/Makefile.e2631:77` 的 `--header-at` 与 §4.5 其余常量（T3 主体）；`slotpart.c:147` 默认值一并统一。
- Release 正文模板：标注基底（iw SHA + patch tree hash）、kernel 6.18.60、未做真机验证（除非 T5 提供）。
- **推送/Release 前需用户批准**。
- 实施状态（2026-11-14）：T5 CI 端到端构建通过（run 43547631478 @ 5d542c5，publish=false，无 Release）；产物 `e2631-immortalwrt-experimental.bin` 22,020,628 B，sha256 `66805b26…`；镜像内 libustream 为 openssl 变体（mbedtls 仅作为包构建，未入镜像）。品牌 `ImmortalWrt v1.10.0`、`E2631_VERSION` 同步、产物 `e2631-immortalwrt-*.bin` 已由 T3 落地；更新链默认仓库 `QC3284/zte-e2631-immortalwrt`，标签剥离后按数字比较（OpenWrt v1.9.0 → ImmortalWrt v1.10.0 可原地升级，测试见 `tests/test_upgrade.py`）。
- **实施细节与证据**：见 [t3-packaging-release-ci.md](t3-packaging-release-ci.md)（产物/版本口径、原厂网页升级的形状限制、更新链加固与镜像白名单修复、CI `publish` 开关与 SOURCE-INFO、host 模拟 30 项与静态检查 39 项、仍需 CI/真机证明的清单）。

### 6.3 T4：文档 / 门禁 / 长期维护

- 文档改写清单：`README.md:4,76-77,95`、`README.en.md:20-21,50,87,192`、`BUILD.md:35-39,137`、`docs/architecture.md:13,47`、`docs/known-issues.md:256-264`、`docs/updates.md:37-38`、`.env.example:19-21`、`seed/e2631.config:110-112`、`tests/test_upgrade.py`、`tests/test-slot-decisions.c`；`board/firstboot-openwrt.txt:4` 保留。
  **实施状态**：以上文档已改（T4）；`.env.example` / `seed/e2631.config` 由 T2 改；测试字符串改为 `ImmortalWrt v1.10.0`，并新增「OpenWrt v1.9.0 → ImmortalWrt v1.10.0」过渡用例与「两个前缀都判 ID_OURS」用例。
- 新增门禁：**g_layout**（跨文件一致性：verify_img / release.mjs / Makefile.e2631 / DTS / preflight 的 KERNEL_AT、ROOTFS_SPAN、HEADER_AT 必须一致）与 **base-pin**（bootstrap 的 iw SHA + tree hash 断言进入 make check，而不只在 bootstrap 里）。
  **实施状态**：`scripts/layout-check.sh`、`scripts/base-pin-check.sh` 已入 `scripts/check.sh`；base-pin 在 `base/commits.env` 缺失且曾入库时会 FAIL（防静默删除），`E2631_BASE_KIND=legacy` 或尚无基底树时 SKIP 77。
- 本文档由 T4 接手维护：基底升级流程写成 runbook（生成 patch → 更新 commits.env → 更新 tree hash → 全量门禁）→ 见 §8。
- 新增 `docs/` 索引/链接（若仓库有 docs 列表）→ 见 `docs/README.md`。

### 6.4 T-12：树 fork 迁移（2026-11-14）

- **决策**：设备支持不再以 overlay + patch series 形式随套件分发，而是改为
  [QC3284/immortalwrt](https://github.com/QC3284/immortalwrt) 的 `e2631` 分支上的真实提交
  （4 个 sanechips 移植提交 + 3 个 E2631 提交，作者信息保留）；本仓库只做钉死、检出、构建、
  打包、发布与在线更新验证。
- **删除**：`overlay/`（79 文件）、`base/`（4 个 patch + `commits.env` + README）、
  `apply.sh`、`overlay-removed.txt`、`wsl/apply-gate.sh`，以及 `Makefile` 的 `apply` 目标；
  `legacy`（旧 OpenWrt sanechips 基底）通道一并退役。
- **保留/新增**：`scripts/pins.env` 成为唯一钉文件；`tests/native/` 保存树 fork 中
  host 测试要编译/运行的源码副本，`g_native_sync` 在 bootstrap 后逐字节比对并打印同步命令；
  `layout-check.sh` / `base-pin-check.sh` 改为「套件 + 树 fork」双侧检查。
- **新增/修复的构建可复现性项**：P5 kernel build id 由 seed 钉死；P6 make-world 步骤剥离
  `GITHUB_REF_NAME`/`GITHUB_SHA`，构建后断言 miniupnpd banner 不再带构建 ref；P7 feed 以
  branch checkout + `reset --hard` 到钉死 commit（修复 LuCI version.uc 的 detached 标记）；
  P8 可选 `use_pinned_apk_key`（secret `E2631_APK_PRIVATE_KEY`，只写入构建树并 always 删除）。
- **钉值演进**：T-12 时树 fork tip 钉为 `e96aed31…`（CI-only 提交不改变镜像，不 bump pin）；
  T-20（2026-11-14 主线质量修复系列）落地后重新钉到 `83df1a9…`；批次 2（2026-11-15：
  marker 加固 + SPDX + fwslot 字符串拼接）再钉到 `cd14ffa…`，见 T-20 与批次 2 记录；
  R 系列（2026-11-15 把 ImmortalWrt master `a4ba8240` merge 进 e2631）后钉到 `3ac18fb9…`，
  task-31（2026-11-20 把 firewall4 fullcone 补丁按上游 3722eadc 重锚，仅该补丁文件变化）再钉到 `5202d4ca…`，
  树内容从此同时包含合并进来的上游 master 侧提交；`E2631_IW_SHA=4765b657…` 保留为
  port 系列之下的祖先锚点（不再代表镜像的唯一上游内容）；SOURCE-INFO 随之增加一行
  `Merged ImmortalWrt master: @ a4ba8240… (2026-11-14)`（钉值记在 `scripts/pins.env`）；
  `ImmortalWrt v1.10.0` / `e2631-immortalwrt-*` / 在线更新仓库口径不变；正式 Release 与真机
  刷写仍需用户批准。
- **验证**：本地 `make bootstrap` + `make check` 全绿；CI `check.yml` 在推送分支上运行
  `host/sim-upgrade.mjs`（30 项）、`tools/check-workflows.mjs`（66 项）与 `make check`。

## 7. 证据与未决问题

### 7.1 关键证据索引

| 结论 | 证据位置 | 值 |
| --- | --- | --- |
| iw master 钉死点 | commit `4765b657625ec5bbda74b44400465fe043802b30` | 2026-11-05T04:06:13Z |
| iw kernel 版本 | `target/linux/generic/kernel-6.18:1-2` | `LINUX_VERSION-6.18 = .60`；hash `3c2f44ef...` |
| iw apk 默认 | `config/Config-build.in:71-72` | `USE_APK` default y，imply `apk-openssl` |
| iw 品牌默认 | `include/version.mk:38-39,29-30,35-36` | ImmortalWrt / SNAPSHOT / downloads.immortalwrt.org/snapshots |
| iw feeds | `feeds.conf.default:1-5` | packages+luci=immortalwrt/*，routing/telephony/video=openwrt/* |
| iw 默认包集差异 | `include/target.mk:28,53,62-63,108,115,319` | libustream-openssl / dnsmasq-full / tweak 被注释 / partx-utils / GPIOLIB |
| 基底 PR 头 | `db8b8d4130457dbe46558a7cea872dd2dae539e6` | 2026-10-12T17:14:44Z，kernel 6.18.55 |
| 基底父提交 | `936617ab598e` | iw master 祖先（ahead 6049 / behind 0） |
| 4 提交 | `fbf76e3c` / `773fd136` / `36754bf5` / `db8b8d41` | 1 / 2 / 46 / 10 文件 |
| 028 前置 | iw `target/linux/generic/backport-6.18/436-v7.3-mtd-spinand-add-support-for-HeYangTek-HYF1GQ4UDACAE.patch` | 提供 `drivers/mtd/nand/spi/heyangtek.c` |
| mt76 pin | `package/kernel/mt76/Makefile:4,11,12` | `PKG_RELEASE:=2`、2026-10-28、`0936617d...` |
| fstools pin | `package/system/fstools/Makefile` | `907cf449...`、2026-10-18、PKG_RELEASE 1 |
| argon feed 版 | iw `themes/luci-theme-argon/Makefile:10,13-15` | 3.1.3 / 20261106 / provides luci-app-argon-config |
| argon overlay 版 | `overlay/package/luci/luci-theme-argon/Makefile:11,13,14-15,18-26,28-33,35-37,39` | 3.1.0 / 20261022 / 额外 flock+coreutils |
| homeproxy 运行时一致 | `cmp` 三处：init.d/homeproxy、homeproxy.uc、homeproxy.js | 无差异 |
| 版本文件 | `overlay/.../base-files/etc/e2631-version:1` | T1 时为 `OpenWrt v1.9.0`；现为 `ImmortalWrt v1.10.0` |
| 更新链 | `.../base-files/sbin/e2631-upgrade:28,37,42-60,127-146` | 默认仓库 `QC3284/zte-e2631-immortalwrt` / GitHub API / 数字比较（剥标签）/ 降级保护 |
| CI | `.github/workflows/firmware.yml:12,16-18,41-43,44-51` | 150 分钟 / E2631_VERSION `ImmortalWrt v1.10.0` / 产物 `e2631-immortalwrt-*.bin` / SOURCE-INFO 含基底 pin |
| 几何真值 | `tools/verify_img.mjs:290`、DTS `zte,hdr-delta`、`host/release.mjs:52` | 0x400000 / 0x1100000 / 0x1500000 |
| overlay 总量 | overlay 目录文件总数（find -type f 计数） | 229 |
| target 合并 | 基底 55 + overlay 新增 49 | 104，覆写 4 |

### 7.2 未决问题（需 Lead / 用户决策）

1. **品牌与版本号**：`/etc/e2631-version` 与 CI `E2631_VERSION` 写 OpenWrt 还是 ImmortalWrt？→ **已决**：`ImmortalWrt v1.10.0`（用户决定，2026-11-14）。
2. **推送与 Release 授权**：T2 需推送到 QC3284 仓库以触发 Actions；T3 发布 Release。→ **已决**：允许推非 main 测试分支触发 `check.yml`；正式 Release 仍需用户批准。
3. **argon/homeproxy 取舍**：是否接受使用 iw feeds 版本（推荐）？→ **已决**：接受 iw feeds 版，overlay 自带 150 个文件已删除（提交 `819af6c`），同名的 NOTICE / notice-check / secret-allowlist 同步由 T4 完成。
4. **legacy 并行周期**：T2 完成后是否保留旧基底通道一个版本周期（推荐保留）还是立即删除？→ **已决并已退役**：先保留到 T5；T-12 树 fork 迁移时删除 `E2631_BASE_KIND=legacy` 与 `apply.sh`，旧基底只留 `scripts/pins.env` 里的 provenance 哈希。
5. **真机验证**：T5 的刷写/回退验证需用户批准并安排时间；T2/T3 不碰设备。→ **未决 / 待安排**：T5 先做 CI 端到端 + 设备只读取证，刷写另行批准。
6. **产物前缀**：`e2631-openwrt-*` 保持不变还是改 `e2631-immortalwrt-*`？→ **已决**：改 `e2631-immortalwrt-*`。

### 7.3 调研边界与复现命令

- 只读：未修改任何源码；未执行任何构建；未推送；未刷写。本文是唯一新增文件（T1 交付物）。
- 2026-11-14 GitHub REST core 配额用尽后改用 raw；如复现时 API 可用，等价命令：`gh api repos/immortalwrt/immortalwrt/commits/master`、`gh api repos/Zlion-Y/openwrt-sanechips-mirror/commits/db8b8d4`、`gh api repos/immortalwrt/immortalwrt/compare/936617ab...master`。
- raw 复现：`curl -s https://raw.githubusercontent.com/immortalwrt/immortalwrt/4765b657625ec5bbda74b44400465fe043802b30/target/linux/generic/kernel-6.18` 等（SHA 固定即可复现）。
- 内核补丁测试：`git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/<path>?h=v6.18.60` 逐文件下载后 `patch -p1 -F3`；脚本与清单在 /tmp，未入库。
- **本决策的证据以本文与 /tmp 采集件为准；进入 T2 后应以 CI 构建日志作为最终证据。**

## 8. 基底升级 runbook（T-12 维护）

触发条件：ImmortalWrt 钉死点需要前移（安全更新 / kernel 小版本 / sanechips 相关上游改动），
或树 fork 需要重放到新基底。原则不变：**本机不做全量编译，最终证据来自 CI；刷写与 Release
需用户批准。**

1. **定新钉点**：确认 `immortalwrt/immortalwrt` 新 commit（`gh api repos/immortalwrt/immortalwrt/commits/master`
   或 raw 固定 SHA），记下新 SHA 与 `target/linux/generic/kernel-6.18` 的 `LINUX_VERSION-6.18`。
2. **在 fork 工作副本上重放**：把 `QC3284/immortalwrt` 的 `e2631` 分支重放到新上游 SHA，
   保留 4 个 sanechips 移植提交（作者/提交信息不变）与 3 个 E2631 提交；**不要新造 patch 文件**，
   也不要手改提交文本（历史本身就是被审查的对象）。
3. **重算钉值**：新 `E2631_IW_SHA`、`E2631_IW_TREE_SHA`（新上游的 pristine tree）、
   `E2631_BASE_TREE_SHA`（最后一个 sanechips 移植提交的 tree）、`E2631_BASE_KERNEL`；
   若 fork 内容变化，新 tip 成为候选 `E2631_FORK_SHA`（只有内容变更才 bump，CI-only 提交不 bump）。
4. **更新 `scripts/pins.env`**：唯一钉文件（原 `base/commits.env` 已随 `base/` 删除）；
   `scripts/env.sh` 自动读取，无需改代码。
5. **本地门禁**：`make bootstrap`（depth-1 构建树 + scratch repo 历史断言）然后 `make check`。
   base-pin/base-tree 会复核 tip、`4f89aa7a` 在历史中、ImmortalWrt 钉的祖先关系、恰好 4 个移植
   提交、设备文件与 feed 钉；g_layout 与基底无关、应保持全绿。
6. **CI 预检**：推**非 main** 测试分支触发 `.github/workflows/check.yml`（bootstrap → make check
   两阶段），确认 scratch repo 断言在实际 CI checkout 上也成立。
7. **全量构建**：手动 dispatch `firmware.yml`（上限 150 分钟，`publish=false`），验证 kernel 编译、
   target 补丁、产物过 `verify_pkg` / `verify_img`；需要发布时再单独走 `publish=true` 审批。
8. **更新证据**：本文 §0 结论表、§6.4 与 §7.1 的 SHA/kernel 行、`docs/relnotes-*.md` 新版本记录，
   以及 `scripts/pins.env` 顶部的来源注释。
9. **回滚**：`git revert` 该 pins.env 提交即可回到旧钉点（旧值在 git 历史）。T-12 起**没有**
   `E2631_BASE_KIND=legacy` 通道——要回到旧基底需整体 revert 树 fork 迁移。
10. **合入门槛**：CI 全绿 + 产物验证通过后才合 main；正式 Release 仍需用户批准。

---

*本文由 T1（iwrt-baseline）产出；后续维护归 T4。任何结论变更需附新证据并更新 §7.1。*