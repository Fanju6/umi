import importlib.util
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("txn419",Path(__file__).resolve().parents[1]/"scripts/patch_selinux_core_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/"security/selinux/ss").mkdir(parents=True)
        (self.root/"security/selinux/include").mkdir(parents=True)
        self.a=self.root/"security/selinux/ss/services.c"
        self.b=self.root/"security/selinux/include/security.h"
        self.a.write_text("int security_load_policy(struct selinux_state *state, void *data, size_t len)\n{}\n"
                          "size_t security_policydb_len(struct selinux_state *state) {}\n")
        self.b.write_text("int security_load_policy(struct selinux_state *state,\n void *data, size_t len);\n")
    def test_patch_idempotent(self):
        self.assertTrue(mod.patch(self.root))
        c,d=self.a.read_text(),self.b.read_text()
        self.assertIn(mod.MARKER,c)
        self.assertIn("ksu_legacy_policy_transaction",c)
        self.assertIn("policydb_destroy(candidate)",c)
        self.assertIn("mutex_lock(&ksu_legacy_policy_mutex)",c)
        self.assertIn("ksu_legacy_policy_transaction",d)
        self.assertFalse(mod.patch(self.root))
        self.assertEqual(c,self.a.read_text())
    def test_upstream_drift_doesnt_edit(self):
        self.b.write_text("missing\n")
        first=self.a.read_text()
        with self.assertRaises(ValueError):mod.patch(self.root)
        self.assertEqual(first,self.a.read_text())
