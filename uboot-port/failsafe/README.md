# E4 救援页资源（v3.1 六标签 Web UI，中英双语，外观对齐上游）

本目录只有**一个**文件是源码：`e2631-failsafe.html`。它是 E4 v3.1（task-96，承接 v3/task-91）
的救援页面：设备端 U-Boot 通过 `e2631rescue` 进入救援模式后，内置 HTTP 服务器把该页面（gzip 后）
发给浏览器。页面**外观照上游 failsafe**（`Yuzhii0718/bl-mt798x-dhcpd` 的 `failsafe/embedded/fsdata-bootstrap`）
重新实现：同样的侧边栏品牌/控件/导航、卡片头图+标题+提示、卡片主体、注意事项脚注、进度条与表格，
但**不整包搬上游资源**；页面内联的 CSS 是从上游 `style.css` 裁剪出的子集（见 §9 许可），
业务 HTML/JS 为本项目自有。页面不引用任何外部资源（无 CDN、无字体、无框架、无外链），完全离线可用。

**v3.1（task-96）增量**：外观按上游重做（侧边栏 + 品牌控件 + 卡片 shell）；新增**语言/主题/强调色**
控件（中文/English；自动/亮色/暗色；8 个上游强调色）；**串口台升级为实时网页终端**（照上游形态，
HTTP 轮询 + ANSI/VT100 网格渲染；端点 `POST /console/exec`、`POST /console/poll`、
`POST /console/abort`、`POST /console/clear`），旧固件无这些端点时自动退回 v2.1 的
`POST /console?cmd=` 单命令模式。v3 的六个标签、全部端点与中英字典保留。

**v3（task-91）增量**：系统信息 `GET /sysinfo`、启动日志快照 `GET /log`（可下载）、完整性自检
`POST /integrity`、用户确认的重启 `POST /reboot`（`X-E2631-Confirm: reboot`）、引导区备份扩为
9 项（加 `slot0/slot1/rootfs/header`）、DHCP 配置卡（`e2631_dhcp_*` 白名单键）、蓝色 LED 救援提示，
以及**中/EN 双语**（单文件字典，默认中文，`localStorage` 键 `e2631_lang`；忙时不允许切换）。

页面实现 `evidence/e4-v2-contract-design-20261128.md` 的 v2/v2.1 契约与
`evidence/e4-v3-contract-delta-20261128.md` 的 v3 契约；v1 的 bootloader 写入（`/flash`）原样保留。
v2.1 新增串口台、env 白名单写回（`/env` 复用 `e2631env` 五步）、引导区分区备份
（`/backup?part=`）；v3 新增系统信息/日志/完整性/重启/整槽备份/DHCP 与中英双语。
明确不做 UBI/SIMG（MT798x 专属）、不做网页终端 stdin（实时终端只发单条命令，不转发按键流）。

## 1. 目录内容

| 文件 | 提交 | 说明 |
|---|---|---|
| `e2631-failsafe.html` | 是 | 单文件页面（HTML/CSS/JS；原始 **113,057 B**，gzip **31,518 B**） |
| `../../tools/embed-failsafe.sh` | 是 | 构建期 gzip 嵌入脚本（确定性输出） |
| `../../tools/mock-failsafe.mjs` | 是 | 本地离线预览服务器（只绑 127.0.0.1，模拟端点，含实时终端） |
| `README.md` | 是 | 本文件 |
| `<u-boot>/board/zte/zxhn-e2631/e2631_failsafe_asset.c/.h` | **否** | 脚本生成物；每次构建重新生成，不入库 |

尺寸预算：**gzip 后 ≤ 32768 B**（task-87 抬闸；v1 曾为 6144 B）。
当前实测：原始 **113,057 B**，gzip **31,518 B**（limit 32,768 B，余量 1,250 B）。
页面 sha256 `82a44f59384144cf037d5d74d4ccdffab50dc5462f000ee3647765a48ed684f3`，
gzip sha256 `e452fb022e5d451eefbefaa5a4368941ce77d7fb353ef88ba43f691dedfe635f`
（`tools/embed-failsafe.sh --check` 实测）。超限不得抬闸，只裁功能；v3.1 已通过压缩 CSS 子集、
精简 I18N 键、压缩 body/custom CSS 控制在门内，双语保留。

## 2. 冻结接口（不要改符号名/类型）

```c
extern const unsigned char e2631_failsafe_html_gz[];
extern const unsigned int  e2631_failsafe_html_gz_len;
```

- 数组是 **gzip 压缩后**的页面字节，`e2631_failsafe_html_gz_len` 是 gzip 流长度
  （不是解压后长度）。
- 服务端原样发送，不要解压：`Content-Type: text/html` + `Content-Encoding: gzip`。
  U-Boot 不链接解压器（与上游同一设计，省空间）。
- 声明位于生成的 `e2631_failsafe_asset.h`；base-builder 的 patch 0026 在
  `board/zte/zxhn-e2631/Makefile` 里加 `obj-y += e2631_failsafe_asset.o`，HTTP 处理器
  `#include "e2631_failsafe_asset.h"`。

## 3. 构建期嵌入

```sh
# 在 $GITHUB_WORKSPACE（= kit 仓库根）执行；必须在 git am 之后、make 之前：
bash tools/embed-failsafe.sh   --outdir "$UBOOT_DIR/board/zte/zxhn-e2631"   --stats  "$UBOOT_DIR/artifacts/E2631-FAILSAFE-ASSET.txt"
```

- `--outdir`：生成 `e2631_failsafe_asset.c` / `.h` 的目录（U-Boot 树内的板级目录）。
- `--stats`：写 `raw_bytes / gzip_bytes / limit_bytes / gzip_sha256 / symbols` 的元数据
  文件，供产物 `SHA256SUMS`、`UBOOT-INFO.txt` 与 step summary 使用。
- `--check`：只校验尺寸并打印，不写文件；`tools/check-workflows.mjs` 用它做静态门禁。
- 确定性：`gzip -9 -n`（无时间戳/文件名），C 文件里没有生成时间、绝对路径或主机名，
  同一 gzip 版本的两次生成逐字节相同。注意 gzip 实现版本变化可能改变压缩字节流——
  以 CI 产物为准，门禁只约束尺寸与符号。
- 生成物**不入库**：`uboot-build.yml` 的 "Embed the failsafe rescue page" 步骤在
  `git am` 之后、`Configure and build` 之前运行；缺少生成物时编译会因缺
  `e2631_failsafe_asset.o` 而失败（这是有意的 fail-fast）。
- 产物：生成物 `e2631_failsafe_asset.c/.h` 与 `E2631-FAILSAFE-ASSET.txt` 一起进 artifact 和
  `SHA256SUMS`，并在 `UBOOT-INFO.txt` 里记录；页面 gzip 字节也受整体 payload 预算
  （653,312 B 硬上限 / 645,120 B CI 门禁）约束。

## 4. 页面结构（v3.1，照上游 failsafe 形态）

| 上游 failsafe 元素 | E2631 v3.1 | 说明 |
|---|---|---|
| `.app` 侧边栏 + `.main` | 左侧栏 + 右侧主区，≤860px 单列 | 与上游同一 `.app`/侧栏宽度/卡片布局 |
| `.sidebar-brand` | 内联 SVG 标志 + “恢复模式 WEBUI”（EN: Failsafe Web UI）+ U-Boot 版本小字 | 无外部图片 |
| `.sidebar-controls` | 语言（中文/English）、主题（自动/亮色/暗色）、强调色（8 个上游预置） | 存入 localStorage；无外部依赖 |
| 导航分组/项 | **救援**：系统状态、固件更新、引导区；**系统**：环境变量、串口台、恢复出厂 | 不做 UBI/SIMG/GPT/BL2 |
| `.card-head`（hero + h1 + 提示） | 每标签页内联 SVG 头图 + 标题 + 提示 + 状态徽标 | 与上游同一 head 结构 |
| `.card-main` | 文件选择、表格、进度条 `.bar`、摘要行、按钮组 | 行改为文件/大小/SHA-256/设备摘要/摘要比对 |
| `.card-foot` 注意事项 `.i.w` | 每页底部“注意事项” | 断电、另一槽回退、serial 变化等 |
| 主题 auto/light/dark、强调色、i18n | 同上；中/EN 单文件字典 | 保留 v3 双语 |
| 程序页 flashing/fail/reboot | 单页内状态区（stage/进度/错误） | 不自动跳转、不自动重启 |

六个标签：

1. **系统状态**：启动路径 rail、运行状态表（`/status` 每秒轮询）、槽位表
   （slot0/slot1 serial/version/identity/valid/intact/next，“下次启动此槽”按钮 → `POST /boot`，
   仅本次 RAM 覆盖）、系统信息表、启动日志、完整性自检。
2. **固件更新**：选择设备升级包 `.bin`，浏览器端计算 SHA-256；目标槽 `auto`/slot0/slot1；
   显示解析目标、身份与守卫徽标；“仅校验”通过且 `sha_match=ok` 且守卫非 `refuse` 后才启用
   “写入待命”；写入确认弹窗写明目标槽与“断电重启后生效”。
3. **引导区**：v1 `/flash` 流程（文件必须恰 655,360 B；仅写 mtd0 `0x20000..0xC0000`；
   五步进度）；显示当前区域 CRC32；分区备份下拉（9 项，只读 `GET /backup?part=`，
   显示偏移/长度/CRC32/SHA-256 并可下载）；用户确认的 `/reboot`；注意事项强调不碰
   secondboot/env。
4. **环境变量**：只读快照表 + 白名单键编辑（`bootdelay` 与 `e2631_*`）；勾选确认 +
   `confirm()` 双确认后按键逐个 `POST /env?key=&value=&confirm=write`，轮询 `/status`
   （`op=envwrite` 五步：diff → check → erase → write → readback → verify → done）；
   vendor 键页面不提供编辑入口；成功只提示断电重启。含 DHCP 配置卡。
5. **串口台（v3.1 实时终端）**：照上游 `console.html/console_js.js` 形态的终端区；
   输入单条命令 → `POST /console/exec`（multipart `cmd`，≤256 B）→ 150/300 ms 轮询
   `POST /console/poll` → ANSI/VT100 网格渲染（24×100；处理 CSI H/f/A/B/C/D/G/J/K、
   `
	`，忽略颜色 SGR）；`POST /console/abort` 发 Ctrl-C，`POST /console/clear`
   清屏。旧固件缺少端点时自动退回 `POST /console?cmd=` 单命令模式。**无 stdin 转发**，
   交互式命令请用物理串口。
6. **恢复出厂**：说明只擦 `rootfs_data`（overlay/配置丢失，squashfs/槽位不动）；勾选确认 +
   `confirm()` 双确认；`POST /factory`；进度与结尾“断电重启后生效”。

交互硬规则：写按钮按摘要/守卫门控；忙时所有写按钮禁用；不做自动重启；成功文案**只用
“断电重启后生效”**，页面不提示 reset（Linux 运行时按住 reset ≥5 s = factory reset，启动时
按住 = 救援触发）；无外部资源；`label for`、`:focus-visible`、`prefers-reduced-motion`、
窄屏单列。安全提示（页无鉴权、串口台可执行任意单条命令）只写文档，不设口令门（用户裁定）。

## 5. HTTP 协议（页面对设备）

v2 端点契约以 `evidence/e4-v2-contract-design-20261128.md` 为准（含 §15 v2.1 增补），
页面只按该契约发请求。

| 请求 | 语义 |
|---|---|
| `GET /` | 本页面（gzip，`Content-Encoding: gzip`） |
| `GET /status` | 纯文本行；单线程服务器每次调用推进一步状态机（页面 1 s 轮询） |
| `GET /slots` | 槽位快照（serial/version/identity/valid/intact/next） |
| `GET /env` | 当前 env 只读快照（`key=value`，含可选 `env_size=`） |
| `GET /backup?part=bootloader|tag|wifi|usercfg|defcfg|slot0|slot1|rootfs|header` | 分区只读备份 + `X-E2631-CRC32`/`X-E2631-SHA256`/`X-E2631-Offset`/`X-E2631-Length`/`X-E2631-Part` 头；缺省 bootloader |
| `POST /boot?slot=0|1` | 仅本次 RAM 启动覆盖 `e2631_next_slot`（不写 flash） |
| `POST /firmware?mode=validate` | body = 固件包；校验包结构与摘要，不写 flash |
| `POST /firmware?mode=write` | 同上 + `X-E2631-Confirm: write`；校验后写目标槽 |
| `POST /flash?mode=validate` | body = 655,360 B bootloader 镜像；只校验 |
| `POST /flash?mode=write` | 同上 + `X-E2631-Confirm: write`；五步写 mtd0 镜像区 |
| `POST /factory?confirm=reset` | 擦除 `rootfs_data` + 全 FF 回读；需 `X-E2631-Confirm: reset` |
| `POST /env?key=&value=&confirm=write` | 只写白名单键（bootdelay / e2631_*）；需 `X-E2631-Confirm: write`；响应 accepted + `/status` 五步 |
| `POST /console/exec` | **v3.1** multipart/form-data 字段 `cmd`（≤256 B，可选 `token`）→ JSON `{"ret":<n>}`；单执行槽，忙时 503 `{"error":"busy"}` |
| `POST /console/poll` | **v3.1** multipart（可选 token）→ JSON `{"data":"…","avail":<n>,"overflow":<bool>,"busy":<bool>}`；ANSI/VT100/退格按字节保留 |
| `POST /console/abort` | **v3.1** Ctrl-C；重复安全 |
| `POST /console/clear` | **v3.1** 清空设备端 console record 缓冲 |
| `POST /console?cmd=` | v2.1 兼容单命令：执行单条命令并捕获 stdout（≤4 KiB，超出截断）；含 `;`/换行 400；无 stdin |

请求头（写操作必需）：`Content-Length` 精确长度、`X-E2631-SHA256`（64 位小写 hex，对
**整个上传文件**的 SHA-256；固件与 bootloader 相同）、`X-E2631-Confirm`（`write` 或
`reset`，防误写）。bootloader/固件上传仍用 `XMLHttpRequest` 原样发送文件
（`xhr.send(file)`，不是 multipart），进度来自 `xhr.upload.onprogress`；只有 v3.1 实时终端
的 `/console/exec|poll|abort|clear` 用 multipart。`/env` 写与 `/factory` 同样要求确认头；
`/console*` 不设确认头（用户裁定不设口令门），页面侧二次确认。

响应（`text/plain`，逐行 `key=value`，客户端容忍未知键）：v1 键
`stage/progress/crc32/sha256/browser_sha256/sha_match/result/error` 不变；v2 追加
`op/mode/slot/slot_target/slot_target_identity/guard/guard_reason/bytes_total/bytes_done/
written_serial/version/next_slot/next_reason/slot0_*/slot1_*/bootloader_region_crc32`；
v2.1 追加 `/env` 的 `new_crc32/keys` 与 `/console` 的 `exit/stdout/truncated`；v3 追加
`/sysinfo`、`/log`、`/integrity`、`/reboot` 的响应；实时终端按上面的 JSON 形状。

页面解析规则：POST 返回 `result=staged|accepted` → 开始轮询；`result=ok` 或
`stage=done` → 成功；`result=error`/`error=` → 失败。轮询间隔 500 ms；连接错误重试。
摘要门控：设备返回的 `sha256=` 必须与浏览器计算值一致且 `sha_match=ok`，才允许启用写按钮。

## 6. 本地预览（不接设备）

```sh
node tools/mock-failsafe.mjs          # 默认 http://127.0.0.1:8787/
PORT=8790 node tools/mock-failsafe.mjs
```

模拟器只绑定 `127.0.0.1`，读取真实页面文件，模拟 `GET / /status /slots /env /backup?part=
/boot`、`POST /firmware /flash /factory`、`POST /env`（白名单校验 + 五步状态机）、
`POST /console`（单命令校验 + 假 stdout）以及 v3.1 的 `POST /console/exec|poll|abort|clear`
（内存 console record，exec 后 poll 取回输出）；`/backup` 按分区返回对应长度与 CRC/SHA 头。
不访问 flash、不与设备通信、不写任何文件。用于改页面后的离线视觉/交互检查
（task-81/88/91/96 证据见 `evidence/failsafe-redesign-20261128.md`）。

## 7. 修改页面

1. 只改 `e2631-failsafe.html`；保持单文件、无外部依赖、无 CDN/字体/框架、无绝对 URL。
2. 改完跑 `bash tools/embed-failsafe.sh --check`；必须 ≤ 32768 B（v3.1 预算，余量 1,250 B）。
3. `node tools/mock-failsafe.mjs` 打开预览，检查六个标签、摘要门控、env 写、实时终端与
   实时终端不可用时的单命令回退。
4. 若改路由/字段/头部，先与 base-builder 对齐，并同步更新本 README、契约文档与
   `docs/E4-多功能U-Boot设计-2026-11-27.md`。
5. 改文案不要求改 C 代码；构建期自动重新生成。

## 8. 验收

- `bash tools/embed-failsafe.sh --check` → gzip ≤ 32768 B。
- `node tools/check-workflows.mjs` → 含救援页/嵌入步骤/产物记录的静态检查全 PASS。
- `uboot-build` 的 "Embed the failsafe rescue page" 步骤绿，产物含
  `E2631-FAILSAFE-ASSET.txt` 且在 `SHA256SUMS` 中。
- 真机验收（task-86）：按键进入 `e2631rescue` → 浏览器打开 `http://192.168.1.1/` →
  各只读标签显示正确；bootloader 走“仅校验 + 负例 + 净零镜像写”流程；固件写只做
  validate 与负例，**首次真实固件升级**（新镜像）走 `/firmware` 作为该端点验收，需用户批准。
  v2.1 补充：`/console` 用 `version`、`printenv bootdelay`、`md 0x40000000 4` 验证 stdout；
  含分号/换行请求 400；`/env` 写 `e2631_*` 测试键走五步并回读一致、vendor 键 403；
  `/backup?part=` 九个分区长度/offset/CRC32/SHA-256 与设备一致、未知 part 400。
  **v3.1 补充**：实时终端 `POST /console/exec` 执行 `version` 后在 `/console/poll` 收到
  ANSI 输出；`/console/abort`/`/console/clear` 生效；旧固件（无四端点）自动显示单命令模式。
  页面显示成功且不自动重启；返回 Linux 需要断电重启（reset 命令的修复是独立任务）。
- 浏览器无关自动化：`tools/e4-rescue-acceptance.sh --v21 --firmware-pkg <工厂包>` 覆盖
  P2-P6 的 HTTP 断言（六标签/32 KiB、/backup 九分区头、/console 单命令+截断、/firmware
  validate 正例 + 9 负例含产品串第 17 B、/env no-change 与拒绝、/factory 仅拒绝、/boot
  RAM 覆盖后清除）；mock 自测 PASS=138 FAIL=0 NOTE=1，详见验收方案 §14。

## 9. 许可

页面、脚本、README 以本项目自有代码为主，`GPL-2.0+`（与 `uboot-port` 一致）。
页面内联 CSS 子集裁剪自上游 `failsafe/embedded/fsdata-bootstrap/style.css`
（`Yuzhii0718/bl-mt798x-dhcpd`，GPL-2.0；上游版权声明见页面头部注释：
MediaTek 2022 / Yuzhii0718 2026）；不复制上游 HTML/JS/图片/字体/i18n 资产，只参考布局与
交互。保留 GPL-2.0 许可与版权声明；本项目同为 GPL-2.0+，兼容。
