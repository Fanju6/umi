"""Safety contract of RAM-only Linux 6.12 first-boot PID1."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/mainline/mini-init.c"
CI = ROOT / ".github/workflows/mainline-mininit.yml"

class MinimalInitTests(unittest.TestCase):
    def test_marker_matches_recovery_collector(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("recovery", ROOT / "scripts/mainline_recovery_postmortem.py")
        m = module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertIn(m.TAG, SOURCE.read_text(encoding="utf8"))

    def test_no_boot_storage_mutations(self):
        code = SOURCE.read_text(encoding="utf8")
        for forbidden in ("/data", "/system", "/vendor", "/dev/block",
                          "reboot(", "system(", "execve(", "mkfs", "wipe"):
            self.assertNotIn(forbidden, code)

    def test_volatile_mounts_only(self):
        code = SOURCE.read_text(encoding="utf8")
        for allowed in ('mount("devtmpfs"', 'mount("proc"', 'mount("sysfs"'):
            self.assertIn(allowed, code)
        self.assertNotIn('mount("ext4"', code)

    def test_never_reboot_on_its_own(self):
        code = SOURCE.read_text(encoding="utf8")
        self.assertIn("for (;;)", code)
        self.assertIn("sleep(15)", code)

    def test_cross_compiler_and_cpio_build(self):
        text = CI.read_text(encoding="utf8")
        self.assertIn("aarch64-linux-gnu-gcc", text)
        self.assertIn("-static", text)
        self.assertIn("cpio -o --null -H newc", text)
        self.assertIn("retention-days: 5", text)

    def test_no_boot_image_in_workflow(self):
        text = CI.read_text(encoding="utf8")
        self.assertNotIn("mkbootimg.py", text)
        self.assertNotIn("fastboot flash", text)
        self.assertNotIn("boot.img --output", text)

if __name__ == "__main__":
    unittest.main()
