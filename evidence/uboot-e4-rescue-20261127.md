# E4 v1 救援模式与厂商复位：CI 构建记录（task-72 / task-76，2026-11-27）

## 0. 结论

- E4 v1（救援模式）与厂商复位已作为 patch 0026-0029 进入 kit；29 个 patch 的 post-am tree 为
  `e7dc246351aba6b8c946967addc0971b4f4e97f4`，uboot-build run `46002766353`（head `c91e976`）全绿。
- 镜像：banner `U-Boot 2027.01-rc2-ga9d4df78ce6e (Nov 19 2026 - 15:44:39 +0000)`，`u-boot.bin` 360,624 B
  （sha256 `49acded8d7b7a664dab7f45aab683b020cc583004aa423c3c47d996c064354e6`，crc32 `b431eb15`），
  mtd0 镜像 sha256 `79dab60d3ce0e3eb72037cd6afb3431b89071824c6449df377d62cb233095a28`，env 块保持
  `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426` 未变。
- 尺寸：defconfig 瘦身后的 320,848 B → 360,624 B（+39,776 B，+12.40%）。设计文档的 Option A 估算是
  +16..34 KB，本次超出估算上限 4,960 B（+4.84 KiB），但距 mtd0 载荷硬上限仍有 292,688 B 余量；若 Lead
  要求严格 ≤34 KB，可再做一个只删未用命令/子系统的 defconfig-only patch，不影响本功能。
- 写入口不变量未变：D-U1 调用点白名单仍恰好 4 个 site（`e2631_write_range`/`e2631_erase_range`/
  `do_e2631flash`/`e2631_env_write_block`，`-O2` 内联后落在 `do_e2631flash`/`do_e2631env_save`）；救援页只经
  `e2631_flash_*` job API 写 mtd0，没有第二个 MTD 写实现。

## 1. 交付

| patch | 内容 |
| --- | --- |
| 0026 | 最小 TCP 栈 + DHCP 服务器（bl-mt798x-dhcpd，GPL-2.0，`e4cf4dc7`），适配本树 legacy net API；新增 `arp_wait_clear()` 与 `CONFIG_MTK_TCP` 的 `PROT_TCP` 钩子 |
| 0027 | `e2631flash.h` 五步写 job API（begin/erase/blank_check/write_image/readback/compare/end），救援页复用 |
| 0028 | `e2631rescue`：DHCP + 极简 HTTP + gzip 救援页 + SHA-256/确认头契约 + 结构校验 + mtd0 五步写 |
| 0029 | 厂商 TOPCRM 软复位：`mdelay(50)` 后向 `0x94000044` 写 1，替换占位 `reset_cpu()` |

## 2. 运行契约（v1 冻结）

- 入口：串口执行 `e2631rescue`；lan1 上 DHCP 服务器（本机 192.168.1.1/24，池从 192.168.1.100 起）与
  HTTP 服务器（80 端口）启动；Ctrl-C 退出，退出时若正在写会打印中断告警。
- `GET /`：内嵌 gzip 救援页（`Content-Type: text/html`、`Content-Encoding: gzip`），无外网依赖。
- `GET /status`：`text/plain`，每行 `key=value`；`stage` 取值 idle/staged/validating/erase/blank/write/
  readback/compare/done/error，另有 `progress`、`crc32`、`sha256`、`browser_sha256`、`sha_match`、`result`、
  `error`。
- `POST /flash?mode=validate|write`：raw body 必须恰好 655,360 B（mtd0 整镜像）；`mode=write` 还要求
  `X-E2631-SHA256`（小写 hex，整文件 SHA-256）与 `X-E2631-Confirm: write`；校验/结构检查失败一律 HTTP 400 +
  `result=error`，不进入擦除。结构检查：size、`+0x10` 内层 magic `0x73383231`、`+0x14` payload 长度窗口、
  padding 全 0xFF、payload 含 `U-Boot 20`。v1 没有 header CRC（保持厂商头格式与 net-zero 字节一致）。
- 写窗口：mtd0 `0x20000..0xA0000`（U-Boot 区）；secondboot `0x0..0x20000`、env `0xC0000..0xE0000`、保留区
  `0xE0000..0xFFFFF` 一律不碰；成功后不自动重启，串口/页面都提示手动 `reset` 或断电。

## 3. CI 门禁（新增/沿用）

- 配置：`CONFIG_MTK_TCP=y`、`CONFIG_MTK_DHCPD=y`、`CONFIG_SHA256=y`、`# CONFIG_MTK_TCP_VERBOSE is not set`。
- 二进制：`e2631rescue` 命令与 `serve the web bootloader rescue on lan1`、`X-E2631-SHA256`、
  `X-E2631-Confirm: write`、`e2631rescue: PASS: mtd0 updated` 必须命中。
- 源码形状：`e2631rescue.c` 含 `e2631_flash_begin`/`sha256_csum_wd`/`e2631_failsafe_html_gz`，且不含
  `mtd_write`/`mtd_erase`；`zxhn-e2631.c` 含 `ZX279128S_TOPCRM_SOFT_RST` 与 `mdelay(50)`。
- 救援页资产：`tools/embed-failsafe.sh` 生成确定性 gzip（本次 raw 9,216 B / gzip 4,456 B，上限 6,144 B），
  workflow 在 `git am` 之后、`make` 之前嵌入。
- 保留：`# CONFIG_CMD_MTD_WRITE is not set`、`# CONFIG_CMD_SAVEENV is not set`、MTD 写调用点白名单、
  `CONFIG_TEXT_BASE=0x47F00000`、入口点、尺寸上限、可复现构建（`SOURCE_DATE_EPOCH` +
  `git am --committer-date-is-author-date`）。

## 4. CI 产物（run 46002766353）

| 项 | 值 |
| --- | --- |
| kit head | `c91e9765032a11ee240264c38b864c4ac63bdb8e` |
| uboot-build run | `46002766353`（SUCCESS） |
| kit check.yml run | `46002763627`（SUCCESS） |
| banner | `U-Boot 2027.01-rc2-ga9d4df78ce6e (Nov 19 2026 - 15:44:39 +0000)` |
| u-boot.bin | 360,624 B / sha256 `49acded8d7b7a664dab7f45aab683b020cc583004aa423c3c47d996c064354e6` / crc32 `b431eb15` |
| mtd0 镜像 | 655,360 B / sha256 `79dab60d3ce0e3eb72037cd6afb3431b89071824c6449df377d62cb233095a28` / crc32 `f5f18b5c` |
| mtd0 首 0x800 | sha256 `1b55581d0372b1abe6ec36ceb11cd22f4828ccf3509a69bc9d269e8c227f4eb9`（装配后；模板输入仍是 `19a9d546...`） |
| env 块 | sha256 `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`（未变） |
| `.config` | sha256 `d3a8450a810064adce1152741cf563237a587e1c2875ad598eaa6c5f969a7a5a` |
| checkpatch | 0 errors / 0 warnings（四类 ignore 后；0026 另有 24 条非阻断 CHECK） |
| artifact | `/home/qc233/zte/e2631-t5-artifacts/uboot-e4-46002766353/e2631-uboot-46002766353/` |

命令帮助（E2631-COMMAND-HELP.txt）：`e2631flash`/`e2631verify`/`e2631slot`/`e2631env`/`e2631rescue` 五段与
二进制字符串均已确认；`e2631rescue` 短帮助为 `serve the web bootloader rescue on lan1`。

## 5. 零写入真机验收（下一次设备会话，写入步骤需用户单独批准）

1. 先做 RAM 链或 flash 链只读验证：`e2631rescue` 启动服务但**不创建写任务**；PC 能 DHCP、能打开页面、
   `GET /status` 为 `stage=idle`。
2. 上传一个错误文件（长度错误/坏 magic/错误 SHA）：必须 HTTP 400 + `result=error`，`/status` 不出现
   erase/write，flash 内容不变（前后 mtd0 全盘 sha256 相同）。
3. 上传正确 net-zero mtd0 镜像并点“仅校验”：返回 `result=ok` 与 CRC32；此时仍未擦除。
4. 只有在用户批准的写会话里才点“写入待命”：记录写前 mtd0 全盘 sha，观察阶段行与串口日志，结束后
   复核写后 mtd0 sha 与预期一致（新镜像 `79dab60d...`），再执行 `reset`。
5. 若写中途失败/断电：串口仍是唯一恢复通道，按 task-54 的 rescue ladder 处理；救援页不自动重启。

## 6. 风险与边界

- 写窗口只在 mtd0 U-Boot 区，固件槽位与 env 不在救援范围内（用户裁决：v1/v2 都不刷固件镜像）。
- v1 不校验 payload 内容本身（没有 header CRC），只做结构 + SHA-256 + 回读比较；payload 单字节翻转若同时
  伪造了 SHA 头则无法检出，页面 SHA-256 只是信息性 + 传输完整性。
- 救援页是 U-Boot 内的单线程轮询服务（无中断、无多连接），只适合维护会话；正常启动不初始化网络。
- 复位依赖厂商 TOPCRM 寄存器；若真机上该写不触发复位，串口会停在自旋前提示，断电恢复。

## 7. 参考

- [docs/E4-多功能U-Boot设计-2026-11-27.md](../docs/E4-多功能U-Boot设计-2026-11-27.md)
- [evidence/e4-bl-mt798x-dhcpd-study-20261127.md](e4-bl-mt798x-dhcpd-study-20261127.md)
- [evidence/e4-reset-re-20261127.md](e4-reset-re-20261127.md)
- [uboot-port/README.md](../uboot-port/README.md) §1/§4/§5
