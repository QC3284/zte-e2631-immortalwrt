// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the console command guard and the untruncated URI parse
 * (patch 0054).
 *
 * The v3 probe showed POST /console?cmd=<257 bytes> passing the length guard:
 * the request parser had copied the URI into a 96-byte buffer, so the value
 * looked like 82 bytes.  The parser now points into the raw header line, and
 * e2631_query_raw_len() measures the full value.  This fixture pins the
 * 256/257 boundary, the query scanning and the parse of a 275-byte URI that
 * does not fit the old fixed path buffer.
 *
 * It includes the same e2631query.h the patch installs into the U-Boot tree,
 * so a drift between the tested header and the shipped one fails the build.
 */
#include <stdio.h>
#include <string.h>

#include "e2631query.h"

static int checks;
static int fails;

#define CHECK(cond, what) do { \
	checks++; \
	if (!(cond)) { \
		fails++; \
		printf("FAIL: %s\n", what); \
	} \
} while (0)

static char cmd[8 + 257 + 1];

static void build_cmd(unsigned int len)
{
	unsigned int i;

	memcpy(cmd, "cmd=", 4);
	for (i = 0; i < len; i++)
		cmd[4 + i] = 'a';
	cmd[4 + len] = 0;
}

/* Split "METHOD URI HTTP/1.1" the way rescue_handle_request() does. */
static int split_request(char *line, char **path, char **query)
{
	char *sp1;
	char *sp2;

	sp1 = strchr(line, ' ');
	if (!sp1)
		return -1;
	sp2 = strchr(sp1 + 1, ' ');
	if (!sp2)
		return -1;
	*sp2 = 0;
	*path = sp1 + 1;
	*query = strchr(*path, '?');
	if (!*query)
		return -1;
	*(*query)++ = 0;

	return 0;
}

int main(void)
{
	char line[512];
	char query[3 + 8 + 257 + 8 + 1];
	char *path = NULL;
	char *q = NULL;
	int n;

	/* The guard boundary: 256 accepted, 257 rejected. */
	CHECK(e2631_console_cmd_len_ok(256), "256 bytes are accepted");
	CHECK(!e2631_console_cmd_len_ok(257), "257 bytes are rejected");
	CHECK(!e2631_console_cmd_len_ok(0), "an empty command is rejected");
	CHECK(!e2631_console_cmd_len_ok(-1), "a missing command is rejected");

	/* Raw length is measured on the full value, never on a copy. */
	build_cmd(257);
	CHECK(e2631_query_raw_len(cmd, "cmd=") == 257,
	      "the 257-byte value is measured in full");
	build_cmd(256);
	CHECK(e2631_query_raw_len(cmd, "cmd=") == 256,
	      "the 256-byte value is measured in full");
	CHECK(e2631_query_raw_len(cmd, "part=") == -1,
	      "an absent key reports -1");

	/* The key can sit between other parameters. */
	snprintf(query, sizeof(query), "x=1&cmd=%s&y=2", cmd + 4);
	CHECK(e2631_query_raw_len(query, "cmd=") == 256,
	      "the length stops at the following ampersand");

	/* A URI that does not fit the old 96-byte path buffer must parse
	 * completely: 269 bytes of URI, 257-byte command. */
	build_cmd(257);
	snprintf(line, sizeof(line), "POST /console?cmd=%s HTTP/1.1", cmd + 4);
	CHECK(split_request(line, &path, &q) == 0,
	      "a 275-byte request line splits");
	if (path && q) {
		CHECK(!strcmp(path, "/console"),
		      "the path is the full endpoint, not a prefix");
		n = e2631_query_raw_len(q, "cmd=");
		CHECK(n == 257, "the full query reaches the guard");
		CHECK(!e2631_console_cmd_len_ok(n),
		      "the 257-byte request is refused before any copy");
	} else {
		CHECK(0, "request line parse produced a path and query");
	}

	/* The same request line with a 256-byte command is accepted. */
	build_cmd(256);
	snprintf(line, sizeof(line), "POST /console?cmd=%s HTTP/1.1", cmd + 4);
	CHECK(split_request(line, &path, &q) == 0,
	      "a 274-byte request line splits");
	if (path && q) {
		n = e2631_query_raw_len(q, "cmd=");
		CHECK(n == 256 && e2631_console_cmd_len_ok(n),
		      "the 256-byte request still reaches the handler");
	}

	printf("console query fixture: %s (%d checks)\n",
	       fails ? "FAIL" : "PASS", checks);

	return fails ? 1 : 0;
}
