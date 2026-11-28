# 恢复键调研：mesh/reset 按键 GPIO、现有行为与「上电长按进入救援」触发方案（task-80）

日期：2026-11-28（CST）  
设备：ZTE ZXHN E2631 / ZX279128S  
当前 flash：E4 + patch 0034 镜像（banner U-Boot 2027.01-rc2-g1673d5c89c7b，mtd0 `ac06d7bc…`，2026-11-28 09:12 真冷启动 GREEN，见 `evidence/e4-rescue-write-acceptance-20261128.md` §13）  
任务卡：task-80「恢复键调研（mesh/reset GPIO + 现有按键行为 + 触发方案）」  
边界：只读静态调研；本轮不改 U-Boot 树、不改 target 树、不写 flash、不碰设备。结论供 Lead/用户拍板后再实现。

## 0. 摘要

| 项 | 结论 |
|---|---|
| reset 键身份 | flat GPIO 18 = `&gpio1 2`，DTS `GPIO_ACTIVE_LOW`（按下为低）；厂商板级表 entry[27] 也是 pin18 输入 |
| mesh/WPS 键身份 | flat GPIO 20 = `&gpio1 4`，DTS `GPIO_ACTIVE_LOW`；厂商板级表 entry[29] |
| 电气 | 按下 = 低电平；DTS 与内核驱动均未配置偏置，默认外部上拉；厂商 U-Boot 轮询语义也是「低 = 按下」 |
| 内核 reset 键现状 | `KEY_RESTART` → `/etc/rc.button/reset`：短按 <1 s 重启；按住 ≥5 s 且 overlay 存在 → factory reset |
| 内核 mesh 键现状 | `KEY_WPS_BUTTON` → `/etc/rc.button/wps` → 仅执行 `/etc/rc.wps/*`，本树唯一脚本是 WPS 绿灯闪 120 s；**没有** WPS/hostapd 功能性动作 |
| 厂商 U-Boot 按键处理 | 只在 boot-mode 控制台 shell 里读 pin18：约 5.25 s 释放等待后跑 `downver version` + `reset`；正常启动路径从不进入该 shell；本 payload 无 `downver` 命令，该分支实际是死代码 |
| 上游先例 | hanwckf/Yuzhii 的 `glbtn`：4 s 长按 → `httpd`；依赖 DM_GPIO + button uclass，本 U-Boot 没有，需裸 MMIO 复刻约 40-60 行 |
| 推荐方案 | **A：上电时按住 reset ≥2 s（board_late_init 连续检测）→ RAM 内把 bootcmd 改成 `e2631rescue`**；B（mesh）备选，C（双键）加固，D（任意键+确认）v1 不做 |
| 主要冲突 | A 与「按住 reset 过启动 = 内核 factory reset」的既有语义重叠，必须写进发布说明；B 无此冲突但发现性低 |
| 证据缺口 | 调研时 SSH 192.168.1.1 超时，缺 `/sys/kernel/debug/gpio`、`/etc/rc.button` 运行时变量、logread 的现场证据，见 §9.3 |

## 1. 任务与约束

### 1.1 目标

回答「上电时长按某个键 → U-Boot 直接进入 `e2631rescue`」是否可行、用哪个键、在哪检测、阈值多少、会和内核按键语义有什么冲突，并给出实现草图与验证计划。本文件不改任何代码。

### 1.2 约束对齐（Lead 转述的用户指令 m11707，2026-11-28）

| # | 约束 | 对 task-80 的影响 |
|---|---|---|
| 1 | 存储/启动：没有 ATF/FIP/GPT/UBI/NMBM；救援 UI 不承担刷 slot（`e2631-upgrade` 是唯一属主） | 触发只负责进入救援；不新增写路径、不做 slot 选择 |
| 2 | 网络：单 MAC + 集成交换，仅 lan1，无 PPE；eth 前必须 refclk（patch 0034 已把 `e2631_net_refclk_init()` 放进 `do_e2631rescue`） | 触发方案不碰网络初始化；进入救援后现有 0034 顺序已成立 |
| 3 | env：厂商格式 @0xC0000，厂商启动会重写 bootargs/bootcmd；写入只允许白名单 | 触发只在 RAM 内 `env_set("bootcmd", …)`，不落 flash，不扩白名单 |
| 4 | 复位：patch 0029 的 `reset` 已真实可用；断电重启是物理动作 | 进入/退出救援不再依赖断电；页面「断电重启后生效」文案属于 env 写回语义，保持不动 |
| 5 | 按键：mesh/reset 的 GPIO 接线是板级事实，MT798x 定义不可照搬 | 本文件即此项的答案（pin 18/20，低有效） |
| 6 | 串口：PL011-ZTE @115200，永不改波特率；救援循环除 Ctrl-C 外吞掉控制台输入 | 触发不改 baud、不新增命令；串口用户仍可手打 `e2631rescue` |
| 7 | 尺寸：payload 653,312 B / 门禁 645,120 B / 当前约 361 KB；页面预算 32 KB | 触发逻辑预计 <1 KB，无预算压力 |
| 8 | 安全：LAN 上无认证的救援页不可接受，需要口令或砍掉 | 本文件不涉及页面实现；auth 是 task-81/v2 的约束，记录在 §10 |

## 2. GPIO 身份与电气事实

### 2.1 身份（三方交叉一致）

| 物理键 | 扁平号 | bank/line | DTS 节点 | 厂商板级表（product_vid 31 = E1630） | 厂商 U-Boot 启动日志 | /proc/zte/ledkey_m/key 实测 |
|---|---|---|---|---|---|---|
| reset | 18 | gpio1 bit2 | `key-reset`：`gpios = <&gpio1 2 GPIO_ACTIVE_LOW>`，`linux,code = <KEY_RESTART>`（dts:108-112） | entry[27]：pin 18，dir=input | `input gpio:18` | key 0x2 → gpio18 |
| mesh/WPS | 20 | gpio1 bit4 | `key-wps`：`gpios = <&gpio1 4 GPIO_ACTIVE_LOW>`，`linux,code = <KEY_WPS_BUTTON>`（dts:114-118） | entry[29]：pin 20，dir=input | `input gpio:20` | key 0x1 → gpio20 |

扁平号公式 = `bank*16 + line`，GPIO 基址 `0x94407000`，bank 间隔 `0x40`（内核 `drivers/gpio/gpio-zx279128s.c` 注释与厂商 U-Boot `0x47f2dcf4` 系列一致）。所以 pin18 = `0x94407040 + bit2`，pin20 = `0x94407040 + bit4`。

来源文件：

- `iwrt-tree/target/linux/zx279128/dts/zx279128s-zte-zxhn-e2631.dts:100-119`（keys 节点：`compatible = "gpio-keys-polled"`，`poll-interval = <50>`，注释明确「供应商键表 flat GPIO 18 和 20」，且轮询是有意为之——IRQ 模式在 H3600 上锁死）；
- `docs/02-实施计划-2026-10-13.md:655-661`（ledkey_m 实测：key 0x2 → gpio18，key 0x1 → gpio20）；
- `docs/02-实施计划-2026-10-13.md:42`（U-Boot 日志按键线索：inputs 5/15/62/61/43/47/46/45/18/20）；
- 厂商 U-Boot 证据：`evidence/p2-oob/vendor-uboot-ram.bin`（426,048 B，sha256 `a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30`）。

### 2.2 电气语义

- 按下 = 低电平：DTS 两个键都是 `GPIO_ACTIVE_LOW`；厂商 U-Boot 的按键轮询把 `0` 当按下（§4），两边一致。
- 偏置：DTS、内核 GPIO 驱动、厂商 U-Boot 都没有写上下拉配置；`e2631net.c` 注释指出按键 bank 的方向位复位后为 0（输入），且不需要额外写。默认依赖板级外部上拉，与厂商行为一致。
- 注意（历史教训）：`docs/02-实施计划-2026-10-13.md:740-800` §L.5/§L.6 记录，在**厂商 Linux OS 里**用 `devmem2` 读 GPIO bank 寄存器（只读）会把板子读挂、看门狗重启；该现象只在厂商 OS 环境观察到。我们内核的 GPIO 驱动读同一批 `DATA` 寄存器正常，厂商 U-Boot 自己也在读（straps + 按键）——因此 U-Boot 侧读 `DATA` 大概率安全，但必须按 §9.1 先在 RAM 链上验证。

### 2.3 键位表里的其它输出（背景，不是触发键）

厂商 E1630 表还驱动 8 个输出：flat 8=1（蓝灯）、40=1（绿灯）、60=0（红灯）、55=0、52=0、54=0、51=0、2=0；其中 2 与 51 在表驱动之后又被厂商补驱到高（4 ms 间隔），对应 `e2631net.c` 的 `E2631_GPIO_PCIE_RST0/1`。按键触发只读 18/20，不碰这些输出。

## 3. 内核侧按键现状（现有行为与包属主）

### 3.1 设备树与驱动

- DTS keys 节点（dts:100-119）：`gpio-keys-polled`，50 ms 轮询；reset → `KEY_RESTART`，wps → `KEY_WPS_BUTTON`。
- 驱动：`package/kernel/gpio-button-hotplug/src/gpio-button-hotplug.c`；事件以 hotplug 形式交给 `/etc/rc.button/<label>`（label 为 `reset` / `wps`），环境变量含 `ACTION`、`BUTTON`、`SEEN`。

### 3.2 reset 键处理链

`package/base-files/files/etc/rc.button/reset`（ImmortalWrt base-files，未改）：

```
pressed)   [ -z "$OVERLAY" ] && return 0;  return 5
timeout)   . /etc/diag.sh; set_state failsafe
released)  SEEN < 1        -> 向 /dev/console 打 REBOOT + sync + reboot
           SEEN >= 5 且 overlay -> 打 FACTORY RESET + factoryreset -y && reboot
```

即：系统起来后短按 = 重启；按住 ≥5 s 再松 = factory reset。`SEEN` 是按下到松开的秒数（见 3.4）。

### 3.3 mesh/WPS 键处理链

- `package/network/config/wifi-scripts/files/etc/rc.button/wps`：`pressed` 直接 `exit 5`；`released` 依次执行 `/etc/rc.wps/*` 里第一个成功（返回 0）的脚本，全失败则无动作。
- 本树唯一脚本 `iwrt-tree/target/linux/zx279128/base-files/etc/rc.wps/00-h3600-ledblink`：让 `green:wps` 以 200/200 ms 闪 120 s，**总是 exit 1**，把机会留给后续脚本；它自己注释也写明「只处理 LED 侧」。
- 结论：当前 mesh 键按下去**只有灯闪**，没有任何 WPS 配对 / mesh 组网动作；也没有 hostapd 侧的按键触发。
- `iwrt-tree/target/linux/zx279128/base-files/etc/rc.button/lights_toggle` 存在，但 DTS 没有 `KEY_LIGHTS_TOGGLE` 键 → 死脚本。

### 3.4 hotplug 事件语义（决定 A 方案的冲突面）

`gpio-button-hotplug.c:258-293`：

- 驱动初始化时如果键已按下，会**上报一次按下事件**（注释原文：But we are very interested in pressed buttons）；松开时按 `SEEN = (jiffies - first_seen)/HZ` 上报。
- 因此**今天**：上电时按住 reset 一直到内核 GPIO 驱动 probe 之后，内核会看到「按下」，等用户松开且 SEEN ≥ 5 秒、overlay 存在 → 触发 factory reset。
- 这正是 A 方案要替换掉的行为：加了 U-Boot 长按触发之后，同样动作会先进救援，Linux 不会起来，也就不会 factory reset。发布说明必须写清楚这条语义变化。
- B 方案（mesh 键）没有 factory reset 冲突：现有 wps 链最长效果是灯闪 120 s；但如果将来给 mesh 键加 WPS PBC / mesh 配对，就会与 U-Boot 触发抢同一个键，届时需要再评估。

## 4. 厂商 U-Boot 的按键处理（静态逆向）

以下全部基于 `evidence/p2-oob/vendor-uboot-ram.bin`（vaddr = `0x47F00000` + 文件偏移；mtd0 偏移 = 文件偏移 + `0x20800`），用 capstone 线性/递归反汇编与字符串交叉引用测得。

### 4.1 调用链

```
run_main_loop 0x47f01660
  ├─ bl 0x47f13e68  cspboot 入口（正常启动）
  │     ├─ 打印 *** Press 1 means entering boot mode***（硬编码 3 s 倒计时）
  │     ├─ 用户按 1 -> 进 boot-mode 控制台 -> 继续走 shell 路径
  │     └─ 否则正常启动：Booting image -> pdt_cspboot_run -> bootm
  └─ bl 0x47f0f37c  boot-mode 控制台 shell（仅当 cspboot 入口返回失败/用户选择时）
        ├─ if bootdelay > 0: 打印 "Hit 1 to upgrade software version"（串 0x47f3a498）
        ├─ bl 0x47f1110c   <-- 按键检测在这里，倒计时之前
        ├─ 打印 "Hit any key to stop autoboot: %2d "（串 0x47f3a4bc），轮询按键
        ├─ run_command("autorun")（串 0x47f3a4e7，本 payload 无此命令 -> Unknown command）
        └─ 提示符 "=> "（串 0x47f37a42）
```

**关键结论：厂商的正常启动路径（cspboot -> bootm）从不进入这个 shell**，所以厂商固件「上电长按 reset 进救援/降级」在实际启动中没有发生；它只存在于 boot-mode 控制台路径。

### 4.2 按键检测细节

`0x47f1110c`：

1. 调 `0x47f110dc`：用 env 写入 `ipaddr=192.168.1.1`、`serverip=192.168.1.100`（字面量 0x47f3c23c/0x47f36d33/0x47f3c1cc/0x47f38d7c）；
2. `bl 0x47f2f2ac`（同时也是 shell 的 `Hit 1` 分支所用的恢复键检测）；
3. 若返回 0（键仍按住）：把全局字节 `0x47f67fec` 置 1，`run_command("downver version")`（串 0x47f3a965）；仅当返回值 ≥0 时 `mdelay(2 s)` 后 `run_command("reset")`（串 0x47f366db）；最后清标志。

`0x47f2f2ac`：

```
lookup board table entry index 0x1b (27) -> pin 18, dir=input
  helper 0x47f2f26c(index, &pin); 失败 -> 打印 "get KEY_RESTORE fail!\n"（串 0x47f3f7da），返回 1
loop 21 次:
    gpio_get(pin)               (0x47f2dcc4: 读 bank DATA +0x14 的对应位)
    if level == 0 (按下):  udelay(0x3d090 = 250 ms); 继续下一轮
    else (松开):          return 非 0
21 轮后 return 0
```

语义：**pin18 低 = 按下**；连续按住约 `21 × 250 ms = 5.25 s` 才返回 0。与上游 `glbtn` 的 4 s、内核 factory reset 的 5 s 都属于「数秒级长按」。

### 4.3 该分支在本 payload 里是死代码

厂商命令表 43 项（`0x47f5ee38..0x47f5f2d0`，每项 6 字：name/maxargs/repeatable/fn/usage/help）：

```
base bdinfo boot bootd bootk bootm bootz cmp coninfo cp cspboot cspnand cspnor
cspstart dhcp echo go gpiotest help i2c imxtract itest md mii mt mtddebug mtest mw
nand ping printenv ? reset run saveenv setenv sleep tftp upgrade version watchdog xmodem
```

表里没有 `downver`，整个 payload 也只有一处 `downver` 字面量（代码里的命令字符串，不是表项）→ `run_command("downver version")` 返回 -1（Unknown command），后面的 2 s 延迟与 `reset` 全部跳过。结论：厂商这段「长按恢复键 → 降级 → 复位」的意图在本固件里已失效，只剩地址/字符串遗迹。

其它读键位置：strap 读取（`0x47f2f0b8`，pins 5/15/62/61/43/47/46/45 算 product_vid）、板级表校验打印（`0x47f2f4e8/528/54c`）、杂项 `0x47f2de88`。**厂商从不因为 pin18/20 做任何联网/升级动作。**

## 5. 我们 U-Boot 的现状与改动面

### 5.1 现状（源码 `/home/qc233/zte/uboot-src`）

- `configs/zx279128s_zte_zxhn-e2631_defconfig`：**没有** `CONFIG_DM_GPIO`、`CONFIG_CMD_GPIO`、button 相关符号；payload 里没有 `gpio` 命令；启动时 `Starting kernel` 前也没有任何按键轮询。
- 唯一的 GPIO 代码是板级裸 MMIO（`board/zte/zxhn-e2631/e2631net.c`）：
  - `E2631_GPIO_BASE 0x94407000`、`E2631_GPIO_BANK_SIZE 0x40`、`DIR 0x00`、`SET 0x18`、`CLR 0x1c`（:90-95）；
  - `e2631_gpio_set_dir()`/`e2631_gpio_drive()`（:163-181）；**没有读函数**；
  - `e2631_gpios[]`（:148-151）只驱动 8 个输出；`e2631_pinmux_gpio_init()`（:192 起）做 pinmux + 输出 + 补驱 pin 2/51。按键 18/20 的方向位复位后本就为输入（同文件 :135-142 注释），不需要写。
- `board/zte/zxhn-e2631/e2631boot.c:490-513` `board_late_init()`：设置 `gd->bd->bi_boot_params`、`e2631_env_snapshot()`、`env_set("bootcmd", "e2631boot")`。这是现成的、每次启动必经的钩子。
- `e2631rescue`（`e2631rescue.c:947` U_BOOT_CMD；`do_e2631rescue`）自 patch 0034 起第一条动作就是 `e2631_net_refclk_init()`（:933-937），然后进阻塞式 `rescue_loop()`：lan1 起 DHCP + HTTP 页面，Ctrl-C 退出；只有 validate 通过且带 `X-E2631-Confirm: write` 时才走 `e2631flash` 五步写 mtd0 `0x20000..0xC0000`，从不自动重启、不保存 env。
- 当前 flash 的 0034 镜像已在真冷启动下验证：BootROM → secondboot → U-Boot → e2631boot → Linux，且救援页/validate 在提示符下可用（`evidence/e4-coldrescue-0034-20261128.md`、`evidence/e4-rescue-write-acceptance-20261128.md` §12-§13）。

### 5.2 触发所需的最小改动面

1. `e2631net.c` 加一个只读 helper（约 8 行）：读 `E2631_GPIO_BASE + (pin>>4)*0x40 + 0x14` 的 `BIT(pin&0xf)`；
2. 加 `#define E2631_GPIO_DATA 0x14`、`E2631_GPIO_KEY_RESET 18`、`E2631_GPIO_KEY_WPS 20`；
3. `board_late_init()` 末尾（`env_set bootcmd` 之后）加检测：见 §8 草图；
4. 可选：加只读调试命令 `e2631key`（打印两个键的当前电平），用于 §9.1 的零写入验证——**只读，不写 flash、不改配置**。

不需要：DM_GPIO/button 驱动、新命令表项（除可选调试命令）、baud 改动、env 写回、网络/cache 改动。预计增量 <1 KB（尺寸门禁 645,120 B 无压力）。

## 6. 上游先例：bl-mt798x 的恢复键

参考仓：`Yuzhii0718/bl-mt798x-dhcpd`（master `e4cf4dc72d451dc7a86c9508390ad5a2e50743c4`，2026-10-08；下游改造自 `hanwckf/bl-mt798x`；GPL-2.0）。task-70 的 `evidence/e4-bl-mt798x-dhcpd-study-20261127.md` 有完整文件/尺寸拆解，这里只摘按键相关：

- `common/main.c:89`：autoboot 之前 `run_command("glbtn", 0)`；
- `cmd/glbtn.c` `do_glbtn`：键名来自 env `glbtn_key`（默认 `reset`；Yuzhii fork 的 `failsafe/modules/env.c:98-107` 设默认 `reset,wps,mesh`），也可用 `glbtn_gpio` 逗号列表 + `!` 前缀表示低有效；按键解析走 button uclass label（`button_get_by_label`）或 `dm_gpio_lookup_name`；
- 检测到按下后每秒打印 `%s is pressed for: %2d second(s)`，循环到第 4 秒：点亮系统 LED 并 `run_command("httpd", 0)` 进 Web failsafe；未长按则什么都不做；
- 另有一次性 env 标志 `failsafe`：`common/main.c` 里 `env_get("failsafe") != NULL` → 清标志 + `env_save()` + 跑 `httpd`；bootmenu 里也有 `Start Web failsafe` 项（如 `board/mediatek/common/bootmenu_mtd.c:167`），并用 `MTK_WEB_FAILSAFE_AFTER_BOOT_FAILURE` 做启动失败计数。

对本项目的可移植性：

- 形状可照搬：**boot 前检测一个键 → 数秒长按 → 起 HTTP 救援**；阈值 4 s 与厂商 5.25 s 同量级。
- 不能照搬：`glbtn` 依赖 DM_GPIO + button uclass + env 键名映射，我们的 U-Boot 三者都没有（见 §5.1）；MT798x 的键定义/GPIO 编号也不能搬运（约束 #5）。
- 我们的等价实现 = 一个板级函数（读两个 raw 寄存器 + 一个循环），不需要通用框架，约 40-60 行。

## 7. 触发方案选项

| 选项 | 键/引脚 | 检测点 | 建议阈值 | 改动面 | 内核冲突 | 评价 |
|---|---|---|---|---|---|---|
| **A. reset 长按** | flat 18（`&gpio1 2`，低有效） | `board_late_init()`（autoboot 之前，每次启动必经） | 连续 2 s（从上电到判定约 5-6 s，见 §8.2） | `e2631net.c` 读 helper + `e2631boot.c` 约 40-60 行 | 与「按住 reset 过启动 = factory reset」重叠：动作被替换为救援 | 与厂商 KEY_RESTORE、上游默认键一致；发现性最好；**推荐** |
| B. mesh 长按 | flat 20（`&gpio1 4`，低有效） | 同上 | 连续 2 s | 同上 | 无 factory reset 冲突；仅有 WPS 灯闪 | 备选；发现性低（需要说明书）；将来若加 WPS PBC 会冲突 |
| C. 双键同按 | 18 + 20 同时低 | 同上 | 2 s | 同上（读两个键） | 同 A/B（无固定冲突，取决于是否同时保留 A） | 防误触最强；需要两只手/两个键同按，说明书成本高 |
| D. 任意键 + 确认窗口 | 18/20 任一 | board_late_init + 串口确认 | 按下后串口问 Y/N | 输出/输入交互代码更多 | 无固定冲突 | 无串口时无法确认；v1 不做 |

补充：

- 四个选项都只改 RAM 行为，不落 flash、不加 MTD 写路径（约束 #1）；
- 都不改串口 baud/输入输出（约束 #6）；
- 检测只在启动早期做一次；进入 U-Boot 提示符之后再按键不会触发（与厂商 boot-mode shell 的「检测一次」一致）。串口用户仍可手打 `e2631rescue`；
- A/C 的「按住 reset 过启动」语义变化必须进发布说明：之前 = factory reset，之后 = 救援。这是本任务唯一需要用户/产品确认的行为变化。

## 8. 推荐方案与实现草图

### 8.1 推荐 A（reset 长按），B 作为配置项

理由：

1. 与厂商板级表的 KEY_RESTORE（pin18）、上游 `glbtn` 默认 `reset` 一致，用户直觉正确；
2. pin18 是两键中更「恢复」语义的那个；mesh 键在当前固件里没有功能，但将来更可能被 WPS/mesh 占用；
3. 实现只要一个只读 helper + 一个循环，无新框架、无 flash 写入、无网络依赖；
4. 失败模式温和：误判/漏判最多是进不了救援（仍可串口手打）或进了救援（Ctrl-C 后 `e2631boot`/`reset` 回正常启动）。

### 8.2 操作方式（面向用户）

```
断电 -> 按住 reset 不放 -> 上电 -> 保持约 6 秒
直到串口出现 e2631rescue 输出（无串口时：PC 网口 DHCP 拿到 192.168.1.100，
浏览器打开 http://192.168.1.1/ 看到救援页） -> 松开。
```

时序说明：上电 → BootROM/secondboot/U-Boot 初始化 → `board_late_init` 大约 3-4 s；检测窗口 2 s（连续低）→ 物理按住约 5-6 s 足够，与厂商 5.25 s、上游 4 s 同量级。阈值最终通过 §9.2 的真机矩阵标定。

### 8.3 代码草图（伪代码，不是最终 patch）

```c
/* e2631net.c */
#define E2631_GPIO_DATA   0x14
#define E2631_KEY_RESET   18
#define E2631_KEY_WPS     20

int e2631_gpio_get_raw(unsigned int pin)
{
        ulong bank = E2631_GPIO_BASE + (pin >> 4) * E2631_GPIO_BANK_SIZE;
        return !!(e2631_readl(bank + E2631_GPIO_DATA) & BIT(pin & 0xf));
}

/* 返回 1 表示键在 window_ms 内持续按下（低） */
int e2631_key_held(unsigned int pin, unsigned int window_ms)
{
        unsigned int waited = 0;
        if (e2631_gpio_get_raw(pin))    /* 起始不按住 -> 立即返回 */
                return 0;
        while (waited < window_ms) {
                mdelay(50);
                waited += 50;
                if (e2631_gpio_get_raw(pin))   /* 中途松开 -> 不算 */
                        return 0;
        }
        return 1;
}

/* e2631boot.c board_late_init() 末尾 */
if (e2631_key_held(E2631_KEY_RESET, 2000)) {
        printf("e2631rescue: reset key held, entering rescue\n");
        env_set("bootcmd", "e2631rescue");   /* 仅 RAM，不 saveenv */
}
```

要点：

- 必须放在 `env_set("bootcmd", "e2631boot")` **之后**，否则会被 e2631boot 覆盖；`e2631_env_snapshot()` 已经在此之前，互不影响；
- 只用 RAM `env_set`，不调用 `e2631env save`，不写 mtd0/env 块；
- 救援 `Ctrl-C` 退出后回到提示符，`bootcmd` 仍是 `e2631rescue`；此时 `e2631boot` 可正常启动 Linux，`reset`（patch 0029，已真实）可回正常 flash 启动链——**写 mtd0 期间绝不能 reset**（既有约束，不变）；
- 不要改 baud、不要改 `board_late_init` 里的 ATAGS/env snapshot 顺序；
- 若采用 B/C，只是换 pin 列表/组合条件，代码形状相同。

## 9. 风险、验证计划与证据缺口

### 9.1 风险

| # | 风险 | 说明 / 缓解 |
|---|---|---|
| R1 | 读 GPIO DATA 寄存器是否安全 | 内核驱动与厂商 U-Boot 都在读同一寄存器；但 §2.2 记录的「厂商 OS 读挂」事件要求先验证：先在 RAM 链加 `e2631key` 只读命令，连续读 20 次两个键，观察是否挂起/看门狗复位；零写入 |
| R2 | 阈值/操作时序不匹配 | 用真机矩阵（长按 2/4/6/8 s、只按一下就松、上电后才按）标定，最终把「按住约 6 秒」写进文档和页面提示 |
| R3 | factory reset 语义被替换 | 发布说明 + 用户决策（§10）；如需保留 factory reset，后续可考虑救援页 v2 增加按钮（需要单独定 MTD 写路径/属主，不在本任务） |
| R4 | 键卡死（硬件故障）导致每次启动都进救援 | 连续 2 s 判定无法完全排除；缓解：救援 Ctrl-C 后 `e2631boot`/`reset` 手动回正常启动（串口）；后续可选加「跳过触发」env 白名单键（需用户批准） |
| R5 | 误触（搬动/清洁时压住 reset 上电） | 2 s 连续 + 松开即取消；C（双键）可进一步降低；说明书提示 |
| R6 | 进入救援后无人操作 | 救援循环消耗控制台输入（除 Ctrl-C），DHCP/HTTP 常驻；不写 flash、不超时重启；断电即可退出（约束 #4 的断电语义） |

### 9.2 验证计划（全部零写入，真机批准后进行）

1. RAM 链：userdata staging 载入候选 U-Boot（与既有 task-79 流程一致），`e2631key` 读 18/20，两种键未按下时打印高、按下时打印低；
2. RAM 链矩阵：不按键上电 → 正常 `e2631boot` → Linux；按住 reset 2 s、4 s、6 s、8 s → 分别观察是否进救援；只按一下立即松 → 不进救援；按住 mesh → 不进救援（A 方案）；
3. 进救援后：lan1 DHCP 租约、`GET /`、`/status idle`；`Ctrl-C` → `e2631boot` 回 Linux；全程 `mtd0` 与 env 块 sha256 前后一致（零写入判据）；
4. `reset` 回 flash 正常启动链（确认 patch 0029 行为不变）；
5. 只有以上全 PASS，才把触发逻辑并入正式 patch 系列；写 mtd0 仍需单独的用户批准（写入会话另行安排）。

### 9.3 证据缺口

- 调研时 `ssh root@192.168.1.1` 连接超时，未能采集 `/sys/kernel/debug/gpio`、`/etc/rc.button` 运行时 `ACTION/SEEN`、`logread` 现场证据；§3 的结论来自代码与文档，属静态证据 + 既有实测记录（docs/02 §655-661）。下次已批准的设备会话可只读补齐。
- 厂商 U-Boot 的按键路径只在 boot-mode 控制台可达；我们未在真机上验证厂商 shell 的 `downver` 分支（本 payload 无该命令，静态即可判定死代码）。

## 10. 未决问题（需用户/Lead 拍板）

| # | 问题 | 建议 |
|---|---|---|
| Q1 | 选 A（reset）还是 B（mesh）或 C（双键）？ | A；B 作为可配置项；C 仅在误触顾虑大时采用 |
| Q2 | 阈值 2 s 是否合适？操作说明写「按住约 6 秒」？ | 是；§9.2 真机后按实测微调 |
| Q3 | 救援是否要提供 factory reset（替换掉被占用的内语义）？ | 本阶段不做；若做，需要单独定义 MTD 写路径和属主（约束 #1/#8） |
| Q4 | 是否加「跳过触发」env 键（白名单扩展）？ | 暂不加；卡键场景可用串口 `Ctrl-C` + `e2631boot`/`reset` 绕过 |
| Q5 | 发布说明如何描述？ | 明确写「上电按住 reset ≈6 s 进救援；要 factory reset 请在系统内按住 reset ≥5 s 或使用 LuCI」 |
| Q6 | 救援页的认证要求（约束 #8）如何落地？ | task-81/v2 范围：口令或去掉 web 控制台；本文件不涉及 |

## 11. 附录

### 11.1 厂商 U-Boot 关键地址表（vaddr / payload 文件偏移 / mtd0 偏移）

| 对象 | vaddr | payload off | mtd0 off |
|---|---|---|---|
| cspboot 入口 | 0x47f13e68 | 0x13e68 | 0x34668 |
| run_main_loop 中 shell 调用点 | 0x47f01690 | 0x01690 | 0x21e90 |
| boot-mode 控制台 shell | 0x47f0f37c | 0x0f37c | 0x2fb7c |
| 按键检测 blob | 0x47f1110c | 0x1110c | 0x3190c |
| ipaddr/serverip 设置 | 0x47f110dc | 0x110dc | 0x318dc |
| KEY_RESTORE 轮询 | 0x47f2f2ac | 0x2f2ac | 0x4faac |
| gpio_get | 0x47f2dcc4 | 0x2dcc4 | 0x4e4c4 |
| 字符串 "get KEY_RESTORE fail!" | 0x47f3f7da | 0x3f7da | 0x5ffda |
| 字符串 "downver version" | 0x47f3a965 | 0x3a965 | 0x5b165 |
| 字符串 "resetting ..."/命令名 reset | 0x47f366db | 0x366db | 0x56edb |
| 字符串 "Hit 1 to upgrade software version" | 0x47f3a498 | 0x3a498 | 0x5ac98 |
| 字符串 "Hit any key to stop autoboot: %2d " | 0x47f3a4bc | 0x3a4bc | 0x5acbc |
| 字符串 "autorun" | 0x47f3a4e7 | 0x3a4e7 | 0x5ace7 |
| 提示符 "=> " | 0x47f37a42 | 0x37a42 | 0x58242 |

### 11.2 复现方法

- 反汇编：capstone（`pip install --target /tmp/pylibs capstone`，脚本用 `Cs(CS_ARCH_ARM, CS_MODE_ARM)` + 递归/线性扫描；vaddr = `0x47F00000` + 文件偏移）；
- 键表：厂商板级表基址 `0x47f42a7c`，行距 `0x128`，按 product_vid 索引；E1630 行 `0x47f44e54`，entry 数组 `0x47f59b28`，项距 `0x1c`（pin/dir/value/valid）；
- 内核/仓库证据：`iwrt-tree/target/linux/zx279128/dts/zx279128s-zte-zxhn-e2631.dts:100-119`、`iwrt-tree/package/base-files/files/etc/rc.button/reset`、`iwrt-tree/package/network/config/wifi-scripts/files/etc/rc.button/wps`、`iwrt-tree/target/linux/zx279128/base-files/etc/rc.wps/00-h3600-ledblink`、`iwrt-tree/package/kernel/gpio-button-hotplug/src/gpio-button-hotplug.c:258-293`；
- 上游：`git clone --depth 1 https://github.com/Yuzhii0718/bl-mt798x-dhcpd`（master `e4cf4dc7…`），看 `uboot-mtk-20250711/common/main.c:89`、`cmd/glbtn.c`、`failsafe/modules/env.c:98-107`；
- 历史文档：`docs/02-实施计划-2026-10-13.md:42`、`:154-155`、`:655-661`、`:740-800`；`evidence/p2-vendorless-network-gap-20261122.md`（GPIO 表来源）；`evidence/e4-reset-re-20261127.md`（reset 路径）；`evidence/uboot-e4-rescue-20261127.md`（0026-0029）；`evidence/e4-coldrescue-0034-20261128.md`、`evidence/e4-rescue-write-acceptance-20261128.md` §12-§13（当前 flash 冷启动/救援基线）。

### 11.3 一句话结论

reset 键 = flat GPIO 18（`&gpio1 2`，低有效），mesh 键 = flat GPIO 20（`&gpio1 4`，低有效）；厂商只在 boot-mode shell 里失效地读过 reset 键，上游 `glbtn` 是 4 s 长按 → httpd 的成熟先例；我们的 U-Boot 无 GPIO 框架但裸 MMIO 40-60 行即可复刻；推荐 A（reset 长按 ≥2 s，`board_late_init` 检测，RAM 内把 bootcmd 改成 `e2631rescue`），唯一需要用户确认的行为变化是「按住 reset 过启动」从 factory reset 变成进救援。
