"""Inkflip contract validation, canonical identity and normalization (Python port).

Exact port of the delivered reference ``planning/tools/contractlib.py`` to the
product layout. The single authoritative JSON Schema (Draft 2020-12, schema
version 1.0.0) is vendored byte-identically at ``schema/inkflip.schema.json``
by ``scripts/generate_contracts.py``; it is a trusted static resource compiled
once at module import. Untrusted report data is never used to build a schema.

Error surface: every rejection is a :class:`ContractError` carrying a stable
``code``. Two deliberate refinements over the reference module, which let the
underlying ``ValueError`` subclasses escape instead:

* malformed JSON syntax raises ``ContractError('JSON')`` (the reference lets
  ``json.JSONDecodeError`` propagate);
* invalid UTF-8 bytes raise ``ContractError('UNICODE')`` (the reference lets
  ``UnicodeDecodeError`` propagate).

Format checkers match the pinned ``jsonschema==4.26.0`` ``FormatChecker``
without format extras: ``uuid`` is enforced, ``date-time`` is unregistered
upstream and therefore not checked. Keep in parity with
``packages/contracts/src/core.ts``.

This is not a hostile-PDF sandbox or a complete image decoder.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).resolve().parent / 'schema' / 'inkflip.schema.json'
SCHEMA = json.loads(SCHEMA_PATH.read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_STRING_LENGTH = 28000000
MAX_DEPTH = 24
MAX_ASSET_BYTES = 20 * 1024 * 1024
MAX_ASSET_TOTAL = 20 * 1024 * 1024
MAX_PNG_PIXELS = 4000000
SAFE_INTEGER = 2 ** 53 - 1
SCHEMA_VERSION = '1.0.0'
CANONICALIZATION = 'inkflip-c14n-v1'


class ContractError(ValueError):
    """A contract rejection carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f'{code}: {message}')


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ContractError(code, message)


def loads_strict(data: str | bytes) -> Any:
    """Parse untrusted JSON bytes/text with duplicate-key and bound checks."""
    if isinstance(data, bytes):
        try:
            data = data.decode('utf-8', errors='strict')
        except UnicodeDecodeError as exc:
            raise ContractError('UNICODE', 'Invalid UTF-8 input') from exc
    require(len(data.encode('utf-8')) <= MAX_JSON_BYTES, 'SIZE', 'JSON too large')

    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'DUPLICATE_KEY', 'Repeated JSON member')
            out[k] = v
        return out

    def bad_constant(s):
        raise ContractError('NONFINITE', 'Nonfinite number')

    try:
        result = json.loads(
            data, object_pairs_hook=pairs, parse_constant=bad_constant
        )
    except RecursionError as exc:
        raise ContractError('DEPTH', 'JSON nesting') from exc
    except json.JSONDecodeError as exc:
        raise ContractError('JSON', str(exc)) from exc
    bounded(result)
    return result


def bounded(value: Any, depth: int = 0) -> None:
    """Enforce depth/size/string/number bounds on a decoded JSON value."""
    require(depth <= MAX_DEPTH, 'DEPTH', 'Nesting exceeds 24')
    if isinstance(value, str):
        require(len(value) <= MAX_STRING_LENGTH, 'SIZE', 'String too large')
        try:
            value.encode('utf-8', 'strict')
        except UnicodeError as exc:
            raise ContractError('UNICODE', 'Unpaired surrogate') from exc
    elif isinstance(value, (float, int)) and not isinstance(value, bool):
        require(
            not isinstance(value, int) or abs(value) <= SAFE_INTEGER,
            'NUMBER',
            'Unsafe integer',
        )
        require(math.isfinite(value), 'NONFINITE', 'Number must be finite')
        require(
            not isinstance(value, float)
            or not value.is_integer()
            or abs(value) <= SAFE_INTEGER,
            'NUMBER',
            'Unsafe integral float',
        )
    elif isinstance(value, list):
        for v in value:
            bounded(v, depth + 1)
    elif isinstance(value, dict):
        for k, v in value.items():
            bounded(k, depth + 1)
            bounded(v, depth + 1)


def canonical(value: Any) -> bytes:
    """inkflip-c14n-v1 tagged binary canonical form; not RFC 8785/JCS."""
    if value is None:
        return b'N'
    if value is True:
        return b'T'
    if value is False:
        return b'F'
    if isinstance(value, (int, float)):
        require(
            not isinstance(value, int) or abs(value) <= SAFE_INTEGER,
            'NUMBER',
            'Unsafe integer',
        )
        require(
            math.isfinite(value), 'NONFINITE', 'Cannot hash nonfinite number'
        )
        require(
            not isinstance(value, float)
            or not value.is_integer()
            or abs(value) <= SAFE_INTEGER,
            'NUMBER',
            'Unsafe integral float',
        )
        return b'D' + struct.pack('>d', 0.0 if value == 0 else float(value))
    if isinstance(value, str):
        raw = value.encode('utf-8', 'strict')
        return b'S' + struct.pack('>I', len(raw)) + raw
    if isinstance(value, list):
        return b'L' + struct.pack('>I', len(value)) + b''.join(
            canonical(x) for x in value
        )
    if isinstance(value, dict):
        require(
            all(isinstance(k, str) for k in value),
            'TYPE',
            'Object keys must be strings',
        )
        keys = sorted(value, key=lambda s: s.encode('utf-8'))
        return b'O' + struct.pack('>I', len(keys)) + b''.join(
            canonical(k) + canonical(value[k]) for k in keys
        )
    raise ContractError('TYPE', 'Unsupported canonical type')


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def report_digest(report: dict) -> str:
    """Report identity excluding report_id, execution timing and asset bytes."""
    p = copy.deepcopy(report)
    p.pop('report_id', None)
    for k in ('execution_id', 'started_at', 'duration_ms'):
        p['execution'].pop(k, None)
    for asset in p['assets']:
        asset.pop('data_base64', None)
    return digest(p)


def run_key(report: dict) -> str:
    return digest(
        {
            'document_sha256': report['document']['sha256'],
            'readers': report['readers'],
            'plan': report['plan'],
        }
    )


def seal(report: dict) -> dict:
    report['execution']['run_key'] = run_key(report)
    report['report_id'] = report_digest(report)
    return report


def occurrence_id(
    run_key: str,
    reader_id: str,
    page_index: int,
    ordinal: int,
    raw_source_locator: str,
) -> str:
    """Hash-based production occurrence identity.

    ``o_`` plus the first 32 hexadecimal characters of the canonical digest of
    ``{run_key, reader_id, page_index, ordinal, raw_source_locator}``. The text
    value is never the key; equal values at different positions stay separate.
    Imported readable IDs remain valid under schema v1; this generator is for
    newly produced occurrences.
    """
    return 'o_' + digest(
        {
            'run_key': run_key,
            'reader_id': reader_id,
            'page_index': page_index,
            'ordinal': ordinal,
            'raw_source_locator': raw_source_locator,
        }
    )[:32]


WS = frozenset(
    '\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680\u2000\u2001\u2002'
    '\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029'
    '\u202f\u205f\u3000'
)


def normalize(s: str) -> tuple[str, list[dict]]:
    """scalar-whitespace-v1: collapse Unicode White_Space runs to one space.

    Returns the normalized view plus the reversible raw map. Index units are
    Unicode code points, matching the TypeScript port exactly.
    """
    out = []
    maps = []
    i = 0
    n = 0
    while i < len(s):
        start = i
        white = s[i] in WS
        while i < len(s) and (s[i] in WS) == white:
            i += 1
        segment = ' ' if white else s[start:i]
        out.append(segment)
        maps.append(
            {
                'raw_start': start,
                'raw_end': i,
                'normalized_start': n,
                'normalized_end': n + len(segment),
                'operation': 'whitespace' if white else 'identity',
            }
        )
        n += len(segment)
    return ''.join(out), maps


def apply(m, p):
    a, b, c, d, e, f = m
    return (a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f)


def inverse(m):
    a, b, c, d, e, f = m
    det = a * d - b * c
    require(abs(det) > 1e-12, 'TRANSFORM', 'Singular transform')
    return [
        d / det,
        -b / det,
        -c / det,
        a / det,
        (c * f - d * e) / det,
        (b * e - a * f) / det,
    ]


def unique(items, code):
    ids = [x['id'] for x in items]
    require(len(ids) == len(set(ids)), code, 'Duplicate identifiers')
    return {x['id']: x for x in items}


def validate(value: dict, check_hashes: bool = True) -> None:
    """Full contract validation: bounds, schema, then semantic relations."""
    bounded(value)
    errs = list(VALIDATOR.iter_errors(value))
    require(not errs, 'SCHEMA', errs[0].message[:250] if errs else '')
    kind = value['kind']
    if kind == 'report':
        validate_report(value, check_hashes)
    elif kind == 'comparison':
        if value['status'] in ('improved', 'regressed'):
            require(
                value['acceptance_rules_sha256'] is not None,
                'RULE',
                'Judgment without rules',
            )
        for ch in value['changes']:
            if ch['status'] in ('improved', 'regressed'):
                require(
                    ch['rule_id'] is not None,
                    'RULE',
                    'Change judgment has no rule',
                )
        if (
            value['mode'] != 'document_versions'
            and value['left_document_sha256'] != value['right_document_sha256']
        ):
            require(
                value['status'] == 'incomparable',
                'DOCUMENT',
                'Different bytes are not the same file',
            )
    elif kind == 'worker_message':
        p = value['payload']
        e = value['event']
        require(
            not p['occurrences'] or e == 'chunk',
            'MESSAGE',
            'Occurrences outside chunk',
        )
        if e == 'check_terminal':
            require(
                p['status'] is not None and p['check_id'] is not None,
                'MESSAGE',
                'Terminal fields missing',
            )
        if e == 'chunk':
            require(
                p['check_id'] is not None and p['status'] is None,
                'MESSAGE',
                'Invalid chunk',
            )
        if e == 'progress':
            require(
                p['completed_units'] is not None,
                'MESSAGE',
                'Progress has no completed units',
            )
            if p['total_units'] is not None:
                require(
                    p['completed_units'] <= p['total_units'],
                    'MESSAGE',
                    'Invalid progress denominator',
                )
        require(
            (p['transfer_slot'] is None) == (p['transfer_bytes'] == 0),
            'MESSAGE',
            'Transfer metadata mismatch',
        )
    elif kind == 'corpus_manifest':
        keys = set()
        for entry in value['entries']:
            p = entry['source_path']
            require(
                not p.startswith(('/', '\\'))
                and '\\' not in p
                and ':' not in p
                and '..' not in Path(p).parts,
                'PATH',
                'Unsafe corpus path',
            )
            require(
                entry['key'] not in keys, 'ID', 'Duplicate corpus key'
            )
            keys.add(entry['key'])
    elif kind == 'acceptance_rules':
        unique(value['rules'], 'ID')
        for rule in value['rules']:
            need = {
                'expected_text': 'expected_text',
                'expected_occurrence_count': 'expected_count',
                'max_geometry_delta': 'max_delta_pt',
                'required_coverage': 'capability',
            }.get(rule['type'])
            if need:
                require(rule[need] is not None, 'RULE', 'Rule operand absent')


def validate_report(r: dict, check_hashes: bool = True) -> None:
    doc = r['document']
    readers = unique(r['readers'], 'ID')
    trans = unique(r['transforms'], 'ID')
    occ = unique(r['occurrences'], 'ID')
    findings = unique(r['findings'], 'ID')
    assets = unique(r['assets'], 'ID')
    pages = {p['index']: p for p in r['pages']}
    require(len(pages) == len(r['pages']), 'PAGE', 'Duplicate page')
    require(
        all(0 <= i < doc['page_count'] for i in pages),
        'PAGE',
        'Page outside document',
    )
    regions = unique(r['plan']['regions'], 'ID')
    plans = unique(r['plan']['checks'], 'ID')
    checks = unique(r['checks'], 'ID')
    require(
        set(plans) == set(checks),
        'COVERAGE',
        'Planned and terminal check IDs differ',
    )
    require(
        set(r['plan']['selected_pages']) <= set(pages),
        'PAGE',
        'Selected page metadata absent',
    )
    for p in pages.values():
        require(
            p['raw_to_canonical_transform_id'] in trans,
            'REFERENCE',
            'Missing page transform',
        )
        for b in (p['media_box'], p['crop_box'], p['effective_view_box']):
            if b:
                require(
                    b[2] > b[0] and b[3] > b[1], 'GEOMETRY', 'Invalid page box'
                )
        u = p['user_unit']
        v = p['effective_view_box']
        expected = [u * (v[2] - v[0]), u * (v[3] - v[1])]
        require(
            all(
                abs(a - b) <= 1e-5
                for a, b in zip(expected, p['canonical_size_pt'])
            ),
            'GEOMETRY',
            'Canonical dimensions inconsistent',
        )
        expected_c = [u, 0, 0, -u, -u * v[0], u * v[3]]
        c = trans[p['raw_to_canonical_transform_id']]
        require(
            c['page_index'] == p['index']
            and all(
                abs(a - b) <= 1e-5 for a, b in zip(c['matrix'], expected_c)
            ),
            'TRANSFORM',
            'Wrong raw-to-canonical matrix',
        )
    for t in trans.values():
        require(t['page_index'] in pages, 'PAGE', 'Transform page absent')
        inv = inverse(t['matrix'])
        require(
            all(abs(a - b) <= 1e-5 for a, b in zip(inv, t['inverse'])),
            'TRANSFORM',
            'Incorrect inverse',
        )

    def geometry(g, page_index=None):
        require(
            set(g['transform_ids']) <= set(trans),
            'REFERENCE',
            'Missing geometry transform',
        )
        require(
            (g['polygon'] is None) == (g['precision'] in ('unknown', 'page_only')),
            'GEOMETRY',
            'Precision/polygon conflict',
        )
        if page_index is not None:
            require(
                all(
                    trans[t]['page_index'] == page_index
                    for t in g['transform_ids']
                ),
                'TRANSFORM',
                'Geometry crosses transform pages',
            )
        if g['polygon'] is not None:
            pts = g['polygon']
            area = sum(
                pts[i][0] * pts[(i + 1) % len(pts)][1]
                - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts))
            )
            require(abs(area) > 1e-12, 'GEOMETRY', 'Degenerate source polygon')

    for region in regions.values():
        require(region['page_index'] in pages, 'PAGE', 'Region page absent')
        geometry(region['geometry'], region['page_index'])
    for p in plans.values():
        require(
            p['page_index'] in r['plan']['selected_pages'],
            'COVERAGE',
            'Check outside selected pages',
        )
        require(
            set(p['reader_ids']) <= set(readers),
            'REFERENCE',
            'Unknown planned reader',
        )
        require(
            p['region_id'] is None or p['region_id'] in regions,
            'REFERENCE',
            'Unknown planned region',
        )
        require(
            p['region_id'] is None
            or regions[p['region_id']]['page_index'] == p['page_index'],
            'PAGE',
            'Plan region crosses page',
        )
    for o in occ.values():
        require(
            o['reader_id'] in readers and o['page_index'] in pages,
            'REFERENCE',
            'Unknown occurrence reader/page',
        )
        geometry(o['geometry'], o['page_index'])
        n, m = normalize(o['raw_text'])
        require(
            o['normalized_text'] == n and o['normalization_map'] == m,
            'NORMALIZATION',
            'Raw/normalized view mismatch',
        )
        require(
            o['source_asset_id'] is None or o['source_asset_id'] in assets,
            'REFERENCE',
            'Unknown occurrence asset',
        )
        if o['engine_score']:
            s = o['engine_score']
            require(
                s['scale_min'] <= s['value'] <= s['scale_max'],
                'SCORE',
                'Score outside own scale',
            )
    for c in checks.values():
        require(
            set(c['retained_occurrence_ids']) <= set(occ),
            'REFERENCE',
            'Check occurrence absent',
        )
        require(
            len(c['retained_occurrence_ids'])
            == len(set(c['retained_occurrence_ids'])),
            'ID',
            'Repeated check occurrence reference',
        )
        require(
            c['produced_occurrence_count'] >= len(c['retained_occurrence_ids']),
            'COVERAGE',
            'Retained more than produced',
        )
        if c['status'] != 'completed':
            require(
                c['reason'] is not None,
                'COVERAGE',
                'Incomplete check lacks reason',
            )
        p = plans[c['id']]
        for oid in c['retained_occurrence_ids']:
            require(
                occ[oid]['reader_id'] in p['reader_ids']
                and occ[oid]['page_index'] == p['page_index'],
                'REFERENCE',
                'Check/occurrence binding mismatch',
            )
    for f in findings.values():
        require(f['page_index'] in pages, 'PAGE', 'Finding page absent')
        require(
            set(f['occurrence_ids']) <= set(occ)
            and set(f['check_ids']) <= set(checks),
            'REFERENCE',
            'Finding references absent',
        )
        require(
            f['region_id'] is None or f['region_id'] in regions,
            'REFERENCE',
            'Finding region absent',
        )
        require(
            f['region_id'] is None
            or regions[f['region_id']]['page_index'] == f['page_index'],
            'PAGE',
            'Finding region crosses page',
        )
        for oid in f['occurrence_ids']:
            require(
                occ[oid]['page_index'] == f['page_index'],
                'PAGE',
                'Finding crosses page',
            )
        if f['kind'] == 'reading_difference':
            require(
                len({occ[o]['reader_id'] for o in f['occurrence_ids']}) >= 2,
                'EVIDENCE',
                'Difference requires two actual readings',
            )
            require(
                all(
                    checks[c]['status'] == 'completed'
                    for c in f['check_ids']
                ),
                'EVIDENCE',
                'Difference cites incomplete read',
            )
            supported = {
                oid
                for cid in f['check_ids']
                for oid in checks[cid]['retained_occurrence_ids']
            }
            require(
                set(f['occurrence_ids']) <= supported,
                'EVIDENCE',
                'Difference occurrence lacks cited completed-read support',
            )
        if f['alignment'] == 'unique':
            require(
                f['region_id'] is not None
                and all(
                    occ[o]['geometry']['polygon'] is not None
                    for o in f['occurrence_ids']
                ),
                'GEOMETRY',
                'Unique match without geometry',
            )
    unique(r['annotations'], 'ID')
    for a in r['annotations']:
        require(a['page_index'] in pages, 'PAGE', 'Annotation page absent')
        require(
            a['finding_id'] is None or a['finding_id'] in findings,
            'REFERENCE',
            'Annotation finding absent',
        )
        require(
            a['finding_id'] is None
            or findings[a['finding_id']]['page_index'] == a['page_index'],
            'PAGE',
            'Annotation finding crosses page',
        )
    complete = sum(c['status'] == 'completed' for c in checks.values())
    status = r['execution']['status']
    if status == 'complete':
        require(
            complete == len(checks),
            'COVERAGE',
            'Complete run includes incomplete check',
        )
    elif status == 'failed':
        require(
            complete == 0
            and any(
                c['status'] in ('failed', 'timeout') for c in checks.values()
            ),
            'COVERAGE',
            'Failed state inconsistent',
        )
    elif status == 'partial':
        require(
            complete < len(checks),
            'COVERAGE',
            'Partial state has no incomplete checks',
        )
    total = 0
    for a in assets.values():
        try:
            data = base64.b64decode(a['data_base64'], validate=True)
        except Exception as exc:
            raise ContractError('ASSET', 'Invalid base64') from exc
        total += len(data)
        require(
            len(data) == a['byte_length']
            and hashlib.sha256(data).hexdigest() == a['sha256'],
            'ASSET',
            'Hash/length mismatch',
        )
        require(len(data) <= MAX_ASSET_BYTES, 'SIZE', 'Asset too large')
        if a['media_type'] == 'image/png':
            require(
                a['purpose'] in ('crop', 'page_render')
                and a['page_index'] in pages,
                'ASSET',
                'Image purpose/page mismatch',
            )
            require(
                data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24,
                'ASSET',
                'Not PNG',
            )
            wh = list(struct.unpack('>II', data[16:24]))
            require(
                wh == a['pixel_size'] and wh[0] * wh[1] <= MAX_PNG_PIXELS,
                'ASSET',
                'PNG size mismatch',
            )
        elif a['media_type'] == 'application/pdf':
            require(
                a['purpose'] == 'source_pdf' and data[:5] == b'%PDF-',
                'ASSET',
                'Wrong PDF purpose/header',
            )
        if a['geometry']:
            geometry(a['geometry'], a['page_index'])
    require(total <= MAX_ASSET_TOTAL, 'SIZE', 'Decoded asset total too large')
    included = set(r['export']['included'])
    require(
        {'document_hash', 'settings', 'coverage'} <= included,
        'PRIVACY',
        'Required metadata disclosure absent',
    )
    require(
        not r['occurrences'] or 'selected_text' in included,
        'PRIVACY',
        'Undisclosed reading text',
    )
    require(
        not r['annotations'] or 'annotations' in included,
        'PRIVACY',
        'Undisclosed annotations',
    )
    require(
        not any(a['purpose'] == 'page_render' for a in assets.values())
        or 'page_renders' in included,
        'PRIVACY',
        'Undisclosed full-page image',
    )
    source = doc['source_asset_id']
    if source is not None:
        require(
            source in assets
            and assets[source]['sha256'] == doc['sha256']
            and assets[source]['byte_length'] == doc['byte_length'],
            'SOURCE',
            'Original bytes not bound',
        )
        require(
            assets[source]['media_type'] == 'application/pdf'
            and assets[source]['purpose'] == 'source_pdf',
            'SOURCE',
            'Source is not a PDF asset',
        )
        require(
            'source_pdf' in r['export']['included'],
            'PRIVACY',
            'Undisclosed original',
        )
    if r['export']['mode'] == 'replayable':
        require(
            source is not None
            and r['export']['replay'] == 'source_included_environment_required',
            'REPLAY',
            'Replayable without source',
        )
    if r['export']['replay'] == 'source_included_environment_required':
        require(source is not None, 'REPLAY', 'Source unavailable')
    require(
        (doc['display_name'] is not None)
        == ('filename' in r['export']['included']),
        'PRIVACY',
        'Filename disclosure mismatch',
    )
    require(
        not any(a['purpose'] == 'source_pdf' for a in assets.values())
        or 'source_pdf' in r['export']['included'],
        'PRIVACY',
        'Undisclosed PDF asset',
    )
    require(
        not any(a['purpose'] == 'crop' for a in assets.values())
        or 'crops' in r['export']['included'],
        'PRIVACY',
        'Undisclosed crop',
    )
    if check_hashes:
        require(
            r['execution']['run_key'] == run_key(r), 'HASH', 'Run key mismatch'
        )
        require(
            r['report_id'] == report_digest(r), 'HASH', 'Report digest mismatch'
        )
