#!/usr/bin/env python3
"""C1b-1a2: retry the reverse-go vendor-console sub-gate (C1b-1a follow-up).

Run-1 proved the write channel (loadx 128 B/1 KiB, mtd write/read/cmp, mtd
erase, scratch block) and that the vendor U-Boot RAM payload runs after go, but
the vendor console was missed: the RAM-booted vendor U-Boot uses its own 3 s
"*** Press 1 means entering boot mode***" window (key 1 + password), not the
"Hit any key to stop autoboot" prompt. This session repeats only stage (iii):
our RAM console -> loadx vendor-uboot-ram.bin -> go -> Press 1 -> vendor
password -> vendor "=>" -> version -> reset -> stock Linux -> health.
Zero flash writes (read-only session; scratch write was proven in run-1).
"""
import argparse, hashlib, json, os, re, sys, time

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import a1_banner_accept as base
import b1_env_session as b1

P3 = base.P3
OUT_DEFAULT = P3 + "/c1b1a2-vendor-console/run-1"
DEFAULT_ART = ("/home/qc233/zte/e2631-t5-artifacts/uboot-c1b0-44898534408/"
               "e2631-uboot-44898534408/u-boot.bin")
DEFAULT_ART_SHA = "010379fde3496fdcbbe835c249cff2bd79234f946918266721e098dd64479f75"
DEFAULT_BANNER = "U-Boot 2027.01-rc2-g2797f3dd3860"
DEFAULT_VENDOR_RAM = ("/home/qc233/zte/e2631-immortalwrt/evidence/p2-oob/"
                      "vendor-uboot-ram.bin")
DEFAULT_VENDOR_RAM_SHA = "a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30"
DEFAULT_C1B0_RESULTS = P3 + "/c1b0-entry/run-1/session-results.json"
DEFAULT_RUN1_RESULTS = P3 + "/c1b1a-rehearsal/run-1/session-results.json"
BOOT_ADDR = 0x47F00000
BASE_SHA = "887a7f6c9b407abc734eb9a76f08733a691441f91987369e8626deb8faf0fa9f"
PANIC_PATTERNS = [b"Kernel panic", b"Unable to mount root", b"VFS: Cannot open root device",
                  b"Attempting to kill init", b"end Kernel panic"]
STOCK_MARKERS = [("boot_spi_nand", b"Boot SPI NAND"), ("secondboot", b"start read bootheader"),
                 ("vendor_uboot", b"U-Boot 2013.04"), ("vfs_root", b"VFS: Mounted root"),
                 ("wifi", b"e2631-wifi-boot")]


def log(msg):
    b1.log(msg)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def cfg_facts(path):
    out = {}
    try:
        for line in open(path, errors="replace"):
            for key in ("CONFIG_TEXT_BASE", "CONFIG_SYS_PROMPT", "CONFIG_BOOTDELAY",
                        "CONFIG_CMD_MTD", "CONFIG_CMD_LOADB"):
                if line.startswith(key + "=") or line == "# " + key + " is not set":
                    out[key] = line.strip()
    except FileNotFoundError:
        pass
    return out


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    b1.make_askpass()
    art = read_file(args.artifact)
    cfg = cfg_facts(args.artifact_config)
    vendor = read_file(args.vendor_ram)
    c1b0 = json.load(open(args.c1b0_results))
    run1 = {}
    try:
        run1 = json.load(open(args.run1_results))
    except Exception as exc:
        run1 = {"error": repr(exc)}
    run1_facts = {
        "loadx_128": bool((run1.get("loadx_128") or {}).get("ok")),
        "loadx_1024": bool((run1.get("loadx_1024") or {}).get("ok")),
        "loadx_128_md": bool((run1.get("loadx_128_md") or {}).get("ok")),
        "loadx_1024_md": bool((run1.get("loadx_1024_md") or {}).get("ok")),
        "scratch_readback_md": bool((run1.get("scratch_readback_md") or {}).get("ok")),
        "scratch_erase_md": bool((run1.get("scratch_erase_md") or {}).get("ok")),
        "vendor_md": bool((run1.get("vendor_md") or {}).get("ok")),
        "vendor_banner": bool((run1.get("vendor_stop_autoboot") or {}).get("banner_seen")),
    }
    run1_ok = all(run1_facts.values())
    route = base.sh("ip route get 192.168.1.1 | head -1")[1]
    chain = {"supervisor_pids": base.pgrep("capture-supervisor-002.sh"),
             "bootwatch_pids": base.pgrep("serial-bootwatch.mjs"),
             "tty_holders": base.tty_holders()}
    dev = {}
    try:
        rc, out, err = b1.ssh_run("sha256sum /dev/mtd0; cut -d. -f1 /proc/uptime; cat /etc/e2631-version; uname -r", 40)
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        dev = {"ssh_rc": rc, "mtd0_sha256": lines[0].split()[0] if lines else None,
               "uptime": lines[1] if len(lines) > 1 else None,
               "version": lines[2] if len(lines) > 2 else None,
               "kernel": lines[3] if len(lines) > 3 else None}
    except Exception as exc:
        dev = {"error": repr(exc)}
    rep = {"mode": "c1b1a2-preflight",
           "artifact": {"path": args.artifact, "size": len(art), "sha256": sha_bytes(art),
                        "sha_ok": sha_bytes(art) == args.sha256.lower(),
                        "token": args.banner_token, "token_ok": args.banner_token.encode() in art,
                        "token_offset": art.find(args.banner_token.encode())},
           "config": cfg, "config_text_base": cfg.get("CONFIG_TEXT_BASE"),
           "vendor_ram": {"size": len(vendor), "sha256": sha_bytes(vendor),
                          "sha_ok": sha_bytes(vendor) == args.vendor_ram_sha.lower()},
           "c1b0_green": c1b0.get("verdict") == "GREEN",
           "run1_facts": run1_facts, "run1_ok": run1_ok,
           "device": dev, "route": route, "capture_chain": chain,
           "start_mode": args.start_mode,
           "vendor_pw_mode": oct(os.stat(base.VENDOR_PW_FILE).st_mode & 0o777)}
    rep["ok"] = bool(rep["artifact"]["sha_ok"] and rep["artifact"]["token_ok"]
                    and rep["vendor_ram"]["sha_ok"] and rep["c1b0_green"] and run1_ok
                    and rep["config_text_base"] == "CONFIG_TEXT_BASE=0x47F00000"
                    and chain["supervisor_pids"] and chain["bootwatch_pids"] and chain["tty_holders"]
                    and dev.get("mtd0_sha256") == BASE_SHA and "via " not in route
                    and rep["vendor_pw_mode"] == "0o600")
    json.dump(rep, open(args.out_dir + "/preflight.json", "w"), indent=1)
    print(json.dumps(rep, indent=1))
    log("preflight ok=%s run1_ok=%s" % (rep["ok"], run1_ok))
    return 0 if rep["ok"] else 2


def wait_prompt(c, timeout=120):
    pat = re.compile(rb"\r\n=> ")
    deadline = time.time() + timeout
    while True:
        m = pat.search(c.pending)
        if m:
            head = bytes(c.pending[:m.end()])
            c.pending = bytes(c.pending[m.end():])
            return head
        data = c.read()
        if data:
            c.pending += data
            continue
        if time.time() > deadline:
            return None
        time.sleep(0.02)


ALLOW_PATTERNS = [
    r"^(help|version|printenv)$",
    r"^md\.b 0x[0-9a-fA-F]+ 0x[0-9a-fA-F]+$",
    r"^mtd list$",
    r"^loadx 0x[0-9a-fA-F]+$",
    r"^go 0x47f00000$",
    r"^reset$",
]
DENY_TOKENS = ("nand ", "saveenv", "upgrade", "tftp", "bootm", "mtd write", "mtd erase")


def check_command(text):
    low = text.strip().lower()
    if any(t in low for t in DENY_TOKENS):
        return False
    return any(re.match(p, low) for p in ALLOW_PATTERNS)


def send_checked(c, results, text, timeout=120):
    if not check_command(text):
        raise RuntimeError("refusing non-whitelisted console command: " + text)
    results.setdefault("commands", []).append(text)
    c.pending = bytes()
    c.send((text + "\r").encode())
    out = wait_prompt(c, timeout)
    results.setdefault("command_outputs", {})[text] = (out or b"")[-2000:].decode("latin-1", "replace")
    return out


def xmodem_cmd(c, results, path, command, block_size, first_timeout=60.0):
    results.setdefault("commands", []).append(command.strip())
    c.pending = bytes()
    t0 = time.time()
    try:
        res = base.ctl_call({"op": "xmodem", "path": path, "block_size": block_size,
                             "first_timeout": first_timeout, "command": command}, timeout=900.0)
    except Exception as exc:
        res = {"ok": False, "error": repr(exc)}
    res["elapsed_s"] = round(time.time() - t0, 1)
    c.wait_until_quiet(0.6, 15)
    log("xmodem_cmd %s block=%d ok=%s elapsed=%ss" % (command.strip(), block_size, res.get("ok"), res.get("elapsed_s")))
    return res


def md_capture(c, results, label, addr, size):
    out = bytearray()
    gaps = 0
    for off in range(0, size, 0x4000):
        n = min(0x4000, size - off)
        text, got, g = c.md_read("md.b 0x%08x 0x%x" % (addr + off, n), addr + off, n, 240)
        results.setdefault("commands", []).append("md.b 0x%08x 0x%x" % (addr + off, n))
        out.extend(got)
        gaps += g
    return bytes(out), gaps


def md_check(c, results, label, addr, want):
    got, gaps = md_capture(c, results, label, addr, len(want))
    ok = got == want and gaps == 0
    rep = {"label": label, "addr": hex(addr), "size": len(want), "ok": ok, "gaps": gaps,
           "want_sha256": sha_bytes(want), "got_sha256": sha_bytes(got)}
    log("md_check %s: %s" % (label, "OK" if ok else "MISMATCH"))
    return rep


def stop_autoboot(c, results, banner, timeout=45):
    pat = re.compile(re.escape(banner.encode()))
    deadline = time.time() + timeout
    seen = False
    spaces = 0
    while time.time() < deadline:
        if not seen and pat.search(c.pending):
            seen = True
            log("banner seen; stopping autoboot")
        if seen and spaces < 20:
            c.send(b" ")
            spaces += 1
            time.sleep(0.15)
        data = c.read()
        if data:
            c.pending += data
            continue
        if seen and spaces >= 20:
            break
        time.sleep(0.02)
    out = wait_prompt(c, 20)
    rep = {"banner_seen": seen, "spaces_sent": spaces, "prompt": out is not None,
           "tail": (out or c.pending)[-800:].decode("latin-1", "replace")}
    log("stop_autoboot: " + json.dumps({"banner": seen, "prompt": rep["prompt"]}))
    return rep


def monitor_stock_file(log_path, results, timeout=300):
    patterns = dict(STOCK_MARKERS)
    seen = {k: False for k in patterns}
    panic = None
    blob = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = open(log_path, "rb").read()
            blob = data[-4 * 1024 * 1024:]
        except FileNotFoundError:
            blob = b""
        for k, p in patterns.items():
            if not seen[k] and p in blob:
                seen[k] = True
                log("stock marker: " + k)
        for p in PANIC_PATTERNS:
            if p in blob:
                panic = p.decode()
        if seen["vfs_root"] or panic:
            break
        time.sleep(0.5)
    results["stock_monitor"] = dict(seen)
    results["stock_monitor"]["panic"] = panic
    results["stock_monitor"]["log_bytes"] = len(blob)
    return results


def trigger_ssh_reboot(c):
    rc, out, err = b1.ssh_run("sync; (sleep 1; reboot -f) >/dev/null 2>&1 &", 30)
    log("ssh reboot rc=%s err=%s" % (rc, err[-120:]))
    return {"rc": rc, "err_tail": err[-200:]}


def run_session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/session-driver.log"
    b1.make_askpass()
    pre = json.load(open(outdir + "/preflight.json"))
    results = {"mode": "c1b1a2-vendor-console", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "outdir": outdir, "artifact": pre["artifact"], "start_mode": args.start_mode,
               "expected_mtd0_sha256": BASE_SHA}
    c = None
    try:
        if not pre.get("ok"):
            raise RuntimeError("preflight is not ok")
        results["capture_before"] = base.pause_capture()
        if not results["capture_before"].get("free"):
            raise RuntimeError("tty busy after pausing capture")
        results["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        json.dump(results, open(outdir + "/session-results.json", "w"), indent=1)
        if args.start_mode == "ssh-reboot":
            log("triggering SSH reboot to catch the vendor Press-1 prompt (no manual power cycle)")
            results["reboot_trigger"] = trigger_ssh_reboot(c)
        else:
            log("READY FOR USER POWER CYCLE (C1b-1a2 vendor-console retry)")
        entry = base.enter_vendor_console(c, args.entry_timeout)
        results["vendor_entry"] = entry
        if not entry.get("ok"):
            raise RuntimeError("vendor console entry failed: " + json.dumps(entry))
        art = read_file(args.artifact)
        load = base.xmodem_load(c, args.artifact, BOOT_ADDR)
        results["uboot_xmodem"] = load
        if not load.get("ok"):
            raise RuntimeError("u-boot.bin xmodem failed")
        tok = pre["artifact"]["token_offset"] & ~0xF
        results["uboot_md"] = [
            md_check(c, results, "uboot-start", BOOT_ADDR, art[:0x100]),
            md_check(c, results, "uboot-banner", BOOT_ADDR + tok, art[tok:tok + 0x100]),
            md_check(c, results, "uboot-tail", BOOT_ADDR + len(art) - 0x100, art[-0x100:]),
        ]
        if not all(r["ok"] for r in results["uboot_md"]):
            raise RuntimeError("u-boot.bin md.b verification failed")
        c.pending = bytes()
        c.send(b"go 0x47f00000\r")
        results["commands"] = ["go 0x47f00000"]
        results["our_stop_autoboot"] = stop_autoboot(c, results, args.banner_token, args.banner_timeout)
        if not results["our_stop_autoboot"]["prompt"]:
            raise RuntimeError("no => prompt in our U-Boot after go")
        version = send_checked(c, results, "version", 60)
        results["our_version_ok"] = bool(version and args.banner_token.encode() in version)
        vendor = read_file(args.vendor_ram)
        vload = xmodem_cmd(c, results, args.vendor_ram, "loadx 0x47f00000\r", 128, 90.0)
        results["vendor_loadx"] = vload
        if not vload.get("ok"):
            raise RuntimeError("loadx of vendor-uboot-ram.bin failed")
        results["vendor_md"] = md_check(c, results, "vendor-ram", BOOT_ADDR, vendor)
        if not results["vendor_md"]["ok"]:
            raise RuntimeError("vendor-uboot-ram.bin md.b mismatch")
        c.pending = bytes()
        c.send(b"go 0x47f00000\r")
        results["commands"].append("go 0x47f00000")
        log("reverse go sent; waiting for the vendor Press-1 boot-mode window")
        ventry = base.enter_vendor_console(c, args.vendor_console_timeout)
        results["vendor_console"] = ventry
        if not ventry.get("ok"):
            raise RuntimeError("vendor console did not come up after the reverse go: " + json.dumps(ventry))
        results["vendor_prompt_ok"] = True
        results["vendor_version_ok"] = bool(ventry.get("stock_banner"));
        send_checked(c, results, "reset", 30)
        results["vendor_reset_sent"] = True
        monitor_stock_file(outdir + "/serial.log", results, args.stock_timeout)
        open(outdir + "/console-transcript.txt", "wb").write(bytes(c.history))
    except Exception as exc:
        results["error"] = str(exc)
        log("SESSION ERROR: " + str(exc))
        open(outdir + "/console-transcript.txt", "wb").write(bytes(c.history) if c else b"")
    finally:
        try:
            base.stop_hub()
        except Exception as exc:
            results["stop_hub_error"] = str(exc)
        try:
            results["capture_after"] = base.restore_capture()
        except Exception as exc:
            results["capture_after"] = {"ok": False, "error": str(exc)}
        json.dump(results, open(outdir + "/session-results.json", "w"), indent=1)
        stock = results.get("stock_monitor") or {}
        health_text = ""
        if stock.get("vfs_root") and not stock.get("panic"):
            try:
                rc, out, err = base.sh("bash " + base.HEALTH, timeout=220)
                results["health_rc"] = rc
                health_text = out
                results["health"] = out[-4000:]
                open(outdir + "/health.txt", "w").write(out)
            except Exception as exc:
                results["health_error"] = str(exc)
        try:
            results["uptime_wait"] = b1.wait_uptime(70, 180)
            rc2, out2, err2 = b1.ssh_run("sha256sum /dev/mtd0; cut -d. -f1 /proc/uptime; cat /etc/e2631-version; uname -r", 40)
            lines = [l.strip() for l in out2.splitlines() if l.strip()]
            results["post_mtd0_sha256"] = lines[0].split()[0] if lines else None
            results["post_uptime"] = lines[1] if len(lines) > 1 else None
            results["post_version"] = lines[2] if len(lines) > 2 else None
            results["post_kernel"] = lines[3] if len(lines) > 3 else None
        except Exception as exc:
            results["post_error"] = repr(exc)
        cmds = results.get("commands", [])
        results["write_audit"] = {
            "mtd_writes": [c for c in cmds if c.startswith("mtd write")],
            "mtd_erases": [c for c in cmds if c.startswith("mtd erase")],
            "forbidden_tokens": [c for c in cmds if re.search(r"(?<!-)\bnand\b|saveenv|upgrade|tftp|bootm", c)],
        }
        results["mtd0_unchanged"] = bool(results.get("post_mtd0_sha256") == BASE_SHA)
        health_ok = ("VERSION=ImmortalWrt" in health_text) and ("PANICS=0" in health_text)
        results["health_ok"] = health_ok
        mon = results.get("stock_monitor") or {}
        results["verdict"] = "GREEN" if (
            results.get("our_version_ok")
            and (results.get("vendor_loadx") or {}).get("ok")
            and (results.get("vendor_md") or {}).get("ok")
            and results.get("vendor_prompt_ok")
            and results.get("vendor_version_ok")
            and results.get("vendor_reset_sent")
            and mon.get("vfs_root") and not mon.get("panic")
            and results.get("mtd0_unchanged")
            and results.get("health_ok")
            and (results.get("capture_after") or {}).get("ok")
            and not results["write_audit"]["mtd_writes"]
            and not results["write_audit"]["mtd_erases"]
            and not results["write_audit"]["forbidden_tokens"]
            and not results.get("error")) else "FAIL"
        results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        json.dump(results, open(outdir + "/session-results.json", "w"), indent=1)
        log("VERDICT " + results["verdict"])
    return 0 if results["verdict"] == "GREEN" else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--artifact", default=DEFAULT_ART)
    ap.add_argument("--sha256", default=DEFAULT_ART_SHA)
    ap.add_argument("--banner-token", default=DEFAULT_BANNER)
    ap.add_argument("--artifact-config", default=DEFAULT_ART.rsplit("/", 1)[0] + "/.config")
    ap.add_argument("--vendor-ram", default=DEFAULT_VENDOR_RAM)
    ap.add_argument("--vendor-ram-sha", default=DEFAULT_VENDOR_RAM_SHA)
    ap.add_argument("--c1b0-results", default=DEFAULT_C1B0_RESULTS)
    ap.add_argument("--run1-results", default=DEFAULT_RUN1_RESULTS)
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    ap.add_argument("--start-mode", choices=("cold", "ssh-reboot"), default="cold")
    ap.add_argument("--entry-timeout", type=int, default=600)
    ap.add_argument("--banner-timeout", type=int, default=45)
    ap.add_argument("--vendor-console-timeout", type=int, default=90)
    ap.add_argument("--stock-timeout", type=int, default=300)
    args = ap.parse_args()
    if args.preflight:
        return preflight(args)
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())