# docs/ 索引

本目录按「先读什么」排序。所有条目都是本仓库历史与证据的一部分；状态描述以文件内
实际内容为准，本文只做导航。

## 从这里开始

| 文件 | 内容 |
|---|---|
| [architecture.md](architecture.md) | 地图：仓库结构、从源码到可启动镜像的链路、槽位几何、验证栈 |
| [immortalwrt-migration.md](immortalwrt-migration.md) | ImmortalWrt 基线迁移的决策、证据与风险；基底升级 runbook 在 §8 |
| [known-issues.md](known-issues.md) | 机器可读的诚实清单：每个已修/未修问题、证据与规避方式 |
| [updates.md](updates.md) | 在线更新机制：原地升级不变量、e2631-upgrade 流程、槽位适配 |
| `../BUILD.md`、`../README.md` | 构建步骤 / 状态与取舍（仓库根目录） |

## 实施记录（按任务）

| 文件 | 内容 |
|---|---|
| [immortalwrt-migration.md](immortalwrt-migration.md) | T1 决策 + T4 门禁/文档实施状态 + §8 基底升级 runbook |
| [t3-packaging-release-ci.md](t3-packaging-release-ci.md) | T3：产物名与版本口径、在线更新与镜像白名单修复、CI 改造、host 侧模拟证据、仍需 CI/真机证明的事项 |


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
- 迁移后的品牌为 `ImmortalWrt v1.10.0`、产物 `e2631-immortalwrt-*.bin`；旧基底只作为
  `E2631_BASE_KIND=legacy` 回退通道存在，见 [immortalwrt-migration.md](immortalwrt-migration.md)。
- 结论变更需附新证据并更新 [immortalwrt-migration.md](immortalwrt-migration.md) §7.1 与
  [known-issues.md](known-issues.md) 对应条目。
