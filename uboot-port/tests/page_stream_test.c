// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the rescue page chunk arithmetic (patch 0053).
 *
 * GET / must stream the embedded gzip page instead of copying it into the
 * 16 KiB e2631_rescue_conn.out: the E4 v3 asset is 24904 bytes and the v3
 * release hit the copy path, reset the connection and served nothing.  The
 * CI passes the real gzip length from the generated asset as
 * -DE2631_PAGE_LEN=<n>; the default below is the v3 page for manual runs.
 */
#include <stdio.h>
#include <string.h>

#include "e2631page.h"

#ifndef E2631_PAGE_LEN
#define E2631_PAGE_LEN 24904U
#endif

#define PAGE_OUT_MAX 16384U
#define PAGE_CHUNK 4096U

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
	unsigned int off = 0;
	unsigned int chunks = 0;
	unsigned int total = 0;
	unsigned int n;

	CHECK(E2631_PAGE_LEN > PAGE_OUT_MAX,
	      "the page must be larger than one response buffer");
	CHECK(e2631_page_chunk_len(0, E2631_PAGE_LEN, PAGE_CHUNK) == PAGE_CHUNK,
	      "the first chunk is full");
	while ((n = e2631_page_chunk_len(off, E2631_PAGE_LEN, PAGE_CHUNK))) {
		CHECK(n <= PAGE_CHUNK, "the chunk is capped at the chunk size");
		off += n;
		total += n;
		chunks++;
		if (chunks > 1000) {
			printf("FAIL: chunk loop did not terminate\n");
			return 1;
		}
	}
	CHECK(off == E2631_PAGE_LEN, "the walk ends exactly at the page length");
	CHECK(total == E2631_PAGE_LEN, "the chunks add up to the page length");
	CHECK(chunks == (E2631_PAGE_LEN + PAGE_CHUNK - 1) / PAGE_CHUNK,
	      "the chunk count is the ceiling division");
	CHECK(e2631_page_chunk_len(E2631_PAGE_LEN, E2631_PAGE_LEN,
				   PAGE_CHUNK) == 0,
	      "an exhausted page asks for no more data");
	CHECK(e2631_page_chunk_len(0, 0, PAGE_CHUNK) == 0,
	      "an empty page asks for no data");
	CHECK(e2631_page_chunk_len(0, 100, 0) == 0,
	      "a zero chunk size asks for no data");
	CHECK(e2631_page_chunk_len(90, 100, PAGE_CHUNK) == 10,
	      "the tail chunk is truncated to the remaining bytes");

	printf("page stream fixture: %s (%d checks, %u chunks, %u bytes)\n",
	       fails ? "FAIL" : "PASS", checks, chunks, E2631_PAGE_LEN);

	return fails ? 1 : 0;
}
