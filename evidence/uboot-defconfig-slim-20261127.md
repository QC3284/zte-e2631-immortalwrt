# E4 前置：defconfig 瘦身（去掉 EFI/MMC/FAT/标准启动栈）— 2026-11-27

任务：task-69（Lead m06142）。目的：把这块板用不到、但默认被 Kconfig 拉进来的子系统
从 U-Boot 镜像里删掉，为 E4 救援模式（Option A，预算 ≤34 KB 增量）腾空间；只改
defconfig，不改任何代码路径。

## 0. 结论

- 变更只有一行：`configs/zx279128s_zte_zxhn-e2631_defconfig` 增加
  `# CONFIG_MMC is not set`（patch 0025，sha256
  `af158e9fb09bc1853a0ff7bf5a32d7201b9ebf8dd04a02a1087e0cccf76218d4`）。
- 级联后 `.config` 少 **56 个 `=y` 符号、0 个新增**；控制台少 `bootefi`、`eficonfig`、
  `bootflow`、`blkcache` 四条命令（FAT/MMC/PXE 命令本来就没编进去）。
- `u-boot.bin` 从 **494,880 B 降到 320,848 B**：**-174,032 B（-35.17%）**，
  距 CI 门禁（645,120 B）余量 324,272 B，距硬上限（653,312 B）余量 332,464 B。
- 启动、MTD 写、网络与 env 语义均未改；MTD 写白名单仍是 4 个调用点、只有
  `e2631flash` + `e2631env` 两个写者。

## 1. 机制（为什么一行就够）

- `CONFIG_MMC` 在 ARM 上 `default y`，并且 `select BLK`、`select DM_MMC`。
- `CONFIG_EFI_LOADER` 在 armv7 上 `default y`，但 `depends on BLK`；BLK 消失后它
  不可见，连带 `EFI`/`EFI_BOOTMGR`/`EFI_VARIABLE_FILE_STORE`/`EFI_DEVICE_PATH_*` 等，
  以及 `EFI_LOADER` 的 `select`（CHARSET/DM_EVENT/EVENT_DYNAMIC/LIB_UUID/LMB 部分）
  与 `imply FS_FAT/FAT_WRITE/FAT_RENAME` 一起消失。
- `CONFIG_BOOTSTD` 是 `default y if BLK`；BLK 消失后标准启动（bootflow/bootmeth/PXE）
  整条链消失。
- `CMD_PXE`、`CMD_MMC`、`CMD_FAT` 本来就没启用；显式写它们的 not-set 行会被 kconfig
  丢弃，所以最终 defconfig 只需 MMC 一行（`make savedefconfig` 往返稳定）。
- 没有被保留项 force-select：这是真正的“自由”符号，不需要 `#ifdef` 对抗 Kconfig。

## 2. 56 个消失的 `=y` 符号（按子系统）

- 块/MMC：`BLK`、`BLOCK_CACHE`、`DM_MMC`、`MMC`、`MMC_HW_PARTITIONING`、
  `MMC_QUIRKS`、`MMC_VERBOSE`、`MMC_WRITE`、`SYS_MMC_MAX_BLK_COUNT`；
- EFI：`EFI`、`EFI_LOADER`、`EFI_LOADER_HII`、`EFI_BINARY_EXEC`、`EFI_BOOTMGR`、
  `EFI_DEBUG_SUPPORT`、`EFI_DEVICE_PATH_TO_TEXT`、`EFI_DEVICE_PATH_UTIL`、
  `EFI_DT_FIXUP`、`EFI_EBBR_2_1_CONFORMANCE`、`EFI_ECPT`、`EFI_GRUB_ARM32_WORKAROUND`、
  `EFI_LOAD_FILE2_INITRD`、`EFI_PLATFORM_LANG_CODES`、`EFI_UNICODE_CAPITALIZATION`、
  `EFI_UNICODE_COLLATION_PROTOCOL2`、`EFI_VARIABLE_FILE_STORE`、`EFI_CAPSULE_MAX`、
  `EFI_VAR_BUF_SIZE`、`BOOTEFI_HELLO_COMPILE`、`BOOTEFI_TESTAPP_COMPILE`；
- 标准启动/PXE：`BOOTSTD`、`BOOTSTD_BOOTCOMMAND`、`BOOTMETH_EFILOADER`、
  `BOOTMETH_EFI_BOOTMGR`、`BOOTMETH_EXTLINUX`、`BOOTMETH_GLOBAL`、
  `BOOTMETH_PXE_COMMON`、`BOOTDEV_ETH`、`PXE_UTILS`；
- FAT：`FS_FAT`、`FS_FAT_MAX_CLUSTSIZE`、`FAT_WRITE`、`FAT_RENAME`；
- 连带库：`CHARSET`、`EVENT`、`EVENT_DYNAMIC`、`DM_EVENT`、`LIB_UUID`、
  `PARTITION_UUIDS`、`SHA1`、`SHA1_LEGACY`、`SMBIOS`、`GENERATE_SMBIOS_TABLE`、
  `MENU`、`LAST_STAGE_INIT`；
- 命令：`CMD_BLOCK_CACHE`、`CMD_BOOTEFI`、`CMD_BOOTEFI_BINARY`、`CMD_BOOTEFI_BOOTMGR`、
  `CMD_BOOTFLOW`、`CMD_EFICONFIG`。

## 3. 保留验证（CI 逐步断言）

- `bootm` 路径：`CONFIG_CMD_BOOTM=y`、`CONFIG_OF_LIBFDT=y`、`CONFIG_LMB=y`；
- 自持命令：`e2631boot`/`e2631soc`/`e2631refclk`/`e2631flash`/`e2631verify`/
  `e2631slot`/`e2631env`/`e2631net` 全部仍链接（二进制字符串门禁）；
- MTD/网络：`CMD_MTD`、`DM_MTD`、`MTD_SPI_NAND`、`SPI_ZX`、`ETH_ZX279128S`、
  `MDIO_ZX279128S`、`CMD_DHCP`、`CMD_MII`、`CMD_PING`、`CMD_TFTPBOOT` 全部 =y；
- 安全门禁保持：`# CONFIG_CMD_SAVEENV is not set`、`# CONFIG_CMD_MTD_WRITE is not set`；
- D-U1 白名单：`mtd writer sites: 4`，仍是 `e2631flash` helpers + `e2631env` 写者；
- 新增 CI step「Assert the unused EFI/MMC/FAT/standard-boot stack stays compiled out」：
  同时断言消失的（MMC/FS_FAT/BOOTSTD/CMD_PXE not-set；EFI/BLK/FAT/CMD_BOOTEFI 等不是 =y）
  与必须保留的（bootm/MTD/DHCP/TFTPBOOT/MII/PING/OF_LIBFDT/LMB）两组符号。

## 4. 构建结果（uboot-build run 45988430055，head 98592c2）

- 结果：SUCCESS（全部 14 步绿，含新瘦身门禁与 checkpatch 0 errors / 0 warnings）；
- banner：`U-Boot 2027.01-rc2-ge6678e875e60 (Nov 19 2026 - 15:44:39 +0000)`；
- `u-boot.bin`：320,848 B，sha256 `339289583f80bd60b7214fa65ad9a4b5a3ca68eb37d95bd1bad65215265ee2fa`，
  crc32 `92257c50`；entry `0x47f00000`；
- mtd0 镜像：655,360 B，sha256 `99886ea0966877fa4978faad2b52df58ceb698ad627a049763957ddbb92bfe51`，
  crc32 `13051599`；载荷长 320,848 B（0x4e550）；装配后首 0x800 B sha256
  `22b12c5adc0d5cc9c06eb2299d9755c8649318d19621736a17b5d25b2cd47c8f`
  （模板输入仍是 `19a9d546…`，两者不是同一个哈希）；
- env 块：`6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`，未变；
- `.config` sha256：`5bc9f529b06e0cde78f6147abe14ddcfb114c58eaf14aeb5ba636a0e003cdfb1`；
- 25 patches，post-am tree `ac98701595404b43ecd48ea43d6ff7f3cf7676fb`；
- 产物：`/home/qc233/zte/e2631-t5-artifacts/uboot-defconfig-45988430055/e2631-uboot-45988430055/`。

## 5. 尺寸前后对照（同一基线、同一构建参数）

| 项 | 24 patch（run 45985501668） | 25 patch（run 45988430055） | 变化 |
|---|---:|---:|---:|
| u-boot.bin | 494,880 B | 320,848 B | -174,032 B（-35.17%） |
| 距 CI 门禁 645,120 B | 150,240 B | 324,272 B | +174,032 B |
| 距硬上限 653,312 B | 158,432 B | 332,464 B | +174,032 B |
| mtd0 镜像 | 655,360 B | 655,360 B | 0（mtd0 布局不变） |

超过对象表估算：EFI loader 100,460 + MMC 14,321 + FAT 16,835 + bootstd/PXE 18,604
≈ 150,220 B 只是对象 `.text` 口径；实际链接还删掉了 event/SMBIOS/SHA1/UUID 等
helper 与 stdio/menu 等连带代码，所以省下 174 KB。

## 6. 影响与风险

- 正常启动/刷写/网络路径不受影响：没有任何 `e2631*` 或 bootm/MTD/net 代码被改；
- 失去的只是本板用不到的命令（bootefi/eficonfig/bootflow/blkcache）与它们的库；
- 若以后某功能需要块设备（BLK），重新打开 BLK 会让 EFI/BOOTSTD/FAT 按默认值回来；
  新 CI 门禁会在那时立刻失败，迫使在 defconfig 里显式关掉它们（不要用 #ifdef 对抗）；
- 本任务未做设备操作、未刷写、未派第二次构建。

## 7. 复现

- patch 0025 的 defconfig 行 + `make defconfig`；
- CI：`gh workflow run uboot-build.yml --ref iwrt-adaptation -R QC3284/zte-e2631-immortalwrt`；
- 尺寸表：artifact 内 `UBOOT-SIZES.txt`；命令帮助：`E2631-COMMAND-HELP.txt`；
- 关联：`uboot-port/README.md` §1 pin 表（0025/tree）、§4 item 17、§8 变更记录。
