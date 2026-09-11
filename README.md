# Inkflip

A PDF reading inspector being built as a browser application with local
native-reader, corpus and regression tools. This private repository currently
contains the accepted bootstrap scaffold, the preserved specification and the
implementation workflow. The product features are not yet implemented.

See [START_HERE.md](START_HERE.md) for the three native app entry prompts and
[docs/NATIVE_PASSES.md](docs/NATIVE_PASSES.md) for shared execution. Beads owns
live task status; the planning snapshot is the specification.

Python 3.11+ can run the current bootstrap checks:

```sh
python3 scripts/task_acceptance.py run verify
```

T02 resolves and installs the production toolchain and dependencies. Product
build and browser/native commands deliberately fail until their owners
implement them. Do not interpret bootstrap checks as product acceptance.

The agreed stack is Bun with isolated dependencies, React, Vite, TypeScript,
CSS Modules, central semantic tokens, Python/uv and a Node comparison bridge.
See [docs/ORIGIN.md](docs/ORIGIN.md) and the retained third-party notices for
source provenance. Public release, licensing choices and contributor onboarding
are completed in the later release tasks.
