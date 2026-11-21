#!/usr/bin/env node
// Offline round-trip tests for the P2 U-Boot area tools:
//   tools/mkuboot-image.mjs, tools/e2631-env.mjs,
//   tools/patch-uboot.mjs, tools/verify-mtd0.mjs
//
//   node tests/test_mtd0_tools.mjs                 # synthetic fixture only (CI)
//   node tests/test_mtd0_tools.mjs --dump <mtd0>   # also the live-dump acceptance
//   node tests/test_mtd0_tools.mjs --dump <mtd0> --ecc <128MiB v2 ECC dump> [--raw <132MiB v2 RAW dump>]
//
// The synthetic fixture is built here from first principles: a 1 MiB mtd0 with
// the vendor layout (secondboot header, U-Boot header block + payload + tail,
// erased gap, env block with a real CRC32). The real-dump acceptance uses the
// mtd0 dump collected from the device on 2026-11-15 (sha256 de4ea5bd...). The
// 2026-11-20 programmer dump comes in two shapes: --ecc is the ECC-corrected
// data-only image (128 MiB), so its first 1 MiB must equal the live dump byte
// for byte; --raw is the page-level image (132 MiB, 2048 data + 64 OOB per
// 2112-byte page), so de-interleaving its pages must also reproduce the live
// dump, and its OOB must be all 0xFF.
//
// Everything is offline; no device and no build are involved.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import {
  crc32, sha1, sha256Hex, readU32, writeU32, mtd0Uboot, buildUbootRegion,
  buildFullMtd0, envParse, envEncode, envToText, envFromText, diffRanges,
  MTD0_SIZE, UBOOT_OFF, UBOOT_REGION_SIZE, PAYLOAD_OFF, PAYLOAD_MAX, ENV_OFF,
  ENV_BLOCK_SIZE, ENV_DATA_SIZE, HDR_BLOCK_SIZE, MAGIC_OFF, LEN_OFF,
  DIGEST_OFF, DIGEST_SIZE, TAIL_SIZE, PASSWORD_OFF, PASSWORD_FLAG_OFF,
  PASSWORD_MAX_BYTES,
} from '../tools/lib/mtd0.mjs';

const KIT_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const REAL_MTD0_SHA256 = 'de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f';

const argv = process.argv.slice(2);
function opt(name) {
  const i = argv.indexOf('--' + name);
  if (i < 0) return undefined;
  const value = argv[i + 1];
  if (value === undefined) throw new Error('--' + name + ' needs a value');
  argv.splice(i, 2);
  return value;
}
const dumpPath = opt('dump');
const eccPath = opt('ecc');
const rawPath = opt('raw');
const verbose = argv.includes('--verbose');
const keep = argv.includes('--keep');
if (argv.includes('--help')) {
  console.log('usage: node tests/test_mtd0_tools.mjs [--dump <mtd0>] [--ecc <v2 ECC dump>] [--raw <v2 RAW dump>] [--verbose] [--keep]');
  process.exit(0);
}

let passed = 0;
let failed = 0;
const failures = [];
function test(name, fn) {
  try {
    fn();
    passed++;
    console.log('PASS ' + name);
  } catch (e) {
    failed++;
    failures.push([name, e]);
    console.log('FAIL ' + name + ': ' + e.message);
  }
}
function assert(condition, message) {
  if (!condition) throw new Error(message || 'assertion failed');
}
function same(a, b, message) {
  if (Buffer.compare(a, b) !== 0) {
    const ranges = diffRanges(a, b, 0);
    throw new Error((message || 'buffers differ') + ' (' + ranges.length + ' range(s), first at 0x' +
      (ranges.length ? ranges[0].offset.toString(16) : '?') + ')');
  }
}

// A deterministic byte stream so the fixture is reproducible across runs.
function stream(seed, length) {
  const out = Buffer.alloc(length);
  let x = seed >>> 0;
  for (let i = 0; i < length; i++) {
    x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
    out[i] = (x >>> 24) & 0xFF;
  }
  return out;
}

const FIXTURE_ENV = [
  ['baudrate', '115200'],
  ['bootdelay', '3'],
  ['bootcmd', 'tftp 0x43000000 e2631.bin; bootm 0x43000000'],
  ['ethaddr', '00:11:22:33:44:55'],
  ['ipaddr', '192.168.1.1'],
  ['serverip', '192.168.1.100'],
];
const FIXTURE_PAYLOAD_LEN = 0x68000;
const FIXTURE_PAYLOAD = stream(0x12345678, FIXTURE_PAYLOAD_LEN);
const FIXTURE_TAIL = Buffer.concat([Buffer.from('TAIL'), stream(0x22222222, TAIL_SIZE - 4)]);

function makeFixture() {
  const dump = Buffer.alloc(MTD0_SIZE, 0xFF);
  // secondboot header (0x0): magic/len only; the tools never touch this area.
  dump.write('128s', MAGIC_OFF, 'ascii');
  writeU32(dump, LEN_OFF, 0x8000);
  // U-Boot header block (0x20000): non-trivial bytes, magic, vendor fields.
  const header = stream(0x0BADF00D, HDR_BLOCK_SIZE);
  header.write('128s', MAGIC_OFF, 'ascii');
  header.write('0001ZXIC..', 0x80, 'ascii');
  header.write('BOOTROM', 0x90, 'ascii');
  header.write('RSA2048', 0xA0, 'ascii');
  writeU32(header, 0xAC, 4);
  writeU32(header, 0xB0, 0x66080);
  stream(0x5EED5EED, DIGEST_SIZE).copy(header, DIGEST_OFF);
  header.copy(dump, UBOOT_OFF);
  writeU32(dump, UBOOT_OFF + LEN_OFF, FIXTURE_PAYLOAD_LEN);
  FIXTURE_PAYLOAD.copy(dump, PAYLOAD_OFF);
  FIXTURE_TAIL.copy(dump, PAYLOAD_OFF + FIXTURE_PAYLOAD_LEN);
  // env block at 0xC0000 with a correct CRC.
  envEncode(FIXTURE_ENV).copy(dump, ENV_OFF);
  return dump;
}

const FIXTURE = makeFixture();
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'e2631-mtd0-test-'));
const FIXTURE_PATH = path.join(TMP, 'mtd0-fixture.bin');
fs.writeFileSync(FIXTURE_PATH, FIXTURE);

function runTool(tool, args) {
  const out = execFileSync(process.execPath, [path.join(KIT_ROOT, 'tools', tool)].concat(args), {
    cwd: KIT_ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
  });
  return out;
}
function runToolFail(tool, args) {
  try {
    runTool(tool, args);
    return { status: 0, stdout: '', stderr: '' };
  } catch (e) {
    return { status: e.status === undefined ? 1 : e.status, stdout: e.stdout || '', stderr: e.stderr || '' };
  }
}
function readTmp(name) { return fs.readFileSync(path.join(TMP, name)); }

// ---- library-level checks -------------------------------------------------

test('crc32 matches the standard vectors', function () {
  assert(crc32(Buffer.alloc(0)) === 0, 'empty buffer');
  assert(crc32(Buffer.from('123456789')) === 0xCBF43926, '123456789');
  assert(crc32(Buffer.from('The quick brown fox jumps over the lazy dog')) === 0x414FA339, 'sentence');
});

test('sha1 matches the standard vector', function () {
  assert(sha1(Buffer.from('abc')).toString('hex') === 'a9993e364706816aba3e25717850c26c9cd0d89d', 'abc');
});

test('fixture parses: magic, declared length, payload, tail, digest', function () {
  const image = mtd0Uboot(FIXTURE);
  assert(image.declaredLen === FIXTURE_PAYLOAD_LEN, 'declared length ' + image.declaredLen.toString(16));
  same(image.payload, FIXTURE_PAYLOAD, 'payload');
  same(image.tail, FIXTURE_TAIL, 'tail');
  assert(!image.tailErased, 'tail should not look erased');
  assert(image.digest.length === DIGEST_SIZE, 'digest length');
  assert(readU32(FIXTURE, UBOOT_OFF + MAGIC_OFF) === 0x73383231, 'magic u32');
});

test('buildUbootRegion round-trips the synthetic U-Boot area', function () {
  const image = mtd0Uboot(FIXTURE);
  const region = buildUbootRegion(FIXTURE, image.payload, image.tail);
  assert(region.length === UBOOT_REGION_SIZE, 'region size');
  same(region, FIXTURE.subarray(UBOOT_OFF, UBOOT_OFF + UBOOT_REGION_SIZE), 'round-trip region');
});

test('buildUbootRegion leaves the erased gap erased and the env untouched', function () {
  const region = buildUbootRegion(FIXTURE, FIXTURE_PAYLOAD, FIXTURE_TAIL);
  const gap = region.subarray(HDR_BLOCK_SIZE + FIXTURE_PAYLOAD_LEN + TAIL_SIZE);
  assert(gap.every(function (b) { return b === 0xFF; }), 'gap after the tail is not 0xFF');
  const full = buildFullMtd0(FIXTURE, FIXTURE_PAYLOAD, FIXTURE_TAIL);
  same(full.subarray(ENV_OFF, MTD0_SIZE), FIXTURE.subarray(ENV_OFF, MTD0_SIZE), 'env + tail of mtd0');
});

test('payload limit: exactly 0x9F800 is accepted, one byte more is refused', function () {
  const max = Buffer.alloc(PAYLOAD_MAX, 0xAA);
  const region = buildUbootRegion(FIXTURE, max, null);
  assert(region.length === UBOOT_REGION_SIZE, 'max payload region');
  assert(region[UBOOT_REGION_SIZE - 1] === 0xAA, 'max payload last byte');
  let threw = false;
  try { buildUbootRegion(FIXTURE, Buffer.alloc(PAYLOAD_MAX + 1, 0xAA), null); } catch (e) { threw = true; }
  assert(threw, 'payload over the limit was accepted');
  let tailThrew = false;
  try { buildUbootRegion(FIXTURE, max, Buffer.alloc(TAIL_SIZE, 0xBB)); } catch (e) { tailThrew = true; }
  assert(tailThrew, 'payload + tail that overruns the image area was accepted');
});

test('env parse + encode round-trip the synthetic block', function () {
  const env = envParse(FIXTURE.subarray(ENV_OFF, ENV_OFF + ENV_BLOCK_SIZE));
  assert(env.crcOk, 'CRC');
  assert(env.entries.length === FIXTURE_ENV.length, 'entry count ' + env.entries.length);
  same(envEncode(env.entries), FIXTURE.subarray(ENV_OFF, ENV_OFF + ENV_BLOCK_SIZE), 'env block');
});

test('env CRC corruption is detected', function () {
  const block = Buffer.from(FIXTURE.subarray(ENV_OFF, ENV_OFF + ENV_BLOCK_SIZE));
  block[4 + 10] ^= 0xFF; // flip a data byte after the CRC
  assert(envParse(block).crcOk === false, 'corrupted data still reported a good CRC');
});

test('env text round-trips through dump and build', function () {
  const env = envParse(FIXTURE.subarray(ENV_OFF, ENV_OFF + ENV_BLOCK_SIZE));
  const text = envToText(env.entries);
  const rebuilt = envEncode(envFromText(text));
  same(rebuilt, envEncode(env.entries), 'text -> block');
  assert(text.indexOf('bootcmd=') >= 0, 'text lost bootcmd');
});

test('diffRanges merges close changes and reports distant ones separately', function () {
  const a = Buffer.alloc(64, 0);
  const b = Buffer.from(a);
  b[1] = 1; b[2] = 1; b[40] = 1;
  const ranges = diffRanges(a, b);
  assert(ranges.length === 2, 'expected 2 ranges, got ' + ranges.length);
  assert(ranges[0].offset === 1 && ranges[0].length === 2, 'first range');
  assert(ranges[1].offset === 40 && ranges[1].length === 1, 'second range');
});

// ---- CLI-level checks -----------------------------------------------------

test('CLI mkuboot-image check accepts the fixture', function () {
  const out = runTool('mkuboot-image.mjs', ['check', '--dump', FIXTURE_PATH]);
  assert(out.indexOf('OK:') >= 0, out);
});

test('CLI unpack + build is byte-identical, with and without the tail', function () {
  const payload = path.join(TMP, 'payload.bin');
  const header = path.join(TMP, 'header.bin');
  const tail = path.join(TMP, 'tail.bin');
  runTool('mkuboot-image.mjs', ['unpack', '--dump', FIXTURE_PATH, '--payload', payload, '--header', header, '--tail', tail]);
  same(readTmp('payload.bin'), FIXTURE_PAYLOAD, 'unpacked payload');
  same(readTmp('tail.bin'), FIXTURE_TAIL, 'unpacked tail');
  const region = path.join(TMP, 'region.bin');
  runTool('mkuboot-image.mjs', ['build', '--dump', FIXTURE_PATH, '--payload', payload, '--tail', tail, '--out', region]);
  same(readTmp('region.bin'), FIXTURE.subarray(UBOOT_OFF, UBOOT_OFF + UBOOT_REGION_SIZE), 'packed region');
  const regionNoTail = path.join(TMP, 'region-notail.bin');
  runTool('mkuboot-image.mjs', ['build', '--dump', FIXTURE_PATH, '--payload', payload, '--out', regionNoTail]);
  const noTail = readTmp('region-notail.bin');
  const tailOff = HDR_BLOCK_SIZE + FIXTURE_PAYLOAD_LEN;
  assert(noTail.subarray(tailOff, tailOff + TAIL_SIZE).every(function (b) { return b === 0xFF; }), 'tail not left erased');
  same(noTail.subarray(0, tailOff), FIXTURE.subarray(UBOOT_OFF, UBOOT_OFF + tailOff), 'bytes before the tail');
});

test('CLI mkuboot-image refuses an oversized payload', function () {
  const big = path.join(TMP, 'payload-big.bin');
  fs.writeFileSync(big, Buffer.alloc(PAYLOAD_MAX + 1, 0xAA));
  const result = runToolFail('mkuboot-image.mjs', ['build', '--dump', FIXTURE_PATH, '--payload', big, '--out', path.join(TMP, 'too-big.bin')]);
  assert(result.status !== 0, 'oversized payload was accepted');
  assert(/exceeds/.test(result.stderr), result.stderr);
});

test('CLI env dump + build round-trips the live block', function () {
  const text = path.join(TMP, 'env.txt');
  runTool('e2631-env.mjs', ['dump', '--dump', FIXTURE_PATH, '--out', text]);
  const block = path.join(TMP, 'env-block.bin');
  runTool('e2631-env.mjs', ['build', '--in', text, '--out', block]);
  same(readTmp('env-block.bin'), FIXTURE.subarray(ENV_OFF, ENV_OFF + ENV_BLOCK_SIZE), 'env block');
  const check = runTool('e2631-env.mjs', ['check', '--dump', FIXTURE_PATH]);
  assert(check.indexOf('byte-identical') >= 0, check);
});

test('CLI patch-uboot writes exactly the 20-byte digest at 0x61F80', function () {
  const inPath = FIXTURE_PATH;
  const outPath = path.join(TMP, 'patched.bin');
  const password = 'roundtrip-passw0';
  assert(Buffer.byteLength(password) <= PASSWORD_MAX_BYTES, 'test password too long');
  const out = runTool('patch-uboot.mjs', ['password', '--in', inPath, '--password', password, '--out', outPath]);
  const patched = readTmp('patched.bin');
  const ranges = diffRanges(FIXTURE, patched, 0);
  assert(ranges.length === 1, 'expected one changed range, got ' + ranges.length);
  assert(ranges[0].offset === PASSWORD_OFF, 'changed at 0x' + ranges[0].offset.toString(16));
  assert(ranges[0].length === 20, 'changed ' + ranges[0].length + ' bytes');
  same(patched.subarray(PASSWORD_OFF, PASSWORD_OFF + 20), sha1(Buffer.from(password, 'utf8')), 'digest bytes');
  assert(readU32(patched, PASSWORD_FLAG_OFF) === readU32(FIXTURE, PASSWORD_FLAG_OFF), 'flag changed');
  assert(out.indexOf('before') >= 0 && out.indexOf('after') >= 0, out);
  const check = runTool('patch-uboot.mjs', ['check-password', '--in', outPath, '--password', password]);
  assert(check.indexOf('MATCH') >= 0, check);
  const bad = runToolFail('patch-uboot.mjs', ['check-password', '--in', outPath, '--password', 'wrong-password']);
  assert(bad.status !== 0, 'wrong password accepted');
});

test('CLI patch-uboot refuses a password over the length limit', function () {
  const result = runToolFail('patch-uboot.mjs', ['password', '--in', FIXTURE_PATH, '--password', 'x'.repeat(PASSWORD_MAX_BYTES + 1), '--out', path.join(TMP, 'nope.bin')]);
  assert(result.status !== 0, 'over-long password accepted');
  assert(/limit/.test(result.stderr), result.stderr);
});

test('CLI patch-uboot digest matches sha1sum', function () {
  const password = 'cross-check-1234';
  const tool = runTool('patch-uboot.mjs', ['password', '--in', FIXTURE_PATH, '--password', password, '--print']);
  const line = tool.split('\n').find(function (l) { return l.indexOf('sha1, unsalted') >= 0; });
  assert(line, 'no digest line in: ' + tool);
  const digest = line.slice(line.lastIndexOf(' ') + 1);
  let expected;
  try {
    expected = execFileSync('sha1sum', [], { input: password, encoding: 'utf8' }).trim().split(/\s+/)[0];
  } catch (e) {
    console.log('SKIP sha1sum cross-check: no sha1sum on PATH');
    return;
  }
  assert(digest === expected, 'tool ' + digest + ' vs sha1sum ' + expected);
});

test('CLI verify-mtd0: sha256 match, byte-identical baseline, and a reported diff', function () {
  const ok = runTool('verify-mtd0.mjs', ['--file', FIXTURE_PATH, '--sha256', sha256Hex(FIXTURE)]);
  assert(ok.indexOf('OK sha256 matches') >= 0, ok);
  const sameFile = runTool('verify-mtd0.mjs', ['--file', FIXTURE_PATH, '--baseline', FIXTURE_PATH]);
  assert(sameFile.indexOf('OK: identical') >= 0, sameFile);
  const corrupt = path.join(TMP, 'corrupt.bin');
  const bad = Buffer.from(FIXTURE); bad[0x61F80 + 5] ^= 0xFF;
  fs.writeFileSync(corrupt, bad);
  const diff = runToolFail('verify-mtd0.mjs', ['--file', corrupt, '--baseline', FIXTURE_PATH]);
  assert(diff.status === 1, 'diff exit code ' + diff.status);
  assert(/DIFF: 1 range/.test(diff.stderr), diff.stderr);
  assert(new RegExp('0x' + (0x61F80 + 5).toString(16)).test(diff.stderr), diff.stderr);
  const wrongSha = runToolFail('verify-mtd0.mjs', ['--file', FIXTURE_PATH, '--sha256', '0'.repeat(64)]);
  assert(wrongSha.status === 1, 'wrong sha256 accepted');
});

// ---- live-dump acceptance (only with --dump) ------------------------------

if (dumpPath) {
  const live = fs.readFileSync(dumpPath);
  test('live dump: size, baselined sha256 and magic', function () {
    assert(live.length === MTD0_SIZE, 'size ' + live.length);
    assert(sha256Hex(live) === REAL_MTD0_SHA256, 'sha256 ' + sha256Hex(live));
    const image = mtd0Uboot(live);
    assert(image.declaredLen === FIXTURE_PAYLOAD_LEN, 'declared length 0x' + image.declaredLen.toString(16));
  });
  test('live dump: U-Boot area unpack + build is byte-identical', function () {
    const image = mtd0Uboot(live);
    const region = buildUbootRegion(live, image.payload, image.tailErased ? null : image.tail);
    same(region, live.subarray(UBOOT_OFF, UBOOT_OFF + UBOOT_REGION_SIZE), 'live U-Boot area');
    const full = buildFullMtd0(live, image.payload, image.tailErased ? null : image.tail);
    same(full, live, 'rebuilding with the same payload must reproduce the whole dump');
  });
  test('live dump: env block rebuild is byte-identical (CRC 0xAFFCEC3E)', function () {
    const block = live.subarray(ENV_OFF, ENV_OFF + ENV_BLOCK_SIZE);
    const env = envParse(block);
    assert(env.crcOk, 'CRC');
    assert(env.storedCrc === 0xAFFCEC3E, 'CRC value 0x' + env.storedCrc.toString(16));
    assert(env.entries.length === 22, 'entry count ' + env.entries.length);
    same(envEncode(env.entries), block, 'env block');
    const out = runTool('e2631-env.mjs', ['check', '--dump', dumpPath]);
    assert(out.indexOf('byte-identical') >= 0, out);
  });
  test('live dump: patch changes only the digest window', function () {
    const outPath = path.join(TMP, 'live-patched.bin');
    const password = 'roundtrip-passw0';
    runTool('patch-uboot.mjs', ['password', '--in', dumpPath, '--password', password, '--out', outPath]);
    const patched = readTmp('live-patched.bin');
    const ranges = diffRanges(live, patched, 0);
    assert(ranges.length === 1, 'ranges ' + ranges.length);
    assert(ranges[0].offset === PASSWORD_OFF && ranges[0].length === 20, 'window 0x' + ranges[0].offset.toString(16) + ' +' + ranges[0].length);
    same(patched.subarray(PASSWORD_OFF, PASSWORD_OFF + 20), sha1(Buffer.from(password, 'utf8')), 'digest');
  });
  test('live dump: verify-mtd0 accepts the baseline sha256', function () {
    const out = runTool('verify-mtd0.mjs', ['--file', dumpPath, '--sha256', REAL_MTD0_SHA256]);
    assert(out.indexOf('OK sha256 matches') >= 0, out);
  });
  if (eccPath) {
    test('v2 ECC dump: first 1 MiB equals the live mtd0 dump', function () {
      const ecc = fs.readFileSync(eccPath);
      assert(ecc.length === 134217728, 'ECC dump size ' + ecc.length);
      same(ecc.subarray(0, MTD0_SIZE), live, 'v2 ECC first 1 MiB vs live mtd0');
      console.log('     v2 ECC: data-only 128 MiB image, first 1 MiB is byte-identical to the live mtd0 dump');
    });
  }
  if (rawPath) {
    test('v2 RAW dump: de-interleaved page data equals the live mtd0 dump, OOB is 0xFF', function () {
      const raw = fs.readFileSync(rawPath);
      const pages = MTD0_SIZE / 2048;
      assert(raw.length === 138412032, 'RAW dump size ' + raw.length);
      const data = Buffer.alloc(MTD0_SIZE);
      for (let p = 0; p < pages; p++) raw.copy(data, p * 2048, p * 2112, p * 2112 + 2048);
      same(data, live, 'de-interleaved v2 RAW data vs live mtd0');
      for (let p = 0; p < pages; p++) {
        const oob = raw.subarray(p * 2112 + 2048, (p + 1) * 2112);
        assert(oob.every(function (b) { return b === 0xFF; }), 'OOB @page ' + p + ' is not 0xFF');
      }
      console.log('     v2 RAW: ' + pages + ' pages x 2112 (2048 data + 64 OOB), OOB all 0xFF, data matches mtd0');
    });
  }
} else {
  console.log('SKIP live-dump acceptance: pass --dump <mtd0 dump> (the CI gate runs the synthetic fixture only)');
}

// ---- summary --------------------------------------------------------------

if (!keep) {
  try { fs.rmSync(TMP, { recursive: true, force: true }); } catch (e) { /* best effort */ }
} else {
  console.log('kept temp dir ' + TMP);
}
console.log('');
console.log('test_mtd0_tools: ' + passed + ' passed, ' + failed + ' failed' +
  (dumpPath ? ' (including live-dump acceptance)' : ' (synthetic fixture only)'));
if (failed) {
  failures.forEach(function (f) { console.error('  FAILED: ' + f[0] + ': ' + (f[1].stack || f[1].message)); });
  process.exit(1);
}
