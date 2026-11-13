#!/bin/bash
# Gate: the base is PINNED, not "whatever master is today" (T1 §5.1, T4 base-pin).
#
# The port is an overlay on a triple pin:
#   - the ImmortalWrt commit the overlay is written against (E2631_IW_SHA);
#   - the four vendored sanechips-port patches, byte-identical to what was
#     reviewed (E2631_BASE_PATCH_SHA256_000N);
#   - the tree those commits produce after "git am" (E2631_BASE_TREE_SHA) -
#     the only stable identity, because the am'd commits get new hashes.
#
# scripts/bootstrap.sh checks the tree hash while it builds; this gate makes
# the same assertion part of "make check", so the pin cannot silently rot
# between two bootstraps (and a deleted base/ dir cannot turn into a SKIP).
#
# Pre-bootstrap (no tree yet): patches + recorded hashes.
# Post-bootstrap: HEAD^{tree} of the tree must equal E2631_BASE_TREE_SHA.
# apply.sh only dirties the worktree (copies and edits, no commits), so the
# committed tree hash is exactly the base pin even after the overlay is laid
# down - measured with base-builder on the real trees.
#
#   bash scripts/base-pin-check.sh       # one of the gates in scripts/check.sh
set -u
MODE=${1:-all}
case "$MODE" in static|tree|all) ;; *) echo "usage: $0 [static|tree|all]" >&2; exit 2 ;; esac
cd "$(dirname "$0")/.." || exit 1
. scripts/env.sh

BASE=base
ENVF=$BASE/commits.env
rc=0
bad() { echo "FAIL $*"; rc=1; }
note() { printf '  %-22s %s\n' "$1" "$2"; }
get() { sed -n "s/^$1=//p" "$ENVF" | tail -1; }

if [ ! -f "$ENVF" ]; then
	if [ -n "$(git log --format=%h -- "$ENVF" 2>/dev/null | head -1)" ]; then
		echo "FAIL $ENVF is in git history but missing from the worktree"
		echo "     the base is pinned by that file; restore it, do not drop the pin"
		exit 1
	fi
	echo "no $ENVF yet - T2 lands base/ and this gate covers it from then on"
	exit 77
fi

# ---- 1. the recorded pin is complete and well-formed -----------------------
req="E2631_IW_REPO E2631_IW_BRANCH E2631_IW_SHA E2631_IW_TREE_SHA E2631_BASE_KERNEL
     E2631_PORT_REPO E2631_PORT_BRANCH E2631_PORT_SHA E2631_PORT_BASE_SHA
     E2631_BASE_TREE_SHA"
for k in $req; do
	v=$(get "$k")
	if [ -z "$v" ]; then
		bad "$ENVF: $k is missing"
		continue
	fi
	case "$k" in
	*_SHA|*_TREE_SHA|*_BASE_SHA)
		case "$v" in
		*[!0-9a-f]*) bad "$ENVF: $k is not a lowercase hex object id: $v" ;;
		*) [ ${#v} -eq 40 ] || bad "$ENVF: $k is not 40 hex chars: $v" ;;
		esac ;;
	esac
done
iw_sha=$(get E2631_IW_SHA)
base_tree=$(get E2631_BASE_TREE_SHA)
kernel=$(get E2631_BASE_KERNEL)
note "immortalwrt pin" "$iw_sha ($(get E2631_IW_BRANCH), kernel $kernel)"
note "base tree pin" "$base_tree"

# ---- 2. the four patches are the reviewed bytes ----------------------------
shopt -s nullglob
patches=("$BASE"/000[1-4]-*.patch)
shopt -u nullglob
if [ ${#patches[@]} -ne 4 ]; then
	bad "$BASE: expected the four 0001..0004-*.patch files, found ${#patches[@]}"
else
	n=0
	for p in "${patches[@]}"; do
		n=$((n + 1))
		rec=$(get "$(printf 'E2631_BASE_PATCH_SHA256_%04d' "$n")")
		got=$(sha256sum "$p" | cut -d' ' -f1)
		if [ -z "$rec" ]; then
			bad "$ENVF: no E2631_BASE_PATCH_SHA256_$(printf '%04d' "$n") for $p"
		elif [ "$got" != "$rec" ]; then
			bad "$p: sha256 $got, the pin records $rec"
			echo "     the patch was edited or re-generated; re-review it, then update the pin"
		else
			note "$(basename "$p")" "sha256 ok ($(printf '%.12s' "$got")...)"
		fi
	done
fi

# ---- 3. the pin is actually enforced where it is used ---------------------
grep -qF 'base/commits.env' scripts/env.sh 2>/dev/null ||
	bad "scripts/env.sh does not source base/commits.env - the pin would be decorative"
grep -qF 'E2631_BASE_TREE_SHA' scripts/env.sh 2>/dev/null ||
	bad "scripts/env.sh does not expose E2631_BASE_TREE_SHA"
grep -qF 'E2631_BASE_KIND' scripts/env.sh 2>/dev/null ||
	bad "scripts/env.sh does not expose E2631_BASE_KIND (legacy|immortalwrt rollback switch)"
if [ -f scripts/bootstrap.sh ]; then
	grep -qF 'E2631_BASE_TREE_SHA' scripts/bootstrap.sh ||
		bad "scripts/bootstrap.sh does not assert the tree hash after git am"
	grep -qF 'HEAD^{tree}' scripts/bootstrap.sh ||
		bad "scripts/bootstrap.sh does not read HEAD^{tree} - the tree-hash assertion is gone"
	grep -qF 'git am' scripts/bootstrap.sh ||
		bad "scripts/bootstrap.sh does not git am the vendored base patches"
fi

if [ "$MODE" = static ]; then
	[ $rc -eq 0 ] || exit 1
	echo "base-pin: iw $iw_sha + 4 patch sha256 verified (tree hash: checked when a tree exists)"
	exit 0
fi

# ---- 4. the tree on this machine, when there is one ------------------------
kind="${E2631_BASE_KIND:-legacy}"
if [ "$kind" = legacy ]; then
	echo "SKIP base tree pin: E2631_BASE_KIND=legacy (rollback window); the pin applies to the immortalwrt base"
	[ $rc -eq 0 ] || exit 1
	exit 77
fi
if [ ! -d "${E2631_TREE:-}/.git" ]; then
	echo "SKIP base tree pin: no base tree at ${E2631_TREE:-<unset>} - run scripts/bootstrap.sh, then re-run this gate"
	[ $rc -eq 0 ] || exit 1
	exit 77
fi
got_tree=$(git -C "$E2631_TREE" rev-parse 'HEAD^{tree}' 2>/dev/null) || got_tree=""
if [ -z "$got_tree" ]; then
	bad "$E2631_TREE: cannot read HEAD^{tree} - is it a git checkout?"
elif [ "$got_tree" != "$base_tree" ]; then
	bad "$E2631_TREE: HEAD^{tree}=$got_tree, the pin records $base_tree"
	echo "     the tree is NOT the reviewed base: re-run scripts/bootstrap.sh (it refuses a wrong tree)"
else
	note "tree at E2631_TREE" "HEAD^{tree} ok ($(printf '%.12s' "$got_tree")...)"
fi
# The kernel line is the other half of the pin: 6.18.60, not "some 6.18".
kf="$E2631_TREE/target/linux/generic/kernel-6.18"
if [ -f "$kf" ] && [ -n "$kernel" ]; then
	want="${kernel#6.18}"	# kernel is 6.18.60 -> ".60", the suffix kernel-6.18 carries
	if grep -q "^LINUX_VERSION-6.18 = ${want}$" "$kf"; then
		note "kernel-6.18 line" "LINUX_VERSION-6.18 = ${kernel#6.18}$(printf '')"
	else
		bad "$kf: LINUX_VERSION-6.18 is not ${want} - the tree is not the pinned $kernel"
	fi
fi

[ $rc -eq 0 ] && echo "base-pin: iw $iw_sha + 4 patches + tree $base_tree verified"
exit $rc
