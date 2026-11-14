#!/bin/bash
# Gate: the base is PINNED, not "whatever master is today" (T1 §5.1, T4 base-pin).
#
# Phase 2 (tree fork): the sanechips port and the e2631 device support are real
# commits in our ImmortalWrt fork (QC3284/immortalwrt, branch e2631). The pin is
# content, not a branch pointer:
#   - the fork branch tip the kit clones (E2631_FORK_SHA);
#   - the base-port tree the four sanechips commits produce
#     (E2631_BASE_TREE_SHA) - it must still be in the fork's fetched history;
#   - the upstream ImmortalWrt commit those four commits sit on (E2631_IW_SHA) -
#     it must be an ancestor, and the series above it must still count four
#     commits, so a rebase onto another base cannot pass silently.
#
# scripts/bootstrap.sh checks the same three things while it builds; this gate
# makes them part of "make check", so the pin cannot silently rot between two
# bootstraps (and a deleted pin file cannot turn into a SKIP).
#
# Pre-bootstrap (no tree yet): pin file + patch hashes + enforcement greps.
# Post-bootstrap: the tree must be the fork tip, the port tree must be in its
# history, the port series must be four commits, and the device files must exist
# (the overlay is committed in the tree fork now, not laid down by apply.sh).
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
     E2631_BASE_TREE_SHA E2631_FORK_REPO E2631_FORK_BRANCH E2631_FORK_SHA
     E2631_FEED_PACKAGES_SHA E2631_FEED_LUCI_SHA"
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
fork_sha=$(get E2631_FORK_SHA)
base_tree=$(get E2631_BASE_TREE_SHA)
kernel=$(get E2631_BASE_KERNEL)
note "immortalwrt pin" "$iw_sha ($(get E2631_IW_BRANCH), kernel $kernel)"
note "tree fork tip" "$fork_sha ($E2631_FORK_BRANCH on $E2631_FORK_REPO)"
note "base-port tree pin" "$base_tree"
note "feed pins" "packages $(printf '%.12s' "$(get E2631_FEED_PACKAGES_SHA)"), luci $(printf '%.12s' "$(get E2631_FEED_LUCI_SHA)") (v1.10.0 reference, P3)"

# ---- 2. the four patches are the reviewed bytes ----------------------------
# The tree fork does not re-apply them, but they stay the provenance record (and
# the legacy rollback path) until task-12 moves the pin out of base/.
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
grep -qF 'E2631_FORK_SHA' scripts/env.sh 2>/dev/null ||
	bad "scripts/env.sh does not expose E2631_FORK_SHA (the tree-fork tip)"
grep -qF 'E2631_BASE_TREE_SHA' scripts/env.sh 2>/dev/null ||
	bad "scripts/env.sh does not expose E2631_BASE_TREE_SHA"
grep -qF 'E2631_BASE_KIND' scripts/env.sh 2>/dev/null ||
	bad "scripts/env.sh does not expose E2631_BASE_KIND (legacy|immortalwrt rollback switch)"
if [ -f scripts/bootstrap.sh ]; then
	grep -qF 'E2631_FORK_SHA' scripts/bootstrap.sh ||
		bad "scripts/bootstrap.sh does not pin the tree-fork tip"
	grep -qF 'E2631_BASE_TREE_SHA' scripts/bootstrap.sh ||
		bad "scripts/bootstrap.sh does not assert the base-port tree pin"
	grep -qF 'E2631_IW_SHA' scripts/bootstrap.sh ||
		bad "scripts/bootstrap.sh does not check the upstream pin ancestry"
	grep -qF 'HEAD^{tree}' scripts/bootstrap.sh ||
		bad "scripts/bootstrap.sh does not read HEAD^{tree} - the tree assertion is gone"
	if grep -qF 'git am' scripts/bootstrap.sh; then
		bad "scripts/bootstrap.sh still git-am's the vendored series - the tree fork is the base now"
	fi
	grep -qF 'E2631_FEED_PACKAGES_SHA' scripts/bootstrap.sh ||
		bad "scripts/bootstrap.sh does not clone the pinned packages feed commit (P3)"
	grep -qF 'E2631_FEED_LUCI_SHA' scripts/bootstrap.sh ||
		bad "scripts/bootstrap.sh does not clone the pinned luci feed commit (P3)"
fi

if [ "$MODE" = static ]; then
	[ $rc -eq 0 ] || exit 1
	echo "base-pin: iw $iw_sha + tree fork $fork_sha + 4 patch sha256 verified (tree content checked when a tree exists)"
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
got_head=$(git -C "$E2631_TREE" rev-parse HEAD 2>/dev/null) || got_head=""
if [ -z "$got_head" ]; then
	bad "$E2631_TREE: cannot read HEAD - is it a git checkout?"
elif [ "$got_head" != "$fork_sha" ]; then
	bad "$E2631_TREE: HEAD=$got_head, the pin records the tree-fork tip $fork_sha"
	echo "     re-run scripts/bootstrap.sh - a patch-series tree is no longer the base"
else
	note "tree fork tip" "HEAD ok ($(printf '%.12s' "$got_head")...)"
fi
# The build tree is a depth-1 checkout on purpose (parity P2): COMMITCOUNT is
# git rev-list --count HEAD ., so a deeper build tree changes base-files
# PKG_RELEASE and the image stops matching the released v1.10.0.
if [ -n "$got_head" ]; then
	if [ -f "$E2631_TREE/.git/shallow" ] &&
		[ "$(git -C "$E2631_TREE" rev-list --count HEAD 2>/dev/null)" = 1 ]; then
		note "build tree depth" "1 commit (COMMITCOUNT stays 1, parity P2)"
	else
		bad "$E2631_TREE: the build tree is not a depth-1 checkout - the parity build needs exactly one commit (P2)"
	fi
fi

# The history assertions run in a scratch repo, NEVER in the depth-1 build
# tree: deepening the build tree would change the build itself.
hist=""
if [ -n "${E2631_WORK:-}" ] && [ -d "$E2631_WORK/.e2631-fork-history/.git" ] &&
	[ "$(git -C "$E2631_WORK/.e2631-fork-history" rev-parse FETCH_HEAD 2>/dev/null)" = "$fork_sha" ]; then
	hist="$E2631_WORK/.e2631-fork-history"
	note "fork history" "reusing $hist (depth $E2631_FORK_DEPTH)"
else
	hist=$(mktemp -d)
	trap 'rm -rf "$hist"' EXIT
	git -C "$hist" init -q &&
		git -C "$hist" remote add origin "$E2631_FORK_REPO" &&
		git -C "$hist" fetch -q --depth "$E2631_FORK_DEPTH" origin "$fork_sha" ||
		bad "cannot fetch $fork_sha from $E2631_FORK_REPO into a scratch history repo"
	if [ "$(git -C "$hist" rev-parse FETCH_HEAD 2>/dev/null)" != "$fork_sha" ]; then
		bad "scratch history repo did not get the pinned fork tip $fork_sha"
	fi
	note "fork history" "fetched into $hist (depth $E2631_FORK_DEPTH)"
fi
# The base-port tree must still be in the fork history: a rebase keeps the
# commits but not necessarily the tree, so this is the content identity.
if [ -n "$hist" ] && git -C "$hist" log --format=%T FETCH_HEAD 2>/dev/null | grep -qx "$base_tree"; then
	note "base-port tree" "in the fork history"
else
	bad "no commit with tree $base_tree in the fetched fork history - not the reviewed base-port tree"
fi
if [ -n "$hist" ] && git -C "$hist" cat-file -e "$iw_sha^{commit}" 2>/dev/null; then
	if git -C "$hist" merge-base --is-ancestor "$iw_sha" FETCH_HEAD; then
		port_head=$(git -C "$hist" log --format='%H %T' FETCH_HEAD 2>/dev/null |
			awk -v t="$base_tree" '$2 == t { print $1; exit }')
		port_steps=$(git -C "$hist" rev-list --count "$iw_sha..$port_head" 2>/dev/null) ||
			port_steps=unknown
		if [ "$port_steps" = 4 ]; then
			note "port series" "4 commits above the upstream pin"
		else
			bad "the port series is $port_steps commits above $iw_sha, expected the four reviewed commits"
		fi
	else
		bad "the fork tip is not descended from the pinned ImmortalWrt commit $iw_sha"
	fi
else
	bad "$iw_sha is outside the fetched history window - raise E2631_FORK_DEPTH (currently ${E2631_FORK_DEPTH:-unset}) and re-bootstrap"
fi
# Device support is committed now: the files must be in the tree, not implied.
for p in target/linux/sanechips/base-files/etc/config/wireless \
	 target/linux/sanechips/image/Makefile.e2631; do
	if git -C "$E2631_TREE" ls-tree -r --name-only HEAD -- "$p" | grep -qx "$p"; then
		note "$(basename "$p")" "present in the tree"
	else
		bad "$E2631_TREE: $p is missing - the e2631 commit set is incomplete"
	fi
done
git -C "$E2631_TREE" ls-tree -r --name-only HEAD -- package/e2631 | grep -q '/Makefile$' ||
	bad "$E2631_TREE: package/e2631/*/Makefile is missing - the e2631 packages are missing"
# The kernel line is the other half of the pin: 6.18.60, not "some 6.18".
kf="$E2631_TREE/target/linux/generic/kernel-6.18"
if [ -f "$kf" ] && [ -n "$kernel" ]; then
	want="${kernel#6.18}"	# kernel is 6.18.60 -> ".60", the suffix kernel-6.18 carries
	if grep -q "^LINUX_VERSION-6.18 = ${want}$" "$kf"; then
		note "kernel-6.18 line" "LINUX_VERSION-6.18 = ${kernel#6.18}"
	else
		bad "$kf: LINUX_VERSION-6.18 is not ${want} - the tree is not the pinned $kernel"
	fi
fi

# P3: the feeds must be at the pinned commits, not the branch tip of the day.
for f in packages luci; do
	case "$f" in
	packages) pin=$(get E2631_FEED_PACKAGES_SHA) ;;
	luci) pin=$(get E2631_FEED_LUCI_SHA) ;;
	esac
	d="$E2631_TREE/feeds/$f"
	if [ -d "$d/.git" ]; then
		got=$(git -C "$d" rev-parse HEAD 2>/dev/null) || got=""
		if [ "$got" = "$pin" ]; then
			note "$f feed" "pinned commit ok ($(printf '%.12s' "$pin")...)"
		else
			bad "$d: HEAD=${got:-<unreadable>}, the P3 pin records $pin"
		fi
	else
		note "$f feed" "not cloned yet - bootstrap pins it to $(printf '%.12s' "$pin")"
	fi
done

[ $rc -eq 0 ] && echo "base-pin: iw $iw_sha + tree fork $fork_sha + base-port tree $base_tree + 4 commits + feed pins verified"
exit $rc
