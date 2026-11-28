# t92d `/env` 写事故：根因与修复（task-98，patches 0060/0061）

日期：2026-11-28　作者：base-builder　状态：代码已提交；构建与真机复测待 task-92 / verify-docs 执行

## 0. 结论

- t92d 零写门禁里，`POST /env?key=bootdelay&value=3&confirm=write`（no-change）第一次返回
  `200 result=ok keys=0`，第二次相同请求却返回 `200 result=accepted keys=1`，把 `e2631_flashboot`
  从 `reset` 改成 `failsafe.lan` 并写了 env 块（CRC `0xf95a816e` → `0xa4f2c14c`）。
- 两层缺陷叠加：**(A)** 0058 的对齐记录把键名存成指向第一次导出缓冲的指针，第二次导出覆盖该缓冲后，
  restore 用野键名调用 `env_set()`（串口的 `illegal character =` / `Baudrate 0` / `Error inserting baudrate`
  就是这些失败输出），RAM 环境被写坏；**(B)** 候选块在写出前被原地解析，`=` 被改成 NUL，写出的块是
  `key\0value` 形式（t92d 现场 `env-block-current.bin`：存储 CRC `0xa4f2c14c`，按数据重算 `0xd8e96dc7`，
  52 个条目全部被拆开），下次开机必然 bad CRC。
- 修复：0060 让 `/env` 候选块只由 flash 基线块 + 请求的单个键生成（`e2631env_build.h` 纯构造器，
  不再改 RAM env、不再解析待写缓冲）；0061 让对齐记录持有键名副本，并在 CLI 保存前把候选块还原成
  `key=value`。61 patches / post-am tree `88ecf6d6b8bbe3a5a14ccb73455c20c757ac6ebf`。

## 1. 现场证据（t92d，2026-11-28）

| 项 | 值 |
| --- | --- |
| 构建 | task-92 第四次统一构建 run `46132729322`，banner `U-Boot 2027.01-rc2-g942c3c38b2d5` |
| u-boot.bin | 417,024 B sha256 `6a352b6f99050ce7672ad88103acc3835aa492db0b9c01a04a56b5bccda25a74` crc32 `184afaa4` |
| mtd0 image | sha256 `2f0aedbd9824e7acba3228652499f816a189a733f042e4773c7975fc3fc7e385` |
| 第一次 no-change | `200 result=ok keys=0` |
| 第二次 no-change | `200 result=accepted keys=1`，`e2631_flashboot: reset -> failsafe.lan` |
| 写入的 env 块 | `0xc0000..0xdffff`，CRC `0xf95a816e` → `0xa4f2c14c` |
| 串口异常 | `## Error: illegal character '=' in variable name ...`、`## Baudrate 0 bps not supported`、`## Error inserting "baudrate" variable, errno=22` |
| 现场 env 块分析 | 存储 CRC `0xa4f2c14c`，数据重算 `0xd8e96dc7`；52 个条目全部是 key 与 value 分开的 NUL 串 |

证据目录：`/home/qc233/zte/e2631-p3/e2/e4-v3-phasea/t92d-run-1/`（串口日志、`env-block-current.bin`、probe.json）。

## 2. 根因 A：对齐记录的键名变成野指针

0058 的 `e2631_env_align_with_baseline()`（`board/zte/zxhn-e2631/e2631env.c`）在第一次
`env_export(cand)` + `e2631_env_parse()` 之后，把需要对齐的键记录为：

- `tweaks[*ntweak].key = key;`，其中 `key` 指向 `cand` 缓冲里 probe 条目的键名字符串；
- `saved` 保存 `env_get(key)` 的值副本（malloc）。

`e2631_env_build_candidate()` 接着对同一个 `cand` 做 `memset(cand, 0)` 和第二次 `env_export(cand)`，
这些指针随即失效。恢复阶段 `e2631_env_restore_tweaks()` 用失效键名调用 `env_set()`：

- `env_set` 对名字含 `=` 的键返回失败并打印 `illegal character '=' in variable name`；
- 名字以数字开头或为空的键触发 `Error inserting ... errno=22`；
- 恢复走错位置时，`e2631_flashboot` 被写入 `failsafe.lan`（`failsafe.lan` 来自 DNS 模块的种子值
  `env_set(dnsd_domain, failsafe.lan)`），这是第二次 no-change 出现 `keys=1` 的来源。

这是纯顺序性缺陷，不依赖浏览器输入、网络时序或并发。

## 3. 根因 B：候选块在写出前被拆开

`e2631_env_parse()` 为了读取旧块键值，会就地把 `key=value` 中的 `=` 改成 NUL。CLI 的
`do_e2631env_save()` 保留了这个被解析过的 `cand` 并直接交给五步写，于是写出的块是
`key\0value\0key\0value...`，CRC 与存储值不符。`/env` 的 staged writer 也有同样风险。
0058 的版本没有触发这一条只因为 no-change 路径先被 A 挡住了。

## 4. 修复 0060：候选块只由基线与请求键生成

新增 `board/zte/zxhn-e2631/e2631env_build.h`（独立头，不依赖 U-Boot，主机可测）：

- `e2631_env_build_parse()`：非破坏解析，遇到首个 `0x00` 结束，格式错误返回 -1；
- `e2631_env_build_single()`：把 `dest` 清零，`base_valid` 时按原序原字节复制基线全部条目，
  只替换或追加请求的那一个键，序列化为 `key=value`，再按传入的 crc 函数重算头部 CRC；
  越界、超长键/值、畸形基线返回 -1。

`e2631_env_write_begin()` 随之重写：

- 不再在写前 `env_set(key, value)`（请求值只进入候选块）；
- 读 flash 旧块并校验 CRC（非空坏块仍拒绝重建）；空白块只写请求键；
- 候选块由旧块 + 请求键构造，`keys=0` 判定直接来自旧值与请求值的比较；
- 变更数为 1 时只记录请求键；写成功、VERIFY 通过后才把请求键写回 RAM env。

## 5. 修复 0061：对齐记录持有键名副本，CLI 保存前还原 `key=value`

新增 `board/zte/zxhn-e2631/e2631env_tweak.h`：

- `struct e2631_env_tweak { char key[32]; char *saved; bool existed; }`；
- `e2631_env_tweak_save()` 用 `strcpy` 复制键名（表满/键过长 -ENOSPC，malloc 失败 -ENOMEM）；
- `e2631_env_tweak_restore()` 只用副本调用 set 回调，随后 free 并清空。

`e2631env.c` 删除旧的指针版 tweak 结构，对齐/恢复改走上面两个函数；新增
`e2631_env_join_block()`，CLI `e2631env save` 在写块前把解析后的条目重新拼成 `key=value`。

## 6. 主机 fixture

| fixture | 项数 | 覆盖 |
| --- | --- | --- |
| `uboot-port/tests/env_candidate_test.c` | 65 | 两次 no-change 字节完全一致；运行时键（dnsd_domain/fdtcontroladdr/serial stdio）不进入候选；只改请求键时其余 key/value 逐项相同；新键追加末尾；空白块只含请求键；畸形/超长/过小拒绝 |
| `uboot-port/tests/env_tweak_test.c` | 27 | 旧事故复现：save 后 memset 掉源缓冲，restore 仍恢复原值且没有畸形键；完整 gate 对齐序列（DNS+telnet+console 之后）restore 后 runtime 键全部还原；不存在的键 restore 后删除；超长键/表满被拒 |

CI 在 `uboot-build.yml` 里编译并运行这两个 fixture，期望 `env candidate fixture: PASS (65 checks)`、
`env tweak fixture: PASS (27 checks)`，随后 task-98 门禁检查构造器/键名副本存在、
禁止 `env_set(key, value);` 与 `tweaks[*ntweak].key = key;` 回归。

## 7. 本地静态验证

- `host gcc -fsyntax-only`：`e2631env.c` 通过；两个新头文件被 fixture 独立编译通过；
- `checkpatch --ignore FILE_PATH_CHANGES,CMD_TEST,LIVETREE,PREFER_IF`：0060/0061 各 0 errors / 0 warnings / 0 checks；
- 干净 clone `u-boot` `c1958b5f6cce03956d309ce422b5d9f819955d4a` + `git am` 61 patches → 61 commits，
  tree `88ecf6d6b8bbe3a5a14ccb73455c20c757ac6ebf` 与 pin 一致；
- kit `make check` 全 PASS/SKIP、`node tools/check-workflows.mjs` OK。

## 8. t92d 复测期望（零写；verify-docs 执行，需 Lead 排期）

1. 前置：把 env 块恢复到基线 `6e2c01da…`（131072 B，`evidence/b1-env-session/resume-1/target-mtd0.bin`
   的 `0xC0000..0xE0000`），或先走一次厂商链自愈；该恢复是 flash 写，需用户/Lead 批准。
2. 进入救援后先跑 DNS 查询、telnet 一条命令、web console 一条命令（重放污染前置条件）。
3. 连续两次 `POST /env?key=bootdelay&value=3&confirm=write`：都必须 `200 result=ok keys=0`，
   串口无 `erasing`/`writing env block` 行，`/status` 的 `crc32` 保持 `0xf95a816e`。
4. `GET /env` 仍是 26 个键，`e2631_flashboot=reset` 不变；`GET /backup?part=bootloader` 之外的四个小分区
   sha 与基线一致。
5. 任何一次 `keys=1`、env CRC 变化或串口 `illegal character` 即 RED。

## 9. 边界与风险

- 本次不重写已发布的 0058（它已存在于 task-92 artifact 中），只在其后追加 0060/0061；
- `/env` 路径不再使用 0058 的对齐逻辑；CLI `diff/save` 仍用它，但键名已改为副本且保存前 join；
- DNS 模块的 `env_set(dnsd_domain, failsafe.lan)` 保留（不再进入持久化路径，RAM 副作用无害），
  文档记录为已知行为；
- 构建由 task-92 统一执行；本轮未 dispatch、无设备/flash 动作。

## 10. 参考

- `evidence/e4-v3-phasea-t92c/serial-env-excerpt.txt`（t92c 串口摘录）
- `/home/qc233/zte/e2631-p3/e2/e4-v3-phasea/t92d-run-1/`
- `uboot-port/README.md` §4 item 37/38、§5 E4 v3.1 小节、§8 changelog
- Lead task-98 要求：`m11664` / `m11683`
