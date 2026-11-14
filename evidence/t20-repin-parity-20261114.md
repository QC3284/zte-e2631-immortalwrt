# T-20 树 fork 重钉 + 构建自洽性验证（2026-11-14）

状态：已完成（2026-11-15 01:10 收口）—— seed 单一来源修复已落地，两次 CI 重建产物逐字节一致（RUN1 == RUN2）。

注：2026-11-15 的批次 2 已把树 fork pin 前移到 `cd14ffa…`（见
evidence/t20b-repin-batch2-20261115.md）；本文记录的是 pin 为 83df1a9 当时的构建证据。

## 1. 背景与钉值

- 树 fork：QC3284/immortalwrt 分支 e2631，tip 83df1a90a71863c2f54d6e399e8b0ee86405083a
  （2026-11-14 的 5 个主线质量修复提交 + 一条 force-push/历史重写说明）。
- ImmortalWrt 基底 4765b657…（kernel 6.18.60）不变；端口树哈希
  4f89aa7ad0a5132dc047a27a9073b43916f0f957 不变（4 个 sanechips 提交未被重写）。
- feed 钉值不变：packages decf9463…、luci ad75cde8…。
- kit 提交 a0067ac（T-20 re-pin）：pins.env 的 E2631_FORK_SHA 由 e96aed3 改为 83df1a9；
  E2631_FORK_DEPTH 下限由 4 提到 12（base-port 提交距新 tip 12 层，旧下限会静默跳过
  树哈希断言）；P5/P7/P8 不受影响。

## 2. STOP-AND-CHECK：kit seed 遮蔽 tree seed（构建已取消）

- 2026-11-14 首次 dispatch 的 run 43601842019（publish=false、use_pinned_apk_key=true、
  未开 reproduce_v1100）在构建早期被取消（conclusion=cancelled，head a0067ac）。
- 取消原因：verify-docs 复核发现构建输入仍是 kit 的 seed/e2631.config，而 kit 副本没有
  CONFIG_KERNEL_DEVMEM=y。
- 根因：seed 双来源。树 fork 在 6b609d7（Q-修2）把 CONFIG_KERNEL_DEVMEM=y 写进树 seed
  （target 的 CONFIG_DEVMEM=y 会被 include/kernel-defaults.mk 末尾追加的 CONFIG_KERNEL_*
  透传覆盖，必须在 seed 里以 CONFIG_KERNEL_DEVMEM=y 请求）；kit 副本没有这行，却带着 P5
  的两行。两边差异恰好是 P5 块 vs DEVMEM 块，其余完全一致。
- 影响：若继续用 kit seed 构建，内核 config 缺 DEVMEM，/sbin/e2631-fwstate 读 /dev/mem
  失败，Q-修2 实际不生效；kit seed 还会长期与树 seed 漂移。

## 3. 修复：seed 单一来源

- scripts/bootstrap.sh：构建输入改为树 fork 的 seed（cp $E2631_TREE/seed/e2631.config
  .config），随后用 heredoc 追加 P5 块（CONFIG_KERNEL_BUILD_USER="e2631-build"、
  CONFIG_KERNEL_BUILD_DOMAIN="immortalwrt-e2631" 及注释）—— P5 是 kit 唯一的 seed 贡献；
  树 seed 缺失则 die。
- 删除 kit 的 seed/e2631.config（git rm）；seed/ 只保留 vendor-verhdr-8b8.bin 模板
  （其 README 不变）。
- wsl/build.sh（本地 WSL 构建路径）同步为树 seed + P5 追加；wsl/mps-static.sh 的
  诊断 grep 改读树 seed。
- tools/check-workflows.mjs 新增/改写 6 项断言（总数 70）：kit 不再有可遮蔽树 seed 的
  副本；树 fork seed（按 FORK_SHA 取 raw）含 CONFIG_KERNEL_DEVMEM=y；bootstrap 用树 seed
  且不含 kit seed 路径；P5 两行在 bootstrap；firmware.yml 有 DEVMEM 构建后断言。
- .github/workflows/firmware.yml 新增步骤 “Assert DEVMEM survived into the kernel build
  config”：在 build_dir 找到 linux-*/linux-*/ 的 .config 并 grep -qx CONFIG_DEVMEM=y，
  失败即 fail（证明镜像级效果，而不只是 seed 文本）。

## 4. 本地验证（修复 commit 内容）

- bash -n scripts/bootstrap.sh / wsl/build.sh / wsl/mps-static.sh 通过；
  node --check tools/check-workflows.mjs 通过；firmware.yml YAML 解析通过。
- node tools/check-workflows.mjs：70 项全部 PASS（含 6 项新 seed 断言）。
- 预 bootstrap make check：全部 PASS 或带原因 SKIP，exit 0。
- 真实 GitHub bootstrap 演练（临时 E2631_TREE，无本地覆盖）：BOOTSTRAP_RC=0；
  构建树 depth-1 at 83df1a9（shallow，rev-list 1）；.config 断言：
  CONFIG_KERNEL_BUILD_USER="e2631-build"（205 行）、
  CONFIG_KERNEL_BUILD_DOMAIN="immortalwrt-e2631"（206 行）、
  CONFIG_KERNEL_DEVMEM=y（341 行）；tree seed 存在、kit seed 已删除。
- 演练树上的后置 make check：全部 PASS 或带原因 SKIP，MAKE_RC=0。演练目录已删除（约 460 MB）。

## 5. 重新构建与自洽性（已完成）

### 5.1 方法与构建

- 在修复 commit c6885dd 上串行 dispatch 两次，参数一致：publish=false、
  use_pinned_apk_key=true，不设 reproduce_v1100；两次之间代码不变；两次都用仓库
  secret E2631_APK_PRIVATE_KEY 的同一把 pinned APK 签名 key。
- RUN1 43603782716：head c6885dd，2026-11-14T14:13:58Z → 15:38:23Z（1h24m25s），SUCCESS。
- RUN2 43611384642：head c6885dd，2026-11-14T15:39:55Z → 17:01:42Z（1h21m47s），SUCCESS。
- artifact zip：e2631-build-43603782716（18,766,177 B）、e2631-build-43611384642
  （18,769,997 B），均未过期。
- 两次运行的关键步骤都是 success：Assert DEVMEM survived into the kernel build config；
  Assert the build ref did not leak into miniupnpd (P6)；Install/Remove the pinned APK
  signing key；“Publish only after all build and artifact gates pass” 两次都 skipped
  （inputs.publish=false）。

### 5.2 产物与自洽性

- 两次产物 e2631-immortalwrt-experimental.bin 均 22,020,628 B，sha256 均
  b9844c3a814e4a085a6e41b6e502e18a74906acf1a104f0ba0ba8b3a7f15b959；逐字节 cmp 相同
  （IDENTICAL）。两次 SHA256SUMS 均校验通过（bin + SOURCE-INFO）。
- SOURCE-INFO 只有 Run: 行不同（run id），其余完全一致：Kit commit c6885dd、Tree fork
  QC3284/immortalwrt e2631 @ 83df1a9、Kernel 6.18.60、Port patches 0001-0004、feeds
  decf9463/ad75cde8、APK signing key 公钥 sha256
  9edb11a9d0879b6626e6980f7d182c7b20541adccae59a14acade68b9a62c1f8、Kernel build id
  e2631-build@immortalwrt-e2631 (P5)。
- 独立校验（解包 RUN1 产物的 rootfs）：/etc/e2631-version = “ImmortalWrt v1.10.0”；
  /etc/apk/keys/public-key.pem sha256 = 9edb11a9…（与 SOURCE-INFO 一致，P8 生效）；
  usr/sbin/miniupnpd 版本串为 “miniupnpd 2.3.11 - Aug 11 2026”，无
  iwrt-adaptation-<sha> 泄漏（P6 生效）；luci version.uc branch = “LuCI Master”
  （P7 生效）；DISTRIB_REVISION/BUILD_ID = r0-83df1a9（未开 reproduce_v1100，预期）。
- 与基线 run 43572710065（pin e96aed3、sha256 4e31df93…）比较：
  PASS-REVIEWED-DIFFS，expected 20、unexpected 0、stamp-only-files 4（P5 kernel build
  id、P6 banner、P7 LuCI branch 标签、P8 apk key/db 等已分类差异）。
- 报告：/home/qc233/zte/e2631-t5-artifacts/parity-43603782716-vs-43611384642.md(+.json)、
  baseline-vs-43603782716-reviewed.md；Lead 用干净 /tmp 重跑 verify-task20.sh 得
  [verify-task20] OK。
- publish/Release：两次 publish 步骤均 skipped；Releases 仍只有 v1.10.0 pre-release
  （2026-11-14T04:10:53Z，早于 T-20），无新增 Release/draft；origin 无 e2631-exp-* tag。

### 5.3 结论

同一 commit、同一把 pinned key 的两次 CI 构建产物逐字节相同 => P5/P6/P7/P8 修复后的
构建可复现（自洽性达成），T-20 收口。

## 6. 约束

- 未发布 Release、未推 main、未碰真机 192.168.1.1；私钥只存在于 GitHub secret 与 runner
  临时 0600 文件，日志/产物中不含私钥。
