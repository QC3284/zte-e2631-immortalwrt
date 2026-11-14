# 树 fork 迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 E2631 的 ImmortalWrt 支持重构为传统树 fork 形态（QC3284/immortalwrt 分支 e2631，标准 make 构建），旧仓库退化为打包/分发 kit，构建产物与已真机验证的 v1.10.0 一致。

**Architecture:** 新仓库 = immortalwrt/immortalwrt fork，分支 e2631 = iw master@4765b657 + 4 个 sanechips 真实提交 + e2631 设备/包提交；kit 仓库删除 overlay/base/apply.sh，bootstrap.sh 改为 clone 树 fork，firmware.yml 其余流程不变。验收硬门 = 树构建产物与 v1.10.0 产物 payload 级一致 + make check 13/13 + BOOT-READY。

**Tech Stack:** ImmortalWrt（apk、kernel 6.18.60）、sanechips target、GitHub Actions、host/mkfactory.mjs 打包链、现有 check.sh/verify_pkg/verify_img 门禁。

**Spec:** docs/treefork-migration-design.md（用户已批准 2026-11-14）

## Global Constraints

- 新仓库名 `QC3284/immortalwrt`，分支 `e2631`；不向上游 immortalwrt/immortalwrt 提 PR/issue。
- 基底钉点 `4765b657625ec5bbda74b44400465fe043802b30` 不变；4 补丁应用后树哈希必须 = `4f89aa7ad0a5132dc047a27a9073b43916f0f957`（迁移中途断言用）。
- kit 仓库 main 推送 / 正式 Release 仍需用户批准；新仓库 e2631 分支推送已随设计获批。
- 本机弱（i5-3230M/2C4T/11GB）：不做全量本地编译；一切构建走 GitHub Actions；本地只跑静态门禁。
- 真机已刷 v1.10.0 保持不动；迁移验收通过前不得再次刷写。
- 结论落盘（docs/、evidence/、TEAM-NOTES.md）。
- 团队内英文、对用户中文（TEAM-NOTES 既有规则）。

## Review Focus

- 树 fork 构建产物 vs v1.10.0：kernel/root payload sha256、包清单、SOURCE-INFO（除日期字段）必须一致；不一致必须查明原因后才可推进 kit 切换。
- 4 个 sanechips 提交保留原 From 署名；e2631 提交署名 QC3284；提交信息风格贴近 iw 主线（小写前缀 + 一句话）。
- overlay/package/* 搬入 tree package/e2631/* 后，包名、目录、Makefile 依赖不得变化（PKG_RELEASE、DEPENDS 原样）。
- 删除 overlay/base/apply.sh 后，kit 的 check.sh/check-workflows/tests 不得引用残留路径。
- firmware.yml 切换后 publish=false 的 CI-only run 必须全绿且 Publish 跳过；真机在线升级通道（Release + SHA256SUMS）行为不变。

---

### Task 1: 树 fork 组装（base-builder）

**Files:**
- Create: `/home/qc233/zte/iwrt-tree/`（clone 自 immortalwrt/immortalwrt @ 4765b657）
- Create: `/home/qc233/zte/iwrt-tree/target/linux/sanechips/base-files/` 下 e2631 设备文件（来自 kit `overlay/target/linux/sanechips/base-files/`）
- Create: `/home/qc233/zte/iwrt-tree/package/e2631/<pkg>/`（来自 kit `overlay/package/{firmware,luci,network}/`，每个包一个目录，包内容原样）
- Create: `/home/qc233/zte/iwrt-tree/seed/e2631.config`（= kit `seed/e2631.config`）
- Create: `/home/qc233/zte/iwrt-tree/README.e2631.md`（来源说明 + 构建指引）

**Interfaces:**
- Consumes: kit `base/0001..0004`、kit `overlay/`、kit `seed/e2631.config`、`overlay-removed.txt`（已执行状态）
- Produces: 分支 `e2631` 尖端提交 SHA（供 Task 2/3 引用）；树哈希 `4f89aa7a…` 断言结果

- [ ] **Step 1: 建仓** — gh repo fork immortalwrt/immortalwrt --org QC3284? 不可用则 gh api 创建 QC3284/immortalwrt（空仓），clone immortalwrt/immortalwrt @ 4765b657 到 `/home/qc233/zte/iwrt-tree`，`git checkout -b e2631`。验证：`git rev-parse HEAD` = 4765b657…。
- [ ] **Step 2: 落 4 个 sanechips 提交** — `git am` kit `base/0001..0004`（顺序不可变）；`git log --format='%an %s'` 显示 4 个新提交、From 保留原作者；计算树哈希并断言 = 4f89aa7a…（与 bootstrap 一致）。
- [ ] **Step 3: 搬设备文件** — `overlay/target/linux/sanechips/base-files/` → tree 同路径（覆盖时 diff 必须为空）；`overlay/package/` 按包搬到 `package/e2631/<pkg>`，每个包的 Makefile 内容逐字节不变（仅路径变化）。
- [ ] **Step 4: seed + 文档** — 复制 seed/e2631.config；写 README.e2631.md（树来源、分支、构建命令、与 kit 的分工）。
- [ ] **Step 5: 提交并推送** — 按主题拆 2-3 个提交（设备文件 / 包 / seed+README），信息风格如 `sanechips: add ZTE ZXHN E2631 device support`；推送 `e2631` 到 QC3284/immortalwrt。验证：`gh api repos/QC3284/immortalwrt/branches/e2631` 存在且尖端 = 本地尖端。
- [ ] **Step 6: 向 Lead 报告** — 分支尖端 SHA、树哈希断言结果、提交列表。

### Task 2: 树仓库 CI（iwrt-baseline）

**Files:**
- Create: `/home/qc233/zte/iwrt-tree/.github/workflows/check.yml`
- Modify: kit `tools/check-workflows.mjs`（+2 项检查：树 CI 存在且引用钉点；见 Task 4）

**Interfaces:**
- Consumes: Task 1 的分支尖端 SHA
- Produces: 树仓库 check.yml（静态门禁，run 需绿）；check-workflows 新检查项

- [ ] **Step 1: 调研 iw 树内惯例** — 看 immortalwrt/immortalwrt 中 target 包、device 文件、CI 的常规做法（1 小时上限，写要点进任务报告）。
- [ ] **Step 2: 写 check.yml** — 静态门禁：`make defconfig`（seed 复制后）成功 + 断言 e2631 关键文件在树（`test -f target/linux/sanechips/base-files/etc/config/wireless` 等 5 条）+ 断言 `git log --oneline` 含 4 个 sanechips 提交。不做 world（2h 构建归 kit firmware.yml）。
- [ ] **Step 3: 推送并等绿** — push 到 e2631 分支；GitHub Actions run SUCCESS。报告 run 号。

### Task 3: 逐字节/载荷级对照验证（verify-docs）

**Files:**
- Create: `/home/qc233/zte/e2631-t5-artifacts/parity-<run>/`（产物与对照输出）
- Modify: `evidence/immortalwrt-verify-20261114.md`（追加第 10 节 parity 结果，未提交）
- Modify: `docs/treefork-migration-design.md`（如验收判据需按实测调整，标注原因）

**Interfaces:**
- Consumes: Task 1 分支尖端；kit firmware.yml（bootstrap 已改为 clone 树 fork —— 由 Task 4 先完成 bootstrap 改动，或先用临时分支验证）
- Produces: parity 报告（kernel/root payload sha256、包清单 diff、make check、BOOT-READY、SOURCE-INFO 差异清单）

- [ ] **Step 1: 触发构建** — 与 pkg-release 协调：先在 kit 的 `iwrt-adaptation` 上改 bootstrap.sh 指向树 fork（属 Task 4 的前置改动，临时提交），dispatch firmware.yml（publish=false）。等待 SUCCESS。
- [ ] **Step 2: 下载产物** — `gh run download` 取 release/*.bin + SOURCE-INFO + SHA256SUMS。
- [ ] **Step 3: 载荷对照** — 用 host/verify_pkg.mjs 解出两版（v1.10.0 artifact 与新产物）的 kernel/root payload，比对 sha256；比对 verify_img 包清单（212 包）；比对 make check 结果；SOURCE-INFO 逐项 diff（预期差异仅构建时间类字段）。
- [ ] **Step 4: 记录与结论** — 差异清单写进 evidence 第 10 节；全部一致 → 报告 GREEN（kit 切换解锁）；不一致 → 逐项查明并回报 Lead。

### Task 4: kit 瘦身与切换（pkg-release）

**Files:**
- Modify: `scripts/bootstrap.sh`（删 git-am/apply 逻辑，改 clone QC3284/immortalwrt@e2631 钉点 + feeds 流程不变）
- Delete: `overlay/`、`base/`、`apply.sh`
- Modify: `scripts/check.sh`（layout-check 改「树内文件存在断言」= git ls-tree；base-pin-check 改「树 fork 钉点 + 4 提交存在」；删 apply-gate）
- Modify: `scripts/layout-check.sh`、`scripts/base-pin-check.sh`、`wsl/apply-gate.sh`（删除或改造）
- Modify: `.github/workflows/firmware.yml`（bootstrap 步名称/行为核对；其余不动）
- Modify: `tools/check-workflows.mjs`（同步 Task 2 的新检查 + 移除 overlay 相关旧检查）
- Modify: `docs/`（immortalwrt-migration.md 实施状态、BUILD.md 构建说明、README 分工说明）

**Interfaces:**
- Consumes: Task 3 的 parity GREEN；Task 1 分支尖端 SHA
- Produces: kit 不再含 overlay/base；firmware.yml 从树 fork 构建；check.sh 全绿

- [ ] **Step 1: 前置验证** — 本地跑 check.sh（bootstrap 改后）、check-workflows 全项、bash -n 全部脚本。
- [ ] **Step 2: 删除与改造** — 按 Files 清单执行；grep 全仓确认无残留引用（`grep -rn 'overlay/\|apply.sh\|base/000' scripts/ tools/ tests/ docs/ .github/` 为空或仅为历史文档）。
- [ ] **Step 3: CI-only 构建** — 推 `iwrt-adaptation`，check.yml 绿后 dispatch firmware.yml（publish=false）——若 Task 3 已用同配置构建过，此步复用其结果，不必重复。
- [ ] **Step 4: 报告** — 提交列表、门禁结果、残留引用扫描结论。

### Task 5: 文档与收尾（lead）

**Files:**
- Modify: `docs/treefork-migration-design.md`（状态更新）
- Modify: `evidence/immortalwrt-verify-20261114.md`（第 10 节定稿 + 提交）
- Modify: `TEAM-NOTES.md`（迁移记录）

- [ ] **Step 1: 复核** — re-read Task 1-4 提交与 parity 报告。
- [ ] **Step 2: 提交 kit 文档** — 迁移文档 + 证据第 10 节提交（kit main 推送需用户批准，执行前请示）。
- [ ] **Step 3: 用户交付说明** — 中文总结：新架构、两仓库分工、验证结果、真机无需重刷、后续维护方式。
