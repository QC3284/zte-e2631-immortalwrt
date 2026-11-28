#!/usr/bin/env node
// SPDX-License-Identifier: GPL-2.0-or-later
// Local, offline preview server for the E4 rescue page (task-81).
// Serves the real uboot-port/failsafe/e2631-failsafe.html and mocks the HTTP
// endpoints of evidence/e4-v2-contract-design-20261128.md on 127.0.0.1 only.
// It never touches flash and never talks to a device. For UI review only.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PAGE_FILE = path.join(ROOT, 'uboot-port', 'failsafe', 'e2631-failsafe.html');
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

const backup = Buffer.alloc(BOOTLOADER_LEN, 0);
const magic = Buffer.from('128s', 'ascii');
magic.copy(backup, 0x10);
backup.writeUInt32LE(494208, 0x14);
Buffer.from('U-Boot 2027.01-rc2 (mock)', 'ascii').copy(backup, 0x800);
const BOOTLOADER_CRC = crc32(backup);
const BOOTLOADER_SHA = sha256(backup);

const PART_DEFS = {
  bootloader: { off: '0x20000', len: 655360, file: 'e2631-bootloader.bin' },
  tag: { off: '0x100000', len: 1048576, file: 'e2631-tag.bin' },
  wifi: { off: '0x200000', len: 1048576, file: 'e2631-wifi.bin' },
  usercfg: { off: '0x300000', len: 2097152, file: 'e2631-usercfg.bin' },
  defcfg: { off: '0x500000', len: 2097152, file: 'e2631-defcfg.bin' }
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
  'gatewayip', 'ipaddr', 'netmask', 'serverip', 'e2631_pocload', 'e2631_flashboot'
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
  e2631_flashboot: 'reset'
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
  if (c === 'md') return { code: 0, text: '42000000: 00000000 00000000 00000000 00000000    ................\n42000010: 00000000 00000000 00000000 00000000    ................\n' };
  if (c === 'help') return { code: 0, text: '?         - alias for \'help\'\nbootm     - boot application image from memory\nprintenv  - print environment variables\nsetenv    - set environment variables\nversion   - print monitor, compiler and linker version\n' };
  return { code: 1, text: 'Unknown command \'' + cmd + '\' - try \'help\'\n' };
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

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://' + HOST + ':' + PORT);
  try {
    if (req.method === 'GET' && u.pathname === '/') {
      const page = fs.readFileSync(PAGE_FILE);
      return send(res, 200, page, 'text/html; charset=utf-8');
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
      const esc = out.text.replace(/\\/g, '\\\\').replace(/\n/g, '\\n');
      return send(res, 200, 'result=ok\nexit=' + out.code + '\nstdout=' + esc + '\ntruncated=0\nerror=\n');
    }
    if (req.method === 'GET' && u.pathname === '/backup') {
      const part = parseQuery(u).part || 'bootloader';
      const def = PART_DEFS[part];
      if (!def) return send(res, 400, 'result=error\nerror=bad part\n');
      const m = partMeta(part);
      return send(res, 200, m.buf, 'application/octet-stream', {
        'Content-Disposition': 'attachment; filename="' + def.file + '"',
        'X-E2631-CRC32': m.crc,
        'X-E2631-SHA256': m.sha,
        'X-E2631-Offset': def.off,
        'X-E2631-Length': '0x' + def.len.toString(16).toUpperCase(),
        'X-E2631-Part': part
      });
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
      if (u.pathname === '/flash' && body.length !== BOOTLOADER_LEN) return send(res, 400, 'result=error\nerror=image size mismatch\n');
      if (u.pathname === '/firmware' && (body.length < 0x214 || body.length > 0x1BE0214)) return send(res, 400, 'result=error\nerror=package size out of range\n');
      if (sent && sent !== sha) return send(res, 400, 'result=error\nerror=sha256 mismatch\n');
      if (mode === 'write' && header(req, 'x-e2631-confirm') !== 'write') return send(res, 400, 'result=error\nerror=missing confirm header\n');
      const slotTarget = q.slot === '0' || q.slot === '1' ? q.slot : SLOTS.next_slot;
      if (mode === 'validate') {
        if (u.pathname === '/firmware') {
          return send(res, 200, ['result=ok', 'sha256=' + info.sha, 'browser_sha256=' + info.browser, 'sha_match=' + (info.browser ? 'ok' : 'absent'), 'crc32=' + info.crc, 'body_len=' + info.len, 'slot_target=' + slotTarget, 'slot_target_identity=' + SLOTS['slot' + slotTarget + '_identity'], 'guard=ok', 'guard_reason='].join('\n') + '\n');
        }
        return send(res, 200, ['result=ok', 'sha256=' + info.sha, 'browser_sha256=' + info.browser, 'sha_match=' + (info.browser ? 'ok' : 'absent'), 'crc32=' + info.crc].join('\n') + '\n');
      }
      task = {
        op: u.pathname === '/flash' ? 'flash' : 'firmware',
        mode: 'write', stage: 'erase', progress: 5, bytesDone: 0, bytesTotal: body.length,
        crc32: info.crc, sha256: info.sha, browser: info.browser, match: 'ok', result: '',
        error: '', slotTarget: slotTarget, writtenSerial: '13', version: task.version
      };
      const accept = ['result=accepted', 'sha256=' + info.sha];
      if (u.pathname === '/firmware') accept.push('slot_target=' + slotTarget, 'written_serial=13');
      return send(res, 200, accept.join('\n') + '\n');
    }
    if (req.method === 'POST' && u.pathname === '/factory') {
      if (parseQuery(u).confirm !== 'reset' || header(req, 'x-e2631-confirm') !== 'reset') return send(res, 400, 'result=error\nerror=missing confirm\n');
      task = { op: 'factory', mode: 'erase', stage: 'erase', progress: 20, bytesDone: 0, bytesTotal: 0x4a0000, crc32: '', sha256: '', browser: '', match: '', result: '', error: '', slotTarget: '', writtenSerial: '', version: task.version };
      return send(res, 200, 'result=accepted\n');
    }
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
