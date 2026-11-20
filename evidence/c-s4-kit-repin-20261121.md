# 方案 C：kit 重钉到重建后的树尖 d74ec77a（2026-11-21）

范围：task-37（S4，kit 重钉 + 排练），由 pkg-release 执行。前置任务 task-35 完成
（树 fork 按主线惯例重建为 14 提交、分支 `e2631-legacy` 保留旧史），task-36（树 CI checkpatch）
尚未落地。**未创建 Release、未 dispatch 固件、未触碰真机、kit main 未动。**

## 1. 树 fork 侧事实（方案 C）

- 重建 tip：`2ecee6fcee474d64ea9023ad0baa4d3e2489224c`（14 提交 = 4 个复核移植提交 +
  10 个 fork 提交，分支 `e2631`）；旧 tip `5202d4ca…` 保留在分支 `e2631-legacy`。
- 排练在旧 tip 上暴露一个方案 C 回归：把 target 由 `sanechips` 改名 `zx279128` 后，两处
  `DEPENDS:=@TARGET_sanechips` 未同步，导致 `zte-mesh`、`luci-app-zte-mesh`、
  `kmod-usb-dwc3-generic-plat` 从 defconfig 中静默消失（D4 审计只比路径，没比 Kconfig 依赖解析）。
- 修复提交：`d74ec77aff719a74c6643e540af74ae5a2f85925`（父 `2ecee6fc`，标题
  `zx279128: fix stale TARGET_sanechips dependencies`，作者 Lead，2026-11-21），diff 仅 2 文件：
  - `package/e2631/zte-mesh/Makefile`：`DEPENDS:=@TARGET_zx279128 +ip-full +kmod-veth +kmod-sched-core`（注释同步）
  - `package/kernel/linux/modules/usb.mk`：`DEPENDS:=@USB_SUPPORT @TARGET_zx279128 +kmod-usb-dwc3`
  - 全树 grep `@TARGET_sanechips` 为 0；剩余 `sanechips` 字样属文档化 allowlist
    （`CONFIG_SANECHIPS_PHY`、`files/drivers/net/phy/sanechips.c`、补丁 019 名称/内容、DTS 注释）。
- 不变量复核：base-port（最后移植提交 `4ca29c6550`）tree = `6136bd92d5259dbaf22f6bca02c675f05abdf86b`
  （替代旧 `4f89aa7a`）；ImmortalWrt pin `a4ba8240…` 为祖先，port series 仍 4 提交；
  kernel 6.18.60；`feeds.conf.default` 零 diff，feed 钉值不变（`decf9463` / `ad75cde8`）。
- 深度实测（/tmp 临时仓库按 SHA fetch）：depth 15 已含最后 port 提交但缺 `a4ba8240`；
  depth 16 起 `a4ba8240` 在窗口内（tip 距 pin 16 层）。`E2631_FORK_DEPTH=32` 不变，
  `base-pin-check` / checker 的静态下限 15 -> 16。
- 分支序列：`a4ba8240..d74ec77a` 共 15 提交（4 port + 11 fork）。`tests/native` 4 个副本与新 tip
  逐字节一致（`027a44d7` fwslot.c、`62bacc5f` e2631-upgrade、`2c353e28` platform.sh、
  `9371db5a` slotpart-core.c），无需重同步，native-sync 门禁照跑 PASS。

## 2. kit 改动（50 文件，+389/-269）

| 文件 | 改动 |
| --- | --- |
| `scripts/pins.env` | `E2631_IW_SHA=a4ba8240…`、`E2631_IW_TREE_SHA=b905483c…`、`E2631_FORK_SHA=d74ec77a…`、`E2631_BASE_TREE_SHA=6136bd92…`；删除 `E2631_MERGED_MASTER_SHA/DATE` 与 `E2631_BASE_PATCH_SHA256_0001..0004`；port provenance 保留并列出 4 个 port 提交 SHA；深度说明 16/32 |
| `scripts/env.sh` | export 列表去掉 MERGED/PATCH 相关键；注释同步 |
| `scripts/bootstrap.sh` | 路径 `target/linux/zx279128/`；image 钩子断言 `Device/zte_zxhn-e2631` 且禁止 `image/Makefile.e2631`（D5）；seed 断言 `CONFIG_TARGET_DEVICE_zx279128_generic_DEVICE_zte_zxhn-e2631=` 与 `CONFIG_TARGET_ROOTFS_INITRAMFS=` |
| `scripts/base-pin-check.sh` | 方案 C 断言：15 提交序列、4 个 port subject、`a4ba8240` 祖先、`4ca29c6550^{tree}==6136bd92`、zx279128 路径存在、`Makefile.e2631` 必须不存在、`@TARGET_sanechips` 必须不存在、seed 三个符号；depth 下限 16；历史断言仍在 scratch 仓库 |
| `scripts/check.sh` / `build.sh` / `layout-check.sh` / `notice-check.sh` / `preflight.sh` / `selftest-wanport.sh` | 目标目录/设备符号/镜像钩子改 zx279128；layout 的 image 规则改为 `image/Makefile`（并断言旧 `Makefile.e2631` 不存在） |
| `wsl/*.sh`（约 25 个） | 机械改名 `sanechips` -> `zx279128`（target 路径、`CONFIG_TARGET_DEVICE_`、产物目录、root-* 名称、说明文字）；`wsl/build.sh` 镜像钩子改查 `Device/zte_zxhn-e2631` |
| `tests/native/`、`tests/test-*` | `git mv` 到 `tests/native/target/linux/zx279128/`（3 个文件；fwslot.c 本就在 `tests/native/package/e2631/`）；4 个副本与新 tip 逐字节一致；测试内路径同步 |
| `host/release.mjs`、`host/sim-upgrade.mjs`、`tools/verify_img.mjs` | DTS 路径/verify_img target/sim 的 updater 路径改 zx279128；v1.10.0 引用注释更正 |
| `tools/check-workflows.mjs` | 常量改为新钉值（a4ba8240/b905483c/6136bd92/d74ec77a）；删除 merged/patch 断言，新增「退役钉值不得回归」「base commit/tree 存在」；SOURCE-INFO 字段 `Port base tree (4 commits applied):`；seed 断言加 `CONFIG_TARGET_zx279128=y/_generic=y` 与 `CONFIG_TARGET_ROOTFS_INITRAMFS=y`；路径 sweep 加 `@TARGET_sanechips`/旧产物 glob；共 80 项检查 |
| `.github/workflows/firmware.yml` | SOURCE-INFO 删除 Merged 与 Port patch 行，新增 `Port base tree (4 commits applied)` 与 `Port provenance: <repo> <branch> @ <sha>`；注释说明方案 C |
| 文档 | `BUILD.md` 钉值表/门禁表/路径、`README.md`、`README.en.md`、`docs/immortalwrt-migration.md` §6.5（方案 C 决策、15 提交结构、e2631-legacy、SOURCE-INFO 变化、checker 80） |

## 3. 排练（真实 GitHub，immortalwrt 路径）

命令（本机 2 核，`nice -n 19`；日志 `/tmp/t37-bootstrap-repin.log`）：

```
E2631_WORK=/home/qc233/zte/e2631-c-work E2631_TREE=/home/qc233/zte/e2631-c-tree \
E2631_OUT=/home/qc233/zte/e2631-c-work/out bash scripts/bootstrap.sh
```

- `bootstrap` RC=0：build tree `depth 1 at d74ec77a…`（`COMMITCOUNT=1`、shallow=yes）；
  scratch 历史仓库 depth 32 校验 base-port tree `6136bd92…`、`a4ba8240…` 祖先、port series 4、kernel 6.18.60。
- feeds：`packages decf9463…`、`luci ad75cde8…`，均 branch=`master`（P7 分支克隆 + reset 到钉值）。
- seed：`.config` 有 `CONFIG_TARGET_zx279128=y`、`CONFIG_TARGET_zx279128_generic=y`、
  `CONFIG_TARGET_DEVICE_zx279128_generic_DEVICE_zte_zxhn-e2631=y`、`CONFIG_TARGET_ROOTFS_INITRAMFS=y`、
  P5 的 `CONFIG_KERNEL_BUILD_USER="e2631-build"` / `CONFIG_KERNEL_BUILD_DOMAIN="immortalwrt-e2631"`；
  **旧 tip 排练时的 "seed packages not present" 警告消失**，`CONFIG_PACKAGE_zte-mesh=y`、
  `CONFIG_PACKAGE_luci-app-zte-mesh=y` 回归。
- `kmod-usb-dwc3-generic-plat`：E2631 seed 有意不选 USB（`seed/e2631.config:110` 注释：本板 USB 不可用，
  探测会重启控制器），因此 .config 中为 not set 属预期；依赖已可见，实测向 .config 追加
  `CONFIG_PACKAGE_kmod-usb-dwc3-generic-plat=y` 后 `make defconfig` 保留 =y（H3600 设备的 image 规则本就会选它），
  证明 stale 依赖导致「无法选择」的回归已消除。
- kernel config 哈希 `106ff47d01ccbcbd01e3661d209d54cd`（RUN6 必须运行时断言）本地无法复算
  （需 kernel prepare + 工具链）；证明链：旧 tip `5202d4ca` 与新 tip 的 kernel 配置输入逐字节一致——
  `target/linux/generic/config-6.18` sha256 `1c2fa733…`、target `config-6.18` sha256 `1ca2327b…`、
  `patches-6.18` 文件名相同且内容合并哈希 `93403a9d…`、seed `CONFIG_KERNEL_*` 行 diff 为空；
  `LINUX_VERMAGIC=md5(.config.set 中 '=[ym]' 行)`，`Kernel/SetNoInitramfs` 在生成 .config.set 时先剔除
  INITRAMFS 行，故 seed 的 `CONFIG_TARGET_ROOTFS_INITRAMFS=y` 不进 kernel config；RUN5 已记录
  `6.18.60~106ff47d…-r1`。本条在 RUN6 以数值断言闭环。

## 4. 本地验证（post-bootstrap 同树）

- `make check`：13/13 PASS、0 FAIL、0 SKIP、RC=0（含 host-native copies PASS、base tree PASS、
  slot layout PASS、first-flash preflight PASS、NOTICE PASS、secret scan PASS）。
- `node tools/check-workflows.mjs`：80 PASS / 0 FAIL（树 CI 内容经 GitHub raw 断言；task-36 的
  checkpatch job 尚未落地，属预期新增项，不影响现有 80 项）。
- `node host/sim-upgrade.mjs`：30 PASS；`python3 tests/test_upgrade.py`：8/8 OK。
- 语法：`bash -n` 全部脚本（scripts/wsl/tests）、`node --check` 全部 host/tools mjs、两份 workflow YAML 解析，均 OK。
- 未 bootstrap 裸树 `make check`：10 PASS、3 个带理由 SKIP（native sync/base tree/board dts 无树），RC=0。
- `bash scripts/base-pin-check.sh static` RC=0；`bash scripts/layout-check.sh`：kit 三份一致，
  tree preflight 在排练树中一致（`0x400000 / 0x1100000 / 0x1500000`）。

## 5. 提交与 CI

- kit 提交 `3c0b10b89d53e8d722c36a2e68facfc5f170f614`（`c: re-pin the kit to the plan-C tree fork`，50 文件 +389/-269），
  push `fb03991..3c0b10b` 到 `origin/iwrt-adaptation`。
- `check.yml` run [44783433480](https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44783433480) on `3c0b10b`：SUCCESS（sim-upgrade、check-workflows、make check、preflight 全绿）。
- 未创建 Release/tag；`origin/main` 未动；无固件 dispatch；真机未触碰。

## 6. 未验证 / 风险

- RUN6（固件重跑，verify-docs/Lead）需以运行时数据断言：kernel package 版本含
  `6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1`、`/etc/openwrt_release` / apk world 的树修订串为
  `r0-d74ec77a`、zte-mesh 系列包重新出现在 manifest、source-info 字段与本次改动一致。
- task-36（树 CI checkpatch job + 豁免表）尚未落地；落地后 checker 80 项中涉及树 CI 内容的断言可能需补一条
  checkpatch 存在性检查（本轮不预改）。
- `image/Makefile` 的 `DEVICE_PACKAGES` 仍保留 `libustream-mbedtls` 历史 wart（已记录，超出 S4 范围）。
