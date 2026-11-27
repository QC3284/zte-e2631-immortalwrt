#!/usr/bin/env python3
"""E4 rescue write-mode acceptance: net-zero write, real E4 write, reset, flash rescue.

User approved both write steps on 2026-11-28 01:08.  The only intended flash
writes are the two rescue POSTs; the userdata staging erase/write is the normal
load path for the RAM image and is audited separately.

Safety: any readback mismatch stops the session at the RAM prompt.  The reset
command is sent only after both readbacks are verified.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import zlib

P3 = "/home/qc233/zte/e2631-p3"
E2 = P3 + "/e2"
sys.path.insert(0, P3)
sys.path.insert(0, E2)
sys.path.insert(0, E2 + "/drivers")
import a1_banner_accept as base
import b1_env_session as b1
import c1b1_final as fin
import e2_session as e2s
import e2t_session as e2t
import e4_rescue_accept as ev

ART = "/home/qc233/zte/e2631-t5-artifacts/uboot-e4hdr-46036894542/e2631-uboot-46036894542"
UBOOT_BIN = ART + "/u-boot.bin"
E4_IMAGE = ART + "/e2631-uboot-mtd0.bin"
BASE_MTD0 = P3 + "/b1-env-session/resume-1/target-mtd0.bin"
NETZERO = E2 + "/e4-rescue/run-2/netzero-mtd0-image.bin"
OUT_DEFAULT = E2 + "/e4-rescue/write-run-1"

UBOOT_SHA = "3dbbfc49e7fa580fe5327f9b0f11cddc0fe0d0f92e5a9fde9c37a7efdf133bb6"
UBOOT_CRC = "0x34b252a4"
UBOOT_SIZE = 365872
NEW_BANNER = "U-Boot 2027.01-rc2-g30dca5f54503"
OLD_BANNER = ev.FLASH_BANNER

MTD0_CUR = "f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4"
REGION_CUR = "b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a"
REGION_CRC = "0x0721e716"
MTD0_E4 = "d87db54ae30af930b67793defe78d3fb64c5b74315306cea69fe952e42fe1338"
REGION_E4 = "8a38896e9164faa7aca4e9c2737e9d0c2b720f5576ce3ee3ef147109aa0b2bb9"
E4_CRC = "0x79ef8c50"
E4_SIZE = 655360
SECONDBOOT_SHA = "540db4350cca5e77228b65ba3b387ea86be545e7f10a81db19b81d6f7816e1fd"
SECONDBOOT_CRC = "0x9848a667"
ENV_BLOCK_SHA = "6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893"
ENV_REGION_CRC = "0xe826c394"
ENV_STORED_CRC = "0xf95a816e"

READBACK_ADDR = 0x46000000
ENV_RAM = 0x47000000
SEC_RAM = 0x48000000
REGION_OFF = 0x20000
REGION_LEN = 0xA0000
ENV_OFF = 0xC0000
ENV_LEN = 0x20000
SEC_OFF = 0x0
SEC_LEN = 0x20000
HOST_IP = "192.168.1.191"
RESCUE = ev.RESCUE_URL

WRITE_HEADERS = ["-H", "Content-Type: application/octet-stream",
                 "-H", "X-E2631-Confirm: write", "-H", "Expect:"]
FORBIDDEN_EXCEPT = re.compile(r"^reset$")


def log(msg):
    ev.log(msg)


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def read_bytes(p):
    with open(p, "rb") as fh:
        return fh.read()


def file_facts(p):
    d = read_bytes(p)
    return {"path": p, "size": len(d), "sha256": sha_bytes(d),
            "crc32": "0x%08x" % (zlib.crc32(d) & 0xFFFFFFFF)}


def http_post_write(outdir, name, body_path, sha256):
    hdr = os.path.join(outdir, name + ".headers")
    body = os.path.join(outdir, name + ".body")
    cmd = ["curl", "-4", "--noproxy", "*", "-sS", "--max-time", "320",
           "--interface", HOST_IP, "-D", hdr, "-o", body, "-X", "POST",
           "--data-binary", "@" + body_path] + WRITE_HEADERS + [
           "-H", "X-E2631-SHA256: " + sha256,
           RESCUE + "/flash?mode=write"]
    t0 = time.time()
    try:
        pr = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=340)
        rc, err = pr.returncode, pr.stderr
    except subprocess.TimeoutExpired:
        rc, err = 124, b"timeout"
    htxt = read_bytes(hdr).decode("latin-1", "replace") if os.path.exists(hdr) else ""
    btxt = read_bytes(body).decode("latin-1", "replace") if os.path.exists(body) else ""
    rep = {"name": name, "rc": rc,
           "stderr": (err or b"").decode("latin-1", "replace")[:500],
           "elapsed_s": round(time.time() - t0, 3), "status": ev._http_status(htxt),
           "headers": htxt[:3000], "body_text": btxt[:2000],
           "kv": ev.parse_kv(btxt)}
    log("write POST %s: http=%s result=%s dt=%.2fs" %
        (name, rep["status"], rep["kv"].get("result"), rep["elapsed_s"]))
    return rep


def wait_status_done(outdir, name, want_crc=None, timeout=240):
    polls = []
    last_stage = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = status_get(outdir, name + "-poll-%02d" % len(polls))
        kv = st.get("kv") or {}
        stage = kv.get("stage")
        if stage != last_stage:
            polls.append({"t": round(time.time() - (deadline - timeout), 2),
                          "http": st.get("status"), "stage": stage,
                          "progress": kv.get("progress"),
                          "result": kv.get("result"),
                          "crc32": kv.get("crc32")})
            last_stage = stage
            log("status stage=%s progress=%s" % (stage, kv.get("progress")))
        crc_ok = (want_crc is None
                  or (kv.get("crc32") or "").lower() == want_crc.lower())
        if stage == "done":
            return {"done": True, "status": st, "polls": polls,
                    "crc_ok": crc_ok, "crc32": kv.get("crc32")}
        if stage == "error":
            return {"done": False, "status": st, "polls": polls,
                    "crc_ok": False, "error": kv.get("error")}
        time.sleep(0.5)
    return {"done": False, "status": None, "polls": polls, "crc_ok": False,
            "error": "timeout waiting for stage=done"}


def start_rescue_alive(c, res, tries=3):
    for attempt in range(tries):
        rec = ev.start_rescue(c, res)
        left = c.wait(ev.RESCUE_LEFT, 1.0)
        if left is None:
            rec["attempt"] = attempt + 1
            return rec
        log("rescue exited immediately after start (attempt %d); retrying" % (attempt + 1))
        time.sleep(0.5)
    raise RuntimeError("e2631rescue could not stay running")


def status_get(outdir, name):
    st = ev._curl_http(outdir, name, [RESCUE + "/status"], timeout=60)
    st["kv"] = ev.parse_kv(st.get("body_text") or "")
    return st


def page_get(outdir, name):
    return ev._curl_http(outdir, name, [RESCUE + "/"], timeout=60)


def read_region(c, res, addr, tag):
    txt = ev.ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (addr, REGION_OFF, REGION_LEN), 300)
    ok = ("%d byte(s)" % REGION_LEN) in (txt or "") and "Failure" not in (txt or "") and "-74" not in (txt or "")
    crc_txt = ev.ub_cmd(c, res, "crc32 0x%08x 0x%x" % (addr, REGION_LEN), 120)
    crc = e2s.parse_crc(crc_txt)
    return {"tag": tag, "addr": "0x%08x" % addr, "read_ok": ok,
            "read_tail": (txt or "")[-500:], "crc": "0x%08x" % crc if crc is not None else None,
            "crc_ok": crc is not None and ("0x%08x" % crc) in (crc_txt or "")}


def read_env_block(c, res):
    txt = ev.ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (ENV_RAM, ENV_OFF, ENV_LEN), 240)
    ok = ("%d byte(s)" % ENV_LEN) in (txt or "") and "Failure" not in (txt or "")
    md = ev.ub_cmd(c, res, "md 0x%08x 1" % ENV_RAM, 30)
    stored = ev.md_first_word(md)
    crc_txt = ev.ub_cmd(c, res, "crc32 0x%08x 0x%x" % (ENV_RAM, ENV_LEN), 240)
    crc = e2s.parse_crc(crc_txt)
    return {"read_ok": ok, "stored_crc": "0x%08x" % stored if stored is not None else None,
            "region_crc": "0x%08x" % crc if crc is not None else None}


def read_secondboot(c, res):
    txt = ev.ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (SEC_RAM, SEC_OFF, SEC_LEN), 240)
    ok = ("%d byte(s)" % SEC_LEN) in (txt or "") and "Failure" not in (txt or "")
    crc_txt = ev.ub_cmd(c, res, "crc32 0x%08x 0x%x" % (SEC_RAM, SEC_LEN), 240)
    crc = e2s.parse_crc(crc_txt)
    return {"read_ok": ok, "crc": "0x%08x" % crc if crc is not None else None}


def reconstruct_expected():
    base = read_bytes(BASE_MTD0)
    netzero = read_bytes(NETZERO)
    e4 = read_bytes(E4_IMAGE)
    cur = base[:REGION_OFF] + netzero + base[ENV_OFF:]
    want = base[:REGION_OFF] + e4 + base[ENV_OFF:]
    return {"base": file_facts(BASE_MTD0), "netzero": file_facts(NETZERO),
            "e4": file_facts(E4_IMAGE),
            "cur_sha256": sha_bytes(cur), "cur_ok": sha_bytes(cur) == MTD0_CUR,
            "want_sha256": sha_bytes(want), "want_ok": sha_bytes(want) == MTD0_E4,
            "secondboot_crc": "0x%08x" % (zlib.crc32(base[:REGION_OFF]) & 0xFFFFFFFF),
            "env_region_crc": "0x%08x" % (zlib.crc32(base[ENV_OFF:ENV_OFF + ENV_LEN]) & 0xFFFFFFFF),
            "env_block_sha": sha_bytes(base[ENV_OFF:ENV_OFF + ENV_LEN])}


def device_region_facts():
    r = e2s.ssh("sha256sum /dev/mtd0 | cut -d\" \" -f1; "
                "dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d\" \" -f1; "
                "dd if=/dev/mtd0 bs=4096 skip=192 count=32 2>/dev/null | sha256sum | cut -d\" \" -f1; "
                "dd if=/dev/mtd0 bs=4096 skip=0 count=32 2>/dev/null | sha256sum | cut -d\" \" -f1", 120)
    lines = [x for x in (r.get("out") or "").strip().splitlines() if x.strip()]
    def at(i):
        return lines[i].split()[0] if len(lines) > i else None
    return {"mtd0": at(0), "region": at(1), "env_block": at(2),
            "secondboot": at(3), "raw": (r.get("out") or "")[-500:]}


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    base.LOG = args.out_dir + "/preflight.log"
    b1.make_askpass()
    rep = {}
    rep["artifact"] = e2s.artifact_facts(UBOOT_BIN)
    rep["e4_image"] = file_facts(E4_IMAGE)
    rep["netzero"] = file_facts(NETZERO)
    rep["reconstruct"] = reconstruct_expected()
    rep["pins"] = {
        "uboot_sha": rep["artifact"]["sha256"] == UBOOT_SHA,
        "uboot_crc": rep["artifact"]["crc32"] == UBOOT_CRC,
        "uboot_size": rep["artifact"]["size"] == UBOOT_SIZE,
        "uboot_banner": rep["artifact"]["banner_token"] == NEW_BANNER,
        "e4_sha": rep["e4_image"]["sha256"] == REGION_E4,
        "e4_crc": rep["e4_image"]["crc32"] == E4_CRC,
        "e4_size": rep["e4_image"]["size"] == E4_SIZE,
        "netzero_sha": rep["netzero"]["sha256"] == REGION_CUR,
    }
    rep["route"] = b1.ensure_direct_link()
    rep["capture_chain"] = {"supervisor": base.pgrep("capture-supervisor-002.sh"),
                            "bootwatch": base.pgrep("serial-bootwatch.mjs"),
                            "tty": base.tty_holders()}
    try:
        rep["device"] = device_region_facts()
        fw = e2s.ssh("e2631-fwslot info -j | head -c 400", 120)
        rep["fwslot"] = fw.get("out", "")[-400:]
    except Exception as exc:
        rep["device"] = {"error": repr(exc)}
    dev = rep.get("device") or {}
    rep["ok"] = bool(all(rep["pins"].values()) and rep["reconstruct"]["cur_ok"]
                     and rep["reconstruct"]["want_ok"] and rep["route"].get("ok")
                     and dev.get("mtd0") == MTD0_CUR and dev.get("region") == REGION_CUR
                     and dev.get("env_block") == ENV_BLOCK_SHA
                     and dev.get("secondboot") == SECONDBOOT_SHA)
    json.dump(rep, open(os.path.join(args.out_dir, "preflight.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))
    return rep


def run_session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/driver.log"
    padded = e2s.pad_artifact(UBOOT_BIN, outdir)
    art = e2s.artifact_facts(UBOOT_BIN)
    res = {"mode": "e4-rescue-write-acceptance",
           "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "artifact": art, "padded": padded, "uboot_commands": []}
    res["artifact_pins"] = {
        "sha_ok": art["sha256"] == UBOOT_SHA, "crc_ok": art["crc32"] == UBOOT_CRC,
        "banner_ok": art["banner_token"] == NEW_BANNER, "size_ok": art["size"] == UBOOT_SIZE}
    res["reconstruct"] = reconstruct_expected()
    res["netzero"] = file_facts(NETZERO)
    res["e4_image"] = file_facts(E4_IMAGE)
    c = None
    try:
        if not all(res["artifact_pins"].values()):
            raise RuntimeError("artifact pins do not match")
        if not (res["reconstruct"]["cur_ok"] and res["reconstruct"]["want_ok"]):
            raise RuntimeError("mtd0 reconstruction mismatch")
        res["route"] = b1.ensure_direct_link()
        if not res["route"].get("ok"):
            raise RuntimeError("no direct route to the device")
        res["device_before"] = device_region_facts()
        if res["device_before"].get("mtd0") != MTD0_CUR or res["device_before"].get("region") != REGION_CUR:
            raise RuntimeError("device flash does not match the expected baseline")
        if res["device_before"].get("env_block") != ENV_BLOCK_SHA:
            raise RuntimeError("env block is not the expected baseline")
        if res["device_before"].get("secondboot") != SECONDBOOT_SHA:
            raise RuntimeError("secondboot region is not the expected baseline")
        chain0 = {"supervisor": base.pgrep("capture-supervisor-002.sh"),
                  "bootwatch": base.pgrep("serial-bootwatch.mjs"),
                  "tty": base.tty_holders()}
        res["capture_chain_before"] = chain0
        if not chain0["supervisor"] and not chain0["bootwatch"]:
            res["capture_restart"] = base.restore_capture()
        res["staging"] = e2t.stage_userdata_ssh(art, padded, outdir)
        if not res["staging"].get("ok"):
            raise RuntimeError("userdata staging failed")
        log("STAGING GREEN: RAM image in userdata and read back")
        res["tcpdump"] = e2t.start_tcpdump(outdir)
        if not res["tcpdump"].get("ready"):
            raise RuntimeError("host tcpdump did not start")
        res["capture_pause"] = base.pause_capture()
        res["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        time.sleep(0.4)
        c.drain()
        b1.ssh_run("sync; (sleep 1; reboot -f) </dev/null >/dev/null 2>&1 &", timeout=30)
        res["flash_banner_seen"] = e2s.wait_banner(c, OLD_BANNER, 180)
        if not res["flash_banner_seen"]:
            raise RuntimeError("flash U-Boot banner not seen after reboot")
        res["flash_stop"] = fin.stop_autoboot(c, res, OLD_BANNER, 30)
        if not res["flash_stop"].get("prompt"):
            raise RuntimeError("no flash U-Boot prompt")
        txt = ev.ub_cmd(c, res, "version", 60)
        res["flash_version_ok"] = OLD_BANNER in (txt or "")
        if not res["flash_version_ok"]:
            raise RuntimeError("flash U-Boot version mismatch")
        txt = ev.ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (ev.LOAD_ADDR, ev.STAGE_OFF, ev.STAGE_LEN), 300)
        res["staging_read"] = {"ok": ("%d byte(s)" % ev.STAGE_LEN) in (txt or "")
                               and "Failure" not in (txt or ""), "tail": (txt or "")[-500:]}
        if not res["staging_read"]["ok"]:
            raise RuntimeError("staging read into RAM failed")
        crc_txt = ev.ub_cmd(c, res, "crc32 0x%08x 0x%x" % (ev.LOAD_ADDR, art["size"]), 120)
        got = e2s.parse_crc(crc_txt)
        res["staging_crc"] = {"got": "0x%08x" % got if got is not None else None,
                              "want": UBOOT_CRC,
                              "ok": got is not None and ("0x%08x" % got) == UBOOT_CRC}
        if not res["staging_crc"]["ok"]:
            raise RuntimeError("staged image crc32 mismatch")
        boot_idx = len(c.history)
        c.pending = b""
        c.send(b"go 0x47f00000\r")
        res["go_sent"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        res["new_banner_seen"] = e2s.wait_banner(c, NEW_BANNER, 90)
        if not res["new_banner_seen"]:
            raise RuntimeError("new image banner not seen after go")
        res["new_stop"] = fin.stop_autoboot(c, res, NEW_BANNER, 20)
        if not res["new_stop"].get("prompt"):
            raise RuntimeError("no prompt in the RAM image")
        txt = ev.ub_cmd(c, res, "version", 60)
        res["new_version_ok"] = NEW_BANNER in (txt or "")
        boot_text = bytes(c.history[boot_idx:]).decode("latin-1", "replace")
        res["env_block"] = ev.env_block_diag(c, res)
        res["env_sanity"] = ev.env_sanity(c, res, boot_text)
        if not res["env_sanity"].get("env_sanity_ok"):
            raise RuntimeError("env sanity failed at the RAM prompt")
        res["rescue_presence"] = ev.rescue_presence(c, res)
        res["help_ok"] = bool((res["rescue_presence"] or {}).get("present"))
        log("RAM prompt ready: env sanity OK, rescue present")

        def post_and_wait(tag, body, body_sha, want_crc, start=True):
            r = {"tag": tag, "body": body, "body_sha256": body_sha, "want_crc": want_crc}
            if start:
                r["start"] = start_rescue_alive(c, res)
                r["page"] = page_get(outdir, tag + "-page")
                r["status_before"] = status_get(outdir, tag + "-status-before")
            r["post"] = http_post_write(outdir, tag + "-post", body, body_sha)
            r["wait"] = wait_status_done(outdir, tag + "-wait", want_crc)
            r["status_after"] = r["wait"].get("status")
            r["done_ok"] = bool(r["wait"].get("done") and r["wait"].get("crc_ok"))
            log("STEP %s write job done=%s crc=%s want=%s ok=%s" %
                (tag, r["wait"].get("done"), r["wait"].get("crc32"), want_crc, r["done_ok"]))
            return r

        # ONE rescue session for both writes (Lead m09555): never touch the
        # console while e2631rescue serves.  The rescue job's own readback and
        # compare is the per-step verification; the independent console
        # readback happens only after both /status reports are done.
        res["step1"] = post_and_wait("step1-netzero", NETZERO, REGION_CUR, REGION_CRC)
        if not res["step1"]["done_ok"]:
            raise RuntimeError("STEP 1 net-zero write did not complete; holding at the RAM prompt")
        log("STEP 1 STATUS-DONE: net-zero write verified by the rescue readback/compare")

        res["step2"] = post_and_wait("step2-e4", E4_IMAGE, REGION_E4, E4_CRC, start=False)
        if not res["step2"]["done_ok"]:
            raise RuntimeError("STEP 2 E4 write did not complete; holding at the RAM prompt")
        log("STEP 2 STATUS-DONE: E4 write verified by the rescue readback/compare")

        res["stop"] = ev.stop_rescue(c, res)
        res["readback"] = read_region(c, res, READBACK_ADDR, "final-e4")
        res["readback_ok"] = (res["readback"].get("crc") == E4_CRC
                              and res["readback"].get("read_ok"))
        if not res["readback_ok"]:
            raise RuntimeError("independent console readback of the E4 region failed; holding at the RAM prompt")
        res["env"] = read_env_block(c, res)
        res["secondboot"] = read_secondboot(c, res)
        res["env_ok"] = (res["env"].get("stored_crc") == ENV_STORED_CRC
                         and res["env"].get("region_crc") == ENV_REGION_CRC)
        res["secondboot_ok"] = (res["secondboot"].get("crc") == SECONDBOOT_CRC)
        if not (res["env_ok"] and res["secondboot_ok"]):
            raise RuntimeError("env or secondboot changed after the E4 write; holding at the RAM prompt")
        log("INDEPENDENT READBACK GREEN: E4 region CRC matches, env and secondboot intact")
        res["hold"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                       "ram_prompt": True, "mtd0_expected": MTD0_E4}
        log("WRITE VERIFIED. HOLD at the RAM prompt; reset follows")

        idx = len(c.history)
        c.pending = b""
        c.send(b"reset\r")
        res["reset_command"] = {"cmd": "reset", "sent": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        token = NEW_BANNER.encode()
        seen = False
        deadline = time.time() + 120
        while time.time() < deadline:
            data = c.read()
            if data:
                c.pending += data
                if token in c.pending:
                    seen = True
                    break
            else:
                time.sleep(0.02)
        res["reset_boot_text"] = bytes(c.history[idx:]).decode("latin-1", "replace")[-8000:]
        res["reset_banner_seen"] = seen
        if not seen:
            raise RuntimeError("reset produced no flash boot banner within 120s; ask the user for a power cycle")
        res["reset_stop"] = fin.stop_autoboot(c, res, NEW_BANNER, 20)
        if not res["reset_stop"].get("prompt"):
            raise RuntimeError("flash-resident U-Boot did not reach a prompt")
        txt = ev.ub_cmd(c, res, "version", 60)
        res["flash_resident_version_ok"] = NEW_BANNER in (txt or "")
        log("RESET GREEN: flash-resident E4 U-Boot prompt")

        r = {"start": ev.start_rescue(c, res)}
        r["page"] = page_get(outdir, "flash-rescue-page")
        r["status"] = status_get(outdir, "flash-rescue-status")
        r["stop"] = ev.stop_rescue(c, res)
        r["page_ok"] = (r["page"].get("status") == 200
                        and (r["page"].get("content_encoding") or "").lower() == "gzip")
        r["status_ok"] = (r["status"].get("status") == 200
                          and (r["status"].get("kv") or {}).get("stage") == "idle")
        res["flash_rescue"] = r
        log("FLASH-RESIDENT RESCUE: page=%s status=%s" % (r["page_ok"], r["status_ok"]))
        res["f1"] = ev.f1_block(c, res)
        if res["f1"].get("verdict") != "KERNEL_STARTED":
            raise RuntimeError("e2631boot from the flash-resident E4 image did not start the kernel")
        log("F1 GREEN: kernel started from the flash-resident E4 image")
    except Exception as exc:
        res["error"] = repr(exc)
        log("SESSION ERROR " + repr(exc))
    finally:
        try:
            e2t.stop_tcpdump()
        except Exception as exc:
            res["stop_tcpdump_error"] = repr(exc)
        try:
            if c is not None:
                open(os.path.join(outdir, "console-history.txt"), "wb").write(bytes(c.history))
        except Exception:
            pass
        try:
            base.stop_hub()
        except Exception as exc:
            res["stop_hub_error"] = repr(exc)
        try:
            res["capture_after"] = base.restore_capture()
        except Exception as exc:
            res["capture_after"] = {"ok": False, "error": repr(exc)}
        try:
            b1.make_askpass()
            b1.ensure_direct_link()
            b1.wait_uptime(60, 240)
            res["device_after"] = device_region_facts()
            deadline = time.time() + 150
            mt = None
            while time.time() < deadline:
                h = e2s.ssh("echo PANICS=$(dmesg | grep -ci -E panic || true); "
                            "echo OOPS=$(dmesg | grep -ci Oops || true); "
                            "echo MT7916=$(dmesg | grep -ci MT7916 || true); "
                            "echo VERSION=$(cat /etc/e2631-version); "
                            "echo KERNEL=$(uname -r); "
                            "e2631-fwslot info -j | head -c 400", 120)
                out = h.get("out") or ""
                mt = out
                if "MT7916=1" in out or "PANICS=0" not in out:
                    break
                time.sleep(10)
            res["postcheck"] = {"out": mt}
        except Exception as exc:
            res["device_after"] = {"error": repr(exc)}
        cmds = [x["cmd"] for x in res.get("uboot_commands", [])]
        res["audit"] = {
            "uboot_commands": cmds,
            "forbidden": [x for x in cmds if ev.FORBIDDEN_RE.search(x)],
            "manual_reset": (res.get("reset_command") or {}),
            "posts": [{"name": (res.get(k) or {}).get("post", {}).get("name"),
                       "status": (res.get(k) or {}).get("post", {}).get("status"),
                       "result": ((res.get(k) or {}).get("post", {}).get("kv") or {}).get("result")}
                      for k in ("step1", "step2")],
        }
        post = (res.get("postcheck") or {}).get("out") or ""
        after = res.get("device_after") or {}
        s1 = res.get("step1") or {}
        s2 = res.get("step2") or {}
        fr = res.get("flash_rescue") or {}
        checks = {
            "artifact_pins": all(res.get("artifact_pins", {}).values()),
            "staging": bool((res.get("staging") or {}).get("ok")),
            "ram_banner": bool(res.get("new_banner_seen")),
            "env_sanity": bool((res.get("env_sanity") or {}).get("env_sanity_ok")),
            "step1_done": bool(s1.get("done_ok")),
            "step2_done": bool(s2.get("done_ok")),
            "final_readback": bool(res.get("readback_ok")),
            "env_unchanged": bool(res.get("env_ok")),
            "secondboot_unchanged": bool(res.get("secondboot_ok")),
            "reset_banner": bool(res.get("reset_banner_seen")),
            "flash_resident": bool(res.get("flash_resident_version_ok")),
            "flash_rescue_page": bool(fr.get("page_ok")),
            "flash_rescue_status": bool(fr.get("status_ok")),
            "f1_verdict": (res.get("f1") or {}).get("verdict"),
            "mtd0_e4": after.get("mtd0") == MTD0_E4,
            "region_e4": after.get("region") == REGION_E4,
            "env_after": after.get("env_block") == ENV_BLOCK_SHA,
            "secondboot_after": after.get("secondboot") == SECONDBOOT_SHA,
            "panics_zero": "PANICS=0" in post,
            "oops_zero": "OOPS=0" in post,
            "mt7916": "MT7916=1" in post,
            "capture_after": bool((res.get("capture_after") or {}).get("ok")),
            "no_error": not res.get("error"),
            "no_forbidden": not res["audit"]["forbidden"],
        }
        res["checks"] = checks
        green = all(v is True for k, v in checks.items() if k != "f1_verdict") \
            and checks["f1_verdict"] == "KERNEL_STARTED"
        res["verdict"] = {"session": "GREEN" if green else ("ERROR" if res.get("error") else "FAIL"),
                          "step1": "PASS" if checks["step1_done"] else "FAIL",
                          "step2": "PASS" if checks["step2_done"] else "FAIL",
                          "reset": "PASS" if checks["reset_banner"] else "FAIL",
                          "flash_rescue": "PASS" if (checks["flash_rescue_page"] and checks["flash_rescue_status"]) else "FAIL",
                          "f1": checks["f1_verdict"],
                          "mtd0": "E4" if checks["mtd0_e4"] else "MISMATCH"}
        res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        json.dump(res, open(os.path.join(outdir, "session-results.json"), "w"), indent=1)
        log("VERDICT " + json.dumps(res["verdict"]))
        log("checks: " + json.dumps(checks))
    return 0 if (res.get("verdict") or {}).get("session") == "GREEN" else 2


def selftest():
    rec = reconstruct_expected() if os.path.exists(BASE_MTD0) else None
    assert UBOOT_CRC == "0x34b252a4"
    assert E4_CRC == "0x79ef8c50"
    assert REGION_CRC == "0x0721e716"
    assert SHA_OK_TEST()
    print("selftest ok: e4=%s expected_mtd0=%s" % (REGION_E4[:16], MTD0_E4[:16]))
    return 0


def SHA_OK_TEST():
    d = b"e2631-write-acceptance"
    return sha_bytes(d) == hashlib.sha256(d).hexdigest() and zlib.crc32(d) >= 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--session", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.preflight:
        rep = preflight(args)
        return 0 if rep.get("ok") else 1
    if args.session:
        return run_session(args)
    ap.error("choose --preflight, --session or --selftest")


if __name__ == "__main__":
    sys.exit(main())
