/* SPDX-License-Identifier: GPL-2.0+ */
/*
 * ZTE ZXHN E2631 firmware slot core, shared verbatim by the U-Boot rescue
 * (e2631fwslot) and the host-side golden-vector fixture.
 *
 * This file is the single source of the slot/package semantics that the
 * rescue UI uses: package layout and validation order, version-header
 * identity, the target/fallback guard rules and the serial stamping.  It
 * mirrors package/e2631/e2631-fwslot/src/e2631-fwslot.c in the tree fork;
 * the kit keeps a byte-identical copy under tests/native/uboot/ and the
 * U-Boot build asserts the two match with cmp(1).
 *
 * Only portable C and linux/types.h/linux/string.h are used, so the same
 * bytes compile inside U-Boot and on the CI host.
 *
 * Copyright (C) 2026 QC3284
 */

#ifndef __E2631_SLOTCORE_H__
#define __E2631_SLOTCORE_H__

#include <linux/types.h>

/* Flash truth (kernel DTS, MTD table and the kit image Makefile). */
#define E2631_SLOT0_BASE		0x00700000U
#define E2631_SLOT1_BASE		0x02300000U
#define E2631_SLOT_SPAN		0x01C00000U
#define E2631_SLOT_HDR_OFS	0x1500000U
#define E2631_ROOTFS_DATA_OFF	0x03360000U
#define E2631_ROOTFS_DATA_LEN	0x004A0000U
#define E2631_BOOTLOADER_OFF	0x00020000U
#define E2631_BOOTLOADER_LEN	0x000A0000U

/* Upgrade package layout (see e2631-fwslot.c). */
#define E2631_OUTER_HDR_SIZE	0x14U
#define E2631_VER_HDR_SIZE	0x200U
#define E2631_KERNEL_MAGIC_SIZE	0x20U
#define E2631_UBOOT_SIZE	0x0U
#define E2631_PKG_BODY_MAX	(E2631_SLOT_SPAN - 0x20000U)
#define E2631_PKG_MAX		(E2631_PKG_BODY_MAX + E2631_OUTER_HDR_SIZE + E2631_VER_HDR_SIZE)

/* Version-header field offsets. */
#define E2631_H_VERSION		0x10U
#define E2631_H_FW_SIZE		0x30U
#define E2631_H_KERNEL_SIZE	0x34U
#define E2631_H_KERNEL_FILEOFS	0x38U
#define E2631_H_KERNEL_CRC	0x3cU
#define E2631_H_FS_SIZE		0x40U
#define E2631_H_FS_FILEOFS	0x44U
#define E2631_H_FS_CRC		0x48U
#define E2631_H_SLOT0		0x4cU
#define E2631_H_SLOT1		0x5cU
#define E2631_H_PRODUCT		0x6cU
#define E2631_H_BOOT_INCLUDED	0x8cU
#define E2631_H_CRC		0xa4U
#define E2631_H_INNER_MAGIC	0xf4U
#define E2631_H_SLOT_START	0x1f0U
#define E2631_H_SERIAL		0x1f4U
#define E2631_H_NEW		0x1f8U
#define E2631_H_CRC2		0x1fcU

#define E2631_PRODUCT_STRING	"ZXHN E2631 V1.0.0"
#define E2631_PRODUCT_LEN	16U

enum e2631_slot_identity {
	E2631_SLOT_ID_EMPTY = 0,
	E2631_SLOT_ID_VENDOR,
	E2631_SLOT_ID_OURS,
	E2631_SLOT_ID_UNKNOWN,
};

enum e2631_slot_guard {
	E2631_GUARD_OK = 0,
	E2631_GUARD_WEAK,
	E2631_GUARD_REFUSE,
};

enum e2631_pkg_error {
	E2631_PKG_OK = 0,
	E2631_PKG_TOO_SMALL,
	E2631_PKG_BAD_OUTER_MAGIC,
	E2631_PKG_TRUNCATED_HEADER,
	E2631_PKG_BAD_INNER_MAGIC,
	E2631_PKG_HEADER_CRC,
	E2631_PKG_WRONG_PRODUCT,
	E2631_PKG_BOOTLOADER,
	E2631_PKG_BODY_SIZE,
	E2631_PKG_SLOT_ADDRESSES,
	E2631_PKG_REGION_OUTSIDE,
	E2631_PKG_KERNEL_CRC,
	E2631_PKG_ROOTFS_CRC,
	E2631_PKG_TOO_LARGE,
};

struct e2631_pkg {
	const u8 *data;
	u32 size;
	const u8 *hdr;
	const u8 *body;
	u32 hdr_off;
	u32 body_off;
	u32 body_len;
};

/* Expected kernel/rootfs extents inside the slot, from the version header. */
struct e2631_slot_regions {
	u32 body_len;
	u32 kernel_start;
	u32 kernel_len;
	u32 kernel_crc;
	u32 rootfs_start;
	u32 rootfs_len;
	u32 rootfs_crc;
};

u32 e2631_slotcore_rd32(const u8 *p, u32 ofs);
void e2631_slotcore_wr32(u8 *p, u32 ofs, u32 v);
u32 e2631_slotcore_crc32(u32 crc, const void *buf, u32 len);

enum e2631_pkg_error e2631_slotcore_pkg_parse(const u8 *img, u32 len,
					      struct e2631_pkg *pkg);
bool e2631_slotcore_header_ok(const u8 *hdr);
enum e2631_slot_identity e2631_slotcore_identity(const u8 *hdr);
enum e2631_pkg_error e2631_slotcore_regions(const u8 *hdr,
					    struct e2631_slot_regions *regions);
enum e2631_slot_guard e2631_slotcore_target_guard(enum e2631_slot_identity id,
						  bool known, bool intact);
enum e2631_slot_guard e2631_slotcore_fallback_guard(enum e2631_slot_identity id,
						    bool known, bool intact);
void e2631_slotcore_stamp(u8 *hdr, int slot, u32 max_serial, u32 pkg_serial,
			  u32 *written_serial);
const char *e2631_slotcore_identity_name(enum e2631_slot_identity id);
const char *e2631_slotcore_guard_name(enum e2631_slot_guard guard);
const char *e2631_slotcore_error_name(enum e2631_pkg_error err);

#endif /* __E2631_SLOTCORE_H__ */
