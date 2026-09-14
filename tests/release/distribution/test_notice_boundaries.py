"""Notice-verification boundary tests for --docker production-image checks
(release-candidate-repairs batch, outcome 3).

Each test drives verify_production_image against a stub docker whose outputs
are fully controlled. Required notice entries with absent/empty hashes or
paths, wrong digests, duplicate ids, or traversal paths must fail the check —
and traversal paths must never reach a container command.
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
MIT_SHA = hashlib.sha256(b"MIT text").hexdigest()
TESS_SHA = hashlib.sha256(b"tesseract apache").hexdigest()

HEALTHY_INDEX = {"entries": [
    {"id": "inkflip-mit", "path": "notices/inkflip-MIT.txt",
     "sha256": MIT_SHA, "bytes": 8},
    {"id": "tesseract-apache", "path": "notices/tesseract.txt",
     "sha256": TESS_SHA, "bytes": 16},
]}
HEALTHY_HASHES = {
    # the checker passes the literal glob from its fixed command string
    "/app/wheels/inkflip-*.whl": WHEEL_SHA,
    "/app/models/tessdata/eng.traineddata": MODEL_SHA,
    "/app/notices/inkflip-MIT.txt": MIT_SHA,
    "/app/notices/tesseract.txt": TESS_SHA,
}


class _FakeResult:
    def __init__(self, returncode, stdout, stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class StubDocker:
    """Canned docker responses; every container invocation is recorded so
    tests can assert that untrusted INDEX data never reaches a command."""

    def __init__(self, index, hashes=None, image_id=IMAGE["expected_image_digest"],
                 arch="amd64", tesseract="tesseract 5.5.0"):
        self.index = index
        self.image_id = image_id
        self.arch = arch
        # normalize keys to basenames: container commands reference files by
        # their in-image absolute path, and only the final segment matters.
        self.hashes = {}
        for key, value in (hashes if hashes is not None else HEALTHY_HASHES).items():
            self.hashes[key.rsplit("/", 1)[-1]] = value
        self.tesseract = tesseract
        self.container_args = []

    def __call__(self, docker_cmd, argv):
        joined = " ".join(argv)
        if "inspect" in joined:
            return _FakeResult(0, f"{self.image_id}\n{self.arch}\nlinux\n")
        self.container_args.append(list(argv))
        if "INDEX.json" in joined:
            return _FakeResult(0, json.dumps(self.index))
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


if __name__ == "__main__":
    unittest.main()
