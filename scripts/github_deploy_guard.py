#!/usr/bin/env python3
"""Decide whether deploy-web may continue building or promote production.

The workflow must call this script. Searching YAML for concurrency is not
enough: a late successful verify of an older main SHA, or a pull_request
verify, must not publish. Cancellation of a GitHub job also does not retract
a Vercel alias that was already accepted.

Exit 0 with CONTINUE or SKIP on stdout. Exit 2 with REJECT when the source
event must never publish. A missing candidate at promote time is REJECT so
a failed deploy cannot be aliased.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

CONTINUE = "CONTINUE"
SKIP = "SKIP"
REJECT = "REJECT"
BEFORE_WORK = "before_work"
BEFORE_PROMOTE = "before_promote"
ALLOWED_EVENTS = {"push"}
REQUIRED_BRANCH = "main"
REQUIRED_CONCLUSION = "success"
CANDIDATE_URL_RE = re.compile(r"https://[a-zA-Z0-9._-]+\.vercel\.app")
CANDIDATE_ID_RE = re.compile(r"dpl_[A-Za-z0-9]+")
PRODUCTION_ALIAS_HOSTS = frozenset(
    {
        "inkflip-jubairjashim1975gmailcoms-projects.vercel.app",
        "inkflip-rose.vercel.app",
        "inkflip.vercel.app",
    }
)


def _looks_like_candidate(value: str) -> bool:
    text = value.strip()
    if CANDIDATE_ID_RE.fullmatch(text):
        return True
    if not CANDIDATE_URL_RE.fullmatch(text):
        return False
    host = text.removeprefix("https://")
    return host not in PRODUCTION_ALIAS_HOSTS


def extract_candidate_url(log_text: str) -> str | None:
    """Pick the unique Vercel deployment URL out of noisy CLI output.

    `vercel deploy --skip-domain` prints the candidate host, the production
    alias, progress glued onto the URL (`…vercel.appBuilding…`), and a later
    `vercel curl <url> --scope …` hint. Promote must receive only the
    candidate URL.
    """
    cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", log_text)
    found: list[str] = []
    for url in CANDIDATE_URL_RE.findall(cleaned):
        host = url.removeprefix("https://")
        if host in PRODUCTION_ALIAS_HOSTS:
            continue
        found.append(url)
    if not found:
        return None
    return found[-1]


def decide(
    *,
    trigger_event: str,
    trigger_branch: str,
    trigger_conclusion: str,
    trigger_sha: str,
    current_main_sha: str,
    phase: str,
    candidate_id: str | None = None,
) -> str:
    if phase not in {BEFORE_WORK, BEFORE_PROMOTE}:
        return REJECT
    if trigger_event not in ALLOWED_EVENTS:
        return REJECT
    if trigger_branch != REQUIRED_BRANCH:
        return REJECT
    if trigger_conclusion != REQUIRED_CONCLUSION:
        return REJECT
    if not trigger_sha or not current_main_sha:
        return REJECT
    if trigger_sha != current_main_sha:
        return SKIP
    if phase == BEFORE_PROMOTE:
        if not candidate_id or not _looks_like_candidate(candidate_id):
            return REJECT
    return CONTINUE


def _write_github_output(decision: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"decision={decision}\n")


def _write_github_url(url: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"url={url}\n")


def _extract_from_log(path: str) -> int:
    url = extract_candidate_url(Path(path).read_text(encoding="utf-8", errors="replace"))
    if not url:
        print("REJECT", file=sys.stderr)
        return 2
    print(url)
    _write_github_url(url)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg == "--extract-candidate-from" or arg.startswith("--extract-candidate-from=") for arg in argv):
        extractor = argparse.ArgumentParser(description=__doc__)
        extractor.add_argument("--extract-candidate-from", required=True)
        extract_args = extractor.parse_args(argv)
        return _extract_from_log(extract_args.extract_candidate_from)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=(BEFORE_WORK, BEFORE_PROMOTE))
    parser.add_argument("--trigger-event", required=True)
    parser.add_argument("--trigger-branch", required=True)
    parser.add_argument("--trigger-conclusion", required=True)
    parser.add_argument("--trigger-sha", required=True)
    parser.add_argument("--current-main-sha", required=True)
    parser.add_argument("--candidate-id", default="")
    args = parser.parse_args(argv)
    decision = decide(
        trigger_event=args.trigger_event,
        trigger_branch=args.trigger_branch,
        trigger_conclusion=args.trigger_conclusion,
        trigger_sha=args.trigger_sha,
        current_main_sha=args.current_main_sha,
        phase=args.phase,
        candidate_id=args.candidate_id or None,
    )
    print(decision)
    _write_github_output(decision)
    return 0 if decision in {CONTINUE, SKIP} else 2


if __name__ == "__main__":
    sys.exit(main())
