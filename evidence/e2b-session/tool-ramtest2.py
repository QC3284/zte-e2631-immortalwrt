import sys, time, json, os
P3 = "/home/qc233/zte/e2631-p3"
sys.path.insert(0, P3)
import a1_banner_accept as base
import c1b1_final as fin

out = "/home/qc233/zte/e2631-p3/e2/session2/ramtest2"
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
        "mtd read spi-nand0 0x48000000 0x2300000 0x800",
        "md 0x48000000 0x40",
        "mtd read spi-nand0 0x48100000 0x700000 0x800",
        "md 0x48100000 0x40",
        "mtd read spi-nand0 0x48200000 0x3800000 0x800",
        "md 0x48200000 0x40",
        "mtd read spi-nand0 0x42000000 0x2300000 0x800",
        "md 0x42000000 0x40",
        "crc32 0x420020 0x40",
        "e2631boot load",
        "md 0x420020 0x20",
        "md 0x420060 0x20",
        "crc32 0x420020 0x40",
        "md 0x480020 0x20",
        "crc32 0x480020 0x40",
    ]
    for cmd in cmds:
        c.pending = b""
        c.send((cmd + "\r").encode())
        outp = fin.wait_prompt(c, 120)
        txt = (outp or b"").decode("latin-1", "replace")
        res["commands"][cmd] = {"t": time.strftime("%H:%M:%S"), "out": txt}
        print("CMD " + cmd, flush=True)
        print(txt[-2500:], flush=True)
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
