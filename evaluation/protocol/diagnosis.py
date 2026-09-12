"""Diagnosis-usefulness and useful-finding review forms (EVALUATION.md).

Two reviewers independently label a blinded sample of surfaced localized
findings against the original page, the raw readings and the stated task.
Disagreements stay reported and are adjudicated with rationale — never
hidden as correct, and never silently counted either way. Duplicate cards
for one issue count as review burden.

The diagnosis task comparison counterbalances tool order (PDF viewer plus
raw text dump versus inspector) per tester and shuffles task order
deterministically per tester, so learning effects cannot fake an
improvement.
"""
from __future__ import annotations

import hashlib
import random
import statistics

CONDITIONS = ("baseline_viewer_dump", "inspector")
DEFAULT_SEED = 0xD1A6


def counterbalanced_assignments(tester_ids: list[str],
                                conditions: tuple[str, ...] = CONDITIONS) -> dict[str, list[str]]:
    """Latin-square tool order per tester — deterministic, balanced.

    With two conditions, half the testers see the inspector first and half
    see the baseline first; no tester ordering is left to chance or to the
    worker's convenience.
    """
    testers = sorted(tester_ids)
    conditions = list(conditions)
    assignments = {}
    for index, tester in enumerate(testers):
        offset = index % len(conditions)
        assignments[tester] = conditions[offset:] + conditions[:offset]
    return assignments


def task_order(tester_id: str, tasks: list[str], seed: int = DEFAULT_SEED) -> list[str]:
    """Deterministic per-tester task shuffle (same inputs, same order)."""
    shuffled = sorted(tasks)
    random.Random(f"{seed}:{tester_id}").shuffle(shuffled)
    return shuffled


def finding_digest(finding: dict) -> str:
    """Content identity of one surfaced finding for blinded reference."""
    canonical = _json_dumps(finding)
    return hashlib.sha256(canonical).hexdigest()


def _json_dumps(obj) -> bytes:
    import json
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def blinded_review_form(findings: list[dict], sample_size: int | None = None,
                        seed: int = DEFAULT_SEED, form_id: str = "useful-review") -> dict:
    """Sample surfaced findings into a blinded labeling form.

    Each item carries the finding digest, a page reference and the stated
    task — never truth labels, adjudication outcomes or reviewer opinions,
    so reviewers label blinded to corpus truth and to each other. Sampling
    is deterministic under ``seed``.
    """
    pool = []
    for finding in findings:
        pool.append({
            "finding_sha256": finding.get("finding_sha256") or finding_digest(finding),
            "page_ref": finding["page_ref"],
            "task": finding.get("task", "investigate the stated reading incident"),
        })
    pool.sort(key=lambda item: item["finding_sha256"])
    random.Random(seed).shuffle(pool)
    if sample_size is not None:
        pool = pool[:sample_size]
    return {
        "kind": "blinded_review_form",
        "schema_version": "1.0.0",
        "form_id": form_id,
        "seed": seed,
        "items": [
            {
                "item_id": f"item-{index:04d}",
                "finding_sha256": item["finding_sha256"],
                "page_ref": item["page_ref"],
                "task": item["task"],
                "labels": {"useful": None, "noise": None, "rationale": None},
            }
            for index, item in enumerate(pool)
        ],
    }


def adjudicate(form: dict, responses: dict[str, dict],
               adjudications: dict | None = None,
               adjudicator: str | None = None) -> dict:
    """Combine independent reviewer labels; disagreements stay visible.

    ``responses`` maps reviewer id to ``{item_id: {"useful": bool,
    "noise": bool, "rationale": str}}``. Agreement decides an item; a
    disagreement is listed with every rationale and counts as not useful
    until an adjudication entry resolves it with its own recorded
    rationale. A resolved dispute uses the adjudicated decision, and the
    disagreement remains in the record.
    """
    adjudications = adjudications or {}
    reviewer_ids = sorted(responses)
    if len(reviewer_ids) < 2:
        raise ValueError("useful-finding precision needs at least two independent reviewers")
    item_ids = [item["item_id"] for item in form["items"]]
    decisions: dict[str, str] = {}
    disagreements: list[dict] = []
    missing: list[str] = []
    for item_id in item_ids:
        votes: dict[str, str] = {}
        rationales: dict[str, str | None] = {}
        for reviewer in reviewer_ids:
            label = (responses.get(reviewer) or {}).get(item_id)
            if label is None:
                missing.append(f"{item_id}:{reviewer}")
                continue
            useful, noise = bool(label.get("useful")), bool(label.get("noise"))
            votes[reviewer] = "useful" if useful and not noise else "noise"
            rationales[reviewer] = label.get("rationale")
        if len(votes) < len(reviewer_ids):
            decisions[item_id] = "unlabeled"
            continue
        if len(set(votes.values())) == 1:
            decisions[item_id] = next(iter(votes.values()))
            continue
        entry = {
            "item_id": item_id,
            "labels": votes,
            "rationales": rationales,
            "adjudicated": None,
        }
        resolution = adjudications.get(item_id)
        if resolution and resolution.get("decision") in ("useful", "noise"):
            _require_rationale(resolution, item_id)
            entry["adjudicated"] = {
                "decision": resolution["decision"],
                "rationale": resolution["rationale"],
                "adjudicator": resolution.get("adjudicator", adjudicator),
            }
            decisions[item_id] = resolution["decision"]
        else:
            decisions[item_id] = "disputed_unresolved"
        disagreements.append(entry)
    useful = sum(1 for d in decisions.values() if d == "useful")
    evaluated = sum(1 for d in decisions.values() if d != "unlabeled")
    return {
        "kind": "adjudication",
        "schema_version": "1.0.0",
        "form_id": form.get("form_id"),
        "reviewers": reviewer_ids,
        "items_total": len(item_ids),
        "decisions": decisions,
        "disagreements": disagreements,
        "unlabeled": missing,
        "useful": useful,
        "evaluated": evaluated,
        # An unresolved dispute counts in the denominator and not the
        # numerator — the conservative reading, never hidden as correct.
        "precision": useful / evaluated if evaluated else None,
    }


def _require_rationale(resolution: dict, item_id: str) -> None:
    if not resolution.get("rationale"):
        raise ValueError(f"adjudication for {item_id} needs a recorded rationale")


def useful_precision_metric(adjudication: dict) -> dict:
    """Point estimate and Wilson bound over adjudicated findings."""
    from .metrics import wilson_interval
    useful = adjudication["useful"]
    evaluated = adjudication["evaluated"]
    low, high = wilson_interval(useful, evaluated)
    return {
        "useful": useful,
        "evaluated": evaluated,
        "point": useful / evaluated if evaluated else None,
        "wilson_lower": low,
        "wilson_upper": high,
        "disagreements": len(adjudication["disagreements"]),
        "unresolved_disputes": sum(
            1 for d in adjudication["decisions"].values() if d == "disputed_unresolved"),
    }


def diagnosis_summary(sessions: list[dict]) -> dict:
    """Formative diagnosis targets (>=4/5 understanding, >=30% median time gain).

    ``sessions``: ``{"tester", "condition", "task", "seconds",
    "understood"}`` per completed task. Understanding counts a tester when
    every one of their inspector sessions was understood; the time
    improvement is the median of per-tester median-time ratios — repeated
    relevant tasks, no correctness loss required upstream.
    """
    testers = sorted({s["tester"] for s in sessions})
    understanding: dict[str, bool] = {}
    improvements: dict[str, float] = {}
    for tester in testers:
        own = [s for s in sessions if s["tester"] == tester]
        inspector = [s for s in own if s["condition"] == "inspector"]
        baseline = [s for s in own if s["condition"] != "inspector"]
        understanding[tester] = bool(inspector) and all(
            bool(s["understood"]) for s in inspector)
        if inspector and baseline:
            med_i = statistics.median(s["seconds"] for s in inspector)
            med_b = statistics.median(s["seconds"] for s in baseline)
            if med_b > 0:
                improvements[tester] = (med_b - med_i) / med_b
    understood = sum(1 for v in understanding.values() if v)
    return {
        "testers": len(testers),
        "understood": understood,
        "understanding_rate": understood / len(testers) if testers else None,
        "per_tester_improvement": improvements,
        "median_improvement": (
            statistics.median(improvements.values()) if improvements else None),
    }
