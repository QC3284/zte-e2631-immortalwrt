#!/usr/bin/env python3
"""Passive true-cold-boot capture for the flashed patch-0034 U-Boot (task-79 gate).
Reads the serial capture log only; no console input, no flash operation.
After Linux is up, does a read-only SSH postcheck."""
import json, os, re, sys, time
sys.path.insert(0, "/home/qc233/zte/e2631-p3")
sys.path.insert(0, "/home/qc233/zte/e2631-p3/e2")
import b1_env_session as b1
import e2_session as e2s

LOG = "/home/qc233/zte/e2631-serial-boot-002.log"
OUT = "/home/qc233/zte/e2631-p3/e2/task79-coldboot/run-1"
BANNER = "U-Boot 2027.01-rc2-g1673d5c89c7b"
MARKERS = [
    ("bootrom", "Boot SPI NAND"),
    ("secondboot", "start read secondboot"),
    ("banner", BANNER),
    ("env_ok", "Loading Environment from MTD"),
    ("e2631boot", "e2631boot: slot0"),
    ("kernel", "Starting kernel"),
    ("init", "Run /sbin/init as init process"),
    ("linux", "Please press Enter"),
    ("mt7916", "e2631-wifi-boot: MT7916 ready"),
    ("wifi_done", "automatic Wi-Fi initialization complete"),
]
PANIC = ["Kernel panic", "Oops", "data abort", "prefetch abort", "undefined instruction", "Resetting CPU"]
HEALTH_CMD = ("echo MTD0=$(sha256sum /dev/mtd0 | cut -d' ' -f1); "
              "echo REGION=$(dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d' ' -f1); "
              "echo ENV=$(dd if=/dev/mtd0 bs=4096 skip=192 count=32 2>/dev/null | sha256sum | cut -d' ' -f1); "
              "echo SECONDBOOT=$(dd if=/dev/mtd0 bs=4096 skip=0 count=32 2>/dev/null | sha256sum | cut -d' ' -f1); "
              "echo TAIL=$(dd if=/dev/mtd0 bs=4096 skip=224 count=32 2>/dev/null | sha256sum | cut -d' ' -f1); "
              "echo UPTIME=$(cut -d' ' -f1 /proc/uptime); echo PANICS=$(dmesg | grep -ci -E 'panic|Oops' || true); "
              "echo MT7916=$(dmesg | grep -c 'e2631-wifi-boot: MT7916 ready' || true); "
              "echo WIFI=$(dmesg | grep -c 'automatic Wi-Fi initialization complete' || true); "
              "echo VERSION=$(cat /etc/e2631-version); echo KERNEL=$(uname -r); "
              "echo FWSLOT=$(e2631-fwslot info -j 2>/dev/null | tr -d '\\n' | head -c 500)")

def log(m):
    line = time.strftime("%H:%M:%S ") + m
    print(line, flush=True)
    open(OUT + "/capture.log", "a").write(line + "\n")

def parse(out):
    d = {}
    for line in (out or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def main():
    os.makedirs(OUT, exist_ok=True)
    start_off = os.path.getsize(LOG)
    res = {"log": LOG, "start_offset": start_off, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "markers": {}, "panics": [], "health": None, "verdict": None}
    log("watching %s from offset %d; cut power when ready" % (LOG, start_off))
    off = start_off
    seg = b""
    seen = set()
    deadline = time.time() + 1800
    while time.time() < deadline:
        size = os.path.getsize(LOG)
        if size < off:
            log("log rotated/shrunk; restart from 0")
            off = 0
        if size > off:
            with open(LOG, "rb") as f:
                f.seek(off)
                chunk = f.read(size - off)
            off = size
            seg += chunk
            txt = chunk.decode("latin-1", "replace")
            for name, pat in MARKERS:
                if name not in seen and pat in txt:
                    seen.add(name)
                    res["markers"][name] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                    if name == "kernel":
                        res["kernel_at"] = time.time()
                    log("MARKER " + name)
            for p in PANIC:
                if p in txt and p not in res["panics"]:
                    res["panics"].append(p)
                    log("PANIC MARKER " + p)
        if "linux" in seen:
            break
        if "kernel" in seen and time.time() > res.get("kernel_at", time.time()) + 90:
            log("kernel marker seen but no console marker after 90s; proceeding to health")
            break
    open(OUT + "/serial-segment.bin", "wb").write(seg)
    open(OUT + "/serial-segment.txt", "wb").write(seg.replace(b"\r", b""))
    res["segment_bytes"] = len(seg)
    # read-only postcheck with retries
    b1.make_askpass()
    health = {}
    attempts = []
    end = time.time() + 300
    while time.time() < end:
        try:
            b1.ensure_direct_link()
            r = e2s.ssh(HEALTH_CMD, 90)
            d = parse(r.get("out") or "")
            attempts.append(d)
            if d.get("MTD0"):
                health = d
                if d.get("MT7916") == "1" and d.get("PANICS") == "0":
                    break
        except Exception as e:
            attempts.append({"error": str(e)})
        time.sleep(10)
    res["health"] = health
    res["health_attempts"] = attempts
    open(OUT + "/health.txt", "w").write(json.dumps(health, indent=1))
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    res["verdict"] = ("GREEN" if ("banner" in seen and "kernel" in seen and "linux" in seen
                                 and health.get("MTD0") == "ac06d7bcccfc1ed2baa18e792cffce8c7912981eb5491e5b3ea67b1a1172325f"
                                 and health.get("MT7916") == "1" and health.get("PANICS") == "0"
                                 and not res["panics"]) else "FAIL")
    json.dump(res, open(OUT + "/results.json", "w"), indent=1)
    log("VERDICT " + res["verdict"])
    return 0 if res["verdict"] == "GREEN" else 2

if __name__ == "__main__":
    sys.exit(main())
