#!/usr/bin/env python3
"""E2 second-round zero-write device session (task-67 rev 3).

Order per the card:
  0  preflight: artifact pins, route, device mtd0 baseline, host services
  1  Linux staging of the padded artifact into the userdata partition
  2  flash U-Boot: mtd read staging -> crc32 gate -> go -> banner gate
  3  F2 network evidence FIRST: mii info, e2631net, dhcp (host dnsmasq +
     tcpdump), ping, tftp, with BMU triples around every network command
  4  F1 discriminator LAST: e2631boot load, uImage header checks, then
     bootm 0x42000000 and bootm 0x420020 (a jumped kernel is the way back)

Zero mtd0 writes. The only flash write is the userdata staging erase+write.
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

EXP_ARTIFACT = ("/home/qc233/zte/e2631-t5-artifacts/uboot-repro-b-44991704112/"
                "e2631-uboot-44991704112/u-boot.bin")
EXP_BANNER = "U-Boot 2027.01-rc2-gf355ce89283c"
EXP_SHA = "3cf000291b1b2d7552b4e7859204a310640dba81fbba5e60b36f99d7b89f355d"
EXP_CRC = "0x3ccc7333"
FLASH_BANNER = "U-Boot 2027.01-rc2-g85df6772a444"
MTD0_SHA = "f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4"
STAGE_OFF = 0x3F00000
STAGE_LEN = 0x80000
LOAD_ADDR = 0x47F00000
TFTP_ADDR = 0x43000000
HOST_IP = "192.168.1.191"
IFACE = "enp0s20u1u4u2c2"
CAP_NAME = "e2631-e2b-cap"
BMU_REGS = [("BUF_ID", "0x9234800c"), ("BUF_ALLOC", "0x92348014"),
            ("FREE_STATUS", "0x923480dc")]
OUT_DEFAULT = E2 + "/session2/run-1"
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


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    base.LOG = args.out_dir + "/preflight.log"
    b1.make_askpass()
    rep = {}
    rep["artifact"] = e2s.artifact_facts(args.artifact)
    rep["artifact_pins"] = {"sha_ok": rep["artifact"]["sha256"] == EXP_SHA,
                            "crc_ok": rep["artifact"]["crc32"] == EXP_CRC,
                            "banner_ok": rep["artifact"]["banner_token"] == EXP_BANNER,
                            "size": rep["artifact"]["size"]}
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
    res = {"mode": "e2b-session", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "artifact": art, "artifact_pins": {"sha_ok": art["sha256"] == EXP_SHA,
           "crc_ok": art["crc32"] == EXP_CRC, "banner_ok": art["banner_token"] == EXP_BANNER},
           "padded": padded, "testfile": tf}
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
        if not res["services"].get("ok"):
            raise RuntimeError("host DHCP/TFTP/HTTP services are not ready")
        res["staging"] = e2s.stage_userdata(art, padded, outdir)
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
        f1["md_marker"] = e2s.ub_cmd(c, res, "md.l 0x42000000 8", 30)
        f1["md_header"] = e2s.ub_cmd(c, res, "md.l 0x420020 8", 30)
        f1["iminfo"] = e2s.ub_cmd(c, res, "iminfo 0x420020", 40)
        att1 = bootm_attempt(c, res, "bootm 0x42000000", 90)
        f1["bootm_marker_addr"] = att1
        if att1["outcome"] == "kernel":
            f1["verdict"] = "KERNEL_FROM_0x42000000"
        else:
            att2 = bootm_attempt(c, res, "bootm 0x420020", 240)
            f1["bootm_uimage_addr"] = att2
            if att2["outcome"] == "kernel":
                f1["verdict"] = "KERNEL_STARTED"
                res["linux_marker"] = e2s.wait_linux_console(c, 300)
            elif att2["outcome"] == "prompt":
                if "Bad Magic" in att2["out"]:
                    f1["verdict"] = "BAD_MAGIC_RETURN"
                else:
                    f1["verdict"] = "SILENT_RETURN"
                f1["printenv_machid"] = e2s.ub_cmd(c, res, "printenv machid", 30)
                f1["bootm_start"] = e2s.ub_cmd(c, res, "bootm start 0x42000000", 40)
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
            "no_panics": "PANICS=0" in post,
            "capture_after": (res.get("capture_after") or {}).get("ok"),
            "no_error": not res.get("error"),
        }
        res["checks"] = checks
        if f1v in ("KERNEL_STARTED", "KERNEL_FROM_0x42000000") and checks["mtd0_unchanged"] and not res.get("error"):
            res["verdict"] = "GREEN"
        elif f1v in ("SILENT_RETURN", "BAD_MAGIC_RETURN", "TIMEOUT"):
            res["verdict"] = "F1_SILENT_RETURN"
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
        assert EXP_SHA == "3cf000291b1b2d7552b4e7859204a310640dba81fbba5e60b36f99d7b89f355d"
        assert EXP_CRC == "0x3ccc7333"
        print("selftest ok")
        return 0
    if args.preflight:
        return 0 if preflight(args).get("ok") else 1
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())