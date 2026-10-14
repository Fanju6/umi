import importlib.util
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("dispatch419",Path(__file__).resolve().parents[1]/"scripts/patch_dispatch_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
class TestDispatch419(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/"supercall").mkdir()
        (self.root/"Kbuild").write_text("# Kbuild\n")
        self.path=self.root/"supercall/dispatch.c"
        self.path.write_text("#include <linux/thread_info.h>\nvoid f() { task_pgrp(&init_task); }\n")
    def test_apply_twice(self):
        self.assertTrue(mod.patch(self.root))
        original=self.path.read_text()
        self.assertIn(mod.MARKER,original)
        self.assertIn("linux/sched/signal.h",original)
        self.assertFalse(mod.patch(self.root))
        self.assertEqual(self.path.read_text(),original)
    def test_reject_invalid_source(self):
        self.path.write_text("no task_pgrp\n")
        with self.assertRaises(ValueError):mod.patch(self.root)
