"""Umi arm64 4.19 block-mapping walker regression tests."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("block_walk", ROOT / "scripts/patch_arm64_block_walk_419.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Arm64BlockWalkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.joinpath("Kbuild").write_text("obj-y += hook/\n")
        self.src = self.root / "hook/arm64/patch_memory.c"
        self.src.parent.mkdir(parents=True)
        self.src.write_text(
            mod.INCLUDE_ANCHOR + "\n"
            + "void *walk(unsigned long addr) {\n"
            + mod.OLD_PUD + "\n"
            + mod.OLD_PMD + "\n}\n"
        )

    def test_legacy_sect_before_bad_and_idempotence(self):
        self.assertTrue(mod.patch(self.root))
        s = self.src.read_text()
        self.assertIn("if (pud_sect(*pud))", s)
        self.assertIn("if (pmd_sect(*pmd))", s)
        self.assertLess(s.index("if (pud_sect(*pud))"), s.index("if (pud_bad(*pud))"))
        # Original pmd_bad check comes after the new explicit PMD block branch.
        self.assertLess(s.index("if (pmd_sect(*pmd))"), s.index("if (pmd_none(*pmd) || pmd_bad(*pmd))"))
        self.assertIn("__pud_to_phys(*pud) + (addr & ~PUD_MASK)", s)
        self.assertIn("__pmd_to_phys(*pmd) + (addr & ~PMD_MASK)", s)
        self.assertFalse(mod.patch(self.root))
        self.assertEqual(s, self.src.read_text())

    def test_source_drift_rejected_without_edit(self):
        s = self.src.read_text().replace("pud_none(*pud) || pud_bad(*pud)", "pud_none(*pud)")
        self.src.write_text(s)
        with self.assertRaises(ValueError):
            mod.patch(self.root)
        self.assertEqual(s, self.src.read_text())

    def test_partial_previous_patch_rejected(self):
        self.src.write_text(mod.MARKER)
        with self.assertRaises(ValueError):
            mod.patch(self.root)

    def test_unknown_root_rejected(self):
        with self.assertRaises(ValueError):
            mod.patch(self.root / "missing")
