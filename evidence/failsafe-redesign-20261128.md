# E4 v2 救援页重做（task-81）

日期：2026-11-28。范围：把 E4 救援页从 v1（单卡片上传）重做为 v2 五标签 Web UI，形态照
上游 failsafe，功能严格按 task-83 契约；不改 U-Boot C 代码、不触发 uboot-build、不接设备。

## 0. 结论

- 页面已重写为单文件、自包含、中文、五标签：**系统状态 / 固件更新 / 引导区 / 环境变量 /
  恢复出厂**；拓扑照上游 failsafe（侧边栏品牌 + 导航分组 + card head/main/foot + 进度条 +
  注意事项列表），但不搬上游资产。
- 尺寸：原始 **34,069 B**，gzip **10,962 B**（上限 32,768 B，余量 21,806 B）；gzip sha256
  = 36d9a176766cdc4245c262c04b36460a14452243b63c72bf35bcfbe7a19e09bb，页面 sha256 =
  adc68a10fbf4eddd9f1a915f30488be1947022840c3a9ec4645c9b575758d7b1。
- v1 功能不变：引导区仍走 /flash?mode=validate|write，原始 655,360 B 上传、纯 JS SHA-256、
  X-E2631-SHA256 摘要门控、X-E2631-Confirm: write、五步进度、写入成功只提示“断电重启后生效”。
- 新增 v2 只读/写入模块（页面侧就绪，设备侧 C 由 task-84 实现）：/status v2 键、/slots、
  /env、/backup、/boot、/firmware、/factory。
- 本地离线预览：node tools/mock-failsafe.mjs（只绑 127.0.0.1，模拟上述端点）。
- 门禁：tools/embed-failsafe.sh --check → gzip 10,962 ≤ 32,768；node tools/check-workflows.mjs
  107 项全 PASS；make check 全 PASS/有理由 SKIP。

## 1. 上游 failsafe 形态摘要（只作布局参考，不复制资产）

上游：Yuzhii0718/bl-mt798x-dhcpd master e4cf4dc4 的 uboot-mtk-20250711/failsafe/（其
web/dhcpd 代码源自 hanwckf/bl-mt798x 与 MediaTek 2022，Yuzhii 2026 扩展；GPL-2.0）。
形态事实（实测/源码）：

- 左侧固定侧边栏：品牌区（logo + 名称“恢复模式 WEBUI”）、语言/主题/强调色控件、分组导航
  （基础功能：固件升级/更新 U-Boot；高级功能：BL2/GPT/SIMG/UBI/Factory/Initramfs；
  系统：闪存备份/闪存编辑/环境管理/网页终端/重启设备）。
- 内容区是卡片：.card-head（hero 图标 + 标题 + 提示）、.card-main（文件选择、sysinfo、
  上传按钮、.bar 进度、文件/大小/MD5/MTD 行）、.card-foot（注意事项 ul）。
- 多页面（index/settings/flash/backup/console + flashing/fail/reboot 程序页），gzip 后 26 个
  资源合计 70,858 B（i18n.js 18,468、style.css 8,195、main.js 9,336、theme.js 1,387，其余
  页面/脚本 33,472）；构建期用 node 压缩后 gzip，Content-Encoding: gzip 直发，U-Boot
  不解压。
- 主题 auto/light/dark + 强调色 + i18n；prefers-reduced-motion；上传后轮询状态并显示
  stage/进度；网页终端无鉴权（对本项目 LAN 暴露风险高，**不做**）。

本页只取“形态”：侧边栏品牌 + 分组导航、卡片三段式、上传 + 进度 + 注意事项；去掉
网页终端/UBI/SIMG/GPT/BL2（MT798x 专属），去掉多页面与 i18n（省体积，中文单语）。

## 2. 页面设计

单文件 uboot-port/failsafe/e2631-failsafe.html，HTML/CSS/JS 全内联，无外链、无字体、
无框架。五个标签与内容：

| 标签 | 内容 | 端点 |
|---|---|---|
| 系统状态 | 启动路径 rail、运行状态卡（stage/progress/crc32/摘要/结果/错误）、槽位卡（serial/version/identity/valid/intact/next + “下次启动此槽”）、引导区备份卡（CRC32 + 只读校验值 + 下载） | /status（1 s 轮询）、/slots、/boot、/backup |
| 固件更新 | 文件选择、大小、浏览器 SHA-256、槽选择 auto/0/1、解析目标/身份/守卫、仅校验/写入待命、进度与日志 | /firmware?mode=validate|write、/status |
| 引导区 | v1 上传流程（恰 655,360 B、只写 0x20000..0xC0000）、当前区域 CRC32、五步进度 | /flash?mode=validate|write、/status |
| 环境变量 | /env 只读表格 + 刷新；标注写入走串口 e2631env（白名单） | /env |
| 恢复出厂 | 说明（只擦 rootfs_data、overlay/配置丢失）、勾选 + confirm 双确认、进度、断电重启文案 | /factory?confirm=reset、/status |

实现细节：

- 纯 JS SHA-256（http://192.168.1.1 非安全上下文没有 WebCrypto），对 640 KiB 约 30 ms；
  已用空串/abc/长串与 0/1/55/56/63/64/65/1000/655360 字节随机数据对拍 node crypto，全部一致。
- 上传用 XMLHttpRequest 原始 body（xhr.send(file)），进度来自 xhr.upload.onprogress；
  POST 返回 result=staged|accepted 后 500 ms 轮询 /status。
- 摘要门控：设备返回 sha256= 必须等于浏览器值且 sha_match=ok，写按钮才可用；固件写还要求
  guard != refuse。
- 忙时禁用所有写/擦/上传按钮；不做自动重启；成功文案只用“断电重启后生效”，任何位置不提示
  reset（运行时按住 reset ≥5 s = factory reset；启动时按住 = 救援触发）。
- 深色模式跟随 prefers-color-scheme；窄屏侧边栏变顶栏、卡片单列；:focus-visible、
  键盘可达、prefers-reduced-motion。

## 3. 尺寸与确定性

| 版本 | 原始 | gzip | 上限 | 说明 |
|---|---|---|---|---|
| v1（task-73/75） | 9,216 B | 4,456 B | 6,144 B | 单卡片最小救援 |
| v2（task-81） | **34,069 B** | **10,962 B** | **32,768 B**（task-87） | 五标签 |

- gzip sha256 = 36d9a176766cdc4245c262c04b36460a14452243b63c72bf35bcfbe7a19e09bb；
  页面 sha256 = adc68a10fbf4eddd9f1a915f30488be1947022840c3a9ec4645c9b575758d7b1。
- 嵌入仍是确定性：tools/embed-failsafe.sh 用 gzip -9 -n，两次生成逐字节相同；符号
  e2631_failsafe_html_gz[] / e2631_failsafe_html_gz_len 未改。
- 页面占 gzip 预算 33.5%，余量 21,806 B；不复制上游 70,858 B 资源（约为其 15.5%）。

## 4. 摘要与文案安全（对照 Lead 修订）

- D3（只拒绝完整原厂槽）：页面“固件更新”的目标槽预览对 identity=vendor && intact 显示
  “拒绝”，其余（空/本固件/无法识别/损坏）允许写并提示“损坏或无法识别槽可重写（救砖）”。
  最终以设备 /firmware 返回的 guard 为准。
- D7（只用断电重启）：所有成功/注意事项文案均为“断电重启后生效”；页面没有 reset 提示，
  也没有自动重启动作。
- D8（不做牺牲写）：页面把“仅校验”和“写入待命”分开；真机验收走 task-86 的 validate +
  负例 + 净零 bootloader 流程，固件写只做 validate/负例，首次真实升级另行批准。

## 5. 本地离线预览

tools/mock-failsafe.mjs：node 单文件，无外部依赖；只监听 127.0.0.1（默认 8787，PORT 可改）；
读取真实页面文件，模拟 /status /slots /env /backup /boot /firmware /flash /factory；
/status 每次调用推进一步状态机（erase→blank/write→readback→compare→done）；不访问 flash、
不与设备通信、不写文件。

已执行的 mock 自测（curl）：页面 GET 200/34,069 B；/slots、/env、/status 正常；/backup 返回
655,360 B 与 X-E2631-CRC32/SHA-256 头；/flash?mode=validate 返回 sha_match=ok；缺 confirm 的
write 返回 400；带 confirm 的 write 经状态机到 stage=done result=ok；/firmware validate 返回
guard=ok + slot_target，write 返回 accepted 并推进到 done；/factory 推进到 done；/boot 返回
next_slot；坏摘要返回 400。

用法：

    node tools/mock-failsafe.mjs            # http://127.0.0.1:8787/
    PORT=8790 node tools/mock-failsafe.mjs

## 6. 验证证据

- bash tools/embed-failsafe.sh --check：raw 34,069 B，gzip 10,962 B（limit 32,768 B）。
- node tools/check-workflows.mjs：107 项 PASS（含页面必须存在的 xhr.send(file)、
  upload.onprogress、function sha256(、id="validate"、id="write"、/flash?mode=、/status、
  X-E2631-Confirm、655360、X-E2631-SHA256、sha_match、devsha，且无外链、无 script src、
  无 /reboot）。
- make check：全 PASS 或带理由 SKIP（本机缺 tree fork 的项按既有规则 SKIP）。
- 页面 JS node --check 通过；SHA-256 对拍 node crypto 全过（见 §2）。
- 页面字符串扫描：无 http(s) 绝对 URL、无 script src、无 link href、无 /reboot。

## 7. 限制与未覆盖

- 本轮未做真机/浏览器端到端：设备侧 C 端点由 task-84 实现，真机验收由 task-86 执行；页面在
  端点未实现时会显示连接/HTTP 错误，属预期。
- mock 是开发预览，不是验收依据；它不模拟坏块、掉电、单线程阻塞和真实 NAND 时序。
- 页面 gzip 门禁归 task-87/task-85（32768 B）；本任务未改门禁文件。
- 页面不提供 env 写入、网页终端、UBI/SIMG/GPT/BL2；这些按契约/风险明确不做。

## 8. 文件清单与复现

| 文件 | 变更 |
|---|---|
| uboot-port/failsafe/e2631-failsafe.html | v2 重写（34,069 B / gzip 10,962 B） |
| uboot-port/failsafe/README.md | v2 结构/协议/预览/验收说明；尺寸与 sha 记录 |
| tools/mock-failsafe.mjs | 新增本地离线预览服务器 |
| evidence/failsafe-redesign-20261128.md | 本文件 |
| docs/README.md | 索引行 |

复现：

    bash tools/embed-failsafe.sh --check        # 尺寸
    node tools/check-workflows.mjs              # 页面/README/嵌入门禁
    node tools/mock-failsafe.mjs                # 离线预览

## 9. 参考

- 上游：Yuzhii0718/bl-mt798x-dhcpd（master e4cf4dc4，GPL-2.0）；hanwckf/bl-mt798x（failsafe 源头）。
- 契约：evidence/e4-v2-contract-design-20261128.md（task-83，Lead 2026-11-28 复核）。
- 设计：docs/E4-多功能U-Boot设计-2026-11-27.md（§10 v2 契约摘要）。
- 门禁：tools/embed-failsafe.sh、tools/check-workflows.mjs、.github/workflows/uboot-build.yml。

## 10. v2.1 扩展（task-88，2026-11-28）

用户裁定（m12022）：“把功能都加上，不要再说安不安全了”。据此在 v2 五标签页面上扩展为
六标签，并补三个端点；**不设口令/鉴权门**，安全边界只写在契约 §15.5 与本节。

### 10.1 新增端点（契约 §15）

| 端点 | 语义 | 写所有者 |
|---|---|---|
| `POST /console?cmd=` | 单条 U-Boot 命令 + stdout 捕获（≤4 KiB，转义 `\n`/`\\`）；含 `;`/换行 400；无 stdin | 无（只转发） |
| `POST /env?key=&value=&confirm=write` | 仅 bootdelay/e2631_* 白名单；复用 e2631env 五步；vendor 键 403 | e2631env（不变） |
| `GET /backup?part=bootloader|tag|wifi|usercfg|defcfg` | 分区只读 + CRC32/SHA-256/Offset/Length/Part 头 | 无（只读） |

明确不做：UBI/SIMG（MT798x 存储布局专属）、I18N（中文单语）、网页终端 stdin 会话。

### 10.2 页面变更

- 六个标签：系统状态 / 固件更新 / 引导区 / 环境变量 / **串口台** / 恢复出厂；
  串口台在“系统”分组、环境变量之后。
- **环境变量**：只读总表 + 白名单编辑行（`bootdelay`、`e2631_*`）+ 新增变量行；
  “我已了解”勾选 + `confirm()` 双确认；按键逐个 `POST /env` 并轮询 `op=envwrite` 五步
  （diff→check→erase→write→readback→verify→done）；每键写前检查 op 避免误判上一任务完成。
- **串口台**：单命令输入、执行、输出区（`pre`）、历史 ≤20 条；客户端校验非空/≤256 B/无分号换行；
  执行前 `confirm()`；显示 stdout、exit、截断标记；无 stdin 提示。
- **引导区**：新增分区备份下拉（5 个分区）+ `读取校验值` + `下载分区`；备份卡从系统状态页移入；
  `GET /backup?part=`，显示偏移/长度/分区 CRC32/SHA-256。
- 侧边栏说明改为“bootloader/槽位/env 写入后都需要断电重启”（原先写“不写入 env”已失效）。

### 10.3 尺寸与门禁

| 项 | v2（task-81） | v2.1（task-88） |
|---|---|---|
| 原始 | 34,069 B | 44,003 B |
| gzip | 10,962 B（sha256 36d9a176…） | 13,773 B（sha256 496c5651…） |
| 页面 sha256 | adc68a10… | d6bff9225bee6b85f453f2e7b64f15b72eaa7106f8aebfbd6c79aca94b4d2ba2 |
| 预算 | 32,768 B | 32,768 B（未抬闸） |

`tools/embed-failsafe.sh --check` 输出：`raw 44003 B, gzip 13773 B (limit 32768 B)`；
确定性未变（`gzip -9 -n`，冻结符号未动）。

### 10.4 本地 mock 覆盖

`tools/mock-failsafe.mjs` 新增：

- `POST /env`：confirm 查询参数 + `X-E2631-Confirm` 头双查、白名单（bootdelay/e2631_*）、
  可打印 ASCII ≤128 B、vendor 键 403、缺失 confirm 400；写后 `/env` 可见，`/status` 走
  `envwrite` 五步（diff/check/erase/write/readback/verify/done）。
- `POST /console`：单命令校验（空/超 256/含 `;` 或换行 → 400），`version`/`printenv`/`md`/`help`
  返回假 stdout 与 exit，未知命令 exit=1；stdout 按契约转义。
- `GET /backup?part=`：5 个分区各自长度（655360/1M/1M/2M/2M）+ CRC32/SHA-256/Offset/Length/Part 头；
  未知 part 400；缺省 bootloader。

curl 实测：page 200/44003；`version` stdout+exit=0；`a;b` 400；`e2631_test=hello` accepted，
轮询到 readback；vendor 键 403；`/backup?part=tag` 200/1048576；未知 part 400。

### 10.5 复现与门禁

    bash tools/embed-failsafe.sh --check        # 44003 / 13773 / 32768
    node tools/check-workflows.mjs              # 107 PASS
    make check                                  # 通过（树 fork 缺省 SKIP 有说明）
    node tools/mock-failsafe.mjs                # 127.0.0.1 预览六标签

页面 JS 通过 `node --check`（抽出 `<script>`）；检查器必需的 v1 字符串全部保留，
禁项（外部 URL/`<script src=`/`<link href=`/`/reboot`）均未出现。

### 10.6 边界与后续

- 页面不提供 env vendor 键编辑；`/console` 不新增 MTD 写路径（命令仍由 e2631flash/fwslot 等所有者执行）。
- base-builder task-84 按契约 §15 实现 `/console`、`/env`、`/backup?part=`；本任务只改页面/契约/mock/文档。
- task-86 真机验收按 README §8 的 v2.1 补充项执行。
