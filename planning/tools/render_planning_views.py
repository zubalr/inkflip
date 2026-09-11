#!/usr/bin/env python3
"""Render task/review/DAG/test/requirement/experiment views from canonical JSON.
No remote writes, task execution, acceptance decisions or baseline changes.
"""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads((ROOT/p).read_text())
def write(p,s):(ROOT/p).write_text(s.rstrip()+'\n',encoding='utf-8')
def sentence(s):return s.rstrip('. ') + '.'
def render():
 tasks=load('execution/tasks.json');tests=load('quality/test-matrix.json');reqs=load('execution/requirements.json')
 for t in tasks:
  tid=t['id'];inputs=', '.join('`'+p+'`' for p in t['input_files']);scopes='\n'.join('- `'+p+'`' for p in t['allowed_scope']);checks='\n'.join('- '+sentence(c) for c in t['acceptance_criteria']);cmd='\n'.join(t['commands']);ids=', '.join(t['invariants']);fixtures=', '.join(t['fixture_ids']);dep=', '.join(t['dependencies']) or 'none'
  worker=f'''# {tid} — {t['title']}

## Copy-ready worker prompt

You own **{tid}**, role **{t['owner_role']}**. Use the assigned isolated checkout. The task is planned, not implemented. Verify dependencies **{dep}** are accepted with fresh merged-branch evidence before editing. Read the task's canonical record in `planning/execution/tasks.json`; this brief is its generated view.

Read these compact inputs from `planning/`: {inputs}.

Current-code anchors: {'; '.join(t['current_code_anchors'])}

{t['purpose']}

## Deliver and own

{scopes}

These are target-repository paths, not files claimed to exist in this planning ZIP. Evidence-only receipt/proposal namespaces are allowed under [ownership](../OWNERSHIP.md). Shared contracts, dependencies, root composition and state acceptance require their named owner's lease. Submit state changes to the coordinator; do not accept your own task.

## Contract and exclusions

Canonical contract **{t['contract_version']}**. Required invariants: {ids}.

{t['non_goals']}

Forbidden: {'; '.join(t['forbidden_scope'])}.

## Execute acceptance

Fixture families: {fixtures}. Test records: {', '.join(t['test_ids'])}. Required assertions:

{checks}

```sh
{cmd}
```

These are implementation acceptance commands, not a claim of execution in planning. Gate commands follow the explicit nonrecursive scenario map. A missing dependency, test, required device or tool is blocked evidence, not success. Record the exact implementation and merged commits, versions, command exits, collected/passed/failed/skipped counts, fixture/model hashes, raw outputs and limitations in {', '.join('`'+x+'`' for x in t['evidence_artifacts'])}.

## Failure and rollback

{t['failure_behavior']}

{t['rollback']}

## Plan mismatch and handoff

{t['plan_mismatch']}

{' '.join(sentence(x) for x in t['required_updates'])}

Request [independent review](../reviews/{tid}.md). The implementer cannot approve their own material change. The integrator reruns acceptance on the merged branch, records that commit and only then changes state to accepted. An optional experiment may be rejected only with complete baseline, clean-control, result and review evidence.
'''
  review=f'''# Independent review — {tid}

Review **{t['title']}** in a different session/person from its implementation author. Read [the worker brief](../workers/{tid}.md), the canonical task, changed source, input contracts, fixture expectations and actual receipts. A green badge or implementation summary alone is insufficient.

**Expected purpose:** {t['purpose']}

## Task-specific review

{checks}

Use fixture families {fixtures} and invariants {ids}. Inspect a negative control and an error/partial path relevant to this task, not only a happy example.

```sh
{cmd}
```

## Scope and integrity

Check that implementation edits stay within {', '.join('`'+p+'`' for p in t['allowed_scope'])}, plus the common evidence-only namespaces. Verify approved shared leases, exact contract/dependency identities, complete attribution and no undeclared network or persistence. Reject deleted assertions, unjustified skips, refreshed baselines that hide failure, or tuning on held-out labels. No unrelated SaaS, repair or adjudication code.

## Required disposition

Write `artifacts/tasks/{tid}/review.md`: reviewed commit, reviewer/session identity, commands actually executed, test counts and skips, source/fixture/model identities, issues with severity and reproduction, and accept/request-changes/blocked. Explicitly label inspection-only areas. A material assertion without evidence is not accepted.

Use the task's proposal procedure for plan conflicts. The integrator repeats affected acceptance on the merge result; branch-local success does not certify integration. Preserve original bytes and rejected-experiment receipts. Rollback reverts candidate changes, never rewrites a baseline to erase a failure.
'''
  write(f'execution/workers/{tid}.md',worker);write(f'execution/reviews/{tid}.md',review)
 graph=['# Issue dependency graph','', 'Authoritative records: [tasks.json](tasks.json). All implementation tasks remain planned. Dependencies require accepted merged-branch evidence. Optional technique experiments may close with a reviewed rejection; required capabilities cannot.','', '```mermaid','flowchart TD']
 for t in tasks:
  graph.append(f'  {t["id"]}["{t["id"]} {t["title"]}"]')
  graph += [f'  {d} --> {t["id"]}' for d in t['dependencies']]
 graph+=['```','','| Task | Owner role | Dependencies | Gate |','|---|---|---|---|']
 for t in tasks:graph.append(f'| [{t["id"]}](workers/{t["id"]}.md) {t["title"]} | {t["owner_role"]} | {", ".join(t["dependencies"]) or "none"} | {t["gate"]} |')
 write('execution/ISSUE_DAG.md','\n'.join(graph))
 out=['# Executable acceptance test matrix','','Canonical records: [test-matrix.json](test-matrix.json). These are **specified product tests**, not test results. The separately recorded planning-utility tests do not satisfy these release tests. Gate-owner rows list direct scenarios so a gate runner never recursively invokes itself.','','| Test | Task / level | Command | Assertions |','|---|---|---|---|']
 for t in tests:out.append(f'| {t["id"]} | {", ".join(t["task_ids"])} / {t["level"]} | `{" && ".join(t["commands"])}` | {"; ".join(t["assertions"])} |')
 write('quality/TEST_MATRIX.md','\n'.join(out))
 out=['# Requirement → task → test → release traceability','','Canonical records: [requirements.json](requirements.json). Source sections refer to the authoritative implementation master prompt, not the superseded research investment gates. A mapped requirement is planned, not already implemented.','','| ID | Required outcome | Master sections | Tasks | Tests | Gate |','|---|---|---|---|---|---|']
 for r in reqs:out.append(f'| {r["id"]} | {r["statement"]} | {", ".join(map(str,r["master_sections"]))} | {", ".join(r["task_ids"])} | {", ".join(r["test_ids"])} | {r["gate"]} |')
 write('execution/TRACEABILITY.md','\n'.join(out))
 out=['# Experiments and decision branches','','Canonical records: [experiments.json](experiments.json). Every experiment has a baseline, selected candidate, clean controls, metric, rejection branch and bounded runtime. A scoped planning probe passing does not mean its full product integration or device matrix passed.','']
 for p in load('research/experiments.json'):
  out += [f'## {p["id"]} — {p["hypothesis"]}','',f'**Owner task:** {p["task"]}. **Dependencies:** {", ".join(p["dependencies"]) or "none"}. **Status:** {p["execution_status"]} / {p["result"]}.','',f'**Baseline:** {p["baseline"]}. **Selected candidate:** {p["candidate"]}.','',f'**Fixtures:** {", ".join(p["fixture_ids"])}. **Clean controls:** {p["clean_controls"]}.','',f'**Metrics:** {p["metrics"]}.','',f'**Accept/reject:** {sentence(p["acceptance_rejection"])}','',f'**Resource costs/bounds:** {sentence(p["resource_cost"])}','',f'**Procedure:** `{p["procedure"]}`. **Evidence artifact:** `{p["result_artifact"]}`. For unexecuted experiments this is a required future artifact, not a claimed file in this ZIP.','',f'**Integration decision:** {sentence(p["integration_decision"])}','',f'**Execution qualification:** {p.get("qualification","Only the recorded execution scope is established; full release tests remain separate.")}','', 'Sources: '+', '.join(f'[{s}](SOURCES.md#{s.lower()})' for s in p['source_ids'])+'.','']
 write('research/EXPERIMENT_MATRIX.md','\n'.join(out))
if __name__=='__main__':render();print('Rendered planning views. No implementation task state changed.')
