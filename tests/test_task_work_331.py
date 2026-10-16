import importlib.util
import tempfile
import unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location("compat_taskwork", Path(__file__).resolve().parents[1] / "scripts/patch_task_work_331.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ManagerTaskWorkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.joinpath("Kbuild").write_text("obj-y += manager/\n")
        self.target = self.root / "manager/pkg_observer.c"
        self.target.parent.mkdir()
        self.src = ('#include <linux/version.h>\n#include <linux/task_work.h>\n'
                    'static void ksu_track_throne_tw_func(struct callback_head *cb) {}\n'
                    'static void ksu_defer_track_throne(void) {\n' + mod.OLD + '\n}\n')
        self.target.write_text(self.src)

    def test_legacy_compat_idempotent(self):
        self.assertTrue(mod.patch(self.root))
        updated = self.target.read_text()
        self.assertIn("task_work_add(current, cb, true)", updated)
        self.assertIn("task_work_add(current, cb, TWA_RESUME)", updated)
        self.assertFalse(mod.patch(self.root))
        self.assertEqual(updated, self.target.read_text())

    def test_upstream_drift_rejected(self):
        changed = self.src.replace(mod.OLD, "track_throne(false);")
        self.target.write_text(changed)
        with self.assertRaises(ValueError):
            mod.patch(self.root)
        self.assertEqual(changed, self.target.read_text())

    def test_incomplete_marker_rejected(self):
        self.target.write_text(mod.MARKER)
        with self.assertRaises(ValueError):
            mod.patch(self.root)
