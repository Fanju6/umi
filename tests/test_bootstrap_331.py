import importlib.util
import tempfile
import unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location("bootstrap_331", Path(__file__).resolve().parents[1] / "scripts/inspect_bootstrap_331.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class AuditFirstInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.kernel = Path(self.tmp.name) / "kernel"
        self.ksu = Path(self.tmp.name) / "ksu"
        data = {
            (self.ksu, mod.MAIN): "Natives.kernelUAPIVersion == Natives.managerUAPIVersion; install()",
            (self.ksu, mod.CLI): 'libksud.so; "debug", "su"',
            (self.ksu, mod.CALLS): "libc::SYS_reboot KSU_INSTALL_MAGIC1 KSU_INSTALL_MAGIC2 KernelSU driver install syscall was blocked by seccomp",
            (self.ksu, mod.SETUID): "ksu_install_fd();",
            (self.ksu, mod.SUPERCALL): "ksu_install_fd_with_permissions(O_CLOEXEC, 0)",
            (self.ksu, mod.KSUD_H): '#define KSUD_PATH "/data/adb/ksud"',
            (self.ksu, mod.SHIM): "UMI_KSU_419_NO_ACTION_CACHE void ksu_seccomp_allow_cache",
            (self.kernel, mod.PTRACE): "secure_computing(NULL); trace_sys_enter(regs, regs->syscallno);",
        }
        for (root, rel), value in data.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value)

    def test_does_not_claim_bootstrap_success(self):
        report = mod.inspect(self.kernel, self.ksu)
        self.assertTrue(report["source_contract_passed"])
        self.assertFalse(report["first_install_without_debugging_verified"])
        self.assertTrue(report["release_blocked_for_first_install"])

    def test_missing_root_bootstrap_path_detected(self):
        p = self.ksu / mod.CALLS
        p.write_text("some new upstream API")
        report = mod.inspect(self.kernel, self.ksu)
        self.assertFalse(report["source_contract_passed"])
        self.assertFalse(report["upstream_contract_checks"]["ksud_reboot_magic_fallback_exists"])

    def test_seccomp_order_reversal_detected(self):
        p = self.kernel / mod.PTRACE
        p.write_text("trace_sys_enter(regs, regs->syscallno); secure_computing(NULL);")
        self.assertFalse(mod.inspect(self.kernel, self.ksu)["source_contract_passed"])
