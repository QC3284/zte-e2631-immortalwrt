#!/usr/bin/env python3
"""Single-reader serial hub for the E2631 P3 session.

Owns /dev/ttyCH343USB0, appends every byte to a raw log, and serves a tiny
JSON-line control socket so separate agent steps can drive the console without
ever opening the tty twice. Also implements the XMODEM sender so the vendor
U-Boot console can receive u-boot.bin without any network wiring.
"""
import argparse, base64, binascii, json, os, socket, sys, threading, time
import serial


class Hub:
    def __init__(self, port, log_path, sock_path, baud=115200):
        self.port = port
        self.log_path = log_path
        self.sock_path = sock_path
        self.baud = baud
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.xf_active = threading.Event()
        self.reader_idle = threading.Event()
        self.reader_idle.set()
        self.ser = serial.Serial(port, baud, timeout=0.05, exclusive=True)
        self.logf = open(log_path, "ab", buffering=0)

    def reader(self):
        while not self.stop.is_set():
            if self.xf_active.is_set():
                # tell xmodem_send that no read() is in flight before it touches
                # the port: concurrent reads on one tty raise
                # "device reports readiness to read but returned no data"
                self.reader_idle.set()
                time.sleep(0.01)
                continue
            self.reader_idle.clear()
            try:
                data = self.ser.read(4096)
            except Exception as e:  # noqa: BLE001
                data = b""
                time.sleep(0.05)
            if not data:
                continue
            with self.lock:
                self.buf.extend(data)
                self.logf.write(data)

    def send(self, data):
        self.ser.write(data)
        self.ser.flush()

    def read_from(self, offset):
        with self.lock:
            total = len(self.buf)
            offset = max(0, min(offset, total))
            chunk = bytes(self.buf[offset:])
        return offset, total, chunk

    def xmodem_send(self, path, block_size=128, first_timeout=60.0, ack_timeout=20.0, max_retry=12,
                    command=None):
        payload = open(path, "rb").read()
        if block_size == 1024:
            soh = b"\x02"
        else:
            block_size = 128
            soh = b"\x01"
        self.xf_active.set()
        try:
            # wait for the reader thread to leave read() so we never read the tty
            # from two threads at once
            self.reader_idle.clear()
            self.reader_idle.wait(1.0)
            # drain anything already buffered, then issue the xmodem command here so
            # there is no host-side gap before we start looking for the C/NAK probe
            # (a gap made the vendor receiver time out and echo frames as console
            # input during the 2026-11-21 attach-mode attempt).
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass
            if command:
                self.send(command.encode())
            mode = None
            deadline = time.time() + first_timeout
            probe_log = b""
            while time.time() < deadline:
                b = self.ser.read(1)
                if not b:
                    continue
                probe_log += b
                if b == b"C":
                    mode = "crc"
                    break
                if b == b"\x15":
                    mode = "checksum"
                    break
            if mode is None:
                return {"ok": False, "error": "no xmodem probe (C/NAK) within %.0fs" % first_timeout,
                        "probe_b64": base64.b64encode(probe_log).decode()}
            nblocks = (len(payload) + block_size - 1) // block_size
            pad = nblocks * block_size - len(payload)
            seq = 0
            sent = 0
            retries = 0
            start = time.time()
            for i in range(nblocks):
                chunk = payload[i * block_size:(i + 1) * block_size]
                if len(chunk) < block_size:
                    chunk = chunk + b"\x1a" * (block_size - len(chunk))
                seq = (i + 1) & 0xFF
                frame = bytes([soh[0], seq, 0xFF - seq]) + chunk
                if mode == "crc":
                    crc = binascii.crc_hqx(chunk, 0).to_bytes(2, "big")
                    frame += crc
                else:
                    frame += bytes([sum(chunk) & 0xFF])
                while True:
                    self.send(frame)
                    r = self.ser.read(1)
                    if not r:
                        r = self.ser.read(1)
                    if r == b"\x06":
                        sent += len(chunk)
                        retries = 0
                        break
                    if r == b"\x15" or r == b"C":
                        retries += 1
                        if retries > max_retry:
                            return {"ok": False, "error": "too many NAKs at block %d" % (i + 1),
                                    "blocks_sent": i, "bytes_sent": sent}
                        continue
                    if r == b"\x18":
                        return {"ok": False, "error": "receiver CAN at block %d" % (i + 1),
                                "blocks_sent": i, "bytes_sent": sent}
                    # unknown byte (maybe CAN sequence continuation) -> retry once
                    retries += 1
                    if retries > max_retry * 2:
                        return {"ok": False, "error": "unexpected reply %r at block %d" % (r, i + 1),
                                "blocks_sent": i, "bytes_sent": sent}
            # EOT handshake
            eot_tries = 0
            while eot_tries < 5:
                self.send(b"\x04")
                r = self.ser.read(1)
                if r == b"\x06":
                    break
                if r == b"\x18":
                    break
                eot_tries += 1
            time.sleep(0.5)
            tail = b""
            deadline = time.time() + 2.0
            while time.time() < deadline:
                b = self.ser.read(4096)
                if b:
                    tail += b
            return {"ok": True, "mode": mode, "file_size": len(payload), "block_size": block_size,
                    "blocks": nblocks, "pad": pad, "bytes_sent": len(payload),
                    "elapsed_s": round(time.time() - start, 1),
                    "eot_acked": r == b"\x06", "tail_b64": base64.b64encode(tail).decode()}
        finally:
            self.xf_active.clear()

    def handle(self, req):
        op = req.get("op")
        if op == "ping":
            with self.lock:
                n = len(self.buf)
            return {"ok": True, "offset": n}
        if op == "read":
            off, total, chunk = self.read_from(int(req.get("offset", 0)))
            return {"ok": True, "offset": total, "data_b64": base64.b64encode(chunk).decode()}
        if op == "send":
            data = base64.b64decode(req["data_b64"])
            self.send(data)
            return {"ok": True, "sent": len(data)}
        if op == "xmodem":
            res = self.xmodem_send(req["path"], int(req.get("block_size", 128)),
                                   float(req.get("first_timeout", 60.0)),
                                   float(req.get("ack_timeout", 20.0)),
                                   command=req.get("command"))
            return res
        if op == "stop":
            self.stop.set()
            return {"ok": True}
        return {"ok": False, "error": "unknown op %r" % (op,)}

    def serve(self):
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.sock_path)
        os.chmod(self.sock_path, 0o600)
        srv.listen(4)
        srv.settimeout(0.5)
        while not self.stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                f = conn.makefile("rwb")
                line = f.readline()
                if not line:
                    continue
                try:
                    req = json.loads(line.decode())
                    resp = self.handle(req)
                except Exception as e:  # noqa: BLE001
                    resp = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
                f.write((json.dumps(resp) + "\n").encode())
                f.flush()
        try:
            srv.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyCH343USB0")
    ap.add_argument("--log", default="/home/qc233/zte/e2631-p3/serial-raw.log")
    ap.add_argument("--socket", default="/tmp/e2631-p3.sock")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()
    hub = Hub(args.port, args.log, args.socket, args.baud)
    th = threading.Thread(target=hub.reader, daemon=True)
    th.start()
    try:
        hub.serve()
    finally:
        hub.stop.set()
        time.sleep(0.2)
        try:
            hub.ser.close()
        except Exception:
            pass
        hub.logf.close()


if __name__ == "__main__":
    main()
