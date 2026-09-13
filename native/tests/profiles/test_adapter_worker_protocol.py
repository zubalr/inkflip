"""ProfileAdapter worker-protocol regressions with REAL child executables.

OWNER-SCOPE.md recorded the confirmed defect: `ProfileAdapter._run` returned
success when a worker exited nonzero but printed `{"ok":true}`, treated an empty
or wrong-shaped response as a normal result, and raised `AttributeError` for a
JSON array. These tests replace the mocked evidence with real tiny workers run in
disposable directories and pin the property that matters: a worker is untrusted
input, so a nonzero exit is never success and every wrong shape is a typed
`ProfileError`.

Every case compiles its own worker body, so no case can pass because of a shared
stub. Cleanup cases write the child pid to `INKFLIP_TEST_PIDFILE`, which the
offline child environment forwards, and assert the process is gone afterwards.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "native"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))

from inkflip.profiles.adapter import ProfileAdapter  # noqa: E402
from inkflip.profiles.models import ProfileError, ReaderProfile  # noqa: E402

VERSION = "1.2.3"
READER_JSON = '{"id": "pypdf-native", "name": "pypdf", "version": "1.2.3"}'

DESCRIBE_OK = """import json, sys
sys.stdout.write('{"ok": true, "reader": %s}')
sys.exit(0)
""" % READER_JSON

OK_TRUE_EXIT_7 = """import sys
sys.stdout.write('{"ok": true, "reader": %s}')
sys.exit(7)
""" % READER_JSON

FULL_PAYLOAD_EXIT_1 = """import sys
sys.stdout.write('{"ok": true, "reader": %s, "pages": [{"page_index": 0, "status": "completed", "raw_text": "x"}], "pypdf_version": "1.2.3"}')
sys.exit(1)
""" % READER_JSON

OK_FALSE = """import sys
sys.stdout.write('{"ok": false, "error": "worker said no"}')
sys.exit(0)
"""

NO_OK = """import sys
sys.stdout.write('{"reader": %s}')
sys.exit(0)
""" % READER_JSON

OK_STRING = """import sys
sys.stdout.write('{"ok": "yes", "reader": %s}')
sys.exit(0)
""" % READER_JSON

OK_ONE = """import sys
sys.stdout.write('{"ok": 1, "reader": %s}')
sys.exit(0)
""" % READER_JSON

RAW_ARRAY = "import sys\nsys.stdout.write('[]')\nsys.exit(0)\n"
RAW_SCALAR = "import sys\nsys.stdout.write('\"scalar\"')\nsys.exit(0)\n"
RAW_NULL = "import sys\nsys.stdout.write('null')\nsys.exit(0)\n"
RAW_INT = "import sys\nsys.stdout.write('3')\nsys.exit(0)\n"
RAW_EMPTY = "pass\n"
RAW_NOT_JSON = "import sys\nsys.stdout.write('not json at all')\nsys.exit(0)\n"
RAW_DUPLICATE = "import sys\nsys.stdout.write('{\"ok\": true, \"ok\": true}')\nsys.exit(0)\n"
RAW_TRAILING = "import sys\nsys.stdout.write('{\"ok\": true} trailing')\nsys.exit(0)\n"

NONZERO_WITH_STDERR = """import sys
sys.stdout.write('{"ok": true, "reader": %s}')
sys.stderr.write('worker exploded mid-extraction\\n')
sys.exit(9)
""" % READER_JSON

UNICODE_STDERR = """import sys
sys.stderr.write('echec de l extraction: caractere inattendu - \u5931\u6557\\n')
sys.exit(4)
"""

STDERR_CHATTER = """import sys
sys.stderr.write('loading model...\\n')
sys.stdout.write('{"ok": true, "reader": %s}')
sys.exit(0)
""" % READER_JSON

DESCRIBE_NO_READER = "import sys\nsys.stdout.write('{\"ok\": true}')\nsys.exit(0)\n"
DESCRIBE_NO_VERSION = "import sys\nsys.stdout.write('{\"ok\": true, \"reader\": {\"id\": \"pypdf-native\"}}')\nsys.exit(0)\n"
DESCRIBE_WRONG_VERSION = """import sys
sys.stdout.write('{"ok": true, "reader": {"id": "pypdf-native", "name": "pypdf", "version": "9.9.9"}}')
sys.exit(0)
"""
DESCRIBE_NO_ID = """import sys
sys.stdout.write('{"ok": true, "reader": {"version": "1.2.3"}}')
sys.exit(0)
"""
EXTRACT_NO_PAGES = DESCRIBE_OK.replace('sys.exit(0)', 'sys.exit(0)')
EXTRACT_NO_PAGES = """import sys
sys.stdout.write('{"ok": true, "reader": %s}')
sys.exit(0)
""" % READER_JSON
EXTRACT_EMPTY_PAGES = """import sys
sys.stdout.write('{"ok": true, "reader": %s, "pages": []}')
sys.exit(0)
""" % READER_JSON
EXTRACT_BAD_STATUS = """import sys
sys.stdout.write('{"ok": true, "reader": %s, "pages": [{"page_index": 0}]}')
sys.exit(0)
""" % READER_JSON
EXTRACT_NO_TEXT = """import sys
sys.stdout.write('{"ok": true, "reader": %s, "pages": [{"page_index": 0, "status": "completed"}]}')
sys.exit(0)
""" % READER_JSON
EXTRACT_FAILED_PAGE = """import sys
sys.stdout.write('{"ok": true, "reader": %s, "pages": [{"page_index": 0, "status": "failed", "reason": "extract_text failed: RuntimeError", "raw_text": null}]}')
sys.exit(0)
""" % READER_JSON

PID_PREFIX = """import os
open(os.environ["INKFLIP_TEST_PIDFILE"], "w").write(str(os.getpid()))
"""

FLOOD_STDOUT = PID_PREFIX + """import sys
chunk = "x" * 65536
for _ in range(512):
    sys.stdout.write(chunk)
"""
FLOOD_STDERR = PID_PREFIX + """import sys
chunk = "y" * 65536
for _ in range(8):
    sys.stderr.write(chunk)
"""
HANG = PID_PREFIX + "import time\ntime.sleep(120)\n"
ABANDON_DESCENDANT = PID_PREFIX + """import json, subprocess, sys
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open(os.environ["INKFLIP_TEST_PIDFILE"], "w").write(str(child.pid))
sys.stdout.write('{"ok": true, "reader": %s}')
sys.exit(0)
""" % READER_JSON


class WorkerProtocolCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmpdir.name)
        self.pidfile = self.td / "child.pid"
        os.environ["INKFLIP_TEST_PIDFILE"] = str(self.pidfile)

    def tearDown(self):
        os.environ.pop("INKFLIP_TEST_PIDFILE", None)
        self.tmpdir.cleanup()

    def adapter(self, body: str, *, version: str = VERSION) -> ProfileAdapter:
        worker = self.td / "worker.py"
        worker.write_text(body, encoding="utf-8")
        profile = ReaderProfile(
            name="protocol-probe",
            reader="pypdf",
            version=version,
            executable=Path(sys.executable),
            platform=sys.platform,
            python_version="3.13.15",
            artifact_digest=None,
            profile_sha256="0" * 64,
            wrapper_path=worker,
            wrapper_sha256="1" * 64,
            created_at="2026-09-14T00:00:00Z",
            extra={},
        )
        return ProfileAdapter(profile)

    def pdf(self) -> Path:
        path = self.td / "probe.pdf"
        path.write_bytes(b"%PDF-1.4\n")
        return path

    def assert_describe_refused(self, body: str, needle: str | None = None, version: str = VERSION) -> str:
        with self.assertRaises(ProfileError) as ctx:
            self.adapter(body, version=version).describe()
        message = str(ctx.exception)
        self.assertNotIn("AttributeError", message)
        self.assertNotIn("Traceback (most recent call last)", message.split("\n")[0])
        if needle:
            self.assertIn(needle, message)
        return message

    def assert_action_refused(self, body: str, needle: str | None = None) -> str:
        with self.assertRaises(ProfileError) as ctx:
            self.adapter(body).extract(self.pdf())
        message = str(ctx.exception)
        if needle:
            self.assertIn(needle, message)
        return message

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def assert_gone(self, pid: int, timeout: float = 8.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline and self._alive(pid):
            time.sleep(0.05)
        self.assertFalse(self._alive(pid), f"process {pid} must not survive")

    def child_pid(self) -> int:
        return int(self.pidfile.read_text())


class TestNonzeroExitIsNeverSuccess(WorkerProtocolCase):
    def test_ok_true_with_nonzero_exit_is_a_failure(self):
        self.assert_describe_refused(OK_TRUE_EXIT_7, "exit 7")

    def test_ok_true_with_nonzero_exit_and_full_payload_is_a_failure(self):
        self.assert_describe_refused(FULL_PAYLOAD_EXIT_1, "exit 1")

    def test_nonzero_exit_keeps_the_stderr_diagnostic(self):
        self.assert_describe_refused(NONZERO_WITH_STDERR, "exit 9")

    def test_zero_exit_with_false_ok_is_a_failure(self):
        self.assert_describe_refused(OK_FALSE, "worker said no")

    def test_zero_exit_without_ok_is_a_failure(self):
        self.assert_describe_refused(NO_OK, "did not report success")

    def test_non_boolean_ok_is_a_failure(self):
        for body in (OK_STRING, OK_ONE):
            with self.subTest(body=body.splitlines()[1][:40]):
                self.assert_describe_refused(body, "did not report success")


class TestWrongShapedResponses(WorkerProtocolCase):
    def test_json_array_is_a_typed_failure_not_attributeerror(self):
        self.assert_describe_refused(RAW_ARRAY, "must be a JSON object")

    def test_scalar_null_and_int_responses_are_typed_failures(self):
        for body, kind in ((RAW_SCALAR, "str"), (RAW_NULL, "NoneType"), (RAW_INT, "int")):
            with self.subTest(kind=kind):
                self.assert_describe_refused(body, kind)

    def test_empty_stdout_is_a_typed_failure(self):
        self.assert_describe_refused(RAW_EMPTY, "no response")

    def test_non_json_stdout_is_a_typed_failure(self):
        self.assert_describe_refused(RAW_NOT_JSON, "non-JSON")

    def test_duplicate_json_members_are_refused(self):
        self.assert_describe_refused(RAW_DUPLICATE, "repeated a JSON member")

    def test_trailing_content_after_the_object_is_refused(self):
        self.assert_describe_refused(RAW_TRAILING, "non-JSON")

    def test_unicode_stderr_survives_into_the_diagnostic(self):
        message = self.assert_describe_refused(UNICODE_STDERR, "exit 4")
        self.assertIn("echec de l extraction", message)
        self.assertIn("\u5931\u6557", message)

    def test_json_on_stdout_with_stderr_chatter_still_parses(self):
        self.assertEqual(self.adapter(STDERR_CHATTER).describe()["reader"]["version"], VERSION)


class TestResponseContract(WorkerProtocolCase):
    def test_describe_missing_reader_is_refused(self):
        self.assert_describe_refused(DESCRIBE_NO_READER, "missing a reader object")

    def test_describe_missing_version_is_refused(self):
        self.assert_describe_refused(DESCRIBE_NO_VERSION, "missing a reader version")

    def test_describe_version_mismatch_is_refused(self):
        self.assert_describe_refused(DESCRIBE_WRONG_VERSION, "identity mismatch")

    def test_describe_without_reader_id_or_name_is_refused(self):
        self.assert_describe_refused(DESCRIBE_NO_ID, "missing a reader id or name")

    def test_valid_describe_is_accepted(self):
        self.assertEqual(self.adapter(DESCRIBE_OK).describe()["reader"]["id"], "pypdf-native")

    def test_extract_missing_pages_is_refused(self):
        self.assert_action_refused(EXTRACT_NO_PAGES, "missing a pages list")

    def test_extract_empty_pages_list_is_a_valid_empty_result(self):
        self.assertEqual(self.adapter(EXTRACT_EMPTY_PAGES).extract(self.pdf())["pages"], [])

    def test_extract_page_entry_without_status_is_refused(self):
        self.assert_action_refused(EXTRACT_BAD_STATUS, "unsupported status")

    def test_extract_completed_page_without_raw_text_is_refused(self):
        self.assert_action_refused(EXTRACT_NO_TEXT, "missing raw_text")

    def test_extract_failed_page_without_text_is_accepted(self):
        pages = self.adapter(EXTRACT_FAILED_PAGE).extract(self.pdf())["pages"]
        self.assertEqual(pages[0]["status"], "failed")
        self.assertIsNone(pages[0]["raw_text"])

    def test_extract_rejects_a_wrong_reader_version(self):
        with self.assertRaises(ProfileError) as ctx:
            self.adapter(EXTRACT_FAILED_PAGE, version="7.7.7").extract(self.pdf())
        self.assertIn("identity mismatch", str(ctx.exception))


class TestBoundedCaptureAndCleanup(WorkerProtocolCase):
    def test_flooding_stdout_is_bounded_and_the_child_is_killed(self):
        with self.assertRaises(ProfileError) as ctx:
            self.adapter(FLOOD_STDOUT).describe()
        self.assertIn("capture bound", str(ctx.exception))
        self.assert_gone(self.child_pid())

    def test_flooding_stderr_is_bounded(self):
        with self.assertRaises(ProfileError) as ctx:
            self.adapter(FLOOD_STDERR).describe()
        self.assertIn("capture bound", str(ctx.exception))

    def test_timeout_kills_the_child_and_reports_the_deadline(self):
        start = time.time()
        with self.assertRaises(ProfileError) as ctx:
            self.adapter(HANG)._run({"action": "describe"}, timeout=1.0)
        self.assertIn("timed out after 1.0s", str(ctx.exception))
        self.assertLess(time.time() - start, 30.0)
        self.assert_gone(self.child_pid())

    def test_an_abandoned_descendant_does_not_survive_a_successful_call(self):
        data = self.adapter(ABANDON_DESCENDANT).describe()
        self.assertEqual(data["reader"]["version"], VERSION)
        self.assert_gone(self.child_pid())


if __name__ == "__main__":
    unittest.main()
