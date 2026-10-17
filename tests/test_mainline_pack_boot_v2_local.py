"""Fail-closed local Boot Header v2 packing tests (no real boot images, no phone)."""
import gzip
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "packer", ROOT / "scripts/mainline_pack_boot_v2_local.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture(directory):
    base = Path(directory)
    stock, pre, kernel, ramdisk, dtb = [base / name for name in
        ("boot.img", "preflight.json", "Image", "initramfs.gz", "umi.dtb")]
    stock.write_bytes(b"PRIVATE-BOOT-NO-PUBLISH")
    k = bytearray(128)
    k[0x38:0x3c] = b"ARMd"
    kernel.write_bytes(k)
    ramdisk.write_bytes(gzip.compress(
        b"070701" + b"UMI612-MINIMAL-INIT" + bytes(200)))
    from struct import pack
    dtb.write_bytes(pack(">II", 0xD00DFEED, 256)
                    + bytes(28) + b"Xiaomi Mi 10 (umi)\0ramoops@b0000000"
                    + bytes(512))
    obj = {"device":"umi","backups":{"boot":{"saved_locally":True,
        "size_bytes":134217728,
        "sha256":hashlib.sha256(stock.read_bytes()).hexdigest(),
        "header":{"kernel_bytes":1234,"ramdisk_bytes":4096}}}}
    pre.write_text(json.dumps(obj))
    layout = {"boot_header_version":2,"page_size":4096,
        "image_size_bytes":134217728,
        "sections":{"kernel":{"size":1234},"ramdisk":{"size":4096},
                    "dtb":{"size":300}},
        "layout_plausible_for_umi":True}
    return stock,pre,kernel,ramdisk,dtb,layout

class FirstbootPackingTests(unittest.TestCase):
    def test_private_original_checksum_and_payload(self):
        with tempfile.TemporaryDirectory() as td:
            stock,pre,kernel,ramdisk,dtb,info=fixture(td)
            with mock.patch.object(m,"audit_boot",return_value=info):
                self.assertIs(m.validate_inputs(stock,pre,kernel,ramdisk,dtb),info)

    def test_dtb_must_exist_in_original_header(self):
        with tempfile.TemporaryDirectory() as td:
            stock,pre,kernel,ramdisk,dtb,info=fixture(td)
            info["sections"]["dtb"]["size"]=0
            with mock.patch.object(m,"audit_boot",return_value=info):
                with self.assertRaisesRegex(ValueError,"NO standalone DTB"):
                    m.validate_inputs(stock,pre,kernel,ramdisk,dtb)

    def test_wrong_stock_backup_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            stock,pre,kernel,ramdisk,dtb,info=fixture(td)
            stock.write_bytes(b"NOT-THE-SAME-BOOT")
            with self.assertRaisesRegex(ValueError,"checksum"):
                m.validate_inputs(stock,pre,kernel,ramdisk,dtb)

    def test_wrong_dtb_identity_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            stock,pre,kernel,ramdisk,dtb,info=fixture(td)
            dtb.write_bytes(b"\xd0\x0d\xfe\xed"+bytes(256))
            with mock.patch.object(m,"audit_boot",return_value=info):
                with self.assertRaisesRegex(ValueError,"invalid FDT DTB size"):
                    m.validate_inputs(stock,pre,kernel,ramdisk,dtb)

    def test_lineage_null_arg_list_preserves_empty_board_value(self):
        tokens = ["--header_version", "2", "--kernel", "kernel",
                  "--ramdisk", "ramdisk", "--dtb", "dtb",
                  "--pagesize", "0x00001000", "--board", "",
                  "--cmdline", "console=ttyMSM0"]
        binary = b"\0".join(s.encode("utf8") for s in tokens) + b"\0"
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
                m.subprocess, "run", return_value=m.subprocess.CompletedProcess(
                    ["python"], 0, binary, b"")):
            args, pairs = m.mkboot_args(Path(td) / "unpack_bootimg.py",
                                        Path(td), Path(td) / "stock.img",
                                        Path(td) / "unpacked")
        self.assertEqual(args, tokens)
        self.assertEqual(pairs["--board"], "")
        self.assertEqual(pairs["--cmdline"], "console=ttyMSM0")

    def test_replaces_values_by_option_not_the_old_value(self):
        original = ["--header_version", "2", "--kernel", "old-kernel",
                    "--ramdisk", "old-ramdisk", "--dtb", "old-dtb",
                    "--pagesize", "4096", "--board", "",
                    "--cmdline", "old androidboot.cmdline"]
        changes = {"--kernel": "NEW-ARM64-IMAGE",
                   "--ramdisk": "NEW-STATIC-INITRD",
                   "--dtb": "NEW-UMI-P1N-DTB",
                   "--cmdline": "rdinit=/init loglevel=8"}
        actual = m.replace_mkbootimg_values(original, changes)
        pairs = dict(zip(actual[::2], actual[1::2]))
        for name, value in changes.items():
            self.assertEqual(pairs[name], value)
        self.assertEqual(pairs["--board"], "")
        self.assertEqual(pairs["--header_version"], "2")
        self.assertNotIn("old-kernel", actual)
        self.assertNotIn("old-ramdisk", actual)
        self.assertNotIn("old-dtb", actual)
        self.assertNotIn("old androidboot.cmdline", actual)

    def test_replacement_requires_all_named_switches(self):
        with self.assertRaisesRegex(ValueError, "missing required"):
            m.replace_mkbootimg_values(
                ["--kernel", "old"], {"--dtb": "new"})

    def test_unsigned_avb_hash_props(self):
        info = ("Algorithm:                NONE\n"
                "      Partition Name:        boot\n"
                "      Hash Algorithm:        sha256\n"
                "Prop: com.android.build.boot.os_version -> '16'\n"
                "Prop: com.android.build.boot.fingerprint -> 'test'\n")
        p=m.parse_avb_info(info)
        self.assertEqual(p, ["com.android.build.boot.os_version:16",
                             "com.android.build.boot.fingerprint:test"])

    def test_signed_avb_rejected(self):
        info="Algorithm: SHA256_RSA2048\nPartition Name: boot\nHash Algorithm: sha256\n"
        with self.assertRaisesRegex(ValueError,"unsupported algorithm"):
            m.parse_avb_info(info)

    def test_script_does_not_phone_or_flash(self):
        import inspect
        code=inspect.getsource(m)
        self.assertNotIn("adb shell", code)
        self.assertNotIn("fastboot flash", code)
        self.assertNotIn("subprocess.run([\"adb\"", code)
        self.assertIn("safe_to_flash", code)

    def test_requires_output_not_in_repo_and_not_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"existing.img"
            out.write_bytes(b"x")
            with self.assertRaisesRegex(ValueError,"output already exists"):
                m.run_pack(out,out,out,out,out,Path(td),out,out)

if __name__ == "__main__":
    unittest.main()
