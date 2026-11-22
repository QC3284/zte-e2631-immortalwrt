#!/usr/bin/env python3
"""task-61 / D-U4: no-serial bridge flash of the patch-0014 U-Boot.

Phase A (Linux console): wget the new mtd0 image from the host HTTP server,
mtd erase/write the userdata staging partition, sha256 read-back.
Phase B (old flash U-Boot console, patch-0013): read staging -> crc32 gate ->
erase image area -> FF sentinel crc32 -> write -> read-back crc32 gate.
No serial file transfer; only one write ladder; HOLD for the user power cycle.
"""
import json, os, re, struct, sys, time, zlib, hashlib

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import a1_banner_accept as base
import c1b1_final as fin

OUT_DEFAULT = "/home/qc233/zte/e2631-p3/c1b3-task61/run-1"
ART_DIR = ("/home/qc233/zte/e2631-t5-artifacts/uboot-du1-44943940449/"
           "e2631-uboot-44943940449")
IMAGE_URL = "http://192.168.5.92:18080/uboot-0014-mtd0.bin"
IMAGE_SHA = "b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a"
IMAGE_SIZE = 655360
IMAGE_CRC = 0x0721e716
FF_CRC = 0x804737c5
ART_SHA = "21b0d804483c7cbb82e2ca92968b6706ed0f740429e6e6c935bf34e16a881af8"
ART_SIZE = 456416
OLD_BANNER = "U-Boot 2027.01-rc2-g85c7367a3106"
NEW_BANNER = "U-Boot 2027.01-rc2-g85df6772a444"
BASELINE = fin.DEFAULT_BASELINE
CURRENT_MTD0_SHA = "5ebb5ab323bafea4a310e4cb3f78cbb77b3d219ba9fb324927bf28e8d0cc48cf"
STAGE_OFF = 0x3F00000
FLASH_OFF = 0x20000
IMAGES_AREA = 0xA0000
TAIL_END = 0x100000
UBOOT_BASE = 0x47F00000
RAM_IMAGE = 0x44000000
RAM_READ = 0x45000000

base.LOG = OUT_DEFAULT + "/driver.log"


def log(msg):
    base.log(msg)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_file(path):
    with open(path, "rb") as fh:
        return fh.read()


class Linux:
    def __init__(self, c):
        self.c = c
        self.n = 0

    def cmd(self, text, timeout=120, quiet_grace=0.0):
        self.n += 1
        sentinel = "__T61_%03d__" % self.n
        full = text + "; echo " + sentinel
        t0 = time.time()
        self.c.pending = b""
        self.c.send((full + "\r").encode())
        deadline = t0 + timeout
        while time.time() < deadline:
            data = self.c.read()
            if data:
                self.c.pending += data
                if sentinel.encode() in self.c.pending:
                    break
            else:
                time.sleep(0.02)
        elapsed = round(time.time() - t0, 2)
        raw = self.c.pending.decode("latin-1", "replace")
        ok = sentinel in raw
        body = raw.split(sentinel)[0]
        body = body.replace(text, "", 1).replace("\r", "")
        log("linux cmd %d %.2fs ok=%s: %s" % (self.n, elapsed, ok, text[:110]))
        return {"cmd": text, "ok": ok, "elapsed_s": elapsed, "output": body[-4000:]}

    def reboot(self):
        self.c.pending = b""
        self.c.send(b"sync; reboot -f\r")
        log("reboot -f sent")


def host_facts(outdir):
    base_img = read_file(BASELINE)
    image = read_file(ART_DIR + "/e2631-uboot-mtd0.bin")
    art = read_file(ART_DIR + "/u-boot.bin")
    facts = {
        "image": {"size": len(image), "sha256": sha_bytes(image),
                  "crc32": "0x%08x" % (zlib.crc32(image) & 0xFFFFFFFF),
                  "sha_ok": sha_bytes(image) == IMAGE_SHA, "size_ok": len(image) == IMAGE_SIZE},
        "u_boot": {"size": len(art), "sha256": sha_bytes(art),
                   "sha_ok": sha_bytes(art) == ART_SHA, "size_ok": len(art) == ART_SIZE,
                   "new_banner_present": NEW_BANNER.encode() in art},
        "structure": {"magic_128s": image[0x10:0x14] == b"128s",
                      "len_field": struct.unpack("<I", image[0x14:0x18])[0],
                      "len_field_ok": struct.unpack("<I", image[0x14:0x18])[0] == len(art),
                      "payload_matches_uboot": image[0x800:0x800 + len(art)] == art,
                      "tail_ff": set(image[0x800 + len(art):]) == {0xFF}},
        "baseline": {"sha256": sha_bytes(base_img), "secondboot_expected": sha_bytes(base_img[:FLASH_OFF]),
                     "tail_expected": sha_bytes(base_img[FLASH_OFF + IMAGES_AREA:TAIL_END])},
        "expected_new_mtd0_sha": sha_bytes(base_img[:FLASH_OFF] + image + base_img[FLASH_OFF + IMAGES_AREA:]),
        "note": "expected sha = current-chip outside-image bytes (verified by region sha) + new image",
    }
    with open(outdir + "/host-facts.json", "w") as fh:
        json.dump(facts, fh, indent=1)
    return facts


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    base.LOG = args.out_dir + "/driver.log"
    hf = host_facts(args.out_dir)
    res = base.pause_capture()
    log("capture paused: " + json.dumps(res))
    hub = base.start_hub(args.out_dir + "/serial.log")
    log("hub pid %s" % hub)
    c = base.Console()
    time.sleep(0.4)
    c.drain()
    c.send(b"\r")
    time.sleep(0.8)
    d = c.read()
    if d:
        c.pending += d
    linux = Linux(c)
    p = {}
    p["version"] = linux.cmd("cat /etc/e2631-version; uname -r; cut -d. -f1 /proc/uptime", 30)
    p["proc_mtd"] = linux.cmd("cat /proc/mtd", 30)
    p["mount"] = linux.cmd("mount | grep -iE 'userdata|mtd10'; echo MOUNT_DONE", 30)
    p["mtd_usage"] = linux.cmd("mtd 2>&1 | head -14", 30)
    p["wan"] = linux.cmd("ip -4 addr show wan | head -4", 30)
    p["region_secondboot"] = linux.cmd("dd if=/dev/mtd0 bs=4096 count=32 2>/dev/null | sha256sum", 60)
    p["region_tailenv"] = linux.cmd("dd if=/dev/mtd0 bs=4096 skip=192 count=64 2>/dev/null | sha256sum", 60)
    p["whole_mtd0"] = linux.cmd("dd if=/dev/mtd0 bs=1M count=1 2>/dev/null | sha256sum", 60)
    p["image_area"] = linux.cmd("dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum", 90)
    p["wget"] = linux.cmd("wget -O /tmp/e2631-new-mtd0.bin " + IMAGE_URL + " 2>&1 | tail -2", 120)
    p["wget_sha"] = linux.cmd("sha256sum /tmp/e2631-new-mtd0.bin", 30)

    def sha_of(key):
        m = re.search(r"\b([0-9a-f]{64})\b", p[key]["output"] or "")
        return m.group(1) if m else None

    geom = {}
    offsets = {}
    for line in (p["proc_mtd"]["output"] or "").splitlines():
        m = re.search(r"mtd(\d+): ([0-9a-f]{8}) ([0-9a-f]{8}) \"([^\"]+)\"", line)
        if m:
            idx, size, name = int(m.group(1)), int(m.group(2), 16), m.group(4)
            offsets[idx] = {"size": size, "name": name}
    # The DTS nests rootfs / rootfs_data / slot1-header inside the slot1 span,
    # so the top-level layout is mtd0..mtd4 -> slot0 -> slot1 -> userdata.
    sizes = {i: offsets[i]["size"] for i in offsets}
    top = sum(sizes[i] for i in range(0, 5))
    slot0_off, slot1_off = top, top + sizes.get(5, 0)
    userdata_off = slot1_off + sizes.get(6, 0)
    for i, v in offsets.items():
        if i <= 4:
            v["chip_off"] = sum(sizes[j] for j in range(0, i))
        elif i == 5:
            v["chip_off"] = slot0_off
        elif i == 6:
            v["chip_off"] = slot1_off
        elif i == 10:
            v["chip_off"] = userdata_off
        else:
            v["chip_off"] = None
    userdata = offsets.get(10)
    geom["partitions"] = offsets
    geom["userdata"] = userdata
    geom["slot0_chip_off"] = slot0_off
    geom["slot1_chip_off"] = slot1_off
    geom["userdata_chip_off"] = userdata_off
    geom["chip_covered_top_level"] = userdata_off + sizes.get(10, 0)
    agg = {
        "version": p["version"]["output"].strip(),
        "whole_mtd0_sha": sha_of("whole_mtd0"),
        "secondboot_sha": sha_of("region_secondboot"),
        "tailenv_sha": sha_of("region_tailenv"),
        "image_area_sha": sha_of("image_area"),
        "wget_sha": sha_of("wget_sha"),
        "geometry": geom,
        "userdata_unmounted": "userdata" not in (p["mount"]["output"] or "") and "mtd10" not in (p["mount"]["output"] or ""),
    }
    agg["ok"] = bool(
        hf["image"]["sha_ok"] and hf["image"]["size_ok"] and hf["u_boot"]["sha_ok"]
        and hf["u_boot"]["size_ok"] and hf["u_boot"]["new_banner_present"]
        and hf["structure"]["magic_128s"] and hf["structure"]["len_field_ok"]
        and hf["structure"]["payload_matches_uboot"] and hf["structure"]["tail_ff"]
        and userdata is not None and userdata["chip_off"] == STAGE_OFF
        and userdata["size"] == 0x2F00000 and agg["userdata_unmounted"]
        and agg["whole_mtd0_sha"] == CURRENT_MTD0_SHA
        and agg["secondboot_sha"] == hf["baseline"]["secondboot_expected"]
        and agg["tailenv_sha"] == hf["baseline"]["tail_expected"]
        and agg["wget_sha"] == IMAGE_SHA
    )
    rep = {"host": hf, "device": agg, "ok": agg["ok"],
           "expected_new_mtd0_sha": hf["expected_new_mtd0_sha"],
           "image_crc32": hf["image"]["crc32"], "ff_crc32": "0x%08x" % FF_CRC}
    with open(args.out_dir + "/preflight.json", "w") as fh:
        json.dump(rep, fh, indent=1)
    base.stop_hub()
    log("preflight ok=%s expected_new_mtd0_sha=%s" % (agg["ok"], hf["expected_new_mtd0_sha"]))
    print(json.dumps(rep, indent=1))
    return 0 if agg["ok"] else 2


def ub_cmd(c, results, text, timeout=180):
    c.pending = b""
    c.send((text + "\r").encode())
    out = fin.wait_prompt(c, timeout)
    txt = (out or b"").decode("latin-1", "replace")
    results.setdefault("uboot_commands", []).append({"cmd": text, "output": txt[-4000:]})
    log("ub cmd: %s ok=%s" % (text, out is not None))
    return txt


def parse_crc(txt):
    m = re.search(r"==>\s*([0-9a-fA-F]{8})", txt)
    return int(m.group(1), 16) if m else None


def session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/driver.log"
    hf = host_facts(outdir)
    image = read_file(ART_DIR + "/e2631-uboot-mtd0.bin")
    expected_sha = hf["expected_new_mtd0_sha"]
    with open(outdir + "/expected-mtd0.bin", "wb") as fh:
        fh.write(read_file(BASELINE)[:FLASH_OFF] + image + read_file(BASELINE)[FLASH_OFF + IMAGES_AREA:])
    res = {"mode": "task61-noserial", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "host": hf, "expected_new_mtd0_sha": expected_sha,
           "image_crc32": hf["image"]["crc32"]}
    c = None
    try:
        cap = base.pause_capture()
        res["capture_before"] = cap
        if not cap.get("free"):
            raise RuntimeError("tty busy after pausing capture")
        res["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        time.sleep(0.4)
        c.drain()
        c.send(b"\r")
        time.sleep(0.8)
        d = c.read()
        if d:
            c.pending += d
        linux = Linux(c)
        # gate: device identity + current chip state
        g = linux.cmd("cat /etc/e2631-version; sha256sum /dev/mtd0", 90)
        gtxt = g["output"]
        res["gate_device"] = g
        if "ImmortalWrt v1.10.0" not in gtxt or CURRENT_MTD0_SHA not in gtxt:
            raise RuntimeError("device identity/current mtd0 gate failed")
        log("gate: device identity and current mtd0 sha verified")
        # Phase A
        res["a_wget"] = linux.cmd("wget -O /tmp/e2631-new-mtd0.bin " + IMAGE_URL + " 2>&1 | tail -2", 120)
        res["a_sha"] = linux.cmd("sha256sum /tmp/e2631-new-mtd0.bin", 30)
        if IMAGE_SHA not in (res["a_sha"]["output"] or ""):
            raise RuntimeError("downloaded image sha mismatch")
        res["a_erase"] = linux.cmd("mtd erase userdata", 180)
        res["a_write"] = linux.cmd("mtd write /tmp/e2631-new-mtd0.bin userdata", 180)
        res["a_readback"] = linux.cmd("dd if=/dev/mtd10 bs=4096 count=160 2>/dev/null | sha256sum", 90)
        res["a_sync"] = linux.cmd("sync; echo SYNCED", 60)
        if IMAGE_SHA not in (res["a_readback"]["output"] or ""):
            raise RuntimeError("userdata read-back sha mismatch")
        if "erased" not in (res["a_erase"]["output"] or "").lower() and "erase" not in (res["a_erase"]["output"] or "").lower():
            log("warn: erase output did not mention erase explicitly")
        log("PHASE A GREEN: staging written and read back")
        # reboot into the old flash U-Boot
        c.pending = b""
        c.send(b"sync; reboot -f\r")
        res["reboot_sent"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        log("reboot -f sent; waiting for the old flash U-Boot banner")
        pat = re.compile(re.escape(OLD_BANNER.encode()))
        deadline = time.time() + 240
        seen = False
        while time.time() < deadline:
            data = c.read()
            if data:
                c.pending += data
                if pat.search(c.pending):
                    seen = True
                    break
            else:
                time.sleep(0.02)
        res["flash_banner_seen"] = seen
        if not seen:
            raise RuntimeError("old flash U-Boot banner not seen after reboot")
        res["flash_stop_autoboot"] = fin.stop_autoboot(c, res, OLD_BANNER, 30)
        ver = ub_cmd(c, res, "version", 60)
        res["flash_version_ok"] = OLD_BANNER in ver
        if not res["flash_version_ok"]:
            raise RuntimeError("flash U-Boot version mismatch")
        log("gate: old flash U-Boot console ready")
        # Phase B
        txt = ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (RAM_IMAGE, STAGE_OFF, IMAGES_AREA), 180)
        res["b_read_staging"] = {"ok": ("%d byte(s)" % IMAGES_AREA) in txt and "Failure" not in txt, "tail": txt[-600:]}
        if not res["b_read_staging"]["ok"]:
            raise RuntimeError("staging read failed")
        txt = ub_cmd(c, res, "crc32 0x%08x 0x%x" % (RAM_IMAGE, IMAGES_AREA), 120)
        got = parse_crc(txt)
        res["b_crc_staging"] = {"got": "0x%08x" % got if got is not None else None,
                                "want": "0x%08x" % IMAGE_CRC, "ok": got == IMAGE_CRC}
        if got != IMAGE_CRC:
            raise RuntimeError("staging crc32 mismatch; refusing to erase")
        log("gate: staging crc32 == 0x%08x" % IMAGE_CRC)
        res["b_erase"] = ub_cmd(c, res, "mtd erase spi-nand0 0x%x 0x%x" % (FLASH_OFF, IMAGES_AREA), 180)
        res["b_erase_ok"] = ("(5 eraseblock(s))" in res["b_erase"] and "Failure" not in res["b_erase"])
        if not res["b_erase_ok"]:
            raise RuntimeError("image-area erase did not report 5 erase blocks")
        log("gate: image area erased (5 blocks)")
        ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (RAM_READ, FLASH_OFF, IMAGES_AREA), 180)
        txt = ub_cmd(c, res, "crc32 0x%08x 0x%x" % (RAM_READ, IMAGES_AREA), 120)
        got = parse_crc(txt)
        res["b_crc_ff"] = {"got": "0x%08x" % got if got is not None else None,
                          "want": "0x%08x" % FF_CRC, "ok": got == FF_CRC}
        if got != FF_CRC:
            raise RuntimeError("post-erase FF sentinel crc32 mismatch; refusing to write")
        log("gate: post-erase FF sentinel crc32 ok")
        res["b_write"] = ub_cmd(c, res, "mtd write spi-nand0 0x%08x 0x%x 0x%x" % (RAM_IMAGE, FLASH_OFF, IMAGES_AREA), 240)
        res["b_write_ok"] = ("Writing %d byte(s) (320 page(s)) at offset 0x00020000" % IMAGES_AREA) in res["b_write"] and "Failure" not in res["b_write"]
        if not res["b_write_ok"]:
            raise RuntimeError("image write did not report a clean 320-page write")
        log("gate: image area written (320 pages)")
        ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (RAM_READ, FLASH_OFF, IMAGES_AREA), 180)
        txt = ub_cmd(c, res, "crc32 0x%08x 0x%x" % (RAM_READ, IMAGES_AREA), 120)
        got = parse_crc(txt)
        res["b_crc_readback"] = {"got": "0x%08x" % got if got is not None else None,
                                 "want": "0x%08x" % IMAGE_CRC, "ok": got == IMAGE_CRC}
        if got != IMAGE_CRC:
            raise RuntimeError("post-write read-back crc32 mismatch")
        res["write_verified"] = True
        log("WRITE VERIFIED. HOLDING. READY FOR POWER CYCLE (one announced cold boot).")
        log("expected new mtd0 sha256: " + expected_sha)
    except Exception as exc:
        res["error"] = str(exc)
        log("SESSION ERROR: " + str(exc))
    finally:
        try:
            base.stop_hub()
        except Exception as exc:
            res["stop_hub_error"] = repr(exc)
        try:
            res["capture_after"] = base.restore_capture()
        except Exception as exc:
            res["capture_after"] = {"ok": False, "error": repr(exc)}
        cmds = [x["cmd"] for x in res.get("uboot_commands", [])]
        res["audit"] = {
            "uboot_mtd_write": [x for x in cmds if x.startswith("mtd write")],
            "uboot_mtd_erase": [x for x in cmds if x.startswith("mtd erase")],
            "serial_transfer_cmds": [x for x in cmds if "loadx" in x or "xmodem" in x],
        }
        res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        res["verdict"] = "GREEN-HOLD" if (
            res.get("write_verified")
            and (res.get("b_crc_staging") or {}).get("ok")
            and (res.get("b_crc_ff") or {}).get("ok")
            and (res.get("b_crc_readback") or {}).get("ok")
            and res.get("b_erase_ok") and res.get("b_write_ok")
            and (res.get("capture_after") or {}).get("ok")
            and len(res["audit"]["uboot_mtd_write"]) == 1
            and len(res["audit"]["uboot_mtd_erase"]) == 1
            and not res["audit"]["serial_transfer_cmds"]
            and not res.get("error")) else "FAIL"
        json.dump(res, open(outdir + "/session-results.json", "w"), indent=1)
        log("VERDICT " + res["verdict"])
    return 0 if res["verdict"] == "GREEN-HOLD" else 2


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    args = ap.parse_args()
    if args.preflight:
        return preflight(args)
    return session(args)


if __name__ == "__main__":
    sys.exit(main())
