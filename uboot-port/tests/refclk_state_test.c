// SPDX-License-Identifier: GPL-2.0+
/*
 * Host fixture for the network clock state detection (patch 0063, task-99).
 *
 * e2631_net_refclk_init() must not reprogram the PLL and the SerDes when the
 * vendor bootloader already brought them up: that is what made the first cold
 * rescue command fail with 'PHY startup failed (-110)'.  The detector is a
 * pure helper so the expected register values are pinned here.
 *
 * Compiled and run by .github/workflows/uboot-build.yml:
 *   gcc -std=gnu11 -Wall -Wextra -Werror \
 *       -I <u-boot>/board/zte/zxhn-e2631 -I uboot-port/tests/shim \
 *       uboot-port/tests/refclk_state_test.c
 */
#include <stdio.h>
#include <string.h>

#include "e2631refclk.h"

static int checks;
static int fails;

#define CHECK(cond, what) do { \
	checks++; \
	if (!(cond)) { \
		fails++; \
		printf("FAIL: %s\n", what); \
	} \
} while (0)

/* Post-init values captured from the vendor-booted chain. */
static const struct e2631_refclk_state vendor = {
	.pll_cfg0 = 0x0004176b,
	.pll_cfg1 = 0x144fdf3b,
	.top_ctrl8 = 0x10061fff,
	.crm_4c = 0x000381ff,
	.crm2_10 = 0x00000100,
	.lsp1_04 = 0x0001381b,
};

/* Values seen at a fresh prompt before any rescue ran. */
static const struct e2631_refclk_state cold = {
	.pll_cfg0 = 0x80040faa,
	.pll_cfg1 = 0x00353f7d,
	.top_ctrl8 = 0x10061fcf,
	.crm_4c = 0x00038000,
	.crm2_10 = 0x00000000,
	.lsp1_04 = 0x0000081b,
};

int main(void)
{
	struct e2631_refclk_state s;

	CHECK(e2631_refclk_is_ready(&vendor),
	      "the vendor post-init state is recognised");
	CHECK(!e2631_refclk_is_ready(&cold),
	      "the cold reset state is not recognised");
	CHECK(!e2631_refclk_is_ready(NULL),
	      "a missing snapshot is never ready");

	s = vendor;
	s.pll_cfg0 = cold.pll_cfg0;
	CHECK(!e2631_refclk_is_ready(&s), "PLL0 gates readiness");
	s = vendor;
	s.pll_cfg1 = cold.pll_cfg1;
	CHECK(!e2631_refclk_is_ready(&s), "PLL1 gates readiness");
	s = vendor;
	s.top_ctrl8 = cold.top_ctrl8;
	CHECK(!e2631_refclk_is_ready(&s), "the SerDes gate gates readiness");
	s = vendor;
	s.crm_4c = cold.crm_4c;
	CHECK(!e2631_refclk_is_ready(&s), "the CRM divider gates readiness");
	s = vendor;
	s.crm2_10 = cold.crm2_10;
	CHECK(!e2631_refclk_is_ready(&s), "the CRM2 select gates readiness");
	s = vendor;
	s.lsp1_04 = cold.lsp1_04;
	CHECK(!e2631_refclk_is_ready(&s), "the LSP1 clock gate gates readiness");

	/* The PLL lock bit lives above the 24-bit field and must be ignored. */
	s = vendor;
	s.pll_cfg1 = 0x044fdf3b;
	CHECK(e2631_refclk_is_ready(&s),
	      "the PLL1 lock bit does not change the verdict");
	s = vendor;
	s.pll_cfg1 = 0x104fdf3b;
	CHECK(e2631_refclk_is_ready(&s),
	      "PLL1 high status bits do not change the verdict");

	printf("refclk state fixture: %s (%d checks)\n",
	       fails ? "FAIL" : "PASS", checks);

	return fails ? 1 : 0;
}
