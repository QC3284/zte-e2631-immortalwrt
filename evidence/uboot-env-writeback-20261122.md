# U-0017：U-Boot env 写回交付与 CI 构建（2026-11-22）

## 0. 结论

- patch 0017 已交付并合并进 kit 的 `uboot-port/` 系列：新增 `e2631env check/diff/save`，它是镜像里**唯一**的
  env 写入口；`env/mtd.c` 的 `.save` 保持 NULL，`CONFIG_CMD_SAVEENV`/`CONFIG_CMD_ERASEENV` 继续编译掉。
- 系列重钉：17 个 patch，post-am tree `fd511f1e4aff26c8f0bf3187b139eaaf45fbd5bc`，patch 0017 sha256
  `da21478e0fe7c53fdf14f59e81ea3da86733b63998926f25e84b3675f96eca0d`。
- uboot-build CI run **44978733720**（head `b42e44d`）SUCCESS：banner `g9a4028535269`，`u-boot.bin` 465,600 B
  sha256 `e46f9cf0fdffe7173b7acbdcdc9f9506002c0f09fa6fbf850fa10c31255a9bee`，mtd0 镜像 sha256
  `e2a76f753152403a42bd7f8faf01c5c3cab1c44a4b12c2744600fc4296784e16`，env 块 `6eee153b…` 未变。
- **尚未真机写入**：第一次 `e2631env save` 必须并入用户批准的设备会话（见 §7）。

## 1. 背景

- 0006/0007 起我们的链从厂商块 `mtd0 0xC0000`（`0x20000` = 一个擦除块）只读加载 env，`saveenv` 编掉。
- D-U1（0014/0015）把 MTD 写入口收敛到 `e2631flash`，但 env 一直没有可写通道；D-U2 设计（docs/
  U-Boot-env写回与启动计数设计-2026-11-22.md）选择 W1：不开通用 `saveenv`，只提供一个受控的 env 写命令。
- Lead ruling（2026-11-22）：采用 Option A —— 五步安全写放进 `e2631env.c`，**不 wire** `env/mtd.c` 的 `.save`，
  让通用 `env_mtd_save()` 根本不进镜像；D-U1 白名单相应覆盖两个安全 writer。

## 2. 交付内容

| 项 | 内容 |
| --- | --- |
| patch 0017 | `uboot-port/patches/0017-board-zte-add-a-whitelisted-environment-writer.patch`（882 行 patch，+789/−4，4 文件） |
| 新文件 | `board/zte/zxhn-e2631/e2631env.c`（约 790 行）、`e2631env.h` |
| 修改 | `board/zte/zxhn-e2631/Makefile`（`obj-y += e2631env.o`）、`e2631boot.c`（include + `board_late_init()` 里 `e2631_env_snapshot()`，在覆盖 `bootcmd` 之前） |
| 命令 | `e2631env check`（读块/解析/重算 CRC，只读）、`e2631env diff`（构建候选并列出变化键，不写）、`e2631env save`（五步写） |

`save` 的语义：

1. 读当前块：全 0xFF 视为首次写；非空但 CRC/解析坏 **拒绝**（见 §5 偏差）；有效则解析出 old 键表。
2. 构建候选：`memset` 0 → 恢复 `bootcmd/bootargs/memsize/versioninfo` 快照 → `env_export()`（CRC + key/value 串）。
3. 逐键 diff（顺序无关）：无变化 → `nothing to write, env block left untouched`，**连擦除都不做**。
4. 白名单：只允许 `e2631_*` 与 `bootdelay`；其它键有差异 → 列出并拒绝（`-EPERM`，无 force）。
5. 写前检查 `0xE0000..0xFFFFF` 保留扇区仍全 0xFF，打印 `DO NOT POWER OFF DURING WRITE` 与 old/new CRC。
6. 五步写：坏块预检（`mtd_block_isbad`，在擦除之前）→ 擦除 → 读回全 0xFF 校验 → 写入 → 读回逐字节比较。
7. 写后再查保留扇区，打印 old/new CRC 与变化键数，`env_set(bootcmd, e2631boot)` 保持 RAM 状态。

## 3. 安全不变量

- 地址只来自冻结常量：`CONFIG_ENV_OFFSET=0xc0000`、`CONFIG_ENV_SIZE=0x20000`；4 条 `static_assert`
  （offset、size、擦除块对齐、`sizeof(env_t)==CONFIG_ENV_SIZE`）。
- 运行期再查 `mtd->erasesize == CONFIG_ENV_SIZE`，不匹配拒绝写。
- 坏块预检位于擦除之前（CI 用源码行号断言）；擦除后必须读回全 0xFF 才写；写完必须逐字节相等（CRC 隐含）。
- `0xE0000..0xFFFFF` 保留扇区写前写后都断言全 FF（设计 Q5）。
- 不做冗余 env（`CONFIG_SYS_REDUNDAND_ENVIRONMENT` 不能打开）。
- 没有地址参数，也没有 `--force`；`saveenv`/`eraseenv` 仍不可用。

## 4. CI 门禁（.github/workflows/uboot-build.yml）

- 配置：`# CONFIG_CMD_SAVEENV is not set`、无 `CONFIG_CMD_ERASEENV=y`、无 `CONFIG_SYS_REDUNDAND_ENVIRONMENT=y`，
  以及原有的 `CONFIG_ENV_IS_IN_MTD=y`/`CONFIG_ENV_MTD_DEV`/offset/size 断言。
- 源码形状：`e2631_env_snapshot` 在 `e2631boot.c`；`e2631_env_write_block` 在 `e2631env.c`；
  `mtd_block_isbad` 行号 < `mtd_erase` 行号；`static_assert(` 恰好 4 条；`0xE0000` 只出现在 `e2631env.c`。
- 二进制：`e2631env` 命令与 help 首行、`DO NOT POWER OFF` 都在 `build/u-boot.bin`。
- D-U1 白名单：所有 `mtd_write`/`mtd_erase`/`mtd_special_write_oob` 调用点只能落在
  `e2631_write_range`/`e2631_erase_range`/`do_e2631flash`/`e2631_env_write_block`/`do_e2631env_save`，且**恰好 4 个**；
  运行输出 `mtd writer sites: 4 (e2631flash and the e2631env writer; -O2 inlines the static helpers)`。
- checkpatch：整个系列 0 errors / 22 reviewed warnings（0017 自身 0 errors / 2 warnings：新文件 MAINTAINERS 提醒 +
  自用板级命令 CMD_TEST，均为已登记豁免）。
- 失败轨迹（留档）：run 44978366516 在“4 条 static_assert”计数上失败（第 4 条首参是 `sizeof(env_t)`，grep 模式只看到 3 条）；
  run 44978533016 在调用点白名单上失败（`-O2` 把 `e2631_env_write_block` 内联进 `do_e2631env_save`，符号名变了）。
  两处都是 CI 断言实现问题，不是补丁逻辑问题；分别由 `8c998b6`、`b42e44d` 修正。

## 5. 与设计稿的偏差（有意，已在设计文档 §12 记录）

1. **不 wire `.save`**：通用 `env/mtd.c` 写路径不进镜像；白名单覆盖两个安全 writer（e2631flash + e2631env）。
2. **非空坏 CRC 块拒绝重建**：坏 CRC 时 U-Boot 回退到默认 env，快照里没有厂商键（`ethaddr` 等），重建会静默丢键；
   恢复交给厂商链 `zteboot_do_settings`（它重建并 saveenv）或用户显式修块。空白块（全 FF）仍允许首次写。

## 6. 本地静态验证（本机不编译，配置检查与单文件语法检查例外）

- 干净 worktree 上按 kit 的 17 个 patch 顺序 `git am`：17 个 commit，tree == `fd511f1e4aff26c8f0bf3187b139eaaf45fbd5bc`。
- `make zx279128s_zte_zxhn-e2631_defconfig` 后 `.config`：`CONFIG_ENV_OFFSET=0xc0000`、`CONFIG_ENV_SIZE=0x20000`、
  `CONFIG_ENV_IS_IN_MTD=y`、`# CONFIG_CMD_SAVEENV is not set`、`# CONFIG_CMD_MTD_WRITE is not set`、无 ERASEENV/
  REDUNDANT；`savedefconfig` 往返一致。
- host gcc `-fsyntax-only`（用生成的 autoconf.h、`-DDO_DEPS_ONLY`）检查 `e2631env.c` 与 `e2631boot.c`：0 errors；
  修掉了 `%zu` 与 U-Boot printf 的格式不匹配、`crc32()` 的指针符号警告、一个 set-but-unused 变量。
- patch 0017 单 commit checkpatch：0 errors / 2 warnings / 0 checks（817 行）。
- kit `make check` 与 `node tools/check-workflows.mjs` 均通过（pin 数 == patch 文件数、tree 断言、workflow 解析）。

## 7. 构建产物（CI run 44978733720，head `b42e44d`）

| 项 | 值 |
| --- | --- |
| banner | `U-Boot 2027.01-rc2-g9a4028535269 (Nov 22 2026 - 03:03:00 +0000)` |
| `u-boot.bin` | 465,600 B（0x71ac0，上限 653,312），sha256 `e46f9cf0fdffe7173b7acbdcdc9f9506002c0f09fa6fbf850fa10c31255a9bee`，crc32 `224214eb` |
| mtd0 镜像 | 655,360 B，sha256 `e2a76f753152403a42bd7f8faf01c5c3cab1c44a4b12c2744600fc4296784e16`，crc32 `b7e5b7d1` |
| 装配后 mtd0 首 0x800 sha256 | `1bd3fa812368af4cc2eaa5c8ea5fabf82bd8f679886d378e362e491790813f91`（≠ UBOOT-INFO 的模板头 19a9d546…，因为 +0x14 长度字段被重写） |
| payload 末端 | 0x20800 + 0x71ac0 = 0x922c0，未触及 0xC0000 env 区 |
| env 块 | sha256 `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`（未变） |
| `.config` | sha256 `91ef0e4d33a4beef46b16e7448a7452aae2463ff71efc732121e81542efda806`（与 0016 相同） |
| 命令 help | `E2631-COMMAND-HELP.txt` 含 `e2631env` 三个子命令与“bad-block precheck, erase, verify all-0xFF, write, read back and compare” |

产物下载目录：`/home/qc233/zte/e2631-t5-artifacts/uboot-u0017-44978733720/e2631-uboot-44978733720/`。

## 8. 真机待办（需用户批准；本任务未接触设备）

建议的零风险第一步（RAM 链，只读写 env 块）：

1. 厂商控制台 `tftp 0x47F00000 u-boot.bin`（465,600 B，核对 sha256）+ `go 0x47F00000`，确认 banner `g9a4028535269`。
2. `e2631env check`：应打印 `stored CRC 0x…, calculated CRC 0x… (valid)` 与 22 条厂商键。
3. `setenv e2631_boot_marker test` 后 `e2631env diff`：只应列出 `e2631_boot_marker` 一条变化。
4. `e2631env save`：应打印 `DO NOT POWER OFF`、`erase verified (all 0xFF)`、`read back 131072 bytes, CRC 0x… matches`、
   `Saving Environment to MTD... OK`、old/new CRC；写前写后各记一次 `0xC0000` 块 sha256（可由 `e2631verify`/`md` 核对）。
5. 再跑一次 `e2631env save`：应打印 `nothing to write`，不产生擦写。
6. 断电冷启动回厂商链确认 env 可读（厂商链会读同一块）；本次不写 image 区。

## 9. 风险与边界

- 五步写只在 CI/代码层证明；第一次真机 save 前必须 `diff` 核对键列表，写前记录 `0xC0000` 块 sha256。
- 写入期间掉电只影响 env 块：两条链都会回到默认 env，厂商 `zteboot_do_settings` 会重建；但不要在高价值变量变更时
  同时断电。
- 白名单依赖源码/内联形态：若将来函数不再内联、或新增 env 写函数，CI 的 4-site 断言会失败，需要显式更新白名单与
  本证据。
- e2631flash 的 bounce buffer 在 `0x44000000`，与 env 无关；task-66 规划中的 16 MiB 网络 arena（`0x45000000`）
  会要求给 e2631flash 增加 arena 重叠保护（见 task-66 卡），本 patch 未改 e2631flash 的地址检查。

## 10. 参考

- 设计：[docs/U-Boot-env写回与启动计数设计-2026-11-22.md](../docs/U-Boot-env写回与启动计数设计-2026-11-22.md)（§12 实现注记）
- kit 变更：`993263c`（patch 0017 + pins + workflow + README + 设计注记）、`8c998b6`、`b42e44d`（CI 断言实现修正）
- CI：https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44978733720
- 上一条证据：[evidence/uboot-class1-fallback-20261122.md](uboot-class1-fallback-20261122.md)
