#!/usr/bin/env node
// Host-side end-to-end simulation of the on-device online updater
// (tests/native/target/linux/zx279128/base-files/sbin/e2631-upgrade, the host
// copy of the tree fork's script). No device and
// no flash: the real updater text runs with its absolute paths redirected into
// a temp sandbox, and /sbin/sysupgrade is a stub that only records its argv.
//
// What T3 has to prove after the brand/prefix switch:
//   * the default release channel is QC3284/zte-e2631-immortalwrt;
//   * a device still running OpenWrt v1.9.0 is offered, and accepts, an
//     ImmortalWrt v1.10.0 release written by this kit (in-place running slot);
//   * downgrade, bad/missing SHA256SUMS, a non-HTTPS mirror and a package the
//     slot tool rejects are refused before sysupgrade is reached.
//
//   node host/sim-upgrade.mjs        # also runs as a step in check.yml
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createHash, randomFillSync } from 'node:crypto';

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const UPDATER_PATH = path.join(REPO, 'tests/native/target/linux/zx279128/base-files/sbin/e2631-upgrade');
const UPDATER = fs.readFileSync(UPDATER_PATH, 'utf8');
const MAGIC = Buffer.from('999999994444444455555555aaaaaaaa', 'hex');
const ASSET = 'e2631-immortalwrt-experimental.bin';
const TAG = 'v1.10.0';
const URL_BASE = 'https://github.com/QC3284/zte-e2631-immortalwrt/releases/download/' + TAG + '/';

let fails = 0;
function ok(name, cond, detail) {
  console.log((cond ? 'PASS ' : 'FAIL ') + name + (detail ? '  (' + detail + ')' : ''));
  if (!cond) fails++;
}
function pkgBytes() {
  const b = Buffer.alloc(64 * 1024);
  MAGIC.copy(b, 0);
  randomFillSync(b, 16);
  return b;
}
const sha256 = (b) => createHash('sha256').update(b).digest('hex');
const readIf = (p) => { try { return fs.readFileSync(p, 'utf8'); } catch { return ''; } };

/* ---------------------------- static assumptions ---------------------------- */
ok('the default release channel is this fork',
  UPDATER.includes('echo QC3284/zte-e2631-immortalwrt)'));
ok('the old upstream slug is not the default any more',
  !UPDATER.includes('|| echo Zlion-Y/zte-e2631-openwrt)'));
ok('the updater comment names this fork',
  UPDATER.includes('QC3284/zte-e2631-immortalwrt'));
ok('version comparison normalises the distro label',
  UPDATER.includes('ver_num()') && UPDATER.includes('version_newer()'));
ok('sysupgrade is the only writer the updater calls',
  (UPDATER.match(/\/sbin\/sysupgrade/g) || []).length === 1 &&
  !/mtd write|ubiformat|dd if=/.test(UPDATER));

/* ------------------------------- fake releases ------------------------------ */
const STUB_UCI = [
  '#!/bin/sh',
  '# uci stub: only the two e2631.upd.* values the updater reads are modelled.',
  '[ "${1:-}" = "-q" ] && shift',
  'if [ "${1:-}" = "get" ] && [ "${2:-}" = "e2631.upd.repository" ]; then',
  '  [ -n "${UCI_REPO:-}" ] && { echo "$UCI_REPO"; exit 0; }',
  '  exit 1',
  'fi',
  'if [ "${1:-}" = "get" ] && [ "${2:-}" = "e2631.upd.mirror" ]; then',
  '  [ -n "${UCI_MIRROR:-}" ] && { echo "$UCI_MIRROR"; exit 0; }',
  '  exit 1',
  'fi',
  'exit 1',
].join('\n');
const STUB_WGET = [
  '#!/bin/sh',
  '# wget stub: serve the fake release by URL suffix and log every URL fetched.',
  'out=; url=',
  'while [ $# -gt 0 ]; do',
  '  case "$1" in',
  '    -O) out=$2; shift 2 ;;',
  '    -q) shift ;;',
  '    *) url=$1; shift ;;',
  '  esac',
  'done',
  'echo "$url" >> "$FIX/wget.log"',
  'case "$url" in',
  '  */releases/latest) cp "$FIX/latest.json" "$out" ;;',
  '  */SHA256SUMS) [ -f "$FIX/SHA256SUMS" ] && cp "$FIX/SHA256SUMS" "$out" || exit 1 ;;',
  '  *.bin) cp "$FIX/asset.bin" "$out" ;;',
  '  *) exit 1 ;;',
  'esac',
].join('\n');
const STUB_FWSLOT = [
  '#!/bin/sh',
  '# fwslot stub: accept only a package that starts with the vendor magic.',
  '[ "${1:-}" = "check" ] || exit 1',
  '[ -s "${2:-}" ] || exit 1',
  'm=$(od -An -tx1 -N16 "$2" | tr -d " \\n")',
  '[ "$m" = "999999994444444455555555aaaaaaaa" ]',
].join('\n');
const STUB_SYSUPGRADE = [
  '#!/bin/sh',
  '# sysupgrade stub: record the call; the simulation never writes flash.',
  'echo "stub-sysupgrade $*" >> "$FIX/sysupgrade.log"',
  'exit 0',
].join('\n');

function writeStub(file, text) { fs.writeFileSync(file, text + '\n'); fs.chmodSync(file, 0o755); }

// Every absolute path the updater touches is moved into the sandbox. Replace all
// occurrences: the first one is usually in a comment, so a single replace would
// leave the code reading the host.
function redirect(text, d) {
  return text
    .split('PATH=/usr/sbin:/usr/bin:/sbin:/bin').join('PATH=' + d.bin + ':/usr/bin:/bin')
    .split('DLDIR=/tmp/e2631-upgrade').join('DLDIR=' + d.sb + '/tmp/e2631-upgrade')
    .split('/etc/.e2631-pending-version').join(d.etc + '/.e2631-pending-version')
    .split('/etc/e2631-version').join(d.etc + '/e2631-version')
    .split('/usr/sbin/e2631-fwslot').join(d.sb + '/usr/sbin/e2631-fwslot')
    .split('/sbin/sysupgrade').join(d.sb + '/sbin/sysupgrade');
}

function makeSandbox(o) {
  const opts = Object.assign({ running: 'OpenWrt v1.9.0', tag: TAG, asset: ASSET,
    sha: 'good', manifest: 'good', mirror: '', repo: '' }, o || {});
  const sb = fs.mkdtempSync(path.join(os.tmpdir(), 'e2631-sim-'));
  const d = { sb, bin: path.join(sb, 'bin'), etc: path.join(sb, 'etc'), fix: path.join(sb, 'fixture') };
  for (const dir of [d.bin, d.etc, d.fix, path.join(sb, 'usr/sbin'), path.join(sb, 'sbin'), path.join(sb, 'tmp')])
    fs.mkdirSync(dir, { recursive: true });
  const bytes = pkgBytes();
  fs.writeFileSync(path.join(d.fix, 'asset.bin'), bytes);
  fs.writeFileSync(path.join(d.etc, 'e2631-version'), opts.running + '\n');
  fs.writeFileSync(path.join(d.fix, 'latest.json'),
    '{"tag_name": "' + opts.tag + '", "assets": [{"browser_download_url": "' + URL_BASE + opts.asset + '"}]}\n');
  const hash = opts.sha === 'bad' ? '0'.repeat(64) : sha256(bytes);
  if (opts.manifest === 'good')
    fs.writeFileSync(path.join(d.fix, 'SHA256SUMS'), hash + '  ' + opts.asset + '\n');
  else if (opts.manifest === 'duplicate')
    fs.writeFileSync(path.join(d.fix, 'SHA256SUMS'),
      hash + '  ' + opts.asset + '\n' + hash + '  ' + opts.asset + '\n');
  writeStub(path.join(d.bin, 'uci'), STUB_UCI);
  writeStub(path.join(d.bin, 'wget'), STUB_WGET);
  writeStub(path.join(sb, 'usr/sbin/e2631-fwslot'), STUB_FWSLOT);
  writeStub(path.join(sb, 'sbin/sysupgrade'), STUB_SYSUPGRADE);
  fs.writeFileSync(path.join(sb, 'updater.sh'), redirect(UPDATER, d));
  return d;
}

function run(d, args, extraEnv) {
  const env = Object.assign({}, process.env, { FIX: d.fix, UCI_MIRROR: '', UCI_REPO: '' }, extraEnv || {});
  try {
    const stdout = execFileSync('sh', [path.join(d.sb, 'updater.sh')].concat(args),
      { env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    return { status: 0, stdout, stderr: '' };
  } catch (e) {
    return { status: e.status == null ? -1 : e.status, stdout: e.stdout || '', stderr: e.stderr || '' };
  }
}
const pending = (d) => readIf(path.join(d.etc, '.e2631-pending-version')).trim();
const calls = (p) => readIf(p).split('\n').filter(Boolean);
const sysupgrades = (d) => calls(path.join(d.fix, 'sysupgrade.log'));
const fetched = (d) => calls(path.join(d.fix, 'wget.log'));
const cleanup = (d) => fs.rmSync(d.sb, { recursive: true, force: true });
const brief = (r) => (r.stdout + r.stderr).trim().split('\n').join(' | ').slice(0, 200);

/* ---------------------------------- checks ---------------------------------- */
// 1. the cross-brand upgrade: OpenWrt v1.9.0 running, ImmortalWrt v1.10.0 offered.
{
  const d = makeSandbox({});
  const r = run(d, ['check']);
  ok('check: an OpenWrt v1.9.0 device sees v1.10.0 as an update',
    r.status === 0 && /update available: v1\.10\.0/.test(r.stdout), brief(r));
  cleanup(d);
}
// 2. the in-place upgrade path: download, strict SHA256SUMS, pending marker,
//    exactly one sysupgrade call - and no real flash because sysupgrade is a stub.
{
  const d = makeSandbox({});
  const r = run(d, ['run']);
  const ups = sysupgrades(d);
  const wl = fetched(d);
  ok('run: exits 0 after downloading a v1.10.0 package for a v1.9.0 system', r.status === 0, brief(r));
  ok('run: pending version marker records v1.10.0', pending(d) === TAG, pending(d));
  ok('run: sysupgrade called exactly once (in-place running slot)', ups.length === 1, String(ups.length));
  ok('run: sysupgrade received the e2631-immortalwrt asset', (ups[0] || '').includes(ASSET), ups[0] || '');
  ok('run: asset and SHA256SUMS both fetched',
    wl.some((u) => u.endsWith(ASSET)) && wl.some((u) => u.endsWith('/SHA256SUMS')), wl.join(' | '));
  cleanup(d);
}
// 3. same version: nothing to do.
{
  const d = makeSandbox({ running: 'ImmortalWrt v1.10.0' });
  const r = run(d, ['check']);
  ok('check: an ImmortalWrt v1.10.0 device is up to date',
    r.status === 0 && /up to date/.test(r.stdout), brief(r));
  cleanup(d);
}
// 4. downgrade refused before any download is used.
{
  const d = makeSandbox({ running: 'ImmortalWrt v1.10.0', tag: 'v1.9.0' });
  const r = run(d, ['run']);
  ok('run: downgrade to v1.9.0 refused', r.status !== 0 && /not newer/.test(r.stderr), brief(r));
  ok('run: downgrade never reaches sysupgrade', sysupgrades(d).length === 0);
  cleanup(d);
}
// 5. a bad checksum stops the update.
{
  const d = makeSandbox({ sha: 'bad' });
  const r = run(d, ['run']);
  ok('run: bad sha256 refused', r.status !== 0 && /sha256 mismatch/.test(r.stderr), brief(r));
  ok('run: bad sha256 writes no pending marker', pending(d) === '');
  ok('run: bad sha256 never reaches sysupgrade', sysupgrades(d).length === 0);
  cleanup(d);
}
// 6. missing SHA256SUMS asset is fatal (the sidecar is mandatory).
{
  const d = makeSandbox({ manifest: 'missing' });
  const r = run(d, ['run']);
  ok('run: missing SHA256SUMS refused',
    r.status !== 0 && /cannot download SHA256SUMS/.test(r.stderr), brief(r));
  ok('run: missing SHA256SUMS never reaches sysupgrade', sysupgrades(d).length === 0);
  cleanup(d);
}
// 7. duplicate manifest entries are rejected (strict parse).
{
  const d = makeSandbox({ manifest: 'duplicate' });
  const r = run(d, ['run']);
  ok('run: duplicate SHA256SUMS entry refused',
    r.status !== 0 && /duplicate or invalid SHA256/.test(r.stderr), brief(r));
  cleanup(d);
}
// 8. an http:// mirror is rejected (update traffic stays HTTPS).
{
  const d = makeSandbox({});
  const r = run(d, ['run'], { UCI_MIRROR: 'http://proxy.example/' });
  ok('run: non-HTTPS mirror refused', r.status !== 0 && /mirror must use HTTPS/.test(r.stderr), brief(r));
  ok('run: refused mirror never reaches sysupgrade', sysupgrades(d).length === 0);
  cleanup(d);
}
// 9. an https mirror is prepended to github URLs only - the API url is not touched.
{
  const d = makeSandbox({});
  const r = run(d, ['run'], { UCI_MIRROR: 'https://gh.example/' });
  const wl = fetched(d);
  ok('run: https mirror allowed', r.status === 0, brief(r));
  ok('run: mirror prefixes the asset URL',
    wl.some((u) => u === 'https://gh.example/' + URL_BASE + ASSET), wl.join(' | '));
  ok('run: mirror is not applied to the api.github.com URL',
    wl.some((u) => u === 'https://api.github.com/repos/QC3284/zte-e2631-immortalwrt/releases/latest'), wl.join(' | '));
  cleanup(d);
}
// 10. the check <file> form verifies a local package without any network use.
{
  const d = makeSandbox({});
  const good = path.join(d.sb, 'good.bin');
  const bad = path.join(d.sb, 'bad.bin');
  fs.copyFileSync(path.join(d.fix, 'asset.bin'), good);
  fs.writeFileSync(bad, 'not a package');
  const rGood = run(d, ['check', good]);
  const rBad = run(d, ['check', bad]);
  ok('check <file>: the kit package passes the slot tool',
    rGood.status === 0 && /package ok/.test(rGood.stdout), brief(rGood));
  ok('check <file>: a foreign file is refused',
    rBad.status !== 0 && /fwslot check rejected/.test(rBad.stderr), brief(rBad));
  ok('check <file>: no download attempted', fetched(d).length === 0);
  cleanup(d);
}
// 11. apply <file> reaches sysupgrade exactly once for a verified package.
{
  const d = makeSandbox({});
  const pkgPath = path.join(d.sb, 'pkg.bin');
  fs.copyFileSync(path.join(d.fix, 'asset.bin'), pkgPath);
  const r = run(d, ['apply', pkgPath]);
  ok('apply <file>: verified package reaches sysupgrade once',
    r.status === 0 && sysupgrades(d).length === 1, brief(r));
  cleanup(d);
}
// 12. the uci e2631.upd.repository override still selects a different channel.
{
  const d = makeSandbox({});
  const r = run(d, ['check'], { UCI_REPO: 'someone/other-fork' });
  ok('check: uci e2631.upd.repository override works', r.status === 0, brief(r));
  cleanup(d);
}

console.log('');
console.log(fails === 0 ? 'sim-upgrade: OK - updater behaviour matches the T3 assumptions'
  : 'sim-upgrade: ' + fails + ' check(s) FAILED');
process.exit(fails === 0 ? 0 : 1);
