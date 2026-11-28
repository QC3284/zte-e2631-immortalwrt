# E4 v2.1 Phase A / task-94 复测附件

本目录是 `evidence/e4-v2-phasea-20261128.md` 的附件。

- `run-1/`：task-86 Phase A 首跑（RED）。含 127 项 probe 的 `probe.json`、`probe.log`、原始 `serial.log`、`load.json`、`preflight.json`、五份 `/backup` 响应头、`/firmware` 负向响应、console/page/status/slots/env 小响应、`crash-excerpt.txt` 与 `backup-body-sha256.txt`。不包含 7 MB 级 backup body（其 sha256 记录在 `backup-body-sha256.txt`）。
- `run-2/`：同一 t85 产物的干净复测（Lead 接受为 replay）。含 `diag-probes.json`、`diag-large-sizes.json`、`diag-sizes.json`、`diag-status-legal.json`、`exit.json`、`serial.log`、backup 头、legal validate 响应、p532 与各尺寸扫描的小响应 body、六次 `/status` body、四个复测脚本。
- `tools/e4_v2_phasea.py`：Phase A 驱动（preflight/load/probe/exit/all；零 flash 写约束）；`run-2/run_*.py` 是本次复测的临时脚本。
- `artifact-*.txt`：t85 产物 UBOOT-INFO/SHA256SUMS/.config。

核验：

```sh
cd evidence/e4-v2-phasea
sha256sum -c SHA256SUMS.txt
```

原始设备目录（未入库）：`/home/qc233/zte/e2631-p3/e2/e4-v2-phasea/{run-1,run-2}`；产物档案：`/home/qc233/zte/e2631-t5-artifacts/t85-46111271598/files/`。
