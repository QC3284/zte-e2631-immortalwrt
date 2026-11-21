#!/usr/bin/env python3
"""A1 banner acceptance session driver for task-49.

Modes:
  --preflight   no device interaction; validate artifact, capture chain, scripts.
  (default)     full session: pause capture chain -> start serial hub -> wait for a
                user cold power-on -> vendor console -> xmodem load of the fixed
                A1 u-boot.bin -> crc32 + full md.b compare -> go -> banner ->
                prompt alive -> recovery -> device health -> restore capture chain.

Zero flash writes: this driver only sends console commands xmodem/md.b/crc32/go/
help/echo/reset over serial; it never issues nand write/erase/upgrade commands.
"""
import argparse, base64, hashlib, json, os, re, signal, subprocess, sys, time, zlib

P3 = "/home/qc233/zte/e2631-p3"
SOCK = "/tmp/e2631-p3.sock"
HUB = P3 + "/serialhub.py"
TTY = "/dev/ttyCH343USB0"
CAPTURE_SUP = "/home/qc233/zte/e2631-capture/capture-supervisor-002.sh"
CAPTURE_BW = "/home/qc233/zte/e2631-capture/serial-bootwatch.mjs"
RESTORE = P3 + "/restore_capture.sh"
HEALTH = P3 + "/a1_banner_health.sh"
VENDOR_PW_FILE = P3 + "/vendor_pw.txt"
ART_DEFAULT = ("/home/qc233/zte/e2631-t5-artifacts/uboot-a1-fix-44875722425/"
               "files/e2631-uboot-a1-44875722425/u-boot.bin")
EXP_SHA = "5310f998824a4c52dd46a18315ac0b989f2545f632477a5769ad5f2e5b4dc742"
EXP_SIZE = 347824
BANNER_TOKEN = "U-Boot 2027.01-rc2-g4910ee2045bd"
OUT_DEFAULT = P3 + "/a1-banner-accept"
LOG = None


def log(msg):
    line = time.strftime("%H:%M:%S") + " " + str(msg)
    print(line, flush=True)
    if LOG:
        with open(LOG, "a") as f:
            f.write(line + "\n")


def sh(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def pgrep(pat):
    rc, out, _ = sh("pgrep -f " + repr(pat))
    return [int(x) for x in out.split() if x.isdigit()]


def tty_holders():
    rc, out, _ = sh("fuser " + TTY + " 2>/dev/null")
    return [int(x) for x in re.findall(r"\d+", out)]


def ctl_call(req, timeout=60.0):
    import socket as _s
    s = _s.socket(_s.AF_UNIX, _s.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(SOCK)
    f = s.makefile("rwb")
    f.write((json.dumps(req) + "\n").encode())
    f.flush()
    line = f.readline()
    s.close()
    return json.loads(line.decode())


class Console:
    def __init__(self):
        self.off = ctl_call({"op": "read", "offset": 0})["offset"]
        self.pending = b""
        self.history = bytearray()

    def read(self):
        r = ctl_call({"op": "read", "offset": self.off})
        data = base64.b64decode(r["data_b64"])
        self.off = r["offset"]
        if data:
            self.history.extend(data)
        return data

    def drain(self):
        self.pending += self.read()

    def wait(self, pattern, timeout):
        pat = re.compile(pattern)
        deadline = time.time() + timeout
        while True:
            m = pat.search(self.pending)
            if m:
                head = bytes(self.pending[:m.end()])
                self.pending = self.pending[m.end():]
                return head
            data = self.read()
            if data:
                self.pending += data
                continue
            if time.time() > deadline:
                return None
            time.sleep(0.02)

    def wait_until_quiet(self, quiet=0.4, max_wait=10.0):
        deadline = time.time() + max_wait
        last = time.time()
        while time.time() < deadline:
            data = self.read()
            if data:
                self.pending += data
                last = time.time()
            elif time.time() - last > quiet:
                return
            else:
                time.sleep(0.02)

    def send(self, data):
        ctl_call({"op": "send", "data_b64": base64.b64encode(data).decode()})

    def cmd(self, text, timeout=60):
        self.pending = b""
        self.send((text + "\r").encode())
        return self.wait(rb"=>", timeout)

    def md_read(self, text, base_addr, n, timeout=120):
        """Issue an md.b command and read until the real console prompt line.

        Waiting for b"=>" anywhere is unsafe: the md.b ASCII column renders data
        bytes 0x3d 0x3e as "=>" and truncates the capture (bug found in the
        2026-11-21 combined run). The prompt is always preceded by CRLF, so wait
        for b"\r\n=> " instead, then parse. Returns (text, data, gaps).
        """
        self.pending = b""
        self.send((text + "\r").encode())
        pat = re.compile(rb"\r\n=> ")
        deadline = time.time() + timeout
        while True:
            m = pat.search(self.pending)
            if m:
                head = bytes(self.pending[:m.end()])
                self.pending = bytes(self.pending[m.end():])
                parsed, gaps = parse_md(head.decode("latin-1"), base_addr)
                return head.decode("latin-1"), parsed, gaps
            data = self.read()
            if data:
                self.pending += data
                continue
            if time.time() > deadline:
                parsed, gaps = parse_md(self.pending.decode("latin-1"), base_addr)
                return self.pending.decode("latin-1"), parsed, gaps
            time.sleep(0.02)


def parse_md(text, base):
    """Parse vendor U-Boot md.b output.

    The greedy predecessor swallowed hex-looking characters out of the ASCII
    column (row length became > 16), shifted expect and dropped real rows, which
    produced fake mismatches in the 2026-11-21 combined run. Take exactly the
    first 16 whitespace-separated tokens after the address prefix.
    """
    data = bytearray()
    expect = base
    gaps = 0
    row_pat = re.compile(r"^([0-9a-fA-F]{8}): ")
    byte_pat = re.compile(r"^[0-9a-fA-F]{2}$")
    for line in text.splitlines():
        m = row_pat.match(line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        toks = line[m.end():].split()
        row = bytes(int(t, 16) for t in toks[:16] if byte_pat.match(t))
        if not row or len(row) > 16:
            gaps += 1
            continue
        if addr != expect:
            gaps += 1
            if addr < expect:
                continue
            data.extend(b"\x00" * (addr - expect))
        data.extend(row)
        expect = addr + len(row)
    return bytes(data), gaps


def artifact_facts(path):
    raw = open(path, "rb").read()
    return {
        "path": path,
        "size": len(raw),
        "size_ok": len(raw) == EXP_SIZE,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sha_ok": hashlib.sha256(raw).hexdigest() == EXP_SHA,
        "entry_bytes": raw[:8].hex(),
        "banner_offset": raw.find(BANNER_TOKEN.encode()),
        "banner_token": BANNER_TOKEN,
        "crc32": format(zlib.crc32(raw) & 0xFFFFFFFF, "08x"),
        "crc32_hex": format(zlib.crc32(raw) & 0xFFFFFFFF, "08x"),
    }


def pause_capture():
    state = {"supervisor_pids": pgrep("capture-supervisor-002.sh"),
             "bootwatch_pids": pgrep("serial-bootwatch.mjs"),
             "tty_holders": tty_holders()}
    for pid in state["supervisor_pids"] + state["bootwatch_pids"] + state["tty_holders"]:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 12
    while time.time() < deadline and tty_holders():
        time.sleep(0.3)
    state["tty_holders_after"] = tty_holders()
    state["free"] = not state["tty_holders_after"]
    log("capture paused: " + json.dumps(state))
    return state


def start_hub(log_path):
    if os.path.exists(SOCK):
        try:
            os.unlink(SOCK)
        except OSError:
            pass
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    cmd = ["nohup", "setsid", "python3", HUB, "--log", log_path, "--socket", SOCK]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            ctl_call({"op": "ping"}, timeout=2)
            log("serial hub started pid=" + str(p.pid) + " log=" + log_path)
            return p.pid
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("serial hub did not start")


def stop_hub():
    try:
        ctl_call({"op": "stop"}, timeout=5)
    except Exception:
        pass
    for pid in pgrep("serialhub.py"):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(1.0)


def restore_capture():
    rc, out, err = sh(RESTORE, timeout=60)
    time.sleep(1.0)
    state = {"restore_rc": rc,
             "supervisor_pids": pgrep("capture-supervisor-002.sh"),
             "bootwatch_pids": pgrep("serial-bootwatch.mjs"),
             "tty_holders": tty_holders()}
    rc2, tail, _ = sh("tail -2 /home/qc233/zte/e2631-serial-capture-002-events.log")
    state["events_tail"] = tail
    state["ok"] = bool(state["supervisor_pids"] and state["bootwatch_pids"] and state["tty_holders"])
    log("capture restore: " + json.dumps(state))
    return state


def enter_vendor_console(c, timeout):
    c.drain()
    m = c.wait(rb"Press 1 means entering boot mode", timeout)
    if not m:
        return {"ok": False, "error": "no cold-boot Press-1 prompt"}
    log("cold-boot prompt caught; sending 1")
    c.send(b"1")
    if not c.wait(rb"bootmode password", 30):
        return {"ok": False, "error": "no bootmode password prompt"}
    pw = open(VENDOR_PW_FILE).read().strip()
    entered = None
    for attempt in range(4):
        c.send((pw + "\r").encode())
        deadline = time.time() + 20
        name = None
        while time.time() < deadline:
            if re.search(rb"Hit any key to stop autoboot", c.pending):
                name = "autoboot"
                break
            if re.search(rb"Hit 1 to upgrade software version", c.pending):
                name = "upgrade"
                break
            if re.search(rb"passwd is (error|too long)", c.pending):
                name = "bad"
                break
            if re.search(rb"Please input bootmode password", c.pending):
                name = "again"
                break
            data = c.read()
            if data:
                c.pending += data
                continue
            time.sleep(0.02)
        log("vendor password attempt " + str(attempt + 1) + " -> " + str(name))
        if name in ("autoboot", "upgrade"):
            entered = name
            break
    if not entered:
        return {"ok": False, "error": "vendor password failed"}
    stopped = False
    deadline = time.time() + 15
    while time.time() < deadline:
        if re.search(rb"Hit any key to stop autoboot", c.pending):
            c.send(b" ")
            stopped = True
            break
        data = c.read()
        if data:
            c.pending += data
            continue
        time.sleep(0.01)
    if not c.wait(rb"=>", 25):
        return {"ok": False, "error": "no vendor prompt after autoboot stop"}
    out = c.cmd("version", 20)
    stock = bool(out and b"U-Boot 2013.04" in out)
    return {"ok": stock, "autoboot_stopped": stopped, "stock_banner": stock}


def xmodem_load(c, path):
    # The hub sends the "xmodem" command and then immediately hunts for the
    # receiver probe in one operation: a host-side gap here let the vendor
    # receiver time out on 2026-11-21 (frames were echoed as console input).
    last = None
    for attempt in range(3):
        c.pending = b""
        t0 = time.time()
        try:
            res = ctl_call({"op": "xmodem", "path": path, "block_size": 1024,
                            "first_timeout": 60.0,
                            "command": "xmodem 0x43000000\r"}, timeout=600.0)
        except Exception as exc:  # noqa: BLE001
            res = {"ok": False, "error": repr(exc)}
        res["elapsed_s"] = round(time.time() - t0, 1)
        res["attempt"] = attempt + 1
        if res.get("ok"):
            c.wait_until_quiet(0.5, 10)
            return res
        last = res
        log("xmodem attempt %d failed: %s" % (attempt + 1, json.dumps(res)[:220]))
        # re-sync the console: CAN CAN aborts a stuck xmodem receiver (the vendor
        # receiver waits forever for frames), then CR returns to the prompt
        try:
            c.send(b"\x18\x18")
            time.sleep(0.3)
            c.send(b"\x03")
            time.sleep(0.2)
            c.pending = b""
            c.send(b"\r")
            c.wait(rb"=>", 15)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0)
    return last


def crc32_check(c, data):
    out = c.cmd("crc32 0x43000000 0x%X" % len(data), 60)
    text = (out or b"").decode("latin-1")
    m = re.search(r"==>\s*([0-9a-fA-F]{8})", text)
    expect = format(zlib.crc32(data) & 0xFFFFFFFF, "08x")
    got = m.group(1).lower() if m else None
    return {"available": bool(m), "device_crc32": got, "host_crc32": expect,
            "ok": got == expect, "raw": text[-300:]}


def md_full_compare(c, data, chunk, progress=None):
    base = 0x43000000
    mismatches = 0
    first_bad = None
    gaps_total = 0
    got = bytearray()
    chunks = []
    off = 0
    while off < len(data):
        n = min(chunk, len(data) - off)
        t0 = time.time()
        out = c.cmd("md.b 0x%08X 0x%X" % (base + off, n), 180)
        text = (out or b"").decode("latin-1")
        seg, gaps = parse_md(text, base + off)
        gaps_total += gaps
        seg = seg[:n]
        if len(seg) < n:
            seg = seg + b"\x00" * (n - len(seg))
            gaps_total += 1
        bad = sum(1 for a, b in zip(seg, data[off:off + n]) if a != b)
        if bad:
            if first_bad is None:
                for i, (a, b) in enumerate(zip(seg, data[off:off + n])):
                    if a != b:
                        first_bad = off + i
                        break
        mismatches += bad
        got.extend(seg)
        ent = {"offset": off, "size": n, "mismatches": bad,
               "elapsed_s": round(time.time() - t0, 1)}
        chunks.append(ent)
        if progress:
            progress(ent)
        off += n
        if mismatches > 200:
            break
    return {"ok": mismatches == 0 and gaps_total == 0,
            "bytes_compared": len(got), "mismatches": mismatches,
            "first_mismatch_offset": first_bad, "gaps": gaps_total,
            "chunks": chunks}


def go_for_banner(c, timeout=120):
    c.pending = b""
    c.send(b"go 0x43000000\r")
    acc = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = c.read()
        if data:
            acc += data
            c.pending += data
            if BANNER_TOKEN.encode() in acc:
                break
            continue
        time.sleep(0.02)
    token = BANNER_TOKEN.encode() in acc
    c.wait_until_quiet(0.5, 15)
    text = acc.decode("latin-1")
    prompt = bool(c.wait(rb"=>", 60))
    return {"banner_token_seen": token, "prompt_seen": prompt,
            "banner_line": next((l for l in text.splitlines() if BANNER_TOKEN in l), None),
            "raw_tail": text[-3000:]}


def prompt_alive(c):
    results = {}
    c.pending = b""
    c.send(b"\r")
    results["bare_cr_prompt"] = bool(c.wait(rb"=>", 20))
    for cmd in ["help", "version", "echo A1-PROMPT-ALIVE", "crc32 0x43000000 0x100"]:
        out = c.cmd(cmd, 30)
        text = (out or b"").decode("latin-1")
        results[cmd] = {"ok": bool(out), "unknown": "Unknown command" in text,
                        "tail": text[-600:]}
    results["alive"] = bool(results["bare_cr_prompt"] and
                            (results["help"]["ok"] or results["echo A1-PROMPT-ALIVE"]["ok"]))
    return results


def try_reset(c):
    c.pending = b""
    c.send(b"reset\r")
    got = c.wait(rb"=>", 15)
    text = (got or b"").decode("latin-1")
    unknown = "Unknown command" in text
    return {"attempted": True, "unknown_command": unknown, "prompt_back": bool(got),
            "tail": text[-300:]}


def wait_linux(c, timeout):
    pat = re.compile(rb"e2631-wifi-boot|ImmortalWrt|login:|Please press Enter")
    deadline = time.time() + timeout
    start = len(c.history)
    while time.time() < deadline:
        if pat.search(c.pending):
            return {"ok": True, "marker": True}
        data = c.read()
        if data:
            c.pending += data
            continue
        if pat.search(bytes(c.history[start:])):
            return {"ok": True, "marker": True}
        time.sleep(0.2)
    return {"ok": False, "marker": False}


def run_preflight(args):
    facts = artifact_facts(args.artifact)
    cap = {"supervisor_pids": pgrep("capture-supervisor-002.sh"),
           "bootwatch_pids": pgrep("serial-bootwatch.mjs"),
           "tty_holders": tty_holders()}
    rc, ev, _ = sh("tail -3 /home/qc233/zte/e2631-serial-capture-002-events.log")
    scripts = {p: os.path.exists(p) for p in [HUB, RESTORE, HEALTH, VENDOR_PW_FILE, CAPTURE_SUP, CAPTURE_BW]}
    pw_mode = oct(os.stat(VENDOR_PW_FILE).st_mode & 0o777) if os.path.exists(VENDOR_PW_FILE) else None
    rc2, df, _ = sh("df -h " + P3 + " | tail -1")
    rep = {"mode": "preflight", "artifact": facts, "capture_chain": cap,
           "capture_events_tail": ev, "scripts": scripts, "vendor_pw_mode": pw_mode,
           "disk": df, "banner_token": BANNER_TOKEN, "expected_sha": EXP_SHA,
           "ok": facts["sha_ok"] and facts["size_ok"] and facts["banner_offset"] > 0
                 and cap["supervisor_pids"] and cap["bootwatch_pids"] and cap["tty_holders"]
                 and all(scripts.values()) and pw_mode == "0o600"}
    os.makedirs(args.out_dir, exist_ok=True)
    with open(args.out_dir + "/preflight.json", "w") as f:
        json.dump(rep, f, indent=1)
    log("PREFLIGHT " + ("OK" if rep["ok"] else "ISSUES"))
    log(json.dumps(rep, indent=1))
    return 0 if rep["ok"] else 1


def run_session(args):
    global LOG
    os.makedirs(args.out_dir, exist_ok=True)
    LOG = args.out_dir + "/session-driver.log"
    results = {"mode": "session", "artifact": artifact_facts(args.artifact),
               "expected_banner_token": BANNER_TOKEN, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    data = open(args.artifact, "rb").read()
    hub_pid = None
    try:
        results["capture_before"] = pause_capture()
        if not results["capture_before"]["free"]:
            raise RuntimeError("tty still busy after pausing the capture chain")
        hub_pid = start_hub(args.out_dir + "/serial.log")
        results["hub_pid"] = hub_pid
        c = Console()
        log("READY FOR USER POWER CYCLE (cold boot); waiting up to %ss" % args.entry_timeout)
        entry = enter_vendor_console(c, args.entry_timeout)
        results["vendor_entry"] = entry
        if not entry.get("ok"):
            raise RuntimeError("vendor console entry failed: " + json.dumps(entry))
        log("vendor console ready (stock U-Boot confirmed)")
        load = xmodem_load(c, args.artifact)
        results["xmodem"] = load
        if not load.get("ok"):
            raise RuntimeError("xmodem failed: " + json.dumps(load)[:400])
        log("xmodem done: " + json.dumps({k: load.get(k) for k in ("mode", "blocks", "bytes_sent", "elapsed_s", "eot_acked")}))
        results["crc32_check"] = crc32_check(c, data)
        log("crc32 check: " + json.dumps(results["crc32_check"])[:300])
        results["md_compare"] = md_full_compare(
            c, data, args.chunk,
            progress=lambda e: log("md compare %d/%d bytes, mismatches=%d, %.1fs" %
                                   (e["offset"] + e["size"], len(data), e["mismatches"], e["elapsed_s"])))
        log("md compare: " + json.dumps({k: results["md_compare"][k] for k in
                                         ("ok", "bytes_compared", "mismatches", "first_mismatch_offset", "gaps")}))
        if not results["md_compare"]["ok"]:
            raise RuntimeError("md.b compare mismatch; refusing to go")
        go = go_for_banner(c, args.banner_timeout)
        results["go"] = go
        log("go: banner_token_seen=%s prompt_seen=%s" % (go["banner_token_seen"], go["prompt_seen"]))
        results["prompt_alive"] = prompt_alive(c)
        log("prompt alive: " + json.dumps({k: results["prompt_alive"][k] for k in ("alive", "bare_cr_prompt")}))
        results["reset"] = try_reset(c)
        log("reset attempt: " + json.dumps(results["reset"])[:300])
        log("POWER CYCLE REQUIRED for recovery: unplug the E2631 for >=5 s, then replug; "
            "waiting up to %ss for Linux to come back" % args.recover_timeout)
        results["recovery"] = wait_linux(c, args.recover_timeout)
        log("recovery Linux marker: " + json.dumps(results["recovery"]))
        results["transcript"] = "serial.log"
        open(args.out_dir + "/console-transcript.txt", "wb").write(bytes(c.history))
    except Exception as exc:  # noqa: BLE001
        results["error"] = str(exc)
        log("SESSION ERROR: " + str(exc))
    finally:
        try:
            stop_hub()
        except Exception:
            pass
        results["capture_after"] = restore_capture()
        try:
            rc, out, _ = sh("bash " + HEALTH, timeout=120)
            results["health_rc"] = rc
            results["health"] = out[-4000:]
            open(args.out_dir + "/health.txt", "w").write(out + "\n" + "_" * 20 + "\nrc=" + str(rc))
        except Exception as exc:  # noqa: BLE001
            results["health_error"] = str(exc)
        results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        go = results.get("go", {})
        pa = results.get("prompt_alive", {})
        md = results.get("md_compare", {})
        results["verdict"] = ("GREEN" if
                              results["artifact"]["sha_ok"] and results.get("xmodem", {}).get("eot_acked")
                              and md.get("ok") and go.get("banner_token_seen")
                              and pa.get("alive") and results["capture_after"].get("ok")
                              else ("FAIL" if results.get("error") else "INCOMPLETE"))
        with open(args.out_dir + "/session-results.json", "w") as f:
            json.dump(results, f, indent=1)
        log("VERDICT " + results["verdict"] + " (results in " + args.out_dir + "/session-results.json)")
    return 0 if results["verdict"] == "GREEN" else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--artifact", default=ART_DEFAULT)
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    ap.add_argument("--chunk", type=lambda v: int(v, 0), default=0x4000)
    ap.add_argument("--entry-timeout", type=int, default=600)
    ap.add_argument("--banner-timeout", type=int, default=120)
    ap.add_argument("--recover-timeout", type=int, default=900)
    ap.add_argument("--vendor-pw-file", default=VENDOR_PW_FILE)
    args = ap.parse_args()
    if args.preflight:
        return run_preflight(args)
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())
