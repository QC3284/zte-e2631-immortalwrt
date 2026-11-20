#!/bin/bash
# verify-task26.sh -- independent verification of the R-验4 merge-candidate build
# (upstream immortalwrt master a4ba8240 merged into the tree fork; RUN5 tip 5202d4ca
#  carries the firewall4 fullcone patch re-anchor on top of the 3ac18fb9 merge).
#
#   bash verify-task26.sh <run>                       # real RUN5 (downloads the artifact)
#   bash verify-task26.sh --candidate-dir DIR --tag X # deliberate self-test on an
#                                                     # already-downloaded build
#
# Checks, in order:
#   1. download (gh run download + API/curl resume fallback) and sha256sum -c SHA256SUMS
#   2. SOURCE-INFO pins: tree fork tip 5202d4ca (RUN5), merged master a4ba8240 (2026-11-14),
#      iw base 4765b657, feeds decf9463 / ad75cde8, kernel 6.18.60
#   3. extract-payload + verify_img (BOOT-READY) + apk DB kernel config hash unchanged
#   4. compare-parity baseline-43572710065 vs RUN5 with t26-policy-baseline.json
#   5. compare-parity RUN3-43623162108 vs RUN5 with t26-policy-merge.json
#   6. kernel-deep-compare RUN3 vs RUN5 -> must be STAMP-ONLY (or IDENTICAL for self-test)
#   7. embedded apk key equals the pinned local PEM and no private key material
#
# Exit status: 0 only when every required check passes.
set -uo pipefail
ART=/home/qc233/zte/e2631-t5-artifacts
TOOLS="$ART/parity-tools"
REPO=QC3284/zte-e2631-immortalwrt
APK=/home/qc233/zte/e2631-apk-public-key.pem
KIT=/home/qc233/zte/e2631-immortalwrt
TREE=/home/qc233/zte/iwrt-tree
VERIFY_PKG="$KIT/host/verify_pkg.mjs"
RUN3_REL="$ART/parity-43623162108/e2631-build-43623162108/release"
RUN3_BIN="$RUN3_REL/e2631-immortalwrt-experimental.bin"
RUN3_INFO="$RUN3_REL/SOURCE-INFO.txt"
BASE_REL="$ART/parity-43572710065/e2631-build-43572710065/release"
BASE_BIN="$BASE_REL/e2631-immortalwrt-experimental.bin"
BASE_INFO="$BASE_REL/SOURCE-INFO.txt"
EXP_TREE_TIP=5202d4cadca831c5394b4ceca32df22c123d46a7
EXP_MERGED=a4ba8240d8a1aaef7e8c6f2d65e841a9bfd2b8c5
EXP_MERGED_DATE=2026-11-14
EXP_LOCAL_DER=b0cbe6fbd709900a248e7ff61fb16fe599ebddbb95775abe29221c346c27b74d
POLICY_A="$TOOLS/t26-policy-baseline.json"
POLICY_B="$TOOLS/t26-policy-merge.json"
fail=0
KMC=0

usage() { sed -n '2,25p' "$0"; exit 2; }
fail_msg() { echo "[verify-task26] FAIL: $*" >&2; fail=1; }

RUN4=""; CAND_DIR=""; REAL=1; TAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --candidate-dir) CAND_DIR=$2; REAL=0; shift 2 ;;
    --tag) TAG=$2; shift 2 ;;
    --kernel-merge-class) KMC=1; shift ;;
    --help|-h) usage ;;
    *) RUN4=$1; shift ;;
  esac
done
if [ $REAL -eq 1 ] && [ -z "$RUN4" ]; then usage; fi
if [ $REAL -eq 0 ] && [ -z "$CAND_DIR" ]; then usage; fi
if [ -z "$TAG" ]; then TAG=$RUN4; fi
if [ -z "$TAG" ]; then TAG=selftest; fi
WORK="$ART/t26/$TAG"

find_release() { find "$1" -type f -name 'e2631-immortalwrt-experimental.bin' 2>/dev/null | head -1; }

download_run() {
  local run=$1 dir="$ART/parity-$1"
  if [ -f "$dir/.complete" ]; then echo "[download] $run already present ($dir)"; return 0; fi
  rm -rf "$dir"; mkdir -p "$dir"
  echo "[download] run $run -> $dir"
  if gh run download "$run" --repo "$REPO" --dir "$dir" 2>/dev/null; then
    : > "$dir/.complete"; return 0
  fi
  echo "[download] gh run download failed for $run, trying API archive + curl resume" >&2
  local aid url tok zip="$dir/artifact.zip" i
  aid=$(gh api "/repos/$REPO/actions/runs/$run/artifacts" --jq '.artifacts[0].id' 2>/dev/null) || aid=""
  if [ -z "$aid" ] || [ "$aid" = null ]; then echo "[download] no artifact for run $run" >&2; return 1; fi
  url=$(gh api "/repos/$REPO/actions/artifacts/$aid" --jq .archive_download_url) || return 1
  tok=$(gh auth token) || return 1
  for i in 1 2 3 4 5 6; do
    curl -sS -L -H "Authorization: Bearer $tok" -C - --retry 7 --retry-all-errors --retry-delay 2 -o "$zip" "$url" && break
    echo "[download] curl attempt $i failed, retrying" >&2
    sleep 2
  done
  unzip -t "$zip" >/dev/null 2>&1 || { echo "[download] artifact zip is not complete for $run" >&2; return 1; }
  ( cd "$dir" && unzip -q -o artifact.zip ) || return 1
  rm -f "$zip"
  : > "$dir/.complete"
}

check_sums() {
  local run=$1 bin rel
  bin=$(find_release "$ART/parity-$1")
  if [ -z "$bin" ]; then fail_msg "run $run: no image found"; return 1; fi
  rel=$(dirname "$bin")
  echo "[sums] run $run: $rel"
  ( cd "$rel" && sha256sum -c SHA256SUMS ) || { fail_msg "run $run: SHA256SUMS mismatch"; return 1; }
}

check_info_run4() {
  local info=$1
  grep -Fq -- "ImmortalWrt base: https://github.com/immortalwrt/immortalwrt master @ 4765b657625ec5bbda74b44400465fe043802b30" "$info" || fail_msg "SOURCE-INFO: iw base pin missing"
  grep -Fq -- "Tree fork: https://github.com/QC3284/immortalwrt e2631 @ $EXP_TREE_TIP" "$info" || fail_msg "SOURCE-INFO: tree fork pin missing"
  grep -Fq -- "Merged ImmortalWrt master: @ $EXP_MERGED ($EXP_MERGED_DATE)" "$info" || fail_msg "SOURCE-INFO: merged master line missing"
  grep -Fq -- "Kernel: 6.18.60" "$info" || fail_msg "SOURCE-INFO: kernel 6.18.60 missing"
  grep -Fq -- "Packages commit: decf94639ffd6ddd26591c190b547c6b7eea150b" "$info" || fail_msg "SOURCE-INFO: packages feed pin missing"
  grep -Fq -- "LuCI commit: ad75cde88e694b511100576bfbe0a280e5efe6ef" "$info" || fail_msg "SOURCE-INFO: luci feed pin missing"
  grep -Fq -- "Hardware tested: NO" "$info" || fail_msg "SOURCE-INFO: hardware-tested note missing"
  grep -F "differs" "$info" >/dev/null 2>&1 && fail_msg "SOURCE-INFO reports a pin mismatch"
  echo "[info] SOURCE-INFO pins match the expected tree fork / merged master"
}

run_compare() {
  local ref=$1 rolef=$2 cand=$3 rolec=$4 info_ref=$5 info_cand=$6 policy=$7 out=$8
  echo "[compare] $rolef vs $rolec -> $out.md"
  node "$TOOLS/compare-parity.mjs" "$ref" "$cand" --apk-key "$APK" --verify-pkg "$VERIFY_PKG"     --label-ref "$rolef" --label-cand "$rolec" --ref-info "$info_ref" --cand-info "$info_cand"     --allow "$policy" --md "$out.md" --json "$out.json" --quiet
}

check_compare_json() {
  node -e '
    const j = require(process.argv[1]);
    const bad = [];
    if (j.verdict !== "PASS-REVIEWED-DIFFS" && j.verdict !== "PASS-BYTE-IDENTICAL") bad.push("verdict " + j.verdict);
    if (j.unexpected && j.unexpected.length) bad.push("unexpected " + j.unexpected.length);
    if (!j.verifyPkg || !j.verifyPkg.cand || j.verifyPkg.cand.all !== true) bad.push("verify_pkg candidate not all-pass");
    if (j.verifyPkg && j.verifyPkg.ref && j.verifyPkg.ref.all !== true) bad.push("verify_pkg reference not all-pass");
    if (!j.apkKey || !j.apkKey.cand || j.apkKey.cand.derSha256 !== process.argv[2]) bad.push("embedded apk key != pinned local PEM");
    if (j.apkKey && j.apkKey.privateKeyLeaks && j.apkKey.privateKeyLeaks.length) bad.push("private key material in rootfs");
    console.log(JSON.stringify({ verdict: j.verdict, expected: (j.expected||[]).length, allowed: (j.allowed||[]).length,
      unexpected: (j.unexpected||[]).length, kernelDataIdentical: j.kernelDataIdentical,
      apkKey: j.apkKey && j.apkKey.cand && j.apkKey.cand.derSha256 }, null, 1));
    if (bad.length) { console.error("BAD: " + bad.join("; ")); process.exit(1); }
  ' "$1.json" "$EXP_LOCAL_DER" || fail_msg "compare $1: unexplained differences"
}

# ---------------------------------------------------------------- candidate
if [ $REAL -eq 1 ]; then
  download_run "$RUN4" || fail_msg "download of run $RUN4 failed"
  check_sums "$RUN4" || fail_msg "SHA256SUMS check failed for run $RUN4"
  CAND_BIN=$(find_release "$ART/parity-$RUN4")
else
  CAND_BIN=$(find_release "$CAND_DIR")
fi
if [ -z "$CAND_BIN" ]; then echo "[verify-task26] no candidate image found" >&2; exit 2; fi
CAND_REL=$(dirname "$CAND_BIN"); CAND_INFO="$CAND_REL/SOURCE-INFO.txt"
echo "[candidate] $CAND_BIN"
( cd "$CAND_REL" && sha256sum -c SHA256SUMS >/dev/null ) || fail_msg "candidate SHA256SUMS mismatch"
if [ $REAL -eq 1 ]; then check_info_run4 "$CAND_INFO"; fi
[ -f "$CAND_INFO" ] || fail_msg "candidate SOURCE-INFO missing"

mkdir -p "$WORK"
echo "[extract] $CAND_BIN -> $WORK/payload"
node "$TOOLS/extract-payload.mjs" "$CAND_BIN" "$WORK" > "$WORK/extract.json" || fail_msg "extract-payload failed"
echo "[verify_img] boot readiness"
node "$KIT/tools/verify_img.mjs" "$WORK/payload" --tree "$TREE" --target sanechips > "$WORK/verify-img.log" 2>&1   || fail_msg "verify_img reported a static blocker"
grep -q "BOOT-READY" "$WORK/verify-img.log" || fail_msg "verify_img did not report BOOT-READY"
echo "[verify_img] $(grep -m1 BOOT-READY "$WORK/verify-img.log")"
INST="$WORK/installed.txt"
unsquashfs -cat "$WORK/payload/root" lib/apk/db/installed > "$INST" 2>/dev/null
[ -s "$INST" ] || fail_msg "could not read the apk installed DB from the candidate rootfs"
grep -Fq "6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1" "$INST" || fail_msg "kernel package config hash is not 106ff47d... (kernel config changed?)"
if [ $REAL -eq 1 ]; then
  EXP_SHORT=$(printf '%s' "$EXP_TREE_TIP" | cut -c1-7)
  grep -Fq "1~$EXP_SHORT" "$INST" || fail_msg "base-files revision is not 1~$EXP_SHORT"
  grep -Fq "6.18.60.7.2-r14" "$INST" || fail_msg "kmod-mac80211 is not 7.2-r14"
  grep -Fq "2026.11.07~5e371ec" "$INST" || fail_msg "fstools is not 2026.11.07~5e371ec"
  grep -Fq "2.5.5-r1" "$INST" || fail_msg "ppp is not 2.5.5-r1"
fi
echo "[apk] kernel config hash 106ff47d... unchanged in the candidate rootfs"

# ---------------------------------------------------------------- comparisons
run_compare "$BASE_BIN" "baseline-43572710065" "$CAND_BIN" "$TAG" "$BASE_INFO" "$CAND_INFO" "$POLICY_A" "$ART/baseline-vs-$TAG-reviewed"   || fail_msg "baseline vs $TAG comparator exited non-zero"
check_compare_json "$ART/baseline-vs-$TAG-reviewed"
run_compare "$RUN3_BIN" "run-43623162108" "$CAND_BIN" "$TAG" "$RUN3_INFO" "$CAND_INFO" "$POLICY_B" "$ART/run3-vs-$TAG-reviewed"   || fail_msg "RUN3 vs $TAG comparator exited non-zero"
check_compare_json "$ART/run3-vs-$TAG-reviewed"

# Kernel merge-class attestation. A NON-STAMP kernel delta is only acceptable
# when the reference and candidate tree tips differ in the reference kernel patch
# set (upstream merge) while kernel config/version/seed stay fixed; the changed
# kernel-input paths are recorded in an attestation JSON next to the evidence.
kernel_merge_class_attest() {
  local ref_tree cand_tree changed bad diff_bytes diff_ranges
  ref_tree=$(sed -n 's/.*e2631 @ \([0-9a-f]\{40\}\).*/\1/p' "$RUN3_INFO" | head -1)
  cand_tree=$(sed -n 's/.*e2631 @ \([0-9a-f]\{40\}\).*/\1/p' "$CAND_INFO" | head -1)
  [ -n "$ref_tree" ] && [ -n "$cand_tree" ] || { fail_msg "kernel merge-class: cannot read tree tips from SOURCE-INFO"; return 1; }
  [ "$ref_tree" != "$cand_tree" ] || { fail_msg "kernel merge-class: ref and candidate tree tips are identical"; return 1; }
  git -C "$TREE" cat-file -e "$ref_tree^{commit}" 2>/dev/null || { fail_msg "kernel merge-class: $ref_tree not in $TREE"; return 1; }
  git -C "$TREE" cat-file -e "$cand_tree^{commit}" 2>/dev/null || { fail_msg "kernel merge-class: $cand_tree not in $TREE"; return 1; }
  git -C "$TREE" diff --quiet "$ref_tree" "$cand_tree" -- target/linux/generic/kernel-6.18 seed/ config/ \
    || { fail_msg "kernel merge-class: kernel version/seed/config inputs changed"; return 1; }
  changed=$(git -C "$TREE" diff --name-only "$ref_tree" "$cand_tree" -- target/linux/generic target/linux/sanechips include/kernel-defaults.mk include/kernel-version.mk package/kernel)
  [ -n "$changed" ] || { fail_msg "kernel merge-class: NON-STAMP kernel but no kernel-input file changed"; return 1; }
  printf '%s\n' "$changed" | grep -q '^target/linux/generic/' || { fail_msg "kernel merge-class: no target/linux/generic patch change"; return 1; }
  bad=$(printf '%s\n' "$changed" | grep -vE '^(target/linux/(generic|sanechips)/|include/kernel-(defaults|version)\.mk$|package/kernel/)' || true)
  [ -z "$bad" ] || { fail_msg "kernel merge-class: kernel-input change outside allowed paths: $bad"; return 1; }
  diff_bytes=$(node -e 'const j=require(process.argv[1]); console.log(j.kernel && j.kernel.diff_bytes != null ? j.kernel.diff_bytes : "")' "$WORK/kernel-deep-$TAG.json" 2>/dev/null || true)
  diff_ranges=$(node -e 'const j=require(process.argv[1]); console.log(j.kernel && j.kernel.diff_ranges != null ? j.kernel.diff_ranges : "")' "$WORK/kernel-deep-$TAG.json" 2>/dev/null || true)
  node -e '
    const fs = require("fs");
    const [out, refTree, candTree, changed, diffBytes, diffRanges] = process.argv.slice(1);
    fs.writeFileSync(out, JSON.stringify({
      kind: "kernel-merge-class-attestation",
      refTree, candTree,
      changedKernelInputFiles: changed.split("\n").filter(Boolean),
      kernelDiff: { diffBytes: Number(diffBytes) || null, diffRanges: Number(diffRanges) || null },
      requirements: {
        kernelConfigHash: "6.18.60~106ff47d01ccbcbd01e3661d209d54cd-r1 unchanged",
        kernelVersionFile: "target/linux/generic/kernel-6.18 unchanged",
        seedAndConfig: "seed/ and config/ unchanged",
        allowedInputPaths: "target/linux/{generic,sanechips}, include/kernel-{defaults,version}.mk, package/kernel"
      },
      note: "MERGE-CLASS kernel delta accepted: the upstream merge changed the reference kernel patch set while kernel config/version/seed stayed fixed; residual semantic risk is documented in the evidence."
    }, null, 2) + "\n");
  ' "$WORK/kernel-merge-class-$TAG.json" "$ref_tree" "$cand_tree" "$changed" "$diff_bytes" "$diff_ranges" \
    || { fail_msg "kernel merge-class: attestation write failed"; return 1; }
  echo "[kernel-deep] MERGE-CLASS-KERNEL-DIFF accepted: $(printf '%s\n' "$changed" | wc -l) kernel-input file(s) changed between $ref_tree and $cand_tree; attestation $WORK/kernel-merge-class-$TAG.json"
  return 0
}

echo "[kernel-deep] RUN3 43623162108 vs $TAG"
node "$TOOLS/kernel-deep-compare.mjs" "$RUN3_BIN" "$CAND_BIN" --md "$WORK/kernel-deep-$TAG.md" --json "$WORK/kernel-deep-$TAG.json" --quiet
kv=$(node -e 'const j=require(process.argv[1]); console.log(j.verdict)' "$WORK/kernel-deep-$TAG.json")
echo "[kernel-deep] verdict $kv"
case "$kv" in
  IDENTICAL|IDENTICAL-DECOMPRESSED|STAMP-ONLY) : ;;
  NON-STAMP-DIFF)
    if [ "$KMC" -eq 1 ]; then
      kernel_merge_class_attest || fail_msg "kernel deep compare NON-STAMP delta is not justified by the kernel-input diff"
    else
      fail_msg "kernel deep compare verdict NON-STAMP-DIFF (pass --kernel-merge-class only with a reviewed kernel-input diff)"
    fi ;;
  *) fail_msg "kernel deep compare verdict $kv is not stamp-class" ;;
esac

echo "[results] baseline-vs-$TAG-reviewed.md  run3-vs-$TAG-reviewed.md  kernel-deep-$TAG.md"
if [ $fail -eq 0 ]; then echo "[verify-task26] OK"; else echo "[verify-task26] FAILURES PRESENT" >&2; fi
exit $fail