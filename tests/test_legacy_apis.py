"""Regression checks for Linux 4.19 KernelSU mount/fsnotify shims."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location("legacy", Path(__file__).resolve().parents[1]/"scripts/patch_legacy_apis.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

MOUNT = """#include <uapi/linux/mount.h>
int fn(void) {
    int pm_ret = path_mount(NULL, &root_path, NULL, MS_PRIVATE | MS_REC, NULL);
    return pm_ret;
}
"""
OBSERVER = """static int ksu_handle_inode_event(struct fsnotify_mark *mark, u32 mask, struct inode *inode, struct inode *dir,
                                  const struct qstr *file_name, u32 cookie)
{
    if (file_name->len == 13 && !memcmp(file_name->name, "packages.list", 13)) {
    }
    return 0;
}

static const struct fsnotify_ops ksu_ops = {
    .handle_inode_event = ksu_handle_inode_event,
};
"""
class TestLegacy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for sub in ("infra","manager"): (self.root/sub).mkdir()
        (self.root/"Kbuild").write_text("obj-$(CONFIG_KSU) += kernelsu.o\n")
        self.mnt = self.root/"infra/su_mount_ns.c"
        self.obs = self.root/"manager/pkg_observer.c"
        self.mnt.write_text(MOUNT)
        self.obs.write_text(OBSERVER)

    def test_idempotent(self):
        self.assertEqual(module.patch(self.root),(True,True))
        mnt,obs = self.mnt.read_text(),self.obs.read_text()
        self.assertIn(module.MARKER_MOUNT,mnt)
        self.assertIn(module.MARKER_FSNOTIFY,obs)
        self.assertIn("set_fs(old_fs)",mnt)
        self.assertIn(".handle_event = ksu_handle_event",obs)
        self.assertEqual(module.patch(self.root),(False,False))
        self.assertEqual(self.mnt.read_text(),mnt)
        self.assertEqual(self.obs.read_text(),obs)

    def test_reject_unknown_without_edit(self):
        self.obs.write_text(OBSERVER.replace(".handle_inode_event =",".other ="))
        with self.assertRaises(ValueError): module.patch(self.root)
        self.assertEqual(self.mnt.read_text(),MOUNT)
