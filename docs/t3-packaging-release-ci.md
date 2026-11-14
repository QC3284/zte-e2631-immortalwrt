# T3：打包 / 发布 / 在线更新 / CI 的 ImmortalWrt 适配（2026-11-14）

本文件记录 task-3 的口径与证据：换基底、换仓库名之后，「打包 → 发布 → 在线更新 → CI」
这条链怎样保持自洽，以及哪些结论只有 CI / 真机才能证明。

> **历史记录说明（T-12 后记）**：本文记录 T3 当时的实施状态。T-12 树 fork 迁移后，
> `overlay/`、`base/`、`apply.sh` 与 `E2631_BASE_KIND` 已删除，设备支持改为
> QC3284/immortalwrt `e2631` 分支的真实提交；当前构建与门禁见 `BUILD.md` 与
> [immortalwrt-migration.md §6.4](immortalwrt-migration.md)。本文的产物名、版本口径、
> 在线更新链与 CI 发布闸门结论仍然有效。

## 1. 本轮改动的提交

| 提交 | 内容 |
|---|---|
| `819af6c` | 删除 overlay 自带的 `luci-theme-argon`（107 文件）与 `luci-app-homeproxy`（43 文件），同名的两个包改由 ImmortalWrt luci feed 提供（T1 结论，用户 2026-11-14 拍板）。 |
| `5a8ad23` | 品牌/版本/产物名/更新通道/CI 全链适配（下文逐项）。 |
| 本文件所在提交 | `docs/t3-packaging-release-ci.md`、firmware.yml 的 `publish` 开关、make_fixture 品牌串。 |

## 2. 产物名与版本口径

统一为 `e2631-immortalwrt-*.bin`，出现位置：

| 位置 | 值 |
|---|---|
| `scripts/build.sh`（第 73、93 行提示/输出） | `e2631-immortalwrt-$STAMP.bin` |
| `host/release.mjs` 默认 `--out` | `out/e2631-immortalwrt-factory.bin` |
| `host/stage.mjs` 默认 `--pkg` | `out/e2631-immortalwrt-factory.bin` |
| `host/publish.mjs` 示例 / 默认标题 | `out/e2631-immortalwrt-v1.0.bin` / `E2631 ImmortalWrt <tag>` |
| `.github/workflows/firmware.yml` | 收集 `e2631-immortalwrt-*.bin`，发布资产名 `e2631-immortalwrt-experimental.bin` |
| 在线更新 | 取 latest release 里第一个 `*.bin` 资产，不写死文件名 |

版本字符串（用户 2026-11-14 决定，品牌定稿）：

* `/etc/e2631-version` = `ImmortalWrt v1.10.0`；
* CI `E2631_VERSION` = 同一个字符串（firmware.yml `env:`）；
* `tools/check-workflows.mjs` 静态断言两者一致，防止再漂移。

### 与厂商网页升级页的关系（保留风险，需用户知悉）

原厂 `supgrade.html` 只接受 `V1.0.0.xBx.xxxx` 形状的版本号，`ImmortalWrt v1.10.0`
**不是**这种形状：

* `host/release.mjs` 会打印警告（原有行为，现改文案指向本套件流程）；
* 首次写入只能用 fwslot 流程（`e2631-fwslot install`），之后可用 `e2631-upgrade` 在线更新；
* 若要在原厂页做首次刷写，可临时 `unset E2631_VERSION` 用模板的厂商字符串打包
  （`host/release.mjs` 警告里已写明）。

## 3. 在线更新（`.../sbin/e2631-upgrade`）

改动后仍然**不写非运行槽**：`do_apply` 只调 `/sbin/sysupgrade`，由 platform.sh 走
`fwslot upgrade-check` + `fwslot upgrade` 原地重写运行槽（`docs/updates.md` 的不变量未动）。

本轮适配的点：

1. 默认发布通道改为 `QC3284/zte-e2631-immortalwrt`；`uci e2631.upd.repository` 覆盖仍然有效
   （zwthys-cyber 加固语义保留）。
2. 版本比较保留「先剥标签再逐段数字比较」：`OpenWrt v1.9.0 → ImmortalWrt v1.10.0`
   的过渡升级不需要特殊处理（host 模拟已覆盖，见第 5 节）。
3. 清单强制且严格：`SHA256SUMS` 缺失 / 重复 / 格式错 / 哈希不符一律拒绝，失败前不写
   `/etc/.e2631-pending-version`，也到不了 `sysupgrade`。
4. 镜像白名单只接受 https；**修掉一个真实漏洞**：`deref()` 原来用 `printf '%s%s'
   "$(mirror)" "$1"`，命令替换里 `mirror()` 的 `die` 被 printf 吞掉，配置成 `http://`
   镜像时会被静默忽略并从 github.com 直连下载。现在 `deref()` 把 `mirror()` 的失败
   向上传递，`do_download` 在下载前中止并报 `mirror must use HTTPS, not <value>`。
   （`docs/updates.md` 原本就写「镜像加速前缀只接受 https」，此次让代码与文档一致。）
5. LuCI 刷机/升级页（`luci-app-e2631` 的 `e2631flash.js`）用户可见文案由「OpenWrt 槽位」
   改为「ImmortalWrt 槽位」。

## 4. CI（`.github/workflows/`）

### `firmware.yml`（手动 dispatch，默认不发布）

* `workflow_dispatch` 新增布尔输入 `publish`，**默认 false**；为 false 时跳过
  `gh release create`，但构建日志与 `release/` 产物仍用 upload-artifact 保留
  （测试性 `make world` 不再产生 Release）。官方 Release 仍需用户批准。
* env 显式 `E2631_BASE_KIND: immortalwrt`（T-12 起该开关已删除；本节记录 T3 当时的状态，
  当时 firmware 构建必须显式选新基底）、`E2631_VERSION: ImmortalWrt v1.10.0`。
* 发布前 `source scripts/env.sh`，`SOURCE-INFO.txt` 记录构建**实际断言**的钉值而不是本地
  `git HEAD`（git-am 提交的 SHA 是机器本地的）：Kit commit、Base kind、ImmortalWrt repo/branch/SHA、
  ImmortalWrt 原始 tree hash、4 个 port patch 的 sha256、打完补丁后的 base tree hash、kernel 版本、
  packages/luci feed 的 **remote URL + commit**（证明用的是 immortalwrt feeds）、Run、`Hardware tested: NO`。
* 权限最小：顶层 `contents: read`，仅 build job `contents: write`；产物 `SHA256SUMS` 覆盖
  `.bin` 与 `SOURCE-INFO.txt`；prerelease + 中文风险文案；tag `e2631-exp-<run>-<sha7>`。

### `check.yml`（push / PR / dispatch）

在 `make check` 之前新增两步（都不依赖 apt 安装）：

```
node host/sim-upgrade.mjs      # 在线更新端到端模拟（第 5 节）
node tools/check-workflows.mjs # 产物名/版本/SOURCE-INFO/权限/通道静态一致性
```

## 5. host 侧证据（可复跑）

### 5.1 在线更新模拟：`host/sim-upgrade.mjs`

做法：读出**真实**的 `e2631-upgrade` 文本，把所有绝对路径（`PATH`、`/tmp/e2631-upgrade`、
`/etc/e2631-version`、`/etc/.e2631-pending-version`、`/usr/sbin/e2631-fwslot`、`/sbin/sysupgrade`）
重定向进临时沙箱；`uci`/`wget`/`e2631-fwslot`/`sysupgrade` 全是桩（sysupgrade 只记录 argv，
**不写 flash**）；假 release 由本地 `latest.json` + `asset.bin` + `SHA256SUMS` 提供。

```
$ node host/sim-upgrade.mjs
sim-upgrade: OK - updater behaviour matches the T3 assumptions   # 30 PASS / 0 FAIL
```

覆盖：`OpenWrt v1.9.0` 运行中看到并安装 `v1.10.0`（恰好一次 sysupgrade、pending 标记、
资产 + SHA256SUMS 都取到）；同版本 up to date；降级被拒（`not newer`，`E2631_UPGRADE_FORCE=1`
才放行）；坏哈希 / 缺清单 / 重复条目被拒且不写 pending、不到 sysupgrade；http 镜像被拒；
https 镜像只给 `https://github.com/...` 加前缀、不动 `api.github.com`；`check <file>` / `apply <file>`；
`uci e2631.upd.repository` 覆盖。

### 5.2 CI 静态一致性：`tools/check-workflows.mjs`

```
$ node tools/check-workflows.mjs
check-workflows: OK - CI, artifact names, version and release channel agree   # 39 PASS / 0 FAIL
```

断言：镜像版本串 = CI `E2631_VERSION`；`E2631_BASE_KIND=immortalwrt`；产物前缀在各处一致；
没有残留 `e2631-openwrt-*` 产物名；更新通道为新仓库且 CI 不含旧 slug；SOURCE-INFO 各字段齐全；
顶层只读 + build job 写权限；Node 固定 22.16.0；dispatch-only；`publish` 开关存在且默认 false；
发布步骤在建/校验步骤之后；只出 prerelease；check.yml 跑模拟与静态检查。

### 5.3 几何常量

`KERNEL_AT=0x400000` / `ROOTFS_SPAN=0x1100000` / `HEADER_AT=0x1500000` 现在在 5 份副本里一致：
板级 DTS、`tools/verify_img.mjs`、`host/release.mjs`、`image/Makefile.e2631` 的打包参数、
两份 preflight（host 由 T4、device 由 T2）。`scripts/layout-check.sh` 由 T4 提供；T2 补上 device
preflight 的 `E2631_KERNEL_AT/ROOTFS_SPAN/HEADER_AT` 字面量后，5 份副本全部 PASS（本轮 make check
已绿，T2 的改动随其提交落地）。

与打包模板的关系：版本头 512 字节仍从 `seed/vendor-verhdr-8b8.bin` 复制，只改 version 等字段；
`tools/mkfactory.mjs` 用 `--rootfs-at/--header-at` 决定 body 结束位置，rootfs 窗口
`0x1100000`（17 MiB）必须在 header 之前结束——bootloader 的校验和覆盖声明范围。
`tools/make_fixture.mjs` 造的测试包版本串改为 `ImmortalWrt v1.10.0`，与真实构建一致，
用来走通「打包器 → fwslot 身份判定」这条路。

## 6. 尚未被证明的部分（需 CI / 真机 / 后续任务）

1. **真实构建未跑**：本地不编译；apk-openssl 基底下的 `world`、feeds 实际 URL、产物在
   `E2631_OUT` 的落点，只有 CI（T5，`publish=false` 的 dispatch）能证明。
2. **manifest 的 libustream ABI 后缀**：`tools/verify_img.mjs` 已放宽为 `libustream-(mbedtls|openssl)\d+`
   家族匹配，但 ImmortalWrt feed 实际叫什么名只有构建后可见。
3. **fwslot 身份判定**：`ImmortalWrt v1.10.0` 被判为「我们」依赖 T2 的 `header_identity()` 双前缀
   修复；T2 已在工作区实现并让 `tests/test-slot-decisions.c` 的 ImmortalWrt 用例通过（slot-tool
   门禁已转绿），最终口径以 T2 的提交为准。
4. **真实 release 通道**：目前没有任何 Release，「latest release → 资产」只能等 T5 的预发布
   或用户批准后的正式 Release 才能端到端验证；host 模拟用的是同形状的假 JSON。
5. **真机 sysupgrade**：模拟里的 sysupgrade 是桩，真机写运行槽、失败回落、CRC 回读属于
   刷写操作，必须用户批准后由 T5/用户执行。
6. **legacy 回退构建**留不下 vendored argon/homeproxy（同名包来自 feed），theme 回落 bootstrap、
   homeproxy 包缺失；这是删除 overlay 副本的既定代价（T2 在 `base/README.md` 记录）。
7. **SSID 品牌**：默认开放 AP 的 SSID 已由 T2 从 `E2631-OpenWrt` 改为 `E2631-ImmortalWrt`，
   `e2631-wifi-boot` 的 reset matcher 仍保留旧名以兼容已刷设备；这是首启产品行为变化，
   现网已刷设备的升级后行为仍需真机确认，Release 文案里不做承诺。

## 7. 复现

```
node host/sim-upgrade.mjs        # 在线更新模拟：30 checks
node tools/check-workflows.mjs   # CI 静态一致性：39 checks
bash scripts/layout-check.sh     # 5 份几何常量（已全绿，T2 提交后一致）
make check                       # 全部门禁；未 bootstrap 时部分 SKIP 属预期
```

CI 侧：`check.yml` 已包含前两条；`firmware.yml` 只在 Lead 于 T5 手动 dispatch 时运行
（`publish=false`，不产生 Release）。
