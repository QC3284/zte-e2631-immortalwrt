#!/usr/bin/env python3
"""C1b-1a: flash write-channel dress rehearsal (task-54 gates).

Cold boot -> vendor console -> xmodem our 0x47F00000 u-boot.bin -> go -> OUR
console -> (i) loadx behaviour at 128 B and 1 KiB blocks; (ii) mtd write a
deterministic 0x20000 block into the UNUSED tail at 0x7F00000, mtd read it
back, byte-compare, then mtd erase and verify 0xFF; (iii) loadx the tracked
vendor-uboot-ram.bin (426,048 B, sha256 a4c640ad...) to 0x47F00000, go, prove
the vendor console takes over, vendor reset -> stock Linux -> health.
Scope: exactly one mtd write + one mtd erase, both on the scratch block
0x7F00000..0x7F20000, outside every partition. mtd0 is checked unchanged.
"""
import argparse, hashlib, json, os, re, sys, time

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import a1_banner_accept as base
import b1_env_session as b1

P3 = base.P3
OUT_DEFAULT = P3 + "/c1b1a-rehearsal/run-1"
DEFAULT_ART = ("/home/qc233/zte/e2631-t5-artifacts/uboot-c1b0-44898534408/"
               "e2631-uboot-44898534408/u-boot.bin")
DEFAULT_ART_SHA = "010379fde3496fdcbbe835c249cff2bd79234f946918266721e098dd64479f75"
DEFAULT_BANNER = "U-Boot 2027.01-rc2-g2797f3dd3860"
DEFAULT_VENDOR_RAM = ("/home/qc233/zte/e2631-immortalwrt/evidence/p2-oob/"
                      "vendor-uboot-ram.bin")
DEFAULT_VENDOR_RAM_SHA = "a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30"
DEFAULT_C1B0_RESULTS = P3 + "/c1b0-entry/run-1/session-results.json"
BOOT_ADDR = 0x47F00000
RAM_TEST = 0x42000000
RAM_READ = 0x43000000
RAM_ERASE = 0x44000000
RAM_CHUNK = 0x4000
SCRATCH_OFF = 0x7F00000
SCRATCH_SIZE = 0x20000
CHIP_SIZE = 0x8000000
PARTITION_END = 0x6E00000
BASE_SHA = "887a7f6c9b407abc734eb9a76f08733a691441f91987369e8626deb8faf0fa9f"
PANIC_PATTERNS = [b"Kernel panic", b"Unable to mount root", b"VFS: Cannot open root device",
                  b"Attempting to kill init", b"end Kernel panic"]


def log(msg):
    b1.log(msg)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def test_data(path, size):
    """Deterministic non-0xFF pattern so mtd write cannot skip every page."""
    buf = bytes(((i * 37) + 11) & 0xFF for i in range(size))
    open(path, "wb").write(buf)
    return buf


def cfg_facts(path):
    out = {}
    try:
        for line in open(path, errors="replace"):
            for key in ("CONFIG_TEXT_BASE", "CONFIG_SYS_PROMPT", "CONFIG_BOOTDELAY",
                        "CONFIG_CMD_MTD", "CONFIG_CMD_LOADB", "CONFIG_CMD_MEMORY"):
                if line.startswith(key + "=") or line == "# " + key + " is not set":
                    out[key] = line.strip()
    except FileNotFoundError:
        pass
    return out


def artifact_facts(args):
    raw = read_file(args.artifact)
    facts = {"path": args.artifact, "size": len(raw), "sha256": sha_bytes(raw),
             "sha_ok": sha_bytes(raw) == args.sha256.lower(),
             "token": args.banner_token, "token_offset": raw.find(args.banner_token.encode()),
             "token_ok": args.banner_token.encode() in raw,
             "entry_bytes": raw[:8].hex()}
    return facts, raw


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    b1.make_askpass()
    art, raw = artifact_facts(args)
    cfg = cfg_facts(args.artifact_config) if args.artifact_config else {}
    vendor = read_file(args.vendor_ram)
    vendor_ok = sha_bytes(vendor) == args.vendor_ram_sha.lower()
    data = test_data(args.out_dir + "/scratch-0x20000.bin", args.scratch_size)
    c1b0 = {}
    try:
        c1b0 = json.load(open(args.c1b0_results))
    except Exception as exc:
        c1b0 = {"error": repr(exc)}
    c1b0_ok = bool(c1b0.get("verdict") == "GREEN"
                   and (c1b0.get("artifact") or {}).get("sha256") == args.sha256.lower())
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
    scratch_ok = (args.scratch_off >= 0x7F00000 and args.scratch_off + args.scratch_size <= CHIP_SIZE
                  and args.scratch_off + args.scratch_size <= 0x8000000
                  and args.scratch_off >= PARTITION_END)
    cmd_mtd = any("CONFIG_CMD_MTD=y" == v for v in cfg.values())
    cmd_loadb = any("CONFIG_CMD_LOADB=y" == v for v in cfg.values())
    text_base = cfg.get("CONFIG_TEXT_BASE")
    data_ok = bool(data) and len(set(data)) > 1 and any(b != 0xFF for b in data[:0x800])
    rep = {"mode": "c1b1a-preflight", "artifact": art, "config": cfg,
           "config_text_base": text_base, "config_cmd_mtd": cmd_mtd, "config_cmd_loadb": cmd_loadb,
           "vendor_ram": {"path": args.vendor_ram, "size": len(vendor),
                          "sha256": sha_bytes(vendor), "sha_ok": vendor_ok},
           "test_data": {"path": args.out_dir + "/scratch-0x20000.bin",
                         "size": len(data), "sha256": sha_bytes(data), "ok": data_ok},
           "scratch": {"off": hex(args.scratch_off), "size": hex(args.scratch_size),
                       "range": hex(args.scratch_off) + ".." + hex(args.scratch_off + args.scratch_size),
                       "outside_all_partitions": scratch_ok, "partition_end": hex(PARTITION_END),
                       "chip_size": hex(CHIP_SIZE),
                       "write_cmd": "mtd write spi-nand0 0x%08x 0x%x 0x%x" % (RAM_TEST, args.scratch_off, args.scratch_size),
                       "erase_cmd": "mtd erase spi-nand0 0x%x 0x%x" % (args.scratch_off, args.scratch_size)},
           "c1b0_green": c1b0_ok, "device": dev, "route": route, "capture_chain": chain,
           "vendor_pw_mode": oct(os.stat(base.VENDOR_PW_FILE).st_mode & 0o777)}
    rep["ok"] = bool(art["sha_ok"] and art["token_ok"] and vendor_ok and data_ok and scratch_ok
                    and c1b0_ok and cmd_mtd and cmd_loadb
                    and text_base == "CONFIG_TEXT_BASE=0x47F00000"
                    and chain["supervisor_pids"] and chain["bootwatch_pids"] and chain["tty_holders"]
                    and dev.get("mtd0_sha256") == BASE_SHA and "via " not in route
                    and rep["vendor_pw_mode"] == "0o600")
    json.dump(rep, open(args.out_dir + "/preflight.json", "w"), indent=1)
    print(json.dumps(rep, indent=1))
    log("preflight ok=%s scratch=%s" % (rep["ok"], rep["scratch"]["range"]))
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
    r"^cmp 0x[0-9a-fA-F]+ 0x[0-9a-fA-F]+ 0x[0-9a-fA-F]+$",
    r"^mtd list$",
    r"^mtd read spi-nand0 0x[0-9a-fA-F]+ 0x[0-9a-fA-F]+ 0x[0-9a-fA-F]+$",
    r"^mtd write spi-nand0 0x[0-9a-fA-F]+ 0x7f00000 0x20000$",
    r"^mtd erase spi-nand0 0x7f00000 0x20000$",
    r"^loadx 0x[0-9a-fA-F]+$",
    r"^go 0x47f00000$",
    r"^reset$",
]
DENY_TOKENS = ("nand ", "saveenv", "upgrade", "tftp", "bootm")


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
    import base64 as _b64
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
    for off in range(0, size, RAM_CHUNK):
        n = min(RAM_CHUNK, size - off)
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


def monitor_stock(c, results, timeout=300):
    patterns = {"boot_spi_nand": b"Boot SPI NAND", "secondboot": b"start read bootheader",
                "vendor_uboot": b"U-Boot 2013.04", "vfs_root": b"VFS: Mounted root",
                "wifi": b"e2631-wifi-boot"}
    seen = {k: False for k in patterns}
    panic = None
    accum = bytearray()
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = c.read()
        if data:
            accum.extend(data)
            blob = bytes(accum)
            for k, p in patterns.items():
                if not seen[k] and p in blob:
                    seen[k] = True
            for p in PANIC_PATTERNS:
                if p in blob:
                    panic = p.decode()
            if seen["vfs_root"] or panic:
                break
            continue
        if time.time() > deadline:
            break
        time.sleep(0.05)
    results["stock_monitor"] = dict(seen)
    results["stock_monitor"]["panic"] = panic
    results["stock_monitor"]["bytes"] = len(accum)
    return results


def run_session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/session-driver.log"
    b1.make_askpass()
    pre = json.load(open(outdir + "/preflight.json"))
    results = {"mode": "c1b1a-rehearsal", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "outdir": outdir, "artifact": pre["artifact"], "scratch": pre["scratch"],
               "expected_mtd0_sha256": BASE_SHA}
    c = None
    try:
        if not pre.get("ok"):
            raise RuntimeError("preflight is not ok; refusing any flash write")
        results["capture_before"] = base.pause_capture()
        if not results["capture_before"].get("free"):
            raise RuntimeError("tty busy after pausing capture")
        results["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        json.dump(results, open(outdir + "/session-results.json", "w"), indent=1)
        log("READY FOR USER POWER CYCLE (C1b-1a rehearsal)")
        entry = base.enter_vendor_console(c, args.entry_timeout)
        results["vendor_entry"] = entry
        if not entry.get("ok"):
            raise RuntimeError("vendor console entry failed: " + json.dumps(entry))
        art = read_file(args.artifact)
        load = base.xmodem_load(c, args.artifact, BOOT_ADDR)
        results["uboot_xmodem"] = load
        if not load.get("ok"):
            raise RuntimeError("u-boot.bin xmodem failed")
        results["uboot_md"] = [
            md_check(c, results, "uboot-start", BOOT_ADDR, art[:0x100]),
            md_check(c, results, "uboot-banner", BOOT_ADDR + (pre["artifact"]["token_offset"] & ~0xF),
                     art[(pre["artifact"]["token_offset"] & ~0xF):(pre["artifact"]["token_offset"] & ~0xF) + 0x100]),
            md_check(c, results, "uboot-tail", BOOT_ADDR + len(art) - 0x100, art[-0x100:]),
        ]
        if not all(r["ok"] for r in results["uboot_md"]):
            raise RuntimeError("u-boot.bin md.b verification failed")
        c.pending = bytes()
        c.send(b"go 0x47f00000\r")
        results["commands"] = ["go 0x47f00000"]
        results["stop_autoboot"] = stop_autoboot(c, results, args.banner_token, args.banner_timeout)
        if not results["stop_autoboot"]["prompt"]:
            raise RuntimeError("no => prompt after go (autoboot not stopped)")
        version = send_checked(c, results, "version", 60)
        results["version_ok"] = bool(version and args.banner_token.encode() in version)
        mtdlist = send_checked(c, results, "mtd list", 60)
        mtext = (mtdlist or b"").decode("latin-1", "replace")
        results["mtd_list"] = mtext[-2500:]
        results["mtd_list_ok"] = all(s in mtext for s in (
            "List of MTD devices:", "spi-nand0", "block size: 0x20000",
            "min I/O: 0x800", "OOB size: 64"))
        data = read_file(outdir + "/scratch-0x20000.bin")
        lx128 = xmodem_cmd(c, results, outdir + "/scratch-0x20000.bin", "loadx 0x42000000\r", 128)
        results["loadx_128"] = lx128
        if not lx128.get("ok"):
            raise RuntimeError("loadx 128 B block test failed")
        results["loadx_128_md"] = md_check(c, results, "loadx-128-data", RAM_TEST, data)
        if not results["loadx_128_md"]["ok"]:
            raise RuntimeError("loadx 128 B data md.b mismatch")
        lx1k = xmodem_cmd(c, results, outdir + "/scratch-0x20000.bin", "loadx 0x42000000\r", 1024, 30.0)
        results["loadx_1024"] = lx1k
        if not lx1k.get("ok"):
            log("loadx 1KiB block test failed as expected; aborting the receiver")
            c.send(b"\x18\x18")
            time.sleep(0.3)
            c.send(b"\x03")
            time.sleep(0.2)
            c.send(b"\r")
            wait_prompt(c, 15)
        else:
            results["loadx_1024_md"] = md_check(c, results, "loadx-1024-data", RAM_TEST, data)
        redo = xmodem_cmd(c, results, outdir + "/scratch-0x20000.bin", "loadx 0x42000000\r", 128)
        results["loadx_redo"] = redo
        if not redo.get("ok"):
            raise RuntimeError("loadx reload after the block-size test failed")
        results["loadx_redo_md"] = md_check(c, results, "loadx-redo-data", RAM_TEST, data)
        if not results["loadx_redo_md"]["ok"]:
            raise RuntimeError("loadx reload md.b mismatch")
        write_cmd = "mtd write spi-nand0 0x%08x 0x%x 0x%x" % (RAM_TEST, args.scratch_off, args.scratch_size)
        wout = send_checked(c, results, write_cmd, 180)
        wtext = (wout or b"").decode("latin-1", "replace")
        results["mtd_write"] = {"cmd": write_cmd, "tail": wtext[-1500:],
                                "error_tokens": [t for t in ("ERROR", "error", "Failed", "failed") if t in wtext]}
        if results["mtd_write"]["error_tokens"]:
            raise RuntimeError("mtd write reported errors")
        read_cmd = "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (RAM_READ, args.scratch_off, args.scratch_size)
        rout = send_checked(c, results, read_cmd, 120)
        results["mtd_read_tail"] = (rout or b"")[-800:].decode("latin-1", "replace")
        results["scratch_readback_md"] = md_check(c, results, "scratch-readback", RAM_READ, data)
        cmpout = send_checked(c, results, "cmp 0x%08x 0x%08x 0x%x" % (RAM_TEST, RAM_READ, args.scratch_size), 120)
        results["scratch_cmp"] = (cmpout or b"")[-800:].decode("latin-1", "replace")
        erase_cmd = "mtd erase spi-nand0 0x%x 0x%x" % (args.scratch_off, args.scratch_size)
        eout = send_checked(c, results, erase_cmd, 180)
        results["mtd_erase_tail"] = (eout or b"")[-800:].decode("latin-1", "replace")
        erout = send_checked(c, results, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (RAM_ERASE, args.scratch_off, args.scratch_size), 120)
        results["mtd_read_erase_tail"] = (erout or b"")[-800:].decode("latin-1", "replace")
        results["scratch_erase_md"] = md_check(c, results, "scratch-erase-readback", RAM_ERASE, b"\xff" * args.scratch_size)
        vendor = read_file(args.vendor_ram)
        vload = xmodem_cmd(c, results, args.vendor_ram, "loadx 0x47f00000\r", 128, 90.0)
        results["vendor_loadx"] = vload
        if not vload.get("ok"):
            raise RuntimeError("loadx of vendor-uboot-ram.bin failed")
        results["vendor_md"] = md_check(c, results, "vendor-ram", BOOT_ADDR, vendor)
        if not results["vendor_md"]["ok"]:
            raise RuntimeError("vendor-uboot-ram.bin md.b mismatch")
        send_checked(c, results, "go 0x47f00000", 30)
        results["vendor_stop_autoboot"] = stop_autoboot(c, results, "U-Boot 2013.04", args.vendor_banner_timeout)
        if not results["vendor_stop_autoboot"]["banner_seen"]:
            raise RuntimeError("vendor U-Boot banner did not appear after the reverse go")
        results["vendor_prompt_ok"] = results["vendor_stop_autoboot"]["prompt"]
        if results["vendor_prompt_ok"]:
            vver = send_checked(c, results, "version", 30)
            results["vendor_version_tail"] = (vver or b"")[-600:].decode("latin-1", "replace")
        send_checked(c, results, "reset", 30)
        results["vendor_reset_sent"] = True
        monitor_stock(c, results, args.stock_timeout)
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
        if stock.get("vfs_root") and not stock.get("panic"):
            try:
                rc, out, err = base.sh("bash " + base.HEALTH, timeout=220)
                results["health_rc"] = rc
                results["health"] = out[-4000:]
                open(outdir + "/health.txt", "w").write(out)
                results["uptime_wait"] = b1.wait_uptime(70, 180)
                rc2, out2, err2 = b1.ssh_run("sha256sum /dev/mtd0; cut -d. -f1 /proc/uptime; cat /etc/e2631-version; uname -r", 40)
                lines = [l.strip() for l in out2.splitlines() if l.strip()]
                results["post_mtd0_sha256"] = lines[0].split()[0] if lines else None
                results["post_uptime"] = lines[1] if len(lines) > 1 else None
                results["post_version"] = lines[2] if len(lines) > 2 else None
                results["post_kernel"] = lines[3] if len(lines) > 3 else None
            except Exception as exc:
                results["health_error"] = str(exc)
        cmds = results.get("commands", [])
        results["write_audit"] = {
            "mtd_writes": [c for c in cmds if c.startswith("mtd write")],
            "mtd_erases": [c for c in cmds if c.startswith("mtd erase")],
            "forbidden": [c for c in cmds if re.search(r"nand|saveenv|upgrade|tftp|bootm", c)],
        }
        results["mtd0_unchanged"] = bool(results.get("post_mtd0_sha256") == BASE_SHA)
        health_text = results.get("health", "") or ""
        results["health_ok"] = ("VERSION=ImmortalWrt" in health_text) and ("PANICS=0" in health_text)
        mon = results.get("stock_monitor") or {}
        results["verdict"] = "GREEN" if (
            results.get("version_ok")
            and results.get("mtd_list_ok")
            and (results.get("loadx_128") or {}).get("ok")
            and (results.get("loadx_128_md") or {}).get("ok")
            and (results.get("loadx_redo_md") or {}).get("ok")
            and not (results.get("mtd_write") or {}).get("error_tokens")
            and (results.get("scratch_readback_md") or {}).get("ok")
            and (results.get("scratch_erase_md") or {}).get("ok")
            and (results.get("vendor_loadx") or {}).get("ok")
            and (results.get("vendor_md") or {}).get("ok")
            and (results.get("vendor_stop_autoboot") or {}).get("banner_seen")
            and results.get("vendor_prompt_ok")
            and results.get("vendor_reset_sent")
            and mon.get("vfs_root") and not mon.get("panic")
            and results.get("mtd0_unchanged")
            and results.get("health_ok")
            and (results.get("capture_after") or {}).get("ok")
            and len(results["write_audit"]["mtd_writes"]) == 1
            and len(results["write_audit"]["mtd_erases"]) == 1
            and not results["write_audit"]["forbidden"]
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
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    ap.add_argument("--scratch-off", type=lambda s: int(s, 0), default=SCRATCH_OFF)
    ap.add_argument("--scratch-size", type=lambda s: int(s, 0), default=SCRATCH_SIZE)
    ap.add_argument("--entry-timeout", type=int, default=600)
    ap.add_argument("--banner-timeout", type=int, default=45)
    ap.add_argument("--vendor-banner-timeout", type=int, default=60)
    ap.add_argument("--stock-timeout", type=int, default=300)
    args = ap.parse_args()
    if args.preflight:
        return preflight(args)
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())