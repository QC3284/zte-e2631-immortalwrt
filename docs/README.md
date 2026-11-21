# docs/ 索引

本目录按「先读什么」排序。所有条目都是本仓库历史与证据的一部分；状态描述以文件内
实际内容为准，本文只做导航。

## 从这里开始

| 文件 | 内容 |
|---|---|
| [architecture.md](architecture.md) | 地图：仓库结构、从源码到可启动镜像的链路、槽位几何、验证栈 |
| [immortalwrt-migration.md](immortalwrt-migration.md) | ImmortalWrt 基线迁移的决策、证据与风险；基底升级 runbook 在 §8 |
| [known-issues.md](known-issues.md) | 机器可读的诚实清单：每个已修/未修问题、证据与规避方式 |
| [救砖手册-2026-11-15.md](救砖手册-2026-11-15.md) | 救砖手册：串口 / U-Boot 控制台 / TFTP RAM 引导 / failsafe / 回原厂槽位路径 / 危险区与禁止事项 |
| [updates.md](updates.md) | 在线更新机制：原地升级不变量、e2631-upgrade 流程、槽位适配 |
| `../BUILD.md`、`../README.md` | 构建步骤 / 状态与取舍（仓库根目录） |

## 实施记录（按任务）

| 文件 | 内容 |
|---|---|
| [immortalwrt-migration.md](immortalwrt-migration.md) | T1 决策 + T4 门禁/文档实施状态 + §8 基底升级 runbook |
| [t3-packaging-release-ci.md](t3-packaging-release-ci.md) | T3：产物名与版本口径、在线更新与镜像白名单修复、CI 改造、host 侧模拟证据、仍需 CI/真机证明的事项 |
| [treefork-migration-design.md](treefork-migration-design.md) | T-12 设计：设备支持改为 QC3284/immortalwrt 树 fork 的真实提交，套件只留构建/打包/发布 |
| [../evidence/immortalwrt-verify-20261114.md](../evidence/immortalwrt-verify-20261114.md) | T5：ImmortalWrt 适配的端到端构建与产物验证报告（本地门禁、CI run、产物 sha256、未覆盖项） |
| [../evidence/t20-verification-20261114.md](../evidence/t20-verification-20261114.md) | T-20：树 fork 重钉重建对的独立验证（RUN1/RUN2 产物哈希、两层门禁、APK 钉值、A==B 逐字节一致、与基线差异复核） |
| [../evidence/cold-boot-sampling-20261114.md](../evidence/cold-boot-sampling-20261114.md) | T-19 与回归：MT7916 冷启动采样（v1.10.0 11/11 + r0-83df1a9 3/3，累计 14/14，0 失败签名）与完成度只读核查 |
| [../evidence/r-verify4-parity-20261115.md](../evidence/r-verify4-parity-20261115.md) | R-验4：RUN5 merge 候选 parity（PASS-REVIEWED-DIFFS、kernel merge-class 归因、RUN4 失败记录） |
| [../evidence/c-plan-parity-20261121.md](../evidence/c-plan-parity-20261121.md) | C-验1：RUN6（方案 C，target 改名 zx279128）对 RUN5 的 parity 验收（RUN6 v3 PASS-REVIEWED-DIFFS，expected 23 / allowed 13 / unexpected 0，kernel STAMP-ONLY，含首轮 5 条归因与负对照） |
| [../evidence/t38/](../evidence/t38/) | task-38 验收附件：verify-task38.sh、终稿策略、端到端日志、比较器/kernel-deep/verify_img 报告、负对照 |
| [../evidence/p2-oob-recon-20261121.md](../evidence/p2-oob-recon-20261121.md) | P2-P1：mtd0 OOB 只读取证（512 页表、normal/RAW 全 FF、跨分区对照、ECC 布局未证实、READID 推断、U-Boot 区界核对） |
| [../evidence/p2-oob/](../evidence/p2-oob/) | task-42 取证附件：OOB 表/二进制、headblock/env/secondboot hex、会话日志、工具源码与 sha256 清单 |
| [../evidence/a1-banner-acceptance-20261121.md](../evidence/a1-banner-acceptance-20261121.md) | task-49/task-50 设备段：A1/A2 u-boot.bin 经 vendor xmodem 装入 RAM 并 go 的 banner/prompt 验收（A1 4910ee2045bd、A2 38bee433d177；mtd list + 两次只读读回；零 flash 写入以 mtd0 sha256 前后一致实证；含工具缺陷修复与主机路由陷阱记录） |
| [../evidence/a1-banner-acceptance/](../evidence/a1-banner-acceptance/) | task-49 验收附件：驱动脚本、session/a2 results JSON、驱动与 health 日志、串口选段 |


| 文件 | 内容 |
|---|---|
| [01-情报汇总与事实核验-2026-10-13.md](01-情报汇总与事实核验-2026-10-13.md) | 事实总表：A 级=从字节重算，B 级=读到一次，C 级=推断；含包格式逐字段验证 |
| [02-实施计划-2026-10-13.md](02-实施计划-2026-10-13.md) | 工作日志（按节，含被证伪的假设——重试前值得先读） |
| [原厂加速方案逆向-2026-10-28.md](原厂加速方案逆向-2026-10-28.md) | PPE / NPP / IDM / TM 私有加速栈的逆向结论 |
| [原生无线驱动重写-2026-11-02.md](原生无线驱动重写-2026-11-02.md) | `native` 分支：不用 mt76，按原厂 4.1.25 二进制重写 WFDMA/MCU 层的过程与结论 |
| [wanlan-adaptive-逆向记录-2026-10-27.md](wanlan-adaptive-逆向记录-2026-10-27.md) | 原厂 WAN/LAN 自适应机制与手动 WAN 口实现的依据 |
| [有线吞吐测量-2026-10-29.md](有线吞吐测量-2026-10-29.md) | 有线吞吐 / 硬件卸载实测数据 |
| [p2-7-wifi-accel-评估-2026-10-28.md](p2-7-wifi-accel-评估-2026-10-28.md) | Wi-Fi 硬件加速路线评估 |
| [v1.5-驱动对齐与逆向移植报告-2026-10-28.md](v1.5-驱动对齐与逆向移植报告-2026-10-28.md) | v1.5 驱动对齐与逆向移植报告 |
| [refs-local/](refs-local/) | 早期本地调研笔记（原厂分区/挂载/硬件视图/槽位定案等，纯文本） |

## 版本记录

| 文件 | 内容 |
|---|---|
| [relnotes-v1.9.0.md](relnotes-v1.9.0.md) | v1.9.0：47 MiB userdata 自动接管、槽位布局扩到 17M、内置插件、homeproxy |
| [relnotes-v1.8.0.md](relnotes-v1.8.0.md) | v1.8.0 更新日志 |
| [v1.3-progress.md](v1.3-progress.md)、[v1.4-progress.md](v1.4-progress.md) | v1.3 / v1.4 阶段进展记录 |

## 维护约定

- `board/` 下的 `ser-*.log`、`firstboot-openwrt.txt` 是采集到的设备证据，**保留原样**（含旧品牌字样）。
- 迁移后的品牌为 `ImmortalWrt v1.10.0`、产物 `e2631-immortalwrt-*.bin`。T-12 起设备支持
  落在 [QC3284/immortalwrt](https://github.com/QC3284/immortalwrt) 的 `e2631` 分支；套件
  不再包含 overlay / patch series / `apply.sh`，旧基底通道已退役，见
  [immortalwrt-migration.md](immortalwrt-migration.md)。
- 结论变更需附新证据并更新 [immortalwrt-migration.md](immortalwrt-migration.md) §7.1 与
  [known-issues.md](known-issues.md) 对应条目。
