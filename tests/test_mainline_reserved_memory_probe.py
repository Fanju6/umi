"""P0b+ reserved-memory 元数据只读采集及安全门禁回归。"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'memprobe', ROOT / 'scripts/mainline_reserved_memory_probe.py'
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def hx(data: bytes):
    return ' '.join(f'{x:02x}' for x in data)


def fixture(override=None):
    payload = {
        'CELLS': hx((2).to_bytes(4, 'big')),
        'SIZES': hx((2).to_bytes(4, 'big')),
    }
    payload.update({k: 'unreadable' for k in mod.NODES})
    payload['hyp_region@80000000'] = hx(
        (0x80000000).to_bytes(8, 'big') + (0x600000).to_bytes(8, 'big')
    )
    if override:
        payload.update(override)
    return 'umi\n' + ''.join(
        f'{mod.TAG} {k} {v}\n' for k, v in payload.items()
    ) + mod.END + '\n'


class ReservedMemoryProbeTests(unittest.TestCase):
    def test_decode_big_endian_ranges(self):
        result = mod.parse(fixture())
        ranges = result['regions']['hyp_region@80000000']['ranges']
        self.assertEqual(ranges[0]['base'], '0x0000000080000000')
        self.assertEqual(ranges[0]['bytes'], 0x600000)
        self.assertEqual(result['regions']['pil_adsp_region@8bb00000']['status'], 'unreadable')
        self.assertFalse(result['safe_to_flash'])

    def test_other_device_rejected(self):
        with self.assertRaises(ValueError):
            mod.parse(fixture().replace('umi\n', 'dagu\n', 1))

    def test_truncated_report_rejected(self):
        with self.assertRaisesRegex(ValueError, '不完整'):
            mod.parse(fixture().replace(mod.END, ''))

    def test_invalid_reg_length_rejected(self):
        with self.assertRaises(ValueError):
            mod.parse(fixture({'hyp_region@80000000': '00 00'}))

    def test_bad_hex_rejected(self):
        with self.assertRaises(ValueError):
            mod.parse(fixture({'hyp_region@80000000': 'zz'}))

    def test_only_whitelisted_metadata_and_no_writes(self):
        script = mod._DEVICE_SCRIPT
        self.assertEqual(len(mod.NODES), 14)
        self.assertTrue(all('/' not in n and '..' not in n for n in mod.NODES))
        for forbidden in (
            'su ', 'dd ', 'fastboot', 'mount ', 'chmod ', 'setprop',
            'imei', '/proc/cmdline', 'ro.boot.serialno', '/dev/block/',
            '/dev/mem', '/proc/kcore',
        ):
            self.assertNotIn(forbidden, script)
