"""Source shim tests using minimal pinned-upstream-shaped fixtures."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply_compat.py"
spec = importlib.util.spec_from_file_location("umi_compat", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CompatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "KernelSU" / "kernel"
        (self.root / "infra").mkdir(parents=True)
        (self.root / "core").mkdir()
        (self.root / "Kbuild").write_text("obj-$(CONFIG_KSU) += kernelsu.o\n")
        self.sec = self.root / "infra/seccomp_cache.c"
        self.sec.write_text("""#include <linux/version.h>
struct action_cache { int fake; };
struct seccomp_filter { struct action_cache cache; };
void ksu_seccomp_clear_cache(struct seccomp_filter *filter, int nr) {}
void ksu_seccomp_allow_cache(struct seccomp_filter *filter, int nr)
{
    filter->cache.allow_native;
}
""")
        self.init = self.root / "core/init.c"
        self.init.write_text("#include <linux/module.h>\n" + module.IMPORT_OLD + "\n")

    def test_legacy_4_19_shims_are_idempotent(self):
        self.assertEqual(len(module.apply(self.root.parent)), 2)
        sec1 = self.sec.read_text()
        init1 = self.init.read_text()
        self.assertIn(module.LEGACY_MARKER, sec1)
        self.assertIn("KERNEL_VERSION(5, 9, 0)", sec1)
        self.assertIn("#else\n#include <linux/version.h>", sec1)
        self.assertIn(module.NAMESPACE_MARKER, init1)
        self.assertIn("#ifdef MODULE_IMPORT_NS", init1)
        self.assertEqual(module.apply(self.root.parent), [])
        self.assertEqual(self.sec.read_text(), sec1)
        self.assertEqual(self.init.read_text(), init1)

    def test_unknown_upstream_is_rejected(self):
        self.sec.write_text("/* unexpected upstream */\n")
        with self.assertRaises(ValueError):
            module.apply(self.root.parent)


if __name__ == "__main__":
    unittest.main()
