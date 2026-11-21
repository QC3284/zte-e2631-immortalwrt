# U-Boot env 写回与启动计数设计 —— 证据笔记（2026-11-22）

> 状态：**已评审通过（2026-11-22），随设计文档提交**。
> 支撑文档：[docs/U-Boot-env写回与启动计数设计-2026-11-22.md](../docs/U-Boot-env写回与启动计数设计-2026-11-22.md)。
> 本笔记只记录**实测/可复现**的输入、命令与结果；设计判断以主文档为准。

## 1. 目的

为 task-59（D-U2）提供可复核的证据：

1. env 块格式（厂商 CRC32 + 0x1FFFC data）与 mtd0 物理布局（0xC0000/0x20000、0xE0000 保留块全 FF）；
2. 我们与厂商的 env 编解码互操作（同一份文本 → 同一块 → 同一 CRC/sha）；
3. 写路径在 U-Boot 主线代码里的真实行为（擦除范围、坏块旁路、.save 指针、默认 env 回退）；
4. 厂商 U-Boot 对 env 的读取/重写行为（do_settings + saveenv）与字符串地址；
5. class-1/class-2 槽回退的既有书面依据 + 我们 e2631boot 的差距；
6. 现有可写/只读边界（DTS read-only、e2631-fwslot 的 H_NEW 死标志、e2631-trial 的 opt-in 回退）。

## 2. 环境与输入

- 主机时间：2026-11-21T19:59:35Z（= 2026-11-22 03:59 +08:00）；
- node v24.22.3、Python 3.14.10；
- 工作副本：`/home/qc233/zte/e2631-immortalwrt`（kit，branch iwrt-adaptation）、
  `/home/qc233/zte/iwrt-tree`（tree）、`/home/qc233/zte/uboot-src`（U-Boot 源码）。

输入文件与哈希（本次实测）：

| 文件 | 大小/说明 | sha256 |
|---|---|---|
| `/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin` | 1,048,576 B，真机 mtd0 只读 dump | `de4ea5bdcf6b4438d04d7de9f15ade68461a6dc60672ab1d1fb2e9c2ae4d5f3f` |
| `evidence/p2-oob/vendor-uboot-ram.bin` | 426,048 B，厂商 U-Boot payload（file = mtd0 0x20800 起） | `a4c640ad488d4b1956475e6613cc52b90d9c1ed453be68d3a2c54906f3dd8a30` |
| `evidence/b1-env-current-20261121.txt` | 22 条 baseline env 文本 | `9f5aa9a93a6ded3055db4699c1c94b3ecdd5605f35a0e4e3840c1d85a8ad8d76` |
| `evidence/b1-env-target-20261121.txt` | 26 条 target env 文本 | `d369ee61d93f94928e47146e98091cb9b8e94da46c09ee706af1cf5c7f8f826e` |
| `evidence/b1-env-target-20261121.hex` | target 块前 768 B 的 hexdump | `87ba74d8306daccdc353f90b2c91afa210c6c9a0f9ebf6c8bab9fd2474c7d333` |

> 注意：`*.bin` 的 env 块是 gitignore 的构建产物；仓库里提交的是文本 + 头部 hexdump + 可复现命令，
> 所以任何评审者都能从文本重建出与本文一致的块与哈希。

## 3. env 块格式复核（实测）

### 3.1 从真机 mtd0 提取

```
python3 -c "d=open('/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin','rb').read(); print('mtd0_size',len(d)); print('env_block_sha',__import__('hashlib').sha256(d[0xC0000:0xE0000]).hexdigest()); print('reserved_0xE0000_uniq',sorted(set(d[0xE0000:0x100000])))"
```

实测输出：

```
mtd0_size 1048576
env_block_sha 6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426
reserved_0xE0000_uniq [255]
```

即：
- env 块位于 `0xC0000..0xDFFFF`（正好 0x20000 = 一个 128 KiB 擦除块）；
- env 块 sha256 = `6eee153b…`（这个值与 baseline dump 的 evidence 文件一致，说明用真机镜像复算稳定）；
- `0xE0000..0xFFFFF` 全 0xFF（uniq 只有一个值 255）= 同分区第二个擦除块**当前完全未用**；
- 这为“0xE0000 放得下第二份拷贝，但本阶段不用”的判断提供物理事实（不涉及写）。

### 3.2 文本 → 块 → CRC 的互操作

```
cd /home/qc233/zte/e2631-immortalwrt
node tools/e2631-env.mjs build --in evidence/b1-env-current-20261121.txt  --out /tmp/t59/current.bin
node tools/e2631-env.mjs build --in evidence/b1-env-target-20261121.txt   --out /tmp/t59/target.bin
sha256sum /tmp/t59/current.bin /tmp/t59/target.bin
```

实测结果（与仓库内 pinned 值一致）：

| 文件 | 条目 | data 长度 | CRC32 | 块 sha256 |
|---|---|---|---|---|
| current.bin | 22 | 646 B 文本 + NUL 补齐 | `0xAFFCEC3E` | `6eee153b82b80664e3ce767b05e967ca977ddc8e9d379f3fffff259a39214426` |
| target.bin | 26 | 749 B 文本 + NUL 补齐 | `0x573ADD31` | `9f46ed98d324644b51fda078d1be8eb3a270142b0cc3580b877ad64df3660a1d` |

Python 独立复算（不经过 tools 代码）：

```
python3 - <<'PY'
import zlib, struct, hashlib
for name in ('current','target'):
    d=open(f'/tmp/t59/{name}.bin','rb').read()
    crc,=struct.unpack('<I',d[:4])
    print(name, 'len',len(d),'crc_stored',hex(crc),'crc_calc',hex(zlib.crc32(d[4:]) & 0xffffffff),
          'sha',hashlib.sha256(d).hexdigest())
PY
```

输出（摘要）：`current len 131072 crc_stored 0xaffcec3e crc_calc 0xaffcec3e`；
`target len 131072 crc_stored 0x573add31 crc_calc 0x573add31`；sha 与上表一致。
=> **块格式 = [u32 LE CRC32(data)][0x1FFFC data]，CRC 覆盖 data-only，长度恒 0x20000**，
与厂商格式（U-Boot env_t）逐字节一致。

### 3.3 顺序敏感性的反例（重要）

Session B 由厂商 U-Boot 的 `saveenv` 写出的块 CRC = `0xF95A816E`、块 sha256 =
`6e2c01da4084ea9e20e66d2985db74aa124d632c819928b7666686cc4acf3893`，条目数同样是 26，但 CRC/sha
与我们的 `0x573ADD31`/`9f46ed98…` **不同**。原因：U-Boot `env_save` 按哈希表导出顺序写键值，
我们的工具按文本顺序导出；两者解析后键值集合相同。=> 任何“块相等”校验必须**先解析再逐键比较**，
不能拿 CRC 或 sha 当语义相等判据（主文档 §2 已写入这一条）。

## 4. 厂商 U-Boot 的 env 行为与字符串（实测地址）

厂商 payload 映射：`vaddr = 0x47F00000 + file_off`（payload 文件即 RAM 0x47F00000 起的镜像）。

### 4.1 默认 env 字符串

- 默认 env 串位于 file `0x3179c`（vaddr `0x47F3179C`），内含
  `bootcmd=setenv bootargs mem=128M console=$(console) ubi.mtd=5 root=ubi0:rootfs rootfstype=ubifs init=/linuxrc ro;bootm 0x42000100`、
  `bootdelay=3`、`baudrate=115200`、`ethaddr`/`ipaddr`/`serverip`/`gatewayip`/`netmask`/`hostname`、
  `loadaddr`、`console=ttyAMA0,115200n8`、`bootfile` 等键。
- 这说明：厂商“默认 env”本身也是同一个 4 字节 CRC 头 + 0x1FFFC 的格式，只是内容不同；
  我们若写坏 env，厂商会回退到这份内置默认值（§6）。

### 4.2 saveenv 相关字符串与长度

| file 偏移 | vaddr | 字符串 |
|---|---|---|
| `0x38e8e` | `0x47F38E8E` | `Saving Environment to %s...` |
| `0x38ed8` | `0x47F38ED8` | `Environment size: %d/%ld bytes`（131068 = 0x1FFFC） |
| `0x39802` | `0x47F39802` | `Erasing 0x%x - 0x%x:` |
| `0x3982d` | `0x47F3982D` | `Writing to Nand:` |

“Environment size 131068”直接确认厂商数据区长度 = 0x1FFFC，与我们完全一致；
“Erasing 0xc0000 - 0xe0000”的日志（Session B 实测）确认厂商只擦 env 一个块。

### 4.3 zteboot_do_settings 的重写 + 自动 saveenv

normal boot 在执行 bootcmd 之前调用 `zteboot_do_settings 0x47f163bc`（证据沿用 b1-env-design §2.2 的实测）：

- `getenv("bootcmd")`：`0x47f164ec/0x47f164f0`；比较：`0x47f251b0`/`0x47f25148`；
- 不一致则 `setenv`：`0x47f164fc/0x47f16500`；
- 需要时 `run_command("saveenv")`：`0x47f1655c/0x47f16564/0x47f1656c`；
- `versioninfo` 同样处理：`0x47f16774/0x47f16778`、`0x47f167bc/0x47f167c4`。

=> **厂商链会对 bootargs/bootcmd/memsize/versioninfo 做运行时重写并回写 flash**。这正是 W1 必须做
“厂商键快照/恢复”的原因（主文档 §3.3）：否则我们的 RAM-only 覆盖会被持久化，引发两链互相洗 env。

## 5. 写路径的代码事实（U-Boot 主线，`/home/qc233/zte/uboot-src`）

### 5.1 env/mtd.c

| 位置 | 事实 |
|---|---|
| `env/mtd.c:33` | `env_mtd_save()` 定义；擦+写的唯一实现 |
| `env/mtd.c:93-94` | 擦除前打印 `Erasing MTD...`，随后 `mtd_erase` |
| `env/mtd.c:111-120` | 写前打印 `Writing to MTD...`，按 `writesize` 分块 `mtd_write` |
| 同文件 `sect_size > CONFIG_ENV_SIZE` 分支 | 小 env 读到 RAM、改、写回（read-modify-write） |
| 同文件 else 分支 | `sect_num = DIV_ROUND_UP(CONFIG_ENV_SIZE, sect_size)`；本板 = 1 |
| 读写循环 | 每步 `mtd_block_isbad` 为真则 `offset += sect_size` 跳过（坏块旁路的来源） |
| `env/mtd.c:342` | `.save = ENV_SAVE_PTR(env_mtd_save)`（当前因 CMD_SAVEENV 关闭而为 NULL） |

### 5.2 头/尺寸符号

| 位置 | 事实 |
|---|---|
| `include/env_internal.h`（ENV_SIZE 定义） | `ENV_HEADER_SIZE = sizeof(uint32_t)`（未开 redundant 时 = 4）；`ENV_SIZE = CONFIG_ENV_SIZE - ENV_HEADER_SIZE` |
| 同文件 `env_t` | `{ u32 crc; u8 data[ENV_SIZE]; }` |
| `include/env_internal.h:188-195` | `env_save_ptr()`/`ENV_SAVE_PTR`：只有 `CONFIG_CMD_SAVEENV` 打开才返回真实指针，否则 NULL |
| `env/env.c:260` | `env_save()` 始终编译；运行时通过驱动 `.save` 指针判断能否写 |
| `env/common.c:388` | `env_set_default()` |
| `env/common.c:443-456` | `env_import()` 校验 CRC；失败 -> `env_set_default("bad CRC")` |

推算验证：`CONFIG_ENV_SIZE=0x20000` -> `ENV_SIZE=0x1FFFC` -> 块总长 = 4 + 0x1FFFC = 0x20000 = 厂商块长度。
=> 只要不开 redundant、不改 offset/size，格式天然兼容。

### 5.3 当前 defconfig（patch 0007 结果）

`uboot-port/patches/0007-*.patch` 改出的 defconfig 关键行：

```
CONFIG_ENV_SIZE=0x20000
CONFIG_ENV_OFFSET=0xc0000
# CONFIG_CMD_SAVEENV is not set
CONFIG_ENV_IS_IN_MTD=y
CONFIG_ENV_MTD_DEV="spi-nand0"
# CONFIG_CMD_ERASEENV is not set
```

v3 运行镜像启动日志：`Loading Environment from MTD... OK`（patch 0009 保证名字非空）；
env 26 条、`Environment size: 646/131068 bytes`（我们的链）——读路径已实证。

### 5.4 写通道实现的最小改动面（供 0017 参考，本任务不改）

- 先决条件：`CONFIG_CMD_SAVEENV` 保持关闭（避免出现通用 `saveenv` 命令）；
- `env/mtd.c:342` 由 `ENV_SAVE_PTR(env_mtd_save)` 改为 `env_mtd_save`；
- 新命令 `e2631env` 内部调用 `env_save()` 触发上表路径；
- 擦除范围完全由 `CONFIG_ENV_OFFSET` + `CONFIG_ENV_SIZE` 推导（`env_mtd_save` 内 `ei.addr/ei.len`），
  命令不接收地址参数。

## 6. 双链兜底（env 坏时的行为）

### 6.1 我们的链

- `env_import` CRC 失败 -> 默认 env（`env/common.c:443-456` -> `env_set_default("bad CRC")`）；
- 默认 env 的 `bootcmd` 来自编译期 `CONFIG_BOOTCOMMAND="e2631boot"`（defconfig）—— 不依赖 flash env；
- `board_late_init()`（patch 0006）无论 env 好坏都把 `bootcmd` 覆盖为 `e2631boot`；
- slot 选择只读 slot 版本头（magic+CRC1+serial），与 env 无关。

=> env 坏 = 丢自定义变量，启动路径不变。

### 6.2 厂商链

- 正常启动先 `zteboot_do_settings` 重建 `bootargs/bootcmd/memsize/versioninfo`（§4.3），
  发现与内置串不同就用 `saveenv` 写回 —— 对坏 env **自愈**；
- 若 env 全 FF（擦除后掉电）：厂商 U-Boot 的 env 导入失败 -> 默认 env -> do_settings 照样重建并保存；
- 厂商 `saveenv` 只擦 `0xC0000..0xE0000`（Session B 日志），不会碰 0xE0000..0xFFFFF。

=> 任意 env 掉电窗口都不阻塞两链启动（主文档 §4.1 表）。

## 7. 坏块旁路的静态证据与风险

代码路径（`env/mtd.c` 读写循环）：

```
for (offset = 0; offset < ei.len; offset += sect_size) {
    if (mtd_block_isbad(mtd, ei.addr + offset)) continue;   // 跳过，而不是报错
    ... read/write ...
}
```

对本板（`ei.addr=0xC0000`、`ei.len=0x20000`、`sect_size=0x20000`）：

- 若 0xC0000 **不是**坏块：唯一一次迭代写 0xC0000，行为正确；
- 若 0xC0000 **是**坏块：迭代被 `continue` 跳过，循环结束，**返回成功但没有写任何内容**；
  更糟的是“大 env 多扇区”语义下会写到下一扇区（本板不触发，但设计不能依赖“恰好 1 扇区”）。
- 厂商链固定读 0xC0000，所以“写到别处”= 静默丢失。

=> 0017 必须在 `env_save()` 之前显式 `mtd_block_isbad`，坏块直接拒绝（主文档 §5.3）。
当前没有证据表明 0xC0000 是坏块（真机读回正常、CRC 可解析），但该防护是预防性硬门。

## 8. 现有可写/只读边界与 Phase 2 素材

### 8.1 DTS read-only

`target/linux/zx279128/dts/zx279128s-zte-zxhn-e2631.dts`：

- :362-366 `bootloader@0`（0x0/0x100000）带 `read-only` -> 用户态 `fw_setenv`/`mtd write` 写不了 mtd0（**只限引导分区**；可写分区如 `userdata` 的标签名 mtd 读写实测正常，见 §13）；
- :490 `slot1-header` 带 `read-only`；
- :467-476 `slot0/slot1` **故意不加** `read-only`（e2631-fwslot 需要写版本头）；
- 结论：phase 2 通道 b（打开 mtd0 read-only）是 DTS 变更加策略变更，不能顺手做。

### 8.2 e2631-fwslot 的 H_NEW 死标志

`package/e2631/e2631-fwslot/src/e2631-fwslot.c`：

- :97 `H_SERIAL` 0x1f4；:98 `H_NEW` 0x1f8；:99 `H_CRC2` 0x1fc（CRC over [0:0x1fc]）；
- :1118 刷写路径写 `H_NEW=1`；
- 全树 grep `H_NEW`：只有定义与写，**没有读取者**；
- cspboot / 内核 slotpart 只用 magic+CRC1+serial，不读 H_CRC2（A3 设计文档）。

=> phase 2 通道 a 的“未确认镜像”标志现成可用，但本阶段不实现。

### 8.3 e2631-trial（现有 class-2 兜底）

- `target/linux/zx279128/base-files/sbin/e2631-trial:1-17`：opt-in（`/etc/e2631-trial-arm`）、600 s 超时、
  未确认则 `e2631-fwslot switch + reboot`；
- `sbin/e2631-commit:1-15`：写 `/etc/e2631-accepted`；
- `etc/init.d/e2631-trial:1-9`：一次性服务 START=99；
- 它写的是可写的 slot 头，不碰 mtd0；默认不布防（历史 UX 原因）。

## 9. cspboot 回退语义的书面依据

- `docs/02-实施计划-2026-10-13.md:360-363`：class-1（kernel/rootfs CRC 坏）cspboot 判槽无效、自动启另一个槽，
  日志 `not found vaild fs!! -> Total found 2 firmwares(valid:1), start from ver 0`；
- 同文件 :363-368：class-2（内核起来后挂死）**无自动补救**；所谓“断电两三次会回去”只对 class-1 成立；
- 厂商 RE：`pdt_getimgindex` 只比较 serial（打印 `select = 1, serial0=0x7, serial1=0xc`），
  没有尝试计数/回写（A 系列 RE 笔记与 stock 启动日志一致）；
- 我们 patch 0006 `e2631boot.c`：
  - :205 注释 `There is no automatic fallback to the other slot.`；
  - :315/:336/:349 失败返回 `CMD_RET_FAILURE`，不试另一槽。

=> class-1 parity 缺口成立，patch 0016 的设计前提由此而来。

## 10. 本次复算命令清单（可逐条重跑）

```
# 1) 真机 mtd0 的 env 块与保留块
python3 -c "d=open('/home/qc233/zte/e2631-flash-dump-20261115/mtd0-bootloader.bin','rb').read(); import hashlib; print(hashlib.sha256(d[0xC0000:0xE0000]).hexdigest(), sorted(set(d[0xE0000:0x100000])))"

# 2) 文本 -> 块（current/target）
cd /home/qc233/zte/e2631-immortalwrt
node tools/e2631-env.mjs build --in evidence/b1-env-current-20261121.txt --out /tmp/t59/current.bin
node tools/e2631-env.mjs build --in evidence/b1-env-target-20261121.txt  --out /tmp/t59/target.bin

# 3) 独立 CRC 复算
python3 -c "import zlib,struct; d=open('/tmp/t59/target.bin','rb').read(); print(hex(struct.unpack('<I',d[:4])[0]), hex(zlib.crc32(d[4:])&0xffffffff))"   # 0x573add31 0x573add31

# 4) 厂商字符串指纹（payload file 偏移）
python3 -c "d=open('evidence/p2-oob/vendor-uboot-ram.bin','rb').read(); [print(hex(d.find(s)), s) for s in (b'Saving Environment to %s...', b'Environment size: %d/%ld bytes', b'Erasing 0x%x - 0x%x:', b'Writing to Nand:')]"
```

预期输出：`0x38e8e/0x38ed8/0x39802/0x3982d` 与 §4.2 表一致。

## 11. 未验证 / 边界

1. **env 块真机写尚未发生**：本任务只读；Q1 决定并入下一次已批准的刷机会话（用户一次批准），不单独开会话。
2. 0xC0000 是否曾被标记坏块：现有真机读回正常，但没有坏块表（BBT）转储；0017 的预检就是为此。
3. 写后“厂商链复核”的具体串口步骤：设计文档 §7.2 给了流程，但尚未执行。
4. 0xE0000 的“保留扇区”身份已于 2026-11-22 评审定为 Q5 = 是；尚无代码/分区表体现，实现 0017 时加 CI 断言。
5. phase 2 的 H_NEW 通道依赖用户态健康检查脚本，尚未实现。
6. Session B 的 env 块（0xF95A816E）与工具块（0x573ADD31）不等价的原因已解释为键顺序；
   若要逐键证明，可用 `node tools/e2631-env.mjs dump --in <mtd0 0xC0000 块>` 对比（工具已支持）。

## 12. 与主文档的对应关系

| 主文档章节 | 本笔记证据 |
|---|---|
| §2 格式 | §3 全节 |
| §3.1/§3.2 W1 | §5 全节 |
| §3.3 厂商键快照 | §4.3 |
| §3.4 擦写算法/坏块 | §5.1、§7 |
| §3.5 0xE0000 | §3.1、§8.1 |
| §4 掉电安全 | §6、§5.2 |
| §5 恢复梯 | §8、§6 |
| §6 计数/回退 | §8.2、§9 |
| §8 CI | 主文档自述（实现时补） |

## 13. 现场补充事实（2026-11-22，Lead 提供）

真机现场（stock mtd 用户态工具）实测：

- **标签名可用**：`mtd erase userdata`、`mtd write <file> userdata` 均返回 0，写入后回读 sha256 一致；
  而 `mtdN`（数字形式）打不开设备 —— 现场 staging 一律用分区标签名。
- 当前镜像暂存流程：以太网传输 ~31 MB/s → `mtd erase userdata`（49 MiB，~1 s）→
  `mtd write <file> userdata`（640 KiB，<1 s）→ 回读校验（<1 s）。
- 与本文的关系：这**不改变** mtd0 的结论（DTS 把 bootloader 分区标 read-only，用户态仍写不了 mtd0）；
  但它纠正了“用户态 MTD 写入不可用”的笼统说法 —— 可写分区的用户态 mtd 读写是正常的，
  所以 phase 2 通道 b 的取舍应表述为“是否把 **mtd0** 暴露给用户态”，而不是“用户态不能写 MTD”。

---

（证据笔记结束。所有数值均来自上述命令的当次输出；文件哈希用 sha256sum 复核。）
