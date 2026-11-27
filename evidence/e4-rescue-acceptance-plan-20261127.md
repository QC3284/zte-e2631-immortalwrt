# E4 救援模式验收方案与零净变更脚本

> 任务：task-75（E4-验1，救援模式验收方案 + 无浏览器脚本；纯文档/工具，无设备操作、无 flash 写入）。
> 日期：2026-11-27。关联：docs/E4-多功能U-Boot设计-2026-11-27.md（行为合同）、
> uboot-port/failsafe/README.md（页面/HTTP 契约）、evidence/e4-bl-mt798x-dhcpd-study-20261127.md（选型）、
> evidence/c1b0-entry-20261121.md 与 evidence/a1-banner-acceptance-20261121.md（零写入 RAM 链方法）、
> docs/救砖手册-2026-11-15.md §6.6/§6.7（回滚与编程器）。
> 交付：本文件 + tools/e4-rescue-acceptance.sh（默认仅校验，写入需双重开关）。

## 1. 结论摘要

1. **验收方案已冻结为「零净变更」**：唯一允许上传的镜像，必须等于板子当前 flash 里
   0x20000..0xC0000 这 0xA0000 字节的逐字节内容。当前（2026-11-27 18:27 SSH 只读核对）
   板的完整 /dev/mtd0 sha256 是 f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4，
   它来自 15-patch 镜像（banner g85df6772a444），镜像区文件是构建 run 44943940449 的
   e2631-uboot-mtd0.bin：sha256 b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a。
   本机已核对该产物（655,360 B、payload_len 0x6f6e0、crc32 0x0721e716、banner g85df6772a444）。
   擦除/写入/回读/比较五步全部真跑，但写进去的字节与原来相同，因此成功验收后
   /dev/mtd0 必须逐字节不变（前后完整 mtd0 sha256 相等，或至少镜像区 sha256 相等）。
   这样完整验证刷写通道，同时把「写坏 U-Boot 区」的风险压到与掉电同等级，而不新增镜像内容风险。
   注意：不要用 99886ea…（25-patch 构建产物）——它不在设备上，Lead 已更正。
2. **脚本 tools/e4-rescue-acceptance.sh 默认只做校验（validate-only）**。写入阶段要同时满足
   --write 与 --approval E4-RESCUE-WRITE-APPROVED 两个条件，缺一即退出码 3；脚本在写入前再次
   核对镜像 sha256，且从不调用 /reboot、不依赖 U-Boot reset 命令（本板 reset_cpu 仍是 patch 0003
   的占位实现，task-76 修复；返回 Linux 的唯一可靠方式是断电重启）。
3. **镜像身份由调用者钉死，不由脚本猜**：脚本默认 expected sha 为 b1ea9a48…，并支持
   --expected-sha 覆盖。正式验收前，verify-docs 必须在目标机上先测当前镜像区摘要：
   dd if=/dev/mtd0 bs=4096 skip=32 count=160 | sha256sum；把结果作为 --expected-sha，
   且上传文件必须正是该摘要对应的文件。两者不一致就停，不得迁就。
4. **设备侧摘要已成契约的一部分**：页面/脚本在上传时携带 X-E2631-SHA256，U-Boot 在擦除前
   校验接收缓冲区。脚本会发正确摘要；矩阵额外做一次「好 body + 错摘要」探测，必须被拒
   （HTTP 400 + result=error）。若设备忽略该头，脚本打印醒目 WARNING 并记为 NOTE；
   加 --require-digest 则把「未强制摘要」变成硬 FAIL。v1 若尚未实现摘要，验收按 WARNING 记录，
   不作为隐藏项。要点：摘要只绑定「HTTP 头 ↔ 收到字节」，证明传输完整；它不证明「上传文件 ==
   我预期的权威镜像」——后者由调用者用 --expected-sha 钉死，脚本也只用该镜像做写入。
5. **脚本已在本地 mock 服务上跑通全部逻辑**（mock 实现同一份冻结契约）：强制摘要时
   validate-only 37 PASS / 0 FAIL / 1 NOTE；带写入 50 PASS / 0 FAIL / 1 NOTE；两次退出码 0。
   不强制摘要的 mock（模拟尚未带摘要的旧构建）上：默认 PASS 但带 WARNING + NOTE；
   --require-digest 时 FAIL、退出码 1。
   矩阵中 size±1、坏 magic、长度越界、非 0xFF padding、缺 banner 均被拒且 /status 保持 idle；
   payload-flip 在 validate 会被接受（摘要绑定的是被改后的 body，见 §4），脚本记 NOTE 且绝不写入。
6. **运行时的关键前提（待 Lead 确认，§12 Q1）**：板子当前 flash 镜像区是 15-patch 镜像，
   不含 0026/rescue 页，直接 mtd read 并 go 出来的 U-Boot 没有 e2631rescue。方案要求 Phase 1
   先把含 0026 的 U-Boot 以零写入方式装入 RAM 再 go（具体装载源按 Lead 最终指令），并在
   S3a 增加硬断言：go 之后 U-Boot 必须存在 e2631rescue 且随后 GET / 可用，否则立即停止。
   Phase 2（把 0026 U-Boot 真正刷进 flash）是非零净升级，单独批准、不并入本验收。

## 2. 前置条件（全部满足才允许进入写入阶段）

| # | 条件 | 验证方法 | 不满足时 |
|---|---|---|---|
| P1 | Lead 明确批准本次写入（不是「可以测」，是「可以写 mtd0」） | 批准消息在案；执行者带 --approval E4-RESCUE-WRITE-APPROVED | 只跑 validate-only |
| P2 | 目标机当前镜像区（0x20000..0xC0000）的 sha256 与上传文件一致 | 正常启动 Linux 后 dd 出镜像区并用 sha256sum 摘要；记录 before；与本地镜像文件 sha256 比对 | 停止：不得用与当前 flash 不同的镜像做「零净」 |
| P3 | 含 0026 的 U-Boot 构建产物在手 | 产物 UBOOT-INFO.txt 含 0026 patch 行；含 E2631-FAILSAFE-ASSET.txt、e2631_failsafe_asset.c/.h；页面 gzip ≤6144 B | 停止，等任务合并/构建 |
| P4 | Phase 1 运行方式已确认（RAM 链；装载源见 Q1） | Lead 确认；go 之后 S3a 断言 e2631rescue 存在 | 停止，不用旧 U-Boot 冒充 |
| P5 | F2 修复在案：救援模式下 DHCP/HTTP 可达 | GET / 返回 200 且 Content-Encoding: gzip | 停止，先修 F2 |
| P6 | host 直连 lan1（不是 wan），拿到 192.168.1.0/24 地址 | ip a；或脚本 --dhcp（需 root） | 脚本以退出码 2 报前置错误 |
| P7 | 串口 115200 可用并开始记录 | verify-docs 的串口桥接脚本 | 停止；无串口不得写 mtd0 |
| P8 | 套件工作区处于被测构建的同一 commit（页面 sha 一致） | 脚本比较板端解压页面与本地 uboot-port/failsafe/e2631-failsafe.html；不同用 --page/--asset-stats 钉住 | 脚本 FAIL 并提示，不写 |
| P9 | 主机侧只通过 HTTP 与电源/串口操作设备 | 脚本不提供任何 reset/reboot 调用 | 人工确认 |

补充：P2 的 before 值必须与脚本的 --expected-sha 相同。若目标机镜像区不是本地文件，
不要改脚本常量去迁就，也不要把目标机镜像区取出来当载荷（Lead 明确：从设备重新生成的载荷
会让写入变成同义反复，证明不了任何东西）；应回到 artifact 与设备历史核对，或找 Lead 决策。

## 3. 零净变更对象的事实

- 当前完整 mtd0：1 MiB，sha256 f9239040…（2026-11-27 18:27 SSH 只读核对）。
  分区结构：secondboot 0x0..0x20000；镜像区 0x20000..0xC0000；env 0xC0000..0xE0000；
  保留 0xE0000..0x100000。救援写路径只写镜像区 0xA0000 字节，不碰 secondboot 与 env。
- 镜像区文件（15-patch 构建 run 44943940449）：e2631-uboot-mtd0.bin，655,360 B（0xA0000），
  sha256 b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a，
  CRC32 0x0721e716（整 655,360 B；脚本本地计算，设备 validate 返回同值则强证同一输入）。
- 布局：0x800 头块 + payload；+0x10 magic 128s，+0x14 payload 长度 0x6f6e0（456,416），
  payload 之后到 0xA0000 全 0xFF；payload 内含 U-Boot banner 字符串
  U-Boot 2027.01-rc2-g85df6772a444（Nov 21 2026）。
- 本机产物路径：
  /home/qc233/zte/e2631-t5-artifacts/uboot-du1-44943940449/e2631-uboot-44943940449/e2631-uboot-mtd0.bin
  （UBOOT-INFO.txt 明确 mtd0 image sha256 = b1ea9a48…；SHA256SUMS 可交叉核对）。
- 为什么 0026 不改变零净性质：base-builder 冻结确认 patch 0026 不改 mtd0 头/payload 布局，
  也不加 CRC/摘要字段（摘要走 HTTP 头，不写镜像）；所以该镜像原样上传仍应通过结构校验。
  若 0026 构建自身也产生新的 mtd0 镜像，那属于 Phase 2 升级对象，不是本验收的零净载荷。
## 4. 设备侧契约（task-72 patch 0026，2026-11-27 冻结）

| 项 | 契约 |
|---|---|
| GET / | 200，单页 HTML，gzip 压缩后原样回传，带 Content-Encoding: gzip；页面内容来自构建期嵌入的 gzip 资产 |
| GET /status | 200 text/plain，逐行 key=value；至少含 stage、progress、result、crc32、error（按阶段出现），以及 sha256=设备摘要、browser_sha256=收到的头值（或空）、sha_match=ok/mismatch/absent；未知键必须被容忍 |
| POST /flash?mode=validate | 原始 body（非 multipart），Content-Length 精确；建议带 X-E2631-SHA256；同步校验，成功 200 + result=ok + crc32=0x… + sha256=… + sha_match=ok/absent；失败 400 + result=error + error=简述；/status 保持 idle，不进入写阶段 |
| POST /flash?mode=write | 必须带 X-E2631-Confirm: write 与 X-E2631-SHA256（缺失/格式错/不符 => 400，不擦除、/status idle）；校验通过后 200 + result=accepted + sha256=…；随后每个 GET /status 有界推进一个阶段：erase → blank → write → readback → compare → done；终态 result=ok + crc32 + sha256 + sha_match，或 result=error + error |
| 校验器（validate 与写前门禁同一份） | (1) body 长度 == 655,360；(2) image+0x10 u32 LE == 0x73383231（128s）；(3) image+0x14 payload_len，0 < len ≤ 0x9F800 且 0x800+len ≤ 0xA0000；(4) 0x800+len..0xA0000 全 0xFF；(5) payload 内含 ASCII U-Boot 20 |
| X-E2631-SHA256 | 页面/脚本双模式都携带（64 位小写 hex，对整个 655,360 B 文件）；U-Boot 在接收缓冲区后、任何擦除之前校验。write 缺失/格式错/不符必须拒绝（400 + result=error，不擦除）；validate 缺失可继续但只报结构校验结果。0026 构建若尚未带该校验，脚本以 WARNING 记录（见 §1.4），--require-digest 可强制 FAIL；旧 X-File-Sha256 仅在 X-E2631-SHA256 缺失时作兼容回退 |
| 明确没有 | 镜像自带的头 CRC/自摘要/签名（摘要只走 HTTP 头，不写镜像）；没有 /reboot；不自动重启 |

由此推出的可测/不可测边界：

- **可测**：长度、magic、长度窗口、padding、banner 五类结构错误必须被拒；摘要不匹配必须被拒；
  拒绝后 /status 仍 idle，且不出现任何 erase/blank/write 阶段。
- **摘要的边界（必须理解）**：X-E2631-SHA256 绑定「请求头 ↔ 收到字节」，能发现传输损坏/中间篡改；
  但若调用者手里就是一份被改过的文件，页面按该文件算出的摘要与设备摘要仍然一致（sha_match=ok），
  因为两边都对同一份被改文件算。权威性来自调用者钉死的 --expected-sha 与 artifact 来源，不来自设备。
  因此写入只允许用 artifact 来源、本地 sha256 已钉死的零净镜像；任何其它镜像（含矩阵里的 payload-flip）
  只做 validate 探测，绝不写入。若 0026 构建尚未实现摘要校验，脚本以 WARNING/NOTE 记录，
  --require-digest 可把「未强制」升级为 FAIL。

## 5. 验收步骤（S0–S9）

S0（会话前，正常 Linux）：只读确认当前 flash 身份，记录 before 值。

    sha256sum /dev/mtd0                 # 期望 f923904049dd6bc5ed2a8b2598e2cbdf992ab2d7d5dc8c388ab2569237f659f4
    dd if=/dev/mtd0 bs=4096 skip=32 count=160 | sha256sum
                                        # 期望 b1ea9a48…（= 上传文件的 sha256）
    sha256sum /dev/mtd0 > /tmp/e4-before.sha256

两项都要记录。镜像区摘要与本地文件不一致就停，按 Lead 更正：不要从设备重新生成载荷
（那会让写入变成同义反复、证明不了任何东西）；回到 artifact 与设备历史核对，或找 Lead 决策。

S1（host）：核对构建产物与脚本。

    cd /home/qc233/zte/e2631-immortalwrt
    sha256sum tools/e4-rescue-acceptance.sh
    bash tools/embed-failsafe.sh --check         # 期望 raw 9216 B / gzip 4456 B（上限 6144）
    ls -l <0026-artifact>/u-boot.bin <0026-artifact>/artifacts/E2631-FAILSAFE-ASSET.txt

同时核对 0026 u-boot.bin 的 sha256 与产物 UBOOT-INFO.txt/SHA256SUMS 一致；记录该 sha256，
后面的 RAM 链要用它做身份断言。

S2（设备 Linux，暂存 0026 U-Boot，Lead 已钉死路径 b）：

    mtd erase userdata
    mtd write /tmp/e2631-uboot-0026.bin userdata
    # 回读并比较：mtd read userdata /tmp/readback.bin && sha256sum /tmp/e2631-uboot-0026.bin /tmp/readback.bin

userdata 起始物理 offset = 0x3F00000。这是已验证的暂存路径（约 1.2 s 全流程），
只动 userdata，不碰 mtd0。若暂存或回读异常，改用 fallback (a)：串口 xmodem 直接把
0026 u-boot.bin 装到 0x47F00000（约 40 s；defconfig 瘦身后镜像约 320–340 KB）。

S3（设备串口）：重启，flash U-Boot 自动启动窗口内打断，进入其 => 提示符；把暂存的
0026 U-Boot 读入 RAM 的链接地址并校验、跳转：

    mtd read spi-nand0 0x47F00000 0x3F00000 <0026-u-boot.bin 长度>
    crc32 0x47F00000 <长度>          # 与 artifact 的 crc32/sha256 对照；不符立即停止
    go 0x47F00000

说明：0x47F00000 是 flash U-Boot 的链接期副本位置；运行中的 flash U-Boot 已重定位到
约 0x4FF94000，因此覆盖 0x47F00000 安全，这是既有的标准 RAM 链。go 之后运行的是
0026 U-Boot（RAM）。

S3a（硬前置断言，必须通过才可继续）：在新 U-Boot 下确认身份与救援命令：

    version
    help                      # 或直接 e2631rescue（先不执行，检查命令存在）
    # 断言：banner/version 与 0026 产物一致；help 中出现 e2631rescue

若 banner 不是 0026 构建身份，或 help 没有 e2631rescue，**立即停止会话**，不得退回旧 U-Boot
继续，也不得换其它入口绕过。把串口原文交 Lead。

S4（设备串口）：进入救援模式。

    e2631rescue

期望：打印网口状态、设备地址 192.168.1.1、DHCP 池 192.168.1.100+；不自动重启、不初始化无线。

S5（host）：取得救援网 DHCP 地址并跑 **validate-only**（默认，零写入）：

    ip -4 -o addr show | grep 192.168.1.        # 期望 192.168.1.100..200
    tools/e4-rescue-acceptance.sh \
      --image /home/qc233/zte/e2631-t5-artifacts/uboot-du1-44943940449/e2631-uboot-44943940449/e2631-uboot-mtd0.bin \
      --expected-sha b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a \
      --asset-stats <0026-artifact>/artifacts/E2631-FAILSAFE-ASSET.txt | tee /tmp/e4-validate.log

期望：页面 200+gzip、解压页面与本地一致、/status idle、validate result=ok 且
crc32=0x0721e716、设备 sha256=b1ea9a48…、sha_match=ok；拒绝矩阵全部 PASS；摘要探测按 0026
构建是否强制返回 PASS 或 WARNING；汇总 PASS=37（强制摘要；不强制摘要时各项计数略少）
FAIL=0 NOTE=1，退出码 0。**FAIL>0 时禁止进入 S6。**

摘要策略（Lead 决定）：0026 构建一旦带 X-E2631-SHA256 校验，正式验收加 --require-digest
（硬 FAIL）；若当前构建还没有，先不加跑一次拿功能结果，等摘要落地后再重跑摘要探测并记录两次结果。

S6（人工，可并读串口）：观察矩阵阶段设备串口是否只有校验活动、无 erase/write 打印。

S7（host，写入需 P1 批准）：零净写入。

    tools/e4-rescue-acceptance.sh \
      --image /home/qc233/zte/e2631-t5-artifacts/uboot-du1-44943940449/e2631-uboot-44943940449/e2631-uboot-mtd0.bin \
      --expected-sha b1ea9a48f4b9c95f8764fcb0ffc5b088cd25c7064d27cb78321ffd3344bdf63a \
      --asset-stats <0026-artifact>/artifacts/E2631-FAILSAFE-ASSET.txt \
      --write --approval E4-RESCUE-WRITE-APPROVED [--require-digest] | tee /tmp/e4-write.log

期望：写前再次核对 sha256 与 /status idle；POST 返回 result=accepted + sha256=b1ea9a48…；
轮询依次看到 erase/blank/write/readback/compare/done；终态 result=ok、crc32=0x0721e716，
且 sha256=b1ea9a48…、sha_match=ok；汇总 PASS=50 FAIL=0 NOTE=1（强制摘要；未强制时计数
略少、带 WARNING），退出码 0。
脚本不发送 /reboot，成功文案明确要求断电重启。

S8（人工）：**不要执行 reset**（占位实现）。断电重启（拔电再上电），确认正常启动日志。
flash 内容应与 S0 相同；U-Boot 从 flash 启动，0026 U-Boot 只存在于刚才的 RAM 链中。

S9（设备，正常 Linux）：写后核对。

    sha256sum /dev/mtd0                                  # 期望仍为 f9239040…
    dd if=/dev/mtd0 bs=4096 skip=32 count=160 | sha256sum # 期望仍为 b1ea9a48…
    # 与 /tmp/e4-before.sha256 对比

把 /tmp/e4-validate.log、/tmp/e4-write.log、串口日志、S0/S9 记录交给 Lead。
## 6. 拒绝矩阵（脚本自动执行）

| 用例 | 构造 | 期望设备行为 | 依据 |
|---|---|---|---|
| size-1 | 截断 1 B（655,359） | HTTP 400 + result=error + error；/status idle；无写阶段 | 长度检查 |
| size+1 | 追加 1 个 0x00（655,361） | 同上；若无 HTTP 响应（服务器提前拒收导致 curl 中断），以 idle + 重新校验好镜像通过为佐证 | 长度检查 |
| bad-magic | image+0x10 异或 0xFF | HTTP 400 + error；idle | magic 检查 |
| length-out-of-window | image+0x14 写 0x9F801 | HTTP 400 + error；idle | 长度窗口 |
| non-FF-padding | 在 payload 末尾之后（0x800+len+0x10）写 0x00 | HTTP 400 + error；idle | padding 检查 |
| banner-missing | payload 内 U-Boot 20 的首字母改成 X | HTTP 400 + error；idle | banner 检查 |
| digest-mismatch | 好 body + X-E2631-SHA256 全 0 | 400 + result=error（强制摘要构建）；未实现时脚本 WARNING/NOTE，--require-digest 时 FAIL | X-E2631-SHA256 |
| payload-flip | payload 中间单字节翻转，摘要按改后文件计算 | validate 预期接受（摘要绑定的是上传 body，不是权威镜像）：记 NOTE，仅 validate，绝不写入 | §4 摘要边界 |

矩阵每一例之后脚本都检查 /status 为 idle 且没有出现 erase/blank/write 等写阶段；任何一例出现
200/ok（除按契约允许的 payload-flip）、进入写阶段或 /status 非 idle，均记 FAIL。

## 7. 脚本用法、参数与安全联锁

    tools/e4-rescue-acceptance.sh --image <file> [options]

| 参数 | 含义 |
|---|---|
| --image PATH | 必须：零净 mtd0 镜像区文件（默认要求 sha256 = b1ea9a48…，否则 FAIL，不写） |
| --expected-sha SHA | 覆盖期望 sha256；正式验收传入 S0 在目标机测得的镜像区摘要 |
| --host IP[:PORT] | 设备地址/端口，默认 192.168.1.1 |
| --iface IFACE | 指定救援网卡；不指定则自动找 192.168.1.0/24 地址 |
| --dhcp | 无地址时以 root 执行 dhclient -1（缺 --iface 或非 root 直接报错） |
| --page PATH | 本地页面基准（默认套件内页面；构建 commit 不同时必须显式指定） |
| --asset-stats PATH | 构建产物 E2631-FAILSAFE-ASSET.txt；用来核对板端 gzip sha256 |
| --write | 开启零净写入阶段；必须同时给 --approval |
| --approval TOKEN | 必须精确等于 E4-RESCUE-WRITE-APPROVED；否则退出码 3 |
| --skip-matrix | 跳过拒绝矩阵（不建议用于正式验收） |
| --require-digest | 若设备未强制 X-E2631-SHA256，直接 FAIL（0026 带摘要后的正式模式） |
| --timeout SECS | 写入轮询超时，默认 600 s |
| --keep-tmp | 保留临时文件（排查用） |

退出码：0 = 断言全过；1 = 验收失败（含任一 FAIL）；2 = 前置/环境错误（设备不在救援模式、
镜像/页面/网络/产物不满足）；3 = 写入批准缺失。

安全联锁：
- 默认 validate-only；写入需要 --write + 批准 token 双条件；
- 写入 POST 前再次核对镜像 sha256 与 /status idle；
- 只写零净镜像；矩阵生成的坏镜像只走 validate；
- 每 POST 带 X-E2631-SHA256；摘要不符探测失败按 §1.4 处理；
- 不调用 /reboot、不发 reset、不自动断电；成功/失败都停在救援模式，由人工决定下一步；
- 失败即停止，不自动重试整个写流程（重试需人工确认，见 §8）。

## 8. 失败判据与处置

| 现象 | 判据 | 处置 |
|---|---|---|
| 设备不在救援模式 / GET / 非 200 | 前置失败（退出码 2） | 检查 P4/P5/P6；不要盲目写 |
| S3a 没有 e2631rescue / banner 不符 | 会话前置失败 | 立即停止，交 Lead；不得退回旧 U-Boot 继续 |
| 页面解压后与本地不同 | FAIL | 用 --page 钉住构建 commit 的页面；否则停止 |
| validate 非 ok / crc32 不符 | FAIL | 停止，不进入写；查串口与产物 |
| 矩阵某例未被拒（非 payload-flip） | FAIL | 停止；0026 校验器有缺陷，记录串口并交 Lead |
| 摘要探测未强制（无 --require-digest） | WARNING + NOTE | 记录为已知 gap；摘要落地后重跑；不许静默跳过 |
| 摘要探测未强制且带 --require-digest | FAIL | 停止；等 0026 摘要校验落地 |
| 写前 /status 非 idle | FAIL | 停止；设备状态不干净，断电重启后重做 |
| POST 非 accepted | FAIL | 停止；不重试、不手工补写 |
| 轮询出现 error 或超时 | FAIL | 停止；保留串口与 /status 原文；是否重试由 Lead 决定 |
| 五阶段缺任一 | FAIL | 停止；写通道不完整 |
| 终态 crc32 不符 | FAIL | 停止；不得断电前再写 |
| 写后 /dev/mtd0 sha 变化 | RED | 不重复上电；按救砖手册 §6.6/§6.7 评估，必要时编程器 |

## 9. 回滚与风险

- validate-only 阶段零写入：矩阵与 dry-run 都只走校验路径；/status 不进入写阶段，flash 不变。
- 写入阶段是零净写：成功时字节与原来相同，理论上无需回滚；验收后 /dev/mtd0 完整 sha256
  必须仍为 f9239040…、镜像区 sha256 必须仍为 b1ea9a48…。
- 掉电风险仍在：擦除/写入窗口内断电会使 mtd0 的 U-Boot 区无效；secondboot（0x0..0x1FFFF）
  与 env（0xC0000+）不受影响，但 secondboot 找不到可启动 U-Boot 时没有串口/网络入口，
  只剩 SPI-NAND 编程器（见救砖手册 §6.6/§6.7）。这是本方案无法消除的残余风险，写入前必须
  确认 P1 批准与 P7 串口记录；不要在供电不稳时执行。
- 不依赖 reset：reset_cpu 仍是占位；验收全程以「人工断电重启」结束，页面文案也已同步修正
  （task-73 跟修：success 文案改为断电重启，并说明 reset 后续由 task-76 修复）。
- 不做的事：不自动重启、不自动改写 env、不写 secondboot/env 区、不跨分区写、不在失败后自动
  重试刷写、不把矩阵坏镜像写入、不把「从设备重新生成的载荷」当零净证据。

## 10. 证据采集清单（verify-docs 执行时保存）

- 串口全程日志（含 S2 暂存回读、S3 mtd read/crc32/go、S3a version/help、S4 e2631rescue、
  S7 五步打印、S8 重启日志）；
- /tmp/e4-validate.log、/tmp/e4-write.log（脚本 stdout+stderr，含 PASS/FAIL/WARNING 汇总）；
- S0/S9 的完整 /dev/mtd0 sha256 与镜像区 dd+sha256sum 输出，before 值文件；
- 0026 构建产物 UBOOT-INFO.txt、SHA256SUMS、E2631-FAILSAFE-ASSET.txt、e2631_failsafe_asset.c/.h，
  以及 0026 u-boot.bin 的 sha256（S3 身份断言依据）；
- 可选：tcpdump（host）抓 HTTP 请求/响应摘要，证明 mode=validate 未触发写、write 只发一次；
- 终端信息：设备型号、构建 run id、套件 commit、脚本 sha256（执行前实测并记录）。

## 11. 交接给 verify-docs（设备会话执行清单）

1. 读 §2 前置条件，逐项打勾；S0 的完整 mtd0 sha256 与镜像区 sha256 必须记录。
2. 按 S2–S3 完成 userdata 暂存与 RAM 链（fallback 为串口 xmodem）；S3a 的 banner/命令断言
   必须通过，否则立刻停。
3. S4–S5 进救援模式并跑 validate-only；期望 PASS=37、FAIL=0、NOTE=1（不强制摘要时计数略少）；
   否则停。
4. 把结果与串口片段发给 Lead，取得「可以写 mtd0」的明确批准后，S7 加 --write/--approval
   （若 0026 已带摘要校验，再加 --require-digest）执行。
5. S8 断电重启；S9 写后完整 mtd0 sha256 与镜像区 sha256 必须等于 before；把 §10 证据路径回报 Lead。
6. 若任何一步失败：停止，保留现场与日志，不要自行重刷/重试；Phase 2（真实刷入 0026 U-Boot）
   另行批准，不在本会话内做。

## 12. 未决问题与已知限制

- **Q1（已由 Lead 钉死）**：Phase 1 = flash U-Boot 环境下把 0026 U-Boot 装入 RAM
  （首选 userdata 暂存 + mtd read；fallback 串口 xmodem），go 后运行 0026 U-Boot 再 e2631rescue。
  S3a 硬断言 e2631rescue 存在；不存在就停止，不得退回旧 U-Boot。
- **Q2**：设备侧摘要已按 Lead/base-builder 新契约（m04264）实现为 0026 的一部分；正式验收带
  --require-digest。注意摘要语义是「传输完整」，不是「镜像权威」；权威仍由调用者 --expected-sha
  钉死（见 §4 末）。若设备用错摘要仍放行，--require-digest 会 FAIL；若要求设备自己判断镜像是否
  为目标版本，需要在设备里内置期望摘要或打包格式 v2，那是单独决策，且会破坏现有镜像字节一致性。
- **Q3**：reset 命令不可用（patch 0003 占位），task-76 修复前所有验收以断电重启收尾。
- **Q4**：页面按构建 commit 变化；脚本默认与本地页面比对，跨 commit 验收时必须用 --page/--asset-stats
  钉住，否则会误 FAIL。
- **Q5**：size+1 等「提前拒收」可能导致 curl 连接中断（HTTP 码抓不到），脚本以 /status idle +
  好镜像重新 validate 成功作为佐证；若 Lead 要求严格 HTTP 400，需要设备侧先读完 body 再拒绝，
  这属于 0026 实现细节，可在验收前与 base-builder 对齐。
- **Q6**：host DHCP 自动化受权限限制（dhclient 需 root）；脚本默认只检查地址并提示手工取址。
- **Q7**：Phase 2（把 0026 U-Boot 真正写入 mtd0）是非零净升级，需单独的用户批准与自己的
  回滚/掉电预案；本方案只覆盖 Phase 1 的零净验收。

## 13. 自测与复现

- 设备不可用期间，用 /tmp 下的 mock HTTP 服务实现 §4 同一份契约（GET / gzip、GET /status、
  POST validate/write 五阶段、X-E2631-SHA256 强制/不强制两种模式），对本脚本做端到端自测：
  强制摘要：validate-only 37 PASS / 0 FAIL / 1 NOTE；--write 50 PASS / 0 FAIL / 1 NOTE；
  不强制摘要（模拟旧构建）：默认 PASS + WARNING + NOTE；加 --require-digest 则 FAIL、退出码 1。
  mock 不写入本仓库（仅临时文件），不作为真机验收证据。
- 页面基线（本文件写作时）：uboot-port/failsafe/e2631-failsafe.html raw 9,216 B，
  gzip 4,456 B（上限 6,144 B），sha256 30a8f03e46867bb066947a2537f738e0539fd214ae579a287c301d5ff9e39bda，
  gzip sha256 8f16817b30d66197364cf5a67d9cf5ddd2720a7a09975e8d01dd2494d78616d3；
  tools/e4-rescue-acceptance.sh sha256 4b514f9b4e67283a7c7ee366532704fe87068fa655cc16a6b64b3844b46a2e54
  （执行前请再实测并记录；本文件随提交记录）。
- 本文件不含任何设备操作结论；真机结果由 verify-docs 在设备会话中按 §5/§10 记录。
