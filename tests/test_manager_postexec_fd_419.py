import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "manager_fd_proto", Path(__file__).resolve().parents[1] / "scripts/patch_manager_postexec_fd_419.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PostExecBootstrapPrototype(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ksu = Path(self.tmp.name)
        self.ksu.joinpath("Kbuild").write_text("obj-y += supercall/\n")
        self.c = self.ksu / "supercall/supercall.c"
        self.c.parent.mkdir()
        self.start = "\n".join((
            mod.OLD_INCLUDE,
            mod.OLD_INIT,
            "    return;",
            "}",
            mod.OLD_EXIT,
            "    cleanup();",
            "}",
        ))
        self.c.write_text(self.start)

    def test_auth_scoping_lifecycle_and_idempotence(self):
        self.assertTrue(mod.patch(self.ksu))
        s = self.c.read_text()
        self.assertIn("!is_manager()", s)
        self.assertIn('"/data/app/"', s)
        self.assertIn('"/me.weishu.kernelsu-"', s)
        self.assertIn('"/libksud.so"', s)
        self.assertIn("register_trace_sched_process_exec(", s)
        self.assertIn("unregister_trace_sched_process_exec(", s)
        self.assertIn("fd = ksu_install_fd();", s)
        self.assertIn("#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)", s)
        self.assertNotIn("O_CLOEXEC, 0", s)
        self.assertFalse(mod.patch(self.ksu))

    def test_drift_fails_without_partial_modification(self):
        s = self.start.replace(mod.OLD_EXIT, "void ksu_other_exit(void) {")
        self.c.write_text(s)
        with self.assertRaises(ValueError):
            mod.patch(self.ksu)
        self.assertEqual(s, self.c.read_text())

    def test_partial_marker_refuses(self):
        self.c.write_text(mod.MARKER)
        with self.assertRaises(ValueError):
            mod.patch(self.ksu)
