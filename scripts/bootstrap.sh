#!/bin/bash
# Get a clean Linux box to the point where `make world` can succeed: the E2631
# ImmortalWrt tree fork at its pinned commit, the two feeds that matter
# installed at their pinned commits, and the seed .config in place.
#
#   bash scripts/bootstrap.sh          # or: make bootstrap
#
# The sanechips port and the E2631 device/package support are real commits in
# QC3284/immortalwrt, branch e2631, pinned by E2631_FORK_SHA (scripts/pins.env)
# - not a patch series applied here. The BUILD tree is fetched at --depth 1
# (parity requirement P2, evidence/immortalwrt-verify-20261114.md: rules.mk
# COMMITCOUNT is "git rev-list --count HEAD .", so a deeper clone changes
# base-files PKG_RELEASE). The history assertions - base-port tree in history,
# the four sanechips commits on the upstream pin - run in a separate scratch
# repo under $E2631_WORK, so the build tree never deepens.
#
# Feeds are pinned too (P3): each feed is cloned on its branch and then reset to
# the v1.10.0 reference commit, so the branch label survives (LuCI's version.uc
# names it) while the content is the pin. A feed that had drifted is reset, never
# left on the branch tip.
#
# Idempotent: every step checks before it acts, so re-running after a failed
# build costs seconds. It never deletes a tree - if something looks wrong it
# stops and says what.
set -eu
cd "$(dirname "$0")/.."
. scripts/env.sh

say() { printf 'bootstrap: %s\n' "$*"; }
die() { printf 'bootstrap: %s\n' "$*" >&2; exit 1; }

e2631_need_cmd git "clone the tree fork and the feeds" || exit 1
e2631_need_cmd make "drive the OpenWrt build" || exit 1
e2631_need_cmd gcc "build the toolchain (build-essential)" || exit 1
e2631_need_cmd g++ "build some host tools (build-essential)" || exit 1
e2631_need_cmd file "identify the built payloads" || exit 1
e2631_need_cmd sha256sum "verify the tree contents" || exit 1

say "tree fork: $E2631_FORK_REPO#$E2631_FORK_BRANCH @ $E2631_FORK_SHA"
say "            base port tree pin: $E2631_BASE_TREE_SHA (kernel $E2631_BASE_KERNEL)"
say "            pins: $E2631_PIN_FILE"

# ---- 1. the build tree -------------------------------------------------------
# The build tree is always a depth-1 checkout of the pinned fork tip. P2 of the
# v1.10.0 parity evidence: rules.mk COMMITCOUNT is "git rev-list --count HEAD .",
# so a deeper clone changes base-files PKG_RELEASE and the image stops matching
# the released v1.10.0. All history assertions therefore run in the scratch repo
# of section 1b, never in the build tree.
if [ ! -d "$E2631_TREE" ]; then
	say "creating $E2631_TREE"
	mkdir -p "$E2631_TREE" &&
	git -C "$E2631_TREE" init -q &&
	git -C "$E2631_TREE" remote add origin "$E2631_FORK_REPO" ||
		die "cannot create a git checkout at $E2631_TREE"
fi
[ -d "$E2631_TREE/.git" ] ||
	die "$E2631_TREE exists but is not a git checkout - point E2631_TREE at a fresh path"

# ---- 1a. a depth-1 checkout of the pinned fork tip ------------------------
head=$(git -C "$E2631_TREE" rev-parse HEAD 2>/dev/null || echo unknown)
if [ "$head" != "$E2631_FORK_SHA" ]; then
	# Common when E2631_TREE is a leftover of an older build or a dirty
	# experiment. Never overwrite someone's work; only move a clean checkout.
	[ -n "$(git -C "$E2631_TREE" status --porcelain)" ] &&
		die "$E2631_TREE is at $(git -C "$E2631_TREE" rev-parse --short HEAD 2>/dev/null), not the pinned fork tip $E2631_FORK_SHA, and has uncommitted changes.
       Point E2631_TREE at a fresh path (the bootstrap is cheap) instead of overwriting that work."
	old_tree=$(git -C "$E2631_TREE" rev-parse 'HEAD^{tree}' 2>/dev/null || echo "")
	[ "$old_tree" = "$E2631_BASE_TREE_SHA" ] &&
		die "$E2631_TREE is the old patch-series base (tree $E2631_BASE_TREE_SHA); the tree fork lives at
       $E2631_FORK_REPO#$E2631_FORK_BRANCH. Point E2631_TREE at a fresh path (e.g. ~/e2631-tree) and re-run."
	say "fetching the pinned fork tip $E2631_FORK_SHA (depth 1 - the build tree never carries history)"
	git -C "$E2631_TREE" remote get-url origin >/dev/null 2>&1 &&
		git -C "$E2631_TREE" remote set-url origin "$E2631_FORK_REPO" ||
		git -C "$E2631_TREE" remote add origin "$E2631_FORK_REPO"
	git -C "$E2631_TREE" fetch -q --depth 1 origin "$E2631_FORK_SHA" &&
	git -C "$E2631_TREE" checkout -q FETCH_HEAD ||
		die "cannot fetch $E2631_FORK_SHA from $E2631_FORK_REPO"
	head=$(git -C "$E2631_TREE" rev-parse HEAD)
fi
[ "$head" = "$E2631_FORK_SHA" ] ||
	die "$E2631_TREE is at $head, not the pinned fork tip $E2631_FORK_SHA"

# Parity needs exactly one commit of history: a reused tree that was fetched
# deeper changes COMMITCOUNT, hence base-files PKG_RELEASE (P2). Refuse it.
[ -f "$E2631_TREE/.git/shallow" ] ||
	die "$E2631_TREE is a full clone; the v1.10.0 parity build needs a depth-1 checkout (P2). Point E2631_TREE at a fresh path."
n=$(git -C "$E2631_TREE" rev-list --count HEAD 2>/dev/null || echo 0)
[ "$n" = 1 ] ||
	die "$E2631_TREE carries $n commits; the v1.10.0 parity build needs exactly 1 (depth 1). Point E2631_TREE at a fresh path."
say "build tree: depth 1 at $E2631_FORK_SHA (COMMITCOUNT stays 1, parity P2)"

# ---- 1b. history assertions in a scratch repo (never the build tree) --
# A one-commit tree cannot see the port commits, the base-port tree or the
# upstream pin. Fetch the tip with a bigger window into a throwaway repo:
# deepening the build tree would change the build itself.
fork_check="$E2631_WORK/.e2631-fork-history"
say "verifying the fork history in $fork_check (depth $E2631_FORK_DEPTH)"
rm -rf "$fork_check"
mkdir -p "$fork_check" &&
git -C "$fork_check" init -q &&
git -C "$fork_check" remote add origin "$E2631_FORK_REPO" ||
	die "cannot create the scratch history repo at $fork_check"
git -C "$fork_check" fetch -q --depth "$E2631_FORK_DEPTH" origin "$E2631_FORK_SHA" ||
	die "cannot fetch $E2631_FORK_SHA from $E2631_FORK_REPO into the scratch history repo
       (raise E2631_FORK_DEPTH if the pin is deeper than $E2631_FORK_DEPTH)"
ck=$(git -C "$fork_check" rev-parse FETCH_HEAD 2>/dev/null || echo unknown)
[ "$ck" = "$E2631_FORK_SHA" ] ||
	die "the scratch history repo got $ck, not the pinned $E2631_FORK_SHA"

# Content identity, not the branch pointer: the fork history must contain the
# exact base-port tree the kit was verified against.
if ! git -C "$fork_check" log --format=%T FETCH_HEAD 2>/dev/null | grep -qx "$E2631_BASE_TREE_SHA"; then
	die "the fork at $E2631_FORK_SHA has no commit with tree $E2631_BASE_TREE_SHA - it is not the
       reviewed base-port tree. Either the pin moved without a deliberate scripts/pins.env update,
       or the shallow fetch (depth $E2631_FORK_DEPTH) was too small to reach that commit."
fi
say "base port tree verified in the fork history: $E2631_BASE_TREE_SHA"

# The upstream commit the port was made against must be in the fetched window
# and be an ancestor; the four reviewed commits must sit directly on it.
if ! git -C "$fork_check" cat-file -e "$E2631_IW_SHA^{commit}" 2>/dev/null; then
	die "the pinned ImmortalWrt commit $E2631_IW_SHA is outside the fetched history window
       (depth $E2631_FORK_DEPTH) - raise E2631_FORK_DEPTH or check the fork pin"
fi
git -C "$fork_check" merge-base --is-ancestor "$E2631_IW_SHA" FETCH_HEAD ||
	die "the fork tip is not descended from the pinned ImmortalWrt commit $E2631_IW_SHA"
say "ancestry verified: $E2631_IW_SHA is in the fork history"
port_head=$(git -C "$fork_check" log --format='%H %T' FETCH_HEAD 2>/dev/null |
	awk -v t="$E2631_BASE_TREE_SHA" '$2 == t { print $1; exit }')
[ -n "$port_head" ] ||
	die "cannot locate the base-port commit (tree $E2631_BASE_TREE_SHA) in the fetched history"
port_steps=$(git -C "$fork_check" rev-list --count "$E2631_IW_SHA..$port_head")
[ "$port_steps" = 4 ] ||
	die "the port series is $port_steps commits above $E2631_IW_SHA, expected the four reviewed commits (tree $E2631_BASE_TREE_SHA)"
say "port series verified: 4 commits above the ImmortalWrt pin"

# Device support is committed in the fork: the files must exist in the build
# tree (depth 1 carries the full working tree, just not the history).
for p in target/linux/sanechips/base-files/etc/config/wireless \
	 target/linux/sanechips/image/Makefile.e2631; do
	git -C "$E2631_TREE" ls-tree -r --name-only HEAD -- "$p" | grep -qx "$p" ||
		die "the tree fork has no $p - the e2631 commit set is incomplete"
done
git -C "$E2631_TREE" ls-tree -r --name-only HEAD -- package/e2631 | grep -q '/Makefile$' ||
	die "the tree fork has no package/e2631/*/Makefile - the e2631 packages are missing"

# ---- 3. the committed kernel pin and image hook ----------------------------
# On the tree fork both properties are committed: a forced kernel command line
# (otherwise the vendor bootargs win) and the image/Makefile hook that includes
# Makefile.e2631. The kit asserts them; it never applies the port itself.
kf="$E2631_TREE/target/linux/generic/kernel-6.18"
[ -f "$kf" ] || die "$E2631_TREE has no $kf - not an OpenWrt/ImmortalWrt tree?"
if [ -n "${E2631_BASE_KERNEL:-}" ]; then
	want_kernel=${E2631_BASE_KERNEL#6.18}
	grep -q "^LINUX_VERSION-6.18 = ${want_kernel}$" "$kf" ||
		die "$kf: LINUX_VERSION-6.18 is not ${want_kernel} - the tree is not the pinned kernel $E2631_BASE_KERNEL"
	say "kernel pin verified: $E2631_BASE_KERNEL"
fi
grep -qx 'CONFIG_CMDLINE_FORCE=y' "$E2631_TREE/target/linux/sanechips/config-6.18" ||
	die "$E2631_TREE/target/linux/sanechips/config-6.18 has no CONFIG_CMDLINE_FORCE=y - the vendor bootargs would win"
say "overlay is committed in the tree fork - not applying it again"
grep -q 'Makefile.e2631' "$E2631_TREE/target/linux/sanechips/image/Makefile" ||
	die "the tree's image/Makefile does not hook Makefile.e2631 - the E2631 device definition would be invisible"

# ---- 4. feeds ---------------------------------------------------------------
# Only packages and luci. Two traps, both hit in practice: a hand-cloned feed has
# no feeds/<name>.index and feeds install then says "Ignoring feed 'luci'" -
# the build still succeeds, just without LuCI, silently; and a killed half-clone
# leaves a shallow repo whose next pull re-fetches the full history.
#
# The URLs are read from the base tree's feeds.conf.default (immortalwrt/* on
# this base) instead of being hardcoded: a future base that moves its feeds
# keeps working. P3 pins each feed to the commit the v1.10.0 reference build
# used (scripts/pins.env) instead of taking the branch tip of the day. The feed
# is cloned on its branch and then reset to the pin, so it stays a branch
# checkout (LuCI's version.uc records the branch name) with pinned content; the
# index is rebuilt with "feeds update -i" so that command cannot pull it off
# the pin.
feed_url() {	# feed_url <feed> -> src-git URL in the base's feeds.conf.default
	sed -n -E "s|^[[:blank:]]*src-git[[:blank:]]+$1[[:blank:]]+([^[:blank:]]+).*|\1|p" \
		"$E2631_TREE/feeds.conf.default" | head -n 1
}
for f in packages luci; do
	url=$(feed_url "$f")
	[ -n "$url" ] ||
		die "the base's feeds.conf.default names no '$f' feed - refusing to install a partial build"
	case "$f" in
	packages) feed_pin=${E2631_FEED_PACKAGES_SHA:-} ;;
	luci) feed_pin=${E2631_FEED_LUCI_SHA:-} ;;
	esac
	[ -n "$feed_pin" ] ||
		die "scripts/pins.env records no $f feed commit (P3) - the parity pin is incomplete"
	feed_short=$(printf '%.12s' "$feed_pin")
	# A missing feed is cloned on its default branch first: that keeps a branch
	# label (FETCH_HEAD checkout alone would leave "HEAD detached at FETCH_HEAD"
	# in version.uc and change the image).
	if [ ! -d "$E2631_TREE/feeds/$f/.git" ]; then
		say "cloning feed $f from $url"
		git clone -q --depth 1 "$url" "$E2631_TREE/feeds/$f" ||
			die "cloning the $f feed failed - network?"
	fi
	# P3: reset the branch checkout to the pinned commit, never the branch tip.
	if [ -d "$E2631_TREE/feeds/$f/.git" ] &&
		[ "$(git -C "$E2631_TREE/feeds/$f" rev-parse HEAD 2>/dev/null)" != "$feed_pin" ]; then
		say "pinning feed $f to $feed_short (branch $(git -C "$E2631_TREE/feeds/$f" symbolic-ref --short -q HEAD 2>/dev/null || echo unknown))"
		git -C "$E2631_TREE/feeds/$f" fetch -q --depth 1 origin "$feed_pin" ||
			die "the $f feed cannot fetch the pinned commit $feed_pin - network?"
		git -C "$E2631_TREE/feeds/$f" reset -q --hard FETCH_HEAD ||
			die "cannot reset the $f feed to $feed_pin"
	fi
	got=$(git -C "$E2631_TREE/feeds/$f" rev-parse HEAD 2>/dev/null) || got=""
	[ "$got" = "$feed_pin" ] ||
		die "the $f feed is at ${got:-<unreadable>}, the pin records $feed_pin"
	branch=$(git -C "$E2631_TREE/feeds/$f" symbolic-ref --short -q HEAD 2>/dev/null || true)
	[ -n "$branch" ] ||
		die "the $f feed is a detached checkout; P7 needs the branch label preserved"
	if [ ! -f "$E2631_TREE/feeds/$f.index" ]; then
		say "indexing feed $f (index only - the checkout stays pinned)"
		( cd "$E2631_TREE" && ./scripts/feeds update -i "$f" 2>&1 | tail -3 )
	fi
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

# The package manager is apk; the TLS provider behind https is a single package
# with CONFLICTS set, so exactly one may be selected. The base defaults to
# apk-openssl/libustream-openssl and the seed follows it; two providers here
# would fail the image build on a package conflict.
grep -qx 'CONFIG_USE_APK=y' "$E2631_TREE/.config" ||
	die "seed check: CONFIG_USE_APK=y missing - the pinned base builds apk packages"
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
# ---- 6. parity reproduction of the released v1.10.0 (P1/P4) ----------------
# The firmware workflow's reproduce_v1100 input (parity run, default off). The
# released image reported REVISION r0-bde1448 and SOURCE_DATE_EPOCH 1794624080;
# scripts/getver.sh and scripts/get_source_date_epoch.sh prefer the topdir
# version / version.date files over git, so writing those two files reproduces
# the release stamps on the shallow tree fork. They are untracked build inputs,
# never committed to the fork. E2631_BUILD=20261114 (also from the workflow env
# block) pins host/release.mjs's build field, which the image header carries.
case "${E2631_REPRODUCE_V1100:-false}" in
true|1)
	printf '%s\n' 'r0-bde1448' > "$E2631_TREE/version"
	printf '%s\n' '1794624080' > "$E2631_TREE/version.date"
	say "parity reproduction: wrote version=r0-bde1448, version.date=1794624080 (untracked)"
	[ "${E2631_BUILD:-}" = 20261114 ] ||
		say "WARNING: E2631_BUILD='${E2631_BUILD:-}' - the released v1.10.0 used 20261114, so the version header will differ"
	;;
*)
	# Files from an earlier parity run would otherwise silently stamp this
	# build with v1.10.0's REVISION / build date.
	for f in version version.date; do
		if [ -e "$E2631_TREE/$f" ]; then
			rm -f "$E2631_TREE/$f"
			say "removed leftover $f from a previous parity run"
		fi
	done
	;;
esac

say "done. next: bash scripts/build.sh   (about 40 minutes on 2 cores, then it packs)"
