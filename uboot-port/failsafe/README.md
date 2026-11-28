# E4 救援页资源（v1 最小救援 Web UI）

本目录只有**一个**文件是源码：`e2631-failsafe.html`。它是 E4 v1（task-73）的最小救援
页面——设备端 U-Boot（task-72）通过 `e2631rescue` 进入救援模式后，由内置 HTTP 服务器
把这个页面（gzip 后）发给浏览器。页面不引用任何外部资源（无 CDN、无字体、无框架、
无 i18n），因此可以在完全离线的救援现场使用。

上游 `Yuzhii0718/bl-mt798x-dhcpd` 的 failsafe 资源（整套 gzip 70,858 B，含 i18n 18,468 B）
不搬——它绑定 MTK 板级 UI 与多页面流程，v1 只需要「上传一个镜像 + 校验 + 写入」这一件事。

## 1. 目录内容

| 文件 | 提交 | 说明 |
|---|---|---|
| `e2631-failsafe.html` | 是 | 单文件页面（HTML/CSS/JS，约 7.9 KB 原始） |
| `../../tools/embed-failsafe.sh` | 是 | 构建期 gzip 嵌入脚本（确定性输出） |
| `README.md` | 是 | 本文件 |
| `<u-boot>/board/zte/zxhn-e2631/e2631_failsafe_asset.c/.h` | **否** | 脚本生成物；每次构建重新生成，不入库 |

尺寸预算（E4 v2 门禁，task-83 契约 + task-87 抬闸；v1 为 6144 B）：**gzip 后 ≤ 32768 B**。
当前页面：原始 9216 B，gzip **4456 B**（`tools/embed-failsafe.sh --check` 实测；gzip
sha256 随页面内容变化，记录在构建产物的 `E2631-FAILSAFE-ASSET.txt` 中）。v2 页面按
`evidence/e4-v2-contract-design-20261128.md` 的 32 KiB 预算重做，闸门由
`tools/embed-failsafe.sh` 与 `tools/check-workflows.mjs` 强制；超限由 task-81 裁功能，不得抬闸。

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
bash tools/embed-failsafe.sh \
  --outdir "$UBOOT_DIR/board/zte/zxhn-e2631" \
  --stats  "$UBOOT_DIR/artifacts/E2631-FAILSAFE-ASSET.txt"
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

## 4. 页面行为（v1，与 Lead 需求 MUST 对齐）

1. 选择 `e2631-uboot-mtd0.bin`（**必须恰为 655,360 字节**）；页面立即显示文件名、大小，
   并用浏览器端纯 JS SHA-256 计算并显示摘要（在 `http://192.168.1.1` 上 WebCrypto 不可用，
   所以自带实现；对 640 KiB 约 30 ms）。
2. 两个按钮：
   - **仅校验**：`POST /flash?mode=validate`，设备读入 RAM 后校验大小/magic/几何/头 CRC 与
     `X-E2631-SHA256` 摘要，不写 flash；返回 `result=ok`、`sha256=`、`sha_match=`；
     页面显示设备摘要并与浏览器摘要比对，**只有 `sha_match=ok` 才启用「写入待命」**；
   - **写入待命**：`POST /flash?mode=write`，额外带 `X-E2631-Confirm: write` 与
     `X-E2631-SHA256` 头（缺失/格式错/摘要不符都返回 400，不擦除）；设备校验通过后进入
     擦写状态机，成功响应带 `sha256=`。
3. 上传用 `XMLHttpRequest`（`xhr.send(file)`，raw body，**不是 multipart**），进度条来自
   `xhr.upload.onprogress`；POST 返回 `result=ok`（校验）或 `result=accepted`（写入）后，
   页面每 500 ms 轮询 `GET /status`，显示阶段（校验/擦除/擦除校验/写入/回读/比对）、进度、
   设备摘要 `sha256=`、`browser_sha256=` 与 `sha_match=ok|mismatch|absent`。
4. 成功：显示 CRC32，并明确提示「未自动重启：请断电重启（拔电再上电）」；U-Boot 的
   `reset` 命令当前不可用（patch 0003 的 `reset_cpu()` 只是打印占位的提示，task-76 修复），
   所以页面与串口都不把 `reset` 作为可靠路径。页面不调用 `/reboot`，不做任何自动重启。
5. 失败：页面显示设备返回的 `error=` 原因（尺寸不符、magic 不符、擦写/回读/比对失败等），
   按钮恢复可点。连接断开按可重试处理（连续 20 次失败或 10 分钟超时才报错）。
6. 其他路径一律 404；页面不引用任何外部 URL。

## 5. HTTP 协议（页面对设备；task-72 实现）

| 请求 | 语义 |
|---|---|
| `GET /` | 本页面（gzip，`Content-Encoding: gzip`） |
| `POST /flash?mode=validate` | body = 655,360 B 原始镜像；读入 RAM 0x46000000；不写 flash |
| `POST /flash?mode=write` | 同上，但必须带 `X-E2631-Confirm: write`；校验后进入擦写状态机 |
| `GET /status` | 纯文本行；单线程服务器每次调用推进一步状态机 |

请求头：`Content-Length`（必需，恰好 655360）、`Content-Type: application/octet-stream`
（设备忽略）、`X-E2631-SHA256`（64 位小写 hex，对**整个 655,360 B 文件**的 SHA-256；
`mode=write` 必需，`mode=validate` 建议但可缺省）、`X-E2631-Confirm: write`（`mode=write`
必需，防误写）。旧 `X-File-Sha256` 仅在 `X-E2631-SHA256` 缺失时作为兼容回退。

响应（`text/plain`，逐行 `key=value`，客户端容忍未知键）：

```
stage=idle|staged|validating|erase|blank|write|readback|compare|done|error
progress=<0..100>
crc32=0x<hex>
sha256=<设备计算的 64 位 hex>
browser_sha256=<收到的头值或空>
sha_match=ok|mismatch|absent
result=staged|accepted|ok|error
error=<短原因>        # 仅 result=error 时
```

页面解析规则：POST 返回 `result=staged|accepted` → 开始轮询；`result=ok` 或
`stage=done` → 成功；`result=error`/`error=` → 失败。轮询间隔 500 ms；连接错误重试。

## 6. 修改页面

1. 只改 `e2631-failsafe.html`；保持单文件、无外部依赖、无 CDN/字体/框架。
2. 改完跑 `bash tools/embed-failsafe.sh --check`；必须 ≤ 32768 B（task-87 抬闸后的 v2 预算）。
3. 本地预览：直接浏览器打开 `e2631-failsafe.html` 可检查布局（按钮无设备会失败，属正常）；
   需要看 gzip 效果可 `gzip -9 -n -c ... | gzip -dc`。
4. 若改路由/字段/头部，先与 base-builder 对齐（task-72 的 HTTP 处理器按 §5 实现），
   并同步更新本 README 与 `docs/E4-多功能U-Boot设计-2026-11-27.md`。
5. 改文案不要求改 C 代码；构建期自动重新生成。

## 7. 验收

- `bash tools/embed-failsafe.sh --check` → gzip ≤ 32768 B。
- `node tools/check-workflows.mjs` → 含救援页/嵌入步骤/产物记录的静态检查全 PASS。
- `uboot-build` 的 "Embed the failsafe rescue page" 步骤绿，产物含
  `E2631-FAILSAFE-ASSET.txt` 且在 `SHA256SUMS` 中。
- 真机验收（F2 修复后）：`e2631rescue` → 电脑 DHCP 拿地址 → 打开 `http://192.168.1.1/` →
  仅校验（设备/浏览器摘要一致，`sha_match=ok`）→ 写入待命 → 串口同刻显示五步 →
  页面显示成功且不会自动重启；返回 Linux 需要断电重启（reset 命令要等 task-76）。
  无浏览器验收见 evidence/e4-rescue-acceptance-plan-20261127.md 与 tools/e4-rescue-acceptance.sh。

## 8. 许可

页面、脚本、README 均为本项目自有代码，`GPL-2.0+`（与 `uboot-port` 一致）。不复制上游
failsafe 资源；符号名/协议只作为接口约定使用。
