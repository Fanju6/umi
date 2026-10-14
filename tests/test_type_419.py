import importlib.util
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("type419",Path(__file__).resolve().parents[1]/"scripts/patch_type_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SRC = """static bool add_type(struct policydb *db, const char *type_name, bool attr);
static bool add_type(struct policydb *db, const char *type_name, bool attr)
{
    struct ebitmap *new_type_attr_map_array =
        ksu_kvrealloc(db->type_attr_map_array, 10, 9);
    db->type_val_to_struct = new_type_val_to_struct;
    db->sym_val_to_name[SYM_TYPES] = new_val_to_name_types;
}
static bool set_type_state(struct policydb *db, const char *type_name, bool permissive) {}
static void add_typeattribute_raw(struct policydb *db, struct type_datum *type, struct type_datum *attr)
{
    struct ebitmap *sattr = &db->type_attr_map_array[type->value - 1];
}
"""

class TestType419(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/"selinux").mkdir()
        (self.root/"Kbuild").write_text("# kbuild\n")
        self.file=self.root/"selinux/sepolicy.c"
        self.file.write_text(SRC)
    def test_apply_twice(self):
        self.assertTrue(mod.patch(self.root))
        source=self.file.read_text()
        self.assertIn(mod.MARKER,source)
        self.assertIn("flex_array_prealloc(new_types",source)
        self.assertIn("flex_array_get(db->type_attr_map_array",source)
        self.assertIn("ebitmap_destroy(self_map)",source)
        self.assertFalse(mod.patch(self.root))
        self.assertEqual(source,self.file.read_text())
    def test_upstream_drift_fails_atomically(self):
        changed=SRC.replace("db->type_val_to_struct = new_type_val_to_struct","incompatible = true;")
        self.file.write_text(changed)
        with self.assertRaises(ValueError):
            mod.patch(self.root)
        self.assertEqual(changed,self.file.read_text())
