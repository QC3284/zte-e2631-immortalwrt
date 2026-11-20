#!/bin/bash
. "$(dirname "$0")/../scripts/env.sh"
# Land the efuse patch for real, and prove it before spending any time on
# `make world`.  T-12: the tree fork is the source of truth - patch and commit it
# in a fork working copy, push, and re-run scripts/bootstrap.sh so the build tree
# picks up the new pin.  Witnesses are printed after every step.
set -u
TREE=$E2631_TREE
echo "=== 1. patches in the build tree (the fork must carry them) ==="
ls -l "$TREE/package/kernel/mt76/patches/" 2>/dev/null | tail -6
echo "--- target kernel patches now:"
ls -l "$TREE/target/linux/zx279128/patches-6.18/" | tail -4

echo
echo "=== 2. clean + prepare the package, then look at the extracted source ==="
cd "$TREE" || exit 1
make package/kernel/mt76/clean >/tmp/mt76clean.out 2>&1; echo "clean rc=$?"
make package/kernel/mt76/{download,prepare} >/tmp/mt76prep.out 2>&1; echo "prepare rc=$?"
tail -6 /tmp/mt76prep.out
M=$(ls -d build_dir/target-*/linux-zx279128_generic/mt76-*/ 2>/dev/null | head -1)
echo "M=$M"
if [ -n "$M" ]; then
	echo "WITNESS patch-in-source=$(grep -c 'Try the file first' "$M/mt7915/eeprom.c" 2>/dev/null)"
	sed -n '/u32 eeprom_blk_size = MT7915_EEPROM_BLOCK_SIZE;/,+13p' "$M/mt7915/eeprom.c" 2>/dev/null
fi
echo
echo "=== 3. did anything delete the tree patches dir? ==="
ls -l "$TREE/package/kernel/mt76/patches/"
git -C "$TREE" status --porcelain package/kernel/mt76 | head
