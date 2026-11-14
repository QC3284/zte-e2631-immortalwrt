# T-20 树 fork 重钉 + 构建自洽性验证（2026-11-14）

状态：进行中 —— seed 单一来源修复已落地；两次 CI 构建待重跑后补齐第 5 节。

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

## 5. 重新构建与自洽性（待完成）

- 在修复 commit 上重新串行 dispatch 两次：
  gh workflow run firmware.yml --ref iwrt-adaptation -f publish=false
    -f use_pinned_apk_key=true
  不设置 reproduce_v1100（本次是修复后的重建，revision 自带）；两次之间不改代码；
  两次都使用仓库 secret E2631_APK_PRIVATE_KEY 的同一把 pinned APK 签名 key。
- 记录项：两次 run id/URL、各自 bin sha256、A==B 逐字节一致、SHA256SUMS、SOURCE-INFO
  （除 Kit commit / Run 外一致）、APK signing key 公钥 sha256、publish 步骤跳过、
  无新 Release/tag、artifact 上传、P8 install/delete、P6 miniupnpd 断言、DEVMEM 断言通过。
- 与基线 run 43572710065（pin e96aed3）的差异仅允许：Q-修1..4 内容、P5 kernel build id、
  P6 banner、P7 LuCI branch 标签、P8 apk key/db、SOURCE-INFO 字段变化、版本/revision 串
  （本次不设 reproduce_v1100，属预期差异）。

## 6. 约束

- 未发布 Release、未推 main、未碰真机 192.168.1.1；私钥只存在于 GitHub secret 与 runner
  临时 0600 文件，日志/产物中不含私钥。
