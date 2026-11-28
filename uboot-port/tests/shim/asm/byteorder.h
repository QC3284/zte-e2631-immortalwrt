/* Host shim for the rescue DHCP pool fixture (CI only). */
#ifndef __HOST_SHIM_ASM_BYTEORDER_H__
#define __HOST_SHIM_ASM_BYTEORDER_H__

#include <stdint.h>

#define ntohl(x) __builtin_bswap32((uint32_t)(x))
#define htonl(x) __builtin_bswap32((uint32_t)(x))

#endif