# R-研1：ImmortalWrt master 差异调研与合并策略（4765b657 → a4ba8240）

- 状态：调研完成（2026-11-15）。只读调研：未构建、未接触真机、未修改树 fork 内容、未推送。
- 交付：本文件（kit `evidence/`，本地 commit，未 push）；英文摘要已通过团队消息发给 Lead。
- 调研对象：树 fork QC3284/immortalwrt 分支 `e2631`（本地 `/home/qc233/zte/iwrt-tree`，tip `cd14ffa091f63116859ae8bd6d262f08778629a8`，worktree clean）与上游 `immortalwrt/immortalwrt` master 的区间 `4765b657625ec5bbda74b44400465fe043802b30..a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5`。

## 0. 结论摘要（TL;DR）

- 区间共 **122 个 commit**：2 个 first-parent（ImmortalWrt 自有 `d42cc475` fullconenat-nft 修复 + `a4ba8240` "Merge Official Source"）+ 120 个 OpenWrt main 侧 commit；内容差异 **284 files, +15,195 / -3,160**。
- **kernel 未变**：6.18.60，`LINUX_KERNEL_HASH-6.18.60` 与 `target/linux/generic/kernel-6.18` 两边逐字节相同；**feeds pin 未变**（feeds.conf.default 0 diff）。
- 我方 `e2631` 相对基线有 18 个 commit、140 个改动文件；与上游 284 个改动文件**只有 1 个交集**：`package/system/fstools/Makefile`。
- **merge 实测 0 冲突**（`git merge-tree --write-tree`，tree `1ff47fed…`），合并结果 = 我方树 + 上游 284 文件差异；7 个钉点 commit SHA 与 `67101828^{tree} = 4f89aa7a…` 全部保持，树 CI 继续全绿。
- **rebase 实测 0 文本冲突**（18/18 全部重放成功），但 **18 个 commit SHA 全变**、H3600 的 tree 变为 `f07333ee…` ≠ `4f89aa7a…`，违反 README 的 never-rewrite 约定，并级联要求重钉 CI/kit/docs → **不推荐**。
- **推荐 merge**；**seed 无需增删符号**；合并唯一语义点 fstools source bump（907cf449→5e371ec）已验证我方补丁 203/204 仍可套用。
- 需注意的行为回归（无冲突）：mac80211 PKG_RELEASE 12→14（WiFi 修复）、ppp/firewall4/uhttpd/procd/hostapd 更新；合并后需 build + 真机回归。

## 1. 区间事实

采集方式：2026-11-15 12:28 CST，在 `/home/qc233/zte/iwrt-tree` 执行 `git fetch upstream master`；`FETCH_HEAD == refs/remotes/upstream/master == a4ba8240…`（采集时无更新）。

| 项目 | 结果 |
| --- | --- |
| 上游 | `immortalwrt/immortalwrt` master |
| 基线 | `4765b657625ec5bbda74b44400465fe043802b30`（2026-11-05 12:06:13 +0800，kernel 6.18.60） |
| 目标 | `a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5`（2026-11-14 11:42:48 +0800，"Merge Official Source"） |
| commit 数 | 122 = 1 merge + 121 non-merge（其中 120 OpenWrt main + 1 ImmortalWrt 自有 `d42cc475`） |
| first-parent | 2（`d42cc475` → `a4ba8240`；再往前是基线 4765b657） |
| merge-base | `4765b657`（a4ba8240 的 first-parent 链含基线，故基线是目标 tip 的祖先） |
| 内容差异 | 284 files changed, 15,195 insertions(+), 3,160 deletions(-) |
| kernel | 未变：6.18.60；hash `3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e` 两边一致 |
| feeds pin | 未变：`feeds.conf.default` 0 diff |
| 机制文件 | `include/`、`rules.mk`、`package/Makefile`、`include/kernel-defaults.mk`、`include/toplevel.mk`、`config/`、`.github/` 均 0 变化 |

首个 first-parent commit：`d42cc475c60e12a2031d0f39c02e7a265458eb56` "fullconenat-nft: honour the port range and the flags"（ImmortalWrt 自有，新增 `package/network/utils/fullconenat-nft/patches/011-honour-port-range-and-flags.patch` + Makefile bump；我方未使用 fullconenat，无影响）。

**shallow 说明**：本地 fork 原为 shallow clone，`4765b657` 是 shallow 边界；未 unshallow 时 `git rev-list 4765b657..a4ba8240` 会得到 72,716 的假象（把 openwrt 完整历史算进来）。本次执行 `git fetch --unshallow origin` 补齐祖先（`.git` 348M → 516M，worktree 未动），以下计数/祖先关系均为补齐后实测。

## 2. 逐类差异清单 + 是否触及我方文件

“我方文件” = 树 fork `e2631` 相对 `4765b657` 的 140 个改动文件（18 commits）。

| 类别 | 文件数 | 主要内容 | 触及我方文件 |
| --- | --- | --- | --- |
| `target/linux` 其它 target | 180 | rockchip 40、realtek 35、ath79 32、mpc85xx 24、qualcommax 19、airoha 7、bcm27xx 5、ipq40xx 4、mvebu 3、mediatek 3、qualcommbe 2、ipq806x 2、qoriq/layerscape/imx/bcm53xx 各 1 | 否（sanechips 只存在于我方 fork） |
| `target/linux/generic` | 13 | net/sfp 750–753 + 757、net/phy 801-01/896-03/802-03/04、net/usb phy 802-01/02、wireguard 792、dma_buf 904 | 否；与 028–034 目标文件（mtd/spi-nand/jffs2/PCI quirks/mtd parsers/zte net/arch-arm/dwc3）无重叠，且 kernel 6.18.60 未变 |
| `package/kernel/mac80211` | 53 | ath11k 新增 14+、ath12k、subsys 485–490、build/160 更新；PKG_RELEASE 12→14，PKG_SOURCE_VERSION 7.2 不变 | 否（文件不重叠）；但属 WiFi 行为变化 |
| `package/kernel` 其它 | 0+* | r8125/r8126/r8127/r8168 Makefile+patches；`modules/{input,netdevices,video}.mk`；**`usb.mk` 未动** | 否；6cf5f6d7 的 DWC3 KernelPackage 块无冲突 |
| `package/network` | 15 | ppp（patches/init）、firewall4、hostapd（ubus.c）、uhttpd（config/init）、umbim、fullconenat-nft | 否；PPPoE/防火墙/Web 行为更新 |
| `package/system` | 5 | fstools Makefile（**唯一交集**）、procd 1→2、hardware-support 2→3 | **fstools 见 §4** |
| `package/base-files` | 1 | `files/lib/functions.sh` 新增 `path_normalize()` | 否（新增函数，现有调用不变） |
| `package/boot` / `firmware` / `utils` / `tools` | 6 / 1 / 3 / 8 | uboot/tfa、ipq-wifi、cmake/ccache/libressl/fakeroot | 否 |
| 删除 | 15 | ath79 10、mvebu 2、qualcommax 1、tools/cmake 2 | 否（不在我方路径） |
| 合计 | 284 | | |

\* 注：`package/kernel` 合计 53，其中 mac80211 占绝大多数，其余为 r812x/r8168 与三个 modules.mk。

## 3. 我方机制逐项判定

| 我方机制 | 上游是否变化 | 结论 |
| --- | --- | --- |
| `include/kernel-defaults.mk:117-119`（CONFIG_KERNEL_* 追加/last-wins） | 未变 | DEVMEM 传递逻辑不变，seed 的 `CONFIG_KERNEL_DEVMEM=y` 继续有效 |
| `rules.mk:355-356` | 未变 | P5/P6 变量口径不变 |
| `package/Makefile:77-78` | 未变 | 不变 |
| `include/toplevel.mk` `SCAN_DEPTH` | 未变 | 包扫描行为不变，`package/e2631/` 扫描不变 |
| `config/Config-kernel.in:1504`（KERNEL_DEVMEM 默认 n） | 未变 | 不变 |
| `config/Config-build.in`（apk / libustream 默认） | 未变 | 包格式 `apk-openssl` 不变 |
| `feeds.conf.default` pin | 未变 | luci/packages 等 feed 解析不变（argon/homeproxy 等由 feeds 提供的版本不动） |
| `target/linux/sanechips`（55 base + 49 fork = 104 文件） | 上游无此目录 | 无冲突 |
| `package/e2631/`、`seed/e2631.config`、`README.e2631.md`、`.github/workflows/check.yml` | 上游均无同名文件 | 无冲突；树 CI 断言见 §4.2 |
| generic backport `436-…HeYangTek…` | 未变（不在 generic 13 文件中） | 补丁 028 依赖不变 |
| `package/kernel/mt76` | 0 变化 | `PKG_RELEASE:=3`、补丁 001/002、PKG_SOURCE_VERSION 0936617… 继续有效 |
| 树 CI（`E2631_IW_SHA`=4765b657、`E2631_PORT_TREE_SHA`=4f89aa7a） | 未变 | merge 后继续通过（见 §4.2）；rebase 后必红（见 §4.3） |

## 4. merge vs rebase 冲突预测与推荐

### 4.1 实测方法

工具：git 2.56.1。全部在树 fork 上做**不写 worktree** 的模拟：

- **merge 模拟**：`git merge-tree --write-tree refs/heads/e2631 a4ba8240…` → exit 0，tree `1ff47feda9e321ef796d513c0ffcbd6f58e860b7`，输出无冲突行；合并结果树相对 `refs/heads/e2631` 的 diff = 284 files, +15,195/−3,160（与上游区间完全一致）→ 我方 140 文件改动逐字节保留。
- **rebase 模拟**：在 `/tmp/iwrt-rebase-sim`（`git clone --shared`，源仓库只读）中 `git rebase a4ba8240…` → 18/18 成功（"成功变基"），0 文本冲突，但 18 个 commit SHA 全变；H3600 的 commit 变为 `9ca857a3c07a10545a7813ec2daa2a39246c0072`，其 tree `f07333ee09235440a02a09ee05cca8e9cfc84a0f` ≠ `4f89aa7ad0a5132dc047a27a9073b43916f0f957`。

### 4.2 merge 方案（推荐）

- `merge-base = 4765b657`；`git merge --no-ff a4ba8240…` 产生 1 个 merge commit（parent1 = `cd14ffa091f63116859ae8bd6d262f08778629a8`，parent2 = `a4ba8240…`）。
- **不变式全部保持**：7 个钉点 commit 的 SHA 不变（merge 不重写 commit 对象）；`67101828…^{tree}` 实测仍 = `4f89aa7a…`；树 CI 各断言继续通过（E2631_IW_SHA=4765b657 仍是 HEAD 祖先，port-series tree 仍是 4f89aa7a）。
- 合并内容：我方树 + 上游 284 文件差异，不触碰 `target/linux/sanechips`、`package/e2631`、`seed`、`docs`、`.github`（实测合并树相对 e2631 的 diff 中这些路径 0 个文件）。
- **fstools 自动合并结果**（merge tree 内实测）：`PKG_RELEASE:=2`（我方）+ `PKG_SOURCE_VERSION:=5e371ecfa7f6289db816b6ce07da5a039fb0a5c8`（上游）+ `patches/{100,203,204}` 共存。语义验证：`git apply --check` 补丁 203/204 对 fstools 5e371ec 均 rc=0；上游区间 fstools 只多 1 个 commit `5e371ec block: don't log an error when fstab is missing`（不触碰 `libfstools/overlay.c`）。
- 建议实施命令（供后续实施任务使用；本卡未执行）：

```sh
git fetch upstream master
git merge --no-ff a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5 \
  -m "Merge ImmortalWrt master a4ba8240 (2026-11-14) into e2631"
```

- merge 后建议（不属于本卡，需 Lead 排期）：① README.e2631.md 基线表补 "上游追踪" 行（a4ba8240），基线桩仍是 4765b657；② 补丁 203 头注释里的 snapshot 名（2aa16407…）更新到 5e371ec（纯注释，上下文已验证）；③ fstools `PKG_RELEASE:=2` 可保持不变（补丁内容未变；若改补丁再 bump）；④ 可选：树 CI 增加 `E2631_IW_TRACKED_SHA=a4ba8240` 的“已合并/祖先”断言（不改 4f89aa7a 钉，kit `tools/check-workflows.mjs` 的硬编码字符串不受影响）。
- 合并 commit 会进入 `git log --format=%s`，不影响树 CI 的 port subject grep。

### 4.3 rebase 方案（不推荐）

- 0 文本冲突（18/18），但代价：**7 钉 + 2 CI + 9 质量共 18 个 SHA 全变**；`4f89aa7a` 不再可达；违反 `README.e2631.md` 的 never-rewrite 约定（`e96aed31` 及之前的 12 个 commit 不可改写、永不重写；force-push 仅在 Lead 批准且 `--force-with-lease` 时允许）。
- 选 rebase 时 Lead 需同时裁决 re-pin 级联：树 CI `E2631_PORT_TREE_SHA`、`E2631_IW_SHA`（注释里 `HEAD~3` 语义也要改）、kit `base/commits.env` 三钉、kit `tools/check-workflows.mjs` 对 check.yml 的硬编码 SHA 断言、README 基线表、`docs/checkpatch-exemptions.md` 引用、evidence/发布记录。
- 收益仅为“线性历史 + 与新上游 tip 对齐”；merge 后同样可用 `git log`/`git merge-base` 追踪，收益不足以抵消审计与钉点损失。
- rebase 后 4 个移植 commit 的新 SHA 示例：DWC3 `278882868005c5b436d36e2329b69e3a90b7cd92`、mt76 `f57715678be65fe04b2dc6bc0f3df15a865eeba9`、ZX279128S `7268d12f2946226a8943f3e4b18b245286269918`、H3600 `9ca857a3c07a10545a7813ec2daa2a39246c0072`。

## 5. seed 是否需要增删符号

**不需要。** 依据：

- kernel 6.18.60 未变；`config/Config-*.in`、`include/target.mk`、`DEFAULT_PACKAGES`、apk/libustream 默认、feeds pin 全部未变；`package/base-files` 仅新增 shell 函数。
- `seed/e2631.config` 保留 `CONFIG_KERNEL_DEVMEM=y`（树 CI 已静态断言；`include/kernel-defaults.mk:117-119` 的 last-wins 传递机制未变）。
- 验证方式：合并后树 CI 的 `make defconfig` + `CONFIG_TARGET_sanechips`/`DEVICE_zte_zxhn-e2631`/`CONFIG_KERNEL_DEVMEM=y` 断言应继续通过；kernel 未变，不应出现新的必选项。

## 6. 风险与合并后回归观察

- **无冲突但有行为变化**（合并后需 build + 设备回归）：
  - mac80211 `PKG_RELEASE 12→14`：subsys 485–490 等 WiFi 修复 + ath11k/ath12k 补丁 → 重跑 WiFi 冷启动/关联/双频/吞吐矩阵（这是本区间最可能与 MT7916 行为相关的部分）；
  - ppp（patches/init）、firewall4、uhttpd（config/init）、hostapd（ubus.c）、procd 1→2 → 重跑 PPPoE、WAN 访问策略、Web/SSH 回归；
  - hardware-support 2→3（video/DMA-BUF 组）→ 对无显示的 E2631 无影响；
  - `base-files/files/lib/functions.sh` 新增 `path_normalize()` → 现有调用不受影响。
- **无风险**：kernel/驱动（6.18.60 同 hash）、sanechips target、设备包、seed、镜像配方/几何、CI 文件（0 变化）。
- 合并后建议链路（不在本卡范围）：merge → docs 记录 → 树 CI 绿 → kit re-pin 到 merge commit（`base/commits.env`）→ Actions 构建 → parity（RUN1==RUN2）→ 真机回归（WiFi/PPPoE/IPv6/slot0/upgrade）。
- 本地仓库状态：树 fork worktree 开工/收工均 clean；本次只做 fetch/unshallow 的 `.git` 元数据变更（新增 `upstream/master` ref、移除 shallow 记录），不改分支、不推送。

## 7. 证据摘要（可复现）

- 采集：`git -C /home/qc233/zte/iwrt-tree fetch upstream master`；`git rev-parse upstream/master` = `a4ba8240…`（2026-11-15 12:28 CST，无更新）。
- 计数：`git rev-list --count 4765b657..a4ba8240` = 122；`--first-parent` = 2；`--merges` = 1；`--no-merges` = 121。
- 差异：`git diff --shortstat 4765b657 a4ba8240` = `284 files changed, 15195 insertions(+), 3160 deletions(-)`。
- kernel：`git show <rev>:target/linux/generic/kernel-6.18 | head -2` 两边相同（`.60` / `3c2f44ef…`）。
- feeds：`git diff 4765b657 a4ba8240 -- feeds.conf.default` 为空。
- 机制：`git diff --name-only 4765b657 a4ba8240 -- include/ rules.mk package/Makefile config/ .github/` 为空。
- merge：`git merge-tree --write-tree refs/heads/e2631 a4ba8240…` → tree `1ff47fed…`（exit 0，无冲突）；合并树内 fstools Makefile 见 §4.2。
- rebase：`/tmp/iwrt-rebase-sim` 中 `git rebase a4ba8240…` → "成功变基"（18/18）；`git log --format='%H %T %s'` 显示 H3600 tree = `f07333ee…`。
- fstools：对 `/tmp/fstools-new@5e371ec` 执行 `git apply --check` 补丁 203/204 → rc=0；`git log 907cf449..5e371ec` 仅 1 个 commit。
- 树 fork 分支：`git rev-list --count 4765b657..refs/heads/e2631` = 18；tip `cd14ffa091f63116859ae8bd6d262f08778629a8`；作者 4×Navid Ghahremani + 14×e2631 tree fork。

### 7.1 树 fork `e2631` 当前 18 个 commit（相对 4765b657）

| # | SHA | subject | 分组 |
| --- | --- | --- | --- |
| 1 | `6cf5f6d79fe5eb30323c8a5e6d5ddce286aa60e6` | kernel: add generic DWC3 platform glue package | 钉点（移植） |
| 2 | `35270f0cbd4b19d499a0c53d9b059f7a5f05a901` | mt76: serialize device reads with outer cache maintenance | 钉点（移植） |
| 3 | `a6c473093d9c59279de2e5ca05c02289672c9498` | sanechips: add ZX279128S target | 钉点（移植） |
| 4 | `671018283968a42db5a64bcf919daa66f8ea0901` | sanechips: add support for ZTE ZXHN H3600 | 钉点（tree=4f89aa7a…） |
| 5 | `f2d03c4ae06ce52e36e6dba8bb38746bedecd1f8` | sanechips: add ZTE ZXHN E2631 board support | 钉点 |
| 6 | `8a253ea8a4558e2eb78fa59fc528982332aff066` | e2631: add the E2631 device packages | 钉点 |
| 7 | `e96aed31c45442374e9a37fd84c1ac048be90613` | e2631: add the image seed and build notes | 钉点 |
| 8 | `8a06f471f19d34eb41fc71097f3884365c18c057` | ci: add a static tree gate for the e2631 branch | CI-only |
| 9 | `3dbeadcedf00fa2de42e0455303516bc6cb2b0d0` | ci: use actions/checkout@v5 (node24) in the tree gate | CI-only |
| 10 | `f3776b32a51879557bd0c51c67ccf22c004646d7` | e2631: gate the userdata extroot on a snapshot marker | 质量 |
| 11 | `76dcaee7e82786b7370addba695a7f5a23f887f3` | e2631: keep SSH and HTTP(S) off the WAN by default | 质量 |
| 12 | `72eff3b70611f20808941964cdfa2054770f4cb1` | e2631: skip the fstools jffs2 sync when there is no upper | 质量（fstools 补丁 204） |
| 13 | `6b609d7ee46dc0b1c46d098b74c22606ac88fafc` | e2631: request CONFIG_DEVMEM where it is decided (seed + tree CI) | 质量 |
| 14 | `b2e15d46b917aaff7a20f37d593734271a5237ab` | e2631: clean up coding style in the tree files | 质量 |
| 15 | `83df1a90a71863c2f54d6e399e8b0ee86405083a` | docs: record the e2631 history rewrite and force-push rules | 质量（docs） |
| 16 | `4b610dc53bbbe16cd99e7aa7b7b31932b059a38d` | e2631-userdata: never write or accept an empty snapshot marker | 质量 |
| 17 | `235fe12536dd2209f050f21beb6b270ecd796750` | e2631: add the missing SPDX tags to the target scripts | 质量 |
| 18 | `cd14ffa091f63116859ae8bd6d262f08778629a8` | e2631-fwslot: put each split user-visible string on one line | 质量（tip） |

## 8. 范围声明

- 本卡为只读调研：未构建（本机弱、禁止全量编译）、未接触真机、未 push、未修改树 fork 内容。
- 唯一写入 = 本证据文件（kit `evidence/`，本地 commit，不 push）；merge/rebase 均只在内存/临时 clone 中模拟，未在树 fork 上执行。
