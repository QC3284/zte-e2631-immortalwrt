# U-Boot checkpatch 收口：MAINTAINERS 条目 + e2631net 用法页（task-66 跟进）

- 日期：2026-11-22
- 触发：Lead 对 E2 系列 checkpatch 结果的要求（目标 0 errors / 0 warnings）
- 结论：两个文档 patch 已交付并重钉、CI 构建 SUCCESS。但**仅靠内容补丁无法把整串 checkpatch 降到 0/0**——
  checkpatch 按单个 patch 独立判断，MAINTAINERS 提醒与 “Possible new command” 都是 patch 局部规则，
  后续 patch 无法消掉前面 patch 的提醒；LIVETREE / PREFER_IF 两类也还在。用 CI 级 `--ignore` 四个类别
  后本地实测 0 errors / 0 warnings。是否采用该 CI 级豁免待 Lead 决定；本轮没有改代码、没有重写 0001-0020。

## 1. 交付

| 项 | 值 |
| --- | --- |
| patch 0021 | `uboot-port/patches/0021-MAINTAINERS-add-the-ZTE-ZXHN-E2631-board-and-the-ZX2.patch`，sha256 `c66643e1eca8c5cc2313e0136636b0ea22822f38f7207236b41786ba93ab7976` |
| patch 0022 | `uboot-port/patches/0022-doc-add-the-e2631net-usage-page.patch`，sha256 `680435c34a4b6ca5154debb0ace1caea7fd7000641e5e572c6477f22b6959b72` |
| 22-patch post-am tree | `c812dd8689ccf146deeec83bd0e74067c8b8abc5` |
| kit commit | `0edf1bf`（`uboot: add the MAINTAINERS entry and the e2631net usage page (task-66)`） |

- patch 0021：MAINTAINERS 新增一段 `ZTE ZXHN E2631 (SANECHIPS ZX279128S)`，maintainer QC3284，
  覆盖 `arch/arm/mach-zx279128s/`、`board/zte/zxhn-e2631/`、`drivers/net/zx279128s_eth.c|.h`、
  `drivers/net/zx279128s_mdio.c`、`drivers/spi/spi-zx.c`、DTS、defconfig、`include/configs/…h`、
  `doc/usage/cmd/e2631*.rst`。
- patch 0022：新增 `doc/usage/cmd/e2631net.rst`（SPDX + 命令页；Synopsis/Description/Example），
  说明只读属性、lan1 = switch port 2 / PHY 12（MDIO 0x0c）与输出示例。`doc/usage/index.rst` 用 glob
  包含 `cmd/*`，无需改索引。
- 0001-0020 的 patch 文件与之前逐字节相同（sha256 未变）；post-am tree 从 `10ade1ec…` 变为
  `c812dd86…` 仅因这两个文档 patch。

## 2. 为什么内容补丁到不了 0/0（checkpatch 源码依据 + 实测）

- `scripts/checkpatch.pl` 的 `sub process` 为每个 patch 文件重置状态：
  `my $reported_maintainer_file = 0;`（第 2805 行），FILE_PATH_CHANGES 只在同一 patch 内见过
  MAINTAINERS 改动时才被抑制（第 3560-3568 行）。CI 用 `format-patch` 后把 `*.patch` 逐个传给
  checkpatch，因此 0021 的 MAINTAINERS 更新对 0001-0020 与 0022 都无效。
- CMD_TEST（第 2670-2674 行）只匹配新增行里的 `do_<name>(struct cmd_tbl`，**完全不读文档**；
  新增用法页不能满足它。8 条提醒来自 8 个自用命令定义。
- LIVETREE（2 条，patch 0002）是板级 `fdtdec_setup_mem_size_base()`/`fdtdec_setup_memory_banksize()`
  的误报；PREFER_IF（5 条，patch 0015）的 `#if CONFIG_IS_ENABLED(CMD_MTD_WRITE)` 必须编译期生效，
  否则原始 mtd 写入口编不掉——这两类同理无法用后续 patch 消除。

实测（本地，22 个 patch，与 CI 完全同一条命令）：

| 命令 | errors | warnings |
| --- | --- | --- |
| `scripts/checkpatch.pl --no-tree --terse /tmp/pchk-all/*.patch` | 0 | **26**（11 MAINTAINERS + 8 CMD_TEST + 5 PREFER_IF + 2 LIVETREE） |
| 同上 + `--ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF` | 0 | **0** |

单 patch 实测：patch 0021 为 0/0；patch 0022 为 0/1（“added, moved or deleted file(s), does
MAINTAINERS need updating?”——文档新文件在 0022 这个 patch 内没有 MAINTAINERS 改动）。
这正好证明：再补文档 patch 只会把总数从 25 抬到 26，不会降到 0。

## 3. CI 构建（文档 patch 重钉后）

- uboot-build run [44982672016](https://github.com/QC3284/zte-e2631-immortalwrt/actions/runs/44982672016)
  （head `0edf1bf`）SUCCESS；kit `Upgrade safety checks` run `44982651725` SUCCESS。
- 产物归档 `/home/qc233/zte/e2631-t5-artifacts/uboot-doc-44982672016/e2631-uboot-44982672016/`：

| 项 | 值 |
| --- | --- |
| banner | `U-Boot 2027.01-rc2-g6bd1fbd087ba`（2026-11-22 03:54:56 +0000） |
| u-boot.bin | 494,208 B（0x78A80，上限 653,312）；sha256 `75ba2e66b448f08fba42fedffae4b21cd84ad082cb32de6f0d3474effc5ca11d`；crc32 `e13c0526` |
| entry | `0x47f00000` |
| mtd0 镜像 | 655,360 B；sha256 `9200fb3594845104ded8b32d494f1702728d9660d07512709931154b9317c739`；crc32 `6cef9a2b` |
| env 块 | sha256 `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`（未变，只读） |
| post-am tree | `c812dd8689ccf146deeec83bd0e74067c8b8abc5`（22 patches） |
| CI checkpatch.txt | 0 errors / 26 warnings（与本地一致） |

构建产物里没有 MAINTAINERS/文档内容，u-boot.bin 尺寸与 E2 产物相同（494,208 B），差异只在版本字符串。

## 4. 待决：怎么才算 0/0

- **方案 A（推荐，无代码/无历史改写）**：在 `.github/workflows/uboot-build.yml` 的 checkpatch 命令上
  加 `--ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF`，并在 workflow 注释与 README §6 写明四类
  豁免与原因（MAINTAINERS 条目已存在、自用板级命令无上游测试、板级 fdtdec 误报、结构性 `#if`）。
  这样 CI 输出就是 0 errors / 0 warnings；二进制/树/pin 都不用动，只需重跑一次 workflow 记录 0/0 产物
  （设备会话用的镜像不因此改变）。
- **方案 B**：保持 0 errors / 26 warnings（现状，README 已逐类写明）。
- 方案 C（不做）：把 MAINTAINERS/文档折进 0001-0020 或改代码绕开规则——违反 append-only 且必须弯代码
  （CMD_TEST/PREFER_IF 只能靠改写定义或运行期分支），Lead 已明确不要。

## 5. 参考

- `.github/workflows/uboot-build.yml` checkpatch step（`scripts/checkpatch.pl --no-tree --terse`）
- `u-boot/scripts/checkpatch.pl`：2805、3560-3568、2670-2674 行
- [uboot-port/README.md](../uboot-port/README.md) §1/§4/§6
- [evidence/uboot-e2-20261122.md](uboot-e2-20261122.md)（E2 系列基线）
