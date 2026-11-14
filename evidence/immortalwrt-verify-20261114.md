# T5：ImmortalWrt 适配的端到端构建与产物验证（2026-11-14）

本文件是 task-5 的证据报告：ImmortalWrt 基底切换后的门禁、CI 构建、产物校验与在线更新模拟。
状态：**本地 / 静态门禁已全部通过**；**CI 全量构建与产物校验已通过**（证据 run 43547631478，见第 4、5 节）。
真机刷写与启动验证明确不在本文件覆盖范围内（需用户批准，见第 7 节）。

## 1. 结论（截至本文件创建时）

- 本地可验证的 13 个门禁在 **immortalwrt 模式 + 真实 bootstrap 树** 下 13/13 PASS，0 FAIL、0 SKIP；在证据 HEAD `5d542c5` 上复跑同样全绿（命令见第 3 节）。
- `check.yml` 在 `aabf0b4`、`23e1323`、`09e2f92`、`73ac520`、`5d542c5` 五次运行全绿（run id 见第 3.7 节）。
- **CI 全量构建成功**：`firmware.yml` dispatch（`publish=false`）run **43547631478** @ `5d542c5`，`completed / success`，1h21m07s；`Publish only after all build and artifact gates pass` 步骤 **skipped**，**未创建 Release**（第 4 节）。
- **产物校验通过**：下载产物 sha256 与 `SHA256SUMS` 一致；`host/verify_pkg.mjs` 33 项 PASS（1 个预期 WARN）；`tools/verify_img.mjs` 输出 `BOOT-READY: no static blocker found`；两项均在 CI 构建目录与宿主机下载产物上各跑通一次（第 5 节）。
- 真机刷写 / 启动 / 硬件功能验证：**未覆盖**，需用户批准后另行安排。

## 2. 输入与钉点

| 项 | 值 |
|---|---|
| 仓库 | `QC3284/zte-e2631-immortalwrt`（fork） |
| 证据构建提交 | `5d542c5`（`build: collect immortalwrt-* sysupgrade images too`；父提交 `73ac520`，再父 `09e2f92`、`23e1323`） |
| 基底模式 | `E2631_BASE_KIND=immortalwrt` |
| ImmortalWrt 分支/提交 | `master` @ `4765b657625ec5bbda74b44400465fe043802b30`（kernel 6.18.60） |
| ImmortalWrt 原始 tree | `340ae5426d1c8dfa071e97f08993393b87a47671` |
| `base/0001` sha256 | `669f41e436c258d2982dc5998efe82ae54230fbfaa0c1cd60fd148d067c07ffc` |
| `base/0002` sha256 | `a512521bd8ae6dba12b44e989e1a6554e0ed0dd21e769dd453a6fafb5a472dcf` |
| `base/0003` sha256 | `67280d1b531b0a9734f1083b527f933a47c68711b5d0d9820bc38c2bba2dc4d7` |
| `base/0004` sha256 | `8f4b2eee62d23f7be0923d742b7eb32fcb207ee936fcac20296020f769490035` |
| git am 后 base tree | `4f89aa7ad0a5132dc047a27a9073b43916f0f957` |
| 打包 feed | `https://github.com/immortalwrt/packages.git` @ `decf94639ffd6ddd26591c190b547c6b7eea150b` |
| LuCI feed | `https://github.com/immortalwrt/luci.git` @ `ad75cde88e694b511100576bfbe0a280e5efe6ef` |
| 本地 bootstrap 树（本机证据） | `/home/qc233/e2631-t2/tree-iw`，HEAD `51798f6`，tree `4f89aa7a...`，`target/linux/sanechips` 共 104 个文件 |
| 本机门禁环境 | `E2631_BASE_KIND=immortalwrt E2631_TREE=/home/qc233/e2631-t2/tree-iw E2631_OUT=/home/qc233/e2631-t2/out-iw` |

## 3. 本地门禁证据

### 3.1 make check（immortalwrt 模式，13/13 PASS）

```
upgrade failure paths (python)      PASS
apply.sh fail-fast + structural assertions PASS
shell syntax (bash -n)              PASS
javascript (node --check)           PASS
device scripts (busybox ash)        PASS
slot tool (-Werror, parse, reject)  PASS
slot layout constants (5 copies)    PASS
base pin (iw SHA + patch sha256)    PASS
base tree hash (git am result)      PASS
board dts cross-reference           PASS
first-flash preflight (fixture)     PASS
no credential shapes                PASS
NOTICE vs tree (both directions)    PASS
MAKE_EXIT=0
```

2026-11-14 在证据 HEAD `5d542c5` 上复跑同一命令：13/13 PASS，0 FAIL、0 SKIP，`MAKE_EXIT=0`（含 apply gate 与 base tree hash）。

### 3.2 base-pin（static 与 tree 两半）

```
  immortalwrt pin        4765b657625ec5bbda74b44400465fe043802b30 (master, kernel 6.18.60)
  base tree pin          4f89aa7ad0a5132dc047a27a9073b43916f0f957
  0001-kernel-add-generic-DWC3-platform-glue-package.patch sha256 ok (669f41e436c2...)
  0002-mt76-serialize-device-reads-with-outer-cache-maintenance.patch sha256 ok (a512521bd8ae...)
  0003-sanechips-add-ZX279128S-target.patch sha256 ok (67280d1b531b...)
  0004-sanechips-add-support-for-ZTE-ZXHN-H3600.patch sha256 ok (8f4b2eee62d2...)
  tree at E2631_TREE     HEAD^{tree} ok (4f89aa7ad0a5...)
  kernel-6.18 line       LINUX_VERSION-6.18 = .60
base-pin: iw 4765b657... + 4 patches + tree 4f89aa7ad0a5... verified
```

注：`09e2f92` 修掉了本门禁在真实树上才暴露的三个 bug（kernel 后缀比较曾拼成 `..60`；`wsl/apply-gate.sh` 的 legacy 基底假设；apply.sh 104 文件断言在 immortalwrt 模式下的差异）。本文件记录的输出是修复后的结果。

### 3.3 槽位几何（6 份副本）

```
  board DTS          slot1@0x2300000+0x1c00000 rootfs@+0x400000[0x1100000] header@+0x1500000[0x20000]
  tools/verify_img.mjs KERNEL_AT=0x400000 ROOTFS_SPAN=0x1100000 HEADER_AT=derived
  host/release.mjs   --rootfs-at=0x400000 --header-at=0x1500000
  overlay/target/linux/sanechips/image/Makefile.e2631 --rootfs-at=0x400000 --header-at=0x1500000
  scripts/preflight.sh KERNEL_AT=0x400000 ROOTFS_SPAN=0x1100000 HEADER_AT=0x1500000
  overlay/target/linux/sanechips/base-files/sbin/e2631-preflight KERNEL_AT=0x400000 ROOTFS_SPAN=0x1100000 HEADER_AT=0x1500000
layout-check: 0x400000 / 0x1100000 / 0x1500000 agree in every copy
```

### 3.4 apply.sh 门禁（immortalwrt 基底）

```
PASS: apply.sh is idempotent on the real tree (34 dirty paths, report stable)
PASS: a tree that is not the pinned base refuses before touching it
PASS: structural assertions pass on a correct skeleton
PASS: tamper 1/4 - missing base dtsi patch refused
PASS: tamper 2/4 - unhookable image Makefile refused
PASS: tamper 3/4 - unverifiable mt76 AutoProbe state refused
PASS: tamper 4/4 - missing generic config refused
```

### 3.5 槽位与升级决策测试

- `tests/test_upgrade.py`：8 个用例全部通过（含 `OpenWrt v1.9.0 -> ImmortalWrt v1.10.0` 过渡升级按数字比较、降级拒绝、坏哈希拒绝、下载失败路径）。
- 槽位工具单测（`slot tool` 门禁，含 `OpenWrt` / `ImmortalWrt` 两个版本前缀都判为 `ID_OURS`、vendor `V1.0.0.` 判为 `ID_VENDOR`）PASS。

### 3.6 host 侧一致性检查

```
node host/sim-upgrade.mjs      # sim-upgrade: OK - updater behaviour matches the T3 assumptions（30 checks）
node tools/check-workflows.mjs # check-workflows: OK - CI, artifact names, version and release channel agree（40 checks；含 collect.sh 两种镜像名前缀）
```

### 3.7 check.yml（推送分支）

| run | 提交 | 结果 | URL |
|---|---|---|---|
| 43466252355 | `aabf0b4` | success | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43466252355 |
| 43467107138 | `23e1323` | success | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43467107138 |
| 43467532119 | `09e2f92` | success | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43467532119 |
| 43467877734 | `73ac520` | success | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43467877734 |
| 43547551351 | `5d542c5` | success | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43547551351 |

## 4. CI 全量构建（证据 run 43547631478）

命令（Lead 执行；`publish=false`，不产生 Release）：

```
gh workflow run firmware.yml --repo QC3284/zte-e2631-immortalwrt --ref iwrt-adaptation -f publish=false
```

### 4.1 构建历史

| run | 提交 | 结果 | 说明 |
|---|---|---|---|
| 43467705567 | `09e2f92` | cancelled | base-builder 随后提交 `73ac520`（仅 `wsl/apply-gate.sh` 的 apply-gate 报告隔离修复，固件代码不变），Lead 主动取消以保证证据 HEAD = 合并候选；无产物下载，不作证据 |
| 43468042015 | `73ac520` | **failed** | `make world` 成功（2h09m），但 `wsl/collect.sh:41` 只 glob `openwrt-*-sysupgrade*.bin`，而 ImmortalWrt 产物名是 `immortalwrt-sanechips-generic-zte_zxhn-e2631-squashfs-sysupgrade.bin` → “no sysupgrade image to unpack” 退出 1（镜像实际已生成在 `bin/targets/sanechips/generic/`）。Lead 在 `5d542c5` 修复：collect 接受两种前缀 + `tools/check-workflows.mjs` 增加第 40 项检查 |
| 43547631478 | `5d542c5` | **success** | 本文证据 run |

### 4.2 证据 run 元数据

- run：https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43547631478（id 43547631478）
- 提交：`5d542c57bb586d803c25ccb1b288616f9306e21a`（`iwrt-adaptation`，`workflow_dispatch`，`publish=false`）
- 结果：`completed / success`；创建 `2026-11-14T02:40:49Z`，结束 `2026-11-14T04:01:56Z`，总用时 **1h21m07s**
- 关键步骤（GitHub 步骤时间）：
  - `Check source before building`（pre-build make check）：02:41:15–02:41:17 success
  - `Bootstrap pinned ImmortalWrt base`：02:41:17–02:42:22 success（65 s）
  - `Check board references against the base tree`（post-bootstrap make check）：02:42:22–02:42:24 success
  - `Build, package and verify firmware`：02:42:24–04:01:50 success（**1h19m26s**）
  - `Prepare experimental release`：04:01:50–04:01:51 success
  - `Publish only after all build and artifact gates pass`：**skipped**
  - `Retain build logs and release files`：success
- Release：**未创建**（`gh api repos/QC3284/zte-e2631-immortalwrt/releases` 数量 = 0；仓库现有 9 个 tag 均为历史 tag，本次未新增）

### 4.3 产物清单

artifact `e2631-build-43547631478`（artifact id 14097642680，zip 18,769,026 B，`expired=false`，保留 14 天），共 4 个文件：

| 文件 | 大小 (B) |
|---|---|
| `release/e2631-immortalwrt-experimental.bin` | 22,020,628（0x1500214） |
| `release/SOURCE-INFO.txt` | 1,026 |
| `release/SHA256SUMS` | 183 |
| `build-logs/world.log` | 48,645,419 |

下载与复跑位置：`/home/qc233/zte/e2631-t5-artifacts/run-43547631478/e2631-build-43547631478/`（宿主机，未提交）。

`SHA256SUMS` 内容（`sha256sum -c` 两行均 OK）：

```
66805b26afa47b612e535ca0885fd088b0b37461c959fb75212548d30c58294d  e2631-immortalwrt-experimental.bin
e2009d9762f9826e8e6517f14dc3a6d3be061e43ab9d383743b796c55e7f8b16  SOURCE-INFO.txt
```

### 4.4 SOURCE-INFO.txt 全文

```
Kit commit: 5d542c57bb586d803c25ccb1b288616f9306e21a
Base kind: immortalwrt
ImmortalWrt base: https://github.com/immortalwrt/immortalwrt master @ 4765b657625ec5bbda74b44400465fe043802b30
ImmortalWrt tree (pristine): 340ae5426d1c8dfa071e97f08993393b87a47671
Port base tree (4 patches applied): 4f89aa7ad0a5132dc047a27a9073b43916f0f957
Port patch 0001 sha256: 669f41e436c258d2982dc5998efe82ae54230fbfaa0c1cd60fd148d067c07ffc
Port patch 0002 sha256: a512521bd8ae6dba12b44e989e1a6554e0ed0dd21e769dd453a6fafb5a472dcf
Port patch 0003 sha256: 67280d1b531b0a9734f1083b527f933a47c68711b5d0d9820bc38c2bba2dc4d7
Port patch 0004 sha256: 8f4b2eee62d23f7be0923d742b7eb32fcb207ee936fcac20296020f769490035
Kernel: 6.18.60
Packages feed: https://github.com/immortalwrt/packages.git
Packages commit: decf94639ffd6ddd26591c190b547c6b7eea150b
LuCI feed: https://github.com/immortalwrt/luci.git
LuCI commit: ad75cde88e694b511100576bfbe0a280e5efe6ef
Run: https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43547631478
Hardware tested: NO
```

与 `base/commits.env` 逐项一致（IW repo/branch/SHA、pristine tree、4 个 patch sha256、base tree、kernel 6.18.60）；feed 两个 commit 与本地 bootstrap 树记录一致。

### 4.5 world.log 关键行

- 构建日志（CI job log）结束标记：`build: make world done`、`build: images collected into .../out/build-20261114-024224`、`build: package: .../e2631-immortalwrt-20261114-024224.bin`
- 内核镜像名：`ARM ImmortalWrt Linux-6.18.60`；包清单 `manifest immortalwrt-sanechips-generic.manifest: 212 packages`
- 系统镜像文件：`immortalwrt-sanechips-generic-zte_zxhn-e2631-squashfs-sysupgrade.bin`（`bin/targets/sanechips/generic/`），manifest 通过 apk 生成（ImmortalWrt apk-openssl 基底）


## 5. 产物校验

### 5.1 CI 内（构建目录上，job log 摘要：0 FAIL / 102 PASS）

- `host/release.mjs` 打包后自检：`post-write verify: CRC1 ok CRC2 ok kernelCRC ok rootfsCRC ok bodySize ok layout ok derivedFsOff ok slotMarker ok innerMagic ok`
- `host/verify_pkg.mjs`：`ALL CHECKS PASSED (warnings: 1)`（33 项 PASS；唯一 WARN 为 uImage `ih_hcrc` 与标准算法不同，官方镜像同样如此，见 verify_pkg.mjs 的既有判定）
- `tools/verify_img.mjs`：`BOOT-READY: no static blocker found`，随后输出 `ready to flash: .../e2631-immortalwrt-20261114-024224.bin`；覆盖 dtb/分区表/cmdline/驱动内建 config 片段/包清单（212 packages）等检查

### 5.2 宿主机（下载产物上复跑）

- `sha256sum -c SHA256SUMS`：两行均 OK；bin sha256 = `66805b26afa47b612e535ca0885fd088b0b37461c959fb75212548d30c58294d`，与 SHA256SUMS 一致
- `node host/verify_pkg.mjs <artifact> --dts overlay/target/linux/sanechips/dts/zx279128s-zte-zxhn-e2631.dts --template seed/vendor-verhdr-8b8.bin`：`ALL CHECKS PASSED (warnings: 1)`（33 项 PASS；几何 slot+0x400000 / kernel 0x3fffe0 / rootfs 0xc60000 / body 0x1500000，DTS 的 slot1、rootfs、slot1-header 一致）
- `node tools/mkfactory.mjs info --template <artifact>`：`version="ImmortalWrt v1.10.0"`、`build="20261114"`、`kernel size=0x3fffe0`、`rootfs size=0xc60000`、slotA `0x700000+0x1c00000` / slotB `0x2300000+0x1c00000`、`file=0x1500214`
- `node tools/verify_img.mjs <重建目录> --tree /home/qc233/e2631-t2/tree-iw --target sanechips`：从 factory 包切出 `payload/kernel`（slot marker + uImage，3,490,562 B）与 `payload/root`（squashfs，12,870,656 B）后复跑，结果 `BOOT-READY: no static blocker found`（退出 0）；工具按自身语义输出两条 NOTE：下载 artifact 不含独立 `e2631.dtb` 与 build_dir 的 `config-6.18`，因此 dtb 用镜像内追加的 dtb 校验、config 侧检查跳过（**不冒充通过**）；`.manifest` 也不在 artifact 内，包清单检查跳过
- 名称 / 版本 / 产物名一致性：artifact 文件名 `e2631-immortalwrt-experimental.bin`；头内版本 `ImmortalWrt v1.10.0`；内核镜像名 `ARM ImmortalWrt Linux-6.18.60`。版本号不是厂商 `V` 格式，原厂网页升级页会拒绝（预期行为；首次写入走 `e2631-fwslot`，之后用 `e2631-upgrade` 在线更新）

### 5.3 关于 `verify_pkg.mjs` 的位置（澄清）

`verify_pkg.mjs` 在 `host/`（不是 `tools/`）：`host/verify_pkg.mjs` 自初始导入（`f41d430`）即存在并受 git 跟踪；`scripts/check.sh:156` 与 `BUILD.md`、`seed/README.md` 的引用正确。`host/release.mjs:185` 调用它，`host/release.mjs:215` 调用 `tools/verify_img.mjs`；两者都在 `scripts/build.sh` 的打包阶段执行，故 `make check` 只提示它们需要在构建中运行。此前“`tools/` 下没有 `verify_pkg.mjs`”的印象来自按目录名查找，文件本身存在且本次已复跑。


## 6. 在线更新模拟

- host 端 `sim-upgrade`：假 release（`latest.json` + `asset.bin` + `SHA256SUMS`）+ 桩 `sysupgrade`/`uci`/`wget`/`e2631-fwslot`，30 项检查覆盖：v1.9.0 -> v1.10.0 原地升级（恰好一次 sysupgrade、pending 标记）、同版本 up to date、降级拒绝（`E2631_UPGRADE_FORCE=1` 才放行）、坏哈希 / 缺清单 / 重复条目拒绝且不写 pending、http 镜像拒绝、https 镜像只给 GitHub 下载加前缀、`check <file>` / `apply <file>`、`uci e2631.upd.repository` 覆盖。全部 PASS。
- 真机 `sysupgrade` 写运行槽 / 失败回落 / CRC 回读：**未覆盖**（写 flash，需用户批准）。

## 7. 未覆盖项与所需批准

1. **真机刷写**：`fwslot install` / 原厂网页升级 / `sysupgrade` 真写 — 需用户明确批准；本报告不含任何刷写操作。
2. **真机启动与硬件功能**：启动、Wi-Fi、WAN/LAN、PPE 卸载、userdata extroot、槽切换 — 需真机任务与用户批准。
3. **正式 Release**：`publish=true` 或正式 Release 需用户批准；本报告的构建必须 `publish=false`。
4. **main 分支推进**：当前 `origin/main` 为 `aabf0b4`（T4 已在 main）；T5 证据在 `iwrt-adaptation` @ `5d542c5`。合并到 main 属 T6/用户批准动作。
5. **Wi-Fi 冷启动挂死等已知问题**：仍按 `docs/known-issues.md` 记录，不在本报告结论内。

## 8. 复现

```
# 本地门禁（immortalwrt 模式 + 已 bootstrap 的树）
cd /home/qc233/zte/e2631-immortalwrt
env E2631_BASE_KIND=immortalwrt E2631_TREE=/home/qc233/e2631-t2/tree-iw E2631_OUT=/home/qc233/e2631-t2/out-iw bash scripts/check.sh

# 单独复跑各证据
bash scripts/base-pin-check.sh tree
bash scripts/layout-check.sh
node host/sim-upgrade.mjs
node tools/check-workflows.mjs
python3 tests/test_upgrade.py -v

# CI：构建（publish=false，不产生 Release）
gh workflow run firmware.yml --repo QC3284/zte-e2631-immortalwrt --ref iwrt-adaptation -f publish=false
# 取回产物与 SOURCE-INFO / SHA256SUMS
gh run download <run-id> --repo QC3284/zte-e2631-immortalwrt

# 宿主机复跑（进入解压出的 .../release/）
sha256sum -c SHA256SUMS
node host/verify_pkg.mjs <artifact> --dts overlay/target/linux/sanechips/dts/zx279128s-zte-zxhn-e2631.dts --template seed/vendor-verhdr-8b8.bin
node tools/mkfactory.mjs info --template <artifact>
# verify_img 需要 payload/kit 目录；从 factory 包切出 marker+uImage 与 squashfs 后：
node tools/verify_img.mjs <payload-dir> --tree <bootstrap tree> --target sanechips
```

## 9. 变更记录

- 2026-11-14 创建：本地 / 静态门禁证据（第 2、3、6 节）已填；CI 构建与产物校验（第 4、5 节）待 Lead dispatch 后回填。
- 2026-11-14 更新：首次 dispatch（`09e2f92`，run 43467705567）被 Lead 取消；改为在 `73ac520` 上重新 dispatch，证据 HEAD 以新 run 为准。
- 2026-11-14 更新：`73ac520` 的 run 43468042015 在 `wsl/collect.sh` 的 sysupgrade 名匹配上失败（world 成功）；Lead 修复为 `5d542c5`，新 run 43547631478 success（1h21m07s，publish skipped，无 Release）。第 1、2、3.1、3.6、3.7、4、5、7 节已按该 run 回填；宿主机复跑证据在 5.2。