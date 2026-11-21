// Shared constants and byte-level helpers for the E2631 U-Boot area tools.
//
// The facts encoded here were measured in evidence/uboot-re-20261115.md (U-逆1)
// and re-checked against the live mtd0 dump in
// evidence/p2-uboot-research-20261121.md:
//
//   mtd0 + 0x20000   U-Boot header block, 0x800 bytes, magic "128s" at +0x10
//   mtd0 + 0x20800   payload, length is the u32 LE at header +0x14
//   payload max      0x9F800: 0x20800 + len must not reach the env at 0xC0000
//   mtd0 + 0xC0000   env block [u32 LE CRC32][0x1FFFC data]; CRC covers the data
//   mtd0 + 0x61F80   console-password SHA1 digest (20 bytes, unsalted)
//
// secondboot checks only the "128s" magic before copying; it does not check a
// CRC or a signature, so the header block is copied byte for byte and only the
// length field and the payload are written here.
//
// Everything is offline: these helpers accept and return Buffers only.

import crypto from 'node:crypto';

export const MTD0_SIZE = 0x100000;
export const UBOOT_OFF = 0x20000;
export const HDR_BLOCK_SIZE = 0x800;
export const PAYLOAD_OFF = UBOOT_OFF + HDR_BLOCK_SIZE;
export const PAYLOAD_MAX = 0x9F800;
export const UBOOT_REGION_SIZE = 0xA0000; // 0x20000 .. 0xC0000
export const ENV_OFF = 0xC0000;
export const ENV_BLOCK_SIZE = 0x20000;
export const ENV_DATA_SIZE = ENV_BLOCK_SIZE - 4;
export const MAGIC_OFF = 0x10;
export const MAGIC_U32 = 0x73383231;
export const LEN_OFF = 0x14;
export const DIGEST_OFF = 0x2D4;
export const DIGEST_SIZE = 32;
export const TAIL_SIZE = 64;
export const PASSWORD_OFF = 0x61F80;
export const PASSWORD_SIZE = 20;
export const PASSWORD_FLAG_OFF = 0x61F94;
// The vendor image prints "passwd is too long"; where exactly it cuts is not
// tested, so 16 bytes is the conservative limit this kit enforces.
export const PASSWORD_MAX_BYTES = 16;

const CRC_TABLE = (function () {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(buf) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}

export function sha1(buf) {
  return crypto.createHash('sha1').update(buf).digest();
}

export function sha256Hex(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

export function readU32(buf, off) {
  return buf.readUInt32LE(off);
}

export function writeU32(buf, off, value) {
  buf.writeUInt32LE(value >>> 0, off);
}

function assertBuffer(buf, size, what) {
  if (!Buffer.isBuffer(buf)) throw new Error(what + ': expected a Buffer, got ' + typeof buf);
  if (size !== undefined && buf.length !== size) {
    throw new Error(what + ': expected ' + size + ' bytes, got ' + buf.length);
  }
}

export function assertMtd0(dump) {
  assertBuffer(dump, MTD0_SIZE, 'mtd0 dump');
  const magic = readU32(dump, UBOOT_OFF + MAGIC_OFF);
  if (magic !== MAGIC_U32) {
    throw new Error('mtd0 dump: no "128s" magic at 0x' + (UBOOT_OFF + MAGIC_OFF).toString(16));
  }
}

// Decode the U-Boot area of a full mtd0 dump. The tail marker (64 bytes at
// 0x20800 + len) is optional; tailErased reports an all-0xFF (erased) tail.
export function mtd0Uboot(dump) {
  assertMtd0(dump);
  const declaredLen = readU32(dump, UBOOT_OFF + LEN_OFF);
  if (declaredLen > PAYLOAD_MAX) {
    throw new Error('declared payload length 0x' + declaredLen.toString(16) +
      ' exceeds the 0x' + PAYLOAD_MAX.toString(16) + ' limit');
  }
  const payloadEnd = PAYLOAD_OFF + declaredLen;
  const tailAvailable = payloadEnd + TAIL_SIZE <= ENV_OFF;
  const tail = tailAvailable ? Buffer.from(dump.subarray(payloadEnd, payloadEnd + TAIL_SIZE)) : null;
  return {
    header: Buffer.from(dump.subarray(UBOOT_OFF, UBOOT_OFF + HDR_BLOCK_SIZE)),
    declaredLen,
    payload: Buffer.from(dump.subarray(PAYLOAD_OFF, payloadEnd)),
    tail,
    tailErased: tail === null || tail.every(function (b) { return b === 0xFF; }),
    digest: Buffer.from(dump.subarray(UBOOT_OFF + DIGEST_OFF, UBOOT_OFF + DIGEST_OFF + DIGEST_SIZE)),
  };
}

// Build the 0xA0000-byte U-Boot region (mtd0 0x20000 .. 0xC0000) from a
// template dump: the original header block is copied byte for byte, +0x14 is
// set to the payload length, the payload follows at 0x800, and an optional
// 64-byte tail marker follows the payload. The rest of the region is erased
// (0xFF), which is what the vendor image leaves there too.
export function buildUbootRegion(templateDump, payload, tail) {
  assertMtd0(templateDump);
  assertBuffer(payload, undefined, 'payload');
  if (payload.length > PAYLOAD_MAX) {
    throw new Error('payload 0x' + payload.length.toString(16) + ' exceeds the 0x' +
      PAYLOAD_MAX.toString(16) + ' limit (the env starts at 0x' + ENV_OFF.toString(16) + ')');
  }
  if (tail !== undefined && tail !== null) {
    assertBuffer(tail, TAIL_SIZE, 'tail block');
    if (HDR_BLOCK_SIZE + payload.length + TAIL_SIZE > UBOOT_REGION_SIZE) {
      throw new Error('payload + 64-byte tail does not fit in the 0x' +
        UBOOT_REGION_SIZE.toString(16) + ' image area');
    }
  }
  const region = Buffer.alloc(UBOOT_REGION_SIZE, 0xFF);
  templateDump.copy(region, 0, UBOOT_OFF, UBOOT_OFF + HDR_BLOCK_SIZE);
  writeU32(region, LEN_OFF, payload.length);
  payload.copy(region, HDR_BLOCK_SIZE);
  if (tail !== undefined && tail !== null) tail.copy(region, HDR_BLOCK_SIZE + payload.length);
  return region;
}

export function buildFullMtd0(templateDump, payload, tail) {
  assertBuffer(templateDump, MTD0_SIZE, 'mtd0 template');
  const out = Buffer.from(templateDump);
  buildUbootRegion(templateDump, payload, tail).copy(out, UBOOT_OFF);
  return out;
}

// Parse the env block. The data area must be canonical: key=value entries,
// each NUL-terminated, then zero padding to 0x1FFFC. Anything else is refused
// instead of guessed at.
export function envParse(block) {
  assertBuffer(block, ENV_BLOCK_SIZE, 'env block');
  const storedCrc = readU32(block, 0);
  const data = Buffer.from(block.subarray(4, 4 + ENV_DATA_SIZE));
  const computedCrc = crc32(data);
  const entries = [];
  let off = 0;
  while (off < data.length && data[off] !== 0) {
    const end = data.indexOf(0, off);
    if (end < 0) throw new Error('env data: unterminated entry at offset 0x' + off.toString(16));
    const text = data.subarray(off, end).toString('utf8');
    const eq = text.indexOf('=');
    if (eq <= 0) throw new Error('env data: malformed entry at offset 0x' + off.toString(16) + ': ' + JSON.stringify(text));
    entries.push([text.slice(0, eq), text.slice(eq + 1)]);
    off = end + 1;
  }
  for (let i = off; i < data.length; i++) {
    if (data[i] !== 0) throw new Error('env data: unexpected bytes after the last entry at offset 0x' + i.toString(16));
  }
  return { storedCrc, computedCrc, crcOk: storedCrc === computedCrc, entries, data };
}

// Encode entries back into a 0x20000-byte env block with a LE CRC32.
export function envEncode(entries) {
  if (!Array.isArray(entries)) throw new Error('env entries: expected an array');
  const data = Buffer.alloc(ENV_DATA_SIZE, 0);
  let off = 0;
  entries.forEach(function (entry) {
    const key = entry[0];
    const value = entry[1];
    if (typeof key !== 'string' || !/^[A-Za-z0-9_.-]+$/.test(key)) throw new Error('env entries: bad key ' + JSON.stringify(key));
    if (typeof value !== 'string') throw new Error('env entries: bad value for ' + key);
    if (value.indexOf('\u0000') >= 0) throw new Error('env entries: NUL in value for ' + key);
    const line = Buffer.from(key + '=' + value, 'utf8');
    if (off + line.length + 1 > ENV_DATA_SIZE) throw new Error('env entries: data exceeds 0x' + ENV_DATA_SIZE.toString(16) + ' bytes');
    line.copy(data, off);
    off += line.length + 1;
  });
  const block = Buffer.alloc(ENV_BLOCK_SIZE, 0);
  writeU32(block, 0, crc32(data));
  data.copy(block, 4);
  return block;
}

export function envToText(entries) {
  return entries.map(function (e) { return e[0] + '=' + e[1]; }).join('\n') + '\n';
}

export function envFromText(text) {
  const entries = [];
  text.split(/\r?\n/).forEach(function (line, index) {
    if (line === '' || line[0] === '#') return;
    const eq = line.indexOf('=');
    if (eq <= 0) throw new Error('env text line ' + (index + 1) + ': expected key=value, got ' + JSON.stringify(line));
    entries.push([line.slice(0, eq), line.slice(eq + 1)]);
  });
  return entries;
}

// Byte ranges that differ between two equal-length buffers. Ranges closer than
// the merge gap are reported as one, so a 20-byte password patch is one range
// rather than four.
export function diffRanges(a, b, mergeGap) {
  assertBuffer(a, b.length, 'diff right side');
  if (!Buffer.isBuffer(b)) throw new Error('diff: expected Buffers');
  const gap = mergeGap === undefined ? 8 : mergeGap;
  const ranges = [];
  let start = -1;
  let last = -1;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) {
      if (start < 0) start = i;
      else if (i - last - 1 > gap) {
        ranges.push({ offset: start, length: last - start + 1 });
        start = i;
      }
      last = i;
    }
  }
  if (start >= 0) ranges.push({ offset: start, length: last - start + 1 });
  return ranges;
}

export function hexAt(buf, offset, length) {
  const end = Math.min(buf.length, offset + length);
  return buf.subarray(offset, end).toString('hex');
}
