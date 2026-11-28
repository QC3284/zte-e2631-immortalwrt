// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the telnet line hand-off (patch 0062, task-99).
 *
 * mtk_telnetd_copy_line() is the only place that turns the line editor's
 * byte buffer into a C string.  It must always terminate the destination
 * and must never leave bytes from a previous, longer command behind: on the
 * device 'version' followed by 'bdinfo' used to run as 'bdinfon'.
 *
 * Compiled and run by .github/workflows/uboot-build.yml:
 *   gcc -std=gnu11 -Wall -Wextra -Werror \
 *       -I <u-boot>/include -I uboot-port/tests/shim \
 *       uboot-port/tests/telnetd_line_test.c
 */
#include <stdio.h>
#include <string.h>

#include <net/mtk_telnetd.h>

static int checks;
static int fails;

#define CHECK(cond, what) do { \
	checks++; \
	if (!(cond)) { \
		fails++; \
		printf("FAIL: %s\n", what); \
	} \
} while (0)

int main(void)
{
	char dst[8];
	char big[257];
	char src[300];

	memset(dst, 'X', sizeof(dst));
	mtk_telnetd_copy_line(dst, sizeof(dst), "version", 7);
	CHECK(!strcmp(dst, "version"),
	      "a queued line is copied and terminated");

	mtk_telnetd_copy_line(dst, sizeof(dst), "bdinfo", 6);
	CHECK(!strcmp(dst, "bdinfo"),
	      "a shorter follow-up line leaves no stale byte");
	CHECK(dst[6] == '\0', "the terminator follows the copied bytes");

	mtk_telnetd_copy_line(dst, sizeof(dst), "abcdefgh", 8);
	CHECK(!strcmp(dst, "abcdefg"),
	      "the copy is truncated to dstsz - 1 and terminated");

	mtk_telnetd_copy_line(dst, sizeof(dst), NULL, 0);
	CHECK(dst[0] == '\0', "an empty line becomes an empty string");

	mtk_telnetd_copy_line(big, sizeof(big), NULL, 300);
	CHECK(strlen(big) == 0,
	      "a NULL source writes only the terminator, never 300 bytes");

	memset(src, 'a', sizeof(src));
	mtk_telnetd_copy_line(big, sizeof(big), src, sizeof(src));
	CHECK(strlen(big) == 256 && big[256] == '\0',
	      "a 256-byte command fits exactly in the 257-byte buffer");

	/* A short source cannot leave the tail of the previous one visible. */
	mtk_telnetd_copy_line(big, sizeof(big), "version", 7);
	mtk_telnetd_copy_line(big, sizeof(big), "bdinfo", 6);
	CHECK(!strcmp(big, "bdinfo") && big[6] == '\0',
	      "a shorter line after a longer one reads back clean");

	printf("telnetd line fixture: %s (%d checks)\n",
	       fails ? "FAIL" : "PASS", checks);

	return fails ? 1 : 0;
}
