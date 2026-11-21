// Patch the E2631 vendor U-Boot console password (mtd0 + 0x61F80, 20 bytes)
// and verify a candidate password against it.
//
//   node tools/patch-uboot.mjs password --in <mtd0|-> --password <new> --out <mtd0>
//          [--print] [--json]
//   node tools/patch-uboot.mjs check-password --in <mtd0> --password <candidate>
//
// U-逆1 found the stored value is an unsalted SHA1 digest of the console
// password; the enable flag is a u32 at 0x61F94 and is left unchanged here.
// Only the 20 digest bytes are written - the patch tool refuses any other
// offset, and the tests assert that nothing else moves.
//
// Offline only: the input and output are files; nothing here talks to a device.

import fs from 'node:fs';
import {
  PASSWORD_OFF, PASSWORD_SIZE, PASSWORD_FLAG_OFF, PASSWORD_MAX_BYTES,
  assertMtd0, readU32, sha1, sha256Hex, diffRanges,
} from './lib/mtd0.mjs';

function usage() {
  console.error([
    'usage:',
    '  patch-uboot.mjs password --in <mtd0|-> --password <new> --out <mtd0> [--print] [--json]',
    '  patch-uboot.mjs check-password --in <mtd0> --password <candidate>',
    '',
    'The digest is an unsalted SHA1 at mtd0 0x61F80; passwords are limited to',
    PASSWORD_MAX_BYTES + ' bytes (the vendor prints "passwd is too long"; the exact cut is untested).',
  ].join('\n'));
  process.exit(2);
}

const argv = process.argv.slice(2);
const command = argv.shift();
if (!command) usage();
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
function read(file, what) {
  try { return file === '-' ? fs.readFileSync(0) : fs.readFileSync(file); }
  catch (e) { throw new Error('cannot read ' + what + ': ' + file + ' (' + e.code + ')'); }
}
function passwordBytes(value) {
  const bytes = Buffer.from(value, 'utf8');
  if (bytes.length === 0) throw new Error('password must not be empty');
  if (bytes.length > PASSWORD_MAX_BYTES) {
    throw new Error('password is ' + bytes.length + ' bytes; the kit limit is ' + PASSWORD_MAX_BYTES +
      ' (the vendor string only says "passwd is too long")');
  }
  return bytes;
}

try {
  const json = flag('json');
  if (command === 'password') {
    const inPath = opt('in');
    const password = opt('password');
    const outPath = opt('out');
    const printOnly = flag('print');
    if (!inPath || password === undefined) usage();
    if (!printOnly && !outPath) usage();
    const dump = read(inPath, 'mtd0 dump');
    assertMtd0(dump);
    const newDigest = sha1(passwordBytes(password));
    const before = Buffer.from(dump.subarray(PASSWORD_OFF, PASSWORD_OFF + PASSWORD_SIZE));
    const patched = Buffer.from(dump);
    newDigest.copy(patched, PASSWORD_OFF);
    const ranges = diffRanges(before, newDigest, 0);
    const changed = ranges.reduce(function (n, r) { return n + r.length; }, 0);
    console.log('password digest: sha1, unsalted, ' + PASSWORD_SIZE + ' bytes -> ' + newDigest.toString('hex'));
    console.log('mtd0 + 0x' + PASSWORD_OFF.toString(16) + ':');
    console.log('  before ' + before.toString('hex'));
    console.log('  after  ' + newDigest.toString('hex'));
    console.log('  changed bytes: ' + changed + ' of ' + PASSWORD_SIZE);
    console.log('enable flag at 0x' + PASSWORD_FLAG_OFF.toString(16) + ': 0x' +
      readU32(dump, PASSWORD_FLAG_OFF).toString(16) + ' (left unchanged)');
    if (!printOnly) {
      fs.writeFileSync(outPath, patched);
      console.log('wrote ' + outPath + ' (' + patched.length + ' bytes, sha256 ' + sha256Hex(patched) + ')');
      console.log('full-image bytes changed: ' + diffRanges(dump, patched, 0).length + ' range(s)');
    }
    if (json) {
      console.log(JSON.stringify({
        offset: '0x' + PASSWORD_OFF.toString(16), digestBytes: PASSWORD_SIZE,
        before: before.toString('hex'), after: newDigest.toString('hex'), changedBytes: changed,
        flagValue: '0x' + readU32(dump, PASSWORD_FLAG_OFF).toString(16),
        wrote: printOnly ? null : outPath,
      }, null, 2));
    }
  } else if (command === 'check-password') {
    const inPath = opt('in');
    const password = opt('password');
    if (!inPath || password === undefined) usage();
    const dump = read(inPath, 'mtd0 dump');
    assertMtd0(dump);
    const stored = Buffer.from(dump.subarray(PASSWORD_OFF, PASSWORD_OFF + PASSWORD_SIZE));
    const candidate = sha1(passwordBytes(password));
    const match = Buffer.compare(stored, candidate) === 0;
    console.log('stored   ' + stored.toString('hex'));
    console.log('candidate ' + candidate.toString('hex'));
    if (!match) {
      console.error('NO MATCH: the stored digest does not belong to this password');
      process.exit(1);
    }
    console.log('MATCH: the stored digest is SHA1 of this password');
    if (json) console.log(JSON.stringify({ stored: stored.toString('hex'), match: true }, null, 2));
  } else {
    usage();
  }
  if (argv.length) throw new Error('unknown arguments: ' + argv.join(' '));
} catch (e) {
  console.error('patch-uboot: ' + e.message);
  process.exit(1);
}
