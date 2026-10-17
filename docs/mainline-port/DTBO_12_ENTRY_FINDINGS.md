# umi 12-entry DTBO report · actual findings and mainline action boundary

**2026-10-17.** This report analyzes the uploaded sanitized JSON (user's successful Root read-only scan) and crosschecks the locked vendor source; it is not an inferred bootloader selection or experimental Linux 6.12 boot result.

## Observed full table, on-device Android DT Table v0

Entries are FDT-structurally parseable 12/12. Total Android DTBO declared size 5,514,578 bytes.

| index | root model suffix | FDT length (bytes) |
|---:|---|---:|
| 0 | alioth | 458105 |
| 1 | apollo | 459753 |
| 2 | cas | 467393 |
| 3 | cmi | 460176 |
| 4 | dagu | 454590 |
| 5 | elish | 462995 |
| 6 | enuma | 461319 |
| 7 | lmi | 451884 |
| 8 | munch | 462317 |
| 9 | psyche | 456050 |
| 10 | thyme | 458797 |
| **11** | **umi** | **460783** |

Every entry has id=0x00000000, rev=0x00000000, and all four custom fields 0x00000000; every root compatible reports qcom,kona-mtp, qcom,kona, qcom,mtp. **Only entry 11 has root model Qualcomm Technologies, Inc. xiaomi umi.** Its FDT begins at byte offset 5,053,795 within the 5,514,578-byte DTBO container.

Fixed vendor source confirms the intended umi overlay identity independently:
https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/umi-sm8250-overlay.dts

The source has that exact model, matching compatibles, and a root qcom,board-id pair of 43,0. **This root qcom,board-id is not equivalent to the outer DTBO entry id**, which is zero in all 12 observed entries. The 43,0 value was taken from source, not newly measured from the live tree.

## What the 96 power-property hits actually mean

All 12 FDTs contain exactly the same eight selected UFS-related property names. The 96 hits thus count 12 x 8 *declarations*, not independent physical power rails:

- PHY (umi fragment@74): vdda-phy-supply, vdda-pll-supply.
- UFS host (umi fragment@75): vdd-hba-supply, vcc-supply, vccq-supply, vccq2-supply, qcom,vddp-ref-clk-supply, qcom,vccq-parent-supply.

The locked shared vendor source defines the same names: https://github.com/LineageOS/android_kernel_xiaomi_sm8250/blob/71b13e62f057a649b77fe4062feb73ee72ad609c/arch/arm64/boot/dts/vendor/qcom/xiaomi-sm8250-common.dtsi. That strongly explains why all twelve board overlay entries share these names. It does **not** mean their encoded phandles or board wiring are all equivalent; the uploaded report intentionally excludes these numeric values.

The reported fragment_target_paths arrays are all empty, **not evidence of missing fragments**. At least umi fragment@74 and fragment@75 exist, with UFS properties; the tool only extracted explicit target-path properties. The compiled vendor overlays can instead point at a target phandle. Resolving fragment target numbers against the actual board/base FDT is not possible from this report alone. Fragment numbers are overlay-local indexes, not hardware addresses.

## Practical impact for Linux 6.12

The board-specific candidate is now unambiguous *within this DTBO table* (entry 11). There is no need to repeatedly scan unrelated alioth/apollo/cmi/... overlays for these common UFS properties.

Data proven at this point:
- 9 actual old-kernel regulator outputs were enabled with runtime sysfs values; 9 matching qcom,resource-name values were seen in the running old device-tree.
- The last Root report has old host 1d84000.ufshc at runtime PM active, PHY at runtime PM unsupported (not proof of malfunction).
- The old ramoops region [0xB0000000, 0xB0400000) is a reserved child of System RAM, compatible with P1j source and runtime module parameters.
- Boot and Recovery partition header v2, and Android DTBO Table v0 with 12 structurally parsed overlays, are known.

Remaining blockers before any hardware enablement: **the final merged UFS/PMIC phandle topology as applied by the bootloader**, six PM8150 input supply parent groups, two vendor-only UFS power-vote lifecycles (one includes shared WLAN/BT usage), mainline 6.12 regulator timing, and reliable Recovery fallback/early logs. Source-level unit tests and a compiling DTB do not resolve any of these.

**Next engineering step** should target the running/merged old FDT's *selected UFS host/PHY phandle values and provider identities*, not another full DTBO scan. Compare with the locked umi vendor sources and 6.12 UFS/power bindings, and develop the mainline research DTS only after electrical and compatibility checks. Any parsing must be bounded and filtered; do not publish a raw full DTB containing unknown device metadata without inspection.

The data do not prove which Bootloader overlay was selected. Model umi is a strong unique candidate, not a logged selection result.

Keep research/sm8250-mainline-p0 and PR #8 independent of stable main. Do not attempt an experimental Linux 6.12 boot, flash, partition write or regulator voltage/enable change. safe_to_attempt_mainline_boot=false, safe_to_flash=false.
