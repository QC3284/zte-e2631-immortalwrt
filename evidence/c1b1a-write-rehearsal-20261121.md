# C1b-1a：写通道 dress rehearsal（run-1 写路径 + run-2 反向 go vendor 控制台）

- 日期：2026-11-21（CST）
- 负责人：verify-docs（设备会话执行）；Lead 协调；用户批准 scratch 块写入与两次 run 的启动方式
- 结论：**GREEN**。主写通道（我们 U-Boot 的 loadx + mtd write/read/cmp + mtd erase）在真机验证通过；反向 go 后能进入 vendor U-Boot 控制台并 reset 回 stock 链；mtd0 未被触碰，scratch 块擦回 0xFF。C1b-1 正式写 mtd0 仍 gated。

## 0. 结论摘要

| 门禁项 | 结果 | 证据 |
|---|---|---|
| loadx 128 B 块收包 + md.b 校验 | 通过（131,072 B / 1024 块 / 15.4 s） | run-1 `loadx_128`、`loadx_128_md` |
| loadx 1 KiB 块收包 + md.b 校验 | 通过（131,072 B / 128 块 / 14.1 s；U-Boot loadx 两种块长都接受） | run-1 `loadx_1024`、`loadx_1024_md` |
| mtd write 到未用区 0x7F00000 | 通过（64 页 / 131,072 B；"Writing 131072 byte(s) (64 page(s)) at offset 0x07f00000"） | run-1 `mtd_write`、串口选段 |
| mtd read 回读 + 逐字节比较 | 通过（md.b 0 差异；cmp "Total of 32768 word(s) were the same"） | run-1 `scratch_readback_md`、串口选段 |
| mtd erase + 回读全 0xFF | 通过（sha256 b5a41c37… = 131,072 B 全 0xFF） | run-1 `scratch_erase_md` |
| reverse go 装入 vendor 载荷 + md 校验 | 通过（426,048 B / 3,329 块 / 44.4 s、44.7 s；两次 md.b 全量一致） | run-1/run-2 `vendor_loadx`、`vendor_md` |
| reverse go 后 vendor 控制台 | 通过（run-2：Press-1 → `1` → 密码 → `=>` → version 显示 U-Boot 2013.04） | run-2 `vendor_console.stock_banner=true`、串口选段 |
| vendor reset → stock Linux | 通过（`resetting ...` → Boot SPI NAND → secondboot → vendor U-Boot → cspboot → VFS Mounted root） | run-2 串口选段、`stock_monitor` |
| 零越界写入 | 通过（run-1 仅 1 次 mtd write + 1 次 mtd erase，均在 0x7F00000..0x7F20000；run-2 零写） | 两次 run `write_audit` |
| mtd0 前后不变 | 通过（887a7f6c…，两次 run 后都复核） | run-1 手动 postcheck、run-2 `mtd0_unchanged=true` |
| 设备健康 | 通过（ImmortalWrt v1.10.0 / 6.18.60 / PANICS=0 / MT7916=1 / WiFi up） | run-2 health、20:31 复核 |

## 1. 目的与门禁来源

Lead 2026-11-21 决定：task-54 静态 RE 未找到 vendor `nand write.uboot` 的派发代码（help 文本存在但无可用证据），因此 C1b-1 的主写通道改为我们自己的 U-Boot 控制台：`loadx` 收 mtd0 映像 → `mtd write spi-nand0 <ram> 0x20000 0xA0000` → `mtd read` + `cmp`（与刷后回滚同一通道）。SPI 控制器写操作从未在真机演练，因此 C1b-1a 必须先做：

1. `loadx` 行为测试（128 B 与 1 KiB 块）；
2. 未用区 `0x7F00000` 一个 `0x20000` 块的 `mtd write` / `mtd read` / 逐字节比较 / `mtd erase` + 回读 0xFF；
3. `loadx vendor-uboot-ram.bin` → `go 0x47F00000` → vendor 控制台出现 → vendor `reset` → stock Linux → health。

约束：scratch 块是唯一允许写入的 flash 区域；mtd0 只读；用户批准本次 scratch 写；C1b-1 正式写仍 gated。

## 2. 输入与产物

| 项 | 值 |
|---|---|
| 我们的 U-Boot | `u-boot.bin` 448,112 B sha256 `010379fde3496fdcbbe835c249cff2bd79234f946918266721e098dd64479f75`，banner `U-Boot 2027.01-rc2-g2797f3dd3860`，CONFIG_TEXT_BASE=0x47F00000（task-55 build，run 44898534408） |
| vendor RAM 载荷 | `evidence/p2-oob/vendor-uboot-ram.bin` 426,048 B sha256 `a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30`（task-54 固定救援输入） |
| scratch 测试数据 | 0x20000 B 确定性非 0xFF 图案，sha256 `2809cb8a646aa7d5821261d1b4d00faf3e9da95d268074682785562157ce9b9e` |
| scratch 范围 | `0x7F00000..0x7F20000`（1 个 128 KiB 块；在所有分区之外，分区末 0x6E00000、芯片 0x8000000） |
| 目标设备 | 192.168.1.1，ImmortalWrt v1.10.0 / kernel 6.18.60，mtd0 sha256 `887a7f6c…` |

## 3. run-1：写通道（冷启动，2026-11-21 19:44:26–20:03:26）

流程：用户冷启动 → vendor 控制台 → xmodem u-boot.bin 到 0x47F00000 → `md.b` 三处抽查 → `go` → 我们的 U-Boot 控制台（空格停 autoboot）→ loadx/ mtd write/ read/ cmp/ erase → loadx vendor 载荷 → `go 0x47F00000`。

| 时间 | 事件 |
|---|---|
| 19:46:59 | 冷启动，Press-1，vendor 密码 attempt 1 → autoboot |
| 19:47:42–43 | `md.b` uboot-start/banner/tail 3/3 OK；停 autoboot 得 `=>` |
| 19:48:02 | `loadx 0x42000000` 128 B 块：131,072 B / 1024 块 / 15.4 s |
| 19:48:57 | `loadx-128-data` md.b 一致（sha 2809cb8a…） |
| 19:49:12 | `loadx 0x42000000` 1 KiB 块：131,072 B / 128 块 / 14.1 s |
| 19:50:08 | `loadx-1024-data` md.b 一致 |
| 19:50:23–19:51:19 | 重新 loadx 128 B（15.3 s）并 md.b 一致 |
| 19:52:15 | `mtd read spi-nand0 0x43000000 0x7f00000 0x20000` 回读 md.b 一致 |
| 19:53:10 | `mtd erase` 后回读全 0xFF（sha b5a41c37…） |
| 19:53:55–19:56:56 | `loadx 0x47f00000` vendor 载荷 426,048 B / 3,329 块 / 44.4 s，md.b 全量一致 |
| 19:57:26 | `go 0x47F00000` → vendor U-Boot 2013.04 banner 出现 |
| 19:57:49 | 空格未能停住 vendor 启动（原因见 §4），cspboot 自动启动 stock Linux |
| 20:03:26 | driver 超时/收尾，capture 恢复；VERDICT FAIL（仅子门禁与驱动记账问题） |

run-1 关键数据：`mtd_write.tail` = `Writing 131072 byte(s) (64 page(s)) at offset 0x07f00000`；回读 md 与预期 sha 相同；`cmp 0x42000000 0x43000000 0x20000` 输出 `Total of 32768 word(s) were the same`；erase 后回读 sha `b5a41c3758763bbec72769fab4a2533bf2db0b6312d93d25a695f9e4b9e02260`（131,072 B 全 0xFF）。

run-1 会话后手动只读复核（20:05 左右）：health `VERSION=ImmortalWrt v1.10.0`、`UPTIME=474`、`MTD0=bootloader`、`PANICS=0`、`MT7916=1`、`WIFIBOOT=53.78 s`；SSH `sha256sum /dev/mtd0` 仍为 `887a7f6c…`；kernel 6.18.60。结论：写通道步骤全部成功，mtd0 未动，scratch 块已擦回 0xFF。

## 4. 子门禁失败根因（run-1）与修正

run-1 在 reverse go 后只看到 vendor banner，没有拿到 vendor `=>`。串口字节显示：从 RAM 启动的 vendor U-Boot 不使用 `Hit any key to stop autoboot`；它打印 `*** Press 1 means entering boot mode***` 并做 3 s 倒计时（2→1→0，只有 `1` 能进 boot mode，之后要 vendor 密码），空格被忽略，随后 cspboot 自动启动 stock kernel。

修正：reverse go 后直接复用 vendor 控制台入口流程（等 `Press 1 means entering boot mode` → 发 `1` → 输密码 → `Hit any key to stop autoboot` 空格 → `=>` → `version`）。run-2 用该流程成功。

## 5. run-2：反向 go vendor 控制台（SSH reboot，2026-11-21 20:23:37–20:29:40）

启动方式：用户/Lead 选择 SSH reboot（warm boot；本门禁不涉及冷启动采样）。driver 先启动 serial hub，再 SSH `sync; (sleep 1; reboot -f) &`，串口抓到 Press-1 后用同一套 vendor 入口流程进入控制台。

| 时间 | 事件 |
|---|---|
| 20:23:40 | capture 暂停、hub 启动；SSH reboot rc=0 |
| 20:23:43 | Press-1 捕获 → `1` → vendor 密码 attempt 1 → autoboot |
| 20:24:26 | xmodem u-boot.bin 438 块 / 448,112 B / 42.0 s；md.b 3/3 OK；停 autoboot 得 `=>` |
| 20:25:15 | `loadx 0x47f00000` vendor 载荷 426,048 B / 3,329 块 / 44.7 s |
| 20:28:15 | md.b 全量一致；`go 0x47F00000` |
| 20:28:16 | Press-1 捕获 → `1` → vendor 密码 → `Hit 1 to upgrade software version` / `Hit any key to stop autoboot: 3` → `=>` |
| 20:28:16 | `=> version` 输出 `U-Boot 2013.04 (Aug 28 2023 - 18:40:22)` |
| 20:28:16 | `=> reset` → `resetting ...` |
| 20:28:xx | `Boot SPI NAND` → `start read bootheader` → `start read secondboot` → `U-Boot 2013.04` → cspboot → `VFS: Mounted root` |
| 20:28:52 | capture 恢复；20:29:40 VERDICT GREEN |

run-2 判据数据：`vendor_console={ok:true, autoboot_stopped:true, stock_banner:true}`；`vendor_prompt_ok=true`、`vendor_version_ok=true`、`vendor_reset_sent=true`；串口选段含 `=> version` 的 U-Boot 2013.04 banner、`=> reset`、`resetting ...` 与后续 stock 启动链；`health`：`VERSION=ImmortalWrt v1.10.0`、`PANICS=0`、`UPTIME=36`（该快照时 WiFi 仍在 `waiting 25s`，MT7916=0 属正常；20:31 复核 UPTIME=204、MT7916=1、WIFIBOOT 53.74 s）；`post_uptime=74`、`post_version=ImmortalWrt v1.10.0`、`post_kernel=6.18.60`、`post_mtd0_sha256=887a7f6c…`；`write_audit` 零写；`capture_after.ok=true`。

## 6. 写审计

| run | mtd write | mtd erase | 越界写 | mtd0 前后 |
|---|---|---|---|---|
| run-1 | 1 次：`mtd write spi-nand0 0x42000000 0x7f00000 0x20000` | 1 次：`mtd erase spi-nand0 0x7f00000 0x20000` | 无 | 887a7f6c… → 887a7f6c… |
| run-2 | 0 | 0 | 无 | 887a7f6c… → 887a7f6c… |

驱动在发送前按白名单拒绝非 scratch 的 mtd write/erase、nand/saveenv/upgrade/tftp/bootm；run-1 串口全文无其他写/擦命令。

## 7. 驱动缺陷与经验（非产品缺陷）

1. run-1 `monitor_stock` 只看新到字节，而开机日志已被前一步读取消费，导致 stock 标记全 false、health 未执行、mtd0_unchanged 假 false。run-2 改为扫描 serial 日志文件。
2. run-1 `write_audit` 的 forbidden 正则匹配 `nand` 时误中 `spi-nand0`，把合法 mtd 命令记成 forbidden；run-2 改为显式 token 判断。
3. run-2 `monitor_stock_file` 扫描整个日志（含会话开始时的 SSH reboot 启动段），单靠标记不能证明 reset 后启动；本证据以串口 `resetting ...` 后紧接的 Boot SPI NAND/secondboot/VFS 段 + `post_uptime=74` 作为 reset 后 stock 启动的直接证据。
4. run-1 完整串口日志 `console-transcript.txt` 5.2 MB 保留在主机 `/home/qc233/zte/e2631-p3/c1b1a-rehearsal/run-1/`；本目录只放选段。

## 8. 对 C1b-1 的结论与输入

- 写通道 PROVEN：`loadx`（128 B 与 1 KiB 两种块长均可）+ `mtd write spi-nand0 <ram> <off> <len>` + `mtd read`/`cmp` + `mtd erase` 在真机全部工作，scratch 块写后回读逐字节一致、擦后回读全 0xFF，mtd0 未受影响。
- C1b-1 主写通道确定为我们的 U-Boot 控制台（vendor `nand write.uboot` 不作为主路径）。
- C1b-1 目标：写 mtd0 `0x20000..0xC0000`（0xA0000）为新 `e2631-uboot-mtd0.bin`（655,360 B sha256 `baf28b6da4d6ca1b356389951b9d49765382b35dd382bc81c8a0a589c09464dd`）；写后 mtd0 预期 sha256 `3c8a8c5b0f9db1953628919d650ff7af6d24e07c48e9a31d5b228881a9f36ffb`。env 块 `0xC0000` 与 secondboot 区 `<0x20000` 不在写入范围。
- C1b-1 仍 gated：需要 Lead 最终 go + 用户在场；本次 1a 不写 mtd0。

## 9. 附件

| 文件 | 内容 |
|---|---|
| [run-1/session-results.json](c1b1a-write-rehearsal/run-1/session-results.json) | run-1 全部判据数据（loadx/mtd write/read/cmp/erase/vendor/go/health） |
| [run-1/serial-scratch-excerpt.txt](c1b1a-write-rehearsal/run-1/serial-scratch-excerpt.txt) | run-1 串口选段：mtd write/read/cmp、mtd erase、reverse go |
| [run-1/preflight.json](c1b1a-write-rehearsal/run-1/preflight.json) / [run-1/session-driver.txt](c1b1a-write-rehearsal/run-1/session-driver.txt) / [run-1/driver.stdout.txt](c1b1a-write-rehearsal/run-1/driver.stdout.txt) | run-1 预检、驱动日志、stdout |
| [run-2/session-results.json](c1b1a-write-rehearsal/run-2/session-results.json) | run-2 全部判据数据（SSH reboot/vendor console/reset/stock/health/mtd0） |
| [run-2/serial-vendor-console-excerpt.txt](c1b1a-write-rehearsal/run-2/serial-vendor-console-excerpt.txt) | run-2 串口选段：Press-1 → 密码 → `=> version` → `=> reset` → `resetting ...` → stock 启动 → VFS |
| [run-2/health.txt](c1b1a-write-rehearsal/run-2/health.txt) / [run-2/preflight.json](c1b1a-write-rehearsal/run-2/preflight.json) / [run-2/session-driver.txt](c1b1a-write-rehearsal/run-2/session-driver.txt) / [run-2/driver.stdout.txt](c1b1a-write-rehearsal/run-2/driver.stdout.txt) | run-2 health、预检、驱动日志、stdout |
| [tools/c1b1a_rehearsal.py](c1b1a-write-rehearsal/tools/c1b1a_rehearsal.py) / [tools/c1b1a2_vendor_console.py](c1b1a-write-rehearsal/tools/c1b1a2_vendor_console.py) | 两个 run 的驱动源码 |
| [SHA256SUMS.txt](c1b1a-write-rehearsal/SHA256SUMS.txt) | 附件清单 sha256 |

## 10. 复现命令（主机侧）

```text
c1b1a_rehearsal.py --artifact <run>/u-boot.bin --sha256 010379fd... \
  --banner-token "U-Boot 2027.01-rc2-g2797f3dd3860" --artifact-config <run>/.config
c1b1a2_vendor_console.py --start-mode ssh-reboot --artifact <run>/u-boot.bin \
  --artifact-config <run>/.config
```

前置：capture 链暂停、串口单读、`/home/qc233/zte/e2631-p3` 工具在位、设备直连路由；run-1 需要用户冷启动并批准 scratch 块写；run-2 由主机 SSH reboot 触发（read-only）。