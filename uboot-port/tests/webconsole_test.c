// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the web console wire helpers (patch 0057).
 *
 * The rescue page sends POST /console/exec as multipart/form-data and reads
 * JSON from POST /console/poll.  These vectors pin the boundary parsing, the
 * form field extraction and the JSON escaping against the same
 * e2631webconsole.h the patch installs into the build.
 */
#include <stdio.h>
#include <string.h>

#include "e2631webconsole.h"

static int checks;
static int fails;

#define CHECK(cond, what) do { \
	checks++; \
	if (!(cond)) { \
		fails++; \
		printf("FAIL: %s\n", what); \
	} \
} while (0)

static const char multipart_body[] =
	"------WebKitFormBoundaryABC123\r\n"
	"Content-Disposition: form-data; name=\"token\"\r\n"
	"\r\n"
	"secret\r\n"
	"------WebKitFormBoundaryABC123\r\n"
	"Content-Disposition: form-data; name=\"cmd\"\r\n"
	"\r\n"
	"help usb\r\n"
	"------WebKitFormBoundaryABC123--\r\n";

int main(void)
{
	char boundary[128];
	char value[64];
	char json[128];
	int n;

	/* Boundary parsing: plain and quoted forms. */
	CHECK(e2631_multipart_boundary(
		      "multipart/form-data; boundary=----WebKitFormBoundaryABC123",
		      boundary, sizeof(boundary)) == 0 &&
	      !strcmp(boundary, "----WebKitFormBoundaryABC123"),
	      "plain boundary is extracted");
	CHECK(e2631_multipart_boundary(
		      "multipart/form-data; boundary=\"abc:def\"",
		      boundary, sizeof(boundary)) == 0 &&
	      !strcmp(boundary, "abc:def"),
	      "quoted boundary is extracted");
	CHECK(e2631_multipart_boundary("application/json", boundary,
				       sizeof(boundary)) == -1,
	      "a non-multipart content type has no boundary");

	/* Field extraction from the captured page request. */
	n = e2631_multipart_field(multipart_body,
				  (int)strlen(multipart_body),
				  "----WebKitFormBoundaryABC123", "cmd",
				  value, sizeof(value));
	CHECK(n == 8 && !strcmp(value, "help usb"),
	      "the cmd field value is extracted");
	n = e2631_multipart_field(multipart_body,
				  (int)strlen(multipart_body),
				  "----WebKitFormBoundaryABC123", "token",
				  value, sizeof(value));
	CHECK(n == 6 && !strcmp(value, "secret"),
	      "the token field value is extracted");
	CHECK(e2631_multipart_field(multipart_body,
				    (int)strlen(multipart_body),
				    "----WebKitFormBoundaryABC123", "missing",
				    value, sizeof(value)) == -1,
	      "a missing field reports -1");
	CHECK(e2631_multipart_field(multipart_body,
				    (int)strlen(multipart_body),
				    "----WebKitFormBoundaryABC123", "cmd",
				    value, 4) == -1,
	      "a value too large for the buffer reports -1");

	/* JSON escaping: the page renders this text in a <pre> node. */
	n = e2631_json_escape(json, sizeof(json), "a\"b\\c\nd\te", 9);
	CHECK(!strcmp(json, "a\\\"b\\\\c\\nd\\te"),
	      "quotes, backslash, newline and tab are escaped");
	CHECK(n == (int)strlen(json), "the escape returns the written length");
	n = e2631_json_escape(json, sizeof(json), "line1\r\nline2", 12);
	CHECK(!strcmp(json, "line1\\r\\nline2"),
	      "carriage returns are escaped");
	n = e2631_json_escape(json, sizeof(json), "\x01", 1);
	CHECK(!strcmp(json, "\\u0001"),
	      "other control bytes become \\u00XX");
	n = e2631_json_escape(json, sizeof(json), "plain text", 10);
	CHECK(!strcmp(json, "plain text"), "printable text is unchanged");
	n = e2631_json_escape(json, 4, "abcdef", 6);
	CHECK(strlen(json) <= 3 && n == (int)strlen(json),
	      "a small destination is respected");

	printf("webconsole fixture: %s (%d checks)\n",
	       fails ? "FAIL" : "PASS", checks);

	return fails ? 1 : 0;
}
