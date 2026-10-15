"""Fail-closed arm64 syscall dispatcher regression (umi first-stage boot failure)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "ksu_failclosed", ROOT / "scripts/patch_syscall_failclosed_419.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FailClosedSyscallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.joinpath("Kbuild").write_text("obj-y += core/\n")
        self.file = self.root / "hook/arm64/syscall_hook.c"
        self.file.parent.mkdir(parents=True)
        self.file.write_text(
            "#include <linux/compiler.h>\n"
            + mod.OLD_HOOK + "\nvoid ksu_syscall_hook_init(void) {\n"
            + mod.OLD_INIT + "\n}\n"
        )

    def test_patch_is_idempotent_and_remains_fail_closed(self):
        self.assertTrue(mod.patch(self.root))
        new = self.file.read_text()
        self.assertIn(mod.MARKER, new)
        self.assertIn("if (patch_syscall_table(nr, fn))", new)
        self.assertIn("if (READ_ONCE(ksu_syscall_table[ni_slot]) !=", new)
        self.assertIn("WRITE_ONCE(ksu_dispatcher_nr, -1);", new)
        self.assertIn("WRITE_ONCE(ksu_dispatcher_nr, ni_slot);", new)
        self.assertLess(
            new.index("if (READ_ONCE(ksu_syscall_table[ni_slot]) !="),
            new.index("WRITE_ONCE(ksu_dispatcher_nr, ni_slot);"))
        self.assertIn("syscall redirection", new)
        self.assertNotIn("dispatcher installed at slot", new)
        self.assertFalse(mod.patch(self.root))
        self.assertEqual(self.file.read_text(), new)

    def test_source_drift_refused_without_partial_edits(self):
        self.file.write_text("unsigned int total=0;\n" + mod.OLD_INIT)
        before = self.file.read_text()
        with self.assertRaises(ValueError):
            mod.patch(self.root)
        self.assertEqual(self.file.read_text(), before)

    def test_unknown_root_rejected(self):
        with self.assertRaises(ValueError):
            mod.patch(self.root / "missing")

    def test_incomplete_previous_patch_refused(self):
        self.file.write_text(mod.MARKER + "\n")
        with self.assertRaises(ValueError):
            mod.patch(self.root)
