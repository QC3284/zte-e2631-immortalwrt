// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the single-key environment candidate builder (task-98).
 *
 * Reproduces the t92d gate conditions: the RAM environment carries runtime
 * keys (DNS dnsd_domain, console stdin/stdout, fdtcontroladdr), yet a
 * request naming only bootdelay must produce a candidate that is the flash
 * baseline block byte for byte - and two consecutive no-change requests must
 * stay byte-identical, with no malformed key anywhere.
 *
 * Copyright (C) 2026 QC3284
 */

#include <stdio.h>
#include <string.h>

#include "e2631env_build.h"

#define BLOCK_SIZE	4096
#define MAX_VIEWS	E2631_ENV_BUILD_MAX_ENTRIES

static unsigned int crc_table[256];
static int crc_ready;

static void crc_init(void)
{
	unsigned int c;
	int i, k;

	for (i = 0; i < 256; i++) {
		c = (unsigned int)i;
		for (k = 0; k < 8; k++)
			c = (c & 1) ? (0xedb88320 ^ (c >> 1)) : (c >> 1);
		crc_table[i] = c;
	}
	crc_ready = 1;
}

static unsigned int test_crc32(unsigned int crc, const unsigned char *buf,
			       unsigned int len)
{
	unsigned int i;

	if (!crc_ready)
		crc_init();
	crc ^= 0xffffffff;
	for (i = 0; i < len; i++)
		crc = (crc >> 8) ^ crc_table[(crc ^ buf[i]) & 0xff];
	return crc ^ 0xffffffff;
}

static int checks, failures;

static void check(int cond, const char *what)
{
	checks++;
	if (!cond) {
		failures++;
		printf("env candidate fixture: FAIL: %s\n", what);
	}
}

struct pair {
	const char *key;
	const char *value;
};

static int make_block(unsigned char *block, unsigned int size,
		      const struct pair *pairs, int n)
{
	unsigned int used = E2631_ENV_BUILD_HEADER;
	int i;

	memset(block, 0, size);
	for (i = 0; i < n; i++) {
		unsigned int klen = strlen(pairs[i].key);
		unsigned int vlen = strlen(pairs[i].value);
		unsigned int need = klen + vlen + 2;

		if (used + need > size)
			return -1;
		memcpy(block + used, pairs[i].key, klen);
		block[used + klen] = '=';
		memcpy(block + used + klen + 1, pairs[i].value, vlen);
		used += need;
	}
	e2631_env_build_put_le32(block, test_crc32(0,
		block + E2631_ENV_BUILD_HEADER, size - E2631_ENV_BUILD_HEADER));
	return 0;
}

static int find_view(const struct e2631_env_build_view *views, int n,
		     const char *key)
{
	int i;
	size_t len = strlen(key);

	for (i = 0; i < n; i++) {
		if (views[i].key_len == len && !memcmp(views[i].key, key, len))
			return i;
	}
	return -1;
}

static int same_view(const struct e2631_env_build_view *a,
		     const struct e2631_env_build_view *b)
{
	return a->key_len == b->key_len && a->value_len == b->value_len &&
	       !memcmp(a->key, b->key, a->key_len) &&
	       !memcmp(a->value, b->value, b->value_len);
}

static const struct pair baseline_pairs[] = {
	{ "baudrate", "115200" },
	{ "bootcmd", "setenv bootargs console=$(console); run bootargs" },
	{ "bootdelay", "3" },
	{ "e2631_flashboot", "reset" },
	{ "e2631_netboot", "tftp 0x42000000 e2631-netboot.uImage" },
	{ "ethact", "eth0" },
	{ "ethaddr", "00:41:71:00:00:50" },
	{ "gatewayip", "192.168.1.1" },
	{ "hostname", "unknown" },
	{ "ipaddr", "192.168.1.1" },
	{ "memsize", "256M" },
	{ "netmask", "255.255.255.0" },
	{ "serverip", "192.168.1.100" },
	{ "stdin", "serial" },
	{ "stdout", "serial" },
	{ "versioninfo", "U-Boot V1.0.0 20230828191152 0x2300000 0x1 0xaf 0x00" },
};

/* Runtime keys the RAM environment carried during the t92d gate. */
static const char *const runtime_keys[] = {
	"dnsd_domain", "fdtcontroladdr", "stdin_serial", "stderr_serial",
};

int main(void)
{
	unsigned char block[BLOCK_SIZE], dest[BLOCK_SIZE], again[BLOCK_SIZE];
	unsigned char malformed[BLOCK_SIZE];
	struct e2631_env_build_view base[MAX_VIEWS], views[MAX_VIEWS];
	int base_count = (int)(sizeof(baseline_pairs) / sizeof(baseline_pairs[0]));
	int base_n = 0, n = 0, i, v, rc;

	check(make_block(block, sizeof(block), baseline_pairs, base_count) == 0,
	      "baseline block builds");
	check(e2631_env_build_parse(block, sizeof(block), base, MAX_VIEWS,
				    &base_n) == 0, "baseline parses");
	check(base_n == base_count, "baseline entry count");

	/* Two consecutive no-change requests must be byte-identical. */
	rc = e2631_env_build_single(dest, sizeof(dest), block, 1,
				    "bootdelay", "3", test_crc32, &n);
	check(rc == 0, "no-change candidate builds");
	check(n == base_n, "no-change keeps the entry count");
	check(!memcmp(dest, block, sizeof(block)),
	      "no-change candidate is byte-identical");
	rc = e2631_env_build_single(again, sizeof(again), block, 1,
				    "bootdelay", "3", test_crc32, &n);
	check(rc == 0, "second no-change candidate builds");
	check(!memcmp(again, block, sizeof(block)),
	      "second no-change candidate is byte-identical");
	check(!memcmp(dest, again, sizeof(block)),
	      "two no-change candidates are identical");

	/* No runtime key may appear; the gate must stay keys=0. */
	check(e2631_env_build_parse(dest, sizeof(dest), views, MAX_VIEWS,
				    &n) == 0, "candidate parses");
	for (i = 0; i < (int)(sizeof(runtime_keys) / sizeof(runtime_keys[0])); i++)
		check(find_view(views, n, runtime_keys[i]) < 0,
		      "runtime key stays out of the candidate");
	v = find_view(views, n, "bootdelay");
	check(v >= 0 && views[v].value_len == 1 && views[v].value[0] == '3',
	      "bootdelay keeps its baseline value");
	v = find_view(views, n, "stdin");
	check(v >= 0 && views[v].value_len == 6 &&
	      !memcmp(views[v].value, "serial", 6),
	      "stdin keeps the flash value, not the live device");

	/* A real change touches only the requested key, order preserved. */
	rc = e2631_env_build_single(dest, sizeof(dest), block, 1,
				    "e2631_flashboot", "failsafe.lan",
				    test_crc32, &n);
	check(rc == 0, "change candidate builds");
	check(n == base_n, "change keeps the entry count");
	check(e2631_env_build_parse(dest, sizeof(dest), views, MAX_VIEWS,
				    &n) == 0, "change candidate parses");
	check(n == base_n, "change candidate entry count");
	for (i = 0; i < base_n; i++) {
		if (base[i].key_len == strlen("e2631_flashboot") &&
		    !memcmp(base[i].key, "e2631_flashboot",
			    base[i].key_len)) {
			check(views[i].value_len == strlen("failsafe.lan") &&
			      !memcmp(views[i].value, "failsafe.lan",
				      views[i].value_len),
			      "changed key carries the new value");
		} else {
			check(same_view(&views[i], &base[i]),
			      "other key and value are unchanged");
		}
	}
	check(e2631_env_build_le32(dest) == test_crc32(0,
		dest + E2631_ENV_BUILD_HEADER,
		sizeof(dest) - E2631_ENV_BUILD_HEADER),
	      "change candidate CRC is valid");

	/* A new whitelisted key is appended after the baseline entries. */
	rc = e2631_env_build_single(dest, sizeof(dest), block, 1,
				    "e2631_newkey", "hello world",
				    test_crc32, &n);
	check(rc == 0, "insert candidate builds");
	check(n == base_n + 1, "insert appends one entry");
	check(e2631_env_build_parse(dest, sizeof(dest), views, MAX_VIEWS,
				    &n) == 0 && n == base_n + 1,
	      "insert candidate parses");
	for (i = 0; i < base_n; i++)
		check(same_view(&views[i], &base[i]),
		      "insert keeps the baseline entry");
	v = find_view(views, n, "e2631_newkey");
	check(v == n - 1, "inserted key is last");
	check(v >= 0 && views[v].value_len == 11 &&
	      !memcmp(views[v].value, "hello world", 11),
	      "inserted value is kept");

	/* Blank block: only the requested key. */
	rc = e2631_env_build_single(dest, sizeof(dest), NULL, 0,
				    "bootdelay", "3", test_crc32, &n);
	check(rc == 0, "blank-block candidate builds");
	check(n == 1, "blank-block candidate has one entry");
	check(e2631_env_build_parse(dest, sizeof(dest), views, MAX_VIEWS,
				    &n) == 0 && n == 1,
	      "blank-block candidate parses");

	/* Malformed baseline and out-of-range requests are refused. */
	memset(malformed, 0, sizeof(malformed));
	memcpy(malformed + E2631_ENV_BUILD_HEADER, "noequals", 8);
	check(e2631_env_build_single(dest, sizeof(dest), malformed, 1,
				     "bootdelay", "3", test_crc32, &n) < 0,
	      "malformed baseline is refused");
	check(e2631_env_build_single(dest, sizeof(dest), block, 1,
				     "k012345678901234567890123456789012",
				     "x", test_crc32, &n) < 0,
	      "over-long key is refused");
	{
		char big[E2631_ENV_BUILD_VALUE_MAX + 2];

		memset(big, 'a', sizeof(big) - 1);
		big[sizeof(big) - 1] = 0;
		check(e2631_env_build_single(dest, sizeof(dest), block, 1,
					     "bootdelay", big, test_crc32,
					     &n) < 0,
		      "over-long value is refused");
	}
	check(e2631_env_build_single(dest, 16, block, 1, "bootdelay", "3",
				     test_crc32, &n) < 0,
	      "too-small block is refused");

	if (failures) {
		printf("env candidate fixture: FAIL (%d of %d checks)\n",
		       failures, checks);
		return 1;
	}
	printf("env candidate fixture: PASS (%d checks)\n", checks);
	return 0;
}
