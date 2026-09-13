"""Immutable baselines and stored-run comparison (T34)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from inkflip.baselines.models import (
    BaselineError,
    BaselineOverwriteError,
    ComparisonResult,
)
from inkflip.cli.html import render_html_comparison
from inkflip.contracts import core
from inkflip.runtime.artifacts import atomic_write_bytes

EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_PARTIAL = 3
EXIT_MISSING_INPUT = 4
EXIT_REGRESSION = 5
EXIT_INCOMPARABLE = 6

_TERMINAL_OK = {"completed"}
_PRECISION_GEOM = {"exact", "estimated"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return core.loads_strict(path.read_bytes())
    except core.ContractError as exc:
        raise BaselineError(f"Malformed JSON at {path}: {exc}") from exc
    except OSError as exc:
        raise BaselineError(f"Cannot read {path}: {exc}") from exc


def _read_json_file(path: Path, label: str) -> Any:
    """Read one configuration JSON file, translating operator input faults.

    A missing, unreadable or malformed configuration file (run index, run
    identity, rules) is an input fault, never an unexpected internal error.
    Translating it here keeps the documented CLI exit-2 contract for invalid
    configuration while an internal invariant break still surfaces as a
    generic failure upstream.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BaselineError(f"Cannot read {label} {path}: {exc}") from exc
    try:
        return core.loads_strict(raw)
    except core.ContractError as exc:
        raise BaselineError(f"Invalid {label} {path}: {exc}") from exc


def _require_report(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("kind") != "report":
        raise BaselineError(f"{path} is not a report")
    try:
        core.validate(data)
    except core.ContractError as exc:
        raise BaselineError(f"Invalid report {path}: {exc}") from exc
    return data


def _run_reports(run_dir: Path) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    reports_dir = run_dir / "reports"
    search = []
    if reports_dir.is_dir():
        search.extend(sorted(reports_dir.glob("*.json")))
    search.extend(sorted(run_dir.glob("*.inkflip.json")))
    for path in search:
        if path.name in {"index.json", "identity.json", "rules.json"}:
            continue
        data = _load_json(path)
        reports[path.stem.replace(".inkflip", "")] = _require_report(data, path)
    return reports


def _identity(run_dir: Path) -> dict[str, Any]:
    identity_path = run_dir / "identity.json"
    if identity_path.is_file():
        return _read_json_file(identity_path, "run identity")
    return {}


def _sidecar_dir(baseline_path: Path) -> Path:
    return baseline_path.with_suffix(baseline_path.suffix + ".reports")


def create_baseline(
    run_dir: Path,
    rules_path: Path | None,
    out_path: Path,
    approved_by: str,
    rationale: str,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    out_path = Path(out_path)
    sidecar = _sidecar_dir(out_path)
    if out_path.exists() or sidecar.exists():
        raise BaselineOverwriteError(
            f"Baseline already exists at {out_path}. Overwrite and auto-refresh are prohibited; "
            "create a new path."
        )
    if not approved_by or not approved_by.strip():
        raise BaselineError("Approved-by reviewer label is required (explicit approval required)")
    approved_by = approved_by.strip()
    if len(approved_by) > 100:
        raise BaselineError("Approved-by label exceeds 100 characters")
    if not rationale or not rationale.strip():
        raise BaselineError("Approval rationale is required")
    rationale = rationale.strip()
    if len(rationale) > 2000:
        raise BaselineError("Approval rationale exceeds 2000 characters")
    if not run_dir.is_dir():
        raise BaselineError(f"Run directory not found: {run_dir}")
    index_path = run_dir / "index.json"
    if not index_path.is_file():
        raise BaselineError(f"Run directory missing index.json: {run_dir}")
    index_data = _read_json_file(index_path, "run index")
    if index_data.get("status") != "complete" and not allow_incomplete:
        raise BaselineError(
            f"Run status is {index_data.get('status')!r}. Incomplete runs cannot become baselines."
        )
    reports = _run_reports(run_dir)
    if not reports:
        raise BaselineError(f"No valid report files found in run directory {run_dir}")
    report_ids = sorted(report["report_id"] for report in reports.values())
    identity = _identity(run_dir)
    rules_sha = None
    if rules_path:
        rules_path = Path(rules_path)
        try:
            rules_bytes = rules_path.read_bytes()
        except OSError as exc:
            raise BaselineError(f"Cannot read rules file {rules_path}: {exc}") from exc
        try:
            rules_data = core.loads_strict(rules_bytes)
            core.validate(rules_data)
        except core.ContractError as exc:
            raise BaselineError(f"Invalid rules file {rules_path}: {exc}") from exc
        if rules_data.get("kind") != "acceptance_rules":
            raise BaselineError("Rules file is not kind acceptance_rules")
        rules_sha = _sha256_bytes(rules_bytes)
    corpus_sha = identity.get("corpus_manifest_sha256")
    profile_sha = identity.get("profile_sha256")
    if not corpus_sha or not profile_sha:
        raise BaselineError(
            "Run is missing identity.json with corpus_manifest_sha256 and profile_sha256; "
            "constant placeholder identities are refused"
        )
    material = {
        "corpus_manifest_sha256": corpus_sha,
        "profile_sha256": profile_sha,
        "report_ids": report_ids,
        "rules_sha256": rules_sha,
        "approved_by": approved_by,
        "rationale": rationale,
    }
    baseline_id = core.digest(material)
    record = {
        "kind": "baseline",
        "schema_version": "1.0.0",
        "id": baseline_id,
        "corpus_manifest_sha256": corpus_sha,
        "profile_sha256": profile_sha,
        "report_ids": report_ids,
        "rules_sha256": rules_sha,
        "approved_by": approved_by,
        "rationale": rationale,
    }
    core.validate(record)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar.mkdir(parents=False)
    for key, report in reports.items():
        atomic_write_bytes(
            sidecar / f"{key}.json",
            (json.dumps(report, indent=2) + "\n").encode("utf-8"),
        )
    atomic_write_bytes(out_path, (json.dumps(record, indent=2) + "\n").encode("utf-8"))
    return record


def _load_baseline_bundle(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    data = _load_json(path)
    if data.get("kind") != "baseline":
        raise BaselineError(f"{path} is not a baseline")
    core.validate(data)
    sidecar = _sidecar_dir(path)
    if not sidecar.is_dir():
        raise BaselineError(f"Baseline {path} is missing verified backing reports at {sidecar}")
    reports = {}
    for report_path in sorted(sidecar.glob("*.json")):
        report = _require_report(_load_json(report_path), report_path)
        reports[report_path.stem] = report
    actual_ids = sorted(report["report_id"] for report in reports.values())
    if actual_ids != sorted(data["report_ids"]):
        raise BaselineError(
            "Baseline backing reports do not match recorded report_ids (tampering or lost files)"
        )
    return data, reports


def _load_side(path: Path) -> tuple[str, dict[str, dict[str, Any]], dict[str, Any] | None]:
    path = Path(path)
    if not path.exists():
        raise BaselineError(f"Comparison target not found: {path}")
    if path.is_file():
        data = _load_json(path)
        if data.get("kind") == "baseline":
            baseline, reports = _load_baseline_bundle(path)
            return "baseline", reports, baseline
        if data.get("kind") == "report":
            report = _require_report(data, path)
            return "report", {path.stem.replace(".inkflip", ""): report}, None
        raise BaselineError(f"Unsupported comparison input kind {data.get('kind')!r} at {path}")
    reports = _run_reports(path)
    identity = _identity(path)
    intended = identity.get("intended_keys")
    if intended:
        for key in intended:
            reports.setdefault(key, None)  # type: ignore[arg-type]
    return "run", reports, identity


def _rule_applies(rule: dict[str, Any], report: dict[str, Any]) -> bool:
    if rule.get("document_sha256") != report["document"]["sha256"]:
        return False
    return True


def _scoped_occurrences(rule: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    occs = [
        occ
        for occ in report.get("occurrences", [])
        if occ.get("page_index") == rule.get("page_index")
    ]
    reader_id = rule.get("reader_id")
    if reader_id:
        occs = [occ for occ in occs if occ.get("reader_id") == reader_id]
    region_id = rule.get("region_id")
    if region_id:
        check_ids = {
            check["id"]
            for check in report.get("plan", {}).get("checks", [])
            if check.get("region_id") == region_id
        }
        retained = set()
        for check in report.get("checks", []):
            if check["id"] in check_ids:
                retained.update(check.get("retained_occurrence_ids") or [])
        occs = [occ for occ in occs if occ["id"] in retained]
    return occs


def _scoped_checks(rule: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    plans = {plan["id"]: plan for plan in report.get("plan", {}).get("checks", [])}
    for check in report.get("checks", []):
        plan = plans.get(check["id"], {})
        if plan.get("page_index") != rule.get("page_index"):
            continue
        if rule.get("reader_id") and rule["reader_id"] not in (plan.get("reader_ids") or []):
            continue
        if rule.get("capability") and plan.get("capability") != rule.get("capability"):
            continue
        if rule.get("region_id") and plan.get("region_id") != rule.get("region_id"):
            continue
        checks.append(check)
    return checks


def _geometry_delta(left: dict, right: dict) -> float | None:
    lg = left.get("geometry") or {}
    rg = right.get("geometry") or {}
    if lg.get("precision") not in _PRECISION_GEOM or rg.get("precision") not in _PRECISION_GEOM:
        return None
    lp = lg.get("polygon")
    rp = rg.get("polygon")
    if not lp or not rp or len(lp) != len(rp):
        return None
    return max(
        ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a, b in zip(lp, rp)
    )


def evaluate_rules(
    left: dict[str, Any],
    right: dict[str, Any],
    rules: dict[str, Any] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    violations: list[str] = []
    changes: list[dict[str, Any]] = []
    if not rules:
        return violations, changes
    for rule in rules.get("rules", []):
        if not _rule_applies(rule, right) and not _rule_applies(rule, left):
            continue
        target = right if _rule_applies(rule, right) else None
        if target is None:
            continue
        rtype = rule.get("type")
        page_occs = _scoped_occurrences(rule, target)
        page_text = "\n".join(occ.get("raw_text", "") for occ in page_occs)
        if rtype == "expected_text" and rule.get("expected_text") is not None:
            if rule["expected_text"] not in page_text:
                violations.append(
                    f"Rule {rule.get('id')!r} [expected_text] failed on page {rule.get('page_index')}"
                )
                changes.append(_change(rule, "text", "regressed", page_occs, "expected_text missing"))
        elif rtype == "stable_reading":
            left_occs = _scoped_occurrences(rule, left)
            left_text = "\n".join(occ.get("raw_text", "") for occ in left_occs)
            if page_text != left_text:
                violations.append(
                    f"Rule {rule.get('id')!r} [stable_reading] violated on page {rule.get('page_index')}"
                )
                changes.append(_change(rule, "text", "regressed", page_occs, "stable_reading changed", left_occs))
        elif rtype == "required_coverage":
            scoped_checks = _scoped_checks(rule, target)
            if not scoped_checks or not any(check["status"] in _TERMINAL_OK for check in scoped_checks):
                violations.append(
                    f"Rule {rule.get('id')!r} [required_coverage] failed on page {rule.get('page_index')}"
                )
                changes.append(_change(rule, "coverage", "regressed", page_occs, "required coverage missing"))
        elif rtype == "expected_occurrence_count" and rule.get("expected_count") is not None:
            if len(page_occs) != rule["expected_count"]:
                violations.append(
                    f"Rule {rule.get('id')!r} [expected_occurrence_count] expected "
                    f"{rule['expected_count']}, got {len(page_occs)}"
                )
                changes.append(_change(rule, "coverage", "regressed", page_occs, "occurrence count mismatch"))
        elif rtype == "max_geometry_delta" and rule.get("max_delta_pt") is not None:
            left_occs = _scoped_occurrences(rule, left)
            comparable = False
            over = False
            for locc, rocc in zip(left_occs, page_occs):
                delta = _geometry_delta(locc, rocc)
                if delta is None:
                    continue
                comparable = True
                if delta > rule["max_delta_pt"]:
                    over = True
            if not comparable:
                changes.append(
                    _change(rule, "geometry", "incomparable", page_occs, "geometry not comparable", left_occs)
                )
            elif over:
                violations.append(
                    f"Rule {rule.get('id')!r} [max_geometry_delta] exceeded {rule['max_delta_pt']}"
                )
                changes.append(_change(rule, "geometry", "regressed", page_occs, "geometry delta exceeded", left_occs))
    return violations, changes


def _change(rule, kind, status, right_occs, explanation, left_occs=None):
    left_occs = left_occs or []
    return {
        "id": f"chg_{rule.get('id', 'rule')}"[:96],
        "kind": kind,
        "page_index": rule.get("page_index"),
        "left_occurrence_ids": [occ["id"] for occ in left_occs][:32],
        "right_occurrence_ids": [occ["id"] for occ in right_occs][:32],
        "status": status,
        "rule_id": rule.get("id"),
        "explanation": explanation,
    }


def _align_pages(left: dict, right: dict) -> list[dict[str, Any]]:
    from inkflip.compare_bridge import BridgeError, CompareBridge

    pages = sorted(
        set(occ["page_index"] for occ in left.get("occurrences", []))
        | set(occ["page_index"] for occ in right.get("occurrences", []))
    )
    payload = []
    for page_index in pages:
        payload.append(
            {
                "page_index": page_index,
                "left": [
                    {
                        "id": occ["id"],
                        "page_index": occ["page_index"],
                        "ordinal": occ["ordinal"],
                        "raw": occ["raw_text"],
                        "normalized_text": occ["normalized_text"],
                        "geometry": occ["geometry"],
                    }
                    for occ in left.get("occurrences", [])
                    if occ["page_index"] == page_index
                ],
                "right": [
                    {
                        "id": occ["id"],
                        "page_index": occ["page_index"],
                        "ordinal": occ["ordinal"],
                        "raw": occ["raw_text"],
                        "normalized_text": occ["normalized_text"],
                        "geometry": occ["geometry"],
                    }
                    for occ in right.get("occurrences", [])
                    if occ["page_index"] == page_index
                ],
            }
        )
    if not payload:
        return []
    try:
        result = CompareBridge().align(payload)
    except BridgeError as exc:
        raise BaselineError(f"Comparison bridge failed: {exc.reason}") from exc
    return result.result.get("results") or []


def _occurrence_ids(values: list[str] | None) -> list[str]:
    return [item for item in (values or []) if isinstance(item, str) and item][:32]


def _changes_from_alignment(alignments: list[dict], left: dict, right: dict) -> tuple[list[dict], bool]:
    changes = []
    has_change = False
    left_checks = {check["id"]: check["status"] for check in left.get("checks", [])}
    right_checks = {check["id"]: check["status"] for check in right.get("checks", [])}
    if left_checks != right_checks:
        has_change = True
        changes.append(
            {
                "id": "chg_check_status",
                "kind": "coverage",
                "page_index": None,
                "left_occurrence_ids": [],
                "right_occurrence_ids": [],
                "status": "changed",
                "rule_id": None,
                "explanation": "Terminal check statuses differ between stored runs",
            }
        )
    left_by_id = {occ["id"]: occ for occ in left.get("occurrences", [])}
    right_by_id = {occ["id"]: occ for occ in right.get("occurrences", [])}
    for index, alignment in enumerate(alignments):
        page_index = alignment.get("page_index", index)
        matches = alignment.get("matches") or []
        page_level = alignment.get("page_level") or {}
        left_unmatched = _occurrence_ids(page_level.get("left_occurrence_ids"))
        right_unmatched = _occurrence_ids(page_level.get("right_occurrence_ids"))
        if alignment.get("order_differences"):
            has_change = True
            changes.append(
                {
                    "id": f"chg_align_p{page_index}",
                    "kind": "order",
                    "page_index": page_index,
                    "left_occurrence_ids": left_unmatched,
                    "right_occurrence_ids": right_unmatched,
                    "status": "changed",
                    "rule_id": None,
                    "explanation": "Alignment observed reordered occurrences",
                }
            )
        for match in matches:
            left_ids = _occurrence_ids(match.get("left_occurrence_ids"))
            right_ids = _occurrence_ids(match.get("right_occurrence_ids"))
            left_text = "\n".join(
                left_by_id[oid]["normalized_text"] for oid in left_ids if oid in left_by_id
            )
            right_text = "\n".join(
                right_by_id[oid]["normalized_text"] for oid in right_ids if oid in right_by_id
            )
            if left_text != right_text:
                has_change = True
                changes.append(
                    {
                        "id": f"chg_text_p{page_index}_{len(changes)}",
                        "kind": "text",
                        "page_index": page_index,
                        "left_occurrence_ids": left_ids,
                        "right_occurrence_ids": right_ids,
                        "status": "changed",
                        "rule_id": None,
                        "explanation": "Aligned occurrences differ in normalized text",
                    }
                )
    left_text = "\n".join(o.get("raw_text", "") for o in left.get("occurrences", []))
    right_text = "\n".join(o.get("raw_text", "") for o in right.get("occurrences", []))
    if left_text != right_text:
        has_change = True
        if not any(change["kind"] == "text" for change in changes):
            changes.append(
                {
                    "id": "chg_raw_text",
                    "kind": "text",
                    "page_index": 0,
                    "left_occurrence_ids": [o["id"] for o in left.get("occurrences", [])][:32],
                    "right_occurrence_ids": [o["id"] for o in right.get("occurrences", [])][:32],
                    "status": "changed",
                    "rule_id": None,
                    "explanation": "Extracted text differs between stored runs",
                }
            )
    return changes, has_change


def _coverage_lost(left: dict, right: dict) -> bool:
    left_ok = [c for c in left.get("checks", []) if c.get("status") in _TERMINAL_OK]
    right_ok = [c for c in right.get("checks", []) if c.get("status") in _TERMINAL_OK]
    if len(right_ok) < len(left_ok):
        return True
    if len(right.get("occurrences", [])) < len(left.get("occurrences", [])):
        return True
    return False


def _incompatible_readers(left: dict, right: dict) -> bool:
    left_ids = sorted(r.get("id") for r in left.get("readers", []))
    right_ids = sorted(r.get("id") for r in right.get("readers", []))
    left_settings = [r.get("settings") for r in left.get("readers", [])]
    right_settings = [r.get("settings") for r in right.get("readers", [])]
    return left_ids != right_ids or left_settings != right_settings


def _build_comparison(
    left: dict | None,
    right: dict | None,
    key: str,
    rules: dict | None,
    mode: str,
    alignments: list[dict] | None = None,
) -> tuple[dict, int, bool, bool]:
    limitations = ["Comparison uses the shared Node alignment bridge and declared acceptance rules."]
    if left is None and right is None:
        raise BaselineError(f"Both sides missing for key {key}")
    if left is None or right is None:
        present = left or right
        absent_side = "left" if left is None else "right"
        policy = (rules or {}).get("policy") or {}
        rules_sha = _sha256_bytes(json.dumps(rules, sort_keys=True).encode()) if rules else None
        status = "errored"
        exit_code = EXIT_PARTIAL
        if rules and (policy.get("fail_on_coverage_loss") or policy.get("fail_on_error")):
            status = "regressed"
            exit_code = EXIT_REGRESSION
        change_id = re.sub(r"[^a-z0-9_-]+", "-", f"chg_missing_{key}".lower()).strip("-")[:96]
        if not change_id or not change_id[0].isalpha():
            change_id = "chg_missing_key"
        comparison = {
            "kind": "comparison",
            "schema_version": "1.0.0",
            "id": "0" * 64,
            "left_report_id": left["report_id"] if left else "0" * 64,
            "right_report_id": right["report_id"] if right else "0" * 64,
            "left_document_sha256": present["document"]["sha256"],
            "right_document_sha256": present["document"]["sha256"],
            "mode": mode,
            "status": status,
            "acceptance_rules_sha256": rules_sha,
            "changes": [
                {
                    "id": change_id,
                    "kind": "error",
                    "page_index": None,
                    "left_occurrence_ids": [],
                    "right_occurrence_ids": [],
                    "status": "errored",
                    "rule_id": None,
                    "explanation": f"Corpus key {key} is missing on the {absent_side} side",
                }
            ],
            "limitations": limitations,
        }
        comparison["id"] = core.digest(comparison)
        core.validate(comparison)
        return comparison, exit_code, True, False
    if left["document"]["sha256"] != right["document"]["sha256"] and mode != "document_versions":
        comparison = {
            "kind": "comparison",
            "schema_version": "1.0.0",
            "id": "0" * 64,
            "left_report_id": left["report_id"],
            "right_report_id": right["report_id"],
            "left_document_sha256": left["document"]["sha256"],
            "right_document_sha256": right["document"]["sha256"],
            "mode": mode,
            "status": "incomparable",
            "acceptance_rules_sha256": _sha256_bytes(json.dumps(rules, sort_keys=True).encode()) if rules else None,
            "changes": [
                {
                    "id": "chg_document",
                    "kind": "configuration",
                    "page_index": None,
                    "left_occurrence_ids": [],
                    "right_occurrence_ids": [],
                    "status": "incomparable",
                    "rule_id": None,
                    "explanation": "Document bytes differ; runs are not the same file",
                }
            ],
            "limitations": limitations,
        }
        comparison["id"] = core.digest(comparison)
        core.validate(comparison)
        return comparison, EXIT_INCOMPARABLE, False, True
    if _incompatible_readers(left, right) and mode == "reader_upgrade":
        # Version-isolated upgrades are expected to differ in reader identity.
        pass
    violations, rule_changes = evaluate_rules(left, right, rules)
    align_changes, has_change = _changes_from_alignment(alignments or [], left, right)
    lost = _coverage_lost(left, right)
    if lost:
        has_change = True
        align_changes.append(
            {
                "id": "chg_coverage",
                "kind": "coverage",
                "page_index": None,
                "left_occurrence_ids": [],
                "right_occurrence_ids": [],
                "status": "changed",
                "rule_id": None,
                "explanation": "Coverage decreased; lost coverage cannot count as improvement",
            }
        )
    failed = any(c.get("status") in {"failed", "timeout"} for c in right.get("checks", []))
    status = "unchanged"
    exit_code = EXIT_OK
    policy = (rules or {}).get("policy") or {}
    if violations:
        status = "regressed"
        exit_code = EXIT_REGRESSION
    elif lost and policy.get("fail_on_coverage_loss"):
        status = "regressed"
        exit_code = EXIT_REGRESSION
    elif failed and policy.get("fail_on_error"):
        status = "regressed"
        exit_code = EXIT_REGRESSION
    elif has_change or rule_changes:
        status = "changed"
        exit_code = EXIT_OK
    changes = []
    seen = set()
    for change in rule_changes + align_changes:
        ident = change["id"]
        if ident in seen:
            continue
        seen.add(ident)
        changes.append(change)
    if not changes:
        changes.append(
            {
                "id": "chg_none",
                "kind": "text",
                "page_index": 0,
                "left_occurrence_ids": [],
                "right_occurrence_ids": [],
                "status": "unchanged",
                "rule_id": None,
                "explanation": "No text, geometry, coverage or rule difference observed",
            }
        )
    rules_sha = _sha256_bytes(json.dumps(rules, sort_keys=True).encode()) if rules else None
    comparison = {
        "kind": "comparison",
        "schema_version": "1.0.0",
        "id": "0" * 64,
        "left_report_id": left["report_id"],
        "right_report_id": right["report_id"],
        "left_document_sha256": left["document"]["sha256"],
        "right_document_sha256": right["document"]["sha256"],
        "mode": mode,
        "status": status,
        "acceptance_rules_sha256": rules_sha,
        "changes": changes,
        "limitations": limitations,
    }
    comparison["id"] = core.digest(comparison)
    core.validate(comparison)
    return comparison, exit_code, lost, False


def write_pair_comparison(
    left: dict,
    right: dict,
    out_dir: Path,
    mode: str = "reader",
    rules: dict | None = None,
) -> int:
    alignments = _align_pages(left, right)
    comparison, code, _lost, _incomp = _build_comparison(left, right, "pair", rules, mode, alignments)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(out_dir / "comparison.json", (json.dumps(comparison, indent=2) + "\n").encode())
    atomic_write_bytes(out_dir / "comparison.html", render_html_comparison(comparison).encode())
    return code


def compare(
    left_path: Path,
    right_path: Path,
    rules_path: Path | None = None,
    out_dir: Path | None = None,
    fail_on_changed: bool = False,
    mode: str = "reader_upgrade",
) -> ComparisonResult:
    try:
        _left_kind, left_reports, _left_meta = _load_side(left_path)
        _right_kind, right_reports, _right_meta = _load_side(right_path)
    except BaselineError as exc:
        return ComparisonResult(
            status="incomparable",
            exit_code=EXIT_INVALID_ARGS,
            violations=[str(exc)],
            limitations=["Malformed or missing comparison input is not a regression."],
        )
    rules = None
    if rules_path:
        try:
            rules = _load_json(Path(rules_path))
            core.validate(rules)
            if rules.get("kind") != "acceptance_rules":
                raise BaselineError("Rules file is not kind acceptance_rules")
        except (BaselineError, core.ContractError) as exc:
            return ComparisonResult(
                status="incomparable",
                exit_code=EXIT_INVALID_ARGS,
                violations=[f"Invalid rules: {exc}"],
            )

    keys = sorted(set(left_reports) | set(right_reports))
    if not keys:
        return ComparisonResult(
            status="incomparable",
            exit_code=EXIT_INVALID_ARGS,
            violations=["No reports available to compare"],
        )

    worst = EXIT_OK
    all_changes = []
    all_violations = []
    coverage_lost = False
    incomparable = False
    artifacts = []
    last_status = "unchanged"

    precedence = {
        EXIT_INVALID_ARGS: 10,
        EXIT_MISSING_INPUT: 9,
        EXIT_REGRESSION: 8,
        EXIT_INCOMPARABLE: 7,
        EXIT_PARTIAL: 6,
        EXIT_OK: 0,
    }

    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    for key in keys:
        left_rep = left_reports.get(key)
        right_rep = right_reports.get(key)
        alignments = []
        if isinstance(left_rep, dict) and isinstance(right_rep, dict):
            try:
                alignments = _align_pages(left_rep, right_rep)
            except BaselineError as exc:
                return ComparisonResult(
                    status="incomparable",
                    exit_code=EXIT_INVALID_ARGS,
                    violations=[str(exc)],
                )
        comparison, code, lost, incomp = _build_comparison(
            left_rep if isinstance(left_rep, dict) else None,
            right_rep if isinstance(right_rep, dict) else None,
            key,
            rules,
            mode,
            alignments,
        )
        last_status = comparison["status"]
        all_changes.extend(comparison["changes"])
        if lost:
            coverage_lost = True
        if incomp or comparison["status"] == "incomparable":
            incomparable = True
        if comparison["status"] == "regressed":
            all_violations.append(f"{key}: {comparison['changes'][0]['explanation']}")
        if precedence.get(code, 0) > precedence.get(worst, 0):
            worst = code
        if fail_on_changed and comparison["status"] == "changed":
            worst = EXIT_REGRESSION if precedence[EXIT_REGRESSION] > precedence.get(worst, 0) else worst
            last_status = "regressed"
        if out_dir:
            path = out_dir / f"{key}.json"
            html = out_dir / f"{key}.html"
            atomic_write_bytes(path, (json.dumps(comparison, indent=2) + "\n").encode())
            atomic_write_bytes(html, render_html_comparison(comparison).encode())
            artifacts.extend([str(path), str(html)])

    if out_dir and keys:
        chosen = keys[0]
        for key in keys:
            path = out_dir / f"{key}.json"
            if path.is_file():
                payload = json.loads(path.read_text())
                if payload.get("status") in {"regressed", "errored", "incomparable"}:
                    chosen = key
                    break
        atomic_write_bytes(out_dir / "comparison.json", (out_dir / f"{chosen}.json").read_bytes())
        atomic_write_bytes(out_dir / "comparison.html", (out_dir / f"{chosen}.html").read_bytes())
        links = "".join(
            f"<li><a href='{key}.html'>{key}</a></li>" for key in keys
        )
        index_html = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='referrer' content='no-referrer'>"
            "<title>Inkflip comparisons</title></head><body><main>"
            "<h1>Per-file comparisons</h1><ul>"
            f"{links}</ul>"
            "<p>Canonical portable artifact: <a href='comparison.json'>comparison.json</a> "
            "and <a href='comparison.html'>comparison.html</a>.</p>"
            "</main></body></html>\n"
        )
        atomic_write_bytes(out_dir / "index.html", index_html.encode())

    status = last_status
    if worst == EXIT_REGRESSION:
        status = "regressed"
    elif incomparable and worst == EXIT_INCOMPARABLE:
        status = "incomparable"
    elif worst == EXIT_PARTIAL:
        status = "errored"
    elif any(change.get("status") not in {"unchanged", None} for change in all_changes) and status == "unchanged":
        status = "changed"

    return ComparisonResult(
        status=status,
        exit_code=worst,
        changes=all_changes,
        violations=all_violations,
        limitations=["Portable comparison artifacts are schema-validated Comparison documents."],
        left_reports_count=sum(1 for v in left_reports.values() if isinstance(v, dict)),
        right_reports_count=sum(1 for v in right_reports.values() if isinstance(v, dict)),
        coverage_lost=coverage_lost,
        incomparable=incomparable,
        artifacts=artifacts,
    )
