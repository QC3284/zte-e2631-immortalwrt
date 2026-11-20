# E2631 tree-fork parity report

- reference: run-43623162108  /home/qc233/zte/e2631-t5-artifacts/parity-43623162108/e2631-build-43623162108/release/e2631-immortalwrt-experimental.bin
  - size 22020628 B, sha256 3d7825c9fdb9a15992ab72393014ce6c13211d76757f162bbe8b3b8cf8dbb13d
  - uImage time 1794677928, squashfs mkfs time 1794677928, revision r0-cd14ffa
- candidate: 44766496013  /home/qc233/zte/e2631-t5-artifacts/parity-44766496013/e2631-build-44766496013/release/e2631-immortalwrt-experimental.bin
  - size 22020628 B, sha256 3a5914edac7dd973c4a86c2c97de5854ed348466701204d5d0903b1972439050
  - uImage time 1795188482, squashfs mkfs time 1795188482, revision r0-5202d4c

## Verdict

**PASS-REVIEWED-DIFFS**

- factory image byte-identical: no
- kernel payload identical (uImage data + slot marker): no
- rootfs content identical apart from revision/date stamps (path/mode/uid/gid/content): no
- rootfs stamp-only file differences: 5, mtime-only entries: 1718
- expected differences: 20, accepted by review policy: 48, unexpected differences: 0

### Explained differences (expected by design)

- build field: "20261114" -> "20261120" (build stamp)
- uImage time: 1794677928 -> 1795188482 (build stamp)
- squashfs mkfs time: 1794677928 -> 1795188482 (build stamp)
- rootfs file differs only in revision/date stamps: etc/apk/world
- rootfs file differs only in revision/date stamps: etc/banner
- rootfs file differs only in revision/date stamps: etc/openwrt_release
- rootfs file differs only in revision/date stamps: etc/openwrt_version
- rootfs file differs only in revision/date stamps: usr/lib/os-release
- 1718 rootfs entries differ only in mtime (epoch 1794677928 -> 1795188482)
- revision string: r0-cd14ffa -> r0-5202d4c
- etc/openwrt_release: differs only in revision/date stamps
- etc/os-release: differs only in revision/date stamps
- usr/lib/os-release: differs only in revision/date stamps
- etc/apk/world: differs only in revision/date stamps
- etc/openwrt_version: differs only in revision/date stamps
- apk version base-files: 1~cd14ffa -> 1~5202d4c (revision suffix)
- SOURCE-INFO Kit commit: 8d87bfa5a02d9ff4919a3b0eadc6f4f3429349c0 -> fd80c1a2b5d58f191096142cb8e1816bb9131d46
- SOURCE-INFO Merged ImmortalWrt master: undefined -> @ a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5 (2026-11-14)
- SOURCE-INFO Run: https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43623162108 -> https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44766496013
- SOURCE-INFO Tree fork: https://github.com/QC3284/immortalwrt e2631 @ cd14ffa091f63116859ae8bd6d262f08778629a8 -> https://github.com/QC3284/immortalwrt e2631 @ 5202d4cadca831c5394b4ceca32df22c123d46a7

### Accepted differences (review policy: T-26 RUN3-43623162108 vs merge candidate (upstream master a4ba8240 merge + firewall4 fullcone re-anchor; kernel config unchanged, kernel patch set changed -> merge-class kernel delta, build stamps re-rolled))

- uImage payload size: 3491850 -> 3491546 [allowed: Kernel config hash is unchanged (6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1), target/linux/generic/kernel-6.18 is byte-identical (LINUX_VERSION-6.18 = .60) and the tree seed/config are unchanged, so no kernel CONFIG changed. The upstream merge a4ba8240 did, however, update the reference kernel patch set: 13 files under target/linux/generic/patches-6.18 changed (757 OEM SFP+ONU quirk; 802-01..04 phylib/usb PHY interrupt handling; 904-debloat_dma_buf; 750-753 SFP quirks; 792 wireguard sticky source address; 801-01/896-03 net-phy), so built-in kernel code legitimately recompiles and kernel-deep-compare reports NON-STAMP-DIFF (2,371,928 differing decompressed bytes in 253,931 ranges, decompressed size unchanged at 13,159,680 B). Accepted as merge-class only via verify-task26.sh --kernel-merge-class, which re-derives: kernel config hash unchanged, kernel-6.18 unchanged, seed/config unchanged, every changed kernel-input path confined to target/linux/{generic,sanechips}, include/kernel-{defaults,version}.mk or package/kernel, and at least one target/linux/generic patch changed; the file list is written to kernel-merge-class-<tag>.json. Residual risk: kernel behaviour follows the upstream reference kernel patches; no e2631-specific kernel patch changed.]
- kernel payload sha256: "fa51a7fbe0cf1c6dac1db5103dfb61f71fafcb9b9d59abdd7fe8e561c2ccc608" -> "d96e0638ed4fc555a538e4b722de1a11edb60f16e4473fe6682417b06d82d284" [allowed: Kernel config hash is unchanged (6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1), target/linux/generic/kernel-6.18 is byte-identical (LINUX_VERSION-6.18 = .60) and the tree seed/config are unchanged, so no kernel CONFIG changed. The upstream merge a4ba8240 did, however, update the reference kernel patch set: 13 files under target/linux/generic/patches-6.18 changed (757 OEM SFP+ONU quirk; 802-01..04 phylib/usb PHY interrupt handling; 904-debloat_dma_buf; 750-753 SFP quirks; 792 wireguard sticky source address; 801-01/896-03 net-phy), so built-in kernel code legitimately recompiles and kernel-deep-compare reports NON-STAMP-DIFF (2,371,928 differing decompressed bytes in 253,931 ranges, decompressed size unchanged at 13,159,680 B). Accepted as merge-class only via verify-task26.sh --kernel-merge-class, which re-derives: kernel config hash unchanged, kernel-6.18 unchanged, seed/config unchanged, every changed kernel-input path confined to target/linux/{generic,sanechips}, include/kernel-{defaults,version}.mk or package/kernel, and at least one target/linux/generic patch changed; the file list is written to kernel-merge-class-<tag>.json. Residual risk: kernel behaviour follows the upstream reference kernel patches; no e2631-specific kernel patch changed.]
- kernel payload bytes differ [allowed: Kernel config hash is unchanged (6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1), target/linux/generic/kernel-6.18 is byte-identical (LINUX_VERSION-6.18 = .60) and the tree seed/config are unchanged, so no kernel CONFIG changed. The upstream merge a4ba8240 did, however, update the reference kernel patch set: 13 files under target/linux/generic/patches-6.18 changed (757 OEM SFP+ONU quirk; 802-01..04 phylib/usb PHY interrupt handling; 904-debloat_dma_buf; 750-753 SFP quirks; 792 wireguard sticky source address; 801-01/896-03 net-phy), so built-in kernel code legitimately recompiles and kernel-deep-compare reports NON-STAMP-DIFF (2,371,928 differing decompressed bytes in 253,931 ranges, decompressed size unchanged at 13,159,680 B). Accepted as merge-class only via verify-task26.sh --kernel-merge-class, which re-derives: kernel config hash unchanged, kernel-6.18 unchanged, seed/config unchanged, every changed kernel-input path confined to target/linux/{generic,sanechips}, include/kernel-{defaults,version}.mk or package/kernel, and at least one target/linux/generic patch changed; the file list is written to kernel-merge-class-<tag>.json. Residual risk: kernel behaviour follows the upstream reference kernel patches; no e2631-specific kernel patch changed.]
- rootfs content changed: bin/busybox [allowed: busybox 1.38.0-r5: upstream changes BusyBox default config (edit history 256->2000 unless SMALL_FLASH/LOW_MEMORY_FOOTPRINT; FEATURE_SH_HISTFILESIZE default y), so the binary is rebuilt.]
- rootfs content changed: etc/config/firewall [allowed: firewall4 upstream source e6f600c4->3722eadc (OpenWrt core commit dab12e7663 'firewall4: update to Git HEAD (2026-11-08)'); the firewall4 repo range e6f600c4..3722eadc updates root/etc/config/firewall (notably 'config: add dest addr restrictions for DHCPv6 rules' and 'templates: remove stray file'): the Allow-DHCPv6 rule gains dest_ip fe80::/10 and two stale commented lines drop; our local fullcone/flow_offloading settings are unchanged.]
- rootfs content changed: etc/config/uhttpd [allowed: uhttpd upstream files/uhttpd.config changed in the merge.]
- rootfs content changed: etc/init.d/uhttpd [allowed: uhttpd upstream files/uhttpd.init changed in the merge.]
- rootfs content changed: etc/profile.d/busybox-history-file.sh [allowed: busybox upstream files/busybox-history-file.sh now exports HISTFILESIZE/HISTSIZE=256 alongside HISTFILE.]
- rootfs content changed: lib/apk/db/installed [allowed: derived apk DB: base-files 1~5202d4c plus the firewall4 2026.11.08~3722eadc-r1, ppp/ppp-mod-pppoe 2.5.5-r1 and kmod-nft-fullcone 6.18.60.2023.05.17~07d93b62-r4 records; no unrecorded package selection change.]
- rootfs content changed: lib/apk/db/scripts.tar.gz [allowed: derived apk scripts archive: the firewall4 and ppp package scripts move with their upstream version/content updates.]
- rootfs content changed: lib/apk/packages/firewall4.conffiles_static [allowed: derived: records the sha256 of the refreshed /etc/config/firewall conffile (6dd76112... -> 055145fd...).]
- rootfs content changed: lib/apk/packages/firewall4.list [allowed: firewall4 e6f600c4..3722eadc 'templates: remove stray file' drops /usr/share/firewall4/templates/mangle-rule.uc from the installed file list; the remaining templates stay.]
- rootfs content changed: lib/apk/packages/ppp-mod-pppoe.list [allowed: ppp-mod-pppoe installed file list moves with PKG_VERSION 2.5.4 -> 2.5.5.]
- rootfs content changed: lib/apk/packages/uhttpd.conffiles_static [allowed: records the sha256 of the updated /etc/config/uhttpd conffile.]
- rootfs content changed: lib/functions.sh [allowed: base-files: upstream 4765b657..a4ba8240 adds path_normalize() to files/lib/functions.sh (existing callers unchanged).]
- rootfs content changed: lib/functions/procd.sh [allowed: procd upstream files/procd.sh changed in the merge; package release r1 -> r2.]
- rootfs content changed: lib/modules/6.18.60/cfg80211.ko [allowed: mac80211 7.2-r14: upstream subsys 490 cfg80211 RTS-threshold fix from the merge.]
- rootfs content changed: lib/modules/6.18.60/mac80211.ko [allowed: mac80211 7.2-r14: upstream subsys 484-490 fixes (airtime, chanctx, PS drain, RX BA timer, fragments) from the merge.]
- rootfs content changed: lib/modules/6.18.60/nft_fullcone.ko [allowed: upstream fullconenat-nft d42cc475c6 'fullconenat-nft: honour the port range and the flags' bumps PKG_RELEASE 3->4 and refreshes its patches (011); the module is rebuilt (20,576 -> 21,172 B).]
- rootfs content changed: lib/netifd/ppp-net-init [allowed: ppp upstream files/lib/netifd/ppp-net-init changed in the merge.]
- rootfs content changed: lib/netifd/proto/ppp.sh [allowed: ppp upstream files/ppp.sh changed in the merge.]
- rootfs content changed: sbin/block [allowed: block-mount shares the fstools source bump 907cf449 -> 5e371ec.]
- rootfs content changed: usr/lib/libcrypto.so.3 [allowed: openssl embeds SOURCE_DATE_EPOCH (tree commit timestamp): RUN3 1794677928 (cd14ffa) -> RUN4 1794717694 (3ac18fb9 merge tip).]
- rootfs content removed: usr/lib/pppd/2.5.4 [allowed: ppp 2.5.4->2.5.5 (upstream commit dd72c4c198 'ppp: update to 2.5.5') moves the plugin directory; the comparator lists the whole directory entry (the individual pppoe.so move is already covered).]
- rootfs content removed: usr/lib/pppd/2.5.4/pppoe.so [allowed: ppp-mod-pppoe plugin path follows PKG_VERSION 2.5.4 -> 2.5.5 (old file removed).]
- rootfs content added: usr/lib/pppd/2.5.5 [allowed: ppp 2.5.4->2.5.5 (upstream commit dd72c4c198 'ppp: update to 2.5.5') adds the new plugin directory; the comparator lists the whole directory entry (the individual pppoe.so add is already covered).]
- rootfs content added: usr/lib/pppd/2.5.5/pppoe.so [allowed: ppp-mod-pppoe plugin path follows PKG_VERSION 2.5.4 -> 2.5.5 (new file).]
- rootfs content changed: usr/lib/uhttpd_ubus.so [allowed: uhttpd source ca796d7d -> 93b05e0b rebuild of its ubus plugin.]
- rootfs content changed: usr/sbin/pppd [allowed: ppp 2.5.4-r7 -> 2.5.5-r1 (upstream ppp 2.5.5 source plus the refreshed build/patches from the merge).]
- rootfs content changed: usr/sbin/uhttpd [allowed: uhttpd source ca796d7d -> 93b05e0b (upstream uhttpd update in the merge).]
- rootfs content removed: usr/share/firewall4/templates/mangle-rule.uc [allowed: firewall4 source e6f600c4 -> 3722eadc (merge templates).]
- rootfs content changed: usr/share/firewall4/templates/redirect.uc [allowed: firewall4 source e6f600c4 -> 3722eadc (merge templates).]
- rootfs content changed: usr/share/firewall4/templates/rule.uc [allowed: firewall4 source e6f600c4 -> 3722eadc (merge templates).]
- rootfs content changed: usr/share/ucode/fw4.uc [allowed: firewall4 source e6f600c4 -> 3722eadc (merge templates).]
- apk package block-mount: 2026.10.18~907cf449-r2 -> 2026.11.07~5e371ecf-r2 [allowed: shares the fstools source date/commit bump 907cf449 -> 5e371ec.]
- apk package busybox: 1.38.0-r4 -> 1.38.0-r5 [allowed: upstream busybox PKG_RELEASE 4 -> 5 (BusyBox default/config refresh).]
- apk package firewall4: 2026.10.29~e6f600c4-r1 -> 2026.11.08~3722eadc-r1 [allowed: upstream firewall4 source date/commit 2026.10.29~e6f600c4 -> 2026.11.08~3722eadc.]
- apk package fstools: 2026.10.18~907cf449-r2 -> 2026.11.07~5e371ecf-r2 [allowed: source date/commit 2026.10.18~907cf449 -> 2026.11.07~5e371ec (PKG_RELEASE stays 2: our patch 204 bump plus the upstream commit).]
- apk package kmod-cfg80211: 6.18.60.7.2-r12 -> 6.18.60.7.2-r14 [allowed: mac80211 PKG_RELEASE 12 -> 14 (kmod version 6.18.60.7.2-r12 -> r14).]
- apk package kmod-mac80211: 6.18.60.7.2-r12 -> 6.18.60.7.2-r14 [allowed: mac80211 PKG_RELEASE 12 -> 14 (kmod version 6.18.60.7.2-r12 -> r14).]
- apk package kmod-nft-fullcone: 6.18.60.2023.05.17~07d93b62-r3 -> 6.18.60.2023.05.17~07d93b62-r4 [allowed: fullconenat-nft d42cc475c6 bumps PKG_RELEASE 3->4 (module rebuilt from the refreshed patches).]
- apk package ppp: 2.5.4-r7 -> 2.5.5-r1 [allowed: upstream ppp PKG_VERSION 2.5.4 -> 2.5.5, PKG_RELEASE 7 -> 1.]
- apk package ppp-mod-pppoe: 2.5.4-r7 -> 2.5.5-r1 [allowed: follows the ppp 2.5.4 -> 2.5.5 bump, plugin path moves to /usr/lib/pppd/2.5.5.]
- apk package procd: 2026.11.03~fb611687-r1 -> 2026.11.03~fb611687-r2 [allowed: upstream procd PKG_RELEASE 1 -> 2.]
- apk package procd-seccomp: 2026.11.03~fb611687-r1 -> 2026.11.03~fb611687-r2 [allowed: subpackage of procd, follows PKG_RELEASE 1 -> 2.]
- apk package procd-ujail: 2026.11.03~fb611687-r1 -> 2026.11.03~fb611687-r2 [allowed: subpackage of procd, follows PKG_RELEASE 1 -> 2.]
- apk package uhttpd: 2026.10.19~ca796d7d-r1 -> 2026.11.05~93b05e0b-r1 [allowed: upstream uhttpd source date/commit 2026.10.19~ca796d7d -> 2026.11.05~93b05e0b.]
- apk package uhttpd-mod-ubus: 2026.10.19~ca796d7d-r1 -> 2026.11.05~93b05e0b-r1 [allowed: subpackage of uhttpd, follows the source bump to 93b05e0b.]

### Notes

- kernel CRC differs: 230337506 -> 3136383969 (derived from the payload)
- rootfs CRC differs: 1791871159 -> 1189507840 (derived from the payload)
- kernel region sha256 differs: "ebc4d213ad5bb4a3b59d5c2890d533adc178811c389b5963fc94fae92bd5d232" -> "193233e24eabc7f2ff0138c7dd95051014230672ed7bbb26958186f1d485e4fc" (derived from the payload)
- uImage header CRC (stored) differs: 2047225196 -> 1274137271 (derived from the payload)
- uImage data CRC differs: 1938013036 -> 4179420469 (derived from the payload)
- rootfs extent sha256 differs: "d4c32ea53dcf82b3928cca27d3f2da354d70e78e635cecedff2a466211b0f044" -> "a6a247c1e4cbd22cad1b6df16e9732c94581518e131a6c5685e8b0dcb3995f60" (derived from the payload)
- squashfs bytes used differs: 12872431 -> 12878059 (derived from the payload)
- squashfs inode count differs: 1754 -> 1753 (derived from the payload)
- squashfs fragment count differs: 59 -> 60 (derived from the payload)
- apk key: embedded public key matches /home/qc233/zte/e2631-apk-public-key.pem (DER sha256 b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d)

## Factory header

| field | run-43623162108 | 44766496013 | status |
|---|---|---|---|
| outer magic | ����DDDDUUUU���� | ����DDDDUUUU���� | same |
| header offset field | 0 | 0 | same |
| inner magic | 3333ffff�������� | 3333ffff�������� | same |
| version field | "ImmortalWrt v1.10.0" | "ImmortalWrt v1.10.0" | same |
| product field | "ZXHN E2631 V1.0.0" | "ZXHN E2631 V1.0.0" | same |
| hw field | "V1.1.1" | "V1.1.1" | same |
| build field | "20261114" | "20261120" | stamp-diff |
| key1 | 4945 | 4945 | same |
| key2 | 21009 | 21009 | same |
| body size | 22020096 | 22020096 | same |
| kernel size (declared) | 4194272 | 4194272 | same |
| kernel file offset | 564 | 564 | same |
| kernel CRC | 230337506 | 3136383969 | DIFF |
| rootfs size (declared) | 12976128 | 12976128 | same |
| rootfs file offset | 4194836 | 4194836 | same |
| rootfs CRC | 1791871159 | 1189507840 | DIFF |
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

| field | run-43623162108 | 44766496013 | status |
|---|---|---|---|
| kernel region sha256 | "ebc4d213ad5bb4a3b59d5c2890d533adc178811c389b5963fc94fae92bd5d232" | "193233e24eabc7f2ff0138c7dd95051014230672ed7bbb26958186f1d485e4fc" | DIFF |
| slot marker | 3333���̈����������������������� | 3333���̈����������������������� | same |
| uImage magic | 654645590 | 654645590 | same |
| uImage header CRC (stored) | 2047225196 | 1274137271 | DIFF |
| uImage time | 1794677928 | 1795188482 | stamp-diff |
| uImage payload size | 3491850 | 3491546 | DIFF |
| uImage load/entry | "1073774592/1073774592" | "1073774592/1073774592" | same |
| uImage data CRC | 1938013036 | 4179420469 | DIFF |
| uImage os/arch/type/comp | "5/2/2/0" | "5/2/2/0" | same |
| uImage name | "ARM ImmortalWrt Linux-6.18.60" | "ARM ImmortalWrt Linux-6.18.60" | same |
| kernel payload sha256 | "fa51a7fbe0cf1c6dac1db5103dfb61f71fafcb9b9d59abdd7fe8e561c2ccc608" | "d96e0638ed4fc555a538e4b722de1a11edb60f16e4473fe6682417b06d82d284" | DIFF |

## Rootfs image

| field | run-43623162108 | 44766496013 | status |
|---|---|---|---|
| rootfs extent sha256 | "d4c32ea53dcf82b3928cca27d3f2da354d70e78e635cecedff2a466211b0f044" | "a6a247c1e4cbd22cad1b6df16e9732c94581518e131a6c5685e8b0dcb3995f60" | DIFF |
| squashfs magic | "hsqs" | "hsqs" | same |
| squashfs mkfs time | 1794677928 | 1795188482 | stamp-diff |
| squashfs block size | 262144 | 262144 | same |
| squashfs compression | 4 | 4 | same |
| squashfs bytes used | 12872431 | 12878059 | DIFF |
| squashfs inode count | 1754 | 1753 | DIFF |
| squashfs fragment count | 59 | 60 | DIFF |
| squashfs version | "4.0" | "4.0" | same |

## Version and package database

| field | run-43623162108 | 44766496013 | status |
|---|---|---|---|
| DISTRIB_REVISION | r0-cd14ffa | r0-5202d4c | stamp-diff |
| etc/openwrt_release | 224 B | 224 B | DIFF |
| etc/os-release | 704 B | 704 B | DIFF |
| usr/lib/os-release | 704 B | 704 B | DIFF |
| etc/e2631-version | 20 B | 20 B | same |
| etc/apk/world | 2971 B | 2971 B | DIFF |
| etc/openwrt_version | 11 B | 11 B | DIFF |
| apk installed db | {"sameVersions":197,"stampDiffs":1,"badDiffs":14,"sampleStamp":[{"name":"base-files","ref":"1~cd14ffa","cand":"1~5202d4c","kind":"stamp"}],"sampleBad":[{"name":"block-mount","ref":"2026.10.18~907cf449-r2","cand":"2026.11.07~5e371ecf-r2","kind":"version"},{"name":"busybox","ref":"1.38.0-r4","cand":"1.38.0-r5","kind":"version"},{"name":"firewall4","ref":"2026.10.29~e6f600c4-r1","cand":"2026.11.08~3722eadc-r1","kind":"version"},{"name":"fstools","ref":"2026.10.18~907cf449-r2","cand":"2026.11.07~5e371ecf-r2","kind":"version"},{"name":"kmod-cfg80211","ref":"6.18.60.7.2-r12","cand":"6.18.60.7.2-r14","kind":"version"},{"name":"kmod-mac80211","ref":"6.18.60.7.2-r12","cand":"6.18.60.7.2-r14","kind":"version"},{"name":"kmod-nft-fullcone","ref":"6.18.60.2023.05.17~07d93b62-r3","cand":"6.18.60.2023.05.17~07d93b62-r4","kind":"version"},{"name":"ppp","ref":"2.5.4-r7","cand":"2.5.5-r1","kind":"version"},{"name":"ppp-mod-pppoe","ref":"2.5.4-r7","cand":"2.5.5-r1","kind":"version"},{"name":"procd","ref":"2026.11.03~fb611687-r1","cand":"2026.11.03~fb611687-r2","kind":"version"},{"name":"procd-seccomp","ref":"2026.11.03~fb611687-r1","cand":"2026.11.03~fb611687-r2","kind":"version"},{"name":"procd-ujail","ref":"2026.11.03~fb611687-r1","cand":"2026.11.03~fb611687-r2","kind":"version"}]} |  | DIFF |

## SOURCE-INFO

| field | run-43623162108 | 44766496013 | status |
|---|---|---|---|
| APK signing key | pinned input, public key sha256 9edb11a9d0879b6626e6980f7d182c7b20541adccae59a14acade68b9a62c1f8 | pinned input, public key sha256 9edb11a9d0879b6626e6980f7d182c7b20541adccae59a14acade68b9a62c1f8 | same |
| Hardware tested | NO | NO | same |
| ImmortalWrt base | https://github.com/immortalwrt/immortalwrt master @ 4765b657625ec5bbda74b44400465fe043802b30 | https://github.com/immortalwrt/immortalwrt master @ 4765b657625ec5bbda74b44400465fe043802b30 | same |
| ImmortalWrt tree (pristine) | 340ae5426d1c8dfa071e97f08993393b87a47671 | 340ae5426d1c8dfa071e97f08993393b87a47671 | same |
| Kernel | 6.18.60 | 6.18.60 | same |
| Kernel build id | e2631-build@immortalwrt-e2631 (P5, from the seed) | e2631-build@immortalwrt-e2631 (P5, from the seed) | same |
| Kit commit | 8d87bfa5a02d9ff4919a3b0eadc6f4f3429349c0 | fd80c1a2b5d58f191096142cb8e1816bb9131d46 | stamp-diff |
| LuCI commit | ad75cde88e694b511100576bfbe0a280e5efe6ef | ad75cde88e694b511100576bfbe0a280e5efe6ef | same |
| LuCI feed | https://github.com/immortalwrt/luci.git | https://github.com/immortalwrt/luci.git | same |
| Merged ImmortalWrt master | <missing> | @ a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5 (2026-11-14) | stamp-diff |
| Packages commit | decf94639ffd6ddd26591c190b547c6b7eea150b | decf94639ffd6ddd26591c190b547c6b7eea150b | same |
| Packages feed | https://github.com/immortalwrt/packages.git | https://github.com/immortalwrt/packages.git | same |
| Parity reproduction | false (build stamp date-of-run) | false (build stamp date-of-run) | same |
| Port base tree (4 patches applied) | 4f89aa7ad0a5132dc047a27a9073b43916f0f957 | 4f89aa7ad0a5132dc047a27a9073b43916f0f957 | same |
| Port patch 0001 sha256 | 669f41e436c258d2982dc5998efe82ae54230fbfaa0c1cd60fd148d067c07ffc | 669f41e436c258d2982dc5998efe82ae54230fbfaa0c1cd60fd148d067c07ffc | same |
| Port patch 0002 sha256 | a512521bd8ae6dba12b44e989e1a6554e0ed0dd21e769dd453a6fafb5a472dcf | a512521bd8ae6dba12b44e989e1a6554e0ed0dd21e769dd453a6fafb5a472dcf | same |
| Port patch 0003 sha256 | 67280d1b531b0a9734f1083b527f933a47c68711b5d0d9820bc38c2bba2dc4d7 | 67280d1b531b0a9734f1083b527f933a47c68711b5d0d9820bc38c2bba2dc4d7 | same |
| Port patch 0004 sha256 | 8f4b2eee62d23f7be0923d742b7eb32fcb207ee936fcac20296020f769490035 | 8f4b2eee62d23f7be0923d742b7eb32fcb207ee936fcac20296020f769490035 | same |
| Run | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43623162108 | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44766496013 | stamp-diff |
| Tree fork | https://github.com/QC3284/immortalwrt e2631 @ cd14ffa091f63116859ae8bd6d262f08778629a8 | https://github.com/QC3284/immortalwrt e2631 @ 5202d4cadca831c5394b4ceca32df22c123d46a7 | stamp-diff |

## verify_pkg

| side | rc | FAIL lines | WARN lines | ALL CHECKS PASSED |
|---|---|---|---|---|
| run-43623162108 | 0 | 0 | 1 | true |
| 44766496013 | 0 | 0 | 1 | true |

## APK signing key

| side | file | bytes | DER sha256 |
|---|---|---|---|
| ref | etc/apk/keys/public-key.pem | 178 | b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d |
| cand | etc/apk/keys/public-key.pem | 178 | b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d |
| local reference | /home/qc233/zte/e2631-apk-public-key.pem | - | b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d |

- private key material inside either rootfs: none

## Rootfs content

- entries: 1753 -> 1752
- unexplained content differences: 0
- stamp-only file differences (revision/date text): 5
- mtime-only differences: 1718

| path | kind | explanation |
|---|---|---|
| etc/apk/world | stamp | revision/date text only |
| etc/banner | stamp | revision/date text only |
| etc/openwrt_release | stamp | revision/date text only |
| etc/openwrt_version | stamp | revision/date text only |
| usr/lib/os-release | stamp | revision/date text only |

