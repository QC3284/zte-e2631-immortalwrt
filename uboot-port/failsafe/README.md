# E4 救援页资源（v2 五标签 Web UI）

本目录只有**一个**文件是源码：\`e2631-failsafe.html\`。它是 E4 v2（task-81）的救援页面：
设备端 U-Boot 通过 \`e2631rescue\` 进入救援模式后，内置 HTTP 服务器把该页面（gzip 后）发给
浏览器。页面形态照上游 failsafe（\`Yuzhii0718/bl-mt798x-dhcpd\`）的侧边栏 + 卡片布局重做，
但**不搬**其资产：上游整套资源 gzip 后约 70,858 B（含 i18n 18,468 B），本页 gzip 10,962 B。
页面不引用任何外部资源（无 CDN、无字体、无框架、无外链），完全离线可用。

页面实现 \`evidence/e4-v2-contract-design-20261128.md\` 定义的 v2 契约；v1 的 bootloader
写入（\`/flash\`）原样保留，v2 只新增只读状态、槽位固件更新、只读 env、恢复出厂四类能力。

## 1. 目录内容

| 文件 | 提交 | 说明 |
|---|---|---|
| \`e2631-failsafe.html\` | 是 | 单文件页面（HTML/CSS/JS；原始 34,069 B，gzip 10,962 B） |
| \`../../tools/embed-failsafe.sh\` | 是 | 构建期 gzip 嵌入脚本（确定性输出） |
| \`../../tools/mock-failsafe.mjs\` | 是 | 本地离线预览服务器（只绑 127.0.0.1，模拟端点） |
| \`README.md\` | 是 | 本文件 |
| \`<u-boot>/board/zte/zxhn-e2631/e2631_failsafe_asset.c/.h\` | **否** | 脚本生成物；每次构建重新生成，不入库 |

尺寸预算：**gzip 后 ≤ 32768 B**（task-87 抬闸；v1 曾为 6144 B）。
当前实测：原始 **34,069 B**，gzip **10,962 B**（limit 32,768 B），
页面 sha256 \`adc68a10fbf4eddd9f1a915f30488be1947022840c3a9ec4645c9b575758d7b1\`，
gzip sha256 \`36d9a176766cdc4245c262c04b36460a14452243b63c72bf35bcfbe7a19e09bb\`
（\`tools/embed-failsafe.sh --check\` 实测）。超限不得抬闸，只裁功能。

## 2. 冻结接口（不要改符号名/类型）

\`\`\`c
extern const unsigned char e2631_failsafe_html_gz[];
extern const unsigned int  e2631_failsafe_html_gz_len;
\`\`\`

- 数组是 **gzip 压缩后**的页面字节，\`e2631_failsafe_html_gz_len\` 是 gzip 流长度
  （不是解压后长度）。
- 服务端原样发送，不要解压：\`Content-Type: text/html\` + \`Content-Encoding: gzip\`。
  U-Boot 不链接解压器（与上游同一设计，省空间）。
- 声明位于生成的 \`e2631_failsafe_asset.h\`；base-builder 的 patch 0026 在
  \`board/zte/zxhn-e2631/Makefile\` 里加 \`obj-y += e2631_failsafe_asset.o\`，HTTP 处理器
  \`#include "e2631_failsafe_asset.h"\`。

## 3. 构建期嵌入

\`\`\`sh
# 在 $GITHUB_WORKSPACE（= kit 仓库根）执行；必须在 git am 之后、make 之前：
bash tools/embed-failsafe.sh \
  --outdir "$UBOOT_DIR/board/zte/zxhn-e2631" \
  --stats  "$UBOOT_DIR/artifacts/E2631-FAILSAFE-ASSET.txt"
\`\`\`

- \`--outdir\`：生成 \`e2631_failsafe_asset.c\` / \`.h\` 的目录（U-Boot 树内的板级目录）。
- \`--stats\`：写 \`raw_bytes / gzip_bytes / limit_bytes / gzip_sha256 / symbols\` 的元数据
  文件，供产物 \`SHA256SUMS\`、\`UBOOT-INFO.txt\` 与 step summary 使用。
- \`--check\`：只校验尺寸并打印，不写文件；\`tools/check-workflows.mjs\` 用它做静态门禁。
- 确定性：\`gzip -9 -n\`（无时间戳/文件名），C 文件里没有生成时间、绝对路径或主机名，
  同一 gzip 版本的两次生成逐字节相同。注意 gzip 实现版本变化可能改变压缩字节流——
  以 CI 产物为准，门禁只约束尺寸与符号。
- 生成物**不入库**：\`uboot-build.yml\` 的 "Embed the failsafe rescue page" 步骤在
  \`git am\` 之后、\`Configure and build\` 之前运行；缺少生成物时编译会因缺
  \`e2631_failsafe_asset.o\` 而失败（这是有意的 fail-fast）。
- 产物：生成物 \`e2631_failsafe_asset.c/.h\` 与 \`E2631-FAILSAFE-ASSET.txt\` 一起进 artifact 和
  \`SHA256SUMS\`，并在 \`UBOOT-INFO.txt\` 里记录；页面 gzip 字节也受整体 payload 预算
  （653,312 B 硬上限 / 645,120 B CI 门禁）约束。

## 4. 页面结构（v2，照上游 failsafe 形态）

| 上游 failsafe 元素 | E2631 v2 | 说明 |
|---|---|---|
| 侧边栏品牌 \`.sidebar-brand\` | 顶部品牌区“E2631 恢复模式” + U-Boot 版本小字 | 纯 CSS，无 logo 图片 |
| 导航分组/项 | 侧边栏分组：**救援**（系统状态、固件更新、引导区）、**系统**（环境变量、恢复出厂） | 不做网页终端；不做 UBI/SIMG/GPT/BL2 |
| \`.card-head\`（hero + h1 + 提示） | 每标签页卡片同样 head 结构 | 图标省略以省体积 |
| \`.card-main\`（文件选择、sysinfo、上传按钮、\`.bar\`、文件/大小/摘要行） | 固件更新 / 引导区两支上传流程 | 行改为文件 / 大小 / SHA-256 / 设备摘要 / 摘要比对 |
| \`.card-foot\` 注意事项 \`<ul>\` | 每页底部“注意事项” | 断电、另一槽回退、serial 变化等 |
| 主题 auto/light/dark、强调色、i18n | 仅 \`prefers-color-scheme\` 自动明暗；中文单语 | 省体积；无外部字体 |
| 程序页 flashing/fail/reboot | 单页内状态区（stage/进度/错误） | 不自动跳转、不自动重启 |

五个标签：

1. **系统状态**：启动路径 rail（BootROM → secondboot → U-Boot → 救援）、运行状态卡
   （\`/status\` 每秒轮询）、槽位卡（slot0/slot1 serial/version/identity/valid/intact/next，
   “下次启动此槽”按钮 → \`POST /boot\`，仅本次 RAM 覆盖）、引导区备份卡（区域 CRC32、
   只读校验值与下载）。
2. **固件更新**：选择设备升级包 \`.bin\`，浏览器端计算 SHA-256；目标槽 \`auto\`/slot0/slot1；
   显示解析目标、身份与守卫徽标；“仅校验”通过且 \`sha_match=ok\` 且守卫非 \`refuse\` 后才启用
   “写入待命”；写入确认弹窗写明目标槽与“断电重启后生效”。
3. **引导区**：v1 \`/flash\` 流程（文件必须恰 655,360 B；仅写 mtd0 \`0x20000..0xC0000\`；
   五步进度）；显示当前区域 CRC32；注意事项强调不碰 secondboot/env。
4. **环境变量**：\`/env\` 只读快照表格，刷新按钮；标注写入只能走串口 \`e2631env\`（白名单）。
5. **恢复出厂**：说明只擦 \`rootfs_data\`（overlay/配置丢失，squashfs/槽位不动）；勾选确认 +
   \`confirm()\` 双确认；\`POST /factory\`；进度与结尾“断电重启后生效”。

交互硬规则：写按钮按摘要/守卫门控；忙时所有写按钮禁用；不做自动重启；成功文案**只用
“断电重启后生效”**，页面不提示 reset（Linux 运行时按住 reset ≥5 s = factory reset，启动时
按住 = 救援触发）；无外部资源；\`label for\`、\`:focus-visible\`、\`prefers-reduced-motion\`、
窄屏单列。

## 5. HTTP 协议（页面对设备）

v2 端点契约以 \`evidence/e4-v2-contract-design-20261128.md\` 为准，页面只按该契约发请求。

| 请求 | 语义 |
|---|---|
| \`GET /\` | 本页面（gzip，\`Content-Encoding: gzip\`） |
| \`GET /status\` | 纯文本行；单线程服务器每次调用推进一步状态机（页面 1 s 轮询） |
| \`GET /slots\` | 槽位快照（serial/version/identity/valid/intact/next） |
| \`GET /env\` | 当前 env 只读快照（\`key=value\`，含可选 \`env_size=\`） |
| \`GET /backup\` | mtd0 \`0x20000..0xC0000\`（655,360 B）+ \`X-E2631-CRC32\`/\`X-E2631-SHA256\` 头 |
| \`POST /boot?slot=0|1\` | 仅本次 RAM 启动覆盖 \`e2631_next_slot\`（不写 flash） |
| \`POST /firmware?mode=validate\` | body = 固件包；校验包结构与摘要，不写 flash |
| \`POST /firmware?mode=write\` | 同上 + \`X-E2631-Confirm: write\`；校验后写目标槽 |
| \`POST /flash?mode=validate\` | body = 655,360 B bootloader 镜像；只校验 |
| \`POST /flash?mode=write\` | 同上 + \`X-E2631-Confirm: write\`；五步写 mtd0 镜像区 |
| \`POST /factory?confirm=reset\` | 擦除 \`rootfs_data\` + 全 FF 回读；需 \`X-E2631-Confirm: reset\` |

请求头（写操作必需）：\`Content-Length\` 精确长度、\`X-E2631-SHA256\`（64 位小写 hex，对
**整个上传文件**的 SHA-256；固件与 bootloader 相同）、\`X-E2631-Confirm\`（\`write\` 或
\`reset\`，防误写）。页面用 \`XMLHttpRequest\` 原样发送文件（\`xhr.send(file)\`，不是
multipart），进度来自 \`xhr.upload.onprogress\`。

响应（\`text/plain\`，逐行 \`key=value\`，客户端容忍未知键）：v1 键
\`stage/progress/crc32/sha256/browser_sha256/sha_match/result/error\` 不变；v2 追加
\`op/mode/slot/slot_target/slot_target_identity/guard/guard_reason/bytes_total/bytes_done/
written_serial/version/next_slot/next_reason/slot0_*/slot1_*/bootloader_region_crc32\`。

页面解析规则：POST 返回 \`result=staged|accepted\` → 开始轮询；\`result=ok\` 或
\`stage=done\` → 成功；\`result=error\`/\`error=\` → 失败。轮询间隔 500 ms；连接错误重试。
摘要门控：设备返回的 \`sha256=\` 必须与浏览器计算值一致且 \`sha_match=ok\`，才允许启用写按钮。

## 6. 本地预览（不接设备）

\`\`\`sh
node tools/mock-failsafe.mjs          # 默认 http://127.0.0.1:8787/
PORT=8790 node tools/mock-failsafe.mjs
\`\`\`

模拟器只绑定 \`127.0.0.1\`，读取真实页面文件，模拟 \`/status /slots /env /backup /boot
/firmware /flash /factory\`，用状态机逐步推进进度；不访问 flash、不与设备通信、不写任何
文件。用于改页面后的离线视觉/交互检查（task-81 证据见
\`evidence/failsafe-redesign-20261128.md\`）。

## 7. 修改页面

1. 只改 \`e2631-failsafe.html\`；保持单文件、无外部依赖、无 CDN/字体/框架、无绝对 URL。
2. 改完跑 \`bash tools/embed-failsafe.sh --check\`；必须 ≤ 32768 B（v2 预算）。
3. \`node tools/mock-failsafe.mjs\` 打开预览，检查五个标签与摘要门控。
4. 若改路由/字段/头部，先与 base-builder 对齐（task-84 按 \`evidence/e4-v2-contract-design-20261128.md\`
   实现），并同步更新本 README、契约文档与 \`docs/E4-多功能U-Boot设计-2026-11-27.md\`。
5. 改文案不要求改 C 代码；构建期自动重新生成。

## 8. 验收

- \`bash tools/embed-failsafe.sh --check\` → gzip ≤ 32768 B。
- \`node tools/check-workflows.mjs\` → 含救援页/嵌入步骤/产物记录的静态检查全 PASS。
- \`uboot-build\` 的 "Embed the failsafe rescue page" 步骤绿，产物含
  \`E2631-FAILSAFE-ASSET.txt\` 且在 \`SHA256SUMS\` 中。
- 真机验收（task-86）：按键进入 \`e2631rescue\` → 浏览器打开 \`http://192.168.1.1/\` →
  各只读标签显示正确；bootloader 走“仅校验 + 负例 + 净零镜像写”流程；固件写只做
  validate 与负例，**首次真实固件升级**（新镜像）走 \`/firmware\` 作为该端点验收，需用户批准。
  页面显示成功且不自动重启；返回 Linux 需要断电重启（reset 命令的修复是独立任务）。

## 9. 许可

页面、脚本、README 均为本项目自有代码，\`GPL-2.0+\`（与 \`uboot-port\` 一致）。不复制上游
failsafe 资源；符号名/协议只作为接口约定使用。
