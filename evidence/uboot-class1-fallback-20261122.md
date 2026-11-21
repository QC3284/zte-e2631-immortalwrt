# U-0016：e2631boot 的 class-1 跨槽回退（2026-11-22）

## 0. 结论

- 补齐 cspboot 的 class-1 parity 缺口：选中槽的 uImage 任一级校验失败时，`e2631boot` 自动改试另一槽一次；两槽都失败才回控制台。
- 交付为单个补丁 0016（`board/zte/zxhn-e2631/e2631boot.c`，+81/−12），**零 flash 写、零 env 写**；选槽规则、版本头校验、`e2631slot` 的扫描/选择代码都不变。
- 重钉：16 个 patch，post-am tree `13c92c68921fa781634beb50d0eaffd50e9a7648`；补丁 sha256 `7838e8a22dd46996c9ccb31f9fe116e194641d2a26f548e9854548bfefc62461`。
- CI uboot-build run `44945090940`（head `8811a5b`）SUCCESS：banner `g61456c131301`、u-boot.bin 457,680 B sha256 `31d2b6d8…f659977`、mtd0 镜像 sha256 `869866d4…dc58ea`、env 块未变、checkpatch 0 errors / 20 warnings（0016 本身 0/0）。
- **运行期回退尚未真机演练**：需要人为破坏选中槽 uImage（写 slot 区，需单独批准）或等真实坏槽；本轮只有静态 + CI 证明。

## 1. 背景与差距

cspboot 的选择/回退是两段式、无状态的（设计文档 §6.1）：两个版本头都合法时选 serial 较大者（相等取 slot0）；选中槽的内核 CRC 不合格（class-1）时判该槽无效并自动改启另一个合法槽（`pdt_getreal_kernelfs` 的 `csp_crc` 路径，日志 `not found vaild fs!! -> Total found 2 firmwares(valid:1)`）；class-2（内核起了但用户态不健康）两链都无自动补救。

我们的 patch 0006（`e2631boot`）复刻了选择规则，但在任一 uImage 校验失败时直接返回 `CMD_RET_FAILURE`，源码注释也写着 “There is no automatic fallback to the other slot.”。结果：选中槽 uImage 坏、另一槽完好时，厂商链能起、我们不能。

## 2. 交付内容（patch 0016，单文件 +81/−12）

- `e2631_load_kernel()` 增加 `const char **whyp` 输出：失败时给出短原因，调用方据此打印回退日志。原因串：
  `unreadable uImage header`、`no plain Linux uImage`、`bad uImage header CRC`、`uImage size outside the kernel window`、
  `short kernel read`、`bad uImage data CRC`。原有逐项详细日志保留。
- 新增 `e2631_try_boot_slot()`：版本头无效时返回 `-ENOENT`（原因 `no valid version header`），否则调用 `e2631_load_kernel()`。
- `do_e2631boot()`：按 cspboot 规则选槽后先试选中槽；失败则打印并试另一槽一次。回退只影响本次启动，不写任何持久状态。
- 固定日志串（供 CI/真机核对）：
  - `e2631boot: slot%d unusable (%s), falling back to slot%d (cspboot class-1 parity)`
  - `e2631boot: slot%d unusable (%s), slot%d has no valid version header`（另一槽连版本头都没有时）
  - `e2631boot: slot%d unusable (%s) as well`
  - `e2631boot: neither slot is bootable (class-1 check):` 后接逐槽诊断表 `e2631boot:   slot%d base 0x%08x: serial %u, version "%s": %s`
  - `e2631boot: dropping to the console, nothing was booted`
  - 回退成功时额外打印 `e2631boot: booting slot%d from the fallback (this boot only)`
- 不变项：`e2631_pick_slot()` 规则、版本头（magic+CRC1）校验、`e2631slot` 共用扫描/选择函数、`bootm` 前的 CP15/网络时钟钩子、ATAGS 地址。

## 3. 本机静态验证（无本地编译）

- `perl scripts/checkpatch.pl --no-tree --show-types -g 433139f9`：`total: 0 errors, 0 warnings, 0 checks`。
- 用 kit 的 16 个 patch 在干净的 u-boot 基线上 `git am`：16 commits，tree `13c92c68921fa781634beb50d0eaffd50e9a7648` 与 pin 一致；16 个 patch 的 sha256 全部匹配 `uboot-port/commits.env`。
- `git show --stat 433139f9`：只改 `board/zte/zxhn-e2631/e2631boot.c`（+81/−12）；该文件无 `mtd_write`/`mtd_erase` 调用，写入口白名单不受影响。
- workflow YAML `python3 -c 'yaml.safe_load'` 通过（13 steps）；`node tools/check-workflows.mjs` OK。

## 4. CI 结果（uboot-build run 44945090940，head 8811a5b）

| 项 | 值 |
| --- | --- |
| 结论 | SUCCESS |
| post-am | 16 commits，tree `13c92c68921fa781634beb50d0eaffd50e9a7648` |
| banner token | `g61456c131301`（`U-Boot 2027.01-rc2-g61456c131301`）|
| u-boot.bin | 457,680 B，sha256 `31d2b6d858a9df1660bceb6390f731f03e457d3cad84b82144d53bf20f659977`，crc32 `2a9f4d30` |
| mtd0 镜像 | 655,360 B，sha256 `869866d4239219975ea90a310697ecbccdd77181a00c314dd97bdec36fdc58ea`，crc32 `78beeb5e` |
| 装配后 mtd0 首 0x800 | sha256 `4d3176d1f5be903274161b134af37d0b666c5cdfb4f5d3c75a2d974e97aeadbb`（UBOOT-INFO 的 `19a9d546…` 是厂商模板块输入，不是装配结果）|
| env 块（只读） | sha256 `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`，与本轮之前完全一致（未被镜像写）|
| .config | sha256 `91ef0e4d33a4beef46b16e7448a7452aae2463ff71efc732121e81542efda806`（0016 不改 defconfig）|
| checkpatch | 0 errors / 20 reviewed warnings（0016 本身 0/0）|
| 新增门禁 | 源码含 `e2631_try_boot_slot`、`falling back to slot`、`cspboot class-1 parity`；二进制含 `falling back to slot`；日志输出 `class-1 slot fallback: source and image present` |
| 写入口白名单 | 仍为 2 个调用点，均在 `do_e2631flash` 内（0016 未引入新写路径）|

产物：`/home/qc233/zte/e2631-t5-artifacts/uboot-u0016-44945090940/e2631-uboot-44945090940/`（含 SHA256SUMS、UBOOT-INFO.txt、E2631-COMMAND-HELP.txt、.config、mtd0 镜像与 env 块）。

## 5. 真机演练（未执行，需要批准）

本任务不做设备访问，也没有写任何 flash。运行期回退的两种验证方式：

1. **零写入的“健康路径不变”核对**（可随下一次已批准的零写入 RAM 链会话一起做）：loadx 457,680 B 到 `0x47F00000` → `go` → 看到新 banner `g61456c131301`；`e2631slot` 与 `e2631boot info` 的选槽结果应与 0014/0015 镜像完全一致；`e2631boot load` 成功；mtd0 sha256 前后不变。
2. **回退路径演练**（需要写 slot 区，单独批准）：把两个槽都准备好后，用 `e2631flash` 只把“选中槽”的 uImage 头写成坏 CRC（RAM 侧构造 staging，范围限定该槽 `slot_base+0x20` 开始的块并接受擦除该 128 KiB 块），重启后应看到 `falling back to slot%d (cspboot class-1 parity)` 并从另一槽启动；随后用 `e2631flash` 把该槽恢复。此演练会暂时破坏一个内核槽，必须在有串口/救砖链路的会话里、经用户批准后执行。

## 6. 风险与回退

- 回退只发生在选中槽的 uImage 级失败之后，健康路径行为不变；无持久状态、无版本头/serial/env 改动，不会出现“回退后下次起不来”的暗状态（下次仍按 serial 规则选）。
- 回退目标槽也失败时打印诊断表并返回 `=>`，不会调用 `bootm`，也不会自动重启/写 flash。
- 回退方案：从 `uboot-port/patches/` 删除 0016 并把 `commits.env` 的 `E2631_UBOOT_TREE_SHA` 恢复为 15-patch 的 `31843b38628ccf9c3e0b542ec4db014b6612755d`、移除 `PATCH_SHA256_0016`，重建即可；不涉及 flash/env。
- 本轮镜像**尚未刷入**；下一个刷写会话仍应使用已批准的 0014/0015 产物（banner `g85df6772a444`、u-boot.bin sha256 `21b0d804…`、mtd0 镜像 `b1ea9a48…`）。0016 的产物（`869866d4…`）留到下一次已批准的写入。

## 7. 参考

- 设计依据：`docs/U-Boot-env写回与启动计数设计-2026-11-22.md` §6.1（cspboot 语义）、§6.2（差距）、§6.3（phase 1 patch 0016）、§7.2（实现顺序）。
- `uboot-port/README.md`（§1 pin 表、§2 补丁 0016 段落、§3 设计参数、§4 CI 断言、§8 变更记录）。
- `uboot-port/a3-slot-boot-design.md`（槽位布局、选择规则与 `e2631slot`）。
- CI：https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44945090940
- kit 提交：`2370dfe`（patch 0016 + pin）、`8811a5b`（CI 门禁 + README）。
