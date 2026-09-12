# Coordination reference

The active cross-app protocol is `docs/NATIVE_PASSES.md`. It supersedes the
old manual, per-task local admission workflow. The owner approved the private
remote, commits, pushes, selected harnesses and coordinator integration.
`coordination.py` still supplies effective contracts and shared validation
helpers; its historical start commands are not cross-machine admission and
now refuse — the coordinator admits work only through `native_pass.py
dispatch` from the canonical integration checkout.

## Repository and OSS quality

Apply these checks at each task handoff and again to the T55 release candidate.

- Prepare focused commits that explain the problem and resulting behavior. Stage
  named paths after reviewing the diff. Consolidate temporary fixup commits only
  after the writer yields, preserving meaningful history and actual attribution.
- Review implementation and tests for unused dependencies, dead code, abandoned
  scaffolding, speculative abstractions, copied boilerplate and unsupported claims.
  Exercise the maintained format, lint, type, test and build commands. A passing
  command alone does not establish readable code or a polished user experience.
- Track source, reproducible configuration, lockfiles, tests, intentional fixtures,
  required notices and selected documentation/evidence. Ignore regenerable caches,
  local environments, coverage, scratch and private inputs. Keep ignore patterns
  narrow: build provenance, fixtures and acceptance receipts can be source inputs.
- Before public GitHub publication, review both the tracked tree and history
  for secrets, private documents, machine-specific paths, obsolete prompts and
  incidental logs. Decide explicitly which planning and coordination files a
  contributor needs. Preserve working acceptance commands and origin notices
  when separating local orchestration material. Adding an ignore rule does not
  remove already tracked files or historical content. Record the public source
  selection and scan results in the T55 evidence; do not prune a running task.
- T49 must provide a clear README and verified setup/development commands, project
  license and retained third-party notices, contribution instructions and a real
  security-reporting route. User-owned choices or contact details remain explicit
  blockers until supplied; do not fabricate them. Use templates only where they
  help contributors perform a concrete action.
- Capture demos and screenshots from the working candidate. Document limitations
  and link claims to measured behavior. T55 must review contributor onboarding,
  the Git tree/history and the rendered product before release approval.

## Release and evidence boundaries

G1 requires real browser own-file PDF/OCR, controls, geometry, cancellation,
export/reopen, and no-egress. G2 completes the public experience. G3 completes
native/corpus/version regression. G4 completes quality/security/accessibility,
evaluation, rights, and experimental decisions. T55 reviews the final candidate;
T54/G5 requires separate publication permission and actual deployment/rollback.

The current host is macOS arm64. Linux x86_64 native support requires actual
reference-environment evidence. Held-out labels require a separately restricted
environment; a different folder or ordinary Git worktree under the same user is
not access control. Manual accessibility receipts and real device results must
come from those checks. No fixture/probe success certifies the unfinished app.
