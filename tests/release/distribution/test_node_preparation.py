"""Node runtime preparation: verified-cache semantics (parallel-closeout).

Regression root (spot review 2026-09-14): prepare_node returned a success
stamp for a merely nonempty corrupted cache tarball. The rewritten
prepare_node verifies cached bytes against the pinned expected digest,
distinguishes missing/corrupt/offline states, keeps the previous artifact
intact when a replacement download fails or is refused, and never publishes
a success stamp whose digest came from bad bytes.

Regression root (spot review 2026-09-14, `--check` read-only): the check mode
rewrote the tracked interface it claimed to only verify. A tree whose wheel
had gone missing exited 1 and still regenerated release/native-requirements.lock
and release/native-wheels.manifest.json from the damaged state, dropping the
recorded wheel entry; a bare tree had its `release/` outputs created by a run
that was supposed to read them. The check mode is now a read-only verification
pass: it re-derives the expectation from native/uv.lock, verifies the prepared
bytes and the recorded stamps, and writes nothing on success or on refusal.

Regression root (spot review 2026-09-14, `--check` verified metadata, not
artifacts): the check mode never opened the node tarball or the OCR model, so a
manifest recording both stamps with no artifact on disk exited 0 as
"verified". Check mode now hashes the prepared artifacts against the recorded
stamps and against config/resolved-assets.json.

Regression root (spot review 2026-09-14, cold-cache success recorded as
failure): prepare_node appended "cache missing" before an authorized fetch of
a valid xz archive and kept that error after publishing a valid stamp, so
successful first-time preparation still exited 1. Missing/corrupt/offline
outcomes stay failures; a verified recovery does not.

Regression root (spot review 2026-09-14, duplicate wheel identity): a healthy
manifest entry followed by a duplicate with a conflicting hash passed --check
because setdefault kept the first. Duplicate package identities are refused
in either order, and lock-derived version/path_in_context must match.

Regression root (spot review 2026-09-14, notice path / wheel selection):
--check treated an absolute, `..`, or symlink license_evidence path as
satisfied if any non-empty file existed there. Evidence must stay inside the
fixture root and must not be a symlink. select_wheel's sort also preferred
newer glibc tags despite the recorded oldest-glibc policy.

Regression root (spot review 2026-09-14, nested evidence symlink):
--check counted a non-empty file reached only through a nested symlink
inside an otherwise-contained notice directory. Nested symlink targets are
not allowed content; a required evidence claim needs a real regular file
in that directory.

All tests use disposable caches and stub fetch functions; no network.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

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

    def genuine_archive(self) -> bytes:
        payload = b"#!/bin/sh\n# fixture node binary\n"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:xz") as tf:
            info = tarfile.TarInfo(f"node-v{VERSION}-linux-x64/bin/node")
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
        return buf.getvalue()

    def test_missing_cache_authorized_fetch_of_genuine_archive_is_success(self):
        """Confirmed probe: remove only the valid tarball, restore it through
        fetch_to, and a published stamp must not keep a cache-missing error."""
        archive = self.genuine_archive()
        digest = hashlib.sha256(archive).hexdigest()
        self.write_stamp(sha=digest)
        dest = self.private / "node" / FILENAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(archive)
        saved = dest.read_bytes()
        dest.unlink()

        stamp, failures = self.run_prepare(
            do_download=True,
            fetch_shasums=lambda url: (_ for _ in ()).throw(AssertionError("stamp already pins the digest")),
            fetch_to=lambda url, dest_path: dest_path.write_bytes(saved),
        )
        self.assertEqual(failures, [], failures)
        self.assertEqual(stamp.get("sha256"), digest)
        self.assertTrue(dest.is_file())
        self.assertEqual(hashlib.sha256(dest.read_bytes()).hexdigest(), digest)
        published = json.loads((self.release / "node" / "node.stamp.json").read_text())
        self.assertEqual(published["sha256"], digest)

    def test_corrupt_cache_authorized_fetch_of_genuine_archive_is_success(self):
        archive = self.genuine_archive()
        digest = hashlib.sha256(archive).hexdigest()
        self.write_stamp(sha=digest)
        corrupt = b"corrupt cache bytes"
        dest = self.write_cache(corrupt)
        stamp, failures = self.run_prepare(
            do_download=True,
            fetch_to=lambda url, dest_path: dest_path.write_bytes(archive),
        )
        self.assertEqual(failures, [], failures)
        self.assertEqual(stamp.get("sha256"), digest)
        self.assertEqual(dest.read_bytes(), archive)
        self.assertNotEqual(dest.read_bytes(), corrupt)

    def test_missing_cache_network_failure_does_not_publish_a_stamp(self):
        def fail_fetch(url, dest):
            raise OSError("connection reset")

        stamp, failures = self.run_prepare(do_download=True, fetch_to=fail_fetch)
        self.assertEqual(stamp, {})
        self.assertTrue(any("missing" in f for f in failures), failures)
        self.assertTrue(any("download failed" in f for f in failures), failures)
        self.assertFalse((self.release / "node" / "node.stamp.json").is_file())
        dest = self.private / "node" / FILENAME
        self.assertFalse(dest.is_file() and dest.stat().st_size > 0)

    def test_missing_cache_bad_bytes_do_not_publish_a_stamp(self):
        archive = self.genuine_archive()
        digest = hashlib.sha256(archive).hexdigest()
        self.write_stamp(sha=digest)

        stamp, failures = self.run_prepare(
            do_download=True,
            fetch_to=lambda url, dest_path: dest_path.write_bytes(b"wrong bytes"),
        )
        self.assertEqual(stamp, {})
        self.assertTrue(any("does not match pinned" in f for f in failures), failures)
        dest = self.private / "node" / FILENAME
        self.assertFalse(dest.is_file())
        published = json.loads((self.release / "node" / "node.stamp.json").read_text())
        self.assertEqual(published["sha256"], digest, "trusted stamp digest must not become the bad bytes")


class WheelSelectionTests(unittest.TestCase):
    def wheel(self, plat, digest="a" * 64, size=1):
        return {
            "url": f"https://example.invalid/demo-1.0.0-cp313-cp313-{plat}.whl",
            "hash": f"sha256:{digest}",
            "size": size,
        }

    def test_oldest_glibc_tag_is_chosen_over_newer(self):
        newer = self.wheel("manylinux_2_28_x86_64", "1" * 64)
        older = self.wheel("manylinux_2_17_x86_64", "2" * 64)
        for order, wheels in (("new-first", [newer, older]), ("old-first", [older, newer])):
            with self.subTest(order):
                pkg = {"name": "demo", "version": "1.0.0", "wheels": wheels}
                chosen, err = pnb.select_wheel(pkg)
                self.assertIsNone(err, err)
                self.assertIn("manylinux_2_17_x86_64", chosen["url"])

    def test_manylinux2014_is_wider_than_manylinux_2_28(self):
        newer = self.wheel("manylinux_2_28_x86_64", "3" * 64)
        older = self.wheel("manylinux2014_x86_64", "4" * 64)
        for order, wheels in (("new-first", [newer, older]), ("old-first", [older, newer])):
            with self.subTest(order):
                pkg = {"name": "demo", "version": "1.0.0", "wheels": wheels}
                chosen, err = pnb.select_wheel(pkg)
                self.assertIsNone(err, err)
                self.assertIn("manylinux2014_x86_64", chosen["url"])


class CheckModeVerificationTests(unittest.TestCase):
    """`--check` verifies a prepared tree, read-only.

    Regression root (spot review 2026-09-14): check mode rebuilt the tracked
    interface while claiming to verify it. A run over a tree whose wheel had
    gone missing exited 1 and still rewrote release/native-requirements.lock
    and release/native-wheels.manifest.json, truncating the recorded wheel
    list from one entry to none. It also never looked at the prepared node and
    model artifacts, so a tree that recorded both stamps with no artifact on
    disk exited 0 as "verified". Check mode now re-derives the expectation
    from native/uv.lock, verifies the prepared bytes against the recorded
    stamps and identities, and writes nothing — not on success, not on
    refusal.

    Each case drives the real main() over a disposable fixture root. The
    fixture bundle is produced by the real preparation path with stubbed
    fetchers (no network), so the manifest, the two stamps, the requirements
    lock and the build-context pointer are exactly what preparation writes;
    the test then mutates one artifact or recorded document.
    """

    WHEEL_NAME = "attrs"
    WHEEL_VERSION = "26.1.0"
    NODE_VERSION = "22.23.2"
    MODEL_BYTES = b"tessdata_fast fixture bytes\n" * 32
    MODEL_STAGED = "models/tessdata-fast-eng/7d4322bd/eng.traineddata"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / ".private" / "distribution" / "native-bundle"
        self.release = self.root / "release"
        # Point the module's roots at the disposable tree.
        self._orig = (pnb.ROOT, pnb.PRIVATE, pnb.RELEASE)
        pnb.ROOT, pnb.PRIVATE, pnb.RELEASE = self.root, self.private, self.release
        self.wheel_filename = f"{self.WHEEL_NAME}-{self.WHEEL_VERSION}-py3-none-any.whl"
        self.node_filename = f"node-v{self.NODE_VERSION}-linux-x64.tar.xz"
        self.wheel_path = self.private / "wheels" / self.wheel_filename
        self.node_path = self.private / "node" / self.node_filename
        self.model_path = self.private / "models" / "tessdata" / "eng.traineddata"
        self.manifest_path = self.release / "native-wheels.manifest.json"
        self.requirements_path = self.release / "native-requirements.lock"
        self.node_stamp_path = self.release / "node" / "node.stamp.json"
        self.model_stamp_path = self.release / "models" / "model.stamp.json"
        self.build_prepared_tree()

    def tearDown(self):
        pnb.ROOT, pnb.PRIVATE, pnb.RELEASE = self._orig

    # ---- fixture ----

    def build_wheel(self) -> bytes:
        """A minimal but valid wheel: a real zip with a dist-info METADATA and
        a license file, as wheel_license_files() expects."""
        name, version = self.WHEEL_NAME, self.WHEEL_VERSION
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"{name}/__init__.py", b"")
            zf.writestr(
                f"{name}-{version}.dist-info/METADATA",
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nLicense: MIT\n",
            )
            zf.writestr(f"{name}-{version}.dist-info/LICENSE", b"MIT license text (fixture)\n")
        return buf.getvalue()

    def build_node_tarball(self) -> bytes:
        """A real xz-compressed tarball carrying the binary path prepare_node
        extracts, so the preparation path publishes a genuine stamp for it."""
        payload = b"#!/bin/sh\n# fixture node binary\n"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:xz") as tf:
            info = tarfile.TarInfo(f"node-v{self.NODE_VERSION}-linux-x64/bin/node")
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
        return buf.getvalue()

    def write_lock(self, wheel_sha256: str, wheel_bytes: int) -> None:
        path = self.root / "native" / "uv.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[[package]]\n"
            'name = "inkflip"\n'
            'version = "0.1.0"\n'
            f'dependencies = [{{ name = "{self.WHEEL_NAME}" }}]\n'
            "\n"
            "[[package]]\n"
            f'name = "{self.WHEEL_NAME}"\n'
            f'version = "{self.WHEEL_VERSION}"\n'
            "\n"
            "[[package.wheels]]\n"
            f'url = "https://files.pythonhosted.org/packages/aa/bb/{self.wheel_filename}"\n'
            f'hash = "sha256:{wheel_sha256}"\n'
            f"size = {wheel_bytes}\n"
        )
        return path

    def build_prepared_tree(self) -> None:
        """Produce the fixture bundle through the real preparation path, with
        the network stubbed out."""
        wheel_bytes = self.build_wheel()
        self.wheel_path.parent.mkdir(parents=True, exist_ok=True)
        self.wheel_path.write_bytes(wheel_bytes)
        self.write_lock(hashlib.sha256(wheel_bytes).hexdigest(), len(wheel_bytes))

        (self.root / ".node-version").write_text(self.NODE_VERSION + "\n")
        node_bytes = self.build_node_tarball()
        node_sha256 = hashlib.sha256(node_bytes).hexdigest()
        # The cache is laid out as preparation leaves it (artifact present, no
        # stamp yet), so preparation takes its verified-replacement path and
        # publishes the stamp for these bytes without reporting anything.
        self.node_path.parent.mkdir(parents=True, exist_ok=True)
        self.node_path.write_bytes(node_bytes)

        staged = self.root / "apps" / "web" / "public" / self.MODEL_STAGED
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(self.MODEL_BYTES)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "config" / "resolved-assets.json").write_text(json.dumps({
            "assets": [{
                "id": "tessdata-fast-eng",
                "kind": "ocr-model",
                "license": "Apache-2.0",
                "rights": "fixture rights",
                "files": [{
                    "staged_path": self.MODEL_STAGED,
                    "sha256": hashlib.sha256(self.MODEL_BYTES).hexdigest(),
                    "bytes": len(self.MODEL_BYTES),
                }],
            }],
        }, indent=2))
        notice = self.root / "licenses" / "tessdata-fast-eng" / "NOTICE.txt"
        notice.parent.mkdir(parents=True, exist_ok=True)
        notice.write_text("tessdata_fast fixture notice\n")

        real_prepare_node = pnb.prepare_node

        def stub_prepare_node(failures, do_download, **kwargs):
            return real_prepare_node(
                failures, do_download,
                fetch_shasums=lambda url: f"{node_sha256}  {self.node_filename}\n",
                fetch_to=lambda url, dest: dest.write_bytes(node_bytes))

        def no_network(*args, **kwargs):
            raise AssertionError("preparation fixture must not touch the network")

        with mock.patch.object(pnb, "prepare_node", stub_prepare_node), \
                mock.patch.object(pnb, "download", no_network), \
                mock.patch.object(pnb.urllib.request, "urlopen", no_network), \
                mock.patch.object(pnb.urllib.request, "urlretrieve", no_network), \
                mock.patch.object(pnb, "_fetch_shasums", no_network), \
                mock.patch.object(pnb, "_fetch_to", no_network):
            code, out, err = self.run_main()
        self.assertEqual(code, 0, f"fixture preparation failed:\n{out}{err}")
        self.assertEqual(self.node_path.read_bytes(), node_bytes,
                         "fixture preparation did not cache the node tarball")

    # ---- driving and observing ----

    def run_main(self, *argv: str):
        """Drive the real main(). An exception is reported as a failure of the
        run under test, not as an error of the test harness."""
        out, err = io.StringIO(), io.StringIO()
        saved_argv = sys.argv
        sys.argv = ["prepare_native_bundle.py", *argv]
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = pnb.main()
        except Exception as exc:  # a crash is never an acceptable outcome
            code = f"raised {type(exc).__name__}: {exc}"
        finally:
            sys.argv = saved_argv
        return code, out.getvalue(), err.getvalue()

    def check(self):
        code, out, err = self.run_main("--check")
        return code, out + err

    def snapshot(self, root: Path | None = None):
        """Every file with its digest plus the directory list, so a run that
        writes, creates or removes anything is visible."""
        root = root or self.root
        files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(root.rglob("*")) if p.is_file()}
        dirs = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_dir())
        return files, dirs

    def assert_tree_unchanged(self, before, root: Path | None = None):
        files_before, dirs_before = before
        files_after, dirs_after = self.snapshot(root)
        changed = sorted(k for k, v in files_after.items() if files_before.get(k) != v)
        removed = sorted(k for k in files_before if k not in files_after)
        created = sorted(k for k in files_after if k not in files_before)
        created_dirs = sorted(d for d in dirs_after if d not in dirs_before)
        self.assertEqual((changed, removed, created, created_dirs), ([], [], [], []),
                         "a --check run must not rewrite, create or remove anything")

    def use_root(self, *, with_lock: bool = True) -> Path:
        """A fresh disposable root; the module globals follow it."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        if with_lock:
            (root / "native").mkdir(parents=True)
            (root / "native" / "uv.lock").write_text(
                (self.root / "native" / "uv.lock").read_text())
        pnb.ROOT = root
        pnb.PRIVATE = root / ".private" / "distribution" / "native-bundle"
        pnb.RELEASE = root / "release"
        return root

    # ---- the healthy path ----

    def test_valid_prepared_bundle_verifies_and_changes_nothing(self):
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("native bundle verified: 1 wheels, node + model artifacts "
                      "match the recorded stamps", out)
        self.assertIn("  bulky artifacts: ", out)
        self.assertIn("  tracked interface: ", out)
        self.assert_tree_unchanged(before)

    # ---- prepared artifacts ----

    def test_missing_wheel_is_named_and_nothing_is_repaired(self):
        self.wheel_path.unlink()
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("native bundle verification:", out)
        self.assertIn(f"prepared wheel missing: {self.wheel_filename}", out)
        self.assert_tree_unchanged(before)  # no download, no repair, no rewrite

    def test_corrupt_wheel_is_named_and_the_manifest_is_untouched(self):
        original = self.wheel_path.read_bytes()
        self.wheel_path.write_bytes(b"X" * len(original))  # bytes changed, size kept
        manifest_before = self.manifest_path.read_bytes()
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn(f"prepared wheel hash mismatch: {self.wheel_filename}", out)
        self.assertNotIn("prepared wheel size mismatch", out)
        self.assertEqual(self.manifest_path.read_bytes(), manifest_before,
                         "the manifest must not be rewritten from the bad bytes")
        self.assert_tree_unchanged(before)

    def test_missing_node_artifact_with_a_valid_stamp_is_named(self):
        self.assertTrue(self.node_stamp_path.is_file(), "fixture must record a node stamp")
        self.node_path.unlink()
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("prepared node artifact missing: ", out)
        self.assertIn(self.node_filename, out)
        self.assert_tree_unchanged(before)

    def test_corrupt_node_artifact_is_named(self):
        self.node_path.write_bytes(b"tampered node bytes")
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("prepared node artifact hash mismatch:", out)
        self.assert_tree_unchanged(before)

    def test_missing_model_artifact_is_named(self):
        self.model_path.unlink()
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("prepared model artifact missing:", out)
        self.assertIn("eng.traineddata", out)
        self.assert_tree_unchanged(before)

    def test_corrupt_model_artifact_is_named(self):
        original = self.model_path.read_bytes()
        self.model_path.write_bytes(b"Y" * len(original))
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("prepared model artifact hash mismatch:", out)
        self.assert_tree_unchanged(before)

    # ---- recorded documents ----

    def test_malformed_manifest_shapes_are_named_not_raised(self):
        shape_valid = json.loads(self.manifest_path.read_text())
        cases = {
            "invalid JSON": b'{"kind": "inkflip-native-wheels-manifest", ',
            "array root": b"[]",
            "wheels not a list": json.dumps(
                {**shape_valid, "wheels": {"attrs": {}}}).encode(),
        }
        expected = {
            "invalid JSON": "release/native-wheels.manifest.json is not readable JSON",
            "array root": "release/native-wheels.manifest.json root must be a JSON object",
            "wheels not a list": "release/native-wheels.manifest.json 'wheels' must be a JSON list",
        }
        for label, content in cases.items():
            with self.subTest(label):
                self.manifest_path.write_bytes(content)
                before = self.snapshot()
                code, out = self.check()
                self.assertEqual(code, 1, out)
                self.assertIn(expected[label], out)
                self.assertNotIn("Traceback", out)
                self.assert_tree_unchanged(before)

    def test_malformed_node_stamp_is_named_not_raised(self):
        good_text = self.node_stamp_path.read_text()
        cases = {
            "truncated JSON": (good_text[:40],
                               "release/node/node.stamp.json is not readable JSON"),
            "missing sha256": (
                json.dumps({k: v for k, v in json.loads(good_text).items() if k != "sha256"}),
                "release/node/node.stamp.json must record a 64-hex sha256"),
            "non-hex sha256": (
                json.dumps({**json.loads(good_text), "sha256": "z" * 64}),
                "release/node/node.stamp.json must record a 64-hex sha256"),
        }
        for label, (content, message) in cases.items():
            with self.subTest(label):
                self.node_stamp_path.write_text(content)
                before = self.snapshot()
                code, out = self.check()
                self.assertEqual(code, 1, out)
                self.assertIn(message, out)
                self.assertNotIn("Traceback", out)
                self.assert_tree_unchanged(before)

    def test_malformed_model_stamp_is_named_not_raised(self):
        good = json.loads(self.model_stamp_path.read_text())
        for label, value in (("boolean", True), ("string", str(good["bytes"]))):
            with self.subTest(label):
                self.model_stamp_path.write_text(json.dumps({**good, "bytes": value}))
                before = self.snapshot()
                code, out = self.check()
                self.assertEqual(code, 1, out)
                self.assertIn(f"must record non-negative integer bytes: found {value!r}", out)
                self.assertNotIn("Traceback", out)
                self.assert_tree_unchanged(before)

    # ---- read-only guarantee ----

    def test_bare_tree_reports_failures_without_creating_directories(self):
        root = self.use_root()
        before = self.snapshot(root)
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("native bundle verification:", out)
        self.assertIn("release/native-wheels.manifest.json missing", out)
        self.assertIn("release/node/node.stamp.json missing", out)
        self.assertIn("release/models/model.stamp.json missing", out)
        self.assertIn("build context pointer missing:", out)
        self.assertIn(f"prepared wheel missing: {self.wheel_filename}", out)
        self.assert_tree_unchanged(before, root)

    def test_refusal_keeps_the_tracked_outputs_byte_identical(self):
        """Defect 1: after a successful check, deleting only the prepared wheel
        and re-running must refuse without rewriting anything."""
        code, out = self.check()
        self.assertEqual(code, 0, out)
        manifest_before = self.manifest_path.read_bytes()
        requirements_before = self.requirements_path.read_bytes()
        recorded_node = json.loads(manifest_before)["node"]

        self.wheel_path.unlink()
        before = self.snapshot()
        code, out = self.check()

        self.assertEqual(code, 1, out)
        self.assertIn(f"prepared wheel missing: {self.wheel_filename}", out)
        self.assertEqual(self.manifest_path.read_bytes(), manifest_before,
                         "the manifest was rewritten by a refused check")
        self.assertEqual(self.requirements_path.read_bytes(), requirements_before,
                         "the requirements lock was rewritten by a refused check")
        document = json.loads(self.manifest_path.read_text())
        self.assertEqual(len(document["wheels"]), 1,
                         "the recorded wheel entry must survive a refused check")
        self.assertEqual(document["node"], recorded_node,
                         "the recorded node provenance must survive a refused check")
        self.assert_tree_unchanged(before)

    def test_check_path_uses_no_network(self):
        def no_network(*args, **kwargs):
            raise AssertionError("--check used the network")

        with mock.patch.object(pnb, "download", no_network), \
                mock.patch.object(pnb, "_fetch_shasums", no_network), \
                mock.patch.object(pnb, "_fetch_to", no_network), \
                mock.patch.object(pnb.urllib.request, "urlopen", no_network), \
                mock.patch.object(pnb.urllib.request, "urlretrieve", no_network):
            code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("native bundle verified: 1 wheels", out)

    def test_symlinked_artifacts_are_named(self):
        """A symlink must not satisfy the prepared-artifact contract."""
        for path, real_name in ((self.wheel_path, "real-wheel.whl"),
                                (self.node_path, "real-node.tar.xz")):
            target = path.with_name(real_name)
            path.rename(target)
            path.symlink_to(target)
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn(f"prepared wheel is a symlink: {self.wheel_filename}", out)
        self.assertIn("prepared node artifact is a symlink:", out)
        self.assert_tree_unchanged(before)

    def test_missing_lock_is_still_a_config_error(self):
        root = self.use_root(with_lock=False)
        before = self.snapshot(root)
        code, out, err = self.run_main("--check")
        self.assertEqual(code, 2, out + err)
        self.assertIn("config error: native/uv.lock not found", err)
        self.assert_tree_unchanged(before, root)

    def test_first_time_authorized_node_fetch_prepares_successfully(self):
        """Successful recovery of a missing cache must not fail the bundle."""
        node_bytes = self.node_path.read_bytes()
        node_sha = hashlib.sha256(node_bytes).hexdigest()
        self.node_path.unlink()
        real_prepare_node = pnb.prepare_node

        def stub_prepare_node(failures, do_download, **kwargs):
            return real_prepare_node(
                failures, do_download,
                fetch_shasums=lambda url: (_ for _ in ()).throw(
                    AssertionError("stamp already pins the digest")),
                fetch_to=lambda url, dest: dest.write_bytes(node_bytes))

        def no_network(*args, **kwargs):
            raise AssertionError("wheel/model path must not touch the network")

        with mock.patch.object(pnb, "prepare_node", stub_prepare_node), \
                mock.patch.object(pnb, "download", no_network), \
                mock.patch.object(pnb.urllib.request, "urlopen", no_network), \
                mock.patch.object(pnb.urllib.request, "urlretrieve", no_network):
            code, out, err = self.run_main()
        self.assertEqual(code, 0, f"{out}{err}")
        self.assertIn("native bundle prepared: 1 wheels", out)
        self.assertNotIn("cache missing", out)
        self.assertEqual(hashlib.sha256(self.node_path.read_bytes()).hexdigest(), node_sha)
        before = self.snapshot()
        check_code, check_out = self.check()
        self.assertEqual(check_code, 0, check_out)
        self.assert_tree_unchanged(before)

    def rewrite_wheels(self, wheels):
        document = json.loads(self.manifest_path.read_text())
        document["wheels"] = wheels
        self.manifest_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        return document

    def test_duplicate_conflicting_hash_healthy_first_is_refused(self):
        document = json.loads(self.manifest_path.read_text())
        healthy = dict(document["wheels"][0])
        conflict = dict(healthy)
        conflict["sha256"] = "0" * 64
        self.rewrite_wheels([healthy, conflict])
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("duplicate package identity", out)
        self.assertIn(self.WHEEL_NAME, out)
        self.assertNotIn("native bundle verified:", out)
        self.assert_tree_unchanged(before)

    def test_duplicate_conflicting_hash_conflict_first_is_refused(self):
        document = json.loads(self.manifest_path.read_text())
        healthy = dict(document["wheels"][0])
        conflict = dict(healthy)
        conflict["sha256"] = "0" * 64
        self.rewrite_wheels([conflict, healthy])
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("duplicate package identity", out)
        self.assertIn(self.WHEEL_NAME, out)
        self.assertNotIn("native bundle verified:", out)
        self.assert_tree_unchanged(before)

    def test_manifest_version_contradiction_is_named(self):
        document = json.loads(self.manifest_path.read_text())
        item = dict(document["wheels"][0])
        item["version"] = "0.0.0"
        self.rewrite_wheels([item])
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("manifest wheel version drift", out)
        self.assertIn(self.WHEEL_NAME, out)
        self.assert_tree_unchanged(before)

    def test_manifest_path_in_context_contradiction_is_named(self):
        document = json.loads(self.manifest_path.read_text())
        item = dict(document["wheels"][0])
        item["path_in_context"] = "wheels/other.whl"
        self.rewrite_wheels([item])
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("manifest wheel path_in_context drift", out)
        self.assert_tree_unchanged(before)

    def test_license_evidence_outside_the_tree_is_named(self):
        document = json.loads(self.manifest_path.read_text())
        item = dict(document["wheels"][0])
        cases = {}
        absolute = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(absolute, ignore_errors=True))
        (absolute / "NOTICE.txt").write_text("harmless generated notice\n")
        cases["absolute"] = str(absolute)
        sibling = self.root.parent / f"harmless-notices-{self.root.name}"
        sibling.mkdir()
        self.addCleanup(lambda: shutil.rmtree(sibling, ignore_errors=True))
        (sibling / "NOTICE.txt").write_text("harmless generated notice\n")
        cases["relative-escape"] = f"../{sibling.name}"
        link = self.release / "notices" / "escaped-link"
        link.symlink_to(absolute)
        cases["symlink"] = str(link.relative_to(self.root))
        for label, evidence in cases.items():
            with self.subTest(label):
                mutated = dict(item)
                mutated["license_evidence"] = evidence
                self.rewrite_wheels([mutated])
                before = self.snapshot()
                code, out = self.check()
                self.assertEqual(code, 1, out)
                self.assertNotIn("Traceback", out)
                self.assertNotIn("native bundle verified:", out)
                if label == "symlink":
                    self.assertIn("license evidence is a symlink", out)
                else:
                    self.assertIn("license evidence path escapes the repository", out)
                self.assert_tree_unchanged(before)

    def _notice_dir(self) -> Path:
        document = json.loads(self.manifest_path.read_text())
        return self.root / document["wheels"][0]["license_evidence"]

    def test_nested_symlink_evidence_is_not_counted(self):
        """An outside file reached only through a nested symlink must not
        satisfy the required evidence claim."""
        notice_dir = self._notice_dir()
        self.assertTrue(notice_dir.is_dir(), "fixture must record a notice directory")
        for child in list(notice_dir.iterdir()):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(outside, ignore_errors=True))
        (outside / "NOTICE.txt").write_text("harmless generated notice\n")
        (notice_dir / "nested-link").symlink_to(outside / "NOTICE.txt")
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("native bundle verified:", out)
        self.assertIn("license evidence missing or empty", out)
        self.assert_tree_unchanged(before)

    def test_empty_license_evidence_directory_is_named(self):
        notice_dir = self._notice_dir()
        for child in list(notice_dir.iterdir()):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("native bundle verified:", out)
        self.assertIn("license evidence missing or empty", out)
        self.assert_tree_unchanged(before)

    def test_malformed_license_evidence_is_named_not_raised(self):
        document = json.loads(self.manifest_path.read_text())
        item = dict(document["wheels"][0])
        item["license_evidence"] = True
        self.rewrite_wheels([item])
        before = self.snapshot()
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("native bundle verified:", out)
        self.assertIn("license evidence missing or empty", out)
        self.assert_tree_unchanged(before)


if __name__ == "__main__":
    unittest.main()
