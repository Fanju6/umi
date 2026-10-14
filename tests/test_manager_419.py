import importlib.util
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("manager",Path(__file__).resolve().parents[1]/"scripts/inspect_manager_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.kernel=Path(self.tmp.name)/"linux"
        self.ksu=Path(self.tmp.name)/"KernelSU"
        (self.kernel/"arch/arm64/kernel").mkdir(parents=True)
        for p in ["hook","supercall","infra"]:(self.ksu/"kernel"/p).mkdir(parents=True)
        (self.ksu/"kernel/Kbuild").write_text("# kbuild\n")
        self.ent=self.kernel/"arch/arm64/kernel/ptrace.c"
        self.ent.write_text("int syscall_trace_enter(struct pt_regs *regs) {\n"
                            "secure_computing(NULL);\ntrace_sys_enter(regs, regs->syscallno);\n}\n"
                            "void syscall_trace_exit(void) {}\n")
        (self.ksu/"kernel/hook/setuid_hook.c").write_text("is_uid_manager(new_uid) ksu_install_fd();")
        (self.ksu/"kernel/supercall/supercall.c").write_text(
            "fd_install(fd, filp) reboot_handler_pre register_kprobe(&reboot_kp)"
        )
        (self.ksu/"kernel/infra/seccomp_cache.c").write_text(
            "UMI_KSU_419_NO_ACTION_CACHE\nvoid ksu_seccomp_allow_cache(void)"
        )
    def test_detect_order_and_never_claim_runtime_success(self):
        report=mod.inspect(self.kernel,self.ksu)
        self.assertTrue(report["seccomp_before_sys_enter"])
        self.assertTrue(report["manager_fd_injection_source_present"])
        self.assertTrue(report["block_release"])
        self.assertFalse(report["manager_runtime_verified"])
    def test_changed_order_fails_guard(self):
        self.ent.write_text(self.ent.read_text().replace(
            "secure_computing(NULL);\ntrace_sys_enter(regs, regs->syscallno);",
            "trace_sys_enter(regs, regs->syscallno);\nsecure_computing(NULL);"))
        self.assertFalse(mod.inspect(self.kernel,self.ksu)["kernel_entry_verified"])
