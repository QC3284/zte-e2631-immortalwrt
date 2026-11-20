# 方案 C：RUN6 与 RUN5 一致性验收（C-验1 / task-38）

- 日期：2026-11-21（UTC 2026-11-20/21）
- 执行：verify-docs（独立验收，只读构建产物与本地树）
- 依据：`docs/mainline-alignment-design.md`（方案 C，2026-11-14 用户批准）；
  `evidence/c-plan-tree-rebuild-audit-20261121.md`（D4 文件级审计）；
  `evidence/c-s4-kit-repin-20261121.md`（S4 重钉与排练）
- 主机：i5-3230M / 11 GB，不做全量本地编译；构建全部来自 GitHub Actions

## 0. 结论摘要

- **RUN6 v3（run 44815428424）SUCCESS**，产物 `e2631-immortalwrt-experimental.bin`
  22,020,628 B，sha256 `6aa2c3b56b455fa80e08f597ec0536be41b0502606a52f81bc0f662714cccafb`。
- 与 RUN5（44766496013）比对：**PASS-REVIEWED-DIFFS**，expected 23 / allowed 13 /
  **unexpected 0**；kernel-deep **STAMP-ONLY**；`verify_img --target zx279128` **BOOT-READY**；
  `verify_pkg` 两侧 **ALL CHECKS PASSED**（各 1 个预期 ih_hcrc WARN）；内嵌 APK 公钥与钉值 PEM 一致。
- 首轮 v3 比对曾 FAIL（5 条 unexpected）。逐条归因后确认全部是“已允许桶的派生结果”或
  比较器策略缺口（etc/os-release 软链、Plan C 新增 Port provenance 行），补入策略并留负对照
  （§4.2、`evidence/t38/negctl/`）：用补前策略可精确复现这 5 条，证明补记与差异一一对应。
- RUN6 v2（44787949071）在镜像装配失败（树内容 `check-size` 单 `$` bug），无产物；
  修复树 fork `86cddb79` 后 v3 才产生产物。该失败不影响 v3 的 parity 口径（§2.2）。
- **判定：方案 C 内容不变性验收 PASS。** kit 可切换；真机刷写/Release 仍需 Lead + 用户批准，
  本次验收未做任何设备写操作、未 push、未发 Release。

## 1. 目的与验收口径

方案 C 把树 fork 从 merge 上游 `a4ba8240` 改为在 `a4ba8240` 上重建提交系列，
并把 target 由 `sanechips` 改名 `zx279128`。本任务独立验收 RUN6 产物：

1. 与 RUN5（44766496013，merge 候选，树尖 `5202d4ca`）比对，verdict 必须是
   **PASS-REVIEWED-DIFFS 且 unexpected = 0**；允许的差异只有以下类别：
   - target 改名导致的版本/目标名字符串：`etc/openwrt_release`、`usr/lib/os-release`、
     `etc/os-release`（软链到前者）、`etc/apk/repositories.d/distfeeds.list`；
   - Plan C checkpatch 类（D4 审计 §3.2 类 ②）：`etc/board.d/01_leds` 仅新增 SPDX 注释；
   - 版本/构建戳类（比较器按修订串与日期归一化，含 OpenSSL 内嵌 built-on 编译时刻）；
   - 上述类别在包/数据库层的派生结果（`lib/apk/db/installed`、`scripts.tar.gz`）；
   - SOURCE-INFO 来源类（Kit commit、Tree fork、ImmortalWrt base/tree、Port base tree、
     Port provenance、Run、重钉后退役的 Merged/Port patch 行等）。
2. 运行时断言：apk DB 中 kernel 配置哈希 `6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1`
   不变；base-files `1~86cddb7`；zte-mesh 与 luci-app-zte-mesh 重新出现在 manifest
   （S4 排练发现的依赖回归不得复现）。
3. SOURCE-INFO Plan C 钉值：iw base `a4ba8240`、pristine tree `b905483c`、
   port base tree `6136bd92`、tree fork `86cddb79`、kernel 6.18.60、feed 钉值
   `decf9463` / `ad75cde8`、pinned APK key，且不得再出现 Merged 行。
4. Kernel 深度比较 RUN5 vs RUN6 必须是 **STAMP-ONLY**（方案 C 不修改任何 kernel 输入；
   已在本地树验证 `5202d4ca..86cddb79` 之间 `target/linux/generic`、kernel-6.18、
   config-6.18、seed 的 `CONFIG_KERNEL_*` 均无差异）；出现 NON-STAMP 一律 FAIL 并上报。

## 2. 输入事实

### 2.1 RUN5（参考产物，已验收）

| 项 | 值 |
| --- | --- |
| run | [44766496013](https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44766496013)，SUCCESS，publish=false |
| kit commit | `fd80c1a2b5d58f191096142cb8e1816bb9131d46` |
| 树尖 | `5202d4cadca831c5394b4ceca32df22c123d46a7`（merged a4ba8240 + firewall4 重锚） |
| 产物 bin | `e2631-immortalwrt-experimental.bin`，22,020,628 B，sha256 `3a5914edac7dd973c4a86c2c97de5854ed348466701204d5d0903b1972439050` |
| apk 包数 | 212 |

### 2.2 RUN6 v2（失败）与修复

| 项 | 值 |
| --- | --- |
| run | [44787949071](https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44787949071)，`completed/failure`，2026-11-20T20:09:19Z |
| kit commit | `b99d449e4e7db255b98cf3961113083e02157111`（`publish=false`、`use_pinned_apk_key=true`） |
| 失败步骤 | `Build, package and verify firmware`（镜像装配阶段；world.log 第 181061-181064 行） |
| 产物 | 仅 `e2631-build-44787949071` 构建日志（2,418,261 B），无固件 |
| 修复提交 | [86cddb79802bb2223db21f7364613505174968d8](https://github.com/QC3284/immortalwrt/commit/86cddb79802bb2223db21f7364613505174968d8) `zx279128: fix check-size escaping in the e2631 image pipeline` |
| tree CI | [44814387651](https://github.com/QC3284/immortalwrt/actions/runs/44814387651) SUCCESS（head 86cddb79） |

失败日志摘录（world.log，行号为原始构建日志）：

```
WARNING: Image file .../zte_zxhn-e2631-kernel.bin is too big: 3491034 > 0
stat: cannot statx .../zte_zxhn-e2631-kernel.bin: No such file or directory
bash: line 1: [: 4194304: unary operator expected
WARNING: Image file .../zte_zxhn-e2631-kernel.bin is too big:  > 4194304
```

根因：Plan C 把 `image/Makefile.e2631` 合并进 `target/linux/zx279128/image/Makefile` 时，
`Device/zte_zxhn-e2631` 的流水线写成了 `check-size $(KERNEL_SIZE)`（单 `$`，make 展开为空值），
而不是延迟求值的 `$$(KERNEL_SIZE)`。空限制使第一个 `check-size` 把 3,491,034 B 的 kernel.bin
判为过大并删除，后续 `check-size 4194304` 面对缺失文件报错，sysupgrade 装配找不到 kernel.bin
而失败。修复只改该文件 1 行（改为 `$$(KERNEL_SIZE)`）；Lead 用 parse-only `make -pn` dump
复核流水线已读作 `... | check-size 4096k`。

对 parity 口径的影响：无。v2 没有产出固件；该修复只恢复装配门限，不改变 kernel/rootfs
编译输入（`target/linux/generic`、kernel 配置、seed 与 package 内容均不变）。

### 2.3 RUN6 v3（本轮验收对象）

| 项 | 值 |
| --- | --- |
| run | [44815428424](https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44815428424)，`completed/success`，attempt 1，2026-11-20T20:53:40Z → 22:18:20Z（1h24m40s） |
| 输入 | workflow_dispatch，ref `iwrt-adaptation`，`publish=false`，`use_pinned_apk_key=true` |
| kit commit（run head） | `38fce86caf9010006898320fd840aa1dbb208f00`（`c: re-pin to the check-size fix and gate the image pipeline parse`，父 cf482e4） |
| 后续 kit 提交关系 | 当前 `origin/iwrt-adaptation` 尖 `f39d63c`；`38fce86c` 是其祖先，`38fce86c..f39d63c` 只改 `BUILD.md`、`docs/immortalwrt-migration.md`、`tools/check-workflows.mjs`（不动 `scripts/pins.env`、`firmware.yml`、seed），构建输入不变 |
| 树尖 | `86cddb79802bb2223db21f7364613505174968d8` |
| artifact | `e2631-build-44815428424`，18,770,618 B（id 14674682789） |
| 产物 bin | `e2631-immortalwrt-experimental.bin`，22,020,628 B，sha256 `6aa2c3b56b455fa80e08f597ec0536be41b0502606a52f81bc0f662714cccafb` |
| 不变量 | port base tree `6136bd92d5259dbaf22f6bca02c675f05abdf86b`；iw base `a4ba8240`；pristine tree `b905483c`；feed `decf9463` / `ad75cde8` |

## 3. 工具与自测

工具在仓库外 `/home/qc233/zte/e2631-t5-artifacts/parity-tools/`，随本证据归档到 `evidence/t38/`：

- `verify-task38.sh`：下载（gh run download + API/curl 回退）→ `sha256sum -c` →
  SOURCE-INFO 钉值断言 → `verify_img --target zx279128`（BOOT-READY）→ apk DB 断言
  （kernel 哈希、base-files 修订、manifest 回归）→ `compare-parity` RUN5 vs RUN6 →
  `kernel-deep-compare` → 内嵌 APK key 与本地 PEM 比对。
- `t38-policy-run5-to-run6.json`：逐条给理由的允许桶；任何未列差异 = FAIL。
  终稿含 7 个 `rootfsExact`、1 个 `versionFiles`、1 个 `infoKeys` 条目（扩展过程见 §4.2）。
- `t38-check-compare.mjs` / `t38-json-field.mjs`：比较器与 kernel 结论的判定辅助。

自测（候选 = RUN5 自身）：**PASS-BYTE-IDENTICAL**，unexpected 0；kernel-deep **IDENTICAL**；
212 个包；`verify_img --target zx279128` BOOT-READY；内嵌 APK key DER sha256 `b0cbe6fb…`
与本地 PEM 一致（`evidence/t38/selftest-run5-as-candidate.log`）。
v3 前已把工具中的预期树尖改为 `86cddb79`；kit commit 通过 `EXP_KIT` 环境变量运行时传入。

负对照：用**补前**策略（删掉 5 条扩展）重跑同一对产物，verdict 精确回到 FAIL 且
unexpected = 5（即 §4.2 的 5 条），证明扩展项与差异一一对应，不是放宽门禁
（`evidence/t38/negctl/pre-extension-report.md`）。

## 4. RUN6 v3 结果

### 4.1 判定与运行时事实

| 检查 | 结果 |
| --- | --- |
| `sha256sum -c SHA256SUMS` | `e2631-immortalwrt-experimental.bin: 成功`、`SOURCE-INFO.txt: 成功` |
| SOURCE-INFO Plan C 钉值 | 全部命中（iw base a4ba8240 / pristine b905483c / port base tree 6136bd92 / tree fork 86cddb79 / kernel 6.18.60 / feeds decf9463, ad75cde8 / pinned APK key；无 Merged 行） |
| `verify_img --target zx279128` | **BOOT-READY**，无静态阻断项（uImage `ARM ImmortalWrt Linux-6.18.60`、dtb `zte,zxhn-e2631` / `zte,zx279128s`、squashfs used=0xc482d3 file=0xc60000、slot 表与 0x400000/0x1100000/0x1500000 几何一致） |
| `verify_pkg`（ref / cand） | 各 `ALL CHECKS PASSED`（fails 0，warnings 1：预期 ih_hcrc） |
| apk DB | 212 包；kernel `6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1`；base-files `1~86cddb7`；kmod-mac80211 `6.18.60.7.2-r14`；fstools `2026.11.07~5e371ecf-r2`；ppp `2.5.5-r1`；`zte-mesh 0.1.0-r1` 与 `luci-app-zte-mesh 0.1.0-r1` 均在 manifest |
| compare-parity RUN5 vs v3 | **PASS-REVIEWED-DIFFS**，expected 23 / allowed 13 / **unexpected 0** |
| kernel-deep | **STAMP-ONLY**：uImage data 3,491,546 → 3,491,050 B、ih_time 1795188482 → 1795207582、解压后 13,159,680 B 大小不变、仅 62 字节 / 11 段不同（全部 uts-version、build-id、build-epoch 类） |
| APK 公钥 | `etc/apk/keys/public-key.pem` 178 B，DER sha256 `b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d`，与钉值 PEM 相同；未发现私钥材料 |

工厂头解析（两侧一致，仅 CRC 派生字段随载荷重滚）：`version="ImmortalWrt v1.10.0"`、
`product="ZXHN E2631 V1.0.0"`、`hw="V1.1.1"`、`build="20261120"`、bodySize=0x1500000、
slotA=0x700000+0x1c00000、slotB=0x2300000+0x1c00000；kernel/rootfs 声明大小不变（4,194,272 /
12,976,128 B）。

### 4.2 首轮 FAIL 的 5 条 unexpected：归因与策略补记

首轮 v3 比对（同一工具、同一策略初稿）结果为 FAIL：expected 22 / allowed 9 / unexpected 5。
逐条分析与处置如下（负对照可复现，见 §3）：

| # | 首轮 unexpected | 归因（可复核证据） | 处置 |
| --- | --- | --- | --- |
| 1 | `usr/lib/libcrypto.so.3` 内容变化 | OpenSSL 把编译时刻写进库内字符串 `built on: Fri Nov 20 HH:MM:SS 2026 UTC`（偏移 3019604）；`cmp -l` 全库只差 **5 字节**，即时间数字 `15:28:02 → 20:46:22`（与两侧 uImage ih_time 1795188482/1795207582 完全对应）；大小同为 3,732,056 B，无代码/数据差异 | 归入构建戳类；策略 `rootfsExact` 给出 5 字节/偏移的证据化理由 |
| 2 | `lib/apk/db/installed` 内容变化 | 212 个 stanza 中只有 2 个变化：base-files（`V 1~5202d4c→1~86cddb7` + C/S/I 与 6 个 Z: 文件哈希，来源是已允许的改名/修订/01_leds 变更）与 libopenssl3（C/S 与 libcrypto 的 Z:，来源是第 1 条 built-on 戳）；其余 210 个 stanza 逐字节相同 | 归入“已允许类别的派生结果”；策略给出逐包核对理由 |
| 3 | `lib/apk/db/scripts.tar.gz` 内容变化 | 425 个成员内容按 X<hash> 归一化后 sha256 全部相同；成员**文件名**内嵌包内容哈希（base-files `X17e859b→X11be395`、libopenssl3 `X19a46dc→X1070171d`），即第 2 条的派生 | 同上，派生类 |
| 4 | `etc/os-release` “content differs beyond stamps” | `etc/os-release` 是指向 `../usr/lib/os-release` 的软链；rootfs 清单比对只看到软链目标不变，而版本文件循环会顺着软链读内容，于是同一条 target 改名规则（`OPENWRT_BOARD sanechips/generic→zx279128/generic`，修订/日期戳归一化）没有命中 | 策略缺口：补 `versionFiles[etc/os-release]`，理由与 `usr/lib/os-release` 相同 |
| 5 | SOURCE-INFO `Port provenance: undefined != … db8b8d41` | Plan C 重钉后 kit 新增“Port provenance”来源行（port 仓库/分支/SHA）；旧 `Merged ImmortalWrt master` 与 `Port patch 000N sha256` 行退役。比较器 provenance 正则不匹配该新键 | 策略缺口：补 `infoKeys[Port provenance]`（纯来源行，不含构建输入） |

补记后同一对产物 verdict = **PASS-REVIEWED-DIFFS，unexpected 0**；expected 22→23（Port provenance 转 expected），
allowed 9→13（新增 4 条）。终稿策略与本证据一起归档，负对照保留下“少了这 5 条就 FAIL”的可复核性。

### 4.3 D4 允许差异类 ↔ 策略桶映射（内容不变性验收）

RUN5-vs-RUN6 比对就是方案 C 的内容不变性验收：D4 审计（`evidence/c-plan-tree-rebuild-audit-20261121.md` §3.2）
列出的允许差异类，逐条映射到 `t38-policy-run5-to-run6.json` 的实际桶；未映射到任何类的差异
一律 FAIL（策略里没有对应 reason）：

| D4 允许类（审计 §3.2） | 树侧实际改动 | 对应策略桶 |
| --- | --- | --- |
| ① 重命名 | `target/linux/sanechips` → `target/linux/zx279128`（100 个 R100）+ seed `CONFIG_TARGET_*` | `rootfsExact`: `etc/openwrt_release`、`usr/lib/os-release`、`etc/apk/repositories.d/distfeeds.list`；`versionFiles`: `etc/os-release`（软链） |
| ② checkpatch / SPDX | `base-files/etc/board.d/01_leds` 仅新增 SPDX 注释 | `rootfsExact`: `etc/board.d/01_leds` |
| ③ firewall4 re-anchor | 补丁内容与 RUN5 相同（仅重锚定） | 无可见差异（firewall4 包版本不变） |
| ④ 文档/CI 重排；D5 image/Makefile 合并 | 不改变编译输入 | 无内容差异；装配修复只恢复 check-size 门限 |
| ①+戳的包层派生 | base-files 版本/内容变化进入 apk 数据库与脚本包 | `rootfsExact`: `lib/apk/db/installed`、`lib/apk/db/scripts.tar.gz` |
| 构建戳（非 D4 类） | revision `r0-5202d4c`→`r0-86cddb7`、构建时间戳、OpenSSL built-on 字符串 | 比较器 expected（stamp）/ `rootfsExact`: `usr/lib/libcrypto.so.3` |
| 来源行（非 D4 类） | SOURCE-INFO 钉值/行集合变化（含新增 Port provenance） | 比较器 provenance 类 expected（`infoKeys` 补缺口） |
| kernel 压缩载荷 | 仅构建戳重滚 | `kernelPayload` reason + kernel-deep 必须 STAMP-ONLY（config hash `106ff47d…` 不变） |

## 5. 差异分类（终稿，unexpected = 0）

### 5.1 expected：23 条（结构类别）

- 构建戳：uImage ih_time、squashfs mkfs_time 各 1 条；3 个仅修订/日期戳文件（`etc/apk/world`、
  `etc/banner`、`etc/openwrt_version`）；1,741 个仅 mtime 不同的条目；revision 串
  `r0-5202d4c → r0-86cddb7`；`etc/apk/world` / `etc/openwrt_version` 的版本文件行；
  apk base-files 版本 `1~5202d4c → 1~86cddb7`。
- SOURCE-INFO 来源行 13 条：ImmortalWrt base（`4765b657→a4ba8240`）、pristine tree
  （`340ae542→b905483c`）、Kit commit（`fd80c1a→38fce86c`）、`Merged ImmortalWrt master` 行退役、
  `Port base tree (4 patches applied)` 退役并出现 `(4 commits applied) 6136bd92`、4 条 Port patch
  sha256 行退役、新增 `Port provenance`、Run、Tree fork（`5202d4ca→86cddb79`）。
- 以上全部由比较器按“来源/戳”类目自动解释，策略只接收需要额外理由的 13 条（§5.2）。

### 5.2 allowed：13 条（逐条理由见归档策略）

| 路径/键 | 类别 |
| --- | --- |
| kernel payload size / sha256 / bytes | kernelPayload：kernel 输入未变，载荷随构建戳重滚 |
| `etc/apk/repositories.d/distfeeds.list` | target 改名（feed 钉值不变） |
| `etc/board.d/01_leds` | D4 ②：仅 SPDX 注释 |
| `etc/openwrt_release`（rootfs 内容 + 版本文件两处） | target 改名 |
| `usr/lib/os-release`（rootfs 内容 + 版本文件两处） | target 改名 |
| `etc/os-release` | target 改名（软链读取） |
| `lib/apk/db/installed` | base-files 修订/改名 + libopenssl3 built-on 戳的派生 |
| `lib/apk/db/scripts.tar.gz` | 同上，成员名内嵌包哈希的派生 |
| `usr/lib/libcrypto.so.3` | OpenSSL built-on 编译时刻，仅 5 字节 |

未解释差异（unexpected）为 0；rootfs 共 1,571 个文件，内容差异仅 10 个（全部落在上述类目内），
其余 1,561 个逐字节相同。

## 6. 结论与风险

- **结论：PASS。** 方案 C 的内容不变性验收通过：RUN6 v3 与 RUN5 的差异全部是 target 改名、
  D4 允许的 checkpatch 注释、构建戳及其派生，kernel 输入与配置哈希不变（kernel-deep STAMP-ONLY）。
  kit 可以按计划切换（S5），真机刷写/Release 另需用户批准。
- 镜像非逐字节相同是预期结论：构建戳（ih_time、mkfs_time、mtime、OpenSSL built-on）每次都重滚；
  v1.10.0 → 方案 C 的可复现性口径仍是“同钉同种子同戳一次重建”的自一致性，而非跨 build 逐字节。
- kit 运行尖与 run head 的差异已核对：`38fce86c..f39d63c` 只改文档与 `tools/check-workflows.mjs`，
  不动 `scripts/pins.env`、`firmware.yml`、seed，故后续用 f39d63c 重建的构建输入与 v3 相同。
- 残余风险：v3 镜像尚未在真机验证（target 改名可能影响设备侧字符串/路径；manifest 与
  `verify_img` 断言已覆盖静态面），真机验收列入 task-39，需用户批准后执行；
  策略中的 5 条补记都有负对照与逐条证据，若后续有人质疑门禁被放宽，可用
  `evidence/t38/negctl/` 复现原 FAIL。
- 本次验收只读：未 push、未发 Release、未对设备做任何写操作。

## 7. 附件（evidence/t38/）

- `verify-task38.sh`、`t38-policy-run5-to-run6.json`、`t38-check-compare.mjs`、`t38-json-field.mjs`：本轮工具与终稿策略。
- `run6v3-verify.log`：端到端验收日志（结束于 `[verify-task38] OK`）。
- `compare-RUN5-vs-RUN6v3.md/.json`：比较器完整报告（verdict、23 expected、13 allowed、0 unexpected）。
- `kernel-deep-RUN6v3.md/.json`：kernel 深比（62 字节 / 11 段，STAMP-ONLY）。
- `verify-img-RUN6v3.log`：BOOT-READY 逐项 PASS。
- `SOURCE-INFO-RUN6-v3.txt`：产物内 SOURCE-INFO 原文。
- `selftest-run5-as-candidate.log`：工具自测（RUN5 vs RUN5，PASS-BYTE-IDENTICAL）。
- `negctl/`：补前策略 + 其 FAIL 报告（精确复现 5 条 unexpected 的负对照）。
- 外部工具目录（未入仓）：`/home/qc233/zte/e2631-t5-artifacts/parity-tools/`（含 `compare-parity.mjs`、`kernel-deep-compare.mjs`）。

