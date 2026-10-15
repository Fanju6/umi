import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v331_artifact', ROOT / 'scripts/verify_v331_artifact.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VerifyV331ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.archive = Path(self.tmp.name) / 'artifact.zip'
        self.image = b'A' * 1024
        self.sha = hashlib.sha256(self.image).hexdigest()
        self.commit = 'a' * 40
        self.report = dict(repack_structurally_verified=True,
                           checks={f'check_{i}': True for i in range(16)},
                           experimental_only=True, safe_to_flash=False, runtime_validated=False,
                           experimental_image_size_bytes=134217728, experimental_boot_sha256=self.sha,
                           experimental_kernel_sha256='b' * 64)
        self.provenance = ('PROVENANCE_COMMIT=' + self.commit + '\nSTOCK_ROM=' + module.ROM +
                           '\nKERNELSU_TAG=v3.3.1\nMANAGER_FD_EXPERIMENT=post_exec_task_work_419\n' +
                           'V331_KERNEL_IMAGE_SHA256=' + 'b' * 64 + '\n')
        self.make_zip()

    def make_zip(self, changes=None):
        entries = {
            module.IMAGE: self.image,
            'experimental-boot-verification.json': json.dumps(self.report).encode(),
            'experimental-boot.sha256': (self.sha + '  ' + module.IMAGE + '\n').encode(),
            'experimental-avb.txt': b'Algorithm:                NONE\nPartition Name:        boot\n',
            'stock-avb.txt': b'Algorithm:                NONE\nPartition Name:        boot\n',
            'experimental-WARNING.txt': b'NEVER auto-flash; NEVER claim stable',
            'experimental-PROVENANCE.txt': self.provenance.encode(),
        }
        entries.update(changes or {})
        with zipfile.ZipFile(self.archive, 'w') as z:
            for k, v in entries.items():
                z.writestr(k, v)

    def test_synthetic_image_size_rejected(self):
        with self.assertRaisesRegex(ValueError, '镜像大小异常'):
            module.inspect(self.archive, self.commit)

    def test_tampered_image_rejected(self):
        self.make_zip({module.IMAGE: b'X' * 1024})
        with self.assertRaises(ValueError):
            module.inspect(self.archive, self.commit)

    def test_wrong_commit_rejected(self):
        with self.assertRaisesRegex(ValueError, 'commit SHA 不匹配'):
            module.inspect(self.archive, 'b' * 40)

    def test_runtime_claim_rejected(self):
        self.report['safe_to_flash'] = True
        self.make_zip()
        with self.assertRaisesRegex(ValueError, '安全标记'):
            module.inspect(self.archive, self.commit)

    def test_unexpected_image_rejected(self):
        self.make_zip({'extra-boot.img': b'abc'})
        with self.assertRaisesRegex(ValueError, '文件列表异常'):
            module.inspect(self.archive, self.commit)

    def test_mixed_ksu_versions_rejected(self):
        self.provenance = self.provenance.replace('KERNELSU_TAG=v3.3.1', 'KERNELSU_TAG=v3.3.0')
        self.make_zip()
        with self.assertRaisesRegex(ValueError, 'ROM、KernelSU'):
            module.inspect(self.archive, self.commit)
