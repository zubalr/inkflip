"""Shared builders for the T36 evaluation-protocol suite (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "fixtures"
MANIFESTS = ROOT / "evaluation" / "manifests"
EVALUATOR = ROOT / "scripts" / "evaluate_inspector.py"
LABEL_SCHEMA = "inkflip-eval-labels-v1"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def doc_sha(name: str) -> str:
    return sha(f"doc:{name}")


def page_key(doc: str, page: int = 0) -> str:
    return f"{doc_sha(doc)}:{page}"


def corpus_entry(key: str, sha256: str | None = None, group_id: str | None = None,
                 pages: list[int] | None = None) -> dict:
    return {
        "key": key,
        "source_path": f"heldout/{key}.pdf",
        "sha256": sha256 or doc_sha(key),
        "group_id": group_id or f"g-{key.split('-')[0]}",
        "pages": pages if pages is not None else [0],
    }


def corpus_manifest(split: str, entries: list[dict]) -> dict:
    return {
        "kind": "corpus_manifest",
        "schema_version": "1.0.0",
        "source_root_policy": "explicit_local_root_no_symlinks",
        "split": split,
        "entries": entries,
    }


def write_json(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    return path


def write_manifest(path: Path, obj: dict) -> Path:
    """Write a corpus manifest with the emitted byte layout."""
    return write_json(path, obj)


def labels_file(pages: dict[str, dict], kind: str = LABEL_SCHEMA) -> dict:
    return {"kind": kind, "pages": pages}


def label_page_keys(labels: dict) -> list[str]:
    return sorted(labels["pages"])


def make_label_store(labels: dict, labels_name: str = "eval-labels.json") -> dict:
    payload = (json.dumps(labels, indent=2, sort_keys=True) + "\n").encode()
    return {
        "schema": LABEL_SCHEMA,
        "labels_file": labels_name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "label_count": len(labels["pages"]),
        "permissioned": True,
        "root_env": "INKFLIP_EVAL_LABEL_ROOT",
    }, payload


def make_plan(label_store: dict | None = None, targets: list[dict] | None = None,
              **overrides) -> dict:
    plan = {
        "kind": "evaluation_plan",
        "schema_version": "1.0.0",
        "plan_id": "eval-test",
        "protocol": "evaluation/protocol 1.0.0",
        "custodian": {"role": "evaluation-custodian"},
        "population": {
            "clean_pages_min": 2,
            "supported_failure_pages_min": 2,
            "mechanism_groups_min": 2,
            "grouping_rule": "siblings stay in one split",
        },
        "split_manifests": {},
        "label_store": label_store or {
            "schema": LABEL_SCHEMA,
            "labels_file": "eval-labels.json",
            "sha256": None,
            "label_count": 0,
            "permissioned": True,
        },
        "candidate_freeze": {"commit": None, "lock_sha256": None, "config_sha256": None},
        "targets": targets if targets is not None else [
            {"id": "t_supported_coverage", "metric": "supported_coverage",
             "comparator": ">=", "threshold": 0.9},
            {"id": "t_clean_alerts", "metric": "clean_false_alerts_per_page",
             "comparator": "<=", "threshold": 0.05},
        ],
    }
    plan.update(overrides)
    return plan


def reading(doc: str, page: int = 0, status: str = "completed",
            check_id: str | None = None, resolution: str | None = None,
            finding_ids: list[str] | None = None, run_id: str = "attempt-1",
            **extra) -> dict:
    record = {
        "document_sha256": doc_sha(doc),
        "page_index": page,
        "check_id": check_id or f"c-{doc}-{page}".replace("_", "-"),
        "run_id": run_id,
        "status": status,
        "finding_ids": finding_ids or [],
    }
    if resolution is not None:
        record["resolution"] = resolution
    record.update(extra)
    return record


def make_run(readings: list[dict], corpus_sha256: str, commit: str = "a" * 40,
             planned_checks: list[str] | None = None, **extra) -> dict:
    run = {
        "kind": "inspection_run",
        "schema_version": "1.0.0",
        "candidate": {
            "commit": commit,
            "lock_sha256": sha("lock"),
            "config_sha256": sha("config"),
        },
        "corpus_manifest_sha256": corpus_sha256,
        "created_at": "2026-09-12T00:00:00+00:00",
        "readings": readings,
    }
    if planned_checks is not None:
        run["planned_checks"] = planned_checks
    run.update(extra)
    return run
