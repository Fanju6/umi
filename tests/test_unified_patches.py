"""统一兼容补丁入口的版本、顺序与失败拒绝测试。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("unified_patches", ROOT / "scripts/apply_patches.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

LEGACY_PATCH_NAMES = (
    "apply_compat.py", "patch_vfs_419.py", "patch_legacy_apis.py",
    "patch_policy_419.py", "patch_sulog_419.py", "patch_dispatch_419.py",
    "patch_syscall_failclosed_419.py", "patch_arm64_block_walk_419.py",
    "patch_avtab_419.py", "patch_filename_419.py", "patch_type_419.py",
    "patch_selinux_core_419.py", "patch_rules_419.py", "patch_umount_419.py",
)
MODERN_PATCH_NAMES = LEGACY_PATCH_NAMES[:4] + (
    "patch_task_work_331.py", "patch_manager_postexec_fd_419.py",
) + LEGACY_PATCH_NAMES[4:]


class UnifiedCompatTests(unittest.TestCase):
    def test_test2_exact_original_order(self):
        self.assertEqual(tuple(name for name, _ in mod.plan("v3.3.0")), LEGACY_PATCH_NAMES)

    def test_v331_exact_original_order(self):
        self.assertEqual(tuple(name for name, _ in mod.plan("v3.3.1")), MODERN_PATCH_NAMES)

    def test_patches_refer_to_existing_scripts(self):
        for name, _ in mod.plan("v3.3.1"):
            self.assertTrue((ROOT / "scripts" / name).is_file(), name)

    def test_source_targets_preserved(self):
        plan = dict(mod.plan("v3.3.1"))
        self.assertEqual(plan["patch_selinux_core_419.py"], ("kernel",))
        self.assertEqual(plan["patch_umount_419.py"], ("kernel", "ksu"))
        self.assertEqual(plan["patch_manager_postexec_fd_419.py"], ("ksu",))

    def test_reject_wrong_ksu_pin(self):
        env = {
            "KSU_REF": "v3.3.1", "KSU_SHA": "0" * 40,
            "LINEAGE_KERNEL_SHA": mod.LINEAGE_SHA,
        }
        with self.assertRaisesRegex(ValueError, "KernelSU"):
            mod.validate_pins(env, "auto")

    def test_reject_cross_version(self):
        env = {
            "KSU_REF": "v3.3.1", "KSU_SHA": mod.PINS["v3.3.1"],
            "LINEAGE_KERNEL_SHA": mod.LINEAGE_SHA,
        }
        with self.assertRaisesRegex(ValueError, "混用"):
            mod.validate_pins(env, "v3.3.0")

    def test_reject_unknown_lineage_sha(self):
        env = {
            "KSU_REF": "v3.3.1", "KSU_SHA": mod.PINS["v3.3.1"],
            "LINEAGE_KERNEL_SHA": "0" * 40,
        }
        with self.assertRaisesRegex(ValueError, "LineageOS"):
            mod.validate_pins(env, "v3.3.1")

    def test_reject_unexpected_version(self):
        with self.assertRaises(ValueError):
            mod.plan("v3.3.2")

    def test_reject_unsafe_upstream_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "upstream.env"
            p.write_text("KSU_REF=$(rm -rf /)\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "白名单"):
                mod.load_pins(p)

    def test_pinned_config_matches_repo(self):
        env = mod.load_pins(ROOT / "config/upstream.env")
        self.assertEqual(mod.validate_pins(env, "auto"), "v3.3.1")

    def test_workflows_no_longer_duplicate_patches(self):
        paths = (
            ".github/workflows/source-audit.yml",
            ".github/workflows/kernel-smoke.yml",
            ".github/workflows/kernel-compile.yml",
            ".github/workflows/experimental-v331-boot.yml",
        )
        for path in paths:
            data = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("scripts/apply_patches.py", data, path)
            self.assertNotIn("python3 scripts/patch_", data, path)
            self.assertNotIn("python3 scripts/apply_compat.py", data, path)
