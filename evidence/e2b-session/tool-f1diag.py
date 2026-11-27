import sys, time, json, os
P3 = "/home/qc233/zte/e2631-p3"
sys.path.insert(0, P3)
import a1_banner_accept as base
import c1b1_final as fin
out = "/home/qc233/zte/e2631-p3/e2/session2/f1diag"
os.makedirs(out, exist_ok=True)
base.LOG = out + "/driver.log"
state = base.pause_capture()
base.start_hub(out + "/serial.log")
c = base.Console()
time.sleep(0.4)
c.drain()
attach = False
for i in range(4):
    c.send(b"\r")
    if fin.wait_prompt(c, 8) is not None:
        attach = True
        break
    time.sleep(0.4)
cmds = ["version",
        "mtd read spi-nand0 0x43000000 0x2300000 0x1000",
        "md.l 0x43000000 8", "md.l 0x430020 8", "md.l 0x430040 8",
        "md.l 0x42000000 8", "md.l 0x420020 8",
        "crc32 0x430020 0x40", "crc32 0x420020 0x40"]
res = {"attach": attach, "commands": {}}
for cmd in cmds:
    c.pending = b""
    c.send((cmd + "\r").encode())
    outp = fin.wait_prompt(c, 90)
    txt = (outp or b"").decode("latin-1", "replace")
    res["commands"][cmd] = txt
    print("CMD " + cmd, flush=True)
    print(txt[-1500:], flush=True)
json.dump(res, open(out + "/result.json", "w"), indent=1)
open(out + "/console-history.txt", "wb").write(bytes(c.history))
base.stop_hub()
rep = base.restore_capture()
print("capture_after=" + json.dumps(rep), flush=True)