# Q-收1 收口:batch-2 真机刷写与复验(2026-11-15)

状态:刷写与七项复验完成;新镜像冷启动采样(≥3 次)待用户拔插头,完成后补第 6 节。

## 1. 批准与来源

- 用户批准:ask_user_question task21b-flash =「批准刷写 (Recommended)」(2026-11-15 08:16)。
- 产物:RUN3 43623162108 @ iwrt-adaptation 检出 8d87bfa,树 fork e2631 @
  cd14ffa091f63116859ae8bd6d262f08778629a8;e2631-immortalwrt-experimental.bin
  22,020,628 B,sha256
  3d7825c9fdb9a15992ab72393014ce6c13211d76757f162bbe8b3b8cf8dbb13d
  (宿主与设备双侧校验一致;parity 结论 PASS-REVIEWED-DIFFS 见
  t20b-repin-batch2-20261115.md §6)。

## 2. 刷写执行

- cat-over-ssh 上传 /tmp/e2631-immortalwrt-experimental.bin,1.76 s,设备端
  sha256 与宿主一致。
- e2631-upgrade apply:package ok → flashing the running slot in place →
  ok: running slot 1 with an intact vendor fallback in slot 0 → 自动重启。
  尾部 "ubus call system sysupgrade (Connection failed)" / "sysupgrade
  failed" 与 01:21 首次刷写同款 = stage2 关闭会话的误报,实际刷写成功
  (与 r0-83df1a9 批次行为一致,两次独立观察)。
- 刷后槽状态:slot 1 serial 10→11 version="ImmortalWrt v1.10.0" [running]
  [next boot];slot 0 = 原厂 V1.0.0.7B5.8000 serial 7,未动。
- 身份:/etc/e2631-version=ImmortalWrt v1.10.0;DISTRIB_REVISION=r0-cd14ffa;
  主机侧 host key 更新(新 dropbear 钥,预期)。

## 3. 密码重设(刷写清空 shadow)

- 本机生成 sha256crypt(`openssl passwd -5`),经 stdin 写入设备
  /etc/shadow(禁双引号命令行教训沿用);空密码 = Permission denied,
  真密码 = LOGIN-OK uid=0 双验证通过;二启后密码保持。
- 配置:uci e2631.storage.autoadopt=0 + fstab.e2631_extroot.enabled=0 已提交
  (沿用"extroot 保持关闭"的用户决策)。

## 4. marker 修复真机实锤(4b610dc)

- 首启现场:userdata 卷仍为旧时代坏标记(卷树时间戳 Nov 14 19:48,设备时钟
  未同步期),即 1 字节换行标记场景的存量卷。
- 新 gate 首启输出(serial log):
  `e2631-userdata: refusing the userdata extroot: the formatted volume has no
  snapshot marker (it was provisioned by an older image)`
  `e2631-userdata: stayed on the internal overlay; the volume was not modified`
  `e2631-userdata: extroot kept off in fstab; this boot runs on the internal
  overlay`
  → 拒绝收养、未改卷、内部 overlay 保持;二启(软件重启)幂等重复同一组输出。
- 判定:4b610dc 的"坏/过期标记拒绝接管"分支在真实首启条件上按设计工作。

## 5. 七项复验(e2631-device-check.sh,全部通过)

| # | 项 | 结果 |
|---|---|---|
| 1 | DEVMEM/fwstate | /dev/mem 存在;e2631-fwstate 200 采样 FW_STATE=0 ✓ |
| 2 | overlay | /overlay=jffs2 mtdblock8;gate 拒绝旧卷 ✓ |
| 3 | jffs2 噪音 | dmesg 'failed to sync jffs2 overlay' 计数 = 0 ✓ |
| 4 | WAN 放行 | 无 Allow-SSH/HTTP/HTTPS-WAN 规则 ✓ |
| 5 | hostname | uci = ImmortalWrt(rootfs_data 完好);注:busybox hostname
  applet 不在(与 batch-2 无关,无功能影响,记档) |
| 6 | 双频 SSID | 2.4G ch1 HE40 + 5G ch36 HE80,均 "E2631" ✓ |
| 7 | 启动签名 | 首启 MT7916 ready 80.7s / 二启 54.7s ✓ |

## 6. 冷启动采样(待补)

- 待用户拔插头 3 次;bootwatch 处理 serial log 后填入会话号、ready 时间、
  结论与累计统计(现役镜像 r0-cd14ffa n/3;历史 v1.10.0 11/11、
  r0-83df1a9 3/3)。

## 6. 冷启动采样(批3,已补)

用户 m06252 '完成' = 3 次拔插头完毕。bootwatch 处理 serial log
(offset 633638, session 21):

| 会话 | 上电 (CST) | MT7916 ready | wifi done |
|---|---|---|---|
| S19 | 08:26:55 | 53.431 s | 53.696 s |
| S20 | 08:31:16 | 53.511 s | 53.746 s |
| S21 | 08:32:48 | 53.899 s | 54.128 s |

- 断电签名核验:serial log 中三次 'Boot SPI NAND' (行 8998/9460/9922) 之间
  均无 'reboot: Restarting system' → 真断电冷启动,非软件重启。
- 结果:3/3 SUCCESS,0 失败签名。
- 累计 (三镜像):v1.10.0 11/11 + r0-83df1a9 3/3 + r0-cd14ffa 3/3 = 17/17;
  批3 均值 53.61 ± 0.25 s;17/17 下失败率 95% 置信上界 ≈ 16%
  (成功概率下界 ≥ 84%)。与 r0-83df1a9 批2 一致,无回归。

## 7. 结论

batch-2 (marker 硬化 + SPDX×5 + fwslot 字符串重构 + DEVMEM 等前序修复)
的树 fork 重钉 → RUN3 构建 → parity PASS-REVIEWED-DIFFS → 真机刷写 →
七项复验 → 冷启动 3/3 全链闭合。marker 修复在真实首启条件下实测拒绝
坏标记卷。task-21 验收完成。
