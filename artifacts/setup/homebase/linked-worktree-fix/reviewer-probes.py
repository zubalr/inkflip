import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path.cwd() / 'tests/coordination'))
import test_homebase_relay as t

class GuardReview(t.RelayTests):
    def test_both_operations_fail_closed(self):
        before = (self.refs(self.origin), self.refs(self.homebase))
        for role, root, message in [('worker', self.mac, 'integrator'), ('integrator', self.worker, 'canonical')]:
            self.run_git(self.mac, 'config', 'inkflip.role', role)
            with patch.dict(self.settings, {'canonical_root': str(root)}):
                for operation in (t.relay.publish, lambda: t.relay.collect('T27')):
                    with self.assertRaisesRegex(ValueError, message):
                        operation()
        self.assertEqual((self.refs(self.origin), self.refs(self.homebase)), before)

suite = unittest.TestSuite([GuardReview('test_both_operations_fail_closed'), t.RelayTests('test_real_linked_checkout_is_rejected_with_matching_config')])
result = unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful()
# Restore only the old function behavior in memory; source files remain unchanged.
def old_canonical_root():
    common = Path(t.relay.c.run(['git', 'rev-parse', '--git-common-dir']))
    return (t.relay.c.ROOT / common).resolve().parent
with patch.object(t.relay.c, 'canonical_root', old_canonical_root):
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([t.RelayTests('test_real_linked_checkout_is_rejected_with_matching_config')]))
assert len(result.failures) == 1 and not result.errors, 'Regression must fail against old implementation'
print('EXPECTED_MUTATION_FAILURE_CONFIRMED: new regression detects old canonical_root')
