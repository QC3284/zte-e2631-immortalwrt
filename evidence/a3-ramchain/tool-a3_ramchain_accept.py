#!/usr/bin/env python3
"""A3 RAM-chain read-only acceptance session driver (P2 A3 slot-aware boot).

Session shape (every console command is checked against a positive allowlist):
  pause capture -> serial hub -> user cold power-on -> vendor console ->
  xmodem 0x43000000 of the A3 u-boot.bin -> crc32 (vendor console: absent) +
  full md.b byte compare -> go 0x43000000 -> A3 banner -> abort autoboot
  (A3 bootcmd is e2631boot) -> prompt alive -> help/printenv checks ->
  e2631boot info (slot scan + decision, no boot) -> e2631boot load only if info
  is clean (uImage verify + load to 0x42000000, no jump) -> mtd list + read-only
  mtd reads compared against reference slices captured from the running Linux
  (read-only SSH dd) -> reset (expect no-op) -> user power cycle -> Linux ->
  capture chain restore -> health -> verdict.

Read-only by construction: no mtd write/erase, no nand write/erase, no saveenv
(compiled out), no bare e2631boot (hence no bootm) unless --boot-test is given.
"""
import argparse, hashlib, json, os, re, signal, subprocess, sys, time

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import a1_banner_accept as base
import a1a2_banner_accept as combo

A3_ART = ("/home/qc233/zte/e2631-t5-artifacts/uboot-a3-44880033207/"
          "e2631-uboot-44880033207/u-boot.bin")
A3_ART_DIR = os.path.dirname(A3_ART)
A3_TOKEN = "U-Boot 2027.01-rc2-g8a9d1f7eecfa"
A3_SHA = "4128523cfc5376e103a89b848fed0d8519004cb0330aa0ca188d548ae562f19d"
A3_SIZE = 448072
A3_BANNER_OFFSET = 380790
A3_RUN = "44880033207"
TREE_PIN = "40f52fb46d9987d8082babac151f9f8dcbdcba4a"
KIT = "/home/qc233/zte/e2631-immortalwrt"
KIT_COMMITS = KIT + "/uboot-port/commits.env"
REF_DIR = base.P3 + "/a3-ref"
REF_JSON = REF_DIR + "/refs.json"
DEV_PW = "/home/qc233/zte/e2631-device-password.txt"
ASKPASS = "/tmp/e2631-askpass-a3.sh"
MTD_DEV = "spi-nand0"
READ = 0x800
NL = chr(10)
MTD_REGIONS = [
    ("slot1-version-header", "/dev/mtd6", 0x1500000, 0x3800000, 0x4C000000),
    ("slot1-uimage-header", "/dev/mtd6", 0x0, 0x2300000, 0x4C001000),
    ("slot0-vendor-header", "/dev/mtd5", 0x1560000, 0x1C60000, 0x4C002000),
    ("u-boot-env-page", "/dev/mtd0", 0xC0000, 0xC0000, 0x4C003000),
]

CMD_ALLOW = re.compile(
    r"^(?:xmodem 0x[0-9A-Fa-f]+"
    r"|md[.]b 0x[0-9A-Fa-f]+ 0x[0-9A-Fa-f]+"
    r"|crc32 0x[0-9A-Fa-f]+ 0x[0-9A-Fa-f]+"
    r"|go 0x43000000"
    r"|help|version|printenv|echo [A-Za-z0-9_-]+|reset"
    r"|mtd list"
    r"|mtd read [A-Za-z0-9_.@-]+ 0x[0-9A-Fa-f]+ 0x[0-9A-Fa-f]+ 0x[0-9A-Fa-f]+"
    r"|e2631boot info|e2631boot load)$")
FORBIDDEN_SAMPLES = [
    "mtd write spi-nand0 0x4C000000 0x0 0x800",
    "mtd erase spi-nand0",
    "mtd bad spi-nand0 0x20000",
    "nand write 0x4C000000 0x20000 0x800",
    "nand erase 0x20000 0x20000",
    "saveenv", "env save", "env set bootcmd foo", "setenv foo bar", "editenv foo",
    "e2631boot", "e2631boot boot", "bootm 0x42000000", "boot", "run bootcmd",
]


def log(msg):
    base.log(msg)


def safe_cmd(c, cmd, timeout=60):
    if not CMD_ALLOW.match(cmd.strip()):
        raise RuntimeError("command not in the read-only allowlist: " + cmd)
    return c.cmd(cmd, timeout)


def help_has(text, name):
    return combo.help_has(text, name)


def a3_artifact_facts():
    saved = (base.BANNER_TOKEN, base.EXP_SHA, base.EXP_SIZE)
    base.BANNER_TOKEN, base.EXP_SHA, base.EXP_SIZE = A3_TOKEN, A3_SHA, A3_SIZE
    try:
        f = base.artifact_facts(A3_ART)
    finally:
        base.BANNER_TOKEN, base.EXP_SHA, base.EXP_SIZE = saved
    f["banner_offset_expected"] = A3_BANNER_OFFSET
    f["banner_offset_ok"] = f["banner_offset"] == A3_BANNER_OFFSET
    f["tree_pin"] = TREE_PIN
    f["ok"] = bool(f["sha_ok"] and f["size_ok"] and f["banner_offset_ok"])
    return f


def read_kv_file(path, prefix):
    try:
        for line in open(path):
            line = line.strip()
            if line.startswith(prefix):
                return line[len(prefix):]
    except OSError:
        return None
    return None


def uboot_info_checks():
    rep = {"artifact_dir": A3_ART_DIR}
    info_tree = read_kv_file(A3_ART_DIR + "/UBOOT-INFO.txt", "Post-am tree: ")
    rep["info_tree"] = info_tree
    rep["info_tree_ok"] = info_tree == TREE_PIN
    try:
        txt = open(A3_ART_DIR + "/UBOOT-INFO.txt").read()
    except OSError:
        txt = ""
    rep["info_hw_untested"] = "Hardware tested: NO" in txt
    rep["info_run_ok"] = ("/actions/runs/" + A3_RUN) in txt
    kit_pin = read_kv_file(KIT_COMMITS, "E2631_UBOOT_TREE_SHA=")
    rep["kit_tree_pin"] = kit_pin
    rep["kit_tree_ok"] = kit_pin == TREE_PIN
    payload = read_kv_file(KIT_COMMITS, "E2631_UBOOT_PAYLOAD_MAX=")
    rep["payload_max"] = payload
    rep["size_under_limit"] = bool(payload and A3_SIZE <= int(payload, 16))
    rep["ok"] = bool(rep["info_tree_ok"] and rep["kit_tree_ok"]
                     and rep["size_under_limit"] and rep["info_run_ok"])
    return rep


def sha256sums_check():
    rep = {"file": A3_ART_DIR + "/SHA256SUMS"}
    want = None
    try:
        for line in open(rep["file"]):
            parts = line.split()
            if len(parts) == 2 and parts[1] == "u-boot.bin":
                want = parts[0]
    except OSError as exc:
        rep["error"] = str(exc)
    got = a3_artifact_facts()["sha256"]
    rep["want"] = want
    rep["got"] = got
    rep["ok"] = want == got
    return rep


def route_check():
    rc, out, _ = base.sh("ip route get 192.168.1.1 | head -1")
    return {"raw": out, "direct": "via " not in out, "ok": "via " not in out}


def make_askpass():
    if os.path.exists(DEV_PW):
        with open(ASKPASS, "w") as f:
            f.write("#!/bin/sh" + NL + "cat " + DEV_PW + NL)
        os.chmod(ASKPASS, 0o700)
    return os.path.exists(ASKPASS)


def ssh_run(remote, timeout=120):
    env = dict(os.environ)
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    cmd = ["setsid", "-w", "ssh", "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10",
           "root@192.168.1.1", remote]
    try:
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def fetch_refs():
    """Capture the four reference slices from the running Linux (read-only dd)."""
    rep = {"source": "ssh-live-linux", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "slices": {}, "ok": False}
    snippet = """echo SLICE %s
raw=$(dd if=%s bs=2048 skip=%d count=1 2>/dev/null | od -An -v -tx1 | tr -d '[:space:]')
if [ $(echo -n "$raw" | wc -c) -ne %d ]; then
raw=$(dd if=%s bs=2048 skip=%d count=1 2>/dev/null | hexdump -v -e '1/1 "%%02x"')
fi
echo "$raw"
"""
    remote = ""
    for label, dev, poff, coff, ram in MTD_REGIONS:
        skip = poff // 2048
        remote += snippet % (label, dev, skip, READ * 2, dev, skip)
    rc, out, err = ssh_run(remote, 180)
    rep["ssh_rc"] = rc
    rep["ssh_err_tail"] = err[-300:]
    lines = out.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("SLICE "):
            label = line[6:]
            hexstr = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if len(hexstr) == READ * 2:
                try:
                    raw = bytes.fromhex(hexstr)
                except ValueError:
                    raw = b""
                if raw:
                    ent = next((x for x in MTD_REGIONS if x[0] == label), None)
                    if ent:
                        rep["slices"][label] = {
                            "partition": ent[1], "partition_offset": hex(ent[2]),
                            "chip_offset": hex(ent[3]), "size": READ,
                            "sha256": hashlib.sha256(raw).hexdigest(),
                            "hex": hexstr}
            i += 2
            continue
        i += 1
    rep["ok"] = len(rep["slices"]) == len(MTD_REGIONS)
    try:
        dump = open(combo.DUMP, "rb").read()
        seg = dump[0xC0000:0xC0000 + READ]
        rep["dump_env_slice_sha256"] = hashlib.sha256(seg).hexdigest()
        rep["dump_env_slice_match"] = (rep["slices"].get("u-boot-env-page", {}).get("sha256")
                                       == rep["dump_env_slice_sha256"])
    except OSError as exc:
        rep["dump_error"] = str(exc)
    os.makedirs(REF_DIR, exist_ok=True)
    with open(REF_JSON, "w") as f:
        json.dump(rep, f, indent=1)
    log("ref slices ok=" + str(rep["ok"]) + " " + json.dumps(
        {k: v["sha256"] for k, v in rep["slices"].items()}))
    return rep


def load_refs():
    try:
        return json.load(open(REF_JSON))
    except OSError:
        return {"ok": False}


def note_boot_lines(c):
    text = c.pending.decode("latin-1")
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("e2631boot: ") and s not in out:
            out.append(s)
    return out


def go_for_banner_a3(c, timeout=45):
    tok = A3_TOKEN.encode()
    c.pending = b""
    c.send(b"go 0x43000000\r")
    acc = bytearray()
    token_seen = False
    prompt_seen = False
    aborts = 0
    last_abort = 0.0
    boot_lines = []
    t0 = time.time()
    while time.time() - t0 < timeout:
        data = c.read()
        if data:
            acc += data
            c.pending += data
        if not token_seen and tok in bytes(acc):
            token_seen = True
            log("A3 banner token seen after %.1fs" % (time.time() - t0))
            c.send(b" ")
            aborts = 1
            last_abort = time.time()
        if token_seen and not prompt_seen:
            for s in note_boot_lines(c):
                if s not in boot_lines:
                    boot_lines.append(s)
            if b"=>" in c.pending:
                prompt_seen = True
                break
            if aborts < 12 and time.time() - last_abort > 0.25:
                c.send(b" ")
                aborts += 1
                last_abort = time.time()
        time.sleep(0.02)
    c.wait_until_quiet(0.4, 8)
    text = acc.decode("latin-1")
    res = {"banner_token_seen": token_seen, "prompt_seen": prompt_seen,
           "abort_keys_sent": aborts, "autoboot_started": bool(boot_lines),
           "e2631boot_lines": boot_lines[:12],
           "env_hang_suspect": not token_seen,
           "elapsed_s": round(time.time() - t0, 1),
           "banner_line": next((l for l in text.splitlines() if A3_TOKEN in l), None),
           "raw_tail": text[-5000:]}
    log("A3 go: banner=%s prompt=%s aborts=%s autoboot_started=%s" % (
        token_seen, prompt_seen, aborts, bool(boot_lines)))
    return res


def prompt_alive_a3(c):
    results = {}
    c.pending = b""
    c.send(b"\r")
    results["bare_cr_prompt"] = bool(c.wait(b"=>", 20))
    for cmd in ["help", "version", "echo E2631-A3-PROMPT-OK", "crc32 0x43000000 0x100"]:
        out = safe_cmd(c, cmd, 30)
        text = (out or b"").decode("latin-1")
        results[cmd] = {"ok": bool(out), "unknown": "Unknown command" in text,
                        "tail": text[-500:]}
    results["alive"] = bool(results["bare_cr_prompt"]
                            and (results["help"]["ok"]
                                 or results["echo E2631-A3-PROMPT-OK"]["ok"]))
    return results


def help_checks(c):
    text = (safe_cmd(c, "help", 30) or b"").decode("latin-1")
    res = {"saveenv_absent": "saveenv" not in text,
           "mtd_present": help_has(text, "mtd"),
           "e2631boot_present": "e2631boot" in text,
           "reset_present": help_has(text, "reset"),
           "raw_tail": text[-1200:]}
    res["ok"] = bool(res["saveenv_absent"] and res["mtd_present"])
    return res


def env_checks(c):
    text = (safe_cmd(c, "printenv", 30) or b"").decode("latin-1")
    res = {"bootcmd_runtime": "e2631boot" if "bootcmd=e2631boot" in text else None,
           "baudrate": "115200" if "baudrate=115200" in text else None,
           "bootdelay": "3" if "bootdelay=3" in text else None,
           "vendor_env_present": ("ethaddr=00:41:71:00:00:50" in text),
           "raw_tail": text[-1500:]}
    res["ok"] = bool(res["bootcmd_runtime"] and res["baudrate"]
                     and res["vendor_env_present"])
    return res


def parse_info_text(text):
    res = {"raw_tail": text[-3000:]}
    slots = {}
    decision = None
    boot_marker = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("e2631boot: slot") and ": serial " in s:
            try:
                head, rest = s.split(": serial ", 1)
                slotnum = int(head.split()[1][4:])
                part = int(head.split(" at ")[1], 16)
                serial_s, rest2 = rest.split(", version ", 1)
                version, rest3 = rest2[1:].split('", header ', 1)
                header = int(rest3, 16)
                slots["slot%d" % slotnum] = {"part_offset": part,
                                             "serial": int(serial_s),
                                             "version": version,
                                             "header": header}
            except (ValueError, IndexError):
                pass
        elif s.startswith("e2631boot: cspboot would boot slot"):
            try:
                decision = int(s.rsplit("slot", 1)[1])
            except (ValueError, IndexError):
                pass
        elif ("Starting kernel" in s) or ("Booting kernel" in s):
            boot_marker = True
    res.update(slots)
    res["decision"] = decision
    s0, s1 = slots.get("slot0"), slots.get("slot1")
    res["asserts"] = {
        "slot0_line": bool(s0), "slot1_line": bool(s1),
        "slot0_part_0x700000": bool(s0 and s0["part_offset"] == 0x700000),
        "slot1_part_0x2300000": bool(s1 and s1["part_offset"] == 0x2300000),
        "slot0_header_0x1C60000": bool(s0 and s0["header"] == 0x1C60000),
        "slot1_header_0x3800000": bool(s1 and s1["header"] == 0x3800000),
        "slot0_serial_7": bool(s0 and s0["serial"] == 7),
        "slot0_version_vendor": bool(s0 and "V1.0.0.7B5.8000" in s0["version"]),
        "slot1_version_immortalwrt": bool(s1 and "ImmortalWrt" in s1["version"]),
        "slot1_serial_gt_slot0": bool(s0 and s1 and s1["serial"] > s0["serial"]),
        "decision_slot1": decision == 1,
        "no_boot_marker": not boot_marker,
    }
    res["ok"] = all(res["asserts"].values())
    return res


def parse_load_text(text):
    res = {"raw_tail": text[-3000:]}
    crcs = "e2631boot: header and data CRCs are good" in text
    boot_marker = ("Starting kernel" in text) or ("Booting kernel" in text)
    line = None
    for cand in text.splitlines():
        s = cand.strip()
        if s.startswith('e2631boot: uImage "') and ": load " in s:
            line = s
            break
    try:
        rest = line.split('e2631boot: uImage "', 1)[1]
        name, rest = rest.split('": load ', 1)
        load_s, rest = rest.split(" entry ", 1)
        entry_s, rest = rest.split(", ", 1)
        size_s, rest = rest.split(" bytes at ", 1)
        dest = int(rest, 16)
        res.update({"name": name, "load": int(load_s, 16),
                    "entry": int(entry_s, 16), "size": int(size_s), "dest": dest})
    except (IndexError, ValueError, AttributeError):
        pass
    res["crcs_good"] = crcs
    res["no_boot_marker"] = not boot_marker
    res["asserts"] = {
        "uimage_line": "name" in res,
        "name_immortalwrt": bool("name" in res and "ImmortalWrt" in res["name"]),
        "load_0x40008000": bool(res.get("load") == 0x40008000),
        "entry_0x40008000": bool(res.get("entry") == 0x40008000),
        "dest_0x42000000": bool(res.get("dest") == 0x42000000),
        "size_plausible": bool(res.get("size") and 3000000 <= res["size"] <= 4000000),
        "crcs_good": crcs,
        "no_boot_marker": not boot_marker,
    }
    res["ok"] = all(res["asserts"].values())
    return res


def e2631boot_info(c):
    t0 = time.time()
    out = safe_cmd(c, "e2631boot info", 120)
    elapsed = round(time.time() - t0, 2)
    text = (out or b"").decode("latin-1")
    res = parse_info_text(text)
    res["elapsed_s"] = elapsed
    res["asserts"]["scan_under_3s"] = elapsed < 3.0
    res["ok"] = all(res["asserts"].values())
    log("e2631boot info elapsed=" + str(elapsed) + "s " + json.dumps(res["asserts"]))
    return res


def e2631boot_load(c):
    t0 = time.time()
    out = safe_cmd(c, "e2631boot load", 180)
    elapsed = round(time.time() - t0, 2)
    text = (out or b"").decode("latin-1")
    res = parse_load_text(text)
    res["elapsed_s"] = elapsed
    log("e2631boot load elapsed=" + str(elapsed) + "s " + json.dumps(res["asserts"]))
    return res


def a3_mtd_checks(c, refs):
    res = {"device": MTD_DEV, "read_size": READ, "reads": []}
    list_out = (safe_cmd(c, "mtd list", 60) or b"").decode("latin-1")
    res["list_tail"] = list_out[-2500:]
    keys = {"header": "List of MTD devices:", "spi_nand": MTD_DEV,
            "block_size": "block size: 0x20000 bytes", "min_io": "min I/O: 0x800 bytes",
            "oob_size": "OOB size: 64 bytes"}
    res["list_checks"] = {k: (v in list_out) for k, v in keys.items()}
    res["list_ok"] = all(res["list_checks"].values())
    log("A3 mtd list checks: " + json.dumps(res["list_checks"]))
    for label, dev, poff, coff, ram in MTD_REGIONS:
        ref = refs.get("slices", {}).get(label)
        cmd = "mtd read %s 0x%08X 0x%X 0x%X" % (MTD_DEV, ram, coff, READ)
        read_out = (safe_cmd(c, cmd, 120) or b"").decode("latin-1")
        err = any(k in read_out for k in ("ERROR", "not found", "Out of range", "Cannot"))
        md_text, seg, gaps = c.md_read("md.b 0x%08X 0x%X" % (ram, READ), ram, READ, 120)
        seg = seg[:READ]
        if len(seg) < READ:
            seg = seg + bytes(READ - len(seg))
            gaps += 1
        ent = {"label": label, "chip_offset": hex(coff), "ram": hex(ram), "size": READ,
               "read_cmd": cmd, "read_error": err, "read_tail": read_out[-300:],
               "gaps": gaps, "ref_sha256": (ref or {}).get("sha256")}
        if ref:
            want = bytes.fromhex(ref["hex"])
            mismatches = sum(1 for a, b in zip(seg, want) if a != b)
            first = next((i for i, (a, b) in enumerate(zip(seg, want)) if a != b), None)
            ent.update({"mismatches": mismatches, "first_mismatch": first,
                        "sha256": hashlib.sha256(seg).hexdigest()})
            ent["ok"] = (not err) and mismatches == 0 and gaps == 0
        else:
            ent.update({"mismatches": None, "first_mismatch": None, "ok": False})
        res["reads"].append(ent)
        log("A3 mtd read " + label + ": " + json.dumps({k: ent[k] for k in
            ("chip_offset", "read_error", "mismatches", "first_mismatch", "gaps", "ok")}))
    res["ok"] = bool(res["list_ok"] and all(r["ok"] for r in res["reads"]))
    return res


def recover_a3(c, help_text, timeout, boot_test=False):
    info = {"reset_in_help": help_has(help_text, "reset"), "boot_test": boot_test}
    if boot_test:
        log("BOOT TEST: bare e2631boot (read-only bootm of the winning slot)")
        c.pending = b""
        c.send(b"e2631boot\r")
        lin = base.wait_linux(c, timeout)
        info.update({"method": "e2631boot", "linux": lin})
        if lin.get("ok"):
            return info
        log("boot test did not reach Linux; falling back to a power cycle")
    if info["reset_in_help"]:
        c.pending = b""
        c.send(b"reset\r")
        rebooted = False
        unknown = False
        deadline = time.time() + 15
        while time.time() < deadline:
            data = c.read()
            if data:
                c.pending += data
            pend = bytes(c.pending)
            if (b"Press 1 means" in pend) or (b"pdt_" in pend) or (
                    b"e2631-wifi-boot" in pend) or (b"ImmortalWrt" in pend):
                rebooted = True
                break
            if b"Unknown command" in pend:
                unknown = True
                break
            time.sleep(0.02)
        info["reset_rebooted"] = rebooted
        info["reset_unknown"] = unknown
        if rebooted:
            info["method"] = "reset"
    if info.get("method") != "reset":
        log("POWER CYCLE REQUIRED for recovery: unplug >=5 s, replug; waiting %ss for Linux" % timeout)
        info["method"] = "power-cycle"
    info["linux"] = base.wait_linux(c, timeout)
    return info


def selftest():
    rep = {"artifact": a3_artifact_facts(), "uboot_info": uboot_info_checks(),
           "sha256sums": sha256sums_check(), "route": route_check()}
    ok_pos = ["xmodem 0x43000000", "md.b 0x43000000 0x4000",
              "crc32 0x43000000 0x6D648", "go 0x43000000", "help", "version",
              "printenv", "echo E2631-A3-PROMPT-OK", "reset", "mtd list",
              "mtd read spi-nand0 0x4C000000 0x3800000 0x800",
              "e2631boot info", "e2631boot load"]
    rep["allow_ok"] = all(bool(CMD_ALLOW.match(c)) for c in ok_pos)
    rep["forbid_ok"] = all(not CMD_ALLOW.match(c) for c in FORBIDDEN_SAMPLES)
    info_sample = NL.join([
        'e2631boot: slot0 at 0x00700000: serial 7, version "V1.0.0.7B5.8000", header 0x01c60000',
        'e2631boot: slot1 at 0x02300000: serial 12, version "ImmortalWrt v1.10.0", header 0x03800000',
        "e2631boot: cspboot would boot slot1",
        "=> "])
    load_sample = NL.join([
        'e2631boot: uImage "ARM ImmortalWrt Linux-6.18.60": load 0x40008000 entry 0x40008000, 3491850 bytes at 0x42000000',
        "e2631boot: header and data CRCs are good",
        "=> "])
    rep["parser_info"] = parse_info_text(info_sample)
    rep["parser_load"] = parse_load_text(load_sample)
    rep["parser_ok"] = bool(rep["parser_info"]["ok"] and rep["parser_load"]["ok"])
    rep["ok"] = bool(rep["artifact"]["ok"] and rep["uboot_info"].get("ok")
                     and rep["sha256sums"].get("ok") and rep["route"].get("ok")
                     and rep["allow_ok"] and rep["forbid_ok"] and rep["parser_ok"])
    os.makedirs(base.P3 + "/a3-ramchain", exist_ok=True)
    with open(base.P3 + "/a3-ramchain/selftest.json", "w") as f:
        json.dump(rep, f, indent=1)
    print("SELFTEST " + ("OK" if rep["ok"] else "FAIL"))
    print(json.dumps({k: rep[k] for k in ("allow_ok", "forbid_ok", "parser_ok")}))
    print(json.dumps({k: rep["artifact"].get(k) for k in
                      ("size", "sha256", "banner_offset", "banner_offset_ok", "ok")}))
    print(json.dumps(rep["uboot_info"]))
    return 0 if rep["ok"] else 1


def run_preflight(args):
    rep = {"mode": "preflight", "artifact": a3_artifact_facts(),
           "uboot_info": uboot_info_checks(), "sha256sums": sha256sums_check(),
           "route": route_check()}
    rep["capture_chain"] = {"supervisor_pids": base.pgrep("capture-supervisor-002.sh"),
                            "bootwatch_pids": base.pgrep("serial-bootwatch.mjs"),
                            "tty_holders": base.tty_holders()}
    rc, tail, _ = base.sh("tail -3 /home/qc233/zte/e2631-serial-capture-002-events.log")
    rep["capture_events_tail"] = tail
    scripts = {p: os.path.exists(p) for p in
               [base.HUB, base.RESTORE, base.HEALTH, base.VENDOR_PW_FILE,
                base.CAPTURE_SUP, base.CAPTURE_BW]}
    rep["scripts"] = scripts
    rep["vendor_pw_mode"] = oct(os.stat(base.VENDOR_PW_FILE).st_mode & 0o777) \
        if os.path.exists(base.VENDOR_PW_FILE) else None
    make_askpass()
    rep["refs"] = fetch_refs()
    dump_ok = False
    try:
        dump = open(combo.DUMP, "rb").read()
        dump_ok = bool(len(dump) == 0x100000 and
                       hashlib.sha256(dump).hexdigest() ==
                       "de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f")
    except OSError:
        pass
    rep["dump_ok"] = dump_ok
    rep["checks"] = {
        "artifact": rep["artifact"]["ok"],
        "uboot_info": bool(rep["uboot_info"].get("ok")),
        "sha256sums": bool(rep["sha256sums"].get("ok")),
        "route_direct": bool(rep["route"].get("ok")),
        "capture": bool(rep["capture_chain"]["supervisor_pids"]
                        and rep["capture_chain"]["bootwatch_pids"]
                        and rep["capture_chain"]["tty_holders"]),
        "scripts": all(scripts.values()),
        "vendor_pw": rep["vendor_pw_mode"] == "0o600",
        "refs": bool(rep["refs"].get("ok")),
        "dump": dump_ok,
    }
    rep["ok"] = all(rep["checks"].values())
    os.makedirs(args.out_dir, exist_ok=True)
    with open(args.out_dir + "/preflight.json", "w") as f:
        json.dump(rep, f, indent=1)
    log("PREFLIGHT " + ("OK" if rep["ok"] else "ISSUES"))
    log(json.dumps(rep["checks"]))
    if not rep["ok"]:
        log(json.dumps(rep, indent=1)[-3500:])
    return 0 if rep["ok"] else 1


def ensure_direct_link():
    rc, out, _ = base.sh("ip route get 192.168.1.1 | head -1")
    if "via " not in out:
        return {"ok": True, "action": "none", "raw": out}
    log("ROUTE TRAP: 192.168.1.1 is not direct; reconnecting the USB NIC")
    base.sh("nmcli device connect enp0s20u1u4u2c2")
    last = out
    for _ in range(15):
        time.sleep(2)
        rc, out, _ = base.sh("ip route get 192.168.1.1 | head -1")
        last = out
        if "via " not in out:
            return {"ok": True, "action": "nmcli-connect-enp0s20u1u4u2c2", "raw": out}
    return {"ok": False, "action": "failed", "raw": last}


def attach_console(c, mode):
    c.pending = b""
    c.send(b"\x18\x18")
    time.sleep(0.3)
    c.send(b"\r")
    probe = c.wait(b"=>", 15)
    if probe is not None:
        c.send(b"\x03")
        time.sleep(0.2)
        c.pending = b""
        c.send(b"\r")
        probe = c.wait(b"=>", 15)
    entry = {"ok": probe is not None, "mode": "attach-" + mode,
             "tail": (probe or b"").decode("latin-1")[-160:]}
    if entry["ok"]:
        out = safe_cmd(c, "version", 20)
        entry["version_tail"] = (out or b"").decode("latin-1")[-300:]
    return entry


def run_session(args):
    os.makedirs(args.out_dir, exist_ok=True)
    base.LOG = args.out_dir + "/session-driver.log"
    data = open(A3_ART, "rb").read()
    results = {"mode": "session", "artifact": a3_artifact_facts(),
               "expected_banner_token": A3_TOKEN,
               "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        if not results["artifact"]["ok"]:
            raise RuntimeError("A3 artifact facts failed: " +
                               json.dumps(results["artifact"])[:400])
        refs = load_refs()
        results["refs"] = {"ok": refs.get("ok"), "source": refs.get("source"),
                           "slices": {k: v.get("sha256") for k, v in
                                      refs.get("slices", {}).items()}}
        if not refs.get("ok"):
            raise RuntimeError("no reference slices; run --preflight first")
        results["capture_before"] = base.pause_capture()
        if not results["capture_before"]["free"]:
            raise RuntimeError("tty still busy after pausing the capture chain")
        results["hub_pid"] = base.start_hub(args.out_dir + "/serial.log")
        c = base.Console()
        if args.start_mode == "cold":
            log("READY FOR USER POWER CYCLE (cold boot); waiting up to %ss" % args.entry_timeout)
            entry = base.enter_vendor_console(c, args.entry_timeout)
        else:
            log("ATTACHING to an existing console prompt (start-mode=%s)" % args.start_mode)
            entry = attach_console(c, args.start_mode)
        results["vendor_entry"] = entry
        if not entry.get("ok"):
            raise RuntimeError("console entry failed: " + json.dumps(entry))
        log("console entered (start-mode=%s)" % args.start_mode)
        load = base.xmodem_load(c, A3_ART)
        results["xmodem"] = load
        log("A3 xmodem: " + json.dumps({k: load.get(k) for k in
            ("mode", "blocks", "bytes_sent", "elapsed_s", "eot_acked")}))
        if not load.get("ok"):
            raise RuntimeError("xmodem failed: " + json.dumps(load)[:400])
        results["crc32"] = base.crc32_check(c, data)
        results["crc32_skipped"] = not results["crc32"].get("available")
        log("A3 crc32: " + json.dumps(results["crc32"])[:220])
        results["md_compare"] = combo.md_compare_retry(c, data, args.chunk, "a3")
        log("A3 loaded: " + json.dumps({k: results["md_compare"][k] for k in
            ("ok", "bytes_compared", "mismatches", "first_mismatch_offset", "gaps")}))
        if not results["md_compare"]["ok"]:
            raise RuntimeError("md.b compare mismatch; refusing to go")
        go = go_for_banner_a3(c, args.banner_timeout)
        results["go"] = go
        if go["env_hang_suspect"]:
            results["env_hang_suspect"] = True
            log("NO A3 BANNER after go: possible env-load hang before prompt (initr_env); "
                "serial tail captured in the log, not retrying")
            log("POWER CYCLE REQUIRED for recovery: unplug >=5 s, replug; waiting %ss for Linux"
                % args.recover_timeout)
            results["recovery"] = {"method": "power-cycle-after-env-hang",
                                   "linux": base.wait_linux(c, args.recover_timeout)}
        elif not go["prompt_seen"]:
            log("A3 banner seen but no prompt (autoboot may have started); waiting for Linux")
            results["recovery"] = {"method": "autoboot",
                                   "linux": base.wait_linux(c, args.recover_timeout)}
        else:
            log("A3 banner: " + str(go["banner_line"]))
            results["prompt_alive"] = prompt_alive_a3(c)
            results["help_checks"] = help_checks(c)
            results["env"] = env_checks(c)
            info = e2631boot_info(c)
            results["e2631boot_info"] = info
            if info["ok"]:
                log("e2631boot info clean: cspboot would boot slot" + str(info.get("decision")))
                results["e2631boot_load"] = e2631boot_load(c)
            else:
                log("e2631boot info NOT clean; skipping e2631boot load")
            results["mtd"] = a3_mtd_checks(c, refs)
            results["recovery"] = recover_a3(c, results["help_checks"]["raw_tail"],
                                             args.recover_timeout, args.boot_test)
            log("recovery: " + json.dumps({k: results["recovery"].get(k) for k in
                ("method", "reset_rebooted", "linux")}))
        results["transcript"] = "serial.log"
        open(args.out_dir + "/console-transcript.txt", "wb").write(bytes(c.history))
    except Exception as exc:
        results["error"] = str(exc)
        log("SESSION ERROR: " + str(exc))
    finally:
        try:
            base.stop_hub()
        except Exception:
            pass
        results["capture_after"] = base.restore_capture()
        results["route_fix"] = ensure_direct_link()
        try:
            rc, out, _ = base.sh("bash " + base.HEALTH, timeout=180)
            results["health_rc"] = rc
            results["health"] = out[-4000:]
            open(args.out_dir + "/health.txt", "w").write(out)
        except Exception as exc:
            results["health_error"] = str(exc)
        results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        health_text = results.get("health", "") or ""
        health_ok = ("VERSION=ImmortalWrt" in health_text) and ("PANICS=0" in health_text)
        needed = ["prompt_alive", "help_checks", "env", "e2631boot_info",
                  "e2631boot_load", "mtd"]
        if all(results.get(k) for k in needed):
            stages_ok = bool(results["prompt_alive"].get("alive")
                             and results["help_checks"].get("ok")
                             and results["env"].get("ok")
                             and results["e2631boot_info"].get("ok")
                             and results["e2631boot_load"].get("ok")
                             and results["mtd"].get("ok"))
        else:
            stages_ok = False
        go_ok = bool(results.get("go", {}).get("banner_token_seen")
                     and results.get("go", {}).get("prompt_seen"))
        results["verdict"] = ("GREEN" if
                              results["artifact"]["ok"]
                              and results.get("xmodem", {}).get("eot_acked")
                              and results.get("md_compare", {}).get("ok")
                              and go_ok and stages_ok
                              and results["capture_after"].get("ok")
                              and health_ok and not results.get("error")
                              else "FAIL")
        with open(args.out_dir + "/session-results.json", "w") as f:
            json.dump(results, f, indent=1)
        log("VERDICT " + results["verdict"] + " (results in " +
            args.out_dir + "/session-results.json)")
    return 0 if results["verdict"] == "GREEN" else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--start-mode", choices=("cold", "vendor-prompt", "uboot-prompt"),
                    default="cold")
    ap.add_argument("--out-dir", default=base.P3 + "/a3-ramchain")
    ap.add_argument("--chunk", type=lambda v: int(v, 0), default=0x4000)
    ap.add_argument("--entry-timeout", type=int, default=600)
    ap.add_argument("--banner-timeout", type=int, default=45)
    ap.add_argument("--recover-timeout", type=int, default=900)
    ap.add_argument("--boot-test", action="store_true",
                    help="on recovery, try the bare e2631boot (bootm) before a power cycle")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.preflight:
        return run_preflight(args)
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())
