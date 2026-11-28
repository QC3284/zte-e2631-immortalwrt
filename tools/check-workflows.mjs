#!/usr/bin/env node
// Static checks for the CI layer of the ImmortalWrt adaptation (T3/T-12):
// the two workflows, the artifact/version naming they publish, the pin file,
// and the release channel the on-device updater talks to must agree with the
// repo, without running a build.
//
// T-12 moved the port into the tree fork (QC3284/immortalwrt branch e2631), so
// the version string and the updater are read from that fork at the pinned SHA
// over HTTPS. Plan C (2026-11-21, mainline alignment) rebased the series onto
// ImmortalWrt a4ba8240 and renamed the target sanechips -> zx279128, so the
// live paths below are zx279128 ones and the provenance block no longer names
// a merge commit. check.yml runs this with network access; a local offline run
// fails those checks explicitly instead of skipping them, because a gate that
// cannot see the fork must not look green.
//
// C-CI1 added a per-commit checkpatch gate to the tree: the enforcer is
// scripts/check-e2631-checkpatch.sh and the single source of its exemptions is
// docs/checkpatch-exemptions.md. Those files are newer than the kit pin, so
// they are read from the tree-fork branch head (CI-only content); everything
// the image ships is still read at the pinned SHA. A second tree gate,
// scripts/check-e2631-image-expansion.sh, parses the zx279128 image context
// and pins the two non-empty check-size invocations (RUN6 v2 shipped an empty
// kernel limit); it is CI-only content too, so it is read at the branch head
// (resolved with git ls-remote and fetched by SHA, never through the branch
// alias, whose raw copy is CDN-cached for minutes).
//
//   node tools/check-workflows.mjs
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const read = (p) => fs.readFileSync(path.join(REPO, p), 'utf8');
const exists = (p) => fs.existsSync(path.join(REPO, p));
const WF = { check: read('.github/workflows/check.yml'), firmware: read('.github/workflows/firmware.yml') };
const BUILD_SH = read('scripts/build.sh');
const COLLECT = read('wsl/collect.sh');
const RELEASE = read('host/release.mjs');
const STAGE = read('host/stage.mjs');
const PUBLISH = read('host/publish.mjs');
const BOOTSTRAP = read('scripts/bootstrap.sh');

// ---- the pin file ---------------------------------------------------------
const PIN_TEXT = read('scripts/pins.env');
const pins = {};
for (const line of PIN_TEXT.split('\n')) {
  if (!line || line.startsWith('#')) continue;
  const i = line.indexOf('=');
  if (i > 0) pins[line.slice(0, i).trim()] = line.slice(i + 1).trim();
}
const PIN_KEYS = ['E2631_IW_REPO', 'E2631_IW_BRANCH', 'E2631_IW_SHA', 'E2631_IW_TREE_SHA',
  'E2631_BASE_KERNEL', 'E2631_FORK_REPO', 'E2631_FORK_BRANCH', 'E2631_FORK_SHA',
  'E2631_FORK_DEPTH', 'E2631_BASE_TREE_SHA', 'E2631_PORT_REPO', 'E2631_PORT_BRANCH',
  'E2631_PORT_SHA', 'E2631_PORT_BASE_SHA',
  'E2631_FEED_PACKAGES_SHA', 'E2631_FEED_LUCI_SHA'];
const hex40 = (v) => typeof v === 'string' && /^[0-9a-f]{40}$/.test(v);
const TREE_REPO = 'QC3284/immortalwrt';
const TREE_BRANCH = 'e2631';
const TREE_PIN_BASE_SHA = 'a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5';
const TREE_PIN_IW_TREE_SHA = 'b905483c80a3a705825ff7aa9c77d1f3db4a01c3';
const TREE_PIN_TREE_SHA = '6136bd92d5259dbaf22f6bca02c675f05abdf86b';
// Resolve the branch head with git ls-remote and fetch the CI-only files by
// commit SHA. raw.githubusercontent.com caches branch aliases for minutes, and
// a stale copy made the kit checker disagree with a tree CI commit it had just
// accepted (2026-11-21: the tree run 44815481592 was green while two local
// checker runs still fetched the previous check.yml). A by-SHA fetch is
// content-addressed, so whatever the CDN cached for that SHA is the right text;
// if ls-remote fails the branch URL is kept as the fallback so the checks still
// fail explicitly instead of vanishing.
const TREE_HEAD_SHA = (() => {
  try {
    const out = execFileSync('git', ['ls-remote', 'https://github.com/' + TREE_REPO + '.git',
      'refs/heads/' + TREE_BRANCH], { encoding: 'utf8', timeout: 30000 });
    const sha = out.trim().split(/\s+/)[0] || '';
    return /^[0-9a-f]{40}$/.test(sha) ? sha : '';
  } catch {
    return '';
  }
})();
const TREE_HEAD_RAW = (p) => TREE_HEAD_SHA
  ? 'https://raw.githubusercontent.com/' + TREE_REPO + '/' + TREE_HEAD_SHA + '/' + p
  : 'https://raw.githubusercontent.com/' + TREE_REPO + '/refs/heads/' + TREE_BRANCH + '/' + p;
const TREE_CI_URL = TREE_HEAD_RAW('.github/workflows/check.yml');
const TREE_CHECKPATCH_URL = TREE_HEAD_RAW('scripts/check-e2631-checkpatch.sh');
const TREE_EXEMPTIONS_URL = TREE_HEAD_RAW('docs/checkpatch-exemptions.md');
const TREE_IMAGE_EXPANSION_URL = TREE_HEAD_RAW('scripts/check-e2631-image-expansion.sh');
const RETIRED_FORK_TIP = 'd74ec77a' + 'ff719a74c6643e540af74ae5a2f85925';
const SELF = read('tools/check-workflows.mjs');
const RAW = (p) => 'https://raw.githubusercontent.com/' + TREE_REPO + '/' + pins.E2631_FORK_SHA + '/' + p;
const VERSION_URL = RAW('target/linux/zx279128/base-files/etc/e2631-version');
const UPDATER_URL = RAW('target/linux/zx279128/base-files/sbin/e2631-upgrade');
const TREE_SEED_URL = RAW('seed/e2631.config');
const TREE_IMAGE_MAKEFILE_URL = RAW('target/linux/zx279128/image/Makefile');
async function fetchText(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(20000) });
    return res.ok ? await res.text() : '';
  } catch {
    return '';
  }
}
const [TREE_CI, TREE_CHECKPATCH, TREE_EXEMPTIONS, TREE_IMAGE_EXPANSION, VERSION_RAW, UPDATER_RAW, TREE_SEED_RAW, TREE_IMAGE_MAKEFILE] = await Promise.all(
  [TREE_CI_URL, TREE_CHECKPATCH_URL, TREE_EXEMPTIONS_URL, TREE_IMAGE_EXPANSION_URL, VERSION_URL, UPDATER_URL, TREE_SEED_URL, TREE_IMAGE_MAKEFILE_URL].map(fetchText));
const VERSION = VERSION_RAW.trim();
const UPDATER = UPDATER_RAW;

let fails = 0;
function ok(name, cond, detail) {
  console.log((cond ? 'PASS ' : 'FAIL ') + name + (detail ? '  (' + detail + ')' : ''));
  if (!cond) fails++;
}
const has = (hay, needle) => hay.includes(needle);
const before = (hay, a, b) => {
  const i = hay.indexOf(a), j = hay.indexOf(b);
  return i >= 0 && j >= 0 && i < j;
};

// 1. The pin file is the single source of truth and carries every old value.
ok('scripts/pins.env exists and carries every pin', PIN_KEYS.every((k) => typeof pins[k] === 'string' && pins[k].length > 0),
  PIN_KEYS.filter((k) => !pins[k]).join(', '));
ok('the pin file has plain values (no shell ${VAR:-default} expressions)',
  !PIN_TEXT.split('\n').some((l) => l && !l.startsWith('#') && l.includes('${')));
ok('the fork pin is on the reviewed tree-fork branch',
  pins.E2631_FORK_REPO === 'https://github.com/' + TREE_REPO &&
  pins.E2631_FORK_BRANCH === TREE_BRANCH && hex40(pins.E2631_FORK_SHA),
  pins.E2631_FORK_REPO + ' ' + pins.E2631_FORK_BRANCH + ' @ ' + pins.E2631_FORK_SHA);
// The tip must come from scripts/pins.env, never from a constant: a hardcoded
// tip silently keeps checking the old build after a re-pin (d74ec77a lesson).
ok('the fork tip is read from scripts/pins.env and no tip SHA is hardcoded here',
  !has(SELF, RETIRED_FORK_TIP) &&
  [VERSION_URL, UPDATER_URL, TREE_SEED_URL].every((u) => has(u, '/' + pins.E2631_FORK_SHA + '/')),
  pins.E2631_FORK_SHA);
ok('the ImmortalWrt base, its pristine tree and the base-port tree pin are the plan-C values',
  pins.E2631_IW_SHA === TREE_PIN_BASE_SHA &&
  pins.E2631_IW_TREE_SHA === TREE_PIN_IW_TREE_SHA &&
  pins.E2631_BASE_TREE_SHA === TREE_PIN_TREE_SHA,
  pins.E2631_IW_SHA + ' / ' + pins.E2631_BASE_TREE_SHA);
ok('all commit pins are full 40-hex SHAs',
  [pins.E2631_IW_SHA, pins.E2631_IW_TREE_SHA, pins.E2631_FORK_SHA, pins.E2631_PORT_SHA,
    pins.E2631_PORT_BASE_SHA, pins.E2631_FEED_PACKAGES_SHA, pins.E2631_FEED_LUCI_SHA]
    .every(hex40));
ok('the retired merge-commit and patch-series pins are gone',
  !has(PIN_TEXT, 'E2631_MERGED_MASTER_SHA=') && !has(PIN_TEXT, 'E2631_MERGED_MASTER_DATE=') &&
  !has(PIN_TEXT, 'E2631_BASE_PATCH_SHA256_0001='));
ok('the scratch history depth is deep enough to reach the upstream pin (P2)',
  /^[0-9]+$/.test(pins.E2631_FORK_DEPTH) && Number(pins.E2631_FORK_DEPTH) >= 19,
  pins.E2631_FORK_DEPTH + ' levels; the upstream pin is 19 below the tip');

// 2. The tree-fork content is what the kit claims to ship.
ok('the tree fork at the pinned SHA serves /etc/e2631-version', VERSION.length > 0,
  VERSION ? VERSION : 'fetch failed: ' + VERSION_URL);
ok('the image version string is the locked ImmortalWrt v1.10.0', VERSION === 'ImmortalWrt v1.10.0', VERSION);
ok('firmware.yml stamps the same version into E2631_VERSION', has(WF.firmware, 'E2631_VERSION: ' + VERSION));
ok('firmware.yml no longer carries the retired E2631_BASE_KIND switch',
  !has(WF.firmware, 'E2631_BASE_KIND:') && !has(BUILD_SH, 'E2631_BASE_KIND'));

// 3. The published release name matches what the updater looks for.
ok('the tree fork serves the updater at the pinned SHA', UPDATER.length > 0,
  UPDATER ? UPDATER_URL : 'fetch failed');
ok('the updater default channel is this kit fork',
  has(UPDATER, 'echo QC3284/zte-e2631-immortalwrt)'));
ok('the updater takes the first *.bin asset of the latest release', has(UPDATER, 'browser_download_url'));
ok('the released asset uses the e2631-immortalwrt- prefix',
  has(WF.firmware, 'e2631-immortalwrt-experimental.bin'));
ok('no CI file defaults to the old upstream slug',
  !/(^|[^\w-])Zlion-Y\/zte-e2631-openwrt/.test(WF.firmware + WF.check));

// 4. artifact naming is e2631-immortalwrt-* everywhere it is produced.
ok('firmware.yml collects e2631-immortalwrt-*.bin', has(WF.firmware, 'e2631-immortalwrt-*.bin'));
ok('build.sh packages e2631-immortalwrt-$STAMP.bin',
  (BUILD_SH.match(/e2631-immortalwrt-\$STAMP\.bin/g) || []).length === 2);
ok('host/release.mjs defaults to out/e2631-immortalwrt-factory.bin',
  has(RELEASE, "'out/e2631-immortalwrt-factory.bin'"));
ok('host/stage.mjs uploads out/e2631-immortalwrt-factory.bin',
  has(STAGE, "'out/e2631-immortalwrt-factory.bin'"));
ok('host/publish.mjs example uses the new prefix', has(PUBLISH, 'out/e2631-immortalwrt-v1.0.bin'));
ok('host/publish.mjs release title says ImmortalWrt', has(PUBLISH, 'E2631 ImmortalWrt'));
ok('collect.sh accepts both openwrt-* and immortalwrt-* sysupgrade images',
  has(COLLECT, 'openwrt-*-sysupgrade*.bin') && has(COLLECT, 'immortalwrt-*-sysupgrade*.bin'));
ok('host/release.mjs reads the board DTS from the zx279128 target',
  has(RELEASE, 'target/linux/zx279128/dts/') && has(RELEASE, "'--target', 'zx279128'"));
ok('the native test copies live under target/linux/zx279128',
  exists('tests/native/target/linux/zx279128/base-files/sbin/e2631-upgrade') &&
  !exists('tests/native/target/linux/sanechips'));
{
  const stale = Object.entries({ '.github/workflows/check.yml': WF.check, '.github/workflows/firmware.yml': WF.firmware,
    'scripts/build.sh': BUILD_SH, 'host/release.mjs': RELEASE, 'host/stage.mjs': STAGE, 'host/publish.mjs': PUBLISH })
    .filter(([, text]) => /e2631-openwrt-/.test(text)).map(([f]) => f);
  ok('no workflow or host script still produces e2631-openwrt-*', stale.length === 0, stale.join(', '));
}

// 5. SOURCE-INFO keeps the provenance the report promises (T-12 fields).
for (const key of ['Kit commit:', 'ImmortalWrt base:', 'ImmortalWrt tree (pristine):',
  'Port base tree (4 commits applied):', 'Tree fork:', 'Parity reproduction:', 'Kernel build id:',
  'Kernel:', 'Packages feed:', 'Packages commit:', 'LuCI feed:', 'LuCI commit:',
  'APK signing key:', 'Hardware tested: NO']) {
  ok('firmware.yml SOURCE-INFO records ' + key.replace(':', ''), has(WF.firmware, key));
}
ok('firmware.yml SOURCE-INFO no longer records a base kind', !has(WF.firmware, 'Base kind:'));
// Plan C rebased the series onto a4ba8240, so there is no merge commit to name:
// SOURCE-INFO states the base commit and its tree directly, and the retired
// merge/patch lines must not come back (a stale line would misdescribe the image).
ok('firmware.yml SOURCE-INFO cites the ImmortalWrt base commit and its tree',
  has(WF.firmware, 'ImmortalWrt base:') && has(WF.firmware, 'E2631_IW_SHA') &&
  has(WF.firmware, 'E2631_IW_TREE_SHA'));
ok('firmware.yml SOURCE-INFO no longer carries the retired merge or patch-series lines',
  !has(WF.firmware, 'Merged ImmortalWrt master:') && !has(WF.firmware, 'E2631_MERGED_MASTER') &&
  !has(WF.firmware, 'Port patch 0001:'));
ok('firmware.yml hashes the release assets',
  has(WF.firmware, 'sha256sum e2631-immortalwrt-experimental.bin SOURCE-INFO.txt > SHA256SUMS'));

// 6. Seed single-source: the build input is the TREE fork seed at the pinned
// SHA; the kit keeps only the P5 kernel build-identity lines and must not
// shadow the tree seed (the kit copy drifted once and dropped DEVMEM).
ok('the kit no longer ships a seed that could shadow the tree fork seed',
  !exists('seed/e2631.config'), exists('seed/e2631.config') ? 'seed/e2631.config still present' : '');
ok('the pinned tree fork seed carries CONFIG_KERNEL_DEVMEM=y',
  has(TREE_SEED_RAW, 'CONFIG_KERNEL_DEVMEM=y'),
  TREE_SEED_RAW ? '' : 'fetch failed: ' + TREE_SEED_URL);
ok('the pinned tree fork seed carries CONFIG_TARGET_ROOTFS_INITRAMFS=y (D6)',
  has(TREE_SEED_RAW, 'CONFIG_TARGET_ROOTFS_INITRAMFS=y'),
  TREE_SEED_RAW ? '' : 'fetch failed: ' + TREE_SEED_URL);
ok('the pinned tree fork seed names the renamed zx279128 target',
  has(TREE_SEED_RAW, 'CONFIG_TARGET_zx279128=y') &&
  has(TREE_SEED_RAW, 'CONFIG_TARGET_zx279128_generic=y'));
ok('bootstrap asserts the initramfs build mode from the seed',
  has(BOOTSTRAP, 'CONFIG_TARGET_ROOTFS_INITRAMFS='));
ok('bootstrap seeds from the tree fork seed, never from a kit copy',
  has(BOOTSTRAP, 'SEED="$E2631_TREE/seed/e2631.config"') &&
  has(BOOTSTRAP, 'cp "$SEED" "$E2631_TREE/.config"') &&
  !has(BOOTSTRAP, '$E2631_KIT/seed/e2631.config'));
// P5: kernel build identity comes from the seed, not the runner.
// RUN6 v2 (44787949071) failed because the image/Makefile merge unescaped
// $$(KERNEL_SIZE): check-size saw an empty limit, removed kernel.bin and killed
// the build. The pinned makefile must keep the double-dollar form, and the kit
// check.sh must carry the parse-only dump gate that catches it locally.
ok('the pinned image pipeline keeps the check-size limit escaped',
  has(TREE_IMAGE_MAKEFILE, 'check-size $$(KERNEL_SIZE)') &&
  !has(TREE_IMAGE_MAKEFILE, 'check-size $(KERNEL_SIZE)'),
  TREE_IMAGE_MAKEFILE_URL);
ok('check.sh carries the image-pipeline parse gate',
  has(read('scripts/check.sh'), 'g_image_parse') &&
  has(read('scripts/check.sh'), 'check-size 4096k') &&
  has(read('scripts/check.sh'), '-pn SUBTARGET=generic DUMP=1'));
ok('the kit adds CONFIG_KERNEL_BUILD_USER on top of the tree seed',
  has(BOOTSTRAP, 'CONFIG_KERNEL_BUILD_USER="e2631-build"'));
ok('the kit adds CONFIG_KERNEL_BUILD_DOMAIN on top of the tree seed',
  has(BOOTSTRAP, 'CONFIG_KERNEL_BUILD_DOMAIN="immortalwrt-e2631"'));
ok('a post-build step proves CONFIG_DEVMEM=y reached the kernel build config',
  has(WF.firmware, 'build_dir') && has(WF.firmware, 'CONFIG_DEVMEM=y'));
ok('firmware.yml records the kernel build id in SOURCE-INFO',
  has(WF.firmware, 'Kernel build id: e2631-build@immortalwrt-e2631'));
ok('firmware.yml does not try to override KBUILD_BUILD_* through the environment',
  !has(WF.firmware, 'KBUILD_BUILD_USER') && !has(WF.firmware, 'KBUILD_BUILD_HOST'));

// 7. P6: the GitHub ref must not leak into package content (miniupnpd).
ok('the build step strips the GitHub ref from its environment only',
  /env -u GITHUB_REF_NAME[^\n]*make build/.test(WF.firmware) &&
  (WF.firmware.match(/env -u GITHUB_REF_NAME/g) || []).length === 1);
ok('a post-build step asserts the build ref did not reach miniupnpd',
  has(WF.firmware, 'Assert the build ref did not leak') && has(WF.firmware, 'MINIUPNPD_GIT_REF'));

// 8. P8: an optional pinned APK signing key, never committed, always removed.
ok('firmware.yml offers a use_pinned_apk_key input (default off)',
  /use_pinned_apk_key:\n\s+description: .*\n\s+type: boolean\n\s+default: false/.test(WF.firmware));
ok('the pinned key comes from the E2631_APK_PRIVATE_KEY secret',
  has(WF.firmware, 'secrets.E2631_APK_PRIVATE_KEY') && has(WF.firmware, 'E2631_APK_PRIVATE_KEY:'));
ok('the key is written to the build tree with 0600, never into the repo',
  has(WF.firmware, '"$E2631_TREE/private-key.pem"') && has(WF.firmware, 'chmod 600') &&
  !/echo .*\$E2631_APK_PRIVATE_KEY/.test(WF.firmware));
ok('the key is removed on every run before the artifact upload',
  has(WF.firmware, 'rm -f "$E2631_TREE/private-key.pem"') &&
  before(WF.firmware, 'Remove the APK signing key', 'Retain build logs and release files'));

// 9. least privilege and pinning in both workflows.
ok('firmware.yml is read-only by default and write only in the build job',
  before(WF.firmware, 'permissions:\n  contents: read', 'permissions:\n      contents: write'));
ok('check.yml is read-only', has(WF.check, 'permissions:\n  contents: read'));
ok('both workflows use the node24 actions releases (checkout@v5 / setup-node@v5)',
  has(WF.check, 'actions/checkout@v5') && has(WF.check, 'actions/setup-node@v5') &&
  has(WF.firmware, 'actions/checkout@v5') && has(WF.firmware, 'actions/setup-node@v5') &&
  !/actions\/(checkout|setup-node)@v4/.test(WF.check + WF.firmware));
ok('both workflows pin Node 22.16.0',
  (WF.check.match(/node-version: '22\.16\.0'/g) || []).length === 1 &&
  (WF.firmware.match(/node-version: '22\.16\.0'/g) || []).length === 1);
ok('firmware.yml is manual-dispatch only (no push trigger)',
  has(WF.firmware, 'workflow_dispatch:') && !/^  push:/m.test(WF.firmware));
ok('firmware.yml can build without publishing',
  /publish:\n\s+description: .*\n\s+type: boolean\n\s+default: false/.test(WF.firmware));
ok('only the publish step is gated on the publish input',
  (WF.firmware.match(/if: inputs\.publish/g) || []).length === 1);
ok('artifacts and build logs are kept on build-only runs',
  /Retain build logs and release files\n\s+if: always\(\)/.test(WF.firmware));
ok('the publishing step is gated behind the build+verify steps',
  before(WF.firmware, 'name: Build, package and verify firmware', 'name: Publish only after all build and artifact gates pass'));
ok('firmware.yml releases are prereleases only',
  has(WF.firmware, '--prerelease') && !has(WF.firmware, '--latest'));

// 10. check.yml runs the host simulation and these static checks.
ok('check.yml runs the updater simulation', has(WF.check, 'node host/sim-upgrade.mjs'));
ok('check.yml runs these workflow checks', has(WF.check, 'node tools/check-workflows.mjs'));
ok('check.yml still runs make check', /run: make check/.test(WF.check));

// 11. the tree fork publishes the static gate, and that gate cites the triple pin.
ok('the tree fork publishes .github/workflows/check.yml on ' + TREE_BRANCH,
  TREE_CI.length > 0, TREE_CI ? TREE_CI_URL : 'fetch failed');
ok('the tree CI references the pinned ImmortalWrt base and the port tree hash',
  has(TREE_CI, TREE_PIN_BASE_SHA) && has(TREE_CI, TREE_PIN_TREE_SHA));
ok('the tree CI names the renamed zx279128 target and the reviewed port commit subject',
  has(TREE_CI, 'target/linux/zx279128/') &&
  has(TREE_CI, 'zx279128: add support for ZTE ZXHN H3600'));
ok('the tree CI forbids the retired image/Makefile.e2631',
  has(TREE_CI, 'Makefile.e2631 must not exist'));
// C-CI1: the tree gate must enforce the checkpatch baseline, not just assert
// that files exist. The enforcer and its exemption table are newer than the kit
// pin, so they are read from the branch head (CI-only content).
ok('the tree CI publishes the per-commit checkpatch gate',
  TREE_CI.length > 0 && has(TREE_CI, 'Per-commit checkpatch gate') &&
  has(TREE_CI, 'bash scripts/check-e2631-checkpatch.sh') && has(TREE_CI, 'fetch-depth: 0'),
  TREE_CI ? TREE_CI_URL : 'fetch failed: ' + TREE_CI_URL);
ok('the checkpatch gate script is published on ' + TREE_BRANCH,
  TREE_CHECKPATCH.length > 0,
  TREE_CHECKPATCH ? TREE_CHECKPATCH_URL : 'fetch failed: ' + TREE_CHECKPATCH_URL);
ok('the checkpatch gate pins the base and proves it is an ancestor',
  has(TREE_CHECKPATCH, 'E2631_IW_SHA') && has(TREE_CHECKPATCH, 'merge-base --is-ancestor'));
ok('the checkpatch gate checks every non-merge commit with the default report format',
  has(TREE_CHECKPATCH, 'git rev-list --no-merges') && has(TREE_CHECKPATCH, '--no-tree') &&
  has(TREE_CHECKPATCH, '--show-types') && has(TREE_CHECKPATCH, '-g "$sha"') &&
  !/perl .*--ignore/.test(TREE_CHECKPATCH));
ok('the checkpatch gate enforces the plan-C scope and commit-message findings',
  has(TREE_CHECKPATCH, 'target/linux/zx279128') && has(TREE_CHECKPATCH, 'package/e2631') &&
  has(TREE_CHECKPATCH, '<commit-message>'));
ok('the checkpatch gate reads the machine-readable exemption table',
  has(TREE_CHECKPATCH, 'docs/checkpatch-exemptions.md') &&
  has(TREE_EXEMPTIONS, '<!-- checkpatch-exemptions:begin -->') &&
  has(TREE_EXEMPTIONS, '<!-- checkpatch-exemptions:end -->'),
  TREE_EXEMPTIONS ? '' : 'fetch failed: ' + TREE_EXEMPTIONS_URL);
ok('the exemption table documents E1-E4 and carries no stale commit exemption',
  ['E1', 'E2', 'E3', 'E4'].every((id) => has(TREE_EXEMPTIONS, '| ' + id + ' |')) &&
  !has(TREE_EXEMPTIONS, '| E5 |') && !/commit:[0-9a-f]{40}/.test(TREE_EXEMPTIONS));
ok('the tree CI gates the image pipeline expansion',
  TREE_CI.length > 0 && has(TREE_CI, 'Image pipeline expansion check') &&
  has(TREE_CI, 'bash scripts/check-e2631-image-expansion.sh') &&
  TREE_IMAGE_EXPANSION.length > 0,
  TREE_IMAGE_EXPANSION ? TREE_CI_URL : 'fetch failed: ' + TREE_IMAGE_EXPANSION_URL);
ok('the image-pipeline gate pins both non-empty check-size invocations',
  has(TREE_IMAGE_EXPANSION, '-C target/linux/zx279128/image -pn') &&
  has(TREE_IMAGE_EXPANSION, 'check-size 4096k') &&
  has(TREE_IMAGE_EXPANSION, '$$(call concat_cmd,$$(KERNEL))') &&
  has(TREE_IMAGE_EXPANSION, '$$(call Build/check-size,$$(KERNEL_SIZE))') &&
  has(TREE_IMAGE_EXPANSION, '$$(KDIR_KERNEL_IMAGE):') &&
  has(TREE_IMAGE_EXPANSION, 'empty argument') &&
  has(TREE_IMAGE_EXPANSION, 'could not parse the image context'),
  TREE_IMAGE_EXPANSION_URL);
ok('the tree static job guards against stale sanechips target references',
  has(TREE_CI, '@TARGET_sanechips') && has(TREE_CI, 'CONFIG_TARGET_sanechips'));
ok('the tree static job installs the feeds so the seed luci apps resolve',
  has(TREE_CI, './scripts/feeds update packages luci') &&
  has(TREE_CI, 'CONFIG_PACKAGE_luci-app-zte-mesh=y'));

// 12. the legacy tree is gone and no live file pretends otherwise.
ok('the kit no longer carries overlay/, base/ or apply.sh',
  !exists('overlay') && !exists('base') && !exists('apply.sh') && !exists('overlay-removed.txt'));
{
  const scan = [];
  const walk = (rel) => {
    const abs = path.join(REPO, rel);
    for (const e of fs.readdirSync(abs, { withFileTypes: true })) {
      const p = path.join(rel, e.name);
      if (e.isDirectory()) { if (!p.startsWith('tests/native')) walk(p); }
      else scan.push(p);
    }
  };
  for (const d of ['scripts', 'host', 'tools', 'wsl', 'tests']) walk(d);
  scan.push('Makefile', 'NOTICE', '.env.example',
    '.github/workflows/check.yml', '.github/workflows/firmware.yml');
  const skip = new Set(['tools/check-workflows.mjs', 'scripts/base-pin-check.sh', 'tests/test_userdata_gate.sh']);
  const pattern = /overlay\/|apply\.sh|base\/commits\.env|E2631_BASE_KIND|target\/linux\/sanechips|CONFIG_TARGET_DEVICE_sanechips|immortalwrt-sanechips-generic/;
  const hits = scan.filter((f) => !skip.has(f) && pattern.test(read(f).split('\n')
    .filter((l) => !/^\s*(#|\/\/)/.test(l)).join('\n')));
  ok('no live file references the retired overlay/apply.sh path', hits.length === 0, hits.join(', '));
}

// 13. the U-Boot port keeps its pin, its standalone CI shape and the D-U1 single-writer gate.
// The workflow validates the chain at build time; these checks catch a missing or
// half-updated pin before a dispatch, and prove the workflow cannot silently lose
// the gates that the task-58 evidence recorded.
const UBOOT_PIN_TEXT = read('uboot-port/commits.env');
const UBOOT_WF = read('.github/workflows/uboot-build.yml');
const UBOOT_README = read('uboot-port/README.md');
const UBOOT_BUDGET_DOC = read('BUILD.md');
const FAILSAFE_PAGE = read('uboot-port/failsafe/e2631-failsafe.html');
const FAILSAFE_README = read('uboot-port/failsafe/README.md');
const FAILSAFE_EMBED = read('tools/embed-failsafe.sh');
const uboot = {};
for (const line of UBOOT_PIN_TEXT.split('\n')) {
  const m = /^(E2631_UBOOT_[A-Z0-9_]+)=(.*)$/.exec(line.trim());
  if (m) uboot[m[1]] = m[2].trim();
}
const ubootPatchFiles = fs.readdirSync(path.join(REPO, 'uboot-port/patches'))
  .filter((f) => /^[0-9]{4}-.*\.patch$/.test(f)).sort();
const ubootPatchPins = Object.keys(uboot).filter((k) => /^E2631_UBOOT_PATCH_SHA256_[0-9]{4}$/.test(k));
const UBOOT_REQUIRED = ['E2631_UBOOT_REPO', 'E2631_UBOOT_BRANCH', 'E2631_UBOOT_SHA',
  'E2631_UBOOT_BASE_TREE_SHA', 'E2631_UBOOT_TREE_SHA', 'E2631_UBOOT_PAYLOAD_MAX',
  'E2631_UBOOT_TEXT_BASE'];
ok('uboot-port/commits.env pins every port patch and the base/post-am trees',
  UBOOT_REQUIRED.every((k) => typeof uboot[k] === 'string' && uboot[k].length > 0) &&
  hex40(uboot.E2631_UBOOT_SHA) && hex40(uboot.E2631_UBOOT_BASE_TREE_SHA) &&
  hex40(uboot.E2631_UBOOT_TREE_SHA) &&
  uboot.E2631_UBOOT_PAYLOAD_MAX === '0x9F800' && uboot.E2631_UBOOT_TEXT_BASE === '0x47F00000' &&
  ubootPatchPins.length === ubootPatchFiles.length &&
  ubootPatchFiles.every((f) => /^[0-9a-f]{64}$/.test(uboot['E2631_UBOOT_PATCH_SHA256_' + f.slice(0, 4)] || '')),
  ubootPatchFiles.length + ' patch files, ' + ubootPatchPins.length + ' patch pins');
// Comments are stripped before the no-hard-coded-SHA scan; a pin belongs in
// uboot-port/commits.env only, never in the workflow.
const UBOOT_WF_LIVE = UBOOT_WF.split('\n').filter((l) => !/^\s*#/.test(l)).join('\n');
ok('the U-Boot workflow is dispatch-only, read-only and never publishes',
  has(UBOOT_WF, 'workflow_dispatch:') &&
  !/^\s+(push|pull_request):\s*$/m.test(UBOOT_WF) &&
  !/gh release|--prerelease|contents:\s*write/.test(UBOOT_WF_LIVE) &&
  has(UBOOT_WF_LIVE, 'contents: read'));
ok('the U-Boot workflow reads every pin from uboot-port/commits.env, hard-codes no SHA and asserts the chain',
  has(UBOOT_WF, '. uboot-port/commits.env') &&
  ['E2631_UBOOT_BASE_TREE_SHA', 'E2631_UBOOT_TREE_SHA', 'E2631_UBOOT_PATCH_SHA256_',
    'E2631_UBOOT_PATCH_COUNT', 'E2631_UBOOT_PAYLOAD_MAX', 'E2631_UBOOT_TEXT_BASE']
    .every((k) => has(UBOOT_WF, k)) &&
  !/[0-9a-f]{40}/.test(UBOOT_WF_LIVE) &&
  has(UBOOT_WF, "git rev-parse 'HEAD^{tree}'") && has(UBOOT_WF, 'git rev-list --count') &&
  has(UBOOT_WF, 'sha256sum -c') && has(UBOOT_WF, 'readelf -h') &&
  has(UBOOT_WF, 'above the CI gate $gate bytes'));
ok('the U-Boot workflow enforces the D-U1 commands and the single-writer gate',
  ['e2631flash', 'e2631verify', 'e2631slot'].every((c) => has(UBOOT_WF, c)) &&
  has(UBOOT_WF, 'flash an image to SPI-NAND with erase, blank and readback checks') &&
  has(UBOOT_WF, 'compare a RAM image with a SPI-NAND range by CRC32 (read-only)') &&
  has(UBOOT_WF, 'print the firmware slot table') &&
  ['e2631_write_range', 'e2631_erase_range', 'do_e2631flash'].every((f) => has(UBOOT_WF, f)) &&
  has(UBOOT_WF, '# CONFIG_CMD_MTD_WRITE is not set') && has(UBOOT_WF, 'objdump') &&
  has(UBOOT_WF, 'vacuous gate') && has(UBOOT_WF, 'E2631_ENV_OFF') &&
  has(UBOOT_WF, 'DO NOT POWER OFF') && has(UBOOT_WF, 'overlaps the environment'));
ok('the U-Boot artifact records the banner, both crc32 values and the command help dump',
  has(UBOOT_WF, 'E2631-COMMAND-HELP.txt') && has(UBOOT_WF, 'Banner:') &&
  has(UBOOT_WF, 'u-boot.bin crc32:') && has(UBOOT_WF, 'mtd0 image crc32:') &&
  /sha256sum[^\n]*E2631-COMMAND-HELP\.txt/.test(UBOOT_WF) &&
  has(UBOOT_WF, 'UBOOT-INFO.txt'));
// Payload budget (task-71): the mtd0 window caps the payload at 0x9F800
// (653312 bytes); CI keeps an 8 KiB margin, so it fails above 645120 bytes and
// does so before assembling the mtd0 image. The numbers are documented in
// uboot-port/README.md (hard cap) and BUILD.md (budget table).
const ubootPayloadMax = parseInt(uboot.E2631_UBOOT_PAYLOAD_MAX, 16);
const ubootGate = ubootPayloadMax - 8192;
const ubootGateAt = UBOOT_WF.indexOf('gate=$((max - margin))');
// lastIndexOf: the gate comment also names the later step, so only the last
// occurrence is the real "Package the flashable mtd0 image" step.
const ubootPackAt = UBOOT_WF.lastIndexOf('Package the flashable mtd0 image');
ok('the U-Boot workflow gates the payload at 653312 - 8192 bytes before assembling mtd0',
  ubootPayloadMax === 653312 && ubootGate === 645120 &&
  has(UBOOT_WF, 'margin=8192') && has(UBOOT_WF, 'gate=$((max - margin))') &&
  has(UBOOT_WF, 'if [ "$size" -gt "$gate" ]') &&
  has(UBOOT_WF, 'above the CI gate $gate bytes') &&
  has(UBOOT_WF, 'observed $size, limit $gate') &&
  ubootGateAt > 0 && ubootPackAt > ubootGateAt,
  'payload max ' + uboot.E2631_UBOOT_PAYLOAD_MAX + ', gate ' + ubootGate + ', gate before mtd0 packaging');
ok('the payload budget is documented against uboot-port/README.md',
  ['0x9F800', '653312', '638 KiB'].every((s) => has(UBOOT_README, s)) &&
  ['653312', '645120', '0x9F800', '8192', '0x20800..0xBFFFF'].every((s) => has(UBOOT_BUDGET_DOC, s)));
ok('UBOOT-SIZES.txt reports the per-object .text sizes and is covered by SHA256SUMS',
  has(UBOOT_WF, 'UBOOT-SIZES.txt') &&
  has(UBOOT_WF, 'arm-none-eabi-size') &&
  has(UBOOT_WF, 'xargs -0 -r arm-none-eabi-size') &&
  has(UBOOT_WF, 'sorted by text desc') &&
  has(UBOOT_WF, "no 'make sizes' target") &&
  has(UBOOT_WF, 'expected the full build') &&
  /sha256sum[^\n]*UBOOT-SIZES\.txt/.test(UBOOT_WF));
ok('UBOOT-INFO.txt carries the payload footprint table',
  ['payload footprint', 'u-boot.bin bytes:', 'mtd0 image bytes:', 'hard cap bytes:',
    'CI gate bytes:', 'headroom bytes vs hard cap:', 'headroom percent vs hard cap:',
    'headroom bytes vs CI gate:', 'env block sha256:', '.config sha256:'].every((s) => has(UBOOT_WF, s)) &&
  has(UBOOT_WF, 'sha256sum build/.config'));

// E4 v1 (task-73) / v2 (task-83): the rescue page is one self-contained HTML
// file that the build gzip-embeds into the U-Boot tree; the page talks to the
// rescue HTTP server with a raw POST body and polls /status. The page, the embed
// tool, the frozen symbols and the workflow hook are pinned here so that an
// external dependency, a multipart regression or a symbol rename cannot land
// silently. The page budget is 32768 bytes: the task-83 v2 contract, raised from
// the v1 6144-byte gate by task-87 (evidence/e4-v2-contract-design-20261128.md).
const failsafeCheck = (() => {
  try {
    const out = execFileSync('bash', [path.join(REPO, 'tools/embed-failsafe.sh'), '--check'], { encoding: 'utf8' });
    const m = /raw (\d+) B, gzip (\d+) B \(limit (\d+) B\)/.exec(out);
    return m ? { out, raw: Number(m[1]), gzip: Number(m[2]), limit: Number(m[3]), ok: true } : { out, ok: false };
  } catch (e) {
    return { out: String(e.stdout || e.message), ok: false };
  }
})();
ok('the E4 rescue page is a single self-contained gzip asset within the 32768-byte v2 budget',
  failsafeCheck.ok && failsafeCheck.limit === 32768 && failsafeCheck.gzip <= failsafeCheck.limit &&
  failsafeCheck.raw > failsafeCheck.gzip &&
  FAILSAFE_PAGE.includes('xhr.send(file)') && !/FormData|multipart/.test(FAILSAFE_PAGE) &&
  FAILSAFE_PAGE.includes('upload.onprogress') && FAILSAFE_PAGE.includes('function sha256(') &&
  FAILSAFE_PAGE.includes('id="validate"') && FAILSAFE_PAGE.includes('id="write"') &&
  FAILSAFE_PAGE.includes('/flash?mode=') && FAILSAFE_PAGE.includes('/status') &&
  FAILSAFE_PAGE.includes('X-E2631-Confirm') && FAILSAFE_PAGE.includes('655360') &&
  FAILSAFE_PAGE.includes('X-E2631-SHA256') && FAILSAFE_PAGE.includes('sha_match') &&
  FAILSAFE_PAGE.includes('devsha') && !/https?:\/\//.test(FAILSAFE_PAGE) &&
  !/<script[^>]+src=/.test(FAILSAFE_PAGE) && !/<link[^>]+href=/.test(FAILSAFE_PAGE) &&
  !/\/reboot/.test(FAILSAFE_PAGE),
  failsafeCheck.ok ? 'raw ' + failsafeCheck.raw + ' B, gzip ' + failsafeCheck.gzip + ' B, limit ' + failsafeCheck.limit + ' B' : failsafeCheck.out.slice(0, 200));
ok('tools/embed-failsafe.sh defines the frozen symbols and emits deterministic asset files',
  FAILSAFE_EMBED.includes('e2631_failsafe_html_gz[]') &&
  FAILSAFE_EMBED.includes('e2631_failsafe_html_gz_len') &&
  FAILSAFE_EMBED.includes('gzip -9 -n') && FAILSAFE_EMBED.includes('--check') &&
  FAILSAFE_EMBED.includes('e2631_failsafe_asset.c') &&
  FAILSAFE_EMBED.includes('e2631_failsafe_asset.h') &&
  FAILSAFE_EMBED.includes('Deterministic') // emitter comment: no timestamps/paths
  && FAILSAFE_EMBED.includes('MAX=32768') &&
  FAILSAFE_EMBED.includes('<= 32768') &&
  FAILSAFE_EMBED.includes('e4-v2-contract-design-20261128.md') &&
  !/\$\(date|date \+/.test(FAILSAFE_EMBED));
const failsafeEmbedAt = UBOOT_WF.indexOf('Embed the failsafe rescue page');
const failsafePatchAt = UBOOT_WF.indexOf('post-am:');
const failsafeBuildAt = UBOOT_WF.indexOf('Configure and build with the ARM cross toolchain');
ok('the U-Boot workflow embeds the rescue page after git am, before make, and ships the size stats',
  failsafeEmbedAt > 0 && failsafeEmbedAt > failsafePatchAt && failsafeEmbedAt < failsafeBuildAt &&
  UBOOT_WF.includes('tools/embed-failsafe.sh') &&
  UBOOT_WF.includes('--outdir "$UBOOT_DIR/board/zte/zxhn-e2631"') &&
  UBOOT_WF.includes('--stats "$UBOOT_DIR/artifacts/E2631-FAILSAFE-ASSET.txt"') &&
  /sha256sum[^\n]*E2631-FAILSAFE-ASSET\.txt/.test(UBOOT_WF) &&
  UBOOT_WF.includes('e2631_failsafe_asset.c') &&
  UBOOT_WF.includes('e2631_failsafe_asset.h') &&
  /sha256sum[^\n]*e2631_failsafe_asset\.c/.test(UBOOT_WF) &&
  UBOOT_WF.includes('failsafe rescue page (E4 v1, task-73):'),
  'embed at ' + failsafeEmbedAt + ', post-am at ' + failsafePatchAt + ', build at ' + failsafeBuildAt);
ok('uboot-port/failsafe/README.md documents the frozen interface, the protocol and the size budget',
  ['e2631_failsafe_html_gz', 'e2631_failsafe_html_gz_len', 'POST /flash?mode=validate',
    'POST /flash?mode=write', 'GET /status', 'X-E2631-Confirm: write', 'X-E2631-SHA256',
    'sha_match', '32768', 'e4-v2-contract-design-20261128.md', 'tools/embed-failsafe.sh',
    '--outdir'].every((s) => FAILSAFE_README.includes(s)) &&
  FAILSAFE_README.includes('仅校验') && FAILSAFE_README.includes('写入待命'));

console.log('');
console.log(fails === 0 ? 'check-workflows: OK - pins, tree-fork content, CI, artifact names and release channel agree'
  : 'check-workflows: ' + fails + ' check(s) FAILED');
process.exit(fails === 0 ? 0 : 1);
