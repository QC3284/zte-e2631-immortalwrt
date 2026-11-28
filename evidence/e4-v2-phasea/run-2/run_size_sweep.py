#!/usr/bin/env python3
import hashlib, json, os, re, subprocess, time
OUT="/home/qc233/zte/e2631-p3/e2/e4-v2-phasea/run-2"
IFACE="192.168.1.191"; URL="http://192.168.1.1"; LOG=OUT+"/serial.log"
EXP={532:"7d9ce3f2824cb3aabd7c327a39cd625ccaa5615db24b2a2aa8bf547a0ea6f90e",
     65536:"7daca2095d0438260fa849183dfc67faa459fdf4936e1bc91eec6b281b27e4c2",
     1048576:"fbbab289f7f94b25736c58be46a994c441fd02552cc6022352e3d86d2fab7c83",
     4194304:"2b07811057df887086f06a67edc6ebf911de8b6741156e7a2eb1416a4b8b1b2e"}
def size(): return os.path.getsize(LOG) if os.path.exists(LOG) else 0
def since(off):
    with open(LOG,"rb") as f: f.seek(off); return f.read().decode("latin-1","replace")
def gen(n):
    p=os.path.join(OUT,"p%d.bin"%n)
    if not os.path.exists(p): open(p,"wb").write(bytes(i&0xff for i in range(n)))
    return p
def post(n):
    p=gen(n); hdr=os.path.join(OUT,"diag-p%d.hdr"%n); body=os.path.join(OUT,"diag-p%d.body"%n)
    off=size()
    cmd=["curl","-4","--noproxy","*","-sS","--max-time","300","--interface",IFACE,
         "-D",hdr,"-o",body,"-H","Content-Type: application/octet-stream","-H","Expect:",
         "--data-binary","@"+p,URL+"/firmware?mode=validate&slot=auto"]
    t0=time.time(); q=subprocess.run(cmd,capture_output=True,text=True,timeout=330)
    time.sleep(0.8)
    hb=open(hdr,"rb").read().decode("latin-1") if os.path.exists(hdr) else ""
    bb=open(body,"rb").read() if os.path.exists(body) else b""
    m=re.search(r"HTTP/1\.[01] (\d{3})",hb)
    ser=since(off)
    rec={"n":n,"rc":q.returncode,"status":int(m.group(1)) if m else None,
         "elapsed_s":round(time.time()-t0,3),"body":bb.decode("latin-1")[:500],
         "serial":ser[-1000:],
         "received":re.findall(r"e2631rescue: received [^\r\n]+",ser),
         "abort":[x for x in ser.splitlines() if any(k in x for k in ("data abort","Resetting CPU","prefetch abort"))]}
    return rec
res=[]
for n in (532,65536,1048576,4194304):
    r=post(n); r["expected"]=EXP[n]; res.append(r)
    print(json.dumps({k:r[k] for k in ("n","status","elapsed_s","body","received","abort")},ensure_ascii=False))
    if r["abort"]: break
print("EXPECTED",json.dumps(EXP))
json.dump(res,open(os.path.join(OUT,"diag-sizes.json"),"w"),indent=1)
