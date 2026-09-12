"""Evaluation reports: verdicts exist only where a bound run produced counts.

The honesty contract is simple and enforced structurally:

* ``status_report`` shows every declared target UNMET — a plan is intent,
  not evidence, and there is no green-by-default.
* ``evaluate`` accepts only a run that binds a frozen candidate (commit +
  lock + config digests) to a pinned corpus manifest, carries real reading
  records with consistent resolutions, and contains no self-attested
  outcome keys anywhere.
* Metrics and verdicts are computed from those readings and custodian-held
  labels only. A run claiming success is input to scoring, never a verdict.
* Emitted artifacts carry digests and aggregate counts; label content is
  scanned out of every serialization before it is written.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import PROTOCOL_VERSION, SCHEMA_VERSION
from .custody import (
    CustodyError,
    assert_labels_not_emitted,
    check_labels_cover_corpus,
    scan_forbidden_keys,
)
from .lineage import SPLITS
from .manifest import SELF_ATTEST_KEYS, ManifestError
from .metrics import (
    RESOLUTIONS,
    TERMINAL_STATUSES,
    check_accounting,
    clean_false_alerts,
    collapse_readings,
    full_coverage,
    grouped_bootstrap_ci,
    occurrence_preservation,
    page_key,
    percentile,
    supported_coverage,
    wilson_interval,
)

SHA_RE = re.compile(r"^[a-f0-9]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CHECK_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
# Closed top-level run shape: a top-level "status": "passed" or any other
# unexpected field is rejected rather than ignored. Reading records inside
# `readings` keep their CheckResult `status` — the honest field.
RUN_KEYS = {
    "kind", "schema_version", "run_id", "candidate",
    "corpus_manifest_sha256", "created_at", "readings", "planned_checks",
    "hard_failures", "repeat_digests", "notes", "environment",
}


class RunError(ValueError):
    """An inspection run is malformed, unbound or self-attested."""


def _scan_keys(obj, banned: set[str], path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in banned:
                found.append(f"{path}.{key}")
            found.extend(_scan_keys(value, banned, f"{path}.{key}"))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found.extend(_scan_keys(value, banned, f"{path}[{index}]"))
    return found


def _check_reading(reading: dict, where: str) -> None:
    required = {"document_sha256", "page_index", "check_id", "status"}
    missing = required - set(reading)
    if missing:
        raise RunError(f"{where}: missing fields {sorted(missing)}")
    if not SHA_RE.match(str(reading["document_sha256"])):
        raise RunError(f"{where}: document_sha256 must be a hex digest")
    if type(reading["page_index"]) is not int or reading["page_index"] < 0:
        raise RunError(f"{where}: page_index must be a nonnegative integer")
    if not CHECK_ID_RE.match(str(reading["check_id"])):
        raise RunError(f"{where}: bad check_id {reading['check_id']!r}")
    if reading["status"] not in TERMINAL_STATUSES:
        raise RunError(
            f"{where}: status {reading['status']!r} is not a terminal CheckResult state")
    resolution = reading.get("resolution")
    if resolution is not None:
        if resolution not in RESOLUTIONS:
            raise RunError(f"{where}: unknown resolution {resolution!r}")
        # Consistency: a resolution is evidence, not a claim. A useful
        # finding must name the surfaced findings; an actionable comparison
        # must name its comparison reference; either way the check must
        # have completed. A self-attested resolution cannot stand.
        if reading["status"] != "completed":
            raise RunError(f"{where}: resolution requires a completed check")
        if resolution == "useful_finding" and not reading.get("finding_ids"):
            raise RunError(f"{where}: useful_finding resolution needs finding_ids")
        if resolution == "actionable_comparison" and not reading.get("comparison_ref"):
            raise RunError(
                f"{where}: actionable_comparison resolution needs comparison_ref")
    findings = reading.get("finding_ids", [])
    if not isinstance(findings, list) or any(not isinstance(f, str) for f in findings):
        raise RunError(f"{where}: finding_ids must be a list of ids")
    occurrences = reading.get("occurrence_count")
    if occurrences is not None and (type(occurrences) is not int or occurrences < 0):
        raise RunError(f"{where}: occurrence_count must be a nonnegative integer")
    errors = reading.get("alignment_errors_px", [])
    if not isinstance(errors, list) or any(
            type(v) not in (int, float) or v < 0 for v in errors):
        raise RunError(f"{where}: alignment_errors_px must be nonnegative numbers")


def validate_run(run: dict) -> None:
    """A bound inspection run: frozen candidate, pinned corpus, real records."""
    if not isinstance(run, dict) or run.get("kind") != "inspection_run":
        raise RunError("run must be an inspection_run object")
    if run.get("schema_version") != SCHEMA_VERSION:
        raise RunError("run schema_version mismatch")
    unknown = set(run) - RUN_KEYS
    if unknown:
        raise RunError(f"run carries unknown top-level keys {sorted(unknown)}")
    attested = _scan_keys(run, SELF_ATTEST_KEYS)
    if attested:
        raise RunError(
            f"run carries self-attested outcome keys {attested[:3]}; "
            "verdicts are computed, never declared"
        )
    candidate = run.get("candidate")
    if not isinstance(candidate, dict):
        raise RunError("run needs a frozen candidate")
    if not COMMIT_RE.match(str(candidate.get("commit"))):
        raise RunError("candidate.commit must be a full git commit")
    for name in ("lock_sha256", "config_sha256"):
        if not SHA_RE.match(str(candidate.get(name))):
            raise RunError(f"candidate.{name} must be a hex digest")
    if not SHA_RE.match(str(run.get("corpus_manifest_sha256"))):
        raise RunError("run must pin corpus_manifest_sha256")
    readings = run.get("readings")
    if not isinstance(readings, list):
        raise RunError("run.readings must be a list")
    for index, reading in enumerate(readings):
        _check_reading(reading, f"run.readings[{index}]")
    plan_checks = run.get("planned_checks")
    if plan_checks is not None:
        if not isinstance(plan_checks, list) or any(
                not CHECK_ID_RE.match(str(c)) for c in plan_checks):
            raise RunError("planned_checks must be check ids")
    hard = run.get("hard_failures")
    if hard is not None and not isinstance(hard, list):
        raise RunError("hard_failures must be a list of violation records")


def compute_metrics(readings: list[dict], labels: dict, groups: dict[str, str],
                    planned_checks: list[str] | None,
                    adjudication: dict | None = None,
                    hard_failures: list | None = None,
                    repeat_digests: dict | None = None) -> dict:
    """All scored metrics over deduplicated page samples."""
    pages = collapse_readings(readings)
    coverage = supported_coverage(pages, labels)
    full = full_coverage(pages, labels)
    alerts = clean_false_alerts(pages, labels)
    occurrences = occurrence_preservation(pages, labels)

    # Cluster uncertainty by document/generator group — never per reading.
    resolved_values = {
        k: 1.0 if pages.get(k, {}).get("resolved") else 0.0
        for k in groups if labels["pages"][k]["truth"] == "supported_failure"
    }
    support_groups = {k: groups[k] for k in resolved_values}
    boot = grouped_bootstrap_ci(resolved_values, support_groups) if resolved_values else None
    coverage["grouped_bootstrap"] = list(boot[:2]) + [boot[2]] if boot else None

    # The sampling unit is the page, not the reading: collapse every
    # page's per-reading errors to its worst observed value BEFORE pooling,
    # so re-reading only well-aligned pages can never dilute p95 or inflate
    # the measured n (independent review P2: 30x re-reads of good pages
    # flipped honest p95=3.9 UNMET to p95=0.1 MET).
    align_errors = [
        max(page["alignment_errors_px"])
        for page in pages.values()
        if page["alignment_errors_px"]
    ]
    metrics = {
        "supported_coverage": coverage,
        "full_coverage": full,
        "clean_false_alerts": alerts,
        "occurrence_preservation": occurrences,
        "samples": {
            "readings": len(readings),
            "unique_pages": len(pages),
            "groups": len(set(groups.values())),
        },
    }
    if planned_checks is not None:
        metrics["check_accounting"] = check_accounting(readings, planned_checks)
    if adjudication is not None:
        from .diagnosis import useful_precision_metric
        metrics["useful_precision"] = useful_precision_metric(adjudication)
        metrics["evaluated_findings"] = adjudication["evaluated"]
    if align_errors:
        metrics["alignment_px"] = {
            "n": len(align_errors),
            "p95": percentile(align_errors, 0.95),
            "max": max(align_errors),
        }
    if hard_failures is not None:
        metrics["hard_fixture_failures"] = len(hard_failures)
    if repeat_digests is not None:
        stable = sum(1 for v in repeat_digests.values() if len(set(v)) == 1)
        metrics["repeatability"] = {
            "pages": len(repeat_digests),
            "stable": stable,
            "fraction": stable / len(repeat_digests) if repeat_digests else None,
        }
    return metrics


_METRIC_LOOKUP = {
    "supported_coverage": lambda m: m["supported_coverage"]["rate"],
    "full_coverage": lambda m: m["full_coverage"]["rate"],
    "clean_false_alerts_per_page": lambda m: m["clean_false_alerts"]["per_page"],
    "occurrence_preservation_fraction": lambda m: (m.get("occurrence_preservation") or {}).get("fraction"),
    "useful_precision_point": lambda m: (m.get("useful_precision") or {}).get("point"),
    "useful_precision_wilson_lower": lambda m: (m.get("useful_precision") or {}).get("wilson_lower"),
    "evaluated_findings": lambda m: m.get("evaluated_findings"),
    "check_terminal_fraction": lambda m: (m.get("check_accounting") or {}).get("fraction"),
    "alignment_p95_px": lambda m: (m.get("alignment_px") or {}).get("p95"),
    "alignment_max_px": lambda m: (m.get("alignment_px") or {}).get("max"),
    "hard_fixture_failures": lambda m: m.get("hard_fixture_failures"),
    "repeatability_fraction": lambda m: (m.get("repeatability") or {}).get("fraction"),
}


def _compare(observed: float, comparator: str, threshold: float) -> bool:
    return {
        ">=": observed >= threshold,
        "<=": observed <= threshold,
        "==": observed == threshold,
        "<": observed < threshold,
    }[comparator]


def target_verdicts(plan: dict, metrics: dict | None,
                    metric_samples: dict[str, int] | None = None,
                    reason: str = "no_evaluation_run") -> list[dict]:
    """Verdict per declared target: UNMET unless a real run says MET.

    ``metrics is None`` means no bound run scored anything — every target
    reports UNMET with the reason. With metrics, an unmeasured metric or a
    sample below its declared minimum is UNMET, never vacuously green.
    """
    metric_samples = metric_samples or {}
    verdicts = []
    for target in plan["targets"]:
        verdict = {
            "id": target["id"],
            "metric": target["metric"],
            "comparator": target["comparator"],
            "threshold": target["threshold"],
            "verdict": "UNMET",
            "observed": None,
        }
        if metrics is None:
            verdict["reason"] = reason
        elif target["metric"] not in _METRIC_LOOKUP:
            verdict["reason"] = "unknown_metric"
        else:
            try:
                observed = _METRIC_LOOKUP[target["metric"]](metrics)
            except (KeyError, TypeError):
                observed = None
            if observed is None:
                verdict["reason"] = "not_measured"
            else:
                verdict["observed"] = observed
                needed = target.get("min_samples")
                have = metric_samples.get(target["metric"])
                if needed is not None and (have is None or have < needed):
                    verdict["reason"] = f"insufficient_evidence:{have or 0}<{needed}"
                elif _compare(observed, target["comparator"], target["threshold"]):
                    verdict["verdict"] = "MET"
                    verdict["reason"] = "measured"
                else:
                    verdict["reason"] = "below_target"
        verdicts.append(verdict)
    return verdicts


def _metric_samples(metrics: dict) -> dict[str, int]:
    samples: dict[str, int] = {}
    precision = metrics.get("useful_precision")
    if precision:
        samples["useful_precision_point"] = precision["evaluated"]
        samples["useful_precision_wilson_lower"] = precision["evaluated"]
        samples["evaluated_findings"] = precision["evaluated"]
    coverage = metrics.get("supported_coverage")
    if coverage:
        samples["supported_coverage"] = coverage["total"]
    full = metrics.get("full_coverage")
    if full:
        samples["full_coverage"] = full["total"]
    alerts = metrics.get("clean_false_alerts")
    if alerts:
        samples["clean_false_alerts_per_page"] = alerts["clean_pages"]
    occurrences = metrics.get("occurrence_preservation")
    if occurrences:
        samples["occurrence_preservation_fraction"] = occurrences["pages"]
    alignment = metrics.get("alignment_px")
    if alignment:
        samples["alignment_p95_px"] = alignment["n"]
        samples["alignment_max_px"] = alignment["n"]
    repeat = metrics.get("repeatability")
    if repeat:
        samples["repeatability_fraction"] = repeat["pages"]
    return samples


def run_digest(run: dict) -> str:
    canonical = json.dumps(run, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def status_report(plan: dict, plan_sha256: str | None = None) -> dict:
    """The plan's standing verdicts: UNMET until a real bound run exists."""
    return {
        "kind": "evaluation_report",
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan_sha256,
        "run": None,
        "labels_sha256": None,
        "corpus": None,
        "samples": None,
        "metrics": None,
        "targets": target_verdicts(plan, None, reason="no_evaluation_run"),
        "summary": {"met": 0, "unmet": len(plan["targets"]), "all_met": False},
        "limitations": [
            "Declared targets are unmet until an actual evaluation run on a "
            "frozen candidate produces real counts; no green-by-default.",
        ],
    }


def evaluate(plan: dict, corpus: dict, run: dict, labels: dict,
             labels_sha256: str, corpus_sha256: str,
             plan_sha256: str | None = None,
             adjudication: dict | None = None) -> dict:
    """Score a bound run against the frozen corpus and custodian labels."""
    validate_run(run)
    # A plan that pins a candidate freeze enforces it: the run's candidate
    # triple must equal the pinned values field-for-field. Null plan fields
    # mean "not frozen yet" — the run's own candidate is still recorded
    # openly in the report, so an advisory freeze hides nothing.
    freeze = plan.get("candidate_freeze") or {}
    for name in ("commit", "lock_sha256", "config_sha256"):
        pinned = freeze.get(name)
        if pinned is not None and run["candidate"].get(name) != pinned:
            raise RunError(
                f"candidate.{name} does not match the plan's pinned "
                "candidate freeze; a different candidate needs a new "
                "evaluation version")
    if run["corpus_manifest_sha256"] != corpus_sha256:
        raise RunError(
            "run is not bound to this corpus manifest: "
            f"run pins {run['corpus_manifest_sha256'][:16]}..., "
            f"manifest digests to {corpus_sha256[:16]}..."
        )
    from .manifest import corpus_groups, corpus_page_keys
    page_keys = corpus_page_keys(corpus)
    check_labels_cover_corpus(labels, page_keys)
    groups = corpus_groups(corpus)
    metrics = compute_metrics(
        run["readings"], labels, groups, run.get("planned_checks"),
        adjudication=adjudication,
        hard_failures=run.get("hard_failures"),
        repeat_digests=run.get("repeat_digests"),
    )
    verdicts = target_verdicts(plan, metrics, _metric_samples(metrics))
    met = sum(1 for v in verdicts if v["verdict"] == "MET")
    report = {
        "kind": "evaluation_report",
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan_sha256,
        "run": {
            "run_sha256": run_digest(run),
            "candidate_commit": run["candidate"]["commit"],
            "lock_sha256": run["candidate"]["lock_sha256"],
            "config_sha256": run["candidate"]["config_sha256"],
            "corpus_manifest_sha256": corpus_sha256,
            "created_at": run.get("created_at"),
        },
        "labels_sha256": labels_sha256,
        "corpus": {
            "split": corpus["split"],
            "documents": len(corpus["entries"]),
            "pages": len(page_keys),
            "groups": len(set(groups.values())),
        },
        "samples": metrics["samples"],
        "metrics": metrics,
        "targets": verdicts,
        "summary": {"met": met, "unmet": len(verdicts) - met,
                    "all_met": met == len(verdicts)},
        "limitations": [
            "Verdicts hold only for the bound corpus population and frozen "
            "candidate; tuning on these cases retires them from untouched claims.",
        ],
    }
    serialized = serialize_report(report, labels)
    report["_emitted_bytes_sha256"] = hashlib.sha256(serialized).hexdigest()
    return report


def serialize_report(report: dict, labels: dict | None = None) -> bytes:
    """Serialize with the leakage gate applied — the only write path."""
    forbidden = scan_forbidden_keys(report)
    if forbidden:
        raise CustodyError(
            f"report would expose held-out keys {forbidden[:3]}")
    body = {k: v for k, v in report.items() if not k.startswith("_")}
    serialized = (json.dumps(body, indent=2, sort_keys=True) + "\n").encode()
    assert_labels_not_emitted(serialized.decode(), labels)
    return serialized
