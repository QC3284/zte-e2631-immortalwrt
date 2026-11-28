// SPDX-License-Identifier: GPL-2.0+
/*
 * ZTE ZXHN E2631 firmware slot core (see e2631_slotcore.h).
 *
 * The validation order, the version-header constants, the identity rules,
 * the guard matrix and the serial stamping are a byte-for-byte port of the
 * Linux side (package/e2631/e2631-fwslot/src/e2631-fwslot.c); the kit keeps
 * an identical copy under tests/native/uboot/ and the U-Boot build compares
 * them before compiling.
 *
 * Copyright (C) 2026 QC3284
 */

#include <linux/string.h>
#include <linux/types.h>

#include "e2631_slotcore.h"

static const u8 e2631_outer_magic[16] = {
	0x99, 0x99, 0x99, 0x99, 0x44, 0x44, 0x44, 0x44,
	0x55, 0x55, 0x55, 0x55, 0xaa, 0xaa, 0xaa, 0xaa,
};

static const u8 e2631_inner_magic[16] = {
	0x33, 0x33, 0x33, 0x33, 0x66, 0x66, 0x66, 0x66,
	0x99, 0x99, 0x99, 0x99, 0xcc, 0xcc, 0xcc, 0xcc,
};

/* Reflected CRC-32 (IEEE) through a 16-entry nibble table: portable, no
 * libc and small enough to keep the shared source free of U-Boot APIs.
 */
static const u32 e2631_crc_nibble[16] = {
	0x00000000U, 0x1db71064U, 0x3b6e20c8U, 0x26d930acU,
	0x76dc4190U, 0x6b6b51f4U, 0x4db26158U, 0x5005713cU,
	0xedb88320U, 0xf00f9344U, 0xd6d6a3e8U, 0xcb61b38cU,
	0x9b64c2b0U, 0x86d3d2d4U, 0xa00ae278U, 0xbdbdf21cU,
};

u32 e2631_slotcore_crc32(u32 crc, const void *buf, u32 len)
{
	const u8 *p = buf;
	u32 i;

	crc ^= 0xffffffffU;
	for (i = 0; i < len; i++) {
		crc = (crc >> 4) ^ e2631_crc_nibble[(crc ^ p[i]) & 0x0f];
		crc = (crc >> 4) ^
		      e2631_crc_nibble[(crc ^ (p[i] >> 4)) & 0x0f];
	}
	return crc ^ 0xffffffffU;
}

u32 e2631_slotcore_rd32(const u8 *p, u32 ofs)
{
	return (u32)p[ofs] | ((u32)p[ofs + 1] << 8) |
	       ((u32)p[ofs + 2] << 16) | ((u32)p[ofs + 3] << 24);
}

void e2631_slotcore_wr32(u8 *p, u32 ofs, u32 v)
{
	p[ofs] = v & 0xff;
	p[ofs + 1] = (v >> 8) & 0xff;
	p[ofs + 2] = (v >> 16) & 0xff;
	p[ofs + 3] = (v >> 24) & 0xff;
}

bool e2631_slotcore_header_ok(const u8 *hdr)
{
	if (memcmp(hdr + E2631_H_INNER_MAGIC, e2631_inner_magic, 16))
		return false;
	return e2631_slotcore_crc32(0, hdr, E2631_H_CRC) ==
	       e2631_slotcore_rd32(hdr, E2631_H_CRC);
}

enum e2631_slot_identity e2631_slotcore_identity(const u8 *hdr)
{
	if (!e2631_slotcore_header_ok(hdr))
		return E2631_SLOT_ID_EMPTY;
	if (!strncmp((const char *)hdr + E2631_H_VERSION, "OpenWrt", 7) ||
	    !strncmp((const char *)hdr + E2631_H_VERSION, "ImmortalWrt", 11))
		return E2631_SLOT_ID_OURS;
	if (!strncmp((const char *)hdr + E2631_H_VERSION, "V1.0.0.", 7))
		return E2631_SLOT_ID_VENDOR;
	return E2631_SLOT_ID_UNKNOWN;
}

enum e2631_pkg_error e2631_slotcore_pkg_parse(const u8 *img, u32 len,
					      struct e2631_pkg *pkg)
{
	u32 hdr_off, body_off, body_len, koff, ksz, foff, fsz;
	const u8 *hdr;

	memset(pkg, 0, sizeof(*pkg));
	pkg->data = img;
	pkg->size = len;

	if (len < E2631_OUTER_HDR_SIZE + E2631_VER_HDR_SIZE)
		return E2631_PKG_TOO_SMALL;
	if (len > E2631_PKG_MAX)
		return E2631_PKG_TOO_LARGE;
	if (memcmp(img, e2631_outer_magic, 16))
		return E2631_PKG_BAD_OUTER_MAGIC;

	hdr_off = E2631_OUTER_HDR_SIZE + e2631_slotcore_rd32(img, 0x10);
	if (hdr_off < E2631_OUTER_HDR_SIZE ||
	    hdr_off > len - E2631_VER_HDR_SIZE)
		return E2631_PKG_TRUNCATED_HEADER;
	body_off = hdr_off + E2631_VER_HDR_SIZE;
	if (body_off > len)
		return E2631_PKG_TRUNCATED_HEADER;

	hdr = img + hdr_off;
	body_len = len - body_off;

	if (memcmp(hdr + E2631_H_INNER_MAGIC, e2631_inner_magic, 16))
		return E2631_PKG_BAD_INNER_MAGIC;
	if (e2631_slotcore_crc32(0, hdr, E2631_H_CRC) !=
	    e2631_slotcore_rd32(hdr, E2631_H_CRC) ||
	    e2631_slotcore_crc32(0, hdr, E2631_H_CRC2) !=
	    e2631_slotcore_rd32(hdr, E2631_H_CRC2))
		return E2631_PKG_HEADER_CRC;
	if (memcmp(hdr + E2631_H_PRODUCT, E2631_PRODUCT_STRING,
		   E2631_PRODUCT_LEN))
		return E2631_PKG_WRONG_PRODUCT;
	if (e2631_slotcore_rd32(hdr, E2631_H_BOOT_INCLUDED))
		return E2631_PKG_BOOTLOADER;
	if (e2631_slotcore_rd32(hdr, E2631_H_FW_SIZE) != body_len)
		return E2631_PKG_BODY_SIZE;
	if (e2631_slotcore_rd32(hdr, E2631_H_SLOT0) != E2631_SLOT0_BASE ||
	    e2631_slotcore_rd32(hdr, E2631_H_SLOT1) != E2631_SLOT1_BASE)
		return E2631_PKG_SLOT_ADDRESSES;

	koff = e2631_slotcore_rd32(hdr, E2631_H_KERNEL_FILEOFS);
	ksz = e2631_slotcore_rd32(hdr, E2631_H_KERNEL_SIZE);
	foff = e2631_slotcore_rd32(hdr, E2631_H_FS_FILEOFS);
	fsz = e2631_slotcore_rd32(hdr, E2631_H_FS_SIZE);
	if ((u64)koff + ksz > len || (u64)foff + fsz > len)
		return E2631_PKG_REGION_OUTSIDE;
	if (e2631_slotcore_crc32(0, img + koff, ksz) !=
	    e2631_slotcore_rd32(hdr, E2631_H_KERNEL_CRC))
		return E2631_PKG_KERNEL_CRC;
	if (e2631_slotcore_crc32(0, img + foff, fsz) !=
	    e2631_slotcore_rd32(hdr, E2631_H_FS_CRC))
		return E2631_PKG_ROOTFS_CRC;

	pkg->hdr = hdr;
	pkg->body = img + body_off;
	pkg->hdr_off = hdr_off;
	pkg->body_off = body_off;
	pkg->body_len = body_len;
	return E2631_PKG_OK;
}

enum e2631_pkg_error e2631_slotcore_regions(const u8 *hdr,
					    struct e2631_slot_regions *regions)
{
	u32 body_len = e2631_slotcore_rd32(hdr, E2631_H_FW_SIZE);
	u32 koff = e2631_slotcore_rd32(hdr, E2631_H_KERNEL_FILEOFS);
	u32 foff = e2631_slotcore_rd32(hdr, E2631_H_FS_FILEOFS);
	u32 kstart = E2631_UBOOT_SIZE + E2631_KERNEL_MAGIC_SIZE;
	u32 rstart;

	memset(regions, 0, sizeof(*regions));
	if (!e2631_slotcore_header_ok(hdr))
		return E2631_PKG_HEADER_CRC;
	if (e2631_slotcore_crc32(0, hdr, E2631_H_CRC2) !=
	    e2631_slotcore_rd32(hdr, E2631_H_CRC2))
		return E2631_PKG_HEADER_CRC;
	if (e2631_slotcore_rd32(hdr, E2631_H_BOOT_INCLUDED))
		return E2631_PKG_BOOTLOADER;
	if (foff < koff)
		return E2631_PKG_REGION_OUTSIDE;
	if (body_len > E2631_PKG_BODY_MAX)
		return E2631_PKG_BODY_SIZE;

	rstart = kstart + (foff - koff);
	regions->body_len = body_len;
	regions->kernel_start = kstart;
	regions->kernel_len = e2631_slotcore_rd32(hdr, E2631_H_KERNEL_SIZE);
	regions->kernel_crc = e2631_slotcore_rd32(hdr, E2631_H_KERNEL_CRC);
	regions->rootfs_start = rstart;
	regions->rootfs_len = e2631_slotcore_rd32(hdr, E2631_H_FS_SIZE);
	regions->rootfs_crc = e2631_slotcore_rd32(hdr, E2631_H_FS_CRC);
	if (regions->kernel_start + regions->kernel_len > body_len ||
	    regions->rootfs_start + regions->rootfs_len > body_len)
		return E2631_PKG_REGION_OUTSIDE;
	return E2631_PKG_OK;
}

enum e2631_slot_guard e2631_slotcore_target_guard(enum e2631_slot_identity id,
						  bool known, bool intact)
{
	if (!known)
		return E2631_GUARD_REFUSE;
	if (id == E2631_SLOT_ID_VENDOR && intact)
		return E2631_GUARD_REFUSE;
	return E2631_GUARD_OK;
}

enum e2631_slot_guard e2631_slotcore_fallback_guard(enum e2631_slot_identity id,
						    bool known, bool intact)
{
	if (!known || !intact)
		return E2631_GUARD_REFUSE;
	if (id == E2631_SLOT_ID_VENDOR)
		return E2631_GUARD_OK;
	return E2631_GUARD_WEAK;
}

void e2631_slotcore_stamp(u8 *hdr, int slot, u32 max_serial, u32 pkg_serial,
			  u32 *written_serial)
{
	u32 serial = max_serial + 1;

	if (pkg_serial > serial)
		serial = pkg_serial;
	e2631_slotcore_wr32(hdr, E2631_H_SLOT_START,
			    slot == 0 ? E2631_SLOT0_BASE : E2631_SLOT1_BASE);
	e2631_slotcore_wr32(hdr, E2631_H_SERIAL, serial);
	e2631_slotcore_wr32(hdr, E2631_H_NEW, 1);
	e2631_slotcore_wr32(hdr, E2631_H_CRC2,
			    e2631_slotcore_crc32(0, hdr, E2631_H_CRC2));
	if (written_serial)
		*written_serial = serial;
}

const char *e2631_slotcore_identity_name(enum e2631_slot_identity id)
{
	switch (id) {
	case E2631_SLOT_ID_EMPTY:
		return "empty";
	case E2631_SLOT_ID_VENDOR:
		return "vendor";
	case E2631_SLOT_ID_OURS:
		return "ours";
	default:
		return "unknown";
	}
}

const char *e2631_slotcore_guard_name(enum e2631_slot_guard guard)
{
	switch (guard) {
	case E2631_GUARD_OK:
		return "ok";
	case E2631_GUARD_WEAK:
		return "weak";
	default:
		return "refuse";
	}
}

const char *e2631_slotcore_error_name(enum e2631_pkg_error err)
{
	switch (err) {
	case E2631_PKG_OK:
		return "ok";
	case E2631_PKG_TOO_SMALL:
		return "package too small";
	case E2631_PKG_BAD_OUTER_MAGIC:
		return "bad outer magic";
	case E2631_PKG_TRUNCATED_HEADER:
		return "truncated header";
	case E2631_PKG_BAD_INNER_MAGIC:
		return "bad version header magic";
	case E2631_PKG_HEADER_CRC:
		return "header CRC mismatch";
	case E2631_PKG_WRONG_PRODUCT:
		return "package is not for this product";
	case E2631_PKG_BOOTLOADER:
		return "package wants to update the bootloader";
	case E2631_PKG_BODY_SIZE:
		return "body size mismatch";
	case E2631_PKG_SLOT_ADDRESSES:
		return "package declares different slot addresses";
	case E2631_PKG_REGION_OUTSIDE:
		return "region outside package";
	case E2631_PKG_KERNEL_CRC:
		return "kernel CRC mismatch";
	case E2631_PKG_ROOTFS_CRC:
		return "rootfs CRC mismatch";
	case E2631_PKG_TOO_LARGE:
		return "package larger than the slot";
	default:
		return "invalid package";
	}
}
