"""Notice-verification boundary tests for --docker production-image checks
(release-candidate-repairs batch, outcome 3).

Each test drives verify_production_image against a stub docker whose outputs
are fully controlled. Required notice entries with absent/empty hashes or
paths, wrong digests, duplicate ids, or traversal paths must fail the check —
and traversal paths must never reach a container command.

The INDEX root itself is untrusted: a list/string/integer/null root, or a
non-list `entries` value, must surface as a named failure rather than an
exception. Required notices must also carry a declared byte count that is a
non-negative integer (never a boolean) and that agrees with the file the
container reports — the size query is argv-form, like the hashing, so notice
metadata can never be interpreted by a shell.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "cd", REPO_ROOT / "scripts" / "check_distribution.py")
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)

IMAGE = {
    "image_ref": "stub:img",
    "expected_image_digest": "sha256:" + "1" * 64,
    "architecture": "amd64",
    "os": "linux",
    "expected_wheel_sha256": "a" * 64,
    "expected_model_sha256": "b" * 64,
    "expected_tesseract_version": "5.5.0",
    "required_notice_ids": ["inkflip-mit", "tesseract-apache"],
}
WHEEL_SHA = "a" * 64
MODEL_SHA = "b" * 64
MIT_TEXT = b"MIT text"
TESS_TEXT = b"tesseract apache"
MIT_SHA = hashlib.sha256(MIT_TEXT).hexdigest()
TESS_SHA = hashlib.sha256(TESS_TEXT).hexdigest()

HEALTHY_INDEX = {"entries": [
    {"id": "inkflip-mit", "path": "notices/inkflip-MIT.txt",
     "sha256": MIT_SHA, "bytes": len(MIT_TEXT)},
    {"id": "tesseract-apache", "path": "notices/tesseract.txt",
     "sha256": TESS_SHA, "bytes": len(TESS_TEXT)},
]}
HEALTHY_HASHES = {
    # the checker passes the literal glob from its fixed command string
    "/app/wheels/inkflip-*.whl": WHEEL_SHA,
    "/app/models/tessdata/eng.traineddata": MODEL_SHA,
    "/app/notices/inkflip-MIT.txt": MIT_SHA,
    "/app/notices/tesseract.txt": TESS_SHA,
}
HEALTHY_SIZES = {
    "/app/notices/inkflip-MIT.txt": len(MIT_TEXT),
    "/app/notices/tesseract.txt": len(TESS_TEXT),
}


class _FakeResult:
    def __init__(self, returncode, stdout, stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class StubDocker:
    """Canned docker responses; every container invocation is recorded so
    tests can assert that untrusted INDEX data never reaches a command.

    `hashes` models the sha256sum output and `sizes` the argv-form size
    query (values are printed verbatim, so a non-numeric value models an
    unparsable size); both are keyed by basename and default to the healthy
    fixture. A missing key models an absent file in the image."""

    def __init__(self, index, hashes=None, sizes=None,
                 image_id=IMAGE["expected_image_digest"],
                 arch="amd64", tesseract="tesseract 5.5.0"):
        self.index = index
        self.image_id = image_id
        self.arch = arch
        # normalize keys to basenames: container commands reference files by
        # their in-image absolute path, and only the final segment matters.
        self.hashes = {}
        for key, value in (hashes if hashes is not None else HEALTHY_HASHES).items():
            self.hashes[key.rsplit("/", 1)[-1]] = value
        self.sizes = {}
        for key, value in (sizes if sizes is not None else HEALTHY_SIZES).items():
            self.sizes[key.rsplit("/", 1)[-1]] = value
        self.tesseract = tesseract
        self.container_args = []

    def entrypoint(self, argv):
        if "--entrypoint" in argv:
            return argv[argv.index("--entrypoint") + 1]
        return None

    def __call__(self, docker_cmd, argv):
        joined = " ".join(argv)
        if "inspect" in joined:
            return _FakeResult(0, f"{self.image_id}\n{self.arch}\nlinux\n")
        self.container_args.append(list(argv))
        if "INDEX.json" in joined:
            return _FakeResult(0, json.dumps(self.index))
        if self.entrypoint(argv) == "stat":
            base = argv[-1].rsplit("/", 1)[-1]
            if base in self.sizes:
                return _FakeResult(0, f"{self.sizes[base]}\n")
            return _FakeResult(1, f"stat: cannot stat {argv[-1]!r}: no such file")
        if "sha256sum" in joined:
            lines = []
            for word in joined.split():
                base = word.rsplit("/", 1)[-1]
                if base in self.hashes and self.hashes[base] is not None:
                    lines.append(f"{self.hashes[base]}  {base}")
            if "--version" in joined:
                lines.append(self.tesseract)
            if lines:
                return _FakeResult(0, "\n".join(lines) + "\n")
            return _FakeResult(1, "no such file")
        if "--version" in joined:
            return _FakeResult(0, self.tesseract + "\n")
        return _FakeResult(0, "")


def verify_with(stub):
    import subprocess
    orig = subprocess.run
    subprocess.run = lambda argv, **kw: stub("stub-docker", list(argv[1:]))
    try:
        return cd.verify_production_image(Path("/nonexistent"), dict(IMAGE), "stub-docker"), stub
    finally:
        subprocess.run = orig


class NoticeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.index = json.loads(json.dumps(HEALTHY_INDEX))

    def verify(self, **overrides):
        stub = StubDocker(self.index, **overrides)
        problems, stub = verify_with(stub)
        return problems, stub

    def test_healthy_notice_inventory_passes(self):
        problems, _ = self.verify()
        self.assertEqual(problems, [], msg=problems)

    def test_required_notice_with_null_sha_fails(self):
        self.index["entries"][0]["sha256"] = None
        problems, _ = self.verify()
        self.assertTrue(any("missing or malformed sha256" in p for p in problems),
                        msg=problems)

    def test_required_notice_with_empty_sha_fails(self):
        self.index["entries"][0]["sha256"] = ""
        problems, _ = self.verify()
        self.assertTrue(any("missing or malformed sha256" in p for p in problems),
                        msg=problems)

    def test_required_notice_with_empty_path_fails(self):
        self.index["entries"][0]["path"] = ""
        problems, _ = self.verify()
        self.assertTrue(any("has no path" in p for p in problems), msg=problems)

    def test_required_notice_absent_fails(self):
        self.index["entries"] = [self.index["entries"][1]]
        problems, _ = self.verify()
        self.assertTrue(any(
            "absent from image notice inventory: inkflip-mit" in p
            for p in problems), msg=problems)

    def test_duplicate_notice_ids_fail(self):
        self.index["entries"].append(dict(self.index["entries"][0]))
        problems, _ = self.verify()
        self.assertTrue(any("duplicate notice id" in p for p in problems), msg=problems)

    def test_notice_path_traversal_fails_and_never_reaches_container(self):
        self.index["entries"][0]["path"] = "notices/../../../etc/MIT.txt"
        problems, stub = self.verify()
        self.assertTrue(any("escapes the notices root" in p for p in problems),
                        msg=problems)
        for argv in stub.container_args:
            joined = " ".join(argv)
            self.assertNotIn("..", joined, msg=joined)

    def test_notice_wrong_bytes_fail(self):
        hashes = dict(HEALTHY_HASHES)
        hashes["/app/notices/inkflip-MIT.txt"] = "0" * 64  # tampered
        problems, _ = self.verify(hashes=hashes)
        self.assertTrue(any("bytes do not match INDEX" in p and "inkflip-mit" in p
                            for p in problems), msg=problems)

    # ---- declared byte counts (INDEX `bytes` vs the real file) ----

    def test_required_notice_without_bytes_fails(self):
        del self.index["entries"][0]["bytes"]
        problems, _ = self.verify()
        self.assertTrue(any("inkflip-mit" in p and "no 'bytes' count" in p
                            for p in problems), msg=problems)

    def test_required_notice_with_null_bytes_fails(self):
        self.index["entries"][0]["bytes"] = None
        problems, _ = self.verify()
        self.assertTrue(any("inkflip-mit" in p and "no 'bytes' count" in p
                            for p in problems), msg=problems)

    def test_required_notice_with_string_bytes_fails(self):
        self.index["entries"][0]["bytes"] = "eight"
        problems, _ = self.verify()
        self.assertTrue(any("inkflip-mit" in p and "non-integer 'bytes'" in p
                            for p in problems), msg=problems)

    def test_required_notice_with_float_bytes_fails(self):
        self.index["entries"][0]["bytes"] = 8.5
        problems, _ = self.verify()
        self.assertTrue(any("inkflip-mit" in p and "non-integer 'bytes'" in p
                            for p in problems), msg=problems)

    def test_required_notice_with_bool_bytes_fails(self):
        # isinstance(True, int) is True in Python: booleans must be excluded
        # explicitly, not accepted as the count 1.
        self.index["entries"][0]["bytes"] = True
        problems, _ = self.verify()
        self.assertTrue(any("inkflip-mit" in p and "boolean 'bytes'" in p
                            for p in problems), msg=problems)

    def test_required_notice_with_negative_bytes_fails(self):
        self.index["entries"][0]["bytes"] = -1
        problems, _ = self.verify()
        self.assertTrue(any("inkflip-mit" in p and "negative 'bytes'" in p
                            for p in problems), msg=problems)

    def test_required_notice_length_mismatch_fails(self):
        # the digest still matches: only the declared length is wrong
        self.index["entries"][0]["bytes"] = 999999
        problems, _ = self.verify()
        self.assertTrue(any("inkflip-mit" in p and "byte length mismatch" in p
                            and "999999" in p and str(len(MIT_TEXT)) in p
                            for p in problems), msg=problems)

    def test_required_notice_zero_length_mismatch_fails(self):
        self.index["entries"][0]["bytes"] = 0
        problems, _ = self.verify()
        self.assertTrue(any("inkflip-mit" in p and "byte length mismatch" in p
                            for p in problems), msg=problems)

    def test_unreadable_notice_size_fails(self):
        sizes = dict(HEALTHY_SIZES)
        del sizes["/app/notices/inkflip-MIT.txt"]  # stat reports no such file
        problems, _ = self.verify(sizes=sizes)
        self.assertTrue(any("inkflip-mit" in p and "size unreadable" in p
                            for p in problems), msg=problems)

    def test_unparsable_notice_size_fails(self):
        sizes = dict(HEALTHY_SIZES)
        sizes["/app/notices/inkflip-MIT.txt"] = "eight"
        problems, _ = self.verify(sizes=sizes)
        self.assertTrue(any("inkflip-mit" in p and "size unreadable" in p
                            for p in problems), msg=problems)

    def test_notice_path_stays_an_argv_element_and_out_of_shell_text(self):
        hostile = "notices/inkflip-MIT.txt; touch /tmp/inkflip-pwned"
        self.index["entries"][0]["path"] = hostile
        _, stub = self.verify()
        in_image = "/app/" + hostile
        # the size/hash reads carry the path as a discrete argv element ...
        self.assertTrue(any(argv[-1] == in_image for argv in stub.container_args),
                        msg=stub.container_args)
        # ... and the fixed shell command never interpolates it
        for argv in stub.container_args:
            if "sh" in argv:
                self.assertNotIn("touch", argv[-1], msg=argv)
                self.assertNotIn(hostile, argv[-1], msg=argv)


class NoticeIndexShapeTests(unittest.TestCase):
    """A malformed INDEX root or `entries` value is a named failure, never an
    escaping AttributeError (json.loads of []/"x"/7/null returns a non-dict)."""

    def verify_root(self, root_value, **overrides):
        stub = StubDocker(root_value, **overrides)
        problems, stub = verify_with(stub)
        return problems, stub

    def assert_root_failure(self, root_value):
        problems, _ = self.verify_root(root_value)
        self.assertTrue(any("root must be a JSON object" in p for p in problems),
                        msg=problems)
        self.assertTrue(any("required notice id absent" in p for p in problems),
                        msg=problems)

    def test_list_root_fails_structurally(self):
        self.assert_root_failure([])

    def test_string_root_fails_structurally(self):
        self.assert_root_failure("x")

    def test_integer_root_fails_structurally(self):
        self.assert_root_failure(7)

    def test_null_root_fails_structurally(self):
        self.assert_root_failure(None)

    def test_entries_missing_fails(self):
        problems, _ = self.verify_root({})
        self.assertTrue(any("'entries' must be a list" in p for p in problems),
                        msg=problems)

    def test_entries_null_fails(self):
        problems, _ = self.verify_root({"entries": None})
        self.assertTrue(any("'entries' must be a list" in p for p in problems),
                        msg=problems)

    def test_entries_string_fails(self):
        problems, _ = self.verify_root({"entries": "x"})
        self.assertTrue(any("'entries' must be a list" in p for p in problems),
                        msg=problems)

    def test_non_dict_entries_fail(self):
        problems, _ = self.verify_root({"entries": [1, 2]})
        self.assertTrue(any("malformed entry" in p for p in problems), msg=problems)


class WheelModelTesseractTests(unittest.TestCase):
    def setUp(self):
        self.index = json.loads(json.dumps(HEALTHY_INDEX))

    def verify(self, hashes=None, image_id=IMAGE["expected_image_digest"],
               arch="amd64", tesseract="tesseract 5.5.0"):
        hashes = dict(HEALTHY_HASHES) if hashes is None else dict(hashes)
        stub = StubDocker(self.index, hashes=hashes, image_id=image_id,
                          arch=arch, tesseract=tesseract)
        problems, stub = verify_with(stub)
        return problems, stub

    def test_missing_wheel_hash_fails(self):
        hashes = dict(HEALTHY_HASHES)
        del hashes["/app/wheels/inkflip-*.whl"]
        problems, _ = self.verify(hashes=hashes)
        self.assertTrue(any("application wheel digest mismatch" in p for p in problems),
                        msg=problems)

    def test_model_digest_mismatch_fails(self):
        hashes = dict(HEALTHY_HASHES)
        hashes["/app/models/tessdata/eng.traineddata"] = "0" * 64
        problems, _ = self.verify(hashes=hashes)
        self.assertTrue(any("model digest mismatch" in p for p in problems), msg=problems)

    def test_wrong_image_identity_fails(self):
        problems, _ = self.verify(image_id="sha256:" + "9" * 64)
        self.assertTrue(any("identity mismatch" in p for p in problems), msg=problems)

    def test_wrong_architecture_fails(self):
        problems, _ = self.verify(arch="arm64")
        self.assertTrue(any("architecture is 'arm64'" in p for p in problems), msg=problems)

    def test_tesseract_version_mismatch_fails(self):
        problems, _ = self.verify(tesseract="tesseract 5.3.0")
        self.assertTrue(any("tesseract version line missing/mismatched" in p
                            for p in problems), msg=problems)

    def test_tesseract_extra_leading_zero_version_fails(self):
        # a substring test accepted 5.5.00 for a declared 5.5.0; the printed
        # version token must match exactly
        problems, _ = self.verify(tesseract="tesseract 5.5.00")
        self.assertTrue(any("tesseract version line missing/mismatched" in p
                            for p in problems), msg=problems)

    def test_tesseract_missing_version_line_fails(self):
        problems, _ = self.verify(tesseract="")
        self.assertTrue(any("tesseract version line missing/mismatched" in p
                            for p in problems), msg=problems)

    def test_tesseract_version_line_with_leptonica_suffix_passes(self):
        # tesseract --version prints the version line, then leptonica-...
        problems, _ = self.verify(
            tesseract="tesseract 5.5.0\nleptonica-1.85.0 (Sep 12 2026)")
        self.assertEqual(problems, [], msg=problems)


if __name__ == "__main__":
    unittest.main()
