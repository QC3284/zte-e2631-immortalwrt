#!/bin/bash
# Gate: NOTICE and the tree must agree in both directions (P1-6 验收 B).
#   - every path NOTICE mentions exists (kit paths in this repo, tree: paths in
#     the tree fork when a bootstrap tree exists);
#   - every file that MUST be listed (third-party material) is mentioned.
#
# T-12: the zte-mesh vendor tarball moved into the tree fork. NOTICE names it
# with a "tree:" prefix so the gate knows which repository to look in; the kit
# itself no longer carries overlay/.
set -u
cd "$(dirname "$0")/.." || exit 1
. scripts/env.sh
rc=0

MUST=(
	tree:package/e2631/zte-mesh/zte-mesh-runtime.tar.gz
	seed/vendor-verhdr-8b8.bin
)
is_tree_path() { case "$1" in tree:*) return 0 ;; *) return 1 ;; esac; }
strip_tree() { printf '%s' "${1#tree:}"; }

# paths mentioned in NOTICE: strip the leading "N. " numbering
while IFS= read -r p; do
	if is_tree_path "$p"; then
		rel=$(strip_tree "$p")
		if [ -d "${E2631_TREE:-}/target/linux/sanechips" ]; then
			[ -e "$E2631_TREE/$rel" ] ||
				{ echo "HIT  NOTICE mentions '$p' which is missing from $E2631_TREE"; rc=1; }
		fi
	elif [ ! -e "$p" ]; then
		echo "HIT  NOTICE mentions '$p' which does not exist"
		rc=1
	fi
done < <(sed -n 's/^[0-9]\+\. \([^ ].*\)$/\1/p' NOTICE)

for f in "${MUST[@]}"; do
	rel=$(strip_tree "$f")
	if is_tree_path "$f"; then
		if [ -d "${E2631_TREE:-}/target/linux/sanechips" ] && [ ! -e "$E2631_TREE/$rel" ]; then
			echo "HIT  $f must be listed in NOTICE but is missing from the tree"
			rc=1
		fi
	else
		[ -e "$f" ] ||
			{ echo "HIT  $f must be listed in NOTICE but is missing from the tree"; rc=1; }
	fi
	if ! grep -qF "$f" NOTICE; then
		echo "HIT  $f is third-party material and must appear in NOTICE"
		rc=1
	fi
done

[ $rc -eq 0 ] && echo "notice-check: NOTICE and the tree agree (0 missing / 0 extra)"
exit $rc
