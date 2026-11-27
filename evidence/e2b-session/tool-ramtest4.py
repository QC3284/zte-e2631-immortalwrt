import sys, time, json, os
P3 = "/home/qc233/zte/e2631-p3"
sys.path.insert(0, P3)
import a1_banner_accept as base
import c1b1_final as fin

out = "/home/qc233/zte/e2631-p3/e2/session2/ramtest4"
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
        "crc32 0x47f00000 0x20",
        "crc32 0x47f00000 0x40",
        "md 0x47f00000 0x10",
        "mw 0x4a000000 0xa5a5a5a5 0x10",
        "md 0x4a000000 0x10",
        "md 0x4a000020 0x8",
        "mtd read spi-nand0 0x4b000000 0x2300000 0x800",
        "crc32 0x4b000000 0x20",
        "md 0x4b000000 0x10",
        "crc32 0x4b000000 0x20",
        "md 0x480020 0x8",
    ]
    for cmd in cmds:
        t0 = time.time()
        c.pending = b""
        c.send((cmd + "\r").encode())
        outp = fin.wait_prompt(c, 120)
        txt = (outp or b"").decode("latin-1", "replace")
        res["commands"][cmd] = {"dt": round(time.time() - t0, 2), "out": txt}
        print("CMD " + cmd + " (%.1fs)" % (time.time() - t0), flush=True)
        print(txt[-1600:], flush=True)
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
