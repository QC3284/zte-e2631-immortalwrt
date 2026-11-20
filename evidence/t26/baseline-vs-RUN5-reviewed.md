# E2631 tree-fork parity report

- reference: baseline-43572710065  /home/qc233/zte/e2631-t5-artifacts/parity-43572710065/e2631-build-43572710065/release/e2631-immortalwrt-experimental.bin
  - size 22020628 B, sha256 4e31df936cec8c02fd25cff83d98efc59c10bc2e877149d7f3c411a6dd2f9e9f
  - uImage time 1794624080, squashfs mkfs time 1794624080, revision r0-bde1448
- candidate: 44766496013  /home/qc233/zte/e2631-t5-artifacts/parity-44766496013/e2631-build-44766496013/release/e2631-immortalwrt-experimental.bin
  - size 22020628 B, sha256 3a5914edac7dd973c4a86c2c97de5854ed348466701204d5d0903b1972439050
  - uImage time 1795188482, squashfs mkfs time 1795188482, revision r0-5202d4c

## Verdict

**PASS-REVIEWED-DIFFS**

- factory image byte-identical: no
- kernel payload identical (uImage data + slot marker): no
- rootfs content identical apart from revision/date stamps (path/mode/uid/gid/content): no
- rootfs stamp-only file differences: 4, mtime-only entries: 1669
- expected differences: 22, accepted by review policy: 103, unexpected differences: 0

### Explained differences (expected by design)

- build field: "20261114" -> "20261120" (build stamp)
- uImage time: 1794624080 -> 1795188482 (build stamp)
- squashfs mkfs time: 1794624080 -> 1795188482 (build stamp)
- rootfs file differs only in revision/date stamps: etc/banner
- rootfs file differs only in revision/date stamps: etc/openwrt_release
- rootfs file differs only in revision/date stamps: etc/openwrt_version
- rootfs file differs only in revision/date stamps: usr/lib/os-release
- 1669 rootfs entries differ only in mtime (epoch 1794624080 -> 1795188482)
- revision string: r0-bde1448 -> r0-5202d4c
- etc/openwrt_release: differs only in revision/date stamps
- etc/os-release: differs only in revision/date stamps
- usr/lib/os-release: differs only in revision/date stamps
- etc/openwrt_version: differs only in revision/date stamps
- apk version base-files: 1~bde1448 -> 1~5202d4c (revision suffix)
- SOURCE-INFO APK signing key: undefined -> pinned input, public key sha256 9edb11a9d0879b6626e6980f7d182c7b20541adccae59a14acade68b9a62c1f8
- SOURCE-INFO Base kind: immortalwrt -> undefined
- SOURCE-INFO Kernel build id: undefined -> e2631-build@immortalwrt-e2631 (P5, from the seed)
- SOURCE-INFO Kit commit: 535c0fef0cf3d554c7aff04891ef44487ec942ce -> fd80c1a2b5d58f191096142cb8e1816bb9131d46
- SOURCE-INFO Merged ImmortalWrt master: undefined -> @ a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5 (2026-11-14)
- SOURCE-INFO Parity reproduction: true (build stamp 20261114) -> false (build stamp date-of-run)
- SOURCE-INFO Run: https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43572710065 -> https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44766496013
- SOURCE-INFO Tree fork: https://github.com/QC3284/immortalwrt e2631 @ e96aed31c45442374e9a37fd84c1ac048be90613 -> https://github.com/QC3284/immortalwrt e2631 @ 5202d4cadca831c5394b4ceca32df22c123d46a7

### Accepted differences (review policy: T-26 baseline-43572710065 vs merge candidate (v1.10.0 -> batch-2 fixes -> upstream master a4ba8240 merge + firewall4 fullcone re-anchor; kernel patch set changed -> merge-class kernel delta))

- uImage payload size: 3490610 -> 3491546 [allowed: Kernel rebuild inputs changed in three documented classes across this span: (1) CONFIG_KERNEL_DEVMEM=y (6b609d7) and the batch-2 fix series vs the pre-DEVMEM baseline; (2) the a4ba8240 merge updated the reference kernel patch set (13 files under target/linux/generic/patches-6.18: OEM SFP+ONU quirk, 802-01..04 phylib/usb PHY interrupt backports, 904-debloat_dma_buf, 750-753 SFP quirks, 792 wireguard sticky source, 801-01/896-03 net-phy) while kernel-6.18 (6.18.60) and the kernel config hash 106ff47d... stayed unchanged; (3) the candidate tree tip moves KBUILD_BUILD_TIMESTAMP. Effect: built-in kernel code recompiles and the section layout shifts, so kernel-deep-compare reports NON-STAMP-DIFF against both references; accepted only via verify-task26.sh --kernel-merge-class, which re-derives config/version/seed invariance and that every changed kernel-input path is confined to target/linux/{generic,sanechips}, include/kernel-{defaults,version}.mk or package/kernel with at least one generic patch changed. Residual risk: kernel behaviour follows the upstream reference patch set; no e2631-specific kernel patch changed.]
- kernel payload sha256: "2a3d3a9807e478f2f2a9f4ecf59967d1b9a1d2ba5f1b5fe725936b01a8032f73" -> "d96e0638ed4fc555a538e4b722de1a11edb60f16e4473fe6682417b06d82d284" [allowed: Kernel rebuild inputs changed in three documented classes across this span: (1) CONFIG_KERNEL_DEVMEM=y (6b609d7) and the batch-2 fix series vs the pre-DEVMEM baseline; (2) the a4ba8240 merge updated the reference kernel patch set (13 files under target/linux/generic/patches-6.18: OEM SFP+ONU quirk, 802-01..04 phylib/usb PHY interrupt backports, 904-debloat_dma_buf, 750-753 SFP quirks, 792 wireguard sticky source, 801-01/896-03 net-phy) while kernel-6.18 (6.18.60) and the kernel config hash 106ff47d... stayed unchanged; (3) the candidate tree tip moves KBUILD_BUILD_TIMESTAMP. Effect: built-in kernel code recompiles and the section layout shifts, so kernel-deep-compare reports NON-STAMP-DIFF against both references; accepted only via verify-task26.sh --kernel-merge-class, which re-derives config/version/seed invariance and that every changed kernel-input path is confined to target/linux/{generic,sanechips}, include/kernel-{defaults,version}.mk or package/kernel with at least one generic patch changed. Residual risk: kernel behaviour follows the upstream reference patch set; no e2631-specific kernel patch changed.]
- kernel payload bytes differ [allowed: Kernel rebuild inputs changed in three documented classes across this span: (1) CONFIG_KERNEL_DEVMEM=y (6b609d7) and the batch-2 fix series vs the pre-DEVMEM baseline; (2) the a4ba8240 merge updated the reference kernel patch set (13 files under target/linux/generic/patches-6.18: OEM SFP+ONU quirk, 802-01..04 phylib/usb PHY interrupt backports, 904-debloat_dma_buf, 750-753 SFP quirks, 792 wireguard sticky source, 801-01/896-03 net-phy) while kernel-6.18 (6.18.60) and the kernel config hash 106ff47d... stayed unchanged; (3) the candidate tree tip moves KBUILD_BUILD_TIMESTAMP. Effect: built-in kernel code recompiles and the section layout shifts, so kernel-deep-compare reports NON-STAMP-DIFF against both references; accepted only via verify-task26.sh --kernel-merge-class, which re-derives config/version/seed invariance and that every changed kernel-input path is confined to target/linux/{generic,sanechips}, include/kernel-{defaults,version}.mk or package/kernel with at least one generic patch changed. Residual risk: kernel behaviour follows the upstream reference patch set; no e2631-specific kernel patch changed.]
- rootfs content changed: bin/busybox [allowed: busybox 1.38.0-r5: upstream changes BusyBox default config (edit history 256->2000 unless SMALL_FLASH/LOW_MEMORY_FOOTPRINT; FEATURE_SH_HISTFILESIZE default y), so the binary is rebuilt.]
- rootfs content changed: etc/apk/keys/public-key.pem [allowed: P8: baseline is the pre-pin parity build with a random per-build ECDSA key; RUN1 signs with the pinned key (public half = the local reference PEM, file sha256 9edb11a9..., DER b0cbe6fb...).]
- rootfs content changed: etc/apk/world [allowed: tree pin lines change only: base-files=1~cd14ffa replaces 1~bde1448; the kernel version hash 106ff47d reflects CONFIG_DEVMEM=y (same as RUN1/RUN2); package selection unchanged.]
- rootfs content changed: etc/board.d/02_network [allowed: 235fe12 SPDX header line added (cd14ffa).]
- rootfs content changed: etc/config/e2631 [allowed: f3776b3 documents the snapshot-marker gate of the userdata extroot in the storage section.]
- rootfs content changed: etc/config/firewall [allowed: firewall4 upstream source e6f600c4->3722eadc (OpenWrt core commit dab12e7663 'firewall4: update to Git HEAD (2026-11-08)'); the firewall4 repo range e6f600c4..3722eadc updates root/etc/config/firewall (notably 'config: add dest addr restrictions for DHCPv6 rules' and 'templates: remove stray file'): the Allow-DHCPv6 rule gains dest_ip fe80::/10 and two stale commented lines drop; our local fullcone/flow_offloading settings are unchanged.]
- rootfs content changed: etc/config/fstab [allowed: f3776b3/72eff3b extroot gate and fstools flow.]
- rootfs content changed: etc/config/uhttpd [allowed: uhttpd upstream files/uhttpd.config changed in the merge.]
- rootfs content changed: etc/diag.sh [allowed: 76dcaee keeps SSH and HTTP(S) off the WAN by default.]
- rootfs content changed: etc/hotplug.d/firmware/11-mt76-caldata [allowed: 235fe12 SPDX header line added (cd14ffa).]
- rootfs content changed: etc/hotplug.d/ieee80211/05-fix-wifi-mac [allowed: 235fe12 SPDX header line added (cd14ffa).]
- rootfs content changed: etc/hotplug.d/iface/20-e2631-netune [allowed: fix series + style pass (netune changes in the 83df1a9 tree).]
- rootfs content changed: etc/init.d/e2631-hb [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: etc/init.d/e2631-leds [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: etc/init.d/e2631-netune [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: etc/init.d/e2631-trial [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: etc/init.d/e2631-userdata [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: etc/init.d/e2631-wifi-eeprom [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: etc/init.d/e2631-wifi-load [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: etc/init.d/uhttpd [allowed: uhttpd upstream files/uhttpd.init changed in the merge.]
- rootfs content changed: etc/profile.d/busybox-history-file.sh [allowed: busybox upstream files/busybox-history-file.sh now exports HISTFILESIZE/HISTSIZE=256 alongside HISTFILE.]
- rootfs content changed: etc/rc.button/lights_toggle [allowed: 235fe12 SPDX header line added (cd14ffa).]
- rootfs content changed: etc/rc.wps/00-h3600-ledblink [allowed: 235fe12 SPDX header line added (cd14ffa).]
- rootfs content changed: etc/uci-defaults/60_e2631_flashmenu [allowed: b2e15d4 style pass; 76dcaee WAN default policy where it touches the defaults.]
- rootfs content changed: etc/uci-defaults/61_e2631_timezone [allowed: b2e15d4 style pass; 76dcaee WAN default policy where it touches the defaults.]
- rootfs content changed: etc/uci-defaults/62_e2631_netune_cron [allowed: b2e15d4 style pass; 76dcaee WAN default policy where it touches the defaults.]
- rootfs content removed: etc/uci-defaults/63_e2631_wan_access [allowed: 76dcaee: SSH/HTTP(S) are no longer opened on the WAN by default (the file is intentionally gone).]
- rootfs content changed: etc/uci-defaults/99_e2631_flowoffload [allowed: b2e15d4 style pass; 76dcaee WAN default policy where it touches the defaults.]
- rootfs content changed: etc/uci-defaults/99_e2631_lang [allowed: b2e15d4 style pass; 76dcaee WAN default policy where it touches the defaults.]
- rootfs content changed: lib/apk/db/installed [allowed: package DB reflects the expected version set: base-files revision stamp r0-cd14ffa, fstools/block-mount r2, kernel config hash 106ff47d, and the batch-2 script bytes (marker hardening + SPDX).]
- rootfs content changed: lib/apk/db/scripts.tar.gz [allowed: install scripts of the e2631 packages changed in the 83df1a9 fix series and again in batch-2 (marker hardening, SPDX headers).]
- rootfs content changed: lib/apk/packages/base-files.conffiles_static [allowed: derived from the base-files revision only (r0-bde1448 -> r0-cd14ffa).]
- rootfs content changed: lib/apk/packages/base-files.list [allowed: derived from the base-files revision only (r0-bde1448 -> r0-cd14ffa).]
- rootfs content changed: lib/apk/packages/firewall4.conffiles_static [allowed: derived: records the sha256 of the refreshed /etc/config/firewall conffile (6dd76112... -> 055145fd...).]
- rootfs content changed: lib/apk/packages/firewall4.list [allowed: firewall4 e6f600c4..3722eadc 'templates: remove stray file' drops /usr/share/firewall4/templates/mangle-rule.uc from the installed file list; the remaining templates stay.]
- rootfs content changed: lib/apk/packages/ppp-mod-pppoe.list [allowed: ppp-mod-pppoe installed file list moves with PKG_VERSION 2.5.4 -> 2.5.5.]
- rootfs content changed: lib/apk/packages/uhttpd.conffiles_static [allowed: records the sha256 of the updated /etc/config/uhttpd conffile.]
- rootfs content added: lib/e2631-snapshot.sh [allowed: f3776b3 snapshot identity gate; 4b610dc empty/unknown marker hardening (write-back verification, hard failure on empty identity).]
- rootfs content changed: lib/functions.sh [allowed: base-files: upstream 4765b657..a4ba8240 adds path_normalize() to files/lib/functions.sh (existing callers unchanged).]
- rootfs content changed: lib/functions/procd.sh [allowed: procd upstream files/procd.sh changed in the merge; package release r1 -> r2.]
- rootfs content changed: lib/libfstools.so [allowed: 72eff3b (fstools 204: skip the jffs2 sync when there is no upper) rebuilds fstools/block-mount as r2. | merge bucket: fstools source bump 907cf449 -> 5e371ec ('block: don't log an error when fstab is missing'); our patches 203/204 still apply, PKG_RELEASE stays 2.]
- rootfs content changed: lib/modules/6.18.60/cfg80211.ko [allowed: mac80211 7.2-r14: upstream subsys 490 cfg80211 RTS-threshold fix from the merge.]
- rootfs content changed: lib/modules/6.18.60/mac80211.ko [allowed: mac80211 7.2-r14: upstream subsys 484-490 fixes (airtime, chanctx, PS drain, RX BA timer, fragments) from the merge.]
- rootfs content changed: lib/modules/6.18.60/nft_fullcone.ko [allowed: upstream fullconenat-nft d42cc475c6 'fullconenat-nft: honour the port range and the flags' bumps PKG_RELEASE 3->4 and refreshes its patches (011); the module is rebuilt (20,576 -> 21,172 B).]
- rootfs content changed: lib/netifd/ppp-net-init [allowed: ppp upstream files/lib/netifd/ppp-net-init changed in the merge.]
- rootfs content changed: lib/netifd/proto/ppp.sh [allowed: ppp upstream files/ppp.sh changed in the merge.]
- rootfs content changed: lib/preinit/79_e2631_userdata [allowed: f3776b3 extroot snapshot gate; 4b610dc refuses adoption when the firmware has no usable identity.]
- rootfs content changed: lib/upgrade/platform.sh [allowed: fix series in the 83df1a9 tree (slot/userdata decision helpers).]
- rootfs content changed: sbin/block [allowed: block-mount shares the fstools source bump 907cf449 -> 5e371ec.]
- rootfs content changed: sbin/e2631-commit [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-fwstate [allowed: 6b609d7 DEVMEM path (fwstate reads /dev/mem) + style pass.]
- rootfs content changed: sbin/e2631-hb [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-leds [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-linkspeed [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-netune-apply [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-preflight [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-probe [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-trial [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-upgrade [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-userdata-firstboot [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-userdata-init [allowed: 83df1a9 fix series + style; 4b610dc marker write-then-read-back check (empty or wrong identity fails the apply).]
- rootfs content changed: sbin/e2631-userdata-status [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-wanport [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-wifi-ap [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-wifi-boot [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: sbin/e2631-wifi-on [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass]
- rootfs content changed: usr/lib/libcrypto.so.3 [allowed: openssl embeds SOURCE_DATE_EPOCH (tree commit timestamp) in its built-on string: baseline 1794624080, RUN3 1794677928 (cd14ffa). | merge bucket: openssl embeds SOURCE_DATE_EPOCH (tree commit timestamp): RUN3 1794677928 (cd14ffa) -> RUN4 1794717694 (3ac18fb9 merge tip).]
- rootfs content removed: usr/lib/pppd/2.5.4 [allowed: ppp 2.5.4->2.5.5 (upstream commit dd72c4c198 'ppp: update to 2.5.5') moves the plugin directory; the comparator lists the whole directory entry (the individual pppoe.so move is already covered).]
- rootfs content removed: usr/lib/pppd/2.5.4/pppoe.so [allowed: ppp-mod-pppoe plugin path follows PKG_VERSION 2.5.4 -> 2.5.5 (old file removed).]
- rootfs content added: usr/lib/pppd/2.5.5 [allowed: ppp 2.5.4->2.5.5 (upstream commit dd72c4c198 'ppp: update to 2.5.5') adds the new plugin directory; the comparator lists the whole directory entry (the individual pppoe.so add is already covered).]
- rootfs content added: usr/lib/pppd/2.5.5/pppoe.so [allowed: ppp-mod-pppoe plugin path follows PKG_VERSION 2.5.4 -> 2.5.5 (new file).]
- rootfs content changed: usr/lib/uhttpd_ubus.so [allowed: uhttpd source ca796d7d -> 93b05e0b rebuild of its ubus plugin.]
- rootfs content changed: usr/libexec/rpcd/e2631 [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass (rpc daemons follow the board tools).]
- rootfs content changed: usr/libexec/rpcd/e2631-wanport [allowed: tree 83df1a9 fix series (f3776b3 extroot snapshot gate, 76dcaee WAN default policy, 72eff3b fstools 204, 6b609d7 DEVMEM) + b2e15d4 style pass (rpc daemons follow the board tools).]
- rootfs content changed: usr/sbin/miniupnpd [allowed: P6: GITHUB_REF_NAME/GITHUB_SHA stripped from the build step; baseline embedded 'iwrt-adaptation-535c0fef', RUN1 reports plain 'miniupnpd 2.3.11'.]
- rootfs content changed: usr/sbin/pppd [allowed: ppp 2.5.4-r7 -> 2.5.5-r1 (upstream ppp 2.5.5 source plus the refreshed build/patches from the merge).]
- rootfs content changed: usr/sbin/uhttpd [allowed: uhttpd source ca796d7d -> 93b05e0b (upstream uhttpd update in the merge).]
- rootfs content removed: usr/share/firewall4/templates/mangle-rule.uc [allowed: firewall4 source e6f600c4 -> 3722eadc (merge templates).]
- rootfs content changed: usr/share/firewall4/templates/redirect.uc [allowed: firewall4 source e6f600c4 -> 3722eadc (merge templates).]
- rootfs content changed: usr/share/firewall4/templates/rule.uc [allowed: firewall4 source e6f600c4 -> 3722eadc (merge templates).]
- rootfs content changed: usr/share/ucode/fw4.uc [allowed: firewall4 source e6f600c4 -> 3722eadc (merge templates).]
- rootfs content changed: usr/share/ucode/luci/version.uc [allowed: P7: the pinned feed is checked out by SHA, so LuCI reports branch 'LuCI Master' instead of 'HEAD detached at FETCH_HEAD' (revision string itself is unchanged).]
- apk key: embedded public keys differ (452463ab10fdabbd vs b0cbe6fbd709900a) [allowed: P8: baseline is the pre-pin parity build (random per-build key, DER 452463ab...); RUN1/RUN2 use the pinned E2631 key whose public half equals the local reference PEM (DER b0cbe6fb..., file sha256 9edb11a9...). Candidate must match the pin; only the baseline reference may differ.]
- apk key(ref): embedded public key != local reference (452463ab10fdabbd vs b0cbe6fbd709900a) [allowed: P8: baseline is the pre-pin parity build (random per-build key, DER 452463ab...); RUN1/RUN2 use the pinned E2631 key whose public half equals the local reference PEM (DER b0cbe6fb..., file sha256 9edb11a9...). Candidate must match the pin; only the baseline reference may differ.]
- etc/apk/world: content differs beyond stamps [allowed: revision line only: base-files=1~<candidate tree tip> replaces 1~bde1448; kernel line 6.18.60~106ff47d... is unchanged; package selection unchanged.]
- apk package block-mount: 2026.10.18~907cf449-r1 -> 2026.11.07~5e371ecf-r2 [allowed: shares the fstools source package version line, so 72eff3b bumps it to r2 as well. | merge bucket: shares the fstools source date/commit bump 907cf449 -> 5e371ec.]
- apk package busybox: 1.38.0-r4 -> 1.38.0-r5 [allowed: upstream busybox PKG_RELEASE 4 -> 5 (BusyBox default/config refresh).]
- apk package firewall4: 2026.10.29~e6f600c4-r1 -> 2026.11.08~3722eadc-r1 [allowed: upstream firewall4 source date/commit 2026.10.29~e6f600c4 -> 2026.11.08~3722eadc.]
- apk package fstools: 2026.10.18~907cf449-r1 -> 2026.11.07~5e371ecf-r2 [allowed: 72eff3b adds fstools patch 204 (skip the jffs2 sync when there is no upper) -> PKG_RELEASE r1 to r2. | merge bucket: source date/commit 2026.10.18~907cf449 -> 2026.11.07~5e371ec (PKG_RELEASE stays 2: our patch 204 bump plus the upstream commit).]
- apk package kernel: 6.18.60~b0734d7a455aafebfe69bf7a6fda19c8-r1 -> 6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1 [allowed: kernel package version hash derives from the kernel config/patches; CONFIG_KERNEL_DEVMEM=y (6b609d7) changes it, version 6.18.60 is unchanged.]
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

- kernel CRC differs: 330883172 -> 3136383969 (derived from the payload)
- rootfs CRC differs: 3039193554 -> 1189507840 (derived from the payload)
- kernel region sha256 differs: "d873c4991843f5d93668527b932393a782dc1f61c0e73829aa18b75cf109e38d" -> "193233e24eabc7f2ff0138c7dd95051014230672ed7bbb26958186f1d485e4fc" (derived from the payload)
- uImage header CRC (stored) differs: 4210866558 -> 1274137271 (derived from the payload)
- uImage data CRC differs: 2901860915 -> 4179420469 (derived from the payload)
- rootfs extent sha256 differs: "716f520ff7b116f32d511e4e605efc11bcc8235d9bed70184f826bad63c0f5e0" -> "a6a247c1e4cbd22cad1b6df16e9732c94581518e131a6c5685e8b0dcb3995f60" (derived from the payload)
- squashfs bytes used differs: 12869671 -> 12878059 (derived from the payload)
- squashfs inode count differs: 1754 -> 1753 (derived from the payload)
- squashfs fragment count differs: 59 -> 60 (derived from the payload)

## Factory header

| field | baseline-43572710065 | 44766496013 | status |
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
| kernel CRC | 330883172 | 3136383969 | DIFF |
| rootfs size (declared) | 12976128 | 12976128 | same |
| rootfs file offset | 4194836 | 4194836 | same |
| rootfs CRC | 3039193554 | 1189507840 | DIFF |
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

| field | baseline-43572710065 | 44766496013 | status |
|---|---|---|---|
| kernel region sha256 | "d873c4991843f5d93668527b932393a782dc1f61c0e73829aa18b75cf109e38d" | "193233e24eabc7f2ff0138c7dd95051014230672ed7bbb26958186f1d485e4fc" | DIFF |
| slot marker | 3333���̈����������������������� | 3333���̈����������������������� | same |
| uImage magic | 654645590 | 654645590 | same |
| uImage header CRC (stored) | 4210866558 | 1274137271 | DIFF |
| uImage time | 1794624080 | 1795188482 | stamp-diff |
| uImage payload size | 3490610 | 3491546 | DIFF |
| uImage load/entry | "1073774592/1073774592" | "1073774592/1073774592" | same |
| uImage data CRC | 2901860915 | 4179420469 | DIFF |
| uImage os/arch/type/comp | "5/2/2/0" | "5/2/2/0" | same |
| uImage name | "ARM ImmortalWrt Linux-6.18.60" | "ARM ImmortalWrt Linux-6.18.60" | same |
| kernel payload sha256 | "2a3d3a9807e478f2f2a9f4ecf59967d1b9a1d2ba5f1b5fe725936b01a8032f73" | "d96e0638ed4fc555a538e4b722de1a11edb60f16e4473fe6682417b06d82d284" | DIFF |

## Rootfs image

| field | baseline-43572710065 | 44766496013 | status |
|---|---|---|---|
| rootfs extent sha256 | "716f520ff7b116f32d511e4e605efc11bcc8235d9bed70184f826bad63c0f5e0" | "a6a247c1e4cbd22cad1b6df16e9732c94581518e131a6c5685e8b0dcb3995f60" | DIFF |
| squashfs magic | "hsqs" | "hsqs" | same |
| squashfs mkfs time | 1794624080 | 1795188482 | stamp-diff |
| squashfs block size | 262144 | 262144 | same |
| squashfs compression | 4 | 4 | same |
| squashfs bytes used | 12869671 | 12878059 | DIFF |
| squashfs inode count | 1754 | 1753 | DIFF |
| squashfs fragment count | 59 | 60 | DIFF |
| squashfs version | "4.0" | "4.0" | same |

## Version and package database

| field | baseline-43572710065 | 44766496013 | status |
|---|---|---|---|
| DISTRIB_REVISION | r0-bde1448 | r0-5202d4c | stamp-diff |
| etc/openwrt_release | 224 B | 224 B | DIFF |
| etc/os-release | 704 B | 704 B | DIFF |
| usr/lib/os-release | 704 B | 704 B | DIFF |
| etc/e2631-version | 20 B | 20 B | same |
| etc/apk/world | 2971 B | 2971 B | DIFF |
| etc/openwrt_version | 11 B | 11 B | DIFF |
| apk installed db | {"sameVersions":196,"stampDiffs":1,"badDiffs":15,"sampleStamp":[{"name":"base-files","ref":"1~bde1448","cand":"1~5202d4c","kind":"stamp"}],"sampleBad":[{"name":"block-mount","ref":"2026.10.18~907cf449-r1","cand":"2026.11.07~5e371ecf-r2","kind":"version"},{"name":"busybox","ref":"1.38.0-r4","cand":"1.38.0-r5","kind":"version"},{"name":"firewall4","ref":"2026.10.29~e6f600c4-r1","cand":"2026.11.08~3722eadc-r1","kind":"version"},{"name":"fstools","ref":"2026.10.18~907cf449-r1","cand":"2026.11.07~5e371ecf-r2","kind":"version"},{"name":"kernel","ref":"6.18.60~b0734d7a455aafebfe69bf7a6fda19c8-r1","cand":"6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1","kind":"version"},{"name":"kmod-cfg80211","ref":"6.18.60.7.2-r12","cand":"6.18.60.7.2-r14","kind":"version"},{"name":"kmod-mac80211","ref":"6.18.60.7.2-r12","cand":"6.18.60.7.2-r14","kind":"version"},{"name":"kmod-nft-fullcone","ref":"6.18.60.2023.05.17~07d93b62-r3","cand":"6.18.60.2023.05.17~07d93b62-r4","kind":"version"},{"name":"ppp","ref":"2.5.4-r7","cand":"2.5.5-r1","kind":"version"},{"name":"ppp-mod-pppoe","ref":"2.5.4-r7","cand":"2.5.5-r1","kind":"version"},{"name":"procd","ref":"2026.11.03~fb611687-r1","cand":"2026.11.03~fb611687-r2","kind":"version"},{"name":"procd-seccomp","ref":"2026.11.03~fb611687-r1","cand":"2026.11.03~fb611687-r2","kind":"version"}]} |  | DIFF |

## SOURCE-INFO

| field | baseline-43572710065 | 44766496013 | status |
|---|---|---|---|
| APK signing key | <missing> | pinned input, public key sha256 9edb11a9d0879b6626e6980f7d182c7b20541adccae59a14acade68b9a62c1f8 | stamp-diff |
| Base kind | immortalwrt | <missing> | stamp-diff |
| Hardware tested | NO | NO | same |
| ImmortalWrt base | https://github.com/immortalwrt/immortalwrt master @ 4765b657625ec5bbda74b44400465fe043802b30 | https://github.com/immortalwrt/immortalwrt master @ 4765b657625ec5bbda74b44400465fe043802b30 | same |
| ImmortalWrt tree (pristine) | 340ae5426d1c8dfa071e97f08993393b87a47671 | 340ae5426d1c8dfa071e97f08993393b87a47671 | same |
| Kernel | 6.18.60 | 6.18.60 | same |
| Kernel build id | <missing> | e2631-build@immortalwrt-e2631 (P5, from the seed) | stamp-diff |
| Kit commit | 535c0fef0cf3d554c7aff04891ef44487ec942ce | fd80c1a2b5d58f191096142cb8e1816bb9131d46 | stamp-diff |
| LuCI commit | ad75cde88e694b511100576bfbe0a280e5efe6ef | ad75cde88e694b511100576bfbe0a280e5efe6ef | same |
| LuCI feed | https://github.com/immortalwrt/luci.git | https://github.com/immortalwrt/luci.git | same |
| Merged ImmortalWrt master | <missing> | @ a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5 (2026-11-14) | stamp-diff |
| Packages commit | decf94639ffd6ddd26591c190b547c6b7eea150b | decf94639ffd6ddd26591c190b547c6b7eea150b | same |
| Packages feed | https://github.com/immortalwrt/packages.git | https://github.com/immortalwrt/packages.git | same |
| Parity reproduction | true (build stamp 20261114) | false (build stamp date-of-run) | stamp-diff |
| Port base tree (4 patches applied) | 4f89aa7ad0a5132dc047a27a9073b43916f0f957 | 4f89aa7ad0a5132dc047a27a9073b43916f0f957 | same |
| Port patch 0001 sha256 | 669f41e436c258d2982dc5998efe82ae54230fbfaa0c1cd60fd148d067c07ffc | 669f41e436c258d2982dc5998efe82ae54230fbfaa0c1cd60fd148d067c07ffc | same |
| Port patch 0002 sha256 | a512521bd8ae6dba12b44e989e1a6554e0ed0dd21e769dd453a6fafb5a472dcf | a512521bd8ae6dba12b44e989e1a6554e0ed0dd21e769dd453a6fafb5a472dcf | same |
| Port patch 0003 sha256 | 67280d1b531b0a9734f1083b527f933a47c68711b5d0d9820bc38c2bba2dc4d7 | 67280d1b531b0a9734f1083b527f933a47c68711b5d0d9820bc38c2bba2dc4d7 | same |
| Port patch 0004 sha256 | 8f4b2eee62d23f7be0923d742b7eb32fcb207ee936fcac20296020f769490035 | 8f4b2eee62d23f7be0923d742b7eb32fcb207ee936fcac20296020f769490035 | same |
| Run | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/43572710065 | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44766496013 | stamp-diff |
| Tree fork | https://github.com/QC3284/immortalwrt e2631 @ e96aed31c45442374e9a37fd84c1ac048be90613 | https://github.com/QC3284/immortalwrt e2631 @ 5202d4cadca831c5394b4ceca32df22c123d46a7 | stamp-diff |

## verify_pkg

| side | rc | FAIL lines | WARN lines | ALL CHECKS PASSED |
|---|---|---|---|---|
| baseline-43572710065 | 0 | 0 | 1 | true |
| 44766496013 | 0 | 0 | 1 | true |

## APK signing key

| side | file | bytes | DER sha256 |
|---|---|---|---|
| ref | etc/apk/keys/public-key.pem | 178 | 452463ab10fdabbd9ffede9c629724065fedcdc77635529f2504c7868ca11299 |
| cand | etc/apk/keys/public-key.pem | 178 | b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d |
| local reference | /home/qc233/zte/e2631-apk-public-key.pem | - | b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d |

- private key material inside either rootfs: none

## Rootfs content

- entries: 1753 -> 1752
- unexplained content differences: 0
- stamp-only file differences (revision/date text): 4
- mtime-only differences: 1669

| path | kind | explanation |
|---|---|---|
| etc/banner | stamp | revision/date text only |
| etc/openwrt_release | stamp | revision/date text only |
| etc/openwrt_version | stamp | revision/date text only |
| usr/lib/os-release | stamp | revision/date text only |

### Text-file differences

- etc/apk/world
  - line 3: ref="base-files=1~bde1448" cand="base-files=1~5202d4c"
  - line 25: ref="kernel=6.18.60~b0734d7a455aafebfe69bf7a6fda19c8-r1" cand="kernel=6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1"

