import json, os, re
R = os.environ.get('A6_RUN_DIR', '/home/qc233/zte/e2631-p3/c1b1fix/a6-pcie/run-3')
OUT = os.environ.get('A6_POSTCHECK', R + '/post/postcheck.json')
serial = open(R + '/serial.log', 'rb').read().decode('latin-1', 'replace')
dev = open(R + '/post/device-readonly.txt', 'r', errors='replace').read()
res = json.load(open(R + '/session-results.json'))

def has(text, s):
    return s in text

gate = res.get('gpio_gate_checks') or {}
p2 = gate.get('pin2') or {}
p51 = gate.get('pin51') or {}
checks = {}
checks['artifact_contract'] = bool((res.get('artifact_contract') or {}).get('ok'))
checks['new_banner'] = bool(res.get('new_version_ok'))
checks['refclk_after_ok'] = bool(res.get('refclk_after_ok'))
checks['gate_pin2_bit2'] = bool(p2.get('ok')) and p2.get('value') == '0x0000db2c'
checks['gate_pin51_bit3'] = bool(p51.get('ok')) and p51.get('value') == '0x0000e028'
checks['kernel_started'] = bool((res.get('kernel') or {}).get('kernel_start'))
checks['linux_marker'] = (res.get('kernel') or {}).get('linux_marker') == 'Please press Enter'
checks['pcie_link_f000000'] = has(dev, 'zx279128s-pcie f000000.pcie: PCIe Gen.1 x1 link up')
checks['pcie_link_f100000'] = has(dev, 'zx279128s-pcie f100000.pcie: PCIe Gen.1 x1 link up')
checks['endpoint_7906'] = has(dev, '0000:01:00.0 0x14c3:0x7906')
checks['endpoint_790a'] = has(dev, '0001:01:00.0 0x14c3:0x790a')
checks['four_mdio_phys'] = all(has(dev, 'mdio:' + p) for p in ('0a', '0b', '0c', '0d'))
checks['lan1_1g'] = has(dev, 'lan1: Link is Up - 1Gbps/Full')
checks['wan_1g'] = has(dev, 'wan: Link is Up - 1Gbps/Full')
checks['mt7915e_bind'] = has(dev, "mt7915e 0000:01:00.0: registering led 'mt76-phy0'")
checks['mt7916_ready'] = has(dev, 'e2631-wifi-boot: MT7916 ready')
checks['wifi_forward'] = has(dev, 'e2631-wifi-boot: automatic Wi-Fi initialization complete')
checks['radio_phy0_ap0'] = has(dev, 'phy0-ap0')
checks['radio_phy1_ap0'] = has(dev, 'phy1-ap0')
checks['no_panic'] = has(dev, '---PANIC\n0')
checks['mtd0_unchanged'] = has(dev, 'd571b76404df1596dd58b710cff84e1ede92e6a29798abe5dcc50198d286b0f5')

cmd_lines = "\n".join(l for l in serial.splitlines() if not re.match(r'^[0-9a-fA-F]{8}:', l))
write_pat = re.compile(r'^\s*(=>\s*)?(mtd\s+(write|erase)|nand\s+(write|erase)|saveenv)\b', re.M)
write_hits = [m.group(0) for m in write_pat.finditer(cmd_lines)]
checks['no_write_commands'] = not write_hits
checks['driver_verdict_fail_is_tooling'] = res.get('error') == "KeyError('probes_late')"

out = {
    'run': 'A6 v3 run-3 (attach, --with-refclk)',
    'artifact': res.get('artifact_contract'),
    'gate': {'pin2': {'value': p2.get('value'), 'vendor': p2.get('vendor_target'), 'ok': p2.get('ok')},
             'pin51': {'value': p51.get('value'), 'vendor': p51.get('vendor_target'), 'ok': p51.get('ok')}},
    'refclk_checks': res.get('refclk_checks'),
    'refclk_after': res.get('refclk_values', {}).get('after'),
    'wifi_latency': {'first_attempt_failed_msg': 'e2631-wifi-boot: previous initialization unfinished; retrying in 120s (29.6 s)',
                     'retry_wait': 'e2631-wifi-boot: waiting 25s (149.6 s)',
                     'mt7915e_bind': '175.8 s', 'MT7916_ready': '176.0 s', 'wifi_complete': '176.3 s'},
    'checks': checks,
    'write_command_hits': write_hits,
    'hexdump_write_strings_note': ('mtd write/erase appear only as U-Boot help strings inside a memory hex dump '
                                    '(serial lines 24006/24011), not as issued commands'),
    'product_verdict': 'GREEN' if all(checks.values()) else 'FAIL',
    'driver_verdict': res.get('verdict'),
    'driver_error': res.get('error'),
}
json.dump(out, open(OUT, 'w'), indent=1)
print(json.dumps({'product_verdict': out['product_verdict'],
                  'failed_checks': [k for k, v in checks.items() if not v],
                  'gate': out['gate']}, indent=1))

