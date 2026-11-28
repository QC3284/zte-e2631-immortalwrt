#!/bin/sh
# SPDX-License-Identifier: GPL-2.0+
#
# Static contract fixture for the task-99 fixes (patches 0062-0064).
#
# The pure parts (line copy, refclk state) have host fixtures; this check
# pins the wiring that cannot be linked on the host: every telnet session
# exit path releases the shared console slot, the refclock detector runs
# before any reprogramming, and the rescue network pins the DNS answer and
# repairs a changed net_ip.
#
# usage: uboot-port/tests/task99_contract_test.sh <u-boot source dir>
set -eu

U=${1:?usage: task99_contract_test.sh <u-boot source dir>}
TELNETD=$U/net/mtk_telnetd.c
TELNETD_H=$U/include/net/mtk_telnetd.h
REFCLK=$U/board/zte/zxhn-e2631/e2631net.c
RESCUE=$U/board/zte/zxhn-e2631/e2631rescue.c
DNSD=$U/net/mtk_dnsd.c

fails=0
checks=0

need() {
	checks=$((checks + 1))
	if grep -qF -- "$2" "$1"; then
		return 0
	fi
	echo "FAIL: $3"
	fails=$((fails + 1))
}

need_absent() {
	checks=$((checks + 1))
	if grep -qF -- "$2" "$1"; then
		echo "FAIL: $3"
		fails=$((fails + 1))
	fi
}

ordered() {
	checks=$((checks + 1))
	first=$(grep -nF -- "$2" "$1" | head -n 1 | cut -d: -f1)
	second=$(grep -nF -- "$3" "$1" | head -n 1 | cut -d: -f1)
	if [ -n "$first" ] && [ -n "$second" ] && [ "$first" -lt "$second" ]; then
		return 0
	fi
	echo "FAIL: $4"
	fails=$((fails + 1))
}

# 1. The queued line is copied through the terminating helper, never by a
#    raw memcpy of line_len + 1 bytes (the stale-byte bug).
need "$TELNETD_H" "mtk_telnetd_copy_line" \
	"the telnet header exposes the line-copy helper"
need "$TELNETD" "mtk_telnetd_copy_line(telnetd.exec_line" \
	"the telnet poll copies the queued line through the helper"
need_absent "$TELNETD" "memcpy(telnetd.exec_line" \
	"the raw exec_line memcpy is gone"

# 2. Every session exit path funnels into telnetd_release_session(), which
#    restores the console record buffer before the memset.
need "$TELNETD" "static void telnetd_release_session(void)" \
	"the session release helper exists"
ordered "$TELNETD" "telnetd_finish_capture();" "telnetd_reset_session();" \
	"the release helper restores the capture before the reset"
need "$TELNETD" "if (telnetd.conn_dead && !telnetd.exec_active)" \
	"the poll loop releases a dead connection"
releases=$(grep -cF 'telnetd_release_session();' "$TELNETD")
checks=$((checks + 1))
if [ "$releases" -lt 4 ]; then
	echo "FAIL: only $releases session release call sites, expected 4"
	fails=$((fails + 1))
fi

# 3. The refclock setup detects an already programmed tree before touching
#    the pinmux, PLL or SerDes.
need "$REFCLK" "e2631_refclk_snapshot(&state);" \
	"the refclock code snapshots the registers"
need "$REFCLK" "e2631_refclk_is_ready(&state)" \
	"the refclock code checks the vendor state"
ordered "$REFCLK" "e2631_refclk_is_ready(&state)" "e2631_pinmux_gpio_init();" \
	"the refclock check runs before any reprogramming"

# 4. The rescue network retries eth_init and pins the DNS answer.
need "$RESCUE" "Ethernet start attempt %d failed, retrying" \
	"the rescue loop retries eth_init"
need "$RESCUE" "mtk_dnsd_set_answer(server_ip.s_addr);" \
	"the rescue network pins the DNS answer"
need "$RESCUE" "net_ip changed to %pI4, restoring %pI4" \
	"the rescue loop repairs a changed net_ip"

# 5. The DNS server answers from the pinned address and logs both values.
need "$DNSD" "dnsd_answer_pinned" \
	"the DNS server keeps a pinned answer"
need "$DNSD" "(net_ip %pI4)" \
	"the DNS log shows the answer and net_ip"

if [ "$fails" -ne 0 ]; then
	echo "task-99 contract fixture: FAIL ($fails of $checks checks)"
	exit 1
fi

echo "task-99 contract fixture: PASS ($checks checks)"
