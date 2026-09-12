"""Precise denominators, deduplicated samples and interval estimates.

Two honesty rules drive every function here:

* Denominators are corpus-declared, never reader-chosen. A page the
  inspector skipped, failed, timed out on, cancelled or never attempted
  stays in its denominator and is reported by status — a report that skips
  9 of 10 pages cannot score 100% on the one it read.
* The sampling unit is the page inside its document/generator group, not
  the reading. k re-reads of one page contribute one sample; uncertainty
  resamples whole groups so sibling pages and repeated OCR passes can never
  masquerade as independent evidence.
"""
from __future__ import annotations

import math
import random

# Terminal CheckResult states from the contract schema. Every planned check
# must reach one of them; anything else is an accounting violation (I05).
TERMINAL_STATUSES = ("completed", "unsupported", "timeout", "cancelled", "failed", "skipped")
UNRESOLVED_STATUSES = ("unsupported", "timeout", "cancelled", "failed", "skipped")
RESOLUTIONS = ("useful_finding", "actionable_comparison")

# Label truth vocabulary. `unsupported` labels stay out of the supported
# recall denominator but inside full-corpus coverage reporting, so a
# selective denominator cannot imply generality.
TRUTHS = ("clean", "supported_failure", "unsupported")

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 0x1A4C


def page_key(document_sha256: str, page_index: int) -> str:
    """Sampling-unit identity: one document page, independent of re-reads."""
    return f"{document_sha256}:{page_index}"


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    n == 0 carries no information and returns the widest possible interval;
    target verdicts additionally gate on declared minimum sample sizes, so
    an empty sample can never look precise.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def collapse_readings(readings: list[dict]) -> dict[str, dict]:
    """Collapse repeated reader attempts into one outcome per page.

    A page resolves when any of its readings carries a consistent
    resolution (validated upstream: a resolution requires a completed check
    plus its declared evidence). Uncovered statuses stay reported per page,
    so re-reads never erase a failure and never multiply a denominator.
    """
    pages: dict[str, dict] = {}
    for reading in readings:
        key = page_key(reading["document_sha256"], reading["page_index"])
        page = pages.setdefault(key, {
            "document_sha256": reading["document_sha256"],
            "page_index": reading["page_index"],
            "readings": 0,
            "statuses": {},
            "resolved": False,
            "finding_ids": set(),
            "alignment_errors_px": [],
        })
        page["readings"] += 1
        status = reading["status"]
        page["statuses"][status] = page["statuses"].get(status, 0) + 1
        page["finding_ids"].update(reading.get("finding_ids", ()))
        page["alignment_errors_px"].extend(reading.get("alignment_errors_px", ()))
        if status == "completed" and "occurrence_count" in reading:
            page.setdefault("occurrence_counts", []).append(reading["occurrence_count"])
        if reading.get("resolution") in RESOLUTIONS and status == "completed":
            page["resolved"] = True
    return pages


def occurrence_preservation(pages: dict[str, dict], labels: dict) -> dict:
    """Fraction of pages whose expected repeated occurrences were preserved.

    The denominator is every labeled page declaring ``expected_occurrences``;
    the conservative observed count is the minimum across completed readings
    (a flaky reader that sometimes drops a duplicate did not preserve it).
    A page whose readings never reported an occurrence count — unread,
    failed, or silent — counts as lost: silence cannot confirm preservation,
    even when the declared expectation is zero.
    """
    declared = sorted(
        k for k, v in labels["pages"].items()
        if type(v.get("expected_occurrences")) is int and v["expected_occurrences"] >= 0
    )
    lost = []
    for key in declared:
        expected = labels["pages"][key]["expected_occurrences"]
        counts = pages.get(key, {}).get("occurrence_counts")
        if not counts or min(counts) != expected:
            lost.append(key)
    preserved = len(declared) - len(lost)
    return {
        "pages": len(declared),
        "preserved": preserved,
        "fraction": preserved / len(declared) if declared else None,
        "lost": lost,
    }


def _truth_pages(labels: dict, truth: str) -> list[str]:
    return sorted(k for k, v in labels["pages"].items() if v["truth"] == truth)


def supported_coverage(pages: dict[str, dict], labels: dict) -> dict:
    """Fraction of predeclared supported failure cases resolved.

    The denominator is every page the label store declares
    ``supported_failure`` — including pages the inspector skipped, failed,
    timed out on, abstained from or never attempted. Abstain-everywhere
    scores 0, not "precision by silence".
    """
    supported = _truth_pages(labels, "supported_failure")
    uncovered = [k for k in supported if not pages.get(k, {}).get("resolved")]
    covered = len(supported) - len(uncovered)
    status_tally: dict[str, int] = {}
    for key in uncovered:
        statuses = pages.get(key, {}).get("statuses") or {"never_attempted": 1}
        for status, count in statuses.items():
            status_tally[status] = status_tally.get(status, 0) + count
    low, high = wilson_interval(covered, len(supported))
    return {
        "covered": covered,
        "total": len(supported),
        "rate": covered / len(supported) if supported else None,
        "wilson": [low, high],
        "uncovered_pages": uncovered,
        "never_attempted": [k for k in uncovered if k not in pages],
        "uncovered_statuses": status_tally,
    }


def full_coverage(pages: dict[str, dict], labels: dict) -> dict:
    """Coverage over the whole labeled corpus, including unsupported cases."""
    all_pages = sorted(labels["pages"])
    uncovered = [k for k in all_pages if not pages.get(k, {}).get("resolved")]
    covered = len(all_pages) - len(uncovered)
    low, high = wilson_interval(covered, len(all_pages))
    return {
        "covered": covered,
        "total": len(all_pages),
        "rate": covered / len(all_pages) if all_pages else None,
        "wilson": [low, high],
        "uncovered_pages": uncovered,
    }


def clean_false_alerts(pages: dict[str, dict], labels: dict) -> dict:
    """Surfaced non-informational findings per clean corpus page.

    Distinct finding ids are counted once per page — re-reading a page and
    re-surfacing the same alert is one burden, not two. The denominator is
    every clean labeled page, read or not; `pages_read` stays visible so a
    nearly-unread corpus cannot hide behind the mean.
    """
    clean = _truth_pages(labels, "clean")
    per_page = {k: pages.get(k, {}).get("finding_ids", set()) for k in clean}
    total_alerts = sum(len(ids) for ids in per_page.values())
    return {
        "alerts": total_alerts,
        "clean_pages": len(clean),
        "per_page": total_alerts / len(clean) if clean else None,
        "pages_with_alerts": sum(1 for ids in per_page.values() if ids),
        "pages_read": sum(1 for k in clean if k in pages),
        "max_per_page": max((len(ids) for ids in per_page.values()), default=0),
    }


def check_accounting(readings: list[dict], planned_check_ids: list[str]) -> dict:
    """I05 accounting: every planned check must reach a terminal result.

    Repeated attempts of one planned check count once — a retried check is
    still one planned unit of work. Missing results and non-terminal states
    are violations, never agreement.
    """
    planned = list(dict.fromkeys(planned_check_ids))
    attempts: dict[str, list[str]] = {}
    for reading in readings:
        attempts.setdefault(reading["check_id"], []).append(reading["status"])
    terminal = sum(
        1 for check_id in planned
        if any(status in TERMINAL_STATUSES for status in attempts.get(check_id, ()))
    )
    missing = [c for c in planned if c not in attempts]
    nonterminal = [
        c for c in planned
        if c in attempts and not any(s in TERMINAL_STATUSES for s in attempts[c])
    ]
    return {
        "planned": len(planned),
        "terminal": terminal,
        "fraction": terminal / len(planned) if planned else None,
        "missing": missing,
        "nonterminal": nonterminal,
        "attempts": sum(len(v) for v in attempts.values()),
    }


def grouped_bootstrap_ci(values: dict[str, float], groups: dict[str, str],
                         resamples: int = BOOTSTRAP_RESAMPLES,
                         seed: int = BOOTSTRAP_SEED,
                         alpha: float = 0.05) -> tuple[float, float, dict]:
    """Percentile bootstrap resampled by document/generator group.

    Each resample draws whole groups with replacement; every page of a
    drawn group moves together. Two runs over the same data with the same
    seed produce identical bounds (deterministic by contract).
    """
    by_group: dict[str, list[str]] = {}
    for key in sorted(values):
        by_group.setdefault(groups[key], []).append(key)
    group_ids = sorted(by_group)
    if not group_ids:
        return (0.0, 1.0, {"groups": 0, "resamples": 0, "seed": seed})
    rng = random.Random(seed)
    stats = []
    for _ in range(resamples):
        chosen = [rng.choice(group_ids) for _ in group_ids]
        sample = [values[k] for group in chosen for k in by_group[group]]
        stats.append(sum(sample) / len(sample))
    stats.sort()
    low = stats[int((alpha / 2) * resamples)]
    high = stats[min(resamples - 1, int((1 - alpha / 2) * resamples) - 1)]
    return (low, high, {"groups": len(group_ids), "resamples": resamples, "seed": seed})


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile over sorted-copy semantics; None if empty."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[rank]
