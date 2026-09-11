# Owner-controlled inputs

No secret belongs in this package, a worker prompt, an example report or Git history. None of these values can be inferred from the research.

| Input | Needed for | Local default / handling |
|---|---|---|
| New remote repository name and publication approval | Publishing source and license under your name | Use a new local `inkflip` directory; no remote is created by bootstrap |
| Git author identity | Real commits | Use your existing approved Git configuration; never impersonate another author or backdate |
| Actual SWE-2 mode/model availability and legitimate session concurrency | Dispatching coding sessions | Separate operator-created sessions; record observed mode, or `not observable`; no entitlement assumption |
| CPU/RAM/storage and supported test machines | Worker admission and performance runs | Start a single native process and a single browser OCR worker; queue other work independently |
| Cloudflare account identifier and deploy authorization | Public deployment | Local Vite/preview works without an account; use owner-operated `wrangler login` or a narrowly scoped secret environment token |
| Eventual domain and its DNS approval | Custom public hostname | Owner's selected workers.dev name is sufficient; custom domain is not required for local completion |
| Rights/consent for real incidents | Optional permissioned usefulness/evaluation material | Complete required tests on original synthetic fixtures; never upload customer PDFs to coding sessions without permission |
| License/publication approval | Release own code, fixtures and notes | MIT for new code and synthetic fixture recipes is selected; owner confirms before publishing |
| Native distribution platforms to claim beyond reference Linux x86_64 | Additional binary support | Source install can be documented as unverified elsewhere; do not claim untested native wheels |

Unknown inputs are blockers only for their own action. They are not reasons to stall contracts, UI, browser implementation or the Linux local workflow. Budget or promotion changes may change dispatch tools; they do not change the product architecture or require a different runtime.
