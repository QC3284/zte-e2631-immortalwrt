/* Combined ZTE/standard-offset UART A/B probe for the ZX279128S.
 *
 * One pass, one power cycle:
 *   1) read and save the current ZTE UART CR/LCRH,
 *   2) configure via ZTE offsets and print ZTE-PROBE lines (expect: visible),
 *   3) print STD-MARKER-BEGIN via ZTE offsets,
 *   4) re-configure via STOCK ARM PL011 offsets and try to print STD-PROBE-SHOULD-BE-INVISIBLE
 *      (expect: no bytes on the host),
 *   5) restore the saved ZTE CR/LCRH, print STD-MARKER-END + COMBINED-DONE,
 *   6) return to the vendor U-Boot with SP/LR restored by start.S.
 */
typedef unsigned int u32;

#define UART_BASE 0x94404000u

/* ZTE zx29 offsets (kernel vendor_zte) */
#define Z_DR   0x04u
#define Z_FR   0x14u
#define Z_CR   0x34u
#define Z_LCRH 0x30u

/* stock ARM PL011 offsets (mainline U-Boot serial_pl01x.c) */
#define S_DR   0x00u
#define S_FR   0x18u
#define S_CR   0x30u
#define S_LCRH 0x2Cu

#define REG(off) (*(volatile u32 *)(UART_BASE + (off)))

static void z_putc(char c)
{
    while (REG(Z_FR) & (1u << 5)) { }
    REG(Z_DR) = (u32)(unsigned char)c;
}
static void z_puts(const char *s) { while (*s) z_putc(*s++); }
static void z_hex(u32 v)
{
    int i;
    z_puts("0x");
    for (i = 28; i >= 0; i -= 4) {
        u32 d = (v >> i) & 0xFu;
        z_putc(d < 10u ? (char)('0' + d) : (char)('a' + d - 10u));
    }
}
static void s_putc(char c)
{
    volatile u32 guard = 200000u;
    while (guard-- && (REG(S_FR) & (1u << 5))) { }
    REG(S_DR) = (u32)(unsigned char)c;
}
static void s_puts(const char *s) { while (*s) s_putc(*s++); }

/* Give the transmitter time to shift out queued bytes before we touch LCRH.
 * Writes to a volatile scratch word (safe RAM at 0x4C100000) so the loop
 * cannot be optimised away like a volatile register loop would be. */
static void tx_delay(void)
{
    volatile u32 *scratch = (volatile u32 *)0x4C100000u;
    u32 i;
    for (i = 0; i < 2000000u; i++)
        *scratch = i;
}

void stub_main(void)
{
    volatile u32 saved_cr = REG(Z_CR);
    volatile u32 saved_lcrh = REG(Z_LCRH);

    /* (2) ZTE offsets: this is the kernel-documented layout */
    REG(Z_CR) = 0;
    REG(Z_LCRH) = 0x70u;
    REG(Z_CR) = 0x301u;
    z_puts("E2631 UART probe ZTE-ZX29 (combined-v4)\n");
    z_puts("SAVED_CR="); z_hex(saved_cr);
    z_puts(" SAVED_LCRH="); z_hex(saved_lcrh);
    z_puts("\nZTE_FR="); z_hex(REG(Z_FR));
    z_puts(" ZTE_CR="); z_hex(REG(Z_CR));
    z_puts(" ZTE_LCRH="); z_hex(REG(Z_LCRH));
    z_puts(" IBRD="); z_hex(REG(0x24u));
    z_puts(" FBRD="); z_hex(REG(0x28u));
    z_puts("\nZTE-PROBE-DONE\n");

    /* (3) marker via the working path */
    z_puts("STD-MARKER-BEGIN\n");
    tx_delay();

    /* (4) stock offsets: this is what mainline serial_pl01x.c does */
    REG(S_CR) = 0;
    REG(S_LCRH) = 0x70u;
    REG(S_CR) = 0x301u;
    s_puts("STD-PROBE-SHOULD-BE-INVISIBLE\n");

    /* (5) restore the vendor configuration through the ZTE offsets */
    REG(Z_CR) = 0;
    REG(Z_LCRH) = saved_lcrh;
    REG(Z_CR) = saved_cr;
    tx_delay();
    z_puts("STD-MARKER-END\n");
    z_puts("COMBINED-DONE\n");
    /* (6) start.S restores SP/LR and returns to the vendor U-Boot */
}
