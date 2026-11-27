import sys, time, json, os
P3 = "/home/qc233/zte/e2631-p3"
sys.path.insert(0, P3)
import a1_banner_accept as base
import c1b1_final as fin

out = "/home/qc233/zte/e2631-p3/e2/session2/ramtest"
os.makedirs(out, exist_ok=True)
base.LOG = out + "/driver.log"
res = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "commands": {}}
c = None
try:
    res["pause"] = base.pause_capture()
    base.start_hub(out + "/serial.log")
    c = base.Console()
    time.sleep(0.4)
    c.drain()
    attach = False
    for i in range(5):
        c.send(b"\r")
        if fin.wait_prompt(c, 8) is not None:
            attach = True
            break
        time.sleep(0.5)
    res["attach"] = attach
    print("ATTACH " + str(attach), flush=True)
    cmds = [
        "version",
        "md 0x46000000 4",
        "mw 0x46000000 0xdeadbeef 4",
        "md 0x46000000 4",
        "mw 0x46000000 0 4",
        "md 0x46000000 4",
        "md.l 0x47f00000 8",
        "mtd read spi-nand0 0x44000000 0x0 0x800",
        "md.l 0x44000000 8",
        "mtd read spi-nand0 0x44100000 0x20000 0x800",
        "md.l 0x44100000 8",
        "mtd read spi-nand0 0x44200000 0x2300000 0x800",
        "md.l 0x44200000 8",
        "mtd read spi-nand0 0x44300000 0x2400000 0x800",
        "md.l 0x44300000 8",
        "mtd read spi-nand0 0x44400000 0x700000 0x800",
        "md.l 0x44400000 8",
        "e2631boot load",
        "md.l 0x42000000 8",
        "md.l 0x420020 8",
        "md.l 0x420060 8",
        "iminfo 0x420020",
        "crc32 0x42000000 0x35454a",
        "crc32 0x420020 0x40",
        "md.l 0x46000000 4",
    ]
    for cmd in cmds:
        c.pending = b""
        c.send((cmd + "\r").encode())
        outp = fin.wait_prompt(c, 120)
        txt = (outp or b"").decode("latin-1", "replace")
        res["commands"][cmd] = {"t": time.strftime("%H:%M:%S"), "out": txt}
        print("CMD " + cmd, flush=True)
        print(txt[-1500:], flush=True)
    res["ended"] = time.strftime("%Y-%m-%d %H:%M:%S")
finally:
    try:
        if c is not None:
            open(out + "/console-history.txt", "wb").write(bytes(c.history))
    except Exception as e:
        res["history_error"] = repr(e)
    try:
        base.stop_hub()
    except Exception as e:
        res["stop_hub_error"] = repr(e)
    try:
        res["capture_after"] = base.restore_capture()
    except Exception as e:
        res["restore_error"] = repr(e)
    json.dump(res, open(out + "/result.json", "w"), indent=1)
    print("capture_after=" + json.dumps(res.get("capture_after")), flush=True)
    print("DONE", flush=True)
