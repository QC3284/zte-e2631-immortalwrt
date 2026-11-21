# P2-B1 vendor U-Boot 环境变量定制：真机会话（2026-11-21）

> 结论：**GREEN**。用户批准的唯一一次 `saveenv` 已执行，on-flash env 块与离线预测**逐字节一致**；
> 除此之外 mtd0 的其他字节零变化（env 块外 pre/post 哈希与基线一致），设备未刷写、bootcmd 未改，
> 设备正常启动并保持健康。

## 0. 结果摘要

| 项目 | 结果 |
|---|---|
| verdict | **GREEN**（session-results.json 内 verdict=GREEN） |
| 写操作 | 恰好 1 次 `saveenv`；无其他 flash 写/擦 |
| env CRC | `0xF95A816E`（存储值 = 重算值） |
| env 块 sha256 | `6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893` |
| full mtd0 sha256 | `887a7f6c9b407abc734eb9a76f08733a691441f91987369e8626deb8faf0fa9f` |
| 与基线 mtd0 差异 | 462 字节，全部在 env 块 `0xC0000..0xC02AA` 内（`diff_outside_env=0`） |
| env 条目 | 26 条（基线 22 条逐字节不变 + 4 条新旁路变量），字母序存储 |
| 回读比较 | env 块与预测 **byte-identical**；full mtd0 sha 与预测一致；env 块外 pre/post 哈希与基线一致 |
| 设备状态 | ImmortalWrt v1.10.0（r0-86cddb7）正常运行；PANICS=0、MT7916=1、WiFi 自动初始化 54.16 s |
| 设备刷写 | 无（本轮只写 env 块；C1 刷 U-Boot 到 mtd0 仍待用户批准） |

## 1. 批准范围与依据

- 用户批准（经 Lead，2026-11-21）的写范围：只允许一次 `saveenv`，持久化 4 个旁路变量
  `e2631_pocload` / `e2631_pocgo` / `e2631_netboot` / `e2631_flashboot`；
  `bootcmd`、`bootargs`、`memsize`、`versioninfo`、`bootdelay` 及其余条目**逐字节不变**（bootdelay 保持 3）；
  除这一次 env 块写以外全部只读。
- 设计依据：`evidence/b1-env-design-20261121.md`（task-46）+ 2026-11-21 的 bootdelay 裁定（维持 3）
  + `evidence/b1-env-current-20261121.txt`（会话前 22 条目、CRC 0xAFFCEC3E）。
- 工具：`tools/e2631-env.mjs`、`tools/lib/mtd0.mjs`（`ENV_OFF=0xC0000`、`ENV_BLOCK_SIZE=0x20000`）；
  基线 dump：`/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin`（sha256 `de4ea5bd...`，与本机
  `e2631-p2/dump2/mtd0-before.bin` 相同）。
- 会话分两段：第一段 16:36–16:38 在 `saveenv` 之前按安全纪律**主动中止（零写入）**；第二段获 Lead 批准后
  用 attach-resume 在同一个 vendor 控制台完成唯一一次写。两段都留有串口与驱动日志。

## 2. 会话前基线事实

- 设备：vendor U-Boot 2013.04（Aug 28 2023）控制台；SPI-NAND FORESEE 128 MiB（READID 0xCD/0x71，见
  P2-P1 证据）；Linux 侧 ImmortalWrt v1.10.0 r0-86cddb7。
- mtd0 全片 sha256：`de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f`。
- env 块（`0xC0000..0xE0000`）sha256：`6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`；
  CRC `0xAFFCEC3E`，22 条目。
- **关键事实**：用 `tools/e2631-env.mjs dump` 读基线 env 块，条目在 flash 中是**字母序**存储的
  （baudrate, bootcmd, bootdelay, bootfile, bootloaderfile, console, ethact, ethaddr, ...）。
  这决定了新增条目不会追加在末尾，而是按字母序插入。

## 3. 会话一：中止（saveenv 之前，零写入）

| 时间（CST） | 事件 |
|---|---|
| 16:36:30 | preflight OK（8 项检查，预测 append-order 变体） |
| 16:36:42 | 驱动打印 READY，等待用户冷启动 |
| 16:38:29 | 用户断电/上电；捕获到冷启动 Press-1 提示，进入 vendor 控制台 |
| 16:38:31 | help 预检（setenv/saveenv 存在）、基线 printenv 22 条与证据一致、4 条 setenv 逐条读回 OK |
| 16:38:31 | 全量 printenv 得 26 条，但驱动的“顺序 = 基线顺序 + 4 条追加”断言失败，**主动中止** |
| — | `saveenv` 从未发出 → 零 flash 写入 |
| 16:38:38 | 捕获链恢复；驱动的 finally 段卡在主机路由陷阱（见 §7），session-results.json 未写出，进程被 kill |
| — | 设备停在 vendor U-Boot `=>` 提示符；4 条变量只在 RAM 中 |

根因：vendor env 在 flash 中按字母序存储，4 条新变量实际插入在 `console` 与 `ethact` 之间，
而不是追加在末尾。中止时观测到的 printenv 顺序为：

`baudrate, bootcmd, bootdelay, bootfile, bootloaderfile, console, e2631_flashboot, e2631_netboot, e2631_pocgo, e2631_pocload, ethact, ...`

证据：`aborted-run1-serial.txt` 第 159/200 行（Environment size 585 -> 733/131068），
`aborted-run1-session-driver.txt`（`SESSION ERROR: combined env does not match the target; refusing to saveenv`），
`aborted-run1-prediction.json`。

### 3.1 预测修正（取代 append-order 常数）

按“基线 22 条 + 4 条新变量、整体字母序”重建后：

| 预测项 | 修正值 |
|---|---|
| env CRC | `0xF95A816E`（原 append-order 变体为 `0xC41396BA`，作废） |
| env 块 sha256 | `6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893` |
| full mtd0 sha256 | `887a7f6c9b407abc734eb9a76f08733a691441f91987369e8626deb8faf0fa9f` |
| 与基线差异 | 462 字节，全部在 env 块内（插入导致后续条目整体位移） |

用 `node tools/e2631-env.mjs verify --dump target-mtd0.bin` 验证：存储 CRC = 重算 CRC = `0xf95a816e`，26 条目。
该修正值已报 Lead 并获批准 attach-resume（2026-11-21 16:45 CST）。

## 4. 会话二：attach-resume（唯一一次写）

| 时间（CST） | 事件 |
|---|---|
| 16:47:02 | 暂停捕获链（tty 空闲）、serial hub 启动、附着到 vendor 控制台并读回 version banner |
| 16:47:03 | 全量 printenv：26 条、字母序、bootdelay=3、bootcmd/versioninfo 未变 → PRE-ENTRIES-OK |
| 16:47:03 | 动态重建预测（按观测顺序）→ PREDICTION-OK（CRC/sha/差异与 §3.1 完全一致） |
| 16:47:03 | 发送唯一一次 `saveenv` → SAVEENV-OK |
| 16:47:03 | 全量 printenv 复核 26 条精确 → POST-SAVEENV-OK |
| 16:47:05 | 发送 `reset`，设备重启（vendor reset 有效）→ RESET-REBOOTED |
| 16:47:12 | 捕获到 Linux 启动标记 → LINUX-BOOTING |
| 16:47:18 | 停止 hub、恢复串口捕获链（supervisor/bootwatch/tty 三进程均在位） |
| 16:57 | 回读 + health 复核完成（见 §5；首次回读在路由陷阱下失败，直连恢复后重试全绿） |

`saveenv` 串口原文关键行（`resume-serial.txt` 第 35–39 行）：

```
=> saveenv
Saving Environment to NAND...
Erasing 0xc0000 - 0xe0000:<nand_erase_skip_bad_,609>!mtdpart=0x1,start=0x0,mtdpartoffset=0xc0000,mtdPartsize=0x40000,length=0x20000
Writing to Nand:<nand_write_skip_bad_,504>!mtdpart=0x1,offset=0x0,mtdpartoffset=0xc0000,mtdPartsize=0x40000,length=0x20000
```

擦除/写入窗口明确限定在 `0xC0000..0xE0000`、长度 `0x20000`，即 env 块本身。

## 5. 回读验收（只读 SSH）

首次回读在 16:47:49 失败：设备已启动但主机 `192.168.1.1` 路由经家用网 `192.168.5.1`（路由陷阱），SSH 被拒；
直连 USB 网卡（`enp0s20u1u4u2c2`, 192.168.1.191）恢复后于 16:57 重试。

回读命令（设备无 `od`/`base64`；`dd bs=1` 过慢，改用块读 + `hexdump -v -C` 本地解析）：

```
sha256sum /dev/mtd0
dd if=/dev/mtd0 bs=4096 skip=0 count=192 2>/dev/null | sha256sum   # 0x0..0xC0000
dd if=/dev/mtd0 bs=4096 skip=224 count=32 2>/dev/null | sha256sum  # 0xE0000..0x100000
dd if=/dev/mtd0 bs=131072 skip=6 count=1 2>/dev/null | hexdump -v -C
```

| 检查 | 结果 |
|---|---|
| full mtd0 sha256 | `887a7f6c...` = 预测值 |
| env 块 sha256 | `6e2c01da...` = 预测值，byte-identical |
| env CRC | `0xF95A816E` = 预测值 = 重算值 |
| env 条目 | 26 条，字母序；22 条旧值逐字节一致，4 条新值精确 |
| env 块外 pre 哈希 | `9e647df44854c1bfa905616476ada0b3ba4452f3c1f8225aa2daee4db0a354bf` = 基线 |
| env 块外 post 哈希 | `b5a41c3758763bbec72769fab4a2533bf2db0b6312d93d25a695f9e4b9e02260` = 基线 |
| 总差异 | 462 字节，全部在 `0xC0000..0xC02AA`；块外 0 字节 |

health（直连路由，`health-retry.txt`）：ping 3/3、`VERSION=ImmortalWrt v1.10.0`、`UPTIME=623`、
`MTD0=mtd0: 00100000 00020000 "bootloader"`、`PANICS=0`、`MT7916=1`、
`e2631-wifi-boot: automatic Wi-Fi initialization complete`（54.158989 s）。

回读明细与产物：`readback-retry.json`、`actual-env-block.bin`（131072 B，sha256 与预测一致）。

## 6. 写范围审计

- **命令层**：整个会话只发送了 1 条 `saveenv`；白名单只允许 4 条 `setenv` + read-only 命令，
  `nand write/erase`、`mtd write/erase`、`saveenv` 以外的写命令、tftp/go/run/upgrade 均被驱动在发送前拒绝。
- **flash 层**：`saveenv` 的擦除/写入窗口 = `0xC0000..0xE0000`（env 块）；mtd0 全片哈希从基线
  `de4ea5bd...` 变为 `887a7f6c...`，但变化字节总数 462、全部落在 env 块内，块外 pre/post 哈希与基线一致。
- **env 内容**：22 条旧条目逐字节不变；4 条新条目 =
  `e2631_pocload=tftp 0x43000000 u-boot.bin`、`e2631_pocgo=go 0x43000000`、
  `e2631_netboot=tftp 0x42000000 e2631-netboot.uImage`、`e2631_flashboot=reset`；
  `bootcmd`、`bootargs`、`memsize`、`versioninfo`、`bootdelay=3` 均未变。
- **启动路径**：saveenv 后设备经 vendor reset 正常冷启动到 Linux，vendor `zteboot_do_settings` 等启动逻辑未受影响
  （4 条变量只是旁路命令文本，没有被 bootcmd 引用）。

## 7. 工具缺陷与修复记录（供 C1/A4 复用）

第一段会话暴露、已在 `b1_resume.py` 中修掉的问题：

1. **顺序假设**：原驱动要求 printenv 顺序 = 基线顺序 + 追加；实际 vendor env 字母序存储。
   修复：改为 dict 相等（26 条值精确）+ 只断言“顺序是字母序”，并保存观测顺序。
2. **预测来源**：不再使用静态 append-order 常数；pre-saveenv 后用观测顺序现场调用
   `tools/e2631-env.mjs build` 生成预测块/CRC/full sha 再比较。
3. **finally 卡死**：原驱动在路由陷阱下 `nmcli device connect` 后长时间无超时，session-results 未落盘；
   修复：finally 每步独立 try/except、先写 results、路由修复失败不阻塞后续 health/读回重试。
4. **设备工具缺失**：无 `od`/`base64`、`dd bs=1` 太慢；回读改用 `dd bs=4096 | sha256sum` +
   `hexdump -v -C`（本地按偏移解析十六进制列，剔除 ASCII 列）。
5. **回读时序**：设备刚启动时主机可能仍走家用网路由；先确认 `ip route get 192.168.1.1` 是直连
   （结果中无 `via`）再 SSH，命中路由陷阱时重试而不是直接判 FAIL。

第一段驱动原件（`b1_env_session.py`）与第二段驱动（`b1_resume.py`）都作为附件保留，便于审计。

## 8. 当前设备状态与后续

- 设备未刷写，仍运行 ImmortalWrt v1.10.0（r0-86cddb7）；env 已持久化 4 条旁路变量，bootcmd 未改；
  mtd0 当前 sha256 `887a7f6c...`。
- 串口捕获链已恢复：supervisor 226285 / bootwatch 226320 / tty holder 226291；
  设备在正常启动后的 Linux 状态，无 panic。
- 下一步 C1（把我们自己的 U-Boot 写入 mtd0）继续 gated：等 Lead 向用户提交刷写计划 + 回滚路径并获得明确批准。
  本轮不涉及 C1。

## 9. 附件清单（`evidence/b1-env-session/`）

| 文件 | 说明 |
|---|---|
| `resume-session-results.json` | 第二段会话完整结果（verdict GREEN；含 saveenv 原文、回读、health、capture 状态） |
| `readback-retry.json` | env 块回读明细（哈希、CRC、26 条目、顺序、块外哈希） |
| `target-env-block.bin` | 离线预测 env 块（sha256 `6e2c01da...`） |
| `actual-env-block.bin` | 设备回读的 env 块（sha256 相同，逐字节一致） |
| `observed-env.txt` | 用于生成预测的 26 条目文本（字母序） |
| `resume-serial.txt` / `resume-console-transcript.txt` | 第二段串口原始日志/控制台转录 |
| `resume-session-driver.txt` / `resume-driver.stdout.txt` | 第二段驱动日志/标准输出 |
| `aborted-run1-serial.txt` / `aborted-run1-session-driver.txt` / `aborted-run1-prediction.json` | 第一段中止会话（零写入）审计材料 |
| `health-first.txt` / `health-retry.txt` | 首次（路由陷阱前）与直连重试的 health 输出 |
| `preflight-resume.json` | attach-resume 前 preflight |
| `tool-b1_resume.py` / `tool-b1_env_session.py` | 第二段驱动 / 第一段驱动原件 |
| `SHA256SUMS.txt` | 上述附件 sha256 清单 |

基线参考（仓库既有）：`evidence/b1-env-current-20261121.txt`、`evidence/b1-env-design-20261121.md`。