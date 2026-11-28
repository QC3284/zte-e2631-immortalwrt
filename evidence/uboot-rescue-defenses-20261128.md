# 救援自检防御：patch 0040 / 0041（task-94）

日期：2026-11-28
状态：两个补丁已进 kit（41 patches）；构建统一由 task-92 的 uboot-build 重跑，本机不交叉编译。

## 0. 结论

- E4 v2.1 Phase A run-1 的三个异常——`/backup` 五个分区的 `X-E2631-SHA256` 与 body 不符、22 MB 合法固件包的 digest 不符（`ccf10a41…` vs `66805b26…`）、第 6 次上传后 `/status` 渲染 data abort——在**新救援进程**里无法复现：verify-docs run-2 零写入重测，backup header sha == body sha、532 B 与 64 KiB/1 MiB/4 MiB/8 MiB/16 MiB/22,020,628 B 的 digest 全部精确、合法包 validate 通过、连续 6 次 `/status` 无 abort。
- 静态分析把 abort 定位到 `/status` 渲染的 `rescue_fmt() -> vsnprintf()`：输出游标槽里是 `0xe28d005c`，正是 36 个 `rescue_fmt` 调用点计算 `&p` 的指令字（`add r0, sp, #92`）；`r7 = 0x1e5ff289` 是当时正在格式化的 bootloader 区 CRC。`rescue_handle_get` 帧布局：`p@sp+0x5c`、`left@sp+0x7c`、`text@sp+0x30`、`body[1024]@sp+0xc0..sp+0x4c0`（frame 1216 B）。
- 设备给出的 digest 不是已交付字节的确定性函数：23 种数据变换（丢头尾/字序/反转/chunk 重排/拼接等）与 finalization 变体（长度字段位数/字节序/零值）都不匹配；`rescue_fmt` 的边界逻辑本身正确，`p` 槽只有初始化（`0x47f07510`）与 `rescue_fmt` 自身会写，因此仍存在**尚未定位的野写来源**。
- 0040/0041 的定位是**防御**：把“静默坏 digest / 野指针写”变成响亮停止；不改任何 MTD 写路径、不改正常启动与正常请求行为。

## 1. Phase A 现场（run-1）

| 项 | 设备 `X-E2631-SHA256` | body 实际 sha256 |
|---|---|---|
| bootloader | `c6053fb6…` | `23395533…` |
| tag | `9b12973d…` | `e2bba333…` |
| wifi | `1bec50bd…` | `a7b72db9…` |
| usercfg | `015447a0…` | `0d4e5a76…` |
| defcfg | `1587a172…` | `360bf435…` |

- 五个 header 的 `X-E2631-CRC32` 与 body CRC 一致（如 bootloader `0x1e5ff289`），说明 CRC 路径与数据正确；只有 SHA-256 错。
- firmware：设备打印 `received 22020628 firmware bytes, sha256 ccf10a41…`，host/两次复测均为 `66805b26…`；包内层 CRC 校验通过（`crc32=0x496cca28`），说明 staging 字节正确。
- abort 寄存器（run-1）：`pc 0x4ffd1098` / reloc `0x47f34098`（vsnprintf 内部 `strblo r3,[r6]`）、`lr 0x4ffa39cc` / reloc `0x47f069cc`（`rescue_fmt+0x30`，vsnprintf 返回点）、`r0=r6=0xe28d005c`、`r7=0x1e5ff289`、`r8=0xe28d0efb`。
- 帧/布局核对：image base `0x4ffa0000`（reloc 偏移 `0x80a0000`），heap/stack top `0x4fb80000`，abort SP `0x4fb7bc28`，栈深约 17,368 B（远低于 4 MiB 上限），staging `0x46100000..0x47d00000` 与栈/堆不重叠——排除栈溢出与 staging 覆盖。

## 2. 复现尝试（run-2，零写入）

- 同 t85 镜像（banner `g49f13e0cbe40`、`u-boot.bin` sha256 `481368a4…`、mtd0 段 crc32 `0x64c4e55d`）新救援进程：Probe 1 两次 `/backup?part=bootloader` 的 header sha 都等于 body sha `23395533…`；Probe 2 的 532 B 与尺寸扫描全部精确；合法包 validate 返回 `result=ok sha_match=ok`；6 次 `/status` 全部 200 且 body 一致。
- 结论：Phase A 的异常依赖**进程状态/请求序列**，不是确定性 SHA 数学，也不是备份数据格式问题。
- run-2 覆盖面缺口（与 verify-docs 证据一致）：没有"页面/slots/env/console 前奏"，也没有"连续 4 次合法 22 MB validate"，因此 run-1 的精确序列仍可复用于重放；完整证据见 [e4-v2-phasea-20261128.md](e4-v2-phasea-20261128.md)（kit commit `600ccb8`，CI run `46118532735`），task-94 保持 OPEN。

## 3. patch 0040：digest 防御

- `e2631rescue.c` 的每个 SHA-256 改为显式 `sha256_context`：`memset(&ctx,0,…)` → `sha256_starts` → `sha256_update` → `sha256_finish` → 再清零；`/backup` 流式摘要的 ctx 前后都清零。
- 新 `rescue_sha256(buf, len, base, maxlen, out)` 在哈希前校验 `(uintptr_t)buf == base && len <= maxlen`：失败打印两行 `e2631rescue: FATAL: refusing to hash …` 并返回 `-EINVAL`（请求 400 `cannot hash … buffer`），绝不把越界指针喂给摘要。
- 删除 `sha256_csum_wd()` 调用；CI 门禁禁止它重新出现在 `e2631rescue.c`，防止未来绕过清零/窗口校验。

## 4. patch 0041：输出游标防御

- 新增 `rescue_fmt_range(buf, size)` / `rescue_fmt_range_ok(p, left)` / `rescue_fmt_range_fail(why)`：渲染前登记目标缓冲；每次格式化前验证 `*p` 落在 `[lo, hi]` 且 `*left <= hi - *p + 1`。
- 失配时打印 `e2631rescue: FATAL: output cursor corrupted (...)` 并置 fault，后续格式全部拒绝执行——野指针不再进入 `vsnprintf()`。
- `rescue_status_text()` 末尾做帧不变量校验：`p == buf + (bufsz - left)`；不一致同样置 fault。
- `/status` 与 `/slots` 命中 fault 时返回 HTTP 500、body `result=error` + `error=output cursor corrupted`；不再用损坏的 `text`/`body` 指针构造响应。

## 5. CI 门禁

- 新增 `rescue self-check gate`：源码 grep `rescue_fmt_range`、`output cursor corrupted`、`memset(&ctx, 0, sizeof(ctx))`；`e2631rescue.c` 出现 `sha256_csum_wd` 即失败。
- 二进制文本门禁：`u-boot.bin` 必须含 `output cursor corrupted` 与 `refusing to hash`。

## 6. Pin 与交付

| 项 | 值 |
|---|---|
| patch 0040 sha256 | `d274ff0f586caefa0a7fb77caa59e0e515af02829062639129a89a537077112e` |
| patch 0041 sha256 | `cf03f0e239e286551cb24f619c8d45fc4fd27d4b74a8d7df7164b6e953c64e1b` |
| patch 总数 | 41 |
| post-am tree | `58c996fe8151ca81f45829d8fb5c41f7aea3b38b` |
| 尺寸预算 | task-90 起改为 v3 门禁：`size <= E2631_UBOOT_HARD_LIMIT - E2631_UBOOT_HEADROOM_MIN` = `653312 - 245760` = 407,552 B；防御逻辑本身 < 1 KiB |

构建统一走 `uboot-build.yml`（task-92），由 CI 重放 41 个 patch 并断言 tree；本文不记录本地构建值。

## 7. 真机复测判读（若野写复现）

- 串口出现 `FATAL: output cursor corrupted` 且 `/status` 返回 500 即证明野写仍在、但已被拦下：立即记录 serial、返回 body、请求序号（第几次上传、是否与 backup/console 并发）并停止写测试。
- 正常路径不得变化：`/backup` header sha 必须等于 body sha；`/firmware?mode=validate` 的 digest 必须等于 host sha256；`/status` 仍为 200。
- 全程零 mtd0/env/secondboot 写入；写路径验收不在本文范围。

## 8. 已知风险与边界

- 防御**不修复**野写根因；它把静默损坏变成响亮停止。定位仍建议重放 run-1 顺序（先 `/console`、`/env`，再 6 次 22 MB 上传，backup 与 status 交错），并记录是否并发连接。
- 若 `rescue_fmt` 因正常的大响应触界（不应发生：所有渲染缓冲 1 KiB/4 KiB，单行最长 < 100 B），返回 500 而非崩溃；页面侧需展示该错误。
- 本文是 task-90（E4 v3）的 known-risk 记录：v3 证据文档应引用本节，说明 v2.1 三个异常可复现性状态与防御。
## 9. 交付后注记（task-90 同批，Lead m10265）

- **上传窗口比契约宽 2 MiB（有意）**：0040 的 `rescue_sha256()` 对固件上传登记的是基址 `0x46100000` + `E2631_FW_STAGE_MAX`
  （`0x1C00000`），窗口上界 `0x47D00000`；task-89 契约 §6 写的是 `0x46100000 + 0x1BE0214`（上界 `0x47CE0214`）。
  实现比文档宽 2 MiB，仍严格低于 U-Boot 链接基址 `0x47F00000`，属安全余量；本文与 v3 证据同时记录该脚注，
  契约文档下一版按代码值收口。
- **`e2631verify` 确认没有 SHA-256 路径**：`e2631flash.c` 只用 `crc32()`（行 323/388/461/470/592），
  `e2631verify` 是只读的 RAM↔flash CRC32 比较；0030 的 env 失败转储也是 CRC32。task-90 把 CI 的 `sha256_csum_wd`
  禁令从 `e2631rescue.c` 扩到整个 `board/zte/zxhn-e2631/`（见 `uboot-build.yml` 的 rescue self-check 段），
  task-92 构建会再次断言；`make check` 侧的 e2631verify 语义验证仍在 kit 静态检查范围内。
