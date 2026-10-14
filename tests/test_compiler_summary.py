import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location("ci_errors",Path(__file__).resolve().parents[1]/"scripts/summarize_compiler_errors.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestSummary(unittest.TestCase):
    def test_clang_and_duplicates(self):
        src = ("/tmp/k/drivers/kernelsu/selinux/rules.c:12:3: error: member missing\n" * 2
               + "/tmp/k/drivers/kernelsu/selinux/sepolicy.c:3:1: fatal error: missing.h\n")
        out=mod.summarize(src)
        self.assertIn("rules.c",out)
        self.assertIn("2 次",out)
        self.assertIn("missing.h",out)

    def test_empty(self):
        self.assertIn("No Clang errors",mod.summarize("make: error 2\n"))
