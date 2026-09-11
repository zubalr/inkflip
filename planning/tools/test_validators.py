#!/usr/bin/env python3
"""Run real planning utility tests, including every invalid contract fixture.
These are not product/browser/native acceptance results. No network or OCR.
"""
from __future__ import annotations
import copy, importlib.util, json, subprocess, sys, tempfile, unittest
from pathlib import Path
from html.parser import HTMLParser
from contractlib import loads_strict, validate, ContractError, canonical, digest, report_digest, normalize, seal
from validate_package import check_dag, check_links, check_integrity, PackageError
from ready_tasks import ready
from bootstrap_repo import bootstrap
from export_html import render
ROOT=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
    def test_all_valid_examples(self):
        for p in sorted((ROOT/'contracts/examples/valid').glob('*.json')):
            with self.subTest(file=p.name):validate(loads_strict(p.read_bytes()))
    def test_all_invalid_examples(self):
        for case in json.loads((ROOT/'contracts/examples/invalid-index.json').read_text()):
            with self.subTest(file=case['path']):
                with self.assertRaises(ContractError) as caught:validate(loads_strict((ROOT/case['path']).read_bytes()))
                self.assertEqual(caught.exception.code,case['expected_code'])
    def test_duplicate_json_keys(self):
        with self.assertRaises(ContractError) as e:loads_strict('{"a":1,"a":2}')
        self.assertEqual(e.exception.code,'DUPLICATE_KEY')
    def test_nonfinite_and_unsafe_integer(self):
        for s in ('NaN','Infinity','9007199254740993'):
            with self.subTest(value=s),self.assertRaises(ContractError):loads_strict(s)
    def test_unsafe_integral_floats_match_node_policy(self):
        for value in (9007199254740992.0, -9007199254740992.0, 1e20):
            with self.subTest(value=value), self.assertRaises(ContractError):canonical(value)
            with self.subTest(json=value), self.assertRaises(ContractError):loads_strict(json.dumps(value))
    def test_canonical_nonstring_keys_rejected(self):
        with self.assertRaises(ContractError):canonical({1:'not a JSON key'})
    def test_depth_and_surrogates(self):
        for s in ('['*25+'0'+']'*25,'"\\ud800"'):
            with self.subTest(value=s),self.assertRaises(ContractError):loads_strict(s)
    def test_hash_vectors(self):
        for v in json.loads((ROOT/'contracts/hash-vectors.json').read_text()):
            self.assertEqual(canonical(v['value']).hex(),v['canonical_hex']);self.assertEqual(digest(v['value']),v['sha256'])
    def test_hash_time_exclusion_and_semantic_change(self):
        r=loads_strict((ROOT/'contracts/examples/valid/native-evidence.inkflip.json').read_bytes());a=report_digest(r)
        r['execution']['duration_ms']+=1;r['execution']['execution_id']='37dfed38-ed9a-436c-b4a8-c61dfb164694';self.assertEqual(report_digest(r),a)
        r['limitations'].append('Additional actual limitation.');self.assertNotEqual(report_digest(r),a)
    def test_normalization_preserves_meaning(self):
        for s in ('$1,000','-$100','not paid','لا','ﬁle','e\u0301','😀'):
            self.assertEqual(normalize(s)[0],s)
        self.assertNotEqual(normalize('$100')[0],normalize('$1,000')[0]);self.assertEqual(normalize(' A\n\tB ')[0],' A B ')
    def test_dag_and_ready(self):
        tasks=json.loads((ROOT/'execution/tasks.json').read_text());self.assertEqual(len(check_dag(tasks)),55)
        self.assertEqual([t['id'] for t in ready(tasks,{})],['T01'])
        out=ready(tasks,{'tasks':{'T01':{'status':'accepted'}}});self.assertTrue({'T02','T03','T05','T06'}<=set(t['id'] for t in out))
    def test_cycle_rejected(self):
        tasks=json.loads((ROOT/'execution/tasks.json').read_text());tasks[0]['dependencies']=['T55']
        with self.assertRaises(PackageError):check_dag(tasks)
    def test_unknown_dependency_rejected(self):
        tasks=json.loads((ROOT/'execution/tasks.json').read_text());tasks[0]['dependencies']=['T99']
        with self.assertRaises(PackageError):check_dag(tasks)
    def test_required_capability_cannot_be_rejected(self):
        tasks=json.loads((ROOT/'execution/tasks.json').read_text())
        with self.assertRaises(ValueError):ready(tasks,{'tasks':{'T09':{'status':'rejected_complete'}}})
    def test_broken_link_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'a.md').write_text('[missing](b.md)')
            with self.assertRaises(PackageError):check_links(p)
            (p/'b.md').write_text('# Existing\n');self.assertEqual(check_links(p),1)
            (p/'a.md').write_text('[missing anchor](b.md#not-there)')
            with self.assertRaises(PackageError):check_links(p)
    def test_manifest_tamper_rejected(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);data=b'original\n';(p/'a.txt').write_bytes(data);h=hashlib.sha256(data).hexdigest()
            (p/'FILE_MANIFEST.json').write_text(json.dumps({'self_reference_exclusions':['FILE_MANIFEST.json','SHA256SUMS.txt'],'files':[{'path':'a.txt','bytes':len(data),'sha256':h}]}));(p/'SHA256SUMS.txt').write_text(h+'  a.txt\n');self.assertEqual(check_integrity(p),1)
            (p/'a.txt').write_text('tampered\n')
            with self.assertRaises(PackageError):check_integrity(p)
    def test_bootstrap_refuses_nonempty(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'owned.txt').write_text('preserve')
            with self.assertRaises(ValueError):bootstrap(p)
            self.assertEqual((p/'owned.txt').read_text(),'preserve')
    def test_export_escapes_document_text(self):
        r=loads_strict((ROOT/'contracts/examples/valid/native-evidence.inkflip.json').read_bytes());r['findings'][0]['title']='<script>alert(1)</script>';seal(r);out=render(r)
        self.assertIn('&lt;script&gt;',out);self.assertNotIn('<script>',out)
        class Inspect(HTMLParser):
            def __init__(self):super().__init__();self.bad=[]
            def handle_starttag(self,tag,attrs):
                if tag in ('script','iframe','object','embed','form'):self.bad.append(tag)
                for k,v in attrs:
                    if k.startswith('on') or (k in ('src','href') and v and v.startswith(('http:','https:','javascript:'))):self.bad.append((k,v))
        parser=Inspect();parser.feed(out);self.assertEqual(parser.bad,[])
    def test_fixture_rebuild_in_temp(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable,str(ROOT/'probes/make_fixtures.py'),'--out',d],check=True,capture_output=True)
            for p in (ROOT/'fixtures').glob('*.pdf'):self.assertEqual(p.read_bytes(),(Path(d)/p.name).read_bytes())
    def test_generated_types_match(self):
        subprocess.run([sys.executable,str(ROOT/'tools/generate_types.py'),'--check'],check=True,capture_output=True)
if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests);result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
