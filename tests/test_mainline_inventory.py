"""P0 高版本内核研究阶段的离线检查与安全门禁。"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mainline_inventory", ROOT / "scripts/mainline_inventory.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class MainlineInventoryTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "config/mainline-research.json").read_text(encoding="utf-8"))

    def test_checked_in_manifest_is_valid_and_nonflashable(self):
        audit.validate_manifest(self.data)
        self.assertFalse(self.data["safety"]["safe_to_flash"])
        self.assertFalse(self.data["safety"]["android_boot_verified"])
        self.assertEqual(set(self.data["sources"]), set(audit.SOURCE_KEYS))

    def test_all_github_pins_are_40_char_shas(self):
        for entry in self.data["sources"].values():
            self.assertRegex(entry["sha"], "^[0-9a-f]{40}$")

    def test_v612_has_umi_dts_absence_gate(self):
        ref = self.data["sources"]["mainline_612"]
        self.assertIn("arch/arm64/boot/dts/qcom/sm8250-xiaomi-umi.dts", ref["absent"])

    def test_dagu_is_never_a_direct_umi_board_source(self):
        self.assertIn("sm8250-xiaomi-dagu.dts", " ".join(self.data["sources"]["dagu_reference"]["required"]))
        self.assertNotEqual(self.data["sources"]["dagu_reference"]["sha"], self.data["sources"]["vendor_419"]["sha"])

    def test_missing_sources_marked_unverified(self):
        result, ok = audit.run(self.data, {})
        self.assertTrue(ok)
        self.assertEqual(result["sources"]["vendor_419"]["status"], "not_scanned")
        self.assertFalse(result["safe_to_flash"])

    def test_require_all_missing_sources_fails(self):
        result, ok = audit.run(self.data, {}, require_all=True)
        self.assertFalse(ok)
        self.assertEqual(result["sources"]["mainline_70"]["status"], "not_scanned")

    def test_reject_path_traversal(self):
        data = json.loads(json.dumps(self.data))
        data["sources"]["mainline_612"]["required"].append("../escape")
        with self.assertRaisesRegex(ValueError, "不安全"):
            audit.validate_manifest(data)

    def test_reject_safety_gate_override(self):
        data = json.loads(json.dumps(self.data))
        data["safety"]["safe_to_flash"] = True
        with self.assertRaisesRegex(ValueError, "禁止"):
            audit.validate_manifest(data)

    def test_reject_wrong_git_sha_before_reading_files(self):
        source = self.data["sources"]["mainline_612"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".git").mkdir()
            with patch.object(audit, "read_head", return_value="0" * 40):
                result = audit.inspect_tree(root, source)
            self.assertEqual(result["status"], "sha_mismatch")
            self.assertFalse(result["required_checked"])

    def test_matching_sha_requires_all_source_files(self):
        source = self.data["sources"]["mainline_612"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".git").mkdir()
            with patch.object(audit, "read_head", return_value=source["sha"]):
                result = audit.inspect_tree(root, source)
            self.assertEqual(result["status"], "file_matrix_mismatch")
            self.assertEqual(set(result["missing"]), set(source["required"]))

    def test_compatible_scan_source_only(self):
        source = {
            "sha": "a" * 40, "required": ["dts/board.dts"], "absent": ["dts/umi.dts"],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".git").mkdir()
            (root / "dts").mkdir()
            (root / "dts/board.dts").write_text(
                '/ { compatible = "qcom,sm8250", "demo,board"; };\n', encoding="utf-8"
            )
            with patch.object(audit, "read_head", return_value=source["sha"]):
                result = audit.inspect_tree(root, source)
            self.assertEqual(result["status"], "sources_present")
            self.assertIn("qcom,sm8250", result["compatible_strings"])
            self.assertFalse("test_passed" in result)

    def test_duplicate_source_rejected(self):
        with self.assertRaises(ValueError):
            audit.parse_root_args(["vendor_419=/tmp/a", "vendor_419=/tmp/b"])

    def test_invalid_version_source_rejected(self):
        with self.assertRaises(ValueError):
            audit.parse_root_args(["unsupported=/tmp/a"])
