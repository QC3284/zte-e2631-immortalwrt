import sys, json, time
sys.path.insert(0,"/home/qc233/zte/e2631-p3")
import b1_env_session as b1
D="/home/qc233/zte/e2631-p3/c1a-bootm/run-2"
print("route", b1.ensure_direct_link())
rc,o,e=b1.ssh_run("sha256sum /dev/mtd0; cut -d. -f1 /proc/uptime; cat /etc/e2631-version; uname -r; dmesg | grep -ci panic; dmesg | grep -c mt7915e", 40)
print("ssh_rc", rc)
facts=[l.strip() for l in o.splitlines() if l.strip()]
print(facts)
log=open("/home/qc233/zte/e2631-serial-boot.log","rb").read().decode("latin-1","replace")
idx=log.rfind("Boot SPI NAND")
if idx<0: idx=log.rfind("U-Boot 2013.04")
seg=log[idx:] if idx>=0 else log[-20000:]
open(D+"/recovery-boot-segment.txt","w",errors="replace").write(seg)
keys=["Boot SPI NAND","start read bootheader","U-Boot 2013.04","cspboot: pdt_getimg","VFS: Mounted root","e2631-wifi-boot: MT7916 ready"]
res={"mode":"c1a-recovery-stock-chain","ssh_rc":rc,"facts":facts,
     "serial_segment_ok":bool(seg),"serial_segment_bytes":len(seg),
     "serial_markers":{k:(k in seg) for k in keys},
     "mtd0_after_recovery":facts[0].split()[0] if facts else None,
     "stock_chain_confirmed":("U-Boot 2013.04" in seg),
     "wifi_ready":("MT7916 ready" in seg)}
json.dump(res, open(D+"/recovery-stock-chain.json","w"), indent=1)
print(json.dumps(res, indent=1)[:2500])