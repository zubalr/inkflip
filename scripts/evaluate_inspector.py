#!/usr/bin/env python3
"""Independent inspector evaluation entry point (T36). Stdlib only.

The evaluation custodian's tool. It freezes corpus manifests from
``fixtures/manifest.json``, audits grouped splits for sibling leakage,
reports declared release targets as UNMET until a real bound run produces
counts, scores an actual run against custodian-held labels, and emits
blinded-review/adjudication artifacts for useful-finding precision.

Held-out labels never pass through this script into logs or artifacts:
``evaluate`` resolves them only from an explicit label root outside every
repository checkout, verifies the plan's pinned digest, and serializes
only digests and aggregate counts through a leak-scanning write path.

Subcommands:

  emit-corpus     freeze fixture-manifest entries into a corpus manifest
                  (deterministic; --check verifies a committed manifest)
  verify-splits   audit corpus manifests for sibling lineage leakage
  status          print plan target verdicts (UNMET until a real bound run)
  evaluate        score one bound run: --plan --corpus --run --label-root
  review-form     emit a blinded reviewer labeling form from a run
  adjudicate      combine reviewer labels into an adjudication artifact
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.protocol import PROTOCOL_VERSION  # noqa: E402
from evaluation.protocol import custody, diagnosis, lineage, manifest, report  # noqa: E402

FIXTURE_MANIFEST = ROOT / "fixtures" / "manifest.json"


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _write_json(path: Path, obj: dict, labels: dict | None = None) -> None:
    """Write JSON only through the leak-scanning serializer."""
    body = (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()
    custody.assert_labels_not_emitted(body.decode(), labels)
    forbidden = custody.scan_forbidden_keys(obj)
    if forbidden:
        raise custody.CustodyError(f"artifact would expose held-out keys {forbidden[:3]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def cmd_emit_corpus(args: argparse.Namespace) -> int:
    fixture_manifest = _load_json(FIXTURE_MANIFEST)
    built = manifest.build_corpus_manifest(fixture_manifest, args.split)
    if args.check:
        committed = _load_json(args.out)
        manifest.validate_corpus_manifest(committed, str(args.out))
        if committed != built:
            print(f"CHECK FAIL: {args.out} differs from fixtures/manifest.json")
            return 1
        print(f"check ok: {args.out} matches the frozen fixture manifest")
        return 0
    _write_json(args.out, built)
    print(f"wrote {args.out}: {len(built['entries'])} entries, split {built['split']}")
    return 0


def cmd_verify_splits(args: argparse.Namespace) -> int:
    manifests: dict[str, list[dict]] = {}
    for path in args.manifests:
        data = manifest.load_manifest(path)
        if data["kind"] != "corpus_manifest":
            raise manifest.ManifestError(f"{path} is not a corpus manifest")
        if data["split"] in manifests:
            raise manifest.ManifestError(f"two manifests claim split {data['split']}")
        manifests[data["split"]] = data["entries"]
    violations = lineage.split_violations(manifests)
    if violations:
        for violation in violations:
            print(f"LEAKAGE: {violation}", file=sys.stderr)
        return 1
    total = sum(len(v) for v in manifests.values())
    print(f"splits ok: {total} entries across {sorted(manifests)}; no sibling straddles a boundary")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    plan = manifest.load_manifest(args.plan)
    result = report.status_report(plan, manifest.file_digest(args.plan))
    _write_json(args.out, result) if args.out else None
    for verdict in result["targets"]:
        print(f"{verdict['verdict']:>6}  {verdict['id']:<32} "
              f"{verdict['metric']} {verdict['comparator']} {verdict['threshold']} "
              f"({verdict['reason']})")
    print(f"plan {plan['plan_id']}: {result['summary']['unmet']} targets UNMET "
          f"(no bound evaluation run)", file=sys.stderr)
    # Status is an honest report, not a pass: exit nonzero while targets
    # stand unmet so callers cannot mistake declaration for evidence.
    return 0 if result["summary"]["all_met"] else 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    plan = manifest.load_manifest(args.plan)
    corpus = manifest.load_manifest(args.corpus)
    if corpus["kind"] != "corpus_manifest":
        raise manifest.ManifestError(f"{args.corpus} is not a corpus manifest")
    run = _load_json(args.run)
    corpus_sha = manifest.file_digest(args.corpus)

    labels = None
    labels_sha = None
    if custody.labels_are_gated(corpus["split"]):
        labels, labels_sha = custody.resolve_labels(
            plan["label_store"], ROOT, args.label_root)
        if corpus["split"] == "permissioned":
            custody.validate_permissioned_labels(labels)
    elif args.labels:
        labels = custody.load_ungated_labels(args.labels, plan["label_store"]["schema"])
        labels_sha = manifest.file_digest(args.labels)
    else:
        raise custody.CustodyError(
            f"split {corpus['split']} needs --labels; gated splits need --label-root")

    adjudication = _load_json(args.adjudication) if args.adjudication else None
    result = report.evaluate(
        plan, corpus, run, labels, labels_sha, corpus_sha,
        plan_sha256=manifest.file_digest(args.plan), adjudication=adjudication)
    serialized = report.serialize_report(result, labels)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(serialized)
    for verdict in result["targets"]:
        observed = verdict["observed"]
        shown = f"{observed:.4f}" if isinstance(observed, float) else str(observed)
        print(f"{verdict['verdict']:>6}  {verdict['id']:<32} "
              f"{verdict['metric']} {verdict['comparator']} {verdict['threshold']} "
              f"(observed {shown}; {verdict['reason']})")
    summary = result["summary"]
    print(f"evaluated {result['samples']['unique_pages']} unique pages "
          f"({result['samples']['readings']} readings, {result['samples']['groups']} groups): "
          f"{summary['met']} MET, {summary['unmet']} UNMET", file=sys.stderr)
    return 0 if summary["all_met"] else 1


def cmd_review_form(args: argparse.Namespace) -> int:
    run = _load_json(args.run)
    report.validate_run(run)
    findings = []
    for reading in run["readings"]:
        for finding_id in reading.get("finding_ids", ()):
            findings.append({
                "finding_sha256": finding_id,
                "page_ref": f"{reading['document_sha256'][:16]}:{reading['page_index']}",
            })
    form = diagnosis.blinded_review_form(
        findings, sample_size=args.sample, seed=args.seed, form_id=args.form_id)
    _write_json(args.out, form)
    print(f"wrote {args.out}: {len(form['items'])} blinded items")
    return 0


def cmd_adjudicate(args: argparse.Namespace) -> int:
    form = _load_json(args.form)
    responses = {}
    for path in args.responses:
        data = _load_json(path)
        reviewer = data.get("reviewer")
        if not reviewer:
            print(f"{path}: missing reviewer identity", file=sys.stderr)
            return 2
        responses[reviewer] = data.get("labels", {})
    adjudications = _load_json(args.adjudications) if args.adjudications else None
    result = diagnosis.adjudicate(form, responses, adjudications)
    _write_json(args.out, result)
    precision = result["precision"]
    print(f"wrote {args.out}: {result['useful']}/{result['evaluated']} useful "
          f"(precision {precision:.4f})" if precision is not None else
          f"wrote {args.out}: no evaluated items")
    print(f"disagreements kept: {len(result['disagreements'])}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version",
                        version=f"inkflip-evaluation-protocol {PROTOCOL_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    emit = sub.add_parser("emit-corpus", help="freeze fixture entries into a corpus manifest")
    emit.add_argument("--split", required=True, choices=sorted(manifest.FIXTURE_SPLIT_MAP))
    emit.add_argument("--out", type=Path, required=True)
    emit.add_argument("--check", action="store_true",
                      help="verify --out still matches fixtures/manifest.json")
    emit.set_defaults(func=cmd_emit_corpus)

    splits = sub.add_parser("verify-splits", help="audit manifests for sibling leakage")
    splits.add_argument("manifests", type=Path, nargs="+")
    splits.set_defaults(func=cmd_verify_splits)

    status = sub.add_parser("status", help="target verdicts without a run (all UNMET)")
    status.add_argument("--plan", type=Path, required=True)
    status.add_argument("--out", type=Path)
    status.set_defaults(func=cmd_status)

    evaluate = sub.add_parser("evaluate", help="score a bound inspection run")
    evaluate.add_argument("--plan", type=Path, required=True)
    evaluate.add_argument("--corpus", type=Path, required=True)
    evaluate.add_argument("--run", type=Path, required=True)
    evaluate.add_argument("--label-root", type=Path,
                          help="custodian label root outside the repository "
                               "(or INKFLIP_EVAL_LABEL_ROOT)")
    evaluate.add_argument("--labels", type=Path,
                          help="ungated label file for development/public_demo splits")
    evaluate.add_argument("--adjudication", type=Path,
                          help="adjudication artifact for useful-finding precision")
    evaluate.add_argument("--out", type=Path)
    evaluate.set_defaults(func=cmd_evaluate)

    form = sub.add_parser("review-form", help="emit a blinded reviewer labeling form")
    form.add_argument("--run", type=Path, required=True)
    form.add_argument("--sample", type=int)
    form.add_argument("--seed", type=int, default=diagnosis.DEFAULT_SEED)
    form.add_argument("--form-id", default="useful-review")
    form.add_argument("--out", type=Path, required=True)
    form.set_defaults(func=cmd_review_form)

    adj = sub.add_parser("adjudicate", help="combine reviewer labels")
    adj.add_argument("--form", type=Path, required=True)
    adj.add_argument("--responses", type=Path, nargs="+", required=True)
    adj.add_argument("--adjudications", type=Path)
    adj.add_argument("--out", type=Path, required=True)
    adj.set_defaults(func=cmd_adjudicate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (custody.CustodyError, manifest.ManifestError, report.RunError,
            lineage.LeakageError, ValueError, KeyError, OSError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
