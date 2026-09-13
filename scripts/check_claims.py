#!/usr/bin/env python3
"""Mechanical checks for Inkflip's public documentation (T49).

Verifies what a machine *can* verify about README.md, docs/*.md,
CONTRIBUTING.md and SECURITY.md:

  1. required documentation files exist;
  2. every local markdown link (file and #anchor) resolves;
  3. every referenced local image/evidence path exists and is non-empty;
  4. versions quoted in prose match the frozen pins in the manifests;
  5. every `bun run <name>` mentioned exists in the command registry (or in
     apps/web/package.json when the doc shows it run from apps/web);
  6. no forbidden claim phrase (data-driven: tests/docs/claims-rules.json)
     appears — e.g. unsupported "safe/fraud/AI sees"/score/autonomy claims;
  7. snapshot facts the docs state are dated and source-bound: each fact in
     tests/docs/snapshot-facts.json must be backed by its dated evidence
     record, and a doc may neither omit a recorded fact nor contradict it.
     Facts are deliberately NOT permanent rules: when reality changes, the
     evidence, the facts file and the docs change together in one reviewed
     change, and this check accepts the new consistent state (the negative
     tests prove both directions).

The rules live in tests/docs/claims-rules.json and
tests/docs/snapshot-facts.json, not in this file's logic, so tightening a
rule never requires editing the checker. The checker validates files
authored independently of it and is itself regression-tested against
deliberately broken input (tests/docs/test_checker_negative.py) so it cannot
merely approve its own generated text.

Usage:
  python3 scripts/check_claims.py                 # static checks, exit 0/1
  python3 scripts/check_claims.py --json          # machine-readable report
  python3 scripts/check_claims.py --run-commands  # additionally execute the
                    # commands the docs present as working (slow: builds and
                    # full suites; reads tests/docs/verified_commands.json)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "tests" / "docs" / "claims-rules.json"
RUN_COMMANDS = ROOT / "tests" / "docs" / "verified_commands.json"

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
BUN_RUN_RE = re.compile(r"bun run ([a-z0-9][a-z0-9:-]*)")
ARTIFACT_RE = re.compile(r"artifacts/[A-Za-z0-9_\-./]+")


def tracked_files(root: Path) -> set[str] | None:
    """Set of git-tracked files, or None when root is not a git work tree.
    Docs must link tracked files: a file that merely exists locally (ignored
    or untracked) must not satisfy a public link."""
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return {line for line in out.stdout.splitlines() if line}


def github_slug(heading: str) -> str:
    text = heading.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text).strip("-")


def doc_headings(path: Path) -> set[str]:
    slugs = set()
    for line in path.read_text().splitlines():
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*$", line)
        if m:
            slugs.add(github_slug(m.group(1)))
    return slugs


def check_required_docs(root: Path, rules: dict) -> list[str]:
    problems = []
    for rel in rules["required_docs"]:
        if not (root / rel).is_file():
            problems.append(f"missing required documentation file: {rel}")
    return problems


def check_links(root: Path, rules: dict) -> list[str]:
    problems = []
    root = root.resolve()
    tracked = tracked_files(root)
    for rel in rules["checked_docs"]:
        path = root / rel
        if not path.is_file():
            problems.append(f"cannot check links of missing file: {rel}")
            continue
        headings_cache: dict[str, set[str]] = {}

        def headings(target_rel: str) -> set[str]:
            if target_rel not in headings_cache:
                tp = root / target_rel
                headings_cache[target_rel] = doc_headings(tp) if tp.is_file() else set()
            return headings_cache[target_rel]

        for m in LINK_RE.finditer(path.read_text()):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            file_part, _, anchor = target.partition("#")
            if file_part:
                resolved = (path.parent / file_part).resolve()
                if not resolved.exists():
                    problems.append(f"{rel}: broken link target: {target}")
                    continue
                if tracked is not None:
                    rel_from_root = resolved.relative_to(root).as_posix()
                    if rel_from_root not in tracked:
                        problems.append(f"{rel}: link target is not tracked in git: {file_part}")
                        continue
                if anchor and resolved.suffix == ".md":
                    rel_resolved = resolved.relative_to(root).as_posix()
                    if anchor not in headings(rel_resolved):
                        problems.append(f"{rel}: missing heading #{anchor} in {rel_resolved}")
            elif anchor:
                if anchor not in headings(rel):
                    problems.append(f"{rel}: missing internal heading #{anchor}")
    return problems


def check_referenced_files(root: Path, rules: dict) -> list[str]:
    problems = []
    tracked = tracked_files(root)
    for rel in rules["checked_docs"]:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text()
        for m in LINK_RE.finditer(text):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            file_part = target.partition("#")[0]
            if not file_part:
                continue
            resolved = (path.parent / file_part).resolve()
            if resolved.is_file() and resolved.stat().st_size == 0:
                problems.append(f"{rel}: referenced file is empty: {file_part}")
            if tracked is not None and resolved.is_file():
                rel_from_root = resolved.relative_to(root).as_posix()
                if rel_from_root not in tracked:
                    problems.append(f"{rel}: referenced file is not tracked in git: {file_part}")
        for m in ARTIFACT_RE.finditer(text):
            token = m.group(0).rstrip(".,;:")
            if "<" in token:  # placeholder like artifacts/tasks/<Txx>/
                continue
            if not (root / token).exists():
                problems.append(f"{rel}: referenced evidence path does not exist: {token}")
            elif tracked is not None and token not in tracked and not (root / token).is_dir():
                problems.append(f"{rel}: referenced evidence path is not tracked in git: {token}")
    return problems


def _extract_pin(root: Path, rule: dict) -> str | None:
    pin_file = root / rule["pin_file"]
    if not pin_file.is_file():
        return None
    raw = pin_file.read_text()
    if "pin_json_path" in rule:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        node = data
        for part in rule["pin_json_path"].split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        value = str(node)
        if "pin_regex" in rule:
            m = re.search(rule["pin_regex"], value)
            return m.group(1) if m else None
        return value
    m = re.search(rule["pin_regex"], raw, re.MULTILINE)
    return m.group(1) if m else None


def check_versions(root: Path, rules: dict) -> list[str]:
    problems = []
    for rule in rules["version_pins"]:
        pin = _extract_pin(root, rule)
        if pin is None:
            problems.append(f"version pin for {rule['name']} could not be read from {rule['pin_file']}")
            continue
        for rel in rules["checked_docs"]:
            path = root / rel
            if not path.is_file():
                continue
            allowed = {a.get("version"): a.get("reason", "") for a in rule.get("allowed_other_versions", [])}
            for m in re.finditer(rule["doc_pattern"], path.read_text()):
                quoted = m.group(1)
                if quoted != pin and quoted not in allowed:
                    problems.append(
                        f"{rel}: quotes {rule['name']} version {quoted} but the frozen pin is {pin}"
                    )
    return problems


def check_registry_commands(root: Path, rules: dict) -> list[str]:
    registry_path = root / "config" / "acceptance-commands.json"
    web_pkg_path = root / "apps" / "web" / "package.json"
    try:
        registry = set(json.loads(registry_path.read_text())["commands"])
    except (OSError, json.JSONDecodeError, KeyError):
        return ["config/acceptance-commands.json is missing or unreadable"]
    try:
        web_scripts = set(json.loads(web_pkg_path.read_text()).get("scripts", {}))
    except (OSError, json.JSONDecodeError):
        web_scripts = set()

    problems = []
    for rel in rules["checked_docs"]:
        path = root / rel
        if not path.is_file():
            continue
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            for m in BUN_RUN_RE.finditer(line):
                name = m.group(1).rstrip(".,;:")
                previous = lines[i - 1].strip() if i else ""
                in_web_context = "apps/web && bun run" in line or previous.endswith("apps/web")
                if in_web_context:
                    if name not in web_scripts:
                        problems.append(f"{rel}: 'bun run {name}' is not an apps/web script")
                elif name not in registry:
                    problems.append(f"{rel}: 'bun run {name}' is not in the command registry")
    return problems


def check_forbidden_phrases(root: Path, rules: dict) -> list[str]:
    problems = []
    for rel in rules["checked_docs"]:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text().lower()
        for phrase in rules["forbidden_phrases"]:
            if phrase.lower() in text:
                problems.append(f"{rel}: forbidden claim phrase present: {phrase!r}")
    return problems


def check_snapshot_facts(root: Path, rules: dict) -> list[str]:
    """Dated, source-bound facts: docs may state a fact only while a dated
    evidence record supports it. These are not permanent rules — when a fact
    legitimately changes, the evidence, tests/docs/snapshot-facts.json and
    the docs change together in one reviewed change, and this check accepts
    the new consistent state. See the file's _purpose for the contract."""
    facts_path = root / rules["snapshot_facts_file"]
    try:
        facts = json.loads(facts_path.read_text())["facts"]
    except (OSError, json.JSONDecodeError, KeyError):
        return [f"snapshot facts file missing or malformed: {rules['snapshot_facts_file']}"]
    problems = []
    for fact in facts:
        fid = fact.get("id", "<unnamed>")
        evidence = root / fact["evidence"]
        if not evidence.is_file():
            problems.append(f"fact {fid}: evidence file missing: {fact['evidence']}")
            continue
        evidence_text = evidence.read_text()
        marker = fact.get("evidence_marker")
        if marker and not re.search(marker, evidence_text):
            problems.append(
                f"fact {fid}: evidence {fact['evidence']} lacks marker {marker!r} "
                f"(as_of {fact.get('as_of')}); update evidence, facts file and docs together"
            )
        for rel, doc_rules in fact.get("per_doc", {}).items():
            path = root / rel
            if not path.is_file():
                problems.append(f"fact {fid}: doc missing: {rel}")
                continue
            text = path.read_text()
            for pattern in doc_rules.get("must_contain", []):
                if not re.search(pattern, text, re.IGNORECASE):
                    problems.append(f"fact {fid}: {rel} no longer states the fact (pattern {pattern!r} absent)")
            for pattern in doc_rules.get("must_not_contain", []):
                if re.search(pattern, text, re.IGNORECASE):
                    problems.append(f"fact {fid}: {rel} contradicts the recorded state (pattern {pattern!r} present)")
    return problems


def check_required_phrases(root: Path, rules: dict) -> list[str]:
    """Permanent claims-hygiene requirements (see claims-rules.json)."""
    problems = []
    for rel, patterns in rules.get("required_phrases", {}).items():
        if rel.startswith("_"):
            continue
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel}: missing, required phrases unverifiable")
            continue
        text = path.read_text()
        for pattern in patterns:
            if not re.search(pattern, text, re.IGNORECASE):
                problems.append(f"{rel}: required claims-hygiene phrasing absent: {pattern!r}")
    return problems


CHECKS = [
    ("required_docs", check_required_docs),
    ("links", check_links),
    ("referenced_files", check_referenced_files),
    ("version_pins", check_versions),
    ("registry_commands", check_registry_commands),
    ("forbidden_phrases", check_forbidden_phrases),
    ("required_phrases", check_required_phrases),
    ("snapshot_facts", check_snapshot_facts),
]


def run_static_checks(root: Path) -> dict:
    rules = json.loads(RULES.read_text())
    report: dict[str, list[str]] = {}
    for name, fn in CHECKS:
        report[name] = fn(root, rules)
    return report


def run_verified_commands(root: Path) -> list[dict]:
    entries = json.loads(RUN_COMMANDS.read_text())["commands"]
    results = []
    for entry in entries:
        print(f"$ {' '.join(entry['argv'])}", flush=True)
        proc = subprocess.run(entry["argv"], cwd=root)
        results.append({"name": entry["name"], "exit_code": proc.returncode})
        print(f"  -> exit {proc.returncode}", flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    parser.add_argument(
        "--run-commands",
        action="store_true",
        help="also execute the commands the docs present as working (slow)",
    )
    args = parser.parse_args()

    report = run_static_checks(ROOT)
    failed = any(report.values())
    if args.run_commands:
        command_results = run_verified_commands(ROOT)
        report["commands"] = [
            {"name": r["name"], "exit_code": r["exit_code"], "ok": r["exit_code"] == 0}
            for r in command_results
        ]
        failed = failed or any(not r["ok"] for r in report["commands"])

    if args.json:
        print(json.dumps({"ok": not failed, "report": report}, indent=2))
    else:
        for name, problems in report.items():
            if name == "commands":
                continue
            status = "ok" if not problems else f"{len(problems)} problem(s)"
            print(f"{name}: {status}")
            for p in problems:
                print(f"  - {p}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
