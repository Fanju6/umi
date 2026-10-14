import importlib.util
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("selinux419",Path(__file__).resolve().parents[1]/"scripts/inspect_selinux_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
class TestLegacyPolicyAPI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.kernel=Path(self.temp.name)/"linux"
        self.ksu=Path(self.temp.name)/"ksu"
        for path in ("security/selinux/include","security/selinux/ss"):
            (self.kernel/path).mkdir(parents=True)
        (self.ksu/"kernel/selinux").mkdir(parents=True)
        (self.ksu/"kernel/Kbuild").write_text("# kbuild\n")
        (self.kernel/"security/selinux/include/security.h").write_text("struct selinux_ss *ss;")
        (self.kernel/"security/selinux/ss/services.h").write_text("policy_rwlock")
        (self.kernel/"security/selinux/ss/services.c").write_text(
            "int security_read_policy(struct selinux_state *state\n"
            "read_lock(&state->ss->policy_rwlock)\npolicydb_write(policydb, &fp)\n"
            "int security_load_policy(struct selinux_state *state\n"
            "write_lock_irq(&state->ss->policy_rwlock)\n"
            "sidtab_convert(oldsidtab, &convert_params)\n"
            "avc_ss_reset(state->avc, seqno)\n")
        (self.ksu/"kernel/selinux/rules.c").write_text("selinux_state.policy_mutex")
    def test_native_api_does_not_imply_root_ready(self):
        x=mod.inspect(self.kernel,self.ksu)
        self.assertEqual(x["native_api"],"FOUND")
        self.assertEqual(x["kernelsu_publisher"],"INCOMPATIBLE")
        self.assertFalse(x["publish_ready"])
    def test_missing_sid_conversion_blocks(self):
        f=self.kernel/"security/selinux/ss/services.c"
        f.write_text(f.read_text().replace("sidtab_convert(oldsidtab, &convert_params)",""))
        self.assertEqual(mod.inspect(self.kernel,self.ksu)["native_api"],"MISSING")
