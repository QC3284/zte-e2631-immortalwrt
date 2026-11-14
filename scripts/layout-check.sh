#!/bin/bash
# Gate: one slot geometry across every file that consumes it (T1 §4.5, T4 g_layout).
#
# The values, and why they are not free choices:
#   KERNEL_AT    0x400000   cspboot derives the rootfs position as
#                           slot + ceil(declared kernel size / erase size) and
#                           ignores the version header's own rootfs offset, so
#                           the packer declares the whole kernel region. Any
#                           other value moves the rootfs out from under the
#                           board DTS partition table.
#   ROOTFS_SPAN  0x1100000  17 MiB rootfs window: squashfs plus the writable
#                           rootfs_data the kernel splits off its tail. The
#                           window must end before the version header block,
#                           because the bootloader's rootfs checksum covers the
#                           declared extent (a config save over a covered tail
#                           destroys the slot - measured on hardware).
#   HEADER_AT    0x1500000  the 512-byte vendor version header block starts
#                           right after the window, outside the overlay.
#
# T-12: the port moved into the tree fork (QC3284/immortalwrt branch e2631).
# The kit still owns the image content test (tools/verify_img.mjs), the packer
# defaults (host/release.mjs) and the host first-flash preflight
# (scripts/preflight.sh); the tree owns the board DTS, the image rule
# (Makefile.e2631) and the device preflight copy. Pre-bootstrap only the kit
# copies exist and are checked; post-bootstrap the tree copies are checked too,
# so drift between the two repos cannot pass silently. Comments and prose are
# not parsed: only the values the code actually uses are.
#
#   bash scripts/layout-check.sh        # one of the gates in scripts/check.sh
set -u
cd "$(dirname "$0")/.." || exit 1
. scripts/env.sh

WANT_KERNEL=$((0x400000))
WANT_SPAN=$((0x1100000))
WANT_HEADER=$((WANT_KERNEL + WANT_SPAN))
rc=0
bad()  { echo "FAIL $*"; rc=1; }
note() { printf '  %-18s %s\n' "$1" "$2"; }
hx()   { printf '0x%x' "$1"; }

# ---- kit copies (always present) ------------------------------------------
# The image content test (verify_img.mjs): KERNEL_AT / ROOTFS_SPAN constants and
# the derived HEADER_AT.
VI=tools/verify_img.mjs
read -r vi_k vi_r <<EOF2
$(sed -n 's/.*const KERNEL_AT = \(0x[0-9a-fA-F]*\), ROOTFS_SPAN = \(0x[0-9a-fA-F]*\).*/\1 \2/p' "$VI" | head -1)
EOF2
if [ -z "${vi_k:-}" ] || [ -z "${vi_r:-}" ]; then
	bad "$VI: could not read 'const KERNEL_AT = ..., ROOTFS_SPAN = ...'"
else
	[ "$((vi_k))" -eq "$WANT_KERNEL" ] || bad "$VI: KERNEL_AT=$vi_k, expected $(hx "$WANT_KERNEL")"
	[ "$((vi_r))" -eq "$WANT_SPAN" ] || bad "$VI: ROOTFS_SPAN=$vi_r, expected $(hx "$WANT_SPAN")"
	grep -q 'HEADER_AT = KERNEL_AT + ROOTFS_SPAN' "$VI" ||
		bad "$VI: HEADER_AT must stay derived as KERNEL_AT + ROOTFS_SPAN"
	note "$VI" "KERNEL_AT=$(hx "$((vi_k))") ROOTFS_SPAN=$(hx "$((vi_r))") HEADER_AT=derived"
fi

# The packer defaults (release.mjs).
RM=host/release.mjs
rm_r=$(sed -n "s/.*const ROOTFS_AT = arg('--rootfs-at', '\(0x[0-9a-fA-F]*\)').*/\1/p" "$RM" | head -1)
rm_h=$(sed -n "s/.*const HEADER_AT = arg('--header-at', '\(0x[0-9a-fA-F]*\)').*/\1/p" "$RM" | head -1)
if [ -z "${rm_r:-}" ] || [ -z "${rm_h:-}" ]; then
	bad "$RM: could not read the --rootfs-at / --header-at defaults"
else
	[ "$((rm_r))" -eq "$WANT_KERNEL" ] || bad "$RM: --rootfs-at default $rm_r, expected $(hx "$WANT_KERNEL")"
	[ "$((rm_h))" -eq "$WANT_HEADER" ] || bad "$RM: --header-at default $rm_h, expected $(hx "$WANT_HEADER")"
	note "$RM" "--rootfs-at=$(hx "$((rm_r))") --header-at=$(hx "$((rm_h))")"
fi

# The host first-flash preflight (kit copy).
check_preflight() {	# check_preflight <path> <label>
	local PF=$1 pf_k pf_r pf_h
	pf_k=$(sed -n 's/^E2631_KERNEL_AT=\(0x[0-9a-fA-F]*\).*/\1/p' "$PF" | head -1)
	pf_r=$(sed -n 's/^E2631_ROOTFS_SPAN=\(0x[0-9a-fA-F]*\).*/\1/p' "$PF" | head -1)
	pf_h=$(sed -n 's/^E2631_HEADER_AT=\(0x[0-9a-fA-F]*\).*/\1/p' "$PF" | head -1)
	if [ -z "${pf_k:-}" ] || [ -z "${pf_r:-}" ] || [ -z "${pf_h:-}" ]; then
		bad "$PF: missing E2631_KERNEL_AT / E2631_ROOTFS_SPAN / E2631_HEADER_AT (plain literals)"
		return
	fi
	[ "$((pf_k))" -eq "$WANT_KERNEL" ] || bad "$PF: E2631_KERNEL_AT=$pf_k, expected $(hx "$WANT_KERNEL")"
	[ "$((pf_r))" -eq "$WANT_SPAN" ] || bad "$PF: E2631_ROOTFS_SPAN=$pf_r, expected $(hx "$WANT_SPAN")"
	[ "$((pf_h))" -eq "$WANT_HEADER" ] || bad "$PF: E2631_HEADER_AT=$pf_h, expected $(hx "$WANT_HEADER")"
	note "$2" "KERNEL_AT=$(hx "$((pf_k))") ROOTFS_SPAN=$(hx "$((pf_r))") HEADER_AT=$(hx "$((pf_h))")"
}
check_preflight scripts/preflight.sh scripts/preflight.sh

# ---- tree copies (post-bootstrap) -----------------------------------------
TREE_DIR="${E2631_TREE:-}/target/linux/sanechips"
if [ ! -d "$TREE_DIR" ]; then
	echo "SKIP tree geometry copies: no tree fork at ${E2631_TREE:-<unset>} - run scripts/bootstrap.sh, then re-run this gate"
	[ $rc -eq 0 ] && echo "layout-check: kit copies agree on $(hx "$WANT_KERNEL") / $(hx "$WANT_SPAN") / $(hx "$WANT_HEADER") (tree copies checked after a bootstrap)"
	exit $rc
fi

# The board DTS: the only description of what the running kernel creates.
DTS="$TREE_DIR/dts/zx279128s-zte-zxhn-e2631.dts"
[ -f "$DTS" ] || { echo "FAIL missing board DTS: $DTS"; exit 1; }

dts_prop1() {	# dts_prop1 <property> -> the first cell, hex
	sed -n "s/.*$1 = <0x\([0-9a-fA-F]*\).*/0x\1/p" "$DTS" | head -1
}
dts_prop2() {	# dts_prop2 <property> -> "cell0 cell1", hex
	sed -n "s/.*$1 = <0x\([0-9a-fA-F]*\) 0x\([0-9a-fA-F]*\)>.*/0x\1 0x\2/p" "$DTS" | head -1
}
dts_reg() {	# dts_reg <label> -> "addr size" of the first reg in that partition
	awk -v l="\"$1\"" 'index($0, "label = " l ";") { f = 1 }
		f && /reg = </ { print; exit }' "$DTS" |
		sed -n 's/.*reg = <0x\([0-9a-fA-F]*\) 0x\([0-9a-fA-F]*\)>.*/0x\1 0x\2/p'
}

read -r s1_base s1_span <<EOF2
$(dts_prop2 'zte,slot1')
EOF2
hdr_delta=$(dts_prop1 'zte,hdr-delta')
read -r n1_base n1_span <<EOF2
$(dts_reg slot1)
EOF2
read -r r_addr r_size <<EOF2
$(dts_reg rootfs)
EOF2
read -r h_addr h_size <<EOF2
$(dts_reg slot1-header)
EOF2

if [ -z "$hdr_delta" ] || [ -z "$s1_base" ] || [ -z "$s1_span" ] ||
   [ -z "$n1_base" ] || [ -z "$n1_span" ] || [ -z "$r_addr" ] || [ -z "$r_size" ] ||
   [ -z "$h_addr" ] || [ -z "$h_size" ]; then
	echo "FAIL $DTS: could not read zte,slot1 / zte,hdr-delta / the slot1, rootfs, slot1-header partitions"
	echo "     (the parser expects the labels and the two-cell reg form this gate was written for)"
	exit 1
fi

s1_base=$((s1_base)); s1_span=$((s1_span)); n1_base=$((n1_base)); n1_span=$((n1_span))
r_addr=$((r_addr)); r_size=$((r_size)); h_addr=$((h_addr)); h_size=$((h_size))
dts_k=$((r_addr - s1_base))
dts_h=$((h_addr - s1_base))
[ "$s1_base" -eq "$n1_base" ] && [ "$s1_span" -eq "$n1_span" ] ||
	bad "$DTS: zte,slot1 = <$(hx "$s1_base") $(hx "$s1_span")> but partition slot1 is <$(hx "$n1_base") $(hx "$n1_span")>"
[ "$dts_k" -eq "$WANT_KERNEL" ] ||
	bad "$DTS: rootfs starts at slot+$(hx "$dts_k"), expected $(hx "$WANT_KERNEL")"
[ "$r_size" -eq "$WANT_SPAN" ] ||
	bad "$DTS: rootfs window is $(hx "$r_size"), expected $(hx "$WANT_SPAN")"
[ "$((hdr_delta))" -eq "$dts_h" ] ||
	bad "$DTS: zte,hdr-delta=$(hx "$((hdr_delta))") but the slot1-header partition sits at slot+$(hx "$dts_h")"
[ "$dts_h" -eq "$WANT_HEADER" ] ||
	bad "$DTS: slot1-header at slot+$(hx "$dts_h"), expected $(hx "$WANT_HEADER")"
[ "$h_size" -eq $((0x20000)) ] ||
	bad "$DTS: slot1-header block is $(hx "$h_size"), expected 0x20000 (one erase block)"
note "board DTS" "slot1@$(hx "$s1_base")+$(hx "$s1_span") rootfs@+$(hx "$dts_k")[$(hx "$r_size")] header@+$(hx "$dts_h")[$(hx "$h_size")]"

# The image rule that calls the packer (tree Makefile.e2631).
MK="$TREE_DIR/image/Makefile.e2631"
read -r mk_r mk_h <<EOF2
$(sed -n 's/.*--rootfs-at \(0x[0-9a-fA-F]*\) --header-at \(0x[0-9a-fA-F]*\).*/\1 \2/p' "$MK" | head -1)
EOF2
if [ -z "${mk_r:-}" ] || [ -z "${mk_h:-}" ]; then
	bad "$MK: could not read the packer call's --rootfs-at / --header-at"
else
	[ "$((mk_r))" -eq "$WANT_KERNEL" ] || bad "$MK: packer --rootfs-at $mk_r, expected $(hx "$WANT_KERNEL")"
	[ "$((mk_h))" -eq "$WANT_HEADER" ] || bad "$MK: packer --header-at $mk_h, expected $(hx "$WANT_HEADER")"
	note "Makefile.e2631" "--rootfs-at=$(hx "$((mk_r))") --header-at=$(hx "$((mk_h))")"
fi

# The device first-flash preflight copy in the tree.
check_preflight "$TREE_DIR/base-files/sbin/e2631-preflight" "tree preflight"

if [ $rc -eq 0 ]; then
	echo "layout-check: $(hx "$WANT_KERNEL") / $(hx "$WANT_SPAN") / $(hx "$WANT_HEADER") agree in every copy (kit + tree)"
fi
exit $rc
