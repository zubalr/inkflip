"""T03 contract acceptance (TEST-03), Python side.

Runs the same delivered fixtures and reference-computed goldens as
``tests/contracts/contracts.test.mjs``. Written with unittest so the suite
is collectable by pytest and by ``python -m unittest`` alike.
"""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / 'native'
sys.path.insert(0, str(NATIVE))

from inkflip.contracts import (  # noqa: E402
    ContractError,
    bounded,
    canonical,
    digest,
    loads_strict,
    normalize,
    occurrence_id,
    report_digest,
    run_key,
    seal,
    validate,
    validate_json,
)

PLANNING = ROOT / 'planning'
EXAMPLES = PLANNING / 'contracts' / 'examples'
VALID_DIR = EXAMPLES / 'valid'
INVALID_INDEX = EXAMPLES / 'invalid-index.json'
FIXTURES = ROOT / 'tests' / 'contracts' / 'fixtures'


def code(fn):
    try:
        fn()
    except ContractError as exc:
        return exc.code
    return None


def load_valid(name):
    return loads_strict((VALID_DIR / name).read_bytes())


class ValidInvalidFixtureTests(unittest.TestCase):
    def test_all_valid_examples(self):
        files = sorted(VALID_DIR.glob('*.json'))
        self.assertGreaterEqual(len(files), 12)
        for p in files:
            with self.subTest(file=p.name):
                validate(loads_strict(p.read_bytes()))

    def test_all_invalid_examples(self):
        index = json.loads(INVALID_INDEX.read_text())
        self.assertGreaterEqual(len(index), 30)
        for entry in index:
            with self.subTest(file=entry['path']):
                actual = code(
                    lambda: validate(
                        loads_strict((PLANNING / entry['path']).read_bytes())
                    )
                )
                self.assertEqual(actual, entry['expected_code'])


class HashVectorTests(unittest.TestCase):
    def test_vectors(self):
        vectors = json.loads(
            (PLANNING / 'contracts' / 'hash-vectors.json').read_text()
        )
        for v in vectors:
            with self.subTest(value=v['value']):
                self.assertEqual(canonical(v['value']).hex(), v['canonical_hex'])
                self.assertEqual(digest(v['value']), v['sha256'])

    def test_reference_goldens(self):
        golden = json.loads((FIXTURES / 'digest-golden.json').read_text())
        for g in golden['digests']:
            self.assertEqual(canonical(g['value']).hex(), g['canonical_hex'])
            self.assertEqual(digest(g['value']), g['sha256'])
        for g in golden['normalize']:
            text, m = normalize(g['input'])
            self.assertEqual(text, g['text'])
            self.assertEqual(m, g['map'])
        for g in golden['occurrence_ids']:
            self.assertEqual(
                occurrence_id(
                    g['run_key'],
                    g['reader_id'],
                    g['page_index'],
                    g['ordinal'],
                    g['raw_source_locator'],
                ),
                g['id'],
            )
        for name, ids in golden['report_identities'].items():
            with self.subTest(file=name):
                r = load_valid(name)
                self.assertEqual(run_key(r), ids['run_key'])
                self.assertEqual(report_digest(r), ids['report_id'])
                self.assertEqual(r['report_id'], ids['sealed_report_id'])


class StrictParseTests(unittest.TestCase):
    def test_duplicate_keys(self):
        self.assertEqual(
            code(lambda: loads_strict('{"a":1,"a":2}')), 'DUPLICATE_KEY'
        )
        self.assertEqual(
            code(lambda: loads_strict('{"a":{"b":1,"b":2}}')), 'DUPLICATE_KEY'
        )
        self.assertEqual(
            code(lambda: loads_strict('{"__proto__":1,"__proto__":2}')),
            'DUPLICATE_KEY',
        )

    def test_nonfinite_and_unsafe(self):
        for s in ('NaN', 'Infinity', '-Infinity', '[NaN]', '{"x":Infinity}'):
            with self.subTest(value=s):
                self.assertEqual(code(lambda: loads_strict(s)), 'NONFINITE')
        for s in ('9007199254740993', '-9007199254740993'):
            with self.subTest(value=s):
                self.assertEqual(code(lambda: loads_strict(s)), 'NUMBER')
        for s in ('9007199254740992.0', '-9007199254740992.0', '1e20'):
            with self.subTest(value=s):
                self.assertEqual(code(lambda: loads_strict(s)), 'NUMBER')
        self.assertEqual(canonical(loads_strict('-0')).hex(), '440000000000000000')

    def test_surrogates_and_depth(self):
        for s in ('"\\ud800"', '"\\udc00"', '"\\ud800x"', '"a\\udc00"'):
            with self.subTest(value=s):
                self.assertEqual(code(lambda: loads_strict(s)), 'UNICODE')
        self.assertEqual(loads_strict('"\\ud83d\\ude00"'), '\U0001f600')
        inner = loads_strict('[' * 24 + '0' + ']' * 24)
        for _ in range(24):
            inner = inner[0]
        self.assertEqual(inner, 0)
        self.assertEqual(code(lambda: loads_strict('[' * 25 + '0' + ']' * 25)), 'DEPTH')

    def test_malformed_json(self):
        for s in ('{', '{"a":}', '[1,]', '{"a":1,}', '{a:1}', '"unterminated'):
            with self.subTest(value=s):
                self.assertEqual(code(lambda: loads_strict(s)), 'JSON')

    def test_bytes_input(self):
        self.assertEqual(loads_strict('{"a":[1,2]}'.encode('utf-8')), {'a': [1, 2]})
        self.assertEqual(code(lambda: loads_strict(b'\xff\xfeA')), 'UNICODE')

    def test_bounded_programmatic(self):
        self.assertEqual(code(lambda: bounded({'a': 2 ** 53})), 'NUMBER')
        self.assertEqual(code(lambda: bounded([float('inf')])), 'NONFINITE')
        self.assertEqual(code(lambda: bounded('', 25)), 'DEPTH')
        with self.assertRaises(ContractError):
            canonical({1: 'non-string key'})

    def test_canonical_rejects_non_plain_values(self):
        import datetime

        for v in ({1, 2}, datetime.datetime(2020, 1, 1), object(), memoryview(b'x')):
            with self.subTest(value=type(v).__name__):
                self.assertEqual(code(lambda: canonical(v)), 'TYPE')
                self.assertEqual(code(lambda: digest(v)), 'TYPE')

    def test_integer_literal_overflow_reports_number(self):
        self.assertEqual(code(lambda: loads_strict('9' * 400)), 'NUMBER')
        self.assertEqual(code(lambda: loads_strict('-' + '9' * 400)), 'NUMBER')
        self.assertEqual(code(lambda: loads_strict('[' + '9' * 400 + ']')), 'NUMBER')
        self.assertEqual(code(lambda: loads_strict('1e999')), 'NONFINITE')
        self.assertEqual(code(lambda: loads_strict('-1e999')), 'NONFINITE')

    def test_pathological_inputs_raise_contract_error(self):
        # Lone-surrogate str input: the parse reports JSON like TypeScript.
        self.assertEqual(code(lambda: loads_strict('\ud800')), 'JSON')
        self.assertEqual(code(lambda: canonical('x\ud800')), 'UNICODE')
        self.assertEqual(code(lambda: canonical({'k\ud800': 1})), 'UNICODE')
        # bytes-like inputs decode like bytes; other types report TYPE.
        self.assertEqual(loads_strict(bytearray(b'{}')), {})
        self.assertEqual(loads_strict(memoryview(b'[]')), [])
        self.assertEqual(code(lambda: loads_strict(5)), 'TYPE')

    def test_non_string_input_reports_type(self):
        for v in (5, None, True, [1], {}, 1.5):
            with self.subTest(value=repr(v)):
                self.assertEqual(code(lambda: loads_strict(v)), 'TYPE')
                self.assertEqual(code(lambda: validate_json(v)), 'TYPE')

    def test_multi_fault_precedence_matches_parse_order(self):
        big = '9' * 400
        self.assertEqual(
            code(lambda: loads_strict('{"a":' + big + ',"a":1}')),
            'DUPLICATE_KEY',
        )
        self.assertEqual(code(lambda: loads_strict('[' + big + ']x')), 'JSON')
        self.assertEqual(code(lambda: loads_strict('[' + big + ',bad')), 'JSON')
        # Traversal order: earlier surrogate beats later unsafe integer.
        self.assertEqual(
            code(lambda: loads_strict('["\\ud800",' + big + ']')), 'UNICODE'
        )
        self.assertEqual(
            code(lambda: loads_strict('[' + big + ',"\\ud800"]')), 'NUMBER'
        )
        self.assertEqual(code(lambda: loads_strict(big)), 'NUMBER')
        self.assertEqual(code(lambda: loads_strict('1e999')), 'NONFINITE')

    def test_duplicate_keys_reported_at_object_close(self):
        cases = [
            ('{"a":1,"a":}', 'JSON'),
            ('{"a":1,"a":NaN}', 'NONFINITE'),
            ('{"a":1,"a":-Infinity}', 'NONFINITE'),
            ('{"a":1,"a":5,"b":NaN}', 'NONFINITE'),
            ('{"a":1,"a":5,"b":}', 'JSON'),
            ('{"a":{"b":1,"b":NaN}}', 'NONFINITE'),
            ('{"a":{"b":1,"b":}}', 'JSON'),
            ('{"a":{"b":1,"b":2},"c":}', 'DUPLICATE_KEY'),
            ('{"x":},{"a":1,"a":2}', 'JSON'),
            ('{"a":{"b":1,"b":2},"a":}', 'DUPLICATE_KEY'),
            ('{"a":1,"a":2}x', 'DUPLICATE_KEY'),
            ('{"a":1,"a":2,}', 'JSON'),
            ('[{"a":1,"a":2},bad', 'DUPLICATE_KEY'),
            ('{"a":{"b":1,"b":2}}x', 'DUPLICATE_KEY'),
            ('{"a":1,"b":{"c":1,"c":2},"d":NaN}', 'DUPLICATE_KEY'),
            ('{"a":1,"a":' + '9' * 400 + '}', 'DUPLICATE_KEY'),
            ('{"a":1,"a":"\\ud800"}', 'DUPLICATE_KEY'),
            ('["\\ud800",{"a":1,"a":2}]', 'DUPLICATE_KEY'),
        ]
        for doc, expected in cases:
            with self.subTest(doc=doc[:40]):
                self.assertEqual(code(lambda: loads_strict(doc)), expected)


class IdentityTests(unittest.TestCase):
    def test_key_order_canonical_array_order_significant(self):
        a = loads_strict('{"z":1,"a":2,"m":{"y":1,"b":2}}')
        b = loads_strict('{"m":{"b":2,"y":1},"a":2,"z":1}')
        self.assertEqual(digest(a), digest(b))
        self.assertNotEqual(digest([1, 2]), digest([2, 1]))
        r = load_valid('native-evidence.inkflip.json')
        flipped = copy.deepcopy(r)
        flipped['readers'] = list(reversed(flipped['readers']))
        self.assertNotEqual(run_key(flipped), run_key(r))

    def test_report_digest_exclusions(self):
        r = load_valid('native-evidence.inkflip.json')
        base = report_digest(r)
        same = copy.deepcopy(r)
        same['execution']['execution_id'] = (
            '37dfed38-ed9a-436c-b4a8-c61dfb164694'
        )
        same['execution']['started_at'] = '2030-01-01T00:00:00+00:00'
        same['execution']['duration_ms'] += 1
        for a in same['assets']:
            a['data_base64'] = 'AA=='
        self.assertEqual(report_digest(same), base)
        changed = copy.deepcopy(r)
        changed['limitations'].append('Additional actual limitation.')
        self.assertNotEqual(report_digest(changed), base)
        meta = copy.deepcopy(r)
        meta['assets'][0]['byte_length'] += 1
        self.assertNotEqual(report_digest(meta), base)

    def test_seal_roundtrip(self):
        r = load_valid('native-evidence.inkflip.json')
        original = r['report_id']
        r['report_id'] = '0' * 64
        self.assertEqual(code(lambda: validate(r)), 'HASH')
        seal(r)
        self.assertEqual(r['report_id'], original)
        validate(r)

    def test_check_hashes_false(self):
        r = load_valid('native-evidence.inkflip.json')
        r['report_id'] = '0' * 64
        self.assertEqual(code(lambda: validate(r)), 'HASH')
        validate(r, check_hashes=False)
        r['plan']['checks'].pop()
        self.assertEqual(code(lambda: validate(r, check_hashes=False)), 'COVERAGE')

    def test_occurrence_id(self):
        rk = 'a' * 64
        i = occurrence_id(rk, 'r_pdfium', 0, 63, 'locator [0,1)')
        self.assertRegex(i, r'^o_[a-f0-9]{32}$')
        self.assertNotEqual(i, occurrence_id(rk, 'r_pdfium', 0, 64, 'locator [0,1)'))
        self.assertNotEqual(i, occurrence_id(rk, 'r_pdfium', 1, 63, 'locator [0,1)'))
        self.assertNotEqual(i, occurrence_id(rk, 'r_pdfium', 0, 63, 'locator [0,2)'))

    def test_duplicate_text_distinct_ids(self):
        r = load_valid('repeated-occurrences.json')
        validate(r)
        texts = [o['raw_text'] for o in r['occurrences']]
        self.assertLess(len(set(texts)), len(texts))
        self.assertEqual(
            len({o['id'] for o in r['occurrences']}), len(r['occurrences'])
        )


class AssetEdgeTests(unittest.TestCase):
    def test_pixel_size_null_reports_asset(self):
        r = load_valid('native-evidence.inkflip.json')
        png = next(
            a for a in r['assets'] if a['media_type'] == 'image/png'
        )
        png['pixel_size'] = None
        self.assertEqual(code(lambda: validate(r)), 'ASSET')


class NormalizationTests(unittest.TestCase):
    def test_meaning_preserved(self):
        for s in ('$1,000', '-$100', 'not paid', 'لا', 'ﬁle', 'é', '😀'):
            with self.subTest(value=s):
                self.assertEqual(normalize(s)[0], s)
        self.assertNotEqual(normalize('$100')[0], normalize('$1,000')[0])
        self.assertEqual(normalize(' A\n\tB ')[0], ' A B ')

    def test_code_point_indexes(self):
        text, m = normalize('x😀 y')
        self.assertEqual(
            m[0],
            {
                'raw_start': 0,
                'raw_end': 2,
                'normalized_start': 0,
                'normalized_end': 2,
                'operation': 'identity',
            },
        )


class VersionAndCompileTests(unittest.TestCase):
    def test_unknown_version_fails_closed(self):
        r = load_valid('acceptance-rules.json')
        r['schema_version'] = '9.9.9'
        self.assertEqual(code(lambda: validate(r)), 'SCHEMA')
        r['schema_version'] = '1.0.0'
        validate(r)

    def test_no_schema_compilation_on_untrusted_input(self):
        # The structural validator is constructed once at module import from
        # the vendored trusted schema. Patching the Draft202012Validator name
        # bound in our module proves validate() never builds a schema
        # validator from untrusted data at call time. (jsonschema internally
        # derives evolved validators from that same trusted schema during
        # traversal, which does not touch our module reference.)
        import inkflip.contracts.core as core

        with mock.patch.object(
            core,
            'Draft202012Validator',
            side_effect=AssertionError('schema compiled during validation'),
        ):
            for p in sorted(VALID_DIR.glob('*.json')):
                validate(loads_strict(p.read_bytes()))
            bad = load_valid('acceptance-rules.json')
            bad['schema_version'] = '9.9.9'
            self.assertEqual(code(lambda: validate(bad)), 'SCHEMA')

    def test_vendored_schema_byte_identical(self):
        authority = (PLANNING / 'contracts' / 'inkflip.schema.json').read_bytes()
        for rel in (
            'packages/contracts/schema/inkflip.schema.json',
            'native/inkflip/contracts/schema/inkflip.schema.json',
        ):
            with self.subTest(path=rel):
                self.assertEqual((ROOT / rel).read_bytes(), authority)

    def test_generated_artifacts_deterministic(self):
        import subprocess

        out = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'generate_contracts.py'), '--check'],
            capture_output=True,
            text=True,
        )
        self.assertEqual(out.returncode, 0, out.stderr)


if __name__ == '__main__':
    unittest.main()
