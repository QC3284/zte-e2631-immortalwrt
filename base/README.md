# base/ —— sanechips target 移植补丁（T2，ImmortalWrt 基底）

这个目录把 ZTE ZXHN E2631（ZX279128S）移植所需的 sanechips target 从
[Zlion-Y/openwrt-sanechips-mirror](https://github.com/Zlion-Y/openwrt-sanechips-mirror)
分支 `pr-zte-zxhn-h3600` 里**原样 vendor** 过来，作为 4 个 `git format-patch`
补丁存在。`scripts/bootstrap.sh` 在 `E2631_BASE_KIND=immortalwrt` 时把
ImmortalWrt 基底检出到钉死的 commit，再 `git am` 这 4 个补丁；legacy 基底
（原来的 OpenWrt sanechips 镜像）本来就含这些提交，不会再打一遍。

为什么要 vendor 而不是直接 clone 第二个仓库：项目的基底钉死在一个 ImmortalWrt
commit 上（docs/immortalwrt-migration.md §5.1），如果这里再依赖一个可变的
sanechips 仓库分支，同一条 `make bootstrap` 在两个月后可能装出另一棵树。把
补丁放进本仓库后，**基底由内容而不是分支指针定义**，三个钉死值任何一个变了
bootstrap 都会直接失败，而不是悄悄产出一棵"看起来一样"的树。

作者与许可：4 个提交的作者是 Navid Ghahremani `<ghahramani.navid@gmail.com>`，
2026-10-12，GPL-2.0-only（OpenWrt 上游移植的许可）。`git format-patch` 保留
了 From/Date/Subject/Signed-off-by，`git am` 会原样重建提交信息；本仓库改动
补丁内容时（只有 0002 一处，见下）必须在提交信息里写明原因。

## 三元组钉死（triple pin）

`commits.env` 是本目录唯一的数值来源，`scripts/env.sh` 会 source 它：

| 键 | 含义 |
| --- | --- |
| `E2631_IW_REPO` / `E2631_IW_BRANCH` / `E2631_IW_SHA` | ImmortalWrt 基底：仓库、分支、钉死的 commit |
| `E2631_IW_TREE_SHA` | 上面那个 commit 的 `HEAD^{tree}`（干净基底） |
| `E2631_BASE_KERNEL` | 基底内核版本，apply.sh 用 `target/linux/generic/kernel-6.18` 断言 |
| `E2631_PORT_REPO` / `E2631_PORT_BRANCH` / `E2631_PORT_SHA` | 补丁来源（provenance，只用于追溯） |
| `E2631_PORT_BASE_SHA` | 这 4 个提交原先基于的 upstream commit（ImmortalWrt 祖先） |
| `E2631_BASE_PATCH_SHA256_0001..0004` | 本目录每个补丁文件的 sha256 |
| `E2631_BASE_TREE_SHA` | 4 个补丁 `git am` 之后的 `HEAD^{tree}`，即最终基底 |

验证链（任何一步不符即失败，不会继续构建）：

1. `bootstrap.sh`：`git fetch --depth 1 <E2631_IW_SHA>` → checkout；
2. 逐个比对 4 个补丁的 sha256；
3. `git am` 后断言 `git rev-parse HEAD^{tree}` == `E2631_BASE_TREE_SHA`；
4. `apply.sh` 每次运行前再断言同一 tree hash（见下）；
5. `make check` 的 base-pin gate 在每次检查时重算补丁 sha256，有 bootstrapped
   树时再算 tree hash。

**tree hash 为什么稳定**：`git am` 在不同机器上会生成不同的 commit ID
（作者时间/提交者时间不同），但树内容相同，所以 `HEAD^{tree}` 不变；apply.sh
只改工作区、从不 commit，因此 apply 之后 `HEAD^{tree}` 仍是这个值。这就是
"同一条命令在任何机器上产出同一棵基底"的可判定标准。

当前钉死值（2026-11-14）：

- ImmortalWrt `master` @ `4765b657625ec5bbda74b44400465fe043802b30`（2026-11-05），
  内核 6.18.60，apk-openssl 默认；
- 干净基底 tree：`340ae5426d1c8dfa071e97f08993393b87a47671`；
- 移植后 tree：`4f89aa7ad0a5132dc047a27a9073b43916f0f957`。

## 4 个补丁

1. `0001-kernel-add-generic-DWC3-platform-glue-package.patch` —— 加
   `package/kernel/linux/modules/usb.mk` 里的 generic DWC3 platform glue
   （`kmod-usb-dwc3-generic-plat`），ZX279128S 的 USB 控制器需要它。
2. `0002-mt76-serialize-device-reads-with-outer-cache-maintenance.patch` ——
   mt76 设备寄存器读取用 outer cache maintenance 串行化（Wi-Fi 冷启动挂死的
   补丁之一），新增 `package/kernel/mt76/patches/001-wifi-mt76-...patch`。
3. `0003-sanechips-add-ZX279128S-target.patch` —— 整个
   `target/linux/sanechips`（46 个文件：target Makefile、config-6.18、board
   DTS、board files、kernel patches 001-028、base-files）。
4. `0004-sanechips-add-support-for-ZTE-ZXHN-H3600.patch` —— H3600 板级支持
   （9 个新文件 + image/Makefile 一行），E2631 与 H3600 共用 sanechips target。

### 0002 唯一的偏离（必须知道）

上游那个提交同时改了两处：mt76 的 **Makefile**（`PKG_RELEASE:=1` 改成
`:=2`）和新增驱动补丁。对 ImmortalWrt 基底（以及 legacy 基底）来说 Makefile
改动是**反向**的——两棵基底的 mt76 已经是 `:=2`，再打这个 hunk 会被 `git am`
拒绝或把版本号改回去。因此 vendored 版 0002 删掉了 Makefile hunk（diffstat
改为 1 file/110 insertions），其余逐字节保留，并在提交信息里写明了原因。

版本号由 `apply.sh` 负责：它要求 mt76 的 `PKG_RELEASE` 是 2 或 3，看到 2 就
改成 3，保证加了驱动补丁的 mt76 包不会复用上一版镜像的版本号；结构断言里也会
检查补丁存在且版本号是 3。

## 用法

```
# 默认仍是 legacy 基底（回滚开关，T5 通过前不变）
make bootstrap

# ImmortalWrt 基底：从钉死的 commit 起，git am base/ 的 4 个补丁
E2631_BASE_KIND=immortalwrt make bootstrap

# 基底重建之后，只重打 overlay（bootstrap 的快速路径）
E2631_BASE_KIND=immortalwrt make apply
```

也可以在 `.env` 里写 `E2631_BASE_KIND=immortalwrt`（见 `.env.example`）。
bootstrap 会把基底、overlay、feeds、seed `.config` 一次做到位；重复运行是
幂等的——基底 tree hash 已经是钉死值就跳过 `git am`。

## 升级 / 重新钉死（repin）runbook

基底前进（换 ImmortalWrt commit）时，按顺序做，**不要**只改一个数字：

1. 在临时目录浅克隆新 commit：`git init` + `git remote add origin
   https://github.com/immortalwrt/immortalwrt` + `git fetch --depth 1 origin
   <新 SHA>` + `git checkout FETCH_HEAD`；
2. `git -c user.name=... -c user.email=... am base/0001-*.patch ... base/0004-*.patch`。
   冲突就地解决，解决方式要作为补丁更新的一部分；
3. 记录新的 `HEAD^{tree}`，更新 `commits.env` 的 `E2631_IW_SHA`、
   `E2631_IW_TREE_SHA`、`E2631_BASE_TREE_SHA`（以及需要时的
   `E2631_BASE_KERNEL`）；如果补丁本身改了，同时更新对应 sha256；
4. 跑一遍 `E2631_BASE_KIND=immortalwrt make bootstrap` 和 `make check`；
5. 只有 CI 全绿（T5）才把新钉死值合入 main——钉子变更是"整条链一起换"，
   不是"改个数试试"。

## 回滚到 legacy 与已知代价

T5 通过前 `E2631_BASE_KIND` 默认 `legacy`，把值改回 `legacy` 即回滚到原
OpenWrt sanechips 基底（docs/immortalwrt-migration.md §5.6）。已知代价（已接受，
记录在案）：argon 主题和 homeproxy 的 vendored 副本在 v1.10 从 overlay 删除了
（ImmortalWrt luci feed 提供同款），旧 OpenWrt luci feed 没有这两个包，所以
legacy 回滚镜像会退回 bootstrap 主题、且没有 luci-app-homeproxy/sing-box
插件——设备可启动、可升级，但少这两个功能。base/ 目录本身对 legacy 无影响
（legacy 基底已含这 4 个提交，bootstrap 不会再 am）。
