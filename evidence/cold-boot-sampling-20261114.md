# 冷启动 / MT7916 初始化采样与完成度只读核查（task-19）

> 状态：**采样完成（含 2026-11-15 batch 2 追加）**：**两镜像累计 14/14 真冷启成功** —— v1.10.0 镜像 11/11（S1、S4、S7、S8–S15；MT7916 ready 54.5 ± 0.7 s），树 fork tip r0-83df1a9 镜像 3/3（S16–S18；ready 53.56 / 53.69 / 55.00 s，§3.5）。0 失败签名、0 自愈事件；早期 1/3 挂起假说在 0/14 下仍被统计否定。S5/S6 因串口链路故障未采集，排除在计数外；延期设备项见 §5.1
> 最后更新：2026-11-15 01:48 CST（batch 2 追加定稿）
> 归属：task-19（Q-验1，设备轨道，只读）；负责人 verify-docs

## 1. 目的与验收

- 目标：用可复现的串口采样统计真断电上电（cold power-on）时 MT7916 WiFi 初始化成功率与失败签名，回答 1/3 冷启动挂起假说。
- 验收：>=10 个真断电样本（理想 20+），成功率与失败签名有明确表格和结论；另对完成度矩阵中的只读项做现状核查，需写入配置才能实测的项单独排期（写入须经用户批准）。
- 只读边界：本任务不刷机、不改设备配置、不切槽；设备侧仅 SSH 只读命令与串口读取。

## 2. 采样装置（当前运行中）

- 硬件：CH343 USB 串口 1a86:55d3（DKMS V2.2），设备 UART PL011 @ 115200n8；主机 /dev/ttyCH343USB0。
- 单读者监督进程：/home/qc233/zte/e2631-capture/capture-supervisor.sh
  - 用 flock 保证全机只有一个读者；cat 退出后 5s 自动重启；原始字节追加到 /home/qc233/zte/e2631-serial-boot.log。
  - 事件（reader-start/end）追加到 /home/qc233/zte/e2631-serial-capture-events.log。
- 增量解析：/home/qc233/zte/e2631-capture/serial-bootwatch.mjs（detached，每 2s 读取新增字节）
  - 输出事件流 /home/qc233/zte/e2631-capture/boot-sessions.jsonl：boot_start、uboot、kernel、userspace_init、wifi_wait、mt7916_ready、wifi_done、fail_pattern、session_end。
  - 解析器已用合成日志自测（2 个会话、ready/done/panic/mt7915e-probe-fail 事件均正确识别）。
- 汇总：/home/qc233/zte/e2631-capture/summarize-bootwatch.mjs --md 输出每会话表格（boot_start CST、ready/done 内核秒数、结果、fail 计数）。
- 冷启动定义：**拔掉电源 >=5s 再上电**（真 cold power-on）。reboot 命令、看门狗复位、failsafe 恢复都属于温启动/恢复会话，只作对照，不计入冷启动成功率。
- 成功判据：串口出现 `e2631-wifi-boot: MT7916 ready`，随后出现 `automatic Wi-Fi initialization complete`，且无 panic/oops；设备可管理（SSH/网页）为附加确认。
- 预登记失败签名（出现即记录原始行，保留完整串口片段）：
  - **已知冷启动挂起签名**（docs/02-实施计划 P.2 + known-issues WIFI-COLD-BIND-HANG 记录）：控制台在 `mt7915e 0000:01:00.0: enabling device (0140 -> 0142)` 之后停住，没有 WM Firmware、没有 AER、没有 oops；盒子可能仍活着但射频永不 ready，只有真断电（PERST）能清卡；重绑会报 `Timeout for initializing firmware`。
  - docs/refs-local 另记录过：`Message 00000010 (seq 1) timeout` / `Failed to start MCU firmware`（同一固件下载窗口）。
  - PCIe link down / training 失败（mt7915e probe 前）
  - mt7915e probe 失败或 WM/WA Firmware 加载失败
  - wifi-on bind 后无 WM Firmware Version 输出
  - e2631-wifi-boot 等待超时后始终没有 ready（WiFi 不出现）
  - Kernel panic / Oops / Call trace
- 自愈事件（不算失败，但必须记录；用于区分“首次 bind 失败但已恢复”和“真挂起”）：
  - `e2631-wifi-boot: radio not ready; rebinding once` = 首次 bind 干净失败，脚本触发唯一一次自动重绑（wait_radio 每次等 30s）
  - `e2631-wifi-boot: previous initialization unfinished; retrying in 120s` = 上次启动留下 pending 标记（可能上次挂起或断电），本次启动清标记并延迟 120s 重试
  - `e2631-wifi-boot: MT7916 initialization failed` = 重绑仍失败
  - `automatic Wi-Fi disabled` = /etc/e2631-wifi-noautoload 存在（非故障，但该样本不能计入自动上电成功）
- 历史采集缺陷（已修复；19:12:25 起的再次中断见 §3.3）：2026-11-14 16:12 之后旧采集停止；此前存在多读者并发写同一日志的时段，日志尾部出现字节交错（例：末尾 `...port 5([ 1843.929886]...` 行），且当前运行会话启动时无采集。旧日志保留作历史证据，但**不能逐会话归因**，也不计入新样本计数。

## 3. 样本

### 3.1 历史参照（旧装置样本，不计入本轮成功率）

| 样本 | 时间（CST） | 启动方式 | MT7916 ready | 结果 | 证据 |
| --- | --- | --- | --- | --- | --- |
| S1 | 2026-11-14 15:19 | 真断电上电（TEAM-NOTES 记录 #1） | 53.71 s | 成功 | /home/qc233/zte/e2631-serial-boot-001-good.log（另见主日志第 1 段） |
| S2 | 2026-11-14 15:41:32 | 温启动（failsafe 恢复后的重启，起始方式未逐项记录） | 55.04 s | 成功 | 设备 dmesg（当前运行会话，uptime 12077s @ 19:02） |
| S3 | 采集日志中的第 2 段完整会话 | reboot 温启动 | 54.48 s | 成功 | 主日志第 2 段；受旧采集多读者/中断影响，会话归因不可靠 |

### 3.2 batch 1（2026-11-14 19:10–19:21，新装置；用户执行 3 次真断电 + 恢复后 1 次拔电试采样）

| 样本 | 时间（CST） | 启动方式 | MT7916 ready | 结果 | 证据 |
| --- | --- | --- | --- | --- | --- |
| S4 | 2026-11-14 19:10:37 | 真断电上电（batch 1 第 1 次） | 55.30 s | **成功**（wifi_done 55.47 s，0 条失败签名） | 主日志第 3 段；serial-bootwatch 会话 1（userspace 19:11:01，waiting 25s @ 28.91 s） |
| S5 | 2026-11-14 19:12:21 | 真断电上电（batch 1 第 2 次） | — | **未采集/无法归因**（串口 4 s 后停止，仅到 U-Boot/bootloader） | 主日志尾停在 `found fs: flashstart:2700000 rsize:c60000`（19:12:25.975）；reader 存活、设备侧 LuCI 正常（见 §3.3） |
| S6 | 2026-11-14 ~19:16 | 真断电上电（batch 1 第 3 次） | — | **未采集**（串口零字节） | 采集事件日志 19:18:43 reader-end / 19:18:48 reader-start（读者重启） |
| S7 | 2026-11-14 19:21:09 | **真断电上电**（用户复位 UART 接线后的试采样；用户已确认为拔电上电） | 53.72 s | **成功**（wifi_done 53.96 s；两个 AP 59.75 s 进入 forwarding；0 条失败签名） | 主日志第 4 段；serial-bootwatch 会话 3（mt7915e enabling 52.65 s） |

### 3.3 采集故障记录（19:12:25 起）

- 现象：原始日志自 19:12:25.975 起零字节；S5 停在 bootloader 阶段，之后用户的第 2/3 次上电都没有任何串口输出。
- 主机侧排查（只读）：reader 进程存活且阻塞在 read（STAT S，WCHAN wait_woken），fuser 确认 /dev/ttyCH343USB0 只有一个持有者；内核日志无 CH343 USB 断开事件（15:17:53 枚举后无 disconnect），sysfs 电源状态 active；tty 参数 115200n8、raw、-crtscts、-echo 均正常。本机 sudo 需密码、ptrace_scope=1，无法 attach 取证。
- 设备侧确认：http://192.168.1.1 返回 LuCI（"ImmortalWrt SNAPSHOT-r0-bde1448"），ICMP 正常 => **设备本身已正常启动**，缺字节属于串口链路故障，不是设备挂起。
- 恢复动作：19:18:48 终止旧 reader（PID 4099343）后 supervisor 自动拉起新 reader（PID 4154454），单持有者已确认；事件日志追加 INCIDENT 记录。
- 待用户：复位 UART 三根杜邦线（GND、适配器 RX <- 设备 TX），做 **1 次试上电**；若仍无字节再重插 CH343 USB。链路恢复后再继续 batch 2-3；S5/S6 按"未采集"处理，不计入成功率。
- **恢复结果（19:21–19:22）**：用户复位接线并做一次上电后，19:21:09 起日志恢复增长（91,743 B @ 19:12:25 -> 118,759 B @ 19:22:19），reader 存活、watcher 完整解析会话 3，S7 成功（ready 53.72 s、done 53.96 s、AP forwarding 59.75 s，0 失败签名）=> **串口链路故障确认，设备侧无异常**。用户已确认 S7 那次是拔电上电，因此计入冷启动样本。教训：读者进程存活不等于链路有字节，故增加主机侧静默看门狗（见 §7）。
- 主机侧静默看门狗：/home/qc233/zte/e2631-capture/capture-stallwatch.sh（30 s 轮询日志大小；静默 >=300 s 追加 CAPTURE-STALL 事件，恢复时追加 CAPTURE-RESUME；只写事件日志，不碰设备与 tty）。
- 采样计数口径：成功/失败只统计**采集完整**的真断电样本；batch 1 中 S5/S6 因串口中断未采集，不计入分母。batch 2–3 的 8 个完整样本与最终累计统计见 §3.4。

- 失败样本数：**0**（未捕获任何 MT7916 初始化失败签名；累计 11 个完整样本全部成功，见 §3.4；计数已定稿）。
- 历史背景：WIFI-COLD-BIND-HANG 的 1/3 结论来自 **2026-10 早期镜像**（3 次冷启动：挂/成/挂，见 docs/02-实施计划 §P.1、§S.7），不是 v1.10.0 的采样结果；本任务要验证该概率在当前 ImmortalWrt 树 fork 镜像上是否仍成立。
- 早期「4/4 成功」的说明：其中包含温启动与 failsafe 恢复会话；failsafe（initramfs）不加载 WiFi 模块，不能计为 MT7916 初始化成功。**采集完整的真断电样本目前为 S1、S4、S7、S8–S15 共 11 个**（11/11 成功，ready 53.38–55.30 s），达到 >=10 门槛；**batch 2–3 已由用户确认为拔电上电，计数定稿 11/11**。

### 3.4 batch 2–3：sessions 4–11（19:29–19:43，采集完整；用户已确认拔电）

用户按协议继续做了 8 次上电循环（**用户已确认全部为真拔电/真冷启**），串口全部完整捕获：

| 样本 | 时间（CST） | 启动方式 | MT7916 ready | 结果 | 证据（watcher 会话） |
| --- | --- | --- | --- | --- | --- |
| S8 | 2026-11-14 19:29:06 | 拔电上电（用户确认；依据见下） | 54.52 s | 成功 | session 4，wifi_done 54.73 s |
| S9 | 2026-11-14 19:31:08 | 拔电上电（用户确认） | 54.76 s | 成功 | session 5，wifi_done 55.00 s |
| S10 | 2026-11-14 19:32:56 | 拔电上电（用户确认） | 55.26 s | 成功 | session 6，wifi_done 55.49 s |
| S11 | 2026-11-14 19:34:40 | 拔电上电（用户确认） | 54.62 s | 成功 | session 7，wifi_done 54.82 s |
| S12 | 2026-11-14 19:36:26 | 拔电上电（用户确认） | 53.38 s | 成功 | session 8，wifi_done 53.61 s |
| S13 | 2026-11-14 19:38:15 | 拔电上电（用户确认） | 55.16 s | 成功 | session 9，wifi_done 55.42 s |
| S14 | 2026-11-14 19:39:57 | 拔电上电（用户确认） | 55.06 s | 成功 | session 10，wifi_done 55.27 s |
| S15 | 2026-11-14 19:43:01 | 拔电上电（用户确认） | 54.47 s | 成功 | session 11，wifi_done 54.72 s |

**分类依据（为什么判定为拔电上电，而非 reboot）**：

- 每个会话结束处都**没有** `procd: - reboot -` / `reboot: Restarting system` 关停序列，日志在正常运行途中戛然而止（个别边界伴随上电瞬间的 UART 乱码字节），符合直接断电特征；全日志仅 1 处软件重启记录（原始日志行 468–471），属于旧采集时段的历史内容，不在本轮样本内。
- 8 次 boot 间隔 1m42s–1m48s（首尾 2m02s / 3m04s），与「看到 WiFi 后拔电、>=5 s 再上电」的人工节奏一致；设备在 19:43:01 最后一次上电后持续在线至今（>12 min），**排除崩溃自重启/看门狗循环**（若为自重启应持续周期性发生）。
- 每个会话都有完整启动链：Boot SPI NAND -> U-Boot -> Linux 6.18.60 -> procd init -> MT7916 ready -> phy0/phy1 AP forwarding；boot-sessions.jsonl 中 fail_pattern 计数 **0**。
- **用户确认（19:56）**：Lead 转达用户确认，19:29–19:43 的 8 次均为真拔电上电，且没有做第 12 个样本；S5/S6 按「未采集」排除。

**累计统计（S1 历史 + 本轮 S4、S7、S8–S15）**：

- 完整真冷启样本 **11 个，11/11 成功**（**计数定稿**）；MT7916 ready 范围 53.38–55.30 s（均值 54.5 ± 0.7 s），wifi_done 与 ready 相差 0.2–0.3 s。
- 失败签名 **0**：无冷启动 bind 挂起、无 rebind/pending_retry 自愈事件、无 firmware timeout、无 panic/oops/PCIe 错误。
- 对早期 1/3 挂起假说的统计含义：11 个样本均为用户确认的真断电，按精确二项检验，H0: p=1/3 下观察到 0 次挂起的概率约 (2/3)^11 ≈ **1.2%**（单侧 p≈0.012），即当前镜像的冷启动挂起率显著低于 1/3；但 0/11 的 95% 双侧置信上限约 **28%**，仍不能给出高置信的「零挂起」保证。
- 目标 >=10 达成（含历史 S1）；**最终计数 11/11，采样结束**。采集链继续运行，便于后续回归复测/补采样。

### 3.5 batch 2（2026-11-15 01:38–01:44，新镜像 r0-83df1a9；用户执行 3 次拔电上电）

背景：T-20 重钉构建验证后，设备换到树 fork tip `83df1a9` 的镜像（DISTRIB_REVISION `r0-83df1a9`，
快照标记未修版本）做冷启动回归；串口采集链（§2）全程运行。用户于 01:38–01:44 CST 做了 3 次
真断电上电，bootwatch 会话 14/15/16 全部完整捕获：

| 样本 | 时间（CST） | 启动方式 | MT7916 ready | wifi done | AP forwarding | 结果 | 证据（watcher 会话） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S16 | 2026-11-15 01:37:55 | 拔电上电（用户执行；断电签名见下） | 53.56 s（53.563972） | 53.78 s | 59.76 s | **成功**，0 失败签名 | session 14 |
| S17 | 2026-11-15 01:40:56 | 拔电上电（用户执行） | 53.69 s（53.690743） | 53.91 s | 59.71 s | **成功**，0 失败签名 | session 15 |
| S18 | 2026-11-15 01:43:17 | 拔电上电（用户执行） | 55.00 s（54.998838） | 55.19 s | 61.10 s | **成功**，0 失败签名 | session 16 |

**断电（而非 reboot）签名核对**：原始日志最后一个软件重启记录在 offset 371090（`Restarting system`，
随后 371111 为 banner）；batch 2 的三个 banner（offset **403072、431054、459216**）之前均**没有**
`Restarting system` / `procd: - reboot -`，且日志在正常运行途中被截断：

- 403072 前：正常 `e2631-userdata-version` 写入行之后紧跟 NUL 字节 + CRLF（`...\0\r\n`），随后直接 ROM banner；
- 431054 前：正常 `br-lan: port 5(phy1-ap0) entered forwarding state\r\n` 之后紧跟 `\0\0\0\0\0\0\xf8\0\0\0\0\0\0\0\r\n`，再直接 banner；
- 459216 前：正常日志后接空行（`\r\n`），日志在运行途中截断，下一段直接是 banner。

全日志 18 个 banner 中只有 3 个（28594、340081、371111）前有 `Restarting system`（温启动），batch 2 的
3 个均无；配合“看到 WiFi 后拔电、>=5 s 再上电”的人工节奏，判定为真拔电。旁证：403072 前一段日志出现
`/tmp/e2631-mktest3` 写入 `content=[ImmortalWrt SNAPSHOT r0-83df1a9 ImmortalWrt v1.10.0]`，与 Lead 报告的
镜像版本一致。

**累计统计（跨镜像）**：

- v1.10.0 镜像：**11/11**（§3.4）；
- r0-83df1a9 镜像：**3/3**（本节）；
- 合计 **14/14 成功 = 100%**，失败签名 0、自愈事件（rebind / pending_retry）0、panic/oops/PCIe 错误 0。
- ready 合并均值：v1.10.0 54.54 s（范围 53.38–55.30 s），r0-83df1a9 54.08 s（53.56–55.00 s），
  14 样本合计均值 54.44 s。两个镜像都是“约 55 s 稳定初始化”；r0-83df1a9 的 3 个样本均值低 0.46 s，
  样本量小，不宣称差异显著。

**采样后的环境变化（Lead 记录，只读事实）**：WAN 已接上游并正常（carrier=1，DHCP 192.168.5.101 via
192.168.5.1），`ping 223.5.5.5` 约 19 ms，系统时钟已同步。该变化不影响冷启动统计（采样只依赖串口时序）。

## 4. 当前会话只读健康快照（19:02 CST）

- 版本：ImmortalWrt v1.10.0（运行分区 rootfs=mtd7，cmdline root=/dev/mtdblock7）；内核 Linux 6.18.60 armv7l。
- 运行时长：uptime 12077 s（约 3h21m），load 0.02/0.04/0.00；内存 248316 kB 总量、138216 kB 可用。
- 稳定性：dmesg 中 panic/oops/BUG 计数 0；无 mt7915e/mt76 失败行。
- WAN：192.168.5.101/24、1Gbps full、默认路由正常（上游 192.168.5.1）；LAN1-3 当前无载波（无有线客户端）。
- WiFi：phy0 AP HE40 ch1 26 dBm；phy1 AP HE80 ch36 28 dBm；MT7916 双频双 phy 正常。
- PPE 计数器路径：/sys/kernel/debug/92000000.ethernet/dma_state；当前 ppe_active=1 ppe_flows=0 ppe_add_skip=272 ppe_add_fail=0（skip 为开机以来累计，当前无活动流；dma_state 是驱动 counters 的唯一出口，文件内包含 ppe_* 行）。

## 5. 完成度矩阵：本次只读核查结果

| 项目 | 现状（只读实测） | 结论 | 下一步 |
| --- | --- | --- | --- |
| 监管域 | `iw reg get` = country CN: DFS-FCC；/lib/firmware/regulatory.db 存在；cfg80211 ieee80211_regdom=00（由 hostapd 按 wireless.radioX.country=CN 设置） | 早期矩阵中的「监管域缺失」在当前 v1.10.0 上不复现，记为已具备 | 补测 5G 非 DFS 信道与雷达检测行为（写入项） |
| WPA3（SAE） | hostapd v2.12、wpad-mbedtls 含 SAE 支持；当前 2.4G/5G 均开放 AP（encryption=none） | 能力具备；现网未启用 | 实测需改配置加密为 sae-mixed，待批准 |
| mesh | iw phy0 info 支持 mesh point；zte-mesh 包与 /etc/init.d/zte-mesh 已装；当前无 mesh 接口/进程 | 已装未测 | 实测需写配置并需第二节点/对端，待批准与排期 |
| PPE 上限 | 仅能读计数器；LAN 端口无载波，主机只有上游有线 + 设备 WiFi 客户端 | 无法做有线 NAT 满载复测 | 需用户提供有线 LAN 客户端（或将主机第二网卡接 LAN 口），并在主机空闲时测 |
| IPv6 | WAN 已有 240e:33d:70d:1f00::/64 与 fd37:d646:8038::/64 默认路由；forwarding=1；LAN 有 fddc:...::1/60 | 地址/路由就绪，软件路径转发未做流量实测 | 与 PPE 测试同批，主机空闲时测 |
| LED | /sys/class/leds：blue:status、green:wan-online、red:status、mt76-phy0、mt76-phy1 均存在且 trigger 可用 | 节点齐全 | 行为核对需 GPIO 读写（写入项） |
| 按键 | /proc/bus/input/devices 与 DT gpio-keys 均未发现按键节点 | 现状无按键输入设备 | 需核对 DT/驱动是否遗漏（代码审查项，非本任务只读点） |
| sysupgrade 保配置 | /etc/sysupgrade.conf 与 /lib/upgrade/keep.d 存在（keep.d 含 luci-theme-argon/luci-argon-branding 等历史项） | 结构就绪 | 保留配置升级实测需刷写（用户批准后才做） |
| PPPoE / 桥接 / AP 模式 | 未实测（WAN 当前为 DHCP） | 待测 | 写入项，逐项排期 |

### 5.1 明确延期到 Q-收1 的设备项（本任务不做，需用户批准/硬件条件）

以下三项属完成度矩阵中需要设备写入或硬件配合的验证，task-19 只读边界内无法完成，**明确延期到 Q-收1**，不阻塞本次采样结论：

- **有线 LAN 客户端下的 PPE 上限复测 + IPv6 转发吞吐测试**：需要一台有线 LAN 客户端（或主机第二网卡接 LAN 口）且主机空闲（当前主机负载高、LAN1-3 无载波）；属加压测试，延期 Q-收1。
- **WPA3(SAE) + mesh 双客户端实测**：需要改无线加密/mesh 配置（写入项）并需第二节点/对端；延期 Q-收1，待用户批准后一次一变量执行。
- **slot-0 受控启动验证**：需要切换启动槽/刷写操作，属设备写入动作，**必须经用户明确批准**；延期 Q-收1。

> 说明：§5 表格中「监管域、LED、按键、sysupgrade 保配置结构、PPPoE/桥接现状」的只读部分已在本次完成；凡标注「写入项/待批准」的行动项统一并入上述 Q-收1 排期。

## 6. 需要用户配合（阻塞项）

1. **冷启动采样（已结束）**：~~请做 >=10 次真断电上电~~ **采样已完成：11 个完整样本（§3.4），11/11 成功，达到 >=10 目标；batch 2–3 已由用户确认为拔电上电，本轮采样结束、不再需要补采样**；2026-11-15 在新镜像 r0-83df1a9 上追加 batch 2（3/3，累计 14/14，见 §3.5），回归采样结束。以下为原始协议，保留作后续回归复测用：
   - 每次：拔掉电源 >=5 秒 -> 插回上电 -> 持续观察 >=180 秒；正常应约 55-60 秒出现 WiFi（首次 bind 干净失败时脚本会 30s 等待 + 重绑，最晚约 120-180 秒出现）；无需人工确认，采集器自动记录。
   - 判据口径：**90 秒**内 WiFi 未出现也不要断电，继续保留现场 **2-3 分钟**（让 120 s 自愈重试与失败签名落盘），再由 Lead 决定是否断电重试。
   - 180 秒后 WiFi 仍不出现时**不要立即断电**：再保留现场 2-3 分钟（串口会把失败签名记录下来），然后告知 Lead，由 Lead 决定是否断电重试。
   - 每批结束后告知 Lead「第 N 批完成」，我据此统计并更新本文件。
2. 完成度实测的写入项（WPA3+mesh、PPPoE、桥接/AP、按键、保留配置升级）逐项需要用户批准，且一次一变量。
3. PPE 上限与 IPv6 转发流量测试：需要有线 LAN 客户端 + 主机空闲（当前主机 load 6.2，不适合做带宽基准）。

## 7. 后续

- ~~先恢复串口链路~~ **已完成（19:21）**：用户复位接线 + 1 次试上电后日志恢复字节，S7 完整成功；可继续 batch 2-3。若再次静默，先查 CAPTURE-STALL 事件（静默看门狗），再按 §3.3 处置。
- **采集链恢复（19:55）**：DSH 重启导致 supervisor/bootwatch/stallwatch 全部退出（后台进程不随会话保留）。已按附录 A 在 19:55:45 重启（supervisor PID 301465、bootwatch PID 301466、stallwatch PID 301467，单读者 cat 301483）；watcher 从 offset 335982 / session 11 继续。用户已确认 batch 2–3 的 8 次均为拔电，**无需再补第 12 个样本**，采样部分已收尾（见 §8）。
- **采集链状态**：采样结束后仍保持运行以便回归复测；若不再需要，可 kill 301465 301466 301467（supervisor 退出会带走 cat 读者）。
- 若捕获失败样本：保存完整串口片段（含 Boot SPI NAND 到失败点）、记录是否伴随 panic/PCIe 错误、记录恢复方式（重新上电是否恢复），交 Lead 决定下一步（不自行刷机）。
- 本文件已按 Lead 指示提交入库（task-19 收尾）；后续回归复测结果追加到本文件。

## 8. 结论与限制（已定稿）

- **成功率**：11 个采集完整的真冷启样本 **11/11 成功 = 100%**（Clopper-Pearson 95% 双侧置信区间约 71.5%–100%）；MT7916 ready = **54.5 ± 0.7 s**（范围 53.38–55.30 s），wiFi done 紧随其后 0.2–0.3 s。
- **失败签名**：0 条 —— 未出现冷启动 bind 挂起（enabling device 后停住）、未出现 rebind/pending_retry 自愈、未出现 firmware timeout / panic / oops / PCIe 错误。
- **样本属性**：11 个样本全部为用户确认的真断电上电（S4、S7、S8–S15）；S5/S6 因串口链路故障丢失，排除在分母外。
- **对早期 1/3 挂起假说**：0/11 在 H0: p=1/3 下的精确二项概率约 (2/3)^11 ≈ 1.2%（单侧 p≈0.012），**统计上否定 1/3**；但 0/11 的 95% 上限约 28%，尚不能排除较低概率（例如 5%–10%）的偶发挂起。若要把 95% 上限压到 <10%，约需 30 个连续成功样本。
- **限制与偏差**：用户手动拔电上电（非随机化采样），2 个样本（S5/S6）因串口链路故障丢失未计入分母；S1 来自较早的采集配置（同镜像 v1.10.0）；全部 8 个 batch 2–3 样本的「拔电」属性已由用户确认；采样期间设备一直是我们验证的 v1.10.0 镜像（未再刷写）。
- **结论（定稿）**：当前 ImmortalWrt 树 fork 镜像 v1.10.0 的冷启动 MT7916 初始化在 11 次真断电中全部成功（11/11，100%），未复现 2026-10 早期镜像的 1/3 挂起；该假说在 p=1/3 下被统计否定（单侧 p≈0.012）。建议把本结论与限制写入 known-issues/架构文档（不单独刷机验证）。
- **batch 2 追加（2026-11-15）**：新镜像 r0-83df1a9（树 fork tip 83df1a9，T-20 重钉构建）3 次用户拔电全部成功（S16–S18，ready 53.56 / 53.69 / 55.00 s，0 失败签名）；两镜像累计 **14/14**（100%，Clopper-Pearson 95% 下限约 78%）。断电签名（无 `Restarting system`、边界残留字节）见 §3.5。

## 附录 A：文件与复现命令

| 用途 | 路径 |
| --- | --- |
| 原始串口日志 | /home/qc233/zte/e2631-serial-boot.log |
| 历史快照 | /home/qc233/zte/e2631-serial-boot-001-good.log |
| failsafe 恢复会话 | /home/qc233/zte/e2631-serial-recovery-1.log、recovery-2.log |
| 采集事件 | /home/qc233/zte/e2631-serial-capture-events.log |
| 历史故障记录 | docs/known-issues.md（WIFI-COLD-BIND-HANG）、docs/02-实施计划-2026-10-13.md（§P.1/§P.2/§S.7） |
| 自愈逻辑源码 | iwrt-tree target/linux/sanechips/base-files/sbin/e2631-wifi-boot（DEFER=25、RETRY=120、一次 rebind） |
| 采集监督脚本 | /home/qc233/zte/e2631-capture/capture-supervisor.sh |
| 增量解析器 | /home/qc233/zte/e2631-capture/serial-bootwatch.mjs |
| 会话事件流 | /home/qc233/zte/e2631-capture/boot-sessions.jsonl |
| 汇总脚本 | /home/qc233/zte/e2631-capture/summarize-bootwatch.mjs |

复查命令（主机）：

```
pgrep -af "capture-supervisor|serial-bootwatch|capture-stallwatch"   # 三个进程应在
pgrep -af "^cat /dev/ttyCH343USB0$"                                  # 单读者
fuser /dev/ttyCH343USB0                                              # 应只有一个 PID
node /home/qc233/zte/e2631-capture/summarize-bootwatch.mjs --md      # 采样表格
tail -5 /home/qc233/zte/e2631-serial-capture-events.log              # 读者起停记录
```

采集链重启（DSH/主机重启后必须执行；后台进程不会自动恢复）：

```bash
cd /home/qc233/zte/e2631-capture
setsid nohup ./capture-supervisor.sh     >>/tmp/e2631-capture-supervisor.out 2>&1 </dev/null &
setsid nohup node ./serial-bootwatch.mjs >>/tmp/e2631-bootwatch.out 2>&1 </dev/null &
setsid nohup ./capture-stallwatch.sh     >>/tmp/e2631-capture-stallwatch.out 2>&1 </dev/null &
```
