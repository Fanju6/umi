"""文档相对链接守卫的回归测试。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("docs_links", ROOT / "scripts/check_doc_links.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class DocumentLinksTests(unittest.TestCase):
    def test_valid_local_link(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "README.md").write_text("[文档](docs/STATUS.md)", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs/STATUS.md").write_text("# Status", encoding="utf-8")
            count, errors = MOD.check(root, ("README.md",))
            self.assertEqual((count, errors), (1, []))

    def test_missing_link_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "README.md").write_text("[不存在](docs/missing.md)", encoding="utf-8")
            count, errors = MOD.check(root, ("README.md",))
            self.assertEqual(count, 1)
            self.assertEqual(len(errors), 1)

    def test_skip_external_and_anchor(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "README.md").write_text(
                "[网址](https://example.com) [内部](#section)", encoding="utf-8"
            )
            self.assertEqual(MOD.check(root, ("README.md",)), (0, []))

    def test_reject_path_escape(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "README.md").write_text("[逃逸](../no.md)", encoding="utf-8")
            _, errors = MOD.check(root, ("README.md",))
            self.assertTrue(any("越出仓库" in x for x in errors))
