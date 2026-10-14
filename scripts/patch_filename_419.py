#!/usr/bin/env python3
"""Port KernelSU filename transitions to Linux 4.19 policydb representation.

Old policydb uses struct filename_trans (including stype) and a hashtab
pointer, not the new filename_trans_key and list of stypes.
"""
import argparse
from pathlib import Path

MARKER = "UMI_KSU_419_FILENAME_TRANS"
SIGNATURE = ("static bool add_filename_trans(struct policydb *db, const char *s, const char *t, const char *c, const char *d,\n"
             "                               const char *o)\n{")

OLD = """static bool add_filename_trans(struct policydb *db, const char *s, const char *t, const char *c,
                               const char *d, const char *o)
{
    struct type_datum *src, *tgt, *def;
    struct class_datum *cls;
    struct filename_trans key, *new_key;
    struct filename_trans_datum *trans;
    int rc;

    if (!s || !t || !c || !d || !o)
        return false;
    src = symtab_search(&db->p_types, s);
    tgt = symtab_search(&db->p_types, t);
    cls = symtab_search(&db->p_classes, c);
    def = symtab_search(&db->p_types, d);
    if (!src || !tgt || !cls || !def)
        return false;

    key.stype = src->value;
    key.ttype = tgt->value;
    key.tclass = cls->value;
    key.name = o;
    trans = hashtab_search(db->filename_trans, &key);
    if (trans) {
        trans->otype = def->value;
        return ebitmap_set_bit(&db->filename_trans_ttypes,
                               src->value - 1, 1) == 0;
    }

    trans = kzalloc(sizeof(*trans), GFP_KERNEL);
    if (!trans)
        return false;
    new_key = kmemdup(&key, sizeof(key), GFP_KERNEL);
    if (!new_key)
        goto free_trans;
    new_key->name = kstrdup(o, GFP_KERNEL);
    if (!new_key->name)
        goto free_key;
    trans->otype = def->value;
    rc = hashtab_insert(db->filename_trans, new_key, trans);
    if (rc)
        goto free_name;
    /* Linux 4.19 records all source types in the global ttypes bitmap. */
    return ebitmap_set_bit(&db->filename_trans_ttypes,
                           src->value - 1, 1) == 0;

free_name:
    kfree(new_key->name);
free_key:
    kfree(new_key);
free_trans:
    kfree(trans);
    return false;
}

"""

def patch(ksu: Path) -> bool:
    root = ksu / "kernel" if (ksu / "kernel/Kbuild").is_file() else ksu
    if not (root / "Kbuild").is_file():
        raise ValueError("Expected official KernelSU checkout")
    path = root / "selinux/sepolicy.c"
    original = path.read_text(encoding="utf-8")
    if MARKER in original:
        return False
    start = original.find(SIGNATURE)
    end = original.find("static bool add_genfscon(", start)
    if start < 0 or end <= start:
        raise ValueError("Unknown upstream filename transition function")
    modern = original[start:end]
    if not all(x in modern for x in
               ("policydb_filenametr_search(db, &key)",
                "db->compat_filename_trans_count++",
                "struct filename_trans_key key;")):
        raise ValueError("Modern policy layout changed, cannot safely patch")
    result = original[:start] + ("/* " + MARKER + " */\n"
              "#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)\n"
              + OLD + "#else\n" + modern + "#endif\n\n") + original[end:]
    if path.read_text(encoding="utf-8") != original:
        raise RuntimeError("Source modified while patching")
    path.write_text(result, encoding="utf-8")
    return True

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernelsu",type=Path)
    args=p.parse_args()
    print("[FILENAME-419] " + ("patched" if patch(args.kernelsu.resolve()) else "already patched"))
