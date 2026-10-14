import importlib.util
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location("output_gate",Path(__file__).resolve().parents[1]/"scripts/check_build_output.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class BuildOutputGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        self.image=self.out/"arch/arm64/boot/Image"
        self.image.parent.mkdir(parents=True)
        self.elf=self.out/"vmlinux"
        self.dtb=self.out/"arch/arm64/boot/dts/qcom/umi.dtb"
        self.dtb.parent.mkdir(parents=True)
        self.dtb.write_bytes(b"fixture")
        self.image.write_bytes(b"Z"*(1024*1024+1))
        self.elf.write_bytes(b"Y"*(1024*1024+1))
    def test_baseline_must_disable_ksu(self):
        (self.out/".config").write_text(
            "CONFIG_EXT4_FS=y\nCONFIG_SECURITY_SELINUX=y\n# CONFIG_KSU is not set\n"
        )
        self.assertTrue(mod.check_output("baseline",self.out)["passed"])
        (self.out/".config").write_text(
            "CONFIG_EXT4_FS=y\nCONFIG_SECURITY_SELINUX=y\nCONFIG_KSU=y\n"
        )
        self.assertFalse(mod.check_output("baseline",self.out)["passed"])
    def test_ksu_requires_full_image_and_driver(self):
        (self.out/".config").write_text(
            "CONFIG_EXT4_FS=y\nCONFIG_SECURITY_SELINUX=y\nCONFIG_KPROBES=y\nCONFIG_KSU=y\n"
        )
        self.assertFalse(mod.check_output("ksu",self.out)["passed"])
        archive=self.out/"drivers/kernelsu/built-in.a"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"archive")
        self.assertTrue(mod.check_output("ksu",self.out)["passed"])
        self.image.unlink()
        self.assertFalse(mod.check_output("ksu",self.out)["passed"])
