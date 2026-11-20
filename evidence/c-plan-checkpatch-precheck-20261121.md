# 方案 C 预演：结构盘点 + checkpatch 基线（C-研1，task-34）

- 日期：2026-11-21 ｜ 角色：iwrt-baseline ｜ 任务：task-34（S1/S3 准备）
- 输入：设计稿 kit iwrt-adaptation \`ec37b96\` docs/mainline-alignment-design.md；
  树 fork QC3284/immortalwrt 分支 \`e2631\` tip \`5202d4ca\`（本地 /home/qc233/zte/iwrt-tree）；
  checkpatch \`scripts/checkpatch.pl\` 版本 \`0.32-openwrt\`。
- 只读：未改树 fork；kit 仓库除本文件外无改动（本文件也未提交，等 Lead 审）。
- 结论：**GREEN**。D5 六项全部"符合"或"合并后符合"（唯一动作 = 既定的
  image/Makefile 合并）；checkpatch 按"新系列最终内容"口径，在 D7 门禁范围内共
  **28E/22W，全部落入 3 类有据豁免**，豁免后 0E/0W。S2 不需要为门禁改内容，但
  **系列必须"构造即干净"**（§3.5），另有 4 项待 Lead 决策（§6）。

## 1. 方法与口径

### 1.1 为什么用 \`-g <commit>\`，不用 \`git show | checkpatch -\`

实测（同一条 commit a6c47309）：\`git show a6c47309 | checkpatch --no-tree -\` 会因
管道里没有 \`From:\` 头而误报 3 条（COMMIT_LOG_LONG_LINE 属真、BAD_SIGN_OFF /
NO_AUTHOR_SIGN_OFF 属误报）；\`-g a6c47309\` 为 0E/0W。门禁必须用 \`-g\`：它按
commit 取作者/SOB，且自动忽略 merge 提交。

- 检查命令：\`perl scripts/checkpatch.pl --no-tree --show-types -g <sha>\`
- 注意：\`--terse\` 的输出是 \`<commit>:<patchline>: ERROR:TYPE: msg\`，**没有文件路径**；
  按路径豁免必须解析默认输出的 \`#N: FILE: <path>:<line>:\` 上下文行。树内旧文档
  docs/checkpatch-exemptions.md:3-4 写的 \`--terse\` 命令要改（见 §5.3）。

### 1.2 两组口径

- **A 口径（历史回放）**：直接对 D3 列的源提交跑 \`-g\` → 老提交的历史违规
  （§3.1）。用于核对"清理来源"，不代表新系列。
- **B 口径（新系列最终内容）**：\`git diff a4ba8240 5202d4ca -- <分组路径>\` 后跑
  checkpatch（§3.3）。D4 不变式要求新系列 tip 树 = 旧 tip 树 + 四类允许差异，故
  最终内容级违规与提交切分无关；**B 口径 = 门禁真正会看到的违规**。
- D7 门禁范围（按 D1 改名后的路径）：\`target/linux/zx279128/{image,base-files,generic,dts}/**\`
  + \`package/e2631/**\`；所有补丁文件（\`**/patches/**\`、\`*.patch\`）显式排除。

## 2. 结构盘点（D5 逐项）

| # | D5 项 | 判定 | 先例（a4ba8240 实测） |
|---|---|---|---|
| 1 | base-files/ 留在 target 根 | **符合**，不动 | target/linux/ipq40xx/base-files/（40 个 target 都在 target 根放 base-files；ipq40xx/base-files/etc/init.d/bootcount 为 100755） |
| 2 | dts/ 放 target 根 | **符合**，不动 | target/linux/ipq40xx/dts/（128 个 .dts，17 个 target 用 target 根 dts/ 目录） |
| 3 | image/Makefile 单文件 | **须合并**（唯一结构动作） | target/linux/ixp4xx/image/Makefile（189 行单文件）；octeon（123 行）；armsr（120 行）；22 个 target 的 image/ 没有 *.mk 拆分文件 |
| 4 | config-6.18 命名 | **符合**，不动 | target/linux/ipq40xx/config-6.18（35 个 target 用 config-6.18，命名 = config-$(KERNEL_PATCHVER)） |
| 5 | DEVICE_ 符号是主线标准形态 | **符合**，不改符号 | scripts/target-metadata.pl:316 \`menuconfig TARGET_DEVICE_$target->{conf}_$profile->{id}\`；include/image.mk:571 消费 \`CONFIG_TARGET_DEVICE_PACKAGES_…\`；本树 seed:7 与树 CI check.yml:111 已按此断言并通过 defconfig |
| 6 | package/e2631 用 emortal 先例 | **符合**，不迁移 | package/emortal/{autocore,automount,autosamba,cpufreq,default-settings}（5 个子包，SPDX 头 + 必要时 PKG_FLAGS:=nonshared）；e2631 的 5 个包同构 |

补充实测：

- 2.1 target 目录布局与 ipq40xx 同构：\`Makefile, config-6.18, base-files/, dts/,
  files/, generic/, image/, patches-6.18/\`（ipq40xx 额外有 chromium/mikrotik 子目录，
  属其多 subtarget 需要，不是主线强约束）。
- 2.2 target Makefile 字段（target/linux/sanechips/Makefile:5-21）与 ipq40xx 同构：
  ARCH/BOARD/BOARDNAME/FEATURES/CPU_TYPE/SUBTARGETS/KERNEL_PATCHVER/KERNELNAME/
  DEFAULT_PACKAGES。D5 要求 FEATURES、KERNELNAME、wpad-basic-mbedtls 不动——现状
  已满足（:8、:14、:20）。
- 2.3 image/Makefile 合并要点（合并后 62+78 = 140 行，仍符合小 target 惯例）：
  a) 把 Makefile.e2631 的 \`E2631_VENDOR_TEMPLATE\`、\`Device/zte_zxhn-e2631\`、
     \`Build/e2631-factory\` 移到 \`$(eval $(call BuildImage))\` 之前，删掉
     image/Makefile:60 的 include；
  b) Makefile.e2631:18 的绝对路径 \`DEVICE_DTS_DIR := $(TOPDIR)/target/linux/sanechips/dts\`
     改为 Device/Default 的 \`../dts\`（ipq40xx image/Makefile 同款写法），顺带消掉
     改名敏感点；
  c) Makefile.e2631:3-4 的 "apply.sh makes … include this file" 注释已过期（当前是
     树内直连），合并时删除。
- 2.4 BOARD 必须与目录名一致：include/target.mk:76 用 \`target/linux/$(BOARD)\` 定位
  PLATFORM_DIR，所以 D1 改名必须 \`BOARD:=zx279128\` + 目录 \`target/linux/zx279128/\`
  同时改，漏一个就找不到 target。

### 2.7 连带影响（供 task-35/36，属盘点而非新工作）

- 改名功能性引用（必须改）：target/linux/sanechips/Makefile:6-7（BOARD/BOARDNAME）、
  image/Makefile:60（include 路径，D5 合并后消失）、image/Makefile.e2631:18（DTS 路径，
  D5 合并后统一为 ../dts）、seed/e2631.config:4,5,7（CONFIG_TARGET_* / DEVICE 符号）
  与 :19 注释、package/e2631/zte-mesh/Makefile:10,30（\`@TARGET_sanechips\`）、
  .github/workflows/check.yml（15 处路径/断言）。
- **不要改**的内核/驱动层名字：target/linux/sanechips/config-6.18:444
  \`CONFIG_SANECHIPS_PHY=y\`、files/drivers/net/phy/sanechips.c 的驱动符号
  （sanechips_phy_driver 等）、patches-6.18 里 005/007/019/027 的补丁内容——它们是
  内核驱动/补丁 provenance，不是 target 标识；改名会破坏补丁 sha256 与内核符号。
  DTS 注释里的 "Sanechips ZX279128 SoC" 属描述文字，可留（不进门禁）。
- 树 CI check.yml 的旧断言在新系列全部失效，S2 必须同步改：E2631_IW_SHA（:27，
  换成新基底 a4ba8240）、E2631_PORT_TREE_SHA 4f89aa7a 钉点（:29，旧系列重建后不再
  存在）、四个 port 提交 subject（:59-62，sanechips:→zx279128:）、文件存在断言
  （:76-86，image/Makefile.e2631 合并后消失、路径改名）、seed grep（:109-111）。

## 3. checkpatch 预演

### 3.1 A 口径：D3 源提交逐提交清单（19 个）

| commit | 主题 | E/W | 违规类型（数量） |
|---|---|---|---|
| 6cf5f6d7 | kernel: add generic DWC3 platform glue package | 0/0 | — |
| 35270f0c | mt76: serialize device reads with outer cache maintenance | 0/0 | — |
| a6c47309 | sanechips: add ZX279128S target | 0/0 | — |
| 67101828 | sanechips: add support for ZTE ZXHN H3600 | 2/25 | EXECUTE_PERMISSIONS 2、SPDX_LICENSE_TAG 6、LONG_LINE_COMMENT 16、LONG_LINE 2、COMMIT_LOG_LONG_LINE 1 |
| f2d03c4a | sanechips: add ZTE ZXHN E2631 board support | 45/45 | SPDX_LICENSE_TAG 35、EXECUTE_PERMISSIONS 24、TRAILING_WHITESPACE 21、BLOCK_COMMENT_STYLE 6、UNSPECIFIED_INT 3、LONG_LINE 1 |
| 8a253ea8 | e2631: add the E2631 device packages | 29/34 | SPACING 24、SPLIT_STRING 17、TYPO_SPELLING 8、BLOCK_COMMENT_STYLE 3、EXECUTE_PERMISSIONS 2、SPDX_LICENSE_TAG 3、TRAILING_WHITESPACE 3、LONG_LINE_STRING 2、LINE_SPACING 1 |
| e96aed31 | e2631: add the image seed and build notes | 0/0 | — |
| 8a06f47 | ci: add a static tree gate for the e2631 branch | 0/0 | — |
| 3dbeadce | ci: use actions/checkout@v5 (node24) in the tree gate | 0/0 | — |
| f3776b32 | e2631: gate the userdata extroot on a snapshot marker | 0/6 | SPDX_LICENSE_TAG 3、LONG_LINE 3 |
| 76dcaee7 | e2631: keep SSH and HTTP(S) off the WAN by default | 0/0 | — |
| 72eff3b7 | e2631: skip the fstools jffs2 sync when there is no upper | 2/0 | TRAILING_WHITESPACE 2（fstools 补丁文件） |
| 6b609d7e | e2631: request CONFIG_DEVMEM where it is decided (seed + tree CI) | 0/0 | — |
| b2e15d46 | e2631: clean up coding style in the tree files | 0/0 | — |
| 83df1a90 | docs: record the e2631 history rewrite and force-push rules | 0/0 | — |
| 4b610dc5 | e2631-userdata: never write or accept an empty snapshot marker | 0/1 | COMMIT_LOG_LONG_LINE 1 |
| 235fe125 | e2631: add the missing SPDX tags to the target scripts | 0/0 | — |
| cd14ffa | e2631-fwslot: put each split user-visible string on one line | 0/12 | LONG_LINE 6、LONG_LINE_STRING 6 |
| 5202d4ca | firewall4: re-anchor fullcone patch against 3722eadc | 0/0 | — |

逐文件明细（只列有违规者，命令见 §7）：

- **67101828**（2E/25W）：2E = base-files/etc/rc.button/lights_toggle、
  etc/rc.wps/00-h3600-ledblink 的 EXECUTE_PERMISSIONS；W = platform.sh 19（SPDX 1 +
  16×LONG_LINE_COMMENT 145 列历史 \`printf '\000…'\` + 2×LONG_LINE）、02_network/
  11-mt76-caldata/05-fix-wifi-mac 各 1 SPDX、提交描述 1。**16 条历史长行已随
  f2d03c4a 重写 platform.sh 消失**（D3 #4 备注）；SPDX 已由 235fe125 补齐；EXEC 保留。
- **f2d03c4a**（45E/45W）：24E = 24 个 base-files 脚本（init.d 7 + sbin 17）执行位；
  21E TRAILING_WHITESPACE = overlay 期脚本/补丁；SPDX 35 = 35 个 base-files 脚本缺头；
  BLOCK_COMMENT_STYLE 6（slotpart-core.c 4、ffe.c 2）、UNSPECIFIED_INT 3（ffe.c）、
  LONG_LINE 1（platform.sh:130）。以上除执行位外**都已在最终内容里清掉**。
- **8a253ea8**（29E/34W）：e2631-fwslot.c 47（SPACING 24、SPLIT_STRING 17、
  BLOCK_COMMENT_STYLE 3、LONG_LINE_STRING 2、TYPO 8 等）；e2631flash.js TYPO 8；
  rpcd/e2631 与 rpcd/e2631-wanport 各 1E（EXECUTE_PERMISSIONS）+ 1W（SPDX）；
  fstools 203 补丁 2E、mt76 002 补丁 1W。最终内容里只剩 §3.3 的三类。
- **f3776b32**（0/6）：e2631-snapshot.sh 4（SPDX 3 + LONG_LINE 1）、
  init.d/e2631-userdata 1 SPDX、preinit/79_e2631_userdata 1 SPDX——已由 235fe125 修掉。
- **72eff3b7**（2E）：fstools 204 补丁 trailing whitespace（补丁语法，非代码）。
- **cd14ffa**（0/12）：e2631-fwslot.c 12 处 100 列以上（6 LONG_LINE + 6 LONG_LINE_STRING）
  ——这是"把用户可见串合并回一行"后的必然结果，最终内容仍有（见 E3）。
- **4b610dc5**（0/1）：提交描述 1 行超 75 字符（消息级，新系列重写消息时清掉）。

### 3.2 A 口径的用途与局限

A 口径是老历史的"清理来源台账"：SPDX×6、trailing whitespace、BLOCK_COMMENT_STYLE、
UNSPECIFIED_INT、platform.sh 历史长行都已进最终内容前的提交清掉；执行位、
fwslot 长行、TYPO 属有据豁免。**新系列若原样回放老 commit 内容，这些老违规会
在中间提交重新出现**——所以 S2 必须"构造即干净"（§3.5）。

### 3.3 B 口径：新系列最终内容分组（门禁预测）

分组按新系列提交映射（\`git diff a4ba8240 5202d4ca -- <路径>\`；路径用改名前的
sanechips，改名后同构）：

| 组 | 路径 | E/W | 明细 | 门禁内 |
|---|---|---|---|---|
| G1 | package/kernel/linux/modules/usb.mk | 0/0 | — | 否（但 port #1 提交自洽） |
| G2 | package/kernel/mt76/** | 1/0 | patches/002 trailing whitespace（补丁语法） | 否 |
| G3core | target/linux/sanechips/{Makefile,config-6.18,files/,generic/} | 0/0 | 7094 行全干净（含全部 C 驱动） | 否（D7 枚举未含 files//Makefile/config，见 §6-D1） |
| G3patches | target/linux/sanechips/patches-6.18/** | 21/0 | TRAILING_WHITESPACE：029×18、030×2、034×1（补丁语法） | **排除**（D3/D7 明文） |
| G45board | target/linux/sanechips/{base-files,dts,image}/** | 26/0 | 26×EXECUTE_PERMISSIONS（init.d 7、sbin 17、rc.button 1、rc.wps 1；hotplug 11-mt76-caldata 1） | **是（28E 中的 26）** |
| G6pkg | package/e2631/** | 2/22 | EXECUTE_PERMISSIONS 2（rpcd）；LONG_LINE 6 + LONG_LINE_STRING 8（e2631-fwslot.c）；TYPO_SPELLING 8（e2631flash.js 的 callE2631* 误报） | **是（2E/22W）** |
| G7seed | seed/**, README.e2631.md | 0/0 | — | 否 |
| Gqother | fstools/firewall4 补丁、generic/config-6.18、docs、check.yml | 4/0 | 203×2 + 204×2 trailing whitespace（补丁语法） | 否 |

**门禁范围内合计：28E/22W = 26+2 执行位（E1）+ 14 行长（E3）+ 8 拼写误报（E4）。**
三类都有据豁免（§4），豁免后 0E/0W；不需要为门禁改任何内容。

### 3.4 消息级（不是内容豁免，S2 必须做到）

- 新系列消息 ≤75 字符换行（checkpatch COMMIT_LOG_LONG_LINE）：老提交里
  67101828、4b610dc5 各 1 条，重写消息时清掉。
- 署名（D3）：port #1-#4 保留原作者 author 与日期、保留原作者 SOB，**追加我们的
  SOB**。实测：\`git format-patch -1 6cf5f6d7\` 消息尾追加
  \`Signed-off-by: QC3284 <2078725082@qq.com>\` 后 \`checkpatch --no-tree\` = 0E/0W
  （checkpatch 的 NO_AUTHOR_SIGN_OFF 只要求作者有匹配 SOB，多一条我们的 SOB 不报）。
  自写提交（#5-#8+）用我们的 SOB。
- 每个提交 subject 前缀按 D3（zx279128: / mt76: / e2631: / ci: / firewall4:）。

### 3.5 门禁前提：系列构造即干净

门禁按提交逐个跑，所以**中间提交也不能脏**。S2 重建时必须把风格清理折进"首次
引入该文件"的提交（D3 #3 已写"改名+SPDX+长行+消息清理"），即：

1. 所有 base-files 脚本首次出现时即带 SPDX 第 2 行、无 trailing whitespace、
   无 BLOCK_COMMENT_STYLE/UNSPECIFIED_INT（最终内容已满足，直接取最终版）；
2. fwslot.c 首次出现即用最终"单行用户串"版本（E3 豁免其行长；若回放成旧
   SPLIT_STRING 版本，E3 也覆盖 SPLIT_STRING，但没必要）；
3. platform.sh 首次出现即用最终版（历史 16 条 145 列长行不再出现）；
4. 消息换行 + SOB 按 §3.4。
   满足后，各提交 checkpatch 结果 = §3.3 的类目分布（执行位/行长/拼写），全部豁免即绿。

## 4. 豁免表草案（建议替换树 docs/checkpatch-exemptions.md 的新版内容）

格式建议：\`path glob\` × \`checkpatch type\`，按路径+类型匹配，不做全局
\`--ignore\`（全局忽略会漏掉非豁免位置的同类型问题）。

| ID | 路径模式 | 类型 | 新版实测数量 | 依据（为什么有据） | 状态 |
|---|---|---|---|---|---|
| E1 | \`target/linux/*/base-files/**\`（mode 100755 的脚本）+ \`package/*/root/usr/libexec/rpcd/*\`（100755） | EXECUTE_PERMISSIONS | 28（26+2） | OpenWrt 运行时脚本的执行位是功能的一部分，安装时按 mode 进镜像：实测 RUN3 根文件系统（mtd7 dump，mtd7-rootfs.bin）与 git 100755 集合**逐一吻合**（/etc/init.d/e2631-*、/sbin/e2631-*、rc.button/lights_toggle、rc.wps/00-h3600-ledblink、usr/libexec/rpcd/e2631*）；上游同款先例 75 个 100755（a4ba8240 target/linux/*/base-files，如 ipq40xx/base-files/etc/init.d/bootcount）。这是内核源码规则，不适用于 OpenWrt base-files | 豁免（旧文档 §1 已写，需要把"按标签列文件"改成路径+mode 规则） |
| E2 | 补丁文件：\`**/patches/**\`、\`*.patch\`（含 target patches-6.18、fstools 203/204、mt76 001/002、firewall4 001） | 全部类型（当前实测只有 TRAILING_WHITESPACE） | 26（21+4+1） | diff 上下文空行是 \`+ \`（加号+空格），删空格会破坏 git apply/patch；且 target/package 补丁字节是 provenance/sha256 锚点。D3/D7 明文：target 补丁不跑 checkpatch | 豁免（旧文档 §2 已写；建议扩成"补丁文件整类排除"） |
| E3 | \`package/e2631/e2631-fwslot/src/e2631-fwslot.c\` | LONG_LINE、LONG_LINE_STRING、SPLIT_STRING | 14（6+8；SPLIT_STRING 0） | 这些行是**用户可见的提示/错误消息**，cd14ffa 已决定"每条消息一行"（可 grep）；checkpatch 的 SPLIT_STRING 规则本身就说"跨行会破坏 grep"（scripts/checkpatch.pl:5488-5496）。折行会回到 SPLIT_STRING 报错，两条规则互斥，只能豁免其一。实测最长 174 列 | 豁免（需 Lead 拍板：见 §6-D2） |
| E4 | \`package/e2631/luci-app-e2631/htdocs/.../system/e2631flash.js\` | TYPO_SPELLING | 8 | 误报：\`callE2631Check\`/\`callE2631Run\`/\`callE2631Slots\`/\`callE2631Switch\` 是 RPC 包装函数名，被当成 "called" 拼错 | 豁免（旧文档 §3 已写） |
| — | （不存在） | COMMIT_LOG_LONG_LINE、BAD_SIGN_OFF、NO_AUTHOR_SIGN_OFF、SPDX_LICENSE_TAG、TRAILING_WHITESPACE（非补丁文件）等 | 0（最终内容） | 消息/内容由 S2 构造即干净（§3.4/§3.5），不豁免 | 不豁免 |

旧文档 docs/checkpatch-exemptions.md 的 §3 已过期：它写"SPLIT_STRING 17 处保留 +
LONG_LINE_STRING 2 处"，而 cd14ffa 合并用户串后最终内容变成 LONG_LINE 6 +
LONG_LINE_STRING 8（SPLIT_STRING 0）。新版按 E3 重写。

## 5. D7 门禁实现草案（供 task-36）

### 5.1 位置与分支

树 fork \`.github/workflows/check.yml\` 新 job（与现有 static job 并列）；
触发条件不变（push/PR e2631 + workflow_dispatch）；\`actions/checkout@v5\` +
\`fetch-depth: 0\`（需要历史与上游基底）。

### 5.2 基线提交范围

- 新系列基于 a4ba8240 重建，故 CI 里用**钉死的基底 SHA**（\`E2631_IW_SHA\` 更新为
  新基底）做范围：\`git rev-list --no-merges "$E2631_IW_SHA"..HEAD\`。
- 先断言基底是祖先（照抄现有 check.yml:42-48 的 \`merge-base --is-ancestor\`），
  否则范围为空会假绿。
- 不用 \`git remote add upstream\` + fetch master：不可复现、且 S4 重钉后要改两处；
  钉 SHA 与 kit pins.env 的哲学一致（§6-D3）。

### 5.3 检查算法（每 commit）

\`\`\`
for sha in $(git rev-list --no-merges "$E2631_IW_SHA"..HEAD); do
    perl scripts/checkpatch.pl --no-tree --show-types -g "$sha" > /tmp/cp.txt 2>&1 || true
    # 解析：ERROR/WARNING 行 + 其后的 "#N: FILE: <path>[:line]:" 上下文行
    #       （无 FILE 的报告 = 提交消息级，记为 <commit-message>）
    # 1) 先应用豁免表（路径 glob × 类型）
    # 2) 剩下的按门禁范围过滤：
    #    ^target/linux/zx279128/(image|base-files|generic|dts)/ 或 ^package/e2631/
    #    （§6-D1 若同意扩到整个 target/linux/zx279128/ 则去掉子目录限制）
    # 3) 输出 ::error file=...,line=...::<type>: <msg> 并以非零退出
done
\`\`\`

- 解析必须用默认输出（\`#N: FILE:\` 行），\`--terse\` 无路径不可用；用
  \`--show-types\` 便于精确豁免。
- 豁免表解析：把 §4 表写成脚本内数组或（更好）仓库内
  \`docs/checkpatch-exemptions.md\` 的机器可读小节，job 用 awk/grep 读同一份文件，
  保证"文档 = 实际豁免"一份真相；kit 侧 tools/check-workflows.mjs 增加断言（该文件
  存在、含 E1-E4 标记、job 引用它）。
- 输出失败摘要：commit subject + 行/类型，附"检查范围/豁免依据"链接，方便评审者。

### 5.4 与 kit 的联动（D7 后半句）

kit \`tools/check-workflows.mjs\` 现有对树 CI 的两条检查（fork 有 check.yml、引用
两个钉点）在 S2 改名后会过期，S3 一起改：新断言 = 树 CI 有 checkpatch job、job 用
\`-g\`、引用豁免文档路径、引用新基底 SHA；kit check.yml 里的树 fork raw 路径同步改名。
（具体改法属 task-36，本文件只给契约。）

## 6. 待决策项（Lead）

- **D1 门禁范围**：D7 枚举 \`{image,base-files,generic,dts}\`，未含 \`target/linux/zx279128/{Makefile,config-6.18,files/}\`。
  实测这三处最终内容 0E/0W（7094 行含全部 C 驱动），纳入不增加当前成本、能防未来
  回归（驱动/配置改动也会被门禁）。**建议：扩到整个 \`target/linux/zx279128/\`
  （补丁除外）+ \`package/e2631/\`。**
- **D2 fwslot.c 行长**：选项 a) 豁免 E3（推荐：内容零改动，D4 最省事）；b) 折行
  源文件（回到 SPLIT_STRING 报错，需再豁免 SPLIT_STRING，且 cd14ffa 的"每条消息
  一行"决定被推翻）；c) 门禁 \`--max-line-length=180\`（放松全局，不推荐）。
- **D3 门禁基线**：钉 SHA（推荐）vs fetch upstream master。
- **D4 门禁强制范围**：整个 commit 0E/0W + 豁免表（推荐，消息/署名也管）vs 只按
  D7 路径过滤内容（消息级只靠 review）。推荐前者：新系列消息本来就是重写的，成本 0。

## 7. 复现命令

\`\`\`sh
# A 口径（逐提交）
cd /home/qc233/zte/iwrt-tree
for s in 6cf5f6d7 35270f0c a6c47309 67101828 f2d03c4a 8a253ea8 e96aed31 \
         8a06f47 3dbeadce f3776b32 76dcaee7 72eff3b7 6b609d7e b2e15d46 \
         83df1a90 4b610dc5 235fe125 cd14ffa 5202d4ca; do
  echo "### $s"; perl scripts/checkpatch.pl --no-tree --show-types -g $s 2>&1 | tail -1
done

# B 口径（最终内容分组，示例：板级组）
git diff a4ba8240 5202d4ca -- target/linux/sanechips/base-files \
    target/linux/sanechips/dts target/linux/sanechips/image \
  | perl scripts/checkpatch.pl --no-tree --show-types - | tail -1

# 执行位豁免证据：git mode vs 运行镜像 mode
git ls-tree -r 5202d4ca target/linux/sanechips/base-files | awk '{print $1, $4}'
unsquashfs -ll /home/qc233/zte/e2631-flash-dump-20261115/mtd7-rootfs.bin \
  | grep -E "e2631|lights_toggle|00-h3600|mt76-caldata|fix-wifi"
\`\`\`

## 8. 证据索引

- 设计输入：kit iwrt-adaptation \`ec37b96\` docs/mainline-alignment-design.md（D1-D7）
- 树 fork：QC3284/immortalwrt \`e2631\` = \`5202d4ca\`；基底 a4ba8240（iw master 2026-11-14）
- 先例：target/linux/ipq40xx/{Makefile,base-files,dts,image/Makefile,generic/target.mk,config-6.18}；
  target/linux/ixp4xx/image/Makefile；package/emortal/；scripts/target-metadata.pl:316；
  include/image.mk:571；include/target.mk:76
- 旧豁免文档：树 fork docs/checkpatch-exemptions.md（§1/§2 仍有效，§3 过期）
- 运行镜像执行位证据：/home/qc233/zte/e2631-flash-dump-20261115/mtd7-rootfs.bin（RUN3，cd14ffa）
- checkpatch 版本：0.32-openwrt（树内 scripts/checkpatch.pl）
- 原始输出：/tmp/cp/{提交}.txt、/tmp/cp/group-*.txt（本机会话临时目录，未入库）
