# Independent review — T52 (G3 gate / complete native+regression surface)

Independent review of assurance source at 7876213 (reviewer: independent-96362dd8, verified by Devin coordinator exec checks on merged state 1015280).

Verdict: APPROVED.

Evidence: native/tests/gates/test_g3_scenarios.py executes the real CLI end-to-end — named readers with distinct identities (pdfium vs pypdf), partial-failure corpus runs with resume preserving good output, baseline immutability (re-create exit 2 + bytes unchanged; mutated report policy exit 5), CSP/no-script HTML with embedded doc hash, documented exit-code table, and the reader-upgrade example run in a symlinked path-with-spaces sandbox asserting versions 5.9.0->6.18.0. The suite's docstring explicitly disclaims gate authority. Gate G3 executed on merged state: 8/8 scenario tests passed, receipt at artifacts/gates/G3/receipt.json.
