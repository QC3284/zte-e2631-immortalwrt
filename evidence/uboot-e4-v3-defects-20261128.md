# E4 v3 设备探针暴露的两个确定性缺陷（task-95，patch 0053/0054）

日期：2026-11-28
范围：`GET /`（救援页）与 `POST /console`（单命令）在 v3 统一构建（task-92 的 t92 镜像）上的两个 100% 复现缺陷。
结论：两者都是 U-Boot 侧实现缺陷（不是页面/网络/环境问题），已分别用 patch 0053、0054 修复，并用主机 fixture 与 CI 门禁钉住。
本任务不派发构建（task-92 第三次重建统一执行），无设备 / 无 flash 写。

## 1. 现场证据（verify-docs t92 Phase A，零写）

- 目录：`/home/qc233/zte/e2631-p3/e2/e4-v3-phasea/run-1/`（`probe.json`、`serial.log`、`console-257.headers`/`.body`、`page-retry2.headers`）。
- `GET /`：page 系列检查（`page_status_200`、`page_gzip`、`page_gzip_len`、`page_gzip_sha`、`page_raw_len`）全部 FAIL；
  curl `rc=56`，headers/body 均为空；同一救援进程里 `/sysinfo`、`/log`、`/integrity`、`/status` 大多正常。
- `POST /console?cmd=<257 个 a>`：curl `rc=56`、`elapsed_s=0.013`、status None、headers/body 空；串口没有
  `console command` 行（说明请求没进到命令执行），随后同一救援进程里所有请求都在 0.01–0.08 s 内被 RST，
  只有 Ctrl-C 能退出救援（`serial.log:618` `e2631rescue: left the rescue mode`）。
- 对照：v2 Phase A（`/home/qc233/zte/e2631-p3/e2/e4-v2-phasea/run-1`）同样发过 257 B console 请求，当时返回 200
  （截断后执行，无 wedge）；v2.1 页面 13,773 B 时 `GET /` 也正常。

## 2. 缺陷 1：`GET /` 空回复

根因（确定性，纯长度问题）：`rescue_reply()`（`board/zte/zxhn-e2631/e2631rescue.c`）把响应头和 body 拼进
`c->out[E2631_RESCUE_OUT_MAX]`，其中 body 是指向嵌入资产 `e2631_failsafe_html_gz` 的整块拷贝；
`E2631_RESCUE_OUT_MAX=16384`，而 v3 页面 gzip `e2631_failsafe_html_gz_len=24904`（`bash tools/embed-failsafe.sh --check`
本机实测 `GZ=24904`）。`(u32)n + body_len > sizeof(c->out)` 成立后走 `mtk_tcp_close_conn(c->conn, 1)` 并返回
`-ENOSPC`，于是浏览器/curl 看到空回复。v2.1 的页面 13,773 B 装在 16 KiB 里，所以此前没有暴露。

修复（patch 0053，local commit `4bbd5d5d`，tree `012115e0…`）：

- `GET /` 不再调用 `rescue_reply()`，改走 `rescue_page_start()`：响应头（`200 OK`、`Content-Type: text/html; charset=utf-8`、
  `Content-Encoding: gzip`、`Content-Length: <page_len>`、`Cache-Control: no-store`、`Connection: close`）仍只占 `c->out` 的很小一部分，
  body 直接用嵌入资产指针分块发送。
- 分块 4 KiB（`#define E2631_RESCUE_PAGE_CHUNK 4096U`），每次 `DATA_SENT` 回调推进 `page_off`；发送完 `page_off >= page_len`
  后正常关连接。块算术抽到 `board/zte/zxhn-e2631/e2631page.h` 的 `e2631_page_chunk_len()`（主机可编译）。
- 语义不变：只读、`responded`/`close_after_send` 行为与 v1/v2 一致；没有扩大 `OUT_MAX`（理由：响应缓冲是连接对象的一部分，
  每个连接都已占约 17.7 KB 堆；把 24,904 B 页面塞进去只会把堆压力转到每个连接，而页面还会继续增长）。
- 主机 fixture `uboot-port/tests/page_stream_test.c`（16 项：长度边界、末块、空洞、块数、16 KiB 缓冲对比、7 块覆盖 24,904 B 等）；
  本地编译（`-DE2631_PAGE_LEN=24904`）输出：`page stream fixture: PASS (16 checks, 7 chunks, 24904 bytes)`。
  CI 在页面生成后按真实 `e2631_failsafe_html_gz_len` 编译运行，输出 `page stream fixture: PASS`。

## 3. 缺陷 2：257 B console 请求后的救援 wedge

现场现象是“无响应 + 之后所有请求被 RST”，根因有两层，缺一不可：

(1) 长度门被截断绕过（真实缺陷，但不是 wedge 的直接原因）：`rescue_handle_request()` 把 URI 复制进 `char path[96]`
（`snprintf(c->path, sizeof(c->path), "%s", rest)`），257 B 的 `cmd=` 值只留下 82 B；0044 的
`rescue_query_raw_len()` 在截断后的字符串上测量，于是 `raw_len=82` 通过 256 B 门，按前缀继续处理。

(2) 死连接泄漏导致堆耗尽（wedge 的直接原因）：`net/mtk_tcp.c` 里 `MTK_TCP_CB_REMOTE_CLOSED` 是终态（`conn_finish()` 交付一次后
连接被 zombify + reap，不会再发 CLOSED 回调）；`e2631rescue.c` 的 `rescue_tcp_cb()` 把 `REMOTE_CLOSING` 与
`REMOTE_CLOSED` 合并成 `mtk_tcp_close_conn(c->conn, 0)`，对已 dying 的连接是 no-op。结果：

- 每个死连接泄漏 `struct e2631_rescue_conn`（含 `out[16384]`，约 17.7 KB）；
- `/backup` 整槽流（`slot0`/`slot1`/`rootfs`，task-90/0047 引入）每条连接还持有 1 MiB cache-aligned bounce buffer；
- Phase A 先前跑过三次大备份（slot0 28 MiB、slot1 28 MiB、rootfs 17 MiB），累计泄漏约 3 MiB；
- U-Boot 堆 `CONFIG_SYS_MALLOC_LEN=0x400000`（TOTAL_MALLOC_LEN 再加 `CONFIG_ENV_SIZE=0x20000`，共 0x420000），
  随后 `NEW_CONN` 的 `calloc(1, sizeof(*c))` 失败，回调里 `mtk_tcp_close_conn(cbd->conn, 1)` 立即 RST 每个新 SYN——
  正是探针看到的“257 之后所有请求 13 ms 被 reset”。
- Ctrl-C 走 `mtk_tcp_close_all_conn()`，会释放仍在 `conn_head` 里的连接（含 1 MiB buffer），所以看起来“Ctrl-C 能恢复”；
  旁证：`MTK_TCP_REXMIT_MAX_CONN_DELAY=300000` ms（`net/mtk_tcp_priv.h:60`），FIN_WAIT_2 可挂 5 分钟一直持有 buffer。

修复（patch 0054，local commit `326dc852`，tree `0b48c04a…`）：

- `struct e2631_rescue_conn.path` 由 `char path[96]` 改为 `char *path`，解析时 `c->path = rest;` 指向请求头原始行
（`hdr` 已 NUL 结尾且活到请求结束），URI 不再截断；删除原 `snprintf(c->path, …)`。
- 原始 query 长度与 256 B 门抽到 `board/zte/zxhn-e2631/e2631query.h`（`e2631_query_raw_len()`、
  `e2631_console_cmd_len_ok()`；主机可编译）。`handle_console()` 先对未截断的原始值判定，257 B 返回 400
  `result=error` / `exit=1` / `stdout=` / `truncated=0` / `error=only a single command is allowed`（契约精确 body）。
- `rescue_tcp_cb()` 拆开 `REMOTE_CLOSING`（保持 `mtk_tcp_close_conn(c->conn, 0)` 的正常关闭）与 `REMOTE_CLOSED`
  （`mtk_tcp_conn_set_pdata(cbd->conn, NULL); rescue_conn_closed(c);`），死连接不再泄漏 pdata。
- 备份流结束/失败路径在关连接前先 `free(c->backup_buf); c->backup_buf = NULL;`，1 MiB buffer 不再等 CLOSED 回调
  （也不必在 FIN_WAIT_2 里挂 5 分钟）。
- 主机 fixture `uboot-port/tests/console_query_test.c`（14 项：256/257 门边界、raw len、缺失 key、`x=1&cmd=…&y=2`
  的 `&` 截止、275 B 请求行 split 后 `path=/console` 且 raw=257 被拒、256 被接受）；输出
  `console query fixture: PASS (14 checks)`。

## 4. 本地验证（无交叉编译）

- 两个 fixture 都 include patch 安装后的头文件（`e2631page.h`/`e2631query.h`），用 `git am` 后的树编译，避免“测的不是要发布的头”。
- 全序列回放：`/home/qc233/zte/uboot-verify54` = `u-boot` 基线 `c1958b5f…` + `git am --committer-date-is-author-date`
  `uboot-port/patches/0001…0054`；`AM_RC=0`、54 commits、`HEAD^{tree}=0b48c04ad18e8df251a1ec93a2614b3a6337e06b`
  （与本机 `uboot-src` HEAD tree 一致）。
- `checkpatch.pl`（`--ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF`）对两个 commit 均 0 errors / 0 warnings。
- `e2631rescue.c` 通过 host `gcc -fsyntax-only`（`DO_DEPS_ONLY` 环境，与既有 task 相同）。
- kit 侧：`make check` 全 PASS/SKIP（exit 0）；`node tools/check-workflows.mjs` 通过；新增两条 fixture step 与两个门禁块；
  YAML 已本地解析核对。

## 5. CI 门禁（随 patch 安装进 `uboot-build.yml`）

- step `Compile and run the console query fixture`（`git am` 之后、页面生成前即可跑）：编译运行 `console_query_test.c`，
  必须打印 `console query fixture: PASS`。
- step `Compile and run the rescue page stream fixture`（页面生成之后、`make` 之前）：从生成的
  `e2631_failsafe_asset.c` 取真实 `e2631_failsafe_html_gz_len`，以 `-DE2631_PAGE_LEN=<len>` 编译运行
  `page_stream_test.c`，必须打印 `page stream fixture: PASS`（页面大小变化后 fixture 自动跟随）。
- gate `page stream gate: GET / streams the gzip page in chunks`：源码必须含 `rescue_page_start(c`、
  `e2631_page_chunk_len`、`#define E2631_RESCUE_PAGE_CHUNK 4096U`，且不得再出现
  `rescue_reply(c, 200, "OK", "text/html`。
- gate `console query gate: untruncated URI, raw length guard, released connections`：源码必须含
  `e2631_query_raw_len`、`e2631_console_cmd_len_ok`、`c->path = rest;`；不得再出现 `snprintf(c->path`；
  `rescue_tcp_cb()` 的 `REMOTE_CLOSED` 分支必须含 `rescue_conn_closed(c);`；必须有 `c->backup_buf = NULL;`。
- `tools/check-workflows.mjs` 同步钉住两条 fixture step、两条 gate 文本与关键 marker，并随 patch 数（54）/tree 更新。

## 6. 真机复测（task-92 第三次统一构建之后，零 flash 写）

1. 用新构建镜像 RAM 链进救援（`mtd read` + `crc32` + `go`，不写 mtd0），`GET /` 必须 200、`Content-Encoding: gzip`、
   body 长度等于该构建的 gzip 资产长度（当前页面 24,904 B），sha256 与 `E2631-FAILSAFE-ASSET.txt` 一致。
2. `POST /console?cmd=<257 个 a>`：必须 400 + 精确 body
   `result=error\nexit=1\nstdout=\ntruncated=0\nerror=only a single command is allowed`；同一救援进程随后
   `GET /status`、`GET /` 仍 200（不出现 RST 风暴），且串口没有 console 执行行。
3. 泄漏回归：连续 3 次 `GET /backup?part=slot0`（或 slot0/slot1/rootfs 各一次）后，再次 `GET /` 与 `/status` 仍正常；
   `/status` 的 `backup` 回到 `idle`；无 RST、无 reset。
4. 全程零 flash 写；结束时 mtd0 / bootloader 区 / env / secondboot 的 sha256 与进入前一致。

## 7. 风险与边界

- 0053 只改变 `GET /` 的发送方式，不改变页面预算（32,768 B）与镜像尺寸门禁；页面继续增长仍会受到资产检查与构建尺寸约束。
- 0054 的 `c->path` 指向 `c->hdr`，生命周期与请求相同（`hdr` 在连接关闭前不会被复用）；`hdr[1024]` 上限不变，
  更长的请求头仍按原逻辑 400 `request header too large`。
- `REMOTE_CLOSED` 分支与 `mtk_tcp` 的状态机对齐：e2631rescue 不依赖 `close_conn()` 在终态上的副作用，因此也不会再与
  `mtk_tcp` 的 reap 逻辑互相等待。
- 两个缺陷都只在设备探针里暴露过，未写过 mtd0；修复不需要重刷 bootloader 才能验证（RAM 链即可），
  整盘写入仍需用户批准。

## 8. 参考

- 契约：`evidence/e4-v3-contract-design-20261128.md`（v3 端点与错误文本）。
- 现场：`/home/qc233/zte/e2631-p3/e2/e4-v3-phasea/run-1/`（t92 Phase A，零写）。
- 代码：`board/zte/zxhn-e2631/e2631rescue.c`、`e2631page.h`、`e2631query.h`、`net/mtk_tcp.c`、`net/mtk_tcp_priv.h`。
- patch：`uboot-port/patches/0053-rescue-stream-the-rescue-page.patch`、
  `uboot-port/patches/0054-rescue-keep-the-URI-untruncated-and-release-dead-connections.patch`。
