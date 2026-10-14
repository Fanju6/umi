#!/usr/bin/env python3
"""Support Linux 4.19 flex_array type maps in pinned official KernelSU v3.3.0.

Build-time adapter only: safe policy publication, SID lifecycle and Manager
authorization remain independent release blockers.
"""
import argparse
from pathlib import Path

MARKER = "UMI_KSU_419_TYPE_FLEX_ARRAY"
OLD = r"""static bool add_type(struct policydb *db, const char *type_name, bool attr)
{
    struct type_datum *type;
    struct flex_array *new_attr = NULL, *new_types = NULL, *new_names = NULL;
    struct flex_array *old_attr, *old_types, *old_names;
    struct ebitmap *self_map = NULL;
    char *key = NULL;
    u32 value;
    int j, ret;

    if (symtab_search(&db->p_types, type_name))
        return true;

    value = db->p_types.nprim + 1;
    type = kzalloc(sizeof(*type), GFP_KERNEL);
    if (!type)
        return false;
    key = kstrdup(type_name, GFP_KERNEL);
    if (!key)
        goto fail;
    type->primary = 1;
    type->value = value;
    type->attribute = attr;

    /*
     * Linux 4.19 policydb keeps these as flex_array containers, not raw
     * pointer/ebitmap arrays. All new allocations and copies must succeed
     * before publishing the new maps into db.
     */
    new_attr = flex_array_alloc(sizeof(struct ebitmap), value, GFP_KERNEL | __GFP_ZERO);
    new_types = flex_array_alloc(sizeof(struct type_datum *), value, GFP_KERNEL | __GFP_ZERO);
    new_names = flex_array_alloc(sizeof(char *), value, GFP_KERNEL | __GFP_ZERO);
    if (!new_attr || !new_types || !new_names)
        goto fail;
    if (flex_array_prealloc(new_attr, 0, value, GFP_KERNEL | __GFP_ZERO) ||
        flex_array_prealloc(new_types, 0, value, GFP_KERNEL | __GFP_ZERO) ||
        flex_array_prealloc(new_names, 0, value, GFP_KERNEL | __GFP_ZERO))
        goto fail;

    for (j = 0; j < value - 1; j++) {
        struct ebitmap *old_map = flex_array_get(db->type_attr_map_array, j);
        struct type_datum *old_type = flex_array_get_ptr(db->type_val_to_struct_array, j);
        char *old_name = flex_array_get_ptr(db->sym_val_to_name[SYM_TYPES], j);
        if (old_map && flex_array_put(new_attr, j, old_map, GFP_KERNEL))
            goto fail;
        if (old_type && flex_array_put_ptr(new_types, j, old_type, GFP_KERNEL))
            goto fail;
        if (old_name && flex_array_put_ptr(new_names, j, old_name, GFP_KERNEL))
            goto fail;
    }

    self_map = flex_array_get(new_attr, value - 1);
    if (!self_map)
        goto fail;
    ebitmap_init(self_map);
    if (ebitmap_set_bit(self_map, value - 1, 1))
        goto fail;

    if (flex_array_put_ptr(new_types, value - 1, type, GFP_KERNEL) ||
        flex_array_put_ptr(new_names, value - 1, key, GFP_KERNEL))
        goto fail;

    /* Insertion happens after all fallible allocations above. */
    ret = symtab_insert(&db->p_types, key, type);
    if (ret)
        goto fail;

    old_attr = db->type_attr_map_array;
    old_types = db->type_val_to_struct_array;
    old_names = db->sym_val_to_name[SYM_TYPES];
    db->type_attr_map_array = new_attr;
    db->type_val_to_struct_array = new_types;
    db->sym_val_to_name[SYM_TYPES] = new_names;
    db->p_types.nprim = value;
    flex_array_free(old_attr);
    flex_array_free(old_types);
    flex_array_free(old_names);

    for (j = 0; j < db->p_roles.nprim; ++j) {
        if (ebitmap_set_bit(&db->role_val_to_struct[j]->types, value - 1, 1))
            pr_warn("KernelSU: could not extend role type bitmap\n");
    }
    return true;

fail:
    /* Only this new entry's bitmap is owned by the candidate flex_array. */
    if (self_map)
        ebitmap_destroy(self_map);
    if (new_attr)
        flex_array_free(new_attr);
    if (new_types)
        flex_array_free(new_types);
    if (new_names)
        flex_array_free(new_names);
    kfree(key);
    kfree(type);
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
    start = original.find("static bool add_type(struct policydb *db, const char *type_name, bool attr)\n{")
    end = original.find("static bool set_type_state(", start)
    if start < 0 or end <= start:
        raise ValueError("Unrecognized upstream add_type implementation")
    modern = original[start:end]
    if not all(k in modern for k in
               ("ksu_kvrealloc(db->type_attr_map_array",
                "db->type_val_to_struct = new_type_val_to_struct",
                "db->sym_val_to_name[SYM_TYPES] = new_val_to_name_types")):
        raise ValueError("Unsupported upstream type arrays")
    source = original[:start] + (
        "/* " + MARKER + " */\n"
        "#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)\n"
        + OLD + "#else\n" + modern + "#endif\n\n"
    ) + original[end:]

    old_lookup = "    struct ebitmap *sattr = &db->type_attr_map_array[type->value - 1];"
    if source.count(old_lookup) != 1:
        raise ValueError("Cannot identify type attribute lookup")
    source = source.replace(old_lookup,
        "#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)\n"
        "    struct ebitmap *sattr = flex_array_get(db->type_attr_map_array, type->value - 1);\n"
        "#else\n"
        + old_lookup + "\n"
        "#endif\n"
        "    if (!sattr) {\n"
        '        pr_err("KernelSU: type attribute map unavailable\\n");\n'
        "        return;\n"
        "    }", 1)
    if path.read_text(encoding="utf-8") != original:
        raise RuntimeError("Upstream source was modified during patching")
    path.write_text(source, encoding="utf-8")
    return True

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernelsu", type=Path)
    args = p.parse_args()
    print("[TYPE-419] " + ("patched" if patch(args.kernelsu.resolve()) else "already patched"))
