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
const BACKUP_CRC = crc32(backup);
const BACKUP_SHA = sha256(backup);

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

const ENV_TEXT = [
  'baudrate=115200',
  'bootcmd=e2631boot',
  'bootdelay=0',
  'bootfile=uboot.bin',
  'console=ttyAMA0,115200n8',
  'ethaddr=00:41:71:00:00:50',
  'gatewayip=192.168.1.1',
  'ipaddr=192.168.1.1',
  'netmask=255.255.255.0',
  'serverip=192.168.1.100',
  'e2631_pocload=tftp 0x43000000 u-boot.bin',
  'e2631_flashboot=reset',
  'env_size=642/131068'
].join('\n') + '\n';

let task = { op: 'idle', mode: '', stage: 'idle', progress: 0, bytesDone: 0, bytesTotal: 0, crc32: '', sha256: '', browser: '', match: '', result: '', error: '', slotTarget: '', writtenSerial: '', version: 'U-Boot 2027.01-rc2 (mock)' };
const STEPS = {
  flash: [['erase', 10], ['blank', 30], ['write', 60], ['readback', 80], ['compare', 95], ['done', 100]],
  firmware: [['erase', 10], ['write', 60], ['readback', 80], ['compare', 95], ['done', 100]],
  factory: [['erase', 40], ['blank', 80], ['done', 100]]
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
    if (req.method === 'GET' && u.pathname === '/env') return send(res, 200, ENV_TEXT);
    if (req.method === 'GET' && u.pathname === '/backup') {
      return send(res, 200, backup, 'application/octet-stream', {
        'Content-Disposition': 'attachment; filename="e2631-uboot-region.bin"',
        'X-E2631-CRC32': hex32(BACKUP_CRC),
        'X-E2631-SHA256': BACKUP_SHA,
        'X-E2631-Offset': '0x20000',
        'X-E2631-Length': '0xA0000'
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
