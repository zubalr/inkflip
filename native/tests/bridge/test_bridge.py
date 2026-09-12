"""T31 shared Node comparison bridge tests (TEST-31), Python side.

Runs the same golden cases as ``tests/bridge/bridge.test.mjs`` through
BOTH real paths — the in-process shared TS code (the browser path, via
``tests/bridge/direct_driver.mjs``) and the Python->Node bridge
(``native/inkflip/compare_bridge.py`` spawning the fixed entrypoint
``packages/compare/node/bridge.mjs``) — asserting byte-identical
normalized output and geometry, never approximations.

Also covered: missing Node as a typed capability error with no fallback
algorithm, honestly bounded stdout/stderr/request channels, a fixed argv
no request or report content can influence, and comparator version
identity surfaced for manifests (I13).

Written with unittest so the suite is collectable by pytest and by
``python -m unittest`` alike, matching native test conventions.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / 'native'
sys.path.insert(0, str(NATIVE))

from inkflip.compare_bridge import (  # noqa: E402
    BRIDGE_PROTOCOL,
    BRIDGE_PROTOCOL_VERSION,
    ENTRYPOINT,
    BridgeCapabilityError,
    BridgeError,
    BridgeLimits,
    CompareBridge,
)

CASES = json.loads((ROOT / 'tests' / 'bridge' / 'cases.json').read_text())
DRIVER = ROOT / 'tests' / 'bridge' / 'direct_driver.mjs'
NODE = shutil.which('node')
PYTHON = sys.executable

requires_node = unittest.skipUnless(
    NODE is not None, 'node runtime not installed on this host'
)


def geometry_for(spec: dict) -> dict:
    """Test-side expansion of the case 'box' shorthand into contract
    geometry; identical to the expansion in bridge.test.mjs."""
    box = spec.get('box')
    return {
        'precision': spec.get('precision', 'exact'),
        'space': 'canonical_page',
        'polygon': (
            None
            if box is None
            else [
                [box[0], box[1]],
                [box[2], box[1]],
                [box[2], box[3]],
                [box[0], box[3]],
            ]
        ),
        'transform_ids': [],
        'basis': 'golden case',
    }


def expand_occurrence(spec: dict) -> dict:
    out = {
        'id': spec['id'],
        'page_index': spec['page_index'],
        'ordinal': spec['ordinal'],
        'geometry': geometry_for(spec),
    }
    if 'raw' in spec:
        out['raw'] = spec['raw']
    if 'normalized_text' in spec:
        out['normalized_text'] = spec['normalized_text']
    return out


def expand_page(spec: dict) -> dict:
    page = {
        'left': [expand_occurrence(o) for o in spec['left']],
        'right': [expand_occurrence(o) for o in spec['right']],
    }
    if 'page_index' in spec:
        page['page_index'] = spec['page_index']
    if 'region' in spec:
        b = spec['region']
        page['region'] = {
            'polygon': [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]
        }
    return page


def direct_ts(payload: dict) -> dict:
    """Run the shared TS code in-process (the browser path) and return
    the op's result payload."""
    completed = subprocess.run(
        [NODE, str(DRIVER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        shell=False,
    )
    assert completed.returncode == 0, (
        f'direct driver exited {completed.returncode}: '
        f'{completed.stderr[:300]}'
    )
    return json.loads(completed.stdout)


def fake_spawn(argv_inside, **spawn_kwargs):
    """A spawn factory that ignores the bridge argv and runs a real
    fault-injection child instead — for overflow/timeout/crash tests."""
    def factory(argv, **kwargs):
        merged = dict(kwargs)
        merged.update(spawn_kwargs)
        return subprocess.Popen(argv_inside, **merged)

    return factory


class GoldenCrossLanguageTests(unittest.TestCase):
    """Golden cases agree exactly through both paths (criterion 1)."""

    @requires_node
    def test_normalize_cases_agree_exactly(self):
        bridge = CompareBridge()
        raws = [case['raw'] for case in CASES['normalize']]
        bridged = bridge.normalize(raws).result
        direct = direct_ts({'op': 'normalize', 'raws': raws})
        self.assertEqual(bridged, direct)
        self.assertEqual(len(bridged['results']), len(CASES['normalize']))

    @requires_node
    def test_align_cases_agree_exactly(self):
        bridge = CompareBridge()
        pages = [expand_page(case) for case in CASES['align']]
        bridged = bridge.align(pages).result
        direct = direct_ts({'op': 'align', 'pages': pages})
        self.assertEqual(bridged, direct)
        self.assertEqual(len(bridged['results']), len(CASES['align']))

    @requires_node
    def test_align_cases_carry_claimed_semantics(self):
        bridge = CompareBridge()
        pages = [expand_page(case) for case in CASES['align']]
        results = bridge.align(pages).result['results']
        by_id = {case['id']: results[i] for i, case in enumerate(CASES['align'])}

        unique = by_id['exact-unique']
        self.assertEqual(len(unique['matches']), 2)
        self.assertTrue(
            all(m['provenance'] == 'one_to_one' for m in unique['matches'])
        )

        split = by_id['split-merge-provenance']
        self.assertEqual(len(split['matches']), 1)
        self.assertEqual(split['matches'][0]['provenance'], 'many_to_one')
        self.assertEqual(
            sorted(split['matches'][0]['left_occurrence_ids']), ['l0', 'l1']
        )

        # F15: digit->letter substitution is a real cost yet still
        # localized uniquely — material text is never normalized away.
        material = by_id['material-text-difference']
        diff = next(
            m for m in material['matches'] if 'l0' in m['left_occurrence_ids']
        )
        self.assertGreater(diff['components']['text_distance'], 0)

        # F11: identical text at four positions binds per position.
        dup = by_id['duplicate-positions']
        self.assertEqual(len(dup['matches']), 4)
        bound = sorted(m['right_occurrence_ids'][0] for m in dup['matches'])
        self.assertEqual(bound, ['r0', 'r1', 'r2', 'r3'])

        # F12: changed emission order is reported as order differences.
        order = by_id['column-order-differs']
        self.assertEqual(len(order['matches']), 4)
        self.assertGreater(len(order['order_differences']), 0)

        # I04: page_only geometry is never rescued by identical text.
        page_level = by_id['page-level-no-rescue']
        status = {o['occurrence_id']: o['status'] for o in page_level['left']}
        self.assertEqual(status['l0'], 'page_level')
        status_r = {o['occurrence_id']: o['status'] for o in page_level['right']}
        self.assertNotEqual(status_r['r0'], 'unique')

        region = by_id['region-scoped']
        self.assertTrue(region['region_scoped'])
        status = {o['occurrence_id']: o['status'] for o in region['left']}
        self.assertEqual(status['l1'], 'out_of_scope')
        self.assertEqual(status['l0'], 'unique')

        extra = by_id['unmatched-extra']
        status = {o['occurrence_id']: o['status'] for o in extra['left']}
        self.assertEqual(status['l1'], 'unmatched')

        tie = by_id['ambiguous-tie']
        self.assertEqual(len(tie['matches']), 0)
        self.assertGreater(len(tie['ambiguous']), 0)
        self.assertTrue(
            all(entry['reason'] == 'tie' for entry in tie['ambiguous'])
        )

    @requires_node
    def test_python_contract_normalize_and_bridge_agree(self):
        # The contract's Python normalize() port (used to write
        # normalized_text into reports) and the shared TS code reached
        # through the bridge produce identical text for every case.
        from inkflip.contracts import normalize as py_normalize

        bridge = CompareBridge()
        raws = [case['raw'] for case in CASES['normalize']]
        bridged = bridge.normalize(raws).result['results']
        for raw, result in zip(raws, bridged):
            text, _segments = py_normalize(raw)
            self.assertEqual(result['text'], text)


class CapabilityErrorTests(unittest.TestCase):
    """Missing Node is a typed capability error, never a silent
    fallback (criterion 2)."""

    def test_missing_node_on_path_fails_typed(self):
        env_path = os.environ.get('PATH', '')
        try:
            os.environ['PATH'] = tempfile.mkdtemp(prefix='inkflip-empty-')
            with self.assertRaises(BridgeCapabilityError) as raised:
                CompareBridge()
            self.assertEqual(raised.exception.reason, 'capability')
        finally:
            os.environ['PATH'] = env_path

    def test_absent_explicit_node_path_fails_typed(self):
        with self.assertRaises(BridgeCapabilityError) as raised:
            CompareBridge(node='/nonexistent/inkflip/node')
        self.assertEqual(raised.exception.reason, 'capability')

    def test_missing_entrypoint_fails_typed(self):
        with self.assertRaises(BridgeCapabilityError) as raised:
            CompareBridge(
                node=NODE or sys.executable,
                entrypoint='/nonexistent/inkflip/bridge.mjs',
            )
        self.assertEqual(raised.exception.reason, 'capability')

    @requires_node
    def test_spawn_enoent_fails_typed_not_fallback(self):
        def enoent_spawn(argv, **kwargs):
            raise FileNotFoundError(2, 'No such file or directory', argv[0])

        bridge = CompareBridge(spawn=enoent_spawn)
        with self.assertRaises(BridgeCapabilityError) as raised:
            bridge.describe()
        self.assertEqual(raised.exception.reason, 'capability')

    @requires_node
    def test_spawn_permission_denied_fails_typed(self):
        def denied_spawn(argv, **kwargs):
            raise PermissionError(13, 'Permission denied', argv[0])

        bridge = CompareBridge(spawn=denied_spawn)
        with self.assertRaises(BridgeCapabilityError) as raised:
            bridge.describe()
        self.assertEqual(raised.exception.reason, 'capability')

    def test_no_fallback_path_exists(self):
        # The module surface has no comparison implementation to fall
        # back to: ops exist only as bridge calls.
        import inkflip.compare_bridge as module

        self.assertFalse(hasattr(module, 'align_page'))
        self.assertFalse(hasattr(module, 'normalize_text'))


class BoundedIoTests(unittest.TestCase):
    """stdout (and friends) are honestly bounded (criterion 3)."""

    @requires_node
    def test_request_over_cap_refused_before_spawn(self):
        spawned = []
        bridge = CompareBridge(
            limits=BridgeLimits(max_request_bytes=1024),
            spawn=lambda argv, **kw: spawned.append(argv)
            or subprocess.Popen(argv, **kw),
        )
        with self.assertRaises(BridgeError) as raised:
            bridge.normalize(['x' * 4096])
        self.assertEqual(raised.exception.reason, 'request_too_large')
        self.assertEqual(spawned, [])  # never reached the child

    @requires_node
    def test_response_over_cap_is_output_limit(self):
        # A real comparison whose JSON answer legitimately exceeds a
        # deliberately tiny cap -> honest output_limit, never truncation.
        bridge = CompareBridge(limits=BridgeLimits(max_response_bytes=512))
        with self.assertRaises(BridgeError) as raised:
            bridge.normalize(['x' * 2048])
        self.assertEqual(raised.exception.reason, 'output_limit')

    @requires_node
    def test_response_within_cap_succeeds(self):
        bridge = CompareBridge(
            limits=BridgeLimits(max_response_bytes=1 << 20)
        )
        result = bridge.normalize(['small'])
        self.assertEqual(result.result['results'][0]['text'], 'small')

    @requires_node
    def test_stdout_flood_is_killed_and_bounded(self):
        # A real runaway child (injected spawn ignores the fixed argv):
        # the pump must kill it and report output_limit.
        flood = fake_spawn(
            [PYTHON, '-c', 'import sys; sys.stdout.write("x" * (1 << 24))'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        bridge = CompareBridge(
            limits=BridgeLimits(max_response_bytes=1 << 16), spawn=flood
        )
        with self.assertRaises(BridgeError) as raised:
            bridge.describe()
        self.assertEqual(raised.exception.reason, 'output_limit')

    @requires_node
    def test_stderr_flood_is_output_limit(self):
        flood = fake_spawn(
            [PYTHON, '-c', 'import sys; sys.stderr.write("e" * (1 << 24))'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        bridge = CompareBridge(
            limits=BridgeLimits(max_stderr_bytes=1 << 16), spawn=flood
        )
        with self.assertRaises(BridgeError) as raised:
            bridge.describe()
        self.assertEqual(raised.exception.reason, 'output_limit')

    @requires_node
    def test_wall_timeout_kills_child_group(self):
        pid_seen = []

        def sleepy_spawn(argv, **kwargs):
            proc = subprocess.Popen(
                [PYTHON, '-c', 'import time; time.sleep(60)'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            pid_seen.append(proc.pid)
            return proc

        bridge = CompareBridge(
            limits=BridgeLimits(wall_seconds=0.3), spawn=sleepy_spawn
        )
        started = __import__('time').monotonic()
        with self.assertRaises(BridgeError) as raised:
            bridge.describe()
        elapsed = __import__('time').monotonic() - started
        self.assertEqual(raised.exception.reason, 'timeout')
        self.assertLess(elapsed, 10)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid_seen[0], 0)


class FixedArgvTests(unittest.TestCase):
    """No shell/plugin/profile selection from report content
    (criterion 4): argv is always exactly [node, entrypoint]."""

    @requires_node
    def test_argv_is_fixed_and_env_minimal(self):
        seen = {}

        def recording_spawn(argv, **kwargs):
            seen['argv'] = list(argv)
            seen['env'] = dict(kwargs.get('env') or {})
            seen['shell'] = kwargs.get('shell')
            return subprocess.Popen(argv, **kwargs)

        bridge = CompareBridge(spawn=recording_spawn)
        bridge.describe()
        self.assertEqual(seen['argv'], [NODE, str(ENTRYPOINT)])
        self.assertEqual(seen['shell'], False)
        self.assertNotIn('NODE_OPTIONS', seen['env'])
        self.assertNotIn('PATH', seen['env'])

    @requires_node
    def test_report_like_content_stays_data(self):
        seen = {}

        def recording_spawn(argv, **kwargs):
            seen['argv'] = list(argv)
            return subprocess.Popen(argv, **kwargs)

        bridge = CompareBridge(spawn=recording_spawn)
        # Occurrence text carrying shell/flag-shaped strings is just data
        # to normalize — it can never reach argv or select a profile.
        hostile_raws = [
            '--input-type=module',
            '$(rm -rf /) && `--eval process.exit(9)`',
            '"; exec("/bin/sh") #',
            'NODE_OPTIONS=--require=evil',
        ]
        result = bridge.normalize(hostile_raws)
        self.assertEqual(seen['argv'], [NODE, str(ENTRYPOINT)])
        # Every hostile string is normalized as inert text, verbatim.
        for raw, view in zip(hostile_raws, result.result['results']):
            self.assertEqual(view['text'], raw)

    @requires_node
    def test_smuggled_envelope_fields_reject_without_influence(self):
        seen = {}

        def recording_spawn(argv, **kwargs):
            seen['argv'] = list(argv)
            return subprocess.Popen(argv, **kwargs)

        bridge = CompareBridge(spawn=recording_spawn)
        # The bridge API only ever sends the fixed envelope; a caller
        # injecting fields into a page object is rejected by the shared
        # closed schema — and argv still never changes.
        with self.assertRaises(BridgeError) as raised:
            bridge.align(
                [
                    {
                        'left': [],
                        'right': [],
                        'profile': 'hostile',
                        'exec': '/bin/sh',
                    }
                ]
            )
        self.assertEqual(raised.exception.reason, 'remote_field')
        self.assertEqual(seen['argv'], [NODE, str(ENTRYPOINT)])


class VersionIdentityTests(unittest.TestCase):
    """Manifests retain comparator version (criterion 5 / I13)."""

    @requires_node
    def test_describe_surfaces_comparator_identity(self):
        result = CompareBridge().describe()
        c = result.comparator
        self.assertEqual(c['package'], '@inkflip/compare')
        self.assertEqual(c['protocol'], BRIDGE_PROTOCOL)
        self.assertEqual(c['protocol_version'], BRIDGE_PROTOCOL_VERSION)
        self.assertEqual(c['normalization'], 'scalar-whitespace-v1')
        self.assertEqual(c['alignment'], 'region-match-v1')
        self.assertEqual(
            c['score_semantics'], 'algorithm_diagnostics_not_probability'
        )
        self.assertTrue(c['node'].startswith('v'))
        self.assertEqual(c['bridge_version'], '1.0.0')

    @requires_node
    def test_identity_rides_every_result_and_lands_in_manifest(self):
        bridge = CompareBridge()
        described = bridge.describe().comparator
        aligned = bridge.align(
            [
                {
                    'left': [expand_occurrence(CASES['align'][0]['left'][0])],
                    'right': [
                        expand_occurrence(CASES['align'][0]['right'][0])
                    ],
                }
            ]
        )
        self.assertEqual(aligned.comparator, described)
        # The block the bridge surfaces drops directly into a manifest-
        # style record; this is what a run/comparison manifest stores.
        manifest = {'comparator': aligned.manifest_entry()}
        self.assertEqual(manifest['comparator']['name'], '@inkflip/compare')
        self.assertEqual(
            manifest['comparator']['normalization'], 'scalar-whitespace-v1'
        )
        self.assertEqual(
            manifest['comparator']['alignment'], 'region-match-v1'
        )
        self.assertEqual(
            manifest['comparator']['protocol'], BRIDGE_PROTOCOL
        )
        self.assertTrue(manifest['comparator']['node'].startswith('v'))


class FailureTaxonomyTests(unittest.TestCase):
    """Remaining typed failures: remote rejection, child exit/crash and
    malformed child output."""

    @requires_node
    def test_remote_rejection_maps_to_typed_reason(self):
        bridge = CompareBridge()
        with self.assertRaises(BridgeError) as raised:
            bridge.normalize([{'not': 'a string'}])
        self.assertEqual(raised.exception.reason, 'remote_type')

    @requires_node
    def test_normalization_parity_surfaces_to_python(self):
        bridge = CompareBridge()
        with self.assertRaises(BridgeError) as raised:
            bridge.align(
                [
                    {
                        'left': [
                            {
                                'id': 'l0',
                                'page_index': 0,
                                'ordinal': 0,
                                'raw': 'Total  due',
                                'normalized_text': 'Total-due',
                                'geometry': geometry_for(
                                    {'box': [10, 20, 80, 32]}
                                ),
                            }
                        ],
                        'right': [],
                    }
                ]
            )
        self.assertEqual(raised.exception.reason, 'remote_normalization')

    @requires_node
    def test_nonzero_child_exit_is_typed(self):
        bridge = CompareBridge(
            spawn=fake_spawn(
                [PYTHON, '-c', 'import sys; sys.exit(3)'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        )
        with self.assertRaises(BridgeError) as raised:
            bridge.describe()
        self.assertEqual(raised.exception.reason, 'exit')

    @requires_node
    def test_child_signal_is_typed_crash(self):
        bridge = CompareBridge(
            spawn=fake_spawn(
                [
                    PYTHON,
                    '-c',
                    'import os, signal; os.kill(os.getpid(), signal.SIGSEGV)',
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        )
        with self.assertRaises(BridgeError) as raised:
            bridge.describe()
        self.assertEqual(raised.exception.reason, 'crash')

    @requires_node
    def test_malformed_child_output_is_protocol_error(self):
        bridge = CompareBridge(
            spawn=fake_spawn(
                [PYTHON, '-c', 'print("definitely not json")'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        )
        with self.assertRaises(BridgeError) as raised:
            bridge.describe()
        self.assertEqual(raised.exception.reason, 'protocol_error')

    @requires_node
    def test_invalid_limits_refused(self):
        with self.assertRaises(BridgeError) as raised:
            CompareBridge(limits=BridgeLimits(max_response_bytes=0))
        self.assertEqual(raised.exception.reason, 'configuration')

    @requires_node
    def test_unserializable_input_is_typed_not_typeerror(self):
        # A caller passing a non-JSON-serializable value gets a typed
        # bridge error before spawn — never a leaked TypeError, and the
        # child is never launched.
        spawned = []
        bridge = CompareBridge(
            spawn=lambda argv, **kw: spawned.append(argv)
            or subprocess.Popen(argv, **kw)
        )
        with self.assertRaises(BridgeError) as raised:
            bridge.normalize([object()])
        self.assertEqual(raised.exception.reason, 'type')
        self.assertEqual(spawned, [])
        with self.assertRaises(BridgeError) as raised:
            bridge.align([{'left': [{'raw': {'a', 'set'}}]}])
        self.assertEqual(raised.exception.reason, 'type')


if __name__ == '__main__':
    unittest.main()
