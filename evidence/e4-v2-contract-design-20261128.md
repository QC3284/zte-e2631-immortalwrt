# E2631 救援 UI v2 模块契约设计（E4 v2）— 2026-11-28

> 状态：设计稿，供 Lead 拍板后由 base-builder（task-84）、页面（task-81）、闸门/构建（task-85）、真机验收（task-86）接力。
> 本文件只定义契约与边界，不含代码；所有地址/字段/错误文本以实现和真机测量为准，变更必须回写本文。
> **2026-11-28 Lead 复核：接受本契约并修订 4 项**（D1 页面闸门改由 task-87 先落地、D3 只拒绝完整 vendor 目标槽、D7 成功文案只用断电重启、D8 真机验收改为首次真实升级）；修订已并入正文与 §13。
> 前序文档：[docs/E4-多功能U-Boot设计-2026-11-27.md](../docs/E4-多功能U-Boot设计-2026-11-27.md)（v1 设计，`/flash` 契约仍然有效）、[evidence/e4-rescue-acceptance-plan-20261127.md](e4-rescue-acceptance-plan-20261127.md)（v1 验收方案）。

## 0. 一页结论

1. **v2 在 v1 的救援页上增加四个只读/写模块**：固件更新（槽位）、引导区备份、环境变量只读、恢复出厂（擦 overlay）；串口网页终端不做。
2. **固件写入的默认目标 = e2631boot 本次会启动的槽**（按版本头 serial 取大者，见 `e2631_pick_slot()`），页面可以显式改槽；写完把目标槽的 serial 重新盖章为 `max_serial()+1`，因此写入的槽自动成为下次启动槽。
3. **新增一个固件写入口 `/firmware`，与 `/flash` 分离**：`/flash` 继续是 bootloader 区（mtd0 `0x20000..0xC0000`）唯一入口、五步写、净零验收可复现；`/firmware` 只写 slot0/slot1，语义逐条对齐 Linux 侧 `e2631-fwslot`（校验、守卫、擦整槽、写 body、写版本头、回读校验、失败擦头回退）。**页面不得做第三个写入实现**。
4. **写路径所有者固定**：bootloader = `e2631flash`（现有五步）；firmware slot = 新增 `e2631fwslot`（语义端口，golden 向量对拍）；overlay = 新增 `e2631factory`（只擦 `rootfs_data` + 全 FF 回读，无文件系统逻辑）；env = `e2631env` 白名单写（patch 0017，v2 页面不暴露写）；其余一律拒绝。
5. **单线程、单飞行任务**：同一时刻只允许一个上传/擦写/回读任务；`/status` 的每次 GET 推进一步有界工作（≤16 个擦除块或 ≤2 MiB 编程/回读），页面 500 ms 轮询。
6. **页面 gzip 预算 32 KiB**（v1 为 6,144 B 的闸门）；闸门提升由 **task-87**（pkg-release，2026-11-28 起进行中）一次性完成并留下构建证据，页面在 task-87 落地后即可提交，**不再等 task-85**。
7. **安全**：仅 lan1、无 TLS、无登录；写端点强制自定义头（`X-E2631-SHA256`、`X-E2631-Confirm`），浏览器跨站请求会因非简单头触发预检而被拒（CSRF 缓解）；`/firmware` 拒绝覆盖**识别为 vendor 且完整的**目标槽，UNKNOWN/CORRUPT 槽可写（救援核心用途）；`/factory` 双确认。

端点总表（新= v2 新增，旧= v1 保留）：

| 方法/路径 | 状态 | 作用 |
|---|---|---|
| `GET /` | 旧，改版 | 单页 gzip，侧边栏 + 标签页 |
| `GET /status` | 旧，扩展 | 状态快照（v1 键保留，新增 op/slot/guard/bytes 等） |
| `POST /flash?mode=validate\|write` | 旧，**不动** | bootloader 区 mtd0 `0x20000..0xC0000` 校验/写入 |
| `GET /slots` | 新 | 两个槽的 serial/版本/身份/完好性 + next |
| `GET /env` | 新 | 环境变量只读文本 |
| `GET /backup` | 新 | 下载 mtd0 `0x20000..0xC0000`（655,360 B）+ CRC32 头 |
| `POST /firmware?mode=validate\|write&slot=auto\|0\|1` | 新 | 固件包校验/写槽 |
| `POST /boot?slot=0\|1` | 新 | 本次启动改槽（RAM env，不写 flash） |
| `POST /factory?confirm=reset` | 新 | 擦除 `rootfs_data`（恢复出厂） |

## 1. 输入与边界

### 1.1 用户/Lead 已定

- 固件更新进入救援 UI：**做**；默认写“本次会启动的槽”，页面可选槽。
- 触发方式：**按住 reset 或 mesh 任一键上电即进救援**（task-82 patch 0035 实现；本契约不涉及 C 侧按键代码）。
- 串口 web 终端：**不做**（无认证暴露 console 不可接受）。
- 页面形态照 `Yuzhii0718/bl-mt798x-dhcpd` 的 failsafe UI（侧边栏 + 卡片 + 上传 + 进度 + 注意事项），但不搬资产、不引外部资源，单文件 gzip。
- 页面 gzip 预算 32 KiB；U-Boot 载荷上限 653,312 B；CI 闸门当前 645,120 B。

### 1.2 v1 已交付且 v2 必须保持

- `/flash` 的请求/响应/校验/写入/摘要契约与 v1 完全一致（见 E4 设计 §4.2、本仓 `uboot-port/failsafe/README.md`）；task-75 的零净验收脚本与 task-79 的写验收证据继续有效。
- 页面永不自动重启；成功文案**只用「断电重启后生效」**，不得提示按 reset（Linux 运行时按住 reset ≥5 s = factory reset；启动时按住 reset = 救援触发，提示会有危险）。
- 上传摘要：页面发送 `X-E2631-SHA256`（整个文件 64 位小写十六进制），设备回显 `sha256=`、`browser_sha256=`、`sha_match=`；摘要一致前不启用写入。

### 1.3 设备事实（本契约的硬输入，2026-11-28 真机只读核对）

| MTD | 名称 | 偏移 | 大小 | 备注 |
|---|---|---|---|---|
| mtd0 | bootloader | 0x0000000 | 0x100000 | `/flash` 只写 `0x20000..0xC0000`（0xA0000） |
| mtd1 | tag | 0x0100000 | 0x100000 | ro，含 MAC nvmem |
| mtd2 | wifi | 0x0200000 | 0x100000 | — |
| mtd3 | usercfg | 0x0300000 | 0x200000 | ro |
| mtd4 | defcfg | 0x0500000 | 0x200000 | ro |
| mtd5 | slot0 | 0x0700000 | 0x1C00000 | 槽 0；版本头在槽内 `+0x1500000`（512 B） |
| mtd6 | slot1 | 0x2300000 | 0x1C00000 | 槽 1；同上 |
| mtd7 | rootfs | 0x2700000 | 0x1100000 | 运行槽的 squashfs 窗口，ro |
| mtd8 | rootfs_data | 0x3360000 | 0x4A0000 | rootfs 尾部切出的 overlay（jffs2），设备上 **没有** 名为 factory 的分区 |
| mtd9 | slot1-header | 0x3800000 | 0x20000 | 槽 1 版本头独立分区（窗口） |
| mtd10 | userdata | 0x3F00000 | 0x2F00000 | 47 MiB，Linux 用；救援不用 |

- 槽内布局（kit `target/image/Makefile.e2631` / DTS）：`+0x0` 32 B slot marker；`+0x20` legacy uImage；`+0x400000` rootfs（固定，cspboot 以 `ceil(kernel_size/erasesize)` 找根）；`+0x1500000` 512 B 版本头；槽跨度 0x1C00000。
- 版本头字段（`e2631-fwslot.c`）：`H_VERSION 0x10`、`H_KERNEL_SIZE 0x34`、`H_KERNEL_FILEOFS 0x38`、`H_KERNEL_CRC 0x3c`、`H_FS_SIZE 0x40`、`H_FS_FILEOFS 0x44`、`H_FS_CRC 0x48`、`H_SLOT0 0x4c`、`H_SLOT1 0x5c`、`H_PRODUCT 0x6c`、`H_BOOT_INCLUDED 0x8c`、`H_CRC 0xa4`、`H_BUILD 0xa8`、`H_INNER_MAGIC 0xf4`、`H_SLOT_START 0x1f0`、`H_SERIAL 0x1f4`、`H_NEW 0x1f8`、`H_CRC2 0x1fc`。
- 固件包格式：`[0x0:0x14 outer][0x14:0x214 512 B version header][0x214: body]`；当前产物 22,020,628 B = 0x1500214；body = 0x1500000（uImage 在 body 内 `+0x20`，rootfs 在 `+0x400000`）。
- `e2631boot` 选槽：`serial` 大者胜，slot0 的 0 视为更小，平局取 slot0（`e2631_pick_slot()`，与 cspboot 等价）；选中槽 uImage 坏时 class-1 回退另一槽一次（patch 0016）。
- 当前救援构建（patch 0034）`u-boot.bin` = 365,872 B；载荷上限 653,312 B、CI 闸门 645,120 B → 余量 279,248 B（闸门） / 287,440 B（硬上限）。

### 1.4 v2 明确不做

- 不做 web 串口终端、不做 UBI/SIMG/GPT/ATF/FIP/NMBM、不做 MMC/EFI/FAT 依赖、不做多网口、不做 TLS/登录、不做 i18n（中文单语）、不做自动重启、不做 env 写页面、不做 bootloader 之外的“裸 flash 编辑”。
- 不在救援 UI 里实现 PPE/交换 VLAN/多端口逻辑；只用一条 lan1（switch port 2、PHY 12）。

## 2. 通用协议约定

### 2.1 服务与请求

- 服务：lan1 静态 `192.168.1.1/24` + DHCP 池 `192.168.1.100+`，HTTP `:80`，单线程；页面仅从 `GET /` 获取。
- HTTP/1.x；请求头 ≤ 1,024 B；方法只接受 `GET`/`POST`；未列出的路径/方法 → `404`/`405`，响应体仍为 `result=error` 形状。
- 请求头名称大小写不敏感（`e2631_http.h` 已实现）；同名头取第一个；不支持 `Transfer-Encoding: chunked`，`POST` 必须带数值 `Content-Length`；超长/非法长度 → `400`。
- 响应一律带 `Content-Length`、`Connection: close`；API 响应 `Content-Type: text/plain`；页面 `GET /` 为 `text/html; charset=utf-8` + `Content-Encoding: gzip`；`GET /backup` 为 `application/octet-stream`。
- 语言：所有错误文本为**短 ASCII**（便于页面直接显示与串口日志），页面负责翻译成中文提示；错误文本不得含换行、控制字符。

### 2.2 状态与错误形状

- 成功：`200`，body 至少包含 `result=ok`（立即完成）或 `result=accepted`（已接受、异步写）。
- 失败：`400`（请求/校验/守卫拒绝）、`409`（忙）、`500`（擦写/读回失败）；body 为：`result=error` + `\n` + `error=<short>` + `\n`。
- 所有 `key=value` 行以 `\n` 结束，键名小写、`_` 分隔；未知键页面必须忽略（向前兼容）。
- `/status` 的 v1 键（`stage/progress/crc32/sha256/browser_sha256/sha_match/result/error`）保持含义不变；v2 只做**追加**。

### 2.3 单飞行与忙

- 同一时刻最多一个“重任务”（固件上传/写、bootloader 上传/写、factory 擦除/回读）；重任务进行中，新的写/擦请求返回 `409` + `error=busy`。
- `GET /status`、`GET /slots`、`GET /env`、`GET /backup` 在重任务期间：`/status` 负责推进状态机（见 §7），其余只读端点允许但不得重置任务；页面在忙时禁用其它标签页的写按钮。
- 上传失败/超时/客户端断开：任务回到 `idle`，已接收的暂存区作废；页面可整包重传（校验幂等；写只在完整校验并收到明确 `mode=write` 后才开始）。

### 2.4 摘要与确认头

- `X-E2631-SHA256: <64 lowercase hex>`：对**整个上传文件**的 SHA-256。`mode=write` 必填；`mode=validate` 建议填（缺省则设备回报 `sha_match=absent`）。设备只把它当作“浏览器声明值”，用于传输完整性与页面门控；**权威校验仍是包内 CRC 和几何检查**。
- `X-E2631-Confirm: write|reset`：写槽必须 `write`；恢复出厂必须 `reset`。缺失/值不符 → `400`，不擦写。
- 跨站缓解：上述自定义头 + `X-E2631-SHA256` 使跨源请求变成非简单请求，浏览器会先发 `OPTIONS` 预检；本服务不实现 CORS，预检失败即拒。服务端另要求 `Origin` 缺省或同源（可选加固）。

### 2.5 时间与超时

- 页面轮询 `GET /status` 每 500 ms 一次；写/擦任务页面总超时 600 s（单次 POST 已返回 `accepted`，不会占住连接）。
- 大文件 `POST` 的传输时间由浏览器/主机决定；设备端不设上传超时，但只接受一个连接，断开即作废。`mode=validate` 在接收完成后**同步**校验再回 200/400（22 MB 的 SHA-256+CRC 在最坏情况下数秒，页面需显示“校验中”并禁用重复提交）。
- `/backup` 传输 655,360 B，分块发送（见 §3.4）。

## 3. 端点契约

### 3.1 `GET /`

- 返回页面单文件 gzip；`Content-Encoding: gzip`；`Content-Type: text/html; charset=utf-8`。
- 页面内不得有外部 URL、外部字体、CDN、`<script src>`、`<link href>`；gzip 后 ≤ 32,768 B（task-85 抬闸后由 `tools/embed-failsafe.sh --max 32768` 断言）。
- 页面可轮询 `/status`、`/slots`、`/env`，并调用 §3.3/§3.5–§3.8。

### 3.2 `GET /status`

v1 键（保持不变）：`stage`、`progress`（0..100）、`crc32`、`sha256`、`browser_sha256`、`sha_match`（ok|mismatch|absent）、`result`（staged|ok|accepted|error）、`error`。

v2 追加键：

| 键 | 取值 | 含义 |
|---|---|---|
| `op` | `idle`/`flash`/`firmware`/`factory` | 当前/最近任务类别（`flash` = v1 bootloader 写） |
| `mode` | `validate`/`write` | 最近请求的模式 |
| `slot` | `auto`/`0`/`1` | 请求里的选择值 |
| `slot_target` | `0`/`1`/空 | 解析后的目标槽 |
| `slot_target_identity` | `empty`/`vendor`/`ours`/`unknown` | 目标槽身份 |
| `guard` | `ok`/`weak`/`refuse` | 写入守卫结论（见 §5.2） |
| `guard_reason` | 短 ASCII | 守卫拒绝/降级原因；`ok` 时为空 |
| `bytes_total` | 十进制 | 本任务总字节（上传长度或擦除长度） |
| `bytes_done` | 十进制 | 已完成字节 |
| `written_serial` | 十进制/空 | 写成功后目标槽新 serial |
| `version` | 字符串 | `U-Boot <version-string>`（来自 `version_string()`，页面显示） |
| `next_slot` | `-1`/`0`/`1` | 按 serial 应启动的槽（-1=都不可启） |
| `next_reason` | `serial`/`only-slot`/`none` | 选槽原因 |
| `slot0_valid`/`slot1_valid` | `0`/`1` | 版本头+CRC1 合法 |
| `slot0_intact`/`slot1_intact` | `0`/`1` | 版本头记录的 kernel/fs CRC 回读一致 |
| `slot0_identity`/`slot1_identity` | `empty`/`vendor`/`ours`/`unknown` | 身份判定同 `e2631-fwslot` |
| `slot0_serial`/`slot1_serial` | 十进制/空 | 版本头 serial |
| `slot0_version`/`slot1_version` | 字符串/空 | 版本头 `H_VERSION`（≤32 字节，空格转义见下） |
| `slot0_header_at`/`slot1_header_at` | `0x...`/空 | 版本头所在槽内偏移 |
| `slot1_header_partition` | `mtd9`/空 | 设备事实注记，页面显示用 |
| `bootloader_region_crc32` | `0x...` | 当前 mtd0 `0x20000..0xC0000` 的 CRC32（`/backup` 同源） |

- 字符串值只允许可打印 ASCII；空白/等号替换为 `_`；空值输出 `key=`。
- 页面不得依赖键顺序；未知键忽略。

### 3.3 `GET /env`

- 返回当前 env 的只读快照：每行 `key=value`，顺序为 U-Boot env 遍历顺序；包含 `bootcmd`、`bootargs`、`memsize`、`versioninfo`、`ethaddr`、`ipaddr`、`serverip`、`e2631_*` 等，**不筛选**（不含敏感项；只读）。
- 首行可含 `env_size=<used>/<total>` 便于页面显示容量（可选键，页面忽略亦可）。
- 任何情况下不回写 flash env；页面只有“刷新”按钮。
- `Content-Type: text/plain; charset=utf-8`。

### 3.4 `GET /backup`

- 返回 mtd0 `0x20000..0xC0000`（655,360 B）原始数据，`Content-Type: application/octet-stream`。
- 响应头：`Content-Length: 655360`、`Content-Disposition: attachment; filename="e2631-uboot-region.bin"`、`X-E2631-CRC32: 0x%08x`（对返回区间）、`X-E2631-SHA256: <64 hex>`（对返回区间，可选但本契约要求提供）、`X-E2631-Offset: 0x20000`、`X-E2631-Length: 0xA0000`。
- 实现：先读 flash 计算 CRC32+SHA-256（≤1 s），再分块发送；每块 ≤16 KiB，`mtk_tcp_send_data()` 的 `DATA_SENT` 回调驱动下一块；块缓冲必须常驻到 ACK。
- 失败：`500` + `result=error error=backup read failed`；`/status` 不变（只读任务不占用飞行锁，但同一时刻只允许一个 `/backup` 传输）。
- 页面：显示 CRC32/SHA-256 与大小；`<a download>` 触发；不自动写入。

### 3.5 `GET /slots`

- 文本快照；字段与 `/status` 的 `slotN_*`、`next_slot`、`next_reason` 相同（可裁剪 `slot0_*` 命名相同），另加：
  - `slot0_partition=mtd5`、`slot1_partition=mtd6`；
  - `slot0_span=0x01c00000`；
  - `slot1_header=0x3800000`（设备注记）。
- 页面“系统状态/固件更新”标签均可用它渲染槽卡片；无副作用。

### 3.6 `POST /boot?slot=0|1`

- 作用：设置 **本次（RAM）** 启动覆盖 `e2631_next_slot=<0|1>`，不写 flash、不写 env 存储。
- 请求：无 body（`Content-Length: 0`）；`slot` 必须显式 0/1。
- 成功：`200 result=ok next_slot=<slot>`；失败：`400 result=error error=bad slot`。
- 语义边界：
  - 覆盖只在当前 U-Boot 会话内有效；断电/`reset` 后失效，回到 serial 选择。
  - 页面必须提示：“按 Ctrl-C 退出救援后运行 `e2631boot` 生效（仅本次）”；页面不自动运行 `e2631boot`、不自动重启。
  - 目标槽必须是 `valid && intact`；否则 `400 error=slot not bootable`。
- 依赖（task-84）：`e2631boot` 在 `e2631_pick_slot()` 之后读取 `e2631_next_slot`，合法则覆盖 `active`（仍走 class-1 回退：目标槽 uImage 坏时回退另一槽并打印）；非法值忽略并打印。

### 3.7 `POST /firmware?mode=validate|write&slot=auto|0|1`

#### 3.7.1 请求

- `Content-Length` = 固件包总长；必须 ≥ `0x214` 且 ≤ `0x1BE0214`（= body 上限 `0x1BE0000` + 包元数据 `0x214`；见 §6）。当前包 22,020,628 B；本契约不把该长度写死，设备按包内 `H_FW_SIZE` 判定 body。
- `X-E2631-SHA256`：写必填；校验建议。
- `X-E2631-Confirm: write`：写必填。
- `slot=auto`（默认）：目标 = `/status` 的 `next_slot`（按 serial）；显式为 `0`/`1`。
- Body 原样上传（非 multipart），接收即写入暂存区 `0x46100000`（§6）；接收超过上限 → `400`，已收字节作废；`Content-Length` 与实收不符 → `400`。

#### 3.7.2 `mode=validate`

接收完成后同步执行 §5.1 全部检查 + §5.2 守卫预检（不擦写），返回：

```
result=ok
sha256=<设备计算值>
browser_sha256=<请求头值或空>
sha_match=ok|absent
crc32=0x<整个包的 CRC32>
body_len=0x<包内 body 长度>
slot_target=0|1
slot_target_identity=empty|vendor|ours|unknown
guard=ok|weak|refuse
guard_reason=<短文本或空>
```

失败：`400` + `result=error error=<校验原因>`；若摘要不符且其它检查都过，优先报 `sha256 mismatch`。不修改 flash、不改变 `/status.stage`（保持 `idle`；v1 兼容行为）。

#### 3.7.3 `mode=write`

前置：validate 全部通过 + `X-E2631-SHA256` 与设备计算一致 + `X-E2631-Confirm: write` + 守卫不是 `refuse`。任一失败 → `400`，**不擦写**。

通过后设备返回 **立即** `200`：

```
result=accepted
sha256=<设备计算值>
slot_target=0|1
written_serial=<将要盖章的 serial>
```

随后状态机在 `/status` 轮询下推进（§7）：`stage=erase → write → readback → compare → done`；完成时 `result=ok`、`stage=done`、`crc32=`（设备对包 body 的 CRC32）、`written_serial=`。

写入步骤（必须与 e2631-fwslot 语义一致）：

1. 坏块预检：扫描 body 覆盖的全部擦除块 + 版本头块；发现坏块 → `400 error=target slot has a bad block`，不擦。
2. 擦除整个目标槽（每个好块；坏块跳过），`stage=erase`。
3. 按包 body 顺序写：每个擦除块 128 KiB（尾块 0xFF 填充），坏块跳过但保证固定偏移（rootfs `+0x400000`）不被移动——坏块预检已保证这段无坏块。
4. 在 body 之后的下一个好块写 512 B 版本头：拷贝包内头、`H_SLOT_START=slot_start[target]`、`H_SERIAL=max_serial()+1`（若包内头 serial 更大则用包内值）、`H_NEW=1`、`H_CRC2=crc32(header[0:0x1fc])`；头块其余 0xFF。
5. 回读：`slot_scan` 找头 + `slot_verify`（kernel/fs CRC 与 body 区域 CRC 对拍）；失败 → 擦掉目标槽版本头（让启动留在另一槽）→ `500 error=verify failed, header erased`。
6. 全部成功 → `stage=done result=ok`；串口打印 `firmware: slotN serial=S written, crc32=0x...`。

失败/掉电语义：目标槽在擦除后即失去旧版本头，因此任何中途失败都回退到另一槽（守卫保证它 `known && intact`）；这是设计上的安全网，页面必须显示“失败后启动仍在另一槽”。**不自动重启、不自动重试**。

#### 3.7.4 只拒绝覆盖「完整可用的 vendor 系统」

- 目标槽 **identity=vendor 且 intact（版本头/内核/rootfs CRC 全部回读一致）** → `guard=refuse`，`400 error=refusing to overwrite a working vendor system`。这是唯一一种“覆盖会把最后一次原厂回退毁掉”的情况；该操作只在 Linux 侧 `e2631-fwslot install --replace-other-system` 做，并先备份 1 MiB。
- 目标槽为 `empty`/`ours` → 允许。
- 目标槽为 `unknown`、`vendor 但损坏`、无有效版本头、或内容不可识别 → **允许写**：救援模式的核心用途就是重写砖掉的槽。页面必须显示“目标槽内容无法识别/已损坏，将被覆盖”。

### 3.8 `POST /factory?confirm=reset`

- 作用：擦除 `rootfs_data`（设备事实：按名 `rootfs_data`，偏移 `0x3360000`、长度 `0x4A0000`、擦除块 `0x20000`，共 37 个擦除块，坏块跳过），然后回读校验全 `0xFF`；**不写任何数据**。
- 请求：`Content-Length: 0`；必须 `confirm=reset` **且** `X-E2631-Confirm: reset`；否则 `400`。
- 设备必须先按名字找到 `rootfs_data` 并核对 `offset==0x3360000 && size==0x4a0000`；不匹配 → `400 error=rootfs_data layout mismatch`，**绝不**改擦 mtd7。
- 返回：`200 result=accepted`（异步）；`/status`：`op=factory`、`stage=erase → blank → done`；完成 `result=ok`。
- 失败：`500 error=erase failed` / `blank check failed`；擦除不完整时保持 `error`，不再写。
- 语义：下次 Linux 启动时 jffs2 发现空 flash 会重新格式化，于是恢复出厂；页面文案必须写明“overlay/配置将丢失；成功后断电重启；失败后启动仍可进 Linux（只影响 overlay）”。
- 掉电：擦除中途掉电 → overlay 损坏/半空，Linux 可能重新格式化；不触碰 squashfs 与槽位，不是砖路径。

### 3.9 `POST /flash?mode=validate|write`（v1，保留）

- 路径、头（`X-E2631-SHA256`/`X-E2631-Confirm: write`）、校验（655,360 B、magic、载荷长度、0xFF 填充、banner、摘要）、五步写、`/status` 键全部保持 v1 行为；实现仍是 `e2631flash`（唯一 bootloader 写入口）。
- 页面“引导区”标签复用它；**v2 不新增 bootloader 写入路径**。

## 4. 写路径所有者矩阵（硬约束）

| 写入目标 | 唯一所有者 | 状态 | 约束 |
|---|---|---|---|
| mtd0 `0x20000..0xC0000`（bootloader 镜像区） | `e2631flash`（`board/zte/zxhn-e2631/e2631flash.c` 五步 job API） | 现有，不改 | `/flash`；固定偏移/长度；secondboot `0x0..0x20000`、env `0xC0000..0xE0000`、保留区 `0xE0000..0xFFFFF` 永不触碰 |
| slot0/slot1 固件槽 | 新增 `e2631fwslot`（task-84） | 新 | 只写槽；语义对齐 `package/e2631/e2631-fwslot/src/e2631-fwslot.c`；不写 mtd0/env/userdata |
| `rootfs_data`（overlay） | 新增 `e2631factory`（task-84） | 新 | 只擦这一段（按名核对偏移/长度）；无文件系统逻辑；绝不写 mtd7 |
| env 区 `0xC0000..0xE0000` | `e2631env`（patch 0017 白名单写） | 现有，页面不暴露 | v2 页面只读 `/env`；写路径保持串口/白名单 |
| 其它任何范围（mtd1/2/3/4/7/9/10、userdata、保留区） | 无 | — | 一律拒绝 |

**禁止出现第三个固件槽写入实现**：Linux 侧 `e2631-fwslot` 继续是 Linux 的唯一实现；救援侧 `e2631fwslot` 是它的语义端口，通过 golden 向量对拍（§5.5）保证不漂移。

## 5. 固件包校验与写入语义

### 5.1 校验顺序（必须在第一次擦除之前全部通过）

| # | 条件 | 拒绝错误文本（`error=`） |
|---|---|---|
| 1 | `len >= 0x214` | `package too small` |
| 2 | `outer_magic[0:16]` == `99 99 99 99 44 44 44 44 55 55 55 55 aa aa aa aa` | `bad outer magic` |
| 3 | 头部偏移 `hdr_ofs = 0x14 + rd32(0x10)`；`body_ofs = hdr_ofs + 0x200 <= len` | `truncated header` |
| 4 | `H_INNER_MAGIC` == `33x4 66x4 99x4 ccx4` | `bad version header magic` |
| 5 | `crc32(header[0:0xa4]) == rd32(H_CRC)` 且 `crc32(header[0:0x1fc]) == rd32(H_CRC2)` | `header CRC mismatch` |
| 6 | `H_PRODUCT` 前 15 B == `ZXHN E2631 V1.0.0` | `package is not for this product` |
| 7 | `rd32(H_BOOT_INCLUDED) == 0` | `package wants to update the bootloader` |
| 8 | `rd32(H_FW_SIZE) == len - body_ofs` | `body size mismatch` |
| 9 | `rd32(H_SLOT0) == 0x00700000 && rd32(H_SLOT1) == 0x02300000` | `package declares different slot addresses` |
| 10 | `koff+ksz <= len` 且 `foff+fsz <= len` | `region outside package` |
| 11 | `crc32(pkg[koff..koff+ksz]) == rd32(H_KERNEL_CRC)` | `kernel CRC mismatch` |
| 12 | `crc32(pkg[foff..foff+fsz]) == rd32(H_FS_CRC)` | `rootfs CRC mismatch` |
| 13 | body 覆盖的擦除块范围无坏块、版本头块无坏块 | `target slot has a bad block` |
| 14 | `X-E2631-SHA256`（写必填）与设备 SHA-256 一致 | `sha256 mismatch` / `sha256 header required` |

几何补充：`body_len <= slot_span - 0x20000`（写 body 后还要一个头块）；`koff/ksz/foff/fsz` 来自版本头；当前包 `koff=0x234`（uImage 头）、`foff=0x400214`。

### 5.2 守卫规则（写前判定，validate 也返回）

- 目标槽（`auto` → `next_slot`；显式 0/1）：
  - `empty` / `ours` → 允许；
  - `vendor` 且 `intact` → `guard=refuse`（唯一拒绝；见 §3.7.4）；
  - `unknown` / `vendor` 但损坏 / 无有效版本头 / 内容不可识别 → 允许（砖槽救援），页面警示内容将被覆盖；
  - 目标槽 MTD 设备本身不存在 → `refuse`。
- 另一槽（fallback）：
  - `known && intact && identity==vendor` → `guard=ok`（与 Linux `upgrade_guard` 一致）；
  - `known && intact && identity in {ours, unknown}` → `guard=weak`：允许写，但页面必须显示“回退槽不是原厂镜像”警告；写完成后若目标槽坏，回退目标是这个镜像而非原厂；
  - 不可读/不完整 → `refuse`（除非将来引入显式 override，v2 不做）。
- `auto` 且 `next_slot == -1`（两槽都不可启）→ `refuse`。

### 5.3 serial 盖章

- `serial = max(两槽当前 serial) + 1`；若包内 `H_SERIAL` 更大，取包内值（防厂商侧 serial 便宜）。
- 写头时 `H_SLOT_START = slot_start[target]`、`H_SERIAL=serial`、`H_NEW=1`、`H_CRC2 = crc32(header[0:0x1fc])`；`H_CRC`（覆盖 `[0:0xa4]`）不动。
- 结果：写入槽在下一次 `e2631_pick_slot()` 中必胜出（serial 最大），页面与 `/status` 报 `written_serial`。

### 5.4 失败/掉电

- 擦除后目标槽无有效版本头 → 启动自动留在另一槽（cspboot 与 e2631boot 同规则；e2631boot 另有 class-1 回退）。
- 回读校验失败 → 擦掉目标槽版本头再报错（防止指向半写镜像），页面显示“回退启动另一槽”。
- 不自动重启、不自动重试、不改 env。

### 5.5 与 Linux 侧的一致性（对拍）

- 语义单一来源：`package/e2631/e2631-fwslot/src/e2631-fwslot.c`（Linux）。救援侧 `e2631fwslot` 必须复刻其校验顺序/错误类别/守卫/盖章/擦写顺序；**不得新增语义**。
- 对拍夹具（task-84 交付，CI 可跑）：
  1. 合法包（当前 22,020,628 B 产物）→ validate 通过；
  2. 16 B outer magic 破坏、头部 CRC1/CRC2 破坏、product 破坏、`H_BOOT_INCLUDED=1`、body size±1、kernel CRC 破坏、rootfs CRC 破坏 → 分别命中 §5.1 的对应错误类别；
  3. 版本头盖章：给定两槽 serial（如 7/12）与包内 serial（0/999）→ 期望 `written_serial` 与 `H_SLOT_START/H_CRC2` 字节序列与 Linux 侧算法一致；
  4. 守卫矩阵：目标 vendor/ours/empty/unknown × 另一槽 vendor/ours/unknown/坏 → 期望 `ok/weak/refuse`。
- `tests/native` 的 `g_native_sync` 继续保证 Linux 侧树内/测试副本一致；U-Boot 侧对拍用同一套 golden 向量，不要求源码逐字节相同（两套 API 不同）。

## 6. RAM 与缓冲布局

救援 U-Boot 运行时的固定占用（既有，勿动）：

| 地址 | 大小 | 用途 |
|---|---|---|
| `0x40000000..0x40007FFF` | 32 KiB | ATAGS / boot_params 区（`E2631_ATAGS_ADDR=0x40000000`，kernel 入口 `0x40008000`） |
| `0x40008000..0x40407FFF` | 4 MiB | Linux kernel 加载/解压窗口（`E2631_KERNEL_LOAD_ADDR`、`E2631_KERNEL_MAX=4 MiB-marker`） |
| `0x42000000..` | 不定 | `e2631boot` 的 legacy uImage 暂存（`CONFIG_SYS_LOAD_ADDR`） |
| `0x43000000..` | 不定 | 上游/网络引导暂存（保留） |
| `0x44000000..0x440FFFFF` | 1 MiB | `e2631flash` 的 flash→flash bounce buffer |
| `0x45000000..0x45FFFFFF` | 16 MiB | U-Boot 网络 DMA arena（`e2631net`） |
| `0x46000000..0x460FFFFF` | 1 MiB | v1 `/flash` 上传缓冲（`E2631_RESCUE_IMG_ADDR`） |
| `0x47F00000..` | 载荷上限 | U-Boot 链接地址/镜像（运行时会搬到高端，`0x4FF...`） |

v2 新增/复用的缓冲：

| 地址 | 大小 | 用途 |
|---|---|---|
| `0x46100000` | `E2631_FW_STAGE_MAX = 0x1C00000`（29,360,128 B） | `/firmware` 上传暂存（包原样，含 outer+header；≥ body 上限 `0x1BE0000` + `0x214`，留 2 MiB 余量） |
| `0x46100000..` 顶部 | — | 暂存区实际使用长度 = 本次 `Content-Length`（当前包 22,020,628 B，结束于 `0x47600214`，距 U-Boot 链接基址 0x47F00000 余 5 MB） |
| 堆/Malloc | ~256 KiB | 擦除块缓冲（128 KiB）+ 版本头块（128 KiB）+ 页响应缓冲 |
| `GET /backup` 块缓冲 | 16 KiB | 常驻到 TCP ACK 的发送块 |

编译期断言（task-84 必须加）：

- `E2631_FW_STAGE_ADDR >= 0x46100000`（不与 v1 1 MiB 缓冲/网络 arena/内核窗口重叠）；
- `E2631_FW_STAGE_ADDR + E2631_FW_STAGE_MAX <= 0x47F00000`（不压 U-Boot 链接镜像；实际运行时镜像已搬到高端，但保持余量）；
- `E2631_FW_STAGE_MAX == 0x1C00000`（≥ body 上限 `0x1BE0000` + 包元数据 `0x214`）；
- `E2631_FW_STAGE_ADDR > CONFIG_SYS_LOAD_ADDR`、`>= 0x45000000 + 0x1000000`（与 v1 静态断言同风格）。

为何不流式写：U-Boot 单线程、无中断；先整包进 RAM 再做全部校验（CRC/SHA/几何）最简单也最安全（擦之前知道整包好坏）。22 MB 暂存在 30 MB 空闲区内（`0x46100000..0x47EFFFFF` = 0x1E00000）；若未来镜像逼近上限，再评估“边收边写”的流式方案（需要先校验头、后按块写，本契约不采用）。

## 7. 状态机与 `/status` 扩展

### 7.1 任务与阶段

| `op` | `stage` 序列 | `progress` 节点 |
|---|---|---|
| `flash`（v1） | `staged → erase → blank → write → readback → compare → done` | 0/10/30/45/80/90/100（保持不变） |
| `firmware` validate | 无异步阶段（同步返回），`stage` 保持 `idle` | — |
| `firmware` write | `erase → write → readback → compare → done` | 0(start)/35(after erase)/85(after write)/90/100 |
| `factory` | `erase → blank → done` | 10/60/100 |
| `idle` | — | 0 |

### 7.2 推进规则

- 每个 `GET /status` 最多推进一个“有界单元”：擦除 ≤8 个块（1 MiB），编程/回读 ≤16 个块（2 MiB）；单个单元耗时目标 < 200 ms，保证页面 500 ms 轮询节奏。
- 首次进入写任务后，保留 `E2631_RESCUE_DWELL_MS=400 ms` 的“先返回 accepted 再动手”节奏（v1 行为）。
- `result`：`accepted`（已接受未完成）→ `ok`（完成）或 `error`；`crc32` 在 firmware write 的 `done` 时 = 设备对包 body 的 CRC32；`written_serial` 在 `done` 时有效。
- 任务完成/失败后回到 `idle` 可接受新请求；失败原因保留在 `error=` 直到下一次请求。

## 8. 页面结构（照上游 failsafe 形态）

### 8.1 形态映射（上游 → 本页）

| 上游 failsafe 元素 | 本页 v2 | 说明 |
|---|---|---|
| 侧边栏品牌 `.sidebar-brand` + app 名 `恢复模式 WEBUI` | 顶部品牌区“E2631 恢复模式” + 小字 `U-Boot` 版本 | 纯 CSS；无 logo 图片 |
| 导航分组/项（基础功能/高级功能/系统） | 侧边栏分组：**救援**（系统状态、固件更新、引导区）、**系统**（环境变量、恢复出厂） | 不做 网页终端；不做 UBI/SIMG/GPT |
| `.card-head`（hero 图标 + h1 + 提示） | 每标签页首卡片同样的 head 结构 | 图标用内联 SVG 或纯 CSS |
| `.card-main`（文件选择、sysinfo、上传按钮、`.bar` 进度、文件/大小/MD5/MTD 行） | 固件更新/引导区页签 | 行改为：文件 / 大小 / SHA-256（浏览器）/ 设备 SHA-256 / 摘要一致 |
| `.card-foot` 注意事项 `<ul>` | 每页底部“注意事项”卡 | 断电、回退槽、serial 变化等 |
| 主题 auto/light/dark、强调色、i18n | 只保留 `prefers-color-scheme` 自动明暗；中文单语 | 省体积；无外部字体 |
| 程序页 flashing/fail/reboot | 单页内状态区（stage/进度/错误） | 不自动跳转、不自动重启 |

### 8.2 标签页

1. **系统状态**：启动路径 rail（BootROM → secondboot → U-Boot → 救援）；槽卡片（slot0/slot1：serial、版本、身份、valid/intact、next 标记）；当前 U-Boot `version`；`/status` 500 ms 轮询显示活动任务与进度；`GET /backup` 下载按钮 + CRC32/SHA-256 显示。
2. **固件更新**：文件选择（`accept=.bin`）、大小、浏览器 SHA-256；槽选择 `auto`/`slot0`/`slot1`（渲染身份/版本/完好/guard 徽标）；按钮“仅校验”和“写入待命”（后者在 `mode=validate` 返回 `result=ok` 且 `sha_match=ok` 且 `guard!=refuse` 后才可用）；写确认弹窗必须写明目标槽与“写入后下次启动该槽 / 断电重启后生效”；进度卡 + 阶段中文映射 + 日志；失败显示 `error` 与“启动仍留在另一槽”。
3. **引导区**：v1 `/flash` 页签（文件、SHA-256、仅校验/写入待命、五步进度）；显示当前 mtd0 镜像区 CRC32（`/status` 的 `bootloader_region_crc32`）；注意事项强调只写 `0x20000..0xC0000`。
4. **环境变量**：`/env` 只读表格（键/值），刷新按钮；页面标注“只读；写入请用串口 `e2631env`（白名单）”。
5. **恢复出厂**：说明（擦除 `rootfs_data`，overlay/配置丢失；squashfs 与槽位不动）；双确认（勾选“我已了解” + `confirm()`）；按钮“擦除 overlay”；进度；成功后“断电重启后生效”。

### 8.3 交互硬规则

- 写按钮 gating：bootloader 写 = v1 摘要门控；firmware 写 = validate 摘要一致 + guard 非 refuse；factory = 双确认。
- 忙时：所有写/擦按钮禁用；`/status` 轮询照旧；Ctrl-C/断开不依赖页面。
- 不做自动重启、不调用 `/reboot`（不存在该端点）；成功文案**只用“断电重启后生效”**，不得出现 reset 提示（Linux 运行时按住 reset ≥5 s = factory reset；启动时按住 = 救援触发）。
- 无外部资源；键盘可达（`label for`、`:focus-visible`）；尊重 `prefers-reduced-motion`。

## 9. 尺寸预算

| 项 | 预算 | 依据 |
|---|---|---|
| 当前 u-boot.bin（patch 0034） | 365,872 B | 构建产物实测 |
| v2 新增 C（备份/状态扩展/env/槽/固件校验+写/factory/HTTP 路由） | ≤ 24 KiB | 按各模块 1–10 KiB 估；U-Boot 已含 CRC32/SHA-256/mtd API |
| 页面资产（gzip，计入载荷） | ≤ 32 KiB | 用户/Lead 预算；v1 为 4,456 B |
| 合计预计 | ≤ 422 KiB | — |
| CI 闸门（现有） | 645,120 B | uboot-build size gate |
| 载荷硬上限 | 653,312 B | mtd0 镜像区 |
| 余量（闸门） | ≥ 221 KiB | 实际以 task-85 构建测量为准 |

规则：**task-87 先落地页面闸门 6,144 → 32,768 B**（`tools/embed-failsafe.sh` 默认 MAX、`tools/check-workflows.mjs` 断言、README 数字）并留下证据；页面的尺寸门以 task-87 的闸门为准。**task-85 实测 v2 构建的 u-boot.bin 大小并留下证据**，只有确需时才调整 `uboot-port` 的尺寸闸门。页面若超 32 KiB，回到 task-81 裁功能，不得偷抬闸门。

## 10. 安全边界

- 仅 lan1；开放 Wi-Fi/wan 无法访问（救援时无无线）。无 TLS、无认证——这是“物理/串口在场”场景的救援页；页面必须在启动文本里提示“仅连接可信 LAN”。
- 写端点必须自定义头（§2.4）；服务端不实现 CORS；同源检查可选加固。
- 不允许覆盖**完整可用的 vendor 系统槽**（唯一拒绝）；UNKNOWN/CORRUPT 槽允许写以救砖；不允许写 env/bootloader 以外的裸区间；factory 只能擦按名核对的 `rootfs_data`。
- 页面不使用 `innerHTML` 注入设备返回文本（错误文本限短 ASCII，仍以 `textContent` 渲染）；文件名只读展示。
- 页面不提供“网页终端/命令执行”；`/env` 只读。

## 11. 验收判据（task-86）

前置：v2 构建（含 task-82 按键触发、task-84 模块）经 CI 构建并记录 banner/sha；RAM 链或真刷写按 Lead 批准；串口 115200 在场。

| # | 检查 | 期望 |
|---|---|---|
| 1 | `GET /` | 200 gzip，解压后含五个标签页、无外部 URL；gzip ≤32 KiB |
| 2 | `GET /status` | v1 键 + v2 键齐全；`next_slot` 与 `e2631boot info`/`e2631slot` 一致；无副作用 |
| 3 | `GET /slots` | 与 `/status` 槽字段一致；slot0/slot1 serial/版本与串口 `e2631slot` 相同 |
| 4 | `GET /env` | 26+ 键；与串口 `printenv` 抽样一致；只读 |
| 5 | `GET /backup` | 655,360 B；`X-E2631-CRC32`/`X-E2631-SHA256` 与本地 `dd mtd0 0x20000..0xC0000` 计算一致；内容与串口 `md` 抽样一致 |
| 6 | `/firmware?mode=validate` 合法包 | 200 `result=ok`、`sha_match=ok`、`slot_target`=next、`guard` 合理；mtd 槽字节不变（前后 sha256 对比） |
| 7 | validate 负例 | 破坏 outer magic / 头部 CRC / kernel CRC / rootfs CRC / body size±1 / SHA 错 → 各自 400 对应 `error`，flash 不变 |
| 8 | `/firmware?mode=write`（真机写，需批准） | 200 `accepted`；`/status` 走完 erase→write→readback→compare→done；`result=ok`、`written_serial` 增加 1；掉电重启后 `e2631boot` 起目标槽、Linux 正常；旧槽仍可回退 |
| 9 | `/factory?confirm=reset`（需批准） | 擦除后 `mtd8` 全 FF；下次 Linux 启动 jffs2 新格式化（overlay 恢复默认）；mtd7 与槽位 sha 不变 |
| 10 | `/boot?slot=0` | `result=ok`；Ctrl-C 后 `e2631boot` 启动 slot0；再 `/boot?slot=1` 恢复；flash 槽 sha 不变 |
| 11 | 负例/并发 | 缺确认头、错 `slot`、旧格式 URL、busy 时段第二个写 → 400/409；不擦写 |
| 12 | 断电窗口 | 写固件中途断电（人工）→ 重启进另一槽（不砖）；记录来回复位证据 |

零净原则：验证阶段（validate/backup/env/slots/status）必须零 flash 写入，用任务前后 mtd0/槽 digest 对比；bootloader 写继续用 task-79 的净零写验收。

**firmware write / factory 不做“同一镜像牺牲写”**（Lead 2026-11-28 定）：验收 = (a) 现在完成 on-device validate + 负例 + 净零 bootloader 流程；(b) **首次真实固件升级**（确实是新镜像）走救援 UI `/firmware`，作为该端点的真机验收，需用户单独批准。

## 12. 实施拆分与移交

### 12.1 task-84（base-builder，U-Boot 侧）
1. 新文件 `board/zte/zxhn-e2631/e2631fwslot.c/.h`：
   - `int e2631fwslot_validate(const void *img, u32 len, struct e2631fwslot_result *r, char *err, size_t errsz);`
   - `int e2631fwslot_guard(int target, struct e2631fwslot_guard *g, char *err, size_t errsz);`
   - `int e2631fwslot_begin(int target, const void *img, u32 len);` // 擦整槽 + 写 body + 写头
   - `int e2631fwslot_poll(void);` // 有界一步；0=进行中，1=完成，<0=失败；暴露 stage/progress/crc/bytes
   - `void e2631fwslot_end(void);`
   - 所有常量（槽基址/跨度/头偏移/包偏移/magic）集中在头文件，便于对拍。
2. 新文件 `board/zte/zxhn-e2631/e2631factory.c`：`begin/poll/end`；按名 `rootfs_data` 核对 `0x3360000/0x4a0000`；erase→blank 回读全 FF；无写。
3. `e2631rescue.c`：
   - 路由 `GET /slots`、`GET /env`、`GET /backup`、`POST /firmware`、`POST /factory`、`POST /boot`；
   - `/status` 扩展（§3.2）；`/firmware` 暂存区替换为 `0x46100000`，`Content-Length` 上限校验；
   - `/backup` 分块发送与 ACK 驱动；`/factory` 与 `/firmware` 复用单飞行状态机；
   - 静态断言（§6）；串口日志：每次写开始/结束打印 target/bytes/serial/crc32。
4. `e2631boot.c`：支持 RAM env `e2631_next_slot`（仅本次覆盖；非法忽略；仍带 class-1 回退）。
5. 对拍夹具（kit `tests/` 或 `uboot-port/tests/`，CI 可跑）：§5.5 的合法/负例/盖章/守卫向量；`/` 路由/头解析可复用现有 host fixture。
6. patch 编号：按当前序列在 0035（按键触发）之后追加；`commits.env` 同步 sha256；不改 `0001..0035` 已发布内容。

### 12.2 task-81（页面，等契约拍板后）
- 按 §8 重写 `uboot-port/failsafe/e2631-failsafe.html`；单文件、无外部资源；复用 v1 的 SHA-256/上传/进度实现；新增五标签页与 §3 端点；
- 生成/自检：`bash tools/embed-failsafe.sh --check --max 32768`；`evidence/failsafe-redesign-20261128.md` 记录上游形态摘要、尺寸、sha；
- 提供 `python3 -m http.server` 之外的 mock 预览脚本（绑定 127.0.0.1）与契约 mock，供浏览器不连设备查看；
- task-87 抬闸后直接提交（Lead 2026-11-28 定）。

### 12.3 task-87 / task-85（pkg-release：闸门/构建）
- **task-87（先做，2026-11-28 已启动）**：页面预算闸门 6144 → 32768，同时更新 `tools/embed-failsafe.sh` 默认 `MAX`、`tools/check-workflows.mjs` 断言与 README 中的数字；
- **task-85（随后）**：实测 v2 构建大小并记录；`uboot-build.yml` 产物表加入新模块/资产统计；不动 `0001..0035` 的既有校验；新增断言覆盖 `/firmware`、`/factory`、`/backup` 的 README/契约字符串；
- 页面提交不再等 task-85（D1）。

### 12.4 task-86（verify-docs：真机验收）
- 按 §11 执行；validate/backup/env/slots 为只读阶段（零 flash 写，mtd 前后 sha 对比）；
- firmware write / factory **不做牺牲写**：firmware 验收 = 首次真实升级（新镜像）走 `/firmware`，需用户单独批准；factory 验收单独安排并说明 overlay 丢失；
- 证据：串口全日志、`/status` 序列、mtd 前后 sha、页面 gzip/解压 sha、curl 请求响应原文。

## 13. 决策记录（Lead 2026-11-28 复核）

本契约在 2026-11-28 经 Lead 复核，**全部接受**，其中四项按修订执行（修订已并入正文）：

| # | 决策 | 落点 |
|---|---|---|
| 1 | **D1 页面闸门**：task-87 先做 6,144 → 32,768 B；页面在 task-87 落地后直接提交，不等 task-85。 | §0.6 / §3.1 / §9 / §12.2 |
| 2 | **D3 目标槽守卫**：只拒绝 `identity=vendor` 且 `intact` 的槽；UNKNOWN / vendor-但损坏 / 无头 / 不可识别槽**可写**（救砖是救援的核心用途）。 | §0.7 / §3.7.4 / §5.2 / §10 |
| 3 | **D7 成功文案**：只用「断电重启后生效」；**不得提示 reset**（Linux 运行时按住 reset ≥5 s = factory reset；启动时按住 = 救援触发）。 | §1.2 / §8.2 / §8.3 |
| 4 | **D8 固件写验收**：不做同一镜像牺牲写；(a) 现在做 on-device validate + 负例 + 净零 bootloader 流程；(b) **首次真实固件升级**（确实是新镜像）走 `/firmware` 作为该端点验收，需用户单独批准。 | §11 / §12.4 |
| 5 | 默认目标 `auto = next_slot`（serial 最大）；写后 `serial=max_serial()+1`、`H_NEW=1`、CRC2 重算盖章。 | §3.7 / §5.3 |
| 6 | weak fallback：另一槽 `ours` 且 intact 时允许写（页面警示“回退不是原厂”）；不完整/不可读仍 `refuse`。 | §5.2 |
| 7 | `/factory` 只擦按名核对的 `rootfs_data` + 全 FF 回读，不格式化（下次 Linux 启动 jffs2 格式化）。 | §3.8 |
| 8 | `/boot` 覆盖变量 `e2631_next_slot`，RAM-only、不持久化。 | §3.6 |
| 9 | 备份文件名/响应头按 §3.4；中文单语；不搬上游资产。 | §3.4 / §8 |
| 10 | 页面形态照上游 failsafe（五标签）；boot-path rail 只有在 fits 上游形态时才保留。 | §8 |

后续实现按 §12 的 task-87 / task-84 / task-81 / task-85 / task-86 拆分推进。
## 14. 参考与复现

- v1 设计/契约：[docs/E4-多功能U-Boot设计-2026-11-27.md](../docs/E4-多功能U-Boot设计-2026-11-27.md) §4.2–§6。
- v1 验收方案：[evidence/e4-rescue-acceptance-plan-20261127.md](e4-rescue-acceptance-plan-20261127.md)；页面接口说明：`uboot-port/failsafe/README.md`。
- 槽/包语义：`/home/qc233/zte/iwrt-tree/package/e2631/e2631-fwslot/src/e2631-fwslot.c`（`package_load`、`cmd_write`、`upgrade_guard`、`install_guard`、`header_identity`、`next_slot`）。
- 启动选槽：`/home/qc233/zte/uboot-src/board/zte/zxhn-e2631/e2631boot.c`（`e2631_pick_slot`、`e2631_load_kernel`、`do_e2631boot`）。
- 现有写路径：`e2631flash.c/.h`（五步 job API）、`e2631rescue.c`（v1 HTTP 状态/摘要/进度）、`e2631http.h`（头解析）。
- 设备事实来源：Lead m05113（mtd8 `rootfs_data` @0x3360000 len 0x4a0000，无 factory 分区）；task-79 真机写/冷启动证据（`evidence/e4-rescue-write-acceptance-20261128.md`）。
- 上游 UI 参考：`Yuzhii0718/bl-mt798x-dhcpd`（`uboot-mtk-20250711/failsafe/embedded/fsdata-bootstrap`，GPL-2.0；仅取形态，不复制资产）。

---

契约变更记录：任何端点/字段/错误文本/地址变更必须同时更新本文件、`docs/E4-多功能U-Boot设计-2026-11-27.md` §10、`uboot-port/failsafe/README.md` 与 `tools/check-workflows.mjs` 的断言，并在 task-86 重新验收。
## 15. v2.1 增补（task-88，用户裁定 2026-11-28：功能全加，不设口令门）

本节是 v2 契约的增补，覆盖三组新能力与两类明确不做项；与 §1–§14 冲突时以本节为准。
用户裁定（m12022）：“把功能都加上，不要再说安不安全了”。因此本页**不设口令/鉴权门**，
安全边界只写进文档（§15.5），不作为裁剪功能的理由。

### 15.0 范围

新增端点：

- POST /console?cmd=<单条命令>：执行一条 U-Boot 命令并捕获 stdout；只适合快速命令，
  不与救援循环 stdin 共享，交互式命令（需要按键/确认的）不支持。
- POST /env?key=<名>&value=<值>&confirm=write：仅 e2631env 白名单键，复用 e2631env 五步写；
  env 写所有者不变（仍是 e2631env）。
- GET /backup?part=bootloader|tag|wifi|usercfg|defcfg：分区只读备份 + CRC32/SHA-256 响应头。

明确不做：UBI/SIMG（MT798x 专属，本机不适用）、I18N（页面中文单语）；页面不提供网页终端
的 stdin 会话，只提供单命令执行。

### 15.1 POST /console?cmd=<单条命令>

请求：

- 无 body（Content-Length: 0）；cmd 由页面 URL-encode；解码后长度 1..256 B。
- 只允许**单条命令**：含分号 ;、换行 CR/LF、NUL 一律 400 error=only a single command is allowed。
- 无需确认头（用户裁定不设口令门）；页面侧有二次确认与风险提示。

执行：

- 服务端调用 U-Boot run_command(cmd, 0)；执行期间把控制台输出重定向到 4 KiB 环形捕获缓冲
  （覆盖式，保留尾部），执行结束后恢复。
- 不与救援循环的 stdin 共享；不等待按键；命令自行阻塞超过约 2 s 时由命令自身语义决定
  （服务端不强制超时，页面提示交互式命令请用物理串口）。
- 捕获输出中的换行编码为两字符 \n，反斜杠编码为 \\；页面反转义后显示。

响应（200，text/plain，逐行 key=value）：

    result=ok|error
    exit=<run_command 返回值，十进制>
    stdout=<转义后的捕获文本，单行>
    truncated=<0|1>
    error=<短原因，无错误时为空>

失败：400（参数非法）、500（执行异常）；错误响应也带 exit= 与 stdout=（可能为空）。

### 15.2 POST /env?key=<名>&value=<值>&confirm=write

请求：

- 无 body；key/value 均为 URL-encode；必须 confirm=write 且请求头 X-E2631-Confirm: write，
  缺一即 400 error=missing confirm。
- 白名单：key 必须等于 bootdelay 或以 e2631_ 开头，且匹配 [a-z0-9_]+，长度 ≤32 B；
  value 只允许可打印 ASCII（0x20..0x7E），长度 ≤128 B。其余一律 403 error=key is not writable
  （vendor 键如 bootcmd/bootargs/memsize/versioninfo 永远只读；e2631env 白名单不变）。
- 同一时刻只允许一个 env 写任务。

五步写（复用 e2631env，写所有者不变）：

1. diff：把当前 env + 本次修改生成目标快照，打印差异；无变化直接 result=ok。
2. check：长度校验与坏块预检（env 块 0xC0000，0x20000 B；不允许越界；坏块则失败）。
3. erase：擦除 env 块（0xC0000..0xDFFFF）。
4. write：写标准 vendor env 格式（4 B CRC32 + 0x1FFFC 数据），全 0x00 填充。
5. readback/verify：回读比较并重算 CRC32；失败则保持 error，不自动重试。

响应：

- 立即 200 accepted：result=accepted、new_crc32=0x…、keys=<本次写入键数>；
  随后 /status：op=envwrite，stage=diff→check→erase→write→readback→verify→done，
  progress 0..100；成功 result=ok、crc32=0x…；失败 result=error、error=<原因>。
- 掉电：最坏回到默认 env（两条启动链都能启动，不是砖路径，D-U2 结论不变）。
- 成功文案只提示“断电重启后生效”；不自动重启。

### 15.3 GET /backup?part=<分区>

part 与区间（设备实测/槽位契约）：

| part | 偏移 | 长度（B） | 说明 |
|---|---|---|---|
| bootloader | 0x20000 | 655,360 | mtd0 的 U-Boot 镜像区（默认，兼容 v1） |
| tag | 0x100000 | 1,048,576 | mtd1（含 MAC 等只读信息） |
| wifi | 0x200000 | 1,048,576 | mtd2 |
| usercfg | 0x300000 | 2,097,152 | mtd3 |
| defcfg | 0x500000 | 2,097,152 | mtd4 |

- 请求：GET，无 body；part 缺省 = bootloader；未知 part → 400 result=error error=bad part。
- 响应：application/octet-stream 原始数据 + Content-Length + Content-Disposition
  （filename=e2631-<part>.bin）+ X-E2631-CRC32 + X-E2631-SHA256 + X-E2631-Offset +
  X-E2631-Length + X-E2631-Part。只读，不占飞行锁（同一时刻只允许一个备份传输）。
- 页面只做读取/下载，不提供写回（写分区仍归各自所有者，见 §4 写所有者矩阵）。

### 15.4 明确不做

- UBI/SIMG/BL2/GPT：MT798x 的存储布局专属，本机 SPI-NAND + 双槽 + mtd0 结构不适用，
  已由其它任务所有者（e2631flash / e2631-fwslot / e2631factory）负责，本页不重复实现。
- I18N：页面中文单语；不引入 i18n 资源（省 gzip 预算，单用户自用）。
- 网页终端 stdin 会话：只做单命令 + stdout 捕获；交互式命令请用物理串口。
- env 写入不扩展到 vendor 键；页面不提供 vendor 键编辑入口。

### 15.5 安全说明（只在文档，不设口令门）

- 救援页无鉴权，任何能访问 192.168.1.1 的主机都可执行 /console 命令或写 env/槽位。
  这是用户明确接受的取舍；救援模式只在按键触发后运行，正常启动不监听网络。
- /console 可执行任意单条 U-Boot 命令（包括 reset、mtd 擦写），页面仅做二次确认与提示；
  不提供 stdin，因此依赖交互的命令不会挂住整个救援循环。
- /env 只允许 e2631env 白名单键；/backup 只读；固件写仍有原厂槽守卫与摘要门控。
- 若未来要收紧，优先加口令或限制 /console 命令白名单；当前版本不做。

### 15.6 写所有者与不变式

| 对象 | 所有者 | 本页动作 |
|---|---|---|
| bootloader mtd0 镜像区 | e2631flash | /flash（v1） |
| 启动槽 | e2631-fwslot | /firmware |
| overlay（rootfs_data） | e2631factory | /factory |
| env 块 | e2631env | /env（v2.1） |
| 备份/只读 | 无 | /backup、/slots、/status、/console |

不变式：三者互不越界；/console 只是转发用户命令，不新增写路径；/env 不写 vendor 键；
/backup 永不写 flash。

### 15.7 页面映射与预算

- 六个标签：系统状态、固件更新、引导区、环境变量、串口台、恢复出厂；串口台放在“系统”
  分组、环境变量之后。引导区新增分区备份下拉（bootloader/tag/wifi/usercfg/defcfg）。
- 环境变量：只读总表 + 白名单键编辑（bootdelay 与 e2631_*），勾选确认 + confirm() 双确认，
  逐个键写入并轮询 /status（op=envwrite）；写入完成提示断电重启。
- 串口台：单命令输入 + 执行 + 输出区 + 历史（≤20 条）；执行前 confirm；提示无 stdin、
  命令立即生效；输出截断标记。
- gzip 预算仍是 32,768 B；新页面实测见 evidence/failsafe-redesign-20261128.md §10。

### 15.8 验收补充（task-86）

- /console：version、printenv bootdelay、md 0x40000000 4 等快速命令返回 stdout；
  含分号/换行请求返回 400；执行 reset 会重启（在验收中只做一次，且仅当用户批准）。
- /env：写 e2631_ 测试键 → /status 五步 → 回读 printenv 一致；写 vendor 键 403；
  掉电模拟（可选）后仍能启动。
- /backup：五个分区下载长度/offset/CRC32/SHA-256 与设备一致；未知 part 400。
