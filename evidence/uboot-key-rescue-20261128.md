# 恢复键进救援（patch 0035，task-82）：设计与构建记录

日期：2026-11-28（CST）
任务：task-82（user 裁决 m11746：reset 与 mesh 两键“任一按下即可”）。
依据：evidence/recovery-button-research-20261128.md（task-80，iwrt-baseline）。

## 0. 结论

- 新增 patch 0035：`board_late_init()` 末尾裸 MMIO 轮询 reset（GPIO18 = bank1 bit2）与 mesh（GPIO20 = bank1 bit4），
  任一键连续按住 2 s 就把 `bootcmd` 在 RAM 内改成 `e2631rescue` 并打印提示；窗口内松手取消。
- 只改 `board/zte/zxhn-e2631/e2631boot.c`（+92 行），不动 defconfig、不改波特率、不改 e2631refclk/e2631net 顺序、
  不新增 MTD 写点（allowlist 仍 4 个 site）；另加只读 `e2631key` 命令便于零写入标定。
- 恢复键把内核层“按住 reset 过启动 = 恢复出厂”的手势替换为“进入网页救援”；恢复出厂将挪进救援页（后续模块）。

## 1. 按键事实（来自 task-80 调研，三方交叉一致）

| 物理键 | 扁平号 | bank/line | 电气 | vendor 行为 |
|---|---|---|---|---|
| reset | 18 | gpio1 bit2（bank1 基址 `0x94407040`，DATA +0x14） | active-low，外部上拉 | `KEY_RESTORE`，连续低 5.25 s 才返回 0 |
| mesh/WPS | 20 | gpio1 bit4 | active-low，外部上拉 | 键表输入（entry[29]） |

方向位复位后即为 0（输入），厂商 U-Boot 与内核 GPIO 驱动都不写上下拉；读 DATA 即可。

## 2. 实现（patch 0035，1 file，+92）

常量：

- `E2631_GPIO_BASE 0x94407000`、`E2631_GPIO_BANK_SIZE 0x40`、`E2631_GPIO_DATA 0x14`
- `E2631_KEY_RESET 18`、`E2631_KEY_MESH 20`、`E2631_KEY_WINDOW_MS 2000`、`E2631_KEY_POLL_MS 50`

函数：

- `e2631_key_down(pin)`：`readl(bank + 0x14) & BIT(pin & 0xf)`，低电平返回 true；
- `e2631_rescue_key_state()`：0 = 两键都没按；1 = 进入时已按下的键在整个 2 s 窗口保持按下；-1 = 中途松手取消。
  只跟踪进入时已按下的键（按下另一个键不能顶替已松开的键）；
- `do_e2631key` / `U_BOOT_CMD(e2631key)`：只读打印两键 `pressed`/`released`，供标定与诊断。

接线：`board_late_init()` 在 `env_set("bootcmd", "e2631boot")` 之后按状态分支——1 时打印
`e2631rescue: recovery key held, booting the web rescue` 并 `env_set("bootcmd", "e2631rescue")`（仅 RAM）；
-1 时打印 `e2631rescue: key released, booting normally`。

## 3. CI 门禁（.github/workflows/uboot-build.yml）

- key rescue gate：awk 截取 `int board_late_init(void)` 后必须含 `e2631_rescue_key_state`；源码含
  `env_set("bootcmd", "e2631rescue")`、`#define E2631_KEY_RESET … 18`、`#define E2631_KEY_MESH … 20`；
  `e2631boot.c` 不得出现 `mtd_write`/`mtd_erase`/`mtd_special_write_oob`；二进制含 `e2631key: reset (gpio18)`。
- recovery-key size gate：u-boot.bin ≤ `E2631_UBOOT_KEY_BASELINE_SIZE`（365,872 B，patch-0034 构建）+
  `E2631_UBOOT_KEY_GROWTH_MAX`（1,024 B）→ 上限 366,896 B。
- 既有 4-site MTD writer allowlist 不变（D-U1 门禁继续断言）。

## 4. 本地验证（无本地交叉编译）

- 干净重放：clone u-boot 到 pinned `c1958b5f`，对 kit 的 35 个 patch 依次 `git am`，35 个 commit，
  tree `a3e940a897ec9d86503c01a2b1c2e70d9f1e0ba6`，与 pin 一致。
- `make defconfig` 不需要新符号（读 GPIO 走裸 MMIO，无 DM_GPIO）；defconfig 未改。
- host `gcc -fsyntax-only`：通过。
- checkpatch（`--ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF`）：0 errors / 0 warnings。
- 模拟 CI 门禁（源码侧）：awk/grep 五项全部命中，`e2631boot.c` 无 MTD 写符号。

## 5. CI 构建与身份

（构建完成后填：run id、banner、u-boot.bin 大小/sha256/crc32、mtd0 镜像 sha256/crc32、env 块、
size gate 行、key rescue gate 行、归档路径。）

## 6. 真机验证计划（零写入，需 Lead/用户批准会话）

1. 把本构建的 `u-boot.bin` 经 Linux 侧 userdata 暂存（`0x3F00000`），或沿用厂商 U-Boot 的 tftp+go 链；
   **不写 mtd0**。
2. 上电时按住 reset（或 mesh）键约 6 s：预期串口出现 `e2631rescue: recovery key held, booting the web rescue`，
   随后 autoboot 进入救援页（DHCP/HTTP 行为同 E4 文档）。
3. 松开键后再次复位、这次按住 1 s 就松：预期 `e2631rescue: key released, booting normally`，固件照常启动。
4. 不按键：预期无任何恢复键输出、启动链与 0034 相同。
5. `e2631key`：不按键时两键 `released`，按住对应键时变 `pressed`（零写入标定）。
6. 失败模式：若 `board_late_init()` 读 GPIO 卡住，串口停在启动早期、无 shell；断电即可恢复（未写任何 flash）。
   该风险必须在 RAM 链验证通过后才讨论把 0035 刷进 mtd0。

## 7. 风险与边界

- GPIO DATA 读首次出现在 `board_late_init()`（此前只在本 U-Boot 的 e2631net/救援入口之后读）；厂商 OS 里
  devmem2 读 GPIO 曾读挂是厂商内核环境现象，U-Boot 侧大概率安全但必须真机零写入验证。
- 2 s 窗口与“上电后约 6 s”的操作指引需真机标定；窗口参数是常量，调整要改 pin + 重建。
- 恢复键触发进救援后，Ctrl-C 退出回到提示符（bootcmd 仍是 `e2631rescue`）；要回固件可跑 `e2631boot` 或 `reset`。
- 不做恢复出厂：该功能计划挪进救援页（后续模块），本 patch 只改启动入口行为。

## 8. 参考

- evidence/recovery-button-research-20261128.md（按键身份/厂商逆向/风险）
- evidence/e4-coldrescue-0034-20261128.md（救援入口的冷启动行为）
- uboot-port/README.md §1/§3/§4/§5/§6
