#!/usr/bin/env node
// Static checks for the CI layer of the ImmortalWrt adaptation (T3):
// the two workflows, the artifact/version naming they publish, and the release
// channel the on-device updater talks to must agree with the repo, without
// running a build. Runs in check.yml and in `make check` (T4 owns check.sh;
// this script is self-contained so either place can call it).
//
//   node tools/check-workflows.mjs
import fs from 'node:fs';
import path from 'node:path';

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const read = (p) => fs.readFileSync(path.join(REPO, p), 'utf8');
const WF = { check: read('.github/workflows/check.yml'), firmware: read('.github/workflows/firmware.yml') };
const VERSION = read('overlay/target/linux/sanechips/base-files/etc/e2631-version').trim();
const UPDATER = read('overlay/target/linux/sanechips/base-files/sbin/e2631-upgrade');
const BUILD_SH = read('scripts/build.sh');
const RELEASE = read('host/release.mjs');
const STAGE = read('host/stage.mjs');
const PUBLISH = read('host/publish.mjs');

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

// 1. brand + version stamp agree between the image and CI.
ok('the image version string is the locked ImmortalWrt v1.10.0', VERSION === 'ImmortalWrt v1.10.0', VERSION);
ok('firmware.yml stamps the same version into E2631_VERSION',
  has(WF.firmware, 'E2631_VERSION: ' + VERSION));
ok('firmware.yml builds on the ImmortalWrt base',
  has(WF.firmware, 'E2631_BASE_KIND: immortalwrt'));

// 2. artifact naming is e2631-immortalwrt-* everywhere it is produced.
ok('firmware.yml collects e2631-immortalwrt-*.bin', has(WF.firmware, "e2631-immortalwrt-*.bin"));
ok('firmware.yml stages e2631-immortalwrt-experimental.bin',
  has(WF.firmware, 'release/e2631-immortalwrt-experimental.bin'));
ok('build.sh packages e2631-immortalwrt-$STAMP.bin',
  (BUILD_SH.match(/e2631-immortalwrt-\$STAMP\.bin/g) || []).length === 2);
ok('host/release.mjs defaults to out/e2631-immortalwrt-factory.bin',
  has(RELEASE, "'out/e2631-immortalwrt-factory.bin'"));
ok('host/stage.mjs uploads out/e2631-immortalwrt-factory.bin',
  has(STAGE, "'out/e2631-immortalwrt-factory.bin'"));
ok('host/publish.mjs example uses the new prefix', has(PUBLISH, 'out/e2631-immortalwrt-v1.0.bin'));
ok('host/publish.mjs release title says ImmortalWrt', has(PUBLISH, 'E2631 ImmortalWrt'));

// 3. no exec-time file still names the old artifact prefix (docs keep history).
{
  const stale = Object.entries({ '.github/workflows/check.yml': WF.check, '.github/workflows/firmware.yml': WF.firmware,
    'scripts/build.sh': BUILD_SH, 'host/release.mjs': RELEASE, 'host/stage.mjs': STAGE, 'host/publish.mjs': PUBLISH })
    .filter(([, text]) => /e2631-openwrt-/.test(text)).map(([f]) => f);
  ok('no workflow or host script still produces e2631-openwrt-*', stale.length === 0, stale.join(', '));
}

// 4. the published release name matches what the updater looks for.
ok('the updater takes the first *.bin asset of the latest release',
  has(UPDATER, "browser_download_url"));
ok('the released asset starts with the e2631-immortalwrt- prefix',
  has(WF.firmware, 'e2631-immortalwrt-experimental.bin') && has(UPDATER, 'e2631-upgrade'));
ok('the updater default channel is this fork',
  has(UPDATER, 'echo QC3284/zte-e2631-immortalwrt)'));
ok('no CI file defaults to the old upstream slug',
  !/(^|[^\\w-])Zlion-Y\/zte-e2631-openwrt/.test(WF.firmware + WF.check));

// 5. SOURCE-INFO keeps the provenance the report promises.
for (const key of ['Kit commit:', 'Base kind:', 'ImmortalWrt base:', 'ImmortalWrt tree (pristine):',
  'Port base tree (4 patches applied):', 'Kernel:', 'Packages feed:', 'Packages commit:',
  'LuCI feed:', 'LuCI commit:', 'Hardware tested: NO']) {
  ok('firmware.yml SOURCE-INFO records ' + key.replace(':', ''), has(WF.firmware, key));
}
ok('firmware.yml hashes the release assets',
  has(WF.firmware, 'sha256sum e2631-immortalwrt-experimental.bin SOURCE-INFO.txt > SHA256SUMS'));

// 6. least privilege and pinning in both workflows.
ok('firmware.yml is read-only by default and write only in the build job',
  before(WF.firmware, 'permissions:\n  contents: read', 'permissions:\n      contents: write'));
ok('check.yml is read-only', has(WF.check, 'permissions:\n  contents: read'));
ok('both workflows pin Node 22.16.0',
  (WF.check.match(/node-version: '22\.16\.0'/g) || []).length === 1 &&
  (WF.firmware.match(/node-version: '22\.16\.0'/g) || []).length === 1);
ok('firmware.yml is manual-dispatch only (no push trigger)',
  has(WF.firmware, 'workflow_dispatch:') && !/^  push:/m.test(WF.firmware));
ok('the publishing step is gated behind the build+verify steps',
  before(WF.firmware, 'name: Build, package and verify firmware', 'name: Publish only after all build and artifact gates pass'));
ok('firmware.yml releases are prereleases only',
  has(WF.firmware, '--prerelease') && !has(WF.firmware, '--latest'));

// 7. check.yml runs the host simulation and these static checks.
ok('check.yml runs the updater simulation', has(WF.check, 'node host/sim-upgrade.mjs'));
ok('check.yml runs these workflow checks', has(WF.check, 'node tools/check-workflows.mjs'));
ok('check.yml still runs make check', /run: make check/.test(WF.check));

console.log('');
console.log(fails === 0 ? 'check-workflows: OK - CI, artifact names, version and release channel agree'
  : 'check-workflows: ' + fails + ' check(s) FAILED');
process.exit(fails === 0 ? 0 : 1);
