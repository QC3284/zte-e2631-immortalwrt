#!/usr/bin/env python3
"""A6: RAM-chain acceptance of patch 0013 (the two late PCIe reset lines).

Cold boot or reboot -f -> OUR flash U-Boot -> loadx the patch-0013 u-boot.bin
-> md.b verify -> go 0x47F00000 -> new prompt -> GPIO gate (pin 2 / pin 51
high) -> e2631boot -> kernel -> console probes for eth / PCIe 14c3:7906 +
14c3:790a / MT7916.

Default is a SINGLE execution of the refclk sequence (inside e2631boot) to
drop the double-execution variable seen in A5 run-3; --with-refclk restores
the explicit e2631refclk + post-dump path. No flash write at any time.
"""
import json, os, re, sys, time

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import c1b1fix_sessionA as sa
import c1b1_final as fin
import a1_banner_accept as base

P3 = "/home/qc233/zte/e2631-p3"
LOAD_ADDR = 0x47F00000
OLD_BANNER = sa.OLD_BANNER
UBOOT_PROMPT = re.compile(rb"\r?\n=>[ \t]*")
SHELL_PROMPT = re.compile(rb"root@ImmortalWrt:[^#\r\n]*#")
SERDES_MD = "md 0x9fe00000 24"
REFCLK_CMD = "e2631refclk"

# Patch-0013 v3 artifact contract (run 44935007253, kit tip 24e52c6; mdelay(4) gap).
EXPECT_ARTIFACT_SHA = "3bf182f148226b6f64696a05bba5d75ca59426747f87eee3f13c5d2b0269423a"
EXPECT_ARTIFACT_SIZE = 450936
EXPECT_BANNER = "U-Boot 2027.01-rc2-g85c7367a3106"
GPIO_PIN2_REG = 0x94407014
GPIO_PIN2_BIT = 2
GPIO_PIN51_REG = 0x944070D4
GPIO_PIN51_BIT = 3
EXPECT_GPIO_VALUES = {"pin2": 0x0000DB2C, "pin51": 0x0000E028}

# Phase-A (true cold) fingerprints taken at our flash prompt on 2026-11-22.
# Lead ruling: --start-mode reboot is valid only when all six match; a mismatch
# means the reboot did not reach the cold register state and A5 must not run.
COLD_FINGERPRINT = {
    "0x94000008": 0x10061FCF,
    "0x9400004c": 0x00038000,
    "0x94000050": 0x80040FAA,
    "0x94000054": 0x00353F7D,
    "0x94100010": 0x00000000,
    "0x9a100004": 0x0000081B,
}

# Patch-0012 artifact contract (run 44929440623, banner token g9a7538311376).
PRE_DUMP_CMDS = [
    "md 0x94000000 0x40",
    "md 0x94100000 0x10",
    "md 0x94200000 0x10",
    "md 0x94400000 0x10",
    "md 0x94407000 0x40",
    "md 0x9a100000 0x10",
    "md 0x9a101000 0x8",
]

EXPECT_AFTER = {
    "PLL0": (0x0004176B,),
    "PLL1": (0x044FDF3B, 0x144FDF3B),
    "CTRL8": (0x10061FFF,),
    "CRM2_10": (0x00000100,),
    "CTRL4C": (0x000381FF,),
    "LSP1_04": (0x0001381B,),
}

# Vendor post-init SerDes table measured on 2026-11-22 (phase B, 24 words).
VENDOR_SERDES = {
    0x00: 0x800010A7, 0x04: 0x0000000F, 0x08: 0x00000540, 0x0C: 0x00000004,
    0x10: 0x00000000, 0x14: 0x018A6400, 0x18: 0x08B50140, 0x1C: 0x01216000,
    0x20: 0x40000000, 0x24: 0x0B570001, 0x28: 0x00000000, 0x2C: 0x00000000,
    0x30: 0x20242000, 0x34: 0xC0593D44, 0x38: 0x0000042F, 0x3C: 0x00000000,
    0x40: 0x003C0040, 0x44: 0xEAC0A013, 0x48: 0x101038CA, 0x4C: 0x0005A000,
    0x50: 0x33333333, 0x54: 0x33333333, 0x58: 0x03E23333, 0x5C: 0x00040244,
}

PROBES_EARLY = [
    ("uptime", "cut -d. -f1 /proc/uptime"),
    ("netdev", "ip -br link"),
    ("sysnet", "ls /sys/class/net"),
    ("eth_speeds", "for n in lan1 lan2 lan3 wan; do printf '%s ' $n; cat /sys/class/net/$n/speed 2>/dev/null || echo NA; done"),
    ("eth_operstate", "for n in lan1 lan2 lan3 wan; do echo $n $(cat /sys/class/net/$n/operstate 2>/dev/null); done"),
    ("pci_ids", "for d in /sys/bus/pci/devices/*; do v=$(cat $d/vendor 2>/dev/null); p=$(cat $d/device 2>/dev/null); echo $(basename $d) $v:$p; done"),
    ("dmesg_eth", "dmesg | grep -iE 'zx279128s-eth|mdio|PHY connect|ENODEV' | tail -20"),
    ("dmesg_pci", "dmesg | grep -iE 'pcie|14c3|mt7915' | tail -20"),
    ("clk_ref", "grep -E 'pll_lsp|mdio_wclk' /sys/kernel/debug/clk/clk_summary 2>/dev/null | head -4"),
]
PROBES_LATE = [
    ("uptime2", "cut -d. -f1 /proc/uptime"),
    ("netdev2", "ip -br link"),
    ("eth_speeds2", "for n in lan1 lan2 lan3 wan; do printf '%s ' $n; cat /sys/class/net/$n/speed 2>/dev/null || echo NA; done"),
    ("pci_ids2", "for d in /sys/bus/pci/devices/*; do v=$(cat $d/vendor 2>/dev/null); p=$(cat $d/device 2>/dev/null); echo $(basename $d) $v:$p; done"),
    ("wifi", "dmesg | grep -iE 'e2631-wifi-boot|MT7916|mt7915e.*firmware' | tail -12"),
    ("clk_ref2", "grep -E 'pll_lsp|mdio_wclk' /sys/kernel/debug/clk/clk_summary 2>/dev/null | head -4"),
]

LOG = None


def log(msg):
    line = time.strftime("%H:%M:%S") + " " + str(msg)
    print(line, flush=True)
    if LOG:
        with open(LOG, "a") as f:
            f.write(line + "\n")


def clean(obj):
    if isinstance(obj, bytes):
        return obj.decode("latin-1", "replace")
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def sha_file(path):
    import hashlib
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def artifact_token(path):
    data = open(path, "rb").read()
    m = re.search(rb"U-Boot 2027\.01-rc2-g[0-9a-f]+", data)
    return m.group(0) if m else None


def hub_pids():
    import subprocess
    try:
        out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid, args = parts
        if "serialhub.py" in args and "python3" in args and "ps -eo" not in args:
            try:
                pids.append(int(pid))
            except ValueError:
                pass
    return pids


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    art = args.uboot
    token = artifact_token(art) if os.path.exists(art) else None
    chain = {"supervisor_pids": base.pgrep("capture-supervisor-002.sh"),
             "bootwatch_pids": base.pgrep("serial-bootwatch.mjs"),
             "tty_holders": base.tty_holders()}
    rep = {"artifact": {"path": art, "exists": os.path.exists(art),
                        "size": os.path.getsize(art) if os.path.exists(art) else None,
                        "sha256": sha_file(art) if os.path.exists(art) else None,
                        "token": token.decode() if token else None},
           "chain": chain,
           "serialhub": hub_pids(),
           "socket_exists": os.path.exists(base.SOCK),
           "vendor_pw_mode": oct(os.stat(base.VENDOR_PW_FILE).st_mode & 0o777)
                             if os.path.exists(base.VENDOR_PW_FILE) else None}
    rep["ok"] = bool(rep["artifact"]["exists"] and rep["artifact"]["token"]
                     and chain["supervisor_pids"] and chain["bootwatch_pids"]
                     and chain["tty_holders"] and not rep["serialhub"]
                     and not rep["socket_exists"] and rep["vendor_pw_mode"] == "0o600")
    return rep


def wait_for(c, pattern, timeout, acc):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = c.read()
        if data:
            c.pending += data
            acc.extend(data)
            if pattern.search(bytes(acc)):
                return True
        else:
            time.sleep(0.05)
    return False


def uboot_cmd(c, cmd, timeout=60):
    c.pending = bytes()
    c.send(cmd.encode() + b"\r")
    buf = bytearray()
    ok = wait_for(c, UBOOT_PROMPT, timeout, buf)
    return {"cmd": cmd, "ok": ok, "out": bytes(buf).decode("latin-1", "replace")}


def shell_cmd(c, cmd, timeout=45):
    c.pending = bytes()
    c.send(cmd.encode() + b"\r")
    buf = bytearray()
    ok = wait_for(c, SHELL_PROMPT, timeout, buf)
    return {"cmd": cmd, "ok": ok, "out": bytes(buf).decode("latin-1", "replace")}


def wake_shell(c, timeout=240):
    deadline = time.time() + timeout
    acc = bytearray()
    while time.time() < deadline:
        c.pending = bytes()
        c.send(b"\r")
        sub = time.time() + 6
        while time.time() < sub:
            data = c.read()
            if data:
                c.pending += data
                acc.extend(data)
            else:
                time.sleep(0.05)
            if SHELL_PROMPT.search(bytes(acc[-4000:])):
                return True
    return False


def parse_md_words(text):
    words = {}
    for line in text.splitlines():
        m = re.match(r"^([0-9a-fA-F]{8}):((?:\s+[0-9a-fA-F]{8})+)", line)
        if m:
            addr = int(m.group(1), 16)
            for i, w in enumerate(m.group(2).split()):
                words["0x%08x" % (addr + i * 4)] = int(w, 16)
    return words


def cold_fingerprint_gate(c, results, enforce):
    found = {}
    raw = {}
    for reg in COLD_FINGERPRINT:
        r = uboot_cmd(c, "md.l " + reg + " 1", 30)
        raw[reg] = r["out"]
        found.update(parse_md_words(r["out"]))
    observed = {reg: found.get(reg) for reg in COLD_FINGERPRINT}
    mismatches = {reg: {"expected": COLD_FINGERPRINT[reg], "observed": observed[reg]}
                  for reg in COLD_FINGERPRINT if observed[reg] != COLD_FINGERPRINT[reg]}
    results["cold_fingerprint"] = {"expected": COLD_FINGERPRINT, "observed": observed,
                                  "mismatches": mismatches, "raw": raw, "ok": not mismatches}
    log("COLD FINGERPRINT " + ("MATCH" if not mismatches else "MISMATCH " + json.dumps(mismatches)))
    if mismatches and enforce:
        raise RuntimeError("cold-state fingerprint mismatch; physical power cycle required: " + json.dumps(mismatches))
    return not mismatches


def a6_gpio_gate(c, results, enforce=True):
    checks = {}
    for name, addr, bit, cmd in (
            ("pin2", GPIO_PIN2_REG, GPIO_PIN2_BIT, "md.l 0x94407014 1"),
            ("pin51", GPIO_PIN51_REG, GPIO_PIN51_BIT, "md.l 0x944070d4 1")):
        r = uboot_cmd(c, cmd, 30)
        results.setdefault("gpio_gate", {})[name] = r
        words = parse_md_words(r["out"])
        val = words.get("0x%08x" % addr)
        ok = val is not None and bool(val & (1 << bit))
        checks[name] = {"cmd": cmd, "reg": "0x%08x" % addr, "bit": bit,
                        "value": ("0x%08x" % val) if val is not None else None,
                        "ok": ok, "raw": r["out"]}
        log("A6 GPIO %s -> %s (bit%d must be 1; vendor target %08x)"
            % (name, checks[name]["value"], bit, EXPECT_GPIO_VALUES[name]))
    for name, want in EXPECT_GPIO_VALUES.items():
        got = checks[name]["value"]
        checks[name]["vendor_target"] = "0x%08x" % want
        checks[name]["matches_vendor"] = got == "0x%08x" % want
    results["gpio_gate_checks"] = checks
    results["gpio_gate_ok"] = all(v["ok"] for v in checks.values())
    if enforce and not results["gpio_gate_ok"]:
        raise RuntimeError("patch-0013 GPIO gate failed: pin 2 bit2 / pin 51 bit3 not both high")
    return results["gpio_gate_ok"]


def parse_refclk(text):
    out = {"before": {}, "after": {}}
    for m in re.finditer(r"e2631refclk:\s+(before|after)\s+PLL0=([0-9a-fA-F]{8})\s+PLL1=([0-9a-fA-F]{8})\s+CTRL8=([0-9a-fA-F]{8})", text):
        out[m.group(1)].update({"PLL0": int(m.group(2), 16), "PLL1": int(m.group(3), 16),
                               "CTRL8": int(m.group(4), 16)})
    for m in re.finditer(r"e2631refclk:\s+(before|after)\s+CRM2_10=([0-9a-fA-F]{8})\s+CTRL4C=([0-9a-fA-F]{8})\s+LSP1_04=([0-9a-fA-F]{8})(?:\s+CTRL0C=([0-9a-fA-F]{8}))?", text):
        out[m.group(1)].update({"CRM2_10": int(m.group(2), 16), "CTRL4C": int(m.group(3), 16),
                               "LSP1_04": int(m.group(4), 16),
                               "CTRL0C": int(m.group(5), 16) if m.group(5) else None})
    return out


def refclk_checks(parsed):
    after = parsed.get("after") or {}
    before = parsed.get("before") or {}
    checks = {}
    for name in ("PLL0", "PLL1", "CTRL8", "CRM2_10", "CTRL4C", "LSP1_04"):
        checks[name] = after.get(name) in EXPECT_AFTER[name]
    ctrl0c = after.get("CTRL0C")
    checks["CTRL0C"] = (ctrl0c & 0x00FF0000) == 0x00510000 if isinstance(ctrl0c, int) else False
    checks["before_pre"] = (before.get("PLL0") == 0x80040FAA and before.get("PLL1") == 0x00353F7D
                            and before.get("CTRL8") == 0x10061FCF and before.get("CRM2_10") == 0
                            and before.get("CTRL4C") == 0x00038000 and before.get("LSP1_04") == 0x0000081B)
    return checks


def pre_dump(c, results):
    words = {}
    cmds = []
    for cmd in PRE_DUMP_CMDS:
        r = uboot_cmd(c, cmd, 30)
        cmds.append(r)
        words.update(parse_md_words(r["out"]))
    results["pre_dump"] = {"commands": cmds, "words": dict(words)}
    log("PRE DUMP words=%d" % len(words))
    return words


def post_dump_and_verify(c, results, pre_words, parsed):
    words = {}
    cmds = []
    for cmd in PRE_DUMP_CMDS:
        r = uboot_cmd(c, cmd, 30)
        cmds.append(r)
        words.update(parse_md_words(r["out"]))
    diffs = []
    for addr in sorted(set(pre_words) | set(words)):
        if pre_words.get(addr) != words.get(addr):
            diffs.append({"reg": addr, "pre": pre_words.get(addr), "post": words.get(addr)})
    key = {"0x94000050": "PLL0", "0x94000054": "PLL1", "0x94000008": "CTRL8",
           "0x94100010": "CRM2_10", "0x9400004c": "CTRL4C", "0x9a100004": "LSP1_04",
           "0x9400000c": "CTRL0C"}
    key_checks = {}
    for addr, name in key.items():
        v = words.get(addr)
        if name == "CTRL0C":
            key_checks[name] = (v & 0x00FF0000) == 0x00510000 if isinstance(v, int) else False
        else:
            key_checks[name] = v in EXPECT_AFTER[name]
    results["post_dump"] = {"commands": cmds, "words": dict(words),
                            "diffs": diffs, "key_checks": key_checks}
    serdes = uboot_cmd(c, SERDES_MD, 60)
    if not serdes["ok"] or "9fe00000:" not in serdes["out"]:
        raise RuntimeError("SerDes read-back after e2631refclk failed")
    sw = parse_md_words(serdes["out"])
    cmp = []
    for off, want in VENDOR_SERDES.items():
        got = sw.get("0x%08x" % (0x9FE00000 + off))
        cmp.append({"off": off, "expected": want, "observed": got, "match": got == want})
    matches = sum(1 for e in cmp if e["match"])
    results["serdes_readback"] = {"raw": serdes["out"], "compare": cmp,
                                  "matches": matches, "total": len(cmp), "ok": matches >= 20}
    if matches < 20:
        raise RuntimeError("SerDes read-back only %d/%d words match the vendor table" % (matches, len(cmp)))
    return results


def run_session(args):
    global LOG
    os.makedirs(args.out_dir, exist_ok=True)
    LOG = args.out_dir + "/session-driver.log"
    pre = preflight(args)
    results = {"mode": "a6-pcie-ram", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "preflight": pre, "commands": []}
    if not pre["ok"]:
        results["error"] = "preflight failed"
        results["verdict"] = "FAIL"
        json.dump(clean(results), open(args.out_dir + "/session-results.json", "w"), indent=1)
        log("VERDICT FAIL (preflight)")
        return 2
    token = pre["artifact"]["token"]
    token_b = token.encode()
    if (pre["artifact"]["sha256"] != EXPECT_ARTIFACT_SHA
            or pre["artifact"]["size"] != EXPECT_ARTIFACT_SIZE
            or token_b != EXPECT_BANNER.encode()):
        results["error"] = ("artifact does not match the patch-0013 contract: sha=%s size=%s token=%s"
                            % (pre["artifact"]["sha256"], pre["artifact"]["size"],
                               pre["artifact"]["token"]))
        results["verdict"] = "FAIL"
        json.dump(clean(results), open(args.out_dir + "/session-results.json", "w"), indent=1)
        log("VERDICT FAIL (artifact contract)")
        return 2
    results["artifact_contract"] = {"sha256": pre["artifact"]["sha256"],
                                    "size": pre["artifact"]["size"],
                                    "banner": pre["artifact"]["token"], "ok": True}
    ublob = fin.read_file(args.uboot)
    cap = base.pause_capture()
    hub = base.start_hub(args.out_dir + "/serial.log")
    c = base.Console()
    results["capture_paused"] = cap
    results["hub_pid"] = hub
    try:
        if args.start_mode == "reboot":
            log("WAKE: current Linux shell, then reboot -f into the flash chain")
            if not wake_shell(c):
                raise RuntimeError("no Linux shell to reboot from")
            c.pending = bytes()
            c.send(b"reboot -f\r")
            acc = bytearray()
            if not wait_for(c, re.compile(re.escape(OLD_BANNER.encode())), args.entry_timeout, acc):
                raise RuntimeError("no OUR flash banner")
            results["flash_banner_seen"] = True
            log("MILESTONE: OUR flash banner; stopping autoboot")
            results["stop_autoboot"] = fin.stop_autoboot(c, results, OLD_BANNER, 40)
            if not results["stop_autoboot"].get("prompt"):
                raise RuntimeError("could not stop autoboot")
        elif args.start_mode == "attach":
            log("ATTACH: reusing the OUR flash U-Boot prompt left by the previous attempt")
            ver = uboot_cmd(c, "version", 20)
            results["attach"] = {"version": ver, "ok": bool(ver["ok"])}
            if not ver["ok"]:
                raise RuntimeError("no OUR flash U-Boot prompt to attach to")
            results["flash_banner_seen"] = False
            results["stop_autoboot"] = {"banner": False, "prompt": True}
            first = ver["out"].strip().splitlines()[0] if ver["out"].strip() else ""
            log("ATTACH OK: " + first)
        else:
            log("READY FOR USER POWER CYCLE (A6: flash chain -> loadx patch 0013 -> GPIO gate -> e2631boot)")
            results["ready_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            acc = bytearray()
            if not wait_for(c, re.compile(re.escape(OLD_BANNER.encode())), args.entry_timeout, acc):
                raise RuntimeError("no OUR flash banner")
            results["flash_banner_seen"] = True
            log("MILESTONE: OUR flash banner; stopping autoboot")
            results["stop_autoboot"] = fin.stop_autoboot(c, results, OLD_BANNER, 40)
            if not results["stop_autoboot"].get("prompt"):
                raise RuntimeError("could not stop autoboot")
        cold_fingerprint_gate(c, results, enforce=(args.start_mode in ("reboot", "attach")))
        pre_words = pre_dump(c, results)
        lx = fin.xmodem_cmd(c, results, args.uboot, "loadx 0x47f00000\r", 1024)
        results["loadx"] = lx
        if not lx.get("ok"):
            raise RuntimeError("loadx of the patch-0013 U-Boot failed")
        md = fin.md_check(c, results, "a5-uboot-in-ram", LOAD_ADDR, ublob)
        results["md_verify"] = md
        if not md["ok"]:
            raise RuntimeError("md.b verify failed; refusing to go")
        log("MILESTONE: patch-0013 U-Boot in RAM verified")
        c.pending = bytes()
        c.send(b"go 0x47f00000\r")
        results["commands"].append("go 0x47f00000")
        acc = bytearray()
        if not wait_for(c, re.compile(re.escape(token_b)), args.entry_timeout, acc):
            raise RuntimeError("no new U-Boot banner after go")
        log("MILESTONE: new U-Boot banner")
        results["stop_autoboot_new"] = fin.stop_autoboot(c, results, token, 40)
        if not results["stop_autoboot_new"].get("prompt"):
            raise RuntimeError("could not stop the new U-Boot autoboot")
        ver = uboot_cmd(c, "version", 30)
        results["version"] = ver
        results["new_version_ok"] = bool(token in ver["out"])
        log("MILESTONE: new U-Boot prompt, version ok=" + str(results["new_version_ok"]))
        if not results["new_version_ok"]:
            raise RuntimeError("new U-Boot version gate failed")
        if args.with_refclk:
            log("STEP: e2631refclk (explicit)")
            ref = uboot_cmd(c, REFCLK_CMD, 60)
            results["refclk"] = ref
            log("refclk ok=" + str(ref["ok"]) + " tail=" + ref["out"][-400:].replace("\n", " | "))
            if not ref["ok"]:
                raise RuntimeError("e2631refclk did not return to the prompt")
            parsed = parse_refclk(ref["out"])
            results["refclk_values"] = parsed
            checks = refclk_checks(parsed)
            results["refclk_checks"] = checks
            results["refclk_after_ok"] = all(v for k, v in checks.items() if k != "before_pre")
            log("REFCLK AFTER " + json.dumps(clean(parsed["after"])) + " checks=" + json.dumps(checks))
            if not results["refclk_after_ok"]:
                raise RuntimeError("e2631refclk after values do not match the artifact contract")
            log("STEP: post dump of the seven register blocks + " + SERDES_MD)
            post_dump_and_verify(c, results, pre_words, parsed)
            log("POST DUMP diffs=" + str(len(results["post_dump"]["diffs"]))
                + " key_checks=" + json.dumps(results["post_dump"]["key_checks"])
                + " serdes_matches=" + str(results["serdes_readback"]["matches"]) + "/24")
        else:
            log("SKIP: explicit e2631refclk + post-dump (single execution via e2631boot; use --with-refclk)")
        log("STEP: patch-0013 GPIO gate before e2631boot")
        a6_gpio_gate(c, results, enforce=True)
        log("STEP: e2631boot (bootm with the new U-Boot)")
        c.pending = bytes()
        c.send(b"e2631boot\r")
        results["commands"].append("e2631boot")
        watched = sa.monitor_kernel(c, results, args.boot_timeout, args.out_dir, "a6")
        results["kernel"] = watched
        try:
            btxt = open(args.out_dir + "/serial.log", "rb").read()[-300000:].decode("latin-1", "replace")
            bparsed = parse_refclk(btxt)
            results["e2631boot_refclk"] = bparsed
            results["e2631boot_refclk_checks"] = refclk_checks(bparsed)
            log("E2631BOOT REFCLK checks=" + json.dumps(results["e2631boot_refclk_checks"]))
        except Exception as exc:
            results["e2631boot_refclk_error"] = repr(exc)
            log("E2631BOOT REFCLK extraction failed: " + repr(exc))
        if not watched.get("linux_marker") or watched.get("panic"):
            raise RuntimeError("kernel did not come up cleanly: " + json.dumps(watched))
        log("MILESTONE: kernel up; running early console probes")
        if not wake_shell(c):
            raise RuntimeError("no Linux shell after boot")
        time.sleep(args.settle)
        results["probes_early"] = {}
        for name, cmd in PROBES_EARLY:
            results["probes_early"][name] = shell_cmd(c, cmd, 45)
            log("PROBE " + name + " -> " + results["probes_early"][name]["out"].strip()[-220:].replace("\n", " | "))
        eth_ok = False
        speed_deadline = time.time() + 90
        while time.time() < speed_deadline:
            sp = results["probes_early"]["eth_speeds"]["out"]
            if all(n in sp for n in ("lan1", "lan2", "lan3", "wan")) and "1000" in sp:
                eth_ok = True
                break
            time.sleep(5)
            results["probes_early"]["eth_speeds"] = shell_cmd(
                c, "for n in lan1 lan2 lan3 wan; do printf '%s ' $n; cat /sys/class/net/$n/speed 2>/dev/null || echo NA; done", 45)
            log("ETH speed poll -> " + results["probes_early"]["eth_speeds"]["out"].strip()[-200:])
        netdev = results["probes_early"]["netdev"]["out"]
        netdev_ok = all(n in netdev for n in ("lan1", "lan2", "lan3", "wan"))
        pci_txt = (results["probes_early"]["pci_ids"]["out"]
                   + results["probes_early"]["dmesg_pci"]["out"]
                   + results["probes_late"]["pci_ids2"]["out"]
                   + results["probes_late"]["wifi"]["out"])
        pci_7906 = "14c3:7906" in pci_txt
        pci_790a = "14c3:790a" in pci_txt
        results["pci_7906"] = pci_7906
        results["pci_790a"] = pci_790a
        log("PCI endpoints 7906=%s 790a=%s" % (pci_7906, pci_790a))
        log("waiting up to %d s for MT7916 readiness" % args.wifi_wait)
        deadline = time.time() + args.wifi_wait
        wifi_ok = False
        wifi_forward = False
        while time.time() < deadline:
            time.sleep(10)
            probe = shell_cmd(c, "dmesg | grep -iE 'MT7916 ready|MT7916 initialization failed|automatic Wi-Fi initialization complete' | tail -3", 45)
            results.setdefault("wifi_poll", []).append(probe)
            log("WIFI poll -> " + probe["out"].strip()[-180:].replace("\n", " | "))
            if "e2631-wifi-boot: MT7916 ready" in probe["out"]:
                wifi_ok = True
            if "e2631-wifi-boot: automatic Wi-Fi initialization complete" in probe["out"]:
                wifi_forward = True
            if wifi_ok and wifi_forward:
                break
        results["wifi_ready"] = wifi_ok
        results["wifi_forward"] = wifi_forward
        wifi_fail_txt = " ".join(p["out"] for p in results.get("wifi_poll", []))
        results["wifi_init_failed"] = ("MT7916 initialization failed" in wifi_fail_txt
                                       or "previous initialization unfinished" in wifi_fail_txt)
        results["probes_late"] = {}
        for name, cmd in PROBES_LATE:
            results["probes_late"][name] = shell_cmd(c, cmd, 45)
            log("PROBE " + name + " -> " + results["probes_late"][name]["out"].strip()[-220:].replace("\n", " | "))
        result_signatures = {
            "gpio_gate_ok": bool(results.get("gpio_gate_ok")),
            "fingerprint_ok": bool(results.get("cold_fingerprint", {}).get("ok", True)),
            "netdev_ok": netdev_ok,
            "eth_link_1g": eth_ok,
            "pci_7906": pci_7906,
            "pci_790a": pci_790a,
            "wifi_ready": wifi_ok,
            "wifi_forward": wifi_forward,
            "no_wifi_init_failure": not results.get("wifi_init_failed", False),
        }
        if args.with_refclk:
            result_signatures["refclk_after_ok"] = bool(results.get("refclk_after_ok"))
            result_signatures["serdes_readback_ok"] = bool(results.get("serdes_readback", {}).get("ok"))
        results["signatures"] = result_signatures
        core_ok = all(v for k, v in result_signatures.items() if k != "fingerprint_ok")
        if args.start_mode == "reboot" and not result_signatures["fingerprint_ok"]:
            core_ok = False
        results["ok"] = bool(core_ok)
        results["verdict"] = "GREEN" if core_ok else "FAIL"
        log("SIGNATURES " + json.dumps(result_signatures))
    except Exception as exc:
        results["error"] = repr(exc)
        results["verdict"] = "FAIL"
        log("ERROR " + repr(exc))
    finally:
        try:
            base.stop_hub()
        except Exception:
            pass
        try:
            results["capture_after"] = base.restore_capture()
        except Exception as exc:
            results["capture_after"] = {"ok": False, "error": repr(exc)}
        results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        if "verdict" not in results:
            results["verdict"] = "GREEN" if results.get("ok") else "FAIL"
        json.dump(clean(results), open(args.out_dir + "/session-results.json", "w"), indent=1)
        log("VERDICT " + results["verdict"])
    return 0 if results["verdict"] == "GREEN" else 2


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--uboot", required=True, help="patch-0012 u-boot.bin from the CI artifact")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--start-mode", choices=["cold", "reboot", "attach"], default="cold")
    ap.add_argument("--entry-timeout", type=int, default=600)
    ap.add_argument("--boot-timeout", type=int, default=420)
    ap.add_argument("--wifi-wait", type=int, default=240)
    ap.add_argument("--settle", type=int, default=15)
    ap.add_argument("--with-refclk", action="store_true")
    args = ap.parse_args()
    global LOG
    os.makedirs(args.out_dir, exist_ok=True)
    LOG = args.out_dir + "/session-driver.log"
    if args.preflight:
        rep = preflight(args)
        json.dump(clean(rep), open(args.out_dir + "/preflight.json", "w"), indent=1)
        print(json.dumps(clean(rep), indent=1))
        print("preflight ok=", rep["ok"])
        return 0 if rep["ok"] else 2
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())

