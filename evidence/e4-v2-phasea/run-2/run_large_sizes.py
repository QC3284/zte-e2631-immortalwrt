#!/usr/bin/env python3
import hashlib, json, os, re, subprocess, time
OUT="/home/qc233/zte/e2631-p3/e2/e4-v2-phasea/run-2"; IFACE="192.168.1.191"; URL="http://192.168.1.1"; LOG=OUT+"/serial.log"
def size(): return os.path.getsize(LOG) if os.path.exists(LOG) else 0
def since(off):
    with open(LOG,"rb") as f: f.seek(off); return f.read().decode("latin-1","replace")
def gen(n):
    p=os.path.join(OUT,"p%d.bin"%n)
    open(p,"wb").write(bytes(i&0xff for i in range(n)))
    return p
res=[]
for n in (8388608,16777216,22020628):
    p=gen(n); exp=hashlib.sha256(open(p,"rb").read()).hexdigest()
    hdr=os.path.join(OUT,"diag-p%d.hdr"%n); body=os.path.join(OUT,"diag-p%d.body"%n); off=size()
    cmd=["curl","-4","--noproxy","*","-sS","--max-time","600","--interface",IFACE,
         "-D",hdr,"-o",body,"-H","Content-Type: application/octet-stream","-H","Expect:",
         "--data-binary","@"+p,URL+"/firmware?mode=validate&slot=auto"]
    t0=time.time(); q=subprocess.run(cmd,capture_output=True,text=True,timeout=630)
    time.sleep(1.0)
    hb=open(hdr,"rb").read().decode("latin-1") if os.path.exists(hdr) else ""
    bb=open(body,"rb").read() if os.path.exists(body) else b""
    m=re.search(r"HTTP/1\.[01] (\d{3})",hb); ser=since(off)
    rec={"n":n,"expected":exp,"rc":q.returncode,"status":int(m.group(1)) if m else None,
         "elapsed_s":round(time.time()-t0,3),"body":bb.decode("latin-1")[:500],
         "received":re.findall(r"e2631rescue: received [^\r\n]+",ser),
         "abort":[x for x in ser.splitlines() if any(k in x for k in ("data abort","Resetting CPU","prefetch abort"))]}
    res.append(rec)
    print(json.dumps(rec,ensure_ascii=False))
    if rec["abort"]: break
json.dump(res,open(os.path.join(OUT,"diag-large-sizes.json"),"w"),indent=1)
