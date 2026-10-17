#!/usr/bin/env python3
"""P0b+ umi DT reserved-memory reg-only audit via unprivileged adb shell.

Reads only selected DT /reserved-memory/*/reg properties and cell-width metadata.
Does not read raw RAM, user files, device identifiers, or write device state.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

NODES = (
    'hyp_region@80000000', 'xbl_aop_region@80700000',
    'reserved-memory@80860000', 'res_xbl_uefi_log_region@80880000',
    'smem_region@80900000', 'removed_region@80b00000',
    'pil_camera_region@86200000', 'pil_wlan_fw_region@86700000',
    'pil_slpi_region@88c00000', 'pil_adsp_region@8bb00000',
    'pil_spss_region@8e000000', 'cdsp_secure_heap@8e100000',
    'cont_splash_region@9c000000', 'disp_rdump_region@9c000000',
)
TAG = '__UMI_REG__'
END = '__UMI_REG_END__'

# 所有路径均为固定白名单；设备输出不会注入 shell 命令。
_DEVICE_SCRIPT = """getprop ro.product.device
DT=/sys/firmware/devicetree/base
[ -d "$DT" ] || DT=/proc/device-tree
[ -d "$DT/reserved-memory" ] || exit 4
printf '__UMI_REG__ CELLS '
if [ -r "$DT/reserved-memory/#address-cells" ]; then
  od -An -v -tx1 "$DT/reserved-memory/#address-cells" | tr '\\n' ' '
else
  printf 'unreadable'
fi
printf '\\n__UMI_REG__ SIZES '
if [ -r "$DT/reserved-memory/#size-cells" ]; then
  od -An -v -tx1 "$DT/reserved-memory/#size-cells" | tr '\\n' ' '
else
  printf 'unreadable'
fi
printf '\\n'
""" + ''.join('''printf '__UMI_REG__ %%s ' '%s'
if [ -r "$DT/reserved-memory/%s/reg" ]; then
  od -An -v -tx1 "$DT/reserved-memory/%s/reg" | tr '\\n' ' '
else
  printf 'unreadable'
fi
printf '\\n'
''' % (n,n,n) for n in NODES) + "printf '__UMI_REG_END__\\n'\n"


def hex_bytes(raw: str) -> bytes | None:
    raw = raw.strip()
    if raw == 'unreadable':
        return None
    chunks = raw.split()
    if len(chunks) > 80 or any(not re.fullmatch(r'[0-9a-fA-F]{2}', ch) for ch in chunks):
        raise ValueError('reg 字节输出格式错误或过长')
    return bytes.fromhex(''.join(chunks))


def decode_cells(data: bytes, width: int) -> int:
    if width not in (1, 2) or len(data) != width * 4:
        raise ValueError('设备树 cell 长度不符合预期')
    return int.from_bytes(data, 'big')


def decode_ranges(raw: bytes, addr_cells: int, size_cells: int) -> list[dict]:
    n = 4 * (addr_cells + size_cells)
    if not raw or len(raw) % n or len(raw) > 80:
        raise ValueError('reg 属性字节数与 address/size-cells 不匹配')
    ranges = []
    for offset in range(0, len(raw), n):
        addr = decode_cells(raw[offset:offset + addr_cells * 4], addr_cells)
        size = decode_cells(raw[offset + addr_cells * 4:offset + n], size_cells)
        if not size:
            raise ValueError('reg 属性存在空尺寸')
        ranges.append({'base': f'0x{addr:016x}', 'size': f'0x{size:x}', 'bytes': size})
    return ranges


def parse(raw: str) -> dict:
    lines = raw.replace('\r', '').splitlines()
    if not lines or lines[0].strip() != 'umi':
        raise ValueError('仅支持小米 10 umi；未获得正确设备 ID')
    parts = {}
    ended = False
    for line in lines[1:]:
        line = line.strip()
        if line == END:
            ended = True
            break
        if not line.startswith(TAG + ' '):
            if line:
                raise ValueError('ADB 采集器输出包含异常行')
            continue
        key, _, value = line[len(TAG) + 1:].partition(' ')
        if key in parts or key not in (*NODES, 'CELLS', 'SIZES'):
            raise ValueError('未知或重复的设备树属性')
        parts[key] = hex_bytes(value)
    if not ended or set(parts) != set((*NODES, 'CELLS', 'SIZES')):
        raise ValueError('设备树采集不完整，不产生部分报告')
    if parts['CELLS'] is None or parts['SIZES'] is None:
        raise ValueError('保留区 #address-cells/#size-cells 不可读，不能解释 reg')
    ac = decode_cells(parts['CELLS'], 1)
    sc = decode_cells(parts['SIZES'], 1)
    if ac not in (1, 2) or sc not in (1, 2):
        raise ValueError('仅支持 1–2 个 32 位 address/size cells')
    out = {
        'device': 'umi', 'phase': 'P0b-reg',
        'source': 'adb shell unprivileged DT reg metadata',
        'address_cells': ac, 'size_cells': sc,
        'safe_to_flash': False, 'memory_contents_read': False, 'regions': {},
        'limitations': '仅只读 DT reg 属性；unreadable 表示权限或节点缺失，不代表设备缺少内存区',
    }
    for node in NODES:
        data = parts[node]
        out['regions'][node] = (
            {'status': 'unreadable'} if data is None else
            {'status': 'observed', 'ranges': decode_ranges(data, ac, sc)}
        )
    return out


def run(adb='adb'):
    r = subprocess.run(
        [adb, 'shell', 'sh'], input=_DEVICE_SCRIPT,
        capture_output=True, text=True, timeout=30, check=False,
    )
    if r.returncode:
        raise RuntimeError(f'ADB shell 返回失败：{r.returncode}，检查 USB 调试状态与 DT 节点可读性')
    return parse(r.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', default='adb')
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    try:
        data = run(args.adb)
        result = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(result, encoding='utf-8')
            print(f'已生成只读 DT reg 报告：{args.output}')
        else:
            print(result)
        return 0
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError) as exc:
        print(f'采集失败：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
