#!/usr/bin/env python3
"""Build a per-artifact navigation and authority index; no task execution."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
SKIP={'__pycache__','.git','node_modules'}
GROUPS={
'adrs':('Selected architecture decision; changed only by reviewed ADR','Architecture owners and integrator','DECISIONS.md'),
'architecture':('Normative implementation specification','Adapter, contract and integration workers','PROJECT_BRIEF.md; contracts/inkflip.schema.json'),
'config':('Canonical planning defaults/pins; resolved locks are produced by T02','Runtime and supply-chain owners','DECISIONS.md; research/sources.json'),
'contracts':('Canonical domain schema and explicitly labeled conformance fixtures','Contract, reader, import and regression workers','architecture/COORDINATES.md; tools/contractlib.py'),
'deployment':('Selected static deployment/runbook or clearly labeled target configuration','Deployment, security and release owner','config/dependencies.json; security/THREAT_MODEL.md'),
'examples':('Executed native prepared evidence; not browser implementation proof','Users, report implementers and reviewers','probes/results/native-probe.json; contracts/inkflip.schema.json'),
'execution':('Canonical task/requirement/gate records, or generated human views','Coordinator, scoped workers, reviewers and owner','PROJECT_BRIEF.md; execution/tasks.json'),
'fixtures':('Original fixed harmless generated sources and their checksums','Fixture, geometry and reader workers','probes/make_fixtures.py; quality/FIXTURE_PROGRAM.md'),
'launch':('Publication drafts/claims to earn; not claims of shipped capabilities','Owner, documentation and presentation workers','execution/RELEASE_CHECKLIST.md; actual future gate receipts'),
'probes':('Executable scoped probe, recorded result or explicit blocked status','Relevant implementer and reviewer','config/dependencies.json; research/experiments.json'),
'product':('Normative product/design/accessibility/copy specification','UI, accessibility and integration workers','PROJECT_BRIEF.md; architecture/GLOSSARY_AND_INVARIANTS.md'),
'quality':('Proposed product quality tests/targets, except explicitly recorded planning results','Evaluation custodian and reviewers','execution/requirements.json; research/experiments.json'),
'reference':('Labeled interaction reference and actual rendering screenshots','UI workers, visual reviewer and owner','product/UX_LAYOUT_AND_INTERACTION.md; reference/README.md'),
'research':('Primary-source inspection, interpretation and scoped experiment ledger','Decision owners and relevant workers','research/INPUTS.md; research/sources.json'),
'security':('Normative threat/privacy/distribution requirements; not certification','Security, import and supply-chain workers','architecture/REPORT_EXPORT_IMPORT.md; config/settings.json'),
 'templates':('Legitimate future record format, explicitly not executed work','Workers and coordinator','execution/RESUME_HANDOFF.md; research/experiments.json'),
 'tools':('Executable planning utility; not finished application code','Coordinator and reviewers','tools/requirements.txt; canonical package records')}
PURPOSES={'START_HERE.md':'Exact path from ZIP validation to local bootstrap, first tasks and release gates.','PROJECT_BRIEF.md':'Chosen user, product loop, full-release boundary, exclusions and definition of done.','PACKAGE_INDEX.md':'Every delivered artifact, its purpose, authority, dependencies and intended readers.','PACKAGE_AUDIT.md':'Actual planning validation results, archive checks and unexecuted product boundaries.','DECISIONS.md':'Decision map and focused ADR entry points.','ASSUMPTIONS_AND_PROBES.md':'Empirical unknowns, selected defaults, decisive tests and fallback branches.','OWNER_INPUTS.md':'Secure owner-controlled values/approvals; local progress without them.','FILE_MANIFEST.json':'Complete byte lengths and SHA-256 inventory; only self-referential integrity files excluded.','SHA256SUMS.txt':'Standard checksum list for all nonexcluded package artifacts.','LICENSE':'MIT license for newly authored planning material and utilities.','NOTICE.md':'Authorship, source influence, third-party separation and execution-status disclosures.'}
def title(p):
 if p.suffix=='.md':
  for l in p.read_text().splitlines():
   if l.startswith('# '):return l[2:].strip().replace('|','/')
 if p.name in PURPOSES:return PURPOSES[p.name]
 return p.stem.replace('-',' ').replace('_',' ')
def build():
 paths=sorted({str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and not any(x in SKIP for x in p.relative_to(ROOT).parts)}|{'PACKAGE_INDEX.md','FILE_MANIFEST.json','SHA256SUMS.txt','PACKAGE_AUDIT.md'})
 out=['# Package index','','## Authority and navigation','','The pasted master prompt controls product scope. [PROJECT_BRIEF.md](PROJECT_BRIEF.md) captures that boundary. The canonical schema, settings, source/experiment ledgers and execution JSON are the machine sources of truth; their generated Markdown views are navigation, not separate competing contracts. Research is supporting evidence. Runtime code has not been implemented except for the explicitly labeled planning probes and utilities.','','Start with [START_HERE.md](START_HERE.md), then the [bootstrap prompt](execution/BOOTSTRAP_PROMPT.md) and [coordinator prompt](execution/COORDINATOR_PROMPT.md). Workers read the brief, glossary/invariants, assigned inputs and their own task/review briefs—not every historical source.','','Future implementation paths inside task manifests are expressly target-repository paths. The links in this index point only to actual package artifacts. Integrity excludes only the two self-referential manifest/checksum files; audit reports and this index are included. Rebuild generated views with `python tools/render_planning_views.py`, this index with `python tools/build_index.py`, and reseal with `python tools/seal_package.py`.','','## Artifact inventory','','| Artifact | Purpose | Authority/status | Dependencies | Intended readers |','|---|---|---|---|---|']
 for name in paths:
  p=ROOT/name;parts=Path(name).parts;first=parts[0]
  authority,readers,deps=GROUPS.get(first,('Root entry point / package governance','Owner, coordinator and reviewers','PROJECT_BRIEF.md; DECISIONS.md'))
  purpose=PURPOSES.get(name,title(p) if p.exists() else name)
  if 'workers' in parts:purpose=f'Copy-ready implementation task {p.stem}: inputs, owned paths, assertions, failure/rollback and handoff.';authority='Generated from execution/tasks.json';deps='execution/tasks.json; task-specific input_files'
  elif 'reviews' in parts:purpose=f'Independent review for {p.stem}: specific negative controls, commands and evidence disposition.';authority='Generated from execution/tasks.json';deps='execution/tasks.json; implementation diff and actual receipts'
  elif name.startswith('contracts/examples/invalid/'):
   purpose='Deliberately invalid '+p.stem+'; expected rejection in invalid-index.json.';authority='Negative conformance example, not a valid report'
  elif name.startswith('contracts/examples/valid/'):
   purpose='Valid '+p.stem+' domain example; inspect result_origin for actual versus synthetic-contract data.'
  elif name.startswith('probes/results/'):
   purpose='Recorded '+p.stem+' output; scope and environment in its corresponding probe receipt.';authority='Execution evidence or explicit blocked status; never generic product proof'
  elif p.suffix=='.pdf':purpose='Original fixed PDF bytes for '+p.stem+'; no font program or private input included.'
  elif p.suffix=='.png':purpose='Actual rendered '+p.stem+' image; interpretation and inspection scope recorded alongside.'
  out.append(f'| [{name}]({name}) | {purpose} | {authority} | {deps} | {readers} |')
 (ROOT/'PACKAGE_INDEX.md').write_text('\n'.join(out)+'\n')
if __name__=='__main__':build();print('Updated per-artifact index.')
