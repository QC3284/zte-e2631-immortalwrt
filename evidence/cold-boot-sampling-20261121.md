# Cold-boot sampling — r0-86cddb7 (2026-11-21)

Acceptance item 4 of the mainline-alignment plan (Plan C): consecutive cold boots
must bring up MT7916 and complete automatic Wi-Fi initialization.

## Method

- Serial capture: CH343 USB UART (/dev/ttyCH343USB0, 115200 8n1), single reader
  (capture-supervisor-002.sh) → /home/qc233/zte/e2631-serial-boot-002.log
- Session detection: serial-bootwatch.mjs (campaign-002 state) → boot-sessions-002.jsonl
- Each session = one power cycle ('Boot SPI NAND' … 'automatic Wi-Fi initialization complete')
- Success = MT7916 ready ≤ ~56 s + wifi_done, no fail_pattern / panic / oops
- Power cycles performed manually by the operator (unplug/replug), 6 consecutive

## Results

| Session | U-Boot | MT7916 ready (s) | Wi-Fi init complete (s) | Verdict |
|---|---|---|---|---|
| 1 | ✓ | 53.674 | 53.904 | SUCCESS |
| 2 | ✓ | 53.653 | 53.886 | SUCCESS |
| 3 | ✓ | 53.499 | 53.721 | SUCCESS |
| 4 | ✓ | 53.720 | 53.970 | SUCCESS |
| 5 | ✓ | 54.974 | 55.220 | SUCCESS |
| 6 | ✓ | 54.470 | 54.699 | SUCCESS |

- MT7916 ready: 53.499–54.974 s (mean ≈ 54.0 s)
- fail_pattern / panic / oops: **0**
- Serial line loss: none (all 6 sessions complete)

## Conclusion

**6/6 cold-boot success** on r0-86cddb7 (acceptance threshold: ≥ 5 consecutive).
Combined with the previous campaign on the v1.10.0 payload (11/11, see
cold-boot-sampling-20261114.md), the MT7916 cold-start hang reported against the
upstream v1.3-era firmware is not reproducible on our payloads.
