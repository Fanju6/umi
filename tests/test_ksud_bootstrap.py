"""Keep umi's assisted ksud installer safe and pinned; no runtime ADB calls."""
import unittest
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / "scripts/umi-ksud-bootstrap.ps1")

class KsudBootstrapContract(unittest.TestCase):
    def test_source_pinning_and_environment_gate(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for mandatory in (
            "8614de6cdc2233c71fd0d1c64381ea10fbe6658651bae9b5a8dab4fe08e6344b",
            "https://github.com/tiann/KernelSU/releases/download/v3.3.0/ksud-aarch64-linux-android",
            "23.2-20261004-NIGHTLY-umi",
            'if ($device -ne "umi")',
            'if ($selinux -ne "Enforcing")',
            'if ($uid -ne "0")',
            'if (-not $Install)',
            "Get-FileHash",
            '"install")',
            "u:object_r:ksu_file:s0",
        ):
            self.assertIn(mandatory, src)

    def test_no_automatic_flash_or_security_bypass(self):
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("fastboot flash", src.lower())
        self.assertNotIn("setenforce 0", src.lower())
        self.assertNotIn('@("shell", "mount", "-o", "remount"', src.lower())
        self.assertNotIn("build.prop", src.lower())
        self.assertIn("Do not overwrite a manager-maintained", src)
        self.assertIn('if ($existing -ne "ABSENT")', src)
        # Installer should not mistake adbd uid=0 for KernelSU app-root success.
        self.assertIn("ordinary-app Root", src)
