"""Independent evaluation protocol for the Inkflip inspector (T36).

This package implements the evaluation-custodian side of
``planning/quality/EVALUATION.md``:

* :mod:`evaluation.protocol.lineage` clusters fixtures and corpus documents
  into sibling groups (same generator family, control twins and identical
  source bytes) and audits frozen development/public_demo/evaluation/
  permissioned splits so a group can never straddle a boundary.
* :mod:`evaluation.protocol.metrics` computes precise denominators where
  skipped/failed/timeout/never-attempted pages stay visible, collapses
  repeated readings of one page into a single sample, and produces Wilson
  and grouped-bootstrap intervals.
* :mod:`evaluation.protocol.manifest` validates the frozen corpus manifests
  and the evaluation plan; the plan format cannot carry a self-attested
  verdict.
* :mod:`evaluation.protocol.custody` is the custodian gate: held-out labels
  resolve only from an explicit label root outside every repository
  checkout, match a pinned digest, and are never emitted into artifacts.
* :mod:`evaluation.protocol.diagnosis` provides the blinded reviewer forms,
  counterbalanced assignment and disagreement-preserving adjudication used
  for useful-finding precision and diagnosis usefulness.
* :mod:`evaluation.protocol.report` binds a validated inspection run to a
  corpus manifest and label store and computes target verdicts. Verdicts
  exist only where a real run produced counts: every target is UNMET until
  then.

Nothing here turns a disagreement into truth (I06), improves a comparison
by losing coverage (I12), invents executed work (I16) or claims beyond the
measured population (I18). Stdlib only.
"""

PROTOCOL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
