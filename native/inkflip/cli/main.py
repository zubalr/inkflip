"""Inkflip native CLI (T30–T34 wiring)."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from inkflip.cli.html import render_html_report
from inkflip.cli.inspect import (
    ALLOWLISTED_READERS,
    InspectError,
    inspect_document,
    write_report,
)
from inkflip.cli.models_cmd import (
    ModelPrepareError,
    ModelUnavailableError,
    prepare_models,
)
from inkflip.cli.paths import directories_overlap, paths_alias, refuse_output_alias, resolved_path
from inkflip.contracts import core
from inkflip.readers import pdfium, pypdf as pypdf_reader, tesseract
from inkflip.runtime.artifacts import atomic_write_bytes

EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_PARTIAL_RUN = 3
EXIT_READ_FAILURE = 4
EXIT_POLICY_FAILURE = 5
EXIT_INCOMPARABLE = 6
EXIT_CANCELLED = 130


class CliError(Exception):
    exit_code = EXIT_INVALID_ARGS

    def __init__(self, message: str, exit_code: int | None = None):
        super().__init__(message)
        self.message = message
        if exit_code is not None:
            self.exit_code = exit_code


class ArgumentError(CliError):
    exit_code = EXIT_INVALID_ARGS


def _guard_output_file(source: Path, destination: Path, replace: bool) -> None:
    try:
        refuse_output_alias(source, destination)
    except ValueError as exc:
        raise ArgumentError(str(exc)) from exc
    if destination.exists() and not replace:
        raise ArgumentError(
            f"Refusing overwrite of existing file {destination}; use --replace-output to allow"
        )


def _write_output(path: Path, write) -> None:
    """Run an output write, translating I/O faults into the CLI contract.

    An unwritable destination is a runtime failure (exit 4) reported as an
    actionable error, never an untranslated traceback.
    """
    try:
        write()
    except OSError as exc:
        raise CliError(f"Cannot write output {path}: {exc}", EXIT_READ_FAILURE) from exc


def _load_validated(path: Path) -> dict:
    if not path.is_file():
        raise CliError(f"File not found: {path}", EXIT_READ_FAILURE)
    try:
        raw = path.read_bytes()
        data = core.loads_strict(raw)
        core.validate(data)
        return data
    except core.ContractError as exc:
        raise ArgumentError(f"Contract validation failed: {exc}") from exc
    except OSError as exc:
        raise CliError(f"Cannot read {path}: {exc}", EXIT_READ_FAILURE) from exc


def cmd_readers_list(_args: argparse.Namespace) -> int:
    output = {
        "readers": [
            pdfium.describe(),
            pypdf_reader.describe(),
            tesseract.describe(),
        ]
    }
    print(json.dumps(output, indent=2))
    return EXIT_OK


def cmd_inspect(args: argparse.Namespace) -> int:
    source_str = args.file
    if source_str.startswith("http://") or source_str.startswith("https://"):
        raise ArgumentError("Remote URL sources are not permitted; local file paths only")
    source_path = resolved_path(Path(source_str))
    out_path = resolved_path(Path(args.out))
    _guard_output_file(source_path, out_path, bool(args.replace_output))
    readers = [item.strip().lower() for item in (args.reader or ["pdfium"])]
    try:
        report, code = inspect_document(
            source_path=source_path,
            readers=readers,
            pages_spec=args.pages or "1",
            ocr_pages_spec=args.ocr_pages,
            region_spec=args.region,
            profile_id=args.profile or "native-default",
            embed_source=bool(getattr(args, "embed_source", False)),
        )
        _write_output(out_path, lambda: write_report(out_path, report))
    except InspectError as exc:
        raise CliError(exc.message, exc.exit_code) from exc
    print(f"Report written to {out_path}")
    return code


def cmd_validate(args: argparse.Namespace) -> int:
    data = _load_validated(resolved_path(Path(args.report)))
    document = data.get("document", {})
    occs = data.get("occurrences", [])
    print(
        f"VALID: report_id={data.get('report_id')}, pages={document.get('page_count')}, "
        f"occurrences={len(occs)}"
    )
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    report_path = resolved_path(Path(args.report))
    out_path = resolved_path(Path(args.out))
    _guard_output_file(report_path, out_path, bool(args.replace_output))
    if args.format != "html":
        raise ArgumentError(f"Unsupported report export format {args.format!r}; only 'html' is supported")
    data = _load_validated(report_path)
    html_content = render_html_report(data)
    _write_output(out_path, lambda: atomic_write_bytes(out_path, html_content.encode("utf-8")))
    print(f"HTML report written to {out_path}")
    return EXIT_OK


def _recorded_profile(report: dict) -> tuple[str | None, str | None, dict[str, str]]:
    environment = report.get("execution", {}).get("environment") or ""
    name = None
    sha = None
    versions: dict[str, str] = {}
    for part in environment.split(";"):
        item = part.strip()
        if item.startswith("profile_name="):
            name = item.split("=", 1)[1]
        elif item.startswith("profile_sha256="):
            sha = item.split("=", 1)[1]
        elif item.startswith("reader_version="):
            versions["profile"] = item.split("=", 1)[1]
    for reader in report.get("readers", []):
        versions[reader.get("id", "")] = reader.get("version", "")
        versions[reader.get("name", "").lower()] = reader.get("version", "")
    return name, sha, versions


def _reconstruct_plan(report: dict) -> tuple[str, str | None, str | None]:
    selected = [str(index + 1) for index in report.get("plan", {}).get("selected_pages", [])]
    pages_spec = ",".join(selected) if selected else "1"
    ocr_pages = [
        str(check["page_index"] + 1)
        for check in report.get("plan", {}).get("checks", [])
        if check.get("capability") == "ocr"
    ]
    ocr_spec = ",".join(ocr_pages) if ocr_pages else None
    region_spec = None
    regions = report.get("plan", {}).get("regions") or []
    if regions:
        polygon = (regions[0].get("geometry") or {}).get("polygon") or []
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        if xs and ys:
            region_spec = f"{min(xs)},{min(ys)},{max(xs)},{max(ys)}"
    return pages_spec, ocr_spec, region_spec


def cmd_replay(args: argparse.Namespace) -> int:
    report_path = resolved_path(Path(args.report))
    out_path = resolved_path(Path(args.out))
    _guard_output_file(report_path, out_path, bool(args.replace_output))
    orig = _load_validated(report_path)
    if orig.get("kind") != "report":
        raise ArgumentError("Replay requires a validated report")
    recorded_name, recorded_sha, versions = _recorded_profile(orig)
    if recorded_name and args.profile != recorded_name and args.profile not in {"native-default", "native"}:
        raise ArgumentError(
            f"Replay refused: profile mismatch (recorded {recorded_name}, requested {args.profile})"
        )
    if recorded_name and recorded_name not in {"native-default", "native", "desktop", "mobile"}:
        if args.profile != recorded_name:
            raise ArgumentError(
                f"Replay refused: profile mismatch (recorded {recorded_name}, requested {args.profile})"
            )
    expected_sha = orig["document"]["sha256"]
    tmp_source = None
    try:
        if args.source:
            source_path = resolved_path(Path(args.source))
            if paths_alias(source_path, out_path):
                raise ArgumentError(
                    "Replay output aliases the source PDF and is refused regardless of overwrite flags"
                )
            if not source_path.is_file():
                raise CliError(f"Specified source file not found: {source_path}", EXIT_READ_FAILURE)
        else:
            source_asset_id = orig["document"].get("source_asset_id")
            matching = next((a for a in orig.get("assets", []) if a.get("id") == source_asset_id), None)
            if not source_asset_id or not matching or not matching.get("data_base64"):
                raise ArgumentError(
                    "Original report does not embed source PDF and no --source was provided"
                )
            source_bytes = __import__("base64").b64decode(matching["data_base64"])
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(source_bytes)
            tmp.close()
            tmp_source = Path(tmp.name)
            source_path = tmp_source
        pages_spec, ocr_spec, region_spec = _reconstruct_plan(orig)
        orig_readers = []
        for reader in orig.get("readers", []):
            name = reader.get("name", "").lower()
            if name in ALLOWLISTED_READERS:
                orig_readers.append(name)
            elif reader.get("id", "").startswith("pdfium"):
                orig_readers.append("pdfium")
            elif reader.get("id", "").startswith("pypdf"):
                orig_readers.append("pypdf")
            elif reader.get("id", "").startswith("tesseract"):
                orig_readers.append("tesseract")
        try:
            report, code = inspect_document(
                source_path=source_path,
                readers=orig_readers or ["pdfium"],
                pages_spec=pages_spec,
                ocr_pages_spec=ocr_spec,
                region_spec=region_spec,
                profile_id=args.profile,
                embed_source=bool(orig["document"].get("source_asset_id")),
                origin_report_id=orig["report_id"],
                expected_sha256=expected_sha,
                required_reader_versions=versions,
            )
        except InspectError as exc:
            raise CliError(exc.message, exc.exit_code) from exc
        try:
            _write_output(out_path, lambda: write_report(out_path, report))
        except InspectError as exc:
            raise CliError(exc.message, exc.exit_code) from exc
        print(f"Replay report written to {out_path}")
        return code
    finally:
        if tmp_source and tmp_source.exists():
            try:
                tmp_source.unlink()
            except OSError:
                pass


def cmd_compare_readers(args: argparse.Namespace) -> int:
    source_path = resolved_path(Path(args.file))
    out_dir = resolved_path(Path(args.out))
    if str(args.file).startswith(("http://", "https://")):
        raise ArgumentError("Remote URL sources are not permitted; local file paths only")
    if not source_path.is_file():
        raise CliError(f"Source file not found: {source_path}", EXIT_READ_FAILURE)
    if directories_overlap(source_path.parent, out_dir):
        raise ArgumentError("Output directory must not overlap the source directory")
    readers = [item.strip().lower() for item in args.readers.split(",")]
    if len(readers) != 2:
        raise ArgumentError(
            f"--readers must declare exactly two comma-separated reader IDs, got {len(readers)}"
        )
    for reader in readers:
        if reader not in ALLOWLISTED_READERS:
            raise ArgumentError(
                f"Unknown reader {reader!r}; allowlisted readers: {', '.join(sorted(ALLOWLISTED_READERS))}"
            )
    if out_dir.exists() and any(out_dir.iterdir()) and not args.replace_output:
        raise ArgumentError(f"Refusing to write into non-empty directory {out_dir}")
    _write_output(out_dir, lambda: out_dir.mkdir(parents=True, exist_ok=True))
    reports = []
    exit_code = EXIT_OK
    for reader in readers:
        try:
            report, code = inspect_document(
                source_path,
                [reader],
                args.pages or "1",
                args.ocr_pages,
                None,
                "native-default",
            )
        except InspectError as exc:
            raise CliError(exc.message, exc.exit_code) from exc
        path = out_dir / f"report_{reader}.inkflip.json"
        try:
            _write_output(path, lambda p=path, r=report: write_report(p, r))
        except InspectError as exc:
            raise CliError(exc.message, exc.exit_code) from exc
        reports.append(report)
        if code != EXIT_OK:
            exit_code = code
    from inkflip.baselines.engine import write_pair_comparison
    from inkflip.baselines.models import BaselineError

    try:
        comparison_code = write_pair_comparison(
            reports[0],
            reports[1],
            out_dir=out_dir,
            mode="reader",
            rules=None,
        )
    except BaselineError as exc:
        raise ArgumentError(str(exc)) from exc
    print(f"Comparison written to {out_dir}")
    return comparison_code if comparison_code != EXIT_OK else exit_code


def cmd_models_prepare(args: argparse.Namespace) -> int:
    manifest_path = resolved_path(Path(args.manifest))
    cache_dir = resolved_path(Path(args.cache or (Path.cwd() / "model-cache")))
    try:
        record = prepare_models(manifest_path, cache_dir)
    except ModelPrepareError as exc:
        raise ArgumentError(str(exc)) from exc
    except ModelUnavailableError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        print("Models remain unavailable until allowlisted bytes verify.")
        return EXIT_PARTIAL_RUN
    print(json.dumps(record, indent=2))
    print("Models manifest verified; local model cache ready.")
    return EXIT_OK


def cmd_corpus_run(args: argparse.Namespace) -> int:
    from inkflip.corpus.manifest import CorpusError
    from inkflip.corpus.runner import run_corpus

    try:
        result = run_corpus(
            manifest_path=args.manifest,
            source_root=args.source_root,
            profile=args.profile,
            out_dir=args.out,
            jobs=args.jobs,
            resume=args.resume,
        )
    except CorpusError as exc:
        raise ArgumentError(str(exc)) from exc
    if result.status == "complete":
        return EXIT_OK
    if result.status == "partial":
        return EXIT_PARTIAL_RUN
    if result.status == "cancelled":
        return EXIT_CANCELLED
    return EXIT_READ_FAILURE


def cmd_baseline_create(args: argparse.Namespace) -> int:
    from inkflip.baselines.engine import create_baseline
    from inkflip.baselines.models import BaselineError, BaselineOverwriteError

    try:
        create_baseline(
            run_dir=Path(args.run),
            rules_path=Path(args.rules) if args.rules else None,
            out_path=Path(args.out),
            approved_by=args.approved_by,
            rationale=args.rationale,
        )
    except BaselineOverwriteError as exc:
        raise ArgumentError(str(exc)) from exc
    except BaselineError as exc:
        raise ArgumentError(str(exc)) from exc
    print(f"Baseline successfully created at: {args.out}")
    return EXIT_OK


def cmd_compare(args: argparse.Namespace) -> int:
    from inkflip.baselines.engine import compare

    result = compare(
        left_path=Path(args.left),
        right_path=Path(args.right),
        rules_path=Path(args.rules) if args.rules else None,
        out_dir=Path(args.out) if args.out else None,
        fail_on_changed=bool(getattr(args, "fail_on", None) == "changed"),
        mode=args.mode or "reader_upgrade",
    )
    for violation in result.violations[:5]:
        sys.stderr.write(f"Error: {violation}\n")
    print(f"Comparison status: {result.status}")
    return result.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inkflip",
        description="Inkflip local-first PDF reading inspector CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_readers = subparsers.add_parser("readers")
    readers_sub = p_readers.add_subparsers(dest="subcommand", required=True)
    p_list = readers_sub.add_parser("list")
    p_list.add_argument("--json", action="store_true", default=True)

    p_inspect = subparsers.add_parser("inspect")
    p_inspect.add_argument("file")
    p_inspect.add_argument("--out", required=True)
    p_inspect.add_argument("--reader", action="append")
    p_inspect.add_argument("--pages", default="1")
    p_inspect.add_argument("--ocr-pages")
    p_inspect.add_argument("--region")
    p_inspect.add_argument("--profile", default="native-default")
    p_inspect.add_argument("--replace-output", action="store_true")
    p_inspect.add_argument("--embed-source", action="store_true")

    p_validate = subparsers.add_parser("validate")
    p_validate.add_argument("report")

    p_report = subparsers.add_parser("report")
    p_report.add_argument("report")
    p_report.add_argument("--format", required=True, choices=["html"])
    p_report.add_argument("--out", required=True)
    p_report.add_argument("--replace-output", action="store_true")

    p_replay = subparsers.add_parser("replay")
    p_replay.add_argument("report")
    p_replay.add_argument("--source")
    p_replay.add_argument("--profile", required=True)
    p_replay.add_argument("--out", required=True)
    p_replay.add_argument("--replace-output", action="store_true")

    p_cr = subparsers.add_parser("compare-readers")
    p_cr.add_argument("file")
    p_cr.add_argument("--readers", required=True)
    p_cr.add_argument("--out", required=True)
    p_cr.add_argument("--pages", default="1")
    p_cr.add_argument("--ocr-pages")
    p_cr.add_argument("--replace-output", action="store_true")

    p_models = subparsers.add_parser("models")
    models_sub = p_models.add_subparsers(dest="subcommand", required=True)
    p_mp = models_sub.add_parser("prepare")
    p_mp.add_argument("--manifest", required=True)
    p_mp.add_argument("--cache")

    p_corpus = subparsers.add_parser("corpus")
    corpus_sub = p_corpus.add_subparsers(dest="subcommand", required=True)
    p_crun = corpus_sub.add_parser("run")
    p_crun.add_argument("--manifest", required=True)
    p_crun.add_argument("--source-root", required=True)
    p_crun.add_argument("--profile", required=True)
    p_crun.add_argument("--out", required=True)
    p_crun.add_argument("--jobs", type=int, default=1)
    p_crun.add_argument("--resume", action="store_true")

    p_baseline = subparsers.add_parser("baseline")
    baseline_sub = p_baseline.add_subparsers(dest="subcommand", required=True)
    p_bcreate = baseline_sub.add_parser("create")
    p_bcreate.add_argument("--run", required=True)
    p_bcreate.add_argument("--rules")
    p_bcreate.add_argument("--out", required=True)
    p_bcreate.add_argument("--approved-by", required=True)
    p_bcreate.add_argument("--rationale", required=True)

    p_compare = subparsers.add_parser("compare")
    p_compare.add_argument("left")
    p_compare.add_argument("right")
    p_compare.add_argument("--rules")
    p_compare.add_argument("--out")
    p_compare.add_argument("--mode", default="reader_upgrade")
    p_compare.add_argument("--fail-on", choices=["changed"])
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_INVALID_ARGS if exc.code not in (0, None) else EXIT_OK
    dispatch = {
        ("readers", "list"): cmd_readers_list,
        ("inspect", None): cmd_inspect,
        ("validate", None): cmd_validate,
        ("report", None): cmd_report,
        ("replay", None): cmd_replay,
        ("compare-readers", None): cmd_compare_readers,
        ("models", "prepare"): cmd_models_prepare,
        ("corpus", "run"): cmd_corpus_run,
        ("baseline", "create"): cmd_baseline_create,
        ("compare", None): cmd_compare,
    }
    try:
        sub = getattr(args, "subcommand", None)
        handler = dispatch.get((args.command, sub)) or dispatch.get((args.command, None))
        if handler is None:
            raise ArgumentError(f"Unknown command: {args.command}")
        return handler(args)
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted\n")
        return EXIT_CANCELLED
    except CliError as exc:
        sys.stderr.write(f"Error: {exc.message}\n")
        return exc.exit_code
    except Exception as exc:
        sys.stderr.write(f"Unexpected error: {exc}\n")
        return EXIT_READ_FAILURE


if __name__ == "__main__":
    sys.exit(main())
