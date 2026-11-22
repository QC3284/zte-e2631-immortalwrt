#!/usr/bin/env python3
"""Reconstruct the expected post-Session-B mtd0 image and check its sha256.

Inputs (read-only):
  baseline  : clean mtd0 baseline, sha256 887a7f6c... (vendor boot area)
  v3 image  : A6 v3 mtd0 image, sha256 f6d179da..., 655,360 B
Writes: nothing. Prints region hashes for the record.
"""
import hashlib

BASELINE = "/home/qc233/zte/e2631-p3/b1-env-session/resume-1/target-mtd0.bin"
V3_IMAGE = "/home/qc233/zte/e2631-t5-artifacts/uboot-a6v3-44935007253/e2631-uboot-44935007253/e2631-uboot-mtd0.bin"
EXPECTED = "5ebb5ab323bafea4a310e4cb3f78cbb77b3d219ba9fb324927bf28e8d0cc48cf"


def sha(b):
    return hashlib.sha256(b).hexdigest()


base = open(BASELINE, "rb").read()
img = open(V3_IMAGE, "rb").read()
assert len(base) == 0x100000, len(base)
assert len(img) == 0xA0000, len(img)
print("baseline  :", sha(base))
for name, a, b in [("secondboot", 0x0, 0x20000), ("image-area-before", 0x20000, 0xC0000),
                   ("env-block", 0xC0000, 0xE0000), ("tail", 0xE0000, 0x100000)]:
    print("%-18s %s  %s" % (name, hex(a), sha(base[a:b])))
print("v3 image  :", sha(img))
out = bytearray(base)
out[0x20000:0xC0000] = img
got = sha(bytes(out))
print("reconstructed:", got)
print("expected     :", EXPECTED)
assert got == EXPECTED, "reconstruction mismatch"
print("OK: reconstruction matches the expected post-write mtd0 sha256")
