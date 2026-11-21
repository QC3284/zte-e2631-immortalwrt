#!/usr/bin/env python3
"""B1 attach-resume: finish the approved single saveenv on the live vendor console.

The first B1 session aborted BEFORE saveenv because the driver expected the 4 new
side vars to be appended at the end of the env, but the vendor env is stored
sorted: the vars are inserted alphabetically between console and ethact.  The
device is still sitting at the vendor U-Boot prompt with the 4 vars in RAM only.
This resume re-verifies the 26 in-RAM entries (sorted order, bootdelay 3,
bootcmd untouched), rebuilds the prediction from the observed sorted order, sends
exactly one saveenv, reboots, and byte-compares the on-flash env block over
read-only SSH.  Approved write scope unchanged: 4 side vars + one saveenv.
"""
import argparse, hashlib, json, os, sys, time, zlib

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import a1_banner_accept as base
import b1_env_session as b1

P3 = base.P3
OUT_DEFAULT = P3 + "/b1-env-session/resume-1"
NL = chr(10)
DUMP = b1.DUMP
ENV_OFF = b1.ENV_OFF
ENV_SIZE = b1.ENV_SIZE
BASELINE_FULL = b1.BASELINE_FULL_SHA
NEW = dict(b1.NEW_VARS)
APPROVED = {"env_crc": 0xF95A816E,
            "env_sha256": "6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893",
            "full_sha256": "887a7f6c9b407abc734eb9a76f08733a691441f91987369e8626deb8faf0fa9f",
            "diff_bytes": 462}
BASELINE_PRE = "9e647df44854c1bfa905616476ada0b3ba4452f3c1f8225aa2daee4db0a354bf"
BASELINE_POST = "b5a41c3758763bbec72769fab4a2533bf2db0b6312d93d25a695f9e4b9e02260"


def log(msg):
    b1.log(msg)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_baseline():
    dump = open(DUMP, "rb").read()
    if sha_bytes(dump) != BASELINE_FULL:
        raise RuntimeError("baseline dump sha256 mismatch: " + DUMP)
    return dump


def expected_env():
    entries, order = b1.read_expected_txt(b1.CURRENT_TXT)
    exp = dict(entries)
    exp.update(NEW)
    return exp


def block_entries(block):
    ent = {}
    for chunk in block[4:].split(bytes([0])):
        if not chunk:
            continue
        k, _, v = chunk.decode("latin-1").partition("=")
        ent[k] = v
    return ent


def write_expected_txt(path, entries, order):
    with open(path, "w") as f:
        f.write(NL.join(k + "=" + entries[k] for k in order) + NL)


def build_prediction(outdir):
    expected = expected_env()
    order = sorted(expected.keys())
    txt = outdir + "/observed-env.txt"
    write_expected_txt(txt, expected, order)
    block = outdir + "/target-env-block.bin"
    full = outdir + "/target-mtd0.bin"
    cmd = ("cd " + b1.KIT + " && node tools/e2631-env.mjs build --in " + txt +
           " --out " + block + " --template " + DUMP + " --full-mtd0 " + full)
    rc, out, err = base.sh(cmd, timeout=120)
    if rc != 0 or not os.path.exists(block) or not os.path.exists(full):
        raise RuntimeError("env build failed rc=" + str(rc) + " stderr=" + err[-400:])
    blk = open(block, "rb").read()
    fl = open(full, "rb").read()
    dump = load_baseline()
    diff = 0
    outside = 0
    first = -1
    last = -1
    for i in range(len(dump)):
        if dump[i] != fl[i]:
            diff += 1
            if first < 0:
                first = i
            last = i
            if not (ENV_OFF <= i < ENV_OFF + ENV_SIZE):
                outside += 1
    crc = int.from_bytes(blk[:4], "little")
    calc = zlib.crc32(blk[4:]) & 0xFFFFFFFF
    rep = {"ok": True, "target_txt": txt, "block": block, "full": full,
           "entries": expected, "order": order, "env_crc": crc, "env_crc_calc": calc,
           "env_sha256": sha_bytes(blk), "full_sha256": sha_bytes(fl),
           "diff_bytes": diff, "diff_outside_env": outside,
           "diff_first": first, "diff_last": last, "build_stdout_tail": out[-400:]}
    if crc != calc:
        raise RuntimeError("prediction CRC does not verify")
    return rep


def save_results(outdir, results):
    with open(outdir + "/session-results.json", "w") as f:
        json.dump(results, f, indent=1)


def short(s):
    return s[:16] + "..." if isinstance(s, str) and len(s) > 16 else str(s)


def readback(pred):
    remote = ("sha256sum /dev/mtd0; "
              "dd if=/dev/mtd0 bs=4096 skip=0 count=192 2>/dev/null | sha256sum; "
              "dd if=/dev/mtd0 bs=4096 skip=224 count=32 2>/dev/null | sha256sum; "
              "dd if=/dev/mtd0 bs=131072 skip=6 count=1 2>/dev/null | hexdump -v -C")
    rc, out, err = b1.ssh_run(remote, 180)
    rep = {"ssh_rc": rc, "ssh_err_tail": err[-300:]}
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if rc != 0 or len(lines) < 3:
        rep["ok"] = False
        rep["raw_head"] = lines[:6]
        return rep
    full = lines[0].split()[0]
    pre = lines[1].split()[0]
    post = lines[2].split()[0]
    hexparts = []
    hexchars = "0123456789abcdef"
    for line in lines[3:]:
        head = line.split("|")[0]
        for tok in head.split()[1:]:
            if len(tok) == 2 and all(ch in hexchars for ch in tok):
                hexparts.append(tok)
    try:
        block = bytes.fromhex("".join(hexparts))
    except ValueError:
        block = bytes([0])
    rep.update({"full_sha256": full, "full_sha_match": full == pred["full_sha256"],
                "outside_env_hashes": {"pre": pre, "post": post},
                "outside_env_ok": pre == BASELINE_PRE and post == BASELINE_POST,
                "block_size": len(block)})
    if len(block) == ENV_SIZE:
        crc = int.from_bytes(block[:4], "little")
        ent = block_entries(block)
        rep.update({"env_crc": hex(crc), "env_sha256": sha_bytes(block),
                    "entry_count": len(ent), "actual_order": list(ent.keys()),
                    "crc_ok": crc == pred["env_crc"],
                    "env_byte_identical": sha_bytes(block) == pred["env_sha256"],
                    "entries_ok": len(ent) == 26 and all(ent.get(k) == v for k, v in pred["entries"].items())})
        open(pred["block"].replace("target-env-block.bin", "actual-env-block.bin"), "wb").write(block)
    rep["ok"] = bool(rep.get("env_byte_identical") and rep.get("crc_ok")
                     and rep.get("entries_ok") and rep.get("full_sha_match")
                     and rep.get("outside_env_ok"))
    return rep


def selftest():
    outdir = P3 + "/b1-env-session/selftest-resume"
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/selftest.log"
    pred = build_prediction(outdir)
    checks = {
        "env_crc": pred["env_crc"] == APPROVED["env_crc"],
        "env_sha": pred["env_sha256"] == APPROVED["env_sha256"],
        "full_sha": pred["full_sha256"] == APPROVED["full_sha256"],
        "diff": pred["diff_bytes"] == APPROVED["diff_bytes"],
        "outside_env": pred["diff_outside_env"] == 0,
        "order_sorted": pred["order"] == sorted(pred["order"]),
        "count_26": len(pred["entries"]) == 26,
        "bootdelay_3": pred["entries"].get("bootdelay") == "3",
    }
    rep = {"mode": "selftest", "checks": checks, "env_crc": hex(pred["env_crc"]),
           "env_sha256": pred["env_sha256"], "full_sha256": pred["full_sha256"],
           "diff_bytes": pred["diff_bytes"], "diff_outside_env": pred["diff_outside_env"],
           "order": pred["order"], "ok": all(checks.values())}
    with open(outdir + "/selftest-resume.json", "w") as f:
        json.dump(rep, f, indent=1)
    log("selftest: " + json.dumps({k: rep[k] for k in ("ok", "env_crc", "diff_bytes")}))
    print(json.dumps(rep, indent=1))
    return 0 if rep["ok"] else 2


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    b1.make_askpass()
    chain = {"supervisor_pids": base.pgrep("capture-supervisor-002.sh"),
             "bootwatch_pids": base.pgrep("serial-bootwatch.mjs"),
             "tty_holders": base.tty_holders()}
    dump = open(DUMP, "rb").read()
    exp = expected_env()
    rep = {"mode": "preflight", "capture_chain": chain,
           "baseline_dump_sha": sha_bytes(dump), "baseline_dump_ok": sha_bytes(dump) == BASELINE_FULL,
           "expected_entries": len(exp), "new_vars": NEW,
           "hub": os.path.exists(base.HUB), "restore": os.path.exists(base.RESTORE),
           "health": os.path.exists(base.HEALTH), "askpass_mode": oct(os.stat(b1.ASKPASS).st_mode & 0o777),
           "artifacts_exist": os.path.exists(py_path()), "approved": APPROVED}
    rep["ok"] = bool(chain["supervisor_pids"] and chain["bootwatch_pids"] and chain["tty_holders"]
                    and rep["baseline_dump_ok"] and rep["hub"] and rep["restore"] and rep["health"]
                    and rep["askpass_mode"] == "0o700" and rep["artifacts_exist"] and len(exp) == 26)
    with open(args.out_dir + "/preflight-resume.json", "w") as f:
        json.dump(rep, f, indent=1)
    log("preflight: " + json.dumps({"ok": rep["ok"], "chain": chain}))
    print(json.dumps(rep, indent=1))
    return 0 if rep["ok"] else 2


def py_path():
    return os.path.abspath(sys.argv[0])


def run_session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/session-driver.log"
    b1.make_askpass()
    results = {"mode": "attach-resume", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    pred = None
    try:
        load_baseline()
        results["capture_before"] = base.pause_capture()
        if not results["capture_before"].get("free"):
            raise RuntimeError("tty busy after pausing the capture chain")
        results["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        ver = b1.send_checked(c, "version", 20)
        results["attach_version_tail"] = ver[-500:]
        log("ATTACHED vendor console (version banner read back)");
        save_results(outdir, results)
        pre_text = b1.send_checked(c, "printenv", 40)
        entries, order = b1.parse_env(pre_text)
        expected = expected_env()
        sorted_order = sorted(entries.keys())
        checks = {"count": len(entries),
                  "entries_match": entries == expected,
                  "order_sorted": order == sorted_order,
                  "bootdelay": entries.get("bootdelay"),
                  "bootcmd_unchanged": entries.get("bootcmd") == expected.get("bootcmd"),
                  "versioninfo_unchanged": entries.get("versioninfo") == expected.get("versioninfo")}
        results["pre_printenv"] = {"entries": entries, "order": order, "checks": checks,
                                   "raw_tail": pre_text[-2000:]}
        if not (checks["count"] == 26 and checks["entries_match"] and checks["order_sorted"]
                and checks["bootdelay"] == "3" and checks["bootcmd_unchanged"]
                and checks["versioninfo_unchanged"]):
            raise RuntimeError("in-RAM env is not the expected sorted 26-entry target; refusing saveenv")
        log("PRE-ENTRIES-OK count=26 sorted=True bootdelay=3 bootcmd_unchanged=True");
        save_results(outdir, results)
        pred = build_prediction(outdir)
        pred_ok = (pred["env_crc"] == APPROVED["env_crc"]
                   and pred["env_sha256"] == APPROVED["env_sha256"]
                   and pred["full_sha256"] == APPROVED["full_sha256"]
                   and pred["diff_bytes"] == APPROVED["diff_bytes"]
                   and pred["diff_outside_env"] == 0)
        results["prediction"] = {"env_crc": hex(pred["env_crc"]), "env_sha256": pred["env_sha256"],
                                  "full_sha256": pred["full_sha256"], "diff_bytes": pred["diff_bytes"],
                                  "diff_outside_env": pred["diff_outside_env"], "order": pred["order"],
                                  "matches_approved": pred_ok}
        log("PREDICTION-OK crc=" + hex(pred["env_crc"]) + " env_sha=" + short(pred["env_sha256"])
            + " full_sha=" + short(pred["full_sha256"]) + " diff=" + str(pred["diff_bytes"]) + " outside_env=0")
        if not pred_ok:
            raise RuntimeError("rebuilt prediction does not match the approved revised constants")
        save_results(outdir, results)
        save_text = b1.send_checked(c, "saveenv", 120)
        ok = ("Saving Environment" in save_text or "OK" in save_text or "ok" in save_text)
        ok = ok and "## Error" not in save_text and "Failed" not in save_text
        results["saveenv"] = {"ok": ok, "raw_tail": save_text[-1500:]}
        log("SAVEENV-OK" if ok else "SAVEENV-FAILED");
        save_results(outdir, results)
        if not ok:
            raise RuntimeError("saveenv did not report success")
        post_text = b1.send_checked(c, "printenv", 40)
        pentries, porder = b1.parse_env(post_text)
        exact = (pentries == expected and len(pentries) == 26)
        results["post_printenv"] = {"entries": pentries, "order": porder, "exact": exact,
                                    "raw_tail": post_text[-1500:]}
        if not exact:
            raise RuntimeError("post-saveenv printenv does not match the target")
        log("POST-SAVEENV-OK 26 entries exact");
        save_results(outdir, results)
        c.pending = bytes()
        log("REBOOT: sending reset");
        c.send(b"reset" + bytes([13]))
        markers = [b"Press 1 means", b"pdt_cspboot", b"ImmortalWrt", b"e2631-wifi-boot",
                   b"Booting image", b"U-Boot 2013.04"]
        rebooted = False
        accum = bytes()
        deadline = time.time() + 20
        while time.time() < deadline:
            data = c.read()
            if data:
                accum += data
                c.pending += data
            if any(m in accum for m in markers):
                rebooted = True
                break
            time.sleep(0.05)
        results["reboot"] = {"reset_rebooted": rebooted, "tail": accum[-400:].decode("latin-1", "replace")}
        log("RESET-REBOOTED" if rebooted else "POWER CYCLE REQUIRED (vendor reset did not reboot); waiting up to " + str(args.powercycle_timeout) + "s");
        save_results(outdir, results)
        lin = base.wait_linux(c, args.boot_timeout if rebooted else args.powercycle_timeout)
        results["linux"] = lin
        log("LINUX-BOOTING marker=" + str(lin.get("ok")));
        if not lin.get("ok"):
            raise RuntimeError("Linux did not boot after saveenv")
        open(outdir + "/console-transcript.txt", "wb").write(bytes(c.history))
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
        try:
            results["route_fix"] = b1.ensure_direct_link()
        except Exception as exc:
            results["route_fix"] = {"ok": False, "error": str(exc)}
        save_results(outdir, results)
        if results.get("linux", {}).get("ok") and pred is not None:
            try:
                results["readback"] = readback(pred)
                rb = results["readback"]
                log("READBACK " + json.dumps({k: rb.get(k) for k in
                    ("ok", "env_byte_identical", "full_sha_match", "crc_ok", "entries_ok", "outside_env_ok")}))
            except Exception as exc:
                results["readback"] = {"ok": False, "error": str(exc)}
                log("readback error: " + str(exc))
            save_results(outdir, results)
            try:
                results["uptime_wait"] = b1.wait_uptime(70, 180)
                rc, out, err = base.sh("bash " + base.HEALTH, timeout=220)
                results["health_rc"] = rc
                results["health"] = out[-4000:]
                open(outdir + "/health.txt", "w").write(out)
                log("HEALTH rc=" + str(rc));
            except Exception as exc:
                results["health_error"] = str(exc)
        health_text = results.get("health", "") or ""
        health_ok = ("VERSION=ImmortalWrt" in health_text) and ("PANICS=0" in health_text)
        rb = results.get("readback", {}) or {}
        results["verdict"] = "GREEN" if (
            results.get("pre_printenv", {}).get("checks", {}).get("entries_match")
            and results.get("prediction", {}).get("matches_approved")
            and results.get("saveenv", {}).get("ok")
            and results.get("post_printenv", {}).get("exact")
            and results.get("linux", {}).get("ok")
            and rb.get("ok")
            and results.get("capture_after", {}).get("ok")
            and health_ok and not results.get("error")) else "FAIL"
        results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        save_results(outdir, results)
        log("VERDICT " + results["verdict"] + " (results in " + outdir + "/session-results.json)")
    return 0 if results["verdict"] == "GREEN" else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    ap.add_argument("--boot-timeout", type=int, default=900)
    ap.add_argument("--powercycle-timeout", type=int, default=900)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.preflight:
        return preflight(args)
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())