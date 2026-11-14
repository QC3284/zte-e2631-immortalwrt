# T-20 独立验证：树 fork 重钉重建对（RUN1 / RUN2）

日期：2026-11-14（夜间续跑至 11-15 凌晨）　负责人：verify-docs（独立验证方）

状态：RUN1 全绿；RUN2 全绿；A==B 逐字节一致已达成（第 6 节）。

## 1. 目的与范围

- T-20 的验收是自洽可复现：kit 在 c6885dd（seed 单一来源修复）上、对树 fork
  83df1a9 连续两次 dispatch firmware.yml（publish=false、use_pinned_apk_key=true、
  reproduce_v1100 不设），两次产物必须逐字节一致；与基线 run 43572710065（kit
  535c0fe、树 e96aed31）的差异必须都能归因到 83df1a9 的修复系列、P5-P8 与时间戳。
- 本文件是 verify-docs 的独立验证记录：产物重新下载、哈希、打包/启动两层门禁复跑、
  APK 公钥钉值核对、与基线的逐项差异复核。pkg-release 的构建事实见
  evidence/t20-repin-parity-20261114.md（第 5 节由其补齐）；本文不重复其 CI 观察。
- 约束：未发布 Release、未推 main、未碰真机 192.168.1.1；私钥不进日志/产物。

## 2. 输入与工件

| 项 | 值 |
| --- | --- |
| RUN1 | run 43603782716，head c6885dd，dispatch 2026-11-14T14:13:58Z，conclusion success（约 1h24m） |
| RUN2 | run 43611384642，head c6885dd，dispatch 2026-11-14T15:39:55Z，conclusion success（15:39:55Z→17:01:42Z，约 1h21m47s） |
| 基线 | run 43572710065，kit 535c0fe，树 e96aed31 |
| 树 fork | https://github.com/QC3284/immortalwrt e2631 @ 83df1a90a71863c2f54d6e399e8b0ee86405083a |
| ImmortalWrt 基底 | immortalwrt/immortalwrt master @ 4765b657625ec5bbda74b44400465fe043802b30（kernel 6.18.60） |
| RUN1 bin | 22,020,628 B sha256 b9844c3a814e4a085a6e41b6e502e18a74906acf1a104f0ba0ba8b3a7f15b959 |
| RUN1 下载包 | artifact zip 18,766,177 B（大小与 API 声明一致） |
| RUN1 落盘 | /home/qc233/zte/e2631-t5-artifacts/parity-43603782716/extracted/release/ |

SHA256SUMS 校验：bin 与 SOURCE-INFO.txt 均成功（sha256sum -c 返回 0）。

## 3. RUN1 独立验证

### 3.1 运行事实

- 结论 success；14:13:58Z 开始、15:38:23Z 更新，约 1h24m25s。
- step「Publish only after all build and artifact gates pass」为 skipped；
  仓库 Release 列表未变化（仍只有 v1.10.0 prerelease，资产创建时间 04:08-04:10Z），
  即本次没有创建新 Release/tag。
- DEVMEM 构建后断言、P6 miniupnpd 断言均为 success。

### 3.2 打包层（host/verify_pkg.mjs）

ALL CHECKS PASSED，33 PASS + 1 个预期 WARN（uImage ih_hcrc 与标准算法不符，
官方镜像同样如此，属 vendor 差异）。关键值：

- body 0x1500000；slot 表 0x700000/0x1c00000 与 0x2300000/0x1c00000；
- kernel 在 slot+0x20、声明 extent 0x3fffe0，uImage ih_size 0x3544da（比基线 +0x1a8=424 B）；
- uImage os/arch/type/comp = 5/2/2/0，load=entry=0x40008000；
- rootfs 在 slot+0x400000、extent 0xc60000，squashfs bytes_used 12,871,615；
- 版本头落在 slot+0x1500000。

### 3.3 启动层（tools/verify_img.mjs）

从 factory 包按头部字段切出 payload/kernel（slot marker + uImage，3,491,130 B，
sha256 3d5915234998672907dfb143751b5b2466fd9d0a84a7f71972a5d3bec4a5ee0d）与
payload/root（squashfs extent，12,976,128 B，sha256
f986b759205133b7eb4a2ed6d28066da617d6a1b5d91d9d31010c18d555d1d71），
运行：node tools/verify_img.mjs <重建目录> --tree /home/qc233/zte/iwrt-tree --target sanechips。

结果 BOOT-READY: no static blocker found（退出 0）。分区表 mtd0..mtd9、rootfs=mtd7、
rootfs_data 由内核从 rootfs 尾部切出、slot1 28 MiB、版本头在只读块、无启用 USB/看门狗、
SMP enable-method 匹配、dtb model/compatible/memory 正确。与 T5 相同的两条 NOTE：
下载 artifact 不含独立 e2631.dtb 与 build_dir 的 kernel .config，故 dtb 用镜像内追加的
dtb 校验、config 侧检查跳过（不冒充通过）；无 .manifest，包清单检查跳过。

### 3.4 APK 签名 key（P8）

- 镜像内 /etc/apk/keys/public-key.pem 文件 sha256 =
  9edb11a9d0879b6626e6980f7d182c7b20541adccae59a14acade68b9a62c1f8，
  与 SOURCE-INFO 的「APK signing key」字段、本地参考
  /home/qc233/zte/e2631-apk-public-key.pem 的文件 sha256 逐字节一致。
- DER 归一化后为 b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d。
- 私钥材料扫描：两个镜像 rootfs 中均未发现私钥。

### 3.5 SOURCE-INFO

Kit commit c6885dd；树 fork e2631 @ 83df1a9；基底 4765b657；pristine tree 340ae542；
port base tree 4f89aa7a；四个补丁 sha256 与钉值一致（0001 669f41e4、0002 a512521b、
0003 67280d1b、0004 8f4b2eee）；feeds packages decf9463、luci ad75cde8；Kernel 6.18.60；
Hardware tested NO；Run 指向 43603782716。

## 4. RUN1 与基线（43572710065）的差异复核

结论：PASS-REVIEWED-DIFFS，unexpected = 0。
（20 项预期差异 + 49 项经显式复核策略接受的差异；rootfs 1753 项对 1753 项，
0 项无法解释，4 项仅 revision/date 戳差异，1700 项仅 mtime 差异。）

### 4.1 归因分组

| 组 | 内容 | 归因 |
| --- | --- | --- |
| 内核载荷 | uImage 数据 +424 B、sha 改变、kernel 包版本 hash 改变 | 6b609d7 打开 CONFIG_KERNEL_DEVMEM=y（kernel-defaults.mk 末尾追加 CONFIG_KERNEL_*，last-wins） |
| 板级脚本 | sbin/e2631-*、etc/init.d/e2631-*、etc/uci-defaults/*、lib/preinit/79_e2631_userdata、lib/upgrade/platform.sh 等 | f3776b3 extroot 快照门、76dcaee WAN 默认策略、b2e15d4 风格整理 |
| 新增/删除 | 新增 lib/e2631-snapshot.sh；删除 etc/uci-defaults/63_e2631_wan_access | f3776b3 / 76dcaee |
| fstools | lib/libfstools.so；fstools、block-mount 版本 r1->r2 | 72eff3b fstools 204（无 upper 时跳过 jffs2 sync） |
| APK 数据库 | etc/apk/keys/public-key.pem、etc/apk/world、lib/apk/db/*、base-files.* | P8 钉 key；base-files revision 1~83df1a9；包版本集合变化 |
| P6 | usr/sbin/miniupnpd | 基线嵌入 iwrt-adaptation-535c0fef；RUN1 剥掉 GITHUB_REF_NAME/GITHUB_SHA |
| P7 | usr/share/ucode/luci/version.uc | 钉 SHA 取 feed，分支标签由 HEAD detached 变为 LuCI Master |
| 构建戳 | uImage time、squashfs mkfs time、1700 项 mtime、banner/os-release 等 | 树 pin 变导致 SOURCE_DATE_EPOCH 变（见第 5 节） |
| openssl | usr/lib/libcrypto.so.3 | openssl 内嵌 SOURCE_DATE_EPOCH 的 built on 串；基线 parity run 固定 1794624080，RUN1 为 1794656911 |

### 4.2 复核策略的两处扩展

基线是 P8 之前的 parity run，APK key 为每次构建随机生成，因此基线必然与钉值不同；
同时 etc/apk/world 除 revision 行外还含内核版本 hash 行。为让「差异已复核」可机器判定，
compare-parity.mjs 增加两个策略类别（只影响带 --allow 的 reviewed 模式）：

- apkKey：仅当 candidate 的公钥等于本地钉值（DER b0cbe6fb...）时，才允许 reference
  侧不同；candidate 侧不匹配仍为 fatal。RUN1 vs RUN2 必须双方都等于钉值。
- versionFiles：允许显式列出的版本/文本文件（本次 etc/apk/world）的「超戳差异」，
  理由写在策略文件里。

策略文件：/home/qc233/zte/e2631-t5-artifacts/parity-tools/t20-policy.json；
报告：/home/qc233/zte/e2631-t5-artifacts/t20/cmp2/baseline-vs-run1-reviewed.md（+.json）。

## 5. 为什么预期 RUN1 与 RUN2 逐字节一致

- 构建戳不是墙钟：RUN1 的 uImage time / squashfs mkfs / rootfs mtime 均为 1794656911，
  等于树 tip 83df1a9 的 commit 时间（%ct，2026-11-14T11:48:31Z）。
  OpenWrt 的 version.date 取自 checkout 的 git tip，SOURCE_DATE_EPOCH 随之固定；
  两次构建同一树 SHA，戳就相同。（基线 parity run 是显式写死 1794624080 的例外。）
- E2631_BUILD 未设 reproduce_v1100 时取当天日期（两次都在 2026-11-14 打包），一致。
- feeds 钉 SHA、APK 用同一把 pinned key、kit/tree 输入相同；基线与 v1.10.0 的 parity
  已经证明该构建在 P1-P8 就位后除随机 key/戳以外是确定性的。

预期 RUN1 vs RUN2 严格比对为 PASS-BYTE-IDENTICAL（bin sha256 相同），
SOURCE-INFO 仅 Kit commit（相同）、Run URL 等 provenance 字段不同。

## 6. RUN1 vs RUN2 严格比对（A==B 已达成）

- RUN2 完成事实：conclusion success，17:01:42Z 完成（15:39:55Z 开始，1h21m47s）；
  publish 步骤 skipped；Release 列表无新增（仍只有 v1.10.0 prerelease）；artifact zip
  18,769,997 B，SHA256SUMS 校验通过。
- 严格成对比对（verify-task20.sh，不带复核策略）：**PASS-BYTE-IDENTICAL**
  - 两跑 bin 均 22,020,628 B，sha256 一致 =
    b9844c3a814e4a085a6e41b6e502e18a74906acf1a104f0ba0ba8b3a7f15b959
  - byte-identical=true；kernel-payload-identical=true；rootfs-content-identical=true；
    stamp-only-files=0；expected diffs=1（仅 SOURCE-INFO 的 Run URL）；unexpected diffs=0。
  - 报告：/home/qc233/zte/e2631-t5-artifacts/parity-43603782716-vs-43611384642.md(+.json)。
- 可复现性解释：构建时间戳 = 树 tip 83df1a9 的提交时间（%ct 1794656911），feeds 与
  APK 私钥均钉定 ⇒ 同输入两跑逐字节一致。
- 基线复核重跑（baseline 43572710065 vs RUN1）：PASS-REVIEWED-DIFFS，expected diffs=20、
  unexpected diffs=0、stamp-only-files=4；报告
  /home/qc233/zte/e2631-t5-artifacts/baseline-vs-43603782716-reviewed.md。
- verify-task20.sh 由 Lead 以干净 /tmp 完整重跑一遍，[verify-task20] OK（2026-11-15 01:15）。

- [ ] 下载 RUN2 artifact，sha256sum -c SHA256SUMS
- [ ] compare-parity.mjs 严格模式（无 --allow）：预期 PASS-BYTE-IDENTICAL
- [ ] 记录两次 bin sha256 / SOURCE-INFO 差异

## 7. 结论与未证明项

- 已验证：RUN1 通过打包层与启动层全部静态门禁；APK 钉值正确；publish 关闭且无 Release；
  与基线的差异均可归因，无内容漂移。
- RUN1 vs RUN2 逐字节一致：已达成（第 6 节）。
- 未证明（照 T5 口径）：真机构建/刷写/启动、libustream ABI、真实 Release 流程；
  真机仍为 v1.10.0，本 T-20 不触碰设备。

## 附录 A：命令与路径

- 重新下载（gh run download 在本机多次出现 signed URL EOF，改用 API 归档地址 + curl 断点续传）：
  url=$(gh api /repos/QC3284/zte-e2631-immortalwrt/actions/artifacts/<id> --jq .archive_download_url);
  curl -L -H "Authorization: Bearer $(gh auth token)" -C - --retry 7 --retry-all-errors -o artifact.zip "$url"
- 解包：unzip -q artifact.zip -d extracted（release/ 下 bin、SHA256SUMS、SOURCE-INFO.txt，build-logs/world.log）。
- 载荷重建：node /home/qc233/zte/e2631-t5-artifacts/parity-tools/extract-payload.mjs <bin> <outdir>
  （按包头的 kSize/kFileOff/rSize/rFileOff 切出 payload/kernel、payload/root）。
- 启动层：node tools/verify_img.mjs <payload-dir> --tree /home/qc233/zte/iwrt-tree --target sanechips。
- 打包层：node host/verify_pkg.mjs <bin>。
- 对照：node /home/qc233/zte/e2631-t5-artifacts/parity-tools/compare-parity.mjs <ref.bin> <cand.bin>
  --ref-info <ref SOURCE-INFO> --cand-info <cand SOURCE-INFO> --verify-pkg host/verify_pkg.mjs
  --apk-key /home/qc233/zte/e2631-apk-public-key.pem [--allow t20-policy.json] --md ... --json ...
- 一键核对脚本：/home/qc233/zte/e2631-t5-artifacts/parity-tools/verify-task20.sh <run1> [run2] [policy]。
- 根文件系统解包对照：unsquashfs -o 4194836 -d <dir> <bin>（0x400214 为 body+0x400000 的十进制）。
