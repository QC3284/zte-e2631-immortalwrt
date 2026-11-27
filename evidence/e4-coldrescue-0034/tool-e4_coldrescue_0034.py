#!/usr/bin/env python3
"""Zero-write warm retest of the patch-0034 cold-rescue ordering fix.

Flow: stage 0034 u-boot.bin to userdata -> SSH reboot to the flash E4 prompt
(old image) -> mtd read the staged image -> go 0x47F00000 -> e2631rescue as the
FIRST network command (no e2631net, no e2631boot) -> GET /, GET /status,
POST /flash?mode=validate -> Ctrl-C -> e2631boot back to Linux.

No mtd0 writes: the only flash write is the routine userdata staging.
"""
import base64, hashlib, json, os, re, subprocess, sys, time
sys.path.insert(0, "/home/qc233/zte/e2631-p3")
sys.path.insert(0, "/home/qc233/zte/e2631-p3/e2")
sys.path.insert(0, "/home/qc233/zte/e2631-p3/e2/drivers")
import a1_banner_accept as base
import b1_env_session as b1
import c1b1_final as fin
import c1b1fix_sessionA as sa
import e2_session as e2s
import e2t_session as e2t
import e4_rescue_accept as ev

ART = "/home/qc233/zte/e2631-t5-artifacts/uboot-coldrescue-46046018929/e2631-uboot-46046018929"
UBOOT = ART + "/u-boot.bin"
MTD0_IMG = ART + "/e2631-uboot-mtd0.bin"
U_SHA = "b7ea6bbc138e1b3cbea6389fbaae89419d1d7e46e0668ef88637dd2cd14ac33d"
U_CRC = "0x9f2b707d"
U_SIZE = 365872
NEW_BANNER = "U-Boot 2027.01-rc2-g1673d5c89c7b"
OLD_BANNER = "U-Boot 2027.01-rc2-g30dca5f54503"   # current flash image (E4 patch 0026-0033)
E4_IMG_SHA = "23395533c123ea1099c951fee55a73f264636ca9d33d8298b160efb6d0fdb7d1"
E4_IMG_CRC = "0x1e5ff289"
MTD0_CUR = "d87db54ae30af930b67793defe78d3fb64c5b74315306cea69fe952e42fe1338"
REGION_CUR = "8a38896e9164faa7aca4e9c2737e9d0c2b720f5576ce3ee3ef147109aa0b2bb9"
ENV_BLOCK = "6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893"
SECONDBOOT = "540db4350cca5e77228b65ba3b387ea86be545e7f10a81db19b81d6f7816e1fd"
STAGE_OFF, STAGE_LEN, LOAD = 0x3F00000, 0x80000, 0x47F00000
PAGE_SHA = "30a8f03e46867bb066947a2537f738e0539fd214ae579a287c301d5ff9e39bda"
OUT = "/home/qc233/zte/e2631-p3/e2/e4-rescue/cold-rescue-0034/run-1"
RES = {}
LOG = None

def log(m):
    line = time.strftime("%H:%M:%S") + " " + str(m)
    print(line, flush=True)
    if LOG:
        open(LOG, "a").write(line + "\n")

def sh(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr[-500:]}
    except Exception as e:
        return {"rc": -1, "out": "", "err": str(e)}

def device_facts():
    cmd = ("echo MTD0=$(sha256sum /dev/mtd0 | cut -d' ' -f1); "
           "echo REGION=$(dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d' ' -f1); "
           "echo ENV=$(dd if=/dev/mtd0 bs=4096 skip=192 count=32 2>/dev/null | sha256sum | cut -d' ' -f1); "
           "echo SECONDBOOT=$(dd if=/dev/mtd0 bs=4096 skip=0 count=32 2>/dev/null | sha256sum | cut -d' ' -f1)")
    r = e2s.ssh(cmd, 45)
    out = r.get("out") or ""
    d = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def parse_kv(txt):
    d = {}
    for line in (txt or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def curl(name, args, timeout=40):
    hdr = OUT + "/" + name + ".headers"
    body = OUT + "/" + name + ".body"
    cmd = "curl -sS -m %d -D %s -o %s %s" % (timeout, hdr, body, args)
    r = sh(cmd, timeout + 10)
    status = None
    if os.path.exists(hdr):
        for line in open(hdr, errors="replace"):
            m = re.match(r"HTTP/[\d.]+ (\d+)", line)
            if m:
                status = int(m.group(1))
    text = ""
    if os.path.exists(body):
        try:
            text = open(body, errors="replace").read()
        except Exception:
            text = ""
    return {"rc": r["rc"], "status": status, "headers_path": hdr, "body_path": body,
            "body_text": text[:2000], "stderr": r["err"]}

def main():
    global LOG
    os.makedirs(OUT, exist_ok=True)
    LOG = OUT + "/driver.log"
    RES["started"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    RES["artifact"] = {"path": ART, "u_boot_sha": U_SHA, "u_boot_crc": U_CRC,
                       "new_banner": NEW_BANNER, "mtd0_img_sha": E4_IMG_SHA,
                       "mtd0_img_crc": E4_IMG_CRC}
    c = None
    try:
        b1.make_askpass()
        RES["route"] = b1.ensure_direct_link()
        if not RES["route"].get("ok"):
            raise RuntimeError("no direct route to the device")
        RES["device_before"] = device_facts()
        if (RES["device_before"].get("MTD0") != MTD0_CUR
                or RES["device_before"].get("REGION") != REGION_CUR
                or RES["device_before"].get("ENV") != ENV_BLOCK
                or RES["device_before"].get("SECONDBOOT") != SECONDBOOT):
            raise RuntimeError("device flash is not the expected E4 baseline: %r" % RES["device_before"])
        art = e2s.artifact_facts(UBOOT)
        padded = e2s.pad_artifact(UBOOT, OUT)
        RES["artifact_facts"] = {k: art.get(k) for k in ("sha256", "crc32", "size", "banner_token")}
        if art.get("sha256") != U_SHA or art.get("crc32") != U_CRC or art.get("size") != U_SIZE:
            raise RuntimeError("artifact pins do not match")
        if art.get("banner_token") != NEW_BANNER:
            raise RuntimeError("artifact banner token mismatch: %r" % art.get("banner_token"))
        RES["staging"] = e2t.stage_userdata_ssh(art, padded, OUT)
        if not RES["staging"].get("ok"):
            raise RuntimeError("userdata staging failed")
        log("STAGING GREEN")

        RES["capture_pause"] = base.pause_capture()
        RES["hub_pid"] = base.start_hub(OUT + "/serial.log")
        c = base.Console()
        time.sleep(0.4); c.drain()
        b1.ssh_run("sync; (sleep 1; reboot -f) </dev/null >/dev/null 2>&1 &", timeout=30)
        _head = c.wait(OLD_BANNER.encode(), 180)
        RES["flash_banner"] = bool(_head)
        if _head:
            c.pending = _head + c.pending
        if not RES["flash_banner"]:
            raise RuntimeError("flash E4 banner not seen after reboot")
        RES["flash_stop"] = fin.stop_autoboot(c, RES, OLD_BANNER, 30)
        if not RES["flash_stop"].get("prompt"):
            raise RuntimeError("no flash U-Boot prompt")
        txt = ev.ub_cmd(c, RES, "version", 60)
        RES["flash_version_ok"] = OLD_BANNER in (txt or "")
        if not RES["flash_version_ok"]:
            raise RuntimeError("flash U-Boot version mismatch")

        txt = ev.ub_cmd(c, RES, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (LOAD, STAGE_OFF, STAGE_LEN), 300)
        RES["staging_read_ok"] = ("%d byte(s)" % STAGE_LEN) in (txt or "") and "Failure" not in (txt or "")
        if not RES["staging_read_ok"]:
            raise RuntimeError("staged image read failed")
        crc_txt = ev.ub_cmd(c, RES, "crc32 0x%08x 0x%x" % (LOAD, U_SIZE), 120)
        got = e2s.parse_crc(crc_txt)
        RES["staging_crc"] = {"got": "0x%08x" % got if got is not None else None, "want": U_CRC,
                              "ok": got is not None and ("0x%08x" % got) == U_CRC}
        if not RES["staging_crc"]["ok"]:
            raise RuntimeError("staged 0034 image crc mismatch")

        c.pending = b""; c.send(b"go 0x47f00000\r")
        RES["go_sent"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        _head = c.wait(NEW_BANNER.encode(), 90)
        RES["new_banner"] = bool(_head)
        if _head:
            c.pending = _head + c.pending
        if not RES["new_banner"]:
            raise RuntimeError("0034 banner not seen after go")
        RES["new_stop"] = fin.stop_autoboot(c, RES, NEW_BANNER, 20)
        if not RES["new_stop"].get("prompt"):
            raise RuntimeError("no 0034 prompt")
        txt = ev.ub_cmd(c, RES, "version", 60)
        RES["new_version_ok"] = NEW_BANNER in (txt or "")
        if not RES["new_version_ok"]:
            raise RuntimeError("0034 version mismatch")
        RES["commands_before_rescue"] = [x["cmd"] for x in RES.get("uboot_commands", [])]
        if any(x.strip().startswith("e2631net") or x.strip() == "e2631boot" for x in RES["commands_before_rescue"]):
            raise RuntimeError("e2631net/e2631boot ran before the rescue-first test")

        log("RESCUE-FIRST: sending e2631rescue without e2631net")
        c.pending = b""
        c.send(b"e2631rescue\r")
        marker = c.wait(rb"e2631rescue: open http://", 90)
        RES["rescue_marker"] = bool(marker)
        txt = (marker or b"").decode("latin-1", "replace")
        RES["rescue_tail"] = txt[-2500:]
        RES["phy_done"] = "auto negotiation to complete........ done" in txt
        RES["phy_timeout"] = "TIMEOUT !" in txt
        RES["lan1_up"] = "zx279128s: lan1 up, 1000 Mbit/s full duplex" in txt
        if not RES["rescue_marker"]:
            # failure diagnostics: the five clock registers, no 0x9FE00000
            RES["clock_regs"] = {}
            for a in ("0x94000050 2", "0x94000008 1", "0x94100010 1", "0x9400004c 1", "0x9a100004 1"):
                t = ev.ub_cmd(c, RES, "md.l " + a, 30)
                RES["clock_regs"][a] = (t or "")[-600:]
            raise RuntimeError("0034 rescue-first still failed to reach HTTP-ready")

        time.sleep(0.5)
        RES["page"] = curl("page", "http://192.168.1.1/")
        RES["status_before"] = curl("status-before", "http://192.168.1.1/status")
        status_kv = parse_kv(RES["status_before"].get("body_text"))
        RES["status_before_kv"] = status_kv
        if RES["page"].get("status") != 200:
            raise RuntimeError("GET / failed: %r" % RES["page"])
        raw = open(OUT + "/page.body", "rb").read()
        import gzip
        try:
            page_raw = gzip.decompress(raw)
        except Exception as e:
            page_raw = b""
            RES["page_gunzip_error"] = str(e)
        RES["page_facts"] = {"gzip_sha": hashlib.sha256(raw).hexdigest(),
                             "raw_sha": hashlib.sha256(page_raw).hexdigest(),
                             "raw_bytes": len(page_raw)}
        RES["page_ok"] = hashlib.sha256(page_raw).hexdigest() == PAGE_SHA

        # validate mode: body is the 0034 mtd0 image; no write confirm header
        post = "curl -sS -m 60 -D %s -o %s -X POST -H 'Content-Type: application/octet-stream' -H 'X-E2631-SHA256: %s' --data-binary @%s 'http://192.168.1.1/flash?mode=validate'" % (
            OUT + "/validate.headers", OUT + "/validate.body", E4_IMG_SHA, MTD0_IMG)
        RES["validate_curl"] = sh(post, 90)
        status = None
        for line in open(OUT + "/validate.headers", errors="replace"):
            m = re.match(r"HTTP/[\d.]+ (\d+)", line)
            if m:
                status = int(m.group(1))
        RES["validate"] = {"status": status,
                           "body": open(OUT + "/validate.body", errors="replace").read()[:2000]}
        kv = parse_kv(RES["validate"]["body"])
        RES["validate_ok"] = status == 200 and kv.get("result") == "ok" and kv.get("sha_match") == "ok"
        RES["status_after"] = curl("status-after", "http://192.168.1.1/status")
        RES["status_after_kv"] = parse_kv(RES["status_after"].get("body_text"))
        RES["readonly_ok"] = (RES["validate_ok"]
                              and RES["status_after_kv"].get("stage") == "idle"
                              and RES["status_after_kv"].get("sha_match") == "ok")

        c.pending = b""; c.send(b"\x03")
        left = c.wait(rb"e2631rescue: left the rescue mode", 20)
        RES["rescue_left"] = bool(left)
        c.pending = b""; c.send(b"e2631boot\r")
        linux = c.wait(rb"Starting kernel|Please press Enter", 150)
        RES["linux_start"] = bool(linux)
        RES["boot_tail"] = (linux or b"").decode("latin-1", "replace")[-1200:]
    except Exception as e:
        RES["error"] = "%s: %s" % (type(e).__name__, e)
        log("SESSION ERROR " + RES["error"])
    finally:
        try:
            if c is not None:
                open(OUT + "/console-history.txt", "wb").write(bytes(c.history))
        except Exception:
            pass
        try: base.stop_hub()
        except Exception as e: RES["stop_hub_error"] = str(e)
        try: RES["capture_after"] = base.restore_capture()
        except Exception as e: RES["capture_after"] = {"ok": False, "error": str(e)}
        try:
            b1.make_askpass(); b1.ensure_direct_link()
            for _ in range(10):
                d = device_facts()
                if d.get("MTD0"):
                    RES["device_after"] = d
                    break
                time.sleep(10)
        except Exception as e:
            RES["device_after"] = {"error": str(e)}
        RES["checks"] = {
            "staging": bool((RES.get("staging") or {}).get("ok")),
            "flash_banner": RES.get("flash_banner"),
            "staging_crc": bool((RES.get("staging_crc") or {}).get("ok")),
            "new_banner": RES.get("new_banner"),
            "rescue_marker": RES.get("rescue_marker"),
            "phy_done": RES.get("phy_done"),
            "lan1_up": RES.get("lan1_up"),
            "page_ok": RES.get("page_ok"),
            "validate_ok": RES.get("validate_ok"),
            "readonly_ok": RES.get("readonly_ok"),
            "linux_back": RES.get("linux_start"),
            "mtd0_unchanged": (RES.get("device_after") or {}).get("MTD0") == MTD0_CUR,
            "region_unchanged": (RES.get("device_after") or {}).get("REGION") == REGION_CUR,
            "capture_after": bool((RES.get("capture_after") or {}).get("ok")),
            "no_error": not RES.get("error"),
        }
        RES["verdict"] = "GREEN" if all(v is True for k, v in RES["checks"].items()) else "FAIL"
        RES["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        json.dump(RES, open(OUT + "/results.json", "w"), indent=1)
        log("VERDICT " + RES["verdict"])
    return 0 if RES.get("verdict") == "GREEN" else 1

if __name__ == "__main__":
    sys.exit(main())
