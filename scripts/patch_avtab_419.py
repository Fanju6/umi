#!/usr/bin/env python3
"""Fail-closed Linux 4.19 avtab remove adapter for KernelSU v3.3.0.

The old kernel stores bucket heads in struct flex_array, and its avtab
nodes are allocated from private slab caches, never to be freed via kfree().
"""
import argparse
from pathlib import Path

MARKER = "UMI_KSU_419_AVTAB_FLEX_ARRAY"
LEGACY = """static bool remove_avtab_node(struct policydb *db, struct avtab_node *node)
{
    struct avtab removed = {};
    struct avtab_node *n, *prev;
    struct avtab_node *empty = NULL;
    size_t shrink_size = sizeof(struct avtab_key) + sizeof(struct avtab_datum);
    int i, ret;

    /* Ensure temporary bucket storage is allocated before touching the tree. */
    ret = avtab_alloc(&removed, 1);
    if (ret)
        return false;
    ret = flex_array_prealloc(removed.htable, 0, 1, GFP_KERNEL | __GFP_ZERO);
    if (ret)
        goto out;

    for (i = 0; i < db->te_avtab.nslot; i++) {
        prev = NULL;
        for (n = flex_array_get_ptr(db->te_avtab.htable, i);
             n; prev = n, n = n->next) {
            if (n != node)
                continue;

            /* Temporary avtab owns this node only after successful unlink. */
            ret = flex_array_put_ptr(removed.htable, 0, n, GFP_KERNEL);
            if (ret)
                goto out;
            if (prev) {
                prev->next = n->next;
            } else {
                struct avtab_node *next = n->next;
                ret = flex_array_put_ptr(db->te_avtab.htable, i, next, GFP_KERNEL);
                if (ret) {
                    flex_array_put_ptr(removed.htable, 0, empty, GFP_KERNEL);
                    goto out;
                }
            }

            if ((n->key.specified & AVTAB_XPERMS) && n->datum.u.xperms)
                shrink_size += sizeof(u8) + sizeof(u8) +
                               sizeof(u32) * ARRAY_SIZE(n->datum.u.xperms->perms.p);
            n->next = NULL;
            removed.nel = 1;
            if (db->te_avtab.nel)
                db->te_avtab.nel--;
            if (db->len >= shrink_size)
                db->len -= shrink_size;

            /* Must use old avtab slab-destructor, not kfree(node). */
            avtab_destroy(&removed);
            return true;
        }
    }
out:
    avtab_destroy(&removed);
    return false;
}

"""

def patch(ksu: Path) -> bool:
    root = ksu / "kernel" if (ksu / "kernel/Kbuild").is_file() else ksu
    if not (root / "Kbuild").is_file():
        raise ValueError("Expected pinned official KernelSU checkout")
    path = root / "selinux/sepolicy.c"
    original = path.read_text()
    if MARKER in original:
        return False
    marker = 'static bool remove_avtab_node(struct policydb *db, struct avtab_node *node)\n{'
    start = original.find(marker)
    end = original.find('static bool add_rule(', start)
    if start < 0 or end <= start:
        raise ValueError("Unrecognized upstream remove_avtab_node definition")
    modern = original[start:end]
    if not all(x in modern for x in (
        'db->te_avtab.htable[i]',
        'removed.htable[0] = n',
        'avtab_destroy(&removed);',
    )):
        raise ValueError("Unexpected upstream AVTAB internals")
    prefix = '/* ' + MARKER + ' */\n#include <linux/flex_array.h>\n'
    if original.count('#include "ss/avtab.h"') != 1:
        raise ValueError("Unexpected upstream avtab header")
    modified = original[:start] + (
        '#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 0, 0)\n' +
        LEGACY + '#else\n' + modern + '#endif\n\n'
    ) + original[end:]
    modified = modified.replace('#include "ss/avtab.h"',
                                prefix + '#include "ss/avtab.h"', 1)
    if path.read_text() != original:
        raise RuntimeError("Source changed during patch")
    path.write_text(modified)
    return True

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernelsu", type=Path)
    args = p.parse_args()
    print("[AVTAB-419] " + ("applied" if patch(args.kernelsu.resolve()) else "already applied"))
