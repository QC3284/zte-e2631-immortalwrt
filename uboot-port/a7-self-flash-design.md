# D-U1：U-Boot 自更新命令设计（e2631flash / e2631verify / e2631slot + CMD_MTD_WRITE）

日期：2026-11-22。对应 patch 0014、0015；tree `31843b38628ccf9c3e0b542ec4db014b6612755d`。

## 1. 为什么要自己刷 U-Boot

C1b-1 之后自定义 U-Boot 已经能作为 mtd0 载荷冷启动（A6 GREEN），但把新镜像写进 mtd0 一直依赖手工
`md.b`/`nand write` 阶梯：

- 串口 `loadx` 实测约 **10.9 KB/s**（655,360 B 用了 60.1 s），mtd0 的 640 KiB 镜像仅传输就 60 s；
- `md.b` 校验 640 KiB 要 **4m36s–4m38s**；
- 同一文件以太网传输 **31 MB/s**（640 KiB 0.15 s、20 MiB 0.64 s）。

同时实测：`/dev/mtd0` 在 Linux 侧被 DTS 设为只读（`O_RDWR` 失败，这是刻意设计），而 userdata
（`/dev/mtd10`，偏移 `0x3F00000`，约 49 MiB）可写且未使用。因此正常更新路径定为：

1. 以太网把新镜像传到 Linux；
2. 写入 userdata 暂存；
3. 重启进入本 U-Boot；
4. U-Boot 把暂存镜像读入 RAM（本次实现用 1 MiB bounce buffer），再做擦除→空白校验→写入→读回比较。

串口只保留给救砖，不再进入正常更新路径。

## 2. 命令契约

### 2.1 e2631flash `<src> <off> <len>`

- `<src>` 语义：
  - `>= 0x40000000`：RAM 地址（loadx/tftp 之后的镜像）；
  - `< 0x10000000`：SPI-NAND 字节偏移（以太网暂存路径），先整段读入 `0x44000000` 的 1 MiB
    bounce buffer，再对目标区做擦写，因此 flash→flash 更新不会边擦边读目标；
  - 其它值（例如 `0x10000000..0x3FFFFFFF`）：拒绝。
- 拒绝条件：`off`/`len` 非块对齐；`off+len` 超出芯片；目标与 secondboot（`0x00000..0x20000`）或
  env（`0xC0000..0xE0000`）重叠；RAM 源超出可用 DRAM 窗口；`len` 超过 1 MiB bounce buffer。
- 执行顺序（任何一步失败即停）：
  1. 打印 4 行 banner，其中含 `DO NOT POWER OFF DURING WRITE`；
  2. 源读入 bounce buffer，打印 `staged payload CRC32`；
  3. 块对齐擦除；
  4. 读回校验全 `0xFF`；
  5. 从 bounce buffer 写入；
  6. 读回逐字节比较（首个不一致偏移立即 FAIL）；
  7. 打印 `readback CRC32` 与 PASS。
- 关键输出（供 CI/真机脚本解析）：

```
e2631flash: ****************************************
e2631flash: DO NOT POWER OFF DURING WRITE
e2631flash: flash source 0x03f00000 -> flash 0x00020000..0x000c0000
e2631flash: 0xa0000 bytes, 5 erase blocks, 0x20000 bytes each
e2631flash: staged payload CRC32 0x........
e2631flash: PASS: 0xa0000 bytes at 0x00020000 written and verified
e2631flash: payload CRC32 0x........, read-back CRC32 0x........
```

### 2.2 e2631verify `<ram地址> <off> <len>`

只读：计算 RAM 缓冲区与 flash 范围的 CRC32，打印两行后给出 PASS/FAIL；不擦、不写、不碰 env。
用于串口调试场景（正常更新路径由 `e2631flash` 的 staged payload CRC32 承担校验）。

### 2.3 e2631slot

打印两个槽的 base/span/serial/version、内层头偏移，以及 cspboot 会选中的槽；内部直接复用
`e2631boot` 的 `e2631_scan_slot`/`e2631_pick_slot`，不复制扫描逻辑。只读。

### 2.4 usage 文本（上游/CI 门禁按原文匹配）

- `e2631flash`：`flash an image to SPI-NAND with erase, blank and readback checks`
- `e2631verify`：`compare a RAM image with a SPI-NAND range by CRC32 (read-only)`
- `e2631slot`：`print the firmware slot table`

## 3. CMD_MTD_WRITE：把原始写入口编掉

`CONFIG_CMD_MTD` 自带 `mtd write`/`mtd erase` 子命令，和 `e2631flash` 并存等于镜像里有第二条无保护写路径。
补丁 0015 增加 `CONFIG_CMD_MTD_WRITE`（bool，依赖 `CMD_MTD`，默认 y，保持上游语义），把以下代码放到
`#if CONFIG_IS_ENABLED(CMD_MTD_WRITE)` 之后：

| 位置 | 内容 |
| --- | --- |
| `cmd/mtd.c` | `mtd_special_write_oob()`、`do_mtd_io()` 的写分支、整个 `do_mtd_erase()`、子命令表中的 `write`/`erase` 两项 |
| `cmd/Kconfig` | 新 `CONFIG_CMD_MTD_WRITE` 选项 |
| defconfig | `# CONFIG_CMD_MTD_WRITE is not set`（这是本板唯一的差异；上游默认仍为 y） |

read/dump 不受影响。`env/mtd.c` 不是第二条写路径：`# CONFIG_CMD_SAVEENV is not set` 时
`ENV_SAVE_PTR`/`ENV_ERASE_PTR` 展开为 NULL，函数没有被引用，ARM 链接的 `--gc-sections` 把对应段丢掉。

CI 侧（`.github/workflows/uboot-build.yml`）用**调用点白名单**证明这一点：对 `build/u-boot` 反汇编，
所有落到 `mtd_write`/`mtd_erase`/`mtd_special_write_oob` 的 `bl` 必须位于 `e2631_write_range`、
`e2631_erase_range` 或 `do_e2631flash` 内，且至少存在一个写调用点（防止白名单空过）。

## 4. 真机更新流程（需用户批准；先零写入）

1. （Linux 侧，以太网）把 mtd0 新镜像写入 userdata：`/dev/mtd10`，U-Boot 视角偏移 `0x3F00000`；
   记录主机 sha256/CRC32。
2. 重启进入本 U-Boot（正常启动即自动 `e2631boot`；需要停在提示符时中断 autoboot）。
3. 零写入预检：`e2631slot` 看槽位表；`e2631flash 3f00000 20000 a0000` 会先打印 staged payload
   CRC32——**先核对 CRC 再让它擦写**（当前实现没有单独的 flash→flash 只读比较命令；如需纯只读，
   用 RAM 源 `e2631verify`）。
4. 写前记录 mtd0（`0x00000..0x100000`）sha256；执行写入；写后读回比较 + 记录新 mtd0 sha256。
5. 断电重启，确认 banner/`e2631boot`/内核/PCIe/WiFi 正常。

救砖路径仍是串口 + 厂商/第二级引导链（见 `p2-c1b-rescue-prep-20261121.md`）；不能在无串口恢复
手段时执行写入。

## 5. 验收

- CI：patch 0014/0015 应用后 tree 校验、镜像含 `e2631flash`/`e2631verify`/`e2631slot` 与三条 usage 文本、
  `.config`/defconfig 的 `# CONFIG_CMD_MTD_WRITE is not set`、调用点白名单、尺寸 ≤ 0x9F800、entry 0x47F00000、
  checkpatch 0 errors（0014 0/4、0015 0/5，均为已核对项）。
- 真机（下一次会话）：`e2631slot` 输出与设备已知槽位一致；零写入阶段核对 staged payload CRC32；写入阶段
  读回 PASS 且 mtd0 sha256 前后按预期变化；重启冷启动成功。

## 6. 风险与回退

- 写入期间掉电 → mtd0 半写，需要串口救砖；因此先零写入核对 CRC、单独一次写入、写前写后 sha256 留档。
- 命令只允许写用户给定范围，并硬拒绝 secondboot/env；bounce buffer 固定 `0x44000000`（1 MiB，避开
  内核 load、uImage 暂存区与重定位后的 U-Boot）。
- 回退：删掉 `e2631boot.c` 里的命令注册/包含即可回到无自更新命令的状态；不使用命令时不会写 flash。
- 不影响 0011–0013 的启动路径：`e2631flash` 只在用户执行命令时运行，autoboot 流程不调用它。
