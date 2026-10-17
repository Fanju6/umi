"""Cloud-only Boot v2 packer regression. No network, device, or real images."""
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "cloud_pack", ROOT / "scripts/mainline_cloud_pack_umi.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
WORKFLOW = ROOT / ".github/workflows/mainline-cloud-firstboot.yml"

class CloudPackerTests(unittest.TestCase):
    def test_public_lineage_boot_pin_is_not_user_backup(self):
        self.assertEqual(len(m.PUBLIC_ROM_SHA256), 64)
        self.assertEqual(len(m.PRIVATE_DEVICE_SHA256), 64)
        self.assertNotEqual(m.PUBLIC_ROM_SHA256, m.PRIVATE_DEVICE_SHA256)

    def test_wrong_public_baseline_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "wrong.img"
            p.write_bytes(b"not pinned public umi boot")
            with self.assertRaisesRegex(ValueError, "wrong pinned"):
                m.validate_data(p, p, p, p)

    def test_cloud_code_does_not_flash_or_adb(self):
        src = (ROOT / "scripts/mainline_cloud_pack_umi.py").read_text()
        for banned in ("fastboot flash", "adb shell", "dd of=", "reboot bootloader"):
            self.assertNotIn(banned, src)

    def test_short_bootargs_for_ram_only_pid1(self):
        self.assertIn("rdinit=/init", m.RAM_ONLY_BOOTARGS)
        self.assertIn("ignore_loglevel", m.RAM_ONLY_BOOTARGS)
        self.assertLess(len(m.RAM_ONLY_BOOTARGS), 256)
        self.assertNotIn("androidboot.", m.RAM_ONLY_BOOTARGS)

    def test_original_addresses_and_payload_hash_are_checked(self):
        src = (ROOT / "scripts/mainline_cloud_pack_umi.py").read_text()
        for token in ("kernel_addr", "ramdisk_addr", "dtb_addr",
                      "tags_addr", "second_addr", "os_version_packed",
                      "parse_avb_info", "sha256(file)", "AVB properties not preserved"):
            self.assertIn(token, src)

    def test_no_silent_unlocked_or_boot_claim(self):
        src = (ROOT / "scripts/mainline_cloud_pack_umi.py").read_text()
        self.assertIn('"safe_to_flash": False', src)
        self.assertIn('"device_boot_tested": False', src)
        self.assertIn('"baseline_matches_user_current_boot": False', src)

    def test_no_unpinned_stock_baseline(self):
        text = WORKFLOW.read_text()
        self.assertIn(m.PUBLIC_ROM_SHA256, text)
        self.assertIn("mirrorbits.lineageos.org/full/umi/20261004/boot.img", text)
        self.assertIn("sha256sum -c -", text)
        self.assertIn("lineage-23.0", text)
        self.assertNotIn("gh release upload", text)

    def test_real_kernel_compilation_and_pack_in_same_workflow(self):
        text = WORKFLOW.read_text()
        self.assertIn("Image", text)
        self.assertIn('make -C upstream', text)
        self.assertIn('needs: kernel', text)
        self.assertIn('mainline_cloud_pack_umi.py', text)
        self.assertIn('actions/upload-artifact@v4', text)
        self.assertIn('compression-level: 1', text)

    def test_one_cloud_build_no_device_writes(self):
        text = WORKFLOW.read_text()
        for forbidden in ("fastboot flash", "adb push", "adb reboot",
                          "dd if=/dev/block", "gh release create"):
            self.assertNotIn(forbidden, text)
        self.assertIn("All UFS / USB and research PMIC regulators remain DISABLED", text)

    def test_no_original_boot_backup_in_ci(self):
        text = WORKFLOW.read_text()
        self.assertNotIn("umi-original-images/boot.img", text)
        self.assertNotIn("PRIVATE_DEVICE_SHA256", text)
        self.assertIn("NOT user's modified Boot", text)

if __name__ == "__main__":
    unittest.main()
