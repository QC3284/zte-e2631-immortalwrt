# R-验4：a4ba8240 上游合并 + firewall4 fullcone 重锚构建的独立验证（RUN5）

状态：**完成（GREEN，2026-11-21 02:5x CST）**。RUN4（43679059048）在构建阶段因上游 firewall4
源码更新导致 fullcone 补丁无法套用作废；树尖重锚（5202d4ca）后由 RUN5（44766496013）完成验证。
本文件的结果全部由 host 侧独立复算，不依赖 CI 自报。

## 1. 目的与验收口径

树 fork 把 immortalwrt/immortalwrt master 从 4765b657 合并到 a4ba8240（122 个上游提交，内核版本仍
6.18.60），得到 3ac18fb9；上游同时把 firewall4 源码从 e6f600c4 推到 3722eadc，使 e2631 的
firewall4 fullcone 补丁（001）失配。树尖以 5202d4ca（firewall4: re-anchor fullcone patch against
3722eadc，只改补丁 16 行）重锚后，kit 重新钉住并派发 RUN5。要回答三件事：

1. 产物本身可用：SHA256SUMS 自洽、host/verify_pkg.mjs 全过、tools/verify_img.mjs 报 BOOT-READY、
   apk 数据库里内核 config 哈希与 RUN3/基线一致、嵌入的 APK 公钥等于钉住的 PEM；
2. 相对 RUN3 的差异全部可以归因：合并桶（上游包更新）+ fullcone 重锚桶 + 上游默认配置桶 +
   构建戳，没有未解释项；
3. 相对基线 43572710065 的差异 = t20b 修复系列桶 + 本次合并桶 + 重锚桶 + 构建戳，没有未解释项。

**内核口径（本轮新增）**：合并把参考内核补丁集（target/linux/generic/patches-6.18）改了 13 个文件，
内核二进制因此合法地重新编译、布局改变，kernel-deep-compare 报 NON-STAMP-DIFF。这一点不再用
STAMP-ONLY 口径硬套，而是走 merge-class 证明（§3、§5.4）：内核 config/版本/seed 不变 + 改动文件
全部落在允许的内核输入路径 + 至少一个 generic 补丁变化，证明文件写入
kernel-merge-class-<tag>.json。风险：内核行为跟随上游参考补丁，Q-收1 真机回归需要覆盖。

### RUN4 历史（作废，不作为验收依据）

- RUN4 = 43679059048 @ kit 3df3dcb / tree 3ac18fb9，publish=false、pinned key；构建步骤约 1h16m 后
  失败：package/network/config/firewall4/patches/001 无法套用到上游 firewall4 3722eadc。
- 修复：树 5202d4ca 只改 001 补丁 16 行（re-anchor）；kit fd80c1a 重钉。这不是设备代码问题。
- RUN4 没有产物、没有下载，判废；证据骨架保留在 git 历史里。

## 2. 输入与基线

| 角色 | 标识 |
| --- | --- |
| RUN5（本次候选） | run 44766496013，kit fd80c1a2b5d58f191096142cb8e1816bb9131d46，tree fork 5202d4ca，2026-11-20T15:45:38Z 到 17:59:41Z（2h14m03s），publish=false，use_pinned_apk_key=true |
| RUN5 产物 | artifact e2631-build-44766496013（18,781,092 B）；bin 22,020,628 B，sha256 3a5914edac7dd973c4a86c2c97de5854ed348466701204d5d0903b1972439050 |
| RUN3（已验收的重钉构建，参照） | run 43623162108，tree cd14ffa，bin sha256 3d7825c9fdb9a15992ab72393014ce6c13211d76757f162bbe8b3b8cf8dbb13d，revision r0-cd14ffa |
| 基线（v1.10.0 复现构建） | run 43572710065，bin sha256 4e31df936cec8c02fd25cff83d98efc59c10bc2e877149d7f3c411a6dd2f9e9f |
| 上游 | merged master a4ba8240（2026-11-14）；iw base 4765b657；base tree 4f89aa7a；feeds packages decf9463 / luci ad75cde8；内核 6.18.60 |
| 期望身份 | revision r0-5202d4c（7 字符短 tip），base-files 1~5202d4c，内核 config 哈希 6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1，APK 公钥 = 钉住的 PEM（DER sha256 b0cbe6fb...） |

RUN5 SOURCE-INFO 关键行（来自产物字节，不是 CI 自报）：Kit commit fd80c1a...；ImmortalWrt base
4765b657...；Port base tree 4f89aa7a...；Tree fork QC3284/immortalwrt e2631 @ 5202d4ca...；
Merged ImmortalWrt master @ a4ba8240...（2026-11-14）；Kernel 6.18.60；Packages commit decf9463...；
LuCI commit ad75cde8...；APK signing key public key sha256 9edb11a9...；Hardware tested: NO。

## 3. 预期差异分类（评审策略桶）

- **合并桶**（RUN3 到 RUN5）：mac80211/cfg80211 7.2-r12 到 r14、busybox 1.38.0-r4 到 r5、
  uhttpd ca796d7d 到 93b05e0b、procd r1 到 r2、ppp 2.5.4-r7 到 2.5.5-r1（插件路径 2.5.4 到 2.5.5）、
  firewall4 e6f600c4 到 3722eadc、fstools 907cf449 到 5e371ec、fullconenat-nft PKG_RELEASE 3 到 4
  （上游提交 d42cc475c6 fullconenat-nft: honour the port range and the flags）、base-files 增
  path_normalize() 等。
- **重锚桶**：firewall4 001 补丁重锚（用户态 fw4 重建）；nft_fullcone.ko 与 r4 版本来自合并桶的
  fullconenat-nft 提交，不是重锚提交（重锚只改 001 补丁）。
- **上游默认配置桶**：firewall4 仓库 e6f600c4 到 3722eadc 更新了 root/etc/config/firewall：
  Allow-DHCPv6 增加 dest_ip fe80::/10（config: add dest addr restrictions for DHCPv6 rules），
  两条过期注释行删除；mangle-rule.uc 被移除（templates: remove stray file）。本地
  fullcone/flow_offloading 设置不变。
- **内核 merge-class 桶**：见 §5.4。只允许"generic 补丁集变化"这一种解释，且必须通过
  verify-task26.sh --kernel-merge-class 重新推导（config/版本/seed 不变、改动路径受限、至少一个
  generic 补丁变化），不接受"内核随便变"。
- **不允许**（仍须逐字节一致，否则失败）：内核 config 哈希、modules.builtin(.modinfo)、compat.ko、
  e2631 全部脚本、APK 公钥。

## 4. 工具与自测

- parity-tools/verify-task26.sh：下载 -> SHA256SUMS -> SOURCE-INFO 断言 -> extract-payload ->
  verify_img -> apk DB 断言 -> 两条 compare-parity -> kernel-deep ->（本轮新增）
  --kernel-merge-class 归因 -> APK 公钥比对。
- 策略：t26-policy-merge.json（58 rootfsExact + 15 packageV + versionFiles + infoKeys）、
  t26-policy-baseline.json（107 rootfsExact + 16 packageV + apkKey + versionFiles）；每条都带
  上游提交/包版本级理由。
- 自测（用 RUN3 作候选，修复前策略）：baseline 到 RUN3 PASS-REVIEWED-DIFFS expected 20 /
  unexpected 0；RUN3 到 RUN3 PASS-BYTE-IDENTICAL；kernel-deep IDENTICAL；而 baseline 到 RUN3（用
  merge 策略）FAIL 53 unexpected，证明策略不能当橡皮章。报告在 t26/selftest-*（仓库外）。
- kernel-deep：解 uImage 内 XZ zImage，逐字节分类 UTS/epoch/build-id；NON-STAMP 必须走归因或失败。

## 5. RUN5 结果（全部 PASS，verify-task26 退出码 0）

### 5.1 产物与门禁

- 下载 + sha256sum -c SHA256SUMS：2/2 成功（bin、SOURCE-INFO）。
- verify_pkg（host/verify_pkg.mjs）：参考与候选都 ALL CHECKS PASSED (warnings: 1)，fails=0；
  1 条 warning 是预期的 uImage ih_hcrc 时间戳告警。
- verify_img：BOOT-READY；uImage name 为 ARM ImmortalWrt Linux-6.18.60；DTB model 为
  zte,zxhn-e2631 / compatible zte,zx279128s；rootfs 为 squashfs（used=0xc480eb / file=0xc60000）。
- 版本头（host 解析，outer/inner magic 与 CRC1/CRC2 均验过）：version 为 ImmortalWrt v1.10.0，
  product 为 ZXHN E2631 V1.0.0，hw 为 V1.1.1，build 为 20261120，key 为 0x1351/0x5211，
  bodySize 为 0x1500000，slotA 为 0x700000+0x1c00000，slotB 为 0x2300000+0x1c00000，
  kSize 为 0x3fffe0，rSize 为 0xc60000，rFileOff 为 0x400214，serial 1。
- APK DB：内核 config 哈希 6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1 不变；base-files 为
  1~5202d4c；kmod-mac80211 为 6.18.60.7.2-r14；fstools 为 2026.11.07~5e371ec；ppp 为 2.5.5-r1。
- 嵌入 APK 公钥 DER sha256 b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d =
  钉住的 PEM；rootfs 中无任何私钥材料。

### 5.2 相对基线 43572710065

PASS-REVIEWED-DIFFS：expected 22 / allowed 103 / unexpected 0。允许项 = t20b 修复系列桶
（DEVMEM、extroot 门禁、WAN access、fstools 204、seed 归一）+ 本次合并桶 + 重锚桶 + 构建戳。

### 5.3 相对 RUN3 43623162108

PASS-REVIEWED-DIFFS：expected 20 / allowed 48 / unexpected 0。首轮 9 条未解释项全部归因后写入策略：

- etc/config/firewall：firewall4 上游默认配置更新（DHCPv6 dest_ip fe80::/10；见 §3）；
- firewall4.list / firewall4.conffiles_static：mangle-rule.uc 移除 + 新 conffile 哈希；
- lib/modules/6.18.60/nft_fullcone.ko：fullconenat-nft d42cc475c6（r3 到 r4），20,576 到 21,172 B；
- usr/lib/pppd/2.5.4（删）/ 2.5.5（增）：ppp 2.5.5 插件目录迁移；
- lib/apk/db/installed + scripts.tar.gz：上述包版本/脚本的派生记录；
- apk 包 kmod-nft-fullcone：6.18.60.2023.05.17~07d93b62-r3 到 -r4。

### 5.4 内核（merge-class）

- kernel-deep：解压后内核 13,159,680 B（同尺寸），sha256 4f64220c... 到 59a20c32...，
  differing bytes 2,371,928 / 253,931 ranges；uImage 数据 3,491,850 到 3,491,546 B，
  ih_time 1794677928 到 1795188482。verdict 为 NON-STAMP-DIFF。
- 归因（attestation：evidence/t26/kernel-merge-class-44766496013.json）：ref tree cd14ffa 到
  cand tree 5202d4ca 的内核输入差异共 66 个文件 = 13 个 target/linux/generic/patches-6.18 文件
  + 53 个 package/kernel 文件（kmod 包输入）。13 个 generic 文件由 4 个上游补丁提交带入：
  - 7b26f9c0d8 generic: backport phylib PHY interrupt restore（802-01..04、801-01、896-03）；
  - 0642965749 generic: 6.18: add quirk for OEM SFP+ONU-XGSPON（757、750-753）；
  - 4d5d291a26 kernel: wireguard: fix sticky source address on p2p interfaces（792）；
  - b12b44bfdf generic: link the DMA-BUF heaps into dma-shared-buffer（904-debloat_dma_buf）。
  内核 config 哈希、target/linux/generic/kernel-6.18（6.18.60）、seed/config 均未变；
  target/linux/sanechips 0 改动。
- 结论：内核二进制差异是本次上游合并的合法结果（参考补丁集变化导致内置代码重编译与布局移动），
  不是 e2631 自有内核补丁变化。残余风险：内核行为跟随上游参考补丁；Q-收1 真机回归必须覆盖
  （net-phy / SFP / DMA-BUF / wireguard 相关路径）。

### 5.5 与 pkg-release 的事实边界

本卡只负责 host 侧复算；CI 自报的 publish skipped / no Release、artifact 上传、SOURCE-INFO 原文
由 pkg-release 独立核对。两边的 bin sha256/字节数、版本头、APK 公钥一致（见 §2、§5.1）。

## 6. 结论

- **GREEN**：RUN5 产物在 host 侧全部门禁通过；相对 RUN3 与基线的差异 = 合并桶 + 重锚桶 +
  上游默认配置桶 + 构建戳，unexpected=0；内核差异按 merge-class 证明归因并保留残余风险说明。
- **不把内核写成未变**：本轮内核载荷确实变了（NON-STAMP），但输入变化全部可追溯到上游参考补丁集。
- 下一步：RUN6（目标名 sanechips 到 zx279128 重命名）对 RUN5 做 PASS-REVIEWED-DIFFS；Q-收1
  真机刷写/回归由用户批准后执行，需要覆盖内核对网络路径的影响。
- 证据落盘：本文件 + evidence/t26/（策略、verify 脚本、kernel-deep、attestation、两份对比报告、
  运行日志）。本轮不 push、不发布 Release、不碰真机。

## 附录 A：复算命令

    cd /home/qc233/zte/e2631-t5-artifacts/parity-tools
    bash verify-task26.sh 44766496013 --kernel-merge-class

（脚本会先 gh run download 并 sha256sum -c，再跑全部 host 侧门禁；输出见 evidence/t26/run5-verify.log。）

## 附录 B：证据文件

- evidence/t26/verify-task26.sh：本次一键复算脚本（含 merge-class 归因）。
- evidence/t26/t26-policy-merge.json：RUN3 到 RUN5 的评审策略（58 rootfsExact + 15 packageV）。
- evidence/t26/t26-policy-baseline.json：基线到 RUN5 的评审策略（107 rootfsExact + 16 packageV）。
- evidence/t26/kernel-deep-44766496013.md / .json：解压内核逐字节分类明细。
- evidence/t26/kernel-merge-class-44766496013.json：内核 merge-class 归因（66 个内核输入文件、
  两条硬性条件、残余风险说明）。
- evidence/t26/baseline-vs-RUN5-reviewed.md / .json：基线到 RUN5 的对比报告。
- evidence/t26/RUN3-vs-RUN5-reviewed.md / .json：RUN3 到 RUN5 的对比报告。
- evidence/t26/run5-verify.log：verify-task26 的完整运行日志（VERIFY_EXIT=0）。
