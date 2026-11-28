#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0+
#
# E4 rescue-mode acceptance harness (task-75).
#
# Drives the browserless acceptance flow for the U-Boot rescue page
# (uboot-port/failsafe/e2631-failsafe.html, patch 0026) over the rescue
# network: page fetch, local image checks, a NET-ZERO validate run, the
# rejection matrix, and optionally the NET-ZERO write run.
#
# Default mode is VALIDATE-ONLY. The write phase requires BOTH --write and the
# approval token issued by the Lead:
#
#     --write --approval E4-RESCUE-WRITE-APPROVED
#
# Safety properties:
#   * the only image uploaded in mode=write is the --image file, re-verified
#     against EXPECTED_IMAGE_SHA immediately before the POST. The default is the
#     15-patch image region b1ea9a48..., but the target's own region digest must
#     be measured first (dd if=/dev/mtd0 bs=4096 skip=32 count=160 | sha256sum);
#     pass it explicitly with --expected-sha and never substitute a different image;
#   * every validate/write POST carries X-E2631-SHA256; v1 checks that digest
#     against the uploaded bytes, so a probe with a wrong digest must be
#     refused. The digest is still client-supplied (no pinned device-side
#     authority), which is why the image identity comes from --expected-sha;
#     without --require-digest an unenforced digest is reported as a loud
#     WARNING instead of being silently skipped;
#   * the image is the one the board already runs, so a successful write leaves
#     /dev/mtd0 byte-identical (net-zero acceptance);
#   * the harness never issues a reboot/reset: returning to Linux is a power
#     cycle, because the board's U-Boot reset_cpu() is currently a placeholder
#     (patch 0003; a real reset is task-76);
#   * the payload-flip case is INFORMATIONAL only: v1 has no device-side digest,
#     so a single flipped payload byte is not expected to be rejected. The
#     harness records the outcome as a known limitation and never writes that
#     image.
#
# Usage:
#   tools/e4-rescue-acceptance.sh --image <e2631-uboot-mtd0.bin> [options]
#   tools/e4-rescue-acceptance.sh --image ... --write --approval <TOKEN>
#
# Exit codes: 0 = all asserted checks passed; 1 = acceptance failure;
#             2 = precondition/environment error; 3 = write approval missing.
#
# See evidence/e4-rescue-acceptance-plan-20261127.md for the full plan.

set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)

DEFAULT_EXPECTED_IMAGE_SHA=b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a
EXPECTED_IMAGE_SHA=$DEFAULT_EXPECTED_IMAGE_SHA
EXPECTED_IMAGE_SIZE=655360
E4_APPROVAL_VALUE=E4-RESCUE-WRITE-APPROVED

HOST=192.168.1.1
IFACE=""
DO_DHCP=0
IMAGE=""
PAGE=""
ASSET_STATS=""
WRITE=0
APPROVAL=""
SKIP_MATRIX=0
REQUIRE_DIGEST=0
POLL_TIMEOUT=600
KEEP_TMP=0
V21=0
FW_PKG=""
BASE_URL=""
SKIP_LAN=0

TMP=""
PASS=0
FAIL=0
NOTES=0

log()  { printf '[e4-accept] %s\n' "$*"; }
note() { NOTES=$((NOTES + 1)); printf '[e4-accept] NOTE: %s\n' "$*"; }
pass() { PASS=$((PASS + 1)); printf '[e4-accept] PASS: %s\n' "$*"; }
failcase() {
	FAIL=$((FAIL + 1))
	printf '[e4-accept] FAIL: %s\n' "$*" >&2
	if [ -n "$TMP" ]; then printf '%s\n' "$*" >>"$TMP/failures.txt"; fi
}
fatal() { printf '[e4-accept] ERROR: %s\n' "$*" >&2; exit 2; }

usage() {
	printf '%s\n' "usage: tools/e4-rescue-acceptance.sh --image <file> [options]" "options:" "  --host IP           device address (default 192.168.1.1)" "  --iface IFACE       host interface on the rescue link" "  --dhcp              run dhclient -1 on --iface (needs root)" "  --page PATH         local page for the served-page comparison" "  --asset-stats PATH  E2631-FAILSAFE-ASSET.txt from the build artifact" "  --write             enable the NET-ZERO write phase" "  --approval TOKEN    required with --write: $E4_APPROVAL_VALUE" "  --skip-matrix       skip the rejection matrix" "  --expected-sha SHA  expected net-zero payload sha256 (default: the 15-patch image region b1ea9a48...)" "  --require-digest    fail if the device does not enforce X-E2631-SHA256" "  --timeout SECS      write-phase poll timeout (default 600)" "  --keep-tmp          keep temporary files" "  --v21               also run the v2.1 endpoint suite (read-only; needs --firmware-pkg)" "  --firmware-pkg PATH factory package .bin for the /firmware validate matrix" "  --base-url URL      override http://HOST (mock self-test: http://127.0.0.1:PORT)" "  --skip-lan          skip the 192.168.1.0/24 host check (only with --base-url)" "  -h, --help          this help"
	exit 0
}

cleanup() {
	if [ "$KEEP_TMP" = 1 ] && [ -n "$TMP" ]; then
		log "temporary files kept: $TMP"
	elif [ -n "$TMP" ]; then
		rm -rf "$TMP"
	fi
}
trap cleanup EXIT

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || fatal "missing required command: $1"
}

show() { if [ -n "$1" ]; then printf '%s' "$1"; else printf '<missing>'; fi; }
lc()   { printf '%s' "$1" | tr 'A-F' 'a-f'; }

kv() { # kv <text> <key>
	printf '%s\n' "$1" | awk -v key="$2" -F= '$1 == key { sub(/^[^=]*=/, ""); print; exit }'
}

get_status() {
	curl -sS --max-time 5 "$BASE/status" 2>/dev/null || true
}

get_status_hdr() {
	curl -sS --max-time 5 -D "$TMP/status.hdr" -o "$TMP/status.body" \
		"$BASE/status" 2>/dev/null || true
}

assert_status_idle() { # assert_status_idle <context>
	local st stage
	st=$(get_status)
	stage=$(kv "$st" stage)
	if [ "$stage" = "idle" ]; then
		pass "$1: /status stays idle"
		return 0
	fi
	failcase "$1: /status is not idle after the request (stage=$(show "$stage"), raw='$st')"
	return 1
}

assert_no_write_stage() { # assert_no_write_stage <context>
	local st stage
	st=$(get_status)
	stage=$(kv "$st" stage)
	case "$stage" in
		erase|blank|write|readback|compare|done)
			failcase "$1: write-stage '$stage' observed in /status; the request must not arm the write path"
			return 1
			;;
	esac
	pass "$1: /status shows no write stage (stage=$(show "$stage"))"
	return 0
}

while [ $# -gt 0 ]; do
	case "$1" in
	--image|--host|--iface|--page|--asset-stats|--approval|--timeout|--expected-sha|--firmware-pkg|--base-url)
		[ $# -ge 2 ] || fatal "missing value for $1"
		case "$1" in
		--image)       IMAGE=$2 ;;
		--host)        HOST=$2 ;;
		--iface)       IFACE=$2 ;;
		--page)        PAGE=$2 ;;
		--asset-stats) ASSET_STATS=$2 ;;
		--approval)    APPROVAL=$2 ;;
		--timeout)     POLL_TIMEOUT=$2 ;;
		--expected-sha) EXPECTED_IMAGE_SHA=$2 ;;
		--firmware-pkg) FW_PKG=$2 ;;
		--base-url)    BASE_URL=$2 ;;
		esac
		shift 2
		;;
	--dhcp)        DO_DHCP=1; shift ;;
	--write)       WRITE=1; shift ;;
	--skip-matrix) SKIP_MATRIX=1; shift ;;
	--require-digest) REQUIRE_DIGEST=1; shift ;;
	--keep-tmp)    KEEP_TMP=1; shift ;;
	--v21)         V21=1; shift ;;
	--skip-lan)    SKIP_LAN=1; shift ;;
	-h|--help)     usage ;;
	*)             fatal "unknown argument: $1 (use --help)" ;;
	esac
done

[ -n "$IMAGE" ] || fatal "--image is required"

if [ "$V21" = 1 ]; then
	[ -n "$FW_PKG" ] || fatal "--v21 needs --firmware-pkg <factory package .bin>"
	[ -f "$FW_PKG" ] || fatal "firmware package not found: $FW_PKG"
fi
if [ -n "$BASE_URL" ] && [ "$SKIP_LAN" != 1 ]; then
	fatal "--base-url is for the mock/loopback self-test; pass --skip-lan too"
fi

if [ "$WRITE" = 1 ] && [ "$APPROVAL" != "$E4_APPROVAL_VALUE" ]; then
	printf '[e4-accept] WRITE REFUSED: --write requires --approval %s (Lead approval must be explicit)\n' \
		"$E4_APPROVAL_VALUE" >&2
	exit 3
fi

[ -f "$IMAGE" ] || fatal "image not found: $IMAGE"
if [ -z "$PAGE" ]; then PAGE="$ROOT/uboot-port/failsafe/e2631-failsafe.html"; fi
[ -f "$PAGE" ] || fatal "page not found: $PAGE"

for c in curl sha256sum python3 gzip stat awk sed; do require_cmd "$c"; done

TMP=$(mktemp -d) || fatal "cannot create temporary directory"
log "workdir: $ROOT"
log "image:   $IMAGE"
log "host:    $HOST"
log "page:    $PAGE"
if [ "$WRITE" = 1 ]; then
	log "mode:    VALIDATE + WRITE (net-zero, Lead-approved)"
else
	log "mode:    VALIDATE-ONLY (write phase skipped)"
fi

# --- local image: exact net-zero identity and the frozen structural contract
local_sha=$(sha256sum "$IMAGE" | awk '{print $1}')
local_size=$(stat -c %s "$IMAGE")
log "local image sha256: $local_sha ($local_size bytes)"

if [ "$local_sha" != "$EXPECTED_IMAGE_SHA" ]; then
	failcase "image sha256 mismatch: got $local_sha, want $EXPECTED_IMAGE_SHA; refusing to test a non-net-zero image"
else
	pass "image sha256 is the approved net-zero image ($EXPECTED_IMAGE_SHA)"
fi
if [ "$local_size" != "$EXPECTED_IMAGE_SIZE" ]; then
	failcase "image size is $local_size, want $EXPECTED_IMAGE_SIZE"
fi

structural=$(python3 - "$IMAGE" <<'PY'
import sys, zlib
p = sys.argv[1]
d = open(p, 'rb').read()
magic = d[0x10:0x14]
ln = int.from_bytes(d[0x14:0x18], 'little')
ok = True
def chk(cond, msg):
    global ok
    if not cond:
        print('ERR ' + msg)
        ok = False
chk(len(d) == 0xA0000, 'size != 0xA0000')
chk(magic == b'128s', 'magic at 0x10 is %r' % (magic,))
chk(0 < ln <= 0x9F800, 'payload_len %#x out of window' % ln)
chk(0x800 + ln <= 0xA0000, 'payload end %#x beyond 0xA0000' % (0x800 + ln))
chk(all(b == 0xFF for b in d[0x800 + ln:0xA0000]), 'padding after payload is not all 0xFF')
chk(b'U-Boot 20' in d[0x800:0x800 + ln], 'payload lacks the banner string "U-Boot 20"')
print(ok, '%#x' % ln, '0x%08x' % (zlib.crc32(d) & 0xFFFFFFFF))
PY
)
structural_ok=$(printf '%s\n' "$structural" | awk 'NR==1 {print $1}')
if [ "$structural_ok" != "True" ]; then
	failcase "local structural contract check failed: $structural"
	LOCAL_CRC=00000000
else
	LOCAL_CRC=$(printf '%s\n' "$structural" | awk '{print $3}')
	pass "local image passes the frozen validator contract (crc32=$LOCAL_CRC)"
fi

# --- page: offline invariants that the acceptance relies on
page_sha=$(sha256sum "$PAGE" | awk '{print $1}')
log "local page sha256: $page_sha"
if grep -q '/reboot' "$PAGE"; then
	if grep -q 'X-E2631-Confirm' "$PAGE" && grep -q 'function doReboot' "$PAGE" && grep -q 'confirm(' "$PAGE"; then
		pass "page offers /reboot only as a user-confirmed v3 action carrying X-E2631-Confirm: reboot"
	else
		failcase "page calls /reboot without the v3 user-confirmation and X-E2631-Confirm guard"
	fi
else
	pass "page does not call /reboot"
fi
for needle in "仅校验" "写入待命" "断电重启"; do
	if grep -q "$needle" "$PAGE"; then
		pass "page carries the expected string: $needle"
	else
		failcase "page is missing the expected string: $needle"
	fi
done
if grep -q '执行 reset' "$PAGE"; then
	failcase "page still instructs the operator to run the no-op reset command"
else
	pass "page does not instruct the operator to run the no-op reset command"
fi

# --- host network: a DHCP lease in 192.168.1.0/24 on the direct link
if [ "$SKIP_LAN" = 1 ]; then
	log "host-network check skipped (--skip-lan: mock/loopback self-test)"
else
lan_ip=""
if [ -n "$IFACE" ]; then
	lan_ip=$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{sub(/\/.*/, "", $4); print $4; exit}')
else
	lan_ip=$(ip -4 -o addr show 2>/dev/null | awk '$4 ~ /^192\.168\.1\.[0-9]+\// {sub(/\/.*/, "", $4); print $4; exit}')
	IFACE=$(ip -4 -o addr show 2>/dev/null | awk '$4 ~ /^192\.168\.1\./ {print $2; exit}')
fi
if [ -z "$lan_ip" ] && [ "$DO_DHCP" = 1 ]; then
	[ -n "$IFACE" ] || fatal "--dhcp needs --iface (no 192.168.1.0/24 address found)"
	[ "$(id -u)" = 0 ] || fatal "--dhcp must run as root (dhclient needs raw sockets); rerun with sudo"
	require_cmd dhclient
	log "requesting a DHCP lease on $IFACE"
	dhclient -1 -v "$IFACE" || true
	lan_ip=$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{sub(/\/.*/, "", $4); print $4; exit}')
fi
if [ -z "$lan_ip" ]; then
	fatal "no host address in 192.168.1.0/24; connect the cable to lan1 and run 'sudo dhclient <iface>' (or pass --iface/--dhcp)"
fi
if [ "$lan_ip" = "$HOST" ]; then
	fatal "host address $lan_ip equals the device address; run DHCP again"
fi
if [ -n "$IFACE" ]; then
	pass "host has a rescue-network address: $lan_ip on $IFACE"
else
	pass "host has a rescue-network address: $lan_ip"
fi

fi

BASE="http://$HOST"
if [ -n "$BASE_URL" ]; then
	BASE=$BASE_URL
fi

# --- device reachable and serving the page
page_code=$(curl -sS --max-time 15 -o "$TMP/page.body" -D "$TMP/page.hdr" -w '%{http_code}' \
	-H 'Accept-Encoding: gzip' "$BASE/" 2>"$TMP/page.err") || page_code=000
if [ "$page_code" != 200 ]; then
	fatal "GET / returned HTTP $page_code: the device is not in rescue mode (or patch 0026 is not in this build)"
fi
if ! grep -qi '^content-encoding:[[:space:]]*gzip' "$TMP/page.hdr"; then
	failcase "GET / is not served with Content-Encoding: gzip (the embedded asset is gzip)"
else
	pass "GET / is served with Content-Encoding: gzip"
fi
if grep -qi '^content-type:[[:space:]]*text/html' "$TMP/page.hdr"; then
	pass "GET / is served as text/html"
else
	failcase "GET / is not served as text/html (headers: $(tr -d '\r' <"$TMP/page.hdr" | head -8 | tr '\n' ' '))"
fi
if gzip -dc "$TMP/page.body" >"$TMP/page.html" 2>/dev/null; then
	served_sha=$(sha256sum "$TMP/page.html" | awk '{print $1}')
	served_size=$(stat -c %s "$TMP/page.html")
	if [ "$served_sha" = "$page_sha" ]; then
		pass "served page decompresses to the repo page ($served_size bytes, sha256 $served_sha)"
	else
		failcase "served page sha256 $served_sha != repo page $page_sha (run the harness from the build's commit or pass --page)"
	fi
else
	failcase "served page is not a valid gzip stream"
fi
if [ -n "$ASSET_STATS" ]; then
	if [ -f "$ASSET_STATS" ]; then
		want_gz=$(sed -n 's/^gzip_sha256=//p' "$ASSET_STATS" | head -1)
		got_gz=$(sha256sum "$TMP/page.body" | awk '{print $1}')
		if [ -n "$want_gz" ] && [ "$got_gz" = "$want_gz" ]; then
			pass "served gzip sha256 matches E2631-FAILSAFE-ASSET.txt"
		else
			failcase "served gzip sha256 $got_gz != asset-stats $want_gz"
		fi
	else
		failcase "asset stats file not found: $ASSET_STATS"
	fi
fi

# ------------------------------------------------------------ validator runs

post_flash() { # post_flash <mode> <file> <outfile> [digest-override]; sets POST_CODE, POST_RC
	local mode=$1 file=$2 out=$3 override="${4:-}" sha
	sha=$(sha256sum "$file" | awk '{print $1}')
	if [ -n "$override" ]; then sha=$override; fi
	if [ "$mode" = write ]; then
		POST_CODE=$(curl -sS --max-time 180 -o "$out" -w '%{http_code}' \
			-H 'Content-Type: application/octet-stream' \
			-H "X-E2631-SHA256: $sha" \
			-H 'X-E2631-Confirm: write' \
			-X POST --data-binary "@$file" "$BASE/flash?mode=$mode" 2>"$TMP/post.err")
	else
		POST_CODE=$(curl -sS --max-time 180 -o "$out" -w '%{http_code}' \
			-H 'Content-Type: application/octet-stream' \
			-H "X-E2631-SHA256: $sha" \
			-X POST --data-binary "@$file" "$BASE/flash?mode=$mode" 2>"$TMP/post.err")
	fi
	POST_RC=$?
}

assert_validate_ok() { # assert_validate_ok <file> <context>
	local file=$1 ctx=$2 code body result crc
	post_flash validate "$file" "$TMP/validate.body"
	code=$POST_CODE
	body=$(cat "$TMP/validate.body" 2>/dev/null || true)
	result=$(kv "$body" result)
	crc=$(kv "$body" crc32)
	crc_src="body"
	if [ -z "$crc" ]; then
		crc=$(kv "$(get_status)" crc32)
		crc_src="status"
	fi
	if [ "$code" != 200 ]; then
		failcase "$ctx: validate returned HTTP $code (curl rc=$POST_RC, body='$body')"
		return 1
	fi
	if [ "$result" != ok ]; then
		failcase "$ctx: validate returned result=$(show "$result"), want ok (body='$body')"
		return 1
	fi
	if [ -z "$crc" ]; then
		failcase "$ctx: neither the validate response nor /status carries crc32 (body='$body')"
		return 1
	fi
	if [ "$(lc "$crc")" != "$(lc "$LOCAL_CRC")" ]; then
		failcase "$ctx: validate crc32 $crc != local $LOCAL_CRC"
		return 1
	fi
	local dsha dmatch
	dsha=$(kv "$body" sha256)
	dmatch=$(kv "$body" sha_match)
	if [ -n "$dsha" ]; then
		if [ "$(lc "$dsha")" = "$(lc "$local_sha")" ] && [ "$dmatch" = ok ]; then
			pass "$ctx: device digest matches (sha256=$dsha, sha_match=ok)"
		else
			failcase "$ctx: device digest mismatch (sha256=$(show "$dsha"), sha_match=$(show "$dmatch"), want $local_sha/ok)"
			return 1
		fi
	elif [ "$REQUIRE_DIGEST" = 1 ]; then
		failcase "$ctx: validate response has no sha256/sha_match (digest contract not implemented)"
		return 1
	else
		printf '[e4-accept] WARNING: validate response has no sha256/sha_match; the build predates the digest contract (v1-consistency gap)\n' >&2
		note "$ctx: response carries no sha256/sha_match (build predates the digest contract)"
	fi
	pass "$ctx: validate HTTP 200, result=ok, crc32=$crc (from $crc_src)"
	return 0
}

assert_rejected() { # assert_rejected <file> <label>
	local file=$1 label=$2 code body result err stage
	post_flash validate "$file" "$TMP/reject.body"
	code=$POST_CODE
	body=$(cat "$TMP/reject.body" 2>/dev/null || true)
	result=$(kv "$body" result)
	err=$(kv "$body" error)
	if [ "$code" = 400 ] && [ "$result" = error ] && [ -n "$err" ]; then
		pass "$label: rejected with HTTP 400 result=error error=$err"
	elif [ "$code" = 000 ] && [ "$POST_RC" != 0 ]; then
		# The server may reject a length-mismatched body before reading it all,
		# which makes curl abort; corroborate with an idle state machine and a
		# fresh good-image validation.
		stage=$(kv "$(get_status)" stage)
		if [ "$stage" = idle ] && assert_validate_ok "$IMAGE" "$label: post-abort re-check"; then
			pass "$label: early reject (connection aborted, curl rc=$POST_RC) corroborated by idle /status + good-image re-validation"
		else
			failcase "$label: POST aborted (curl rc=$POST_RC) but /status is not idle (stage=$(show "$stage"))"
		fi
	else
		failcase "$label: expected HTTP 400 result=error, got HTTP $code (curl rc=$POST_RC, body='$body')"
	fi
	assert_status_idle "$label"
	assert_no_write_stage "$label"
}

# --- pre-state: the rescue server must be idle before anything is uploaded
get_status_hdr
if grep -qi '^content-type:[[:space:]]*text/plain' "$TMP/status.hdr"; then
	pass "/status is served as text/plain"
else
	failcase "/status is not served as text/plain (headers: $(tr -d '\r' <"$TMP/status.hdr" | head -8 | tr '\n' ' '))"
fi
st=$(cat "$TMP/status.body" 2>/dev/null || get_status)
if ! printf '%s\n' "$st" | grep -q '^stage='; then
	failcase "/status body has no stage= key (body='$(printf '%s' "$st" | head -c 200)')"
fi
stage=$(kv "$st" stage)
if [ "$stage" = idle ]; then
	pass "pre-state: /status is idle"
else
	failcase "pre-state: /status is not idle (stage=$(show "$stage"), raw='$st'); power-cycle and re-enter rescue"
fi

# --- net-zero validate (dry run; must not touch flash)
assert_validate_ok "$IMAGE" "net-zero validate-only"
assert_status_idle "net-zero validate-only"
assert_no_write_stage "net-zero validate-only"

# --- X-E2631-SHA256 enforcement: a good body with a wrong digest must be refused
ZERO_SHA=0000000000000000000000000000000000000000000000000000000000000000
post_flash validate "$IMAGE" "$TMP/digest.body" "$ZERO_SHA"
dbody=$(cat "$TMP/digest.body" 2>/dev/null || true)
dresult=$(kv "$dbody" result)
derr=$(kv "$dbody" error)
if [ "$POST_CODE" = 400 ] && [ "$dresult" = error ] && [ -n "$derr" ]; then
	pass "X-E2631-SHA256: device refuses a mismatching digest (HTTP 400 result=error error=$derr)"
elif [ "$POST_CODE" = 200 ] && [ "$dresult" = ok ]; then
	if [ "$REQUIRE_DIGEST" = 1 ]; then
		failcase "X-E2631-SHA256: device ACCEPTED a good body with a wrong digest; payload integrity is NOT enforced"
	else
		printf '[e4-accept] WARNING: X-E2631-SHA256 NOT ENFORCED - a good body with a wrong digest was accepted; v1 payload-integrity gap remains (pass --require-digest to make this fatal, or land the 0026 digest check first)\n' >&2
		note "X-E2631-SHA256 NOT ENFORCED: device accepted a good body with a wrong digest; v1 payload-integrity gap remains"
	fi
else
	failcase "X-E2631-SHA256 probe: unexpected response HTTP $POST_CODE (curl rc=$POST_RC, body='$dbody')"
fi
assert_status_idle "X-E2631-SHA256 probe"
assert_no_write_stage "X-E2631-SHA256 probe"

make_case() { # make_case <name> <kind>; writes $TMP/<name>.bin
	local name=$1 kind=$2
	case "$kind" in
	trunc)
		head -c $((EXPECTED_IMAGE_SIZE - 1)) "$IMAGE" >"$TMP/$name.bin"
		;;
	append)
		cat "$IMAGE" >"$TMP/$name.bin"
		printf '\x00' >>"$TMP/$name.bin"
		;;
	*)
		python3 - "$IMAGE" "$TMP/$name.bin" "$kind" <<'PY'
import sys
src, dst, kind = sys.argv[1:4]
d = bytearray(open(src, 'rb').read())
if kind == 'badmagic':
    d[0x10] ^= 0xFF
elif kind == 'badlen':
    d[0x14:0x18] = (0x9F801).to_bytes(4, 'little')
elif kind == 'badpadding':
    ln = int.from_bytes(d[0x14:0x18], 'little')
    off = 0x800 + ln + 0x10
    assert off < 0xA0000
    d[off] = 0x00
elif kind == 'nobanner':
    # The E4 payload carries two 'U-Boot 20' probe strings, so flip every
    # occurrence in the payload; flipping only the first one would leave the
    # image acceptable to the device banner probe.
    hits = 0
    i = d.find(b'U-Boot 20', 0x800)
    while i > 0:
        d[i] = ord('X')
        hits += 1
        i = d.find(b'U-Boot 20', i + 1)
    assert hits >= 1
elif kind == 'payloadflip':
    d[0x30000] ^= 0x01
else:
    raise SystemExit('unknown kind: ' + kind)
open(dst, 'wb').write(d)
PY
		;;
	esac
}

if [ "$SKIP_MATRIX" = 0 ]; then
	make_case size_minus_one trunc
	assert_rejected "$TMP/size_minus_one.bin" "matrix size-1"
	make_case size_plus_one append
	assert_rejected "$TMP/size_plus_one.bin" "matrix size+1"
	make_case bad_magic badmagic
	assert_rejected "$TMP/bad_magic.bin" "matrix bad-magic"
	make_case bad_length badlen
	assert_rejected "$TMP/bad_length.bin" "matrix length-out-of-window"
	make_case bad_padding badpadding
	assert_rejected "$TMP/bad_padding.bin" "matrix non-FF-padding"
	make_case no_banner nobanner
	assert_rejected "$TMP/no_banner.bin" "matrix banner-missing"

	# Known v1 limitation, informational only: v1 has no device-side digest.
	make_case payload_flip payloadflip
	post_flash validate "$TMP/payload_flip.bin" "$TMP/payload_flip.body"
	flip_body=$(cat "$TMP/payload_flip.body" 2>/dev/null || true)
	flip_result=$(kv "$flip_body" result)
	if [ "$POST_CODE" = 200 ] && [ "$flip_result" = ok ]; then
		note "payload-flip: validate accepts a locally modified body because X-E2631-SHA256 binds the header to the uploaded bytes, not to the authoritative image; authority comes from the pinned expected sha (the harness never writes this body)"
	elif [ "$POST_CODE" = 400 ]; then
		note "payload-flip: validate rejected the modified body (stricter than required; record which check fired)"
	else
		note "payload-flip: inconclusive (HTTP $POST_CODE, result=$(show "$flip_result")); do not rely on it"
	fi
	assert_no_write_stage "payload-flip"
fi

# --------------------------------------------------------------- write phase

if [ "$WRITE" = 0 ]; then
	log "write phase skipped (default validate-only); pass --write --approval $E4_APPROVAL_VALUE after Lead approval"
else
	write_sha=$(sha256sum "$IMAGE" | awk '{print $1}')
	if [ "$write_sha" != "$EXPECTED_IMAGE_SHA" ]; then
		failcase "refusing to write: image sha256 changed to $write_sha"
	else
		pass "write pre-check: image still the approved net-zero image"
	fi
	if [ "$(kv "$(get_status)" stage)" != idle ]; then
		failcase "refusing to write: /status is not idle before the write POST"
	else
		pass "write pre-check: /status is idle"
	fi

	if [ "$FAIL" -eq 0 ]; then
		log "starting the NET-ZERO write run (erase/blank/write/readback/compare; do not cut power)"
		post_flash write "$IMAGE" "$TMP/write.body"
		wbody=$(cat "$TMP/write.body" 2>/dev/null || true)
		wresult=$(kv "$wbody" result)
		wsha=$(kv "$wbody" sha256)
		if [ "$POST_CODE" = 200 ] && [ "$wresult" = accepted ]; then
			pass "write POST: HTTP 200 result=accepted"
			if [ -n "$wsha" ] && [ "$(lc "$wsha")" = "$(lc "$local_sha")" ]; then
				pass "write POST: device digest matches (sha256=$wsha)"
			elif [ -n "$wsha" ]; then
				failcase "write POST: device digest $wsha != local $local_sha"
			elif [ "$REQUIRE_DIGEST" = 1 ]; then
				failcase "write POST: no sha256 in the accepted response"
			else
				note "write POST: accepted response has no sha256 (build predates the digest contract)"
			fi
		else
			failcase "write POST expected HTTP 200 result=accepted, got HTTP $POST_CODE (curl rc=$POST_RC, body='$wbody')"
		fi

		observed=" "
		last=""
		final_ok=0
		device_sha=""
		device_match=""
		deadline=$((SECONDS + POLL_TIMEOUT))
		while :; do
			st=$(get_status)
			stage=$(kv "$st" stage)
			result=$(kv "$st" result)
			err=$(kv "$st" error)
			crc=$(kv "$st" crc32)
			progress=$(kv "$st" progress)
			poll_sha=$(kv "$st" sha256)
			poll_match=$(kv "$st" sha_match)
			if [ -n "$poll_sha" ]; then device_sha=$poll_sha; fi
			if [ -n "$poll_match" ]; then device_match=$poll_match; fi
			if [ "$stage" != "$last" ]; then
				log "status: stage=$(show "$stage") progress=$(show "$progress") result=$(show "$result")"
				observed="$observed$stage "
				last=$stage
			fi
			case "$stage" in
			erase|blank|write|readback|compare|done|validating|staged|idle|error|"") ;;
			*) failcase "write poll: unknown stage '$stage'"; break ;;
			esac
			if [ "$result" = ok ] || [ "$stage" = done ]; then
				final_ok=1
				break
			fi
			if [ "$result" = error ] || [ "$stage" = error ] || [ -n "$err" ]; then
				failcase "write poll: device reported an error (stage=$(show "$stage"), error=$(show "$err"))"
				break
			fi
			if [ "$SECONDS" -ge "$deadline" ]; then
				failcase "write poll: timed out after $POLL_TIMEOUT s (last stage=$(show "$stage"))"
				break
			fi
			sleep 0.5
		done
		if [ "$final_ok" = 1 ]; then
			pass "write poll: terminal result=ok"
		fi
		if [ -n "$device_sha" ]; then
			if [ "$(lc "$device_sha")" = "$(lc "$local_sha")" ] && [ "$device_match" = ok ]; then
				pass "write poll: final device digest matches ($device_sha, sha_match=ok)"
			elif [ "$(lc "$device_sha")" = "$(lc "$local_sha")" ] && [ -z "$device_match" ]; then
				pass "write poll: final device digest matches ($device_sha)"
			else
				failcase "write poll: final device digest $(show "$device_sha") sha_match=$(show "$device_match") != local $local_sha/ok"
			fi
		elif [ "$REQUIRE_DIGEST" = 1 ]; then
			failcase "write poll: /status never reported sha256"
		else
			note "write poll: /status never reported sha256 (build predates the digest contract)"
		fi
		seen_stages=0
		for want in erase blank write readback compare; do
			case "$observed" in
			*" $want "*) pass "write poll: observed stage '$want'"; seen_stages=$((seen_stages + 1)) ;;
			*) note "write poll: stage '$want' was not sampled between polls (transient; observed:$observed)" ;;
			esac
		done
		if [ "$seen_stages" -eq 0 ]; then
			failcase "write poll: none of erase/blank/write/readback/compare was ever observed (observed:$observed)"
		fi
		if [ -n "$crc" ] && [ "$(lc "$crc")" = "$(lc "$LOCAL_CRC")" ]; then
			pass "write poll: final CRC32 $crc equals the local image CRC32"
		else
			failcase "write poll: final crc32 $(show "$crc") != local $LOCAL_CRC"
		fi
		pass "write: no reboot/reset was requested; the device stays in rescue mode"
	else
		failcase "write phase skipped because pre-write checks failed; fix the failures and re-run"
	fi
fi

# ------------------------------------------------------- v2.1 suite (opt-in)

if [ "$V21" = 1 ]; then
	log "v2.1 suite: six page tabs, /backup parts, /console, /firmware validate + negatives, /env refusals, /factory refusals, /boot"

	# --- page: the six v2.1 tabs are served and the page stays self-contained
	if [ -s "$TMP/page.html" ]; then
		for needle in "系统状态" "固件更新" "引导区" "环境变量" "串口台" "恢复出厂"; do
			if grep -q "$needle" "$TMP/page.html"; then
				pass "v2.1 page: carries the tab string: $needle"
			else
				failcase "v2.1 page: missing the tab string: $needle"
			fi
		done
		if grep -Eq "https?://|<script[[:space:]]+src=|<link[[:space:]]+href=" "$TMP/page.html"; then
			failcase "v2.1 page: contains an external URL or an external resource reference"
		else
			pass "v2.1 page: no external URL or external resource reference"
		fi
		page_gz_bytes=$(stat -c %s "$TMP/page.body")
		if [ "$page_gz_bytes" -le 32768 ]; then
			pass "v2.1 page: served gzip asset is $page_gz_bytes B (limit 32768 B)"
		else
			failcase "v2.1 page: served gzip asset is $page_gz_bytes B (limit 32768 B)"
		fi
	else
		failcase "v2.1 page: no decompressed page is available for the tab checks"
	fi

	# --- GET /backup?part=: raw partition + CRC32/SHA-256/offset/length headers
	hdrval() { # hdrval <file> <header-name>
		tr -d "\r" <"$1" | awk -v want="$(printf "%s" "$2" | tr "A-Z" "a-z")" -F: 'tolower($1) == want { v = substr($0, index($0, ":") + 1); sub(/^[ \t]+/, "", v); print v; exit }'
	}
	backup_fetch() { # backup_fetch <part> <outfile> <hdrfile>
		BACK_CODE=$(curl -sS --max-time 300 -o "$2" -D "$3" -w "%{http_code}" "$BASE/backup?part=$1" 2>"$TMP/backup.err")
	}
	backup_part() { # backup_part <part> <off> <len> <label>
		local part=$1 off=$2 len=$3 label=$4 out="$TMP/backup-$1.bin" hdr="$TMP/backup-$1.hdr"
		backup_fetch "$part" "$out" "$hdr"
		if [ "$BACK_CODE" != 200 ]; then
			failcase "$label: GET /backup?part=$part returned HTTP $BACK_CODE (body=$(head -c 200 "$out" 2>/dev/null || true))"
			return
		fi
		local size got_off got_len got_part got_crc got_sha computed body_crc body_sha
		size=$(stat -c %s "$out")
		got_off=$(hdrval "$hdr" "X-E2631-Offset")
		got_len=$(hdrval "$hdr" "X-E2631-Length")
		got_part=$(hdrval "$hdr" "X-E2631-Part")
		got_crc=$(hdrval "$hdr" "X-E2631-CRC32")
		got_sha=$(hdrval "$hdr" "X-E2631-SHA256")
		computed=$(python3 - "$out" <<'PY'
import sys, hashlib, zlib
d = open(sys.argv[1], "rb").read()
print("0x%08x" % (zlib.crc32(d) & 0xFFFFFFFF), hashlib.sha256(d).hexdigest())
PY
		)
		body_crc=${computed%% *}
		body_sha=${computed##* }
		if [ "$size" = "$len" ]; then
			pass "$label: $part body length $size B"
		else
			failcase "$label: $part body length $size B, want $len B"
		fi
		if [ "$(lc "$got_off")" = "$(lc "$(printf "0x%x" "$off")")" ]; then
			pass "$label: X-E2631-Offset=$got_off"
		else
			failcase "$label: X-E2631-Offset=$(show "$got_off"), want 0x$(printf "%x" "$off")"
		fi
		if [ "$(lc "$got_len")" = "$(lc "$(printf "0x%x" "$len")")" ]; then
			pass "$label: X-E2631-Length=$got_len"
		else
			failcase "$label: X-E2631-Length=$(show "$got_len"), want 0x$(printf "%x" "$len")"
		fi
		if [ "$got_part" = "$part" ]; then
			pass "$label: X-E2631-Part=$got_part"
		else
			failcase "$label: X-E2631-Part=$(show "$got_part"), want $part"
		fi
		if [ "$(lc "$got_crc")" = "$(lc "$body_crc")" ]; then
			pass "$label: X-E2631-CRC32 matches the body ($body_crc)"
		else
			failcase "$label: X-E2631-CRC32 $(show "$got_crc") != body $body_crc"
		fi
		if [ "$(lc "$got_sha")" = "$(lc "$body_sha")" ]; then
			pass "$label: X-E2631-SHA256 matches the body"
		else
			failcase "$label: X-E2631-SHA256 $(show "$got_sha") != body $body_sha"
		fi
		if grep -q "Content-Type: application/octet-stream" "$hdr" 2>/dev/null; then
			pass "$label: served as application/octet-stream"
		else
			failcase "$label: not served as application/octet-stream"
		fi
		if grep -qi "Content-Disposition: attachment; filename=\"e2631-$part.bin\"" "$hdr" 2>/dev/null; then
			pass "$label: download filename is e2631-$part.bin"
		else
			failcase "$label: download filename is not e2631-$part.bin"
		fi
	}
	backup_part bootloader 0x20000 655360 "v2.1 backup bootloader"
	if [ "$(sha256sum "$TMP/backup-bootloader.bin" 2>/dev/null | awk '{print $1}')" = "$EXPECTED_IMAGE_SHA" ]; then
		pass "v2.1 backup bootloader: body sha256 equals the net-zero image ($EXPECTED_IMAGE_SHA)"
	else
		failcase "v2.1 backup bootloader: body sha256 does not equal the net-zero image"
	fi
	backup_part tag 0x100000 1048576 "v2.1 backup tag"
	backup_part wifi 0x200000 1048576 "v2.1 backup wifi"
	backup_part usercfg 0x300000 2097152 "v2.1 backup usercfg"
	backup_part defcfg 0x500000 2097152 "v2.1 backup defcfg"
	BACK_CODE=$(curl -sS --max-time 20 -o "$TMP/backup-bad.body" -w "%{http_code}" "$BASE/backup?part=bogus" 2>/dev/null || true)
	if [ "$BACK_CODE" = 400 ] && grep -q "result=error" "$TMP/backup-bad.body" && grep -q "error=" "$TMP/backup-bad.body"; then
		pass "v2.1 backup: unknown part rejected with HTTP 400 result=error"
	else
		failcase "v2.1 backup: unknown part expected HTTP 400 result=error, got HTTP $BACK_CODE"
	fi
	assert_status_idle "v2.1 backup"

	# --- POST /console?cmd=: one command, captured stdout, exact refusals
	console_post() { # console_post <cmd> <outfile>
		local enc
		enc=$(python3 - "$1" <<'PY'
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=""))
PY
		)
		CON_CODE=$(curl -sS --max-time 30 -o "$2" -w "%{http_code}" -X POST --data "" "$BASE/console?cmd=$enc" 2>"$TMP/console.err")
	}
	console_ok() { # console_ok <cmd> <label> [want-substring]
		local cmd=$1 label=$2 want="${3:-}" body result exitcode stdout truncated err
		console_post "$cmd" "$TMP/console.body"
		body=$(cat "$TMP/console.body" 2>/dev/null || true)
		result=$(kv "$body" result)
		exitcode=$(kv "$body" exit)
		stdout=$(kv "$body" stdout)
		truncated=$(kv "$body" truncated)
		err=$(kv "$body" error)
		if [ "$CON_CODE" = 200 ] && [ "$result" = ok ] && [ "$exitcode" = 0 ] && [ -n "$stdout" ]; then
			pass "$label: HTTP 200 result=ok exit=0 truncated=$(show "$truncated")"
			if [ -n "$want" ]; then
				case "$stdout" in
				*"$want"*) pass "$label: stdout carries '$want'" ;;
				*) failcase "$label: stdout does not carry '$want' (stdout=$(printf "%s" "$stdout" | head -c 160))" ;;
				esac
			fi
		else
			failcase "$label: expected HTTP 200 result=ok exit=0 with stdout, got HTTP $CON_CODE (result=$(show "$result"), exit=$(show "$exitcode"), error=$(show "$err"))"
		fi
	}
	console_reject() { # console_reject <cmd> <label> [want-error-substring]
		local cmd=$1 label=$2 want="${3:-}" body result err
		console_post "$cmd" "$TMP/console.body"
		body=$(cat "$TMP/console.body" 2>/dev/null || true)
		result=$(kv "$body" result)
		err=$(kv "$body" error)
		if [ "$CON_CODE" = 400 ] && [ "$result" = error ] && [ -n "$err" ]; then
			pass "$label: refused with HTTP 400 result=error error=$err"
			if [ -n "$want" ]; then
				case "$err" in
				*"$want"*) pass "$label: error text carries '$want'" ;;
				*) failcase "$label: error text does not carry '$want' (error=$err)" ;;
				esac
			fi
		else
			failcase "$label: expected HTTP 400 result=error, got HTTP $CON_CODE (result=$(show "$result"), error=$(show "$err"))"
		fi
	}
	console_ok "version" "v2.1 console version" "U-Boot"
	console_ok "printenv bootdelay" "v2.1 console printenv bootdelay" "bootdelay="
	console_ok "md.b 0x47F00000 0x4000" "v2.1 console md.b large read"
	con_trunc=$(kv "$(cat "$TMP/console.body" 2>/dev/null || true)" truncated)
	if [ "$con_trunc" = 1 ]; then
		pass "v2.1 console: output larger than 4 KiB is reported as truncated=1"
	else
		failcase "v2.1 console: md.b 0x4000 output was not reported as truncated=1 (truncated=$(show "$con_trunc"))"
	fi
	console_reject "" "v2.1 console empty command"
	console_reject "echo a; echo b" "v2.1 console semicolon" "single command"
	long_cmd=$(python3 -c 'print("a" * 300)')
	console_reject "$long_cmd" "v2.1 console overlong command"
	assert_status_idle "v2.1 console"

	# --- POST /firmware?mode=validate: the factory package matrix (no write)
	if [ ! -f "$FW_PKG" ]; then
		failcase "v2.1 firmware: --firmware-pkg file disappeared: $FW_PKG"
	else
		fw_sha=$(sha256sum "$FW_PKG" | awk '{print $1}')
		fw_size=$(stat -c %s "$FW_PKG")
		fw_body_len=$((fw_size - 0x214))
		if [ "$fw_size" -ge $((0x214)) ] && [ "$fw_size" -le $((0x1BE0214)) ]; then
			pass "v2.1 firmware: package size $fw_size B is inside the contract window"
		else
			failcase "v2.1 firmware: package size $fw_size B is outside the contract window"
		fi
		post_fw() { # post_fw <file> <outfile> [extra-query] [digest-override]
			local file=$1 out=$2 query="${3:-}" override="${4:-}" sha
			sha=$(sha256sum "$file" | awk '{print $1}')
			if [ -n "$override" ]; then sha=$override; fi
			FW_CODE=$(curl -sS --max-time 600 -o "$out" -w "%{http_code}" \
				-H "Content-Type: application/octet-stream" \
				-H "X-E2631-SHA256: $sha" \
				-X POST --data-binary "@$file" "$BASE/firmware?mode=validate$query" 2>"$TMP/fw.err")
			FW_RC=$?
		}
		fw_validate_ok() { # fw_validate_ok <file> <label>
			local file=$1 label=$2 body result sha match bodylen slot ident guard
			post_fw "$file" "$TMP/fw.body"
			body=$(cat "$TMP/fw.body" 2>/dev/null || true)
			result=$(kv "$body" result)
			sha=$(kv "$body" sha256)
			match=$(kv "$body" sha_match)
			bodylen=$(kv "$body" body_len)
			slot=$(kv "$body" slot_target)
			ident=$(kv "$body" slot_target_identity)
			guard=$(kv "$body" guard)
			if [ "$FW_CODE" != 200 ] || [ "$result" != ok ]; then
				failcase "$label: expected HTTP 200 result=ok, got HTTP $FW_CODE (result=$(show "$result"), body=$(printf "%s" "$body" | head -c 200))"
				return
			fi
			pass "$label: HTTP 200 result=ok (slot_target=$(show "$slot"), guard=$(show "$guard"))"
			if [ "$(lc "$sha")" = "$(lc "$fw_sha")" ] && [ "$match" = ok ]; then
				pass "$label: device digest matches (sha256=$sha, sha_match=ok)"
			else
				failcase "$label: digest mismatch (sha256=$(show "$sha"), sha_match=$(show "$match"))"
			fi
			if [ "$(lc "$bodylen")" = "$(lc "$(printf "0x%x" "$fw_body_len")")" ]; then
				pass "$label: body_len=$bodylen matches the package body"
			else
				failcase "$label: body_len=$(show "$bodylen"), want 0x$(printf "%x" "$fw_body_len")"
			fi
			case "$slot" in
			0|1) pass "$label: slot_target=$slot" ;;
			*) failcase "$label: slot_target=$(show "$slot") is not 0/1" ;;
			esac
			case "$ident" in
			empty|vendor|ours|unknown) pass "$label: slot_target_identity=$ident" ;;
			*) failcase "$label: slot_target_identity=$(show "$ident") is not a known identity" ;;
			esac
			case "$guard" in
			ok|weak) pass "$label: guard=$guard" ;;
			refuse) failcase "$label: guard=refuse for the net-zero package (target slot is a working vendor system?)" ;;
			*) failcase "$label: guard=$(show "$guard") is not ok/weak/refuse" ;;
			esac
		}
		fw_reject() { # fw_reject <file> <label> [want-error-substring] [extra-query] [digest-override]
			local file=$1 label=$2 want="${3:-}" query="${4:-}" override="${5:-}" body result err stage
			post_fw "$file" "$TMP/fw.body" "$query" "$override"
			body=$(cat "$TMP/fw.body" 2>/dev/null || true)
			result=$(kv "$body" result)
			err=$(kv "$body" error)
			if [ "$FW_CODE" = 400 ] && [ "$result" = error ] && [ -n "$err" ]; then
				pass "$label: refused with HTTP 400 result=error error=$err"
				if [ -n "$want" ]; then
					case "$(printf "%s" "$err" | tr "A-Z" "a-z")" in
					*"$want"*) pass "$label: error text carries '$want'" ;;
					*) failcase "$label: error text does not carry '$want' (error=$err)" ;;
					esac
				fi
			elif [ "$FW_CODE" = 000 ] && [ "$FW_RC" != 0 ]; then
				stage=$(kv "$(get_status)" stage)
				if [ "$stage" = idle ]; then
					pass "$label: early reject (connection aborted, curl rc=$FW_RC) with /status idle"
				else
					failcase "$label: POST aborted but /status stage=$(show "$stage")"
				fi
			else
				failcase "$label: expected HTTP 400 result=error, got HTTP $FW_CODE (result=$(show "$result"), body=$(printf "%s" "$body" | head -c 200))"
			fi
			assert_status_idle "$label"
		}
		make_pkg_case() { # make_pkg_case <name> <kind>
			python3 - "$FW_PKG" "$TMP/fw-$1.bin" "$2" <<'PY'
import sys, zlib
src, dst, kind = sys.argv[1:4]
d = bytearray(open(src, "rb").read())
hdr_ofs = 0x14 + int.from_bytes(d[0x10:0x14], "little")
def reseal():
    h = memoryview(d)[hdr_ofs:hdr_ofs + 0x200]
    d[hdr_ofs + 0xa4:hdr_ofs + 0xa8] = zlib.crc32(h[:0xa4]).to_bytes(4, "little")
    h = memoryview(d)[hdr_ofs:hdr_ofs + 0x200]
    d[hdr_ofs + 0x1fc:hdr_ofs + 0x200] = zlib.crc32(h[:0x1fc]).to_bytes(4, "little")
if kind == "badmagic":
    d[0] ^= 0xFF
elif kind == "badheader":
    d[0x20] ^= 0xFF
elif kind == "badkernel":
    d[0x1000] ^= 0xFF
elif kind == "badrootfs":
    d[0x410000] ^= 0xFF
elif kind == "badproduct":
    d[hdr_ofs + 0x6c + 16] = ord("X")
    reseal()
elif kind == "bootincluded":
    d[hdr_ofs + 0x8c:hdr_ofs + 0x90] = (1).to_bytes(4, "little")
    reseal()
elif kind == "badsize":
    v = int.from_bytes(d[hdr_ofs + 0x30:hdr_ofs + 0x34], "little")
    d[hdr_ofs + 0x30:hdr_ofs + 0x34] = (v + 1).to_bytes(4, "little")
    reseal()
else:
    raise SystemExit("unknown kind: " + kind)
open(dst, "wb").write(d)
PY
		}
		fw_validate_ok "$FW_PKG" "v2.1 firmware validate legal package"
		fw_reject "$FW_PKG" "v2.1 firmware digest mismatch" "sha256 mismatch" "" "$ZERO_SHA"
		head -c 500 "$FW_PKG" >"$TMP/fw-small.bin"
		fw_reject "$TMP/fw-small.bin" "v2.1 firmware package too small" "too small"
		truncate -s $((0x1BE0215)) "$TMP/fw-large.bin"
		fw_reject "$TMP/fw-large.bin" "v2.1 firmware package too large" ""
		make_pkg_case badmagic badmagic
		fw_reject "$TMP/fw-badmagic.bin" "v2.1 firmware bad outer magic" "outer magic"
		make_pkg_case badheader badheader
		fw_reject "$TMP/fw-badheader.bin" "v2.1 firmware header CRC" "header crc"
		make_pkg_case badkernel badkernel
		fw_reject "$TMP/fw-badkernel.bin" "v2.1 firmware kernel CRC" "kernel crc"
		make_pkg_case badrootfs badrootfs
		fw_reject "$TMP/fw-badrootfs.bin" "v2.1 firmware rootfs CRC" "rootfs crc"
		make_pkg_case badproduct badproduct
		fw_reject "$TMP/fw-badproduct.bin" "v2.1 firmware product prefix (17th byte)" "product"
		make_pkg_case bootincluded bootincluded
		fw_reject "$TMP/fw-bootincluded.bin" "v2.1 firmware bootloader included" "bootloader"
		make_pkg_case badsize badsize
		fw_reject "$TMP/fw-badsize.bin" "v2.1 firmware body size" "body size"
		fw_reject "$FW_PKG" "v2.1 firmware bad slot" "slot" "&slot=2"
	fi

	# --- POST /env and /factory: refusal-only probes (no write is ever armed)
	env_get_code=$(curl -sS --max-time 15 -o "$TMP/env.body" -w "%{http_code}" "$BASE/env" 2>/dev/null || true)
	if [ "$env_get_code" = 200 ] && grep -q "^bootcmd=" "$TMP/env.body" && grep -q "^bootdelay=" "$TMP/env.body"; then
		pass "v2.1 env: GET /env is a read-only snapshot with bootcmd/bootdelay"
	else
		failcase "v2.1 env: GET /env failed (HTTP $env_get_code) or lacks bootcmd/bootdelay"
	fi
	env_keys=$(grep -c "^[a-z0-9_]*=" "$TMP/env.body" 2>/dev/null || true)
	if [ "$env_keys" -ge 20 ]; then
		pass "v2.1 env: snapshot carries $env_keys keys"
	else
		note "v2.1 env: snapshot carries only $env_keys keys (mock or trimmed build; device carries the full env)"
	fi
	cur_bootdelay=$(sed -n "s/^bootdelay=//p" "$TMP/env.body" | head -1)
	if [ -n "$cur_bootdelay" ]; then
		env_nochange=$(curl -sS --max-time 20 -o "$TMP/env-nochange.body" -w "%{http_code}" \
			-H "X-E2631-Confirm: write" -X POST --data "" \
			"$BASE/env?key=bootdelay&value=$cur_bootdelay&confirm=write" 2>/dev/null || true)
		nc_body=$(cat "$TMP/env-nochange.body" 2>/dev/null || true)
		if [ "$env_nochange" = 200 ] && [ "$(kv "$nc_body" result)" = ok ] && [ "$(kv "$nc_body" keys)" = 0 ]; then
			pass "v2.1 env: writing the current bootdelay=$cur_bootdelay is a no-change (result=ok keys=0)"
			assert_status_idle "v2.1 env no-change"
		else
			failcase "v2.1 env: no-change probe expected HTTP 200 result=ok keys=0, got HTTP $env_nochange (body=$(printf "%s" "$nc_body" | head -c 200))"
		fi
	else
		note "v2.1 env: /env did not expose a bootdelay value; no-change probe skipped"
	fi
	env_refusal() { # env_refusal <url-suffix> <label> [want-error]
		local suffix=$1 label=$2 want="${3:-}" code body result err
		code=$(curl -sS --max-time 20 -o "$TMP/env-bad.body" -w "%{http_code}" -X POST --data "" "$BASE/env?$suffix" 2>/dev/null || true)
		body=$(cat "$TMP/env-bad.body" 2>/dev/null || true)
		result=$(kv "$body" result)
		err=$(kv "$body" error)
		if { [ "$code" = 400 ] || [ "$code" = 403 ]; } && [ "$result" = error ] && [ -n "$err" ]; then
			pass "$label: refused with HTTP $code result=error error=$err"
		else
			failcase "$label: expected HTTP 400/403 result=error, got HTTP $code (body=$(printf "%s" "$body" | head -c 200))"
		fi
	}
	env_refusal "key=bootcmd&value=foo&confirm=write" "v2.1 env vendor key refused (no confirm header)" "confirm"
	curl -sS --max-time 20 -o "$TMP/env-vendor.body" -w "%{http_code}" -H "X-E2631-Confirm: write" -X POST --data "" "$BASE/env?key=bootcmd&value=foo&confirm=write" >"$TMP/env-vendor.code" 2>/dev/null || true
	vcode=$(cat "$TMP/env-vendor.code")
	vbody=$(cat "$TMP/env-vendor.body" 2>/dev/null || true)
	if [ "$vcode" = 403 ] && [ "$(kv "$vbody" result)" = error ] && [ -n "$(kv "$vbody" error)" ]; then
		pass "v2.1 env: vendor key bootcmd refused with HTTP 403 error=$(kv "$vbody" error)"
	else
		failcase "v2.1 env: vendor key expected HTTP 403 result=error, got HTTP $vcode"
	fi
	curl -sS --max-time 20 -o "$TMP/env-key.body" -w "%{http_code}" -H "X-E2631-Confirm: write" -X POST --data "" "$BASE/env?key=Bogus_Key&value=1&confirm=write" >"$TMP/env-key.code" 2>/dev/null || true
	kcode=$(cat "$TMP/env-key.code")
	if [ "$kcode" = 403 ]; then
		pass "v2.1 env: an out-of-whitelist key name is refused with HTTP 403"
	else
		failcase "v2.1 env: out-of-whitelist key expected HTTP 403, got HTTP $kcode"
	fi
	curl -sS --max-time 20 -o "$TMP/env-val.body" -w "%{http_code}" -H "X-E2631-Confirm: write" -X POST --data "" "$BASE/env?key=e2631_test&value=%01&confirm=write" >"$TMP/env-val.code" 2>/dev/null || true
	valcode=$(cat "$TMP/env-val.code")
	if [ "$valcode" = 400 ]; then
		pass "v2.1 env: a non-printable value is refused with HTTP 400"
	else
		failcase "v2.1 env: non-printable value expected HTTP 400, got HTTP $valcode"
	fi
	assert_status_idle "v2.1 env refusals"
	assert_no_write_stage "v2.1 env refusals"
	factory_refusal() { # factory_refusal <query> <header|-> <label>
		local query=$1 hdr=$2 label=$3 extra=() code body
		if [ "$hdr" != "-" ]; then extra=(-H "X-E2631-Confirm: $hdr"); fi
		code=$(curl -sS --max-time 20 -o "$TMP/factory.body" -w "%{http_code}" "${extra[@]}" -X POST --data "" "$BASE/factory$query" 2>/dev/null || true)
		body=$(cat "$TMP/factory.body" 2>/dev/null || true)
		if [ "$code" = 400 ] && [ "$(kv "$body" result)" = error ]; then
			pass "$label: refused with HTTP 400 result=error"
		else
			failcase "$label: expected HTTP 400 result=error, got HTTP $code (body=$(printf "%s" "$body" | head -c 160))"
		fi
	}
	factory_refusal "" "-" "v2.1 factory: no confirmation at all"
	factory_refusal "?confirm=reset" "-" "v2.1 factory: query-only confirmation without header"
	factory_refusal "?confirm=write" "reset" "v2.1 factory: wrong confirmation value"
	assert_status_idle "v2.1 factory refusals"
	assert_no_write_stage "v2.1 factory refusals"

	# --- POST /boot: RAM-only slot override (do this last, then clear it)
	slots_text=$(curl -sS --max-time 15 "$BASE/slots" 2>/dev/null || true)
	next_slot=$(kv "$slots_text" next_slot)
	case "$next_slot" in
	0|1)
		boot_code=$(curl -sS --max-time 20 -o "$TMP/boot.body" -w "%{http_code}" -X POST --data "" "$BASE/boot?slot=$next_slot" 2>/dev/null || true)
		boot_body=$(cat "$TMP/boot.body" 2>/dev/null || true)
		if [ "$boot_code" = 200 ] && [ "$(kv "$boot_body" result)" = ok ] && [ "$(kv "$boot_body" next_slot)" = "$next_slot" ]; then
			pass "v2.1 boot: /boot?slot=$next_slot sets the RAM override (result=ok)"
		else
			failcase "v2.1 boot: /boot?slot=$next_slot expected HTTP 200 result=ok next_slot=$next_slot, got HTTP $boot_code"
		fi
		;;
	*) note "v2.1 boot: /slots did not expose a usable next_slot ($(show "$next_slot")); boot probe skipped" ;;
	esac
	boot_bad=$(curl -sS --max-time 20 -o "$TMP/boot-bad.body" -w "%{http_code}" -X POST --data "" "$BASE/boot?slot=2" 2>/dev/null || true)
	if [ "$boot_bad" = 400 ] && [ "$(kv "$(cat "$TMP/boot-bad.body" 2>/dev/null || true)" result)" = error ]; then
		pass "v2.1 boot: bad slot rejected with HTTP 400 result=error"
	else
		failcase "v2.1 boot: bad slot expected HTTP 400 result=error, got HTTP $boot_bad"
	fi
	clear_enc=$(python3 - <<'PY'
import urllib.parse
print(urllib.parse.quote("setenv e2631_next_slot", safe=""))
PY
	)
	clear_code=$(curl -sS --max-time 20 -o "$TMP/boot-clear.body" -w "%{http_code}" -X POST --data "" "$BASE/console?cmd=$clear_enc" 2>/dev/null || true)
	if [ "$clear_code" = 200 ] && [ "$(kv "$(cat "$TMP/boot-clear.body" 2>/dev/null || true)" result)" = ok ]; then
		pass "v2.1 boot: cleared the RAM override via /console setenv e2631_next_slot"
	else
		failcase "v2.1 boot: could not clear e2631_next_slot via /console (HTTP $clear_code); clear it manually at the prompt"
	fi
	assert_status_idle "v2.1 boot"
	log "v2.1 suite complete (read-only: no slot, overlay or env write was requested)"
fi


# ------------------------------------------------------------------- summary

printf '\n[e4-accept] ===== summary =====\n'
printf '[e4-accept] PASS=%d FAIL=%d NOTE=%d\n' "$PASS" "$FAIL" "$NOTES"
if [ "$FAIL" -gt 0 ]; then
	printf '[e4-accept] failures:\n'
	while IFS= read -r f; do printf '[e4-accept]   - %s\n' "$f"; done <"$TMP/failures.txt"
	printf '[e4-accept] RESULT: FAIL\n'
	exit 1
fi
printf '[e4-accept] RESULT: PASS\n'
if [ "$WRITE" = 1 ]; then
	printf '[e4-accept] NEXT: power-cycle the board (unplug/replug), then in OpenWrt run:\n'
	printf '[e4-accept]   sha256sum /dev/mtd0   # expect %s\n' "$EXPECTED_IMAGE_SHA"
	printf '[e4-accept] Do not use the U-Boot reset command (placeholder until task-76).\n'
else
	printf '[e4-accept] NEXT: net-zero validate-only run complete. mtd0 must be unchanged:\n'
	printf '[e4-accept]   sha256sum /dev/mtd0   # expect %s\n' "$EXPECTED_IMAGE_SHA"
fi
exit 0
