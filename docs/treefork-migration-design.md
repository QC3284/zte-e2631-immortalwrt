# 树 fork 迁移设计 —— e2631 支持进入传统 ImmortalWrt 形态（自用，不向上游提 PR）

**状态：已获用户批准（2026-11-14，方案 B）。本文档为迁移的设计与验收基准。**

## 1. 目标

把 ZXHN E2631 的 ImmortalWrt 支持从「补丁系列 + overlay 套件」重构为**传统树 fork 形态**：
设备支持以真实 git 提交落在我们自己的 ImmortalWrt 树 fork 里，标准 `make` 构建。
**不向上游 immortalwrt/immortalwrt 提任何 PR/issue。**

## 2. 决策（已批准）

| 项 | 决策 |
|---|---|
| 新仓库 | `QC3284/immortalwrt`（fork 自 immortalwrt/immortalwrt），分支 `e2631` |
| 基底钉点 | **保持 `4765b657625ec5bbda74b44400465fe043802b30` 不变**（迁移验收依赖与已验证 v1.10.0 逐字节对照） |
| sanechips 提交 | base/0001..0004 以真实提交落树，保留原作者署名与提交信息 |
| 设备文件 | 全部进树 `target/linux/sanechips/base-files`（zte_zxhn-e2631）与 image/Makefile |
| 设备包 | 进树 `package/e2631/`（fwslot、wifi-ap/boot、leds、wanport、luci-app-e2631-*、zte-mesh 等），不建独立 feed |
| 旧仓库角色 | **方案 B**：退化为打包/分发 kit（host/ 工具、CI、Release、在线升级）；overlay/、base/、apply.sh 机制退役删除 |
| 上游关系 | 不主动 PR；自用 fork |

## 3. 目标结构

```
QC3284/immortalwrt 分支 e2631
├─ iw master @ 4765b657（钉点）
├─ 提交: kernel DWC3 glue / mt76 cache maint / sanechips target / H3600 设备
├─ 提交: e2631 设备支持（target/linux/sanechips/base-files/zte_zxhn-e2631、
│        image/Makefile 设备定义、package/e2631/*、seed 对应 .config）
└─ CI: .github/workflows/check.yml（make defconfig + 全量或增量门禁）
```

```
QC3284/zte-e2631-immortalwrt（保留，改为 kit）
├─ host/（mkfactory、verify_pkg、verify_img、release、publish）
├─ scripts/（bootstrap 改为 clone QC3284/immortalwrt@e2631，不再 git-am）
├─ .github/workflows/firmware.yml（clone 树 fork → make world → 打包 → Release）
├─ docs/ evidence/ tests/
└─ 删除: overlay/、base/、apply.sh、bootstrap 的 am 逻辑
```

## 4. 验收标准

1. 树 fork 在钉点上构建出的 sysupgrade 镜像与 v1.10.0 产物**逐字节一致**
   （sha256 对照；至少 payload 级一致 + make check 13/13）。
2. 树 fork 的 check.yml 绿；kit 的 check.yml / firmware.yml 绿（切换后）。
3. 真机无需重刷：若逐字节一致，已刷设备即树 fork 产物。
4. 在线升级、Release 流程在新 kit 上跑通（CI-only 验证，publish=false）。

## 5. 阶段

1. **组装树 fork**：fork iw → 分支 e2631 → 4 个 sanechips 提交（git am 后 am --abort 前先
   `git format-patch` 成提交）→ e2631 设备提交（overlay 内容搬入 target/package）→ 推送。
2. **树 CI**：树 fork 的 check.yml 构建验证（GitHub Actions）。
3. **逐字节对照**：树构建产物 vs v1.10.0 产物 sha256；不一致则修到一致。
4. **kit 瘦身**：删 overlay/base/apply.sh，bootstrap 改 clone 树 fork，firmware.yml 改走树构建。
5. **文档与收尾**：docs 更新、迁移记录落盘、真机状态复核（无需重刷）。

## 6. 风险与门禁

- **新仓库创建、推送、Release 均需用户批准**（新仓库已随本设计获批）。
- 载荷级一致是硬验收：任何不一致必须查明。实测结果（run 43572710065）：
  PASS-CONTENT-PARITY modulo provenance——全部差异溯源为构建来历（主机名/gitref/
  LuCI 版本串/apk 签名钥）；byte-identical 对 v1.10.0 参照因 apk 私钥未保留而
  数学上不可达，未来构建的可复现性定义为两次树 fork 构建自一致（P5-P8 已落地）。
- 迁移期间 v1.10.0 继续可用；旧机制在 kit 删除前保留在 git 历史中，可回退。

## 7. 进展记录（2026-11-14）

- **阶段 1 完成**：`QC3284/immortalwrt`（正血统 fork，parent immortalwrt/immortalwrt）分支
  `e2631`，tip 处含 7 个真实提交：4 个 sanechips（作者署名 Navid Ghahremani 保留）+
  板级 + 设备包 + seed/README。第 4 个 sanechips 提交树哈希 == 钉点 `4f89aa7a…`。
  旧仓 `immortalwrt-archive`（VIKINGYFY fork）原样保留。
- **阶段 2 完成**：树 fork 内 `.github/workflows/check.yml`（祖先断言 + 4 提交主题 +
  树哈希 + 关键文件 + defconfig 符号），runs 43567339762 / 43567461005 绿；kit 侧
  check-workflows 增「树 CI 存在且引用钉点」断言（fb4dd0a，run 43567626382 绿）。
- **阶段 3 完成**（535c0fe，parity run 43572710065 SUCCESS 1h24m45s，publish=false）：
  树 fork 构建产物与 v1.10.0 参照 **PASS-CONTENT-PARITY modulo provenance** ——
  8 处差异全部溯源为构建来历（KBUILD_BUILD_HOST 主机名 / gitrev.mk 嵌 GITREF /
  LuCI FETCH_HEAD detached 版本串 / apk 随机签名钥），内容层逐字节一致；
  byte-identical 对 v1.10.0 参照数学上不可达（v1.10.0 的 apk 私钥从未保留），
  不重跑。P5-P7（主机名/gitref/feed clone 归一）转入 task-12 未来构建自一致性硬化；
  P8 apk 密钥：默认随机，task-12 加可选输入注入钉定密钥（私钥不入库）。
- **阶段 4 完成**（57f1671，check.yml 43584081336 绿）：kit 瘦身收尾落地——
  pins 全部迁入 scripts/pins.env；overlay/(79)/base/(4 补丁+commits.env)/apply.sh/
  wsl/apply-gate.sh 删除（+1049/-19953）；bootstrap 纯树 fork（depth-1 构建树+
  scratch 历史断言+feed 分支克隆 reset 钉点）；四个设备原生源文件字节一致迁入
  tests/native/ 并加同步门；check.sh 13 门；P5（内核构建 id 固定）/P6（CI ref
  归一+miniupnpd 横幅断言）/P8（可选钉定 apk 密钥，私钥不入库不归档）；
  actions v5；check-workflows 66 项。真机无需重刷（parity 已证载荷一致）。
- **遗留门禁（不变）**：kit main 合入、正式 Release、真机操作均待用户批准。
- **质量整改批次（树 fork，2026-11-15）**：批1 = CI 提交重写补 SOB + extroot
  gate 快照标记（f3776b3）+ 删 WAN 放行（76dcaee）+ fstools 204 去 jffs2 噪音
  （72eff3b）+ 种子 CONFIG_KERNEL_DEVMEM=y（6b609d7）+ 风格清扫（b2e15d4），
  tip 83df1a9，树 CI 绿；批2 = marker 硬化（4b610dc）+ 5 脚本 SPDX（235fe12）+
  fwslot.c 字符串重构（cd14ffa，ASM_IDENTICAL），tip cd14ffa，树 CI 绿。每次
  重钉后 kit 以 RUN 验证：RUN1/RUN2 @ 83df1a9 逐字节自一致（A==B），RUN3 @
  cd14ffa 对基线 PASS-REVIEWED-DIFFS（内核差异实锤为 KBUILD_BUILD_TIMESTAMP
  构建戳），真机刷入 r0-cd14ffa，七项复验全过（marker 拒绝坏卷实测、DEVMEM、
  噪音清零、无 WAN 放行），冷启动累计 17/17。详见 evidence/qshou1-batch2-flash-
  20261115.md 与 t20b-repin-batch2-20261115.md。

## 8. 方向定调 (2026-11-14, 用户)
用户对「开发版/发布版」三选项的答复是第四条路: **按「合并到 immortalwrt 主线」的方向做**。即树 fork 保持 master 基底与 snapshot 身份(诚实), 修复队列与 4 个内核补丁以主线可合并质量为标准落入树 fork, 定期 rebase 跟踪 iw master; PR 动作维持「不主动」边界, 质量达标后由用户决定。
