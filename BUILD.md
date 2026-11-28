# BUILD - from a clone of this repository to a package that flashes

This is the whole supported path. README.md explains *why* the port is shaped like
this; this file is the procedure, and every step says what it does and what it
means when it fails.

Everything below runs on one Linux box (a VM, a container, WSL, or bare metal).
The build was developed in WSL2 Ubuntu on Windows, which is why `wsl/` is spelled
that way - those scripts are the same steps, plus the workarounds for one machine's
network. If you are on Linux, use `scripts/`.

```
tree fork (QC3284/immortalwrt e2631 @ pin; device support as commits)
  ->  depth-1 checkout + feeds + seed  ->  make world  ->  collect
  ->  mkfactory pack (header template ships in seed/)  ->  verify x2  ->  flash
```

## 1. What you need

| | |
|---|---|
| OS | any Linux with a working `make`/`gcc`; developed on Ubuntu 22.04 (WSL2) |
| Disk | **~12 GB** for the tree: the measured total here is 11 GB, of which `build_dir` is 8.4 GB, `dl` 573 MB, `feeds` 279 MB, `.git` 16 MB |
| RAM / cores | 4 GB and 2 cores will finish; measured here on 12 cores / 8 GB |
| Time | a from-scratch `make world` was about 40 minutes; with ccache warm and only the target rebuilt, 6 1/2 minutes (measured 2026-10-15 16:18:43 -> 16:25:12) |
| Packages | OpenWrt's own build-dependency set for Debian/Ubuntu (on 22.04: `build-essential clang flex bison g++ gawk gcc gettext libncurses-dev make python3 rsync swig unzip zlib1g-dev file wget`), plus `git`, `curl`, `busybox` for the ash gate, and `ccache` if you want fast rebuilds. `scripts/bootstrap.sh` checks `git make gcc g++ file` and stops with the package name if one is missing |
| Node | **20.15 or newer** (22 LTS recommended). The packer and the screens use `zlib.crc32`, which does not exist before that. `scripts/build.sh` checks it; by hand: `node -p "typeof require('node:zlib').crc32"` must print `function` |
| A serial console | 115200 8N1 on the board's UART. Not optional in practice: the failure modes on this SoC are silent, and `docs/known-issues.md` explains why no other channel survives them |

## 2. The base tree and the version-header template

**The base tree.** The port now lives in a real tree fork:
[QC3284/immortalwrt](https://github.com/QC3284/immortalwrt), branch `e2631`, a fork of
`immortalwrt/immortalwrt`. The zx279128 target (renamed from sanechips in plan C,
2026-11-21), the H3600 board support and the E2631 device packages are ordinary
commits there, and the kit checks that fork out at a pinned tip - there is no
vendored patch series and no `apply.sh` any more (T-12):

    E2631_IW_REPO        https://github.com/immortalwrt/immortalwrt
    E2631_IW_BRANCH      master
    E2631_IW_SHA         a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5    (kernel 6.18.60)
    E2631_IW_TREE_SHA    b905483c80a3a705825ff7aa9c77d1f3db4a01c3    (pristine upstream tree)
    E2631_FORK_REPO      https://github.com/QC3284/immortalwrt
    E2631_FORK_BRANCH    e2631
    E2631_FORK_SHA       86cddb79802bb2223db21f7364613505174968d8    (plan-C rebuild: 18 commits on the base, target renamed zx279128,
                                                                   including the check-size escaping fix)
    E2631_BASE_TREE_SHA  6136bd92d5259dbaf22f6bca02c675f05abdf86b    (tree of the last zx279128 port commit)
    E2631_FORK_DEPTH     32                                          (scratch-history window; measured floor 19)

`scripts/pins.env` is the single pin file. It also records the four reviewed port
commit SHAs (provenance; the old vendored patch files and their sha256 lines are
gone), the two feed commits the released v1.10.0 was built with, and the port
provenance from the original sanechips mirror. Plan C rebased the series onto
`a4ba8240`, so there is no merge commit to name in SOURCE-INFO. `scripts/bootstrap.sh`
fetches the fork tip at **depth 1** for the build tree (parity P2: `COMMITCOUNT` is
`git rev-list --count HEAD .`, so a deeper tree changes `base-files` `PKG_RELEASE`),
and verifies the history in a separate scratch repo: the tip, the base-port tree
(`6136bd92…`), the ImmortalWrt pin ancestry, the four port commit subjects and the
18-commit plan-C series. `make check`'s base-pin gate repeats those assertions on the
scratch repo and fails a tree built from anything else; a drifted feed is re-pinned or
refused.

To change the port, patch and commit in a fork working copy, push, then re-bootstrap with
the new pin - never edit the depth-1 build tree by hand. The old OpenWrt sanechips base
(`Zlion-Y/openwrt-sanechips-mirror`, kernel 6.18.55) was the `legacy` rollback until
T-12; it is retired together with the overlay and the patch series. See
[docs/immortalwrt-migration.md](docs/immortalwrt-migration.md) for the migration decision
and the triple-pin rationale.

**The version-header template.** `tools/mkfactory.mjs pack` copies a 512-byte version
header out of a template and rewrites only the geometry and CRC fields, so the template
has to supply everything the packer does not compute:

    +0x08/+0x0c  upgradeKey1/Key2      +0x6c  product string
    +0x4c..+0x60 slot A/B base + span  +0x8c/+0x98 bootloader inclusion + U-Boot CRC
    +0x110       hw version            +0x1e0..+0x1f8 slot table, serial, isNew

**That header now ships here: `seed/vendor-verhdr-8b8.bin`, 532 bytes, and it is the
default.** No `--template`, no vendor firmware on your disk, and packing still produces a
package the vendor flash page accepts. It is the outer header plus the version header cut
out of `V1.0.0.8B8.8000`; [seed/README.md](seed/README.md) records the source file, its
sha256, and the measurement that matters - packing a build directory twice, once with this
slice and once with the full 21 MB package, gives **the same bytes**
(`02b35106…`, which is also the published `v1.2`).

You still want a real official package in two cases:

* `mkfactory selftest` / `info` read the *payload* the header points at - they are the
  proof that the geometry model matches the vendor's, and they say so plainly when handed
  a header-only file.
* your hardware revision needs a different `upgradeKey1/Key2` pair. The keys are not
  stable across vendor versions: `6B5`/`7B5`/`8B8` all carry `0x1351/0x5211`, but the old
  `4B4` package carries `0x238/0x2e`. Re-cut the slice from a 6B5-or-newer package
  (`head -c 532 official.bin > my-template.bin`) and `host/verify_pkg.mjs` will check the
  packed header against it.

We have not found a copy of an uploaded package left behind on the box - the vendor
flasher is copied into `/var` during an upgrade (`docs/02-...md` section F), the firmware
file itself was not located - and `e2631-fwslot info -j` prints a slot's header *fields*,
not a package you can reuse. The format is fully decoded in
`docs/01-情报汇总与事实核验-2026-10-13.md` section 2 - every field of four official
packages verified by recomputing CRC1 and CRC2 - and `tools/make_fixture.mjs` synthesizes
a self-consistent header from nothing so the slot tool is testable without any vendor
binary. **What has not been tested** is whether the vendor web page accepts a package
built from a *synthesized* header: shipped packages were built from a real one, and that
is the only combination proven to flash.

Override the template only if you need to:

    E2631_TEMPLATE=<path to the official .bin or your own slice>   # absolute, or relative to E2631_WORK

## 3. Configure the paths (optional)

Every machine-specific path has a default that works on a normal clone, and can be
overridden by an environment variable or by `.env` (untracked; copy `.env.example`).
`scripts/env.sh` is the single definition; `host/release.mjs` reads the same `.env`.

| variable | default | meaning |
|---|---|---|
| `E2631_KIT` | found from the script's own location | this repository |
| `E2631_WORK` | parent of the kit | where `out/` lives; relative values in `.env` resolve against it |
| `E2631_OUT` | `$E2631_WORK/out` | build directories, logs, packages |
| `E2631_TREE` | `$HOME/openwrt` | the tree-fork checkout being built (depth 1; bootstrap creates it) |
| `E2631_FORK_REPO/BRANCH/DEPTH` | the pinned fork, `e2631`, depth 32 | what bootstrap fetches; the depth is only for the scratch history checks |
| `E2631_BASE_*` | the pins in `scripts/pins.env` | ImmortalWrt base, expected tree, kernel version - what bootstrap asserts |
| `E2631_TEMPLATE` | `seed/vendor-verhdr-8b8.bin` | the 532-byte version-header template; see section 2 |
| `E2631_PROXY` | unset | http(s) proxy for the download phases |
| `E2631_GNU_MIRROR` | unset | move a fast GNU mirror to the head of `@GNU` |
| `E2631_SEGMENTED` | unset | fetch distfiles as parallel byte ranges (see section 7) |

## 4. Check the clone

    make check            # or: bash scripts/check.sh

Fifteen gates, each reporting PASS / FAIL / SKIP with the reason:

| gate | what it proves |
|---|---|
| `tests/test_upgrade.py` | the online updater fails safely: a bad checksum, an anti-downgrade refusal and a failed download all leave the board alone, the slot decision dispatches correctly, and the label transition `OpenWrt v1.9.0` -> `ImmortalWrt v1.10.0` upgrades in place (the label is stripped before the numeric compare) |
| host-native copies | `tests/native/` holds the host copies of the tree-owned sources the offline gates compile and run (`e2631-fwslot.c`, `e2631-upgrade`, `platform.sh`, `slotpart-core.c`); after a bootstrap this gate `cmp`s each against the tree and, on a mismatch, prints the exact `cp` that syncs it. SKIPs until a tree exists, because there is nothing to compare against |
| `bash -n` | every helper in the kit parses |
| `node --check` | every tool parses |
| busybox ash | the scripts that get put on the *device* parse under the device's shell, with CRLF stripped - a bashism or a `\r` here only shows up on the board |
| slot tool | `e2631-fwslot.c` (the host-native copy) compiles with `-Wall -Wextra -Werror`, then accepts a synthesized package and rejects the same package with one kernel byte changed. Its identity tests require both brand prefixes (`OpenWrt` and `ImmortalWrt`) to classify as ours, so a package from either era is not mistaken for the vendor system |
| slot layout | the kit copies (`tools/verify_img.mjs`, `host/release.mjs`, `scripts/preflight.sh`) and, after a bootstrap, the tree copies (board DTS, `target/linux/zx279128/image/Makefile`, device `e2631-preflight`) agree on KERNEL_AT `0x400000`, ROOTFS_SPAN `0x1100000` and HEADER_AT `0x1500000`; the retired `image/Makefile.e2631` must be gone. A stale `0x1400000` in any one of them is how a package gets built for the wrong header offset |
| U-Boot tools round-trip | `tests/test_mtd0_tools.mjs` builds a synthetic 1 MiB mtd0 (secondboot header, U-Boot header block + payload + 64-byte tail, erased gap, CRC32 env block) and proves the P2 tools round-trip it byte for byte: `tools/mkuboot-image.mjs` (unpack + build of the 0x20000..0xC0000 image area, payload limit 0x9F800), `tools/e2631-env.mjs` (env block parse/rebuild with the same CRC32 as the vendor image), `tools/patch-uboot.mjs` (only the 20-byte unsalted SHA1 digest at 0x61F80 moves; flag untouched), `tools/verify-mtd0.mjs` (sha256 and baseline diff with reported offsets). Purely offline. The real-dump acceptance (live mtd0 sha256 `de4ea5bd...`, both 2026-11-20 v2 dumps) runs by hand and is not required in CI |
| base pin | `scripts/pins.env` exists, carries every pin as a plain value, and matches the fork/branch/tip, the ImmortalWrt SHA, the base-port tree hash and the feed commits; the gate also fails if the scripts stop enforcing them. Runs on every `make check`, even before a tree exists |
| base tree hash | the tree at `E2631_TREE` is a depth-1 checkout of the pinned fork tip, and the scratch repo really contains the `6136bd92` base-port tree, the ImmortalWrt pin `a4ba8240` in its ancestry with its tree at `b905483c`, exactly four reviewed port commits above it, the 18-commit plan-C series (including the check-size fix), the renamed zx279128 paths and seed, and the two pinned feed HEADs. SKIPs until bootstrap has made a tree; never deepens the build tree |
| board dts | `#include`s and every `&label` in the board file resolve against the tree fork's zx279128 patch series (needs the tree, so it SKIPs before bootstrap) |
| first-flash preflight | the host copy of `e2631-preflight` accepts a synthesized valid package and refuses one with a single altered byte, offline (it needs the native `e2631-fwslot`) |
| `scripts/secret-scan.sh` | no credential shapes in any tracked file, and the evidence files that must stay ignored (the vendor harvest, the config export, the token helper) are not tracked. It exists because a scrub that searched for a value **literally** missed nine files that carry the tcl-escaped form of the same password |
| `scripts/notice-check.sh` | NOTICE and the tree agree in both directions: every path NOTICE names exists (tree paths use the `tree:` prefix), and every third-party file that must be listed (the mesh runtime tarball in the tree fork, the vendor version-header template here) is listed |

The two gates that read a finished artifact - `host/verify_pkg.mjs` (re-derives the
geometry independently) and `tools/verify_img.mjs` (boot readiness) - run inside the
pack step, so they need a build first.

Two more consistency checks run in `.github/workflows/check.yml` before `make check` (and can be
run by hand): `node host/sim-upgrade.mjs` simulates the online updater end to end with stub
`sysupgrade`/`uci`/`wget` (30 checks, no flash write), and `node tools/check-workflows.mjs`
asserts that the pin file, the tree-fork content (version string and updater, fetched at the
pinned SHA), the CI workflows, artifact names and release channel agree
(94 checks; the two newest assert the tree's image-pipeline expansion gate - the
parse-only dump that keeps `check-size 4096k` non-empty. It needs network access and
fails those fetches explicitly rather than skipping).

## 5. Bootstrap, then build

    make bootstrap        # depth-1 tree fork @ pin (history checked in a scratch repo) + feeds + seed
    make build            # make world, collect, pack, verify

`bootstrap` stops rather than guessing: it dies if the checkout ends up at another
commit, if the build tree is not depth 1, if the scratch history lacks the pinned
base-port tree or the four port commits, if a feed cannot be pinned, if an image hook
is missing, or if the seed's device selection does not survive `defconfig`.

`build` refuses to start a forty-minute job on inputs it can see are missing, so the
errors you get are the useful ones: no build tree, no `.config`, tree fork not checked
out, device not selected, no `node`, `node` too old for `zlib.crc32`, a template path
that does not exist (the default lives in `seed/`). It writes
`$E2631_OUT/build-<timestamp>/world.log`, then collects into the same directory
(`kernel`, `root`, `e2631.dtb`, `config-6.18`, `e2631-fwslot`) and packs
`$E2631_OUT/e2631-immortalwrt-<timestamp>.bin`.

Run it again to see the loop you will actually live in: bootstrap re-fetches the pin and
re-installs the feeds, then `make build` is a warm rebuild.

## 6. Flash it

Two routes, both used on real hardware. The upgrade package is the same file for both.

**A. The vendor web page** (verified 2026-10-14, this is the acceptance route). Boot the
box into the vendor system, log into its admin UI (it lives on `192.168.5.3`), open the
hidden firmware-upgrade page - the writeups call it `supgrade.html`, and its form POSTs
the multipart field `VersionUpload` to `/?_type=hiddenData&_tag=firmware_upgrade` on
port 8085 - select the package, submit. It writes the **inactive** slot, raises the slot
header's serial itself (33 -> 34 was measured) and reboots into the new system. The
vendor slot stays byte-identical, which is what makes route B possible afterwards.

**B. From the vendor system with our own tool.** `node host/stage.mjs put` copies
`e2631-fwslot` and the package onto the box over its telnet service and runs `info` +
`check` - read-only. `node host/stage.mjs flash --yes` then writes the inactive slot.
This needs the vendor telnet root password in `ZTE_TELNET_PW`; it is not in this
repository and `host/stage.mjs` refuses to run without it.

**Getting back.** From ImmortalWrt (or a legacy OpenWrt build): `e2631-fwslot switch` then `reboot` re-stamps the other
slot's header with a higher serial and nothing else - the vendor firmware body is never
touched. This also works from failsafe, because the tool only needs `/dev/mtd*` and the
slot partitions from the dtb. There is no `sysupgrade` path that overwrites the vendor
slot, by design.

**After first boot.** The image comes up with `br-lan` at `192.168.1.1/24` serving DHCP
(measured on the console: `lan1: Link is Up - 1Gbps/Full`, then `ssh root@192.168.1.1`,
LuCI on `http://192.168.1.1/`, Argon theme). The WAN port and the three LAN ports are
one WAN + `lan1 lan2 lan3`, all four on the SoC's internal PHYs.

## 7. When the build itself is the problem

The network is the constraint on most boxes, not the CPU. `wsl/build.sh` and README.md
document what was measured here: kernel.org 73 KB/s, `sources.cdn.openwrt.org`
25 KB/s, `sources.openwrt.org` 14 KB/s, `musl.libc.org` nothing at all inside a 12 s
probe - and the cap is per connection, not per host.

    E2631_SEGMENTED=1 make build     # fetch each distfile as 8-12 parallel byte ranges
    E2631_GNU_MIRROR=https://... make build
    E2631_PROXY=http://host:port make build

`wsl/segdl.sh` is the segmented fetcher, wired in through `DOWNLOAD_TOOL_CUSTOM` - the
only hook `scripts/download.pl` offers, because its `select_tool()` prefers curl and
never reaches aria2c. A 147 MiB kernel tarball came in at ~288 KB/s aggregate this way
and its sha256 matched the one in `download.pl`'s own command line, so the result is
byte-exact rather than merely fast. It falls back to a single connection for a server
that answers a range request with `200` and the whole file (`mirrors.huaweicloud.com`
does that), otherwise every worker would receive the same bytes.

`CURL_OPTIONS="--speed-limit 20000 --speed-time 20"` is set by default in
`scripts/build.sh`: OpenWrt gives curl a connect timeout but no transfer watchdog, so a
mirror that accepts the connection and sends nothing blocks forever instead of rotating.
A finished toolchain once sat five minutes on the 1 MiB musl tarball.

`make download` is deliberately not run up front: it walks every package in the tree,
selected or not, and was pulling `broadcom-wl` and `libwebsockets` while the packages
this image needs waited.

Windows side, if you build under WSL or edit from Windows: a **CRLF working copy breaks
kconfig** (`unknown statement "If"`), and a case-insensitive filesystem silently
collapses path pairs that differ only in case. Check files out with LF
(`.gitattributes` is set) and never compare a tree by directory names alone.

## 8. Making your own change

The port is the tree fork: `target/linux/zx279128/` (config fragments,
`image/Makefile` with the merged E2631 image recipe, the board DTS, `base-files/`),
`package/e2631/` (the slot tool,
the wifiap/wanport/LuCI packages, the mesh controller). Work in a full fork clone, commit,
push, bump `E2631_FORK_SHA` in `scripts/pins.env` after review, then `make bootstrap` -
the depth-1 build tree is disposable and must never be edited by hand. The build seed is
`seed/e2631.config` **inside the tree fork** - the kit no longer carries a copy (single-source
seed rule, T-20); `scripts/bootstrap.sh` appends only the P5 kernel build-identity lines.

Four rules that exist because breaking them cost hours:

* **Never hand-write a patch.** Generate it against the source the build actually uses:
  `wsl/gen-retrain-patch.sh`, `wsl/gen-efuse-patch.sh`. A hand-written patch here failed
  with "malformed patch at line 37"; the generators prove `APPLIED == GENERATED`.
* **The build tree is a pinned checkout, not a workspace.** A patch you carry in a fork
  commit is real; a file you edit in the depth-1 checkout disappears on the next bootstrap
  and never reaches a release. The same applied to the retired `apply.sh`: it copied, it
  did not sync, so a patch deleted from `overlay/` kept being applied - which is why the
  migration moved the port into commits instead.
* **Ask for a symbol where it is actually decided.** `target/linux/generic/config-6.18`
  wins over `target/linux/zx279128/config-6.18` for symbols generic names explicitly as
  "is not set" - that is why the lockup detectors are flipped in both files. The witness
  is the built kernel's own `.config` (`$E2631_OUT/build-*/config-6.18`), never a fragment.
* **A screen is not a boot.** Passing the bootloader's CRC gates only means the bytes are
  accepted. `tools/verify_img.mjs` checks the things that stop a boot instead: `root=`
  against the partition order the dtb really creates, flash/squashfs/decompressor built
  in, the forced command line beating the vendor bootargs, USB and watchdog staying
  disabled, soft-float, and the package list. Do not flash an artifact it refuses - a slot
  that hangs at startup does not fall back by itself.

`docs/architecture.md` maps the pieces and `docs/known-issues.md` is the machine-readable
honest list, including what is still broken on real hardware.


## 9. U-Boot payload budget (multifunction U-Boot)

The custom U-Boot eventually goes into the mtd0 image area 0x20000..0xC0000:
secondboot copies the payload from mtd0 0x20800 using the length field at header
+0x14, the payload area runs to 0xBFFFF, and the environment area starts at
0xC0000. The payload hard cap is therefore **0x9F800 = 653312 bytes (638 KiB)**.
A1/A2/A3 run it from RAM, where the cap does not apply, but the same binary must
fit mtd0 later, so CI enforces the budget up front.

Since E4, space is a first-class constraint: `uboot-build.yml` gates the payload
*before* the "Package the flashable mtd0 image" step. Two limits apply: the
E4 v3 budget keeps at least 240 KiB of headroom below the hard cap, and a
structural 8 KiB safety margin remains as the last line of defence.

| item | value |
|---|---|
| payload window | mtd0 `0x20800..0xBFFFF` (0x9F800) |
| hard cap | **653312 bytes (638 KiB)** |
| E4 v3 gate (`E2631_UBOOT_HARD_LIMIT` - `E2631_UBOOT_HEADROOM_MIN`) | **407,552 bytes** (653312 - 245,760 = 240 KiB headroom) |
| structural safety gate | **645120 bytes** (hard cap - 8192 bytes; last line of defence before mtd0 assembly) |
| E4 v3 baseline (`E2631_UBOOT_SIZE_BASELINE`) | 405,368 bytes (task-84 build, run 46109519805) |
| P1 reclaim (patch 0042) | 12,380 bytes (`CONFIG_CMD_FDT` 8229 + `CONFIG_CMD_TFTPBOOT` 4151) |
| v3 page growth | +11,131 bytes (page gzip 24904 vs the v1 13773 baseline) |
| P2 reclaim (patch 0051) | 11,520 bytes measured (`CONFIG_CMD_MII`; applied after the first unified v3 build measured 410,040 bytes) |
| current `u-boot.bin` (task-92 rebuild, run 46121809714) | **398,520 bytes**; 9,032 bytes below the E4 v3 gate, 6,848 bytes below the v3 baseline, 254,792 bytes (39.00%) below the hard cap |
| failure behaviour | above 407,552 bytes the build fails before mtd0 assembly and prints the observed size and the E4 v3 budget |

The budget ruling was exercised exactly once: the first unified v3 build
(410,040 bytes) tripped the 407,552-byte gate by 2,488 bytes, so the
pre-approved P2 (`CONFIG_CMD_MII`) was reclaimed in patch 0051 and the page
I18N was left untouched - I18N is preserved ahead of mii. The command set
follows the same ruling: bootm/MTD/DHCP/PING/OF_LIBFDT/LMB stay mandatory;
tftp/mii are conditional (patch 0042 drops fdt+tftp, patch 0051 drops mii,
and CI prints `command set: mii retained|reclaimed`).

Every successful build records a footprint table in the artifact's
`UBOOT-INFO.txt`: `u-boot.bin` bytes, mtd0 image bytes, the environment block
sha256, the `.config` sha256, the headroom against both the hard cap and the
E4 v3 gate, and the size delta against the v3 baseline.
`node tools/check-workflows.mjs` cross-checks the 8 KiB/645120 structural gate
and the 407552/245760 v3 gate against `uboot-port/README.md` and this table,
and asserts both gates run before mtd0 assembly.

Besides UBOOT-INFO.txt, every build ships `UBOOT-SIZES.txt`: the authoritative
per-object `.text` table (`arm-none-eabi-size` over all built objects plus the
linked-image total, sorted by `.text` descending). The pinned U-Boot baseline has
no `make sizes` target, so the CI step computes the same report from the build
objects. Use it to size E4 features (DHCP server, web UI): the current big
contributors are the EFI loader, MMC/FAT, bootflow/PXE and the command set.
`UBOOT-SIZES.txt` is covered by SHA256SUMS like every other artifact file.

Before adding a U-Boot feature, look at the `u-boot.bin` headroom: a patch that
would cross the gate must shrink something else first. Do not touch the 8 KiB
safety margin itself.
