# A1 最小 U-Boot 的 CI 交叉构建（task-44，2026-11-21）

本文件记录 task-44 的交付：为 A1 纯 RAM 链的 E2631 最小 U-Boot 增加一个
`.github/workflows/uboot-build.yml`（手动 dispatch），在 GitHub Actions 上用
`arm-none-eabi-` 交叉工具链完成「钉点检出 → 应用 uboot-port 补丁 → 构建 → 验收门禁 →
上传产物」的全流程。**本阶段只做 CI 构建，未加载到真机、未写 flash、未发布 Release。**

## 1. 目标与边界

- 目标：用 CI 产出可被 vendor U-Boot 控制台以 `tftp` 载入 RAM 再 `go` 执行的
  `u-boot.bin`，并把 A1 的验收断言（tree/size/entry/.config）固化进 workflow。
- A1 = 纯 RAM 链：vendor secondboot 把 payload 复制到 RAM 后跳转，**不写 mtd0**；
  真正落盘（写 mtd0 `0x20000..0xC0000`）属 A3 阶段。
- 边界：只新增独立 workflow；`firmware.yml` / `check.yml` 主链未改；无 publish、
  无 Release；kit main 未动；真机未刷（A1 真机会话需用户单独批准）。
- 本机不编译（弱机），构建全部在 GitHub Actions 上完成。

## 2. 钉点（唯一真相源 `uboot-port/commits.env`）

| 项 | 值 |
| --- | --- |
| 基线仓库 | https://github.com/u-boot/u-boot |
| 基线分支 | master |
| 基线 commit | `c1958b5f6cce03956d309ce422b5d9f819955d4a`（v2027.01-rc2，2026-11-19） |
| 基线 tree | `62f07967f69e656689266ee1f3e7116cf4b5fd10` |
| patch 0001 sha256 | `1e051c226bb0a5fcd44ded121c73acf03b76b7881d46aad7fd1247c19948c535`（A1 SoC 支持） |
| patch 0002 sha256 | `71fdce39af5700bd440f87fbe1d50ce7fe97a1c2ab15a44e009d47af09250003`（A1 板级/defconfig） |
| patch 0003 sha256 | `d16e7b563adc8693ea59e23900870b07a168f44136218d740c3ba49e44c7b395`（链接修复，本任务新增） |
| post-am tree | `abab1858bfee030bfdbc18bc227189a6e8ba5d83`（3 个提交） |
| payload 上限 | `0x9F800` = 653312 B（secondboot 从 mtd0 `0x20800` 复制，payload 到 `0xBFFFF`，env 从 `0xC0000` 起） |
| TEXT_BASE | `0x43000000`（u-boot.bin 的链接/入口地址） |

workflow 不再硬编码 patch 列表：pin 步用 `uboot-port/patches/[0-9][0-9][0-9][0-9]-*.patch`
枚举文件，逐个读 `E2631_UBOOT_PATCH_SHA256_NNNN`（缺失即失败），并核对 pin 数与文件数；
apply 步对每个 patch 做 `sha256sum -c` 后 `git am uboot-port/patches/*.patch`，再断言
`HEAD^{tree} == E2631_UBOOT_TREE_SHA`、提交数 == patch 数。**新增 patch 只需加文件 + 新
pin，不用改 workflow。**

## 3. workflow 结构（`.github/workflows/uboot-build.yml`）

- 触发：仅 `workflow_dispatch`；输入 `checkpatch`（boolean，默认 true，纯信息性）。
- 权限：`contents: read`；`concurrency` 按 ref 互斥；`runs-on: ubuntu-24.04`、`timeout-minutes: 45`。
- 步骤：checkout@v5 → 读取 `uboot-port/commits.env`（校验 7 个基础 pin、写 `$GITHUB_ENV`）
  → 安装 `gcc-arm-none-eabi`/binutils 与 U-Boot 构建依赖 → `git init` + `fetch --depth 1` 按 SHA
  取基线并验证 `HEAD` 与 base tree → 校验并 `git am` patch 系列、验证 post-am tree 与提交数
  → `make O=build zx279128s_zte_zxhn-e2631_defconfig` + `make O=build -j$(nproc)`
  `CROSS_COMPILE=arm-none-eabi-` → 验收门禁 → checkpatch（可选）→ 生成 UBOOT-INFO/SHA256SUMS
  → 上传 artifact。
- 验收门禁：`.config` 精确含 9 个符号（`CONFIG_ARCH_ZX279128=y`、`CONFIG_TARGET_ZXHN_E2631=y`、
  `CONFIG_TEXT_BASE=0x43000000`、`CONFIG_OF_EMBED=y`、`CONFIG_ARM_GLOBAL_TIMER=y`、
  `CONFIG_TIMER=y`、`CONFIG_PL01X_SERIAL=y`、`CONFIG_DM_SERIAL=y`、`CONFIG_CLK=y`）、
  `size(u-boot.bin) <= 653312`、`readelf -h` 的 Entry point == `0x43000000`。
- 产物：artifact `e2631-uboot-a1-<run_id>`（14 天保留），含 `u-boot.bin`、`u-boot.map`、
  `.config`、`build.log`、`checkpatch.txt`、`UBOOT-INFO.txt`、`SHA256SUMS`。

## 4. 构建历史（从失败到绿）

### 4.1 首次构建失败：run 44868198743

workflow 自身的两处修正（`a2b50b0` → `f343a0c`/`5b43f13`：job 级 env 不能引用 `runner`
上下文、step summary 里的反引号）之后，run **44868198743** 走到链接失败：

```
arm-none-eabi-ld: undefined reference to `reset_cpu`   (arch/arm/lib/reset.c:41 / boot/bootm.c:1357)
arm-none-eabi-ld: undefined reference to `print_cpuinfo` (common/board_f.c:988 INITCALL)
arm-none-eabi-ld: undefined reference to `board_init`   (common/board_r.c:636 INITCALL)
make[1]: *** [Makefile:2121: u-boot] Error 1
```

根因（读 pinned 源码确认）：

1. `arch/arm/lib/reset.c` 的 `do_reset()` 无条件调用 `reset_cpu()`，该符号没有 weak 默认；
2. `common/board_f.c` 的 `print_cpuinfo` 静态定义受 `#if defined(CONFIG_DISPLAY_CPUINFO) && CONFIG_IS_ENABLED(CPU)`
   限制，而 A1 defconfig 里 `CONFIG_DISPLAY_CPUINFO=y` 却没有 CONFIG_CPU 驱动，
   `INITCALL(print_cpuinfo)` 却按 `#if CONFIG_IS_ENABLED(DISPLAY_CPUINFO)` 编译；
3. `common/board_r.c` 的 `INITCALL(board_init)` 在 `CONFIG_BOARD_INIT=y` 时编译，A1 板级文件
   只有 `dram_init`/`dram_init_banksize`，没有 `board_init`。

task-43 只做了 `git am` + tree hash 校验、从未编译，所以这三个链接缺口到本次 CI 才暴露。
工具链本身正常：Ubuntu 24.04 的 `gcc-arm-none-eabi` 15:13.2.rel1-2（13.2.1 20231009）一路编译到链接。

### 4.2 patch 0003：最小链接修复（提交 `78ee697`）

只做三处链接错误对应的最小改动（2 文件 +14）：

- `configs/zx279128s_zte_zxhn-e2631_defconfig` 末尾加
  `# CONFIG_DISPLAY_CPUINFO is not set`、`# CONFIG_BOARD_INIT is not set`；
- `board/zte/zxhn-e2631/zxhn-e2631.c` 加 `reset_cpu()`：**打印 A1 限制后返回，不死循环**
  （A1 没有复位控制器，复位由 vendor loader 掌管；需要重启就断电/看门狗）。

没给 `print_cpuinfo`/`board_init` 加空 stub：它们对应的 initcall 已经被上面的 disable 关掉，
加空函数只会留下死代码。

同一提交完成 re-pin 与 workflow 泛化：`uboot-port/commits.env` 加 `E2631_UBOOT_PATCH_SHA256_0003`，
`E2631_UBOOT_TREE_SHA` 由 `d4714ecf` 改为 `abab1858`；`uboot-port/README.md` 更新 pin 表、补丁
说明与 A1 限制；workflow 改为 patch-list driven（见 §2）。

### 4.3 首次成功：run 44868839622

12 步全绿（约 1m45s）。下载 artifact 后发现 3 个交付质量问题：

1. `.config` 是隐藏文件，`actions/upload-artifact@v4` 默认 `include-hidden-files: false` 把它漏掉了
   （SHA256SUMS 仍列它，导致下载后 `sha256sum -c` 失败）；
2. checkpatch 用 `--terse` 时，问题行是 `file:line: WARNING:` 形式，原 `grep '^WARNING:'` 永远计 0；
3. provenance 的 "Port patches sha256" 行手写了 0001/0002，新 patch 不会自动出现。

### 4.4 修复：提交 `f1bd383`

- upload 步加 `include-hidden-files: true`；
- checkpatch 计数改 `grep -c ': WARNING:'` / `: ERROR:`，step 文案不再写死数字；
- provenance 从环境变量动态收集全部 `E2631_UBOOT_PATCH_SHA256_NNNN`；
- README 更正 checkpatch 实测结果：**0 errors / 4 reviewed warnings**（2 条 MAINTAINERS
  提示：0001 新建 `arch/arm/mach-zx279128s/`、0002 新建 `board/zte/zxhn-e2631/`；
  2 条 "Use the livetree API" 是 checkpatch 对板级 `fdtdec_setup_*` 用法的误报）。

### 4.5 最终绿：run 44869143179

- head `f1bd383`，2026-11-21T05:04:42Z → 05:06:32Z（约 1m50s），事件 `workflow_dispatch`；
- 12/12 步 success（含 `Enforce the A1 acceptance gates`、checkpatch、artifact 上传）；
- kit `check.yml` 在同提交上的 run **44869141981** = SUCCESS。

## 5. 产物核验（下载到本机）

- artifact：id **14693515744**，name `e2631-uboot-a1-44869143179`，284,757 B（zip），
  zip 的 SHA256 = `13b6eec2c53257d1a3f839b6e0411ff41c9b3f52a1639abd40e23b11767ae9f5`；
- 解包 7 个文件：`u-boot.bin` 347,640 B、`u-boot.map` 633,833 B、`.config` 34,399 B、
  `build.log` 18,301 B、`checkpatch.txt` 752 B、`UBOOT-INFO.txt` 851 B、`SHA256SUMS` 309 B；
- `sha256sum -c SHA256SUMS`：**4/4 成功**（u-boot.bin / u-boot.map / .config / UBOOT-INFO.txt）；
- `u-boot.bin` sha256 = `a3771aca6144879701d5336ae032a6d242fab3e1c90a80dbea0710a6816679b3`，
  347,640 B ≤ 653,312 B（余量 305,672 B，约 46.8%）；
- 入口点：门禁 `readelf -h` 断言 `0x43000000`（PASS）；`u-boot.map` 里
  `__image_copy_start = ADDR (.text) = 0x43000000` 一致；
- `.config`：9 个验收符号全部命中；新增的 `# CONFIG_DISPLAY_CPUINFO is not set`、
  `# CONFIG_BOARD_INIT is not set` 也在（证明 0003 已生效）；
- checkpatch：`errors=0 warnings=4`（见 §4.4 说明）；
- UBOOT-INFO.txt 记录：baseline `c1958b5f`/tree `62f07967`、3 个 patch sha、post-am tree
  `abab1858`、defconfig、工具链 `arm-none-eabi-gcc (15:13.2.rel1-2) 13.2.1 20231009`、
  size、entry、run URL、`Hardware tested: NO`。

**可复现性说明**：`u-boot.bin` 的 banner 内嵌编译时间与 post-am 提交短哈希，例如
`U-Boot 2027.01-rc2-g7c42c3f6b431 (Nov 21 2026 - 05:06:01 +0000)`，因此同一钉点重复构建
**不是逐字节可复现**（run 44868839622 与 run 44869143179 的 bin sha256 不同：
`290bb1be…` vs `a3771aca…`）。产物身份以 **run URL + SHA256SUMS** 为准；如需长期归档，
下载 zip 保存（artifact 默认保留 14 天）。本机归档：
`/home/qc233/zte/e2631-t5-artifacts/uboot-a1-44869143179/`。

## 6. A1 真机装载（未执行，需用户批准）

真机侧动作**本次未做**；A1 是纯 RAM 会话，按 `uboot-port/README.md` 的路径需要：

1. 串口进 vendor U-Boot 控制台，网线连通（tftp 服务在用户主机上）；
2. `tftp 0x43000000 u-boot.bin`（只写 RAM，**不写 flash**）；
3. `go 0x43000000` 进入自定义 U-Boot。

因为是纯 RAM 链，断电即回到 vendor 系统，**不构成砖风险**；写 mtd0 属 A3，需要单独的
用户批准与 A2 备份。本次交付因此标注 `Hardware tested: NO`。

## 7. 复现命令

```bash
# 触发一次（默认带 checkpatch）
gh workflow run uboot-build.yml --repo QC3284/zte-e2631-immortalwrt \
  --ref iwrt-adaptation -f checkpatch=true

# 查看/下载
gh run list --repo QC3284/zte-e2631-immortalwrt --workflow uboot-build.yml --limit 5
gh run download <run_id> --repo QC3284/zte-e2631-immortalwrt -D <dir>
(cd <dir>/e2631-uboot-a1-<run_id> && sha256sum -c SHA256SUMS)
```

## 8. 未验证 / 风险

- **真机未装载**：tftp 载入、DDR 初始化、串口交互都要等用户批准的真机会话（A1）验证；
- **非逐字节可复现**：见 §5；若以后需要可复现构建，可再固定 U-Boot 的 build timestamp
  （目前未做，避免为个别需求改上游构建语义）；
- **payload 布局假设**：size 上限与 `0xC0000` env 边界来自 README 对 vendor secondboot 的
  分析；真机加载前应再复核 `0x9F800` 余量；
- **checkpatch 4 warnings** 已逐条评审（2 MAINTAINERS + 2 livetree 误报），不是回归；
- artifact 保留 14 天，过期后需从本机归档或重跑 workflow。

## 9. 相关提交 / run

| 内容 | 位置 |
| --- | --- |
| patch 0003 + re-pin + workflow 泛化 | kit 提交 `78ee697` |
| artifact 完整性 + checkpatch 计数修复 | kit 提交 `f1bd383` |
| 首个绿 run | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44868839622 |
| 最终绿 run | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44869143179 |
| kit check.yml（f1bd383） | https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44869141981 |
| workflow | `.github/workflows/uboot-build.yml` |
| 钉点/说明 | `uboot-port/commits.env`、`uboot-port/README.md` |

## 10. patch 0004（ZTE UART map）重建（task-48，2026-11-21）

task-47 落地串口修复后（kit 提交 `a9dbd6e` "uboot: fix the A1 console with the ZTE UART
register map"）按 task-48 重新构建并验收。**这是同一 workflow 的第四次运行，workflow 代码未改
（只随 task-47 提交多了 embedded-DTB 门禁），pins 由 `uboot-port/commits.env` 驱动自动更新。**

### 10.1 新的钉点

| 项 | 值 |
| --- | --- |
| patch 数量 | 4（0001/0002/0003/0004） |
| patch 0004 sha256 | `ce6a01ef5b0c1c47f213a79a30bc3bb13f0b8cdeec10ebb4395ce988b5e746ca`（ZTE-variant PL011 寄存器映射，341 行） |
| post-am tree | `418ae89f09b34238daf37d0db78b4485001ffc2c`（原 0003 时代为 `abab1858`） |
| 基线/上限/入口 | 不变：`c1958b5f` / base tree `62f07967` / payload max `0x9F800` / TEXT_BASE `0x43000000` |

workflow 同时新增 embedded-DTB 门禁：`grep -aq 'zte,zx29-uart' build/u-boot.bin`，验证
`CONFIG_OF_EMBED` 的 DTB 确实使用 ZTE UART compatible（A1 串口在 stock-ARM 偏移下静默，
task-45 双偏移探针已硬件证实差异；见 `evidence/a1-ramchain-poc-20261121.md`）。

### 10.2 构建结果

- run **44875722425**（head `a9dbd6e`，workflow_dispatch，checkpatch=true）：
  2026-11-21T06:28:45Z → 06:30:36Z（约 1m51s），**12/12 步 success**；
- 门禁原始输出：
  - `u-boot.bin: 347824 bytes, limit 653312 bytes`
  - `entry point: 0x43000000`
  - `.config` 9 个验收符号全过；`# CONFIG_DISPLAY_CPUINFO is not set`、`# CONFIG_BOARD_INIT is not set` 仍在；
  - embedded-DTB 门禁通过（离线复核 `grep -ac 'zte,zx29-uart' u-boot.bin` = 2，strings 含
    `zte,zx279128s` / `zte,zx29-uart` / `zte,zxhn-e2631`）；
  - `checkpatch: errors=0 warnings=4`（仍为 0001 MAINTAINERS、0002 MAINTAINERS + 2 livetree，patch 0004 自身无告警）。
- kit `check.yml` 在 `a9dbd6e` 上的 run **44875548158** = SUCCESS（重建前已核）。

### 10.3 产物（已归档）

- artifact id **14694824928**，name `e2631-uboot-a1-44875722425`，zip 284,949 B，
  zip SHA256 `e323fb049078ebfff498e5301d746780970ecb4ace87e0de9dcdd6f4f4f6288f`；
- 7 文件，`sha256sum -c SHA256SUMS` **4/4 成功**；
- `u-boot.bin` = **347,824 B**（比 task-44 的 347,640 多 184 B，来自 UART map 代码），
  sha256 = `5310f998824a4c52dd46a18315ac0b989f2545f632477a5769ad5f2e5b4dc742`，
  距上限余量 305,488 B；
- `u-boot.map` 入口仍为 `0x43000000`；`UBOOT-INFO.txt` 记录 4 个 patch sha、post-am tree
  `418ae89f`、工具链同上、`Hardware tested: NO`；
- banner 串：`U-Boot 2027.01-rc2-g4910ee2045bd (Nov 21 2026 - 06:30:06 +0000)` —— 设备侧的
  banner 验收应核对 post-am 短哈希 **4910ee2045bd**（task-44 时代为 7c42c3f6b431）；
- 本机归档：`/home/qc233/zte/e2631-t5-artifacts/uboot-a1-fix-44875722425/`
  （`artifact.zip`、`artifact-id.txt`、`files/`）。

### 10.4 边界

未 publish、未创建 Release/tag；`firmware.yml`/`check.yml` 未改；kit main 未动；真机未碰
（A1 串口/banner 复测由 Lead 另排批准任务）。

## 11. A3 mtd0 镜像打包（task-52，2026-11-21）

task-51 的 A3 代码落地（kit `b90a0de` + `265c818`，patch 0005/0006/0007，post-am tree
`40f52fb46d9987d8082babac151f9f8dcbdcba4a`）后，workflow 增加**镜像产出**：把 `u-boot.bin`
用 P0 工具链打成可刷的 mtd0 镜像资产。**仍然只产出：不发布、不刷写、不碰设备。**

### 11.1 打包管线（新增两步）

1. **Package the flashable mtd0 image**：
   - 从已入库的厂商读取证据重建 0x800 B U-Boot 头块：
     `evidence/p2-oob/headblock-0x20000-0x20800.hex`（magic `128s`、厂商声明长度 `0x68000`，
     sha256 `19a9d54614e9d5cdfb7573495609448cdf1a740e470fbebcac5783c8e9b93510`）；
   - 用 `tools/e2631-env.mjs build` 从现网 env 文本
     `evidence/b1-env-current-20261121.txt` 重建厂商 env 块（22 项、CRC32 `0xaffcec3e`、
     0x20000 B、sha256 `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`，
     与 P0「现网 dump 解析-重生成逐字节一致」的结论同源）；
   - 合成 1 MiB 模板（头块 @0x20000、env @0xC0000、其余 0xFF），
     `tools/mkuboot-image.mjs build` 把 payload 写到 0x20800 并只改头块 +0x14 的长度字段，
     产出 `e2631-uboot-mtd0.bin` = mtd0 `0x20000..0xC0000`（0xA0000 B）；
   - 镜像尾部默认无 64 B tail marker（工具按擦除 0xFF 处理；secondboot 只校验 magic，不校验 tail/CRC）。
2. **Verify the mtd0 image against the P0 gates**：
   - `mkuboot-image check`：解包/重打包逐字节一致；
   - `e2631-env check`：env 块 CRC32 往返一致（22 项，`0xaffcec3e`）；
   - `verify-mtd0 --sha256`：P0 的 sha256 回读门禁；
   - 结构断言：镜像恰为 0xA0000；头块除 +0x14 外与厂商块逐字节一致；+0x14 == payload 长度；
     payload 与 `u-boot.bin` 逐字节一致；payload 之后（到 0xA0000）全 0xFF；
     payload 末端（绝对 `0x20800 + len`）不越过 env 起点 `0xC0000`。

产物 zip 现在含：`u-boot.bin`、`e2631-uboot-mtd0.bin`、`e2631-env-block.bin`（只读参考，
不属于镜像）、`u-boot.map`、`.config`、日志、`UBOOT-INFO.txt`、`SHA256SUMS`。
`UBOOT-INFO.txt` 记录镜像/头块/env 的 sha256、payload 长度和边界。

### 11.2 构建与门禁结果

- run **44880753221**（head `20f2d9b`，workflow_dispatch，checkpatch=true）：
  2026-11-21T07:32:55Z → 07:34:45Z，**15/15 step success**（含新增的打包与 P0 门禁两步）；
- 门禁原始输出：`u-boot.bin: 448072 bytes, limit 653312 bytes`、`entry point: 0x43000000`、
  `vendor U-Boot header block: 0x800 bytes`、`env: 22 entries, CRC 0xaffcec3e`、
  `wrote artifacts/e2631-uboot-mtd0.bin (0xa0000 bytes, sha256 7cac2d39...)`、
  `OK: unpack + build is byte-identical`、`OK: env dump + rebuild is byte-identical`、
  `OK sha256 matches 7cac2d39...`、`mtd0 image: 0xa0000 bytes ... env @0xC0000 untouched`；
- `.config` 9 个验收符号、9F800 上限、entry 门禁、embedded-DTB 门禁全部照旧通过；
- checkpatch：**0 errors / 7 reviewed warnings**（0001/0002 的 4 条旧项 + A2/A3 新增 3 条：
  0005 新建文件 1 条 MAINTAINERS、0006 新建文件 1 条 MAINTAINERS + 1 条 "Possible new command -
  make sure you add a test"；均已在 task-50/51 证据中审阅，属信息性）；
- kit `check.yml` 在 `20f2d9b` 上 run **44880750288** = SUCCESS。

### 11.3 产物（已归档）

- artifact id **14698261124**，name `e2631-uboot-44880753221`，zip 562,838 B，
  zip SHA256 `33e6d9a8f78df726fb7837ff9acde473c7e31232bd1d981e714b9661d065a977`；
- 9 文件，`sha256sum -c SHA256SUMS` **6/6 成功**；
- `e2631-uboot-mtd0.bin` = 655,360 B（0xA0000），sha256
  `7cac2d399cf8cf6c678bdfcea3fe6669bbb8a2e0af1b72a9b93e348a5b8aa8c8`；
  header 块 sha256 `19a9d546...`；payload 长度 `0x6d648`（448,072 B），
  payload 末端 `0x20800 + 0x6d648 = 0x8de48`，距 env `0xC0000` 余量 209,080 B；
- `u-boot.bin` = 448,072 B，sha256 `adc00a8f08d5bde6584fcb7e4f63e117fd99c5189cc53122affb64aec32b5cd0`；
- `e2631-env-block.bin` = 131,072 B，sha256 `6eee153b...`；
- 本机归档：`/home/qc233/zte/e2631-t5-artifacts/uboot-a3-mtd0-44880753221/`
  （`artifact.zip`、`artifact-id.txt`、`files/`）。

### 11.4 可复现性说明

`u-boot.bin` 的 banner 内嵌编译时间（本 run 记为 `adc00a8f...`，与本地用上一 run payload 的
`4128523c...` 不同），因此 **镜像 sha256 会随构建时间变化**（本地预演镜像
`e762c003...`，CI 产物 `7cac2d39...`）。在 payload 固定时镜像字节是确定的：
头块、env 块、长度字段和擦除尾部都由钉点/证据唯一决定。产物身份以 run URL + SHA256SUMS 为准。

### 11.5 边界

未 publish、未发布 Release/tag；未 dispatch 任何额外 workflow；真机未碰（A1/A2/A3 设备会话
是分开的用户批准任务）；`firmware.yml`/`check.yml` 未改；pin 文件未动——workflow 只是消费
task-51 已钉的 4→7 个 patch 与 post-am tree `40f52fb4`。
