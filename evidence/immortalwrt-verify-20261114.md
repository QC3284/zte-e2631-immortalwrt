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
- 2026-11-14 更新：树 fork parity run 43572710065（`535c0fe`）SUCCESS（1h24m45s，publish skipped，无新 Release）；对照判定 FAIL (byte-identical)，8 项意外差异全部定位为构建 provenance（runner hostname、miniupnpd GITREF、LuCI feed 检出方式、apk 每构建随机签名密钥），详见第 10 节。Lead 同日接受判定 `FAIL (byte-identical)` + `PASS-CONTENT-PARITY modulo provenance`，并解除 task-12 阻塞。

## 10. 树 fork 载荷级对照验证（phase 2，run 43572710065 已对照，Lead 已接受判定）

> 状态：parity run 43572710065（`535c0fe`，reproduce_v1100=true、publish=false）已取回并按 10.3 工具对照；10.4 已回填实际结论与 Lead 判定。本节随证据提交。

### 10.1 参考产物指纹（v1.10.0 Release asset）

- 文件：`/home/qc233/zte/e2631-t5-artifacts/parity-ref/e2631-immortalwrt-experimental.bin`，22,020,628 B，sha256 `66805b26afa47b612e535ca0885fd088b0b37461c959fb75212548d30c58294d`；与 T5 run 43547631478 产物逐字节相同（Release 资产 = T5 证据产物）。
- 工厂头：version=`ImmortalWrt v1.10.0`，product=`ZXHN E2631 V1.0.0`，hw=`V1.1.1`，build=`20261114`，key=0x1351/0x5211，bodySize=0x1500000，slotA=0x700000+0x1c00000，slotB=0x2300000+0x1c00000。
- 内核：槽 marker 32 B + uImage（file 0x234），ih_size=0x3542a2（3,490,466 B），ih_time=1794624080，name=`ARM ImmortalWrt Linux-6.18.60`；声明 kSize=0x3fffe0（4 MiB 区），rootfs 位于 file 0x400214（slot+0x400000）。
- rootfs：squashfs（xz，块 262144，bytes_used=12,869,767），mkfs_time=1794624080，声明 rSize=0xc60000；`lib/apk/db/installed` 恰 212 个包。
- 版本串：`/etc/openwrt_release` DISTRIB_REVISION=`r0-bde1448`，`/etc/os-release` BUILD_ID=`r0-bde1448`、OPENWRT_BUILD_DATE=1794624080；`/etc/apk/world` 含 `base-files=1~bde1448`；`/etc/e2631-version`=`ImmortalWrt v1.10.0`。
- SOURCE-INFO：Kit commit `5d542c5…`，ImmortalWrt base master @ `4765b657…`（kernel 6.18.60），tree 340ae542…，port tree 4f89aa7a…，feed packages `decf94639ffd6ddd26591c190b547c6b7eea150b`、luci `ad75cde88e694b511100576bfbe0a280e5efe6ef`。

### 10.2 构建确定性前提（不满足则不可能字节一致）

树 fork 的 HEAD 是固定提交、且历史完整，而 v1.10.0 是在 bootstrap 现场 `git am` 出的 5 提交浅树里构建的。差异会经 OpenWrt 的版本机制进入产物：

1. `include/toplevel.mk:13-21`：MAKELEVEL=0 时**总是**执行 `REVISION=$(scripts/getver.sh)` 与 `SOURCE_DATE_EPOCH=$(scripts/get_source_date_epoch.sh)`，只有递归 make 且两变量已在环境里才跳过。因此 workflow 里 export `REVISION`/`SOURCE_DATE_EPOCH` 对顶层 make 无效。
2. `scripts/getver.sh`：优先读顶层 `version` 文件（内容即 REV）；否则 `git`：REBOOT=`ee53a240ac902dc83209008a2671e7fdcf55957a`，REV=`r<REBOOT 之后提交数>-<短哈希>`。v1.10.0 的浅树缺 REBOOT 提交，故得 `r0-bde1448`（bde1448 = bootstrap am 提交的短哈希）。
3. `scripts/get_source_date_epoch.sh`：优先读顶层 `version.date`；否则 `git log -1 --format=%ct`。v1.10.0 的 1794624080 = 2026-11-14T02:41:20Z = bootstrap am 提交时间。
4. `rules.mk:595-625` 的 `COMMITCOUNT`（`git rev-list --count HEAD .`）决定 base-files 的 `PKG_RELEASE`；浅树里每个目录计数为 1，完整历史会是成百上千。

已做微实验（2026-11-14）：在临时目录放 `version`=`r0-bde1448`、`version.date`=`1794624080` 后，两份脚本分别原样输出这两个值；浅克隆（depth 1）子目录 `git rev-list --count HEAD .` = 1，完整克隆（3 提交）= 3。

**直接后果**：若树 fork 正常构建，REVISION 变 `r<N>-<tip>`、SOURCE_DATE_EPOCH 变 tip 提交时间，则 `/etc/openwrt_release`、`/etc/os-release` BUILD_ID、base-files 包版本、apk world/db、rootfs mtime、uImage ih_time、squashfs mkfs_time 全部改变——即使源码完全相同，载荷 sha256 也必然不同。

因此 parity 构建需要显式钉住（**这属于 Task 10/Task 3 的临时 kit 改动，不是验证方的改动**）：

| 编号 | 前提 | 做法（建议） |
|---|---|---|
| P1 | REVISION/SOURCE_DATE_EPOCH 与 v1.10.0 一致 | 在树 checkout 写顶层 `version`=`r0-bde1448`、`version.date`=`1794624080`（OpenWrt 官方 release 机制，`try_version` 优先；bootstrap 或 workflow 步骤加两行即可，不改 build.sh）；备选：给 `make world` 传命令行变量 `REVISION=… SOURCE_DATE_EPOCH=…`（需改 build.sh 的 MAKEVAR 槽）。 |
| P2 | 树 fork 必须按浅克隆构建 | `fetch --depth 1` 取 e2631 tip（与现有 immortalwrt 基底的 clone 方式一致）；完整克隆会让 COMMITCOUNT 变大、base-files 版本不同。 |
| P3 | feeds 钉在与 v1.10.0 相同的提交 | 记录值 packages=`decf9463…`、luci=`ad75cde8…`；2026-11-14 14:0x 复核两个 feed 的 master tip 仍等于记录值，但 parity 构建时应显式 checkout 或在 dispatch 前复核。 |
| P4 | 同一 seed / E2631_VERSION / 打包器 | seed/e2631.config、E2631_VERSION=`ImmortalWrt v1.10.0` 不变；工厂头 `build` 字段由 `--build`/`E2631_BUILD` 决定，否则取当天日期（v1.10.0 为 20261114）；要**工厂包逐字节一致**还需 `E2631_BUILD=20261114`，否则 build 字段与 CRC1/CRC2 属预期差异。 |

若 P1/P2/P3 任一无法满足，验收应降级为“载荷内容一致 + 差异已解释”（见 10.3 的 CLEAR 判定），而不是字节一致。

**2026-11-14 Lead 决策（parity 验收目标 = `PASS-BYTE-IDENTICAL`，P1–P4 全部确认）**：

- P1：parity bootstrap 时把 `version`=`r0-bde1448`、`version.date`=`1794624080` 写进树顶层；**不提交进 fork 仓库**，也不加 Makefile 的 MAKEVAR 覆盖。
- P2：构建树仍按 depth 1 浅取；历史断言（4 个 sanechips commit 在历史中、`4f89aa7a…` 树存在、`4765b657…` 是祖先）必须在**独立 scratch 仓库**里做（如 `git init` + `fetch --depth 32`），不得加深构建树（会改 `git rev-list --count` → base-files PKG_RELEASE）。
- P3：feed pin 以 `base/commits.env` 里的记录为准（packages `decf9463…`、luci `ad75cde8…`），parity run 在 dispatch 时复核两 feed tip 仍等于 pin。
- P4：parity run 设 `E2631_BUILD=20261114`；`firmware.yml` 增加 additive 的 `workflow_dispatch` 输入（如 `reproduce_v1100`，默认 false），由 task-10 实现，打开时才写 version 文件并传 E2631_BUILD。
- 若全部 pin 后仍有差异：保留 `PASS-CONTENT-PARITY` 作为文档化降级，报告必须写明具体哪个 stamp/字段不同及原因。
- 注意：`SOURCE-INFO.txt`/`SHA256SUMS` 属发布旁路文件，树 fork 阶段其 provenance 键（Kit commit、base 描述、port patch 哈希等）**会合理变化**；字节一致的目标只针对工厂 `.bin`，对照工具把 provenance 键变化归为预期，不据此判 FAIL。

### 10.3 对照工具与自检（未入库，位于工作区外）

- 工具：`/home/qc233/zte/e2631-t5-artifacts/parity-tools/compare-parity.mjs`（自包含 Node，仅依赖 `unsquashfs`）；按工厂头偏移自行解析，不信任 mkfactory。
- 检查层次：①工厂包 sha256/字节一致；②内核区（marker+uImage+pad）与 uImage 头字段、uImage data sha256；③rootfs 区 sha256、squashfs 超级块（mkfs_time/block/compression）；④rootfs 内容清单（路径/类型/权限/uid/gid/文件 sha256/symlink 目标，mtime 单独统计）；⑤版本文件与 `lib/apk/db/installed` 包名+版本；⑥SOURCE-INFO 逐键；⑦可选 `host/verify_pkg.mjs` 独立复验。
- 判定：`PASS-BYTE-IDENTICAL`（整文件一致）；`PASS-CONTENT-PARITY`（载荷内容一致，仅版本/时间戳/build 字段等已解释差异）；`FAIL`（存在无法解释差异，退出码 1）。版本串差异（`r0-…` 与包版本后缀）按 token 归一化后比较，时间戳按 epoch 归一化。
- 自检 1（同物对照）：parity-ref 对 T5 产物 → `PASS-BYTE-IDENTICAL`，0 预期差异、0 意外差异；rootfs 1753 条目、0 内容差异。报告：`parity-tools/dryrun-identical.{md,json}`。
- 自检 2（仅工厂 build 字段改 20261115 并重算 CRC）→ `PASS-CONTENT-PARITY`，1 条预期差异（build stamp），载荷一致。
- 自检 3（合成“仅版本/时间戳变化”镜像：改 `r0-bde1448`→`r0-abcdef1`、epoch 1794626000，重打 squashfs/工厂包）→ 6 个文件归为 stamp-only、1746 条 mtime-only 归为预期、内容差异 0；唯一 FAIL 来自宿主 mksquashfs 重压后 `rSize` 变化（合成噪声，真实同源构建不会出现）。
- 自检 4（合成真实内容变化：只改 `/etc/e2631-version`）→ 正确报 `rootfs content changed: etc/e2631-version` 并以 FAIL 退出。
- `verify_pkg.mjs` 与 `verify_img.mjs` 的旧疑问已澄清：`host/verify_pkg.mjs` 确实存在（check.sh:156 指的是它）；`tools/verify_img.mjs` 是另一层启动就绪检查，需要 payload 目录与构建树里的 dtb/config，parity 阶段不重跑，包清单以 rootfs 的 apk 数据库为准（212 个包）。

实际运行命令（拿到 candidate 后）：

```
cd /home/qc233/zte/e2631-t5-artifacts/parity-tools
node compare-parity.mjs ../parity-ref/e2631-immortalwrt-experimental.bin \
  ../parity-<run>/e2631-build-<run>/release/e2631-immortalwrt-experimental.bin \
  --ref-info ../parity-ref/SOURCE-INFO.txt \
  --cand-info ../parity-<run>/e2631-build-<run>/release/SOURCE-INFO.txt \
  --verify-pkg /home/qc233/zte/e2631-immortalwrt/host/verify_pkg.mjs \
  --md parity-<run>.md --json parity-<run>.json
```

### 10.4 实际 parity run（2026-11-14，run 43572710065）

- 触发与配置：`firmware.yml` workflow_dispatch，ref `iwrt-adaptation` @ `535c0fef0cf3d554c7aff04891ef44487ec942ce`，`publish=false`、`reproduce_v1100=true`；run https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43572710065 ，SUCCESS，1h24m45s（07:47:15Z → 09:12:00Z）。bootstrap pinned base、post-bootstrap `make check`、Build/package/verify 全 SUCCESS；`Publish only after all build and artifact gates pass` 为 **skipped**，`gh release list` 无新 Release（仍只有既有 v1.10.0 预发布）。
- 取回产物：`e2631-build-43572710065`（压缩包 18,753,821 B）解到 `/home/qc233/zte/e2631-t5-artifacts/parity-43572710065/`；`release/e2631-immortalwrt-experimental.bin` 22,020,628 B，sha256 `4e31df936cec8c02fd25cff83d98efc59c10bc2e877149d7f3c411a6dd2f9e9f`；`sha256sum -c SHA256SUMS` 通过；`build-logs/world.log` 48,636,521 B。
- SOURCE-INFO（逐键）：Kit commit `535c0fef…`；Base kind immortalwrt；ImmortalWrt base `4765b657…`@master；ImmortalWrt tree `340ae542…`；Port base tree `4f89aa7a…`；**Tree fork** `https://github.com/QC3284/immortalwrt e2631 @ e96aed31c45442374e9a37fd84c1ac048be90613`；**Parity reproduction: true（build stamp 20261114）**；四个 Port patch sha256 与参考完全一致；Kernel 6.18.60；feeds packages `decf9463…` / luci `ad75cde8…`；Run 行；Hardware tested: NO。与参考的 SOURCE-INFO 差异恰为 4 处预期 provenance：Kit commit、Run、新增 Tree fork 行、新增 Parity reproduction 行。
- 对照结论（`node compare-parity.mjs`，报告 `parity-tools/parity-43572710065.{md,json}`）：**FAIL**（退出码 1）。预期差异 4（上述 provenance）；**意外差异 8 项**：

| # | 项 | 参考（v1.10.0） | 候选（run 43572710065） | 差异量 |
|---|---|---|---|---|
| 1 | 工厂包整文件 sha256 | `66805b26afa4…` | `4e31df936cec…` | 整文件不同 |
| 2 | uImage 载荷大小 | 3,490,466 B | 3,490,610 B | +144 B |
| 3 | 内核载荷 sha256 | `1b137940cade…` | `2a3d3a9807e4…` | 不同 |
| 4 | rootfs `etc/apk/keys/public-key.pem` | `98f9bdb6…` | `2807f25a…` | 不同 |
| 5 | rootfs `lib/apk/db/installed` | 181,094 B | 181,094 B | 内容不同 |
| 6 | rootfs `lib/apk/db/scripts.tar.gz` | 425 条 | 425 条 | 内容不同 |
| 7 | rootfs `usr/sbin/miniupnpd` | apk `S:` 85138 B | apk `S:` 85135 B | 解包后 6 B 不同（banner；归档大小差 3 B 属签名） |
| 8 | rootfs `usr/share/ucode/luci/version.uc` | branch=`LuCI Master` | branch=`LuCI (HEAD detached at FETCH_HEAD) branch` | 字符串不同 |

- 一致项（重要）：工厂头 version=`ImmortalWrt v1.10.0`、product、hw、build=20261114、key1/key2、bodySize=0x1500000、slot 表全同；uImage ih_time=1794624080、name=`ARM ImmortalWrt Linux-6.18.60`；squashfs mkfs_time=1794624080、压缩/块大小、inode=1754、fragment=59 相同；`/etc/openwrt_release` revision=`r0-bde1448`；**212 个包名+版本全部相同**；rootfs 1753 条目、0 stamp-only、0 mtime-only；`host/verify_pkg.mjs` 两侧均 rc=0、0 FAIL、1 WARN（已知 `ih_hcrc` 期望差异），ALL CHECKS PASSED。

**四类根因（均已定位到机制）**：

1. **内核 hostname 嵌入**：两侧 uImage 是按原样存放的 zImage（comp=0）；真实 xz 流偏移 26547（26084 处是字符串 `XZ decompressor ran out` 里的伪 magic），解出 vmlinux 均 13,159,680 B；二进制仅 4,235 B 不同，`strings` 唯一差异为 UTS_VERSION 里的 `(runner@runnervm8axu0)` vs `(runner@ip-10-0-142-88)`（各出现 2 次），工具链（`arm-openwrt-linux-muslgnueabi-gcc`、OpenWrt GCC 14.4.0 toolchain-0336f60730、GNU ld 2.46.1）、`#0 SMP Sat Nov 14 02:41:20 2026`、时间戳均相同。原因：`KBUILD_BUILD_HOST` 缺省取构建机 `hostname`，GitHub runner 主机名每次不同。
2. **miniupnpd GITREF**：`usr/sbin/miniupnpd` 仅 6 B 不同，banner `miniupnpd 2.3.11 iwrt-adaptation-5d542c57 Aug 11 2026` vs `…iwrt-adaptation-535c0fef…`。原因：上游 `gitrev.mk`（miniupnpd_2_3_11）在 GitHub Actions 环境下用 `GITHUB_REF_NAME`+`GITHUB_SHA` 前 8 位生成 `-DMINIUPNPD_GIT_REF=…`（world.log 第 173462 行可见编译参数），kit 分支/提交被编入；属 provenance，不是源码漂移。
3. **LuCI version.uc branch**：参考 `branch = "LuCI Master"`；候选 `branch = "LuCI (HEAD detached at FETCH_HEAD) branch"`，revision 同为 `26.315.10273~ad75cde`。原因：参考用 `git clone --depth 1 --single-branch`（有分支名）取 feed；T10 改为按 SHA `git init + fetch --depth 1 + checkout FETCH_HEAD`（detached HEAD），LuCI 自版本串取自 git 分支名。
4. **apk 每构建随机签名密钥**：`rules.mk:355-356` 指定 `BUILD_KEY_APK_SEC=$(TOPDIR)/private-key.pem`；`package/Makefile:77-78` 每次构建用 `openssl ecparam -name prime256v1 -genkey` 生成随机 P-256 私钥，:80-81 导出公钥；种子 `.config` 里 `CONFIG_SIGNED_PACKAGES=y`（185 行）、`CONFIG_SIGN_EACH_PACKAGE=y`（189 行），打包用 `--sign $(BUILD_KEY_APK_SEC)`。树内 patch 0012（openssl 确定性 ECDSA）只保证“同一密钥下签名可复现”，**密钥本身每构建随机**，于是：`public-key.pem` 不同；apk `installed` 的 `S:`（包归档字节数）177/212 个包差 ±1–3 B（DER 编码的 ECDSA 签名长度随随机密钥波动）；`C:`（包校验）对 10 个内容确有变化的包不同：base-files、e2631-fwslot、luci-app-e2631、luci-app-e2631-wanport、luci-app-zte-mesh、luci-base、luci-i18n-e2631-wanport-zh-cn、luci-i18n-zte-mesh-zh-cn、miniupnpd-nftables、zte-mesh；`scripts.tar.gz` 的 425 条文件名嵌 `X<40-hex>` 哈希随包变化，但**脚本文件内容逐字节相同**（抽样 base-files、e2631-fwslot、luci-app-e2631、luci-app-e2631-wanport、luci-app-zte-mesh、zte-mesh、miniupnpd-nftables、luci-base、adblock-fast 的 post-upgrade/pre-deinstall sha256 全同）。

**结构性结论**：v1.10.0 Release 构建的随机 apk ECDSA 私钥未随发布保留（Release 里只有公钥），因此**事后无法重现其字节**；即使再钉 hostname、GITREF、feed 检出方式，apk key/db 仍不可能一致。故 `PASS-BYTE-IDENTICAL` 本次判定**未达成，且不可回溯达成**。8 项差异全部为构建 provenance（主机名、kit 分支/提交、feed 检出方式、随机签名密钥），无源码/功能漂移。

**判定（Lead 2026-11-14 接受，解除 task-12 阻塞）**：记为 `FAIL (byte-identical)` + `PASS-CONTENT-PARITY modulo provenance`（差异表、机制与不可消除原因如上）；迁移目的（载荷不变）已由本对照证明。

**明确结论：v1.10.0 的字节级复现是不可能的（impossible by construction）** —— 其 apk 随机签名私钥未随发布保留（Release 只有公钥），apk key/db 字节无法重建；因此不做重跑。**未来“可复现”的定义改为自洽（self-consistency）**：两次树 fork 构建彼此字节一致，而不是与旧 Release 相等。该判定解除 task-12（`E2631_BASE_KIND` 默认翻转为 immortalwrt + kit 瘦身）的阻塞。

为未来自洽可复现，需在构建前钉住（P5–P8 交 task-12 “future-build reproducibility”）：P5 `KBUILD_BUILD_HOST`（及 `KBUILD_BUILD_USER`）；P6 归一化 `GITHUB_*` 或显式 `MINIUPNPD_GIT_REF`；P7 feed 按分支 clone 后 `reset --hard <pin>`（保住分支名）；P8 apk 签名密钥——Lead 决定：默认仍**每构建随机**，task-12 增加可选 workflow 输入以注入固定密钥，**私钥不提交入库**。

- 数据位置：`/tmp/parity-analyse/`（carve 的 `ref.uimg/kernel/vmlinux`、`cand.uimg/kernel/vmlinux`、`ref-root/`、`cand-root/`、`ref-scripts/`、`cand-scripts/`）、`parity-tools/parity-43572710065.{md,json}`。
- 本小节未提交，待 Lead 评审；本轮无 push、无 Release、无真机操作。
