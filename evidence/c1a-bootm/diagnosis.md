# C1a bootm dry-run - diagnosis (2026-11-21 17:17-17:24 CST)

## Session flow
- User cold power cycle at ~17:16:47 (vendor Press-1 prompt caught; vendor password accepted; stock U-Boot 2013.04 console).
- xmodem: A3 u-boot.bin 448,072 B, 438 blocks CRC mode, 41.9 s, EOT ACK; md.b spot checks start/tail/banner all byte-exact (0 gaps).
- go 0x43000000 at 17:17:30; banner 'U-Boot 2027.01-rc2-g8a9d1f7eecfa' seen 17:17:31; autoboot not interrupted (driver sent nothing).
- e2631boot: slot0 serial 7 V1.0.0.7B5.8000 (header 0x01c60000); slot1 serial 12 ImmortalWrt v1.10.0 (header 0x03800000); decision slot1.
- e2631boot load: uImage 'ARM ImmortalWrt Linux-6.18.60', load/entry 0x40008000, 3,491,146 bytes at 0x42000000, header+data CRC good.
- bootm: Legacy Image verified OK; 'Working FDT set to 0'; 'Loading Kernel Image to 40008000'; then DATA ABORT.

## Data abort
pc 0x4ff9578c (reloc 0x4300178c) = boot_prep_linux + 0x74 (arch/arm/lib/bootm.c, inlined ATAGS setup).
Faulting instruction e5810004 = str r0, [r1, #4]; r0=0x54410002 (ATAG_MEM), r1=0x967fc480 (outside DRAM 0x40000000..0x4fffffff).
Caller frame lr 0x43042edc = hsearch_r+0xf4 (stale frame from env_get path). U-Boot then prints 'Resetting CPU ... resetting ...' and 'reset: the A1 port has no reset controller, power-cycle the board'; device stays at our U-Boot prompt.

## Root cause analysis
- CONFIG_SETUP_MEMORY_TAGS=y, CONFIG_CMDLINE_TAG/SERIAL_TAG/REVISION_TAG/INITRD_TAG all not set -> only ATAG_CORE + ATAG_MEM tags are emitted.
- setup_start_tag() uses bd->bi_boot_params (arch/arm/lib/bootm.c:47). Grep of the whole u-boot tree at post-am 40f52fb4 finds no assignment for our board; board/zte/zxhn-e2631/zxhn-e2631.c only has dram_init/dram_init_banksize/reset_cpu.
- Therefore the ATAGS buffer pointer is never placed in DRAM by board code (bd_info is zeroed in reserve_board); the ATAG_MEM write goes through an invalid pointer -> data abort. A3 had never executed bootm before (A3 acceptance only did info/load), so this was latent.
- Fix belongs to the U-Boot port: initialise gd->bd->bi_boot_params in board init (classic CFG_SYS_SDRAM_BASE + 0x100), keep it clear of the kernel load/entry addresses, then rebuild and re-run C1a before any flash write.

## Secondary findings
1) 'Loading Environment from <NULL>... OK': the ENV_IS_IN_MTD read-only vendor-env path (patch 0007) is not active (no mtd env driver bound). bootcmd still ran e2631boot from the compiled default environment, and e2631boot sets bootargs in RAM, so bootm was reached; but the planned read-only env feature is not live.
2) 'WARNING: Caches not enabled' and 'Net: No ethernet found.' - informational for A1/A3 (no cache/eth support yet).
3) Driver bug: monitor matched 'ImmortalWrt' (inside slot version / uImage name) as a Linux marker and stopped the serial monitor early; the bootm continuation was recorded by the restored capture chain instead. Fix: require kernel/userspace markers (e2631-wifi-boot / Please press Enter / login) and watch the bootm result.

## Safety
No flash write command was ever sent (transcripts contain none of: nand write/erase, mtd write/erase, saveenv, Erasing/Writing to Nand). Kernel never started, so no userspace/network; device currently powered, waiting for one power cycle to return to the vendor chain.

## Evidence files in this directory
- hub-serial-full.txt / a3-boot-segment.txt: our U-Boot banner + e2631boot slot decision (from serialhub log).
- a3-boot-continuation-002.txt: bootm load + data abort + reset (from the restored capture chain).
- session-results.json, driver.console.log, preflight.json.