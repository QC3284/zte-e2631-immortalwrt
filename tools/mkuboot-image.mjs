// Build, unpack and round-trip-check the E2631 U-Boot area of mtd0.
//
//   node tools/mkuboot-image.mjs unpack --dump <mtd0> --payload <out>
//          [--header <out>] [--tail <out>] [--json]
//   node tools/mkuboot-image.mjs build --dump <template-mtd0> --payload <file>
//          --out <region.bin> [--tail <file>] [--full-mtd0 <out>] [--json]
//   node tools/mkuboot-image.mjs check --dump <mtd0>
//
// The image is the U-Boot area only: mtd0 0x20000 .. 0xC0000 (0xA0000 bytes).
// The 0x800 header block is copied from the template dump byte for byte; only
// +0x14 (u32 LE payload length) changes. The payload goes at 0x20800, an
// optional 64-byte tail marker follows it, and the rest stays erased (0xFF).
// secondboot checks only the "128s" magic, so no CRC or signature is computed.
//
// Offline only: nothing here touches a device.

import fs from 'node:fs';
import {
  buildUbootRegion, buildFullMtd0, mtd0Uboot, sha256Hex,
  UBOOT_OFF, UBOOT_REGION_SIZE, PAYLOAD_MAX, ENV_OFF, PAYLOAD_OFF,
} from './lib/mtd0.mjs';

function usage() {
  console.error([
    'usage:',
    '  mkuboot-image.mjs unpack --dump <mtd0> --payload <out> [--header <out>] [--tail <out>] [--json]',
    '  mkuboot-image.mjs build  --dump <template-mtd0> --payload <file> --out <region.bin>',
    '                           [--tail <file>] [--full-mtd0 <out>] [--json]',
    '  mkuboot-image.mjs check  --dump <mtd0>',
    '',
    'The image area is mtd0 0x20000..0xC0000; payload max 0x9F800 bytes.',
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
function save(file, buf) {
  fs.writeFileSync(file, buf);
  console.log('wrote ' + file + ' (' + buf.length + ' bytes, sha256 ' + sha256Hex(buf) + ')');
}

try {
  const json = flag('json');
  if (command === 'unpack') {
    const dumpPath = opt('dump');
    const payloadOut = opt('payload');
    const headerOut = opt('header');
    const tailOut = opt('tail');
    if (!dumpPath || !payloadOut) usage();
    const dump = read(dumpPath, 'mtd0 dump');
    const image = mtd0Uboot(dump);
    save(payloadOut, image.payload);
    console.log('payload: 0x' + image.payload.length.toString(16) + ' bytes, starts at mtd0 0x' +
      PAYLOAD_OFF.toString(16) + ', sha256 ' + sha256Hex(image.payload));
    if (headerOut) {
      save(headerOut, image.header);
      console.log('header: 0x800 bytes, sha256 ' + sha256Hex(image.header));
    }
    if (tailOut) {
      if (image.tailErased) {
        console.log('tail: absent (all 0xFF at mtd0 0x' + (PAYLOAD_OFF + image.declaredLen).toString(16) + '), not written');
      } else {
        save(tailOut, image.tail);
        console.log('tail: 64 bytes at mtd0 0x' + (PAYLOAD_OFF + image.declaredLen).toString(16));
      }
    }
    if (json) {
      console.log(JSON.stringify({
        payloadLength: image.payload.length,
        payloadSha256: sha256Hex(image.payload),
        headerSha256: sha256Hex(image.header),
        tailPresent: !image.tailErased,
        declaredLength: image.declaredLen,
      }, null, 2));
    }
  } else if (command === 'build') {
    const dumpPath = opt('dump');
    const payloadPath = opt('payload');
    const outPath = opt('out');
    const tailPath = opt('tail');
    const fullPath = opt('full-mtd0');
    if (!dumpPath || !payloadPath || !outPath) usage();
    const template = read(dumpPath, 'template mtd0');
    const payload = read(payloadPath, 'payload');
    const tail = tailPath ? read(tailPath, 'tail block') : undefined;
    const region = buildUbootRegion(template, payload, tail);
    fs.writeFileSync(outPath, region);
    console.log('payload: 0x' + payload.length.toString(16) + ' bytes, sha256 ' + sha256Hex(payload));
    console.log('declared length at header +0x14: 0x' + payload.length.toString(16));
    console.log('wrote ' + outPath + ' (0x' + region.length.toString(16) + ' bytes, sha256 ' + sha256Hex(region) + ')');
    if (fullPath) {
      const full = buildFullMtd0(template, payload, tail);
      fs.writeFileSync(fullPath, full);
      console.log('wrote ' + fullPath + ' (full mtd0, sha256 ' + sha256Hex(full) + ')');
    }
    if (json) {
      console.log(JSON.stringify({
        regionBytes: region.length, regionSha256: sha256Hex(region),
        payloadLength: payload.length, payloadMax: PAYLOAD_MAX,
        payloadEnd: '0x' + (PAYLOAD_OFF + payload.length).toString(16),
        envOffset: '0x' + ENV_OFF.toString(16),
      }, null, 2));
    }
  } else if (command === 'check') {
    const dumpPath = opt('dump');
    if (!dumpPath) usage();
    const dump = read(dumpPath, 'mtd0 dump');
    const image = mtd0Uboot(dump);
    const repacked = buildUbootRegion(dump, image.payload, image.tailErased ? null : image.tail);
    const region = dump.subarray(UBOOT_OFF, UBOOT_OFF + UBOOT_REGION_SIZE);
    if (Buffer.compare(repacked, region) !== 0) {
      console.error('FAIL: repacked U-Boot area differs from the dump');
      process.exit(1);
    }
    console.log('OK: unpack + build is byte-identical over mtd0 0x' + UBOOT_OFF.toString(16) +
      '..0x' + ENV_OFF.toString(16) + ' (0x' + UBOOT_REGION_SIZE.toString(16) + ' bytes)');
    console.log('    payload 0x' + image.declaredLen.toString(16) + ' bytes, sha256 ' + sha256Hex(image.payload));
    console.log('    tail marker: ' + (image.tailErased ? 'absent (erased)' : 'present at mtd0 0x' +
      (PAYLOAD_OFF + image.declaredLen).toString(16)));
  } else {
    usage();
  }
  if (argv.length) throw new Error('unknown arguments: ' + argv.join(' '));
} catch (e) {
  console.error('mkuboot-image: ' + e.message);
  process.exit(1);
}
