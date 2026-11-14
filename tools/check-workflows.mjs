#!/usr/bin/env node
// Static checks for the CI layer of the ImmortalWrt adaptation (T3/T-12):
// the two workflows, the artifact/version naming they publish, the pin file,
// and the release channel the on-device updater talks to must agree with the
// repo, without running a build.
//
// T-12 moved the port into the tree fork (QC3284/immortalwrt branch e2631), so
// the version string and the updater are read from that fork at the pinned SHA
// over HTTPS. check.yml runs this with network access; a local offline run
// fails those two checks explicitly instead of skipping them, because a gate
// that cannot see the fork must not look green.
//
//   node tools/check-workflows.mjs
import fs from 'node:fs';
import path from 'node:path';

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
const SEED = read('seed/e2631.config');

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
  'E2631_PORT_SHA', 'E2631_PORT_BASE_SHA', 'E2631_BASE_PATCH_SHA256_0001',
  'E2631_BASE_PATCH_SHA256_0002', 'E2631_BASE_PATCH_SHA256_0003',
  'E2631_BASE_PATCH_SHA256_0004', 'E2631_FEED_PACKAGES_SHA', 'E2631_FEED_LUCI_SHA'];
const hex40 = (v) => typeof v === 'string' && /^[0-9a-f]{40}$/.test(v);
const TREE_REPO = 'QC3284/immortalwrt';
const TREE_BRANCH = 'e2631';
const TREE_PIN_BASE_SHA = '4765b657625ec5bbda74b44400465fe043802b30';
const TREE_PIN_TREE_SHA = '4f89aa7ad0a5132dc047a27a9073b43916f0f957';
const TREE_CI_URL = 'https://raw.githubusercontent.com/' + TREE_REPO + '/' + TREE_BRANCH + '/.github/workflows/check.yml';
const RAW = (p) => 'https://raw.githubusercontent.com/' + TREE_REPO + '/' + pins.E2631_FORK_SHA + '/' + p;
const VERSION_URL = RAW('target/linux/sanechips/base-files/etc/e2631-version');
const UPDATER_URL = RAW('target/linux/sanechips/base-files/sbin/e2631-upgrade');
async function fetchText(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(20000) });
    return res.ok ? await res.text() : '';
  } catch {
    return '';
  }
}
const [TREE_CI, VERSION_RAW, UPDATER_RAW] = await Promise.all(
  [TREE_CI_URL, VERSION_URL, UPDATER_URL].map(fetchText));
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
ok('the fork pin is the reviewed tip on the tree-fork branch',
  pins.E2631_FORK_REPO === 'https://github.com/' + TREE_REPO &&
  pins.E2631_FORK_BRANCH === TREE_BRANCH &&
  pins.E2631_FORK_SHA === 'e96aed31c45442374e9a37fd84c1ac048be90613',
  pins.E2631_FORK_REPO + ' ' + pins.E2631_FORK_BRANCH + ' @ ' + pins.E2631_FORK_SHA);
ok('the ImmortalWrt pin and the base-port tree pin are unchanged',
  pins.E2631_IW_SHA === TREE_PIN_BASE_SHA && pins.E2631_BASE_TREE_SHA === TREE_PIN_TREE_SHA);
ok('all commit pins are full 40-hex SHAs',
  [pins.E2631_IW_SHA, pins.E2631_IW_TREE_SHA, pins.E2631_FORK_SHA, pins.E2631_PORT_SHA,
    pins.E2631_PORT_BASE_SHA, pins.E2631_FEED_PACKAGES_SHA, pins.E2631_FEED_LUCI_SHA]
    .every(hex40) &&
  /^[0-9a-f]{64}$/.test(pins.E2631_BASE_PATCH_SHA256_0001));
ok('the scratch history depth is deep enough to reach the base-port commit (P2)',
  /^[0-9]+$/.test(pins.E2631_FORK_DEPTH) && Number(pins.E2631_FORK_DEPTH) >= 4, pins.E2631_FORK_DEPTH);

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
{
  const stale = Object.entries({ '.github/workflows/check.yml': WF.check, '.github/workflows/firmware.yml': WF.firmware,
    'scripts/build.sh': BUILD_SH, 'host/release.mjs': RELEASE, 'host/stage.mjs': STAGE, 'host/publish.mjs': PUBLISH })
    .filter(([, text]) => /e2631-openwrt-/.test(text)).map(([f]) => f);
  ok('no workflow or host script still produces e2631-openwrt-*', stale.length === 0, stale.join(', '));
}

// 5. SOURCE-INFO keeps the provenance the report promises (T-12 fields).
for (const key of ['Kit commit:', 'ImmortalWrt base:', 'ImmortalWrt tree (pristine):',
  'Port base tree (4 patches applied):', 'Tree fork:', 'Parity reproduction:', 'Kernel build id:',
  'Kernel:', 'Packages feed:', 'Packages commit:', 'LuCI feed:', 'LuCI commit:',
  'APK signing key:', 'Hardware tested: NO']) {
  ok('firmware.yml SOURCE-INFO records ' + key.replace(':', ''), has(WF.firmware, key));
}
ok('firmware.yml SOURCE-INFO no longer records a base kind', !has(WF.firmware, 'Base kind:'));
ok('firmware.yml hashes the release assets',
  has(WF.firmware, 'sha256sum e2631-immortalwrt-experimental.bin SOURCE-INFO.txt > SHA256SUMS'));

// 6. P5: kernel build identity comes from the seed, not the runner.
ok('the seed pins CONFIG_KERNEL_BUILD_USER', has(SEED, 'CONFIG_KERNEL_BUILD_USER="e2631-build"'));
ok('the seed pins CONFIG_KERNEL_BUILD_DOMAIN', has(SEED, 'CONFIG_KERNEL_BUILD_DOMAIN="immortalwrt-e2631"'));
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
  scan.push('Makefile', 'NOTICE', '.env.example', 'seed/e2631.config',
    '.github/workflows/check.yml', '.github/workflows/firmware.yml');
  const skip = new Set(['tools/check-workflows.mjs', 'scripts/base-pin-check.sh', 'tests/test_userdata_gate.sh']);
  const pattern = /overlay\/|apply\.sh|base\/commits\.env|E2631_BASE_KIND/;
  const hits = scan.filter((f) => !skip.has(f) && pattern.test(read(f).split('\n')
    .filter((l) => !/^\s*(#|\/\/)/.test(l)).join('\n')));
  ok('no live file references the retired overlay/apply.sh path', hits.length === 0, hits.join(', '));
}

console.log('');
console.log(fails === 0 ? 'check-workflows: OK - pins, tree-fork content, CI, artifact names and release channel agree'
  : 'check-workflows: ' + fails + ' check(s) FAILED');
process.exit(fails === 0 ? 0 : 1);
