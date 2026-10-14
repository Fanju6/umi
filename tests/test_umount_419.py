import importlib.util
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("umount",Path(__file__).resolve().parents[1]/"scripts/patch_umount_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NAMESPACE = """static int do_umount(struct mount *mnt, int flags) {}
static inline bool may_mount(void) {}
void x(void) {
    if (!check_mnt(mnt)) return;
    mntput_no_expire(mnt);
    retval = do_umount(mnt, flags);
}
SYSCALL_DEFINE2(umount, char __user *, name, int, flags) {}
"""
KSU = """#include <linux/sched.h>
extern int path_umount(struct path *path, int flags);
static void ksu_umount_mnt(void) { path_umount(path, flags); }
"""

class TestUmount(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.kernel=Path(self.tmp.name)/"linux"
        self.ksu=Path(self.tmp.name)/"ksu"
        (self.kernel/"fs").mkdir(parents=True)
        (self.ksu/"kernel/feature").mkdir(parents=True)
        (self.ksu/"kernel/Kbuild").write_text("# kbuild\n")
        self.ns=self.kernel/"fs/namespace.c"
        self.uf=self.ksu/"kernel/feature/kernel_umount.c"
        self.ns.write_text(NAMESPACE)
        self.uf.write_text(KSU)
    def test_safe_unmount_helper_is_idempotent(self):
        self.assertTrue(mod.patch(self.kernel,self.ksu))
        n,u=self.ns.read_text(),self.uf.read_text()
        self.assertIn(mod.MARKER,n)
        self.assertIn(mod.MARKER,u)
        self.assertIn("mntput_no_expire(mnt)",n)
        self.assertIn("if (!check_mnt(mnt))",n)
        self.assertIn("if (!may_mount())",n)
        self.assertIn("if (flags & MNT_FORCE && !capable(CAP_SYS_ADMIN))",n)
        self.assertIn("ksu_legacy_path_umount",u)
        self.assertFalse(mod.patch(self.kernel,self.ksu))
        self.assertEqual((n,u),(self.ns.read_text(),self.uf.read_text()))
    def test_partial_or_changed_upstream_refused(self):
        self.uf.write_text(KSU.replace(mod.DECLARATION,"/* drift */"))
        with self.assertRaises(ValueError):mod.patch(self.kernel,self.ksu)
        self.assertEqual(NAMESPACE,self.ns.read_text())
