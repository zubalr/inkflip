"""Validation for explicit coordinator-owned follow-up grants in Beads."""
from __future__ import annotations

from pathlib import PurePosixPath
import re


def execution_grant(issue_id: str, issue: dict) -> dict:
    if not isinstance(issue, dict):
        raise ValueError(f"{issue_id}: malformed issue record")
    metadata = issue.get("metadata")
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValueError(f"{issue_id}: malformed metadata")
    if "execution" not in metadata:
        return {}
    grant = metadata["execution"]
    if not isinstance(grant, dict) or not isinstance(grant.get("app"), str) or not grant["app"]:
        raise ValueError(f"{issue_id}: malformed execution grant")
    return grant


def validate_id(issue_id: str) -> None:
    if (not re.fullmatch(r"pdf-[a-z0-9][a-z0-9-]{0,63}", issue_id)
            or re.fullmatch(r"pdf-(?:t[0-9]+|pass[0-9]+)", issue_id)):
        raise ValueError("Follow-up requires a non-product pdf issue ID")


def validate_scope(issue_id: str, grant: dict) -> list[str]:
    scopes = grant.get("allowed_scope")
    if not isinstance(scopes, list) or not scopes:
        raise ValueError(f"{issue_id}: follow-up requires explicit allowed_scope")
    for scope in scopes:
        if not isinstance(scope, str) or not scope:
            raise ValueError(f"{issue_id}: invalid follow-up scope")
        path = PurePosixPath(scope)
        if (path.is_absolute() or not path.parts or ".." in path.parts
                or str(path) != scope.rstrip("/")
                or any(char in scope for char in "*?[]\\\n\r\x00")
                or path.parts[0] in {".git", ".beads", "planning"}):
            raise ValueError(f"{issue_id}: unsafe follow-up scope {scope!r}")
    mode = grant.get("mode")
    if mode not in {"audit", "implementation"}:
        raise ValueError(f"{issue_id}: follow-up mode must be audit or implementation")
    output = f"artifacts/followups/{issue_id}"
    if mode == "audit" and any(s.rstrip("/") != output and not s.startswith(output + "/") for s in scopes):
        raise ValueError(f"{issue_id}: audit writes are confined to its evidence directory")
    return scopes


def validate_grant(issue_id: str, grant: dict, config: dict) -> None:
    validate_id(issue_id)
    if not isinstance(grant, dict) or grant.get("kind") != "followup":
        raise ValueError(f"{issue_id}: requires an explicit follow-up grant")
    app = grant.get("app")
    if app not in config["apps"]:
        raise ValueError(f"{issue_id}: unknown native app")
    if grant.get("branch") != config["apps"][app]["branch_prefix"] + issue_id:
        raise ValueError(f"{issue_id}: unsafe or mismatched assigned branch")
    if not re.fullmatch(r"[0-9a-f]{40}", str(grant.get("base", ""))):
        raise ValueError(f"{issue_id}: grant requires an exact full base commit")
    if type(grant.get("pass")) is not int or grant["pass"] not in {s["id"] for s in config["passes"]}:
        raise ValueError(f"{issue_id}: invalid follow-up pass")
    if not isinstance(grant.get("instructions"), str) or not grant["instructions"].strip():
        raise ValueError(f"{issue_id}: follow-up requires concrete instructions")
    validate_scope(issue_id, grant)
