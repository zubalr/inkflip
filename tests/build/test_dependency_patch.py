"""Tampering with patch declarations, source or bytes fails frozen verification."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_dependencies


class DependencyPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in ("package.json", "bun.lock", "config/dependency-patches.json",
                         "patches/tesseract.js@7.0.0.patch"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.installed = self.root / "installed"
        (self.installed / "src").mkdir(parents=True)
        for relative in ("package.json", "src/createWorker.js", "src/index.d.ts"):
            shutil.copyfile(ROOT / "apps/web/node_modules/tesseract.js" / relative,
                            self.installed / relative)

    def verify(self):
        check_dependencies.FAILURES.clear()
        with mock.patch.object(check_dependencies, "ROOT", self.root), \
                mock.patch.object(check_dependencies.prepare_assets, "package_root", return_value=self.installed), \
                contextlib.redirect_stdout(io.StringIO()):
            check_dependencies.check_dependency_patch()
        return list(check_dependencies.FAILURES)

    def test_exact_record_and_installed_bytes_pass(self):
        self.assertEqual(self.verify(), [])

    def test_modified_patch_fails(self):
        with (self.root / "patches/tesseract.js@7.0.0.patch").open("a") as handle:
            handle.write("\nchanged\n")
        self.assertTrue(any("patch.bytes" in item for item in self.verify()))

    def test_missing_patch_fails(self):
        (self.root / "patches/tesseract.js@7.0.0.patch").unlink()
        self.assertTrue(any("patch.install" in item for item in self.verify()))

    def test_unrecorded_patch_target_fails_even_with_updated_digest(self):
        patch = self.root / "patches/tesseract.js@7.0.0.patch"
        with patch.open("a") as handle:
            handle.write("\ndiff --git a/.bun-tag-extra b/.bun-tag-extra\nnew file mode 100644\n")
        metadata = self.root / "config/dependency-patches.json"
        record = json.loads(metadata.read_text())
        record["tesseract.js@7.0.0"]["patch_sha256"] = hashlib.sha256(patch.read_bytes()).hexdigest()
        metadata.write_text(json.dumps(record))
        self.assertTrue(any("patch.targets" in item for item in self.verify()))

    def test_unpatched_or_modified_constructor_fails(self):
        (self.installed / "src/createWorker.js").write_text("module.exports = async () => {};\n")
        self.assertTrue(any("patch.installed.src/createWorker.js" in item for item in self.verify()))

    def test_missing_manifest_declaration_fails(self):
        package = json.loads((self.root / "package.json").read_text())
        package.pop("patchedDependencies")
        (self.root / "package.json").write_text(json.dumps(package))
        self.assertTrue(any("patch.manifest" in item for item in self.verify()))

    def test_missing_lock_declaration_fails(self):
        lock = json.loads(check_dependencies.jsonc_to_json((self.root / "bun.lock").read_text()))
        lock.pop("patchedDependencies")
        (self.root / "bun.lock").write_text(json.dumps(lock))
        self.assertTrue(any("patch.lock" in item for item in self.verify()))

    def test_wrong_installed_version_fails(self):
        (self.installed / "package.json").write_text('{"name":"tesseract.js","version":"8.0.0"}')
        self.assertTrue(any("patch.version" in item for item in self.verify()))
