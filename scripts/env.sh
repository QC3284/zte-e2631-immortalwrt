# shellcheck shell=sh
# Every machine-specific path in this kit, resolved in one place.
#
#   from the repo root:   . scripts/env.sh
#   from wsl/ or tools/:  . "$(dirname "$0")/../scripts/env.sh"
#
# Precedence is: an exported variable, then $E2631_KIT/.env (untracked; copy
# .env.example), then the default. The defaults are chosen so a plain clone works
# on an ordinary Linux box: the pinned tree fork lives in ~/openwrt and everything
# else is derived from where this repo actually lives rather than from a
# hardcoded path. Nothing here builds anything - it only answers "where" and
# "which pin", so a failure can name the path that was wrong instead of leaving
# a stranger to guess.
#
# T-12 (2026-11-14): the kit is packaging/release/CI only. The E2631 port itself
# - overlay/, the base patch series, apply.sh - moved into QC3284/immortalwrt
# branch e2631 as real commits; this file no longer has a legacy base switch.

# Find the repo root: the kit is the directory holding scripts/pins.env and
# host/release.mjs. (The old marker was apply.sh + overlay/, both retired.)
e2631_find_kit() {
	_e_d=$(cd "$(dirname "$1")" 2>/dev/null && pwd) || return 1
	while [ -n "$_e_d" ] && [ "$_e_d" != "/" ]; do
		if [ -f "$_e_d/scripts/pins.env" ] && [ -f "$_e_d/host/release.mjs" ]; then echo "$_e_d"; return 0; fi
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
	echo "env.sh: cannot locate this repository (a directory holding scripts/pins.env and host/release.mjs)." >&2
	echo "        Set E2631_KIT to the directory you cloned the kit into, then re-run." >&2
	exit 1
fi

# $KIT/.env is the local, untracked config. It is read before the pin file so
# it can supply build-path overrides. Only the keys listed in the case below are
# honoured, assigned literally - no eval, so a value containing $( ) or a
# semicolon stays a value.
if [ -f "$E2631_KIT/.env" ]; then
	while IFS= read -r _l || [ -n "$_l" ]; do
		_k=$(printf '%s' "$_l" | sed -n 's/^[[:blank:]]*\(E2631_[A-Z0-9_]*\)[[:blank:]]*=.*$/\1/p')
		[ -n "$_k" ] || continue
		_v=$(printf '%s' "$_l" | sed -n 's/^[^=]*=[[:blank:]]*\(.*\)$/\1/p' | sed 's/[[:blank:]]*$//; s/^["'"'"']\(.*\)["'"'"']$/\1/')
		case "$_k" in
		E2631_WORK) [ -n "${E2631_WORK:-}" ] || E2631_WORK=$_v ;;
		E2631_OUT) [ -n "${E2631_OUT:-}" ] || E2631_OUT=$_v ;;
		E2631_TREE) [ -n "${E2631_TREE:-}" ] || E2631_TREE=$_v ;;
		E2631_FORK_REPO) [ -n "${E2631_FORK_REPO:-}" ] || E2631_FORK_REPO=$_v ;;
		E2631_FORK_BRANCH) [ -n "${E2631_FORK_BRANCH:-}" ] || E2631_FORK_BRANCH=$_v ;;
		E2631_FORK_DEPTH) [ -n "${E2631_FORK_DEPTH:-}" ] || E2631_FORK_DEPTH=$_v ;;
		# E2631_FORK_SHA is deliberately NOT a .env key: the pin file owns it.
		# Parity reproduction switches (P1/P4): the firmware workflow sets both in env.
		E2631_REPRODUCE_V1100) [ -n "${E2631_REPRODUCE_V1100:-}" ] || E2631_REPRODUCE_V1100=$_v ;;
		E2631_BUILD) [ -n "${E2631_BUILD:-}" ] || E2631_BUILD=$_v ;;
		E2631_TEMPLATE) [ -n "${E2631_TEMPLATE:-}" ] || E2631_TEMPLATE=$_v ;;
		E2631_PROXY) [ -n "${E2631_PROXY:-}" ] || E2631_PROXY=$_v ;;
		esac
	done < "$E2631_KIT/.env"
fi

# The directory that holds out/ and the vendor template package. Default: the
# parent of the kit, which is where a sibling checkout naturally lives.
E2631_WORK=${E2631_WORK:-$(dirname "$E2631_KIT")}
E2631_OUT=${E2631_OUT:-$E2631_WORK/out}
# The build checkout: a depth-1 clone of the pinned tree fork (scripts/bootstrap.sh).
E2631_TREE=${E2631_TREE:-$HOME/openwrt}

# ---- the pin file ----------------------------------------------------------
# scripts/pins.env is the single source of pins: the upstream ImmortalWrt
# commit, the reviewed sanechips port tree, the tree-fork tip the build checks
# out, and the two feed commits. bootstrap/base-pin-check read these numbers;
# they are never repeated here. The values are PLAIN KEY=VALUE lines (no
# ${VAR:-default}) because base-pin-check.sh reads the file literally.
E2631_PIN_FILE=$E2631_KIT/scripts/pins.env
if [ ! -f "$E2631_PIN_FILE" ]; then
	echo "env.sh: missing $E2631_PIN_FILE - the kit cannot build without its pins." >&2
	echo "        Restore it with: git checkout -- scripts/pins.env" >&2
	exit 1
fi
# A local rehearsal may point REPO/BRANCH/DEPTH at a local fork copy through the
# environment or .env; the source below would overwrite that, so keep them.
_e2631_keep_fork_repo=${E2631_FORK_REPO:-}
_e2631_keep_fork_branch=${E2631_FORK_BRANCH:-}
_e2631_keep_fork_depth=${E2631_FORK_DEPTH:-}
. "$E2631_PIN_FILE"
if [ -n "$_e2631_keep_fork_repo" ]; then E2631_FORK_REPO=$_e2631_keep_fork_repo; fi
if [ -n "$_e2631_keep_fork_branch" ]; then E2631_FORK_BRANCH=$_e2631_keep_fork_branch; fi
if [ -n "$_e2631_keep_fork_depth" ]; then E2631_FORK_DEPTH=$_e2631_keep_fork_depth; fi
if [ -z "${E2631_FORK_SHA:-}" ]; then
	echo "env.sh: $E2631_PIN_FILE records no E2631_FORK_SHA - the tree-fork pin is incomplete." >&2
	exit 1
fi

# The version-header template. Default is the 532-byte header slice shipped here
# (seed/vendor-verhdr-8b8.bin): packing only reads the 512-byte version header, so a
# full vendor package is optional. Point this at an official .bin you own to run
# mkfactory's selftest/info, or to re-check the slice against the real thing.
E2631_TEMPLATE=${E2631_TEMPLATE:-$E2631_KIT/seed/vendor-verhdr-8b8.bin}
# Scripts that drop a log under out/ should not have to create it, and a fresh clone has
# no out/ yet. Failing to create it is not fatal: the read-only tools need no scratch dir.
[ -d "$E2631_OUT" ] || mkdir -p "$E2631_OUT" 2>/dev/null || true
export E2631_KIT E2631_WORK E2631_OUT E2631_TREE E2631_TEMPLATE E2631_PIN_FILE \
	E2631_FORK_REPO E2631_FORK_BRANCH E2631_FORK_SHA E2631_FORK_DEPTH \
	E2631_FEED_PACKAGES_SHA E2631_FEED_LUCI_SHA \
	E2631_REPRODUCE_V1100 E2631_BUILD
# Pin provenance from scripts/pins.env, exported for CI/SOURCE-INFO consumers.
export E2631_IW_REPO E2631_IW_BRANCH E2631_IW_SHA E2631_IW_TREE_SHA \
	E2631_BASE_KERNEL E2631_BASE_TREE_SHA \
	E2631_PORT_REPO E2631_PORT_BRANCH E2631_PORT_SHA E2631_PORT_BASE_SHA \
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
