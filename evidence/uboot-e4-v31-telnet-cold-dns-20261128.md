# task-99 t92f 修复：telnet 行尾/执行槽、冷启动救援、DNS 地址（2026-11-28）

结论摘要：t92e 零写门禁 283/285，失败项与另外两处回归都定位到确定性代码缺陷，分三个 patch 修复：

- 0062：telnet 行编辑器把上一行残留字节带进新命令（`version` 后 `bdinfo` 变成 `bdinfon`）；同一会话状态里还有两个
  共享槽泄漏——`telnetd_reset_session()` 在私有 capture 缓冲安装时被调用会留下悬空的 `gd->console_out`，连接在
  draining 期间死亡会让 `draining` 永真、web console 后段 503 busy。
- 0063：RAM 链的厂商 U-Boot 已把网络参考时钟/SerDes 配好并启动 PHY 自协商，`e2631_net_refclk_init()` 无条件重编程
  把它打断，于是全新 RAM 载入后第一条 `e2631rescue` 报 `PHY startup failed (-110)` / `no usable Ethernet`。
- 0064：DNS A 记录取共享 `net_ip`；t92e 第二次救援时 `net_ip` 在同一流程里被改成 `99.117.101.0`（字节
  `63 75 65 00`），与同一行的 DHCP 服务器地址不一致。DNS 改为启动时 pin 住救援地址，日志同时打印两者，救援主循环
  发现 `net_ip` 被改会告警并恢复，作为诊断兼兜底。

## 1. t92e 现场

- artifact：run `46136469366`（head `3497032`），banner `U-Boot 2027.01-rc2-gfc5b1f0f2eeb`，61 patches。
- 设备由 patch 0034 的 flash 镜像启动，再用 `mtd read` + `go` 载入 t92e RAM 链；probe 285 项中 283 PASS。
- 失败：`telnet_version`（满序列里只有 echo，无命令输出）与 `telnet_bdinfo`（`Unknown command 'bdinfon'`）。
- 后段 quick 的 web console exec 返回 503 busy；fresh quick 通过。
- 冷救援回归：全新 RAM 载入后提示符第一条命令直接 `e2631rescue` 报
  `ethernet@92000000 Waiting for PHY auto negotiation to complete......... TIMEOUT !`、
  `zx279128s: PHY startup failed (-110)`、`e2631rescue: no usable Ethernet device`；先执行一次 `e2631net` 再进救援则正常
  （`e2631net` 只打印状态，说明失败的第一轮 `eth_init()` 已经把 `hw_ready` 置起，第二轮能成）。
- DNS：`diag-after-exit.serial.log` 里 `dnsd: started, resolving 'failsafe.lan' -> 99.117.101.0`，而正常载入的
  `load.json` 是 `-> 192.168.1.1`；同一流程 DHCP 行始终是 `192.168.1.1/255.255.255.0`。
- env 修复实证：两次 no-change `POST /env` 均 `keys=0`、块不动，恢复字节级验证 PASS；mtd0 回到 `ac06d7bc…`。

## 2. 根因与修复

### 2.1 telnet 行尾（0062）

`mtk_telnetd_poll()` 旧代码：

```c
telnetd.exec_line[telnetd.line_len] = '\0';
memcpy(telnetd.exec_line, telnetd.line, telnetd.line_len + 1);
```

行编辑器只在 `line[]` 里保存 `line_len` 个字节，没有维护 `line[line_len]` 的终止符；第一行先写的终止符随后的 memcpy
把它覆盖成上一行残留的字符。`version`（7 字节）后 `bdinfo`（6 字节）实际执行 `bdinfon`。修复：新增纯 helper
`mtk_telnetd_copy_line()`（先按 `dstsz - 1` 截断，再补 NUL），poll 只走这一条路；helper 放在
`include/net/mtk_telnetd.h` 以便主机 fixture 覆盖。

### 2.2 执行槽与 console record（0062）

- `telnetd_reset_session()` 是 `memset(&telnetd, 0, sizeof(telnetd))`。若在 `draining`（私有 membuf 已装进
  `gd->console_out`）时调用，`saved_out` 被清掉，`gd->console_out` 仍指向私有 membuf；随后 membuf 被释放或复用，
  之后所有 console record（telnet 与 web）都拿不到输出——对应“满序列 telnet version 无输出”。
- 连接在 `draining` 期间死亡时，CLOSE 回调只在 `!exec_active && !draining` 才 reset；`draining` 保持为真，
  `mtk_telnetd_exec_active()` 恒真，web console 一律 503 busy；而且 `gd->console_out` 也没恢复。
- 修复：新增 `telnetd_release_session()` = 先 `telnetd_finish_capture()`（恢复 `gd->console_out`、dispose 私有缓冲）
  再 `telnetd_reset_session()`；NEW_CONN、CLOSE/REMOTE_CLOSED 回调（只要不在 `run_command()` 内）与主 poll 开头
  的 `conn_dead && !exec_active` 分支都调用它。`telnetd_execute()` 里命令执行完发现连接已死也走 release。

### 2.3 冷启动救援（0063）

- RAM 链 = 厂商 U-Boot 先跑，`board_eth_init()` 已写 PLL（`0x94000050/54`）、SerDes（`0x9fe00000` 24 个寄存器）、
  CRM2/LSP1 时钟并让内部 PHY 开始自协商；t92c 时 `e2631_net_refclk_init()` 只在 `e2631boot` 里跑过，冷救援失败是
  因为 `eth_init()` 之前没人建立时钟（0034 已修）。这次 RAM 链里时钟本来已建立，但 `e2631_net_refclk_init()` 仍会
  无条件重编程 PLL 与 SerDes，打断正在进行的自协商，第一轮 `eth_init()` 因此 -110。
- 修复：`e2631net.c` 先快照六个寄存器，交给新头 `e2631refclk.h` 的纯函数 `e2631_refclk_is_ready()` 判定；全部匹配
  厂商 post-init 值（PLL0/PLL1 低 24 位、SerDes gate `0x10061fff`、CRM divider 低 9 位、CRM2 select bit8、LSP1
  `0x0001381b`）时只置 `refclk_done` 并返回，不碰 pinmux/PLL/SerDes。`rescue_loop()` 另对 `eth_init()` 最多重试
  3 次、每次间隔 200 ms，并在最终失败信息里带尝试次数。

### 2.4 DNS 地址（0064）

- 事实：`%pI4` 直接打印 `net_ip` 的 4 个字节（`lib/vsprintf.c`），`99.117.101.0` 对应 `63 75 65 00`，等于 `net_ip`
  的 `s_addr = 0x00657563`。DNS 的线格式 builder 只把传入的 4 字节地址写进 RDATA（DNS fixture 自 0055 起就断言
  网络序字节；本次再加三组显式字节向量，含 `0x00657563`），所以 DNS 代码不是错误来源，来源是共享 `net_ip`。
- `net_ip` 会被 DHCP 服务器（`mtk_dhcpd_start()` 仅在为 0 时写）、`ipaddr` env 回调（`net/net.c:209`）与救援网络
  自身写；`net_boot_file_name[1024]` 正好紧邻其前，静态审计没有找到确定的 4 字节野写源。
- 修复分两层：(1) `mtk_dnsd_set_answer(server_ip.s_addr)` 在 `mtk_dnsd_start()` 前 pin 住救援地址，A 记录只读它；
  日志改为 `dnsd: started, resolving '…' -> <answer> (net_ip <net_ip>)`，下一场可判别两者是否一致；(2) `rescue_loop()`
  在 DNS 启动前和主循环里发现 `net_ip != server_ip` 时打印 WARNING 并恢复（最多 3 次），因为 DHCP/DNS/TCP 的源地址
  都用 `net_ip`。

## 3. 修改文件

- 0062：`include/net/mtk_telnetd.h`（`mtk_telnetd_copy_line()`）、`net/mtk_telnetd.c`（copy 路径、
  `telnetd_release_session()`、poll/execute/NEW_CONN/CLOSE 释放）。
- 0063：`board/zte/zxhn-e2631/e2631refclk.h`（新，纯检测）、`e2631net.c`（snapshot + 早返回）、
  `e2631rescue.c`（`eth_init()` 重试与提示）。
- 0064：`include/net/mtk_dnsd.h`（setter 声明）、`net/mtk_dnsd.c`（pin + 双地址日志）、`e2631rescue.c`（pin、
  启动前与主循环的 `net_ip` 检查/恢复）。

## 4. 主机 fixture 与 CI 门禁

- `uboot-port/tests/telnetd_line_test.c`（8 项）：NUL 终止、短命令无残留、截断/空行/NULL 源、256 字节边界。
- `uboot-port/tests/refclk_state_test.c`（11 项）：厂商 post-init 判定、冷复位不判定、六个字段逐个 gate、PLL1
  lock/status 位不影响结论。
- `uboot-port/tests/task99_contract_test.sh`（15 项）：行拷贝接线、`release_session` 的 finish→reset 顺序与至少 4 个
  调用点、poll 的 dead-conn 分支、refclock 检测先于重编程、救援重试/DNS pin/net_ip 恢复、dnsd 的 pinned 与双地址日志。
- `uboot-port/tests/dnsd_test.c` 29→35 项：新增 3 组 A 记录 RDATA 字节向量（`192.168.1.1`、`10.0.0.1`、
  `0x00657563`），证明 RDATA 只来自传入地址。
- `.github/workflows/uboot-build.yml`：新增三个 fixture step（`telnetd-line-test`、`refclk-state-test`、
  `task99-contract`），DNS fixture 的期望改为 `PASS (35 checks)`；全部在 `git am` 之后、交叉编译之前运行。

## 5. 静态验证（本机，无交叉编译）

- kit patch 序列 64 个；新 `E2631_UBOOT_TREE_SHA=548f064a900ce01e2e51d7bf4b6e6454a21884d1`；0040-0064 的 sha256 均已
  逐条写入 `uboot-port/commits.env`。干净 clone + `git am --committer-date-is-author-date` 回放 64 个 patch 得到同一
  tree（见 §6 验证记录）。
- 三个新 fixture 与扩充后的 DNS fixture 在本地对 patched 树全过：telnetd line 8、refclk state 11、task-99 contract
  15、DNS 35。checkpatch（`--ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF`）对 0062/0063/0064 各 0 errors /
  0 warnings。
- 本机不跑交叉编译；构建由 task-92 统一派发 `uboot-build.yml`。

## 6. 回放验证记录

- 干净 clone（u-boot base `c1958b5f6cce03956d309ce422b5d9f819955d4a`，base tree `62f07967…`）+ 按 kit 文件名顺序
  `git am --committer-date-is-author-date` 64 个 patch：**64 个 commit**，post-am tree
  `548f064a900ce01e2e51d7bf4b6e6454a21884d1`，与 `E2631_UBOOT_TREE_SHA` 一致；64 个 patch 的 sha256 与
  `uboot-port/commits.env` 逐条一致。
- 对该 am 树运行：`telnetd line fixture: PASS (8 checks)`、`refclk state fixture: PASS (11 checks)`、
  `dnsd fixture: PASS (35 checks)`、`task-99 contract fixture: PASS (15 checks)`。
- checkpatch（`--ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF`）对 0062/0063/0064 三个 commit：
  0 errors / 0 warnings（“no obvious style problems”）。
- kit 提交 `5f2c1b6`（12 files, +1128/−9）已 push 到 `origin/iwrt-adaptation`；kit「Upgrade safety checks」
  run `46145244404` SUCCESS。
- 本机未跑交叉编译；uboot-build 由 task-92 统一派发。

## 7. 真机验收要点（t92f，零写）

1. 冷 RAM 链加载 t92f 镜像；提示符第一条命令直接 `e2631rescue`：必须 `lan1 up, 1000 Mbit/s full duplex` 并打印
   `open http://…`，不得出现 `PHY startup failed (-110)` / `no usable Ethernet`；允许最多两次
   `Ethernet start attempt N failed, retrying`。
2. telnet 连续执行 `version` 再 `bdinfo`：第二条必须正常输出 `bdinfo`，不得 `Unknown command 'bdinfon'`。
3. 满探针序列后再跑 telnet / web console exec：不得再出现 503 busy 或 `console is busy`（共享槽已释放）。
4. `e2631rescue: DHCP <ip>/…` 行、`dnsd: started, resolving '…' -> <ip> (net_ip <ip>)` 行、`/status` 的地址必须一致；
   若出现 `net_ip changed to … restoring …` 的 WARNING，记录出现前的命令序列——说明仍有写者在改 `net_ip`。
5. env 块、mtd0、secondboot 区全程不变；除已批准的 userdata staging 外零 flash 写；结束 `e2631boot` 回 Linux 并记录
   `PANICS=0`、`MT7916=1`、`WIFI=1`。

## 8. 风险与未决

- `net_ip` 的 4 字节野写源仍未静态定位；0064 的 pin 让 DNS 不再受影响，WARNING 负责把首现现场留在串口日志里。
- telnet 连接在命令执行期间死亡时输出被丢弃（peer 已不存在），这是有意行为；不会再把执行槽留成 busy。
- `net_ip` 恢复守卫只在救援主循环内生效，且最多告警/恢复 3 次；串口控制台里主动 `setenv ipaddr …` 也会触发一次
  WARNING，属预期。
- 满序列后 telnet 输出依赖 console record；若其它模块在命令间重置了 console record，仍可能丢输出，t92f 复测时
  留意 `e2631rescue` 与 telnet 命令交错顺序。

## 9. 参考

- t92e 现场：`/home/qc233/zte/e2631-p3/e2/t92e-gate/run-1/`（`serial.log`、`load.json`、`diag-after-exit.serial.log`、
  `diag-rescue-retry2.serial.log`、`probe.json`）。
- 契约：`evidence/e4-v3-contract-delta-20261128.md`（§15 与 telnet/web console 端点）。
- 台账：`uboot-port/README.md` §1（pin 表）、§4 item 39/40、§5「E4 v3.1 t92f 修复」、§6 风险、§8 变更记录。
- patch sha256：0062 `bc272f4c…`、0063 `36731dad…`、0064 `86b8cb48…`。
