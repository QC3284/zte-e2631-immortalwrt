# E4-发1：U-Boot 载荷体积门禁与 footprint / 分项尺寸报告（task-71）

日期：2026-11-27。范围：CI / tooling / docs only —— 不动 `uboot-port/patches`，不动树 fork，
不建 Release / tag，不碰真机。task-71 卡在 rev3 增加第 3 项（逐对象尺寸表）。

## 1. 为什么

多功能 U-Boot（E4，参考 bl-mt798x-dhcpd）要在现有镜像里加 DHCP server 和 web UI，而载荷窗口
被封死在 mtd0 `0x20800..0xBFFFF`：secondboot 按封装头 +0x14 的长度从 mtd0 0x20800 拷贝载荷，
载荷区到 0xBFFFF 结束，env 区从 0xC0000 开始。硬上限 **0x9F800 = 653312 B（638 KiB）**。
原来的门禁只卡硬上限、且失败信息没有门限值；空间成为一等约束后，需要：

1. 带 8 KiB 安全余量的门禁（**645120 B**），在拼装 mtd0 之前就失败；
2. 每次构建记录 footprint（实测/上限/余量/env/.config sha256）；
3. 权威的逐对象 `.text` 尺寸表，给 E4 选捐献者（EFI loader / MMC / FAT / bootflow+PXE / 命令集）；
4. checker 与文档把这些数字钉住。

## 2. 实现

### 2.1 载荷门禁（`uboot-build.yml`，"Enforce the A1 acceptance gates"）

```sh
size=$(stat -c%s build/u-boot.bin)
max=$((E2631_UBOOT_PAYLOAD_MAX))          # 0x9F800 = 653312
margin=8192
gate=$((max - margin))                    # 645120
if [ "$size" -gt "$gate" ]; then
  echo "::error::u-boot.bin is $size bytes, above the CI gate $gate bytes (hard cap $max bytes, $margin byte safety margin); observed $size, limit $gate"
  exit 1
fi
```

门禁位于 "Package the flashable mtd0 image" 之前，超限时不产出 mtd0 镜像；失败信息同时打印实测值
与门限值（原文 `observed $size, limit $gate`）。

### 2.2 footprint 表（`UBOOT-INFO.txt`）

```
payload footprint (mtd0 payload window 0x20800..0xBFFFF, hard cap 653312 bytes):
  u-boot.bin bytes: 494880
  mtd0 image bytes: 655360
  hard cap bytes: 653312
  CI gate bytes: 645120 (hard cap - 8192 safety margin)
  headroom bytes vs hard cap: 158432
  headroom percent vs hard cap: 24.25%
  headroom bytes vs CI gate: 150240
  env block sha256: 6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426
  .config sha256: fbbfeb1dbed7dc90df7e75320d5e6b3976661108794811d2fc4220aa55d9a73d
```

### 2.3 逐对象尺寸（`UBOOT-SIZES.txt`）

**更正一个前提**：pinned U-Boot（c1958b5f，v2027.01-rc2）和 upstream master 的顶层 Makefile
都**没有 `sizes` 目标**（`grep -n sizes Makefile` 无命中；上游 master 同）。因此 CI 用与这类
目标等价的口径直接算：对 `build/` 下每个 `.o` 跑 `arm-none-eabi-size`，加上链接镜像总量，
按 `.text` 降序排序。表头记录 post-am tree 与工具链，空表或对象行 <100 即失败（防空跑）。

```
# linked image total:
#  474963	  19900	      0	 494863	  78d0f	build/u-boot
# objects:  (282 rows, sorted by .text desc)
```

产物 `UBOOT-SIZES.txt`（15,635 B，sha256 `9f8a19ea…`）已列入 `SHA256SUMS`（7→8 项）与
step summary。

### 2.4 checker（`tools/check-workflows.mjs`，99 → 103 PASS，新增 4 项）

* 门禁常量与顺序：`margin=8192`、`gate=$((max - margin))`、`$size -gt $gate`、
  失败文案 `above the CI gate $gate bytes` / `observed $size, limit $gate`，且门禁文本在
  "Package the flashable mtd0 image" 之前（用 `lastIndexOf`，因为门禁注释也提到后一步）；
* 文档一致性：`uboot-port/README.md` 的 `0x9F800` / `653312` / `638 KiB` 与
  `BUILD.md` 的 `653312` / `645120` / `8192` / `0x20800..0xBFFFF`；
* footprint 字段齐全（10 个字段）；
* `UBOOT-SIZES.txt`：`arm-none-eabi-size`、`xargs -0 -r`、sorted by text desc、
  无 `make sizes` 的说明、行数下限，且出现在 `SHA256SUMS` 里。

### 2.5 文档（`BUILD.md` 新增 §9）

上限来源、现用量/余量（2026-11-27，24 patch：494880 B，余量 158432 B = 24.25%，
距门禁 150240 B）、门禁规则、footprint 字段、`UBOOT-SIZES.txt` 的用法与"不要动 8 KiB 余量"。

## 3. CI 事实

| run | head | 结论 | 说明 |
|---|---|---|---|
| check.yml 45984657180 | 37ddcc6 | success | 门禁 + footprint 代码 |
| uboot-build 45984779157 | 37ddcc6 | success | run 32：证明门禁与 footprint（当时还没有 sizes 步骤） |
| check.yml 45985469934 | 454c105 | success | sizes 步骤 + checker + BUILD.md |
| uboot-build 45985501668 | 454c105 | success | run 33：footprint + UBOOT-SIZES.txt，artifact id 15191856388 |

run 33 产物：`e2631-uboot-45985501668`，zip 622,794 B，sha256
`65ccc53834c085614131b4437d8c866501a9f0fb3f21d6a7da68fdc66ef7c4fb`；
`sha256sum -c SHA256SUMS` 8/8 通过。u-boot.bin 494,880 B sha256
`15bfa0c1484d96a4ab90e774a47798251116a9abebd3480f29762dabf64d692a`；
mtd0 655,360 B sha256 `c45baf4fd1831ec90b501f78dc1c02f18da0fd2bae80ba9f142a1a9a81895ae7`。

provenance 说明：sizes 步骤是在共享工作树里被并发提交 `8e16330`（task-69 items 1/2）一并
带进去的（我的提交 `454c105` 只带 checker + BUILD.md）；内容在 HEAD `454c105` 与 run 33
中复核无误。task-69 的补丁把 pin 推进到 24 patch / tree `721bb825`，因此 run 33 的
u-boot.bin 比 run 32 大 672 B，余量相应缩小，两组数字都符合门禁。

## 4. run 33 逐对象 .text 前 20 行

| text | data | bss | object |
|---:|---:|---:|---|
| 16835 | 0 | 132 | `build/fs/fat/fat_write.o` |
| 13271 | 337 | 25 | `build/lib/efi_loader/efi_boottime.o` |
| 12154 | 0 | 0 | `build/lib/zlib/zlib.o` |
| 11734 | 116 | 9 | `build/cmd/eficonfig.o` |
| 11701 | 0 | 0 | `build/boot/fdt_support.o` |
| 10065 | 64 | 4 | `build/drivers/mmc/mmc.o` |
| 9889 | 68 | 4 | `build/drivers/mtd/nand/spi/core.o` |
| 9327 | 0 | 0 | `build/lib/fdtdec.o` |
| 8166 | 63 | 1028 | `build/cmd/fdt.o` |
| 7941 | 0 | 0 | `build/drivers/core/ofnode.o` |
| 7813 | 0 | 0 | `build/boot/pxe_utils.o` |
| 7148 | 28 | 645 | `build/board/zte/zxhn-e2631/e2631env.o` |
| 6551 | 0 | 0 | `build/lib/sha1.o` |
| 6442 | 0 | 24 | `build/lib/efi_loader/dtbdump.o` |
| 5955 | 0 | 30 | `build/boot/image.o` |
| 5696 | 28 | 26 | `build/cmd/mii.o` |
| 5658 | 140 | 0 | `build/cmd/mtd.o` |
| 5657 | 24 | 0 | `build/drivers/mtd/mtdpart.o` |
| 5632 | 96 | 4 | `build/drivers/net/zx279128s_eth.o` |
| 5458 | 56 | 0 | `build/board/zte/zxhn-e2631/e2631flash.o` |

链接镜像总量：text 474,963 / data 19,900 / bss 0（`build/u-boot`）。

归档：`/home/qc233/zte/e2631-t5-artifacts/t71-run1-45984779157/`（run 32）与
`/home/qc233/zte/e2631-t5-artifacts/t71-run33-45985501668/`（run 33）。

## 5. 边界

未建 Release/tag（仓库 Releases 仍只有 v1.10.0）；kit main 未动；`uboot-port/patches` 与树 fork
没有因本任务改动；未碰真机；`firmware.yml`/`check.yml` 未改。
