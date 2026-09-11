# Earned demonstration and curated gallery

Six public cards, not a wall of near-duplicate traps. All labels describe reader behavior rather than deception by a person. Every gallery asset has a fixed generator, license, source hash, named reader build/config, actual output and clean counterpart/negative control. Downloadable source and manifest are adjacent to “How this was checked”. A prepared report may be instant because it is marked prepared; own-file results must be live.

| Card / fixture family | Mechanism and intended experience | Required expected evidence | Current planning execution |
|---|---|---|---|
| The amount that reads differently | Font ToUnicode maps the displayed `1` to `1,0`; visual `$100` becomes extracted `$1,000` | Named native/browser output; source crop; clean mapping counterpart renders identically | Executed native PDFium/Tesseract proof; browser-specific manifest still required |
| A cover is not a rewrite | Paint `$1,000`, cover with opaque rectangle, paint `$100` | Show actual text returned, not assumed concatenation; structural check limitation | Fixed source generated and native outputs recorded; PDFium returned `$1,00000`, pypdf `$1,000$100` |
| The ordinary searchable scan | Owned raster of ordinary printed English plus correct invisible text layer | No alarm solely for non-painting text; compare actual OCR and layer | Recipe specified, not generated/executed in this pass |
| The rotated postcard | Nonzero media/crop origins, rotation, UserUnit; paired clean geometry | Correct location through zoom/rotation; off-view support explicitly named | Four fixed geometry PDFs executed through native metadata/render probe |
| Two columns, two reading orders | Same visible paragraph columns, different content stream emission order | Actual raw reader sequence and derived geometric order, not accessibility verdict | Recipe specified; exact reader outputs freeze after execution |
| Same words, different places | Repeated amounts/serial strings with one lightly damaged raster region | Separate occurrences, bounded region OCR, ambiguous matches left unresolved | Contract fixtures for duplicates included; damaged OCR outputs not invented |

White-on-dark/white-on-white, clipped/partial covers, ligatures, missing mapping and long-document partial coverage belong in the broader fixture corpus and the gallery's detail controls, not seven more homepage cards. Non-Latin native reading examples demonstrate preservation, not English OCR support for every script.

## Fixed amount source construction

`probes/make_fixtures.py` writes a small original PDF with base-14 Helvetica and a ToUnicode CMap. The generator contains only fixed harmless examples; it cannot build arbitrary payloads. It embeds no font program. The mapping and control have identical painting operators but different text mappings. `probes/native_probe.py` checks actual extraction, renders both with the installed PDFium build and compares pixels, then runs one selected crop through Tesseract. The stored native result proves the mechanism in that environment. It does not prove the planned browser reader output or arbitrary compositing behavior.

The prepared evidence report intentionally marks automatic alignment unsupported because the native proof manually selects the known crop. Do not relabel it as a passed automatic-finding pipeline. G1 must process the source as an ordinary local File through PDF.js/Tesseract.js and the implemented alignment. If PDF.js's current reading differs from the proposed headline, use the measured wording or select another generated mapping supported by actual bytes; never insert a filename conditional into the UI.

## Clip scripts

**10-second silent presentation:** 0–2 show synthetic label and original crop; 2–4 highlight Page control and `$100`; 4–6 select named extracted reading; 6–8 open its evidence with both outputs; 8–10 show “Keep evidence” and the local-file action. Duration is editing/storyboard design, not a promised runtime. Every prepared section stays labelled. Any accelerated processing is marked “sped up”.

**30-second walkthrough:** reveal the amount, open its actual manifest, show the ordinary searchable-scan control without alarm, choose a selected region, and export a report whose coverage and source-inclusion status are visible.

**Full walkthrough:** open a new permitted local PDF, choose pages and prepare a model on first use; show real progress or partial/cancelled state; inspect repeated occurrences and an ambiguous case; export selected evidence; reopen it without the source; attach the matching original and run a local CLI replay; demonstrate an upgrade comparison with an explicit acceptance rule. Do not edit out every failure or imply an edited sequence was continuously live.

## Publication gate

No demo claim ships before source bytes, generator version, exact actual readers, renderer settings, model hash, raw outputs and report are linked and tested in the release build. Native-prepared and browser-prepared manifests are different. Each card has a clean control. No challenge applicant vocabulary or customer-sensitive document appears in the public gallery. Gallery usefulness does not substitute for the live own-file gate.
