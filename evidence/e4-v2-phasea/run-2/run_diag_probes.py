#!/usr/bin/env python3
import hashlib, json, os, re, subprocess, time, sys

OUT = "/home/qc233/zte/e2631-p3/e2/e4-v2-phasea/run-2"
IFACE = "192.168.1.191"
URL = "http://192.168.1.1"
LOG = os.path.join(OUT, "serial.log")

def curl_get(name, path, timeout=180):
    hdr = os.path.join(OUT, name + ".hdr")
    body = os.path.join(OUT, name + ".body")
    cmd = ["curl", "-4", "--noproxy", "*", "-sS", "--max-time", str(timeout),
           "--interface", IFACE, "-D", hdr, "-o", body, URL + path]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 20)
    rec = {"name": name, "path": path, "rc": p.returncode,
           "stderr": (p.stderr or "")[:500], "elapsed_s": round(time.time()-t0, 3),
           "hdr": hdr, "body": body}
    try:
        hb = open(hdr, "rb").read().decode("latin-1")
    except FileNotFoundError:
        hb = ""
    try:
        bb = open(body, "rb").read()
    except FileNotFoundError:
        bb = b""
    rec["headers"] = hb
    rec["body_len"] = len(bb)
    rec["body_sha256"] = hashlib.sha256(bb).hexdigest() if bb else None
    m = re.search(r"HTTP/1\.[01] (\d{3})", hb)
    rec["status"] = int(m.group(1)) if m else None
    rec["body_text"] = bb.decode("latin-1")[:1200]
    return rec

def header(rec, name):
    m = re.search(r"(?im)^" + re.escape(name) + r":\s*(.+?)\s*$", rec.get("headers") or "")
    return m.group(1) if m else None

def post_file(name, path, body_path, timeout=300):
    hdr = os.path.join(OUT, name + ".hdr")
    body = os.path.join(OUT, name + ".body")
    cmd = ["curl", "-4", "--noproxy", "*", "-sS", "--max-time", str(timeout),
           "--interface", IFACE, "-D", hdr, "-o", body,
           "-H", "Content-Type: application/octet-stream",
           "--data-binary", "@" + body_path, URL + path]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)
    hb = open(hdr, "rb").read().decode("latin-1") if os.path.exists(hdr) else ""
    bb = open(body, "rb").read() if os.path.exists(body) else b""
    m = re.search(r"HTTP/1\.[01] (\d{3})", hb)
    return {"name": name, "path": path, "rc": p.returncode,
            "stderr": (p.stderr or "")[:500], "elapsed_s": round(time.time()-t0, 3),
            "hdr": hdr, "body": body, "headers": hb, "status": int(m.group(1)) if m else None,
            "body_len": len(bb), "body_sha256": hashlib.sha256(bb).hexdigest() if bb else None,
            "body_text": bb.decode("latin-1")[:1200]}

def serial_size():
    return os.path.getsize(LOG) if os.path.exists(LOG) else 0

def serial_since(off):
    try:
        with open(LOG, "rb") as f:
            f.seek(off)
            return f.read().decode("latin-1", "replace")
    except FileNotFoundError:
        return ""

def main():
    os.makedirs(OUT, exist_ok=True)
    res = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "steps": []}
    off = serial_size()
    res["serial_offset_start"] = off

    # status before
    st = curl_get("diag-status-before", "/status")
    res["status_before"] = st
    res["steps"].append({"step": "status_before", "status": st["status"], "body": st["body_text"]})

    # backup twice
    bk = []
    for i in (1, 2):
        r = curl_get("diag-bk%d" % i, "/backup?part=bootloader", timeout=240)
        r["hdr_crc"] = header(r, "X-E2631-CRC32")
        r["hdr_sha"] = header(r, "X-E2631-SHA256")
        r["hdr_len"] = header(r, "Content-Length")
        bk.append(r)
        res["steps"].append({"step": "backup%d" % i, "status": r["status"],
                             "hdr_crc": r["hdr_crc"], "hdr_sha": r["hdr_sha"],
                             "body_sha256": r["body_sha256"], "body_len": r["body_len"]})
    res["backup"] = bk

    st2 = curl_get("diag-status-after-backup", "/status")
    res["status_after_backup"] = st2
    res["steps"].append({"step": "status_after_backup", "status": st2["status"], "body": st2["body_text"]})

    # known 532-byte payload
    p532 = os.path.join(OUT, "p532.bin")
    data = bytes(i & 0xff for i in range(532))
    open(p532, "wb").write(data)
    res["p532"] = {"path": p532, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    posts = []
    for i in (1, 2):
        before = serial_size()
        r = post_file("diag-p532-%d" % i, "/firmware?mode=validate&slot=auto", p532, timeout=300)
        time.sleep(0.6)
        r["serial"] = serial_since(before)
        posts.append(r)
        res["steps"].append({"step": "p532_%d" % i, "status": r["status"],
                             "body": r["body_text"], "serial": r["serial"][-800:]})
    res["p532_posts"] = posts

    st3 = curl_get("diag-status-after-p532", "/status")
    res["status_after_p532"] = st3
    res["steps"].append({"step": "status_after_p532", "status": st3["status"], "body": st3["body_text"]})

    # six status requests back-to-back
    statuses = []
    for i in range(1, 7):
        r = curl_get("diag-status-%d" % i, "/status", timeout=120)
        statuses.append({"n": i, "status": r["status"], "rc": r["rc"],
                         "body_len": r["body_len"], "body_sha256": r["body_sha256"],
                         "body": r["body_text"], "stderr": r["stderr"]})
        time.sleep(0.3)
    res["status_series"] = statuses

    # serial tail, received lines and abort markers
    time.sleep(1.0)
    tail = serial_since(off)
    res["serial_tail"] = tail[-12000:]
    res["received_lines"] = re.findall(r"e2631rescue: received [^\r\n]+", tail)
    res["abort_lines"] = [x for x in tail.splitlines() if any(k in x for k in ("data abort", "prefetch abort", "Resetting CPU", "rescue: FAIL", "e2631rescue: FAIL"))]
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    json.dump(res, open(os.path.join(OUT, "diag-probes.json"), "w"), indent=1)
    # concise stdout
    print(json.dumps({
        "backup": [{k: x.get(k) for k in ("status","hdr_crc","hdr_sha","hdr_len","body_sha256","body_len")} for x in bk],
        "status_before": st["body_text"], "status_after_backup": st2["body_text"],
        "p532_sha": res["p532"]["sha256"],
        "p532_posts": [{"status": x["status"], "body": x["body_text"], "serial": x["serial"][-500:]} for x in posts],
        "received_lines": res["received_lines"], "abort_lines": res["abort_lines"],
        "status_series": [{"n": x["n"], "status": x["status"], "len": x["body_len"], "sha": x["body_sha256"]} for x in statuses],
        "serial_tail": tail[-3000:],
    }, indent=1)[:12000])

if __name__ == "__main__":
    main()
