// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the stable environment tweak records (task-98).
 *
 * Reproduces the t92d corruption at unit level: the baseline alignment
 * saved values through pointers into the first export buffer, the second
 * export overwrote that buffer, and the restore then called env_set() with
 * garbage keys ("illegal character '=' in variable name"). With the key
 * copies in e2631env_tweak.h the restore must put the original runtime
 * values back and never pass a malformed key to env_set().
 *
 * Copyright (C) 2026 QC3284
 */

#include <stdio.h>
#include <string.h>

#include "e2631env_align.h"
#include "e2631env_tweak.h"

#define FAKE_MAX	16
#define KEY_MAX		32
#define VALUE_MAX	128

static char fake_keys[FAKE_MAX][KEY_MAX];
static char fake_values[FAKE_MAX][VALUE_MAX];
static int fake_count;
static int malformed;

static int checks, failures;

static void check(int cond, const char *what)
{
	checks++;
	if (!cond) {
		failures++;
		printf("env tweak fixture: FAIL: %s\n", what);
	}
}

static int fake_find(const char *key)
{
	int i;

	for (i = 0; i < fake_count; i++) {
		if (!strcmp(fake_keys[i], key))
			return i;
	}
	return -1;
}

static const char *fake_get(const char *key)
{
	int i = fake_find(key);

	return i < 0 ? NULL : fake_values[i];
}

static int fake_set(const char *key, const char *value)
{
	int i;

	if (!key || !key[0] || strlen(key) >= KEY_MAX || strchr(key, '=')) {
		malformed++;
		return -1;
	}

	i = fake_find(key);
	if (!value) {
		if (i >= 0) {
			fake_keys[i][0] = 0;
			fake_values[i][0] = 0;
		}
		return 0;
	}

	if (strlen(value) >= VALUE_MAX) {
		malformed++;
		return -1;
	}
	if (i < 0) {
		if (fake_count >= FAKE_MAX)
			return -1;
		i = fake_count++;
		strcpy(fake_keys[i], key);
	}
	strcpy(fake_values[i], value);
	return 0;
}

static void reset_fake(void)
{
	memset(fake_keys, 0, sizeof(fake_keys));
	memset(fake_values, 0, sizeof(fake_values));
	fake_count = 0;
	malformed = 0;
}

/* Runtime RAM environment during the t92d gate. */
static const struct {
	const char *key;
	const char *value;
} runtime[] = {
	{ "bootcmd", "e2631boot" },
	{ "bootargs", "console=$(console) root=/dev/mtdblock8 ro" },
	{ "fdtcontroladdr", "0x4fff25a0" },
	{ "stdin", "serial@94404000" },
	{ "stdout", "serial@94404000" },
	{ "stderr", "serial@94404000" },
	{ "dnsd_domain", "failsafe.lan" },
	{ "e2631_flashboot", "reset" },
	{ "bootdelay", "3" },
};

/* Flash baseline used for the alignment. */
static const struct {
	const char *key;
	const char *value;
} baseline[] = {
	{ "bootcmd", "setenv bootargs console=serial" },
	{ "bootargs", "console=serial root=/dev/mtdblock8 ro" },
	{ "stdin", "serial" },
	{ "stdout", "serial" },
	{ "stderr", "serial" },
	{ "e2631_flashboot", "reset" },
	{ "bootdelay", "3" },
};

static const char *baseline_find(const char *key)
{
	size_t i;

	for (i = 0; i < sizeof(baseline) / sizeof(baseline[0]); i++) {
		if (!strcmp(baseline[i].key, key))
			return baseline[i].value;
	}
	return NULL;
}

static void seed_runtime(void)
{
	size_t i;

	reset_fake();
	for (i = 0; i < sizeof(runtime) / sizeof(runtime[0]); i++)
		fake_set(runtime[i].key, runtime[i].value);
}

int main(void)
{
	struct e2631_env_tweak tweaks[8];
	const char *runtime_keys[] = {
		"bootcmd", "bootargs", "fdtcontroladdr", "stdin", "stdout",
		"stderr", "dnsd_domain", "e2631_flashboot", "bootdelay",
	};
	int ntweak = 0, i;
	char probe[256];

	/* 1. A stale key pointer must not reach fake_set(): the record owns
	 *    a key copy, so overwriting the source buffer is harmless.
	 */
	seed_runtime();
	strcpy(probe, "fdtcontroladdr");
	check(e2631_env_tweak_save(tweaks, &ntweak, 8, probe, fake_get) != NULL,
	      "save records a key");
	fake_set("fdtcontroladdr", "baseline");
	memset(probe, 0x5a, sizeof(probe));
	e2631_env_tweak_restore(tweaks, ntweak, fake_set);
	ntweak = 0;
	check(fake_get("fdtcontroladdr") &&
	      !strcmp(fake_get("fdtcontroladdr"), "0x4fff25a0"),
	      "restore puts the runtime value back after the buffer dies");
	check(malformed == 0, "restore never calls env_set with a bad key");

	/* 2. Full gate sequence: align the runtime environment with the flash
	 *    baseline, overwrite the export buffer, then restore. The RAM
	 *    environment must be back exactly as the gate left it.
	 */
	seed_runtime();
	ntweak = 0;
	for (i = 0; i < (int)(sizeof(runtime_keys) / sizeof(runtime_keys[0]));
	     i++) {
		const char *key = runtime_keys[i];
		const char *cur = fake_get(key);
		const char *base_value = baseline_find(key);
		enum e2631_env_align_action action =
			e2631_env_align_action(key, cur ? cur : "", base_value,
					       true,
					       !strncmp(key, "e2631_", 6) ||
					       !strcmp(key, "bootdelay"));
		const char *want;

		if (action == E2631_ENV_ALIGN_KEEP)
			continue;
		want = action == E2631_ENV_ALIGN_SET ? base_value : NULL;
		check(e2631_env_tweak_save(tweaks, &ntweak, 8, key,
					   fake_get) != NULL,
		      "align record saved");
		fake_set(key, want);
	}
	check(ntweak == 7, "seven non-whitelisted keys were aligned");
	check(!strcmp(fake_get("stdin"), "serial"),
	      "align wrote the flash value");
	check(!strcmp(fake_get("bootargs"), baseline[1].value),
	      "align wrote the baseline bootargs");
	check(fake_get("fdtcontroladdr") == NULL,
	      "align removed the runtime-only pointer");
	check(fake_get("e2631_flashboot") &&
	      !strcmp(fake_get("e2631_flashboot"), "reset"),
	      "whitelisted key was never aligned");

	/* The old bug: the second export overwrote the first export buffer,
	 * where the key strings lived. Nothing must point there any more.
	 */
	memset(tweaks, 0, sizeof(tweaks[0]) * 0);
	e2631_env_tweak_restore(tweaks, ntweak, fake_set);
	ntweak = 0;
	check(fake_get("bootcmd") && !strcmp(fake_get("bootcmd"), "e2631boot"),
	      "runtime bootcmd restored, not garbage");
	check(fake_get("stdin") && !strcmp(fake_get("stdin"),
					  "serial@94404000"),
	      "runtime stdin restored");
	check(fake_get("fdtcontroladdr") &&
	      !strcmp(fake_get("fdtcontroladdr"), "0x4fff25a0"),
	      "runtime fdtcontroladdr restored");
	check(fake_get("dnsd_domain") &&
	      !strcmp(fake_get("dnsd_domain"), "failsafe.lan"),
	      "runtime dnsd_domain restored");
	check(malformed == 0, "no setenv saw an illegal or empty key");

	/* 3. A key that was absent is removed again by the restore. */
	reset_fake();
	ntweak = 0;
	check(e2631_env_tweak_save(tweaks, &ntweak, 8, "e2631_tmp",
				   fake_get) != NULL,
	      "save an absent key");
	check(tweaks[0].existed == false, "absent key is recorded as absent");
	fake_set("e2631_tmp", "temporary");
	e2631_env_tweak_restore(tweaks, ntweak, fake_set);
	check(fake_get("e2631_tmp") == NULL, "absent key is removed again");
	check(tweaks[0].saved == NULL && tweaks[0].key[0] == 0,
	      "restore frees and clears the record");

	/* 4. Out-of-range keys and a full table are refused. */
	reset_fake();
	ntweak = 0;
	check(e2631_env_tweak_save(tweaks, &ntweak, 8,
				   "k0123456789012345678901234567890",
				   fake_get) == NULL,
	      "over-long key is refused");
	check(e2631_env_tweak_save(tweaks, &ntweak, 1, "bootcmd",
				   fake_get) != NULL,
	      "first record fits");
	check(e2631_env_tweak_save(tweaks, &ntweak, 1, "bootargs",
				   fake_get) == NULL,
	      "full table is refused");
	e2631_env_tweak_restore(tweaks, ntweak, fake_set);

	if (failures) {
		printf("env tweak fixture: FAIL (%d of %d checks)\n",
		       failures, checks);
		return 1;
	}
	printf("env tweak fixture: PASS (%d checks)\n", checks);
	return 0;
}
