# Follow-up delivery repair

Implementation: 682cbc2ea19c6da1516c918b240c4bf2a9608abc
Branch: setup/followup-delivery
Base: 15d4d71c1bf523f427edb9771d1781adaaba6fb3
Owner: Codex, temporary setup scope reserved by Devin in pdf-pass1. Devin remains sole integration, Beads and publication owner.

Explicit non-product grants now reach native inboxes, consume capacity and reserve their write scopes. Their full pdf-... IDs survive relay collection and the Homebase push guard. Notes-only assignments are diagnosed, never inferred as authority. Invalid metadata fails explicitly. Product gates, fixed configured budgets, branch ancestry checks and review acceptance remain intact.

Validation: required scripts/task_acceptance.py run verify passed (97 coordination tests plus bootstrap/native-bootstrap and registry checks). Homebase Linux: 12 follow-up, 23 real installed-hook and 28 relay tests passed in disposable repositories. Independent review found four issues, all fixed and rechecked; see peer-review.md. No product files or planning snapshot changed.

Integration: review this candidate independently as required, integrate at a deliberate checkpoint, rerun affected receipt checks because scripts are COMMON_INPUTS, publish code/Dolt and relay, fast-forward clean Homebase canonical. No hook configuration update is needed: .tools/hooks/pre-push already invokes the canonical Python guard.

Reconcile legacy pdf-8hn and pdf-g78 notes without overwriting live writers or preserved commits. Only Devin may change claims. For a ready unassigned follow-up, dispatch-followup records concrete instructions/mode/scope and publishes. Confirm target status --sync includes the grant, then actual native pickup and checkpoint; collection alone does not prove model execution. Return follow-up checkpoints as hb/inkflip/pdf-ID, collect pdf-ID. Continue product pass gates and real eligible parallel work.

Do not claim this patch is deployed or the app is complete until those operational checks and product acceptance occur. Do not reboot or suspend Homebase. Public T54 publication still needs owner approval.
