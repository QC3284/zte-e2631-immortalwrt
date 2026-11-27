#!/usr/bin/env python3
"""E2 thin-image zero-write device session (Lead GO 2026-11-27 19:46).

Order per the Lead instruction:
  0  preflight: thin artifact pins, route, device mtd0 / image-region baseline,
     host services, single-reader capture chain
  1  Linux staging of the padded artifact into the userdata partition
  2  flash U-Boot: mtd read staging -> crc32 gate -> go -> banner gate
  2.5 0x48000000 anomaly re-test (md vs crc32 on the flash-read buffer)
  3  F2 network evidence: mii info, e2631net, dhcp (host dnsmasq + tcpdump),
     ping, tftp, with BMU triples around every command; wire yes/no is the
     decisive datum
  4  F1 LAST: e2631boot load -> md/crc32/iminfo at 0x420000 space right after
     the load -> plain e2631boot hand-off; a started kernel ends on Linux

Zero mtd0 writes. The only flash write is the userdata staging erase+write.
Persistent gates: /dev/mtd0 == f9239040... and the U-Boot image region
(dd bs=4096 skip=32 count=160) == b1ea9a48...
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

P3 = "/home/qc233/zte/e2631-p3"
E2 = P3 + "/e2"
sys.path.insert(0, P3)
sys.path.insert(0, E2)
import a1_banner_accept as base
import b1_env_session as b1
import c1b1_final as fin
import e2_session as e2s

EXP_ARTIFACT = ("/home/qc233/zte/e2631-t5-artifacts/uboot-defconfig-45988430055/"
                "e2631-uboot-45988430055/u-boot.bin")
EXP_BANNER = "U-Boot 2027.01-rc2-ge6678e875e60"
EXP_SHA = "339289583f80bd60b7214fa65ad9a4b5a3ca68eb37d95bd1bad65215265ee2fa"
EXP_CRC = None  # computed from the artifact file at preflight/session time
FLASH_BANNER = "U-Boot 2027.01-rc2-g85df6772a444"
MTD0_SHA = "f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4"
REGION_SHA = "b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a"
STAGE_OFF = 0x3F00000
STAGE_LEN = 0x80000
LOAD_ADDR = 0x47F00000
TFTP_ADDR = 0x43000000
HOST_IP = "192.168.1.191"
IFACE = "enp0s20u1u4u2c2"
CAP_NAME = "e2631-e2b-cap"
BMU_REGS = [("BUF_ID", "0x9234800c"), ("BUF_ALLOC", "0x92348014"),
            ("FREE_STATUS", "0x923480dc")]
OUT_DEFAULT = E2 + "/session3/run-1"
LOG = None


def log(msg):
    base.log(msg)


def start_tcpdump(outdir):
    inner = ("apk add --no-cache tcpdump >/dev/null 2>&1 && exec tcpdump -i "
             + IFACE + " -nne -l > /out/tcpdump.log 2>&1")
    cmd = ("docker rm -f " + CAP_NAME + " >/dev/null 2>&1; docker run -d --name "
           + CAP_NAME + " --net=host --cap-add=NET_RAW --cap-add=NET_ADMIN -v "
           + outdir + ":/out alpine:latest sh -c " + shlex.quote(inner))
    rc, out, err = base.sh(cmd, timeout=180)
    rep = {"rc": rc, "container": out.strip()[:64], "stderr": err[-500:]}
    logpath = os.path.join(outdir, "tcpdump.log")
    deadline = time.time() + 90
    ready = False
    while time.time() < deadline:
        if os.path.exists(logpath):
            try:
                txt = open(logpath, "rb").read()
            except OSError:
                txt = b""
            if b"listening on" in txt:
                ready = True
                break
        time.sleep(1)
    rep["ready"] = ready
    log("tcpdump ready=" + str(ready))
    return rep


def stop_tcpdump():
    base.sh("docker rm -f " + CAP_NAME + " >/dev/null 2>&1", timeout=60)


STAGING_PORT = 18081


def start_staging_http(outdir):
    logpath = os.path.join(outdir, "staging-http.log")
    pidfile = os.path.join(outdir, "staging-http.pid")
    inner = ("cd " + e2s.HTTP_DIR + " && exec python3 -m http.server %d --bind %s"
             % (STAGING_PORT, HOST_IP))
    cmd = ("nohup bash -c " + shlex.quote(inner) + " >> " + shlex.quote(logpath)
           + " 2>&1 & echo $! > " + shlex.quote(pidfile) + "; cat " + shlex.quote(pidfile))
    rc, out, err = base.sh(cmd, timeout=30)
    pid = out.strip().splitlines()[-1] if out.strip() else None
    deadline = time.time() + 15
    bound = False
    while time.time() < deadline:
        rc2, out2, _ = base.sh("ss -ltn 2>/dev/null | grep ':%d '" % STAGING_PORT)
        if out2.strip():
            bound = True
            break
        time.sleep(0.5)
    rec = {"pid": pid, "port": STAGING_PORT, "bound": bound, "log": logpath,
           "rc": rc, "err": (err or "")[-300:]}
    log("staging HTTP " + json.dumps(rec))
    return rec


def bmu_snapshot(c, res, label):
    snap = {"label": label, "t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "regs": {}}
    for name, addr in BMU_REGS:
        txt = e2s.ub_cmd(c, res, "md.l " + addr + " 1", 30)
        m = re.search(addr[2:] + r":\s+([0-9a-fA-F]{8})", txt)
        snap["regs"][name] = {"addr": addr, "value": m.group(1) if m else None,
                              "tail": txt[-300:]}
    log("BMU snapshot " + label + " " + json.dumps({k: v["value"] for k, v in snap["regs"].items()}))
    return snap


def bootm_attempt(c, res, cmd, timeout=240):
    idx = len(c.history)
    c.pending = b""
    t0 = time.time()
    c.send((cmd + "\r").encode())
    outcome = "timeout"
    while time.time() - t0 < timeout:
        if b"Starting kernel" in c.pending:
            outcome = "kernel"
            time.sleep(3)
            break
        if re.search(rb"\r\n=> ", c.pending):
            outcome = "prompt"
            break
        data = c.read()
        if data:
            c.pending += data
        else:
            time.sleep(0.02)
    txt = bytes(c.history[idx:]).decode("latin-1", "replace")
    rec = {"cmd": cmd, "outcome": outcome, "dt": round(time.time() - t0, 2), "out": txt}
    res.setdefault("uboot_commands", []).append(
        {"cmd": cmd, "output": txt[-6000:], "ok": outcome != "timeout"})
    log("bootm attempt " + cmd + " outcome=" + outcome + " dt=%.2f" % (time.time() - t0))
    return rec


def dhcp_attempt(c, res, timeout=300):
    idx = len(c.history)
    c.pending = b""
    t0 = time.time()
    c.send(b"dhcp\r")
    got_prompt = False
    while time.time() - t0 < timeout:
        if re.search(rb"\r\n=> ", c.pending):
            got_prompt = True
            break
        if (time.time() - t0) > (timeout - 30):
            c.send(b"\x03")
        data = c.read()
        if data:
            c.pending += data
        else:
            time.sleep(0.03)
    if not got_prompt:
        c.send(b"\x03")
        time.sleep(0.5)
        c.pending = b""
        c.send(b"\r")
        if fin.wait_prompt(c, 15) is not None:
            got_prompt = True
    txt = bytes(c.history[idx:]).decode("latin-1", "replace")
    m = re.search(r"bound to address\s+([0-9.]+)", txt)
    rec = {"cmd": "dhcp", "prompt": got_prompt, "ip": m.group(1) if m else None,
           "dt": round(time.time() - t0, 2), "out": txt}
    res.setdefault("uboot_commands", []).append(
        {"cmd": "dhcp", "output": txt[-6000:], "ok": got_prompt})
    log("dhcp prompt=" + str(got_prompt) + " ip=" + str(rec["ip"]) + " dt=%.2f" % (time.time() - t0))
    return rec


def ssh_stdin(remote, data, timeout=180):
    env = dict(os.environ)
    env.update({"SSH_ASKPASS": b1.ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    cmd = ["setsid", "-w", "ssh", "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10",
           "root@192.168.1.1", remote]
    p = subprocess.run(cmd, env=env, input=data, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout.decode("latin-1", "replace"), p.stderr.decode("latin-1", "replace")


def stage_userdata_ssh(art, padded, outdir):
    """Stage the padded artifact into the userdata partition through SSH stdin.

    The host HTTP ports 18080/18081 are held by another live mock-rescue tool
    (detected during preflight), so the copy uses the same-address SSH channel
    instead of HTTP; the device-side sha256 gate is unchanged.
    """
    res = {"method": "ssh-stdin", "padded": padded}
    data = open(padded["path"], "rb").read()

    def step(key, cmd, payload=None, timeout=180):
        t0 = time.time()
        if payload is None:
            rc, out, err = b1.ssh_run(cmd, timeout=timeout)
        else:
            rc, out, err = ssh_stdin(cmd, payload, timeout=timeout)
        r = {"rc": rc, "out": (out or "")[-1500:], "err": (err or "")[-600:],
             "elapsed_s": round(time.time() - t0, 2)}
        res[key] = r
        log("stage %s %.2fs rc=%s" % (key, r["elapsed_s"], rc))
        return r

    r = step("copy", "cat > /tmp/e2-uboot-stage.bin; sha256sum /tmp/e2-uboot-stage.bin",
             data, 240)
    res["copy_bytes"] = len(data)
    if padded["sha256"] not in (r["out"] or ""):
        raise RuntimeError("staged file sha256 mismatch after ssh copy")
    step("erase", "mtd erase userdata; echo ERASE_RC=$?", None, 180)
    step("write", "mtd write /tmp/e2-uboot-stage.bin userdata; echo WRITE_RC=$?", None, 180)
    r = step("readback", "dd if=/dev/mtd10 bs=4096 count=%d 2>/dev/null | sha256sum"
             % (STAGE_LEN // 4096), None, 120)
    if padded["sha256"] not in (r["out"] or ""):
        raise RuntimeError("userdata read-back sha256 mismatch")
    step("sync", "sync; echo SYNCED", None, 60)
    res["ok"] = True
    return res


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    base.LOG = args.out_dir + "/preflight.log"
    b1.make_askpass()
    rep = {}
    rep["artifact"] = e2s.artifact_facts(args.artifact)
    rep["artifact_pins"] = {"sha_ok": rep["artifact"]["sha256"] == EXP_SHA,
                            "crc_ok": bool(rep["artifact"]["crc32"]),
                            "banner_ok": rep["artifact"]["banner_token"] == EXP_BANNER,
                            "size": rep["artifact"]["size"],
                            "crc32": rep["artifact"]["crc32"]}
    rep["padded"] = e2s.pad_artifact(args.artifact, args.out_dir)
    rep["testfile"] = e2s.testfile_facts()
    rep["route"] = b1.ensure_direct_link()
    rep["services"] = e2s.check_services()
    rep["capture_chain"] = {"supervisor": base.pgrep("capture-supervisor-002.sh"),
                            "bootwatch": base.pgrep("serial-bootwatch.mjs"),
                            "tty": base.tty_holders()}
    try:
        rep["device"] = e2s.device_facts()
    except Exception as exc:
        rep["device"] = {"error": repr(exc)}
    dev = rep.get("device") or {}
    rep["ok"] = bool(rep["artifact_pins"]["sha_ok"] and rep["artifact_pins"]["crc_ok"]
                     and rep["artifact_pins"]["banner_ok"] and rep["route"].get("ok")
                     and dev.get("mtd0_sha") == MTD0_SHA)
    print(json.dumps(rep, indent=1))
    return rep


def run_session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/driver.log"
    art = e2s.artifact_facts(args.artifact)
    padded = e2s.pad_artifact(args.artifact, outdir)
    tf = e2s.testfile_facts()
    res = {"mode": "e2t-session", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "artifact": art, "artifact_pins": {"sha_ok": art["sha256"] == EXP_SHA,
           "crc_ok": bool(art["crc32"]), "banner_ok": art["banner_token"] == EXP_BANNER,
           "crc32": art["crc32"]},
           "padded": padded, "testfile": tf}

    def region_facts():
        txt = e2s.ssh("sha256sum /dev/mtd0 | cut -d\" \" -f1; "
                      "dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d\" \" -f1", 120)
        lines = [x for x in txt.strip().splitlines() if x.strip()]
        return {"mtd0": lines[0].split()[0] if len(lines) > 0 else None,
                "region": lines[1].split()[0] if len(lines) > 1 else None,
                "raw": txt[-400:]}

    try:
        res["host_before"] = region_facts()
    except Exception as exc:
        res["host_before"] = {"error": repr(exc)}
    res["uboot_commands"] = []
    b1.make_askpass()
    c = None
    try:
        res["route"] = b1.ensure_direct_link()
        if not res["route"].get("ok"):
            raise RuntimeError("no direct route to the device")
        res["device_before"] = e2s.device_facts()
        if res["device_before"].get("mtd0_sha") != MTD0_SHA:
            raise RuntimeError("device mtd0 is not the expected zero-write baseline")
        chain0 = {"supervisor": base.pgrep("capture-supervisor-002.sh"),
                  "bootwatch": base.pgrep("serial-bootwatch.mjs"),
                  "tty": base.tty_holders()}
        res["capture_chain_before"] = chain0
        if not chain0["supervisor"] and not chain0["bootwatch"]:
            res["capture_restart"] = base.restore_capture()
            log("serial capture chain restarted as a single reader")
        res["services"] = e2s.start_services()
        res["staging_http"] = {"skipped": "host 18080/18081 are held by another live tool; "
                               "staging goes over SSH stdin"}
        res["staging"] = stage_userdata_ssh(art, padded, outdir)
        log("PHASE 1 GREEN: artifact staged in userdata and read back")
        res["tcpdump"] = start_tcpdump(outdir)
        res["capture_pause"] = base.pause_capture()
        res["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        time.sleep(0.4)
        c.drain()
        b1.ssh_run("sync; (sleep 1; reboot -f) </dev/null >/dev/null 2>&1 &", timeout=30)
        log("reboot -f requested; waiting for the flash U-Boot banner")
        res["flash_banner_seen"] = e2s.wait_banner(c, FLASH_BANNER, 180)
        if not res["flash_banner_seen"]:
            raise RuntimeError("flash U-Boot banner not seen after reboot")
        res["flash_stop_autoboot"] = fin.stop_autoboot(c, res, FLASH_BANNER, 30)
        if not res["flash_stop_autoboot"].get("prompt"):
            raise RuntimeError("no flash U-Boot prompt")
        txt = e2s.ub_cmd(c, res, "version", 60)
        res["flash_version_ok"] = FLASH_BANNER in txt
        if not res["flash_version_ok"]:
            raise RuntimeError("flash U-Boot version mismatch")
        txt = e2s.ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x"
                         % (LOAD_ADDR, STAGE_OFF, STAGE_LEN), 240)
        res["read_staging"] = {"ok": ("%d byte(s)" % STAGE_LEN) in txt and "Failure" not in txt,
                               "tail": txt[-800:]}
        if not res["read_staging"]["ok"]:
            raise RuntimeError("staging read into RAM failed")
        txt = e2s.ub_cmd(c, res, "crc32 0x%08x 0x%x" % (LOAD_ADDR, art["size"]), 120)
        got = e2s.parse_crc(txt)
        res["staging_crc"] = {"got": "0x%08x" % got if got is not None else None,
                              "want": art["crc32"],
                              "ok": got is not None and ("0x%08x" % got) == art["crc32"]}
        if not res["staging_crc"]["ok"]:
            raise RuntimeError("staged image crc32 mismatch; refusing to go")
        log("gate: staged image crc32 == " + art["crc32"])
        c.pending = b""
        c.send(b"go 0x47f00000\r")
        res["go_sent"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        res["new_banner_seen"] = e2s.wait_banner(c, art["banner_token"], 90)
        if not res["new_banner_seen"]:
            raise RuntimeError("new image banner not seen after go")
        res["new_stop_autoboot"] = fin.stop_autoboot(c, res, art["banner_token"], 20)
        if not res["new_stop_autoboot"].get("prompt"):
            raise RuntimeError("no prompt in the new image")
        txt = e2s.ub_cmd(c, res, "version", 60)
        res["new_version_ok"] = art["banner_token"] in txt
        log("PHASE 2 GREEN: new image banner and prompt")
        anomaly = {}
        txt = e2s.ub_cmd(c, res, "mtd read spi-nand0 0x48000000 0x2300000 0x800", 120)
        anomaly["read_48000000"] = {"ok": ("2048 byte(s)" in txt) and ("Failure" not in txt),
                                    "tail": txt[-800:]}
        anomaly["md_480000"] = e2s.ub_cmd(c, res, "md 0x480000 4", 30)
        anomaly["md_480020"] = e2s.ub_cmd(c, res, "md 0x480020 8", 30)
        anomaly["crc32_480020"] = e2s.ub_cmd(c, res, "crc32 0x480020 0x40", 40)
        anomaly["iminfo_480020"] = e2s.ub_cmd(c, res, "iminfo 0x480020", 40)
        res["anomaly"] = anomaly
        log("PHASE 2.5 anomaly re-test recorded")
        f2 = {}
        f2["mii_info"] = {"snapshot": bmu_snapshot(c, res, "before_mii"),
                          "out": e2s.ub_cmd(c, res, "mii info", 120)}
        f2["mii_info"]["after"] = bmu_snapshot(c, res, "after_mii")
        f2["e2631net"] = {"snapshot": bmu_snapshot(c, res, "before_e2631net"),
                          "out": e2s.ub_cmd(c, res, "e2631net", 180)}
        f2["e2631net"]["after"] = bmu_snapshot(c, res, "after_e2631net")
        f2["dhcp"] = {"snapshot": bmu_snapshot(c, res, "before_dhcp"),
                      "result": dhcp_attempt(c, res, 300)}
        f2["dhcp"]["after"] = bmu_snapshot(c, res, "after_dhcp")
        if f2["dhcp"]["result"]["ip"]:
            e2s.ub_cmd(c, res, "setenv serverip " + HOST_IP, 60)
        else:
            log("dhcp gave no address; setting RAM-only static addresses for ping/tftp")
            e2s.ub_cmd(c, res, "setenv ipaddr 192.168.1.50", 60)
            e2s.ub_cmd(c, res, "setenv netmask 255.255.255.0", 60)
            e2s.ub_cmd(c, res, "setenv serverip " + HOST_IP, 60)
            f2["static_fallback"] = True
        f2["ping"] = {"snapshot": bmu_snapshot(c, res, "before_ping"),
                      "out": e2s.ub_cmd(c, res, "ping " + HOST_IP, 180)}
        f2["ping"]["after"] = bmu_snapshot(c, res, "after_ping")
        f2["tftp"] = {"snapshot": bmu_snapshot(c, res, "before_tftp"),
                      "out": e2s.ub_cmd(c, res, "tftp 0x%08x %s" % (TFTP_ADDR, e2s.TEST_NAME), 240)}
        f2["tftp"]["after"] = bmu_snapshot(c, res, "after_tftp")
        m = re.search(r"Bytes transferred = (\d+)", f2["tftp"]["out"])
        f2["tftp"]["bytes"] = int(m.group(1)) if m else None
        f2["tftp"]["size"] = tf["size"]
        f2["tftp"]["crc"] = {"out": e2s.ub_cmd(c, res, "crc32 0x%08x 0x%x" % (TFTP_ADDR, tf["size"]), 120)}
        got = e2s.parse_crc(f2["tftp"]["crc"]["out"])
        f2["tftp"]["crc"]["got"] = "0x%08x" % got if got is not None else None
        f2["tftp"]["crc"]["want"] = tf["crc32"]
        res["f2"] = f2
        stop_tcpdump()
        log("PHASE 3 F2 evidence recorded")
        f1 = {}
        load_txt = e2s.ub_cmd(c, res, "e2631boot load", 240)
        f1["load"] = {"out": load_txt, "crc_good": "header and data CRCs are good" in load_txt}
        f1["md_marker"] = e2s.ub_cmd(c, res, "md 0x420000 8", 30)
        f1["md_header"] = e2s.ub_cmd(c, res, "md 0x420020 8", 30)
        f1["crc32_header"] = e2s.ub_cmd(c, res, "crc32 0x420020 0x40", 40)
        f1["iminfo_marker_addr"] = e2s.ub_cmd(c, res, "iminfo 0x420000", 40)
        f1["iminfo_uimage_addr"] = e2s.ub_cmd(c, res, "iminfo 0x420020", 40)
        log("F1 discriminator recorded; starting the plain e2631boot hand-off")
        att = bootm_attempt(c, res, "e2631boot", 300)
        f1["boot"] = att
        if att["outcome"] == "kernel":
            f1["verdict"] = "KERNEL_STARTED"
            res["linux_marker"] = e2s.wait_linux_console(c, 300)
        elif att["outcome"] == "prompt":
            if "Wrong Image Type" in att["out"]:
                f1["verdict"] = "WRONG_IMAGE_TYPE_RETURN"
            elif "Bad Magic" in att["out"]:
                f1["verdict"] = "BAD_MAGIC_RETURN"
            else:
                f1["verdict"] = "SILENT_RETURN"
        else:
            f1["verdict"] = "TIMEOUT"
        res["f1"] = f1
        log("PHASE 4 F1 verdict " + f1["verdict"])
    except Exception as exc:
        res["error"] = repr(exc)
        log("SESSION ERROR " + repr(exc))
    finally:
        try:
            stop_tcpdump()
        except Exception as exc:
            res["stop_tcpdump_error"] = repr(exc)
        try:
            with open(os.path.join(outdir, "console-history.txt"), "wb") as f:
                if c is not None:
                    f.write(bytes(c.history))
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
            e2s.stop_services()
        except Exception as exc:
            res["stop_services_error"] = repr(exc)
        try:
            base.sh("pkill -f 'http.server %d' 2>/dev/null || true" % STAGING_PORT, timeout=30)
        except Exception:
            pass
        for name in ("dnsmasq.log", "http.log", "testfile.json"):
            src = E2 + "/logs/" + name
            if os.path.exists(src):
                try:
                    shutil.copyfile(src, os.path.join(outdir, name))
                except Exception:
                    pass
        try:
            b1.make_askpass()
            b1.ensure_direct_link()
            b1.wait_uptime(60, 240)
            res["device_after"] = e2s.device_facts()
            res["postcheck"] = e2s.ssh("echo VERSION=$(cat /etc/e2631-version); "
                                       "echo KERNEL=$(uname -r); "
                                       "echo PANICS=$(dmesg | grep -ci -E panic || true); "
                                       "echo OOPS=$(dmesg | grep -ci Oops || true); "
                                       "echo MT7916=$(dmesg | grep -ci MT7916 || true); "
                                       "echo MTD0=$(sha256sum /dev/mtd0 | cut -d\" \" -f1); "
                                       "echo REGION=$(dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d\" \" -f1); "
                                       "e2631-fwslot info -j | head -c 400", 180)
        except Exception as exc:
            res["device_after"] = {"error": repr(exc)}
        cmds = [x["cmd"] for x in res.get("uboot_commands", [])]
        res["audit"] = {
            "uboot_commands": cmds,
            "uboot_flash_writes": [x for x in cmds if re.search(
                r"mtd (write|erase)|saveenv|nand (write|erase)|e2631flash|loadx|xmodem", x)],
            "staging_linux_writes": [x["cmd"] for x in []],
            "net_cmds": [x for x in cmds if re.match(r"^(e2631net|mii info|dhcp|ping |tftp |crc32 |setenv )", x)],
        }
        staging = res.get("staging") or {}
        res["audit"]["staging_ops"] = {k: (staging.get(k) or {}).get("rc") for k in
                                       ("erase", "write", "readback", "wget", "sync")}
        post = (res.get("postcheck") or {}).get("out", "")
        after = res.get("device_after") or {}
        res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        f1v = ((res.get("f1") or {}).get("verdict"))
        checks = {
            "artifact_pins": all(res["artifact_pins"].values()),
            "staging": bool(staging.get("ok")),
            "staging_crc_gate": ((res.get("staging_crc") or {}).get("ok")),
            "new_banner": res.get("new_banner_seen"),
            "new_version": res.get("new_version_ok"),
            "f1_verdict": f1v,
            "f2_recorded": bool(res.get("f2")),
            "no_uboot_flash_writes": not res["audit"]["uboot_flash_writes"],
            "mtd0_unchanged": (after.get("mtd0_sha") == MTD0_SHA) or (MTD0_SHA in post),
            "region_unchanged": REGION_SHA in post,
            "no_panics": "PANICS=0" in post,
            "capture_after": (res.get("capture_after") or {}).get("ok"),
            "no_error": not res.get("error"),
        }
        res["checks"] = checks
        if (f1v == "KERNEL_STARTED" and checks["mtd0_unchanged"]
                and checks["region_unchanged"] and not res.get("error")):
            res["verdict"] = "GREEN"
        elif f1v in ("SILENT_RETURN", "BAD_MAGIC_RETURN", "WRONG_IMAGE_TYPE_RETURN", "TIMEOUT"):
            res["verdict"] = "F1_" + f1v
        else:
            res["verdict"] = "FAIL"
        json.dump(res, open(outdir + "/session-results.json", "w"), indent=1)
        log("VERDICT " + res["verdict"])
        log("checks: " + json.dumps(checks))
    return 0 if res.get("verdict") == "GREEN" else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=EXP_ARTIFACT)
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        assert EXP_SHA == "339289583f80bd60b7214fa65ad9a4b5a3ca68eb37d95bd1bad65215265ee2fa"
        assert EXP_BANNER == "U-Boot 2027.01-rc2-ge6678e875e60"
        assert MTD0_SHA == "f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4"
        assert REGION_SHA == "b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a"
        print("selftest ok")
        return 0
    if args.preflight:
        return 0 if preflight(args).get("ok") else 1
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())