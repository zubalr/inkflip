"""Sibling lineage grouping, frozen split assignment and leakage audit.

Splits group by generator family, producer/layout and shared source
ancestry — never by individual pages at random. A cover/no-cover twin and
every seed variation of one source stay in one split; public/development
cases and their generated siblings never enter the untouched evaluation
denominator.

Three lineage edges union entries transitively:

1. a shared declared ``group_id`` (corpus manifests) or
   ``fixture_id``/``family`` pair (T05 fixture-manifest entries),
2. a control <-> variant edge (fixture-manifest ``control`` or corpus
   ``controls`` references), and
3. identical content ``sha256`` — the same source bytes reused under a new
   name still share ancestry (e.g. the F17 clean control is literally the
   F03 raster-only file).
"""
from __future__ import annotations

import random

SPLITS = ("development", "public_demo", "evaluation", "permissioned")
# Splits whose groups may never appear in untouched evaluation claims.
CLAIM_EXCLUDED = ("development", "public_demo")
# Splits whose labels stay behind the custodian gate.
GATED_SPLITS = ("evaluation", "permissioned")


class LeakageError(ValueError):
    """A sibling group straddles a split boundary or bytes leaked."""


def _normalize_entry(entry: dict, default_split: str | None = None) -> dict:
    """Adapt a fixture-manifest or corpus-manifest entry to one node shape."""
    if "group_id" in entry and "key" in entry:
        # CorpusEntry (packages/contracts schema): the declared group is the
        # lineage identity chosen when the corpus was frozen.
        return {
            "key": entry["key"],
            "sha256": entry["sha256"],
            "group_id": entry["group_id"],
            "split": entry.get("split", default_split),
            "controls": set(entry.get("controls", ())),
        }
    # T05 fixture-manifest entry: fixture_id + family is the declared
    # generator group; `control` points at the sibling control path.
    fixture_id = str(entry["fixture_id"]).lower()
    return {
        "key": entry["path"],
        "sha256": entry["sha256"],
        "group_id": f"{fixture_id}-{entry['family']}",
        "split": entry.get("split", default_split),
        "controls": {entry["control"]} if entry.get("control") else set(),
    }


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        self._parent.setdefault(key, key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Deterministic root keeps group listings stable.
            self._parent[max(ra, rb)] = min(ra, rb)


def sibling_groups(entries: list[dict]) -> dict[str, list[str]]:
    """Cluster entries sharing document lineage.

    Returns ``{root_key: sorted member keys}``; every returned cluster is a
    set of siblings that must live in exactly one split.
    """
    nodes = [_normalize_entry(e) for e in entries]
    by_key = {n["key"]: n for n in nodes}
    by_group: dict[str, list[str]] = {}
    by_sha: dict[str, list[str]] = {}
    uf = _UnionFind()
    for node in nodes:
        uf.find(node["key"])
        by_group.setdefault(node["group_id"], []).append(node["key"])
        by_sha.setdefault(node["sha256"], []).append(node["key"])
    for node in nodes:
        for peer in by_group[node["group_id"]]:
            uf.union(node["key"], peer)
        for peer in by_sha[node["sha256"]]:
            uf.union(node["key"], peer)
        for control in node["controls"]:
            if control in by_key:
                uf.union(node["key"], control)
    groups: dict[str, list[str]] = {}
    for node in nodes:
        groups.setdefault(uf.find(node["key"]), set())
        groups[uf.find(node["key"])].add(node["key"])
    return {root: sorted(members) for root, members in sorted(groups.items())}


def split_violations(manifests: dict[str, list[dict]]) -> list[str]:
    """Every sibling-lineage violation across the named splits.

    ``manifests`` maps a split name to its entries. A violation is any
    lineage group whose members land in more than one split — a fixture and
    its transformed siblings can never straddle a dev/eval boundary, and
    identical bytes in two splits are a leak even under different names.
    """
    tagged: list[dict] = []
    for split in sorted(manifests):
        if split not in SPLITS:
            raise LeakageError(f"unknown split {split!r}; expected one of {SPLITS}")
        for entry in manifests[split]:
            node = _normalize_entry(entry, default_split=split)
            node["split"] = split
            tagged.append(node)
    by_key = {n["key"]: n for n in tagged}
    if len(by_key) != len(tagged):
        raise LeakageError("duplicate entry key across manifests")
    violations: list[str] = []
    for members in sibling_groups(tagged).values():
        splits = sorted({by_key[m]["split"] for m in members})
        if len(splits) > 1:
            preview = ", ".join(members[:4])
            violations.append(
                f"lineage group straddles splits {splits}: {preview}"
                + (", ..." if len(members) > 4 else "")
            )
    return violations


def assert_no_leakage(manifests: dict[str, list[dict]]) -> None:
    """Raise LeakageError on the first sign of a straddling group."""
    violations = split_violations(manifests)
    if violations:
        raise LeakageError("; ".join(violations))


def assign_naive(keys: list[str], splits: list[str], seed: int) -> dict[str, str]:
    """Per-entry random assignment — the baseline that CAN straddle siblings.

    Kept only to demonstrate, in tests, why the grouped assignment below is
    the protocol: independent draws can put a control and its variants on
    opposite sides of a boundary.
    """
    rng = random.Random(seed)
    return {key: rng.choice(list(splits)) for key in list(keys)}


def assign_grouped(groups: dict[str, list[str]], splits: list[str], seed: int) -> dict[str, str]:
    """Assign whole lineage groups to splits.

    One draw per group, applied to every member: a fixture and its siblings
    are assigned together, so no seed can make them straddle a boundary.
    """
    rng = random.Random(seed)
    assignment: dict[str, str] = {}
    for members in sorted(groups.values()):
        chosen = rng.choice(list(splits))
        for member in members:
            assignment[member] = chosen
    return assignment
