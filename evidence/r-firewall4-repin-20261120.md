# R 系列：kit 重钉到 firewall4 重锚树尖 5202d4ca（2026-11-20）

范围：task-31（树 fork 修复 firewall4 fullcone 补丁 + 重锚）之后的 kit 重钉（R-发 跟进），
由 pkg-release 执行。**未创建 Release、未触碰真机、kit main 未动。**

## 1. 树 fork 侧事实

- 新 tip：`5202d4cadca831c5394b4ceca32df22c123d46a7`（分支 `e2631`，父 `3ac18fb9`），
  提交标题 `firewall4: re-anchor fullcone patch against 3722eadc`，作者 `e2631 tree fork`，
  时间 2026-11-20T23:28:02+08:00；top tree `867b7b5d800f4d0aac8b46ce9b7ab3c625ef146b`。
  树 CI run 44763561408 SUCCESS（base-builder 报告）。
- `3ac18fb9..5202d4ca` 的 diff 恰好 1 个文件：
  `package/network/config/firewall4/patches/001-firewall4-add-support-for-fullcone-nat.patch`，+16/-16。
  原因：上游 `89f1ef18c8` 刷新 hunk offsets 后，`dab12e7663` 把 firewall4 升到 Git HEAD `3722eadc`，
  改了 `root/etc/config/firewall`（`option disable_ipv6` 示例行消失，改锚到新的 config defaults 块）与
  `root/usr/share/ucode/fw4.uc`（zone dflags 上下文新增 `zone.related_l3devs = related_l3devs;`）两处锚点。
  只有上下文/偏移变化，增删行与旧补丁逐字节相同；补丁头部 diffstat 从过期的 89 insertions 更正为 93 insertions/4 deletions。
- 不变量复核：base-port tree `4f89aa7ad0a5132dc047a27a9073b43916f0f957` 仍在历史；
  ImmortalWrt pin `4765b657625ec5bbda74b44400465fe043802b30` 仍在祖先（port_head `6710182`，port series 仍 4）；
  kernel 6.18.60；`feeds.conf.default` 与上一 pin 一致（8 行）。
- 深度实测（沿 first-parent）：base-port 提交距 tip 16 个提交（需 depth 17），ImmortalWrt pin 距 tip 20 个提交（需 depth 21）；
  `E2631_FORK_DEPTH=32` 保持不变。
- `tests/native/` 4 个副本与新 tip 逐字节一致（`027a44d7` fwslot.c、`62bacc5f` e2631-upgrade、`2c353e28` platform.sh、
  `9371db5a` slotpart-core.c），无需重同步，`g_native_sync` 仍照跑。

## 2. kit 改动（6 文件）

| 文件 | 改动 |
| --- | --- |
| `scripts/pins.env` | `E2631_FORK_SHA` `3ac18fb9…` -> `5202d4ca…`；`3ac18fb9` 列入祖先清单；加 task-31 说明；深度文本 16/20 -> 17/21 |
| `scripts/base-pin-check.sh` | `E2631_FORK_DEPTH` 静态下限 16 -> 17，注释同步 |
| `tools/check-workflows.mjs` | fork pin 断言 -> `5202d4ca…`；depth 下限 16 -> 17；仍 72 项检查 |
| `BUILD.md` | 钉值表新 tip + task-31 备注 |
| `README.en.md` | 引导段新 tip 说明（含 firewall4 重锚） |
| `docs/immortalwrt-migration.md` | 钉值演进加 task-31 / `5202d4ca…` 一句 |

其余钉值（`BASE_TREE_SHA` 4f89aa7a、`E2631_IW_SHA` 4765b657、feeds `decf9463`/`ad75cde8`、`MERGED_MASTER` a4ba8240 2026-11-14）不动。

## 3. 本地验证

- 语法：`bash -n scripts/pins.env`、`bash -n scripts/base-pin-check.sh`、`node --check tools/check-workflows.mjs`、两份 workflow YAML 解析，全部 OK。
- `bash scripts/base-pin-check.sh static` RC=0（iw pin + fork tip + base-port provenance + feed pins）。
- `node tools/check-workflows.mjs`：72 PASS / 0 FAIL。
- 未 bootstrap 的 `make check`：全部 PASS 或带理由 SKIP（host-native/base tree/board dts 因无树 SKIP）。
- 真实 GitHub 排练（`E2631_TREE=/home/qc233/zte/e2631-b4-tree`，`E2631_WORK=/home/qc233/zte/e2631-b4-work`，日志 `/tmp/t32-bootstrap.log`）：
  `bootstrap` RC=0 —— build tree `depth 1 at 5202d4ca…`（COMMITCOUNT=1、shallow=yes），scratch 历史仓库 depth 32
  （`FETCH_HEAD=5202d4ca…`，base-port tree/祖先/port series 4 全过），feeds `packages decf9463…`、`luci ad75cde8…` 均 pinned 且 branch=master，seed ok。
- post-bootstrap `make check`：13 项全 PASS、0 FAIL、0 SKIP（含 host-native copies PASS、base tree PASS、slot layout PASS、
  first-flash preflight PASS、NOTICE PASS、secret scan PASS）。
- 同树再跑：`check-workflows` 72 PASS、`host/sim-upgrade.mjs` 30 PASS、`python3 tests/test_upgrade.py` 8/8 OK。

## 4. 提交与 CI

- kit 提交 `fd80c1a2b5d58f191096142cb8e1816bb9131d46`（`r: re-pin the tree fork to the firewall4 re-anchor tip`，6 文件 +26/-19），
  push `905a2ae..fd80c1a` 到 `origin/iwrt-adaptation`。
- `check.yml` run 44766346904 on `fd80c1a`：SUCCESS（sim-upgrade、check-workflows、make check、preflight 全绿）。
- 未创建 Release/tag；`origin/main` 未动；无固件 dispatch 之外的动作。

## 5. RUN5（固件重跑）

- 按 Lead 指令 dispatch：`gh workflow run firmware.yml --ref iwrt-adaptation -f publish=false -f use_pinned_apk_key=true`。
- run 44766496013，head `fd80c1a`，event workflow_dispatch，2026-11-20T15:45:38Z 起。
- `publish=false` => 发布步骤应 SKIPPED；`use_pinned_apk_key=true` => 使用 repo secret `E2631_APK_PRIVATE_KEY`。
- 记录时状态：in_progress；产物与 RUN4 失败的对照（firewall4 补丁应在新锚点 strict apply）由 T-26 / verify-docs 验证。

## 6. 守卫

- 无 Release、无 tag、不碰真机 192.168.1.1、kit main 不动；tree fork `e2631` 的 push 属 task-31 范围（已由 base-builder 完成）。
