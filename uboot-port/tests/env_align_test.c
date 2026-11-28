// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the environment baseline-alignment rule (patch 0058).
 *
 * The t92c device probe hit a 403 "key is not writable" on a genuine
 * no-change write: the candidate block exported the RAM environment, which
 * carries runtime-only values (fdtcontroladdr, serial@9440... stdio) that
 * are not in the flash block.  The rule pinned here decides, per key,
 * whether the candidate keeps the RAM value, takes the flash value or
 * drops the key.
 *
 * It includes the same e2631env_align.h the patch installs into the tree.
 */
#include <stdio.h>
#include <string.h>

#include "e2631env_align.h"

static int checks;
static int fails;

#define CHECK(cond, what) do { \
	checks++; \
	if (!(cond)) { \
		fails++; \
		printf("FAIL: %s\n", what); \
	} \
} while (0)

static enum e2631_env_align_action
act(const char *key, const char *value, const char *base, bool valid,
    bool whitelisted)
{
	return e2631_env_align_action(key, value, base, valid, whitelisted);
}

int main(void)
{
	/* Whitelisted keys always keep the RAM value (the web write target). */
	CHECK(act("e2631_dhcp_pool_start", "254", NULL, true, true) ==
	      E2631_ENV_ALIGN_KEEP, "whitelisted key keeps its RAM value");
	CHECK(act("bootdelay", "5", "3", true, true) == E2631_ENV_ALIGN_KEEP,
	      "bootdelay is whitelisted too");

	/* Runtime stdio values align with flash when the baseline exists. */
	CHECK(act("stdout", "serial@94404000", "serial", true, false) ==
	      E2631_ENV_ALIGN_SET, "serial@... takes the flash value");
	CHECK(act("stdout", "serial", "serial", true, false) ==
	      E2631_ENV_ALIGN_KEEP, "an equal stdio value is left alone");
	CHECK(act("stderr", "serial@94404000", NULL, true, false) ==
	      E2631_ENV_ALIGN_DELETE,
	      "a runtime key missing from flash is dropped");

	/* The device-tree pointer is never persisted. */
	CHECK(act("fdtcontroladdr", "4fff25a0", NULL, true, false) ==
	      E2631_ENV_ALIGN_DELETE,
	      "fdtcontroladdr is dropped against a valid baseline");
	CHECK(act("fdtcontroladdr", "4fff25a0", NULL, false, false) ==
	      E2631_ENV_ALIGN_DELETE,
	      "fdtcontroladdr is dropped without a baseline as well");

	/* Vendor keys present in flash keep or take the flash value. */
	CHECK(act("bootcmd", "e2631boot", "zboot", true, false) ==
	      E2631_ENV_ALIGN_SET, "a vendor key takes the flash value");
	CHECK(act("bootargs", "console=ttyAMA0", "console=ttyAMA0", true,
		  false) == E2631_ENV_ALIGN_KEEP,
	      "an equal vendor key is left alone");

	/* Without a usable baseline only the store pointer is special. */
	CHECK(act("stdout", "serial@94404000", NULL, false, false) ==
	      E2631_ENV_ALIGN_KEEP,
	      "stdio stays as RAM has it on a blank block");
	CHECK(act("bootcmd", "e2631boot", NULL, false, false) ==
	      E2631_ENV_ALIGN_KEEP,
	      "vendor keys stay on a blank block");

	/* The no-change case the probe needed: baseline equal + runtime equal. */
	CHECK(act("stdout", "serial", "serial", true, false) ==
	      E2631_ENV_ALIGN_KEEP, "no-change stdio produces no tweak");
	CHECK(act("fdtcontroladdr", "4fff25a0", NULL, true, false) !=
	      E2631_ENV_ALIGN_KEEP, "no-change run still drops the pointer");

	printf("env align fixture: %s (%d checks)\n",
	       fails ? "FAIL" : "PASS", checks);

	return fails ? 1 : 0;
}
