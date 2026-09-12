"""Generator intent tests; no model/engine initialization required."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from test_fixtures import FIXTURES, ROOT, content_of


def source(name):
    return (FIXTURES / 'development' / name).read_bytes()


class TestPriorityCatalog(unittest.TestCase):
    def test_original_pdfs_and_expectations_are_unchanged(self):
        baseline = json.loads((ROOT / 'artifacts/tasks/T05/followup-g78/baseline-hashes.json').read_text())
        self.assertEqual(len(baseline), 32)
        for name, digest in baseline.items():
            self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), digest, name)

    def test_contrast_control_has_white_text_and_dark_background(self):
        control = content_of(source('white-contrast-control.pdf'))
        white = content_of(source('white-contrast-white.pdf'))
        self.assertTrue(control.endswith(white))
        self.assertIn(b'0 0 0 rg 24 96 200 60 re f', control)
        self.assertIn(b'1 1 1 rg', white)

    def test_paint_order_changes_only_sequence(self):
        before = content_of(source('paint-order-control.pdf'))
        after = content_of(source('paint-order-after.pdf'))
        self.assertLess(before.index(b're f'), before.index(b'Tj'))
        self.assertLess(after.index(b'Tj'), after.index(b're f'))
        self.assertIn(b'24 96 200 60 re f', after)

    def test_partial_and_nonrectangular_clip_are_distinct(self):
        partial = content_of(source('partial-clip-partial.pdf'))
        triangle = content_of(source('partial-clip-triangle.pdf'))
        self.assertIn(b'78 110 24 36 re f', partial)
        self.assertIn(b'48 110 m 108 150 l 168 110 l h W n', triangle)
        self.assertNotIn(b'W n', content_of(source('partial-clip-control.pdf')))

    def test_mapping_absence_and_malformed_are_not_missing_ink(self):
        variants = [source(f'mapping-missing-{v}.pdf') for v in ('control', 'absent', 'malformed')]
        self.assertEqual(len({content_of(v) for v in variants}), 1)
        self.assertIn(b'/ToUnicode', variants[0])
        self.assertNotIn(b'/ToUnicode', variants[1])
        self.assertIn(b'<ZZZZ>', variants[2])

    def test_duplicates_keep_four_positions(self):
        data = content_of(source('duplicates-four.pdf'))
        self.assertEqual(data.count(b'($100) Tj'), 4)
        for x, y in [(48, 180), (200, 180), (48, 60), (200, 60)]:
            self.assertIn(f'1 0 0 1 {x} {y} Tm'.encode(), data)

    def test_unreadable_has_no_native_text_or_plausible_default(self):
        for variant in ('blank', 'noise'):
            data = source(f'unreadable-{variant}.pdf')
            self.assertNotIn(b'Tj', content_of(data))
            exp = json.loads(source(f'unreadable-{variant}.expect.json'))
            self.assertIsNone(exp['mechanism']['intent']['raster_text'])

    def test_invalid_and_encrypted_are_bounded_distinct_cases(self):
        locked = source('bad-pdf-encrypted.pdf')
        self.assertIn(b'/Encrypt 6 0 R', locked)
        self.assertNotIn(b'($100)', locked)
        self.assertLess(len(source('bad-pdf-truncated.pdf')), 100)
        self.assertIn(b'2 0 obj\nnull', source('bad-pdf-malformed.pdf'))

    def test_extreme_geometry_has_tiny_bytes_and_explicit_render_limit(self):
        data = source('huge-page-extreme.pdf')
        self.assertLess(len(data), 1024)
        self.assertIn(b'/MediaBox [0 0 1000000000 1000000000]', data)
        intent = json.loads(source('huge-page-extreme.expect.json'))['mechanism']['intent']
        self.assertEqual(intent['requested_pixels_at_72dpi'], 10**18)
        self.assertTrue(intent['unbounded_render_forbidden'])

    def test_canary_channels_bind_actual_source(self):
        data = source('network-canary-channels.pdf')
        channels = json.loads(source('network-canary-channels.expect.json'))['mechanism']['intent']['channels']
        for channel in ('text', 'metadata', 'annotation'):
            self.assertIn(channels[channel].encode(), data)
        self.assertEqual(channels['hash'], hashlib.sha256(data).hexdigest())
        self.assertNotIn(b'/URI', data)
        self.assertNotIn(b'/JavaScript', data)


class TestFaultDoubles(unittest.TestCase):
    def launch(self, variant):
        return subprocess.Popen([sys.executable, str(Path(__file__).with_name('fault_double.py')),
                                 str(FIXTURES / f'development/worker-fault-{variant}.json')],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_completed_failure_crash_stale_preserve_first_result(self):
        for variant in ('control', 'model-failure', 'crash', 'stale'):
            child = self.launch(variant)
            try:
                out, err = child.communicate(timeout=1)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
            events = [json.loads(line) for line in out.splitlines()]
            self.assertEqual(events[0]['job'], 'completed-first')
            self.assertEqual(events[0]['state'], 'completed')
            self.assertEqual(err, '')
            self.assertEqual(child.returncode, 17 if variant == 'crash' else 0)
            if variant == 'stale':
                self.assertEqual(events[1]['generation'], 1)
            if variant == 'model-failure':
                self.assertEqual(events[-1]['state'], 'failed')

    def test_hang_and_cancel_are_reaped_with_prior_result(self):
        for variant in ('hang', 'cancel'):
            child = self.launch(variant)
            try:
                self.assertEqual(json.loads(child.stdout.readline())['job'], 'completed-first')
                if variant == 'hang':
                    with self.assertRaises(subprocess.TimeoutExpired):
                        child.communicate(timeout=0.05)
                child.terminate()
                child.communicate(timeout=1)
                self.assertIsNotNone(child.returncode)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
