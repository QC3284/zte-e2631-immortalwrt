# E4 rescue acceptance — run-1 (validate-only, RED)

Evidence for `evidence/e4-rescue-acceptance-20261128.md`.

F2-fixed artifact: CI run 46030383958, banner `U-Boot 2027.01-rc2-gd38f69c44523`,
u-boot.bin sha256 `e87a8580...`, 32 patches, tree `ae723347...`.

Session 2026-11-28 00:29:44–00:31:39 CST: userdata staging -> RAM load ->
e2631rescue. GET / and GET /status PASS; POST /flash?mode=validate returns
HTTP 400 `unsupported request` because of the rescue header-name case bug
(see root-cause-rescue-header-bug.txt). RX is proven by the tcpdump capture.
Zero mtd0 writes; F1 `e2631boot` started the kernel.

Files: preflight.txt, serial.txt, console-history.txt, tcpdump.txt,
tcpdump-http-lines.txt, page.headers.txt, page.body.gz, page.html,
page-asset-sha256.txt, status-initial.body.txt, validate.headers.txt,
validate.body.txt, status-after-validate.body.txt, session-results.json,
driver.txt, tool-e4_rescue_accept.py, artifact-SHA256SUMS.txt,
artifact-UBOOT-INFO.txt, root-cause-rescue-header-bug.txt,
netzero-payload.txt, SHA256SUMS.txt.
