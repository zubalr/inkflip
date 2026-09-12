"""Evaluation manifest kinds, validation, digests and corpus freezing.

Two file kinds live under ``evaluation/manifests/``:

* ``corpus_manifest`` — the contract-schema CorpusManifest (kind/
  schema_version/entries/source_root_policy/split, closed key sets). The
  development and public_demo corpus manifests are frozen directly from
  ``fixtures/manifest.json`` so the T05 truth anchors (sha256, family,
  split, control edges) carry over byte-for-byte.
* ``evaluation_plan`` — the custodian's held-out design: population
  minimums, split-manifest digests, the pinned label store, the candidate
  freeze and the declared release targets. The format has no field that can
  carry a verdict: a plan cannot attest its own pass.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .lineage import SPLITS

KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
COMPARATORS = (">=", "<=", "==", "<")
# The plan format is closed: an unrecognized top-level key is rejected
# rather than ignored, so a plan cannot smuggle a verdict in under an
# unexpected name.
ALLOWED_PLAN_KEYS = {
    "kind", "schema_version", "plan_id", "protocol", "custodian",
    "population", "split_manifests", "label_store", "candidate_freeze",
    "targets", "retirement_policy", "public_boundary", "diagnosis",
    "note", "notes", "seed_policy",
}
# A plan/run key that could carry a self-attested outcome is forbidden by
# construction — verdicts are computed from measured runs, never declared.
SELF_ATTEST_KEYS = {"verdict", "verdicts", "met", "passed", "status_met",
                    "targets_met", "self_attested", "attested", "approved"}

CORPUS_ENTRY_KEYS = {"key", "source_path", "sha256", "group_id", "pages"}
CORPUS_MANIFEST_KEYS = {"kind", "schema_version", "entries",
                        "source_root_policy", "split"}
# Fixture-manifest split names map onto the contract corpus split enum.
FIXTURE_SPLIT_MAP = {"public": "public_demo", "development": "development"}
SOURCE_ROOT_POLICY = "explicit_local_root_no_symlinks"


class ManifestError(ValueError):
    """A manifest is malformed, self-attested or off-contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def _scan_forbidden_keys(obj, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in SELF_ATTEST_KEYS:
                found.append(f"{path}.{key}")
            found.extend(_scan_forbidden_keys(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found.extend(_scan_forbidden_keys(value, f"{path}[{index}]"))
    return found


def _check_entry(entry: dict, where: str) -> None:
    _require(set(entry) == CORPUS_ENTRY_KEYS,
             f"{where}: entry keys must be exactly {sorted(CORPUS_ENTRY_KEYS)}")
    _require(isinstance(entry["key"], str) and KEY_RE.match(entry["key"]),
             f"{where}: bad entry key {entry['key']!r}")
    source = entry["source_path"]
    _require(isinstance(source, str) and 0 < len(source) <= 512
             and ".." not in source.split("/"),
             f"{where}: source_path must be a bounded in-root path")
    _require(isinstance(entry["sha256"], str) and SHA_RE.match(entry["sha256"]),
             f"{where}: sha256 must be a lowercase hex digest")
    _require(isinstance(entry["group_id"], str) and KEY_RE.match(entry["group_id"]),
             f"{where}: bad group_id {entry['group_id']!r}")
    pages = entry["pages"]
    _require(isinstance(pages, list) and pages
             and all(type(p) is int and p >= 0 for p in pages)
             and len(set(pages)) == len(pages),
             f"{where}: pages must be a non-empty list of unique indices")


def validate_corpus_manifest(manifest: dict, where: str = "corpus_manifest") -> None:
    """Validate a corpus manifest against the contract CorpusManifest shape."""
    _require(isinstance(manifest, dict), f"{where}: not an object")
    _require(set(manifest) == CORPUS_MANIFEST_KEYS,
             f"{where}: keys must be exactly {sorted(CORPUS_MANIFEST_KEYS)}")
    _require(manifest["kind"] == "corpus_manifest", f"{where}: wrong kind")
    _require(manifest["schema_version"] == "1.0.0", f"{where}: wrong schema_version")
    _require(manifest["source_root_policy"] == SOURCE_ROOT_POLICY,
             f"{where}: source_root_policy must be {SOURCE_ROOT_POLICY!r}")
    _require(manifest["split"] in SPLITS, f"{where}: unknown split")
    entries = manifest["entries"]
    _require(isinstance(entries, list) and entries, f"{where}: entries required")
    keys = set()
    for index, entry in enumerate(entries):
        _check_entry(entry, f"{where}.entries[{index}]")
        _require(entry["key"] not in keys, f"{where}: duplicate key {entry['key']}")
        keys.add(entry["key"])


def corpus_page_keys(manifest: dict) -> list[str]:
    """Every page key a corpus manifest declares, content-addressed.

    Identical source bytes collapse to one page key: two manifest entries
    naming the same sha256 are the same document and one sample unit.
    """
    return sorted({
        f"{entry['sha256']}:{page}"
        for entry in manifest["entries"]
        for page in entry["pages"]
    })


def corpus_groups(manifest: dict) -> dict[str, str]:
    """Map every declared page key to its effective document/generator group.

    The effective group is lineage-canonical: entries joined by shared
    group ids, control edges or identical bytes resample as one unit, so
    byte-identical documents can never act as two independent samples. The
    canonical id is the smallest declared group id in the cluster, which
    keeps the mapping deterministic.
    """
    from .lineage import sibling_groups
    by_key = {entry["key"]: entry for entry in manifest["entries"]}
    effective: dict[str, str] = {}
    for members in sibling_groups(manifest["entries"]).values():
        canonical = min(by_key[m]["group_id"] for m in members)
        for member in members:
            entry = by_key[member]
            for page in entry["pages"]:
                effective[f"{entry['sha256']}:{page}"] = canonical
    return effective


def corpus_entries_from_fixtures(fixture_manifest: dict, split: str) -> list[dict]:
    """Freeze T05 fixture entries of one split into CorpusEntry records.

    Only page-bearing PDF payloads enter a corpus; JSON process fixtures
    (worker-fault doubles) are supervised scenarios, not corpus documents.
    The group id is the fixture lineage: ``<fixture_id>-<family>`` — every
    variant and its control twin share it by construction.
    """
    entries = []
    for item in sorted(fixture_manifest["entries"], key=lambda e: e["path"]):
        if item["split"] != split or not item["path"].endswith(".pdf"):
            continue
        key = re.sub(r"[^a-z0-9_-]+", "-", Path(item["path"]).stem.lower()).strip("-")
        entries.append({
            "key": key,
            "source_path": f"fixtures/{item['path']}",
            "sha256": item["sha256"],
            "group_id": f"{str(item['fixture_id']).lower()}-{item['family']}",
            "pages": [0],
        })
    return entries


def build_corpus_manifest(fixture_manifest: dict, split: str) -> dict:
    """Deterministic corpus manifest for a fixture-manifest split name."""
    _require(split in FIXTURE_SPLIT_MAP,
             f"fixture split {split!r} is not a corpus split source")
    return {
        "kind": "corpus_manifest",
        "schema_version": "1.0.0",
        "source_root_policy": SOURCE_ROOT_POLICY,
        "split": FIXTURE_SPLIT_MAP[split],
        "entries": corpus_entries_from_fixtures(fixture_manifest, split),
    }


def _check_target(target: dict, where: str) -> None:
    _require(isinstance(target, dict), f"{where}: target must be an object")
    allowed = {"id", "metric", "comparator", "threshold", "min_samples", "note"}
    _require(set(target) <= allowed,
             f"{where}: unknown target keys {sorted(set(target) - allowed)}")
    _require(isinstance(target.get("id"), str) and KEY_RE.match(target["id"]),
             f"{where}: bad target id")
    _require(isinstance(target.get("metric"), str) and target["metric"],
             f"{where}: metric required")
    _require(target.get("comparator") in COMPARATORS,
             f"{where}: comparator must be one of {COMPARATORS}")
    _require(type(target.get("threshold")) in (int, float),
             f"{where}: numeric threshold required")
    if "min_samples" in target:
        _require(type(target["min_samples"]) is int and target["min_samples"] >= 0,
                 f"{where}: min_samples must be a nonnegative integer")


def validate_evaluation_plan(plan: dict, where: str = "evaluation_plan") -> None:
    """Validate the custodian's held-out evaluation plan.

    Rejects any field that could carry a self-attested verdict: targets are
    declarations of intent and stay UNMET until a bound run produces counts.
    """
    _require(isinstance(plan, dict), f"{where}: not an object")
    _require(plan.get("kind") == "evaluation_plan", f"{where}: wrong kind")
    _require(plan.get("schema_version") == "1.0.0", f"{where}: wrong schema_version")
    _require(set(plan) <= ALLOWED_PLAN_KEYS,
             f"{where}: unknown keys {sorted(set(plan) - ALLOWED_PLAN_KEYS)}")
    _require(isinstance(plan.get("plan_id"), str) and KEY_RE.match(plan["plan_id"]),
             f"{where}: bad plan_id")
    bad = _scan_forbidden_keys(plan)
    _require(not bad, f"{where}: self-attested outcome keys forbidden: {bad[:3]}")

    population = plan.get("population")
    _require(isinstance(population, dict), f"{where}: population required")
    for name in ("clean_pages_min", "supported_failure_pages_min"):
        _require(type(population.get(name)) is int and population[name] >= 0,
                 f"{where}.population: {name} must be a nonnegative integer")
    _require(type(population.get("mechanism_groups_min")) is int
             and population["mechanism_groups_min"] >= 2,
             f"{where}.population: mechanism_groups_min must be >= 2")
    _require(isinstance(population.get("grouping_rule"), str)
             and population["grouping_rule"],
             f"{where}.population: grouping_rule required")

    splits = plan.get("split_manifests")
    _require(isinstance(splits, dict), f"{where}: split_manifests required")
    _require(set(splits) <= set(SPLITS), f"{where}: unknown split names")
    for name, ref in splits.items():
        _require(isinstance(ref, dict), f"{where}.split_manifests.{name}: object required")
        path = ref.get("path")
        sha = ref.get("sha256")
        _require(path is None or (isinstance(path, str) and ".." not in path.split("/")),
                 f"{where}.split_manifests.{name}: path must stay in the repository")
        _require(sha is None or (isinstance(sha, str) and SHA_RE.match(sha)),
                 f"{where}.split_manifests.{name}: sha256 must be a hex digest")
        if path is not None:
            _require(sha is not None,
                     f"{where}.split_manifests.{name}: a pinned manifest needs its digest")

    store = plan.get("label_store")
    _require(isinstance(store, dict), f"{where}: label_store required")
    _require(store.get("permissioned") is True,
             f"{where}.label_store: held-out labels must be permissioned")
    _require(isinstance(store.get("schema"), str) and store["schema"],
             f"{where}.label_store: schema required")
    _require(isinstance(store.get("labels_file"), str) and store["labels_file"],
             f"{where}.label_store: labels_file required")
    sha = store.get("sha256")
    _require(sha is None or (isinstance(sha, str) and SHA_RE.match(sha)),
             f"{where}.label_store: sha256 must be null or a hex digest")
    _require(type(store.get("label_count")) is int and store["label_count"] >= 0,
             f"{where}.label_store: label_count must be a nonnegative integer")

    freeze = plan.get("candidate_freeze")
    _require(isinstance(freeze, dict), f"{where}: candidate_freeze required")
    commit = freeze.get("commit")
    _require(commit is None or (isinstance(commit, str) and COMMIT_RE.match(commit)),
             f"{where}.candidate_freeze: commit must be null or a full git commit")
    for name in ("lock_sha256", "config_sha256"):
        value = freeze.get(name)
        _require(value is None or (isinstance(value, str) and SHA_RE.match(value)),
                 f"{where}.candidate_freeze: {name} must be null or a hex digest")

    targets = plan.get("targets")
    _require(isinstance(targets, list) and targets, f"{where}: targets required")
    seen = set()
    for index, target in enumerate(targets):
        _check_target(target, f"{where}.targets[{index}]")
        _require(target["id"] not in seen, f"{where}: duplicate target {target['id']}")
        seen.add(target["id"])


def load_manifest(path: Path) -> dict:
    """Load and validate a corpus manifest or evaluation plan by its kind."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"{path}: unreadable manifest: {error}") from error
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind == "corpus_manifest":
        validate_corpus_manifest(data, str(path))
    elif kind == "evaluation_plan":
        validate_evaluation_plan(data, str(path))
    else:
        raise ManifestError(f"{path}: unknown manifest kind {kind!r}")
    return data
