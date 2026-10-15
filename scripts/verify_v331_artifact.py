#!/usr/bin/env python3
"""只读核查 umi KernelSU v3.3.1 Manager FD 实验版 Actions ZIP。"""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

IMAGE = '.work/experiment/umi-KernelSU3.3.1-20261004-MANAGERFD-UNVERIFIED-boot.img'
FILES = {IMAGE, 'experimental-boot-verification.json', 'experimental-boot.sha256',
         'experimental-avb.txt', 'stock-avb.txt',
         'experimental-WARNING.txt', 'experimental-PROVENANCE.txt'}
ROM = '23.2-20261004-NIGHTLY-umi'
HEX64 = re.compile(r'^[0-9a-f]{64}$')
HEX40 = re.compile(r'^[0-9a-f]{40}$')


def inspect(path: Path, expected_commit: str | None = None) -> dict:
    """只验证归档完整性与构建溯源，不判定真机可用或可刷。"""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or set(names) != FILES:
            raise ValueError('Actions ZIP 文件列表异常，拒绝验证')
        report = json.loads(z.read('experimental-boot-verification.json'))
        checks = report.get('checks')
        if (not report.get('repack_structurally_verified') or not isinstance(checks, dict)
                or len(checks) < 16 or not all(v is True for v in checks.values())):
            raise ValueError('boot 结构验证不完整')
        if (report.get('experimental_only') is not True
                or report.get('safe_to_flash') is not False
                or report.get('runtime_validated') is not False):
            raise ValueError('实验镜像安全标记被修改，拒绝验证')
        if report.get('experimental_image_size_bytes') != 134217728:
            raise ValueError('镜像分区长度不是预期的 128MiB')
        lines = z.read('experimental-boot.sha256').decode('utf-8').strip().splitlines()
        if len(lines) != 1:
            raise ValueError('镜像哈希行数量异常')
        expected_hash = report.get('experimental_boot_sha256')
        if not isinstance(expected_hash, str) or not HEX64.fullmatch(expected_hash):
            raise ValueError('缺失有效的镜像 SHA256')
        if lines[0] != expected_hash + '  ' + IMAGE:
            raise ValueError('sha256 文件与镜像路径、报告不一致')
        prov_lines = z.read('experimental-PROVENANCE.txt').decode('utf-8').splitlines()
        if any('=' not in line for line in prov_lines):
            raise ValueError('构建溯源字段错误')
        prov = dict(line.split('=', 1) for line in prov_lines)
        commit = prov.get('PROVENANCE_COMMIT', '')
        if not HEX40.fullmatch(commit) or (expected_commit is not None and commit != expected_commit):
            raise ValueError('构建 commit SHA 不匹配')
        if (prov.get('STOCK_ROM') != ROM or prov.get('KERNELSU_TAG') != 'v3.3.1'
                or prov.get('MANAGER_FD_EXPERIMENT') != 'post_exec_task_work_419'
                or prov.get('V331_KERNEL_IMAGE_SHA256') != report.get('experimental_kernel_sha256')):
            raise ValueError('ROM、KernelSU、实验版本或内核 SHA 不匹配')
        for suffix in ('stock-avb.txt', 'experimental-avb.txt'):
            avb = z.read(suffix).decode('utf-8')
            if 'Algorithm:                NONE' not in avb or 'Partition Name:        boot' not in avb:
                raise ValueError('AVB 元数据并非原验证的无签名哈希类型')
        warn = z.read('experimental-WARNING.txt').decode('utf-8')
        if 'NEVER auto-flash' not in warn or 'NEVER claim stable' not in warn:
            raise ValueError('实验警告缺失')
        info = z.getinfo(IMAGE)
        if info.file_size != 134217728:
            raise ValueError('归档中的镜像大小异常')
        h = hashlib.sha256()
        with z.open(IMAGE) as stream:
            while block := stream.read(1024 * 1024):
                h.update(block)
        if h.hexdigest() != expected_hash:
            raise ValueError('实际镜像与宣称 SHA256 不一致')
        return {'verified': True, 'commit': commit, 'image_sha256': expected_hash,
                'kernel_image_sha256': prov['V331_KERNEL_IMAGE_SHA256'],
                'offline_structure_passed': True, 'safe_to_flash': False,
                'runtime_validated': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('artifact_zip', type=Path)
    p.add_argument('--expect-commit', default=None)
    a = p.parse_args()
    print(json.dumps(inspect(a.artifact_zip, a.expect_commit), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
