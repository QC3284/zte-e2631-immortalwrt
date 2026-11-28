// SPDX-License-Identifier: GPL-2.0+
/*
 * Host golden-vector fixture for the shared E2631 slot core.
 *
 * The kit keeps a byte-identical copy of the U-Boot shared source under
 * tests/native/uboot/ and uboot-build.yml compares it with the file that
 * git am puts into the U-Boot tree.  This fixture then runs the semantics
 * the rescue UI relies on, so a behaviour change cannot ride along with a
 * harmless-looking edit:
 *
 *   - the package validation order and every error category
 *   - the kernel/rootfs geometry read back from the version header
 *   - identity of empty / vendor / our / unknown headers
 *   - the target and fallback guard matrix
 *   - the serial stamping (H_SLOT_START, H_SERIAL, H_NEW, H_CRC2)
 *
 * The vectors are self-contained: the package image is synthesised here and
 * its CRCs are computed with the same shared implementation.
 *
 * Copyright (C) 2026 QC3284
 */

#include <stdio.h>
#include <string.h>

#include "e2631_slotcore.h"

#define PKG_LEN		0x314U
#define PKG_HDR_OFF	0x14U
#define PKG_BODY_OFF	0x214U
#define PKG_BODY_LEN	0x100U
#define PKG_KOFF	0x234U
#define PKG_KSZ		0x40U
#define PKG_FOFF	0x274U
#define PKG_FSZ		0x40U

static int failures;
static int checks;

#define CHECK(cond, name) do { \
	checks++; \
	if (!(cond)) { \
		failures++; \
		printf("slot core fixture: FAIL %s (line %d)\n", name, __LINE__); \
	} \
} while (0)

static void fix_header_crcs(u8 *img)
{
	u8 *hdr = img + PKG_HDR_OFF;

	e2631_slotcore_wr32(hdr, E2631_H_CRC,
			    e2631_slotcore_crc32(0, hdr, E2631_H_CRC));
	e2631_slotcore_wr32(hdr, E2631_H_CRC2,
			    e2631_slotcore_crc32(0, hdr, E2631_H_CRC2));
}

static void put_header(u8 *img)
{
	u8 *hdr = img + PKG_HDR_OFF;

	memset(hdr, 0, E2631_VER_HDR_SIZE);
	memset(hdr + E2631_H_INNER_MAGIC, 0x33, 4);
	memset(hdr + E2631_H_INNER_MAGIC + 4, 0x66, 4);
	memset(hdr + E2631_H_INNER_MAGIC + 8, 0x99, 4);
	memset(hdr + E2631_H_INNER_MAGIC + 12, 0xcc, 4);
	memcpy(hdr + E2631_H_VERSION, "ImmortalWrt v1.10.0", 19);
	memcpy(hdr + E2631_H_PRODUCT, E2631_PRODUCT_STRING,
	       E2631_PRODUCT_LEN);
	e2631_slotcore_wr32(hdr, E2631_H_FW_SIZE, PKG_BODY_LEN);
	e2631_slotcore_wr32(hdr, E2631_H_KERNEL_SIZE, PKG_KSZ);
	e2631_slotcore_wr32(hdr, E2631_H_KERNEL_FILEOFS, PKG_KOFF);
	e2631_slotcore_wr32(hdr, E2631_H_FS_SIZE, PKG_FSZ);
	e2631_slotcore_wr32(hdr, E2631_H_FS_FILEOFS, PKG_FOFF);
	e2631_slotcore_wr32(hdr, E2631_H_SLOT0, E2631_SLOT0_BASE);
	e2631_slotcore_wr32(hdr, E2631_H_SLOT1, E2631_SLOT1_BASE);
	e2631_slotcore_wr32(hdr, E2631_H_BOOT_INCLUDED, 0);
	e2631_slotcore_wr32(hdr, E2631_H_SERIAL, 0);
	e2631_slotcore_wr32(hdr, E2631_H_KERNEL_CRC,
			    e2631_slotcore_crc32(0, img + PKG_KOFF, PKG_KSZ));
	e2631_slotcore_wr32(hdr, E2631_H_FS_CRC,
			    e2631_slotcore_crc32(0, img + PKG_FOFF, PKG_FSZ));
	fix_header_crcs(img);
}

static void make_package(u8 *img)
{
	u32 i;

	memset(img, 0, PKG_LEN);
	memset(img, 0x99, 4);
	memset(img + 4, 0x44, 4);
	memset(img + 8, 0x55, 4);
	memset(img + 12, 0xaa, 4);
	e2631_slotcore_wr32(img, 0x10, 0);
	for (i = PKG_BODY_OFF; i < PKG_LEN; i++)
		img[i] = (u8)(i * 7 + 3);
	put_header(img);
}

static enum e2631_pkg_error parse(const u8 *img, u32 len)
{
	struct e2631_pkg pkg;

	return e2631_slotcore_pkg_parse(img, len, &pkg);
}

static int test_parse(void)
{
	u8 img[PKG_LEN];
	struct e2631_pkg pkg;
	struct e2631_slot_regions regions;
	enum e2631_pkg_error err;

	make_package(img);
	err = e2631_slotcore_pkg_parse(img, PKG_LEN, &pkg);
	CHECK(err == E2631_PKG_OK, "package parses");
	CHECK(pkg.body_off == PKG_BODY_OFF, "body offset");
	CHECK(pkg.body_len == PKG_BODY_LEN, "body length");
	CHECK(pkg.hdr == img + PKG_HDR_OFF, "header pointer");
	CHECK(!strcmp(e2631_slotcore_error_name(err), "ok"), "ok name");

	CHECK(parse(img, 0x213) == E2631_PKG_TOO_SMALL, "too small");
	CHECK(parse(img, E2631_PKG_MAX + 1) == E2631_PKG_TOO_LARGE,
	      "too large");

	img[3] ^= 0xff;
	CHECK(parse(img, PKG_LEN) == E2631_PKG_BAD_OUTER_MAGIC, "outer magic");
	img[3] ^= 0xff;

	img[PKG_HDR_OFF + E2631_H_INNER_MAGIC] ^= 0xff;
	CHECK(parse(img, PKG_LEN) == E2631_PKG_BAD_INNER_MAGIC, "inner magic");
	img[PKG_HDR_OFF + E2631_H_INNER_MAGIC] ^= 0xff;

	img[PKG_HDR_OFF + E2631_H_CRC] ^= 0xff;
	CHECK(parse(img, PKG_LEN) == E2631_PKG_HEADER_CRC, "header crc1");
	img[PKG_HDR_OFF + E2631_H_CRC] ^= 0xff;

	img[PKG_HDR_OFF + E2631_H_CRC2] ^= 0xff;
	CHECK(parse(img, PKG_LEN) == E2631_PKG_HEADER_CRC, "header crc2");
	img[PKG_HDR_OFF + E2631_H_CRC2] ^= 0xff;

	img[PKG_HDR_OFF + E2631_H_PRODUCT] = 'X';
	fix_header_crcs(img);
	CHECK(parse(img, PKG_LEN) == E2631_PKG_WRONG_PRODUCT, "product");
	make_package(img);

	/* Linux compares the 17th product byte; U-Boot must not be looser. */
	img[PKG_HDR_OFF + E2631_H_PRODUCT + 16] = 'X';
	fix_header_crcs(img);
	CHECK(parse(img, PKG_LEN) == E2631_PKG_WRONG_PRODUCT,
	      "product 17th byte");
	make_package(img);

	e2631_slotcore_wr32(img + PKG_HDR_OFF, E2631_H_BOOT_INCLUDED, 1);
	fix_header_crcs(img);
	CHECK(parse(img, PKG_LEN) == E2631_PKG_BOOTLOADER, "bootloader flag");
	make_package(img);

	e2631_slotcore_wr32(img + PKG_HDR_OFF, E2631_H_FW_SIZE, PKG_BODY_LEN + 1);
	fix_header_crcs(img);
	CHECK(parse(img, PKG_LEN) == E2631_PKG_BODY_SIZE, "body size");
	make_package(img);

	e2631_slotcore_wr32(img + PKG_HDR_OFF, E2631_H_SLOT0, 0x700001);
	fix_header_crcs(img);
	CHECK(parse(img, PKG_LEN) == E2631_PKG_SLOT_ADDRESSES, "slot addrs");
	make_package(img);

	e2631_slotcore_wr32(img + PKG_HDR_OFF, E2631_H_KERNEL_FILEOFS, 0x100000);
	fix_header_crcs(img);
	CHECK(parse(img, PKG_LEN) == E2631_PKG_REGION_OUTSIDE, "region outside");
	make_package(img);

	img[PKG_KOFF + 1] ^= 0xff;
	CHECK(parse(img, PKG_LEN) == E2631_PKG_KERNEL_CRC, "kernel crc");
	img[PKG_KOFF + 1] ^= 0xff;
	img[PKG_FOFF + 1] ^= 0xff;
	CHECK(parse(img, PKG_LEN) == E2631_PKG_ROOTFS_CRC, "rootfs crc");
	img[PKG_FOFF + 1] ^= 0xff;

	err = e2631_slotcore_pkg_parse(img, PKG_LEN, &pkg);
	CHECK(err == E2631_PKG_OK, "package parses again");
	err = e2631_slotcore_regions(pkg.hdr, &regions);
	CHECK(err == E2631_PKG_OK, "regions parse");
	CHECK(regions.kernel_start == E2631_KERNEL_MAGIC_SIZE, "kernel start");
	CHECK(regions.kernel_len == PKG_KSZ && regions.rootfs_len == PKG_FSZ,
	      "region lengths");
	CHECK(regions.rootfs_start ==
	      E2631_KERNEL_MAGIC_SIZE + (PKG_FOFF - PKG_KOFF), "rootfs start");
	CHECK(regions.kernel_crc ==
	      e2631_slotcore_crc32(0, img + PKG_KOFF, PKG_KSZ), "kernel crc2");
	CHECK(regions.rootfs_crc ==
	      e2631_slotcore_crc32(0, img + PKG_FOFF, PKG_FSZ), "rootfs crc2");

	return 0;
}

static void test_identity(void)
{
	u8 hdr[E2631_VER_HDR_SIZE];
	u8 img[PKG_LEN];

	make_package(img);
	memcpy(hdr, img + PKG_HDR_OFF, sizeof(hdr));
	CHECK(e2631_slotcore_identity(hdr) == E2631_SLOT_ID_OURS, "ours");
	memcpy(hdr + E2631_H_VERSION, "OpenWrt v1.9.0", 14);
	e2631_slotcore_wr32(hdr, E2631_H_CRC,
			    e2631_slotcore_crc32(0, hdr, E2631_H_CRC));
	CHECK(e2631_slotcore_identity(hdr) == E2631_SLOT_ID_OURS,
	      "ours openwrt brand");
	memcpy(hdr + E2631_H_VERSION, "V1.0.0.20250325", 15);
	e2631_slotcore_wr32(hdr, E2631_H_CRC,
			    e2631_slotcore_crc32(0, hdr, E2631_H_CRC));
	CHECK(e2631_slotcore_identity(hdr) == E2631_SLOT_ID_VENDOR, "vendor");
	memcpy(hdr + E2631_H_VERSION, "SomeLinux 1.0", 13);
	e2631_slotcore_wr32(hdr, E2631_H_CRC,
			    e2631_slotcore_crc32(0, hdr, E2631_H_CRC));
	CHECK(e2631_slotcore_identity(hdr) == E2631_SLOT_ID_UNKNOWN, "unknown");
	hdr[E2631_H_INNER_MAGIC] ^= 0xff;
	CHECK(e2631_slotcore_identity(hdr) == E2631_SLOT_ID_EMPTY, "empty");
	CHECK(!strcmp(e2631_slotcore_identity_name(E2631_SLOT_ID_VENDOR),
		      "vendor"), "identity names");
}

static void test_guards(void)
{
	CHECK(e2631_slotcore_target_guard(E2631_SLOT_ID_VENDOR, true, true) ==
	      E2631_GUARD_REFUSE, "target vendor intact refused");
	CHECK(e2631_slotcore_target_guard(E2631_SLOT_ID_VENDOR, true, false) ==
	      E2631_GUARD_OK, "target damaged vendor writable");
	CHECK(e2631_slotcore_target_guard(E2631_SLOT_ID_EMPTY, true, false) ==
	      E2631_GUARD_OK, "target empty");
	CHECK(e2631_slotcore_target_guard(E2631_SLOT_ID_OURS, true, true) ==
	      E2631_GUARD_OK, "target ours");
	CHECK(e2631_slotcore_target_guard(E2631_SLOT_ID_UNKNOWN, true, false) ==
	      E2631_GUARD_OK, "target unknown writable");
	CHECK(e2631_slotcore_target_guard(E2631_SLOT_ID_EMPTY, false, false) ==
	      E2631_GUARD_REFUSE, "target unreachable");
	CHECK(e2631_slotcore_fallback_guard(E2631_SLOT_ID_VENDOR, true, true) ==
	      E2631_GUARD_OK, "fallback vendor intact");
	CHECK(e2631_slotcore_fallback_guard(E2631_SLOT_ID_OURS, true, true) ==
	      E2631_GUARD_WEAK, "fallback ours weak");
	CHECK(e2631_slotcore_fallback_guard(E2631_SLOT_ID_UNKNOWN, true, true) ==
	      E2631_GUARD_WEAK, "fallback unknown weak");
	CHECK(e2631_slotcore_fallback_guard(E2631_SLOT_ID_VENDOR, true, false) ==
	      E2631_GUARD_REFUSE, "fallback damaged refused");
	CHECK(e2631_slotcore_fallback_guard(E2631_SLOT_ID_EMPTY, false, false) ==
	      E2631_GUARD_REFUSE, "fallback unreachable");
	CHECK(!strcmp(e2631_slotcore_guard_name(E2631_GUARD_WEAK), "weak"),
	      "guard names");
}

static void test_stamp(void)
{
	u8 img[PKG_LEN];
	u8 hdr[E2631_VER_HDR_SIZE];
	u32 serial;

	make_package(img);
	memcpy(hdr, img + PKG_HDR_OFF, sizeof(hdr));
	e2631_slotcore_stamp(hdr, 1, 7, 0, &serial);
	CHECK(serial == 8, "stamp max+1");
	CHECK(e2631_slotcore_rd32(hdr, E2631_H_SLOT_START) == E2631_SLOT1_BASE,
	      "stamp slot1 start");
	CHECK(e2631_slotcore_rd32(hdr, E2631_H_SERIAL) == 8, "stamp serial");
	CHECK(e2631_slotcore_rd32(hdr, E2631_H_NEW) == 1, "stamp new flag");
	CHECK(e2631_slotcore_rd32(hdr, E2631_H_CRC2) ==
	      e2631_slotcore_crc32(0, hdr, E2631_H_CRC2), "stamp crc2");

	memcpy(hdr, img + PKG_HDR_OFF, sizeof(hdr));
	e2631_slotcore_stamp(hdr, 0, 7, 999, &serial);
	CHECK(serial == 999, "stamp honours package serial");
	CHECK(e2631_slotcore_rd32(hdr, E2631_H_SLOT_START) == E2631_SLOT0_BASE,
	      "stamp slot0 start");

	memcpy(hdr, img + PKG_HDR_OFF, sizeof(hdr));
	e2631_slotcore_stamp(hdr, 1, 12, 5, &serial);
	CHECK(serial == 13, "stamp ignores lower package serial");
}

int main(void)
{
	test_parse();
	test_identity();
	test_guards();
	test_stamp();

	if (failures) {
		printf("slot core fixture: FAIL (%d/%d checks)\n", failures, checks);
		return 1;
	}
	printf("slot core fixture: PASS (%d checks, package/identity/guard/stamp vectors)\n",
	       checks);
	return 0;
}
