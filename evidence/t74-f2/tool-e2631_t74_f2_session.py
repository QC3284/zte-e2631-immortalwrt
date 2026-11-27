#!/usr/bin/env python3
"""T74 read-visibility discriminator + optional F2 re-run, one session.

Prepared offline 2026-11-27; updated per Lead m08459.  Do not run until the Lead
gives GO with the combined build archive (env fix).  Two load paths are
available: the default userdata staging (Linux mtd erase/write of the userdata
partition, the only permitted flash write) and --loadx (serial xmodem from the
flash U-Boot prompt, zero flash writes).

Session order (nothing depends on a power cycle in the middle):
  0  preflight (read-only): artifact pins, route, device mtd0 + image-region
     baseline, capture chain, host services (services only with --with-f2)
  1  load path: userdata staging (default) or --loadx serial transfer
  2  flash U-Boot: mtd read + crc32 gate, or loadx + md.b verify, then go
  3  env-block diagnostics at the new prompt: read 0xC0000 (0x20000) through
     mtd read into RAM, record the stored CRC word and the region crc32 against
     the B1 baseline (block sha 6e2c01da, region crc 0xe826c394, stored 0xf95a816e)
  4  env sanity: boot-time "Loading Environment from MTD... OK", no bad CRC /
     default environment, printenv 26 entries and exact baseline values,
     ethaddr=00:41:71:00:00:50 (NOT the 26:a1:2f random MAC).  If the env is
     still bad, the session automatically reloads the same image over serial
     (loadx, zero flash writes), goes again and re-checks the env; a second
     bad env is recorded as a deterministic regression and F2 is skipped.
  5  F2 (only with --with-f2): mii info / e2631net / dhcp / short netretry=1
     retry / (static fallback) ping / tftp / crc32, BMU snapshots and the NIC
     register set (MAC ctrl, MAC TX frames, TM int status/mask, DMA ctrl/ring/
     tx_start/tx_done, RX queue counts, switch FWD ctrl, SPA port enable)
     around every step, host dnsmasq + tcpdump, wire yes/no analysis
  6  T74 discriminators: control pair (known-good 0x4C000000, 0x4A000000) and
     the live suspect 0x42000000 (the 0x48000000 phantom was a command typo:
     "md 0x480000" reads 0x00480000); mw/md at both; mtd read into the suspect
     followed by immediate md/crc32/iminfo; bdinfo relocaddr recorded before and
     after, tests repeated after bdinfo to test relocation dependence
  7  F1 sanity LAST: e2631boot -> expect KERNEL_STARTED; then SSH postcheck
     (mtd0/region unchanged, PANICS=0, fwslot) plus the kernel NIC dmesg view
     (zx279128s-eth / PHY, first 30 lines) for U-Boot vs Linux comparison

Every U-Boot command passes a fixed allowlist before it is sent, and the audit
re-checks the transcript for mtd write/erase, saveenv, nand write/erase,
e2631flash, bootm and reset.  loadx is forbidden by default and is excluded
from that audit only in the explicit --loadx mode.

Output: <out-dir>/session-results.json with per-check booleans and a small
verdict object {session, env_sanity, f2, t74, f1}. Exit code 0 only for GREEN.

Usage:
  python3 e2631_t74_f2_session.py --preflight --artifact <u-boot.bin|archive dir>
  python3 e2631_t74_f2_session.py --session --artifact ... --out-dir ... [--with-f2] [--loadx]
  python3 e2631_t74_f2_session.py --selftest
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import zlib

P3 = "/home/qc233/zte/e2631-p3"
E2 = P3 + "/e2"
sys.path.insert(0, P3)
sys.path.insert(0, E2)
sys.path.insert(0, E2 + "/drivers")
import a1_banner_accept as base
import b1_env_session as b1
import c1b1_final as fin
import e2_session as e2s
import e2t_session as e2t

# ---------------------------------------------------------------- persistent facts
MTD0_SHA = "f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4"
REGION_SHA = "b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a"
FLASH_BANNER = "U-Boot 2027.01-rc2-g85df6772a444"   # current flashed 15-patch U-Boot
FLASH_MAC = "00:41:71:00:00:50"                     # env ethaddr
RANDOM_MAC_PREFIX = "26:a1:2f"
STAGE_OFF = 0x3F00000
STAGE_LEN = 0x80000
LOAD_ADDR = 0x47F00000
TFTP_ADDR = 0x43000000
HOST_IP = "192.168.1.191"
IFACE = "enp0s20u1u4u2c2"

# T74 address plan (Lead m08459): the 0x48000000 phantom was a command typo
# ("md 0x480000" reads 0x00480000); the live suspect is 0x42000000 only.
SUSPECTS = [0x42000000]
CONTROLS = [0x4C000000, 0x4A000000]
PATTERN_WORD = 0x11223344
PATTERN_WORDS = 0x10                      # 16 words = 64 bytes, count is HEX
PATTERN_BYTES = PATTERN_WORD.to_bytes(4, "little") * PATTERN_WORDS
PATTERN_CRC = zlib.crc32(PATTERN_BYTES) & 0xFFFFFFFF
# slot1 base (chip 0x02300000) starts with a 32-byte slot marker then the uImage.
SLOT1_CHIP_OFF = 0x2300000
SLOT_MARKER_HEX = "33333333cccccccc88888888dddddddd"
SLOT_MARKER = bytes.fromhex(SLOT_MARKER_HEX) + b"\xff" * 16
SLOT_MARKER_CRC = zlib.crc32(SLOT_MARKER) & 0xFFFFFFFF
SLOT_MARKER_WORDS = [0x33333333, 0xCCCCCCCC, 0x88888888, 0xDDDDDDDD]
SLOT_HEADER_MAGIC = 0x56190527  # uImage magic 0x27051956; md prints the LE word

# env block at 0xC0000: B1 26-entry baseline, read-only diagnostics at the new prompt
ENV_BLOCK_OFF = 0xC0000
ENV_BLOCK_LEN = 0x20000
ENV_READ_ADDR = 0x44000000
ENV_BLOCK_FILE = P3 + "/b1-env-session/resume-1/target-env-block.bin"
ENV_BLOCK_SHA = "6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893"
ENV_STORED_CRC = 0xF95A816E
ENV_REGION_CRC = 0xE826C394

# NIC register snapshots for the F2 diagnosis (GMAC base 0x92000000; LAN1 is
# switch port 2 so its MAC block is at 0x92280000, TM/BMU/DMA sit above it).
NIC_REGS = [
    ("lan1_mac_ctrl", 0x92280000, 1),
    ("lan1_mac_tx_octets", 0x92280764, 1),
    ("lan1_mac_tx_frames", 0x92280768, 1),
    ("lan1_mac_rx_ucast", 0x922807C4, 1),
    ("tm_ctrl", 0x92340000, 1),
    ("tm_int_status", 0x92340100, 1),
    ("tm_int_mask", 0x92340104, 1),
    ("bmu_buf_alloc", 0x92348014, 1),
    ("bmu_buf_id", 0x9234800C, 1),
    ("bmu_free_status", 0x923480DC, 1),
    ("dma_ctrl", 0x92350000, 1),
    ("dma_ring_cfg", 0x9235003C, 1),
    ("dma_tx_ring", 0x92350060, 1),
    ("dma_tx_start", 0x92350064, 1),
    ("dma_tx_done", 0x92350068, 1),
    ("dma_rx_queue_counts", 0x92350100, 8),
    ("sw_fwd_ctrl", 0x921CC000, 1),
    ("spa_port_en", 0x921D428C, 5),
]

def expected_env_block():
    """Facts of the B1 baseline env block that sits in flash at 0xC0000."""
    exp = {"path": ENV_BLOCK_FILE, "sha256": None, "crc": None, "stored": None}
    if not os.path.exists(ENV_BLOCK_FILE):
        return exp
    d = open(ENV_BLOCK_FILE, "rb").read()
    exp["sha256"] = hashlib.sha256(d).hexdigest()
    exp["crc"] = zlib.crc32(d) & 0xFFFFFFFF
    exp["stored"] = int.from_bytes(d[:4], "little") if len(d) >= 4 else None
    return exp

# The B1 env block currently in flash: 26 entries, byte-exact baseline.
EXPECTED_ENV = {
    "baudrate": "115200",
    "bootcmd": "setenv bootargs console=$(console) root=/dev/mtdblock8 ro rootfstype=squashfs  mem=$(memsize) ;",
    "bootdelay": "3",
    "bootfile": "uboot.bin",
    "bootloaderfile": "bootloader.bin",
    "console": "ttyAMA0,115200n8",
    "ethact": "eth0",
    "ethaddr": "00:41:71:00:00:50",
    "fullfile": "upgrade.bin",
    "gatewayip": "192.168.1.1",
    "hostname": "unknown",
    "ipaddr": "192.168.1.1",
    "linuzfile": "vmlinuz.bin",
    "loadaddr": "0x42000000",
    "memsize": "256M",
    "netmask": "255.255.255.0",
    "netretry": "5",
    "serverip": "192.168.1.100",
    "stderr": "serial",
    "stdin": "serial",
    "stdout": "serial",
    "versioninfo": "U-Boot V1.0.0 20230828191152 0x2300000 0x1 0xaf 0x00",
    "e2631_flashboot": "reset",
    "e2631_netboot": "tftp 0x42000000 e2631-netboot.uImage",
    "e2631_pocgo": "go 0x43000000",
    "e2631_pocload": "tftp 0x43000000 u-boot.bin",
}
# At the U-Boot prompt the flash environment is augmented by U-Boot itself:
# board_late_init() overrides bootcmd in RAM (patch 0006/0017, the flash copy is
# verified byte-exact separately by env_block_diag), the DM serial driver names
# the stdio devices, and fdtcontroladdr is a runtime variable.  env_sanity()
# therefore checks the EFFECTIVE prompt view, not the raw flash view.
EXPECTED_ENV_EFFECTIVE = dict(EXPECTED_ENV)
EXPECTED_ENV_EFFECTIVE.update({
    "bootcmd": "e2631boot",
    "stdin": "serial@94404000",
    "stdout": "serial@94404000",
    "stderr": "serial@94404000",
})
EXPECTED_RUNTIME_EXTRAS = {"fdtcontroladdr"}
EXPECTED_ENV_COUNT = len(EXPECTED_ENV)

OUT_DEFAULT = E2 + "/t74/run-1"

# ---------------------------------------------------------------- command allowlist
_HEX = r"0x[0-9a-fA-F]+"
ALLOW_EXACT = [
    "version", "bdinfo", "printenv", "mii info", "e2631net", "dhcp",
    "e2631boot", "e2631boot load", "help", "help e2631rescue",
    "ping " + HOST_IP,
    "tftp 0x%08x %s" % (TFTP_ADDR, e2s.TEST_NAME),
]
ALLOW_RES = [
    re.compile(r"^md(?:\.l|\.b)? " + _HEX + r"(?: (?:0x[0-9a-fA-F]+|\d+))?$"),
    re.compile(r"^mw " + _HEX + r" " + _HEX + r" " + _HEX + r"$"),
    re.compile(r"^mtd read spi-nand0 " + _HEX + r" " + _HEX + r" " + _HEX + r"$"),
    re.compile(r"^crc32 " + _HEX + r" " + _HEX + r"$"),
    re.compile(r"^iminfo " + _HEX + r"$"),
    re.compile(r"^go " + _HEX + r"$"),
    re.compile(r"^setenv (?:ipaddr|netmask|serverip|netretry) [0-9.]+$"),
]
FORBIDDEN_RE = re.compile(
    r"(mtd\s+(?:write|erase)|saveenv|nand\s+(?:write|erase)|e2631flash|loadx|xmodem|bootm|reset\b|e2631env)")
MW_ADDRS = set([hex(a) for a in SUSPECTS + CONTROLS] + ["0x%08x" % a for a in SUSPECTS + CONTROLS])


def log(msg):
    base.log(msg)


def command_allowed(cmd):
    if cmd in ALLOW_EXACT:
        return True
    for rx in ALLOW_RES:
        if rx.match(cmd):
            if cmd.startswith("mw "):
                return cmd.split()[1].lower() in MW_ADDRS
            return True
    return False


def ub_cmd(c, res, cmd, timeout=120):
    if not command_allowed(cmd):
        raise RuntimeError("command rejected by allowlist: " + cmd)
    return e2s.ub_cmd(c, res, cmd, timeout)


# ---------------------------------------------------------------- parsers
def parse_md(txt):
    """Parse U-Boot md output into {address:int -> [word, ...]} and a flat list."""
    out = {}
    flat = []
    for line in (txt or "").splitlines():
        m = re.match(r"^([0-9a-fA-F]{8}):\s+((?:[0-9a-fA-F]{8}\s+)+)", line.strip())
        if not m:
            continue
        addr = int(m.group(1), 16)
        words = [int(w, 16) for w in m.group(2).split()]
        out[addr] = words
        flat.extend(words)
    return out, flat


def md_first_word(txt):
    _, flat = parse_md(txt)
    return flat[0] if flat else None


def md_words_equal(txt, want, count):
    _, flat = parse_md(txt)
    return len(flat) >= count and flat[:count] == want[:count]


def parse_bdinfo(txt):
    f = {}
    for key, rx in (("relocaddr", r"relocaddr\s*=\s*(0x[0-9a-fA-F]+)"),
                    ("reloc_off", r"reloc off\s*=\s*(0x[0-9a-fA-F]+)"),
                    ("dram_bank", r"DRAM bank\s*=\s*(0x[0-9a-fA-F]+)"),
                    ("dram_start", r"->\s*start\s*=\s*(0x[0-9a-fA-F]+)"),
                    ("dram_size", r"->\s*size\s*=\s*(0x[0-9a-fA-F]+)"),
                    ("fdt_blob", r"fdt_blob\s*=\s*(0x[0-9a-fA-F]+)"),
                    ("baudrate", r"baudrate\s*=\s*(\d+)")):
        m = re.search(rx, txt or "")
        f[key] = m.group(1).strip() if m else None
    return f


def parse_printenv(txt):
    env = {}
    for line in (txt or "").splitlines():
        line = line.strip()
        m = re.match(r"^([A-Za-z0-9_]+)=(.*)$", line)
        if m:
            env[m.group(1)] = m.group(2)
    return env


def parse_wire(path):
    rep = {"path": path, "present": os.path.exists(path), "lines": 0,
           "frames": 0, "uboot_mac": 0, "bootp": 0, "dhcp": 0,
           "device_mac": 0, "random_mac": 0}
    if not rep["present"]:
        return rep
    try:
        raw = open(path, "rb").read().decode("latin-1", "replace")
    except OSError:
        return rep
    lines = raw.splitlines()
    rep["lines"] = len(lines)
    rep["frames"] = max(0, len(lines) - 2)
    rep["uboot_mac"] = raw.count(FLASH_MAC)
    rep["bootp"] = len(re.findall(r"BOOTP|DHCP", raw, re.I))
    rep["device_mac"] = raw.lower().count("e0:b6:68:ac:f3:d8")
    rep["random_mac"] = raw.count(RANDOM_MAC_PREFIX)
    return rep


def pattern_crc_ok(txt):
    got = e2s.parse_crc(txt)
    return got is not None and got == PATTERN_CRC


def marker_visible(md_txt, crc_txt):
    _, flat = parse_md(md_txt)
    words_ok = len(flat) >= 4 and flat[:4] == SLOT_MARKER_WORDS
    got = e2s.parse_crc(crc_txt)
    return {"words_ok": words_ok, "crc_ok": (got == SLOT_MARKER_CRC),
            "crc": "0x%08x" % got if got is not None else None,
            "want_crc": "0x%08x" % SLOT_MARKER_CRC,
            "words": ["%08x" % w for w in flat[:8]]}


def classify_t74(t):
    sw = (t.get("suspect_write") or {}).get("readback_ok")
    cw = (t.get("control_write") or {}).get("readback_ok")
    vis = (t.get("mtd_read_suspect") or {}).get("marker", {})
    words_ok = bool(vis.get("words_ok"))
    crc_ok = bool(vis.get("crc_ok"))
    if sw and cw:
        if words_ok and crc_ok:
            return "NO_ANOMALY"
        if not words_ok and not crc_ok:
            return "READ_VIEW_ANOMALY"
        return "PARTIAL_VIEW"
    if (not sw) and cw:
        return "MAPPING_WRITE_FAIL"
    return "PARTIAL"


# ---------------------------------------------------------------- T74 block
def run_mw_md(c, res, addr, tag):
    a = "0x%08x" % addr
    out = {"addr": a, "tag": tag}
    out["md_before"] = ub_cmd(c, res, "md " + a + " 0x%x" % PATTERN_WORDS, 30)
    out["mw"] = ub_cmd(c, res, "mw " + a + " 0x%08x 0x%x" % (PATTERN_WORD, PATTERN_WORDS), 30)
    out["md_after"] = ub_cmd(c, res, "md " + a + " 0x%x" % PATTERN_WORDS, 30)
    out["crc32"] = ub_cmd(c, res, "crc32 " + a + " 0x40", 40)
    out["readback_ok"] = md_words_equal(out["md_after"], [PATTERN_WORD] * PATTERN_WORDS, PATTERN_WORDS)
    out["crc_ok"] = pattern_crc_ok(out["crc32"])
    log("T74 mw/md " + tag + " " + a + " readback_ok=" + str(out["readback_ok"])
        + " crc_ok=" + str(out["crc_ok"]))
    return out


def run_mtd_read_md(c, res, addr, tag):
    a = "0x%08x" % addr
    out = {"addr": a, "tag": tag, "flash_off": "0x%x" % SLOT1_CHIP_OFF}
    out["read"] = ub_cmd(c, res, "mtd read spi-nand0 %s 0x%x 0x800" % (a, SLOT1_CHIP_OFF), 120)
    out["read_ok"] = ("2048 byte(s)" in out["read"]) and ("Failure" not in out["read"])
    out["md"] = ub_cmd(c, res, "md %s 8" % a, 30)
    out["md_header"] = ub_cmd(c, res, "md 0x%08x 8" % (addr + 0x20), 30)
    out["crc32"] = ub_cmd(c, res, "crc32 %s 0x20" % a, 40)
    out["iminfo"] = ub_cmd(c, res, "iminfo 0x%08x" % (addr + 0x20), 40)
    out["marker"] = marker_visible(out["md"], out["crc32"])
    hdr_word = md_first_word(out["md_header"])
    out["iminfo_ok"] = ("Unknown image format" not in out["iminfo"]
                        and "Image Name" in out["iminfo"])
    out["header_magic_ok"] = (hdr_word == SLOT_HEADER_MAGIC)
    log("T74 mtd read " + tag + " " + a + " read_ok=" + str(out["read_ok"])
        + " marker_words=" + str(out["marker"]["words_ok"])
        + " marker_crc=" + str(out["marker"]["crc_ok"])
        + " iminfo_ok=" + str(out["iminfo_ok"]))
    return out


def t74_block(c, res):
    t = {"suspects": ["0x%08x" % a for a in SUSPECTS],
         "controls": ["0x%08x" % a for a in CONTROLS],
         "closed_phantom": "0x48000000 closed as a command typo (md 0x480000 reads 0x00480000); not tested",
         "pattern": "0x%08x x %d words (crc32 0x%08x)" % (PATTERN_WORD, PATTERN_WORDS, PATTERN_CRC),
         "slot_marker_crc32": "0x%08x" % SLOT_MARKER_CRC}
    t["bdinfo_before"] = parse_bdinfo(ub_cmd(c, res, "bdinfo", 60))
    t["suspect_baseline"] = ub_cmd(c, res, "md 0x%08x 8" % SUSPECTS[0], 30)
    t["suspect_write"] = run_mw_md(c, res, SUSPECTS[0], "suspect-42000000")
    t["control_write"] = run_mw_md(c, res, CONTROLS[0], "control-4C000000")
    t["control2_write"] = run_mw_md(c, res, CONTROLS[1], "control-4A000000")
    t["mtd_read_suspect"] = run_mtd_read_md(c, res, SUSPECTS[0], "suspect-42000000")
    t["bdinfo_mid"] = parse_bdinfo(ub_cmd(c, res, "bdinfo", 60))
    t["mtd_read_suspect_after_bdinfo"] = run_mtd_read_md(c, res, SUSPECTS[0], "suspect-42000000-after-bdinfo")
    t["suspect_md_after_bdinfo"] = ub_cmd(c, res, "md 0x%08x 8" % SUSPECTS[0], 30)
    ptr = t["bdinfo_mid"].get("relocaddr")
    reloc = int(ptr, 16) if ptr and ptr.startswith("0x") else None
    t["reloc"] = {"relocaddr": ptr,
                  "reloc_off": t["bdinfo_mid"].get("reloc_off"),
                  "suspect_below_reloc": (reloc is not None and SUSPECTS[0] < reloc),
                  "suspect_in_dram": (SUSPECTS[0] >= 0x40000000)}
    first = t["mtd_read_suspect"]["marker"]
    again = t["mtd_read_suspect_after_bdinfo"]["marker"]
    t["reloc_dependent"] = (first.get("words_ok") != again.get("words_ok")
                            or first.get("crc_ok") != again.get("crc_ok"))
    t["classification"] = classify_t74(t)
    log("T74 classification " + t["classification"]
        + " reloc_dependent=" + str(t["reloc_dependent"]))
    return t


# ---------------------------------------------------------------- env sanity
def env_sanity(c, res, boot_text):
    e = {"boot_text_tail": (boot_text or "")[-4000:]}
    e["boot_env_ok"] = ("Loading Environment from MTD" in (boot_text or "")
                        and "bad CRC" not in (boot_text or "")
                        and "default environment" not in (boot_text or "")
                        and "Warning: ethernet" not in (boot_text or ""))
    txt = ub_cmd(c, res, "printenv", 60)
    env = parse_printenv(txt)
    e["entries"] = len(env)
    e["expected_entries"] = EXPECTED_ENV_COUNT
    e["expected_entries_effective"] = len(EXPECTED_ENV_EFFECTIVE)
    e["runtime_extras"] = sorted(k for k in env if k in EXPECTED_RUNTIME_EXTRAS)
    unexpected = sorted(k for k in env if k not in EXPECTED_ENV_EFFECTIVE
                        and k not in EXPECTED_RUNTIME_EXTRAS)
    e["unexpected"] = unexpected
    e["entry_count_ok"] = (not unexpected and all(k in env for k in EXPECTED_ENV_EFFECTIVE))
    missing = [k for k in EXPECTED_ENV_EFFECTIVE if k not in env]
    mismatched = [k for k in EXPECTED_ENV_EFFECTIVE if k in env and env[k] != EXPECTED_ENV_EFFECTIVE[k]]
    e["missing"] = missing
    e["mismatched"] = mismatched
    e["values_ok"] = (not missing and not mismatched)
    e["ethaddr"] = env.get("ethaddr")
    e["ethaddr_ok"] = (env.get("ethaddr") == FLASH_MAC)
    e["random_mac_absent"] = not str(env.get("ethaddr", "")).startswith(RANDOM_MAC_PREFIX)
    e["bootdelay_ok"] = (env.get("bootdelay") == "3")
    e["bootcmd_ok"] = (env.get("bootcmd") == EXPECTED_ENV_EFFECTIVE["bootcmd"])
    e["stdio_ok"] = all(env.get(k) == EXPECTED_ENV_EFFECTIVE[k]
                        for k in ("stdin", "stdout", "stderr"))
    e["env_sanity_ok"] = bool(e["boot_env_ok"] and e["entry_count_ok"] and e["values_ok"]
                              and e["stdio_ok"] and e["ethaddr_ok"] and e["random_mac_absent"])
    log("env sanity ok=" + str(e["env_sanity_ok"]) + " entries=" + str(e["entries"]))
    return e


# ---------------------------------------------------------------- F2 block
def f2_block(c, res, outdir, tf):
    f2 = {"enabled": True}
    res["tcpdump"] = e2t.start_tcpdump(outdir)
    f2["mii_info"] = {"snapshot": e2t.bmu_snapshot(c, res, "before_mii"),
                      "nic": dump_nic(c, res, "before_mii"),
                      "out": ub_cmd(c, res, "mii info", 120)}
    f2["mii_info"]["after"] = e2t.bmu_snapshot(c, res, "after_mii")
    f2["e2631net"] = {"snapshot": e2t.bmu_snapshot(c, res, "before_e2631net"),
                      "nic_before": dump_nic(c, res, "before_e2631net"),
                      "out": ub_cmd(c, res, "e2631net", 180)}
    f2["e2631net"]["after"] = e2t.bmu_snapshot(c, res, "after_e2631net")
    f2["e2631net"]["nic_after"] = dump_nic(c, res, "after_e2631net")
    f2["dhcp"] = {"snapshot": e2t.bmu_snapshot(c, res, "before_dhcp"),
                  "nic_before": dump_nic(c, res, "before_dhcp"),
                  "result": e2t.dhcp_attempt(c, res, 300)}
    f2["dhcp"]["after"] = e2t.bmu_snapshot(c, res, "after_dhcp")
    f2["dhcp"]["nic_after"] = dump_nic(c, res, "after_dhcp")
    # Short retry with netretry=1 (RAM only): one BOOTP round so the MAC/TM/DMA
    # counters can be read between transmissions (Lead m08459).
    f2["dhcp_short"] = {"nic_before": dump_nic(c, res, "before_dhcp_short")}
    ub_cmd(c, res, "setenv netretry 1", 30)
    f2["dhcp_short"]["result"] = e2t.dhcp_attempt(c, res, 180)
    f2["dhcp_short"]["nic_after"] = dump_nic(c, res, "after_dhcp_short")
    ub_cmd(c, res, "setenv netretry 5", 30)
    if f2["dhcp"]["result"].get("ip"):
        ub_cmd(c, res, "setenv serverip " + HOST_IP, 60)
    else:
        log("dhcp gave no address; setting RAM-only static addresses for ping/tftp")
        f2["static_fallback"] = True
        ub_cmd(c, res, "setenv ipaddr 192.168.1.50", 60)
        ub_cmd(c, res, "setenv netmask 255.255.255.0", 60)
        ub_cmd(c, res, "setenv serverip " + HOST_IP, 60)
    f2["ping"] = {"snapshot": e2t.bmu_snapshot(c, res, "before_ping"),
                  "nic_before": dump_nic(c, res, "before_ping"),
                  "out": ub_cmd(c, res, "ping " + HOST_IP, 180)}
    f2["ping"]["after"] = e2t.bmu_snapshot(c, res, "after_ping")
    f2["ping"]["nic_after"] = dump_nic(c, res, "after_ping")
    f2["tftp"] = {"snapshot": e2t.bmu_snapshot(c, res, "before_tftp"),
                  "nic_before": dump_nic(c, res, "before_tftp"),
                  "out": ub_cmd(c, res, "tftp 0x%08x %s" % (TFTP_ADDR, e2s.TEST_NAME), 240)}
    f2["tftp"]["after"] = e2t.bmu_snapshot(c, res, "after_tftp")
    f2["tftp"]["nic_after"] = dump_nic(c, res, "after_tftp")
    m = re.search(r"Bytes transferred = (\d+)", f2["tftp"]["out"])
    f2["tftp"]["bytes"] = int(m.group(1)) if m else None
    f2["tftp"]["size"] = tf.get("size")
    f2["tftp"]["crc"] = {"out": ub_cmd(c, res, "crc32 0x%08x 0x%x" % (TFTP_ADDR, tf["size"]), 120)}
    got = e2s.parse_crc(f2["tftp"]["crc"]["out"])
    f2["tftp"]["crc"]["got"] = "0x%08x" % got if got is not None else None
    f2["tftp"]["crc"]["want"] = tf.get("crc32")
    f2["tftp"]["ok"] = (f2["tftp"]["bytes"] == tf.get("size")
                        and f2["tftp"]["crc"]["got"] == tf.get("crc32"))
    e2t.stop_tcpdump()
    f2["wire"] = parse_wire(os.path.join(outdir, "tcpdump.log"))
    f2["wire_frames_seen"] = (f2["wire"]["uboot_mac"] > 0 or f2["wire"]["bootp"] > 0)
    f2["verdict"] = "WIRE_FRAMES" if f2["wire_frames_seen"] else "NO_WIRE_FRAMES"

    def frame_count(tag):
        regs = ((res.get("nic") or {}).get(tag) or {}).get("regs") or {}
        v = (regs.get("lan1_mac_tx_frames") or [None])[0]
        try:
            return int(v, 16)
        except (TypeError, ValueError):
            return None
    f2["egress"] = {
        "tx_frames_after_e2631net": frame_count("after_e2631net"),
        "tx_frames_after_dhcp": frame_count("after_dhcp"),
        "tx_frames_after_dhcp_short": frame_count("after_dhcp_short"),
        "tx_frames_after_ping": frame_count("after_ping"),
        "tx_frames_after_tftp": frame_count("after_tftp"),
    }
    vals = [v for v in f2["egress"].values() if isinstance(v, int)]
    f2["egress"]["mac_tx_advanced"] = bool(len(vals) >= 2 and max(vals) > min(vals))
    log("F2 verdict " + f2["verdict"] + " " + json.dumps(f2["wire"])
        + " egress=" + json.dumps(f2["egress"]))
    return f2


def f1_block(c, res):
    f1 = {}
    load_txt = ub_cmd(c, res, "e2631boot load", 240)
    f1["load"] = {"out": load_txt, "crc_good": "header and data CRCs are good" in load_txt}
    # NOTE: the full 32-bit addresses are required.  An earlier revision of this
    # block (and of the e2t_session.py probes copied into it) sent "md 0x420000"
    # and "crc32 0x420020", which read 0x00420000/0x00420020 instead of
    # 0x42000000/0x42000020 and produced the false "image loaded but reads back
    # as zeros" observation.
    f1["md_marker"] = ub_cmd(c, res, "md 0x%08x 8" % LOAD_ADDR, 30)
    f1["md_header"] = ub_cmd(c, res, "md 0x%08x 8" % (LOAD_ADDR + 0x20), 30)
    f1["crc32_header"] = ub_cmd(c, res, "crc32 0x%08x 0x40" % (LOAD_ADDR + 0x20), 40)
    f1["iminfo_marker"] = ub_cmd(c, res, "iminfo 0x%08x" % LOAD_ADDR, 40)
    f1["iminfo_uimage"] = ub_cmd(c, res, "iminfo 0x%08x" % (LOAD_ADDR + 0x20), 40)
    att = e2t.bootm_attempt(c, res, "e2631boot", 300)
    f1["boot"] = att
    if att["outcome"] == "kernel":
        f1["verdict"] = "KERNEL_STARTED"
        res["linux_marker"] = e2s.wait_linux_console(c, 300)
    elif att["outcome"] == "prompt":
        if "Wrong Image Type" in att["out"]:
            f1["verdict"] = "WRONG_IMAGE_TYPE_RETURN"
        elif "Bad Magic" in att["out"]:
            f1["verdict"] = "BAD_MAGIC_RETURN"
        else:
            f1["verdict"] = "SILENT_RETURN"
    else:
        f1["verdict"] = "TIMEOUT"
    log("F1 verdict " + f1["verdict"])
    return f1


# ---------------------------------------------------------------- env block + NIC
def env_block_diag(c, res):
    """Read the env block at 0xC0000 at the new prompt and compare it to the B1 baseline."""
    e = {"offset": "0x%x" % ENV_BLOCK_OFF, "length": "0x%x" % ENV_BLOCK_LEN,
         "addr": "0x%08x" % ENV_READ_ADDR, "expected": expected_env_block()}
    txt = ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x"
                 % (ENV_READ_ADDR, ENV_BLOCK_OFF, ENV_BLOCK_LEN), 240)
    e["read_tail"] = (txt or "")[-400:]
    e["read_ok"] = (("%d byte(s)" % ENV_BLOCK_LEN) in (txt or "")) and ("Failure" not in (txt or ""))
    md = ub_cmd(c, res, "md 0x%08x 4" % ENV_READ_ADDR, 30)
    e["md"] = md
    stored = md_first_word(md)
    e["stored_crc"] = "0x%08x" % stored if stored is not None else None
    crc_txt = ub_cmd(c, res, "crc32 0x%08x 0x%x" % (ENV_READ_ADDR, ENV_BLOCK_LEN), 240)
    got = e2s.parse_crc(crc_txt)
    e["region_crc"] = "0x%08x" % got if got is not None else None
    e["want_region_crc"] = "0x%08x" % ENV_REGION_CRC
    e["want_stored_crc"] = "0x%08x" % ENV_STORED_CRC
    e["want_block_sha"] = ENV_BLOCK_SHA
    e["read_ok"] = bool(e["read_ok"])
    e["stored_ok"] = (e["stored_crc"] == e["want_stored_crc"])
    e["region_ok"] = (e["region_crc"] == e["want_region_crc"])
    e["state"] = "OK" if (e["read_ok"] and e["stored_ok"] and e["region_ok"]) else "BAD"
    log("env block state=%s stored=%s region=%s" % (e["state"], e["stored_crc"], e["region_crc"]))
    return e


def dump_nic(c, res, tag):
    """Snapshot the NIC/TM/DMA/switch registers that the F2 diagnosis needs."""
    rep = {"tag": tag, "regs": {}}
    for name, addr, count in NIC_REGS:
        txt = ub_cmd(c, res, "md 0x%08x %d" % (addr, count), 30)
        _, flat = parse_md(txt)
        words = ["0x%08x" % w for w in flat[:count]]
        if len(words) < count:
            words.extend(["MISSING"] * (count - len(words)))
        rep["regs"][name] = words
    r = rep["regs"]
    rep["summary"] = {
        "mac_ctrl": r.get("lan1_mac_ctrl"),
        "mac_tx_frames": r.get("lan1_mac_tx_frames"),
        "mac_tx_octets": r.get("lan1_mac_tx_octets"),
        "tm_int_status": r.get("tm_int_status"),
        "tm_int_mask": r.get("tm_int_mask"),
        "bmu_buf_alloc": r.get("bmu_buf_alloc"),
        "dma_ctrl": r.get("dma_ctrl"),
        "dma_tx_done": r.get("dma_tx_done"),
        "rx_queue_counts": r.get("dma_rx_queue_counts"),
        "sw_fwd_ctrl": r.get("sw_fwd_ctrl"),
        "spa_port_en": r.get("spa_port_en"),
    }
    res.setdefault("nic", {})[tag] = rep
    return rep


def loadx_verify(c, res, art_path):
    """--loadx mode: transfer the image over serial and verify it in RAM before go."""
    data = open(art_path, "rb").read()
    out = {"path": art_path, "size": len(data), "addr": "0x%08x" % LOAD_ADDR}
    tr = fin.xmodem_cmd(c, res, art_path, "loadx 0x%08x\r" % LOAD_ADDR, 1024)
    out["transfer"] = tr if isinstance(tr, dict) else repr(tr)
    banner_off = data.find(b"U-Boot 2027")
    spots = []
    for label, off0 in (("start", 0),
                        ("banner", banner_off if banner_off > 0 else 0),
                        ("tail", max(0, len(data) - 0x100))):
        want = data[off0:off0 + 0x100]
        spots.append(fin.md_check(c, res, "loadx-" + label, LOAD_ADDR + off0, want))
    out["spots"] = spots
    out["ok"] = bool(all(x.get("ok") for x in spots) and (tr or {}).get("ok") is not False)
    log("loadx verify ok=" + str(out["ok"]))
    return out


def rescue_presence(c, res):
    """Read-only presence check: help e2631rescue must list the command."""
    r = {}
    txt = ub_cmd(c, res, "help e2631rescue", 60)
    r["help_text"] = txt
    r["present"] = "e2631rescue" in (txt or "")
    r["short_help"] = "serve the web bootloader rescue on lan1" in (txt or "")
    if not r["present"]:
        txt = ub_cmd(c, res, "help", 60)
        r["help_all_tail"] = (txt or "")[-2000:]
        r["present"] = "e2631rescue" in (txt or "")
    log("rescue command present=" + str(r["present"]))
    return r


def env_retry_via_loadx(c, res, art_path, token):
    """Second RAM load over serial after a BAD env on the first boot.

    Zero flash writes: loadx the same artifact again, go, then re-read the env
    block and the printenv baseline.  The caller keeps the final env sanity.
    """
    r = {"attempted": True, "reason": "env sanity failed on the first RAM boot"}
    res["env_retry"] = r
    log("ENV BAD on the first RAM boot; retrying with an in-session loadx reload")
    try:
        r["loadx"] = loadx_verify(c, res, art_path)
        if not r["loadx"].get("ok"):
            r["ok"] = False
            r["error"] = "loadx reload did not verify in RAM"
            return r
        boot_idx = len(c.history)
        c.pending = b""
        c.send(b"go 0x47f00000\r")
        r["go_sent"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        r["banner_seen"] = e2s.wait_banner(c, token, 90)
        if not r["banner_seen"]:
            r["ok"] = False
            r["error"] = "no banner after the loadx go"
            return r
        r["stop_autoboot"] = fin.stop_autoboot(c, res, token, 20)
        if not r["stop_autoboot"].get("prompt"):
            r["ok"] = False
            r["error"] = "no prompt after the loadx go"
            return r
        r["version_ok"] = token in ub_cmd(c, res, "version", 60)
        boot_text = bytes(c.history[boot_idx:]).decode("latin-1", "replace")
        r["boot_text_tail"] = boot_text[-4000:]
        r["env_block"] = env_block_diag(c, res)
        r["env_sanity"] = env_sanity(c, res, boot_text)
        r["ok"] = True
        log("env retry complete, env sanity ok=" + str(r["env_sanity"].get("env_sanity_ok")))
    except Exception as exc:
        r["ok"] = False
        r["error"] = repr(exc)
        log("env retry ERROR " + repr(exc))
    return r


# ---------------------------------------------------------------- artifact pins
def artifact_expected(art_path):
    """Derive expected pins from the archive UBOOT-INFO.txt next to u-boot.bin."""
    exp = {"sha256": None, "banner_token": None, "size": None, "crc32": None,
           "info_path": None, "mtd0_sha": None, "tree": None}
    directory = art_path if os.path.isdir(art_path) else os.path.dirname(art_path)
    info = os.path.join(directory, "UBOOT-INFO.txt")
    exp["info_path"] = info
    if not os.path.exists(info):
        return exp
    txt = open(info, encoding="utf-8", errors="replace").read()
    m = re.search(r"u-boot\.bin sha256:\s*([0-9a-f]{64})", txt)
    if m:
        exp["sha256"] = m.group(1)
    m = re.search(r"u-boot\.bin crc32:\s*([0-9a-fA-F]{8})", txt)
    if m:
        exp["crc32"] = "0x" + m.group(1).lower()
    m = re.search(r"u-boot\.bin size:\s*(\d+)", txt)
    if m:
        exp["size"] = int(m.group(1))
    m = re.search(r"Banner:\s*([^\r\n]+)", txt)
    if m:
        tok = re.search(r"U-Boot 2027\.01-rc2-g[0-9a-f]+", m.group(1))
        exp["banner_token"] = tok.group(0) if tok else m.group(1).strip()
    m = re.search(r"mtd0 image: .*sha256\s*([0-9a-f]{64})", txt)
    if m:
        exp["mtd0_sha"] = m.group(1)
    m = re.search(r"Post-am tree:\s*([0-9a-f]{40})", txt)
    if m:
        exp["tree"] = m.group(1)
    return exp


def resolve_artifact(path):
    if os.path.isdir(path):
        candidate = os.path.join(path, "u-boot.bin")
        if not os.path.exists(candidate):
            raise SystemExit("no u-boot.bin in " + path)
        return candidate
    if not os.path.exists(path):
        raise SystemExit("artifact not found: " + path)
    return path


def preflight(args):
    os.makedirs(args.out_dir, exist_ok=True)
    base.LOG = args.out_dir + "/preflight.log"
    b1.make_askpass()
    rep = {}
    art_path = resolve_artifact(args.artifact)
    rep["artifact"] = e2s.artifact_facts(art_path)
    rep["expected"] = artifact_expected(args.artifact)
    rep["artifact_pins"] = {
        "sha_ok": (rep["expected"]["sha256"] or rep["artifact"]["sha256"]) == rep["artifact"]["sha256"],
        "crc_ok": (rep["expected"]["crc32"] or rep["artifact"]["crc32"]) == rep["artifact"]["crc32"],
        "banner_ok": (rep["expected"]["banner_token"] or rep["artifact"]["banner_token"])
                     == rep["artifact"]["banner_token"],
        "size_ok": (rep["expected"]["size"] or rep["artifact"]["size"]) == rep["artifact"]["size"],
        "size": rep["artifact"]["size"], "crc32": rep["artifact"]["crc32"],
        "banner": rep["artifact"]["banner_token"],
    }
    rep["padded"] = ({"skipped": "--loadx: no padded staging image needed"} if args.loadx
                     else e2s.pad_artifact(art_path, args.out_dir))
    rep["testfile"] = e2s.testfile_facts()
    rep["route"] = b1.ensure_direct_link()
    rep["capture_chain"] = {"supervisor": base.pgrep("capture-supervisor-002.sh"),
                            "bootwatch": base.pgrep("serial-bootwatch.mjs"),
                            "tty": base.tty_holders()}
    try:
        rep["device"] = e2s.device_facts()
        region = e2s.ssh("dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d\" \" -f1", 120)
        rep["region_sha"] = (region.get("out") or "").split()[0] if (region.get("out") or "").split() else None
    except Exception as exc:
        rep["device"] = {"error": repr(exc)}
        rep["region_sha"] = None
    dev = rep.get("device") or {}
    if args.with_f2:
        rep["services"] = e2s.check_services()
    rep["ok"] = bool(all(rep["artifact_pins"][k] for k in ("sha_ok", "crc_ok", "banner_ok", "size_ok"))
                     and rep["route"].get("ok")
                     and dev.get("mtd0_sha") == MTD0_SHA
                     and rep["region_sha"] == REGION_SHA)
    print(json.dumps(rep, indent=1))
    return rep


# ---------------------------------------------------------------- session
def run_session(args):
    outdir = args.out_dir
    os.makedirs(outdir, exist_ok=True)
    base.LOG = outdir + "/driver.log"
    art_path = resolve_artifact(args.artifact)
    art = e2s.artifact_facts(art_path)
    exp = artifact_expected(args.artifact)
    padded = ({"skipped": "--loadx: no padded staging image needed"} if args.loadx
              else e2s.pad_artifact(art_path, outdir))
    tf = e2s.testfile_facts()
    res = {"mode": "e2631-t74-f2-session", "with_f2": bool(args.with_f2),
           "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "artifact": art, "expected": exp, "padded": padded, "testfile": tf,
           "uboot_commands": []}
    res["artifact_pins"] = {
        "sha_ok": (exp["sha256"] or art["sha256"]) == art["sha256"],
        "crc_ok": (exp["crc32"] or art["crc32"]) == art["crc32"],
        "banner_ok": (exp["banner_token"] or art["banner_token"]) == art["banner_token"],
        "size_ok": (exp["size"] or art["size"]) == art["size"],
    }

    def region_facts():
        r = e2s.ssh("sha256sum /dev/mtd0 | cut -d\" \" -f1; "
                    "dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d\" \" -f1", 120)
        lines = [x for x in (r.get("out") or "").strip().splitlines() if x.strip()]
        return {"mtd0": lines[0].split()[0] if len(lines) > 0 else None,
                "region": lines[1].split()[0] if len(lines) > 1 else None,
                "raw": (r.get("out") or "")[-400:]}

    try:
        res["host_before"] = region_facts()
    except Exception as exc:
        res["host_before"] = {"error": repr(exc)}
    b1.make_askpass()
    c = None
    try:
        if not all(res["artifact_pins"].values()):
            raise RuntimeError("artifact pins do not match the UBOOT-INFO expectations")
        res["route"] = b1.ensure_direct_link()
        if not res["route"].get("ok"):
            raise RuntimeError("no direct route to the device")
        res["device_before"] = e2s.device_facts()
        if res["device_before"].get("mtd0_sha") != MTD0_SHA:
            raise RuntimeError("device mtd0 is not the expected baseline")
        res["host_before2"] = region_facts()
        if res["host_before2"].get("region") != REGION_SHA:
            raise RuntimeError("device image region is not the expected baseline")
        chain0 = {"supervisor": base.pgrep("capture-supervisor-002.sh"),
                  "bootwatch": base.pgrep("serial-bootwatch.mjs"),
                  "tty": base.tty_holders()}
        res["capture_chain_before"] = chain0
        if not chain0["supervisor"] and not chain0["bootwatch"]:
            res["capture_restart"] = base.restore_capture()
        if args.with_f2:
            res["services"] = e2s.start_services()
        if args.loadx:
            res["load_path"] = "loadx"
            res["staging"] = {"skipped": "--loadx: the image goes over serial; no flash write at all"}
            log("PHASE 1 (loadx): no flash write; the transfer happens at the flash U-Boot prompt")
        else:
            res["load_path"] = "userdata"
            res["staging_http"] = {"skipped": "staging goes over SSH stdin (host 18080/18081 may be held)"}
            res["staging"] = e2t.stage_userdata_ssh(art, padded, outdir)
            log("PHASE 1 GREEN: artifact staged in userdata and read back")
        res["capture_pause"] = base.pause_capture()
        res["hub_pid"] = base.start_hub(outdir + "/serial.log")
        c = base.Console()
        time.sleep(0.4)
        c.drain()
        b1.ssh_run("sync; (sleep 1; reboot -f) </dev/null >/dev/null 2>&1 &", timeout=30)
        log("reboot -f requested; waiting for the flash U-Boot banner")
        res["flash_banner_seen"] = e2s.wait_banner(c, FLASH_BANNER, 180)
        if not res["flash_banner_seen"]:
            raise RuntimeError("flash U-Boot banner not seen after reboot")
        res["flash_stop_autoboot"] = fin.stop_autoboot(c, res, FLASH_BANNER, 30)
        if not res["flash_stop_autoboot"].get("prompt"):
            raise RuntimeError("no flash U-Boot prompt")
        txt = ub_cmd(c, res, "version", 60)
        res["flash_version_ok"] = FLASH_BANNER in txt
        if not res["flash_version_ok"]:
            raise RuntimeError("flash U-Boot version mismatch")
        if args.loadx:
            res["loadx"] = loadx_verify(c, res, art_path)
            if not res["loadx"].get("ok"):
                raise RuntimeError("loadx transfer/verification failed; refusing to go")
            log("gate: loadx image verified in RAM")
        else:
            txt = ub_cmd(c, res, "mtd read spi-nand0 0x%08x 0x%x 0x%x" % (LOAD_ADDR, STAGE_OFF, STAGE_LEN), 240)
            res["read_staging"] = {"ok": ("%d byte(s)" % STAGE_LEN) in txt and "Failure" not in txt,
                                   "tail": txt[-800:]}
            if not res["read_staging"]["ok"]:
                raise RuntimeError("staging read into RAM failed")
            txt = ub_cmd(c, res, "crc32 0x%08x 0x%x" % (LOAD_ADDR, art["size"]), 120)
            got = e2s.parse_crc(txt)
            res["staging_crc"] = {"got": "0x%08x" % got if got is not None else None,
                                  "want": art["crc32"],
                                  "ok": got is not None and ("0x%08x" % got) == art["crc32"]}
            if not res["staging_crc"]["ok"]:
                raise RuntimeError("staged image crc32 mismatch; refusing to go")
            log("gate: staged image crc32 == " + art["crc32"])
        boot_idx = len(c.history)
        c.pending = b""
        c.send(b"go 0x47f00000\r")
        res["go_sent"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        res["new_banner_seen"] = e2s.wait_banner(c, art["banner_token"], 90)
        if not res["new_banner_seen"]:
            raise RuntimeError("new image banner not seen after go")
        res["new_stop_autoboot"] = fin.stop_autoboot(c, res, art["banner_token"], 20)
        if not res["new_stop_autoboot"].get("prompt"):
            raise RuntimeError("no prompt in the new image")
        txt = ub_cmd(c, res, "version", 60)
        res["new_version_ok"] = art["banner_token"] in txt
        log("PHASE 2 GREEN: new image banner and prompt")
        boot_text = bytes(c.history[boot_idx:]).decode("latin-1", "replace")
        res["env_block"] = env_block_diag(c, res)
        res["env_sanity"] = env_sanity(c, res, boot_text)
        if not res["env_sanity"]["env_sanity_ok"] and not args.loadx and not args.no_env_retry:
            res["env_retry"] = env_retry_via_loadx(c, res, art_path, art["banner_token"])
            if (res["env_retry"].get("env_sanity") or {}).get("env_sanity_ok"):
                res["env_sanity_first_load"] = res["env_sanity"]
                res["env_sanity"] = res["env_retry"]["env_sanity"]
                res["env_sanity"]["second_load_after_bad_first"] = True
                log("env sanity recovered on the second loadx reload")
            else:
                res["env_sanity"]["next_step"] = ("the in-session loadx retry did not recover the env; "
                                                  "stop the session and report the deterministic regression")
        elif not res["env_sanity"]["env_sanity_ok"]:
            res["env_sanity"]["next_step"] = ("re-run with --loadx (serial transfer, zero flash writes) "
                                              "to rule out the userdata mtd-read path")
        res["rescue"] = rescue_presence(c, res)
        if args.with_f2:
            if res["env_sanity"]["env_sanity_ok"]:
                res["f2"] = f2_block(c, res, outdir, tf)
            else:
                log("F2 skipped: env sanity failed, F2 data would be taken under the default env")
                res["f2"] = {"enabled": True, "verdict": "SKIPPED_ENV_BAD",
                             "note": "env sanity failed; F2 is only meaningful after the env regression is fixed"}
        else:
            res["f2"] = {"enabled": False, "skipped": "use --with-f2 after the env regression is fixed"}
        res["t74"] = t74_block(c, res)
        res["f1"] = f1_block(c, res)
    except Exception as exc:
        res["error"] = repr(exc)
        log("SESSION ERROR " + repr(exc))
    finally:
        try:
            e2t.stop_tcpdump()
        except Exception as exc:
            res["stop_tcpdump_error"] = repr(exc)
        try:
            if c is not None:
                open(os.path.join(outdir, "console-history.txt"), "wb").write(bytes(c.history))
        except Exception:
            pass
        try:
            base.stop_hub()
        except Exception as exc:
            res["stop_hub_error"] = repr(exc)
        try:
            res["capture_after"] = base.restore_capture()
        except Exception as exc:
            res["capture_after"] = {"ok": False, "error": repr(exc)}
        if args.with_f2:
            try:
                e2s.stop_services()
            except Exception as exc:
                res["stop_services_error"] = repr(exc)
        for name in ("dnsmasq.log", "http.log", "testfile.json"):
            src = E2 + "/logs/" + name
            if os.path.exists(src):
                try:
                    shutil.copyfile(src, os.path.join(outdir, name))
                except Exception:
                    pass
        try:
            b1.make_askpass()
            b1.ensure_direct_link()
            b1.wait_uptime(60, 240)
            res["device_after"] = e2s.device_facts()
            res["postcheck"] = e2s.ssh(
                "echo VERSION=$(cat /etc/e2631-version); "
                "echo KERNEL=$(uname -r); "
                "echo PANICS=$(dmesg | grep -ci -E panic || true); "
                "echo OOPS=$(dmesg | grep -ci Oops || true); "
                "echo MT7916=$(dmesg | grep -ci MT7916 || true); "
                "echo MTD0=$(sha256sum /dev/mtd0 | cut -d\" \" -f1); "
                "echo REGION=$(dd if=/dev/mtd0 bs=4096 skip=32 count=160 2>/dev/null | sha256sum | cut -d\" \" -f1); "
                "e2631-fwslot info -j | head -c 400", 180)
        except Exception as exc:
            res["device_after"] = {"error": repr(exc)}
        # Lead m08418: record the kernel NIC view in the same session so U-Boot and
        # Linux link/MDIO behaviour can be compared. Informational only.
        try:
            res["kernel_nic_view"] = e2s.ssh(
                "echo NIC_BEGIN; dmesg | grep -i -E \"zx279128s-eth|PHY\" | head -30; echo NIC_END", 120)
        except Exception as exc:
            res["kernel_nic_view"] = {"error": repr(exc)}
        cmds = [x["cmd"] for x in res.get("uboot_commands", [])]
        res["audit"] = {
            "uboot_commands": cmds,
            "forbidden": [x for x in cmds if FORBIDDEN_RE.search(x)
                          and not ((getattr(args, "loadx", False)
                                   or (res.get("env_retry") or {}).get("attempted"))
                                   and x.startswith("loadx "))],
            "staging_ops": {k: ((res.get("staging") or {}).get(k) or {}).get("rc")
                            for k in ("erase", "write", "readback", "sync")},
            "staging_cmds": [x for x in cmds if x.startswith("mtd ")],
        }
        post = (res.get("postcheck") or {}).get("out", "")
        after = res.get("device_after") or {}
        t74 = res.get("t74") or {}
        f2 = res.get("f2") or {}
        checks = {
            "artifact_pins": all(res["artifact_pins"].values()),
            "load_path": res.get("load_path"),
            "loading": (bool((res.get("loadx") or {}).get("ok")) if res.get("load_path") == "loadx"
                        else bool((res.get("staging") or {}).get("ok"))),
            "loading_gate": (bool((res.get("loadx") or {}).get("ok")) if res.get("load_path") == "loadx"
                             else bool((res.get("staging_crc") or {}).get("ok"))),
            "env_block": (res.get("env_block") or {}).get("state"),
            "new_banner": bool(res.get("new_banner_seen")),
            "new_version": bool(res.get("new_version_ok")),
            "env_sanity": bool((res.get("env_sanity") or {}).get("env_sanity_ok")),
            "t74_recorded": bool(t74),
            "f2_verdict": f2.get("verdict") if f2.get("enabled") else "SKIPPED",
            "f1_verdict": (res.get("f1") or {}).get("verdict"),
            "no_uboot_flash_writes": not res["audit"]["forbidden"],
            "mtd0_unchanged": (after.get("mtd0_sha") == MTD0_SHA) or (MTD0_SHA in post),
            "region_unchanged": REGION_SHA in post,
            "no_panics": "PANICS=0" in post,
            "kernel_nic_view": bool(((res.get("kernel_nic_view") or {}).get("out") or "").strip()),
            "capture_after": bool((res.get("capture_after") or {}).get("ok")),
            "no_error": not res.get("error"),
        }
        res["checks"] = checks
        f1v = checks["f1_verdict"]
        session_green = bool(f1v == "KERNEL_STARTED" and checks["mtd0_unchanged"]
                             and checks["region_unchanged"] and checks["no_uboot_flash_writes"]
                             and checks["loading"] and checks["no_error"] and checks["env_sanity"])
        res["verdict"] = {
            "session": "GREEN" if session_green else ("ERROR" if res.get("error") else "FAIL"),
            "env_sanity": "OK" if checks["env_sanity"] else "BAD",
            "env_retry": ("recovered" if (res.get("env_retry") or {}).get("env_sanity", {}).get("env_sanity_ok")
                          else "failed" if res.get("env_retry") else "not-needed"),
            "rescue": "present" if (res.get("rescue") or {}).get("present") else "absent",
            "f2": checks["f2_verdict"],
            "t74": t74.get("classification"),
            "f1": f1v,
        }
        res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        json.dump(res, open(os.path.join(outdir, "session-results.json"), "w"), indent=1)
        log("VERDICT " + json.dumps(res["verdict"]))
        log("checks: " + json.dumps(checks))
    return 0 if (res.get("verdict") or {}).get("session") == "GREEN" else 2


# ---------------------------------------------------------------- selftest
def selftest():
    assert PATTERN_CRC == zlib.crc32(PATTERN_WORD.to_bytes(4, "little") * PATTERN_WORDS) & 0xFFFFFFFF
    assert SLOT_MARKER_CRC == 0x5076ACE3, hex(SLOT_MARKER_CRC)
    assert len(SLOT_MARKER) == 32 and SLOT_MARKER_WORDS[0] == 0x33333333
    # parser: md output with two lines
    md = "42000000: 33333333 cccccccc 88888888 dddddddd  ................\r\n" \
         "42000010: ffffffff ffffffff ffffffff ffffffff  ................\r\n=> "
    d, flat = parse_md(md)
    assert flat[:4] == SLOT_MARKER_WORDS and len(flat) == 8
    assert md_words_equal(md, SLOT_MARKER_WORDS, 4)
    # bdinfo parser
    bd = "relocaddr   = 0x4ff8a000\r\nreloc off   = 0x07f8a000\r\n" \
         "DRAM bank   = 0x00000000\r\n-> start    = 0x40000000\r\n-> size     = 0x10000000\r\n" \
         "fdt_blob    = 0x4fff0ff0\r\nbaudrate    = 115200 bps\r\n"
    b = parse_bdinfo(bd)
    assert b["relocaddr"] == "0x4ff8a000" and b["reloc_off"] == "0x07f8a000"
    assert b["dram_start"] == "0x40000000" and b["dram_size"] == "0x10000000"
    assert b["fdt_blob"] == "0x4fff0ff0" and b["baudrate"] == "115200"
    # printenv parser
    env = parse_printenv("baudrate=115200\r\nbootdelay=3\r\nbad line\r\n\r\nEnvironment size: 733/131068 bytes")
    assert env["baudrate"] == "115200" and env["bootdelay"] == "3" and len(env) == 2
    # allowlist
    assert command_allowed("md 0x42000000 8")
    assert command_allowed("mw 0x42000000 0x11223344 0x10")
    assert command_allowed("mtd read spi-nand0 0x42000000 0x2300000 0x800")
    assert command_allowed("crc32 0x42000000 0x40")
    assert command_allowed("iminfo 0x420020")
    assert command_allowed("bdinfo") and command_allowed("printenv")
    assert command_allowed("e2631boot") and command_allowed("e2631boot load")
    assert command_allowed("setenv serverip 192.168.1.191")
    assert not command_allowed("mtd write spi-nand0 0x42000000 0x20000 0xa0000")
    assert not command_allowed("mtd erase spi-nand0 0x20000 0xa0000")
    assert not command_allowed("saveenv")
    assert not command_allowed("mw 0x43000000 0x11223344 0x10")   # mw outside test addresses
    assert not command_allowed("bootm 0x420020")
    assert not command_allowed("reset")
    assert FORBIDDEN_RE.search("mtd write spi-nand0 0x42000000 0x20000 0xa0000")
    assert FORBIDDEN_RE.search("saveenv")
    assert not FORBIDDEN_RE.search("mtd read spi-nand0 0x42000000 0x2300000 0x800")
    assert not FORBIDDEN_RE.search("e2631boot load")
    # classification logic
    base_t = {"suspect_write": {"readback_ok": True}, "control_write": {"readback_ok": True},
              "mtd_read_suspect": {"marker": {"words_ok": False, "crc_ok": False}}}
    assert classify_t74(base_t) == "READ_VIEW_ANOMALY"
    base_t["mtd_read_suspect"]["marker"] = {"words_ok": True, "crc_ok": True}
    assert classify_t74(base_t) == "NO_ANOMALY"
    base_t["mtd_read_suspect"]["marker"] = {"words_ok": True, "crc_ok": False}
    assert classify_t74(base_t) == "PARTIAL_VIEW"
    base_t["suspect_write"]["readback_ok"] = False
    assert classify_t74(base_t) == "MAPPING_WRITE_FAIL"
    # expected env count / ethaddr
    assert EXPECTED_ENV_COUNT == 26 and EXPECTED_ENV["ethaddr"] == FLASH_MAC
    assert not FLASH_MAC.startswith(RANDOM_MAC_PREFIX)
    # env block diagnostics and NIC snapshot constants
    assert ENV_BLOCK_OFF == 0xC0000 and ENV_BLOCK_LEN == 0x20000
    assert ENV_STORED_CRC == 0xF95A816E and ENV_REGION_CRC == 0xE826C394
    assert ENV_BLOCK_SHA.startswith("6e2c01da")
    exp_env = expected_env_block()
    if exp_env["sha256"]:
        assert exp_env["sha256"] == ENV_BLOCK_SHA
        assert exp_env["crc"] == ENV_REGION_CRC and exp_env["stored"] == ENV_STORED_CRC
    assert len(NIC_REGS) >= 14 and NIC_REGS[0][1] == 0x92280000
    assert command_allowed("setenv netretry 1")
    assert command_allowed("md 0x92350068 1")
    assert EXPECTED_ENV_EFFECTIVE["bootcmd"] == "e2631boot"
    assert "fdtcontroladdr" in EXPECTED_RUNTIME_EXTRAS
    print("selftest ok: pattern_crc=0x%08x slot_marker_crc=0x%08x env_entries=%d effective=%d"
          % (PATTERN_CRC, SLOT_MARKER_CRC, EXPECTED_ENV_COUNT, len(EXPECTED_ENV_EFFECTIVE)))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=False, default=None,
                    help="u-boot.bin or the CI archive directory (with UBOOT-INFO.txt)")
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    ap.add_argument("--with-f2", action="store_true")
    ap.add_argument("--loadx", action="store_true",
                    help="serial xmodem load from the flash prompt instead of userdata staging "
                         "(zero flash writes; use when the thin-image env is still bad)")
    ap.add_argument("--no-env-retry", action="store_true",
                    help="do not reload the image over serial when the first RAM boot shows a bad env")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--session", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.artifact:
        raise SystemExit("--artifact is required (new thin image after the env/BMU fixes)")
    if args.preflight:
        return 0 if preflight(args).get("ok") else 1
    if args.session:
        return run_session(args)
    raise SystemExit("choose --preflight, --session or --selftest")


if __name__ == "__main__":
    sys.exit(main())
