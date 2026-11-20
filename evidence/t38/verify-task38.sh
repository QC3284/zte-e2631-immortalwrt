#!/bin/bash
# verify-task38.sh -- independent verification of the Plan C rebuild (C-验1, task-38).
#
# Reference : RUN5 44766496013 (merge-candidate lineage, tree fork 5202d4ca).
# Candidate : RUN6 44787949071 (tree fork rebuilt on immortalwrt a4ba8240, target
#             renamed sanechips -> zx279128, tip f85cbea0).
#
# usage:
#   bash verify-task38.sh <run6>                        # real run: download + full check
#   bash verify-task38.sh --selftest                    # REF release as candidate (tool self-test)
#   bash verify-task38.sh --candidate-dir DIR --tag X   # check an already-downloaded build
#
# Checks, in order:
#   1. download (gh run download + API/curl resume fallback) and sha256sum -c SHA256SUMS
#   2. SOURCE-INFO Plan C pins: iw base a4ba8240, pristine tree b905483c, port base tree
#      6136bd92, tree fork f85cbea0, feeds decf9463 / ad75cde8, kernel 6.18.60, pinned
#      APK key, and no retired merge line
#   3. extract-payload + verify_img --target zx279128 (BOOT-READY)
#   4. apk DB: kernel config hash 106ff47d unchanged, base-files 1~f85cbea, mac80211 r14,
#      fstools 5e371ec, ppp 2.5.5-r1, and the manifest carries zte-mesh and luci-app-zte-mesh
#      again (Plan C regression guard)
#   5. compare-parity RUN5 vs RUN6 with t38 policy: PASS-REVIEWED-DIFFS, unexpected 0
#   6. kernel-deep-compare RUN5 vs RUN6: STAMP-ONLY (Plan C changes no kernel input)
#   7. embedded apk key equals the pinned local PEM and no private key material
#
# Exit status: 0 only when every required check passes.
set -uo pipefail
ART=/home/qc233/zte/e2631-t5-artifacts
TOOLS="${ART}/parity-tools"
REPO=QC3284/zte-e2631-immortalwrt
KIT=/home/qc233/zte/e2631-immortalwrt
TREE=/home/qc233/zte/iwrt-tree
APK=/home/qc233/zte/e2631-apk-public-key.pem
VERIFY_PKG="${KIT}/host/verify_pkg.mjs"
REF_RUN=44766496013
REF_REL="${ART}/parity-${REF_RUN}/e2631-build-${REF_RUN}/release"
REF_BIN="${REF_REL}/e2631-immortalwrt-experimental.bin"
REF_INFO="${REF_REL}/SOURCE-INFO.txt"
EXP_KIT="${EXP_KIT:-b99d449e4e7db255b98cf3961113083e02157111}"
EXP_TREE_TIP=86cddb79802bb2223db21f7364613505174968d8
EXP_IW_SHA=a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5
EXP_IW_TREE=b905483c80a3a705825ff7aa9c77d1f3db4a01c3
EXP_PORT_TREE=6136bd92d5259dbaf22f6bca02c675f05abdf86b
EXP_PKGS=decf94639ffd6ddd26591c190b547c6b7eea150b
EXP_LUCI=ad75cde88e694b511100576bfbe0a280e5efe6ef
EXP_KERNEL_HASH=6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1
EXP_LOCAL_DER=b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d
EXP_TARGET=zx279128
POLICY="${TOOLS}/t38-policy-run5-to-run6.json"
fail=0
SELFTEST=0
CAND_DIR=""
RUN6=""
TAG=""

usage() { sed -n "2,30p" "${0}"; exit 2; }
fail_msg() { echo "[verify-task38] FAIL: $*" >&2; fail=1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --candidate-dir) CAND_DIR=${2}; shift 2 ;;
    --tag) TAG=${2}; shift 2 ;;
    --selftest) SELFTEST=1; shift ;;
    --help|-h) usage ;;
    *) RUN6=${1}; shift ;;
  esac
done
if [ "$SELFTEST" -eq 1 ]; then
  [ -n "$CAND_DIR" ] || CAND_DIR="$REF_REL"
  [ -n "$TAG" ] || TAG=selftest
fi
if [ "$SELFTEST" -eq 0 ] && [ -z "$CAND_DIR" ] && [ -z "$RUN6" ]; then usage; fi
if [ -z "$TAG" ]; then TAG=${RUN6:-unknown}; fi
WORK="${ART}/t38/${TAG}"
mkdir -p "$WORK"

find_release() {
  local d=$1 f
  f=$(find "$d" -type f -path "*/release/e2631-immortalwrt-experimental.bin" 2>/dev/null | head -1)
  if [ -n "$f" ]; then echo "$f"; return 0; fi
  f=$(find "$d" -type f -path "*/release/*.bin" 2>/dev/null | head -1)
  if [ -n "$f" ]; then echo "[warn] release asset name changed: $(basename "$f")" >&2; echo "$f"; return 0; fi
  f=$(find "$d" -type f -name "*.bin" 2>/dev/null | head -1)
  if [ -n "$f" ]; then echo "[warn] no release dir, using raw artifact bin: $f" >&2; echo "$f"; return 0; fi
  return 1
}

download_run() {
  local run=$1 dir="${ART}/parity-$1"
  if [ -f "$dir/.complete" ]; then echo "[download] $run already present ($dir)"; return 0; fi
  rm -rf "$dir"; mkdir -p "$dir"
  echo "[download] run $run -> $dir"
  if gh run download "$run" --repo "$REPO" --dir "$dir" 2>/dev/null; then : > "$dir/.complete"; return 0; fi
  echo "[download] gh run download failed, trying API archive + curl resume" >&2
  local aid url tok zip="$dir/artifact.zip" i
  aid=$(gh api "/repos/$REPO/actions/runs/$run/artifacts" --jq ".artifacts[0].id" 2>/dev/null) || aid=""
  if [ -z "$aid" ] || [ "$aid" = null ]; then echo "[download] no artifact for run $run" >&2; return 1; fi
  url=$(gh api "/repos/$REPO/actions/artifacts/$aid" --jq .archive_download_url) || return 1
  tok=$(gh auth token) || return 1
  for i in 1 2 3 4 5 6; do
    curl -sS -L -H "Authorization: Bearer $tok" -C - --retry 7 --retry-all-errors --retry-delay 2 -o "$zip" "$url" && break
    echo "[download] curl attempt $i failed, retrying" >&2
    sleep 2
  done
  unzip -t "$zip" >/dev/null 2>&1 || { echo "[download] artifact zip is not complete" >&2; return 1; }
  ( cd "$dir" && unzip -q -o artifact.zip ) || return 1
  rm -f "$zip"
  : > "$dir/.complete"
}

check_sums() {
  local bin rel
  bin=$(find_release "$1")
  if [ -z "$bin" ]; then fail_msg "no image found under $1"; return 1; fi
  rel=$(dirname "$bin")
  echo "[sums] $rel"
  ( cd "$rel" && sha256sum -c SHA256SUMS ) || { fail_msg "SHA256SUMS mismatch under $rel"; return 1; }
}

check_info() {
  local info=$1 pem_sha
  [ -f "$info" ] || { fail_msg "SOURCE-INFO missing: $info"; return 1; }
  grep -Fq -- "Kit commit: $EXP_KIT" "$info" || fail_msg "SOURCE-INFO: kit commit is not $EXP_KIT"
  grep -Fq -- "ImmortalWrt base: https://github.com/immortalwrt/immortalwrt master @ $EXP_IW_SHA" "$info" || fail_msg "SOURCE-INFO: iw base pin missing"
  grep -Fq -- "ImmortalWrt tree (pristine): $EXP_IW_TREE" "$info" || fail_msg "SOURCE-INFO: pristine tree pin missing"
  grep -Fq -- "Port base tree (4 commits applied): $EXP_PORT_TREE" "$info" || fail_msg "SOURCE-INFO: port base tree pin missing"
  grep -Fq -- "Tree fork: https://github.com/QC3284/immortalwrt e2631 @ $EXP_TREE_TIP" "$info" || fail_msg "SOURCE-INFO: tree fork pin missing"
  grep -Fq -- "Kernel: 6.18.60" "$info" || fail_msg "SOURCE-INFO: kernel 6.18.60 missing"
  grep -Fq -- "Packages commit: $EXP_PKGS" "$info" || fail_msg "SOURCE-INFO: packages feed pin missing"
  grep -Fq -- "LuCI commit: $EXP_LUCI" "$info" || fail_msg "SOURCE-INFO: luci feed pin missing"
  pem_sha=$(sha256sum "$APK" | cut -d" " -f1)
  grep -Fq -- "APK signing key: pinned input, public key sha256 $pem_sha" "$info" || fail_msg "SOURCE-INFO: pinned APK key line missing"
  grep -Fq -- "Hardware tested: NO" "$info" || fail_msg "SOURCE-INFO: hardware-tested note missing"
  if grep -q -- "Merged ImmortalWrt master:" "$info"; then fail_msg "SOURCE-INFO: retired merge line still present"; fi
  if grep -q -- "differs" "$info"; then fail_msg "SOURCE-INFO reports a pin mismatch"; fi
  echo "[info] SOURCE-INFO Plan C pins match"
}

run_compare() {
  local out=$1
  node "$TOOLS/compare-parity.mjs" "$REF_BIN" "$CAND_BIN" --apk-key "$APK" --verify-pkg "$VERIFY_PKG" --label-ref "RUN5-44766496013" --label-cand "$TAG" --ref-info "$REF_INFO" --cand-info "$CAND_INFO" --allow "$POLICY" --md "$out.md" --json "$out.json" --quiet
}

# ---------------------------------------------------------------- candidate
if [ "$SELFTEST" -eq 0 ] && [ -z "$CAND_DIR" ]; then
  download_run "$RUN6" || fail_msg "download of run $RUN6 failed"
  check_sums "${ART}/parity-$RUN6"
  CAND_BIN=$(find_release "${ART}/parity-$RUN6")
else
  CAND_BIN=$(find_release "$CAND_DIR")
fi
if [ -z "$CAND_BIN" ]; then echo "[verify-task38] no candidate image found" >&2; exit 2; fi
CAND_REL=$(dirname "$CAND_BIN")
CAND_INFO="$CAND_REL/SOURCE-INFO.txt"
echo "[candidate] $CAND_BIN"
if [ -f "$CAND_REL/SHA256SUMS" ]; then ( cd "$CAND_REL" && sha256sum -c SHA256SUMS >/dev/null ) || fail_msg "candidate SHA256SUMS mismatch"; fi
if [ "$SELFTEST" -eq 0 ]; then check_info "$CAND_INFO"; fi
[ -f "$CAND_INFO" ] || fail_msg "candidate SOURCE-INFO missing"

echo "[extract] $CAND_BIN"
node "$TOOLS/extract-payload.mjs" "$CAND_BIN" "$WORK" > "$WORK/extract.json" || fail_msg "extract-payload failed"
echo "[verify_img] boot readiness (target $EXP_TARGET)"
node "$KIT/tools/verify_img.mjs" "$WORK/payload" --tree "$TREE" --target "$EXP_TARGET" > "$WORK/verify-img.log" 2>&1 || fail_msg "verify_img reported a static blocker"
grep -q "BOOT-READY" "$WORK/verify-img.log" || fail_msg "verify_img did not report BOOT-READY"
echo "[verify_img] $(grep -m1 BOOT-READY "$WORK/verify-img.log")"
unsquashfs -cat "$WORK/payload/root" lib/apk/db/installed > "$WORK/installed.txt" 2>/dev/null
[ -s "$WORK/installed.txt" ] || fail_msg "could not read the apk installed DB"
grep -Fq "$EXP_KERNEL_HASH" "$WORK/installed.txt" || fail_msg "kernel config hash is not $EXP_KERNEL_HASH"
grep -Fq "6.18.60.7.2-r14" "$WORK/installed.txt" || fail_msg "kmod-mac80211 is not 6.18.60.7.2-r14"
grep -Fq "2026.11.07~5e371ec" "$WORK/installed.txt" || fail_msg "fstools is not 2026.11.07~5e371ec"
grep -Fq "2.5.5-r1" "$WORK/installed.txt" || fail_msg "ppp is not 2.5.5-r1"
grep -qx "P:zte-mesh" "$WORK/installed.txt" || fail_msg "plan C regression: zte-mesh missing from the manifest"
grep -qx "P:luci-app-zte-mesh" "$WORK/installed.txt" || fail_msg "plan C regression: luci-app-zte-mesh missing from the manifest"
COUNT=$(grep -c "^P:" "$WORK/installed.txt")
if [ "$SELFTEST" -eq 0 ]; then
  SHORT=$(printf "%s" "$EXP_TREE_TIP" | cut -c1-7)
  grep -Fq "1~$SHORT" "$WORK/installed.txt" || fail_msg "base-files revision is not 1~$SHORT"
fi
echo "[apk] $COUNT packages; kernel hash unchanged; zte-mesh manifest entries present"

# ---------------------------------------------------------------- comparisons
[ -f "$POLICY" ] || fail_msg "review policy missing: $POLICY"
echo "[compare] RUN5-44766496013 vs $TAG"
run_compare "$WORK/run5-vs-$TAG-reviewed" || fail_msg "comparator exited non-zero"
node "$TOOLS/t38-check-compare.mjs" "$WORK/run5-vs-$TAG-reviewed.json" "$EXP_LOCAL_DER" || fail_msg "comparator found unexplained differences"

echo "[kernel-deep] RUN5-44766496013 vs $TAG"
node "$TOOLS/kernel-deep-compare.mjs" "$REF_BIN" "$CAND_BIN" --md "$WORK/kernel-deep-$TAG.md" --json "$WORK/kernel-deep-$TAG.json" --quiet
KV=$(node "$TOOLS/t38-json-field.mjs" "$WORK/kernel-deep-$TAG.json" verdict)
echo "[kernel-deep] verdict $KV"
case "$KV" in
  IDENTICAL|IDENTICAL-DECOMPRESSED|STAMP-ONLY) : ;;
  *) fail_msg "kernel deep compare verdict $KV (Plan C expects stamp-only; investigate)" ;;
esac

echo "[results] $WORK"
if [ "$fail" -eq 0 ]; then echo "[verify-task38] OK"; exit 0; else echo "[verify-task38] FAILURES PRESENT" >&2; exit 1; fi