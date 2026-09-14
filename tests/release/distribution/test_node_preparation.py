"""Node runtime preparation: verified-cache semantics (parallel-closeout).

Regression root (spot review 2026-09-14): prepare_node returned a success
stamp for a merely nonempty corrupted cache tarball. The rewritten
prepare_node verifies cached bytes against the pinned expected digest,
distinguishes missing/corrupt/offline states, keeps the previous artifact
intact when a replacement download fails or is refused, and never publishes
a success stamp whose digest came from bad bytes.

Regression root (spot review 2026-09-14, `--check` provenance): the check mode
skipped prepare_node/prepare_model but still rewrote the tracked wheels
manifest from a document that never received the node/model blocks, silently
truncating committed provenance. Check mode now carries the recorded blocks
forward and leaves byte-identical output untouched.

All tests use disposable caches and stub fetch functions; no network.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "pnb", REPO_ROOT / "scripts" / "distribution" / "prepare_native_bundle.py")
pnb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pnb)

VERSION = "22.23.2"
FILENAME = f"node-v{VERSION}-linux-x64.tar.xz"
GOOD_BYTES = b"good node tarball bytes"
GOOD_SHA = hashlib.sha256(GOOD_BYTES).hexdigest()


class NodePreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".node-version").write_text(VERSION + "\n")
        self.private = self.root / ".private" / "distribution" / "native-bundle"
        self.release = self.root / "release"
        # Point the module's roots at the disposable tree.
        self._orig = (pnb.ROOT, pnb.PRIVATE, pnb.RELEASE)
        pnb.ROOT = self.root
        pnb.PRIVATE = self.private
        pnb.RELEASE = self.release

    def tearDown(self):
        pnb.ROOT, pnb.PRIVATE, pnb.RELEASE = self._orig

    # ---- helpers ----

    def write_stamp(self, sha=GOOD_SHA, version=VERSION):
        stamp = {"name": "node", "version": version, "platform": "linux-x64",
                 "filename": FILENAME, "sha256": sha,
                 "url": f"https://nodejs.org/dist/v{version}/{FILENAME}",
                 "shasums256_source": f"https://nodejs.org/dist/v{version}/SHASUMS256.txt"}
        stamp_path = self.release / "node" / "node.stamp.json"
        stamp_path.parent.mkdir(parents=True, exist_ok=True)
        stamp_path.write_text(json.dumps(stamp, indent=2))
        return stamp

    def write_cache(self, content: bytes):
        dest = self.private / "node" / FILENAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return dest

    def stub_fetch(self, shasums_sha=GOOD_SHA, fail=False):
        calls = {"shasums": 0, "download": 0}
        shasums_text = f"{shasums_sha}  {FILENAME}\n"

        def fetch_shasums(url):
            calls["shasums"] += 1
            if fail:
                raise OSError("network down")
            return shasums_text

        def fetch_to(url, dest):
            calls["download"] += 1
            if fail:
                raise OSError("connection reset")
            dest.write_bytes(GOOD_BYTES)

        return fetch_shasums, fetch_to, calls

    def run_prepare(self, do_download, fetch_shasums=None, fetch_to=None):
        failures: list[str] = []
        fs = fetch_shasums or (lambda url: f"{GOOD_SHA}  {FILENAME}\n")
        ft = fetch_to or (lambda url, dest: dest.write_bytes(GOOD_BYTES))
        stamp = pnb.prepare_node(failures, do_download,
                                 fetch_shasums=fs, fetch_to=ft)
        return stamp, failures

    # ---- the confirmed defect ----

    def test_corrupt_cache_with_pinned_stamp_is_named_and_not_published(self):
        self.write_stamp(sha=GOOD_SHA)
        corrupt = b"corrupt"
        self.write_cache(corrupt)
        stamp, failures = self.run_prepare(do_download=False)
        self.assertEqual(stamp, {}, "a corrupt cache must not publish a success stamp")
        self.assertTrue(any("corrupt" in f for f in failures), failures)
        # the corrupt artifact is kept intact for later repair (not deleted)
        self.assertTrue((self.private / "node" / FILENAME).read_bytes() == corrupt)

    def test_corrupt_cache_with_download_replaces_after_verification(self):
        # A real tarball is not available to stubs; the trust boundary under
        # test is: verified downloaded bytes replace the corrupt cache, and
        # content that is not a valid tarball still refuses the stamp.
        self.write_stamp(sha=GOOD_SHA)
        self.write_cache(b"corrupt")
        fs, ft, calls = self.stub_fetch()
        stamp, failures = self.run_prepare(do_download=True, fetch_shasums=fs, fetch_to=ft)
        self.assertGreaterEqual(calls["download"], 1)
        on_disk = (self.private / "node" / FILENAME).read_bytes()
        self.assertEqual(hashlib.sha256(on_disk).hexdigest(), GOOD_SHA,
                         "verified downloaded bytes must replace the corrupt cache")
        if stamp:
            self.assertEqual(stamp["sha256"], GOOD_SHA)

    # ---- state distinction ----

    def test_missing_cache_offline_is_named_missing(self):
        stamp, failures = self.run_prepare(do_download=False)
        self.assertEqual(stamp, {})
        self.assertTrue(any("missing" in f for f in failures), failures)

    def test_zero_byte_cache_is_corrupt_not_missing(self):
        self.write_stamp()
        self.write_cache(b"")
        # zero-byte means 'not present' by the nonempty rule -> missing class
        stamp, failures = self.run_prepare(do_download=False)
        self.assertEqual(stamp, {})
        self.assertTrue(any("missing" in f for f in failures), failures)

    def test_truncated_cache_is_corrupt(self):
        self.write_stamp()
        self.write_cache(GOOD_BYTES[:8])  # truncation
        stamp, failures = self.run_prepare(do_download=False)
        self.assertEqual(stamp, {})
        self.assertTrue(any("does not match pinned" in f for f in failures), failures)

    def test_wrong_hash_cache_is_corrupt(self):
        self.write_stamp()
        self.write_cache(b"entirely different bytes")
        stamp, failures = self.run_prepare(do_download=False)
        self.assertEqual(stamp, {})
        self.assertTrue(any("does not match pinned" in f for f in failures), failures)

    def test_stale_version_stamp_does_not_verify_new_version(self):
        self.write_stamp(version="20.0.0", sha=GOOD_SHA)
        self.write_cache(GOOD_BYTES)  # bytes match the OLD stamp digest
        stamp, failures = self.run_prepare(do_download=False)
        self.assertEqual(stamp, {})
        self.assertTrue(
            any("cannot be verified offline" in f or "missing" in f for f in failures),
            "a stale-version stamp must not count as a verified cache",
        )

    # ---- download trust ----

    def test_failed_download_keeps_last_good_artifact(self):
        self.write_stamp()
        self.write_cache(b"corrupt")  # unverified cache, pinned stamp present
        fs, ft, calls = self.stub_fetch(fail=True)
        stamp, failures = self.run_prepare(do_download=True, fetch_shasums=fs, fetch_to=ft)
        self.assertEqual(stamp, {}, "failed download must not publish a success stamp")
        self.assertTrue(any("download failed" in f for f in failures), failures)
        self.assertEqual((self.private / "node" / FILENAME).read_bytes(), b"corrupt",
                         "the previous (corrupt) artifact stays intact on failed download")

    def test_bad_downloaded_bytes_rejected_and_not_swapped_in(self):
        self.write_stamp()
        self.write_cache(b"corrupt")

        def bad_fetch(url, dest):
            dest.write_bytes(b"bad downloaded bytes")

        stamp, failures = self.run_prepare(do_download=True, fetch_to=bad_fetch)
        self.assertEqual(stamp, {})
        self.assertTrue(any("does not match pinned" in f for f in failures), failures)
        self.assertEqual((self.private / "node" / FILENAME).read_bytes(), b"corrupt",
                         "the corrupt artifact stays until a verified replacement exists")

    def test_verified_cache_needs_no_download(self):
        self.write_stamp()
        self.write_cache(GOOD_BYTES)

        def must_not_fetch(*a, **k):
            raise AssertionError("network used despite verified cache")

        stamp, failures = self.run_prepare(do_download=True,
                                           fetch_shasums=must_not_fetch,
                                           fetch_to=must_not_fetch)
        self.assertEqual(failures, [], failures)
        self.assertEqual(stamp["sha256"], GOOD_SHA)

    def test_stamp_digest_never_replaced_by_bad_bytes(self):
        self.write_stamp(sha=GOOD_SHA)
        self.write_cache(b"corrupt")
        self.run_prepare(do_download=False)
        stamp_on_disk = json.loads(
            (self.release / "node" / "node.stamp.json").read_text())
        self.assertEqual(stamp_on_disk["sha256"], GOOD_SHA,
                         "the trusted expected digest must survive a failed repair")

    def test_retry_after_successful_repair(self):
        self.write_stamp()
        self.write_cache(b"corrupt")
        # Simulate a valid tarball for the extraction step so stamp publication
        # is exercised; digests still come from the stub bytes.
        import io
        from unittest.mock import patch

        class FakeTar:
            def __init__(self, payload):
                self._payload = io.BytesIO(payload)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def extractfile(self, name):
                return io.BytesIO(self._payload.getvalue())

        fake = FakeTar(b"fake node binary")
        with patch.object(pnb.tarfile, "open", return_value=fake):
            stamp, failures = self.run_prepare(do_download=True)
        self.assertEqual(stamp.get("sha256"), GOOD_SHA)
        self.assertEqual(stamp.get("binary_sha256"),
                         hashlib.sha256(b"fake node binary").hexdigest())
        # second run: verified cache, no failures, no further download
        fs, ft, calls = self.stub_fetch()
        stamp2, failures2 = self.run_prepare(do_download=True, fetch_shasums=fs, fetch_to=ft)
        self.assertEqual(failures2, [], failures2)
        self.assertEqual(stamp2.get("sha256"), GOOD_SHA)
        self.assertEqual(calls["download"], 0, "verified cache must not re-download")


class CheckModeProvenanceTests(unittest.TestCase):
    """`--check` verifies the prepared tree; it must not destroy the tracked
    interface it is verifying.

    Drives the real `main()` in `--check` mode against a disposable fixture
    root holding a prepared (hash-valid) bundle and a tracked manifest that
    already records the node/model provenance blocks. The verification run
    must report success, keep those blocks, and leave every byte of the
    tracked output tree untouched.
    """

    WHEEL = ("attrs", "26.1.0")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / ".private" / "distribution" / "native-bundle"
        self.release = self.root / "release"
        # Point the module's roots at the disposable tree.
        self._orig = (pnb.ROOT, pnb.PRIVATE, pnb.RELEASE)
        pnb.ROOT, pnb.PRIVATE, pnb.RELEASE = self.root, self.private, self.release
        self.wheel_file = self.build_prepared_tree()

    def tearDown(self):
        pnb.ROOT, pnb.PRIVATE, pnb.RELEASE = self._orig

    # ---- fixture ----

    @staticmethod
    def build_wheel() -> bytes:
        """A minimal but valid wheel: a real zip with a dist-info METADATA
        and a license file, as wheel_license_files() expects."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("attrs/__init__.py", b"")
            zf.writestr(
                "attrs-26.1.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: attrs\nVersion: 26.1.0\nLicense: MIT\n",
            )
            zf.writestr("attrs-26.1.0.dist-info/LICENSE", b"MIT license text (fixture)\n")
        return buf.getvalue()

    def build_prepared_tree(self) -> str:
        name, version = self.WHEEL
        wheel_bytes = self.build_wheel()
        sha = hashlib.sha256(wheel_bytes).hexdigest()
        filename = f"{name}-{version}-py3-none-any.whl"
        dest = self.private / "wheels" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(wheel_bytes)
        (self.root / "native").mkdir(parents=True, exist_ok=True)
        (self.root / "native" / "uv.lock").write_text(
            "[[package]]\n"
            'name = "inkflip"\n'
            'version = "0.1.0"\n'
            'dependencies = [{ name = "attrs" }]\n'
            "\n"
            "[[package]]\n"
            f'name = "{name}"\n'
            f'version = "{version}"\n'
            "\n"
            "[[package.wheels]]\n"
            f'url = "https://files.pythonhosted.org/packages/aa/bb/{filename}"\n'
            f'hash = "sha256:{sha}"\n'
            f"size = {len(wheel_bytes)}\n"
        )
        return filename

    def run_check(self) -> tuple[int, str]:
        buf = io.StringIO()
        saved_argv = sys.argv
        sys.argv = ["prepare_native_bundle.py", "--check"]
        try:
            with contextlib.redirect_stdout(buf):
                code = pnb.main()
        finally:
            sys.argv = saved_argv
        return code, buf.getvalue()

    def snapshot_release(self) -> dict[str, bytes]:
        return {
            str(p.relative_to(self.release)): p.read_bytes()
            for p in sorted(self.release.rglob("*"))
            if p.is_file()
        }

    # ---- the confirmed defect ----

    def test_check_keeps_recorded_node_and_model_provenance(self):
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

        manifest_path = self.release / "native-wheels.manifest.json"
        self.assertTrue(manifest_path.is_file(), "check mode must still emit the manifest")
        recorded = json.loads(manifest_path.read_text())
        # The committed manifest records what the real preparation stamped.
        recorded["node"] = {
            "name": "node",
            "version": "22.23.2",
            "platform": "linux-x64",
            "filename": "node-v22.23.2-linux-x64.tar.xz",
            "url": "https://nodejs.org/dist/v22.23.2/node-v22.23.2-linux-x64.tar.xz",
            "shasums256_source": "https://nodejs.org/dist/v22.23.2/SHASUMS256.txt",
            "sha256": "d" * 64,
        }
        recorded["model"] = {
            "name": "tessdata_fast (eng.traineddata)",
            "version": "pinned commit 7d4322bd",
            "sha256": "e" * 64,
            "bytes": 4113088,
        }
        manifest_path.write_text(json.dumps(recorded, indent=2, sort_keys=True) + "\n")
        committed = manifest_path.read_text()
        before = self.snapshot_release()

        code, out = self.run_check()

        self.assertEqual(code, 0, out)
        self.assertIn("native bundle prepared: 1 wheels", out)
        verification_doc = json.loads(manifest_path.read_text())
        self.assertEqual(verification_doc.get("node"), recorded["node"],
                         "--check dropped the recorded node provenance block")
        self.assertEqual(verification_doc.get("model"), recorded["model"],
                         "--check dropped the recorded model provenance block")
        self.assertEqual(manifest_path.read_text(), committed,
                         "--check rewrote the tracked manifest to different bytes")
        changed = sorted(
            key for key, value in self.snapshot_release().items()
            if before.get(key) != value
        )
        self.assertEqual(changed, [], "--check rewrote tracked outputs it was only verifying")


if __name__ == "__main__":
    unittest.main()
