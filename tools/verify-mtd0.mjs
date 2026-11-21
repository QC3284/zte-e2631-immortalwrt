// Compare a read-back mtd0 image against a baseline, or check its sha256.
//
//   node tools/verify-mtd0.mjs --file <dump> [--sha256 <hex>] [--baseline <dump>]
//          [--offset <hex>] [--length <hex>] [--json]
//
// The read-back protocol in evidence/p2-uboot-research-20261121.md section 4.5
// requires comparing what a flash tool wrote against what the device reads
// back, and the baseline dump's sha256 (docs/救砖手册-2026-11-15.md section 2.3)
// to decide whether a rollback image is the original.
//
// Offline only: this tool reads two files, never a device.

import fs from 'node:fs';
import { sha256Hex, diffRanges, hexAt } from './lib/mtd0.mjs';

function usage() {
  console.error([
    'usage:',
    '  verify-mtd0.mjs --file <dump> [--sha256 <hex>] [--baseline <dump>]',
    '                  [--offset <hex>] [--length <hex>] [--json]',
    '',
    'With none of --sha256/--baseline it prints size and sha256.',
    '--offset/--length (hex, 0x optional) limit the baseline comparison.',
  ].join('\n'));
  process.exit(2);
}

const argv = process.argv.slice(2);
function opt(name) {
  const i = argv.indexOf('--' + name);
  if (i < 0) return undefined;
  const value = argv[i + 1];
  if (value === undefined || value.startsWith('--')) throw new Error('--' + name + ' needs a value');
  argv.splice(i, 2);
  return value;
}
function flag(name) {
  const i = argv.indexOf('--' + name);
  if (i < 0) return false;
  argv.splice(i, 1);
  return true;
}
function hex(value, name) {
  if (!/^(0x)?[0-9a-fA-F]+$/.test(value)) throw new Error('--' + name + ' expects hex, got ' + JSON.stringify(value));
  return parseInt(value.replace(/^0x/i, ''), 16);
}
function read(file, what) {
  try { return fs.readFileSync(file); }
  catch (e) { throw new Error('cannot read ' + what + ': ' + file + ' (' + e.code + ')'); }
}

try {
  const json = flag('json');
  const filePath = opt('file');
  if (!filePath) usage();
  const expectSha = opt('sha256');
  const baselinePath = opt('baseline');
  const rawOffset = opt('offset');
  const rawLength = opt('length');
  const offset = rawOffset === undefined ? 0 : hex(rawOffset, 'offset');
  const length = rawLength === undefined ? undefined : hex(rawLength, 'length');
  if (argv.length) throw new Error('unknown arguments: ' + argv.join(' '));
  const dump = read(filePath, 'dump');
  const actualSha = sha256Hex(dump);
  let failed = false;
  console.log('file: ' + filePath);
  console.log('size: ' + dump.length + ' bytes (0x' + dump.length.toString(16) + ')');
  console.log('sha256: ' + actualSha);
  if (expectSha) {
    const want = expectSha.trim().toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(want)) throw new Error('--sha256 expects 64 hex digits, got ' + JSON.stringify(expectSha));
    if (want !== actualSha) {
      console.error('MISMATCH sha256: expected ' + want + ', got ' + actualSha);
      failed = true;
    } else {
      console.log('OK sha256 matches ' + want);
    }
  }
  if (baselinePath) {
    const base = read(baselinePath, 'baseline dump');
    if (base.length !== dump.length) {
      throw new Error('baseline is ' + base.length + ' bytes and dump is ' + dump.length + '; sizes must match');
    }
    const end = length === undefined ? base.length : Math.min(base.length, offset + length);
    if (offset > base.length) throw new Error('--offset 0x' + offset.toString(16) + ' is past the end of the image');
    const a = dump.subarray(offset, end);
    const b = base.subarray(offset, end);
    const ranges = diffRanges(a, b);
    console.log('baseline: ' + baselinePath);
    console.log('compared: 0x' + offset.toString(16) + '..0x' + end.toString(16) + ' (' + (end - offset) + ' bytes)');
    if (ranges.length === 0) {
      console.log('OK: identical over the compared range');
    } else {
      failed = true;
      const total = ranges.reduce(function (n, r) { return n + r.length; }, 0);
      console.error('DIFF: ' + ranges.length + ' range(s), ' + total + ' byte(s) differ');
      ranges.forEach(function (r) {
        const shown = Math.min(32, r.length);
        console.error('  0x' + (offset + r.offset).toString(16) + ' +' + r.length +
          '  dump ' + hexAt(a, r.offset, shown) + (shown < r.length ? '...' : '') +
          '  base ' + hexAt(b, r.offset, shown) + (shown < r.length ? '...' : ''));
      });
    }
    if (json) {
      console.log(JSON.stringify({
        file: filePath, baseline: baselinePath, offset: offset, length: end - offset,
        ranges: ranges.map(function (r) { return { offset: offset + r.offset, length: r.length }; }),
        identical: ranges.length === 0,
      }, null, 2));
    }
  }
  if (!expectSha && !baselinePath) {
    console.log('(no --sha256 and no --baseline given; nothing compared)');
  }
  if (json && !baselinePath) console.log(JSON.stringify({ file: filePath, size: dump.length, sha256: actualSha }, null, 2));
  if (failed) process.exit(1);
} catch (e) {
  console.error('verify-mtd0: ' + e.message);
  process.exit(1);
}
