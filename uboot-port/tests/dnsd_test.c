// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the minimal DNS responder shipped with the rescue page
 * (patch 0055, task-97).  It exercises the wire helpers in
 * include/net/mtk_dnsd.h: name parsing, case-insensitive matching and the
 * A-record reply layout, so the device cannot regress to a malformed answer
 * without the build failing.
 */
#include <stdio.h>
#include <string.h>

#include <net/mtk_dnsd.h>

static int checks;
static int fails;

#define CHECK(cond, what) do { \
	checks++; \
	if (!(cond)) { \
		fails++; \
		printf("FAIL: %s\n", what); \
	} \
} while (0)

/* Build a standard query for @name and @qtype; returns the packet length. */
static int build_query(unsigned char *q, const char *name, unsigned short qtype,
		       int truncate_by)
{
	int off = 12;
	const char *p = name;

	memset(q, 0, 512);
	q[0] = 0x12;
	q[1] = 0x34;
	q[2] = 0x01;
	q[3] = 0x00;
	q[5] = 1;

	while (*p) {
		const char *dot = strchr(p, '.');
		int len = dot ? (int)(dot - p) : (int)strlen(p);
		int i;

		q[off++] = (unsigned char)len;
		for (i = 0; i < len; i++)
			q[off++] = (unsigned char)p[i];
		p += len;
		if (*p == '.')
			p++;
	}
	q[off++] = 0;
	q[off++] = qtype >> 8;
	q[off++] = qtype & 0xff;
	q[off++] = 0;
	q[off++] = 1;

	return off - truncate_by;
}

static unsigned int get16(const unsigned char *p)
{
	return ((unsigned int)p[0] << 8) | p[1];
}

int main(void)
{
	unsigned char q[512];
	unsigned char out[512];
	int qlen;
	int name_len;
	int len;
	unsigned int ip = 0xc0a80101; /* 192.168.1.1 in network order */

	qlen = build_query(q, "rescue.local", MTK_DNSD_TYPE_A, 0);
	CHECK(qlen == 12 + 14 + 4, "the rescue.local query is 30 bytes");

	name_len = mtk_dnsd_parse_name_len(q, qlen, 12);
	CHECK(name_len == 14, "the encoded name is 14 octets");
	CHECK(mtk_dnsd_name_matches(q, qlen, 12, "rescue.local"),
	      "the configured domain matches");
	CHECK(!mtk_dnsd_name_matches(q, qlen, 12, "other.local"),
	      "a different name does not match");
	CHECK(!mtk_dnsd_name_matches(q, qlen, 12, "rescue"),
	      "a prefix of the name does not match");
	CHECK(!mtk_dnsd_name_matches(q, qlen, 12, "rescue.local.extra"),
	      "a longer name does not match");

	/* Matching is case-insensitive on both sides. */
	qlen = build_query(q, "RESCUE.LOCAL", MTK_DNSD_TYPE_A, 0);
	CHECK(mtk_dnsd_name_matches(q, qlen, 12, "rescue.local"),
	      "an upper-case query still matches");
	qlen = build_query(q, "rescue.local", MTK_DNSD_TYPE_A, 0);
	CHECK(mtk_dnsd_name_matches(q, qlen, 12, "Rescue.LoCaL"),
	      "a mixed-case domain still matches");

	/* A-record answer: header + question + 16-byte answer. */
	len = mtk_dnsd_build_reply(q, 12, 14, MTK_DNSD_RCODE_NOERROR, ip,
				   out, sizeof(out));
	CHECK(len == 12 + 14 + 4 + 16, "the A answer is 46 bytes");
	CHECK((get16(out) >> 8) == 0x12 && (out[1]) == 0x34,
	      "the transaction id is echoed");
	CHECK((out[2] & 0x80) && (out[2] & 0x04), "QR and AA are set");
	CHECK((out[3] & 0x0f) == MTK_DNSD_RCODE_NOERROR, "rcode is NOERROR");
	CHECK(get16(out + 4) == 1, "one question is echoed");
	CHECK(get16(out + 6) == 1, "one answer is present");
	CHECK(get16(out + 8) == 0 && get16(out + 10) == 0,
	      "authority and additional counts are zero");
	CHECK(!memcmp(out + 12, q + 12, 14 + 4),
	      "the question section is copied verbatim");
	CHECK(out[12 + 14 + 4] == 0xc0 && out[12 + 14 + 5] == 0x0c,
	      "the answer name is a pointer to offset 12");
	CHECK(get16(out + 12 + 14 + 4 + 2) == MTK_DNSD_TYPE_A,
	      "the answer type is A");
	CHECK(get16(out + 12 + 14 + 4 + 4) == MTK_DNSD_CLASS_IN,
	      "the answer class is IN");
	CHECK(((unsigned long)out[12 + 14 + 4 + 6] << 24 |
	       (unsigned long)out[12 + 14 + 4 + 7] << 16 |
	       (unsigned long)out[12 + 14 + 4 + 8] << 8 |
	       out[12 + 14 + 4 + 9]) == MTK_DNSD_TTL, "the TTL is 300");
	CHECK(get16(out + 12 + 14 + 4 + 10) == 4, "RDLENGTH is 4");
	CHECK(!memcmp(out + 12 + 14 + 4 + 12, &ip, 4),
	      "the address is stored in network order");

	/* NXDOMAIN and a zero address carry no answer record. */
	len = mtk_dnsd_build_reply(q, 12, 14, MTK_DNSD_RCODE_NXDOMAIN, 0,
				   out, sizeof(out));
	CHECK(len == 12 + 14 + 4, "the NXDOMAIN reply has no answer");
	CHECK((out[3] & 0x0f) == MTK_DNSD_RCODE_NXDOMAIN,
	      "the NXDOMAIN rcode is set");
	CHECK(get16(out + 6) == 0, "NXDOMAIN ANCOUNT is zero");
	len = mtk_dnsd_build_reply(q, 12, 14, MTK_DNSD_RCODE_NOERROR, 0,
				   out, sizeof(out));
	CHECK(len == 12 + 14 + 4 && get16(out + 6) == 0,
	      "a zero address produces no answer");

	/* A short output buffer is refused, not overrun. */
	len = mtk_dnsd_build_reply(q, 12, 14, MTK_DNSD_RCODE_NOERROR, ip,
				   out, 12 + 14 + 4 + 15);
	CHECK(len == -1, "a too-small answer buffer is rejected");
	len = mtk_dnsd_build_reply(q, 12, 14, MTK_DNSD_RCODE_NXDOMAIN, 0,
				   out, 12 + 14 + 3);
	CHECK(len == -1, "a too-small NXDOMAIN buffer is rejected");

	/* Truncated packets are reported, not read out of bounds. */
	CHECK(mtk_dnsd_parse_name_len(q, 12, 12) == 0,
	      "a packet that ends before the name is rejected");

	printf("dnsd fixture: %s (%d checks)\n", fails ? "FAIL" : "PASS", checks);

	return fails ? 1 : 0;
}
