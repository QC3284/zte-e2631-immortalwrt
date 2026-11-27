// SPDX-License-Identifier: GPL-2.0+
/*
 * Host-side fixture for the E2631 rescue HTTP header helpers.
 *
 * The helpers live in board/zte/zxhn-e2631/e2631http.h and are compiled into
 * the rescue server. This fixture replays the header blocks a browser sends
 * for GET /status and POST /flash?mode=validate|write with the mixed-case
 * spelling HTTP uses on the wire, so a case-comparison regression fails in
 * CI instead of on the board (task-78/E4 phase-1, patch 0033).
 *
 * Build with: gcc -std=gnu11 -Wall -Wextra -Werror \
 *   -I board/zte/zxhn-e2631 uboot-port/tests/rescue_headers_test.c
 */

#include <stdio.h>
#include <string.h>

#include "e2631http.h"

static int failures;

static void check_name(const char *line, const char *name, int want)
{
	int got = e2631_http_name_is(line, name);

	if (got != want) {
		printf("FAIL name '%s' vs '%s': got %d want %d\n", line, name,
		       got, want);
		failures++;
	}
}

static void check_value(const char *block, const char *name, const char *want)
{
	char out[80];

	memset(out, 0, sizeof(out));
	if (!e2631_http_header_value(block, name, out, sizeof(out))) {
		printf("FAIL value '%s' not found\n", name);
		failures++;
		return;
	}
	if (strcmp(out, want)) {
		printf("FAIL value '%s': got '%s' want '%s'\n", name, out, want);
		failures++;
	}
}

static void check_missing(const char *block, const char *name)
{
	char out[80];

	if (e2631_http_header_value(block, name, out, sizeof(out))) {
		printf("FAIL value '%s' unexpectedly found: '%s'\n", name, out);
		failures++;
	}
}

int main(void)
{
	/* Captured POST /flash?mode=validate header block (mixed case). */
	const char *post_validate =
		"POST /flash?mode=validate HTTP/1.1\r\n"
		"Host: 192.168.1.1\r\n"
		"Connection: keep-alive\r\n"
		"Content-Length: 655360\r\n"
		"X-E2631-SHA256: 8f16817b0123456789abcdef0123456789abcdef0123456789abcdef01234567\r\n"
		"User-Agent: rescue-fixture\r\n"
		"\r\n";
	const char *post_write =
		"POST /flash?mode=write HTTP/1.1\r\n"
		"Content-Length: 655360\r\n"
		"X-E2631-SHA256: 8f16817b0123456789abcdef0123456789abcdef0123456789abcdef01234567\r\n"
		"X-E2631-Confirm: write\r\n"
		"\r\n";
	const char *send_lower =
		"POST /flash?mode=validate HTTP/1.1\r\n"
		"content-length: 655360\r\n"
		"x-e2631-sha256: abc\r\n"
		"\r\n";

	/* The name rule: case-insensitive, whole field, ':' terminator. */
	check_name("Content-Length: 655360", "Content-Length", 1);
	check_name("Content-Length: 655360", "content-length", 1);
	check_name("content-length: 655360", "Content-Length", 1);
	check_name("CONTENT-LENGTH: 655360", "Content-Length", 1);
	check_name("X-E2631-Confirm: write", "x-e2631-confirm", 1);
	check_name("Content-Length: 655360", "Content-Type", 0);
	check_name("Content-Lengths: 655360", "Content-Length", 0);
	check_name("Content-Length 655360", "Content-Length", 0);
	check_name("GET /status HTTP/1.1", "Content-Length", 0);

	/* The captured requests resolve exactly as the handler expects. */
	check_value(post_validate, "Content-Length", "655360");
	check_value(post_validate, "content-length", "655360");
	check_value(post_validate, "X-E2631-SHA256",
		    "8f16817b0123456789abcdef0123456789abcdef0123456789abcdef01234567");
	check_value(post_validate, "x-e2631-sha256",
		    "8f16817b0123456789abcdef0123456789abcdef0123456789abcdef01234567");
	check_missing(post_validate, "X-E2631-Confirm");
	check_value(post_write, "X-E2631-Confirm", "write");
	check_value(post_write, "Content-Length", "655360");
	check_missing(post_write, "X-File-Sha256");
	check_value(send_lower, "Content-Length", "655360");
	check_value(send_lower, "X-E2631-SHA256", "abc");

	if (failures) {
		printf("rescue header fixture: FAIL (%d)\n", failures);
		return 1;
	}

	printf("rescue header fixture: PASS (mixed-case GET/POST blocks resolve)\n");
	return 0;
}
