# GPL 源码索取函(草稿 2026-11-14)—— ZTE ZXHN E2631

> 用途: 向中兴通讯索取本机(ZXHN E2631)固件中 GPL/LGPL 组件的对应源代码,
> 覆盖 U-Boot 2013.04 引导加载器与 cspkernel4.1 内核(含 FFE/PPE/tm/switch 模块)。
> 待用户确认后经中兴官方渠道(技术支持工单/热线/邮箱)发出。

---

致: 中兴通讯股份有限公司 技术支持中心

主题: 关于 ZTE ZXHN E2631(巡天 AX3000)固件中开源软件对应源代码的索取请求

尊敬的中兴通讯:

我是一台 ZTE ZXHN E2631 无线路由器(巡天 AX3000, 主控 Sanechips ZX279128S)的终端用户。
该设备固件(版本 V1.0.0.8B8.8000)包含下列以 GNU 通用公共许可证(GPLv2/LGPL)等开源
许可证发布的软件组件:

1. **U-Boot 2013.04** 引导加载器(设备串口启动日志: `U-Boot 2013.04 (Sep 25 2024)`);
2. **Linux 内核**(固件内泄露路径 `/zte/csp/opensource/cspkernel4.1/`, 包含
   `protocol/ffe/` 及 tm/switch 等模块);
3. 其他 GPL/LGPL 组件(如 busybox、hostapd、dropbear、OpenSSL 等, 以固件自带开源
   声明为准)。

依据 GPLv2 第 3 条、LGPL 第 4 条之义务, 贵司应向我提供上述组件**完整对应的源代码**,
且应满足「用于修改的首选形式」(complete, buildable source, 含编译脚本与配置)。

请提供:
- 可直接下载的源码链接, 或物理存储介质(介质费用由我方承担);
- 若上述固件版本无法提供, 请指明贵司开源代码发布平台(我已在
  https://opensource.ztedevices.com 检索, 该平台仅收录手机/MiFi/CPE 类产品,
  未收录 ZXHN 家庭路由器产品线)。

设备信息:
- 型号: ZTE ZXHN E2631(巡天 AX3000)
- 固件版本: V1.0.0.8B8.8000(备用槽 V1.0.0.7B5.8000)
- 主控: Sanechips ZX279128S(Cortex-A9 双核)

请于收到本函后按贵司开源合规流程予以处理。谢谢。

[署名/联系方式占位]

---

## 备注(不随函发出)
- 渠道候选: 中兴技术支持热线/官网工单(support.zte.com.cn)/服务邮箱; 微信小程序
  「中兴服务」亦可提交。优先走能留书面凭证的渠道(工单/邮件)。
- 开源门户检索结论(2026-11-14 实测): opensource.ztedevices.com 的产品接口
  `rest/product/tabDropDown` 共 1086 个条目, 全部 brand=ztedevices(手机/MiFi/CPE),
  **无任何 ZXHN/ZX279128S 家用路由器条目**; opensource.zte.com.cn 域名不存在
  (NXDOMAIN)。⇒ 官方发布渠道对 E2631 不可用, 必须走直接索取。
- 索取范围策略: U-Boot 与内核一次要齐(两者同为 GPLv2, 义务同源); 若对方要求
  提供购买凭证/SN, 如实提供即可(索取 GPL 源码是法定权利, 无需谈判)。
- 时间预期: 国内厂商响应通常 2-6 周, 可能以邮件链接/网盘形式交付; 拿到后首先
  核对 U-Boot 源码能否对应 2013.04 (Sep 25 2024) 二进制。
