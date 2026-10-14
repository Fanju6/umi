import importlib.util
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location("sulog_419",Path(__file__).resolve().parents[1]/"scripts/patch_sulog_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestSulogCompat(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/"sulog").mkdir()
        (self.root/"Kbuild").write_text("# kbuild\n")
        self.src=self.root/"sulog/event.c"
        self.src.write_text("#include <asm/current.h>\n#include <linux/minmax.h>\n")

    def test_idempotence_and_preserve_modern_include(self):
        self.assertTrue(mod.patch(self.root))
        content=self.src.read_text()
        self.assertIn(mod.MARKER,content)
        self.assertIn("#include <linux/kernel.h>",content)
        self.assertIn("#else\n#include <linux/minmax.h>",content)
        self.assertFalse(mod.patch(self.root))
        self.assertEqual(content,self.src.read_text())

    def test_fail_closed(self):
        original="#include <asm/current.h>\n#include <linux/other.h>\n"
        self.src.write_text(original)
        with self.assertRaises(ValueError):
            mod.patch(self.root)
        self.assertEqual(original,self.src.read_text())
