# 芯片级物理布局实测（ZTE ZXHN E2631 / FSNAND F35SQA001G，128 MiB）

- 任务：task-33（编2）"芯片级物理映射（dump v2 → 救砖手册升级）"
- 日期：2026-11-20 / 2026-11-21
- 输入：/run/media/qc233/DATA/zxhn_e2631_full-v2-ECC.bin（134,217,728 B）、/run/media/qc233/DATA/zxhn_e2631_full-v2-RAW.bin（138,412,032 B），以及 /home/qc233/zte/e2631-flash-dump-20261115/ 的 11 个分区级 dump
- 证据等级：**全部为只读实测**（mmap 逐字节比对 + 结构解析 + CRC 校验）。本任务没有对设备做任何操作，没有用编程器写回。
- 关联文档：docs/救砖手册-2026-11-15.md §6.6（面向操作的写回表）；evidence/programmer-dump-analysis-20261120.md（v1 dump 判废）；docs/U-Boot结构分析-2026-11-15.md（引导链）

## 0. 结论（先看这里）

1. **11 个 mtd 的真实芯片偏移全部确定**：mtd0 0x0、mtd1 0x100000、mtd2 0x200000、mtd3 0x300000、mtd4 0x500000、mtd5 0x700000、mtd6 0x2300000、mtd7 0x2700000、mtd8 0x3360000、mtd9 0x3800000、mtd10 0x3F00000。mtd0–mtd5 与 2026-11-15 的分区 dump **逐字节相同（0 差异）**；mtd2、mtd4 这两个此前没定过位的位置也一并钉死。
2. **分区表大小之和 131.75 MiB > 128 MiB 不是错**：mtd7/mtd8/mtd9 是 mtd6（slot1）内部的**嵌套别名窗**，合计 21.75 MiB。芯片唯一占用 110.0 MiB，剩 18 MiB = 未声明的原厂插件/配置区 17 MiB + 末尾 1 MiB 擦除态（全 FF）。
3. **mtd10 userdata 在 0x3F00000**（47 MiB，376 个 PEB）。当前是**重新格式化过**的空壳 UBIFS：376 个 PEB 全部带 UBI EC 头，EC 计数从 11-15 的全 1 变成"355 个 2 + 21 个 3"；卷内只有门禁脚本的 /etc/e2631-userdata-version 标记文件（内容 1 字节 0x0a），**没有任何用户数据**。
4. **当前芯片 = 11-15 之后写槽两次 + 重格式化 userdata 之后的状态**：slot1 与批量刷写 RUN3 产物（sha256 3d7825c9…）的载荷逐字节相同，差异只有 rootfs_data（overlay）和版本头 8 个字节（slot_start/serial/new/crc2）。因此 **mtd6–mtd10 的 11-15 dump 已经过期**；mtd0–mtd5 仍然可用。
5. **v2 dump 的 spare 区不可信**：RAW 文件 65,536 页 × 64 B 的 spare **全部是 0xFF**（非 FF 字节数 = 0），编程器没有导出真实 OOB/ECC/坏块标记。整片回写必须由编程器或 MTD 层按芯片 ECC 参数重新生成 spare，不能把 RAW 的 spare 原样写回。
6. **未声明尾部 0x6E00000–0x7F00000 实测是原厂 JFFS2**（文件名明文：datainfo.json、datainfo_backup.json、uu.conf、uuplugin、owdpts、start.sh/stop.sh、db_tbl_cfg.xml 等；文件内容为压缩数据）。DTS 注释（dts:511-515）与手册旧文写的"AES-128-ECB、只有原厂内核可读"与实测不符，见 §7。

## 1. 输入与方法

### 1.1 输入文件

| 文件 | 大小（B） | 时间 | sha256 | 用途 |
|---|---|---|---|---|
| /run/media/qc233/DATA/zxhn_e2631_full-v2-ECC.bin | 134,217,728（128 MiB） | 2026-11-20 23:57 | 4a20e6931808018a63378a7d630c3742bb49330441b996d3f4da690a2884b1fc | **本次主证据**：整片数据视图（每页只含 2,048 B 主区） |
| /run/media/qc233/DATA/zxhn_e2631_full-v2-RAW.bin | 138,412,032（65,536 × 2,112） | 2026-11-20 23:59 | 12bcf1700ce072f8889aed6fb610d5453f9aff48d29860efe7d2a9d9cafe3f53 | 原始页格式：2,048 B 数据 + 64 B spare |
| /run/media/qc233/DATA/zxhn_e2631_full.bin | 134,217,728 | 2026-11-20 18:22 | （无效，见下） | v1 dump，**判废** |
| /home/qc233/zte/e2631-flash-dump-20261115/ 的 mtd0–mtd10 | 见 §2 表 | 2026-11-15 00:05–00:06 | 见该目录 INVENTORY.md、手册 §2.3 | 分区级对照 |

**v1 dump 判废**：2026-11-20 18:22 的 zxhn_e2631_full.bin 是同一个 2,112 B 页的旋转/拼接重复，不含 secondboot/U-Boot/env/slot/rootfs 等任何真实内容（见 evidence/programmer-dump-analysis-20261120.md）。下文全部结论只用 v2 两份文件。

### 1.2 方法

- 两份 dump 都只读：mmap + numpy 视图，**没有把 128 MiB 复制到工作区**，没有写设备。
- 逐字节比对：把 11-15 分区 dump 放到 DTS 候选偏移处，与芯片数据视图直接比较（同时统计差异字节数、差异 64 KiB 块数、首个差异偏移）。
- 结构解析：uImage 头（大端）、squashfs 超级块（小端）、槽标记、版本头（fwslot.c 字段偏移）、UBI EC/VID 头（大端字段）、UBIFS 节点（含 CRC-32 校验）、JFFS2 节点（含 dirent 文件名）。
- 脚本与原始输出：/tmp/e2631-dump/recon30.py–recon45.py，out30.txt–out44.txt。核心结论不依赖脚本本身，均可按 §11 的命令复现。

### 1.3 关键前提：spare/OOB 不能作为恢复数据

- RAW 共 65,536 页 × 2,112 B；每页前 2,048 B 拼起来与 v2-ECC **完全相等**（numpy array_equal = True）。
- 每页后 64 B 的 spare：**全部 0xFF，非 FF 字节数 = 0**。
- 结论：这是"只读主区、spare 用 FF 填充"的导出方式。dump 里**没有**真实 ECC 校验字节、没有坏块标记、没有原始 spare。恢复时必须重新生成 spare（§9.3），并且不能根据本 dump 判断坏块（§9.4）。

## 2. 11 个 mtd 的真实芯片偏移（实测）

### 2.1 偏移表

| mtd | label | 大小（B） | 芯片偏移 | 结束偏移 | 备注 |
|---|---|---|---|---|---|
| mtd0 | bootloader | 1,048,576 | 0x0000000 | 0x0100000 | secondboot + U-Boot + env（env 在 +0xC0000） |
| mtd1 | tag | 1,048,576 | 0x0100000 | 0x0200000 | 原厂身份/MAC/工厂数据 |
| mtd2 | wifi | 1,048,576 | 0x0200000 | 0x0300000 | 原厂 WiFi 校准 |
| mtd3 | usercfg | 2,097,152 | 0x0300000 | 0x0500000 | 原厂用户配置（JFFS2） |
| mtd4 | defcfg | 2,097,152 | 0x0500000 | 0x0700000 | 原厂出厂配置（JFFS2） |
| mtd5 | slot0 | 29,360,128 | 0x0700000 | 0x2300000 | 原厂系统槽（兜底） |
| mtd6 | slot1 | 29,360,128 | 0x2300000 | 0x3F00000 | 我们的运行槽（含 mtd7/8/9 别名） |
| mtd7 | rootfs | 17,825,792 | 0x2700000 | 0x3800000 | = slot1 + 0x400000（squashfs + overlay 窗） |
| mtd8 | rootfs_data | 4,849,664 | 0x3360000 | 0x3800000 | = slot1 + 0x1060000（squashfs 之后切出） |
| mtd9 | slot1-header | 131,072 | 0x3800000 | 0x3820000 | = slot1 + 0x1500000（版本头在 +0） |
| mtd10 | userdata | 49,283,072 | 0x3F00000 | 0x6E00000 | 独立 UBI 数据盘（376 PEB） |

交叉验证：

- mtd7 + mtd8 首尾相接：0x2700000 + 0x1100000 = 0x3800000 = mtd9 起点；mtd8 起点 0x3360000 = 0x2700000 + 0xC60000。
- mtd10 起点 0x3F00000 = mtd6 结束偏移；mtd10 大小 0x2F00000，结束 0x6E00000。
- 0x6E00000–0x8000000（18 MiB）不在任何分区内，见 §7。

### 2.2 11-15 分区 dump 与当前芯片的比对量化

| mtd | 差异字节 | 差异占比 | 差异 64 KiB 块 | 首个差异 | 结论 |
|---|---|---|---|---|---|
| mtd0 | 0 | 0.000% | 0/16 | — | 相同 |
| mtd1 | 0 | 0.000% | 0/16 | — | 相同 |
| mtd2 | 0 | 0.000% | 0/16 | — | 相同 |
| mtd3 | 0 | 0.000% | 0/32 | — | 相同 |
| mtd4 | 0 | 0.000% | 0/32 | — | 相同 |
| mtd5 | 0 | 0.000% | 0/448 | — | 相同（原厂槽自 11-15 未被写） |
| mtd6 | 16,736,893 | 57.006% | 263/448 | 0x2300024 | 过期（构建不同 + overlay 不同） |
| mtd7 | 13,289,370 | 74.551% | 208/272 | 0x2700008 | 过期（squashfs mkfs_time 就不同） |
| mtd8 | 665,852 | 13.730% | 12/74 | 0x3360800 | 过期（overlay 内容变了） |
| mtd9 | 17 | 0.013% | 1/2 | 0x380003C | 过期（serial/CRC/构建相关字段） |
| mtd10 | 350,468 | 0.711% | 378/752 | 0x3F0000F | 过期（EC 计数 + 重格式化） |

读法：

- 前 6 个分区 0 差异 ⇒ 引导区、身份区、校准区、原厂配置区、原厂槽槽头/版本头自 2026-11-15 00:05 以来**没有被写过**（我们的升级路径确实不碰引导区，也和手册 §0.2 的声明一致）。
- mtd6 的首个差异在 mtd6+0x24（uImage 头的 CRC 字段），不是槽标记；槽标记 32 B 与 11-15 完全相同。
- mtd7 的首个差异在 0x2700008（squashfs 超级块的 mkfs_time），是"重新构建过"的直接证据。
- mtd9 只差 17 B，全部是 serial/CRC/构建相关的字段（详见 §4.3）。

## 3. 为什么分区大小之和（131.75 MiB）大于 128 MiB

11 个 mtd 大小相加 = 138,149,888 B = **131.75 MiB**。这不是分区表算错，而是因为三个分区与 mtd6 重叠：

| 关系 | 公式 | 大小 |
|---|---|---|
| mtd7 ⊂ mtd6 | 0x2700000 = slot1 + 0x400000，size 0x1100000 | 17.0 MiB |
| mtd8 ⊂ mtd6 | 0x3360000 = slot1 + 0x1060000，size 0x4A0000（= 0x1100000 − 0xC60000） | 4.625 MiB |
| mtd9 ⊂ mtd6 | 0x3800000 = slot1 + 0x1500000，size 0x20000 | 0.125 MiB |
| 别名合计 | | **21.75 MiB** |

- 芯片唯一占用 = mtd0 1 + mtd1 1 + mtd2 1 + mtd3 2 + mtd4 2 + mtd5 28 + mtd6 28 + mtd10 47 = **110.0 MiB**（= 115,343,360 B）。
- 131.75 = 110.0 + 21.75；而 110 + 17（原厂插件区）+ 1（末尾 FF）= 128 MiB，正好补满芯片。
- 设计原因：内核要在 /proc/mtd 里把 rootfs 窗口、rootfs_data、版本头分别暴露成可独立操作的 mtd 节点（对齐、切分、升级都按这些节点做），所以它们与 slot1 重叠，不会多占物理空间。

## 4. 运行槽 slot1（= mtd6）结构实测

### 4.1 槽内布局

| 槽内偏移 | 大小 | 内容 | 实测要点 |
|---|---|---|---|
| +0x0000000 | 32 B | slot marker | 33333333 cccccccc 88888888 dddddddd + 16×FF |
| +0x0000020 | ~3.33 MiB | uImage 内核 | 头 + 载荷；载荷后 0x00 填充到 +0x400000 |
| +0x0400000 | 0xC60000 | squashfs rootfs | hsqs；bytes_used 0xC46AEF，128 KiB 对齐后 0xC60000 |
| +0x1060000 | 0x4A0000 | rootfs_data | 运行期 jffs2 overlay（= mtd8） |
| +0x1500000 | 0x20000 | 版本头块 | 512 B 版本头 + 0xFF 填充（= mtd9） |
| +0x1520000 | 0x6E0000 | 空 | 100% 0xFF（7.375 MiB，槽内未用尾部） |

### 4.2 关键字段（实测值）

| 对象 | 字段 | 值 |
|---|---|---|
| uImage（+0x20） | time | 1,794,677,928（2026-11-14 17:38:48 UTC） |
| | size | 3,491,850 |
| | load/entry | 0x40008000 / 0x40008000 |
| | name | ARM ImmortalWrt Linux-6.18.60 |
| squashfs（+0x400000） | inode_count / mkfs_time | 1,754 / 1,794,677,928 |
| | block_size / block_log | 262,144 / 18 |
| | bytes_used | 12,872,431（0xC46AEF） |
| | compression / flags | 4 / 1,728 |
| 版本头（+0x1500000） | version 字符串 | ImmortalWrt v1.10.0 |
| | H_KERNEL_SIZE / H_FS_SIZE | 0x3FFFE0 / 0xC60000 |
| | H_SLOT0 / H_SLOT1 / H_SLOT_START | 0x700000 / 0x2300000 / 0x2300000 |
| | H_BUILD | 0x36323032 |
| | kernel CRC / fs CRC / H_CRC | 0x0DBAABE2 / 0x6ACDC8B7 / 0x74011783 |
| | serial / new / CRC2 | 11 / 1 / 0xF8CB731A |

字段偏移依据：树 fork package/e2631/e2631-fwslot/src/e2631-fwslot.c:69（KERNEL_MAGIC_SIZE）、:83–:97（H_KERNEL_SIZE/H_FS_SIZE/H_SLOT0/H_SLOT1/H_SLOT_START/H_SERIAL）、:104（slot_start 表）、:650–:657（槽表与 kSize/fsSize 校验）、:761（写 serial）。

### 4.3 三方比对：当前芯片 vs RUN3 包 vs 11-15 dump

| 对比对象 | 差异 | 解释 |
|---|---|---|
| 芯片 slot1 vs RUN3 包体（包文件 [0x214:0x214+0x1500000]） | 209,993 B（0.9536%），内核窗 0 差异、squashfs 窗到 0xC60000 0 差异；差异全部从包体 +0x1060000 起，外加版本头 8 B | 芯片 = RUN3 包的载荷原样 + 首启后写入的 overlay；版本头 8 B = slot_start（0x0→0x2300000）、serial（1→11）、new（0→1）、CRC2 重算 |
| 芯片 slot1 vs 11-15 mtd6 dump | 16,736,893 B（57.006%） | 11-15 dump 是 REF 构建（uImage time 1,794,624,080 / size 3,490,466），不是 RUN3 构建；且 overlay 也不同 |
| 11-15 mtd9 vs 芯片版本头 | 17 B：0x3C–0x3F（kernel CRC）、0x48–0x4B（fs CRC）、0xA4–0xA7（H_CRC）、0x1F4（serial 9→11）、0x1FC–0x1FF（CRC2） | 构建不同 + 写槽时 serial/CRC 更新 |

RUN3 产物：/home/qc233/zte/e2631-t5-artifacts/parity-43623162108/e2631-build-43623162108/release/e2631-immortalwrt-experimental.bin，22,020,628 B，sha256 3d7825c9fdb9a15992ab72393014ce6c13211d76757f162bbe8b3b8cf8dbb13d。包内版本头是模板值（serial 1、new 0、CRC2 0x97B2A209、slot_start 0），写槽时由 fwslot 重算 —— 这与"芯片头 8 B 与包不同"精确吻合。

**结论一**：任务卡里"mtd6 载荷窗一致"的正确读法是"**芯片 slot1 的载荷 = RUN3 包载荷**"，而不是"= 11-15 的 mtd6 dump"。
**结论二**：11-15 的 mtd6/mtd7/mtd8/mtd9 是旧的 REF 构建，回写它们等于把系统回滚到 11-15 之前（并且 serial 会退到 9）。

## 5. 原厂槽 slot0（= mtd5）结构实测

- 槽标记 + 内核：slot0+0x20 是原厂 uImage（time 1,758,807,062 = 2025-09-25 13:31:02 UTC；size 3,352,998；load/entry 0x40008000；name "Linux Kernel Image"）。
- 原厂版本头（slot0+0x1560000 = 0x1C60000，**不是**我们的 +0x1500000）字段：

| 字段 | 值 |
|---|---|
| version | V1.0.0.7B5.8000 |
| product | ZXHN E2631 V1.0.0 |
| H_KERNEL_SIZE / H_FS_SIZE | 0x33FDCC / 0x1220000 |
| H_KERNEL_FILEOFS / H_FS_FILEOFS | 0x234 / 0x340214 |
| H_SLOT0 / H_SLOT1 / H_SLOT_START | 0x700000 / 0x2300000 / 0x700000 |
| serial / new / CRC2 | 7 / 1 / 0x6D82DD02 |
| kernel CRC / fs CRC / H_CRC | 0x46C2F79E / 0xE25EF83D / 0xDBDF616E |
| H_BUILD | 0x35323032 |

- 布局互证：cspboot 按"slot + ceil(声明内核大小 / 128 KiB)"找 rootfs；原厂声明 0x33FDCC → 0x340000，包内偏移 H_FS_FILEOFS 0x340214 − 包体基址 0x214 = 0x340000，两者一致。实测槽内 0x340000 起就是高熵密文（AES-128-ECB 原厂 rootfs，0x1220000 = 18.125 MiB），一直到 +0x1560000 正好结束 —— 与版本头的 H_FS_SIZE 互证。
- 版本头之后 +0x1560200 起还有 **130,560 B 高熵数据**（唯一字节数 256、0x00 占 0.23%），到 +0x1580000 结束；性质未识别（疑为签名/加密附加块，未解析）。
- +0x1580000–+0x1C00000（6.5 MiB）为 100% 0xFF。
- **结论**：原厂槽布局与我们的槽不同（头在 +0x1560000，rootfs 起点 +0x340000，密文不可解析），只能原样保存/回写；正常升级不碰它（11-15 的 mtd5 与芯片逐字节相同）。

## 6. userdata（mtd10）实测

### 6.1 位置与 PEB 结构

- 芯片 0x3F00000–0x6E00000，47 MiB = 376 个 128 KiB PEB（0x3F00000 起，最后一个 0x6DE0000）。
- 376/376 个 PEB 都带 UBI EC 头：version 1；EC 计数为 2 的 355 个、为 3 的 21 个；vid_hdr_offset = 2,048、data_offset = 4,096、image_seq = 0x08E273EE。
- 对比 11-15 的 mtd10 dump：376 个 EC 头全为 1 ⇒ 11-15 之后整片至少被重新格式化过一次（§6.2）。
- 376/376 都能擦写并写入 EC 头 ⇒ 这 47 MiB 内至少没有"擦不动"的块；但坏块标记在 spare 里，本 dump 看不到，不能据此断言全芯片无坏块。

### 6.2 时间线

| 时间 | 事件 | 证据 |
|---|---|---|
| 2026-11-15 00:05 | mtd10 dump：376 个 EC 头全 1，只有 2 个内部 layout 卷的 VID 头，没有任何 UBIFS 卷 | dump 实测 |
| 之后（11-15 至 11-20 之间） | 重新格式化 + 创建卷：EC 计数变 2/3，出现 10 个 VID 头（2 个内部 layout 卷 vol_id 0x7FFFEFFF + 卷 0 的 8 个 LEB：lnum 0/1/2/4/6/10/11/13） | 本次实测 |
| 2026-11-20 23:57/23:59 | v2 整片 dump | 本次实测 |

### 6.3 UBIFS 卷内容

- 卷名 userdata（UBI 卷 0），UBIFS 超级块在 PEB 0x4F80000 + 0x1000 = 0x4F81000：min_io 2,048、leb_size 126,976、leb_cnt 352、log_lebs 3、lpt 2、orph 2、fmt_version 5、default_compr 3、uuid ef108a35-2ae3-40c9-ad44-60730b8d1f91。
- 全卷节点扫描：**253 个节点 CRC-32 全部校验通过**（超级块 1、MST 512 B × 116、inode 6、dirent 2、data 1、index 2、ref 2、commit-start 1、padding 122）。MST 节点每个提交写一份，数量偏多说明该卷被多次挂载/提交过（与门禁脚本反复测试相符；具体动作未逐次追溯）。
- dirent 只有两个：根目录下的 etc（目录）、etc 下的 e2631-userdata-version（文件）；该文件的数据节点只有 **1 字节 0x0a**。
- **结论**：当前 mtd10 是门禁脚本建立过的"空壳卷"，除版本标记外没有任何用户数据；11-15 的 mtd10 则是"空 UBI（无卷）"。两份都不含可丢数据。

## 7. 未声明尾部 0x6E00000–0x7F00000（原厂插件/配置区）

- 17 MiB 里只有 5 个 128 KiB 块含数据：0x6E20000、0x7040000、0x7900000、0x7960000、0x7E80000；合计 350,424 B 非 FF，其余全 0xFF。
- JFFS2 解析：351 个节点（285 个 inode、45 个 dirent、21 个 padding）；文件名（明文）按块分布：

| 块偏移 | 文件名 |
|---|---|
| 0x6E20000 | datainfo.json、datainfo_backup.json（多个版本）、unif_tmp_laninfo.01.laninfo_mgr.json |
| 0x7040000 | uu.conf、uuplugin（UU 加速器插件） |
| 0x7900000 | start.sh、stop.sh、owdpts、bin、.version、.dmac |
| 0x7960000 | （同一插件的后续 inode/数据块） |
| 0x7E80000 | db_tbl_cfg.xml（多个版本） |

- 文件内容本身是高熵（压缩/打包格式）数据，没有逐文件解包；但**文件名与目录结构明文可读**。
- 末尾 0x7F00000–0x8000000（1 MiB）为 100% 0xFF。
- **纠正**：DTS 注释（树 fork target/linux/sanechips/dts/zx279128s-zte-zxhn-e2631.dts:511-515）与手册旧文写的"0x6E00000–0x7F00000 是 AES-128-ECB、只有原厂内核可读"与实测不符：该区是原厂 JFFS2，元数据/文件名明文。AES-128-ECB 的是原厂 slot0 的 rootfs（§5）。DTS 注释应改（属 tree fork 的 T3/T4 范围）；手册已在 §6.6 纠正。
- 我们的固件不声明、不写这个区（DTS 没有对应分区节点），所以正常升级不会碰它；整片回写会把它一并恢复（同机无害，但不要跨机带走）。

## 8. 时效性：11-15 的 11 个 dump 现在还能用哪些

| mtd | 11-15 dump 内容 | 与当前芯片 | 能不能当"当前备份"用 |
|---|---|---|---|
| mtd0–mtd5 | 引导区/身份/校准/原厂配置/原厂槽 | 逐字节相同 | **可以** |
| mtd6 | REF 构建的整槽（serial 9） | 57.0% 不同 | 不能（回写=回滚到旧构建） |
| mtd7 | REF 构建的 squashfs + 旧 overlay | 74.6% 不同 | 不能 |
| mtd8 | 旧 overlay（jffs2） | 13.7% 不同 | 不能（会丢当前 overlay 内容） |
| mtd9 | 版本头 serial 9 | 17 B 不同 | 不能单独用（与 mtd6 必须同源） |
| mtd10 | 空 UBI（无卷） | EC 计数/卷结构不同 | 不能（回写=退回无卷状态） |

- "当前状态的完整备份"目前只有 v2 整片 dump（sha256 4a20e693…）。分区级"当前备份"应在运行系统里重新 dump（手册 §2.1 的命令）。
- 11-15 的 mtd6–mtd9 仍有历史价值（回滚到 11-15 系统），但必须四个分区一起写、且要接受 serial 退回 9；"单独回写 mtd9"没有意义。

## 9. 回写规则（数据区 only；手册 §6.6 是精简版）

### 9.1 用哪份数据

- 首选 v2-ECC（128 MiB，数据视图）；也可以把 v2-RAW 每页前 2,048 B 拼起来，二者已实测完全相等。
- 分区级恢复：用 11-15 的 mtd0–mtd5 文件（仍与当前芯片一致）；不要用 11-15 的 mtd6–mtd10 当作"当前状态"。

### 9.2 地址

- 整片：从芯片 0x0 起连续 128 MiB。
- 分区级：严格按 §2.1 表；特别注意 mtd8 = 0x3360000（不是 0x2700000 + 0x1100000 的某个近似值）、mtd9 = 0x3800000。
- 绝对不要用原厂 /proc/mtd 编号去猜偏移（手册 §2.4 的抄错点）。

### 9.3 ECC / spare

- 只写每页 2,048 B 主区；64 B spare 必须由编程器按芯片 ECC 参数重新生成，或让 MTD 层（nand write / ubiformat）处理。
- RAW 文件里的 spare 全 FF，**不能原样写回**（否则 ECC 校验失败或坏块标记丢失）。
- 编程器写入时的 ECC 模式/位宽需要与主控运行时一致（主控启动日志能确认本机 SPI-NAND 参数；写入前由用户确认编程器设置）。

### 9.4 坏块

- dump 不含 OOB ⇒ 无法知道坏块图。整片"无脑写"在有坏块的芯片上会把数据写错位。
- 可选策略：坏块感知写（MTD/ubi 工具）；或编程器写入后逐块回读，与数据视图比对并在出错块上跳过/重试。
- 本机证据：mtd10 的 376/376 个 PEB 都能格式化并写 EC 头，说明该区至少没有不可擦写的块；slot 区数据连续、未见异常空洞。但这是"推断"，不是坏块图。

### 9.5 一致性约束

- mtd6/7/8/9 是同一块物理区的嵌套视图：回写必须同一时点、同一来源。
- 整槽写 mtd6 会覆盖 mtd7/8/9 的内容；分区级写 mtd7/8/9 时若跨时点混用（例如 mtd7 用 11-15、mtd8 用当前），会得到"版本头 CRC 对不上 + overlay 与 squashfs 不匹配"的半坏槽。
- mtd9 的版本头 CRC 覆盖声明窗口（kernel+squashfs）；手工拼数据时必须保证 kernel/fs 大小与 CRC 字段一致，否则 cspboot 会拒绝该槽。

### 9.6 验证

1. 回写后整片回读，与 v2-ECC 的 sha256（4a20e693…）逐字节比对；或按分区与 INVENTORY.md 的 sha256 比对。
2. 检查 0x0 的 '128s'（secondboot 头）、0x20000 的 U-Boot 头、0xC0000 的 env CRC（0xAFFCEC3E）、0x2300000 的 slot marker。
3. 真机启动验证属于设备操作，必须先经用户批准（手册 §0 的硬约束）。

### 9.7 跨机禁忌

- mtd0（引导区）、mtd1（身份/MAC/工厂密钥）、mtd2（WiFi 校准）是本机唯一的身份数据；整片 dump 只适用于**同一台设备**。
- 把本机整片 dump 写到另一台 E2631 会克隆 MAC/身份，可能导致网络冲突或原厂功能异常。

### 9.8 门槛

- 写 flash / 刷芯片必须先经用户批准（项目硬约束）。
- 动手前先把当前芯片再整片读一遍（如果还能读），不要拿唯一备份去赌。

## 10. 未决与未验证

1. **编程器写回未验证**：本任务只做了只读分析；没有写回/启动证据。
2. **spare/ECC 真实性未知**：v2 两份文件的 spare 都是 FF 占位，无法判断编程器读取时是否做了片上 ECC 纠错；只能说 2,048 B 数据视图在 RAW 与 ECC 两份文件之间自洽。
3. **坏块图未知**：见 §9.4。
4. slot0 版本头之后 +0x1560200 起的 130,560 B 高熵数据性质未识别（不是 FF，也不是可解析结构）。
5. 原厂 JFFS2 插件区的文件内容（压缩格式）未解包；该区是否仍被原厂内核读写未验证。
6. DTS 注释（dts:511-515）与实测不符，待 T3/T4 修正；手册已在 §6.6 纠正。
7. v2 dump 采集于 2026-11-20 23:57/23:59；此后的任何写入没有证据排除（不过 11-15 dump 比对已覆盖 mtd0–mtd5，可确认这些区自 11-15 未变）。

## 11. 证据索引与复现

### 11.1 引用

| 事实 | 证据 |
|---|---|
| 分区表（我们的编号） | 树 fork target/linux/sanechips/dts/zx279128s-zte-zxhn-e2631.dts:362–364、:368–370、:389–391、:394–396、:400–402、:465–473、:476–478、:481–484、:487–489、:507–509 |
| 槽布局与 cspboot 取 rootfs 规则 | target/linux/sanechips/image/Makefile:7–13、:34–42；target/linux/sanechips/image/Makefile.e2631:11–28、:77；tools/mkfactory.mjs:121–132、:150–153 |
| 版本头字段偏移 / serial 写入 | package/e2631/e2631-fwslot/src/e2631-fwslot.c:69、:83–:97、:104、:544–:562、:650–:657、:761 |
| 11-15 分区 dump 与 sha256 | /home/qc233/zte/e2631-flash-dump-20261115/INVENTORY.md、manifest.log；手册 §2.3 |
| v1 dump 判废 | evidence/programmer-dump-analysis-20261120.md |
| 批量刷写 RUN3 与 serial 变化 | evidence/qshou1-batch2-flash-20261115.md；手册 §2.2 |
| 引导链（secondboot/U-Boot/env） | docs/U-Boot结构分析-2026-11-15.md；evidence/uboot-re-20261115.md |

### 11.2 脚本与输出

- /tmp/e2631-dump/recon30.py–recon33.py：早期探路（OOB/RAW 关系、magic 扫描、DTS 偏移比对）。
- /tmp/e2631-dump/recon34.py–recon38.py：槽头/版本头字段、squashfs 超级块、UBIFS 超级块。
- /tmp/e2631-dump/recon40.py–recon46.py：UBIFS 节点 CRC 校验、版本头字节级比对、槽0 字段。
- /tmp/e2631-dump/out30.txt–out44.txt：对应原始输出。
- 全部只读；没有把 dump 复制进仓库或用例目录。

### 11.3 复现要点

    # 1) RAW 的 2,048 B 数据视图 == ECC 文件
    python3 - <<'EOF'
    import numpy as np
    raw = np.fromfile('/run/media/qc233/DATA/zxhn_e2631_full-v2-RAW.bin', dtype=np.uint8).reshape(-1, 2112)
    ecc = np.fromfile('/run/media/qc233/DATA/zxhn_e2631_full-v2-ECC.bin', dtype=np.uint8)
    assert np.array_equal(raw[:, :2048].tobytes(), ecc.tobytes())
    assert not (raw[:, 2048:] != 0xFF).any()   # spare 全 FF
    print('ok')
    EOF

    # 2) 分区偏移比对（示例：mtd9）
    python3 - <<'EOF'
    ecc = open('/run/media/qc233/DATA/zxhn_e2631_full-v2-ECC.bin','rb').read()
    d = open('/home/qc233/zte/e2631-flash-dump-20261115/mtd9-slot1-header.bin','rb').read()
    chip = ecc[0x3800000:0x3800000+len(d)]
    print('diff bytes:', sum(1 for a,b in zip(d,chip) if a!=b))
    EOF
