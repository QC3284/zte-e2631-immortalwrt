# E2631 树 fork 主线化全量对齐设计（方案 C）

- 状态：设计稿（用户 m06864 已选 C 并解除"永不重写"一次；m06872 授权自行批准，本稿按授权落地）
- 关联：docs/treefork-migration-design.md（原迁移设计，§6/§7 为旧形态收口记录）；docs/immortalwrt-migration.md（T1 基线）
- 本文件与实施计划（docs/superpowers/plans/）配套，是方案 C 的唯一定义文档

## 0. 目标与边界

把树 fork（QC3284/immortalwrt，分支 e2631）的 e2631 支持从"能构建"提升到"按主线惯例组织、可审查质量"：
提交系列可被主线评审者逐提交阅读、每个提交自洽、checkpatch 干净（或豁免有据）、target 命名符合惯例、
结构与主线 target 组织方式一致。**仍然不向上游提 PR**；这是形态对齐，不是提交。

边界不变：不 PR / 本机不做重活 / 构建走 Actions / 刷写走文档化安全规程（slot-0 原厂兜底不动）。

## 1. 现状基线（2026-11-21）

- 树 fork e2631 tip = 5202d4ca（firewall4 重锚修复），链：iw 4765b657 → 4 port 提交（作者 Navid Ghahremani）
  → f2d03c4a 板级 → 8a253ea8 设备包 → e96aed31 seed → CI 提交 → merge 3ac18fb9（a4ba8240）
  → quality 系列 8a06f47..cd14ffa → 5202d4ca。
- kit iwrt-adaptation tip = 3c4a5e0；pins.env：FORK_BRANCH=e2631、FORK_SHA=5202d4ca、DEPTH=17。
- 真机：RUN3（r0-cd14ffa）运行中，slot0 原厂完好，芯片级 v2 备份在 /run/media/qc233/DATA/。
- 正在跑：RUN5（44766496013，merge 跟踪目标 parity 构建）。

## 2. 关键决策

### D1 target 改名：sanechips → zx279128

- 依据：主线惯例 target 以 SoC 家族命名（ipq807x / mt7622 / bcm4908…），不以公司名；设备树 compatible
  本来就是 `"zte,zxhn-e2631", "zte,zx279128s"`（zte 前缀，从无 sanechips 前缀）；BOARDNAME 现值
  "Sanechips ZX279128" 指的就是 ZX279128 家族。
- 执行：BOARD:=zx279128、BOARDNAME:=ZTE ZX279128、目录 target/linux/zx279128/、seed 三行
  CONFIG_TARGET_zx279128*=、提交前缀 "zx279128:"、产物前缀 immortalwrt-zx279128-generic-*。
- 不动：DTS 文件名（zx279128s-zte-zxhn-*.dts）与 compatible、设备名 zte_zxhn-e2631、
  package/e2631/（设备专属包，emortal 先例）、CONFIG_TARGET_DEVICE_* 符号（现代主线标准形态，
  之前"双重 DEVICE_ 别扭"的说法作废）。
- 备选被否：zxic（公司缩写，主线无此先例）；保留 sanechips（用户已否）。

### D2 分支策略：e2631-legacy 保点 + 新系列重推 e2631

- 旧分支 git branch -m e2631 e2631-legacy 后 push（保留 5202d4ca 全部历史与 SHA，永久可引用、
  可回滚）；新系列基于 iw master a4ba8240 重建，推为新 e2631（不 force-push 覆盖旧历史）。
- "永不重写"解除的语义：允许重建新系列、允许旧提交不再被新分支引用；但旧 SHA 以 e2631-legacy
  与本地 clone 双保险保留，历史事实不消失。

### D3 新系列结构（基于 a4ba8240，全部 checkpatch 目标 0E/0W）

| # | 提交 | 内容来源 | 备注 |
|---|---|---|---|
| 1 | zx279128: add generic DWC3 platform glue driver | 6cf5f6d7 | 内容不变，仅消息/前缀 |
| 2 | mt76: serialize device reads with outer cache maintenance | 35270f0c | 同上 |
| 3 | zx279128: add ZX279128S target | a6c47309 + 67101828 的 target 部分 | 改名+SPDX+长行+消息清理；H3600 板级拆到 #4 |
| 4 | zx279128: add support for ZTE ZXHN H3600 | 67101828 板级部分 | 历史 platform.sh 16 行长行已随 f2d03c4 移除，重放时直接清 |
| 5 | zx279128: add ZTE ZXHN E2631 board support | f2d03c4a | 拆分：板级 DTS/镜像/平台脚本 |
| 6 | e2631: add device packages | 8a253ea8 | package/e2631 5 包 |
| 7 | e2631: add image seed and build notes | e96aed31 | 并入 task-30：CONFIG_TARGET_INITRAMFS=y（见 D6） |
| 8+ | quality 修复系列（按主题独立提交，消息重排） | 8a06f47..cd14ffa | extroot 快照门 / WAN 放行删除 / DEVMEM / fstools 204 / 风格 |
| 末 | firewall4 fullcone patch 直接以重锚版落地 | 5202d4ca | 不再有"merge 后重锚"提交；merge 3ac18fb9 被 rebase 吸收 |

- 作者与签名：port 提交保留原作者 author 与日期；Sign-off 用我们自己的（作为提交路径声明），
  消息尾注明来源（ImmortalWrt fork 引入，原文消息保留）。不伪造原作者 SOB。
- 4 内核补丁（patches-6.18/33 个 target 补丁）不跑 checkpatch（主线对 target patch 无此门禁），
  豁免有据；Q-研1 的 2 exec-bit 豁免、6 SPDX 一并处理。

### D4 内容不变式（重建验收的核心）

- 重建系列 tip 树 == 旧 5202d4ca 树 + 逐文件差异清单，清单只允许四类：
  ① sanechips→zx279128 改名（路径+BOARD+seed+镜像名）；② checkpatch 内容修复（SPDX 首行、
  长行断行、注释措辞，逻辑行多重集不变）；③ firewall4 patch 重锚版直接落地（与 5202d4ca 终态同）；
  ④ quality 提交重排的消息（内容不变）。
- 执行层用两层证明：git diff 旧 tip..新 tip 逐文件审计 + RUN6 vs RUN5 parity
  PASS-REVIEWED-DIFFS（允许桶 = 镜像名前缀 / os-release 与 version 文件中的 target 名字符串；
  其余任何包内容差异 = 失败）。

### D5 结构对齐清单（低风险微调）

- image/Makefile.e2631（78 行）合并回 image/Makefile（主线小 target 惯例，合并后 140 行单文件）。
- base-files/ 留在 target 根（ipq40xx 先例）；dts/、config-6.18、patches-6.18、files/ 位置不动。
- DEFAULT_PACKAGES wpad-basic-mbedtls 不动；FEATURES/KERNELNAME 不动。

### D6 task-30（initramfs 上传）并入重建 seed

- 新 seed 直接含 CONFIG_TARGET_INITRAMFS=y；firmware.yml 增 initramfs.uImage 上传（TFTP 救援）。
- 硬要求：内核 config 哈希 106ff47d01ccbcbd01e3661d209d54cd 不变（initramfs 是构建模式非内核
  config，S4 排练断言）；factory bin 字节不受影响（RUN6 parity 覆盖）。

### D7 CI 门禁增量（树 fork check.yml）

- 新增 job：对 e2631 相对 upstream/master 的新增提交，跑 scripts/checkpatch.pl（树内自带）于
  target/linux/zx279128/{image,base-files,generic,dts} + package/e2631，0E/0W + 豁免表文件
  （patches-6.18 除外、移植提交原作者无 SOB 由我方 SOB 满足）。
- kit check-workflows 同步更新路径断言与豁免口径。

## 3. 阶段

| 阶段 | 内容 | 执行者 |
|---|---|---|
| S1 | 本设计定稿 | lead（已完成） |
| S2 | 系列重建（本地组装+差异清单）→ e2631-legacy 保点 → 推新 e2631 → 树 CI 绿 | base-builder |
| S3 | checkpatch 门禁 job + 豁免表 + kit check-workflows 更新 | iwrt-baseline |
| S4 | kit 重钉（pins.env→新 tip）+ 路径/glob 更新 + bootstrap 排练（kernel hash 断言） | pkg-release |
| S5 | RUN6 dispatch（publish=false, use_pinned_apk_key=true）+ parity 全链 | verify-docs |
| S6 | 真机刷写（自批授权 m06872，文档化流程：slot-0 不动、RUN3 本地副本可回滚）+ 七项复验 + 冷启动样本 | lead |
| S7 | 文档收口（救砖手册/设计文档/README 中 sanechips 引用）+ goal complete | lead |

- 与现 goal 关系：RUN5 parity（task-26）完成后现 goal 收口；task-27 真机验收并入本计划 S6
  （一次刷写，避免连续两次）；task-30 由 D6 并入。
- 任务板：task-34（C-研1 结构盘点+checkpatch 预演，iwrt-baseline）→ task-35（C-树1 系列重建，
  base-builder）→ task-36（C-CI1 门禁，iwrt-baseline）→ task-37（C-发1 重钉+排练，pkg-release）
  → task-38（C-验1 RUN6 parity，verify-docs）→ task-39（C-收1 真机+文档，lead）。

## 4. 风险与回滚

- 回滚链：e2631-legacy（旧树史）→ pins.env 旧值 → RUN3 产物本地副本
  （/home/qc233/zte/e2631-t5-artifacts/parity-43623162108/，22,020,628B sha256 3d7825c9…）
  → 芯片级 v2 整片备份。slot-0 原厂槽全程不碰。
- 最大风险 = checkpatch 清理误改逻辑：靠逻辑行多重集对比 + RUN6 parity 双保险，差异超桶即停。
- 改名漏改：S4 排练 + check-workflows 66→72 项 + RUN6 产物名断言兜底。

## 5. 验收标准（S7 收口时逐项打勾）

1. 新 e2631 全部提交 checkpatch 0E/0W 或豁免有据；系列可按主线阅读顺序自洽。
2. 树 CI 双绿（静态门 + checkpatch 门）；kit check.yml 绿。
3. RUN6 parity = PASS-REVIEWED-DIFFS 且差异桶仅 D4 允许类目。
4. 真机 = RUN6 固件运行，七项复验通过，冷启动 ≥5 连续成功。
5. docs 无残留 sanechips 误引用（evidence 历史文档除外，以迁移说明覆盖）。
6. 旧分支 e2631-legacy 与全部旧钉点可引用。


## 6. 进展记录 (2026-11-21)

- S1–S5 全部完成: task-34..38 completed。RUN6 v3 = run 44815428424 @ kit 38fce86,
  SUCCESS 1h24m40s, publish=false + use_pinned_apk_key=true; parity RUN5-vs-RUN6 =
  PASS-REVIEWED-DIFFS (expected 23 / allowed 13 / unexpected 0), kernel-deep
  STAMP-ONLY, apk 密钥 = 钉定公钥 9edb11a9…。中途一次失败: RUN6 v2 因 image/Makefile
  合并时 check-size 丢失 $ 转义而删除 kernel.bin, 树修复 86cddb79 + 新门禁
  g_image_parse/树 CI image-pipeline-expansion check(4b09208b)。
- S6 真机刷写完成 (2026-11-21 06:34, 自批授权 m06872): e2631-upgrade apply 原地
  重写运行槽, slot1 serial 11→12, slot0 原厂 V1.0.0.7B5.8000 serial=7 未动。
  复验: revision r0-86cddb7 / DISTRIB_TARGET='zx279128/generic' / fwstate 正常
  (DEVMEM 修复生效, FW_STATE=0) / /overlay=jffs2 (extroot 未接管) / 0 panic/oops /
  双频 AP "E2631" 正常 / apk 公钥=钉定钥 / zte-mesh+luci-app-zte-mesh 在镜像。
  遗留: mount_root 'failed to sync jffs2 overlay' 仍出现 1 次 (fstools 204 未完全
  消除, 化妆级, 入修复队列); 冷启动采样待用户配合 (见验收 4)。
- 验收标准: 1 ✓ 2 ✓ 3 ✓ 4 部分(七项复验过, 冷启动待采) 5 ✓(docs/architecture.md
  /updates.md 已改 zx279128; 历史文档按豁免) 6 ✓。

