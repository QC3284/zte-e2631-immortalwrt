#!/usr/bin/env python3
"""task-79 final: flash patch-0034 into mtd0 through one e2631rescue write,
then verify the flashed image's cold-prompt rescue and return to Linux."""
import base64, hashlib, json, os, re, subprocess, sys, time, zlib
P3 = "/home/qc233/zte/e2631-p3"
E2 = P3 + "/e2"
for p in (P3, E2, E2 + "/drivers"):
    sys.path.insert(0, p)
import a1_banner_accept as base
import b1_env_session as b1
import c1b1_final as fin
import e2_session as e2s
import e2t_session as e2t
import e4_rescue_accept as ev

ART = "/home/qc233/zte/e2631-t5-artifacts/uboot-coldrescue-46046018929/e2631-uboot-46046018929"
UBOOT = ART + "/u-boot.bin"
IMAGE = ART + "/e2631-uboot-mtd0.bin"
BASE_MTD0 = P3 + "/b1-env-session/resume-1/target-mtd0.bin"
OLD_IMAGE = "/home/qc233/zte/e2631-t5-artifacts/uboot-e4hdr-46036894542/e2631-uboot-46036894542/e2631-uboot-mtd0.bin"
OUT_DEFAULT = E2 + "/e4-rescue/final-0034/run-1"

U_SHA = "b7ea6bbc138e1b3cbea6389fbaae89419d1d7e46e0668ef88637dd2cd14ac33d"
U_CRC = "0x9f2b707d"
U_SIZE = 365872
NEW_BANNER = "U-Boot 2027.01-rc2-g1673d5c89c7b"
OLD_BANNER = "U-Boot 2027.01-rc2-g30dca5f54503"
IMG_SHA = "23395533c123ea1099c951fee55a73f264636ca9d33d8298b160efb6d0fdb7d1"
IMG_CRC = "0x1e5ff289"
IMG_SIZE = 655360
MTD0_CUR = "d87db54ae30af930b67793defe78d3fb64c5b74315306cea69fe952e42fe1338"
REGION_CUR = "8a38896e9164faa7aca4e9c2737e9d0c2b720f5576ce3ee3ef147109aa0b2bb9"
ENV_BLOCK = "6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893"
SECONDBOOT = "540db4350cca5e77228b65ba3b387ea86be545e7f10a81db19b81d6f7816e1fd"
SEC_CRC = "0x9848a667"
ENV_STORED = "0xf95a816e"
ENV_REGION = "0xe826c394"
FINAL_MTD0 = "ac06d7bcccfc1ed2baa18e792cffce8c7912981eb5491e5b3ea67b1a1172325f"
STAGE_OFF, STAGE_LEN, LOAD = 0x3F00000, 0x80000, 0x47F00000
REGION_OFF, REGION_LEN = 0x20000, 0xA0000
REGION_RAM, ENV_RAM, SEC_RAM = 0x46000000, 0x47000000, 0x48000000
PAGE_SHA = "30a8f03e46867bb066947a2537f738e0539fd214ae579a287c301d5ff9e39bda"
RES = {"uboot_commands": [], "status_polls": []}
LOG = None

def log(m):
    line = time.strftime("%H:%M:%S") + " " + str(m)
    print(line, flush=True)
    if LOG:
        open(LOG, "a").write(line + "\n")

def sh(cmd, timeout=40):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr[-500:]}
    except Exception as e:
        return {"rc": -1, "out": "", "err": str(e)}

def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

def curl(name, url, method=None, body_file=None, headers=()):
    hdr = os.path.join(OUT, name + ".headers")
    body = os.path.join(OUT, name + ".body")
    cmd = ["curl", "-sS", "-m", "90", "-D", hdr, "-o", body]
    if method:
        cmd += ["-X", method]
    for h in headers:
        cmd += ["-H", h]
    if body_file:
        cmd += ["--data-binary", "@" + body_file]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    status = None
    try:
        for line in open(hdr, errors="replace"):
            m = re.match(r"HTTP/[\d.]+ (\d+)", line)
            if m:
                status = int(m.group(1))
    except Exception:
        pass
    text = ""
    try:
        text = open(body, errors="replace").read()
    except Exception:
        pass
    return {"status": status, "body": text[:4000], "headers": hdr, "body_path": body,
            "rc": r.returncode, "stderr": r.stderr[-300:]}

def kv(txt):
    d = {}
    for line in (txt or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def wait_status(out, timeout=180):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = curl("status-%03d" % len(RES["status_polls"]), ev.RESCUE_URL + "/status")
        d = kv(r.get("body"))
        last = {"http": r.get("status"), "kv": d}
        RES["status_polls"].append(last)
        stage = d.get("stage")
        if stage and stage != "idle":
            log("status stage=%s progress=%s" % (stage, d.get("progress")))
        if stage == "done":
            return last
        if stage == "error":
            return last
        time.sleep(0.8)
    return last

def region_readback(c, tag):
    txt = ev.ub_cmd(c, RES, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (REGION_RAM, REGION_OFF, REGION_LEN), 300)
    ok = ("%d byte(s)" % REGION_LEN) in (txt or "") and "Failure" not in (txt or "") and "-74" not in (txt or "")
    crc_txt = ev.ub_cmd(c, RES, "crc32 0x%08x 0x%x" % (REGION_RAM, REGION_LEN), 120)
    crc = e2s.parse_crc(crc_txt)
    return {"tag": tag, "read_ok": ok, "crc": "0x%08x" % crc if crc is not None else None,
            "read_tail": (txt or "")[-400:]}

def env_readback(c):
    ev.ub_cmd(c, RES, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (ENV_RAM, 0xC0000, 0x20000), 240)
    md = ev.ub_cmd(c, RES, "md 0x%08x 1" % ENV_RAM, 30)
    stored = ev.md_first_word(md)
    crc_txt = ev.ub_cmd(c, RES, "crc32 0x%08x 0x%x" % (ENV_RAM, 0x20000), 240)
    crc = e2s.parse_crc(crc_txt)
    return {"stored": "0x%08x" % stored if stored is not None else None,
            "region": "0x%08x" % crc if crc is not None else None}

def sec_readback(c):
    ev.ub_cmd(c, RES, "mtd read spi-nand0 0x%08x 0x0 0x20000" % SEC_RAM, 240)
    crc_txt = ev.ub_cmd(c, RES, "crc32 0x%08x 0x20000" % SEC_RAM, 240)
    crc = e2s.parse_crc(crc_txt)
    return {"crc": "0x%08x" % crc if crc is not None else None}

def device_facts():
    cmd = ("echo MTD0=$(sha256sum /dev/mtd0 | cut -d' ' -f1); "
           "echo REGION=$(dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d' ' -f1); "
           "echo ENV=$(dd if=/dev/mtd0 bs=4096 skip=192 count=32 2>/dev/null | sha256sum | cut -d' ' -f1); "
           "echo SECONDBOOT=$(dd if=/dev/mtd0 bs=4096 skip=0 count=32 2>/dev/null | sha256sum | cut -d' ' -f1); "
           "echo PANICS=$(dmesg | grep -ci -E 'panic|Oops' || true); "
           "echo MT7916=$(dmesg | grep -c 'e2631-wifi-boot: MT7916 ready' || true); "
           "echo VERSION=$(cat /etc/e2631-version); echo KERNEL=$(uname -r); "
           "echo FWSLOT=$(e2631-fwslot info -j 2>/dev/null | tr -d '\\n' | head -c 500)")
    r = e2s.ssh(cmd, 90)
    out = r.get("out") or ""
    d = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def expected_final():
    base = open(BASE_MTD0, "rb").read()
    img = open(IMAGE, "rb").read()
    cur = base[:REGION_OFF] + open(OLD_IMAGE, "rb").read() + base[0xC0000:]
    fin = base[:REGION_OFF] + img + base[0xC0000:]
    return {"cur_sha": hashlib.sha256(cur).hexdigest(),
            "final_sha": hashlib.sha256(fin).hexdigest(),
            "final_ok": hashlib.sha256(fin).hexdigest() == FINAL_MTD0}

def start_rescue_first(c, tag):
    assert not any(x["cmd"].startswith(("e2631net", "e2631boot")) for x in RES["uboot_commands"]), \
        "a network/boot command ran before the rescue-first check"
    RES["uboot_commands"].append({"cmd": "e2631rescue", "why": tag})
    c.pending = b""
    c.send(b"e2631rescue\r")
    marker = c.wait(rb"e2631rescue: open http://", 90)
    txt = (marker or b"").decode("latin-1", "replace")
    rec = {"marker": bool(marker), "tail": txt[-2500:],
           "phy_done": "auto negotiation to complete........ done" in txt,
           "phy_timeout": "TIMEOUT !" in txt,
           "lan1_up": "zx279128s: lan1 up, 1000 Mbit/s full duplex" in txt}
    return rec

def stop_rescue(c):
    c.pending = b""; c.send(b"\x03")
    left = c.wait(rb"e2631rescue: left the rescue mode", 25)
    if not left:
        c.send(b"\x03\r")
        left = c.wait(rb"e2631rescue: left the rescue mode", 15)
    return bool(left)

def main():
    global LOG, OUT
    OUT = OUT_DEFAULT
    os.makedirs(OUT, exist_ok=True)
    LOG = OUT + "/driver.log"
    RES["started"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    c = None
    try:
        b1.make_askpass()
        RES["route"] = b1.ensure_direct_link()
        if not RES["route"].get("ok"):
            raise RuntimeError("no direct route")
        RES["device_before"] = device_facts()
        db = RES["device_before"]
        if (db.get("MTD0") != MTD0_CUR or db.get("REGION") != REGION_CUR
                or db.get("ENV") != ENV_BLOCK or db.get("SECONDBOOT") != SECONDBOOT):
            raise RuntimeError("device baseline mismatch: %r" % db)
        RES["expected"] = expected_final()
        if not RES["expected"]["cur_ok"] if "cur_ok" in RES["expected"] else False:
            raise RuntimeError("expected-final reconstruction mismatch")
        if RES["expected"]["cur_sha"] != MTD0_CUR:
            raise RuntimeError("reconstruction current sha mismatch")
        if RES["expected"]["final_sha"] != FINAL_MTD0:
            raise RuntimeError("reconstruction final sha mismatch")
        art = e2s.artifact_facts(UBOOT)
        padded = e2s.pad_artifact(UBOOT, OUT)
        RES["artifact"] = {k: art.get(k) for k in ("sha256", "crc32", "size", "banner_token")}
        if (art.get("sha256") != U_SHA or art.get("crc32") != U_CRC
                or art.get("size") != U_SIZE or art.get("banner_token") != NEW_BANNER):
            raise RuntimeError("artifact pins mismatch")
        RES["image"] = {"sha256": sha_file(IMAGE), "size": os.path.getsize(IMAGE)}
        if RES["image"]["sha256"] != IMG_SHA or RES["image"]["size"] != IMG_SIZE:
            raise RuntimeError("mtd0 image pins mismatch")
        RES["staging"] = e2t.stage_userdata_ssh(art, padded, OUT)
        if not RES["staging"].get("ok"):
            raise RuntimeError("userdata staging failed")
        log("STAGING GREEN")

        RES["capture_pause"] = base.pause_capture()
        RES["hub_pid"] = base.start_hub(OUT + "/serial.log")
        c = base.Console(); time.sleep(0.4); c.drain()
        b1.ssh_run("sync; (sleep 1; reboot -f) </dev/null >/dev/null 2>&1 &", timeout=30)
        head = c.wait(OLD_BANNER.encode(), 180)
        RES["flash_banner"] = bool(head)
        if head:
            c.pending = head + c.pending
        if not RES["flash_banner"]:
            raise RuntimeError("flash E4 banner not seen")
        RES["flash_stop"] = fin.stop_autoboot(c, RES, OLD_BANNER, 30)
        if not RES["flash_stop"].get("prompt"):
            raise RuntimeError("no flash prompt")
        txt = ev.ub_cmd(c, RES, "version", 60)
        RES["flash_version"] = OLD_BANNER in (txt or "")
        if not RES["flash_version"]:
            raise RuntimeError("flash version mismatch")
        txt = ev.ub_cmd(c, RES, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (LOAD, STAGE_OFF, STAGE_LEN), 300)
        RES["staging_read"] = ("%d byte(s)" % STAGE_LEN) in (txt or "") and "Failure" not in (txt or "")
        if not RES["staging_read"]:
            raise RuntimeError("staging read failed")
        crc_txt = ev.ub_cmd(c, RES, "crc32 0x%08x 0x%x" % (LOAD, U_SIZE), 120)
        got = e2s.parse_crc(crc_txt)
        RES["staging_crc"] = {"got": "0x%08x" % got if got is not None else None, "ok": got is not None and ("0x%08x" % got) == U_CRC}
        if not RES["staging_crc"]["ok"]:
            raise RuntimeError("staging crc mismatch")
        c.pending = b""; c.send(b"go 0x47f00000\r")
        RES["go_sent"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        head = c.wait(NEW_BANNER.encode(), 90)
        RES["new_banner"] = bool(head)
        if head:
            c.pending = head + c.pending
        if not RES["new_banner"]:
            raise RuntimeError("0034 banner not seen after go")
        RES["new_stop"] = fin.stop_autoboot(c, RES, NEW_BANNER, 20)
        if not RES["new_stop"].get("prompt"):
            raise RuntimeError("no 0034 prompt")
        txt = ev.ub_cmd(c, RES, "version", 60)
        RES["new_version"] = NEW_BANNER in (txt or "")
        if not RES["new_version"]:
            raise RuntimeError("0034 version mismatch")
        RES["env_block_diag"] = ev.env_block_diag(c, RES)
        RES["env_sanity"] = ev.env_sanity(c, RES, bytes(c.history or b"").decode("latin-1", "replace"))
        RES["rescue_presence"] = ev.rescue_presence(c, RES)
        log("RAM prompt ready")

        r = start_rescue_first(c, "write")
        RES["write_rescue"] = r
        if not (r["marker"] and r["phy_done"] and r["lan1_up"]):
            raise RuntimeError("write rescue failed to come up: %r" % r)
        post = curl("write-post", ev.RESCUE_URL + "/flash?mode=write", method="POST",
                    body_file=IMAGE,
                    headers=("Content-Type: application/octet-stream",
                             "X-E2631-SHA256: " + IMG_SHA,
                             "X-E2631-Confirm: write", "Expect:"))
        RES["write_post"] = post
        log("WRITE POST status=%s body=%r" % (post.get("status"), post.get("body")[:200]))
        done = wait_status(OUT)
        RES["write_done"] = done
        dkv = (done or {}).get("kv") or {}
        if not (dkv.get("stage") == "done" and dkv.get("result") == "ok"
                and dkv.get("crc32") == IMG_CRC and dkv.get("sha_match") == "ok"):
            raise RuntimeError("write did not finish cleanly: %r" % done)
        RES["write_done_ok"] = True
        log("WRITE DONE: crc32=%s result=%s" % (dkv.get("crc32"), dkv.get("result")))

        RES["rescue_left_after_write"] = stop_rescue(c)
        RES["readback_region"] = region_readback(c, "after-write")
        RES["readback_env"] = env_readback(c)
        RES["readback_secondboot"] = sec_readback(c)
        RES["readback_ok"] = (RES["readback_region"].get("read_ok")
                              and RES["readback_region"].get("crc") == IMG_CRC
                              and RES["readback_env"].get("stored") == ENV_STORED
                              and RES["readback_env"].get("region") == ENV_REGION
                              and RES["readback_secondboot"].get("crc") == SEC_CRC)
        if not RES["readback_ok"]:
            raise RuntimeError("independent readback mismatch: %r" % {
                "region": RES["readback_region"], "env": RES["readback_env"],
                "secondboot": RES["readback_secondboot"]})
        log("READBACK GREEN: region=%s env=%s/%s secondboot=%s" % (
            RES["readback_region"].get("crc"), RES["readback_env"].get("stored"),
            RES["readback_env"].get("region"), RES["readback_secondboot"].get("crc")))

        c.pending = b""; c.send(b"reset\r")
        RES["reset_sent"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        head = c.wait(NEW_BANNER.encode(), 120)
        RES["reset_banner"] = bool(head)
        if head:
            c.pending = head + c.pending
        if not RES["reset_banner"]:
            raise RuntimeError("reset did not boot the flashed 0034 image")
        RES["reset_stop"] = fin.stop_autoboot(c, RES, NEW_BANNER, 20)
        if not RES["reset_stop"].get("prompt"):
            raise RuntimeError("no flash 0034 prompt after reset")
        txt = ev.ub_cmd(c, RES, "version", 60)
        RES["flash_0034_version"] = NEW_BANNER in (txt or "")
        if not RES["flash_0034_version"]:
            raise RuntimeError("flash 0034 version mismatch")
        log("RESET GREEN: flash 0034 prompt")

        r = start_rescue_first(c, "flashed-resident")
        RES["resident_rescue"] = r
        if not (r["marker"] and r["phy_done"] and r["lan1_up"]):
            raise RuntimeError("flashed-resident rescue failed: %r" % r)
        RES["resident_page"] = curl("resident-page", ev.RESCUE_URL + "/")
        raw = open(RES["resident_page"]["body_path"], "rb").read()
        try:
            import gzip
            page_raw = gzip.decompress(raw)
        except Exception:
            page_raw = b""
        RES["resident_page_sha"] = hashlib.sha256(page_raw).hexdigest()
        RES["resident_page_ok"] = (RES["resident_page"].get("status") == 200
                                   and RES["resident_page_sha"] == PAGE_SHA)
        RES["resident_status_before"] = curl("resident-status-before", ev.RESCUE_URL + "/status")
        RES["resident_validate"] = curl("resident-validate", ev.RESCUE_URL + "/flash?mode=validate",
                                        method="POST", body_file=IMAGE,
                                        headers=("Content-Type: application/octet-stream",
                                                 "X-E2631-SHA256: " + IMG_SHA, "Expect:"))
        vkv = kv(RES["resident_validate"].get("body"))
        RES["resident_status_after"] = curl("resident-status-after", ev.RESCUE_URL + "/status")
        skv = kv(RES["resident_status_after"].get("body"))
        RES["resident_validate_ok"] = (RES["resident_validate"].get("status") == 200
                                       and vkv.get("result") == "ok" and vkv.get("sha_match") == "ok")
        RES["resident_readonly_ok"] = (RES["resident_validate_ok"]
                                       and skv.get("stage") == "idle" and skv.get("sha_match") == "ok")
        RES["resident_rescue_left"] = stop_rescue(c)
        log("RESIDENT RESCUE: page=%s validate=%s readonly=%s" % (
            RES["resident_page_ok"], RES["resident_validate_ok"], RES["resident_readonly_ok"]))
        if not (RES["resident_page_ok"] and RES["resident_readonly_ok"]):
            raise RuntimeError("flashed-resident rescue HTTP/validate failed")

        c.pending = b""; c.send(b"e2631boot\r")
        linux = c.wait(rb"Starting kernel|Please press Enter", 150)
        RES["linux_start"] = bool(linux)
        RES["boot_tail"] = (linux or b"").decode("latin-1", "replace")[-1000:]
        if not RES["linux_start"]:
            raise RuntimeError("e2631boot did not start the kernel")
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
            deadline = time.time() + 300
            RES["postcheck_attempts"] = []
            while time.time() < deadline:
                d = device_facts()
                RES["postcheck_attempts"].append({
                    "mt7916": d.get("MT7916"), "panics": d.get("PANICS"),
                    "mtd0": d.get("MTD0"), "uptime": d.get("UPTIME")})
                if d.get("MTD0"):
                    RES["device_after"] = d
                    if (d.get("MTD0") == FINAL_MTD0 and d.get("PANICS") == "0"
                            and d.get("MT7916") == "1"):
                        break
                time.sleep(10)
        except Exception as e:
            RES["device_after"] = {"error": str(e)}
        after = RES["device_after"] or {}
        cmds = [x["cmd"] for x in RES.get("uboot_commands", [])]
        RES["audit"] = {
            "uboot_commands": cmds,
            "forbidden": [x for x in cmds if ev.FORBIDDEN_RE.search(x)],
            "write_posts": [{"status": (RES.get("write_post") or {}).get("status"),
                             "result": kv((RES.get("write_post") or {}).get("body")).get("result")}],
            "reset": RES.get("reset_sent"),
        }
        checks = {
            "artifact_pins": RES.get("artifact", {}).get("sha256") == U_SHA,
            "image_pins": RES.get("image", {}).get("sha256") == IMG_SHA,
            "staging": bool((RES.get("staging") or {}).get("ok")),
            "flash_banner": RES.get("flash_banner"),
            "staging_crc": bool((RES.get("staging_crc") or {}).get("ok")),
            "ram_banner": RES.get("new_banner"),
            "env_sanity": bool((RES.get("env_sanity") or {}).get("env_sanity_ok")),
            "write_done": (RES.get("write_done") or {}).get("kv", {}).get("crc32") == IMG_CRC,
            "readback": RES.get("readback_ok"),
            "reset_banner": RES.get("reset_banner"),
            "flash_0034_version": RES.get("flash_0034_version"),
            "resident_phy": bool((RES.get("resident_rescue") or {}).get("phy_done")),
            "resident_page": RES.get("resident_page_ok"),
            "resident_validate": RES.get("resident_validate_ok"),
            "resident_readonly": RES.get("resident_readonly_ok"),
            "linux_back": RES.get("linux_start"),
            "mtd0_final": after.get("MTD0") == FINAL_MTD0,
            "region_final": after.get("REGION") == IMG_SHA,
            "env_after": after.get("ENV") == ENV_BLOCK,
            "secondboot_after": after.get("SECONDBOOT") == SECONDBOOT,
            "panics_zero": after.get("PANICS") == "0",
            "mt7916": after.get("MT7916") == "1",
            "capture_after": bool((RES.get("capture_after") or {}).get("ok")),
            "no_error": not RES.get("error"),
            "no_forbidden": not RES["audit"]["forbidden"],
        }
        RES["checks"] = checks
        RES["verdict"] = "GREEN" if all(v is True for v in checks.values()) else "FAIL"
        RES["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        json.dump(RES, open(OUT + "/results.json", "w"), indent=1)
        log("VERDICT " + RES["verdict"])
    return 0 if RES.get("verdict") == "GREEN" else 2

if __name__ == "__main__":
    sys.exit(main())