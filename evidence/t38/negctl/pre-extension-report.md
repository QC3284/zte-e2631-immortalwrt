# E2631 tree-fork parity report

- reference: RUN5-44766496013  /home/qc233/zte/e2631-t5-artifacts/parity-44766496013/e2631-build-44766496013/release/e2631-immortalwrt-experimental.bin
  - size 22020628 B, sha256 3a5914edac7dd973c4a86c2c97de5854ed348466701204d5d0903b1972439050
  - uImage time 1795188482, squashfs mkfs time 1795188482, revision r0-5202d4c
- candidate: 44815428424  /home/qc233/zte/e2631-t5-artifacts/parity-44815428424/e2631-build-44815428424/release/e2631-immortalwrt-experimental.bin
  - size 22020628 B, sha256 6aa2c3b56b455fa80e08f597ec0536be41b0502606a52f81bc0f662714cccafb
  - uImage time 1795207582, squashfs mkfs time 1795207582, revision r0-86cddb7

## Verdict

**FAIL**

- factory image byte-identical: no
- kernel payload identical (uImage data + slot marker): no
- rootfs content identical apart from revision/date stamps (path/mode/uid/gid/content): no
- rootfs stamp-only file differences: 3, mtime-only entries: 1741
- expected differences: 22, accepted by review policy: 9, unexpected differences: 5

### Unexplained differences

- rootfs content changed: lib/apk/db/installed
- rootfs content changed: lib/apk/db/scripts.tar.gz
- rootfs content changed: usr/lib/libcrypto.so.3
- etc/os-release: content differs beyond stamps
- SOURCE-INFO Port provenance: undefined != https://github.com/Zlion-Y/openwrt-sanechips-mirror pr-zte-zxhn-h3600 @ db8b8d4130457dbe46558a7cea872dd2dae539e6

### Explained differences (expected by design)

- uImage time: 1795188482 -> 1795207582 (build stamp)
- squashfs mkfs time: 1795188482 -> 1795207582 (build stamp)
- rootfs file differs only in revision/date stamps: etc/apk/world
- rootfs file differs only in revision/date stamps: etc/banner
- rootfs file differs only in revision/date stamps: etc/openwrt_version
- 1741 rootfs entries differ only in mtime (epoch 1795188482 -> 1795207582)
- revision string: r0-5202d4c -> r0-86cddb7
- etc/apk/world: differs only in revision/date stamps
- etc/openwrt_version: differs only in revision/date stamps
- apk version base-files: 1~5202d4c -> 1~86cddb7 (revision suffix)
- SOURCE-INFO ImmortalWrt base: https://github.com/immortalwrt/immortalwrt master @ 4765b657625ec5bbda74b44400465fe043802b30 -> https://github.com/immortalwrt/immortalwrt master @ a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5
- SOURCE-INFO ImmortalWrt tree (pristine): 340ae5426d1c8dfa071e97f08993393b87a47671 -> b905483c80a3a705825ff7aa9c77d1f3db4a01c3
- SOURCE-INFO Kit commit: fd80c1a2b5d58f191096142cb8e1816bb9131d46 -> 38fce86caf9010006898320fd840aa1dbb208f00
- SOURCE-INFO Merged ImmortalWrt master: @ a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5 (2026-11-14) -> undefined
- SOURCE-INFO Port base tree (4 commits applied): undefined -> 6136bd92d5259dbaf22f6bca02c675f05abdf86b
- SOURCE-INFO Port base tree (4 patches applied): 4f89aa7ad0a5132dc047a27a9073b43916f0f957 -> undefined
- SOURCE-INFO Port patch 0001 sha256: 669f41e436c258d2982dc5998efe82ae54230fbfaa0c1cd60fd148d067c07ffc -> undefined
- SOURCE-INFO Port patch 0002 sha256: a512521bd8ae6dba12b44e989e1a6554e0ed0dd21e769dd453a6fafb5a472dcf -> undefined
- SOURCE-INFO Port patch 0003 sha256: 67280d1b531b0a9734f1083b527f933a47c68711b5d0d9820bc38c2bba2dc4d7 -> undefined
- SOURCE-INFO Port patch 0004 sha256: 8f4b2eee62d23f7be0923d742b7eb32fcb207ee936fcac20296020f769490035 -> undefined
- SOURCE-INFO Run: https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44766496013 -> https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44815428424
- SOURCE-INFO Tree fork: https://github.com/QC3284/immortalwrt e2631 @ 5202d4cadca831c5394b4ceca32df22c123d46a7 -> https://github.com/QC3284/immortalwrt e2631 @ 86cddb79802bb2223db21f7364613505174968d8

### Accepted differences (review policy: T-38 RUN5-44766496013 vs Plan C RUN6 v3 (tree fork rebuilt on immortalwrt a4ba8240, target renamed sanechips -> zx279128, tree tip 86cddb79 after the check-size escaping fix))

- uImage payload size: 3491546 -> 3491050 [allowed: Plan C leaves every kernel input unchanged: the kernel config hash 6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1 is asserted unchanged, target/linux/generic/config-6.18 and the zx279128 patches are byte-identical to RUN5 (the target directory was renamed, not edited), and the seed CONFIG_KERNEL_* lines are unchanged. The compressed uImage payload is therefore re-rolled by the build timestamp; kernel-deep-compare must report STAMP-ONLY.]
- kernel payload sha256: "d96e0638ed4fc555a538e4b722de1a11edb60f16e4473fe6682417b06d82d284" -> "4b698fec0e8c4dacb234f6ce0a5c2e8c50391b1c15165e8055639fc643f5fed0" [allowed: Plan C leaves every kernel input unchanged: the kernel config hash 6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1 is asserted unchanged, target/linux/generic/config-6.18 and the zx279128 patches are byte-identical to RUN5 (the target directory was renamed, not edited), and the seed CONFIG_KERNEL_* lines are unchanged. The compressed uImage payload is therefore re-rolled by the build timestamp; kernel-deep-compare must report STAMP-ONLY.]
- kernel payload bytes differ [allowed: Plan C leaves every kernel input unchanged: the kernel config hash 6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1 is asserted unchanged, target/linux/generic/config-6.18 and the zx279128 patches are byte-identical to RUN5 (the target directory was renamed, not edited), and the seed CONFIG_KERNEL_* lines are unchanged. The compressed uImage payload is therefore re-rolled by the build timestamp; kernel-deep-compare must report STAMP-ONLY.]
- rootfs content changed: etc/apk/repositories.d/distfeeds.list [allowed: Plan C target rename: the snapshot feed URL path targets/sanechips/generic -> targets/zx279128/generic (feed pins unchanged: packages decf9463, luci ad75cde8).]
- rootfs content changed: etc/board.d/01_leds [allowed: Plan C checkpatch class: target/linux/zx279128/base-files/etc/board.d/01_leds gains only the SPDX license identifier comment (evidence/c-plan-tree-rebuild-audit-20261121.md section 3.2 class II); the shell logic is byte-identical, so the only rootfs effect is the added comment line.]
- rootfs content changed: etc/openwrt_release [allowed: Plan C target rename: DISTRIB_TARGET sanechips/generic -> zx279128/generic. The DISTRIB_REVISION r0-5202d4c -> r0-f85cbea line is normalised by the comparator as a stamp.]
- rootfs content changed: usr/lib/os-release [allowed: Plan C target rename: OPENWRT_BOARD sanechips/generic -> zx279128/generic. Revision/build strings are stamp-normalised.]
- etc/openwrt_release: content differs beyond stamps [allowed: Plan C target rename: DISTRIB_TARGET sanechips/generic -> zx279128/generic. The DISTRIB_REVISION r0-5202d4c -> r0-f85cbea line is normalised by the comparator as a stamp.]
- usr/lib/os-release: content differs beyond stamps [allowed: Plan C target rename: OPENWRT_BOARD sanechips/generic -> zx279128/generic. Revision/build strings are stamp-normalised.]

### Notes

- kernel CRC differs: 3136383969 -> 4087510629 (derived from the payload)
- rootfs CRC differs: 1189507840 -> 2360549458 (derived from the payload)
- kernel region sha256 differs: "193233e24eabc7f2ff0138c7dd95051014230672ed7bbb26958186f1d485e4fc" -> "d1bdb33304314bfc338cc5a48a627459677f104d886dbc0023bceb0bd0c4cb7d" (derived from the payload)
- uImage header CRC (stored) differs: 1274137271 -> 4148508354 (derived from the payload)
- uImage data CRC differs: 4179420469 -> 1655293686 (derived from the payload)
- rootfs extent sha256 differs: "a6a247c1e4cbd22cad1b6df16e9732c94581518e131a6c5685e8b0dcb3995f60" -> "46818a9b77659bb1cc981679675458cfd4004b0438f7cfd799632804ee34ca58" (derived from the payload)
- squashfs bytes used differs: 12878059 -> 12878547 (derived from the payload)
- apk key: embedded public key matches /home/qc233/zte/e2631-apk-public-key.pem (DER sha256 b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d)

## Factory header

| field | RUN5-44766496013 | 44815428424 | status |
|---|---|---|---|
| outer magic | ����DDDDUUUU���� | ����DDDDUUUU���� | same |
| header offset field | 0 | 0 | same |
| inner magic | 3333ffff�������� | 3333ffff�������� | same |
| version field | "ImmortalWrt v1.10.0" | "ImmortalWrt v1.10.0" | same |
| product field | "ZXHN E2631 V1.0.0" | "ZXHN E2631 V1.0.0" | same |
| hw field | "V1.1.1" | "V1.1.1" | same |
| build field | "20261120" | "20261120" | same |
| key1 | 4945 | 4945 | same |
| key2 | 21009 | 21009 | same |
| body size | 22020096 | 22020096 | same |
| kernel size (declared) | 4194272 | 4194272 | same |
| kernel file offset | 564 | 564 | same |
| kernel CRC | 3136383969 | 4087510629 | DIFF |
| rootfs size (declared) | 12976128 | 12976128 | same |
| rootfs file offset | 4194836 | 4194836 | same |
| rootfs CRC | 1189507840 | 2360549458 | DIFF |
| slotA base/span | "7340032/29360128" | "7340032/29360128" | same |
| slotB base/span | "36700160/29360128" | "36700160/29360128" | same |
| slot table | "7340032,36700160,36700160,66060288" | "7340032,36700160,36700160,66060288" | same |
| slotStart | 0 | 0 | same |
| bootIncl | 0 | 0 | same |
| uboot CRC | 0 | 0 | same |
| integrity | 0 | 0 | same |
| serial | 1 | 1 | same |
| isNew | 0 | 0 | same |

## Kernel

| field | RUN5-44766496013 | 44815428424 | status |
|---|---|---|---|
| kernel region sha256 | "193233e24eabc7f2ff0138c7dd95051014230672ed7bbb26958186f1d485e4fc" | "d1bdb33304314bfc338cc5a48a627459677f104d886dbc0023bceb0bd0c4cb7d" | DIFF |
| slot marker | 3333���̈����������������������� | 3333���̈����������������������� | same |
| uImage magic | 654645590 | 654645590 | same |
| uImage header CRC (stored) | 1274137271 | 4148508354 | DIFF |
| uImage time | 1795188482 | 1795207582 | stamp-diff |
| uImage payload size | 3491546 | 3491050 | DIFF |
| uImage load/entry | "1073774592/1073774592" | "1073774592/1073774592" | same |
| uImage data CRC | 4179420469 | 1655293686 | DIFF |
| uImage os/arch/type/comp | "5/2/2/0" | "5/2/2/0" | same |
| uImage name | "ARM ImmortalWrt Linux-6.18.60" | "ARM ImmortalWrt Linux-6.18.60" | same |
| kernel payload sha256 | "d96e0638ed4fc555a538e4b722de1a11edb60f16e4473fe6682417b06d82d284" | "4b698fec0e8c4dacb234f6ce0a5c2e8c50391b1c15165e8055639fc643f5fed0" | DIFF |

## Rootfs image

| field | RUN5-44766496013 | 44815428424 | status |
|---|---|---|---|
| rootfs extent sha256 | "a6a247c1e4cbd22cad1b6df16e9732c94581518e131a6c5685e8b0dcb3995f60" | "46818a9b77659bb1cc981679675458cfd4004b0438f7cfd799632804ee34ca58" | DIFF |
| squashfs magic | "hsqs" | "hsqs" | same |
| squashfs mkfs time | 1795188482 | 1795207582 | stamp-diff |
| squashfs block size | 262144 | 262144 | same |
| squashfs compression | 4 | 4 | same |
| squashfs bytes used | 12878059 | 12878547 | DIFF |
| squashfs inode count | 1753 | 1753 | same |
| squashfs fragment count | 60 | 60 | same |
| squashfs version | "4.0" | "4.0" | same |

## Version and package database

| field | RUN5-44766496013 | 44815428424 | status |
|---|---|---|---|
| DISTRIB_REVISION | r0-5202d4c | r0-86cddb7 | stamp-diff |
| etc/openwrt_release | 224 B | 223 B | DIFF |
| etc/os-release | 704 B | 703 B | DIFF |
| usr/lib/os-release | 704 B | 703 B | DIFF |
| etc/e2631-version | 20 B | 20 B | same |
| etc/apk/world | 2971 B | 2971 B | DIFF |
| etc/openwrt_version | 11 B | 11 B | DIFF |
| apk installed db | {"sameVersions":211,"stampDiffs":1,"badDiffs":0,"sampleStamp":[{"name":"base-files","ref":"1~5202d4c","cand":"1~86cddb7","kind":"stamp"}],"sampleBad":[]} |  | same |

## SOURCE-INFO

| field | RUN5-44766496013 | 44815428424 | status |
|---|---|---|---|
| APK signing key | pinned input, public key sha256 9edb11a9d0879b6626e6980f7d182c7b20541adccae59a14acade68b9a62c1f8 | pinned input, public key sha256 9edb11a9d0879b6626e6980f7d182c7b20541adccae59a14acade68b9a62c1f8 | same |
| Hardware tested | NO | NO | same |
| ImmortalWrt base | https://github.com/immortalwrt/immortalwrt master @ 4765b657625ec5bbda74b44400465fe043802b30 | https://github.com/immortalwrt/immortalwrt master @ a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5 | stamp-diff |
| ImmortalWrt tree (pristine) | 340ae5426d1c8dfa071e97f08993393b87a47671 | b905483c80a3a705825ff7aa9c77d1f3db4a01c3 | stamp-diff |
| Kernel | 6.18.60 | 6.18.60 | same |
| Kernel build id | e2631-build@immortalwrt-e2631 (P5, from the seed) | e2631-build@immortalwrt-e2631 (P5, from the seed) | same |
| Kit commit | fd80c1a2b5d58f191096142cb8e1816bb9131d46 | 38fce86caf9010006898320fd840aa1dbb208f00 | stamp-diff |
| LuCI commit | ad75cde88e694b511100576bfbe0a280e5efe6ef | ad75cde88e694b511100576bfbe0a280e5efe6ef | same |
| LuCI feed | https://github.com/immortalwrt/luci.git | https://github.com/immortalwrt/luci.git | same |
| Merged ImmortalWrt master | @ a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5 (2026-11-14) | <missing> | stamp-diff |
| Packages commit | decf94639ffd6ddd26591c190b547c6b7eea150b | decf94639ffd6ddd26591c190b547c6b7eea150b | same |
| Packages feed | https://github.com/immortalwrt/packages.git | https://github.com/immortalwrt/packages.git | same |
| Parity reproduction | false (build stamp date-of-run) | false (build stamp date-of-run) | same |
| Port base tree (4 commits applied) | <missing> | 6136bd92d5259dbaf22f6bca02c675f05abdf86b | stamp-diff |
| Port base tree (4 patches applied) | 4f89aa7ad0a5132dc047a27a9073b43916f0f957 | <missing> | stamp-diff |
| Port patch 0001 sha256 | 669f41e436c258d2982dc5998efe82ae54230fbfaa0c1cd60fd148d067c07ffc | <missing> | stamp-diff |
| Port patch 0002 sha256 | a512521bd8ae6dba12b44e989e1a6554e0ed0dd21e769dd453a6fafb5a472dcf | <missing> | stamp-diff |
| Port patch 0003 sha256 | 67280d1b531b0a9734f1083b527f933a47c68711b5d0d9820bc38c2bba2dc4d7 | <missing> | stamp-diff |
| Port patch 0004 sha256 | 8f4b2eee62d23f7be0923d742b7eb32fcb207ee936fcac20296020f769490035 | <missing> | stamp-diff |
| Port provenance | <missing> | https://github.com/Zlion-Y/openwrt-sanechips-mirror pr-zte-zxhn-h3600 @ db8b8d4130457dbe46558a7cea872dd2dae539e6 | DIFF |
| Run | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44766496013 | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44815428424 | stamp-diff |
| Tree fork | https://github.com/QC3284/immortalwrt e2631 @ 5202d4cadca831c5394b4ceca32df22c123d46a7 | https://github.com/QC3284/immortalwrt e2631 @ 86cddb79802bb2223db21f7364613505174968d8 | stamp-diff |

## APK signing key

| side | file | bytes | DER sha256 |
|---|---|---|---|
| ref | etc/apk/keys/public-key.pem | 178 | b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d |
| cand | etc/apk/keys/public-key.pem | 178 | b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d |
| local reference | /home/qc233/zte/e2631-apk-public-key.pem | - | b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d |

- private key material inside either rootfs: none

## Rootfs content

- entries: 1752 -> 1752
- unexplained content differences: 3
- stamp-only file differences (revision/date text): 3
- mtime-only differences: 1741

| path | kind | ref | candidate |
|---|---|---|---|
| lib/apk/db/installed | changed | f\|420\|1000\|1000\|38edea1c8350e398b179a364995260e5d469664d1c17a8f105491219ff09d1e6 | f\|420\|1000\|1000\|a91b09775097554b3274f71c159f9c289fe472b78303458ede6978801742cc5c |
| lib/apk/db/scripts.tar.gz | changed | f\|420\|1000\|1000\|cd1ffb74813805f3dcf69607d44fa856db46f6c59ce952118c8f632133e20a41 | f\|420\|1000\|1000\|ccdccf57628f11ee8e405d430ade9b3ed3e4b04b7092628801ec58215b95b593 |
| usr/lib/libcrypto.so.3 | changed | f\|420\|1000\|1000\|f9950dbe330e4ec393906d2f111bc99bb00bbefc83641cd75d3556600779f063 | f\|420\|1000\|1000\|6a9207b9a05ec713d29e827be132056a9f0cf371d857c600ea5a8d0f8bbe023d |

| path | kind | explanation |
|---|---|---|
| etc/apk/world | stamp | revision/date text only |
| etc/banner | stamp | revision/date text only |
| etc/openwrt_version | stamp | revision/date text only |

### Text-file differences

- etc/openwrt_release
  - line 3: ref="DISTRIB_REVISION='r0-5202d4c'" cand="DISTRIB_REVISION='r0-86cddb7'"
  - line 4: ref="DISTRIB_TARGET='sanechips/generic'" cand="DISTRIB_TARGET='zx279128/generic'"
  - line 6: ref="DISTRIB_DESCRIPTION='ImmortalWrt SNAPSHOT r0-5202d4c'" cand="DISTRIB_DESCRIPTION='ImmortalWrt SNAPSHOT r0-86cddb7'"
- etc/os-release
  - line 11: ref="BUILD_ID=\"r0-5202d4c\"" cand="BUILD_ID=\"r0-86cddb7\""
  - line 12: ref="OPENWRT_BOARD=\"sanechips/generic\"" cand="OPENWRT_BOARD=\"zx279128/generic\""
  - line 19: ref="OPENWRT_RELEASE=\"ImmortalWrt SNAPSHOT r0-5202d4c\"" cand="OPENWRT_RELEASE=\"ImmortalWrt SNAPSHOT r0-86cddb7\""
  - line 20: ref="OPENWRT_BUILD_DATE=\"1795188482\"" cand="OPENWRT_BUILD_DATE=\"1795207582\""
- usr/lib/os-release
  - line 11: ref="BUILD_ID=\"r0-5202d4c\"" cand="BUILD_ID=\"r0-86cddb7\""
  - line 12: ref="OPENWRT_BOARD=\"sanechips/generic\"" cand="OPENWRT_BOARD=\"zx279128/generic\""
  - line 19: ref="OPENWRT_RELEASE=\"ImmortalWrt SNAPSHOT r0-5202d4c\"" cand="OPENWRT_RELEASE=\"ImmortalWrt SNAPSHOT r0-86cddb7\""
  - line 20: ref="OPENWRT_BUILD_DATE=\"1795188482\"" cand="OPENWRT_BUILD_DATE=\"1795207582\""

