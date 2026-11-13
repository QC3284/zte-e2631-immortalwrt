#!/bin/bash
# Get a clean Linux box to the point where `make world` can succeed: the base
# tree at its pinned state, the E2631 overlay applied, the two feeds that matter
# installed, and the seed .config in place.
#
#   bash scripts/bootstrap.sh          # or: make bootstrap
#
# Two bases are supported for one release cycle (scripts/env.sh, the rollback):
# "immortalwrt" is immortalwrt/immortalwrt at a pinned commit with the sanechips
# target port applied from base/*.patch; "legacy" is the original OpenWrt
# sanechips mirror checkout. Either way the result is identified by content, not
# by a branch: the ImmortalWrt tree must hash to E2631_BASE_TREE_SHA.
#
# Idempotent: every step checks before it acts, so re-running after a failed
# build costs seconds. It never deletes a tree - if something looks wrong it
# stops and says what.
set -eu
cd "$(dirname "$0")/.."
. scripts/env.sh

say() { printf 'bootstrap: %s\n' "$*"; }
die() { printf 'bootstrap: %s\n' "$*" >&2; exit 1; }

e2631_need_cmd git "clone the base tree and the feeds" || exit 1
e2631_need_cmd make "drive the OpenWrt build" || exit 1
e2631_need_cmd gcc "build the toolchain (build-essential)" || exit 1
e2631_need_cmd g++ "build some host tools (build-essential)" || exit 1
e2631_need_cmd file "identify the built payloads" || exit 1
e2631_need_cmd sha256sum "verify the vendored port patch series" || exit 1

say "base: kind=$E2631_BASE_KIND  $E2631_BASE_REPO#$E2631_BASE_BRANCH @ $E2631_BASE_SHA"
[ "$E2631_BASE_KIND" = immortalwrt ] &&
	say "      port series: $E2631_PORT_DIR/0001..0004 -> tree $E2631_BASE_TREE_SHA (kernel $E2631_BASE_KERNEL)"

# ---- 1. the base tree --------------------------------------------------------
if [ ! -d "$E2631_TREE" ]; then
	say "creating $E2631_TREE"
	case "$E2631_BASE_KIND" in
	immortalwrt)
		# One pinned commit, no history. Fetching the commit by SHA works on
		# GitHub and keeps this clone small; trust comes from the tree hash
		# below, not from a branch pointer that can move.
		mkdir -p "$E2631_TREE" &&
		git -C "$E2631_TREE" init -q &&
		git -C "$E2631_TREE" remote add origin "$E2631_BASE_REPO" &&
		git -C "$E2631_TREE" fetch -q --depth 1 origin "$E2631_BASE_SHA" &&
		git -C "$E2631_TREE" checkout -q FETCH_HEAD ||
			die "clone failed - network, or $E2631_BASE_REPO does not carry $E2631_BASE_SHA.
       Point E2631_BASE_REPO at a mirror of immortalwrt/immortalwrt, or unset it to use the pin."
		;;
	legacy)
		# A full clone, not a shallow one: the base is pinned to a commit that
		# may not be the branch head, and a shallow clone cannot check out an
		# arbitrary SHA.
		git clone --branch "$E2631_BASE_BRANCH" "$E2631_BASE_REPO" "$E2631_TREE" ||
			die "clone failed - network, or the branch moved? $E2631_BASE_REPO can be overridden in .env"
		;;
	esac
fi
[ -d "$E2631_TREE/.git" ] ||
	die "$E2631_TREE exists but is not a git checkout - point E2631_TREE at a fresh path (or an OpenWrt tree you own)"

if [ "$E2631_BASE_KIND" = immortalwrt ]; then
	# ---- 2a. the vendored sanechips port series -------------------------
	at=$(git -C "$E2631_TREE" rev-parse 'HEAD^{tree}' 2>/dev/null || echo unknown)
	if [ "$at" = "$E2631_BASE_TREE_SHA" ]; then
		say "base tree already at the pinned port tree hash - not re-applying"
	else
		[ -d "$E2631_TREE/.git/rebase-apply" ] &&
			die "git am was interrupted in $E2631_TREE.
       Finish or abort it (git -C $E2631_TREE am --abort), then re-run."
		head=$(git -C "$E2631_TREE" rev-parse HEAD 2>/dev/null || echo unknown)
		if [ "$head" != "$E2631_BASE_SHA" ]; then
			# A pre-existing checkout at another commit is common when
			# E2631_TREE points at an ImmortalWrt tree someone already had.
			# Move it to the pin only when the worktree is clean: anything
			# else is that person's work and this script does not overwrite it.
			[ -n "$(git -C "$E2631_TREE" status --porcelain)" ] &&
				die "$E2631_TREE is at $(git -C "$E2631_TREE" rev-parse --short HEAD 2>/dev/null), not the pinned $E2631_BASE_SHA, and has uncommitted changes.
       Look at 'git -C $E2631_TREE status' first: if those edits are yours, point E2631_TREE at a
       fresh clone instead of overwriting them."
			say "fetching the pinned commit $E2631_BASE_SHA"
			git -C "$E2631_TREE" fetch -q --depth 1 origin "$E2631_BASE_SHA" &&
			git -C "$E2631_TREE" checkout -q FETCH_HEAD ||
				die "cannot fetch $E2631_BASE_SHA from $E2631_BASE_REPO"
			head=$(git -C "$E2631_TREE" rev-parse HEAD)
		fi
		[ "$head" = "$E2631_BASE_SHA" ] ||
			die "$E2631_TREE is at $head, not the pinned $E2631_BASE_SHA"
		[ -n "$(git -C "$E2631_TREE" status --porcelain)" ] &&
			die "$E2631_TREE is at the pinned commit but has uncommitted changes.
       If they are only a stale copy of this overlay, run
       'git -C $E2631_TREE reset --hard $E2631_BASE_SHA' and re-run; otherwise use a fresh tree."

		# The patch bytes are part of the pin: an edited patch must not
		# silently change the base the images are built from.
		for i in 0001 0002 0003 0004; do
			var=E2631_BASE_PATCH_SHA256_$i
			want=${!var}
			[ -n "$want" ] || die "no sha256 pinned for patch $i (base/commits.env incomplete)"
			set -- "$E2631_KIT/$E2631_PORT_DIR/$i"-*.patch
			[ "$#" -eq 1 ] && [ -f "$1" ] ||
				die "expected exactly one $E2631_PORT_DIR/$i-*.patch, found $# - the vendored series is incomplete"
			got=$(sha256sum "$1" | cut -d' ' -f1)
			[ "$got" = "$want" ] ||
				die "patch $i sha256 $got does not match the pin $want.
       The vendored series was edited. If that is deliberate, update
       base/commits.env (and E2631_BASE_TREE_SHA) as described in base/README.md."
		done
		say "applying the sanechips port series ($E2631_PORT_DIR/0001..0004)"
		git -C "$E2631_TREE" -c user.name="e2631 bootstrap" -c user.email="e2631@localhost" \
			am "$E2631_KIT/$E2631_PORT_DIR"/0001-*.patch \
			   "$E2631_KIT/$E2631_PORT_DIR"/0002-*.patch \
			   "$E2631_KIT/$E2631_PORT_DIR"/0003-*.patch \
			   "$E2631_KIT/$E2631_PORT_DIR"/0004-*.patch ||
			die "git am stopped (conflict?) - 'git -C $E2631_TREE am --abort' and inspect.
       The series was built against $E2631_PORT_BASE_SHA; the pinned base is $E2631_IW_SHA."
		got=$(git -C "$E2631_TREE" rev-parse 'HEAD^{tree}')
		[ "$got" = "$E2631_BASE_TREE_SHA" ] ||
			die "base tree hash mismatch: expected $E2631_BASE_TREE_SHA, got $got.
       The patches applied but the result is not the tree this kit was verified against.
       Update base/commits.env deliberately (see base/README.md), or use E2631_BASE_KIND=legacy."
		say "base tree hash verified: $E2631_BASE_TREE_SHA"
	fi
else
	# ---- 2b. legacy base: one pinned OpenWrt commit, no patch series ----
	if ! git -C "$E2631_TREE" rev-parse --verify "$E2631_BASE_SHA^{commit}" >/dev/null 2>&1; then
		say "fetching $E2631_BASE_BRANCH (the pinned commit is not in this clone yet)"
		git -C "$E2631_TREE" fetch -q origin "$E2631_BASE_BRANCH" ||
			die "cannot fetch $E2631_BASE_SHA - it must be reachable from $E2631_BASE_BRANCH"
	fi
	if [ "$(git -C "$E2631_TREE" rev-parse HEAD)" != "$E2631_BASE_SHA" ]; then
		if [ -n "$(git -C "$E2631_TREE" status --porcelain)" ]; then
			die "$E2631_TREE is at $(git -C "$E2631_TREE" rev-parse --short HEAD), not the pinned $E2631_BASE_SHA, and has uncommitted changes.
       Look at 'git -C $E2631_TREE status' first: if those edits are yours, point E2631_TREE at a
       fresh clone instead of overwriting them. If they are only a stale copy of this overlay,
       reset the tree to the pinned commit and re-run."
		fi
		say "checking out the pinned commit $E2631_BASE_SHA"
		git -C "$E2631_TREE" checkout -q "$E2631_BASE_SHA"
	fi
fi

[ -d "$E2631_TREE/target/linux/sanechips" ] ||
	die "no sanechips target in $E2631_TREE - that is not the base tree this kit overlays
       (set E2631_TREE, or remove the directory and re-run). For the ImmortalWrt base the
       target comes from base/$E2631_PORT_DIR applied by this script."

# ---- 3. the overlay ----------------------------------------------------------
say "applying the E2631 overlay to $E2631_TREE"
bash "$E2631_KIT/apply.sh" "$E2631_TREE"

# The two edits apply.sh must leave behind, checked here rather than trusted:
# both are what make the image boot on this board instead of the H3600.
grep -qx 'CONFIG_CMDLINE_FORCE=y' "$E2631_TREE/target/linux/sanechips/config-6.18" ||
	die "apply.sh left no forced kernel command line in $E2631_TREE - the vendor bootargs would win"
grep -q 'Makefile.e2631' "$E2631_TREE/target/linux/sanechips/image/Makefile" ||
	die "apply.sh did not hook image/Makefile - the E2631 device definition would be invisible"

# ---- 4. feeds ---------------------------------------------------------------
# Only packages and luci. Two traps, both hit in practice: a hand-cloned feed has
# no feeds/<name>.index and feeds install then says "Ignoring feed 'luci'" -
# the build still succeeds, just without LuCI, silently; and a killed half-clone
# leaves a shallow repo whose next pull re-fetches the full history.
#
# The ImmortalWrt base names its own feed forks in feeds.conf.default (packages
# and luci come from immortalwrt/*), so the URLs are read from the base tree
# instead of being hardcoded: a future base that moves its feeds keeps working.
# The legacy base keeps the openwrt GitHub mirrors this kit always used.
feed_url() {	# feed_url <feed> -> src-git URL in the base's feeds.conf.default
	sed -n -E "s|^[[:blank:]]*src-git[[:blank:]]+$1[[:blank:]]+([^[:blank:]]+).*|\1|p" \
		"$E2631_TREE/feeds.conf.default" | head -n 1
}
for f in packages luci; do
	case "$E2631_BASE_KIND" in
	immortalwrt) url=$(feed_url "$f") ;;
	legacy) url=https://github.com/openwrt/$f ;;
	esac
	[ -n "$url" ] ||
		die "the base's feeds.conf.default names no '$f' feed - refusing to install a partial build"
	[ -d "$E2631_TREE/feeds/$f/.git" ] || {
		say "cloning feed $f from $url"
		git clone -q --depth 1 --single-branch "$url" "$E2631_TREE/feeds/$f" ||
			die "cloning the $f feed failed - network?"
	}
	[ -f "$E2631_TREE/feeds/$f.index" ] || {
		say "indexing feed $f"
		( cd "$E2631_TREE" && ./scripts/feeds update "$f" 2>&1 | tail -3 )
	}
done
say "installing feed packages"
( cd "$E2631_TREE" && ./scripts/feeds install -a 2>&1 | grep -E "Ignoring|Installing" | tail -8 )
[ -d "$E2631_TREE/package/feeds/packages" ] || die "feed install produced no package/feeds/packages"

# ---- 5. the seed config -----------------------------------------------------
say "seeding .config from seed/e2631.config"
cp "$E2631_KIT/seed/e2631.config" "$E2631_TREE/.config"
( cd "$E2631_TREE" && make defconfig >/dev/null 2>&1 )
# The first expansion can demote seed =y lines to =m: kconfig resolves the
# bare fragment's dependency edges against defaults on that pass (measured
# with the v1.9.1 plugin set: every baked =y came back =m, while the same =y
# re-asserted on the expanded config survived).  Re-assert the seed's own
# CONFIG lines over the expanded result and expand once more.
awk -F= '
	FILENAME ~ /seed/ { if ($0 ~ /^CONFIG_/) want[$1] = $0; next }
	{
		line = $0
		split(line, a, "=")
		if (a[1] in want) line = want[a[1]]
		print line
	}
' "$E2631_KIT/seed/e2631.config" "$E2631_TREE/.config" > "$E2631_TREE/.config.reseed"
mv "$E2631_TREE/.config.reseed" "$E2631_TREE/.config"
( cd "$E2631_TREE" && make defconfig >/dev/null 2>&1 )
for want in CONFIG_TARGET_DEVICE_sanechips_generic_DEVICE_zte_zxhn-e2631= \
	CONFIG_SOFT_FLOAT= CONFIG_PACKAGE_luci= CONFIG_PACKAGE_e2631-fwslot=; do
	grep -q "^$want" "$E2631_TREE/.config" || die "seed check: $want missing after defconfig"
done

# The package manager is apk on both pinned bases; the TLS provider behind
# https is a single package with CONFLICTS set, so exactly one may be selected.
# immortalwrt defaults to apk-openssl/libustream-openssl and the seed follows
# it; two providers here would fail the image build on a package conflict.
grep -qx 'CONFIG_USE_APK=y' "$E2631_TREE/.config" ||
	die "seed check: CONFIG_USE_APK=y missing - both pinned bases build apk packages"
n=$(grep -cE '^CONFIG_PACKAGE_libustream-(openssl|mbedtls|wolfssl)=y$' "$E2631_TREE/.config" || true)
[ "$n" = 1 ] ||
	die "seed check: expected exactly one libustream provider in .config, found $n
       (libustream-* CONFLICT with each other; the seed follows the base's TLS choice)"
grep -qx '# CONFIG_PACKAGE_wpad-basic-mbedtls is not set' "$E2631_TREE/.config" ||
	die "seed check: wpad-basic-mbedtls is still selected - it CONFLICTS with wpad-mbedtls
       (the seed disables it because the sanechips target adds it to DEFAULT_PACKAGES)"

# A package name in the seed that does not exist in the feeds (or lost its
# dependency) is silently dropped by defconfig. That used to be invisible; on a
# new base it is the migration's canary, so report it loudly and keep going so
# the report can be read in one pass.
missing=$(awk -F= '/^CONFIG_PACKAGE_[A-Za-z0-9_-]+=/ { print $1 }' "$E2631_KIT/seed/e2631.config" |
	while read -r k; do grep -q "^$k=" "$E2631_TREE/.config" || echo "$k"; done || true)
if [ -n "$missing" ]; then
	printf 'bootstrap: WARNING seed packages not present in the expanded .config:\n' >&2
	printf '%s\n' "$missing" | sed 's/^/  /' >&2
	printf 'bootstrap:          either add them to the feeds or drop them from seed/e2631.config\n' >&2
fi
say "seed ok: E2631 device selected, soft-float on, apk + one TLS provider, LuCI and the slot tool in the image"

say "done. next: bash scripts/build.sh   (about 40 minutes on 2 cores, then it packs)"
