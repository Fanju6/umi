"""Compatibility patch checks with mini fixtures matching pinned version."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("policy419",Path(__file__).resolve().parents[1]/"scripts/patch_policy_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
class Tests(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.root=Path(self.d.name)
        for name in ["policy","supercall"]: (self.root/name).mkdir()
        (self.root/"Kbuild").write_text("obj-$(CONFIG_KSU) += kernelsu.o\n")
        self.p=self.root/"policy/app_profile.c"
        self.a=self.root/"policy/allowlist.c"
        self.s=self.root/"supercall/supercall.c"
        self.p.write_text("    atomic_set(&current->seccomp.filter_count, 0);\n    seccomp_filter_release(fake);\n")
        self.a.write_text("#include <linux/task_work.h>\n    if (task_work_add(tsk, cb, TWA_RESUME)) {\n")
        self.s.write_text("#include <linux/task_work.h>\n        if (task_work_add(current, &tw->cb, TWA_RESUME)) {\n")
    def test_idempotence_and_4_19_guard(self):
        self.assertEqual(mod.patch(self.root),3)
        self.assertEqual(mod.patch(self.root),0)
        self.assertIn("put_seccomp_filter(fake)",self.p.read_text())
        self.assertIn("task_work_add(tsk, cb, true)",self.a.read_text())
        self.assertIn("task_work_add(current, &tw->cb, true)",self.s.read_text())
    def test_refuse_upstream_variation_atomically(self):
        self.s.write_text("unexpected upstream\n")
        before=self.p.read_text()
        with self.assertRaises(ValueError):mod.patch(self.root)
        self.assertEqual(self.p.read_text(),before)
