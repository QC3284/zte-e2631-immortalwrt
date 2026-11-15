# R 系列：kit 重钉到 merge 树尖 3ac18fb9（2026-11-15）

状态：pin 已更新、本地真实排练全绿；本任务不 dispatch 构建，后续构建 run 由 Lead 决定（见 §5）。

## 1. 背景与钉值

- 树 fork QC3284/immortalwrt 分支 e2631 把 ImmortalWrt master `a4ba8240`（2026-11-14，
  提交信息 "Merge Official Source"）merge 进批次 2 修复系列，merge commit 为
  `3ac18fb9`（第一父 `cd14ffa`，第二父 `a4ba8240`），树 CI 43677955603 绿。
- origin/e2631 tip = `3ac18fb9a6032a16f9f0aad5417f843832aa2c6d`；top tree =
  `1ff47feda9e321ef796d513c0ffcbd6f58e860b7`（仅展示，不钉）。
- 保持不变的钉值：IW pin `4765b657…`（kernel 6.18.60，port 系列之下的祖先锚点）、
  IW pristine tree `340ae542…`、base-port tree `4f89aa7a…`（`6710182` 的树未变）、
  feed 钉值 `decf9463`（packages）/`ad75cde8`（luci）（`feeds.conf.default` 与
  `cd14ffa` 零 diff，merge 未碰 feed 行）、4 个 port patch sha256。
- 语义变化：merge 后镜像内容 = port 系列 + 合并进来的上游 master 侧提交；IW pin 只是
  port 系列之下的祖先锚点，不再是镜像唯一上游内容。`scripts/pins.env`、`BUILD.md`、
  `README.en.md`、`docs/immortalwrt-migration.md` 均已注记。

## 2. 深度实测（本次关键）

- 方法：把 `3ac18fb9` 以 `git fetch --depth 32` 取到临时仓库，按 **first-parent 路径**
  数层数，而不是看浅仓库里的 `rev-list --count`。
- `6710182`（base-port 提交）距 tip 的第一父路径 15 个提交 → 第 **16** 层；
  `4765b657`（IW 锚点）第 **20** 层；`E2631_FORK_DEPTH=32` 足够，静态下限 15 → 16。
- 陷阱：浅仓库里 `git rev-list --count 6710182..HEAD` 得 47、`4765b657..HEAD` 得 51，
  这是 merge 的 master 侧 32 层浅边界带来的假象，**不是**真实深度，不能用来定下限。

## 3. 套件改动

- `scripts/pins.env`：`E2631_FORK_SHA` `cd14ffa…` -> `3ac18fb9…`；注释增加 merge 段
  与深度推导（base-port 第 16 层、IW 第 20 层、窗口 >= 16、32 留余量）。
- `scripts/base-pin-check.sh` 与 `tools/check-workflows.mjs`：深度下限 15 -> 16，
  checker 的 fork pin 断言改到 `3ac18fb9…`（总检查数仍 70 项）。
- `tests/native/`：merge 对 4 个受管树路径零改动，4 个文件 sha256 与 merge tip 逐字节
  一致（`027a44d7…` e2631-fwslot.c、`62bacc5f…` e2631-upgrade、`2c353e28…`
  platform.sh、`9371db5a…` slotpart-core.c），无需重同步；bootstrap 后
  `host-native copies vs tree fork` 门禁复核 PASS。
- 文档：`BUILD.md`、`README.en.md`、`docs/immortalwrt-migration.md` 更新；本文件。

## 4. 真实排练（GitHub，2026-11-15）

环境：`E2631_TREE=/home/qc233/zte/e2631-b3-tree`、`E2631_WORK=/home/qc233/zte/e2631-b3-work`
（排练后删除）。

- `bootstrap` EXIT=0：`build tree: depth 1 at 3ac18fb9…`（COMMITCOUNT=1、shallow=true）；
  scratch 历史（depth 32）：base-port tree `4f89aa7a` 在历史、IW pin 是祖先、
  `port series verified: 4 commits`；feeds 从 immortalwrt/packages + luci 克隆并钉到
  `decf9463`/`ad75cde8`（分支 master，P7）；seed ok（设备选中、soft-float、apk + 单一
  TLS provider、LuCI、slot tool）；tree seed P5 生效（`.config` `CONFIG_KERNEL_DEVMEM=y`）。
- 物树 facts：HEAD=`3ac18fb9…`、top tree=`1ff47fed…`、`rev-list --count HEAD`=1、
  shallow=true。
- post-bootstrap `make check`：**13/13 PASS，0 FAIL/SKIP，exit 0**（含 host-native copies、
  base pin、base tree、layout、board dts、first-flash preflight、secret、NOTICE）。
- `node tools/check-workflows.mjs`：70/70 PASS，RC=0。
- `node host/sim-upgrade.mjs`：30/30 PASS，RC=0。
- `python3 tests/test_upgrade.py`：8 tests OK，RC=0。
- `bash scripts/base-pin-check.sh tree` 明细：build tree depth 1、fork history 复用
  `…/.e2631-fork-history`（depth 32）、base-port tree 在历史、port series 4、wireless /
  Makefile.e2631 存在、`LINUX_VERSION-6.18 = .60`、两个 feed 均 pinned commit ok 且
  branch master。

## 5. 后续与风险

- 本任务**不** dispatch `firmware.yml`；是否跑 RUN4 由 Lead 决定。
- 若跑 RUN4：与基线 43572710065 / RUN3 43623162108 的差异会新增"上游 master a4ba8240
  合并"这一大类（内核与大量包版本变化），需要 verify-docs 扩展 reviewed-diff 策略
  （expected classes）后才能给 verdict。
- `SOURCE-INFO` 仍记录 `ImmortalWrt base: … @ 4765b657`（port 之下的锚点）；merge 后该行
  不再代表镜像全部上游内容，建议 Lead 决定是否在 firmware.yml 的 SOURCE-INFO 增加 merge
  行（属 CI 适配，本次未改 firmware.yml）。
- 未推 kit main、未 dispatch、未发 Release、未碰真机；APK 私钥未动。

## 6. 复现

```sh
E2631_TREE=/path/to/tree E2631_WORK=/path/to/work bash scripts/bootstrap.sh
E2631_TREE=/path/to/tree E2631_WORK=/path/to/work make check
node tools/check-workflows.mjs
node host/sim-upgrade.mjs
python3 tests/test_upgrade.py
```
