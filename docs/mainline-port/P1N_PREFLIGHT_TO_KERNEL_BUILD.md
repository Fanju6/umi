# umi：一次性 Boot/Recovery/DTBO 数据已收齐，立即转向 Linux 6.12 实际编译

2026-10-17：来自用户的最后一轮脱敏 Root preflight。原始镜像文件、校验信息保留于用户电脑，不提交 GitHub。本文件只公开与启动工程有关的匿名硬件事实。

## 实际分区与启动结构

| 项目 | 实测 |
| --- | --- |
| boot | 134217728 B, Android Header v2, page 4096, kernel 55560208 B, ramdisk 1494000 B, second 0 |
| recovery | 134217728 B, Android Header v2, page 4096, kernel 54837264 B, ramdisk 48962397 B, second 0 |
| dtbo | 33554432 B partition, Android DT Table v0 declared 5514578 B and 12 entries |
| vbmeta | 131072 B |
| vbmeta_system | 131072 B |
| vendor_boot | absent |
| super | 9126805504 B |

boot/recovery/dtbo 全部已在测试者电脑只读备份并计算 SHA-256（SHA 保留在其本地 JSON，而非本仓库）。当前 Verified Boot 状态 orange；其他 Flash 锁定状态属性 unavailable，不能据此确认独立 Fastboot unlock/temporary boot support。

pstore filesystem mounted；有 console/pmsg 类；旧 ramoops 0xB0000000 起始、大小 4 MiB、console 2 MiB、pmsg 2 MiB，但 record_size=0。不能据此承诺 Linux 6.12 panic/dmesg 留痕或可观察的 earlycon。

## 已经不需要重复采集的数据

之前已完成 umi 12-entry DTBO、索引 11 唯一 model=umi、Linux 4.19 运行设备树根 board-id <43 0>、UFS Host+PHY 八条真实 phandle、9 条启用的 PMIC 电源轨以及 Linux 6.12 P1m 五条标准供电的离线 DTS 编译。上述数据全部已经在研究分支存档，不再重复。

## 直接开始实际 Linux 6.12 ARM64 Image 编译

GitHub Actions workflow: .github/workflows/mainline-arm64-image.yml。

- 严格固定 torvalds/linux v6.12 SHA adc218676eef25575469234709c2d87185ca223a；
- 编译真正 Linux 6.12 ARM64 Image（不是只跑静态 DTS），并检查 UFS Qualcomm Host、RPMh regulator 内核选项；
- 编译 umi P1m 研究 DTS 并用 fdtget 校验五个标准 UFS/PHY regulator links、六个 UFS/USB 硬件节点和参考 provider 全部保持 disabled；
- 仅输出研究产物 Image.generic-arm64.NOT-FLASHABLE / config.generic-arm64 / umi-P1m-OFFLINE-NOT-BOOTABLE.dtb / SHA256SUMS；
- 该 ARM64 Image 只是通用内核，不含 umi 安全启动所需的已使能板级 DTS、原始设备厂商二进制、initramfs、boot.img、AVB 或已验证的恢复流程。因此绝不可下载后刷入手机。

## 唯一重要的剩余门禁

1. 真正完成可启动的 umi 板级 PMIC/UFS 供电、输入 parent、两条厂商 UFS 特殊电源投票生命周期以及固件/内存区域匹配；禁用研究 provider 不等于电气安全验证。
2. 按已确认的 Android Boot Header v2 对最小 initramfs 和内核进行本机离线打包/结构检查；不能从镜像头猜测 fastboot 支持。
3. 验证 **可逆恢复** 和真实 early failure log 通路。设备非 A/B；Boot/Recovery 备份存在不等于实测过回刷，pstore mount 不等于新内核 crash 后日志可读。任何写 boot/recovery/vbmeta 之前必须先验证恢复通路。

研究 PR #8 保持 Open，main 不改。safe_to_flash=false；safe_to_attempt_mainline_boot=false。下一阶段以成功的编译产物和可恢复启动为验收，而不是再增加一串没有工程收益的 Root 探针。
