#!/usr/bin/env python3
"""B1 vendor-U-Boot env session driver (P2-B1): write ONLY the 4 side vars.

Approved write scope (user, 2026-11-21):
  one saveenv that persists exactly e2631_pocload / e2631_pocgo /
  e2631_netboot / e2631_flashboot; bootcmd, bootargs, memsize, versioninfo,
  bootdelay and every other entry stay byte-identical; nothing else is written.

Session: cold boot -> vendor console -> help precheck (setenv+saveenv must be
present) -> printenv baseline compare (22 entries) -> setenv x4 with per-key
readback -> full printenv compare (26 entries, old 22 byte-identical) ->
saveenv (the single write) -> printenv -> reboot -> normal boot (the vendor
zteboot_do_settings survival test) -> Linux -> read the env block back over
read-only SSH -> byte-compare with the offline prediction -> mtd0 sha256
before/after -> health.

Read-only everywhere else: tftp/go/run/nand/mtddebug/cspnand/upgrade and any
setenv outside the allowlist are refused before transmission.
"""
import argparse, base64, hashlib, json, os, re, subprocess, sys, time, zlib

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import a1_banner_accept as base

KIT = "/home/qc233/zte/e2631-immortalwrt"
P3 = base.P3
SESSION_DIR = P3 + "/b1-env-session"
DUMP = "/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin"
CURRENT_TXT = KIT + "/evidence/b1-env-current-20261121.txt"
DEV_PW = "/home/qc233/zte/e2631-device-password.txt"
ASKPASS = "/tmp/e2631-askpass-b1.sh"
ENV_OFF = 0xC0000
ENV_SIZE = 0x20000
BASELINE_FULL_SHA = "de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f"
BASELINE_ENV_CRC = 0xAFFCEC3E
CURRENT_TXT_SHA = "9f5aa9a93a6ded3055db4699c1c94b3ecdd5605f35a0e4e3840c1d85a8ad8d76"
EXPECTED_ENV_CRC = 0xC41396BA
EXPECTED_ENV_SHA = "00d4177d8d0173b2536848d1e769929832e11a7c0055903e278fe0db88f07d3c"
EXPECTED_FULL_SHA = "f452d4c0f646af9f28177d4acf91ce0f193e38ce57d33f7e02189caffc78c77c"
NEW_VARS = [
    ("e2631_pocload", "tftp 0x43000000 u-boot.bin"),
    ("e2631_pocgo", "go 0x43000000"),
    ("e2631_netboot", "tftp 0x42000000 e2631-netboot.uImage"),
    ("e2631_flashboot", "reset"),
]
NL = chr(10)

SETENV_RE = re.compile(r"^setenv (e2631_pocload|e2631_pocgo|e2631_netboot|e2631_flashboot) (?:tftp 0x43000000 u-boot[.]bin|go 0x43000000|tftp 0x42000000 e2631-netboot[.]uImage|reset)$")
READ_RE = re.compile(r"^(?:help|version|reset|printenv|printenv [A-Za-z0-9_]+|md[.]?b? 0x[0-9A-Fa-f]+ [0-9]+|echo [A-Za-z0-9_.-]+|saveenv)$")
FORBIDDEN = [
    "setenv bootcmd x", "setenv bootargs x", "setenv bootdelay 0",
    "setenv memsize 128M", "setenv versioninfo x", "setenv foo bar",
    "tftp 0x43000000 u-boot.bin", "go 0x43000000", "run e2631_pocload",
    "nand write 0x4C000000 0x20000 0x800", "nand erase 0x20000 0x20000",
    "mtddebug write", "upgrade", "cspnand", "bootm 0x42000000", "boot",
]


def log(msg):
    base.log(msg)


def guard(cmd):
    c = cmd.strip()
    if SETENV_RE.match(c) or READ_RE.match(c):
        return c
    raise RuntimeError("command outside the B1 write/read allowlist: " + c)


def send_checked(c, cmd, timeout=30, expect_prompt=True):
    guard(cmd)
    if expect_prompt:
        out = c.cmd(cmd, timeout)
    else:
        c.pending = b""
        c.send((cmd + "\r").encode())
        out = None
    time.sleep(0.1)
    text = (out or b"").decode("latin-1")
    bad = ("## Error" in text) or ("Unknown command" in text) or ("Can't overwrite" in text)
    if bad:
        raise RuntimeError("console error for [" + cmd + "]: " + text[-300:])
    return text


def parse_env(text):
    entries = {}
    order = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("##") or s.startswith("Environment size"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        if not k or not all(ch.isalnum() or ch == "_" for ch in k):
            continue
        if k not in entries:
            order.append(k)
        entries[k] = v
    return entries, order


def read_expected_txt(path):
    entries = {}
    order = []
    for line in open(path):
        line = line.rstrip(NL)
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        order.append(k)
        entries[k] = v
    return entries, order


def sha256_file(path):
    h = hashlib.sha256()
    h.update(open(path, "rb").read())
    return h.hexdigest()


def make_askpass():
    with open(ASKPASS, "w") as f:
        f.write("#!/bin/sh" + NL + "cat " + DEV_PW + NL)
    os.chmod(ASKPASS, 0o700)


def ssh_run(remote, timeout=180):
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


def ensure_direct_link():
    rc, out, _ = base.sh("ip route get 192.168.1.1 | head -1")
    if "via " not in out:
        return {"ok": True, "action": "none", "raw": out}
    log("ROUTE TRAP: reconnecting the USB NIC")
    base.sh("nmcli device connect enp0s20u1u4u2c2")
    last = out
    for _ in range(15):
        time.sleep(2)
        rc, out, _ = base.sh("ip route get 192.168.1.1 | head -1")
        last = out
        if "via " not in out:
            return {"ok": True, "action": "nmcli-connect-enp0s20u1u4u2c2", "raw": out}
    return {"ok": False, "action": "failed", "raw": last}


def build_target(outdir):
    os.makedirs(outdir, exist_ok=True)
    cur_entries, cur_order = read_expected_txt(CURRENT_TXT)
    lines = [k + "=" + v for k, v in zip(cur_order, [cur_entries[k] for k in cur_order])]
    for k, v in NEW_VARS:
        lines.append(k + "=" + v)
    target_txt = outdir + "/target-env.txt"
    open(target_txt, "w").write(NL.join(lines) + NL)
    block = outdir + "/target-env-block.bin"
    full = outdir + "/target-mtd0.bin"
    cmd = ("cd " + KIT + " && node tools/e2631-env.mjs build --in " + target_txt +
           " --out " + block + " --template " + DUMP + " --full-mtd0 " + full)
    rc, out, err = base.sh(cmd, timeout=120)
    ok = rc == 0 and os.path.exists(block) and os.path.exists(full)
    rep = {"ok": ok, "cmd_rc": rc, "stdout_tail": out[-800:], "stderr_tail": err[-400:],
           "target_txt": target_txt, "block": block, "full": full}
    if ok:
        data = open(block, "rb").read()
        fullb = open(full, "rb").read()
        dump = open(DUMP, "rb").read()
        rep.update({
            "env_crc": int.from_bytes(data[:4], "little"),
            "env_crc_recomputed": zlib.crc32(data[4:]) & 0xFFFFFFFF,
            "env_sha256": hashlib.sha256(data).hexdigest(),
            "full_sha256": hashlib.sha256(fullb).hexdigest(),
            "size": len(data),
            "diff_bytes": sum(1 for a, b in zip(dump, fullb) if a != b),
            "diff_outside_env": sum(1 for i, (a, b) in enumerate(zip(dump, fullb))
                                    if a != b and not (ENV_OFF <= i < ENV_OFF + ENV_SIZE)),
        })
        ent = {}
        for chunk in data[4:].split(b"\x00"):
            if not chunk:
                continue
            k, _, v = chunk.decode("latin-1").partition("=")
            ent[k] = v
        rep["entries"] = ent
        mk, mo = parse_env(open(block, "rb").read().decode("latin-1"))
        rep["target_order"] = mo
    return rep


def selftest():
    rep = {}
    rep["allow_ok"] = all(bool(SETENV_RE.match(x)) or bool(READ_RE.match(x)) for x in [
        "setenv e2631_pocload tftp 0x43000000 u-boot.bin", "setenv e2631_pocgo go 0x43000000",
        "setenv e2631_netboot tftp 0x42000000 e2631-netboot.uImage",
        "setenv e2631_flashboot reset", "printenv bootcmd", "help", "saveenv", "reset",
        "md 0x43000000 8"])
    rep["forbid_ok"] = all(not (SETENV_RE.match(x) or READ_RE.match(x)) for x in FORBIDDEN)
    sample = NL.join([
        "baudrate=115200",
        "bootcmd=setenv bootargs console=$(console)  mem=$(memsize) ;",
        "bootdelay=3",
        "e2631_pocload=tftp 0x43000000 u-boot.bin",
        "Environment size: 460/131068 bytes",
        "=> "])
    ent, order = parse_env(sample)
    rep["parser_ok"] = (ent.get("bootdelay") == "3"
                        and ent.get("e2631_pocload") == "tftp 0x43000000 u-boot.bin"
                        and "Environment size" not in " ".join(ent.keys()))
    rep["prediction_ok"] = True
    os.makedirs(SESSION_DIR, exist_ok=True)
    with open(SESSION_DIR + "/selftest.json", "w") as f:
        json.dump(rep, f, indent=1)
    print("SELFTEST " + ("OK" if all(rep[k] for k in ("allow_ok", "forbid_ok", "parser_ok")) else "FAIL"))
    print(json.dumps(rep))
    return 0 if all(rep[k] for k in ("allow_ok", "forbid_ok", "parser_ok")) else 1


def run_preflight(args):
    outdir = args.out_dir
    rep = {"mode": "preflight", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    make_askpass()
    mk, mo = read_expected_txt(CURRENT_TXT)
    rep["current_txt"] = {"sha256": sha256_file(CURRENT_TXT), "entries": len(mo),
                          "bootdelay": mk.get("bootdelay"), "has_side_vars":
                          [k for k in mk if k.startswith("e2631_")]}
    dump = open(DUMP, "rb").read()
    env_cur = dump[ENV_OFF:ENV_OFF + ENV_SIZE]
    rep["dump"] = {"sha256": hashlib.sha256(dump).hexdigest(), "size": len(dump),
                   "env_crc": int.from_bytes(env_cur[:4], "little")}
    rep["pred"] = build_target(outdir)
    rep["pred"]["expected_crc_ok"] = rep["pred"].get("env_crc") == EXPECTED_ENV_CRC
    rep["pred"]["expected_env_sha_ok"] = rep["pred"].get("env_sha256") == EXPECTED_ENV_SHA
    rep["pred"]["expected_full_sha_ok"] = rep["pred"].get("full_sha256") == EXPECTED_FULL_SHA
    rep["pred"]["entries_ok"] = (len(rep["pred"].get("entries", {})) == 26
                                 and all(rep["pred"]["entries"].get(k) == v for k, v in NEW_VARS)
                                 and all(rep["pred"]["entries"].get(k) == mk[k] for k in mo))
    rep["capture_chain"] = {"supervisor_pids": base.pgrep("capture-supervisor-002.sh"),
                            "bootwatch_pids": base.pgrep("serial-bootwatch.mjs"),
                            "tty_holders": base.tty_holders()}
    rep["route"] = {"raw": base.sh("ip route get 192.168.1.1 | head -1")[1], "direct": False}
    rep["route"]["direct"] = "via " not in rep["route"]["raw"]
    rep["vendor_pw"] = {"exists": os.path.exists(base.VENDOR_PW_FILE),
                        "mode": oct(os.stat(base.VENDOR_PW_FILE).st_mode & 0o777)
                        if os.path.exists(base.VENDOR_PW_FILE) else None}
    rep["scripts"] = {p: os.path.exists(p) for p in
                      [base.HUB, base.RESTORE, base.HEALTH, base.VENDOR_PW_FILE]}
    help_src = base.sh("grep -c saveenv " + KIT + "/docs/救砖手册-2026-11-15.md")[1].strip()
    help_src2 = base.sh("grep -c setenv " + KIT + "/docs/救砖手册-2026-11-15.md")[1].strip()
    rep["vendor_help_evidence"] = {"saveenv_mentions": help_src, "setenv_mentions": help_src2,
                                   "note": "design doc section 2.4: 43-command list includes setenv and saveenv; in-session help assert before any setenv"}
    rep["checks"] = {
        "current_txt_sha": rep["current_txt"]["sha256"] == CURRENT_TXT_SHA,
        "current_22_bootdelay3": len(mo) == 22 and mk.get("bootdelay") == "3"
                                 and not rep["current_txt"]["has_side_vars"],
        "dump_baseline": rep["dump"]["sha256"] == BASELINE_FULL_SHA
                         and rep["dump"]["env_crc"] == BASELINE_ENV_CRC,
        "prediction": bool(rep["pred"]["ok"] and rep["pred"]["expected_crc_ok"]
                           and rep["pred"]["expected_env_sha_ok"]
                           and rep["pred"]["expected_full_sha_ok"]
                           and rep["pred"]["entries_ok"]
                           and rep["pred"]["diff_bytes"] == 140
                           and rep["pred"]["diff_outside_env"] == 0),
        "capture": bool(rep["capture_chain"]["supervisor_pids"]
                        and rep["capture_chain"]["bootwatch_pids"]
                        and rep["capture_chain"]["tty_holders"]),
        "route_direct": rep["route"]["direct"],
        "vendor_pw": rep["vendor_pw"]["mode"] == "0o600" and os.path.exists(DEV_PW),
        "scripts": all(rep["scripts"].values()),
    }
    rep["ok"] = all(rep["checks"].values())
    with open(outdir + "/prediction.json", "w") as f:
        json.dump(rep, f, indent=1)
    log("PREFLIGHT " + ("OK" if rep["ok"] else "ISSUES"))
    log(json.dumps(rep["checks"]))
    log("prediction: crc=0x%08X env_sha=%s full_sha=%s diff=%s B outside_env=%s" % (
        rep["pred"].get("env_crc", 0), rep["pred"].get("env_sha256"),
        rep["pred"].get("full_sha256"), rep["pred"].get("diff_bytes"),
        rep["pred"].get("diff_outside_env")))
    if not rep["ok"]:
        log(json.dumps({k: v for k, v in rep["pred"].items() if k != "entries"}, indent=1)[:3000])
    return 0 if rep["ok"] else 1


def readback_env(pred):
    rc, out, err = ssh_run("sha256sum /dev/mtd0; dd if=/dev/mtd0 bs=131072 skip=6 count=1 2>/dev/null | od -An -v -tx1", 180)
    rep = {"ssh_rc": rc, "ssh_err_tail": err[-300:]}
    lines = out.splitlines()
    full_sha = lines[0].split()[0] if lines and lines[0].split() else None
    hexstr = "".join("".join(line.split()) for line in lines[1:])
    rep["full_sha256"] = full_sha
    rep["expected_full_sha256"] = pred["full_sha256"]
    try:
        block = bytes.fromhex(hexstr)
    except ValueError:
        block = b""
    rep["block_size"] = len(block)
    if len(block) == ENV_SIZE:
        rep["env_sha256"] = hashlib.sha256(block).hexdigest()
        rep["env_crc"] = int.from_bytes(block[:4], "little")
        ent = {}
        for chunk in block[4:].split(b"\x00"):
            if not chunk:
                continue
            k, _, v = chunk.decode("latin-1").partition("=")
            ent[k] = v
        rep["entries"] = ent
        rep["expected"] = pred["entries"]
        rep["entry_count"] = len(ent)
    rep["env_byte_identical"] = (len(block) == ENV_SIZE
                                 and hashlib.sha256(block).hexdigest() == pred["env_sha256"])
    rep["full_sha_match"] = full_sha == pred["full_sha256"]
    rep["crc_ok"] = len(block) == ENV_SIZE and int.from_bytes(block[:4], "little") == pred["env_crc"]
    want = pred["entries"]
    got = rep.get("entries", {})
    rep["entries_ok"] = (len(got) == 26
                         and all(got.get(k) == v for k, v in want.items())
                         and all(got.get(k) == v for k, v in NEW_VARS))
    rep["ok"] = bool(rep["env_byte_identical"] and rep["full_sha_match"]
                     and rep["crc_ok"] and rep["entries_ok"])
    return rep


def wait_uptime(seconds=75, timeout=150):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        rc, out, _ = ssh_run("cut -d. -f1 /proc/uptime", 30)
        if rc == 0 and out.strip().isdigit():
            last = int(out.strip())
            if last >= seconds:
                return {"ok": True, "uptime": last}
        time.sleep(5)
    return {"ok": False, "uptime": last}


def run_session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/session-driver.log"
    results = {"mode": "session", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        pred = json.load(open(outdir + "/prediction.json"))["pred"]
        results["prediction"] = {"env_crc": hex(pred["env_crc"]),
                                 "env_sha256": pred["env_sha256"],
                                 "full_sha256": pred["full_sha256"],
                                 "baseline_full_sha256": BASELINE_FULL_SHA}
        if not (pred["env_crc"] == EXPECTED_ENV_CRC and pred["full_sha256"] == EXPECTED_FULL_SHA):
            raise RuntimeError("prediction.json does not match the approved-scope constants")
        results["capture_before"] = base.pause_capture()
        if not results["capture_before"]["free"]:
            raise RuntimeError("tty busy after pausing the capture chain")
        results["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        log("READY FOR USER POWER CYCLE (cold boot, B1 env session); waiting up to %ss" % args.entry_timeout)
        entry = base.enter_vendor_console(c, args.entry_timeout)
        results["vendor_entry"] = entry
        if not entry.get("ok"):
            raise RuntimeError("vendor console entry failed: " + json.dumps(entry))
        log("console entered (vendor U-Boot 2013.04, stock banner)")
        help_text = send_checked(c, "help", 20)
        results["help"] = {"len": len(help_text),
                           "setenv_present": "setenv" in help_text,
                           "saveenv_present": "saveenv" in help_text,
                           "raw_tail": help_text[-1500:]}
        log("help precheck: setenv=%s saveenv=%s" % (
            results["help"]["setenv_present"], results["help"]["saveenv_present"]))
        if not (results["help"]["setenv_present"] and results["help"]["saveenv_present"]):
            raise RuntimeError("vendor console help lacks setenv/saveenv; refusing to write")
        base_mk, base_mo = read_expected_txt(CURRENT_TXT)
        pre_text = send_checked(c, "printenv", 30)
        pre_entries, pre_order = parse_env(pre_text)
        results["pre_printenv"] = {"entries": pre_entries, "order": pre_order,
                                   "raw_tail": pre_text[-2500:]}
        results["pre_match_baseline"] = (pre_entries == base_mk and pre_order == base_mo)
        log("baseline printenv: %d entries, match_baseline=%s, bootdelay=%s" % (
            len(pre_order), results["pre_match_baseline"], pre_entries.get("bootdelay")))
        if not results["pre_match_baseline"]:
            raise RuntimeError("live env does not match evidence/b1-env-current; refusing to write")
        setenv_steps = []
        for k, v in NEW_VARS:
            t0 = time.time()
            out = send_checked(c, "setenv " + k + " " + v, 20)
            check = send_checked(c, "printenv " + k, 20)
            want = k + "=" + v
            step = {"key": k, "value": v, "ok": want in check,
                    "elapsed_s": round(time.time() - t0, 2), "tail": check[-200:]}
            setenv_steps.append(step)
            log("setenv " + k + ": " + ("OK" if step["ok"] else "MISMATCH"))
        results["setenv_steps"] = setenv_steps
        if not all(s["ok"] for s in setenv_steps):
            raise RuntimeError("a setenv readback did not match; refusing to saveenv")
        mid_text = send_checked(c, "printenv", 30)
        mid_entries, mid_order = parse_env(mid_text)
        expected = dict(base_mk)
        expected.update(dict(NEW_VARS))
        expected_order = list(base_mo) + [k for k, _ in NEW_VARS]
        results["pre_saveenv"] = {"entries": len(mid_order), "order": mid_order,
                                  "bootcmd": mid_entries.get("bootcmd"),
                                  "versioninfo": mid_entries.get("versioninfo"),
                                  "raw_tail": mid_text[-2500:]}
        results["pre_saveenv_ok"] = (mid_entries == expected and mid_order == expected_order)
        log("pre-saveenv printenv: %d entries, exact_target=%s, bootcmd_unchanged=%s" % (
            len(mid_order), results["pre_saveenv_ok"],
            mid_entries.get("bootcmd") == base_mk.get("bootcmd")))
        if not results["pre_saveenv_ok"]:
            raise RuntimeError("combined env does not match the target; refusing to saveenv")
        results["write_scope"] = "one saveenv: 4 side vars only"
        t0 = time.time()
        save_text = send_checked(c, "saveenv", 120)
        results["saveenv"] = {"elapsed_s": round(time.time() - t0, 2), "raw_tail": save_text[-2000:],
                              "error_text": ("## Error" in save_text) or ("Failed" in save_text),
                              "ok": ("Saving Environment" in save_text or "OK" in save_text
                                     or "ok" in save_text or "done" in save_text.lower())
                              and "## Error" not in save_text and "Failed" not in save_text}
        log("saveenv: ok=%s elapsed=%.1fs" % (results["saveenv"]["ok"], results["saveenv"]["elapsed_s"]))
        if not results["saveenv"]["ok"]:
            raise RuntimeError("saveenv did not report success")
        post_text = send_checked(c, "printenv", 30)
        post_entries, post_order = parse_env(post_text)
        results["post_saveenv"] = {"entries": len(post_order), "exact_target":
                                   post_entries == expected and post_order == expected_order,
                                   "raw_tail": post_text[-2000:]}
        if not results["post_saveenv"]["exact_target"]:
            raise RuntimeError("post-saveenv printenv does not match the target")
        log("saveenv done; printenv %d entries exact" % len(post_order))
        c.pending = b""
        log("rebooting (normal boot; do_settings survival test)")
        c.send(b"reset\r")
        rebooted = False
        deadline = time.time() + 20
        markers = [b"Press 1 means", b"pdt_cspboot", b"e2631-wifi-boot", b"ImmortalWrt", b"Booting image"]
        while time.time() < deadline:
            data = c.read()
            if data:
                c.pending += data
            if any(m in bytes(c.pending) for m in markers):
                rebooted = True
                break
            time.sleep(0.02)
        results["reboot"] = {"reset_rebooted": rebooted}
        log("reboot marker=%s" % rebooted)
        if not rebooted:
            log("POWER CYCLE REQUIRED (reset did not reboot); waiting %ss for Linux" % args.boot_timeout)
            results["reboot"]["power_cycle_required"] = True
        lin = base.wait_linux(c, args.boot_timeout)
        results["linux"] = lin
        log("Linux marker: " + json.dumps(lin))
        if not lin.get("ok"):
            raise RuntimeError("Linux did not boot after saveenv")
        results["transcript"] = "serial.log"
        open(outdir + "/console-transcript.txt", "wb").write(bytes(c.history))
    except Exception as exc:
        results["error"] = str(exc)
        log("SESSION ERROR: " + str(exc))
    finally:
        try:
            base.stop_hub()
        except Exception:
            pass
        results["capture_after"] = base.restore_capture()
        try:
            results["route_fix"] = ensure_direct_link()
            up = wait_uptime(75, 150)
            results["uptime_wait"] = up
            rc, out, _ = base.sh("bash " + base.HEALTH, timeout=180)
            results["health_rc"] = rc
            results["health"] = out[-4000:]
            open(outdir + "/health.txt", "w").write(out)
        except Exception as exc:
            results["health_error"] = str(exc)
        if results.get("linux", {}).get("ok") and not results.get("error"):
            try:
                results["readback"] = readback_env(results["prediction"])
                log("env readback: " + json.dumps({k: results["readback"].get(k) for k in
                    ("env_byte_identical", "full_sha_match", "crc_ok", "entries_ok",
                     "entry_count", "full_sha256")}))
            except Exception as exc:
                results["readback"] = {"ok": False, "error": str(exc)}
                log("readback error: " + str(exc))
        results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        health_text = results.get("health", "") or ""
        health_ok = ("VERSION=ImmortalWrt" in health_text) and ("PANICS=0" in health_text)
        rb = results.get("readback", {}) or {}
        results["verdict"] = "GREEN" if (
            results.get("pre_match_baseline")
            and all(s.get("ok") for s in results.get("setenv_steps", []))
            and results.get("pre_saveenv_ok")
            and results.get("saveenv", {}).get("ok")
            and results.get("linux", {}).get("ok")
            and rb.get("ok")
            and results.get("route_fix", {}).get("ok")
            and results.get("capture_after", {}).get("ok")
            and health_ok and not results.get("error")) else "FAIL"
        with open(outdir + "/session-results.json", "w") as f:
            json.dump(results, f, indent=1)
        log("VERDICT " + results["verdict"] + " (results in " + outdir + "/session-results.json)")
    return 0 if results["verdict"] == "GREEN" else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--out-dir", default=SESSION_DIR + "/run-1")
    ap.add_argument("--entry-timeout", type=int, default=600)
    ap.add_argument("--boot-timeout", type=int, default=900)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.preflight:
        return run_preflight(args)
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())
