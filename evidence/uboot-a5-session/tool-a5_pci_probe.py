#!/usr/bin/env python3
"""A5 PCIe endpoint / WiFi diagnostic on the running patch-0012 kernel (read-only)."""
import json, os, sys, time

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import a1_banner_accept as base

OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/qc233/zte/e2631-p3/c1b1fix/a5-refclk/pci-probe"
SHELL = None
import re
SHELL = re.compile(rb"root@ImmortalWrt:[^#\r\n]*#")

CMDS = [
    ("dmesg_pcie_full", "dmesg | grep -iE 'pcie|link training|link up|link down' | tail -40"),
    ("sysfs_pci", "ls -l /sys/bus/pci/devices"),
    ("pci_uevent", "for d in /sys/bus/pci/devices/*; do echo $(basename $d); cat $d/uevent 2>/dev/null | head -6; done"),
    ("rescan", "echo 1 > /sys/bus/pci/rescan; sleep 3; ls -l /sys/bus/pci/devices"),
    ("dmesg_after_rescan", "dmesg | tail -25"),
    ("wifi_now", "dmesg | grep -iE 'MT7916|previous initialization|automatic Wi-Fi initialization' | tail -10"),
    ("mt7915_drv", "ls -l /sys/bus/pci/drivers/mt7915e 2>/dev/null | head -6"),
]


def read_for(c, seconds):
    buf = bytearray()
    end = time.time() + seconds
    while time.time() < end:
        data = c.read()
        if data:
            buf.extend(data)
        else:
            time.sleep(0.05)
    return bytes(buf)


def run(cmd, c, timeout=45):
    c.pending = bytes()
    c.send(cmd.encode() + b"\r")
    buf = bytearray()
    end = time.time() + timeout
    while time.time() < end:
        data = c.read()
        if data:
            c.pending += data
            buf.extend(data)
        else:
            time.sleep(0.05)
        if SHELL.search(bytes(buf)):
            break
    return {"cmd": cmd, "out": bytes(buf).decode("latin-1", "replace")}


def main():
    os.makedirs(OUT, exist_ok=True)
    cap = base.pause_capture()
    hub = base.start_hub(OUT + "/serial.log")
    c = base.Console()
    res = {"capture_paused": cap, "hub_pid": hub}
    try:
        # wake the shell
        for _ in range(20):
            c.pending = bytes()
            c.send(b"\r")
            time.sleep(0.5)
            d = c.read()
            if d:
                c.pending += d
            if SHELL.search(bytes(c.pending[-4000:])):
                break
        res["shell"] = True
        res["commands"] = {}
        for name, cmd in CMDS:
            r = run(cmd, c)
            res["commands"][name] = r
            print("CMD", name, "->", r["out"].strip()[-400:].replace("\n", " | "), flush=True)
            time.sleep(1)
    finally:
        try:
            base.stop_hub()
        except Exception:
            pass
        res["capture_after"] = base.restore_capture()
        json.dump(res, open(OUT + "/pci-probe.json", "w"), indent=1)
        print("SAVED", OUT + "/pci-probe.json", flush=True)


if __name__ == "__main__":
    main()
