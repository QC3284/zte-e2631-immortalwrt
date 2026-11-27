# E4 救援模式验收（第一阶段，validate-only）—— RED：救援 POST 解析缺陷

> 结论：`e2631rescue` 的页面与状态接口可用、TCP 收发链路已证实可用；但 `POST /flash?mode=validate` 在固件侧被 `rescue_name_is()` 的头部大小写比较缺陷拦截，固定返回 `400 result=error error=unsupported request`，validate 与 write 两条路径都不可用。本次为零写会话，mtd0 未变，F1 内核照常启动。

## 0 摘要

| 项目 | 结果 |
| --- | --- |
| 产物（F2-fixed build） | CI run 46030383958，banner `U-Boot 2027.01-rc2-gd38f69c44523`，32 patches，tree `ae72334756d47f05a247f0dea63f81c0ca7265dc` |
| 零写链 | userdata staging -> flash U-Boot -> `mtd read` + crc32 -> `go`，全部通过 |
| GET / 页面 | **PASS**：200，gzip 4456 B（sha256 `8f16817b...`），解压 9216 B（sha256 `30a8f03e...`）= 仓库 `e2631-failsafe.html` |
| GET /status | **PASS**：200，`stage=idle progress=0 sha256= browser_sha256= sha_match=absent` |
| POST /flash?mode=validate | **FAIL**：400 `result=error error=unsupported request`，未进入结构校验/摘要校验 |
| 负向（错误摘要） | 未能执行：正向 validate 就失败，缺陷在更早的头部解析处；负向用例已加入驱动的下一轮流程 |
| TCP/RX | **已证实**：tcpdump 抓到完整三次握手、GET 请求/200 响应、POST 请求头/400 响应；设备 MAC `00:41:71:00:00:50` |
| 零写 | mtd0 前后 `f9239040...`；region `b1ea9a48...`；env block `6e2c01da...`；U-Boot 审计零写命令 |
| F1 | `e2631boot` -> KERNEL_STARTED 8.63 s，Linux 正常起来 |
| 设备终态 | ImmortalWrt v1.10.0 / 6.18.60，PANICS=0 OOPS=0 MT7916=1，fwslot slot1 serial 12 running / slot0 serial 7 intact |

## 1 输入与产物

- 构建：`uboot-build` run 46030383958（F2-fixed，32 patches，kit tip 739b8e8）；本机归档 `/home/qc233/zte/e2631-t5-artifacts/uboot-f2-fix-46030383958/e2631-uboot-46030383958/`，`sha256sum -c SHA256SUMS` 11/11 通过。
- `u-boot.bin`：365872 B（0x59530），sha256 `e87a858046b865acfd8e83f1bfbd14cae262a3b16c9738a9edc321cc6a1adc6b`，crc32 `0x0966526e`，banner `gd38f69c44523`，entry 0x47F00000。
- `e2631-uboot-mtd0.bin`：655360 B，sha256 `4fa8bd4d0e4600fd4c3463848135c7239a21f7e2cdb6f4865c462b888ddcb857`（未刷写）。
- env block template：`6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`。
- 会话驱动：`/home/qc233/zte/e2631-p3/e2/drivers/e4_rescue_accept.py`（附件 tool-e4_rescue_accept.py）；out-dir `/home/qc233/zte/e2631-p3/e2/e4-rescue/run-1`。

## 2 会话与零写链

会话时间 2026-11-28 00:29:44–00:31:39（CST）。

1. preflight：artifact pins、直连路由 `192.168.1.1 dev enp0s20u1u4u2c2 src 192.168.1.191`、设备 mtd0 `f9239040...`、image region `b1ea9a48...`、capture chain 均在位。
2. 从运行中的 Linux 只读提取 net-zero 载荷：`dd if=/dev/mtd0 bs=4096 skip=32 count=160`，655360 B，sha256 `b1ea9a48...`，crc32 `0x0721e716`。
3. staging 到 userdata（本会话唯一 flash 写）：padded 524288 B sha256 `bdf14c1d1f68d33317966d5fe6e377275cc54d255590637d1db4c224c8ce7792`；copy 0.25 s / erase 0.88 s / write 0.42 s / readback 0.25 s / sync 0.19 s，全部 rc=0。
4. reboot 后停在 flash 15-patch U-Boot（banner `g85df6772a444`）：`mtd read spi-nand0 0x47f00000 0x3f00000 0x80000` -> `crc32` 得 `0x0966526e` 与产物一致；`go 0x47f00000`。
5. 新镜像 banner `gd38f69c44523`，env block 读回 `stored=0xf95a816e region=0xe826c394`，与 B1 基线一致；env sanity 27 项（26 flash keys + `fdtcontroladdr`），无 bad CRC/default env，ethaddr `00:41:71:00:00:50`。
6. 救援页面验收（第 3-6 节），然后 Ctrl-C 退出；F1 `e2631boot` 起内核；SSH 只读 postcheck；capture chain 恢复。

## 3 GET / 页面（PASS）

请求：`curl -4 --noproxy * --interface 192.168.1.191 http://192.168.1.1/`。

```
HTTP/1.1 200 OK
Server: e2631rescue
Content-Type: text/html; charset=utf-8
Content-Encoding: gzip
Content-Length: 4456
Cache-Control: no-store
Connection: close
```

- gzip body 4456 B，sha256 `8f16817b30d66197364cf5a67d9cf5ddd2720a7a09975e8d01dd2494d78616d3`。
- 解压 9216 B，sha256 `30a8f03e46867bb066947a2537f738e0539fd214ae579a287c301d5ff9e39bda`，与仓库 `uboot-port/failsafe/e2631-failsafe.html` 逐字节一致。

## 4 GET /status（PASS）

```
stage=idle
progress=0
sha256=
browser_sha256=
sha_match=absent
```

## 5 POST /flash?mode=validate（FAIL，关键缺陷）

请求：`curl -X POST --data-binary @netzero-mtd0-image.bin -H "Content-Type: application/octet-stream" -H "X-E2631-SHA256: b1ea9a48..." -H "Expect:" http://192.168.1.1/flash?mode=validate`。

```
HTTP/1.1 400 Bad Request
Server: e2631rescue
Content-Type: text/plain
Content-Length: 39
Cache-Control: no-store
Connection: close

result=error
error=unsupported request
```

`/status` 之后仍为 `stage=idle`、`sha_match=absent`，说明请求在读取 body 之前就被拒绝，结构校验/摘要校验均未执行。

## 6 TCP / RX 证据（RX 已证实，不是网络问题）

主机 tcpdump（enp0s20u1u4u2c2，`-nne -l`）抓到完整交互，关键行：

```
16:30:15.139610 ... 192.168.1.191.40742 > 192.168.1.1.80: ... HTTP: GET / HTTP/1.1
16:30:15.142542 ... 192.168.1.1.80 > 192.168.1.191.40742: ... HTTP: HTTP/1.1 200 OK
16:30:15.158266 ... 192.168.1.191.40754 > 192.168.1.1.80: ... HTTP: GET /status HTTP/1.1
16:30:15.160795 ... 192.168.1.1.80 > 192.168.1.191.40754: ... HTTP: HTTP/1.1 200 OK
16:30:15.221813 ... 192.168.1.191.40762 > 192.168.1.1.80: ... HTTP: POST /flash?mode=validate HTTP/1.1
16:30:15.229116 ... 192.168.1.1.80 > 192.168.1.191.40762: ... HTTP: HTTP/1.1 400 Bad Request
```

设备 MAC 出现在双向报文（`00:41:71:00:00:50`），三次握手、请求、响应均可见，因此 F2 之后的 TX/RX 路径在救援模式下工作正常；本次失败在应用层解析。

## 7 根因：patch 0028 的头部大小写比较缺陷

`uboot-port/patches/0028-board-zte-add-the-web-bootloader-rescue-e2631rescue.patch`：

```c
static bool rescue_name_is(const char *line, const char *name)
{
	unsigned int i;

	for (i = 0; name[i]; i++) {
		if (!line[i] || rescue_lower(line[i]) != name[i])
			return false;
	}

	return line[i] == ':';
}

if (!rescue_header_value(hdr_start, "Content-Length", value,
			 sizeof(value)))
	goto bad;
```

`rescue_name_is()` 只把**收到的头部行**转小写，却拿它与调用者传入的**大小写混合**名字比较；`rescue_lower('C')=='c' != 'C'`，所以 `Content-Length`、`X-E2631-SHA256`、`X-E2631-Confirm` 永远匹配不上。`rescue_header_value()` 返回 false，`rescue_handle_request()` 直接 `goto bad`，返回 `unsupported request`。GET 路径不使用该函数，所以页面和状态接口正常。

修复：比较 `rescue_lower(name[i])`（或调用处统一传小写字面量）；同时建议加一个主机侧解析 fixture/CI 断言，避免同类回归。该缺陷同时阻塞 `mode=validate` 与 `mode=write`，write 路径在修复前无法验收。

## 8 驱动侧缺陷与修复（下一轮使用）

1. 生成驱动时漏了 `import gzip`，导致页面解压抛 `NameError`，`page_raw_sha/page_repo_match` 误报 false；实际主机侧手工校验已证明页面逐字节正确。已补 import。
2. `_rx_report()` 在请求刚结束时读取 tcpdump 文件，尚未 flush 完，导致 POST 计数为 0、rx_http=false；已改为等待 1.5 s 并解析完整 fresh log。
3. 负向用例已按 Lead m09259 加入：正向 validate 通过后，再发一次 `X-E2631-SHA256` 为全零的错误摘要，期望 400 + `sha256 mismatch`，且 `/status` 保持 `stage=idle`/`sha_match=mismatch`，不产生 staging 变化。

## 9 零写审计与设备终态

- 本会话唯一 flash 写：Linux 侧 userdata staging（erase + write + readback + sync，全部 rc=0，目标 `/dev/mtd10`，未挂载）。
- U-Boot 命令审计：21 条命令，全部只读/加载/启动类；`forbidden` 为空（无 mtd write/erase、saveenv、nand write/erase、e2631flash、bootm）。
- mtd0：`f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4`（会话前后一致）。
- image region：`b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a`（前后一致）。
- env block：`6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893`（stored CRC 0xf95a816e / region CRC 0xe826c394）。
- fwslot：slot1 serial 12 `ImmortalWrt v1.10.0` running/next-boot；slot0 serial 7 `V1.0.0.7B5.8000` intact。
- 健康：VERSION=ImmortalWrt v1.10.0，KERNEL=6.18.60，PANICS=0，OOPS=0，MT7916=1。
- capture chain 已恢复：supervisor 339948 / bootwatch 339958 / tty holder 339955。

## 10 后续

1. base-builder 出 patch 0033 修复头部大小写比较，重钉并重建；本轮 artifact 的 write 路径同样不可用。
2. 新产物出来后重跑本驱动（第一轮 validate + 错误摘要负向），预期 `RESCUE_PASS`。
3. write 模式仍需用户单独批准后另开验收会话；本轮未执行。

## 附录 A 附件

- `preflight.txt`：会话后只读 preflight（artifact/route/device/baseline）。
- `serial.txt`：救援会话串口原文；`console-history.txt`：U-Boot 控制台完整回显。
- `tcpdump.txt`：主机抓包；`tcpdump-http-lines.txt`：HTTP 关键行摘录。
- `page.headers.txt`、`page.body.gz`、`page.html`、`page-asset-sha256.txt`：GET / 页面与摘要。
- `status-initial.body.txt`、`validate.headers.txt`、`validate.body.txt`、`status-after-validate.body.txt`：/status 与 validate 的原始响应。
- `session-results.json`：完整会话结果；`driver.txt`：驱动日志；`tool-e4_rescue_accept.py`：本会话驱动。
- `artifact-SHA256SUMS.txt`、`artifact-UBOOT-INFO.txt`：产物校验。
- `root-cause-rescue-header-bug.txt`：patch 0028 代码片段与解释；`netzero-payload.txt`：净零载荷摘要。
- `SHA256SUMS.txt`：附件清单。

## 附录 B 复现命令（第三阶段重跑）

```
cd /home/qc233/zte/e2631-p3/e2
python3 drivers/e4_rescue_accept.py --preflight --rescue \
  --artifact <new-artifact-dir> --out-dir /home/qc233/zte/e2631-p3/e2/e4-rescue/run-2
python3 drivers/e4_rescue_accept.py --session --rescue \
  --artifact <new-artifact-dir> --out-dir /home/qc233/zte/e2631-p3/e2/e4-rescue/run-2
```
