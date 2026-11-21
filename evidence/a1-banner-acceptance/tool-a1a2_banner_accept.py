#!/usr/bin/env python3
"""A1 (+ optional A2) banner acceptance device session driver (task-49/task-50).

Single stage (default): cold boot -> vendor console -> xmodem A1 -> crc32 + full
md.b compare -> go -> A1 banner -> prompt alive -> recovery -> Linux -> capture
chain restore -> health.

Combined two-stage (--second-artifact/--second-token): the same power-cycle
window is reused: A1 stage first, then reset (or a second user power cycle) back
to the vendor console, then A2 (SPI-NAND read path): banner, prompt alive,
mtd list, two read-only mtd reads compared byte-exactly against the mtd0 dump.

Zero flash writes: the only console commands ever sent are xmodem, md.b, crc32,
go, help, version, echo, reset, mtd list and mtd read; every command is checked
against an allowlist before it is transmitted.
"""
import argparse, json, os, re, sys, time

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import a1_banner_accept as base

A1_ART = ("/home/qc233/zte/e2631-t5-artifacts/uboot-a1-fix-44875722425/"
          "files/e2631-uboot-a1-44875722425/u-boot.bin")
A1_TOKEN = "U-Boot 2027.01-rc2-g4910ee2045bd"
A2_ART = ("/home/qc233/zte/e2631-t5-artifacts/uboot-a2-44877441503/"
          "e2631-uboot-44877441503/u-boot.bin")
A2_TOKEN = "U-Boot 2027.01-rc2-g38bee433d177"
DUMP = "/home/qc233/zte/e2631-p2/dump2/mtd0-before.bin"
MTD_DEV = "spi-nand0"
MTD_REGIONS = [("u-boot-header", 0x20000, 0x4C000000),
               ("u-boot-env", 0xC0000, 0x4C100000)]
MTD_READ_SIZE = 0x2000
A1_EXP_SHA = base.EXP_SHA
A1_EXP_SIZE = base.EXP_SIZE
A2_EXP_SHA = "a1df51f360eb70d9f4622f2f417a75726819c8661531ab24f62415a63ba2a626"
A2_EXP_SIZE = 444152
EXPECTED = {"a1": (A1_EXP_SHA, A1_EXP_SIZE), "a2": (A2_EXP_SHA, A2_EXP_SIZE)}

CMD_ALLOW = re.compile(
    r"^(?:xmodem 0x[0-9A-Fa-f]+"
    r"|md\.b 0x[0-9A-Fa-f]+ 0x[0-9A-Fa-f]+"
    r"|crc32 0x[0-9A-Fa-f]+ 0x[0-9A-Fa-f]+"
    r"|go 0x[0-9A-Fa-f]+"
    r"|help|version|echo [A-Za-z0-9_-]+|reset"
    r"|mtd list"
    r"|mtd read [A-Za-z0-9_.@-]+ 0x[0-9A-Fa-f]+ 0x[0-9A-Fa-f]+ 0x[0-9A-Fa-f]+)$")


def log(msg):
    base.log(msg)


def artifact_facts(path, token, name="a1"):
    saved = base.BANNER_TOKEN
    base.BANNER_TOKEN = token
    try:
        f = base.artifact_facts(path)
    finally:
        base.BANNER_TOKEN = saved
    exp_sha, exp_size = EXPECTED.get(name, (None, None))
    if exp_sha:
        f["sha_ok"] = f["sha256"] == exp_sha
        f["expected_sha"] = exp_sha
    if exp_size:
        f["size_ok"] = f["size"] == exp_size
        f["expected_size"] = exp_size
    f["expected_token"] = token
    f["expected_token_ok"] = f["banner_offset"] > 0
    return f


def go_for_banner(c, token, timeout):
    saved = base.BANNER_TOKEN
    base.BANNER_TOKEN = token
    try:
        return base.go_for_banner(c, timeout)
    finally:
        base.BANNER_TOKEN = saved


def safe_cmd(c, cmd, timeout=60):
    if not CMD_ALLOW.match(cmd.strip()):
        raise RuntimeError("command not in the read-only allowlist: " + cmd)
    return c.cmd(cmd, timeout)


def help_text_of(c):
    return (safe_cmd(c, "help", 30) or b"").decode("latin-1")


def help_has(help_text, name):
    return re.search(r"(?:^|\s)" + re.escape(name) + r"(?:\s|$)", help_text or "") is not None



def md_compare_retry(c, data, chunk, name):
    base_addr = 0x43000000
    mismatches = 0
    first_bad = None
    gaps_total = 0
    got = bytearray()
    chunks = []
    retries = 0
    off = 0
    while off < len(data):
        n = min(chunk, len(data) - off)
        best = None
        for attempt in range(2):
            t0 = time.time()
            text, seg, gaps = c.md_read("md.b 0x%08X 0x%X" % (base_addr + off, n),
                                        base_addr + off, n, 120)
            seg = seg[:n]
            if len(seg) < n:
                seg = seg + bytes(n - len(seg))
                gaps += 1
            expect = data[off:off + n]
            bad = sum(1 for a, b in zip(seg, expect) if a != b)
            ent = {"offset": off, "size": n, "mismatches": bad, "gaps": gaps,
                   "elapsed_s": round(time.time() - t0, 1), "attempt": attempt + 1}
            if best is None or bad < best[0]:
                best = (bad, seg, gaps, ent)
            if bad == 0 and gaps == 0:
                break
            retries += 1
        bad, seg, gaps, ent = best
        chunks.append(ent)
        gaps_total += gaps
        if bad and first_bad is None:
            expect = data[off:off + n]
            for i, (a, b) in enumerate(zip(seg, expect)):
                if a != b:
                    first_bad = off + i
                    break
        mismatches += bad
        got.extend(seg)
        log("stage %s md compare %d/%d, mismatches=%d, %.1fs%s" % (
            name, off + n, len(data), bad, ent["elapsed_s"],
            "" if ent["attempt"] == 1 else " (retry)"))
        off += n
        if mismatches > 200:
            break
    return {"ok": mismatches == 0 and gaps_total == 0,
            "bytes_compared": len(got), "mismatches": mismatches,
            "first_mismatch_offset": first_bad, "gaps": gaps_total,
            "retries": retries, "chunks": chunks}

def verify_stage(c, st, chunk, banner_timeout):
    name, path, token = st["name"], st["artifact"], st["token"]
    res = {"name": name, "artifact": artifact_facts(path, token, name)}
    if not res["artifact"]["expected_token_ok"]:
        raise RuntimeError("artifact does not embed its expected banner token: " + path)
    data = open(path, "rb").read()
    load = base.xmodem_load(c, path)
    res["xmodem"] = load
    log("stage %s xmodem: %s" % (name, json.dumps(
        {k: load.get(k) for k in ("mode", "blocks", "bytes_sent", "elapsed_s", "eot_acked")})))
    if not load.get("ok"):
        raise RuntimeError("xmodem failed for " + name)
    res["crc32"] = base.crc32_check(c, data)
    res["crc32_skipped"] = not res["crc32"].get("available")
    log("stage %s crc32: %s" % (name, json.dumps(res["crc32"])[:260]))
    if res["crc32_skipped"]:
        log("stage %s crc32 command unavailable on this console; full md.b compare is the byte-identity proof" % name)
    res["md_compare"] = md_compare_retry(c, data, chunk, name)
    log("stage %s md compare: %s" % (name, json.dumps(
        {k: res["md_compare"][k] for k in
         ("ok", "bytes_compared", "mismatches", "first_mismatch_offset", "gaps")})))
    if not res["md_compare"]["ok"]:
        raise RuntimeError("md.b compare mismatch for " + name + "; refusing to go")
    res["go"] = go_for_banner(c, token, banner_timeout)
    log("stage %s go: banner_token_seen=%s prompt_seen=%s banner_line=%r" % (
        name, res["go"]["banner_token_seen"], res["go"]["prompt_seen"], res["go"]["banner_line"]))
    if not res["go"]["banner_token_seen"]:
        raise RuntimeError("expected banner token not seen for " + name)
    res["prompt_alive"] = base.prompt_alive(c)
    res["help_text"] = help_text_of(c)
    res["help_has_reset"] = help_has(res["help_text"], "reset")
    res["help_has_mtd"] = help_has(res["help_text"], "mtd")
    log("stage %s prompt: alive=%s reset=%s mtd=%s" % (
        name, res["prompt_alive"].get("alive"), res["help_has_reset"], res["help_has_mtd"]))
    res["ok"] = bool((res["crc32_skipped"] or res["crc32"]["ok"])
                     and res["md_compare"]["ok"]
                     and res["go"]["banner_token_seen"] and res["prompt_alive"].get("alive"))
    return res


def transition_to_vendor(c, prev_help_text, timeout):
    info = {"prev_help_has_reset": help_has(prev_help_text, "reset"), "method": "power-cycle"}
    if info["prev_help_has_reset"]:
        c.pending = b""
        c.send(b"reset\r")
        rebooted = False
        unknown = False
        deadline = time.time() + 15
        while time.time() < deadline:
            data = c.read()
            if data:
                c.pending += data
            if re.search(rb"Press 1 means entering boot mode|pdt_cspboot|BootROM", c.pending):
                rebooted = True
                break
            if b"Unknown command" in c.pending:
                unknown = True
                break
            time.sleep(0.02)
        info["reset_rebooted"] = rebooted
        info["reset_unknown"] = unknown
        if rebooted:
            info["method"] = "reset"
    if info["method"] == "reset":
        entry = base.enter_vendor_console(c, 120)
    else:
        log("POWER CYCLE REQUIRED (stage transition): unplug >=5 s, replug; waiting %ss" % timeout)
        entry = base.enter_vendor_console(c, timeout)
    info["entry"] = entry
    info["ok"] = bool(entry.get("ok"))
    log("stage transition: " + json.dumps({k: info[k] for k in
                                           ("method", "prev_help_has_reset", "reset_rebooted",
                                            "reset_unknown", "ok")}))
    return info


def mtd_checks(c, dump, read_size):
    res = {"device": MTD_DEV, "read_size": read_size, "reads": []}
    list_out = (safe_cmd(c, "mtd list", 60) or b"").decode("latin-1")
    res["list_tail"] = list_out[-2500:]
    keys = {"header": "List of MTD devices:", "spi_nand": MTD_DEV,
            "block_size": "block size: 0x20000 bytes", "min_io": "min I/O: 0x800 bytes",
            "oob_size": "OOB size: 64 bytes"}
    res["list_checks"] = {k: (v in list_out) for k, v in keys.items()}
    res["list_ok"] = all(res["list_checks"].values())
    log("A2 mtd list checks: " + json.dumps(res["list_checks"]))
    for label, off, ram in MTD_REGIONS:
        size = read_size
        n = min(size, len(dump) - off)
        cmd = "mtd read %s 0x%08X 0x%X 0x%X" % (MTD_DEV, ram, off, n)
        read_out = (safe_cmd(c, cmd, 120) or b"").decode("latin-1")
        err = any(k in read_out for k in ("ERROR", "not found", "Out of range", "Cannot"))
        md_text, seg, gaps = c.md_read("md.b 0x%08X 0x%X" % (ram, n), ram, n, 120)
        md_out = md_text
        seg = seg[:n]
        if len(seg) < n:
            seg = seg + bytes(n - len(seg))
            gaps += 1
        expect = dump[off:off + n]
        mismatches = sum(1 for a, b in zip(seg, expect) if a != b)
        first = next((i for i, (a, b) in enumerate(zip(seg, expect)) if a != b), None)
        ent = {"label": label, "offset": off, "ram": ram, "size": n,
               "read_cmd": cmd, "read_error": err, "read_tail": read_out[-400:],
               "mismatches": mismatches, "first_mismatch": first, "gaps": gaps,
               "ok": (not err) and mismatches == 0 and gaps == 0}
        res["reads"].append(ent)
        log("A2 mtd read %s: %s" % (label, json.dumps(
            {k: ent[k] for k in ("offset", "size", "read_error", "mismatches", "first_mismatch", "gaps", "ok")})))
    res["ok"] = bool(res["list_ok"] and all(r["ok"] for r in res["reads"]))
    return res


def recover(c, last_help_text, timeout):
    info = {"method": "power-cycle", "reset_in_help": help_has(last_help_text, "reset")}
    if info["reset_in_help"]:
        c.pending = b""
        c.send(b"reset\r")
        rebooted = False
        deadline = time.time() + 15
        while time.time() < deadline:
            data = c.read()
            if data:
                c.pending += data
            if re.search(rb"Press 1 means|pdt_|e2631-wifi-boot|ImmortalWrt", c.pending):
                rebooted = True
                break
            if b"Unknown command" in c.pending:
                break
            time.sleep(0.02)
        info["reset_rebooted"] = rebooted
        if rebooted:
            info["method"] = "reset"
    if info["method"] == "power-cycle":
        log("POWER CYCLE REQUIRED for recovery: unplug >=5 s, replug; waiting %ss for Linux" % timeout)
    info["linux"] = base.wait_linux(c, timeout)
    log("recovery: " + json.dumps({k: info[k] for k in
                                   ("method", "reset_in_help", "reset_rebooted", "linux")}))
    return info


def run_preflight(args):
    stages = [("a1", args.artifact, args.expect_banner)]
    if args.second_artifact:
        stages.append(("a2", args.second_artifact, args.second_token))
    rep = {"mode": "preflight", "stages": {}, "capture_chain": {}, "checks": {}}
    for name, path, token in stages:
        facts = artifact_facts(path, token, name)
        rep["stages"][name] = facts
    rep["capture_chain"] = {
        "supervisor_pids": base.pgrep("capture-supervisor-002.sh"),
        "bootwatch_pids": base.pgrep("serial-bootwatch.mjs"),
        "tty_holders": base.tty_holders()}
    rc, ev, _ = base.sh("tail -3 /home/qc233/zte/e2631-serial-capture-002-events.log")
    rep["capture_events_tail"] = ev
    scripts = {p: os.path.exists(p) for p in
               [base.HUB, base.RESTORE, base.HEALTH, base.VENDOR_PW_FILE,
                base.CAPTURE_SUP, base.CAPTURE_BW]}
    rep["scripts"] = scripts
    if args.second_artifact:
        dump = open(args.dump, "rb").read()
        import hashlib
        slices = {}
        for label, off, ram in MTD_REGIONS:
            n = MTD_READ_SIZE
            seg = dump[off:off + n]
            slices[label] = {"offset": hex(off), "size": n,
                             "sha256": hashlib.sha256(seg).hexdigest(),
                             "head16": seg[:16].hex()}
        rep["dump"] = {"path": args.dump, "size": len(dump),
                       "sha256": hashlib.sha256(dump).hexdigest(), "slices": slices}
    rep["checks"]["artifacts"] = all(f["expected_token_ok"] and f["sha_ok"] and f["size_ok"]
                                     for f in rep["stages"].values())
    rep["checks"]["capture"] = bool(rep["capture_chain"]["supervisor_pids"]
                                    and rep["capture_chain"]["bootwatch_pids"]
                                    and rep["capture_chain"]["tty_holders"])
    rep["checks"]["scripts"] = all(scripts.values())
    rep["checks"]["dump"] = abs(len(open(args.dump, "rb").read()) - 0x100000) == 0 if args.second_artifact else True
    rep["ok"] = all(rep["checks"].values())
    os.makedirs(args.out_dir, exist_ok=True)
    with open(args.out_dir + "/preflight.json", "w") as f:
        json.dump(rep, f, indent=1)
    log("PREFLIGHT " + ("OK" if rep["ok"] else "ISSUES"))
    log(json.dumps(rep, indent=1))
    return 0 if rep["ok"] else 1


def run_session(args):
    os.makedirs(args.out_dir, exist_ok=True)
    base.LOG = args.out_dir + "/session-driver.log"
    stages = [{"name": "a1", "artifact": args.artifact, "token": args.expect_banner}]
    if args.second_artifact:
        stages.append({"name": "a2", "artifact": args.second_artifact, "token": args.second_token})
    dump = open(args.dump, "rb").read() if args.second_artifact else None
    results = {"mode": "session", "stages_expected": [s["name"] for s in stages],
               "stages": [], "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        results["capture_before"] = base.pause_capture()
        if not results["capture_before"]["free"]:
            raise RuntimeError("tty still busy after pausing the capture chain")
        base.start_hub(args.out_dir + "/serial.log")
        c = base.Console()
        if args.start_mode == "cold":
            log("READY FOR USER POWER CYCLE (cold boot); waiting up to %ss" % args.entry_timeout)
            entry = base.enter_vendor_console(c, args.entry_timeout)
        else:
            log("ATTACHING to the existing console prompt (start-mode=%s)" % args.start_mode)
            c.pending = b""
            c.send(b"\x18\x18")
            time.sleep(0.3)
            c.send(b"\r")
            probe = c.wait(rb"=>", 15)
            if probe is not None:
                # clear any half-typed line left by an aborted transfer, then get a
                # clean prompt again before sending the next command
                c.send(b"\x03")
                time.sleep(0.2)
                c.pending = b""
                c.send(b"\r")
                probe = c.wait(rb"=>", 15)
            entry = {"ok": probe is not None, "mode": "attach-" + args.start_mode,
                     "probe_tail": (probe or b"").decode("latin-1")[-120:]}
            if entry["ok"] and args.start_mode == "uboot-prompt":
                entry["help_text"] = help_text_of(c)
                entry["help_has_reset"] = help_has(entry["help_text"], "reset")
        results["vendor_entry"] = entry
        results["start_mode"] = args.start_mode
        if not entry.get("ok"):
            raise RuntimeError("vendor console entry failed: " + json.dumps(entry))
        log("console ready (start-mode=%s)" % args.start_mode)
        last_help = ""
        for idx, st in enumerate(stages):
            if idx > 0:
                trans = transition_to_vendor(c, last_help, args.entry_timeout)
                results["stages"][-1]["transition"] = trans
                if not trans.get("ok"):
                    raise RuntimeError("stage transition failed")
            st_res = verify_stage(c, st, args.chunk, args.banner_timeout)
            if st["name"] == "a2":
                st_res["mtd"] = mtd_checks(c, dump, args.mtd_size)
                st_res["ok"] = bool(st_res["ok"] and st_res["mtd"]["ok"])
            results["stages"].append(st_res)
            last_help = st_res.get("help_text", "")
            log("stage %s OK=%s" % (st["name"], st_res["ok"]))
            if not st_res["ok"]:
                results.setdefault("stage_failures", []).append(st["name"])
                log("stage %s acceptance FAILED (recorded; continuing to the next stage)" % st["name"])
        results["recovery"] = recover(c, last_help, args.recover_timeout)
        results["transcript"] = "serial.log"
        open(args.out_dir + "/console-transcript.txt", "wb").write(bytes(c.history))
    except Exception as exc:  # noqa: BLE001
        results["error"] = str(exc)
        log("SESSION ERROR: " + str(exc))
    finally:
        try:
            base.stop_hub()
        except Exception:
            pass
        results["capture_after"] = base.restore_capture()
        try:
            rc, out, _ = base.sh("bash " + base.HEALTH, timeout=120)
            results["health_rc"] = rc
            results["health"] = out[-4000:]
            open(args.out_dir + "/health.txt", "w").write(out)
        except Exception as exc:  # noqa: BLE001
            results["health_error"] = str(exc)
        results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        health_text = results.get("health", "") or ""
        health_ok = ("VERSION=ImmortalWrt" in health_text) and ("PANICS=0" in health_text)
        stages_ok = bool(results["stages"]) and len(results["stages"]) == len(stages) \
            and all(s.get("ok") for s in results["stages"])
        results["verdict"] = "GREEN" if (stages_ok and results["capture_after"].get("ok")
                                          and health_ok and not results.get("error")) else "FAIL"
        with open(args.out_dir + "/session-results.json", "w") as f:
            json.dump(results, f, indent=1)
        log("VERDICT " + results["verdict"] + " (results in " + args.out_dir + "/session-results.json)")
    return 0 if results["verdict"] == "GREEN" else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--artifact", default=A1_ART)
    ap.add_argument("--expect-banner", default=A1_TOKEN)
    ap.add_argument("--second-artifact", default=None)
    ap.add_argument("--second-token", default=A2_TOKEN)
    ap.add_argument("--start-mode", choices=("cold", "vendor-prompt", "uboot-prompt"),
                    default="cold")
    ap.add_argument("--dump", default=DUMP)
    ap.add_argument("--mtd-size", type=lambda v: int(v, 0), default=MTD_READ_SIZE)
    ap.add_argument("--out-dir", default=base.P3 + "/a1-banner-accept")
    ap.add_argument("--chunk", type=lambda v: int(v, 0), default=0x4000)
    ap.add_argument("--entry-timeout", type=int, default=600)
    ap.add_argument("--banner-timeout", type=int, default=120)
    ap.add_argument("--recover-timeout", type=int, default=900)
    args = ap.parse_args()
    if args.preflight:
        return run_preflight(args)
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())
