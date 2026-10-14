import importlib.util
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location("rules419",Path(__file__).resolve().parents[1]/"scripts/patch_rules_419.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
RULES="""void apply_kernelsu_rules()
{
    struct selinux_policy *pol, *old_pol = selinux_state.policy;
    mutex_lock(&selinux_state.policy_mutex);
    struct policydb *db = &pol->policydb;
    ksu_type(db, KERNEL_SU_DOMAIN, "domain");
    ksu_type(db, KERNEL_SU_FILE, "file_type");
    ksu_allow(db, KERNEL_SU_DOMAIN, ALL, ALL, ALL);
    rcu_assign_pointer(selinux_state.policy, pol);
    reset_avc_cache();
    mutex_unlock(&selinux_state.policy_mutex);
}
#define KSU_SEPOLICY_MAX_BATCH_SIZE (8U * 1024U * 1024U)
int handle_sepolicy(void __user *user_data, u64 data_len)
{
    rcu_assign_pointer(selinux_state.policy, pol);
}
"""
class TestRules419(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for p in ["selinux","feature"]: (self.root/p).mkdir()
        (self.root/"Kbuild").write_text("# kbuild\n")
        self.rules=self.root/"selinux/rules.c"
        self.pol=self.root/"selinux/sepolicy.c"
        self.hide=self.root/"feature/selinux_hide.c"
        self.rules.write_text(RULES)
        self.pol.write_text("void ksu_destroy_sepolicy(struct selinux_policy *pol) { }\n")
        self.hide.write_text("#include <linux/cred.h>\n")
    def test_4_19_is_real_transaction_not_cast(self):
        self.assertTrue(mod.patch(self.root))
        content=self.rules.read_text()
        self.assertIn(mod.MARKER,content)
        self.assertIn("ksu_legacy_policy_transaction",content)
        self.assertIn("ksu_legacy_sepol_edit",content)
        # Failed rules must cancel the entire policydb candidate, not commit.
        failed_branch=mod.LEGACY_BATCH.split("ret = apply_one_sepolicy_cmd(db, &header, args);")[1].split("data->success_count++")[0]
        self.assertIn("if (ret)",failed_branch)
        self.assertIn("return ret;",failed_branch)
        self.assertIn("aborting transaction",failed_branch)
        self.assertIn(mod.MARKER_HIDE,self.hide.read_text())
        self.assertIn(mod.MARKER_SEPOL,self.pol.read_text())
        self.assertFalse(mod.patch(self.root))
    def test_drift_no_partial_edit(self):
        self.rules.write_text(RULES.replace("mutex_unlock(&selinux_state.policy_mutex)","broken();"))
        source=self.rules.read_text()
        with self.assertRaises(ValueError):mod.patch(self.root)
        self.assertEqual(source,self.rules.read_text())
        self.assertNotIn(mod.MARKER_SEPOL,self.pol.read_text())
