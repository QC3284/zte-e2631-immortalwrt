#!/usr/bin/env python3
"""Session B (v3): env baseline restore + v3 mtd0 image write ladder.

Lead sequence (m07061):
 1. reboot -f (current Linux) -> old flash U-Boot g2797f3dd3860 -> stop autoboot
 2. loadx vendor-uboot-ram.bin -> go 0x47f00000 -> vendor console (Press 1 + password)
 3. vendor console: xmodem v3 u-boot.bin (450,936 B) -> go 0x47f00000 ->
    our v3 console (banner g85c7367a3106 gate)
 4. env baseline restore: mtd erase 0xc0000 0x20000 -> FF gate -> write the
    6e2c01da... env block -> asserted readback
 5. v3 image ladder: loadx -> md.b verify -> erase 0x20000 0xa0000 -> FF gate ->
    write -> asserted readback -> env/secondboot/tail baseline checks ->
    WRITE VERIFIED + HOLD

No reset from the driver. Session C is the user's physical power cycle that
proves the new image boots from flash. Zero writes happen before the env erase.
"""
import json, os, re, struct, sys, time

sys.path.insert(0, "/home/qc233/zte/e2631-p3")
import c1b1_final as fin
import b1_env_session as b1

base = fin.base
OUT_DEFAULT = "/home/qc233/zte/e2631-p3/c1b2-session-b"
ART_DIR = ("/home/qc233/zte/e2631-t5-artifacts/uboot-a6v3-44935007253/"
           "e2631-uboot-44935007253")
ART_UBOOT = ART_DIR + "/u-boot.bin"
ART_IMAGE = ART_DIR + "/e2631-uboot-mtd0.bin"
ART_UBOOT_SHA = "3bf182f148226b6f64696a05bba5d75ca59426747f87eee3f13c5d2b0269423a"
ART_IMAGE_SHA = "f6d179daa952db910afacde635f259fbe5f2eabf97f3d8aa07d2c09540979a42"
ART_UBOOT_SIZE = 450936
NEW_BANNER = "U-Boot 2027.01-rc2-g85c7367a3106"
OLD_BANNER = "U-Boot 2027.01-rc2-g2797f3dd3860"
VENDOR_RAM = ("/home/qc233/zte/e2631-immortalwrt/evidence/p2-oob/"
              "vendor-uboot-ram.bin")
VENDOR_RAM_SHA = "a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30"
BASELINE = fin.DEFAULT_BASELINE
BASELINE_SHA = "887a7f6c9b407abc734eb9a76f08733a691441f91987369e8626deb8faf0fa9f"
ENV_BLOCK_SHA = "6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893"
CLEAN_AFTER_SHA = "3c8a8c5b0f9db1953628919d650ff7af6d24e07c48e9a31d5b228881a9f36ffb"
OLD_IMAGE_SHA = "baf28b6da4d6ca1b356389951b9d49765382b35dd382bc81c8a0a589c09464dd"
OLD_IMAGE = ("/home/qc233/zte/e2631-t5-artifacts/uboot-c1b0-44898534408/"
             "e2631-uboot-44898534408/e2631-uboot-mtd0.bin")
BOOT_ADDR = 0x47F00000
RAM_IMAGE = 0x44000000
RAM_READ = 0x45000000
RAM_ENV = 0x46000000
RAM_BOOT = 0x47000000
CHUNK = 0x4000
FLASH_OFF = 0x20000
IMAGES_AREA = 0xA0000
ENV_OFF = 0xC0000
ENV_SIZE = 0x20000
TAIL_OFF = 0xE0000
ALLOW = [
    r"^(help|version|printenv|mtd list)$",
    r"^md\.[lbw] 0x[0-9a-f]+( (?:0x)?[0-9a-f]+)?$",
    r"^loadx 0x[0-9a-f]+$",
    r"^mtd read spi-nand0 0x[0-9a-f]+ 0x[0-9a-f]+ 0x[0-9a-f]+$",
    r"^mtd erase spi-nand0 0xc0000 0x20000$",
    r"^mtd erase spi-nand0 0x20000 0xa0000$",
    r"^mtd write spi-nand0 0x46000000 0xc0000 0x20000$",
    r"^mtd write spi-nand0 0x44000000 0x20000 0xa0000$",
    r"^cmp 0x[0-9a-f]+ 0x[0-9a-f]+ 0x[0-9a-f]+$",
    r"^go 0x47f00000$",
]
DENY = ("nand ", "saveenv", "upgrade", "tftp", "bootm", "setenv", "mw.", "cp.",
        "mtd erase spi-nand0 0x0 ", "mtd write spi-nand0 0x0 ",
        "mtd erase spi-nand0 0x20000 0xc0000", "mtd erase spi-nand0 0xc0000 0xa0000")


def log(msg):
    base.log(msg)


def sha_bytes(data):
    return fin.sha_bytes(data)


def read_file(path):
    with open(path, "rb") as fh:
        return fh.read()


def check_command(text):
    low = text.strip().lower()
    if low.startswith("go ") and low != "go 0x47f00000":
        return False
    if any(t in low for t in DENY):
        return False
    return any(re.match(p, low) for p in ALLOW)


def send(c, results, text, timeout=300):
    if not check_command(text):
        raise RuntimeError("refusing console command: " + text)
    results.setdefault("commands", []).append(text)
    c.pending = bytes()
    c.send((text + "\r").encode())
    out = fin.wait_prompt(c, timeout)
    results.setdefault("command_outputs", {})[text] = (out or b"")[-4000:].decode("latin-1", "replace")
    return out or b""


def send_go(c, results, text="go 0x47f00000"):
    if not check_command(text):
        raise RuntimeError("refusing console command: " + text)
    results.setdefault("commands", []).append(text)
    c.pending = bytes()
    c.send((text + "\r").encode())
    log("sent: " + text)


def read_region(c, results, label, addr, off, size, timeout=420):
    out = send(c, results, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (addr, off, size), timeout)
    txt = out.decode("latin-1", "replace")
    ok = ("Reading %d byte(s)" % size) in txt and "Failure while reading" not in txt and "failed with error" not in txt
    results.setdefault("reads", {})[label] = {"ok": ok, "tail": txt[-600:]}
    log("read " + label + " ok=" + str(ok))
    return ok


def enter_flash_console(c, results, timeout):
    pat = re.compile(re.escape(OLD_BANNER.encode()))
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = c.read()
        if data:
            c.pending += data
            if pat.search(c.pending):
                results["flash_banner_seen"] = True
                break
        time.sleep(0.05)
    results["flash_stop_autoboot"] = fin.stop_autoboot(c, results, OLD_BANNER, 30)
    return bool(results["flash_stop_autoboot"].get("prompt"))


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    b1.make_askpass()
    art = read_file(ART_UBOOT)
    image = read_file(ART_IMAGE)
    vendor = read_file(VENDOR_RAM)
    base_img = read_file(BASELINE)
    envblk = base_img[ENV_OFF:ENV_OFF + ENV_SIZE]
    old_img = read_file(OLD_IMAGE)
    expected = bytearray(base_img)
    expected[FLASH_OFF:ENV_OFF] = image
    expected = bytes(expected)
    dev = {}
    try:
        rc, out, err = b1.ssh_run("sha256sum /dev/mtd0; cut -d. -f1 /proc/uptime; cat /etc/e2631-version", 40)
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        dev = {"mtd0_sha256": lines[0].split()[0] if lines else None,
               "uptime": lines[1] if len(lines) > 1 else None,
               "version": lines[2] if len(lines) > 2 else None}
    except Exception as exc:
        dev = {"error": repr(exc)}
    route = base.sh("ip route get 192.168.1.1 | head -1")[1]
    chain = {"supervisor_pids": base.pgrep("capture-supervisor-002.sh"),
             "bootwatch_pids": base.pgrep("serial-bootwatch.mjs"),
             "tty_holders": base.tty_holders()}
    with open(args.out_dir + "/target-env-block.bin", "wb") as fh:
        fh.write(envblk)
    with open(args.out_dir + "/expected-mtd0.bin", "wb") as fh:
        fh.write(expected)
    rep = {
        "artifact": {"path": ART_UBOOT, "size": len(art), "sha256": sha_bytes(art),
                     "sha_ok": sha_bytes(art) == ART_UBOOT_SHA,
                     "size_ok": len(art) == ART_UBOOT_SIZE,
                     "new_banner_present": NEW_BANNER.encode() in art},
        "image": {"path": ART_IMAGE, "size": len(image), "sha256": sha_bytes(image),
                  "sha_ok": sha_bytes(image) == ART_IMAGE_SHA,
                  "is_0xa0000": len(image) == IMAGES_AREA,
                  "header_magic_128s": image[0x10:0x14] == b"128s",
                  "header_diff_only_length": (
                      image[:0x14] == base_img[FLASH_OFF:FLASH_OFF + 0x14]
                      and struct.unpack("<I", image[0x14:0x18])[0] == len(art)
                      and image[0x18:0x800] == base_img[FLASH_OFF + 0x18:FLASH_OFF + 0x800]),
                  "payload_matches_uboot": image[0x800:0x800 + len(art)] == art,
                  "tail_ff": set(image[0x800 + len(art):]) == {0xFF}},
        "vendor_ram": {"path": VENDOR_RAM, "size": len(vendor),
                       "sha256": sha_bytes(vendor), "ok": sha_bytes(vendor) == VENDOR_RAM_SHA},
        "baseline": {"sha256": sha_bytes(base_img), "ok": sha_bytes(base_img) == BASELINE_SHA,
                     "env_block_sha256": sha_bytes(envblk), "env_block_ok": sha_bytes(envblk) == ENV_BLOCK_SHA},
        "old_image": {"sha256": sha_bytes(old_img), "ok": sha_bytes(old_img) == OLD_IMAGE_SHA},
        "expected_after": {"sha256": sha_bytes(expected),
                           "clean_old_image_sha256": sha_bytes(bytes(bytearray(base_img[:FLASH_OFF]) + old_img + base_img[ENV_OFF:]))},
        "device": dev, "route": route, "capture_chain": chain,
        "vendor_pw_mode": oct(os.stat(base.VENDOR_PW_FILE).st_mode & 0o777),
        "erase_env_cmd": "mtd erase spi-nand0 0xc0000 0x20000",
        "write_env_cmd": "mtd write spi-nand0 0x46000000 0xc0000 0x20000",
        "erase_image_cmd": "mtd erase spi-nand0 0x20000 0xa0000",
        "write_image_cmd": "mtd write spi-nand0 0x44000000 0x20000 0xa0000",
    }
    rep["clean_old_image_ok"] = rep["expected_after"]["clean_old_image_sha256"] == CLEAN_AFTER_SHA
    rep["ok"] = bool(rep["artifact"]["sha_ok"] and rep["artifact"]["size_ok"]
                     and rep["artifact"]["new_banner_present"]
                     and rep["image"]["sha_ok"] and rep["image"]["is_0xa0000"]
                     and rep["image"]["header_magic_128s"] and rep["image"]["header_diff_only_length"]
                     and rep["image"]["payload_matches_uboot"]
                     and rep["image"]["tail_ff"] and rep["vendor_ram"]["ok"]
                     and rep["baseline"]["ok"] and rep["baseline"]["env_block_ok"]
                     and rep["old_image"]["ok"] and rep["clean_old_image_ok"]
                     and "via " not in route and chain["supervisor_pids"] and chain["bootwatch_pids"]
                     and chain["tty_holders"] and rep["vendor_pw_mode"] == "0o600")
    with open(args.out_dir + "/preflight.json", "w") as fh:
        json.dump(rep, fh, indent=1)
    print(json.dumps(rep, indent=1))
    log("preflight ok=" + str(rep["ok"]) + " expected_after=" + rep["expected_after"]["sha256"])
    return 0 if rep["ok"] else 2


def run_session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/session-driver.log"
    b1.make_askpass()
    with open(outdir + "/preflight.json") as fh:
        pre = json.load(fh)
    art = read_file(ART_UBOOT)
    image = read_file(ART_IMAGE)
    vendor = read_file(VENDOR_RAM)
    base_img = read_file(BASELINE)
    envblk = base_img[ENV_OFF:ENV_OFF + ENV_SIZE]
    expected_after = pre["expected_after"]["sha256"]
    results = {"mode": "c1b2-session-b-v3", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "outdir": outdir, "artifact": pre["artifact"], "image": pre["image"],
               "vendor_ram": pre["vendor_ram"],
               "expected_after_sha256": expected_after,
               "pre_mtd0_sha256": pre.get("device", {}).get("mtd0_sha256")}
    c = None
    try:
        if not pre.get("ok"):
            raise RuntimeError("preflight is not ok; refusing any flash operation")
        results["capture_before"] = base.pause_capture()
        if not results["capture_before"].get("free"):
            raise RuntimeError("tty busy after pausing capture")
        results["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        json.dump(results, open(outdir + "/session-results.json", "w"), indent=1)
        if args.start_mode == "ssh-reboot":
            link = b1.ensure_direct_link()
            results["reboot_link"] = link
            if not link.get("ok"):
                raise RuntimeError("no direct link to 192.168.1.1 for the reboot")
            rc, out, err = b1.ssh_run("sync; (sleep 1; reboot -f) &", 40)
            results["reboot_sent"] = {"rc": rc, "stdout": out[-300:], "stderr": err[-300:]}
            log("REBOOT SENT (ssh reboot -f); waiting for the flash chain")
        else:
            log("READY FOR USER POWER CYCLE (Session B: env restore + v3 image write, 2 erases + 2 writes)")
        if not enter_flash_console(c, results, args.entry_timeout):
            raise RuntimeError("could not stop autoboot at our flash U-Boot prompt")
        ver = send(c, results, "version", 60)
        results["flash_version_ok"] = bool(ver and OLD_BANNER.encode() in ver)
        if not results["flash_version_ok"]:
            raise RuntimeError("flash U-Boot version mismatch")
        log("gate: old flash console ready")
        lxv = fin.xmodem_cmd(c, results, VENDOR_RAM, "loadx 0x47f00000\r", 1024)
        results["vendor_loadx"] = lxv
        if not lxv.get("ok"):
            raise RuntimeError("loadx of the vendor U-Boot RAM image failed")
        results["md_vendor_head"] = fin.md_check(c, results, "vendor-ram-head", BOOT_ADDR, vendor[:0x1000])
        results["md_vendor_tail"] = fin.md_check(c, results, "vendor-ram-tail",
                                                 BOOT_ADDR + len(vendor) - 0x1000, vendor[-0x1000:])
        if not (results["md_vendor_head"]["ok"] and results["md_vendor_tail"]["ok"]):
            raise RuntimeError("vendor U-Boot RAM image md verification failed")
        log("gate: vendor U-Boot RAM image verified; go 0x47f00000")
        send_go(c, results)
        vc = base.enter_vendor_console(c, 180)
        results["vendor_console"] = vc
        if not vc.get("ok"):
            raise RuntimeError("vendor console entry failed: " + json.dumps(vc))
        log("gate: vendor console ready (stock U-Boot 2013.04)")
        lx = base.xmodem_load(c, ART_UBOOT, addr=BOOT_ADDR)
        results["vendor_xmodem"] = lx
        if not lx.get("ok"):
            raise RuntimeError("vendor xmodem of the v3 u-boot.bin failed")
        results["md_new_head"] = fin.md_check(c, results, "v3-uboot-head", BOOT_ADDR, art[:0x1000])
        results["md_new_tail"] = fin.md_check(c, results, "v3-uboot-tail",
                                              BOOT_ADDR + len(art) - 0x1000, art[-0x1000:])
        if not (results["md_new_head"]["ok"] and results["md_new_tail"]["ok"]):
            raise RuntimeError("v3 u-boot.bin md verification failed")
        log("gate: v3 u-boot.bin in RAM verified; go 0x47f00000 into our v3 console")
        send_go(c, results)
        results["v3_stop_autoboot"] = fin.stop_autoboot(c, results, NEW_BANNER, 60)
        ver3 = send(c, results, "version", 60)
        results["v3_banner_ok"] = bool(ver3 and NEW_BANNER.encode() in ver3)
        if not results["v3_banner_ok"]:
            raise RuntimeError("v3 banner gate failed")
        log("gate: our v3 console ready (" + NEW_BANNER + ")")
        envpath = outdir + "/target-env-block.bin"
        lxe = fin.xmodem_cmd(c, results, envpath, "loadx 0x46000000\r", 1024)
        results["env_loadx"] = lxe
        if not lxe.get("ok"):
            raise RuntimeError("loadx of the env block failed")
        results["env_md_in_ram"] = fin.md_check(c, results, "env-block-in-ram", RAM_ENV, envblk)
        if not results["env_md_in_ram"]["ok"]:
            raise RuntimeError("env block md verification failed; refusing to erase")
        log("gate: env block in RAM verified")
        eout = send(c, results, "mtd erase spi-nand0 0xc0000 0x20000", 300)
        etxt = eout.decode("latin-1", "replace")
        results["env_erase"] = {"tail": etxt[-800:],
                                "ok": ("Erasing 0x000c0000" in etxt and "(1 eraseblock(s))" in etxt
                                       and "Failure" not in etxt and "ERROR" not in etxt)}
        log("ENV ERASE sent; ok=" + str(results["env_erase"]["ok"]))
        if not results["env_erase"]["ok"]:
            raise RuntimeError("env erase did not report the expected block")
        okff = read_region(c, results, "env-post-erase", RAM_READ, ENV_OFF, ENV_SIZE)
        results["env_md_ff"] = fin.md_check(c, results, "env-post-erase-all-ff", RAM_READ, b"\xff" * ENV_SIZE)
        if not okff or not results["env_md_ff"]["ok"]:
            raise RuntimeError("env post-erase readback failed or not all 0xFF")
        log("gate: env post-erase ALL FF")
        wout = send(c, results, "mtd write spi-nand0 0x46000000 0xc0000 0x20000", 420)
        wtxt = wout.decode("latin-1", "replace")
        results["env_write"] = {"tail": wtxt[-800:],
                                "ok": ("Writing 131072 byte(s) (64 page(s)) at offset 0x000c0000" in wtxt
                                       and "Failure while writing" not in wtxt and "failed with error" not in wtxt)}
        log("ENV WRITE sent; ok=" + str(results["env_write"]["ok"]))
        if not results["env_write"]["ok"]:
            raise RuntimeError("env write did not report a clean 64-page write")
        okrb = read_region(c, results, "env-readback", RAM_READ, ENV_OFF, ENV_SIZE)
        results["env_md_readback"] = fin.md_check(c, results, "env-readback", RAM_READ, envblk)
        if not okrb:
            raise RuntimeError("env post-write read FAILED (explicit success assertion)")
        if not results["env_md_readback"]["ok"]:
            raise RuntimeError("env post-write readback mismatch")
        log("gate: env readback SUCCESS and md == baseline env block (6e2c01da...)")
        okboot = read_region(c, results, "pre-secondboot", RAM_BOOT, 0, FLASH_OFF)
        results["md_secondboot"] = fin.md_check(c, results, "secondboot-baseline", RAM_BOOT, base_img[:FLASH_OFF])
        lxi = fin.xmodem_cmd(c, results, ART_IMAGE, "loadx 0x44000000\r", 1024)
        results["image_loadx"] = lxi
        if not lxi.get("ok"):
            raise RuntimeError("loadx of the v3 mtd0 image failed")
        results["image_md"] = fin.md_check(c, results, "new-image-in-ram", RAM_IMAGE, image)
        if not results["image_md"]["ok"]:
            raise RuntimeError("new mtd0 image md verification failed; refusing to erase")
        results["env_restore_verified"] = bool(okboot and results["md_secondboot"]["ok"])
        log("ENV RESTORED (mtd0 back at the clean baseline); starting the v3 image ladder")
        eout2 = send(c, results, "mtd erase spi-nand0 0x20000 0xa0000", 300)
        etxt2 = eout2.decode("latin-1", "replace")
        results["image_erase"] = {"tail": etxt2[-800:],
                                  "ok": ("Erasing 0x00020000" in etxt2 and "(5 eraseblock(s))" in etxt2
                                         and "Failure" not in etxt2 and "ERROR" not in etxt2)}
        log("IMAGE ERASE sent; ok=" + str(results["image_erase"]["ok"]))
        if not results["image_erase"]["ok"]:
            raise RuntimeError("image erase did not report 5 erase blocks")
        okff2 = read_region(c, results, "image-post-erase", RAM_READ, FLASH_OFF, IMAGES_AREA)
        results["image_md_ff"] = fin.md_check(c, results, "image-post-erase-all-ff", RAM_READ, b"\xff" * IMAGES_AREA)
        if not okff2 or not results["image_md_ff"]["ok"]:
            raise RuntimeError("image post-erase readback failed or not all 0xFF; refusing to write")
        log("gate: image post-erase ALL FF")
        wout2 = send(c, results, "mtd write spi-nand0 0x44000000 0x20000 0xa0000", 420)
        wtxt2 = wout2.decode("latin-1", "replace")
        results["image_write"] = {"tail": wtxt2[-1000:],
                                  "ok": ("Writing 655360 byte(s) (320 page(s)) at offset 0x00020000" in wtxt2
                                         and "Failure while writing" not in wtxt2 and "failed with error" not in wtxt2)}
        log("IMAGE WRITE sent; ok=" + str(results["image_write"]["ok"]))
        if not results["image_write"]["ok"]:
            raise RuntimeError("image write did not report a clean 320-page write")
        okrb2 = read_region(c, results, "image-readback", RAM_READ, FLASH_OFF, IMAGES_AREA)
        results["image_md_readback"] = fin.md_check(c, results, "image-readback", RAM_READ, image)
        if not okrb2:
            raise RuntimeError("image post-write read FAILED (explicit success assertion)")
        if not results["image_md_readback"]["ok"]:
            raise RuntimeError("image post-write readback mismatch")
        log("gate: image readback SUCCESS and md == v3 image")
        okenv = read_region(c, results, "post-env", RAM_ENV, ENV_OFF, ENV_SIZE)
        okboot2 = read_region(c, results, "post-secondboot", RAM_BOOT, 0, FLASH_OFF, 240)
        oktail = read_region(c, results, "post-tail", RAM_READ, TAIL_OFF, 0x20000, 240)
        results["md_env_after"] = fin.md_check(c, results, "env-after-image-write", RAM_ENV, envblk)
        results["md_secondboot_after"] = fin.md_check(c, results, "secondboot-after-image-write", RAM_BOOT, base_img[:FLASH_OFF])
        results["md_tail_after"] = fin.md_check(c, results, "tail-after-image-write", RAM_READ, base_img[TAIL_OFF:0x100000])
        cmpout = send(c, results, "cmp 0x%08x 0x%08x 0x%x" % (RAM_IMAGE, RAM_READ, IMAGES_AREA), 240)
        results["readback_cmp"] = (cmpout or b"")[-600:].decode("latin-1", "replace")
        results["write_verified"] = bool(okenv and okboot2 and oktail and results["md_env_after"]["ok"]
                                         and results["md_secondboot_after"]["ok"] and results["md_tail_after"]["ok"]
                                         and "were the same" in results["readback_cmp"])
        if not results["write_verified"]:
            raise RuntimeError("post-write env/secondboot/tail verification failed")
        results["vendor_leg_ok"] = bool(results.get("vendor_loadx", {}).get("ok")
                                        and results.get("vendor_console", {}).get("ok")
                                        and results.get("vendor_xmodem", {}).get("ok")
                                        and results.get("v3_banner_ok"))
        log("WRITE VERIFIED. HOLDING (no reset).")
        log("READY FOR POWER CYCLE (Session C): expected mtd0 sha256 " + expected_after)
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
            results["capture_after"] = {"ok": False, "error": repr(exc)}
        cmds = results.get("commands", [])
        results["write_audit"] = {
            "mtd_erases": [x for x in cmds if x.startswith("mtd erase")],
            "mtd_writes": [x for x in cmds if x.startswith("mtd write")],
            "forbidden": [x for x in cmds if re.search(r"nand |saveenv|upgrade|tftp|bootm|setenv|mw\.", x)],
        }
        results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        results["verdict"] = "B-WRITE-GREEN-HOLD" if (
            results.get("env_restore_verified") and results.get("write_verified")
            and results.get("vendor_leg_ok")
            and (results.get("env_erase") or {}).get("ok") and (results.get("env_write") or {}).get("ok")
            and (results.get("env_md_readback") or {}).get("ok")
            and (results.get("image_erase") or {}).get("ok") and (results.get("image_write") or {}).get("ok")
            and (results.get("image_md_readback") or {}).get("ok")
            and (results.get("capture_after") or {}).get("ok")
            and len(results["write_audit"]["mtd_erases"]) == 2
            and len(results["write_audit"]["mtd_writes"]) == 2
            and not results["write_audit"]["forbidden"] and not results.get("error")) else "FAIL"
        json.dump(results, open(outdir + "/session-results.json", "w"), indent=1)
        log("VERDICT " + results["verdict"])
    return 0 if results["verdict"] == "B-WRITE-GREEN-HOLD" else 2


def selftest():
    ok = True
    for cmd in ["version", "md.l 0xc00100 1", "mtd read spi-nand0 0x45000000 0xc0000 0x20000",
                "mtd erase spi-nand0 0xc0000 0x20000", "mtd write spi-nand0 0x46000000 0xc0000 0x20000",
                "mtd erase spi-nand0 0x20000 0xa0000", "mtd write spi-nand0 0x44000000 0x20000 0xa0000",
                "loadx 0x46000000", "loadx 0x47f00000", "go 0x47f00000",
                "cmp 0x44000000 0x45000000 0xa0000"]:
        if not check_command(cmd):
            ok = False
            print("FAIL should allow: " + cmd)
    for cmd in ["mtd write spi-nand0 0x44000000 0x0 0xa0000", "mtd erase spi-nand0 0x0 0x20000",
                "nand erase 0x0 0x20000", "saveenv", "mw.l 0xc00100 0", "bootm 0x40008000",
                "setenv a b", "go 0x43000000", "go 0x40008000"]:
        if check_command(cmd):
            ok = False
            print("FAIL should deny: " + cmd)
    print("SELFTEST OK" if ok else "SELFTEST FAILED")
    return 0 if ok else 2


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    ap.add_argument("--start-mode", choices=["ssh-reboot", "cold"], default="ssh-reboot")
    ap.add_argument("--entry-timeout", type=int, default=1800)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.preflight:
        return preflight(args)
    return run_session(args)


if __name__ == "__main__":
    sys.exit(main())
