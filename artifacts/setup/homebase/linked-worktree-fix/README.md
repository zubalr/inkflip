# pdf-27v: isolate canonical-root detection

Parent implementation: Astra/Codex, 2026-09-12. Base `cd7935133379305d05256bdf48ebf6a764e76cca`.

The relay suite failed from a real linked checkout: 19 tests produced six failures and eleven errors, all at the canonical-clone guard. Zcode first reported the same failures on Homebase. The suite replaces `coordination.ROOT` with its temporary Git clone, but `run`'s default cwd retains the module's original ROOT. From a linked checkout Git therefore returns the outer repository's absolute common directory, which is then interpreted using the temporary root.

A direct probe confirmed that replacing ROOT with a new temporary Git repository still returned the original Inkflip canonical checkout; explicit `cwd=ROOT` returned that temporary repository's `.git`. The fix supplies the current root explicitly in `canonical_root`. No admission condition, authorization rule, remote check, or gate is removed.

The regression creates a real Git linked checkout, makes the configured path match it, and checks that both relay publication and collection still reject it. It also asserts normal temporary-clone canonical resolution. This test failed before the fix (wrong canonical root) and is included in the passing suite afterward.

Mac linked-checkout verification:

- `PYTHONPATH=tests/coordination PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_homebase_relay.RelayTests.test_real_linked_checkout_is_rejected_with_matching_config -v`: failed before the fix at the explicit canonical-root assertion.
- `PYTHONDONTWRITEBYTECODE=1 python3 scripts/task_acceptance.py run verify`: exit 0 after the fix; 49 bootstrap, 2 native bootstrap, and 64 coordination tests passed (115 total), plus registry self-check. Full output is in `verify-mac-linked.log`.
- `git diff --check`: passed.

The `required tests failed=0 skipped=1` line inside the bootstrap output comes from an intentionally skipped synthetic fixture in an acceptance-integrity negative test. The actual bootstrap suite reports 49 passed, with no skipped required tests. It does not require a gate exception or removal.

Linux verification and independent review are pending at this implementation checkpoint. This correction does not accept any stale product receipt.
