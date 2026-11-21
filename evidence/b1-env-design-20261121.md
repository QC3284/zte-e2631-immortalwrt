# B1 厂商 U-Boot env 定制设计（task-46，2026-11-21）

> 范围：离线设计 + 产物生成 + 设备会话执行方案。**不写设备、不刷机、不动 mtd0 的 secondboot/U-Boot 区**。用户已批准 B 阶段（C→B→A），但按下文 §5.1 的纪律，B1 只写 env 区（`saveenv`），且真机动作由 Lead 排期的设备会话执行。

## 0. 结论摘要

1. **任务卡里「把 TFTP-first 脚本写进 bootcmd」无法按字面实现。** 正常启动路径在真正执行 `bootcmd` 之前，会先用内置字符串强制重写 `bootcmd`（不等则 `setenv` 并 `saveenv`），证据见 §2.2。env 层面只能加旁路变量，不能改变 `bootcmd` 的行为；这也**推翻了 `evidence/p2-uboot-research-20261121.md:188` 关于「bootcmd 脚本」的可行性判断**（该行以本文为准）。
2. 目标 env = **26 项**：`bootdelay 3→0`，新增 4 个单命令变量（`e2631_pocload` / `e2631_pocgo` / `e2631_netboot` / `e2631_flashboot`），**其余 21 项逐字节不动**，`bootcmd` 保持原厂字符串。
3. 目标 env 块：CRC32 `0x573ADD31`，块 sha256 `9f46ed98…`；整片 mtd0（模板 + 新 env）sha256 `c990bab3…`。与现 dump 的差异**全部落在 0xC0000–0xC02AA（141 B，env 块内）**；`0x20000–0xBFFFF`（secondboot/U-Boot 区）与 `0xE0000–0xFFFFF` 逐字节相同。
4. 仓库提交的是**文本 + 头部 hex**（`*.bin` 按 `.gitignore:5` 是生成物、不入库），设备会话前用一条命令重建块并核对 sha256，见 §4、§5。

## 1. 边界与输入

- 输入 dump：`/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin`（1 MiB，sha256 `de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f`）；env 块在 file `0xC0000`，大小 `0x20000`。
- 工具：`tools/e2631-env.mjs`（dump/build/verify/check），格式常量的唯一真相源是 `tools/lib/mtd0.mjs`（`ENV_OFF=0xC0000`、`ENV_BLOCK_SIZE=0x20000`、`ENV_DATA_SIZE=0x1FFFC`）。
- 前置研究：`evidence/p2-uboot-research-20261121.md`（B 阶段定位、B1 行、env 格式兼容性）、`docs/U-Boot结构分析-2026-11-15.md`、`evidence/uboot-re-20261115.md`（地址换算与头块修正）、`docs/救砖手册-2026-11-15.md`（控制台与回滚）。
- 本次不涉及：不改 U-Boot payload/头块；不碰控制台密码摘要（B2 另做）；不验证 tftp 的 autoload；不执行 `go`/POC（A1 会话另行批准）。

## 2. 为什么这样设计：vendor 启动路径实测

### 2.1 映像与地址换算

mtd0 前 0xE0000 的布局与换算关系（`evidence/uboot-re-20261115.md:29-33,45-50,58-74`）：

| file 区间 | 大小 | 内容 |
| --- | --- | --- |
| 0x00000–0x007FF | 0x800 | secondboot 镜像头块（+0x10 起 `128s`） |
| 0x00800–0x068AB | 0x60AC | secondboot 实际代码，运行时基址 0x00200000 |
| 0x20000–0x207FF | 0x800 | U-Boot 镜像头块（+0x10 `128s`，+0x14 长度 0x68000） |
| 0x20800–0x8683E | 0x6603F | U-Boot 实际代码，运行时基址 **0x47F00000** |
| 0xC0000–0xDFFFF | 0x20000 | 运行时 env：`[u32 LE CRC32][0x1FFFC 数据]` |

换算：`vaddr = 0x47F00000 + (file - 0x20800)`，`file = 0x20800 + (vaddr - 0x47F00000)`。本文所有 RE 地址均为 vaddr；U-Boot 代码从 file 0x20800 开始（头块是 **0x800 B 而不是 64 B**，`docs/U-Boot结构分析-2026-11-15.md:12` 的 0x40 说法已被 RE 修正）。

### 2.2 正常启动会先重写 bootcmd，再执行它（决定性证据）

正常启动调用链（串口实测 + 反汇编互证）：

`run_main_loop 0x47f01660` → `cspboot 0x47f13e68` → 未按 1 → `pdt_cspboot_run 0x47f15c10` → **启动执行器 0x47f15808** → `zteboot_do_settings 0x47f163bc` → 执行器运行 `bootcmd` → 再 `bootm <kernel>`。

关键指令与字符串（U-Boot 侧基址换算见 `evidence/uboot-re-20261115.md`；本任务逐条复核）：

| vaddr | 证据 | 含义 |
| --- | --- | --- |
| 0x47f15a24 | `bl 0x47f163bc` | 执行器在运行 bootcmd **之前**调用 do_settings |
| 0x47f164ec / 0x47f164f0 | `ldr r0,[pc]` / `bl getenv` | `getenv("bootcmd")`，字面量池 0x47f16810 → 字符串 0x47f36e45 |
| 0x47f251b0 / 0x47f25148 | `strlen` / `strncmp` | 把现 env 值与内置字符串比较 |
| 0x47f164fc / 0x47f16500 | `ldr r0` / `bl setenv` | 不同则 `setenv bootcmd <内置字符串>` |
| 0x47f1655c / 0x47f16564 / 0x47f1656c | `cmp r6,#0` / `ldr r0` / `bl run_command` | 有改写则执行 `run_command("saveenv")`；字符串 0x47f3918f「saveenv」 |
| 0x47f16774 / 0x47f167bc | `getenv("versioninfo")` / `run_command("saveenv")` | versioninfo（0x47f36bc2）同样被重建、不同则 saveenv |
| 0x47f15a44 / 0x47f15a54 / 0x47f15a6c | `getenv("bootcmd")` / `bl 0x47f0f364` / `bl 0x47f0f364` | 执行器随后真正运行的仍是 env 里的（已被重写的）bootcmd；再运行自建的 `bootm 0x%x;`（0x47f3c18c） |

内置 bootargs 字符串按 bootpara fstype 分派（`zteboot_do_settings` 0x47f163bc）：fstype 1 → 0x47f3c926；fstype 2 → 0x47f3c873（`root=%s ro rootfstype=%s  mem=$(memsize);`，参数 `/dev/mtdblock8` 0x47f3c8c0、`squashfs` 0x47f3c91d）；fstype 4 → 0x47f3c8cf（相同但结尾 `' mem=$(memsize) ;'`）。现网 env 里的 `bootcmd` 正好等于 fstype 4 的内置串（见附录 B 第 2 行），说明当前已是「do_settings 稳态」：每次正常启动比较相同、不再 saveenv。

**结论**：`bootcmd` 是厂商状态机的组成部分；自定义值会在第一次正常启动时被覆盖并 `saveenv`，之后正常启动运行的永远是内置 `setenv bootargs …`。因此「env-only 自动 TFTP-first」不可行，必须把能力放到不受 do_settings 管理的**旁路变量**里。

### 2.3 boot-mode 控制台与 bootdelay 语义

- 进 boot-mode 的 3 秒窗口是**硬编码常量**：cspboot 入口 0x47f13e68，`0x47f13e7c mov r5,#3`；与 env `bootdelay` 无关。串口操作（按 1、密码 `5cE080@fyBD`、必须以 CR 结尾、卡住的自救）见 `docs/救砖手册-2026-11-15.md:257-280`。
- boot-mode 控制台 shell 0x47f0f37c 才读 `bootdelay`：`getenv("bootdelay")`（0x47f0f380/0x47f0f384，字符串 0x47f3a48e，缺失默认 3），`simple_strtoul` 十进制（0x47f26328）；`bootdelay<=0` 时跳过定时等待，打印一次 `Hit any key to stop autoboot: %2d `（0x47f3a4bc）后走 `autorun`（未知命令 → 打印 `Unknown command 'autorun' - try 'help'`，属正常）→ `=>` 提示符。`-1` 无法表达（`simple_strtoul` 不处理符号，会得到 0），所以用 **0**。
- 因此 `bootdelay=0` 只缩短 boot-mode 控制台的等待，**不会**缩短正常启动的 Press 1 窗口（见上一条）。
- 注意救砖手册 §4.2（`docs/救砖手册-2026-11-15.md:277`）在「救砖」语境里要求不要 `saveenv`；B1 正是**经批准的 env 定制**，写的就是 env 区（0xC0000），不碰引导区其他位置。设备会话前仍需 Lead/用户确认。

### 2.4 命令面与脚本能力（决定「只能单命令」）

- 控制台实测 43 个命令名（`docs/救砖手册-2026-11-15.md:269`；`TEAM-NOTES.md:438` 记 44，以实测为准）：`? base bdinfo boot bootd bootk bootm bootz cmp coninfo cp cspboot cspnand cspnor cspstart dhcp echo fdt go gpiotest help i2c imxtract itest md mii mt mtddebug mtest mw nand ping printenv reset run saveenv setenv sleep tftp upgrade version watchdog xmodem`。
- **没有 hush**：payload 里没有 `hush`、`then`、`else`、`elif` 字符串；`if ` 只出现在帮助文本（for testing purposes if you…），`while`/`for `/`done` 只出现在「bad block table」「Architecture 0x%x」「clk won't change」等无关串里。⇒ 不能用 `if/then/fi`，脚本只能是单命令，或**未验证**的 `;` 序列。
- 本设计用到的命令（vendor 命令表实测入口）：`tftp@0x47f5f260`（fn 0x47f08664，help `[loadAddress] [[hostIPaddr:]bootfilename]`）、`go@0x47f5f014`（fn 0x47f03890，help `addr [arg ...]`）、`reset@0x47f5f1d4`（fn 0x47f01a40）；控制台侧 `setenv@0x47f5f228`（fn 0x47f08a64，help `[-f] name value ...`）、`saveenv`、`printenv@0x47f5f19c`、`run@0x47f5f1f0`（fn 0x47f0f604）、`md@0x47f5f0bc`（fn 0x47f0664c）。全部在 43 命令内。
- `tftp` 的 autoload（传输后自动 bootm）行为**离线未确认**，设备会话先做「只加载 + md 校验」（§5.8），不自动执行。

## 3. 目标 env 设计

### 3.1 决策 D1–D5

| # | 决策 | 理由 |
| --- | --- | --- |
| D1 | `bootcmd` 保持原厂字符串，一字不改 | §2.2：改也会被覆盖并触发 saveenv，只会增加风险 |
| D2 | `bootdelay 3 → 0` | 进 boot-mode 控制台后不再等 3 秒；正常启动的 Press 1 窗口不受影响（§2.3）；保守可随时改回 3 |
| D3 | 新增 4 个**单命令**变量 `e2631_pocload` / `e2631_pocgo` / `e2631_netboot` / `e2631_flashboot` | 旁路变量不受 do_settings 管理；单命令值不依赖 `;` 序列，控制台 `setenv` 可安全写入 |
| D4 | `ipaddr` / `serverip` / `ethaddr` / `netmask` / `gatewayip` / `ethact` 不动 | 保持现网值；临时换 TFTP 主机只需 `setenv serverip …`（不 saveenv） |
| D5 | 默认目标 env **不放** `;` 多命令脚本 | 无 hush（§2.4）；`;` 序列能力未验证；失败后自动 `go` 的风险高于收益。序列能力由设备会话的可选探针确认（§5.6、§7 Q3） |

### 3.2 逐项 diff（改 1 项、加 4 项、其余 21 项不变）

| 键 | 现值 | 新值 | 理由 / 依据 |
| --- | --- | --- | --- |
| `bootdelay` | `3` | `0` | §2.3：只影响 boot-mode 控制台倒计时 |
| `e2631_pocload` | （无） | `tftp 0x43000000 u-boot.bin` | A1 产物必须放在链接/入口地址 0x43000000（`evidence/uboot-ci-build-20261121.md:31,52,131-132`），加载用 vendor `tftp`（同文件 :152-153 的既定 RAM 链流程） |
| `e2631_pocgo` | （无） | `go 0x43000000` | 与加载配对；A1 会话才执行，B1 会话禁止执行（§5.8） |
| `e2631_netboot` | （无） | `tftp 0x42000000 e2631-netboot.uImage` | TFTP-first 的载入口；0x42000000 是现网 `loadaddr`/内核地址约定（附录 B）；`e2631-netboot.uImage` 是 A2/A3 才有的产物，**当前占位、inert** |
| `e2631_flashboot` | （无） | `reset` | 「失败回退原厂 cspboot」：`reset` 后回到 cspboot 的 Press 1 窗口/正常启动链（`reset` 语义实测见 `docs/救砖手册-2026-11-15.md:272-280`） |

不变的 21 项（全文见附录 B）：`baudrate`、`bootcmd`、`bootfile`、`bootloaderfile`、`console`、`ethact`、`ethaddr`、`fullfile`、`gatewayip`、`hostname`、`ipaddr`、`linuzfile`、`loadaddr`、`memsize`、`netmask`、`netretry`、`serverip`、`stderr`、`stdin`、`stdout`、`versioninfo`。

### 3.3 任务卡要求 → 本设计映射

| 卡内要求 | 本设计 | 说明 |
| --- | --- | --- |
| bootcmd 先试 TFTP 网络启动脚本 | 控制台 `run e2631_netboot` | 不能进 bootcmd（§2.2）；`tftp` 是否 autoload 由 §5.8 用只读方式确认 |
| 失败回退原厂 cspboot 流程 | `run e2631_flashboot`（= `reset`）或直接 `reset` | 不自动串联；失败/放弃时人工执行，回原厂启动链 |
| 脚本只用实测命令集 | 只用 `tftp` / `go` / `reset`（脚本值）；控制台用 `setenv`/`saveenv`/`printenv`/`run`/`md` | 全部在 43 命令内（§2.4） |
| bootdelay / ipaddr / serverip / ethaddr | `bootdelay 3→0`；网络参数不动 | §3.1 D2/D4 |

### 3.4 被否决的方案

- **改 bootcmd / bootargs**：被 do_settings 重建 + saveenv（§2.2），不采纳。
- **单变量 `;` 多命令脚本**：无 hush、序列未验证、失败自动 `go` 风险（§2.4、D5），默认不采纳；作为未来选项保留（§7 Q3）。
- **改 ipaddr/serverip**：没必要；保持现网，临时需要时用不 saveenv 的 `setenv serverip`。
- **用 `upgrade`/`nand`/`cspnand` 写**：手册禁用（未演练且写 flash，`docs/救砖手册-2026-11-15.md:473`），B1 不用。

## 4. 生成产物与校验

### 4.1 产物清单

| 文件 | 内容 | sha256 |
| --- | --- | --- |
| `evidence/b1-env-current-20261121.txt` | 现网 env 22 项（回滚基线） | `9f5aa9a93a6ded3055db4699c1c94b3ecdd5605f35a0e4e3840c1d85a8ad8d76` |
| `evidence/b1-env-target-20261121.txt` | 目标 env 26 项（生成块的内容源） | `d369ee61d93f94928e47146e98091cb9b8e94da46c09ee706af1cf5c7f8f826e` |
| `evidence/b1-env-target-20261121.hex` | 目标块前 768 B 的 `xxd`（含 CRC 与全部条目） | `87ba74d8306daccdc353f90b2c91afa210c6c9a0f9ebf6c8bab9fd2474c7d333` |
| （生成物，不入库）`b1-env-target.bin` | 完整 0x20000 env 块 | `9f46ed98d324644b51fda078d1be8eb3a270142b0cc3580b877ad64df3660a1d` |
| （生成物，不入库）`mtd0-target.bin` | 现 dump + 新 env 的整片 1 MiB | `c990bab35c0b4f5c03c0106c987794b826f7a4c5779d89831869b8eefe05a37f` |

### 4.2 重建命令与期望输出

```bash
cd /home/qc233/zte/e2631-immortalwrt
node tools/e2631-env.mjs build \
  --in evidence/b1-env-target-20261121.txt \
  --out /tmp/b1-env-target.bin \
  --template /home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin \
  --full-mtd0 /tmp/mtd0-target.bin
# 期望：env: 26 entries, CRC 0x573add31
#       wrote /tmp/b1-env-target.bin (0x20000 bytes, sha256 9f46ed98d324644b51fda078d1be8eb3a270142b0cc3580b877ad64df3660a1d)
#       wrote /tmp/mtd0-target.bin (full mtd0, sha256 c990bab35c0b4f5c03c0106c987794b826f7a4c5779d89831869b8eefe05a37f)
sha256sum /tmp/b1-env-target.bin   # 与上表一致
```

### 4.3 结构校验（本任务已全部执行）

- 块结构：前 4 B = `31 dd 3a 57`（LE CRC32 = `0x573ADD31`），之后是 NUL 结尾的 `key=value` 串，最后补 0x00 到 0x1FFFC；块内最后一个非零字节在 **0x2AA**，`0x2AB–0x1FFFF` 全 0。
- 独立复算：Python `zlib.crc32(block[4:])` 与存储值一致（`0x573ADD31`）；现网块复算 `0xAFFCEC3E` 也一致（`tools/e2631-env.mjs dump` 已报 `OK`）。
- 整片差异（现 dump vs 模板重建）只有 6 段，全部在 env 块内：`0xC0000–0xC0003`（CRC）、`0xC0086`（bootdelay 的 `0` vs `3`）、`0xC0220–0xC02AA`（4 个新条目文本，被 NUL 终止符自然分成数段）；累计 **141 B**。`0x00000–0xBFFFF`、`0xE0000–0xFFFFF` 逐字节相同 ⇒ 未触碰 secondboot/U-Boot 区。
- 目标块被写入整片后，`mtd0[0xC0000:0xE0000]` 与单独生成的块逐字节相同（工具 `--template` 路径已断言）。

### 4.4 为什么提交文本 + hex，而不提交 .bin

`.gitignore:5` 把 `*.bin` 定义为生成物（唯一输入例外是 `seed/vendor-verhdr-8b8.bin`，有专门注释）。env 块可由 §4.2 的文本**确定性重建**，sha256 已钉死，所以仓库里保存便于 review 的等价表示（文本 + 头部 hex）；设备会话前重建并核对 sha256 即可。

## 5. 设备执行方案（下次设备会话）

### 5.1 前置条件、物料与安全纪律

- 串口：板载 X1A22，3.3 V TTL，115200 8N1（`docs/救砖手册-2026-11-15.md:46`）；本机 `picocom -b 115200 /dev/ttyCH343USB0`（同文件 :77-78）。
- 网络：TFTP 主机 `192.168.1.100`，网线接 LAN1–LAN3；设备 `ipaddr=192.168.1.1`。
- 物料：A1 产物 `u-boot.bin`（本机归档 `/home/qc233/zte/e2631-t5-artifacts/uboot-a1-44869143179/files/e2631-uboot-a1-44869143179/u-boot.bin`，347,640 B，sha256 `a3771aca6144879701d5336ae032a6d242fab3e1c90a80dbea0710a6816679b3`，`evidence/uboot-ci-build-20261121.md:124-129`）；`evidence/b1-env-target-20261121.txt`；回滚基线 `evidence/b1-env-current-20261121.txt` + 原始 mtd0 dump（sha256 `de4ea5bd…`）。
- 安全纪律：B1 只做「env 区写入（saveenv）+ 只读验证」；**不执行 `go`、不刷槽、不用 `upgrade`/`nand`/`cspnand`/`mtddebug write`**（`docs/救砖手册-2026-11-15.md:473`）。任何写 flash 动作按项目硬约束先经用户批准（同文件 :479）。串口日志全量落盘（沿用 `board/ser-*.log` 惯例）。

### 5.2 进入 boot-mode 控制台（实测路径）

1. 上电，串口出现 `*** Press 1 means entering boot mode***`，在 3 秒内按 `1`。
2. 随后 `cspboot:1454 Entering boot mode ...` → `*** Please input bootmode password: ***`。
3. 输入密码 `5cE080@fyBD`，**必须以 CR（`\r`）结尾**，不能是 LF（`docs/救砖手册-2026-11-15.md:257-262`；用 picocom/minicom 直接回车即可）。
4. 看到 `Hit 1 to upgrade software version` 后，按**任意键（不要按 1）**停住自动升级；再看到 `Hit any key to stop autoboot: 3 2 1 0` 时按任意键，进入 `=>`。
5. `Unknown command 'autorun' - try 'help'` 属正常现象，不是错误（同文件 :262）。

### 5.3 动手前核对（只读）

| 命令 | 期望 |
| --- | --- |
| `printenv` | 22 项；`bootcmd` 等于附录 B 第 2 行；`versioninfo` / `memsize` / `ipaddr` / `serverip` / `ethaddr` 与附录 B 一致；**没有** `e2631_*` |
| `printenv bootdelay` | `bootdelay=3` |
| `printenv e2631_pocload` | `## Error: "e2631_pocload" not defined`（各实现文案可能略有差异，只要报未定义即可） |

把 `printenv` 全文抄进会话记录，作为回滚对照。

### 5.4 写入（逐条；多词值不需要引号）

vendor `setenv` 把 argv[2..] 用单个空格连接成值（与现网含空格的 `bootcmd`/`versioninfo` 同机制）；我们的值**不含 `;`**，因此逐条键入即可，不需要引号：

```text
setenv bootdelay 0
setenv e2631_pocload tftp 0x43000000 u-boot.bin
setenv e2631_pocgo go 0x43000000
setenv e2631_netboot tftp 0x42000000 e2631-netboot.uImage
setenv e2631_flashboot reset
```

每条成功只回 `=>`；出现 `## Error` 立即停止并重来（不要 saveenv）。

### 5.5 写入后即时核对（saveenv 之前）

| 命令 | 期望 |
| --- | --- |
| `printenv e2631_pocload` | `e2631_pocload=tftp 0x43000000 u-boot.bin` |
| `printenv e2631_pocgo` | `e2631_pocgo=go 0x43000000` |
| `printenv e2631_netboot` | `e2631_netboot=tftp 0x42000000 e2631-netboot.uImage` |
| `printenv e2631_flashboot` | `e2631_flashboot=reset` |
| `printenv bootdelay` | `bootdelay=0` |
| `printenv bootcmd` | 与附录 B 第 2 行**逐字符相同**（被改动则立即停止） |

若某项被截断/拼接错误（例如多词值只剩第一个词）：**不要 saveenv**，记录现象并结束会话；回退路径见 §5.9 B（env 块由编程器写回，需另行批准）。

### 5.6 可选：序列能力探针（无害，且可答 §7 Q3）

```text
setenv e2631_seqtest echo one; echo two
printenv e2631_seqtest
run e2631_seqtest
setenv e2631_seqtest
```

- 若 `printenv` 显示完整 `echo one; echo two`、`run` 打两行 `one` / `two` ⇒ `;` 序列可用（未来可把 `e2631_netboot` 升级成自动回退脚本，另行设计）。
- 若 `printenv` 只显示 `echo one` 并立刻出现 `two` ⇒ 控制台输入层把 `;` 当分隔符，序列不可用；主方案不受影响。
- 若出现 `Unknown command …` 之类 ⇒ 序列不可执行；同样不影响主方案。
- 三种结果都只影响「未来是否自动化」，与本次 env 写入无关；探针值随后删除。

### 5.7 saveenv 与持久化验证

1. `saveenv` → 期望 `Saving Environment to SPI Flash...` / `OK`（以实测文案为准）。
2. `printenv` → 26 项；四项 `e2631_*` 与 `bootdelay=0` 都在；`bootcmd`、`versioninfo` 未变。
3. 冷启动（断电重启或 `reset`，**不要按 1**）：串口日志应与改动前逐行一致（`*** Press 1 …` 3 秒倒计时 → `Booting image ......` → 固件搜索/选择 → 内核启动）。把日志与基线并排比对。
4. 可选：再次进 boot mode，`printenv bootdelay` 仍为 0 ⇒ 持久化确认。

### 5.8 可选：TFTP 只读功能验证（禁止 go）

1. 主机上把 A1 `u-boot.bin` 放进 TFTP 根目录，启动 TFTP 服务；若主机 IP 不是 192.168.1.100，先在控制台 `setenv serverip <主机 IP>`（**不要 saveenv**，会话结束再改回）。
2. 控制台执行 `run e2631_pocload`，期望出现类似：`TFTP from server 192.168.1.100; our IP address is 192.168.1.1; Filename 'u-boot.bin'.; Load address: 0x43000000; Loading: ######; Bytes transferred = 347640 (54df8 hex)`（文案/大小以实测为准）。
3. `md 0x43000000 8` → 与主机 `xxd -l 32 u-boot.bin` 逐字节一致。
4. 若 `tftp` 在传输后尝试 `bootm` 并打印 `Bad Magic Number` 后回到 `=>`：预期无害（只读内存，不写 flash）。
5. **禁止** `run e2631_pocgo` / `go 0x43000000`（A1 会话另行批准）；禁止 `upgrade`/`nand`/`cspnand`/`mtddebug write`。
6. 收尾：`run e2631_flashboot`（= reset）回正常启动。

### 5.9 回滚

- **A. 有控制台**（首选）：
  ```text
  setenv bootdelay 3
  setenv e2631_pocload
  setenv e2631_pocgo
  setenv e2631_netboot
  setenv e2631_flashboot
  saveenv
  ```
  然后 `printenv` 与回滚基线（`evidence/b1-env-current-20261121.txt`）逐项对照；正常启动冷启动日志应与基线一致。
- **B. 无控制台**：用编程器写回 env 区 `0xC0000–0xDFFFF`（或整片 mtd0；仅在 U-Boot 区也受损时才需要整片）。**只写数据区、并按片内 ECC 处理 OOB**（编程器 dump 的 OOB 全 0xFF，回写 ECC 未验证，`evidence/p2-uboot-research-20261121.md:33`；`docs/救砖手册-2026-11-15.md` §6.4/§6.6）。
- **C. env CRC 坏的自愈**：U-Boot 会退回内置默认 env，`bootcmd`/`bootargs` 由 do_settings 重建，cspboot 仍能启动；重进 boot mode 重设即可。这是 B1 最坏情况仍不砖的依据。
- 备份清单：回滚基线文本（sha256 `9f5aa9a9…`）、原始块 CRC `0xAFFCEC3E`、原始块 sha256 `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426`、原始 mtd0 sha256 `de4ea5bd…`、全片 v2 dump 路径（`/run/media/qc233/DATA/zxhn_e2631_full-v2-ECC.bin` / `…-RAW.bin`）。

### 5.10 中止与验收标准

- 中止：`printenv bootcmd` 与基线不同；`saveenv` 报错；任何非 env 写命令被执行；冷启动日志与基线不一致；控制台丢字符导致任一项值不符。
- 验收：26 项 env 持久 + 冷启动日志与基线一致 + （可选）`run e2631_pocload` 只读校验通过 + 全程无其他 flash 写（日志中除本次 `saveenv` 外没有 `Saving Environment`）。
- **本任务不执行设备会话**；会话由 Lead 排期，执行结果另写 evidence 记录。

## 6. 风险登记

| # | 风险 | 概率/影响 | 缓解 |
| --- | --- | --- | --- |
| R1 | `saveenv` 期间掉电，env CRC 坏 | 低/中 | §5.9 C：U-Boot 用内置默认 env，cspboot 仍能启动；重进 boot mode 重设 |
| R2 | 误改/写坏 `bootcmd` 或 `bootargs` | 低/高 | 本设计不动这两项；§5.5 逐字符核对 bootcmd；出错不 saveenv 直接回滚 |
| R3 | `bootdelay=0` 行为与预期不符 | 低/低 | 改回 3 并 saveenv（§5.9 A） |
| R4 | `tftp` 的 autoload 行为未知 | 中/低 | §5.8 只做加载 + md 校验；异常即 reset，不写 flash |
| R5 | 控制台 `setenv` 多词拼接不符合预期 | 低/低 | 值不含 `;`；写入后 `printenv` 逐项校验；不符即重设 |
| R6 | 未来厂商 `upgrade` 流程重置 env | 中/低 | 升级后重查 `printenv`；B1 会话禁用 `upgrade` |
| R7 | ECC/OOB：编程器写回时 ECC 位出错 | 中/高（仅回滚 B 路径） | 优先控制台回滚；必须编程器时只写数据区并参照手册 §6.6；本任务不涉及写回 |
| R8 | 串口密码/CR 坑（发 LF 会卡） | 中/低 | 按 `docs/救砖手册-2026-11-15.md:257-262` 的自救步骤 |
| R9 | 冷启动验证时机不对（误按 1 进 boot mode/升级模式） | 低/低 | §5.7 规程：不按键；看到 `Hit 1 to upgrade software version` 按非 1 键 |
| R10 | env 写磨损 | 可忽略 | 一次 saveenv；稳态下 do_settings 不再写（§2.2） |

## 7. 未决问题

- **Q1** `tftp` 命令的 autoload 语义（传输后是否自动 bootm）离线无法确认 → §5.8 只读验证时观察。
- **Q2** `e2631_netboot` 的产物名/加载地址要到 A2/A3 才定；当前是 inert 占位，B1 不验证它。
- **Q3** `;` 多命令序列能力 → §5.6 探针；若可用，未来可把网络启动做成单变量自动回退脚本（另行设计）。
- **Q4** `bootdelay` 最终取 0 还是 3 → B1 设备体验后定；3 是保守回退值。
- **Q5** 额外 env 变量/顺序是否影响厂商 `upgrade` 校验（未验证，手册 §10 把 upgrade 列为未验证/禁用）→ 不在 B1 使用 upgrade；若未来要用，先单独验证。
- **Q6** 若 A2 更换 POC 产物（文件名/地址），`e2631_pocload`/`e2631_pocgo` 需同步更新并重算 CRC。
- **Q7** 后续 B2（控制台密码摘要）或 A 阶段替换 U-Boot 时，env 区格式仍兼容（`[CRC32][0x1FFFC]`，`evidence/p2-uboot-research-20261121.md:29`），本设计可原样沿用。

## 8. 证据索引

- 现网 dump：`/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin`，sha256 `de4ea5bd…`；env 块 0xC0000/0x20000，CRC `0xAFFCEC3E`，块 sha256 `6eee153b…`。
- RE 与地址换算：`evidence/uboot-re-20261115.md:29-33,45-50,58-74`（0x800B 头块、payload 0x20800、基址 0x47F00000）。
- B 阶段定位与 env 格式兼容：`evidence/p2-uboot-research-20261121.md:20-33,62-63,188,195`（其中 :188 的 bootcmd 脚本可行性已被 §2.2 推翻，以本文为准）。
- A1 产物与 RAM 链步骤：`evidence/uboot-ci-build-20261121.md:31,52,124-132,152-153`。
- 控制台/串口/回滚纪律：`docs/救砖手册-2026-11-15.md:46,77-85,257-280,473-479`；43 命令清单同文件 :269。
- 本任务实测命令：见 §4.2，产物 sha256 见 §4.1。

## 附录 A 目标 env 全文（26 项，`evidence/b1-env-target-20261121.txt`）

```text
baudrate=115200
bootcmd=setenv bootargs console=$(console) root=/dev/mtdblock8 ro rootfstype=squashfs  mem=$(memsize) ;
bootdelay=0
bootfile=uboot.bin
bootloaderfile=bootloader.bin
console=ttyAMA0,115200n8
ethact=eth0
ethaddr=00:41:71:00:00:50
fullfile=upgrade.bin
gatewayip=192.168.1.1
hostname=unknown
ipaddr=192.168.1.1
linuzfile=vmlinuz.bin
loadaddr=0x42000000
memsize=256M
netmask=255.255.255.0
netretry=5
serverip=192.168.1.100
stderr=serial
stdin=serial
stdout=serial
versioninfo=U-Boot V1.0.0 20230828191152 0x2300000 0x1 0xaf 0x00
e2631_pocload=tftp 0x43000000 u-boot.bin
e2631_pocgo=go 0x43000000
e2631_netboot=tftp 0x42000000 e2631-netboot.uImage
e2631_flashboot=reset
```

## 附录 B 现网 env 全文（22 项，`evidence/b1-env-current-20261121.txt`，回滚基线）

```text
baudrate=115200
bootcmd=setenv bootargs console=$(console) root=/dev/mtdblock8 ro rootfstype=squashfs  mem=$(memsize) ;
bootdelay=3
bootfile=uboot.bin
bootloaderfile=bootloader.bin
console=ttyAMA0,115200n8
ethact=eth0
ethaddr=00:41:71:00:00:50
fullfile=upgrade.bin
gatewayip=192.168.1.1
hostname=unknown
ipaddr=192.168.1.1
linuzfile=vmlinuz.bin
loadaddr=0x42000000
memsize=256M
netmask=255.255.255.0
netretry=5
serverip=192.168.1.100
stderr=serial
stdin=serial
stdout=serial
versioninfo=U-Boot V1.0.0 20230828191152 0x2300000 0x1 0xaf 0x00
```

## 附录 C 目标块头部（前 768 B，`evidence/b1-env-target-20261121.hex`）

```text
00000000: 31 dd 3a 57 62 61 75 64 72 61 74 65 3d 31 31 35  1.:Wbaudrate=115
00000010: 32 30 30 00 62 6f 6f 74 63 6d 64 3d 73 65 74 65  200.bootcmd=sete
...
000002f0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
```

（`0x2AB–0x1FFFF` 全 0；完整 0x20000 块用 §4.2 命令重建。）
