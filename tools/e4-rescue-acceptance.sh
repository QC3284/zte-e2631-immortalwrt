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
#   * every validate/write POST carries X-E2631-SHA256; a probe with a wrong
#     digest must be refused. Without --require-digest an unenforced digest is
#     reported as a loud WARNING (v1 gap) instead of being silently skipped;
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
	printf '%s\n' "usage: tools/e4-rescue-acceptance.sh --image <file> [options]" "options:" "  --host IP           device address (default 192.168.1.1)" "  --iface IFACE       host interface on the rescue link" "  --dhcp              run dhclient -1 on --iface (needs root)" "  --page PATH         local page for the served-page comparison" "  --asset-stats PATH  E2631-FAILSAFE-ASSET.txt from the build artifact" "  --write             enable the NET-ZERO write phase" "  --approval TOKEN    required with --write: $E4_APPROVAL_VALUE" "  --skip-matrix       skip the rejection matrix" "  --expected-sha SHA  expected net-zero payload sha256 (default: the 15-patch image region b1ea9a48...)" "  --require-digest    fail if the device does not enforce X-E2631-SHA256" "  --timeout SECS      write-phase poll timeout (default 600)" "  --keep-tmp          keep temporary files" "  -h, --help          this help"
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
	curl -sS --max-time 5 "http://$HOST/status" 2>/dev/null || true
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
	--image|--host|--iface|--page|--asset-stats|--approval|--timeout|--expected-sha)
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
		esac
		shift 2
		;;
	--dhcp)        DO_DHCP=1; shift ;;
	--write)       WRITE=1; shift ;;
	--skip-matrix) SKIP_MATRIX=1; shift ;;
	--require-digest) REQUIRE_DIGEST=1; shift ;;
	--keep-tmp)    KEEP_TMP=1; shift ;;
	-h|--help)     usage ;;
	*)             fatal "unknown argument: $1 (use --help)" ;;
	esac
done

[ -n "$IMAGE" ] || fatal "--image is required"

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
	failcase "page calls /reboot; per the behaviour contract the page must never trigger a reboot"
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

BASE="http://$HOST"

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
	if [ "$code" != 200 ]; then
		failcase "$ctx: validate returned HTTP $code (curl rc=$POST_RC, body='$body')"
		return 1
	fi
	if [ "$result" != ok ]; then
		failcase "$ctx: validate returned result=$(show "$result"), want ok (body='$body')"
		return 1
	fi
	if [ -z "$crc" ]; then
		failcase "$ctx: validate response has no crc32 (body='$body')"
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
	pass "$ctx: validate HTTP 200, result=ok, crc32=$crc"
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
st=$(get_status)
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
    i = d.find(b'U-Boot 20', 0x800)
    assert i > 0
    d[i] = ord('X')
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
		for want in erase blank write readback compare; do
			case "$observed" in
			*" $want "*) pass "write poll: observed stage '$want'" ;;
			*) failcase "write poll: stage '$want' was never observed (observed:$observed)" ;;
			esac
		done
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
