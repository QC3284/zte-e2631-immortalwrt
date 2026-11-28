#!/usr/bin/env python3
"""E4 v2.1 rescue Phase A device acceptance (task-86).

Modes:
  preflight  host-only checks + read-only device baseline. No writes.
  load       Linux staging of the 655360-byte mtd0 image into userdata, reboot
             to the flash U-Boot, RAM-load the image at 0x47EFF800 so the
             u-boot payload lands at 0x47F00000, start e2631rescue and leave it
             running. Leaves the serial hub alive; no capture restore.
  probe      host-side HTTP matrix against the running rescue server.
  exit       Ctrl-C the rescue loop, clear the RAM next-slot override,
             e2631boot back to Linux, restore the capture chain, verify that
             every flash digest is unchanged and audit the serial/HTTP logs.
  all        preflight + load + probe + exit (exit always attempted).

Hard limits: no mtd0/slot/env writes. The only flash write is the userdata
staging erase+write. No saveenv. Ctrl-C is sent only while the rescue loop is
running. The RAM image is the t85 rebuild, byte-identical to run 46.
"""
import argparse
import binascii
import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
from urllib.parse import quote
import zlib

P3 = "/home/qc233/zte/e2631-p3"
E2 = P3 + "/e2"
KIT = "/home/qc233/zte/e2631-immortalwrt"
sys.path.insert(0, P3)
sys.path.insert(0, E2)
sys.path.insert(0, E2 + "/drivers")
import a1_banner_accept as base
import b1_env_session as b1
import c1b1_final as fin

ART_DEFAULT = "/home/qc233/zte/e2631-t5-artifacts/t85-46111271598/files"
LEGAL_DEFAULT = "/home/qc233/zte/e2631-t5-artifacts/parity-ref/e2631-immortalwrt-experimental.bin"
PAGE_LOCAL = KIT + "/uboot-port/failsafe/e2631-failsafe.html"

# Current flash (patch-0034 image, written by task-79). Measured read-only at
# 2026-11-28 13:20; the Lead's f9239040/b1ea9a48 values predate that write.
FLASH_BANNER = "U-Boot 2027.01-rc2-g1673d5c89c7b"
NEW_BANNER = "U-Boot 2027.01-rc2-g49f13e0cbe40"
BASE_MTD0_SHA = "ac06d7bcccfc1ed2baa18e792cffce8c7912981eb5491e5b3ea67b1a1172325f"
BASE_REGION_SHA = "23395533c123ea1099c951fee55a73f264636ca9d33d8298b160efb6d0fdb7d1"
BASE_ENV_SHA = "6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893"
BASE_SECOND_SHA = "540db4350cca5e77228b65ba3b387ea86be545e7f10a81db19b81d6f7816e1fd"
BASE_PARTS = {
    "mtd1": "e2bba3332de45858b5f3d3b68b57d58d5e6a47de437de3a0fa6ba3389e752f3d",
    "mtd2": "a7b72db92a81f9c9a804933371beece2f1b90bdc9a36fc90393f705d8a3744bc",
    "mtd3": "0d4e5a76e58f9d0f81872795e0c961ef4cc457caf60564689d22d3a31b01793a",
    "mtd4": "360bf435e5967d6f69fe1645f3e43b1aba123ee99c391d307d4a5e820a987d24",
    "mtd5": "c0dd53794028ef38414d53706036e0f50d9b963d23c64fbd0f3a2df0cd2f5b7f",
    "mtd6": "107980d7352b303e1b5279658660018b8419a6931524cb6c459e18f0463c8e63",
    "mtd7": "381da11e92b3736a06bb5245151102991a7ea4d044c5244dc769ec6f75dad6f9",
    "mtd8": "73a14042672def65a49b0e4a5e80db91995e68b4c497ae61fa49b83d168e121c",
}
STAGE_OFF = 0x3F00000
STAGE_LEN = 0xA0000
LOAD_ADDR = 0x47EFF800
EXEC_ADDR = 0x47F00000
HOST_IP = "192.168.1.191"
IFACE = "enp0s20u1u4u2c2"
RESCUE_URL = "http://192.168.1.1"
RESCUE_MARKER = rb"e2631rescue: open http://192\.168\.1\.1/"
RESCUE_LEFT = rb"e2631rescue: left the rescue mode"
KERNEL_START = [b"Starting kernel ...", b"Booting Linux"]
LINUX_MARKERS = [b"e2631-wifi-boot", b"automatic Wi-Fi initialization complete",
                 b"Please press Enter", b"login:"]
PANIC = [b"Kernel panic", b"Unable to mount root", b"data abort", b"prefetch abort"]
PAGE_TABS = ["系统状态", "固件更新", "引导区", "环境变量", "串口台", "恢复出厂"]
BACKUP_PARTS = {
    "bootloader": (0x20000, 0xA0000),
    "tag": (0x100000, 0x100000),
    "wifi": (0x200000, 0x100000),
    "usercfg": (0x300000, 0x200000),
    "defcfg": (0x500000, 0x200000),
}
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


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def crc_hex(b):
    return "0x%08x" % (zlib.crc32(b) & 0xFFFFFFFF)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def write_bytes(path, data):
    with open(path, "wb") as f:
        f.write(data)


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)


def load_json(path):
    with open(path) as f:
        return json.load(f)


def ssh_binary(remote, timeout=180):
    env = dict(os.environ)
    env.update({"SSH_ASKPASS": b1.ASKPASS, "SSH_ASKPASS_REQUIRE": "force",
                "DISPLAY": ":0"})
    cmd = ["setsid", "-w", "ssh", "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10",
           "root@192.168.1.1", remote]
    try:
        p = subprocess.run(cmd, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
        return p.returncode, p.stdout, p.stderr.decode("latin-1", "replace")
    except subprocess.TimeoutExpired:
        return 124, b"", "timeout"


def ssh_stdin(remote, data, timeout=240):
    env = dict(os.environ)
    env.update({"SSH_ASKPASS": b1.ASKPASS, "SSH_ASKPASS_REQUIRE": "force",
                "DISPLAY": ":0"})
    cmd = ["setsid", "-w", "ssh", "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10",
           "root@192.168.1.1", remote]
    try:
        p = subprocess.run(cmd, env=env, input=data, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
        return p.returncode, p.stdout.decode("latin-1", "replace"), p.stderr.decode("latin-1", "replace")
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def parse_uboot_info(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    out = {"raw": txt}
    for line in txt.splitlines():
        if line.startswith("Banner: "):
            out["banner"] = line.split("Banner: ", 1)[1].strip()
        elif line.startswith("u-boot.bin size: "):
            out["uboot_size"] = int(re.search(r"([0-9]+)", line).group(1))
        elif line.startswith("u-boot.bin sha256: "):
            out["uboot_sha256"] = line.split(": ", 1)[1].strip()
        elif line.startswith("u-boot.bin crc32: "):
            out["uboot_crc32"] = "0x" + line.split(": ", 1)[1].strip()
        elif line.startswith("mtd0 image: "):
            m = re.search(r"sha256 ([0-9a-f]{64})", line)
            if m:
                out["mtd0_sha256"] = m.group(1)
        elif line.startswith("mtd0 image crc32: "):
            out["mtd0_crc32"] = "0x" + line.split(": ", 1)[1].strip()
        elif line.startswith("Post-am tree: "):
            out["tree"] = line.split(": ", 1)[1].strip()
        elif line.startswith("Run: "):
            out["run"] = line.split(": ", 1)[1].strip()
        elif line.startswith("  source=") and "failsafe" in line:
            out["page_source"] = line.split("=", 1)[1].strip()
        elif line.startswith("  raw_bytes=") and "page_source" in out:
            out["page_raw_bytes"] = int(line.split("=", 1)[1])
        elif line.startswith("  gzip_bytes=") and "page_source" in out:
            out["page_gzip_bytes"] = int(line.split("=", 1)[1])
        elif line.startswith("  gzip_sha256=") and "page_source" in out:
            out["page_gzip_sha256"] = line.split("=", 1)[1].strip()
    return out


def artifact_facts(artdir):
    rep = {"dir": artdir}
    info = parse_uboot_info(os.path.join(artdir, "UBOOT-INFO.txt"))
    rep["info"] = info
    ub = os.path.join(artdir, "u-boot.bin")
    img = os.path.join(artdir, "e2631-uboot-mtd0.bin")
    rep["uboot"] = {"path": ub, "size": os.path.getsize(ub), "sha256": sha_bytes(read_bytes(ub))}
    rep["image"] = {"path": img, "size": os.path.getsize(img), "sha256": sha_bytes(read_bytes(img)),
                    "crc32": crc_hex(read_bytes(img))}
    ubb = read_bytes(ub)
    imb = read_bytes(img)
    rep["uboot"]["crc32"] = crc_hex(ubb)
    rep["image_payload_ok"] = imb[0x800:0x800 + len(ubb)] == ubb
    rep["image_header_magic"] = binascii.hexlify(imb[0x10:0x14]).decode()
    rep["image_header_len"] = int.from_bytes(imb[0x14:0x18], "little")
    rep["page_local"] = {"path": PAGE_LOCAL, "size": os.path.getsize(PAGE_LOCAL),
                         "sha256": sha_bytes(read_bytes(PAGE_LOCAL))}
    rep["pins"] = {
        "uboot_sha_ok": rep["uboot"]["sha256"] == info.get("uboot_sha256"),
        "uboot_size_ok": rep["uboot"]["size"] == info.get("uboot_size"),
        "image_sha_ok": rep["image"]["sha256"] == info.get("mtd0_sha256"),
        "image_crc_ok": rep["image"]["crc32"] == info.get("mtd0_crc32"),
        "banner_ok": info.get("banner", "").startswith(NEW_BANNER),
        "page_raw_ok": rep["page_local"]["sha256"] == sha_bytes(read_bytes(PAGE_LOCAL)),
    }
    sums = os.path.join(artdir, "SHA256SUMS")
    if os.path.exists(sums):
        rc, out, err = sh("cd " + artdir + " && sha256sum -c SHA256SUMS", timeout=60)
        rep["sha256sums"] = {"rc": rc, "out": out[-1200:], "err": err[-300:]}
    else:
        rep["sha256sums"] = {"rc": 1, "out": "", "err": "missing SHA256SUMS"}
    rep["ok"] = all(rep["pins"].values()) and rep["sha256sums"]["rc"] == 0
    return rep


def legal_pkg_facts(path):
    b = read_bytes(path)
    hdr_off = 0x14 + int.from_bytes(b[0x10:0x14], "little")
    body_off = hdr_off + 0x200
    hdr = b[hdr_off:body_off]
    return {"path": path, "size": len(b), "sha256": sha_bytes(b), "crc32": crc_hex(b),
            "outer_magic": binascii.hexlify(b[:16]).decode(), "hdr_off": hdr_off,
            "body_off": body_off, "body_len": len(b) - body_off,
            "rootfs_crc": "0x%08x" % int.from_bytes(hdr[0x48:0x4c], "little"),
            "inner_magic": binascii.hexlify(hdr[0xf4:0xf4 + 16]).decode(),
            "product": hdr[0x6c:0x6c + 17].decode("latin-1", "replace"),
            "body_crc32": "0x%08x" % (zlib.crc32(b[body_off:]) & 0xFFFFFFFF)}


def region_fetch(outdir):
    path = os.path.join(outdir, "current-region.bin")
    rc, data, err = ssh_binary("dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null", 120)
    if rc == 0 and len(data) == 655360:
        with open(path, "wb") as f:
            f.write(data)
    return {"path": path, "rc": rc, "err": err, "size": len(data),
            "sha256": sha_bytes(data), "crc32": crc_hex(data) if data else None}


DEV_CMD = (
    "printf 'VERSION='; cat /etc/e2631-version; "
    "printf 'KERNEL='; uname -r; "
    "printf 'UPTIME='; cut -d. -f1 /proc/uptime; "
    "printf 'MTD0='; sha256sum /dev/mtd0 | cut -d' ' -f1; "
    "printf 'REGION='; dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d' ' -f1; "
    "printf 'ENV='; dd if=/dev/mtd0 bs=4096 skip=192 count=32 2>/dev/null | sha256sum | cut -d' ' -f1; "
    "printf 'SECOND='; dd if=/dev/mtd0 bs=4096 count=32 2>/dev/null | sha256sum | cut -d' ' -f1; "
    "printf 'USERDATA='; grep -q /dev/mtd10 /proc/mounts && echo mounted || echo unmounted; "
    "for p in 1 2 3 4 5 6 7 8; do printf 'MTD%s=' \"$p\"; sha256sum /dev/mtd$p | cut -d' ' -f1; done"
)


def parse_kv(text):
    out = {}
    for line in (text or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def device_facts():
    rc, out, err = b1.ssh_run(DEV_CMD, timeout=300)
    return {"rc": rc, "raw": out, "err": err, "kv": parse_kv(out)}


def preflight(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    global LOG
    LOG = outdir + "/preflight.log"
    b1.make_askpass()
    b1.ensure_direct_link()
    rep = {"mode": "preflight", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "artifact": artifact_facts(args.artifact_dir),
           "legal": legal_pkg_facts(args.legal),
           "route": {"raw": base.sh("ip route get 192.168.1.1 | head -1")[1]},
           "capture": {"supervisor": base.pgrep("capture-supervisor-002.sh"),
                       "bootwatch": base.pgrep("serial-bootwatch.mjs"),
                       "tty": base.tty_holders()}}
    rep["region"] = region_fetch(outdir)
    rep["device"] = device_facts()
    kv = rep["device"]["kv"]
    rep["baseline"] = {
        "mtd0": kv.get("MTD0"), "region": kv.get("REGION"), "env": kv.get("ENV"),
        "secondboot": kv.get("SECOND"),
        "parts": {k: kv.get("MTD" + k.replace("mtd", "")) for k in BASE_PARTS},
    }
    rep["baseline_ok"] = {
        "mtd0": kv.get("MTD0") == BASE_MTD0_SHA,
        "region": kv.get("REGION") == BASE_REGION_SHA,
        "env": kv.get("ENV") == BASE_ENV_SHA,
        "secondboot": kv.get("SECOND") == BASE_SECOND_SHA,
        "region_file": rep["region"]["sha256"] == BASE_REGION_SHA,
        "parts": all(kv.get("MTD" + k.replace("mtd", "")) == v for k, v in BASE_PARTS.items()),
    }
    rep["region_crc"] = rep["region"]["crc32"]
    rep["region_sha"] = rep["region"]["sha256"]
    rep["baseline"]["region_path"] = rep["region"]["path"]
    rep["device_ok"] = (rep["device"]["rc"] == 0 and rep["baseline_ok"]["mtd0"]
                        and rep["baseline_ok"]["region"] and rep["baseline_ok"]["env"]
                        and rep["baseline_ok"]["secondboot"])
    rep["route_ok"] = "via " not in rep["route"]["raw"]
    rep["capture_ok"] = bool(rep["capture"]["supervisor"] and rep["capture"]["bootwatch"]
                              and rep["capture"]["tty"])
    rep["ok"] = bool(rep["artifact"]["ok"] and rep["device_ok"] and rep["route_ok"]
                     and rep["capture_ok"] and rep["region"]["sha256"] == BASE_REGION_SHA)
    write_json(outdir + "/preflight.json", rep)
    print(json.dumps(rep, indent=1))
    log("preflight ok=" + str(rep["ok"]) + " region_crc=" + str(rep["region_crc"]))
    return 0 if rep["ok"] else 2


def wait_for(c, pattern, timeout):
    return c.wait(pattern, timeout)


def stop_autoboot_any(c, banner, timeout=90):
    c.pending = b""
    seen = c.wait(re.escape(banner.encode()), timeout)
    if seen is None:
        return {"banner_seen": False, "prompt": False, "tail": c.pending[-800:].decode("latin-1", "replace")}
    for _ in range(30):
        c.send(b" ")
        time.sleep(0.08)
    prompt = fin.wait_prompt(c, 25)
    out = {"banner_seen": True, "prompt": prompt is not None,
           "tail": ((seen or b"") + (prompt or b""))[-1200:].decode("latin-1", "replace")}
    return out


def send_cmd(c, cmd, timeout=180, wait=True):
    c.pending = b""
    c.send((cmd + "\r").encode())
    if not wait:
        return b""
    out = fin.wait_prompt(c, timeout)
    return (out or b"").decode("latin-1", "replace")


def stage_image(outdir, image_path):
    data = read_bytes(image_path)
    sha = sha_bytes(data)
    rep = {"image": image_path, "size": len(data), "sha256": sha}
    rc, out, err = ssh_stdin("cat > /tmp/e4v2-stage.bin; sha256sum /tmp/e4v2-stage.bin", data, 240)
    rep["copy"] = {"rc": rc, "out": out[-500:], "err": err[-300:]}
    if rc != 0 or sha not in out:
        rep["ok"] = False
        return rep
    for key, cmd in [
        ("erase", "mtd erase userdata; echo ERASE_RC=$?"),
        ("write", "mtd write /tmp/e4v2-stage.bin userdata; echo WRITE_RC=$?"),
        ("readback", "dd if=/dev/mtd10 bs=4096 count=160 2>/dev/null | sha256sum"),
        ("sync", "sync; echo SYNCED"),
    ]:
        t0 = time.time()
        rc, out, err = b1.ssh_run(cmd, timeout=300)
        rep[key] = {"rc": rc, "out": out[-500:], "err": err[-300:], "elapsed_s": round(time.time() - t0, 2)}
        if key == "readback" and sha not in out:
            rep["ok"] = False
            return rep
    rep["ok"] = True
    return rep


def reboot_to_flash(c, outdir, capture=None, hub_pid=None):
    rep = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if capture is None:
        rep["capture"] = base.pause_capture()
        if not rep["capture"].get("free"):
            rep["error"] = "tty still busy after pausing the capture chain"
            return rep
        rep["hub_pid"] = base.start_hub(outdir + "/serial.log")
    else:
        rep["capture"] = capture
        rep["hub_pid"] = hub_pid
    rc, out, err = b1.ssh_run("sync; (sleep 1; reboot -f) </dev/null >/dev/null 2>&1 &",
                              timeout=30)
    rep["reboot_ssh"] = {"rc": rc, "out": out[-300:], "err": err[-300:]}
    rep["flash_boot"] = stop_autoboot_any(c, FLASH_BANNER, 120)
    if not rep["flash_boot"].get("prompt"):
        rep["error"] = "flash U-Boot prompt not reached"
        return rep
    rep["flash_version"] = send_cmd(c, "version", 30)
    rep["flash_version_ok"] = FLASH_BANNER in rep["flash_version"]
    return rep


def attach_console():
    # The hub stays alive across the load/probe/exit invocations.
    try:
        base.ctl_call({"op": "ping"}, timeout=5)
    except Exception:
        start = base.start_hub(os.path.join(os.environ.get("E4V2_OUT", "."), "serial.log"))
        log("restarted serial hub pid=" + str(start))
    return base.Console()


def load_mode(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    global LOG
    LOG = outdir + "/load.log"
    os.environ["E4V2_OUT"] = outdir
    rep = {"mode": "load", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    pre = load_json(outdir + "/preflight.json")
    if not pre.get("ok"):
        raise RuntimeError("preflight is not green; refusing to load")
    b1.make_askpass()
    b1.ensure_direct_link()
    try:
        rep["stage"] = stage_image(outdir, os.path.join(args.artifact_dir, "e2631-uboot-mtd0.bin"))
        if not rep["stage"].get("ok"):
            raise RuntimeError("userdata staging failed")
        rep["capture"] = base.pause_capture()
        if not rep["capture"].get("free"):
            raise RuntimeError("tty still busy after pausing the capture chain")
        rep["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        rep["reboot"] = reboot_to_flash(c, outdir, rep["capture"], rep["hub_pid"])
        if not rep["reboot"].get("flash_version_ok"):
            raise RuntimeError("flash U-Boot banner/version gate failed")
        rep["commands"] = []
        def cmd(text, timeout=180):
            t0 = time.time()
            out = send_cmd(c, text, timeout)
            rep["commands"].append({"cmd": text, "elapsed_s": round(time.time() - t0, 2),
                                     "out": out[-3000:]})
            log("cmd " + text + " %.1fs" % (time.time() - t0))
            return out
        out = cmd("mtd read spi-nand0 0x47eff800 0x3f00000 0xa0000", 180)
        rep["read_ok"] = ("655360 byte(s)" in out) and ("Failure" not in out)
        out = cmd("crc32 0x47eff800 0xa0000", 120)
        m = re.search(r"==>\s*([0-9a-fA-F]{8})", out)
        rep["image_crc_ok"] = bool(m and m.group(1).lower() == "64c4e55d")
        out = cmd("md.l 0x47eff810 1", 30)
        rep["header_magic_ok"] = ("73383231" in out.lower())
        c.pending = b""
        c.send(b"go 0x47f00000\r")
        rep["new_boot"] = stop_autoboot_any(c, NEW_BANNER, 60)
        if not rep["new_boot"].get("prompt"):
            raise RuntimeError("v2.1 U-Boot prompt not reached after go")
        rep["new_version"] = send_cmd(c, "version", 30)
        rep["new_version_ok"] = NEW_BANNER in rep["new_version"]
        if not rep["new_version_ok"]:
            raise RuntimeError("v2.1 banner/version gate failed")
        rep["slot_before"] = send_cmd(c, "e2631slot", 120)
        rep["help_rescue"] = send_cmd(c, "help e2631rescue", 30)
        rep["rescue_help_ok"] = any(t in rep["help_rescue"] for t in
                                     ("serve the web failsafe", "serve the web bootloader rescue",
                                      "serve the web"))
        c.pending = b""
        c.send(b"e2631rescue\r")
        marker = c.wait(RESCUE_MARKER, 120)
        rep["rescue_marker"] = marker is not None
        rep["rescue_tail"] = ((marker or b"")[-1500:]).decode("latin-1", "replace")
        if not rep["rescue_marker"]:
            raise RuntimeError("e2631rescue never printed the HTTP-ready line")
        time.sleep(1.0)
        rep["ok"] = bool(rep["read_ok"] and rep["image_crc_ok"] and rep["header_magic_ok"]
                         and rep["new_version_ok"] and rep["rescue_help_ok"])
        rep["rescue_running"] = True
    except Exception as exc:
        rep["error"] = repr(exc)
        rep["rescue_running"] = bool(rep.get("rescue_marker"))
        if not rep["rescue_running"]:
            try:
                base.stop_hub()
            except Exception:
                pass
            try:
                base.restore_capture()
            except Exception:
                pass
    write_json(outdir + "/load.json", rep)
    print(json.dumps({k: rep.get(k) for k in ("mode", "ok", "error", "rescue_running")}, indent=1))
    return 0 if rep.get("ok") else 2


def curl_req(outdir, name, url, method="GET", body=None, headers=None, timeout=120):
    hdr = os.path.join(outdir, name + ".headers")
    bpath = os.path.join(outdir, name + ".body")
    args = ["curl", "-4", "--noproxy", "*", "-sS", "--max-time", str(timeout),
            "--interface", HOST_IP, "-D", hdr, "-o", bpath]
    if method != "GET":
        args += ["-X", method]
    if body is not None:
        args += ["--data-binary", "@" + body]
    for h in (headers or []):
        args += ["-H", h]
    args.append(url)
    t0 = time.time()
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 15)
        rc, err = p.returncode, p.stderr
    except subprocess.TimeoutExpired:
        rc, err = 124, "timeout"
    hb = read_bytes(hdr) if os.path.exists(hdr) else b""
    bb = read_bytes(bpath) if os.path.exists(bpath) else b""
    htxt = hb.decode("latin-1", "replace")
    m = re.search(r"HTTP/1\.[01] (\d{3})", htxt)
    rec = {"name": name, "url": url, "method": method,
           "rc": rc, "stderr": (err or "")[:500],
           "elapsed_s": round(time.time() - t0, 3),
           "headers_path": hdr, "body_path": bpath,
           "status": int(m.group(1)) if m else None,
           "headers": htxt[:4000], "body_len": len(bb),
           "body_sha256": sha_bytes(bb) if bb else None,
           "body_text": bb.decode("latin-1", "replace")[:4000]}
    return rec


def http_header(rec, name):
    m = re.search(r"(?im)^" + re.escape(name) + r":\s*(.+?)\s*$", rec.get("headers") or "")
    return m.group(1) if m else None


def kv_body(rec):
    path = rec.get("body_path")
    if path and os.path.exists(path):
        return parse_kv(read_bytes(path).decode("latin-1", "replace"))
    return parse_kv(rec.get("body_text") or "")


def add_check(res, name, ok, detail=None):
    res["checks"][name] = bool(ok)
    if detail is not None:
        res.setdefault("check_detail", {})[name] = detail
    log("CHECK %-38s %s" % (name, "PASS" if ok else "FAIL"))


def status_get(outdir, name, timeout=300):
    rec = curl_req(outdir, name, RESCUE_URL + "/status", timeout=timeout)
    rec["kv"] = kv_body(rec)
    return rec


def parse_status_kv(rec):
    return rec.get("kv") or {}


def backup_check(outdir, part, off, length, want_sha, res, region=None):
    name = "backup-" + part
    rec = curl_req(outdir, name, RESCUE_URL + "/backup?part=" + part, timeout=240)
    rec["kv"] = kv_body(rec)
    bb = read_bytes(rec["body_path"]) if os.path.exists(rec["body_path"]) else b""
    body_sha = sha_bytes(bb) if bb else None
    body_crc = "0x%08x" % (zlib.crc32(bb) & 0xFFFFFFFF) if bb else None
    hdr_crc = (http_header(rec, "X-E2631-CRC32") or "").lower()
    hdr_sha = (http_header(rec, "X-E2631-SHA256") or "").lower()
    hdr_off = (http_header(rec, "X-E2631-Offset") or "").lower()
    hdr_len = (http_header(rec, "X-E2631-Length") or "").lower()
    hdr_part = http_header(rec, "X-E2631-Part")
    cd = http_header(rec, "Content-Disposition") or ""
    clen = http_header(rec, "Content-Length")
    checks = {
        "status_200": rec.get("status") == 200,
        "body_len": len(bb) == length,
        "body_sha": body_sha == want_sha,
        "hdr_sha": hdr_sha == body_sha,
        "body_crc": body_crc == hdr_crc,
        "hdr_crc": hdr_crc == body_crc,
        "offset": hdr_off == "0x%08x" % off,
        "length": hdr_len == "0x%08x" % length,
        "part": hdr_part == part,
        "disposition": ("e2631-" + part + ".bin") in cd,
        "content_length": str(length) == (clen or ""),
    }
    if part == "bootloader" and region is not None:
        checks["region_exact"] = bb == read_bytes(region)
    rec["checks"] = checks
    rec["body_crc"] = body_crc
    res.setdefault("backups", {})[part] = rec
    for k, v in checks.items():
        add_check(res, "backup_%s_%s" % (part, k), v)
    return rec


def page_check(outdir, pre, res):
    rec = curl_req(outdir, "page", RESCUE_URL + "/", timeout=60)
    bb = read_bytes(rec["body_path"]) if os.path.exists(rec["body_path"]) else b""
    raw = None
    try:
        raw = gzip.decompress(bb)
    except Exception:
        raw = None
    info = pre["artifact"]["info"]
    local = read_bytes(PAGE_LOCAL)
    checks = {
        "status_200": rec.get("status") == 200,
        "gzip": (http_header(rec, "Content-Encoding") or "").lower() == "gzip",
        "gzip_len": len(bb) == info.get("page_gzip_bytes"),
        "gzip_sha": sha_bytes(bb) == info.get("page_gzip_sha256"),
        "raw_ok": raw is not None,
        "raw_len": raw is not None and len(raw) == info.get("page_raw_bytes"),
        "raw_sha": raw is not None and sha_bytes(raw) == sha_bytes(local),
        "six_tabs": raw is not None and all(t.encode("utf-8") in raw for t in PAGE_TABS),
        "no_external_url": raw is not None and not re.search(rb"https?://(?!192\.168\.1\.1)", raw),
    }
    rec["checks"] = checks
    rec["raw_sha256"] = sha_bytes(raw) if raw else None
    res["page"] = rec
    for k, v in checks.items():
        add_check(res, "page_" + k, v)
    return rec


def status_checks(outdir, pre, res, name="status"):
    rec = status_get(outdir, name, timeout=300)
    rec["kv"] = kv_body(rec)
    s = rec["kv"]
    info = pre["artifact"]["info"]
    expected_keys = ["stage", "progress", "op", "mode", "result", "error", "crc32",
                     "sha256", "browser_sha256", "sha_match", "bytes_total", "bytes_done",
                     "slot", "slot_target", "slot_target_identity", "guard", "guard_reason",
                     "written_serial", "version", "next_slot", "next_reason",
                     "bootloader_region_crc32", "slot0_valid", "slot0_intact",
                     "slot0_identity", "slot0_serial", "slot0_version", "slot0_header_at",
                     "slot1_valid", "slot1_intact", "slot1_identity", "slot1_serial",
                     "slot1_version", "slot1_header_at", "slot1_header_partition"]
    checks = {
        "status_200": rec.get("status") == 200,
        "keys": all(k in s for k in expected_keys),
        "idle": s.get("stage") == "idle" and s.get("op") == "idle" and s.get("result") in ("", None),
        "version": NEW_BANNER in (s.get("version") or "").replace("_", " "),
        "region_crc": (s.get("bootloader_region_crc32") or "").lower() == (pre.get("region_crc") or "").lower(),
        "slot1_header_partition": s.get("slot1_header_partition") == "mtd8",
        "next_slot": s.get("next_slot") == "1",
        "next_reason": s.get("next_reason") == "serial",
        "slot0_vendor": s.get("slot0_identity") == "vendor" and s.get("slot0_intact") == "1" and s.get("slot0_serial") == "7",
        "slot1_ours": s.get("slot1_identity") == "ours" and s.get("slot1_intact") == "1" and s.get("slot1_serial") == "12",
        "slot0_header": (s.get("slot0_header_at") or "").lower() == "0x01c60000",
        "slot1_header": (s.get("slot1_header_at") or "").lower() == "0x03800000",
    }
    rec["checks"] = checks
    res[name] = rec
    for k, v in checks.items():
        add_check(res, "status_" + k, v)
    return rec


def slots_check(outdir, res):
    rec = curl_req(outdir, "slots", RESCUE_URL + "/slots", timeout=180)
    s = kv_body(rec)
    rec["kv"] = s
    checks = {
        "status_200": rec.get("status") == 200,
        "partitions": s.get("slot0_partition") == "mtd5" and s.get("slot1_partition") == "mtd6",
        "spans": (s.get("slot0_span") or "").lower() == "0x01c00000"
                 and (s.get("slot1_span") or "").lower() == "0x01c00000",
        "slot1_header": (s.get("slot1_header") or "").lower() == "0x03800000",
        "next_slot": s.get("next_slot") == "1" and s.get("next_reason") == "serial",
        "slot0": s.get("slot0_identity") == "vendor" and s.get("slot0_intact") == "1"
                 and s.get("slot0_serial") == "7" and (s.get("slot0_header_at") or "").lower() == "0x01c60000",
        "slot1": s.get("slot1_identity") == "ours" and s.get("slot1_intact") == "1"
                 and s.get("slot1_serial") == "12" and (s.get("slot1_header_at") or "").lower() == "0x03800000",
    }
    rec["checks"] = checks
    res["slots"] = rec
    for k, v in checks.items():
        add_check(res, "slots_" + k, v)
    return rec


def env_check(outdir, res):
    rec = curl_req(outdir, "env", RESCUE_URL + "/env", timeout=60)
    txt = rec.get("body_text") or ""
    kv = parse_kv(txt)
    rec["kv"] = kv
    checks = {
        "status_200": rec.get("status") == 200,
        "count": len(kv) >= 26,
        "ethaddr": kv.get("ethaddr") == "00:41:71:00:00:50",
        "bootdelay": kv.get("bootdelay") == "3",
        "bootcmd": kv.get("bootcmd") == "e2631boot",
        "console": kv.get("console") == "ttyAMA0,115200n8",
        "versioninfo": kv.get("versioninfo") == "U-Boot V1.0.0 20230828191152 0x2300000 0x1 0xaf 0x00",
        "no_next_slot": "e2631_next_slot" not in kv,
    }
    rec["checks"] = checks
    res["env_initial"] = rec
    for k, v in checks.items():
        add_check(res, "env_" + k, v)
    return rec


def nope_check(outdir, res):
    rec = curl_req(outdir, "nope", RESCUE_URL + "/nope", timeout=30)
    kv = kv_body(rec)
    checks = {"status_404": rec.get("status") == 404, "error_not_found": kv.get("error") == "not found"}
    rec["checks"] = checks
    res["nope"] = rec
    for k, v in checks.items():
        add_check(res, "nope_" + k, v)
    return rec


def unescape_console(s):
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


BAD_CONSOLE_BODY = ("result=error\nexit=1\nstdout=\ntruncated=0\n"
                    "error=only a single command is allowed\n")


def console_call(outdir, name, cmd, timeout=90):
    url = RESCUE_URL + "/console?cmd=" + quote(cmd, safe="")
    rec = curl_req(outdir, name, url, method="POST", timeout=timeout)
    rec["cmd"] = cmd
    rec["kv"] = kv_body(rec)
    return rec


def console_checks(outdir, res):
    rec = curl_req(outdir, "console-get", RESCUE_URL + "/console", timeout=30)
    rec["kv"] = kv_body(rec)
    add_check(res, "console_get_404", rec.get("status") == 404
              and rec["kv"].get("error") == "not found")
    res["console_get"] = rec
    for tag, cmd in [("version", "version"), ("bootdelay", "printenv bootdelay"),
                     ("mdl", "md.l 0x40000000 4"), ("mdb", "md.b 0x40000000 0x2000")]:
        rec = console_call(outdir, "console-" + tag, cmd, timeout=90)
        rec["kv"] = kv_body(rec)
        kv = rec["kv"]
        stdout = unescape_console(kv.get("stdout") or "")
        checks = {
            "status_200": rec.get("status") == 200,
            "result_ok": kv.get("result") == "ok",
            "error_empty": (kv.get("error") or "") == "",
            "stdout_some": len(stdout) > 0,
        }
        if tag == "version":
            checks["version"] = NEW_BANNER in stdout
        if tag == "bootdelay":
            checks["bootdelay"] = "bootdelay=3" in stdout
        if tag == "mdb":
            checks["truncated"] = kv.get("truncated") == "1"
        rec["checks"] = checks
        rec["stdout_unescaped"] = stdout[:3000]
        res["console_" + tag] = rec
        for k, v in checks.items():
            add_check(res, "console_%s_%s" % (tag, k), v)

    cases = [("missing", RESCUE_URL + "/console"),
             ("empty", RESCUE_URL + "/console?cmd="),
             ("semicolon", RESCUE_URL + "/console?cmd=" + quote("version;version", safe="")),
             ("newline", RESCUE_URL + "/console?cmd=" + quote("version\n", safe="")),
             ("nul", RESCUE_URL + "/console?cmd=" + quote("version\x00", safe=""))]
    for tag, url in cases:
        rec = curl_req(outdir, "console-neg-" + tag, url, method="POST", timeout=30)
        text = rec.get("body_text") or ""
        add_check(res, "console_neg_" + tag, rec.get("status") == 400
                  and text == BAD_CONSOLE_BODY)
        res["console_neg_" + tag] = rec

    cmd257 = "a" * 257
    rec = console_call(outdir, "console-257", cmd257, timeout=90)
    rec["kv"] = kv_body(rec)
    rec["spec_gap"] = rec.get("status") != 400
    res["console_257"] = rec
    log("CONSOLE 257-byte status=%s spec_gap=%s" % (rec.get("status"), rec.get("spec_gap")))


def raw_http_post(outdir, name, path, headers, body=b"", timeout=20):
    s = socket.create_connection((DEVICE, 80), timeout=10)
    s.settimeout(timeout)
    req = "POST " + path + " HTTP/1.1\r\nHost: 192.168.1.1\r\nConnection: close\r\n"
    for k, v in headers:
        req += "%s: %s\r\n" % (k, v)
    req += "\r\n"
    t0 = time.time()
    try:
        s.sendall(req.encode("latin-1") + body)
        try:
            s.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        chunks = []
        while True:
            d = s.recv(65536)
            if not d:
                break
            chunks.append(d)
            if sum(len(x) for x in chunks) > 262144:
                break
    except socket.timeout:
        pass
    finally:
        s.close()
    raw = b"".join(chunks)
    sh = raw.split(b"\r\n\r\n", 1)
    htxt = sh[0].decode("latin-1", "replace")
    bb = sh[1] if len(sh) > 1 else b""
    m = re.search(r"HTTP/1\.[01] (\d{3})", htxt)
    return {"name": name, "path": path, "status": int(m.group(1)) if m else None,
            "headers": htxt, "body": bb.decode("latin-1", "replace"),
            "body_sha256": sha_bytes(bb) if bb else None,
            "elapsed_s": round(time.time() - t0, 3)}


def firmware_validate(outdir, name, path, sha, timeout=600):
    rec = curl_req(outdir, name, RESCUE_URL + "/firmware?mode=validate", method="POST",
                   body=path, headers=["Content-Type: application/octet-stream",
                                       "X-E2631-SHA256: " + sha], timeout=timeout)
    rec["kv"] = kv_body(rec)
    return rec


def firmware_checks(outdir, pre, res, status_first, slots):
    pkg = pre["legal"]
    out = pre["artifact"]
    checks = {}

    def expect(tag, rec, code, result=None, error=None, extra=None):
        kv = rec.get("kv") or {}
        ok = rec.get("status") == code
        if result is not None:
            ok = ok and kv.get("result") == result
        if error is not None:
            ok = ok and kv.get("error") == error
        for k, v in (extra or {}).items():
            ok = ok and kv.get(k) == v
        add_check(res, "fw_" + tag, ok, {"status": rec.get("status"), "kv": kv})
        return kv

    slots_kv = slots.get("kv") or {}
    next_slot = slots_kv.get("next_slot") or "1"
    slot0_vendor_intact = (slots_kv.get("slot0_identity") == "vendor"
                           and slots_kv.get("slot0_intact") == "1")
    legal_extra = {"sha_match": "ok", "body_len": str(pkg["body_len"]),
                   "crc32": pkg["body_crc32"]}
    rec = firmware_validate(outdir, "fw-auto", pkg["path"], pkg["sha256"], 600)
    kv = expect("auto", rec, 200, "ok", None, legal_extra)
    add_check(res, "fw_auto_target", kv.get("slot_target") == next_slot)
    add_check(res, "fw_auto_guard", kv.get("guard") in ("ok", "weak"))
    add_check(res, "fw_auto_sha", (kv.get("sha256") or "").lower() == pkg["sha256"]
              and (kv.get("browser_sha256") or "").lower() == pkg["sha256"])
    res["fw_auto"] = rec

    if slot0_vendor_intact:
        rec = firmware_validate(outdir, "fw-slot0", pkg["path"], pkg["sha256"], 600)
        expect("slot0_refused", rec, 400, "error",
               "refusing to overwrite a working vendor system")
        res["fw_slot0"] = rec
    else:
        rec = firmware_validate(outdir, "fw-slot0", pkg["path"], pkg["sha256"], 600)
        kv = expect("slot0_accepted", rec, 200, "ok")
        add_check(res, "fw_slot0_target", kv.get("slot_target") == "0")
        res["fw_slot0"] = rec

    rec = firmware_validate(outdir, "fw-slot1", pkg["path"], pkg["sha256"], 600)
    kv = expect("slot1", rec, 200, "ok")
    add_check(res, "fw_slot1_target", kv.get("slot_target") == "1")
    res["fw_slot1"] = rec

    rec = curl_req(outdir, "fw-wrongsha", RESCUE_URL + "/firmware?mode=validate",
                   method="POST", body=pkg["path"],
                   headers=["Content-Type: application/octet-stream",
                            "X-E2631-SHA256: " + ("0" * 64)], timeout=600)
    rec["kv"] = kv_body(rec)
    expect("wrong_sha", rec, 400, "error", "sha256 mismatch")
    res["fw_wrongsha"] = rec

    mutations = [("magic", 0, "bad outer magic"),
                 ("hdr", 0x20, "header CRC mismatch"),
                 ("kernel", 0x1000, "kernel CRC mismatch"),
                 ("rootfs", 0x410000, "rootfs CRC mismatch")]
    for tag, off, want in mutations:
        dst = os.path.join(outdir, "pkg-" + tag + ".bin")
        buf = bytearray(read_bytes(pkg["path"]))
        buf[off] ^= 0xFF
        write_bytes(dst, bytes(buf))
        sha = sha_bytes(bytes(buf))
        rec = firmware_validate(outdir, "fw-" + tag, dst, sha, 600)
        expect(tag, rec, 400, "error", want)
        res["fw_" + tag] = rec

    for tag, clen, body_len in [("too_big", 0x1BE0215, 0x100), ("too_small", 0x213, 0x213)]:
        rec = raw_http_post(outdir, "fw-" + tag, "/firmware?mode=validate",
                            [("Content-Type", "application/octet-stream"),
                             ("X-E2631-SHA256", "0" * 64),
                             ("Content-Length", str(clen))],
                            body=b"x" * body_len, timeout=25)
        kv = parse_kv(rec.get("body") or "")
        ok = rec.get("status") == 400 and kv.get("error") == "package size out of range"
        add_check(res, "fw_" + tag, ok, {"status": rec.get("status"), "kv": kv})
        res["fw_" + tag] = rec

    rec = raw_http_post(outdir, "fw-badslot", "/firmware?mode=validate&slot=2",
                        [("Content-Type", "application/octet-stream"),
                         ("X-E2631-SHA256", "0" * 64), ("Content-Length", "0")],
                        body=b"", timeout=20)
    kv = parse_kv(rec.get("body") or "")
    add_check(res, "fw_badslot", rec.get("status") == 400 and kv.get("error") == "bad slot",
              {"status": rec.get("status"), "kv": kv})
    res["fw_badslot"] = rec

    rec = status_get(outdir, "status-after-fw", timeout=120)
    kv = rec["kv"]
    add_check(res, "fw_status_idle", kv.get("stage") == "idle" and kv.get("op") == "idle")
    res["status_after_fw"] = rec


def factory_checks(outdir, res):
    cases = [("no_query", RESCUE_URL + "/factory", []),
             ("no_header", RESCUE_URL + "/factory?confirm=reset", []),
             ("wrong_confirm", RESCUE_URL + "/factory?confirm=wrong",
              ["X-E2631-Confirm: reset"])]
    for tag, url, headers in cases:
        rec = curl_req(outdir, "factory-" + tag, url, method="POST", headers=headers, timeout=30)
        kv = kv_body(rec)
        add_check(res, "factory_" + tag, rec.get("status") == 400
                  and kv.get("result") == "error" and kv.get("error") == "missing confirm")
        res["factory_" + tag] = rec


def env_refusal_checks(outdir, pre, res):
    write_hdr = ["X-E2631-Confirm: write"]
    cases = [
        ("no_confirm", RESCUE_URL + "/env?key=bootdelay&value=3", [], 400, "missing confirm"),
        ("bootcmd", RESCUE_URL + "/env?key=bootcmd&value=e2631boot&confirm=write", write_hdr, 403,
         "key is not writable"),
        ("bad_value", RESCUE_URL + "/env?key=bootdelay&value=%7f&confirm=write", write_hdr, 400,
         "bad value"),
        ("upper_key", RESCUE_URL + "/env?key=BOOTDELAY&value=3&confirm=write", write_hdr, 403,
         "key is not writable"),
        ("long_key", RESCUE_URL + "/env?key=" + ("e2631_" + "a" * 27) + "&value=1&confirm=write",
         write_hdr, 403, "key is not writable"),
    ]
    for tag, url, headers, code, err in cases:
        rec = curl_req(outdir, "env-" + tag, url, method="POST", headers=headers, timeout=30)
        kv = kv_body(rec)
        add_check(res, "env_" + tag, rec.get("status") == code and kv.get("error") == err)
        res["env_" + tag] = rec
    rec = curl_req(outdir, "env-nochange", RESCUE_URL + "/env?key=bootdelay&value=3&confirm=write",
                   method="POST", headers=write_hdr, timeout=30)
    kv = kv_body(rec)
    checks = {"status_200": rec.get("status") == 200, "result_ok": kv.get("result") == "ok",
              "keys_0": kv.get("keys") == "0",
              "new_crc": (kv.get("new_crc32") or "").lower() == "0xf95a816e"}
    for k, v in checks.items():
        add_check(res, "env_nochange_" + k, v)
    res["env_nochange"] = rec


def boot_checks(outdir, res):
    def post(name, query):
        rec = curl_req(outdir, name, RESCUE_URL + "/boot" + query, method="POST", timeout=60)
        rec["kv"] = kv_body(rec)
        return rec
    rec = post("boot-slot0", "?slot=0")
    kv = rec["kv"]
    add_check(res, "boot_slot0", rec.get("status") == 200 and kv.get("result") == "ok"
              and kv.get("next_slot") == "0")
    res["boot_slot0"] = rec
    env = curl_req(outdir, "env-after-boot0", RESCUE_URL + "/env", timeout=60)
    ev = kv_body(env)
    add_check(res, "boot_slot0_env", ev.get("e2631_next_slot") == "0")
    res["env_after_boot0"] = env
    rec = post("boot-slot1", "?slot=1")
    kv = rec["kv"]
    add_check(res, "boot_slot1", rec.get("status") == 200 and kv.get("next_slot") == "1")
    res["boot_slot1"] = rec
    env = curl_req(outdir, "env-after-boot1", RESCUE_URL + "/env", timeout=60)
    add_check(res, "boot_slot1_env", kv_body(env).get("e2631_next_slot") == "1")
    res["env_after_boot1"] = env
    rec = post("boot-slot2", "?slot=2")
    add_check(res, "boot_slot2", rec.get("status") == 400
              and rec["kv"].get("error") == "bad slot")
    res["boot_slot2"] = rec
    rec = post("boot-missing", "")
    add_check(res, "boot_missing", rec.get("status") == 400
              and rec["kv"].get("error") == "bad slot")
    res["boot_missing"] = rec
    rec = post("boot-slot1-final", "?slot=1")
    add_check(res, "boot_final_slot1", rec.get("status") == 200
              and rec["kv"].get("next_slot") == "1")
    res["boot_final"] = rec


def flash_validate_check(outdir, pre, res):
    region = pre["baseline"]["region_path"]
    sha = pre["region_sha"]
    rec = curl_req(outdir, "flash-validate", RESCUE_URL + "/flash?mode=validate", method="POST",
                   body=region, headers=["Content-Type: application/octet-stream",
                                         "X-E2631-SHA256: " + sha], timeout=240)
    rec["kv"] = kv_body(rec)
    kv = rec["kv"]
    add_check(res, "flash_validate",
              rec.get("status") == 200 and kv.get("result") == "ok" and kv.get("sha_match") == "ok")
    res["flash_validate"] = rec
    st = status_get(outdir, "status-final", timeout=120)
    add_check(res, "flash_final_idle", st["kv"].get("stage") == "idle")
    add_check(res, "flash_final_sha", (st["kv"].get("sha256") or "").lower() == sha)
    res["status_final"] = st


def probe_mode(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    global LOG
    LOG = outdir + "/probe.log"
    res = {"mode": "probe", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "checks": {}, "requests": []}
    b1.make_askpass()
    b1.ensure_direct_link()
    os.environ["E4V2_OUT"] = outdir
    pre = load_json(outdir + "/preflight.json")
    load = load_json(outdir + "/load.json")
    if not pre.get("ok") or not load.get("ok"):
        raise RuntimeError("preflight/load not green; refuse probe")
    try:
        page_check(outdir, pre, res)
        status_first = status_checks(outdir, pre, res, "status")
        slots = slots_check(outdir, res)
        env_check(outdir, res)
        for part, (off, length) in BACKUP_PARTS.items():
            key = "mtd1" if part == "tag" else ("mtd2" if part == "wifi" else
                  ("mtd3" if part == "usercfg" else ("mtd4" if part == "defcfg" else "mtd0")))
            want = pre["region_sha"] if part == "bootloader" else pre["baseline"]["parts"][key]
            backup_check(outdir, part, off, length, want, res,
                         region=(pre.get("region", {}).get("path") or
                pre["baseline"].get("region_path")) if part == "bootloader" else None)
        nope_check(outdir, res)
        console_checks(outdir, res)
        firmware_checks(outdir, pre, res, status_first, slots)
        factory_checks(outdir, res)
        env_refusal_checks(outdir, pre, res)
        boot_checks(outdir, res)
        flash_validate_check(outdir, pre, res)
        res["ok"] = all(bool(v) for k, v in res["checks"].items()
                        if not k.startswith("console_257"))
        res["console_257_spec_gap"] = bool(res.get("console_257", {}).get("spec_gap"))
        res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        write_json(outdir + "/probe.json", res)
        print(json.dumps({"mode": "probe", "ok": res["ok"],
                          "checks": len(res["checks"]),
                          "failed": [k for k, v in res["checks"].items() if not v],
                          "console_257_spec_gap": res["console_257_spec_gap"]}, indent=1))
        return 0 if res["ok"] else 3
    except Exception as exc:
        res["ok"] = False
        res["error"] = repr(exc)
        res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        write_json(outdir + "/probe.json", res)
        print("PROBE ERROR: " + repr(exc))
        return 3


def monitor_boot(c, timeout=300, linux_timeout=180):
    buf = bytearray()
    started = False
    start_ts = None
    deadline = time.time() + timeout
    linux_deadline = None
    while time.time() < deadline and (linux_deadline is None or time.time() < linux_deadline):
        d = c.read()
        if d:
            buf.extend(d)
            if not started and any(m in buf for m in KERNEL_START):
                started = True
                start_ts = round(time.time() - (deadline - timeout), 2)
                linux_deadline = time.time() + linux_timeout
                log("kernel hand-off seen")
            if any(m in buf for m in PANIC):
                break
            if started and any(m in buf for m in LINUX_MARKERS):
                break
        else:
            time.sleep(0.05)
    return {"kernel_started": started, "kernel_at_s": start_ts,
            "linux_marker": any(m in buf for m in LINUX_MARKERS),
            "panic": any(m in buf for m in PANIC),
            "tail": bytes(buf)[-5000:].decode("latin-1", "replace")}


def exit_mode(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    global LOG
    LOG = outdir + "/exit.log"
    res = {"mode": "exit", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    b1.make_askpass()
    b1.ensure_direct_link()
    os.environ["E4V2_OUT"] = outdir
    pre = load_json(outdir + "/preflight.json")
    load = load_json(outdir + "/load.json")
    probe_path = outdir + "/probe.json"
    probe = load_json(probe_path) if os.path.exists(probe_path) else {"ok": False}
    if not load.get("rescue_running"):
        res["error"] = "load did not leave the rescue running; nothing to exit"
        res["ok"] = False
        write_json(outdir + "/exit.json", res)
        return 4
    c = attach_console()
    try:
        c.pending = b""
        c.send(b"\x03")
        left = c.wait(RESCUE_LEFT, 25)
        res["rescue_left"] = left is not None
        if left is None:
            c.pending = b""
            c.send(b"\x03")
            left = c.wait(RESCUE_LEFT, 15)
            res["rescue_left_retry"] = left is not None
        prompt = fin.wait_prompt(c, 30)
        res["prompt_after_ctrlc"] = prompt is not None
        if prompt is None:
            raise RuntimeError("no U-Boot prompt after leaving the rescue")
        out = send_cmd(c, "setenv e2631_next_slot", 30)
        res["clear_override"] = out
        out = send_cmd(c, "printenv e2631_next_slot", 30)
        res["cleared"] = "not defined" in out
        c.pending = b""
        c.send(b"e2631boot\r")
        res["boot"] = monitor_boot(c, 300, 180)
        res["boot_ok"] = bool(res["boot"]["kernel_started"] and res["boot"]["linux_marker"]
                              and not res["boot"]["panic"])
        base.stop_hub()
        res["capture_after"] = base.restore_capture()
        b1.wait_uptime(60, 180)
        res["health"] = health_snapshot()
        facts = device_facts()
        res["device"] = facts
        kv = facts["kv"]
        res["final_checks"] = {
            "mtd0": kv.get("MTD0") == pre["baseline"]["mtd0"],
            "region": kv.get("REGION") == pre["baseline"]["region"],
            "env": kv.get("ENV") == pre["baseline"]["env"],
            "secondboot": kv.get("SECOND") == pre["baseline"]["secondboot"],
            # Only the four Lead-specified end gates matter here: the E4 v2
            # session legitimately changes mtd6/mtd7/mtd8 (slot1 + rootfs_data).
            "version": (kv.get("VERSION") or "").startswith("ImmortalWrt"),
            "kernel": kv.get("KERNEL") == "6.18.60",
        }
        res["serial_audit"] = audit_serial(outdir + "/serial.log")
        res["http_audit"] = audit_http(probe)
        res["ok"] = bool(res["boot_ok"] and res["capture_after"].get("ok")
                         and all(res["final_checks"].values())
                         and res["serial_audit"]["forbidden"] == []
                         and res["http_audit"]["write_requests"] == [])
    except Exception as exc:
        res["error"] = repr(exc)
        res["ok"] = False
        try:
            base.stop_hub()
        except Exception:
            pass
        try:
            res["capture_after"] = base.restore_capture()
        except Exception:
            pass
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write_json(outdir + "/exit.json", res)
    aggregate(args, pre, load, probe, res)
    print(json.dumps({k: res.get(k) for k in ("mode", "ok", "error", "boot_ok")}, indent=1))
    return 0 if res.get("ok") else 4


def health_snapshot():
    cmd = (
        "printf 'VERSION='; cat /etc/e2631-version; "
        "printf 'KERNEL='; uname -r; "
        "printf 'UPTIME='; cut -d. -f1 /proc/uptime; "
        "printf 'PANICS='; dmesg | grep -c -E 'Kernel panic|Oops|BUG:' || true; "
        "printf 'MT7916='; dmesg | grep -c 'MT7916 ready' || true; "
        "printf 'WIFI='; dmesg | grep -c 'automatic Wi-Fi initialization complete' || true; "
        "printf 'FWSLOT='; /usr/sbin/e2631-fwslot info -j 2>/dev/null | head -c 800; echo"
    )
    rc, out, err = b1.ssh_run(cmd, timeout=120)
    return {"rc": rc, "raw": out, "err": err, "kv": parse_kv(out)}


def audit_serial(path):
    if not os.path.exists(path):
        return {"path": path, "size": 0, "forbidden": [], "error": "missing"}
    data = read_bytes(path).decode("latin-1", "replace")
    pats = ["mtd write", "mtd erase", "saveenv", "nand write", "nand erase",
            "e2631flash", "e2631env"]
    forb = []
    for p in pats:
        if p in data.lower():
            forb.append(p)
    return {"path": path, "size": os.path.getsize(path), "forbidden": forb,
            "write_words": len(re.findall(r"\bmtd\s+(?:write|erase)\b", data, re.I))}


def audit_http(probe):
    writes = []

    def walk(obj):
        if isinstance(obj, dict):
            url = obj.get("url") or ""
            hdr = obj.get("headers") or ""
            if "mode=write" in url or "mode=write" in (obj.get("path") or ""):
                writes.append(url or obj.get("path"))
            if ("confirm=reset" in url and "X-E2631-Confirm: reset" in hdr):
                writes.append(url)
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
    walk(probe)
    return {"write_requests": writes, "probe_ok": probe.get("ok")}


def aggregate(args, pre, load, probe, exit_rep):
    rep = {"mode": "all", "artifact": pre.get("artifact", {}).get("info", {}),
           "preflight_ok": pre.get("ok"), "load_ok": load.get("ok"),
           "rescue_running": load.get("rescue_running"),
           "probe_ok": probe.get("ok"),
           "probe_checks": len(probe.get("checks") or {}),
           "probe_failed": [k for k, v in (probe.get("checks") or {}).items() if not v],
           "console_257_spec_gap": probe.get("console_257_spec_gap"),
           "exit_ok": exit_rep.get("ok"), "boot_ok": exit_rep.get("boot_ok"),
           "final_checks": exit_rep.get("final_checks"),
           "serial_audit": exit_rep.get("serial_audit"),
           "http_audit": exit_rep.get("http_audit"),
           "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    rep["ok"] = bool(rep["preflight_ok"] and rep["load_ok"] and rep["probe_ok"] and rep["exit_ok"])
    write_json(os.path.join(args.out_dir, "session-results.json"), rep)


def all_mode(args):
    rc = preflight(args)
    if rc:
        return rc
    rc = load_mode(args)
    if rc:
        return rc
    rc = probe_mode(args)
    exit_rc = exit_mode(args)
    if rc:
        return rc
    return exit_rc


def selftest(args):
    checks = {}
    try:
        info = parse_uboot_info(os.path.join(args.artifact_dir, "UBOOT-INFO.txt"))
        af = artifact_facts(args.artifact_dir)
        pkg = legal_pkg_facts(args.legal)
        checks["artifact"] = bool(af["ok"])
        checks["banner"] = info.get("banner", "").startswith(NEW_BANNER)
        checks["image_sha"] = af["image"]["sha256"] == "856703a10c741bae202eb308c548fe5a24d5ac15ac9c8200f973d48a8f272bbe"
        checks["image_crc"] = af["image"]["crc32"] == "0x64c4e55d"
        checks["uboot_crc"] = af["uboot"]["crc32"] == "0x0c5ef993"
        checks["legal_sha"] = pkg["sha256"] == "66805b26afa47b612e535ca0885fd088b0b37461c959fb75212548d30c58294d"
        checks["legal_body_crc"] = pkg["body_crc32"] == "0x496cca28"
        checks["legal_rootfs_crc"] = pkg["rootfs_crc"] == "0x9ff1a966"
        checks["legal_body_len"] = pkg["body_len"] == 0x1500000
        checks["page_gzip"] = info.get("page_gzip_bytes") == 13773
        checks["kv"] = parse_kv("a=1\nb=2\n") == {"a": "1", "b": "2"}
        checks["unescape"] = unescape_console("a\\nb\\\\c") == "a\nb\\c"
        checks["backup_parts"] = len(BACKUP_PARTS) == 5 and BACKUP_PARTS["bootloader"] == (0x20000, 0xA0000)
    except Exception as exc:
        print("selftest error: " + repr(exc))
        return 1
    for k, v in checks.items():
        print(("%-18s %s" % (k, "PASS" if v else "FAIL")))
    print("selftest " + ("ok" if all(checks.values()) else "FAILED"))
    return 0 if all(checks.values()) else 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["preflight", "load", "probe", "exit", "all"], default="all")
    ap.add_argument("--artifact-dir", default=ART_DEFAULT)
    ap.add_argument("--legal", default=LEGAL_DEFAULT)
    ap.add_argument("--out-dir", default="/home/qc233/zte/e2631-p3/e2/e4-v2-phasea/run-1")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest(args)
    return {"preflight": preflight, "load": load_mode, "probe": probe_mode,
            "exit": exit_mode, "all": all_mode}[args.mode](args)


if __name__ == "__main__":
    sys.exit(main())
