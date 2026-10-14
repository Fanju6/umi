import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("avtab419",Path(__file__).resolve().parents[1]/"scripts/patch_avtab_419.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SRC = """#include "ss/avtab.h"
static bool remove_avtab_node(struct policydb *db, struct avtab_node *node);
static bool remove_avtab_node(struct policydb *db, struct avtab_node *node)
{
    db->te_avtab.htable[i] = n;
    removed.htable[0] = n;
    avtab_destroy(&removed);
}
static bool add_rule(struct policydb *db) {return false;}
"""

class TestAvtab419(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ksu=Path(self.tmp.name)
        (self.ksu/"selinux").mkdir()
        (self.ksu/"Kbuild").write_text("# kbuild\n")
        self.p=self.ksu/"selinux/sepolicy.c"
        self.p.write_text(SRC)

    def test_idempotent(self):
        self.assertTrue(mod.patch(self.ksu))
        first=self.p.read_text()
        self.assertIn(mod.MARKER, first)
        self.assertIn("flex_array_get_ptr(db->te_avtab.htable", first)
        self.assertIn("avtab_destroy(&removed)", first)
        self.assertIn("struct avtab_node *empty = NULL", first)
        self.assertFalse(mod.patch(self.ksu))
        self.assertEqual(first, self.p.read_text())

    def test_unknown_upstream_rejected_without_changes(self):
        src=SRC.replace("removed.htable[0] = n;", "changed = 1;")
        self.p.write_text(src)
        with self.assertRaises(ValueError):
            mod.patch(self.ksu)
        self.assertEqual(src,self.p.read_text())
