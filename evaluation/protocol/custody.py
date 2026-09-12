"""Custodian gate for held-out labels and permissioned incident data.

Tuning workers get development fixtures and this protocol — never the
untouched labels. Worktrees are not an access boundary (AGENTS.md), and a
different folder inside the same repository is not custody either
(planning/quality/EVALUATION.md). This module therefore fails closed:

* an evaluation/permissioned run must name an explicit label root via
  ``--label-root`` or ``INKFLIP_EVAL_LABEL_ROOT``;
* that root must resolve to a directory outside the repository checkout —
  a label file committed or copied into the tree is refused by
  construction;
* the label file must match the plan's pinned SHA-256 and declared count,
  so an unattested or stale label store is refused; and
* every label page must reference a declared corpus page, and every corpus
  page must be labeled — the denominator cannot silently shrink.

Labels are read into memory for scoring only. Emission paths serialize
digests and aggregate counts; ``assert_labels_not_emitted`` and
``scan_forbidden_keys`` are run over every artifact before it is written,
so label content cannot reach logs or task artifacts.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

LABEL_ROOT_ENV = "INKFLIP_EVAL_LABEL_ROOT"
GATED_SPLITS = ("evaluation", "permissioned")
# Generic truth vocabulary is protocol enum, not label content. Any other
# string inside a label record is held-out content that must never be
# emitted into artifacts, logs or reports.
TRUTH_VOCABULARY = {"clean", "supported_failure", "unsupported"}
# Report keys that would expose held-out truth or incident identity.
FORBIDDEN_REPORT_KEYS = {
    "truth", "expected", "expected_finding", "consent_ref", "incident_ref",
    "display_name", "label_note", "mechanism", "source_name",
}
# Tokens inside a key are just as damning: "per_page_truth" or
# "page_consent_ref" expose the same held-out content. Matching is on whole
# alphanumeric tokens so "labels_sha256" and "unlabeled" stay permitted.
FORBIDDEN_KEY_TOKENS = {
    "truth", "expected", "consent", "incident", "mechanism", "label",
}


class CustodyError(ValueError):
    """Label access was refused, or label content would leak."""


def labels_are_gated(split: str) -> bool:
    """Whether a split's labels sit behind the custodian gate."""
    return split in GATED_SPLITS


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_labels(label_store: dict, repo_root: Path,
                   label_root: str | os.PathLike | None = None) -> tuple[dict, str]:
    """Resolve held-out labels for a gated split. Fails closed.

    ``label_root`` must come from the evaluator invocation. It must be a
    directory outside the repository checkout; a different folder in the
    shared tree is not custody. The label file must match the plan's pinned
    digest and count exactly. Returns ``(labels, verified_file_sha256)`` —
    the digest is the only label identity artifacts may carry.
    """
    root_value = label_root if label_root is not None else os.environ.get(LABEL_ROOT_ENV)
    if not root_value:
        raise CustodyError(
            "held-out labels require an explicit label root "
            f"(--label-root or {LABEL_ROOT_ENV}); failing closed"
        )
    root = Path(root_value).resolve()
    repo = Path(repo_root).resolve()
    if not root.is_dir():
        raise CustodyError(f"label root is not a directory: {root}")
    if root == repo or _inside(root, repo):
        raise CustodyError(
            "held-out labels inside a repository checkout are not custody; "
            "the label root must live outside every worktree"
        )
    name = label_store.get("labels_file") or "eval-labels.json"
    candidate = (root / name).resolve()
    if not _inside(candidate, root):
        raise CustodyError(f"label file {name!r} escapes the label root")
    if not candidate.is_file():
        raise CustodyError(f"label file missing in label root: {name}")
    payload = candidate.read_bytes()
    expected = label_store.get("sha256")
    if expected is None:
        raise CustodyError(
            "the plan does not pin a label digest; the custodian must issue "
            "labels before any evaluation run is scored"
        )
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise CustodyError(
            "label digest mismatch; refusing unattested or stale labels "
            f"(pinned {expected[:16]}..., found {actual[:16]}...)"
        )
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise CustodyError(f"label store is not valid JSON: {error}") from error
    if not isinstance(data, dict) or data.get("kind") != label_store.get("schema"):
        raise CustodyError("label store kind does not match the pinned schema")
    pages = data.get("pages")
    if not isinstance(pages, dict) or not pages:
        raise CustodyError("label store declares no pages")
    declared = label_store.get("label_count")
    if isinstance(declared, int) and declared > 0 and len(pages) != declared:
        raise CustodyError(
            f"label count {len(pages)} does not match pinned store count {declared}"
        )
    for key, record in pages.items():
        if not isinstance(record, dict):
            raise CustodyError(f"label {key} is not a record")
        if record.get("truth") not in TRUTH_VOCABULARY:
            raise CustodyError(f"label {key} has unknown truth {record.get('truth')!r}")
        _check_label_record(key, record)
    return data, actual


def _check_label_record(key: str, record: dict) -> None:
    """Fail closed on malformed declared expectations — never silently drop."""
    expected = record.get("expected_occurrences")
    if expected is not None and (type(expected) is not int or expected < 0):
        raise CustodyError(
            f"label {key}: expected_occurrences must be a nonnegative integer")


def validate_permissioned_labels(labels: dict) -> None:
    """Permissioned incident labels additionally require consent references."""
    for key, record in labels["pages"].items():
        if not record.get("consent_ref"):
            raise CustodyError(
                f"permissioned label {key} lacks a consent reference; "
                "real incident data without consent never enters scoring"
            )


def check_labels_cover_corpus(labels: dict, corpus_page_keys: list[str]) -> None:
    """Every label must name a corpus page; every corpus page must be labeled.

    This is what keeps denominators precise: a corpus page without a truth
    label, or a label for a page outside the frozen corpus, is a hard
    failure rather than a silently dropped sample.
    """
    label_keys = set(labels["pages"])
    corpus_keys = set(corpus_page_keys)
    unlabeled = sorted(corpus_keys - label_keys)
    stray = sorted(label_keys - corpus_keys)
    problems = []
    if unlabeled:
        problems.append(f"{len(unlabeled)} corpus pages have no truth label "
                        f"(first: {unlabeled[0]})")
    if stray:
        problems.append(f"{len(stray)} labels name pages outside the frozen corpus "
                        f"(first: {stray[0]})")
    if problems:
        raise CustodyError("; ".join(problems))


def label_secret_values(labels: dict) -> set[str]:
    """Every label-content string that must never appear in an artifact."""
    secrets: set[str] = set()
    for record in labels.get("pages", {}).values():
        if not isinstance(record, dict):
            continue
        for value in record.values():
            if isinstance(value, str) and value and value not in TRUTH_VOCABULARY:
                secrets.add(value)
            elif isinstance(value, list):
                secrets.update(v for v in value
                               if isinstance(v, str) and v and v not in TRUTH_VOCABULARY)
    for key, value in labels.items():
        if key != "pages" and isinstance(value, str) and value:
            secrets.add(value)
    return secrets


def assert_labels_not_emitted(serialized: str, labels: dict | None) -> None:
    """Refuse serialization that would carry any label content."""
    if not labels:
        return
    for secret in sorted(label_secret_values(labels)):
        if secret in serialized:
            raise CustodyError(
                f"label content would be emitted into an artifact: {secret[:24]!r}..."
            )


def _forbidden_key(key: str) -> bool:
    if key in FORBIDDEN_REPORT_KEYS:
        return True
    tokens = {t for t in re.split(r"[^0-9A-Za-z]+", key.lower()) if t}
    return bool(tokens & FORBIDDEN_KEY_TOKENS)


def scan_forbidden_keys(obj, path: str = "$") -> list[str]:
    """Report-key paths that would expose held-out truth or incident identity."""
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if _forbidden_key(key):
                found.append(f"{path}.{key}")
            found.extend(scan_forbidden_keys(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found.extend(scan_forbidden_keys(value, f"{path}[{index}]"))
    return found


def load_ungated_labels(path: Path, schema: str) -> dict:
    """Load development/public labels from a committed, ungated file.

    Only splits outside the custodian gate may use this path; held-out and
    permissioned labels must come through :func:`resolve_labels` so the
    outside-checkout and pinned-digest rules apply.
    """
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise CustodyError(f"unreadable label file {path}: {error}") from error
    if not isinstance(data, dict) or data.get("kind") != schema:
        raise CustodyError("label file kind does not match the declared schema")
    pages = data.get("pages")
    if not isinstance(pages, dict) or not pages:
        raise CustodyError("label file declares no pages")
    for key, record in pages.items():
        if not isinstance(record, dict) or record.get("truth") not in TRUTH_VOCABULARY:
            raise CustodyError(f"label {key} is malformed")
        _check_label_record(key, record)
    return data
