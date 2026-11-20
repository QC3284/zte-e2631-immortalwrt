# 方案 C 树重建审计（task-35 / S2）

- 日期：2026-11-21（UTC 2026-11-20）
- 执行：base-builder
- 仓库：`QC3284/immortalwrt`（树 fork），分支 `e2631` / `e2631-legacy`
- 依据：`docs/mainline-alignment-design.md`（方案 C，2026-11-14 用户批准）；
  `evidence/c-plan-checkpatch-precheck-20261121.md`（task-34 门禁与豁免预检）
- 主机：i5-3230M / 11 GB，本地不跑全量编译（构建走 GitHub Actions）

## 0. 结论摘要

1. `e2631` 已按方案 C 从 ImmortalWrt `a4ba8240` 重建为 14 个提交（4 个移植
   commit + 10 个本 fork commit），tip `2ecee6fcee474d64ea9023ad0baa4d3e2489224c`；
   旧系列原样保存在新分支 `e2631-legacy`（tip `5202d4ca`）。
2. 新不变量：4 个移植 commit 之后的树哈希
   `6136bd92d5259dbaf22f6bca02c675f05abdf86b`，替换旧 `4f89aa7a…`；
   对应第 4 个 commit `4ca29c6550`（zx279128: add support for ZTE ZXHN H3600）。
3. D4 文件级审计：与旧 tip 的树差异共 108 个路径，全部落入允许类
   （①重命名、②checkpatch/SPDX、③firewall4 re-anchor、④消息/文档重排，
   加 D5 指定的 image/Makefile 合并、D3/D7 指定的 CI/README/豁免文档重写）；
   无未批准的内容漂移。
4. checkpatch 门禁（D1 范围）：范围内 50E/22W 全部命中 E1-E4 豁免，非豁免 0。
5. 树 CI：见 §5（推送后自动运行）。

## 1. 分支与钉点

| 项 | 值 |
| --- | --- |
| 树 fork | https://github.com/QC3284/immortalwrt |
| 基线 | `immortalwrt/immortalwrt` master @ `a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5`（2026-11-14，kernel 6.18.60） |
| `e2631` 推送前 | `5202d4cadca831c5394b4ceca32df22c123d46a7`（旧系列 tip） |
| `e2631` 推送后 | `2ecee6fcee474d64ea9023ad0baa4d3e2489224c`（14 commits，`--force-with-lease`） |
| `e2631-legacy` | 新建 = `5202d4cadca831c5394b4ceca32df22c123d46a7`（旧系列完整历史，回滚用） |
| 新不变量 | `6136bd92d5259dbaf22f6bca02c675f05abdf86b`（= `4ca29c6550^{tree}`） |

旧 `4f89aa7ad0a5132dc047a27a9073b43916f0f957` 随之失效；kit 树 CI 的
`E2631_PORT_TREE_SHA` 与 kit `base/commits.env` 的 `E2631_BASE_TREE_SHA`
需在 S4 re-pin 时同步（见 §6）。

第一次推送的 CI run `44779074310` 失败，原因是**新 CI 工作流自身**的
awk 正则把行尾锚点写成了字面 `$`（`H3600\$`），不是树内容问题；改为
`H3600$/ ` 后 fixup 进 CI commit 并重推，得到当前 tip 与 run `44779366548`。

## 2. 提交清单（最旧在前，24 个路径之外的细节见各 commit）

| # | SHA | 作者 | 日期 | subject | 类别 |
| --- | --- | --- | --- | --- | --- |
| 1 | `af89c4703b` | Navid Ghahremani | 2026-10-12 | zx279128: add generic DWC3 platform glue driver | 移植 |
| 2 | `c300b1eca5` | Navid Ghahremani | 2026-10-12 | mt76: serialize device reads with outer cache maintenance | 移植 |
| 3 | `7a19c62cbc` | Navid Ghahremani | 2026-10-12 | zx279128: add ZX279128S target | 移植 |
| 4 | `4ca29c6550` | Navid Ghahremani | 2026-10-12 | zx279128: add support for ZTE ZXHN H3600 | 移植（不变量） |
| 5 | `0cf92a8153` | QC3284 | 2026-11-21 | zx279128: add ZTE ZXHN E2631 board support | 板级 |
| 6 | `51173cc6e9` | QC3284 | 2026-11-21 | e2631: add the E2631 device packages | 设备包 |
| 7 | `325bfaf461` | QC3284 | 2026-11-21 | e2631: add the image seed and build notes | seed/文档 |
| 8 | `de14696c2a` | QC3284 | 2026-11-21 | ci: check the e2631 tree without building it | CI |
| 9 | `a2b49ed493` | QC3284 | 2026-11-21 | e2631: gate the userdata extroot on a snapshot marker | Q1 extroot |
| 10 | `71a54a1fc1` | QC3284 | 2026-11-21 | e2631: keep SSH and HTTP(S) off the WAN by default | Q2 安全 |
| 11 | `18078094fa` | QC3284 | 2026-11-21 | e2631: skip the fstools jffs2 sync when there is no upper | Q3 fstools |
| 12 | `8dfd7ed8c3` | QC3284 | 2026-11-21 | e2631: request CONFIG_DEVMEM where it is decided (seed + tree CI) | Q4 DEVMEM |
| 13 | `ebaf17c05e` | QC3284 | 2026-11-21 | e2631-userdata: never write or accept an empty snapshot marker | Q5 加固 |
| 14 | `2ecee6fcee` | QC3284 | 2026-11-21 | firewall4: re-anchor fullcone patch against 3722eadc | ③ re-anchor |

签名：commit 1-4 保留原作者 + 原日期，保留原 `Signed-off-by: Navid
Ghahremani` 并追加本 fork 的 `Signed-off-by: QC3284
<2078725082@qq.com>`；commit 5-14 作者/签名均为 QC3284。全系列已无旧
`e2631 tree fork` 签名残留（`git log --format=%B | grep -c` = 0）。
提交消息按 ≤75 列排版（整提交 checkpatch 无 COMMIT_LOG_LONG_LINE）。

## 3. D4 文件级审计（树 `e2631-legacy` vs `e2631`）

### 3.1 差异统计（`git diff --name-status -M`）

```
 1  D    target/linux/sanechips/image/Makefile
 4  M    .github/workflows/check.yml, README.e2631.md,
         docs/checkpatch-exemptions.md, seed/e2631.config
 1  R063 target/linux/sanechips/image/Makefile.e2631 -> target/linux/zx279128/image/Makefile
 1  R088 target/linux/sanechips/Makefile -> target/linux/zx279128/Makefile
 1  R092 .../base-files/etc/board.d/01_leds -> .../zx279128/.../01_leds
100 R100 target/linux/sanechips/** -> target/linux/zx279128/**（逐字节相同）
```

合计 108 个路径；新树 `target/linux/zx279128` 共 103 个文件
（104 = 旧 target 105 个文件 - 1 个合并掉的 Makefile.e2631）。

### 3.2 允许类逐项

| 路径/差异 | 允许类 | 实际差异 |
| --- | --- | --- |
| 100 个 R100 重命名 | ① 重命名 | `git` 判定 100% 相似，内容逐字节相同（含 base-files 45、files 19、patches 33、dts 2、config 1 等） |
| `target/linux/zx279128/Makefile`（R088） | ① 重命名 | 仅 `BOARD:=sanechips→zx279128`、`BOARDNAME:=Sanechips ZX279128→ZTE ZX279128` 两行；FEATURES/CPU_TYPE/SUBTARGETS/KERNEL_PATCHVER/KERNELNAME/DEFAULT_PACKAGES 不变 |
| `.../board.d/01_leds`（R092） | ② checkpatch | 仅新增第 2 行 SPDX（GPL-2.0-only）；其余逐字节相同 |
| `image/Makefile.e2631` → `image/Makefile`（R063）+ 旧 `image/Makefile`（D） | D5 合并 | 旧 image/Makefile 的 4 个 define（Build/zte-slot-marker、Build/uImage-ramboot、Device/Default、Device/zte_zxhn-h3600）与旧 Makefile.e2631 的 2 个 define（Device/zte_zxhn-e2631、Build/e2631-factory）全部进入新 image/Makefile，无缺失/无新增；`include … Makefile.e2631` 删除；绝对 `DEVICE_DTS_DIR=$(TOPDIR)/target/linux/sanechips/dts` 删除，改用 Device/Default 的 `DEVICE_DTS_DIR := ../dts`；Build/e2631-factory 位于 `$(eval $(call BuildImage))` 之前 |
| `seed/e2631.config`（M） | ① 重命名 | 仅 4 处：`CONFIG_TARGET_sanechips*→zx279128*`（3 行）与 no-fpu 注释里的 target 名；DEVMEM 块、其他配置与旧 tip 相同 |
| `README.e2631.md`（M） | ④ 文档重写 | 按 D3/D7 新写：树 fork 说明、基线 a4ba8240、14 提交清单、不变量、构建步骤、checkpatch 约定；另含 DEVMEM、userdata/extroot、安全提示三节 |
| `docs/checkpatch-exemptions.md`（M） | ④ 文档重写 | 新写门禁口径（整提交、`-g`、默认输出格式）与 E1-E4 豁免表 |
| `.github/workflows/check.yml`（M） | ④ CI 重写 | 新 pin（`E2631_IW_SHA=a4ba8240…`）、新不变量 `E2631_PORT_TREE_SHA=6136bd92…`、新四个 subject、新路径列表（无 Makefile.e2631）、generic flips 断言、DEVMEM 断言、seed defconfig 断言 |

未改动（与旧 tip 逐字节相同）：`package/e2631/` 24 个文件、`package/kernel/mt76`
（Makefile + patches 001/002）、`package/system/fstools`（Makefile
`PKG_RELEASE:=2` + patches 203/204）、`package/network/config/firewall4`
的 fullcone 补丁（sha256 `6e0b7566eaadd6a5d596fc93d7e8243801ac24f5b3103a0e8a7ff0ddff7cce05`，
内容与旧 tip 的 re-anchor 版本相同）、`target/linux/generic/config-6.18`
（hung-task 25 / DETECT_HUNG_TASK / SOFTLOCKUP_DETECTOR 三处 flips 保留）。
`git diff --stat` 对上述路径均为空。

### 3.3 模式与其他

- 重命名路径 mode 全部一致（`MODES_OK`，无权限漂移）；旧/新 exec 位集合
  在 103 个 surviving 文件上一一对应。
- 无新增符号链接、无 submodule 变化。
- 旧 target 目录 `target/linux/sanechips` 不存在残留；`target/linux/zx279128/image/Makefile.e2631`
  不存在（树 CI 有断言）。

## 4. checkpatch 门禁

- 命令：`perl scripts/checkpatch.pl --no-tree --show-types -g <sha>`
  （整提交口径：提交消息与 Signed-off-by 也检查；`--terse` 无路径，不能
  用于路径豁免）。
- 范围（D1）：`target/linux/zx279128/**`（patches 走 E2）+ `package/e2631/**`。
- 系列合计：范围内 **50E / 22W，全部命中 E1-E4，非豁免 0**。
  类型统计：EXECUTE_PERMISSIONS 29、TRAILING_WHITESPACE 26、
  LONG_LINE 6、LONG_LINE_STRING 8、TYPO_SPELLING 8。
- 逐提交整提交 totals（ERROR/WARNING）：
  `af89c4703b 0/0`，`c300b1eca5 0/0`，`7a19c62cbc 3/0`，`4ca29c6550 0/0`，
  `0cf92a8153 45/0`，`51173cc6e9 5/22`，`325bfaf461 0/0`，`de14696c2a 0/0`，
  `a2b49ed493 0/0`，`71a54a1fc1 0/0`，`18078094fa 2/0`，`8dfd7ed8c3 0/0`，
  `ebaf17c05e 0/0`，`2ecee6fcee 0/0`。
- 豁免解释：E1 执行位（base-files 脚本 + rpcd 2 个）；E2 补丁文件行尾空格
  （diff 上下文语法）；E3 fwslot.c 用户可见消息单行；E4 e2631flash.js 的
  callE2631* RPC 名误报。
- 差异说明：文档表 E1 记「28（26+2）」按**最终树**统计；系列范围 29 是
  因为 `63_e2631_wan_access`（755）在 commit5 引入、commit10 删除，
  两个口径一致。
- 整系列所有 commit 的 `COMMIT_LOG_LONG_LINE/BAD_SIGN_OFF/NO_AUTHOR_SIGN_OFF/
  SPDX_LICENSE_TAG` 等非豁免类均为 0。

## 5. 本地验证

| 检查 | 结果 |
| --- | --- |
| `busybox ash -n`（target base-files 38 个 sh 脚本） | 0 失败 |
| `node --check`（package/e2631 3 个 luci JS） | 0 失败 |
| `gcc -fsyntax-only -Wall -Wextra -Werror`（e2631-fwslot.c） | 通过 |
| 树 CI 等价：base ancestor / 四 subject / 不变量 tree / 必需文件 / Makefile.e2631 absent / generic flips / seed symbols / CI pins | 全部 OK |
| `git status` | clean |
| `make defconfig` | 未本地执行（本机无 feeds；树 CI 执行） |

树 CI：run `44779366548`（head `2ecee6fc`，branch `e2631`）在推送后
自动运行；结果：**SUCCESS**（Static tree gate）。前一次 run
`44779074310`（head `da9a6d86`）失败仅因新工作流 awk 转义，修复后重推。

本机临时日志：`/tmp/c35-gate-final.txt`、`/tmp/c35-audit-final.txt`；
关键统计已全部写入本文。

## 6. 残余风险与后续

1. **S4 kit re-pin（pkg-release）**：kit `base/commits.env` 的
   `E2631_IW_SHA` 应改为 `a4ba8240…`、`E2631_BASE_TREE_SHA` 改为
   `6136bd92…`；`base/0001-0004` 的 git-am 序列已被树 fork 取代，
   kit bootstrap/apply 与门禁（`scripts/base-pin-check.sh`、
   `wsl/apply-gate.sh` 等）需要按方案 C 流程调整——不在 S2 范围。
2. **S5 RUN6（verify-docs/Lead）**：实机验证 extroot 标记、DEVMEM
   （`/sbin/e2631-fwstate` 读 `MT_TOP_MISC`）、WAN 22/80/443 关闭、
   首次启动静默；树 CI 只证明静态内容。
3. **task-36 checkpatch job（iwrt-baseline）**：按本部门禁实现——`-g`
   口径、D1 范围、E1-E4 表、默认输出格式解析。
4. **已知保留项**：`image/Makefile` 的 `DEVICE_PACKAGES` 仍列
   `libustream-mbedtls`（旧 tip 相同，未改动）；seed 用
   `libustream-openssl`（apk-openssl 基底），RUN5 构建未观察到冲突；
   若后续 apk 报冲突，在单独提交里处理。
5. `e2631-legacy` 是旧系列（含旧 pin、合并历史）的唯一入口，
   不要改写；`e2631` 在本次推送后如再改写，按仓库约定需要 Lead
   批准并使用 `--force-with-lease`。

## 附：复现命令（节选）

```sh
# 1) 以 a4ba8240 为基重建（本地工作树 /home/qc233/zte/iwrt-tree）
git branch -m e2631 e2631-legacy
git checkout --orphan e2631 a4ba8240     # 实际按单提交构造，见提交清单
# 2) 四个移植 commit：原 author/date + 原 SOB + 本 fork SOB
# 3) 本 fork commit：板级/设备包/seed/CI/Q1-Q5/firewall4
# 4) 不变量
git rev-parse 4ca29c6550^{tree}   # 6136bd92d5259dbaf22f6bca02c675f05abdf86b
# 5) checkpatch 门禁（逐提交）
perl scripts/checkpatch.pl --no-tree --show-types -g <sha>
# 6) D4 审计
git diff --name-status -M e2631-legacy HEAD
# 7) 推送（第二次为 CI 工作流修正后的 force-with-lease）
git push origin e2631-legacy
git push --force-with-lease=refs/heads/e2631:5202d4ca... origin refs/heads/e2631
```
