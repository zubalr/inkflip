# Native Beads portability verification

Beads 1.2.2 (revision 6c124203e771433a3550c348771a5b5e27fd3c21) was tested
with three disposable clones and a local bare Git remote. Native Dolt push,
bootstrap and pull preserved synthetic tasks, a blocking dependency, nested
metadata, labels, assignees, notes and durable memory. No separate server or
Dolt executable was needed. Git clone alone did not restore the database.

Competing offline claims both succeeded locally, but the second push failed
non-fast-forward and pull reported a merge conflict without silently changing
ownership. Therefore the production protocol has one Beads writer (Devin)
and read-only worker replicas. A successful publication precedes dispatch.
This test did not prove globally atomic claims across independent writers.

First publish an ordinary Git branch, then the Beads data. Native transport
created refs/dolt/data and the __dolt_remote_info__ support branch.

The official Linux amd64 archive for v1.2.2 was downloaded, and its SHA-256
matched both official checksums and release API digest:
8140098a51d3b81d5548d1c5e6db1a2d9930e5d141efe2a4bff7d079c4d321e8.
Build metadata matches the installed macOS revision. Linux execution was not
tested on this macOS host; the cloud bootstrap must verify it in its environment.

Primary release: https://github.com/gastownhall/beads/releases/tag/v1.2.2
Pinned bootstrap source: https://github.com/gastownhall/beads/blob/v1.2.2/cmd/bd/bootstrap.go

Authenticated GitHub restoration and the final repository smoke results are
recorded separately in native-verification.json after the remote publication.
