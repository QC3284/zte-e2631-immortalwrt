#!/usr/bin/env node
// SPDX-License-Identifier: GPL-2.0-or-later
// Local, offline preview server for the E4 rescue page.
// Serves the real uboot-port/failsafe/e2631-failsafe.html and mocks the HTTP
// endpoints of evidence/e4-v2-contract-design-20261128.md (v2.1) plus the v3
// additions of evidence/e4-v3-contract-delta-20261128.md: /sysinfo, /log,
// /integrity, /backup?part=slot0|slot1|rootfs|header, /reboot, the
// e2631_dhcp_* env keys and their /status fields. Localhost only; it never
// touches flash and never talks to a device. For UI review only.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PAGE_FILE = path.join(ROOT, 'uboot-port', 'failsafe', 'e2631-failsafe.html');
const PAGE_GZ = zlib.gzipSync(fs.readFileSync(PAGE_FILE), { level: 9 });
const HOST = '127.0.0.1';
const PORT = Number(process.env.PORT || 8787);
const MAX_BODY = 32 * 1024 * 1024;
const BOOTLOADER_LEN = 655360;

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function sha256(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}
function hex32(n) {
  return '0x' + (n >>> 0).toString(16).padStart(8, '0');
}

// Factory-package validator, mirroring e2631-fwslot.c package_load() and the
// v2 contract section 5.1. Used by the local mock so the acceptance harness can
// exercise the firmware negative matrix without a device (task-89 extension of
// the task-75 harness).
const FW_MIN = 0x214;
const FW_MAX = 0x1be0214;
const OUTER_MAGIC = Buffer.from([0x99, 0x99, 0x99, 0x99, 0x44, 0x44, 0x44, 0x44, 0x55, 0x55, 0x55, 0x55, 0xaa, 0xaa, 0xaa, 0xaa]);
const INNER_MAGIC = Buffer.from([0x33, 0x33, 0x33, 0x33, 0x66, 0x66, 0x66, 0x66, 0x99, 0x99, 0x99, 0x99, 0xcc, 0xcc, 0xcc, 0xcc]);
const FW_PRODUCT = 'ZXHN E2631 V1.0.0';
function rd32(b, o) {
  return b.readUInt32LE(o) >>> 0;
}
function pkgVerdict(buf) {
  const n = buf.length;
  if (n < FW_MIN) return { error: 'package too small' };
  if (n > FW_MAX) return { error: 'package size out of range' };
  if (!buf.subarray(0, 16).equals(OUTER_MAGIC)) return { error: 'bad outer magic' };
  const hdrOfs = 0x14 + rd32(buf, 0x10);
  const bodyOfs = hdrOfs + 0x200;
  if (bodyOfs > n) return { error: 'truncated header' };
  const hdr = buf.subarray(hdrOfs, hdrOfs + 0x200);
  if (!hdr.subarray(0xf4, 0x104).equals(INNER_MAGIC)) return { error: 'bad version header magic' };
  if (crc32(hdr.subarray(0, 0xa4)) !== rd32(hdr, 0xa4) || crc32(hdr.subarray(0, 0x1fc)) !== rd32(hdr, 0x1fc)) return { error: 'header CRC mismatch' };
  if (hdr.subarray(0x6c, 0x6c + FW_PRODUCT.length).toString('latin1') !== FW_PRODUCT) return { error: 'package is not for this product' };
  if (rd32(hdr, 0x8c) !== 0) return { error: 'package wants to update the bootloader' };
  const bodyLen = n - bodyOfs;
  if (rd32(hdr, 0x30) !== bodyLen) return { error: 'body size mismatch' };
  if (rd32(hdr, 0x4c) !== 0x700000 || rd32(hdr, 0x5c) !== 0x2300000) return { error: 'package declares different slot addresses' };
  const koff = rd32(hdr, 0x38);
  const ksz = rd32(hdr, 0x34);
  const foff = rd32(hdr, 0x44);
  const fsz = rd32(hdr, 0x40);
  if (koff + ksz > n || foff + fsz > n) return { error: 'region outside package' };
  if (crc32(buf.subarray(koff, koff + ksz)) !== rd32(hdr, 0x3c)) return { error: 'kernel CRC mismatch' };
  if (crc32(buf.subarray(foff, foff + fsz)) !== rd32(hdr, 0x48)) return { error: 'rootfs CRC mismatch' };
  return { ok: true, bodyLen };
}

const MOCK_BOOTLOADER = process.env.E2631_MOCK_BOOTLOADER || '';
let backup;
if (MOCK_BOOTLOADER) {
  backup = fs.readFileSync(MOCK_BOOTLOADER);
  if (backup.length !== BOOTLOADER_LEN) throw new Error('E2631_MOCK_BOOTLOADER must be ' + BOOTLOADER_LEN + ' bytes');
} else {
  backup = Buffer.alloc(BOOTLOADER_LEN, 0);
  const magic = Buffer.from('128s', 'ascii');
  magic.copy(backup, 0x10);
  backup.writeUInt32LE(494208, 0x14);
  Buffer.from('U-Boot 2027.01-rc2 (mock)', 'ascii').copy(backup, 0x800);
}
const BOOTLOADER_CRC = crc32(backup);
const BOOTLOADER_SHA = sha256(backup);

const PART_DEFS = {
  bootloader: { off: '0x20000', len: 655360, file: 'e2631-bootloader.bin' },
  tag: { off: '0x100000', len: 1048576, file: 'e2631-tag.bin' },
  wifi: { off: '0x200000', len: 1048576, file: 'e2631-wifi.bin' },
  usercfg: { off: '0x300000', len: 2097152, file: 'e2631-usercfg.bin' },
  defcfg: { off: '0x500000', len: 2097152, file: 'e2631-defcfg.bin' },
  // v3 whole-slot / window downloads (read-only)
  slot0: { off: '0x700000', len: 0x1c00000, file: 'e2631-slot0.bin' },
  slot1: { off: '0x2300000', len: 0x1c00000, file: 'e2631-slot1.bin' },
  rootfs: { off: '0x2700000', len: 0x1100000, file: 'e2631-rootfs.bin' },
  header: { off: '0x3800000', len: 0x20000, file: 'e2631-slot1-header.bin' }
};
const partCache = {};
function partMeta(p) {
  if (partCache[p]) return partCache[p];
  const d = PART_DEFS[p];
  let buf;
  if (p === 'bootloader') buf = backup;
  else {
    buf = Buffer.alloc(d.len, 0);
    Buffer.from('E2631 ' + p + ' mock partition', 'ascii').copy(buf, 0);
  }
  partCache[p] = { buf, crc: hex32(crc32(buf)), sha: sha256(buf) };
  return partCache[p];
}

const BACKUP_CRC = BOOTLOADER_CRC;
const BACKUP_SHA = BOOTLOADER_SHA;

const SLOTS = {
  next_slot: '1',
  next_reason: 'serial',
  slot0_valid: '1',
  slot0_intact: '1',
  slot0_identity: 'vendor',
  slot0_serial: '7',
  slot0_version: 'V1.0.0.7B5.8000',
  slot0_header_at: '0x1c60000',
  slot0_partition: 'mtd5',
  slot0_span: '0x01c00000',
  slot1_valid: '1',
  slot1_intact: '1',
  slot1_identity: 'ours',
  slot1_serial: '12',
  slot1_version: 'ImmortalWrt v1.10.0',
  slot1_header_at: '0x1580000',
  slot1_partition: 'mtd6',
  slot1_span: '0x01c00000',
  slot1_header: '0x3800000',
  bootloader_region_crc32: hex32(BACKUP_CRC)
};

const ENV_ORDER = [
  'baudrate', 'bootcmd', 'bootdelay', 'bootfile', 'console', 'ethaddr',
  'gatewayip', 'ipaddr', 'netmask', 'serverip', 'e2631_pocload', 'e2631_flashboot',
  'e2631_dhcp_ipaddr', 'e2631_dhcp_netmask', 'e2631_dhcp_pool_start', 'e2631_dhcp_pool_size'
];
const ENV_MAP = {
  baudrate: '115200',
  bootcmd: 'e2631boot',
  bootdelay: '0',
  bootfile: 'uboot.bin',
  console: 'ttyAMA0,115200n8',
  ethaddr: '00:41:71:00:00:50',
  gatewayip: '192.168.1.1',
  ipaddr: '192.168.1.1',
  netmask: '255.255.255.0',
  serverip: '192.168.1.100',
  e2631_pocload: 'tftp 0x43000000 u-boot.bin',
  e2631_flashboot: 'reset',
  e2631_dhcp_ipaddr: '192.168.1.1',
  e2631_dhcp_netmask: '255.255.255.0',
  e2631_dhcp_pool_start: '100',
  e2631_dhcp_pool_size: '101'
};
function envText() {
  const lines = ENV_ORDER.map((k) => k + '=' + ENV_MAP[k]);
  lines.push('env_size=' + ENV_ORDER.length + '/131068');
  return lines.join('\n') + '\n';
}

let task = { op: 'idle', mode: '', stage: 'idle', progress: 0, bytesDone: 0, bytesTotal: 0, crc32: '', sha256: '', browser: '', match: '', result: '', error: '', slotTarget: '', writtenSerial: '', version: 'U-Boot 2027.01-rc2 (mock)' };
const STEPS = {
  flash: [['erase', 10], ['blank', 30], ['write', 60], ['readback', 80], ['compare', 95], ['done', 100]],
  firmware: [['erase', 10], ['write', 60], ['readback', 80], ['compare', 95], ['done', 100]],
  factory: [['erase', 40], ['blank', 80], ['done', 100]],
  envwrite: [['diff', 10], ['check', 30], ['erase', 50], ['write', 70], ['readback', 85], ['verify', 95], ['done', 100]]
};
function advance() {
  if (task.stage === 'done' || task.stage === 'error' || task.stage === 'idle') return;
  const steps = STEPS[task.op] || [];
  const idx = steps.findIndex((s) => s[0] === task.stage);
  const next = steps[idx + 1];
  if (!next) return;
  task.stage = next[0];
  task.progress = next[1];
  if (task.stage === 'done') task.result = 'ok';
}
function mockConsole(cmd) {
  const parts = cmd.split(/\s+/);
  const c = parts[0];
  if (c === 'version') return { code: 0, text: '\nU-Boot 2027.01-rc2 (mock)\n\narm-linux-gnueabi-gcc\n' };
  if (c === 'printenv') {
    const k = parts[1];
    if (k) return { code: 0, text: Object.prototype.hasOwnProperty.call(ENV_MAP, k) ? k + '=' + ENV_MAP[k] : '\n## Error: "' + k + '" not defined\n' };
    return { code: 0, text: ENV_ORDER.map((x) => x + '=' + ENV_MAP[x]).join('\n') + '\n' };
  }
  if (c === 'md.b') {
    const n = parts[2] ? parseInt(parts[2], 0) : 4;
    const lines = Math.max(16, Math.min(256, Math.ceil((Number.isFinite(n) ? n : 4) / 16)));
    let text = '';
    for (let i = 0; i < lines; i++) text += (0x47f00000 + i * 16).toString(16).padStart(8, '0') + ': 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00    ................\n';
    return { code: 0, text };
  }
  if (c === 'md') return { code: 0, text: '42000000: 00000000 00000000 00000000 00000000    ................\n42000010: 00000000 00000000 00000000 00000000    ................\n' };
  if (c === 'setenv') return { code: 0, text: '' };
  if (c === 'help') return { code: 0, text: '?         - alias for \'help\'\nbootm     - boot application image from memory\nprintenv  - print environment variables\nsetenv    - set environment variables\nversion   - print monitor, compiler and linker version\n' };
  return { code: 1, text: 'Unknown command \'' + cmd + '\' - try \'help\'\n' };
}

const BOOT_LOG = [
  'U-Boot 2027.01-rc2 (mock E4 v3)',
  'Model: ZTE ZXHN E2631 (ZX279128S)',
  'DRAM:  256 MiB',
  'Core:  10 devices, 8 uclasses, devicetree: embed',
  'Loading Environment from MTD... OK',
  'In:    serial',
  'Out:   serial',
  'Err:   serial',
  'Net:   lan1',
  'e2631boot: slot0 serial 7, slot1 serial 12',
  'e2631boot: boot slot1',
  'Starting kernel ...'
].join('\n') + '\n';

function validIpv4(s) {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(s || '');
  if (!m) return false;
  return m.slice(1).every((x) => Number(x) <= 255);
}

function dhcpConfig() {
  const defaults = { ip: '192.168.1.1', netmask: '255.255.255.0', pool_start: 100, pool_size: 101 };
  const env = (k, d) => (Object.prototype.hasOwnProperty.call(ENV_MAP, k) && ENV_MAP[k] !== '' ? ENV_MAP[k] : d);
  const ip = env('e2631_dhcp_ipaddr', defaults.ip);
  const netmask = env('e2631_dhcp_netmask', defaults.netmask);
  const ps = env('e2631_dhcp_pool_start', String(defaults.pool_start));
  const pn = env('e2631_dhcp_pool_size', String(defaults.pool_size));
  const source = ['e2631_dhcp_ipaddr', 'e2631_dhcp_netmask', 'e2631_dhcp_pool_start', 'e2631_dhcp_pool_size'].some((k) => Object.prototype.hasOwnProperty.call(ENV_MAP, k)) ? 'env' : 'default';
  const warnings = [];
  let poolStart = Number(ps), poolSize = Number(pn);
  if (!validIpv4(ip)) warnings.push('bad e2631_dhcp_ipaddr');
  if (!validIpv4(netmask)) warnings.push('bad e2631_dhcp_netmask');
  if (!Number.isInteger(poolStart) || poolStart < 1 || poolStart > 254) { warnings.push('bad e2631_dhcp_pool_start'); poolStart = defaults.pool_start; }
  if (!Number.isInteger(poolSize) || poolSize < 1 || poolSize > 200) { warnings.push('bad e2631_dhcp_pool_size'); poolSize = defaults.pool_size; }
  return { ip: validIpv4(ip) ? ip : defaults.ip, netmask: validIpv4(netmask) ? netmask : defaults.netmask, poolStart, poolSize, source: warnings.length ? 'fallback' : source, warning: warnings.join(',') };
}

function statusText() {
  const s = task;
  const out = [
    'stage=' + s.stage,
    'progress=' + s.progress,
    'op=' + s.op,
    'mode=' + s.mode,
    'result=' + (s.result || (s.stage === 'error' ? 'error' : '')),
    'error=' + s.error,
    'crc32=' + s.crc32,
    'sha256=' + s.sha256,
    'browser_sha256=' + s.browser,
    'sha_match=' + s.match,
    'bytes_total=' + s.bytesTotal,
    'bytes_done=' + s.bytesDone,
    'slot_target=' + s.slotTarget,
    'written_serial=' + s.writtenSerial,
    'version=' + s.version,
    'next_slot=' + SLOTS.next_slot,
    'next_reason=' + SLOTS.next_reason,
    'bootloader_region_crc32=' + SLOTS.bootloader_region_crc32
  ];
  for (const k of ['slot0', 'slot1']) {
    for (const f of ['valid', 'intact', 'identity', 'serial', 'version']) out.push(k + '_' + f + '=' + SLOTS[k + '_' + f]);
  }
  const d = dhcpConfig();
  out.push('dhcp_ip=' + d.ip);
  out.push('dhcp_netmask=' + d.netmask);
  out.push('dhcp_pool_start=' + d.poolStart);
  out.push('dhcp_pool_size=' + d.poolSize);
  out.push('dhcp_source=' + d.source);
  out.push('dhcp_warning=' + d.warning);
  out.push('backup=' + (backupActive ? 'active' : 'idle'));
  out.push('backup_part=' + (backupActive ? backupPart : ''));
  out.push('log_bytes=' + BOOT_LOG.length);
  out.push('reboot_pending=' + (rebootPending ? '1' : '0'));
  return out.join('\n') + '\n';
}
function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let len = 0;
    req.on('data', (c) => {
      len += c.length;
      if (len > MAX_BODY) {
        reject(new Error('body too large'));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}
function parseQuery(u) {
  const q = {};
  for (const [k, v] of u.searchParams) q[k] = v;
  return q;
}
function send(res, code, body, type, extra) {
  res.writeHead(code, Object.assign({ 'Content-Type': type || 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' }, extra || {}));
  res.end(body);
}
function header(req, name) {
  const v = req.headers[name];
  return Array.isArray(v) ? v[0] : v || '';
}

let backupActive = false;
let backupPart = '';
let rebootPending = false;
function jobActive() {
  return task.stage !== 'idle' && task.stage !== 'done' && task.stage !== 'error';
}
function sendBackup(res, part) {
  const def = PART_DEFS[part];
  const m = partMeta(part);
  backupActive = true;
  backupPart = part;
  res.on('finish', () => { backupActive = false; backupPart = ''; });
  return send(res, 200, m.buf, 'application/octet-stream', {
    'Content-Disposition': 'attachment; filename="' + def.file + '"',
    'X-E2631-CRC32': m.crc,
    'X-E2631-SHA256': m.sha,
    'X-E2631-Offset': def.off,
    'X-E2631-Length': '0x' + def.len.toString(16).toUpperCase(),
    'X-E2631-Part': part,
    'Content-Length': String(m.buf.length)
  });
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://' + HOST + ':' + PORT);
  try {
    if (req.method === 'GET' && u.pathname === '/') {
      return send(res, 200, PAGE_GZ, 'text/html; charset=utf-8', { 'Content-Encoding': 'gzip' });
    }
    if (req.method === 'GET' && u.pathname === '/sysinfo') {
      const lines = [
        'result=ok',
        'version=U-Boot 2027.01-rc2 (mock E4 v3)',
        'banner=U-Boot 2027.01-rc2 (mock E4 v3)',
        'build=Nov 28 2026 - 00:00:00 +0000',
        'board=ZTE ZXHN E2631',
        'soc=ZX279128S',
        'cpu=ARM Cortex-A9',
        'dram=0x10000000',
        'dram_mb=256',
        'mtd0_size=0x100000',
        'spi_nand=spi-nand0',
        'spi_size=0x8000000',
        'spi_erasesize=0x20000',
        'spi_writesize=0x800',
        'spi_oobsize=0x40',
        'spi_id=a1a1a1a1a1',
        'sctlr=0x08c50878',
        'midr=0x410fc090',
        'clidr=0x09200003',
        'ttbr0=0x00000000',
        'vbar=0x47f00000',
        'actlr=0x00000000',
        'dacr=0x55555555',
        'pll_a9_cfg0=0x00000000',
        'pll_a9_cfg1=0x00000000',
        'top_ctrl8=0x10061fff',
        'top_clk_sel=0x00517800',
        'crm2_10=0x00000100',
        'crm_4c=0x000381ff',
        'lsp1_04=0x0001381b',
        'net_pll_cfg0=0x0004176b',
        'net_pll_cfg1=0x144fdf3b',
        'cpu_mhz=1000',
        'cpu_mhz_source=known'
      ];
      return send(res, 200, lines.join('\n') + '\n');
    }
    if (req.method === 'GET' && u.pathname === '/log') {
      const dl = parseQuery(u).download === '1';
      return send(res, 200, BOOT_LOG, 'text/plain; charset=utf-8', {
        'X-E2631-Log-Bytes': String(BOOT_LOG.length),
        ...(dl ? { 'Content-Disposition': 'attachment; filename="e2631-bootlog.txt"' } : {})
      });
    }
    if (req.method === 'POST' && u.pathname === '/integrity') {
      const expect = (parseQuery(u).expect || header(req, 'x-e2631-sha256') || '').toLowerCase();
      if (expect && !/^[0-9a-f]{64}$/.test(expect)) return send(res, 400, 'result=error\nerror=bad sha256\n');
      const crc = hex32(BOOTLOADER_CRC);
      const match = expect ? (expect === BOOTLOADER_SHA ? 'ok' : 'mismatch') : 'absent';
      const lines = ['result=ok', 'offset=0x20000', 'length=0xa0000', 'crc32=' + crc, 'sha256=' + BOOTLOADER_SHA, 'match=' + match];
      if (expect) lines.push('expected=' + expect);
      return send(res, 200, lines.join('\n') + '\n');
    }
    if (req.method === 'GET' && u.pathname === '/status') {
      advance();
      return send(res, 200, statusText());
    }
    if (req.method === 'GET' && u.pathname === '/slots') {
      const lines = ['next_slot=' + SLOTS.next_slot, 'next_reason=' + SLOTS.next_reason, 'slot0_partition=' + SLOTS.slot0_partition, 'slot0_span=' + SLOTS.slot0_span, 'slot1_partition=' + SLOTS.slot1_partition, 'slot1_span=' + SLOTS.slot1_span, 'slot1_header=' + SLOTS.slot1_header];
      for (const k of ['slot0', 'slot1']) for (const f of ['valid', 'intact', 'identity', 'serial', 'version', 'header_at']) lines.push(k + '_' + f + '=' + SLOTS[k + '_' + f]);
      return send(res, 200, lines.join('\n') + '\n');
    }
    if (req.method === 'GET' && u.pathname === '/env') return send(res, 200, envText());
    if (req.method === 'POST' && u.pathname === '/env') {
      const q = parseQuery(u);
      if (q.confirm !== 'write' || header(req, 'x-e2631-confirm') !== 'write') return send(res, 400, 'result=error\nerror=missing confirm\n');
      const key = q.key || '';
      const value = q.value === undefined ? '' : q.value;
      const writable = key === 'bootdelay' || key.indexOf('e2631_') === 0;
      if (!/^[a-z0-9_]{1,32}$/.test(key) || !writable) return send(res, 403, 'result=error\nerror=key is not writable\n');
      if (value.length > 128 || !/^[\x20-\x7e]*$/.test(value)) return send(res, 400, 'result=error\nerror=bad value\n');
      if (key === 'e2631_dhcp_ipaddr' || key === 'e2631_dhcp_netmask') {
        if (!validIpv4(value)) return send(res, 400, 'result=error\nerror=bad value\n');
      }
      if (key === 'e2631_dhcp_pool_start') {
        const n = Number(value);
        if (!Number.isInteger(n) || n < 1 || n > 254) return send(res, 400, 'result=error\nerror=bad value\n');
      }
      if (key === 'e2631_dhcp_pool_size') {
        const n = Number(value);
        if (!Number.isInteger(n) || n < 1 || n > 200) return send(res, 400, 'result=error\nerror=bad value\n');
      }
      if (Object.prototype.hasOwnProperty.call(ENV_MAP, key) && ENV_MAP[key] === value) {
        return send(res, 200, 'result=ok\nnew_crc32=' + hex32(crc32(Buffer.from(envText(), 'utf8'))) + '\nkeys=0\n');
      }
      if (!Object.prototype.hasOwnProperty.call(ENV_MAP, key)) ENV_ORDER.push(key);
      ENV_MAP[key] = value;
      const crc = hex32(crc32(Buffer.from(envText(), 'utf8')));
      task = { op: 'envwrite', mode: 'write', stage: 'diff', progress: 5, bytesDone: 1, bytesTotal: 1, crc32: crc, sha256: '', browser: '', match: '', result: '', error: '', slotTarget: '', writtenSerial: '', version: task.version };
      return send(res, 200, 'result=accepted\nnew_crc32=' + crc + '\nkeys=1\n');
    }
    if (req.method === 'POST' && u.pathname === '/console') {
      const cmd = (parseQuery(u).cmd || '').trim();
      if (!cmd || cmd.length > 256 || /[;\r\n]/.test(cmd)) return send(res, 400, 'result=error\nexit=1\nstdout=\ntruncated=0\nerror=only a single command is allowed\n');
      const out = mockConsole(cmd);
      let esc = out.text.replace(/\\/g, '\\\\').replace(/\n/g, '\\n');
      let truncated = 0;
      if (esc.length > 4096) {
        esc = esc.slice(-4096);
        truncated = 1;
      }
      return send(res, 200, 'result=ok\nexit=' + out.code + '\nstdout=' + esc + '\ntruncated=' + truncated + '\nerror=\n');
    }
    if (req.method === 'GET' && u.pathname === '/backup') {
      const part = parseQuery(u).part || 'bootloader';
      const def = PART_DEFS[part];
      if (!def) return send(res, 400, 'result=error\nerror=bad part\n');
      if (backupActive) return send(res, 409, 'result=error\nerror=busy\n');
      return sendBackup(res, part);
    }
    if (req.method === 'POST' && u.pathname === '/boot') {
      const slot = parseQuery(u).slot;
      if (slot !== '0' && slot !== '1') return send(res, 400, 'result=error\nerror=bad slot\n');
      return send(res, 200, 'result=ok\nnext_slot=' + slot + '\n');
    }
    if (req.method === 'POST' && (u.pathname === '/flash' || u.pathname === '/firmware')) {
      const q = parseQuery(u);
      const mode = q.mode === 'write' ? 'write' : 'validate';
      const body = await readBody(req);
      const declared = Number(req.headers['content-length'] || body.length);
      const sha = sha256(body);
      const sent = header(req, 'x-e2631-sha256').toLowerCase();
      const browser = sent;
      const info = { sha, crc: hex32(crc32(body)), len: body.length, browser };
      if (u.pathname === '/flash') {
        if (body.length !== BOOTLOADER_LEN) return send(res, 400, 'result=error\nerror=image size mismatch\n');
        if (sent && sent !== sha) return send(res, 400, 'result=error\nerror=sha256 mismatch\n');
        if (mode === 'write' && header(req, 'x-e2631-confirm') !== 'write') return send(res, 400, 'result=error\nerror=missing confirm header\n');
        if (mode === 'validate') {
          return send(res, 200, ['result=ok', 'sha256=' + info.sha, 'browser_sha256=' + info.browser, 'sha_match=' + (info.browser ? 'ok' : 'absent'), 'crc32=' + info.crc].join('\n') + '\n');
        }
        task = {
          op: 'flash', mode: 'write', stage: 'erase', progress: 5, bytesDone: 0, bytesTotal: body.length,
          crc32: info.crc, sha256: info.sha, browser: info.browser, match: 'ok', result: '',
          error: '', slotTarget: '', writtenSerial: '', version: task.version
        };
        return send(res, 200, 'result=accepted\nsha256=' + info.sha + '\n');
      }
      // /firmware: mirror the factory-package contract (section 5.1/5.2).
      if (q.slot && q.slot !== 'auto' && q.slot !== '0' && q.slot !== '1') return send(res, 400, 'result=error\nerror=bad slot\n');
      if (body.length < FW_MIN) return send(res, 400, 'result=error\nerror=package too small\n');
      if (body.length > FW_MAX) return send(res, 400, 'result=error\nerror=package size out of range\n');
      if (sent && sent !== sha) return send(res, 400, 'result=error\nerror=sha256 mismatch\n');
      const slotTarget = q.slot === '0' || q.slot === '1' ? q.slot : SLOTS.next_slot;
      const verdict = pkgVerdict(body);
      if (!verdict.ok) return send(res, 400, 'result=error\nerror=' + verdict.error + '\n');
      const targetIdentity = SLOTS['slot' + slotTarget + '_identity'];
      const targetIntact = SLOTS['slot' + slotTarget + '_intact'] === '1';
      if (targetIdentity === 'vendor' && targetIntact) return send(res, 400, 'result=error\nerror=refusing to overwrite a working vendor system\n');
      if (mode === 'validate') {
        return send(res, 200, ['result=ok', 'sha256=' + info.sha, 'browser_sha256=' + info.browser, 'sha_match=' + (info.browser ? 'ok' : 'absent'), 'crc32=' + info.crc, 'body_len=0x' + verdict.bodyLen.toString(16), 'slot_target=' + slotTarget, 'slot_target_identity=' + targetIdentity, 'guard=ok', 'guard_reason='].join('\n') + '\n');
      }
      if (header(req, 'x-e2631-confirm') !== 'write') return send(res, 400, 'result=error\nerror=missing confirm header\n');
      task = {
        op: 'firmware', mode: 'write', stage: 'erase', progress: 5, bytesDone: 0, bytesTotal: body.length,
        crc32: info.crc, sha256: info.sha, browser: info.browser, match: 'ok', result: '',
        error: '', slotTarget: slotTarget, writtenSerial: '13', version: task.version
      };
      return send(res, 200, ['result=accepted', 'sha256=' + info.sha, 'slot_target=' + slotTarget, 'written_serial=13'].join('\n') + '\n');
    }
    if (req.method === 'POST' && u.pathname === '/factory') {
      if (parseQuery(u).confirm !== 'reset' || header(req, 'x-e2631-confirm') !== 'reset') return send(res, 400, 'result=error\nerror=missing confirm\n');
      task = { op: 'factory', mode: 'erase', stage: 'erase', progress: 20, bytesDone: 0, bytesTotal: 0x4a0000, crc32: '', sha256: '', browser: '', match: '', result: '', error: '', slotTarget: '', writtenSerial: '', version: task.version };
      return send(res, 200, 'result=accepted\n');
    }
    if (req.method === 'POST' && u.pathname === '/reboot') {
      if (header(req, 'x-e2631-confirm') !== 'reboot') return send(res, 400, 'result=error\nerror=missing confirm\n');
      if (jobActive() || backupActive) return send(res, 409, 'result=error\nerror=busy\n');
      rebootPending = true;
      return send(res, 200, 'result=accepted\nreboot=1\n');
    }
    const KNOWN = new Set(['/', '/status', '/slots', '/env', '/backup', '/sysinfo', '/log', '/integrity', '/reboot', '/console', '/boot', '/flash', '/firmware', '/factory']);
    if (KNOWN.has(u.pathname)) return send(res, 405, 'result=error\nerror=method not allowed\n');
    send(res, 404, 'result=error\nerror=not found\n');
  } catch (e) {
    send(res, 500, 'result=error\nerror=' + String(e.message || e).replace(/\s+/g, ' ').slice(0, 120) + '\n');
  }
});

server.listen(PORT, HOST, () => {
  console.log('E4 rescue page mock: http://' + HOST + ':' + PORT + '/');
  console.log('Page file: ' + path.relative(ROOT, PAGE_FILE));
  console.log('Mock only: no flash access, no device. Ctrl-C to stop.');
});
