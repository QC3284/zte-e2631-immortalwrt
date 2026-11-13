# shellcheck shell=sh
# Every machine-specific path in this kit, resolved in one place.
#
#   from the repo root:   . scripts/env.sh
#   from wsl/ or tools/:  . "$(dirname "$0")/../scripts/env.sh"
#
# Precedence is: an exported variable, then $E2631_KIT/.env (untracked; copy
# .env.example), then the default. The defaults are chosen so a plain clone works
# on an ordinary Linux box: the base tree lives in ~/openwrt and everything else
# is derived from where this repo actually lives rather than from a hardcoded
# path. Nothing here builds anything - it only answers "where", so a failure can
# name the path that was wrong instead of leaving a stranger to guess.

# Find the repo root: a directory holding both apply.sh and overlay/.
e2631_find_kit() {
	_e_d=$(cd "$(dirname "$1")" 2>/dev/null && pwd) || return 1
	while [ -n "$_e_d" ] && [ "$_e_d" != "/" ]; do
		if [ -f "$_e_d/apply.sh" ] && [ -d "$_e_d/overlay" ]; then echo "$_e_d"; return 0; fi
		_e_d=$(dirname "$_e_d")
	done
	return 1
}

if [ -z "${E2631_KIT:-}" ]; then
	for _c in "$(e2631_find_kit "${BASH_SOURCE:-$0}" 2>/dev/null)" "$(e2631_find_kit "$PWD" 2>/dev/null)"; do
		[ -n "$_c" ] || continue
		E2631_KIT=$_c
		break
	done
fi
if [ -z "${E2631_KIT:-}" ]; then
	echo "env.sh: cannot locate this repository (a directory holding apply.sh and overlay/)." >&2
	echo "        Set E2631_KIT to the directory you cloned the kit into, then re-run." >&2
	exit 1
fi

# $KIT/.env is the local, untracked config. It is read before the defaults so it
# can supply them. Only the keys listed in the case below are honoured, assigned
# literally - no eval, so a value containing $( ) or a semicolon stays a value.
if [ -f "$E2631_KIT/.env" ]; then
	while IFS= read -r _l || [ -n "$_l" ]; do
		_k=$(printf '%s' "$_l" | sed -n 's/^[[:blank:]]*\(E2631_[A-Z0-9_]*\)[[:blank:]]*=.*$/\1/p')
		[ -n "$_k" ] || continue
		_v=$(printf '%s' "$_l" | sed -n 's/^[^=]*=[[:blank:]]*\(.*\)$/\1/p' | sed 's/[[:blank:]]*$//; s/^["'"'"']\(.*\)["'"'"']$/\1/')
		case "$_k" in
		E2631_WORK) [ -n "${E2631_WORK:-}" ] || E2631_WORK=$_v ;;
		E2631_OUT) [ -n "${E2631_OUT:-}" ] || E2631_OUT=$_v ;;
		E2631_TREE) [ -n "${E2631_TREE:-}" ] || E2631_TREE=$_v ;;
		E2631_BASE_KIND) [ -n "${E2631_BASE_KIND:-}" ] || E2631_BASE_KIND=$_v ;;
		E2631_BASE_REPO) [ -n "${E2631_BASE_REPO:-}" ] || E2631_BASE_REPO=$_v ;;
		E2631_BASE_BRANCH) [ -n "${E2631_BASE_BRANCH:-}" ] || E2631_BASE_BRANCH=$_v ;;
		E2631_BASE_SHA) [ -n "${E2631_BASE_SHA:-}" ] || E2631_BASE_SHA=$_v ;;
		E2631_TEMPLATE) [ -n "${E2631_TEMPLATE:-}" ] || E2631_TEMPLATE=$_v ;;
		E2631_PROXY) [ -n "${E2631_PROXY:-}" ] || E2631_PROXY=$_v ;;
		esac
	done < "$E2631_KIT/.env"
fi

# The directory that holds out/ and the vendor template package. Default: the
# parent of the kit, which is where a sibling checkout naturally lives.
E2631_WORK=${E2631_WORK:-$(dirname "$E2631_KIT")}
E2631_OUT=${E2631_OUT:-$E2631_WORK/out}
# The base checkout the overlay gets applied to.
E2631_TREE=${E2631_TREE:-$HOME/openwrt}

# ---- which base tree -------------------------------------------------------
# Two bases are supported for one release cycle (docs/immortalwrt-migration.md
# 5.6, the rollback): "immortalwrt" is immortalwrt/immortalwrt at a pinned
# commit with the sanechips target port applied on top from base/*.patch (git
# am); "legacy" is the original OpenWrt sanechips mirror checkout this kit was
# written against. legacy is the DEFAULT until the ImmortalWrt chain passes
# end-to-end CI - it is the one-line rollback switch.
#
# base/commits.env is the pin file: the ImmortalWrt commit, the sha256 of every
# port patch, and the tree hash the series must produce. The immortalwrt branch
# reads those numbers, it does not repeat them; a change to a pin is a
# deliberate edit of that file, never a silent one.
E2631_BASE_KIND=${E2631_BASE_KIND:-legacy}
E2631_PORT_DIR=${E2631_PORT_DIR:-base}
if [ -f "$E2631_KIT/base/commits.env" ]; then
	. "$E2631_KIT/base/commits.env"
elif [ "$E2631_BASE_KIND" = immortalwrt ]; then
	echo "env.sh: E2631_BASE_KIND=immortalwrt needs the pin file $E2631_KIT/base/commits.env." >&2
	echo "        Restore it (git checkout -- base/), or set E2631_BASE_KIND=legacy." >&2
	exit 1
fi
case "$E2631_BASE_KIND" in
immortalwrt)
	# scripts/bootstrap.sh fetches exactly this commit and applies
	# base/0001..0004; E2631_BASE_TREE_SHA is the tree hash the result must
	# have, and both apply.sh and make check verify it.
	E2631_BASE_REPO=${E2631_BASE_REPO:-$E2631_IW_REPO}
	E2631_BASE_BRANCH=${E2631_BASE_BRANCH:-$E2631_IW_BRANCH}
	E2631_BASE_SHA=${E2631_BASE_SHA:-$E2631_IW_SHA}
	case "$E2631_BASE_REPO" in
	*openwrt-sanechips-mirror*)
		echo "env.sh: E2631_BASE_KIND=immortalwrt, but E2631_BASE_REPO is the legacy sanechips mirror." >&2
		echo "        Unset E2631_BASE_REPO (and the E2631_BASE_* lines in .env) to use the pin." >&2
		exit 1
		;;
	esac
	;;
legacy)
	# The commit is the whole base: no patch series, no tree-hash check.
	E2631_BASE_REPO=${E2631_BASE_REPO:-https://github.com/Zlion-Y/openwrt-sanechips-mirror}
	E2631_BASE_BRANCH=${E2631_BASE_BRANCH:-pr-zte-zxhn-h3600}
	E2631_BASE_SHA=${E2631_BASE_SHA:-db8b8d4130457dbe46558a7cea872dd2dae539e6}
	E2631_BASE_TREE_SHA=
	;;
*)
	echo "env.sh: E2631_BASE_KIND=$E2631_BASE_KIND is not one of: immortalwrt legacy" >&2
	exit 1
	;;
esac
# The version-header template. Default is the 532-byte header slice shipped here
# (seed/vendor-verhdr-8b8.bin): packing only reads the 512-byte version header, so a
# full vendor package is optional. Point this at an official .bin you own to run
# mkfactory's selftest/info, or to re-check the slice against the real thing.
E2631_TEMPLATE=${E2631_TEMPLATE:-$E2631_KIT/seed/vendor-verhdr-8b8.bin}
# Scripts that drop a log under out/ should not have to create it, and a fresh clone has
# no out/ yet. Failing to create it is not fatal: the read-only tools need no scratch dir.
[ -d "$E2631_OUT" ] || mkdir -p "$E2631_OUT" 2>/dev/null || true
export E2631_KIT E2631_WORK E2631_OUT E2631_TREE E2631_BASE_KIND E2631_PORT_DIR \
	E2631_BASE_REPO E2631_BASE_BRANCH E2631_BASE_SHA E2631_BASE_TREE_SHA E2631_TEMPLATE
# Pin provenance from base/commits.env, exported for CI/SOURCE-INFO consumers.
# (export of an unset name is fine under set -u; legacy without base/ still works.)
export E2631_IW_REPO E2631_IW_BRANCH E2631_IW_SHA E2631_IW_TREE_SHA \
	E2631_BASE_KERNEL E2631_PORT_REPO E2631_PORT_BRANCH E2631_PORT_SHA \
	E2631_PORT_BASE_SHA \
	E2631_BASE_PATCH_SHA256_0001 E2631_BASE_PATCH_SHA256_0002 \
	E2631_BASE_PATCH_SHA256_0003 E2631_BASE_PATCH_SHA256_0004

e2631_need_cmd() {	# e2631_need_cmd <command> <what it is needed for>
	command -v "$1" >/dev/null 2>&1 && return 0
	echo "env.sh: no $1 on PATH - $2" >&2
	echo "        Debian/Ubuntu: sudo apt-get install $( [ "$1" = node ] && echo nodejs || echo "$1" )" >&2
	return 1
}

e2631_need_file() {	# e2631_need_file <path> <what it is> <how to get it>
	[ -f "$1" ] && return 0
	echo "missing $1 ($2)" >&2
	echo "        $3" >&2
	return 1
}
