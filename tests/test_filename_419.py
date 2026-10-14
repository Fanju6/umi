import importlib.util
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("filename419",Path(__file__).resolve().parents[1]/"scripts/patch_filename_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SRC = """static bool add_filename_trans(struct policydb *db, const char *s, const char *t, const char *c, const char *d,
                               const char *o);
static bool add_filename_trans(struct policydb *db, const char *s, const char *t, const char *c, const char *d,
                               const char *o)
{
    struct filename_trans_key key;
    policydb_filenametr_search(db, &key);
    db->compat_filename_trans_count++;
}
static bool add_genfscon(struct policydb *db) {return false;}
"""

class TestFilename419(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/"selinux").mkdir()
        (self.root/"Kbuild").write_text("# kbuild\n")
        self.path=self.root/"selinux/sepolicy.c"
        self.path.write_text(SRC)
    def test_idempotent(self):
        self.assertTrue(mod.patch(self.root))
        content=self.path.read_text()
        self.assertIn(mod.MARKER,content)
        self.assertIn("struct filename_trans key",content)
        self.assertIn("hashtab_search(db->filename_trans",content)
        self.assertIn("db->filename_trans_ttypes",content)
        self.assertFalse(mod.patch(self.root))
        self.assertEqual(content,self.path.read_text())
    def test_unexpected_source_refused(self):
        drifted=SRC.replace("db->compat_filename_trans_count++","incompatible++;")
        self.path.write_text(drifted)
        with self.assertRaises(ValueError): mod.patch(self.root)
        self.assertEqual(drifted,self.path.read_text())
