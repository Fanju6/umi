"""Static regression tests for VFS 4.19 exact-match source patch."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("vfs419", Path(__file__).resolve().parents[1] / "scripts/patch_vfs_419.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SRC = """#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 1, 0)
static int ksu_wrapper_iopoll(struct kiocb *iocb, int x) { return 0; }
#else
static int ksu_wrapper_iopoll(struct kiocb *kiocb, bool spin)
{
    return orig->f_op->iopoll(kiocb, spin);
}
#endif
// no REMAP_FILE_DEDUP: use file_in
static loff_t ksu_wrapper_remap_file_range(void) { return 0; }
static int ksu_wrapper_fadvise(struct file *fp, loff_t off1, loff_t off2, int flags) { return 0; }
    p->ops.iopoll = fp->f_op->iopoll ? ksu_wrapper_iopoll : NULL;
    p->ops.remap_file_range = fp->f_op->remap_file_range ? ksu_wrapper_remap_file_range : NULL;
"""

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "infra").mkdir()
        (self.root / "Kbuild").write_text("obj-$(CONFIG_KSU) += kernelsu.o\n")
        self.path = self.root / "infra/file_wrapper.c"
        self.path.write_text(SRC)

    def test_idempotent(self):
        self.assertTrue(module.patch(self.root))
        once = self.path.read_text()
        self.assertIn(module.MARKER, once)
        self.assertIn("p->ops.clone_file_range", once)
        self.assertIn("p->ops.dedupe_file_range", once)
        self.assertFalse(module.patch(self.root))
        self.assertEqual(self.path.read_text(), once)

    def test_rejects_unknown_without_partial_file_change(self):
        broken = SRC.replace("p->ops.remap_file_range =", "p->ops.unknown =")
        self.path.write_text(broken)
        with self.assertRaises(ValueError):
            module.patch(self.root)
        self.assertEqual(self.path.read_text(), broken)
