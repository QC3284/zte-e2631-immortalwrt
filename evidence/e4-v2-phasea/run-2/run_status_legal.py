#!/usr/bin/env python3
import hashlib, json, os, re, subprocess, time
OUT="/home/qc233/zte/e2631-p3/e2/e4-v2-phasea/run-2"; IFACE="192.168.1.191"; URL="http://192.168.1.1"; LOG=OUT+"/serial.log"
def since(off):
    with open(LOG,"rb") as f: f.seek(off); return f.read().decode("latin-1","replace")
def get(name,path,timeout=180):
    hdr=os.path.join(OUT,name+".hdr"); body=os.path.join(OUT,name+".body")
    q=subprocess.run(["curl","-4","--noproxy","*","-sS","--max-time",str(timeout),"--interface",IFACE,"-D",hdr,"-o",body,URL+path],capture_output=True,text=True,timeout=timeout+20)
    hb=open(hdr,"rb").read().decode("latin-1") if os.path.exists(hdr) else ""
    bb=open(body,"rb").read() if os.path.exists(body) else b""
    m=re.search(r"HTTP/1\.[01] (\d{3})",hb)
    return {"name":name,"path":path,"rc":q.returncode,"status":int(m.group(1)) if m else None,
            "body_len":len(bb),"body_sha256":hashlib.sha256(bb).hexdigest() if bb else None,
            "body":bb.decode("latin-1")[:1500],"stderr":q.stderr[:500]}
# six statuses
sts=[]
for i in range(1,7):
    r=get("post-large-status-%d"%i,"/status",120); sts.append(r)
    print("status",i,r["status"],r["body_len"],r["body_sha256"],r["stderr"][:100])
# legal package with correct header
pkg="/home/qc233/zte/e2631-t5-artifacts/parity-ref/e2631-immortalwrt-experimental.bin"
sha="66805b26afa47b612e535ca0885fd088b0b37461c959fb75212548d30c58294d"
hdr=OUT+"/legal-validate.hdr"; body=OUT+"/legal-validate.body"; off=os.path.getsize(LOG)
cmd=["curl","-4","--noproxy","*","-sS","--max-time","600","--interface",IFACE,"-D",hdr,"-o",body,
     "-H","Content-Type: application/octet-stream","-H","Expect:","-H","X-E2631-SHA256: "+sha,
     "--data-binary","@"+pkg,URL+"/firmware?mode=validate&slot=auto"]
t0=time.time(); q=subprocess.run(cmd,capture_output=True,text=True,timeout=630); time.sleep(1.2)
hb=open(hdr,"rb").read().decode("latin-1") if os.path.exists(hdr) else ""
bb=open(body,"rb").read() if os.path.exists(body) else b""
m=re.search(r"HTTP/1\.[01] (\d{3})",hb); ser=since(off)
rec={"status":int(m.group(1)) if m else None,"elapsed_s":round(time.time()-t0,3),
     "body":bb.decode("latin-1")[:1500],"headers":hb[:1000],
     "received":re.findall(r"e2631rescue: received [^\r\n]+",ser),
     "abort":[x for x in ser.splitlines() if any(k in x for k in ("data abort","Resetting CPU","prefetch abort","panic"))],
     "serial_tail":ser[-3000:]}
print(json.dumps(rec,indent=1,ensure_ascii=False)[:6000])
json.dump({"statuses":sts,"legal":rec},open(os.path.join(OUT,"diag-status-legal.json"),"w"),indent=1)
