# patch 0034 cold-boot rescue ordering — device retest bundle (2026-11-28)

Corresponding evidence doc: ../e4-coldrescue-0034-20261128.md

Artifact: uboot-build run 46046018929 (34 patches, tree 0480ef83…), banner g1673d5c89c7b.
Method: stage 0034 u-boot.bin to userdata -> SSH reboot to the current flash E4 prompt ->
mtd read + crc32 0x9f2b707d -> go 0x47F00000 -> e2631rescue as the FIRST network command
(no e2631net, no e2631boot). Verified PHY autoneg done, lan1 up 1 Gbps, HTTP page, validate
200 result=ok sha_match=ok (crc32 0x1e5ff289), then Ctrl-C + e2631boot back to Linux.
mtd0 d87db54a… and region 8a38896e… unchanged; zero mtd0 writes.

Run history: run 1 failed in the driver at stop_autoboot because the banner had already been
consumed from the pending buffer (no device write); run 2 GREEN. Both stdout logs are included.

Limitation: this is warm-reset + RAM-load of 0034, not a cold boot of a flashed 0034 image.
The true cold acceptance follows the third write with fresh user approval.

Files:
- results.json, driver.txt, serial.txt, console-history.txt
- page/status/validate HTTP headers and bodies
- run1-stdout.txt (failed attempt), run2-stdout.txt (GREEN)
- tool-e4_coldrescue_0034.py
- artifact-SHA256SUMS.txt, artifact-UBOOT-INFO.txt
- SHA256SUMS.txt
