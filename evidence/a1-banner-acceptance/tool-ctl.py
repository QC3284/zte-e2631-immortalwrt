#!/usr/bin/env python3
"""Tiny client for the serial hub control socket."""
import argparse, base64, json, socket, sys, time

SOCK = "/tmp/e2631-p3.sock"


def call(req, timeout=30.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(SOCK)
    f = s.makefile("rwb")
    f.write((json.dumps(req) + "\n").encode())
    f.flush()
    line = f.readline()
    s.close()
    return json.loads(line.decode())


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ping")
    p = sub.add_parser("read")
    p.add_argument("offset", type=int)
    p = sub.add_parser("wait")
    p.add_argument("pattern")
    p.add_argument("timeout", type=float)
    p.add_argument("offset", type=int, default=0, nargs="?")
    p.add_argument("--ignore-case", action="store_true")
    p = sub.add_parser("send-hex")
    p.add_argument("hex")
    p = sub.add_parser("send")
    p.add_argument("text")
    p.add_argument("--cr", action="store_true")
    p.add_argument("--lf", action="store_true")
    p = sub.add_parser("xmodem")
    p.add_argument("path")
    p.add_argument("--block-size", type=int, default=128)
    p = sub.add_parser("stop")
    args = ap.parse_args()
    if args.cmd == "ping":
        print(json.dumps(call({"op": "ping"})))
    elif args.cmd == "read":
        print(json.dumps(call({"op": "read", "offset": args.offset})))
    elif args.cmd == "send-hex":
        print(json.dumps(call({"op": "send", "data_b64": base64.b64encode(bytes.fromhex(args.hex)).decode()})))
    elif args.cmd == "send":
        data = args.text.encode()
        if args.cr:
            data += b"\r"
        if args.lf:
            data += b"\n"
        print(json.dumps(call({"op": "send", "data_b64": base64.b64encode(data).decode()})))
    elif args.cmd == "wait":
        import re
        off = args.offset
        deadline = time.time() + args.timeout
        pat = re.compile(args.pattern.encode(), re.I if args.ignore_case else 0)
        acc = b""
        while time.time() < deadline:
            r = call({"op": "read", "offset": off})
            off = r["offset"]
            acc += base64.b64decode(r["data_b64"])
            m = pat.search(acc)
            if m:
                print(json.dumps({"matched": True, "offset": off,
                                  "match": m.group(0).decode("latin-1"),
                                  "data_b64": base64.b64encode(acc).decode()}))
                return
            time.sleep(0.05)
        print(json.dumps({"matched": False, "offset": off, "data_b64": base64.b64encode(acc).decode()}))
    elif args.cmd == "xmodem":
        print(json.dumps(call({"op": "xmodem", "path": args.path, "block_size": args.block_size},
                              timeout=900.0)))
    elif args.cmd == "stop":
        print(json.dumps(call({"op": "stop"})))


if __name__ == "__main__":
    main()
