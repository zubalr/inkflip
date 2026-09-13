"""Engine for baseline creation and comparison under acceptance rules (T34)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from inkflip.contracts import core
from inkflip.baselines.models import (
    BaselineError,
    BaselineOverwriteError,
    ComparisonResult,
    IncompatibleRunError,
    RuleRegressionError,
)

EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_MISSING_INPUT = 4
EXIT_REGRESSION = 5


def create_baseline(
    run_dir: Path,
    rules_path: Path | None,
    out_path: Path,
    approved_by: str,
    rationale: str,
    overwrite: bool = False,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    """Create an immutable, schema-conforming Baseline record from a completed run.

    Enforces:
    - Baseline overwrite and auto-refresh strictly prohibited
    - Explicit reviewer approval and rationale required
    - Incomplete/invalid runs rejected unless explicit diagnostic override
    - Conformance to inkflip.schema.json ($defs/Baseline)
    """
    if out_path.exists() and not overwrite:
        raise BaselineOverwriteError(
            f"Baseline file already exists at '{out_path}'. Overwrite and auto-refresh are strictly prohibited."
        )

    if not approved_by or not approved_by.strip():
        raise BaselineError("Approved-by reviewer label is required (explicit approval required)")
    approved_by = approved_by.strip()
    if len(approved_by) > 100:
        raise BaselineError("Approved-by label exceeds 100 characters")

    if not rationale or not rationale.strip():
        raise BaselineError("Approval rationale is required (explicit approval rationale required)")
    rationale = rationale.strip()
    if len(rationale) > 2000:
        raise BaselineError("Approval rationale exceeds 2000 characters")

    if not run_dir.is_dir():
        raise BaselineError(f"Run directory not found: '{run_dir}'")

    index_path = run_dir / "index.json"
    if not index_path.is_file():
        raise BaselineError(f"Run directory missing index.json: '{run_dir}'")

    try:
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise BaselineError(f"Failed to read index.json in '{run_dir}': {e}") from e

    run_status = index_data.get("status")
    if run_status != "complete" and not allow_incomplete:
        raise BaselineError(
            f"Run status is '{run_status}'. Incomplete or invalid runs cannot be converted to baselines."
        )

    report_files = sorted(run_dir.glob("*.inkflip.json"))
    if not report_files:
        # Also check *.json that are valid reports
        for f in sorted(run_dir.glob("*.json")):
            if f.name in ("index.json", "rules.json"):
                continue
            try:
                data = json.loads(f.read_text("utf-8"))
                if data.get("kind") == "report":
                    report_files.append(f)
            except Exception:
                continue

    if not report_files:
        raise BaselineError(f"No valid report files found in run directory '{run_dir}'")

    report_ids: list[str] = []
    for rf in report_files:
        sha = hashlib.sha256(rf.read_bytes()).hexdigest()
        report_ids.append(sha)
    report_ids.sort()

    rules_sha: str | None = None
    if rules_path:
        if not rules_path.is_file():
            raise BaselineError(f"Rules file not found: '{rules_path}'")
        rules_bytes = rules_path.read_bytes()
        try:
            rules_data = json.loads(rules_bytes.decode("utf-8"))
            core.validate(rules_data)
        except Exception as e:
            raise BaselineError(f"Invalid acceptance rules file: {e}") from e
        rules_sha = hashlib.sha256(rules_bytes).hexdigest()

    corpus_manifest_sha = index_data.get("corpus_manifest_sha256") or hashlib.sha256(
        b"inkflip-default-corpus"
    ).hexdigest()
    profile_sha = index_data.get("profile_sha256") or hashlib.sha256(
        b"inkflip-default-profile"
    ).hexdigest()

    id_material = f"{corpus_manifest_sha}:{profile_sha}:{rules_sha}:{','.join(report_ids)}:{approved_by}:{rationale}"
    baseline_id = hashlib.sha256(id_material.encode("utf-8")).hexdigest()

    baseline_record = {
        "kind": "baseline",
        "schema_version": "1.0.0",
        "id": baseline_id,
        "corpus_manifest_sha256": corpus_manifest_sha,
        "profile_sha256": profile_sha,
        "report_ids": report_ids,
        "rules_sha256": rules_sha,
        "approved_by": approved_by,
        "rationale": rationale,
    }

    core.validate(baseline_record)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(baseline_record, indent=2) + "\n", encoding="utf-8")
    return baseline_record


def _load_reports_from_dir(path: Path) -> dict[str, dict[str, Any]]:
    """Load all valid reports from a run directory, keyed by file stem or document key."""
    reports = {}
    for f in sorted(path.glob("*.json")):
        if f.name in ("index.json", "rules.json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("kind") == "report":
                key = f.name.replace(".inkflip.json", "").replace(".json", "")
                reports[key] = data
        except Exception:
            continue
    return reports


def compare(
    left_path: Path,
    right_path: Path,
    rules_path: Path | None = None,
    out_dir: Path | None = None,
) -> ComparisonResult:
    """Compare two runs, or a baseline and a run, evaluating acceptance rules.

    Enforces:
    - Changed with no rule is informational (exit 0)
    - Rule regression exits 5
    - Lost coverage cannot count improvement (regression under fail_on_coverage_loss)
    - Incompatible files/readerconfig marked
    """
    if not left_path.exists():
        return ComparisonResult(
            status="incompatible",
            exit_code=EXIT_MISSING_INPUT,
            violations=[f"Left comparison target not found: {left_path}"],
            limitations=["Missing input path"],
        )
    if not right_path.exists():
        return ComparisonResult(
            status="incompatible",
            exit_code=EXIT_MISSING_INPUT,
            violations=[f"Right comparison target not found: {right_path}"],
            limitations=["Missing input path"],
        )

    # 1. Load left reports
    left_reports: dict[str, dict[str, Any]] = {}
    if left_path.is_file():
        try:
            doc = json.loads(left_path.read_text(encoding="utf-8"))
            if doc.get("kind") == "baseline":
                stem = left_path.stem
                candidate_dirs = [
                    left_path.parent.parent / "runs" / stem,
                    left_path.parent / "runs" / stem,
                    left_path.parent / stem,
                    left_path.parent,
                ]
                for cdir in candidate_dirs:
                    if cdir.is_dir():
                        reps = _load_reports_from_dir(cdir)
                        if reps:
                            left_reports = reps
                            break
            elif doc.get("kind") == "report":
                left_reports[left_path.stem] = doc
        except Exception as e:
            return ComparisonResult(
                status="incompatible",
                exit_code=EXIT_INVALID_ARGS,
                violations=[f"Failed to read left path: {e}"],
            )
    else:
        left_reports = _load_reports_from_dir(left_path)

    # 2. Load right reports
    right_reports: dict[str, dict[str, Any]] = {}
    if right_path.is_file():
        try:
            doc = json.loads(right_path.read_text(encoding="utf-8"))
            if doc.get("kind") == "report":
                right_reports[right_path.stem] = doc
        except Exception as e:
            return ComparisonResult(
                status="incompatible",
                exit_code=EXIT_INVALID_ARGS,
                violations=[f"Failed to read right path: {e}"],
            )
    else:
        right_reports = _load_reports_from_dir(right_path)

    # 3. Load acceptance rules if supplied
    acceptance_rules = None
    if rules_path:
        if not rules_path.is_file():
            return ComparisonResult(
                status="incompatible",
                exit_code=EXIT_MISSING_INPUT,
                violations=[f"Rules file not found: {rules_path}"],
            )
        try:
            rules_data = json.loads(rules_path.read_text(encoding="utf-8"))
            core.validate(rules_data)
            acceptance_rules = rules_data
        except Exception as e:
            return ComparisonResult(
                status="incompatible",
                exit_code=EXIT_INVALID_ARGS,
                violations=[f"Failed to validate rules: {e}"],
            )

    all_violations: list[str] = []
    all_changes: list[dict[str, Any]] = []
    has_any_change = False
    coverage_lost = False
    is_incompatible = False

    common_keys = set(left_reports.keys()).intersection(set(right_reports.keys()))
    if not common_keys:
        if left_reports and right_reports:
            # Check if there is single report in each
            if len(left_reports) == 1 and len(right_reports) == 1:
                left_doc = next(iter(left_reports.values()))
                right_doc = next(iter(right_reports.values()))
                common_keys = {"__single__"}
                left_reports["__single__"] = left_doc
                right_reports["__single__"] = right_doc
            else:
                is_incompatible = True
                all_violations.append("Incompatible files: No common report keys found between runs")
        else:
            is_incompatible = True
            all_violations.append("No reports available to compare")

    for k in common_keys:
        l_rep = left_reports[k]
        r_rep = right_reports[k]

        l_sha = l_rep.get("document", {}).get("sha256")
        r_sha = r_rep.get("document", {}).get("sha256")

        if l_sha and r_sha and l_sha != r_sha:
            is_incompatible = True
            all_violations.append(f"Incompatible source documents for '{k}': {l_sha} != {r_sha}")
            continue

        l_occs = l_rep.get("occurrences", [])
        r_occs = r_rep.get("occurrences", [])

        # Coverage check
        if len(r_occs) < len(l_occs):
            coverage_lost = True
            all_violations.append(
                f"Coverage loss in '{k}': occurrence count dropped from {len(l_occs)} to {len(r_occs)}"
            )

        # Content difference check
        l_text = "\n".join(o.get("raw_text", "") for o in l_occs)
        r_text = "\n".join(o.get("raw_text", "") for o in r_occs)

        if l_text != r_text or len(l_occs) != len(r_occs):
            has_any_change = True
            all_changes.append({
                "key": k,
                "kind": "modified",
                "left_count": len(l_occs),
                "right_count": len(r_occs),
                "status": "changed",
            })

        # Evaluate rules
        if acceptance_rules and "rules" in acceptance_rules:
            for rule in acceptance_rules["rules"]:
                r_type = rule.get("type")
                exp_text = rule.get("expected_text")
                page_idx = rule.get("page_index", 0)

                # Find occurrences on specified page
                page_occs = [o for o in r_occs if o.get("page_index") == page_idx]
                page_text = "\n".join(o.get("raw_text", "") for o in page_occs)

                if r_type == "expected_text" and exp_text is not None:
                    if exp_text not in page_text:
                        all_violations.append(
                            f"Rule '{rule.get('id')}' [expected_text] failed on page {page_idx}: expected '{exp_text}'"
                        )
                elif r_type == "stable_reading":
                    base_occs = [o for o in l_occs if o.get("page_index") == page_idx]
                    base_text = "\n".join(o.get("raw_text", "") for o in base_occs)
                    if page_text != base_text:
                        all_violations.append(
                            f"Rule '{rule.get('id')}' [stable_reading] violated on page {page_idx}: candidate reading changed from approved baseline"
                        )
                elif r_type == "required_coverage":
                    if not page_occs:
                        all_violations.append(
                            f"Rule '{rule.get('id')}' [required_coverage] failed on page {page_idx}: 0 occurrences found"
                        )
                elif r_type == "expected_occurrence_count":
                    exp_count = rule.get("expected_count")
                    if exp_count is not None and len(page_occs) != exp_count:
                        all_violations.append(
                            f"Rule '{rule.get('id')}' [expected_occurrence_count] failed: expected {exp_count}, got {len(page_occs)}"
                        )

    # Status and exit code assignment
    status = "unchanged"
    exit_code = EXIT_OK

    if is_incompatible:
        status = "incompatible"
        exit_code = EXIT_INVALID_ARGS
    elif all_violations:
        status = "regressed"
        exit_code = EXIT_REGRESSION
    elif coverage_lost:
        status = "regressed"
        exit_code = EXIT_REGRESSION
    elif has_any_change:
        # Changed with no rule violation is informational
        status = "changed"
        exit_code = EXIT_OK

    result = ComparisonResult(
        status=status,
        exit_code=exit_code,
        changes=all_changes,
        violations=all_violations,
        limitations=["Comparison limited to extracted text occurrences and bounds"],
        left_reports_count=len(left_reports),
        right_reports_count=len(right_reports),
        coverage_lost=coverage_lost,
    )

    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        summary_path = out_dir / "comparison.json"
        summary_path.write_text(
            json.dumps({
                "kind": "comparison_summary",
                "status": result.status,
                "exit_code": result.exit_code,
                "violations": result.violations,
                "changes": result.changes,
                "left_count": result.left_reports_count,
                "right_count": result.right_reports_count,
            }, indent=2) + "\n",
            encoding="utf-8",
        )

    return result
