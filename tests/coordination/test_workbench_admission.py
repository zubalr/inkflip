"""Independent queues retain prerequisite and ownership admission boundaries."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_pass as p


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.config = p.plan()

    def test_independent_task_uses_actual_stage_while_checkpoint_stays_open(self):
        self.assertEqual(p.current_pass(self.config, {})['id'], 1)
        self.assertEqual(p.admission_stage(self.config, {}, 'T30')['id'], 2)
        self.assertEqual(p.admission_stage(self.config, {}, 'T44')['id'], 3)
        self.assertEqual(p.current_pass(self.config, {})['id'], 1)

    def test_legacy_mode_and_invalid_modes_fail_closed(self):
        self.config.pop('admission_mode', None)
        self.assertEqual(p.admission_stage(self.config, {}, 'T30')['id'], 1)
        self.config['admission_mode'] = 'typo'
        with self.assertRaisesRegex(ValueError, 'admission mode'):
            p.admission_stage(self.config, {}, 'T30')

    def test_owner_release_and_ambiguous_stage_are_rejected(self):
        with self.assertRaises(ValueError):
            p.admission_stage(self.config, {}, 'T54')
        self.config['passes'][0]['tasks'].append('T30')
        with self.assertRaises(ValueError):
            p.admission_stage(self.config, {}, 'T30')

    def test_new_grants_identify_separate_devin_workbenches(self):
        for task, lane in [('T18', 'A'), ('T30', 'B'), ('T47', 'E')]:
            self.assertEqual(p.assignment(self.config, task, 'devin', 'a' * 40, 2)['workbench'], lane)

    def test_filtered_inboxes_preserve_exact_saved_grants(self):
        issues = {}
        for task, lane in [('T18', None), ('T30', 'B'), ('T47', 'E')]:
            grant = {'app': 'devin', 'base': 'b' * 40, 'branch': 'work/devin/' + task.lower(), 'pass': 1}
            if lane:
                grant['workbench'] = lane
            issues[p.c.bead_id(task)] = {'status': 'in_progress', 'metadata': {'execution': grant}}
        before = json.dumps(issues, sort_keys=True)
        with patch.object(p.c, 'admission_lock'), patch.object(p.c, 'issues_by_id', return_value=issues):
            for lane, task in [('A', 'T18'), ('B', 'T30'), ('E', 'T47')]:
                with redirect_stdout(StringIO()) as output:
                    p.status('devin', False, lane)
                assignments = json.loads(output.getvalue())['assignments']
                self.assertEqual([x['task'] for x in assignments], [task])
                self.assertEqual(assignments[0]['base'], 'b' * 40)
                self.assertEqual(assignments[0]['branch'], 'work/devin/' + task.lower())
        self.assertEqual(before, json.dumps(issues, sort_keys=True))

    def test_wrong_app_cannot_read_another_workbench_inbox(self):
        with self.assertRaisesRegex(ValueError, 'workbench'):
            p.status('zcode', False, 'B')

    def test_future_dispatch_checks_fresh_prerequisites_before_claim(self):
        issues = {'pdf-t19': {'status': 'open'}}
        def git(argv):
            if argv[1:3] == ['config', '--get']:
                return 'integrator'
            if argv[1:3] == ['branch', '--show-current']:
                return 'main'
            return 'a' * 40 if argv[1] == 'rev-parse' else ''
        with patch.object(p.c, 'canonical_root', return_value=p.c.ROOT), \
             patch.object(p.c, 'run', side_effect=git), patch.object(p.c, 'admission_lock'), \
             patch.object(p, 'sync_state'), patch.object(p.c, 'issues_by_id', return_value=issues), \
             patch.object(p.c, 'bd', return_value=[{'id': 'pdf-t19'}]) as bd, \
             patch.object(p.c, 'check_predecessors', side_effect=ValueError('T18 acceptance is missing')) as predecessors, \
             patch.object(p, 'publish_state') as publish:
            with self.assertRaisesRegex(ValueError, 'T18 acceptance'):
                p.dispatch('T19', 'antigravity')
            predecessors.assert_called_once()
            self.assertEqual(predecessors.call_args.args[0]['id'], 'T19')
            self.assertEqual(predecessors.call_args.kwargs['ref'], 'HEAD')
            self.assertFalse(any(call.kwargs.get('write') for call in bd.call_args_list))
            publish.assert_not_called()

    def test_future_dispatch_publishes_actual_stage_after_all_guards(self):
        issues = {'pdf-t30': {'status': 'open'}}
        def git(argv):
            if argv[1:3] == ['config', '--get']:
                return 'integrator'
            if argv[1:3] == ['branch', '--show-current']:
                return 'main'
            return 'a' * 40 if argv[1] == 'rev-parse' else ''
        with patch.object(p.c, 'canonical_root', return_value=p.c.ROOT), \
             patch.object(p.c, 'run', side_effect=git), patch.object(p.c, 'admission_lock'), \
             patch.object(p, 'sync_state'), patch.object(p.c, 'issues_by_id', return_value=issues), \
             patch.object(p.c, 'bd', return_value=[{'id': 'pdf-t30'}]) as bd, \
             patch.object(p.c, 'check_predecessors') as predecessors, \
             patch.object(p, 'check_fresh_predecessors') as fresh, \
             patch.object(p.c, 'check_scope_ownership') as scopes, \
             patch.object(p, 'publish_state') as publish, redirect_stdout(StringIO()) as output:
            p.dispatch('T30', 'devin')
        grant = json.loads(output.getvalue())
        self.assertEqual((grant['pass'], grant['workbench']), (2, 'B'))
        predecessors.assert_called_once()
        scopes.assert_called_once()
        fresh.assert_called_once()
        self.assertEqual(fresh.call_args.args[2], "HEAD")
        publish.assert_called_once()
        self.assertEqual(sum(bool(call.kwargs.get('write')) for call in bd.call_args_list), 1)

    def test_linked_checkout_cannot_dispatch_even_with_shared_integrator_config(self):
        with patch.object(p.c, 'canonical_root', return_value=p.c.ROOT.parent / 'other'), \
             patch.object(p.c, 'run', return_value='integrator'), patch.object(p.c, 'bd') as bd:
            with self.assertRaisesRegex(ValueError, 'designated'):
                p.dispatch('T30', 'devin')
            bd.assert_not_called()


if __name__ == '__main__':
    unittest.main()
