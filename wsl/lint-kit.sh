#!/bin/bash
. "$(dirname "$0")/../scripts/env.sh"
# Normalize line endings for every script we push to the box and prove each one
# parses under busybox ash.  Without this, a Windows-authored CRLF shows up on
# the device as a baffling "unexpected newline (expecting ")")".
#
# T-12: the device scripts ship in the tree fork (target/linux/sanechips/
# base-files); the kit keeps only the board/ helpers. Kit files may be
# CRLF-normalized in place (tracked, we own them); tree files are never
# modified - they are copied to /tmp first, because the bootstrap tree must
# stay byte-identical to the pinned commit.
set -u
cd "$E2631_KIT" || exit 1   # the repo root; out/ lives one level above
rc=0

lint_ash() {	# lint_ash <path> <label> [readonly]
	local f=$1 label=$2 tmp=/tmp/lint.sh
	[ -f "$f" ] || { echo "MISSING $f"; rc=1; return; }
	tr -d '\r' < "$f" > "$tmp"
	if /bin/busybox ash -n "$tmp" 2>/tmp/lint.err; then
		echo "OK    $label"
	else
		echo "FAIL  $label: $(head -c 120 /tmp/lint.err)"
		rc=1
	fi
}

# The board/ helpers are ours: normalize in place, then ash-check.
for f in board/*.sh; do
	[ -f "$f" ] || continue
	sed -i 's/\r$//' "$f"
	lint_ash "$f" "$f"
done

# The device scripts that ship in the tree fork, when a bootstrap tree exists.
if [ -d "${E2631_TREE:-}/target/linux/sanechips/base-files" ]; then
	while IFS= read -r f; do
		lint_ash "$f" "${f#"$E2631_TREE"/}"
	done < <(find "$E2631_TREE/target/linux/sanechips/base-files" -type f \
		\( -path '*/sbin/e2631-*' -o -path '*/etc/init.d/e2631-*' \) | sort)
else
	echo "SKIP  device tree scripts: no tree fork at ${E2631_TREE:-<unset>} (bootstrap first)"
fi

# The wsl/ helpers and the kit scripts run under bash, not ash: same CRLF
# problem, different parser.
for f in wsl/*.sh scripts/*.sh; do
	[ -f "$f" ] || continue
	sed -i 's/\r$//' "$f"
	if bash -n "$f" 2>/tmp/lintb.err; then
		echo "bash-OK  $f"
	else
		echo "bash-FAIL $f: $(head -c 160 /tmp/lintb.err)"
		rc=1
	fi
done
echo "rc=$rc"
exit $rc
