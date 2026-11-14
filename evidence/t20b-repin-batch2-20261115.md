# T-20 批次 2：树 fork re-pin 到 cd14ffa（2026-11-15）

状态：pin 已更新、本地验证全绿；单次 RUN3 构建由 Lead 触发（结果待补第 5 节）。

## 1. 背景与钉值

- base-builder 三个主线质量修复提交并入树 fork QC3284/immortalwrt 分支 e2631
  （直接叠在 83df1a9 之上，无历史重写）：
  - 4b610dc（tree 8d3caba2…）e2631-userdata: never write or accept an empty snapshot
    marker —— 空/未知 marker 拒绝、写回校验、preinit 拒绝；
  - 235fe12（tree 89d01cac…）e2631: add the missing SPDX tags to the target scripts
    —— 5 处 SPDX；
  - cd14ffa（tree 238d16a1…）e2631-fwslot: put each split user-visible string on one
    line —— QUOTED_STRING_SPLIT/SPLIT_STRING 17 处，纯字符串拼接合并，汇编等价。
- origin/e2631 tip = cd14ffa091f63116859ae8bd6d262f08778629a8；top tree =
  238d16a1abdfd0159100009885da9efe90cef68e（仅展示，不钉）。
- 不变：ImmortalWrt pin 4765b657…（kernel 6.18.60）、pristine tree 340ae542…、
  base-port tree 4f89aa7a（4 个 sanechips 提交未重写）、feed 钉值
  decf9463/ad75cde8、4 个 port patch sha256。
- 深度：base-port 提交 6710182 现在位于 tip 下第 15 层（中间隔 14 个提交），
  静态下限由 12 提到 15；E2631_FORK_DEPTH 仍为 32（富余）。

## 2. 套件改动

- scripts/pins.env：E2631_FORK_SHA 83df1a9… -> cd14ffa…；注释更新（历史链
  e96aed3 -> 83df1a9 -> cd14ffa 均可审计；深度下限 15 的推导写明）。
- scripts/base-pin-check.sh 与 tools/check-workflows.mjs：深度下限 12 -> 15，
  check-workflows 的 fork pin 断言改到 cd14ffa（总检查数 70 项）。
- tests/native/package/e2631/e2631-fwslot/src/e2631-fwslot.c 重新同步：
  sha256 2ab1bf0c… -> 027a44d7…；11 处 hunk 全是字符串拼接合并；用 gcc 分别编译
  新旧两版并 objdump -d 比较，.text 逐行相同（ASM_IDENTICAL）。
  其余三个 native 文件在 cd14ffa 上与套件一致（未变）：
  e2631-upgrade 62bacc5f…、platform.sh 2c353e28…、slotpart-core.c 9371db5a…。
- 文档同步：BUILD.md pin 表、README.en.md、docs/immortalwrt-migration.md 的钉值
  演进说明；T-20 记录加交叉注；说明 8da2f8d 只在 TEAM-NOTES 历史日志中出现，
  套件内无任何活跃引用（8da2f8d 是 b2e15d4 的 top tree）。

## 3. 本地验证（全绿）

- bash -n 全部改动的 shell 脚本；node --check tools/check-workflows.mjs。
- node tools/check-workflows.mjs：OK（70 项 PASS，含 pin 值与深度下限断言）。
- 预 bootstrap make check：全部 PASS 或带原因 SKIP，MAKE_RC=0。
- 真实 GitHub bootstrap 演练（E2631_TREE=/home/qc233/zte/e2631-b2-tree）：
  BOOTSTRAP_RC=0；构建树 depth-1 at cd14ffa（shallow，rev-list 1）；
  从头历史（depth 32）验证：base-port tree 4f89aa7a 在历史中、ImmortalWrt pin
  4765b657 是祖先、port series 恰 4 个提交、kernel 6.18.60；feeds 钉值取回；
  tree seed 生效（记录 CONFIG_KERNEL_DEVMEM=y 与 P5 两行）。
- 演练树上的后置 make check：全部 PASS 或带原因 SKIP，MAKE_RC=0；其中
  host-native copies vs tree fork PASS、base pin PASS、base tree（fork 历史 +
  4 提交）PASS、slot layout constants PASS、board dts PASS、NOTICE PASS。
- node host/sim-upgrade.mjs：OK（30 项）。python3 tests/test_upgrade.py：8 tests OK。
  tests/test_userdata_gate.sh（配合演练树）：verdict ALL-PASS（marker 加固静态 +
  mock 层；真机功能层属设备轨道）。演练目录已删除（约 460 MB）。

## 4. 构建计划与验收口径

- 单次 RUN3（A==B 可复现性已在 83df1a9 由 RUN1/RUN2 证明）：由 Lead 触发
  gh workflow run firmware.yml --ref iwrt-adaptation -f publish=false
    -f use_pinned_apk_key=true
  不设 reproduce_v1100；不发布 Release。
- 验收 = 对基线 43572710065（sha256 4e31df93…）的 PASS-REVIEWED-DIFFS 复核；
  预期差异类别在 P5–P8 基础上新增：树修订串（DISTRIB_REVISION/BUILD_ID/
  base-files revision 由 r0-83df1a9 变为 r0-cd14ffa）、fwslot 二进制中的字符串
  行号/布局变化、e2631-userdata 与 preinit 的 marker 加固内容、目标脚本 SPDX 注释
  带来的字节变化。unexpected diffs 必须为 0。
- RUN3 的 run id、产物 sha256、SOURCE-INFO 与复核结论待补入本节。

## 5. 约束

- 未发布 Release、未推 kit main、未碰真机 192.168.1.1；APK 私钥只存在于 GitHub
  secret 与 runner 临时 0600 文件，仓库与日志不落私钥。
