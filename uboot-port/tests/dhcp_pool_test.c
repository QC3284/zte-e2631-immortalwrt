// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the rescue DHCP pool validation (task-93 defect).
 *
 * The rescue page reads four e2631_dhcp_* environment keys and must fall
 * back to its built-in values only when a key is really unusable.  The
 * task-93 Phase A device run found /status reporting
 * dhcp_source=fallback on a CLEAN environment: the host octet of
 * 192.168.1.1 was taken from the raw network-order word (& 0xff on a
 * little-endian machine yields 192, the FIRST octet) and 192 was then
 * wrongly found inside the default pool 100..200.
 *
 * These vectors pin the correct behaviour: last octet via ntohl(), clean
 * defaults accepted, and a server address inside the pool rejected.
 *
 * Copyright (C) 2026 QC3284
 */

#include <stdio.h>

#include "e2631dhcp.h"

/* s_addr values as they sit in memory: 192.168.1.x is C0 A8 01 xx. */
#define IP_192_168_1_1		0x0101a8c0U
#define IP_192_168_1_50		0x3201a8c0U
#define IP_192_168_1_100	0x6401a8c0U
#define IP_192_168_1_200	0xc801a8c0U
#define IP_192_168_1_201	0xc901a8c0U
#define IP_10_0_0_1		0x0100000aU

static int failures;
static int checks;

#define CHECK(cond, name) do { \
	checks++; \
	if (!(cond)) { \
		failures++; \
		printf("FAIL: %s\n", name); \
	} \
} while (0)

int main(void)
{
	CHECK(e2631_dhcp_host_octet(IP_192_168_1_1) == 1,
	      "192.168.1.1 host octet is 1");
	CHECK(e2631_dhcp_host_octet(IP_10_0_0_1) == 1,
	      "10.0.0.1 host octet is 1");
	CHECK(e2631_dhcp_host_octet(IP_192_168_1_100) == 100,
	      "192.168.1.100 host octet is 100");
	/* The task-93 regression: the first octet must not be returned. */
	CHECK(e2631_dhcp_host_octet(IP_192_168_1_1) != 0xc0,
	      "192.168.1.1 must not read as its first octet");

	/* Clean defaults (server .1, pool 100..200) must be accepted. */
	CHECK(e2631_dhcp_pool_ok(IP_192_168_1_1, 100, 101),
	      "clean defaults are not a fallback");
	CHECK(e2631_dhcp_pool_ok(IP_10_0_0_1, 100, 101),
	      "a 10/8 server keeps the default pool");
	/* A server address inside the pool is a real collision. */
	CHECK(!e2631_dhcp_pool_ok(IP_192_168_1_100, 100, 101),
	      "pool start collides with the server");
	CHECK(!e2631_dhcp_pool_ok(IP_192_168_1_200, 100, 101),
	      "pool end collides with the server");
	CHECK(e2631_dhcp_pool_ok(IP_192_168_1_201, 100, 101),
	      "server just past the pool is accepted");
	CHECK(e2631_dhcp_pool_ok(IP_192_168_1_50, 100, 101),
	      "server below the pool is accepted");

	/* Range edges: pool must stay inside 1..254. */
	CHECK(e2631_dhcp_pool_ok(IP_192_168_1_1, 200, 55),
	      "pool 200..254 is accepted");
	CHECK(!e2631_dhcp_pool_ok(IP_192_168_1_1, 200, 56),
	      "pool 200..255 is rejected");
	CHECK(!e2631_dhcp_pool_ok(IP_192_168_1_1, 0, 10),
	      "pool starting at 0 is rejected");
	CHECK(!e2631_dhcp_pool_ok(IP_192_168_1_1, 1, 0),
	      "empty pool is rejected");

	if (failures) {
		printf("rescue dhcp pool fixture: FAIL (%d/%d checks)\n",
		       failures, checks);
		return 1;
	}
	printf("rescue dhcp pool fixture: PASS (%d checks)\n", checks);
	return 0;
}