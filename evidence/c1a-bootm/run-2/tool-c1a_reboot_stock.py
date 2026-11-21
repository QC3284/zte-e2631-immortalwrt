import sys, time, json
sys.path.insert(0,"/home/qc233/zte/e2631-p3")
import b1_env_session as b1
print("route", b1.ensure_direct_link())
rc,out,err=b1.ssh_run("sync; (sleep 1; reboot -f) >/dev/null 2>&1 &", 30)
print("reboot_rc", rc, "out", out[-200:], "err", err[-200:])