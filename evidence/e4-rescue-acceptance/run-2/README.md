# E4 rescue acceptance — run-2 (patch 0033, validate + wrong-digest negative, PASS)

Artifact: `uboot-build` run 46036894542, 33 patches, tree
`cd67a0414737dcbb860072ddbaaf3de16a306b46`, banner
`U-Boot 2027.01-rc2-g30dca5f54503`, u-boot.bin 365,872 B sha256
`3dbbfc49...`, crc32 `0x34b252a4`, mtd0 image sha256 `8a38896e...`.

Session 2026-11-28 00:55:16–00:57:14 CST, RAM chain, zero mtd0 writes.

- GET /: 200 gzip 4456 B (sha `8f16817b...`), 9216 B decompressed
  (sha `30a8f03e...`) == repo page.
- GET /status initial: stage=idle, sha_match=absent.
- POST /flash?mode=validate: 200 `result=ok` + computed sha256
  `b1ea9a48...` + `sha_match=ok`; /status then shows crc32 `0x0721e716`,
  sha256/browser_sha256 `b1ea9a48...`, sha_match=ok, stage=idle.
- Negative: POST with X-E2631-SHA256 = 64 zeros -> 400
  `result=error error=sha256 mismatch`; /status stays stage=idle,
  sha_match=mismatch, no staging/write stage.
- F1: e2631boot -> KERNEL_STARTED 8.68 s; mtd0/region unchanged; env block
  `6e2c01da...`; fwslot slot1 serial 12 running / slot0 serial 7 intact.

Files: preflight-free session logs, serial.txt, console-history.txt, tcpdump.txt,
tcpdump-http-lines.txt, page.headers.txt/page.body.gz/page.html, /status and
validate response bodies (positive + wrong-sha), session-results.json, driver.txt,
tool-e4_rescue_accept.py, artifact-SHA256SUMS/UBOOT-INFO/FAILSAFE-ASSET,
SHA256SUMS.txt.
