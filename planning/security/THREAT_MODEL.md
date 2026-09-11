# Threat model and containment

The assets at risk are local source bytes, extracted text, filenames/metadata, crops, annotations, report content, developer filesystem, build credentials and the accuracy of public claims. Inputs are untrusted even when supplied by the owner. Trust boundaries are file→parser, renderer→OCR, reader→contract validator, worker→coordinator, imported report→viewer, export→recipient, dependency→build and build→deployment.

| Threat | Concrete entry / failure | Mitigation and test | Residual limit |
|---|---|---|---|
| Parser exploitation | Malformed objects/fonts/images trigger native or WASM defect | Current patched dependencies, bounded process/worker, no scripting/actions, fuzz corpus, native network/privilege restriction | Browser/container/parser vulnerabilities are still possible |
| Resource exhaustion | Huge page, decompressed image, excessive text/objects, deep recursion | Byte/page/pixel/edge/text/object limits before allocation where possible; parent wall deadline; bounded messages | Browser RAM cannot be portably hard-capped; a pathological file may crash a tab |
| Stale-file disclosure | Old worker returns after replacement | Generation/doc/run/job/seq guard before rendering; terminate/revoke; delayed-message tests | Engine memory reclamation is browser-managed |
| Exfiltration | Telemetry, URLs, logs, model request parameters, report resources | No third-party scripts/analytics; exact static request allowlist; canary capture; no URL-based document loading | Host still sees ordinary static connection metadata |
| Script injection | Extracted HTML, bidi text, event attributes, report titles | Strict schema, text nodes, no autolinking or innerHTML, direction isolation; escaped static HTML | A compromised trusted build can violate policy |
| Malicious report assets | Oversized base64/PNG, disguised SVG, deep JSON, duplicate keys | Preparse limits, strict decoder, magic/dimensions/hash, bounded PNG decode+reencode; no archive/HTML import | Checksums do not establish benign content |
| Replay command execution | Report includes a plugin name, shell string or source path | Closed schema; installed reader allowlist; explicit local source choice; no report-controlled process execution | Owner-installed profiles are trusted executable configuration |
| Local path abuse | Native corpus path traversal, symlink escape, output clobber | Explicit source root, no symlinks, canonical path checks, exclusive output, private scratch | Host filesystem permissions remain relevant |
| Process hang/orphan | Native C call ignores signal; child spawns subprocess | Parent deadline, process-group termination, pids limit, kill/wait verification, one bounded retry | Container is not a microVM/security guarantee |
| Supply-chain compromise | Model/binary replacement, postinstall script, unpinned action | Exact lock/digests, allowlisted build scripts, SBOM/notices, checksum refusal, explicit setup network | Signed/hash-matching malicious upstream code remains possible |
| Evaluation leakage | Optimizer sees held-out labels or changes assertions | Separate evaluator checkout/labels, immutable fixture group split, reviewer approval for goldens | Public synthetic mechanisms are not representative real-world prevalence |
| Misleading inference | Zero findings called safe; consensus called true | Typed finding kinds, incomplete coverage, copy tests, no trust score | Human interpretation still needs observation and revision |
| Paid-path drift | Scaffold adds SSR/functions/Worker script | Config/build validator rejects main/bindings/functions and dynamic routes; deployed-path proof | Other account resources and future provider prices remain outside this app |

## Native reference containment

Supported hardened route: Linux OCI container, non-root UID, read-only root, read-only input mount, dedicated writable output mount and capped tmpfs scratch, `--network none`, `--cap-drop ALL`, `--security-opt no-new-privileges`, bounded pids/CPU/memory. Do not mount Docker socket, home directory, SSH agent, cloud credentials or arbitrary host roots. Parent supervisor sits outside the parser child and enforces wall/output limits even when a child blocks native signals. Direct source installs are useful but explicitly provide weaker containment than the hardened route.

Parse-only jobs must not inherit proxy tokens, cloud credentials or broad environment variables. Construct a minimal environment allowlist (locale, fixed language-data path, thread counts, temp directory). Set thread libraries to one thread per child by default. Use subprocess argv arrays, no shell interpolation. Reports never carry executable commands. pypdfium2 calls stay in one thread per process; more processes require a memory-aware operator decision. [PDFium source](../research/SOURCES.md#s26).

## Vulnerability handling

At bootstrap and before every release, audit the resolved npm/Python lock, base image, PDFium/Tesseract binaries and model/package provenance against current primary advisories. A reproducible lock is not proof of safety. A known reachable critical/high parser issue blocks public release until patched or the affected capability is removed with explicit limits. A non-reachable finding requires documented reasoning and independent review, not blanket severity dismissal.

Patch within the selected library family, rerun geometry/fixture/regression/privacy tests, publish a new artifact identity and preserve old reports. Do not update a dependency silently while continuing to advertise an old prepared manifest. Security reports from users should be handled without asking them to post confidential PDFs publicly; use minimized synthetic reproductions or explicitly consented handling.

No exploit payload generator is included. Malicious test strings and fixed harmless PDF mechanisms exercise boundaries without network destinations or destructive behavior.
