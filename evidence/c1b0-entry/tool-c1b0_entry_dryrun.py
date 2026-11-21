#!/usr/bin/env python3
"""C1b-0 entry-address dry run: load the fixed A3 U-Boot at 0x47F00000 in RAM.

0x47F00000 is the exact address secondboot copies the flashed payload to and
then jumps to (RE evidence); the vendor U-Boot has relocated away, so the area
is free.  Read-only session; zero flash writes.  Flow:
  cold boot -> vendor console -> xmodem u-boot.bin to 0x47F00000 ->
  md.b spot-check -> go 0x47F00000 -> send NOTHING -> our U-Boot autoboots
  e2631boot (bootdelay 3) -> bootm -> kernel -> Linux up -> SSH reboot to
  return to the stock chain -> health + mtd0 sha256 (must stay unchanged).
The artifact is linked for TEXT_BASE=0x43000000 and CONFIG_POSITION_INDEPENDENT
is not set, so a banner/prompt at 0x47F00000 is the PIC pre-reloc proof Lead
asked for; a hang or garbage before the banner is a valid FAIL outcome.
No flash write command is ever sent; the only console commands are
version/help/md.b/xmodem/go on the vendor side.
"""
import argparse, hashlib, json, os, re, sys, time, zlib

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import a1_banner_accept as base
import b1_env_session as b1

P3 = base.P3
OUT_DEFAULT = P3 + "/c1b0-entry/run-1"
KIT = "/home/qc233/zte/e2631-immortalwrt"
ART_BIN = "/home/qc233/zte/e2631-t5-artifacts/uboot-c1a-fix-44892376502/u-boot.bin"
ART_SHA = "2c90fc558dd8e35f50c887040cd25e00f98325e13e35422de1bc52d056de3eb3"
ART_SIZE = 448096
BANNER = b"U-Boot 2027.01-rc2-gb74974862b8d"
ENV_OK = b"Loading Environment from MTD... OK"
ENV_NULL = b"Loading Environment from <NULL>"
BOOT_ADDR = 0x47F00000
NL = chr(10)
PANIC_PATTERNS = [b"Kernel panic", b"Unable to mount root", b"VFS: Cannot open root device",
                  b"No filesystem could mount root", b"FDT and ATAGS support not compiled in",
                  b"Attempting to kill init", b"end Kernel panic",
                  b"data abort", b"prefetch abort", b"undefined instruction"]
# Do NOT use "ImmortalWrt" here: the uImage name and the slot version header both
# contain it, which produced a false positive in run 1 and stopped the monitor
# before bootm had even started.  Wait for a real userspace/kernel marker.
LINUX_MARKERS = [b"e2631-wifi-boot", b"automatic Wi-Fi initialization complete",
                 b"Please press Enter", b"login:"]
KERNEL_START = [b"Starting kernel ...", b"Booting Linux"]


def log(msg):
    b1.log(msg)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_config():
    cfg = {}
    path = os.path.join(os.path.dirname(ART_BIN), ".config")
    if not os.path.exists(path):
        return {"error": ".config not next to the artifact"}
    for line in open(path, errors="replace"):
        line = line.strip()
        if line.startswith("CONFIG_TEXT_BASE="):
            cfg["CONFIG_TEXT_BASE"] = line.split("=", 1)[1].strip()
        elif line.startswith("CONFIG_POSITION_INDEPENDENT="):
            cfg["CONFIG_POSITION_INDEPENDENT"] = line.split("=", 1)[1].strip()
        elif line == "# CONFIG_POSITION_INDEPENDENT is not set":
            cfg["CONFIG_POSITION_INDEPENDENT"] = "not set"
        elif line.startswith("CONFIG_SKIP_RELOCATE="):
            cfg["CONFIG_SKIP_RELOCATE"] = line.split("=", 1)[1].strip()
    return cfg


def artifact_facts(path):
    raw = open(path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    return {"path": path, "size": len(raw), "size_ok": len(raw) == ART_SIZE,
            "sha256": sha, "sha_ok": sha == ART_SHA,
            "first_bytes": raw[:16].hex(), "banner_offset": raw.find(BANNER),
            "banner_present": raw.find(BANNER) >= 0,
            "crc32": format(zlib.crc32(raw) & 0xFFFFFFFF, "08x")}


def device_facts():
    remote = ("sha256sum /dev/mtd0; cut -d. -f1 /proc/uptime; ")
    remote += ("cat /etc/e2631-version 2>/dev/null | head -1; ")
    remote += ("uname -r; cat /proc/mtd")
    rc, out, err = b1.ssh_run(remote, 60)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    rep = {"ssh_rc": rc, "ssh_err_tail": err[-200:], "raw_head": lines[:6]}
    if rc == 0 and lines:
        rep["mtd0_sha256"] = lines[0].split()[0]
        rep["uptime_s"] = lines[1] if len(lines) > 1 else None
        rep["e2631_version"] = lines[2] if len(lines) > 2 else None
        rep["kernel"] = lines[3] if len(lines) > 3 else None
    return rep


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    b1.make_askpass()
    route = base.sh("ip route get 192.168.1.1 | head -1")[1]
    chain = {"supervisor_pids": base.pgrep("capture-supervisor-002.sh"),
             "bootwatch_pids": base.pgrep("serial-bootwatch.mjs"),
             "tty_holders": base.tty_holders()}
    art = artifact_facts(ART_BIN)
    cfg = artifact_config()
    dev = device_facts()
    scripts = {p: os.path.exists(p) for p in [base.HUB, base.RESTORE, base.HEALTH, base.VENDOR_PW_FILE]}
    pw_mode = oct(os.stat(base.VENDOR_PW_FILE).st_mode & 0o777) if os.path.exists(base.VENDOR_PW_FILE) else None
    rep = {"mode": "preflight", "artifact": art, "artifact_config": cfg,
           "capture_chain": chain,
           "route": route, "device": dev, "scripts": scripts, "vendor_pw_mode": pw_mode,
           "kit": KIT, "boot_addr": hex(BOOT_ADDR), "banner": BANNER.decode(),
           "linked_text_base": cfg.get("CONFIG_TEXT_BASE"),
           "text_base_matches_entry": cfg.get("CONFIG_TEXT_BASE", "").lower() == hex(BOOT_ADDR),
           "panic_patterns": [p.decode() for p in PANIC_PATTERNS]}
    rep["ok"] = bool(art["size_ok"] and art["sha_ok"] and art["banner_present"]
                    and chain["supervisor_pids"] and chain["bootwatch_pids"] and chain["tty_holders"]
                    and all(scripts.values()) and pw_mode == "0o600" and dev.get("mtd0_sha256")
                    and "via " not in route and rep["text_base_matches_entry"])
    with open(args.out_dir + "/preflight.json", "w") as f:
        json.dump(rep, f, indent=1)
    log("preflight: " + json.dumps({"ok": rep["ok"], "sha": art["sha256"][:16],
        "mtd0": (dev.get("mtd0_sha256") or "")[:16], "route": route, "chain": chain}))
    print(json.dumps(rep, indent=1))
    return 0 if rep["ok"] else 2


def save_results(outdir, results):
    with open(outdir + "/session-results.json", "w") as f:
        json.dump(results, f, indent=1)


def md_spot_check(c, path, label, offset, length=0x100):
    want = open(path, "rb").read()[offset:offset + length]
    addr = BOOT_ADDR + offset
    text, got, gaps = c.md_read("md.b 0x%08x 0x%x" % (addr, length), addr, length)
    ok = (got == want) and gaps == 0
    log("md spot-check " + label + ": " + ("OK" if ok else "MISMATCH")
        + " addr=0x" + format(addr, "08x") + " gaps=" + str(gaps)
        + " tail=" + text[-200:].replace(chr(13), " ").replace(chr(10), " "))
    return {"label": label, "addr": "0x" + format(addr, "08x"), "length": length,
            "ok": ok, "gaps": gaps, "want_sha256": hashlib.sha256(want).hexdigest(),
            "got_sha256": hashlib.sha256(got).hexdigest(), "tail": text[-300:]}


def monitor_boot(c, result, timeout):
    c.pending = bytes()
    watched = {"banner": False, "slot_line": False, "boot_line": False,
               "kernel_start": False, "linux_marker": False, "panic": None,
               "env_ok": False, "env_null": False}
    accum = bytearray()
    boot_lines = []
    deadline = time.time() + timeout
    panic_at = None
    while time.time() < deadline:
        data = c.read()
        if data:
            accum.extend(data)
            text = bytes(data)
            if (not watched["banner"]) and BANNER in bytes(accum):
                watched["banner"] = True
                log("OUR BANNER SEEN (A3 U-Boot running from RAM)")
            for line in text.splitlines():
                s = line.decode("latin-1", "replace")
                if "e2631boot:" in s and len(boot_lines) < 40:
                    boot_lines.append(s.strip())
            blob = bytes(accum)
            if not watched["env_ok"] and (ENV_OK in blob) and not watched["env_null"]:
                watched["env_ok"] = True
                log("env loaded from MTD (patch 0009 env-name fix live)")
            if not watched["env_null"] and ENV_NULL in blob:
                watched["env_null"] = True
                log("ENV NAMING REGRESSION: <NULL> in the env log")
            if not watched["slot_line"] and b"cspboot would boot slot" in blob:
                watched["slot_line"] = True
                log("e2631boot: slot decision line seen")
            if not watched["boot_line"] and b"header and data CRCs are good" in blob:
                watched["boot_line"] = True
                log("e2631boot: load done, CRCs good; bootm next")
            if not watched["kernel_start"] and any(m in blob for m in KERNEL_START):
                watched["kernel_start"] = True
                log("KERNEL STARTED (bootm handed off)")
            for pat in PANIC_PATTERNS:
                if pat in blob:
                    if watched["panic"] is None:
                        watched["panic"] = pat.decode()
                        panic_at = len(accum)
                        log("PANIC PATTERN: " + pat.decode())
                    break
            if watched["panic"] is not None:
                time.sleep(2.0)
                more = c.read()
                if more:
                    accum.extend(more)
                break
            if watched["linux_marker"] is False and any(m in blob for m in LINUX_MARKERS):
                watched["linux_marker"] = True
                log("LINUX MARKER SEEN (userspace coming up)")
                break
            continue
        time.sleep(0.05)
    result["monitor"] = {"banner": watched["banner"], "slot_line": watched["slot_line"],
                         "boot_line": watched["boot_line"], "kernel_start": watched["kernel_start"],
                         "linux_marker": watched["linux_marker"], "panic": watched["panic"],
                         "env_ok": watched["env_ok"], "env_null": watched["env_null"],
                         "boot_lines": boot_lines, "accum_bytes": len(accum)}
    tail = bytes(accum)
    if panic_at is not None:
        result["panic_tail"] = tail[panic_at:panic_at + 6000].decode("latin-1", "replace")
    else:
        result["serial_tail"] = tail[-4000:].decode("latin-1", "replace")
    open(os.path.dirname(result["outdir"]) + "/" + str(result.get("tag", "run")) + "-boot-tail.txt", "wb").write(tail)
    return result


def reboot_to_stock(timeout=260):
    """After the RAM-chain kernel is up, reboot the SoC back into the stock chain.

    Linux resets the SoC; BootROM -> secondboot -> vendor U-Boot -> stock kernel
    again.  The flashed mtd0 is untouched, so this is the recovery path used by
    the previous session and needs no user power cycle.
    """
    rep = {"mode": "reboot-to-stock"}
    try:
        rc, out, err = b1.ssh_run("sync; (sleep 1; reboot -f) >/dev/null 2>&1 &", 30)
        rep["reboot_rc"] = rc
    except Exception as exc:  # noqa: BLE001
        rep["reboot_error"] = repr(exc)
    t0 = time.time()
    time.sleep(10)
    while time.time() - t0 < timeout:
        try:
            b1.ensure_direct_link()
            rc, out, err = b1.ssh_run("cut -d. -f1 /proc/uptime", 12)
            up = out.strip()
            if rc == 0 and up.isdigit() and int(up) < 600:
                rep.update({"ok": True, "uptime": int(up),
                            "waited_s": int(time.time() - t0)})
                return rep
        except Exception as exc:  # noqa: BLE001
            rep["last_error"] = repr(exc)
        time.sleep(6)
    rep["ok"] = False
    return rep


def stock_serial_markers():
    path = "/home/qc233/zte/e2631-serial-boot.log"
    try:
        raw = open(path, "rb").read()[-200000:].decode("latin-1", "replace")
    except Exception as exc:  # noqa: BLE001
        return {"error": repr(exc)}
    return {"Boot SPI NAND": "Boot SPI NAND" in raw,
            "U-Boot 2013.04": "U-Boot 2013.04" in raw,
            "VFS: Mounted root": "VFS: Mounted root" in raw,
            "MT7916 ready": "e2631-wifi-boot: MT7916 ready" in raw}


def run_session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/session-driver.log"
    b1.make_askpass()
    results = {"mode": "c1b0-entry-dryrun", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "outdir": outdir, "tag": "c1b0", "ready_for_user_power_cycle": False}
    pre = json.load(open(outdir + "/preflight.json"))
    pre_mtd0 = (pre.get("device") or {}).get("mtd0_sha256")
    results["pre_mtd0_sha256"] = pre_mtd0
    art = artifact_facts(ART_BIN)
    results["artifact"] = art
    results["artifact_config"] = artifact_config()
    try:
        if not (art["sha_ok"] and art["size_ok"] and art["banner_present"]):
            raise RuntimeError("A3 artifact facts do not match the approved binary")
        results["capture_before"] = base.pause_capture()
        if not results["capture_before"].get("free"):
            raise RuntimeError("tty busy after pausing the capture chain")
        results["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        results["ready_for_user_power_cycle"] = True
        save_results(outdir, results)
        log("READY FOR USER POWER CYCLE (C1a: cold boot into the vendor console)")
        entry = base.enter_vendor_console(c, args.entry_timeout)
        results["vendor_entry"] = entry
        save_results(outdir, results)
        if not entry.get("ok"):
            raise RuntimeError("vendor console entry failed: " + json.dumps(entry))
        log("vendor console ready; stock U-Boot confirmed")
        load = base.xmodem_load(c, ART_BIN, BOOT_ADDR)
        results["xmodem"] = load
        save_results(outdir, results)
        log("xmodem done: " + json.dumps(load)[:400])
        if not load.get("ok"):
            raise RuntimeError("xmodem load failed")
        md1 = md_spot_check(c, ART_BIN, "start", 0)
        md2 = md_spot_check(c, ART_BIN, "tail", ART_SIZE - 0x100, 0x100)
        banner_off = art["banner_offset"]
        md3 = md_spot_check(c, ART_BIN, "banner", banner_off & ~0xF, 0x100)
        results["md_checks"] = [md1, md2, md3]
        save_results(outdir, results)
        if not all(x["ok"] for x in results["md_checks"]):
            raise RuntimeError("md.b spot checks failed; refusing to go")
        log("go: jumping to 0x%08x; no further input will be sent" % BOOT_ADDR)
        results["go_sent"] = True
        save_results(outdir, results)
        c.pending = bytes()
        c.send(("go 0x%08x" % BOOT_ADDR).encode() + bytes([13]))
        monitor_boot(c, results, args.boot_timeout)
        open(outdir + "/console-transcript.txt", "wb").write(bytes(c.history))
        save_results(outdir, results)
        log("monitor done: " + json.dumps({k: results["monitor"].get(k) for k in
            ("banner", "slot_line", "boot_line", "kernel_start", "linux_marker", "panic")}))
    except Exception as exc:
        results["error"] = str(exc)
        log("SESSION ERROR: " + str(exc))
    finally:
        try:
            base.stop_hub()
        except Exception as exc:
            results["stop_hub_error"] = str(exc)
        try:
            results["capture_after"] = base.restore_capture()
        except Exception as exc:
            results["capture_after"] = {"ok": False, "error": str(exc)}
        results["route_fix"] = {"ok": False}
        for attempt in range(6):
            try:
                rf = b1.ensure_direct_link()
            except Exception as exc:
                rf = {"ok": False, "error": str(exc)}
            results["route_fix"] = rf
            if rf.get("ok"):
                break
            log("route fix attempt " + str(attempt + 1) + " failed; retrying")
            time.sleep(5)
        save_results(outdir, results)
        mon = results.get("monitor") or {}
        expect_linux = bool(mon.get("linux_marker") and not mon.get("panic"))
        if expect_linux:
            try:
                # The health script also self-heals the host route trap; run it
                # before device_facts() so the mtd0 readback is not skipped.
                rc, out, err = base.sh("bash " + base.HEALTH, timeout=220)
                results["health_rc"] = rc
                results["health"] = out[-4000:]
                open(outdir + "/health.txt", "w").write(out)
                log("HEALTH rc=" + str(rc))
                results["uptime_wait"] = b1.wait_uptime(70, 180)
                results["device_after"] = device_facts()
                results["recovery_reboot"] = reboot_to_stock()
                if results["recovery_reboot"].get("ok"):
                    results["device_after_stock"] = device_facts()
                    rc2, out2, err2 = base.sh("bash " + base.HEALTH, timeout=220)
                    results["health_stock_rc"] = rc2
                    results["health_stock"] = out2[-4000:]
                    open(outdir + "/health-stock.txt", "w").write(out2)
                    results["stock_serial"] = stock_serial_markers()
                    log("HEALTH-STOCK rc=" + str(rc2))
            except Exception as exc:
                results["health_error"] = str(exc)
        elif results.get("go_sent"):
            log("NO LINUX MARKER: power cycle required to return to the vendor chain")
        post_facts = (results.get("device_after_stock") or results.get("device_after") or {})
        post_mtd0 = post_facts.get("mtd0_sha256")
        results["mtd0_unchanged"] = bool(post_mtd0 and pre_mtd0 and post_mtd0 == pre_mtd0)
        health_text = results.get("health_stock", "") or results.get("health", "") or ""
        health_ok = ("VERSION=ImmortalWrt" in health_text) and ("PANICS=0" in health_text)
        stock_ok = (bool((results.get("recovery_reboot") or {}).get("ok"))
                    and bool((results.get("stock_serial") or {}).get("U-Boot 2013.04"))
                    and bool((results.get("stock_serial") or {}).get("Boot SPI NAND"))
                    and health_ok)
        mon = results.get("monitor") or {}
        results["verdict"] = "GREEN" if (
            results.get("artifact", {}).get("sha_ok")
            and results.get("vendor_entry", {}).get("ok")
            and results.get("xmodem", {}).get("ok")
            and all(x.get("ok") for x in results.get("md_checks", []))
            and results.get("go_sent")
            and mon.get("banner") and mon.get("env_ok") and not mon.get("env_null")
            and mon.get("slot_line") and mon.get("boot_line")
            and mon.get("kernel_start") and mon.get("linux_marker") and not mon.get("panic")
            and results.get("mtd0_unchanged")
            and results.get("capture_after", {}).get("ok")
            and results.get("route_fix", {}).get("ok")
            and stock_ok and not results.get("error")) else "FAIL"
        results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        save_results(outdir, results)
        log("VERDICT " + results["verdict"] + " (results in " + outdir + "/session-results.json)")
    return 0 if results["verdict"] == "GREEN" else 2


def main():
    global ART_BIN, ART_SHA, ART_SIZE, BANNER, BOOT_ADDR
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--artifact", help="u-boot.bin built with the flash entry address")
    ap.add_argument("--sha256", help="expected artifact sha256")
    ap.add_argument("--banner-token", help="banner substring proving our U-Boot runs")
    ap.add_argument("--load-addr", default="0x47F00000")
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    ap.add_argument("--entry-timeout", type=int, default=600)
    ap.add_argument("--boot-timeout", type=int, default=300)
    args = ap.parse_args()
    if not (args.artifact and args.sha256 and args.banner_token):
        ap.error("--artifact, --sha256 and --banner-token are required")
    ART_BIN = os.path.abspath(args.artifact)
    ART_SHA = args.sha256.strip().lower()
    ART_SIZE = os.path.getsize(ART_BIN)
    BANNER = args.banner_token.encode()
    BOOT_ADDR = int(args.load_addr, 16)
    if args.preflight:
        return preflight(args)
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())