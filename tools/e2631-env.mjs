// Read, rebuild and verify the E2631 U-Boot env block (mtd0 0xC0000, 128 KiB).
//
//   node tools/e2631-env.mjs dump   --dump <mtd0> [--out <text>] [--json] [--allow-bad]
//   node tools/e2631-env.mjs build  --in <text> --out <env-block.bin>
//                                   [--template <mtd0> --full-mtd0 <out>]
//   node tools/e2631-env.mjs verify --dump <mtd0>
//   node tools/e2631-env.mjs check  --dump <mtd0>
//
// The block is [u32 LE CRC32][0x1FFFC data]; the CRC32 covers the data area
// only (same algorithm and layout as U-Boot 2013.04 and mainline env/mtd.c).
// Data is canonical key=value entries, each NUL-terminated, then zero padding.
// "dump --out" + "build --in" therefore round-trips the live block byte for
// byte; "check" proves it without writing anything.
//
// Offline only: nothing here touches a device.

import fs from 'node:fs';
import {
  ENV_OFF, ENV_BLOCK_SIZE, ENV_DATA_SIZE, envParse, envEncode, envToText, envFromText,
  assertMtd0, sha256Hex,
} from './lib/mtd0.mjs';

function usage() {
  console.error([
    'usage:',
    '  e2631-env.mjs dump   --dump <mtd0> [--out <text>] [--json] [--allow-bad]',
    '  e2631-env.mjs build  --in <text> --out <env-block.bin> [--template <mtd0> --full-mtd0 <out>]',
    '  e2631-env.mjs verify --dump <mtd0>',
    '  e2631-env.mjs check  --dump <mtd0>',
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
  try { return fs.readFileSync(file); }
  catch (e) { throw new Error('cannot read ' + what + ': ' + file + ' (' + e.code + ')'); }
}
function envFromDump(dumpPath) {
  const dump = read(dumpPath, 'mtd0 dump');
  assertMtd0(dump);
  return { dump, block: Buffer.from(dump.subarray(ENV_OFF, ENV_OFF + ENV_BLOCK_SIZE)) };
}

try {
  const json = flag('json');
  if (command === 'dump') {
    const dumpPath = opt('dump');
    const outPath = opt('out');
    const allowBad = flag('allow-bad');
    if (!dumpPath) usage();
    const pair = envFromDump(dumpPath);
    const env = envParse(pair.block);
    if (!env.crcOk && !allowBad) {
      throw new Error('env CRC mismatch: stored 0x' + env.storedCrc.toString(16) +
        ', computed 0x' + env.computedCrc.toString(16) + ' (use --allow-bad to inspect anyway)');
    }
    console.log('env: ' + env.entries.length + ' entries, CRC stored 0x' + env.storedCrc.toString(16) +
      ', computed 0x' + env.computedCrc.toString(16) + ', ' + (env.crcOk ? 'OK' : 'MISMATCH'));
    if (outPath) {
      fs.writeFileSync(outPath, envToText(env.entries));
      console.log('wrote ' + outPath + ' (' + envToText(env.entries).length + ' bytes)');
    } else if (!json) {
      process.stdout.write(envToText(env.entries));
    }
    if (json) {
      console.log(JSON.stringify({
        entries: env.entries, storedCrc: env.storedCrc, computedCrc: env.computedCrc, crcOk: env.crcOk,
        dataBytes: ENV_DATA_SIZE,
      }, null, 2));
    }
  } else if (command === 'build') {
    const inPath = opt('in');
    const outPath = opt('out');
    const templatePath = opt('template');
    const fullPath = opt('full-mtd0');
    if (!inPath || !outPath) usage();
    if (fullPath && !templatePath) throw new Error('--full-mtd0 needs --template <mtd0>');
    const entries = envFromText(read(inPath, 'env text').toString('utf8'));
    const block = envEncode(entries);
    fs.writeFileSync(outPath, block);
    console.log('env: ' + entries.length + ' entries, CRC 0x' + block.readUInt32LE(0).toString(16));
    console.log('wrote ' + outPath + ' (0x' + block.length.toString(16) + ' bytes, sha256 ' + sha256Hex(block) + ')');
    if (fullPath) {
      const template = read(templatePath, 'template mtd0');
      assertMtd0(template);
      const full = Buffer.from(template);
      block.copy(full, ENV_OFF);
      fs.writeFileSync(fullPath, full);
      console.log('wrote ' + fullPath + ' (full mtd0, sha256 ' + sha256Hex(full) + ')');
    }
  } else if (command === 'verify') {
    const dumpPath = opt('dump');
    if (!dumpPath) usage();
    const env = envParse(envFromDump(dumpPath).block);
    console.log('stored CRC 0x' + env.storedCrc.toString(16) + ', computed 0x' + env.computedCrc.toString(16) +
      ', entries ' + env.entries.length);
    if (!env.crcOk) {
      console.error('FAIL: env CRC mismatch');
      process.exit(1);
    }
    console.log('OK: env CRC matches');
  } else if (command === 'check') {
    const dumpPath = opt('dump');
    if (!dumpPath) usage();
    const pair = envFromDump(dumpPath);
    const env = envParse(pair.block);
    if (!env.crcOk) throw new Error('env CRC mismatch: stored 0x' + env.storedCrc.toString(16) + ', computed 0x' + env.computedCrc.toString(16));
    const rebuilt = envEncode(env.entries);
    if (Buffer.compare(rebuilt, pair.block) !== 0) {
      console.error('FAIL: dump + rebuild differs from the live env block');
      process.exit(1);
    }
    console.log('OK: env dump + rebuild is byte-identical (0x' + ENV_BLOCK_SIZE.toString(16) +
      ' bytes, ' + env.entries.length + ' entries, CRC 0x' + env.storedCrc.toString(16) + ')');
  } else {
    usage();
  }
  if (argv.length) throw new Error('unknown arguments: ' + argv.join(' '));
} catch (e) {
  console.error('e2631-env: ' + e.message);
  process.exit(1);
}
